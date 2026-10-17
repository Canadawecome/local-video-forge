#!/usr/bin/env python3
"""v3.6 hard gates: the full approved English story must survive plan -> TTS -> video.

This module never writes filler narration or modifies the source-media audio.
It fails closed and requires the real ElevenLabs audio for the final coverage gate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

from storytelling_contracts_v33 import StorytellingPlan
from storytelling_render_v33 import ffprobe_duration, sha256, tts_path, _alignment_words

MIN_SEGMENTS = 5
MIN_TEXT_WPS = 1.52
MAX_TEXT_WPS = 3.3
MIN_PLANNED_COVERAGE = .64
MIN_ACTUAL_TTS_COVERAGE = .59
MAX_PLAN_GAP = 13.0
MAX_ACTUAL_GAP = 14.0
MAX_START_DELAY = 5.0
MAX_END_TAIL = 8.0
MAX_TTS_END_TAIL = 10.0
MAX_SPEED_WORDS_PER_SEC = 3.9


class StoryCoverageError(ValueError):
    pass


def words(text: str) -> list[str]:
    return re.findall(r"\b[\w]+(?:[’'-][\w]+)*\b", text, flags=re.UNICODE)


def norm(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def story_text(plan: StorytellingPlan) -> str:
    return '\n\n'.join(s.text_en.strip() for s in sorted(plan.narration_segments, key=lambda x: x.start))


def assess_story(plan: StorytellingPlan, duration: float) -> dict:
    """Validate a time-distributed story; segments with no or tiny narration never pass."""
    if not math.isfinite(duration) or duration <= 65.0:
        raise StoryCoverageError('DURATION_GATE: actual clip must be strictly >65 seconds')
    plan.validate_duration(duration)
    segments = sorted(plan.narration_segments, key=lambda s:s.start)
    if len(segments) < MIN_SEGMENTS:
        raise StoryCoverageError(f'STORY_TOO_SHORT: need >= {MIN_SEGMENTS} independent segments, got {len(segments)}')
    if len(segments) > 18:
        raise StoryCoverageError('STORY_TOO_FRAGMENTED: no more than 18 segments')
    nwords = sum(len(words(s.text_en)) for s in segments)
    minimum = math.ceil(duration * MIN_TEXT_WPS)
    maximum = math.floor(duration * MAX_TEXT_WPS)
    if nwords < minimum:
        raise StoryCoverageError(f'STORY_TOO_SHORT: {nwords} words; need >= {minimum} words for {duration:.2f}s clip')
    if nwords > maximum:
        raise StoryCoverageError(f'STORY_TOO_DENSE: {nwords} words; max {maximum}, preserve workshop ASMR pauses')
    if segments[0].start > MAX_START_DELAY:
        raise StoryCoverageError('STORY_START_TOO_LATE: no hook within first 5s')
    if duration - segments[-1].end > MAX_END_TAIL:
        raise StoryCoverageError('STORY_END_TOO_EARLY: no narration planned near end of clip')
    total_slots = sum(s.end-s.start for s in segments)
    if total_slots/duration < MIN_PLANNED_COVERAGE:
        raise StoryCoverageError(f'STORY_TIMELINE_TOO_SPARSE: planned narration slots {total_slots/duration:.1%}; need >= {MIN_PLANNED_COVERAGE:.0%}')
    if total_slots/duration > .93:
        raise StoryCoverageError('STORY_TOO_DENSE: leave some natural workshop ASMR pauses')
    for i,s in enumerate(segments):
        w=len(words(s.text_en)); slot=s.end-s.start
        if w < 6:
            raise StoryCoverageError(f'STORY_FRAGMENT_TOO_SHORT: {s.id} has only {w} words')
        if w/slot > MAX_SPEED_WORDS_PER_SEC:
            raise StoryCoverageError(f'STORY_TTS_WILL_NOT_FIT: {s.id} has {w} words in {slot:.2f}s slot')
        if i and s.start - segments[i-1].end > MAX_PLAN_GAP:
            raise StoryCoverageError(f'STORY_HAS_DEAD_ZONE: gap after {segments[i-1].id} too long')
    return {'duration_sec':duration,'segments':len(segments),'words':nwords,
            'min_words':minimum,'planned_coverage_ratio':round(total_slots/duration,4),
            'last_planned_voice_end_sec':segments[-1].end,'status':'PASS_FULL_STORY_TEXT'}


def approved_duration(folder:Path) -> float:
    # One single gate preserves v3.5 rights/provenance/viral approval and FFprobe >65s.
    from director_workflow_v35 import assert_approved
    assert_approved(folder)
    return ffprobe_duration(folder/'clip.mp4')


def seal_script(folder:Path) -> dict:
    """Run after a complete story_plan.json was written; refuses partial script.

    script_en.txt must match ALL narration segments exactly, not only first segment.
    """
    folder=Path(folder).resolve()
    duration=approved_duration(folder)
    plan_path=folder/'story_plan.json'
    plan=StorytellingPlan.model_validate_json(plan_path.read_text(encoding='utf-8'))
    stats=assess_story(plan,duration)
    full=story_text(plan)
    full_path=folder/'script_en.txt'
    if not full_path.is_file():
        raise StoryCoverageError('SCRIPT_MISSING: require full script_en.txt, not only story_plan segments')
    if norm(full_path.read_text(encoding='utf-8')) != norm(full):
        raise StoryCoverageError('SCRIPT_SEGMENTS_MISMATCH: full script_en.txt differs from ALL narration_segments')
    tts_script=folder/'script_tts.txt'
    if not tts_script.is_file() or norm(tts_script.read_text(encoding='utf-8')) != norm(' '.join(seg.text_en for seg in sorted(plan.narration_segments,key=lambda x:x.start))):
        raise StoryCoverageError('TTS_SCRIPT_INCOMPLETE: script_tts.txt must contain ALL narration_segments')
    record={**stats,'policy_version':'3.6',
            'clip_sha256':sha256(folder/'clip.mp4'),
            'story_plan_sha256':sha256(plan_path),
            'full_script_sha256':sha256(full_path),
            'script_tts_sha256':sha256(tts_script),
            'segment_ids':[s.id for s in sorted(plan.narration_segments,key=lambda s:s.start)]}
    (folder/'story_coverage_v36.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    return record


def require_sealed_script(folder:Path) -> dict:
    folder=Path(folder).resolve()
    record_path=folder/'story_coverage_v36.json'
    if not record_path.is_file():
        raise StoryCoverageError('STORY_NOT_SEALED: run story_coverage_v36.py seal before spending TTS credits')
    recorded=json.loads(record_path.read_text(encoding='utf-8'))
    if recorded.get('policy_version')!='3.6' or recorded.get('status')!='PASS_FULL_STORY_TEXT':
        raise StoryCoverageError('STORY_NOT_APPROVED: require valid v3.6 coverage record')
    plan=folder/'story_plan.json';script=folder/'script_en.txt';clip=folder/'clip.mp4'
    for file,field in [(plan,'story_plan_sha256'),(script,'full_script_sha256'),
                       (folder/'script_tts.txt','script_tts_sha256'),(clip,'clip_sha256')]:
        if not file.is_file() or sha256(file)!=recorded.get(field):
            raise StoryCoverageError(f'STORY_STALE_OR_CHANGED: {file.name}, re-seal and regenerate voice as needed')
    verified=seal_script(folder)
    if any(verified.get(k)!=recorded.get(k) for k in (
        'duration_sec','segments','words','segment_ids','planned_coverage_ratio')):
        raise StoryCoverageError('STORY_RECORD_INCONSISTENT')
    return verified


def verify_all_tts(folder:Path) -> dict:
    """Require EVERY segment, exact alignment and audio spoken time covering the clip.

    Called before ANY render. ffprobe uses actual TTS bytes, not expected slot length.
    """
    folder=Path(folder).resolve()
    approved= require_sealed_script(folder)
    plan=StorytellingPlan.model_validate_json((folder/'story_plan.json').read_text(encoding='utf-8'))
    duration=approved['duration_sec']
    actual=[]; details=[]
    for s in sorted(plan.narration_segments,key=lambda x:x.start):
        f=tts_path(folder,s)
        if not f.is_file() or f.stat().st_size == 0:
            raise StoryCoverageError(f'TTS_INCOMPLETE: missing voice for {s.id}: {f}')
        audio_sec=ffprobe_duration(f)
        if not math.isfinite(audio_sec) or audio_sec<=.2:
            raise StoryCoverageError(f'TTS_BROKEN: {s.id}')
        if audio_sec > s.end-s.start + .03 or s.start+audio_sec>duration+.03:
            raise StoryCoverageError(f'TTS_OVERFLOWS_SLOT: {s.id} ({audio_sec:.2f}s)')
        wc=len(words(s.text_en))
        if audio_sec < wc / MAX_SPEED_WORDS_PER_SEC:
            raise StoryCoverageError(f'TTS_TRUNCATED_OR_TOO_FAST: {s.id}, {wc} words in {audio_sec:.2f}s')
        aligned=_alignment_words(f.with_suffix('.alignment.json'),s.text_en,s.start,audio_sec)
        # All words must fit inside the TTS; reject a mismatched or cut-off final phrase.
        if aligned[-1][1] > s.start+audio_sec+.05:
            raise StoryCoverageError(f'TTS_ALIGNMENT_EXCEEDS_AUDIO: {s.id}')
        actual.append((s.start,s.start+audio_sec))
        details.append({'id':s.id,'word_count':wc,'tts_duration_sec':round(audio_sec,3),
                        'audio_sha256':sha256(f),'alignment_sha256':sha256(f.with_suffix('.alignment.json'))})
    audio_seconds=sum(end-start for start,end in actual)
    ratio=audio_seconds/duration
    if ratio<MIN_ACTUAL_TTS_COVERAGE:
        raise StoryCoverageError(f'TTS_COVERAGE_TOO_LOW: {ratio:.1%}; need >= {MIN_ACTUAL_TTS_COVERAGE:.0%}, regenerate longer English script/voice')
    if actual[0][0] > MAX_START_DELAY or duration-actual[-1][1]>MAX_TTS_END_TAIL:
        raise StoryCoverageError('TTS_TIMELINE_INCOMPLETE: English voice missing at start or near end')
    if any(b[0]-a[1]>MAX_ACTUAL_GAP for a,b in zip(actual,actual[1:])):
        raise StoryCoverageError('TTS_TIMELINE_HAS_LONG_SILENCE: narration truncated or mispositioned')
    return {'status':'PASS_FULL_TTS','policy_version':'3.6','spoken_audio_seconds':round(audio_seconds,3),
            'actual_tts_coverage_ratio':round(ratio,4), 'tts_segments':len(details), 'details':details}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('cmd',choices=['seal','gate','tts-check']);p.add_argument('--folder',type=Path,required=True)
    a=p.parse_args()
    r=seal_script(a.folder) if a.cmd=='seal' else require_sealed_script(a.folder) if a.cmd=='gate' else verify_all_tts(a.folder)
    print(json.dumps(r,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
