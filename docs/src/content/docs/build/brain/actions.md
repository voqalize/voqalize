---
title: Actions
description: The brain's second output. A typed message that renders on the page and is never spoken — declared as a pydantic model, dispatched from anywhere.
---

An action is a command to the app, declared as a shape. It renders; it never
speaks. It carries no audio and holds no floor, which is why it is never yielded
— it is `session.dispatch(...)`, callable from inside a turn, from a callback
that is not a generator, or from work that finished long after the turn that
started it. A number the caller would have to hold in their head belongs on the
screen.

```python
from voqalize.sdk import Action


class ShowResults(Action):
    query: str
    result_ids: list[str]
    highlight: str | None = None


session.dispatch(ShowResults(query="metformin", result_ids=["p1", "p2"], highlight="p1"))
```

## Your fields are the payload

Subclass `Action` and declare fields. There is nothing else to write: no
registration, no decorator, no handler table. `Action` is a pydantic model, so a
field may be a scalar, an enum, a `date`, a nested model, or a list of nested
models, and all of it dumps as JSON.

An action with no fields at all is legal and common — `class
ClearFilters(Action): pass` sends an empty payload, which is the whole message
(`demos/shopping/backend/brain.py`).

No field name is reserved. `command`, `payload`, `type` and `name` are ordinary
fields, because the payload is *nested* under `payload` rather than spread onto
the envelope — there is nothing for a field to collide with, so there is no
reserved-name list to remember
(`sdk/python/tests/unit/test_actions.py::test_no_field_can_shadow_the_envelope`).

## The wire name comes from the class name

`OpenItinerary` becomes `open_itinerary`. An all-caps run is one word, so
`OpenURL` becomes `open_url`.

**The class name is therefore part of your app contract.** Rename the class and
you rename the action: the browser's handler for the old name simply stops being
called. Nothing raises on either side — a command a page does not recognize is a
no-op there, which is exactly what you want at runtime and exactly what hides a
rename. Our own demos make that explicit; the reducer behind `orderdesk` ignores
an unknown command by design (`demos/orderdesk/frontend/src/OrderDeskCall.tsx`).

Pin the name when you would rather the class be free to move:

```python
class OpenItinerary(Action, name="open_itinerary"):
    ...
```

`name=` is a class keyword, not a reserved field. A field called `name` is fine,
and the travel demo's `open_itinerary` really does carry one.

## Every declared field is emitted, including `None`

```python
import datetime as dt
from enum import StrEnum

from voqalize.sdk import Action


class Board(StrEnum):
    BREAKFAST = "breakfast"


class ShowStay(Action):
    when: dt.date
    board: Board
    note: str | None = None


ShowStay(when=dt.date(2026, 8, 12), board=Board.BREAKFAST).to_payload()
# {"when": "2026-08-12", "board": "breakfast", "note": None}
```

There is no `exclude_none`. The wire shape of an action is a function of the
**class**, not of which fields happened to be set on one instance. That is what
lets the app declare one total interface and handle one shape: a field that
vanishes when it is `None` is a field the page cannot distinguish from a field
you never sent, and the two mean different things — "no highlight" and "this
build of the brain does not know about highlights".

`None` crosses as JSON `null`.

## Why pydantic rather than a dataclass

Four properties the wire needs, all of which a dataclass would hand-roll
(`sdk/python/src/voqalize/sdk/actions.py`).

**Validation at the call site.** `model_config = ConfigDict(populate_by_name=True,
extra="forbid")`. A typo raises `ValidationError` on the line you wrote it on,
rather than becoming a field that silently never reaches the screen:

```python
OpenItinerary(name="x", nmae="y")   # ValidationError: Extra inputs are not permitted
```

**Aliases, at every depth.** A wire key that is not a Python identifier stays
expressible, in nested models and inside lists as well as at the top:

```python
from pydantic import BaseModel, Field

from voqalize.sdk import Action


class Leg(BaseModel):
    label: str = ""
    from_: str = Field(default="", alias="from")
    to: str = ""


class SearchFlights(Action):
    leg_id: str
    legs: list[Leg] = []


SearchFlights(leg_id="blr-out", legs=[Leg(label="BLR-SGN", **{"from": "BLR"}, to="SGN")]).to_payload()
# {"leg_id": "blr-out", "legs": [{"label": "BLR-SGN", "from": "BLR", "to": "SGN"}]}
```

`from_` is the Python spelling and `from` is the browser's, and the handler is
written against the second and never sees the first. `populate_by_name=True`
means either spelling constructs.

**JSON-mode dumping.** `to_payload()` is `model_dump(by_alias=True,
mode="json")`, so a `datetime`, `Enum`, `Decimal` or `UUID` becomes a JSON scalar
*here* — where a bad field is a clear Python error naming the field, rather than
at the transport where it is an opaque serialization crash mid-call.

**JSON Schema export.** `ShowResults.model_json_schema()` gives you the shape as
JSON Schema, and `extra="forbid"` carries into it as `"additionalProperties":
false`. That is what makes the browser half generatable rather than hand-copied.
We do not ship a generator today: our own demos keep the TypeScript types by
hand and say so in the source, next to the classes they shadow
(`demos/sugar/backend/brain.py`, `demos/sugar/frontend/src/types.ts`). Change a
field on one side and change it on the other in the same commit until that
changes.

## One class can be the tool argument and the payload

Because an action is a pydantic model, it is also a legal parameter model for a
tool: the fields the model fills are the fields the page renders, declared once.

```python
async def highlight_feature(self, action: Highlight) -> str:
    """Highlight and scroll to one spec section on the currently open product
    page, so the shopper's eye follows what you are describing."""
    self.session.dispatch(action)
    return str(self.catalog.detail(action.product_id, action.feature))
```

Four of the shopping demo's eleven tools are written this way
(`demos/shopping/backend/brain.py`); the catalog lookup on the last line is your
code, and what it returns is what the model reads to keep talking. The tool
declaration contract — one `async def`, exactly one model parameter, the
docstring as the description — is [tools](/build/brain/tools/).

A `@computed_field` is the seam between the two jobs: it is absent from the
schema the model is given and present in the payload the browser renders, so a
total that must equal the sum of the rows shown under it is summed in Python and
never asked of the model (`demos/sugar/backend/brain.py`).

## On the wire it is an RTVI `ui-command`

`session.dispatch` is sugar over `session.send_rtvi`. It sends one `ui-command`,
naming the action and nesting its fields under `payload`:

```json
{"command": "show_results", "payload": {"query": "metformin", "result_ids": ["p1", "p2"], "highlight": "p1"}}
```

That is pipecat's own message, so the browser half of an action is stock and
nothing here has to be taught to a client library:

```tsx
useUICommandHandler<ShowResultsPayload>("show_results", (payload) => {
  store.showResults(payload);
});
```

Or subscribe to the event once and route in a reducer, which is what a page with
more than a handful of actions ends up doing — `RTVIEvent.UICommand` carries
`{ command, payload }`. The envelope, the rest of the whitelist and what does not
cross are [the RTVI plane](/reference/rtvi/).

## Ordering, and the one time an action does not arrive

`dispatch` never blocks and nothing comes back.

Inside a turn it reaches the wire in the order it runs, so it cannot jump ahead
of speech you already yielded — the outbound bulk lane is one queue, drained in
order, and only session control rides the lane that overtakes it. An action that
belongs with a sentence goes next to that sentence in the generator body.

A barge-in cancels the turn's task. A `dispatch` your code had not reached yet
therefore never happens; one already emitted stands, and the page keeps what it
already drew. Floor-free work — an `on_rtvi` handler, a callback from something
that finished late — is not cancelled by a barge-in at all.

**Under congestion an action can be dropped, and the call site is silent.** The
outbound bulk lane holds 256 frames by default; when it is full, the two
unbounded flows are shed — speech chunks and RTVI messages, actions included
(`sdk/python/src/voqalize/sdk/engine.py`,
`sdk/python/src/voqalize/sdk/wire/frames.py`). `dispatch` returns `None` either
way, nothing raises, and the only symptom is a screen that is one render behind
the conversation while the transcript reads perfectly.

The signal is `on_error`: one non-fatal `ErrorCode.OVERLOAD`, edge-triggered —
one per congestion episode per direction, not one per dropped frame. The session
is never killed by it.

```python
async def on_error(self, session, error):
    if error.code is ErrorCode.OVERLOAD:
        logger.warning("session {}: {}", session.id, error.message)
```

Implement it if the screen carries state the caller acts on. See
[error codes](/reference/errors/).

## The page answers back

Nothing is returned and nothing is awaited, so an action that asks a question
gets its answer the way every other tap arrives: as an ordinary `client-message`
at `on_rtvi`, correlated by whatever your app put in it. The dispatch that asked
is long over by then.

That direction is [context and history](/build/brain/context/).

## Read next

- [Voice points, the screen holds](/design/speech-vs-screen/) — what goes where.
- [The RTVI plane](/reference/rtvi/) — the message whitelist, both directions.
