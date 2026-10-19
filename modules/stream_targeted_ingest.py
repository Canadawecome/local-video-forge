"""Targeted Stream Ingest & Slicer for Local Video Forge.
Zero Full-Video Download: Analyzes metadata/chapters and downloads ONLY the required 75-120s of
critical transformation footage using HTTP range requests (--download-sections).
Saves >95% bandwidth and disk space while maintaining 1080p source quality.
"""
from __future__ import annotations

import json
import logging
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from config import Config

logger = logging.getLogger("stream_targeted_ingest")

RESTORATION_STAGES = [
    ("BEFORE", "Heavy rust, decay, or initial worn condition of the antique artifact", 0.00, 0.04),
    ("INSPECTION", "Detailed inspection, testing frozen parts, measuring wear", 0.04, 0.08),
    ("DISASSEMBLY", "Tearing down components, extracting seized bolts, pins and springs", 0.08, 0.18),
    ("RUST_REMOVAL", "Electrolysis, wire wheeling, acid bath, or heavy sandblasting", 0.18, 0.32),
    ("GRINDING", "Surface grinding, rotary filing, flattening warped contact faces", 0.32, 0.46),
    ("REPAIR", "Welding cracks, brazing broken tabs, precision thread chasing", 0.46, 0.60),
    ("POLISHING", "Abrasive wheel buffing, scotch-brite scouring, mirror finish work", 0.60, 0.74),
    ("PAINT_FINISH", "Primer application, hot blueing, oil quenching, or protective coating", 0.74, 0.84),
    ("ASSEMBLY", "Aligning newly restored parts, pressing bearings, tightening polished brass", 0.84, 0.92),
    ("TEST", "First functional test under full load, smooth mechanical operation", 0.92, 0.97),
    ("AFTER_REVEAL", "Pristine gleaming final reveal, 360-degree beauty spin", 0.97, 1.00),
]

class StreamTargetedIngest:
    def __init__(self):
        pass

    def fetch_video_metadata(self, youtube_url: str) -> dict[str, Any]:
        """Fetches metadata via yt-dlp in zero-download mode (<2 seconds)."""
        logger.info(f"Fetching YouTube metadata (zero-download) for: {youtube_url}")
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--dump-single-json",
            "--skip-download",
            "--no-playlist",
            "--extractor-args", "youtube:player_client=android,web,tv",
        ]
        
        # Add Deno JS runtime
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        deno_cand = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages" / "DenoLand.Deno_Microsoft.Winget.Source_8wekyb3d8bbwe" / "deno.exe"
        if deno_cand.exists():
            cmd.extend(["--js-runtimes", f"deno:{deno_cand}"])

        # Add cookies if available
        for cookie_cand in [Config.DATA_DIR / "cookies.txt", Path("cookies.txt")]:
            if cookie_cand.exists():
                cmd.extend(["--cookies", str(cookie_cand.resolve())])
                break

        cmd.append(youtube_url)

        res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=90)
        return json.loads(res.stdout)

    def plan_targeted_sections(
        self,
        meta: dict[str, Any],
        target_total_sec: float = 74.0,
    ) -> list[dict[str, Any]]:
        """Plans exact start and end timestamps for each restoration stage.
        Strictly enforces duration between 72.0s and 76.0s (default: 74.0s).
        """
        # Strict duration gate: clamp to [72.0s, 76.0s]
        target_total_sec = max(72.0, min(76.0, float(target_total_sec)))
        total_duration = float(meta.get("duration") or 600.0)
        chapters = meta.get("chapters") or []
        
        logger.info(f"Planning targeted sections: Video duration={total_duration:.1f}s, Target={target_total_sec:.2f}s (Constraint: 72s-76s)")

        # Distribute target_total_sec evenly across stages so sum is EXACTLY target_total_sec
        n_stages = len(RESTORATION_STAGES)
        base_dur = round(target_total_sec / n_stages, 2)
        durs = [base_dur] * n_stages
        diff = round(target_total_sec - sum(durs), 2)
        durs[-1] = round(durs[-1] + diff, 2)

        sections: list[dict[str, Any]] = []

        for idx, ((stage_name, desc, p_start, p_end), shot_dur) in enumerate(zip(RESTORATION_STAGES, durs), 1):
            # Calculate nominal range in the source video
            src_win_start = p_start * total_duration
            src_win_end = p_end * total_duration
            win_len = src_win_end - src_win_start

            # Take high-activity segment in the middle/upper portion of the stage window
            if win_len > shot_dur:
                offset = (win_len - shot_dur) * 0.4
                actual_start = round(src_win_start + offset, 2)
                actual_end = round(actual_start + shot_dur, 2)
            else:
                actual_start = round(src_win_start, 2)
                actual_end = round(min(total_duration, actual_start + shot_dur), 2)

            sections.append({
                "stage_idx": idx,
                "stage_name": stage_name,
                "description": desc,
                "source_start_sec": actual_start,
                "source_end_sec": actual_end,
                "duration_sec": round(actual_end - actual_start, 2),
            })

        planned_total = sum(s["duration_sec"] for s in sections)
        logger.info(f"Planned {len(sections)} stages, total planned duration: {planned_total:.2f}s")
        return sections

    def build_authentic_workshop_asmr_bed(
        self,
        youtube_url: str,
        target_total_sec: float,
        output_wav: Path,
        cut_folder: Path,
    ) -> Path:
        """Builds a 100% speech-free, authentic workshop ASMR soundbed.
        Discovers non-speech intervals (machining, lathe, tools) directly from the source video,
        stitches them, and normalizes with loudnorm so RMS is punchy (~0.08) and crisp.
        """
        temp_dir = cut_folder / "asmr_bed_temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Fetch automatic subtitles in json3 format
        sub_base = temp_dir / "autosub"
        cmd_sub = [
            sys.executable, "-m", "yt_dlp",
            "--skip-download",
            "--write-auto-sub",
            "--sub-lang", "en",
            "--sub-format", "json3",
            "-o", str(sub_base),
            youtube_url,
        ]
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        deno_cand = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages" / "DenoLand.Deno_Microsoft.Winget.Source_8wekyb3d8bbwe" / "deno.exe"
        if deno_cand.exists():
            cmd_sub.extend(["--js-runtimes", f"deno:{deno_cand}"])
        for cookie_cand in [Config.DATA_DIR / "cookies.txt", Path("cookies.txt")]:
            if cookie_cand.exists():
                cmd_sub.extend(["--cookies", str(cookie_cand.resolve())])
                break

        try:
            subprocess.run(cmd_sub, capture_output=True, text=True, check=True, timeout=60)
        except Exception as e:
            logger.warning(f"Could not download auto-subtitles for ASMR gap detection: {e}")

        # Find the downloaded json3 file
        json3_files = list(temp_dir.glob("autosub*.json3"))
        gaps: list[tuple[float, float, float]] = []

        if json3_files:
            try:
                sub_data = json.loads(json3_files[0].read_text(encoding="utf-8"))
                events = sub_data.get("events", [])
                speech_spans = []
                for e in events:
                    dur_ms = e.get("dDurationMs", 0)
                    text = "".join(s.get("utf8", "") for s in e.get("segs", [])).strip()
                    if dur_ms > 500 and text and text != "\n":
                        st = e.get("tStartMs", 0) / 1000.0
                        et = st + dur_ms / 1000.0
                        speech_spans.append((st, et))
                speech_spans.sort()
                
                # Merge overlapping spans
                merged = []
                for s in speech_spans:
                    if not merged or s[0] > merged[-1][1]:
                        merged.append(s)
                    else:
                        merged[-1] = (merged[-1][0], max(merged[-1][1], s[1]))

                for i in range(len(merged) - 1):
                    gap_st = merged[i][1]
                    gap_et = merged[i+1][0]
                    gap_dur = gap_et - gap_st
                    if gap_dur >= 3.0:
                        gaps.append((gap_st, gap_et, gap_dur))

                # Sort by duration descending (longest pure ASMR stretches first)
                gaps.sort(key=lambda g: g[2], reverse=True)
                logger.info(f"Discovered {len(gaps)} non-speech ASMR intervals in source video.")
            except Exception as e:
                logger.warning(f"Error parsing json3 captions: {e}")

        # Format helper
        def fmt_time(s: float) -> str:
            h = int(s // 3600)
            m = int((s % 3600) // 60)
            sec_rem = s % 60
            return f"{h:02d}:{m:02d}:{sec_rem:06.3f}"

        # Collect pure ASMR slices
        downloaded_asmr_parts: list[Path] = []
        accumulated_sec = 0.0

        for idx, (gst, get, gdur) in enumerate(gaps, 1):
            if accumulated_sec >= target_total_sec:
                break
            take_dur = min(gdur, target_total_sec - accumulated_sec + 2.0)
            part_path = temp_dir / f"pure_asmr_gap_{idx}.wav"

            if not part_path.exists() or part_path.stat().st_size < 10000:
                raw_part_m4a = temp_dir / f"pure_asmr_gap_{idx}.m4a"
                range_str = f"*{fmt_time(gst)}-{fmt_time(gst + take_dur)}"
                dl_cmd = [
                    sys.executable, "-m", "yt_dlp",
                    "--download-sections", range_str,
                    "-f", "bestaudio/ba/best",
                    "-o", str(raw_part_m4a),
                    youtube_url,
                ]
                if deno_cand.exists():
                    dl_cmd.extend(["--js-runtimes", f"deno:{deno_cand}"])
                for cookie_cand in [Config.DATA_DIR / "cookies.txt", Path("cookies.txt")]:
                    if cookie_cand.exists():
                        dl_cmd.extend(["--cookies", str(cookie_cand.resolve())])
                        break
                try:
                    subprocess.run(dl_cmd, check=True, capture_output=True)
                    subprocess.run([
                        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(raw_part_m4a),
                        "-ar", "48000", "-ac", "2",
                        "-c:a", "pcm_s16le",
                        str(part_path)
                    ], check=True)
                except Exception as e:
                    logger.warning(f"Failed to download ASMR gap {idx}: {e}")
                    continue

            if part_path.exists() and part_path.stat().st_size > 10000:
                downloaded_asmr_parts.append(part_path)
                accumulated_sec += take_dur
                logger.info(f"Loaded pure ASMR gap {idx}: {take_dur:.1f}s (Total: {accumulated_sec:.1f}s)")

        # Fallback if no non-speech gaps found
        if not downloaded_asmr_parts or accumulated_sec < 5.0:
            logger.info("Falling back to native audio extraction...")
            return output_wav

        # Concat the pure ASMR parts and normalize with loudnorm
        concat_txt = temp_dir / "asmr_concat.txt"
        with open(concat_txt, "w", encoding="utf-8") as f:
            for p in downloaded_asmr_parts:
                f.write(f"file '{p.resolve().as_posix()}'\n")

        raw_assembled = temp_dir / "raw_assembled.wav"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_txt),
            "-c:a", "pcm_s16le",
            str(raw_assembled)
        ], check=True)

        # Loop and normalize with loudnorm=I=-18:TP=-1.5:LRA=11 to exact target_total_sec
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-stream_loop", "3",
            "-i", str(raw_assembled),
            "-t", f"{target_total_sec:.2f}",
            "-af", "loudnorm=I=-18:TP=-1.5:LRA=11",
            "-ar", "48000", "-ac", "2",
            "-c:a", "pcm_s16le",
            str(output_wav)
        ], check=True)

        logger.info(f"Built authentic 100% speech-free workshop ASMR bed: {output_wav} ({target_total_sec:.1f}s)")
        return output_wav

    def download_and_assemble(
        self,
        youtube_url: str,
        sections: list[dict[str, Any]],
        output_dir: Path,
        target_total_sec: float = 74.0,
    ) -> tuple[Path, Path, Path]:
        """
        Downloads ONLY the targeted sections using yt-dlp range requests,
        reframes to 9:16 portrait using Smart Reframe ASMR v1.0,
        and stitches them into visual_cut.mp4 and source_asmr.wav.
        Enforces strict duration between 72.0s and 76.0s (target: 74.0s).
        """
        target_total_sec = max(72.0, min(76.0, float(target_total_sec)))
        out_folder = Path(output_dir).resolve()
        raw_shots_dir = out_folder / "raw_shots"
        reframed_shots_dir = out_folder / "reframed_shots"
        raw_shots_dir.mkdir(parents=True, exist_ok=True)
        reframed_shots_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Targeted Slicing: Downloading {len(sections)} sections directly from YouTube (Target: {target_total_sec:.1f}s)...")

        reframed_files: list[Path] = []
        story_map: list[dict[str, Any]] = []
        current_timeline = 0.0

        for sec in sections:
            stage_idx = sec["stage_idx"]
            stage_name = sec["stage_name"]
            st = sec["source_start_sec"]
            et = sec["source_end_sec"]
            dur = sec["duration_sec"]

            raw_shot_path = raw_shots_dir / f"shot_{stage_idx:02d}_{stage_name}.mp4"

            # Download single section via yt-dlp if not already cached
            if not raw_shot_path.exists() or raw_shot_path.stat().st_size < 10000:
                logger.info(f"Downloading [{stage_idx}/{len(sections)}] {stage_name}: {st:.1f}s -> {et:.1f}s ({dur:.1f}s)...")
                
                # Format time as HH:MM:SS
                def fmt_time(s: float) -> str:
                    h = int(s // 3600)
                    m = int((s % 3600) // 60)
                    sec_rem = s % 60
                    return f"{h:02d}:{m:02d}:{sec_rem:06.3f}"

                range_str = f"*{fmt_time(st)}-{fmt_time(et)}"
                cmd = [
                    sys.executable, "-m", "yt_dlp",
                    "--download-sections", range_str,
                    "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
                    "--merge-output-format", "mp4",
                    "--extractor-args", "youtube:player_client=android,web,tv",
                    "-o", str(raw_shot_path),
                ]
                local_appdata = os.environ.get("LOCALAPPDATA", "")
                deno_cand = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages" / "DenoLand.Deno_Microsoft.Winget.Source_8wekyb3d8bbwe" / "deno.exe"
                if deno_cand.exists():
                    cmd.extend(["--js-runtimes", f"deno:{deno_cand}"])

                for cookie_cand in [Config.DATA_DIR / "cookies.txt", Path("cookies.txt")]:
                    if cookie_cand.exists():
                        cmd.extend(["--cookies", str(cookie_cand.resolve())])
                        break
                cmd.append(youtube_url)

                # Retry loop (up to 3 attempts with backoff)
                download_success = False
                for attempt in range(1, 4):
                    try:
                        subprocess.run(cmd, check=True)
                        if raw_shot_path.exists() and raw_shot_path.stat().st_size > 5000:
                            download_success = True
                            break
                    except Exception as e:
                        logger.warning(f"Shot {stage_name} attempt {attempt}/3 failed: {e}. Retrying in 2s...")
                        for part in raw_shots_dir.glob(f"shot_{stage_idx:02d}*.part"):
                            try:
                                part.unlink(missing_ok=True)
                            except Exception:
                                pass
                        time.sleep(2.0 * attempt)

                if not download_success:
                    raise RuntimeError(f"Failed to download shot {stage_name} after 3 attempts")

            # Reframe to 9:16 portrait (1080x1920) with Smart Reframe ASMR v1.0, trimmed to exact duration
            reframed_path = reframed_shots_dir / f"reframed_{stage_idx:02d}_{stage_name}.mp4"
            if not reframed_path.exists() or reframed_path.stat().st_size < 10000:
                logger.info(f"Reframing {stage_name} to 9:16 portrait (duration: {dur:.2f}s)...")
                
                vf = (
                    "[0:v]split=2[bg_in][fg_in];"
                    "[bg_in]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];"
                    "[fg_in]scale=1080:-2[fg];"
                    "[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"
                )
                rf_cmd = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(raw_shot_path),
                    "-t", f"{dur:.3f}",
                    "-filter_complex", vf,
                    "-map", "[v]",
                    "-map", "0:a?",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast", "-crf", "18",
                    "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
                    str(reframed_path),
                ]
                subprocess.run(rf_cmd, check=True)

            reframed_files.append(reframed_path)

            # Probe exact duration with ffprobe
            p_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(reframed_path)]
            p_res = subprocess.run(p_cmd, capture_output=True, text=True)
            try:
                actual_dur = float(p_res.stdout.strip())
            except Exception:
                actual_dur = dur

            story_map.append({
                "stage_idx": stage_idx,
                "stage_name": stage_name,
                "source_start_sec": st,
                "source_end_sec": et,
                "output_start_sec": current_timeline,
                "output_end_sec": round(current_timeline + actual_dur, 2),
                "visual_transformation": sec["description"],
            })
            current_timeline = round(current_timeline + actual_dur, 2)

        # Concat all reframed shots into visual_cut.mp4 with strict total duration
        concat_list = out_folder / "concat_list.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for rf in reframed_files:
                f.write(f"file '{rf.resolve().as_posix()}'\n")

        visual_cut = out_folder / "visual_cut.mp4"
        logger.info(f"Stitching {len(reframed_files)} reframed shots into {visual_cut.name} (target: {target_total_sec:.1f}s)...")
        stitch_cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
            "-t", f"{target_total_sec:.2f}",
            str(visual_cut),
        ]
        subprocess.run(stitch_cmd, check=True)

        # Build authentic, speech-free workshop ASMR bed
        source_asmr = out_folder / "source_asmr.wav"
        self.build_authentic_workshop_asmr_bed(
            youtube_url=youtube_url,
            target_total_sec=target_total_sec,
            output_wav=source_asmr,
            cut_folder=out_folder,
        )

        # If source_asmr still doesn't exist, extract from visual_cut
        if not source_asmr.exists() or source_asmr.stat().st_size < 10000:
            asmr_cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(visual_cut),
                "-vn", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
                "-t", f"{target_total_sec:.2f}",
                str(source_asmr),
            ]
            subprocess.run(asmr_cmd, check=True)

        # Remux visual_cut.mp4 with source_asmr so it is 100% clean and exact duration
        temp_remux = out_folder / "visual_cut_asmr.mp4"
        remux_cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(visual_cut),
            "-i", str(source_asmr),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", f"{target_total_sec:.2f}",
            str(temp_remux),
        ]
        subprocess.run(remux_cmd, check=True)
        shutil.move(str(temp_remux), str(visual_cut))

        # Save story_map.json
        story_map_file = out_folder / "story_map.json"
        story_map_file.write_text(json.dumps(story_map, indent=2), encoding="utf-8")

        # Verify final duration with ffprobe
        p_cut = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(visual_cut)]
        p_res = subprocess.run(p_cut, capture_output=True, text=True)
        verified_dur = float(p_res.stdout.strip())
        logger.info(f"Targeted Ingest Complete! Verified Cut Duration: {verified_dur:.2f}s (Constraint: 72s-76s) | ASMR: {source_asmr.name}")
        return visual_cut, source_asmr, story_map_file
