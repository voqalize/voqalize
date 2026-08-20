"""Actions — a command to the browser, declared as a shape.

An action is the brain's second output channel. It renders; it never speaks. It
carries no audio, holds no floor, and can therefore be sent from anywhere: from
inside a turn (``yield ShowResults(...)``), from a callback, from work that
finished long after the turn that started it (``session.dispatch(...)``).

Subclass :class:`Action` and your fields *are* the payload::

    class ShowResults(Action):
        rows: list[Row]
        highlight: str | None = None

    yield ShowResults(rows=rows, on_result=self.on_row_picked)

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
``open_itinerary``. **The class name is therefore part of your browser
contract**; renaming the class renames the action. Pin it when you don't want
that coupling::

    class OpenItinerary(Action, name="open_itinerary"):
        ...

## Serialization

``model_dump(by_alias=True, mode="json")``, spread onto the envelope:

    {"type": "ui_command", "action": "show_results", "action_id": 7, **payload}

**Every declared field is emitted, including ``None``, which goes as JSON
``null``.** No ``exclude_none``: the wire shape of an action must be a function
of the *class*, not of which fields happened to be set on one instance, because a
stable shape is what lets the browser declare one total interface instead of
marking every field optional.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["CONTROL_ACTION_FIELDS", "RESERVED_ACTION_KEYS", "Action", "Result"]

#: Envelope keys the ``ui_command`` wire shape owns. An action's fields are
#: spread onto the top level of that envelope, so a field serializing to one of
#: these would overwrite it — rejected at class-definition time rather than
#: silently on the wire.
RESERVED_ACTION_KEYS = frozenset({"type", "action", "action_id"})

#: Base-class fields that are control, not payload. They are ``exclude=True``, so
#: a subclass that redeclares one silently puts it on the wire — also rejected at
#: class-definition time.
CONTROL_ACTION_FIELDS = ("on_result", "timeout_s")

#: How long an unanswered action stays pending before its ``on_result`` fires
#: with ``status="timeout"``. Long enough for a human to read a dialog, short
#: enough that a forgotten action does not outlive the exchange it belonged to.
DEFAULT_ACTION_TIMEOUT_S = 30.0

_CAMEL_BOUNDARY = re.compile(r"(.)([A-Z][a-z]+)")
_LOWER_UPPER = re.compile(r"([a-z0-9])([A-Z])")


def _snake_case(name: str) -> str:
    """``OpenItinerary`` → ``open_itinerary``; ``OpenURL`` → ``open_url``."""
    return _LOWER_UPPER.sub(r"\1_\2", _CAMEL_BOUNDARY.sub(r"\1_\2", name)).lower()


class Result(BaseModel):
    """The browser's answer to an action — or the fact that it never came.

    ``status="timeout"`` is not an error path you handle separately: it is the
    same callback with a different status, so "the answer came" and "it didn't"
    are one piece of code.
    """

    action_id: int
    status: Literal["ok", "error", "timeout"]
    data: Any = None
    error: str | None = None


class Action(BaseModel):
    """Base class for a typed UI command. See the module docstring for the rules."""

    #: The ``action`` string this class serializes to. Set from the class name, or
    #: from an explicit ``name=`` class keyword. A dunder because pydantic
    #: reserves no ordinary identifier — a field called ``action`` must stay
    #: something we can *reject*, not something that silently shadows this.
    __voqal_action__: ClassVar[str] = "action"

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    #: Fires when the browser answers, or when ``timeout_s`` elapses. It runs on
    #: the session, not inside the turn that sent the action — the turn may be
    #: long over — so it holds no floor and cannot speak. To change the screen,
    #: call ``session.dispatch``; to say something, store it and let the next turn
    #: pick it up.
    on_result: Callable[[Result], Awaitable[None] | None] | None = Field(default=None, exclude=True)

    #: Seconds before an unanswered action expires. ``None`` opts out, and those
    #: handlers are reclaimed at session teardown instead.
    timeout_s: float | None = Field(default=DEFAULT_ACTION_TIMEOUT_S, exclude=True)

    def __init_subclass__(cls, name: str | None = None, **kwargs: Any) -> None:
        # Runs during type creation, BEFORE pydantic collects `model_fields` — so
        # only the name is settled here; the field-shape guards wait for
        # `__pydantic_init_subclass__`, which pydantic calls once the model is built.
        super().__init_subclass__(**kwargs)
        cls.__voqal_action__ = name if name is not None else _snake_case(cls.__name__)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        clashes = sorted(
            wire
            for field_name, field in cls.model_fields.items()
            if (wire := field.alias or field_name) in RESERVED_ACTION_KEYS
        )
        if clashes:
            raise TypeError(
                f"{cls.__name__}: field(s) {clashes} collide with the ui_command "
                f"envelope ({sorted(RESERVED_ACTION_KEYS)}). An action's fields are "
                f"spread onto the top level of the envelope, so these would overwrite "
                f"it — rename the field, or give it an alias the envelope doesn't own."
            )
        leaked = sorted(f for f in CONTROL_ACTION_FIELDS if not cls.model_fields[f].exclude)
        if leaked:
            raise TypeError(
                f"{cls.__name__}: field(s) {leaked} are control, not payload. "
                f"Redeclaring one drops the base class's exclude=True and puts it "
                f"straight onto the wire — pick another name."
            )

    def to_payload(self) -> dict[str, Any]:
        """This action's args as the browser receives them (minus the envelope)."""
        return self.model_dump(by_alias=True, mode="json")
