#!/usr/bin/env python3
"""v3.5 GPT-first director + hard >65s Opus output duration policy.

Retains v3.4 evidence/rights/score validation. This module is the ONLY
supported director CLI for v3.5. No ElevenLabs API call happens here.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from director_workflow_v34 import (
    opus_jobs as _v34_opus_jobs, review_decision as _v34_review_decision,
    assert_approved as _v34_assert_approved, submit as _v34_submit,
)
from duration_gate_v35 import (
    TARGET_MIN_SEC, TARGET_MAX_SEC, THRESHOLD_SEC,
    check_clip, require_eligible, DurationGateError,
)


def opus_jobs(plan_path:Path, evidence_path:Path, video_url:str) -> dict:
    """Never submit a request asking Opus to generate <=65s clips.

    Candidate source windows under 70 seconds are skipped, not silently widened
    outside GPT's reviewed footage. Human/GPT can plan a longer source window.
    """
    old=_v34_opus_jobs(plan_path,evidence_path,video_url)
    jobs=[];skipped=[]
    for job in old['jobs']:
        a,b=job['source_window']
        window_sec=b-a
        if window_sec < TARGET_MIN_SEC:
            skipped.append({'candidate_id':job['candidate_id'],'source_window':[a,b],
                            'status':'NEEDS_LONGER_SOURCE_WINDOW',
                            'reason':f'Source window {window_sec:.3f}s is shorter than {TARGET_MIN_SEC}s target'})
            continue
        old_ranges=job['request']['curationPref']['clipDurations']
        old_min=old_ranges[0][0]
        # If the original plan asked for >=70s, honor that within the source bounds;
        # otherwise upgrade from the old short defaults to 70s.
        target_min=max(TARGET_MIN_SEC,old_min)
        target_max=min(180,max(target_min,TARGET_MAX_SEC),int(window_sec))
        if target_max < target_min:
            skipped.append({'candidate_id':job['candidate_id'],'source_window':[a,b],
                            'status':'NEEDS_LONGER_SOURCE_WINDOW','reason':'Cannot satisfy requested target length'})
            continue
        job['request']['curationPref']['clipDurations']=[[target_min,target_max]]
        job['request']['curationPref']['customPrompt'] += (
            f' REQUIRED: return a clip strictly longer than {THRESHOLD_SEC:.0f} seconds; '
            f'aim for {target_min}-{target_max} seconds. Final exported duration will be verified '
            'by FFprobe and clips <=65 seconds will be rejected before narration.')
        job['duration_policy']='FFPROBE_STRICT_GREATER_THAN_65S'
        jobs.append(job)
    return {'schema_version':'3.5','mode':'GPT_FIRST_VIRAL_DIRECTOR',
            'min_export_duration_exclusive_sec':THRESHOLD_SEC,
            'opus_target_sec':[TARGET_MIN_SEC,TARGET_MAX_SEC],
            'rights_checked':True,'precut_plan_sha256':old['precut_plan_sha256'],
            'source_evidence_sha256':old['source_evidence_sha256'],
            'jobs':jobs,'skipped_candidates':skipped}


def review_decision(clip_folder:Path, review_path:Path, clip_manifest_path:Path,
                    plan_path:Path, source_evidence_path:Path):
    """Enforce duration before invoking/accepting costly GPT postcut review.

    On fail, create a non-approved duration receipt; cannot claim review success.
    """
    require_eligible(clip_folder)
    return _v34_review_decision(clip_folder,review_path,clip_manifest_path,
                                plan_path,source_evidence_path)


def assert_approved(clip_folder:Path):
    """Mandatory re-probe before TTS call and render; rejects old approvals for shorts."""
    require_eligible(clip_folder)
    return _v34_assert_approved(clip_folder)


def tts_handoff(clip_folder:Path)->dict:
    """Paid ElevenLabs adapter MUST call this in the same job immediately before TTS."""
    approval=assert_approved(clip_folder)
    from story_coverage_v36 import require_sealed_script
    story_gate=require_sealed_script(clip_folder)  # no ElevenLabs without complete and sealed story
    duration=check_clip(clip_folder)
    return {
        'policy_version':'3.6',
        'story_gate':story_gate,
        'can_call_elevenlabs':True,
        'duration_sec':duration['actual_duration_sec'],
        'clip_sha256':duration['media_sha256'],
        'viral_approval':'APPROVED',
        'viral_review_score':approval.score,
        'next_step':'CREATE_ENGLISH_STORY_THEN_ELEVENLABS'
    }


def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='cmd',required=True)
    a=s.add_parser('opus-jobs');a.add_argument('--precut',type=Path,required=True);a.add_argument('--source-evidence',type=Path,required=True);a.add_argument('--source-url',required=True);a.add_argument('--output',type=Path,required=True)
    a=s.add_parser('decide');a.add_argument('--clip-folder',type=Path,required=True);a.add_argument('--review',type=Path,required=True);a.add_argument('--clip-evidence',type=Path,required=True);a.add_argument('--precut',type=Path,required=True);a.add_argument('--source-evidence',type=Path,required=True)
    a=s.add_parser('gate');a.add_argument('--clip-folder',type=Path,required=True)
    a=s.add_parser('tts-handoff');a.add_argument('--clip-folder',type=Path,required=True)
    a=s.add_parser('submit-opus');a.add_argument('--jobs',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--execute',action='store_true')
    a=p.parse_args()
    if a.cmd=='opus-jobs':
        r=opus_jobs(a.precut,a.source_evidence,a.source_url)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(r,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps({'jobs':len(r['jobs']),'skipped':len(r['skipped_candidates']),'output':str(a.output)},ensure_ascii=False))
    elif a.cmd=='decide':
        if a.clip_evidence.resolve() != (a.clip_folder/'clip_evidence'/'evidence_manifest.json').resolve():
            raise ValueError('Evidence path must live at clip_folder/clip_evidence/evidence_manifest.json')
        result=review_decision(a.clip_folder,a.review,a.clip_evidence,a.precut,a.source_evidence)
        print(result.model_dump_json(indent=2))
    elif a.cmd=='gate':print(assert_approved(a.clip_folder).model_dump_json(indent=2))
    elif a.cmd=='tts-handoff':print(json.dumps(tts_handoff(a.clip_folder),indent=2,ensure_ascii=False))
    else:
        # v3.4 submission validates schema_version=3.4. Preserve request formatting
        # but explicitly replace only the batch marker for transport; duration fields
        # remain present inside provider request.
        job_data=json.loads(a.jobs.read_text(encoding='utf-8'))
        if job_data.get('schema_version')!='3.5':raise ValueError('v3.5 jobs required')
        if not job_data.get('rights_checked'):raise ValueError('Source rights not verified')
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as td:
            temp=Path(td)/'opus_jobs_transport.json'
            job_data['schema_version']='3.4'
            temp.write_text(json.dumps(job_data),encoding='utf-8')
            print(json.dumps(_v34_submit(temp,a.execute,a.output),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
