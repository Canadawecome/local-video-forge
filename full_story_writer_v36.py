#!/usr/bin/env python3
"""GPT full-story writer v3.6: approved Opus clip -> time-distributed, complete story.

No API call without --execute. Uses actual exported clip frame evidence, not a YouTube URL.
Only rewrites story_plan.json after schema, length, time, and factual gates pass.
"""
from __future__ import annotations
import argparse,json,math,os,re
from pathlib import Path
from storytelling_contracts_v33 import StorytellingPlan
from story_coverage_v36 import assess_story, story_text, seal_script, approved_duration
from storytelling_render_v33 import sha256
from director_workflow_v34 import manifest_from
from gpt_vision_adapter_v34 import ask_model


def suggest_slots(duration:float)->list[dict]:
    """Create 7-12 distributed slots leaving ASMR between narration chunks."""
    count=max(7,min(12,math.ceil(duration/9.0)))
    first=0.8
    last_end=duration-1.2
    window=last_end-first
    slot_len=round(.79*duration/count, 3)
    gap=round((window-count*slot_len)/(count-1), 3)
    if gap<0.8:
        slot_len=round(.75*duration/count, 3)
        gap=round((window-count*slot_len)/(count-1), 3)
    if gap<0:raise ValueError('NOT_ENOUGH_ROOM_FOR_NARRATION_SLOTS')
    result=[]
    for i in range(count):
        a=first+i*(slot_len+gap)
        result.append({'id':f'story_{i+1:03d}', 'start':round(a,3),
                       'end':round(a+slot_len,3),
                       'role':'hook' if i==0 else 'payoff' if i==count-1 else 'process'})
    return result


def run(folder:Path,model:str,seed_path:Path|None=None,execute:bool=False,max_attempts:int=3)->dict:
    folder=folder.resolve()
    duration=approved_duration(folder)
    evidence=folder/'clip_evidence'/'evidence_manifest.json'
    m=manifest_from(evidence,'OPUS_CLIP')
    if m.media_sha256 != sha256(folder/'clip.mp4'):
        raise ValueError('STALE_CLIP_EVIDENCE: cannot write story about another MP4')
    path=seed_path or folder/'story_plan.json'
    seed=json.loads(path.read_text(encoding='utf-8'))
    seed.pop('narration_segments',None)
    # Do not let a language model approve rights, speech removal, or invent source country.
    if seed.get('rights_status')!='VERIFIED' or seed.get('music_rights_status') not in ('NO_MUSIC','CLEARED'):
        raise ValueError('STORY_SEED_RIGHTS_NOT_VERIFIED')
    insp_file = folder / 'inspection.json'
    if not insp_file.is_file():
        insp_file = folder.parent / 'inspection.json'
    visible_actions = []
    if insp_file.is_file():
        try:
            insp = json.loads(insp_file.read_text(encoding='utf-8')).get('inspection', {})
            visible_actions = insp.get('visible_actions', [])
        except Exception:
            pass
    slots=suggest_slots(duration)
    frame_list=m.frames
    if len(frame_list)>24:
        inds=sorted(set(round(i*(len(frame_list)-1)/23) for i in range(24)))
        frame_list=[frame_list[i] for i in inds]
    allowed={f.id for f in frame_list}
    min_w = math.ceil(duration*1.52)
    min_per_slot = math.ceil(min_w / len(slots))
    target_w = max(min_w + 10, math.ceil(duration*1.68))
    target_per_slot = math.ceil(target_w / len(slots))
    cfg={'actual_clip_duration_sec':duration,'slots':slots,
         'visible_workshop_actions':visible_actions,
         'source_context':seed['source_context'],
         'source_speech_status':seed['source_speech_status'],
         'protected_asmr':seed.get('protected_asmr',[]),
         'observed_frames':[{'id':f.id,'time_sec':f.time_sec} for f in frame_list],
         'min_total_words':min_w,
         'min_words_per_segment':min_per_slot,
         'target_total_words':target_w,
         'all_frame_ids':sorted(allowed)}
    if not execute:
        return {'status':'DRY_RUN_NO_PAID_API_CALL','model':model,'slots':slots,
                'draft_requirements':cfg,'hint':'Use --execute and a valid OPENAI_API_KEY to generate and validate actual narration'}
    instruction=f'''You are an award-winning documentary director and sound designer creating an organic, audio-synchronized voiceover for this craft metalworking video.
    Return STRICT JSON only:
    {{
      "audio_direction": {{
        "voice_gain_db": 6.5,
        "bed_ducking_db": -3.5,
        "rhythm_style": "...",
        "rationale": "..."
      }},
      "segments": [
        {{"id": "story_001", "text_en": "...", "evidence_refs": ["frame_0000"]}}
      ]
    }}
    AUDIO & RHYTHM DIRECTIVES (ORGANIC PACING, NEVER MECHANICAL):
    - AUDIO-ACTION SYNCHRONIZATION: Read visible_workshop_actions carefully. Match your narrative tone and rhythm to what is physically happening on screen and in the workshop audio.
    - DYNAMIC SENTENCE LENGTHS: Do NOT force every segment to have the exact same word count, but keep each segment between 10 and 20 words (average at least {min_per_slot} words/segment).
      * Opening Hook (story_001): Make it punchy, suspenseful, and direct (10-14 words).
      * Heavy Action / Impact Moments: Keep lines rhythmic and focused (11-15 words) so the narrator leaves room for the ASMR strike to reverberate.
      * Sustained Craft / Observation Moments: Use richer, evocative descriptions (14-19 words) to describe the metal glowing, scale cracking, or grain refining.
      * Payoff: Strong, memorable concluding statement (11-15 words).
    - TOTAL WORDS (CRITICAL): Total words across all {len(slots)} segments MUST be at least {min_w} words (target roughly {target_w} words). An average of at least {min_per_slot} words per segment is required. Do NOT write short segments that total less than {min_w} words!
    - PUNCTUATION: Use standard ASCII quotes and double dashes (--) instead of em-dashes.
    - VOICE GAIN & DUCKING: Recommend voice_gain_db (+4.0 to +8.5 dB) and bed_ducking_db (-2.0 to -5.0 dB) tailored to this specific clip's noise environment.
    - EVIDENCE & INTEGRITY: Each sentence references real visual frames or verified facts. No fabricated country, alloy grades, or fake provenance.'''
    context=json.dumps(cfg,ensure_ascii=False)
    last_error=''
    for attempt in range(1,max_attempts+1):
        out=ask_model(model,instruction, evidence,frame_list, context+'\nPrevious validation error: '+last_error,detail='low')
        try:
            rows=out.get('segments', [])
            if len(rows)!=len(slots) or [r.get('id') for r in rows]!=[s['id'] for s in slots]:
                print(f"DEBUG: expected slots {[s['id'] for s in slots]}, got {[r.get('id') for r in rows]}")
                raise ValueError(f"Missing/misordered story segments: expected {len(slots)} {[s['id'] for s in slots]}, got {len(rows)} {[r.get('id') for r in rows]}")
            segments=[]
            for row,slot in zip(rows,slots):
                refs=row.get('evidence_refs',[])
                known=allowed | {ref for fact in seed['source_context'].get('verified_facts',[]) for ref in fact.get('evidence_refs',[])}
                if not refs or any(ref not in known for ref in refs):
                    raise ValueError(f'Invalid evidence ref for {slot["id"]}')
                raw_text = str(row.get('text_en', ''))
                clean_text = re.sub(r'[\u2014\u2013]', '--', raw_text)
                clean_text = re.sub(r'[\u2018\u2019]', "'", clean_text)
                clean_text = re.sub(r'[\u201c\u201d]', '"', clean_text)
                clean_text = re.sub(r'[\u2026]', '...', clean_text)
                clean_text = re.sub(r'\s+', ' ', clean_text).strip()
                wc = len(clean_text.split())
                slot_dur = slot['end'] - slot['start']
                max_w_slot = min(22, max(19, math.floor(slot_dur * 2.8)))
                if wc > max_w_slot:
                    raise ValueError(f'Segment {slot["id"]} has {wc} words; max {max_w_slot} allowed for {slot_dur:.1f}s slot to avoid TTS slot overflow')
                segments.append({**slot,'text_en':clean_text,'evidence_refs':refs})

            audio_dir = out.get('audio_direction', {})
            vg = float(audio_dir.get('voice_gain_db', 6.0))
            vg = max(2.0, min(9.5, vg))
            bd = float(audio_dir.get('bed_ducking_db', -3.5))
            bd = max(-6.0, min(0.0, bd))
            notes = str(audio_dir.get('rationale', 'GPT-5.6-Sol dynamic audio director'))
            
            settings_data = seed.get('settings', {})
            settings_data['voice_gain_db'] = vg
            settings_data['bed_ducking_db'] = bd
            settings_data['audio_direction_notes'] = notes

            candidate=StorytellingPlan.model_validate({
                **seed,
                'narration_segments':segments,
                'settings': settings_data
            })
            metrics=assess_story(candidate,duration)
            # Atomic-like staging: original plan is left intact if the model fails any check.
            target=folder/'story_plan.json';script_file=folder/'script_en.txt'
            target.write_text(candidate.model_dump_json(indent=2),encoding='utf-8')
            script_file.write_text(story_text(candidate)+'\n',encoding='utf-8')
            (folder/'script_tts.txt').write_text(' '.join(x.text_en.strip() for x in candidate.narration_segments)+'\n',encoding='utf-8')
            (folder/'script_en.md').write_text('# English Storytelling Script\n\n'+story_text(candidate)+'\n',encoding='utf-8')
            for stale in ('story_coverage_v36.json','tts_full_story_v36.json','final.mp4','qc_report.json'):
                (folder/stale).unlink(missing_ok=True)
            proof=seal_script(folder)
            return {'status':'COMPLETE_STORY_CREATED','model':model,'attempt':attempt,'coverage':metrics,
                    'audio_direction': {'voice_gain_db': vg, 'bed_ducking_db': bd, 'rationale': notes},
                    'script_path':str(script_file),'story_plan_path':str(target),'proof':proof}
        except (KeyError,ValueError,TypeError) as exc:
            last_error=str(exc)
    raise ValueError('STORY_GENERATION_FAILED_AFTER_RETRIES: '+last_error)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['generate']);p.add_argument('--folder',type=Path,required=True)
    p.add_argument('--model',required=True,help='Your actually API-available image-capable GPT model')
    p.add_argument('--seed',type=Path,help='Approved base story plan; can use old one-segment story_plan.json as seed')
    p.add_argument('--execute',action='store_true');p.add_argument('--attempts',type=int,default=3)
    a=p.parse_args()
    if a.attempts<1 or a.attempts>4:raise ValueError('attempts must be 1..4')
    print(json.dumps(run(a.folder,a.model,a.seed,a.execute,a.attempts),indent=2,ensure_ascii=False))
if __name__=='__main__':main()
