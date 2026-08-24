"""Actions — a command to the app, declared as a shape.

An action is the brain's second output channel. It renders; it never speaks. It
carries no audio, holds no floor, and is therefore never yielded — it is
``session.dispatch(...)``, from anywhere: from inside a turn, from a callback
that is not a generator at all, from work that finished long after the turn that
started it.

Subclass :class:`Action` and your fields *are* the payload::

    class ShowResults(Action):
        rows: list[Row]
        highlight: str | None = None

    session.dispatch(ShowResults(rows=rows))

Why pydantic rather than a dataclass — four properties the wire needs and a
dataclass would hand-roll: validation at the call site (``extra="forbid"`` turns
a typo into a loud error instead of a field that silently never reaches the
screen), aliases (a wire key that is not a Python identifier stays expressible),
JSON-mode dumping (``datetime`` / ``Enum`` / ``Decimal`` / ``UUID`` become JSON
scalars *here*, where the failure is a clear Python error, rather than at the
transport where it is an opaque crash), and JSON Schema export, which is what
makes the TypeScript half generatable instead of hand-copied.

## The wire name

Derived from the class name in ``snake_case`` — ``OpenItinerary`` →
``open_itinerary``. **The class name is therefore part of your app
contract**; renaming the class renames the action. Pin it when you don't want
that coupling::

    class OpenItinerary(Action, name="open_itinerary"):
        ...

## Serialization

``model_dump(by_alias=True, mode="json")``, carried as the ``payload`` of an RTVI
``ui-command``::

    {"command": "show_results", "payload": {...}}

That is pipecat's own message, which its ``useUICommandHandler`` reads directly —
so the browser half of an action is stock, and nothing here has to be taught to a
client library.

**Every declared field is emitted, including ``None``, which goes as JSON
``null``.** No ``exclude_none``: the wire shape of an action must be a function
of the *class*, not of which fields happened to be set on one instance, because a
stable shape is what lets the app declare one total interface instead of
marking every field optional.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

__all__ = ["Action"]

_CAMEL_BOUNDARY = re.compile(r"(.)([A-Z][a-z]+)")
_LOWER_UPPER = re.compile(r"([a-z0-9])([A-Z])")


def _snake_case(name: str) -> str:
    """``OpenItinerary`` → ``open_itinerary``; ``OpenURL`` → ``open_url``."""
    return _LOWER_UPPER.sub(r"\1_\2", _CAMEL_BOUNDARY.sub(r"\1_\2", name)).lower()


class Action(BaseModel):
    """Base class for a typed UI command. See the module docstring for the rules."""

    #: The ``command`` string this class serializes to. Set from the class name, or
    #: from an explicit ``name=`` class keyword. A dunder because pydantic
    #: reserves no ordinary identifier — a field called ``command`` has to stay
    #: usable as payload, not silently shadow this.
    __voqal_action__: ClassVar[str] = "action"

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    def __init_subclass__(cls, name: str | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.__voqal_action__ = name if name is not None else _snake_case(cls.__name__)

    def to_payload(self) -> dict[str, Any]:
        """This action's fields as the app receives them."""
        return self.model_dump(by_alias=True, mode="json")
