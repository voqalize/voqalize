---
title: Prompt design for voice
description: Every lookup the agent has to make is silence the caller sits through. A voice prompt is a latency budget written in English.
---

A chat prompt can afford to be thin. The model can look things up, and the reader
watches a spinner while it does — a two-second tool call reads as work happening.

Say the same two seconds out loud. Nothing happens, on a channel where nothing
happening is the one thing a caller reacts to. So the arithmetic changes: what the
agent needs, it should mostly already have.

That is the whole design rule, and it is not "be concise."

## The 80/10/10 target

| Share of what the agent needs | Where it lives | What it costs |
|---|---|---|
| 80% | In the prompt already | tokens |
| 10% | One fast tool call away — in your process, no network | a model round trip |
| 10% | Genuinely slow — remote, expensive | a background workstream, with an answer to "what does the caller hear meanwhile" |

These numbers are a design target we hold to, not a ratio we have instrumented.
Their job is the third row: anything that lands there needs a plan for the
silence, which is [parallel workstreams](/docs/design/parallel-workstreams/).

## Five things a voice prompt does that a chat prompt need not

### 1. Talk less, do more

The default reply is one short line, and everything longer is on the screen. The
shipped prompts say it in the imperative, because a model's default register is a
paragraph:

- `orderdesk`: "No markdown, no lists, no stage directions. **Never narrate your
  own actions** — call the tool and say only what the pharmacist should hear."
- `forge`: "your actions are already acknowledged visually — trust it and stay
  quiet."
- `sugar`: "better, don't say units at all; the screen shows them."
- `support`: "Never read out ids or order numbers as raw text — say 'your order
  from May 28th' instead."

See [voice points, the screen holds](/docs/design/voice-points-screen-holds/).

### 2. Hold its prompt still

The system prompt is the cache prefix. Set it once per session and it matches
turn after turn; rebuild it — even to append one fresh line — and the provider
re-reads the whole thing on every turn, which the caller pays for in silence.

Volatile context goes at the tail, next to the latest user message, where a change
costs the provider only the small new suffix. This is the cheapest latency win
available and the easiest to throw away by accident, because nothing in a
transcript shows it.

### 3. Know where the caller is

The agent needs a way to answer "what is on screen right now," and the answer has
to be current rather than remembered. Two demos do the same thing: the page keeps
pushing its state, the brain parks the latest snapshot, and a tool reads it on
demand — `aura`'s `get_screen_context`, `servicing`'s `get_advisor_context`.

The reciprocal instruction matters as much. The screen is authoritative over the
agent's own memory of it, because the caller has hands: `orderdesk`'s prompt ends
that thought with "**NEVER redo what he already did himself.**"

### 4. Track a task list

Several threads are open at once and the prompt has to name them and say how each
one closes. `servicing`'s prompt is explicit that background prep runs while the
advisor keeps working: "prepare the other case quietly and tell them when it's
ready. They are never blocked."

### 5. Assume it misheard

A recognizer on a phone line in a pharmacy will get things wrong. Correction paths
belong in the prompt as first-class instructions rather than as a fallback
paragraph at the end. See
[misunderstanding and reversal](/docs/design/misunderstanding-and-reversal/).

## Never leave silence, said twice in production

- `orderdesk`: "Say a tiny line before or while calling a tool — never leave
  silence, never speak a whole sentence about what you are doing."
- `aura`: "opening a page or loading a video takes a moment; never leave silence.
  Say a brief line FIRST, THEN call the tool."

Both of these are the prompt doing latency work. See
[the turn budget](/docs/design/the-turn-budget/).

## The sharpest fragment we have shipped

`orderdesk` has to disambiguate a spoken drug name against two dozen SKUs, over
the phone, in Hindi, without reading a list aloud. Its prompt teaches an
information-theoretic rule in plain language, and the whole block is worth reading
as a model of how specific this gets:

> Four or fewer choices need no machinery: the pills are already on his screen.
>
> Five or more, and the tool hands you a CANDIDATE TABLE instead of options. Never
> read it. Never try to show it all. Call `ask_choice` ONCE with one short English
> question and TWO TO FOUR choices that split those candidates as evenly as you
> can. **The sharpest question is the one that eliminates the most candidates
> WHATEVER he answers** — a choice that keeps twenty-three of twenty-four is a
> wasted turn.
>
> Group on the axis that actually partitions the list: the suffix line first, then
> form, then a strength band. **Never split on pack size while a bigger axis still
> divides the list.**
>
> **TWO ROUNDS AT MOST.** Round one cuts twenty-four to a handful; round two is
> leaf pills he can tap.

Three things to take from it. It names the threshold at which machinery starts
(five). It gives the model a decision rule rather than an example. And it caps the
interaction in turns, because a turn is the unit the caller feels.

The wording of the question is the model's; the *shape* is not. `ask_choice`
rejects a set that has fewer than two or more than four choices, or that leaves a
candidate uncovered — and the prompt tells the model what happens when it does, so
a rejection is a retry rather than a dead turn. See
[tool design for voice](/docs/design/tool-design/).

## Read next

- [Tool design for voice](/docs/design/tool-design/) — why a tool that waits is a bug.
- [The turn budget](/docs/design/the-turn-budget/) — what a prompt costs on every turn.
