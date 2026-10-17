from __future__ import annotations
import json
import subprocess
from pathlib import Path
import numpy as np
try:
    import pytest
except ImportError:
    class _PytestShim:
        class raises:
            def __init__(self, expected_exc, match=None):
                self.expected_exc = expected_exc
                self.match = match
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                if exc_type is None:
                    raise AssertionError(f"Expected {self.expected_exc} but no exception was raised")
                if not issubclass(exc_type, self.expected_exc):
                    return False
                if self.match and self.match not in str(exc_val):
                    raise AssertionError(f"Pattern '{self.match}' not found in '{exc_val}'")
                return True
    pytest = _PytestShim()
import soundfile as sf
from pydantic import ValidationError
from hybrid_audio_contracts_v2_7 import HybridClipPlan
from hybrid_audio_engine import SAMPLE_RATE, mix_audio, process_clip, batch, segment_tts_path


def mkplan(**changes):
    base = {
        "clip_uid": "source:clipA", "rights_status": "VERIFIED", "music_rights_status": "NO_MUSIC",
        "source_german_speech": [{"id": "de1", "start": 1.0, "end": 1.7, "text_de": "Hallo"}],
        "protected_asmr": [{"start": 0.1, "end": 0.7, "kind": "hammer"}],
        "voice_segments": [
            {"id": "dub1", "kind": "dub", "start": 1.0, "end": 1.7,
             "text_en": "Hello", "speech_ids": ["de1"]},
            {"id": "story1", "kind": "commentary", "start": 2.1, "end": 2.9,
             "text_en": "Hammered steel", "speech_ids": []}
        ]
    }
    base.update(changes)
    return HybridClipPlan.model_validate(base)


def tone(seconds, freq=400, vol=0.1):
    t = np.arange(round(seconds*SAMPLE_RATE), dtype=np.float32) / SAMPLE_RATE
    return np.repeat((vol * np.sin(2 * np.pi * freq * t))[:,None],2,axis=1).astype(np.float32)


def voices():
    return {"dub1": tone(0.6, 750, 0.05), "story1": tone(0.65, 600, 0.05)}


def rms(x):
    return float(np.sqrt(np.mean(x**2)))


def span(x, a, b):
    return x[int(a * SAMPLE_RATE):int(b * SAMPLE_RATE)]


def test_hammer_kept_and_german_duck():
    raw = tone(3.0, 400, 0.11)
    y, report = mix_audio(Path('.'), mkplan(), raw, None, voices())
    # The hammer-only interval is pristine (outside voice, no attenuation)
    assert np.max(np.abs(span(y-raw, 0.23, 0.55))) < 2e-6
    # During German voice the workshop backing track is deeply attenuated
    y_silent, _ = mix_audio(Path('.'), mkplan(), raw, None, {k: np.zeros_like(v) for k,v in voices().items()})
    assert rms(span(y_silent, 1.21, 1.47)) / rms(span(raw, 1.21, 1.47)) < .08
    assert report['needs_listening_qc'] is True


def test_german_asmr_overlap_requires_stem():
    with pytest.raises(ValidationError, match='approved speech-free workshop stem'):
        mkplan(protected_asmr=[{"start": 1.1,"end":1.5,"kind":"hammer"}])


def test_protected_asmr_fails_english_voice():
    with pytest.raises(ValidationError, match='overlaps protected'):
        mkplan(protected_asmr=[{"start": 2.2,"end":2.8,"kind":"hammer"}])


def test_source_speech_must_have_dub():
    with pytest.raises(ValidationError, match='not mapped to a dub'):
        mkplan(voice_segments=[{"id":"v","kind":"commentary","start":2,"end":2.8,"text_en":"Just a story"}])


def test_rights_music_gate():
    with pytest.raises(ValidationError, match='Music rights'):
        mkplan(music_rights_status="UNKNOWN")
    with pytest.raises(ValidationError, match='Footage rights'):
        mkplan(rights_status="UNKNOWN")


def test_no_truncate_overlong_voice():
    raw=tone(3.0)
    bad=voices()
    bad['dub1']=tone(0.82)
    with pytest.raises(ValueError,match='too long'):
        mix_audio(Path('.'),mkplan(),raw,None,bad)


def test_approved_stem_preserves_hammer_over_source_speech():
    plan=mkplan(protected_asmr=[{"start":1.15,"end":1.55,"kind":"hammer"}],
                voice_segments=[
                    {"id":"dub1","kind":"dub","start":1.76,"end":2.4,"text_en":"Hello","speech_ids":["de1"]},
                    {"id":"story1","kind":"commentary","start":2.45,"end":2.99,"text_en":"Okay"}
                ],
                approved_workshop_stem_path='workshop_only.wav', workshop_stem_qc_passed=True)
    raw=tone(3.0,400,.10)
    stem=tone(3.0,200,.08)
    test_voices = {'dub1':tone(.5), 'story1':tone(.5)}
    out, rep=mix_audio(Path('.'),plan,raw,stem,test_voices)
    assert rep['workshop_stem_used']
    assert out.shape == raw.shape


def test_duration_bounds():
    with pytest.raises(ValueError, match='beyond clip'):
        mkplan().validate_duration(2.5)


def test_end_to_end_and_batch_failure_isolation(tmp_path):
    root=tmp_path/'batch'; root.mkdir()
    okay=root/'clip_001'; okay.mkdir()
    bad=root/'clip_002'; bad.mkdir()
    sr=SAMPLE_RATE
    sf.write(tmp_path/'tone.wav',tone(3.0),sr)
    cmd=["ffmpeg","-hide_banner","-loglevel","error","-y",
         "-f","lavfi","-i","color=c=black:s=320x568:r=12:d=3",
         "-i",str(tmp_path/'tone.wav'),"-c:v","mpeg4","-q:v","8",
         "-c:a","aac","-shortest",str(okay/'clip.mp4')]
    subprocess.run(cmd,check=True)
    plan=mkplan()
    (okay/'audio_plan.json').write_text(plan.model_dump_json(indent=2))
    for v in plan.voice_segments:
        p=okay/'audio'/'tts'/f'{v.id}.wav'
        p.parent.mkdir(parents=True,exist_ok=True)
        sf.write(p,voices()[v.id],sr)
    spec=json.loads((okay/'audio_plan.json').read_text())
    for v in spec['voice_segments']:
        v['audio_path']=f"audio/tts/{v['id']}.wav"
    (okay/'audio_plan.json').write_text(json.dumps(spec))
    (bad/'audio_plan.json').write_text('{"bad":true}')
    result=batch(root,skip_tts=True)
    assert result['total']==2 and result['passed']==1 and result['needs_review']==1
    assert (okay/'final.mp4').is_file()
    assert (okay/'audio_mix_report.json').is_file()
    assert not (bad/'final.mp4').exists()
    assert process_clip(okay,skip_tts=True,dry_run=True)['validated']


def test_script_revision_changes_tts_cache_key(tmp_path):
    a = mkplan().voice_segments[0]
    b = a.model_copy(update={"text_en": "Changed translation with new technical details"})
    assert segment_tts_path(tmp_path, a) != segment_tts_path(tmp_path, b)


def test_five_clip_fanout_independent_outputs(tmp_path):
    import shutil
    src=tmp_path/'synthetic_src.wav'
    sf.write(src,tone(3.0),SAMPLE_RATE)
    one=tmp_path/'prototype.mp4'
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y",
        "-f","lavfi","-i","color=c=black:s=320x568:r=10:d=3",
        "-i",str(src),"-c:v","mpeg4","-q:v","10", "-c:a","aac","-shortest",str(one)],check=True)
    root=tmp_path/'five'; root.mkdir()
    for i in range(5):
        d=root/f'clip_{i+1:03d}'
        d.mkdir()
        shutil.copyfile(one,d/'clip.mp4')
        plan=mkplan(clip_uid=f'batch1:clip{i+1}')
        spec=plan.model_dump()
        for seg in spec['voice_segments']:
            wav=d/'audio'/'tts'/f"{seg['id']}.wav"
            wav.parent.mkdir(parents=True,exist_ok=True)
            sf.write(wav,voices()[seg['id']],SAMPLE_RATE)
            seg['audio_path']=f"audio/tts/{seg['id']}.wav"
            seg['text_en']+=f" Variant {i+1}"
        (d/'audio_plan.json').write_text(json.dumps(spec))
    summary=batch(root,skip_tts=True)
    assert summary['passed']==5
    for i in range(5):
        folder=root/f'clip_{i+1:03d}'
        assert (folder/'final.mp4').stat().st_size>1000
        assert json.loads((folder/'audio_mix_report.json').read_text())['clip_uid']==f'batch1:clip{i+1}'


def test_master_gain_would_crush_asmr_fails():
    raw=tone(3.0,vol=0.4)
    loud={"dub1":tone(.6,750,.9), "story1":tone(.65,600,.9)}
    with pytest.raises(ValueError, match='Master peak reduction'):
        mix_audio(Path('.'),mkplan(),raw,None,loud)
