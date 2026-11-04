---
title: Context and history
description: What the user does in your app reaches the brain as typed app events at on_rtvi. How to declare them, what crosses in each direction, what session.init carries, and where history lives.
---

A voice agent that cannot see what the user just clicked talks past them. Your
page names what the user did, `on_rtvi` delivers it, and nobody's turn changes.
**Voqalize does not observe the screen**: nothing reads your DOM, store or
routes. Your app decides what to send, and your brain decides what to keep.

## Send the act, not the screen

An **app event** is one thing the user did, typed: `li3 quantity set to 5`.
Declare it the way you declare an [action](/build/brain/actions/), and its fields
are the payload:

```python
from voqalize.sdk import AppEvent, AppEvents, Brain, RTVIMessage, Session


class QuantitySet(AppEvent):
    item_id: str
    quantity: int


class RowRemoved(AppEvent):
    item_id: str


EVENTS = AppEvents(QuantitySet, RowRemoved)


class Desk(Brain):
    def __init__(self) -> None:
        self.cart: dict[str, int] = {}

    async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
        match EVENTS.parse(msg):
            case QuantitySet() as e:
                self.cart[e.item_id] = e.quantity
            case RowRemoved() as e:
                self.cart.pop(e.item_id, None)
```

The page sends it with pipecat's client, at the moment the user acts:

```ts
client.sendUIEvent("quantity_set", { item_id: "li3", quantity: 5 });
```

That is an RTVI `ui-event`. `EVENTS.parse` returns `None`, never an exception,
for a name it does not know, a payload that does not fit, or a message that is
not an event, so a page one deploy ahead of its brain cannot end a call. It also
reads the deprecated `client-message` with a `{ t, d }` payload (from pages built
on `sendClientMessage`) and warns once per process.

`voqalize types` generates the TypeScript for both directions from the same
module ([TypeScript types](/build/brain/typescript/)).

**Do not push whole-screen snapshots.** A snapshot names no change, so the brain
has to diff pictures and guess which act produced the difference, and a model
handed many snapshots reasons from whichever it notices. One named act needs no
diff. The trade: an act your page does not send is one your brain never learns
about.

## `on_rtvi` returns nothing and cannot speak

`async def on_rtvi(self, session, msg) -> None`. A tap can update context, drive
the screen or end the call, but it cannot start the agent talking, because a tap
does not mean the user stopped speaking. Put a `yield` in the body and the SDK
refuses the handler whole: it raises `WireError` into your log and runs none of
the body.

Everything else is a session method, callable from here:

```python
from voqalize.sdk import RTVIType

session.dispatch(ShowCart(items=list(self.cart)))                       # render
session.send_rtvi(RTVIType.SERVER_RESPONSE, {"ok": True}, id=msg.id)     # answer a request
session.end(reason="user tapped hang up")                               # hang up
```

Quote `msg.id` back when the message carried one: that resolves the page's
pending request.

**Each message is handled in its own task.** A barge-in does not cancel it, and an
exception in your handler is logged and contained. Handlers start in arrival
order, but one that awaits can be overtaken by the next, so fold state in with a
plain assignment and do slow work where order does not matter.

## What crosses, in each direction

| Direction | Types |
|---|---|
| Page to brain | `ui-event`, `ui-snapshot`, `ui-cancel-job-group`, and the deprecated `client-message` |
| Brain to page | `server-message`, `server-response`, `error-response`, `ui-command` (what `dispatch` sends), `ui-job-group` |

- **`send-text`** from the page is a typed sentence: it arrives as a user turn in
  `on_user_message`, never at `on_rtvi`.
- **`bot-*` and `llm-*` are on neither list.** Only Voqalize sends them, so your
  page can trust `bot-started-speaking`.
- **`session.send_rtvi` with a type you may not send** raises `WireError` before
  anything reaches the socket. A brain that sends one another way gets a
  non-fatal error at `on_error` ([error codes](/reference/errors/)), and the page
  gets nothing.

What each type is for: [RTVI messages](/reference/rtvi/).

## Where a message goes missing

- **Size.** An RTVI payload is limited to **64 KiB**. Pipecat's `sendUIEvent`
  throws above it in the browser. A brain-to-page message over it is refused with
  a non-fatal error; a page-to-brain message that gets through anyway is dropped
  with a log line.
- **Congestion.** When the outbound queue is full, speech chunks and RTVI messages
  are the frames shed, and `on_error` gets one non-fatal `OVERLOAD` per
  congestion episode per direction.

Make the current state **readable**, not only remembered: give the model a tool
that returns what is on screen now, from the state your `on_rtvi` handler already
holds. Mark it `@needs_result_now`, because the model reads it to answer this
turn ([Tools](/build/brain/tools/#mark-the-reads-the-model-needs-now)).

## `session.init`: send identifiers, not personal data

`session.init` is whatever your app passed as `init` in the
[`sessions.connect` body](/build/connect/), available before the first word:

```python
async def on_session_start(self, session: Session) -> None:
    self.customer_id = session.init.get("customer_id")
    self.history = await self.store.load(self.customer_id)
```

It is a `dict`, empty when the request carried no `init`, and the SDK never reads
a key of it. `on_session_start` runs before `greet`, so a greeting can be a
template over it.

:::caution[Send identifiers, not personal data, in `init`]
`init` is stored on the session record and returned to anyone who can read that
session. Pass ids (a customer id, an order id) and resolve them against your own
store, as above. [Status and support](/overview/status/) says what is stored and for
how long.
:::

The `sessions.connect` body is strict: an undeclared top-level key is a `422`
naming it, so a misspelled `init` fails loudly.

## History is yours

The SDK keeps no conversation store. History, model context and domain state
live in your process, on your schema:

| Callback | What to do there |
|---|---|
| `on_session_start` | Read your identifier from `session.init` and load your history. |
| `on_rtvi` | Fold in what the user did. |
| `on_finalize` | Write the turn back as what the user *heard* ([Transcripts and heard truth](/build/brain/transcripts/)). |

Everything you fold into context is re-read on every later turn, so append the
act, not the screen, and keep the rest in the store you already query.
Voqalize keeps the session record, events and recordings
([Reading a call back](/operate/reading-a-call/)).

## Read next

- [Transcripts and heard truth](/build/brain/transcripts/): what goes into history.
- [RTVI messages](/reference/rtvi/): the message list, type by type.
- [Misunderstanding and reversal](/design/#misunderstanding-and-reversal).
