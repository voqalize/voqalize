---
title: The Brain API
description: Every callback a brain may implement, its signature, and what it is handed. The one that is required, and the two that are generators.
---

A brain is a subclass of `Brain`. Voqalize opens one WebSocket per session, and
what arrives on it reaches your code as one of eight callbacks, each handed the
`Session` for that call. This page is every signature on that surface,
read out of `voqalize-agent-sdk` 0.2.0 and speaking wire version 3.

Only `on_user_message` is required. Two callbacks are async generators —
`on_user_message` and `on_user_idle` — and those two are the only moments the
floor is yours. Everything that is not speech is a method on `session`, callable
from any callback and from work that outlives one.

## The import surface

`voqalize.sdk` exports twenty-two names.

| Name | Kind | What it is |
|---|---|---|
| `Brain` | class | The callback surface. Subclass it. |
| `Session` | class | The per-call capability handle every callback is handed. |
| `Action` | class | Base for a typed command to the app. See [Actions](/build/brain/actions/). |
| `UserMessage` | dataclass | The caller finished an utterance. |
| `UserIdle` | dataclass | The caller went quiet past the idle timeout. |
| `RTVIMessage` | dataclass | One message from the app. |
| `Finalize` | dataclass | What the caller actually heard, for one speech unit. |
| `Error` | dataclass | A signal from Voqalize. |
| `SpeechStart` | dataclass | Opens a speech unit. |
| `Chunk` | dataclass | Text to speak inside an open unit. |
| `SpeechEnd` | dataclass | Closes the open unit. |
| `Speech` | type alias | `SpeechStart \| Chunk \| SpeechEnd` — what a generator may yield. |
| `ErrorCode` | enum | The code on an `Error`. See [Error codes](/reference/errors/). |
| `RTVIType` | enum | The RTVI message types. See [The RTVI plane](/reference/rtvi/). |
| `WireError` | exception | A brain broke a wire obligation. |
| `RequestRejected` | exception | Voqalize refused a `configure` call. |
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
from voqalize.sdk.wire import Config, IdleConfig, Language, SttConfig, TtsConfig, Voice
```

The two shipped model adapters are not among them either — importing
`voqalize.sdk` pulls no model vendor, so each lives in its own module behind the
`gemini` extra. There is no ADK adapter; that one was removed.

## `Brain`

### The eight callbacks

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

The two speaking callbacks are declared `def … -> AsyncGenerator[Speech, None]`
in the base class because that is the type an async generator function returns.
You write them as `async def` with `yield` in the body:

```python
class Concierge(Brain):
    async def on_user_message(self, session, msg):
        yield SpeechStart()
        yield Chunk("Let me check that")
        yield SpeechEnd()
```

The base `on_user_message` raises `NotImplementedError`; the base `on_user_idle`
returns an empty generator, which declines the floor. The other six default to
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
first turn, so a caller who talks over the greeting interrupts it like any other
turn.

**No model call belongs here.** A fixed line, or at most a template over
`session.init` — `f"Hi {name}, how can I help?"` — and nothing else. It is
`async` so you can look that name up, not so you can generate the sentence: this
is the one moment a connected caller is sitting there hearing nothing.

### Failure at the two opening hooks

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
| `id` | `str` | The session id Voqalize assigned — the same string in `?session_id=`, in your logs, and in [the event stream](/operate/reading-a-call/). |
| `init` | `dict[str, Any]` | The opaque init data handed to Voqalize at connect. Read your own keys out of it; the SDK interprets none of it. |

There is no `SessionStart` object in the SDK. The frame's payload arrives as
these two attributes, and its turn id is the turn the greeting is bound to.

### Methods

```python
def dispatch(self, action: Action) -> None: ...
def send_rtvi(self, type: RTVIType, data: Any = None, *, id: str | None = None) -> None: ...
def end(self, reason: str = "agent_ended") -> None: ...
def next_speech_id(self) -> int: ...
async def configure(self, config: Config) -> None: ...
```

**`next_speech_id`** takes the next speech id for the session. Name a unit with
it — `SpeechStart(id=sid)` — and the same value arrives on that unit's
`Finalize`, which is how a brain recognises its own work after the fact. Taking
one and not using it is fine: ids are opaque and gaps mean nothing. Reusing one
raises `WireError`.

**`dispatch`** sends one action to the app and never blocks; nothing comes back.
It rides RTVI's own `ui-command`, which a pipecat client reads with
`useUICommandHandler`. See [Actions](/build/brain/actions/).

**`send_rtvi`** sends one RTVI message. Only the five types a brain may
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

`Config` has three sections, each optional: `tts` (`voice`, `language`), `stt`
(`language`), `idle` (`timeout_ms`). A section left `None` is untouched, and so
is a field left `None` inside a section that is present.

- **Naming a language on one leg and not the other raises `ConfigError`** before
  anything reaches the wire. They may differ — fewer languages can be spoken
  than understood — but you state both. See [Voice and language](/reference/catalog/).
- **A session runs with `idle.timeout_ms` at 0**, which is idle detection off.
  Until you set it, `on_user_idle` never fires.
- **Rejection is all-or-nothing.** `RequestRejected` means Voqalize applied none
  of it and the call is still in the state it was in; `detail` is Voqalize's own
  reason, written to be shown.
- **Acceptance is not audibility.** `tts` lands on the next speech unit, `stt`
  once the open turn commits, `idle` immediately.
- The call waits `REQUEST_TIMEOUT_S`, 10.0 seconds, then raises `TimeoutError`
  saying that whether it applied is unknown.

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

`idle.level` resets the moment the caller says something, so a brain can nudge at
1 and wrap up at 3.

`fin.heard` is the one to record. See [Transcripts](/build/brain/transcripts/).

**The dataclass is not the frame.** `Finalize` is the SDK's shape; the wire
carries different names, and a reader moving between this page and
[the wire](/reference/wire/) has to know the mapping:

| Wire field | SDK attribute | |
|---|---|---|
| `speech_id` | `speech_id` | Same name, same value — the id the unit was opened under. |
| `heard_text` | `heard` | Same value. |
| — | `generated` | Not on the wire. The SDK keeps the text each unit sent, so the comparison below has both halves without you writing a ledger. |
| — | `interrupted` | Not on the wire either: `heard != generated`. |

`heard` is a verbatim prefix of `generated`, so equal means the unit played out
and shorter means the caller cut it off. Voqalize used to send that verdict as
well — a `FinalizeReason` — and stopped, because the end that generated the text
can work it out, and a copy of a fact you can derive is one more thing that can
be wrong.

## What a generator may yield

```python
@dataclass(frozen=True)
class SpeechStart:
    id: int | None = None    # name it, or let the SDK take the next id

@dataclass(frozen=True)
class Chunk:
    text: str

@dataclass(frozen=True)
class SpeechEnd: ...

Speech = SpeechStart | Chunk | SpeechEnd
```

One `SpeechStart` … `SpeechEnd` pair is one unit, and a unit is the granularity
at which Voqalize reports back what the caller heard. Yielding anything else, a
`Chunk` outside a unit, a `SpeechStart` inside one, or a `SpeechEnd` with no unit
open, raises `WireError`. A `Chunk` with empty text is dropped. See
[Speaking](/build/brain/speaking/).

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
[Inbound server](/build/inbound/).

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
| `api_key` | one of two | The `sk_…` agent secret, sent as `Authorization: Bearer`. |
| `authorization_provider` | one of two | A zero-arg callable returning a fresh `"Bearer <jwt>"` per connect. |
| `inbound_queue_maxsize` | no | Per-session inbound backlog before shedding. |

Passing both or neither of `api_key` and `authorization_provider` raises
`ValueError`. `serve` blocks until the connection closes permanently: every
session rides that one socket, demultiplexed by a 16-byte session prefix, and
you decide where the call lives. See [Cortex relay](/build/outbound/).

## Logging

Two pieces, and the split is deliberate: the context is always on, the sink is
opt-in.

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

## The two shipped adapters

Both are `Brain` subclasses, both are installed with the `gemini` extra
(`pip install "voqalize-agent-sdk[gemini]==0.2.0"`), and both are hosted exactly
like any other brain.

```python
from voqalize.sdk.gemini import GeminiBrain
from voqalize.sdk.gemini_interactions import GeminiInteractionsBrain
```

They take the same constructor:

```python
def __init__(
    self,
    *,
    client: genai.Client,
    system_instruction: str,
    model: str = DEFAULT_MODEL,
    max_tool_hops: int = 6,
) -> None: ...
```

and offer the same members to override, read or call:

| Member | Kind | What it does |
|---|---|---|
| `tools` | property | The tools the model may call, read once per turn. A list of bound `async def` methods. |
| `system_instruction` | property, settable | The prompt every hop carries. Set it from `on_session_start`, where this caller's facts are in hand. |
| `append_to_context(…)` | method | Add to the conversation the model sees, in the provider's own type. |
| `respond(session)` | async generator | Stream one turn, however many tool hops it takes. |

`GeminiBrain` hands the tool loop to `google-genai` and takes the record it kept;
`GeminiInteractionsBrain` runs the loop itself on the `interactions` API, where a
call and its result are linked by id rather than by position. `append_to_context`
takes a `types.Content` on the first and a `gi.UserInputStep` on the second — that
is the one place a brain written for one does not paste into the other.

`DEFAULT_MODEL` reads `VOQAL_GEMINI_MODEL` from the environment, falling back to
`gemini-3.5-flash`. Both classes force the model's minimum reasoning level: a
thinking budget on a voice turn is spent in silence the caller sits through, and
the thought parts are never spoken. Moving models means re-measuring both the
knob and the model's willingness to call tools at a level it accepts.

The tool declaration contract they share — the method name is the tool name, the
docstring is its description, and it takes exactly one pydantic model — is in
[Tools](/build/brain/tools/). Porting a brain you already have is
[Bringing an existing agent](/build/existing-agent/).

## What is not here

No conversation store. No model client. No `pipecat` import — installing this SDK
pulls none, and the wire is plain protobuf against plain dataclasses. `Session`
holds only what dies with the socket: in-flight request ids and the speech
counter. History, model context and domain state have a different lifetime, so
they are yours, in your process, in whatever shape your model takes.

## Read next

- [Your first brain](/build/brain/) — the same surface, taught rather than listed.
- [The wire](/reference/wire/) — what the frames underneath look like.
