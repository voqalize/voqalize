---
title: Tools
description: Tool calls are local function calls in your process. What that changes, and what a voice tool owes the caller that a chat tool does not.
---

The boundary Voqalize holds is text, so what generates the text is yours — and so
are the tools. A tool call is an ordinary function call in the process you
deploy: you keep the stack trace, the connection pool and the secret. What
changes for voice is not the mechanism but the clock, because a caller is
listening to silence while the tool runs.

## `Brain` has no tools property

There is no tool frame on [the wire](/reference/wire/) and no `tools` member on
`Brain`. A brain that loops over its own model stream calls its own functions,
and the SDK never sees one — [bringing an agent you already
have](/build/existing-agent/) is that port, and it is unchanged by voice.

`tools` is a member of the **two shipped Gemini adapters**, `GeminiBrain` and
`GeminiInteractionsBrain`, and the rest of this page is the contract they share.
The two run the loop in different places
([the Brain API](/reference/brain/#the-two-shipped-adapters) has that split), and
they take the same list, so a brain moves between them without touching its
tools.

## The declaration contract

`tools` is an overridable property returning bound methods. There is no
decorator and no registry:

```python
from typing import Literal

from google import genai
from pydantic import BaseModel, Field

from voqalize.sdk import Action
from voqalize.sdk.gemini import GeminiBrain


class ShowSection(Action):
    name: str


class Section(BaseModel):
    """Which part of the screen to show."""

    name: Literal["glucose", "meals"] = Field(description="Section to show.")


class Coach(GeminiBrain):
    def __init__(self, meals) -> None:
        super().__init__(
            client=genai.Client(),
            system_instruction="You are a diabetes coach. Answer in a sentence or two.",
        )
        self.meals = meals

    @property
    def tools(self):
        return [self.show, self.log_meal]

    async def show(self, args: Section) -> str:
        """Put a section of the screen in front of the caller."""
        self.session.dispatch(ShowSection(name=args.name))
        return "shown"

    async def log_meal(self) -> str:
        """Record that the caller ate, now."""
        await self.meals.record(self.session.id)
        return "logged"
```

**The method is the declaration.** Its name is the name the model calls, its
docstring is the description the model reads, and its single pydantic-model
parameter is the schema. Nothing is declared twice, so there is no second copy
to drift (`sdk/python/src/voqalize/sdk/gemini.py`, `tools`).

Four rules bite.

### `async def` is required, and it fails on the first turn

Both adapters refuse a synchronous tool with a `TypeError`. The automatic path
says why at length, because that is where the half-working version used to
ship:

```
tool 'log_meal' must be `async def`. A sync tool runs on a worker thread, off the
loop, so the first self.session.dispatch(...) it grows reaches a loop that is not
running. Make it `async def` — the body needs no other change.
```

Read where that check runs, because the timing is the trap. Tools are read
inside `respond`, which runs inside the turn task — `_ready` on the automatic
path, `_declare` on the interactions path. So a sync tool is not an import
error and not a startup error: the session opens, the greeting plays, and the
`TypeError` lands on the first turn that reads `tools`. The turn task catches
it, writes `brain: turn failed` to your log, and produces no speech
(`sdk/python/src/voqalize/sdk/brain.py`, `_run_turn`). The caller asked a
question and heard nothing back.

Drive one turn in [the conformance harness](/build/testing/) and assert
`turn.completed`; that is the assertion this failure trips.

### Exactly one pydantic model, or nothing at all

A tool takes one model parameter — or, like `log_meal` above, no parameters,
which declares none rather than an empty object. Nested models are fine on both
adapters: the schema goes over as JSON Schema with its `$defs` intact.

The reason is not that flat parameters are unsupported. A flat `str`, `int`,
`bool` or `list[str]` runs on both adapters. It is that a flat parameter is the
one place **neither adapter parses what the model sent**, and the two get that
wrong in opposite directions.

On the automatic path google-genai checks each flat argument with `isinstance`
and coerces nothing. A bare `Literal` raises immediately — `isinstance` refuses a
subscripted generic — and a bare `Enum`, `date`, `Decimal` or `UUID` is rejected
as the JSON string it still is. Both are caught into `{'error': …}` and handed to
the model, which narrates it to the caller as success. The tool never ran, the
schema was right, the stream was well-formed, and nothing on the wire says
otherwise.

On the interactions path the same tool executes. It parses the model parameter
and passes every other argument through untouched, so your `date` arrives as a
`str` and the tool is wrong quietly rather than loudly.

A single model parameter is the only annotation *either* path validates. That is
why the wrapper is not a workaround for `Literal` specifically: `Section` above
carries a `Literal`, and inside a model it parses on both adapters. Written flat,
the same field is the version that breaks:

```python
    # Declares a correct schema, then fails to execute on the automatic path.
    async def show(self, section: Literal["glucose", "meals"]) -> str:
        """Put a section of the screen in front of the caller."""
```

### `session` is never a parameter

The signature *is* the schema, so a `session` parameter is a field the model
would try to fill. Tools read `self.session`; callbacks take the parameter they
are handed. The line between them is whether we call it or the model does
(`sdk/python/src/voqalize/sdk/brain.py`, `Brain.session`).

`self.session` inside a tool reaches the session serving this call, because the
brain is one instance per session and nothing about it crosses to the provider.
On the automatic path that costs a closure: google-genai deep-copies the config
it is handed, once on entry and again on every hop, and `copy.deepcopy` of a
bound method copies `__self__` with it. A bound method that crossed that line
would have its tools called on a *clone* — `self.session.dispatch` reaching
nothing, the model told `ok`, and not one frame on the wire to say so. So a
plain function is what goes over and the brain stays here
(`sdk/python/src/voqalize/sdk/gemini.py`, `_ready`;
`sdk/python/tests/unit/test_gemini_turn.py`,
`test_the_brain_is_not_handed_to_google_genai`).

### The property is read once per turn

Once, at the top of the turn, and fixed for its length however many hops it
takes. So the list can depend on this caller and on what has happened so far in
the session:

```python
    @property
    def tools(self):
        if self.authenticated:
            return [self.show, self.get_balance, self.get_statement]
        return [self.show, self.authenticate]
```

A tool the model cannot see is a tool it cannot call, which is a stronger
guarantee than a sentence in the prompt asking it not to. Both adapters pin this
in `test_the_tools_are_read_once_per_turn`
(`sdk/python/tests/unit/test_gemini_turn.py` and
`sdk/python/tests/unit/test_gemini_interactions_turn.py`).

## The call is a function call in your process

There is no webhook to expose, no allowlist to file and no egress rule to open,
because nothing about a tool leaves your process: the wire carries speech,
transcripts, configuration, RTVI and errors, and no frame that declares a tool
or carries a schema. The same tool reached as a webhook is a network round trip
on every turn that uses it, plus a public endpoint to authenticate and an
inbound path to your network to justify.

What that buys is measured in what stays put. Your model client and its keys,
your retrieval, your database session and your connection pool are reached by
`self`, from a coroutine running in the turn's own task — no serialization, no
second set of credentials, no schema of yours living somewhere you do not
deploy. What happens when one of those raises is
[tool design for voice](/design/tool-design/); it is a result the model reads,
and a line in your log.

## Silence during a tool call is dead air

The model cannot speak while it waits for a result it asked for, and the caller
has no spinner. So the first thing a voice tool needs is a sentence in front of
it.

A turn that narrates, calls a tool and then reports back is **two speech units
under one turn id** — [Speaking](/build/brain/speaking/) owns that rule — and the
first one is already playing while the tool runs:

```
[ "Let me look that up." ]   → show()   → [ "You're averaging 6.4." ]
```

That shape is the model's decision, not the SDK's, which means the instruction
belongs where the model reads it — **the docstring, which is the description**.
`aura`'s `authenticate` says so in the tool itself
(`demos/aura/backend/brain.py`):

```python
    async def authenticate(self) -> str:
        """Sign the customer in securely, on screen, before anything to do with
        THEIR money — balance, statement, or card.

        This opens a sign-in sheet and waits for them to finish it, so say one
        short line first ("let me get you signed in securely") and expect a
        pause. …"""
```

The second lever is the screen. `session.dispatch(...)` never blocks and holds
no floor, so a tool can move the display on its first line and let the caller
read while the voice is still working — [Actions](/build/brain/actions/) owns
that channel. A tool that is slower than a sentence should return a note instead
of a result; [tool design for voice](/design/tool-design/) is that argument, and
[parallel workstreams](/design/parallel-workstreams/) is where the slow half
goes.

Every hop is a model round trip, and `max_tool_hops` (default 6) is how many of
them may call a tool. Count them against [the turn budget](/design/turn-budget/).

## A blocking tool needs the turn in flight

One tool is allowed to wait: the one waiting on a human decision. It works
because the turn and the app's messages run in different tasks — the SDK spawns
each turn as its own task and each RTVI message as an ambient one
(`sdk/python/src/voqalize/sdk/brain.py`, `_spawn_turn` and `_deliver_rtvi`) — so
`on_rtvi` can resolve a future that a tool inside a live turn is awaiting.

```python
import asyncio
import uuid

from google import genai
from pydantic import BaseModel

from voqalize.sdk import Action, RTVIType
from voqalize.sdk.gemini_interactions import GeminiInteractionsBrain


class OpenConfirm(Action):
    nonce: str
    summary: str


class ConfirmArgs(BaseModel):
    """The booking to confirm, in one line the caller can read."""

    summary: str


class Booking(GeminiInteractionsBrain):
    def __init__(self) -> None:
        super().__init__(
            client=genai.Client(),
            system_instruction="You book appointments. Confirm on screen before you commit.",
        )
        self._pending: dict[str, asyncio.Future[str]] = {}

    @property
    def tools(self):
        return [self.confirm_on_screen]

    async def confirm_on_screen(self, args: ConfirmArgs) -> str:
        """Put the booking in front of the caller and wait for them to tap
        Confirm. This opens a sheet and waits, so say one short line first
        ("let me put that on screen for you") and expect a pause."""
        nonce = uuid.uuid4().hex
        pending = asyncio.get_running_loop().create_future()
        self._pending[nonce] = pending
        self.session.dispatch(OpenConfirm(nonce=nonce, summary=args.summary))
        try:
            answer = await asyncio.wait_for(pending, 90)
        except TimeoutError:
            return "The caller never answered the sheet. Offer to try again."
        finally:
            self._pending.pop(nonce, None)
        if answer == "yes":
            return "confirmed"
        return "The caller declined. Acknowledge it and offer another slot."

    async def on_rtvi(self, session, msg) -> None:
        if msg.type is not RTVIType.CLIENT_MESSAGE or not isinstance(msg.data, dict):
            return
        if msg.data.get("t") != "confirm_answer":
            return
        data = msg.data.get("d") or {}
        pending = self._pending.get(data.get("nonce", ""))
        if pending is not None and not pending.done():
            pending.set_result(data.get("answer", "no"))
```

Three things in there are load-bearing. The **nonce** binds this dialog to this
future; without it the app's answer resolves nothing and the turn runs out its
timeout while the caller sits in silence. The **cancel path** — a `"no"` the app sends when
the caller dismisses the sheet — is what stops a dismissed dialog going silent
for the length of the timeout, so give the app something to send and handle it.
And the **timeout** is a backstop, not the escape hatch; the caller pressing
something is.

Test it with the turn in flight, because the turn does not finish until the tool
returns:

```python
in_flight = asyncio.create_task(driver.user_says("Book the nine o'clock."))
commands = await driver.collect_ui_commands(min_count=1)
assert commands[0]["command"] == "open_confirm"
assert not in_flight.done(), "the tool returned before the caller answered"

await driver.send_client_message(
    "confirm_answer", {"nonce": commands[0]["payload"]["nonce"], "answer": "yes"}
)
turn = await in_flight
assert turn.completed
```

`await driver.user_says(...)` on its own blocks until the driver's timeout: it
is waiting for the turn, and the turn is waiting for a message nothing has sent.
[Testing a brain](/build/testing/) has the rest of the driver.

## A tool result is for the model, not the ear

Nothing in either adapter speaks a return value. It goes into the context as a
function result and the model decides what to say about it, on the hop after
(`sdk/python/src/voqalize/sdk/gemini.py`, `_fold_results`;
`sdk/python/src/voqalize/sdk/gemini_interactions.py`, `_run`).

That absence is why a tool returning a row set has not decided anything. Eleven
rows read out loud is a caller with no memory of row four; the rows go to the
screen with `session.dispatch(...)` and the return value tells the model what to
say about them — how many there are, which one is the answer, what to ask next.
Write the return value as the sentence's raw material rather than as the
sentence.

Return something the model can read: a short string, or a value that survives
`json.dumps`. `GeminiInteractionsBrain` writes the return value into the context
as `{"result": …}` with `default=str`, so an object with nothing but a `repr`
reaches the model as that `repr` and the model reads it aloud as a fact
(`sdk/python/src/voqalize/sdk/gemini_interactions.py`, `_run`).

## Read next

- [Tool design for voice](/design/tool-design/) — the argument, at length.
- [Parallel workstreams](/design/parallel-workstreams/) — work that outlives a turn.
