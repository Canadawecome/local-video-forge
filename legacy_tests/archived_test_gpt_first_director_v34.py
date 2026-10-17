"""Offline regression for v3.4 director; no Opus or OpenAI API charges."""
import json, subprocess, tempfile, shutil
from pathlib import Path
import pytest
from director_workflow_v34 import opus_jobs, review_decision, assert_approved, check_source_mapping
from prepare_video_evidence_v34 import build,sha256
from viral_director_contracts_v34 import PrecutPlan,PostcutReview
from storytelling_render_v34 import process as render_v34


MEDIA_CACHE=Path(tempfile.mkdtemp(prefix='lvf34_test_media_'))

def media(p:Path,portrait=True,duration=16):
    p.parent.mkdir(parents=True,exist_ok=True)
    cached=MEDIA_CACHE/f"{int(portrait)}_{duration}.mp4"
    if cached.is_file():
        shutil.copy2(cached,p)
        return
    size='160x288' if portrait else '288x160'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi',
        '-i',f'testsrc2=size={size}:rate=3','-t',str(duration),'-pix_fmt','yuv420p',str(cached)],
        check=True,capture_output=True)
    shutil.copy2(cached,p)


def fixture(tmp_path):
    source=tmp_path/'source.mp4';media(source,duration=18)
    src_ev=tmp_path/'source_evidence'/'evidence_manifest.json'
    build(source,src_ev.parent,'SOURCE',step_sec=1,max_frames=12)
    precut=tmp_path/'precut_plan.json'
    obj={'source_sha256':sha256(source),'source_duration_sec':18,
         'rights_status':'VERIFIED','analysis_model':'test-vision','production_topic_en':'Knife forging',
         'candidates':[{'id':'C01','start_sec':0,'end_sec':17.9,'hook_at_sec':1,
               'evidence_frame_ids':['frame_0001','frame_0002'],
               'hook_visual':'Bright sparks fly at the bench',
               'actions':['hammering'],'hook_why':'The impact would be visually arresting',
               'asmr_notes':'unverified hammer ASMR potential','narrative_arc':'Heating then shaping then reveal',
               'potential_score':95,'uncertainty_notes':'Sparse frames, audio not reviewed',
               'desired_clip_min_sec':10,'desired_clip_max_sec':20}]}
    precut.write_text(json.dumps(obj))
    clips=tmp_path/'clip_001';clip=clips/'clip.mp4';media(clip,duration=16)
    evidence=clips/'clip_evidence'/'evidence_manifest.json'
    build(clip,evidence.parent,'OPUS_CLIP',step_sec=1,max_frames=9)
    rev=clips/'postcut_review.json'
    r={'source_candidate_id':'C01','clip_sha256':sha256(clip),'clip_duration_sec':16,
       'review_model':'test-vision','review_evidence_frame_ids':['frame_0000','frame_0001','frame_0002'],
       'hook_evidence_frame_ids':['frame_0000'],
       'scores':{'hook':96,'action_asmr':94,'narrative_arc':95,'vertical_framing':95,'pacing':95,'english_story_potential':95},
       'includes_real_mechanical_action':True,'has_obvious_visual_hook':True,'coherent_visual_story':True,
       'subject_framed_correctly':True,'serious_export_defect':False,
       'content_rights_reviewed':True,'mapped_to_planned_source':'UNVERIFIED','model_confidence':0.93,
       'reasons':['Impact visible immediately'],'asmr_warning':'Audio unverified; ASMR must be checked downstream'}
    rev.write_text(json.dumps(r))
    mapping=clips/'source_mapping.json'
    mapping.write_text(json.dumps({'source_candidate_id':'C01','verified_by':'OPUS_PROVIDER',
       'opus_project_id':'demo-project','source_time_ranges':[[0,15800]],
       'time_unit':'MILLISECONDS','evidence_note':'Opus returned source original ranges'}))
    return source,src_ev,precut,clips,evidence,rev,mapping


def test_opus_range_and_prompt(tmp_path):
    _,se,precut,*_=fixture(tmp_path)
    req=opus_jobs(precut,se,'https://www.youtube.com/watch?v=fake')['jobs'][0]['request']
    assert req['curationPref']['model']=='ClipAnything'
    assert req['curationPref']['range']=={'startSec':0.0,'endSec':17.9}
    assert 'real' in req['curationPref']['customPrompt'].lower()


def test_cannot_dispatch_without_rights(tmp_path):
    _,se,precut,*_=fixture(tmp_path)
    obj=json.loads(precut.read_text());obj['rights_status']='UNKNOWN';precut.write_text(json.dumps(obj))
    with pytest.raises(ValueError,match='RIGHTS_NOT_VERIFIED'):opus_jobs(precut,se,'https://example.com/clip.mp4')


def test_wrong_frame_source_rejected(tmp_path):
    _,se,precut,*_=fixture(tmp_path)
    obj=json.loads(precut.read_text());obj['candidates'][0]['evidence_frame_ids']=['guess_60sec'];precut.write_text(json.dumps(obj))
    with pytest.raises(ValueError,match='nonexistent'):opus_jobs(precut,se,'https://example.com/x.mp4')


def test_no_tts_or_render_without_gpt_approval(tmp_path):
    _,_,_,clips,*_=fixture(tmp_path)
    with pytest.raises(ValueError,match='VIRAL_APPROVAL_REQUIRED'):render_v34(clips,dry_run=True)


def test_mapping_units_and_range_validation(tmp_path):
    _,_,precut,clips,_,_,mapping=fixture(tmp_path)
    candidate=PrecutPlan.model_validate_json(precut.read_text()).candidates[0]
    assert check_source_mapping(mapping,candidate)
    obj=json.loads(mapping.read_text());obj['source_time_ranges']=[[500000,510000]]
    mapping.write_text(json.dumps(obj))
    assert not check_source_mapping(mapping,candidate)


def test_high_score_verified_approval(tmp_path):
    _,se,precut,clips,evidence,rev,_=fixture(tmp_path)
    approval=review_decision(clips,rev,evidence,precut,se)
    assert approval.status=='APPROVED'
    assert approval.score>85
    assert_approved(clips)


def test_low_score_recut(tmp_path):
    _,se,precut,clips,evidence,rev,_=fixture(tmp_path)
    data=json.loads(rev.read_text());data['scores']={key:75 for key in data['scores']}
    rev.write_text(json.dumps(data))
    assert review_decision(clips,rev,evidence,precut,se).status=='RECUT'
    with pytest.raises(ValueError,match='VIRAL_NOT_APPROVED'):assert_approved(clips)


def test_low_confidence_hold_even_with_good_score(tmp_path):
    _,se,precut,clips,evidence,rev,_=fixture(tmp_path)
    data=json.loads(rev.read_text());data['model_confidence']=.52;rev.write_text(json.dumps(data))
    assert review_decision(clips,rev,evidence,precut,se).status=='HOLD'


def test_unauthorized_missing_mapping_hold(tmp_path):
    _,se,precut,clips,evidence,rev,mapping=fixture(tmp_path)
    mapping.unlink()
    approval=review_decision(clips,rev,evidence,precut,se)
    assert approval.status=='HOLD' and 'SOURCE_MAPPING_NOT_VERIFIED' in approval.blockers


def test_rights_not_reviewed_hold(tmp_path):
    _,se,precut,clips,evidence,rev,_=fixture(tmp_path)
    data=json.loads(rev.read_text());data['content_rights_reviewed']=False;rev.write_text(json.dumps(data))
    approval=review_decision(clips,rev,evidence,precut,se)
    assert approval.status=='HOLD'


def test_stale_video_blocks_handoff(tmp_path):
    _,se,precut,clips,evidence,rev,_=fixture(tmp_path)
    assert review_decision(clips,rev,evidence,precut,se).status=='APPROVED'
    (clips/'clip.mp4').write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='STALE_APPROVAL'):assert_approved(clips)


def test_stale_pre_cut_plan_blocks_handoff(tmp_path):
    _,se,precut,clips,evidence,rev,_=fixture(tmp_path)
    assert review_decision(clips,rev,evidence,precut,se).status=='APPROVED'
    d=json.loads(precut.read_text());d['production_topic_en']='Steelcraft';precut.write_text(json.dumps(d))
    with pytest.raises(ValueError,match='STALE_APPROVAL'):assert_approved(clips)


def test_frame_evidence_is_real(tmp_path):
    _,src_ev,_,_,_,_,_=fixture(tmp_path)
    data=json.loads(src_ev.read_text())
    assert all((src_ev.parent/f['path']).exists() for f in data['frames'])
    assert all(0<=f['time_sec']<=data['duration_sec'] for f in data['frames'])


def test_bad_portrait_blocks_gpt_approval(tmp_path):
    _,se,precut,clips,evidence,rev,_=fixture(tmp_path)
    # Rebuild media and matching artifacts with landscape dimensions
    media(clips/'clip.mp4',portrait=False,duration=16)
    build(clips/'clip.mp4',evidence.parent,'OPUS_CLIP',step_sec=1,max_frames=9)
    data=json.loads(rev.read_text());data['clip_sha256']=sha256(clips/'clip.mp4');rev.write_text(json.dumps(data))
    a=review_decision(clips,rev,evidence,precut,se)
    assert a.status=='REJECTED' and 'NOT_PORTRAIT' in a.blockers
