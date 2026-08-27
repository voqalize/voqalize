# 6. Tool design for voice

> **The surprise.** A tool that waits is a bug. In voice, every tool returns
> immediately — often with nothing but a promise — is never cancelled, and is
> undone by a compensating call rather than by an abort.

## Belief

- **No synchronous tasks, ever.** A tool that takes two seconds spends them as
  dead air, because the model cannot speak while it is waiting for a result it
  asked for.
- So the return value's job changes: it is not *the answer*, it is **instructions
  to the model about how to behave while the answer is on its way**.
- **Tools are uninterruptible, and that is correct.** Cancelling a tool call on
  barge-in sounds tidy and is wrong: the caller interrupted the *speech*, not the
  work, and half-applied work is worse than completed work. It should not matter,
  because —
- **Tools are cheap and easy to undo.** The undo is a compensating call
  (`remove_items`, `set_quantity` back), not a rollback. A tool expensive enough
  that you want to cancel it is a tool that should have been split into a cheap
  dispatch plus a background workstream.
- **Tools are typed**, and **errors are returned from the model's point of view** —
  a sentence the model can act on, never an exception that kills the turn.

## Facts

- `session.dispatch(...)` **never blocks and returns nothing**. There is no handle
  to await, no result correlation and no timeout: the brain says what it wants
  rendered and moves on. An answer, if the app has one, arrives later as an
  ordinary `client-message` at `on_rtvi`, correlated by whatever the app put in
  it — which is exactly how every other tap already arrives.
- The action rides RTVI's own `ui-command`, `{"command": …, "payload": {…}}`, so a
  stock pipecat client reads it with `useUICommandHandler` and no adapter of ours.
  The payload is **nested**, so no field can shadow the envelope and there is no
  reserved-name rule to remember.
- **Typed by construction:** an `Action` is a Pydantic model; the wire name is the
  class name in snake_case (`__voqal_action__` to pin it); serialised
  `model_dump(by_alias=True, mode="json")`; JSON Schema export makes the
  TypeScript half generatable rather than hand-copied.
- **A failed tool call is a result, not an exception** — the "errors from the
  model's POV" mechanism. `sdk/gemini_interactions.py`: `_failed(...)` returns a
  `FunctionResultStep` carrying `is_error=True`, so the model reads what went
  wrong and calls again. The code comment's phrase is "**never a dead turn.**"
  `is_error` is the half the automatic path has no room for: there a failure
  reaches the model as an ordinary payload and gets narrated as success.
- Interruption cancels the *turn* (`_cancel_turns()`, generator `aclose()`), not
  dispatched actions or in-flight work — see [3](03-interruption-and-heard-truth.md).

## Proof

- **The immediate-return contract, verbatim.** `servicing`'s `prepare_case`:
  `{"status": "preparing_in_background", "note": "Running in the background; the
  advisor stays unblocked. Tell them when ready."}` — a return value that is
  entirely behavioural instruction.
- **Validation as a retriable error.** `orderdesk`'s `ask_choice` is rejected
  unless it has 2–4 choices, uses known codes, and covers every candidate — and
  the prompt tells the model what happens: "the tool rejects a choice set that
  leaves a code uncovered, and you will have to call again."
- **A guard that shapes output.** `orderdesk`'s English-only `field_validator` on
  choice labels returns a retriable tool error rather than passing Devanagari
  labels through to a screen that must stay Latin.
- **Compensating calls, as a taxonomy.** `orderdesk` gives the model six distinct
  edit tools instead of one re-add, and shouts the reason:
  - "**A QUANTITY TWEAK IS NEVER A RE-ADD**" (`set_quantity` absolute /
    `adjust_quantity` delta)
  - "**A VARIANT SWAP IS NEVER A RE-ADD EITHER** — he loses his place on the
    screen" (`change_variant`)
  - plus `refine_item`, `remove_items`, `choose`.
  Every one of these is the undo for a different mistake, and each preserves the
  row's identity so the screen does not jump.
- **Authority withheld on purpose.** "**You have no confirm tool and no confirm
  authority.**" The agent cannot commit the order; the pharmacist presses Confirm.
  `servicing` is the same shape: `submit_packet` only goes through after the
  advisor approves. See [9](09-misunderstanding-and-reversal.md).
- **Floor-free tools exist.** `orderdesk`'s `catalog_search` and `list_variants`
  are answered with "a **floor-free** action — session-scoped, no inference, no
  speech — so neither a keystroke nor a tap can make the agent start talking over
  him."
- **The one sanctioned blocking tool.** `aura`'s `authenticate` awaits an
  `asyncio.Future` resolved in `on_client_message`. It blocks because it is
  waiting on a *human decision*, which is the only thing worth waiting for.

## The shape, as a checklist

1. Returns in single-digit milliseconds, or returns a promise and a note.
2. Typed arguments; bad arguments come back as an error the model can read.
3. Has an undo that is another tool call, not a rollback.
4. Preserves identity of what it touched, so the screen does not re-render from
   scratch.
5. Never holds authority over anything irreversible.

## Gap

- We have **no documented pattern** for "tool starts background work and reports
  later" beyond `servicing`'s convention. Dispatch paints the screen the moment
  the work lands; server-side background work is bare `asyncio`.
- **Open:** should the SDK own a task-list abstraction, given that four demos have
  independently built one? See [4](04-parallel-workstreams.md).
- **Open:** the "tools are cheap" premise is a design rule we follow, not one the
  framework enforces. Nothing stops a customer awaiting a 4-second HTTP call
  inside `dispatch_tool`. Is there a guard worth adding — a warning when a tool
  body exceeds a threshold?
- No demo exercises `status="timeout"`. It is the path a customer will meet first
  and the one we have never demonstrated.
