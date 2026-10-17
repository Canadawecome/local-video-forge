# Migration v2.5 -> v2.6 (No Gemini)

- Replace global Gemini native-YouTube-video scout with metadata/subtitle text ingest + GPT-5.6 Sol text scout.
- Direct YouTube URL is sent to OpusClip, not OpenAI. Default omit `curationPref.range` without trusted timecoded evidence.
- After Opus returns all clip MP4s, local FFmpeg samples timestamped still images, faster-whisper reads German speech.
- Every clip gets its own GPT-5.6 Sol vision inspection + independent script (each output evidence scoped to its own clip), then individual ElevenLabs TTS and FFmpeg render.
- `N_discovered`, `N_accepted` and all existing batch contract logic remain unchanged.
- One output folder per clip with `final.mp4`, `script_en.md`, `script_tts.txt`, `captions`, `description.txt`, `hashtags.txt`, `publish_pack.json`, and QC.
- Added `SourceScoutPlanV26`, `ClipEvidenceBundleV26`, `SolRequestContentV26` and 13 offline tests. Existing 10 offline tests preserved (23 total).
- Real API behavior, Opus clean export and your OpenAI key's access to `gpt-5.6-sol` must be verified during Phase 0.
