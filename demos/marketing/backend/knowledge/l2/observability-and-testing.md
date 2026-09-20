# L2 — observability, recordings and testing

Read when: the call record, logs, events, recordings, the conformance harness,
evals in CI, or usage counters.

## The reads, in order

- **The call record** (`get_call_record`) — the contract. What was agreed: the
  session, its configuration, its turns, how it ended.
- **Session logs** (`get_session_logs`) — the evidence. What each layer did.
- **Session events** (`get_session_events`) — the only read available **while the
  call is still running**.

All of them through the console UI or the MCP server. Per-turn timings are in the
record and the events, so they come out over MCP rather than being trapped in the
console — there is no console-only view of the waterfall.

Realtime: events are the live read, polled. **There is no webhook and no
streaming events API today** — do not promise one. A brain that needs a turn's
data in realtime already has it, in `on_finalize`, in its own process; the
platform reads are for after the fact and for operators.

## What is stored, and what is not

Stored during preview: the session record and its `init` blob, lifecycle and wire
events, transcripts, Voqalize's own logs, and audio **only when recording was
enabled**.

Not stored: the brain's model history and the brain's logs. Those never leave the
customer's environment, because the brain never runs here.

**Retention is not configurable and not guaranteed during developer preview.**
That is the literal position, and it has a practical reading: treat anything you
need to keep as something to pull down and store yourself, and do not build a
compliance process on Voqalize's copy yet. For anything else, `support@voqalize.com`.

Region: processed and stored in India.

## Recordings

- **Off by default**, decided per call at connect through `config.record`, with
  the agent record supplying the default.
- A publishable `pk_` may turn recording **off** and may not turn it **on**.
- Output: one WebM track per role (`user`, `agent`), **sample-aligned and
  equal-length**, so the tracks line up on one timeline rather than needing
  to be re-synced.
- Capture is raw and cheap during the call; the tracks are rendered offline
  afterwards, anchored to the call's own clock. A recording is therefore
  available shortly after the call, not during it.
- Download URLs are **short-lived signed credentials**, fetched through
  `get_recordings`.

## Testing a brain in CI

`voqalize.conformance` is **a fake Voqalize speaking the real wire over a real
socket**, driven in text mode. That is what "no microphone, no network, no live
model" means concretely:

- `user_says("…")` in, a `Turn` with `.text` out.
- `barge_in`, `user_idle`, `collect_ui_commands` for the harder paths.
- **Real token verification** — the harness presents a genuine brain-connection
  token, so auth is exercised rather than stubbed.
- **Deterministic barge-in timing** — interruption lands at the same point every
  run, which is the only way an interruption test is worth having.

No browser, no audio, no GPU. It runs in an ordinary CI job in seconds, and it is
also the compatibility path for a brain written in another language: drive it
with the harness and conformance is demonstrated rather than asserted.

What it does not do: prove the call works. A live dial is still the only thing
that catches defects the wire tests pass over — that is learned experience, not a
caveat. Keep a smoke test that joins a real call.

## Usage

`get_usage` returns the counters — sessions and session time. During preview they
are a meter with no invoice attached, which is also how the planned pricing will
be measured.
