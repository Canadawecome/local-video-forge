# SPEC CHÍNH THỨC v2.8 — LOCAL VIDEO FORGE: OPUS TRANSCRIPT FIRST + SPEECH STEM REPLACEMENT

**Cập nhật:** 17/10/2026  
**Bản kế thừa đầy đủ:** v2.7 (one YouTube → N clips → N scripts/TTS/folders).  
**Quan trọng:** Quy tắc *v2.8 mục 19* ghi đè mọi mô tả trước đó khiến Whisper chạy mặc định hoặc coi deep-duck là xóa được giọng Đức.  
**Mức triển khai:** SPEC + adapter transcript-first đã kiểm thử offline; separator SAM Audio/AudioShake chưa được tích hợp/kiểm chứng bằng API thật.

# SPEC CHÍNH THỨC v2.7 — LOCAL VIDEO FORGE: ONE YOUTUBE → MULTI CLIPS → MULTI SCRIPTS → MULTI VOICES

**Ngày chỉnh sửa:** 16/10/2026  
**Trạng thái:** Final product specification v2.7 + runnable per-clip hybrid audio patch; vẫn KHÔNG phải ứng dụng đầu-cuối đã hoàn thành.  
**Kế thừa:** `SPEC_Local_Video_Forge_ASMR_v2.4_REVIEWED.md`, các hợp đồng v2.2–v2.4, Notion “Đức >>> Anh”, tài liệu `DAI_TONG_HOP_BI_THUAT_TIKTOK_DUC_MY_CHINH_THUC_2026.md`.  
**Nền kế thừa v2.5:** Thay tư duy **một nguồn → một video** bằng **một nguồn YouTube → toàn bộ clip hữu dụng từ OpusClip → mỗi clip một kịch bản độc lập → mỗi clip một bản ElevenLabs độc lập → mỗi clip một thư mục output hoàn chỉnh**.  

**Lịch sử thay đổi kiến trúc v2.6 (NO GEMINI, nay áp dụng transcript-first v2.8):** Dùng `gpt-5.6-sol` làm model suy luận và thị giác từ *ảnh tĩnh*, không giả định OpenAI đọc trực tiếp video/YouTube URL. Duy trì trải nghiệm 1 URL: lấy metadata/phụ đề hợp lệ từ nguồn → GPT-5.6 Sol lập context sơ bộ (không đoán hình ảnh) → OpusClip trực tiếp nhận URL và tạo N clip → download N clip → local FFmpeg lấy frames, Opus clip transcript/SRT trước (chỉ dùng `faster-whisper`/WhisperX khi thiếu hoặc lệch) để lấy lời Đức → GPT-5.6 Sol viết một script khác nhau cho mỗi clip → ElevenLabs → render riêng. **Không cần GOOGLE/GEMINI_API_KEY.**

**Lưu ý API:** ChatGPT subscription không đồng nghĩa có OpenAI API credits. Cần `OPENAI_API_KEY` riêng và API access cho `gpt-5.6-sol`; cần `OPUSCLIP_API_KEY`, `ELEVENLABS_API_KEY`.

**Đối tượng:** Video xưởng Đức, rèn, mài, phục chế, tiện/phay, thủ công, ASMR; biên tập tiếng Anh cho người xem Mỹ.  
**Quyền:** Chỉ xử lý/đăng tải nội dung có quyền sử dụng phù hợp; quyền xem trên YouTube không mặc nhiên cho phép tái xuất bản hoặc kiếm tiền.

> **Quy tắc tối cao:** `N = số clip mà OpusClip thực tế xuất được và hệ thống chấp nhận xử lý`. Không đặt sẵn N=3/5/10; không chọn duy nhất clip có điểm cao nhất; không tạo N kịch bản trước khi N clip đã được nhận diện. Mỗi clip được xem/xác minh riêng. `N_valid` có thể nhỏ hơn `N_discovered` do gate chất lượng/bản quyền. Từ `N_valid` tạo `N_valid` kịch bản, `N_valid` TTS và `N_valid` gói thành phẩm, trừ clip bị lỗi/đang chờ duyệt.

---

## 0. Những quyết định KHÓA CỨNG v2.7

| Mã | Quyết định | Ý nghĩa thực thi |
|---|---|---|
| V25-01 | `ONE_SOURCE_MANY_OUTPUTS` | Một `source_id` liên kết nhiều `opus_project_id`/`clip_id`; không còn `active_asset_id` duy nhất ở project. |
| V25-02 | `OPUS_BATCH_BARRIER` | **Đợi các Opus jobs dự kiến kết thúc và tổng hợp danh sách clip** rồi mới kích hoạt viết kịch bản/lồng tiếng hàng loạt. |
| V25-03 | `DYNAMIC_FAN_OUT` | Với mỗi clip đạt gate, tạo **một child job độc lập**: inspect → script → review → TTS → audio → render → QC → publication pack. |
| V26-04 | `SOL_SOURCE_CONTEXT` | Không đọc video trực tiếp từ YouTube: trích xuất metadata/phụ đề hiện có, có thể dùng thumbnail; GPT-5.6 Sol tạo source context có giới hạn bằng chứng; **không tự tạo visual timestamps**. |
| V26-05 | `OPUS_FIRST_VISUAL_GROUNDING` | OpusClip trực tiếp nhận YouTube URL; **chỉ sau khi có MP4 clip Opus**, FFmpeg mới lấy frames và Sol mới có căn cứ thị giác để viết kịch bản. |
| V26-06 | `NO_GEMINI_DEPENDENCY` | Không sử dụng Gemini SDK/model/key/chi phí/fallback; GPT-5.6 Sol được cấu hình bằng `OPENAI_MODEL=gpt-5.6-sol`. |
| V26-07 | `SEPARATE_AUDIO_ASR` (superseded by V28-01) | Sol không nhận audio trực tiếp; **v2.8 ưu tiên Opus SRT/clip transcript**, faster-whisper/WhisperX chỉ là fallback khi thiếu hoặc không đạt QC. |
| V25-05 | `CLIP_LOCAL_GROUNDING` | **Clip cuối của OpusClip là sự thật hình/âm duy nhất để xác định câu nào được đọc ở thời điểm nào**; phải phân tích từng clip riêng. |
| V25-06 | `ONE_CLIP_ONE_SCRIPT` | Mỗi clip có `script_en.md`, `script_tts.txt`, `edit_plan.json` khác nhau và version riêng. |
| V25-07 | `ONE_CLIP_ONE_TTS` | Mỗi clip có file voice riêng, alignment riêng; sử dụng cùng voice profile nếu người dùng muốn đồng nhất kênh. Không chia chung một file TTS dài cho các clip. |
| V25-08 | `ONE_CLIP_ONE_FOLDER` | Mỗi clip có folder riêng chứa source excerpt, script, audio, final MP4, caption/sub, description, hashtag, QC và log. |
| V25-09 | `BEST_EFFORT_MAXIMIZATION` | Cố tận dụng mọi clip đủ chất lượng và nội dung; **không** xuất clip lỗi/rỗng chỉ để tăng số lượng. |
| V25-10 | `PER_CLIP_RETRY` | Nếu clip 4 lỗi ElevenLabs chỉ chạy lại TTS clip 4, không gọi lại OpenAI source scout/Opus và các clip 1–3. |
| V25-11 | `HUMAN_IN_THE_LOOP` | Có thể auto tiến qua các gate đã cấu hình nhưng phải có bước duyệt trước công bố; không tự đăng TikTok. |
| V25-12 | `NO_EVASION_PROMISES` | Không sử dụng mirror/noise/FPS/metadata để tuyên bố tránh nhận diện hoặc thành nội dung nguyên bản; tính nguyên bản phải dựa đóng góp nội dung thực chất. |
| V27-01 | `HYBRID_DEFAULT_FOR_NEW_JOBS` | Kể từ v2.7, **từng clip mới** mặc định `HYBRID_SELECTIVE_DUB_ASMR_STORY`: dịch có chọn lọc những gì người Đức nói, thêm commentary trong khoảng phù hợp, khóa vùng tiếng búa/mài ASMR. |
| V27-02 | `NO_UNTRANSLATED_GERMAN` (updated V28-02) | Dịch tất cả vùng thoại Đức đáng tin; v2.8 ưu tiên tách + thay speech stem và QC; deep duck chỉ là fallback được duyệt, không đại diện vocal removal. |
| V27-03 | `PROTECTED_ASMR` | Trong những khoảng `protected_asmr`, không có English narration, không duck raw workshop nếu không trùng German speech. Nếu trùng, bắt buộc QC-approved workshop stem hoặc `NEEDS_REVIEW`. |
| V27-04 | `ENGLISH_STORY_IN_GAPS` | Chỉ chèn English commentary khi không phủ vùng German dubbing/ASMR. TTS có timing theo từng phân đoạn và script phải bám facts thật của clip. |
| V27-05 | `PERSISTENT_DEFAULT_AND_PATCH` | Lưu cấu hình mặc định trong `config/hybrid_audio_defaults.json`, apply cho child job mới; dùng `HybridClipPlan` + `hybrid_audio_engine.py`. |

### 0.1 Công thức output

```text
M = số Opus project jobs được gửi (mặc định M=1 toàn video; M>1 chỉ khi có các cửa sổ có mốc thời gian được kiểm chứng)
N_discovered = số clip IDs duy nhất đọc từ tất cả project jobs đã hoàn thành
N_accepted  = số clip được chấp nhận sau QC + rights + editorial viability
N_scripts   = số clip accepted đã tạo script và PASS SCRIPT_QC
N_voices    = số clip có script PASS đã có ElevenLabs voice PASS
N_final     = số clip render và FINAL_QC PASS
N_asmr_final = số final được duyệt ngoại lệ ASMR_ONLY, không có TTS

N_final - N_asmr_final <= N_voices <= N_scripts <= N_accepted <= N_discovered
N_final <= N_accepted
```

Không dự đoán tổng N từ độ dài video hoặc `clipDurations`. Nếu OpusClip trả 0 clip thì `NO_USABLE_CLIPS` và báo nguyên nhân, không bịa output.

## 1. Mục tiêu, đầu vào, đầu ra

### 1.1 Đầu vào bắt buộc

- `youtube_url` (URL công khai mà OpusClip có thể truy cập; **không** chuyển URL này thẳng vào input video của OpenAI).
- Bằng chứng quyền sử dụng video, âm thanh, các phạm vi được phép sửa/đăng/khai thác thương mại (hard gate theo v2.4).
- Cấu hình voice mặc định `QIhD5ivPGEoYZQDocuHI` (tên Adam theo lựa chọn người dùng; xác minh quyền truy cập/metadata trong tài khoản ElevenLabs).
- `max_provider_spend_usd` và `output_root`.

### 1.2 Đầu vào tùy chọn

`fact_sheet.md`, hướng dẫn phong cách kênh, `target_duration_sec` hoặc dải duration, số clip tối đa theo ngân sách, topic priority, chọn Mode B/C, dữ kiện nhân vật/vật liệu xác thực, từ khóa mong muốn, template clean 9:16, source attribution, chính sách ngôn ngữ, business/legal notes.

### 1.3 Đầu ra thành công

- Thư mục nguồn `source_<id>/` có `source_metadata`, `source_context_sol`, `source_evidence`, Opus job/results, rights, dashboard và batch report.
- **Mỗi clip thành công** có `final.mp4`, `script_en.md`, `script_tts.txt`, `voiceover.wav`/`mp3`, `captions.ass`/`.srt`, `description.txt`, `hashtags.txt`, `publish_pack.json`, `edit_plan.json`, `qc_report.json`.
- `batch_summary.csv` và `batch_manifest.json`: tất cả clip, trạng thái, lỗi, chi phí, đường dẫn, mức trùng cảnh, clip nào cần duyệt.
- Không tự đăng; gói thành phẩm có thể dùng cho thao tác xuất bản được phép.

---

## 2. Kiến trúc tổng thể — Global Scout → Opus Fan-out → Clip Fan-out

```text
[YOUTUBE URL + RIGHTS + CONFIG]
              |
              v
  PRE-FLIGHT (auth / rights / public URL / budget)
              |
              v
  SOURCE TEXT INGEST + GPT-5.6 SOL (SOURCE CONTEXT; 1x/SOURCE REVISION)
     - Collect permitted YouTube metadata, description, subtitles/transcript if available
     - Optional public thumbnail: static image only, no shot-level observations
     - Evidence IDs, confidence, timestamp ONLY from traceable inputs
     - Source context + topical Opus custom prompts; no invented visual shot ranges
     - If metadata/subtitles unavailable: use a broad safe prompt and let Opus self-curate
              |
              v
  OPUSCLIP PROJECT CREATION (1 HOẶC NHIỀU WINDOWS/JOBS)
     - ClipAnything, portrait, requested clipDurations, clean template
     - asynchronous projects with idempotency/credits
              |
              v
  [WAIT ALL SCHEDULED OPUS JOBS TERMINAL]
              |
              v
  ENUMERATE ALL CLIPS / DEDUP IDS / METADATA / EXPORT DOWNLOAD
              |
              v
  OPUS_BATCH_BARRIER -> DISCOVERED N CLIPS (N DYNAMIC)
              |
              v
  PER-CLIP PRE-QC + RIGHTS + VIABILITY GATE
              |
      +-------+--------+------------------------- ...
      |                |
    Clip 01           Clip 02                  Clip N
      |                |                         |
   Inspector 01     Inspector 02              Inspector N
   - local frames  - local frames             - local frames
   - Opus SRT→ASR* - Opus SRT→ASR*           - Opus SRT→ASR*
   - ASMR events   - ASMR events              - ASMR events
      |                |                         |
   Sol Script 01  Sol Script 02             Sol Script N
   (clip+global facts) (clip+global facts) (clip+global facts)
      |                |                         |
   TTS ElevenLabs 01 TTS ElevenLabs 02      TTS ElevenLabs N
      |                |                         |
   local audio mix / subtitles / local FFmpeg render (independent jobs)
      |                |                         |
   FINAL_QC + publication pack (each) + human review
      |                |                         |
   /clip_001/        /clip_002/               /clip_NNN/
      +----------------+-------------------------+
                       |
                       v
        BATCH SUMMARY + GALLERY + COST LEDGER + EXPORT
```

**Tính tuần tự:** `SOURCE_TEXT_SCOUT` → `OPUS_PROJECTS` → `OPUS_BATCH_COMPLETE` → `ENUMERATION/CLIP_QC` → `CLIP_ANALYSIS` → `SCRIPT` → `TTS` → `RENDER`. Các child jobs **có thể chạy song song SAU barrier** trong giới hạn API/quota. Không viết kịch bản riêng từng clip chỉ từ metadata/trích đoạn phụ đề YouTube trước khi có clip Opus thực tế; source scout chỉ sinh context/prompt.

### 2.1 Source-level và Clip-level tách biệt

| Source-level (tính một lần) | Clip-level (tính N lần) |
|---|---|
| URL/rights & source identity | Clip ID + asset hash + rights inheritance |
| Source metadata + Sol text context + evidence provenance | FFmpeg sampled frames từ MP4 Opus + faster-whisper/VAD + Sol vision inspector |
| Source text data có thể rỗng/thiếu transcript (không bịa) | Observation phải có `clip_time_sec` và frame/audio evidence cụ thể |
| Opus project scheduling / provider status | Clip-specific story angle, script, edit plan |
| Source license / shared source credit | TTS voice+alignment, audio mix, captions |
| Batch budget, report, retry policy | Preview, final MP4, description, hashtags, QC |

### 2.2 Quản lý số clip

`clip_selection_policy`:
- `ALL_USABLE` (**default**): xử lý mọi clip pass gate; phù hợp yêu cầu tối đa hóa của người dùng.
- `TOP_K_USABLE`: chỉ xử lý K clip tốt nhất khi ngân sách/hiệu suất có giới hạn.
- `MANUAL_SELECT`: UI checkbox chọn clip sau khi Opus output đã có.

**Không** mặc định chỉ lấy `top 1` hay `viral score >=85`; provider score chỉ là một tín hiệu bổ trợ. Tất cả clips được liệt kê, bao gồm rejected và pending để người dùng thấy Opus đã cắt được bao nhiêu.

## 3. State machine và dữ liệu liên kết

### 3.1 Source batch statuses

```text
CREATED -> PREFLIGHT_PASS -> SCOUT_DONE -> OPUS_SUBMITTED -> OPUS_RUNNING
  -> OPUS_BATCH_COMPLETE -> CLIPS_ENUMERATED -> CHILD_JOBS_ACTIVE
  -> BATCH_COMPLETE | BATCH_PARTIAL | NEEDS_REVIEW | FAILED
```

- Opus project states có thể `SUCCEEDED/FAILED/TIMED_OUT`; tất cả phải ở trạng thái terminal trước khi barrier được mở, **kể cả thất bại**, và được ghi rõ trong report.
- `BATCH_PARTIAL` khi một/một số clip lỗi, các clip khác vẫn thành công.
- `BATCH_COMPLETE` khi toàn bộ accepted clips có verdict terminal, không nhất thiết tất cả đều published-ready.
- Nếu Opus tool không cho nhận list đúng cách: `OPUS_RESULTS_UNVERIFIED`, người duyệt không được suy ra N.

### 3.2 Clip states

```text
DISCOVERED -> ASSET_DOWNLOADED -> PREFLIGHT_QC_PASS -> INSPECTED
  -> SCRIPT_DRAFTED -> SCRIPT_APPROVED -> TTS_DONE -> AUDIO_QC_PASS
  -> PREVIEW_READY -> FINAL_READY -> FINAL_QC_PASS -> PUBLISH_READY

Alternative terminal/review states:
REJECTED_QC | REJECTED_RIGHTS | REJECTED_EDITORIAL | NEEDS_REVIEW |
TTS_FAILED | RENDER_FAILED | FINAL_QC_FAILED | CANCELLED
```

`clip_id` là provider-native identity; `clip_uid = source_id + provider_project_id + clip_id` đảm bảo uniqueness, kể cả OpusClip trả trùng `clip_id` trong các project khác nhau. Output folder dùng index cố định do batch manifest quản lý, không dùng tên script làm identity.

### 3.3 Bảng SQLite mới/đổi

```text
sources(id, youtube_url, rights_status, metadata_json, created_at)
source_evidence(id, source_id, evidence_type, source_in, source_out, text, verification)
source_batches(id, source_id, config_hash, barrier_state, clip_selection_policy,
               max_spend_usd, created_at, completed_at)
opus_projects(id, batch_id, provider_project_id, window_id, status, request_hash,
              submitted_at, completed_at, last_error)
clips(id, batch_id, opus_project_id, opus_clip_id, index_no, status,
      source_asset_path, source_asset_sha256, duration_sec, opus_metadata_json,
      output_folder, title_en, narration_mode, revision)
clip_inspections(id, clip_id, inspector_json, transcript_path, fact_refs_json)
clip_scripts(id, clip_id, revision, script_text, tts_text, story_angle, evidence_json,
             approved_at, script_hash)
clip_tts(id, clip_id, script_revision, voice_id, model_id, settings_hash,
         audio_path, alignment_path, provider_request_id, status)
clip_renders(id, clip_id, script_revision, ffmpeg_plan_hash, preview_path,
             final_path, media_probe_json, qc_status)
clip_publications(id, clip_id, revision, title_en, description_en,
                  hashtags_json, source_credit, policy_status)
clip_job_attempts(id, clip_id, stage, attempt, input_hash, status, error_code,
                  started_at, finished_at)
provider_costs(id, batch_id, clip_id_nullable, stage, estimated_usd, actual_usd, unit)
```

**Đổi từ v2.4:** không lưu `active_asset_id` trên source project như asset duy nhất. Cùng lúc tồn tại nhiều `clips` và nhiều bản script, audio, video. Tất cả artifact có `clip_uid`, `revision`, `input_hash`, `sha256`.

## 4. YouTube Source Text Scout bằng GPT-5.6 Sol (NO GEMINI, NO NATIVE VIDEO)

### 4.1 Khả năng có thật và giới hạn bắt buộc

- OpenAI model **`gpt-5.6-sol`** hỗ trợ text + image input, structured text output; **KHÔNG hỗ trợ đầu vào video và audio**. Chỉ gọi `gpt-5.6-sol` cho phân tích text + ảnh; không pass YouTube URL/MP4 như `input_video` hay giả lập model có native video understanding. Ảnh và text có thể đưa qua Responses API `input_image` + `input_text`.
- **YouTube URL là input orchestration**, không phải OpenAI video input. `SourceIngestAdapter` và OpusClip hiểu URL; nguồn video gốc không cần download về local ở `DEFAULT_ZERO_ORIGINAL_DOWNLOAD`.
- Audio/transcript do `faster-whisper`/VAD chạy local; tùy chọn `whisper-1`/`gpt-transcribe` qua API *riêng* nếu user bật. Sol **không** thay ASR engine.
- Xác minh quyền sử dụng nguồn, âm thanh và phạm vi chuyển thể trước bước cắt. Không bypass các giới hạn nguồn/platform. URL không khả dụng thì yêu cầu người dùng cung cấp file gốc có quyền sử dụng hoặc video/subtitles hợp lệ, không tự gán quyền.
- OpenAI API billing tách biệt gói ChatGPT. Cấu hình `OPENAI_API_KEY`, `OPENAI_MODEL=gpt-5.6-sol`, `OPUSCLIP_API_KEY`, `ELEVENLABS_API_KEY`; **không khai báo GPT-5.6 Sol key**.

### 4.2 Source Ingest: lấy dữ liệu văn bản trước, không tải video dài

Các bước theo thứ tự (có cache và giới hạn request):

1. Validate `youtube_url`, source identity, video Public/provider fetchability, scope quyền khai thác, cost budget. Trích thông tin qua API/metadata reader hợp lệ hoặc dữ liệu do user cung cấp: `title`, `description`, `channel`, `duration`, `chapters`, `tags`, `thumbnail`, subtitle tracks; ghi rõ source field và provenance. Có thể sử dụng công cụ metadata/subtitle compliant ở chế độ **không tải video gốc**; nếu fail, nguồn user-supplied title/description vẫn đủ tạo Opus prompt đơn giản.
2. Với phụ đề tiếng Đức đã được cấp quyền truy xuất (creator-provided hoặc captions accessible), lấy đoạn text cùng timecode thật. **Không** cam kết mọi video đều có subtitles; automated captions có thể sai hoặc không truy cập được.
3. Nếu có thumbnail, tải *ảnh thumbnail* hợp lệ (không phải video) để cung cấp một điểm tham khảo chung, gắn `THUMBNAIL_ONLY`. Không coi thumbnail là bằng chứng về trình tự hành động hoặc nguồn ASMR.
4. Gửi **text/ảnh tĩnh** tới `gpt-5.6-sol` để trích chủ đề, thuật ngữ, facts đã dẫn nguồn, các kịch bản/công đoạn có thể xuất hiện (`hypothesis`), và `customPrompt` chung cho ClipAnything. Khi dữ liệu không đủ, output `INSUFFICIENT_SOURCE_CONTEXT` với prompt rộng an toàn; không bịa nhiệt độ, tuổi hiện vật, model máy, phần kết, thời lượng thao tác.
5. Tạo `source_context_sol.json`, `source_metadata.json`, `source_evidence.json`, `source_subtitles_de.json` (nếu có), `opus_prompt_plan.json`. Cache theo `source_id`, `source_data_hash`, `model_id`, `prompt_version`.

**Khoanh vùng Opus:** Với `METADATA_ONLY` hoặc không có timestamp đáng tin, **OMIT `curationPref.range`**; cho OpusClip tự cắt trên toàn bộ video. Chỉ thêm window khi timecode lấy được từ `SUBTITLE_TIMESTAMPS`, `EDITOR_MARKER`, hoặc `AUTHORIZED_SOURCE_FRAMES`; prompt luôn nêu cảnh mong muốn như yêu cầu, không khẳng định đã nhìn thấy cảnh.

### 4.3 Chế độ khảo sát nguồn

| Mode | Source download | Sol nhìn thấy | Có thể khẳng định gì? | Window `range` |
|---|---|---|---|---|
| `METADATA_ONLY` (fallback) | Không | Title/description/chapter/text | Chủ đề, creator claims có gắn nguồn | Không tự phát sinh |
| `SUBTITLE_ENRICHED` (default nếu có) | Không download MP4 | Metadata + phụ đề/timestamps thật + optional thumbnail | Lời được nói, công đoạn mô tả; không xác nhận footage | Chỉ theo markers phụ đề có kiểm chứng và giới hạn độ tin cậy |
| `AUTHORIZED_SOURCE_FRAMES` (opt-in) | **Có** nếu có file gốc được cấp quyền | Sampled frames + metadata + subtitle | Mốc visual đủ bằng chứng theo sample resolution | Có thể tạo candidate windows từ sampled frame sequence, chưa bảo đảm frame-perfect |

Trong default pipeline, sau khi Opus trả N clip mới có phân tích thị giác đầy đủ từng clip. Nếu video gốc không tải được, đây là giới hạn thật của hệ thống chứ không phải lỗi cần che giấu.

### 4.4 Fact resolution / không dựng chuyện

1. `CLIP_DIRECT`: hành động thực sự nhìn thấy trong frame clip hoặc âm thanh được nhận diện từ clip (ưu tiên cao nhất), có clip timestamps + evidence refs.
2. `SOURCE_TRANSCRIPT`: nội dung lời nói tiếng Đức gốc được nhận diện/kiểm tra, không coi là xác minh kỹ thuật tuyệt đối.
3. `SOURCE_METADATA`: mô tả/tiêu đề do tác giả đăng; chỉ là thông tin nguồn, cần so với footage và facts trước khi khẳng định.
4. `THUMBNAIL_ONLY`: tham khảo vật thể/chủ đề, không suy diễn frame/timecode/âm thanh của video dài.
5. `EXTERNAL_CONTEXT`: tài liệu kiểm chứng có URL; không nói như thể người thợ đã nói câu đó.
6. `UNVERIFIED`: không dùng như fact chắc chắn trong video, metadata quảng bá hoặc con số định lượng.

**Ánh xạ thời gian:** `opus_clip_seconds -> youtube_source_seconds = UNKNOWN` cho đến khi Opus provider trả mapping hợp lệ hoặc có verification local. Không lấy timestamp từ subtitles toàn nguồn để chèn trực tiếp vào clip đã cắt/đảo thứ tự.

### 4.5 GPT-5.6 Sol Responses API / OpenAI adapter

```python
# Sơ đồ API tối thiểu cho ảnh tĩnh từ MP4 clip ĐÃ DOWNLOAD:
from openai import OpenAI
import base64

client = OpenAI()  # OPENAI_API_KEY

def as_input_image(path: str, detail: str = "high"):
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return {
        "type": "input_image",
        "image_url": f"data:image/jpeg;base64,{b64}",
        "detail": detail,
    }

# sampled_frames: ordered list of (clip_time_sec, jpeg_path), created by local FFmpeg.
# audio_transcript: generated independently via local faster-whisper.
# Bind output to a reviewed strict JSON Schema / Pydantic model in production.
def inspect_clip_with_sol(sampled_frames, audio_transcript, source_context_text):
    parts = [{
        "type": "input_text",
        "text": f"Analyze this ONE Opus clip. Frames are timestamped and sparse; "
                f"do not infer unseen events. Source context is secondary. "
                f"Transcript: {audio_transcript}\nSource context: {source_context_text}"
    }]
    for sec, file_path in sampled_frames:
        parts.append({"type": "input_text", "text": f"FRAME at {sec:.2f}s"})
        parts.append(as_input_image(file_path))
    return client.responses.create(
        model="gpt-5.6-sol",
        input=[{"role": "user", "content": parts}],
        reasoning={"effort": "medium"},
        # Production: add `text={"format":{"type":"json_schema",...}}`.
    )
```

Mỗi JPEG/frame có thể tính image tokens và tốn API phí. Không gửi 60–90 giây video dưới dạng hundreds of frames mặc định: cấu hình adaptive sampling + budget trước khi gọi Sol.

### 4.6 Adaptive frame sampler và nguồn âm thanh clip

- Sau OpusClip HD export và local download mới chạy FFmpeg/ffprobe. Pass 1: khoảng `0.5 fps` (mỗi 2 giây một ảnh) 320–768px, gắn clip timestamp thật + hash. Pass 2: bổ sung frames ở cảnh chuyển shot/đỉnh chuyển động/cú búa (ví dụ 2–4 fps trong *những vùng ngắn* do local scene/event detection khoanh), không mặc định tăng toàn clip.
- Sử dụng `faster-whisper` / local VAD để lấy lời nói tiếng Đức và timestamps, thêm detector âm nhạc/ASMR. Nếu ASR không chắc, ghi `TRANSCRIPT_UNCERTAIN`; đừng bịa lời Đức từ ảnh.
- Kết hợp frame timeline, transcript, `source_context_sol` để Sol tạo **clip_inspection.json trước** rồi mới viết script. Bắt buộc `evidence_refs` gắn tới frame/audio/text segment, và `confidence`/`observed_vs_inferred` trong kết quả.
- Nếu video có tiếng búa chồng thoại Đức, không giả định Demucs sạch; speech separation là optional + A/B audio QC. Bảo toàn ASMR ưu tiên hơn việc ép lời bình phủ kín.
- Nếu frame extraction thất bại: chỉ tạo `INSPECTION_BLOCKED`; không viết lời bình gắn sự kiện nhìn thấy khi chưa có hình ảnh. Có thể xử lý ASMR_ONLY sau human review nếu bằng chứng âm thanh đủ.

### 4.7 Cost, capability & fallback

- Cấu hình `OPENAI_MODEL=gpt-5.6-sol` (không dùng tên hiển thị "Sol" làm model ID tùy tiện). Kiểm tra `client.models.retrieve("gpt-5.6-sol")` **nếu API key có quyền**; nếu 403/404 hoặc quota fail, dừng với `OPENAI_MODEL_UNAVAILABLE`, không fallback sang GPT-5.6 Sol.
- Chi phí Sol tính theo text/image input tokens và output tokens; tính một lượt source context và N lượt clip inspection+script, giới hạn `max_frames_per_clip`, `max_total_image_tokens`, `max_concurrent_openai`, `max_provider_spend_usd`.
- `SOURCE_TEXT_UNAVAILABLE`: vẫn có thể gửi 1 Opus project bằng user-supplied topic + broad workshop prompt, nhưng source context đánh dấu thiếu; **không** tự tạo facts từ URL rỗng. `OPENAI_MODEL_UNAVAILABLE`: tạm dừng stages Sol, giữ clip assets/cached outputs để chạy tiếp sau.

## 5. OpusClip — cắt hàng loạt và nhận TẤT CẢ clip

### 5.1 Request adapter

Provider-specific API documented baseline:

```http
POST https://api.opus.pro/api/clip-projects
Authorization: Bearer $OPUSCLIP_API_KEY
Content-Type: application/json
```

```json
{
  "videoUrl": "https://www.youtube.com/watch?v=VIDEO_ID",
  "brandTemplateId": "CLEAN_9_16_TEMPLATE_ID",
  "curationPref": {
    "model": "ClipAnything",
    "clipDurations": [[60, 90]],
    "customPrompt": "Find several distinct high-quality real workshop action sequences, preserving close-ups of hammer strikes, grinding, inspection and authentic mechanical ASMR. Avoid prolonged talking heads."
  },
  "renderPref": {"layoutAspectRatio": "portrait"},
  "importPreference": {"sourceLang": "de"}
}
```

**Quan trọng:** đây là **request một Opus project trên toàn video (default không truyền `range`)**; **không** có field giả `numberOfClips: 10`. Provider quyết định số clip có thể cắt. Chỉ tạo nhiều projects theo các windows có timestamps đáng tin (`SUBTITLE_TIMESTAMPS`, `EDITOR_MARKER`, hoặc `AUTHORIZED_SOURCE_FRAMES`); nếu không có, gửi 1 job với custom prompt chung và nhận toàn bộ clip Opus xuất được. Nếu provider không hỗ trợ một field trong tài khoản thực, capability probe và bỏ/tùy biến field đó theo API docs.

### 5.2 Lập lịch M project jobs

- Mặc định tạo **một project toàn video** để Opus tự tìm nhiều clip. Nếu có windows thực sự được kiểm chứng, có thể tạo M projects trên windows khác nhau trong ngân sách.
- Không gửi quá nhiều job giống hệt để đánh lừa hệ thống chọn thêm clip; tránh chi phí credit vô ích.
- Mỗi job `request_hash`, `window_id`, `provider_project_id` và `status`. Đợi tất cả terminal.
- Dùng polling; webhook optional nếu endpoint HTTPS có thể tiếp nhận và xác thực chữ ký. Không trông đợi webhook vào localhost.
- Tự động retry lỗi tạm thời trong quota, không duplicate job nếu provider đã nhận request nhưng client timeout.

### 5.3 List, export, download tất cả clips

Sau mỗi project có kết quả:

```http
GET https://api.opus.pro/api/exportable-clips?q=findByProjectId&projectId={projectId}
```

1. Đọc danh sách toàn bộ clip IDs, giữ metadata gốc và `provider_project_id`.
2. Phân biệt **preview URL** và **HD export URL**; không giả định preview là bản clean HD để render final. Nếu HD export cần bước riêng, thực hiện theo capability/API và theo dõi trạng thái export.
3. Download từng MP4 có thể xuất vào `opus_exports/clip_<index>/original_opus.mp4`.
4. `ffprobe`, SHA-256, kiểm duration/dimensions/audio presence/corruption.
5. Khử trùng danh sách theo `(provider_project_id, opus_clip_id)`; kiểm **overlap nội dung** là warning/editorial gate riêng, không xóa nhầm các clip có ý nghĩa khác nhau.
6. Khi tất cả project jobs đã terminal, gọi `close_batch_discovery()` đóng số N và tạo child jobs. Nếu user thêm Opus project mới, mở batch revision mới (`batch_revision=2`) thay vì âm thầm bổ sung clip vào batch đã đóng.

**Tài liệu adapter:** [OpusClip API Quickstart](https://help.opus.pro/api-reference/quickstart); [OpusClip official skills API reference](https://github.com/opus-pro/opus-skills/blob/main/skills/opusclip/references/api-reference.md). Cần test chính xác export HD flow trên tài khoản API thực.

### 5.4 Clean Plate + viability gate — theo từng clip

- Caption/headline/emoji baked-in làm hỏng video, watermark/overlays không được phép xử lý, tay/búa/máy bị crop mất, hình/âm lỗi, ASMR vỡ, clip vô nghĩa → `REJECTED_QC` hoặc `NEEDS_REVIEW`.
- Có nhạc chưa rõ quyền → `MUSIC_UNRESOLVED` và block/đổi clip/xin nguồn âm phù hợp.
- Clip có hình/âm đạt nhưng quá ít thông tin để tạo script độc lập → `EDITORIAL_REVIEW`, không bịa chi tiết để hợp thức hóa.
- Dựa thứ tự thẩm định: rights → decodability → framing/audio → **story angle đủ riêng** → cost feasibility.
- Người dùng có thể quyết định giữ clip xếp hạng thấp nếu vẫn đạt gate. Không ép `viral_score >=85`.

## 6. Fan-out engine sau Opus barrier

Pseudocode **bắt buộc**:

```python
async def finish_opus_batch(batch_id: str) -> None:
    await wait_for_all_scheduled_opus_projects_terminal(batch_id)
    discovered = await enumerate_all_exportable_opus_clips(batch_id)
    discovered = dedupe_provider_identities(discovered)
    await persist_discovered_clips_and_folders(discovered)
    await mark_opus_batch_complete(batch_id, count=len(discovered))

    for clip in discovered:
        if await per_clip_pre_qc_and_rights_pass(clip):
            await enqueue_unique_child_job(
                clip_uid=clip.uid, stage="INSPECT_AND_SCRIPT_TTS_RENDER",
                idempotency_key=f"{clip.uid}:{clip.asset_hash}:v2.5"
            )
        else:
            await mark_clip_review_or_rejection(clip.uid)
```

```python
async def process_clip(clip_uid: str) -> None:
    asset = await load_clip_asset(clip_uid)
    inspection = await inspect_real_opus_clip(asset)                # per clip
    context = await fetch_relevant_source_context(inspection)   # reuse Sol source-context
    script = await generate_unique_script_for_this_clip(inspection, context)
    await validate_script_claims_and_time_budget(script, asset, inspection)
    await persist_script_revision(clip_uid, script)

    if requires_human_script_approval():
        await wait_for_review_approval(clip_uid)  # queue state, not blocking worker
        return

    tts = await elevenlabs_generate_per_clip(script.tts_text, clip_uid=clip_uid)
    await verify_tts_alignment_duration(tts, script)
    final = await render_ffmpeg_for_clip(asset, inspection, script, tts)
    await final_media_qc(final)
    await generate_publication_pack_from_verified_clip(clip_uid, script)
    await mark_ready_or_review(clip_uid)
```

`wait_for_review_approval()` là **trạng thái chờ trong DB**, không chặn một worker thread/process. Khi người dùng duyệt thì enqueue stage tiếp theo. Có `max_concurrent_scripts`, `max_concurrent_tts`, `max_concurrent_render`, rate limiter, per-clip provider cost estimate. Mỗi stage check budget trước khi gọi API.

### 6.1 Không tái tính những gì đã có

- Sol source context (metadata + subtitle) global cache; reuse cho tất cả clips; không coi source text là bằng chứng trực tiếp của hình ảnh.
- Mỗi Opus clip Inspector riêng (không reuse transcript clip khác).
- OpenAI Script writer riêng theo `(clip_uid, script_revision, evidence_hash)`.
- ElevenLabs cache theo `(clip_uid, script_revision, voice_id, model_id, settings_hash)`; regen một clip không chạm các clip khác.
- Render cache theo `(clip_uid, script_hash, tts_audio_hash, edit_plan_hash, export_profile_hash)`.

## 7. Clip Inspector + kịch bản khác nhau cho TỪNG video

### 7.1 Per-clip input pack

```json
{
  "clip_uid": "src_001:opus_P1:clip_C1",
  "clip_asset_path": "opus_exports/clip_001/original_opus.mp4",
  "clip_duration_sec": 71.9,
  "clip_inspection": {
    "visible_actions": ["heating steel", "hammer shaping", "edge grinding"],
    "audio_events": ["hammer impacts", "grinding wheel"],
    "german_speech": [],
    "protected_asmr_intervals": [{"start": 2.4, "end": 5.8}],
    "source_to_youtube_mapping": "UNKNOWN"
  },
  "global_context_refs": ["source_fact_01", "source_fact_09"],
  "channel_style": "concise factual American English; hybrid ASMR"
}
```

- FFmpeg trích ảnh có timestamp từ *clip Opus thật*, Opus transcript-first (faster-whisper/VAD fallback) phân tích audio, GPT-5.6 Sol nhận **ảnh tĩnh + transcript + source context** để dựng inspection JSON; speaker/music/ASMR map. **Không** upload MP4/audio trực tiếp vào `gpt-5.6-sol`.
- Kiểm tra clip nào chứa những bước gì. **Không** mô tả cảnh không có trong clip bằng ngôn ngữ như thể người xem sắp thấy cảnh đó.
- Fact global chỉ được gắn vào script khi phù hợp ngữ cảnh clip và có evidence. Nếu clip chuyển thứ tự cảnh, clip-local timeline vẫn là chuẩn.

### 7.2 Quy tắc độc lập kịch bản

1. Một clip → một `story_angle` rõ ràng (ví dụ: tạo đầu rìu / mài lưỡi / lắp cán), và `clip_specific_summary`.
2. Hook có hình ảnh thật trong chính clip hoặc cùng đối tượng dự án được chứng minh; không chuyển hook clip A sang clip B khi không có footage tương ứng.
3. Mỗi clip có cấu trúc linh hoạt `HOOK → CONTEXT → PROCESS → PAYOFF → END`, bỏ beat nếu footage không hỗ trợ.
4. Tạo một `en_script_text` mới cho mỗi clip, không dùng một script chung lặp lại N lần rồi thay mỗi tên đồ vật.
5. Kiểm tra `script_similarity` và `source_overlap` xuyên batch: **chỉ cảnh báo** khi kịch bản/cảnh gần như trùng, đề nghị chọn angle khác hoặc loại clip dư thừa; không thực hiện thao tác biến đổi pixel để vượt bộ lọc nền tảng.
6. Độ dài kịch bản phụ thuộc `tts_window` và các khoảng ASMR; không ép 110–125 từ hoặc 72–74 giây cho tất cả clip.
7. Voice có thể giữ cùng persona xuyên series nhưng nội dung TTS, timestamps và file audio **riêng từng clip**.
8. Nếu clip không có thông tin đủ để bình luận hữu ích, tạo `NEEDS_EDITORIAL_REVIEW` chứ không bịa kỹ thuật, giá tiền, niên đại, dung sai hoặc rủi ro.

### 7.3 Narration modes

- **Mặc định từ v2.7:** `HYBRID_SELECTIVE_DUB_ASMR_STORY` cho **mọi clip được nhận**: nếu có lời Đức, dịch và lồng tiếng Anh bám ý người thợ; nếu có khoảng không cần tiếng Đức và không nằm trong protected ASMR, thêm lời dẫn kỹ thuật; bảo vệ các tiếng búa/mài/máy thực tế. Đây là một mode kết hợp, không còn buộc chọn B hoặc C cho cả clip.
- B `SELECTIVE_DUBBING` và C `ORIGINAL_COMMENTARY` vẫn tồn tại như thành phần/legacy và được map thành các `voice_segments.kind = dub/commentary`, không dùng làm mặc định batch.
- Tiếng Đức cần được nhận diện bằng faster-whisper/VAD, Sol dịch dựa trên bản ASR đã đối chiếu và dữ kiện video; không bịa câu nói của thợ. Mỗi phát biểu Đức phải map sang dubbing tiếng Anh.
- TTS không được cắt mất từ nếu dài: short rewrite / time replan / review clip.
- German speech và protected ASMR overlap trên một track: không thể bảo vệ cả hai chỉ bằng ducking; xử lý bằng stem speech-free có QC hoặc chuyển sang NEEDS_REVIEW.
- **Ngoại lệ:** A `ASMR_ONLY` chỉ khi người dùng chủ động chọn / clip thực sự không phù hợp voice và người dùng duyệt. Trong Mode A không có TTS; UI hiển thị rõ ngoại lệ thay vì báo N voice giả.
- Khi mục tiêu bắt buộc là “mỗi clip đều có ElevenLabs”, clip không thể đáp ứng sẽ chuyển `NEEDS_REVIEW`/`REJECTED_EDITORIAL`, không tự chuyển sang A rồi tính là hoàn thành.

### 7.4 Output script theo clip

```json
{
  "schema_version": "2.5",
  "clip_uid": "src_001:opus_P1:clip_C1",
  "script_revision": 1,
  "title_en": "How a Blacksmith Shapes an Axe Head",
  "story_angle": "Hammer forging and shaping the hot steel",
  "narration_mode": "ORIGINAL_COMMENTARY",
  "hook_type": "ACTION_FIRST",
  "hook_visual_in_sec": 2.4,
  "en_script_text": "Every strike gradually pushes the hot steel toward the shape of an axe head.",
  "tts_text": "Every strike gradually pushes the hot steel toward the shape of an axe head.",
  "narration_windows": [{"start_sec": 7.0, "end_sec": 13.0, "text": "Every strike gradually pushes the hot steel toward the shape of an axe head."}],
  "protected_asmr_intervals": [{"start_sec": 2.4, "end_sec": 5.8}],
  "evidence_refs": ["clip_ev_01", "source_fact_01"],
  "script_qc_status": "PASS"
}
```

**Lưu ý:** ví dụ minh họa không được coi là duration-sync thực; timing chính xác chỉ được xác nhận sau khi có file ElevenLabs. Với thoại dài hơn cửa sổ, hệ thống phải tự rút gọn/đặt lại time window hoặc xin duyệt, không cưỡng bức nói quá nhanh.

### 7.5 System instruction cho per-clip scriptwriter

```text
ROLE: Expert documentary short-form editor and engineering fact-checker.
You receive a CLIP inspection built from timestamped still frames + local German ASR and a GLOBAL GPT-5.6 Sol source-text context with limited evidence.
The clip itself is the primary evidence for what viewers will see and hear.

TASK: Generate exactly ONE independent US-English script for this specific clip.
Do not write a batch-wide generic script. Do not assume the clip contains events
only described in the global full-video fact sheet. Cite fact/evidence IDs for
claims. Provide a fresh story angle appropriate to the clip, natural hook,
short factual narration, protected mechanical-ASMR intervals, precise suggested
speech windows, clean TTS copy, and a title.

RULES:
- No invented prices, year, tolerances, engineering mechanisms or danger.
- Don't narrate over protected hammer/grinding/lathe moments unless authorized.
- Do not copy another clip's script; if unavoidable overlap, explicitly flag it.
- Only output structured JSON matching PerClipScriptV25; don't explain outside JSON.
```

## 8. Voice ElevenLabs — N clip = N voice assets

### 8.1 Voice profile

- `voice_id = QIhD5ivPGEoYZQDocuHI` (nhận theo profile người dùng đã chọn; không suy từ nickname hiển thị rằng account luôn có quyền API).
- Model khởi điểm `eleven_multilingual_v2`; config `voice_settings` phiên bản hóa và kiểm tính tương thích.
- Endpoint With-Timestamps: `/v1/text-to-speech/{voice_id}/with-timestamps`. Response thường gồm audio và **character-level alignment**; chuyển đổi sang word/phrase timestamps cho phụ đề. [ElevenLabs official docs](https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps/).
- `previous_text`/`next_text`: dùng **giữa các câu trong cùng clip** để cải thiện tính liền mạch; **không** đưa script clip khác vào để ghép thành một chương nếu chúng không cùng đoạn thoại.

### 8.2 TTS lifecycle một clip

```text
script_tts.txt → ElevenLabs request → decoded voiceover.wav
  → alignment_char.json → alignment_word.json
  → silence trim (conservative) → actual duration measurement
  → adjust word budget / voice pacing / narration windows if needed
  → voice_qc_report.json → audio mixer
```

- TTS input phải chính là script đã duyệt, không dùng transcript nguồn / script toàn batch.
- Voice generation gọi riêng cho mỗi child job; lưu metadata `request_id`, model, voice ID, settings, credit, error, revision.
- Nếu `D_tts > D_window * max_atempo` → viết ngắn/điều chỉnh đoạn đọc và regen riêng clip; không làm mất âm ASMR protected.
- Nếu ElevenLabs rate-limit: clip `TTS_PENDING_RETRY`, chạy lại sau backoff, các clip khác tiếp tục.
- Clip đụng budget: `BUDGET_REVIEW_REQUIRED`, không âm thầm phát sinh phí cho N clip.

## 9. Local Audio/Video Engine (mỗi clip độc lập)

**Mặc định v2.7:** Áp dụng quy trình Hybrid nêu ở §18 và module `hybrid_audio_engine.py`. Đoạn tiếng Đức hạ sâu -24dB có crossfade; trong lời kể English hạ tiếng nền khoảng -7dB; nguyên ASMR không có lời giữ 0dB. Không coi -24dB là loại bỏ giọng Đức hoàn toàn. Âm xưởng trùng tiếng Đức phải có speech-free stem duyệt chất lượng nếu muốn bảo vệ ASMR. Mọi clip đều cần audio listening-QC.

- `MUSIC_RIGHTS_GATE`: kiểm nhạc, tiếng Đức, ASMR và quyền audio. Music separation không chứng minh đã loại bỏ hết bản nhạc; nếu không đạt, block/đổi source/lấy bản âm được phép.
- Tách lời Đức khỏi âm xưởng chỉ khi separation A/B QC đạt. Demucs không được coi là bảo đảm giữ 100% tiếng máy.
- Cấu trúc timeline gồm `VIDEO`, `RAW_ASMR/AMBIENCE`, `EN_VOICE`, `SUBTITLES` và optionally approved `MUSIC`.
- Sidechain ducking có attack/release; dành các đoạn ASMR protected không lời; tránh pumping/clipping, giữ nguyên tính chân thực thao tác.
- Dùng source clip Opus làm visual base, reframe nhẹ khi thực sự cần, phụ đề ASS/SRT theo alignment, FFmpeg build từ `edit_plan.json` đã validate.
- Xuất 540p preview và 1080×1920 H.264/yuv420p final; frame rate căn cứ footage/target, không ép 60fps như luật TikTok.
- Target loudness/loudness range, peak là export profile có QC, không tuyên bố -14 LUFS bắt buộc pháp lý/platform.
- Có `AUDIO_QC` và `FINAL_QC`: audio sync, intelligibility, tiếng Đức còn sót, mức ASMR, captions, crop, metadata private leak, quyền và nguồn fact.

## 10. Mỗi clip một thư mục output riêng — KHÓA CỨNG

```text
local-video-forge/
  data/
    sources/
      src_001_axe_workshop/
        source.json
        rights/
          proof_of_permission.pdf             # nếu có, lưu bảo mật
        global_context/
          source_metadata.json
          source_context_sol.json
          source_subtitles_de.json            # nếu có
          opus_prompt_plan.json
          source_fact_sheet.json
          source_evidence.json
          source_video_summary.md
        opus/
          batch_manifest.json
          project_jobs.json
          opus_batch_report.json
          opus_exports/
            clip_001_original.mp4
            clip_002_original.mp4
            clip_003_original.mp4
        output/
          clip_001_hammer_forging/
            original_opus.mp4                  # hoặc symlink/hardlink + manifest
            clip_info.json
            inspection.json
            transcript_de.json
            evidence_used.json
            story_angle.md
            script_en.md                      # script có cue/timestamp để đọc
            script_tts.txt                    # CHỈ lời đọc copy/gọi API
            edit_plan.json
            audio/
              voiceover.wav
              voiceover.mp3                    # optional
              alignment_char.json
              alignment_word.json
              mixed_audio.wav
            subtitles/
              captions.ass
              captions.srt
            preview.mp4
            final.mp4
            description.txt                   # đoạn mô tả tiếng Anh ready-to-copy
            hashtags.txt                     # hashtag ready-to-copy
            title.txt                         # title riêng từng clip
            publish_pack.json                # title/desc/tags/keywords/credits
            thumbnail.jpg                     # optional
            qc_report.json
            cost_report.json
            process_log.jsonl
          clip_002_edge_grinding/
            ... same independent layout ...
          clip_003_axe_handle/
            ... same independent layout ...
        batch_summary.csv
        batch_manifest.json
        batch_report.md
        index.html                             # optional local gallery
```

- Tên folder dựa `clip_index` cố định + slug được làm sạch (`[a-z0-9_-]`), không trùng, có giới hạn length; không đổi tên folder khi sửa title/hook.
- Tất cả outputs cần relative paths có thật; `publish_pack.json` lưu `final_video_path`, `description_path`, `hashtags_path`, `script_path`, `source_credit`, `rights_state`, `qc_status`.
- `description.txt`: 1–3 câu tiếng Anh đúng nội dung từng clip, có ngữ cảnh/hook/CTA vừa phải, không claim bừa bãi.
- `hashtags.txt`: gợi ý 3–6 hashtag liên quan chính clip, không copy-paste toàn bộ hashtag giống nhau cho N clip. Không có bảo đảm viral/SEO.
- `title.txt`: title riêng, không giật tít trái hình.
- Có thể sinh `publish_caption.txt` gộp mô tả + hashtag để copy một lần; vẫn giữ `description.txt` và `hashtags.txt` riêng theo yêu cầu.
- Nếu clip fail, vẫn có folder với `clip_info.json`/`qc_report.json`/`process_log.jsonl`, nhưng **không** tạo `final.mp4` giả và không đánh dấu `PUBLISH_READY`.

### 10.1 `publish_pack.json` ví dụ (riêng clip_001)

```json
{
  "schema_version": "2.5",
  "clip_uid": "src_001:opus_P1:clip_C1",
  "status": "PUBLISH_READY",
  "title_en": "How a Blacksmith Shapes an Axe Head",
  "description_en": "Watch a blacksmith shape hot steel with controlled hammer strikes before refining the edge. The sound of the workshop tells part of the story.",
  "hashtags": ["#Blacksmithing", "#Forging", "#AxeMaking", "#Metalworking", "#WorkshopASMR"],
  "search_keywords": ["axe forging", "blacksmith workshop", "forging steel"],
  "language": "en-US",
  "media": {"final_video_path": "final.mp4", "thumbnail_path": "thumbnail.jpg"},
  "script_path": "script_en.md",
  "tts_text_path": "script_tts.txt",
  "source_credit": "Attribution per verified license terms",
  "rights_state": "VERIFIED",
  "human_approved": true
}
```

Nếu không có thumbnail thì cho `thumbnail_path=null`; example JSON không có nghĩa đã tạo file ở runtime.

## 11. REST API v2.5

```http
POST   /api/v1/sources                                  # URL, rights, style, spend cap
POST   /api/v1/sources/{id}/scout                       # Text metadata/subtitle -> GPT-5.6 Sol source context once/cache
POST   /api/v1/sources/{id}/opus-batches                # start scheduling M projects
GET    /api/v1/opus-batches/{batch_id}/projects         # states, provider IDs
POST   /api/v1/opus-batches/{batch_id}/sync             # poll jobs/list/export clips
POST   /api/v1/opus-batches/{batch_id}/close            # barrier: terminal jobs only
GET    /api/v1/opus-batches/{batch_id}/clips            # all N incl fail/review
POST   /api/v1/opus-batches/{batch_id}/process-all      # all accepted clips, idempotent
POST   /api/v1/opus-batches/{batch_id}/process-selected # selected clip_uids
GET    /api/v1/clips/{clip_uid}                         # metadata/current status
POST   /api/v1/clips/{clip_uid}/extract-evidence      # local FFmpeg frames + ASR
POST   /api/v1/clips/{clip_uid}/inspect
POST   /api/v1/clips/{clip_uid}/script                  # generate one script
PATCH  /api/v1/clips/{clip_uid}/script                  # edit script/revision
POST   /api/v1/clips/{clip_uid}/approve-script
POST   /api/v1/clips/{clip_uid}/tts                     # one ElevenLabs generation
POST   /api/v1/clips/{clip_uid}/render-preview
POST   /api/v1/clips/{clip_uid}/render-final
POST   /api/v1/clips/{clip_uid}/publication-pack
POST   /api/v1/clips/{clip_uid}/approve-final
POST   /api/v1/clips/{clip_uid}/retry/{stage}           # only this clip and downstream
GET    /api/v1/opus-batches/{batch_id}/summary
GET    /api/v1/opus-batches/{batch_id}/download-manifest
GET    /api/v1/clips/{clip_uid}/artifacts
```

**API implementation rules:**
- Routes dùng id/URL được encode/path-safe, clip UID có dấu `:` nên nên chọn `clip_uuid` nội bộ trong route thực, giữ full UID trong DB/JSON. Không dùng raw title làm path.
- `process-all` phải idempotent, không tạo TTS trùng vì người dùng refresh.
- `close` chỉ hợp lệ khi không có pending Opus project; nếu incomplete trả `409 BATCH_NOT_READY`.
- `batch_processing` có `dry_run`, budget estimate và stage toggles; UI hiện progress `completed/accepted/discovered`, không chỉ tổng % ảo.
- UI có gallery toàn bộ N clips, mỗi card: preview, duration, source range (nếu biết), story angle, script, voice, status, retries, folder, description/hashtags.

## 12. Cost guard, retries, quota, security

### 12.1 Fan-out cost guard

Trước `process-all`, tính:

```text
expected_batch_extra = Σ over accepted clips
  (Sol text+image inspection_i + Sol script_i + ElevenLabs_i + Opus export_i + local compute_i)

if (source_cost_spent + expected_batch_extra > batch_max_budget):
    return BUDGET_REVIEW_REQUIRED
```

Chi phí estimated không phải giá thực; phải log actual theo provider response / dashboard. Cho người dùng chọn `all usable` hoặc `top K`. Retry TTS tối đa theo config và ghi chi phí mỗi attempt. Có `max_active_tts=2` làm default vận hành bảo thủ, tùy account API rate limit; không coi đây là limit của ElevenLabs.

### 12.2 Failure isolation

| Tình huống | Kết quả bắt buộc |
|---|---|
| Sol source-context fail | Cache error; có thể tạo Opus project theo topic metadata + user approval; không dựng fact/visual timestamps giả |
| 1/3 Opus project fail | Ghi project failed; barrier mở sau khi tất cả terminal, vẫn xử lý clips từ 2 project thành công |
| Opus return 0 clips | `NO_USABLE_CLIPS` report; không tạo script/voice giả |
| Opus return 8 clips nhưng 2 bị crop hỏng | Discovered 8, accepted 6; 6 kịch bản/6 TTS mục tiêu |
| Clip 4 script chứa claim sai | Chỉ clip 4 `NEEDS_SCRIPT_REVIEW`; 5 clip khác chạy bình thường |
| Clip 3 TTS error 429 | Chỉ clip 3 retry với backoff; không regenerate clip khác |
| Clip 2 script sửa sau TTS | Invalidate TTS/mix/subs/render **clip 2**; không ảnh hưởng clip 1/3 |
| Clip 5 nhạc không rõ quyền | Block hoặc review **clip 5**; nguồn có thể cần human global rights review nếu chung giấy phép |
| Bấm process-all lần 2 | Không phát sinh duplicate jobs/artifacts/cost cho jobs đã PASS |
| Batch bị stop | Child terminal/cancelled local, chi phí provider đã dùng vẫn được lưu |

### 12.3 Security/privacy/rights

- API keys local env/secret store, không log keys/signed URLs; tránh SSRF khi tải export URLs; allowlist domain/provider, reject private IP/redirect nguy hiểm.
- Rights ledger source-level + per-clip inheritance có khả năng override nếu chứa nhạc/ảnh/logo bên thứ ba.
- Giữ provenance ở sidecar `source.json/evidence_registry`; nếu loại metadata GPS nhạy cảm khỏi final, đó là vệ sinh quyền riêng tư chứ không thay quyền sử dụng hay originality.
- Không tự động lách kiểm duyệt, không dùng giả mạo vùng tài khoản, không bảo đảm Creator Rewards eligibility.

## 13. Pydantic contracts & validator requirements

Companion files: `local_video_forge_batch_contracts_v2_5.py` + `local_video_forge_sol_source_contracts_v2_6.py` (tham chiếu được khi phát triển app). Các contracts v2.2–v2.4 giữ dùng cho shot/audio/facts; v2.5 là **batch orchestration contracts** và v2.6 là **source metadata + image frame evidence contracts**.

Validation bắt buộc:
- `source_id`, `opus_project_id`, `opus_clip_id` non-empty; `clip_uid` unique; `index_no` unique trong batch; stable sorting.
- Mọi child `clip_uid` xuất hiện trong `discovered_clips` của batch.
- `N_discovered == len(discovered_clips)`; `N_accepted <= N_discovered`; không set `OPUS_BATCH_COMPLETE` khi pending project.
- Một clip `PUBLISH_READY` bắt buộc script/TTS/final + QC PASS + rights VERIFIED + publisher pack + human approval (ngoại lệ ASMR_ONLY được ghi rõ).
- `script.clip_uid == clip.clip_uid`; `tts.clip_uid == clip.clip_uid`; `publish_pack.clip_uid == clip.clip_uid`.
- JSON paths phải nằm trong folder clip tương ứng, không `../` traversal.
- `description_en` không rỗng, hashtag normalized/deduplicated, title không rỗng; claim references valid.
- `script_revision` tăng đơn điệu, regen TTS chỉ khi hash/revision khác, clip states có transitions hợp lệ.

### 13.1 Manifest example

```json
{
  "schema_version": "2.5",
  "batch_id": "batch_001",
  "source_id": "src_001",
  "youtube_url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "opus_batch_status": "OPUS_BATCH_COMPLETE",
  "opus_projects": [
    {"project_id": "opus_P1", "status": "SUCCEEDED", "candidate_window_id": "win_01"}
  ],
  "discovered_clips": [
    {"clip_uid": "src_001:opus_P1:clip_C1", "index_no": 1, "status": "PUBLISH_READY", "folder": "output/clip_001_hammer_forging"},
    {"clip_uid": "src_001:opus_P1:clip_C2", "index_no": 2, "status": "PUBLISH_READY", "folder": "output/clip_002_edge_grinding"},
    {"clip_uid": "src_001:opus_P1:clip_C3", "index_no": 3, "status": "TTS_FAILED", "folder": "output/clip_003_axe_handle"}
  ],
  "counts": {"discovered": 3, "accepted": 3, "script_pass": 3, "voice_pass": 2, "final_pass": 2, "asmr_final_pass": 0},
  "batch_status": "BATCH_PARTIAL"
}
```

## 14. Acceptance tests v2.6 (bao gồm regression v2.5) — phải có trước khi gọi dự án 'DONE'

| ID | Case | Pass condition |
|---|---|---|
| V25-T01 | 1 YouTube → Opus returns 1 usable clip | 1 script, 1 voice, 1 folder, 1 final, 1 description, 1 hashtag file |
| V25-T02 | 1 YouTube → Opus returns 5 usable clips | **5 script khác nhau** gắn 5 clip UIDs; 5 TTS; 5 finals và đủ packs |
| V25-T03 | Opus returns 10, 2 reject by QC | 10 folders/tracks; 8 accepted, 8 child jobs; rejected không có final giả |
| V25-T04 | Opus 2 projects returns overlapping clip IDs | Unique `(project_id, clip_id)`; duplicate không double-processing |
| V25-T05 | Opus jobs pending | Không được bắt đầu kịch bản hàng loạt trước batch barrier |
| V26-T06 | Source metadata nói “lắp cán” nhưng clip chỉ có “rèn đầu” | Script không nói có cảnh lắp cán; fact scope đúng clip |
| V25-T07 | Clip 1 & clip 2 có hành động khác nhau | Hai story angles/voice texts/phụ đề tương ứng khác nhau |
| V25-T08 | Clip 3 failed TTS | Retry clip 3, clips 1/2 không phát sinh API mới |
| V25-T09 | Modify script clip 2 | Chỉ clip 2 downstream invalidated; source/global & Opus unchanged |
| V25-T10 | Clip có music rights unresolved | Block clip, không auto-PUBLISH_READY |
| V25-T11 | Đã có script/TTS/render và restart tool | Resumable, không lặp API call nếu input hashes unchanged |
| V25-T12 | Output folder path includes traversal | Reject unsafe path; files chỉ trong project data root |
| V25-T13 | Thiếu hashtag hoặc description | `PUBLISH_PACK_INCOMPLETE`, không PUBLISH_READY |
| V25-T14 | Per-clip voice is too long | Replan/shorten only that clip, giữ ASMR và constraints |
| V25-T15 | Opus 0 clip / source video blocked | Không tạo output giả, có report và hướng xử lý |
| V25-T16 | Final exports have different source excerpt offsets | Captions/TTS sync theo timeline từng clip, không reuse offsets nguồn |
| V25-T17 | N=20 on low budget | Dry-run cost report + budget guard; không tự gọi 20 TTS quá mức |
| V25-T18 | Explicit ASMR_ONLY exception | Clip không có TTS được phân loại ngoại lệ; không giả count voice |
| V25-T19 | source overlap high between two clips | Editorial warning và tùy chọn choose different angle/skip |
| V25-T20 | Publication pack copied for two different clips | Test fail nếu không clip-specific hoặc claim sai footage |

**Test fixture tối thiểu:** một video xưởng có quyền sử dụng được Opus trả giả lập 0/1/3/5/10 clips; một nguồn 2 jobs khác nhau; ít nhất các case có/không lời Đức, speech+ASMR, nhạc, watermark/caption burn-in, sai footage/source fact, nhiều clip nội dung gần giống nhau.

### 14.1 Tests v2.6 — Sol multimodal migration

| ID | Scenario | Acceptance |
|---|---|---|
| V26-S01 | Không có bất kỳ Google/Gemini API key nào | Pipeline vẫn chạy với `OPENAI_API_KEY`, OpusClip, ElevenLabs, local tools |
| V26-S02 | Source không subtitles và không download MP4 | Source scout báo `METADATA_ONLY`, **không** tự tạo timestamp range hoặc claim thấy cảnh; Opus nhận full YouTube URL |
| V26-S03 | Metadata nói có rèn rìu nhưng Opus trả clip chỉ mài dao | Sol script gắn frame của clip đó, không kể chuyện rèn rìu không thấy |
| V26-S04 | 5 clip Opus khác nhau | Tối thiểu 5 independent frame bundles, 5 transcripts (kể cả rỗng), 5 inspections, 5 scripts, 5 TTS, 5 folders |
| V26-S05 | Sol adapter gửi MP4/audio/YouTube URL như `input_video` | Unit test phải FAIL trước khi gửi API, chỉ cho input_text/input_image |
| V26-S06 | Frame time ngoài duration / thiếu file / path traversal | Validator FAIL, không phát sinh content bogus |
| V26-S07 | Source fact chỉ nằm ở description, clip không cho thấy | Script không khẳng định đó là hành động đang diễn ra |
| V26-S08 | Sol key chưa được cấp quyền 403/404/rate limit | Record error + pause/retry phù hợp; không tự đổi provider, không mất clip assets |
| V26-S09 | N frames lớn, total image token dự toán quá budget | Reduce frames/low detail/ask approval before calling API; never exceed spending guard silently |
| V26-S10 | Per-clip TTS lỗi | Chỉ retry child clip, không lấy source text/Opus clips lại |

**Độ độc lập bắt buộc:** schema v2.6 mô tả `SourceScoutPlanV26` và `ClipEvidenceBundleV26` trước khi gọi Sol; batch contracts v2.5 giữ nguyên, không cần đổi định danh clip hay các output folders.

## 15. Roadmap triển khai thực tế (Sol-only multimodal)

**Phase 0 — API Spike:** Kiểm tra `OPENAI_API_KEY` có quyền `gpt-5.6-sol` và hỗ trợ text+image/structured JSON (KHÔNG native video/audio); test source metadata + subtitle fetch, Opus create → poll → list → HD export N clips, local FFmpeg frame sampler, local ASR, ElevenLabs 2 text và alignment. Lưu vào `capabilities.json`. Không coi subscription ChatGPT UI tương đương API credits.

**Phase 1 — MULTI-CLIP FOUNDATION [P0]:** Source/Batch/Clip DB, Opus batch barrier, enumerate all clips, download, one folder per clip, per-clip status, gallery N clips. Mock test N=0/1/5/10. **Chưa cần TTS** để kiểm count và folder.

**Phase 2 — PER-CLIP SOL VISION + SCRIPT ENGINE [P0]:** Extract sparse timestamped JPEG frames and local audio transcript per clip, source-context retrieval, GPT-5.6 Sol inspection và one-script-per-clip, source evidence, clip-specific edit plan, script QC, versioned revisions. Test 5 clips = 5 scripts đúng footage.

**Phase 3 — PER-CLIP VOICE + RENDER [P0]:** ElevenLabs từng dubbed/commentary segment trong từng clip; bắt buộc Hybrid v2.7, German duck/stem, protected ASMR, voice time sync, FFmpeg final + listening QC/captions per clip. Failure isolation, retry/resume, cost guards.

**Phase 4 — PUBLICATION PACK [P0]:** title, description, hashtags, pack JSON per folder, batch summary, downloadable artifact links, preview gallery, human approval.

**Phase 5 — QUALITY OPTIMIZATION [P1]:** A/B hook, source overlap and script similarity warnings, Most Replayed manual hints, user feedback CSV, rank clips and `TOP_K_USABLE`, hardware benchmark.

### 15.1 Delivery checklist cho coding agent

- [ ] `N` clips dynamically enumerated; `N` never hard-coded.
- [ ] Complete Opus jobs barrier before creating clip scripts.
- [ ] Source metadata/subtitles ingest once + GPT-5.6 Sol source context cache; local FFmpeg frames + ASR + Sol inspection for **every** clip; no native video/audio Sol calls.
- [ ] One independent script & evidence map per accepted clip.
- [ ] ElevenLabs called separately per script; save voice+alignment per clip.
- [ ] One stable folder per discovered clip, final + description + hashtags for all PASS clips.
- [ ] Clip failures don't halt other clips; retry isolated and resumable.
- [ ] Budget, rights, music, export, and fact-check gates enforced.
- [ ] Dashboard gives `discovered / accepted / scripted / voiced / final / failed` live counts.
- [ ] Mock integration fixture proves 5 clips lead to 5 scripts, 5 voices, 5 publication packs.

## 16. Open questions & verification gates (OpenAI/Opus/ElevenLabs)

1. Số clip thực tế do OpusClip tạo cho mỗi project/range **không được bảo đảm**; cần thử trên tài khoản API chính thức.
2. API HD export có thể khác preview clip; adapter phải capability-probe thật. Nếu không lấy được HD clean clip, dừng hoặc fallback tới footage có quyền dùng.
3. Một số tổ hợp `curationPref`/brand template có thể không được chấp nhận; chỉ tin request đã qua smoke test và saved capability snapshot.
4. GPT-5.6 Sol không nhận YouTube URL thành input video; **chỉ** text & still images, cần OpenAI API access và image token budget. Nguồn không có subtitles thì Opus self-curate trước khi local frame inspection; không bịa source visual facts.
5. ElevenLabs limits/pricing/voice_id API entitlement theo tài khoản; thử với TTS vài câu trước khi xử lý N clips.
6. Các video nguồn có thể được xuất nhiều clip nhưng khác nhau rất ít; tối đa hóa **clip có giá trị** thay vì số clip thô; điều kiện original content nền tảng phải xem riêng.

## 17. Tài liệu chính, phân biệt xác thực

- Nền v2.4: `SPEC_Local_Video_Forge_ASMR_v2.4_REVIEWED.md` (đã dùng để hợp nhất v2.5; v2.5 thay phần project 1-clip và multi-output-optional của v2.4).
- Tài liệu người dùng: `DAI_TONG_HOP_BI_THUAT_TIKTOK_DUC_MY_CHINH_THUC_2026.md` (ý tưởng nội dung, **không coi claim lách trùng/RPM/fair use là sự thật**).
- Notion: https://app.notion.com/p/3fa4eb56c52380dabd28df7b74e5e5db
- OpusClip API: https://help.opus.pro/api-reference/quickstart và https://github.com/opus-pro/opus-skills/blob/main/skills/opusclip/references/api-reference.md
- GPT-5.6 Sol (supported modalities & model ID): https://developers.openai.com/api/docs/models/gpt-5.6-sol
- OpenAI vision: https://developers.openai.com/api/docs/guides/images-vision
- OpenAI structured outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- OpenAI speech-to-text (nếu chọn ASR API thay local): https://developers.openai.com/api/docs/guides/speech-to-text
- ElevenLabs: https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps/

**Định nghĩa DONE v2.6 (legacy; tham chiếu mục 19 cho v2.8):** Dán **một URL YouTube**, sau OpusClip nhận được `N` clip hợp lệ thì tool tự tạo **N kịch bản gắn nội dung từng clip, N bản ElevenLabs, N final MP4, N bộ description/hashtags**, lưu **mỗi clip trong một thư mục riêng**, và xuất báo cáo/tình trạng lỗi minh bạch. Không cần Gemini; không gửi MP4 trực tiếp vào model Sol; 1 URL → N output vẫn là tiêu chí quan trọng nhất để coding agent không xây sai.


---

## 18. UPDATE v2.7 — HYBRID SELECTIVE DUBBING + ASMR PROTECTION + STORYTELLING

### 18.1 Quyết định nghiệp vụ bắt buộc cho MỌI clip mới

Bên cạnh mục tiêu fan-out `1 YouTube → N Opus clips → N independent scripts → N voices → N folders`, cập nhật **default per-clip edit mode**: `HYBRID_SELECTIVE_DUB_ASMR_STORY`. Một clip có thể có cả `dub` và `commentary`, cộng nhiều vùng `protected_asmr`.

```text
[Original Opus clip] → [faster-whisper DE transcript + speech timestamps]
                    → [ASMR event detector + reviewer protected intervals]
                    → [GPT-5.6 Sol receives clip keyframes + DE text + verified source facts]
                    → [HybridClipPlan: GermanSpeech[] + VoiceSegment[dub/commentary][] + ProtectedASMR[]]
                    → [ElevenLabs generates EN audio for EACH voice segment]
                    → [Audio engine: -24dB raw DE speech, -7dB ambience during commentary,
                       0dB original workshop in protected raw ASMR intervals]
                    → [QC listen for residual German / missing hammer / narration overlap]
                    → [final.mp4 + audio/mixed_audio.wav + report, in THIS CLIP folder]
```

Do not interpret `[German spoken 05–09s] + [Hammer impacts 07–08s]` as simultaneously solvable by ducking the full audio track: -24dB would weaken hammer. If `protected_asmr` overlaps German speech, block unless a **quality-approved** workshop-only stem exists; do not automatically force output or pretend Demucs guarantees quality. Can relocate dubbed English voice to another window if consistent with meaning and clip.

### 18.2 Rule-based gains and boundaries

| Situation | Raw workshop audio | ElevenLabs EN | Default action |
|---|---|---|---|
| German speech, without significant hammer impact | Attenuate to -24dB with 65ms attack / 145ms release | Dub faithful English | PASS subject to listening-QC |
| Hammer/grind/lathe protected, NO German speech | Preserve at native gain (0dB), avoid additional compression | Silence (no English narration) | PASS |
| Process-transition/handwork interval, without German speech or protected ASMR | Duck background about -7dB while voice speaks | Original factual commentary | PASS |
| German speech and protected hammer coexist | Do not weaken protected ASMR without explicit approval | Delay/replan dub to avoid impact | `NEEDS_REVIEW` unless approved speech-free stem |
| TTS longer than planned window | Do not cut last words | Shorten/regenerate/relocate per clip | BLOCK this child job only |
| Unknown music rights or unverified footage | No export | No export | BLOCK this child job |

`-24 dB` is attenuation of the **whole source audio** during German speech unless a speech-free stem is provided. It is not vocal isolation; German could still be audible. There is no purely deterministic signal processing solution to both erase German and keep coincident hammer sounds in one mixed audio stream without separation/QC or re-recording.

### 18.3 Contracts, module and status

- Source-of-truth contract: `hybrid_audio_contracts_v2_7.HybridClipPlan` with `source_german_speech`, `protected_asmr`, `voice_segments`, rights gate, QC-approved stem marker and DSP gain settings.
- Execution module: `hybrid_audio_engine.process_clip(folder)` or `batch(root)` with per-child fault isolation. A folder contains `clip.mp4`, `audio_plan.json`; outputs `audio/mixed_audio.wav`, `final.mp4`, and `audio_mix_report.json`. Reuse prior publisher pack workflow for `script_en.md`, `description.txt`, `hashtags.txt`, captions.
- As-run test: at least 10 offline tests including actual FFmpeg media, silent render validation, overlong TTS fail, overlaps, deep duck and batch failure isolation. Tests do not imply real ElevenLabs API was used or audio isolation is perceptually perfect.
- If a clip fails to preserve its workshop sound, output `NEEDS_AUDIO_REVIEW`, not `PUBLISH_READY`.
- Persistent setting for all *future* jobs: `config/hybrid_audio_defaults.json` must be read by actual application at new child-job creation time. Old jobs require explicit reprocess; **the source project code/repository must be integrated** before this requirement can affect an already running local app.

### 18.4 Per-clip Sol director system instruction (replaces B-or-C global decision)

```text
You are the clip-specific English documentary editor for Local Video Forge.
INPUT: current Opus clip's timestamped still frames, German ASR segments
with uncertainty markers, source-level facts/evidence, and workshop ASMR
interval candidates. Do not pretend you listened to the audio: ASR and
ASMR event data are prepared by separate audio tools.

Output ONE HybridClipPlan for this clip; do NOT copy other clips' scripts.
DEFAULT mode must be HYBRID_SELECTIVE_DUB_ASMR_STORY.
1. For EVERY reliable German utterance: faithful but natural English dubbed
   text (kind=dub), map exact source speech IDs. If low-confidence source
   transcript, flag for review instead of hallucinating a translation.
2. In visually and technically evidenced transitions that do NOT coincide
   with protected hammer/grind/lathe segments, write concise factual
   English documentary narration (kind=commentary).
3. Preserve the strongest real workshop sounds. No voice window may overlap
   protected_asmr. When German speech and protected impact overlap, plan
   a shifted dub OR require an approved workshop-only stem/human review.
4. No invented years, temperatures, machine tolerances, prices or risks.
5. Speech window must fit actual generated TTS; this is only proposed timing.
6. Output JSON for the strict v2.7 Pydantic schema; do not fabricate
   audio_path or claim the tool already generated audio.
7. Rights/music gates must come from independently verified project data,
   not guessed from frames.
```

### 18.5 Practical implementation / limits

This spec update provides executable `hybrid_audio_engine.py`, Pydantic contracts and offline tests. It is **not** the complete production app: API adapters for YouTube metadata, OpusClip export, GPT-5.6 Sol planning, publishing metadata and UI remain upstream/external. The currently shared v2.6 bundle did not include the app's executable repository, so a real merge requires access to that codebase. ElevenLabs calls are implemented for each voice segment via `with-timestamps` when API key and plan are available, but **not tested live**. No automatic file publication to TikTok occurs.

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
