# The Brain protocol — from first principles

> **Status: PROPOSAL.** This is the agreed shape from the design discussion of
> 2026-08-19, written down so we are working from the same model before anyone
> refactors code. It describes what the Brain *should* be, not what
> `voqalize/sdk/python` is today. Open questions are collected at the end;
> everything else is settled unless someone reopens it.

---

## 1. Why a voice agent needs its own contract

A text agent is a function: request in, response out. It may take as long as it
likes, its output is atomic, and nothing happens between the call and the return.

A voice agent breaks all three properties, and every design decision below is a
consequence of exactly one of them.

| Property of voice | Consequence for the contract |
|---|---|
| **Only one party can hold the air.** The human decides when they take it. | The brain never initiates. It is *given* the floor and responds. |
| **Output is consumed in real time and can be cut mid-word.** | What you generated is not what the user received. You must be told, afterwards, what actually landed. |
| **Silence is a signal.** A gap reads as a failure. | Latency is correctness, not a metric. The opening line cannot wait on a model. |
| **Output is a stream, not a value.** | You emit speech incrementally, in delimited units, and a unit can be truncated. |

Four properties. Everything that follows is bookkeeping on top of them.

---

## 2. The one asymmetry

**Voice owns the floor. The brain spends it.**

Voice — the runtime (PyGato today; the Go runtime tomorrow; pipecat is an
implementation detail of one of them, and never crosses the socket) — decides
when the brain may speak. It does this by invoking a callback. The brain's entire
job is to decide *what* to say when handed that opportunity, and to say nothing
at any other time.

There is no `request_floor`. There is no way for the brain to interrupt the user.
That is not an omission; it is the property that makes the system predictable.

---

## 3. The objects

Every object has exactly one job. If you cannot state its job in one line, it
should not exist.

| Object | Its one job |
|---|---|
| `Session` | The capability handle. Emits to the wire; owns machinery whose lifetime is the socket. |
| `UserMessage` | What the human said (or sent). |
| `AppMessage` | What the application said. |
| `IdleTrigger` | How long the human has been quiet, and how many times we've noticed. |
| `SpeechStart` / `Chunk` / `SpeechEnd` | One unit of speech, delimited, streamed. |
| `Action` | Pydantic base class for commands to the browser. You subclass it; your fields are the payload. Carries no audio, never touches the floor. |
| `EndSession` | Hang up — after everything queued ahead of it has been said. |
| `Finalize` | What the user actually heard for one unit of speech. |
| `Result` | The browser's answer to an `Action`. |

That is the whole vocabulary. Notably absent, and deliberately: no
`Interaction`, no `Conversation`, no `Inference`, no `SessionStart`, no
`ClientMessage`, no `IdleInfo`, no speech context manager.

### `Session` — and the line that keeps it thin

```python
class Session:
    id: str                      # the session id Voice assigned
    init: dict                   # the opaque payload from VqlStart

    def dispatch(self, action: Action) -> ActionHandle
    def configure_language(self, language, *, voice=None) -> None
    def configure_tts(self, *, voice=None, language=None) -> None
    def configure_stt(self, **knobs) -> None
    def configure_idle(self, *, timeout_ms) -> None
    def end(self, reason="agent_ended") -> None      # immediate; prefer yield EndSession()
```

The rule that decides what may live here:

> **Session owns nothing about the conversation. It owns the in-flight
> machinery whose lifetime is exactly the socket.**

Action ids, pending result handlers, and background work must die when the
socket dies — so they belong to the thing whose lifetime *is* the socket.
Conversation history, model context, and domain state have a different lifetime
(they may outlive the session; see resume) and belong to the Brain.

Session is *thin*, which is not the same as *inert*: it holds no conversation
state, but it can still send. It is the only thing in the SDK that knows a wire
exists.

---

## 4. The Brain

```python
class Brain:
    # ── lifecycle ────────────────────────────────────────────────────────
    async def on_session_start(self, session: Session) -> None: ...
    async def on_session_end(self, session: Session) -> None: ...
    async def on_error(self, session: Session, error: Error) -> None: ...

    # ── the opening line ─────────────────────────────────────────────────
    async def greet(self, session: Session) -> str | None: ...

    # ── the three triggers ───────────────────────────────────────────────
    async def on_user_message(
        self, session: Session, msg: UserMessage
    ) -> AsyncIterator[Speech | Action]: ...

    async def on_user_idle(
        self, session: Session, idle: IdleTrigger
    ) -> AsyncIterator[Speech | Action]: ...

    async def on_app_message(
        self, session: Session, msg: AppMessage
    ) -> AsyncIterator[Action | EndSession]: ...

    # ── what landed ──────────────────────────────────────────────────────
    async def on_finalize(self, session: Session, fin: Finalize) -> None: ...
```

Eight methods. Note the return types: **`on_app_message` returns
`AsyncIterator[Action | EndSession]`.** The rule "an application event may not
make the agent talk" is not a documented convention a reviewer has to catch — it
is a type the checker rejects. Hanging up is not speech, so it is in: a tap on
"end call" is the browser's to make, not a sentence the agent has to say first.

### `greet` is static by contract

`greet` returns a string, immediately, and the SDK speaks it. It is `async` so
you can look up a name, not so you can run a model. You *may* call an LLM; you
should not. The opening line is the one moment where the user is staring at a
connected session hearing nothing, and a model round-trip there is the single
most expensive latency in the product.

Returning `None` or `""` opens silently — valid for an agent that waits to be
addressed.

### The two speaking callbacks

`on_user_message` and `on_user_idle` are the only places speech can originate.
Both are async generators. They yield events; the SDK consumes them and puts
them on the wire.

```python
async def on_user_message(self, session, msg):
    yield SpeechStart()
    yield Chunk("Let me check that")
    yield Chunk(" for you…")
    yield SpeechEnd()

    rows = await self.catalog.search(msg.text)      # awaiting between units is fine
    yield ShowResults(rows=rows)

    yield SpeechStart()
    yield Chunk(f"I found {len(rows)}.")
    yield SpeechEnd()
```

Two speech units, one action, in that order, guaranteed.

### `on_app_message` acts but never speaks

```python
async def on_app_message(self, session, msg):
    if msg.type == "state_sync":
        self.screen = msg.data          # update state, yield nothing
    elif msg.type == "catalog_search":
        yield ShowSearchResults(rows=self.search(msg.data["query"]))
    elif msg.type == "hang_up":
        yield EndSession(reason="user tapped hang up")
```

A keystroke or a tap can update the screen, or end the call. It cannot make the
agent start talking over the person using it.

### `on_finalize` is how you learn what happened

```python
async def on_finalize(self, session, fin):
    # fin.inference_id, fin.heard, fin.interrupted
    self.history.append(("assistant", fin.heard))
```

It carries what the user *heard*, not what you generated — you already know what
you generated, and `inference_id` ties the two together.

---

## 5. Lifecycles

### 5.1 The session

```
Voice dials {brain_url}/s/{session_id}          (or the brain dials Cortex)
        │
        ├─ VqlStart(payload)
        │       └─ SDK builds Session
        │       └─ on_session_start(session)     ← configure language, load resume state
        │
        ├─ SDK calls greet(session) → str
        │       └─ opens a bracket, speaks it, closes it
        │
        ├─ … turns …
        │
        └─ socket closes
                └─ cancel everything in flight
                └─ on_session_end(session)       ← best-effort; never blocks the close
```

`on_session_start` runs **before** `greet`, which is what makes
`session.configure_language(...)` land before the first word is spoken. That
ordering is the contract, not an accident of implementation.

**If `on_session_start` raises, the call fails — it does not greet.** A greeting
promises a working agent, and after failed setup the state behind that promise is
not there; the caller believes it and starts talking to something that cannot
answer. The SDK puts a fatal `ErrorFrame` on the wire and ends the session, which
fails where the failure happened rather than a turn later.

### 5.2 A turn

```
user stops speaking
        │
        ├─ Voice endpoints the utterance, sends it over
        │
        ├─ SDK calls on_user_message(session, msg) → async generator
        │
        └─ SDK pulls events until the generator returns:
                SpeechStart()  → mint inference_id, open the unit on the wire
                Chunk(text)    → stream it
                SpeechEnd()    → close the unit
                an Action     → send it (floor-free, no audio)
        │
        └─ generator returns ⇒ the turn is over
```

The turn ends when the generator returns. **It does not wait for audio to
finish playing.** That is the next lifecycle, and it is the one that surprises
people.

### 5.3 An inference — three phases, separated in time

A unit of speech exists in three states, and the gap between them is where every
voice-specific difficulty lives.

```
  generated                spoken                    heard
  ─────────                ──────                    ─────
  you yielded it      TTS synthesized and       playout finished (or was cut)
  (instant)           the user is hearing it     → Finalize(inference_id, heard, interrupted)
                      (real time)
```

Consequences:

- A turn can complete while its speech is still playing.
- `on_finalize` fires **after** the generator has returned — sometimes long after.
- One `SpeechStart`/`SpeechEnd` pair produces **exactly one** `Finalize`, *if it
  produced audio*. A unit that emitted no chunks produces none.
- Therefore `on_finalize` fires **0..N times per turn**, and the brain chooses N
  by how many units it opens.

### 5.4 Barge-in

```
agent is speaking
        │
        ├─ user starts talking over it
        │
        ├─ Voice cuts TTS, tells the brain
        │
        ├─ SDK stops pulling the generator and closes it
        │       └─ any open speech unit is closed on the wire
        │       └─ your `finally` blocks run
        │
        ├─ Finalize(inference_id, heard=<partial>, interrupted=True)
        │
        └─ Voice discards stale in-flight frames until it sees fresh ones
```

The brain does not handle barge-in. It happens *to* the brain. The only visible
effect is that a generator stops being pulled and a `Finalize` arrives with
`interrupted=True` and a truncated `heard`.

### 5.5 An action, and its result

An action is a command the brain sends to the browser. It may answer.

```
yield ShowResults(rows=…, on_result=f)   ─or─   session.dispatch(same_thing)
        │
        ├─ SDK mints action_id, sends it, registers f on the session
        │
        ├─ browser executes it
        │
        ├─ browser echoes {action_id, status, data}   ─── or never answers
        │                                                       │
        └─ Result(action_id, "ok" | "error", data) → f          │
                                                                │
                       timeout_s elapses ── Result(…, "timeout", None) → f
```

Results are **session-scoped**, not turn-scoped, and this is structural rather
than arbitrary: a browser can take ten seconds to answer, by which time the
originating turn is long gone. A turn-scoped registry would drop it.

#### `Action` is a pydantic model; your subclass *is* the payload

**This one is already built.** `voqalize.sdk.Action` ships today
(`sdk/python/src/voqalize/sdk/actions.py`), `pydantic>=2.7` is a declared runtime
dependency of the SDK for exactly this reason, and `travel` and `orderdesk`
already declare their entire screen contract as `Action` subclasses. An earlier
draft of this section proposed a dataclass base; it was a regression against
shipping code. What follows is the class that exists, plus the two control fields
this protocol adds.

```python
class Action(BaseModel):
    """Subclass this. Your fields are what the browser receives."""

    # The wire name — set by __init_subclass__ from the class name, or from an
    # explicit `name=`. A dunder because pydantic reserves no ordinary
    # identifier: a field called `action` must stay something we can *reject*,
    # not something that silently shadows the wire name.
    __voqal_action__: ClassVar[str] = "action"

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    # ── what this protocol adds: control, never payload ──
    on_result: Callable[[Result], Awaitable[None]] | None = Field(default=None, exclude=True)
    timeout_s: float | None = Field(default=30.0, exclude=True)


class Result(BaseModel):
    action_id: int                      # SDK-minted; for logs, not for you to track
    status: Literal["ok", "error", "timeout"]
    data: Any = None                    # whatever the browser sent back
    error: str | None = None
```

An action is then a declaration, and using it is one line:

```python
class ShowResults(Action):
    rows: list[Row]
    highlight: str | None = None


yield ShowResults(rows=rows, on_result=self.on_row_picked)
```

**Why pydantic and not a dataclass.** Four properties the wire needs, every one
of which a dataclass would hand-roll: validation at the call site
(`extra="forbid"` turns a typo into a loud `ValidationError` instead of a field
that silently never reaches the screen); aliases (`Field(alias="from")`, so a
wire key that isn't a Python identifier is expressible); JSON-mode dumping
(`datetime` / `Enum` / `Decimal` / `UUID` become JSON scalars *here*, where the
failure is a clear Python error, rather than at the transport where it is an
opaque serialization crash); and — the one that decides it — **JSON Schema
export**, which is what makes the TypeScript half generatable instead of
hand-copied. See below.

**The wire name is derived, with a pin.** `OpenItinerary` → `open_itinerary`, and
`class OpenItinerary(Action, name="open_itinerary")` pins it when you don't want
the class name inside your browser contract. Derivation carries a real risk —
renaming the class renames the action, and a browser keyed on the old string
stops updating the screen with nothing red anywhere — but it is the convention
two demos and the docs already ship, and generating the TypeScript mirror (below)
dissolves the risk rather than documenting around it: a rename regenerates both
halves, and a handler map that no longer matches is a frontend **compile** error.

**`exclude=True` is what keeps control out of the payload.** Verified: with the
two fields declared as above, `ShowResults(rows=["a"], on_result=cb).to_payload()`
is `{"rows": ["a"], "highlight": None}` — the callback lives on the object, never
on the wire — and the serialization schema drops them too, so the generated
TypeScript never sees them either.

**Two guards, both at class-definition time.** The first exists today:
`RESERVED_ACTION_KEYS = {"type", "action", "action_id"}` — an action's fields are
spread onto the top level of the envelope, so a field serializing to one of those
would overwrite it, and `__pydantic_init_subclass__` raises instead of letting it
reach the wire. The second is new and this protocol needs it: **a subclass that
redeclares `on_result` or `timeout_s` silently un-excludes it.** Verified —
`class Shadow(Action): on_result: str` puts `on_result` straight onto the wire.
Same guard, one more reserved set.

**What goes on the wire** is `model_dump(by_alias=True, mode="json")` of the
subclass's own fields, spread onto the envelope that already exists:

```
{"type": "ui_command", "action": "show_results", "action_id": 7, **payload}
```

This is an ergonomics change in the SDK, not a wire change. Every declared field
is emitted, **including `None`, which goes as JSON `null`** — no `exclude_none`.
That is deliberate, and the next section rests on it: the wire shape of an action
must be a function of the *class*, not of which fields happened to be set on one
instance, because a stable shape is what lets the browser declare one total
interface instead of marking every field optional.

#### Why not `Action[T]`

Two readings of the generic, rejected for different reasons.

**`T` as the payload** — `Action[ShowResultsArgs]`, args as a nested model — loses
to fields-are-the-payload on shape. The wire spreads args onto the envelope's top
level, so a nested payload model either nests the wire (a change) or is flattened
straight back out (a generic that buys nothing). The subclass's own fields already
*are* the typed payload.

**`R` as the result type** — `Action[PickedRow]`, so `on_result` receives a
`Result[PickedRow]` — is the reading that would mean something, and it is
technically available. A plain `TypeVar` fails the repo's gate: verified, a bare
`Action` in an annotation is `reportMissingTypeArgument` **and**
`reportUnknownParameterType` under strict pyright, so every fire-and-forget action
would have to be spelled `Action[None]`. But `typing_extensions.TypeVar("R",
default=None)` — PEP 696, usable on 3.12 — clears it, and bare `Action`
type-checks clean.

It is still the wrong trade *today*, because it types a claim rather than checking
one. The browser is a separately-deployed program — `useUiCommand` already treats
version skew as normal, routing an unknown action to `console.debug` rather than
failing. `Result[PickedRow]` asserts a shape that nothing validates, which is the
silent-failure pattern this repo keeps designing against. If we want the result
typed, the load-bearing version is a declared model the SDK **validates** the echo
through:

```python
class ShowResults(Action):
    result_model: ClassVar[type[BaseModel] | None] = PickedRow
```

— checked at runtime, generates its own TypeScript, and needs no generic.
Deferred rather than adopted, because no shipping action reads `result.data`
structurally yet. Worth recording that the generic stays available and
non-breaking if we later want the static half as well.

#### Two ways to send it, one object

```python
# turn channel — ordered against the speech around it
yield ShowResults(rows=rows, on_result=self.on_row_picked)

# session channel — from a callback, from anywhere, no generator frame needed
session.dispatch(ShowToast(text="Saved"))
```

The callback comes from the base class, so it is not a feature of one channel
that the other has to reimplement — it is a field on the object, and both
channels take the object.

**Both forms hit the wire in the same order they run.** By the time your code
resumes past a `yield SpeechEnd()`, that speech is already sent — only the
*audio* lags. So a `session.dispatch()` called mid-turn cannot jump ahead of
speech you already yielded. The yielded form exists because it makes the
ordering visible in the code, not because it behaves differently.

#### Callbacks cannot speak

`on_result` returns `None`. It runs on the session, not inside the turn that sent
the action — the turn may be long over. It holds no floor, for the same reason
`on_app_message` doesn't: nothing about a browser echo means the human stopped
talking. A callback that wants to change the screen calls `session.dispatch(...)`;
a callback that wants the agent to *say* something stores it and lets the next
turn pick it up.

#### Waiting for an answer

Sometimes the turn genuinely must block — "read me the code I just texted you",
"approve this and I'll continue." `session.dispatch()` returns a handle whose
result is awaitable:

```python
async def on_user_message(self, session, msg):
    yield SpeechStart()
    yield Chunk("I've sent a code to your phone. Read it back when you have it.")
    yield SpeechEnd()

    result = await session.dispatch(RequestOtp(timeout_s=60)).result

    yield SpeechStart()
    yield Chunk("Got it, you're verified." if result.status == "ok"
                else "I didn't get that — let's try another way.")
    yield SpeechEnd()
```

Two rules make this safe, and they are the reason it is worth having at all:

1. **Say something before you block.** You are holding the floor. An `await` with
   no preceding speech is dead air, and the SDK cannot tell the difference.
2. **The wait is cancelled by barge-in.** If the caller talks over you while you
   are awaiting, the turn is cancelled at the `await` — ordinary `asyncio`
   cancellation, not the async-generator corner in the open list. The pending
   result is discarded with the turn.

There is no awaitable form on the yielded channel. Getting a value back out of a
`yield` means `asend`, which makes the generator protocol bidirectional for one
feature — and it is unnecessary, because `session.dispatch()` is callable from
inside the generator body, which is exactly where you are when you want to wait.

#### `timeout_s` exists so the registry cannot grow

A browser is under no obligation to answer, and a long call could otherwise
accumulate pending handlers for its whole duration. Every action expires; the
expiry fires the callback with `status="timeout"`, so there is **one** code path
for "the answer came" and "it didn't." `timeout_s=None` opts out, and those
handlers are reclaimed at session teardown.

> The default of 30 s is a starting number, not a finding. It should be long
> enough for a human to read a dialog and short enough that a forgotten action
> does not outlive the exchange it belonged to.

#### The browser declares the same set — and should not hand-write it

Typed actions are half a contract while the far side still switches on strings.
The other half already exists, but it is copied by hand: `useUiCommand<T>` in
`@voqalize/client-react` checks a handler map against a command-shape map `T`,
and `demos/orderdesk/frontend/src/uiCommands.ts` *is* that map — written out by
hand, under a header that says `brain.py` is the source of truth and "change one
side and the other must move with it."

Pydantic is what makes that generated. `model_json_schema(mode="serialization")`
over every `Action` subclass in a module, walked into TypeScript, reproduces
OrderDesk's hand-written map **field for field** — all six commands, plus the
three nested interfaces (`SkuWire`, `LineItemView`, `FamilyWire`) that today live
hand-written in `types.ts`, down to
`status: "resolving" | "multi_family" | "multi_variant" | "matched" | "not_found"`
recovered from the Python `Literal`. A ~25-line prototype reached exact parity.

Two sharp edges found doing it, both belonging in whatever ships:

- **Serialization mode, not the default.** `model_json_schema()` defaults to
  `mode="validation"` and **raises** `PydanticInvalidForJsonSchema` on a
  `Callable` field — which `on_result` is. Serialization mode is the right
  direction anyway (the wire is what we are describing) and it drops the excluded
  control fields for free.
- **`required` is keyed off defaults, not off emission.** A field with a default
  is absent from `required` in *both* modes, so a naive generator writes
  `note?: string | null` for a field the wire always carries. The rule is: every
  property in the serialization schema is required — true precisely because there
  is no `exclude_none`.

A follow-on rather than part of the protocol, but it is where most of the value
lands, and it settles the wire-name question above: the name and the field set
stop being agreed in prose and become one generated file.

## 6. The two channels

The brain emits through two doors. They are not interchangeable, and the
difference is the floor.

| | **Turn channel** | **Session channel** |
|---|---|---|
| How | `yield Speech… / an Action` | `session.dispatch(…)` |
| Available from | the three trigger callbacks | anywhere, any time |
| Ordered | yes, within the turn | no |
| Can produce speech | yes (user message / idle only) | **never** |
| Lifetime | the callback frame | the session |

The asymmetry is structural, not stylistic: yielding requires a generator frame,
and code that isn't in one (a callback, background work) has nothing to yield
into. What makes it safe is that **the session channel is floor-free by
construction** — it carries actions only, and actions carry no audio.

The runtime already agrees: a barge-in drain discards stale speech but
deliberately exempts actions, so a render racing an interruption isn't silently
lost.

**The consequence to internalize:** work that finishes after a turn can *render*
its result but cannot *say* it. The agent mentions it on the next turn. Screen
updates are ambient; speech requires the floor.

### Hanging up

`yield EndSession(reason=...)` is an event like any other, and that is the whole
point: it takes its place in the queue behind the goodbye you just yielded, so
"say it, *then* hang up" is expressed by writing it in that order rather than by
relying on how a lane drains.

```python
yield SpeechStart()
yield Chunk("All set — thanks for calling!")
yield SpeechEnd()
yield EndSession(reason="task_complete")
```

`session.end()` remains, for the session channel where there is nothing to yield
into. It is **immediate** — it does not wait for queued audio — which is what you
want for an abort and not what you want for a goodbye.

---

## 7. The contract, stated as obligations

### What Voice guarantees you

1. At most one speech-capable callback is in flight at a time. You never race yourself for the floor.
2. Every speech unit you open receives exactly one `Finalize` — if it produced audio.
3. An application message never interrupts a turn in progress.
4. On barge-in your generator is closed, not abandoned. Your `finally` blocks run.
5. For the duration of a speaking callback, the floor is yours.

### What you guarantee Voice

1. **Balanced brackets.** Every `SpeechStart` is followed by a `SpeechEnd`. A `Chunk` outside a unit is a protocol error.
2. **You don't block.** Stream, and return when you're done. A hung generator is dead air.
3. **You don't speak outside a speaking callback.** There is no door for it; don't look for one.
4. **`greet` is fast.** It is on the critical path of every session.

### What neither side promises

- No ordering between a session-channel action and turn events.
- No guarantee a `Finalize` arrives before the next turn opens.
- No guarantee the browser *answers* an action. Your `on_result` always fires — with `status="timeout"` if it didn't.

---

## 8. What the brain does *not* own

### Conversation history

Core `Brain` does not maintain a transcript. It reports facts —
`on_user_message` gives you the utterance, `on_finalize` gives you what was
heard — and the brain decides what to keep.

This is a deliberate reversal. The reason it is safe to reverse is that the
heard-truth guarantee moves *up* a layer rather than disappearing:
`FrameworkBrain` (the provider-agnostic base every framework adapter extends)
accumulates history with the invariant intact, and buffers generated chunks so
its subclasses can pair generated against heard. A brain that wraps an existing
agent opts out and keeps its own.

The rule that must survive wherever history lives:

> **History records what was heard, never what was generated.**

A barged-in reply generated three sentences and delivered one. Record the three
and the model will reference things it never finished saying — a failure that is
silent, cumulative, and invisible in every metric.

### Resume

There is no resume API. A logical conversation spanning several sockets is:
read your own identifier from `session.init`, load your own history in
`on_session_start`, keep it. The SDK persists nothing and interprets no
identifier — the transcript never leaves the customer's environment.

Removing the abstraction makes the hard case *easier*, which is usually the sign
the abstraction was wrong.

### Ids that are not yours

- **`inference_id`** is minted brain-side, unique within the session, and
  **opaque to Voice.** Voice's only job is to carry it out and bring it back on
  the `Finalize`. It is a correlation token; nothing compares or orders it.
- **The floor clock** (`interaction_id` on today's wire) is Voice-minted,
  monotonic, and exists for exactly one purpose: letting Voice tell fresh frames
  from stale ones after an interruption. It is SDK plumbing. **A brain author
  should never see it or name it.**

Two ids, two owners, two jobs. The two-key model is already the documented design
(`platform/docs/voice-protocol.md`), so nothing here is new. Two things change:

- **`inference_id` becomes session-unique instead of restarting at 1 per
  interaction.** That is the only reason TTS pins a composite
  `context_id = "{interaction_id}.{inference_id}"` — with a unique id the
  composite collapses to the id, and the correlation stops depending on the
  floor clock at all.
- **The floor clock stops being developer-facing.** It reaches the brain author
  today as `Interaction.id`, which reads like a durable identity for a turn and
  is not one — the greeting doesn't get a real one, every browser message gets
  one whether or not it's a turn, and the completion frame that would close one
  has no consumer in the runtime. Keeping it internal removes all three cracks
  without changing the wire.

---

## 9. A complete brain

```python
class OrderBrain(Brain):
    voice = "omnivoice/gauri"
    language = "en"

    def __init__(self, catalog):
        self.catalog = catalog
        self.screen: dict | None = None
        self.history: list[tuple[str, str]] = []

    async def on_session_start(self, session):
        if account := session.init.get("account_id"):
            self.history = await load_history(account)

    async def greet(self, session):
        return "Hi! What are we ordering today?"

    async def on_app_message(self, session, msg):
        if msg.type == "state_sync":
            self.screen = msg.data
        elif msg.type == "catalog_search":
            rows = self.catalog.search(msg.data["query"])
            yield ShowSearchResults(rows=rows)

    async def on_user_message(self, session, msg):
        self.history.append(("user", msg.text))

        yield SpeechStart()
        yield Chunk("One moment…")
        yield SpeechEnd()

        rows = await self.catalog.search_for(msg.text, screen=self.screen)
        yield ShowResults(rows=rows, on_result=self.on_row_picked)

        yield SpeechStart()
        async for token in self.llm.stream(self.history, rows):
            yield Chunk(token)
        yield SpeechEnd()

    async def on_row_picked(self, result):
        if result.status == "ok":
            self.selected = result.data["sku"]        # note it; the next turn can mention it

    async def on_finalize(self, session, fin):
        if fin.heard:
            self.history.append(("assistant", fin.heard))
```

Everything voice-specific is in the shape of the code, not in objects the
developer has to learn: the floor is the callback, speech is a bracket, the
screen is an action, and truth arrives afterwards.

---

## 10. Open

Ordered by how much they block.

1. **The scope of `on_error`.** Today's `ErrorFrame` means one thing: the runtime
   dropped data under congestion. But an `on_result` callback runs outside the
   turn that created it, so "your callback raised" now needs a door too, and it
   is not the same event as "the wire is congested." One widened callback or two
   separate ones? This is the last thing action callbacks depend on.
2. **Naming.** `on_app_message` — agreed in principle (name by *actor*, not by
   *transport*), exact word open. Likewise the browser SDK's two send methods
   (`sendUserMessage` / `sendAppMessage`), which are what makes the split
   routable without the runtime interpreting payloads.
3. **Generated greetings.** `greet -> str` is static by contract. Several
   existing brains stream a generated opener behind a static lead-in. They need
   either an escape hatch or an explicit decision to go static.
4. **Async-generator finalization.** The one implementation risk, and it is
   narrower than it first looked — it splits by where the generator is suspended
   when the caller barges in:
   - **At an `await`** (an LLM call, an action result): ordinary `asyncio`
     cancellation. Well-defined, and the reason the blocking-action pattern in
     §5.5 is safe.
   - **At a `yield`**: `aclose()` throws `GeneratorExit` at the suspension
     point, and a brain with `await` inside a `finally` around an LLM stream
     meets the sharpest corner of the async-generator protocol.
   Only the second case is uncertain. Prototype it against a real barge-in
   before committing to the shape.
5. **Where the action codegen lives.** Blocks nothing — the protocol is complete
   without it — but it is the piece that turns typed actions into a checked
   cross-language contract. Open: a `voqalize` CLI subcommand vs. a script each
   frontend runs; generated file committed or built; and whether the SDK's own
   `Speech`/`Result` envelope types are generated alongside the app's actions.

### Deferred

**Background work — deferred until the right abstraction exists.** The shape
discussed (a long-lived coroutine bound to the session that need not complete,
with Session holding the references and cancelling at teardown) is a plausible
sketch, not a design, and the questions it opens are the ones that decide whether
it is the right primitive at all: who spawns it, what happens when it raises,
whether it is bounded, and what — if anything — it may promise about ordering.

Note that the protocol does not *need* it. `on_result` covers deferred work that
is a **response to something the brain sent**, and it is bounded by construction:
one action, at most one callback, expired on a timer. Unbounded self-started work
is the open case, and nothing above depends on it.

### Settled since the first draft

- **`greet(session)`**, not `greet(init)` — consistent with every other callback;
  `session.init` is the same payload.
- **`yield EndSession(...)`** is the way a brain hangs up on the turn channel, so
  the goodbye is spoken first by ordering rather than by lane behaviour.
  `session.end()` survives for the session channel and is immediate.
- **Actions are typed classes**, not a payload bag: `Action` is a base you
  subclass, and the subclass's fields *are* the payload. `on_result` is inherited
  from the base, so it works identically on both channels. §5.5.
- **The base is pydantic, and already shipping.** Not a dataclass — validation,
  aliases, JSON-mode dumping and JSON Schema export are all load-bearing, and
  `voqalize.sdk.Action` already exists with the first three. The protocol's
  contribution is the two `exclude=True` control fields and the guard that keeps
  a subclass from redeclaring them. §5.5.
- **No `Action[T]`.** Payload-as-`T` loses to fields-are-the-payload;
  result-as-`R` types a claim about a separately-deployed browser that nothing
  validates. A runtime-validated `result_model` is the version worth having, and
  it is deferred until an action actually reads `result.data` structurally. §5.5.
- **`Action → Result`**, not `Action → Outcome`. The callback is `on_result`; the
  payload the browser sends back is `result.data`.
- **No correlation tags.** Optional opaque tags echoed back on `Finalize` /
  `Result` were considered and dropped — `inference_id` and `on_result` already
  close both loops, and a second correlation mechanism earns nothing.
