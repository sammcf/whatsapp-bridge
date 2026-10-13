#!/usr/bin/env python3
"""Build credential-free ChatGPT plugin ZIPs from an explicit file allowlist.

Requires jsonschema. Schemas are vendored from agent-plugins.org, version 1.0.0.
"""
import copy
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / 'plugin/plugin.json').read_text())
mcp = json.loads((ROOT / 'plugin/mcp.json').read_text())
schemas = {name: json.loads((ROOT / f'schemas/{name}.schema.json').read_text())
           for name in ('plugin', 'mcp')}

def validate(manifest, mcp):
    jsonschema.validate(manifest, schemas['plugin'])
    # The published portable schema rejects extensions on server entries, while
    # OpenAI's package docs explicitly require them for OAuth configuration.
    # Validate the portable portion separately from the documented extension.
    portable = copy.deepcopy(mcp)
    for server in portable['mcpServers'].values():
        extension = server.pop('extensions')
        assert set(extension) == {'com.openai'}
        auth = extension['com.openai']['auth']
        assert auth['type'] == 'oauth'
        assert auth['client']['mode'] in ('provided', 'dcr')
        assert 'clientSecret' not in auth['client']
        if auth['client']['mode'] == 'provided':
            assert auth['client']['clientId']
            assert auth['client']['tokenEndpointAuthMethod'] == 'client_secret_post'
        else:
            assert set(auth['client']) == {'mode'}
            assert auth['registrationUrl'].startswith('https://')
    jsonschema.validate(portable, schemas['mcp'])

validate(manifest, mcp)
# Verify that schema validation actually rejects an invalid transport.
broken = copy.deepcopy(mcp)
broken['mcpServers']['whatsapp']['type'] = 'deliberately-invalid-transport'
try:
    validate(manifest, broken)
except jsonschema.ValidationError:
    pass
else:
    raise AssertionError('Schema validation failed to reject the deliberate violation')

secrets = [(ROOT / 'private' / name).read_text().strip() for name in
           ('agent-key', 'oauth-password.txt', 'chatgpt-client-secret.txt')]
(ROOT / 'dist').mkdir(exist_ok=True)
for mode in ('provided', 'dcr'):
    config = copy.deepcopy(mcp)
    auth = config['mcpServers']['whatsapp']['extensions']['com.openai']['auth']
    if mode == 'dcr':
        auth['client'] = {'mode': 'dcr'}
        auth['registrationUrl'] = auth['authorizationServerBase'] + '.idp/register'
    validate(manifest, config)
    entries = {'plugin.json': manifest, 'mcp.json': config}
    target = ROOT / 'dist' / f'whatsapp-bridge-{mode}.zip'
    with ZipFile(target, 'w', compression=ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            content = json.dumps(data, indent=2) + '\n'
            if any(secret in content for secret in secrets if secret):
                raise AssertionError('Secret detected in package')
            archive.writestr(name, content)
    with ZipFile(target) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(entries)
    print(f'Validated {target} ({target.stat().st_size} bytes)')
