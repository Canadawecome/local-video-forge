#!/usr/bin/env python3
"""Local Video Forge v3.1 — ENGLISH_STORYTELLING_WITH_CLEAN_ASMR + speech-free workshop bed.

This is an offline *render integration module*, not an OpusClip/SAM/ElevenLabs client.
German dialogue is removed from the entire workshop track BEFORE independent
English storytelling is mixed. NO source-language-to-TTS time alignment.
It refuses to render without timed EN TTS alignment; exports EN SRT/ASS
and burns ASS into the video. No source-workshop ducking under English voice. QC flags require independent listening confirmation.

Per-clip folder:
  clip.mp4; story_plan.json (v3.1 StorytellingPlan)
  audio/workshop_clean.wav; audio/replacement_qc.json
  audio/tts/{name}.wav and audio/tts/{name}.alignment.json
  or audio_path in narration_segments and corresponding .alignment.json
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
from storytelling_contracts_v31 import StorytellingPlan

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
        items.append({'segment_id': seg.id,'role':seg.role,
                      'workshop_bed_rms_dbfs':round(bed_db,2),
                      'english_voice_rms_dbfs':round(vo_db,2),
                      'protected_asmr_overlap':overlaps})
    return items



def _transient_level_db(x: np.ndarray, a: int, b: int, *, win_ms: float=15.0) -> tuple[float, float]:
    """High-frequency onset proxy: peak short-time energy of differentiated audio.

    This is a *screening heuristic*, not a source separator or an ASMR perceptual
    model. A suspicious drop requests human review, never fabricates lost sound.
    """
    x=x[a:b].astype(np.float64)
    if len(x) < 128:
        return -120., 0.
    mono=x.mean(axis=1) if x.ndim==2 else x
    high=np.diff(mono, prepend=mono[:1])
    window=max(128,round(SR*win_ms/1000))
    if len(high)<window:
        return rms_db(high), 0.
    n=(len(high)//window)*window
    level=np.sqrt(np.mean(high[:n].reshape(-1,window)**2,axis=1))
    peak=20*np.log10(max(1e-12,float(np.max(level))))
    median=20*np.log10(max(1e-12,float(np.median(level))))
    return peak, peak-median


def check_transient_retention(raw: np.ndarray, bed: np.ndarray, protected_asmr: list,
                              *, allowed_peak_drop_db: float=-9.0) -> list[dict]:
    """Flag high-energy forge impacts that disappear after speech separation.

    Should supplement—not replace—listening and voice-leakage checks. It is
    intentionally only applied to editor-marked ASMR windows.
    """
    findings=[]
    for mark in protected_asmr:
        if mark.kind not in ('hammer','grinding','machine','saw','other'):
            continue
        a=max(0,round(mark.start*SR));b=min(len(raw),len(bed),round(mark.end*SR))
        if b-a<round(.08*SR):
            continue
        peak_src, contrast_src=_transient_level_db(raw,a,b)
        peak_bed, contrast_bed=_transient_level_db(bed,a,b)
        drop=peak_bed-peak_src
        findings.append({'kind':mark.kind,'start':mark.start,'end':mark.end,
                         'source_transient_peak_dbfs':round(peak_src,2),
                         'workshop_transient_peak_dbfs':round(peak_bed,2),
                         'source_onset_contrast_db':round(contrast_src,2),
                         'workshop_onset_contrast_db':round(contrast_bed,2),
                         'transient_peak_change_db':round(drop,2)})
        # Real hits stand out from the local noise floor; don't flag the
        # absence of a transient on intentionally quiet source audio.
        if peak_src>-53 and contrast_src>=5 and drop<allowed_peak_drop_db:
            raise ValueError(
                f'NEEDS_ASMR_REVIEW: {mark.kind} transient at '
                f'{mark.start:.2f}-{mark.end:.2f}s dropped {abs(drop):.1f} dB; '
                'separator likely removed metal impact together with speech')
    return findings


def check_asmr_retention(raw: np.ndarray, bed: np.ndarray, protected_asmr: list,
                         *, min_retention_db: float = -8.0) -> list[dict]:
    """Detect obvious ASMR loss after speech separation. Conservative heuristic.

    Audio with German dialogue naturally raises source RMS, so this is a
    signal-loss alarm, NOT proof of perfect isolation. Human listening still
    required for overlapping voice/hammer sounds.
    """
    findings=[]
    for mark in protected_asmr:
        a=max(0,round(mark.start*SR)); b=min(len(raw),round(mark.end*SR))
        if b-a < round(.06*SR):
            continue
        original=rms_db(raw[a:b]); retained=rms_db(bed[a:b]); drop=retained-original
        finding={'kind':mark.kind,'start':mark.start,'end':mark.end,
                 'source_rms_dbfs':round(original,2),
                 'workshop_rms_dbfs':round(retained,2),
                 'change_db':round(drop,2)}
        findings.append(finding)
        if original > -52 and drop < min_retention_db:
            raise ValueError(
                f'NEEDS_ASMR_REVIEW: {mark.kind} at {mark.start:.2f}-{mark.end:.2f}s '
                f'lost {abs(drop):.1f} dB in workshop stem; do not publish a silent hammer')
    return findings


def _escape_ass(s: str) -> str:
    return s.replace("\\", r"\\").replace("{", "(").replace("}", ")").replace("\n", r"\N")


def ass_time(t: float) -> str:
    cs = max(0, round(t*100))
    hh,cs=divmod(cs,360000); mm,cs=divmod(cs,6000); ss,cs=divmod(cs,100)
    return f'{hh}:{mm:02}:{ss:02}.{cs:02}'


def caption_regions(folder: Path, duration: float) -> list[dict]:
    """Optional editor-specified per-shot positions, never guessed from footage.

    Example caption_regions.json:
      [{"start":0,"end":8,"anchor_pct":85},
       {"start":8,"end":18,"anchor_pct":79,"italic_terms":["blacksmith"]}]
    """
    path=folder/'caption_regions.json'
    if not path.is_file():
        return []
    regions=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(regions,list):
        raise ValueError('caption_regions.json must be a list')
    last_end=0.
    out=[]
    for r in regions:
        if not isinstance(r,dict) or set(r)-{'start','end','anchor_pct','italic_terms'}:
            raise ValueError('Invalid caption region keys')
        a,b=float(r['start']),float(r['end'])
        y=float(r.get('anchor_pct',85))
        terms=r.get('italic_terms',[])
        if not (0<=a<b<=duration+.08 and 68<=y<=90 and a>=last_end-0.001):
            raise ValueError('Caption region time/position invalid or overlaps')
        if (not isinstance(terms,list) or len(terms)>20 or
            any(not isinstance(t,str) or not 1<=len(t)<=32 for t in terms)):
            raise ValueError('Invalid caption italic_terms')
        out.append({'start':a,'end':b,'anchor_pct':y,'italic_terms':terms})
        last_end=b
    return out


def _ass_emphasis(text: str, words: list[str]) -> str:
    """Apply italic to an explicitly chosen whole word, keeping ASS escaped."""
    pieces=re.split(r'(\s+)',text)
    targets={w.casefold() for w in words}
    result=[]
    for item in pieces:
        normalized=re.sub(r'^[^\w]+|[^\w]+$','',item).casefold()
        escaped=_escape_ass(item)
        result.append((r'{\i1}'+escaped+r'{\i0}') if normalized and normalized in targets else escaped)
    return ''.join(result)


def _break_caption(text: str, char_limit: int=23) -> str:
    """Balance two short lines only when needed; never use three lines."""
    words=text.split()
    if len(text)<=char_limit or len(words)<3:
        return text
    best=None
    for i in range(1,len(words)):
        l=' '.join(words[:i]);r=' '.join(words[i:])
        if max(len(l),len(r))>char_limit:
            continue
        metric=abs(len(l)-len(r))+max(len(l),len(r))*.15
        if best is None or metric<best[0]:
            best=(metric,l,r)
    return (best[1]+r'\N'+best[2]) if best else text


def compact_ass(cues: list[tuple[float,float,str]], width: int, height: int,
                *, anchor_pct: float=85.0, font_scale: float=.050,
                regions: list[dict]|None=None) -> tuple[str, dict]:
    """Reference-style English subtitles, scale by output width (1080 -> 54px).

    Default Y=85%; optional per-shot overrides handle letterboxed/blur shots.
    All overrides are editor-specified (not inferred from a still frame).
    """
    if not (68 <= anchor_pct <= 90):
        raise ValueError('Caption position must remain within safe bounds')
    font_px = max(16,min(76,round(width*font_scale)))
    outline_px = max(1,round(font_px*.065))
    anchor_y=round(height*anchor_pct/100)
    margin_lr=round(width*.075)
    header=f"""[Script Info]
Title: LVF Reference English Captions v3.1
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Compact,Inter,{font_px},&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,{outline_px},0,2,{margin_lr},{margin_lr},0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events=[];actual_anchors=[]
    regions=regions or []
    for a,b,txt in cues:
        midpoint=(a+b)/2
        region=next((r for r in regions if r['start']<=midpoint<r['end']),None)
        cy=round(height*(region['anchor_pct'] if region else anchor_pct)/100)
        italic_terms=region.get('italic_terms',[]) if region else []
        balanced=_break_caption(txt)
        # Escape the two-line ASS separator while escaping the actual text.
        styled=r'\N'.join(_ass_emphasis(t,italic_terms) for t in balanced.split(r'\N'))
        events.append(f'Dialogue: 0,{ass_time(a)},{ass_time(b)},Compact,,0,0,0,,{{\\an2\\pos({width//2},{cy})}}{styled}')
        actual_anchors.append(round(100*cy/height,2))
    return header+'\n'.join(events)+'\n', {'font':'Inter','font_px':font_px,
        'font_pct_of_width':round(100*font_px/width,2),
        'default_anchor_y_pct':anchor_pct,'anchor_y_pct':anchor_pct,
        'anchor_y_px':anchor_y,'outline_px':outline_px,
        'anchor_positions_pct':actual_anchors,
        'adaptive_regions':len(regions),
        'max_lines':2}


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
    sig = hashlib.sha256(json.dumps([seg.text_en, seg.role],
                                    ensure_ascii=False).encode()).hexdigest()[:12]
    return folder / 'audio' / 'tts' / f'{seg.id}_{sig}.mp3'


def get_approved_background(folder: Path, plan: StorytellingPlan, clip: Path,
                            clip_duration: float) -> tuple[Path | None, dict]:
    """Require independent QC tied to source and residual hashes.

    If German speech exists, ALWAYS use the whole approved speech-free residual
    throughout the clip. No raw audio leaks between imperfect transcript regions.
    """
    qc_path = folder / 'audio' / 'replacement_qc.json'
    if not qc_path.is_file():
        raise ValueError('NEEDS_AUDIO_REVIEW: missing audio/replacement_qc.json')
    qc = json.loads(qc_path.read_text(encoding='utf-8'))
    if qc.get('source_sha256') != sha256(clip):
        raise ValueError('NEEDS_AUDIO_REVIEW: stale source approval')
    if not str(qc.get('reviewed_by', '')).strip():
        raise ValueError('NEEDS_AUDIO_REVIEW: missing QC reviewer')

    if plan.german_speech_status == 'CONFIRMED_ABSENT':
        if qc.get('source_speech_absence_confirmed') is not True:
            raise ValueError('NEEDS_AUDIO_REVIEW: speech-free status not approved')
        return None, qc

    if not plan.approved_workshop_stem_path or not plan.workshop_stem_qc_passed:
        raise ValueError('NEEDS_AUDIO_REVIEW: speech is present without approved clean residual')
    stem = resolve_asset(folder, plan.approved_workshop_stem_path)
    if not stem.is_file():
        raise ValueError(f'NEEDS_AUDIO_REVIEW: approved residual missing: {stem}')
    if abs(ffprobe_duration(stem) - clip_duration) > .10:
        raise ValueError('NEEDS_AUDIO_REVIEW: residual duration mismatch')
    if not all(qc.get(k) is True for k in ('german_voice_absent', 'asmr_preserved', 'clip_transcript_checked')):
        raise ValueError('NEEDS_AUDIO_REVIEW: residual lacks speech/ASMR approval')
    if qc.get('residual_sha256') != sha256(stem):
        raise ValueError('NEEDS_AUDIO_REVIEW: stale residual approval')
    return stem, qc



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
                         max_words: int=4, max_chars: int=28) -> list[tuple[float,float,str]]:
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
    defaults = {'subtitle_anchor_pct':85.0, 'subtitle_font_width_ratio':0.050,
                'max_words_per_caption':4,'max_characters_per_caption':28,
                'measure_mastering':True}
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
    if not .038 <= float(values['subtitle_font_width_ratio']) <= .065:
        raise ValueError('Subtitle font ratio must be 3.8%-6.5% of picture width')
    if not 1 <= int(values['max_words_per_caption']) <= 4:
        raise ValueError('Caption maximum must be 1-4 words')
    if not 15 <= int(values['max_characters_per_caption']) <= 32:
        raise ValueError('Caption character cap must be 15-32')
    if not isinstance(values['measure_mastering'],bool):
        raise ValueError('measure_mastering must be boolean')
    return values


def _measure_mastering(path: Path) -> dict:
    """FFmpeg loudnorm analysis-only; measure, never auto-normalize master."""
    p=subprocess.run(['ffmpeg','-hide_banner','-nostdin','-i',str(path),
       '-vn','-af','loudnorm=I=-16:TP=-1.0:LRA=11:print_format=json',
       '-f','null','-'],capture_output=True,text=True)
    if p.returncode:
        return {'measurement_error':p.stderr[-400:]}
    matches=re.findall(r'\{\s*"input_i"\s*:\s*"[^"\n]+".*?\}',p.stderr,flags=re.DOTALL)
    if not matches:
        return {'measurement_error':'FFmpeg loudnorm did not return stats'}
    d=json.loads(matches[-1])
    try:
        lufs=float(d['input_i']);tp=float(d['input_tp'])
        return {'integrated_lufs':lufs,'true_peak_dbtp':tp,
                'reference_integrated_lufs':-15.8,
                'reference_true_peak_dbtp':-1.23,
                'loudness_delta_from_reference':round(lufs+15.8,2),
                'warning': bool(abs(lufs+15.8)>4.0 or tp>-.5)}
    except (ValueError,KeyError) as e:
        return {'measurement_error':str(e)}


def _final_bed_qc(final_audio: np.ndarray, background: np.ndarray,
                  voice_only: np.ndarray, master_gain: float,
                  voice_segments: list,protected_asmr: list) -> list[dict]:
    """Decode MP4 AAC, subtract known voice mix, and compare residual bed.

    PCM subtraction is approximate after AAC encoding. It is a regression alarm,
    not an objective proof that speech removal or ASMR restoration is perfect.
    """
    n=min(len(final_audio),len(background),len(voice_only))
    if n < SR//2:
        raise ValueError('NEEDS_AUDIO_REVIEW: exported MP4 audio too short')
    results=[]
    for seg in voice_segments:
        a=max(0,round((seg.start+.04)*SR))
        b=min(n,round((seg.end-.04)*SR))
        if b-a<round(.08*SR): continue
        target=background[a:b]*master_gain
        extracted=final_audio[a:b]-voice_only[a:b]*master_gain
        target_db=rms_db(target);ext_db=rms_db(extracted)
        diff=ext_db-target_db
        # AAC may vary the level of an estimated signal a little, but a true
        # missing bed drops far more than this.
        if target_db>-48 and diff<-7.0:
            raise ValueError(f'NEEDS_AUDIO_REVIEW: ASMR disappeared from final MP4 under {seg.id} ({diff:.1f} dB)')
        results.append({'segment_id':seg.id,'expected_bed_rms_dbfs':round(target_db,2),
            'estimated_final_bed_rms_dbfs':round(ext_db,2),'estimated_change_db':round(diff,2),
            'aac_subtraction_approximation':True})
    return results

def process(folder: Path, *, dry_run=False) -> dict[str,Any]:
    folder=folder.resolve()
    clip=folder/'clip.mp4'
    if not dry_run:
        (folder/'final.mp4').unlink(missing_ok=True)
        (folder/'qc_report.json').unlink(missing_ok=True)
    if not clip.is_file(): raise FileNotFoundError(f'Missing clip.mp4 in {folder}')
    plan=StorytellingPlan.model_validate_json((folder/'story_plan.json').read_text(encoding='utf-8'))
    prefs=render_preferences(folder)
    duration=ffprobe_duration(clip)
    width,height=ffprobe_video_size(clip)
    plan.validate_duration(duration)
    if not plan.narration_segments: raise ValueError('NEEDS_ENGLISH_VOICE: no English narration segments')
    # English story timing is independent of the original German speech windows.
    stem,gate=get_approved_background(folder,plan,clip,duration)
    if dry_run:
        return {'status':'GATES_PASSED', 'clip_uid':plan.clip_uid,'stem':str(stem) if stem else None}
    with tempfile.TemporaryDirectory(prefix='lvf_v29_') as tmpdirname:
        tmp=Path(tmpdirname)
        raw=decode(clip,tmp)
        n=len(raw)
        if stem:
            residual = decode(stem,tmp)
            if residual.shape[1] != raw.shape[1] or abs(len(residual)-n)>round(.05*SR):
                raise ValueError('NEEDS_AUDIO_REVIEW: source/residual length mismatch')
            if len(residual)<n:
                residual=np.pad(residual,((0,n-len(residual)),(0,0)))
            # Use approved residual FULL TIME, so no German audio returns in gaps.
            background=residual[:n].copy()
        else:
            background=raw.copy()
        residual_match_db=0.0
        asmr_retention_qc=check_asmr_retention(raw,background,plan.protected_asmr)
        transient_retention_qc=check_transient_retention(raw,background,plan.protected_asmr)
        speech=np.zeros_like(background)
        caption_words=[]
        for seg in plan.narration_segments:
            tts=tts_path(folder,seg)
            if not tts.is_file():
                raise ValueError(f'NEEDS_TTS: missing English TTS {tts}')
            wav=decode(tts,tmp)
            start=round(seg.start*SR)
            if start+len(wav)>n or (len(wav)/SR)>(seg.end-seg.start+.03):
                raise ValueError(f'NEEDS_STORY_SYNC: English TTS {seg.id} exceeds planned slot')
            # Captions are synced with English TTS, not German transcript timings.
            ap=tts.with_suffix('.alignment.json')
            caption_words.extend(_alignment_words(ap,seg.text_en,seg.start,len(wav)/SR))
            # Independent English storytelling, over permanent workshop ASMR.
            # NEVER match the original German utterance timing or duck the bed.
            gain_db=plan.settings.voice_gain_db
            i1=min(n,start+len(wav))
            # No RMS-based voice-vs-bed clamping. Forge audio is dynamic:
            # quiet passages must not make narration disappear, and a hammer
            # transient must not trigger whole-track automatic ducking.
            speech[start:i1] += wav[:i1-start]*(10**(gain_db/20))
        # Keep a separately auditable ASMR track: background stays unmuted
        # under EVERY independent English storytelling segment.
        qc_asmr_bed=_voice_bed_qc(background,speech,plan.narration_segments,plan.protected_asmr)
        mix=background+speech
        peak=float(np.max(np.abs(mix))) if mix.size else 0
        peak_limit=10**(plan.settings.peak_ceiling_dbfs/20)
        gain=min(1.,peak_limit/peak) if peak else 1.
        if gain<10**(-5.0/20):
            raise ValueError('NEEDS_AUDIO_REVIEW: master gain would reduce hammer ASMR too much')
        mix*=gain
        caption_words.sort(key=lambda x:x[0])
        cues=compact_caption_cues(caption_words,max_words=int(prefs['max_words_per_caption']),
                                  max_chars=int(prefs['max_characters_per_caption']))
        sub=cues_to_srt(cues)
        regions=caption_regions(folder,duration)
        ass,caption_style=compact_ass(cues,width,height,
              regions=regions,
              anchor_pct=float(prefs['subtitle_anchor_pct']),
              font_scale=float(prefs['subtitle_font_width_ratio']))
        ncaptions=len(cues)
        if caption_words[-1][1] > duration + .08:
            raise ValueError('NEEDS_CAPTIONS: English subtitle outside clip')
        # Stage outputs first: do not publish uncaptioned video or incomplete captions.
        audio_folder=folder/'audio'; audio_folder.mkdir(exist_ok=True)
        wav=audio_folder/'english_mix.wav'
        bed=audio_folder/'workshop_bed_always_on.wav'
        voice_only=audio_folder/'english_voice_only.wav'
        srt=folder/'captions_en.srt'
        ass_path=folder/'captions_en.ass'
        partial=folder/'final.en.partial.mp4'
        final=folder/'final.mp4'
        sf.write(wav,mix,SR,subtype='PCM_24')
        sf.write(bed,background,SR,subtype='PCM_24')
        sf.write(voice_only,speech,SR,subtype='PCM_24')
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
            final_audio=decode(partial,tmp)
            final_bed_metrics=_final_bed_qc(final_audio,background,speech,gain,
                                            plan.narration_segments,plan.protected_asmr)
            mastering=_measure_mastering(partial) if prefs['measure_mastering'] else {'skipped':True}
            partial.replace(final)
        finally: partial.unlink(missing_ok=True)
    report={'status':'RENDERED_WITH_APPROVED_AUDIO_AND_EN_SUBS',
            'clip_uid':plan.clip_uid,'german_speech_segments':len(plan.source_german_speech),
            'storytelling_mode':'ENGLISH_STORYTELLING_WITH_CLEAN_ASMR',
            'source_german_speech_status':plan.german_speech_status,
            'replacement_stem_used':bool(stem),'residual_qc_reviewer':gate.get('reviewed_by'),
            'english_voice_segments':len(plan.narration_segments),'english_caption_cues':ncaptions,
            'english_srt':'captions_en.srt','english_ass':'captions_en.ass',
            'caption_style':caption_style,
            'workshop_bed_file':'audio/workshop_bed_always_on.wav',
            'workshop_bed_never_ducked_for_english_voice':True,
            'stem_gain_match_db':round(residual_match_db,2),
            'render_preferences':prefs,
            'per_voice_asmr_metrics':qc_asmr_bed,'protected_asmr_retention':asmr_retention_qc,
            'protected_asmr_transients':transient_retention_qc,
            'final_mp4_asmr_during_voice':final_bed_metrics,
            'master_gain_db':round(20*math.log10(max(gain,1e-12)),3),
            'mastering':mastering,
            'no_bed_ducking':True,
            'english_subtitles_burned_in':True,
            'output_video':'final.mp4','actual_audio_review_required_for_new_source':True}
    (folder/'qc_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def batch(root: Path) -> dict:
    out=[]
    for p in sorted(root.iterdir()):
        if p.is_dir() and (p/'story_plan.json').is_file():
            try:
                out.append({'clip':p.name,'status':'PASS','result':process(p)})
            except Exception as exc:
                # Old, stale final must not masquerade as approved output on retry.
                (p/'final.mp4').unlink(missing_ok=True)
                out.append({'clip':p.name,'status':'NEEDS_REVIEW','reason':str(exc)})
    result={'clips':len(out),'passed':sum(x['status']=='PASS' for x in out),'results':out}
    (root/'storytelling_batch_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
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
