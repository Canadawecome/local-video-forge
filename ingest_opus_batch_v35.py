#!/usr/bin/env python3
"""Import Opus MP4 clips and immediately classify by real duration.

Imports do NOT imply GPT approval or rights verification by themselves.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
from ingest_opus_batch_v33 import ingest as _base_ingest
from duration_gate_v35 import check_clip, DurationGateError


def ingest(clips_dir:Path,output_root:Path,source_youtube_url:str|None=None,rights_reviewed:bool=False):
    base=_base_ingest(clips_dir,output_root,source_youtube_url,rights_reviewed)
    passed=0;blocked=0
    for row in base['items']:
        if row['status']=='DUPLICATE_SKIPPED':continue
        folder=Path(output_root).resolve()/row['clip_uid']
        manifest_path=folder/'import_manifest.json'
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        try:
            duration=check_clip(folder)
            row['duration_sec']=duration['actual_duration_sec']
            row['duration_gate_status']=duration['status']
            if duration['eligible']:
                passed+=1
                row['status']='DURATION_PASS_AWAIT_GPT_REVIEW'
                manifest['status']=row['status']
                manifest['next_steps']=['prepare frame evidence','run GPT Pass 2 review','verify source mapping and rights',
                                        'if APPROVED: prepare story, Clean ASMR, ElevenLabs, render']
            else:
                blocked+=1
                row['status']='RECUT_REQUIRED_DURATION'
                manifest['status']=row['status']
                manifest['next_steps']=['request a longer recut; STRICTLY >65s, target 70-90s',
                                        'do not run GPT review, scripts, separation or ElevenLabs']
        except DurationGateError as exc:
            blocked+=1
            row['status']='HOLD_INVALID_MEDIA'
            row['duration_gate_status']='HOLD'
            row['duration_error']=str(exc)
            manifest['status']=row['status']
            manifest['next_steps']=['repair/correct unreadable media, then repeat FFprobe duration gate']
        manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    base['schema_version']='3.5';base['duration_policy']='STRICT_GT_65S'
    base['duration_pass_count']=passed;base['duration_blocked_count']=blocked
    (Path(output_root)/'import_summary.json').write_text(json.dumps(base,ensure_ascii=False,indent=2),encoding='utf-8')
    return base


def main():
    p=argparse.ArgumentParser();p.add_argument('--clips-dir',required=True,type=Path)
    p.add_argument('--output-root',required=True,type=Path)
    p.add_argument('--source-youtube-url');p.add_argument('--rights-reviewed',action='store_true')
    a=p.parse_args()
    print(json.dumps(ingest(a.clips_dir,a.output_root,a.source_youtube_url,a.rights_reviewed),indent=2,ensure_ascii=False))

if __name__=='__main__':main()
