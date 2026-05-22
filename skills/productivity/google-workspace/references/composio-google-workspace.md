# Composio MCP as a Google Workspace backend

Use this reference when the user asks for Gmail, Calendar, Google Tasks, or Google Drive access but the local Google Workspace skill is not authenticated, or when the user explicitly wants to use Composio.

Important setup fallback: if Composio MCP is blocked before OAuth by a Cloudflare managed challenge / 403 from `https://connect.composio.dev/mcp`, the Google app tools will not be reachable through Composio yet. Do not keep trying app-tool calls. Have the user complete Composio setup from a regular browser/terminal environment that can pass the challenge, or fall back to the direct Google OAuth setup in `SKILL.md` when immediate access matters.

## General Composio workflow

1. Call `COMPOSIO_SEARCH_TOOLS` for the specific task. Preserve the returned `session_id` in every later Composio meta-tool call.
2. Check toolkit connection status in the search result. Google apps use separate toolkit slugs; do not assume one authorization covers the others:
   - Gmail: `gmail`
   - Calendar: `googlecalendar`
   - Tasks: `googletasks`
   - Drive: `googledrive`
3. If a toolkit is not ACTIVE, call `COMPOSIO_MANAGE_CONNECTIONS` with the exact toolkit slug and show the returned auth link. Then call `COMPOSIO_WAIT_FOR_CONNECTIONS` before any app tool execution.
4. Fetch schemas with `COMPOSIO_GET_TOOL_SCHEMAS` when needed. Never invent app tool argument names.
5. Execute app tools with `COMPOSIO_MULTI_EXECUTE_TOOL`; use remote workbench only for large saved responses or bulk processing.
6. Treat OAuth callback URLs, auth codes, tokens, and state parameters as secrets. Do not preserve them in notes or summaries.

## Gmail triage

For "check my Gmail / recent messages / what needs my attention":

- Default to read-only. Do not send, reply, mark read, archive, or label without explicit confirmation.
- Use `GMAIL_FETCH_EMAILS` metadata-first: `include_payload=false`, `verbose=false`, reasonable `max_results`, and a bounded query such as `in:inbox newer_than:7d` or `is:unread in:inbox newer_than:30d`.
- Sort by `messageTimestamp` / internal date client-side; Gmail results may not be ordered by recency.
- Paginate only when needed; stop when `nextPageToken` is absent or empty.
- Shortlist likely attention items: direct human requests, questions, deadlines, scheduling, security/account alerts, billing/payment/domain renewal, failed CI/security scans, or other explicit "action required" subjects.
- Deprioritize newsletters, promotions, social digests, receipts, and automated marketing unless they include security/payment/deadline language.
- Hydrate only the shortlist with `GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID` or thread fetch if the snippet is insufficient.
- Final answer: sender, subject, date/time, why it matters, suggested action, and a brief "likely no action" summary.

## Calendar checks

For "anything on my calendar this afternoon / today / that I need to prep for":

- Calendar requires the `googlecalendar` toolkit connection even if Gmail is connected.
- Use `GOOGLECALENDAR_GET_CURRENT_DATE_TIME` to anchor local time when available; if the user's timezone is already known, a local `date` command with `TZ=<IANA timezone>` is an acceptable anchor for read-only checks.
- Use `GOOGLECALENDAR_EVENTS_LIST_ALL_CALENDARS` when available. If the search plan returns `GOOGLECALENDAR_LIST_CALENDARS` + `GOOGLECALENDAR_EVENTS_LIST`, list calendars first and query selected calendar IDs such as `primary` and any selected calendars.
- For `GOOGLECALENDAR_EVENTS_LIST`, use bounded RFC3339 local-offset windows (`timeMin` / `timeMax`), `singleEvents=true`, `showDeleted=false`, and `orderBy="startTime"`. Use the calendar's local timezone offset, not UTC `Z`, for local-day windows.
- Start with minimal detail where supported; hydrate/get full details only for ambiguous prep needs.
- Check both `summary_view` and `events` / `items`; minimal responses may put usable rows in `summary_view`.
- For "this afternoon," compute a local-time bounded window such as noon-6pm. If the current time is late afternoon and the window is empty, also check now-through-midnight before saying there is nothing later today.
- Watch for synced-calendar duplication: Office 365 or other sync bridges can create many duplicate Google events with the same title/time. Deduplicate by title + start + end before briefing the user, and mention likely sync duplication if obvious.
- Final answer should include timezone and window checked. If events exist, list title, time, location/conference link if available, prep needs, and gaps/conflicts. If empty, say no events were found in the selected calendars/window.

## Google Drive verification and search

For "can you see my Google Drive / verify Drive access / find recent Drive files":

- Drive requires the `googledrive` toolkit connection even if Gmail/Calendar/Tasks are connected.
- Start with `COMPOSIO_SEARCH_TOOLS` for the exact Drive task and preserve the returned `session_id`.
- For simple read-only verification, use `GOOGLEDRIVE_GET_ABOUT` and/or `GOOGLEDRIVE_FIND_FILE` with a small `pageSize` and minimal `fields` such as `files(id,name,mimeType,modifiedTime,webViewLink)`.
- For recent file snapshots, query `trashed = false` and sort with `orderBy="modifiedTime desc"` when the query does not use `fullText`. Avoid broad `*` fields unless the user explicitly needs rich metadata.
- If shared drives matter, use `corpora="allDrives"`, `includeItemsFromAllDrives=true`, and `supportsAllDrives=true` (the Composio tool defaults may already do this, but be explicit when troubleshooting empty results).
- If results are unexpectedly empty, widen the query or check shared drives before concluding Drive is inaccessible.
- Never create, upload, delete, move, or share Drive files without explicit user confirmation. For destructive operations, show file name, ID, action, and reversibility first.
- Final verification answer can be brief: say whether Drive access works, which account/toolkit was active if available, and list a few recent file names/types/timestamps without exposing unnecessary document contents.

## Google Tasks review

For "any Google Tasks that need my attention":

- Tasks requires the `googletasks` toolkit connection even if Gmail/Calendar are connected.
- Use `GOOGLETASKS_LIST_ALL_TASKS` to avoid missing tasks from non-default lists.
- Prefer `showCompleted=false` and a conservative `dueMax` (end-of-day or near-future) to reduce payload. If the user asks broadly for all attention items, also consider undated open tasks if payload size allows.
- Normalize `due` timestamps to the user's/calendar timezone before grouping. Google Tasks due dates can appear as RFC3339 UTC timestamps at midnight; avoid off-by-one-day classifications.
- Preserve `tasklist_id` and `tasklist_title` in the output.
- Final answer should group by overdue, due today, upcoming soon, and optionally undated/actionable. Include title, task list, due date, and suggested next action.
- Never mark complete, edit, delete, move, or create tasks without explicit user confirmation.
