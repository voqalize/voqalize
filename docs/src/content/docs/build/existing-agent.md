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

The adapters we ship are `GeminiBrain` and `GeminiInteractionsBrain`, both for
Gemini. There is no ADK adapter, no LangChain adapter and no OpenAI Agents
adapter, and none is coming.

An adapter is a second surface to learn and a lag behind every release of a
framework we do not own. Read what the Gemini ones actually spend their code on:
`GeminiBrain._file` puts each tool's response in the context directly after the
call that asked for it, so that context appended while the tool ran lands behind
the pair rather than between them, and `GeminiBrain._drop_unanswered` removes a
`function_call` whose `function_response` never arrived because a barge-in cut
the stream between them (`sdk/python/src/voqalize/sdk/gemini.py`). Neither is
about voice. Both are about one provider's turn record, and both break when that
provider changes it.

The boundary Voqalize holds is text. Nothing in the wire declares a tool,
carries a schema or names a model: `proto/voqalize/frames/frames.proto` has
frames for speech, transcripts, configuration, RTVI and errors, and there is no
tool frame in it. So there is nothing for an adapter to sit between — your
stream of strings goes out as speech, and the user's finalized text comes back
in.

## The port

Subclass `Brain`, call your existing entrypoint from `on_user_message`, and
record what the user heard. Against a framework whose entrypoint is
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
        yield SpeechStart()
        async for piece in self.agent.run(msg.text):
            yield SpeechChunk(piece)
        yield SpeechEnd()

    async def on_finalize(self, session, fin):
        if fin.heard:
            self.agent.history.append({"role": "assistant", "content": fin.heard})
```

`msg.text` is one finalized utterance. `SpeechStart` / `SpeechChunk` / `SpeechEnd` are
one **speech unit** — the granularity at which a user can cut you off and the
granularity at which Voqalize reports back what they heard. Yield the chunks as
your framework produces them; awaiting between them is what a tool call inside a
turn looks like. [Speaking](/build/brain/speaking/) owns the frames.

You host this the same way as any other brain, and the choice is unrelated to
the port — [Where the brain runs](/build/hosting/). The class is what you hand
over, not an instance: the SDK constructs one per session, so a framework object
built in `__init__` belongs to that call and leaks nothing into the next.
Per-user setup that needs an identifier goes in `on_session_start`, which reads
`session.init` and runs before the greeting —
[Context and history](/build/brain/context/).

### One turn, several units

The fence above opens a unit before your framework has produced anything. If
`run()` calls a tool before its first token, the user is holding an open unit
and hearing nothing. Open lazily instead, and the turn mints a unit only when
there is something to say:

```python
    async def on_user_message(self, session, msg):
        speaking = False
        async for piece in self.agent.run(msg.text):
            if not speaking:
                yield SpeechStart()
                speaking = True
            yield SpeechChunk(piece)
        if speaking:
            yield SpeechEnd()
```

That is what `GeminiBrain.respond` does — a response that only calls a tool
never opens a unit at all. Opening one per response is what used to emit an empty
`SpeechStart` / `SpeechEnd` pair around a silent tool call
(`sdk/python/src/voqalize/sdk/gemini.py`, `respond`).

Lazy opening removes the empty bracket. It does not remove the silence: the tool
runs for as long as it runs and the user sits through it either way, and the
fix for that is to say what you are doing before you do it, or to move the screen
while the voice waits. `GeminiBrain` does both by construction: the model says its
line and calls in the same response, and every tool returns within 20 ms. [The turn budget](/design/#the-turn-budget) is the argument;
[Tools](/build/brain/tools/) is the mechanism.

Every unit that emitted text gets exactly one `on_finalize`, in the order the
units opened — including one that was generated and beaten to the speaker, which
arrives as `heard=""`. A turn that says a line, closes the unit, waits on a tool
and opens a second for the answer produces two units and two finalizes.

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

A user can interrupt mid-word. What your model generated and what the user
heard are then two different strings, and only one of them is a thing both
parties can refer to. `on_finalize` hands you the delivered prefix as
`fin.heard`, per unit, after playout — long after the generator that produced it
returned (`sdk/python/src/voqalize/sdk/events.py`, `Finalize`). So:

- Turn off your framework's own append of the assistant turn, or rewrite that
  entry in place when the finalize arrives.
- Append `fin.heard`. A reply that generated three sentences and delivered one
  goes into history as one.
- Handle the empty case. `heard` is an empty string for a unit that reached no
  speaker, and that unit belongs out of your history entirely rather than in it
  as a sentence the model believes it said.

Nothing reports this when you get it wrong — no error, no log line, no metric —
and the user is the only instrument that sees it.
[Transcripts and heard truth](/build/brain/transcripts/) has the watermark and
the ordering rules; [Interruption and heard
truth](/design/#interruption-and-heard-truth) is the argument under them.

`GeminiBrain.on_finalize` is a shipped implementation of exactly this: it pops
the oldest unit still awaiting a finalize, rewrites that turn's text down to
`heard`, and drops the turn when nothing is left of it
(`sdk/python/src/voqalize/sdk/gemini.py`, `on_finalize` and `_reconcile`).
`sdk/python/tests/unit/test_gemini_heard_truth.py` pins the cases, including
that finalizes match units in order and that a unit nobody heard leaves the
context.

### The greeting is also history

`greet` returns a string the SDK speaks, so your framework never saw it. Its
finalize arrives with nothing of yours awaiting one — that is the branch in both
adapters that appends `fin.heard` as a fresh model turn rather than rewriting an
existing one. Skip it and the model does not know it greeted, and asks its
opening question a second time.

### Keep the conversation in your process

If your framework holds history on the provider's server — a stored conversation
id that each call continues — heard truth cannot be applied to it. A server-side
conversation cannot be told that the user only heard half of the last sentence.
`GeminiInteractionsBrain` sends `store=False` and no `previous_interaction_id`
for that reason, and carries the whole context on every call
(`sdk/python/src/voqalize/sdk/gemini_interactions.py`, `_stream`). Port to a
local history list and the rewrite is a list mutation.

## Where the Gemini adapters fit

Both are worked examples of the port above, not a supported-frameworks list.
[The Brain API](/reference/brain/#the-shipped-adapters) has the constructor
they share, the members they offer, and which of them to build on.

The differences that matter while porting are in the tool loop, and both
adapters run their own. `GeminiBrain` makes one request per turn and files each
tool's result for the next request, which is the user's next message unless the
tool is marked `@needs_result_now`; then it asks again at once
([Tools](/build/brain/tools/#when-the-model-reads-a-result) has the rule for
which tools earn the mark). `GeminiInteractionsBrain` asks again after every
response that made a call. Both re-read the whole context on every request, so
an append that lands while a tool is running reaches the model with the next
request either of them makes, and both apply heard truth per unit of speech.

## What changes about the agent itself

Nothing above touches the prompt, and the prompt is where a ported agent
actually goes wrong first. A chat prompt can afford a lookup, because the reader
watches a spinner while it happens. Said out loud, the same two seconds are
silence on a channel where silence is the one thing a user reacts to — so what
the agent needs, it should mostly already have, and what it says has to survive
having no scrollback.

That is a design problem rather than an SDK one, and it has its own section:
[Designing for voice](/design/), starting with
[Prompt design for voice](/design/#prompt-design-for-voice).

## Read next

- [Your first brain](/build/brain/) — the callbacks you are subclassing.
- [Tools](/build/brain/tools/) — what a voice tool owes the user.
- [Testing a brain](/build/testing/) — port it, then prove it without a microphone.
