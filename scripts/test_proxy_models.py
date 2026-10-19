import urllib.request
import json
import re

req = urllib.request.Request('http://localhost:20128/v1/models', headers={'Authorization': 'Bearer sk-acbc7bc93e0c15d5-6d5b8d-4037db8f'})
models = json.loads(urllib.request.urlopen(req).read())['data']
print(f"Total models available: {len(models)}")
for m in models:
    mid = m['id']
    data = json.dumps({'model': mid, 'messages': [{'role': 'user', 'content': 'hi'}], 'max_tokens': 5}).encode()
    r = urllib.request.Request('http://localhost:20128/v1/chat/completions', data=data, headers={'Authorization': 'Bearer sk-acbc7bc93e0c15d5-6d5b8d-4037db8f', 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(r, timeout=10) as res:
            content = json.loads(res.read())['choices'][0]['message']['content']
            print(f"[OK] {mid}: {content.strip()[:30]}")
    except urllib.error.HTTPError as e:
        err = e.read().decode('utf-8', errors='replace')
        m_res = re.search(r'reset after [^"}]+', err)
        if m_res:
            print(f"[LIMIT] {mid}: {m_res.group(0)}")
        else:
            print(f"[ERR {e.code}] {mid}: {err[:60]}")
    except Exception as e:
        print(f"[EXC] {mid}: {e}")
