---
title: Reading a call back
description: The record says what happened and is contract. Logs say why and are evidence. Milestones say how far the call got. Read them in that order, and check availability before concluding a call was silent.
---

A call is over and something was wrong with it. There are three reads, they are
different kinds of thing, and the order matters.

**`get_call_record` is the contract.** Versioned, additive-only, tenant-scoped,
safe to assert on in a test. It answers *what happened*: what was said, what the
user actually heard, and where the wire was quiet.

**`get_session_logs` is the evidence.** Voqalize's own lines, written in
our vocabulary and free to change whenever our internals do. It answers *why*.

**`get_session_events` is the milestones.** Created, connected, ended — about
five of them, written *while the call runs*. It answers *how far the call got*,
and it is the one read that answers for a call still in progress.

Read the record first. Interleaving it with the logs would make the weaker half
look exactly as reliable as the stronger one, which is why they stay separate
reads.

All three are on [the MCP server](/reference/mcp/), and all three take the
`session_id` you already have — the same string that was in your connect params,
in `{brain_url}?session_id={session_id}`, and in every line your own brain logged.
It is the join key across both sides of the call.

## What the record contains

A **turn** is one question handed to your brain and everything your brain sent
back. Each carries:

- **`asked`** and **`asked_at`** — the question, verbatim, and when it was handed
  over. Empty on a greeting, or any turn your brain opened on its own; that is a
  real answer and is not filled in from the transcript.
- **`units`** — each stretch of speech your brain opened, with what it
  `generated`, what the user actually `heard`, and an `outcome`:

  | Outcome | Meaning |
  |---|---|
  | `spoken` | They heard all of it. |
  | `cut_short` | They heard the start and cut in. |
  | `never_spoken` | Your brain answered a turn they had already talked past, so not one word was said. |
  | `unknown` | The session ended before the unit settled. |

  `cut_short` and `never_spoken` are barge-in working, not faults. `never_spoken`
  is the **wasted work**, and the usual explanation for **"my brain replied and
  nothing happened on screen."** It used to be invisible — the frame simply did
  not appear. It appears now, marked as discarded. See
  [interruption and heard truth](/design/interruption-and-heard-truth/).
- **`gaps`** — stretches where your brain sent nothing. Named for what a record
  can see: a gap may be a model thinking, a tool running or a socket stalled, and
  nothing here tells them apart. It is *the wire was quiet*, never *the brain was
  slow*.
- **`marks`** — published measurements, each placed independently on the turn's
  own zero. `acked_at` is a protocol reflex and is not a response time.

`pace` is each measurement's spread across the session, with the number of turns
it was computed over. `meta` is what is true of the file itself, including
`closed_by`: `recovery` means the record was salvaged after the session's voice
died and may be incomplete.

`include_events=True` adds the raw records underneath the turns — every message
in both directions, which is a lot of them. `limit` bounds those and never the
turns. [The wire](/reference/wire/) names every message.

## What the milestones contain

`get_session_events` is Voqalize's own account of what it did: created,
something connected, it ended. None is ever dropped. Two payloads on
`session.created` answer most of "the call connected and nothing I expected
happened":

- **`recording_enabled` and `recording_source`** — whether this call was recorded
  and which rule decided. See [recordings](/operate/recordings/).

On calls placed before 2026-09-01 you may also see **`brain_url_defaulted`**. When
`true`, the agent had no `brain_url`, so a hosted `welcome` brain answered instead
of yours: the call worked, it greeted, it answered, and it was not your agent — a
working call in the wrong voice. No call since carries it, because an agent with
no brain is refused at `sessions.connect` rather than answered by us.

Each event carries `actor_id` — the raw id of what caused it — and `actor`, that
person as `{id, email, name}` when a person did it (a `terminate_session`, say)
and `null` when Voqalize itself did.

Because they are written during the call, the milestones are the cheap answer to
"how far did this call get" — and the only answer while it is still running.

## Check availability before you conclude anything

The record and the logs are each uploaded **when the call ends**. There is no
tail of a live call. So a read can come back empty for three different reasons,
and the response says which — `record` on `get_call_record`, `logs_availability`
on `get_session_logs`:

| Value | What it means |
|---|---|
| `found` | The file was read. |
| `missing` | No file at all — the call is still running, the voice tier died before teardown, or the upload failed. |
| `unavailable` | The store itself could not be read — or, for the record, the file is a version this control plane does not implement, which `detail` names. |

**An empty list is not the same fact as any of those**, and treating it as "the
call was silent" is the mistake this field exists to prevent. When the record is
`missing`, read the milestones: they say whether anything ever connected.

## Reading the logs

`get_session_logs` returns Voqalize's timeline for the call: WebRTC and ICE,
speech in and out, the brain WebSocket, teardown.

`level` is a floor — start at `INFO`, drop to `DEBUG` once you know roughly where
the problem is. `service` narrows to one surface: `service="pygato"` marks the
lines written by the process that holds the call, and it is the one worth
reading first. That string is an internal name — a log field, not vocabulary.
The other place you will meet it is the `iss` claim on the brain-connection
token, in [the wire](/reference/wire/).

Do not write assertions against their wording. That is what the record is
for.

## There is no general log search, on purpose

No free-text query, no arbitrary time range, no label explorer. Every read is
derived from a session you have already been authorized to see, and the object is
fetched by name under your own tenant's prefix. There is no user-supplied
predicate to get wrong, which is the failure mode a tenant-facing log API with a
query string eventually has.

## Your half is still yours

These are Voqalize's records of the call. Your brain runs in your environment and
logs where you put it. `session.id` is the same string on both sides, so joining
them is a grep — and your side is where `on_finalize` recorded what the user
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
