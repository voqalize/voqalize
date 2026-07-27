---
title: What is Voqalize?
description: Voqalize runs the voice stack so you only write the brain — an agent that receives text and speaks text back.
---

Voqalize is a platform for building **voice agents**. It runs the hard,
latency-critical parts of a real-time voice stack — WebRTC media, voice activity
detection, speech-to-text, text-to-speech, turn-taking, barge-in, recording — and
leaves you exactly one job: the **brain**.

> **Voqalize is a voice operator that lives inside your app — it drives the UI, reads live
> and authenticated state, and does the actual work. You write the brain; Voqalize runs the voice.**

## The split

A Voqalize app has two halves:

- **The voice runtime** (ours). It answers the call, transcribes the caller,
  speaks your agent's replies, and handles interruptions. It is a managed service;
  you don't run it.
- **The brain** (yours). A program that receives the caller's text and streams
  text back. It holds your prompt, your model, your tools, and your data. **Your
  code never touches audio** — no sample rates, no codecs, no jitter buffers.

The two talk over a single WebSocket, one connection per call, carrying a small
set of `Vql*` frames: user text in, agent text out, plus a few frames for tool
calls, UI commands, and mid-call reconfiguration.

## Why it's shaped this way

Voice is hard in the parts that have nothing to do with *your* agent: echo
cancellation, endpointing, streaming TTS, cutting the bot off cleanly when the
user starts talking. Those are the same for every agent. Your prompt, tools, and
business logic are the same as any backend you already write.

So Voqalize draws the line at **text**. Everything below the text boundary is the
platform's problem. Everything above it — *what to say* — is yours, written in
whatever language and framework you already use, running wherever your other
backend code runs.

## What you write

A brain is a short subclass with a couple of callbacks:

```python
from voqalize.sdk import Brain, Interaction, Session, SessionStart

class EchoBrain(Brain):
    async def on_session_start(self, session: Session, start: SessionStart) -> None:
        async with session.inference() as inf:
            await inf.speak("Hi! I'm an echo bot. Say something and I'll repeat it.")

    async def on_interaction(self, interaction: Interaction) -> None:
        async with interaction.inference() as inf:
            await inf.speak(f"You said: {interaction.transcript}")
```

That's a complete, running voice agent. Swap the body of `on_interaction` for a
call to your LLM and you have a real one. See the [Quickstart](/docs/start/quickstart/).

## Where to go next

- **[Quickstart](/docs/start/quickstart/)** — build and run your first brain.
- **[Core concepts](/docs/start/concepts/)** — sessions, interactions, inferences,
  and the `brain_url`.
- **[Build a brain: Python](/docs/brain/python/)** / **[Go](/docs/brain/go/)** —
  the full SDK surface.
- **[Demo gallery](/docs/demos/gallery/)** — nine complete, runnable voice apps.
