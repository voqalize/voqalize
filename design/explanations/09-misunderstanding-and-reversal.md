# 9. Misunderstanding and reversal

> **The surprise.** The caller will be misheard, and will correct themselves
> mid-sentence — this is normal operation, not failure. So the design question is
> never "how do we avoid errors", it is "how fast is an error visible and how
> cheap is it to undo." And the answer to *irreversible* actions is that the agent
> does not have the authority: a human commits them with a click.

## Belief

- Three failure sources stack, and none of them go away: the recognizer mishears,
  the model misinterprets, and **the caller changes their mind mid-utterance**.
  The third is not an error at all — it is how people talk.
- Therefore:
  1. **Make mistakes visible.** The screen shows what the agent believes,
     immediately, including while it is still uncertain ([1](01-voice-points-screen-holds.md)).
  2. **Make correction cheap.** By voice *and* by hand, and correction must
     preserve identity so the caller does not lose their place.
  3. **Withhold authority.** Anything important or irreversible is committed by an
     explicit on-screen click, never by the agent.
- **Why the click, and not a spoken confirmation:** a spoken "yes" can be
  misheard, can be barge-in noise, and can be a "yes" to a question the caller only
  half-heard ([3](03-interruption-and-heard-truth.md)). A click cannot.

## Facts

- **`spoken_text` is kept beside the resolved value.** `LineItemView` carries the
  raw heard phrase *and* the SKU it settled on. The evidence for a mistake
  survives the resolution — you can see what it heard, not just what it decided.
- **Uncertainty is a first-class status**, not a null: `resolving`,
  `multi_family`, `multi_variant`, `matched`, `not_found`. The screen can render
  "I am not sure yet" as a distinct state.
- **`source: "agent" | "manual"`** records who did it, so a correction by hand is
  distinguishable from the agent's own work.
- **Every action carries the whole row**, so a correction is a re-render of one
  row and not a diff that can half-apply ([7](07-who-owns-which-state.md)).
- **A malformed tool call is retriable** rather than fatal — it comes back as an
  error result the model can read and fix, "never a dead turn"
  (`sdk/gemini_interactions.py`, `_failed`) ([6](06-tool-design.md)).

## Proof — the correction taxonomy

`orderdesk` gives the model six edit tools instead of one re-add, and the prompt
shouts the two rules that matter:

| Correction | Tool | Why not a re-add |
|---|---|---|
| "make it three" | `set_quantity` (absolute) | "**A QUANTITY TWEAK IS NEVER A RE-ADD**" |
| "one more" | `adjust_quantity` (delta) | delta and absolute are different intents |
| "the syrup, not the tablets" | `change_variant` | "**A VARIANT SWAP IS NEVER A RE-ADD EITHER** — he loses his place on the screen" |
| "I meant the 40" | `refine_item` | keeps the row and its history |
| "drop that" | `remove_items` | |
| picking from options | `choose` | |

The shared property: **identity is preserved**. The row stays where it is on
screen, so the caller's eye does not have to re-find it. That is the whole reason
the taxonomy exists — not tidiness, orientation.

## Proof — withheld authority

- `orderdesk`: "**You have no confirm tool and no confirm authority.**" The
  pharmacist presses Confirm; that gesture arrives as its own event and the brain
  closes in one line.
- `servicing`: `submit_packet` only goes through after the advisor approves.
- `aura`: `authenticate` is the one blocking tool in the demo set, and it blocks
  precisely because it is waiting on a human decision.
- The symmetric instruction, so the human's action is not undone by the agent:
  `orderdesk` — "**NEVER redo what he already did himself.**"

## Proof — correction by hand is a supported path, not an escape hatch

The pharmacist can tap a variant pill, type a quantity, delete a row, add from the
search bar. Each of those is its own typed event, and each says what it was
([7](07-who-owns-which-state.md)) — so a correction the agent never heard arrives
named rather than inferred from a diff. "Chose the 150 g gel for li3" is a
sentence the model can act on; "the cart is different now" is not.

## Gap

- **Nothing in the SDK expresses "the agent may not do this."** Withheld authority
  is achieved today by simply not writing the tool. That works, and it is
  invisible to a reviewer — there is no declaration to audit. Worth asking whether
  it should be declarable.
- **Open:** should there be a reserved *confirmation* action, given three demos
  hand-roll the same approve-on-screen gesture?
- We have **no worked example of correcting something already committed** — the
  compensating-call story stops at the confirm boundary.
- **Open:** how does the agent learn it misheard when the screen shows nothing? An
  ambient agent with no UI has none of these affordances. Every one of our eleven
  demos has a screen; the page should be honest that this design assumes one.
