# Hermes AgentMail setup and verification

Use this when configuring AgentMail inside a Hermes profile and testing inbox access.

## Configure the API key

Find the active profile env file:

```bash
/opt/hermes/.venv/bin/python /opt/hermes/hermes config env-path
```

Add or replace:

```bash
AGENTMAIL_API_KEY=am_...
```

For the SiteKick profile this has been `/opt/data/profiles/sitekick/.env`, but always check `hermes config env-path` for the active profile.

## Ensure pip exists in the Hermes venv

Some Hermes source checkouts have a slim venv without pip. If `python -m pip` fails, install pip with uv:

```bash
uv pip install --python /opt/hermes/.venv/bin/python pip
/opt/hermes/.venv/bin/python -m pip --version
```

Then install AgentMail:

```bash
/opt/hermes/.venv/bin/python -m pip install agentmail
```

## Verify SDK access

Load the profile env and list inboxes:

```bash
set -a
. /opt/data/profiles/sitekick/.env
set +a
/opt/hermes/.venv/bin/python - <<'PY'
from agentmail import AgentMail
client = AgentMail()
resp = client.inboxes.list()
print('inbox_count:', getattr(resp, 'count', None) or len(getattr(resp, 'inboxes', []) or []))
for inbox in resp.inboxes:
    print('inbox:', inbox.email, '| display_name:', getattr(inbox, 'display_name', None))
PY
```

## Count messages with pagination

Do not assume one page is complete. AgentMail list endpoints use cursor pagination.

```bash
set -a
. /opt/data/profiles/sitekick/.env
set +a
/opt/hermes/.venv/bin/python - <<'PY'
from agentmail import AgentMail
client = AgentMail()
for inbox in client.inboxes.list().inboxes:
    total = 0
    page_token = None
    while True:
        kwargs = {'inbox_id': inbox.email, 'limit': 100}
        if page_token:
            kwargs['page_token'] = page_token
        resp = client.inboxes.messages.list(**kwargs)
        total += len(getattr(resp, 'messages', []) or [])
        page_token = getattr(resp, 'next_page_token', None)
        if not page_token:
            break
    print(f'{inbox.email}\t{total}')
PY
```

## Notes

- The SDK can read `AGENTMAIL_API_KEY` from the environment; no need to pass the key in code.
- When the SDK is unavailable, the REST API works directly: `Authorization: Bearer $AGENTMAIL_API_KEY`, base URL `https://api.agentmail.to/v0`.
- Do not send messages or create/update/delete inbox records without explicit user approval.