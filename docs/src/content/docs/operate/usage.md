---
title: Usage and limits
description: What Voqalize counts, how call duration is measured, and the one gap that tells you your embed is broken.
---

`get_usage(tenant, period="")` returns one workspace's counters for one billing
period. `period` is `YYYY-MM` in UTC; empty means the current month.

These are counters maintained as the calls happen rather than a scan of your
history, so the answer costs the same in a workspace's fortieth month as in its
first, and a period with no calls returns zeros rather than taking longer to say
so.

## The usage quantity

`duration_secs` comes from the **voice runtime's own measurement of the call** —
the time it actually held, not the span from when a token was minted. A session
that was created and never answered contributes zero.

Developer preview is free. Future paid pricing is planned per session minute,
with the developer's LLM billed separately by its provider; prices have not
been set. See [current status and supported environments](/overview/status/) for
what the planned minute includes.

`agents` breaks the same numbers down per agent, busiest first.

## The gap that tells you something

`sessions_created` minus `sessions_started` is the calls **nobody ever answered**:
a session was minted, and no caller ever connected to it.

A few of those are normal — someone opened the page and left. A wide gap is a
broken embed rather than a broken agent, and it is the one number here worth an
alert. The usual causes are a page that mints on load instead of on click, an
origin the `pk_` key's allowlist rejects at the offer, or a connect that throws
before the transport starts.

`list_sessions` shows the calls behind any number, and
[reading a call back](/operate/reading-a-call/) shows how far each one got.

## Limits

Every workspace has limits, including concurrent-call and API rate limits.
During developer preview they are set per workspace rather than published as a
tier table; no public concurrency number is committed. The preview also has no
availability guarantee. Ask before a pilot or launch that needs a specific
ceiling.

One is worth knowing about because it shapes how you poll: the management API is
rate limited per workspace. A dashboard that fires a burst of reads per page is
well inside it; a loop that reads every session every minute is not the shape to
build. Read a call when something happened to it, which is what the `session_id`
join is for.

## Read next

- [Reading a call back](/operate/reading-a-call/) — the calls behind the counters.
- [MCP server](/reference/mcp/) — `get_usage` and `list_sessions` in full.
