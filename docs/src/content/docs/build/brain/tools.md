---
title: Tools
description: Tool calls are local function calls in your process. The model speaks and then calls, a tool returns at once, and a result waits for the next request unless the model needs it now.
---

The boundary Voqalize holds is text, so what generates the text is yours — and so
are the tools. A tool call is an ordinary function call in the process you
deploy: you keep the stack trace, the connection pool and the secret. What
changes for voice is not the mechanism but the clock, because every tool runs
while the user waits for the agent's next word.

## `Brain` has no tools property

There is no tool frame on [the wire](/reference/wire/) and no `tools` member on
`Brain`. A brain that loops over its own model stream calls its own functions,
and the SDK never sees one — [bringing an agent you already
have](/build/existing-agent/) is that port, and it is unchanged by voice.

`tools` is a member of the **shipped Gemini adapters**, `GeminiBrain` and
`GeminiInteractionsBrain`, and the rest of this page is the contract they share.

:::caution[`GeminiInteractionsBrain` is experimental]
Every demo brain runs on `GeminiBrain`, and the last one that did not moved across
on 2026-09-08. The interactions adapter's interruption path has open defects —
a step interrupted before its first delta stays in the context forever, and text
buffered during a step is discarded if a barge-in lands before the step
closes. Build on `GeminiBrain`; this one is kept, and tested, for the
properties it has that `generate_content` does not.
:::

They take the same list, so a brain moves between them without touching its
tools. They do not run it the same way:
[the Brain API](/reference/brain/#the-shipped-adapters) has that split, and
[when the model reads a result](#when-the-model-reads-a-result) below is what it
means for a turn.

## The declaration contract

`tools` is an overridable property returning bound methods. There is no
decorator and no registry:

```python
from datetime import UTC, datetime
from typing import Literal

from google import genai
from pydantic import BaseModel, Field

from voqalize.sdk import Action
from voqalize.sdk.gemini import GeminiBrain, needs_result_now


class ShowSection(Action):
    name: str


class Section(BaseModel):
    """Which part of the screen to show."""

    name: Literal["glucose", "meals"] = Field(description="Section to show.")


class Coach(GeminiBrain):
    def __init__(self) -> None:
        super().__init__(
            client=genai.Client(),
            system_instruction=(
                "You are a diabetes coach. Answer in a sentence or two. "
                "When you use a tool, say one short line and call it in the same response."
            ),
        )
        self.readings: list[float] = []  # this user's week, loaded in on_session_start
        self.meals: list[datetime] = []

    @property
    def tools(self):
        return [self.show, self.log_meal, self.weekly_average]

    async def show(self, args: Section) -> str:
        """Put a section of the screen in front of the user."""
        self.session.dispatch(ShowSection(name=args.name))
        return "shown"

    async def log_meal(self) -> str:
        """Record that the user ate, now."""
        self.meals.append(datetime.now(UTC))
        return "logged"

    @needs_result_now
    async def weekly_average(self) -> str:
        """The user's average glucose this week, in mmol/L."""
        if not self.readings:
            return "No readings this week."
        return f"{sum(self.readings) / len(self.readings):.1f}"
```

**The method is the declaration.** Its name is the name the model calls, its
docstring is the description the model reads, and its single pydantic-model
parameter is the schema. Nothing is declared twice, so there is no second copy
to drift (`sdk/python/src/voqalize/sdk/gemini.py`, `tools`).

Every tool here reads or writes memory and returns. `weekly_average` is the one
whose result the model has to read before it can finish its sentence, so it is
the one marked; [when the model reads a result](#when-the-model-reads-a-result)
is why the other two are not.

These rules bite.

### `async def` is required, and it fails on the first turn

Both adapters refuse a synchronous tool with a `TypeError`. `GeminiBrain` says
why:

```
tool 'log_meal' must be `async def`. A tool runs in the turn's task on the event
loop, and a sync one would block every session in the process while it ran. Make
it `async def` — the body needs no other change.
```

Read where that check runs, because the timing is the trap. Tools are read
inside `respond`, which runs inside the turn task — `_ready` on `GeminiBrain`,
`_declare` on `GeminiInteractionsBrain`. So a sync tool is not an import
error and not a startup error: the session opens, the greeting plays, and the
`TypeError` lands on the first turn that reads `tools`. The turn task catches
it, writes `brain: turn failed` to your log, and produces no speech
(`sdk/python/src/voqalize/sdk/brain.py`, `_run_turn`). The user asked a
question and heard nothing back.

Drive one turn in [the conformance harness](/build/testing/) and assert
`turn.completed`; that is the assertion this failure trips.

### Exactly one pydantic model, or nothing at all

A tool takes one model parameter — or, like `log_meal` above, no parameters,
which declares none rather than an empty object. Nested models are fine on both
adapters: the schema goes over as JSON Schema with its `$defs` intact.

The reason is not that flat parameters are unsupported. A flat `str`, `int`,
`bool` or `list[str]` runs on both adapters. It is that a flat parameter is the
one place **neither adapter parses what the model sent**, and they get that
wrong in opposite directions.

`GeminiBrain` builds the call with google-genai's own argument conversion, which
checks each flat argument with `isinstance` and coerces nothing. A bare `Literal`
raises immediately — `isinstance` refuses a subscripted generic — and a bare
`Enum`, `date`, `Decimal` or `UUID` is rejected as the JSON string it still is.
Both are caught into `{'error': …}` and handed to the model, which narrates it to
the user as success. The tool never ran, the schema was right, the stream was
well-formed, and nothing on the wire says otherwise; the one trace is a
`tool … failed` line in your log.

On `GeminiInteractionsBrain` the same tool executes. It parses the model parameter
and passes every other argument through untouched, so your `date` arrives as a
`str` and the tool is wrong quietly rather than loudly.

A single model parameter is the only annotation *either* path validates. That is
why the wrapper is not a workaround for `Literal` specifically: `Section` above
carries a `Literal`, and inside a model it parses on both adapters. Written flat,
the same field is the version that breaks:

```python
    # Declares a correct schema, then fails to execute on GeminiBrain.
    async def show(self, section: Literal["glucose", "meals"]) -> str:
        """Put a section of the screen in front of the user."""
```

### `session` is never a parameter

The signature *is* the schema, so a `session` parameter is a field the model
would try to fill. Tools read `self.session`; callbacks take the parameter they
are handed. The line between them is whether we call it or the model does
(`sdk/python/src/voqalize/sdk/brain.py`, `Brain.session`).

`self.session` inside a tool reaches the session serving this call, because the
brain is one instance per session and nothing about it crosses to the provider.
On `GeminiBrain` that costs a closure: google-genai deep-copies the config it is
handed on every request, and `copy.deepcopy` of a bound method copies
`__self__` with it. A bound method that crossed that line
would have its tools called on a *clone* — `self.session.dispatch` reaching
nothing, the model told `ok`, and not one frame on the wire to say so. So a
plain function is what goes over and the brain stays here
(`sdk/python/src/voqalize/sdk/gemini.py`, `_ready`;
`sdk/python/tests/unit/test_gemini_turn.py`,
`test_the_brain_is_not_handed_to_google_genai`).

### The property is read once per turn

Once, at the top of the turn, and fixed for its length however many requests it
makes. So the list can depend on this user and on what has happened so far in
the session:

```python
    @property
    def tools(self):
        if self.authenticated:
            return [self.show, self.get_balance, self.get_statement]
        return [self.show, self.show_sign_in]
```

A tool the model cannot see is a tool it cannot call, which is a stronger
guarantee than a sentence in the prompt asking it not to. The contract suite pins
this against both adapters in `test_the_tools_are_read_once_per_turn`
(`sdk/python/tests/contract/test_brain_contract.py`).

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
[tool design for voice](/design/#tool-design-for-voice); it is a result the model reads,
and a line in your log.

## When the model reads a result

On `GeminiBrain` a turn is **one request**. Each function call in the model's
response runs the moment it arrives, in stream order, after the speech in front
of it has gone out — so *"Opening your meals now."* is heard as the screen
changes, not after it. The result goes into the context directly after the call,
and the model is not asked again for it: it reads the result with the next
request, which is normally the user's next message.

```
[ "Opening your meals now."  → show() ]   the turn ends; "shown" waits in the context
```

So the model's reply is decided in one response, and what the user hears around
a call is the model's choice rather than the SDK's. The instruction belongs where
the model reads it — the prompt, and the tool's docstring: **say one short line,
and call the tool in the same response.** `aura`'s sign-in tool says so in the
tool itself (`demos/aura/backend/brain.py`):

```python
    async def show_auth_popup(self) -> str:
        """Put a secure sign-in on the customer's screen. …

        Returns as soon as the sheet is up. It does NOT wait: the customer
        authorises it in their own time, and you are told when they have and handed
        an ``authenticated_context`` then. Say one short line ("I'll put a secure
        sign-in on your screen") and carry on being useful. …"""
```

A response that calls a tool and says nothing leaves the user in silence until
they speak again. The turn has produced no text, so after ten seconds Voqalize
fills the silence with a line of its own — *"Sorry — that's taking longer than I expected."*
([Speaking](/build/brain/speaking/#the-clock-between-units-is-yours) has that
watchdog). Fixing it is the prompt's job, or the brain's, by speaking a line of
its own. The `turn:` line `GeminiBrain` logs for every turn reports
`speechless=yes` when it happened, beside `hops=`, `calls=` and `awaited=`, so you
can count how often it does.

### `@needs_result_now`, for the result the model must read first

Some results *are* the reply: the balance the user asked for, what is in the
cart, what is on the screen right now. Mark those tools, and `GeminiBrain` asks
the model again the moment the response that called one has finished, with every
result that response produced, so the model speaks about it in the same turn:

```python
from pydantic import BaseModel

from voqalize.sdk import Action
from voqalize.sdk.gemini import GeminiBrain, needs_result_now


class ShowCardControls(Action):
    pass


class Account(BaseModel):
    """One of the user's accounts."""

    number: str


class Desk(GeminiBrain):
    async def show_card_controls(self) -> str:
        """Put the card controls on screen."""
        self.session.dispatch(ShowCardControls())
        return "shown"

    @needs_result_now
    async def get_account_balance(self, args: Account) -> dict[str, str]:
        """The balance of one of the user's accounts."""
        return self.accounts[args.number].balance()
```

**Mark a tool when it reads data the model needs to answer correctly** — a
balance, a cart, the screen, an eligibility check — from memory. Leave it off
everything else: actions, screen changes, sign-in prompts, language switches, and
a tool whose result only repeats what the model already said. Unmarked is the
default, and the right answer for most tools.

Both mistakes are audible. A read that is missing the mark sounds like an agent
that says its line, calls the tool and goes quiet, then answers from the result
a turn late, when the user next speaks. A mark on a tool that does not need it
sounds like a pause before every reply that calls it: the second request is a
whole model round trip of silence, which is why it is not the default.

The mark sets an attribute on the function and does nothing else, so it goes on
a method or a free function, above or below other decorators that keep
attributes. It is imported from `voqalize.sdk.gemini`
(`sdk/python/src/voqalize/sdk/gemini.py`, `needs_result_now`).

`max_tool_hops` (default 6) caps how many times one turn asks again. The last of
those requests may not call a tool, so the model has to answer, and
`GeminiBrain` logs a warning when a turn reaches it. Unmarked tools never ask
again, so they never count against it.

`GeminiInteractionsBrain` ignores the mark. It asks the model again after every
response that made a call, marked or not, until one makes none or
`max_tool_hops` is spent — so every tool on it costs the turn a round trip.

## A tool returns within 20 ms

A tool runs in the turn's task, between one piece of speech and the next. Until
it returns, nothing after the call in that response is spoken, and a marked
tool's second request cannot start. So a tool reads memory, dispatches to the
screen, starts background work if it has any, and returns — `TOOL_BUDGET_MS` in
`voqalize.sdk.gemini` is 20.

`GeminiBrain` times every tool from the moment it is called to the moment it
returns. Over budget, it logs one warning and cancels nothing:

```
tool Coach.weekly_average took 412ms, over the 20ms budget; the user waited for it
```

A slow tool is still a tool that ran, and its result still counts. The warning
is how you find it before a user does. `GeminiInteractionsBrain` does not time
its tools.

Work that genuinely takes longer — a search, a payment, a report — is two
pieces: a tool that starts it and returns a note the model can say something
about, and the result arriving later as context. The screen is the other lever:
`session.dispatch(...)` never blocks and holds no floor, so a tool can move the
display and let the user read while the voice carries on —
[Actions](/build/brain/actions/) owns that channel.
[Tool design for voice](/design/#tool-design-for-voice) is the argument, and
[parallel workstreams](/design/#parallel-workstreams) is where the slow half
goes.

## A tool that needs a person announces and returns

No tool waits for the user. A confirmation, a sign-in, a choice between accounts:
the tool puts it on the screen and returns at once, and the user's answer
reaches the brain later as an app event, which the brain adds to the context.
The turn is over long before they tap — and a tap does not start the agent
talking, because nothing about a click means the person stopped speaking
([RTVI](/reference/rtvi/#to-your-brain) has that rule).

```python
import uuid
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel

from voqalize.sdk import Action, AppEvent, AppEvents
from voqalize.sdk.gemini import GeminiBrain


class OpenConfirm(Action):
    nonce: str
    summary: str


class ConfirmAnswered(AppEvent):
    nonce: str
    answer: Literal["yes", "no"]


EVENTS = AppEvents(ConfirmAnswered)


class ConfirmArgs(BaseModel):
    """The booking to confirm, in one line the user can read."""

    summary: str


class Booking(GeminiBrain):
    def __init__(self) -> None:
        super().__init__(
            client=genai.Client(),
            system_instruction=(
                "You book appointments. The user confirms a booking on screen; "
                "you never confirm one yourself."
            ),
        )
        self._open: dict[str, str] = {}

    @property
    def tools(self):
        return [self.confirm_on_screen]

    async def confirm_on_screen(self, args: ConfirmArgs) -> str:
        """Put the booking on the user's screen for them to confirm or decline.
        Returns as soon as the sheet is up; it does not wait. Say one short line
        with the call ("it's on your screen to confirm"). You will be told what
        they chose."""
        nonce = uuid.uuid4().hex
        self._open[nonce] = args.summary
        self.session.dispatch(OpenConfirm(nonce=nonce, summary=args.summary))
        return "The sheet is up. Wait to be told what they chose."

    async def on_rtvi(self, session, msg) -> None:
        match EVENTS.parse(msg):
            case ConfirmAnswered() as e:
                summary = self._open.pop(e.nonce, None)
                if summary is None:
                    return  # not a sheet this call has open
                verdict = "CONFIRMED" if e.answer == "yes" else "DECLINED"
                self.append_to_context(
                    types.Content(
                        role="user",
                        parts=[types.Part(text=f"ON SCREEN, THE USER {verdict}: {summary}")],
                    )
                )
```

The **nonce** binds an answer to the sheet it answers, so a tap on a sheet the
call no longer has open changes nothing. The **decline path** — a `"no"` the app
sends when the user dismisses the sheet — is what tells the model the question
is closed, so give the app something to send. And the commit belongs to the
tap, in your app, rather than to the model; the brain learns what happened.
Nothing waits, so there is no timeout to choose.

The context is read again on every request, so the answer reaches the model with
the user's next message — or with a marked tool's second request, if one is
running when it lands.

Test it as two steps, because the turn finishes on its own:

```python
import asyncio

turn = await driver.user_says("Book the nine o'clock.")
assert turn.completed  # the tool returned; nothing waited on the user

commands = await driver.collect_ui_commands(min_count=1)
sheet = next(c for c in commands if c["command"] == "open_confirm")
await driver.send_ui_event(
    "confirm_answered", {"nonce": sheet["payload"]["nonce"], "answer": "yes"}
)
await asyncio.sleep(0.1)  # on_rtvi opens no turn, so there is nothing to await
```

What the user chose opens no turn and is never spoken, so no `Turn` carries it.
It reaches the model as context: assert on what the model is handed with the
next message.
[Testing a brain](/build/testing/) has the rest of the driver.

## A tool result is for the model, not the ear

Nothing in either adapter speaks a return value. It goes into the context as a
function result and the model decides what to say about it with the next request
(`sdk/python/src/voqalize/sdk/gemini.py`, `_file`;
`sdk/python/src/voqalize/sdk/gemini_interactions.py`, `_run`). On `GeminiBrain`
that is the user's next message unless the tool is marked, so a result written
for an unmarked tool is read a turn later, as background to whatever the user
says next.

That absence is why a tool returning a row set has not decided anything. Eleven
rows read out loud is a user with no memory of row four; the rows go to the
screen with `session.dispatch(...)` and the return value tells the model what to
say about them — how many there are, which one is the answer, what to ask next.
Write the return value as the sentence's raw material rather than as the
sentence, and mark the tool: the model is speaking from it this turn.

Return something the model can read: a short string, or a value that survives
`json.dumps`. `GeminiInteractionsBrain` writes the return value into the context
as `{"result": …}` with `default=str`, so an object with nothing but a `repr`
reaches the model as that `repr` and the model reads it aloud as a fact
(`sdk/python/src/voqalize/sdk/gemini_interactions.py`, `_run`).

## Read next

- [Tool design for voice](/design/#tool-design-for-voice) — the argument, at length.
- [Parallel workstreams](/design/#parallel-workstreams) — work that outlives a turn.
