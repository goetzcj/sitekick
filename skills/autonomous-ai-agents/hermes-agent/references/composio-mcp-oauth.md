# Composio MCP setup and OAuth troubleshooting

Use this reference when configuring Composio from `composio.dev/hermes` or when using Composio MCP tools through Hermes.

## Durable setup facts

- Composio's Hermes MCP endpoint is `https://connect.composio.dev/mcp`.
- Configure it as an HTTP MCP server with OAuth/PKCE; do not invent API-key headers unless Composio's current setup page explicitly says to.
- In the `/opt/hermes` checkout, if the `hermes` CLI is not on PATH, invoke it via the venv, e.g. `.venv/bin/python ./hermes ...` from `/opt/hermes`.

Typical commands:

```bash
cd /opt/hermes
.venv/bin/python ./hermes mcp add composio --url https://connect.composio.dev/mcp --auth oauth
.venv/bin/python ./hermes config set mcp_servers.composio.enabled true
.venv/bin/python ./hermes mcp login composio
.venv/bin/python ./hermes mcp test composio
```

A healthy Composio MCP connection discovers these meta-tools:

- `COMPOSIO_SEARCH_TOOLS`
- `COMPOSIO_MANAGE_CONNECTIONS`
- `COMPOSIO_WAIT_FOR_CONNECTIONS`
- `COMPOSIO_GET_TOOL_SCHEMAS`
- `COMPOSIO_MULTI_EXECUTE_TOOL`
- `COMPOSIO_REMOTE_WORKBENCH`
- `COMPOSIO_REMOTE_BASH_TOOL`

## Headless / WSL OAuth callback workaround

If the user's browser completes OAuth but lands on a `localhost:<port>/callback?...` URL that fails, the browser may be on the Windows side while the callback listener is inside WSL. Have the user copy the full redirected URL from the browser address bar, then forward it inside WSL by replacing `localhost` with `127.0.0.1`:

```bash
curl -sS -i 'http://127.0.0.1:<port>/callback?<query-from-browser-url>'
```

Security rule: never preserve or expose OAuth codes, tokens, API keys, secrets, passwords, or connection strings. Redact callback URL `code`, `state`, tokens, and credentials as `[REDACTED]` in notes and summaries.

## Extending the callback window

`hermes mcp login composio` may only keep the OAuth listener open for roughly 40 seconds because the MCP probe default timeout is about `connect_timeout + 10`. In slow/headless OAuth flows, start a longer-lived probe from a helper script that calls Hermes internals with a larger `connect_timeout`.

Pattern:

```python
from hermes_cli.config import load_config
from tools.mcp_oauth import get_manager
from hermes_cli.mcp_config import _probe_single_server

cfg = load_config()
servers = cfg.get("mcp_servers") or {}
get_manager().remove("composio")  # force fresh PKCE state when retrying
_probe_single_server("composio", servers["composio"], connect_timeout=300)
```

Run that helper in the background/PTY, give the user the emitted authorization URL, and forward the copied callback URL into `127.0.0.1:<port>` before the long timeout expires.

Important: old callback URLs cannot be reused after the listener exits because the PKCE verifier and state live in the login process.

## Using app tools after MCP auth

Composio MCP auth only connects Hermes to Composio. Individual app toolkits such as Gmail may still need their own Composio connection.

Workflow:

1. Always call `COMPOSIO_SEARCH_TOOLS` first for the use case and keep the returned `session_id`.
2. If the needed toolkit is not active, call `COMPOSIO_MANAGE_CONNECTIONS` with the exact toolkit slug, show the user the returned auth link, then call `COMPOSIO_WAIT_FOR_CONNECTIONS` before executing app tools.
3. Call `COMPOSIO_GET_TOOL_SCHEMAS` for exact tool schemas before executing app tools.
4. Execute app tools with `COMPOSIO_MULTI_EXECUTE_TOOL`; use `COMPOSIO_REMOTE_WORKBENCH` for large saved responses.

## Gmail triage pattern through Composio

For Gmail triage, prefer metadata/snippet-first access:

- `GMAIL_FETCH_EMAILS` with `include_payload=false`, `verbose=false`, and a bounded query such as `newer_than:7d in:inbox`.
- Paginate with `nextPageToken` until absent/empty when completeness matters.
- Sort by `messageTimestamp` or `internalDate` client-side; results are not guaranteed sorted by recency.
- Shortlist likely action items from snippets: security alerts, billing/renewals, account/login alerts, failed CI/security scans, direct human requests, deadlines, scheduling, support/customer issues.
- Exclude ordinary newsletters/promotions/social updates unless urgent/account/security/billing related.
- Hydrate only shortlisted message IDs with `GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID` if full content is needed.
