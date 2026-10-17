# Changelog — v3.2 CINEMATIC ASMR

## Added

- `SmartEffectPlan` strict JSON, preset `CINEMATIC_ASMR`.
- Fallback từ `protected_asmr` (không phán đoán khoảnh khắc chưa phân tích).
- Microzoom time-preserving 1.00→1.045→1.00, grading nhẹ bằng FFmpeg.
- Video-only effect asset + hashed manifest; fail-closed stale clips/plans.
- Renderer v3.2 dùng visual effect asset thay video gốc nhưng trộn audio gốc/stem sạch và ElevenLabs **độc lập**, không duck.
- 8 bài test effects mới, kiểm tra tích hợp, non-audio, reject config lỗi.

## Unchanged

- Mode `ENGLISH_STORYTELLING_WITH_CLEAN_ASMR`, source transcript chỉ làm fact evidence.
- Clean ASMR review gate, English TTS/story timing, caption 54px/Y85%, clip-level publish folders, clip failure isolation.

## Not implemented

- Hook recut, actual speed ramps, b-roll splice, before/after timeline, audio separator API, provider orchestration. Need a synchronized upstream EDL before offering them as automatic effects.
