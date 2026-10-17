from __future__ import annotations
import json
from pathlib import Path
import subprocess
import numpy as np
import pytest
import soundfile as sf
from PIL import Image
from strict_english_render_v2_10 import SR, process, batch, sha256, decode


def wave(s, f=300, amp=.1):
    t=np.arange(round(s*SR),dtype=np.float32)/SR
    return np.repeat((amp*np.sin(2*np.pi*f*t))[:,None],2,axis=1)


def add_part(base,a,b,f=720,amp=.1):
    i=int(a*SR);j=int(b*SR)
    base[i:j] += wave((j-i)/SR,f,amp)[:j-i]
    return base


def store_align(wav_path,text,length):
    v=length/len(text)
    p=wav_path.with_suffix('.alignment.json')
    p.write_text(json.dumps({'alignment':{
        'characters':list(text),
        'character_start_times_seconds':[i*v for i in range(len(text))],
        'character_end_times_seconds':[(i+1)*v for i in range(len(text))]}}))


def mkclip(folder,*, qc=True,alignment=True,stem=True):
    folder.mkdir(parents=True)
    residual=wave(3.0,300,.045)
    raw=residual.copy()
    add_part(raw,.9,1.6,870,.04) # synthetic 'German speech' as a separate layer
    sf.write(folder/'source.wav',raw,SR)
    sf.write(folder/'audio'/'residual_workshop.wav',residual,SR) if (folder/'audio').mkdir(exist_ok=True) is None else None
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y',
        '-f','lavfi','-i','color=c=black:s=320x568:r=12:d=3',
        '-i',str(folder/'source.wav'),'-c:v','mpeg4','-q:v','7',
        '-c:a','aac','-shortest',str(folder/'clip.mp4')],check=True)
    plan={'clip_uid':'test:clip1','rights_status':'VERIFIED','music_rights_status':'NO_MUSIC',
          'source_german_speech':[{'id':'de1','start':.9,'end':1.6,'text_de':'Guten Tag'}],
          'protected_asmr':[{'start':.2,'end':.6,'kind':'hammer'}],
          'voice_segments':[{'id':'dub1','kind':'dub','start':.9,'end':1.6,'text_en':'Hello!',
                             'speech_ids':['de1'],'audio_path':'audio/tts/dub1.wav'},
                            {'id':'story1','kind':'commentary','start':2.1,'end':2.9,
                             'text_en':'Bright steel.','audio_path':'audio/tts/story1.wav'}],
          'approved_workshop_stem_path':'audio/residual_workshop.wav' if stem else None,
          'workshop_stem_qc_passed':stem}
    (folder/'audio_plan.json').write_text(json.dumps(plan))
    (folder/'audio'/'tts').mkdir(exist_ok=True)
    for name,text,length in [('dub1','Hello!',.6),('story1','Bright steel.',.65)]:
        path=folder/'audio'/'tts'/f'{name}.wav'
        sf.write(path,wave(length,500,.028),SR)
        if alignment: store_align(path,text,length)
    if qc:
        (folder/'audio'/'replacement_qc.json').write_text(json.dumps({
            'german_voice_absent':True,'asmr_preserved':True,'clip_transcript_checked':True,
            'reviewed_by':'audio-review-demo',
            'source_sha256':sha256(folder/'clip.mp4'),
            'residual_sha256':sha256(folder/'audio'/'residual_workshop.wav')}))
    return folder


def test_no_residual_fails_closed(tmp_path):
    p=mkclip(tmp_path/'clip',stem=False)
    with pytest.raises(ValueError,match='-24dB fallback is forbidden'):
        process(p)
    assert not (p/'final.mp4').exists()


def test_no_qc_approval_fails_closed(tmp_path):
    p=mkclip(tmp_path/'clip',qc=False)
    with pytest.raises(ValueError,match='replacement_qc.json'):
        process(p)


def test_no_english_tts_alignment_fails_closed(tmp_path):
    p=mkclip(tmp_path/'clip',alignment=False)
    with pytest.raises(ValueError,match='NEEDS_CAPTION_ALIGNMENT'):
        process(p)
    assert not (p/'final.mp4').exists()


def test_stale_approval_rejected(tmp_path):
    p=mkclip(tmp_path/'clip')
    meta=p/'audio'/'replacement_qc.json'
    content=json.loads(meta.read_text());content['residual_sha256']='broken'
    meta.write_text(json.dumps(content))
    with pytest.raises(ValueError,match='approval is stale'):
        process(p)


def test_fully_captioned_render_and_preserves_asmr(tmp_path):
    p=mkclip(tmp_path/'clip')
    report=process(p)
    assert report['english_subtitles_burned_in'] is True
    assert report['english_caption_cues']>=2
    assert report['replacement_stem_used']
    assert (p/'final.mp4').stat().st_size>2000
    srt=(p/'captions_en.srt').read_text()
    assert 'Hello!' in srt and 'Bright steel.' in srt
    # Our artificial German frequency is absent from backing waveform in the
    # middle of the original speech interval (apart from new EN TTS).
    audio,_=sf.read(p/'audio'/'english_mix.wav',always_2d=True)
    # Early ASMR retains its unmodified source waveform (PCM quantization tolerance).
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        original=decode(p/'clip.mp4',Path(d))
    n0,n1=int(.3*SR),int(.5*SR)
    assert float(np.max(np.abs(audio[n0:n1]-original[n0:n1])))<.0002
    # Hard-burned captions actually appear on the encoded VIDEO (not only sidecar).
    screenshot=p/'frame.png'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss','1.15',
                    '-i',str(p/'final.mp4'),'-frames:v','1',str(screenshot)],check=True)
    pix=np.asarray(Image.open(screenshot).convert('L'))
    assert np.count_nonzero(pix[230:]>75)>25


def test_batch_independent_failure(tmp_path):
    a=mkclip(tmp_path/'batch'/'clip_001')
    b=mkclip(tmp_path/'batch'/'clip_002',qc=False)
    rep=batch(tmp_path/'batch')
    assert rep['passed']==1 and rep['clips']==2
    assert (a/'final.mp4').exists()
    assert not (b/'final.mp4').exists()


def test_bed_unchanged_under_commentary_and_replaced_only_german(tmp_path):
    p=mkclip(tmp_path/'clip')
    report=process(p)
    assert report['workshop_bed_never_ducked_for_english_voice']
    assert report['caption_style']['anchor_y_pct']==85.0
    assert (p/'captions_en.ass').exists()
    assert (p/'audio'/'workshop_bed_always_on.wav').exists()
    bed,_=sf.read(p/'audio'/'workshop_bed_always_on.wav',always_2d=True)
    original,_=sf.read(p/'source.wav',always_2d=True)
    residual,_=sf.read(p/'audio'/'residual_workshop.wav',always_2d=True)
    a,b=int(2.25*SR),int(2.7*SR)
    # Commentary: no -7 dB audio dip. Original waveform is maintained.
    assert abs(20*np.log10(np.sqrt(np.mean(bed[a:b]**2))/np.sqrt(np.mean(original[a:b]**2)))) < .2
    a,b=int(1.1*SR),int(1.4*SR)
    # Dub: German-dominated raw replaced by speech-free residual, not muted.
    assert abs(20*np.log10(np.sqrt(np.mean(bed[a:b]**2))/np.sqrt(np.mean(residual[a:b]**2)))) < .3
    # Voice still included, as well as its independent workshop bed.
    mix,_=sf.read(p/'audio'/'english_mix.wav',always_2d=True)
    assert np.sqrt(np.mean((mix[a:b]-bed[a:b])**2))>.005


def test_english_voice_may_overlap_protected_hammer_while_bed_kept(tmp_path):
    p=mkclip(tmp_path/'clip')
    plan=json.loads((p/'audio_plan.json').read_text())
    plan['protected_asmr']=[{'start':1.05,'end':1.35,'kind':'hammer'}]
    (p/'audio_plan.json').write_text(json.dumps(plan))
    report=process(p)
    assert report['per_voice_asmr_metrics'][0]['protected_asmr_overlap']==['hammer']
    assert (p/'final.mp4').exists()


def test_default_subtitles_small_and_positioned_above_tiktok_ui(tmp_path):
    p=mkclip(tmp_path/'clip')
    report=process(p)
    style=report['caption_style']
    assert 12 <= style['font_px'] <= 42
    assert style['anchor_y_pct']==85.0
    assert style['outline_px']<=3
    assert '\\pos(160,483)' in (p/'captions_en.ass').read_text()
    img=p/'capture.png'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss','1.2',
                    '-i',str(p/'final.mp4'),'-frames:v','1',str(img)],check=True)
    pixels=np.array(Image.open(img).convert('L'))
    ys,xs=np.where(pixels>90)
    assert len(ys)>15
    assert np.percentile(ys,50)<.93*568  # Not down by platform buttons / caption overlay.
    assert np.percentile(ys,50)>.75*568


def test_subtitle_preferences_and_invalid_config(tmp_path):
    p=mkclip(tmp_path/'clip')
    (p/'render_preferences.json').write_text(json.dumps({'subtitle_anchor_pct':72,
       'subtitle_font_width_ratio':.028,'max_voice_over_bed_db':5.0}))
    rep=process(p)
    assert rep['caption_style']['anchor_y_pct']==72
    assert rep['render_preferences']['max_voice_over_bed_db']==5
    (p/'render_preferences.json').write_text(json.dumps({'subtitle_anchor_pct':98}))
    with pytest.raises(ValueError,match='Subtitle position'):
        process(p)
    assert not (p/'final.mp4').exists()


def test_silent_residual_over_hammer_blocks_video(tmp_path):
    p=mkclip(tmp_path/'clip')
    plan=json.loads((p/'audio_plan.json').read_text())
    plan['protected_asmr']=[{'start':1.05,'end':1.35,'kind':'hammer'}]
    (p/'audio_plan.json').write_text(json.dumps(plan))
    stem=p/'audio'/'residual_workshop.wav'
    sf.write(stem,np.zeros((round(3*SR),2),dtype=np.float32),SR)
    qc_path=p/'audio'/'replacement_qc.json'
    qc=json.loads(qc_path.read_text());qc['residual_sha256']=sha256(stem)
    qc_path.write_text(json.dumps(qc))
    with pytest.raises(ValueError,match='NEEDS_ASMR_REVIEW'):
        process(p)
    assert not (p/'final.mp4').exists()


def test_shared_batch_preferences_are_inherited(tmp_path):
    p=mkclip(tmp_path/'batch'/'clip_001')
    (p.parent/'render_preferences.json').write_text(json.dumps({'subtitle_anchor_pct':70,
                                                       'subtitle_font_width_ratio':.029}))
    rep=process(p)
    assert rep['caption_style']['anchor_y_pct']==70
    assert rep['render_preferences']['subtitle_font_width_ratio']==.029
