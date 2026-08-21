# 4. Parallel workstreams

> **The surprise.** Voice is fast for one reason only: the caller can say five
> things in a row *without waiting* for any of them. An agent that handles them
> one at a time hands that entire advantage back, and ends up slower than the form
> it replaced.

## Belief

- The speed of voice is not in the transport. It is in the *absence of a
  round-trip per intent*. A form makes you wait for each field to render. Speech
  does not.
- So the agent must accept a burst and **fan it out** — several units of work in
  flight at once, resolving at different times, out of order.
- Which forces the real design question: **how does a result come back?** Voice is
  a serial channel and there are now three things to report. The answer is almost
  never "read them out." It is a task list on screen, or one short spoken question
  about the only item that is genuinely ambiguous.
- **Corollary:** parallelism is not an optimisation you add later. Without it the
  interaction model does not work, because the caller's natural behaviour — the
  burst — becomes the worst case.

## Facts

- `session.dispatch(...)` **never blocks** and is callable from anywhere,
  including from work that outlived the turn that started it. That is what makes
  a late result deliverable at all (`Session.dispatch` docstring).
- An action carries no audio, so it needs no floor — a background job can paint
  the screen without waiting for the agent to stop talking.
- `ActionHandle` awaits a `Result`. The docstring's warning is the whole discipline
  in one line: "say something first, because you are holding the floor and an
  `await` with no preceding speech is dead air."
- `Result(action_id, status: "ok" | "error" | "timeout", data, error)` —
  **timeout is the same callback with a different status**, not a separate path.
  `DEFAULT_ACTION_TIMEOUT_S = 30.0`, per-dispatch via the `timeout_s` control
  field.
- `on_result` is a control field on the action, not a payload field: the resolution
  path is declared at dispatch.
- `on_app_message` is deliberately **not** a generator (`brain.py`). The browser
  pushing state must not be able to seize the floor. Background completion
  reports through actions and history, not through the mouth.

## Proof

- **`servicing` states the belief outright.** "THE BIG IDEA — WORKING ONE CASE
  DOESN'T FREEZE THE OTHERS… background prep jobs that run on their own while the
  advisor keeps clicking and talking… They are never blocked."
  `prepare_case` returns immediately with
  `{"status": "preparing_in_background", "note": "Running in the background; the
  advisor stays unblocked. Tell them when ready."}` — the return value is
  *instructions to the model about how to behave while waiting*.
- **`orderdesk` teaches the model to batch.** "Do not wait for the previous one to
  resolve… take them all in ONE `add_items` call with a list." And symmetrically,
  on the way out: "**Batch your questions.**"
- **`orderdesk`'s shadow order book is the fan-out made visible.** Items enter as
  `status="resolving"` and move to `multi_family` / `multi_variant` / `matched` /
  `not_found` independently, each on its own background refinement. The caller
  keeps talking; rows settle underneath. See [7](07-who-owns-which-state.md) — the
  same structure is also the state answer.
- **`forge` reports progress without speaking.** "Every tool you call also shows up
  as a live task on screen (a small 'activity' checklist), so your actions are
  already acknowledged visually — trust it and stay quiet." That is the on-screen
  task list, shipped.
- **`aura`'s blocking tool is the deliberate exception.** `authenticate` awaits an
  `asyncio.Future` resolved from `on_client_message` — because it is waiting on
  *the human*, not on a machine. Machine work never blocks; human consent does.

## The three ways a late result surfaces

| Way | When | Shipped in |
|---|---|---|
| A row changes on screen, silently | The result is legible and unambiguous | `orderdesk`, `forge` |
| One short spoken line | It changes what the caller should do next | `servicing` ("tell them when ready") |
| A spoken question | Genuinely ambiguous, and only the caller can resolve it | `orderdesk` `ask_choice` |

The default is the first. Speaking is the exception, and it costs a turn.

## Gap

- There is no SDK affordance for "a task list" — every demo builds its own action
  and its own React component. If the on-screen checklist is the canonical way a
  fan-out reports, it is a candidate for a *reserved* action, the way `avatar` is.
- **Open:** ordering. If three background jobs finish at once, three dispatches hit
  the browser in the order they ran. Does the UI need a sequence number to render
  a stable list, or does last-write-wins per row suffice? `orderdesk` answers this
  by sending the whole row rather than a patch — but that is a demo's convention,
  not a documented rule.
- **Open:** we have no worked example of a fan-out where one branch *fails*. Every
  demo's background work succeeds. The error path is the one a customer will hit
  first.
