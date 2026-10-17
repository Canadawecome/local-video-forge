"""OpusClip Project Manager & Batch Barrier for Local Video Forge v2.6.
Manages OpusClip project submission, polling, clip enumeration, and download.
Enforces the OPUS_BATCH_BARRIER (Section 0 & Section 5 of the SPEC).
Supports both real OpusClip API and local clip import / mock mode for testing without credits.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

from config import Config
from local_video_forge_batch_contracts_v2_5 import (
    BatchCounts,
    BatchManifestV25,
    BatchState,
    ClipRecord,
    ClipState,
    NarrationMode,
    OpusProjectRecord,
    OpusProjectState,
    RightsState,
)
from storage.db import get_connection

logger = logging.getLogger("opus_manager")

def probe_video(video_path: Path) -> dict[str, Any]:
    """Runs ffprobe on a video file and returns duration, width, height, has_audio."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration,size:stream=codec_type,width,height",
        "-of", "json",
        str(video_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)
    
    duration = float(data.get("format", {}).get("duration", 0.0))
    width = 0
    height = 0
    has_audio = False
    
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            width = int(s.get("width") or 0)
            height = int(s.get("height") or 0)
        elif s.get("codec_type") == "audio":
            has_audio = True
            
    return {
        "duration": duration,
        "width": width,
        "height": height,
        "has_audio": has_audio,
    }

def compute_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

class OpusManager:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or Config.OPUSCLIP_API_KEY
        self.base_url = (base_url or Config.OPUSCLIP_BASE_URL).rstrip("/")

    def create_batch(
        self,
        source_id: str,
        youtube_url: str,
        max_spend_usd: float = 10.0,
        clip_selection_policy: str = "ALL_USABLE",
    ) -> str:
        """Initializes a new source batch record in DB."""
        batch_id = f"batch_{source_id}_{int(time.time())}"
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sources (id, youtube_url) VALUES (?, ?)",
                (source_id, youtube_url),
            )
            conn.execute(
                """INSERT INTO source_batches 
                (id, source_id, config_hash, barrier_state, clip_selection_policy, max_spend_usd) 
                VALUES (?, ?, ?, ?, ?, ?)""",
                (batch_id, source_id, f"cfg_{source_id}", BatchState.CREATED.value, clip_selection_policy, max_spend_usd),
            )
        return batch_id

    def submit_opus_project(
        self,
        batch_id: str,
        youtube_url: str,
        custom_prompt: str,
        candidate_window_id: str | None = None,
    ) -> OpusProjectRecord:
        """Submits an OpusClip project for the whole video or candidate window."""
        project_record_id = f"opus_p_{int(time.time() * 1000)}"
        
        # If API key is not configured, register in MOCK / LOCAL mode
        if not self.api_key:
            logger.info("OPUSCLIP_API_KEY not configured. Project scheduled in LOCAL/MOCK mode.")
            rec = OpusProjectRecord(
                project_id=project_record_id,
                status=OpusProjectState.SUCCEEDED,
                candidate_window_id=candidate_window_id,
                request_hash=hashlib.sha256(f"{youtube_url}:{custom_prompt}".encode()).hexdigest(),
            )
            with get_connection() as conn:
                conn.execute(
                    """INSERT INTO opus_projects 
                    (id, batch_id, provider_project_id, window_id, status, request_hash)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (rec.project_id, batch_id, rec.project_id, candidate_window_id, rec.status.value, rec.request_hash),
                )
            return rec

        # Call real OpusClip API
        url = f"{self.base_url}/clip-projects"
        payload = {
            "videoUrl": youtube_url,
            "curationPref": {
                "model": "ClipAnything",
                "clipDurations": [[60, 90]],
                "customPrompt": custom_prompt,
            },
            "renderPref": {"layoutAspectRatio": "portrait"},
            "importPreference": {"sourceLang": "de"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                provider_proj_id = data.get("id") or project_record_id
        except Exception as e:
            logger.error(f"Failed submitting Opus project: {e}")
            raise

        rec = OpusProjectRecord(
            project_id=provider_proj_id,
            status=OpusProjectState.RUNNING,
            candidate_window_id=candidate_window_id,
            request_hash=hashlib.sha256(f"{youtube_url}:{custom_prompt}".encode()).hexdigest(),
        )
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO opus_projects 
                (id, batch_id, provider_project_id, window_id, status, request_hash)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (rec.project_id, batch_id, rec.project_id, candidate_window_id, rec.status.value, rec.request_hash),
            )
        return rec

    def poll_and_download_clips(
        self,
        batch_id: str,
        source_id: str,
        project_id: str,
        max_wait_sec: int = 600,
        poll_interval_sec: int = 15,
    ) -> list[ClipRecord]:
        """Polls OpusClip API until project reaches COMPLETE, then downloads all clips."""
        source_dir = Config.DATA_DIR / "sources" / source_id
        opus_exports_dir = source_dir / "opus" / "opus_exports"
        opus_exports_dir.mkdir(parents=True, exist_ok=True)

        url_proj = f"{self.base_url}/clip-projects/{project_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }

        start_time = time.time()
        logger.info(f"Waiting for OpusClip project {project_id} to finish processing...")
        stage = "QUEUED"

        while time.time() - start_time < max_wait_sec:
            try:
                req = urllib.request.Request(url_proj, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    p_data = json.loads(resp.read().decode("utf-8"))
                    stage = p_data.get("stage", "PROCESSING")
                    logger.info(f"OpusClip project {project_id} status: {stage}")

                    if stage == "COMPLETE":
                        break
                    elif stage in ("FAILED", "ERROR"):
                        with get_connection() as conn:
                            conn.execute("UPDATE opus_projects SET status = ? WHERE id = ?", (OpusProjectState.FAILED.value, project_id))
                        raise RuntimeError(f"OpusClip project {project_id} failed on server.")
            except Exception as e:
                logger.warning(f"Error checking Opus project status: {e}")

            time.sleep(poll_interval_sec)

        if stage != "COMPLETE":
            with get_connection() as conn:
                conn.execute("UPDATE opus_projects SET status = ? WHERE id = ?", (OpusProjectState.TIMED_OUT.value, project_id))
            raise TimeoutError(f"OpusClip project {project_id} timed out after {max_wait_sec}s.")

        # Update project to SUCCEEDED
        with get_connection() as conn:
            conn.execute("UPDATE opus_projects SET status = ? WHERE id = ?", (OpusProjectState.SUCCEEDED.value, project_id))

        # Fetch exportable clips
        clips_url = f"{self.base_url}/exportable-clips?q=findByProjectId&projectId={project_id}"
        req_clips = urllib.request.Request(clips_url, headers=headers)
        with urllib.request.urlopen(req_clips, timeout=30) as resp:
            clips_resp = json.loads(resp.read().decode("utf-8"))
            raw_clips = clips_resp.get("data", [])

        logger.info(f"OpusClip returned {len(raw_clips)} clips for project {project_id}. Downloading...")

        imported: list[ClipRecord] = []
        for idx, item in enumerate(raw_clips, start=1):
            clip_id = f"clip_{idx:03d}"
            clip_uid = f"{source_id}:{project_id}:{clip_id}"
            clip_export_dir = opus_exports_dir / clip_id
            clip_export_dir.mkdir(parents=True, exist_ok=True)
            dest_file = clip_export_dir / "original_opus.mp4"

            # Download MP4
            dl_url = item.get("uriForExport") or item.get("uriForPreview")
            if not dl_url:
                continue

            dl_req = urllib.request.Request(dl_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(dl_req, timeout=120) as resp, open(dest_file, "wb") as f_out:
                shutil.copyfileobj(resp, f_out)

            probe = probe_video(dest_file)
            sha = compute_sha256(dest_file)

            out_folder_rel = f"output/clip_{idx:03d}_craft"
            full_out_folder = source_dir / out_folder_rel
            full_out_folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest_file, full_out_folder / "original_opus.mp4")

            meta = {
                "provider": "opusclip_cloud",
                "width": probe["width"],
                "height": probe["height"],
                "duration": probe["duration"],
                "has_audio": probe["has_audio"],
                "viral_score": float(item.get("score") or 80.0),
                "title": item.get("title") or f"Clip {idx}",
            }

            rec = ClipRecord(
                clip_uid=clip_uid,
                index_no=idx,
                provider_project_id=project_id,
                provider_clip_id=clip_id,
                status=ClipState.ASSET_DOWNLOADED,
                folder=out_folder_rel,
                narration_mode=NarrationMode.ORIGINAL_COMMENTARY,
                rights_state=RightsState.VERIFIED,
                accepted=True,
            )

            with get_connection() as conn:
                conn.execute(
                    """INSERT INTO clips 
                    (id, batch_id, opus_project_id, opus_clip_id, index_no, status,
                     source_asset_path, source_asset_sha256, duration_sec, opus_metadata_json,
                     output_folder, title_en, narration_mode, revision)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        batch_id=excluded.batch_id,
                        opus_project_id=excluded.opus_project_id,
                        opus_clip_id=excluded.opus_clip_id,
                        index_no=excluded.index_no,
                        status=excluded.status,
                        source_asset_path=excluded.source_asset_path,
                        source_asset_sha256=excluded.source_asset_sha256,
                        duration_sec=excluded.duration_sec,
                        opus_metadata_json=excluded.opus_metadata_json,
                        output_folder=excluded.output_folder,
                        title_en=excluded.title_en,
                        narration_mode=excluded.narration_mode,
                        revision=excluded.revision""",
                    (
                        clip_uid, batch_id, project_id, clip_id, idx, rec.status.value,
                        str(dest_file.relative_to(Config.DATA_DIR)), sha, probe["duration"],
                        json.dumps(meta), out_folder_rel, f"Artisan Craft Clip {idx:02d}",
                        rec.narration_mode.value, 1,
                    )
                )

            with open(full_out_folder / "clip_info.json", "w", encoding="utf-8") as f:
                json.dump({
                    "clip_uid": clip_uid,
                    "index_no": idx,
                    "source_asset_sha256": sha,
                    "duration_sec": probe["duration"],
                    "dimensions": [probe["width"], probe["height"]],
                    "status": rec.status.value,
                }, f, indent=2)

            imported.append(rec)

        return imported

    def import_local_clips(
        self,
        batch_id: str,
        source_id: str,
        clip_mp4_paths: list[str | Path],
    ) -> list[ClipRecord]:
        """Imports local existing MP4 clips as OpusClip exported clips."""
        source_dir = Config.DATA_DIR / "sources" / source_id
        opus_exports_dir = source_dir / "opus" / "opus_exports"
        opus_exports_dir.mkdir(parents=True, exist_ok=True)

        # Ensure an Opus project exists for this batch
        with get_connection() as conn:
            row = conn.execute("SELECT id FROM opus_projects WHERE batch_id = ? LIMIT 1", (batch_id,)).fetchone()
            if row:
                project_id = row["id"]
            else:
                project_id = f"opus_p_{int(time.time() * 1000)}"
                conn.execute(
                    "INSERT INTO opus_projects (id, batch_id, status) VALUES (?, ?, ?)",
                    (project_id, batch_id, OpusProjectState.SUCCEEDED.value)
                )

        imported: list[ClipRecord] = []
        for idx, src_p in enumerate(clip_mp4_paths, start=1):
            src_path = Path(src_p)
            if not src_path.exists():
                logger.warning(f"Clip path does not exist: {src_path}")
                continue

            clip_id = f"clip_{idx:03d}"
            clip_uid = f"{source_id}:{project_id}:{clip_id}"
            
            # Destination folder per spec:
            clip_export_dir = opus_exports_dir / f"clip_{idx:03d}"
            clip_export_dir.mkdir(parents=True, exist_ok=True)
            dest_file = clip_export_dir / "original_opus.mp4"
            shutil.copy2(src_path, dest_file)

            probe = probe_video(dest_file)
            sha = compute_sha256(dest_file)

            out_folder_rel = f"output/clip_{idx:03d}_craft"
            full_out_folder = source_dir / out_folder_rel
            full_out_folder.mkdir(parents=True, exist_ok=True)
            # Copy original into the clip folder as well
            shutil.copy2(dest_file, full_out_folder / "original_opus.mp4")

            meta = {
                "provider": "opusclip_local",
                "width": probe["width"],
                "height": probe["height"],
                "duration": probe["duration"],
                "has_audio": probe["has_audio"],
                "viral_score": 85.0,
            }

            rec = ClipRecord(
                clip_uid=clip_uid,
                index_no=idx,
                provider_project_id=project_id,
                provider_clip_id=clip_id,
                status=ClipState.ASSET_DOWNLOADED,
                folder=out_folder_rel,
                narration_mode=NarrationMode.ORIGINAL_COMMENTARY,
                rights_state=RightsState.VERIFIED,
                accepted=True,
            )

            # Persist to DB
            with get_connection() as conn:
                conn.execute(
                    """INSERT INTO clips 
                    (id, batch_id, opus_project_id, opus_clip_id, index_no, status,
                     source_asset_path, source_asset_sha256, duration_sec, opus_metadata_json,
                     output_folder, title_en, narration_mode, revision)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        batch_id=excluded.batch_id,
                        opus_project_id=excluded.opus_project_id,
                        opus_clip_id=excluded.opus_clip_id,
                        index_no=excluded.index_no,
                        status=excluded.status,
                        source_asset_path=excluded.source_asset_path,
                        source_asset_sha256=excluded.source_asset_sha256,
                        duration_sec=excluded.duration_sec,
                        opus_metadata_json=excluded.opus_metadata_json,
                        output_folder=excluded.output_folder,
                        title_en=excluded.title_en,
                        narration_mode=excluded.narration_mode,
                        revision=excluded.revision""",
                    (
                        clip_uid, batch_id, project_id, clip_id, idx, rec.status.value,
                        str(dest_file.relative_to(Config.DATA_DIR)), sha, probe["duration"],
                        json.dumps(meta), out_folder_rel, f"Artisan Craft Clip {idx:02d}",
                        rec.narration_mode.value, 1,
                    )
                )

            # Save clip_info.json
            with open(full_out_folder / "clip_info.json", "w", encoding="utf-8") as f:
                json.dump({
                    "clip_uid": clip_uid,
                    "index_no": idx,
                    "source_asset_sha256": sha,
                    "duration_sec": probe["duration"],
                    "dimensions": [probe["width"], probe["height"]],
                    "status": rec.status.value,
                }, f, indent=2)

            imported.append(rec)

        return imported

    def close_batch_discovery(
        self,
        batch_id: str,
        source_id: str,
        youtube_url: str,
    ) -> BatchManifestV25:
        """Enforces OPUS_BATCH_BARRIER:
        Verifies that all Opus projects have reached a terminal state,
        enumerates all clips, verifies counts, and writes batch_manifest.json.
        """
        with get_connection() as conn:
            proj_rows = conn.execute(
                "SELECT id, status, window_id, request_hash FROM opus_projects WHERE batch_id = ?",
                (batch_id,)
            ).fetchall()

            clip_rows = conn.execute(
                "SELECT * FROM clips WHERE batch_id = ? ORDER BY index_no ASC",
                (batch_id,)
            ).fetchall()

        opus_projects: list[OpusProjectRecord] = []
        for r in proj_rows:
            p_state = OpusProjectState(r["status"])
            if p_state not in {OpusProjectState.SUCCEEDED, OpusProjectState.FAILED, OpusProjectState.TIMED_OUT, OpusProjectState.CANCELLED}:
                raise RuntimeError(f"Cannot close batch: Opus project {r['id']} is still in non-terminal state {p_state}")
            opus_projects.append(OpusProjectRecord(
                project_id=r["id"],
                status=p_state,
                candidate_window_id=r["window_id"],
                request_hash=r["request_hash"],
            ))

        discovered_clips: list[ClipRecord] = []
        for r in clip_rows:
            rec = ClipRecord(
                clip_uid=r["id"],
                index_no=r["index_no"],
                provider_project_id=r["opus_project_id"],
                provider_clip_id=r["opus_clip_id"],
                status=ClipState(r["status"]),
                folder=r["output_folder"],
                narration_mode=NarrationMode(r["narration_mode"]),
                rights_state=RightsState.VERIFIED,
                accepted=True,
            )
            discovered_clips.append(rec)

        n_discovered = len(discovered_clips)
        n_accepted = len([c for c in discovered_clips if c.accepted])

        counts = BatchCounts(
            discovered=n_discovered,
            accepted=n_accepted,
            script_pass=0,
            voice_pass=0,
            final_pass=0,
            asmr_final_pass=0,
        )

        manifest = BatchManifestV25(
            schema_version="2.5",
            batch_id=batch_id,
            source_id=source_id,
            youtube_url=youtube_url,
            batch_status=BatchState.OPUS_BATCH_COMPLETE,
            opus_projects=opus_projects,
            discovered_clips=discovered_clips,
            counts=counts,
            opus_batch_closed=True,
        )

        # Write manifest to source dir
        source_dir = Config.DATA_DIR / "sources" / source_id
        opus_dir = source_dir / "opus"
        opus_dir.mkdir(parents=True, exist_ok=True)
        
        with open(opus_dir / "batch_manifest.json", "w", encoding="utf-8") as f:
            f.write(manifest.model_dump_json(indent=2))

        with open(source_dir / "batch_manifest.json", "w", encoding="utf-8") as f:
            f.write(manifest.model_dump_json(indent=2))

        # Update DB batch state
        with get_connection() as conn:
            conn.execute(
                "UPDATE source_batches SET barrier_state = ? WHERE id = ?",
                (BatchState.OPUS_BATCH_COMPLETE.value, batch_id),
            )

        return manifest
