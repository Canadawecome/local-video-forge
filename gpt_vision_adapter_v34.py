#!/usr/bin/env python3
"""Optional real OpenAI Responses API adapter using sampled video frames + timed text.

Requires OPENAI_API_KEY, --model being an actual API-accessible image-capable model.
A URL, description, or transcript alone is NOT treated as actual video inspection.
The model does not automatically hear audio in this image-frame workflow.
"""
from __future__ import annotations
import argparse,base64,json,os,re,urllib.request,urllib.error
from pathlib import Path
from viral_director_contracts_v34 import ViralCandidate, PrecutPlan, PostcutReview
from director_workflow_v34 import manifest_from, read_json

BASE_URL='https://api.openai.com/v1/responses'


def _reply(resp:dict) -> dict:
    chunks=[]
    for item in resp.get('output',[]):
        if item.get('type')=='message':
            chunks.extend(c.get('text','') for c in item.get('content',[]) if c.get('type')=='output_text')
    content='\n'.join(chunks).strip()
    if not content:
        raise ValueError('No text output from OpenAI Responses API (possibly refusal/incomplete)')
    if content.startswith('```'):
        content=re.sub(r'^```(?:json)?\s*|\s*```$','',content,flags=re.I).strip()
    return json.loads(content)


def ask_model(model:str, instruction:str, manifest_path:Path, frames:list, context:str='',detail='low') -> dict:
    token=os.environ.get('OPENAI_API_KEY')
    if not token:raise ValueError('OPENAI_API_KEY is missing')
    base_url = os.environ.get('OPENAI_BASE_URL', '').rstrip('/')
    if base_url:
        chat_url = f"{base_url}/chat/completions"
        insp_file = manifest_path.parent / 'inspection.json'
        if not insp_file.is_file():
            insp_file = manifest_path.parent.parent / 'inspection.json'
        extra_ctx = ""
        if insp_file.is_file():
            try:
                insp = json.loads(insp_file.read_text(encoding='utf-8')).get('inspection', {})
                actions = insp.get('visible_actions', [])
                if actions:
                    extra_ctx = "\nOBSERVED ACTIONS:\n" + "\n".join("- " + a for a in actions)
            except Exception:
                pass
        
        frame_notes = "\n".join(f"- {f.id} at {f.time_sec:.2f}s" for f in frames)
        full_text = f"{instruction}\n\nFRAME EVIDENCE TIMELINE:\n{frame_notes}\n{extra_ctx}\n\n{context}"
        
        payload = {
            'model': model,
            'messages': [
                {'role': 'system', 'content': 'You are a master craftsman scriptwriter and director. Directly output the requested JSON without long reasoning.'},
                {'role': 'user', 'content': full_text}
            ],
            'max_tokens': 10000,
        }
        req = urllib.request.Request(chat_url, method='POST',
            data=json.dumps(payload).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                resp = json.loads(r.read().decode('utf-8'))
                choice = resp.get('choices', [{}])[0]
                msg = choice.get('message', {})
                raw_text = (msg.get('content') or msg.get('reasoning_content') or '').strip()
                if raw_text.startswith('```'):
                    raw_text = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw_text, flags=re.I).strip()
                try:
                    return json.loads(raw_text)
                except Exception:
                    # Try finding JSON object in raw_text or reasoning_content
                    for text_candidate in [raw_text, msg.get('reasoning_content', '')]:
                        clean = re.sub(r'```(?:json)?|```', '', text_candidate)
                        cand = re.search(r'\{[\s\S]*"segments"[\s\S]*\}', clean)
                        if cand:
                            try:
                                return json.loads(cand.group(0))
                            except Exception:
                                pass
                    raise ValueError(f"COULD_NOT_PARSE_JSON from response: choice={choice}")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'OpenAI API HTTP {exc.code}: {exc.read(1500).decode("utf-8", errors="replace")}') from exc

    content=[{'type':'input_text','text':instruction+'\n\n'+context}]
    for frame in frames:
        f=manifest_path.parent/frame.path
        content.append({'type':'input_text','text':f'Visual evidence {frame.id} at {frame.time_sec:.3f} seconds'})
        data=base64.b64encode(f.read_bytes()).decode('ascii')
        content.append({'type':'input_image','image_url':'data:image/jpeg;base64,'+data,'detail':detail})
    payload={'model':model,'input':[{'role':'user','content':content}],
             'max_output_tokens':10000}
    req=urllib.request.Request(BASE_URL,method='POST',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=180) as r:
            return _reply(json.loads(r.read()))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'OpenAI API HTTP {exc.code}: {exc.read(1500).decode("utf-8",errors="replace")}') from exc


PRECUT_PROMPT='''You are an evidence-grounded director choosing real mechanical workshop moments for an English ASMR documentary short.
This is only a sparse set of time-labelled STILL FRAMES, not a full native video or audio review.
Return JSON ONLY: {"candidates": [ViralCandidate,...]}.
For EACH candidate include exactly fields: id, start_sec, end_sec, hook_at_sec, evidence_frame_ids,
hook_visual, actions (list of observed mechanics), hook_why, asmr_notes, narrative_arc,
potential_score (0-100 subjective ranking), uncertainty_notes, desired_clip_min_sec (int), desired_clip_max_sec (int).
Use ONLY visible frames and provided corroborated text. Refer to exact frame IDs from this call.
Do not invent tools, country, material grade, sound, technique or accurate frame-to-frame movements.
When action is ambiguous, say so in uncertainty_notes. ASMR not heard = label as UNVERIFIED in asmr_notes.
Frame timestamp resolution is sparse. Choose practical windows, not fake frame-accurate action boundaries.
For each window make sure start <= hook_at <= end. Fit windows inside supplied full source duration.
STRICT DURATION POLICY: propose ONLY source windows of >=70 seconds; desire 70-90 second finished clips.
Set desired_clip_min_sec >=70 and desired_clip_max_sec >= desired_clip_min_sec. Never propose a <=65s short.
If evidence for a coherent >=70s section is absent, return no candidates rather than fabricating filler.
Prefer visually demonstrable hammer/grinder/forging, escalating process and payoff rather than talking heads.
If evidence inadequate, return empty list. No claim of guaranteed virality.'''

REVIEW_PROMPT='''You are a strict independent reviewer of ACTUAL OpusClip EXPORTED CLIP still frames (not its score).
Return one JSON object with EXACT fields expected by PostcutReview:
schema_version="3.4", source_candidate_id, clip_sha256, clip_duration_sec, review_model,
analyzed_media="EXPORTED_CLIP_VISUAL_FRAMES", review_evidence_frame_ids (>=2 IDs),
hook_evidence_frame_ids (>=1 frame from 0-3 seconds),
scores {hook,action_asmr,narrative_arc,vertical_framing,pacing,english_story_potential} all ints 0-100,
includes_real_mechanical_action,has_obvious_visual_hook,coherent_visual_story,subject_framed_correctly,
serious_export_defect,content_rights_reviewed, mapped_to_planned_source="UNVERIFIED",
source_mapping_evidence=null,model_confidence float, reasons list, suggested_recut string-or-null,asmr_warning.
This sparse visual evidence does not let you hear source speech or ASMR. Do not certify ASMR or audio QC.
Do not claim source timeline verification. Source matching will be separately attested from Opus timeRanges
or a human editor. Thus mapped_to_planned_source remains UNVERIFIED.
If no first-3-second frame exists, model MUST NOT invent a hook evidence ID; report insufficient evidence.
Strictly assess action, hook, framing, pacing and narrative in this actual exported video, not the desired plan.
If uncertain, lower confidence and explain. No claim of predicted TikTok views.'''


def run_precut(evidence:Path, output:Path, model:str, country_status:str='UNKNOWN',
               source_language:str='und',topic_en:str='Metalworking',batch_size:int=22,
               max_candidates:int=12,transcript:Path|None=None,events:Path|None=None):
    manifest=manifest_from(evidence,'SOURCE')
    if not 2<=batch_size<=24:raise ValueError('Batch size must be 2..24')
    ctx={'duration_sec':manifest.duration_sec,'width':manifest.width,'height':manifest.height,
         'country_status':country_status,'language':source_language,'topic_en':topic_en}
    if transcript:
        # Limits very long ASR to avoid silently exhausting model context;
        # production systems should align transcript segments to each frame chunk.
        ctx['transcript_excerpt_first_12000_char']=transcript.read_text(encoding='utf-8')[:12000]
    if events:
        event_data=read_json(events)
        if event_data.get('source_sha256')!=manifest.media_sha256:
            raise ValueError('Event timestamps refer to a different source media SHA')
        ctx['visual_scene_changes']=(event_data.get('scene_events') or [])[:100]
        ctx['unclassified_audio_onsets']=(event_data.get('audio_onset_events') or [])[:80]
        ctx['warning']='Audio onsets unclassified; not proof of hammering.'
    frames=manifest.frames
    candidates=[]
    # Overlap neighboring chunks so a 60+ second visual story can span a boundary.
    stride=max(2,batch_size-5)
    for batch in range(0,len(frames),stride):
        group=frames[batch:batch+batch_size]
        if len(group)<2:break
        context=json.dumps(ctx,ensure_ascii=False)+'\nObserved frame times: '+json.dumps([{'id':f.id,'s':f.time_sec} for f in group])
        result=ask_model(model,PRECUT_PROMPT,evidence,group,context)
        for row in result.get('candidates',[]):
            row=dict(row)
            # Candidate ids scoped across chunk calls; use stable model provided suffix.
            row['id']=f"b{batch//stride+1:03d}_{row.get('id','candidate')}"
            item=ViralCandidate.model_validate(row)
            candidates.append(item)
    if not candidates:raise ValueError('Model found no evidence-grounded candidate: review the video manually')
    candidates.sort(key=lambda c:c.potential_score,reverse=True)
    # Overlapping frame chunks must not submit almost-identical moments repeatedly.
    selected=[]
    for c in candidates:
        if any(max(0,min(c.end_sec,x.end_sec)-max(c.start_sec,x.start_sec)) /
               min(c.end_sec-c.start_sec,x.end_sec-x.start_sec) > .75 for x in selected):
            continue
        selected.append(c)
        if len(selected)>=max_candidates:break
    plan=PrecutPlan.model_validate({
        'source_sha256':manifest.media_sha256,'source_duration_sec':manifest.duration_sec,
        'rights_status':'UNKNOWN',  # MUST be signed off by an actual rights reviewer, not the model
        'analysis_model':model,'source_country_status':country_status,
        'source_language':source_language,'production_topic_en':topic_en,
        'candidates':[c.model_dump() for c in selected]})
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(plan.model_dump_json(indent=2),encoding='utf-8')
    return {'status':'DRAFT_REQUIRES_RIGHTS_REVIEW','candidates':len(plan.candidates),'file':str(output)}


def run_review(clip_evidence:Path, output:Path, model:str,candidate_id:str,
               max_frames:int=24):
    m=manifest_from(clip_evidence,'OPUS_CLIP')
    from duration_gate_v35 import require_eligible
    require_eligible(Path(m.media_file).parent)  # BEFORE paid GPT Pass 2 call
    # First 3 seconds and late payoff must be covered. Evidence manifest normally sampled at <=2s.
    frames=m.frames
    if len(frames)>max_frames:
        idx=[round(i*(len(frames)-1)/(max_frames-1)) for i in range(max_frames)]
        frames=[frames[i] for i in dict.fromkeys(idx)]
    if not any(f.time_sec<=3.1 for f in frames):
        raise ValueError('No opening frames: cannot score hook; resample first 3 seconds')
    ctx=json.dumps({'source_candidate_id':candidate_id,'clip_sha256':m.media_sha256,
                    'clip_duration_sec':m.duration_sec,'review_model':model,
                    'width':m.width,'height':m.height,'content_rights_reviewed':False},ensure_ascii=False)
    raw=ask_model(model,REVIEW_PROMPT,clip_evidence,frames,ctx)
    raw['schema_version']='3.4'
    raw['source_candidate_id']=candidate_id
    raw['clip_sha256']=m.media_sha256
    raw['clip_duration_sec']=m.duration_sec
    raw['review_model']=model
    raw['mapped_to_planned_source']='UNVERIFIED'
    raw['source_mapping_evidence']=None
    raw['content_rights_reviewed']=False  # external reviewer confirms, never GPT self-attests
    review=PostcutReview.model_validate(raw)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(review.model_dump_json(indent=2),encoding='utf-8')
    return {'status':'REVIEW_DRAFT_REQUIRES_RIGHTS_AND_SOURCE_MAPPING','score':review.scores.total(),'file':str(output)}


def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='cmd',required=True)
    a=s.add_parser('precut');a.add_argument('--source-evidence',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--model',required=True);a.add_argument('--topic',default='Metalworking');a.add_argument('--source-language',default='und');a.add_argument('--transcript',type=Path);a.add_argument('--events-json',type=Path);a.add_argument('--batch-size',type=int,default=22)
    a=s.add_parser('review');a.add_argument('--clip-evidence',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--model',required=True);a.add_argument('--candidate-id',required=True)
    args=p.parse_args()
    if args.cmd=='precut':r=run_precut(args.source_evidence,args.output,args.model,topic_en=args.topic,source_language=args.source_language,transcript=args.transcript,events=args.events_json,batch_size=args.batch_size)
    else:r=run_review(args.clip_evidence,args.output,args.model,args.candidate_id)
    print(json.dumps(r,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
