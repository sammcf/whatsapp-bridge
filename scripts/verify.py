#!/usr/bin/env python3
"""Exercise positive and negative authentication checks without sending messages."""
import json
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:3031'
KEY = (ROOT / 'private/agent-key').read_text().strip()

def request(path, body=None, key=None, bearer=False):
    headers = {'Accept': 'application/json, text/event-stream'}
    if key:
        headers['Authorization' if bearer else 'X-Api-Key'] = ('Bearer ' if bearer else '') + key
    if body is not None:
        headers['Content-Type'] = 'application/json'
    req = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        with urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except HTTPError as e:
        return e.code, e.read().decode()

def rpc(method, params=None):
    return {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}

def decode(body):
    if body.startswith('event:'):
        return json.loads(next(line[6:] for line in body.splitlines() if line.startswith('data: ')))
    return json.loads(body)

def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print('PASS', label)

init = rpc('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'bridge-check', 'version': '1'}})
check('missing key rejected', request('/mcp', init)[0] == 401)
check('invalid key rejected', request('/mcp', init, 'deliberately-invalid-key')[0] == 401)
for bearer in (False, True):
    status, body = request('/mcp', init, KEY, bearer)
    check('MCP initialization with ' + ('Bearer' if bearer else 'X-Api-Key'), status == 200 and 'serverInfo' in decode(body).get('result', {}))
status, body = request('/mcp', rpc('tools/list'), KEY)
tools = decode(body).get('result', {}).get('tools', [])
check('chat reading tools available', status == 200 and any(t['name'] == 'chats-get-messages' for t in tools))
status, body = request('/mcp', rpc('tools/call', {'name': 'sessions-get', 'arguments': {'session': 'default'}}), KEY)
inner = json.loads(decode(body)['result']['content'][0]['text'])
check('session read allowed', status == 200 and inner['status'] == 200)
state = json.loads(inner['response'])['status']
print('WhatsApp session:', state)
# No real session or recipient is ever used for this mutating-tool rejection check.
status, body = request('/mcp', rpc('tools/call', {'name': 'sessions-stop', 'arguments': {'session': 'permission-test-nonexistent'}}), KEY)
inner = json.loads(decode(body)['result']['content'][0]['text'])
check('out-of-scope MCP call forbidden', inner['status'] == 403)
for path in ('/', '/dashboard', '/api/sessions', '/api/apps', '/api/server/version'):
    check('admin route hidden: ' + path, request(path, key=KEY)[0] == 404)
check('media requires authentication', request('/api/files/default/nonexistent')[0] == 401)
print('All endpoint checks passed; no messages sent.')
