# GPT-first process — example: Korean Damascus knife video

1. Source: 18 minutes of authorized blade forging footage, country UNKNOWN unless verified.
2. FFmpeg extracts timecode-labelled frames every 3s; optionally ASR text/audio events.
3. GPT Pass 1 selects multiple action-rich source windows: forging hammer / grinder sparks / pattern reveal.
4. For each: Opus ClipAnything receives customPrompt and bounded original video range.
5. Export Opus MP4s; preserve Opus project/source timeRanges and user permissions.
6. GPT Pass 2 sees **frames from each export**, not Opus's claimed virality score. Grade 6 categories.
7. Validator: >=85 + hard gates -> APPROVED; 70-84 -> RECUT; below -> REJECTED; uncertain -> HOLD.
8. ONLY approved clips: create English narrative + speech-free workshop residual + ElevenLabs TTS + subtitles + Cinematic ASMR render.
9. Release QC after audio separation; don't publish if workshop sounds removed or original spoken Korean/German/Japanese persists.

No language-to-country inference. No claim of guaranteed TikTok virality. No claim of being original just because footage is recut.
