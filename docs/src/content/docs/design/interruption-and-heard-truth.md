---
title: Interruption and heard truth
description: The caller heard the part that finished playing. If you record what your brain generated, you have written down a call that never happened.
---

Your brain yields three sentences. The caller cuts in after the first one.

What the caller knows is one sentence. What your code produced is three. If the
three go into history, every later turn is planned against a version of the call
that never happened — the agent thanks the caller for a detail they never gave,
or declines to repeat something it believes it already covered.

Nothing catches this. There is no error, no dropped frame, no latency spike, no
failed eval. The transcript your own code wrote agrees with itself. The only
artifact that disagrees is the recording, and nobody plays the recording of a call
that went fine.

## Interruption is the normal case

On any turn longer than a sentence, a caller who cuts in is a caller working
correctly: they got what they needed and moved on. Building for it as an
exception gets the arithmetic backwards — the uninterrupted turn is the one worth
treating as a special case, because it is the one where the caller had nothing to
add.

## `on_finalize` hands you the prefix

After a unit of speech finishes playing, one callback fires:

```python
async def on_finalize(self, session: Session, fin: Finalize) -> None:
    ...
```

`Finalize` carries three things: `speech_id`, `heard`, and `interrupted`.

`heard` is **the delivered prefix** — the text that reached the caller's ear, not
the text you yielded. `interrupted` says whether the caller cut in. This is the
one place the runtime knows something your process cannot: playout happens on our
side of the wire, so where the audio actually stopped is ours to report and yours
to record.

The callback fires long after the generator that produced the speech has
returned. That ordering is the point — the truth about a unit is not available
while it is still playing.

## The obligation, stated plainly

Whatever you persist as the assistant's turn — a Gemini `Content`, a row in your
own table, a line in a log — is built from `fin.heard`. Not from the string you
yielded, and not from the accumulated chunks.

Two places it bites, and they are the same lie twice:

1. **History for the next model call.** The model plans its next turn against what
   the caller knows.
2. **Everything downstream of the transcript** — summaries, QA scoring, handoff
   notes, the "what did we tell this customer" audit that someone runs six months
   later during a dispute.

The second is worse, because by then the recording is gone.

## What happens to a turn that gets cut

Voqalize sends an interruption naming the last turn it applies to. The SDK marks
that number as a watermark, and every turn at or below it is dead: its task is
cancelled, and any chunk still in flight from it is discarded rather than spoken.

Two consequences worth knowing:

**Your `finally` runs.** The generator is closed, not abandoned — the SDK calls
`aclose()`, so cleanup, span exits and released locks all execute on an
interrupted turn exactly as on a completed one.

**Turn ids fence the turns from each other.** The turn that replaces a cancelled
one carries a higher number, and a watermark never rises to reach it. Late work
from a dead turn cannot leak a sentence into its successor.

## What interruption does not undo

An action already dispatched has already arrived. The screen does not roll back
when the caller cuts in, and it should not: the itinerary they are looking at is
the itinerary they asked for, whether or not the sentence describing it finished.
See [voice points, the screen holds](/design/voice-points-screen-holds/).

In-flight tool work is not cancelled either. A charge that was authorized was
authorized. If a tool must not outlive its turn, that is a decision for your tool
to make, and it needs its own idempotency rather than a hope about timing.

## Testing it without a microphone

The conformance harness models playout and heard-truth finalization the way the
runtime does, so heard truth is an assertion your brain passes rather than a
behaviour described on a page. `VoqalizeDriver` records what was delivered per
unit, which means a test can assert on the heard text instead of the generated
text — and the strongest property available is the one worth asserting:
**the history your brain wrote equals what the driver says was heard.**

See [testing a brain](/brain/testing/).

## One limit we have not established

`heard` is a prefix of your text, but playout was cut in the middle of a word.
Whether that prefix is character-exact or rounds to a boundary is not something we
have pinned down, and a page should not claim a precision nobody has verified.
Treat `heard` as the honest account of what was delivered, and do not build
anything that depends on its last character.

## Read next

- [The turn budget](/design/the-turn-budget/) — why interruption rate is the cheapest quality signal you have.
- [Testing a brain](/brain/testing/) — driving barge-in from a test.
