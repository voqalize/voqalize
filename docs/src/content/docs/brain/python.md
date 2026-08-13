---
title: Build a brain (Python)
description: The Python brain SDK — subclass Brain, implement a couple of async callbacks, serve it inbound or over Cortex.
---

The Python SDK (`voqalize.sdk`) is pipecat-free: your brain is plain `async`
Python over a small set of dataclasses. You subclass `Brain`, implement callbacks,
and serve the class over one of two transports.

:::note[Pre-release]
Not yet on PyPI. Install editable from a clone of
[`voqalize/voqalize`](https://github.com/voqalize/voqalize):
`uv pip install -e sdk/python` (the published name will be `voqalize-agent-sdk`).
:::

## The `Brain` base class

Subclass `Brain` and implement callbacks. All are `async`. Only `on_interaction`
is required.

```python
from voqalize.sdk import (
    Brain, ClientMessage, Inference, Interaction, Session, SessionStart,
)

class MyBrain(Brain):
    async def on_session_start(self, session: Session, start: SessionStart) -> None:
        ...   # setup + optional greeting; default no-op

    async def on_interaction(self, interaction: Interaction) -> None:
        ...   # REQUIRED: one committed user turn

    async def on_inference_finalized(self, inference: Inference) -> None:
        ...   # per-inference side effects (logging/persistence); default no-op

    async def on_user_idle(self, interaction: Interaction) -> None:
        ...   # the user went silent past the idle timeout; default no-op

    async def on_client_message(self, session: Session, message: ClientMessage) -> None:
        ...   # browser → brain message; default no-op

    async def on_session_end(self, session: Session) -> None:
        ...   # teardown; default no-op

    async def on_error(self, session: Session, error) -> None:
        ...   # non-fatal runtime signal; session is never killed; default ignore
```

| Callback | When it fires |
|---|---|
| `on_session_start(session, start)` | Once, at connect. `start.init` is the opaque payload from the client. Greet here. |
| `on_interaction(interaction)` | **Required.** Once per committed user turn. A clean return emits `VqlInteractionCompleted`. |
| `on_inference_finalized(inference)` | After each bot inference finishes; the heard transcript is already committed. |
| `on_user_idle(interaction)` | The user has been silent past the idle timeout. You hold the floor; re-engage or stay quiet. |
| `on_client_message(session, message)` | Browser sent a message (e.g. `state_sync`, an uploaded photo). Replying is opt-in. |
| `on_session_end(session)` | Session teardown. |
| `on_error(session, error)` | Non-fatal congestion/drop signal. Never fatal. |

### Who holds the floor

Voice is the sole interaction initiator: it mints every `interaction_id` and hands
the brain the floor through a callback. `on_session_start`, `on_interaction` and
`on_user_idle` are **floor-owning** — the runtime opened the interaction for you,
so respond freely. `on_client_message` is the exception: Voice delivers *every*
client message with a pre-minted id but does not judge whether it deserves a
reply. You do — see below.

## Speaking

All bot speech goes through a **speech bracket**, opened with `say()`. One bracket
equals one model call (1:1 with the wire):

```python
# Agent-initiated (greeting) — runs under interaction_id = 0.
async with session.say() as speech:
    await speech.speak("Hi! How can I help?")

# Response to a user turn.
async with interaction.say() as speech:
    await speech.speak("You said: ")
    await speech.speak(interaction.transcript)   # many speak() calls per bracket are fine
```

Entering emits `VqlLLMFullResponseStart` (and mints the inference id); each
`speak(text)` emits a `VqlLLMText` chunk (empty string is a no-op); exiting emits
`VqlLLMFullResponseEnd`. A barge-in cancels the coroutine and unwinds any open
bracket.

## The `Session` object

Passed to `on_session_start`, `on_client_message`, `on_session_end`. Attributes:
`.id: str`, `.init: dict`, `.conversation: Conversation`.

```python
session.say()                              # → bracket for agent-initiated speech (id 0)
session.action(name, args=None, *, callback=None) -> int
session.action(action, *, callback=None) -> int    # a voqalize.sdk.Action instance
session.configure_language(language, *, voice=None) -> None   # the whole call
session.configure_tts(*, voice=None, language=None, model=None) -> None
session.configure_stt(*, language_hint=None, vad_confidence=None, ...) -> None
session.configure_idle(*, timeout_ms=None) -> None
```

- **`action(name, args)`** fires a UI command to the browser *outside* any
  interaction (from `on_session_start`, `on_client_message`, or a background task).
  Returns a brain-minted `action_id`; the browser echoes an outcome that your
  optional `callback` receives. Never blocks. Pass an
  [`Action`](/docs/brain/conversation/#typed-actions) instance instead of
  `(name, args)` to declare the payload's shape — same bytes on the wire.
- **`configure_language`** switches the whole call — recognizer *and* voice — to
  another language. **This is the only supported way to change language.** The two
  sides name the field differently, so doing it as a `configure_tts` +
  `configure_stt` pair can half-apply, and a half-applied language is silent.
- **`configure_tts`** changes voice/language/model for the **next** inference
  (never mid-utterance). Only the fields you pass change. Use it for a voice
  change; for a language change use `configure_language`.
- **`configure_stt`** applies **live** (mid-utterance safe) — the VAD/turn knobs.
  It also accepts the raw `language_hint`; prefer `configure_language`. See the
  [catalog](/docs/reference/catalog/) for allowed values.
- **`configure_idle`** sets how long the user may stay silent (after the agent
  stops speaking) before Voice opens an idle interaction and calls
  `on_user_idle`. `timeout_ms=0` disables idle detection entirely. Fire-and-forget,
  callable any time mid-call.

## The `Interaction` object

Passed to `on_interaction` and `on_user_idle` (and reachable from a
`ClientMessage`). Attributes: `.id`, `.transcript: str` (what the user said —
empty for an idle interaction), `.session`, `.conversation` (the running
transcript, already including this turn), `.source` (`InteractionSource.USER` /
`IDLE` / `CLIENT_MESSAGE`), and `.idle` (an `IdleInfo` on idle interactions).

```python
interaction.say()                          # → bracket; one per model call
interaction.action(name, args=None, *, callback=None) -> int   # UI command, attributed to this turn
interaction.action(action, *, callback=None) -> int            # ...or a typed Action instance
```

## Idle: `on_user_idle`

When the user stays silent past the configured timeout, Voice opens an idle
interaction and hands you the floor. `interaction.idle` carries `level` (1 for the
first nudge, escalating while the silence persists, reset by any user speech) and
`idle_ms` (elapsed silence). `interaction.transcript` is empty — nothing was said.

```python
async def on_session_start(self, session, start) -> None:
    session.configure_idle(timeout_ms=8000)     # 0 disables idle entirely

async def on_user_idle(self, interaction: Interaction) -> None:
    idle = interaction.idle
    if idle is not None and idle.level == 1:
        async with interaction.say() as speech:
            await speech.speak("Still there?")
    # returning without speaking is fine — the silence just rides
```

## Browser messages: `on_client_message`

`client.sendClientMessage(type, data)` in the browser arrives here as a
`ClientMessage` with `.type`, `.data`, `.id` (the browser-supplied message id, may
be empty) and `.interaction_id` (minted by Voice for this message). Voice delivers
every message and does not interpret it — the brain decides what it's worth:

```python
async def on_client_message(self, session: Session, message: ClientMessage) -> None:
    if message.type == "state_sync":
        self._screen = message.data          # silent: nothing is spoken
    elif message.type == "photo_upload":
        # Take the floor: touching `.interaction` claims the pre-minted id, so a
        # barge-in cancels this reply and Voice is told the interaction completed.
        async with message.interaction.say() as speech:
            await speech.speak("Got the photo — let me take a look.")
```

Touching `message.interaction` is what takes the floor; it is lazy and idempotent.
If you never touch it, no interaction is driven and the id simply goes unused.

`type == "action_outcome"` never reaches this callback — it is routed to the
`callback=` you passed to the `action(...)` that fired it.

## The `Conversation` and `Message` objects

`session.conversation.messages` is the framework-maintained transcript — a list of
`Message(role, content)` where `role` is `"user"` or `"assistant"` and an
assistant message's `content` is the **heard** text (post-interruption truth). The
brain never writes to it directly; rebuild your model context from it each turn.

## Serving the brain

You serve the same `Brain` class over one of two transports. Both build a **fresh
brain per session** from a zero-arg `() -> Brain` builder (inject dependencies here):

```python
def build() -> MyBrain:            # a fresh instance per session
    return MyBrain(llm=my_client)
```

`run_session` takes this builder directly as `brain_builder=`; the outbound agents
(`CortexAgent` / `DirectAgent`) take it wrapped in `brain_factory(build)`.

### Inbound (primary)

The runtime dials into your `wss://` route. The framework-agnostic primitive is
`run_session`, which drives a session over any WebSocket you hand it:

```python
from voqalize.sdk import run_session

await run_session(
    channel,                       # anything with async send(bytes)/recv()->bytes
    brain_builder=build,           # a () -> Brain builder; or brain=MyBrain
    session_id=session_id,
    token=token,                   # the Authorization header value
    public_keys=None,              # None → embedded Voqalize platform keys
    allow_unverified=False,        # True only for local dev
)
```

Mount it on FastAPI/Starlette/aiohttp (see the [Quickstart](/docs/start/quickstart/)
and [Inbound server](/docs/deploy/inbound/)). For a zero-boilerplate local server,
`DirectAgent` / `serve_direct(MyBrain, ...)` own the socket for you.

### Cortex (fallback)

Your brain dials *out* to a Cortex relay; many sessions multiplex over one socket:

```python
from voqalize.sdk import CortexAgent, brain_factory

agent = CortexAgent(
    version="1.0.0",
    cortex_url="wss://cortex.voqalize.com/agent",  # verbatim from create_agent_credentials
    factory=brain_factory(build),  # the () -> Brain builder, wrapped
    api_key="sk_…",                # OR authorization_provider=lambda: "Bearer <jwt>"
)
await agent.run()
```

`serve(MyBrain, ...)` is the sugar wrapper. `serve_auto(MyBrain, mode=...)` picks
inbound vs. Cortex from `$VOQAL_AGENT_MODE`. See [Cortex relay](/docs/deploy/cortex/).

## Examples

- **`sdk/python/examples/echo`** — the smallest complete brain (greet + echo, no
  LLM). Start here.
- **`sdk/python/examples/travel`** — a full agent: a real Gemini function-calling
  loop, multi-inference tool round-trips, screen-driving via `interaction.action`,
  and rebuilding model context from the heard transcript.
- **`sdk/python/examples/fastapi_inbound`** — the production inbound shape, with
  proper close-code discipline.
- **`sdk/python/examples/travel_adk`** — the same travel agent written as a native
  Google ADK agent, handed to the SDK's ADK adapter (`voqalize.google_adk`).
  Install the optional extra for it: `uv pip install -e 'sdk/python[adk]'`.

## Next

- **[Handling a conversation](/docs/brain/conversation/)** — LLM streaming, tools,
  and UI actions in depth.
- **[Voice protocol reference](/docs/reference/voice-protocol/)** — the frames
  beneath the SDK.
