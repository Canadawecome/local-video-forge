#!/usr/bin/env python3
"""Local Video Forge v2.10 — ASMR ALWAYS ON + compact English subtitles.

This is an offline *render integration module*, not an OpusClip/SAM/ElevenLabs client.
It refuses to render if an approved, speech-free residual is unavailable for a
clip containing German speech; no whole-track ducking fallback is allowed.
It refuses to render without timed EN TTS alignment; exports EN SRT/ASS
and burns ASS into the video. No source-workshop ducking under English voice. QC flags require independent listening confirmation.

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


def ffprobe_video_size(path: Path) -> tuple[int, int]:
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height", "-of", "json", str(path)],
                       check=True, capture_output=True, text=True)
    streams = json.loads(p.stdout).get('streams') or []
    if not streams:
        raise ValueError('Missing video stream')
    return int(streams[0]['width']), int(streams[0]['height'])


def rms_db(x: np.ndarray) -> float:
    if not x.size:
        return -120.0
    return 20 * math.log10(max(1e-12, float(np.sqrt(np.mean(x.astype(np.float64)**2)))))


def _voice_bed_qc(background: np.ndarray, speech: np.ndarray, segments: list,
                  protected_asmr: list) -> list[dict]:
    """Non-destructive measurement: no bed gain automation during voice regions.

    On protected overlapping ASMR, a silent separator output is blocked; quiet
    non-protected regions are allowed, because a forge might naturally be quiet.
    """
    items = []
    for seg in segments:
        i0, i1 = max(0,round(seg.start*SR)), min(len(background),round(seg.end*SR))
        bed_db = rms_db(background[i0:i1])
        vo_db = rms_db(speech[i0:i1])
        overlaps = [x.kind for x in protected_asmr
                    if min(x.end,seg.end)-max(x.start,seg.start) > .05]
        if overlaps and bed_db < -49:
            raise ValueError(f'NEEDS_ASMR_REVIEW: {seg.id} overlaps {overlaps} but speech-free workshop bed is near silent')
        items.append({'segment_id': seg.id,'kind':seg.kind,
                      'workshop_bed_rms_dbfs':round(bed_db,2),
                      'english_voice_rms_dbfs':round(vo_db,2),
                      'protected_asmr_overlap':overlaps})
    return items


def normalize_residual(raw: np.ndarray, residual: np.ndarray,
                       speech_intervals: list) -> tuple[np.ndarray, float]:
    """Match separation stem to original recording's gain using non-speech times.

    We never normalize a stem to the louder ORIGINAL inside a speech window,
    because original RMS includes German speech. Avoid pumping/noise boosting.
    """
    mask = np.ones(len(raw), dtype=bool)
    for seg in speech_intervals:
        a=max(0,round((seg.start-.3)*SR));b=min(len(raw),round((seg.end+.3)*SR))
        mask[a:b] = False
    if mask.sum() < SR // 4:
        return residual, 0.0
    before = rms_db(raw[mask]); after = rms_db(residual[mask])
    if before < -48 or after < -53:
        return residual, 0.0
    desired_db = max(-3.0,min(3.0,before-after))
    result = residual*(10**(desired_db/20))
    if np.max(np.abs(result)) > .99:
        raise ValueError('NEEDS_ASMR_REVIEW: residual gain matching would clip audio')
    return result, desired_db


def _escape_ass(s: str) -> str:
    return s.replace("\\", r"\\").replace("{", "(").replace("}", ")").replace("\n", r"\N")


def ass_time(t: float) -> str:
    cs = max(0, round(t*100))
    hh,cs=divmod(cs,360000); mm,cs=divmod(cs,6000); ss,cs=divmod(cs,100)
    return f'{hh}:{mm:02}:{ss:02}.{cs:02}'


def compact_ass(cues: list[tuple[float,float,str]], width: int, height: int,
                *, anchor_pct: float=85.0, font_scale: float=.036) -> tuple[str, dict]:
    """Use pixel-based ASS PlayResX/Y so 1080x1920 output gets ~39px text,
    unlike libass interpreting arbitrary SRT force_style font size scaling.
    """
    if not (64 <= anchor_pct <= 90):
        raise ValueError('Caption position must remain within upper safe-band bounds')
    font_px = max(12,min(42,round(width*font_scale)))
    outline_px = max(1,round(font_px * .075))
    anchor_y=round(height*anchor_pct/100)
    margin_lr=round(width*.10)
    header=f"""[Script Info]
Title: LVF Compact English Captions v2.10
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Compact,Inter,{font_px},&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,0,0,0,0,100,100,0,0,1,{outline_px},0,2,{margin_lr},{margin_lr},0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events=[]
    for a,b,text in cues:
        # \pos baseline defaults to 85% of picture height.
        events.append(f'Dialogue: 0,{ass_time(a)},{ass_time(b)},Compact,,0,0,0,,{{\\an2\\pos({width//2},{anchor_y})}}{_escape_ass(text)}')
    return header+'\n'.join(events)+'\n', {'font':'Inter', 'font_px':font_px,'font_pct_of_width':round(100*font_px/width,2),'anchor_y_pct':anchor_pct,'anchor_y_px':anchor_y,'outline_px':outline_px,'max_words_per_cue':'user-configurable','max_chars_per_cue':'user-configurable'}


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


def compact_caption_cues(parts: list[tuple[float,float,str]],
                         max_words: int=3, max_chars: int=25) -> list[tuple[float,float,str]]:
    if not parts:
        raise ValueError('NEEDS_CAPTIONS: no English words')
    cues=[];group=[]
    def emit():
        if group:
            text=' '.join(w[2] for w in group)
            cues.append((group[0][0], max(group[-1][1],group[0][0]+.12),text))
            group.clear()
    for word in parts:
        new_text=' '.join([w[2] for w in group]+[word[2]])
        if group and (len(group)>=max_words or len(new_text)>max_chars
                      or word[0]-group[-1][1]>.36):
            emit()
        group.append(word)
        if re.search(r'[.!?]$',word[2]) and len(group)>=2:
            emit()
    emit()
    for a,b,t in cues:
        if not 0<=a<b: raise ValueError('Broken English caption timing')
    return cues


def cues_to_srt(cues: list[tuple[float,float,str]]) -> str:
    return '\n'.join(f'{i}\n{_srt_clock(a)} --> {_srt_clock(b)}\n{t}\n' for i,(a,b,t) in enumerate(cues,1))+'\n'


def render_preferences(folder: Path) -> dict[str,float|int]:
    defaults = {'subtitle_anchor_pct':85.0, 'subtitle_font_width_ratio':0.032,
                'max_words_per_caption':3,'max_characters_per_caption':25,
                'max_voice_over_bed_db':7.0}
    path=folder/'render_preferences.json'
    if not path.is_file():
        path=folder.parent/'render_preferences.json' # shared defaults for all batch children
    if not path.is_file():
        return defaults
    override=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(override,dict) or set(override)-set(defaults):
        raise ValueError('Invalid/unknown render_preferences.json setting')
    values={**defaults, **override}
    if not 68 <= float(values['subtitle_anchor_pct']) <= 90:
        raise ValueError('Subtitle position must be 68-90% of picture height')
    if not .026 <= float(values['subtitle_font_width_ratio']) <= .042:
        raise ValueError('Subtitle font ratio must be 2.6%-4.2% of picture width')
    if not 2 <= int(values['max_words_per_caption']) <= 5:
        raise ValueError('Caption words must be 2-5')
    if not 15 <= int(values['max_characters_per_caption']) <= 32:
        raise ValueError('Caption character cap must be 15-32')
    if not 3 <= float(values['max_voice_over_bed_db']) <= 12:
        raise ValueError('Voice/ASMR difference must be 3-12 dB')
    return values


def process(folder: Path, *, dry_run=False) -> dict[str,Any]:
    folder=folder.resolve()
    clip=folder/'clip.mp4'
    if not dry_run:
        (folder/'final.mp4').unlink(missing_ok=True)
        (folder/'qc_report.json').unlink(missing_ok=True)
    if not clip.is_file(): raise FileNotFoundError(f'Missing clip.mp4 in {folder}')
    plan=HybridClipPlan.model_validate_json((folder/'audio_plan.json').read_text(encoding='utf-8'))
    prefs=render_preferences(folder)
    duration=ffprobe_duration(clip)
    width,height=ffprobe_video_size(clip)
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
            residual, residual_match_db = normalize_residual(raw,residual,plan.source_german_speech)
            swap=background_swap_envelope(n,plan.source_german_speech)
            # Persistent ASMR BED is always active. Only its speech-containing
            # *source* is substituted by approved speech-free residual.
            background=raw*(1-swap[:,None])+residual*swap[:,None]
        else:
            background=raw.copy()
            residual_match_db=0.0
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
            # English voice adds to the permanent workshop BED; never apply
            # whole-bed ducking or erase hammer/grinder under commentary.
            gain_db=plan.settings.voice_gain_db
            i1=min(n,start+len(wav))
            bed_db=rms_db(background[start:i1])
            voice_db=rms_db(wav)
            if bed_db > -43 and voice_db+gain_db > bed_db+float(prefs['max_voice_over_bed_db']):
                gain_db=bed_db+float(prefs['max_voice_over_bed_db'])-voice_db
            speech[start:i1] += wav[:i1-start]*(10**(gain_db/20))
        # Keep a separately auditable ASMR track: background stays unmuted
        # under EVERY English segment (dub and commentary).
        qc_asmr_bed=_voice_bed_qc(background,speech,plan.voice_segments,plan.protected_asmr)
        mix=background+speech
        peak=float(np.max(np.abs(mix))) if mix.size else 0
        peak_limit=10**(plan.settings.peak_ceiling_dbfs/20)
        gain=min(1.,peak_limit/peak) if peak else 1.
        if gain<10**(-1.5/20):
            raise ValueError('NEEDS_AUDIO_REVIEW: master gain would reduce hammer ASMR too much')
        mix*=gain
        caption_words.sort(key=lambda x:x[0])
        cues=compact_caption_cues(caption_words,max_words=int(prefs['max_words_per_caption']),
                                  max_chars=int(prefs['max_characters_per_caption']))
        sub=cues_to_srt(cues)
        ass,caption_style=compact_ass(cues,width,height,
              anchor_pct=float(prefs['subtitle_anchor_pct']),
              font_scale=float(prefs['subtitle_font_width_ratio']))
        ncaptions=len(cues)
        if caption_words[-1][1] > duration + .08:
            raise ValueError('NEEDS_CAPTIONS: English subtitle outside clip')
        # Stage outputs first: do not publish uncaptioned video or incomplete captions.
        audio_folder=folder/'audio'; audio_folder.mkdir(exist_ok=True)
        wav=audio_folder/'english_mix.wav'
        bed=audio_folder/'workshop_bed_always_on.wav'
        srt=folder/'captions_en.srt'
        ass_path=folder/'captions_en.ass'
        partial=folder/'final.en.partial.mp4'
        final=folder/'final.mp4'
        sf.write(wav,mix,SR,subtype='PCM_24')
        sf.write(bed,background,SR,subtype='PCM_24')
        srt.write_text(sub,encoding='utf-8')
        ass_path.write_text(ass,encoding='utf-8')
        # Subtitle file path is relative to cwd to avoid colon/escape problems.
        # Re-encode video because a hard-burned subtitle cannot be stream-copied.
        filters="ass=filename='captions_en.ass'"
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
            'english_srt':'captions_en.srt','english_ass':'captions_en.ass',
            'caption_style':caption_style,
            'workshop_bed_file':'audio/workshop_bed_always_on.wav',
            'workshop_bed_never_ducked_for_english_voice':True,
            'stem_gain_match_db':round(residual_match_db,2),
            'render_preferences':prefs,
            'per_voice_asmr_metrics':qc_asmr_bed,
            'english_subtitles_burned_in':True,
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
