---
title: Speaking
description: Speech is the only thing you yield. The three frames, why a turn is many units, and what streaming buys the caller.
---

Speech is the only thing `on_user_message` yields, because speech is the only
thing with a position on the audio timeline. You yield `SpeechStart()`, one or
more `Chunk(text)`, then `SpeechEnd()` — and Voqalize speaks the first sentence
while you are still producing the last. Everything that is not speech is a
method on `session`.

## The three frames

```python
from voqalize.sdk import Brain, Chunk, SpeechEnd, SpeechStart

class Concierge(Brain):
    async def on_user_message(self, session, msg):
        yield SpeechStart()
        yield Chunk("You said: " + msg.text)
        yield SpeechEnd()
```

`SpeechStart()` opens a **speech unit** and binds it to the turn you are
answering. `Chunk(text)` carries text inside the open unit. `SpeechEnd()` closes
it. The SDK mints the unit's id and stamps the turn on it, so you write neither.

Yield anything else — an action, a bare string, a dict — and the SDK raises
`WireError` rather than putting it on the wire. So do three shapes of unbalanced
bracket: a `Chunk` outside a unit, a `SpeechStart` inside an open one, and a
`SpeechEnd` with nothing open. The rule the errors enforce is that every unit
you open closes exactly once, and the
[conformance harness](/build/testing/) checks it against your brain over the
real wire.

Two behaviours you get for free:

- **A unit left open by a crash is closed on the wire.** If your generator
  raises mid-unit, the SDK emits the missing `SpeechEnd` rather than leaving
  Voqalize waiting for a chunk that is never coming.
- **On a barge-in the generator is closed, not abandoned**, so your `finally`
  blocks run. Nothing is emitted for the dead unit.

**Chunk boundaries carry no meaning of their own.** Voqalize re-segments the text
for synthesis (`proto/voqalize/frames/frames.proto`, `message SpeechChunk`), so
split where your model splits and do not buffer to build tidy sentences.
`Chunk("")` puts nothing on the wire.

`greet` is the one place you do not write the brackets. It returns a string
rather than yielding, and the SDK wraps that string into exactly one unit on
turn 1.

## A turn is many units

One call to `on_user_message` may open and close the floor several times:

```python
async def on_user_message(self, session, msg):
    yield SpeechStart()
    yield Chunk("Let me check that.")
    yield SpeechEnd()

    rows = await self.catalog.search(msg.text)

    yield SpeechStart()
    yield Chunk(f"I found {len(rows)}.")
    yield SpeechEnd()
```

Two units, one turn. Write it as one unit spanning the `await` and Voqalize
reports both back as one `Finalize` — the filler and the answer become a single
entry in your history, under a single heard prefix.

**The unit is the grain of everything downstream.** It is what a caller can be
cut out of mid-word, and it is what Voqalize reports heard truth against — one
`Finalize` per unit that produced audio, never a concatenation across units. So
a unit opens on the first thing you actually say and closes when you stop:

- speech either side of a tool call is two units, because the caller can
  interrupt between them and Voqalize needs somewhere to stop
  (`sdk/python/tests/contract/test_brain_contract.py:120`);
- a hop that only calls a tool opens no unit at all. An empty
  `SpeechStart`/`SpeechEnd` pair around a silent tool call owes Voqalize a
  finalize for a unit nobody heard, and every finalize after it lands on the
  wrong unit for the rest of the call
  (`sdk/python/tests/contract/test_brain_contract.py:110`).

Both shipped adapters are written this way — `GeminiBrain.respond` opens a unit
lazily on the first spoken text and closes it on the model's `finish_reason`,
once per hop (`sdk/python/src/voqalize/sdk/gemini.py:189`).

## The clock between units is yours

Voqalize arms one watchdog per committed user turn. If that turn produces no
**text** for ten seconds, Voqalize speaks a line of its own — *"Sorry — that's
taking longer than I expected."* — and leaves the session up. The watchdog is
disarmed by **the first chunk of that turn**, not by the unit opening, and it is
armed only for a user message: an idle turn you decline to fill is a brain
behaving correctly and gets no line.

That is the whole guarantee, and its edge is the thing to design around. Once
your first chunk is out, the turn is unwatched. Silence between unit one and
unit two is invisible: there is no error, no dropped frame, no failed check, and
your logs show a turn that answered. The only instrument that sees it is the
caller, sitting through a database query with the floor held by nobody.

So say something before you await, and mean it:

```python
async def on_user_message(self, session, msg):
    yield SpeechStart()
    yield Chunk("Pulling that up now.")
    yield SpeechEnd()

    booking = await self.crm.fetch(msg.text)   # 400 ms, or 4 seconds

    yield SpeechStart()
    yield Chunk(f"Your booking is {booking.reference}.")
    yield SpeechEnd()
```

An `await` with no speech in front of it is dead air you chose. Work that can
start early should start early — see
[parallel workstreams](/design/parallel-workstreams/) — and what a tool costs the
turn is [tool design for voice](/design/tool-design/).

## Why speech is a yield and not a return

A generator lets audio start before your model has finished.

Voqalize aggregates the chunks of an open unit and hands each completed sentence
to the speech tier as it forms, rather than waiting for `SpeechEnd`. So the first
syllable is spoken at the first sentence boundary in the text you have yielded so
far. Stream from your model and the caller's ear and your model's output run
concurrently; build the whole reply and `return` it, and the caller pays for the
generation in silence first and then hears the same words.

```python
async def on_user_message(self, session, msg):
    yield SpeechStart()
    async for piece in self.model.stream(msg.text):   # your client, your model
        yield Chunk(piece)
    yield SpeechEnd()
```

Nothing in a transcript distinguishes those two calls. The words are identical,
the recording is not, and the number that moved is
[time to first chunk](/design/turn-budget/).

The corollary is worth knowing before it bites: text with no sentence boundary in
it waits. A unit that is one long unpunctuated clause is synthesized when
`SpeechEnd` flushes it, however early you yielded the chunks.

The second thing the generator buys is a place to stop. When the caller cuts in,
the SDK closes your generator at the `yield` it is sitting on, so your model stops
producing a reply nobody is listening to any more. A body that builds the whole
string and returns it has already finished by then, and there is nothing left to
stop.

## A callback that decides not to speak

Declining the floor is a real answer, and the natural way to write it has no
`yield` in it:

```python
async def on_user_idle(self, session, idle):
    if idle.level >= 3:
        session.end(reason="idle")
```

Python decides generator-or-coroutine from the source, so that body is an
ordinary coroutine however it is annotated. The SDK runs it either way. Leave the
`yield` out when you have nothing to say; `on_user_idle` says nothing by default.

## What the caller heard is not what you sent

A unit you generated in full and the caller cut after four words is four words in
their memory of the call. Voqalize reports that back per unit, after playout, at
`on_finalize` — long after the generator that produced it returned. Record the
delivered prefix rather than what you yielded:
[transcripts and heard truth](/build/brain/transcripts/).

## Read next

- [Actions](/build/brain/actions/) — the second channel, which does not speak.
- [The turn budget](/design/turn-budget/) — how long a unit may be.
- [Interruption and heard truth](/design/interruption-and-heard-truth/).
