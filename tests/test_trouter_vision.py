import json, os, urllib.request, base64
from pathlib import Path
from dotenv import load_dotenv
load_dotenv('.env')

base_url = os.environ.get('OPENAI_BASE_URL', '').rstrip('/')
token = os.environ.get('OPENAI_API_KEY')
chat_url = f'{base_url}/chat/completions'

folder = Path('data/sources/src_aiUbN2Sne84_1792227455/output/clip_001_craft').resolve()
ev = folder / 'clip_evidence' / 'evidence_manifest.json'
ev_data = json.loads(ev.read_text())
frames = ev_data['frames'][:3]

content = [{'type': 'text', 'text': 'Describe what you see in JSON format: {"summary": "..."}'}]
for frame in frames:
    f = folder / 'clip_evidence' / frame['path']
    data = base64.b64encode(f.read_bytes()).decode('ascii')
    content.append({'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + data, 'detail': 'low'}})

payload = {
    'model': 'gpt-5.6-sol',
    'messages': [
        {'role': 'system', 'content': 'You are an AI assistant. Output JSON only.'},
        {'role': 'user', 'content': content}
    ],
    'response_format': {'type': 'json_object'},
    'max_tokens': 500
}
req = urllib.request.Request(chat_url, method='POST',
    data=json.dumps(payload).encode('utf-8'),
    headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req) as r:
        resp = json.loads(r.read().decode('utf-8'))
        msg = resp['choices'][0]['message']
        print('content:', msg.get('content'))
        print('reasoning_content length:', len(msg.get('reasoning_content', '')))
except Exception as e:
    print('Error:', e)
