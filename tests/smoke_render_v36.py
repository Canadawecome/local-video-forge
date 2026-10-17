"""Opt-in end-to-end offline smoke with synthetic 70s test footage and synthetic voice.

Run: PYTHONPATH=.:tests python tests/smoke_render_v36.py
Does NOT call OpenAI, OpusClip, SAM Audio, or ElevenLabs. Verifies FFmpeg renderer integration.
"""
from pathlib import Path
import json,subprocess,tempfile
from unittest.mock import patch
from test_full_story_v36 import story,synth_voice
from story_coverage_v36 import story_text,seal_script
from storytelling_render_v36 import process
from storytelling_render_v33 import sha256


def main():
    with tempfile.TemporaryDirectory(prefix='lvf_v36_real_render_') as tmp:
        folder=Path(tmp)/'clip_001';folder.mkdir()
        clip=folder/'clip.mp4'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y',
            '-f','lavfi','-i','color=c=0x443322:size=144x256:rate=12',
            '-f','lavfi','-i','sine=frequency=220:sample_rate=16000',
            '-t','70','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',
            '-c:a','aac','-b:a','96k','-shortest',str(clip)],check=True)
        p=story()
        (folder/'story_plan.json').write_text(p.model_dump_json(indent=2),encoding='utf8')
        (folder/'script_en.txt').write_text(story_text(p)+'\n',encoding='utf8')
        (folder/'script_tts.txt').write_text(' '.join(x.text_en for x in p.narration_segments)+'\n',encoding='utf8')
        (folder/'script_en.md').write_text(story_text(p)+'\n',encoding='utf8')
        (folder/'audio').mkdir(exist_ok=True)
        (folder/'audio'/'replacement_qc.json').write_text(json.dumps({'source_sha256':sha256(clip),
              'reviewed_by':'offline fixture','source_speech_absence_confirmed':True}),encoding='utf8')
        (folder/'render_preferences.json').write_text(json.dumps({'measure_mastering':False}),encoding='utf8')
        synth_voice(folder,p)
        # Approval-only mocking: video and audio still go through actual FFmpeg pipeline.
        with patch('director_workflow_v35.assert_approved',return_value=type('Ap',(),{'status':'APPROVED','score':95})()):
            seal_script(folder)
            result=process(folder)
        print(json.dumps({'status':result['final_story_qc']['status'],
                          'duration_sec':result['final_story_qc']['final_duration_sec'],
                          'full_story_segments':result['final_story_qc']['narration_segments'],
                          'voice_coverage':result['final_story_qc']['actual_tts_coverage_ratio'],
                          'asmr_preserved':result['workshop_bed_never_ducked_for_english_voice']},indent=2))
        assert (folder/'final.mp4').is_file()
        assert result['final_story_qc']['status']=='PASS_FULL_STORY_FINAL'

if __name__=='__main__':main()
