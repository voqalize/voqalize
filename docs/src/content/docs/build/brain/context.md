---
title: Context and history
description: What the caller did in the app arrives as context, so the two of you work together rather than past each other. The reverse channel, and what your brain remembers.
---

A voice agent that cannot see what the caller just clicked is talking past them.
Your page pushes what it chooses to push, `on_rtvi` delivers it, and the floor
stays where it was. **We do not observe the screen.** Nothing on our side reads
your DOM, your store or your routes: your app decides what to send, and your
brain decides what to keep.

## The reverse channel

```python
from voqalize.sdk import (
    Brain, Chunk, RTVIMessage, RTVIType, Session, SpeechEnd, SpeechStart, UserMessage,
)


class Desk(Brain):
    def __init__(self) -> None:
        self.screen: dict = {}

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        if msg.type is not RTVIType.CLIENT_MESSAGE or not isinstance(msg.data, dict):
            return
        if msg.data.get("t") == "state_sync":
            self.screen = msg.data.get("d") or {}

    async def on_user_message(self, session: Session, msg: UserMessage):
        yield SpeechStart()
        yield Chunk(f"You are looking at {self.screen.get('page', 'nothing yet')}.")
        yield SpeechEnd()
```

The page half is one line, debounced to around 250 ms so a re-render does not
send a message per keystroke:

```ts
client.sendClientMessage("state_sync", { page: "cart", items: snapshot() });
```

`sendClientMessage(type, data)` is pipecat's own client method and it sends an
RTVI `client-message` whose payload is `{ t: type, d: data }` — which is why the
handler above reads `msg.data["t"]` and `msg.data["d"]`. Both halves of that
convention are yours: we carry the payload verbatim and interpret nothing in it.

## `on_rtvi` is not a generator

`async def on_rtvi(self, session, msg) -> None`. It returns nothing, and that is
the design rather than an omission: a tap can update context, drive the screen or
end the call, and it cannot make the agent start talking, because nothing about a
tap means the human stopped speaking. There is no channel for speech to leave by,
so the rule needs no runtime check.

Write a `yield` in the body anyway — Python decides from the source, so one
`yield` makes the whole function an async generator — and the SDK closes it
unstarted and raises `WireError` — into your brain's log, not into anything you
can catch, because nothing of yours called the handler. Not a byte of speech
reaches the wire, and the body's own bookkeeping does not happen either: a
contract violation is refused whole rather than half-honoured.
`tests/wire/test_rtvi_tunnel.py` drives that case over a real socket.

Everything a message *can* do is a method on the session, callable from here:

```python
session.dispatch(ShowCart(items=self.screen["items"]))   # render
session.send_rtvi(RTVIType.SERVER_RESPONSE, {"ok": True}, id=msg.id)  # answer
session.end(reason="user tapped hang up")               # hang up
```

See [actions](/build/brain/actions/) for the typed outbound half, and quote
`msg.id` back when the message carried one — that is what resolves the client's
pending request.

**Each message is handled in its own task, off the floor.** Two consequences you
can rely on: a barge-in cancels the turns through its watermark and does not
touch a message being handled, because a message carries no audio and nothing
about it is dead; and an exception in your handler is logged and contained, so
the session survives it. One consequence to design around: handlers begin in
arrival order, and a handler that awaits can be overtaken by the next one. Fold a
snapshot in with an assignment, and do the slow part where ordering does not
matter.

## What crosses, in each direction

The enumeration is `RTVIType` in
[`proto/voqalize/frames/frames.proto`](https://github.com/voqalize/voqalize/blob/main/proto/voqalize/frames/frames.proto),
split into two sets the SDK names `RTVI_TO_BRAIN` and `RTVI_TO_APP` in
`voqalize.sdk.wire.frames`.

Your page may send `client-message`, `send-text`, `ui-event`, `ui-snapshot` and
`ui-cancel-job-group`. Your brain may send `server-message`, `server-response`,
`error-response`, `ui-command` and `ui-job-group`. What each one is for is in
[the RTVI plane](/reference/rtvi/); `ui-command` is what `session.dispatch`
rides, and `client-message` is what most pages send back.

**`bot-*` and `llm-*` are on neither list.** They are the voice tier's own
assertions about the media and the model — that speech started, that playout
stopped — and a brain must not be able to forge one. State it positively: your
page can trust `bot-started-speaking`, because only the process that moved the
audio can emit it.

Two enforcement points, and they fail differently:

- `session.send_rtvi` with a type the app originates raises `WireError` before
  anything reaches the socket, naming the five types you may send.
- A brain that reaches the wire another way is refused there. Voqalize sends back
  a non-fatal error frame, which arrives at `on_error` (see
  [error codes](/reference/errors/)), and the page is sent nothing at all.

The same wall stands in the other direction: a type only Voqalize originates is
never lifted onto the wire from a page, so an app cannot make your brain believe
we said something.

## Where a message goes missing

An RTVI payload is bounded at **64 KiB** — the wire field and its semantics are
in [the wire](/reference/wire/). It is the limit the pipecat client enforces on
its own side: `sendClientMessage` throws there and fires `onError`,
and nothing reaches the wire. Over it, brain to page, the message is refused at
the wire and you get the non-fatal error frame. A page-to-brain message that gets
past the browser anyway is dropped on our side with a log line and nothing else,
because the page is not a wire peer and there is no error frame that reaches it.
Both refusals are bugs in the page rather than conditions your brain can act on.
That is the failure with no sound — the caller taps, the screen does nothing, and
on the next turn the agent answers about a screen that has moved.

Congestion sheds the same class of message. Speech chunks and RTVI messages are
the two unbounded flows on the wire, so they are the only two frames a full lane
drops; everything else is bounded by turns taken and units spoken and queues
however deep the backlog runs. A drop delivers one non-fatal `OVERLOAD` error to
`on_error` per congestion episode per direction, and the session is never killed
for it. If your context can go stale invisibly, send a whole snapshot each time
rather than a delta — a lost snapshot is corrected by the next one, and a lost
delta is wrong until the call ends.

## `session.init`

Whatever your app passed at connect, waiting on the session before the first
word:

```python
async def on_session_start(self, session: Session) -> None:
    self.customer_id = session.init.get("customer_id")
    self.history = await self.store.load(self.customer_id)
```

A `dict`, empty when the connect request carried no `init`, and the SDK never
reads a key of it. `on_session_start` runs before `greet`, so a greeting can be a
template over it.

**It is the same word on both ends, and that is the point.** `init` in the
`sessions.connect` body ([the browser half](/build/connect/)), `init` on the
wire, `session.init` in your brain. It used to be `agent_input` in the request,
`user_payload` at the token and `payload` on the claim — a different name at
every hop, none of them the one a developer reads. A renamed field goes on being
sent, the call still connects, and the session runs on defaults with nothing
anywhere saying so — which is why the request body is strict and an undeclared
key is a 422 naming it.

`init` is stored on the session record, returned to anyone who can read that
session, and it has no retention policy of its own. **Send identifiers, not
personal data**, and resolve them against your own store the way the snippet
above does.

## History is yours

The SDK holds no conversation store. `Session` owns exactly what dies with the
socket — the in-flight request ids — and stops there, because conversation
history, model context and domain state have a different lifetime and may outlive
the call. They are yours, in your process, on your schema.

That leaves you three places, and the split is the whole arrangement:

- **`on_session_start`** is where a logical conversation spanning several sockets
  picks up: read your own identifier out of `session.init` and load your own
  history. Nothing about it leaves your environment.
- **`on_rtvi`** is where what the caller did in the app folds in.
- **`on_finalize`** is where the turn is written back, and it must be recorded as
  what the caller *heard* — see [transcripts](/build/brain/transcripts/).

What we hold is the call while it is up, and the session record, events and
recordings afterwards; [reading a call](/operate/reading-a-call/) is how you get
them back.

One clock note before you grow the payload. Everything you fold into context is
read on every turn after this one, and paid for on every one of them: keep a
snapshot to the fields that change the answer, and let the rest live in the store
you already query.

## Read next

- [Actions](/build/brain/actions/) — the outbound half of the same channel.
- [Misunderstanding and reversal](/design/misunderstanding-and-reversal/).
- [The RTVI plane](/reference/rtvi/) — the whitelist, type by type.
