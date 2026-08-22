"""Tool arguments arrive as the pydantic models the tool annotated.

ADK derives a tool's JSON schema from its type hints but does **not** construct the
declared models for a list-valued parameter — the tool is handed the model's raw dicts,
so every tool body re-does the same defensive ``dict(raw) if isinstance(raw, dict) else
raw.model_dump()`` dance and the annotation is a lie. The SDK coerces at the plugin's
``before_tool_callback`` seam instead, so:

* ``Model`` and ``list[Model]`` parameters are real model instances in the body;
* non-model annotations (``str``, ``int``, a bare ``dict``) are passed through untouched;
* ``Field(alias=...)`` works **both ways** — the alias (``from``) and the field name
  (``from_``, which is what ADK actually puts in the schema, since aliases don't survive
  schema generation), so a keyword-named wire field needs no rename in the tool body;
* an argument the model shaped wrong comes back to *it* as a tool error to retry, rather
  than exploding inside the tool.
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("google.adk")

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from pydantic import BaseModel, Field

from voqalize.conformance import (
    DirectConnection,
    VoiceDriver,
    checks,
    generate_keypair,
    mint_pygato_token,
)
from voqalize.google_adk import adk_brain
from voqalize.google_adk.testing import ScriptedLlm, call, reply
from voqalize.sdk import DirectAgent, brain_factory

GREETING = "Travel desk, how can I help?"
INSTRUCTION = "You are a travel desk."
SESSION_ID = "adk-tool-args-test"

RECEIVED: dict[str, Any] = {}


class Leg(BaseModel):
    """One flight leg. ``from`` is a Python keyword, so the field is ``from_``."""

    from_: str = Field(default="", alias="from")
    to: str = ""


class CityNights(BaseModel):
    """One hotel city and how many nights."""

    city: str
    nights: int = 0


async def set_trip(legs: list[Leg], stay: CityNights, note: str, extra: dict[str, Any]) -> dict:
    """Set the trip's legs and hotel stay.

    Args:
        legs: The flight legs, each with from/to city names.
        stay: The hotel city and its number of nights.
        note: A free-text note.
        extra: Anything else, as a plain object.
    """
    RECEIVED["legs"] = legs
    RECEIVED["stay"] = stay
    RECEIVED["note"] = note
    RECEIVED["extra"] = extra
    return {"status": "set"}


def build_agent(model: str | BaseLlm) -> LlmAgent:
    return LlmAgent(name="desk", model=model, instruction=INSTRUCTION, tools=[set_trip])


async def _host(llm: ScriptedLlm) -> tuple[DirectAgent, VoiceDriver]:
    keypair = generate_keypair()
    make = adk_brain(lambda: build_agent(llm), greeting=GREETING, streaming=True)
    agent = DirectAgent(
        factory=brain_factory(make), host="127.0.0.1", port=0, public_keys=keypair.public_pem
    )
    port = await agent.start()
    token = mint_pygato_token(
        private_key_pem=keypair.private_pem,
        session_id=SESSION_ID,
        agent_id="desk",
        tenant_id="demo",
    )
    driver = VoiceDriver(
        DirectConnection(f"ws://127.0.0.1:{port}", SESSION_ID, token=token),
        session_id=SESSION_ID,
        default_timeout=10.0,
    )
    await driver.open()
    return agent, driver


def _script(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "Set up the trip.": [
            call("set_trip", args=args),
            reply("Done — the trip is set."),
        ]
    }


async def _run(args: dict[str, Any]) -> None:
    """Drive one scripted ``set_trip`` call. Every parameter is required (ADK refuses a
    call missing a mandatory one), so the two the test isn't about get filled in here."""
    RECEIVED.clear()
    llm = ScriptedLlm(_script({"note": "", "extra": {}, **args}))
    agent, driver = await _host(llm)
    try:
        await driver.start_session()
        t = await driver.user_says("Set up the trip.")
        checks.check_completed(t)
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_list_of_models_and_scalar_model_are_constructed() -> None:
    """``list[Leg]`` and ``CityNights`` reach the tool as instances, not raw dicts."""
    await _run(
        {
            "legs": [{"from_": "BLR", "to": "SGN"}],
            "stay": {"city": "Hanoi", "nights": 3},
            "note": "family trip",
        }
    )
    legs = RECEIVED["legs"]
    assert all(isinstance(leg, Leg) for leg in legs), legs
    assert legs[0].from_ == "BLR" and legs[0].to == "SGN"
    stay = RECEIVED["stay"]
    assert isinstance(stay, CityNights)
    assert stay.city == "Hanoi" and stay.nights == 3


async def test_non_model_annotations_are_untouched() -> None:
    """A ``str`` stays a ``str`` and a bare ``dict`` stays a ``dict`` — the SDK coerces
    only what the tool declared as a pydantic model."""
    await _run(
        {
            "legs": [],
            "stay": {"city": "Hanoi"},
            "note": "family trip",
            "extra": {"anything": [1, 2]},
        }
    )
    assert RECEIVED["note"] == "family trip"
    assert RECEIVED["extra"] == {"anything": [1, 2]}
    assert isinstance(RECEIVED["extra"], dict)


async def test_alias_field_accepts_the_schema_name_adk_emits() -> None:
    """ADK's generated schema uses the *field name* (``from_``) — aliases don't survive
    schema generation — so that is what the model emits, and it must populate the
    aliased field without a hand-rolled rename."""
    await _run({"legs": [{"from_": "BLR", "to": "SGN"}], "stay": {"city": "Hanoi"}})
    assert RECEIVED["legs"][0].from_ == "BLR"


async def test_alias_field_also_accepts_the_wire_alias() -> None:
    """…and the alias itself (``from``) still validates, so a snapshot round-tripped
    from the browser feeds straight back in. The tool body dumps with
    ``by_alias=True`` to hand ``from`` back to the UI."""
    await _run({"legs": [{"from": "BLR", "to": "SGN"}], "stay": {"city": "Hanoi"}})
    leg = RECEIVED["legs"][0]
    assert leg.from_ == "BLR"
    assert leg.model_dump(by_alias=True)["from"] == "BLR"


async def test_bad_argument_shape_becomes_a_tool_error_the_model_can_retry() -> None:
    """An argument the model shaped wrong never reaches the tool: the SDK answers the
    call with an error result, so the model recovers in-conversation instead of the turn
    dying on a validation exception."""
    RECEIVED.clear()
    llm = ScriptedLlm(
        {
            "Set up the trip.": [
                # `stay` is missing its required `city`.
                call(
                    "set_trip",
                    args={"legs": [], "stay": {"nights": "many"}, "note": "", "extra": {}},
                ),
                reply("Sorry — let me try that again."),
            ]
        }
    )
    agent, driver = await _host(llm)
    try:
        await driver.start_session()
        t = await driver.user_says("Set up the trip.")
        checks.check_completed(t)
        assert RECEIVED == {}, "the tool must not run with un-coercible arguments"
        # The model saw the error as this call's result.
        follow_up = llm.captured_contents[-1]
        blob = str(follow_up)
        assert "not a valid CityNights" in blob, blob
    finally:
        await driver.aclose()
        await agent.aclose()
