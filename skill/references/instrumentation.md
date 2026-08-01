# Instrumentation — logging, correlation, and proving it works

Two audiences, two jobs. **Debugging** asks "why did this call go wrong?" and is
answered by brain logs correlated with platform logs. **Value** asks "is this agent
worth keeping?" and is answered by aggregating across meetings. Instrument for both
from day one; retrofitting after a demo goes badly is too late.

---

## What to log from the brain

### `on_inference_finalized` — the turn-level metric hook

Fires once per LLM call, **after** the SDK has already committed the heard text to
`session.conversation`. This is where per-turn telemetry belongs.

```python
import time
from voqalize.sdk import Brain, Inference, Session

class MyBrain(Brain):
    async def on_interaction(self, interaction):
        self._t0 = time.monotonic()
        async with interaction.say() as speech:
            await speech.speak(await self.answer(interaction.transcript))

    async def on_inference_finalized(self, inference: Inference) -> None:
        logger.info(
            "turn interaction={} inference={} interrupted={} heard_chars={} latency_ms={:.0f}",
            inference.interaction_id,
            inference.id,
            inference.interrupted,
            len(inference.heard),
            (time.monotonic() - self._t0) * 1000,
        )
```

`Inference` gives you `interaction_id`, `id`, `heard`, `interrupted`, and
`interaction`. Two signals matter most:

- **`interrupted`** — the user talked over the agent. A rising interruption rate means
  the agent is too verbose, too slow, or wrong. This is the single best quality proxy
  you get for free.
- **`heard` vs. what you generated** — the gap is what the user missed. Log both when
  debugging verbosity; log only lengths in production.

### `on_error` — non-fatal runtime signals

```python
async def on_error(self, session: Session, error) -> None:
    logger.warning("session {} runtime error: {}", session.id, error)
```

The runtime delivers these when it has to drop data under congestion (drop-newest).
It never kills the session. If these appear at all, the brain is emitting faster than
the wire drains — usually a runaway loop.

### `on_session_start` / `on_session_end` — the call envelope

Log `session.id` at start with whatever business context `start.init` carried (user
id, plan, cart value, ticket id). Log the outcome at end. **`session.id` is the join
key** — it is the same string the platform reports as a meeting's
`active_session_id` and as the `session_id` on every platform log entry, so your logs
and the platform's line up with no extra plumbing.

```python
async def on_session_start(self, session, start):
    logger.info("session {} user={} surface={}",
                session.id, start.init.get("user", {}).get("id"), start.init.get("surface"))

async def on_session_end(self, session):
    logger.info("session {} outcome={} turns={}",
                session.id, self._outcome, len(session.conversation.messages))
```

Structure your own outcome field deliberately — `booked` / `abandoned` /
`escalated` / `answered`. It is the field every value question later reduces to.

### What *not* to log

Don't rebuild the transcript: `session.conversation` already holds the faithful,
heard-truth record and the platform stores it per meeting. Don't log PII you wouldn't
put in your own database — brain logs are your logs, in your environment, under your
retention policy.

---

## Correlating with the platform

The MCP observability tools read the platform's side of the same call:

| Tool | Answers |
|---|---|
| `list_meetings(tenant, agent_id="", state="", limit=20)` | Which calls happened; filter by agent or lifecycle state. |
| `get_meeting(tenant, meeting_id)` | The transcript + recordings for one call. |
| `list_meeting_events(tenant, meeting_id)` | Lifecycle milestones — created / started / ended / errors. How far it got and why it stopped. |
| `query_logs(tenant, meeting_id, severity_min, component, limit)` | **Platform runtime** log lines for that call (voice runtime + control plane), each stamped with `session_id`. |

Debugging order, cheapest first:

1. `get_meeting` — did it say the right thing? Most bugs are visible here.
2. `list_meeting_events` — did the call end where you expected, or fail?
3. `query_logs(..., severity_min="WARNING")` — narrow to what actually broke on the
   platform side.
4. Only then read `INFO`/`DEBUG` with a `component=` filter.

**Your brain's logs are not in `query_logs`** — the brain runs in the customer's own
environment and logs wherever that environment logs. That is precisely why you log
`session.id`: take `active_session_id` off the meeting (or `session_id` off a log
line) and grep your own logs for the same string. One identifier, both sides.

---

## Demonstrating business value

Aggregate over `list_meetings` + `list_meeting_events` and you have a report without
building an analytics pipeline:

| Metric | Where it comes from |
|---|---|
| **Volume** | Count of meetings per agent per day (`list_meetings`, filter `agent_id`). |
| **Completion rate** | Share of meetings reaching a `closed`/ended state vs. `failed` (meeting `state` + events). |
| **Call length / turn count** | Event timestamps (start → end); turns from the transcript in `get_meeting`. |
| **Interruption rate** | Share of inferences with `interrupted=True` — from **your** `on_inference_finalized` logs. The conversational-quality number. |
| **Task outcome** | Your own `outcome=` field logged at `on_session_end` — bookings made, tickets deflected, leads qualified. |
| **Containment / escalation** | Share of sessions whose outcome was `escalated`. The number a support buyer actually asks for. |

The first three come free from the platform. The last three come from the two log
lines above — which is why you write them before the pilot, not after.

For a pilot, pick **one** headline number tied to the customer's existing metric
(deflection rate, lead qualification cost, time-to-book) and instrument it explicitly
as an `outcome=` value. Generic voice metrics don't survive a budget review; a
containment rate against their current number does.

---

## Testing your instrumentation

The offline harness sees this too: `driver.errors` accumulates every `ErrorFrame`,
and `on_inference_finalized` fires under the conformance driver exactly as it does in
production. A test that asserts your outcome field is set on the abandon path is
worth more than one more transcript assertion.

## Read next

- **`references/testing.md`** — reproduce a bad live call as an offline scenario.
- **`references/transport.md`** — if logs show the brain was never dialed at all.
