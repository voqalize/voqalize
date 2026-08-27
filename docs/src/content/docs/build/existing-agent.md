---
title: Bringing an agent you already have
description: You have an ADK, LangChain, OpenAI Agents or hand-rolled agent. What has to change to give it a voice, and what does not.
---

Most readers of these pages are not starting from nothing. There is already an
agent — a Google ADK app, a LangChain graph, an OpenAI Agents runner, a state
machine somebody wrote by hand — and the question is what it costs to give it a
voice. The answer is a subclass and a loop: `Brain.on_user_message` hands you
finalized text and takes speech back, so whatever already turns a string into a
stream of strings is the body of the method. Your model, your prompts, your
tools, your retrieval and your memory do not move.

## There is no adapter for your framework

We ship two adapters and both are for Gemini. There is no ADK adapter, no
LangChain adapter and no OpenAI Agents adapter, and none is coming.

An adapter is a second surface to learn and a lag behind every release of a
framework we do not own. Read what the Gemini ones actually spend their code on:
`GeminiBrain._fold_results` moves the tool responses out of google-genai's
automatic-function-calling record into the context as that record grows between
hops, and `GeminiBrain._drop_unanswered` removes a `function_call` whose
`function_response` never arrived because a barge-in cut the stream between them
(`sdk/python/src/voqalize/sdk/gemini.py`). Neither is
about voice. Both are about one provider's turn record, and both break when that
provider changes it.

The boundary Voqalize holds is text. Nothing in the wire declares a tool,
carries a schema or names a model: `proto/voqalize/frames/frames.proto` has
frames for speech, transcripts, configuration, RTVI and errors, and there is no
tool frame in it. So there is nothing for an adapter to sit between — your
stream of strings goes out as speech, and the caller's finalized text comes back
in.

## The port, in three steps

Subclass `Brain`, call your existing entrypoint from `on_user_message`, and
record what the caller heard. Against a framework whose entrypoint is
`async def run(text) -> AsyncIterator[str]`, that is the whole port:

```python
from voqalize.sdk import Brain, Chunk, SpeechEnd, SpeechStart

from myagent import Agent  # your framework, unchanged


class PortedBrain(Brain):
    def __init__(self) -> None:
        self.agent = Agent()

    async def greet(self, session):
        return "Hi! What can I do for you?"

    async def on_user_message(self, session, msg):
        yield SpeechStart()
        async for piece in self.agent.run(msg.text):
            yield Chunk(piece)
        yield SpeechEnd()

    async def on_finalize(self, session, fin):
        if fin.heard:
            self.agent.history.append({"role": "assistant", "content": fin.heard})
```

`msg.text` is one finalized utterance. `SpeechStart` / `Chunk` / `SpeechEnd` are
one **speech unit** — the granularity at which a caller can cut you off and the
granularity at which Voqalize reports back what they heard. Yield the chunks as
your framework produces them; awaiting between them is what a tool call inside a
turn looks like. [Speaking](/build/brain/speaking/) owns the frames.

You host this the same way as any other brain, and the choice is unrelated to
the port — [Where the brain runs](/build/hosting/). The class is what you hand
over, not an instance: the SDK constructs one per session, so a framework object
built in `__init__` belongs to that call and leaks nothing into the next.
Per-caller setup that needs an identifier goes in `on_session_start`, which reads
`session.init` and runs before the greeting —
[Context and history](/build/brain/context/).

### One turn, several units

The fence above opens a unit before your framework has produced anything. If
`run()` calls a tool before its first token, the caller is holding an open unit
and hearing nothing. Open lazily instead, and the turn mints a unit only when
there is something to say:

```python
    async def on_user_message(self, session, msg):
        speaking = False
        async for piece in self.agent.run(msg.text):
            if not speaking:
                yield SpeechStart()
                speaking = True
            yield Chunk(piece)
        if speaking:
            yield SpeechEnd()
```

That is what `GeminiBrain.respond` does — a hop that only calls a tool never
opens a unit at all. Opening one per hop is what used to emit an empty
`SpeechStart` / `SpeechEnd` pair around a silent tool call
(`sdk/python/src/voqalize/sdk/gemini.py`, `respond`).

Lazy opening removes the empty bracket. It does not remove the silence: the tool
runs for as long as it runs and the caller sits through it either way, and the
fix for that is to say what you are doing before you do it, or to move the screen
while the voice waits. [The turn budget](/design/turn-budget/) is the argument;
[Tools](/build/brain/tools/) is the mechanism.

Every unit that emitted text gets exactly one `on_finalize`, in the order the
units opened — including one that was generated and beaten to the speaker, which
arrives as `heard=""`. A turn that says a line, calls a tool and says a second
line produces two units and two finalizes.

## What your framework keeps

Tool calls stay ordinary function calls in your process. Your framework's
registry, its decorators and its dispatch are untouched, because no tool reaches
the wire and there is nothing here to interpose on.

The same holds for everything behind them: your retrieval, your model client and
its keys, your prompts in your version control, your database session. The port
adds one class to your service and changes nothing about what that service
already reaches.

## What has to change, and it is one thing: history

Your framework almost certainly appends the assistant message from what the
model returned. That is the wrong record for a call.

A caller can interrupt mid-word. What your model generated and what the caller
heard are then two different strings, and only one of them is a thing the two
parties can both refer to. `on_finalize` hands you the delivered prefix as
`fin.heard`, per unit, after playout — long after the generator that produced it
returned (`sdk/python/src/voqalize/sdk/events.py`, `Finalize`). So:

- Turn off your framework's own append of the assistant turn, or rewrite that
  entry in place when the finalize arrives.
- Append `fin.heard`. A reply that generated three sentences and delivered one
  goes into history as one.
- Handle the empty case. `heard` is an empty string for a unit that reached no
  speaker, and that unit belongs out of your history entirely rather than in it
  as a sentence the model believes it said.

This failure produces no error, no log line and no metric. The call sounds fine,
the transcript is a real transcript, and three turns later the agent references
something it never finished saying — and the caller is the only instrument that
saw it. [Transcripts and heard truth](/build/brain/transcripts/) has the
watermark and the ordering rules;
[Interruption and heard truth](/design/interruption-and-heard-truth/) is the
argument under them.

`GeminiBrain.on_finalize` is a shipped implementation of exactly this: it pops
the oldest unit still awaiting a finalize, rewrites that turn's text down to
`heard`, and drops the turn when nothing is left of it
(`sdk/python/src/voqalize/sdk/gemini.py`, `on_finalize` and `_reconcile`).
`sdk/python/tests/unit/test_gemini_heard_truth.py` pins the eight cases,
including that finalizes match units in order and that a unit nobody heard leaves
the context.

### The greeting is also history

`greet` returns a string the SDK speaks, so your framework never saw it. Its
finalize arrives with nothing of yours awaiting one — that is the branch in both
adapters that appends `fin.heard` as a fresh model turn rather than rewriting an
existing one. Skip it and the model does not know it greeted, and asks its
opening question a second time.

### Keep the conversation in your process

If your framework holds history on the provider's server — a stored conversation
id that each call continues — heard truth cannot be applied to it. A server-side
conversation cannot be told that the caller only heard half of the last sentence.
`GeminiInteractionsBrain` sends `store=False` and no `previous_interaction_id`
for that reason, and carries the whole context on every call
(`sdk/python/src/voqalize/sdk/gemini_interactions.py`, `_stream`). Port to a
local history list and the rewrite is a list mutation.

## Where the two Gemini adapters fit

Both are worked examples of the port above, not a supported-frameworks list.
Both are behind the `gemini` extra, because `import voqalize.sdk` pulls no model
vendor:

```bash
pip install "voqalize-agent-sdk[gemini]==0.2.0"
```

Neither is re-exported from `voqalize.sdk`; you import them from their own
modules. Both take the same constructor and the same `tools` property of bound
`async def` methods, so a brain moves between them without touching its tools;
[the Brain API](/reference/brain/#the-two-shipped-adapters) lists both surfaces
in full.

**`GeminiBrain`**, in `voqalize.sdk.gemini`, runs on `generate_content` with
google-genai's automatic function calling. The provider runs the tools and loops
for us, so a turn that calls a tool and then speaks about the result is one call;
the adapter takes the record google-genai kept
(`automatic_function_calling_history`) instead of interposing to make its own.
Two consequences fall out of that: the contents are handed over once per turn, so
heard truth applies per turn rather than per hop, and context appended while a
tool is running reaches the model on the turn after.

**`GeminiInteractionsBrain`**, in `voqalize.sdk.gemini_interactions`, runs on the
interactions API, which declares tools and nothing else — no field takes a
callable, so this class runs the loop itself: declare, stream, call, answer,
stream again, up to `max_tool_hops`, and the last hop runs with
`tool_choice="none"` so a turn that spends its whole budget still ends in
something the caller hears. Because the loop is ours, step boundaries arrive
bracketed rather than inferred from a `finish_reason`, a call and its result are
linked by id rather than by position, and the whole context is re-read on every
hop — so an append that lands while a tool is running is in front of the model
for the sentence that follows it.

## What changes about the agent itself

Nothing above touches the prompt, and the prompt is where a ported agent
actually goes wrong first. A chat prompt can afford a lookup, because the reader
watches a spinner while it happens. Said out loud, the same two seconds are
silence on a channel where silence is the one thing a caller reacts to — so what
the agent needs, it should mostly already have, and what it says has to survive
having no scrollback.

That is a design problem rather than an SDK one, and it has its own section:
[Designing for voice](/design/), starting with
[Prompt design for voice](/design/prompt-design/).

## Read next

- [Your first brain](/build/brain/) — the callbacks you are subclassing.
- [Tools](/build/brain/tools/) — what a voice tool owes the caller.
- [Testing a brain](/build/testing/) — port it, then prove it without a microphone.
