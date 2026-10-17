import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from storytelling_contracts_v33 import StorytellingPlan
from storytelling_render_v33 import tts_path

def norm(st: str) -> str:
    st = re.sub(r'[\u2014\u2013]', '--', st)
    st = re.sub(r'[\u2018\u2019]', "'", st)
    st = re.sub(r'[\u201c\u201d]', '"', st)
    st = re.sub(r'[\u2026]', '...', st)
    return re.sub(r'\s+', ' ', st).strip().casefold()

for clip_id in ['clip_007', 'clip_012', 'clip_014', 'clip_015', 'clip_016']:
    folder = Path(f'data/sources/src_aiUbN2Sne84_1792227455/output/{clip_id}_craft')
    plan_path = folder / 'story_plan.json'
    if not plan_path.is_file():
        print(f'{clip_id}: no plan')
        continue
    plan = StorytellingPlan.model_validate_json(plan_path.read_text('utf-8'))
    passes = 0
    total = len(plan.narration_segments)
    for s in plan.narration_segments:
        tp = tts_path(folder, s)
        ap = tp.with_suffix('.alignment.json')
        if not ap.is_file():
            continue
        data = json.loads(ap.read_text('utf-8'))
        align = data.get('normalized_alignment') or data.get('alignment') or data
        spoken = ''.join(align.get('characters', []))
        if norm(spoken) == norm(s.text_en):
            passes += 1
        else:
            print(f'  {clip_id} {s.id} mismatch:')
            print(f'    spoken:   {repr(norm(spoken))}')
            print(f'    expected: {repr(norm(s.text_en))}')
    print(f'{clip_id}: {passes}/{total} match')
