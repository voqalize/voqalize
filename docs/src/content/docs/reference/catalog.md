---
title: Voice & language catalog
description: The languages the recognizer hears, the voices and the languages each one speaks, the turn-taking settings with their defaults, and the rule that both language legs are set together.
---

The values a session's `Config` accepts: recognizer languages, voices, and the
turn-taking settings. How to choose them, at connect or from your brain, is
[Voice and language](/build/voice-and-language/).

A session with no configuration runs in English on both legs, with ack on and
idle detection off.

:::caution[Set both legs of a language, always]
`stt.language` picks the **recognizer**. `tts.language` picks the language the
voice reads in, which for a cloned voice is a different recorded speaker. Name a
language on one leg and you must name it on the other; the SDK raises
`ConfigError` otherwise:

```python
from voqalize.sdk.wire import Config, SttConfig, TtsConfig

await session.configure(
    Config(
        stt=SttConfig(language="ta"),
        tts=TtsConfig(language="ta", voice="omnivoice/gauri"),
    )
)
```

**A half-applied language is silent.** The words stay right and only the speaker
is wrong, so no transcript, log or automated score shows it. See
[why both halves matter](#why-both-halves-matter).
:::

Voices and languages are strings: a voice by its id, a language by its BCP-47
tag. The older `Voice` and `Language` enums still parse, and are deprecated and
frozen: a voice or language added since has no member. A string needs a session
whose `session.can_configure_strings` is true; every Voqalize session
advertises it today.

## Turn-taking settings

| Setting | Values | Default |
|---|---|---|
| `stt.patience` | `0` (answer as soon as possible) to `10` (wait longest through a pause) | `7` when unset |
| `idle.timeout_ms` | `0` (off) to `300000` | `0`, so `on_user_idle` never fires until you set it |
| `ack.enabled` | `true` or `false` | on |

A value off the scale is refused. What each one does and when a change lands is
in [the wire reference](/reference/wire/#config--tts-stt-idle-and-ack-in-one-message).

## Speech-to-text

### Language (`stt.language`)

There is no model to choose. One recognizer serves every session and picks the
engine underneath from the language you set.

A language is a BCP-47 tag, such as `es`, `es-MX` or `ta`. The recognizer
matches it by the part before the first hyphen, ignoring case, so `es-MX` is
heard as Spanish. It hears **English (`en`)** and these European languages:

| Code | Language | Code | Language | Code | Language |
|---|---|---|---|---|---|
| `bg` | Bulgarian | `cs` | Czech | `da` | Danish |
| `de` | German | `el` | Greek | `es` | Spanish |
| `et` | Estonian | `fi` | Finnish | `fr` | French |
| `hr` | Croatian | `hu` | Hungarian | `it` | Italian |
| `lt` | Lithuanian | `lv` | Latvian | `mt` | Maltese |
| `nl` | Dutch | `pl` | Polish | `pt` | Portuguese |
| `ro` | Romanian | `ru` | Russian | `sk` | Slovak |
| `sl` | Slovenian | `sv` | Swedish | `uk` | Ukrainian |

And these Indic languages:

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

**A language the recognizer does not hear is refused, never substituted.** At
`sessions.connect` it is a `400` `invalid_config` whose `details.code` is
`unsupported_language`, and the message lists the languages the recognizer does
hear. From your brain it is a rejected `configure`. See
[error codes](/reference/errors/#refused-before-your-brain-is-dialled).

A language change applies at the **next end of turn**, never mid-utterance.

## Text-to-speech

### Voice (`tts.voice`)

<!-- voices:begin -->
| `Voice` | Voice ID | Sounds like | Speaks |
|---|---|---|---|
| `Voice.OMNIVOICE_AALIYAH` | `omnivoice/aaliyah` | Aaliyah (female) | `en` |
| `Voice.OMNIVOICE_ADITYA` | `omnivoice/aditya` | Aditya (male) | `en`, `hi` |
| `Voice.OMNIVOICE_AMARA` | `omnivoice/amara` | Amara (female) | `en` |
| `Voice.OMNIVOICE_ANANYA` | `omnivoice/ananya` | Ananya (female) | `en`, `hi` |
| `Voice.OMNIVOICE_ANDREI` | `omnivoice/andrei` | Andrei (male) | `en` |
| `Voice.OMNIVOICE_ARJUN` | `omnivoice/arjun` | Arjun (male) | `en`, `hi` |
| `Voice.OMNIVOICE_CHIARA` | `omnivoice/chiara` | Chiara (female) | `en` |
| `Voice.OMNIVOICE_DANIEL` | `omnivoice/daniel` | Daniel (male) | `en` |
| `Voice.OMNIVOICE_ELODIE` | `omnivoice/elodie` | Elodie (female) | `en` |
| `Voice.OMNIVOICE_EMILY` | `omnivoice/emily` | Emily (female) | `en` |
| `Voice.OMNIVOICE_FREYA` | `omnivoice/freya` | Freya (female) | `en` |
| `Voice.OMNIVOICE_GAURAV` | `omnivoice/gaurav` | Gaurav (male) | `bn`, `en`, `gu`, `hi`, `kn`, `ml`, `mr`, `pa`, `ta`, `te` |
| `Voice.OMNIVOICE_GAURI` | `omnivoice/gauri` | Gauri (female) | `bn`, `en`, `gu`, `hi`, `kn`, `ml`, `mr`, `pa`, `ta`, `te` |
| `Voice.OMNIVOICE_GAUTAM` | `omnivoice/gautam` | Gautam (male) | `bn`, `en`, `gu`, `hi`, `kn`, `ml`, `mr`, `pa`, `ta`, `te` |
| `Voice.OMNIVOICE_GAYATRI` | `omnivoice/gayatri` | Gayatri (female) | `bn`, `en`, `gu`, `hi`, `kn`, `ml`, `mr`, `pa`, `ta`, `te` |
| `Voice.OMNIVOICE_JASMINE` | `omnivoice/jasmine` | Jasmine (female) | `en` |
| `Voice.OMNIVOICE_JAVIER` | `omnivoice/javier` | Javier (male) | `en`, `es` |
| `Voice.OMNIVOICE_JORDAN` | `omnivoice/jordan` | Jordan (male) | `en` |
| `Voice.OMNIVOICE_KARTHIK` | `omnivoice/karthik` | Karthik (male) | `en`, `hi` |
| `Voice.OMNIVOICE_KASIA` | `omnivoice/kasia` | Kasia (female) | `en` |
| `Voice.OMNIVOICE_KAVYA` | `omnivoice/kavya` | Kavya (female) | `en`, `hi` |
| `Voice.OMNIVOICE_LUKAS` | `omnivoice/lukas` | Lukas (male) | `en` |
| `Voice.OMNIVOICE_MADISON` | `omnivoice/madison` | Madison (female) | `en` |
| `Voice.OMNIVOICE_MARCUS` | `omnivoice/marcus` | Marcus (male) | `en` |
| `Voice.OMNIVOICE_MEERA` | `omnivoice/meera` | Meera (female) | `en`, `hi` |
| `Voice.OMNIVOICE_NIKHIL` | `omnivoice/nikhil` | Nikhil (male) | `en`, `hi` |
| `Voice.OMNIVOICE_OLIVERBENNETT` | `omnivoice/oliverbennett` | Oliverbennett (male) | `en` |
| `Voice.OMNIVOICE_PRIYA` | `omnivoice/priya` | Priya (female) | `en`, `hi` |
| `Voice.OMNIVOICE_RIYA` | `omnivoice/riya` | Riya (female) | `en`, `hi` |
| `Voice.OMNIVOICE_ROHAN` | `omnivoice/rohan` | Rohan (male) | `en`, `hi` |
| `Voice.OMNIVOICE_RYAN` | `omnivoice/ryan` | Ryan (male) | `en` |
| — | `omnivoice/saanvi` | Saanvi (female) | `en`, `hi` |
| `Voice.OMNIVOICE_SAMUEL` | `omnivoice/samuel` | Samuel (male) | `en` |
| `Voice.OMNIVOICE_SOFIA` | `omnivoice/sofia` | Sofia (female) | `en` |
| `Voice.OMNIVOICE_TYLER` | `omnivoice/tyler` | Tyler (male) | `en` |
<!-- voices:end -->

The table is generated from the voices the speech tier is serving. The prefix on
the voice id picks the engine; there is no other engine selector.

### Language (`tts.language`)

What `tts.language` means depends on the voice, which is why the table states it
per voice:

- A **cloned** voice is recorded separately for each language it speaks.
  `omnivoice/gauri` speaking `hi` and `omnivoice/gauri` speaking `en` are two
  different recorded speakers.
- A voice whose accent comes from its **checkpoint** speaks only the language
  that checkpoint was trained on.

**A pairing the voice cannot speak is rejected**, not served in the wrong
language. The rejection names the languages that voice does speak.

The legs may differ on purpose. An Odia call spoken with the Hindi clip is a
configuration you write down:

```python
from voqalize.sdk.wire import Config, SttConfig, TtsConfig

Config(
    stt=SttConfig(language="or"),   # understood in Odia
    tts=TtsConfig(language="hi"),   # spoken with the Hindi clip
)
```

## Why both halves matter

Each half fails on its own, quietly, in a different way:

| Half wrong | What you get | How you find out |
|---|---|---|
| `tts.language` | The right words in the wrong speaker: Hindi read by the English reference clip sounds like a non-native accent | **By ear only.** The words are correct, so transcription-based scoring is blind to it |
| `stt.language` | What the user says is transcribed in the wrong language | Garbled transcripts, blamed on the model |

Two rules prevent it:

- **State both legs or neither.** Not that the legs agree, only that you named
  both. Changing only the voice touches no language field. `Config` raises
  `ConfigError` at the call site, before anything reaches the socket.
- **No silent substitution.** A language the chosen voice does not speak is
  refused, so the Hindi clip is only ever something you asked for. Voqalize
  answers this one: at connect when the configuration arrived there, and as a
  rejected `configure` when your brain sent it.

Voqalize runs recognition and synthesis itself, so there is no speech provider
to configure and no provider key in your deployment.

## Read next

- [Voice and language](/build/voice-and-language/): set these per session, and switch mid-call.
- [The wire](/reference/wire/#the-control-leg): the `Config` fields and when each change lands.
- [Error codes](/reference/errors/): what a refused configuration looks like.
