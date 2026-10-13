#!/usr/bin/env python3
"""Exercise real public OAuth + PKCE and read-only MCP; never send messages.

Registers a test client on each run. Credentials are kept only in memory.
"""
import base64
import hashlib
import http.cookiejar
import json
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://fiddler.minotaur-altered.ts.net:8443'
CHATGPT = '--chatgpt' in sys.argv[1:]
CLIENT_CONFIG = json.loads((ROOT / 'private/chatgpt-oauth-client.json').read_text()) if CHATGPT else None
CALLBACK = CLIENT_CONFIG['redirect_uris'][0] if CHATGPT else 'http://127.0.0.1:49199/callback'

class Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if newurl.startswith(CALLBACK):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)

browser = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()), Redirects())

def request(url, data=None, form=False, token=None, extra_headers=None):
    if CLIENT_CONFIG and form and url.endswith('/.idp/token'):
        data = {**data, 'client_secret': CLIENT_CONFIG['client_secret']}
    headers = {'Accept': 'application/json, text/event-stream'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if data is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
        data = (urlencode(data) if form else json.dumps(data)).encode()
    headers.update(extra_headers or {})
    req = Request(url if url.startswith('http') else BASE + url, data=data, headers=headers)
    try:
        response = browser.open(req, timeout=30)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.read().decode(), response.headers, response.url

def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print('PASS', label, flush=True)

def rpc(method, params=None):
    return {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}

def decode(body):
    if body.startswith('event:'):
        body = next(line[6:] for line in body.splitlines() if line.startswith('data: '))
    return json.loads(body)

init = rpc('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'oauth-check', 'version': '1'}})
status, _, headers, _ = request('/mcp', init)
check('unauthenticated request advertises OAuth discovery', status == 401 and 'resource_metadata=' in headers.get('WWW-Authenticate', ''))
resource = json.loads(request('/.well-known/oauth-protected-resource')[1])
metadata = json.loads(request('/.well-known/oauth-authorization-server')[1])
check('PKCE S256 discovery', 'S256' in metadata['code_challenge_methods_supported'])
if CLIENT_CONFIG:
    client = CLIENT_CONFIG['client_id']
    print('Testing registered ChatGPT client; callback is intercepted locally.')
else:
    status, body, _, _ = request(metadata['registration_endpoint'], {
        'client_name': 'WhatsApp bridge verification', 'redirect_uris': [CALLBACK],
        'grant_types': ['authorization_code', 'refresh_token'], 'response_types': ['code'],
        'token_endpoint_auth_method': 'none',
    })
    check('dynamic client registration', status in (200, 201))
    client = json.loads(body)['client_id']

def authorize(test_password=False):
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    state = secrets.token_urlsafe(24)
    query = urlencode({'client_id': client, 'redirect_uri': CALLBACK, 'response_type': 'code',
                       'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256',
                       'resource': resource['resource']})
    status, body, _, url = request(metadata['authorization_endpoint'] + '?' + query)
    check('authorization page available', status == 200)
    if test_password:
        status, body, _, url = request('/.auth/login', {'password': 'deliberately-incorrect'}, form=True)
        check('incorrect password denied', 'Invalid password' in body)
        status, body, _, url = request('/.auth/login', {'password': (ROOT / 'private/oauth-password.txt').read_text().strip()}, form=True)
    check('consent required after login', '/.idp/auth/' in url and 'Authorize' in body)
    status, _, headers, _ = request(url, {}, form=True)
    result = parse_qs(urlparse(headers.get('Location', '')).query)
    check('authorization code returned with matching state', status in (302, 303) and result.get('state') == [state] and 'code' in result)
    return result['code'][0], verifier

def exchange(code, verifier):
    return request(metadata['token_endpoint'], {'grant_type': 'authorization_code', 'client_id': client,
                   'redirect_uri': CALLBACK, 'code': code, 'code_verifier': verifier}, form=True)

code, verifier = authorize(test_password=True)
check('wrong PKCE verifier rejected', exchange(code, secrets.token_urlsafe(48))[0] == 400)
code, verifier = authorize()
status, body, _, _ = exchange(code, verifier)
check('authorization code exchanged', status == 200)
tokens = json.loads(body)
access = tokens['access_token']
status, body, _, _ = request('/mcp', init, token=access)
check('OAuth MCP initialization', status == 200 and 'serverInfo' in decode(body).get('result', {}))
check('tampered JWT rejected', request('/mcp', init, token=access[:-8] + 'INVALID!')[0] == 401)
status, body, _, _ = request('/mcp', rpc('tools/list'), token=access)
check('OAuth chat tools available', status == 200 and any(t['name'] == 'chats-get-messages' for t in decode(body)['result']['tools']))
status, body, _, _ = request('/mcp', rpc('tools/call', {'name': 'sessions-get', 'arguments': {'session': 'default'}}), token=access,
                            extra_headers={'X-Api-Key': 'deliberately-invalid-injected-key'})
inner = json.loads(decode(body)['result']['content'][0]['text'])
check('OAuth session read; caller cannot override backend key', status == 200 and inner['status'] == 200)
status, body, _, _ = request('/mcp', rpc('tools/call', {'name': 'sessions-stop', 'arguments': {'session': 'permission-test-nonexistent'}}), token=access)
check('OAuth cannot stop sessions', json.loads(decode(body)['result']['content'][0]['text'])['status'] == 403)
check('OAuth cannot expose admin REST API', request('/api/sessions', token=access)[0] == 404)
subprocess.run(['systemctl', '--user', 'restart', 'waha-oauth.service'], check=True)
# Restart completion precedes listener readiness. Poll locally without printing tokens.
import time
import socket
for attempt in range(50):
    try:
        with socket.create_connection(('127.0.0.1', 3033), timeout=1):
            break
    except OSError:
        time.sleep(0.1)
status, body, _, _ = request('/mcp', init, token=access)
check('access token survives gateway restart', status == 200)
status, body, _, _ = request(metadata['token_endpoint'], {'grant_type': 'refresh_token', 'client_id': client,
                           'refresh_token': tokens['refresh_token']}, form=True)
check('refresh token and client survive restart', status == 200)
check('refreshed access token works', request('/mcp', init, token=json.loads(body)['access_token'])[0] == 200)
check('authorization code cannot be replayed', exchange(code, verifier)[0] == 400)
print('All OAuth checks passed; no messages sent.')
