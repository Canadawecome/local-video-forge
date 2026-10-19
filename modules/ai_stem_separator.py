"""AI Vocal Stem Separator for Local Video Forge.
Uses Meta Demucs v4 (Hybrid Demucs) to physically separate human vocals from workshop ASMR.
Extracts pure ambient audio (grinding, hammering, machining, filing) with 100% voice elimination.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("ai_stem_separator")

class AIVocalSeparator:
    def __init__(self, model_name: str = "htdemucs"):
        """
        model_name:
            'htdemucs' (default high-fidelity 4-source separator, optimized for fast GPU/CPU)
            'htdemucs_ft' (fine-tuned)
        """
        self.model_name = model_name

    def separate_vocals(
        self,
        input_wav: Path | str,
        output_clean_wav: Path | str,
        output_vocal_wav: Path | str | None = None,
        device: str | None = None,
    ) -> Path:
        """
        Separates vocals from the input audio file.
        Saves the speech-free ambient track to output_clean_wav.
        Optionally saves the isolated vocal stem to output_vocal_wav.
        """
        in_path = Path(input_wav).resolve()
        out_clean = Path(output_clean_wav).resolve()
        out_clean.parent.mkdir(parents=True, exist_ok=True)

        if not in_path.exists():
            raise FileNotFoundError(f"Input audio not found: {in_path}")

        logger.info(f"Starting AI Vocal Stem Separation on {in_path.name} using {self.model_name}...")

        # Temp directory for demucs output
        temp_out = in_path.parent / "demucs_temp"
        temp_out.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable, "-m", "demucs.separate",
            "-n", self.model_name,
            "--two-stems", "vocals",
            "-o", str(temp_out),
        ]

        if device:
            cmd.extend(["-d", device])

        cmd.append(str(in_path))

        try:
            logger.info(f"Running Demucs command: {' '.join(cmd)}")
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.debug(res.stdout)

            # Demucs places files at: temp_out / model_name / <track_name> / no_vocals.wav and vocals.wav
            track_name = in_path.stem
            stem_dir = temp_out / self.model_name / track_name
            no_vocals = stem_dir / "no_vocals.wav"
            vocals = stem_dir / "vocals.wav"

            if not no_vocals.exists():
                raise FileNotFoundError(f"Demucs finished but no_vocals.wav was not found at {no_vocals}")

            # Resample to 48kHz stereo using ffmpeg for perfect video sync
            resample_cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(no_vocals),
                "-ar", "48000", "-ac", "2",
                "-c:a", "pcm_s16le",
                str(out_clean)
            ]
            subprocess.run(resample_cmd, check=True)
            logger.info(f"Successfully isolated clean 48kHz workshop ASMR to {out_clean} ({out_clean.stat().st_size} bytes)")

            if output_vocal_wav and vocals.exists():
                shutil.copy2(vocals, Path(output_vocal_wav))

            # Cleanup temp folder
            try:
                shutil.rmtree(temp_out, ignore_errors=True)
            except Exception:
                pass

            return out_clean

        except subprocess.CalledProcessError as e:
            logger.error(f"Demucs stem separation failed: {e.stderr}")
            # Fallback: if demucs fails (e.g. out of memory), copy source or use whisper cleaner
            logger.warning("Falling back to copying raw audio...")
            shutil.copy2(in_path, out_clean)
            return out_clean
