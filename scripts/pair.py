#!/usr/bin/env python3
"""Local-only pairing page. Never forward this port through the tunnel."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ENV = dict(line.split('=', 1) for line in (ROOT / 'private/waha.env').read_text().splitlines())
PAIR_LOCK = threading.Lock()

def session_status():
    def api(path, post=False):
        req = Request('http://127.0.0.1:3030' + path,
                      headers={'X-Api-Key': ENV['WAHA_API_KEY'], 'Content-Type': 'application/json'},
                      data=b'{}' if post else None)
        with urlopen(req, timeout=15) as r:
            return json.load(r)
    with PAIR_LOCK:
        status = api('/api/sessions/default')['status']
        # QR windows expire. Renew only while the local pairing page is being viewed.
        if status == 'FAILED':
            api('/api/sessions/default/stop', True)
            status = 'STOPPED'
        if status == 'STOPPED':
            api('/api/sessions/default/start', True)
            status = 'STARTING'
        return status
PAGE = b'''<!doctype html><meta charset="utf-8"><title>Link WhatsApp</title>
<style>body{font:18px system-ui;max-width:650px;margin:50px auto;padding:20px}img{width:300px;height:300px}#status{font-weight:bold}</style>
<h1>Link WhatsApp</h1><p>On your phone, open WhatsApp &rarr; Settings / menu &rarr; Linked devices &rarr; Link a device, then scan:</p>
<p id="status">Checking session...</p><img id="qr" alt="Waiting for WhatsApp QR code">
<p>The QR code refreshes automatically. Once connected, this page can be closed.</p>
<script>
async function refresh(){try{let r=await fetch('/status',{cache:'no-store'});let s=await r.json();
document.getElementById('status').textContent=s.status;
let img=document.getElementById('qr');img.hidden=s.status==='WORKING';
if(s.status==='SCAN_QR_CODE')img.src='/qr?t='+Date.now();
}catch(e){document.getElementById('status').textContent='Waiting for bridge...'}}
refresh();setInterval(refresh,10000);
</script>'''

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.headers.get('Host') not in ('127.0.0.1:3032', 'localhost:3032'):
            self.send_error(403)
            return
        path = self.path.split('?', 1)[0]
        if path == '/':
            data, ctype, status = PAGE, 'text/html; charset=utf-8', 200
        elif path in ('/qr', '/status'):
            upstream = '/api/default/auth/qr' if path == '/qr' else '/api/sessions/default'
            headers = {'X-Api-Key': ENV['WAHA_API_KEY']}
            if path == '/qr':
                headers['Accept'] = 'image/png'
            try:
                if path == '/status':
                    data, ctype, status = json.dumps({'status': session_status()}).encode(), 'application/json', 200
                else:
                    with urlopen(Request('http://127.0.0.1:3030' + upstream, headers=headers), timeout=15) as r:
                        data, ctype, status = r.read(), r.headers.get('Content-Type', 'application/json'), 200
            except HTTPError as e:
                data, ctype, status = b'QR not ready. The page will retry.', 'text/plain', e.code
            except OSError:
                data, ctype, status = b'Bridge temporarily unavailable', 'text/plain', 503
        else:
            data, ctype, status = b'Not found', 'text/plain', 404
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass

if __name__ == '__main__':
    print('Pairing page: http://127.0.0.1:3032', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 3032), Handler).serve_forever()
