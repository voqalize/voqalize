# Architecture

The SDK is **pipecat-free**. The customer writes a :class:`Brain` of callbacks;
the SDK maps the `Vql*` wire onto those callbacks and back, one isolated
per-session engine at a time. This page is the map — the canonical narratives live
in the module docstrings of [`brain.py`](../src/voqalize/sdk/brain.py),
[`engine.py`](../src/voqalize/sdk/engine.py), and
[`session.py`](../src/voqalize/sdk/session.py).

## The layers

```
                Brain (customer)  ── subclass; implement on_interaction (+ optional hooks)
                     ▲  │
   Vql* callbacks    │  │ speak / action / configure
                     │  ▼
              _BrainAdapter        ── one per session; Vql* frames ↔ Brain callbacks   (brain.py)
                     ▲  │
   handle_frame(f)   │  │ emitter.send(f)
                     │  ▼
              SessionRunner         ── one per session; two-lane in/out, ack-gating,   (engine.py)
                     ▲  │              backpressure, teardown  (Emitter + SessionAdapter seams)
   enqueue_inbound   │  │ pop_out
                     │  ▼
                a Runner host       ── owns the socket(s); reads/writes bytes
```

`Brain` is the **sole customer surface** — there is no raw `FrameProcessor` path.
The `_BrainAdapter` implements the `SessionAdapter` protocol (`handle_frame` /
`close`) and the `SessionRunner` implements the `Emitter` protocol (`send`) it was
built with. The Brain never sees the wire; the runner never sees a Brain callback.

## Two runners, one engine

A brain is not a server. It sits inside an application, and that application either
can accept an inbound connection or it can't — which is the entire choice. The same
`Brain` and the same `SessionRunner` drive both; they differ only in the small
`RunnerHost` seam — who owns the socket and who dials whom.

| Runner | Who dials | Owns a server? | Use |
|---|---|---|---|
| **`run_session()`** ([`session.py`](../src/voqalize/sdk/session.py)) | PyGato dials **you** | No — you hand it a connected socket | **Primary path.** Mount in the route your app already owns (FastAPI/Starlette/Django/aiohttp). |
| **`serve()`** ([`outbound.py`](../src/voqalize/sdk/outbound.py)) | **You** dial Cortex | One outbound multiplexed WS | Fallback for brains that can't accept inbound (FaaS, laptops, egress-only). Blocks until the relay closes. |

The SDK owns no listener and no process management on either path. `serve` blocking
is the interface, not an oversight: where that call lives — `asyncio.run`, an app
lifespan task, a worker entrypoint — is the caller's decision, not ours.

For a socket in a *test*, [`voqalize.conformance.brain_server`](../src/voqalize/conformance/host.py)
stands a brain on an ephemeral localhost port. It is a test bench, not a third
hosting surface.

### `run_session` — the primary inbound surface

The SDK does **not** own a WebSocket server on this path. Your framework accepts
the upgrade and hands the connected socket to the SDK as a `Channel` — anything
with `async send(bytes)` / `async recv() -> bytes`:

```python
@app.websocket("/s/{session_id}")
async def voice(ws, session_id):
    await ws.accept()
    await run_session(
        _WsChannel(ws),                          # send/recv-bytes adapter
        brain=MyBrain,
        session_id=session_id,                   # from the URL path
        token=ws.headers.get("Authorization"),   # SDK verifies it
    )
```

PyGato dials `{brain_url}/s/{session_id}` — **one connection per session**, opened
just-in-time, torn down when the call ends. Connection state *is* liveness; there
is no pooled connection to manage. A runnable FastAPI version lives in
[`../examples/fastapi_inbound/`](../examples/fastapi_inbound/).

### Token verification

`run_session` verifies PyGato's short-lived RS256 token before running the session
(`verify_token` in [`session.py`](../src/voqalize/sdk/session.py)). The token
shape is **uniform for every brain**: `iss="pygato"`, `aud="brain"` (a protocol
constant, `BRAIN_AUDIENCE` — not per-agent), and `sub == session_id`. By default
it checks the signature against the Voqalize public keys embedded in
[`_platform_keys.py`](../src/voqalize/sdk/_platform_keys.py) — **zero config**
for a real deployment. Override with `public_keys=` (self-hosted), or
`allow_unverified=True` for local dev (local PyGato signs with a dev key, so a real
check would reject every local session). A bad token raises `SessionRejected`; the
caller closes **4000** (permanent, non-retriable — PyGato gives up, mirroring
Cortex's `NoAgent`).

## Per-session engine (`SessionRunner`)

One runner per `session_id`. The `SessionFactory` (`factory(emitter)`) builds a
fresh `_BrainAdapter(Brain(), emitter)` per session, so cross-session writes are
structurally unreachable — the adapter can only reach *its* runner's `Emitter`.

**Two lanes each way** (`_InLanes` / `_OutLanes`):

- **System** — priority, tiny bounded tripwire (default 32, never expected to
  fill). Carries `VqlStart` / `Interruption` / `Cancel` (per
  [`is_system`](../src/voqalize/sdk/wire/__init__.py)), so an interrupt bypasses
  queued data. `End` is **not** system — it rides the normal lane, so a session
  tears down only after its queued data drains.
- **Normal** — bounded (default 256), **drop-newest** on overflow.

The feeder loop dispatches one inbound frame at a time to `adapter.handle_frame`,
system-lane first.

### Ack-gated ordering

Every wire-vocab data frame carries `request_id > 0`. After `handle_frame`
returns, the runner enqueues an `_Ack(request_id)` onto the **outbound normal
lane** — so the ack FIFOs *behind* any response frames the handler emitted
synchronously. Acks bypass the lane bound (`append_ack`): a dropped ack would hang
PyGato's per-frame flow control. Crucially, the adapter **spawns**
`on_interaction` as a task rather than awaiting it, so the `VqlUserText` ack fires
promptly and PyGato keeps sending; the reply streams out of the spawned task via
`emitter.send`.

### Backpressure never kills a session

On normal-lane overflow the runner drops the newest frame and delivers a
**non-fatal** `ErrorFrame` to the adapter, edge-triggered (one per congestion
*episode* per direction; the episode clears when the lane drains below half its
bound). The Brain sees it via optional `on_error`. The session is never killed.

## Interruption (barge-in)

Barge-in rides the wire as a field-less native `InterruptionFrame` on the system
lane. The `_BrainAdapter` cancels the in-flight `on_interaction` task(s) — the
`CancelledError` unwinds their open `say()` brackets — then echoes an
`InterruptionFrame` back on the outbound system lane, which is PyGato's drain
barrier. Correlation lives on `inference_id`, not on the interrupt.

## The Brain callback mapping

`_BrainAdapter.handle_frame` translates inbound `Vql*` frames into Brain
callbacks, and the Brain's responses back onto the wire via the `Emitter`:

| Inbound frame | Brain callback / effect |
|---|---|
| `VqlStartFrame` | build `Session`; `on_session_start(session, start)` |
| `VqlUserTextFrame` | commit user turn to `Conversation`; spawn `on_interaction(interaction)` |
| `InterruptionFrame` | cancel in-flight interaction(s); echo the drain barrier |
| `VqlInferenceFinalizedFrame` | commit assistant **heard** text; `on_inference_finalized(inference)` |
| `VqlUserIdleFrame` | open a floor-owning idle interaction; `on_user_idle(interaction)` |
| `VqlRTVIClientMessageFrame` (`action_result`) | route to the pending `action` callback by `action_id` |
| `VqlRTVIClientMessageFrame` (other) | pre-mint an `interaction_id`; `on_client_message(session, message)` |
| `ErrorFrame` | `on_error(session, error)` |

| Brain action | Outbound frame |
|---|---|
| `async with interaction.say()` | `VqlLLMFullResponseStart` … `End` (mints `inference_id`) |
| `await inf.speak(text)` | `VqlLLMTextFrame` |
| `interaction.action(name, {...})` / `session.action(...)` | `RTVIServerMessageFrame` (`ui_command`) |
| `session.configure_tts(...)` / `configure_stt(...)` | `TTSUpdateSettingsFrame` / `STTUpdateSettingsFrame` |
| clean return from `on_interaction` | `VqlInteractionCompletedFrame` |

**Framework-owned faithful transcript.** The heard-text contract is enforced in
the SDK, not left to the Brain: it commits the user utterance at interaction start
and one assistant message per inference from its **heard** text at finalize (the
generated-but-barged-in tail never lands in the record). The Brain reads
`interaction.conversation.messages` to build its LLM prompt and cannot commit
generated text by mistake — it never commits at all.

## Cortex (fallback) — multiplexing

The direct/`run_session` path is one socket per session. The Cortex fallback
([`outbound.py`](../src/voqalize/sdk/outbound.py)) instead opens **one** outbound
WebSocket to the `wss://…/agent` URL and multiplexes many sessions over it,
demuxed by a **16-byte raw `session_id` prefix**. Auth is `Authorization:
Bearer <api_key>` (or a per-connect JWT
via `authorization_provider`) + `X-Agent-Version`; Cortex resolves the credential
to a pool key internally. A shared fair writer drains per-session outbound lanes in
round-robin so one talkative session can't starve the others. Each session still
gets its own `SessionRunner` — the engine is identical; only the `RunnerHost` seam
(shared wire vs. one socket) differs.

Reconnect is crash-only: on a transient close every open session is torn down; the
SDK does **not** re-send `VqlStartFrame` (that would trample state). A `4000` close
propagates out as `PermanentClose`.

## Wire framing

- **Direct / `run_session`** (`/s/{session_id}`): `[1-byte direction][protobuf]`,
  session implicit in the URL. Identical to the PyGato↔Cortex `/s/` leg.
- **Cortex** (`/agent`): `[16-byte session_id][1-byte direction][protobuf]`.

The 1-byte direction is `1 = DOWNSTREAM`, `2 = UPSTREAM` (matching pipecat's
`FrameDirection`). Every brain→wire frame goes DOWNSTREAM (`OUT_DIRECTION`); PyGato
flips `ui_command` to UPSTREAM on its own read. Serialization is
[`CortexFrameSerializer`](../src/voqalize/sdk/wire/serializer.py) (protobuf); the
frame vocabulary is documented in [`wire-protocol.md`](wire-protocol.md).
