# v3.5 — Strict Duration Gate (>65s) | 2026-10-17

- **Breaking policy**: FFprobe MP4 exported by OpusClip; only **duration >65.000 seconds** can proceed. `==65.000` rejected. No dependence on Opus metadata or reported GPT durations.
- **OpusClip job planner**: target 70–90 seconds (clipped to available source range); skip candidate ranges shorter than 70 rather than silently expanding beyond GPT evidence.
- **Early gate after import**: `ingest_opus_batch_v35.py` tags `DURATION_PASS_AWAIT_GPT_REVIEW` or `RECUT_REQUIRED_DURATION`, and emits `duration_gate_v35.json` (measured FFprobe seconds + SHA-256).
- **Model expense guard**: GPT Pass 2 entrypoint blocks short exports; other export QA/approval remains v3.4.
- **Before paid ElevenLabs**: `director_workflow_v35.py tts-handoff` checks fresh FFprobe + viral approval + content hashes, rejects missing or stale approval. External TTS client must call the same function; code cannot force arbitrary out-of-process API clients to obey.
- **Renderer guard**: `storytelling_render_v35.py` checks same policy. Legacy v3.4 renderer forwards to v3.5; v3.3 internal renderer also validates v3.5 gate, preventing direct accidental bypass in this release.
- **Retained**: GPT-first/Opus/review/85-point approval, rights guard, universal source, Clean ASMR, English ElevenLabs, subtitles 54px 85% 1–4 words, Cinematic ASMR video-only.
- **Limits**: audio cleanup and ElevenLabs API clients still require real integration and field testing; >65s does not guarantee platform reward eligibility.
