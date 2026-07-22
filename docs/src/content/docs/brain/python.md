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
from voqalize.sdk import Brain, Interaction, Session, SessionStart, AppEvent

class MyBrain(Brain):
    async def on_session_start(self, session: Session, start: SessionStart) -> None:
        ...   # setup + optional greeting; default no-op

    async def on_interaction(self, interaction: Interaction) -> None:
        ...   # REQUIRED: one committed user turn

    async def on_inference_finalized(self, inference: Inference) -> None:
        ...   # per-inference side effects (logging/persistence); default no-op

    async def on_app_event(self, session: Session, event: AppEvent) -> None:
        ...   # browser → brain message outside an interaction; default no-op

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
| `on_app_event(session, event)` | Browser sent a message outside any turn (e.g. `state_sync`, an uploaded photo). |
| `on_session_end(session)` | Session teardown. |
| `on_error(session, error)` | Non-fatal congestion/drop signal. Never fatal. |

## Speaking

There are no `say`/`generate` helpers — all bot speech goes through an **inference
bracket**. One bracket equals one model call (1:1 with the wire):

```python
# Agent-initiated (greeting) — runs under interaction_id = 0.
async with session.inference() as inf:
    await inf.speak("Hi! How can I help?")

# Response to a user turn.
async with interaction.inference() as inf:
    await inf.speak("You said: ")
    await inf.speak(interaction.transcript)   # many speak() calls per bracket are fine
```

Entering emits `VqlLLMFullResponseStart` (and mints the inference id); each
`speak(text)` emits a `VqlLLMText` chunk (empty string is a no-op); exiting emits
`VqlLLMFullResponseEnd`. A barge-in cancels the coroutine and unwinds any open
bracket.

## The `Session` object

Passed to `on_session_start`, `on_app_event`, `on_session_end`. Attributes:
`.id: str`, `.init: dict`, `.conversation: Conversation`.

```python
session.inference()                        # → bracket for agent-initiated speech (id 0)
session.action(name, args=None, *, callback=None) -> int
session.configure_tts(*, voice=None, language=None, model=None) -> None
session.configure_stt(*, language_hint=None, vad_confidence=None, ...) -> None
```

- **`action(name, args)`** fires a UI command to the browser *outside* any
  interaction (from `on_session_start`, `on_app_event`, or a background task).
  Returns a brain-minted `action_id`; the browser echoes an outcome that your
  optional `callback` receives. Never blocks.
- **`configure_tts`** changes voice/language/model for the **next** inference
  (never mid-utterance). Only the fields you pass change.
- **`configure_stt`** applies **live** (mid-utterance safe); `language_hint` swaps
  the recognition language mid-call. See the [catalog](/docs/reference/catalog/)
  for allowed values.

## The `Interaction` object

Passed to `on_interaction`. Attributes: `.id`, `.transcript: str` (what the user
said), `.session`, `.conversation` (the running transcript, already including this
turn).

```python
interaction.inference()                    # → bracket; one per model call
interaction.action(name, args=None, *, callback=None) -> int   # UI command, attributed to this turn
```

## The `Conversation` and `Message` objects

`session.conversation.messages` is the framework-maintained transcript — a list of
`Message(role, content)` where `role` is `"user"` or `"assistant"` and an
assistant message's `content` is the **heard** text (post-interruption truth). The
brain never writes to it directly; rebuild your model context from it each turn.

## Serving the brain

You serve the same `Brain` class over one of two transports. Pass a **factory** so
a fresh brain instance is built per session (inject dependencies with a lambda):

```python
from voqalize.sdk import brain_factory
factory = brain_factory(lambda: MyBrain(llm=my_client))
```

### Inbound (primary)

The runtime dials into your `wss://` route. The framework-agnostic primitive is
`run_session`, which drives a session over any WebSocket you hand it:

```python
from voqalize.sdk import run_session

await run_session(
    channel,                       # anything with async send(bytes)/recv()->bytes
    brain_builder=factory,         # or brain=MyBrain
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
    cortex_url="wss://cortex.voqalize.com/<pool>",
    factory=brain_factory(MyBrain),
    api_key="ak_…",                # OR authorization_provider=lambda: "Bearer <jwt>"
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

## Next

- **[Handling a conversation](/docs/brain/conversation/)** — LLM streaming, tools,
  and UI actions in depth.
- **[Voice protocol reference](/docs/reference/voice-protocol/)** — the frames
  beneath the SDK.
