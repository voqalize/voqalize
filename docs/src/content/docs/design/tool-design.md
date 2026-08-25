---
title: Tool design for voice
description: A tool that waits is a bug. Voice tools return immediately, are never cancelled, and are undone by another call rather than by a rollback.
---

A tool call in a chat app is a pause. A tool call in a voice call is dead air,
because the model cannot speak while it waits for a result it asked for.

That single fact reshapes every tool you write. Four properties follow from it,
and they are properties of the tool rather than of the prompt around it.

## A tool returns immediately

Single-digit milliseconds, or a promise and a note. `servicing`'s `prepare_case`
kicks off minutes of background work and returns this:

```python
{"status": "preparing_in_background",
 "note": "Running in the background; the advisor stays unblocked. Tell them when ready."}
```

There is no data in that return value. It is behavioural instruction — the tool
telling the model how to act while the answer is on its way. That is what a voice
tool's return value is for whenever the work is slower than a sentence.

A tool that genuinely takes two seconds has been mis-split. Break it into a cheap
dispatch plus a background workstream, and report the result the way
[parallel workstreams](/design/parallel-workstreams/) describes.

## A tool is not cancelled

Barge-in cancels the turn. It does not cancel a tool call already running, and it
does not un-dispatch an action already sent.

This sounds untidy and is correct: the caller interrupted the *speech*. They did
not interrupt the lookup, and half-applied work is worse to reason about than
completed work. The screen showing what they asked for is right, whether or not
the sentence describing it finished. See
[interruption and heard truth](/design/interruption-and-heard-truth/).

Tools also run **one at a time, in the order the model produced them**. Two tools
racing would put the caller's display in an order the model never asked for, and
the screen is the thing the caller is reading.

## A tool is undone by another tool

The undo for a voice tool is a compensating call, and the compensating calls are
worth enumerating separately rather than collapsing into a re-add. `orderdesk`
gives the model six edit tools and shouts why:

> **A QUANTITY TWEAK IS NEVER A RE-ADD.** An absolute number is `set_quantity`; a
> relative one is `adjust_quantity` with a delta. If he wants none of it, that is
> `remove_items`.

> **A VARIANT SWAP IS NEVER A RE-ADD EITHER.** … Never remove the row and add it
> again — he loses his place on the screen.

The reason in that second line is the general rule. Each of these preserves the
identity of the row it touches, so the display updates in place and the caller's
eye keeps its position. A re-add is correct in the database and wrong on the
screen.

The premise underneath is that tools are cheap enough to undo this way. A tool
expensive enough that you want to abort it mid-flight is the one to split.

## A failed call is a result, not an exception

A tool that raises comes back to the model as an error it can read and act on:
`is_error` on the step, plus a line in your log. The model sees what went wrong
and calls again.

The SDK's own comment on that path is worth repeating, because the failure mode it
names is the one that reaches production:

> `is_error` is the half the automatic path has no room for: there a failure
> reaches the model as an ordinary payload, and the model narrates it as success.

An agent cheerfully telling a caller their order is placed, because the failure
came back as `{"error": …}` and looked like data, is the shape of the worst bug in
this category.

Use the same seam for validation. `orderdesk`'s `ask_choice` is rejected unless it
has two to four choices, uses known codes, and covers every candidate; a separate
validator rejects non-Latin labels headed for a screen that must stay Latin. Both
come back as retriable errors, and the prompt warns the model in advance that they
can. So the *shape* of the question is guaranteed even though its wording is the
model's. See [prompt design for voice](/design/prompt-design/).

## A tool never holds irreversible authority

`orderdesk`'s prompt draws the line in one sentence:

> You have no confirm tool and no confirm authority. Your job is a fully matched
> cart: every row green, every quantity set.

The pharmacist presses Confirm. `servicing` is the same shape — `submit_packet`
goes through after the advisor approves. The agent gets the work to the edge of
the commit and stops there, which is also what makes every earlier tool safe to
undo.

## Some tools must not take the floor

`orderdesk` answers the manual search bar's `catalog_search` and `list_variants`
**floor-free** — session-scoped, no inference, no speech. The caller is typing in
a search box; a keystroke must not make the agent start talking over them.

If a tool exists to serve the screen rather than the conversation, say so
explicitly. Anything that can be triggered by a tap or a keystroke belongs in this
category.

## The one blocking tool that is allowed

`aura`'s `authenticate` awaits a future resolved when the caller taps consent. It
blocks because it is waiting on a human decision, and there is nothing else the
agent could truthfully be doing.

Machine work never blocks a turn. A person's decision sometimes has to.

## The checklist

1. Returns in single-digit milliseconds, or returns a promise and a note.
2. Typed arguments; bad ones come back as an error the model can read.
3. Has an undo that is another tool call.
4. Preserves the identity of what it touched, so the screen does not jump.
5. Holds no authority over anything irreversible.

## Read next

- [Parallel workstreams](/design/parallel-workstreams/) — where the slow half of a tool goes.
- [Prompt design for voice](/design/prompt-design/) — teaching the model which tool to reach for.
