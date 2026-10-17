#!/usr/bin/env python3
"""v3.5 canonical render entrypoint. Fail closed if actual Opus duration <=65s."""
from pathlib import Path
import argparse,json
from director_workflow_v35 import assert_approved
from storytelling_render_v36 import process as _legacy_renderer


def process(folder:Path,*,dry_run:bool=False):
    approval=assert_approved(folder)  # FFprobe + GPT approved + stale hash checks
    result=_legacy_renderer(folder,dry_run=dry_run)
    result.update({'duration_gate':'PASS_GT_65S',
                   'viral_approval_status':approval.status,
                   'viral_review_score':approval.score,
                   'viral_candidate_id':approval.candidate_id})
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['process','check']);p.add_argument('--folder',type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(process(a.folder,dry_run=a.command=='check'),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
