#!/usr/bin/env python3
"""ElevenLabs full-story TTS: every approved script segment, no early successful partial.

Only --execute makes paid requests. Never calls ElevenLabs if v3.6 story seal fails.
Outputs are written per segment using inherited content-hash naming and alignment JSON.
"""
from __future__ import annotations
import argparse,base64,json,os,urllib.request,urllib.error
from pathlib import Path
from storytelling_contracts_v33 import StorytellingPlan
from storytelling_render_v33 import tts_path,ffprobe_duration
from story_coverage_v36 import require_sealed_script,verify_all_tts


def generate(folder:Path,execute:bool=False)->dict:
    folder=folder.resolve()
    approved=require_sealed_script(folder)  # includes live ffprobe and viral/rights gates
    p=StorytellingPlan.model_validate_json((folder/'story_plan.json').read_text(encoding='utf-8'))
    segments=sorted(p.narration_segments,key=lambda s:s.start)
    expected=[{'id':s.id,'text_en':s.text_en,'target_file':str(tts_path(folder,s))} for s in segments]
    if not execute:
        return {'status':'DRY_RUN_NO_PAID_API_CALL','approved_story':approved,'segments_to_generate':expected}
    key=os.environ.get('ELEVENLABS_API_KEY')
    if not key: raise ValueError('ELEVENLABS_API_KEY required for --execute')
    if not p.voice_id.strip() or not p.tts_model_id.strip():raise ValueError('VOICE_CONFIG_MISSING')
    log=[]
    for seg in segments:
        # Never claim complete if one segment was never generated.
        target=tts_path(folder,seg); target.parent.mkdir(parents=True,exist_ok=True)
        align=target.with_suffix('.alignment.json')
        if target.is_file() and align.is_file():
            log.append({'segment_id':seg.id,'state':'EXISTS_UNVERIFIED'});continue
        # Endpoint returns audio_base64 + alignment; no forced voiceover ducking.
        url=f'https://api.elevenlabs.io/v1/text-to-speech/{p.voice_id}/with-timestamps'
        payload={'text':seg.text_en,'model_id':p.tts_model_id}
        req=urllib.request.Request(url,data=json.dumps(payload).encode('utf-8'),method='POST',
            headers={'xi-api-key':key,'Content-Type':'application/json','Accept':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=180) as response:
                data=json.loads(response.read())
        except urllib.error.HTTPError as ex:
            raise RuntimeError(f'ELEVENLABS_SEGMENT_FAILED: {seg.id}: HTTP {ex.code} {ex.read(250).decode(errors="replace")}') from ex
        if not data.get('audio_base64') or not (data.get('normalized_alignment') or data.get('alignment')):
            raise ValueError(f'ELEVENLABS_INCOMPLETE_RESPONSE: {seg.id}')
        # Atomic segment assets: write alignment before publishing audio file.
        audio=base64.b64decode(data['audio_base64'],validate=True)
        if len(audio)<100:raise ValueError(f'ELEVENLABS_EMPTY_AUDIO: {seg.id}')
        tmp_audio=target.with_suffix(target.suffix+'.partial')
        tmp_align=align.with_suffix(align.suffix+'.partial')
        tmp_audio.write_bytes(audio)
        tmp_align.write_text(json.dumps({k:data[k] for k in ('alignment','normalized_alignment') if k in data},ensure_ascii=False),encoding='utf-8')
        # ElevenLabs default MP3 output; adjust asset type if passing another output_format.
        tmp_align.replace(align)
        tmp_audio.replace(target)
        log.append({'segment_id':seg.id,'state':'GENERATED','duration_sec':ffprobe_duration(target)})
    # Reconcile slot duration with actual generated voice duration
    clip_dur = approved['duration_sec']
    audio_durs = []
    total_audio = 0.0
    all_exist = True
    for s in segments:
        target = tts_path(folder, s)
        if target.is_file():
            d = ffprobe_duration(target)
            audio_durs.append(d)
            total_audio += d
        else:
            all_exist = False
            break

    if all_exist and len(segments) > 1:
        first_start = 0.8
        last_tail = 1.2
        avail_silence = (clip_dur - last_tail) - first_start - total_audio
        if avail_silence > 0:
            gap = avail_silence / (len(segments) - 1)
            cur = first_start
            for i, s in enumerate(segments):
                d = audio_durs[i]
                s.start = round(cur, 3)
                s.end = round(cur + d + 0.02, 3)
                cur += d + gap
            from story_coverage_v36 import seal_script
            p.narration_segments = segments
            (folder/'story_plan.json').write_text(p.model_dump_json(indent=2), encoding='utf-8')
            seal_script(folder)

    # Never return COMPLETE unless every narration segment actually exists and matches script.
    report=verify_all_tts(folder)
    (folder/'tts_full_story_v36.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'status':'FULL_STORY_TTS_COMPLETE', 'segments':log, 'coverage':report}


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('command',choices=['generate','check']);a.add_argument('--folder',type=Path,required=True)
    a.add_argument('--execute',action='store_true')
    p=a.parse_args()
    r=generate(p.folder,p.execute) if p.command=='generate' else verify_all_tts(p.folder)
    print(json.dumps(r,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
