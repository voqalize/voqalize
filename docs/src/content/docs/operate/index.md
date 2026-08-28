---
title: Operate
description: Inspect one call, retrieve its artifacts, and monitor usage and limits.
---

Use `session_id` to join the console, events, logs, optional recordings and your
own systems. Start with the affected call, then compare it with aggregate usage.

## Start with one call

Inspect these artifacts in order:

1. **Events** — what happened and when. The ordered spine of the call, and the
   only one of the three that is a contract.
2. **Logs** — Voqalize's own lines for that call, uploaded when it ends. Your
   brain logs in your environment; the `session_id` joins the two.
3. **The recording** — what it actually sounded like. Off by default.

[Reading a call back](/operate/reading-a-call/) walks all three.

## What persists, and what does not

- **Events** persist per session and are the durable record.
- **Logs** upload when the call ends, so a call in progress has none.
- **Recordings are off by default.** The agent carries a default; an authorized
  session creator can override it for a call.
- **Conversation history is yours.** We hold the call, not what your brain
  remembered about it.

During developer preview, retention is not configurable or guaranteed. See
[current status and supported environments](/overview/status/) before building
an archival or compliance workflow.

## The pages

| | |
|---|---|
| [Reading a call back](/operate/reading-a-call/) | Events, logs and recordings for one `session_id`. |
| [Recordings](/operate/recordings/) | Turning them on, and where they land. |
| [Usage and limits](/operate/usage/) | What is counted, and the gap that means a broken embed. |

## Debugging from your editor

The [MCP server](/reference/mcp/) puts all of it in your coding agent's hands —
list sessions, read a call back, check an agent's configuration, without leaving
the editor. It is the programmatic surface for all of it — there is no
bearer-key HTTP API beside it, and [the management
API](/reference/management-api/) explains why.

## Read next

- [Keys and authentication](/build/keys/) — rotation, and which key goes where.
- [Error codes](/reference/errors/) — what a code means and whether it was fatal.
