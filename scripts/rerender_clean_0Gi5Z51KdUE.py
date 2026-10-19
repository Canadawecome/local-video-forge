"""Re-render src_0Gi5Z51KdUE with 100% voice-free Demucs stem."""
import sys
import shutil
import subprocess
from pathlib import Path
sys.path.insert(0, ".")

from modules.render_engine import RenderEngine
from modules.script_generator import ScriptGenerator
from modules.voice_engine import VoiceEngine
from adapters.sol_adapter import SolAdapter

def main():
    source_dir = Path("data/sources/src_0Gi5Z51KdUE")
    clip_folder = source_dir / "output" / "clip_001_craft"
    clip_mp4 = clip_folder / "clip.mp4"
    visual_cut = source_dir / "restoration_cut" / "visual_cut.mp4"
    clean_stem = clip_folder / "audio" / "workshop_clean.wav"

    print("Step 1: Remuxing clip.mp4 with 100% voice-free workshop_clean.wav...")
    temp_clip = clip_folder / "clip_clean_temp.mp4"
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(visual_cut),
        "-i", str(clean_stem),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        str(temp_clip)
    ]
    subprocess.run(cmd, check=True)
    shutil.move(str(temp_clip), str(clip_mp4))
    print("clip.mp4 remuxed successfully!")

    print("Step 2: Generating rich storytelling script...")
    sol = SolAdapter()
    script_gen = ScriptGenerator(sol)
    clip_uid = f"src_0Gi5Z51KdUE:proj_restoration_src_0Gi5Z51KdUE:clip_001"
    script_rec = script_gen.generate_script_for_clip(
        clip_uid=clip_uid,
        output_folder=clip_folder,
        source_context_text="Reinventing the pencil sharpener with precision lathe and milling machine",
        clip_index=1,
    )
    print("Generated script title:", script_rec.title_en)

    print("Step 3: Synthesizing voiceover with ElevenLabs...")
    voice = VoiceEngine()
    voice.synthesize_plan_voice(clip_uid=clip_uid, output_folder=clip_folder)

    print("Step 4: Rendering final.mp4 with guaranteed voice-free ASMR stem...")
    renderer = RenderEngine()
    renderer.render_clip_v31(clip_uid=clip_uid, output_folder=clip_folder)
    print("SUCCESS: final.mp4 has been re-rendered!")

if __name__ == "__main__":
    main()
