---
title: Misunderstanding and reversal
description: The caller will be misheard and will change their mind mid-sentence. The design question is how fast a mistake becomes visible and how cheap it is to undo.
---

Three things go wrong on every voice deployment, and none of them are going away.

The recognizer mishears. The model misinterprets what it heard correctly. And the
caller changes their mind halfway through the sentence — which is not an error at
all. It is how people talk, and a system that treats it as a fault is a system
that argues with its user.

So "how do we prevent mistakes" is the wrong question to build against. The
questions that produce a working design are: **how fast does a mistake become
visible, and how cheap is it to undo?**

Three answers follow, and the third is the one that saves you.

## Show what the agent believes, including that it is unsure

Uncertainty is a state to render, rather than a null to hide. `orderdesk` gives
every row on the cart one of five statuses:

```python
LineItemStatus = Literal["resolving", "multi_family", "multi_variant", "matched", "not_found"]
```

A row that has entered but not settled says so on screen. The pharmacist can see
the agent is still working on item four while item five is already matched, and
can fix item four by hand without waiting to be asked.

Two more fields do the same job at a finer grain. Each row keeps `spoken_text` —
the raw heard phrase — beside the SKU it resolved to, so the *evidence* for a
mistake survives the resolution. Seeing "amlong" next to a row that resolved to
the wrong brand tells the pharmacist immediately whether the recognizer or the
matcher was at fault. And `source: "agent" | "manual"` records who put the row
there, so a hand correction is distinguishable from the agent's own work.

None of that is possible if the screen only shows conclusions. See
[voice points, the screen holds](/design/voice-points-screen-holds/).

## Make correction cheap, by voice and by hand

By voice, correction is a taxonomy of tools rather than one re-add:

| What the caller says | Tool | What it preserves |
|---|---|---|
| "make it three" | `set_quantity` | the row |
| "one more" | `adjust_quantity` | the row, and the distinction between delta and absolute |
| "the syrup, the tablets" | `change_variant` | the row and its quantity |
| "I meant the 40" | `refine_item` | the row and its history |
| "drop that" | `remove_items` | — |
| picking from options | `choose` | the row |

The shared property is identity. The row stays where it is, so the caller's eye
does not have to re-find it. `orderdesk`'s prompt gives the reason in five words:
remove and re-add, and "he loses his place on the screen."

By hand, correction is the same event arriving from the other side. The pharmacist
taps a variant pill, edits a quantity, deletes a row, adds something from the
search bar — and the page's state reaches the brain, which yields to it. That path
is a supported one, and it is how the agent notices a correction it never heard.

The instruction that closes the loop is the reciprocal of everything above:
"**NEVER redo what he already did himself.**"

## Withhold the authority that matters

The strongest correction mechanism is not correcting at all. Anything important or
irreversible is committed by a human, with a click, and the agent has no tool for
it.

- `orderdesk`: "You have no confirm tool and no confirm authority." The pharmacist
  presses Confirm; the brain sees the screen say `confirmed` and closes in one
  line.
- `servicing`: `submit_packet` goes through after the advisor approves.
- `aura`: `authenticate` waits on a tap.

**Why a click and not a spoken "yes."** A spoken yes can be misheard. It can be
background noise the recognizer resolved into a word. It can be a genuine yes to a
question the caller only half-heard, because they started talking over the second
half of it — and [what the caller heard](/design/interruption-and-heard-truth/)
is the part that finished playing, which your agent does not know at the moment it
asks. A click has none of those failure modes, and it lands on a screen showing
exactly what is being agreed to.

This is also what makes every earlier tool safe. Corrections stay cheap right up
to the commit boundary, and the boundary is a human.

## Where the story stops

Two limits, stated because a page that omits them would be selling something.

**We have no worked example of correcting something already committed.** The
compensating-call taxonomy above runs up to the confirm click and stops. Whatever
undoes a placed order is your system's problem, and it is a different kind of
problem.

**All of this assumes a screen.** Every mechanism on this page — visible
uncertainty, identity-preserving edits, the click that commits — needs somewhere
to render. An agent with no UI has none of them, and has to fall back to spoken
confirmation with all the failure modes just listed. If you are building
voice-only, the honest version is fewer irreversible actions rather than better
confirmations.

## Read next

- [Tool design for voice](/design/tool-design/) — the compensating-call shape in full.
- [Interruption and heard truth](/design/interruption-and-heard-truth/) — why the agent cannot assume its question was heard.
