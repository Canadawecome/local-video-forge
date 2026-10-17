# Offline Test Report — v3.3

Command: `python -m pytest -q tests`

**Result: 36/36 offline tests passed** on the current environment (2026-10-17).

Coverage: previous v3.1 audio/story, v3.2 visual-effects/regression, plus v3.3 language-country distinction, geo-claim guard, validated context, Korean-render FFmpeg synthetic test, old-QC rejection, migration review reset, batch isolation.

**Important:** This exercises schemas and local Python+FFmpeg on synthetic footage only. It does not make live calls to Whisper/OpenAI/OpusClip/ElevenLabs/SAM Audio/AudioShake and is not an audio separation accuracy benchmark.
