---
title: Voice & language catalog
description: The STT models, languages, and TTS voices a session can select, and the knobs a brain can change mid-call.
---

A session picks its speech-to-text model, language, and text-to-speech voice
either at connect time (the client's `pipeline` config) or mid-call (the brain's
`configure_*` methods). This page is the catalog of allowed values.

:::caution[Setting the language: there is exactly one way]
**At connect:** set `language` to the same code on **both** `stt` and `tts`.

```ts
pipeline: {
  stt: { model: "vql-stt", language: "hi" },
  tts: { voice: "omnivoice/gauri", language: "hi" },
}
```

**Mid-call:** one call — `session.configure_language("hi")`.

Do not set `stt.language_hint`, and do not change a language with a
`configure_stt` + `configure_tts` pair. Those are the raw halves; the runtime
derives them from the above. Setting them by hand is how a config ends up
half-applied, and **a half-applied language is silent** — see
[Why both halves](#why-both-halves-matter) below.
:::

## Speech-to-text

### Model (`stt.model`)

| Value | What it is |
|---|---|
| `vql-stt` *(default, and the only one)* | A composite router covering **English plus 22 Indic languages**. It picks the underlying engine from `language` — you never name an engine directly. No language → English. |

There is no second recognizer to pin: leave the model as `vql-stt` and set the
language.

### Language (`stt.language`)

`vql-stt` supports **English (`en`)** plus these 22 Indic languages:

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

A language outside this set is not served; a session that asks for one falls back
to the English recognizer rather than failing to connect.

A mid-call language change (`configure_language`) that crosses the English↔Indic
boundary is applied at the **next end-of-turn**, never mid-utterance.

### STT session knobs

Passed via `configure_stt` (applies live):

| Knob | Purpose |
|---|---|
| VAD knobs | `vad_confidence`, `vad_min_volume`, `vad_start_frames`, `vad_stop_frames_to_trigger_update`, `vad_eager_frames`, `vad_barge_in_ms`, `resume_frames`, `min_segment_speech_frames`, `confidence_tail_ms` — voice-activity / end-of-turn tuning |

These are exactly the arguments `Session.configure_stt(...)` accepts. It also
takes `language_hint`, the raw recognizer field — use `configure_language`
instead, which sets it *and* moves the voice with it.

## Text-to-speech

### Voice (`tts.voice`)

Voice IDs are `engine/voice` — **the engine prefix is required** (a bare name is
rejected; there is no implicit default). The prefix, not any `model` field,
selects the engine.

The engine the public demos use is **`omnivoice`**, a voice-cloning model with two
personas:

| Voice ID | Persona |
|---|---|
| `omnivoice/gauri` | Female |
| `omnivoice/gaurav` | Male |

These two are the whole catalog. `tts.model` is not a real knob — the engine is
chosen entirely by the voice-id prefix, and `omnivoice` is the only prefix.

### Language (`tts.language`)

Both personas default to Hindi and have dedicated reference clips for `hi, en, bn,
gu, kn, ml, mr, pa, ta, te`; other languages fall back to the Hindi clip.

`tts.language` is **not a text tag** — it selects which of those reference clips
the voice is cloned from. `omnivoice/gauri` speaking `hi` and `omnivoice/gauri`
speaking `en` are two different recorded speakers.

## Why both halves matter

Each half fails on its own, quietly, in a different way:

| Half wrong | What you get | How you find out |
|---|---|---|
| `tts.language` | The right words in the wrong speaker — Hindi read by the English reference voice sounds like a non-native accent | **By ear only.** The words are correct, so transcription-based scoring is blind to it |
| `stt.language` | Whatever the caller says is transcribed by the English recognizer | Garbled transcripts, blamed on the model |

The first one is the reason this page leads with a rule instead of a menu. A demo
shipped with Devanagari under `language: "en"` and spoke in an accented English
voice for weeks: every test was green, every log line looked right, and every
automated score was unchanged, because none of them can hear.

Setting one field, `language`, on both sides makes the pair impossible to
half-apply. That is the whole reason the rule exists.

## Setting it

- **At connect (client):** the React SDK's `pipeline` prop.
  ```ts
  pipeline: {
    stt: { model: "vql-stt", language: "hi" },
    tts: { voice: "omnivoice/gauri", language: "hi" },
  }
  ```
- **Mid-call (brain):** `session.configure_language("hi")`, optionally with
  `voice=` when the target language wants a different persona. STT applies at the
  next turn boundary; TTS at the next inference, never mid-utterance. See
  [Handling a conversation](/docs/brain/conversation/#reconfigure-voice-mid-call).

The `lead_qual` demo switches language mid-call across eight Indic languages — a
good worked example.
