# Changelog

All notable changes to `voqalize-agent-sdk`. This project is pre-1.0 and still
alpha: the package API can break on a minor version, the **wire** does not.

**The numbering restarts at `0.0.1`.** Everything below it — `0.1.0` through the
work that would have been `0.4.0` — was never published: the one host that used
the SDK installed it from a path in a sibling checkout. `0.0.1` is the first
version anyone can `pip install`, and starting the public series at the bottom
says plainly that nothing here is promised yet. Those older entries stay,
because the API they describe is the API `0.0.1` ships.

## 0.0.4 (unreleased)

**Wire version 3, and it is a break.** The envelope carries no fields, barge-in
is a one-way watermark, and the browser plane is RTVI. A brain built against
version 2 refuses a version 3 session outright — a fatal `Error` then `End`,
before it has greeted — and the same in reverse, so neither end ever guesses.

### Changed

- **The envelope is one `oneof body` and nothing else.** The two correlation
  scalars are gone from it; every identifier is a field of the message it
  belongs to — `turn_id` on `SessionStart`/`UserMessage`/`UserIdle`/`SpeechStart`,
  `speech_id` on the speech frames and `Finalize`, `request_id` on the
  request/response pair. `WireSerializer.serialize(frame)` takes the frame and
  nothing else; `deserialize_message(payload)` returns one.
- **`epoch` → `turn_id`, and `SessionStart` is turn 1.** Only `UserMessage` and
  `UserIdle` mint further turns, so the first thing the caller says is turn 2.
  The greeting rides the turn `SessionStart` itself minted; there is no turn `0`.
- **Interruption is a watermark, not a reply.** `Interruption` carries
  `through_turn` and travels voice→brain only. Record
  `max(watermark, through_turn)` and stop generating for anything at or below it;
  send nothing back. The echo, the drain barrier and its timeout are gone — a
  repeat is harmless, a missed one is covered by the next, and a newer turn
  simply outranks the watermark.
- **The browser plane is RTVI.** `BrowserMessage`/`BrowserCommand` →
  one `RTVIFrame(type, data, id, turn_id)` in both directions, carrying a pipecat
  RTVI message minus its constant label. `on_browser_message` → `on_rtvi`;
  `session.dispatch(action)` is now sugar over `session.send_rtvi(...)`. `type`
  is a closed whitelist of ten values and which side may originate each is part
  of the type: a brain cannot forge `bot-*` or `llm-*`.
- **The brain leg is dialled at `{brain_url}?session_id={session_id}`.** Your
  path is used verbatim, so a brain is one ordinary WebSocket route rather than a
  wildcard path segment carved out for us.
- **`Error` carries an `ErrorCode`** — `PROTOCOL`, `WIRE_VERSION`, `REJECTED`,
  `OVERLOAD`, `INTERNAL` — alongside the message and `fatal` flag.
- **The inbound socket is the session and is not reconnected.** The runtime
  retries the *first* connect under a short deadline; once you have answered, any
  close ends the call.
- **Conformance:** `InferenceObs` → `SpeechObs`, `EpochObs` → `TurnObs`,
  `.inferences` → `.units`, `.epoch` → `.turn_id`; `send_browser_message` →
  `send_rtvi` / `send_client_message`; scenario ids `two_inferences_one_turn` →
  `two_units_one_turn` and `browser_message_*` → `app_message_*`.
- **`cryptography` is a declared dependency** rather than one borrowed from
  `pyjwt[crypto]`: `voqalize.conformance` imports it directly to mint the keypair
  a scenario signs with. A package you import is a package you declare.
- **The `examples` extra is now `fastapi` + `uvicorn`.** `openai-agents`,
  `python-dotenv` and `google-genai` left with the examples that used them.
- **`py.typed` moved.** `voqalize` is a namespace package, so the marker at its
  root was never read; it now sits in `voqalize/conformance/`, beside the one
  `voqalize/sdk/` already had. Both packages are typed to consumers, which is what
  the root marker was meant to do and did not.

### Removed

- **`voqalize.google_adk` is gone**, along with `voqalize._framework` and the
  `[adk]` extra. The adapter never learned version 3 — turns, the RTVI plane and
  the heard-truth write-back all still assumed version 2 — and its suite had been
  switched off at collection since that break, so what shipped was 2,100 lines
  that nothing ran. A test file that is not collected is not a skip: the suite
  reported green the whole time.

  It comes back as a port once the `Brain` surface has settled. The shape it ports
  *to* already exists: `tests/contract/` states the nine clauses once and runs them
  against every engine, so adding an integration is writing an `Engine` and reading
  the failures — not another twenty-two files of its own.
- **`examples/travel` and `examples/travel_adk`.** Both were written against the
  retired `on_interaction` surface. `echo`, `reference` and `fastapi_inbound` are
  on the current one and stay.

## 0.0.3

**No wire change.** The ack below is sent at a different *moment*, not in a
different shape, and a runtime running the old timing is unaffected.

### Fixed

- **A slow callback no longer holds up the caller's next sentence.** The SDK
  acknowledged each inbound frame *after* your handler returned, so the ack
  doubled as "handled". The voice runtime blocks its transmit lane until that
  ack arrives — that is what keeps frames in order — which meant any work your
  callback did was welded onto the runtime's critical path. A brain writing a
  transcript to a database from `on_inference_finalized` charged the candidate's
  *next* question for the previous one's write.

  The ack is now sent when the frame is taken off the inbound queue, before your
  handler runs. It says **"committed to the ordered lane"**, not "handled" —
  which is all the runtime ever needed it to mean, since ordering is settled the
  moment the frame is queued. Measured on a production call, the runtime's own
  share of a turn is now 2–4 ms; it had been carrying seconds that were never
  its own.

  Ordering is unchanged: frames are still handled one at a time, in arrival
  order, on a single lane. Nothing becomes concurrent. But **the lane is still
  yours to keep clear** — a handler that blocks still delays every frame behind
  it, it just no longer stalls the runtime as well. Do slow I/O in a background
  task and drain it at session end.

### Added

- **`AdkBrain` now says what a default thinking budget costs you.** A Gemini
  agent built without an explicit `thinking_config` reasons before its first
  spoken token, and the SDK drops thought parts rather than speaking them — so
  on a voice call that time is silence the caller sits through, with nothing to
  show for it. Building such an agent logs the measurement and the one-line fix.

  Measured against a real screening prompt, median time-to-first-token:
  default **2115 ms**, `thinking_level="low"` **1480 ms**, `thinking_budget=0`
  **1119 ms**.

  It is a notice, not a change: nothing is set on your behalf. An agent that
  passes its own `thinking_config` has made the decision deliberately and stays
  quiet, as does a non-Gemini model or a model instance you constructed
  yourself.

## 0.0.2

**No wire change.**

### Fixed

- **A rejected API key now fails immediately, and says so.** Connecting a
  `CortexAgent` with a key the relay refuses used to retry forever behind
  exponential backoff, and the only evidence was
  `wire: connect attempt 14 failed (InvalidStatus(...)); retrying` — the number
  `401` appeared nowhere, and the process looked alive. The relay rejects a bad
  credential at the *HTTP upgrade*, so there is no websocket close code to read;
  the transport was looking for one, not finding it, and concluding "transient".

  `serve(...)` / `CortexAgent.run()` now raise **`AuthRejected`** on the first
  `401`/`403`, with a message that names the status and what to check. It
  subclasses `PermanentClose`, so code that already catches that keeps working.
  Failures that genuinely *are* transient — the relay down, DNS not yet
  resolving, a network blip — still retry exactly as before.

## 0.0.1

First release published to PyPI: `pip install voqalize-agent-sdk`.

**No wire change.** Every change below is package-API or packaging only; the
frames a brain emits are byte-identical to what the previous release emitted.

### Added

- **Session-scoped logging — your brain's logs join the rest of the call.** Every
  session now runs inside a context that tags each log line with `session_id`,
  and with `tenant_id`/`agent_id` when the connection's verified token carries
  them. A bare `from loguru import logger` anywhere in your brain — including in
  tasks it spawns — picks that up with nothing threaded through your signatures.

  The SDK **only adds fields**; it never touches your logging setup. If you
  already configure loguru, add `{extra}` to your format. If you don't, call
  `voqalize.sdk.configure_logging()` from your entrypoint — `json_logs=True`
  writes one JSON object per line with the identity fields at top level, which is
  the shape a log shipper indexes on.

  `session_context(...)` is exported too, for tagging work you do outside a
  session (a warm-up, a background reconciler).

- **`voqalize.sdk.Action` — typed UI commands.** Declare a command as a pydantic
  model that carries its own wire name and pass an instance where you used to pass
  `(name, args)`:

  ```python
  class AddToCart(Action):          # wire name: "add_to_cart"
      sku: str
      qty: int = 1

  interaction.action(AddToCart(sku="oat-milk", qty=2))
  ```

  The name is `snake_case`d from the class name unless pinned
  (`class AddToCart(Action, name="add_to_cart")`). Serialization is
  `model_dump(by_alias=True, mode="json")`: aliases apply (a `from_` field goes out
  as `from`), `date`/`Enum`/`Decimal`/`UUID` become JSON scalars, nested models and
  lists compose, unknown kwargs are rejected, and **every declared field is emitted
  including `None`** — no `exclude_none`, so the wire shape is a function of the
  class and the browser can declare one total TypeScript interface. A field that
  would serialize to `type`, `action` or `action_id` raises at class definition.
  Accepted by `session.action`, `interaction.action` and `voice().action`, with
  `callback=` unchanged. **The `(name, args)` dict form is unchanged and remains
  first-class** — convert one command at a time. `pydantic` is now a core
  dependency (it was already a transitive one for ADK users).
- **Tools may return pydantic models.** The ADK adapter's new `after_tool_callback`
  dumps a returned model — and models nested in a returned dict/list — with the
  same `by_alias`/JSON-mode rules before the result reaches the model, so the field
  names a tool declares are the field names the model reads, instead of ADK's
  `str()` of a `BaseModel`. A non-dict dump is wrapped as `{"result": ...}`,
  matching ADK's own handling; a result containing no model passes through
  untouched. This is the mirror of the 0.3.0 tool-*argument* coercion.
- **`useUiCommand`** in `@voqalize/client-react` is the browser half — see
  [the React client docs](https://docs.voqalize.com/client/react/).

### Changed

- **`protobuf>=5.29.3,<7`** (was `>=6.30,<7`) — **the SDK no longer drags a host
  application onto protobuf 6.** The old floor came from the committed wire stubs,
  which were generated with protoc v32 and therefore assert a 6.32 runtime at
  import. A protobuf runtime accepts gencode from its own major or an older one,
  so the stubs are now generated with protoc **v29.3**: they run unchanged on
  protobuf 5.29+ *and* on 6.x, and an application already resolved on 5.29 keeps
  its resolution when it adds this SDK. The `.proto` contract is untouched and the
  wire bytes are identical — this is a gencode-target change, not a wire change.
  We test against both majors.

  The generator pin lives in `proto/buf.gen.yaml` and now tracks the **oldest**
  runtime we support, not the newest; raise it only together with the floor here.
- **The `adk` extra now requires `google-adk>=2.3,<3`** (was `>=1.33,<2`). The old
  ceiling held installs on the 1.x line, and 1.x caps two things a host
  application is likely to be ahead of: `starlette<1` (lifted in ADK 2.2) and
  `opentelemetry-*<=1.41.1` (lifted in ADK 2.3). Installing `[adk]` next to a
  modern FastAPI or OTel stack therefore walked those backwards, and dragged in
  the 1.x-only `google-cloud-aiplatform` subtree with them. 2.3 is the first
  release that pins neither. The adapter itself is unchanged — the ADK surfaces
  it uses (`Runner`, `InvocationContext`, callbacks, `types`) are identical
  across the two lines, and the drift canaries pass on 2.3.0 and 2.6.2 alike.

## 0.3.0

The ADK adapter grows the seams a real screen-driving agent needed. **No wire
change** — `proto/voqalize/frames/frames.proto` is untouched, so this is a pure
package-API release and any 0.2.0 runtime pairing keeps working.

### Added

- **`AdkBrain.grounding() -> str | None`** — override it to append live context to
  the **fully assembled** system instruction on *every* model call (the root
  agent's and every sub-agent's). Appending after ADK assembles is what makes it
  compose instead of clobber: a plain-string `instruction` keeps ADK's `{state}`
  templating, a client's own `InstructionProvider` still runs, and one
  registration covers the whole agent tree. `None` appends nothing, turn by turn.
  This replaces reaching for an `InstructionProvider` just to re-read state.
- **The `state_sync` browser-snapshot convention.** `on_client_message` now
  handles the `state_sync` message type by default and parks the payload on
  **`self.browser_state`**. It **takes no floor** — a screen change never makes
  the agent talk — and it **replaces** rather than merges (the browser sends a
  complete picture; merging would resurrect rows the user just deleted). Pair it
  with `grounding()`. A subclass that overrides `on_client_message` keeps the
  default by calling `super()`. Convention, not protocol: the wire still carries
  an opaque client message.
- **Tool arguments arrive as the models you annotated.** A parameter typed `Leg`
  or `list[Leg]` (also `Model | None`, `Sequence`/`tuple`/`set` of a model) is
  constructed from the model's raw JSON before the tool runs; every other
  annotation is passed through untouched. `Field(alias=...)` validates **both
  ways** — from the wire's `from` *and* from the schema's `from_` — so a wire key
  that is a Python keyword needs no rename in the body. An argument the model
  shaped wrong comes back to it as a **tool error result** it can retry, not an
  exception that kills the turn. (`voqalize._framework.coerce`, wired at
  `before_tool_callback`.)
- **The sync-tool guard.** A non-`async` tool is rejected when the agent is
  built, with a `ValueError` naming it — ADK dispatches a sync tool on a thread
  pool, where `voice()` is unset and `voice().action(...)` would raise mid-call,
  after the model already spoke. **`allow_sync_tools=True`** opts out for tools
  that never call `voice()`.
- **`AdkBrain.agent`** — the ADK `LlmAgent` this brain drives, for inspection in
  tests.

### Changed

- **The ADK agent is built lazily**, on first need (session start, or the `agent`
  property) and exactly once — never in `__init__`. A subclass can therefore
  assign its per-session state *after* `super().__init__(...)` and still have the
  factory, the instruction and the tools see it. The "build your state before
  `super().__init__`" ordering trap is gone.
- **`ScriptedLlm`** records `captured_system_instructions` (each call's assembled
  system instruction, in call order) alongside `captured_contents`.
- **`call(name, /, ...)` / `reply_and_call(text, name, /, ...)`** take the
  helper's own parameters **positional-only**, so every keyword is unambiguously
  a tool argument — a tool taking `name=` or `text=` no longer collides — plus an
  explicit `args={...}` form for an argument literally named `args`. Mixing the
  two forms raises `TypeError`.

## 0.2.0

Breaking changes to the package API. The wire protocol is fully backward
compatible — every change to `proto/voqalize/frames/frames.proto` in this release
is an addition, so a 0.1.0 brain keeps working against the current runtime and a
0.2.0 brain keeps working against an older one (it just never sees the new
frames).

### Breaking (package API)

- **`on_app_event(session, event)` → `on_client_message(session, message)`.**
  `event.name` → `message.type`, `event.data` → `message.data`. The `AppEvent`
  type is gone; `ClientMessage` replaces it and adds `.id` (the browser-supplied
  message id) and `.interaction_id` (minted by Voice for this message).
  Replying is now explicit: touch `message.interaction` to take the floor and
  respond on the pre-minted id, or read the data and return to ingest it
  silently. Messages from an older runtime arrive unstamped
  (`interaction_id == 0`) and degrade to an agent-initiated turn.
- **`inference()` → `say()`.** `session.inference()` → `session.say()` and
  `interaction.inference()` → `interaction.say()`. The bracket is otherwise
  unchanged (`async with … as speech: await speech.speak(text)`), still 1:1 with
  one model call.

### Added

- **`on_user_idle(interaction)`** — the user went silent past the idle timeout
  and the brain holds the floor to re-engage. `interaction.idle` is an
  `IdleInfo(level, idle_ms)`; `level` escalates while the silence persists and
  resets on user speech. Default is a no-op, so the silence just rides.
- **`session.configure_idle(timeout_ms=…)`** — set the silence window mid-call;
  `0` disables idle detection entirely.
- **`InteractionSource`** (`USER` / `IDLE` / `CLIENT_MESSAGE`), readable as
  `interaction.source`.
- **`voqalize.google_adk`** — hand the SDK a native Google ADK agent
  (`AdkBrain` / `adk_brain(...)`) and let it drive the run loop, including the
  heard-truth corrector that reconciles what the user actually heard back into
  ADK's session history. Optional extra: `pip install voqalize-agent-sdk[adk]`.
- **`voqalize.conformance`** — a wire-level driver plus a scenario catalog and
  MUST checks that any brain can be run against
  (`python -m voqalize.conformance`), so protocol compatibility is testable
  without the voice runtime.
- **`voqalize._framework`** — the internal framework-brain machinery the ADK
  adapter is built on (heard-truth readers, greeting resolution, the no-dead-air
  turn runner). Private; not part of the public API.

### Wire (all additive)

- `VqlUserIdle` (`Envelope` body 12) — `interaction_id`, `level`, `idle_ms`.
- `IdleUpdateSettings` (`Envelope` body 38) — JSON idle policy.
- `RTVIClientMessage.interaction_id` (field 4) — the Voice-minted stamp; `0` or
  absent means an older, unstamped sender.

### Migration

```diff
-async with session.inference() as inf:
-    await inf.speak("Hi!")
+async with session.say() as speech:
+    await speech.speak("Hi!")

-async def on_app_event(self, session, event) -> None:
-    if event.name == "state_sync":
-        self.screen = event.data
+async def on_client_message(self, session, message) -> None:
+    if message.type == "state_sync":
+        self.screen = message.data          # silent: no floor taken
+    elif message.type == "photo_upload":
+        async with message.interaction.say() as speech:
+            await speech.speak("Let me look at that.")
```

## 0.1.0

Initial release: the pipecat-free `Brain` surface, the inbound (direct) server
and the Cortex agent, the `Vql*` wire vocabulary, and the framework-owned
heard-text conversation record.
