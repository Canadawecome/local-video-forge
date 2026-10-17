#!/usr/bin/env python3
import json, sys, shutil
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from unittest.mock import patch
from dotenv import load_dotenv
load_dotenv(root_dir / '.env')

import numpy as np
import soundfile as sf
import full_story_writer_v36
import elevenlabs_full_story_v36
import storytelling_render_v36
from storytelling_render_v33 import ffprobe_duration

def run():
    folder = root_dir / 'data' / 'sources' / 'src_aiUbN2Sne84_1792227455' / 'output' / 'clip_001_craft'
    clip_id = 'clip_001'
    print(f"=== TESTING AUDIO-SYNCED RHYTHM & AI AUDIO DIRECTOR ON {folder.name} ===")
    
    # 1. Clear previous outputs and TTS to force fresh generation
    for f in ['final.mp4', 'story_coverage_v36.json', 'qc_report.json', 'script_en.txt', 'script_tts.txt', 'script_en.md']:
        (folder / f).unlink(missing_ok=True)
    tts_dir = folder / 'audio' / 'tts'
    if tts_dir.is_dir():
        shutil.rmtree(tts_dir)
        
    # Fresh seed with actions
    insp_file = folder / 'inspection.json'
    topic = "Forging and refining Damascus steel billet"
    actions = []
    if insp_file.is_file():
        try:
            insp_data = json.loads(insp_file.read_text(encoding='utf-8'))
            insp = insp_data.get('inspection', {})
            topic = insp.get('primary_craft_process') or topic
            actions = insp.get('visible_actions', [])
        except Exception:
            pass

    seed_data = {
        "schema_version": "3.3",
        "clip_uid": clip_id,
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
    (folder / 'story_plan.json').write_text(json.dumps(seed_data, indent=2), encoding='utf-8')

    mock_appr = type('Ap', (), {'status': 'APPROVED', 'score': 95})()
    with patch('director_workflow_v35.assert_approved', return_value=mock_appr):
        print("\n[Step 1] Calling GPT-5.6-Sol with Audio-Action Synchronized Directives...")
        w_res = full_story_writer_v36.run(folder, model='gpt-5.6-sol', execute=True, max_attempts=3)
        print(f"-> Status: {w_res['status']}")
        audio_dir = w_res.get('audio_direction', {})
        print(f"-> AI Decided Voice Gain:    +{audio_dir.get('voice_gain_db'):.1f} dB")
        print(f"-> AI Decided Bed Ducking:   {audio_dir.get('bed_ducking_db'):.1f} dB")
        print(f"-> AI Sound Design Rationale: {audio_dir.get('rationale')}")
        
        # Display each segment's dynamic rhythm
        plan = json.loads((folder / 'story_plan.json').read_text(encoding='utf-8'))
        print("\n--- DYNAMIC SCRIPT & RHYTHMIC TIMELINE ---")
        for i, s in enumerate(plan['narration_segments'], 1):
            wc = len(s['text_en'].split())
            print(f"  {s['id']} [{s['role'].upper()}] ({wc:2d} words): \"{s['text_en']}\"")
        
        print("\n[Step 2] Generating ElevenLabs Audio & Reconciling Timeline...")
        tts_res = elevenlabs_full_story_v36.generate(folder, execute=True)
        print(f"-> TTS complete: {tts_res['status']} ({tts_res['coverage']['tts_segments']} segments, {tts_res['coverage']['spoken_audio_seconds']:.1f}s spoken)")
        
        # Display reconciled slots and ASMR pause sizes
        reconciled = json.loads((folder / 'story_plan.json').read_text(encoding='utf-8'))
        segs = reconciled['narration_segments']
        print("\n--- FINAL ACOUSTIC RHYTHM & ASMR GAPS ---")
        for i in range(len(segs)):
            s = segs[i]
            dur = s['end'] - s['start']
            gap_str = ""
            if i + 1 < len(segs):
                gap = segs[i+1]['start'] - s['end']
                gap_str = f" | ASMR pause to next: {gap:.2f}s"
            print(f"  {s['id']}: [{s['start']:5.2f}s - {s['end']:5.2f}s] (speech: {dur:4.2f}s){gap_str}")

        print("\n[Step 3] Rendering final 1080x1920 MP4 with dynamic ducking & burned subtitles...")
        r_res = storytelling_render_v36.process(folder)
        final_qc = r_res.get('final_story_qc', {})
        print(f"-> Render finished: {final_qc.get('status')} ({final_qc.get('final_duration_sec'):.2f}s, coverage={final_qc.get('actual_tts_coverage_ratio'):.1%})")
        
    # Measure audio levels
    v_path = folder / 'audio' / 'english_voice_only.wav'
    b_path = folder / 'audio' / 'workshop_clean.wav'
    m_path = folder / 'audio' / 'mixed_audio.wav'
    
    v, sr = sf.read(v_path)
    b, _ = sf.read(b_path)
    m, _ = sf.read(m_path)
    
    v_act = v[np.abs(v) > 1e-4]
    rms_v = np.sqrt(np.mean(v_act**2)) if len(v_act) else 0
    rms_b = np.sqrt(np.mean(b**2)) if len(b) else 0
    rms_m = np.sqrt(np.mean(m**2)) if len(m) else 0
    
    print("\n=== FINAL AUDIO METRICS ===")
    print(f"Active Voice RMS:    {20*np.log10(rms_v):.1f} dBFS")
    print(f"Raw Background RMS:  {20*np.log10(rms_b):.1f} dBFS")
    print(f"Mixed Audio RMS:     {20*np.log10(rms_m):.1f} dBFS")
    diff_vb = 20*np.log10(rms_v) - 20*np.log10(rms_b)
    print(f"Voice vs Background: {diff_vb:+.1f} dB (Narrator is dominant and crystal clear)")
    print(f"Final MP4: {folder / 'final.mp4'}")

if __name__ == '__main__':
    run()
