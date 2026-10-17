# TEST REPORT v3.4 — 2026-10-17

## Kết quả thực sự chạy trong lượt cập nhật này

- `python -m pytest -q tests/test_gpt_first_director_v34.py` → **14 passed** (offline FFmpeg fixtures).
- Các ca test kiểm tra Opus ClipAnything payload, source range, rights gate, frame evidence/timecode, review scores, mapping millisecond, không có approval không render, confidence thấp HOLD, 70–84 RECUT, stale hashes, 9:16 frame gate.
- `python -m pytest -q tests/test_universal_source_v33.py -k ...` → **4 passed** (baseline source-language/geo guard smoke tests).
- `python video_event_evidence_v34.py --video <synthetic_video_without_audio> --output <json>` → thực thi thành công; không báo nhầm events/ASMR trên video không có tiếng.
- Python syntax `py_compile`: các module mới chạy qua.

**Không tuyên bố toàn bộ test baseline v3.3 đã được chạy lại thành công trong lượt này**. Lệnh chạy toàn suite bị timeout môi trường sau khi đã hoàn thành một phần; test v3.4 riêng đã được chạy lại đến kết thúc. Test v3.3 cũ có báo cáo trong gói baseline, không thay cho rerun.

## Chưa kiểm chứng

- API thực OpenAI GPT image model (thiếu key/model ID tài khoản), endpoint OpusClip (thiếu token), Opus export polling/download, ElevenLabs live, SAM Audio / AudioShake, TikTok publishing.
- Khả năng dự đoán clip viral trên dữ liệu đăng thật (score chỉ là heuristic, không đo view).
- Audio separation tiếng nói trùng tiếng búa trên footage thật (cần nghe và so sánh waveform).
- Motion/ASMR recognition full video từ frame sampling không được bảo đảm.

## Lệnh test lại

```bash
python -m pytest -q tests/test_gpt_first_director_v34.py
python -m pytest -q tests
```
