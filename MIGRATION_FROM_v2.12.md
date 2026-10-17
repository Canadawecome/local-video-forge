# Migration from v2.12 to v3.0

1. Stop reading `audio_plan.json` / old `HybridClipPlan`. New per-clip input: `story_plan.json` parsed with `StorytellingPlan`.
2. Change `mode` from `HYBRID_SELECTIVE_DUB_ASMR_STORY` to `ORIGINAL_COMMENTARY_ASMR` on **newly generated** plans. Existing v2.12 plan cannot be mechanically translated: regenerate the English story without `speech_ids` or German sentence sync.
3. Replace `voice_segments` (mixed `dub`/`commentary`) with `narration_segments` (all independent English story). Preserve evidence refs and voice text as appropriate.
4. German transcript is source evidence only. Opus transcript/SRT → WhisperX fallback when missing; no obligatory translation of each German sentence.
5. Speech status must be CONFIRMED_PRESENT / CONFIRMED_ABSENT; UNKNOWN/UNCERTAIN blocks render.
6. For CONFIRMED_PRESENT provide a FULL-LENGTH clean workshop stem that does not include German speech. Store approved `audio/replacement_qc.json` with real source/stem hashes.
7. Default bed: full residual when German is present, raw checked audio only when absent. No per-German-window switching back to raw: could leak German.
8. Remove all whole-bed duck, ambience_gain=0.35, -24dB suppression, synchronization to German speech windows, and automatic global mix reductions that crush hammer transients.
9. Keep SRT and hard-burned English ASS from ElevenLabs character alignment; subtitles at 85% / Inter Bold / 54px on 1080 width.
10. Replace invocation `strict_english_render_v2_12.py` with `storytelling_render_v3.py` in orchestrator; migrate per-clip folders and tests. Do not run both renderers for the same batch.
11. After render, generate and review `description.txt`, `hashtags.txt` and `script_tts.txt`, then run `validate_publish_pack_v3.py`.
12. For full one-link automation build OpenAI/OpusClip/SAM/ElevenLabs API adapters and job queue; the included code handles offline fan-out/validation/render only.
