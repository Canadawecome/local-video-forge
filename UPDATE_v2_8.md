
---

## 19. UPDATE v2.8 — OPUS TRANSCRIPT FIRST + SPEECH STEM REPLACEMENT (BẮT BUỘC)

> **Thứ tự ưu tiên và quyền ghi đè:** Mục 19 là bản cập nhật mới nhất. Nó thay các câu trong 0, 2, 4, 6, 7, 14, 15, 18 của v2.7 còn mô tả `faster-whisper` chạy mặc định hoặc `-24 dB` là cách loại bỏ giọng Đức chuẩn. Không xóa lịch sử các phiên bản trước; triển khai phải áp dụng quy tắc v2.8.

### 19.1 Phạm vi bất biến

- Một URL nguồn (có quyền sử dụng) → OpusClip tạo **N clip** → đối với mỗi clip hợp lệ: clip transcript riêng → clip inspection + factual script riêng → ElevenLabs segments riêng → mix audio riêng → `final.mp4` + description/hashtags + folder riêng.
- `gpt-5.6-sol` làm bộ não kịch bản qua ảnh tĩnh, source facts và transcript; không giả định Sol nghe MP4 hay YouTube URL trực tiếp. Giữ zero-download *video dài* ở tiền kỳ khi có thể.
- **Không gọi WhisperX/faster-whisper chỉ vì pipeline tới bước ASR.** Trước hết thử lấy transcript từ OpusClip. Số lần gọi ASR fallback phải quan sát được và tính riêng chi phí/thời gian.
- Source-transcript có thể lấy từ OpusClip sau khi project tạo xong; source context ban đầu trước Opus sử dụng metadata/phụ đề YouTube nếu hợp pháp và có sẵn.
- Chỉ phát hành khi transcript, bản dịch, chất âm xưởng, quyền nội dung và output đã qua các gate tương ứng; kết quả của stem separator không mặc nhiên được coi là hoàn hảo.

### 19.2 Sự thật API OpusClip và thứ tự truy xuất

**Đã xác minh từ tài liệu công khai:**

1. OpusClip cho phép tải SRT từ giao diện kết quả (menu transcript / Export to XML chứa SRT). **Không được suy diễn tự động rằng API trả trực tiếp một `srtUrl`.**
2. REST `GET /api/transcripts?q=findByProjectId&projectId=...` có thể trả transcript của **video nguồn** dạng paragraphs và word timings. Lưu vào `source/opus_source_transcript.json`. API timestamps theo đơn vị **giây**; nếu dùng output khác của CLI có `_ms` thì chuẩn hóa sang giây, không lấy tên field làm đoán.
3. Công cụ chính thức OpusClip `clip get --transcript --project PROJECT_ID --clip CLIP_ID` có thể lấy text của clip. **Transcript text đơn thuần chưa chắc có timestamps cấp clip**; inspect phản hồi ở runtime trước khi quyết định bỏ local alignment.
4. Một số giao diện/adapter trả SRT theo **timeline clip**. Khi có, ghi `clip_xxx/transcript/opus_clip.srt` và dùng làm ưu tiên số 1.
5. Chỉ khi có source-to-clip timeline map **đã xác minh** mới dùng project transcript để tạo transcript theo clip. Không được trừ đi `range.startSec` rồi giả định Opus không đảo cảnh, không thay tốc độ, không rút ngắn câu.

**Trình tự ưu tiên:**

```text
FOR EACH OPUS CLIP:
    1. GET exact-clip SRT (provided/exported) and validate vs actual clip duration
       -> if reliable: normalize to transcript_de.json + transcript_de.srt, skip Whisper
    2. ELSE GET exact-clip timed transcript JSON (only if local timebase is explicit)
       -> if reliable: normalize to above, skip Whisper
    3. ELSE GET source-project transcript + VERIFIED edit map
       -> map exact source words/paragraphs into clip timeline, validate,
          optionally local forced alignment for minor uncertainty, skip re-ASR if verified
    4. ELSE run faster-whisper/WhisperX on ONLY this downloaded clip
       -> require segment/word timestamps; log fallback reason and provider cost
    5. If no German speech: independently confirm with VAD/listening-QC;
       do not hallucinate a German sentence just to fill script
    6. Transcript QC (German language/technical terms/timing/visual-spoken mismatch)
       -> after PASS route to translation & segment planning
```

**QC điều kiện:** timestamps nằm trong `[0, actual_clip_duration]`, time order hợp lý, transcript là tiếng Đức nếu gắn nhãn `de`, không lẫn phụ đề tiếng Anh do Opus tự dịch, không bỏ lời thợ ở điểm quan trọng; những chỗ không chắc chắn phải đánh dấu `LOW_CONFIDENCE`/`NEEDS_REVIEW`. Timing valid ≠ transcription đúng nghĩa; phải có kiểm tra chất lượng nội dung. Subtitle SRT tiếng Anh tạo từ ElevenLabs là asset **khác** với German source transcript.

### 19.3 API adapter / contracts và caching

- Hàm chuẩn: `resolve_german_transcript(clip_id, duration, opus_clip_srt?, opus_clip_timed_json?, opus_project_transcript?, verified_clip_edit_map?) -> TranscriptResult`.
- `TranscriptResult`: `clip_id`, `language`, `timebase="clip_seconds"`, `segments: [{start,end,text,speaker?,confidence?,provenance}]`, `used_whisper: bool`, `source_kind`, `qc_flags`, `version`, `checksum`.
- Persist trong `transcript_de.json`, `transcript_de.srt`, `transcript_qc.json`, giữ `opus_clip_raw.json`, `opus_source_transcript.json`, `time_map.json` nếu có.
- Bất kỳ khi nào transcript đầu vào hoặc clip export thay đổi hash/revision, invalidate **chỉ các child artifacts phụ thuộc**: text translation/voice timing/audio render/captions, không làm lại toàn bộ Opus source.
- Không ép người dùng xuất XML thủ công cho mỗi clip. Ưu tiên API/adapter nếu runtime cung cấp; UI-export SRT là phương án nhập file tùy chọn, fallback local ASR vẫn cần thiết khi API không trả đúng loại transcript.
- `transcript_engine=opus_first`, `fallback_asr=faster_whisper` (tuỳ chọn `whisperx` để forced alignment / diarization), `max_asr_retries=1` hoặc theo ngân sách, `asr_on_every_clip=false`.
- Source-level cached transcript được chia sẻ để lập fact sheet, nhưng **clip-level timings phải độc lập** cho N clip.

Ví dụ truy cập transcript nguồn từ REST (trả JSON, cần key hợp lệ và project hoàn tất):

```bash
curl -fsS -G 'https://api.opus.pro/api/transcripts' \
  -H "Authorization: Bearer ${OPUSCLIP_API_KEY}" \
  --data-urlencode 'q=findByProjectId' \
  --data-urlencode "projectId=${OPUS_PROJECT_ID}" \
  -o opus_source_transcript.json
```

**Không dùng trực tiếp `opus_source_transcript.json` để tạo file SRT clip** nếu chưa có mapping thật. Có sample/validator offline tại `opus_transcript_first_v2_8.py`.

### 19.4 Speech replacement: loại stem tiếng Đức, không chỉ duck

Mục tiêu là chỉ nghe tiếng Anh khi thợ nói và vẫn nghe tiếng búa/mài/lửa. V2.8 thay ưu tiên như sau:

```
Opus clean clip MP4
    │
    ├── Transcript-first Opus -> fallback Whisper only if needed -> DE windows
    │
    ├── Speech separator adapter (SAM Audio LOCAL / AudioShake CLOUD)
    │     ├── `speech_stem.wav` (German voice estimate)
    │     └── `residual_workshop.wav` (hammer/forge/grinder background estimate)
    │
    ├── Audio quality gate: German leakage + hammer preservation + distortion
    │       PASS: use `residual_workshop.wav` for active German windows
    │       FAIL: safer alternate source/regen OR `NEEDS_AUDIO_REVIEW`
    │
    ├── GPT-5.6 Sol per-clip translation (faithful) + optional story in safe gaps
    ├── ElevenLabs DE->EN dubbing segments with timestamps
    └── FFmpeg: residual under dubbed windows + original audio elsewhere +
                 original ASMR protected intervals + narration only in gaps
```

- SAM Audio: nhận text prompt về human speaking / thời gian lời; cần kiểm tra cài đặt, khả năng GPU/cấp quyền checkpoint. **Không nhầm audio separation với language-specific voice recognition**: transcript xác định thời gian tiếng Đức, model separation xác định âm thanh giọng người.
- AudioShake: alternative qua API nếu runtime thiếu tài nguyên hoặc model local không đạt; giá/quyền truy cập phải được test trước.
- `-24dB` whole-track duck của v2.7 **chỉ là fallback thủ công được chấp thuận**, không phải `SPEECH_REMOVED`. Nếu German voice và impact trùng, không được thừa nhận đủ sạch nếu chỉ duck nguyên audio.
- `workshop residual` chưa được kiểm chứng không được dùng âm thầm. Âm thanh sau separation có thể mất transient búa, tiếng kim loại, gây artefact. Nếu thất bại, clip chờ duyệt/thay nguồn chứ không tuyên bố xóa triệt để.
- Bản dịch English `en_script_text` phải map tới từng `de_speech_id` và phù hợp time window (thời lượng TTS thực đo). `narration_story` chỉ nằm trong safe interval, tránh đè vào protected ASMR.

### 19.5 File layout mở rộng (per clip)

```text
source_<id>/
  opus_projects/<project_id>/opus_source_transcript.json
  clips/clip_001_<clipid>/
    opus_clip.mp4
    transcript/
      opus_clip.srt               # optional, only if available
      opus_clip_raw.json          # optional, provider return
      time_map.json               # optional, verified source->clip map
      transcript_de.json          # normalized CLIP-local seconds
      transcript_de.srt           # normalized CLIP-local seconds
      transcript_qc.json          # provider/fallback source, errors, confidence
    audio/
      german_speech_stem.wav      # if model separator approved
      residual_workshop.wav       # if separator approved
      english_dub_*.wav
      final_mix.wav
    script_en.md
    script_tts.txt
    edit_plan.json
    captions_en.srt
    description.txt
    hashtags.txt
    final.mp4
    qc_report.json
  clips/clip_002_<clipid>/...
  batch_manifest.json
```

### 19.6 Acceptance tests v2.8

| ID | Scenario | Expected |
|---|---|---|
| V28-01 | Clip has valid German SRT with clip-relative timestamps | Zero Whisper calls, SRT/JSON normalized |
| V28-02 | Clip SRT missing but clip-local timed transcript JSON exists | Zero Whisper calls |
| V28-03 | Only source project transcript exists; **no verified timeline map** | Run local ASR on that clip, NEVER assign raw source seconds to clip |
| V28-04 | Source transcript + verified reordered edit map | Correct mapped clip-relative timeline; validate boundaries |
| V28-05 | Opus SRT empty/corrupted/out of clip bounds | Run ASR once for that child clip, save fallback reason |
| V28-06 | 5 clips with transcripts, 2 clips without | 5 bypass Whisper; exactly 2 run fallback; N child scripts remain independent |
| V28-07 | No speaking in clip / no transcript | Speech absence confirmed, ASMR_ONLY or story, no invented dub |
| V28-08 | Separator leaves audible German or distorts hammer | `NEEDS_AUDIO_REVIEW`, not publish-ready |
| V28-09 | SAM unavailable or insufficient GPU | Backend adapter can route to AudioShake if configured/allowed, else review |
| V28-10 | English TTS lasts longer than German window | Re-write/retime with proof, no truncation |
| V28-11 | Opus provider returns English auto-translated subtitles | Reject as raw German transcript, do not use for source translation |
| V28-12 | 10 Opus clips | 10 clip-bound transcripts (including confirmed-empty), up to 10 independent scripts, voice, description & hashtags folders |

**Definition of DONE v2.8:** Tạo N child jobs từ N usable Opus clips; ưu tiên reuse SRT/timed transcript **khớp clip**; chỉ chạy ASR trên clip thiếu transcript hợp lệ; tách giọng Đức thành stem để thay bằng tiếng Anh với QC giữ ASMR; không còn khẳng định duck cả track là xóa giọng; không đòi Gemini; mỗi clip có output folder và publish pack riêng. Đây là contract + adapter offline; muốn chạy trên repository sản xuất vẫn phải tích hợp và thử API/nguồn video thật.

### 19.7 Tài liệu tham chiếu (tra cứu 17/10/2026)

- OpusClip Export-to-XML (gói tải chứa `.srt`): https://www.opus.pro/export-to-xml
- OpusClip project transcript/clip get: https://github.com/opus-pro/opus-skills/blob/main/skills/opusclip/SKILL.md
- OpusClip public API reference: https://github.com/opus-pro/opus-skills/blob/main/skills/opusclip/references/api-reference.md
- OpusClip transcription overview: https://www.opus.pro/blog/video-transcription-api
- SAM Audio: https://github.com/facebookresearch/sam-audio
- WhisperX: https://github.com/m-bain/whisperX
