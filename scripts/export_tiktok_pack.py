#!/usr/bin/env python3
import os, sys, json, re, shutil
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
base_dir = root_dir / 'data' / 'sources' / 'src_aiUbN2Sne84_1792227455' / 'output'
desktop = Path(os.environ.get('USERPROFILE', 'C:/Users/ADMIN')) / 'Desktop'
target_folder = desktop / 'TikTok_Damascus_Steel_Clips'
target_folder.mkdir(parents=True, exist_ok=True)

QUALIFYING_CLIPS = [
    ('clip_001', '01_Forging_Billet_Compression', 'Forging Damascus Steel: Billet Compression'),
    ('clip_002', '02_Precision_Machining_Axe_Blank', 'Machining the Damascus Axe Blank'),
    ('clip_007', '03_Angle_Grinding_Steel_Prep', 'Raw Steel Prep & Angle Grinding'),
    ('clip_008', '04_Arc_Welding_Billet_Stack', 'Arc Welding Damascus Billet Layers'),
    ('clip_009', '05_White_Hot_Forge_Welding_Flux', 'White-Hot Forge Welding & Flux'),
    ('clip_010', '06_Heavy_Press_Hammer_Shaping', 'Hydraulic Press & Hammer Shaping'),
    ('clip_011', '07_Handcrafted_Axe_Handle_Sanding', 'Carving & Sanding the Axe Handle'),
    ('clip_012', '08_Billet_Tongs_Forge_Heating', 'Billet Stacking & Forge Chamber Heat'),
    ('clip_013', '09_Master_Damascus_Axe_Forging', 'Master Blacksmith Forging Damascus Axe'),
    ('clip_014', '10_Acid_Etch_Pattern_Reveal', 'Acid Etch Revealing Damascus Waves'),
    ('clip_015', '11_Forging_Axe_Head_Refining', 'Fire & Force: Refining Damascus Axe'),
    ('clip_016', '12_Final_Polish_Legendary_Axe', 'The Legendary Damascus Axe Payoff')
]

DEFAULT_HASHTAGS = "#damascussteel #blacksmith #craftsmanship #metalworking #satisfying #asmrsounds #forging #axemaking #handmade #oddlysatisfying #fyp"

def clean_str(s: str) -> str:
    s = re.sub(r'[\u2014\u2013]', '--', s)
    s = re.sub(r'[\u2018\u2019]', "'", s)
    s = re.sub(r'[\u201c\u201d]', '"', s)
    s = re.sub(r'[\u2026]', '...', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

all_captions_txt = []
all_captions_md = []

all_captions_md.append("# 🎬 BỘ 12 CLIP TIKTOK - BLACKSMITHING & DAMASCUS STEEL CRAFT ASMR\n")
all_captions_md.append("> **Âm thanh**: Giọng dẫn truyện tiếng Anh AI Director + Workshop ASMR nguyên bản, không chèn nhạc nền.\n")
all_captions_md.append("> **Định dạng**: 1080x1920 (chuẩn dọc 9:16), phụ đề Inter Y=85% đã gắn trực tiếp vào video.\n\n---\n")

for idx, (c_id, prefix_name, friendly_title) in enumerate(QUALIFYING_CLIPS, 1):
    src_folder = base_dir / f"{c_id}_craft"
    mp4_src = src_folder / 'final.mp4'
    plan_file = src_folder / 'story_plan.json'
    
    if not mp4_src.is_file():
        print(f"Skipping {c_id}: missing final.mp4")
        continue
        
    plan = json.loads(plan_file.read_text('utf-8'))
    segments = plan.get('narration_segments', [])
    hook = clean_str(segments[0]['text_en']) if segments else ""
    payoff = clean_str(segments[-1]['text_en']) if segments else ""
    dur = segments[-1]['end'] if segments else 70.0
    
    # Specific TikTok tailored description
    tiktok_desc = f"{friendly_title} 🔥🔨\n\n\"{hook}\"\n\nWatch the full transformation as raw steel becomes a masterpiece under heavy fire and pressure.\nAuthentic workshop ASMR, no added music.\n\n{DEFAULT_HASHTAGS}"
    
    # 1. Copy MP4 to target folder with clean descriptive filename
    target_mp4 = target_folder / f"{prefix_name}.mp4"
    shutil.copy2(mp4_src, target_mp4)
    print(f"[{c_id}] Copied -> {target_mp4.name} ({target_mp4.stat().st_size / (1024*1024):.1f} MB)")
    
    # 2. Write individual caption file
    caption_file = target_folder / f"{prefix_name}_caption.txt"
    caption_content = f"--- TIÊU ĐỀ / TITLE ---\n{friendly_title}\n\n--- TIKTOK CAPTION (COPY PASTE) ---\n{tiktok_desc}\n"
    caption_file.write_text(caption_content, encoding='utf-8')
    
    # 3. Add to master compilation
    txt_block = f"""================================================================================
CLIP #{idx:02d}: {friendly_title} ({prefix_name}.mp4)
Thời lượng: {dur:.1f}s
================================================================================
[NỘI DUNG COPY ĐĂNG TIKTOK]:

{tiktok_desc}

"""
    all_captions_txt.append(txt_block)
    
    md_block = f"""### Clip #{idx:02d}: {friendly_title}
- **Tên file video**: `{prefix_name}.mp4`
- **Thời lượng**: `{dur:.1f}s` | **Hook**: *"{hook}"*
- **Nội dung copy đăng TikTok**:
```text
{tiktok_desc}
```
---
"""
    all_captions_md.append(md_block)

# Save Master Files
master_txt = target_folder / "TIKTOK_ALL_CAPTIONS.txt"
master_txt.write_text("\n".join(all_captions_txt), encoding='utf-8')

master_md = target_folder / "TIKTOK_GUIDE_DANH_SACH.md"
master_md.write_text("\n".join(all_captions_md), encoding='utf-8')

print("\n" + "="*60)
print(f"EXPORT COMPLETED SUCCESSFULLY!")
print(f"Folder location: {target_folder}")
print("="*60)
