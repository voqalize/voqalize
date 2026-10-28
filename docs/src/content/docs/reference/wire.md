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
A voice agent breaks each of those, and every rule below is a consequence of
exactly one of them.

| Property of voice | What the wire does about it |
|---|---|
| Only one party can hold the air, and the human decides when they take it. | The brain never initiates. It is handed the floor by a stimulus and answers. |
| Output is consumed in real time and can be cut mid-word. | Speech is bracketed into units, and `Finalize` reports back what was actually heard. |
| Silence reads as failure. | The opening line is a plain string, sent before anything else. Nothing waits on a model there. |
| Output is a stream, not a value. | Speech arrives as chunks inside an open unit, not as one finished message. |

## The voice plane and the RTVI plane

**The voice plane is ours**: turns, speech units, what the user actually heard,
and the control leg. Voqalize mints the turn because Voqalize decides when a turn
commits, and speech names the turn it answers.

**The RTVI plane is a tunnel.** An `RTVIFrame` is one pipecat RTVI message —
`{id, label: "rtvi-ai", type, data}` minus the constant label — forwarded
verbatim in both directions between the app and the brain. Voqalize moves the
whitelisted types and interprets nothing else about them.

The planes share the socket and nothing else. A message on the RTVI plane
never mints a turn, never takes the floor, and never changes what the user
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

If your brain reaches Voqalize through the [Cortex relay](/build/hosting/#a-brain-that-dials-out),
Cortex relays these bytes without reading them. The ends of the wire are
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
between the legs — the same brain code serves both.

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
1, and after it only `UserMessage` and `UserIdle` mint one. So the first thing
the user says is turn 2.

A turn is a permission to speak. The brain names it on every `SpeechStart`, and
that is what lets Voqalize tell speech that answers the current stimulus from
speech still arriving for one the user has already talked over.

Nothing else mints a turn. An `RTVIFrame` from the app does not — the app tapping
a button is not the app taking the floor.

## Speech units

**`speech_id` is brain-minted and names one unit of speech.** `SpeechStart`
opens it and binds it to a turn; each `SpeechChunk` carries it; `SpeechEnd`
closes it — or `SpeechCancel` does, when the brain takes it back; the `Finalize`
that reports what was heard names it back. Voqalize never
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
nothing has been synthesized and the user has heard nothing.

The comparison is `!=`, not `<`. A lower version is not a subset of a higher
one; the arms it names may mean something else underneath it. Refusing in both
directions is what keeps that from being a guess.

The version gates behaviour, not parsing — protobuf ignores fields it does not
know without help. What a version buys is the ability to refuse rather than
guess.

## Capabilities

`SessionStart.capabilities` lists what this Voqalize honours beyond the
version's baseline. A frame added within a version is skipped, not refused, by a
Voqalize that predates it, so a brain that sent one would see nothing happen and
could not tell *ignored* from *too late*. The list says up front.

```proto
enum Capability {
  CAPABILITY_UNSPECIFIED = 0;
  CAPABILITY_SPEECH_CANCEL = 1;  // SpeechCancel is honoured
  // …
  CAPABILITY_TURN_STEPS = 3;     // TurnStep is recorded
}
```

| Capability | Means |
|---|---|
| `CAPABILITY_SPEECH_CANCEL` | `SpeechCancel` stops a unit and is answered by its `Finalize`. See [taking speech back](#taking-speech-back). |
| `CAPABILITY_TURN_STEPS` | `TurnStep` is recorded beside its turn. See [what a turn did](#what-a-turn-did). |

Check before sending an optional frame, and treat a value you do not recognise
as absent. Adding a capability is append-only and does not move the version.
The Python SDK reads them as `session.can_cancel_speech` and
`session.can_report_steps`, and refuses the call locally when the one it needs
is false.

## Voqalize → brain

| Message | Fields | Meaning |
|---|---|---|
| `SessionStart` | `turn_id`, `session_id`, `init` *(JSON)*, `wire_version`, `capabilities` | First envelope of the session, and its first turn. `init` is your opaque init data, whatever the session was minted with, and reaches your brain as `session.init`. `capabilities` is what this Voqalize honours beyond the version's baseline — see [capabilities](#capabilities). Who the agent is arrives on the connection's credential, verified, and never here. |
| `UserMessage` | `turn_id`, `text` | The human finished an utterance. A new turn: the floor is the brain's. |
| `UserIdle` | `turn_id`, `level`, `idle_ms` | The human has been silent past the configured timeout. Also a new turn. `level` counts consecutive escalations with no intervening speech (1 is the first nudge) and resets when they speak; `idle_ms` is the silence elapsed when it fired. |
| `Interruption` | `through_turn` | Everything up to and including `through_turn` is dead — the user will not hear it. Stop generating for it. |
| `Finalize` | `speech_id`, `heard_text` | What the human actually heard of one speech unit. |
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
| `SpeechCancel` | `speech_id` | Stop one unit now and close it. Answered by that unit's `Finalize`, and nothing else. Honoured when `SessionStart` lists `CAPABILITY_SPEECH_CANCEL`. |
| `RTVIFrame` | `type`, `data` *(JSON)*, `id`, `turn_id` | Drive the screen. Relayed to the app unread. |
| `TurnStep` | `turn_id`, `kind`, `name`, `provider`, times, `counts` | One piece of work the brain did for a turn: a model request, a tool, a query. Recorded, never acknowledged. Honoured when `SessionStart` lists `CAPABILITY_TURN_STEPS`. See [what a turn did](#what-a-turn-did). |
| `Request` | `request_id`, one `op` | Change how the call behaves — today `configure`. Answered by exactly one `Response`. |
| `End` | — | Hang up. |
| `Cancel` | `reason` | Tear down abruptly. |
| `Error` | `code`, `message`, `fatal` | Something went wrong on this side. |

Fields marked *(JSON)* travel as a JSON-encoded string and arrive as a dict in
the SDK. The wire has no `Struct` dependency; opaque payloads stay opaque.

### What the human heard

`Finalize.heard_text` is the **delivered prefix** — what was actually played,
not what was generated. It is a *verbatim* prefix of that unit's own text, never
a concatenation across units, which is what makes it the whole report: equal to
what you sent means the unit played out, shorter means the user cut it off, and
empty against chunks you sent means nothing reached the ear.

So the message carries no verdict. Tag 3 held a `FinalizeReason` until
2026-08-27 and is now reserved: you hold the text you generated, Voqalize holds
what played, and the comparison is one subtraction away on the end that has both.
A copy of that answer could disagree with it; the subtraction cannot. An older
brain still decodes the message and reads the field as unset.

"Played" means **released on Voqalize's playout clock** — handed to the
outbound media — and it is word-granular. It is accurate to about one word
either way: a word whose audio had only just been handed over counts as heard,
and audio already on the network or in the user's jitter buffer keeps playing
after a cut. Where that matters, as it does for a guardrail, read it as *the
user may have heard one word more*.

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

### Taking speech back

`SpeechCancel(speech_id)` is the brain's own cut. A guardrail running beside the
model flags text that has already been sent; the brain stops its model, sends
`SpeechCancel`, and Voqalize drops whatever of that unit has not played.

**The answer is the unit's `Finalize`, and nothing else.** Voqalize already owes
every unit exactly one, so there is no acknowledgement frame: its `heard_text`
says how far playout got, and comparing it with what you sent says whether the
cut landed in time.

**It is not a barge-in.** No `Interruption` is sent, the watermark does not
move, and the turn stays open — the brain may open a new unit on the same
`turn_id` straight away, and that unit plays.

```
B→V  SpeechStart{speech_id: 7, turn_id: 3}
B→V  SpeechChunk{7, "Good question. One approach is "}
B→V  SpeechChunk{7, "to use binary search on…"}     ← the guardrail flags this
B→V  SpeechCancel{7}                                ← closes unit 7; no SpeechEnd
V→B  Finalize{7, heard_text: "Good question."}
B→V  SpeechStart{speech_id: 8, turn_id: 3}          ← same turn, still open
B→V  SpeechChunk{8, "Let's think about it differently."}
B→V  SpeechEnd{8}
V→B  Finalize{8, heard_text: "Let's think about it differently."}
```

| When the cancel arrives | What comes back |
|---|---|
| The unit is open, or closed and still playing or queued | Its `Finalize`, once the cut has happened — milliseconds |
| Before any of it was spoken | Its `Finalize` with empty `heard_text` |
| After its `Finalize` was sent, or a second time | Nothing: the one `Finalize` has already gone |
| Naming `0` or a unit this session never opened | A non-fatal `PROTOCOL` `Error`; the call continues |
| At a Voqalize that does not list the capability | Nothing; the unit plays out and its `Finalize` carries the full text |

Socket order decides every race. A chunk sent before the cancel is part of what
was cut; a `SpeechChunk` or `SpeechEnd` for the unit after it is **ignored, not
an error**, because a model may still be streaming when the guardrail decides.
A cancel and a barge-in arriving together converge: each unit still gets
exactly one `Finalize`, and the barge-in's `Interruption` kills the turn as
usual.

Today the cut is the whole floor, not one unit: every unit still playing or
queued when the cancel arrives is stopped — an earlier unit of the same reply
included, and a later one still open, whose further chunks and `SpeechEnd` are
ignored the same way — and each gets its own truthful `Finalize`, oldest first.
A unit opened after the cancel plays. Stopping your model is still your job: Voqalize
can only drop text it is sent.

### What a turn did

`TurnStep` is the brain telling Voqalize about one piece of work it did for a
turn: a model request, a tool it ran, a database query, an API or MCP call.
Voqalize records it beside the turn and changes nothing about the call because
of it. A brain that sends none loses nothing but the record.

```proto
message TurnStep {
  uint64              turn_id         = 1;
  string              kind            = 2;  // "model", "tool", or the brain's own word
  string              name            = 3;  // "gpt-6-sol", "open_section", "orders"
  string              provider        = 4;  // the company whose meter ran; empty for the brain's own work
  uint32              start_ms        = 5;  // after the brain received the turn's stimulus
  uint32              duration_ms     = 6;
  optional uint32     first_output_ms = 7;  // for a step that streams
  map<string, uint64> counts          = 8;  // how much of what, by name
}
```

**A turn is the steps that name it.** Say the visitor asks to see pricing, and
the brain asks its model, which calls `open_section`, then asks again with the
result and speaks. That is three steps on one `turn_id`:

| `kind` | `name` | `start_ms` | `duration_ms` |
|---|---|---|---|
| `tool` | `open_section` | 610 | 40 |
| `model` | `gpt-6-sol` | 0 | 900 |
| `model` | `gpt-6-sol` | 900 | 600 |

Each is sent when it ends, so they arrive in the order they finished, and a
reader orders them by `start_ms`. Steps may overlap: the tool above ran while the
first request's stream was open, so it lies inside it.

**It is never acknowledged.** Nothing comes back for it, success or failure, and
it needs no turn to be open: it is floor-free, like an `RTVIFrame`. It is
envelope arm 16.

**`kind` and the count names are open.** They are words, like a `voice_id`, not
a list fixed in the proto: a new kind of work, or a new thing a provider bills
for, needs no new message and no new Voqalize. The words below are the ones every
brain spells the same way. A brain may use its own for its own work, and a
reader shows a word it does not know as it is.

| `kind` | Means |
|---|---|
| `model` | One request to a model. `name` is the model as the brain asked for it. |
| `tool` | One tool the model called. `name` is the tool's name. |
| `database`, `http`, `mcp` | The brain's own work: a query, an API call, an MCP call. |

| Count | Means |
|---|---|
| `input_tokens` | Every input token, cached ones included. |
| `cached_input_tokens` | The part of `input_tokens` served from the provider's prompt cache. |
| `cache_write_tokens` | Input tokens written to the cache, where the provider bills writes apart. |
| `output_tokens` | Tokens the model wrote as text or tool calls, reasoning excluded. |
| `reasoning_tokens` | Tokens spent on reasoning nobody hears. |
| `audio_input_tokens`, `audio_output_tokens` | For a model that takes or makes audio. |
| `rows` | Rows a query returned. |

**Absent is not zero.** A count that was not reported is left out of `counts`;
one present with `0` is a zero. That is what lets a reader tell *not reported*
from *none*.

**Facts about the work, never its content.** No prompt, no tool arguments, no
result, no query text, nothing the caller said. Steps are kept in the call
record, and the record of a call is not the place for its words.

**Counts, never prices.** A price changes on a date nobody here controls, so cost
is computed from the counts by whoever reads them.

**`provider` is whoever's meter ran.** `openai`, `google`, `anthropic` — never a
router or gateway in between, so steps from different brains add up by company.

At a Voqalize that does not list `CAPABILITY_TURN_STEPS`, the frame is skipped.
A brain that checks first sends nothing that will not be kept.

## The control leg

The brain asks Voqalize to change how the call behaves, and learns whether the ask
was any good.

```proto
message Request {
  uint64 request_id = 1;
  oneof op { Config configure = 2; }
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

### `Config` — `tts`, `stt`, `idle` and `ack` in one message

```proto
message Config {
  TtsConfig  tts  = 1;
  SttConfig  stt  = 2;
  IdleConfig idle = 3;
  AckConfig  ack  = 4;
}

message TtsConfig  { optional Voice voice = 1; optional Language language = 2; }
message SttConfig  { optional Language language = 1; optional uint32 patience = 2; }
message IdleConfig { optional uint32 timeout_ms = 1; }
message AckConfig  { optional bool enabled = 1; }
```

This message is used twice. `sessions.connect` supplies the starting sections immediately before the call; the brain sends the same
shape in this op while the call is running. The agent record holds a connection
`mode`, a `brain_url` and a recording default, and carries no voice, language or
idle configuration.
See [the catalog](/reference/catalog/#where-it-is-set).

Unset means *leave it alone*: a `Request` carries a delta and the call is
already running. Explicit presence is what makes that readable — without it an
unset `timeout_ms` is indistinguishable from `0`, and a delta that never
mentioned idle detection would silently disable it.

**One op, not one per section.** A language change has to move both legs at
once. Separate ops would put a turn boundary — and a possible refusal — between
the halves, leaving the call heard in one language and spoken in another.

The surface is deliberately narrow: the voice, the language on each leg, how
long the recognizer waits through a pause, the idle timeout, and whether
Voqalize acknowledges the caller. The
recognizer's other thresholds are not settable from here; they keep the voice
tier's own calibration. It widens as we learn what is worth naming, and a knob
is far easier to add than to take back.

### When each change lands

| Change | Effective | Why |
|---|---|---|
| `tts` | the next speech unit | The synthesizer locks the voice for one synthesis context and Voqalize pins one context per unit, so the sentence being spoken finishes in the old voice. |
| `stt.language` | once the open turn commits | The recognizer carries per-turn decoder state, so the turn being spoken when the change arrives still transcribes as spoken. |
| `stt.patience` | immediately | It bounds a silence counter that resets at every word, so there is nothing in flight for it to corrupt — including the pause already running. |
| `ack` | the next turn | The acknowledgement is chosen when a turn ends, so a turn already answered keeps what it had. |
| `idle` | immediately | Voqalize owns that timer; one already running restarts on the new duration. `timeout_ms` is the silence after Voqalize stops speaking before it mints an idle turn, and `0` disables idle detection. |

### `ack` — Voqalize acknowledges while the brain thinks

When the caller's turn ends and the brain has not started its reply, Voqalize
can say a short line of its own — "Let me check.", "Sure.", "Go on." — chosen
from what the caller said, so the caller is not left in silence while the model
works. Where nothing fits, it says nothing. It speaks only the languages it has
a vocabulary for, which today are English, Hindi and Spanish, and stays silent
in every other.

**It is on unless the session turns it off.** `enabled: false` at
`sessions.connect` turns it off for one call; the brain can turn it off, or back
on, with this op at any time — which is how an agent opts out for every call.
A brain that opens its replies with its own acknowledgement should turn it off,
or the caller hears two.

### Both legs carry a language, and both must be set

`Language` appears on `TtsConfig` and on `SttConfig`, and that is not
duplication. The recognizer serves English, the European languages and the
Indic languages; a voice
speaks the subset it was recorded or trained for, which is smaller and differs
from voice to voice. So the legs genuinely differ — a call understood in Odia is
spoken with the Hindi clip — and one field could not say so.

The rules that follow are enforced in different places on purpose:

- **Name a language on one leg and you must name it on the other.** Not that
  they agree — that you stated both. Moving one alone is the silent failure:
  the words stay right and only the voice is wrong, which no transcript, no WER
  number and no automated check will ever show you. This is a property of the
  message itself, so the SDK refuses to build it — before the request leaves.
- **A `tts.language` the chosen voice does not speak is rejected**, rather
  than served by the Hindi clip. That one is not in the message; it is a
  capability of the speech tier, it changes as voices are added and clips are
  recorded, and it comes back as a `REJECTED` `Response` naming the languages
  that voice does speak. A wire contract that froze today's pairings would be
  wrong the day the next clip lands, and every SDK carrying a copy of it would
  be wrong with it.

Write what you are actually getting:

```proto
stt { language: LANGUAGE_OR }   // listen in Odia
tts { language: LANGUAGE_HI }   // speak with the Hindi clip
```

Changing only the voice touches no language field and is unaffected by either
rule.

### Waiting through a pause (`stt.patience`)

`patience` is a scale from 0 to 10, not a duration: `0` answers as soon as the
recognizer can, `10` lets a caller finish a sentence they are still assembling.
What a step is worth in silence stays ours, because the frame size and the
calibration behind it are ours to retune — a brain that wants *wait longer for
this caller* says that, and keeps saying it correctly across a retune it never
hears about.

Leave it unset and the session runs the calibration that deployment already
runs, which is patience 7. That is the value the tuning was done against, and it
is written down so the scale has a fixed point to reason from rather than one
you have to discover. **Nothing writes a `7` onto the wire** — unset is what a
default-patience session sends, which is why a brain on an older SDK is served
exactly what it was served before.

A patience off the scale is refused at whichever door it arrives at, in the same
words. At `sessions.connect` the request comes back `invalid_config` and the
call never starts. Mid-call it comes back as a `RequestRejected` whose `detail`
names the range, and the session continues at the patience it already had — so a
brain that miscalculates one loses the change, not the call. A brain on the
Python SDK meets an earlier door and never reaches this one: `SttConfig` raises
`ConfigError` in your own process, before anything is written to the socket.

### The catalog

`Voice` and `Language` are enumerations, not free strings, so a value we do not
serve cannot be sent at all. Each `Language` value carries its speech-tier code
as a proto option, which is what makes the SDKs' own tables derived rather than
copied:

```proto
extend google.protobuf.EnumValueOptions {
  optional string iso_code = 50001;
}

enum Language {
  // Unset. On the wire this means leave the language alone.
  LANGUAGE_UNSPECIFIED = 0;

  // English.
  LANGUAGE_EN = 1 [(iso_code) = "en"];

  // Odia.
  LANGUAGE_OR = 16 [(iso_code) = "or"];
  // …
}
```

`iso_code` is not derivable from the name: the catalog mixes ISO 639-1
two-letter codes with 639-3 three-letter ones, because some of these languages
have no two-letter code. It is here because it is the identifier a developer
writes and reads, and every end of the wire has to spell it the same way.

Nothing here says which of these can be *spoken*. That is a capability of the
speech tier, it moves when the speech tier does, and Voqalize answers it when
asked. See the [voice & language catalog](/reference/catalog) for the full
list.

Every declaration in `frames.proto` carries its own doc comment, the way the
`Language` values above do — protoc puts them in `SourceCodeInfo`, so buf and
any other descriptor consumer read the same words you do, and `buf lint`'s
`COMMENTS` category fails the build if one is missing.

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
| App → Voqalize → brain | `ui-event`, `client-message`, `ui-snapshot`, `ui-cancel-job-group` |

`send-text` is on the app's half of the whitelist and is not in that row on
purpose: it is the one type that does not cross as a message. A typed sentence
takes the floor the way a spoken one does, so Voqalize commits it as a **user
turn** — your brain answers it in `on_user_message` and never sees an `RTVI`
frame for it. See [the RTVI plane](/reference/rtvi/).

A type absent from the list does not cross in either direction. `bot-*` and
`llm-*` are Voqalize's own assertions about the media and the model, and a
brain must not be able to forge them; a brain that sends one gets a **non-fatal
`PROTOCOL` `Error`** and the frame is dropped. The call continues — see
[error codes](/reference/errors/).

## Lifecycle

`End` is a graceful close from either side. `Cancel` carries a `reason` and is
the abrupt one; the SDK never sends it, so a brain that emits `Cancel` toward
Voqalize is one written directly against the wire. `Error` carries a `code`, a
message and a `fatal` flag; a fatal error means the session is ending, and a
non-fatal one is a signal the brain may act on.

## Connection and auth

Voqalize dials `{brain_url}?session_id={session_id}`, presenting **the
brain-connection token** — a short-lived RS256 JWT, sent as a bare token or as
`Authorization: Bearer <jwt>` and verified against Voqalize's public key. Required claims: `iss="pygato"`, `aud="brain"`,
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
on `Finalize`, which reports what a unit was heard as and needs to say which —
and the SDK writes the same id onto the `SpeechStart` you yielded, so you can
name the unit to `cancel_speech`.

```python
class Greeter(Brain):
    async def greet(self, session):
        return "Hi! How can I help?"

    async def on_user_message(self, session, msg):
        yield SpeechStart()
        yield SpeechChunk(f"You said: {msg.text}")
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
| `yield SpeechStart()` / `SpeechChunk` / `SpeechEnd()` | → `SpeechStart` / `SpeechChunk` / `SpeechEnd`, one minted `speech_id` per unit |
| `session.send_rtvi(type, data)` / `session.dispatch(action)` | → `RTVIFrame` |
| `await session.configure(Config(...))` | → `Request`, awaited until its `Response` |
| `await session.cancel_speech(start.speech_id)` | → `SpeechCancel`, awaited until that unit's `Finalize`; refused locally unless `session.can_cancel_speech` |
| `session.report_step(TurnStep(...))` | → `TurnStep`, never answered; refused locally unless `session.can_report_steps`. The SDK's model-backed brains send one for every model request and tool |
| `session.end()` | → `End` |

`greet` returns a string or `None` — one unit of speech, on the turn
`SessionStart` itself minted. It is a static line: no model call sits on the one
turn that has nothing to retry it.

The speaking callbacks are async generators, and **the generator is the mouth**:
`SpeechStart`, `SpeechChunk` and `SpeechEnd` are the only things they may yield,
because speech is the only output whose position on the audio timeline is its
meaning. Awaiting between yields is how a tool call sits between two things the
brain says. Everything else is a method on the session, callable from anywhere —
including from the callbacks that are not generators at all.

`session.dispatch(action)` is sugar over `send_rtvi`: it serializes an action
onto RTVI's own `ui-command` as `{"command": "show_results", "payload": {…fields}}`,
which a pipecat client reads with `useUICommandHandler`. Nothing comes back — if
the app has an answer it sends an ordinary `ui-event`, correlated by whatever
the app puts in it.

`configure` is awaited because Voqalize answers it. Awaiting is how a language
Voqalize cannot serve becomes an exception the brain handles, rather than a call
that runs on sounding wrong and reports nothing — the rejection names the reason
and the SDK raises `RequestRejected` carrying it.

One rule does not wait for that round trip: a half-stated language is a
`ConfigError` at the call site, because whether both legs were named is a
property of the message and needs nothing from the far end to decide.

## Invariants

Both ends rely on these, and a brain that implements the wire directly owes them:

- **`SessionStart` is first**, and nothing goes the other way before it.
- **Brackets balance.** Every `SpeechStart` is closed by a `SpeechEnd` or a
  `SpeechCancel`; a `SpeechChunk` outside an open unit is an error. A
  `SpeechCancel` after the unit's `SpeechEnd` is legal — it cuts a unit still
  playing — and a `SpeechChunk` or `SpeechEnd` after its `SpeechCancel` is
  ignored.
- **One `speech_id` per unit**, on every frame of that unit, brain-minted and
  never reused.
- **Speech names its turn.** Every `SpeechStart` carries the `turn_id` of the
  stimulus it answers, and only Voqalize mints one.
- **The interruption watermark is one-way** — never acknowledged, never
  echoed, never lowered.
- **Exactly one `Response` per `Request`**, matching on `request_id`.
- **Nothing is emitted outside a turn except floor-free messages** —
  `RTVIFrame`, `Request`, `SpeechCancel`, `TurnStep`, `End`, `Cancel`, `Error`.
- **`heard_text` is the delivered prefix**, per unit, never a concatenation,
  and a verbatim prefix of that unit's own text.
- **Exactly one `Finalize` per bracket the brain opened**, in that order —
  including for a unit that turned out silent, which reports nothing heard, and
  for a unit the brain cancelled, which reports what played before the cut.
  A brain cannot know in advance which of its units will be silent, and an
  absent report is indistinguishable from a late one.

## Changing the wire

The schema is append-only within a version.

- Field numbers are never reused; a retired one is `reserved`.
- `Envelope` arms are never renumbered.
- A message is reserved rather than removed.
- Adding a field or an arm **does not** bump the version.
- A bump means the ends no longer speak the same wire, and it is meant to be
  rare.
