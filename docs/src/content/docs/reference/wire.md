---
title: The wire
description: One WebSocket per session between Voqalize and your brain — the framing, the envelope, every message, and what each one obliges the other to do.
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

## The shape of a session

Voqalize dials your brain, one socket per call, and speaks first: the session's
opening envelope is `SessionStart`, and nothing crosses in the other direction
until it has arrived.

**Voqalize owns the floor.** It decides when the brain may speak by sending a
stimulus — a `UserMessage` or a `UserIdle` — and the brain answers with speech.
There is no message a brain can send to ask for the floor, and none that
interrupts the human. That absence is what makes a call predictable.

Everything the brain sends that is *not* speech is floor-free: a
`BrowserCommand` to redraw the screen, a `Request` to change how the call
behaves, an `End` to hang up. Those need no turn and are legal at any moment.

If your brain reaches Voqalize through the [Cortex relay](/docs/deploy/cortex),
Cortex relays these bytes without reading them. The two ends of the wire are the
Voqalize and the brain; nothing in between interprets the schema.

## Framing

Binary WebSocket messages only — a text message is an error.

| Leg | Layout |
|---|---|
| Your inbound server, at `{brain_url}/s/{session_id}` | `[Envelope]` |
| The Cortex relay, at `/agent` | `[16-byte session_id][Envelope]` |

One message carries one envelope and nothing around it. Nothing frames it,
lengths it, or tags it: the WebSocket already delimits messages, and the
envelope already says what it is.

The 16-byte prefix on the relay leg is how one socket carries many sessions.
Cortex adds it inbound and strips it outbound, and it is the only difference
between the two legs — the same brain code serves both.

## The envelope

Every message is an `Envelope`: one message in a `oneof body`, plus two
correlation scalars that belong to the envelope and never to a body.

```proto
message Envelope {
  oneof body { SessionStart session_start = 1; /* … */ }
  uint64 epoch     = 51;
  uint64 speech_id = 52;
}
```

**`epoch`** is Voqalize-minted and session-monotonic, incremented on every stimulus
Voqalize commits. The brain echoes it, unread, on everything it emits while
handling that stimulus. It exists for one decision: when a barge-in opens a
drain barrier, Voqalize must tell "emitted before the barrier" from "emitted after
it, answering the new stimulus". Only a Voqalize-minted counter settles that. No
brain-facing API names it. Speech the brain starts on its own — the opening line
— answers no stimulus and rides epoch `0`.

**`speech_id`** is brain-minted and names one unit of speech. Every envelope of
that unit carries it: the `SpeechStart`/`SpeechEnd` bracket, each `SpeechChunk`
inside, and the `Finalize` that reports what was heard. Voqalize never mints, reads,
orders or compares one — it echoes it back on `Finalize` exactly as it arrived,
so a brain may number units however it likes.

Correlation lives here so that every body is only its own payload. The one
identifier that is *not* in the envelope is `Request.request_id`, which names a
single request/response pair rather than anything about the session, and so
belongs to the pair.

## Version

`SessionStart.wire_version` is the version Voqalize speaks. **This is
version 2.**

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
| `SessionStart` | `session_id`, `init` *(JSON)*, `wire_version` | First envelope of the session. `init` is your opaque init data, whatever the session was minted with, and reaches your brain as `session.init`. Who the agent is arrives on the connection's credential, verified, and never here. |
| `UserMessage` | `text` | The human finished an utterance. A stimulus: the floor is the brain's. |
| `UserIdle` | `level`, `idle_ms` | The human has been silent past the configured timeout. Also a stimulus. `level` counts consecutive escalations with no intervening speech (1 is the first nudge) and resets when they speak; `idle_ms` is the silence elapsed when it fired. |
| `BrowserMessage` | `type`, `data` *(JSON)* | The browser said something — a tap, a keystroke, a state push. Every one is delivered; Voqalize never reads `type` and never decides whether it deserves a reply. |
| `Interruption` | — | The human spoke over the bot. |
| `Finalize` | `heard_text`, `reason` | What the human actually heard of the unit named by the envelope's `speech_id`. |
| `Response` | `request_id`, `status`, `detail` | The answer to one `Request`. |
| `End` | — | The call is over. |
| `Cancel` | `reason` | The call is being torn down abruptly. |
| `Error` | `error`, `fatal` | Something went wrong. `fatal` means the session is ending. |

## Brain → Voqalize

| Message | Fields | Meaning |
|---|---|---|
| `SpeechStart` | — | Open a unit of speech. |
| `SpeechChunk` | `text` | Text to speak, inside an open unit. Stream them as they are produced. |
| `SpeechEnd` | — | Close the open unit. |
| `BrowserCommand` | `data` *(JSON)* | Drive the screen. Relayed to the browser unread. |
| `Interruption` | — | The drain barrier: sent back after an `Interruption` from Voqalize, once the brain has stopped producing for the turn it cut. |
| `Request` | `request_id`, one `op` | Change how the call behaves. Answered by exactly one `Response`. |
| `End` | — | Hang up. |
| `Cancel` | `reason` | Tear down abruptly. |
| `Error` | `error`, `fatal` | Something went wrong on this side. |

Fields marked *(JSON)* travel as a JSON-encoded string and arrive as a dict in
the SDK. The wire has no `Struct` dependency; opaque payloads stay opaque.

### Speech units, and what the human heard

A unit is one `SpeechStart` … `SpeechEnd` bracket, and it is the granularity of
everything downstream. It is bracketed because it can be cut mid-word.

`Finalize.heard_text` is the **delivered prefix** — what was actually played,
not what was generated. On a barge-in the two differ, and it is never a
concatenation across units. `reason` is `COMPLETED` or `USER_BARGE_IN`.

Feed `heard_text` back into your model's history rather than what you generated.
A model that remembers the sentence it started is a model that references a
sentence the human never heard.

`Finalize` arrives after playout, which can be long after the turn that produced
the unit has returned. **A turn ends when the brain stops emitting, not when the
audio finishes.**

### Barge-in

The human speaks over the bot. Voqalize sends `Interruption`; the brain stops the
turn in flight and echoes `Interruption` back. The echo is Voqalize's drain barrier
— everything before it is discarded, everything after it belongs to the new
stimulus — so it must not arrive until the frames it fences off have stopped
being produced. That ordering is the brain's obligation, and the SDK holds it.

## The control leg

The brain asks Voqalize to change how the call behaves, and learns whether the ask
was any good.

```proto
message Request {
  uint64 request_id = 1;
  oneof op { ConfigureTts configure_tts = 2; ConfigureStt configure_stt = 3;
             ConfigureIdle configure_idle = 4; }
}
message Response { uint64 request_id = 1; Status status = 2; string detail = 3; }
```

`request_id` is brain-minted and session-monotonic; its whole job is to name the
`Response`. **Exactly one `Response` comes back for every `Request`, on every op,
always** — a brain awaiting one never has to know which ops answer.

`status` is `ACCEPTED` or `REJECTED`, and it reports **whether Voqalize took the
request, not whether the effect is audible yet**. `detail` says why on a
rejection and is empty otherwise, and it is written to be shown.

A request is accepted or rejected **whole**. A rejected `ConfigureStt` applies
none of its fields, thresholds included, so the call is still coherent
afterwards and the previous settings are still in force.

Every field of every op is `optional`, and that is load-bearing: these are
deltas, so Voqalize changes only what the brain set. Without explicit presence, an
unset field is indistinguishable from `0` or `""`, and a delta silently becomes a
reset.

### `ConfigureTts` — `voice`, `language`, `model`, `speed`

Takes effect at the next speech unit, never mid-utterance: the synthesizer locks
these for the length of one synthesis context and Voqalize pins one context per
unit. Accepting is therefore the most Voqalize can honestly report — there is no
ask-and-answer with the synthesizer, only the next unit. `speed` runs 0.5–2.0,
where 1.0 is the voice's natural rate.

### `ConfigureStt` — `language_hint`, plus the recognizer's thresholds

The thresholds apply live: the recognizer treats them as bounds against counters
that reset themselves, so changing one mid-utterance is safe. `language_hint`
does not — a language change carries per-turn decoder state, so the recognizer
queues it and applies it once the open turn commits. The turn being spoken when
it arrives still transcribes as spoken; the change governs the next one.

Acceptance here is the recognizer's own answer, not Voqalize's guess: a language it
has no engine for rejects the request.

Threshold names match the recognizer's own `Configure` message verbatim. See the
[voice & language catalog](/docs/reference/catalog) for what is available.

### `ConfigureIdle` — `timeout_ms`

Applied by Voqalize itself, immediately; a running idle timer restarts on the new
duration. `timeout_ms` is the silence after Voqalize stops speaking before it opens
an idle stimulus. `0` disables idle detection.

## Lifecycle

`End` is a graceful close from either side. `Cancel` carries a `reason` and is
the abrupt one; the SDK never sends it, so a brain that emits `Cancel` toward
Voqalize is one written directly against the wire. `Error` carries a message and a `fatal` flag; a fatal error means
the session is ending, and a non-fatal one is a signal the brain may act on.

## Connection and auth

Voqalize dials `{brain_url}/s/{session_id}`, presenting a short-lived RS256 JWT as a
bare token or as `Authorization: Bearer <jwt>`, verified against Voqalize's
public key. Required claims: `iss="pygato"`, `aud="brain"`, `sub == session_id`,
and `exp`. `agent_id` and `tenant_id` are informational — the recipient decides
from them whether it serves this agent.

`aud` is the constant `"brain"` for every brain, whatever kind it is. Routing
lives in the `brain_url`, never in the token. `iss` is the literal string
`pygato` — our internal name for the process that holds the call, here because it
is a value you compare against, not a name you need.

Close codes: **4000** — no agent, permanent, never retry. **4001** — agent gone,
transient, reconnect with backoff. Anything else is transient. **1000** from your
own side means you closed it and no reconnect follows. A `401` or `403` at the
HTTP handshake is not a close code at all and is terminal: a credential that is
missing, revoked, or for another agent will not start working on attempt twelve.

## What the SDK makes of it

The [Python SDK](https://github.com/voqalize/voqalize/tree/main/sdk/python) is
the wire with the correlation removed. A brain implements callbacks and yields
speech; nothing in its surface names an `epoch`. The one `speech_id` it sees is
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
| `on_browser_message` | ← `BrowserMessage` |
| `on_finalize` | ← `Finalize` |
| `on_error` | ← `Error` |
| `yield SpeechStart()` / `Chunk` / `SpeechEnd()` | → `SpeechStart` / `SpeechChunk` / `SpeechEnd`, one minted `speech_id` per unit |
| `session.dispatch(action)` | → `BrowserCommand` |
| `await session.configure_tts / _stt / _idle / _language` | → `Request`, awaited until its `Response` |
| `session.end()` | → `End` |

`greet` returns a string or `None` — one unit of speech, sent before any
stimulus, on epoch `0`. It is a static line: no model call sits on the one turn
that has nothing to retry it.

The speaking callbacks are async generators, and **the generator is the mouth**:
`SpeechStart`, `Chunk` and `SpeechEnd` are the only things they may yield,
because speech is the only output whose position on the audio timeline is its
meaning. Awaiting between yields is how a tool call sits between two things the
brain says. Everything else is a method on the session, callable from anywhere —
including from the callbacks that are not generators at all.

`session.dispatch(action)` serializes an action onto the `BrowserCommand`
payload as `{"type": "ui_command", "action": "show_results", "action_id": 7,
…fields}`. The browser answers with a `BrowserMessage` of type `action_result`
carrying that `action_id`, and the SDK settles it into the action's `on_result`.

`configure_*` is awaited because Voqalize answers it. Awaiting is how a language
Voqalize has no recognizer for becomes an exception the brain handles, rather than a
call that runs on sounding wrong and reports nothing.

## Invariants

Both ends rely on these, and a brain that implements the wire directly owes them:

1. **`SessionStart` is first**, and nothing goes the other way before it.
2. **Brackets balance.** Every `SpeechStart` is closed by a `SpeechEnd`; a
   `SpeechChunk` outside an open unit is an error.
3. **One `speech_id` per unit**, on every envelope of that unit, brain-minted and
   never reused.
4. **The epoch is echoed unread** on speech: every envelope of a unit carries
   the epoch of the stimulus that prompted it. Floor-free messages ride epoch
   `0`, whenever they are sent.
5. **The interruption echo comes last** — after the cut turn has stopped
   producing.
6. **Exactly one `Response` per `Request`**, matching on `request_id`.
7. **Nothing is emitted outside a stimulus except floor-free messages** —
   `BrowserCommand`, `Request`, `End`, `Cancel`, `Error` — and the greeting,
   the one speech unit that answers no stimulus.
8. **`heard_text` is the delivered prefix**, per unit, never a concatenation.

## Changing the wire

The schema is append-only from v1.

- Field numbers are never reused; a retired one is `reserved`.
- `Envelope` arms are never renumbered.
- A message is reserved rather than removed.
- Adding a field or an arm **does not** bump the version.
- A bump means the two ends no longer speak the same wire, and it is meant to be
  rare.
