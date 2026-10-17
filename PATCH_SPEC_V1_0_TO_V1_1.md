# BẢN VÁ CHO SPEC 1.0 NGƯỜI DÙNG VỪA DÁN — v1.1

**Giữ nguyên các mục khác** trong SPEC 1.0; thay các dòng xung đột bên dưới trước khi cho coding agent triển khai.

## Mục 5.2 — Thay JSON audio + captions

```json
{
  "audio": {
    "mode": "continuous_workshop_bed_plus_english_voice",
    "auto_duck_workshop_under_english": false,
    "workshop_bed_gain_db": 0.0,
    "speech_removal_strategy": "QC_APPROVED_SPEECH_FREE_RESIDUAL",
    "block_if_asmr_stem_lost": true
  },
  "captions": {
    "enabled": true,
    "format": "ASS_BURN_IN_AND_SRT",
    "language": "en-US",
    "anchor_y_pct": 85.0,
    "font": "Inter Bold",
    "font_size_px_at_1080w": 54,
    "outline_px": 3,
    "max_words_per_cue": 3,
    "timing_source": "EN_ELEVENLABS_ALIGNMENT"
  }
}
```

## Mục 7 — Thay toàn bộ điều 3

**Không duck tiếng xưởng xuống 30–40% khi giọng Anh xuất hiện.** Luôn giữ workshop bed ở 0 dB trong suốt clip. Với lời Đức, chỉ thay các vùng chứa giọng Đức bằng speech-free residual đã QC. Ngay khi có giọng Anh, cộng track English TTS lên nền xưởng; cấm mute/sidechaincompress/volume=0.35 trên workshop bed vì English voice. Nếu audio separator làm mất búa trong cùng vùng giọng Đức, chặn thành phẩm (`NEEDS_ASMR_REVIEW`), không dùng im lặng để thay thế. Lưu 3 track để A/B: `workshop_bed_always_on.wav`, `english_voice_only.wav`, `english_mix.wav`.

## Mục 8 — Thay caption rule

Sub được lấy **theo giọng Anh TTS thực tế**; font Inter Bold tương đương 54 px ở 1080×1920; anchor 85% chiều cao; căn giữa phía dưới; tối đa 3 từ mỗi cue; xuất `captions_en.ass` + `captions_en.srt` và burn trực tiếp vào MP4. ASS PlayRes đúng video output.

## Mục 11 — Thêm QC

- So sánh track nền trước/sau separation tại các cửa sổ ASMR bảo vệ; mất >8 dB thì block để duyệt.
- Test từ AUDIO TRACK **bên trong final MP4**, không chỉ test WAV premix.
- Human listening review khi lời Đức đè lên búa; ngưỡng RMS không thay thế thẩm định bằng tai.
- Xác minh orchestrator dùng renderer mới, không gọi lại mã ducking cũ.

## Trạng thái giới hạn

Patch code Python đi kèm là **renderer offline**, cần ghép vào ứng dụng của bạn. Chưa thể tuyên bố đã sửa ứng dụng thực tế hoặc xóa tiếng Đức thành công trên footage thật khi chưa có repository và clip.
