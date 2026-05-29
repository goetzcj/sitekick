---
name: pocket-ai
description: Use when connecting to Pocket AI MCP, searching Pocket recordings/action items, or turning Pocket transcripts into SiteKick commitments, tasks, risks, and follow-ups.
version: 1.0.0
author: SiteKick
license: MIT
metadata:
  hermes:
    tags: [pocket, mcp, oauth, transcripts, action-items, construction-ops]
    related_skills: [native-mcp]
---

# Pocket AI for SiteKick

## Overview

Pocket AI captures audio, transcribes it, summarizes recordings into notes, and creates action items. For SiteKick, Pocket is a source of field commitments: customer promises, crew assignments, vendor follow-ups, estimates, change orders, inspections, material needs, blockers, risks, and decisions.

Treat Pocket output as source material, not final truth. Transcripts may contain speaker or wording errors. Extract likely commitments and ask for confirmation before sending messages, creating external records, spending money, changing schedules, or marking work complete.

## When to Use

Use this skill when the user wants to:
- Connect Pocket AI to Hermes/SiteKick through MCP.
- Authenticate Pocket using OAuth from Telegram, TUI, or another chat interface.
- Search Pocket recordings by topic, job, customer, date, or tag.
- Pull full transcripts from recordings.
- Review Pocket action items.
- Convert meeting, call, field-note, or voice-note recordings into SiteKick follow-ups.
- Produce a daily briefing from Pocket recordings and action items.

Do not use this skill for generic audio transcription if the audio is not in Pocket.

## MCP Connection Facts

Pocket MCP endpoint:

```text
https://public.heypocketai.com/mcp
```

Pocket MCP supports OAuth and API key auth. OAuth is preferred for normal users. API keys are a fallback for admin/server installs.

Verified Pocket MCP tools:

| Tool | Use |
| --- | --- |
| `get_pocket_conversation` | Fetch full transcripts for specific recording IDs, including transcript segments and signed audio URLs. |
| `search_pocket_conversations` | Search conversation sections using semantic + keyword search. |
| `search_pocket_conversations_timerange` | Fetch full transcripts within a date range, sorted by recency. |
| `search_pocket_actionitems` | Search Pocket action items by query, status, priority, category, due date, and source recording date. |

## OAuth Paste-Back Flow

This is the right pattern for Telegram and other messaging interfaces where the user cannot complete localhost OAuth directly inside the agent runtime.

1. Start the Pocket OAuth flow and generate an authorization URL.
2. Send the authorization URL to the user.
3. Tell the user to approve Pocket access.
4. The browser will redirect to a URL like:

```text
http://localhost:<port>/oauth/callback?code=...&state=...
```

5. The page may fail to load. That is expected when the callback server is inside the agent environment or not reachable from the user's browser.
6. Ask the user to paste the full localhost callback URL back into the chat.
7. Validate the returned `state` exactly matches the generated state.
8. Exchange the `code` for tokens.
9. Store tokens securely for the user/profile.
10. Verify by listing Pocket MCP tools.

Never ask the user to paste access tokens. The paste-back value should be the OAuth callback URL containing a short-lived authorization code.

## Production OAuth Connector Script

A reusable connector script now lives at:

```text
/root/.hermes/profiles/sitekick/skills/productivity/pocket-ai/scripts/pocket_connect.py
```

Use it for durable per-user Pocket OAuth, including Telegram paste-back flows.

Start OAuth for a user:

```bash
python3 /root/.hermes/profiles/sitekick/skills/productivity/pocket-ai/scripts/pocket_connect.py start --user-id telegram-123456
```

Send the printed `authorization_url` to the user. After they approve Pocket access, ask them to paste back the full localhost callback URL. Complete the connection:

```bash
python3 /root/.hermes/profiles/sitekick/skills/productivity/pocket-ai/scripts/pocket_connect.py complete --user-id telegram-123456 'http://localhost:11226/oauth/callback?code=...&state=...' --verify
```

Check or refresh a connection:

```bash
python3 /root/.hermes/profiles/sitekick/skills/productivity/pocket-ai/scripts/pocket_connect.py status --user-id telegram-123456
python3 /root/.hermes/profiles/sitekick/skills/productivity/pocket-ai/scripts/pocket_connect.py refresh --user-id telegram-123456
python3 /root/.hermes/profiles/sitekick/skills/productivity/pocket-ai/scripts/pocket_connect.py list-tools --user-id telegram-123456
```

Token storage:

```text
/root/.hermes/profiles/sitekick/mcp-tokens/pocket/<safe-user-id>.tokens.json
```

Files are written with private permissions where supported. The script never prints access or refresh tokens.

For single-owner/admin runtime MCP discovery only, after a user has connected you can write the current access token into Hermes config:

```bash
python3 /root/.hermes/profiles/sitekick/skills/productivity/pocket-ai/scripts/pocket_connect.py configure-hermes --user-id sitekick-owner
```

Then restart Hermes so native MCP tools are discovered as `mcp_pocket_*`. Use this only for a single-user/admin profile because `mcp_servers` is process-wide; for multi-user Telegram, keep tokens per `telegram-<id>` and route Pocket calls through the per-user token store instead of sharing one global Pocket connection.

## API Key Fallback

If OAuth is not available, Pocket API key auth uses:

```yaml
mcp_servers:
  pocket:
    url: "https://public.heypocketai.com/mcp"
    headers:
      Authorization: "Bearer pk_your_api_key_here"
    timeout: 120
    connect_timeout: 60
```

Pocket API keys start with `pk_`. Do not expose the key in summaries or logs.

## Search Strategy

For broad user requests, search first, then fetch full transcripts only for likely relevant recordings.

Examples:
- “What did I promise today?” → search Pocket action items and today’s conversations.
- “Find what we said about the Miller change order” → search conversations for customer/job + change order terms.
- “Wrap my day” → search today’s recordings and action items; rank by risk.
- “What did I tell the roofer?” → search conversations by roofer/vendor name and date if known.

Recommended order:

1. Search action items when the user asks for tasks, promises, due dates, or open loops.
2. Search conversations when the user asks what was discussed, decided, promised, or said.
3. Use time-range search for daily briefing or “today/yesterday/last week” requests.
4. Fetch full conversation transcripts only after identifying recording IDs.

## SiteKick Extraction Format

When reviewing Pocket transcripts, extract these fields when possible:

```text
Type: customer promise | crew task | subcontractor follow-up | vendor/materials | inspection/schedule | estimate/change order | invoice/payment | job note | risk/blocker | decision
Related job/customer:
Owner:
Action/commitment:
Due date/time:
Source recording:
Speaker/source:
Confidence: high | medium | low
Recommended next step: task | reminder | draft message | calendar event | job note | confirm only
Notes/uncertainty:
```

For mobile replies, summarize first:

```text
I found 4 follow-ups from Pocket:
1. High risk — Call inspector for Oak Street rough-in, due tomorrow. Owner unclear.
2. Customer promise — Send revised change order to Miller. Due Friday.
3. Materials — Order 12 sheets 5/8 drywall for Elm job. Need confirmation.
4. Crew task — Ask Jose to patch siding before rain. No due time given.

Want me to turn these into tasks?
```

## Commitment Rules

- Treat Pocket action items as drafts until the user confirms.
- Do not assume transcript speaker labels are correct when the content is uncertain.
- Do not mark something complete because it was discussed.
- Do not send customer or crew messages without approval.
- Do not schedule inspections, commit dates, or place orders without explicit confirmation.
- If due dates are vague (“tomorrow”, “Friday”), resolve them relative to the recording date when available; otherwise ask.

## Daily Briefing from Pocket

For “wrap my day” or daily briefing:

1. Pull today’s Pocket action items.
2. Pull today’s recordings/conversations.
3. Extract commitments, blockers, decisions, and risks.
4. Rank by operational risk:
   - customer dissatisfaction
   - job delay
   - missed revenue/change order
   - safety issue
   - crew/vendor confusion
5. Keep it short.

Briefing format:

```text
Pocket briefing — today

Highest risk:
- [Issue] — [why it matters] — [recommended next step]

Promises made:
- ...

Open follow-ups:
- ...

Tomorrow / scheduled:
- ...

Needs confirmation:
- ...
```

## Common Pitfalls

1. Using Pocket summaries only. Summaries can miss commitments; fetch transcript segments for important items.
2. Trusting speaker labels too much. Treat unknown speakers and noisy transcripts as uncertain.
3. Creating tasks without owner or due date. If missing, ask one short question or create a draft with “owner/due date needs confirmation.”
4. Over-fetching. Start with search to avoid dumping large transcripts into context.
5. Leaking credentials. Never print API keys or OAuth tokens.
6. Assuming localhost callback failure means auth failed. In chat-based OAuth, the failed localhost URL is usually the artifact the user must paste back.

## Verification Checklist

- [ ] OAuth URL was generated and sent to the user.
- [ ] User pasted back the full callback URL.
- [ ] Returned `state` matched the generated `state`.
- [ ] Token exchange succeeded.
- [ ] Pocket MCP tools listed successfully.
- [ ] Search or transcript retrieval was tested before claiming the integration works.
- [ ] Extracted commitments are presented as drafts unless confirmed.
