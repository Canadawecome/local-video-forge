from pathlib import Path
import subprocess, json

base = Path('data/sources/src_aiUbN2Sne84_1792227455/output')
for d in sorted(base.glob('clip_*_craft')):
    mp4 = d / 'clip.mp4'
    if not mp4.is_file():
        mp4 = d / 'original_opus.mp4'
    if not mp4.is_file():
        clip_id = d.name.replace('_craft', '')
        cand = Path('data/sources/src_aiUbN2Sne84_1792227455/opus/opus_exports') / clip_id / f'{clip_id}.mp4'
        if cand.is_file():
            mp4 = cand
    dur = 0.0
    if mp4.is_file():
        res = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(mp4)], capture_output=True, text=True)
        dur = float(json.loads(res.stdout)['format']['duration'])
    print(f"{d.name}: file={mp4.name if mp4.is_file() else 'MISSING'}, duration={dur:.2f}s, eligible={dur > 65.0}")
