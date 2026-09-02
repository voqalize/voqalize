# 1. Voice points, the screen holds

> **The surprise.** Voice is the fastest way for a human to express dense intent
> and the worst way to receive it. So the agent's job on the way out is not to
> tell the caller things — it is to point them at something that holds more than
> a sentence can.

## Belief

- Speech is serial, unskimmable, and gone the moment it is played. Nine SKUs read
  aloud are nine things the caller has already forgotten.
- The screen is random-access and persistent, and it is silent — it cannot direct
  attention on its own.
- **The division that follows:** voice carries *intent, acknowledgement, and the
  one number that matters*. The screen carries *the record*. Voice's highest-value
  use is as a pointer into a richer surface — a widget, a form, a document, a
  video at the right second.
- A voice agent that narrates its screen has used the slow channel to repeat what
  the fast one already did, and doubled every turn to do it.

## Facts

- The brain has exactly two output channels: **speech**, which is yielded, and
  **actions**, which are dispatched. `Speech = SpeechStart | Chunk | SpeechEnd` is
  the only yieldable type (`sdk/actions.py`, `sdk/events.py`).
- An action is never yielded. It carries no audio, therefore holds no floor:
  `session.dispatch(action)` is callable from inside a turn, from a non-generator
  callback, and from work that finished after the turn that started it
  (`Session.dispatch` docstring).
- Actions are **typed**: subclass `Action`, and the fields are the payload. The
  class name is the wire name (`OpenItinerary` → `open_itinerary`), pinnable with
  `name=`.
- **Every declared field is emitted, including `None`.** No `exclude_none`. The
  wire shape of an action is a function of the class, not of which fields happened
  to be set — so the browser declares one total interface
  (`sdk/actions.py` module docstring).
- JSON Schema export is what makes the TypeScript half generatable instead of
  hand-copied.
- Inside a turn, a dispatch hits the wire in the order it runs, so it cannot jump
  ahead of speech already yielded.

## Proof

- **`orderdesk`** — "NEVER read out a list of options, prices, pack sizes or SKU
  codes. Ever. That is what the screen is for." And the positive move: "Point at
  the screen instead: *स्क्रीन पर ऑप्शन देखिए*". The TTS mangles pharma brand
  names, so the prompt minimises saying them at all and leans on the screen, which
  spells them correctly (`demos/orderdesk/backend/brain.py`).
- **`aura`** — `play_help_video(video_id, start_sec)` plays the official how-to
  video **muted, seeked to the chapter that answers the exact question**, while
  the agent narrates. `highlight_step(index)` moves the on-screen focus and the
  agent "says just one short line pointing at the screen." The chapter map is in
  the prompt explicitly "for YOU to pick the right start_sec… it is not a script
  to read out." Also `spotlight(target, label)` — literally draws a ring around an
  element (`demos/aura/backend/brain.py`).
- **`sugar`** — "NEVER recite what is on screen: no reading out calorie numbers,
  glucose values, med names or lists. Gesture at them instead." And: "don't say
  units at all; the screen shows them."
- **`forge`** — "Don't describe what's now on screen. The admin can see the new
  step, the passing tests, the lit path, the code."
- **`servicing`** — "Voice augments the screen; it does not replace it."
- **`support`** — `highlight_item` "to point at the exact line."
- Every demo drives a screen. None of them is a phone call.

## The move this page names

**Speak the pointer, render the payload.** Three shapes, all shipped:

| Shape | Demo | What voice says |
|---|---|---|
| Pill options on a row | `orderdesk` | "drops or ointment?" — never the prices |
| Video seeked to a step | `aura` | one line pointing at the screen |
| A ring around a field | `aura` `spotlight` | the field's name, nothing else |

## Gap

- We have no page that states this, so every demo prompt re-derives it by hand.
  Eleven prompts contain a private copy of the same rule, phrased eleven ways.
- **Open:** is there a fourth channel worth naming — audio that is not speech
  (earcons, a shutter click on commit)? Nothing ships it today.
