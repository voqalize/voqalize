---
title: Actions
description: The brain's second output. A typed message that renders on the page and is never spoken, declared as a pydantic model and dispatched from anywhere.
---

An **action** is a typed command to your app: it renders, and it never speaks.
It holds no place on the audio timeline, so it is not yielded; you call
`session.dispatch(...)` from inside a turn, from any other callback, or from work
that finished after the turn ended. A number the user would have to hold in their
head belongs on the screen.

```python
from voqalize.sdk import Action


class ShowResults(Action):
    query: str
    result_ids: list[str]
    highlight: str | None = None


session.dispatch(ShowResults(query="metformin", result_ids=["p1", "p2"], highlight="p1"))
```

## Declare the fields; they are the payload

Subclass `Action` and declare fields. There is no registration, decorator or
handler table. `Action` is a pydantic model, so a field may be a scalar, an enum,
a `date`, a nested model or a list of them.

- **An action with no fields is fine.** `class ClearFilters(Action): pass` sends
  an empty payload.
- **No field name is reserved.** `command`, `payload`, `type` and `name` are
  ordinary fields, because your fields are nested under `payload`.
- **A typo raises at the call site.** Unknown fields are refused:

```python
class OpenItinerary(Action):
    name: str


OpenItinerary(nmae="Goa")   # ValidationError: Extra inputs are not permitted
```

- **A wire key that is not a Python identifier** uses a pydantic alias, at any
  depth. Either spelling constructs; the payload uses the alias:

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

`to_payload()` dumps in JSON mode, so a `datetime`, `Enum`, `Decimal` or `UUID`
becomes a JSON value in your process, where a bad field is a clear Python error.

## The class name is the wire name

`OpenItinerary` becomes `open_itinerary`. An all-caps run is one word, so
`OpenURL` becomes `open_url`.

**Renaming the class renames the action.** Nothing raises on either side: a page
ignores a command it does not recognize, so the old handler simply stops being
called. Pin the name when you want the class free to move:

```python
class OpenItinerary(Action, name="open_itinerary"):
    ...
```

`name=` is a class keyword, so a field called `name` is still fine.

## Every declared field is sent, including `None`

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

The payload's shape depends on the class, not on which fields one instance set,
so the page handles one shape. `None` crosses as JSON `null`, which keeps "no
highlight" distinct from "this brain does not know about highlights".

## Use one class as the tool argument and the payload

An action is a pydantic model, so it is also a valid parameter model for a
[tool](/build/brain/tools/): the fields the model fills are the fields the page
renders, declared once. This sample is illustrative:

```python
async def highlight_feature(self, action: Highlight) -> str:
    """Highlight and scroll to one spec section on the open product page,
    so the shopper's eye follows what you are describing."""
    self.session.dispatch(action)
    return "highlighted"
```

It goes unmarked because it only moves the screen. If its result carried data the
model must read to answer this turn, it would take `@needs_result_now`
([Tools](/build/brain/tools/#mark-the-reads-the-model-needs-now)). The `shopping`
demo declares its `highlight_feature` this way.

A pydantic `@computed_field` is absent from the schema the model is given and
present in the payload the page renders, so a total that must equal the sum of
the rows is computed in Python, never asked of the model.

## On the wire it is an RTVI `ui-command`

`session.dispatch` sends one RTVI `ui-command`, naming the action and nesting its
fields under `payload`:

```json
{"command": "show_results", "payload": {"query": "metformin", "result_ids": ["p1", "p2"], "highlight": "p1"}}
```

That is pipecat's own message, so the browser handles it with pipecat's own hook:

```tsx
useUICommandHandler<ShowResults>("show_results", (payload) => {
  store.showResults(payload);
});
```

A page with many actions subscribes once to `RTVIEvent.UICommand`, which carries
`{ command, payload }`, and routes in a reducer. Do not write `ShowResults` by
hand: `voqalize types` generates it and the union over `command`
([TypeScript types](/build/brain/typescript/)). The rest of the message set is
[RTVI messages](/reference/rtvi/).

## Ordering, and when an action does not arrive

`dispatch` never blocks and returns nothing.

- **Inside a turn it keeps its place.** It reaches the wire in the order it runs,
  so it never jumps ahead of speech you already yielded. Put an action that
  belongs with a sentence next to that sentence.
- **A barge-in cancels the turn.** A `dispatch` your code had not reached never
  happens; one already sent stands. Work outside a turn (an `on_rtvi` handler, a
  late callback) is not cancelled.
- **Under congestion an action can be dropped, silently.** The outbound queue
  holds 256 frames by default; when it is full, speech chunks and RTVI messages
  (actions included) are shed. The symptom is a screen one render behind the
  conversation.

The signal is one non-fatal `ErrorCode.OVERLOAD` at `on_error` per congestion
episode per direction. The session continues. Handle it if the screen carries
state the user acts on:

```python
from loguru import logger

from voqalize.sdk import Brain, ErrorCode


class Desk(Brain):
    async def on_error(self, session, error):
        if error.code is ErrorCode.OVERLOAD:
            logger.warning("session {}: {}", session.id, error.message)
```

See [error codes](/reference/errors/).

## The page answers back as an app event

An action gets no reply. When it asks the user something, the answer arrives
later as an ordinary `ui-event` at `on_rtvi`, correlated by whatever your app put
in it: [Context and history](/build/brain/context/).

## Read next

- [TypeScript types](/build/brain/typescript/): the browser half, generated.
- [Context and history](/build/brain/context/): the reverse channel.
- [Voice points, the screen holds](/design/#voice-points-the-screen-holds): what goes where.
