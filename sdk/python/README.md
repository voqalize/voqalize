# Voqalize Agent SDK (Python)

**You bring the brain, we bring the voice.**

**Pipecat-free.** Installing this SDK pulls **no** `pipecat` dependency — the
promise is "bring the brain, not the voice infra." The customer writes a
`Brain` of callbacks; the wire is plain protobuf and the Brain surface is
plain dataclasses. (Pipecat lives only inside the Voqalize voice runtime, on
the far side of the socket.) The wire is language-neutral — see
[the wire](https://github.com/voqalize/voqalize/blob/python-sdk-v0.1.0/docs/src/content/docs/reference/wire.md)
for the contract.

The **`Brain` is the sole customer surface** — there is no raw `FrameProcessor`
path. A brain is not a server: it sits inside an application you already run, and
the SDK owns **no** WebSocket server and **no** process management. That leaves
exactly two ways to host it, and the same `Brain` runs unchanged on either:

- **`run_session()` (`src/voqalize/sdk/session.py`) — your app owns the route.**
  Your web framework (FastAPI/Starlette, Django Channels, aiohttp) accepts the
  upgrade and hands the connected socket (anything with `send(bytes)`/`recv()->bytes` —
  the `Channel` protocol) to the SDK, along with the URL `session_id` and the
  `Authorization` header. The voice runtime dials `{brain_url}?session_id={session_id}`
  per session — your path, verbatim — so one ordinary route is enough; one
  connection = one session. No relay in the path.
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
pip install "voqalize-agent-sdk[gemini]"     # + `GeminiBrain` (google-genai)
pip install "voqalize-agent-sdk[examples]"   # + deps used only by examples/
```

## The smallest complete brain

One method is required. It is handed what the caller said and yields speech; the
brackets are what let the runtime start and stop audio without waiting for the
sentence to finish.

```python
from collections.abc import AsyncGenerator
from voqalize.sdk import Brain, Chunk, Session, Speech, SpeechEnd, SpeechStart, UserMessage

class EchoBrain(Brain):
    async def greet(self, session: Session) -> str:
        return "Hi! I'm an echo bot. Say something and I'll repeat it back."

    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncGenerator[Speech, None]:
        yield SpeechStart()
        yield Chunk(f"You said: {msg.text}")
        yield SpeechEnd()
```

`greet` returns a **string, not a model call** — the caller is already on the line
and the first word has to arrive now. A template is as clever as it gets.

## Let a model do the talking: `GeminiBrain`

`GeminiBrain` (`[gemini]` extra) fills in the parts every model-backed brain
writes the same way: the context, the streaming, the tool hops, and the rewrite at
the end that makes the context say what the caller *heard*. You bring the
system instruction and the tools.

```python
from google import genai
from voqalize.sdk import Action, Session
from voqalize.sdk.gemini import GeminiBrain

class OpenBooking(Action):
    destination: str

class Concierge(GeminiBrain):
    def __init__(self) -> None:
        super().__init__(client=genai.Client(), system_instruction="You are a travel desk.")

    async def greet(self, session: Session) -> str:
        return "Travel desk — where to?"

    @property
    def tools(self):
        return [self.open_booking]

    async def open_booking(self, args: OpenBooking) -> str:
        """Put the booking form on screen."""      # the model reads this
        self.session.dispatch(args)
        return "ok"
```

**The method is the declaration.** A tool is a bound `async def`: its docstring is
the description the model reads, its single pydantic parameter is the schema. There
is no registry and no decorator to forget.

Two things carry most of what a real agent needs beyond its tools.
`system_instruction` is settable, so facts known only once the session opens — who
called, which tenant — go in from `on_session_start`. And `append_to_context()`
adds to the conversation the model sees, for context the app knows and the
conversation does not — typically the live screen state pushed to `on_rtvi`, which
takes no floor and starts no turn:

```python
import json

from google.genai import types
from voqalize.sdk import RTVIMessage, Session

async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None:
    if msg.data.get("t") == "state_sync":
        self.append_to_context(
            types.Content(
                role="user",
                parts=[types.Part(text="ON SCREEN: " + json.dumps(msg.data["d"]))],
            )
        )
```

It takes the provider's own type on purpose — a `Content` here, a `UserInputStep`
on `GeminiInteractionsBrain`. **Voqalize owns the wire; the provider owns the
context.** What a brain owes Voqalize is neutral and the same across every adapter;
what a brain says to a model is the provider's, and a wrapper type in between is
one more thing that has to keep up with Gemini. It also means handing the model a
screenshot or a PDF is this same call with a different part, rather than a second
method we would have had to invent for it.

It appends where you call it, once. Nothing debounces or diffs for you — the
context only ever grows, which is what makes it cacheable, so append what
*changed* rather than the whole screen every time.

`import voqalize.sdk` pulls no model vendor: nothing in the core SDK imports this
module.

## Layout

- `src/voqalize/sdk/brain.py` — the ergonomic surface: `Brain` (implement
  `on_user_message`; the rest are optional — `greet`/`on_session_start`/
  `on_session_end`/`on_user_idle`/`on_rtvi`/`on_finalize`/`on_error`) +
  `Session`, the private adapter that maps wire frames ↔ callbacks, and the
  `serve` entry point for the Cortex leg.
- `src/voqalize/sdk/events.py` — what a callback is handed and what it yields:
  `UserMessage`/`UserIdle`/`RTVIMessage`, `SpeechStart`/`Chunk`/`SpeechEnd`,
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
  `is_system()`, `WireSerializer` (the protobuf serializer, no base class),
  `Wire`/`MultiplexedWire` transport, protobuf stubs.
- `src/voqalize/sdk/gemini.py` — `GeminiBrain` (`[gemini]` extra): the context, the
  streamed turn, the tool hops google-genai runs for us, and the finalize that
  rewrites it to what was heard. `gemini_interactions.py` is the same
  turn against the Interactions API.
- `src/voqalize/conformance/` — the wire-level conformance harness: `VoqalizeDriver`
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
  for an RTVI message.
- **A `Response` bypasses the lanes.** It is an answer, not a stimulus: exactly
  one consumer — the caller blocked on it — and no ordering against speech or user
  messages. Queueing it behind the feeder would deadlock every `configure_*` made
  from inside a callback, because the feeder is inside that very callback.
- **Interruption is a watermark.** Barge-in rides the wire as an
  `InterruptionFrame` naming the turn it condemns (system lane); the adapter
  raises `max(watermark, through_turn)` and cancels the in-flight turn. Nothing
  goes back, so there is no barrier to hold and nothing to time out — a newer
  turn simply outranks the watermark.
- **Backpressure never kills a session.** On normal-lane overflow the runner drops
  the newest frame and delivers a non-fatal `ErrorFrame` to the adapter
  (edge-triggered: one per congestion episode per direction), surfaced to the Brain
  via optional `on_error`.
- **Heard truth, not generated text.** A brain that keeps a context commits the
  user utterance when the stimulus arrives, and one assistant message per speech
  unit — from its *heard* text, at finalize. `GeminiBrain` does this for you. A
  reply that generated three sentences and was cut after one is remembered as one,
  which is the only version the caller and the model can both agree on.

## Read next

- [The protobuf contract](https://github.com/voqalize/voqalize/blob/python-sdk-v0.1.0/proto/voqalize/frames/frames.proto) — the wire contract of record: envelope, frame vocabulary, direction table.
- [The wire reference](https://github.com/voqalize/voqalize/blob/python-sdk-v0.1.0/docs/src/content/docs/reference/wire.md) — the wire in full, and why the Brain has the shape it has.
- The module docstrings in `src/voqalize/sdk/` (`brain.py`, `engine.py`, `session.py`) — the canonical narratives, and they move with the code.
- `examples/` — runnable brains: `echo` (the smallest complete brain),
  `reference` (the one every conformance scenario is run against),
  `fastapi_inbound` (mount a brain in your own FastAPI app).

## Development

```bash
uv run pytest
```

Integration tests run a `FakeCortex` over real TCP; the runtime leg is simulated
by the SDK's own `Wire` client. No `MagicMock` / `AsyncMock` anywhere.
