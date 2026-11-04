---
title: Voice and language catalog
description: The languages the recognizer hears, the voices and the languages each one speaks, the turn-taking settings with their defaults, and the rule that both language legs are set together.
---

The values a session's `Config` accepts: recognizer languages, voices, and the
turn-taking settings. How to choose them, at connect or from your brain, is
[Voice and language](/build/voice-and-language/).

A session with no configuration runs in English on both legs, with ack on and
idle detection off.

:::caution[Set both legs of a language, always]
Name a language on `stt` and you must name one on `tts`, or the SDK raises
`ConfigError`. A half-applied language is silent: the words stay right and only
the speaker is wrong. [Voice and language](/build/voice-and-language/#always-set-both-legs)
shows how; [why both halves matter](#why-both-halves-matter) shows what each
half does wrong.
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

The voices Voqalize serves are published live, voice by voice, at
[`https://speech.prod.voqalize.com/voices.json`](https://speech.prod.voqalize.com/voices.json).
The table below is read from it when the page loads, so it is never a copy that
has gone stale. To read the list from code, fetch that URL: it is public JSON and
needs no key.

Each entry in its `voices` list has these fields:

| Field | Meaning |
|---|---|
| `id` | What you send as `tts.voice`, such as `omnivoice/gauri`. Matched without regard to case. The prefix before the `/` picks the engine; there is no other engine selector. |
| `display` | A human name for the voice, and whether it sounds male or female. |
| `languages` | The tags this voice speaks: the values `tts.language` accepts with it. A tag matches by the part before the first hyphen, so `hi-IN` is `hi`. |
| `engine` | The engine behind the voice. |

The document also carries `version` (the shape of the document, `1` today) and
`rules`, which states in words how a voice id and a language tag are matched.

<div id="voice-catalog" class="not-content">
  <p>Loading the voices from <a href="https://speech.prod.voqalize.com/voices.json">speech.prod.voqalize.com/voices.json</a>…</p>
</div>
<script src="/voice-catalog.js" type="module"></script>

### Language (`tts.language`)

What `tts.language` means depends on the voice, which is why the table states it
per voice:

- Most voices are **cloned** from a reference recording, one per language they
  speak. `omnivoice/gauri` speaking `hi` and `omnivoice/gauri` speaking `en`
  are two different recorded speakers.
- A voice whose accent comes from its model (its **checkpoint**) speaks only
  the language that model was trained on.

**A pairing the voice cannot speak is rejected**, not served in the wrong
language. The rejection names the languages that voice does speak.

The legs may differ on purpose. An Odia call answered in the voice's Hindi
recording is a configuration you write down:

```python
from voqalize.sdk.wire import Config, SttConfig, TtsConfig

Config(
    stt=SttConfig(language="or"),   # understood in Odia
    tts=TtsConfig(language="hi"),   # spoken in Hindi
)
```

## Why both halves matter

Each half fails on its own, quietly, in a different way:

| Half wrong | What you get | How you find out |
|---|---|---|
| `tts.language` | The right words in the wrong speaker: Hindi read by the voice's English recording sounds like a non-native accent | **By ear only.** The words are correct, so transcription-based scoring is blind to it |
| `stt.language` | What the user says is transcribed in the wrong language | Garbled transcripts, blamed on the model |

Voqalize never substitutes for either: a language the chosen voice does not
speak is refused at connect, or as a rejected `configure` from your brain.

Voqalize runs recognition and synthesis itself, so there is no speech provider
to configure and no provider key in your deployment.

## Read next

- [Voice and language](/build/voice-and-language/): set these per session, and switch mid-call.
- [The wire](/reference/wire/#the-control-leg): the `Config` fields and when each change lands.
- [Error codes](/reference/errors/): what a refused configuration looks like.
