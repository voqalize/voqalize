---
title: Usage and limits
description: What Voqalize counts per billing period, how session duration is measured, the limits that apply today, and the one gap that tells you your embed is broken.
---

`get_usage(tenant, period="")` on [the MCP server](/reference/mcp/) returns one
tenant's counters for one billing period. `period` is `YYYY-MM` in UTC; empty
means the current month, and a period with no sessions returns zeros.

| Field | What it counts |
|---|---|
| `sessions_created` | Sessions minted by `sessions.connect`. |
| `sessions_started` | Sessions a user connected to. |
| `sessions_completed`, `sessions_failed` | Started sessions that ended cleanly, or on a failure. The rest of `sessions_started` are in progress or were never reported. |
| `duration_secs` | The usage quantity. |
| `agents` | The same numbers per agent, busiest first. |

## How duration is measured

`duration_secs` is Voqalize's own measurement of each session: from the moment
the user connected to the moment the session ended. A session nobody joined
counts zero. Silence inside a session counts, because the session is still
open; a user who stops talking has not ended it. The same span is what a
[recording](/operate/recordings/) runs for, so the counted time is the length of
the audio you can play back.

Voqalize is priced per conversation minute, and your LLM is billed separately by
its provider. Each plan's included minutes and rate are on the
[pricing page](https://voqalize.com/pricing).

## The gap that means a broken embed

`sessions_created` minus `sessions_started` is the sessions **nobody joined**.

A few are normal: someone opened the page and left. A wide gap is a broken embed
rather than a broken agent, and it is the number here worth an alert. The usual
causes:

- The page mints a session on load instead of on click.
- The `pk_` key's allowed origins reject the page's origin.
- The page's `connect` throws before the transport starts.

`list_sessions` with `state="expired"` shows the sessions behind the gap, and
[Reading a call back](/operate/reading-a-call/) shows how far each one got.

## Limits

| Limit | Value | What happens |
|---|---|---|
| Session length | 1 hour | The session ends with `end_reason` `max_duration`. A session still `active` five minutes past the hour reads `lost`. |
| MCP tool calls | 120 per minute, per tenant | The call fails with the tool error `Too many requests. Slow down and retry.` Back off and call again. |
| `sessions.connect` | Rate limited per tenant | A `429` with a `Retry-After` header, in seconds. Wait that long and retry. |
| `metadata` on a session | 10 keys, 256 characters per value | The request is refused. |

Concurrent sessions, included minutes and storage are set per plan. Ask us
before a launch that needs more than your plan carries, or if you need to know
your exact limits.

Poll with care: read a session when something happened to it, by its
`session_id`, rather than reading every session on a timer.

## Read next

- [Going to production](/operate/production/) — the checklist before launch.
- [Reading a call back](/operate/reading-a-call/) — the sessions behind the counters.
- [MCP server](/reference/mcp/) — `get_usage` and `list_sessions` in full.
