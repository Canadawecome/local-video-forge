# v2.12 Changes

- Kept 54px Inter Bold EN subtitles with default 85% Y position; pause-aware 1–4 words/cue.
- Optional shot-specific Y and italics using `caption_regions.json`.
- Removed v2.11 per-speech automatic voice RMS clamp to bed RMS (legacy config accepted but ignored).
- Kept workshop bed never ducked, swapped only for QC-approved German speech-free residual in German windows.
- Added high-frequency transient preservation gate for hammer impacts missed by average RMS QC.
- Added MP4 post-encode workshop bed test during English voice.
- Added final LUFS/true-peak measurement (reference comparison only).
- Added synthetic regression tests and consolidated SPEC section 23.
