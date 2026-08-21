---
title: Instrumenting a brain
description: What to log from the brain, how session.id joins your logs to the platform's, and the numbers that survive a budget review.
---

Two questions get asked of a voice agent, and they want different instruments.
*Why did this call go wrong?* is answered by your brain's logs lined up against
the platform's records. *Is this agent worth keeping?* is answered by aggregating
across calls. Write both before the pilot — the day a demo goes badly is too
late to start.

## The turn hook: `on_inference_finalized`

Fires once per LLM call, after the framework has committed the heard text to
`session.conversation`. Per-turn telemetry belongs here and nowhere else.

```python
import time

from voqalize.sdk import Brain, Inference

class MyBrain(Brain):
    async def on_interaction(self, interaction):
        self._t0 = time.monotonic()
        async with interaction.say() as speech:
            await speech.speak(await self.answer(interaction.transcript))

    async def on_inference_finalized(self, inference: Inference) -> None:
        logger.info(
            "turn interaction=%s inference=%s interrupted=%s heard_chars=%d latency_ms=%.0f",
            inference.interaction_id,
            inference.id,
            inference.interrupted,
            len(inference.heard),
            (time.monotonic() - self._t0) * 1000,
        )
```

`Inference` carries `interaction_id`, `id`, `heard`, `interrupted` and
`interaction`. Two of those are worth watching from day one:

**`interrupted`** is the user talking over the agent. A rising interruption rate
means the agent is too long, too slow, or wrong, and it is the best free proxy
for conversational quality you get.

**`heard` against what you generated** is what the user missed. Log both while
debugging verbosity; log the lengths alone in production, because `heard` is the
caller's words.

## The call envelope: `on_session_start` and `on_session_end`

```python
async def on_session_start(self, session, start):
    logger.info("session %s user=%s surface=%s",
                session.id, start.init.get("user", {}).get("id"), start.init.get("surface"))

async def on_session_end(self, session):
    logger.info("session %s outcome=%s turns=%d",
                session.id, self._outcome, len(session.conversation.messages))
```

Choose the `outcome` vocabulary deliberately — `booked`, `abandoned`,
`escalated`, `answered` — because every value question later reduces to it.

Do not rebuild the transcript. `session.conversation` already holds the
heard-truth record and the platform stores it per call. And do not log PII you
would not put in your own database: these are your logs, in your environment,
under your retention policy.

## `on_error` is congestion, not failure

```python
async def on_error(self, session, error) -> None:
    logger.warning("session %s runtime error: %s", session.id, error)
```

The runtime delivers these when it drops data under congestion. It never ends the
call. If they appear at all, the brain is emitting faster than the wire drains —
usually a loop that got away.

## `session.id` is the join key

Your brain's logs are not in `get_session_logs`. The brain runs in your
environment and logs wherever that environment logs; `get_session_logs` returns
the platform's own lines. The two sides line up because they use the same string:
`session.id` is the id in the URL the runtime dialled you on
(`{brain_url}/s/{session_id}`), the id the platform files the call under, and the
`session_id` stamped on every platform log line. There is no second identifier
and nothing to map. Log it on every line and grep your own logs for it.

The platform's half of the same call, over the [MCP tools](/docs/reference/mcp/):

| Tool | Answers |
|---|---|
| `list_sessions` | Which calls happened; filter by agent or state. |
| `get_session` | One call's envelope — state, timing, `agent_input`, `metadata`, which recordings exist. |
| `get_session_events` | What happened: platform milestones and the wire — transcripts, replies, actions, interruptions. Versioned contract. |
| `get_session_logs` | The runtime's log lines for that call. Evidence, not contract. |
| `get_recordings` | The audio, one track per side, behind a short-lived signed URL. |

Read them cheapest first: `get_session_events(..., source="platform")` to see
whether the call connected and where it stopped; then the full event stream to
see what was said. `disposition="dropped_in_drain"` on an event is the usual
explanation for *the brain replied and the screen never changed* — the caller
barged in and voice discarded the answer. Only then `get_session_logs(...,
level="WARNING")`, and only after that the `INFO` lines with a `service=` filter.

## The numbers that survive a budget review

| Metric | Where it comes from |
|---|---|
| Volume | Sessions per agent per day — `list_sessions`, filtered on `agent_id`. |
| Completion rate | Sessions reaching `ended` against `failed`. Read `expired` separately: a token that died with nobody on it is a broken embed, not a bad agent. |
| Call length | `duration_secs` on the session — what the runtime measured, not two control-plane timestamps subtracted. |
| Turn count | `get_session_events`. |
| Interruption rate | Inferences with `interrupted=True` — from your own `on_inference_finalized` line. |
| Task outcome | Your own `outcome=` at `on_session_end`. |
| Escalation rate | The share of those outcomes that were `escalated`. |

The first four come free from the platform. The last three come from the two log
lines above, which is why they get written before the pilot rather than after.

For a pilot, pick one headline number tied to a metric the customer already
tracks — deflection rate, cost per qualified lead, time to book — and instrument
it as an explicit `outcome=` value. A containment rate against their current
number is a number they can act on; a generic voice metric is one they have to be
talked into caring about.

## Test the instrumentation too

The offline harness sees all of this: `driver.errors` accumulates every
`ErrorFrame`, and `on_inference_finalized` fires under the conformance driver
exactly as it does in production. A test asserting your outcome field is set on
the abandon path is worth more than one more transcript assertion.

## Next

- **[Testing a brain](/docs/brain/testing/)** — reproduce a bad live call as an
  offline scenario.
- **[Where the brain runs](/docs/deploy/brain-url/)** — if the logs show the brain
  was never dialled at all.
