---
title: RTVI messages
description: A whitelist of message types carried verbatim between your brain and your page. What crosses, what does not, and why the exclusions are the security property.
---

Your brain and your page talk to each other over RTVI, the message format they
share over the session's data channel, tunnelled through the Voqalize wire. A
message is `{id, label, type, data}`; Voqalize carries the whitelisted types
verbatim in both directions and interprets nothing about them — with one
deliberate exception, [`send-text`](#send-text-is-a-turn-not-a-message), which
becomes a user turn rather than arriving as a message.

This is the second channel of a call. The first one is speech, and it holds the
floor; this one does not. See
[voice points, the screen holds](/design/#voice-points-the-screen-holds).

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
| `ui-command` | An [action](/build/brain/actions/) — `{"command": …, "payload": {…}}`. |
| `ui-job-group` | Lifecycle envelopes for a group of jobs — started, update, completed — keyed by a shared `job_id`. |

**Page → brain**

| Type | What it is |
|---|---|
| `ui-event` | A named event with an app-defined payload — one gesture the person made. |
| `client-message` | The older untyped envelope, `{t, d}`. **Deprecated.** Still carried and still parsed, so a page already built on `sendClientMessage` keeps working; new pages send `ui-event`. |
| `ui-snapshot` | The page's accessibility tree, whole, each time. |
| `ui-cancel-job-group` | Cancel an in-flight job group, by its `job_id`. |

`ui-command` and `ui-event` are the ones with a Voqalize method behind them:
`ui-command` is what `session.dispatch` rides, and `ui-event` is what
`AppEvents.parse` reads. The rest of the `ui-*` family has no Voqalize method:
the client sends and receives them, and Voqalize carries them and interprets
nothing. Your page sends `ui-snapshot` with `client.startUISnapshotStream()` and
`ui-cancel-job-group` with `client.cancelUIJobGroup(jobId)`, and receives
`ui-job-group` as `RTVIEvent.UIJobGroup`.

## `send-text` is a turn, not a message

`send-text` is the exception, and it is the reason the sentence above says
"verbatim" everywhere except here. A person typing a question
is not clicking: it is the same stimulus speaking is, and it takes the floor the
same way. So `send-text` never reaches your brain as a message.

```js
client.sendText("where do I download my interest certificate?");
```

Voqalize interrupts whatever the agent was saying — the answer to the last
question is over — and commits the sentence as a user turn. Your brain answers it
in `on_user_message`, with no way to tell it was typed and nothing to write to
receive it: a brain built before you added a text box gains one the day you add
it.

`run_immediately` and `audio_response` ride `send-text` and **neither
is honoured**, deliberately rather than by omission. `run_immediately=false` would need a stimulus that is
stored without minting a turn, and `audio_response=false` would need a per-turn
gate on synthesis; Voqalize has neither. **A typed question is answered aloud,
always.**

An empty submission mints nothing — it is dropped where it arrives rather than
travelling as a turn that says nothing.

## What Voqalize tells your page

Voqalize sends your page one `server-message` of its own, and your brain never
sees it: how well the user's audio is reaching Voqalize.

```json
{ "label": "rtvi-ai", "type": "server-message",
  "data": { "type": "network-quality", "quality": "poor" } }
```

`quality` is one of these, best first:

| `quality` | What it means for the call |
|---|---|
| `good` | Nothing to say. |
| `fair` | Audio is being lost and repaired before anyone hears it. The call sounds normal. |
| `poor` | Some audio did not arrive, or arrives slowly. Expect slower replies and the odd misheard word. |
| `bad` | Long stretches of audio are missing. Expect the agent to miss what was said. |

It is sent only when the grade changes, and never at the start: until the first
one arrives, the call is `good`. A worse grade arrives at once; a better one comes
back a step at a time, after the network has held there for a while, so a brief
burst of loss doesn't make it flicker.

What the user is told, if anything, is yours to decide. A banner at `poor`, a
"we lost you for a moment" at `bad`, or nothing at all. The word is all Voqalize sends:
the measurements behind it can change as Voqalize is tuned.

```js
client.on(RTVIEvent.ServerMessage, (data) => {
  if (data?.type === "network-quality") showNetworkBanner(data.quality);
});
```

## What does not cross, and why that is the point

`bot-*` and `llm-*` are absent from both lists. They are the voice tier's own
assertions about the media and the model — that speech started, that the model is
thinking, that playout stopped — and a brain must not be able to forge one.

The consequence is worth stating positively: **your page can trust
`bot-started-speaking`**, because only the process that actually moved the audio
can emit it. A whitelist that let a brain send it would make every one of those
events a claim rather than a fact.

A type outside the whitelist does not cross in either direction, and the
payload is bounded by the client's 64 KiB limit:

| Sent by | Outside the whitelist, or over 64 KiB |
|---|---|
| Your brain | Dropped, and your brain gets a non-fatal `ErrorCode.PROTOCOL` [error](/reference/errors/#protocol). The call continues. |
| Your page | Dropped. Nothing is sent back. |

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
which the client reads with `useUICommandHandler`.

## To your brain

```python
async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
    match EVENTS.parse(msg):
        case QuantitySet() as e:
            ...
```

`AppEvents.parse` is the typed reader — it takes both envelopes and returns
`None` for anything it does not know. See [context](/build/brain/context/).

`on_rtvi` is **not a generator**, and that is deliberate. A click can update the
screen or end the call; it cannot make the agent start talking over the person
clicking, because nothing about a click means the human stopped speaking. A
`yield` in its body is refused with `WireError` and none of the handler runs
([Context and history](/build/brain/context/#on_rtvi-returns-nothing-and-cannot-speak)).

To say something back, call `session.send_rtvi`.

## Correlation

RTVI's own `id` rides requests and the responses that name them. Quote it back
from the message you are answering, and the client's pending-request machinery
resolves.

Nothing else is correlated for you. `dispatch` is one-way — nothing is returned
and nothing is awaited — so a brain that needs an answer gets it the way it gets
every other tap: as an ordinary `ui-event`, correlated by whatever your app put
in it. See [parallel workstreams](/design/#parallel-workstreams).

One field never reaches the app: `turn_id` annotates traces on the way out and is
stripped before delivery.

## Read next

- [Client libraries](/build/client/): the browser packages that read these.
- [The wire](/reference/wire/): the envelope RTVI is carried in.
