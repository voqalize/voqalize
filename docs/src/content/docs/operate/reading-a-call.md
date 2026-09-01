---
title: Reading a call back
description: Events say what happened and are contract. Logs say why and are evidence. Read them in that order, and check availability before concluding a call was silent.
---

A call is over and something was wrong with it. There are two reads, they are
different kinds of thing, and the order matters.

**`get_session_events` is the contract.** Versioned, additive-only, tenant-scoped,
safe to assert on in a test. It answers *what happened*.

**`get_session_logs` is the evidence.** The voice runtime's own lines, written in
our vocabulary and free to change whenever our internals do. It answers *why*.

Read events first. Interleaving the two would make the weaker half look exactly as
reliable as the stronger one, which is why they stay separate reads.

Both are on [the MCP server](/reference/mcp/), and both take the
`session_id` you already have — the same string that was in your connect params,
in `{brain_url}?session_id={session_id}`, and in every line your own brain logged.
It is the join key across both sides of the call.

## What the event stream contains

Two sources, merged chronologically.

`source="platform"` — Voqalize's own milestones, written *during* the call:
created, connected, ended. Two payloads on `session.created` answer most of "the
call connected and nothing I expected happened":

- **`recording_enabled` and `recording_source`** — whether this call was recorded
  and which rule decided. See [recordings](/operate/recordings/).

On calls placed before 2026-09-01 you may also see **`brain_url_defaulted`**. When
`true`, the agent had no `brain_url`, so a hosted `welcome` brain answered instead
of yours: the call worked, it greeted, it answered, and it was not your agent — a
working call in the wrong voice. No call since carries it, because an agent with
no brain is refused at `sessions.connect` rather than answered by us.

`source="wire"` — the frames themselves, both directions, between Voqalize and
your brain. Transcripts, each piece of the agent's reply, each action it asked the
page to take, each interruption. This is the same wire your brain speaks; see
[the wire](/reference/wire/).

Passing `source="platform"` skips the wire read entirely, which is what makes "how
far did this call get" a cheap question.

## The disposition field usually settles the argument

Every wire event carries what actually happened to that frame:

| Disposition | Meaning |
|---|---|
| `sent` | The bytes left for your brain. Recorded after a confirmed send, so it never claims a frame the socket dropped. |
| `received` | Decoded from your brain and pushed into the pipeline. |
| `dropped_after_watermark` | Your brain answered a turn the caller's barge-in had already killed. A real answer, correctly thrown away. |
| `dropped_after_barge_in` | A unit released mid-stream; the rest of its words are not relayed, because nothing downstream can attribute them. |

Those last two are the usual explanation for **"my brain replied and nothing
happened on screen."** It is correct behaviour rather than a bug, and it used to be
invisible — the frame simply did not appear. It appears now, marked as discarded.
Filtering the wire half by `disposition` is the fastest way to see everything one
barge-in threw away. See
[interruption and heard truth](/design/interruption-and-heard-truth/).

`frame` narrows the same half by type, named exactly as it appears on the wire
(`VqlUserTextFrame`, `VqlLLMTextFrame`, `VqlFunctionCallsStartedFrame`).

## Check availability before you conclude anything

Both halves are uploaded as **one bundle when the call ends**. There is no tail of
a live call. So a read can come back empty for four different reasons, and the
response says which:

| Value | What it means |
|---|---|
| `found` | The bundle was read. |
| `missing` | No bundle at all — the call is still running, the voice tier died before teardown, or the upload failed. |
| `unavailable` | The store itself could not be read. |
| `skipped` | You asked for `source="platform"`. |

**An empty list is not the same fact as any of those**, and treating it as "the
call was silent" is the mistake this field exists to prevent. `platform` events are
never truncated; `limit` applies to the wire half only.

## Reading the logs

`get_session_logs` returns Voqalize's timeline for the call: WebRTC and ICE,
speech in and out, the brain WebSocket, teardown.

`level` is a floor — start at `INFO`, drop to `DEBUG` once you know roughly where
the problem is. `service` narrows to one surface: `service="pygato"` marks the
lines written by the process that holds the call, and it is the one worth
reading first. That string is an internal name — a log field, not vocabulary.
The other place you will meet it is the `iss` claim on the brain-connection
token, in [the wire](/reference/wire/).

Do not write assertions against their wording. That is what the event stream is
for.

## There is no general log search, on purpose

No free-text query, no arbitrary time range, no label explorer. Every read is
derived from a session you have already been authorized to see, and the object is
fetched by name under your own workspace's prefix. There is no user-supplied
predicate to get wrong, which is the failure mode a tenant-facing log API with a
query string eventually has.

## Your half is still yours

These are Voqalize's records of the call. Your brain runs in your environment and
logs where you put it. `session.id` is the same string on both sides, so joining
them is a grep — and your side is where `on_finalize` recorded what the caller
actually heard.

The join only works if your lines carry the id, and **the SDK has already put it
there**: both entry points wrap every session in a logging context, so a bare
`from loguru import logger` anywhere in your brain — and in any task it spawns —
logs with the call attached. You thread nothing through.

What is left to you is one line at your own entrypoint, because a library has no
business replacing your process's log handlers:

```python
from voqalize.sdk import configure_logging

configure_logging(json_logs=True)     # only if you have no loguru setup of your own
```

Without a sink that prints those fields, they are computed and thrown away, and
it looks exactly like working. If you already configure loguru, add `{extra}` to
your format instead. Signatures and the rest are in
[The Brain API](/reference/brain/#logging).

**Ids are carried whole.** A truncated id reads better in a terminal and matches
nothing on our side of the query, which is the entire purpose of writing it down.

## Read next

- [Recordings](/operate/recordings/) — when the events and the logs both look right and the call still sounded wrong.
- [MCP server](/reference/mcp/) — every tool's signature.
