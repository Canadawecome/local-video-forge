#!/usr/bin/env python3
"""Local Video Forge v3.5, strict >65s duration gate based on actual FFprobe output.

Fail closed: no FFprobe, invalid/undecodable MP4, audio-only or missing duration
must never reach paid narration. Returns receipt tied to media SHA256 for audit;
this is a pipeline policy gate, not a cryptographic authorization system.
"""
from __future__ import annotations
import argparse
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from prepare_video_evidence_v34 import sha256

THRESHOLD_SEC = 65.0  # STRICTLY greater, 65.000 is NOT valid.
TARGET_MIN_SEC = 70
TARGET_MAX_SEC = 90

class DurationGateError(ValueError):
    pass


def probe_actual_duration(media: Path) -> float:
    media=Path(media)
    if not media.is_file():
        raise DurationGateError(f'MEDIA_MISSING: {media}')
    proc = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_type',
         '-of', 'json', str(media)], text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise DurationGateError(f'FFPROBE_FAILED: {proc.stderr.strip()[:300]}')
    try:
        parsed=json.loads(proc.stdout)
        if not any(s.get('codec_type')=='video' for s in parsed['streams']):
            raise DurationGateError('NO_VIDEO_STREAM')
        secs=float(parsed['format']['duration'])
    except DurationGateError:
        raise
    except (KeyError, ValueError, TypeError, json.JSONDecodeError, OverflowError) as exc:
        raise DurationGateError('INVALID_PROBE_RESULT') from exc
    if not math.isfinite(secs) or secs<=0:
        raise DurationGateError('INVALID_DURATION')
    return secs


def is_eligible(seconds: float) -> bool:
    try:
        seconds=float(seconds)
    except (ValueError, TypeError):
        return False
    return math.isfinite(seconds) and seconds > THRESHOLD_SEC


def check_clip(clip_folder:Path, *, write_receipt:bool=True) -> dict:
    clip_folder=Path(clip_folder)
    clip=clip_folder/'clip.mp4'
    actual=probe_actual_duration(clip)
    eligible=is_eligible(actual)
    receipt={
        'policy_version':'3.5',
        'gate':'POST_OPUS_DURATION_BEFORE_GPT_REVIEW_AND_ELEVENLABS',
        'media_path':str(clip.resolve()),
        'media_sha256':sha256(clip),
        'actual_duration_sec':round(actual,6),
        'duration_source':'FFPROBE_FORMAT_DURATION',
        'threshold_operator':'>',
        'threshold_sec':THRESHOLD_SEC,
        'target_opus_duration_sec':[TARGET_MIN_SEC,TARGET_MAX_SEC],
        'eligible':eligible,
        'status':'PASS' if eligible else 'RECUT_REQUIRED',
        'reason':None if eligible else 'DURATION_NOT_OVER_65S',
        'checked_at_utc':datetime.now(timezone.utc).isoformat()
    }
    if write_receipt:
        clip_folder.mkdir(parents=True,exist_ok=True)
        (clip_folder/'duration_gate_v35.json').write_text(
            json.dumps(receipt,indent=2,ensure_ascii=False),encoding='utf-8')
    return receipt


def require_eligible(clip_folder:Path, *, write_receipt:bool=True) -> dict:
    receipt=check_clip(clip_folder,write_receipt=write_receipt)
    if not receipt['eligible']:
        raise DurationGateError(
            f"DURATION_NOT_OVER_65S: actual={receipt['actual_duration_sec']:.3f}s, "
            'requires >65.000s; block GPT review, ElevenLabs and rendering; recut.')
    return receipt


def main():
    p=argparse.ArgumentParser(description='FFprobe real MP4 duration gate (>65.000s).')
    s=p.add_subparsers(dest='cmd',required=True)
    c=s.add_parser('check',help='Check one Opus output clip; nonzero exit if <=65s.')
    c.add_argument('--clip-folder',required=True,type=Path)
    b=s.add_parser('batch',help='Check clip_*/clip.mp4 under batch directory; emit JSON summary.')
    b.add_argument('--batch-dir',required=True,type=Path)
    b.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.cmd=='check':
        result=check_clip(a.clip_folder)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if not result['eligible']:raise SystemExit(2)
    else:
        results=[]
        for clip_path in sorted(a.batch_dir.glob('*/clip.mp4')):
            try:results.append(check_clip(clip_path.parent))
            except DurationGateError as e:
                results.append({'media_path':str(clip_path),'eligible':False,'status':'HOLD','reason':str(e)})
        result={'policy_version':'3.5','checked':len(results),'eligible':sum(x['eligible'] for x in results),'clips':results}
        payload=json.dumps(result,ensure_ascii=False,indent=2)
        if a.output:
            a.output.parent.mkdir(parents=True,exist_ok=True)
            a.output.write_text(payload,encoding='utf-8')
        print(payload)

if __name__=='__main__':main()
