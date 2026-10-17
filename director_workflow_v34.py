#!/usr/bin/env python3
"""GPT-first director guardrails: precut -> Opus requests -> postcut review -> approved handoff.

No TTS/API model calls are made here; model outputs MUST be attached and validated.
"""
from __future__ import annotations
import argparse, hashlib, json, os, urllib.request, urllib.error
from pathlib import Path
from viral_director_contracts_v34 import EvidenceManifest, PrecutPlan, PostcutReview, Approval, SourceMapping
from prepare_video_evidence_v34 import sha256


def read_json(p:Path):
    return json.loads(p.read_text(encoding='utf-8'))


def manifest_from(path:Path, kind:str) -> EvidenceManifest:
    m=EvidenceManifest.model_validate(read_json(path))
    if m.media_kind!=kind:raise ValueError(f'Expected {kind} evidence')
    if not Path(m.media_file).is_file():raise FileNotFoundError(m.media_file)
    if sha256(Path(m.media_file))!=m.media_sha256:
        raise ValueError('Evidence stale: input media changed')
    for frame in m.frames:
        if not (path.parent/frame.path).is_file():raise ValueError(f'Evidence missing frame: {frame.path}')
    return m


def verify_precut(plan_path:Path, evidence_path:Path):
    plan=PrecutPlan.model_validate(read_json(plan_path))
    m=manifest_from(evidence_path,'SOURCE')
    if plan.rights_status!='VERIFIED':raise ValueError('RIGHTS_NOT_VERIFIED: Opus dispatch blocked')
    if plan.source_sha256!=m.media_sha256 or abs(plan.source_duration_sec-m.duration_sec)>.20:
        raise ValueError('Source plan stale/mismatched evidence')
    by_id={f.id:f for f in m.frames}
    for c in plan.candidates:
        missing=set(c.evidence_frame_ids)-set(by_id)
        if missing:raise ValueError(f'{c.id}: nonexistent frame IDs: {sorted(missing)}')
        if not any(c.start_sec-1 <= by_id[i].time_sec <= c.end_sec+1 for i in c.evidence_frame_ids):
            raise ValueError(f'{c.id}: no evidence frames inside requested window')
        if not any(abs(by_id[i].time_sec-c.hook_at_sec)<=5 for i in c.evidence_frame_ids):
            raise ValueError(f'{c.id}: hook time unsupported by sampled frames (refine at 0.5s)')
    return plan,m


def opus_jobs(plan_path:Path, evidence_path:Path, video_url:str) -> dict:
    plan,_=verify_precut(plan_path,evidence_path)
    if not video_url.startswith(('https://','http://')) or ' ' in video_url:
        raise ValueError('Opus requires a valid network-accessible video URL')
    jobs=[]
    # Range is on SOURCE timeline; Opus still performs its own curation inside this window.
    for c in sorted(plan.candidates,key=lambda c:c.potential_score,reverse=True):
        avail=c.end_sec-c.start_sec
        hi=min(c.desired_clip_max_sec, max(10,int(avail)))
        lo=min(c.desired_clip_min_sec,hi)
        payload={'videoUrl':video_url,
          'curationPref':{'model':'ClipAnything',
            'range':{'startSec':round(c.start_sec,3),'endSec':round(c.end_sec,3)},
            'clipDurations':[[lo,hi]],
            'genre':'Blacksmith / restoration / workshop craft',
            'customPrompt':(
              f'Prioritize the visible REAL workshop action: {"; ".join(c.actions)}. '
              f'The most compelling hook action occurs around source time {c.hook_at_sec:.1f}s: {c.hook_visual}. '
              'Make a coherent vertical craft-process clip with an opening visual hook. '
              'Avoid static talking-head passages, fabricated steps, flashy transitions, '
              'added music and unnecessary on-screen captions where controls permit. '
              'Preserve natural chronological causality; retain usable source audio for later separation. '
              f'Visual storyline: {c.narrative_arc}.')},
          'renderPref':{'layoutAspectRatio':'portrait'}}
        jobs.append({'candidate_id':c.id,'priority_score':c.potential_score,
                     'source_sha256':plan.source_sha256,
                     'source_window':[c.start_sec,c.end_sec],
                     'request':payload,'status':'READY_FOR_OPUS_SUBMIT'})
    return {'schema_version':'3.4','mode':'GPT_FIRST_VIRAL_DIRECTOR',
            'rights_checked':True,'precut_plan_sha256':sha256(plan_path),
            'source_evidence_sha256':sha256(evidence_path),'jobs':jobs}


def check_source_mapping(mapping_path:Path, candidate) -> bool:
    if not mapping_path.is_file():return False
    try:
        m=SourceMapping.model_validate(read_json(mapping_path))
        if m.source_candidate_id!=candidate.id:return False
        scale=0.001 if m.time_unit=='MILLISECONDS' else 1.0
        ranges=[(a*scale,b*scale) for a,b in m.source_time_ranges]
        total=sum(b-a for a,b in ranges)
        inside=sum(max(0.,min(b,candidate.end_sec)-max(a,candidate.start_sec)) for a,b in ranges)
        # The entire returned clip should largely originate within the requested source window.
        return total>0 and inside/total>=.75
    except Exception:
        return False


def review_decision(clip_folder:Path, review_path:Path, clip_manifest_path:Path,
                    plan_path:Path, source_evidence_path:Path) -> Approval:
    plan,_=verify_precut(plan_path,source_evidence_path)
    clip_m=manifest_from(clip_manifest_path,'OPUS_CLIP')
    review=PostcutReview.model_validate(read_json(review_path))
    candidates={c.id:c for c in plan.candidates}
    if review.source_candidate_id not in candidates:
        raise ValueError('Review candidate not in source plan')
    clip=clip_folder/'clip.mp4'
    if not clip.is_file() or sha256(clip)!=clip_m.media_sha256 or clip_m.media_sha256!=review.clip_sha256:
        raise ValueError('Clip or review media hash changed')
    if abs(review.clip_duration_sec-clip_m.duration_sec)>.20:
        raise ValueError('Review duration not equal to actual clip duration')
    frame_by_id={f.id:f for f in clip_m.frames}
    if not set(review.review_evidence_frame_ids).issubset(frame_by_id) or not set(review.hook_evidence_frame_ids).issubset(frame_by_id):
        raise ValueError('Review cites nonexistent clip frames')
    if not set(review.hook_evidence_frame_ids).issubset(review.review_evidence_frame_ids):
        raise ValueError('Hook evidence not included in reviewed frames')
    if not any(frame_by_id[i].time_sec<=3.1 for i in review.hook_evidence_frame_ids):
        raise ValueError('Must inspect a real exported frame from the first 3s')
    score=review.scores.total(); blockers=[]
    if clip_m.height<=clip_m.width:blockers.append('NOT_PORTRAIT')
    if clip_m.width/clip_m.height > .70:blockers.append('BAD_9x16_FRAMING')
    if review.model_confidence<.75:blockers.append('LOW_REVIEW_CONFIDENCE')
    if not review.content_rights_reviewed:blockers.append('RIGHTS_NOT_REVIEWED')
    if not check_source_mapping(clip_folder/'source_mapping.json',candidates[review.source_candidate_id]):
        blockers.append('SOURCE_MAPPING_NOT_VERIFIED')
    if review.serious_export_defect:blockers.append('EXPORT_DEFECT')
    if not review.includes_real_mechanical_action: blockers.append('NO_MECHANICAL_ACTION')
    if not review.has_obvious_visual_hook:blockers.append('NO_VISUAL_HOOK')
    if not review.coherent_visual_story:blockers.append('NO_COHERENT_VISUAL_STORY')
    if not review.subject_framed_correctly:blockers.append('BAD_SUBJECT_FRAMING')
    if clip_m.duration_sec<15: blockers.append('TOO_SHORT_FOR_STORY')
    if blockers:status='HOLD' if any(x in blockers for x in
        ('LOW_REVIEW_CONFIDENCE','RIGHTS_NOT_REVIEWED','SOURCE_MAPPING_NOT_VERIFIED')) else 'REJECTED'
    else:status='APPROVED' if score>=85 else ('RECUT' if score>=70 else 'REJECTED')
    next_step={'APPROVED':'ENGLISH_STORY_WRITING_AND_CLEAN_ASMR',
               'RECUT':'SEND_RECUT_INSTRUCTIONS_TO_OPUS_OR_LOCAL_EDITOR',
               'REJECTED':'SKIP_CLIP','HOLD':'HUMAN_REVIEW_REQUIRED'}[status]
    approval=Approval(status=status,candidate_id=review.source_candidate_id,
        media_sha256=clip_m.media_sha256,review_sha256=sha256(review_path),
        evidence_sha256=sha256(clip_manifest_path),
        precut_plan_sha256=sha256(plan_path),
        mapping_sha256=sha256(clip_folder/'source_mapping.json') if (clip_folder/'source_mapping.json').is_file() else 'MISSING',
        score=score,blockers=blockers,next_step=next_step)
    (clip_folder/'source_plan_pointer.json').write_text(json.dumps({'precut_plan_path':str(plan_path.resolve())},indent=2),encoding='utf-8')
    (clip_folder/'viral_approval.json').write_text(approval.model_dump_json(indent=2),encoding='utf-8')
    return approval


def assert_approved(clip_folder:Path) -> Approval:
    approval_path=clip_folder/'viral_approval.json'
    if not approval_path.is_file():raise ValueError('VIRAL_APPROVAL_REQUIRED: no approval file; do not create TTS or render')
    a=Approval.model_validate(read_json(approval_path))
    if a.status!='APPROVED':raise ValueError('VIRAL_NOT_APPROVED: '+a.status)
    if sha256(clip_folder/'clip.mp4')!=a.media_sha256:
        raise ValueError('STALE_APPROVAL: clip contents changed')
    if sha256(clip_folder/'postcut_review.json')!=a.review_sha256:
        raise ValueError('STALE_APPROVAL: review was changed')
    if sha256(clip_folder/'clip_evidence'/'evidence_manifest.json')!=a.evidence_sha256:
        raise ValueError('STALE_APPROVAL: evidence was changed')
    if not (clip_folder/'source_mapping.json').is_file() or sha256(clip_folder/'source_mapping.json')!=a.mapping_sha256:
        raise ValueError('STALE_APPROVAL: source mapping changed')
    # Plan changes invalidate approval; the job folder stores canonical source plan location.
    plan_pointer=clip_folder/'source_plan_pointer.json'
    if not plan_pointer.is_file():raise ValueError('STALE_APPROVAL: missing source plan pointer')
    plan=Path(read_json(plan_pointer)['precut_plan_path'])
    if not plan.is_file() or sha256(plan)!=a.precut_plan_sha256:
        raise ValueError('STALE_APPROVAL: source plan changed')
    # Hash checking guards accidental stale files, not intentional tampering or a signature.
    return a


def submit(jobs_path:Path, execute:bool, output:Path) -> dict:
    data=read_json(jobs_path)
    if data.get('schema_version')!='3.4' or not data.get('rights_checked'):
        raise ValueError('Invalid Opus job batch')
    if not execute:return {'status':'DRY_RUN','would_submit':len(data['jobs'])}
    token=os.environ.get('OPUSCLIP_API_KEY')
    if not token:raise ValueError('OPUSCLIP_API_KEY not set')
    if output.exists():raise FileExistsError('Refusing to resubmit existing job-result batch: '+str(output))
    results=[]
    for job in data['jobs']:
        if job.get('status')!='READY_FOR_OPUS_SUBMIT':continue
        req=urllib.request.Request('https://api.opus.pro/api/clip-projects',
            data=json.dumps(job['request']).encode('utf-8'),
            headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
        try:
            with urllib.request.urlopen(req,timeout=60) as resp:
                result=json.loads(resp.read())
            results.append({'candidate_id':job['candidate_id'],'status':'SUBMITTED','provider_response':result})
        except (urllib.error.HTTPError,urllib.error.URLError) as exc:
            results.append({'candidate_id':job['candidate_id'],'status':'FAILED','reason':str(exc)})
            # A real production adapter must add retry/backoff and checkpoint per job.
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps({'schema_version':'3.4','results':results},indent=2),encoding='utf-8')
    return {'results':results}


def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='cmd',required=True)
    a=s.add_parser('opus-jobs');a.add_argument('--precut',type=Path,required=True);a.add_argument('--source-evidence',type=Path,required=True);a.add_argument('--source-url',required=True);a.add_argument('--output',type=Path,required=True)
    a=s.add_parser('decide');a.add_argument('--clip-folder',type=Path,required=True);a.add_argument('--review',type=Path,required=True);a.add_argument('--clip-evidence',type=Path,required=True);a.add_argument('--precut',type=Path,required=True);a.add_argument('--source-evidence',type=Path,required=True)
    a=s.add_parser('gate');a.add_argument('--clip-folder',type=Path,required=True)
    a=s.add_parser('submit-opus');a.add_argument('--jobs',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--execute',action='store_true')
    args=p.parse_args()
    if args.cmd=='opus-jobs':
        result=opus_jobs(args.precut,args.source_evidence,args.source_url)
        args.output.parent.mkdir(exist_ok=True,parents=True)
        args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps({'jobs':len(result['jobs']),'output':str(args.output)}))
    elif args.cmd=='decide':
        if args.clip_evidence.resolve() != (args.clip_folder/'clip_evidence'/'evidence_manifest.json').resolve():
            raise ValueError('Clip evidence must live at clip_folder/clip_evidence/evidence_manifest.json')
        # Copies the validated review to canonical path before stamping it; caller is responsible for source mapping evidence.
        canon=args.clip_folder/'postcut_review.json'
        if args.review.resolve()!=canon.resolve():
            import shutil
            shutil.copy2(args.review,canon)
        print(review_decision(args.clip_folder,canon,args.clip_evidence,args.precut,args.source_evidence).model_dump_json(indent=2))
    elif args.cmd=='gate':print(assert_approved(args.clip_folder).model_dump_json(indent=2))
    else:print(json.dumps(submit(args.jobs,args.execute,args.output),indent=2))

if __name__=='__main__':
    # Deprecated CLI: automatically forward to duration-gated v3.5 dispatcher.
    from director_workflow_v35 import main as _v35_main
    _v35_main()
