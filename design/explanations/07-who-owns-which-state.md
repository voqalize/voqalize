# 7. Who owns which state

> **The surprise.** We own the conversation and you own everything else — so every
> turn is a **merge**, and the merge is your code. There is no single place the
> truth lives, and any design that pretends otherwise loses one half of it.

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
- **The screen usually wins.** It is the surface the human is looking at and
  acting on; the agent's memory of what it did is a hypothesis about the screen.
  Two demos independently arrived at the same rule.
- **The under-appreciated part is the clock, not the ownership.** The agent's
  belief is always at least one turn old, and the human edits between turns.

## Facts

- **Conversation state is ours, delivered as events.** `Finalize(inference_id,
  heard, interrupted)` after playout ([3](03-interruption-and-heard-truth.md)) —
  and `heard` is a fact you cannot compute.
- **Screen state is yours, delivered as `state_sync`.** It lands on
  `on_app_message`, which is deliberately **not a generator**: the browser
  pushing state must not be able to take the floor. The default handler parks it
  on `browser_state`.
- **The merge point is `grounding()`** — the seam that folds your state into the
  model's next call with no tool round trip ([5](05-prompt-design.md)). It goes in
  at the **tail**, just before the latest user turn, never into the system prompt:
  the merged view is the most volatile thing in the context and the system prompt
  is the least ([8](08-getting-information-to-the-model.md)).
- **`session_id` is the join key** across both halves; `get_session_events(source=…)`
  over the MCP server returns our side of the same session.
- **An action carries the whole row, not a patch** — so a re-render is idempotent
  and a dropped message does not leave the screen holding a half-applied diff.
- `inference_id` is the brain's alone (commit `aa6754e`) — a stable handle for
  joining what was generated to what was heard.

## Proof — the shadow order book

`orderdesk` is the fullest worked example we have, and it is worth reading as the
canonical answer:

- **Two writers, one cart.** "the pharmacist's phone and the voice call drive one
  store, so the agent and the pharmacist edit the same cart" (`store.tsx`).
- **Two bridges.** Brain → screen as typed actions; screen → brain as `state_sync`
  "on every `rev` bump, so the agent's grounding always shows the *authoritative*
  cart — including everything the pharmacist tapped by hand."
- **A staging area with a lifecycle.** `LineItemView.status` is
  `resolving → multi_family | multi_variant → matched | not_found`. Rows enter
  uncommitted, carry `spoken_text` **beside** the resolved `sku` so the heard
  phrase survives resolution, and settle independently while the caller keeps
  talking. `source: "agent" | "manual"` records who put each row there.
- **The merge is explicit and the screen wins.** `grounding()`: "The browser's own
  `state_sync` snapshot wins — it is the authoritative cart and it carries the
  pharmacist's manual edits… with this brain's mirror as the fallback for the
  first beat."
- **The merge is two-way.** `self.desk.absorb(live)` folds the snapshot's
  `candidate_codes` back into the brain's mirror *before* computing what to ask:
  "a group pill the pharmacist tapped narrows the row *here*, so the PENDING line
  says 'narrowed to 6 — ask the next question' rather than repeating the question
  he just answered with his thumb."
- **The feedback channel is designed as one.** From `store.tsx`: "`candidate_codes`
  is the sharpest-question feedback channel… a pill tap the agent never heard
  shows up on its next grounding as a *smaller* set — that is how it knows to ask
  the next question, or that the row already answered itself."
- **The behavioural rule that falls out:** "**NEVER redo what he already did
  himself.**"

## Proof — the same shape, smaller

- `servicing`: `get_advisor_context` reports which case and which tab is open; the
  agent steers the screen the advisor is already on.
- `aura`: `get_screen_context` reads the same `state_sync` snapshot, appended as a
  trailing user turn each turn.
- `forge`: the workspace snapshot is folded into every turn's working context, and
  before any snapshot arrives there is **deliberately no grounding at all**.

## The generalisation this page should make

**A shadow copy with a settling workflow.** Hold an uncommitted mirror of the
thing being built, let background refinement move each element toward committed,
keep the raw heard phrase beside the resolved value, and let the human's direct
edits win. It is not an ordering pattern — it is what any voice agent that builds
a structured artifact under dictation needs. Naming and generalising it is the
main job of the page this outline becomes.

## Gap

- The pattern above exists once, in one 1600-line demo, and is not named anywhere.
- **Open:** does the SDK owe a helper here (a `ShadowState` base), or is naming it
  enough? My position: name it first; a helper that guesses the merge rule would
  be worse than none.
- **Open:** conflict semantics have no rule. If a `state_sync` and a dispatched
  action cross on the wire, the demo relies on the browser diffing by id and
  last-write-wins per row. That is a convention, unstated and untested.
- We have no page and no example of a **server-owned** third state (a CRM the
  browser cannot see) taking part in the merge. Every demo's other state is the
  screen.
