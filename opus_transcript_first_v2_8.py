"""Local Video Forge v2.8: OpusClip transcript/SRT first, Whisper only as fallback.

Adapter processes already-fetched provider data. No API keys are required for offline tests.
Timebase must be made explicit. A project transcript cannot be treated as a clip transcript.
Real API project transcript endpoint (verify live account permissions):
  GET https://api.opus.pro/api/transcripts?q=findByProjectId&projectId=PROJECT_ID

This adapter is an integration component, not an application or speech-removal model.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable
import argparse
import json
import re


class TranscriptError(ValueError):
    pass


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str
    provenance: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MapPiece:
    """Source-to-output mapping for one contiguous clip piece. Seconds.

    Reverse ordering and splits are valid via independent pieces.
    This mapping must come from verified clip editing data, not guessed range offsets.
    """
    source_in: float
    source_out: float
    clip_in: float
    clip_out: float

    def __post_init__(self) -> None:
        if self.source_in < 0 or self.clip_in < 0 or self.source_out <= self.source_in or self.clip_out <= self.clip_in:
            raise TranscriptError("invalid verified map piece")

    def project(self, t: float) -> float:
        scale = (self.clip_out - self.clip_in) / (self.source_out - self.source_in)
        return self.clip_in + (t - self.source_in) * scale


def _timestamp(value: str) -> float:
    val = value.replace('.', ',').strip()
    m = re.fullmatch(r"(?:(\d+):)?(\d{2}):(\d{2}),([0-9]{1,3})", val)
    if not m:
        raise TranscriptError(f"unsupported SRT time: {value}")
    h, minute, sec, ms = m.groups()
    if int(minute) >= 60 or int(sec) >= 60:
        raise TranscriptError("invalid SRT clock")
    return int(h or 0) * 3600 + int(minute) * 60 + int(sec) + int(ms.ljust(3, '0')) / 1000


def parse_srt(content: str) -> list[Segment]:
    content = content.replace('\ufeff', '').replace('\r\n', '\n').replace('\r', '\n').strip()
    result: list[Segment] = []
    if not content:
        return []
    for block in re.split(r"\n\s*\n", content):
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        if lines and lines[0].isdigit():
            lines = lines[1:]
        if len(lines) < 2 or '-->' not in lines[0]:
            raise TranscriptError('SRT block without clock/text')
        interval = lines.pop(0).split('-->')
        left = _timestamp(interval[0])
        # SRT can attach position attributes to the right side
        right = _timestamp(interval[1].strip().split()[0])
        text = ' '.join(re.sub(r'<[^>]*>', '', l) for l in lines).strip()
        if not text or left >= right:
            raise TranscriptError('invalid SRT subtitle')
        result.append(Segment(left, right, text, 'opus_clip_srt'))
    return result


def _fmt(t: float) -> str:
    ms = int(round(t * 1000))
    h, r = divmod(ms, 3600000)
    m, r = divmod(r, 60000)
    s, msec = divmod(r, 1000)
    return f"{h:02}:{m:02}:{s:02},{msec:03}"


def to_srt(segments: list[Segment]) -> str:
    return ''.join(f"{i}\n{_fmt(seg.start)} --> {_fmt(seg.end)}\n{seg.text}\n\n" for i, seg in enumerate(segments, 1))


def validate(segments: list[Segment], duration: float, *, allow_overlap: bool = False) -> None:
    if duration <= 0:
        raise TranscriptError('clip duration must be positive')
    last = 0.0
    for s in sorted(segments, key=lambda x: x.start):
        if not (0 <= s.start < s.end <= duration + 0.15):
            raise TranscriptError(f'timestamp outside clip duration: {s}')
        if not allow_overlap and s.start < last - 0.02:
            raise TranscriptError('conflicting/overlapping subtitles')
        last = max(last, s.end)
        if not s.text.strip():
            raise TranscriptError('blank speech text')


def from_timed_clip_json(value: Any) -> list[Segment]:
    """Parse a clip-local list of timed transcript records.

    Must ONLY be called if the provider explicitly declares the timebase is clip-local.
    Un-timed clip transcript *text* does not qualify and must not bypass ASR.
    """
    if isinstance(value, dict):
        value = value.get('segments') or value.get('paragraphs')
    if not isinstance(value, list):
        raise TranscriptError('clip transcript has no timed segments')
    result = []
    for x in value:
        if not isinstance(x, dict) or 'start' not in x or 'end' not in x:
            raise TranscriptError('clip transcript missing timing')
        result.append(Segment(float(x['start']), float(x['end']), str(x.get('text', '')).strip(), 'opus_clip_timed_json'))
    return result


def from_opus_project_api(payload: dict[str, Any]) -> list[Segment]:
    """Normalize *source* transcripts from REST (seconds) or CLI (milliseconds).

    REST GET /api/transcripts returns {data:[[paragraphs]]} with start/end seconds.
    Official CLI 'project transcript' uses {paragraphs:[...]} with *_ms fields.
    Neither timebase is clip-relative.
    """
    data = payload.get('data')
    if isinstance(data, list):
        paragraphs = data[0] if data else None
    else:
        paragraphs = payload.get('paragraphs')
    if paragraphs is None:
        return []
    if not isinstance(paragraphs, list):
        raise TranscriptError('unexpected Opus project transcript payload')
    result: list[Segment] = []
    for p in paragraphs:
        words = p.get('words') or []
        entries = words if words else ([p] if p.get('text') else [])
        for x in entries:
            txt = str(x.get('word', x.get('text', ''))).strip()
            if not txt:
                continue
            if 'start_ms' in x and 'end_ms' in x:
                start, end = float(x['start_ms']) / 1000, float(x['end_ms']) / 1000
            elif 'start' in x and 'end' in x:
                start, end = float(x['start']), float(x['end'])
            else:
                raise TranscriptError('missing time unit / timestamp on Opus source transcript')
            if start < 0 or end <= start:
                raise TranscriptError('bad source transcript timing')
            result.append(Segment(start, end, txt,
                                  'opus_source_word' if words else 'opus_source_paragraph'))
    return result


def map_project_to_clip(source: list[Segment], pieces: list[MapPiece], duration: float) -> list[Segment]:
    if not pieces:
        raise TranscriptError('verified source-to-clip edit mapping required')
    output: list[Segment] = []
    for piece in pieces:
        for seg in source:
            left = max(seg.start, piece.source_in)
            right = min(seg.end, piece.source_out)
            if right <= left:
                continue
            # Text cut across a source boundary can be incomplete. Clip/local ASR is
            # required for partially cut words or paragraphs, instead of guessing.
            if left - seg.start > .03 or seg.end - right > .03:
                raise TranscriptError('a word/paragraph crosses a cut boundary: needs alignment or local ASR')
            output.append(Segment(piece.project(left), piece.project(right), seg.text, 'opus_project_verified_map'))
    output.sort(key=lambda s: s.start)
    validate(output, duration)
    return output


def choose_transcript(*, duration: float, clip_srt: str | None = None,
                      clip_timed: Any = None,
                      project_transcript: dict[str, Any] | None = None,
                      verified_edit_map: list[MapPiece] | None = None,
                      whisper_fallback: Callable[[], list[Segment]] | None = None) -> tuple[list[Segment], dict[str, Any]]:
    """Return (segments, report); fallback once if all Opus options fail.

    A transcript with unknown language or dubious word accuracy still needs a separate
    language/accuracy QC gate. Timestamp validation alone does not prove ASR accuracy.
    """
    errors = []
    if clip_srt is not None:
        try:
            segs = parse_srt(clip_srt)
            if not segs:
                raise TranscriptError('empty clip SRT')
            validate(segs, duration)
            return segs, {'source': 'opus_clip_srt', 'whisper_used': False, 'issues': []}
        except (TranscriptError, TypeError, KeyError, ValueError) as exc:
            errors.append(f'clip_srt: {exc}')
    if clip_timed is not None:
        try:
            segs = from_timed_clip_json(clip_timed)
            if not segs:
                raise TranscriptError('empty clip transcript')
            validate(segs, duration)
            return segs, {'source': 'opus_clip_timed_json', 'whisper_used': False, 'issues': errors}
        except (TranscriptError, TypeError, KeyError, ValueError) as exc:
            errors.append(f'clip_timed: {exc}')
    if project_transcript is not None and verified_edit_map:
        try:
            segs = map_project_to_clip(from_opus_project_api(project_transcript), verified_edit_map, duration)
            if not segs:
                raise TranscriptError('project map has no speech segments')
            return segs, {'source': 'opus_project_verified_map', 'whisper_used': False, 'issues': errors}
        except (TranscriptError, TypeError, KeyError, ValueError) as exc:
            errors.append(f'project_transcript: {exc}')
    if whisper_fallback:
        segs = whisper_fallback()
        validate(segs, duration)
        return segs, {'source': 'local_whisper_fallback', 'whisper_used': True,
                      'issues': errors, 'empty_transcript_requires_vad_or_listen_qc': not bool(segs)}
    raise TranscriptError('no clip-timed transcript and no Whisper fallback; ' + '; '.join(errors))


def run_local_faster_whisper(mp4: str, language: str = 'de', model_size: str = 'medium') -> list[Segment]:
    """Optional fallback; install faster-whisper separately.

    If there is non-German speech the caller must re-check language rather than forcing
    translation as German. Stable word timestamps require extra alignment if needed.
    """
    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device='auto', compute_type='auto')
    segs, _ = model.transcribe(mp4, language=language, vad_filter=True, word_timestamps=True)
    result = []
    for seg in segs:
        if seg.words:
            result.extend(Segment(float(w.start), float(w.end), w.word.strip(), 'local_whisper')
                          for w in seg.words if w.word and w.start is not None and w.end is not None)
        elif seg.text and seg.start < seg.end:
            result.append(Segment(float(seg.start), float(seg.end), seg.text.strip(), 'local_whisper'))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--clip', required=True, help='local MP4 required only for fallback')
    parser.add_argument('--duration', required=True, type=float, help='measured clip duration from ffprobe')
    parser.add_argument('--srt', help='optional Opus clip SRT path')
    parser.add_argument('--timed-json', help='optional clip-relative JSON transcript path')
    parser.add_argument('--out', required=True, help='output directory per clip')
    args = parser.parse_args()
    srt = Path(args.srt).read_text('utf-8') if args.srt else None
    timed = json.loads(Path(args.timed_json).read_text('utf-8')) if args.timed_json else None
    segs, report = choose_transcript(
        duration=args.duration, clip_srt=srt, clip_timed=timed,
        whisper_fallback=lambda: run_local_faster_whisper(args.clip))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'transcript_de.json').write_text(json.dumps([s.to_dict() for s in segs], ensure_ascii=False, indent=2), 'utf-8')
    (out / 'transcript_de.srt').write_text(to_srt(segs), 'utf-8')
    (out / 'transcript_qc.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
