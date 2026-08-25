---
title: The RTVI plane
description: A whitelist of message types carried verbatim between your brain and your page. What crosses, what does not, and why the exclusions are the security property.
---

Your brain and your page talk to each other over RTVI, pipecat's own message
format, tunnelled through the Voqalize wire. A message is
`{id, label, type, data}` on the data channel; we carry the whitelisted types
verbatim in both directions and interpret nothing about them.

This is the second channel of a call. The first one is speech, and it holds the
floor; this one does not. See
[voice points, the screen holds](/design/voice-points-screen-holds/).

## The whitelist

The enumeration lives in `RTVIType` in
[`proto/voqalize/frames/frames.proto`](https://github.com/voqalize/voqalize/blob/main/proto/voqalize/frames/frames.proto),
which is the contract of record.

**Brain → page**

| Type | What it is |
|---|---|
| `server-message` | An unsolicited message to the app. |
| `server-response` | An answer to a message the app sent, quoting its `id`. |
| `error-response` | The same, when the answer is a failure. |
| `ui-command` | An [action](/design/voice-points-screen-holds/) — `{"command": …, "payload": {…}}`. |
| `ui-job-group` | Lifecycle envelopes for a group of jobs — started, update, completed — keyed by a shared `job_id`. |

**Page → brain**

| Type | What it is |
|---|---|
| `client-message` | Anything the app wants to tell the brain — a tap, a keystroke, a state push. |
| `send-text` | Text submitted into the conversation, carrying its own flags for whether to run it immediately and whether to answer aloud. |
| `ui-event` | A named event with an app-defined payload. |
| `ui-snapshot` | The page's accessibility tree, whole, each time. |
| `ui-cancel-job-group` | Cancel an in-flight job group, by its `job_id`. |

Only two of these have a Voqalize method behind them: `ui-command` is what
`session.dispatch` rides, and `client-message` is what most apps send back. The
rest of the `ui-*` family and `send-text` are pipecat's own, defined and
implemented by its client and its server-side workers; we carry them and
interpret nothing. The descriptions above are what pipecat's client does with
them, and pipecat's documentation is the authority on all five.

## What does not cross, and why that is the point

`bot-*` and `llm-*` are absent from both lists. They are the voice tier's own
assertions about the media and the model — that speech started, that the model is
thinking, that playout stopped — and a brain must not be able to forge one.

The consequence is worth stating positively: **your page can trust
`bot-started-speaking`**, because only the process that actually moved the audio
can emit it. A whitelist that let a brain send it would make every one of those
events a claim rather than a fact.

A type outside the whitelist does not cross in either direction. An envelope
carrying one comes back as `ERROR_CODE_REJECTED`, which is also what an oversized
message gets: the payload is bounded by the client's 64 KiB limit.

## From your brain

```python
session.send_rtvi(RTVIType.SERVER_MESSAGE, {"ready": True})
```

Never blocks, and callable from anywhere — inside a turn, or from work that
finished long after the turn that started it — because a message carries no audio
and so needs no floor.

Inside a turn it hits the wire in the order it runs, so it cannot jump ahead of
speech you already yielded. Sending a type the app originates raises before
anything reaches the socket.

`session.dispatch(action)` is sugar over the same method: it rides `ui-command`,
which a stock pipecat client reads with `useUICommandHandler` and no adapter of
ours.

## To your brain

```python
async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
    if msg.type is not RTVIType.CLIENT_MESSAGE:
        return
    ...
```

`on_rtvi` is **not a generator**, and that is deliberate. A click can update the
screen or end the call; it cannot make the agent start talking over the person
clicking, because nothing about a click means the human stopped speaking. There is
nothing to yield, so the rule needs no runtime check and cannot be broken.

To say something back, call `session.send_rtvi`.

## Correlation

RTVI's own `id` rides requests and the responses that name them. Quote it back
from the message you are answering, and the client's pending-request machinery
resolves.

Nothing else is correlated for you. `dispatch` is one-way — nothing is returned
and nothing is awaited — so a brain that needs an answer gets it the way it gets
every other tap: as an ordinary `client-message`, correlated by whatever your app
put in it. See [parallel workstreams](/design/parallel-workstreams/).

One field never reaches the app: `turn_id` annotates traces on the way out and is
stripped before delivery.

## Read next

- [Voqalize and pipecat](/start/pipecat/) — the browser packages that read these.
- [The wire](/reference/wire/) — the envelope RTVI is carried in.
