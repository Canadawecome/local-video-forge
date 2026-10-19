"""Build OpusClip Voiced Comparison for c6AghBnluHk."""
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
logger = logging.getLogger("opus_comparison")

def main():
    init_db()
    src_id = "src_c6AghBnluHk"
    src_dir = Config.DATA_DIR / "sources" / src_id
    raw_opus = src_dir / "opus_comparison" / "opus_cut_raw.mp4"
    clip2_dir = src_dir / "output" / "clip_002_opus"
    clip2_dir.mkdir(parents=True, exist_ok=True)
    (clip2_dir / "audio").mkdir(parents=True, exist_ok=True)

    dest_clip = clip2_dir / "clip.mp4"
    dest_orig = clip2_dir / "original_opus.mp4"
    if not dest_clip.exists():
        shutil.copy2(raw_opus, dest_clip)
        shutil.copy2(raw_opus, dest_orig)

    probe = probe_video(dest_clip)
    dur = float(probe["duration"])
    clip_uid = f"{src_id}:P3101807XjpP:clip_002"

    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO clips (id, batch_id, opus_project_id, opus_clip_id, index_no, status, duration_sec, source_asset_path, output_folder)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (clip_uid, f"batch_{src_id}", "P3101807XjpP", "clip_002", 2, "DISCOVERED", dur, str(dest_clip), "output/clip_002_opus")
        )

    insp_data = {
        "clip_uid": clip_uid,
        "clip_duration_sec": dur,
        "inspection": {
            "primary_craft_process": "Vintage jeweler wire roller restoration",
            "visible_actions": [
                "Shaft chucked into lathe chuck",
                "Carbide cutting tool peeling rust off rotating shaft",
                "Emery cloth strip smoothing freshly exposed metal",
                "Bench grinder finishing the axle journals",
                "Final reveal of pristine mirror machined finish",
            ],
            "suggested_story_angle": "Precision lathe machining and mirror finishing worn components",
            "material_observations": [
                "Severe rust scale",
                "Fresh bright turned steel",
                "Mirror polished journal surfaces"
            ]
        }
    }
    (clip2_dir / "inspection.json").write_text(json.dumps(insp_data, indent=2), encoding="utf-8")

    orch = PipelineOrchestrator()
    print("1. Generating craft script with GPT-5.6 Sol...")
    script = orch.script_gen.generate_script_for_clip(
        clip_uid=clip_uid,
        output_folder=clip2_dir,
        source_context_text="Antique jeweler gold roller precision lathe restoration",
        clip_index=2,
    )

    print("2. Synthesizing voiceover with ElevenLabs (Adam)...")
    voice = orch.voice.synthesize_plan_voice(
        clip_uid=clip_uid,
        output_folder=clip2_dir,
        script_revision=1,
    )

    print("3. Rendering final v3.1 Clean ASMR video with dynamic captions...")
    qc = orch.renderer.render_clip_v31(
        clip_uid=clip_uid,
        output_folder=clip2_dir,
    )

    final_mp4 = clip2_dir / "final.mp4"
    if final_mp4.exists():
        print(f"SUCCESS! Rendered {final_mp4} ({final_mp4.stat().st_size / 1_000_000:.2f} MB)")
    else:
        print("FAILED: final.mp4 not found")

if __name__ == "__main__":
    main()
