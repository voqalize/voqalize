"""Why a tool takes one pydantic model, pinned against both adapters.

The rule in the ``tools`` docstrings is not "flat parameters are unsupported" —
a flat ``str`` or ``int`` runs on both paths. It is that a flat parameter is the
one place *neither* adapter parses the model's JSON, and the two fail
differently:

* **The automatic path** checks each flat argument with ``isinstance`` and never
  coerces (``google.genai._extra_utils.convert_argument_from_function``). A
  ``Literal`` raises ``TypeError`` outright — ``isinstance`` refuses a
  subscripted generic — and ``Enum``/``date``/``Decimal``/``UUID`` raise
  ``UnknownFunctionCallArgumentError`` because the JSON string is not yet an
  instance of them. ``get_function_response_parts_async`` catches both into
  ``{'error': …}``, which the model narrates to the caller as success.
* **The interactions path** coerces nothing at all, so the same ``date`` reaches
  the tool as the ``str`` it arrived as: wrong quietly rather than loudly.

A single model parameter is the only annotation either path validates —
``annotation(**value)`` there, ``model_validate`` here — which is why a
``Literal`` written *inside* a model is safe on both.

The last test here is the other half of the same rule: the one model has to be
*complete* by the time the declaration is built, which under postponed
annotations it is not — so :func:`~voqalize.sdk.gemini._ready` rebuilds it.

These tests read upstream behaviour, not ours. When they fail because
google-genai started coercing, the rule they justify goes with them.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

import pytest
from google.genai import _extra_utils, types
from google.genai import errors as genai_errors
from pydantic import BaseModel, Field

from voqalize.sdk.gemini import _ready
from voqalize.sdk.gemini_interactions import _coerce


class Section(StrEnum):
    glucose = "glucose"
    meals = "meals"


class Payload(BaseModel):
    section: Literal["glucose", "meals"]
    when: date
    which: Section
    amount: Decimal
    ref: UUID


def _flat(annotation: object):
    """A one-parameter callable annotated ``annotation``, named like a tool."""

    def show(value):  # pyright: ignore[reportMissingParameterType]
        return value

    show.__annotations__ = {"value": annotation}
    return show


PASSES = [
    ("str", str, "glucose"),
    ("int", int, 3),
    ("float", float, 1.5),
    ("bool", bool, True),
    ("list", list[str], ["a"]),
    ("dict", dict[str, int], {"a": 1}),
    ("optional", str | None, "x"),
]

NEEDS_PARSING = [
    ("enum", Section, "glucose"),
    ("date", date, "2026-08-26"),
    ("decimal", Decimal, "1.50"),
    ("uuid", UUID, "0" * 32),
]


@pytest.mark.parametrize(("label", "annotation", "value"), PASSES, ids=[p[0] for p in PASSES])
def test_a_flat_json_native_parameter_is_fine(label, annotation, value):
    """Flatness is not the problem. Everything JSON already produces an instance
    of passes ``isinstance`` and reaches the tool unchanged."""
    got = _extra_utils.convert_argument_from_function({"value": value}, _flat(annotation))
    assert got == {"value": value}


def test_a_flat_literal_raises_before_the_tool_is_called():
    """``isinstance(value, Literal[...])`` is not a legal call, so this one does
    not even reach the error path the others take."""
    with pytest.raises(TypeError, match=r"[Ss]ubscripted generics"):
        _extra_utils.convert_argument_from_function(
            {"value": "glucose"}, _flat(Literal["glucose", "meals"])
        )


@pytest.mark.parametrize(
    ("label", "annotation", "value"), NEEDS_PARSING, ids=[p[0] for p in NEEDS_PARSING]
)
def test_a_flat_parameter_that_needs_parsing_is_rejected(label, annotation, value):
    """The JSON is the right *value* and the wrong *type*, and nothing coerces it."""
    with pytest.raises(genai_errors.UnknownFunctionCallArgumentError):
        _extra_utils.convert_argument_from_function({"value": value}, _flat(annotation))


def test_one_model_parameter_parses_every_one_of_them():
    """The wrapper is not a workaround for ``Literal``; it is the only annotation
    on either path that gets validated at all."""
    got = _extra_utils.convert_argument_from_function(
        {
            "value": {
                "section": "glucose",
                "when": "2026-08-26",
                "which": "meals",
                "amount": "1.50",
                "ref": "0" * 32,
            }
        },
        _flat(Payload),
    )
    payload = got["value"]
    assert payload == Payload(
        section="glucose",
        when=date(2026, 8, 26),
        which=Section.meals,
        amount=Decimal("1.50"),
        ref=UUID("0" * 32),
    )


def test_the_interactions_path_parses_the_model_and_nothing_else():
    """Its failure mode is the opposite one: the flat ``date`` runs, and the tool
    is handed the ``str`` it arrived as."""

    async def show(payload: Payload, when: date) -> None: ...

    got = _coerce(
        show,
        {
            "payload": {
                "section": "glucose",
                "when": "2026-08-26",
                "which": "meals",
                "amount": "1.50",
                "ref": "0" * 32,
            },
            "when": "2026-08-26",
        },
    )
    assert isinstance(got["payload"], Payload)
    assert got["when"] == "2026-08-26"
    assert not isinstance(got["when"], date)


# ─── The model has to be complete, not just correct ──────────────────────


class Unrebuilt(BaseModel):
    """A wrapper naming a row class defined below it — aura's ``compare`` shape."""

    rows: list[UnrebuiltRow] = Field(default_factory=list)


class UnrebuiltRow(BaseModel):
    name: str


class Rebuilt(BaseModel):
    rows: list[RebuiltRow] = Field(default_factory=list)


class RebuiltRow(BaseModel):
    name: str


def _declare(fn: object) -> types.FunctionDeclaration:
    return types.FunctionDeclaration.from_callable_with_api_option(
        callable=fn,  # pyright: ignore[reportArgumentType]
        api_option="GEMINI_API",
    )


def test_a_model_whose_own_fields_are_still_forward_refs_does_not_declare():
    """The failure ``_ready`` exists to prevent, one level in.

    ``from __future__ import annotations`` leaves a model's *fields* as strings
    too, and pydantic resolves them on first validation — which is long after the
    declaration is built. google-genai reads the fields directly, so the tool
    never reaches the turn, and the ``ValueError`` names the parameter rather than
    the field that is actually unresolved."""
    assert Unrebuilt.__pydantic_complete__ is False

    async def compare(request: Unrebuilt) -> str:
        """Compare rows.

        Args:
            request: The rows.
        """
        return ""

    compare.__annotations__ = {"request": Unrebuilt, "return": str}
    with pytest.raises(ValueError, match="Failed to parse the parameter request"):
        _declare(compare)


def test_ready_rebuilds_the_model_parameter_so_the_tool_declares():
    """Same shape, handed over the way a brain hands it over."""

    async def compare(request: Rebuilt) -> str:
        """Compare rows.

        Args:
            request: The rows.
        """
        return ""

    declaration = _declare(_ready(compare))
    assert Rebuilt.__pydantic_complete__
    parameters = declaration.parameters
    assert parameters is not None
    request = (parameters.properties or {})["request"]
    assert (request.properties or {}).keys() == {"rows"}
