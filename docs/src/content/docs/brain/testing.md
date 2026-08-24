---
title: Testing a brain
description: Drive your brain over the real wire in text mode — no audio, no browser, no human — then inspect a live call.
---

The hard part of shipping a voice agent is usually not the voice. It's that every
change appears to need a person with a microphone. It doesn't.

The SDK ships **`voqalize.conformance`**: a fake Voqalize that speaks
[the wire](/docs/reference/wire/). It hosts your real `Brain` on a real WebSocket,
mints a real brain-connection token, and models playout and heard-truth the way
Voqalize does — and lets you drive it in **text mode**. `user_says("…")` in, a `Turn` with
`.text` out.

That makes a voice agent testable like any other service, and it is the eval
primitive: a scenario is a conversation script plus assertions. Keep a scenario file
per use case in your repo and run it in CI.

## Set it up

```python
from voqalize.conformance import (
    DirectConnection, VoqalizeDriver, brain_server, generate_keypair, mint_voqalize_token,
)
from mybrain import MyBrain

keypair = generate_keypair()

async with brain_server(MyBrain, public_keys=keypair.public_pem) as server:
    token = mint_voqalize_token(
        private_key_pem=keypair.private_pem,
        session_id="s1", agent_id="agent_test", tenant_id="tenant_test",
    )
    driver = VoqalizeDriver(
        DirectConnection(server.url, "s1", token=token),
        session_id="s1", default_timeout=10.0,
    )
    await driver.open()
```

`brain_server` binds an ephemeral port, so tests never collide, and closes on the
way out whatever the test did. It is a *test* server — production hosting is
`run_session` in your own web framework's route (see
[Inbound](/docs/deploy/inbound/)); the SDK owns no server.

The brain verifies against the public half of the keypair and the driver signs with
the private half, so **token verification runs for real** rather than being switched
off.

## Drive it

| Call | Drives | Returns |
|---|---|---|
| `start_session(init={…})` | `SessionStart`, which *is* turn 1; plays out the greeting. `init` reaches the brain as `session.init`. | `Turn \| None` |
| `user_says("…")` | One user turn, played out and finalized. | `Turn` |
| `barge_in("…")` | Start a turn, let the brain speak, interrupt, finalize the cut with partial heard-truth. | `Turn` |
| `user_idle(level=1, idle_ms=30000)` | An idle trigger; plays out `on_user_idle`. | `Turn` |
| `send_rtvi(type, data)` / `send_client_message(t, d)` | One app→brain RTVI message, delivered to `on_rtvi`. That callback cannot speak and opens no turn, so there is nothing to wait for. | — |
| `collect_ui_commands(min_count=1)` | Waits for and returns the `ui-command` bodies the brain fired — `{"command": …, "payload": {…}}`. | `list[dict]` |
| `end_session()` / `send_cancel()` / `aclose()` | `End`, `Cancel`, teardown. | — |

## Assert on it

A `Turn` carries `.turn_id`, `.text` (everything spoken this turn), `.completed`,
`.interrupted`, `.heard` (for a barge-in: the partial the user actually heard), and
`.units` — one entry per speech unit, each with `.speech_id`, `.text`, `.spoke` and
`.ended`.

`.completed` is the most valuable single assertion — a false there usually means the
brain hung or raised.

```python
async def test_answers(driver):
    await driver.start_session()
    turn = await driver.user_says("Add two oat milks to my cart.")
    assert turn.completed
    assert "oat milk" in turn.text.lower()

    cmds = await driver.collect_ui_commands(min_count=1)
    add = next(c for c in cmds if c["command"] == "add_to_cart")
    assert add["payload"] == {"sku": "oat-milk", "qty": 2}
```

The driver also accumulates `driver.ui_commands`, `driver.errors` and
`driver.requests` — every `configure_*` the brain made, in wire order — so *"did the
brain switch to Hindi when asked?"* is an assertion on `driver.requests`, not a
listening exercise. Set `driver.reject[op] = "reason"` to make Voqalize refuse one, and
`driver.withhold.add(op)` to make it never answer at all.

:::tip[Determinism]
The driver *is* Voqalize, so it dictates the timing a real call can't reproduce:
exactly when a barge-in lands (`speak_delay`, `wait_for_speech`, `wait_for_complete`)
and exactly what heard-truth the brain is told (`heard_prefix=`). Use those instead
of sleeping and hoping.
:::

If the brain calls a real LLM, tests get slow and flaky for the usual reasons. Inject
a scripted fake (`brain=lambda: MyBrain(llm=FakeLLM())`) and keep one slow
test against the real model as a smoke check.

## The built-in conformance suite

Beyond your own scenarios, the harness ships a sixteen-scenario catalog — the bar a
brain must clear to be wire-compatible: greeting, turn- and speech-id monotonicity,
bracket integrity, the barge-in watermark, heard-truth reconciliation across
multiple interruptions, action-outcome correlation, RTVI delivery, idle
re-engagement, and bad-token rejection.

```bash
# Point it at any brain that speaks the wire.
python -m voqalize.conformance --brain-url ws://127.0.0.1:8787 --private-key ./pygato_priv.pem

# Prove the harness itself: host the bundled reference brain, run everything.
python -m voqalize.conformance --self-test
```

Add `--no-auth` instead of `--private-key` if the brain runs `allow_unverified`;
the auth scenarios are then skipped, because an unverified brain has no bad token
to reject.

Twelve of the sixteen need a *cooperating* brain — one that speaks a private
command grammar (`say banana`, `count slowly`) and echoes its committed state back,
which is what `voqalize.conformance.reference.ConformanceBrain` is for. Yours
doesn't, and shouldn't. The suite probes for that grammar on connect and **skips**
what can't apply, naming the reason and qualifying the verdict:

```
  [PASS] greeting                     (299 ms)
  [PASS] single_turn                  (299 ms)
  [PASS] multi_turn                   (300 ms)
  [SKIP] two_units_one_turn
  [SKIP] barge_in
  …
  [PASS] reject_bad_token             (83 ms)
  …

  12 skipped: needs the reference command grammar — this brain answered the probe with its own words, which is what any real brain does

  4 passed, 0 failed, 12 skipped — CONFORMANT on what ran (4 of 16 scenarios; see the skips above)
```

That is the honest result for an ordinary brain: the wire-level tier is what the
suite can prove about it, and the verdict says so rather than claiming more. Force
the probe either way with `--reference` / `--no-reference` if you need to.

`--only name1,name2` restricts the run; the exit code is 0 iff nothing **failed**
— skips don't fail a build, so this is safe in CI. Programmatically it's
`run_suite(brain_url, private_key_pem=…)` → a `Report` with `.ok`, `.passed`,
`.failed`, `.skipped`, `.summary()`.

The deep tier is worth reaching for once your own scenarios are in place: to run
it, your brain needs a test mode that answers the grammar and answers a
`__voqal.conformance.dump` client message with its conversation. Read
`ConformanceBrain` for the shape — the cooperation is small, and it buys you
heard-truth reconciliation across multiple interruptions.

## Then: inspect a live call

Once a human has actually talked to the agent, read the call back over the
[MCP tools](/docs/reference/mcp/):

```
list_sessions(tenant, agent_id=…, limit=20)              # find it — most recent first
get_session_events(tenant, session_id)                   # what was said and done, in order
get_session_logs(tenant, session_id, level="WARNING")    # why, when the above isn't enough
```

Events first: they carry both the lifecycle (created / connected / ended) and the
wire itself — each transcript, each piece of the reply, each action, each
interruption — and they are versioned contract, so a test may assert on them. Logs
are evidence, not contract: read them to understand a call, never to assert on one.

A call still running has no wire bundle yet, so check the `wire` field before
concluding it was silent — `missing` is a different fact from an empty list. And
these are **Voqalize's** records; your brain logs in your own environment. The
id joining the two sides is `session.id`, the same string in both.

When a live call misbehaves in a way the offline suite passed, that gap **is** the
next scenario. Reproduce it offline first, then fix it.

## Next

- **The SDK README** (`sdk/python/README.md`) — heard-truth, barge-in,
  and what the framework commits for you.
- **[MCP server](/docs/reference/mcp/)** — what to log so a
  live call is readable in the first place.
- **[MCP server](/docs/reference/mcp/)** — the observability tools, and the agent
  surface that runs this loop for you.
