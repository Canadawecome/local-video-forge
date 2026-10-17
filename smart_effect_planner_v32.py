#!/usr/bin/env python3
"""Create conservative Cinematic ASMR effect plans from REAL reviewed ASMR windows.

This is a deterministic fallback for an AI planner, not an OpenAI API client.
An AI may output the same SmartEffectPlan JSON, subject to identical validators.
No invented hook, shot boundary or action labels are added by this script.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from smart_effect_contracts_v32 import SmartEffectPlan
import hashlib
import subprocess


def sha256(path: Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda:f.read(1<<20),b''): h.update(part)
    return h.hexdigest()


def ffprobe_duration(path: Path)->float:
    r=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration',
                      '-of','default=noprint_wrappers=1:nokey=1',str(path)],
                     check=True,capture_output=True,text=True)
    return float(r.stdout.strip())


def build_plan(folder: Path) -> SmartEffectPlan:
    clip=folder/'clip.mp4'
    story=json.loads((folder/'story_plan.json').read_text(encoding='utf-8'))
    duration=ffprobe_duration(clip)
    found=[]
    last_end=-1.
    for marker in sorted(story.get('protected_asmr',[]),key=lambda m:m['start']):
        if marker.get('kind') not in {'hammer','grinding','machine','saw','forge'}:
            continue
        mid=(float(marker['start'])+float(marker['end']))/2
        a=max(0.,mid-1.0); b=min(duration,mid+1.0)
        if b-a<.65 or a<last_end+.3: continue
        found.append({'start':round(a,3),'end':round(b,3),'peak_scale':1.045,
                      'center_x':.5,'center_y':.5,
                      'evidence_ref':f"protected_asmr:{marker['kind']}@{marker['start']:.2f}"})
        last_end=b
        if len(found)>=4: break
    return SmartEffectPlan.model_validate({
        'source_clip_sha256':sha256(clip),
        'duration_seconds':round(duration,6),
        'micro_zooms':found,
        'storyboard_notes':['Only real marked ASMR windows received zoom. No timeline reorder, speed ramp, black flash or synthetic SFX.']})


def ensure_plan(folder: Path) -> Path:
    output=folder/'effect_plan.json'
    if not output.is_file():
        plan=build_plan(folder)
        output.write_text(plan.model_dump_json(indent=2),encoding='utf-8')
    else:
        SmartEffectPlan.model_validate_json(output.read_text(encoding='utf-8'))
    return output


def main() -> None:
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True)
    args=p.parse_args();print(ensure_plan(args.folder))

if __name__=='__main__': main()
