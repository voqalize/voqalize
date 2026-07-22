---
title: Voice & language catalog
description: The STT models, languages, and TTS voices a session can select, and the knobs a brain can change mid-call.
---

A session picks its speech-to-text model, language, and text-to-speech voice
either at connect time (the client's `pipeline` config) or mid-call (the brain's
`configure_stt` / `configure_tts`). This page is the catalog of allowed values.

:::note[Deployment-specific]
The concrete set of enabled models and installed voices is a property of the
deployment (each engine is opt-in server-side). The values below are what ships in
the public demos and are the stable, documented surface.
:::

## Speech-to-text

### Model (`stt.model`)

| Value | What it is |
|---|---|
| `vql-stt` *(default)* | A composite router covering **English plus 22 Indic languages**. It picks the underlying engine from `language` — you never name an engine directly. No language → English. Use this. |
| `nemotron-streaming` | A directly-pinned engine, for comparison/testing. |
| `cohere-transcribe` | A directly-pinned engine, for comparison/testing. |

For almost every agent, leave the model as `vql-stt` and just set the language.

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

A mid-call language change (`configure_stt(language_hint=...)`) that crosses the
English↔Indic boundary is applied at the **next end-of-turn**, never mid-utterance.

### STT session knobs

Passed via `configure_stt` (applies live). Defaults shown:

| Knob | Default | Range |
|---|---|---|
| `language_hint` | — | any code above |
| `eot_threshold` | `0.5` | `0.0`–`1.0` (end-of-turn probability) |
| `eot_timeout_ms` | `3000` | `500`–`30000` (force end-of-turn after trailing silence) |
| `sample_rate` | `16000` | `8000`–`48000` |
| VAD knobs | — | `vad_confidence`, `vad_min_volume`, `vad_start_frames`, `vad_stop_frames_to_trigger_update`, `vad_eager_frames`, `vad_barge_in_ms`, `resume_frames`, `min_segment_speech_frames`, `confidence_tail_ms` |

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
| `omnivoice/auto` | Model-chosen voice (no fixed persona) |

Both personas default to Hindi and have dedicated reference clips for `hi, en, bn,
gu, kn, ml, mr, pa, ta, te`; other languages fall back to the Hindi clip.

:::note
Other TTS engines (`supertonic`, `indicf5`, `kokoro`) exist and may be enabled in a
given deployment, with their own voice IDs. The `omnivoice/*` voices above are the
shipping catalog. `tts.model` is not a real knob — the engine is chosen entirely by
the voice-id prefix.
:::

## Setting it

- **At connect (client):** the React SDK's `pipeline` prop, e.g.
  ```ts
  pipeline: {
    stt: { model: "vql-stt", language: "en" },
    tts: { voice: "omnivoice/gauri", language: "en" },
  }
  ```
- **Mid-call (brain):** `session.configure_stt(language_hint="hi")` and
  `session.configure_tts(voice="omnivoice/gaurav")`. STT applies live; TTS applies
  at the next inference. See
  [Handling a conversation](/docs/brain/conversation/#reconfigure-voice-mid-call).

The `lead_qual` demo switches both STT and TTS language mid-call for multilingual
qualification — a good worked example.
