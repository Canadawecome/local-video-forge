"""v3.6 regression: a one-fragment English story can never reach ElevenLabs/render."""
import json
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
from storytelling_contracts_v33 import StorytellingPlan
from story_coverage_v36 import (assess_story,seal_script,require_sealed_script,verify_all_tts,
                                 StoryCoverageError, story_text)
from full_story_writer_v36 import suggest_slots
from elevenlabs_full_story_v36 import generate


def story(length=70.0):
    slots=suggest_slots(length)
    texts=[
        'The first sparks fly as the hot steel meets the hammer, revealing the difficult task ahead.',
        'Each careful strike reshapes the glowing metal while the craftsman checks how the edge is developing.',
        'Now the blade is turned over, exposing a new surface that still needs precision and patience.',
        'The grinding wheel slowly works along the steel, removing rough marks left by earlier forging.',
        'A closer view reveals subtle changes across the metal as the tool moves from side to side.',
        'The craftsman returns to the workbench, adjusting his grip before continuing the delicate shaping process.',
        'As the finishing stage approaches, fine details become easier to see under the workshop lights.',
        'The final close view shows how repeated careful movements have transformed the original rough piece of metal.',
        'One more slow pass refines the surface, revealing the result of this long and methodical process.',
        'A final inspection shows the small details that make precision metalworking so visually satisfying.',
        'The finished shape is checked from multiple angles as the craftsman examines the polished steel closely.',
        'What began as a rough piece has become a carefully shaped tool through many demanding steps.'
    ]
    segments=[{**slot,'text_en':texts[i], 'evidence_refs':['frame_0000'],
               'audio_path':f'audio/tts/{slot["id"]}.wav'} for i,slot in enumerate(slots)]
    data={'schema_version':'3.3','clip_uid':'case','mode':'ENGLISH_STORYTELLING_WITH_CLEAN_ASMR',
          'rights_status':'VERIFIED','music_rights_status':'NO_MUSIC',
          'source_context':{'source_language':'und','source_language_status':'UNDETERMINED',
          'source_country':None,'source_country_status':'UNKNOWN','topic_en':'metalworking'},
          'source_speech_status':'CONFIRMED_ABSENT','source_speech':[], 'protected_asmr':[],
          'narration_segments':segments}
    return StorytellingPlan.model_validate(data)

@pytest.fixture
def sealed(tmp_path,monkeypatch):
    import story_coverage_v36 as v
    monkeypatch.setattr(v,'approved_duration',lambda folder:70.0)
    p=story()
    (tmp_path/'clip.mp4').write_bytes(b'fake-clip-for-story-coverage-unit-tests')
    (tmp_path/'story_plan.json').write_text(p.model_dump_json(indent=2),encoding='utf8')
    (tmp_path/'script_en.txt').write_text(story_text(p)+'\n',encoding='utf8')
    (tmp_path/'script_tts.txt').write_text(' '.join(s.text_en for s in p.narration_segments)+'\n',encoding='utf8')
    seal_script(tmp_path)
    return tmp_path


def synth_voice(folder,plan,omit=None,scale=1.0):
    for s in plan.narration_segments:
        if s.id==omit:continue
        # Audible synthetic audio with word-level time stamps (offline fixture).
        d=(s.end-s.start)*scale
        sr=16000
        samples=(0.055*np.sin(2*np.pi*220*np.arange(round(sr*d))/sr)).astype('float32')
        file=folder/s.audio_path;file.parent.mkdir(parents=True,exist_ok=True)
        sf.write(file,samples,sr)
        chars=list(s.text_en)
        n=len(chars)
        alignment={'characters':chars,
                   'character_start_times_seconds':[i*d/n for i in range(n)],
                   'character_end_times_seconds':[(i+1)*d/n for i in range(n)]}
        file.with_suffix('.alignment.json').write_text(json.dumps({'alignment':alignment}),encoding='utf8')


def test_scheduled_slots_distributed_for_70_and_95_seconds():
    for length in (66,70,95,130):
        ss=suggest_slots(length)
        assert len(ss)>=7 and ss[0]['start']<=5 and ss[-1]['end']>=length-8
        assert sum(s['end']-s['start'] for s in ss)/length >=.74


def test_one_fragment_rejected_even_if_hundred_words():
    plan=story().model_copy(deep=True)
    plan.narration_segments=plan.narration_segments[:1]
    with pytest.raises(StoryCoverageError,match='STORY_TOO_SHORT'):
        assess_story(plan,70)


def test_short_script_across_all_slots_rejected():
    p=story().model_copy(deep=True)
    for s in p.narration_segments:s.text_en='The blacksmith hits the steel repeatedly.'
    with pytest.raises(StoryCoverageError,match='STORY_TOO_SHORT'):
        assess_story(p,70)


def test_full_writing_passes_and_has_words():
    result=assess_story(story(),70)
    assert result['segments']>=7 and result['words']>=107 and result['planned_coverage_ratio']>.70


def test_sealed_story_matches_all_segments(sealed):
    x=require_sealed_script(sealed)
    assert x['segments']>=7
    assert x['status']=='PASS_FULL_STORY_TEXT'


def test_short_full_script_mismatch_is_rejected(sealed):
    (sealed/'script_en.txt').write_text('only first sentence',encoding='utf8')
    with pytest.raises(StoryCoverageError,match='STORY_STALE_OR_CHANGED'):
        require_sealed_script(sealed)


def test_patched_partial_plan_invalidates_script_proof(sealed):
    d=json.loads((sealed/'story_plan.json').read_text())
    d['narration_segments']=d['narration_segments'][:1]
    (sealed/'story_plan.json').write_text(json.dumps(d),encoding='utf8')
    with pytest.raises(StoryCoverageError,match='STORY_STALE_OR_CHANGED'):
        require_sealed_script(sealed)


def test_missing_middle_tts_blocks_render(sealed):
    p=story();synth_voice(sealed,p,omit=p.narration_segments[3].id)
    with pytest.raises(StoryCoverageError,match='TTS_INCOMPLETE'):
        verify_all_tts(sealed)


def test_all_tts_with_alignment_pass(sealed):
    p=story();synth_voice(sealed,p)
    result=verify_all_tts(sealed)
    assert result['tts_segments']==len(p.narration_segments)
    assert result['actual_tts_coverage_ratio']>.70


def test_fast_truncated_voice_rejected(sealed):
    p=story();synth_voice(sealed,p,scale=.23)
    with pytest.raises(StoryCoverageError,match='TTS_TRUNCATED_OR_TOO_FAST'):
        verify_all_tts(sealed)


def test_bad_alignment_detected(sealed):
    p=story();synth_voice(sealed,p)
    s=p.narration_segments[2]
    f=sealed/s.audio_path
    q=f.with_suffix('.alignment.json')
    d=json.loads(q.read_text());d['alignment']['characters'][0]='X'
    q.write_text(json.dumps(d),encoding='utf8')
    with pytest.raises(ValueError,match='alignment does not match'):
        verify_all_tts(sealed)


def test_tts_dry_run_lists_every_segment_without_api(sealed,monkeypatch):
    monkeypatch.delenv('ELEVENLABS_API_KEY',raising=False)
    result=generate(sealed,False)
    assert result['status']=='DRY_RUN_NO_PAID_API_CALL'
    assert len(result['segments_to_generate'])==len(story().narration_segments)


def test_v35_handoff_requires_new_story_gate(tmp_path,monkeypatch):
    import director_workflow_v35 as d
    monkeypatch.setattr(d,'assert_approved',lambda folder: type('Review',(),{'status':'APPROVED','score':96})())
    with pytest.raises(StoryCoverageError,match='STORY_NOT_SEALED'):
        d.tts_handoff(tmp_path)


def test_core_renderer_cannot_bypass_coverage(tmp_path,monkeypatch):
    import director_workflow_v35 as d
    import storytelling_render_v33 as renderer
    monkeypatch.setattr(d,'assert_approved',lambda folder:None)
    with pytest.raises(StoryCoverageError,match='STORY_NOT_SEALED'):
        renderer.process(tmp_path,dry_run=True)
