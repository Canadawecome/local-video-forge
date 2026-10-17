# SPEC CHÍNH THỨC — LOCAL VIDEO FORGE v3.2: CINEMATIC ASMR + ENGLISH STORYTELLING + CLEAN ASMR

**Ngày:** 17/10/2026  
**Trạng thái:** Bản đặc tả sản phẩm thống nhất (authoritative spec) + bản vá renderer offline được đóng gói. **Chưa phải một ứng dụng end-to-end đã kết nối và kiểm thử tất cả API thật.**  
**Thay thế:** v2.12 và toàn bộ chỉ dẫn `SELECTIVE_DUBBING`, `HYBRID_SELECTIVE_DUB_ASMR_STORY` trước đó **làm mặc định**. Lịch sử cũ không được dùng để xác định chức năng mới.  
**Ngôn ngữ đầu ra:** English (US). **Trải nghiệm:** Một URL YouTube → OpusClip N clip → N kịch bản tiếng Anh theo từng clip → N giọng đọc ElevenLabs → N thành phẩm, mỗi clip một thư mục.

---

> **KHÓA YÊU CẦU — FINAL v3.1**  
> **HÌNH:** luôn ưu tiên cảnh thao tác xưởng rèn/kim loại, va đập búa, máy mài, phôi thép, lửa và quá trình phục chế thật.  
> **ÂM:** không còn lời Đức nghe được ở bất kỳ thời điểm nào, kể cả khi giọng Anh đang im lặng; chỉ dùng clean workshop bed đã qua QC (hoặc raw nếu xác nhận không có người nói).  
> **GIỌNG:** một câu chuyện tiếng Anh độc lập do GPT tạo cho **chính clip đó**, ElevenLabs đọc, **không dịch đồng bộ lời Đức**.  
> **MIX:** tiếng xưởng phát liên tục phía dưới lời kể, không dùng speech-keyed ducking hay mute nền mỗi khi voice Anh vang lên.  
> **SUB:** lời Anh có phụ đề đốt trên MP4, Inter Bold 54 px ở 1080px, Y=85%, 1–4 từ mỗi cụm.  
> **FAN-OUT:** 1 link YouTube → OpusClip N clips → N kịch bản, N giọng, N folders, mỗi folder có MP4, script, SRT/ASS, description và hashtags.  
> **BẢN QUYỀN:** nguồn phải có quyền sử dụng phù hợp; lời bình và phụ đề không tự biến cảnh quay của người khác thành nội dung nguyên bản hợp lệ.


## 0. Quyết định bất biến — KHÔNG được coding agent tự thay đổi

| ID | Quy tắc | Hành vi bắt buộc |
|---|---|---|
| F01 | `ENGLISH_STORYTELLING_WITH_CLEAN_ASMR` | **Mode duy nhất mặc định** cho tất cả job mới. Không dịch/lồng giọng Anh tương ứng từng câu tiếng Đức. |
| F02 | `GERMAN_AS_EVIDENCE_ONLY` | Transcript Đức chỉ là **nguồn dữ kiện** để hiểu quá trình, thuật ngữ, kỹ thuật; không phải kịch bản TTS hoặc ràng buộc timecode voice Anh. |
| F03 | `REMOVE_ALL_AUDIBLE_GERMAN` | Nếu nguồn có lời Đức, cần bản **workshop bed sạch lời trên toàn clip** đã qua kiểm tra; không dùng `-24 dB` duck/mute để giả xóa thoại. |
| F04 | `KEEP_REAL_WORKSHOP_ASMR` | Tiếng búa, máy mài, máy tiện, lửa, dụng cụ phải tiếp tục chạy bên dưới lời kể. Không giảm tất cả ambience mỗi lần giọng Anh xuất hiện. |
| F05 | `ONE_CLIP_ONE_STORY` | Mỗi clip Opus hợp lệ có **script riêng dựa trên nội dung của chính nó**, không tạo N kịch bản trước khi có N clip. |
| F06 | `ONE_CLIP_ONE_TTS` | Mỗi clip có TTS riêng, timestamp tiếng Anh riêng; sử dụng ElevenLabs voice được khóa, không tự chọn giọng khác. |
| F07 | `ENGLISH_SUBTITLES_ALWAYS` | Video storytelling nào xuất thành công cũng có **sub tiếng Anh trên MP4** và các file `.srt` + `.ass` bên cạnh. |
| F08 | `SUBTITLE_PROFILE` | 1080x1920: **Inter Bold, 54 px, Y=85%**, giữa ngang; 1–4 từ/cụm; tối đa hai dòng; có thể đổi vị trí theo cảnh qua `caption_regions.json`. |
| F09 | `FANOUT_ALL_VALID` | Nhận mọi clip Opus hợp lệ, không chỉ clip điểm cao nhất; clip hỏng không làm hỏng batch. |
| F10 | `NO_FAKE_QC` | Không có stem sạch/chưa xác nhận tách lời/tiếng búa bị mất/thiếu timing sub → `NEEDS_REVIEW`, **không xuất MP4 thành phẩm**. |
| F11 | `SOURCE_RIGHTS_GATE` | Phải xác minh quyền sử dụng hình/âm thanh trước khi render/publish; metadata/lật gương không thay thế quyền sử dụng. |
| F12 | `MANUAL_APPROVAL` | Tool tạo các asset và gói đăng bài, nhưng **không tự đăng TikTok** và không tuyên bố chắc chắn đủ điều kiện kiếm tiền. |

| F13 | `CINEMATIC_ASMR_EFFECT_PRESET` | Preset mặc định dành cho footage cơ khí: zoom 1.00–1.045 theo vùng ASMR có bằng chứng; grading nhẹ; tuyệt đối không cần hiệu ứng giật, flash, nhiễu hay âm giả. |
| F14 | `VISUAL_ONLY_NO_TIMELINE_DRIFT` | Hiệu ứng v3.2 chỉ dựng lại track hình, giữ nguyên thời gian và FPS. Track gốc và `workshop_clean.wav` vẫn là nguồn audio, ElevenLabs và sub không được dịch thời gian. |
| F15 | `UPSTREAM_EDIT_ONLY_FOR_REORDER` | Result-first, speed-ramp, b-roll insertion, action-matched cuts và before/after timeline là **chỉ dẫn biên tập**; chưa thực thi trên thành phẩm v3.2. Muốn dùng phải recut từ nguồn trước bước story/TTS và tái kiểm tra time-map/stem. |
| F16 | `EFFECT_HASH_QC` | `effect_plan.json` + `effects/video_effects.mp4` + manifest có hash; thay đổi source, plan, duration hoặc frame rate → fail-closed. |

**Chống hồi quy:** Các cấu hình trong SPEC 1.0 như `duck_db = -8`, `ambience_gain = 0.35` hoặc `duck ambience to 30%-40% whenever English speaks` bị **bãi bỏ**. Các trường `speech_ids` cho voice Anh và `dub` cũng bị **bãi bỏ** trong schema v3.1. Không viết lại cơ chế lồng tiếng Đức theo từ/câu dưới tên gọi khác.

## 1. Điều gì đổi so với v2.12?

**Trước (bỏ):** clip chứa tiếng Đức → bóc từng câu → dịch đúng câu → tạo TTS khớp thời gian nói Đức → trộn thêm lời bình → tiếng búa có nguy cơ bị mất trong vùng thoại.

**Bây giờ (bắt buộc):** clip chứa tiếng Đức → xác minh có người nói → tách tiếng nói ra khỏi **toàn track ambience** → kiểm tra âm xưởng còn nguyên → GPT viết câu chuyện **mới, riêng cho nội dung clip** bằng tiếng Anh → ElevenLabs đọc theo cửa sổ kể chuyện thuận nhịp hình → FFmpeg trộn trên tiếng xưởng liên tục + sub EN → QC.

Lợi ích: ít khớp nối thoại, tránh ghép sát môi và mất tự nhiên; có thể kể chuyện ở vùng không có người nói mà vẫn bảo vệ khoảng nghỉ ASMR. **Không có nghĩa là speech separator chắc chắn tách được giọng Đức sạch hoặc giữ 100% tiếng búa trong mọi tình huống.**

## 2. Kiến trúc sản xuất nguồn → N clips

```text
[YOUTUBE URL + QUYỀN SỬ DỤNG + API KEYS + BUDGET]
                |
                v
[SOURCE CONTEXT / FACT SCOUT] — 1 lần / nguồn
    - metadata / mô tả / transcript hợp lệ / fact sheet
    - GPT-5.6 Sol: tóm tắt thông tin kỹ thuật, fact refs
    - KHÔNG giả định Sol đọc trực tiếp URL YouTube hoặc MP4 qua API
                |
                v
[OPUSCLIP API] — gửi URL, ClipAnything, clean-plate template nếu có
                |
                v
[COLLECT ALL OPUS OUTPUTS] → N_discovered clip IDs
    - lấy MP4 + clip transcript/SRT (nếu có)
    - kiểm tra codec, quyền, quality, duration, ASMR viability
                |
                v
[BATCH BARRIER] → N_accepted clip hợp lệ
                |
          for each clip i
                |
                +--- [CLIP ANALYZER] frames + transcript + ASMR map
                |        ├─ Opus clip transcript/SRT trước
                |        └─ Whisper/WhisperX/Scribe chỉ khi thiếu/lệch
                |
                +--- [SMART_EFFECT_PLANNER — CINEMATIC ASMR]
                |        ├─ GPT Sol có thể xuất effect_plan JSON từ frames/action labels
                |        ├─ fallback deterministic: protected_asmr timestamps có sẵn
                |        └─ EFFECT VIDEO ONLY: zoom nhẹ + cinematic grade, giữ timeline
                |
                +--- [SPEECH-FREE WORKSHOP BED]
                |        ├─ nếu không có lời: raw audio (đã duyệt)
                |        └─ nếu có: SAM Audio / AudioShake → clean residual
                |            QC: no German leakage + hammer/grinder preserved
                |
                +--- [GPT-5.6 SOL PER-CLIP STORY PLANNER]
                |        ├─ clip-specific frames + facts with evidence
                |        ├─ English story script + narration windows + ASMR gaps
                |        └─ caption/description/hashtags draft
                |
                +--- [ELEVENLABS — per-clip English story TTS]
                |        └─ separate MP3/WAV + character timestamps
                |
                +--- [LOCAL FFmpeg RENDER]
                |        ├─ lấy track hình đã render effects/video_effects.mp4 (NO AUDIO)
                |        ├─ workshop clean bed từ nguồn original clip, luôn ON
                |        ├─ EN voice placed INDEPENDENTLY from German speech
                |        └─ English ASS/SRT captions, Y=85%, 54px/1080px
                |
                +--- [FINAL QC + HUMAN REVIEW]
                |        └─ final.mp4 + scripts + audio + metadata
                v
[ONE FOLDER PER CLIP] + [BATCH REPORT]
```

**N không cố định:** `N_accepted <= N_discovered`; `N_final <= N_accepted`. Nếu 10 clip đã được Opus xuất nhưng 2 clip lỗi âm thanh, không được lấp bằng kịch bản giả: ghi `N_final=8`, 2 clip chờ review. Trong chế độ batch có thể ưu tiên/giới hạn credit bằng `budget_cap` nhưng không được im lặng bỏ clip còn lại.

## 3. Source-level Scout (GPT-5.6 Sol, không Gemini)

Dữ liệu đọc từ nguồn (nếu có quyền truy cập): YouTube title, description, thông tin tác giả, phụ đề, hình thumbnail, fact_sheet của người dùng và bằng chứng kỹ thuật. Model tạo `source_context.json`:

```json
{
  "source_id":"src_001",
  "topic":"blacksmithing / tool forging",
  "facts":[
    {"id":"fact_01","claim":"example technical fact","evidence_ref":"description:line_2","confidence":"source_claim"}
  ],
  "uncertainties":["actual material grade unverified"],
  "suggested_clip_prompts":["close-up forging action; metal striking an anvil"]
}
```

Sol **không tự nhận** đã nhìn hết 20 phút YouTube từ URL. Nếu cần hiểu hình ảnh, phải dùng ảnh trích từ clip thực tế và timestamps do hệ thống trích xuất. Model phải được cấu hình bằng `OPENAI_MODEL` và kiểm tra quyền API thực tế ở Phase 0. Không hardcode tính năng video input khi endpoint không hỗ trợ.

## 4. OpusClip import, transcript-first và fan-out

1. Tạo một hoặc nhiều project OpusClip từ YouTube URL, dùng preset sạch khi tài khoản/API hỗ trợ. **Kiểm chứng tên trường API trước khi gọi**; không giả định `brandTemplateId` đồng nghĩa clean-plate tuyệt đối.
2. Chờ job hoàn tất, lấy toàn bộ clip IDs và MP4 hợp lệ, hash SHA-256, tránh clip trùng bytes và đánh dấu clip quá giống nội dung để editor xem.
3. Nếu Opus trả transcript/SRT **trùng timeline clip**, dùng để hiểu câu tiếng Đức, nhận diện vùng nói và facts. Nếu chỉ có transcript video nguồn, không gán thẳng source timestamps vào clip đã reorder. Cần time-map hoặc căn chỉnh.
4. Nếu Opus không trả transcript hoặc timestamp lệch: dùng Whisper/WhisperX/Scribe **chỉ trên clip thiếu**, không trên cả batch vô ích.
5. Transcript không đủ để kết luận đã **xóa được** giọng Đức. Đây là bước riêng của Audio Separation và QC.
6. Import các MP4 đã có với `ingest_opus_batch_v31.py`; utility này không thay thế Opus API client.

## 5. German Voice Removal — Speech-free Bed

### 5.1 Trạng thái đầu vào

`german_speech_status`: `CONFIRMED_PRESENT | CONFIRMED_ABSENT | UNCERTAIN`.

- `UNCERTAIN`: chặn render và yêu cầu phân tích/nghe thử.
- `CONFIRMED_ABSENT`: chỉ dùng raw audio nếu `source_speech_absence_confirmed=true` được kiểm tra và gắn `source_sha256` đúng.
- `CONFIRMED_PRESENT`: **bắt buộc** có `audio/workshop_clean.wav` full-length và `audio/replacement_qc.json` đã duyệt. Trong v3.1, audio bed thành phẩm = **toàn bộ clean residual**, không đổi qua raw tùy theo German word timestamps (tránh lọt lời Đức ở khoảng tưởng như không nói).

### 5.2 Tách lời

Adapter primary: Meta SAM Audio text-prompt/speech selection nếu thiết bị được hỗ trợ, checkpoint được cấp quyền và GPU đủ năng lực; fallback dịch vụ: AudioShake Dialogue/Effects nếu API/account hỗ trợ. Không coi hai adapter đồng nhất kết quả. **Đây là kế hoạch tích hợp, chưa có client separator chạy thật trong package.**

Đầu ra: `speech_target.wav` (tham khảo/không xuất bản), `workshop_clean.wav` (full-duration), report `separation.json` gồm model/version, thời gian, sample rate, hàm băm, trạng thái.

### 5.3 Fail-closed QC (P0)

- Kiểm tra clip/clean duration, time alignment, sample rate, không lỗi decode.
- Đánh giá lời Đức còn rò rỉ bằng nghe thử và/hoặc ASR độc lập **trên clean bed**; ASR rỗng không phải bằng chứng tuyệt đối.
- So sánh phổ âm, transient và mức năng lượng ở vị trí tiếng búa/mài đã đánh dấu. Nếu tiếng búa mất, `NEEDS_ASMR_REVIEW`.
- Không thay bằng đoạn im lặng và không chèn Foley giả mặc định khi separator lỗi; thử adapter khác hoặc chọn clip khác.
- Chỉ ghi `german_voice_absent=true`, `asmr_preserved=true`, `reviewed_by` sau khi kiểm tra, gắn hash SHA-256 của source và residual. Mất hiệu lực nếu file thay đổi.

**Quan trọng:** Quy tắc "tắt tiếng Đức" không được diễn dịch là `volume=0` cho audio gốc, vì như vậy tiếng búa mất theo.

## 6. Storytelling per clip — không dịch theo câu Đức

### 6.1 Inputs clip-level

`clip.mp4`, frames sampled có timecode, cảnh/chuyển động/ASMR map, Opus transcript/Whisper transcript (để hiểu facts), `source_context.json`, source evidence refs, video length và quyền sử dụng. Chỉ được bình luận những hình/hoạt động và kỹ thuật có căn cứ ở clip hoặc source facts; không tự thêm thông số thép, nhiệt độ, tuổi đồ vật hoặc giá tiền không có bằng chứng.

### 6.2 Sản phẩm AI phải trả

`story_plan.json`: `mode=ENGLISH_STORYTELLING_WITH_CLEAN_ASMR`, `source_german_speech` cho báo cáo, `narration_segments` gồm time window **tự chọn theo nhịp kể** không dựa vào German utterance windows, `protected_asmr`, `evidence_refs`. `script_en.md` mô tả câu chuyện; `script_tts.txt` **chỉ chứa nội dung lời sẽ đọc**, không có bracket/stage directions. `description.txt` + `hashtags.txt` bằng tiếng Anh Mỹ, bám nội dung clip, không bịa yếu tố giật gân.

Một clip dài ~75 giây có thể bắt đầu ở 85–110 từ đọc tiếng Anh, nhưng đây là **khoảng thử nghiệm**, không phải quota cưỡng chế. TTS phải vừa cửa sổ sau khi sinh và model phải bố trí các khoảng chỉ nghe ASMR, đặc biệt cú búa, tia lửa, đánh bóng, kết quả cuối. Có thể thuyết minh nhẹ lúc làm việc nếu tiếng xưởng vẫn rõ. Đầu video ưu tiên visual hook, giữa giải thích quá trình, cuối payoff dựa trên cảnh thật.

### 6.3 Sự khác nhau giữa N script

Script của clip A chỉ sử dụng những cảnh clip A đang có, không lấy facts của clip B để đặt vào A. Các clip lặp cảnh phải được flag `SIMILARITY_REVIEW` để tránh N nội dung gần như giống nhau; không thay từ đồng nghĩa để gọi là script mới.

### 6.4 System instruction cần có trong AI planner

```text
You are a documentary storyteller for an American audience.
Input: a specific 9:16 clip, its time-coded still frames, optional German
transcript as fact evidence, and a source evidence ledger.
Write ONE independent English documentary story grounded in THIS clip.
Do NOT translate line-by-line or synchronize narration with German speech.
Generate timestamped English narration windows, preserve key ASMR moments,
and never invent technical measurements, material grades, ages, prices,
participants, or events. Every specific factual claim cites evidence_refs.
Produce structured JSON matching StorytellingPlan v3.1.
```

**Tính năng Sol:** Thiết kế chỉ phụ thuộc text/images + Structured Outputs khi endpoint cho phép. Không gửi URL YouTube/MP4 như một video input được hỗ trợ nếu API đó chưa có tính năng ấy. Chạy API capability smoke test trước.

## 7. ElevenLabs TTS — English Story

- Voice ID khóa: `QIhD5ivPGEoYZQDocuHI` (tên Adam theo lựa chọn người dùng; kiểm tra ID thật và quyền API của tài khoản). Model mặc định: `eleven_multilingual_v2`, có thể đổi nếu người dùng phê duyệt.
- Đọc từng `narration_segment`, không có `speech_ids`, không có `dub`, không cần tính khoảng German-original ↔ English-dub.
- Dùng endpoint có timestamps hoặc align English TTS từ nguồn đã tạo. **Sub dựa chính xác trên TTS thực tế**, không dựa transcript Đức.
- Measure duration; nếu quá `end-start`, rút script/hạ mật độ đọc có kiểm soát hoặc đổi window; không cắt mất từ cuối.
- Cache key: `script + voice_id + model_id + settings + clip_uid`. Retry riêng clip lỗi, không tiêu tốn toàn batch lần nữa.

## 8. Mixer — ASMR dưới giọng Anh mọi lúc

### 8.1 Công thức bắt buộc

```text
if german_speech_status == CONFIRMED_PRESENT:
    workshop_bed = approved_full_length_workshop_clean.wav
else if german_speech_status == CONFIRMED_ABSENT and source_absence_QC:
    workshop_bed = original_audio_from_opus_clip
else:
    FAIL(NEEDS_AUDIO_REVIEW)

english_voice = placement_of_independent_ElevenLabs_story_segments
premix = workshop_bed + english_voice
# NO ambience duck keyed to English speech
# NO German-to-English dubbing mappings
# Prevent clipping; if gain reduction would crush hammer impacts -> review
```

- FFmpeg/Python chuẩn hóa sample rate và channels **trước** mix. `workshop_bed` dài trọn video, không mute ở bất kỳ cửa sổ giọng Anh nào.
- Không mặc định sidechaincompress, `duck_db`, hay hệ số âm xưởng 0.35; có thể thiết kế compressor tự động **riêng** sau khi đã kiểm chứng, không thay nguyên tắc v3.
- Khi tiếng búa rất lớn và voice yếu, cân giọng đọc ở stage voice, kiểm tra clip headroom. Không giảm toàn bộ bed để bảo đảm voice nghe nổi.
- Export `audio/workshop_bed_always_on.wav`, `audio/english_voice_only.wav`, `audio/english_mix.wav` để debug.
- QC track final MP4 bằng decode lại: waveform/peak/LUFS/true peak, kiểm tra âm bed trong vùng có lời English; phép trừ AAC chỉ là heuristic, không bảo đảm chất lượng cảm nhận.
- Reference mastering tham khảo từ video mẫu: ~`-15.8 LUFS`, peak `-1.23 dBTP`, **không phải mức cứng buộc mọi video**.

## 8A. Smart Effect Planner v3.2 — Preset `CINEMATIC_ASMR` (MỚI)

### 8A.1 Mục tiêu

Tăng chất lượng xem footage rèn búa, mài kim loại, CNC và phục chế nhưng không làm mất tiếng búa hay phá timecode kể chuyện. Thứ tự công đoạn sau khi Opus tạo clip:

```text
clip.mp4 + scene/action map + protected_asmr[]
      ↓
GPT-5.6 Sol: đề xuất effect_plan.json (JSON strict) HOẶC
smart_effect_planner_v32.py: deterministic fallback dựa trên nhãn ASMR có thật
      ↓
smart_effect_contracts_v32.py: Pydantic validate
      ↓
smart_effect_render_v32.py: FFmpeg output VIDEO-ONLY, nguồn âm nguyên vẹn
      ↓
effects/video_effects.mp4 + effects/video_effects_manifest.json
      ↓
storytelling_render_v32.py:
  video từ effects/video_effects.mp4
  audio từ `clip.mp4` hoặc `audio/workshop_clean.wav` đã duyệt
  English voice + captions_en.ass from ElevenLabs timestamps
      ↓
final.mp4 (English Storytelling + Clean Workshop ASMR + English sub)
```

### 8A.2 Tính năng được code thực thi ở v3.2

| Feature | Mặc định / ràng buộc | Trạng thái |
|---|---|---|
| Dynamic Micro-Zoom | Tại nhiều nhất 4 vùng hành động ASMR có evidence trong fallback, tối đa 8 vùng hợp lệ trong plan; thang zoom 1.00 → tối đa 1.05 → 1.00; 0.65–3.5s; không mất tay/búa trong crop | **Có code render FFmpeg** |
| Cinematic Color Enhance | Contrast=1.04, saturation=1.035, brightness=0; bounded trong Pydantic, không giả lập lửa/khói | **Có code render FFmpeg** |
| Visual-only effect pre-render | FFmpeg `-an`; giữ nguyên fps và thời lượng trong dung sai nhỏ; mỗi effect output hash-bound với input/plan | **Có code render + verify** |
| Effect batch isolation | Clip lỗi `NEEDS_REVIEW`; không render nhầm source/effect cũ | **Có qua v3.2 storytelling batch** |
| English captions | Inter Bold, 54 px/1080p, Y=85%, 1–4 từ/cụm, timing từ ElevenLabs | **Giữ v3.1, test lại** |
| Clean ASMR | Nếu có giọng Đức phải có clean bed được duyệt; không duck theo English voice | **Giữ v3.1, test lại** |

**Fallback không đoán nội dung:** `smart_effect_planner_v32.py` chỉ đặt micro-zoom ở timestamps `protected_asmr` đã có trong story plan; mặc định center `(0.5,0.5)` (người dùng có thể điều chỉnh `center_x/y` trong effect plan). Nếu không có vùng ASMR đã đánh dấu, chỉ áp dụng color grading nhẹ, không tự bịa điểm rèn búa. Model GPT có thể tạo effect plan thay cho fallback sau khi kiểm tra bằng chứng và schema, nhưng bộ ZIP **chưa có GPT API client tự sinh effect plan**.

### 8A.3 Các hiệu ứng chỉ là gợi ý biên tập, KHÔNG được giả vờ đã render

| Feature | Chiến lược an toàn | Trạng thái |
|---|---|---|
| Result-First Hook | GPT đánh dấu cảnh tốt nhất và gửi gợi ý sang OpusClip hoặc editor **trước** khi dựng script; nếu recut nguồn phải re-run audio/voice/sub maps | `result_first_hook.status=REQUIRES_UPSTREAM_RECUT` (advisory only) |
| Action-Matched Cut | Đặt điểm cắt theo cú búa/chuyển động trên footage gốc; không xóa/đảo frame sau khi đã có TTS | Planned upstream, chưa có code auto-recut |
| Smart Speed Ramp | Chỉ khi có media time-warp EDL, audio stretch đúng sync, kiểm tra hammer transient và caption alignment | **Off**, không chèn mặc định |
| B-roll Insert | Dùng footage được cấp phép, dựng từ source cùng timeline trước bước voice | Planned upstream |
| Before/After Reveal | Chỉ nếu nguồn có cặp cảnh trước/sau có thật, kế hoạch dựng có evidence | Planned upstream |
| Seamless Loop | Chuyển cảnh tự nhiên nếu hợp footage, không chèn màn đen ép loop | Planned upstream |

Tất cả thay đổi thời lượng/thứ tự cần **rời pipeline time-preserving v3.2**, recut clip trước, tạo `source→output` map và duyệt lại full-length `workshop_clean.wav` + thuyết minh/caption timing; **cấm dùng filter video-only** để ngụy tạo hành động mà âm thanh không khớp. Các mẹo như mirror, drop-frame, thay metadata, noise overlay nhằm qua kiểm tra trùng lặp không phải hiệu ứng mặc định hoặc cách bảo đảm tính nguyên bản.

### 8A.4 Hợp đồng JSON `effect_plan.json` và sản phẩm

```json
{
  "schema_version": "3.2",
  "preset": "CINEMATIC_ASMR",
  "source_clip_sha256": "<64-character SHA-256 from clip.mp4>",
  "duration_seconds": 75.0,
  "timeline_policy": "PRESERVE_SOURCE_TIMECODES",
  "audio_policy": "NO_AUDIO_MODIFICATION",
  "grading": {"contrast":1.04,"saturation":1.035,"brightness":0},
  "micro_zooms": [
    {"start":12.0,"end":14.0,"peak_scale":1.045,
     "center_x":0.5,"center_y":0.5,"evidence_ref":"protected_asmr:hammer@12.30"}
  ],
  "result_first_hook": null,
  "storyboard_notes": ["Keep real hammer strikes intact"]
}
```

Không dùng giá trị hash placeholder này để render: phải tính thật. Output `effects/video_effects_manifest.json` ghi source+plan+effect hashes, duration, FPS, trạng thái no-audio, và xác nhận hook suggestions **chưa áp dụng**. Khi đổi `clip.mp4` hoặc plan phải re-render effects; không được tự fallback sang video chưa hiệu ứng mà giả báo preset đã chạy.

### 8A.5 Hợp nhất pipeline / thứ tự commands

```bash
# Cài dependencies và FFmpeg/ffprobe (libass cho English ASS burn-in)
python -m pip install -r requirements.txt

# Trong mỗi folder đã có clip.mp4 và story_plan.json (protected_asmr có timestamps thật)
python smart_effect_planner_v32.py --folder /path/to/clip_001
python smart_effect_render_v32.py process --folder /path/to/clip_001
python storytelling_render_v32.py process --folder /path/to/clip_001

# Dùng một lệnh final renderer cũng được: nếu chưa có effect_plan,
# v3.2 sẽ tạo fallback; nếu chưa có visual_effects.mp4 sẽ render video-only.
# Nếu effect plan đã có nhưng outdated, renderer CHẶN thay vì bỏ qua.
python storytelling_render_v32.py batch --root /path/to/source_batch

# Tests offline (bao gồm hồi quy v3.1)
PYTHONPATH=. pytest -q tests
```

**V3.2 không thêm API client OpusClip, GPT, ElevenLabs, SAM Audio / AudioShake.** Những adapter đó vẫn là phần công việc phải tích hợp từ v3.1. Renderer hoạt động với MP4, approved clean bed, English TTS+alignment và story plan đã được chuẩn bị. Tests chỉ xác minh code/timebase/QC, không chứng minh khả năng giữ tiếng búa của một separator trên video Đức thật.

## 9. English subtitle bắt buộc

| Setting | Default |
|---|---|
| Tỉ lệ khung hình | 9:16, 1080×1920 |
| Font | Inter Bold (có fallback nếu máy chưa có) |
| Font size | **54 px tại 1080px** (`font_size = 0.05 × width`) |
| Vị trí | **85% chiều cao từ trên xuống**, bottom-centered |
| Nội dung | 1–4 từ/cụm, tối đa 28 ký tự/cụm, ngắt theo dấu câu/khoảng nghỉ |
| Dòng | Tối đa hai dòng |
| Màu | Trắng, viền đen |
| Adaptive layout | Tùy file `caption_regions.json` theo các cảnh crop/blur |
| File | `captions_en.srt`, `captions_en.ass`, **burned into final.mp4** |

Sub chỉ hiển thị lời **thực sự được ElevenLabs đọc**. Cảnh không có voice thì không tạo phụ đề thoại. Khi font Inter không có, FFmpeg/libass có thể thay thế; QC cần kiểm tra font thực tế trên máy. Không tự dời chữ xuống khu vực nút TikTok quá thấp.

## 10. Schema clip-level v3.1 (implemented)

`storytelling_contracts_v31.py` là hợp đồng dữ liệu mới. Các trường chính:

```json
{
  "schema_version":"3.1",
  "mode":"ENGLISH_STORYTELLING_WITH_CLEAN_ASMR",
  "clip_uid":"clip_001",
  "rights_status":"VERIFIED",
  "music_rights_status":"NO_MUSIC",
  "german_speech_status":"CONFIRMED_PRESENT",
  "source_german_speech":[{"id":"de1","start":10.3,"end":12.8,"text_de":"..."}],
  "approved_workshop_stem_path":"audio/workshop_clean.wav",
  "workshop_stem_qc_passed":true,
  "protected_asmr":[{"start":14.4,"end":16.1,"kind":"hammer"}],
  "narration_segments":[
    {"id":"st1","role":"hook","start":0.5,"end":4.2,
     "text_en":"This handmade blade begins as a glowing bar of steel.",
     "audio_path":"audio/tts/st1.wav","evidence_refs":["shot_001"]}
  ],
  "settings":{"voice_gain_db":0,"peak_ceiling_dbfs":-1.0},
  "voice_id":"QIhD5ivPGEoYZQDocuHI",
  "tts_model_id":"eleven_multilingual_v2"
}
```

**Không có `dialogue_mapping`, `speech_ids`, `kind=dub`, `commentary_duck_db` trong schema v3.1.** Trường `source_german_speech` chỉ dùng báo cáo/nguồn thông tin, không quyết định đặt TTS ở đâu.

## 11. File/folder contract

```text
output_root/
  source_<source_id>/
    source_context.json                # 1 lần/YouTube
    source_evidence.json               # facts + provenance
    opus_jobs.json / opus_results.json # nếu adapter Opus có
    batch_report.json                  # status N discovered / N accepted / N final
    render_preferences.json            # common defaults toàn batch
    clip_001_<hash>/
      clip.mp4                          # clip clean plate từ Opus
      import_manifest.json
      story_plan.json                  # schema v3.1
      caption_regions.json            # optional
      effect_plan.json                # JSON strict SmartEffectPlan v3.2
      effects/
        video_effects.mp4             # video-only, không có audio stream
        video_effects_manifest.json   # hash + FPS + timeline validation
      script_en.md
      script_tts.txt
      description.txt
      hashtags.txt
      audio/
        source.wav                     # optional debug
        workshop_clean.wav            # approved full-length residual if German
        speech_target.wav             # optional diagnostic, NEVER in final
        replacement_qc.json           # manual/source hash QC
        workshop_bed_always_on.wav
        english_voice_only.wav
        english_mix.wav
        tts/story_001.wav
        tts/story_001.alignment.json
      captions_en.srt
      captions_en.ass
      final.mp4
      qc_report.json
      publish_pack.json                # assembled by orchestration layer
      logs/
    clip_002_<hash>/
      ...
```

`description.txt` và `hashtags.txt` riêng cho mỗi clip. `publish_pack.json` có tối thiểu caption, hashtags, source credit nếu cần, clip_id, rights/ref, status. `validate_publish_pack_v31.py` kiểm tra file và tính nhất quán; chỉ báo `READY_FOR_HUMAN_REVIEW`, **không tự post**.

## 12. API/workflow orchestration (thiết kế cần implement)

| Endpoint/command | Việc làm |
|---|---|
| `POST /sources` | YouTube URL + rights + budget, tạo source project |
| `POST /sources/{id}/scout` | GPT Sol phân tích text/facts nguồn, không native YouTube |
| `POST /sources/{id}/opus-jobs` | Request OpusClip; handle polling/webhook tùy API |
| `POST /sources/{id}/collect-clips` | Nhận/kiểm tra toàn bộ outputs, fanout N clips |
| `POST /clips/{id}/inspect` | Frames + transcript-first + ASMR windows |
| `POST /clips/{id}/separate-speech` | SAM Audio/AudioShake, xuất full residual và QC yêu cầu |
| `POST /clips/{id}/story` | GPT Sol viết script JSON riêng từng clip |
| `POST /clips/{id}/effects/plan` | GPT Sol frame/evidence → `SmartEffectPlan v3.2` (adapter tương lai); deterministic fallback đã có |
| `POST /clips/{id}/effects/render` | FFmpeg tạo `effects/video_effects.mp4` video-only, hash/timebase QC; module đã có |
| `POST /clips/{id}/voice` | ElevenLabs tạo timed English narration |
| `POST /clips/{id}/render` | `storytelling_render_v32.py process --folder …` |
| `POST /clips/{id}/qc` | Audio/video/rights/ASMR/sub/facts check |
| `POST /sources/{id}/render-batch` | N child jobs độc lập; retry lỗi từng clip |
| `GET /sources/{id}/report` | clip status/cost/error/output |

**Batch state:** `SOURCE_READY → OPUS_RUNNING → CLIPS_COLLECTED → CLIP_INSPECTED → SPEECH_BED_APPROVED → STORY_APPROVED → TTS_READY → RENDERED → QC_REVIEW → HUMAN_APPROVED` hoặc `BLOCKED_*`. Clip khác vẫn xử lý nếu một clip bị blocked.

## 13. Cost, retry, secrets, reproducibility

- API credits độc lập với subscription ChatGPT. Kiểm tra OpenAI model ID/capabilities, Opus API entitlement, ElevenLabs voice ID/timestamps, separator device/API trước khi viết production adapter.
- Secrets trong `.env`, không đưa key vào manifest/project ZIP.
- Cache `source_context` một lần mỗi nguồn; cache asset theo hash + version/prompt/settings, TTS cache theo clip + script + voice profile.
- Store timestamps source vs Opus clip vs output separately, không tự đoán map timeline.
- Clip failure isolation và retry idempotent. Log FFmpeg args/stderr nếu lỗi, không đánh dấu thành công khi thiếu stem hoặc caption.
- Quyền nhạc gốc, video gốc và quyền tái sử dụng là gate riêng. Fair Use/phụ đề/lời bình mới **không tự động** biến nguồn của người khác thành nội dung được quyền phát hành hay đủ điều kiện Creator Rewards.

## 14. Chặn lỗi và nghiệm thu bắt buộc

**P0 functional:**

1. 1 video nguồn → có thể ingest N clip riêng; số N lấy thực tế từ outputs, không đặt cứng.
2. Với clip có tiếng Đức: thiếu clean residual, thiếu QC, hash sai → không render. Bản export không sử dụng raw audio chứa tiếng Đức.
3. Với clip không có tiếng Đức: raw ASMR chỉ được giữ nếu đã xác nhận âm nguồn không chứa lời.
4. Giọng Anh hoàn toàn là `narration_segments` tùy theo **nhịp câu chuyện**, không có mapping sang German words.
5. Tiếng xưởng tồn tại ngay cả khi giọng Anh nói; không áp blanket duck.
6. Tiếng búa biến mất/suy giảm đáng ngờ sau separation → flag, chặn xuất cho đến khi có review/thay separator.
7. `captions_en.srt` và `captions_en.ass` từ TTS thực; sub burned trên MP4; font 54 px tương ứng 1080p, Y=85%, 1–4 từ/cụm.
8. Clip 3 lỗi audio không làm clip 1/2 mất final; rerun chỉ clip 3.
9. Mỗi clip có description + hashtag tiếng Anh riêng, đúng nội dung. Validator kiểm tra tồn tại và nhất quán, người biên tập duyệt tính hấp dẫn/chính xác.
10. Human preview xác nhận không nghe Đức còn sót, nhịp kể không đè khoảnh khắc quan trọng, subtitle và ASMR tự nhiên. Test synthetic không thay thế nghe thử thực tế.

**P1:** near-duplicate similarity (trên nội dung clips), A/B hook, upload analytics tùy chọn, review UI waveform/sub safe-zone, publish pack UI.

## 15. Delivery & trạng thái kỹ thuật chính xác

**Đã có trong gói v3.2 (giữ tương thích schema Storytelling v3.1):**

- `storytelling_contracts_v31.py`: schema thực thi nghiêm ngặt, không còn chế độ dubbing.
- `storytelling_render_v32.py`: renderer theo full clean bed + narration tự do; xuất English SRT/ASS + burned sub, ASMR premix, báo cáo loudness/QC, batch độc lập.
- `ingest_opus_batch_v31.py`: nhận **các MP4 Opus đã tải sẵn** và fan-out N folder, hash/dedupe/rights review flag.
- `validate_publish_pack_v31.py`: phát hiện output thiếu assets/description/hashtags và script lệch plan.
- `smart_effect_contracts_v32.py`: strict visual-only JSON bounds; không nhận speed/duck/stale plan.
- `smart_effect_planner_v32.py`: tạo effect_plan có căn cứ từ protected ASMR windows.
- `smart_effect_render_v32.py`: render micro-zoom & grade video-only, assert no-audio, giữ timebase, kiểm hash.
- Bộ test offline contract/FFmpeg (v3.1 regression + v3.2 effects).

**CHƯA có / phải nối vào repo thực tế:** Opus API client (create/poll/export/download), source metadata & transcript access adapters, GPT source+per-clip vision planning, actual SAM Audio/AudioShake connector, ElevenLabs request/voice API, tự động tạo description/hashtags, UI và database. `storytelling_render_v32.py` nhận **assets đã được tạo và kiểm chứng**, không phải app gọi tất cả provider chỉ từ URL. Cấm coding agent tuyên bố "đã chạy được one-click" chỉ vì offline tests pass.

## 16. Triển khai theo phases

| Phase | Thực hiện | Exit criteria |
|---|---|---|
| 0 — Provider Spike | Thử 1 nguồn/1 clip trên tài khoản thật, kiểm tra API và model IDs | JSON response sample, clip exports, timing, quyền, ngân sách thực |
| 1 — Speech Bed | Kết nối SAM Audio / AudioShake và QC giọng Đức/tiếng búa | Có clean bed nghe được, âm búa được giữ, không leak lời Đức |
| 2 — Story Builder | GPT clip-specific evidence/story JSON, ElevenLabs timed TTS | 1 clip → 1 câu chuyện mới, không dịch từng lời Đức |
| 3 — Render & Pack | Ghép renderer v3, sub, description, hashtags, QC | 1 clip đạt đủ output theo mục 11 |
| 4 — Full Fan-out | Opus N clips tự động + state machine + resume + dashboard | 1 nguồn → N clips → N thành phẩm độc lập |

### Câu lệnh smoke test offline

```bash
python -m pip install pydantic numpy soundfile pytest pillow
# Máy cần FFmpeg/ffprobe và ffmpeg build có libass cho subtitle.
PYTHONPATH=. pytest -q tests

# Import MP4s đã xuất từ OpusClip, không tự gọi Opus:
python ingest_opus_batch_v31.py \
  --clips-dir /path/to/opus_exports --output-root /path/to/batch \
  --rights-reviewed --source-youtube-url 'https://www.youtube.com/watch?v=...'

# Sau khi điền story_plan.json, approved audio residual/QC, ElevenLabs files/alignment:
python storytelling_render_v32.py process --folder /path/to/batch/clip_001_<hash>
python storytelling_render_v32.py batch --root /path/to/batch
python validate_publish_pack_v31.py --folder /path/to/batch/clip_001_<hash>
```

**Kết luận triển khai:** v3.2 thêm preset visual-only Cinematic ASMR. Chế độ giọng vẫn là **storytelling tiếng Anh, không phải dubbing**. Transcript tiếng Đức phục vụ hiểu bối cảnh; tiếng Đức không xuất hiện ở âm thanh thành phẩm; tiếng búa/ASMR là lớp nền liên tục được kiểm chứng. Các kịch bản, giọng, phụ đề và thông tin đăng bài được tạo **riêng cho từng clip**.


## 17. Khóa giao diện tích hợp và nghiệm thu bổ sung (v3.1 FINAL)

### 17.1 Audio separator contract bắt buộc cho coding agent

```text
Input: clip.mp4, audio nguồn, speaker regions đã đối chiếu, vùng protected ASMR
Output: audio/workshop_clean.wav (full timeline), audio/speech_target.wav,
        audio/separation_report.json, audio/replacement_qc.json
```

- Đầu ra sạch giọng Đức phải đủ chiều dài clip và đồng bộ sample chính xác; không được chèn phần raw có lời Đức vào các khoảng rỗng.
- Tách giọng người phải thực hiện từ tín hiệu audio nguồn, **không chỉ xóa các câu có trong transcript**. Transcript/SRT dùng hỗ trợ tìm vùng thoại và tra cứu kỹ thuật, không bảo đảm dò hết lời nói.
- Nếu separator làm mất tiếng búa, sinh trạng thái `NEEDS_ASMR_REVIEW` và chuyển sang adapter khác hoặc editor xử lý; **không mute toàn bộ audio để đạt tiêu chí không còn tiếng Đức**.
- QC gồm nghe residual riêng, so sánh tiếng va đập trước/sau, nghe đoạn voice nói chồng tiếng máy và nghe toàn bộ phần âm còn lại; ASR không nghe được tiếng Đức **không đồng nghĩa chứng minh sạch tuyệt đối**.
- Đặt `approved=true` và reviewer/hash sau khi kiểm chứng; tool không tự ký duyệt dựa duy nhất trên ASR rỗng.

### 17.2 Quy tắc ASMR/Voice mix

**Không được cấu hình** `ambience_gain=0`, `duck_db=-8`, `background_volume=0.35`, `sidechaincompress` theo giọng Anh hoặc tắt track xưởng mỗi khi ElevenLabs nói. `0 dB gain` có nghĩa không đổi mức âm; khác với `amplitude=0` (tắt tiếng).

`final_audio = approved_clean_workshop_bed + independently_timed_english_voice`, sau đó xử lý clip-peak/headroom có kiểm chứng. Nếu để chống clipping phải giảm toàn bộ master đến mức mất sức mạnh tiếng búa, chặn xuất và yêu cầu cân giọng/tách lại.

### 17.3 Visual-first acceptance

Phân tích cảnh từ **MP4 mà Opus xuất thật**, không giả định prompt Opus sẽ đáp ứng đầy đủ. Ưu tiên shot `HAMMER_STRIKE`, `GRINDING`, `CUTTING`, `FORGING`, `METAL_TURNING`, `RESTORATION_ACTION`, `RESULT_REVEAL`. Tùy nội dung nguồn có quyền, cho phép loại clip quá nhiều talking-head/cảnh trống. Không bắt buộc mọi clip phải có đủ tất cả loại cảnh; cần đủ hành động thực tế để câu chuyện bám được hình.

### 17.4 Không tuyên bố khả năng chưa tích hợp

Gói Python v3.1 **có** renderer offline, schema, importer MP4 đã xuất, kiểm tra assets/test. **Chưa có** adapter chạy thật cho SAM Audio/AudioShake, OpusClip, GPT-5.6 Sol và ElevenLabs; bản thử nghiệm không xác nhận separator đã xóa tiếng Đức trong video xưởng thực tế. Phải nối API/SDK vào repo ứng dụng, chạy thử trên clip thật trước khi coi là triển khai end-to-end thành công.


## 18. Ghi chú nâng cấp v3.2 và kiểm tra hiệu ứng với footage thực

- Giữ mọi điều kiện duyệt nguồn, no German, Clean ASMR, phụ đề Y=85%/54px. Không thay đổi mode trong `story_plan.json`: vẫn `ENGLISH_STORYTELLING_WITH_CLEAN_ASMR` (schema `3.1`).
- Kiểm tra trên 3 dạng clip thật: hammer strike, grinder, restored-result shot. So sánh frame 0/1/2 giây và frame gần ASMR mark để xác nhận crop không cắt mất tay, búa, phôi.
- Nếu crop làm mất đầu búa/cạnh vật thể: sửa `center_x/y` trong effect_plan hoặc xóa zoom window; render lại hiệu ứng và final.
- Nghe track Clean ASMR, track English TTS và final MP4 riêng; **hiệu ứng chỉ tác động track video**, mọi mất tiếng búa phải debug separator/mixer, không thể đổ cho effect filter.
- Recut hook/slow-motion/b-roll thay đổi timeline chỉ chạy **trước** bước TTS, bắt buộc cập nhật audio/video time-map và asset hash.
- Bài test offline v3.2 phải pass trước khi tích hợp: `pytest -q tests`, nhưng không thay thế QA bằng người nghe với footage thật.
