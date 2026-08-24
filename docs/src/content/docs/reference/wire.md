---
title: The wire
description: One WebSocket per session between Voqalize and your brain — the framing, both planes, every message, and what each one obliges the other to do.
---

Voqalize runs the call. Your brain decides what it says and what it shows. Between
them is one WebSocket per session carrying protobuf envelopes in both
directions, and this page is that contract in full.

The schema of record is
[`proto/voqalize/frames/frames.proto`](https://github.com/voqalize/voqalize/tree/main/proto/voqalize/frames/frames.proto).
The SDKs mirror it exactly, so most brains never see a byte of this — but
everything the SDK can do, it does by putting one of these messages on the wire,
and nothing else is possible.

## Why it is shaped this way

A text agent is a function: request in, response out. It may take as long as it
likes, its output is atomic, and nothing happens between the call and the return.
A voice agent breaks all three, and every rule below is a consequence of exactly
one of these.

| Property of voice | What the wire does about it |
|---|---|
| Only one party can hold the air, and the human decides when they take it. | The brain never initiates. It is handed the floor by a stimulus and answers. |
| Output is consumed in real time and can be cut mid-word. | Speech is bracketed into units, and `Finalize` reports back what was actually heard. |
| Silence reads as failure. | The opening line is a plain string, sent before anything else. Nothing waits on a model there. |
| Output is a stream, not a value. | Speech arrives as chunks inside an open unit, not as one finished message. |

## Two planes on one socket

**The voice plane is ours**: turns, speech units, what the caller actually heard,
and the control leg. Voqalize mints the turn because Voqalize decides when a turn
commits, and speech names the turn it answers.

**The RTVI plane is a tunnel.** An `RTVIFrame` is one pipecat RTVI message —
`{id, label: "rtvi-ai", type, data}` minus the constant label — forwarded
verbatim in both directions between the app and the brain. Voqalize moves the
whitelisted types and interprets nothing else about them.

The two planes share the socket and nothing else. A message on the RTVI plane
never mints a turn, never takes the floor, and never changes what the caller
hears.

## The shape of a session

Voqalize dials your brain, one socket per call, and speaks first: the session's
opening envelope is `SessionStart`, and nothing crosses in the other direction
until it has arrived.

**Voqalize owns the floor.** It decides when the brain may speak by minting a turn
— a `SessionStart`, a `UserMessage` or a `UserIdle` — and the brain answers with
speech that names that turn. There is no message a brain can send to ask for the
floor, and none that interrupts the human. That absence is what makes a call
predictable.

Everything the brain sends that is *not* speech is floor-free: an `RTVIFrame` to
redraw the screen, a `Request` to change how the call behaves, an `End` to hang
up. Those need no turn and are legal at any moment.

If your brain reaches Voqalize through the [Cortex relay](/docs/deploy/cortex),
Cortex relays these bytes without reading them. The two ends of the wire are
Voqalize and the brain; nothing in between interprets the schema.

## Framing

Binary WebSocket messages only — a text message is an error.

| Leg | Layout |
|---|---|
| Your inbound server, at `{brain_url}?session_id={session_id}` | `[Envelope]` |
| The Cortex relay, at `/agent` | `[16-byte session_id][Envelope]` |

One message carries one envelope and nothing around it. Nothing frames it,
lengths it, or tags it: the WebSocket already delimits messages, and the
envelope already says what it is.

The 16-byte prefix on the relay leg is how one socket carries many sessions.
Cortex adds it inbound and strips it outbound, and it is the only difference
between the two legs — the same brain code serves both.

## The envelope

The envelope is one `oneof body` and nothing else.

```proto
message Envelope {
  oneof body { SessionStart session_start = 1; /* … */ }
}
```

Every identifier is a field of the message it belongs to: `turn_id` on the
frames that mint or answer a turn, `speech_id` on the frames of one speech unit,
`request_id` on the request/response pair. A reader that has parsed the body has
everything, and there is no second place to look.

## Turns

**`turn_id` is Voqalize-minted and session-monotonic.** `SessionStart` *is* turn
1, and after it exactly two messages mint a turn: `UserMessage` and `UserIdle`.
So the first thing the caller says is turn 2.

A turn is a permission to speak. The brain names it on every `SpeechStart`, and
that is what lets Voqalize tell speech that answers the current stimulus from
speech still arriving for one the caller has already talked over.

Nothing else mints a turn. An `RTVIFrame` from the app does not — the app tapping
a button is not the app taking the floor.

## Speech units

**`speech_id` is brain-minted and names one unit of speech.** `SpeechStart`
opens it and binds it to a turn; each `SpeechChunk` carries it; `SpeechEnd`
closes it; the `Finalize` that reports what was heard names it back. Voqalize never
mints, orders or compares one — it quotes it back exactly as it arrived, so a
brain may number units however it likes.

One turn may hold several units: a filler, a pause while a tool runs, then the
answer. The unit is the granularity of everything downstream, because the unit
is what can be cut mid-word.

## Version

`SessionStart.wire_version` is the version Voqalize speaks. **This is
version 3.**

A brain whose build speaks a different version refuses the session outright: a
fatal `Error`, then `End`, before it has greeted. Voqalize speaks first, so that is
the last moment either end can refuse and the only one where refusing is free —
nothing has been synthesized and the caller has heard nothing.

The comparison is `!=`, not `<`. A lower version is not a subset of a higher
one; the arms it names may mean something else underneath it. Refusing in both
directions is what keeps that from being a guess.

The version gates behaviour, not parsing — protobuf ignores fields it does not
know without help. What a version buys is the ability to refuse rather than
guess.

## Voqalize → brain

| Message | Fields | Meaning |
|---|---|---|
| `SessionStart` | `turn_id`, `session_id`, `init` *(JSON)*, `wire_version` | First envelope of the session, and its first turn. `init` is your opaque init data, whatever the session was minted with, and reaches your brain as `session.init`. Who the agent is arrives on the connection's credential, verified, and never here. |
| `UserMessage` | `turn_id`, `text` | The human finished an utterance. A new turn: the floor is the brain's. |
| `UserIdle` | `turn_id`, `level`, `idle_ms` | The human has been silent past the configured timeout. Also a new turn. `level` counts consecutive escalations with no intervening speech (1 is the first nudge) and resets when they speak; `idle_ms` is the silence elapsed when it fired. |
| `Interruption` | `through_turn` | Everything up to and including `through_turn` is dead — the caller will not hear it. Stop generating for it. |
| `Finalize` | `speech_id`, `heard_text`, `reason` | What the human actually heard of one speech unit. |
| `Response` | `request_id`, `status`, `detail` | The answer to one `Request`. |
| `RTVIFrame` | `type`, `data` *(JSON)*, `id` | The app said something. Delivered verbatim; Voqalize never decides whether it deserves a reply. |
| `End` | — | The call is over. |
| `Cancel` | `reason` | The call is being torn down abruptly. |
| `Error` | `code`, `message`, `fatal` | Something went wrong. `fatal` means the session is ending. |

## Brain → Voqalize

| Message | Fields | Meaning |
|---|---|---|
| `SpeechStart` | `speech_id`, `turn_id` | Open a unit of speech, on the turn it answers. |
| `SpeechChunk` | `speech_id`, `text` | Text to speak, inside an open unit. Stream them as they are produced. |
| `SpeechEnd` | `speech_id` | Close the open unit. |
| `RTVIFrame` | `type`, `data` *(JSON)*, `id`, `turn_id` | Drive the screen. Relayed to the app unread. |
| `Request` | `request_id`, one `op` | Change how the call behaves — today `configure`. Answered by exactly one `Response`. |
| `End` | — | Hang up. |
| `Cancel` | `reason` | Tear down abruptly. |
| `Error` | `code`, `message`, `fatal` | Something went wrong on this side. |

Fields marked *(JSON)* travel as a JSON-encoded string and arrive as a dict in
the SDK. The wire has no `Struct` dependency; opaque payloads stay opaque.

### What the human heard

`Finalize.heard_text` is the **delivered prefix** — what was actually played,
not what was generated. On a barge-in the two differ, and it is bounded by that
unit's own text, never a concatenation across units. `reason` is `COMPLETED` or
`USER_BARGE_IN`.

Feed `heard_text` back into your model's history rather than what you generated.
A model that remembers the sentence it started is a model that references a
sentence the human never heard.

`Finalize` arrives after playout, which can be long after the turn that produced
the unit has returned. **A turn ends when the brain stops emitting, not when the
audio finishes.**

### Barge-in

The human speaks over the bot. Voqalize sends `Interruption(through_turn)`, and
that is a **watermark**: everything up to and including that turn is dead, and
the brain stops generating for it.

The watermark travels one way. Nothing is sent back, nothing is acknowledged,
and Voqalize waits for nothing — it has already stopped the audio. Recording it is
`watermark = max(watermark, through_turn)`, which makes a repeat harmless and a
missed one self-correcting: the next watermark carries a higher number and
covers it.

Nothing lowers a watermark. A turn above it simply outranks it, so the brain
never has to reopen anything — the next `UserMessage` mints a higher turn, and
speech on that turn is live by construction.

## The control leg

The brain asks Voqalize to change how the call behaves, and learns whether the ask
was any good.

```proto
message Request {
  uint64 request_id = 1;
  oneof op { Config configure = 5; }
}
message Response { uint64 request_id = 1; Status status = 2; string detail = 3; }
```

`request_id` is brain-minted and session-monotonic; its whole job is to name the
`Response`. **Exactly one `Response` comes back for every `Request`, on every op,
always** — a brain awaiting one never has to know which ops answer.

`status` is `ACCEPTED` or `REJECTED`, and it reports **whether Voqalize took the
request, not whether the effect is audible yet**. `detail` says why on a
rejection and is empty otherwise, and it is written to be shown.

A request is accepted or rejected **whole**. A rejected `Config` applies none of
its sections, so the call is still coherent afterwards and the previous settings
are still in force.

### `Config` — one message, three sections

```proto
message Config {
  TtsConfig  tts  = 1;
  SttConfig  stt  = 2;
  IdleConfig idle = 3;
}

message TtsConfig  { optional Voice voice = 1; optional Language language = 2; }
message SttConfig  { optional Language language = 1; }
message IdleConfig { optional uint32 timeout_ms = 1; }
```

The same message is the agent record's stored configuration and this op's
payload. That is the point: a record cannot drift from the wire if there is only
one definition of what a configuration is. "Unset" reads differently at each end
— in the record it means *take the platform default*, so a section added later
does not invalidate every stored record; on the wire it means *leave it alone*,
because a `Request` carries a delta and the runtime is already running.

Explicit presence is load-bearing on both. Without it an unset `timeout_ms` is
indistinguishable from `0`, and a delta that never mentioned idle detection would
silently disable it.

**One op, not three.** A language change has to move both legs at once. Three ops
would put a turn boundary — and a possible refusal — between the halves, leaving
the call heard in one language and spoken in another.

The surface is deliberately narrow: voice and language, and nothing else. The
recognizer's thresholds are not settable from here; they keep the runtime's own
defaults. This widens as we learn what is worth naming, and a knob is far easier
to add than to take back.

### When each section lands

| Section | Effective | Why not sooner |
|---|---|---|
| `tts` | the next speech unit | The synthesizer locks the voice for one synthesis context and Voqalize pins one context per unit, so the sentence being spoken finishes in the old voice. |
| `stt` | once the open turn commits | The recognizer carries per-turn decoder state, so the turn being spoken when the change arrives still transcribes as spoken. |
| `idle` | immediately | Voqalize owns that timer; one already running restarts on the new duration. `timeout_ms` is the silence after Voqalize stops speaking before it mints an idle turn, and `0` disables idle detection. |

### Both legs carry a language, and both must be set

`Language` appears on `TtsConfig` and on `SttConfig`, and that is not
duplication. The recognizer serves twenty-three languages; the synthesizer has a
reference clip recorded in ten of them. So the legs genuinely differ — a call
understood in Odia is spoken with the Hindi clip — and one field could not say
so.

Two rules follow, and both are enforced before the request leaves the SDK:

1. **Name a language on one leg and you must name it on the other.** Not that
   they agree — that you stated both. Moving one alone is the silent failure:
   the words stay right and only the voice is wrong, which no transcript, no WER
   number and no automated check will ever show you.
2. **A `tts.language` with no recorded clip is rejected.** It would be served by
   the Hindi clip, and being handed that substitution quietly is how a call ends
   up in a voice nobody chose. Write what you are actually getting:

```proto
stt { language: LANGUAGE_OR }   // listen in Odia
tts { language: LANGUAGE_HI }   // speak with the Hindi clip
```

Changing only the voice touches no language field and is unaffected by either
rule.

### The catalog

`Voice` and `Language` are enumerations, not free strings, so a value we do not
serve cannot be sent at all. Each `Language` value carries its speech-tier code
and whether a clip exists as proto options, which is what makes the SDKs' own
tables derived rather than copied:

```proto
extend google.protobuf.EnumValueOptions {
  optional string iso_code     = 50001;
  optional bool   has_tts_clip = 50002;
}

enum Language {
  LANGUAGE_UNSPECIFIED = 0;
  LANGUAGE_EN = 1 [(iso_code) = "en", (has_tts_clip) = true];  // English
  LANGUAGE_OR = 16 [(iso_code) = "or"];                        // Odia, understood only
  // …
}
```

`iso_code` is not derivable from the name: the catalog mixes ISO 639-1
two-letter codes with 639-3 three-letter ones, because six of these languages
have no two-letter code. See the
[voice & language catalog](/docs/reference/catalog) for the full list.

## The RTVI plane

One message, both directions:

```proto
message RTVIFrame {
  RTVIType        type    = 1;
  string          data    = 2;  // JSON-encoded, opaque
  optional string id      = 3;
  optional uint64 turn_id = 4;
}
```

`data` is the RTVI payload, opaque and bounded by the client's 64 KiB message
limit. `id` is RTVI's own correlation id, quoted back on the message that answers
one. `turn_id` annotates traces, is set only brain→Voqalize, and never reaches the
app.

**`type` is a closed whitelist**, and which side may originate it is part of the
type:

| Direction | Types |
|---|---|
| Brain → Voqalize → app | `server-message`, `server-response`, `error-response`, `ui-command`, `ui-job-group` |
| App → Voqalize → brain | `client-message`, `send-text`, `ui-event`, `ui-snapshot`, `ui-cancel-job-group` |

A type absent from the list does not cross in either direction. `bot-*` and
`llm-*` are the runtime's own assertions about the media and the model, and a
brain must not be able to forge them; a brain that sends one gets a `REJECTED`
`Error` and the frame is dropped.

## Lifecycle

`End` is a graceful close from either side. `Cancel` carries a `reason` and is
the abrupt one; the SDK never sends it, so a brain that emits `Cancel` toward
Voqalize is one written directly against the wire. `Error` carries a `code`, a
message and a `fatal` flag; a fatal error means the session is ending, and a
non-fatal one is a signal the brain may act on.

## Connection and auth

Voqalize dials `{brain_url}?session_id={session_id}`, presenting a short-lived
RS256 JWT as a bare token or as `Authorization: Bearer <jwt>`, verified against
Voqalize's public key. Required claims: `iss="pygato"`, `aud="brain"`,
`sub == session_id`, and `exp`. `agent_id` and `tenant_id` are informational —
the recipient decides from them whether it serves this agent.

The path is yours and is used verbatim; the session rides as a query parameter.
A brain is therefore one ordinary WebSocket route rather than a wildcard path
segment you have to carve out for us.

`aud` is the constant `"brain"` for every brain, whatever kind it is. Routing
lives in the `brain_url`, never in the token. `iss` is the literal string
`pygato` — our internal name for the process that holds the call, here because it
is a value you compare against, not a name you need.

**The socket is the session, and it is not reconnected.** Voqalize retries the
first connect for a few seconds, and once you have answered, any close ends the
call. A close code of **4000** — no agent — is permanent even during that
window. A `401` or `403` at the HTTP handshake is not a close code at all and is
equally terminal: a credential that is missing, revoked, or for another agent
will not start working on attempt twelve.

There is nothing to resume, because there is no state to carry: a second
connection would reach a fresh session with none of the first one's history.

## What the SDK makes of it

The [Python SDK](https://github.com/voqalize/voqalize/tree/main/sdk/python) is
the wire with the bookkeeping removed. A brain implements callbacks and yields
speech; nothing in its surface names a `turn_id`. The one `speech_id` it sees is
on `Finalize`, which reports what a unit was heard as and needs to say which.

```python
class Greeter(Brain):
    async def greet(self, session):
        return "Hi! How can I help?"

    async def on_user_message(self, session, msg):
        yield SpeechStart()
        yield Chunk(f"You said: {msg.text}")
        yield SpeechEnd()
```

| Brain surface | Wire |
|---|---|
| `on_session_start` / `greet` | ← `SessionStart` |
| `on_user_message` | ← `UserMessage` |
| `on_user_idle` | ← `UserIdle` |
| `on_rtvi` | ← `RTVIFrame` |
| `on_finalize` | ← `Finalize` |
| `on_error` | ← `Error` |
| `yield SpeechStart()` / `Chunk` / `SpeechEnd()` | → `SpeechStart` / `SpeechChunk` / `SpeechEnd`, one minted `speech_id` per unit |
| `session.send_rtvi(type, data)` / `session.dispatch(action)` | → `RTVIFrame` |
| `await session.configure(Config(...))` | → `Request`, awaited until its `Response` |
| `session.end()` | → `End` |

`greet` returns a string or `None` — one unit of speech, on the turn
`SessionStart` itself minted. It is a static line: no model call sits on the one
turn that has nothing to retry it.

The speaking callbacks are async generators, and **the generator is the mouth**:
`SpeechStart`, `Chunk` and `SpeechEnd` are the only things they may yield,
because speech is the only output whose position on the audio timeline is its
meaning. Awaiting between yields is how a tool call sits between two things the
brain says. Everything else is a method on the session, callable from anywhere —
including from the callbacks that are not generators at all.

`session.dispatch(action)` is sugar over `send_rtvi`: it serializes an action
onto RTVI's own `ui-command` as `{"command": "show_results", "payload": {…fields}}`,
which a pipecat client reads with `useUICommandHandler`. Nothing comes back — if
the app has an answer it sends an ordinary `client-message`, correlated by
whatever the app puts in it.

`configure` is awaited because Voqalize answers it. Awaiting is how a language
Voqalize has no recognizer for becomes an exception the brain handles, rather than a
call that runs on sounding wrong and reports nothing. The two language rules are
checked before the request leaves the SDK, so a half-stated language change and a
clip-less voice are both a `ConfigError` at the call site rather than a rejection
a turn later.

## Invariants

Both ends rely on these, and a brain that implements the wire directly owes them:

1. **`SessionStart` is first**, and nothing goes the other way before it.
2. **Brackets balance.** Every `SpeechStart` is closed by a `SpeechEnd`; a
   `SpeechChunk` outside an open unit is an error.
3. **One `speech_id` per unit**, on every frame of that unit, brain-minted and
   never reused.
4. **Speech names its turn.** Every `SpeechStart` carries the `turn_id` of the
   stimulus it answers, and only Voqalize mints one.
5. **The interruption watermark is one-way** — never acknowledged, never
   echoed, never lowered.
6. **Exactly one `Response` per `Request`**, matching on `request_id`.
7. **Nothing is emitted outside a turn except floor-free messages** —
   `RTVIFrame`, `Request`, `End`, `Cancel`, `Error`.
8. **`heard_text` is the delivered prefix**, per unit, never a concatenation.

## Changing the wire

The schema is append-only within a version.

- Field numbers are never reused; a retired one is `reserved`.
- `Envelope` arms are never renumbered.
- A message is reserved rather than removed.
- Adding a field or an arm **does not** bump the version.
- A bump means the two ends no longer speak the same wire, and it is meant to be
  rare.
