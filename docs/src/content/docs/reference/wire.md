---
title: The wire
description: One WebSocket per session between Voqalize and your brain, told as a call in the order its messages appear, from the opening envelope to failure, with the full reference tables at the end.
---

Voqalize runs the call. Your brain decides what it says and what it shows. Between
them is one WebSocket per session carrying protobuf envelopes in both
directions, and this page is that contract in full.

The schema of record is
[`proto/voqalize/frames/frames.proto`](https://github.com/voqalize/voqalize/tree/main/proto/voqalize/frames/frames.proto).
The SDKs mirror it exactly, so most brains never see a byte of this. But
everything the SDK can do, it does by putting one of these messages on the wire,
and nothing else is possible.

The page follows one call from its first envelope. Each section adds the
messages that part of the call needs, and opens with a trace of the call so far.
In the traces, `V→B` is Voqalize to your brain, `B→V` is your brain to Voqalize,
and `…` stands for lines an earlier section already showed. The
[reference](#reference) at the end has every message in tables, with the framing,
the connection, the invariants and the rules for changing the wire.

## One socket, one envelope

```
V→B  SessionStart{session_id: "…", turn_id: 1, wire_version: 3, init: "{\"plan\":\"pro\"}", capabilities: […]}
```

Voqalize dials your brain, one socket per call, and speaks first. The session's
opening envelope is `SessionStart`, and nothing crosses in the other direction
until it has arrived.

Every message on the socket is an `Envelope`, and the envelope is one
`oneof body` and nothing else:

```proto
message Envelope {
  oneof body { SessionStart session_start = 1; /* … */ }
}
```

Exactly one body is set; an envelope with none is a protocol error, not an empty
frame. Every identifier is a field of the message it belongs to: `turn_id` on the
messages that mint or answer a turn, `speech_id` on the messages of one speech
unit, `request_id` on a request and its response. A reader that has parsed the
body has everything, and there is no second place to look.

`SessionStart` carries:

- `session_id`: the call. Stable for the session's life, and the same id the
  brain was dialled with as `?session_id=`.
- `turn_id`: the session's first turn. The next section is about it.
- `init`: your opaque init data, whatever the app passed at connect,
  JSON-encoded. It reaches your brain as `session.init`. Who the agent is
  arrives on the connection's credential, verified, and never here.
- `wire_version`: the version Voqalize speaks. A brain that speaks another one
  refuses the session; see [version](#version).
- `capabilities`: what this Voqalize honours beyond the version's baseline;
  see [capabilities](#capabilities).

If your brain reaches Voqalize through the [Cortex relay](/build/hosting/#a-brain-that-dials-out),
Cortex relays these bytes without reading them. The ends of the wire are
Voqalize and the brain; nothing in between interprets the schema.

## The greeting

```
V→B  SessionStart{turn_id: 1, wire_version: 3, …}
B→V  SpeechStart{speech_id: 1, turn_id: 1}
B→V  SpeechChunk{speech_id: 1, text: "Hi, welcome to the shop. "}
B→V  SpeechChunk{speech_id: 1, text: "What can I help you find?"}
B→V  SpeechEnd{speech_id: 1}
```

**Voqalize owns the floor.** It decides when the brain may speak by minting a
turn, and the brain answers with speech that names that turn. `SessionStart`
*is* turn 1, so the greeting answers it. There is no message a brain can send to
ask for the floor, and none that interrupts the human.

**`turn_id` is Voqalize-minted and session-monotonic.** A turn is a permission to
speak. The brain names it on every `SpeechStart`, and that is what lets Voqalize
tell speech that answers the current stimulus from speech still arriving for
one the user has already talked over.

Speech travels in **speech units**:

- `SpeechStart{speech_id, turn_id}` opens a unit and binds it to the turn it
  answers.
- `SpeechChunk{speech_id, text}` carries text inside the open unit, in order.
  Stream chunks as they are produced. Chunk boundaries carry no meaning:
  Voqalize re-segments the text for synthesis.
- `SpeechEnd{speech_id}` closes the unit.

**`speech_id` is brain-minted** and unique within the session. Voqalize never
mints, orders or compares one. It quotes it back exactly as it arrived, so a
brain may number units however it likes. A `SpeechChunk` outside an open unit is
an error.

## A user turn and the reply

```
…
B→V  SpeechEnd{speech_id: 1}
V→B  UserMessage{turn_id: 2, text: "do you have the blue one in large"}
B→V  SpeechStart{speech_id: 2, turn_id: 2}
B→V  SpeechChunk{speech_id: 2, text: "Let me look."}
B→V  SpeechEnd{speech_id: 2}
B→V  SpeechStart{speech_id: 3, turn_id: 2}
B→V  SpeechChunk{speech_id: 3, text: "Yes, there are two left in large."}
B→V  SpeechEnd{speech_id: 3}
```

`UserMessage{turn_id, text}` says the human finished an utterance. `text` is the
recognizer's committed transcript, and `turn_id` is a new turn: the floor is the
brain's. After `SessionStart`, only `UserMessage` and `UserIdle` mint a turn, so
the first thing the user says is turn 2.

One turn may hold several units: a line, a pause while a tool runs, then the
answer. The unit is the granularity of everything downstream, because the unit
is what can be cut mid-word. Each unit names the same `turn_id`.

## What was heard

```
…
B→V  SpeechEnd{speech_id: 1}
V→B  Finalize{speech_id: 1, heard_text: "Hi, welcome to the shop. What can I help you find?"}
V→B  UserMessage{turn_id: 2, text: "do you have the blue one in large"}
…
B→V  SpeechEnd{speech_id: 3}
V→B  Finalize{speech_id: 2, heard_text: "Let me look."}
V→B  Finalize{speech_id: 3, heard_text: "Yes, there are two left in large."}
```

`Finalize{speech_id, heard_text}` is what the human actually heard of one speech
unit. It is the only place a brain learns it. **Every unit the brain opens gets
exactly one `Finalize`**, in the order the units opened, including a unit that
turned out silent, which reports nothing heard.

`heard_text` is the **delivered prefix**: what was actually played, not what was
generated. It is a *verbatim* prefix of that unit's own text, never a
concatenation across units, which is what makes it the whole report:

| `heard_text` against the text you sent | Means |
|---|---|
| Equal | The unit played out. |
| Shorter | The user cut it off. |
| Empty, though you sent chunks | Nothing reached the ear. |

So the message carries no verdict: you hold the text you generated, Voqalize
holds what played, and the comparison is yours. Field 3 is reserved; it was a
reason field, retired because it was a second copy of that comparison.

"Played" means **released on Voqalize's playout clock**: handed to the outbound
media. It is word-granular and accurate to about one word either way. Audio
already on the network or in the user's jitter buffer keeps playing after a cut,
so where that matters, as it does for a guardrail, read it as *the user may have
heard one word more*. Do not build anything that depends on its last character.

Feed `heard_text` back into your model's history rather than what you generated.
A model that remembers the sentence it started is a model that references a
sentence the human never heard.

`Finalize` arrives after playout, which can be long after the turn that produced
the unit has returned. **A turn ends when the brain stops emitting, not when the
audio finishes.**

## Hanging up

```
…
V→B  UserMessage{turn_id: 4, text: "that's all, thanks"}
B→V  SpeechStart{speech_id: 6, turn_id: 4}
B→V  SpeechChunk{speech_id: 6, text: "Thanks for stopping by. Bye!"}
B→V  SpeechEnd{speech_id: 6}
B→V  End{}
```

`End` is a graceful close from either side, and it carries nothing.

- **From the brain** it means hang up once everything already sent has played.
  Speak the goodbye, then send `End`, and the goodbye is heard. The reason
  belongs in the brain's own logs, not on the wire.
- **From Voqalize** it means the call is over: the user hung up, or the session
  ended on Voqalize's side.

`End` needs no turn. It is one of the **floor-free** messages, legal at any
moment, which the next sections add to.

**A minimal brain is complete here.** It reads `SessionStart`, `UserMessage` and
`Finalize`, sends speech units and `End`, and holds a whole conversation. Every
message from here on refines that call. A brain that ignores them still works:
speech it sends for a turn the user has already talked over is dropped, because
[a unit that names a dead turn plays nothing](#barge-in).

## Silence

```
…
B→V  SpeechEnd{speech_id: 3}
V→B  Finalize{speech_id: 3, heard_text: "Yes, there are two left in large."}
                                                   … the user says nothing …
V→B  UserIdle{turn_id: 3, level: 1, idle_ms: 15000}
B→V  SpeechStart{speech_id: 4, turn_id: 3}
B→V  SpeechChunk{speech_id: 4, text: "Shall I add one to your cart?"}
B→V  SpeechEnd{speech_id: 4}
```

`UserIdle{turn_id, level, idle_ms}` says the human has been silent past the
configured idle timeout, and gives the brain the floor to re-engage. It is a new
turn, minted like a `UserMessage`.

- `level` counts consecutive escalations with no intervening speech, `1` being
  the first nudge. It resets when the user speaks, so a brain can say something
  different the third time.
- `idle_ms` is the silence elapsed since Voqalize stopped speaking, when it
  fired.

The brain may also say nothing: a turn is a permission, not an obligation. The
timeout is set by `idle.timeout_ms`, at connect or
[mid-session](#changing-the-call-mid-session), and `0` disables idle detection.

## Barge-in

```
…
V→B  UserMessage{turn_id: 5, text: "what's your return policy"}
B→V  SpeechStart{speech_id: 7, turn_id: 5}
B→V  SpeechChunk{speech_id: 7, text: "You can return anything within thirty days, "}
B→V  SpeechChunk{speech_id: 7, text: "as long as the tags are still on and"}
                                                   … the user talks over it …
V→B  Interruption{through_turn: 5}
V→B  Finalize{speech_id: 7, heard_text: "You can return anything"}
V→B  UserMessage{turn_id: 6, text: "what about sale items"}
B→V  SpeechStart{speech_id: 8, turn_id: 6}
…
```

The human speaks over the bot. Voqalize stops the audio and sends
`Interruption{through_turn}`, and that is a **watermark**: everything up to and
including that turn is dead, the user will not hear it, and the brain stops
generating for it.

The watermark travels one way. Nothing is sent back, nothing is acknowledged,
and Voqalize waits for nothing; it has already stopped the audio. Recording it
is `watermark = max(watermark, through_turn)`, which makes a repeat harmless and
a missed one self-correcting: the next watermark carries a higher number and
covers it.

Nothing lowers a watermark. A turn above it simply outranks it, so the brain
never has to reopen anything: the next `UserMessage` mints a higher turn, and
speech on that turn is live by construction.

**How it meets `Finalize`:**

- **The cut units are still finalized.** Every unit the brain opened on a dead
  turn gets its one `Finalize`, and its `heard_text` is the prefix that played
  before the cut. Above, unit 7 reports "You can return anything", which is
  what goes into the model's history.
- **A unit on a dead turn plays nothing.** A `SpeechStart` that names a turn at
  or below the watermark is dropped, so a brain that is slow to notice loses
  nothing but the work.
- **No `SpeechEnd` is owed for a cut unit.** The Python SDK sends nothing more
  for it once the `Interruption` arrives, and its `Finalize` closes it.

The trace shows the usual order, but do not depend on the `Finalize` arriving
after the `Interruption`: match each `Finalize` to its unit by `speech_id`.

## Taking speech back

```
…
V→B  SessionStart{…, capabilities: [CAPABILITY_SPEECH_CANCEL, CAPABILITY_STRING_CONFIG, CAPABILITY_TURN_STEPS]}
…
V→B  UserMessage{turn_id: 7, text: "how do I find a number in a sorted list"}
B→V  SpeechStart{speech_id: 9, turn_id: 7}
B→V  SpeechChunk{speech_id: 9, text: "Good question. One approach is "}
B→V  SpeechChunk{speech_id: 9, text: "to use binary search on…"}   ← the guardrail flags this
B→V  SpeechCancel{speech_id: 9}                               ← closes unit 9; no SpeechEnd
V→B  Finalize{speech_id: 9, heard_text: "Good question."}
B→V  SpeechStart{speech_id: 10, turn_id: 7}                   ← same turn, still open
B→V  SpeechChunk{speech_id: 10, text: "Let's think about it differently."}
B→V  SpeechEnd{speech_id: 10}
V→B  Finalize{speech_id: 10, heard_text: "Let's think about it differently."}
```

`SpeechCancel{speech_id}` is the brain's own cut. A guardrail running beside the
model flags text that has already been sent; the brain stops its model, sends
`SpeechCancel`, and Voqalize drops whatever of that unit has not played.

**The answer is the unit's `Finalize`, and nothing else.** Voqalize already owes
every unit exactly one, so there is no acknowledgement message: its
`heard_text` says how far playout got, and comparing it with what you sent says
whether the cut landed in time.

**It is not a barge-in.** No `Interruption` is sent, the watermark does not
move, and the turn stays open: the brain may open a new unit on the same
`turn_id` straight away, and that unit plays. `SpeechCancel` is floor-free.

| When the cancel arrives | What comes back |
|---|---|
| The unit is open, or closed and still playing or queued | Its `Finalize`, once the cut has happened: milliseconds |
| Before any of it was spoken | Its `Finalize` with empty `heard_text` |
| After its `Finalize` was sent, or a second time | Nothing: the one `Finalize` has already gone |
| Naming `0` or a unit this session never opened | A non-fatal `ERROR_CODE_PROTOCOL` `Error`; the call continues |
| At a Voqalize that does not list the capability | Nothing; the unit plays out and its `Finalize` carries the full text |

Socket order decides every race. A chunk sent before the cancel is part of what
was cut. A `SpeechChunk` or `SpeechEnd` for the unit after it is **ignored, not
an error**, because a model may still be streaming when the guardrail decides.
A cancel and a barge-in arriving together converge: each unit still gets
exactly one `Finalize`, and the barge-in's `Interruption` kills the turn as
usual.

Today the cut is the whole floor, not one unit. Every unit still playing or
queued when the cancel arrives is stopped, an earlier unit of the same reply
included, and so is a later one still open, whose further chunks and `SpeechEnd`
are ignored the same way. Each gets its own truthful `Finalize`, oldest first.
A unit opened after the cancel plays. Stopping your model is still your job:
Voqalize can only drop text it is sent.

### Capabilities

`SpeechCancel` is the first message here that a Voqalize may not honour, and
`SessionStart.capabilities` is how a brain knows. It lists what this Voqalize
honours beyond the version's baseline. A message added within a version is
skipped, not refused, by a Voqalize that predates it, so a brain that sent one
would see nothing happen and could not tell *ignored* from *too late*. The list
says up front.

```proto
enum Capability {
  CAPABILITY_UNSPECIFIED = 0;
  CAPABILITY_SPEECH_CANCEL = 1;  // SpeechCancel is honoured
  CAPABILITY_STRING_CONFIG = 2;  // voice_id and language_tag are read
  CAPABILITY_TURN_STEPS = 3;     // TurnStep is recorded
}
```

| Capability | Means |
|---|---|
| `CAPABILITY_SPEECH_CANCEL` | `SpeechCancel` stops a unit and is answered by its `Finalize`. See [taking speech back](#taking-speech-back). |
| `CAPABILITY_STRING_CONFIG` | `TtsConfig.voice_id`, `TtsConfig.language_tag` and `SttConfig.language_tag` are read. Without it they are ignored, and a request carrying only them is answered accepted with nothing changed. See [changing the call mid-session](#changing-the-call-mid-session). |
| `CAPABILITY_TURN_STEPS` | `TurnStep` is recorded beside its turn. See [what a turn did](#what-a-turn-did). |

Check before sending an optional message, and treat a value you do not
recognise as absent. Adding a capability is append-only and does not move the
version. The Python SDK reads them as `session.can_cancel_speech`,
`session.can_configure_strings` and `session.can_report_steps`, and refuses the
call locally when the one it needs is false.

## The screen

```
…
V→B  UserMessage{turn_id: 8, text: "show me the blue one"}
B→V  RTVIFrame{type: RTVI_TYPE_UI_COMMAND, data: "{\"command\":\"show_product\",\"payload\":{\"color\":\"blue\"}}", turn_id: 8}
B→V  SpeechStart{speech_id: 11, turn_id: 8}
B→V  SpeechChunk{speech_id: 11, text: "Here it is."}
B→V  SpeechEnd{speech_id: 11}
V→B  Finalize{speech_id: 11, heard_text: "Here it is."}
V→B  RTVIFrame{type: RTVI_TYPE_UI_EVENT, data: "{\"event\":\"size_selected\",\"payload\":{\"size\":\"L\"}}"}
                                                   … the user types "add it to my cart" …
V→B  UserMessage{turn_id: 9, text: "add it to my cart"}
```

Everything so far is the **voice plane**, and it is Voqalize's: turns, speech
units, what the user actually heard, and (later) the control leg. Voqalize mints
the turn because Voqalize decides when a turn commits, and speech names the turn
it answers.

The **RTVI plane is a tunnel.** An `RTVIFrame` is one RTVI message
(the format your page and your brain share over the session's data channel),
`{id, label: "rtvi-ai", type, data}` minus the constant label, forwarded
verbatim in both directions between the app and the brain. Voqalize moves the
whitelisted types and interprets nothing else about them. Actions,
[Stage](/build/stage/) moves and the page's answers, and
[avatar gestures](/build/avatar/#gestures-from-your-brain) all ride this plane.

```proto
message RTVIFrame {
  RTVIType        type    = 1;
  string          data    = 2;  // JSON-encoded, opaque
  optional string id      = 3;
  optional uint64 turn_id = 4;
}
```

- `data` is the RTVI payload, opaque and bounded by the client's 64 KiB message
  limit.
- `id` is RTVI's own correlation id, present on requests and quoted back on the
  message that answers one.
- `turn_id` annotates traces, is set only brain→Voqalize, and never reaches the
  app.

**The planes share the socket and nothing else.** A message on the RTVI plane
never mints a turn, never takes the floor, and never changes what the user
hears. An `RTVIFrame` from the app does not mint a turn: the app tapping a button
is not the app taking the floor. An `RTVIFrame` from the brain is floor-free and
legal at any moment.

**`type` is a closed whitelist**, and which side may originate it is part of the
type. Each `RTVI_TYPE_*` value in the proto is the RTVI type string in kebab
case: `RTVI_TYPE_UI_COMMAND` is `ui-command` in the app.

| Direction | Types |
|---|---|
| Brain → Voqalize → app | `server-message`, `server-response`, `error-response`, `ui-command`, `ui-job-group` |
| App → Voqalize → brain | `ui-event`, `client-message` (deprecated), `ui-snapshot`, `ui-cancel-job-group` |

- `ui-command` is an action, `{"command": …, "payload": {…}}`, and what Stage's
  moves ride. `ui-job-group` carries lifecycle envelopes for a group of jobs.
- `ui-event` is a named event from the page, `{"event": …, "payload": …}`, and
  carries Stage's results and state. `ui-snapshot` is the page's accessibility
  tree. `ui-cancel-job-group` cancels a job group.
- `server-message` is an unsolicited message to the app; avatar gestures are
  server messages. `server-response` and `error-response` answer a message the
  app sent, quoting its `id`.
- `client-message` is the older untyped envelope. It still crosses and still
  parses; new pages send `ui-event`.

`send-text` is on the app's half of the whitelist and is not in that table on
purpose: it is the one type that does not cross as a message. A typed sentence
takes the floor the way a spoken one does, so Voqalize commits it as a **user
turn**, interrupting whatever the agent was saying. It reaches your brain as a
`UserMessage`, and your brain never sees an `RTVIFrame` for it. In the trace,
"add it to my cart" was typed. See [RTVI messages](/reference/rtvi/).

A type absent from the whitelist does not cross in either direction. `bot-*` and
`llm-*` are Voqalize's own assertions about the media and the model, and a
brain must not be able to forge them. A brain that sends one, or sends a payload
over 64 KiB, gets a **non-fatal `ERROR_CODE_PROTOCOL` `Error`** and the frame is
dropped. The call continues; see [error codes](/reference/errors/).
`RTVI_TYPE_UNSPECIFIED` is never sent, and an envelope carrying it is rejected.

## Changing the call mid-session

```
…
V→B  UserMessage{turn_id: 10, text: "can we speak in Hindi"}
B→V  Request{request_id: 1, configure: {tts: {language_tag: "hi"}, stt: {language_tag: "hi"}}}
V→B  Response{request_id: 1, status: STATUS_ACCEPTED}
B→V  SpeechStart{speech_id: 12, turn_id: 10}
B→V  SpeechChunk{speech_id: 12, text: "ज़रूर, अब हिंदी में बात करते हैं।"}
B→V  SpeechEnd{speech_id: 12}
…
B→V  Request{request_id: 2, configure: {tts: {voice_id: "omnivoice/nobody"}}}
V→B  Response{request_id: 2, status: STATUS_REJECTED, code: ERROR_CODE_UNSUPPORTED_VOICE, detail: "…"}
```

### The control leg

The brain asks Voqalize to change how the call behaves, and learns whether the
ask was any good.

```proto
message Request {
  uint64 request_id = 1;
  oneof op { Config configure = 2; }
}
message Response {
  uint64    request_id = 1;
  Status    status     = 2;
  string    detail     = 3;
  ErrorCode code       = 4;
}
```

`request_id` is brain-minted and session-monotonic; its whole job is to name the
`Response`. **Exactly one `Response` comes back for every `Request`, on every op,
always**, so a brain awaiting one never has to know which ops answer. `configure`
is the one op today; the `oneof` is there so adding another does not change the
shape of this one. A `Request` is floor-free.

`status` is `STATUS_ACCEPTED` or `STATUS_REJECTED`, and it reports **whether
Voqalize took the request, not whether the effect is audible yet**. `detail`
says why on a rejection and is empty otherwise, and it is written to be shown.
`code` is the same reason by kind, set on a rejection:

| `code` | Rejected because |
|---|---|
| `ERROR_CODE_UNSUPPORTED_VOICE` | No voice by that id is served. |
| `ERROR_CODE_UNSUPPORTED_LANGUAGE` | The voice does not speak the language, the recognizer does not hear it, or the tag is malformed. |
| `ERROR_CODE_INVALID_REQUEST` | Anything else: a language on one leg only, a patience off the scale, or one setting given both as a string and as an enum. |

It is unset on acceptance, and from a Voqalize that predates the field.

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

message TtsConfig {
  optional Voice    voice        = 1 [deprecated = true];
  optional Language language     = 2 [deprecated = true];
  optional string   voice_id     = 3;  // "omnivoice/gauri"
  optional string   language_tag = 4;  // BCP-47, "ta"
}
message SttConfig {
  optional Language language     = 1 [deprecated = true];
  optional uint32   patience     = 2;  // 0 to 10
  optional string   language_tag = 3;  // BCP-47, "ta"
}
message IdleConfig { optional uint32 timeout_ms = 1; }
message AckConfig  { optional bool enabled = 1; }
```

This message is used twice: `sessions.connect` supplies the starting sections,
and the brain sends the same shape in this op while the call is running. The
agent record carries none of it. See
[Voice and language](/build/voice-and-language/).

Name a voice by `voice_id` and a language by `language_tag`, which need
`CAPABILITY_STRING_CONFIG`. The enum fields `TtsConfig.voice`,
`TtsConfig.language` and `SttConfig.language` are deprecated and still parse.
Set at most one of the two spellings for a setting, or the request is rejected
with `ERROR_CODE_INVALID_REQUEST`. A tag matches by its primary subtag,
case-insensitively, so `en-IN` is `en`. The values are in
[the catalog](/reference/catalog/).

Unset means *leave it alone*: a `Request` carries a delta and the call is
already running. Explicit presence is what makes that readable. Without it an
unset `timeout_ms` is indistinguishable from `0`, and a delta that never
mentioned idle detection would silently disable it. At `sessions.connect`, unset
means take Voqalize's default.

**One op, not one per section.** A language change has to move both legs at
once. Separate ops would put a turn boundary, and a possible refusal, between
the halves, leaving the call heard in one language and spoken in another.

The surface is deliberately narrow: the voice, the language on each leg, how
long the recognizer waits through a pause, the idle timeout, and whether
Voqalize acknowledges the user. The recognizer's other thresholds are not
settable, and recording is fixed when the session starts.

### When each change lands

| Change | Effective | Why |
|---|---|---|
| `tts` | the next speech unit | The synthesizer locks the voice for one synthesis context and Voqalize pins one context per unit, so the sentence being spoken finishes in the old voice. |
| `stt.language` | once the open turn commits | The recognizer carries per-turn decoder state, so the turn being spoken when the change arrives still transcribes as spoken. |
| `stt.patience` | immediately | It bounds a silence counter that resets at every word, so there is nothing in flight for it to corrupt, including the pause already running. |
| `ack` | the next turn | The acknowledgement is chosen when a turn ends, so a turn already answered keeps what it had. |
| `idle` | immediately | Voqalize owns that timer; one already running restarts on the new duration. `timeout_ms` is the silence after Voqalize stops speaking before it mints an idle turn, and `0` disables idle detection. |

### `ack` — Voqalize acknowledges while the brain thinks

When the user's turn ends and the brain has not started its reply, Voqalize can
say a short line of its own, such as "Let me check." or "Sure.", chosen from
what the user said. Where nothing fits, or the call's language has no
acknowledgement vocabulary, it says nothing. This line is not on the wire: the
brain sees no message for it.

**It is on unless the session turns it off.** `enabled: false` at
`sessions.connect` turns it off for one call; the brain can turn it off, or back
on, with this op at any time. A brain that opens its replies with its own nod
should turn it off, or the user hears two. When to turn it off is in
[Voice and language](/build/voice-and-language/).

### Both legs carry a language, and both must be set

A language appears on `TtsConfig` and on `SttConfig`, and that is not
duplication. The recognizer serves English, the European languages and the
Indic languages; a voice speaks the subset it was recorded or trained for,
which is smaller and differs from voice to voice. So the legs genuinely differ
(a call understood in Assamese is spoken in the voice's Hindi) and one field could
not say so.

The rules that follow are enforced in different places on purpose:

- **Name a language on one leg and you must name it on the other.** Not that
  they agree: that you stated both. Moving one alone is the silent failure:
  the words stay right and only the voice is wrong, which no transcript, no WER
  number and no automated check will ever show you. This is a property of the
  message itself, so the SDK refuses to build it, before the request leaves.
- **A `tts` language the chosen voice does not speak is rejected**, rather
  than served in another language. That one is not in the message; it is a
  property of the voices Voqalize serves, and it changes as voices are added and
  recorded. So it comes back as a `STATUS_REJECTED` `Response` with
  `ERROR_CODE_UNSUPPORTED_LANGUAGE`, naming the languages that voice does speak.

Write what you are actually getting:

```proto
stt { language_tag: "as" }   // listen in Assamese
tts { language_tag: "hi" }   // speak in Hindi
```

Changing only the voice touches no language field and is unaffected by either
rule.

### Waiting through a pause (`stt.patience`)

`patience` is a scale from 0 to 10, not a duration: `0` answers as soon as the
recognizer can, `10` lets a user finish a sentence they are still assembling.
Unset runs the deployment's calibration, which is patience 7; nothing writes a
`7` onto the wire.

A patience off the scale is refused at whichever door it arrives at, in the same
words: `invalid_config` at `sessions.connect`, so the call never starts, and a
`STATUS_REJECTED` `Response` mid-call, so the session keeps the patience it had.
The Python SDK raises `ConfigError` before either, when you build the
`SttConfig`.

### The catalog

A voice is a `voice_id` string, the id Voqalize serves it under, and its
prefix picks the engine. A language is a BCP-47 `language_tag`. Neither is a
list fixed in the proto, so a voice or language Voqalize adds needs no
wire release; one it does not serve is refused.

The deprecated `Voice` and `Language` enums are frozen. Each `Voice` value
carries its id as the `voice_id` option, and each `Language` value carries its
tag as the `iso_code` option:

```proto
extend google.protobuf.EnumValueOptions {
  optional string iso_code = 50001;
  optional string voice_id = 50002;
}

enum Language {
  LANGUAGE_UNSPECIFIED = 0;              // leave the language alone
  LANGUAGE_EN = 1 [(iso_code) = "en"];
  LANGUAGE_OR = 16 [(iso_code) = "or"];
  // …
}
```

Which voice speaks which language is Voqalize's to say, not the wire's. See
[the catalog](/reference/catalog/), which is also public JSON at
`GET https://app.voqalize.com/api/v1/catalog.get`.

## Tools and turn accounting

```
…
V→B  UserMessage{turn_id: 11, text: "show me your pricing"}
B→V  SpeechStart{speech_id: 13, turn_id: 11}
B→V  SpeechChunk{speech_id: 13, text: "Opening pricing."}
B→V  SpeechEnd{speech_id: 13}
B→V  RTVIFrame{type: RTVI_TYPE_UI_COMMAND, data: "{\"command\":\"open_section\",…}", turn_id: 11}
B→V  TurnStep{turn_id: 11, kind: "tool", name: "open_section", start_ms: 610, duration_ms: 40}
B→V  TurnStep{turn_id: 11, kind: "model", name: "gpt-6-sol", provider: "openai", start_ms: 0, duration_ms: 900, counts: {…}}
B→V  SpeechStart{speech_id: 14, turn_id: 11}
B→V  SpeechChunk{speech_id: 14, text: "There are monthly and yearly plans."}
B→V  SpeechEnd{speech_id: 14}
B→V  TurnStep{turn_id: 11, kind: "model", name: "gpt-6-sol", provider: "openai", start_ms: 900, duration_ms: 600, counts: {…}}
```

**There is no tool-call message.** Your model, its tools and its prompts live in
your brain, and Voqalize never sees a tool called or a result returned. What
crosses the wire is the tool's *effect*: speech the brain says, or an
`RTVIFrame` that moves the screen. A tool is recorded only if the brain reports
it, with `TurnStep`.

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

**A turn is the steps that name it.** In the trace the visitor asks to see
pricing, and the brain asks its model, which calls `open_section`, then asks
again with the result and speaks. Those are the steps below, all on one
`turn_id`:

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
result, no query text, nothing the user said. Steps are kept in the call
record, and the record of a call is not the place for its words.

**Counts, never prices.** A price changes on a date nobody here controls, so cost
is computed from the counts by whoever reads them.

**`provider` is whoever's meter ran.** `openai`, `google`, `anthropic`, never a
router or gateway in between, so steps from different brains add up by company.

At a Voqalize that does not list `CAPABILITY_TURN_STEPS`, the message is
skipped. A brain that checks first sends nothing that will not be kept.

## Failure

```
V→B  SessionStart{turn_id: 1, wire_version: 4, …}
B→V  Error{code: ERROR_CODE_WIRE_VERSION, message: "…", fatal: true}
B→V  End{}
```

`Error{code, message, fatal}` says something went wrong, from either side.
Fatal or not, it is reported rather than swallowed. `message` is for the
developer reading the log. `fatal` means the session is ending; a non-fatal
error is informational, a signal the brain may act on, and the call continues.

| `ErrorCode` | Means |
|---|---|
| `ERROR_CODE_UNSPECIFIED` | Never sent; proto3 requires a zero value. |
| `ERROR_CODE_PROTOCOL` | A malformed or unexpected message: a type the brain may not send on the RTVI plane, a payload over 64 KiB, a `SpeechCancel` naming a unit the session never opened. Voqalize drops it and the call continues. |
| `ERROR_CODE_WIRE_VERSION` | The two ends do not speak the same wire. Fatal; see [version](#version). |
| `ERROR_CODE_REJECTED` | Defined as "not permitted on the RTVI plane, or oversized". Nothing sends it today: those come back as `ERROR_CODE_PROTOCOL`. |
| `ERROR_CODE_OVERLOAD` | Dropped under congestion. The Python SDK raises it to its own `on_error` when its queue sheds frames; it does not cross the wire. |
| `ERROR_CODE_INTERNAL` | Our side failed: a bug, or a fault in a service or provider we depend on that did not clear. Never the caller's mistake. |
| `ERROR_CODE_UNSUPPORTED_VOICE` | A `Response` code: no voice by that id is served. |
| `ERROR_CODE_UNSUPPORTED_LANGUAGE` | A `Response` code: the voice does not speak the language, the recognizer does not transcribe it, or the tag is malformed. |
| `ERROR_CODE_INVALID_REQUEST` | A `Response` code: any other fault in a request. |

What raises each one in practice, and how the SDK surfaces it, is in
[error codes](/reference/errors/).

`Cancel{reason}` is the abrupt close: abandon the session now, without waiting
for pending audio. `reason` is for the log, and empty is legal. The SDK never
sends it, so a brain that emits `Cancel` toward Voqalize is one written directly
against the wire. `End` is the graceful one.

### Version

`SessionStart.wire_version` is the version Voqalize speaks. **This is
version 3.**

A brain whose build speaks a different version refuses the session outright: a
fatal `ERROR_CODE_WIRE_VERSION` `Error`, then `End`, before it has greeted.
Voqalize speaks first, so that is the last moment either end can refuse and the
only one where refusing is free: nothing has been synthesized and the user has
heard nothing.

The comparison is `!=`, not `<`. A lower version is not a subset of a higher
one; the arms it names may mean something else underneath it. Refusing in both
directions is what keeps that from being a guess.

The version gates behaviour, not parsing: protobuf ignores fields it does not
know without help. What a version buys is the ability to refuse rather than
guess.

## Reference

### Framing

Binary WebSocket messages only; a text message is an error.

| Leg | Layout |
|---|---|
| Your inbound server, at `{brain_url}?session_id={session_id}` | `[Envelope]` |
| The Cortex relay, at `/agent` | `[16-byte session_id][Envelope]` |

One message carries one envelope and nothing around it. Nothing frames it,
lengths it, or tags it: the WebSocket already delimits messages, and the
envelope already says what it is.

The 16-byte prefix on the relay leg is how one socket carries many sessions.
Cortex adds it inbound and strips it outbound, and it is the only difference
between the legs: the same brain code serves both.

### Connection and auth

Voqalize dials `{brain_url}?session_id={session_id}`, presenting **the
brain-connection token**: a short-lived RS256 JWT, sent as a bare token or as
`Authorization: Bearer <jwt>` and verified against Voqalize's public key.
Required claims: `iss="pygato"`, `aud="brain"`, `sub == session_id`, and `exp`.
`agent_id` and `tenant_id` are informational: the recipient decides from them
whether it serves this agent.

The path is yours and is used verbatim; the session rides as a query parameter.
A brain is therefore one ordinary WebSocket route rather than a wildcard path
segment you have to carve out.

`aud` is the constant `"brain"` for every brain. Routing lives in the
`brain_url`, never in the token.

**The socket is the session, and it is not reconnected.**

| What happens | What Voqalize does |
|---|---|
| The dial fails: connection refused, TLS error, or a `401` or `403` at the HTTP handshake | Retries, from 100 ms with backoff, for up to **10 seconds** from the first attempt. Then the session ends as `brain_unreachable` and the user hears [the unreachable line](/reference/errors/#what-your-user-hears). |
| Your brain closes the open socket, with any code | The session ends at once. `1000` reads as `agent_hung_up`; any other code, including **4000** after a failed token check, as `brain_disconnected`. |

A rejected token is therefore best refused after the upgrade, with **4000**: a
`401` at the handshake is retried for the whole window first. Nothing reconnects
an open session, because a second connection would reach a brain with none of
the first one's state.

### Voqalize → brain

| Message | Fields | Meaning |
|---|---|---|
| `SessionStart` | `turn_id`, `session_id`, `init` *(JSON)*, `wire_version`, `capabilities` | First envelope of the session, and its first turn. See [one socket, one envelope](#one-socket-one-envelope). |
| `UserMessage` | `turn_id`, `text` | The human finished an utterance. A new turn: the floor is the brain's. |
| `UserIdle` | `turn_id`, `level`, `idle_ms` | The human has been silent past the configured timeout. Also a new turn. See [silence](#silence). |
| `Interruption` | `through_turn` | Everything up to and including `through_turn` is dead; the user will not hear it. Stop generating for it. See [barge-in](#barge-in). |
| `Finalize` | `speech_id`, `heard_text` | What the human actually heard of one speech unit. See [what was heard](#what-was-heard). |
| `Response` | `request_id`, `status`, `detail`, `code` | The answer to one `Request`. See [the control leg](#the-control-leg). |
| `RTVIFrame` | `type`, `data` *(JSON)*, `id` | The app said something. Delivered verbatim; Voqalize never decides whether it deserves a reply. |
| `End` | — | The call is over. |
| `Cancel` | `reason` | The call is being torn down abruptly. |
| `Error` | `code`, `message`, `fatal` | Something went wrong. `fatal` means the session is ending. |

### Brain → Voqalize

| Message | Fields | Meaning |
|---|---|---|
| `SpeechStart` | `speech_id`, `turn_id` | Open a unit of speech, on the turn it answers. |
| `SpeechChunk` | `speech_id`, `text` | Text to speak, inside an open unit. Stream them as they are produced. |
| `SpeechEnd` | `speech_id` | Close the open unit. |
| `SpeechCancel` | `speech_id` | Stop one unit now and close it. Answered by that unit's `Finalize`, and nothing else. Honoured when `SessionStart` lists `CAPABILITY_SPEECH_CANCEL`. |
| `RTVIFrame` | `type`, `data` *(JSON)*, `id`, `turn_id` | Drive the screen. Relayed to the app unread. |
| `TurnStep` | `turn_id`, `kind`, `name`, `provider`, `start_ms`, `duration_ms`, `first_output_ms`, `counts` | One piece of work the brain did for a turn. Recorded, never acknowledged. Honoured when `SessionStart` lists `CAPABILITY_TURN_STEPS`. See [what a turn did](#what-a-turn-did). |
| `Request` | `request_id`, one `op` | Change how the call behaves; today `configure`. Answered by exactly one `Response`. |
| `End` | — | Hang up, once everything already sent has played. |
| `Cancel` | `reason` | Tear down abruptly. |
| `Error` | `code`, `message`, `fatal` | Something went wrong on this side. |

Fields marked *(JSON)* travel as a JSON-encoded string and arrive as a dict in
the SDK. The wire has no `Struct` dependency; opaque payloads stay opaque.

### What the SDK makes of it

The [Python SDK](/reference/brain/) mints every `speech_id` and `request_id`
and binds speech to its `turn_id` for you; its callbacks and methods map one to
one onto the messages above, listed in
the [Brain API](/reference/brain/#how-the-sdk-maps-onto-the-wire).

### Invariants

Both ends rely on these, and a brain that implements the wire directly owes them:

- **`SessionStart` is first**, and nothing goes the other way before it.
- **Brackets balance.** Every `SpeechStart` is closed by a `SpeechEnd` or a
  `SpeechCancel`; a `SpeechChunk` outside an open unit is an error. A
  `SpeechCancel` after the unit's `SpeechEnd` is legal (it cuts a unit still
  playing), and a `SpeechChunk` or `SpeechEnd` after its `SpeechCancel` is
  ignored. A unit an `Interruption` cut is closed by its `Finalize`; the Python
  SDK sends no `SpeechEnd` for it.
- **One `speech_id` per unit**, on every message of that unit, brain-minted and
  never reused.
- **Speech names its turn.** Every `SpeechStart` carries the `turn_id` of the
  stimulus it answers, and only Voqalize mints one.
- **The interruption watermark is one-way**: never acknowledged, never
  echoed, never lowered.
- **Exactly one `Response` per `Request`**, matching on `request_id`.
- **Nothing is emitted outside a turn except floor-free messages**:
  `RTVIFrame`, `Request`, `SpeechCancel`, `TurnStep`, `End`, `Cancel`, `Error`.
- **`heard_text` is the delivered prefix**, per unit, never a concatenation,
  and a verbatim prefix of that unit's own text.
- **Exactly one `Finalize` per bracket the brain opened**, in that order,
  including for a unit that turned out silent, which reports nothing heard, and
  for a unit the brain cancelled, which reports what played before the cut.
  A brain cannot know in advance which of its units will be silent, and an
  absent report is indistinguishable from a late one.

### Changing the wire

The schema is append-only within a version.

- Field numbers are never reused; a retired one is `reserved`.
- `Envelope` arms are never renumbered.
- A message is reserved rather than removed.
- Adding a field or an arm **does not** bump the version.
- A bump means the ends no longer speak the same wire, and it is meant to be
  rare.
