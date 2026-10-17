import json, os, urllib.request, math
from pathlib import Path
from dotenv import load_dotenv
load_dotenv('.env')

base_url = os.environ.get('OPENAI_BASE_URL', '').rstrip('/')
token = os.environ.get('OPENAI_API_KEY')
chat_url = f'{base_url}/chat/completions'

duration = 71.27
count = 8
first = 0.8
last_end = duration - 2.0
window = last_end - first
slot_len = .755 * duration / count
gap = (window - count * slot_len) / (count - 1)
slots = []
for i in range(count):
    a = first + i * (slot_len + gap)
    slots.append({'id': f'story_{i+1:03d}', 'start': round(a, 3), 'end': round(a + slot_len, 3), 'role': 'hook' if i==0 else 'payoff' if i==count-1 else 'process'})

cfg = {
    'actual_clip_duration_sec': duration,
    'slots': slots,
    'source_context': {
        'topic_en': 'Forging a Damascus axe with 253 layers',
        'verified_facts': [{'claim_en': 'Billet is heated and compressed under forging dies', 'evidence_refs': ['frame_0000']}]
    },
    'observed_actions': [
        '0.5s: Heating rectangular steel billet in forge fire',
        '2.5-6.5s: Positioning billet under flat forging dies with tongs',
        '8.5-22.5s: Feeding and squeezing billet, hot forge scale flakes off',
        '26.5-28.5s: Brushing and scraping glowing billet over anvil to clear scale'
    ],
    'min_total_words': math.ceil(duration * 1.52),
    'target_total_words': math.ceil(duration * 1.85),
    'all_frame_ids': ['frame_0000']
}

instruction = '''You are writing an original natural American-English documentary voiceover for this actual licensed metalworking clip.
Return STRICT JSON only: {"segments":[{"id":"story_001","text_en":"...","evidence_refs":["frame_0000"]},...]}; do NOT return country metadata, timestamps or approval flags.
MUST return ONE segment per provided slot, preserving the exact slot IDs and ORDER; the Python system controls all time windows.
At least 7 segments, an opening hook, factual process narration, and a payoff toward the end. Total words MUST meet min_total_words, target roughly target_total_words; balanced across all slots.
Each segment should have ~13-20 spoken words, natural punctuation and no filler or repeated generic sentences.
English narration will be spoken by ElevenLabs: do not write a single short sentence for the whole >65s video.
Each sentence references real visuals or verified facts. evidence_refs must use IDs from observed_frames or verified_facts evidence, no invention.
Original source speech is factual evidence only, NOT speech to be dubbed. No fabricated material grade, origin, identity, provenance, actions or outcome.
If country unknown do not name any country. Leave naturally spaced workshop ASMR pauses between slots.
'''

payload = {
    'model': 'gpt-5.6-sol',
    'messages': [
        {'role': 'system', 'content': 'You are a master craftsman scriptwriter. Output valid JSON only.'},
        {'role': 'user', 'content': instruction + '\n\n' + json.dumps(cfg)}
    ],
    'max_tokens': 4000
}

req = urllib.request.Request(chat_url, method='POST',
    data=json.dumps(payload).encode('utf-8'),
    headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})

with urllib.request.urlopen(req) as r:
    resp = json.loads(r.read().decode('utf-8'))
    msg = resp['choices'][0]['message']
    txt = msg.get('content') or msg.get('reasoning_content') or ''
    print('Raw response length:', len(txt))
    # parse json
    import re
    if txt.startswith('```'):
        txt = re.sub(r'^```(?:json)?\s*|\s*```$', '', txt, flags=re.I).strip()
    data = json.loads(txt)
    print('Segments returned:', len(data.get('segments', [])))
    for s in data.get('segments', []):
        print(f"- {s['id']}: ({len(s['text_en'].split())} words) {s['text_en']}")
