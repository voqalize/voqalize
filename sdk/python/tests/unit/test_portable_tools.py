"""Tools declared from their signatures, for the JSON-schema layers."""

from __future__ import annotations

from typing import Literal

import pytest
from pydantic import BaseModel, ValidationError

from voqalize.sdk._portable import declare  # pyright: ignore[reportPrivateUsage]


class _Where(BaseModel):
    """Where to go."""

    city: str
    nights: int = 1


class _Trip(BaseModel):
    """A trip."""

    where: _Where
    kind: Literal["work", "leisure"]


async def test_one_model_is_declared_flat_with_its_refs_written_out() -> None:
    seen: list[_Trip] = []

    async def book(trip: _Trip) -> str:
        """Book a trip."""
        seen.append(trip)
        return "booked"

    tool = declare(book)
    assert (tool.name, tool.description) == ("book", "Book a trip.")
    assert set(tool.parameters["properties"]) == {"where", "kind"}
    assert "$defs" not in tool.parameters
    assert tool.parameters["properties"]["where"]["properties"]["city"]["type"] == "string"

    assert await tool.call({"where": {"city": "Pune"}, "kind": "work"}) == "booked"
    assert seen[0].where.nights == 1


async def test_plain_parameters_are_validated_before_the_call() -> None:
    async def nudge(level: int, tone: Literal["soft", "firm"] = "soft") -> str:
        """Nudge."""
        return f"{level}:{tone}"

    tool = declare(nudge)
    assert tool.parameters["required"] == ["level"]
    assert await tool.call({"level": "2"}) == "2:soft"
    with pytest.raises(ValidationError):
        await tool.call({"level": 1, "tone": "loud"})


async def test_no_parameters_is_an_empty_object() -> None:
    async def ping() -> str:
        """Ping."""
        return "pong"

    tool = declare(ping)
    assert tool.parameters == {"type": "object", "properties": {}, "additionalProperties": False}
    assert await tool.call({}) == "pong"


def test_a_sync_tool_is_refused() -> None:
    def ping() -> str:
        return "pong"

    with pytest.raises(TypeError, match="async def"):
        declare(ping)
