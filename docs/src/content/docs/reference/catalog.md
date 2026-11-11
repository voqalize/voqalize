---
title: Voice, language and character catalog
description: The live catalog at GET /api/v1/catalog.get, field by field. The languages the recognizer hears, the voices and the languages each one speaks, the avatar characters and the voices that suit them, the turn-taking settings with their defaults, and the rule that both language legs are set together.
---

The values a session's `Config` accepts (recognizer languages, voices and the
turn-taking settings) and the avatar characters you can mount beside them. How
to choose them, at connect or from your brain, is
[Voice and language](/build/voice-and-language/).

## The live catalog

Voices, languages and characters are published live at:

```
GET https://app.voqalize.com/api/v1/catalog.get
```

It is public JSON: no key, no sign-in, and it may be cached for 60 seconds. The
tables on this page are read from it when the page loads, so none of them is a
copy that has gone stale. To read the catalog from code, fetch that URL.

| Field | Meaning |
|---|---|
| `voices` | Every voice served by id. Each has `id`, `name`, `display`, `engine` and `languages`; see [Voice](#voice-ttsvoice). |
| `open` | Prefixes under which any id is accepted, each with `prefix`, `engine` and `languages`. The engine behind the prefix judges the rest of the id. Often empty. |
| `rules` | In words, how a voice id and a language tag are matched, or `null`. |
| `languages` | The languages the recognizer hears, each with `name`, `code` and `display_name`; see [Language](#language-sttlanguage). |
| `characters` | The avatar characters, each with `name`, `gender`, `age`, `ethnicity`, `tags`, `suggested_voices` and `languages`; see [Characters](#avatar-characters). |
| `avatar_package` | The `@voqalize/avatar` release whose characters `characters` lists. |
| `stale` | `{voices, languages}`, each `true` while that list is being re-read. A stale list may be empty or out of date; read it again shortly rather than treating it as the truth. |

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
heard as Spanish. It hears English, the major European languages and the Indic
languages. The catalog's `languages` list names each one:

| Field | Meaning |
|---|---|
| `code` | The tag to send as `stt.language`, such as `hi`. |
| `display_name` | The language's English name, such as `Hindi`. |
| `name` | The deprecated `Language` enum member for it, such as `LANGUAGE_HI`, where one exists; otherwise the code. The enum is frozen, so a newer language is a string only. |

<div id="language-catalog" class="catalog-live not-content">
  <p>Loading the languages from <a href="https://app.voqalize.com/api/v1/catalog.get">app.voqalize.com/api/v1/catalog.get</a>…</p>
</div>

**A language the recognizer does not hear is refused, never substituted.** At
`sessions.connect` it is a `400` `invalid_config` whose `details.code` is
`unsupported_language`, and the message lists the languages the recognizer does
hear. From your brain it is a rejected `configure`. See
[error codes](/reference/errors/#refused-before-your-brain-is-dialled).

A language change applies at the **next end of turn**, never mid-utterance.

## Text-to-speech

### Voice (`tts.voice`)

The voices Voqalize serves are the catalog's `voices` list, voice by voice.
Each entry has these fields:

| Field | Meaning |
|---|---|
| `id` | What you send as `tts.voice`, such as `omnivoice/gauri`. Matched without regard to case. The prefix before the `/` picks the engine; there is no other engine selector. |
| `name` | The deprecated `Voice` enum member for it, such as `VOICE_OMNIVOICE_GAURI`, where one exists; otherwise the `id`. Send the `id`. |
| `display` | A human name for the voice, and whether it sounds male or female. |
| `languages` | The tags this voice speaks: the values `tts.language` accepts with it. A tag matches by the part before the first hyphen, so `hi-IN` is `hi`. |
| `engine` | The engine behind the voice. |

<div id="voice-catalog" class="catalog-live not-content">
  <p>Loading the voices from <a href="https://app.voqalize.com/api/v1/catalog.get">app.voqalize.com/api/v1/catalog.get</a>…</p>
</div>

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

The legs may differ on purpose. An Assamese call answered in the voice's Hindi
recording is a configuration you write down:

```python
from voqalize.sdk.wire import Config, SttConfig, TtsConfig

Config(
    stt=SttConfig(language="as"),   # understood in Assamese
    tts=TtsConfig(language="hi"),   # spoken in Hindi
)
```

## Avatar characters

The characters [the avatar](/build/avatar/) mounts are the catalog's
`characters` list, for the `@voqalize/avatar` release `avatar_package` names.
Pass a `name` as the avatar's `character`.

| Field | Meaning |
|---|---|
| `name` | What you pass as `character`, such as `emily`. |
| `gender` | The character's presented gender. |
| `age` | `{min, max}`, the age range the face reads as. |
| `ethnicity` | A list of words from a closed vocabulary. |
| `tags` | A list of words from a closed vocabulary, such as `formal`. |
| `suggested_voices` | Voice ids that suit the face, best first. Advice only: nothing checks the voice a session sets against the face it shows. |
| `languages` | The languages the first suggested voice speaks. |

A face and a voice are chosen separately: set the session's voice and language
yourself, on both legs, as [Voice and language](/build/voice-and-language/)
shows. Each name below opens that character on the avatar page.

<div id="character-catalog" class="catalog-live not-content">
  <p>Loading the characters from <a href="https://app.voqalize.com/api/v1/catalog.get">app.voqalize.com/api/v1/catalog.get</a>…</p>
</div>
<script src="/voice-catalog.js" type="module"></script>

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
- [The avatar](/build/avatar/): mount a character beside the call.
