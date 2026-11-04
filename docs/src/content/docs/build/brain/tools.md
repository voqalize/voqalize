---
title: Tools
description: Tools on the shipped model brains are local async functions. How to declare them, speak first and call in the same response, mark the reads the model needs now, and return within 20 ms.
---

A tool is an ordinary async function in the process you deploy, so it keeps your
stack traces, connection pools and secrets. What voice changes is the clock:
every tool runs while the user waits for the agent's next word.

## Which brains have tools

`tools` is a member of the shipped model brains, `GeminiBrain`, `OpenAIBrain` and
`LiteLLMBrain`. All three run one tool loop, so everything on this page applies
to each, and a brain moves between them by changing only its constructor
([the constructors](/reference/brain/#the-constructors)). Install the extra for
your model:

```bash
pip install "voqalize-agent-sdk[gemini]==0.12.0"    # or [openai], or [litellm]
```

A plain `Brain` has no `tools` member: it calls its own functions from its own
loop ([Bringing an agent you already have](/build/existing-agent/)).
`GeminiInteractionsBrain` takes the same tool list but runs it differently and
is experimental; see [the shipped adapters](/reference/brain/#the-shipped-adapters).

## Declare tools as bound methods

`tools` is a property returning bound methods. There is no decorator and no
registry:

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
                "When you use a tool, say what you are doing or showing "
                "in the same response as the call."
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

**The method is the declaration.** Its name is what the model calls, its
docstring is the description the model reads, and its parameter is the schema.

### `async def` is required

A synchronous tool raises `TypeError` ("must be `async def`…"), because it would
block every session in the process. The check runs when a turn first reads
`tools`, not at import: the session opens, the greeting plays, and the first
turn fails with `brain: turn failed` in your log and no speech. Drive one turn in
[the conformance harness](/build/testing/) and assert `turn.completed` to catch
it.

### One pydantic model, or no parameters

| Brain | Parameters a tool may take |
|---|---|
| `GeminiBrain` | One pydantic model, or none. |
| `OpenAIBrain`, `LiteLLMBrain` | One pydantic model, plain parameters (`str`, `int`, `Literal`…), or none. All are validated before the tool runs, and a validation error goes back to the model to correct. |

On the Gemini brains, flat parameters are not validated: a bare `Literal`,
`Enum`, `date`, `Decimal` or `UUID` can fail at call time (the model is told
`{'error': …}` and may report success) or arrive as a plain string. Inside a
model the same field parses on every brain, so write one model and the tool
moves between brains unchanged. Nested models are fine everywhere.

### `session` is never a parameter

The signature is the schema, so a `session` parameter is a field the model would
try to fill. Inside a tool, use `self.session`; the brain is one instance per
session.

### The list is read once per turn

`tools` is read at the top of each turn and fixed for that turn, so it can depend
on the user and on what has happened so far:

```python
    @property
    def tools(self):
        if self.authenticated:
            return [self.show, self.get_balance, self.get_statement]
        return [self.show, self.show_sign_in]
```

A tool the model cannot see is one it cannot call, which is a stronger guarantee
than a line in the prompt.

## Speak first, and call in the same response

A turn is **one model request**. Each call in the response runs as it arrives,
after the speech before it has gone out, so *"Opening your meals now."* is heard
as the screen changes. Its result goes into the context and is read with the
next request, which is normally the user's next message.

```
[ "Opening your meals now."  → show() ]   the turn ends; "shown" waits in the context
```

So the line the user hears around a call is the model's, and the rule belongs in
the prompt and the tool's docstring:

- **Say the substantive line in the same response as the call**: what you are
  doing or showing ("Opening your meals now", "It's on your screen to confirm").
- **Never add a filler line** ("Let me check"). With ack on (the default),
  Voqalize already acknowledged the user when their turn ended
  ([Speaking](/build/brain/speaking/#voqalize-covers-the-wait-before-your-first-word)).
  A brain that writes its own acknowledgements turns ack off with
  `await session.configure(Config(ack=AckConfig(enabled=False)))`.

A response that calls a tool and says nothing leaves the user in silence until
they speak again, and after ten seconds Voqalize says *"Sorry — that's taking
longer than I expected."* The `turn:` log line reports `speechless=yes` for those
turns. Fix the prompt, or give the brain a floor: speak a written line with
`say_line`, or ask once more with tools off,
`respond_with(session, tools=ToolChoice.NONE)`
([the members](/reference/brain/#the-members)).

## Mark the reads the model needs now

Some results *are* the reply: the balance the user asked for, the cart, what is
on screen. Mark those with `@needs_result_now`, and the brain asks the model again
as soon as the response that called it finishes, with every result that response
produced, so the model answers in the same turn. In the example above,
`weekly_average` is marked; `show` and `log_meal` are not.

**Mark a tool when it reads data the model needs to answer correctly**: a
balance, a cart, the screen, an eligibility check. Leave it off everything else:
actions, screen changes, sign-in prompts, language switches, and results that
repeat what the model already said. Unmarked is the default.

Both mistakes are audible:

- **A read left unmarked**: the agent says its line, calls, goes quiet, and
  answers from the result a turn late.
- **A mark that is not needed**: a pause before every reply that calls it, the
  length of a whole model round trip.

`needs_result_now` lives in `voqalize.sdk.voice`, and `voqalize.sdk.gemini`,
`voqalize.sdk.openai` and `voqalize.sdk.litellm` each re-export it. It only sets
an attribute, so it combines with other decorators that keep attributes.

**`max_tool_hops`** (default `6`) caps how many times one turn asks again. The last
request may not call a tool, so the model must answer, and a warning is logged.
Unmarked tools never ask again, so they never count.

## A tool returns within 20 ms

Until a tool returns, nothing after the call in that response is spoken, and a
marked tool's second request cannot start. So a tool reads memory, dispatches to
the screen, starts background work if any, and returns. `TOOL_BUDGET_MS` in
`voqalize.sdk.voice` is `20`.

Every tool is timed. Over budget, one warning is logged and nothing is cancelled:

```
tool Coach.weekly_average took 412ms, over the 20ms budget; the user waited for it
```

Work that takes longer (a search, a payment, a report) is two pieces: a tool
that starts it and returns a note the model can speak about, and the result
arriving later as context. `session.dispatch(...)` never blocks, so a tool can
move the screen while the voice carries on ([Actions](/build/brain/actions/)).
[Parallel workstreams](/design/#parallel-workstreams) shows where the slow half
goes.

## A tool that needs a person announces and returns

No tool waits for the user. For a confirmation, a sign-in or a choice, the tool
puts it on the screen and returns at once. The user's answer reaches the brain
later as an app event at `on_rtvi`, which adds it to the context. A tap never
starts the agent talking ([RTVI](/reference/rtvi/#to-your-brain)).

```python
import uuid
from typing import Literal

from google import genai
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
                    return  # not a sheet this session has open
                verdict = "confirmed" if e.answer == "yes" else "declined"
                self.append_note(f"On screen, the user {verdict}: {summary}")
```

- **The nonce** binds an answer to its sheet, so a tap on a sheet that is no
  longer open changes nothing.
- **The decline path** (a `"no"` your app sends when the user dismisses the
  sheet) tells the model the question is closed.
- **The commit belongs to the tap**, in your app, not to the model.

`append_note` adds one sentence to the context without starting a turn. The
model reads it with the user's next message, or with a marked tool's second
request if one is running.

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

The answer is never spoken, so no `Turn` carries it: assert on what the model is
handed with the next message. [Testing a brain](/build/testing/) has the rest of
the driver.

## Write results for the model, not the ear

No shipped brain speaks a return value. It goes into the context, and the model
decides what to say about it. So a tool that finds eleven rows puts them on the
screen with `session.dispatch(...)` and returns what the model needs to speak
about them: how many, which one answers the question, what to ask next. Mark
that tool, because the model speaks from it this turn.

Return a short string or a value that survives `json.dumps`. Anything else is
turned into a string, so an object with only a `repr` reaches the model as that
`repr`, and the model may read it aloud.

## What leaves your process

A tool's **arguments and result never leave your process**, and there is no
webhook to expose: the call is a function call. Its **name, duration and counts**
are reported to Voqalize as a `TurnStep`, beside each model request's token
counts, so the call record shows where a slow turn spent its time. Build the
brain with `report_steps=False` to keep steps off the wire
([`report_step`](/reference/brain/#methods)).

## Read next

- [Tool design for voice](/design/#tool-design-for-voice): the argument, at length.
- [Context and history](/build/brain/context/): app events, and making state readable.
- [Testing a brain](/build/testing/): drive tools over the real wire.
