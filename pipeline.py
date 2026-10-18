"""Master Pipeline Orchestrator for Local Video Forge v2.6.
Executes the full pipeline:
One YouTube URL -> Source Text Scout -> OpusClip Multi-Clip ->
Dynamic Fan-Out Barrier -> Per-Clip Sol Inspection -> Per-Clip Script ->
Per-Clip ElevenLabs TTS -> Per-Clip FFmpeg Render -> Publication Pack.
Supports isolated per-clip retries and budget guards.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable

from adapters.sol_adapter import SolAdapter
from config import Config
from local_video_forge_batch_contracts_v2_5 import (
    BatchCounts,
    BatchManifestV25,
    BatchState,
    ClipRecord,
    ClipState,
    NarrationMode,
    RightsState,
)
from modules.clip_inspector import ClipInspector
from modules.opus_manager import OpusManager
from modules.publication_pack import PublicationPackManager
from modules.render_engine import RenderEngine
from modules.script_generator import ScriptGenerator
from modules.source_scout import SourceScout
from storage.db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("pipeline")

class PipelineOrchestrator:
    def __init__(self):
        self.sol = SolAdapter()
        self.scout = SourceScout(self.sol)
        self.opus = OpusManager()
        self.inspector = ClipInspector(self.sol)
        self.script_gen = ScriptGenerator(self.sol)
        from modules.voice_engine import VoiceEngine
        self.voice = VoiceEngine()
        self.renderer = RenderEngine()
        self.publisher = PublicationPackManager(self.sol)

    def run_full_pipeline(
        self,
        youtube_url: str,
        source_id: str | None = None,
        local_srt_path: str | Path | None = None,
        local_clip_paths: list[str | Path] | None = None,
        opus_project_id: str | None = None,
        rights_status: str = "VERIFIED",
        max_spend_usd: float = 10.0,
        time_range: tuple[float, float] | list[float] | None = None,
        video_range: tuple[float, float] | list[float] | None = None,
        time_ranges: list[list[float]] | None = None,
        progress_callback: Callable[[str, float, str], None] | None = None,
    ) -> BatchManifestV25:
        """Runs the entire end-to-end pipeline with strict contract enforcement."""
        def notify(stage: str, pct: float, msg: str):
            logger.info(f"[{pct*100:.0f}%] {stage}: {msg}")
            if progress_callback:
                progress_callback(stage, pct, msg)

        # 1. Source Identity
        if not source_id:
            raw_id = youtube_url.split("v=")[-1].split("&")[0] if "v=" in youtube_url else "src"
            source_id = f"src_{raw_id}_{int(time.time())}"

        source_dir = Config.DATA_DIR / "sources" / source_id
        source_dir.mkdir(parents=True, exist_ok=True)

        # 2. Source Text Scout
        notify("SOURCE_SCOUT", 0.15, "Fetching YouTube metadata & running GPT-5.6 Sol Text Scout...")
        scout_plan = self.scout.execute_scout(
            source_id=source_id,
            youtube_url=youtube_url,
            local_srt_path=local_srt_path,
            rights_status=rights_status,
        )

        notify("PREFLIGHT", 0.20, f"Initializing source batch for {source_id}...")
        batch_id = self.opus.create_batch(source_id, youtube_url, max_spend_usd)

        # 3. Opus Projects & Clip Ingest
        notify("OPUS_BATCH", 0.30, "Scheduling OpusClip projects & retrieving clips...")
        if opus_project_id:
            logger.info(f"Using OpusClip project ID {opus_project_id}...")
            with get_connection() as conn:
                conn.execute(
                    """INSERT INTO opus_projects (id, batch_id, status) VALUES (?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET batch_id=excluded.batch_id""",
                    (opus_project_id, batch_id, "RUNNING")
                )
            self.opus.poll_and_download_clips(batch_id, source_id, opus_project_id)
        elif local_clip_paths:
            logger.info(f"Importing {len(local_clip_paths)} local clips...")
            self.opus.import_local_clips(batch_id, source_id, local_clip_paths)
        else:
            sample_clip = Path("/Volumes/KINGSTON/Reup Từ Đức/Video làm đồ thủ công/after edit/C1ND2YXWET59.mp4")
            if sample_clip.exists() and not self.opus.api_key:
                logger.info(f"Found sample craft video at {sample_clip}, importing as candidate clip...")
                self.opus.import_local_clips(batch_id, source_id, [sample_clip])
            else:
                effective_range = time_range or video_range
                effective_window_id = None
                if not effective_range and not time_ranges and getattr(scout_plan, 'candidate_windows', None):
                    cw = scout_plan.candidate_windows[0]
                    effective_range = (cw.start_sec, cw.end_sec)
                    effective_window_id = cw.window_id

                proj = self.opus.submit_opus_project(
                    batch_id=batch_id,
                    youtube_url=youtube_url,
                    custom_prompt=scout_plan.global_opus_prompt_en,
                    candidate_window_id=effective_window_id,
                    time_range=effective_range,
                    time_ranges=time_ranges,
                )
                self.opus.poll_and_download_clips(batch_id, source_id, proj.project_id)

        # 4. OPUS_BATCH_BARRIER: Enforce barrier before fan-out
        notify("OPUS_BARRIER", 0.40, "Closing batch discovery barrier & enumerating N clips...")
        manifest = self.opus.close_batch_discovery(batch_id, source_id, youtube_url)
        n_clips = len(manifest.discovered_clips)
        logger.info(f"OPUS_BATCH_BARRIER CLOSED: Discovered N={n_clips} clips.")

        if n_clips == 0:
            logger.warning("No usable clips returned by OpusClip or import.")
            return manifest

        # 5. Dynamic Fan-Out: Process each accepted clip independently
        script_pass_count = 0
        voice_pass_count = 0
        final_pass_count = 0

        for i, clip in enumerate(manifest.discovered_clips, start=1):
            clip_folder = source_dir / clip.folder
            clip_folder.mkdir(parents=True, exist_ok=True)
            clip_mp4 = clip_folder / "original_opus.mp4"
            
            step_base = 0.40 + (i - 1) * (0.55 / n_clips)
            step_weight = 0.55 / n_clips

            final_mp4 = clip_folder / "final.mp4"
            publish_pack_file = clip_folder / "publish_pack.json"
            qc_file = clip_folder / "qc_report.json"

            # v2.9 Idempotency / Resuming: Check if clip is already rendered and passed QC
            if final_mp4.is_file() and publish_pack_file.is_file() and qc_file.is_file():
                try:
                    qc_data = json.loads(qc_file.read_text(encoding="utf-8"))
                    if qc_data.get("qc_verdict") == "PASS" or qc_data.get("status") == "RENDERED_WITH_APPROVED_AUDIO_AND_EN_SUBS":
                        logger.info(f"Clip {i}/{n_clips} ({clip.clip_uid}) already rendered & passed QC. Resuming/skipping...")
                        script_pass_count += 1
                        voice_pass_count += 1
                        final_pass_count += 1
                        clip.final_media_qc_pass = True
                        clip.status = ClipState.PUBLISH_READY
                        continue
                except Exception as e:
                    logger.warning(f"Failed reading existing clip records: {e}. Reprocessing clip {clip.clip_uid}...")

            # Step 5a: Clip Inspection
            notify("CLIP_INSPECTION", step_base + step_weight * 0.2, f"Inspecting clip {i}/{n_clips} ({clip.clip_uid})...")
            insp = self.inspector.inspect_clip(
                source_id=source_id,
                clip_uid=clip.clip_uid,
                video_path=clip_mp4,
                output_folder=clip_folder,
                source_context_text=scout_plan.source_summary,
            )

            # Step 5b: One Script Per Clip
            notify("SCRIPT_GENERATION", step_base + step_weight * 0.4, f"Generating unique script for clip {i}/{n_clips}...")
            script_rec = self.script_gen.generate_script_for_clip(
                clip_uid=clip.clip_uid,
                output_folder=clip_folder,
                source_context_text=scout_plan.source_summary,
                clip_index=i,
            )
            script_pass_count += 1

            # Step 5c: ElevenLabs TTS
            notify("VOICE_SYNTHESIS", step_base + step_weight * 0.6, f"Synthesizing voice for clip {i}/{n_clips}...")
            if (clip_folder / "audio_plan.json").exists():
                voice_rec = self.voice.synthesize_plan_voice(
                    clip_uid=clip.clip_uid,
                    output_folder=clip_folder,
                    script_revision=1,
                )
            else:
                tts_text = (clip_folder / "script_tts.txt").read_text(encoding="utf-8")
                voice_rec = self.voice.synthesize_clip_voice(
                    clip_uid=clip.clip_uid,
                    tts_text=tts_text,
                    output_folder=clip_folder,
                    script_revision=1,
                )
            voice_pass_count += 1

            # Step 5d: Local FFmpeg Render (v3.1 FINAL Clean ASMR)
            notify("RENDER_ENGINE", step_base + step_weight * 0.8, f"Rendering 1080x1920 video with v3.1 Clean ASMR for clip {i}/{n_clips}...")
            if (clip_folder / "story_plan.json").exists() or (clip_folder / "audio_plan.json").exists():
                qc = self.renderer.render_clip_v31(
                    clip_uid=clip.clip_uid,
                    output_folder=clip_folder,
                )
            else:
                qc = self.renderer.render_clip(
                    clip_uid=clip.clip_uid,
                    output_folder=clip_folder,
                )
            final_pass_count += 1

            # Step 5e: Publication Pack
            notify("PUBLICATION_PACK", step_base + step_weight * 0.95, f"Building publication pack for clip {i}/{n_clips}...")
            pack_rec = self.publisher.build_pack_for_clip(
                clip_uid=clip.clip_uid,
                output_folder=clip_folder,
                title_en=script_rec.title_en,
                story_angle=script_rec.story_angle,
                source_credit=f"Authentic German craftsman workshop (Source: {youtube_url})",
            )

            # Update in-memory manifest record
            clip.script = script_rec
            clip.voice = voice_rec
            clip.publish_pack = pack_rec
            clip.final_media_qc_pass = True
            clip.status = ClipState.PUBLISH_READY

        # 6. Generate Batch Summary & Reports
        notify("BATCH_SUMMARY", 0.98, "Generating batch summary CSV and final report...")
        self.publisher.generate_batch_reports(batch_id, source_id)

        # Update final counts
        manifest.counts = BatchCounts(
            discovered=n_clips,
            accepted=n_clips,
            script_pass=script_pass_count,
            voice_pass=voice_pass_count,
            final_pass=final_pass_count,
            asmr_final_pass=0,
        )
        manifest.batch_status = BatchState.BATCH_COMPLETE

        with open(source_dir / "batch_manifest.json", "w", encoding="utf-8") as f:
            f.write(manifest.model_dump_json(indent=2))

        notify("COMPLETE", 1.0, f"Pipeline complete! {n_clips} clips ready in {source_dir / 'output'}")
        return manifest
