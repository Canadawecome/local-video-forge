#!/usr/bin/env python3
"""Import all OpusClip MP4 exports into independent per-clip folders.

This utility does NOT call OpusClip. It performs a deterministic local fan-out
from already-downloaded, legitimately usable clips. Subsequent AI/TTS steps are
provided by separate adapters/orchestrator described in SPEC.
"""
import argparse, hashlib, json, os, shutil, sys
from pathlib import Path
from datetime import datetime, timezone


def digest(p:Path)->str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for piece in iter(lambda:f.read(1024*1024),b''):
            h.update(piece)
    return h.hexdigest()


def ingest(clips_dir:Path, root:Path, source_url:str|None=None, allowed=False)->dict:
    if not allowed:
        raise ValueError('Provide --rights-reviewed only after verifying rights for these assets')
    clips_dir=clips_dir.resolve(); root=root.resolve()
    if not clips_dir.is_dir(): raise FileNotFoundError(clips_dir)
    videos=sorted(p for p in clips_dir.iterdir() if p.is_file() and p.suffix.lower()=='.mp4')
    if not videos: raise ValueError('No OpusClip MP4 exports were found')
    root.mkdir(parents=True,exist_ok=True)
    rows=[]; seen=set()
    for p in videos:
        d=digest(p)
        if d in seen:
            rows.append({'source_file':p.name,'status':'DUPLICATE_SKIPPED','sha256':d})
            continue
        seen.add(d)
        dest=root/f'clip_{len(seen):03d}_{d[:8]}'
        dest.mkdir(exist_ok=True)
        output=dest/'clip.mp4'
        if not output.exists(): shutil.copy2(p,output)
        elif digest(output)!=d: raise ValueError(f'Nonmatching clip exists at {output}')
        for child in ['audio/tts','analysis','scripts','publication','logs']:
            (dest/child).mkdir(parents=True,exist_ok=True)
        meta={'clip_uid':dest.name,'opus_export_name':p.name,'clip_sha256':d,
              'source_youtube_url':source_url,'rights_reviewed_at':datetime.now(timezone.utc).isoformat(),
              'status':'IMPORTED_NEEDS_INSPECTION','next_steps':["detect and confirm source language and country evidence (or UNKNOWN); confirm speech status","build source fact_sheet","approve source-speech-free workshop bed","write unique English story","generate aligned ElevenLabs voice","render and QC","write description and hashtags"]}
        (dest/'import_manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
        rows.append({'source_file':p.name,'clip_uid':dest.name,'status':meta['status'],'sha256':d})
    summary={'source_youtube_url':source_url,'unique_clip_count':sum(r['status']=='IMPORTED_NEEDS_INSPECTION' for r in rows),'items':rows}
    (root/'import_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--clips-dir',required=True,type=Path)
    ap.add_argument('--output-root',required=True,type=Path)
    ap.add_argument('--source-youtube-url')
    ap.add_argument('--rights-reviewed',action='store_true')
    args=ap.parse_args()
    try: print(json.dumps(ingest(args.clips_dir,args.output_root,args.source_youtube_url,args.rights_reviewed),ensure_ascii=False,indent=2))
    except Exception as e: print(str(e),file=sys.stderr);return 2
    return 0
if __name__=='__main__':
    # v3.5 package: deprecated importer CLI forwards to duration-gated importer.
    from ingest_opus_batch_v35 import main as _v35_main
    _v35_main()
