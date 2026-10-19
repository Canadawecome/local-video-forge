"""Speech Cleaner Module for Local Video Forge.
Detects host / creator voice in original craft/restoration footage using faster-whisper,
and removes / suppresses it with smooth cosine ramps to produce a clean, speech-free
workshop ASMR background bed.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

logger = logging.getLogger("speech_cleaner")


class HostSpeechCleaner:
    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self._whisper_model = None

    def _get_whisper(self):
        if self._whisper_model is None:
            from faster_whisper import WhisperModel
            logger.info(f"Loading faster-whisper ({self.model_size}) for host speech detection...")
            self._whisper_model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._whisper_model

    def detect_speech_segments(self, wav_path: Path) -> list[dict[str, Any]]:
        """Detects speech segments and timestamps in the audio using faster-whisper."""
        temp_16k = wav_path.parent / f"_temp_16k_{wav_path.stem}.wav"
        try:
            # Resample to 16kHz mono using FFmpeg
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(wav_path),
                "-ar", "16000", "-ac", "1",
                str(temp_16k),
            ]
            subprocess.run(cmd, check=True)
            data_16k, _ = sf.read(str(temp_16k))

            model = self._get_whisper()
            segments, info = model.transcribe(data_16k.astype(np.float32), vad_filter=False)

            detected: list[dict[str, Any]] = []
            for s in segments:
                text = s.text.strip()
                # Ignore empty or microscopic noise bursts (<0.3s)
                if text and (s.end - s.start >= 0.3):
                    detected.append({
                        "start": round(s.start, 3),
                        "end": round(s.end, 3),
                        "duration": round(s.end - s.start, 3),
                        "text": text,
                        "language": info.language,
                    })

            return detected
        except Exception as e:
            logger.warning(f"Host speech detection failed: {e}. Defaulting to no speech detected.")
            return []
        finally:
            if temp_16k.exists():
                try:
                    temp_16k.unlink()
                except OSError:
                    pass

    def remove_host_speech(
        self,
        input_wav: Path,
        output_wav: Path,
        fade_sec: float = 0.08,
        suppression_gain: float = 0.01,  # -40dB suppression
    ) -> list[dict[str, Any]]:
        """Detects and removes host speech from input_wav, writing clean ASMR to output_wav."""
        speech_segments = self.detect_speech_segments(input_wav)

        raw_audio, sr = sf.read(str(input_wav))
        residual = raw_audio.copy()
        n_samples = len(residual)

        if not speech_segments:
            logger.info("No host speech detected in audio. Workshop ASMR is already clean.")
            sf.write(str(output_wav), residual, sr, subtype="PCM_24")
            return []

        logger.info(f"Removing {len(speech_segments)} host speech segments from {input_wav.name}...")
        for s in speech_segments:
            st = s["start"]
            et = s["end"]
            i0 = max(0, int((st - fade_sec) * sr))
            i1 = max(0, int(st * sr))
            i2 = min(n_samples, int(et * sr))
            i3 = min(n_samples, int((et + fade_sec) * sr))

            # Apply smooth raised cosine ramp-down
            if i1 > i0:
                ramp = suppression_gain + (1.0 - suppression_gain) * 0.5 * (1 + np.cos(np.linspace(0, np.pi, i1 - i0, dtype=np.float32)))
                residual[i0:i1] *= (ramp[:, None] if residual.ndim > 1 else ramp)
            # Suppress speech region to near-zero
            if i2 > i1:
                residual[i1:i2] *= suppression_gain
            # Apply smooth raised cosine ramp-up
            if i3 > i2:
                ramp = suppression_gain + (1.0 - suppression_gain) * 0.5 * (1 - np.cos(np.linspace(0, np.pi, i3 - i2, dtype=np.float32)))
                residual[i2:i3] *= (ramp[:, None] if residual.ndim > 1 else ramp)

        sf.write(str(output_wav), residual, sr, subtype="PCM_24")
        logger.info(f"Wrote clean speech-free ASMR bed to {output_wav}")

        # Save inspection report
        report_path = output_wav.parent / "detected_speech.json"
        report_path.write_text(json.dumps(speech_segments, indent=2, ensure_ascii=False), encoding="utf-8")
        return speech_segments
