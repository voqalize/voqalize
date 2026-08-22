# Voqalize Agent SDK (Python)

**You bring the brain, we bring the voice.**

**Pipecat-free.** Installing this SDK pulls **no** `pipecat` dependency — the
promise is "bring the brain, not the voice infra." The customer writes a
`Brain` of callbacks; the wire is plain protobuf and the Brain surface is
plain dataclasses. (Pipecat lives only inside the Voqalize voice runtime, on
the far side of the socket.) The wire is language-neutral — see
[the wire](../../docs/src/content/docs/reference/wire.md) for the contract.

The **`Brain` is the sole customer surface** — there is no raw `FrameProcessor`
path. A brain is not a server: it sits inside an application you already run, and
the SDK owns **no** WebSocket server and **no** process management. That leaves
exactly two ways to host it, and the same `Brain` runs unchanged on either:

- **`run_session()` (`src/voqalize/sdk/session.py`) — your app owns the route.**
  Your web framework (FastAPI/Starlette, Django Channels, aiohttp) accepts the
  upgrade and hands the connected socket (anything with `send(bytes)`/`recv()->bytes` —
  the `Channel` protocol) to the SDK, along with the URL `session_id` and the
  `Authorization` header. The voice runtime dials `{brain_url}/s/{session_id}` per
  session; one connection = one session. No relay in the path.
- **`serve()` (`src/voqalize/sdk/outbound.py`) — your app can't accept inbound.**
  One outbound multiplexed WebSocket to a Cortex relay; many sessions demuxed by a
  16-byte prefix. For serverless/FaaS, laptops and egress-only networks. It
  **blocks** until the relay closes permanently — where that call lives is yours to
  decide.

For a socket in a *test*, `voqalize.conformance.brain_server` stands a brain on an
ephemeral localhost port. It is a test bench, not a hosting option.

## Install

```bash
pip install voqalize-agent-sdk               # core, pipecat-free
pip install "voqalize-agent-sdk[adk]"        # + the Google ADK integration
pip install "voqalize-agent-sdk[examples]"   # + deps used only by examples/
```

## Already have an ADK agent? Wrap it

If your brain is already a **Google ADK** agent, you don't port it to the `Brain`
API. You hand the SDK a factory for the agent you already have, and it drives your
agent's own run loop — adding only the voice concerns: one speech bracket per model
call, barge-in, heard-truth history (what the user *actually heard*, truncated on
interruption), and the wire. Your agent, tools, model, and prompt stay exactly as
they are.

The integration is an **optional extra** — `import voqalize.sdk` pulls none of it;
installing `[adk]` is what pulls in `google-adk`.

```python
from google.adk.agents import LlmAgent
from voqalize.google_adk import adk_brain
from voqalize.sdk import run_session

def build_agent() -> LlmAgent:                 # your existing agent, unchanged
    return LlmAgent(name="desk", model="gemini-2.5-flash",
                    instruction="You are a travel desk.", tools=[book_flight])

make = adk_brain(build_agent, greeting="Travel desk — where to?")
await run_session(channel, brain=make, session_id=session_id, token=token)
```

Every default is overridable and your existing framework customizations survive:
a dynamic `greeting=` callback, your own ADK `Runner` / `SessionService` via
`runner_factory=`, multi-agent trees, `on_resume=` to rehydrate a conversation that
spanned an earlier call, `turn_timeout` / `error_fallback`, and `voice().action(...)`
from inside a tool to drive the browser. For the full knob list, read the
`adk_brain` docstring. ADK is the one shipped framework integration today.

### Subclass `AdkBrain` when the agent needs the screen

A screen-driving agent extends `AdkBrain` instead of calling `adk_brain(...)`, and
gets four things the raw framework doesn't give you:

```python
class TravelBrain(AdkBrain):
    def __init__(self) -> None:
        super().__init__(lambda: build_agent(self.desk), greeting="Where to?")
        self.desk = TravelDesk()          # the agent is built lazily — this is in time

    def grounding(self) -> str:           # appended to the system instruction, every call
        return "ON SCREEN NOW: " + json.dumps(self.browser_state or {})
```

- **`grounding()`** is appended to the *fully assembled* system instruction on every
  model call — the root agent's and each sub-agent's. It composes with your own
  `instruction` rather than replacing it, is re-read per call (so `return None`
  omits the block turn by turn), and costs no round-trip. Use it for anything the
  model must not answer from a stale turn.
- **`self.browser_state`** is the last `state_sync` client message your UI pushed,
  parsed and kept for you. It takes **no floor** — a screen change never makes the
  agent talk — and replaces rather than merges. Override `on_client_message` for
  your own message types and call `super()` to keep it.
- **Tool arguments arrive as the models you annotated.** A parameter typed `Leg` or
  `list[Leg]` is constructed before your tool runs, `Field(alias=...)` honored both
  ways; an argument the model shaped wrong comes back to it as a retryable tool
  error, not an exception. No defensive `isinstance(raw, dict)` in the body.
- **Tools must be `async`.** A sync tool is rejected when the agent is built, naming
  it — ADK would dispatch it on a thread pool where `voice()` is unset, and you'd
  find out mid-call. `allow_sync_tools=True` opts out.

The [`travel` demo](https://github.com/voqalize/voqalize/blob/main/demos/travel/backend/brain.py)
is the worked example: a prompt, ten async tools, and one `grounding()` override.

## Layout

- `src/voqalize/sdk/brain.py` — the ergonomic surface: `Brain` (implement
  `on_user_message`; the rest are optional — `greet`/`on_session_start`/
  `on_session_end`/`on_user_idle`/`on_browser_message`/`on_finalize`/`on_error`) +
  `Session`/`ActionHandle`, the `_BrainAdapter` that maps wire frames ↔
  callbacks, and the entry points (`serve` for the Cortex leg, plus the internal
  `adapter_for` / `brain_factory` seams).
- `src/voqalize/sdk/events.py` — what a callback is handed and what it yields:
  `UserMessage`/`UserIdle`/`BrowserMessage`, `SpeechStart`/`Chunk`/`SpeechEnd`,
  `Finalize`, `Error`.
- `src/voqalize/sdk/engine.py` — the pipecat-free per-session runtime:
  `SessionRunner` (two-lane in/out, system-first feeder, drop-newest +
  `ErrorFrame`, teardown), the `Emitter` / `SessionAdapter` / `SessionFactory` /
  `RunnerHost` seams. **One runner drives both transports.**
- `src/voqalize/sdk/session.py` — the connection-handoff surface: the `Channel`
  protocol (`send`/`recv` bytes), `run_session()` (verify token → run one session
  over a caller-supplied channel), `serve_channel()` (the transport-neutral loop,
  no auth — reused by the conformance `brain_server`), and `verify_token`. Owns no
  server.
- `src/voqalize/sdk/outbound.py` — `CortexAgent` (multiplexed demux + shared fair
  writer over one wire), implementing `RunnerHost`.
- `src/voqalize/sdk/_keys.py` — the embedded Voqalize public key(s)
  `run_session` verifies against by default.
- `src/voqalize/sdk/wire/` — the frame dataclasses, `WIRE_VERSION`,
  `is_system()`, `CortexFrameSerializer` (protobuf transcoder, no base class),
  `Wire`/`MultiplexedWire` transport, protobuf stubs.
- `src/voqalize/_framework/` — the shared, framework-agnostic core every framework
  integration is built on: `_FrameworkBrain` (owns `run_inference`, the one
  primitive that spends a floor on a model turn), `voice()` (the `ContextVar`
  accessor a native tool uses for UI side-effects), heard-truth readers, the
  greeting/resume resolver, and the no-dead-air turn runner. Internal.
- `src/voqalize/google_adk/` — the **Google ADK** integration (`[adk]` extra):
  `AdkBrain` / `adk_brain(...)` plus `ScriptedLlm` for tests. See
  [Already have an ADK agent? Wrap it](#already-have-an-adk-agent-wrap-it).
- `src/voqalize/conformance/` — the wire-level conformance harness: `VoiceDriver`
  (drives a brain over a real socket from the voice-runtime side, no runtime
  needed), `brain_server` (a brain on an ephemeral localhost port, for tests that
  want the real wire), the scenario catalog, the MUST checks, and a `python -m
  voqalize.conformance` CLI. Point it at your brain to prove it speaks the
  wire correctly.

## Core invariants

- **Pipecat-free customer surface.** `import voqalize.sdk` loads zero pipecat
  modules. `pyjwt` is a runtime dependency (`run_session` verifies the runtime's
  token).
- **Connection-handoff, not a server.** The production inbound surface is
  `run_session(channel, *, brain, session_id, token=...)`: the customer's
  framework owns the listener + upgrade and hands the SDK a connected `Channel`.
  The SDK **verifies by default** against the embedded Voqalize public keys
  (`_keys.py`) — the token shape is uniform for every brain
  (`iss=pygato, aud=brain, sub=session_id`), and `sub` must equal the passed
  `session_id`. The audience is a wire constant (`BRAIN_AUDIENCE = "brain"`),
  verified unconditionally alongside `iss="pygato"` and `exp` — there is no
  per-agent audience and no `audience=` parameter; override `public_keys=`, or
  `allow_unverified=True` (local dev). A bad token raises `SessionRejected`
  (caller closes 4000). One socket = one session; framing is bare
  `[protobuf]`, session implicit in the URL.
- **Two hosting paths, one `Brain`.** `run_session` in the route your app already
  owns, or `await serve(...)` over a Cortex relay when it can't accept inbound. The
  SDK reads no environment variables and owns no process management: which path you
  are on is a property of your application, not a config flip.
- **Cortex (fallback):** one `CortexAgent` process → one outbound WebSocket to a
  `wss://.../agent` URL. Auth is `Authorization: Bearer <api_key>` (or a
  per-connect JWT via `authorization_provider`) + `X-Agent-Version`. Many sessions
  multiplex over the connection, demuxed by a 16-byte raw `session_id` prefix.
- **One `SessionRunner` per `session_id`.** `factory(emitter)` (a `SessionFactory`)
  runs once per session, building a fresh `_BrainAdapter(Brain(), emitter)`.
  Cross-session writes are structurally unreachable. Holds identically for both
  transports — the inbound path just has one session per connection.
- **Two lanes each way.** System frames (`SessionStart` / `Interruption` /
  `Cancel`, per `is_system()`) ride a priority lane that bypasses queued data;
  everything else rides a bounded normal lane (default 256) with **drop-newest**.
  `End` is *not* system — it rides the normal lane so a session tears down only
  after its queued data drains.
- **One sequential consumer.** The feeder takes envelopes off the inbound lane
  one at a time and awaits `adapter.handle_frame` on each, so callbacks see frames
  in wire order. A slow callback delays the callbacks behind it and nothing else —
  it never reaches back across the wire. Still, **do slow I/O off the callback
  lane**: an `on_finalize` that writes a database row delays the next callback by
  exactly that write. Spawn your own background work, as the adapter already does
  for a browser message.
- **A `Response` bypasses the lanes.** It is an answer, not a stimulus: exactly
  one consumer — the caller blocked on it — and no ordering against speech or user
  messages. Queueing it behind the feeder would deadlock every `configure_*` made
  from inside a callback, because the feeder is inside that very callback.
- **Interruption is a drain barrier.** Barge-in rides the wire as a field-less
  `InterruptionFrame` (system lane); the adapter cancels the in-flight turn and
  echoes an `InterruptionFrame` back on the outbound system lane — the runtime's
  drain barrier. Correlation lives on the envelope, never on the interrupt.
- **Backpressure never kills a session.** On normal-lane overflow the runner drops
  the newest frame and delivers a non-fatal `ErrorFrame` to the adapter
  (edge-triggered: one per congestion episode per direction), surfaced to the Brain
  via optional `on_error`.
- **Heard truth, not generated text.** A framework integration commits the user
  utterance when the stimulus arrives and one assistant message per speech unit
  from its *heard* text at finalize. The Brain keeps no parallel history and
  cannot commit what it generated.

## Read next

- [`../../proto/voqalize/frames/frames.proto`](../../proto/voqalize/frames/frames.proto) — the wire contract of record: envelope, frame vocabulary, direction table.
- [`../../docs/src/content/docs/reference/wire.md`](../../docs/src/content/docs/reference/wire.md) — the wire in full, and why the Brain has the shape it has.
- The module docstrings in `src/voqalize/sdk/` (`brain.py`, `engine.py`, `session.py`) — the canonical narratives, and they move with the code.
- `examples/` — runnable brains: `echo` (smallest complete brain), `travel`
  (a hand-written `Brain` over Gemini with screen-driving tools), `travel_adk`
  (the same agent as a native ADK `LlmAgent`, wrapped with `adk_brain`),
  `fastapi_inbound` (mount a brain in your own FastAPI app).

## Development

```bash
uv run pytest
```

Integration tests run a `FakeCortex` over real TCP; the runtime leg is simulated
by the SDK's own `Wire` client. No `MagicMock` / `AsyncMock` anywhere.
