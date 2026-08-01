# Changelog

All notable changes to `voqalize-agent-sdk`. This project is pre-1.0 and still
alpha: the package API can break on a minor version, the **wire** does not.

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
