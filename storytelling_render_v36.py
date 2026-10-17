#!/usr/bin/env python3
"""FINAL v3.6 renderer: approved >65s video + full English script + ALL TTS assets."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from story_coverage_v36 import require_sealed_script,verify_all_tts
from storytelling_render_v33 import process as _core
from final_story_qc_v36 import check_final


def process(folder:Path,*,dry_run:bool=False)->dict:
    folder=folder.resolve()
    script=require_sealed_script(folder)
    if dry_run:
        return {'status':'STORY_GATE_PASS_AWAITING_TTS','story_coverage':script}
    try:
        voice=verify_all_tts(folder)
        result=_core(folder,dry_run=False)
        final=check_final(folder)
        return {**result,'full_story_gate':'PASS','script_coverage':script,
                'full_tts_coverage':voice,'final_story_qc':final}
    except Exception:
        # Never leave a stale/rejected output masquerading as the current final video.
        (folder/'final.mp4').unlink(missing_ok=True)
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('cmd',choices=['check','process']);p.add_argument('--folder',required=True,type=Path)
    a=p.parse_args()
    print(json.dumps(process(a.folder,dry_run=a.cmd=='check'),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
