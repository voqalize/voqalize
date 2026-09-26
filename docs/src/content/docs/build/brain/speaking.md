---
title: Speaking
description: Speech is the only thing you yield. The frames that carry it, why a turn is many units, and what streaming buys the user.
---

Speech is the only thing `on_user_message` yields, because speech is the only
thing with a position on the audio timeline. You yield `SpeechStart()`, one or
more `SpeechChunk(text)`, then `SpeechEnd()` — and Voqalize speaks the first sentence
while you are still producing the last. Everything that is not speech is a
method on `session`.

## `SpeechStart`, `SpeechChunk`, `SpeechEnd`

```python
from voqalize.sdk import Brain, SpeechChunk, SpeechEnd, SpeechStart

class Concierge(Brain):
    async def on_user_message(self, session, msg):
        yield SpeechStart()
        yield SpeechChunk("You said: " + msg.text)
        yield SpeechEnd()
```

`SpeechStart()` opens a **speech unit** and binds it to the turn you are
answering. `SpeechChunk(text)` carries text inside the open unit. `SpeechEnd()` closes
it. The SDK mints the unit's id and stamps the turn on it, so you write neither.

Yield anything else — an action, a bare string, a dict — and the SDK raises
`WireError` rather than putting it on the wire. So does an unbalanced bracket:
a `SpeechChunk` outside a unit, a `SpeechStart` inside an open one, a
`SpeechEnd` with nothing open. The rule the errors enforce is that every unit
you open closes exactly once, and the
[conformance harness](/build/testing/) checks it against your brain over the
real wire.

Behaviours you get for free:

- **A unit left open by a crash is closed on the wire.** If your generator
  raises mid-unit, the SDK emits the missing `SpeechEnd` rather than leaving
  Voqalize waiting for a chunk that is never coming.
- **On a barge-in the generator is closed, not abandoned**, so your `finally`
  blocks run. Nothing is emitted for the dead unit.

**SpeechChunk boundaries carry no meaning of their own.** Voqalize re-segments the text
for synthesis (`proto/voqalize/frames/frames.proto`, `message SpeechChunk`), so
split where your model splits and do not buffer to build tidy sentences.
`SpeechChunk("")` puts nothing on the wire.

`greet` is the one place you do not write the brackets. It returns a string
rather than yielding, and the SDK wraps that string into exactly one unit on
turn 1.

## A turn is many units

One call to `on_user_message` may open and close the floor several times:

```python
async def on_user_message(self, session, msg):
    yield SpeechStart()
    yield SpeechChunk("Let me check that.")
    yield SpeechEnd()

    rows = await self.catalog.search(msg.text)

    yield SpeechStart()
    yield SpeechChunk(f"I found {len(rows)}.")
    yield SpeechEnd()
```

Two units, one turn. Write it as one unit spanning the `await` and Voqalize
reports both back as one `Finalize` — the filler and the answer become a single
entry in your history, under a single heard prefix.

**The unit is the grain of everything downstream.** It is what a user can be
cut out of mid-word, and it is what Voqalize reports heard truth against — one
`Finalize` per unit that produced audio, never a concatenation across units. So
a unit opens on the first thing you actually say and closes when you stop:

- speech either side of a wait — a database query, a marked tool's second
  request — is two units, because the user can interrupt between them and
  Voqalize needs somewhere to stop
  (`test_speech_either_side_of_a_tool_is_two_units` in
  `sdk/python/tests/contract/test_brain_contract.py`);
- a response that only calls a tool opens no unit at all. An empty
  `SpeechStart`/`SpeechEnd` pair around a silent tool call owes Voqalize a
  finalize for a unit nobody heard, and every finalize after it lands on the
  wrong unit for the rest of the call (`test_a_silent_hop_opens_no_unit`, in the
  same file).

Both shipped adapters are written this way. `GeminiBrain.respond` makes a unit
of **one model response**: it opens lazily on the first spoken text and closes on
the response's `finish_reason`, or when its stream ends
(`sdk/python/src/voqalize/sdk/gemini.py`, `respond`). A tool it calls mid-response
runs between two pieces of the same unit, so a line, a call and a second line in
one response are one unit, and the tool has to be quick —
[Tools](/build/brain/tools/#a-tool-returns-within-20-ms) has the budget. Two units
come from two responses: a tool marked `@needs_result_now` makes the model answer
again, and that answer is a unit of its own.

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
user, sitting through a database query with the floor held by nobody.

So say something before you await, and mean it:

```python
async def on_user_message(self, session, msg):
    yield SpeechStart()
    yield SpeechChunk("Pulling that up now.")
    yield SpeechEnd()

    booking = await self.crm.fetch(msg.text)   # 400 ms, or 4 seconds

    yield SpeechStart()
    yield SpeechChunk(f"Your booking is {booking.reference}.")
    yield SpeechEnd()
```

An `await` with no speech in front of it is dead air you chose. On `GeminiBrain`
the SDK writes this shape for a tool marked `@needs_result_now`: the model's
line is the first unit and its answer from the result is the second. The first
line is still the model's to say, so it belongs in the prompt —
[Tools](/build/brain/tools/#when-the-model-reads-a-result) has what a response
that calls a tool and says nothing sounds like. Work that can
start early should start early — see
[parallel workstreams](/design/#parallel-workstreams) — and what a tool costs the
turn is [tool design for voice](/design/#tool-design-for-voice).

## Why speech is a yield and not a return

A generator lets audio start before your model has finished.

Voqalize aggregates the chunks of an open unit and hands each completed sentence
to the speech tier as it forms, rather than waiting for `SpeechEnd`. So the first
syllable is spoken at the first sentence boundary in the text you have yielded so
far. Stream from your model and the user's ear and your model's output run
concurrently; build the whole reply and `return` it, and the user pays for the
generation in silence first and then hears the same words.

```python
async def on_user_message(self, session, msg):
    yield SpeechStart()
    async for piece in self.model.stream(msg.text):   # your client, your model
        yield SpeechChunk(piece)
    yield SpeechEnd()
```

Nothing in a transcript distinguishes those calls. The words are identical,
the recording is not, and the number that moved is
[time to first chunk](/design/#the-turn-budget).

The corollary is worth knowing before it bites: text with no sentence boundary in
it waits. A unit that is one long unpunctuated clause is synthesized when
`SpeechEnd` flushes it, however early you yielded the chunks.

The generator also buys a place to stop. When the user cuts in,
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

## What the user heard is not what you sent

A unit you generated in full and the user cut after four words is four words in
their memory of the call. Voqalize reports that back per unit, after playout, at
`on_finalize` — long after the generator that produced it returned. Record the
delivered prefix rather than what you yielded:
[transcripts and heard truth](/build/brain/transcripts/).

## Read next

- [Actions](/build/brain/actions/) — the channel that does not speak.
- [The turn budget](/design/#the-turn-budget) — how long a unit may be.
- [Interruption and heard truth](/design/#interruption-and-heard-truth).
