#!/usr/bin/env python3
"""Render Cinematic ASMR visuals while keeping SOURCE TIMECODES and NO AUDIO.

Output: effects/video_effects.mp4 (video-only), effects/video_effects_manifest.json.
Pass this video to the v3.2 storytelling renderer, which ALWAYS mixes the
original, QC-approved clean workshop bed + independent ElevenLabs narration.
This stage never touches audio, German-speech stems, voice or subtitles.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
from smart_effect_contracts_v32 import SmartEffectPlan


def _run(args: list[str]):
    result=subprocess.run(args, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError('FFmpeg failed: '+result.stderr[-2400:])


def _probe(path: Path) -> dict:
    p=subprocess.run(['ffprobe','-v','error','-show_entries',
                      'format=duration:stream=index,codec_type,width,height,avg_frame_rate',
                      '-of','json',str(path)],check=True,capture_output=True,text=True)
    return json.loads(p.stdout)


def _sha256(path: Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda:f.read(1<<20),b''): h.update(part)
    return h.hexdigest()


def _fps(video: dict)->float:
    stream=next((x for x in video.get('streams',[]) if x.get('codec_type')=='video'),None)
    if not stream: raise ValueError('No video stream')
    a,b=map(int,stream['avg_frame_rate'].split('/'))
    if b<=0 or a<=0: raise ValueError('Unknown fps')
    value=a/b
    if not 12<=value<=60: raise ValueError('FPS outside 12..60; review source')
    return value


def _filter(plan: SmartEffectPlan, width: int, height: int, fps: float)->str:
    terms=[];xs=[];ys=[]
    for z in plan.micro_zooms:
        first=round(z.start*fps);last=round(z.end*fps)
        if last<=first: continue
        # Half-sine ramp (1 at first/last, peak at midpoint), no temporal change.
        # Clamped to avoid harmful unbounded zoom; single-frame output per input frame.
        time=f'between(on,{first},{last})'
        terms.append(f'({z.peak_scale-1:.6f})*if({time},sin(PI*(on-{first})/{last-first}),0)')
        xs.append(f'if({time},{z.center_x:.5f},')
        ys.append(f'if({time},{z.center_y:.5f},')
    zoom='1+'+'+'.join(terms) if terms else '1'
    def weighted(attr: str)->str:
        exp='.5'
        for z in reversed(plan.micro_zooms):
            first=round(z.start*fps);last=round(z.end*fps)
            exp=f'if(between(on,{first},{last}),{getattr(z,attr):.5f},{exp})'
        return exp
    x=f'(iw-iw/zoom)*({weighted("center_x")})'
    y=f'(ih-ih/zoom)*({weighted("center_y")})'
    # Preserve crop aspect. Opus output must already be 9:16.
    return (f'fps={fps:.8f},format=yuv420p,'
            f'zoompan=z=\'{zoom}\':x=\'{x}\':y=\'{y}\':d=1:s={width}x{height}:fps={fps:.8f},'
            f'eq=contrast={plan.grading.contrast}:saturation={plan.grading.saturation}:'
            f'brightness={plan.grading.brightness}')


def render(folder: Path) -> dict:
    folder=folder.resolve();src=folder/'clip.mp4';plan_path=folder/'effect_plan.json'
    if not src.exists() or not plan_path.exists(): raise ValueError('Missing clip.mp4 or effect_plan.json')
    plan=SmartEffectPlan.model_validate_json(plan_path.read_text(encoding='utf-8'))
    if _sha256(src)!=plan.source_clip_sha256:
        raise ValueError('EFFECT_STALE: source hash no longer matches effect plan')
    info=_probe(src)
    input_duration=float(info['format']['duration']);fps=_fps(info)
    if abs(input_duration-plan.duration_seconds)>.085:
        raise ValueError('EFFECT_STALE: source duration differs from approved effect plan')
    v=next(x for x in info['streams'] if x.get('codec_type')=='video')
    width,height=int(v['width']),int(v['height'])
    if abs(width/height-9/16)>.025:
        raise ValueError('Smart visual stage expects Opus 9:16 clip, not raw 16:9')
    dest=folder/'effects';dest.mkdir(parents=True,exist_ok=True)
    out=dest/'video_effects.mp4';partial=dest/'video_effects.partial.mp4'
    manifest=dest/'video_effects_manifest.json'
    out.unlink(missing_ok=True);manifest.unlink(missing_ok=True);partial.unlink(missing_ok=True)
    vf=_filter(plan,width,height,fps)
    try:
        _run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-i',str(src),
              '-vf',vf,'-an','-sn','-dn','-c:v','libx264','-preset','veryfast',
              '-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(partial)])
        rendered=_probe(partial)
        if any(s.get('codec_type')=='audio' for s in rendered.get('streams',[])):
            raise ValueError('Visual effects output must have no audio stream')
        output_duration=float(rendered['format']['duration'])
        if abs(output_duration-input_duration)>max(.09,1.2/fps):
            raise ValueError('EFFECT_TIMELINE_DRIFT: rendering changed video duration')
        if _fps(rendered)!=fps and abs(_fps(rendered)-fps)>0.03:
            raise ValueError('EFFECT_TIMELINE_DRIFT: frame rate changed')
        partial.replace(out)
        result={'schema_version':'3.2','preset':plan.preset,
                'source_clip_sha256':_sha256(src),'effect_plan_sha256':_sha256(plan_path),
                'effect_video_sha256':_sha256(out),'source_duration':input_duration,
                'output_duration':output_duration,'source_fps':fps,'output_fps':_fps(rendered),
                'video_only_no_audio':True,'source_timecodes_preserved':True,
                'micro_zoom_windows':len(plan.micro_zooms),
                'result_first_hook_applied':False,
                'unapplied_hook_suggestion':plan.result_first_hook is not None,
                'color_grading_applied':True,
                'notes':'No audio manipulated; hook/speed/b-roll reorder needs upstream re-edit and new time map.'}
        manifest.write_text(json.dumps(result,indent=2),encoding='utf-8')
        return result
    finally:
        partial.unlink(missing_ok=True)


def verify(folder: Path)->tuple[Path,dict]:
    folder=folder.resolve();src=folder/'clip.mp4'
    plan_path=folder/'effect_plan.json'
    out=folder/'effects'/'video_effects.mp4'
    manifest_path=folder/'effects'/'video_effects_manifest.json'
    if not out.exists() or not manifest_path.exists():
        raise ValueError('NEEDS_EFFECT_RENDER: missing rendered effects/manifest')
    m=json.loads(manifest_path.read_text(encoding='utf-8'))
    plan=SmartEffectPlan.model_validate_json(plan_path.read_text(encoding='utf-8'))
    if not (m.get('source_clip_sha256')==_sha256(src)==plan.source_clip_sha256 and
            m.get('effect_plan_sha256')==_sha256(plan_path) and
            m.get('effect_video_sha256')==_sha256(out) and
            m.get('video_only_no_audio') is True and
            m.get('source_timecodes_preserved') is True):
        raise ValueError('EFFECT_STALE: video/plan/hash validation failed')
    if abs(float(_probe(out)['format']['duration'])-float(_probe(src)['format']['duration']))>.09:
        raise ValueError('EFFECT_TIMELINE_DRIFT: output/source duration mismatch')
    if any(s.get('codec_type')=='audio' for s in _probe(out)['streams']):
        raise ValueError('EFFECT_AUDIO_LEAK: effect track unexpectedly has audio')
    return out,m


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['process','verify']);p.add_argument('--folder',type=Path,required=True)
    args=p.parse_args();print(json.dumps(render(args.folder) if args.command=='process' else verify(args.folder)[1],indent=2))

if __name__=='__main__':main()
