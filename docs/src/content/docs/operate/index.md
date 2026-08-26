---
title: Operate
description: Running it in production — reading one call back, what persists per session, and the counters that tell you the embed is broken.
---

In production you debug one call, not a system. Everything here is keyed by
`session_id`, and that is the join: the console, the logs, the recording and your
own systems all name a call the same way. Start with the call somebody complained
about and work outward.

## Start with one call

In this order, because each is cheaper than the next:

1. **Events** — what happened and when. The ordered spine of the call, and the
   only one of the three that is a contract.
2. **Logs** — Voqalize's own lines for that call, uploaded when it ends. Your
   brain logs in your environment; the `session_id` joins the two.
3. **The recording** — what it actually sounded like. Off by default.

[Reading a call back](/operate/reading-a-call/) walks all three.

## What persists, and what does not

- **Events** persist per session and are the durable record.
- **Logs** upload when the call ends, so a call in progress has none.
- **Recordings are off by default** and are turned on per agent.
- **Conversation history is yours.** We hold the call, not what your brain
  remembered about it.

## The pages

| | |
|---|---|
| [Reading a call back](/operate/reading-a-call/) | Events, logs and recordings for one `session_id`. |
| [Recordings](/operate/recordings/) | Turning them on, and where they land. |
| [Usage and limits](/operate/usage/) | What is counted, and the gap that means a broken embed. |

## Debugging from your editor

The [MCP server](/reference/mcp/) puts all of it in your coding agent's hands —
list sessions, read a call back, check an agent's configuration, without leaving
the editor. The [management API](/reference/management-api/) is the same surface
over HTTP.

## Read next

- [Keys and authentication](/build/keys/) — rotation, and which key goes where.
- [Error codes](/reference/errors/) — what a code means and whether it was fatal.
