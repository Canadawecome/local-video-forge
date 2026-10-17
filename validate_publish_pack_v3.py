#!/usr/bin/env python3
"""Check a render folder contains the promised English story and publication pack.
Checks consistency only; editorial value and permission remain human review tasks.
"""
import argparse, json, re, sys
from pathlib import Path
from storytelling_contracts_v3 import StorytellingPlan


def validate(folder:Path)->dict:
    expected=['clip.mp4','story_plan.json','script_en.md','script_tts.txt','description.txt',
              'hashtags.txt','final.mp4','captions_en.srt','captions_en.ass','qc_report.json',
              'audio/workshop_bed_always_on.wav','audio/english_voice_only.wav']
    missing=[p for p in expected if not (folder/p).is_file()]
    if missing: return {'status':'INCOMPLETE','missing':missing}
    plan=StorytellingPlan.model_validate_json((folder/'story_plan.json').read_text())
    clean=lambda s:re.sub(r'\s+',' ',s).strip().casefold()
    script=clean((folder/'script_tts.txt').read_text(encoding='utf-8'))
    from_plan=clean(' '.join(x.text_en for x in sorted(plan.narration_segments,key=lambda x:x.start)))
    if script!=from_plan: return {'status':'INCOMPLETE','reason':'script_tts differs from approved narration segments'}
    if not (folder/'description.txt').read_text(encoding='utf-8').strip():
        return {'status':'INCOMPLETE','reason':'empty description'}
    tags=re.findall(r'#[\w]+',(folder/'hashtags.txt').read_text(encoding='utf-8'))
    if len(tags)<1: return {'status':'INCOMPLETE','reason':'no hashtags'}
    qc=json.loads((folder/'qc_report.json').read_text())
    if qc.get('status')!='RENDERED_WITH_APPROVED_AUDIO_AND_EN_SUBS' or not qc.get('english_subtitles_burned_in'):
        return {'status':'INCOMPLETE','reason':'final render QC not passed'}
    return {'status':'READY_FOR_HUMAN_REVIEW','clip_uid':plan.clip_uid,'hashtag_count':len(tags),
            'english_story_segments':len(plan.narration_segments),'note':'not automatically published'}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--folder',type=Path,required=True)
    args=ap.parse_args()
    try: r=validate(args.folder)
    except Exception as e: r={'status':'INCOMPLETE','reason':str(e)}
    print(json.dumps(r,ensure_ascii=False,indent=2));return 0 if r['status']=='READY_FOR_HUMAN_REVIEW' else 2
if __name__=='__main__':raise SystemExit(main())
