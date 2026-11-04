---
title: Transcripts and heard truth
description: Record what the user heard, not what you generated. How on_finalize reports each speech unit, how to pair it with the unit that produced it, and what the user's transcript is.
---

A reply that generated three sentences and was cut after one is remembered as
one. After each speech unit plays, Voqalize tells your brain what the user
actually **heard**, and that, not what your model produced, is what goes into
history. Get it wrong and the next turn refers to things the user was never told.

## `on_finalize` runs once per unit, after playout

```python
from voqalize.sdk import Brain, Finalize, Session


class Concierge(Brain):
    async def on_finalize(self, session: Session, fin: Finalize) -> None:
        ...
```

| Field | What it is |
|---|---|
| `heard` | The prefix of that unit's text that reached the user. |
| `generated` | The text you sent for that unit, kept by the SDK for you. |
| `speech_id` | The unit this reports on. |
| `interrupted` | `heard != generated`: `True` when the user cut in, `False` when it played to the end. |

`heard` is always a verbatim prefix of `generated`, never longer and never
another unit's words. Equal means the unit played out, shorter means it was cut,
and empty means nothing reached the user.

It fires **after playout**, long after the generator that produced the unit
returned, so this callback is the only place the record can be written.

What you can rely on:

- **Exactly one finalize per `SpeechStart` you yielded**, including a unit with no
  text (`heard=""`, `generated=""`, not interrupted).
- **In the order the units opened**, oldest first.
- **A unit the user never heard is still reported**, as `heard=""` against what
  you generated.
- **A barge-in does not cancel the finalizes you are owed.** Every unit the turn
  opened is still reported.
- **A finalize with nothing of yours waiting is the greeting.** `greet` returns a
  string the SDK speaks, so this is the only record of it. Skip it and your model
  does not know it greeted, and greets again.

## Pair each finalize with the unit that produced it

`speech_id` is minted inside your generator, so pair by order instead: put the
unit in a queue on the same line where you yield `SpeechStart`, and the n-th
finalize belongs to the n-th unit you opened. Open no unit you have nothing to
say in, so a step that only calls a tool never puts an entry in the queue.

```python
from collections import deque

from voqalize.sdk import Brain, Finalize, Session, SpeechChunk, SpeechEnd, SpeechStart, UserMessage


class Concierge(Brain):
    def __init__(self) -> None:
        self.history: list[dict[str, str]] = []
        # Units opened, oldest first. One finalize is coming for each.
        self._awaiting: deque[dict[str, str]] = deque()

    async def on_user_message(self, session: Session, msg: UserMessage):
        self.history.append({"role": "user", "text": msg.text})

        unit: dict[str, str] | None = None
        async for piece in self.model.stream(self.history):
            if not piece:                       # never sent, so it opens nothing
                continue
            if unit is None:
                unit = {"role": "assistant", "text": ""}
                self.history.append(unit)
                self._awaiting.append(unit)
                yield SpeechStart()
            unit["text"] += piece
            yield SpeechChunk(piece)
        if unit is not None:
            yield SpeechEnd()

    async def on_finalize(self, session: Session, fin: Finalize) -> None:
        if not self._awaiting:
            if fin.heard:                       # the greeting
                self.history.append({"role": "assistant", "text": fin.heard})
            return
        unit = self._awaiting.popleft()
        if fin.heard:
            unit["text"] = fin.heard
        else:                                   # nobody heard it, so it is not a turn
            self.history = [c for c in self.history if c is not unit]
```

The shipped model brains (`GeminiBrain`, `OpenAIBrain`, `LiteLLMBrain`) do
exactly this for you. The [conformance driver](/build/testing/) reports every
unit too, so a brain that opens one and forgets to queue it fails there rather
than in a call.

**Keep the callback short.** Frames are handled one at a time, so a slow database
write in `on_finalize` delays everything queued behind it, including the next
`on_user_message`. Write into memory here and flush from your own task.

## A wrong record is invisible until the next turn

Record what you generated, and the next turn is planned against a conversation
that never happened: the model refers to a sentence it did not finish, reuses a
number the user never heard, or declines to repeat something it believes it
covered. Transcripts, logs and evals all agree with the wrong record; only the
[recording](/operate/recordings/) disagrees. Test it with `barge_in` in the
[harness](/build/testing/). The argument is
[interruption and heard truth](/design/#interruption-and-heard-truth).

## What the user said

`msg.text` is the **committed** transcript of one user turn. Nothing partial
reaches a brain (there is no interim-transcript frame), so the text never changes
under you, and one turn may be several pieces of speech joined.

- **While you speak**, the user takes the floor only with sustained speech. A
  backchannel ("mm", "haan") does not cut you off.
- **When the user stops**, the turn is committed when the end of turn is
  confident, or when silence closes it first. A turn with no transcribed words is
  not handed to you.

So a committed turn is not always a finished thought. Write your brain so a short
reply to a fragment is survivable: a user who was mid-thought simply carries on,
and interrupts you if you are speaking.

Record `msg.text` verbatim for the user's side.

## Voqalize keeps the durable copy

Your history lives in your process, and Voqalize stores none of it. Voqalize's own
record of the session (what was asked, what your brain generated, what the user
heard, and what each interruption discarded) is read back by `session_id`, the
same id your brain sees as `session.id`
([Reading a call back](/operate/reading-a-call/)).

## Read next

- [Test the brain](/build/testing/): assert on heard text without a microphone.
- [Interruption and heard truth](/design/#interruption-and-heard-truth): the argument.
- [The wire](/reference/wire/): the frames that carry it.
