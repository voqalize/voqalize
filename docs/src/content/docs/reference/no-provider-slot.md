---
title: Why there is no provider slot
description: A session names a language and a voice. It names no engine, no model and no vendor. What that absence buys, what it costs, and the shape a second engine would arrive in.
---

You arrived at the configuration surface looking for the field that says which
speech vendor runs the call. There is no such field, and this page is the reason.

## What a session configures

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

Four settings: the recognizer's language, the speaking voice, the reference clip
that voice is cloned from, and how long silence runs before the brain gets the
floor back. The
[catalog](/reference/catalog/) is the roster of allowed values.

None of the four names an engine. The comment above the `Voice` enum in
[`frames.proto`](https://github.com/voqalize/voqalize/blob/main/proto/voqalize/frames/frames.proto)
is the whole story:

> The engine is chosen by the voice, not by a model field; there has never been a
> second engine to name.

## We run the speech tier ourselves

The recognizer covers English plus 22 Indic languages, and it runs on our own
GPUs. Text-to-speech is one voice-cloning engine with two personas, each with
recorded clips for a subset of that roster. Speech-to-text is `vql-stt`, a
composite that reads the language and routes to the engine underneath, which is
why a brain never names one.

We run it because of the roster. Assamese, Bodo, Dogri, Konkani, Maithili,
Manipuri, Santali and Sindhi are the languages a hosted catalog tends to be short
of, and they are the ones our callers speak. Running the tier is what puts them
in the enum.

## What the absence buys

**No engine knob exists** — on the wire, in the SDK, in the agent record, or per
environment. Two sessions cannot differ by an engine, so a change you hear
between one call and the next is a change we shipped, and we can name it.

**`Voice` and `Language` are protobuf enumerations**, so an unsupported value is
a value you cannot construct. The failure that closes is an unserved language
code falling through to the English recognizer, in a call whose transcript reads
correctly and whose logs are clean — see
[why both halves matter](/reference/catalog/#why-both-halves-matter).

**There are no VAD or end-of-turn knobs either.** Recognizer routing, the clip
roster and the moment a turn commits are tuned together against the same calls.
A knob on one of them is a knob on all three.

**No speech vendor key sits in your deployment**, and no speech vendor's outage
is a call you have to explain. When a voice sounds wrong, there is one place to
raise it.

## What it costs, plainly

A brain cannot point a session at another vendor's speech-to-text or
text-to-speech. If a particular commercial voice is the product — a brand voice
you have already licensed, a celebrity read, a language outside the roster — we
are the wrong voice tier for that call today, and a hosted speech vendor with
that voice is the right one.

The catalog is two personas. A product that needs a dozen distinguishable
speakers is ten short.

## The shape a second engine would arrive in

New members of `Voice` and `Language`. Your brain changes by one identifier, the
enum tells your editor what exists, and a value your SDK version has never heard
of stays unconstructable. The wire shape is the commitment we are making here;
the roster inside it is what moves.

## What you do choose

The model, the prompt, the tools, the history and the turn — all of it in the
process you deploy, in whichever framework you brought. The engine that turns
your text into audio is the one thing on the call we hold, and the reason is that
we hold the GPUs it runs on.

## Read next

- [Voice & language catalog](/reference/catalog/) — the values themselves, and the one rule that makes them safe to change.
- [What Voqalize is](/start/what-voqalize-is/) — the whole seam, in one page.
