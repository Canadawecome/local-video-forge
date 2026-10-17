"""v3.3 source-origin, provenance and speech QC regressions; no live API calls."""
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from storytelling_contracts_v33 import StorytellingPlan, SourceContext
from story_claim_guard_v33 import detected_geography
from source_profile_from_asr_v33 import build_profile
from migrate_v32_to_v33 import migrate
from storytelling_render_v33 import process,sha256
from test_storytelling_v31 import make_fixture


def base():
    return {'schema_version':'3.3','clip_uid':'korean_damascus',
      'rights_status':'VERIFIED','music_rights_status':'NO_MUSIC',
      'source_context':{'source_language':'ko','source_language_status':'CONFIRMED',
          'language_evidence_refs':['asr:ko:clip01'], 'source_country':None,
          'source_country_status':'UNKNOWN','topic_en':'Knife forging'},
      'source_speech_status':'CONFIRMED_ABSENT',
      'narration_segments':[{'id':'n1','start':0.1,'end':2.5,
          'text_en':'The hammer shapes this blade.','evidence_refs':['frame:001']}]}

def test_korean_language_does_not_imply_korean_location():
    p=StorytellingPlan.model_validate(base())
    assert p.source_context.source_language=='ko'
    assert p.source_context.source_country is None

def test_unknown_origin_blocks_false_german_workshop():
    b=base();b['narration_segments'][0]['text_en']='In this German workshop, a knife takes shape.'
    with pytest.raises(ValidationError,match='UNSUPPORTED_COUNTRY_CLAIM'):
        StorytellingPlan.model_validate(b)

def test_unknown_origin_blocks_false_korean_workshop_and_seoul():
    for line in ('A Korean craftsman hammers the blade.','In Seoul, the blade is polished.'):
        b=base();b['narration_segments'][0]['text_en']=line
        with pytest.raises(ValidationError,match='UNSUPPORTED_COUNTRY_CLAIM'):
            StorytellingPlan.model_validate(b)

def test_verified_korean_country_allows_korean_reference():
    b=base()
    b['source_context'].update(source_country='KR',source_country_status='VERIFIED',
       country_evidence_refs=['creator_official_about:01'],country_reviewed_by='editor1')
    b['narration_segments'][0]['text_en']='In this Korean workshop, the hammer shapes the blade.'
    p=StorytellingPlan.model_validate(b)
    assert p.source_context.source_country=='KR'
    b['narration_segments'][0]['text_en']='A German craftsman hammers the blade.'
    with pytest.raises(ValidationError,match='UNSUPPORTED_COUNTRY_CLAIM'):
        StorytellingPlan.model_validate(b)

def test_japanese_language_not_japanese_country():
    b=base();b['source_context']['source_language']='ja'
    b['source_context']['language_evidence_refs']=['asr:ja:clip02']
    StorytellingPlan.model_validate(b)
    b['narration_segments'][0]['text_en']='A Japanese workshop is forging a knife.'
    with pytest.raises(ValidationError,match='UNSUPPORTED_COUNTRY_CLAIM'):
        StorytellingPlan.model_validate(b)

def test_language_confirmation_needs_evidence():
    b=base();b['source_context']['language_evidence_refs']=[]
    with pytest.raises(ValidationError,match='evidence'): StorytellingPlan.model_validate(b)

def test_unknown_country_must_be_null():
    b=base();b['source_context']['source_country']='DE'
    with pytest.raises(ValidationError,match='Unknown country'): StorytellingPlan.model_validate(b)

def test_country_verified_requires_reviewer_and_evidence():
    b=base();b['source_context'].update(source_country='KR',source_country_status='VERIFIED')
    with pytest.raises(ValidationError,match='evidence'): StorytellingPlan.model_validate(b)

def test_legacy_german_only_fields_rejected():
    b=base();b['german_speech_status']='CONFIRMED_ABSENT'
    with pytest.raises(ValidationError,match='german_speech_status'): StorytellingPlan.model_validate(b)

def test_multilingual_speech_requires_whole_clean_bed():
    b=base();b.update(source_speech_status='CONFIRMED_PRESENT',
        source_speech=[{'id':'ko1','start':.2,'end':.7,'language':'ko'},
                       {'id':'ja1','start':1.2,'end':2.3,'language':'ja'}])
    with pytest.raises(ValidationError,match='approved speech-free workshop stem'):
        StorytellingPlan.model_validate(b)

def test_asr_builder_never_derives_country_from_korean():
    ctx=build_profile({'language_detection':{'language':'ko','confidence':.98,'evidence_ref':'asr:1'},
                       'topic_en':'Knife forging'})
    assert ctx.source_language=='ko' and ctx.source_country is None
    low=build_profile({'language_detection':{'language':'ja','confidence':.45,'evidence_ref':'asr:1'},
                       'topic_en':'Knife forging'})
    assert low.source_language=='und'

def test_japanese_demonym_detection():
    assert detected_geography('This Japanese craft method is shown.') == [{'word':'Japanese','country_code':'JP'}]
    assert detected_geography('In North Korea, ...')[0]['country_code']=='KP'

def test_korean_full_render_with_correct_source_schema(tmp_path):
    d=make_fixture(tmp_path/'ko')
    obj=json.loads((d/'story_plan.json').read_text())
    obj['source_context']['source_language']='ko'
    obj['source_context']['language_evidence_refs']=['asr:ko:1']
    obj['source_speech'][0]['language']='ko'
    obj['source_speech'][0]['transcript']='검을 만듭니다'
    (d/'story_plan.json').write_text(json.dumps(obj))
    rep=process(d)
    assert rep['source_language']=='ko'
    assert rep['source_country_status']=='UNKNOWN'
    assert rep['source_speech_status']=='CONFIRMED_PRESENT'
    assert rep['replacement_stem_used']
    assert rep['workshop_bed_never_ducked_for_english_voice']
    assert (d/'final.mp4').is_file()

def test_bad_german_qc_flag_rejected_in_v33(tmp_path):
    d=make_fixture(tmp_path/'c')
    q=d/'audio'/'replacement_qc.json'
    obj=json.loads(q.read_text());obj['german_voice_absent']=obj.pop('source_voice_absent')
    q.write_text(json.dumps(obj))
    with pytest.raises(ValueError,match='speech/ASMR approval'): process(d)

def test_unknown_country_rejected_from_description(tmp_path):
    d=make_fixture(tmp_path/'c')
    (d/'description.txt').write_text('Forging a knife in Germany')
    with pytest.raises(ValueError,match='UNSUPPORTED_COUNTRY_CLAIM'):process(d)

def test_migration_resets_german_only_qc(tmp_path):
    d=make_fixture(tmp_path/'c')
    obj=json.loads((d/'story_plan.json').read_text())
    obj['schema_version']='3.1'
    obj['german_speech_status']=obj.pop('source_speech_status')
    obj['source_german_speech']=[{'id':'de1','start':.5,'end':1.4,'text_de':'Hammer'}]
    obj.pop('source_speech'); obj.pop('source_context')
    (d/'story_plan.json').write_text(json.dumps(obj))
    r=migrate(d,write=True)
    assert r['plan']['source_speech_status']=='UNCERTAIN'
    assert r['plan']['source_context']['source_country'] is None
    assert not r['plan']['workshop_stem_qc_passed']
    assert (d/'story_plan.v32.backup.json').exists()
    assert (d/'audio'/'replacement_qc.v32.backup.json').exists()
    with pytest.raises(ValidationError): StorytellingPlan.model_validate(r['plan'])
