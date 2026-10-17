# Local Video Forge v3.5 — Offline Test Report

**Date:** 2026-10-17  
**Test command:** `python -m pytest -q tests/test_duration_gate_v35.py`  
**Result:** `15 passed` (offline; no paid API calls).

## Verified

- Strict logic: `65.0000000s` fails; `65.0000001s` passes in pure comparison; NaN and Inf fail.
- Real FFprobe MP4 fixtures: 64.75s and 65.00s rejected, 65.25s and 70.00s accepted.
- Invalid MP4 fails closed.
- Opus job preparation forces `clipDurations` ≥70s and skips source windows shorter than 70s.
- 70s clip with mock evidence/rights/mapping + GPT scores can receive APPROVED; `tts_handoff()` returns permit.
- 65s clip cannot run v3.5 review, TTS handoff or render.
- A once-approved 70s clip replaced by 65s fails on the fresh FFprobe check.
- Replacing 70s clip with a *different* 65.25s clip fails SHA verification (`STALE_APPROVAL`).
- Batch import classifies short exports as `RECUT_REQUIRED_DURATION`; long as `DURATION_PASS_AWAIT_GPT_REVIEW`.
- Direct legacy renderer v3.3/v3.4 imports cannot bypass v3.5 gate for short MP4.
- GPT Pass 2 adapter rejects 65s before any OpenAI request.
- A 70s clip without GPT `viral_approval.json` cannot reach ElevenLabs handoff.

**Test caveats:** Mocked source evidence frames, source mapping, rights reviewed signals, model scores and local MP4 fixtures only. No OpenAI, OpusClip, ElevenLabs, SAM Audio or AudioShake live integrations were exercised, and audio separation quality was not validated with real workshops. All older suites based on allowing 16s clips are archived as historical in `legacy_tests/`; they are not v3.5 acceptance tests.
