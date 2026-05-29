# Pocket MCP OAuth Notes

Pocket MCP endpoint: `https://public.heypocketai.com/mcp`.

Pocket supports both API-key headers and OAuth. For SiteKick-style users on Telegram or another chat interface, prefer OAuth when possible because users should not have to copy API keys into chat.

## User-facing OAuth paste-back pattern

1. Start an OAuth-capable MCP connection to the remote Pocket MCP server.
2. Capture the generated authorization URL.
3. Send that URL to the user in chat with short instructions:
   - Open the link.
   - Approve Pocket access.
   - If the browser lands on a `localhost` URL that does not load, that is expected.
   - Copy the full resulting `http://localhost:.../oauth/callback?code=...&state=...` URL and paste it back into the chat.
4. Feed the pasted callback URL back into the waiting OAuth flow.
5. Verify the MCP tools load before claiming the integration is connected.

## Pocket tools observed in docs

- `get_pocket_conversation`: fetch full transcripts for specific recordings, including transcript segments and signed audio URLs.
- `search_pocket_conversations`: semantic + keyword search over conversation sections.
- `search_pocket_conversations_timerange`: fetch transcripts in a date range, sorted by recency.
- `search_pocket_actionitems`: search action items by status, priority, category, due date, and source recording date.

## Construction-operations handling

When using Pocket transcripts or action items for SiteKick work:

- Treat extracted action items as drafts until an authorized user confirms them.
- Extract commitments, owner, job/customer, due date, urgency, source recording, and confidence.
- Flag uncertain transcript details instead of turning them into facts.
- Offer follow-up actions: create task, reminder, calendar event, customer draft, crew/subcontractor message, or job note.

## API-key fallback

If OAuth is not available in the current client, Pocket accepts static auth headers:

```yaml
mcp_servers:
  pocket:
    url: "https://public.heypocketai.com/mcp"
    headers:
      Authorization: "Bearer pk_your_api_key_here"
```

Use API-key fallback only when OAuth is unavailable or explicitly requested.