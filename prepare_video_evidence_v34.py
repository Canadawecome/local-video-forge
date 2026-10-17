#!/usr/bin/env python3
"""Create auditable, time-labelled source/Opus clip frame evidence.

No claims of direct native understanding of a YouTube URL: the media must be local.
The user / ingest tool is responsible for legitimate access and usage permissions.
"""
from __future__ import annotations
import argparse, hashlib, json, math, subprocess
from pathlib import Path
from viral_director_contracts_v34 import EvidenceManifest


def sha256(path:Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda:fh.read(1<<20),b''):h.update(chunk)
    return h.hexdigest()


def probe(video:Path) -> tuple[float,int,int]:
    p=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)],
                     check=True,text=True,capture_output=True)
    data=json.loads(p.stdout)
    v=next((x for x in data['streams'] if x['codec_type']=='video'),None)
    if not v:raise ValueError('No video stream')
    dur=float(data['format']['duration']); w=int(v['width']);h=int(v['height'])
    if dur<=0:raise ValueError('Invalid duration')
    return dur,w,h


def build(video:Path, output_dir:Path, kind:str, step_sec:float=3.0,
          max_frames:int=120, windows:list[list[float]]|None=None,
          transcript:Path|None=None) -> EvidenceManifest:
    video=video.resolve();output_dir=output_dir.resolve()
    if not video.is_file():raise FileNotFoundError(video)
    duration,w,h=probe(video)
    if step_sec<.25 or max_frames<2:raise ValueError('step_sec >= .25 and max_frames >= 2 required')
    if windows:
        intervals=[(max(0,float(a)),min(duration,float(b))) for a,b in windows]
        if any(b<=a for a,b in intervals):raise ValueError('Invalid windows')
    else:intervals=[(0,duration)]
    times=[]
    for a,b in intervals:
        n=max(1,int(math.ceil((b-a)/step_sec)))
        times.extend(min(max(0,duration-.5),a+i*step_sec) for i in range(n) if a+i*step_sec<duration)
        times.append(min(max(0,duration-.5),b-.04))
    times=sorted(set(round(max(0,t),3) for t in times))
    if len(times)>max_frames:
        # Uniform downsampling is EXPLICITLY recorded; may miss rapid highlights.
        selected=[round(i*(len(times)-1)/(max_frames-1)) for i in range(max_frames)]
        times=[times[i] for i in dict.fromkeys(selected)]
    output_dir.mkdir(parents=True,exist_ok=True)
    frames_dir=output_dir/'frames';frames_dir.mkdir(exist_ok=True)
    frames=[]
    for i,t in enumerate(times):
        rel=f'frames/frame_{i:04d}.jpg';path=output_dir/rel
        cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(t),'-i',str(video),
             '-frames:v','1','-vf','scale=640:-2','-q:v','4',str(path)]
        subprocess.run(cmd,check=True,capture_output=True)
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f'Frame extraction failed at {t:.3f}s')
        frames.append({'id':f'frame_{i:04d}','time_sec':t,'path':rel})
    manifest=EvidenceManifest.model_validate({
        'media_kind':kind,'media_sha256':sha256(video),'media_file':str(video),
        'duration_sec':round(duration,3),'width':w,'height':h,'frames':frames,
        'transcript_path':str(transcript.resolve()) if transcript else None,
        'visual_sampling_note':f'{len(times)} still frames sampled; no native full-motion perception. '
                               f'requested_step={step_sec}; max_frames={max_frames}; '
                               'fast actions between frames can be missed; audio needs separate analysis.'})
    (output_dir/'evidence_manifest.json').write_text(manifest.model_dump_json(indent=2),encoding='utf-8')
    return manifest


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--video',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--kind',choices=['SOURCE','OPUS_CLIP'],required=True)
    p.add_argument('--step-sec',type=float,default=3)
    p.add_argument('--max-frames',type=int,default=120)
    p.add_argument('--windows-json',type=Path,help='JSON [[start_sec,end_sec],...] to resample densely')
    p.add_argument('--transcript',type=Path)
    a=p.parse_args()
    windows=json.loads(a.windows_json.read_text()) if a.windows_json else None
    print(build(a.video,a.output_dir,a.kind,a.step_sec,a.max_frames,windows,a.transcript).model_dump_json(indent=2))

if __name__=='__main__':main()
