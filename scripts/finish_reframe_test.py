"""Finish voiced pipeline for Smart Reframe test video."""
import json
import logging
import shutil
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from config import Config
from modules.opus_manager import probe_video
from pipeline import PipelineOrchestrator
from storage.db import get_connection, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("finish_reframe_test")

def main():
    init_db()
    src_id = "src_c6AghBnluHk_reframe_test"
    src_dir = Config.DATA_DIR / "sources" / src_id
    cut_dir = src_dir / "restoration_cut"
    visual_cut = cut_dir / "visual_cut.mp4"
    output_dir = src_dir / "output"
    clip_dir = output_dir / "clip_001_craft"
    clip_dir.mkdir(parents=True, exist_ok=True)
    (clip_dir / "audio").mkdir(parents=True, exist_ok=True)

    dest_clip = clip_dir / "clip.mp4"
    dest_orig = clip_dir / "original_opus.mp4"
    shutil.copy2(visual_cut, dest_clip)
    shutil.copy2(visual_cut, dest_orig)

    asmr_wav = cut_dir / "source_asmr.wav"
    if asmr_wav.exists():
        shutil.copy2(asmr_wav, clip_dir / "audio" / "workshop_clean.wav")
        shutil.copy2(asmr_wav, clip_dir / "audio" / "residual_workshop.wav")

    probe = probe_video(dest_clip)
    dur = float(probe["duration"])
    clip_uid = f"{src_id}:proj_{src_id}:clip_001"

    with get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO sources (id, youtube_url, rights_status) VALUES (?, ?, ?)", (src_id, "https://www.youtube.com/watch?v=c6AghBnluHk", "VERIFIED"))
        conn.execute("INSERT OR REPLACE INTO source_batches (id, source_id, barrier_state) VALUES (?, ?, ?)", (f"batch_{src_id}", src_id, "PROCESSED"))
        conn.execute("INSERT OR REPLACE INTO opus_projects (id, batch_id, status) VALUES (?, ?, ?)", (f"proj_{src_id}", f"batch_{src_id}", "SUCCEEDED"))
        conn.execute("INSERT OR REPLACE INTO clips (id, batch_id, opus_project_id, opus_clip_id, index_no, status, duration_sec, source_asset_path, output_folder) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (clip_uid, f"batch_{src_id}", f"proj_{src_id}", "clip_001", 1, "DISCOVERED", dur, str(dest_clip), "output/clip_001_craft"))

    # Read story map
    story_map_file = cut_dir / "story_map.json"
    visible_actions = [
        "1.2s Teaser hook of pristine gold roller",
        "Disassembly and gear unseating",
        "Rust wire brushing at lathe bed",
        "Dynamic lathe turning pass along steel shaft",
        "Polishing and spray finish",
        "Final wire rolling test and reveal"
    ]
    insp_data = {
        "clip_uid": clip_uid,
        "clip_duration_sec": dur,
        "inspection": {
            "primary_craft_process": "Vintage mechanical antique restoration",
            "visible_actions": visible_actions,
            "suggested_story_angle": "Master craftsman restoration transformation",
            "material_observations": ["Corroded steel", "Machined precision tolerances", "Mirror finish"],
        }
    }
    (clip_dir / "inspection.json").write_text(json.dumps(insp_data, indent=2), encoding="utf-8")

    orch = PipelineOrchestrator()
    print("1. Generating craftsman voiceover script with GPT-5.6 Sol...")
    script = orch.script_gen.generate_script_for_clip(
        clip_uid=clip_uid,
        output_folder=clip_dir,
        source_context_text="Antique mechanical restoration documentary cut",
        clip_index=1,
    )

    print("2. Synthesizing voiceover with ElevenLabs (Adam)...")
    voice = orch.voice.synthesize_plan_voice(
        clip_uid=clip_uid,
        output_folder=clip_dir,
        script_revision=1,
    )

    print("3. Rendering final v3.1 Clean ASMR video with dynamic captions...")
    qc = orch.renderer.render_clip_v31(
        clip_uid=clip_uid,
        output_folder=clip_dir,
    )

    final_mp4 = clip_dir / "final.mp4"
    print(f"SUCCESS! Rendered {final_mp4} ({final_mp4.stat().st_size / 1_000_000:.2f} MB)")

if __name__ == "__main__":
    main()
