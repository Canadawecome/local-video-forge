import json, os, urllib.request
from dotenv import load_dotenv
load_dotenv('.env')

base_url = os.environ.get('OPENAI_BASE_URL', '').rstrip('/')
token = os.environ.get('OPENAI_API_KEY')
chat_url = f'{base_url}/chat/completions'

payload = {
    'model': 'gpt-5.6-sol',
    'messages': [{'role': 'user', 'content': 'Say hi in JSON format: {"msg": "hi"}'}],
    'max_tokens': 100
}
req = urllib.request.Request(chat_url, method='POST',
    data=json.dumps(payload).encode('utf-8'),
    headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
with urllib.request.urlopen(req) as r:
    resp = json.loads(r.read().decode('utf-8'))
    print('Response:', resp)
