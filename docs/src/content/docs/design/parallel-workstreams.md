---
title: Parallel workstreams
description: A caller can say five things in one breath. An agent that handles them one at a time gives back the only speed advantage voice has.
---

A form makes you wait for each field. You type, it validates, it renders the next
one, and the round trip repeats until the form is done. Speech has no such
round trip: a caller can name six items in one breath and stop, having spent four
seconds on what the form spends four minutes on.

That burst is where the speed comes from. It is also the thing an agent gives back
first. Handle the six items one at a time — ask, resolve, confirm, ask again —
and you have rebuilt the form, out loud, at the pace of a conversation. Slower
than the form it replaced, because now every field costs a spoken turn.

So parallelism is not a later optimization here. Without it the caller's natural
behaviour becomes your worst case.

## Take the burst whole

`orderdesk`'s prompt says it in the imperative, because a model left to itself
will take one item and stop:

> The moment he names a product, call `add_items`. Do not wait for the previous
> one to resolve; do not ask a question in between. He can list six items in one
> breath — take them all in ONE `add_items` call with a list.

One tool call, six items, six independent pieces of work in flight. The rows enter
as `resolving` and settle one at a time — matched, or ambiguous between two pack
sizes, or not stocked — each on its own timeline, in whatever order the lookups
come back. The caller is still talking while they settle.

## Work that outlives its turn

`servicing` makes the same shape explicit for long work. `prepare_case` returns
immediately:

```python
{"status": "preparing_in_background",
 "note": "Running in the background; the advisor stays unblocked. Tell them when ready."}
```

The return value is not data. It is an instruction to the model about how to
behave while waiting — the tool's answer to "what do I say now" is "carry on."

Two SDK facts make this safe:

`session.dispatch(...)` never blocks and is callable from anywhere, including from
a task that outlived the turn that started it. A background job finishing ninety
seconds later can still paint the screen.

An action carries no audio, so it needs no floor. The screen can change while the
agent is mid-sentence, and neither one waits for the other. See
[voice points, the screen holds](/design/speech-vs-screen/).

## The real design question is how a result comes back

Voice is one serial channel and there are now three finished jobs to report.
Reading them out is almost never the answer. There are three ways, and they are
not equally priced:

| Way | When to use it | Shipped in |
|---|---|---|
| A row changes on screen, silently | The result is legible and unambiguous | `orderdesk`, `forge` |
| One short spoken line | It changes what the caller should do next | `servicing` |
| A spoken question | Genuinely ambiguous, and only the caller can resolve it | `orderdesk` |

The default is the first, and `forge`'s prompt tells the model to trust it:

> Every tool you call also shows up as a live task on screen (a small "activity"
> checklist), so your actions are already acknowledged visually — trust it and
> stay quiet.

Speaking costs a turn, so the second and third rows are spent, not spread. When
several rows do turn out to need the caller, batch them the way you batched the
intake — `orderdesk` again:

> Batch your questions. Let him finish his run of items, then at the natural
> pause ask about the ambiguous rows, one short question each.

## The exception is a human, not a machine

`aura` has one blocking tool. `authenticate` awaits a future that resolves when
the caller taps consent on their own screen, and the turn genuinely waits.

That is the rule, drawn tightly: machine work never blocks a turn; waiting on a
person sometimes has to, because there is nothing else the agent could
truthfully be doing. Even then it is worth a spoken line first, so the caller
knows the silence is theirs to end.

## Two things to decide for yourself

**Ordering.** Three background jobs finishing at once produce three dispatches in
the order they completed. `orderdesk` sends the whole row rather than a patch, so
last write wins per row and arrival order stops mattering. That is a convention
that works, and it is the one to copy until the SDK reserves something better.

**Failure.** Every worked example here succeeds. A fan-out where one branch fails
is the case you will hit first in production, and the failed row still has to
reach the caller through one of the three ways above — most often the first, as a
row that says so.

## Read next

- [The turn budget](/design/turn-budget/) — where the time in a single turn goes.
- [Voice points, the screen holds](/design/speech-vs-screen/) — why the screen is the wide channel.
