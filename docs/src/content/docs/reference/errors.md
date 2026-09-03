---
title: Error codes
description: Every code the wire can carry, what raises it, and whether the call survives it.
---

Every error code the wire can carry, what raises it, and whether the call
survives it. A code that ends the session and a code that rejects one request are
different failures, and the table says which is which — because the brain author
meets both at the worst possible moment.

There are five codes and they are the whole enum:

```python
from voqalize.sdk import ErrorCode

list(ErrorCode)
# [<ErrorCode.PROTOCOL: 'protocol'>, <ErrorCode.WIRE_VERSION: 'wire_version'>,
#  <ErrorCode.REJECTED: 'rejected'>, <ErrorCode.OVERLOAD: 'overload'>,
#  <ErrorCode.INTERNAL: 'internal'>]
```

## The five codes

| Code | Direction | Fatal | What raises it |
|---|---|---|---|
| `protocol` | Voqalize → brain | No | Your brain sent an RTVI type the app owns, or a payload over 64 KiB. |
| `wire_version` | brain → Voqalize | **Yes** | `SessionStart` carried a wire version this SDK does not speak. |
| `rejected` | — | — | Nothing that ships sends it. See below. |
| `overload` | minted locally | No | Your own SDK shed frames from a full lane. |
| `internal` | both | Sometimes | From Voqalize: a language change did not land on the recognizer. From your brain: `on_session_start` or `greet` raised. |

`fatal` is a separate field from the code, and it is the field that decides
whether the call ends. A fatal `Error` travelling brain → Voqalize cancels the
pipeline under the call; a non-fatal one is a signal your brain may act on and
nothing more.

Every code arrives in `on_error`, which is handed an `Error` with all three
fields:

```python
import logging

from voqalize.sdk import Brain, Error, ErrorCode

logger = logging.getLogger(__name__)


class Watchful(Brain):
    async def on_error(self, session, error: Error) -> None:
        if error.code is ErrorCode.OVERLOAD:
            logger.warning("session %s shed frames: %s", session.id, error.message)
        else:
            logger.error("session %s: %s %s", session.id, error.code, error.message)
```

Three of the five can reach that callback today — `overload`, `protocol` and
`internal` — and none of them arrives fatal, so `on_error` never has to end a
call. `wire_version` is one your own SDK *sends*, and `rejected` is sent by
nothing.

### `protocol`

Voqalize refuses one thing your brain sent. Three of the five sites are on the
RTVI plane: a type the app originates rather than the brain, a payload that will
not serialize to JSON, and a payload past the 64 KiB limit the browser's message
size imposes. The fourth is a `SpeechStart` carrying no `speech_id`, which names
nothing a `Finalize` could ever be matched against.

The fifth is **fatal, and it is the only one that is**: a `SpeechStart` whose
`speech_id` does not ascend. A repeated or out-of-order id means the two ends have
stopped agreeing on what a unit is — one `Finalize` would describe two pieces of
text with no way to tell which — so speech stops there and the session ends.
Units already open are still answered. The SDK raises `WireError` at the call site
first, so this reaches the wire only from a brain that speaks it directly.

For the other four the frame is dropped, the error comes back non-fatal, and the
turn continues.
The SDK catches the first of those before it reaches the socket — `send_rtvi`
raises `WireError` for a type outside the sendable set — so a `protocol` error
in your logs usually means an oversized payload. See
[The RTVI plane](/reference/rtvi/) for the whitelist and
[Actions](/build/brain/actions/) for keeping payloads small.

### `wire_version`

Voqalize speaks first, and the version it speaks is stamped on `SessionStart`.
If it is not the version your SDK speaks — in either direction, higher or lower —
the SDK emits a fatal `wire_version` error and ends the session before your
`greet` runs. Nothing has been synthesized at that point and the caller has heard
nothing, which is the only moment refusing is free.

You do not write this check and you cannot switch it off. A lower version is not
a subset of a higher one: the envelope arms it names may have been renumbered
underneath it, so guessing is exactly what a version number exists to prevent.
The current version and the rules for moving it are in
[The wire](/reference/wire/).

### `rejected`

**Nothing Voqalize or the SDK sends carries this code.** The two cases the wire
contract assigns to it — an RTVI type the brain may not send, and a payload over
the limit — both come back as `protocol` in the shipping code, and two tests in
the voice tier pin that. Handle `rejected` if you are writing directly against the
wire and want to be exhaustive over the enum; do not wait for it to arrive.

### `overload`

Your SDK holds two lanes per session, and the bulk lane defaults to 256 frames.
When it fills, the newest droppable frames are shed — speech chunks and RTVI
messages, the two unbounded flows — and a single non-fatal `overload` error is
delivered to `on_error` on the edge, rather than once per dropped frame.

This error never crosses the wire. It is minted inside your own process by the
session runner and handed to your own callback, which is why the message reads
`inbound queue full` or `outbound queue full`: it is telling you which side of
your brain is behind. A user message is never shed — it is bounded by turns
taken, so it queues however deep the backlog runs. The session is never killed
by a drop.

### `internal`

From Voqalize: a language change did not land on the recognizer — it refused the
language, it never acknowledged the change inside Voqalize's own wait, or its
socket was gone — so the session is still listening in the language it was.
The error names that language and is not fatal — the answer to your `configure`
already came back accepted, and this is the correction arriving behind it.

From your brain: `on_session_start` or `greet` raised. The SDK emits a **fatal**
`internal` error naming the hook, and ends the session without greeting. Both
halves of that are deliberate. A greeting spoken over state that was never built
promises a working agent the caller then talks to; a session whose greeting never
arrives is dead air on the one turn nothing will retry. The failure goes on the
wire instead, where the browser's `onError` shows it and the call ends.

A callback that raises **after** the session has opened does not do this. An
exception inside `on_user_message`, `on_user_idle`, `on_rtvi` or `on_finalize` is
logged in your process and goes no further: the turn stops producing, the socket
stays up, and the next turn runs. What the caller hears in that case is the last
section on this page.

## A rejected request comes back on the request

`RequestRejected` is not an `ErrorCode` and does not arrive at `on_error`. It is
raised by the `await` on the request that was refused, in the coroutine that made
it:

```python
import logging

from voqalize.sdk import Brain, Chunk, RequestRejected, SpeechEnd, SpeechStart
from voqalize.sdk.wire import Config, Language, SttConfig, TtsConfig

logger = logging.getLogger(__name__)


class Switcher(Brain):
    async def on_user_message(self, session, msg):
        yield SpeechStart()
        yield Chunk("Switching to Odia.")
        yield SpeechEnd()
        try:
            await session.configure(
                Config(
                    stt=SttConfig(language=Language.OR),
                    tts=TtsConfig(language=Language.OR),
                )
            )
        except RequestRejected as rejected:
            logger.info("configure refused: %s", rejected.detail)
            yield SpeechStart()
            yield Chunk("I will listen in Odia and answer in Hindi.")
            yield SpeechEnd()
            await session.configure(
                Config(
                    stt=SttConfig(language=Language.OR),
                    tts=TtsConfig(language=Language.HI),
                )
            )
```

Speak before you await. The `configure` is a round trip to Voqalize, and an
`await` with no speech in front of it is dead air the caller sits in.

**A rejection is all-or-nothing, and it is an answer rather than a broken
session.** Nothing in the request applied — a `Config` naming `tts`, `stt` and
`idle` at once moves all three or none — so on this exception the previous
settings are still in force and the call is still coherent. The socket is
healthy, the turn finishes, the next turn runs. `rejected.op` is the operation
name and `rejected.detail` is Voqalize's own sentence, written to be shown.

One refusal is worth planning for, and it is the reason this exception exists:
a `tts.language` the speech tier has no recorded clip for. Which languages have
clips changes as clips are recorded, so it is answered at the moment it is
asked rather than frozen into the wire contract. The ten that have one, and the
Odia-in-a-Hindi-clip configuration above, are in
[Voice and language](/reference/catalog/).

Two things that are *not* a `RequestRejected`:

- **A configuration the SDK can refuse for itself** raises `ConfigError` at the
  call site, before anything reaches the socket. Naming a language on one leg
  and not the other is the whole of that rule; it is a property of the message,
  so nothing has to be asked.
- **No answer at all** raises `TimeoutError` after 10 seconds, with a message
  saying that whether the change applied is unknown. The session lives.
  Accepted is answered before the change reaches the recognizer, so it means
  the configuration was legal and is being applied — never that the recognizer
  confirmed it. That correction arrives behind it, as an `internal` error.

## The two the SDK raises in your process

Neither of these crosses the wire. They are ordinary Python exceptions in the
process you deploy.

**`WireError`** — your brain broke one of its obligations. Almost always an
unbalanced bracket: a `Chunk` outside a speech unit, a `SpeechStart` inside an
open one, a `SpeechEnd` with nothing open. `send_rtvi` also raises it for a type
the app originates, and `on_rtvi` raises it if you wrote a `yield` anywhere in
the body, because a message from the app never takes the floor. Raised inside a
turn it is caught, logged and the turn dies; raised from `send_rtvi` it
propagates into your own code. The obligations are listed in
[Speaking](/build/brain/speaking/).

**`SessionRejected`** — the brain-connection token on the incoming socket failed
verification. `run_session` raises it before your brain is constructed, so no
session exists and no callback has run. Close the socket with code **4000**; the
wiring is in [Inbound server](/build/inbound/), and what the caller hears when
you do is below.

## Refused before your brain is dialled

Some failures end a call before there is a socket to report them on. Your brain
sees nothing at all — no `SessionStart`, no `on_session_end`, no log line — so
the place to look is the connect response the browser or your server got.

A session is minted by `sessions.connect`, and its status table is in
[Connect a browser](/build/connect/). One refusal is about the *agent*:

- **An agent with no brain cannot take a call.** If nobody has said how the agent
  is reached — no `brain_url`, and no Cortex credentials minted for it — the mint
  is a `409` with code `agent_not_configured`, before any quota is spent. Set a
  brain URL to run [inbound](/build/inbound/), or mint credentials to run
  [outbound over Cortex](/build/outbound/).

  This used to succeed. An unconfigured agent's empty `brain_url` was filled with
  a hosted `welcome` brain, so the call connected and your caller was greeted —
  by us, saying words you had never written. It worked, which is precisely what
  made it worth removing: a setup step you can skip without seeing anything break
  is a step that gets skipped.

Two more are about the session's configuration rather than the key:

- **The control plane parses `config` as canonical proto3 JSON.** An unknown
  field name, a wrong type, or a language the enum does not contain is a `400`
  with code `invalid_config`, naming the offending field. Nothing about the
  catalog is re-typed on that side; the message is proto's own.
- **Voqalize then runs the same validator your brain's `configure` goes
  through**, before it builds the pipeline, and answers the request that starts
  the media instead. The clip rule, the both-legs rule and the idle ceiling are
  one function with two callers, and a test pins that the two doors return the
  same sentence. So an unservable `tts.language` is a `400` when the page set it and a
  rejected response when your brain set it — same rule, same words, different
  door.

A refusal at either door happens before the session task starts, so the brain is
never dialled.

**There is no model field on the wire, and no free-text voice or language.**
`Config` names a voice and a language, both protobuf enums, and a value outside
them is refused by the decoder before it reaches anything that could substitute
for it. That absence is what makes a whole class of failure unreachable: your
brain cannot select an engine, cannot name a model, and cannot ask for a voice
that does not exist. The wire used to carry `voice`, `language` and `model` as
free-text strings, and a language with no recorded clip behind it was read in
the English clip's voice with nothing reporting it.

## What your caller hears

Nothing above describes the failure the way the person on the phone experiences
it. Voqalize speaks two fixed lines to the caller, off two thresholds, and these
are the only sentences it ever puts in your agent's mouth.

**A brain it could not reach.** Voqalize retries the first connect from 100 ms
out, and gives up after **10 seconds** — about as long as a person will hold a
silent line before deciding the thing is broken. Then the caller hears:

> Sorry — I can't reach the assistant right now. Please try again shortly.

Six seconds later the call ends. The line says nothing about *why*: your
`brain_url` never reaches a browser, so the diagnosis goes to your session events
instead. This is what plays when your service is down, when the URL has a typo in
it, when TLS fails — and when your own `run_session` raised `SessionRejected` and
you closed **4000**, which is read as permanent and stops the retries at once.

**A turn that produced no audio.** Once a committed user message has been sent to
your brain, Voqalize starts a **10-second** watchdog. If the turn has produced no
text by then, the caller hears:

> Sorry — that's taking longer than I expected.

The threshold is the same number as the connect deadline, for the same reason,
and it is bounded from below by a brain that is merely slow — a tool round trip
legitimately delays the first token by seconds, and speaking over one would
create the defect this prevents. **The session stays up.** Only this turn's
answer is missing; the socket is healthy and the next turn may be fine.

The watchdog is disarmed by the first chunk of text your brain sends for that
turn, and by a barge-in, and it is armed only by a user message. A `UserIdle`
never arms it — Voqalize opened that turn because the line went quiet, and a
brain that declines to fill a silence is behaving correctly.

Your brain is not told either line was spoken. Both are registered with the
aligner on the way out, so an answer that arrives late plays behind the apology
and its `Finalize` still carries your words and only your words. That is
deliberate: a brain learning that a sentence it never generated was said would be
new wire vocabulary for a fact it cannot act on, against a history already
degraded because the turn produced nothing.

**So this is what your caller hears when your brain is down**: a ten-second
silence, one apology, and — on the unreachable path — a call that ends six
seconds after it. Every callback that raises after the session opened lands in
the second line, because from Voqalize's seat a brain that raised, a brain
that returned empty and a brain that hung are the same thing: a turn with no
audio in it.

Finding out which one it was is a read of the session's events and logs.

## Read next

- [Reading a call back](/operate/reading-a-call/) — finding the failure afterwards.
- [The wire](/reference/wire/) — the frame that carries a code.
