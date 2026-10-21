---
title: The Brain API
description: Every callback a brain may implement, its signature, and what it is handed. Which one is required, and which are generators.
---

A brain is a subclass of `Brain`. Voqalize opens one WebSocket per session, and
what arrives on it reaches your code as a callback, each handed the `Session`
for that call. This page is every signature on that surface,
read out of `voqalize-agent-sdk` 0.9.0 and speaking wire version 3.

Only `on_user_message` is required. `on_user_message` and `on_user_idle` are
async generators, and they are the only moments the floor is yours. Everything that is not speech is a method on `session`, callable
from any callback and from work that outlives one.

## The import surface

`voqalize.sdk` exports these names.

| Name | Kind | What it is |
|---|---|---|
| `Brain` | class | The callback surface. Subclass it. |
| `Session` | class | The per-call capability handle every callback is handed. |
| `Action` | class | Base for a typed command to the app. See [Actions](/build/brain/actions/). |
| `UserMessage` | dataclass | The user finished an utterance. |
| `UserIdle` | dataclass | The user went quiet past the idle timeout. |
| `RTVIMessage` | dataclass | One message from the app. |
| `Finalize` | dataclass | What the user actually heard, for one speech unit. |
| `Error` | dataclass | A signal from Voqalize. |
| `TurnStep` | dataclass | One piece of work a turn did, for `session.report_step`. |
| `SpeechStart` | dataclass | Opens a speech unit. |
| `SpeechChunk` | dataclass | Text to speak inside an open unit. |
| `SpeechEnd` | dataclass | Closes the open unit. |
| `Chunk` | alias | The name `SpeechChunk` shipped under until 2026-09-08, kept working. Prefer `SpeechChunk`: it is the name the proto message, the wire frame and every recorded event also answer to. |
| `Speech` | type alias | `SpeechStart \| SpeechChunk \| SpeechEnd` — what a generator may yield. |
| `AppEvent` | class | Base for a typed thing the person did in your app. The app→brain direction of [`Action`](/build/brain/actions/). |
| `AppEvents` | class | Your brain's app→brain vocabulary. Hand it your `AppEvent` classes, give it every `RTVIMessage`, and `parse` returns your union or `None` — it never raises on a live call. |
| `ErrorCode` | enum | The code on an `Error`. See [Error codes](/reference/errors/). |
| `RTVIType` | enum | The RTVI message types. See [The RTVI plane](/reference/rtvi/). |
| `WireError` | exception | A brain broke a wire obligation. |
| `RequestRejected` | exception | Voqalize refused a `configure` call. |
| `Unsupported` | exception | The Voqalize serving this session does not honour the call — today, `cancel_speech` without `can_cancel_speech`. Raised before anything is sent. |
| `SessionRejected` | exception | The connection's token failed verification. |
| `Channel` | protocol | `send(bytes)` / `recv() -> bytes` — what `run_session` takes. |
| `run_session` | function | Run one session over a socket your framework accepted. |
| `serve` | function | Run every session over one outbound Cortex connection. |
| `configure_logging` | function | Install a loguru sink that renders the session fields. |
| `session_context` | context manager | Tag log lines with a call's identity. |

Configuration types are not among them. They live in `voqalize.sdk.wire`,
because the same definitions are accepted at session creation and over the
mid-call wire:

```python
from voqalize.sdk.wire import (
    Config, ConfigError, IdleConfig, Language, SttConfig, TtsConfig, Voice
)
```

`ConfigError` is there too, and not under `voqalize.sdk`, because it is raised by
`Config.__post_init__` rather than by anything on the session — it is a property
of the message, decided before the call is reached. See [why both halves
matter](/reference/catalog/#why-both-halves-matter).

The shipped model-backed brains are not among them either — importing
`voqalize.sdk` pulls no model vendor, so each lives in its own module behind its
own extra: `gemini`, `openai` or `litellm`. See [the shipped
adapters](#the-shipped-adapters). There is no ADK adapter; that one was removed.

## `Brain`

### The callbacks

Verbatim from the base class. `self` is your brain instance; a fresh one is
built per session, so nothing leaks between calls.

```python
async def on_session_start(self, session: Session) -> None: ...
async def greet(self, session: Session) -> str | None: ...
def on_user_message(self, session: Session, msg: UserMessage) -> AsyncGenerator[Speech, None]: ...
def on_user_idle(self, session: Session, idle: UserIdle) -> AsyncGenerator[Speech, None]: ...
async def on_rtvi(self, session: Session, msg: RTVIMessage) -> None: ...
async def on_finalize(self, session: Session, fin: Finalize) -> None: ...
async def on_error(self, session: Session, error: Error) -> None: ...
async def on_session_end(self, session: Session) -> None: ...
```

| Callback | Required | Yields | Fires |
|---|---|---|---|
| `on_session_start` | no | — | Once, on `SessionStart`, before `greet`. |
| `greet` | no | — | Once, after `on_session_start` returns. |
| `on_user_message` | **yes** | speech | On every `UserMessage`. `msg.text` is the finalized transcript. |
| `on_user_idle` | no | speech | On every `UserIdle`. Off unless you set a timeout. |
| `on_rtvi` | no | — | On every whitelisted RTVI message from the app. |
| `on_finalize` | no | — | Once per speech unit that produced audio, after playout. |
| `on_error` | no | — | On an `Error` frame. The session is never killed by it. |
| `on_session_end` | no | — | Once, for any reason, as the socket closes. |

The speaking callbacks are declared `def … -> AsyncGenerator[Speech, None]`
in the base class because that is the type an async generator function returns.
You write them as `async def` with `yield` in the body:

```python
class Concierge(Brain):
    async def on_user_message(self, session, msg):
        yield SpeechStart()
        yield SpeechChunk("Let me check that")
        yield SpeechEnd()
```

The base `on_user_message` raises `NotImplementedError`; the base `on_user_idle`
returns an empty generator, which declines the floor. The rest default to
doing nothing.

**A speaking callback with no `yield` anywhere in its body is not a generator.**
Python decides that from the source, not from the annotation, so a turn that only
ends the call or only updates the screen compiles to an ordinary coroutine. The
SDK awaits it rather than driving it, which is the only reading that is not a
silent no-op — but the callback speaks nothing, and that is the shape it has.

**`on_rtvi` must not be a generator.** A `yield` anywhere in its body raises
`WireError` naming the rule: an app message never takes the floor, so there is
nothing to yield there. Render with `session.dispatch(...)`, answer with
`session.send_rtvi(...)`, hang up with `session.end()`. See
[Context and history](/build/brain/context/).

### `greet`

```python
async def greet(self, session: Session) -> str | None: ...
```

Returns the opening line as one string, or `None` — the default — to open
silently. The SDK speaks the string as one speech unit bound to the session's
first turn, so a user who talks over the greeting interrupts it like any other
turn.

**No model call belongs here.** A fixed line, or at most a template over
`session.init` — `f"Hi {name}, how can I help?"` — and nothing else. It is
`async` so you can look that name up, not so you can generate the sentence: this
is the one moment a connected user is sitting there hearing nothing.

### Failure in `on_session_start` or `greet`

An exception out of `on_session_start` or out of `greet` fails the session: the
SDK emits a fatal `Error` naming the hook that raised and ends the call. Neither
half of a half-opened session is a state to keep a call alive in — a greeting
spoken over state that was never built promises a working agent, and a session
whose greeting never arrives is dead air on the one turn nothing retries.

An exception out of any other callback is logged and the session continues.

### `Brain.session`

```python
@property
def session(self) -> Session: ...
```

The same object every callback is handed, reachable from anywhere on the
instance. Inside a callback, use the parameter. This property exists for code
that cannot be handed anything — a tool's signature is the schema the model is
given, so a `session` parameter is a field the model tries to fill. Tools read
`self.session`; callbacks take the parameter. Reading it before the session
starts (in `__init__`, for instance) raises `RuntimeError`.

## `Session`

Created by the SDK when `SessionStart` arrives and handed to every callback. Its
lifetime is exactly the socket's.

### Attributes

| Attribute | Type | What it holds |
|---|---|---|
| `id` | `str` | The session id Voqalize assigned — the same string in `?session_id=`, in your logs, and in [the call record](/operate/reading-a-call/). |
| `init` | `dict[str, Any]` | The opaque init data handed to Voqalize at connect. Read your own keys out of it; the SDK interprets none of it. |
| `capabilities` | `frozenset[Capability]` | What this Voqalize said it honours beyond the wire version's baseline, at `SessionStart`. Read the `can_*` properties rather than the set. |
| `can_cancel_speech` | `bool` | Whether `cancel_speech` is honoured. Fixed for the session's life. |
| `can_report_steps` | `bool` | Whether `report_step` is recorded. Fixed for the session's life. |

There is no `SessionStart` object in the SDK. The frame's payload arrives as
these attributes, and its turn id is the turn the greeting is bound to.

### Methods

```python
def dispatch(self, action: Action) -> None: ...
def send_rtvi(self, type: RTVIType, data: Any = None, *, id: str | None = None) -> None: ...
def end(self, reason: str = "agent_ended") -> None: ...
async def configure(self, config: Config) -> None: ...
async def cancel_speech(self, speech_id: int | None) -> Finalize: ...
def report_step(self, step: TurnStep, *, turn_id: int | None = None) -> None: ...
```

**`dispatch`** sends one action to the app and never blocks; nothing comes back.
It rides RTVI's own `ui-command`, which a pipecat client reads with
`useUICommandHandler`. See [Actions](/build/brain/actions/).

**`send_rtvi`** sends one RTVI message. Only the types a brain may
originate are accepted — `server-message`, `server-response`, `error-response`,
`ui-command`, `ui-job-group` — and any other raises `WireError` listing them.
Quote `id` back from the message you are answering. See
[The RTVI plane](/reference/rtvi/).

**`end`** hangs up. Idempotent, callable from anywhere. To say goodbye first,
speak it and then call this: the generator body resumes only after the SDK has
consumed what you yielded, so writing it in that order *is* the ordering, and
the goodbye is heard. `reason` is logged locally and does not cross the wire.

**`configure`** overrides the session's configuration mid-call and is awaited,
because Voqalize answers it. The session opened on the configuration supplied
to `sessions.connect`, resolved over Voqalize's defaults; the brain may change
it from `on_session_start` or later.

```python
from voqalize.sdk.wire import Config, Language, SttConfig, TtsConfig, Voice

await session.configure(
    Config(
        stt=SttConfig(language=Language.TA),
        tts=TtsConfig(language=Language.TA, voice=Voice.OMNIVOICE_GAURI),
    )
)
```

`Config` has optional `tts` (`voice`, `language`), `stt` (`language`,
`patience`) and `idle` (`timeout_ms`) sections. A section left `None` is untouched, and so
is a field left `None` inside a section that is present.

- **Naming a language on one leg and not the other raises `ConfigError`** before
  anything reaches the wire. They may differ — fewer languages can be spoken
  than understood — but you state both. See [Voice and language](/reference/catalog/).
- **A session runs with `idle.timeout_ms` at 0**, which is idle detection off.
  Until you set it, `on_user_idle` never fires.
- **Rejection is all-or-nothing.** `RequestRejected` means Voqalize applied none
  of it and the call is still in the state it was in; `detail` is Voqalize's own
  reason, written to be shown.
- **Acceptance is not audibility.** `tts` lands on the next speech unit, `idle`
  immediately, and the `stt` fields differ from each other: `language` waits for
  the open turn to commit, `patience` applies at once — to the pause already
  running. Why they differ is [the catalog's
  argument](/reference/catalog/#what-the-absence-buys).
- **`stt.patience` is a scale from 0 to 10**, not a duration, and a value off it
  raises `ConfigError` where you build the `SttConfig` rather than at the far end
  of the wire. Unset takes the deployment's own calibration, which is 7.
- The call waits `REQUEST_TIMEOUT_S`, 10.0 seconds, then raises `TimeoutError`
  saying that whether it applied is unknown.

**`cancel_speech`** stops one speech unit now and returns its `Finalize` — what
the user heard before the cut. Name the unit by the id the SDK wrote onto the
`SpeechStart` you yielded:

```python
start = SpeechStart()
yield start
...
fin = await session.cancel_speech(start.speech_id)   # fin.heard, fin.interrupted
```

- **The answer is the unit's own `Finalize`**, the one Voqalize owes every unit.
  `on_finalize` still receives it. There is no acknowledgement besides it.
- **The turn stays open.** No other turn is cut, and the generator may open a
  new unit straight away. The cancelled unit needs no `SpeechEnd`; anything
  yielded for it afterwards is dropped by the SDK.
- **Already finished, or cancelled twice:** returns the `Finalize` already
  received, and sends nothing.
- **Refused before sending:** `Unsupported` when `can_cancel_speech` is false;
  `ValueError` for an id this session never opened, or `None` — a
  `SpeechStart` the SDK has not consumed yet.
- The call waits `REQUEST_TIMEOUT_S`, 10.0 seconds, for the `Finalize`, then
  raises `TimeoutError`.
- `heard` is accurate to about one word either way, and today the cut stops
  every unit still playing or queued, each with its own `Finalize`. See
  [stopping your own speech](/build/brain/speaking/#stopping-your-own-speech).

Raise `patience` for a caller reading a number off a card, or thinking aloud in a
language they are translating into. Lower it when the turns are short and known —
a yes/no, a digit, a menu choice — and the wait is the only thing the caller
notices. Most brains should leave it alone: it is a floor on how long a pause has
to run before it counts as the end, and moving it trades one kind of wrong
against the other rather than removing either.

**`report_step`** tells Voqalize about one piece of work your brain did for a
turn: a model request, a tool, a database query, an API or MCP call. It never
blocks and nothing comes back; Voqalize keeps it in the call record beside the
turn, and the console shows a turn's steps as a timeline. The
[model-backed brains](#the-shipped-adapters) report every model request and every
tool for you unless built with `report_steps=False`. Report anything else your
brain does the moment it ends:

```python
import time

from voqalize.sdk import TurnStep

started = time.monotonic()
rows = await db.fetch(query)
if session.can_report_steps:
    session.report_step(
        TurnStep(
            kind="database",
            name="orders",
            duration_ms=round((time.monotonic() - started) * 1000),
            counts={"rows": len(rows)},
        )
    )
```

```python
@dataclass(frozen=True)
class TurnStep:
    kind: str                           # "model", "tool", or your own word: "database", "http", "mcp"
    name: str                           # which one: the model, the tool, the table
    duration_ms: int
    provider: str = ""                  # the company whose meter ran; empty for your own work
    start_ms: int | None = None         # after the turn's stimulus; None: it ended now
    first_output_ms: int | None = None  # for a step that streams
    counts: Mapping[str, int] = {}      # how much of what, by name
```

- **Facts about the work, never its content.** No prompt, no arguments, no
  result, no query text — and no prices: a price changes on a date nobody here
  controls, so cost is computed from the counts by whoever reads them.
- **The names are open.** Use the documented `kind` words and count names in
  [the wire reference](/reference/wire/#what-a-turn-did) where they fit, so
  every brain's steps add up the same way, and your own words where they do not.
- **Leave out a count you do not have** rather than writing `0`; absent means
  not reported.
- **`start_ms` is placed for you** when you report a step as it ends: it began
  `duration_ms` before now. Give it yourself for a step you report later.
- **`turn_id` defaults to the turn the call is made from**, which is right
  inside a speaking callback, including in its `finally`. Outside a turn, pass
  it, or the call raises `ValueError`.
- **Refused before sending:** `Unsupported` when `can_report_steps` is false.
  Check it first; a Voqalize that does not record steps would skip the frame.

## What a callback is handed

Frozen dataclasses, every field listed.

```python
@dataclass(frozen=True)
class UserMessage:
    text: str

@dataclass(frozen=True)
class UserIdle:
    level: int          # consecutive escalations, 1 is the first nudge
    idle_ms: int        # silence elapsed when Voqalize noticed

@dataclass(frozen=True)
class RTVIMessage:
    type: RTVIType
    data: Any = None
    id: str | None = None

@dataclass(frozen=True)
class Finalize:
    speech_id: int      # the unit this reports on
    heard: str          # the delivered prefix, not what you generated
    generated: str      # what you sent for that unit, kept by the SDK

    @property
    def interrupted(self) -> bool:   # heard != generated
        ...

@dataclass(frozen=True)
class Error:
    code: ErrorCode
    message: str
    fatal: bool = False
```

`idle.level` resets the moment the user says something, so a brain can nudge at
1 and wrap up at 3.

`fin.heard` is the one to record. See [Transcripts](/build/brain/transcripts/).

**The dataclass is not the frame.** `Finalize` is the SDK's shape; the wire
carries different names, and a reader moving between this page and
[the wire](/reference/wire/) has to know the mapping:

| Wire field | SDK attribute | |
|---|---|---|
| `speech_id` | `speech_id` | Same name, same value. |
| `heard_text` | `heard` | Same value. |
| — | `generated` | Not on the wire. The SDK keeps the text each unit sent, so the comparison below has both halves without you writing a ledger. |
| — | `interrupted` | Not on the wire either: `heard != generated`. |

`heard` is a verbatim prefix of `generated`, so equal means the unit played out
and shorter means it was cut off — by the user, or by your own `cancel_speech`. Voqalize used to send that verdict as
well — a `FinalizeReason` — and stopped, because the end that generated the text
can work it out, and a copy of a fact you can derive is one more thing that can
be wrong.

## What a generator may yield

```python
@dataclass(frozen=True)
class SpeechStart:
    speech_id: int | None   # not a constructor argument; the SDK writes it as the unit opens

@dataclass(frozen=True)
class SpeechChunk:
    text: str

@dataclass(frozen=True)
class SpeechEnd: ...

Speech = SpeechStart | SpeechChunk | SpeechEnd
```

One `SpeechStart` … `SpeechEnd` pair is one unit, and a unit is the granularity
at which Voqalize reports back what the user heard. Yielding anything else, a
`SpeechChunk` outside a unit, a `SpeechStart` inside one, or a `SpeechEnd` with no unit
open, raises `WireError`. A `SpeechChunk` with empty text is dropped. A unit
closed by `cancel_speech` needs no `SpeechEnd`. See
[Speaking](/build/brain/speaking/).

`SpeechStart.speech_id` is `None` until the SDK consumes the yield, then the id
it minted for that unit — the one `Finalize` names and `cancel_speech` takes. It
plays no part in equality.

## Hosting

The same `Brain` runs on either entry point. Which one you use is a property of
your network, not of your code — see [Where the brain runs](/build/hosting/).

### `run_session`

```python
async def run_session(
    channel: Channel,
    *,
    brain: type[Brain] | Callable[[], Brain],
    session_id: str,
    token: str | None = None,
    public_keys: str | list[str] | None = None,
    allow_unverified: bool = False,
    inbound_queue_maxsize: int | None = None,
) -> None: ...
```

The channel is positional; everything else is keyword-only. `brain=` takes the
**class**, or any zero-arg callable returning one when the brain needs injected
dependencies (`brain=lambda: TravelBrain(llm=provider)`); it is called once per
session.

`channel` is anything satisfying the `Channel` protocol:

```python
class Channel(Protocol):
    async def send(self, data: bytes) -> None: ...
    async def recv(self) -> bytes: ...
```

Verification is on by default, against the public keys embedded in the SDK: pass
the `Authorization` header value as `token=` and the query parameter as
`session_id=`. `public_keys=` overrides the keys; `allow_unverified=True` skips
the check and is for local development. A token that fails raises
`SessionRejected`, and the caller should close the socket with code 4000, which
Voqalize reads as permanent. The claims themselves are in
[The wire](/reference/wire/).

`run_session` returns when the session ends or the socket errors, and it never
closes the channel — your framework owns the socket's lifecycle. See
[Deploy the brain](/build/hosting/#a-route-voqalize-dials).

### `serve`

```python
async def serve(brain_cls: type[Brain] | Callable[[], Brain], **cortex_kwargs: Any) -> None: ...
```

**Read the required arguments here, because the signature does not carry them.**
`**cortex_kwargs` is passed straight to the Cortex client's constructor, so
`version=` and `cortex_url=` are required and `api_key=` /
`authorization_provider=` are a choose-exactly-one pair — and a missing one is a
`TypeError` or a `ValueError` at the call, rather than something your editor
flags:

```python
await serve(
    Concierge,
    api_key=os.environ["VOQALIZE_AGENT_SECRET"],
    version="1.0.0",
    cortex_url=os.environ["VOQALIZE_CORTEX_URL"],
)
```

| Argument | Required | What it is |
|---|---|---|
| `version` | yes | Your agent's version string, sent as a connection header. |
| `cortex_url` | yes | The relay URL from `create_agent_credentials`. It already ends in `/agent`; the SDK appends nothing. |
| `api_key` | one of these | The `sk_…` agent secret, sent as `Authorization: Bearer`. |
| `authorization_provider` | one of these | A zero-arg callable returning a fresh `"Bearer <jwt>"` per connect. |
| `inbound_queue_maxsize` | no | Per-session inbound backlog before shedding. |

Passing both or neither of `api_key` and `authorization_provider` raises
`ValueError`. `serve` blocks until the connection closes permanently: every
session rides that one socket, demultiplexed by a 16-byte session prefix, and
you decide where the call lives. See [Cortex relay](/build/hosting/#a-brain-that-dials-out).

## Logging

The split is deliberate: the context is always on, the sink is opt-in.

```python
@contextmanager
def session_context(session_id: str, *, tenant_id: str = "", agent_id: str = "") -> Generator[None]: ...

def configure_logging(*, level: str = "INFO", json_logs: bool = False) -> None: ...
```

**`session_context`** puts `service`, `session_id`, and any `tenant_id` /
`agent_id` into loguru's `extra` via a `ContextVar`. Both entry points already
wrap every session in it, so a bare `from loguru import logger` anywhere in your
brain — and in any task it spawns — logs with the call attached, with no argument
threaded through. Call it yourself only to tag work that runs outside a session.

**`configure_logging`** installs a loguru sink that renders those fields. The SDK
never calls it: it replaces loguru's handlers for the whole process, which a
library has no business doing to its host. Call it from your own entrypoint if
you have no loguru configuration; if you do have one, add `{extra}` to your
format instead. `json_logs=True` writes one JSON object per line with
`session_id`, `tenant_id` and `agent_id` promoted to the top level.

Binding fields onto a handler whose format never prints them looks exactly like
working, and every one of those fields is computed and thrown away. The
`session_id` is the join key across both sides of the call — see
[Reading a call back](/operate/reading-a-call/).

## The shipped adapters

Three model-backed brains ship with the SDK, one per model API, and they are one
brain underneath. The voice core, `voqalize.sdk.voice`, holds everything about a
voice turn that is not about one model: speech opened on the first word, tools
run mid-sentence after the words before them, results filed for the next request
unless the tool is marked, `max_tool_hops`, heard truth, the greeting in the
history, the `TOOL_BUDGET_MS` warning, the `turn:` log line and a
`TurnStep` for every model request and tool. Each class below is that core plus one provider's layer, which
calls the model's API and keeps the conversation in the provider's own types.
Subclass a layer, never the core.

| Class | Module | Extra | Speaks to |
|---|---|---|---|
| `GeminiBrain` | `voqalize.sdk.gemini` | `gemini` | Gemini's `generate_content`. |
| `OpenAIBrain` | `voqalize.sdk.openai` | `openai` | OpenAI's Responses API. |
| `LiteLLMBrain` | `voqalize.sdk.litellm` | `litellm` | Any model LiteLLM reaches, as chat messages. |

```python
from voqalize.sdk.gemini import GeminiBrain
from voqalize.sdk.openai import OpenAIBrain
from voqalize.sdk.litellm import LiteLLMBrain
from voqalize.sdk.voice import TOOL_BUDGET_MS, ToolChoice, needs_result_now
```

`GeminiBrain` is installed with `pip install "voqalize-agent-sdk[gemini]==0.9.0"`;
the other two take the `openai` and `litellm` extras the same way. All three are
hosted exactly like any other brain.

### The constructors

They share one shape. Every argument is keyword-only, and the brain is built
once per session, so a client constructed in your subclass's `__init__` belongs
to that call.

```python
class GeminiBrain:
    def __init__(
        self,
        *,
        client: genai.Client,
        system_instruction: str,
        model: str = DEFAULT_MODEL,
        max_tool_hops: int = 6,
        report_steps: bool = True,
    ) -> None: ...

class OpenAIBrain:
    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        system_instruction: str,
        model: str,
        reasoning: str | None = None,
        options: Mapping[str, Any] | None = None,
        max_tool_hops: int = 6,
        report_steps: bool = True,
    ) -> None: ...

class LiteLLMBrain:
    def __init__(
        self,
        *,
        system_instruction: str,
        model: str,
        reasoning: str | None = None,
        options: Mapping[str, Any] | None = None,
        max_tool_hops: int = 6,
        report_steps: bool = True,
    ) -> None: ...
```

| Argument | On | What it does |
|---|---|---|
| `system_instruction` | all | The prompt every request carries. |
| `model` | all | The model every request names. Required on `OpenAIBrain` and `LiteLLMBrain`; `GeminiBrain` defaults it. On `LiteLLMBrain` it is LiteLLM's model string. |
| `max_tool_hops` | all | How many times one turn may ask the model again for a marked tool's result. |
| `report_steps` | all | Send a `TurnStep` to Voqalize for every model request and tool. On by default; `False` keeps the numbers in your logs only. |
| `client` | Gemini, OpenAI | The provider's async client, with its keys. `LiteLLMBrain` has none: LiteLLM reads keys from the environment, or from `options`. |
| `reasoning` | OpenAI, LiteLLM | The model's reasoning effort: `"none"`, `"low"`, `"medium"` or `"high"`, or `None` for the model's own default. |
| `options` | OpenAI, LiteLLM | Passed as they are to every `responses.create` or `litellm.acompletion` call, for whatever the class does not name. |

**Reasoning is silence.** On a voice turn every reasoning token is spent before
the first word, and none of it is spoken. `GeminiBrain` forces the model's
minimum thinking level and takes no `reasoning` argument; on the other two, start
low and measure.

`DEFAULT_MODEL` reads `VOQAL_GEMINI_MODEL` from the environment, falling back to
`gemini-3.5-flash`. Moving models means re-measuring both the thinking knob and
the model's willingness to call tools at a level it accepts.

What each layer does differently:

- **`OpenAIBrain` keeps the conversation in your process.** Every request sends
  the whole context with `store=False` and no `previous_response_id`, because a
  conversation kept on OpenAI's side cannot be told that the user heard half of
  the last sentence. Encrypted reasoning items go back in as they came, so a
  reasoning model keeps its thread across a tool call.
- **`LiteLLMBrain` does not carry reasoning between requests.** Chat messages
  have no place for a provider's reasoning items, so each request reasons
  afresh. A call runs when its arguments are complete, which over chat
  completions is when the response ends, so the words before it have already
  been spoken. GPT-6 with tools and a reasoning effort needs the Responses
  bridge, `"openai/responses/<model>"`.
- **`GeminiBrain` declares tools through google-genai**, which validates one
  pydantic model parameter and nothing else. The other two declare a tool from
  its signature and validate plain parameters too. See
  [Tools](/build/brain/tools/#one-pydantic-model-or-nothing-at-all).

### The members

All three offer the same members to override, read or call:

| Member | Kind | What it does |
|---|---|---|
| `tools` | property | The tools the model may call, read once per turn. A list of bound `async def` methods, each returning within `TOOL_BUDGET_MS`. |
| `system_instruction` | property, settable | The prompt every request carries. Set it from `on_session_start`, where this user's facts are in hand. |
| `model` | property | The model every request names. |
| `append_note(text)` | method | Add one sentence to the context, on the user's side, without starting a turn. |
| `say_line(line, *, remember=False)` | async generator | Speak a line the brain wrote itself, as a unit of its own. |
| `respond(session)` | async generator | Stream one turn, however many requests it takes. |
| `respond_with(session, *, tools)` | async generator | One more model loop on the turn under way, with the tools limited by a `ToolChoice`. |

`GeminiBrain` also keeps `append_to_context(content)`, which takes a Gemini
`types.Content` with role `user`: the same as `append_note`, for what only
Gemini takes, such as an image or a PDF part.

**`append_note`** appends immediately, once, where you call it. Nothing
debounces or re-renders it, and it is never cut by heard truth or dropped as an
unanswered call. Calling it from inside a tool is safe: a call's result is filed
directly after the call, so the note lands after both.

```python
async def on_rtvi(self, session, msg):
    match EVENTS.parse(msg):
        case QuantitySet() as e:
            self.append_note(f"(They set {e.item_id} to {e.quantity}.)")
```

**`say_line`** is for a line the model did not write, yielded from inside a
speaking callback. By default it stays out of the context, so the model never
reads words it did not choose; `remember=True` puts it in as the model's words,
cut to what was heard like any other unit. Use it rather than yielding the unit
yourself: every unit Voqalize plays gets a finalize, and a unit the brain did not
open would take the finalize meant for the model's next one.

```python
async for event in self.say_line("One moment, opening it."):
    yield event
```

**`respond_with`** asks again within the same turn, with every request of that
loop limited by `tools`:

| `ToolChoice` | The model |
|---|---|
| `ToolChoice.AUTO` | may call any tool. The same as `respond`. |
| `ToolChoice.NONE` | may call none, so it has to speak. |
| `ToolChoice.only(name)` | must call `name`, and no other tool. |

The tools stay declared either way, so the calls already in the context still
read. It goes straight to the voice core rather than through `respond`, so an
override of `respond` that calls it runs once per turn:

```python
from voqalize.sdk import SpeechStart
from voqalize.sdk.voice import ToolChoice


class Desk(OpenAIBrain):
    async def respond(self, session):
        spoke = False
        async for event in super().respond(session):
            spoke = spoke or isinstance(event, SpeechStart)
            yield event
        if not spoke:
            async for event in self.respond_with(session, tools=ToolChoice.NONE):
                yield event
```

### The tool loop

A turn is one request. Each call runs as it arrives, after the speech before it
has gone out, and its result is read with the next request, which is the user's
next message unless the tool is marked `@needs_result_now`. A response that
called a marked tool is followed at once by another request carrying every
result it produced. This is the voice core's, so it is the same on every model.

`max_tool_hops` caps how many times one turn asks again. The last of those
requests may not call a tool, so the model has to answer. Only marked tools ask
again, so unmarked ones never count against it.

| Name | Kind | What it does |
|---|---|---|
| `needs_result_now` | decorator | Marks a tool whose result the model must read before it finishes its reply. Sets an attribute and nothing else. |
| `TOOL_BUDGET_MS` | constant | How long a tool may take, in milliseconds, before it is logged as slow. Nothing is cancelled. |

Both live in `voqalize.sdk.voice`, and each layer's module re-exports them, so
`from voqalize.sdk.gemini import needs_result_now` keeps working. Neither is
exported from `voqalize.sdk`, because nothing there imports a model vendor.

Every turn logs one `turn:` line per model loop, from the `voqalize.sdk.voice`
logger: requests, tools run and how many were marked, whether the turn said
nothing, the times, and the token counts summed over the turn's requests. Unless
built with `report_steps=False`, every request and every tool also goes to
Voqalize as a `TurnStep` when `session.can_report_steps` is true: the model
request with its own token counts, the tool with its time.

The tool declaration contract, the mark and the budget are in
[Tools](/build/brain/tools/). Porting a brain you already have is
[Bringing an existing agent](/build/existing-agent/).

### `GeminiInteractionsBrain`

:::caution[`GeminiInteractionsBrain` is experimental]
Every demo brain runs on `GeminiBrain`, and the last one that did not moved across
on 2026-09-08. The interactions adapter's interruption path has open defects: a
step interrupted before its first delta stays in the context forever, and text
buffered during a step is discarded if a barge-in lands before the step closes. Build on `GeminiBrain`; this one is kept, and tested, for the
properties it has that `generate_content` does not.
:::

```python
from voqalize.sdk.gemini_interactions import GeminiInteractionsBrain
```

It is not on the voice core and is unchanged. It is installed with the `gemini`
extra and takes `client`, `system_instruction`, `model` and `max_tool_hops`, with
no `report_steps`: it sends no `TurnStep`. It offers `tools`,
`system_instruction`, `append_to_context` and `respond`, and none of
`append_note`, `say_line` or `respond_with`.

It runs on the `interactions` API, where a call and its result are linked by id
rather than by position, and asks again after every response that made a call;
it ignores the mark and does not time its tools. `append_to_context` takes a
`gi.UserInputStep` here rather than a `types.Content`, which is the one place a
brain written for `GeminiBrain` does not paste into this one. It too forces the
model's minimum reasoning level.

## What is not here

No conversation store. No model client. No `pipecat` import — installing this SDK
pulls none, and the wire is plain protobuf against plain dataclasses. `Session`
holds only what dies with the socket: in-flight request ids and the speech
counter. History, model context and domain state have a different lifetime, so
they are yours, in your process, in whatever shape your model takes.

## Read next

- [Your first brain](/build/brain/) — the same surface, taught rather than listed.
- [The wire](/reference/wire/) — what the frames underneath look like.
