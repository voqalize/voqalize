# Testing a voice agent without talking to it

The hard part of shipping a voice agent is usually not the voice — it's that every
change seems to need a human with a microphone. It doesn't. The SDK ships
**`voqalize.conformance`**: a protocol-compliant *fake Voqalize* that hosts your real
`Brain` on a real socket, speaks the real wire, and drives it in **text mode**.
No audio, no browser, no runtime, no human.

That makes a voice agent testable like any other service — and it is the eval
primitive. A scenario is a conversation script plus assertions. **Keep a scenario
file per use case in the customer's repo and run it in CI.**

Two loops, in order:

1. **Offline** — `voqalize.conformance` drives the brain deterministically. Fast,
   runs on every commit, no platform account needed.
2. **Live** — after a real call, read it back with `list_sessions` /
   `get_session_events` / `get_session_logs`.

---

## 1. The offline loop

### Start from the template

`templates/test_brain.py` is a working pytest file: a fixture that hosts `MyBrain`
on an ephemeral port with a per-run RSA keypair, plus tests for greeting, a turn,
UI actions, client messages, barge-in, and idle. Copy it into the customer's repo,
rename the assertions to their use case, wire it into CI. That is the deliverable.

### The shape

```python
from voqalize.conformance import (
    DirectConnection, VoiceDriver, brain_server, generate_keypair, mint_pygato_token,
)

keypair = generate_keypair()
async with brain_server(MyBrain, public_keys=keypair.public_pem) as server:
    token = mint_pygato_token(private_key_pem=keypair.private_pem, session_id="s1",
                              agent_id="agent_test", tenant_id="tenant_test")
    driver = VoiceDriver(DirectConnection(server.url, "s1", token=token),
                         session_id="s1", agent_id="agent_test", default_timeout=10.0)
    await driver.open()
```

`brain_server` binds an ephemeral port, so tests never collide, and closes on the way
out. It is a **test** server: production hosting is `run_session` in the customer's
own route (`references/transport.md`).

Note the keypair: the brain verifies against the public half, the driver signs with
the private half — **token verification is exercised for real**, not switched off.

### Driving it

| Call | Drives | Returns |
|---|---|---|
| `start_session(payload={...})` | `VqlStart`; plays out the greeting (interaction 0). `payload` lands brain-side as `start.init`. | `Turn \| None` |
| `user_says("…")` | One user turn, played out to completion and finalized. | `Turn` |
| `barge_in("…")` | Start a turn, let the brain speak, interrupt it, finalize the cut with partial heard-truth. | `Turn` |
| `client_message(type, data)` | A browser message the brain **answers** (via `message.interaction`); waits for the reply. | `Turn` |
| `send_client_message(type, data)` | A browser message the brain **ingests silently**; does not wait. | `interaction_id` |
| `user_idle(level=1, idle_ms=30000)` | An idle trigger; plays out `on_user_idle`. | `Turn` |
| `send_action_result(action_id, status=, result=)` | The UI reporting back on an action; fires the brain's `callback=`. | — |
| `collect_ui_commands(min_count=1)` | Waits for and returns the `ui_command` envelopes the brain fired. | `list[dict]` |
| `end_session()` / `aclose()` | `End` frame + teardown. | — |

### Asserting on it

A `Turn` carries:

- `.text` — everything the brain spoke this turn (all inferences joined).
- `.completed` — the interaction closed. **A false here usually means the brain hung
  or raised**; assert it explicitly, it's the most valuable single check.
- `.interrupted` / `.heard` — for a barge-in: `heard` is the partial the user actually
  heard. That, not the generated tail, is what belongs in history.
- `.inferences` — per-LLM-call detail: `.text`, `.spoke`, `.tool_calls`,
  `.inference_id`.

The driver also accumulates `driver.ui_commands`, `driver.errors`,
`driver.tts_settings`, `driver.stt_settings`, `driver.idle_settings` — so
"did the brain switch to Hindi when asked?" is an assertion on `tts_settings`, not a
listening exercise.

### Making it deterministic

The driver *is* Voice, so it dictates the timing a real call can't reproduce: exactly
when a barge-in lands (`speak_delay`, `wait_for_speech`, `wait_for_complete`) and
exactly what heard-truth the brain is told (`heard_prefix=`). Use those instead of
sleeping and hoping.

If the brain calls a real LLM, tests are slow and flaky for the usual reasons — raise
`default_timeout`, and prefer injecting a scripted fake:
`brain_server(lambda: MyBrain(llm=FakeLLM()), ...)` — the same `() -> Brain` callable
`run_session` takes. Keep one slow test that uses the real model as a smoke check.

### The built-in catalog

Beyond your own scenarios, the harness ships a 16-scenario protocol suite — the bar
a brain must clear to be wire-compatible (greeting, turn/inference-id monotonicity,
bracket integrity, barge-in drain, heard-truth reconciliation across multiple
interruptions, action-outcome correlation, client-message delivery, idle,
bad-token rejection).

```bash
# Any brain that speaks the wire.
python -m voqalize.conformance --brain-url ws://127.0.0.1:8787 --private-key ./pygato_priv.pem

# Prove the harness itself: host the bundled reference brain and run everything.
python -m voqalize.conformance --self-test
```

**Expect skips against a customer brain, and don't treat them as failures.** Twelve
of the sixteen need a cooperating brain that speaks the reference command grammar
(`voqalize.conformance.reference.ConformanceBrain`). The suite probes for it on
connect and skips what can't apply, so a customer brain reports something like
`4 passed, 0 failed, 12 skipped — CONFORMANT on what ran (4 of 16 scenarios)`.
That is the correct result, and the exit code is 0. `--reference` /
`--no-reference` force the probe either way; `--no-auth` only if the brain runs
`allow_unverified` (which also skips the auth scenario — an unverified brain has no
bad token to reject). `--only name1,name2` restricts the run; the exit code is 0
iff nothing **failed**.

Programmatically the same thing is `run_suite(brain_url, private_key_pem=...)` → a
`Report` with `.ok`, `.passed`, `.failed`, `.skipped`, `.summary()`.

Reaching the deep tier means giving the brain a test mode that answers the grammar
and answers a `__voqal.conformance.dump` client message with its conversation —
worth suggesting once the customer's own scenarios are in place, since that tier is
where heard-truth across multiple interruptions gets proven.

---

## 2. The live loop

Once a human (or you, via `test_url`) has actually talked to it:

```
list_sessions(tenant, agent_id=..., limit=20)            # find the call — most recent first
get_session_events(tenant, session_id, source="platform")  # how far did it get?
get_session_events(tenant, session_id)                   # + the wire: what was said and done
get_session_logs(tenant, session_id, level="WARNING")    # platform runtime log lines
```

Order matters: **events first** (both halves are versioned contract — safe to assert
on), **logs last** (evidence, in our vocabulary, free to change; never assert on
their wording). `source="platform"` skips the wire read, which is what makes "did
this call even connect" the cheap first question; `disposition="dropped_in_drain"`
shows what a caller's barge-in threw away, the usual explanation for "the agent
replied but nothing happened". `get_session_logs` also takes `service=` (`pygato` is
the voice runtime) and `level` ∈ `DEBUG|INFO|WARNING|ERROR|CRITICAL`.

Both the wire events and the logs are uploaded as one bundle **when the call ends**,
so a call still running has neither — check the `wire` / `logs_availability` field
rather than reading an empty list as silence.

These are the **platform's** records, not the brain's — the brain runs in the
customer's own environment. `session.id` is the same string on both sides; grep your
own logs for it. See `references/instrumentation.md`.

If a live call misbehaves in a way the offline suite passed, that gap **is the next
scenario** — reproduce it in `test_brain.py` first, then fix it.

## Read next

- **`references/instrumentation.md`** — what to log so `get_session_logs` is worth
  reading.
- **`references/ui-actions.md`** — the exact `ui_command` shape `collect_ui_commands`
  returns.
