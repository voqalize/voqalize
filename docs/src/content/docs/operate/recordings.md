---
title: Recordings
description: Off by default, decided per call, one audio track per side. Who is allowed to turn recording on, and why a publishable key is not.
---

Recording is **off by default** and is decided for each call, at the moment the
session is minted. Most calls have none, and an empty list from `get_recordings`
is a real answer rather than a missing one.

## Who decides

The client developer's explicit `record` wins in both directions, because they are
the only party who knows whether *this* caller consented. They can turn it off for
an agent that records by default just as easily as on.

| What the mint request says | What happens |
|---|---|
| `record: true` | Recorded |
| `record: false` | Not recorded, whatever the agent's default says |
| omitted | The agent's configured default, which itself defaults to off |

Omitting the field is how "let the agent decide" is spelled. It is a different
thing from `false`, and the distinction is the whole reason the field is nullable.

## One asymmetry, and it is about which key you hold

**A publishable (`pk_`) key may turn recording off. It may not turn it on.**

A `pk_` key ships in page source, so "the client developer" on that path is
whoever can read the page. Turning recording *off* needs no trust — opting out of
being recorded never does. Turning it *on* would let a stranger write voice into
your bucket, on your bill, for an agent whose owner chose not to record.

That refusal is an HTTP `400` with code `recording_not_permitted`, and it starts no
call. It used to be a silent fallback to the agent default, which meant a page
asking to record could "work" by coincidence whenever the owner had already turned
recording on — and then quietly not work the day they turned it off. A request
that can only ever be a no-op is a bug in the page, and it should be found on the
page's first run rather than by an auditor looking for a call nobody recorded.

A `pk_` embed that wants recording sets the **agent's** default, which its owner
controls: `update_agent(recording=true)` over
[the MCP server](/docs/reference/mcp/), or the same switch in the console.

See [keys and authentication](/docs/operate/keys/).

## What you get back

`get_recordings(tenant, session_id)` returns one track **per side**: `role` is
`user` (the caller's microphone) or `agent` (what was spoken back).

Two tracks rather than one mix is the point. Listening to them separately
distinguishes "the agent said nothing" from "the agent was never asked anything" —
which a mixed track cannot tell you, and which is the first question worth asking
about a call that went quiet.

Each track carries its state, duration, size, content type, and a
`failure_reason` if it has one.

## The download URL is a credential

A track in state `completed` carries a `download_url`: a short-lived signed URL you
fetch with a plain unauthenticated `GET`.

It carries its own credential, so treat it as a secret. Do not write it anywhere
durable — not a ticket, not a log line, not a spreadsheet. `ttl_seconds` sets its
lifetime between 60 and 900 seconds, defaulting to the maximum. Fifteen minutes is
long enough to download and short enough that a leaked URL is dead by the time
anyone finds it.

Ask for a fresh one rather than holding one.

## Which rule decided, after the fact

The call's `session.created` event carries `recording_enabled` and
`recording_source` — `client` when the mint request said so, `agent_default` when
it did not. That is how you answer "why was this call not recorded" without
guessing. See [reading a call back](/docs/operate/logs/).

`get_session` also carries the same recordings without URLs, for when you only
need to know whether any exist.

## Read next

- [Reading a call back](/docs/operate/logs/) — events first, logs second, audio last.
- [Keys and authentication](/docs/operate/keys/) — why the key you hold changes what you may ask for.
