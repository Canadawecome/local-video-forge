"""Batch Audio & Render Fixer for Videos 5 to 13.
Applies Meta Demucs v4 vocal stripping, 120Hz highpass filter, 320Hz notch filter,
remuxes clip.mp4, and renders final.mp4 with v3.1 dynamic sidechain ducking.
"""
import json
import logging
import shutil
import subprocess
import time
from pathlib import Path

from config import Config
from modules.ai_stem_separator import AIVocalSeparator
from storytelling_render_v31 import process

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fix_5_to_13")

VIDS = [
    "src_R0qk4E1hEMY",
    "src_kIWkSQmD_C0",
    "src_KrStsdNG5go",
    "src_XaBnH35eVXA",
    "src_bv9IQTOYl8Q",
    "src_8IewMXUzt7U",
    "src_ilpWj3fiWGs",
    "src_21py6ZDP9wQ",
    "src_zEIiZ8DlMm0",
]

def fix_video(source_id: str) -> bool:
    source_dir = Config.DATA_DIR / "sources" / source_id
    clip_folder = source_dir / "output" / "clip_001_craft"
    audio_dir = clip_folder / "audio"
    visual_cut = source_dir / "restoration_cut" / "visual_cut.mp4"
    
    if not visual_cut.exists():
        visual_cut = clip_folder / "original_opus.mp4"
    if not visual_cut.exists():
        logger.error(f"Cannot find visual cut or original clip for {source_id}")
        return False

    t0 = time.time()
    logger.info(f"\n{'='*70}\n[DEMUCS & CLEAN AUDIO] Processing {source_id}...\n{'='*70}")
    
    # 1. Demucs separation
    demucs_flag = audio_dir / "demucs_done.flag"
    clean_stem = audio_dir / "workshop_clean.wav"
    if not (demucs_flag.exists() and clean_stem.exists()):
        raw_audio = audio_dir / "raw_cut_audio.wav"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(visual_cut),
            "-vn", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
            "-t", "74.0",
            str(raw_audio)
        ], check=True)

        temp_demucs = audio_dir / "demucs_clean.wav"
        separator = AIVocalSeparator()
        separator.separate_vocals(raw_audio, temp_demucs, audio_dir / "isolated_creator_vocals.wav", device="cpu")

        # Apply 120Hz HPF + 320Hz notch + 4500Hz boost
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(temp_demucs),
            "-af", "highpass=f=120,equalizer=f=320:width_type=o:w=1.2:g=-6,equalizer=f=4500:width_type=o:w=1.2:g=3.5,volume=1.2",
            "-ar", "48000", "-ac", "2",
            "-c:a", "pcm_s16le",
            str(clean_stem)
        ], check=True)
        shutil.copy2(clean_stem, audio_dir / "residual_workshop.wav")
        demucs_flag.write_text("DEMUCS_SEPARATED_OK", encoding="utf-8")
        temp_demucs.unlink(missing_ok=True)
        logger.info(f"Demucs vocal separation complete for {source_id}")

    # 2. Remux clip.mp4
    temp_remux = clip_folder / "clip_voicefree.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(clip_folder / "clip.mp4"),
        "-i", str(clean_stem),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-t", "74.0",
        str(temp_remux)
    ], check=True)
    shutil.move(str(temp_remux), str(clip_folder / "clip.mp4"))

    # 3. Render final.mp4 with clean sidechain ducking v3.1
    qc = process(clip_folder)
    elapsed = time.time() - t0
    status = qc.get("status")
    logger.info(f"SUCCESS {source_id} in {elapsed:.1f}s | Status: {status}")
    return status == "RENDERED_WITH_APPROVED_AUDIO_AND_EN_SUBS"

def main():
    success = 0
    for idx, vid in enumerate(VIDS, 5):
        logger.info(f"[{idx}/{len(VIDS)+4}] Starting clean audio fix for {vid}")
        try:
            if fix_video(vid):
                success += 1
        except Exception as e:
            logger.error(f"Error on {vid}: {e}", exc_info=True)
    logger.info(f"\nAll done! Fixed {success}/{len(VIDS)} videos with Demucs + Clean ASMR.")

if __name__ == "__main__":
    main()
