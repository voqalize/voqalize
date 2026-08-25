---
title: Voice points, the screen holds
description: Voice is the fastest way for a person to express dense intent and the slowest way to receive it. The division of labour that follows, and the two output channels that enforce it.
---

Speech is serial, it cannot be skimmed, and it is gone the moment it is played.
Nine product codes read aloud are nine things the caller has forgotten by the
time the tenth arrives. The screen is random-access and it persists, and it
cannot direct attention on its own.

So the division: **voice carries intent, acknowledgement, and the one number that
matters. The screen carries the record.** On the way out, the agent's job is to
point at something that holds more than a sentence can.

## Two channels, and one of them holds the floor

A brain has exactly two ways to reach the caller, and the difference between them
is audio.

**Speech** is yielded from the turn. `SpeechStart`, `Chunk`, `SpeechEnd` are the
only yieldable types (`sdk/events.py`), and a unit of speech is one thing the
caller can be interrupted out of.

**An action** is dispatched, never yielded. It carries no audio, so it holds no
floor, and `session.dispatch(action)` is callable from inside a turn, from a
callback that is not a generator at all, and from work that finished long after
the turn that started it.

That asymmetry is the whole design. Speaking is a turn and costs the caller time.
Rendering costs them nothing, so it can happen at any moment, including while the
agent is saying something else.

## Speak the pointer, render the payload

Three shapes, all of them running today:

| Shape | What voice says |
|---|---|
| Options on a row the caller can tap | "drops or ointment?" — never the prices |
| A video seeked to the second that answers the question | one line pointing at the screen |
| A ring drawn around the field in question | the field's name, and nothing else |

`orderdesk` states the rule in its own prompt, because a text-to-speech engine
reads pharmaceutical brand names badly and the screen spells them correctly:
*"NEVER read out a list of options, prices, pack sizes or SKU codes. Ever. That
is what the screen is for"* (`demos/orderdesk/backend/brain.py`). `aura` plays
the official how-to video muted and seeked to the right chapter while the agent
narrates over it, and carries the chapter map in the prompt marked as material
for choosing a timestamp rather than a script to read out.

## An action is a shape, and the shape is the contract

Subclass `Action` and the fields are the payload. The class name becomes the wire
name — `OpenItinerary` becomes `open_itinerary` — and can be pinned with `name=`
when you would rather the class be free to move.

**Every declared field is emitted, including the ones that are `None`.** The wire
shape of an action is a function of the class rather than of which fields
happened to be set on this call, so the browser declares one total interface and
handles one shape. JSON Schema export is what makes the TypeScript half
generatable rather than hand-copied (`sdk/actions.py`).

Inside a turn, a dispatch reaches the wire in the order it runs, so it cannot
jump ahead of speech already yielded. An action that belongs with a sentence goes
next to that sentence.

## The failure this prevents is invisible

An agent that narrates its own screen produces a correct transcript, a completed
call, and a satisfied dashboard. Every instrument reports success. The only
symptom is that the call took twice as long as it needed to, because the slow
channel repeated what the fast one had already delivered — and no metric you
have distinguishes that from a caller who had more to say.

The proxy that does see it is the interruption rate. Callers talk over an agent
that is reading things to them.

## Read next

- [The turn budget](/design/the-turn-budget/) — the one interval of a turn your code controls.
- [Interruption and heard truth](/design/interruption-and-heard-truth/) — what the caller heard, which is what a transcript records.
