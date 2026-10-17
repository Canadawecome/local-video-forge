import json, os, urllib.request, math
from pathlib import Path
from dotenv import load_dotenv
load_dotenv('.env')

base_url = os.environ.get('OPENAI_BASE_URL', '').rstrip('/')
token = os.environ.get('OPENAI_API_KEY')
chat_url = f'{base_url}/chat/completions'

payload = {
    'model': 'gpt-5.6-sol',
    'messages': [
        {'role': 'system', 'content': 'You are a concise scriptwriter. Directly output the requested JSON without long reasoning.'},
        {'role': 'user', 'content': 'Generate a 8-segment JSON story for a 71s Damascus axe clip:\n{"segments": [{"id": "story_001", "text_en": "A glowing Damascus billet sits on the lower die as the forging press begins its first compression.", "evidence_refs": ["frame_0000"]}]}'}
    ],
    'max_tokens': 4000
}

req = urllib.request.Request(chat_url, method='POST',
    data=json.dumps(payload).encode('utf-8'),
    headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})

with urllib.request.urlopen(req) as r:
    resp = json.loads(r.read().decode('utf-8'))
    msg = resp['choices'][0]['message']
    print('content:', msg.get('content'))
    print('reasoning_content length:', len(msg.get('reasoning_content', '')))
