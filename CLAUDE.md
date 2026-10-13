# WhatsApp bridge execution context

This standalone project runs rootless Podman containers under systemd user Quadlet units on Fedora Linux. No Docker daemon or application build is required.

Workspace: `/var/mnt/stuff/development/whatsapp-bridge`.
Run project commands from this directory. Do not commit `private/` or `data/`; they contain credentials, WhatsApp session keys, messages and attachments.

WAHA listens on loopback port 3030. Nginx listens on loopback port 3031 and exposes MCP, authenticated media and OAuth login/discovery routes. The pinned sigbit/mcp-auth-proxy binary listens on loopback port 3033 with persistent state in data/oauth. Tailscale Funnel uses HTTPS port 8443; the pre-existing private service on port 443 must stay private.

Use a scoped session key for agents. Never put the WAHA admin key into an agent configuration or expose administrative endpoints through the tunnel. Initial agent permissions are read-only.

Validation must include missing/invalid credential rejection, MCP initialization and tool discovery, forbidden write checks against a nonexistent session (never a real recipient), and isolation of admin paths. Never send a WhatsApp message as a test.

Run scripts/verify-oauth.py for OAuth changes. It registers a test client and restarts the OAuth gateway to check persistence. Keep upstream request logs disabled because they include OAuth query parameters. Never print passwords, tokens or cookies. Use scripts/setup-oauth.py to regenerate private OAuth configuration after rotating the agent key, then restart both waha-oauth and waha-proxy.
