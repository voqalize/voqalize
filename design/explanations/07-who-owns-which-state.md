# 7. Who owns which state

> **The surprise.** We own the conversation and you own everything else — and the
> temptation is to reconcile the two halves every turn. Don't. Hold **one** mirror
> and let both writers name what they changed; the merge you were about to write
> is the bug you were about to ship.

## Belief

- A voice session has at least six moving parts, with different owners and
  different clocks:

  | What | Who owns it | Changes when |
  |---|---|---|
  | What the caller said | **Voqalize** | the recognizer finalizes |
  | What the caller actually **heard** | **Voqalize** | playout ends or is cut |
  | What is on screen right now | **you** (the browser) | a click, a render, a push |
  | Your knowledge base / catalog / CRM | **you** | on its own schedule |
  | Which tool calls happened and what they returned | **you** | mid-turn |
  | The model's own history | **you** | you write it |

- Nobody can merge these but you, because only you know which of them wins when
  two disagree. Our job is to hand you our two cleanly and never to guess at
  yours.
- **The screen usually wins**, but that is not a merge rule — it is a rule about
  which writes are allowed. The agent's memory of what it did is a hypothesis
  about the screen only for as long as the screen can change without telling it.
- **The under-appreciated part is the clock, not the ownership.** The agent's
  belief is always at least one turn old, and the human edits between turns. The
  cure is not a better merge; it is the human's edit arriving as a fact.

## Facts

- **Conversation state is ours, delivered as events.** `Finalize(speech_id,
  heard, generated)` after playout ([3](03-interruption-and-heard-truth.md)) —
  and `heard` is the one of the three you cannot compute, which is why it is the
  only one that travels.
- **Screen state is yours, delivered one gesture at a time as a typed
  `AppEvent`.** It lands on `on_rtvi`, which is deliberately **not a generator**:
  the app must not be able to take the floor by acting, and an app message mints
  no turn.
- **There is no merge point, and that is the correction this page owes.** A
  snapshot needs merging because two pictures have to be reconciled. A named
  gesture is applied: `apply_event` patches the one mirror, the brain's own
  dispatches patch it too, and the model reads that mirror through a tool. What
  reaches the context is one line saying what moved
  ([5](05-prompt-design.md), [8](08-getting-information-to-the-model.md)).
- **`session_id` is the join key** across both halves; `get_session_events(source=…)`
  over the MCP server returns our side of the same session.
- **An action carries the whole row, not a patch** — so a re-render is idempotent
  and a dropped message does not leave the screen holding a half-applied diff.
- `speech_id` is the brain's alone — a stable handle for joining what was
  generated to what was heard. Voqalize quotes it back and never reads it.

## Proof — the shadow order book

`orderdesk` is the fullest worked example we have, and it is worth reading as the
canonical answer:

- **Two writers, one cart.** "the pharmacist's phone and the voice call drive one
  store, so the agent and the pharmacist edit the same cart" (`store.tsx`).
- **Two bridges, both typed, both generated from the same module.** Brain → screen
  as an `Action` on `ui-command`; screen → brain as an `AppEvent` on `ui-event`.
  `voqalize types` emits both TypeScript unions, so a gesture the brain does not
  handle is a compile error rather than a silent drop.
- **A staging area with a lifecycle.** `LineItemView.status` is
  `resolving → multi_family | multi_variant → matched | not_found`. Rows enter
  uncommitted, carry `spoken_text` **beside** the resolved `sku` so the heard
  phrase survives resolution, and settle independently while the caller keeps
  talking. `source: "agent" | "manual"` records who put each row there.
- **One mirror, patched from both sides.** A group pill the pharmacist taps
  arrives as its own event and narrows the row *in the brain*, so `pending()`
  reads the mirror alone and says "narrowed to 6 — ask the next question" rather
  than repeating the question he just answered with his thumb.
- **Echo suppression died by construction.** A brain's own dispatch is not a
  gesture, so it produces no event and there is nothing to suppress. The flag that
  used to do it, and the diff it protected, are both gone.
- **The behavioural rule that falls out:** "**NEVER redo what he already did
  himself.**"

## Proof — the same shape, smaller

- `servicing`: `get_advisor_context` reports which case and which tab is open; the
  agent steers the screen the advisor is already on.
- `aura`: `get_screen_context` reads the brain's own mirror; the twenty-two typed
  gestures the page sends are what keep it true.
- `forge`: the same shape with a second kind of note — a test run finishing is the
  *browser's* computation rather than anybody's decision, so it arrives through
  `ScreenState.happened` carrying its result.

## The generalisation this page should make

**A shadow copy with a settling workflow.** Hold an uncommitted mirror of the
thing being built, let background refinement move each element toward committed,
keep the raw heard phrase beside the resolved value, and let the human's direct
edits win. It is not an ordering pattern — it is what any voice agent that builds
a structured artifact under dictation needs. Naming and generalising it is the
main job of the page this outline becomes.

## Gap

- The pattern above exists once, in one 1600-line demo, and is not named anywhere.
- **Settled:** the SDK owes the *transport*, not the merge. `AppEvent` /
  `AppEvents` ship in `sdk/python`; `ScreenState` is a demo helper because the
  read tool and the actor's name are things only a brain can supply.
- **Settled:** conflict semantics no longer need a rule. Two writers to one mirror
  in one event loop, each write naming exactly what it changes, cannot produce the
  crossing case a snapshot and a dispatch used to.
- We have no page and no example of a **server-owned** third state (a CRM the
  browser cannot see) taking part in the merge. Every demo's other state is the
  screen.
