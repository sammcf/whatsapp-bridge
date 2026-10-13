#!/usr/bin/env python3
"""Local administrative helpers. Does not print credentials or chat contents."""
import json
import runpy
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ENV = dict(line.split('=', 1) for line in (ROOT / 'private/waha.env').read_text().splitlines())

def api(path, body=None, agent=False):
    key = (ROOT / 'private/agent-key').read_text().strip() if agent else ENV['WAHA_API_KEY']
    headers = {'X-Api-Key': key, 'Content-Type': 'application/json'}
    req = Request('http://127.0.0.1:3030' + path, headers=headers,
                  data=json.dumps(body).encode() if body is not None else None)
    with urlopen(req, timeout=60) as r:
        return json.load(r)

command = sys.argv[1] if len(sys.argv) > 1 else 'status'
if command == 'status':
    print('WhatsApp session:', api('/api/sessions/default')['status'])
elif command == 'pair':
    status = api('/api/sessions/default')['status']
    if status == 'WORKING':
        print('Already paired.')
        sys.exit(0)
    if status == 'FAILED':
        api('/api/sessions/default/stop', {})
        status = 'STOPPED'
    if status == 'STOPPED':
        api('/api/sessions/default/start', {})
    runpy.run_path(str(ROOT / 'scripts/pair.py'), run_name='__main__')
elif command == 'check-chats':
    status = api('/api/sessions/default', agent=True)['status']
    if status != 'WORKING':
        sys.exit('WhatsApp is not paired yet: ' + status)
    chats = api('/api/default/chats?limit=5&offset=0', agent=True)
    if not isinstance(chats, list):
        sys.exit('Unexpected chat response shape')
    print('Chat read succeeded; returned', len(chats), 'chats (limit 5). Contents not printed.')
else:
    sys.exit('Usage: admin.py [status|pair|check-chats]')
