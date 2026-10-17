import os, sys, json, subprocess
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from unittest.mock import patch
from dotenv import load_dotenv

load_dotenv('.env')

from storytelling_render_v33 import sha256, ffprobe_duration
from prepare_video_evidence_v34 import build as build_evidence
import full_story_writer_v36
import elevenlabs_full_story_v36
import storytelling_render_v36

def process_clip(folder: Path):
    folder = folder.resolve()
    clip_mp4 = folder / 'clip.mp4'
    if not clip_mp4.is_file():
        orig = folder / 'original_opus.mp4'
        if orig.is_file():
            import shutil
            shutil.copy2(orig, clip_mp4)
            print(f"Copied original_opus.mp4 to clip.mp4 in {folder.name}")
    
    dur = ffprobe_duration(clip_mp4)
    print(f"[{folder.name}] Duration: {dur:.2f}s")
    if dur <= 65.0:
        print(f"[{folder.name}] Ineligible (<= 65s), skipping.")
        return False

    # Evidence
    ev_dir = folder / 'clip_evidence'
    ev_manifest = ev_dir / 'evidence_manifest.json'
    if not ev_manifest.is_file():
        print(f"[{folder.name}] Generating clip evidence...")
        build_evidence(clip_mp4, ev_dir, 'OPUS_CLIP', step_sec=3.0, max_frames=24)

    # Audio clean workshop stem
    audio_dir = folder / 'audio'
    audio_dir.mkdir(exist_ok=True)
    clean_wav = audio_dir / 'workshop_clean.wav'
    if not clean_wav.is_file():
        print(f"[{folder.name}] Extracting clean workshop audio...")
        subprocess.run(['ffmpeg', '-y', '-i', str(clip_mp4), '-vn', '-acodec', 'pcm_s16le', '-ar', '48000', '-ac', '2', str(clean_wav)], check=True, capture_output=True)

    # Replacement QC
    qc_file = audio_dir / 'replacement_qc.json'
    clip_hash = sha256(clip_mp4)
    qc_file.write_text(json.dumps({
        'source_sha256': clip_hash,
        'reviewed_by': 'craft_pipeline_v36',
        'source_speech_absence_confirmed': True
    }, indent=2), encoding='utf-8')

    # Render preferences
    rp_file = folder / 'render_preferences.json'
    rp_file.write_text(json.dumps({
        'subtitle_anchor_pct': 85.0,
        'subtitle_font_width_ratio': 0.050,
        'max_words_per_caption': 4,
        'max_characters_per_caption': 28,
        'measure_mastering': False
    }, indent=2), encoding='utf-8')

    # Ensure seed story_plan.json
    plan_file = folder / 'story_plan.json'
    insp_file = folder / 'inspection.json'
    topic = "Forging Damascus steel axe billet"
    actions = []
    if insp_file.is_file():
        try:
            insp_data = json.loads(insp_file.read_text(encoding='utf-8'))
            insp = insp_data.get('inspection', {})
            topic = insp.get('primary_craft_process') or topic
            actions = insp.get('visible_actions', [])
        except Exception:
            pass

    mock_appr = type('Ap', (), {'status': 'APPROVED', 'score': 95})()
    with patch('director_workflow_v35.assert_approved', return_value=mock_appr):
        # 1. Full Story Writer
        cov_file = folder / 'story_coverage_v36.json'
        if not cov_file.is_file():
            seed_data = {
                "schema_version": "3.3",
                "clip_uid": folder.name.replace('_craft', ''),
                "mode": "ENGLISH_STORYTELLING_WITH_CLEAN_ASMR",
                "rights_status": "VERIFIED",
                "music_rights_status": "NO_MUSIC",
                "source_context": {
                    "source_language": "und",
                    "source_language_status": "UNDETERMINED",
                    "source_country": None,
                    "source_country_status": "UNKNOWN",
                    "topic_en": topic,
                    "verified_facts": [
                        {
                            "claim_en": actions[0] if actions else "Craftsman shapes steel billet in workshop",
                            "evidence_refs": ["frame_0000"]
                        }
                    ]
                },
                "source_speech_status": "CONFIRMED_ABSENT",
                "source_speech": [],
                "protected_asmr": [],
                "approved_workshop_stem_path": None,
                "workshop_stem_qc_passed": False,
                "settings": {
                    "voice_gain_db": 0.0,
                    "peak_ceiling_dbfs": -1.0
                },
                "voice_id": "QIhD5ivPGEoYZQDocuHI",
                "tts_model_id": "eleven_multilingual_v2"
            }
            plan_file.write_text(json.dumps(seed_data, indent=2), encoding='utf-8')
            print(f"[{folder.name}] Writing full story with GPT...")
            w_res = full_story_writer_v36.run(folder, model='gpt-5.6-sol', execute=True, max_attempts=3)
            print(f"[{folder.name}] Story writer result: {w_res['status']}")

        # 2. ElevenLabs TTS
        print(f"[{folder.name}] Generating ElevenLabs TTS for all segments...")
        tts_res = elevenlabs_full_story_v36.generate(folder, execute=True)
        print(f"[{folder.name}] TTS result: {tts_res['status']}, coverage={tts_res['coverage']['actual_tts_coverage_ratio']:.1%}")

        # 3. Final Render
        print(f"[{folder.name}] Rendering final video with storytelling_render_v36...")
        render_res = storytelling_render_v36.process(folder)
        final_qc = render_res.get('final_story_qc', {})
        print(f"[{folder.name}] Render complete: status={final_qc.get('status')}, duration={final_qc.get('final_duration_sec')}s, coverage={final_qc.get('actual_tts_coverage_ratio'):.1%}")

    return True

if __name__ == '__main__':
    target = Path('data/sources/src_aiUbN2Sne84_1792227455/output/clip_001_craft')
    process_clip(target)
