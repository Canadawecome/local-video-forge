# Local Video Forge v3.6 — FINAL FULL STORY COVERAGE

**QUAN TRỌNG:** Vấn đề vừa sửa: trước đây `story_plan.json` chỉ có 1 đoạn 3s nhưng renderer vẫn có thể xuất video 70s. Bản này từ chối toàn bộ chuỗi đó ở ba điểm: script, ElevenLabs, render.

## Điểm khởi động cho coding agent

1. Đọc `SPEC_Local_Video_Forge_v3.6_FINAL_FULL_STORY.md` làm **SPEC duy nhất**.
2. Giữ các module v3.5 duyệt viral/rights/FFprobe >65s; dùng chúng trước script/TTS.
3. GPT writer: `full_story_writer_v36.py` (tự bố trí ~7-12 voice slots, retry có validation).
4. Script integrity: `story_coverage_v36.py` (word count, coverage, start/end gaps, SHA256 full script/TTS script).
5. ElevenLabs: `elevenlabs_full_story_v36.py` (mỗi slot một request with-timestamps khi `--execute`, check đủ N file).
6. Render: **chỉ** `storytelling_render_v36.py process --folder ...`; bản v3.5/v3.3 kế thừa trong ZIP cũng có gate mới chống gọi tắt.
7. Run `PYTHONPATH=.:tests pytest -q tests/test_full_story_v36.py tests/test_writer_retry_v36.py tests/test_duration_gate_v35.py`.
8. Run smoke: `PYTHONPATH=.:tests python tests/smoke_render_v36.py` (offline, không API calls).

### Bước chạy an toàn

```bash
python -m pip install -r requirements.txt
python director_workflow_v35.py gate --clip-folder /work/clips/clip_001
python full_story_writer_v36.py generate --folder /work/clips/clip_001 --model YOUR_ACTUAL_MODEL
python full_story_writer_v36.py generate --folder /work/clips/clip_001 --model YOUR_ACTUAL_MODEL --execute
python director_workflow_v35.py tts-handoff --clip-folder /work/clips/clip_001
python elevenlabs_full_story_v36.py generate --folder /work/clips/clip_001 --execute
python storytelling_render_v36.py process --folder /work/clips/clip_001
```

**API keys bắt buộc khi chạy live:** `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`; OpusClip, nguồn quyền footage và speech separation cần nối/kiểm chứng trong deployment thực.

**Không quay lại** German-only assumptions, dub tiếng nguồn từng câu, mute/duck tiếng búa, phụ đề nằm ngoài 85%, hay cho qua clip dưới hoặc bằng 65 giây.

Kiểm thử offline: 31/31 unit/regression; FFmpeg smoke 70s/8 TTS segments/75.5% coverage đạt. **Chưa xác nhận APIs live và chất lượng nguồn thực.**
