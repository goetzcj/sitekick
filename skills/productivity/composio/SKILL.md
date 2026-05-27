---
name: composio
description: Use when integrating with third-party services (GitHub, Google, Slack, Linear, etc.) via the Composio Python package. Covers installation, API-key auth, SDK usage, tool execution, and connecting accounts. Prefer env-var auth over interactive login for autonomous agent operation.
version: 1.0.1
author: Aspire Interactive Technologies LLC
license: Commercial
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [composio, integrations, tools, api, python]
    related_skills: [native-mcp, agentmail]
---

# Composio

Composio connects agents to 250+ external services (GitHub, Google Workspace, Slack, Linear, Notion, etc.) through a unified Python SDK. Each service exposes typed actions the agent can execute directly after the account is linked once.

## When to Use

- You need to call a third-party API action (create a GitHub issue, send a Slack message, update a Linear ticket) without writing bespoke auth or request code
- You want to enumerate available tools for a connected service at runtime
- You're setting up a new Hermes profile that relies on Composio-backed integrations
- Don't use for: direct HTTP calls to APIs that don't need Composio auth injection, or when the composio package is not installed (run `scripts/install.sh` first)

## Installation

Run the bundled installer (detects uv vs pip automatically):

```bash
bash skills/productivity/composio/scripts/install.sh
```

Or manually:

```bash
# uv-managed Hermes installs
uv add composio

# pip-managed installs
pip install composio
```

Verify:

```bash
python -c "import composio; print('composio ok:', composio.__version__)"
```

## Authentication

For autonomous agent operation, set the API key in the profile `.env` — no interactive login required:

```bash
# ~/.hermes/profiles/sitekick/.env
COMPOSIO_API_KEY=your-key-here
```

The SDK picks this up automatically:

```python
import os
from composio import Composio

composio = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))
```

For interactive / one-time setup on a developer machine only:

```bash
composio login   # opens browser — NOT suitable for headless agent operation
composio whoami  # verify auth
```

## Connecting Accounts (One-Time Setup)

Link a third-party account once; Composio handles token storage and refresh:

```bash
composio add github      # GitHub
composio add googlecalendar
composio add slack
composio add linear
```

List connected accounts:

```bash
composio connections
```

## Python SDK — Core Patterns

Always follow this three-step pattern: **init client → create session with user_id → use session**.

The `user_id` is the single most important parameter. Composio uses it to partition connected accounts — each unique `user_id` has its own completely isolated set of connections. **Using the wrong `user_id` gives access to a different user's accounts.**

### user_id rules

| Context | Correct `user_id` | Wrong |
|---|---|---|
| Agent's own admin tasks | Fixed string, e.g. `"sitekick-admin"` | — |
| Telegram user interaction | `f"telegram-{message.from_user.id}"` | `"sitekick-agent"` (shared) |
| Email user interaction | `f"user-{sender_email}"` | any hardcoded string |

**Never fall back to a hardcoded default when a user-specific ID is available.** An incorrect `user_id` silently uses the wrong person's connected accounts — there is no error.

### Complete connection flow (single-agent / admin)

```python
import os
from composio import Composio

# 1. Init the client (reads COMPOSIO_API_KEY from env)
composio = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))

# 2. Create a session — use a FIXED id for the agent's own admin tasks only
session = composio.create(user_id="sitekick-owner")

# 3. List available tools
tools = session.tools(toolkits=["github"])  # omit toolkits= to get all connected

# 4. Execute a tool
result = session.execute(
    "GITHUB_CREATE_AN_ISSUE",
    arguments={"owner": "your-org", "repo": "your-repo",
               "title": "Issue from SiteKick", "body": "Details here"},
)
print(result)
```

### Multi-user isolation (Telegram example)

When the interaction comes from a real user (e.g. a Telegram message), derive `user_id` from the platform identity — never use a hardcoded shared ID:

```python
import os
from composio import Composio

composio = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))

def get_user_session(telegram_user_id: int):
    """Return a Composio session scoped to this Telegram user.
    Each user's connected accounts are fully isolated from every other user.
    """
    user_id = f"telegram-{telegram_user_id}"   # stable, unique per Telegram user
    return composio.create(user_id=user_id)

# In your message handler:
# session = get_user_session(message.from_user.id)
# tools  = session.tools(toolkits=["googlecalendar"])
# result = session.execute("GOOGLECALENDAR_CREATE_EVENT", arguments={...})
```

> **Initial setup note:** The admin connects accounts once using the admin `user_id` (e.g. `"sitekick-owner"`). End-users who need their *own* connected accounts must go through their own OAuth flow tied to *their* `user_id`. A connection made under `"sitekick-owner"` is **not** accessible under `"telegram-12345"` — they are isolated by design.

### Use tools with an LLM (pass as schemas)

```python
# session.tools() returns OpenAI-compatible tool schemas
tools = session.tools()
# Pass `tools` directly to your LLM client's tools parameter
```

## Common Pitfalls

1. **Interactive login in agent context.** `composio login` requires a browser. Always use `COMPOSIO_API_KEY` env var in `.env` for headless operation.

2. **Package not installed.** `ImportError: No module named 'composio'` — run `scripts/install.sh` or `pip install composio`.

3. **Account not connected.** Tool execution fails if the third-party account hasn't been linked. Run `composio add <toolkit>` once from a developer machine.

4. **Cross-user `user_id` contamination (silent data leak).** Composio does not error if you use a wrong `user_id` — it simply opens that user's accounts. In multi-user contexts, always derive `user_id` from the incoming request. Hardcoding a single shared ID in a multi-user flow means every user operates on the same connected accounts. Use `f"telegram-{telegram_user.id}"` (or equivalent), not `"sitekick-owner"`.

5. **Using `composio-core` instead of `composio`.** `composio-core` is deprecated (PyPI status: Inactive). Always install the `composio` package.

## Verification Checklist

- [ ] `COMPOSIO_API_KEY` is present in the profile `.env`
- [ ] `python -c "import composio"` succeeds inside the Hermes virtualenv
- [ ] `composio connections` shows the expected linked accounts
- [ ] A test tool execution returns a result (not an auth error)
