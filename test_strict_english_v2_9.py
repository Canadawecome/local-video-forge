from __future__ import annotations
import json
from pathlib import Path
import subprocess
import numpy as np
import pytest
import soundfile as sf
from PIL import Image
from strict_english_render_v2_9 import SR, process, batch, sha256, decode


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
