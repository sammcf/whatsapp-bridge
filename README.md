# WhatsApp MCP bridge

Self-hosted WAHA 2026.9.2 (GOWS engine), rootless Podman, systemd user services, and Tailscale Funnel. Container images are pinned by digest in `deploy/`.

This repository records a working personal deployment, rather than a fresh-install bootstrapper. Deployment paths, the Tailscale hostname, and OAuth client identifiers are specific to this installation; adapt them before deploying elsewhere. OAuth client IDs and endpoint URLs are public identifiers, not credentials.

Credentials, WhatsApp databases and attachments, OAuth state, downloaded binaries, generated plugin archives, and local caches are excluded from Git. A fresh checkout requires your own WAHA configuration in `private/waha.env`, a paired session and scoped read-only MCP key in `private/agent-key`. Never substitute the administrator key for the scoped agent key. Install Podman/Quadlet, Tailscale, Python, and `jsonschema` (for plugin packaging); configure your own Funnel and OAuth registration before installing the services.

## Agent connection

- Endpoint: `https://fiddler.minotaur-altered.ts.net:8443/mcp`
- Transport: Streamable HTTP MCP
- Authentication: `Authorization: Bearer <agent-key>` or `X-Api-Key: <agent-key>`
- WhatsApp session: `default`
- Key: `private/agent-key` (mode 0600)
- Ready-to-use generic MCP configuration: `private/mcp-client.json` (mode 0600)

Client configuration syntax varies. Copy the endpoint and authentication header into the client's remote MCP settings. The supplied JSON uses the common `mcpServers` shape. The same endpoint also supports OAuth for ChatGPT.

The key permits reading only. WAHA may list write tools, but server-side permissions reject their execution. The administrator key in `private/waha.env` must never be used by an agent.

## ChatGPT OAuth connection

### Uploadable plugin archive

Upload `dist/whatsapp-bridge-provided.zip` to ChatGPT. It includes root `plugin.json` and `mcp.json`, the registered client ID, and explicit OAuth endpoints. Enter the secret from `private/chatgpt-client-secret.txt` when prompted. The archive contains no passwords, API keys, or client secrets.

If upload creates a different callback, the registered client needs replacement for that exact callback. Alternatively, `dist/whatsapp-bridge-dcr.zip` explicitly requests dynamic client registration, allowing ChatGPT to register its new callback automatically. Install one variant, not both.

Rebuild with `python3 scripts/build-plugin.py` (requires `jsonschema`). The script checks portable manifest fields against the vendored Agent Plugins 1.0.0 schemas and separately checks the OpenAI OAuth extension documented at https://developers.openai.com/plugins/build/plugins. The published portable MCP schema currently rejects server-level extensions, so validation strips only that documented extension before checking the portable fields. ZIP integrity, an explicit two-file allowlist, secret exclusion, and deliberate invalid-transport rejection are checked during the build. Actual ChatGPT import remains to be tested in the UI.

Add a custom MCP connection with URL `https://fiddler.minotaur-altered.ts.net:8443/mcp` and authentication **OAuth**. Use the registered client ID from `private/chatgpt-client-id.txt` and client secret from `private/chatgpt-client-secret.txt`. In the browser login, enter the separate password from `private/oauth-password.txt`, then click **Authorize**. No username or external identity-provider account is required.

The ChatGPT client is registered for the exact callback `https://chatgpt.com/connector/oauth/WjsDrP9JaCGL`, with authorization-code and refresh grants and `client_secret_post` authentication. Its registration response is saved in `private/chatgpt-oauth-client.json` (0600). If recreating the plugin changes its callback, register a new client for the new exact URL. Dynamic registration passes standalone tests, but the user's ChatGPT setup required explicit client credentials. [Official OAuth guidance](https://developers.openai.com/plugins/build/auth#redirect-url).

The MIT-licensed [sigbit/mcp-auth-proxy](https://github.com/sigbit/mcp-auth-proxy) runs locally. The pinned Linux amd64 release is **v2.10.2**, SHA256 `1c76b230fdb6c536a0912c059232cba2229acbcf1f02a11a5d0664781326bcd6`. `scripts/setup-oauth.py` downloads and verifies it when absent; the service installer runs this setup automatically and preserves the existing login password. No paid authentication service is involved.

OAuth clients receive the same read-only WAHA permissions as API-key clients. Nginx passes only the exact configured static key directly to WAHA; other MCP requests go through OAuth verification. The gateway injects the scoped key server-side, after nginx removes caller-supplied API-key headers. Discovery and a `WWW-Authenticate` challenge advertise the OAuth server.

`private/oauth.env` holds the gateway password and backend key; `private/agent-key.map` holds the static-key routing rule. These and the login password are mode 0600. `data/oauth/` persists registered clients, token state, and signing keys across restarts. Back it up with the private configuration. Changing the login password alone does not revoke already issued OAuth credentials.

OAuth request logs are disabled because the upstream logger includes full query strings, which can contain authorization codes. Use service state and the verification script for routine diagnostics. Media downloads still require a WAHA API/file key; an OAuth access token authenticates MCP calls, not the separate media route.

## WhatsApp pairing

Open `http://127.0.0.1:3032` on this computer. On your phone, use WhatsApp → Linked devices → Link a device, then scan the QR code. The page automatically refreshes it.

The pairing helper is a local-only temporary service. After pairing:

```sh
systemctl --user stop waha-pairing.service
```

If a later re-pair is needed, use:

```sh
python3 scripts/admin.py pair
```

This starts the session if needed and runs the pairing page in the foreground. Stop it with Ctrl-C after scanning. Never tunnel port 3032: it exposes the pairing QR.

## Services and storage

```sh
systemctl --user status waha.service waha-proxy.service waha-oauth.service
systemctl --user restart waha.service
tailscale funnel status
python3 scripts/admin.py status
```

The two Quadlet definitions are installed as regular files under `~/.config/containers/systemd/`, so systemd can find them even if the project drive mounts late. They retry every five seconds after failures, with no startup rate limit, and verify that `/var/mnt/stuff` is mounted before starting. User lingering is enabled, allowing startup at boot without an interactive login.

`waha-funnel.service` is enabled under `~/.config/systemd/user/` and restores the port-8443 Funnel endpoint at boot. It retries failures every 15 seconds. The system `tailscaled.service` is enabled at boot and maintains the tunnel after setup. This does not modify the private port-443 service.

`waha-oauth.service` is also enabled at boot and automatically restarts after failures. It binds only `127.0.0.1:3033`; TLS terminates at Funnel. OAuth login, consent, PKCE, refresh, and token persistence have been tested through the HTTPS endpoint. Completing the actual ChatGPT connection remains a client-side step.

After editing unit definitions in `deploy/`, reinstall them with `bash scripts/install-services.sh`, then restart the affected service. The installer explicitly enables lingering. These services require the computer to remain powered on and awake.

Paths:

- `data/sessions/`: WhatsApp credentials, message databases, MCP app/key records.
- `data/media/`: downloaded attachments. Retention is unlimited (`WHATSAPP_FILES_LIFETIME=0`); monitor disk space.
- `data/oauth/`: OAuth client/token database and signing keys.
- `private/`: API credentials and client configuration.

Back up session databases consistently (stop WAHA briefly or use a filesystem snapshot), alongside media and private configuration. Treat all these paths as sensitive. They are ignored by Git.

WAHA binds only `127.0.0.1:3030`. Nginx binds `127.0.0.1:3031`, accepts `/mcp`, authenticated GET/HEAD under `/api/files/`, and OAuth paths under `/.auth/`, `/.idp/`, and `/.well-known/`. Other paths are rejected. Dashboard and Swagger are disabled. Access logs are disabled to avoid recording message/file URLs or credentials.

Funnel uses port **8443**. The existing private `/v1/library` service on port **443** is separate and must remain private. To disable only this public endpoint:

```sh
tailscale funnel --https=8443 off
```

To keep it disabled across reboots, also run `systemctl --user disable --now waha-funnel.service`.

To restore it:

```sh
tailscale funnel --bg --https=8443 --yes http://127.0.0.1:3031
```

## Verification

```sh
python3 scripts/verify.py
python3 scripts/verify.py https://fiddler.minotaur-altered.ts.net:8443
python3 scripts/verify-oauth.py
python3 scripts/verify-oauth.py --chatgpt
```

Checks cover missing/invalid credentials, both authentication header formats, MCP initialization, chat tools, session status, rejection of an out-of-scope operation, hidden management routes and media authentication. No messages are sent. Initial verification also confirmed that the agent key receives 403 on the send API for its own session using a payload with no recipient or text.

The OAuth script registers a test client on each run and briefly restarts the gateway. It checks wrong-password rejection, consent, PKCE failure and success, tampered-token rejection, read-only MCP calls, backend-header isolation, restart persistence, refresh and authorization-code replay rejection. It prints no credentials or chat contents.

With `--chatgpt`, it instead tests the existing registered confidential client and intercepts the final redirect locally without sending the test authorization code to ChatGPT.

The deployment was also checked through a public Funnel edge address (resolved using public DNS, preserving TLS hostname verification): missing and invalid keys returned 401; a valid key successfully initialized MCP. The existing private port-443 Tailscale configuration was compared before and after and remained unchanged.

WhatsApp pairing is complete. The session returned to `WORKING` after restarting WAHA without another QR scan, and chat retrieval succeeded again. Live `chats-list` retrieval through the authenticated HTTPS MCP endpoint also succeeded. The temporary pairing service has been stopped.

After pairing, run `python3 scripts/admin.py check-chats` to confirm live chat retrieval without printing chat names or message contents.

## Limitations

- This computer must stay awake and online for fresh syncing and endpoint access.
- Keep using WhatsApp on the primary phone; linked devices can log out after more than 14 days of primary-phone inactivity.
- History synchronization is best effort. Authentication persistence does not guarantee complete historical coverage.
- WAHA provides chat/message retrieval and pagination. A separate index may be useful for full-text or semantic search.
- It uses an unofficial WhatsApp connection, which can break after protocol changes or be restricted by WhatsApp.
- Automatic image updates are intentionally disabled. Upgrade the pinned images deliberately and repeat verification.

Sources: [WAHA MCP](https://waha.devlike.pro/docs/apps/mcp/), [GOWS](https://waha.devlike.pro/docs/engines/gows/), [storage](https://waha.devlike.pro/docs/how-to/storages/), [Tailscale Funnel](https://tailscale.com/docs/features/tailscale-funnel).
