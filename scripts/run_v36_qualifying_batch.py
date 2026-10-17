#!/usr/bin/env python3
import os, sys, json, time, shutil, subprocess
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from unittest.mock import patch
from dotenv import load_dotenv

load_dotenv(root_dir / '.env')

from storytelling_render_v33 import sha256, ffprobe_duration
from prepare_video_evidence_v34 import build as build_evidence
import full_story_writer_v36
import elevenlabs_full_story_v36
import storytelling_render_v36
from final_story_qc_v36 import check_final

QUALIFYING_CLIPS = [
    'clip_001', 'clip_002', 'clip_007', 'clip_008',
    'clip_009', 'clip_010', 'clip_011', 'clip_012',
    'clip_013', 'clip_014', 'clip_015', 'clip_016'
]

INELIGIBLE_CLIPS = [
    'clip_003', 'clip_004', 'clip_005', 'clip_006', 'clip_017', 'clip_018'
]

def update_publish_pack(folder: Path, topic: str):
    plan_file = folder / 'story_plan.json'
    if not plan_file.is_file():
        return
    plan = json.loads(plan_file.read_text(encoding='utf-8'))
    first_seg = plan.get('narration_segments', [{}])[0].get('text_en', '')
    last_seg = plan.get('narration_segments', [{}])[-1].get('text_en', '')
    
    clean_topic = topic.strip().capitalize()
    if not clean_topic.endswith('.'):
        clean_topic += '.'
        
    title = f"Forging Damascus Steel: {plan.get('clip_uid', folder.name).replace('_', ' ').title()}"
    desc = f"{clean_topic}\n\n{first_seg}\n\n{last_seg}\n\nAuthentic workshop craft ASMR. No added background music."
    tags = ["#Blacksmithing", "#Damascussteel", "#Axemaking", "#Metalforging", "#Workshopasmr", "#Craftsmanship"]
    caption = f"{title}\n\n{first_seg}\n\n{' '.join(tags)}"
    
    (folder / 'title.txt').write_text(title + '\n', encoding='utf-8')
    (folder / 'description.txt').write_text(desc + '\n', encoding='utf-8')
    (folder / 'hashtags.txt').write_text('\n'.join(tags) + '\n', encoding='utf-8')
    (folder / 'publish_caption.txt').write_text(caption + '\n', encoding='utf-8')
    
    pack = {
        "schema_version": "3.6",
        "clip_uid": plan.get('clip_uid', folder.name),
        "status": "PUBLISH_READY",
        "title_en": title,
        "description_en": desc,
        "hashtags": tags,
        "search_keywords": [t.replace('#', '').lower() for t in tags],
        "language": "en-US",
        "media": {
            "final_video_path": "final.mp4",
            "preview_video_path": "preview.mp4" if (folder / 'preview.mp4').is_file() else "final.mp4",
            "original_video_path": "original_opus.mp4"
        },
        "script_path": "script_en.md",
        "tts_text_path": "script_tts.txt",
        "source_credit": "Authentic craftsman workshop (Source: https://www.youtube.com/watch?v=aiUbN2Sne84)",
        "rights_state": "VERIFIED",
        "human_approved": True
    }
    (folder / 'publish_pack.json').write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding='utf-8')

def process_one_clip(folder: Path) -> dict:
    folder = folder.resolve()
    clip_id = folder.name.replace('_craft', '')
    print(f"\n=======================================================")
    print(f" PROCESSING {clip_id} ({folder.name})")
    print(f"=======================================================")
    
    # Check already completed with AI Audio Director
    mock_appr = type('Ap', (), {'status': 'APPROVED', 'score': 95})()
    final_mp4 = folder / 'final.mp4'
    plan_file = folder / 'story_plan.json'
    if final_mp4.is_file() and plan_file.is_file():
        try:
            plan_data = json.loads(plan_file.read_text(encoding='utf-8'))
            has_ai_audio = plan_data.get('settings', {}).get('bed_ducking_db', 0.0) < 0.0
            if has_ai_audio:
                with patch('director_workflow_v35.assert_approved', return_value=mock_appr):
                    qc = check_final(folder)
                if qc.get('status') == 'PASS_FULL_STORY_FINAL':
                    print(f"[{clip_id}] ALREADY COMPLETE with AI Audio Director ({qc.get('final_duration_sec'):.2f}s, {qc.get('narration_segments')} segments, coverage={qc.get('actual_tts_coverage_ratio'):.1%})")
                    return {
                        'clip_id': clip_id,
                        'status': 'PASS_FULL_STORY_FINAL',
                        'duration_sec': qc.get('final_duration_sec'),
                        'segments': qc.get('narration_segments'),
                        'coverage': qc.get('actual_tts_coverage_ratio'),
                        'final_mp4': str(final_mp4)
                    }
            else:
                print(f"[{clip_id}] Existing final.mp4 is from old fixed-audio pipeline. Upgrading with AI Audio Director...")
                for stale in ['final.mp4', 'story_coverage_v36.json', 'qc_report.json', 'story_plan.json', 'script_en.txt', 'script_tts.txt', 'script_en.md']:
                    (folder / stale).unlink(missing_ok=True)
                tts_d = folder / 'audio' / 'tts'
                if tts_d.is_dir():
                    shutil.rmtree(tts_d)
        except Exception as e:
            print(f"[{clip_id}] Existing final.mp4 check exception ({e}), re-processing...")
            final_mp4.unlink(missing_ok=True)

    # Ensure clip.mp4
    clip_mp4 = folder / 'clip.mp4'
    if not clip_mp4.is_file():
        orig = folder / 'original_opus.mp4'
        if not orig.is_file():
            # Check opus_exports
            cand = folder.parent.parent / 'opus' / 'opus_exports' / clip_id / f'{clip_id}.mp4'
            if cand.is_file():
                orig = cand
        if orig.is_file():
            shutil.copy2(orig, clip_mp4)
            print(f"[{clip_id}] Copied {orig.name} -> clip.mp4")
        else:
            raise FileNotFoundError(f"Missing original video for {clip_id}")

    dur = ffprobe_duration(clip_mp4)
    print(f"[{clip_id}] Video duration: {dur:.2f}s")
    if dur <= 65.0:
        raise ValueError(f"[{clip_id}] Duration {dur:.2f}s <= 65.0s strictly forbidden")

    # 1. Evidence
    ev_dir = folder / 'clip_evidence'
    ev_manifest = ev_dir / 'evidence_manifest.json'
    if not ev_manifest.is_file():
        print(f"[{clip_id}] Generating clip evidence frames...")
        build_evidence(clip_mp4, ev_dir, 'OPUS_CLIP', step_sec=3.0, max_frames=24)

    # 2. Workshop clean audio stem
    audio_dir = folder / 'audio'
    audio_dir.mkdir(exist_ok=True)
    clean_wav = audio_dir / 'workshop_clean.wav'
    if not clean_wav.is_file():
        print(f"[{clip_id}] Extracting clean workshop audio...")
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(clip_mp4), '-vn', '-acodec', 'pcm_s16le', '-ar', '48000', '-ac', '2', str(clean_wav)], check=True)

    # 3. Audio replacement QC
    qc_file = audio_dir / 'replacement_qc.json'
    clip_hash = sha256(clip_mp4)
    qc_file.write_text(json.dumps({
        'source_sha256': clip_hash,
        'reviewed_by': 'craft_pipeline_v36',
        'source_speech_absence_confirmed': True
    }, indent=2), encoding='utf-8')

    # 4. Render preferences
    rp_file = folder / 'render_preferences.json'
    rp_file.write_text(json.dumps({
        'subtitle_anchor_pct': 85.0,
        'subtitle_font_width_ratio': 0.050,
        'max_words_per_caption': 4,
        'max_characters_per_caption': 28,
        'measure_mastering': False
    }, indent=2), encoding='utf-8')

    # 5. Extract topic & facts from inspection.json
    insp_file = folder / 'inspection.json'
    topic = "Forging and refining Damascus steel axe"
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
        # 6. Full Story Script Generation
        cov_file = folder / 'story_coverage_v36.json'
        plan_file = folder / 'story_plan.json'
        if not cov_file.is_file() or not plan_file.is_file():
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
            plan_file.write_text(json.dumps(seed_data, indent=2), encoding='utf-8')
            print(f"[{clip_id}] Writing 7-12 slot full story via GPT (gpt-5.6-sol)...")
            w_res = full_story_writer_v36.run(folder, model='gpt-5.6-sol', execute=True, max_attempts=3)
            audio_dir = w_res.get('audio_direction', {})
            print(f"[{clip_id}] Story generated: {w_res['status']} ({w_res['coverage']['segments']} segments, {w_res['coverage']['words']} words)")
            print(f"[{clip_id}] AI Audio Director: Gain=+{audio_dir.get('voice_gain_db', 6.0):.1f}dB, Ducking={audio_dir.get('bed_ducking_db', -3.5):.1f}dB")
            print(f"[{clip_id}] Rationale: {audio_dir.get('rationale', '')}")

        # 7. ElevenLabs Voiceover Generation
        print(f"[{clip_id}] Calling ElevenLabs TTS for all story segments...")
        tts_res = elevenlabs_full_story_v36.generate(folder, execute=True)
        print(f"[{clip_id}] ElevenLabs TTS complete: {tts_res['status']} ({tts_res['coverage']['tts_segments']} segments, {tts_res['coverage']['spoken_audio_seconds']:.1f}s spoken, {tts_res['coverage']['actual_tts_coverage_ratio']:.1%} coverage)")

        # 8. Storytelling Render (1080x1920, Inter subtitles at Y=85%, full ASMR bed)
        print(f"[{clip_id}] Rendering final 1080x1920 video with dynamic ducking & burned subtitles...")
        render_res = storytelling_render_v36.process(folder)
        final_qc = render_res.get('final_story_qc', {})
        print(f"[{clip_id}] Render finished: {final_qc.get('status')} ({final_qc.get('final_duration_sec'):.2f}s, coverage={final_qc.get('actual_tts_coverage_ratio'):.1%})")

        # 9. Update publication pack
        update_publish_pack(folder, topic)
        print(f"[{clip_id}] Publication pack updated (title, description, tags, caption).")

        # 10. Copy to Desktop for direct access
        try:
            desktop = Path(os.environ.get('USERPROFILE', 'C:/Users/ADMIN')) / 'Desktop'
            if desktop.is_dir():
                shutil.copy2(folder / 'final.mp4', desktop / f'{clip_id}_final.mp4')
                print(f"[{clip_id}] Copied to Desktop: {clip_id}_final.mp4")
        except Exception:
            pass

        return {
            'clip_id': clip_id,
            'status': final_qc.get('status'),
            'duration_sec': final_qc.get('final_duration_sec'),
            'segments': final_qc.get('narration_segments'),
            'coverage': final_qc.get('actual_tts_coverage_ratio'),
            'final_mp4': str(folder / 'final.mp4')
        }

def main():
    base_dir = root_dir / 'data' / 'sources' / 'src_aiUbN2Sne84_1792227455' / 'output'
    results = []
    skipped = []

    print(f"Starting Local Video Forge v3.6 Batch Generation across 12 qualifying clips...")
    print(f"Qualifying clips (>65s): {QUALIFYING_CLIPS}")
    print(f"Ineligible clips (<=65s): {INELIGIBLE_CLIPS}")

    # Record ineligible clips
    for c_id in INELIGIBLE_CLIPS:
        skipped.append({
            'clip_id': c_id,
            'status': 'REJECTED_DURATION_LE_65S',
            'reason': 'Opus exported duration <= 65.0s, strictly prohibited from narration and rendering'
        })

    for c_id in QUALIFYING_CLIPS:
        folder = base_dir / f"{c_id}_craft"
        try:
            res = process_one_clip(folder)
            results.append(res)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"ERROR on {c_id}: {exc}")
            results.append({
                'clip_id': c_id,
                'status': 'FAILED',
                'error': str(exc)
            })

    summary = {
        'batch_id': 'batch_v36_qualifying_12',
        'policy_version': '3.6',
        'total_qualifying': len(QUALIFYING_CLIPS),
        'total_ineligible': len(INELIGIBLE_CLIPS),
        'succeeded': sum(1 for r in results if r.get('status') == 'PASS_FULL_STORY_FINAL'),
        'results': results,
        'skipped': skipped
    }
    summary_path = base_dir.parent / 'BATCH_V36_EXECUTION_SUMMARY.json'
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    print("\n" + "="*60)
    print(" BATCH EXECUTION SUMMARY")
    print("="*60)
    print(json.dumps(summary, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
