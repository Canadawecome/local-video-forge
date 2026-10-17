# Changelog v3.4 — GPT-First Viral Director

- **Breaking pipeline change:** GPT Pass 1 đánh giá video nguồn và chọn timestamps trước khi OpusClip được gọi.
- JSON `precut_plan` ràng buộc source media SHA-256, frame IDs, hook timestamp và source permissions.
- OpusClip ClipAnything được hướng dẫn bằng `curationPref.range` + `curationPref.customPrompt` theo từng candidate; submit API có opt-in `--execute`.
- **GPT Pass 2** phân tích media Opus export thật theo 6 rubric (25/25/20/15/10/5), có hard gates và quyết định APPROVED/RECUT/REJECTED/HOLD.
- `source_mapping.json` dùng Opus timeRanges có unit rõ ràng hoặc editor evidence; thiếu mapping → HOLD.
- Handoff đóng dấu hashes clip/review/source plan/clip evidence/mapping, sửa file → mất hiệu lực.
- Renderer public `storytelling_render_v34.py` yêu cầu approval trước khi kế thừa v3.3 Clean ASMR + English narration + cinematic effects + subtitles.
- Quyền sử dụng được xác minh riêng; GPT chỉ cho đánh giá hình ảnh, không tự certify licenses.
- Không thay thế v3.3 ASR/audio QC; live source separation/TTS vẫn cần connectors thật và footage review.
- Bổ sung `video_event_evidence_v34.py`: scene cuts + audio transients **unclassified** để hỗ trợ phát hiện các khu vực cần dense video frames; Pass 1 hỗ trợ `--events-json`.
- GPT Pass 1 dùng 22 frames/chunk, overlap 5 frames và gộp vùng chọn bị trùng lặp cao.
