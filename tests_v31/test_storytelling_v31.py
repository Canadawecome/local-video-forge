"""Offline contract and FFmpeg integration tests; NOT accuracy claims for SAM Audio."""
import json, subprocess
import numpy as np
import soundfile as sf
import pytest
from pathlib import Path
from storytelling_render_v31 import SR, process, batch, sha256, decode
from storytelling_contracts_v31 import StorytellingPlan


def sine(t, freq=310, amp=.035):
    sec=np.arange(round(SR*t))/SR
    return np.repeat((amp*np.sin(2*np.pi*freq*sec))[:,None].astype(np.float32),2,axis=1)


def make_fixture(d: Path, *, speech=True, stem=True, qc=True, alignment=True):
    d.mkdir(parents=True,exist_ok=True)
    (d/'audio'/'tts').mkdir(parents=True,exist_ok=True)
    # Constant audio bed with hammer transient at 1.9 sec (outside fake speech region)
    bed=sine(3,310,.035)
    k=int(1.9*SR)
    bed[k:k+int(.02*SR)] += sine(.02,950,.13)
    raw=bed.copy()
    if speech:
        raw[int(.5*SR):int(1.4*SR)]+=sine(.9,770,.045)
    sf.write(d/'raw.wav',raw,SR)
    if stem:
        sf.write(d/'audio'/'workshop_clean.wav',bed,SR)
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y',
        '-f','lavfi','-i','color=c=black:s=320x568:r=12:d=3',
        '-i',str(d/'raw.wav'),'-c:v','mpeg4','-q:v','7',
        '-c:a','aac','-shortest',str(d/'clip.mp4')],check=True)
    voice=sine(.58,410,.03)
    path=d/'audio'/'tts'/'story.wav'
    sf.write(path,voice,SR)
    text='The forge is blazing.'
    if alignment:
        char_dt=.58/len(text)
        path.with_suffix('.alignment.json').write_text(json.dumps({'alignment':{
            'characters':list(text),
            'character_start_times_seconds':[i*char_dt for i in range(len(text))],
            'character_end_times_seconds':[(i+1)*char_dt for i in range(len(text))]
        }}))
    plan={'schema_version':'3.1','clip_uid':'demo_001','mode':'ENGLISH_STORYTELLING_WITH_CLEAN_ASMR',
        'rights_status':'VERIFIED','music_rights_status':'NO_MUSIC',
        'german_speech_status':'CONFIRMED_PRESENT' if speech else 'CONFIRMED_ABSENT',
        'source_german_speech':[{'id':'s1','start':.5,'end':1.4,'text_de':'Hier ist ein Hammer.'}] if speech else [],
        'protected_asmr':[{'start':1.85,'end':2.1,'kind':'hammer'}],
        'narration_segments':[{'id':'story1','role':'process','start':.7,'end':1.5,
            'text_en':text,'audio_path':'audio/tts/story.wav','evidence_refs':['frame_03']}],
        'approved_workshop_stem_path':'audio/workshop_clean.wav' if speech and stem else None,
        'workshop_stem_qc_passed':bool(speech and stem)}
    (d/'story_plan.json').write_text(json.dumps(plan))
    if qc:
        data={'source_sha256':sha256(d/'clip.mp4'),'reviewed_by':'test-fixture',
            'source_speech_absence_confirmed':not speech,
            'german_voice_absent':True,'asmr_preserved':True,'clip_transcript_checked':True,
            'residual_sha256':sha256(d/'audio'/'workshop_clean.wav') if stem else None}
        (d/'audio'/'replacement_qc.json').write_text(json.dumps(data))
    return d


def test_schema_no_dubbing_contract():
    base={'clip_uid':'abc','rights_status':'VERIFIED','music_rights_status':'NO_MUSIC',
          'german_speech_status':'CONFIRMED_ABSENT','narration_segments':[{'id':'a','start':0,'end':2,'text_en':'Story'}]}
    StorytellingPlan.model_validate(base)
    base['mode']='HYBRID_SELECTIVE_DUB_ASMR_STORY'
    with pytest.raises(ValueError): StorytellingPlan.model_validate(base)
    base['mode']='ENGLISH_STORYTELLING_WITH_CLEAN_ASMR'
    base['narration_segments'][0]['speech_ids']=['de1']
    with pytest.raises(ValueError): StorytellingPlan.model_validate(base)


def test_old_mode_name_rejected():
    base={'clip_uid':'abc','rights_status':'VERIFIED','music_rights_status':'NO_MUSIC',
          'german_speech_status':'CONFIRMED_ABSENT',
          'narration_segments':[{'id':'a','start':0,'end':2,'text_en':'Story'}]}
    base['mode']='ORIGINAL_COMMENTARY_ASMR'
    with pytest.raises(ValueError): StorytellingPlan.model_validate(base)


def test_missing_clean_stem_blocks(tmp_path):
    d=make_fixture(tmp_path/'c',stem=False)
    with pytest.raises(ValueError,match='full-length approved speech-free'): process(d)
    assert not (d/'final.mp4').exists()


def test_missing_stem_qc_blocks(tmp_path):
    d=make_fixture(tmp_path/'c',qc=False)
    with pytest.raises(ValueError,match='replacement_qc.json'): process(d)


def test_missing_english_timing_blocks(tmp_path):
    d=make_fixture(tmp_path/'c',alignment=False)
    with pytest.raises(ValueError,match='NEEDS_CAPTION_ALIGNMENT'): process(d)


def test_full_residual_and_story_independent_timing(tmp_path):
    d=make_fixture(tmp_path/'c')
    report=process(d)
    assert report['storytelling_mode']=='ENGLISH_STORYTELLING_WITH_CLEAN_ASMR'
    assert report['workshop_bed_never_ducked_for_english_voice']
    assert report['english_subtitles_burned_in']
    assert report['caption_style']['font_pct_of_width']==5.0
    assert report['caption_style']['anchor_y_pct']==85.0
    assert report['english_caption_cues']>0
    assert 'forge' in (d/'captions_en.srt').read_text()
    assert (d/'final.mp4').stat().st_size>1000
    w,_=sf.read(d/'audio'/'workshop_bed_always_on.wav',always_2d=True)
    residual,_=sf.read(d/'audio'/'workshop_clean.wav',always_2d=True)
    # The entire bed comes from cleaned stem (not only a small German window).
    assert np.max(np.abs(w[round(2.2*SR):round(2.4*SR)]-residual[round(2.2*SR):round(2.4*SR)]))<.0003
    # Voice did not erase the bed during English narration.
    mix,_=sf.read(d/'audio'/'english_mix.wav',always_2d=True)
    v,_=sf.read(d/'audio'/'english_voice_only.wav',always_2d=True)
    a,b=round(.8*SR),round(1.1*SR)
    assert np.max(np.abs((mix-v)[a:b]-w[a:b]))<.0003


def test_speech_free_clip_uses_raw_and_no_model(tmp_path):
    d=make_fixture(tmp_path/'c',speech=False,stem=False)
    rep=process(d)
    assert rep['replacement_stem_used'] is False
    assert (d/'final.mp4').is_file()


def test_batch_one_failure_does_not_block_good_clip(tmp_path):
    root=tmp_path/'batch'
    good=make_fixture(root/'clip_001')
    bad=make_fixture(root/'clip_002',qc=False)
    result=batch(root)
    assert result['clips']==2 and result['passed']==1
    assert (good/'final.mp4').is_file()
    assert not (bad/'final.mp4').exists()


def test_missing_hammer_transient_blocks(tmp_path):
    d=make_fixture(tmp_path/'c')
    stem=d/'audio'/'workshop_clean.wav'
    a,_=sf.read(stem,always_2d=True)
    a[int(1.85*SR):int(2.1*SR)]=0
    sf.write(stem,a,SR)
    qcfile=d/'audio'/'replacement_qc.json'
    qc=json.loads(qcfile.read_text());qc['residual_sha256']=sha256(stem)
    qcfile.write_text(json.dumps(qc))
    with pytest.raises(ValueError,match='NEEDS_ASMR_REVIEW'): process(d)
