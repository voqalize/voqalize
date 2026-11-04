---
title: Speaking
description: Speech is the only thing you yield. The frames that carry it, why a turn is many units, when Voqalize acknowledges for you, and how to stop your own speech.
---

You yield `SpeechStart()`, one or more `SpeechChunk(text)`, then `SpeechEnd()`,
and Voqalize starts speaking while you are still producing the rest. Everything
that is not speech is a method on `session` ([Your first brain](/build/brain/)).

## Open, fill and close a speech unit

```python
from voqalize.sdk import Brain, SpeechChunk, SpeechEnd, SpeechStart


class Concierge(Brain):
    async def on_user_message(self, session, msg):
        yield SpeechStart()
        yield SpeechChunk("You said: " + msg.text)
        yield SpeechEnd()
```

`SpeechStart()` opens a **speech unit** (one stretch of speech the user can cut
into, and the grain Voqalize reports what was heard against) and binds it to the
turn you are answering. `SpeechChunk(text)` carries text inside the open unit.
`SpeechEnd()` closes it. The SDK mints the unit's id and stamps the turn, so you
write neither.

The SDK raises `WireError` instead of sending:

- anything else you yield: an action, a bare string, a dict;
- an unbalanced bracket: a `SpeechChunk` outside a unit, a `SpeechStart` inside
  an open one, a `SpeechEnd` with nothing open.

Every unit you open closes exactly once. A unit you
[cancelled](#stopping-your-own-speech) counts as closed. The
[conformance harness](/build/testing/) checks this over the real wire.

What you get for free:

- **A crash mid-unit still closes the unit.** If your generator raises, the SDK
  sends the missing `SpeechEnd`.
- **A barge-in closes your generator**, so your `finally` blocks run. Nothing
  more is sent for the dead unit.
- **Chunk boundaries carry no meaning.** Voqalize re-segments the text for
  synthesis, so split where your model splits and do not buffer into tidy
  sentences. `SpeechChunk("")` sends nothing.

`greet` is the one place you write no brackets: it returns a string, and the SDK
wraps it into one unit on turn 1.

## A turn can be several units

One call to `on_user_message` may open and close several units:

```python
async def on_user_message(self, session, msg):
    yield SpeechStart()
    yield SpeechChunk("The blue one is out of stock.")
    yield SpeechEnd()

    rows = await self.catalog.similar(msg.text)

    yield SpeechStart()
    yield SpeechChunk(f"I found {len(rows)} like it.")
    yield SpeechEnd()
```

Open a unit on the first thing you actually say, and close it when you stop:

- **Speech either side of a wait is two units.** The user can interrupt between
  them, and each gets its own `Finalize` with its own heard text. Written as one
  unit spanning the `await`, both lines become one history entry under one heard
  prefix.
- **A step that says nothing opens no unit.** An empty `SpeechStart`/`SpeechEnd`
  pair around a silent tool call still owes a `Finalize`, and if your pairing
  code forgets it, every finalize after it lands on the wrong unit.

The shipped model brains (`GeminiBrain`, `OpenAIBrain`, `LiteLLMBrain`) make one
unit per model response: opened on the first spoken text, closed when the
response ends. A tool called mid-response runs between two pieces of that unit,
which is why it must be quick ([Tools](/build/brain/tools/#a-tool-returns-within-20-ms)).

## Voqalize covers the wait before your first word

With **ack** on (the default), Voqalize says a short acknowledgement such as
"Sure." or "Let me check." when the user's turn ends, before your reply begins.
So:

- **Do slow work before you first speak, and open on the answer.**
- **Never add a filler line of your own** ("Let me check", "Pulling that up"):
  the user would hear two.
- **When a turn calls a tool, say the substantive line in the same response as
  the call**: what you are doing or showing. [Tools](/build/brain/tools/#speak-first-and-call-in-the-same-response)
  owns that rule.

```python
async def on_user_message(self, session, msg):
    booking = await self.crm.fetch(msg.text)   # 400 ms, or 4 seconds

    yield SpeechStart()
    yield SpeechChunk(f"Your booking is {booking.reference}.")
    yield SpeechEnd()
```

### Turn ack off when your brain writes its own

A brain whose replies open with their own acknowledgement turns ack off. It
applies from the next turn, so do it in `on_session_start`:

```python
from voqalize.sdk import Brain
from voqalize.sdk.wire import AckConfig, Config


class MyBrain(Brain):
    async def on_session_start(self, session):
        await session.configure(Config(ack=AckConfig(enabled=False)))
```

Acknowledgements are said only in the languages Voqalize has a vocabulary for.
[Voice and language](/build/voice-and-language/) covers the rest of the session
settings.

### The ten-second line

If a user turn produces no text for ten seconds, Voqalize says a line of its
own, *"Sorry — that's taking longer than I expected."*, and keeps the session
up. The timer starts when the user's turn is committed and stops at **your first
chunk** (not when a unit opens). It runs only for a user message, not for an
idle turn.

After your first chunk nothing covers a wait. An `await` between units is
silence you chose, so the line before it has to carry something, as "The blue
one is out of stock." does above. Work that can start early should
([parallel workstreams](/design/#parallel-workstreams)).

## Stream, so speech starts before generation ends

Voqalize does not wait for `SpeechEnd`: it starts speaking once it has a
sentence. Stream from your model and the user hears the first sentence while the
model writes the rest; build the whole reply first and the user waits through
the generation in silence.

```python
async def on_user_message(self, session, msg):
    yield SpeechStart()
    async for piece in self.model.stream(msg.text):   # your client, your model
        yield SpeechChunk(piece)
    yield SpeechEnd()
```

Text with no sentence boundary waits, so one long unpunctuated clause is spoken
only when `SpeechEnd` flushes it. Streaming also gives a barge-in somewhere to
stop: the SDK closes your generator at the `yield` it is on, and your model
stops producing a reply nobody is hearing. The number this moves is
[time to first chunk](/design/#the-turn-budget).

## Decline the floor with no `yield`

```python
async def on_user_idle(self, session, idle):
    if idle.level >= 3:
        session.end(reason="idle")
```

A body with no `yield` is an ordinary coroutine, and the SDK runs it either way.
`on_user_idle` says nothing by default.

## Stopping your own speech

A guardrail that checks output beside the stream decides a beat after the text
went out. `cancel_speech` stops the unit where playout has got to, drops the
rest, and returns what the user heard:

```python
from voqalize.sdk import Brain, SpeechChunk, SpeechEnd, SpeechStart


class Guarded(Brain):
    async def on_user_message(self, session, msg):
        start = SpeechStart()
        yield start                                   # the SDK writes start.speech_id
        async for piece in self.model.stream(msg.text):
            if session.can_cancel_speech and await self.guardrail.flags(piece):
                await self.model.stop()               # Voqalize can only drop what it is sent
                fin = await session.cancel_speech(start.speech_id)
                self.history.append(fin.heard)        # what was said, not what was generated
                yield SpeechStart()
                yield SpeechChunk("Let me put that another way.")
                yield SpeechEnd()
                return
            yield SpeechChunk(piece)
        yield SpeechEnd()
```

Keep the `SpeechStart` you yield: the SDK writes the unit's id onto it, and that
id is what you cancel. The call returns the unit's `Finalize` (the same one
`on_finalize` then receives).

- **The turn stays open.** This is not a barge-in: open a new unit and it plays.
  A cancelled unit needs no `SpeechEnd`, and anything you yield for it afterwards
  is dropped.
- **`heard` is accurate to about one word.** Audio already on its way still
  plays, so assume one word more than `heard` may have been heard.
- **A cancel that lost the race returns at once** with the unit's `Finalize`,
  nothing cut. A second cancel does the same.
- **Check `session.can_cancel_speech` first.** Without it the SDK raises
  `Unsupported` before sending. An id this session never opened raises
  `ValueError`. No `Finalize` within ten seconds raises `TimeoutError`, and the
  unit still counts as open, so close it with `SpeechEnd`.
- **The cut stops every unit still playing or queued**, not only the one you
  named. Each gets its own `Finalize`. A unit you open after the cancel is
  unaffected.

Call it from the turn, from `on_rtvi` or from your own task, but not from
`on_finalize`: that hook runs in line with incoming frames, so the `Finalize` it
would wait for is queued behind it.

## Read next

- [Transcripts and heard truth](/build/brain/transcripts/): record what the user heard.
- [Actions](/build/brain/actions/): the channel that does not speak.
- [The turn budget](/design/#the-turn-budget): how long a unit may be.
