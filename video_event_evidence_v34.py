#!/usr/bin/env python3
"""Optional heuristics for source scene boundaries and undifferentiated audio onsets.

Neither output identifies hammering or recognizes speech. No claims of actual action recognition.
"""
import argparse,json,re,subprocess, tempfile
from pathlib import Path
import numpy as np
import soundfile as sf
from prepare_video_evidence_v34 import sha256,probe


def scene_changes(video:Path,threshold:float=.35,max_events:int=200) -> list[dict]:
    cmd=['ffmpeg','-hide_banner','-loglevel','info','-i',str(video),
         '-vf',f"select='gt(scene,{threshold})',showinfo",'-an','-f','null','-']
    p=subprocess.run(cmd,capture_output=True,text=True)
    if p.returncode:raise RuntimeError('FFmpeg scene scan failed: '+p.stderr[-700:])
    times=[]
    for val in re.findall(r'pts_time:([0-9.]+)',p.stderr):
        t=float(val)
        if not times or t-times[-1]>.25:
            times.append(t)
    return [{'time_sec':round(t,3),'kind':'VISUAL_SCENE_CHANGE','note':'Heuristic FFmpeg scene detection'}
            for t in times[:max_events]]


def audio_onsets(video:Path,max_events:int=150) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        wav=Path(tmp)/'audio.wav'
        p=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(video),
                          '-vn','-ac','1','-ar','16000','-acodec','pcm_s16le',str(wav)],
                         capture_output=True)
        if p.returncode or not wav.is_file():
            return [] # legitimate silent/no-audio source
        samples,sr=sf.read(wav,always_2d=False)
    if len(samples)<sr//2:return []
    hop=round(sr*.02)
    n=len(samples)//hop
    z=np.diff(samples[:n*hop],prepend=samples[0])
    energy=np.sqrt(np.mean(z.reshape(n,hop).astype('float64')**2,axis=1))
    baseline=np.median(energy)
    threshold=max(baseline*5,.006)
    cand=np.flatnonzero(energy>threshold)
    cand=sorted(cand,key=lambda i:energy[i],reverse=True)
    events=[]
    for i in cand:
        sec=round(float(i)*hop/sr,3)
        if any(abs(e['time_sec']-sec)<.42 for e in events):continue
        events.append({'time_sec':sec,'kind':'AUDIO_TRANSIENT_UNCLASSIFIED',
                       'strength':round(float(energy[i]),5),
                       'note':'Energy onset; not proof of hammer/grinder. Speech/noise may trigger it.'})
        if len(events)>=max_events:break
    return sorted(events,key=lambda x:x['time_sec'])


def analyze(video:Path,out:Path,threshold:float=.35) -> dict:
    duration,_,_=probe(video)
    report={'schema_version':'3.4','source_sha256':sha256(video),
            'duration_sec':duration,'scene_events':scene_changes(video,threshold),
            'audio_onset_events':audio_onsets(video),
            'limitations':['Scene cuts are not craft-action recognition',
               'Audio onset spikes can be speech/music and are not ASMR classification',
               'Use densified original frames/video + human QC for exact hammer and speech events']}
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--video',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--scene-threshold',type=float,default=.35)
    a=p.parse_args()
    if not .1<=a.scene_threshold<=.9:raise ValueError('scene threshold must be .1-.9')
    r=analyze(a.video,a.output,a.scene_threshold)
    print(json.dumps({'scene_events':len(r['scene_events']),
                      'audio_onsets':len(r['audio_onset_events']),'output':str(a.output)}))

if __name__=='__main__':main()
