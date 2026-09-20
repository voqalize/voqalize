# L2 — latency, failure and limits

Read when: the turn waterfall, timeouts, what the user hears when the brain is
down, reconnection, interruption, background work, or session limits.

## The waterfall

Per turn, Voqalize publishes: user stopped speaking → words recognized → brain
dialled → brain's first byte → first audible sample. The homepage draws these to
scale, and the brain's span is by far the widest — that is the honest picture,
and it is why the page shows the shape rather than a number.

**No per-layer latency figure is published.** The instrument ships; the claim
does not. Anyone sizing a deployment should measure their own brain first,
because it dominates.

## Slow brain, mid-turn

If a turn produces no text within **ten seconds**, Voqalize speaks a fixed line —
*"Sorry — that's taking longer than I expected."* — and **the session stays up**.
Only that turn's answer is missing; the next turn proceeds normally.

That line and the unreachable-brain line below are the only sentences Voqalize
ever puts in the agent's mouth. Nothing else is synthesized on the brain's
behalf, and there is no hosted fallback brain any more — an agent with no
`brain_url` is refused at connect with `409 agent_not_configured` rather than
answering in a voice the developer never wrote.

## Unreachable brain

On the **first** connect, Voqalize retries with backoff from 100 ms and gives up
at **ten seconds**. Close code 4000 from the brain stops retries immediately.

If it never connects, the user hears *"Sorry — I can't reach the assistant right
now. Please try again shortly."* and the call ends about six seconds later.

## Crash mid-call

**The socket is the session, and it is not reconnected.** Once the brain has
answered, any close ends the call. There is no resume, no replay, no buffered
turn waiting for a new connection.

This is a design position rather than a missing feature: connection state *is*
liveness. A reconnect protocol would have to define what the user heard, what the
brain believes it said and who wins — and the honest answer to each during a
dropped call is "end it and let them redial".

State that must survive belongs in the customer's own store, written from inside
the brain.

## Interruption

Voqalize stops mid-word. On `Finalize` the brain receives the **heard prefix**
per speech unit — what the user actually heard, not what was queued. The brain's
history must record that prefix; otherwise the model's next turn refers to a
sentence nobody heard.

The watermark only moves forward. There is no rollback.

Known structural limit: a turn holds many speech units, so **silence between
units is not detectable** from the wire's shape alone. Dead air inside a turn is
tracked as an open epic rather than claimed as solved.

## Background work

Work that outlives its turn is normal: the brain announces it, returns the turn,
and opens a new speech unit later when the result lands. A tool announces and
returns — never block a turn waiting for the UI or for a slow backend. If the
brain needs something from the page, make it an unfabricable parameter on the
next call rather than a wait.

## Limits

- **Session cap: one hour.** `end_reason` is `max_duration`. A session still
  reading `active` five minutes past the cap settles as `lost`.
- **Idle**: `idle.timeout_ms` defaults to `0`, meaning off; ceiling 300000.
  `on_user_idle` never fires until you set it.
- **Concurrency and sessions per day**: tier limits exist in the model but are
  **not enforced during developer preview**, and no public concurrency ceiling is
  committed. A pilot with a known peak should be discussed before it runs rather
  than discovered.
- **Management API**: rate limited per tenant, `429` with `Retry-After`. MCP: 120
  tool calls per minute per tenant.

The largest number we will state is the observed one: **1,143 simultaneous
conversations**, a peak on one nationwide campus event on the voice tier — an
observation, not a load test and not a guarantee.
