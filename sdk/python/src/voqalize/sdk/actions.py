"""Typed actions — a UI command declared as a shape instead of assembled as a dict.

A screen-driving brain fires ``ui_command``s at the browser
(:meth:`~voqalize.sdk.brain.Session.action`). The wire shape is fixed —
``{"type": "ui_command", "action": <name>, "action_id": <int>, **args}`` — but the
*args* half has always been an untyped ``dict``, which means the contract between
your brain and your UI lives in two hand-written places that drift: a dict literal
in Python and a ``switch`` with ``String(cmd.foo)`` coercions in TypeScript.

An :class:`Action` makes the Python half declared:

    from voqalize.sdk import Action

    class OpenItinerary(Action):
        name: str

    class SearchFlights(Action):
        leg_id: str
        options: list[FlightOption]

    interaction.action(OpenItinerary(name="Poddar Vietnam"))

The **wire is unchanged** — that call is byte-identical to the legacy
``interaction.action("open_itinerary", {"name": "Poddar Vietnam"})``. What you gain
is that the payload is now a type your editor, your linter and your tests all know,
and that composes: an Action field may be another model (or a list of them), and
nested aliases are respected all the way down.

The legacy ``(name, args)`` form keeps working, unchanged and unhinted — it stays
the general surface for non-pydantic brains and for other languages.

## The wire name

Derived from the class name in ``snake_case`` — ``OpenItinerary`` →
``open_itinerary``, ``SetTripStructure`` → ``set_trip_structure`` — which is the
convention the demos and docs already use. **The class name is therefore part of
your browser contract**; renaming the class renames the action. When you don't want
that coupling (or the wire name isn't a valid identifier), pin it explicitly:

    class OpenItinerary(Action, name="open_itinerary"):
        ...

## Serialization rules (the part the browser depends on)

``model_dump(by_alias=True, mode="json")``:

- **By alias.** A field declared ``from_: str = Field(alias="from")`` goes out as
  ``from`` — the spelling the UI reads. Construction accepts *either* spelling
  (``populate_by_name``), matching how the SDK builds tool arguments.
- **JSON mode.** ``datetime``/``Enum``/``Decimal``/``UUID`` become JSON scalars here,
  where the failure is a clear Python error, rather than at the transport where it
  would be an opaque serialization crash.
- **Every declared field is emitted — including ``None``, which goes as JSON
  ``null``.** No ``exclude_none``. This is deliberate: the wire shape of an Action
  must be a function of the *class*, not of which fields happened to be unset on one
  instance. A stable shape is what lets the browser side declare one total
  TypeScript interface instead of marking every field optional. If a key should be
  absent rather than null, model it as a field the UI treats as empty (``""``,
  ``[]``), or fall back to the legacy dict form for that one call.
- **Unknown keyword arguments are rejected** (``extra="forbid"``), so a typo is a
  loud ``ValidationError`` at the call site instead of a field that silently never
  reaches the screen.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

__all__ = ["RESERVED_ACTION_KEYS", "Action"]

#: Envelope keys the ``ui_command`` wire shape owns. An Action's fields are spread
#: onto the top level of that envelope, so a field serializing to one of these would
#: overwrite it — rejected at class-definition time rather than silently on the wire.
RESERVED_ACTION_KEYS = frozenset({"type", "action", "action_id"})

_CAMEL_BOUNDARY = re.compile(r"(.)([A-Z][a-z]+)")
_LOWER_UPPER = re.compile(r"([a-z0-9])([A-Z])")


def _snake_case(name: str) -> str:
    """``OpenItinerary`` → ``open_itinerary``; ``OpenURL`` → ``open_url``."""
    return _LOWER_UPPER.sub(r"\1_\2", _CAMEL_BOUNDARY.sub(r"\1_\2", name)).lower()


class Action(BaseModel):
    """Base class for a typed UI command. See the module docstring for the rules.

    Subclass it, declare the fields the browser reads, and hand an *instance* to
    :meth:`~voqalize.sdk.brain.Session.action`,
    :meth:`~voqalize.sdk.brain.Interaction.action` or
    :meth:`voqalize.google_adk.voice().action <voqalize._framework.context.Voice.action>`.

    The wire name is on the class as :attr:`__voqal_action__` — a dunder so it can
    never collide with a field name (pydantic reserves no ordinary identifier).
    """

    #: The ``action`` string this class serializes to. Set from the class name, or
    #: from an explicit ``name=`` class keyword. Read it in tests to pin the
    #: cross-language contract: ``assert OpenItinerary.__voqal_action__ ==
    #: "open_itinerary"``.
    __voqal_action__: ClassVar[str] = "action"

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    def __init_subclass__(cls, name: str | None = None, **kwargs: Any) -> None:
        # Runs during type creation, BEFORE pydantic collects `model_fields` — so
        # only the name is settled here; the field-shape guard waits for
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
                f"envelope ({sorted(RESERVED_ACTION_KEYS)}). An Action's fields are "
                f"spread onto the top level of the envelope, so these would overwrite "
                f"it — rename the field, or give it an alias the envelope doesn't own."
            )

    def to_payload(self) -> dict[str, Any]:
        """This action's args as the browser receives them (minus the envelope).

        ``model_dump(by_alias=True, mode="json")`` — see the module docstring for
        why those two flags and no ``exclude_none``.
        """
        return self.model_dump(by_alias=True, mode="json")


def action_envelope(
    name_or_action: str | Action, args: dict[str, Any] | None
) -> tuple[str, dict[str, Any]]:
    """Normalize either ``action(...)`` calling form to ``(wire_name, args)``.

    The single place the typed and legacy forms converge, so both emit the exact
    same envelope. Internal — the public surface is the ``action`` methods.
    """
    if isinstance(name_or_action, Action):
        if args is not None:
            raise TypeError(
                f"action({type(name_or_action).__name__}(...)) takes no separate args "
                f"dict — the action instance IS the args. Pass either a typed Action "
                f"or the legacy (name, args) pair, not both."
            )
        return name_or_action.__voqal_action__, name_or_action.to_payload()
    return name_or_action, dict(args or {})
