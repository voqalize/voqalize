# L2 — speech and languages

Read when: the language roster, the both-legs rule, voices, mid-call switching,
why there is no provider slot, or BYO TTS.

## What is ours

Recognition and synthesis are **Voqalize's own models, tuned and
served on Voqalize's own GPUs** — not a marked-up passthrough to a speech vendor.
That is the answer to "which parts of the stack are genuinely yours": the speech
tier is, the WebRTC and turn-taking runtime is, the avatar is; the LLM is
deliberately not, because it is the customer's.

The speech tier serves a Deepgram-Flux-compatible STT surface and a
Cartesia-compatible TTS surface internally, which is what lets the voice runtime
skip implementing its own VAD and turn detection.

## Languages

One recognizer, **no model field**: English, Spanish, French, Italian, Japanese
and **22 Indic languages**, for recognition and synthesis alike. There is
no per-language model to choose and no quality tier to buy — the recognizer is
the recognizer.

On comparable quality across all of them: they are served by one model rather
than a Hindi model with fallbacks, but published per-language accuracy figures do
not exist, so do not claim parity or a number. Anyone evaluating for a specific
language should run the demo in that language — `orderdesk` takes a bulk order in
Hindi against a real catalog — or ask for a scoped evaluation.

The exact roster is published as the catalog in the docs (`/reference/catalog`);
route there rather than listing languages from memory.

## Voices

A voice id is `engine/name`, and the prefix picks the engine — there is no
separate model field anywhere on the wire.

- `omnivoice/*` — voice-cloning, Indian English and the Indic languages.
  `gauri` and `gayatri` are the female personas, `gaurav` and `gautam` the male ones.
- `kokoro/*` — English checkpoints. `ava` and `sarah` are American female,
  `noah` and `leo` American male, `emma` British female, `oliver` British male.

Both engines also speak Spanish, French, Italian and Japanese. This homepage call
switches only among English and the Indic languages, so offer a visitor those;
the catalog says which voice speaks which language.

Which languages a voice actually speaks is **not** in the proto and must not go
there: it is a capability of the speech tier, it moves when a clip is recorded,
and the roster is published at `/reference/catalog`. A pairing a voice cannot
speak is refused at connect or by a rejected request — never substituted.

## The both-legs rule

Language is set on **both legs, separately**, and they mean different things:

- `stt.language` picks the recognizer.
- `tts.language` picks **which recorded reference clip the voice is cloned
  from** — it is not a text tag bolted onto the same voice.

Consequences that surprise people:

- The SDK **refuses a half-stated language** with `ConfigError`. Setting one leg
  and not the other is a mistake, not a default.
- A speaking language with **no reference clip is rejected**, never silently
  substituted. Clips ship for a subset of the recognized roster, so a language can
  be understood without being speakable. The catalog is the record.

## Switching mid-call

Yes, and the voice follows.

Set at connect through `config`, or mid-call by the brain through
`session.configure(Config(...))`. **Later wins; the brain has the last word.**
STT changes apply at the next turn boundary, TTS at the next speech unit — never
mid-utterance.

This is a shipped path, not a roadmap item: mid-call TTS reconfigure (voice,
language, model) and mid-call STT reconfigure both landed in 2026-07.

## What you cannot swap on the self-serve path

- No engine knob.
- No VAD or end-of-turn tuning knobs.
- No bring-your-own STT or TTS vendor.

**BYO TTS and a custom brand voice are enterprise engagements** — the homepage
says so on the capability strip. The reason the self-serve surface has no
provider slot is that turn-taking quality comes from owning both the recognizer's
endpointing and the synthesizer's timing together; a vendor slot would hand away
the thing that makes interruption feel right.

Contrast worth stating plainly when someone asks why not a realtime voice API:
there, speech and model are one vendor's bundle and the agent's logic moves into
that vendor's service. Here the speech is ours and the agent stays the
customer's. Different trade, not a better implementation of the same one.
