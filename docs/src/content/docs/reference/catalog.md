---
title: Voice & language catalog
description: The recognizer languages and TTS voices a session can select, and how a brain moves them.
---

Every session starts on the runtime's defaults — English on both legs — and
**the brain** sets the recognizer language and the speaking voice for *this*
caller. This page is the catalog of allowed values, and the one rule that makes
them safe to change.

:::caution[A language has two legs, and you set both]
`stt.language` picks the **recognizer**. `tts.language` picks the **reference
clip** — which recorded speaker the voice is cloned from. They are one setting
with two halves, so the SDK will not let you state one without the other:

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

One request, three optional sections — `tts`, `stt`, `idle` — because a language
change has to move both legs at once. The same call switches language mid-call.

**A half-applied language is silent.** The words stay right and only the speaker
is wrong, so every transcript, log and automated score is blind to it — see
[Why both halves](#why-both-halves-matter) below.
:::

## Speech-to-text

### Model

There is no model to choose. Every session is served by **`vql-stt`**, a
composite router covering **English plus 22 Indic languages**; it picks the
engine underneath from the language, and a brain never names an engine.

### Language (`stt.language`)

`vql-stt` serves **English (`en`)** plus these 22 Indic languages:

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

There are no VAD or end-of-turn knobs on the wire. The runtime keeps its own
tuned defaults; we widen the surface as we learn, not in advance.

## Text-to-speech

### Voice (`tts.voice`)

The engine is **`omnivoice`**, a voice-cloning model with two personas, and the
whole catalog is these two:

| `Voice` | Voice ID | Persona |
|---|---|---|
| `Voice.OMNIVOICE_GAURI` | `omnivoice/gauri` | Female |
| `Voice.OMNIVOICE_GAURAV` | `omnivoice/gaurav` | Male |

There is no separate model field: the engine is chosen entirely by the voice-id
prefix, and `omnivoice` is the only prefix.

### Language (`tts.language`)

`tts.language` is **not a text tag** — it selects which recorded reference clip
the voice is cloned from. `omnivoice/gauri` speaking `hi` and `omnivoice/gauri`
speaking `en` are two different recorded speakers.

Both personas have clips for **ten** of the 23 languages:

`hi`, `en`, `bn`, `gu`, `kn`, `ml`, `mr`, `pa`, `ta`, `te`

**A `tts.language` outside those ten is rejected** by the runtime, not quietly
served by the Hindi clip. The list is the roster today, not a promise frozen
into the wire contract: it grows as clips are recorded, and the session tells
you when you name one it cannot speak. So an Odia call is a configuration you
write down:

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
| `stt.language` | Whatever the caller says is transcribed by the English recognizer | Garbled transcripts, blamed on the model |

The first is the reason this page leads with a rule instead of a menu. A demo
shipped with Devanagari read in an English voice for weeks: every test was green,
every log line looked right, and every automated score was unchanged, because
none of them can hear.

Two rules kill it, and they are checked in two different places:

1. **State both legs or neither.** Not that the two agree — that you said both.
   Changing only the voice touches no language field and is unaffected. `Config`
   raises `ConfigError` on this one at the call site, before anything reaches
   the socket: it is a property of the request, so nothing needs to be asked.
2. **No silent substitution.** A speaking language with no clip is refused, so
   the Hindi fallback can only be something you asked for. This one comes back
   from the runtime as a rejected response naming the language — which clips
   exist is the speech tier's answer, and it changes as clips are recorded.

## Where it is set

- **For every session:** the runtime's own defaults, English on both legs. The
  agent record holds `brain_url` and nothing about voice or language — an
  agent-level language cannot depend on the caller, and `lead_qual` is the proof:
  it resolves a language from an enquiry form that does not exist until the
  session starts.
- **Per caller, or mid-call:** `await session.configure(Config(...))` from the
  brain — the only thing in the call that sees *this* caller. STT applies at the
  next turn boundary, TTS at the next speech unit, never mid-utterance.
- **From the browser: never.** A page can set at most one leg of a pair, which
  is precisely the failure above.

The `lead_qual` demo resolves its language per caller and then switches mid-call
across eight Indic languages — a worked example of both.
