#!/usr/bin/env python3
"""Install the pinned OAuth gateway and generate private local configuration."""
import hashlib
import os
import re
import secrets
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'v2.10.2'
SHA256 = '1c76b230fdb6c536a0912c059232cba2229acbcf1f02a11a5d0664781326bcd6'
URL = f'https://github.com/sigbit/mcp-auth-proxy/releases/download/{VERSION}/mcp-auth-proxy-linux-amd64'
os.umask(0o077)
binary = ROOT / 'bin/mcp-auth-proxy'
binary.parent.mkdir(exist_ok=True)
if not binary.exists():
    with urllib.request.urlopen(URL, timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise SystemExit('OAuth release checksum mismatch')
    temporary = binary.with_suffix('.tmp')
    temporary.write_bytes(data)
    temporary.chmod(0o755)
    temporary.replace(binary)
if hashlib.sha256(binary.read_bytes()).hexdigest() != SHA256:
    raise SystemExit('Installed OAuth binary differs from the pinned release')

private = ROOT / 'private'
private.mkdir(exist_ok=True, mode=0o700)
password_file = private / 'oauth-password.txt'
if not password_file.exists():
    password_file.write_text(secrets.token_urlsafe(32) + '\n')
key = (private / 'agent-key').read_text().strip()
password = password_file.read_text().strip()
# These are generated tokens. Reject characters requiring nginx/systemd escaping.
if not all(re.fullmatch(r'[A-Za-z0-9_-]+', value) for value in (key, password)):
    raise SystemExit('Expected URL-safe generated credentials')
(private / 'oauth.env').write_text(f'PASSWORD={password}\nPROXY_HEADERS=X-Api-Key:{key}\n')
(private / 'agent-key.map').write_text(f'"{key}" "{key}";\n')
for name in ('oauth-password.txt', 'oauth.env', 'agent-key.map'):
    (private / name).chmod(0o600)
(ROOT / 'data/oauth').mkdir(exist_ok=True, mode=0o700)
print('Pinned OAuth binary and private configuration ready.')
