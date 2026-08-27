---
title: The turn budget
description: Between the caller finishing a sentence and hearing a syllable, exactly one interval belongs to your code. Where it goes, how to measure it, and why a fast turn is one that starts fast.
---

Between a caller finishing a sentence and hearing the first syllable back, three
things happen in order:

1. Voqalize decides the caller has stopped and finalizes the recognizer's text.
2. **Your callback runs, until it yields its first `Chunk`.**
3. Voqalize synthesizes that chunk and plays it out.

The middle interval is the only latency in the product your code controls. It has
a measurable name — **time to first chunk** — and it has no idle time you can
reclaim later. If the caller waited, they waited.

So a fast turn is not a turn that finishes quickly. It is a turn that *starts*
quickly. After the first chunk you have the caller's attention and the rest of
your generation runs underneath it; before the first chunk you have a person
listening to nothing.

## `greet` is not a turn

`greet` returns a string, not a generator. It is `async` so you can look up the
caller's name, and not so you can generate the sentence. This is the one moment
where a caller is sitting on a connected session hearing nothing at all, and a
model round-trip here is the most expensive latency in the product.

A fixed line, or a template over what the page sent — `f"Hi {name}, how can I
help?"` — is as elaborate as it should get. Returning `None` opens the session
silently, which is what an ambient agent wants.

Where a generated opener is worth having, speak a written one first. The demos
send a one-word hello from a table (`demos/voqalize_demos/greeting.py`) before
any model has run, and append a line to the greeting prompt telling the model to
continue rather than greet again. The caller hears a syllable immediately and the
model's sentence arrives underneath it.

## Where your half actually goes

**Time to the model's first token, not its last.** Awaiting a completion before
speaking converts a streaming system into a batch one. Stream chunks as you
produce them.

**Tool round trips.** A tool in your process is a function call. The same tool
reached over HTTP is a network round trip on every turn that uses it. See
[tool design for voice](/design/tool-design/).

**Retrieval as a serial hop**, unless it was started before it was needed. See
[parallel workstreams](/design/parallel-workstreams/).

**Work that was serial for no reason.** Three sequential `await`s cost the sum;
one `asyncio.gather` costs the slowest.

**Prompt size**, which is [prompt design for voice](/design/prompt-design/).

**A cache miss you caused yourself.** The system instruction is the cache prefix.
Set it once per session and it matches turn after turn; edit it — even to append
one fresh line of context — and every turn re-reads the whole thing. This is the
item on the list that is free to get right and quietly expensive to get wrong,
because nothing in a transcript shows it. Context that changes belongs at the
tail, next to the latest user message.

## Thinking budget is a latency setting

A reasoning budget on a voice turn is spent in silence the caller sits through,
and thought tokens are never spoken, so the cost has no audible half at all. The
SDK's `VOICE_THINKING` asks for the least thinking the default model allows
(`sdk/gemini.py`).

Both halves of that setting are model-specific, and three ways it bites were each
verified against the live API on 2026-08-14:

- **The knob moved.** `thinking_budget=0` was accepted by the 3.1 models; 3.5 and
  later reject it with a bare `400 INVALID_ARGUMENT` that names no field.
- **The floor moved.** `gemini-3.7-flash` refuses `MINIMAL` outright. Its floor,
  `LOW`, still spends around 275 thought tokens, so it has no zero-thinking
  setting at all, and its turns ran about twice as long as the default model's.
- **A level a model accepts is not one it acts at.** `gemini-3.5-flash-lite`
  takes `MINIMAL` and then drives the screen on 9 of 15 identical turns, asking
  "which trip?" on the rest. At `LOW` it was 11 of 15.

Measure when you change the model. The numbers above are one afternoon against
one set of turns, and they are printed here with that condition attached because
that is all they are.

## Pace the caller while the work runs

Two prompt rules, both in production. `orderdesk`: *"Start every reply with a
tiny phrase so audio begins instantly,"* and *"Say a tiny line before or while
calling a tool — never leave silence."* `aura`: *"Speak a short line first, then
call the tool."*

This is not a trick to hide latency. A short acknowledgement is what a person
does while they look something up, and it converts dead air into a turn that has
started.

## Instruments you already have

`on_finalize` fires once per speech unit after playout, carrying what was heard
and whether it was interrupted. Stamp a monotonic clock at callback entry and
close it at your first `Chunk`; that is your half of the budget, measured on
every turn, in your own process.

**Interruption rate is the cheapest quality proxy in the product.** Callers talk
over an agent that is too slow, too long, or wrong, and the three are hard to
tell apart from a transcript and easy to tell apart from a clock.

`get_session_events` over [the MCP server](/reference/mcp/) returns our half
of the same call, joined on the same `session_id`.

## There are no latency numbers on this page

We publish no figure for the intervals we own, because we have not measured them
under conditions we would be willing to print. A number without its percentile,
its region and its load is a mood, and this reader would check it.

So this page names moments instead — before the first word, on every turn that
uses it — and hands over the instruments to measure your own half, which is the
half you can change today.

## Read next

- [Parallel workstreams](/design/parallel-workstreams/) — why an agent that handles one thing at a time gives the speed back.
- [Prompt design for voice](/design/prompt-design/) — what has to be in the prompt because a lookup is silence.
