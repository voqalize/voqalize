---
title: Transcripts and heard truth
description: Your history holds what the caller heard, not what you intended to say. Where the finalized text comes from and where the record lives.
---

A reply that generated three sentences and was cut after one is remembered as
one. At the end of each speech unit Voqalize tells your brain what the caller
actually **heard**, and that — not what your model produced — is what belongs in
history. Get this wrong and the next turn argues with the caller about something
they were never told.

## `on_finalize`, once per unit, after playout

```python
async def on_finalize(self, session: Session, fin: Finalize) -> None:
    ...
```

`Finalize` carries three fields and one thing derived from two of them:

| Field | What it is |
|---|---|
| `heard` | The delivered prefix of that unit's text — what reached the caller's ear. |
| `generated` | The text you emitted for that unit, kept by the SDK so you need not. |
| `speech_id` | The unit this reports on. |
| `interrupted` | `heard != generated`. `True` when the caller talked over it, `False` when it played to its end. |

`heard` is a verbatim prefix of `generated`, which is what makes `interrupted` a
comparison rather than a claim: equal means the unit played out, shorter means it
was cut off, and empty against a unit that sent text means nothing reached the
ear. Voqalize used to send the verdict alongside the evidence and no longer does
— a second copy of a derivable fact is one more thing that can disagree.

`speech_id` correlates and does nothing else. Take one from
`session.next_speech_id()`, name the unit with it, and it comes back here on that
unit's finalize — which is how the pairing below works.

The callback fires **after playout**, which is long after the generator that
produced the unit returned. The turn is over when the generator returns; it does
not wait for the audio. So there is no point in your generator's `finally` where
what was heard is known yet, and the record is written here or nowhere.

Four guarantees a brain can be written against:

- **Exactly one finalize per bracket you opened.** Enrolment happens at
  `SpeechStart`, not at the first `Chunk`, so a unit you opened and closed with
  no text in it is reported too — as `heard=""` against `generated=""`, which
  reads as complete, because nothing was cut.
- **They arrive in the order the units opened**, oldest first. Pair by id
  anyway: order is a property of today's runtime, and an id is a property of the
  unit.
- **A unit the caller never heard is still reported**, as `heard=""` against the
  text you generated. Generated ahead of playout and beaten to the speaker.
- **A finalize naming an id you never opened is speech you did not generate.**
  `greet` returns a string the SDK speaks for you, so this callback is the only
  record of it that exists — skip it and your model does not know it greeted, and
  opens a second time. A line you yielded yourself arrives the same way.

## Pair a finalize with the unit that produced it

Enrol a unit **where you yield `SpeechStart`** — the same line, so the queue and
the wire cannot disagree. Then a plain FIFO is enough: the n-th finalize belongs
to the n-th bracket you opened.

The other half is to **open no bracket you have nothing to say in**. A hop that
only calls a tool is what the model did, not something it said; open a unit for
it and you have bought a finalize you must account for. So the `SpeechStart`
below is lazy — it waits for the first non-empty piece — and the unit is enrolled
on the adjacent line, so the record and the wire cannot disagree about which unit
is which.

```python
from voqalize.sdk import Brain, Chunk, Finalize, Session, SpeechEnd, SpeechStart, UserMessage


class Concierge(Brain):
    def __init__(self) -> None:
        self.history: list[dict[str, str]] = []
        # Units awaiting their heard truth, by the id they were opened under.
        self._awaiting: dict[int, dict[str, str]] = {}

    async def on_user_message(self, session: Session, msg: UserMessage):
        self.history.append({"role": "user", "text": msg.text})

        unit: dict[str, str] | None = None
        async for piece in self.model.stream(self.history):
            if not piece:                       # never sent, so it opens nothing
                continue
            if unit is None:
                unit = {"role": "assistant", "text": ""}
                self.history.append(unit)
                speech_id = session.next_speech_id()
                self._awaiting[speech_id] = unit
                yield SpeechStart(id=speech_id)
            unit["text"] += piece
            yield Chunk(piece)
        if unit is not None:
            yield SpeechEnd()

    async def on_finalize(self, session: Session, fin: Finalize) -> None:
        unit = self._awaiting.pop(fin.speech_id, None)
        if unit is None:                        # speech you did not generate here
            if fin.heard:                       # the greeting, already heard-truth
                self.history.append({"role": "assistant", "text": fin.heard})
            return
        if fin.heard:
            unit["text"] = fin.heard
        else:                                   # nobody heard it, so it is not a turn
            self.history = [c for c in self.history if c is not unit]
```

**Match by id, not by position.** A queue popped oldest-first reads an unmatched
finalize as "this must be the greeting", and that is only true while nothing else
speaks. Yield a line of your own — a filler while a tool runs — and its finalize
pops the model's unit instead, rewriting a sentence the model generated and
leaving its reasoning signature attached to text it never produced. Keyed, an id
you never opened matches nothing, and the model's turn is untouched.

Both shipped adapters are built this way, and the contract suite asserts it
against every brain we ship — including the tool-only hop that must leave the
record untouched, and a finalize arriving out of order. The conformance driver
answers silent brackets too, so a brain that opens one and forgets to enrol it
fails there rather than in a call — see [testing a brain](/build/testing/).

**Keep the callback short.** Frames are dispatched one at a time, so a database
round-trip in `on_finalize` delays the callbacks queued behind it, including the
next `on_user_message`. Write into memory here and flush from your own task. An
interruption rides a priority lane and overtakes everything queued, but not the
callback already running — one consumer, one frame at a time — so a two-second
write here is two seconds of a dead turn still generating.

## The correction only ever shortens

`heard` is bounded by that unit's own `generated` text, and expressed in that
unit's own characters. Voqalize can hand you back less than you sent, down to
nothing at all, and can never hand you back more. That bound is what the
`interrupted` comparison rests on.

That bound is a mechanism rather than a promise. No label survives the speech
path to say which text belonged to which unit, so Voqalize does not carry one: it
holds the text it relayed, in order, and walks the played-back text through it
with a cursor that only moves forward. A word that matches nothing at the cursor
is skipped and counted in the session's own logs. Alignment drift therefore
degrades into a number you can read back rather than into a history you cannot.

Two things follow, and they are the reason to build on this:

- **A finalize can never put words in your model's mouth.** Everything between
  your chunks and the speaker — normalization, segmentation, the synthesis
  itself — can change what a listener hears and cannot change what you are told
  you said. The worst case is a turn recorded shorter than it was played.
- **One unit's finalize can never carry another unit's words.** A cross-unit
  concatenation is unrepresentable, so the FIFO pairing above cannot silently
  drift onto the wrong turn.

The interruption watermark is one-way in the same spirit: Voqalize sends the
newest dead turn, the SDK raises its own mark to it, and it is never lowered,
never acknowledged, never echoed. A brain that misses one is corrected by the
next.

**An interruption does not cancel the finalizes you are owed.** The turn's task
is cancelled and its generator closed, and every bracket it had already opened
is still reported — as the prefix that played, or as `heard=""`. That is what
makes `on_finalize` the one place the record is written.

## What a wrong record costs on the next turn

Record what you generated and the next turn is planned against a version of the
call that never happened. The model refers back to a sentence it did not finish,
re-uses a number the caller never got, or declines to repeat something it
believes it already covered.

Nothing downstream can tell. Your model's output is a plausible record of what it
meant to say, your transcript agrees with your logs, your evals pass, and no
error, dropped frame or latency spike marks the moment it went wrong. The one
artifact that disagrees is the [recording](/operate/recordings/), and nobody
plays the recording of a call that went fine. The full argument is in
[interruption and heard truth](/design/interruption-and-heard-truth/).

## What the caller said

`msg.text` in `on_user_message` is the recognizer's **committed** transcript for
one turn. Nothing partial reaches a brain — there is no interim-transcript frame
on the wire — so the text you are handed does not move under you, and a turn's
text may be several commits joined into the one message.

Endpointing decides where that turn ends, and it decides twice:

- **While you are speaking**, a start of speech takes the floor only once it is
  sustained enough to be a real barge-in. A backchannel — "mm", "haan", a
  one-word garble — does not cut you off and does not become a `UserMessage`.
- **When the caller stops**, the turn is committed either because the end of turn
  was confident, or because silence forced the close first. A silence-forced
  close that transcribed nothing is dropped rather than handed to you: there is
  no question in it to answer.

So a committed turn is not always a finished thought. Silence forces the close on
8.6% of real turns, measured over 14 days of production, and answering the
fragment is the cheaper mistake — a caller who was mid-thought resumes, and
resuming inside a few seconds of their own turn ending interrupts you at once.
Write your brain so a short reply to a fragment is survivable, rather than so it
never happens.

What you record for the caller's side is `msg.text` verbatim. It arrived
finalized, so there is nothing to reconcile on that leg.

## The durable copy is ours; the working copy is yours

Your history lives in your process, on your schema, and Voqalize persists none of
it. Our own copy is the wire itself: every frame both directions, uploaded as one
bundle when the call ends and read back by `session_id` — the same string that was
in `{brain_url}?session_id={session_id}` and in every line your brain logged. The
transcripts, each piece of the reply, and each frame a barge-in discarded are all
in it. See [reading a call back](/operate/reading-a-call/).

## Read next

- [Interruption and heard truth](/design/interruption-and-heard-truth/) — the argument.
- [The wire](/reference/wire/) — the frames that carry it.
- [Testing a brain](/build/testing/) — assert on the heard text, without a microphone.
