# Kết quả kiểm thử v3.2

- Lệnh: `PYTHONPATH=. python -m pytest -q tests`
- Kết quả: **20 passed** (chạy offline trong môi trường tác giả).
- 8 bài mới: giới hạn preset/zoom, reject tốc độ và duck sai contract, overlap, tự tạo từ protected ASMR, video-only + timebase, hash stale, FFmpeg final MP4 voice/sub/ASMR, batch failure isolation, hook advisory.
- 12 bài hồi quy v3.1: schema, âm xưởng, phụ đề, stems/QC, batch.
- Đã thử render hiệu ứng FFmpeg với clip 3 giây/12 FPS 320x568 có audio và render MP4 cuối.

## Phạm vi của kiểm thử

Không thử gọi API thật GPT-5.6 Sol, OpusClip, ElevenLabs hoặc SAM Audio/AudioShake. Không khẳng định tách sạch giọng Đức hoặc giữ tiếng búa hoàn hảo trên video thật. Với v3.2, hiệu ứng chạy trên hình, không trực tiếp chỉnh audio.
