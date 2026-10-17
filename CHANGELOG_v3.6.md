# CHANGELOG v3.6 FINAL — FULL STORY COVERAGE

**Fixed:** video 70-90s được GPT viết 1 câu, ElevenLabs chỉ tạo 1 voice ngắn nhưng renderer vẫn xuất video dài.

- Added `full_story_writer_v36.py`: 7-12 distributed narration slots with fact/evidence grounding, GPT retries, no partial plan publish.
- Added `story_coverage_v36.py`: >=5 segments, min word count relative duration, timeline coverage start/middle/end, stable hashes for full script and TTS script.
- Added `elevenlabs_full_story_v36.py`: paid TTS only after story gate; each segment has audio + alignment, all required.
- Added `final_story_qc_v36.py`: final duration, segment-count, captions and nonzero per-segment voice-track QC.
- Added `storytelling_render_v36.py` canonical entrypoint.
- Patched `director_workflow_v35.tts_handoff` to require sealed v3.6 full story.
- Patched `storytelling_render_v35.py` and legacy core `storytelling_render_v33.py` to prevent bypass.
- Added test coverage, GPT retry fixtures, and optional real FFmpeg render smoke with synthetic media.
- Preserves Universal Source, strict >65s, GPT-first director/postcut approval, Clean ASMR always on, ElevenLabs voice choice, Cinematic ASMR visuals and 85%-height English subtitles.

**Not claimed:** live API integration on user video, guarantee of all source speech removed, rights clearance of 3rd-party content, predictive virality.
