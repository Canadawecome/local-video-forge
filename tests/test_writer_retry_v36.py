import json,hashlib
from types import SimpleNamespace
import pytest
from test_full_story_v36 import story, synth_voice
from story_coverage_v36 import story_text, seal_script, StoryCoverageError
from full_story_writer_v36 import run, suggest_slots


def test_gpt_writer_rejects_one_fragment_then_writes_all_segments(tmp_path,monkeypatch):
    import full_story_writer_v36 as w
    import story_coverage_v36 as c
    (tmp_path/'clip.mp4').write_bytes(b'demo-media')
    manifest=tmp_path/'clip_evidence'/'evidence_manifest.json'
    manifest.parent.mkdir();manifest.write_text('{}')
    p=story(); seed=p.model_dump();seed['narration_segments']=seed['narration_segments'][:1]
    (tmp_path/'story_plan.json').write_text(json.dumps(seed))
    digest=hashlib.sha256((tmp_path/'clip.mp4').read_bytes()).hexdigest()
    evidence=SimpleNamespace(media_sha256=digest,frames=[SimpleNamespace(id='frame_0000',time_sec=0,path='frames/mock.jpg')])
    monkeypatch.setattr(w,'manifest_from',lambda *x:evidence)
    monkeypatch.setattr(w,'approved_duration',lambda folder:70)
    monkeypatch.setattr(c,'approved_duration',lambda folder:70)
    calls=[]
    good=[{'id':s.id,'text_en':s.text_en,'evidence_refs':['frame_0000']} for s in p.narration_segments]
    def mock_gpt(*args,**kw):
        calls.append('x')
        return {'segments':good[:1] if len(calls)==1 else good}
    monkeypatch.setattr(w,'ask_model',mock_gpt)
    result=run(tmp_path,'test-model',execute=True,max_attempts=2)
    assert result['status']=='COMPLETE_STORY_CREATED' and result['attempt']==2
    assert len(json.loads((tmp_path/'story_plan.json').read_text())['narration_segments'])==len(good)
    assert len(calls)==2


def test_writer_never_overwrites_existing_story_after_three_failed_attempts(tmp_path,monkeypatch):
    import full_story_writer_v36 as w
    (tmp_path/'clip.mp4').write_bytes(b'demo-media')
    e=tmp_path/'clip_evidence'/'evidence_manifest.json';e.parent.mkdir();e.write_text('{}')
    seed=story().model_dump();seed['narration_segments']=seed['narration_segments'][:1]
    original=json.dumps(seed)
    (tmp_path/'story_plan.json').write_text(original)
    sha=hashlib.sha256((tmp_path/'clip.mp4').read_bytes()).hexdigest()
    monkeypatch.setattr(w,'manifest_from',lambda *x:SimpleNamespace(media_sha256=sha,frames=[SimpleNamespace(id='frame_0000',time_sec=0,path='x.jpg')]))
    monkeypatch.setattr(w,'approved_duration',lambda folder:70)
    monkeypatch.setattr(w,'ask_model',lambda *args,**kw:{'segments':[{'id':'story_001','text_en':'Only one line'}]})
    with pytest.raises(ValueError,match='STORY_GENERATION_FAILED_AFTER_RETRIES'):
        run(tmp_path,'test-model',execute=True,max_attempts=3)
    assert (tmp_path/'story_plan.json').read_text()==original
    assert not (tmp_path/'story_coverage_v36.json').exists()
