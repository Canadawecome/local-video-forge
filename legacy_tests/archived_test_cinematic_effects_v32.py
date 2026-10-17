"""Offline v3.2 tests: visual effects cannot alter storytelling/ASMR timeline."""
import json
import subprocess
import sys
from pathlib import Path
import pytest
import numpy as np
import soundfile as sf

sys.path.insert(0,str(Path(__file__).parent))
from test_storytelling_v31 import make_fixture
from smart_effect_contracts_v32 import SmartEffectPlan
from smart_effect_planner_v32 import ensure_plan
from smart_effect_render_v32 import render, verify
from storytelling_render_v33 import process, SR


def test_preset_contract_blocks_tempo_sfx_and_audio():
    with pytest.raises(ValueError):
        SmartEffectPlan.model_validate({'source_clip_sha256':'a'*64,
            'duration_seconds':3,'audio_policy':'DUCK_ASMR_WHEN_VOICE'})
    with pytest.raises(ValueError):
        SmartEffectPlan.model_validate({'source_clip_sha256':'a'*64,
            'duration_seconds':3,'speed_ramp':[1.15]})
    with pytest.raises(ValueError):
        SmartEffectPlan.model_validate({'source_clip_sha256':'a'*64,
            'duration_seconds':3,'micro_zooms':[{'start':0,'end':1,
            'peak_scale':1.06,'evidence_ref':'shot'}]})


def test_zoom_overlap_rejected():
    with pytest.raises(ValueError,match='overlap'):
        SmartEffectPlan.model_validate({'source_clip_sha256':'a'*64,
          'duration_seconds':3,'micro_zooms':[
              {'start':.2,'end':1.4,'evidence_ref':'shot:1'},
              {'start':1.2,'end':2.4,'evidence_ref':'shot:2'}]})


def test_auto_plan_uses_only_real_asmr_windows(tmp_path):
    d=make_fixture(tmp_path/'clip_1')
    ensure_plan(d)
    p=SmartEffectPlan.model_validate_json((d/'effect_plan.json').read_text())
    assert p.preset=='CINEMATIC_ASMR'
    assert p.audio_policy=='NO_AUDIO_MODIFICATION'
    assert 1<=len(p.micro_zooms)<=4
    assert p.micro_zooms[0].evidence_ref.startswith('protected_asmr:')
    assert p.result_first_hook is None


def test_effect_video_has_no_audio_and_preserves_timing(tmp_path):
    d=make_fixture(tmp_path/'clip_1')
    ensure_plan(d)
    r=render(d)
    assert r['video_only_no_audio']
    assert abs(r['source_duration']-r['output_duration']) < .09
    assert r['micro_zoom_windows']==1
    assert r['result_first_hook_applied'] is False
    video,m=verify(d)
    assert video.exists() and m==r
    s=subprocess.run(['ffprobe','-v','error','-select_streams','a',
            '-show_entries','stream=index','-of','csv=p=0',str(video)],
            check=True,capture_output=True,text=True)
    assert not s.stdout.strip()


def test_stale_plan_and_stale_effect_hash_fail_closed(tmp_path):
    d=make_fixture(tmp_path/'clip_1')
    ensure_plan(d)
    obj=json.loads((d/'effect_plan.json').read_text())
    obj['source_clip_sha256']='0'*64
    (d/'effect_plan.json').write_text(json.dumps(obj))
    with pytest.raises(ValueError,match='EFFECT_STALE'):
        render(d)
    obj['source_clip_sha256']=__import__('hashlib').sha256((d/'clip.mp4').read_bytes()).hexdigest()
    (d/'effect_plan.json').write_text(json.dumps(obj))
    render(d)
    obj['grading']['contrast']=1.05
    (d/'effect_plan.json').write_text(json.dumps(obj))
    with pytest.raises(ValueError,match='EFFECT_STALE'):
        verify(d)


def test_v32_final_keeps_bed_under_english_and_burns_sub(tmp_path):
    d=make_fixture(tmp_path/'clip_1')
    r=process(d)
    assert r['visual_effect_preset']=='CINEMATIC_ASMR'
    assert r['timeline_unchanged_for_voice_and_asmr']
    assert r['workshop_bed_never_ducked_for_english_voice']
    assert r['english_subtitles_burned_in']
    assert r['caption_style']['font_px']==16  # 320px fixture: 5% = 16px
    assert r['caption_style']['anchor_y_pct']==85.0
    assert (d/'final.mp4').stat().st_size>1000
    assert r['final_mp4_asmr_during_voice']
    assert (d/'effects'/'video_effects.mp4').exists()
    mixed,_=sf.read(d/'audio'/'english_mix.wav',always_2d=True)
    voice,_=sf.read(d/'audio'/'english_voice_only.wav',always_2d=True)
    bed,_=sf.read(d/'audio'/'workshop_bed_always_on.wav',always_2d=True)
    a,b=round(.8*SR),round(1.2*SR)
    # No ducking: audio in the voice window remains exactly bed + English voice, up to gain.
    assert np.std(mixed[a:b]-voice[a:b]-bed[a:b])<.0005


def test_batch_failure_isolation(tmp_path):
    from storytelling_render_v33 import batch
    root=tmp_path/'source'
    ok=make_fixture(root/'clip_a')
    bad=make_fixture(root/'clip_b',stem=False)
    report=batch(root)
    assert report['clips']==2 and report['passed']==1
    assert (ok/'final.mp4').is_file()
    assert not (bad/'final.mp4').exists()


def test_hook_suggestion_is_advisory_not_misrepresented(tmp_path):
    d=make_fixture(tmp_path/'clip_1')
    ensure_plan(d)
    data=json.loads((d/'effect_plan.json').read_text())
    data['result_first_hook']={'start':1.8,'end':2.6,'evidence_ref':'shot_02',
                               'reason':'hammer impact'}
    (d/'effect_plan.json').write_text(json.dumps(data))
    result=render(d)
    assert not result['result_first_hook_applied']
    assert result['unapplied_hook_suggestion']
