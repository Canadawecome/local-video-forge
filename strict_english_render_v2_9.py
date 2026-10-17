#!/usr/bin/env python3
"""Local Video Forge v2.9 — strict German-speech-replacement + embedded English subtitles.

This is an offline *render integration module*, not an OpusClip/SAM/ElevenLabs client.
It refuses to render if an approved, speech-free residual is unavailable for a
clip containing German speech; no whole-track ducking fallback is allowed.
It refuses to render without timed EN TTS alignment; exports EN SRT and burns
it into the video. QC flags require independent listening confirmation.

Per-clip folder:
  clip.mp4; audio_plan.json (existing v2.7 HybridClipPlan)
  audio/residual_workshop.wav; audio/replacement_qc.json
  audio/tts/{name}.mp3 and audio/tts/{name}.alignment.json
  or audio_path in voice_segments and corresponding .alignment.json
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

import numpy as np
import soundfile as sf
from hybrid_audio_contracts_v2_7 import HybridClipPlan

SR = 48000


def cmd_run(args: list[str], *, cwd: Path | None = None) -> None:
    p = subprocess.run([str(x) for x in args], cwd=cwd, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        raise RuntimeError(f"Command error: {p.stderr[-2200:]}")


def ffprobe_duration(path: Path) -> float:
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                       check=True, capture_output=True, text=True)
    return float(p.stdout.strip())


def decode(path: Path, tmp: Path) -> np.ndarray:
    target = tmp / (hashlib.sha256(str(path).encode()).hexdigest()[:14] + ".wav")
    cmd_run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
             "-i", str(path), "-map", "0:a:0", "-ac", "2", "-ar", str(SR),
             "-c:a", "pcm_s16le", str(target)])
    data, hz = sf.read(target, dtype="float32", always_2d=True)
    if hz != SR or data.shape[1] != 2:
        raise ValueError("Expected 48kHz stereo after decoding")
    return data


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def resolve_asset(folder: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else folder / p


def tts_path(folder: Path, seg) -> Path:
    if seg.audio_path:
        return resolve_asset(folder, seg.audio_path)
    sig = hashlib.sha256(json.dumps([seg.text_en, seg.kind, seg.speech_ids],
                                    ensure_ascii=False).encode()).hexdigest()[:12]
    return folder / 'audio' / 'tts' / f'{seg.id}_{sig}.mp3'


def get_approved_background(folder: Path, plan: HybridClipPlan, clip: Path,
                            clip_duration: float) -> tuple[Path | None, dict]:
    """Fail closed; audio approval tied to source/stem checksums."""
    if not plan.source_german_speech:
        # Source content must have been checked for actually being speech-free.
        meta = folder / 'audio' / 'replacement_qc.json'
        if not meta.exists():
            raise ValueError('NEEDS_AUDIO_REVIEW: missing replacement_qc.json (even a no-speech clip must be checked)')
        gate = json.loads(meta.read_text(encoding='utf-8'))
        if not gate.get('source_speech_absence_confirmed') or gate.get('source_sha256') != sha256(clip):
            raise ValueError('NEEDS_AUDIO_REVIEW: source speech absence not approved for current clip hash')
        return None, gate

    if not plan.approved_workshop_stem_path or not plan.workshop_stem_qc_passed:
        raise ValueError('NEEDS_AUDIO_REVIEW: German speech present; no approved speech-free residual. -24dB fallback is forbidden.')
    stem = resolve_asset(folder, plan.approved_workshop_stem_path)
    if not stem.is_file():
        raise ValueError(f'NEEDS_AUDIO_REVIEW: missing approved residual {stem}')
    if abs(ffprobe_duration(stem) - clip_duration) > .10:
        raise ValueError('NEEDS_AUDIO_REVIEW: residual duration mismatches video')
    qc_path = folder / 'audio' / 'replacement_qc.json'
    if not qc_path.is_file():
        raise ValueError('NEEDS_AUDIO_REVIEW: missing audio/replacement_qc.json')
    qc = json.loads(qc_path.read_text(encoding='utf-8'))
    if not all(qc.get(k) is True for k in ['german_voice_absent', 'asmr_preserved', 'clip_transcript_checked']):
        raise ValueError('NEEDS_AUDIO_REVIEW: speech-removal / ASMR / transcript QA not approved')
    if not str(qc.get('reviewed_by', '')).strip():
        raise ValueError('NEEDS_AUDIO_REVIEW: QC reviewer identity missing')
    if qc.get('source_sha256') != sha256(clip) or qc.get('residual_sha256') != sha256(stem):
        raise ValueError('NEEDS_AUDIO_REVIEW: QC approval is stale (source/stem changed)')
    return stem, qc


def background_swap_envelope(n: int, intervals: list, preroll=.13, postroll=.17) -> np.ndarray:
    """Residual replaces RAW 100% throughout every confirmed DE interval."""
    env = np.zeros(n, dtype=np.float32)
    for s in intervals:
        i0 = max(0, round((s.start-preroll)*SR))
        i1 = max(0, min(n, round(s.start*SR)))
        i2 = max(0, min(n, round(s.end*SR)))
        i3 = min(n, round((s.end+postroll)*SR))
        if i1 > i0:
            env[i0:i1] = np.maximum(env[i0:i1], np.linspace(0, 1, i1-i0, dtype=np.float32))
        if i2 > i1:
            env[i1:i2] = 1.0
        if i3 > i2:
            env[i2:i3] = np.maximum(env[i2:i3], np.linspace(1, 0, i3-i2, dtype=np.float32))
    return env


def _alignment_words(path: Path, expected: str, onset: float, duration: float) -> list[tuple[float,float,str]]:
    if not path.exists():
        raise ValueError(f'NEEDS_CAPTION_ALIGNMENT: missing {path}; use ElevenLabs with-timestamps or align English TTS first')
    data = json.loads(path.read_text(encoding='utf-8'))
    align = data.get('normalized_alignment') or data.get('alignment') or data
    chars = align.get('characters') or []
    start = align.get('character_start_times_seconds') or []
    end = align.get('character_end_times_seconds') or []
    if not chars or len(chars) != len(start) or len(chars) != len(end):
        raise ValueError(f'NEEDS_CAPTION_ALIGNMENT: invalid timestamps in {path}')
    spoken = ''.join(chars)
    norm = lambda s: re.sub(r'\s+', ' ', s).strip().casefold()
    if norm(spoken) != norm(expected):
        raise ValueError('NEEDS_CAPTION_ALIGNMENT: TTS alignment does not match English script; do not subtitle the wrong words')
    if any(float(a) > float(b) or float(a) < 0 for a,b in zip(start,end)):
        raise ValueError('NEEDS_CAPTION_ALIGNMENT: invalid word timing')
    if any(float(end[i]) > float(start[i+1]) + 0.04 for i in range(len(chars)-1)):
        raise ValueError('NEEDS_CAPTION_ALIGNMENT: non-monotonic alignment')
    if max(map(float,end)) > duration + .08:
        raise ValueError('NEEDS_CAPTION_ALIGNMENT: timing longer than actual TTS asset')
    words: list[tuple[float,float,str]] = []
    for m in re.finditer(r'\S+', spoken):
        a,b=m.span()
        words.append((onset+float(start[a]), onset+float(end[b-1]), spoken[a:b]))
    if not words:
        raise ValueError('NEEDS_CAPTION_ALIGNMENT: no words')
    return words


def _srt_clock(t: float) -> str:
    k = max(0, round(t*1000))
    h,k=divmod(k,3600000); minute,k=divmod(k,60000); sec,ms=divmod(k,1000)
    return f'{h:02}:{minute:02}:{sec:02},{ms:03}'


def english_captions(parts: list[tuple[float,float,str]], max_words=4) -> tuple[str, int]:
    if not parts:
        raise ValueError('NEEDS_CAPTIONS: no English text')
    out=[]
    group=[]
    for word in parts:
        if group and (len(group)>=max_words or word[0]-group[-1][1] > .38):
            out.append(group)
            group=[]
        group.append(word)
        if re.search(r'[.!?]$',word[2]) and len(group)>=2:
            out.append(group)
            group=[]
    if group: out.append(group)
    rows=[]
    for i,g in enumerate(out,1):
        a=g[0][0]; b=max(g[-1][1],a+.12)
        if not (0 <= a < b):
            raise ValueError('NEEDS_CAPTIONS: broken English caption times')
        text=' '.join(w[2] for w in g)
        rows.append(f'{i}\n{_srt_clock(a)} --> {_srt_clock(b)}\n{text}\n')
    return '\n'.join(rows)+'\n',len(out)


def process(folder: Path, *, dry_run=False) -> dict[str,Any]:
    folder=folder.resolve()
    clip=folder/'clip.mp4'
    if not dry_run:
        (folder/'final.mp4').unlink(missing_ok=True)
        (folder/'qc_report.json').unlink(missing_ok=True)
    if not clip.is_file(): raise FileNotFoundError(f'Missing clip.mp4 in {folder}')
    plan=HybridClipPlan.model_validate_json((folder/'audio_plan.json').read_text(encoding='utf-8'))
    duration=ffprobe_duration(clip)
    plan.validate_duration(duration)
    if not plan.voice_segments: raise ValueError('NEEDS_ENGLISH_VOICE: no English script/voice segments')
    if plan.source_german_speech:
        idmap={s.id:s for s in plan.source_german_speech}
        for seg in plan.voice_segments:
            if seg.kind=='dub':
                de=[idmap[i] for i in seg.speech_ids]
                if min(abs(seg.start-s.start) for s in de) > .7:
                    raise ValueError(f'NEEDS_DUB_SYNC: English dub {seg.id} does not begin around German speech')
    stem,gate=get_approved_background(folder,plan,clip,duration)
    if dry_run:
        return {'status':'GATES_PASSED', 'clip_uid':plan.clip_uid,'stem':str(stem) if stem else None}
    with tempfile.TemporaryDirectory(prefix='lvf_v29_') as tmpdirname:
        tmp=Path(tmpdirname)
        raw=decode(clip,tmp)
        n=len(raw)
        if stem:
            residual=decode(stem,tmp)
            if residual.shape[1] != raw.shape[1] or abs(len(residual)-n) > round(.05*SR):
                raise ValueError('NEEDS_AUDIO_REVIEW: source and residual lengths differ materially')
            # AAC encoders can introduce up to ~1 frame of padding. Align at 48kHz
            # after checking the actual decoded durations; never stretch a stem.
            if len(residual) < n:
                residual = np.pad(residual, ((0,n-len(residual)),(0,0)))
            else:
                residual = residual[:n]
            swap=background_swap_envelope(n,plan.source_german_speech)
            background=raw*(1-swap[:,None])+residual*swap[:,None]
        else: background=raw.copy()
        speech=np.zeros_like(background)
        caption_words=[]
        for seg in plan.voice_segments:
            tts=tts_path(folder,seg)
            if not tts.is_file():
                raise ValueError(f'NEEDS_TTS: missing English TTS {tts}')
            wav=decode(tts,tmp)
            start=round(seg.start*SR)
            if start+len(wav)>n or (len(wav)/SR)>(seg.end-seg.start+.03):
                raise ValueError(f'NEEDS_DUB_SYNC: English TTS {seg.id} exceeds planned timing')
            # Use the actual TTS timestamps, never raw German transcript timings.
            ap=tts.with_suffix('.alignment.json')
            caption_words.extend(_alignment_words(ap,seg.text_en,seg.start,len(wav)/SR))
            speech[start:start+len(wav)] += wav*(10**(plan.settings.voice_gain_db/20))
            if seg.kind == 'commentary':
                a=max(0,start-round(.06*SR)); b=min(n,start+len(wav)+round(.12*SR))
                background[a:b]*=10**(plan.settings.commentary_duck_db/20)
        mix=background+speech
        peak=float(np.max(np.abs(mix))) if mix.size else 0
        peak_limit=10**(plan.settings.peak_ceiling_dbfs/20)
        gain=min(1.,peak_limit/peak) if peak else 1.
        if gain<10**(-1.5/20):
            raise ValueError('NEEDS_AUDIO_REVIEW: master gain would reduce hammer ASMR too much')
        mix*=gain
        caption_words.sort(key=lambda x:x[0])
        sub,ncaptions=english_captions(caption_words)
        if caption_words[-1][1] > duration + .08:
            raise ValueError('NEEDS_CAPTIONS: English subtitle outside clip')
        # Stage outputs first: do not publish uncaptioned video or incomplete captions.
        audio_folder=folder/'audio'; audio_folder.mkdir(exist_ok=True)
        wav=audio_folder/'english_mix.wav'
        srt=folder/'captions_en.srt'
        partial=folder/'final.en.partial.mp4'
        final=folder/'final.mp4'
        sf.write(wav,mix,SR,subtype='PCM_24')
        srt.write_text(sub,encoding='utf-8')
        # Subtitle file path is relative to cwd to avoid colon/escape problems.
        # Re-encode video because a hard-burned subtitle cannot be stream-copied.
        filters="subtitles=filename='captions_en.srt':force_style='FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=0,Alignment=2,MarginV=150'"
        try:
            cmd_run(["ffmpeg","-hide_banner","-loglevel","error","-nostdin","-y",
                 "-i",str(clip),"-i",str(wav),"-map","0:v:0","-map","1:a:0",
                 "-vf",filters,"-c:v","libx264","-preset","veryfast","-crf","20",
                 "-pix_fmt","yuv420p","-c:a","aac","-b:a","192k",
                 "-movflags","+faststart","-shortest",str(partial)],cwd=folder)
            if not partial.is_file() or partial.stat().st_size<1000:
                raise ValueError('Subtitle burn-in output missing')
            partial.replace(final)
        finally: partial.unlink(missing_ok=True)
    report={'status':'RENDERED_WITH_APPROVED_AUDIO_AND_EN_SUBS',
            'clip_uid':plan.clip_uid,'german_speech_segments':len(plan.source_german_speech),
            'replacement_stem_used':bool(stem),'residual_qc_reviewer':gate.get('reviewed_by'),
            'english_voice_segments':len(plan.voice_segments),'english_caption_cues':ncaptions,
            'english_srt':'captions_en.srt','english_subtitles_burned_in':True,
            'output_video':'final.mp4','actual_audio_review_required_for_new_source':True}
    (folder/'qc_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def batch(root: Path) -> dict:
    out=[]
    for p in sorted(root.iterdir()):
        if p.is_dir() and (p/'audio_plan.json').is_file():
            try:
                out.append({'clip':p.name,'status':'PASS','result':process(p)})
            except Exception as exc:
                # Old, stale final must not masquerade as approved output on retry.
                (p/'final.mp4').unlink(missing_ok=True)
                out.append({'clip':p.name,'status':'NEEDS_REVIEW','reason':str(exc)})
    result={'clips':len(out),'passed':sum(x['status']=='PASS' for x in out),'results':out}
    (root/'strict_batch_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='mode',required=True)
    a=sub.add_parser('process');a.add_argument('--folder',required=True,type=Path);a.add_argument('--dry-run',action='store_true')
    a=sub.add_parser('batch');a.add_argument('--root',required=True,type=Path)
    args=p.parse_args()
    try: result=process(args.folder,dry_run=args.dry_run) if args.mode=='process' else batch(args.root)
    except Exception as exc:
        print(json.dumps({'status':'NEEDS_REVIEW','reason':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__': raise SystemExit(main())
