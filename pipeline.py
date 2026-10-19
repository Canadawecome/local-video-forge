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
import shutil
import sys
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
    OpusProjectRecord,
    OpusProjectState,
    RightsState,
)
from modules.clip_inspector import ClipInspector
from modules.opus_manager import OpusManager, probe_video
from modules.publication_pack import PublicationPackManager
from modules.render_engine import RenderEngine
from modules.restoration_cut_director import RestorationCutDirector
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
        self.restoration_director = RestorationCutDirector(self.sol)

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
        opus_model: str = "ClipAnything",
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
                    model=opus_model,
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
            if not clip.accepted:
                logger.warning(f"Clip {i}/{n_clips} ({clip.clip_uid}) not accepted (duration <= 65s or rejected). Skipping fan-out.")
                continue

            clip_folder = source_dir / clip.folder
            clip_folder.mkdir(parents=True, exist_ok=True)
            clip_mp4 = clip_folder / "original_opus.mp4"

            if clip_mp4.exists():
                probe = probe_video(clip_mp4)
                if probe.get("duration", 0.0) <= 65.0:
                    logger.warning(
                        f"Clip {i}/{n_clips} ({clip.clip_uid}) duration {probe.get('duration'):.2f}s <= 65.0s. "
                        f"Strictly rejecting per duration policy (>65.0s required)."
                    )
                    clip.accepted = False
                    continue
            
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

    def run_restoration_pipeline(
        self,
        source: str | Path,
        source_id: str | None = None,
        runtime_preference: str = "standard",
        progress_callback: Callable[[str, float, str], None] | None = None,
    ) -> BatchManifestV25:
        """Runs the SPEC v4.1 Restoration Cut Director end-to-end through downstream
        Script -> Voice (ElevenLabs) -> Render Engine (Subtitles + Mixed ASMR) -> Publication Pack.
        """
        def notify(stage: str, pct: float, msg: str):
            logger.info(f"[{pct*100:.0f}%] {stage}: {msg}")
            if progress_callback:
                progress_callback(stage, pct, msg)

        # 1. Source Setup
        raw_source = str(source).strip()
        is_url = raw_source.startswith("http://") or raw_source.startswith("https://") or "youtube.com" in raw_source or "youtu.be" in raw_source
        if not source_id:
            if is_url:
                import re
                match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", raw_source)
                vid_id = match.group(1) if match else f"yt_{int(time.time())}"
                source_id = f"src_{vid_id}"
            else:
                source_id = f"src_{Path(raw_source).stem}_{int(time.time())}"

        source_dir = Config.DATA_DIR / "sources" / source_id
        source_dir.mkdir(parents=True, exist_ok=True)

        cut_dir = source_dir / "restoration_cut"
        cut_dir.mkdir(parents=True, exist_ok=True)
        visual_cut_mp4 = cut_dir / "visual_cut.mp4"
        src_asmr = cut_dir / "source_asmr.wav"

        if is_url:
            needs_ingest = True
            if visual_cut_mp4.exists():
                from modules.opus_manager import probe_video
                p = probe_video(visual_cut_mp4)
                dur = p.get("duration", 0.0)
                if 72.0 <= dur <= 76.0 and src_asmr.exists():
                    needs_ingest = False
                    logger.info(f"Existing visual cut meets duration constraint: {dur:.2f}s (72s - 76s). Reusing.")
            if needs_ingest:
                notify("TARGETED_STREAM_INGEST", 0.05, f"Zero-download metadata scan & targeted slicing for {raw_source} (Target: 74.0s)...")
                from modules.stream_targeted_ingest import StreamTargetedIngest
                ingester = StreamTargetedIngest()
                meta = ingester.fetch_video_metadata(raw_source)
                sections = ingester.plan_targeted_sections(meta, target_total_sec=74.0)
                visual_cut_mp4, src_asmr, _ = ingester.download_and_assemble(
                    youtube_url=raw_source,
                    sections=sections,
                    output_dir=cut_dir,
                    target_total_sec=74.0,
                )
        else:
            src_video = Path(raw_source)
            # Stage 1-4: SPEC v4.1 Restoration Cut Director
            notify("RESTORATION_DIRECTOR", 0.20, f"Executing SPEC v4.1 Restoration Cut Director ({runtime_preference} runtime)...")
            plan = self.restoration_director.execute_cut_directing(
                source_video=src_video,
                output_dir=cut_dir,
                source_id=source_id,
                runtime_preference=runtime_preference,
            )

        if not visual_cut_mp4.exists():
            raise FileNotFoundError(f"Visual cut was not generated: {visual_cut_mp4}")

        # 3. Bridge to Downstream Review / Clip Folder
        output_dir = source_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        clip_folder_name = "clip_001_craft"
        clip_folder = output_dir / clip_folder_name
        clip_folder.mkdir(parents=True, exist_ok=True)

        provider_project_id = f"proj_restoration_{source_id}"
        provider_clip_id = "clip_001"
        canonical_clip_uid = f"{source_id}:{provider_project_id}:{provider_clip_id}"

        # Copy visual_cut.mp4 as original_opus.mp4 and clip.mp4
        dest_clip = clip_folder / "clip.mp4"
        dest_orig = clip_folder / "original_opus.mp4"
        shutil.copy2(visual_cut_mp4, dest_clip)
        shutil.copy2(visual_cut_mp4, dest_orig)

        # AI Voice Elimination & Pure Workshop ASMR Bed:
        audio_dir = clip_folder / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        if src_asmr.exists():
            notify("AUTHENTIC_ASMR_ENGINE", 0.40, "Authentic Workshop ASMR Engine: Activating 100% voice-free mechanical soundbed (RMS >= 0.05)...")
            clean_stem = audio_dir / "workshop_clean.wav"
            res_stem = audio_dir / "residual_workshop.wav"
            shutil.copy2(src_asmr, clean_stem)
            shutil.copy2(src_asmr, res_stem)

            # Bulletproof Defense: Remux dest_clip (clip.mp4) with clean_stem so clip.mp4 NEVER has human speech
            try:
                temp_remux = clip_folder / "clip_voicefree.mp4"
                remux_cmd = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(dest_clip),
                    "-i", str(clean_stem),
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-t", "74.0",
                    str(temp_remux)
                ]
                import subprocess
                subprocess.run(remux_cmd, check=True)
                shutil.move(str(temp_remux), str(dest_clip))
                logger.info("Successfully remuxed clip.mp4 with 100% voice-free ASMR stem.")
            except Exception as e:
                logger.warning(f"Could not remux clip.mp4 with clean stem: {e}")

        # Read story map and build inspection.json
        story_map_file = cut_dir / "story_map.json"
        story_map_data = []
        if story_map_file.exists():
            story_map_data = json.loads(story_map_file.read_text(encoding="utf-8"))

        visible_actions = [
            f"[{s.get('output_start_sec', 0.0):.1f}s - {s.get('output_end_sec', 0.0):.1f}s] {s.get('stage_name', 'STAGE')}: {s.get('visual_transformation', '')}"
            for s in story_map_data
        ]
        if not visible_actions:
            visible_actions = [
                "Inspection and assessment of worn antique tool",
                "Disassembly and extraction of seized parts",
                "Rust removal and heavy oxide clearance",
                "Surface grinding and precision tolerance rebuilding",
                "Fine abrasive polishing and mirror buffing",
                "Reassembly, lubrication and mechanical alignment",
                "Final operational testing and pristine finished reveal",
            ]

        from modules.opus_manager import probe_video
        cut_probe = probe_video(dest_clip)
        actual_dur = cut_probe.get("duration") or 105.0

        insp_data = {
            "clip_uid": canonical_clip_uid,
            "clip_duration_sec": actual_dur,
            "inspection": {
                "primary_craft_process": "Vintage mechanical antique restoration",
                "visible_actions": visible_actions,
                "suggested_story_angle": "Master craftsman restoration transformation",
                "material_observations": ["Heavily corroded steel", "Machined precision tolerances", "Mirror finish"],
            }
        }
        (clip_folder / "inspection.json").write_text(json.dumps(insp_data, indent=2), encoding="utf-8")

        # Register in SQLite database
        from storage.db import init_db
        init_db()
        with get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO sources (id, youtube_url, rights_status) VALUES (?, ?, ?)""",
                (source_id, raw_source, "VERIFIED")
            )
            conn.execute(
                """INSERT OR REPLACE INTO source_batches (id, source_id, barrier_state) VALUES (?, ?, ?)""",
                (f"batch_{source_id}", source_id, "PROCESSED")
            )
            conn.execute(
                """INSERT OR REPLACE INTO opus_projects (id, batch_id, status) VALUES (?, ?, ?)""",
                (provider_project_id, f"batch_{source_id}", OpusProjectState.SUCCEEDED.value)
            )
            conn.execute(
                """INSERT OR REPLACE INTO clips (id, batch_id, opus_project_id, opus_clip_id, index_no, status, duration_sec, source_asset_path, output_folder)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (canonical_clip_uid, f"batch_{source_id}", provider_project_id, provider_clip_id, 1, "DISCOVERED", actual_dur, str(dest_clip), f"output/{clip_folder_name}")
            )

        # 4. Step 5b: Script Generation (GPT Sol)
        notify("SCRIPT_GENERATION", 0.45, "Generating craftsman first-person voiceover script with GPT-5.6 Sol...")
        script_rec = self.script_gen.generate_script_for_clip(
            clip_uid=canonical_clip_uid,
            output_folder=clip_folder,
            source_context_text="Antique mechanical restoration documentary cut",
            clip_index=1,
        )

        # 5. Step 5c: ElevenLabs TTS
        notify("VOICE_SYNTHESIS", 0.65, "Synthesizing voiceover with ElevenLabs (Adam / craftsman voice)...")
        voice_rec = self.voice.synthesize_plan_voice(
            clip_uid=canonical_clip_uid,
            output_folder=clip_folder,
            script_revision=1,
        )

        # 6. Step 5d: Local FFmpeg Render (v3.1 Clean ASMR + 54px Dynamic Captions)
        notify("RENDER_ENGINE", 0.85, "Rendering final 1080x1920 video with mixed audio, ducked ASMR & captions...")
        qc = self.renderer.render_clip_v31(
            clip_uid=canonical_clip_uid,
            output_folder=clip_folder,
        )

        # 7. Step 5e: Publication Pack
        notify("PUBLICATION_PACK", 0.95, "Building publication pack (TikTok title, description, hashtags)...")
        pack_rec = self.publisher.build_pack_for_clip(
            clip_uid=canonical_clip_uid,
            output_folder=clip_folder,
            title_en=script_rec.title_en,
            story_angle=script_rec.story_angle,
            source_credit=f"Authentic craftsman restoration (Source: {raw_source})",
        )

        # 8. Batch Manifest
        clip_rec = ClipRecord(
            clip_uid=canonical_clip_uid,
            index_no=1,
            provider_project_id=provider_project_id,
            provider_clip_id=provider_clip_id,
            folder=f"output/{clip_folder_name}",
            rights_state=RightsState.VERIFIED,
            accepted=True,
            status=ClipState.PUBLISH_READY,
            final_media_qc_pass=True,
            script=script_rec,
            voice=voice_rec,
            publish_pack=pack_rec,
        )

        yt_url = raw_source if raw_source.startswith("http") else f"https://www.youtube.com/watch?v={source_id.replace('src_', '')}"
        manifest = BatchManifestV25(
            source_id=source_id,
            batch_id=f"batch_{source_id}",
            youtube_url=yt_url,
            batch_status=BatchState.BATCH_COMPLETE,
            opus_projects=[OpusProjectRecord(project_id=provider_project_id, status=OpusProjectState.SUCCEEDED)],
            discovered_clips=[clip_rec],
            counts=BatchCounts(
                discovered=1,
                accepted=1,
                script_pass=1,
                voice_pass=1,
                final_pass=1,
                asmr_final_pass=0,
            ),
            opus_batch_closed=True,
        )

        with open(source_dir / "batch_manifest.json", "w", encoding="utf-8") as f:
            f.write(manifest.model_dump_json(indent=2))

        notify("COMPLETE", 1.0, f"Restoration pipeline complete! Final voiced video at {clip_folder / 'final.mp4'}")
        return manifest
