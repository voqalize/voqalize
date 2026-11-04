---
title: Use another agent framework
description: Give an existing ADK, LangChain, OpenAI Agents or hand-rolled agent a voice. The port is one subclass; the one thing that has to change is how you record history.
---

`Brain.on_user_message` hands you the user's finished text and takes speech
back, so whatever already turns a string into a stream of strings becomes the
body of that method. Your model, prompts, tools, retrieval and memory stay where
they are.

## The port

Subclass `Brain`, call your existing entrypoint from `on_user_message`, and
record what the user heard. For a framework whose entrypoint is
`async def run(text) -> AsyncIterator[str]`, that is the whole port:

```python
from voqalize.sdk import Brain, SpeechChunk, SpeechEnd, SpeechStart

from myagent import Agent  # your framework, unchanged


class PortedBrain(Brain):
    def __init__(self) -> None:
        self.agent = Agent()

    async def greet(self, session):
        return "Hi! What can I do for you?"

    async def on_user_message(self, session, msg):
        speaking = False
        async for piece in self.agent.run(msg.text):
            if not speaking:
                yield SpeechStart()
                speaking = True
            yield SpeechChunk(piece)
        if speaking:
            yield SpeechEnd()

    async def on_finalize(self, session, fin):
        if fin.heard:
            self.agent.history.append({"role": "assistant", "content": fin.heard})
```

- **`msg.text`** is one committed user turn.
- **`SpeechStart` / `SpeechChunk` / `SpeechEnd`** are one speech unit: the stretch
  the user can cut into, and the grain Voqalize reports what was heard against.
  The unit opens on the first piece of text, so a step that only calls a tool
  opens nothing ([Speaking](/build/brain/speaking/#a-turn-can-be-several-units)).
- **The class, not an instance, is what you host.** The SDK constructs one per
  session, so an object built in `__init__` belongs to that call. Per-user setup
  goes in `on_session_start`, which reads `session.init` before the greeting
  ([Context and history](/build/brain/context/)).

Host it like any other brain: [Deploy the brain](/build/hosting/).

## What has to change: history records what was heard

Your framework almost certainly appends the assistant message from what the model
returned. For a call that is the wrong record: a user can interrupt mid-word, and
then what your model generated and what the user heard are different strings.

- **Turn off your framework's own append** of the assistant turn, or rewrite that
  entry when the finalize arrives.
- **Append `fin.heard`**, per unit. A reply that generated three sentences and
  delivered one goes into history as one.
- **Drop a unit with `heard == ""`.** It reached nobody, so it is not something
  the model said.
- **Record the greeting.** `greet` returns a string the SDK speaks, so your
  framework never saw it. Its finalize arrives first; append it, or the model
  greets twice.
- **Keep the conversation in your process.** A conversation stored on the model
  provider's server (a stored conversation id that each call continues) cannot be
  told that the user heard only half of the last sentence. Keep a local history
  list and send it on each request.

[Transcripts and heard truth](/build/brain/transcripts/) has the ordering rules
and a complete pairing example.

## What stays the same

Tool calls stay ordinary function calls in your process. Your framework's
registry, decorators and dispatch are untouched, because no tool crosses to
Voqalize: the boundary is text. The same goes for your retrieval, model client and
keys, prompts and database. The port adds one class to your service.

What a tool costs is new, though: it runs while the user waits. Say what you are
doing in the same response as the call, keep tools fast, and move the screen
while the voice waits ([Tools](/build/brain/tools/#speak-first-and-call-in-the-same-response)).

## Or start from a shipped model brain

If your agent is a prompt, a model and a list of tools, subclassing a shipped
model brain is a shorter port than wrapping your loop. Each one runs speech,
tools, heard truth and the greeting for you:

| Class | Install | Speaks to |
|---|---|---|
| `GeminiBrain` | `pip install "voqalize-agent-sdk[gemini]==0.12.0"` | Gemini's `generate_content` |
| `OpenAIBrain` | `pip install "voqalize-agent-sdk[openai]==0.12.0"` | OpenAI's Responses API |
| `LiteLLMBrain` | `pip install "voqalize-agent-sdk[litellm]==0.12.0"` | Any model LiteLLM reaches |

Constructors are in [the shipped adapters](/reference/brain/#the-shipped-adapters);
tools are in [Tools](/build/brain/tools/). There is no adapter for a framework that
owns its own loop (ADK, LangGraph, the OpenAI Agents SDK): use the port above.

## Report what a turn did

The shipped model brains report every model request and tool to Voqalize as a
`TurnStep`, and the call record shows them as a timeline beside the turn. A ported
brain runs its own loop, so it reports its own: one step per model request, when
the request ends.

```python
import time

from voqalize.sdk import Brain, SpeechChunk, SpeechEnd, SpeechStart, TurnStep

from myagent import Agent


class PortedBrain(Brain):
    def __init__(self) -> None:
        self.agent = Agent()

    async def on_user_message(self, session, msg):
        started = time.monotonic()
        yield SpeechStart()
        async for piece in self.agent.run(msg.text):
            yield SpeechChunk(piece)
        yield SpeechEnd()
        usage = self.agent.last_usage  # whatever your framework reports
        if session.can_report_steps:
            session.report_step(
                TurnStep(
                    kind="model",
                    name="gpt-6-sol",
                    provider="openai",
                    duration_ms=round((time.monotonic() - started) * 1000),
                    counts={
                        "input_tokens": usage.input_tokens,
                        "output_tokens": usage.output_tokens,
                    },
                )
            )
```

It never blocks and nothing comes back. Steps carry facts, never content: no
prompt, arguments or results. Leave out a count you do not have rather than
writing `0`. Report a tool or a database query the same way, with
`kind="tool"` or your own word. Fields: [`report_step`](/reference/brain/#methods).

## Rewrite the prompt for voice

A chat prompt can afford a lookup, because the reader watches a spinner. Spoken,
the same two seconds are silence, and nothing can be scrolled back. That is a
design problem, not an SDK one: start with
[Prompt design for voice](/design/#prompt-design-for-voice).

## Read next

- [Transcripts and heard truth](/build/brain/transcripts/): the history rule in full.
- [Test the brain](/build/testing/): prove the port without a microphone.
- [Deploy the brain](/build/hosting/): a route Voqalize dials, or Cortex for local development.
