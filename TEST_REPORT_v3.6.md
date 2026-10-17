# Offline Test Report — Local Video Forge v3.6

Run from package root:

```
PYTHONPATH=.:tests pytest -q tests/test_full_story_v36.py tests/test_writer_retry_v36.py tests/test_duration_gate_v35.py
```

Result: **31 passed**. Cases cover one-fragment reject, short 8-part script reject, early-ending narration, incomplete/mismatched source text, hash tamper, missing middle TTS, too-short TTS, mismatched alignment, ElevenLabs dry-run, legacy renderer/handoff bypass protection, GPT retry and no corrupted plan on failed model response, plus v3.5 actual FFprobe boundaries and approvals.

Separate real-FFmpeg offline smoke:

```
PYTHONPATH=.:tests python tests/smoke_render_v36.py
```

Result: `PASS_FULL_STORY_FINAL`, 70.0 seconds, 8 synthetic voice segments, 0.755 active-audio coverage ratio, workshop background continually mixed, captions in final MP4.

**Scope limitations:** Test media/audio are generated fixtures. OpenAI/OpusClip/ElevenLabs/SAM Audio live requests were **not** executed; verifying source separation quality and natural spoken timing requires a real end-to-end sample.
