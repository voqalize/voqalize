# Instrumentation — logging, correlation, and proving it works

Two audiences, two jobs. **Debugging** asks "why did this call go wrong?" and is
answered by brain logs correlated with platform logs. **Value** asks "is this agent
worth keeping?" and is answered by aggregating across sessions. Instrument for both
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
key** — it is the id the platform files the call under, the one in the URL the
runtime dialled you on (`{brain_url}/s/{session_id}`) and the `session_id` stamped on
every platform log line, so your logs and the platform's line up with no extra
plumbing. There is no second identifier to map it to.

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
heard-truth record and the platform stores it per session. Don't log PII you wouldn't
put in your own database — brain logs are your logs, in your environment, under your
retention policy.

---

## Correlating with the platform

The MCP observability tools read the platform's side of the same call:

| Tool | Answers |
|---|---|
| `list_sessions(tenant, agent_id="", state="", limit=20, cursor="")` | Which calls happened; filter by agent or state. |
| `get_session(tenant, session_id)` | One call's envelope — state, timing, `agent_input`, `metadata`, which recordings exist. |
| `get_session_events(tenant, session_id, source, frame, disposition, limit)` | What happened: platform milestones **and** the wire — transcripts, replies, actions, interruptions. Versioned contract. |
| `get_session_logs(tenant, session_id, level, service, limit)` | **Platform runtime** log lines for that call. Evidence, not contract. |
| `get_recordings(tenant, session_id, ttl_seconds)` | The audio, one track per side, with a short-lived signed URL each. |

Debugging order, cheapest first:

1. `get_session_events(..., source="platform")` — did the call even connect, and
   where did it stop? Skipping the wire read makes this the cheap first question.
2. `get_session_events(...)` in full — did it say the right thing? Most bugs are
   visible here, and `disposition="dropped_in_drain"` explains the common "it replied
   but nothing happened": the caller barged in and voice discarded the answer.
3. `get_session_logs(..., level="WARNING")` — narrow to what actually broke on the
   platform side.
4. Only then read `INFO`/`DEBUG` with a `service=` filter (`pygato` is the voice
   runtime, and the one worth reading first).

**Your brain's logs are not in `get_session_logs`** — the brain runs in the
customer's own environment and logs wherever that environment logs. That is precisely
why you log `session.id`: it is the same string the platform files the call under, so
grep your own logs for it. One identifier, both sides.

---

## Demonstrating business value

Aggregate over `list_sessions` + `get_session_events` and you have a report without
building an analytics pipeline:

| Metric | Where it comes from |
|---|---|
| **Volume** | Count of sessions per agent per day (`list_sessions`, filter `agent_id`). |
| **Completion rate** | Share of sessions reaching `ended` vs. `failed` — and note `expired`, the token that died with nobody on it, which is a broken embed rather than a bad agent. |
| **Call length / turn count** | `duration_secs` off the session — what the runtime measured, not two control-plane timestamps subtracted; turns from `get_session_events`. |
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
