# CHANGELOG v3.3 — Universal Source FIX

- Remove Germany-specific source schema and German-only speech-QC gates.
- Add `SourceContext` with separate language evidence vs reviewed documentary country evidence; unverified country must be null.
- `source_speech_status`, `source_speech[]` with language, and `source_voice_absent` for all source speech.
- Add rule-based country/demonym/city claim guard for narrator/scripts/descriptions; manual fact review still mandatory.
- Add ASR language result normalizer (no embedded ASR API) and prompts for vision/source analysis and original en-US storytelling.
- Add safe v3.2 migration with backup + full reset of audio approval.
- Change renderer source QC report fields and package validator; retain no-duck ASMR and visual-only Cinematic ASMR.
- Add Korean/Japanese/no-origin and migration offline integration tests.
