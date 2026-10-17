#!/usr/bin/env python3
"""Local Video Forge v2.12 — Reference Mix & Adaptive Captions Pipeline
- Enforces strict clip filter: Duration >= 65.0s strictly enforced.
- Subtitle v2.12: 54px Inter Bold on 1080w, 1-4 words/cue pause-aware, default 85% Y position.
- Optional caption_regions.json support for per-shot positioning and italics keyword emphasis.
- Audio v2.12: Removed old voice-vs-bed RMS clamp; workshop bed never ducked, 0 dB throughout.
- Transient retention check: P0 detection for short metal/hammer impacts.
- Post-encode MP4 bed test: verifies workshop bed survived AAC encoding under English voice.
- Mastering measurement: integrated LUFS and true peak compared to reference style.
- Hard-burns 54px ASS subtitles into final.mp4 and exports captions_en.srt + captions_en.ass.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

from config import Config
from pipeline import PipelineOrchestrator
from opus_transcript_first_v2_8 import (
    from_opus_project_api,
    map_project_to_clip,
    MapPiece,
    to_srt,
    Segment,
    validate,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("run_v212")

YOUTUBE_URL = "https://www.youtube.com/watch?v=vL5MrypSvpE"
OPUS_PROJECT_ID = "P31016084uMa"
SOURCE_ID = "source_knife_v212_ref_audio"
INPUT_FOLDER = Path("/Volumes/KINGSTON/Reup Từ Đức/Opusclip/1")
PREV_SOURCE_ID = "source_knife_v211_asmr_sub_fix"
MIN_DURATION_SEC = 65.0

def probe_duration(path: Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(res.stdout.strip())

def build_srt_blocks(mapped_words: list[Segment], max_words: int = 6, max_gap: float = 1.0) -> list[Segment]:
    blocks: list[Segment] = []
    cur: list[Segment] = []
    for w in mapped_words:
        if not cur:
            cur.append(w)
        else:
            gap = w.start - cur[-1].end
            if len(cur) >= max_words or gap > max_gap:
                blocks.append(Segment(cur[0].start, cur[-1].end, " ".join(x.text for x in cur), "opus_clip_srt"))
                cur = [w]
            else:
                cur.append(w)
    if cur:
        blocks.append(Segment(cur[0].start, cur[-1].end, " ".join(x.text for x in cur), "opus_clip_srt"))
    return blocks

def main():
    logger.info("=" * 70)
    logger.info("LOCAL VIDEO FORGE v2.12 — REFERENCE MIX & ADAPTIVE CAPTIONS PIPELINE")
    logger.info("=" * 70)

    # 1. Fetch project transcripts and exportable clips info from OpusClip API
    key = Config.OPUSCLIP_API_KEY
    headers = {"Authorization": f"Bearer {key}", "User-Agent": "Mozilla/5.0"}

    logger.info(f"Fetching source transcript for project {OPUS_PROJECT_ID} from OpusClip API...")
    url_transcripts = f"https://api.opus.pro/api/transcripts?q=findByProjectId&projectId={OPUS_PROJECT_ID}"
    req_t = urllib.request.Request(url_transcripts, headers=headers)
    with urllib.request.urlopen(req_t) as resp:
        t_data = json.loads(resp.read().decode())
    source_words = from_opus_project_api(t_data)
    spoken_words = [w for w in source_words if not w.text.startswith("__")]
    logger.info(f"Loaded {len(spoken_words)} spoken German words from source project.")

    logger.info(f"Fetching clip metadata for project {OPUS_PROJECT_ID}...")
    url_clips = f"https://api.opus.pro/api/exportable-clips?q=findByProjectId&projectId={OPUS_PROJECT_ID}"
    req_c = urllib.request.Request(url_clips, headers=headers)
    with urllib.request.urlopen(req_c) as resp:
        c_data = json.loads(resp.read().decode())
    opus_clips = c_data.get("data", [])
    logger.info(f"OpusClip project has {len(opus_clips)} total clips.")

    # 2. Filter input files: only keep clips with duration >= 65.0s (ignore macOS ._ files)
    candidate_files = [f for f in sorted(INPUT_FOLDER.glob("*.mp4")) if not f.name.startswith("._")]
    qualifying_clips = []
    logger.info(f"Scanning folder {INPUT_FOLDER} for clips >= {MIN_DURATION_SEC}s:")
    for f in candidate_files:
        dur = probe_duration(f)
        if dur >= MIN_DURATION_SEC:
            logger.info(f"  [KEEP] {dur:.2f}s | {f.name}")
            qualifying_clips.append((f, dur))
        else:
            logger.info(f"  [DISCARD < 65s] {dur:.2f}s | {f.name}")

    if not qualifying_clips:
        logger.error("No clips found with duration >= 65.0s!")
        return

    logger.info(f"Selected {len(qualifying_clips)} qualifying clips for processing.")

    # 3. Setup output directory & write render preferences v2.12
    source_dir = Config.DATA_DIR / "sources" / SOURCE_ID
    source_dir.mkdir(parents=True, exist_ok=True)
    out_root = source_dir / "output"
    out_root.mkdir(parents=True, exist_ok=True)

    prefs = {
        "subtitle_anchor_pct": 85.0,
        "subtitle_font_width_ratio": 0.05,
        "max_words_per_caption": 4,
        "max_characters_per_caption": 28,
        "measure_mastering": True,
    }
    (out_root / "render_preferences.json").write_text(json.dumps(prefs, indent=2), encoding="utf-8")
    (source_dir / "render_preferences.json").write_text(json.dumps(prefs, indent=2), encoding="utf-8")
    logger.info(f"Wrote v2.12 render_preferences.json to {out_root / 'render_preferences.json'}")

    prev_out_root = Config.DATA_DIR / "sources" / PREV_SOURCE_ID / "output"

    prepared_clip_paths = []
    for idx, (clip_path, dur) in enumerate(qualifying_clips, start=1):
        out_folder = out_root / f"clip_{idx:03d}_craft"
        out_folder.mkdir(parents=True, exist_ok=True)
        transcript_dir = out_folder / "transcript"
        transcript_dir.mkdir(parents=True, exist_ok=True)

        # Match with Opus clip timeRanges
        matched_ranges = None
        for oc in opus_clips:
            oc_dur = (oc.get("durationMs") or 0) / 1000.0
            if abs(oc_dur - dur) <= 1.0:
                matched_ranges = oc.get("timeRanges")
                logger.info(f"Clip {idx} ({clip_path.name}) matches Opus clip: {oc.get('title')} (range: {matched_ranges})")
                break

        if matched_ranges and len(matched_ranges) > 0:
            s_in = matched_ranges[0][0] / 1000.0
            s_out = matched_ranges[0][1] / 1000.0
            mapped = map_project_to_clip(spoken_words, [MapPiece(s_in, s_out, 0.0, dur)], dur)
            blocks = build_srt_blocks(mapped)
            validate(blocks, dur)
            srt_str = to_srt(blocks)
            (transcript_dir / "opus_clip.srt").write_text(srt_str, encoding="utf-8")
            (out_folder / "opus_clip.srt").write_text(srt_str, encoding="utf-8")
            logger.info(f"Wrote exact Opus SRT ({len(blocks)} blocks) to {transcript_dir / 'opus_clip.srt'}")

        # Seed pre-synthesized TTS audio and script from previous run if available
        prev_folder = prev_out_root / f"clip_{idx:03d}_craft"
        if prev_folder.exists():
            prev_tts_dir = prev_folder / "audio" / "tts"
            target_tts_dir = out_folder / "audio" / "tts"
            if prev_tts_dir.exists():
                target_tts_dir.mkdir(parents=True, exist_ok=True)
                for f in prev_tts_dir.iterdir():
                    if f.is_file() and not f.name.startswith("._"):
                        shutil.copy2(f, target_tts_dir / f.name)
                logger.info(f"Seeded existing TTS audio & alignments from {prev_tts_dir}")

            for meta_file in ["script_en.md", "script_tts.txt", "story_angle.md", "title.txt"]:
                src_f = prev_folder / meta_file
                if src_f.exists():
                    shutil.copy2(src_f, out_folder / meta_file)

        prepared_clip_paths.append(clip_path)

    # 4. Execute v2.12 Pipeline
    orchestrator = PipelineOrchestrator()
    manifest = orchestrator.run_full_pipeline(
        youtube_url=YOUTUBE_URL,
        source_id=SOURCE_ID,
        local_srt_path=None,
        local_clip_paths=prepared_clip_paths,
        opus_project_id=None,
        rights_status="VERIFIED",
        max_spend_usd=10.0,
    )

    logger.info("=" * 70)
    logger.info("v2.12 PIPELINE EXECUTION FINISHED")
    logger.info(f"Batch Status: {manifest.batch_status}")
    logger.info(f"Total Accepted: {manifest.counts.accepted}")
    logger.info(f"Final QC Pass: {manifest.counts.final_pass}")
    for idx, c in enumerate(manifest.discovered_clips, start=1):
        c_folder = source_dir / c.folder
        final_mp4 = c_folder / "final.mp4"
        srt_en = c_folder / "captions_en.srt"
        ass_en = c_folder / "captions_en.ass"
        bed_wav = c_folder / "audio" / "workshop_bed_always_on.wav"
        voice_wav = c_folder / "audio" / "english_voice_only.wav"
        mix_wav = c_folder / "audio" / "english_mix.wav"
        logger.info(f"Clip {idx}: {final_mp4.name} (exists={final_mp4.exists()}, size={final_mp4.stat().st_size if final_mp4.exists() else 0} bytes)")
        logger.info(f"         EN Subtitles: {srt_en.name} (exists={srt_en.exists()}), {ass_en.name} (exists={ass_en.exists()})")
        logger.info(f"         Audio stems: {bed_wav.name} (exists={bed_wav.exists()}), {voice_wav.name} (exists={voice_wav.exists()}), {mix_wav.name} (exists={mix_wav.exists()})")

        # Capture a verification screenshot at 5.0s
        screenshot_path = c_folder / "screenshot_v212_5s.png"
        cmd_ss = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", "5.0", "-i", str(final_mp4),
            "-vframes", "1", "-q:v", "2",
            str(screenshot_path)
        ]
        try:
            subprocess.run(cmd_ss, check=True)
            logger.info(f"         Screenshot saved: {screenshot_path}")
        except Exception as e:
            logger.warning(f"Could not take screenshot for clip {idx}: {e}")

    logger.info("=" * 70)

if __name__ == "__main__":
    main()
