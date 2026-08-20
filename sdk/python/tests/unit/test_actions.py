"""Typed actions: declaration, naming, and serialization.

:class:`~voqalize.sdk.Action` is a *declaration* of a ui_command's args half. This
file pins the three things a browser contract depends on — the wire **name** derived
from the class, the wire **shape** produced by the fields, and the line between
payload and control. The over-the-wire half (that this really reaches the pygato
leg) is ``tests/e2e_cortex/test_e2e_session_action.py``.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

import pytest
from pydantic import BaseModel, Field, ValidationError

from voqalize.sdk import Action, Result


class OpenItinerary(Action):
    name: str


class SetTripStructure(Action):
    families: list[str] = []


class OpenURL(Action):
    href: str


class Explicit(Action, name="totally_different"):
    x: int = 0


def test_wire_name_is_derived_from_the_class_name() -> None:
    assert OpenItinerary.__voqal_action__ == "open_itinerary"
    assert SetTripStructure.__voqal_action__ == "set_trip_structure"
    # An all-caps run is one word, not one word per letter.
    assert OpenURL.__voqal_action__ == "open_url"


def test_explicit_name_wins_over_the_derived_one() -> None:
    assert Explicit.__voqal_action__ == "totally_different"


def test_payload_is_the_declared_fields() -> None:
    assert OpenItinerary(name="Poddar Vietnam").to_payload() == {"name": "Poddar Vietnam"}


# ─── payload vs control ───────────────────────────────────────────────────────


def test_control_fields_never_reach_the_payload() -> None:
    """``on_result`` and ``timeout_s`` steer the SDK; they are not the browser's
    business, and a callable could not be serialized anyway."""
    action = OpenItinerary(name="x", on_result=lambda _r: None, timeout_s=5.0)
    assert action.to_payload() == {"name": "x"}
    assert action.timeout_s == 5.0


def test_redeclaring_a_control_field_is_rejected_at_declaration() -> None:
    """Redeclaring one silently drops the base class's ``exclude=True`` and puts it
    straight onto the wire — so the class never gets built."""
    with pytest.raises(TypeError, match="are control, not payload"):

        class Bad(Action):
            timeout_s: float | None = 3.0


def test_a_result_carries_the_action_it_answers() -> None:
    assert Result(action_id=7, status="timeout").data is None


# ─── aliases ───────────────────────────────────────────────────────────────────


class Leg(BaseModel):
    """A nested model, aliased the way the travel demo's really is."""

    label: str = ""
    from_: str = Field(default="", alias="from")
    to: str = ""


class SearchFlights(Action):
    leg_id: str
    legs: list[Leg] = []
    from_: str = Field(default="", alias="from")


def test_aliases_are_emitted_by_alias_at_every_depth() -> None:
    """``from_`` is the Python spelling; ``from`` is the browser's. The nested model
    inside a list is dumped by alias too — this is what makes an Action *compose*."""
    action = SearchFlights(
        leg_id="blr-out",
        legs=[Leg(label="BLR → SGN", **{"from": "BLR"}, to="SGN")],
        **{"from": "top"},
    )
    assert action.to_payload() == {
        "leg_id": "blr-out",
        "legs": [{"label": "BLR → SGN", "from": "BLR", "to": "SGN"}],
        "from": "top",
    }


def test_either_spelling_constructs() -> None:
    """``populate_by_name`` — the field name and the alias both validate, matching how
    the SDK builds tool *arguments* (``_framework.coerce``)."""
    by_alias = SearchFlights(leg_id="l", **{"from": "BLR"})
    by_name = SearchFlights(leg_id="l", from_="BLR")
    assert (
        by_alias.to_payload()
        == by_name.to_payload()
        == {
            "leg_id": "l",
            "legs": [],
            "from": "BLR",
        }
    )


# ─── serialization rules ───────────────────────────────────────────────────────


class Board(StrEnum):
    BREAKFAST = "breakfast"


class Rich(Action):
    when: dt.date
    board: Board
    note: str | None = None


def test_json_mode_scalars() -> None:
    """A ``date`` / ``StrEnum`` becomes a JSON scalar *here*, where a bad field is a
    clear Python error — not at the transport, as an opaque serialization crash."""
    assert Rich(when=dt.date(2026, 8, 12), board=Board.BREAKFAST).to_payload() == {
        "when": "2026-08-12",
        "board": "breakfast",
        "note": None,
    }


def test_none_fields_are_emitted_not_dropped() -> None:
    """No ``exclude_none``: the wire shape is a function of the CLASS, not of which
    fields happened to be set. That stability is what lets the browser declare one
    total TypeScript interface."""
    payload = Rich(when=dt.date(2026, 8, 12), board=Board.BREAKFAST).to_payload()
    assert "note" in payload and payload["note"] is None


def test_unknown_kwargs_are_rejected() -> None:
    """A typo is a loud error at the call site, not a field that silently never
    reaches the screen — the entire reason to declare the shape."""
    with pytest.raises(ValidationError):
        OpenItinerary(name="x", nmae="y")  # type: ignore[call-arg]


# ─── the envelope guard ────────────────────────────────────────────────────────


@pytest.mark.parametrize("reserved", ["type", "action", "action_id"])
def test_a_field_colliding_with_the_envelope_is_rejected_at_declaration(reserved: str) -> None:
    """Args are spread onto the envelope's top level, so a field named ``action``
    would overwrite the action name. Caught when the class is defined, not on the
    wire."""
    with pytest.raises(TypeError, match="collide with the ui_command envelope"):
        type(Action)("Bad", (Action,), {"__annotations__": {reserved: str}})


def test_the_guard_looks_at_the_alias_not_the_field_name() -> None:
    with pytest.raises(TypeError, match="collide with the ui_command envelope"):

        class AlsoBad(Action):
            kind: str = Field(default="", alias="type")


def test_a_field_named_name_is_fine() -> None:
    """``name`` is the class *keyword*, not a reserved field — the travel demo's
    ``open_itinerary`` really does carry one."""
    assert OpenItinerary(name="x").to_payload() == {"name": "x"}
