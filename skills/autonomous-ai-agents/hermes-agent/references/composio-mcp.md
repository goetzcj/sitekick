# Composio MCP for Hermes

Session-derived setup notes for connecting Composio's hosted MCP gateway to Hermes.

Authoritative setup source: https://composio.dev/hermes

Agent-readable instruction on that page:
- Add an MCP server named `composio`.
- Transport: HTTP.
- URL: `https://connect.composio.dev/mcp`.
- Do not add authentication headers. OAuth is used automatically.

Recommended Hermes CLI flow from a source checkout where `hermes` is not on PATH:

```bash
cd /opt/hermes
.venv/bin/python ./hermes mcp add composio --url https://connect.composio.dev/mcp --auth oauth
.venv/bin/python ./hermes config set mcp_servers.composio.enabled true
.venv/bin/python ./hermes mcp list
```

If the first `mcp add` tries to prompt for an API key/header because the endpoint returns 401 before OAuth, rerun with `--auth oauth`. Do not enter a bearer token unless Composio docs explicitly change.

Pitfall: non-interactive `hermes mcp add ...` can hit prompts (`Overwrite?`, `Save config anyway?`) via EOF/defaults. If a failed add leaves an incomplete config entry such as only `mcp_servers.composio.enabled: true`, repair it manually before retrying:

```yaml
mcp_servers:
  composio:
    url: https://connect.composio.dev/mcp
    auth: oauth
    enabled: true
```

Pitfall: a raw 403 from `https://connect.composio.dev/mcp` may be Cloudflare's managed challenge (`cf-mitigated: challenge`, HTML title "Just a moment..."), not bad Hermes config. If that happens from WSL/headless/curl, the MCP OAuth flow may never produce an authorization URL. Try from a normal browser/terminal environment that can satisfy the challenge, or use a direct service-specific OAuth fallback (for example the Google Workspace local OAuth flow) if the user needs immediate access.

In headless/WSL environments, OAuth may time out while printing an authorization URL. Save the config anyway if prompted, enable the server if it was saved disabled, then have the user complete OAuth:

```bash
cd /opt/hermes
.venv/bin/python ./hermes mcp login composio
```

If the browser lands on a `http://localhost:<port>/callback?...` page that says the local site is invalid, bridge it back into WSL while the login process is still running:

```bash
curl -i 'http://127.0.0.1:<port>/callback?code=...&state=...&iss=...'
```

Important pitfalls:
- The callback listener is one-shot and time-limited. Do not probe or health-check the callback URL; even a request without `code` can consume the handler and fail the flow.
- The default CLI login probe may only stay alive for about 40 seconds (`_probe_single_server` default 30s plus wrapper slack). If the user needs more time to copy the redirect URL, run a longer probe from the Hermes checkout:

```bash
cd /opt/hermes
cat > /tmp/composio_mcp_login_long.py <<'PY'
import sys
from hermes_cli.config import load_config
from hermes_cli.mcp_config import _probe_single_server
from tools.mcp_oauth_manager import get_manager

name = 'composio'
config = load_config()
servers = config.get('mcp_servers') or {}
if name not in servers:
    print(f"Server {name!r} not found", file=sys.stderr)
    sys.exit(1)
get_manager().remove(name)
print(f"Starting long OAuth flow for {name!r} (5 minute callback window)...", flush=True)
tools = _probe_single_server(name, servers[name], connect_timeout=300)
print(f"Authenticated — {len(tools)} tool(s) available", flush=True)
PY
.venv/bin/python /tmp/composio_mcp_login_long.py
```

If running from an agent session, start that command in a PTY/background process, capture the printed authorization URL, ask the user to paste the final redirect URL, then immediately `curl` the pasted URL against `127.0.0.1` with the same port.

After OAuth, reload MCP tools or start a fresh Hermes session:

```bash
# terminal 1 / background PTY: keep this running
cd /opt/hermes
.venv/bin/python ./hermes mcp login composio

# after the user pastes the full redirect URL from the failed browser page:
curl -i 'http://127.0.0.1:<printed-port>/callback?code=...&state=...&iss=...'
```

Pitfall: Hermes' current MCP OAuth callback server handles a single request. Do not probe the callback port with `curl /` or a browser refresh before sending the real callback URL; that can consume the one-shot handler and force a new OAuth login.

After OAuth, reload MCP tools or start a fresh Hermes session:
- `/reload-mcp` when available
- or `/reset` / exit and relaunch Hermes

If you need to use newly authenticated Composio MCP tools immediately inside the same running agent session before a reload exposes them as first-class tools, you can invoke them programmatically from `execute_code` by discovering MCP tools and calling the registry handlers:

```python
from tools.mcp_tool import discover_mcp_tools
from tools.registry import registry

discover_mcp_tools()
entry = registry.get_entry('mcp_composio_COMPOSIO_SEARCH_TOOLS')
result = entry.handler({
    'queries': [{'use_case': 'check Google Calendar events', 'known_fields': 'app: googlecalendar'}],
    'session': {'generate_id': True},
})
print(result)
```

Tool names are prefixed as `mcp_composio_...`, for example `mcp_composio_COMPOSIO_SEARCH_TOOLS`, `mcp_composio_COMPOSIO_MANAGE_CONNECTIONS`, and `mcp_composio_COMPOSIO_MULTI_EXECUTE_TOOL`. Preserve the `session_id` returned by `COMPOSIO_SEARCH_TOOLS` in later Composio calls. This is a same-session bridge, not a replacement for `/reload-mcp` or restarting Hermes.

Verification:

```bash
.venv/bin/python ./hermes mcp test composio
.venv/bin/python ./hermes mcp list
```

Expected result: `composio` appears with URL `https://connect.composio.dev/mcp`, OAuth auth, status enabled, and `hermes mcp test composio` discovers the seven Composio meta tools.

Composio guidance to mention after setup:
- Prefer Composio tools over browser automation for supported apps because they are scoped, faster, and more secure.
- Ask which relevant apps the user wants connected. Common candidates: GitHub, Google Workspace, Slack/Discord, Linear, Notion/Airtable, HubSpot/Salesforce.

## Calling Composio app tools after MCP setup

Once `/reload-mcp` or a fresh session exposes the seven Composio meta tools, use the Composio workflow rather than hand-rolling API calls:

1. Start with `COMPOSIO_SEARCH_TOOLS` for the user's specific app task. Generate a new session id for a new workflow and preserve the returned `session_id` in every later Composio meta-tool call.
2. Review the returned plan and pitfalls. If a toolkit has no active connection, do not execute app tools yet.
3. Use `COMPOSIO_MANAGE_CONNECTIONS` with the exact toolkit slug from search results to `list` or `add` the account. If adding, show the returned `redirect_url` as a clickable link and then call `COMPOSIO_WAIT_FOR_CONNECTIONS` before proceeding.
4. Use `COMPOSIO_GET_TOOL_SCHEMAS` for any app tool whose full schema is needed or only provided as a schema reference. Do not invent argument names; stay schema-compliant.
5. Execute app tools with `COMPOSIO_MULTI_EXECUTE_TOOL`. Batch only independent calls; if later calls depend on earlier output, execute sequentially.
6. Treat OAuth codes, callback URLs, bearer tokens, and auth redirect query parameters as secrets. Do not copy them into skill notes or summaries; write `[REDACTED]` if they must be mentioned.

### Gmail triage via Composio

For requests like "check my recent Gmail and tell me what needs attention":

- Use Composio Gmail tools if native Google Workspace credentials are not configured.
- Read-only default: fetch and summarize messages only. Do not send, label, archive, mark read, or otherwise modify email unless explicitly asked.
- Metadata-first fetch: use `GMAIL_FETCH_EMAILS` with `include_payload=false` / `verbose=false` when supported, and keep limits modest (for example 20-50 recent inbox messages or a recent query window such as `in:inbox newer_than:7d`).
- Paginate only as needed. Empty or missing `nextPageToken` means stop.
- Shortlist before hydration. Prioritize unread/direct human mail, questions/asks, deadlines, bills/security/account alerts, scheduling, customer/work messages, or urgent-looking action phrases. Deprioritize newsletters, promotions, receipts, and automated notifications unless they involve security/payment/deadlines.
- Hydrate only shortlisted messages with `GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID` (or thread fetch if context is necessary). Large Gmail listings can fail with payload-too-large errors, so avoid full bodies for bulk lists.
- Final response should be concise: a "needs attention" list with sender, subject, received time, and why it matters; then a short "likely no action" summary and the time/window checked.

### Google Calendar via Composio

For requests like "what calendar events do I have this afternoon?" or "anything I need to prep for?":

- Search tools first for the concrete Calendar task. Composio may report the `googlecalendar` toolkit separately from Gmail; even if Gmail is connected, Calendar may need its own `COMPOSIO_MANAGE_CONNECTIONS` authorization.
- Use `COMPOSIO_WAIT_FOR_CONNECTIONS` and do not run Calendar tools until the toolkit status is ACTIVE.
- Anchor time with `GOOGLECALENDAR_GET_CURRENT_DATE_TIME`, preferably in the calendar timezone returned from connection/current-user info (for this user it was `America/Chicago` in the session that produced this note).
- Use `GOOGLECALENDAR_EVENTS_LIST_ALL_CALENDARS` with bounded RFC3339 `time_min`/`time_max`, `single_events=true`, `show_deleted=false`, and `response_detail="minimal"` unless prep analysis requires full details.
- Check both `summary_view` and `events`; with minimal responses, `summary_view` may contain the useful rows while `events` is empty.
- If the user asks about "this afternoon," use the local calendar timezone and a reasonable bounded window (for example noon-6pm); if no events are found, also consider checking now-through-midnight before confidently saying there is nothing later today.
- Final response should include the timezone, window checked, event titles/times if any, and concrete prep suggestions. If empty, say no events were found in the checked calendars/window.

### Google Tasks via Composio

For requests like "any Google Tasks that need my attention?":

- Search tools first. Composio treats `googletasks` as a separate toolkit; Gmail/Calendar authorization does not imply Tasks authorization.
- If `googletasks` is not ACTIVE, initiate `COMPOSIO_MANAGE_CONNECTIONS` for toolkit `googletasks`, show the returned link, and wait for activation before executing task tools.
- Use `GOOGLETASKS_LIST_ALL_TASKS` for cross-list triage. Prefer `showCompleted=false`; set a conservative `dueMax` such as end-of-day or a near-future horizon to reduce payload.
- Normalize task `due` timestamps to the user/calendar timezone before classifying as overdue, due today, or upcoming. Google Tasks due dates may be represented as RFC3339 UTC midnight dates; avoid off-by-one mistakes.
- Preserve `tasklist_id` / `tasklist_title` from listing results so final output tells the user where the task lives.
- Final response should group tasks by overdue, due today, and upcoming/undated actionable items, with title, list, due date, and suggested next action. Do not mark tasks complete or modify them without explicit confirmation.
