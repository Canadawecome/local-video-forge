#!/usr/bin/env python3
"""Local Video Forge v2.10 — ASMR ALWAYS ON & 85% Y-Position Subtitle Pipeline
- Filters clips: Duration >= 65.0s strictly enforced. Discards all clips < 65s.
- Ingests exact German transcript from OpusClip project P31016084uMa.
- Translates every German dialogue block to English (artisan craftsman persona).
- Eliminates German voice completely with approved speech-free residual.
- ASMR Always On: Permanent workshop bed remains alive under English speech; zero German voice leak.
- Subtitle 85% Y-position: Compact ASS subtitles at 85% height (~35px, 2-3 words/cue).
- Hard-burns pixel-calibrated ASS captions into final.mp4 and exports captions_en.srt + captions_en.ass.
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
logger = logging.getLogger("run_v210")

YOUTUBE_URL = "https://www.youtube.com/watch?v=vL5MrypSvpE"
OPUS_PROJECT_ID = "P31016084uMa"
SOURCE_ID = "source_knife_v210_sub85"
INPUT_FOLDER = Path("/Volumes/KINGSTON/Reup Từ Đức/Opusclip/1")
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
    logger.info("LOCAL VIDEO FORGE v2.10 — ASMR ALWAYS ON & 85% Y SUBTITLES PIPELINE")
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

    # 3. Setup output directory & write render preferences
    source_dir = Config.DATA_DIR / "sources" / SOURCE_ID
    source_dir.mkdir(parents=True, exist_ok=True)
    out_root = source_dir / "output"
    out_root.mkdir(parents=True, exist_ok=True)

    prefs = {
        "subtitle_anchor_pct": 85.0,
        "subtitle_font_width_ratio": 0.032,
        "max_words_per_caption": 3,
        "max_characters_per_caption": 25,
        "max_voice_over_bed_db": 7.0,
    }
    (out_root / "render_preferences.json").write_text(json.dumps(prefs, indent=2), encoding="utf-8")
    logger.info(f"Wrote v2.10 render_preferences.json to {out_root / 'render_preferences.json'}")

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

        prepared_clip_paths.append(clip_path)

    # 4. Execute v2.10 Pipeline
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
    logger.info("v2.10 PIPELINE EXECUTION FINISHED")
    logger.info(f"Batch Status: {manifest.batch_status}")
    logger.info(f"Total Accepted: {manifest.counts.accepted}")
    logger.info(f"Final QC Pass: {manifest.counts.final_pass}")
    for idx, c in enumerate(manifest.discovered_clips, start=1):
        c_folder = source_dir / c.folder
        final_mp4 = c_folder / "final.mp4"
        srt_en = c_folder / "captions_en.srt"
        ass_en = c_folder / "captions_en.ass"
        bed_wav = c_folder / "audio" / "workshop_bed_always_on.wav"
        logger.info(f"Clip {idx}: {final_mp4.name} (exists={final_mp4.exists()}, size={final_mp4.stat().st_size if final_mp4.exists() else 0} bytes)")
        logger.info(f"         EN Subtitles: {srt_en.name} (exists={srt_en.exists()}), {ass_en.name} (exists={ass_en.exists()})")
        logger.info(f"         ASMR Bed: {bed_wav.name} (exists={bed_wav.exists()})")
    logger.info("=" * 70)

if __name__ == "__main__":
    main()
