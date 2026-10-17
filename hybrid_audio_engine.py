#!/usr/bin/env python3
"""Local Video Forge v2.7: hybrid DE->EN dubbing + protected workshop ASMR.

Runnable audio/render patch. This is not a full OpusClip/OpenAI application.
Commands:
  process --folder CLIP_FOLDER     (clip.mp4 + audio_plan.json)
  batch   --root OUTPUT_BATCH_DIR  (each clip_* folder independent)
  transcribe --clip MP4 --out JSON (optional faster-whisper dependency)

Uses FFmpeg + NumPy + SoundFile. ElevenLabs TTS is optional and is called only
if a segment's audio file does not already exist.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any
import numpy as np
import soundfile as sf
from hybrid_audio_contracts_v2_7 import HybridClipPlan

SAMPLE_RATE = 48000


def run(cmd: list[str]) -> None:
    subprocess.run([str(i) for i in cmd], check=True, capture_output=True, text=True)


def media_duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(proc.stdout.strip())


def extract_audio(path: Path, out: Path) -> None:
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
         "-i", str(path), "-map", "0:a:0", "-ac", "2", "-ar", str(SAMPLE_RATE),
         "-c:a", "pcm_s16le", str(out)])


def read_audio(path: Path, workdir: Path) -> np.ndarray:
    out = workdir / (hashlib.sha256(str(path).encode()).hexdigest()[:16] + ".wav")
    extract_audio(path, out)
    x, rate = sf.read(out, dtype="float32", always_2d=True)
    if rate != SAMPLE_RATE or x.shape[1] != 2:
        raise RuntimeError("Unexpected decoded audio format")
    return x


def db_to_gain(db: float) -> float:
    return 10.0 ** (db / 20.0)


def faded_window(total_samples: int, start: float, end: float,
                 attack_ms: int, release_ms: int) -> np.ndarray:
    """A gain envelope of 0 outside interval, smooth 0->1 and 1->0 at edges.

    Attack/release also reduce clicks, and can overlap at very short intervals.
    """
    i0 = max(0, int(round(start * SAMPLE_RATE)))
    i1 = min(total_samples, int(round(end * SAMPLE_RATE)))
    env = np.zeros(total_samples, dtype=np.float32)
    n = i1 - i0
    if n <= 0:
        return env
    a = min(n // 2, max(1, int(attack_ms * SAMPLE_RATE / 1000)))
    r = min(n // 2, max(1, int(release_ms * SAMPLE_RATE / 1000)))
    env[i0:i1] = 1.0
    if a:
        env[i0:i0 + a] = np.linspace(0.0, 1.0, a, endpoint=True, dtype=np.float32)
    if r:
        env[i1-r:i1] = np.linspace(1.0, 0.0, r, endpoint=True, dtype=np.float32)
    return env


def load_plan(folder: Path) -> HybridClipPlan:
    return HybridClipPlan.model_validate_json((folder / "audio_plan.json").read_text(encoding="utf-8"))


def segment_tts_path(folder: Path, seg) -> Path:
    if seg.audio_path:
        p = Path(seg.audio_path)
        # Absolute asset paths are allowed for editor-controlled local jobs.
        return p if p.is_absolute() else folder / p
    signature = hashlib.sha256(
        json.dumps([seg.text_en, seg.kind, seg.speech_ids], ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]
    return folder / "audio" / "tts" / f"{seg.id}_{signature}.mp3"


def generate_elevenlabs_tts(text_en: str, output_path: Path, voice_id: str,
                            model_id: str) -> None:
    """Generate one per-segment voice file, along with alignment JSON.

    Never called if output_path exists. Missing API key does not silently fall
    back to another voice or model.
    """
    import requests
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY is missing and no existing audio file provided")
    response = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        json={"text": text_en, "model_id": model_id}, timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    blob = base64.b64decode(payload["audio_base64"], validate=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temp_path.write_bytes(blob)
    temp_path.replace(output_path)
    output_path.with_suffix(".alignment.json").write_text(
        json.dumps({"alignment": payload.get("alignment"),
                    "normalized_alignment": payload.get("normalized_alignment")},
                   ensure_ascii=False, indent=2), encoding="utf-8",
    )


def mix_audio(folder: Path, plan: HybridClipPlan, raw_audio: np.ndarray,
              stem: np.ndarray | None, voices: dict[str, np.ndarray]):
    n = raw_audio.shape[0]
    duration = n / SAMPLE_RATE
    plan.validate_duration(duration)
    opts = plan.settings
    german_amount = np.zeros(n, dtype=np.float32)
    for s in plan.source_german_speech:
        german_amount = np.maximum(german_amount,
            faded_window(n, s.start, s.end, opts.duck_attack_ms, opts.duck_release_ms))
    voice_mix = np.zeros_like(raw_audio, dtype=np.float32)
    commentary_amount = np.zeros(n, dtype=np.float32)
    placement = []
    for v in plan.voice_segments:
        voice = voices[v.id]
        requested_start = int(round(v.start * SAMPLE_RATE))
        window_samples = int(round((v.end - v.start) * SAMPLE_RATE))
        if voice.shape[0] > window_samples + int(opts.max_tts_overrun_sec * SAMPLE_RATE):
            raise ValueError(f"TTS {v.id} too long by {(voice.shape[0]-window_samples)/SAMPLE_RATE:.3f}s. Shorten/replan; do not truncate voice")
        if voice.shape[0] > window_samples:
            raise ValueError(f"TTS {v.id} exceeds its speech window. Replan before rendering")
        if requested_start + voice.shape[0] > n:
            raise ValueError(f"TTS {v.id} beyond media duration")
        voice = voice.copy()
        fade_n = min(int(0.015 * SAMPLE_RATE), voice.shape[0]//4)
        if fade_n:
            fade_in = np.linspace(0, 1, fade_n, dtype=np.float32)
            voice[:fade_n] *= fade_in[:, None]
            voice[-fade_n:] *= fade_in[::-1, None]
        voice_mix[requested_start:requested_start + voice.shape[0]] += voice * db_to_gain(opts.voice_gain_db)
        commentary_amount = np.maximum(commentary_amount,
            faded_window(n, v.start, v.start + voice.shape[0]/SAMPLE_RATE,
                         opts.duck_attack_ms, opts.duck_release_ms))
        placement.append({"segment_id": v.id, "kind": v.kind, "start": v.start,
                          "planned_end": v.end, "tts_duration": voice.shape[0]/SAMPLE_RATE})

    # The approved workshop-only stem is used only over German-speech windows.
    # Otherwise the original workshop track is retained as the authentic ASMR.
    if stem is not None:
        if stem.shape != raw_audio.shape:
            raise ValueError("Workshop stem length/channel count does not match original audio")
        background = raw_audio * (1.0 - german_amount[:, None]) + stem * german_amount[:, None]
        german_gain = np.ones(n, dtype=np.float32)
    else:
        background = raw_audio.copy()
        german_gain = 1.0 - german_amount * (1.0 - db_to_gain(opts.german_speech_duck_db))
    commentary_gain = 1.0 - commentary_amount * (1.0 - db_to_gain(opts.commentary_duck_db))
    background *= np.minimum(german_gain, commentary_gain)[:, None]
    output = background + voice_mix

    peak_before = float(np.max(np.abs(output))) if n else 0
    limit = db_to_gain(opts.peak_ceiling_dbfs)
    global_gain = min(1.0, limit / peak_before) if peak_before else 1.0
    # Don't silently crush the desired hammer ASMR via a drastic master gain.
    if 20 * math.log10(max(global_gain, 1e-8)) < -1.5:
        raise ValueError("Master peak reduction would lower workshop ASMR >1.5dB; reduce voice gain/replan and QC")
    output *= global_gain
    protected_duration = sum(max(0.0, v.end-v.start) for v in plan.protected_asmr)
    report = {
        "clip_uid": plan.clip_uid,
        "mode": plan.mode,
        "duration_sec": round(duration, 3),
        "german_speech_windows": len(plan.source_german_speech),
        "protected_asmr_windows": len(plan.protected_asmr),
        "protected_asmr_duration_sec_unmerged": round(protected_duration, 3),
        "protected_asmr_ratio_unmerged": round(protected_duration/max(duration, 0.01), 3),
        "asmr_below_preferred_30pct": protected_duration/max(duration, 0.01) < .30,
        "voice_segments": placement,
        "workshop_stem_used": stem is not None,
        "german_speech_attenuation_db": None if stem is not None else opts.german_speech_duck_db,
        "commentary_duck_db": opts.commentary_duck_db,
        "peak_before_scaling_dbfs": round(20 * math.log10(max(peak_before, 1e-8)), 2),
        "output_peak_dbfs_sample_estimate": round(20*math.log10(max(float(np.max(np.abs(output))),1e-8)),2),
        "global_peak_gain_db": round(20*math.log10(max(global_gain, 1e-8)),2),
        "needs_listening_qc": True,
        "warning": "-24 dB attenuates German speech; it cannot guarantee removal. Verify source/voice mix by listening.",
    }
    return output, report


def process_clip(folder: Path, *, skip_tts: bool = False, dry_run: bool = False) -> dict[str, Any]:
    folder = Path(folder)
    input_video = folder / "clip.mp4"
    if not input_video.exists():
        raise FileNotFoundError(input_video)
    plan = load_plan(folder)
    video_sec = media_duration(input_video)
    plan.validate_duration(video_sec)
    report: dict[str, Any] = {"clip_uid": plan.clip_uid, "duration_sec": video_sec,
                              "validated": True, "mode": plan.mode}
    if dry_run:
        return report
    with tempfile.TemporaryDirectory(prefix="lvf_hybrid_") as wd:
        temp_dir = Path(wd)
        raw = read_audio(input_video, temp_dir)
        stem = None
        if plan.approved_workshop_stem_path:
            sp = Path(plan.approved_workshop_stem_path)
            sp = sp if sp.is_absolute() else folder / sp
            stem = read_audio(sp, temp_dir)
        voices: dict[str, np.ndarray] = {}
        for seg in plan.voice_segments:
            p = segment_tts_path(folder, seg)
            if not p.is_file():
                if skip_tts:
                    raise FileNotFoundError(f"Missing TTS asset {p}")
                generate_elevenlabs_tts(seg.text_en, p, plan.voice_id, plan.tts_model_id)
            voices[seg.id] = read_audio(p, temp_dir)
        mixed, mix_report = mix_audio(folder, plan, raw, stem, voices)
        # Save the artifacts only after validation and successful complete mix.
        mix_dir = folder / "audio"
        mix_dir.mkdir(parents=True, exist_ok=True)
        mixed_path = mix_dir / "mixed_audio.wav"
        sf.write(mixed_path, mixed, SAMPLE_RATE, subtype="PCM_24")
        final_tmp = folder / "final.hybrid.partial.mp4"
        final = folder / "final.mp4"
        try:
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                 "-i", str(input_video), "-i", str(mixed_path),
                 "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                 "-c:a", "aac", "-b:a", "192k", "-ar", str(SAMPLE_RATE),
                 "-movflags", "+faststart", "-shortest", str(final_tmp)])
            final_tmp.replace(final)
        finally:
            final_tmp.unlink(missing_ok=True)
        report.update(mix_report)
        report["output_video"] = str(final)
        (folder / "audio_mix_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report


def batch(root: Path, *, skip_tts: bool = False, dry_run: bool = False) -> dict:
    root = Path(root)
    results = []
    for folder in sorted(root.iterdir()):
        if folder.is_dir() and (folder / "audio_plan.json").is_file():
            try:
                report = process_clip(folder, skip_tts=skip_tts, dry_run=dry_run)
                results.append({"folder": str(folder), "status": "PASS", "report": report})
            except Exception as e:
                results.append({"folder": str(folder), "status": "NEEDS_REVIEW", "error": str(e)})
    summary = {"total": len(results),
               "passed": sum(r["status"] == "PASS" for r in results),
               "needs_review": sum(r["status"] != "PASS" for r in results),
               "results": results}
    (root / "hybrid_batch_report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def transcribe_clip(path: Path, out: Path, model_name: str = "small") -> None:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("Install optional dependency: pip install faster-whisper") from e
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segs, info = model.transcribe(str(path), language="de", vad_filter=True)
    data = {"language": info.language,
            "segments": [{"start": s.start, "end": s.end,
                          "text_de": s.text, "avg_logprob": s.avg_logprob}
                         for s in segs],
            "note": "ASR is fallible; check against the source before dubbing."}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("process")
    p.add_argument("--folder", type=Path, required=True)
    p.add_argument("--skip-tts", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("batch")
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--skip-tts", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("transcribe")
    p.add_argument("--clip", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--model", default="small")
    args = parser.parse_args()
    try:
        if args.command == "process":
            result = process_clip(args.folder, skip_tts=args.skip_tts, dry_run=args.dry_run)
        elif args.command == "batch":
            result = batch(args.root, skip_tts=args.skip_tts, dry_run=args.dry_run)
        else:
            transcribe_clip(args.clip, args.out, args.model)
            result = {"transcribed": str(args.out)}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
