"""v3.5 Duration Gate: real FFprobe media, GPT/rights review approval, paid TTS gate.
Runs offline; no model, OpusClip or ElevenLabs charges.
"""
from __future__ import annotations
import json, math, subprocess
from pathlib import Path
import pytest

from duration_gate_v35 import check_clip, require_eligible, probe_actual_duration, is_eligible, DurationGateError
from director_workflow_v35 import opus_jobs, review_decision, assert_approved, tts_handoff
from viral_director_contracts_v34 import PrecutPlan
from prepare_video_evidence_v34 import build,sha256
from ingest_opus_batch_v35 import ingest
from storytelling_render_v35 import process as render_v35


def make_mp4(p:Path, seconds:float,portrait=True):
    p.parent.mkdir(parents=True,exist_ok=True)
    size='144x256' if portrait else '256x144'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y',
       '-f','lavfi','-i',f'color=c=0x3a3a3a:size={size}:rate=4',
       '-t',str(seconds),'-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',str(p)],
       check=True,capture_output=True)

@pytest.fixture(scope='module')
def video_library(tmp_path_factory):
    root=tmp_path_factory.mktemp('videos_v35')
    clips={}
    for secs in (64.75,65.0,65.25,70.0,78.0):
        fp=root/f'video_{str(secs).replace(".","_")}.mp4'
        make_mp4(fp,secs)
        clips[secs]=fp
    return clips


def test_strict_math_boundary():
    assert not is_eligible(65)
    assert not is_eligible(64.9999999)
    assert is_eligible(65.0000001)
    assert not is_eligible(float('nan'))
    assert not is_eligible(float('inf'))
    assert not is_eligible('N/A')

@pytest.mark.parametrize('length,valid',[(64.75,False),(65.0,False),(65.25,True),(70.0,True)])
def test_actual_ffprobe_boundary(tmp_path,video_library,length,valid):
    folder=tmp_path/'clip_001';folder.mkdir()
    import shutil
    shutil.copy2(video_library[length],folder/'clip.mp4')
    record=check_clip(folder)
    assert record['eligible'] is valid
    assert abs(record['actual_duration_sec']-length)<.01
    assert (folder/'duration_gate_v35.json').is_file()
    if valid:
        assert require_eligible(folder)['eligible']
    else:
        with pytest.raises(DurationGateError,match='DURATION_NOT_OVER_65S'):
            require_eligible(folder)


def test_corrupt_export_fails_closed(tmp_path):
    folder=tmp_path/'short';folder.mkdir()
    (folder/'clip.mp4').write_bytes(b'not a real MP4')
    with pytest.raises(DurationGateError,match='FFPROBE_FAILED'):
        require_eligible(folder)


def build_video_case(root,video_library):
    import shutil
    src=root/'source.mp4';shutil.copy2(video_library[78.0],src)
    source_ev=root/'source_evidence'/'evidence_manifest.json'
    build(src,source_ev.parent,'SOURCE',step_sec=8,max_frames=12)
    plan=root/'precut_plan.json'
    plan.write_text(json.dumps({
        'source_sha256':sha256(src),'source_duration_sec':probe_actual_duration(src),
        'rights_status':'VERIFIED','analysis_model':'test-vision','production_topic_en':'Knife forging',
        'candidates':[
            {'id':'C_long','start_sec':0,'end_sec':76,'hook_at_sec':0,
             'evidence_frame_ids':['frame_0000','frame_0001'],
             'hook_visual':'A glowing piece of metal struck by hammer',
             'actions':['hammering'],'hook_why':'Glowing metal with visible sparks',
             'asmr_notes':'potential impact sounds unverified',
             'narrative_arc':'Forge heating followed by shaping and reveal',
             'potential_score':96,'uncertainty_notes':'Audio not reviewed',
             'desired_clip_min_sec':45,'desired_clip_max_sec':90},
            {'id':'C_short','start_sec':0,'end_sec':45,'hook_at_sec':0,
             'evidence_frame_ids':['frame_0000','frame_0001'],
             'hook_visual':'A glowing piece of metal struck by hammer',
             'actions':['hammering'],'hook_why':'Glowing metal with visible sparks',
             'asmr_notes':'potential impact sounds unverified',
             'narrative_arc':'Forge heating followed by shaping and reveal',
             'potential_score':90,'uncertainty_notes':'Audio not reviewed',
             'desired_clip_min_sec':20,'desired_clip_max_sec':45}]}
    ))
    folder=root/'clip_001';folder.mkdir()
    shutil.copy2(video_library[70.0],folder/'clip.mp4')
    evidence=folder/'clip_evidence'/'evidence_manifest.json'
    build(folder/'clip.mp4',evidence.parent,'OPUS_CLIP',step_sec=8,max_frames=12)
    review=folder/'postcut_review.json'
    review.write_text(json.dumps({
        'source_candidate_id':'C_long','clip_sha256':sha256(folder/'clip.mp4'),
        'clip_duration_sec':probe_actual_duration(folder/'clip.mp4'),
        'review_model':'test-vision',
        'review_evidence_frame_ids':['frame_0000','frame_0001','frame_0002'],
        'hook_evidence_frame_ids':['frame_0000'],
        'scores':{'hook':96,'action_asmr':94,'narrative_arc':95,'vertical_framing':95,'pacing':95,'english_story_potential':95},
        'includes_real_mechanical_action':True,'has_obvious_visual_hook':True,
        'coherent_visual_story':True,'subject_framed_correctly':True,
        'serious_export_defect':False,'content_rights_reviewed':True,
        'mapped_to_planned_source':'UNVERIFIED','model_confidence':0.93,
        'reasons':['Visible impact immediately'],
        'asmr_warning':'Audio needs independent QC before publication'}))
    (folder/'source_mapping.json').write_text(json.dumps({
        'source_candidate_id':'C_long','verified_by':'HUMAN_EDITOR',
        'human_reviewer':'test-reviewer','source_time_ranges':[[0,70]],
        'time_unit':'SECONDS','evidence_note':'Verified in original MP4 timeline'}))
    return plan,source_ev,folder,evidence,review


def test_opus_min_70_only_and_short_source_skipped(tmp_path,video_library):
    plan,source_ev,*_=build_video_case(tmp_path,video_library)
    data=opus_jobs(plan,source_ev,'https://example.com/source.mp4')
    assert data['schema_version']=='3.5'
    assert len(data['jobs'])==1
    assert data['jobs'][0]['candidate_id']=='C_long'
    assert data['jobs'][0]['request']['curationPref']['clipDurations']==[[70,76]]
    assert len(data['skipped_candidates'])==1
    assert data['skipped_candidates'][0]['candidate_id']=='C_short'


def test_approved_over_65_passes_tts_handoff(tmp_path,video_library):
    plan,se,folder,evidence,review=build_video_case(tmp_path,video_library)
    a=review_decision(folder,review,evidence,plan,se)
    assert a.status=='APPROVED'
    # v3.6 changes expected behavior: no paid TTS handoff immediately after viral approval.
    # The full English story must be authored, distributed across the clip and sealed.
    from story_coverage_v36 import StoryCoverageError, seal_script, story_text
    from test_full_story_v36 import story
    with pytest.raises(StoryCoverageError,match='STORY_NOT_SEALED'):
        tts_handoff(folder)
    full_plan=story()
    (folder/'story_plan.json').write_text(full_plan.model_dump_json(indent=2),encoding='utf8')
    (folder/'script_en.txt').write_text(story_text(full_plan)+'\n',encoding='utf8')
    (folder/'script_tts.txt').write_text(' '.join(s.text_en for s in full_plan.narration_segments)+'\n',encoding='utf8')
    seal_script(folder)
    r=tts_handoff(folder)
    assert r['can_call_elevenlabs'] and r['duration_sec']==70
    assert r['story_gate']['segments']>=7
    assert assert_approved(folder).status=='APPROVED'


def test_short_export_cannot_get_approval_or_paid_handoff(tmp_path,video_library):
    import shutil
    plan,se,folder,evidence,review=build_video_case(tmp_path,video_library)
    shutil.copy2(video_library[65.0],folder/'clip.mp4')
    with pytest.raises(DurationGateError,match='DURATION_NOT_OVER_65S'):
        review_decision(folder,review,evidence,plan,se)
    with pytest.raises(DurationGateError,match='DURATION_NOT_OVER_65S'):
        tts_handoff(folder)
    with pytest.raises(DurationGateError,match='DURATION_NOT_OVER_65S'):
        render_v35(folder,dry_run=True)


def test_old_approval_16sec_rejected_in_v35(tmp_path,video_library):
    import shutil
    plan,se,folder,evidence,review=build_video_case(tmp_path,video_library)
    assert review_decision(folder,review,evidence,plan,se).status=='APPROVED'
    # Approved 70s MP4 is replaced by a valid but too-short 65s MP4.
    shutil.copy2(video_library[65.0],folder/'clip.mp4')
    with pytest.raises(DurationGateError,match='DURATION_NOT_OVER_65S'):
        assert_approved(folder)


def test_stale_approval_for_eligible_changed_clip_blocked(tmp_path,video_library):
    import shutil
    plan,se,folder,evidence,review=build_video_case(tmp_path,video_library)
    assert review_decision(folder,review,evidence,plan,se).status=='APPROVED'
    shutil.copy2(video_library[65.25],folder/'clip.mp4')
    with pytest.raises(ValueError,match='STALE_APPROVAL'):
        assert_approved(folder)


def test_batch_ingest_early_classification(tmp_path,video_library):
    import shutil
    exports=tmp_path/'exports';exports.mkdir()
    shutil.copy2(video_library[65.0],exports/'short.mp4')
    shutil.copy2(video_library[70.0],exports/'long.mp4')
    result=ingest(exports,tmp_path/'imported',rights_reviewed=True)
    assert result['duration_pass_count']==1
    assert result['duration_blocked_count']==1
    assert {r['status'] for r in result['items']}=={
        'RECUT_REQUIRED_DURATION','DURATION_PASS_AWAIT_GPT_REVIEW'}


def test_old_renderers_cannot_bypass_duration(tmp_path,video_library):
    import shutil
    from storytelling_render_v33 import process as old_v33_renderer
    from storytelling_render_v34 import process as old_v34_renderer
    folder=tmp_path/'clip_unsafe';folder.mkdir()
    shutil.copy2(video_library[65.0],folder/'clip.mp4')
    for renderer in (old_v33_renderer,old_v34_renderer):
        with pytest.raises(DurationGateError,match='DURATION_NOT_OVER_65S'):
            renderer(folder,dry_run=True)


def test_pre_review_adapter_does_not_consume_api_on_short(tmp_path,video_library):
    import shutil
    from gpt_vision_adapter_v34 import run_review
    folder=tmp_path/'clip_short';folder.mkdir()
    shutil.copy2(video_library[65.0],folder/'clip.mp4')
    evidence=folder/'clip_evidence'/'evidence_manifest.json'
    build(folder/'clip.mp4',evidence.parent,'OPUS_CLIP',step_sec=10,max_frames=10)
    # Neither OPENAI_API_KEY nor model connection is supplied: duration is rejected first.
    with pytest.raises(DurationGateError,match='DURATION_NOT_OVER_65S'):
        run_review(evidence,folder/'postcut_review.json',model='unavailable-test-model',candidate_id='x')


def test_long_without_gpt_review_cannot_call_elevenlabs(tmp_path,video_library):
    import shutil
    folder=tmp_path/'clip_001';folder.mkdir()
    shutil.copy2(video_library[70.0],folder/'clip.mp4')
    with pytest.raises(ValueError,match='VIRAL_APPROVAL_REQUIRED'):
        tts_handoff(folder)
