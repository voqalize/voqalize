---
title: Testing a brain
description: Drive your brain over the real wire in text mode — no audio, no browser, no human — then inspect a live call.
---

The hard part of shipping a voice agent is usually not the voice. It's that every
change appears to need a person with a microphone. It doesn't.

The SDK ships **`voqalize.conformance`**: a protocol-compliant *fake Voqalize*. It
hosts your real `Brain` on a real WebSocket, mints a real runtime token, speaks the
real `Vql*` wire, models playout and heard-truth the way the runtime does — and lets
you drive it in **text mode**. `user_says("…")` in, a `Turn` with `.text` out.

That makes a voice agent testable like any other service, and it is the eval
primitive: a scenario is a conversation script plus assertions. Keep a scenario file
per use case in your repo and run it in CI.

## Set it up

```python
from voqalize.conformance import (
    DirectConnection, VoiceDriver, generate_keypair, mint_pygato_token,
)
from voqalize.sdk import DirectAgent, brain_factory
from mybrain import MyBrain

keypair = generate_keypair()
agent = DirectAgent(
    factory=brain_factory(MyBrain),
    host="127.0.0.1",
    port=0,                                   # ephemeral — tests never collide
    public_keys=keypair.public_pem,
)
port = await agent.start()

token = mint_pygato_token(
    private_key_pem=keypair.private_pem,
    session_id="s1", agent_id="agent_test", tenant_id="tenant_test",
)
driver = VoiceDriver(
    DirectConnection(f"ws://127.0.0.1:{port}", "s1", token=token),
    session_id="s1", agent_id="agent_test", default_timeout=10.0,
)
await driver.open()
```

The brain verifies against the public half of the keypair and the driver signs with
the private half, so **token verification runs for real** rather than being switched
off.

## Drive it

| Call | Drives | Returns |
|---|---|---|
| `start_session(payload={…})` | `VqlStart`; plays out the greeting (interaction 0). `payload` arrives brain-side as `start.init`. | `Turn \| None` |
| `user_says("…")` | One user turn, played out and finalized. | `Turn` |
| `barge_in("…")` | Start a turn, let the brain speak, interrupt, finalize the cut with partial heard-truth. | `Turn` |
| `client_message(type, data)` | A browser message the brain **answers** via `message.interaction`; waits for the reply. | `Turn` |
| `send_client_message(type, data)` | A browser message the brain **ingests silently**. | `interaction_id` |
| `user_idle(level=1, idle_ms=30000)` | An idle trigger; plays out `on_user_idle`. | `Turn` |
| `send_action_outcome(action_id, status=, result=)` | The UI reporting back; fires the brain's `callback=`. | — |
| `collect_ui_commands(min_count=1)` | Waits for and returns the `ui_command` envelopes the brain fired. | `list[dict]` |
| `end_session()` / `aclose()` | `End` frame + teardown. | — |

## Assert on it

A `Turn` carries `.text` (everything spoken this turn), `.completed`, `.interrupted`,
`.heard` (for a barge-in: the partial the user actually heard), and `.inferences`
(per-LLM-call `.text` / `.spoke` / `.tool_calls` / `.inference_id`).

`.completed` is the most valuable single assertion — a false there usually means the
brain hung or raised.

```python
async def test_answers(driver):
    await driver.start_session()
    turn = await driver.user_says("Add two oat milks to my cart.")
    assert turn.completed
    assert "oat milk" in turn.text.lower()

    cmds = await driver.collect_ui_commands(min_count=1)
    add = next(c for c in cmds if c["action"] == "add_to_cart")
    assert add["sku"] == "oat-milk" and add["qty"] == 2
```

The driver also accumulates `driver.ui_commands`, `driver.errors`,
`driver.tts_settings`, `driver.stt_settings` and `driver.idle_settings` — so *"did
the brain switch to Hindi when asked?"* is an assertion on `tts_settings`, not a
listening exercise.

:::tip[Determinism]
The driver *is* the runtime, so it dictates the timing a real call can't reproduce:
exactly when a barge-in lands (`speak_delay`, `wait_for_speech`, `wait_for_complete`)
and exactly what heard-truth the brain is told (`heard_prefix=`). Use those instead
of sleeping and hoping.
:::

If the brain calls a real LLM, tests get slow and flaky for the usual reasons. Inject
a scripted fake (`brain_builder=lambda: MyBrain(llm=FakeLLM())`) and keep one slow
test against the real model as a smoke check.

## The built-in protocol suite

Beyond your own scenarios, the harness ships a sixteen-scenario catalog — the bar a
brain must clear to be wire-compatible: greeting, interaction/inference id
monotonicity, bracket integrity, barge-in drain, heard-truth reconciliation across
multiple interruptions, action-outcome correlation, client-message delivery, idle
re-engagement, and bad-token rejection.

```bash
# Point it at any brain that speaks the wire.
python -m voqalize.conformance --brain-url ws://127.0.0.1:8787 --no-auth --no-reference

# Prove the harness itself: host the bundled reference brain, run everything.
python -m voqalize.conformance --self-test
```

:::caution[Use `--no-reference` against your own brain]
The deep-semantics scenarios need a cooperating brain that speaks the reference
command grammar (`voqalize.conformance.reference.ConformanceBrain`). Against an
ordinary brain they fail for the wrong reason. `--no-auth` only if the brain runs
`allow_unverified`.
:::

`--only name1,name2` restricts the run; the exit code is 0 iff conformant.
Programmatically it's `run_suite(brain_url, private_key_pem=…,
include_reference=False)` → a `Report` with `.ok`, `.passed`, `.failed`,
`.summary()`.

## Then: inspect a live call

Once a human has actually talked to the agent, read the call back over the
[MCP tools](/docs/reference/mcp/):

```
list_meetings(tenant, agent_id=…, limit=20)   # find it — most recent first
get_meeting(tenant, meeting_id)                # transcript, turn by turn
list_meeting_events(tenant, meeting_id)        # lifecycle: created/started/ended/errors
query_logs(tenant, meeting_id, severity_min="WARNING")
```

Cheapest first: transcript (did it say the right thing?), then events (how far did it
get, and why did it end?), then logs. `query_logs` returns the **platform's** log
lines; your brain logs in your own environment — join the two on the meeting's
`active_session_id`, which is the brain's `session.id`.

When a live call misbehaves in a way the offline suite passed, that gap **is** the
next scenario. Reproduce it offline first, then fix it.

## Next

- **[Handling a conversation](/docs/brain/conversation/)** — heard-truth, barge-in,
  and what the framework commits for you.
- **[MCP server & Claude Code skill](/docs/reference/mcp/)** — the observability
  tools, and the skill that runs this loop for you.
