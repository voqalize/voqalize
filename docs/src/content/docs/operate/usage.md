---
title: Usage and limits
description: What Voqalize counts, how session duration is measured, which limits apply, and the one gap that tells you your embed is broken.
---

`get_usage(tenant, period="")` returns one tenant's counters for one billing
period. `period` is `YYYY-MM` in UTC; empty means the current month.

These are counters maintained as the sessions happen rather than a scan of your
history, so the answer costs the same in a tenant's fortieth month as in its
first, and a period with no sessions returns zeros rather than taking longer to say
so.

## The usage quantity

`duration_secs` comes from **Voqalize's own measurement of the session** —
the time it actually held, not the span from when a token was minted. It runs
from the moment the call connects to the moment it ends. A session that was
created and never answered contributes zero.

That span is what a recording is cut to, so the number counted here is the
length of the audio you can play back. Silence inside a call is inside both: a
caller who stops talking has not ended the session, and the track carries those
seconds as silence.

Voqalize is priced per conversation minute, with the developer's LLM billed
separately by its provider. Each plan's included minutes and rate are on the
[pricing page](https://voqalize.com/pricing).

`agents` breaks the same numbers down per agent, busiest first.

## The gap that tells you something

`sessions_created` minus `sessions_started` is the sessions **nobody ever joined**:
a session was minted, and no user ever connected to it.

A few of those are normal — someone opened the page and left. A wide gap is a
broken embed rather than a broken agent, and it is the one number here worth an
alert. The usual causes are a page that mints on load instead of on click, an
origin the `pk_` key's allowlist rejects at the offer, or a connect that throws
before the transport starts.

`list_sessions` shows the sessions behind any number, and
[reading a call back](/operate/reading-a-call/) shows how far each one got.

## Limits

Concurrent sessions, included minutes and storage are set by your plan; the
[pricing page](https://voqalize.com/pricing) lists each plan's allowance. Talk to
us before a launch that needs more than a plan carries.

A session lasts at most one hour: the voice tier ends it at the hour with
`end_reason` `max_duration`. A session still `active` five minutes past the hour
reads `lost`, because the voice tier never reported how it ended.

The MCP server is rate limited per tenant, which shapes how you poll. A refused
request is a `429` with a `Retry-After` header; wait that long and send it
again. A dashboard that fires a burst of reads per page is well inside it; a
loop that reads every session every minute is not the shape to build. Read a session when something happened to it, which is what the `session_id`
join is for.

## Read next

- [Reading a call back](/operate/reading-a-call/) — the sessions behind the counters.
- [MCP server](/reference/mcp/) — `get_usage` and `list_sessions` in full.
