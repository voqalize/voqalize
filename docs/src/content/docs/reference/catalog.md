---
title: Voice & language catalog
description: The recognizer languages and TTS voices a session can select, and how a brain moves them.
---

Every session starts from the configuration supplied to `sessions.connect`,
resolved over Voqalize's defaults — English on both legs when nobody says
otherwise. The brain may change the recognizer language, speaking voice and idle
timeout while the call runs. This page is the catalog of allowed values, and the
one rule that makes them safe to change.

:::caution[Set both legs of a language, always]
`stt.language` picks the **recognizer**. `tts.language` picks the language the
voice reads in — which, for a cloned voice, is a different recorded speaker.
They are one setting with a leg each way, so the SDK requires both together and
refuses a configuration that names a language on one leg alone:

```python
from voqalize.sdk.wire import Config, Language, SttConfig, TtsConfig, Voice

async def on_session_start(self, session):
    await session.configure(
        Config(
            stt=SttConfig(language=Language.TA),
            tts=TtsConfig(language=Language.TA, voice=Voice.OMNIVOICE_GAURI),
        )
    )
```

One request, with optional `tts`, `stt` and `idle` sections, because a language
change has to move both legs at once. The same call switches language mid-call.

**A half-applied language is silent.** The words stay right and only the speaker
is wrong, so every transcript, log and automated score is blind to it — see
[Why both halves](#why-both-halves-matter) below.
:::

## Speech-to-text

### Model

There is no model to choose, and no field in which to choose one. Every session
is served by the same **recognizer**: a composite that covers **English plus 22
Indic languages** and picks the engine underneath from the language you set. A
brain names a language; it never names an engine.

### Language (`stt.language`)

The recognizer serves **English (`en`)** plus these 22 Indic languages:

| Code | Language | Code | Language | Code | Language |
|---|---|---|---|---|---|
| `as` | Assamese | `bn` | Bengali | `brx` | Bodo |
| `doi` | Dogri | `kok` | Konkani | `gu` | Gujarati |
| `hi` | Hindi | `kn` | Kannada | `ks` | Kashmiri |
| `mai` | Maithili | `ml` | Malayalam | `mr` | Marathi |
| `mni` | Manipuri | `ne` | Nepali | `or` | Odia |
| `pa` | Punjabi | `sa` | Sanskrit | `sat` | Santali |
| `sd` | Sindhi | `ta` | Tamil | `te` | Telugu |
| `ur` | Urdu | | | | |

These are the members of the `Language` enum, so a language outside the set is
not a value you can send — it is a value you cannot construct. That is the point:
the old failure mode was an unserved code falling through to the English
recognizer, in a call nobody could tell had gone wrong.

A language change that crosses the English↔Indic boundary is applied at the
**next end-of-turn**, never mid-utterance.

There are no VAD or end-of-turn knobs on the wire. Voqalize keeps its own
tuned defaults; we widen the surface as we learn, not in advance.

## Text-to-speech

### Voice (`tts.voice`)

<!-- voices:begin -->
| `Voice` | Voice ID | Sounds like | Speaks |
|---|---|---|---|
| `Voice.KOKORO_AVA` | `kokoro/ava` | Ava (American female) | `en` |
| `Voice.KOKORO_EMMA` | `kokoro/emma` | Emma (British female) | `en` |
| `Voice.KOKORO_LEO` | `kokoro/leo` | Leo (American male) | `en` |
| `Voice.KOKORO_NOAH` | `kokoro/noah` | Noah (American male) | `en` |
| `Voice.KOKORO_OLIVER` | `kokoro/oliver` | Oliver (British male) | `en` |
| `Voice.KOKORO_SARAH` | `kokoro/sarah` | Sarah (American female) | `en` |
| `Voice.OMNIVOICE_GAURAV` | `omnivoice/gaurav` | Gaurav (male) | `bn`, `en`, `gu`, `hi`, `kn`, `ml`, `mr`, `pa`, `ta`, `te` |
| `Voice.OMNIVOICE_GAURI` | `omnivoice/gauri` | Gauri (female) | `bn`, `en`, `gu`, `hi`, `kn`, `ml`, `mr`, `pa`, `ta`, `te` |
<!-- voices:end -->

**That table is not written by hand.** Voqalize's speech tier publishes the
voices its running process has loaded, and this page is generated from that
roster — so a voice that exists here exists on the call, and one that does not
cannot be quietly advertised for weeks.

There is no separate model field. The engine is chosen entirely by the prefix on
the voice id, and that prefix is the only engine selector there is — on the
wire, in the SDK or in the agent record.

### Language (`tts.language`)

`tts.language` is **not a text tag**, and what it means depends on the voice —
which is why the table above states it per voice rather than once for all of
them:

- A **cloned** voice is re-recorded for each language it speaks.
  `omnivoice/gauri` speaking `hi` and `omnivoice/gauri` speaking `en` are two
  different recorded speakers.
- A voice whose accent comes from its **checkpoint** speaks the language that
  checkpoint was trained on, and no other. Asking one for a language it does not
  speak is not a mild request: there is no accent for it to reach for.

**A pairing the voice cannot speak is rejected**, not quietly served in the
wrong language. The rejection names the languages that voice does speak, so the
fix is in the message. The roster is today's, not a promise frozen into the wire
contract: it grows as voices are added and clips are recorded.

So an Odia call is a configuration you write down:

```python
Config(
    stt=SttConfig(language=Language.OR),   # understood in Odia
    tts=TtsConfig(language=Language.HI),   # spoken with the Hindi clip
)
```

That is a legitimate session, and it is why both legs keep their own `language`
field rather than sharing one. What is not legitimate is arriving at it by
accident.

## Why both halves matter

Each half fails on its own, quietly, in a different way:

| Half wrong | What you get | How you find out |
|---|---|---|
| `tts.language` | The right words in the wrong speaker — Hindi read by the English reference clip sounds like a non-native accent | **By ear only.** The words are correct, so transcription-based scoring is blind to it |
| `stt.language` | Whatever the user says is transcribed by the English recognizer | Garbled transcripts, blamed on the model |

The `tts.language` half is the reason this page leads with a rule instead of a
menu. A demo
shipped with Devanagari read in an English voice for weeks: every test was green,
every log line looked right, and every automated score was unchanged, because
none of them can hear.

The rules that kill it are checked in different places:

- **State both legs or neither.** Not that the legs agree — that you said both.
  Changing only the voice touches no language field and is unaffected. `Config`
  raises `ConfigError` on this one at the call site, before anything reaches
  the socket: it is a property of the request, so nothing needs to be asked.
- **No silent substitution.** A language the chosen voice does not speak is
  refused, so the Hindi fallback can only be something you asked for. Voqalize
  answers this one, because which voice speaks what is the speech tier's own
  record and it moves as voices are added — at connect if the configuration
  arrived there, and as a rejected response if your brain sent it mid-call.

## Where it is set

There is **one message**, `Config`, and it is set from either side. Whoever calls
`sessions.connect` sends it as proto3 JSON; your brain sends the same message as
a Python object with `session.configure(...)`. Same fields, same rules, same
rejections — a `config` block in an HTTP body and a `Config(...)` in a callback
are not two features to learn.

| Level | Who sets it | When |
|---|---|---|
| 1 | Voqalize's defaults | English on both legs, always |
| 2 | The session creator, in `config` at [connect](/build/session/) | Knows who is starting the call |
| 3 | Your brain, `await session.configure(Config(...))` | Knows how the call is going |

Later wins, and the brain always has the last word because `on_session_start`
runs after connect. STT applies at the next turn boundary, TTS at the next
speech unit, never mid-utterance.

The agent record holds a connection `mode`, a `brain_url` and a recording
default. It holds no voice,
language or idle setting — an agent-level language cannot depend on the user,
and `lead_qual` is the proof: it resolves a language from an enquiry form that
does not exist until the session starts.

A browser holding a publishable `pk_` may call `sessions.connect` directly and
set `tts`, `stt` and `idle`, subject to the same pairing and catalog rules. A
browser that asks its own backend to start the session supplies no Voqalize
configuration itself; the backend holding the `sk_` makes that request. The
separate recording rule is on [recordings](/operate/recordings/).

The `lead_qual` demo resolves its language per user and then switches mid-call
across Indic languages — a worked example of both rules.

## Why there is no provider slot

You arrived at the configuration surface looking for the field that says which
speech vendor runs the call. There is no such field, and this page is the reason.

### What a session configures

```python
from voqalize.sdk.wire import Config, IdleConfig, Language, SttConfig, TtsConfig, Voice

await session.configure(
    Config(
        stt=SttConfig(language=Language.TA),
        tts=TtsConfig(language=Language.TA, voice=Voice.OMNIVOICE_GAURI),
        idle=IdleConfig(timeout_ms=8000),
    )
)
```

What that sets: the recognizer's language, the speaking voice, the language that
voice reads in, and how long silence runs before the brain gets the floor back.

**`idle.timeout_ms` defaults to `0`, which is off.** A nudge nobody asked for
talks over a user who was thinking, so `on_user_idle` never fires until you
set a timeout. The ceiling is `300000` — past a few minutes the user has gone,
and the lever that helps is ending the session rather than nudging it. Setting
it back to `0` mid-call switches idle detection off again.

None of them names an engine. The comment above the `Voice` enum in
[`frames.proto`](https://github.com/voqalize/voqalize/blob/main/proto/voqalize/frames/frames.proto)
is the whole story:

> The engine is chosen by the voice — by the prefix on `voice_id` — and never by
> a model field; there is no engine knob on the wire.

### We run the speech tier ourselves

The recognizer covers English plus 22 Indic languages, and it runs on our own
GPUs. Text-to-speech runs there too: a voice-cloning model whose personas are
recorded per language, and English checkpoint voices that speak in the accent
they were trained in. Speech-to-text is a composite that reads the language and
routes to the engine underneath, which is why a brain never names one.

We run it because of the roster. Assamese, Bodo, Dogri, Konkani, Maithili,
Manipuri, Santali and Sindhi are the languages a hosted catalog tends to be short
of, and they are the ones our users speak. Running the tier is what puts them
in the enum.

### What the absence buys

**No engine knob exists** — on the wire, in the SDK, in the agent record, or per
environment. Two sessions cannot differ by an engine, so a change you hear
between one call and the next is a change we shipped, and we can name it.

**`Voice` and `Language` are protobuf enumerations**, so an unsupported value is
a value you cannot construct. The roster inside them is checked against what the
speech tier serves, so a voice reaches the enum when it reaches the GPU and not
on some other schedule. The failure that closes is an unserved language
code falling through to the English recognizer, in a call whose transcript reads
correctly and whose logs are clean — see
[why both halves matter](/reference/catalog/#why-both-halves-matter).

**There are no VAD or end-of-turn knobs either.** Recognizer routing, the voice
roster and the moment a turn commits are tuned together against the same calls.
A knob on one of them is a knob on the rest.

**No speech vendor key sits in your deployment**, and no speech vendor's outage
is a call you have to explain. When a voice sounds wrong, there is one place to
raise it.

### What it costs, plainly

A brain cannot point a session at another vendor's speech-to-text or
text-to-speech. If a particular commercial voice is the product — a brand voice
you have already licensed, a celebrity read, a language outside the roster — we
are the wrong voice tier for that call today, and a hosted speech vendor with
that voice is the right one.

The catalog is the table at the top of this page, and it is short. A product
whose premise is a wide cast of distinguishable speakers will run out of it.

### The shape a second engine would arrive in

New members of `Voice` and `Language` — which is exactly how the second one
arrived. Your brain changes by one identifier, the enum tells your editor what
exists, and a value your SDK version has never heard of stays unconstructable.
The wire shape is the commitment we are making here; the roster inside it is
what moves.

### What you do choose

The model, the prompt, the tools, the history and the turn — all of it in the
process you deploy, in whichever framework you brought. The engine that turns
your text into audio is the one thing on the call we hold, and the reason is that
we hold the GPUs it runs on.
