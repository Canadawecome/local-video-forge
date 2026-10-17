#!/usr/bin/env python3
"""Auditable final asset checks, independent of render-success/Opus success flags."""
from pathlib import Path
import json
import numpy as np
import soundfile as sf
from story_coverage_v36 import verify_all_tts, StoryCoverageError
from storytelling_render_v33 import ffprobe_duration
from storytelling_contracts_v33 import StorytellingPlan


def check_final(folder:Path)->dict:
    folder=Path(folder).resolve()
    coverage=verify_all_tts(folder)
    plan=StorytellingPlan.model_validate_json((folder/'story_plan.json').read_text(encoding='utf8'))
    clip_duration=ffprobe_duration(folder/'clip.mp4')
    final=folder/'final.mp4'
    if not final.is_file():raise StoryCoverageError('FINAL_MISSING')
    final_duration=ffprobe_duration(final)
    if abs(final_duration-clip_duration)>.25:
        raise StoryCoverageError(f'FINAL_TRUNCATED: source={clip_duration:.3f}s, final={final_duration:.3f}s')
    qc_path=folder/'qc_report.json'
    if not qc_path.exists():raise StoryCoverageError('FINAL_MISSING_QC_REPORT')
    qc=json.loads(qc_path.read_text(encoding='utf-8'))
    if qc.get('english_voice_segments')!=len(plan.narration_segments):
        raise StoryCoverageError('FINAL_SEGMENT_COUNT_MISMATCH')
    sub=folder/'captions_en.srt'
    if not sub.exists() or '-->' not in sub.read_text(encoding='utf-8'):
        raise StoryCoverageError('FINAL_MISSING_CAPTIONS')
    voice=folder/'audio'/'english_voice_only.wav'
    if not voice.exists():raise StoryCoverageError('FINAL_MISSING_VOICE_TRACK')
    samples,sr=sf.read(voice,always_2d=True,dtype='float32')
    # Each voice region must contain real nonzero samples (not only metadata, or a silent wav).
    for s in plan.narration_segments:
        a=int(round(s.start*sr));b=min(len(samples),int(round(s.end*sr)))
        if b<=a:raise StoryCoverageError(f'FINAL_INVALID_VOICE_WINDOW: {s.id}')
        rms=float(np.sqrt(np.mean(np.square(samples[a:b],dtype=np.float64))))
        if rms<1e-4:
            raise StoryCoverageError(f'FINAL_SILENT_TTS: {s.id}, rms {rms:.7f}')
    return {'status':'PASS_FULL_STORY_FINAL','source_duration_sec':clip_duration,
            'final_duration_sec':final_duration,'narration_segments':len(plan.narration_segments),
            'actual_tts_coverage_ratio':coverage['actual_tts_coverage_ratio'],
            'all_voice_windows_non_silent':True,'asmr_pipeline':'INHERITED_CLEAN_ASMR_QC'}
