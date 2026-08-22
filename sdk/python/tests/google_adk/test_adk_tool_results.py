"""Tool *return* values are dumped for the model, the same way arguments are built.

The sibling ``test_adk_tool_args.py`` covers the inbound half: a ``list[Leg]``
parameter really is a list of ``Leg``s in the tool body. This file covers the
symmetric outbound half — a tool that *returns* a pydantic model, which is the
natural thing to write once its arguments are models.

Left to ADK, a returned model is nested live under ``{"result": <Model>}`` and only
flattened at the transport by a bare ``model_dump()``: **aliases are dropped**
(``from`` silently becomes ``from_``, asymmetric with the input path) and a
``datetime.date`` field survives all the way to an opaque ``json.dumps`` ``TypeError``
at the HTTP boundary. The SDK dumps it at the plugin's ``after_tool_callback`` seam
instead, with the same rules a typed ``Action`` serializes by
(``by_alias=True, mode="json"``), so:

* a returned **model becomes the function response object itself** — its fields are
  what the model reads, by alias, not wrapped in ``result``;
* models **nested inside** a returned dict or list are dumped in place;
* a return with no model in it — a plain dict, a string — is left on ADK's own path,
  byte-for-byte unchanged.

``ScriptedLlm.captured_contents`` is where the assertion lands: the tool result the
model was shown on its follow-up call is a ``function_response`` part in the last
captured request.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

pytest.importorskip("google.adk")

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from pydantic import BaseModel, Field

from voqalize.conformance import (
    DirectConnection,
    VoqalizeDriver,
    checks,
    generate_keypair,
    mint_voqalize_token,
)
from voqalize.google_adk import adk_brain
from voqalize.google_adk.testing import ScriptedLlm, call, reply
from voqalize.sdk import DirectAgent, brain_factory

GREETING = "Travel desk, how can I help?"
INSTRUCTION = "You are a travel desk."
SESSION_ID = "adk-tool-results-test"


class Leg(BaseModel):
    """``from`` is a Python keyword, so the field is ``from_`` and the wire key is the
    alias — the exact shape the travel demo ships."""

    from_: str = Field(default="", alias="from")
    to: str = ""
    on: dt.date | None = None


class SearchResult(BaseModel):
    """A tool's declared return type."""

    status: str = "ok"
    legs: list[Leg] = []


async def return_model() -> SearchResult:
    """Return a pydantic model directly."""
    return SearchResult(status="found", legs=[Leg(**{"from": "BLR"}, to="SGN")])


async def return_nested() -> dict[str, Any]:
    """Return a dict with models inside it."""
    return {"count": 1, "legs": [Leg(**{"from": "SGN"}, to="BLR")], "note": "hi"}


async def return_dates() -> SearchResult:
    """Return a model carrying a non-JSON scalar."""
    return SearchResult(legs=[Leg(**{"from": "BLR"}, on=dt.date(2026, 8, 12))])


async def return_plain() -> dict[str, Any]:
    """Return an ordinary dict — nothing pydantic anywhere."""
    return {"status": "plain", "n": 3}


async def return_scalar() -> str:
    """Return a bare string — ADK wraps non-dicts under ``result``."""
    return "just a string"


TOOLS = [return_model, return_nested, return_dates, return_plain, return_scalar]


def build_agent(model: str | BaseLlm) -> LlmAgent:
    return LlmAgent(name="desk", model=model, instruction=INSTRUCTION, tools=TOOLS)


async def _host(llm: ScriptedLlm) -> tuple[DirectAgent, VoqalizeDriver]:
    keypair = generate_keypair()
    make = adk_brain(lambda: build_agent(llm), greeting=GREETING, streaming=True)
    agent = DirectAgent(
        factory=brain_factory(make), host="127.0.0.1", port=0, public_keys=keypair.public_pem
    )
    port = await agent.start()
    token = mint_voqalize_token(
        private_key_pem=keypair.private_pem,
        session_id=SESSION_ID,
        agent_id="desk",
        tenant_id="demo",
    )
    driver = VoqalizeDriver(
        DirectConnection(f"ws://127.0.0.1:{port}", SESSION_ID, token=token),
        session_id=SESSION_ID,
        default_timeout=10.0,
    )
    await driver.open()
    return agent, driver


def _tool_response(llm: ScriptedLlm) -> dict[str, Any]:
    """The tool result as the model saw it on its follow-up call — the last
    ``function_response`` part in the last captured request."""
    for content in reversed(llm.captured_contents[-1]):
        for part in reversed(content.parts or []):
            fr = getattr(part, "function_response", None)
            if fr is not None:
                return dict(fr.response or {})
    raise AssertionError("no function_response in the last captured request")


async def _run(tool: str) -> dict[str, Any]:
    """Drive one scripted call of ``tool`` and return what the model was shown."""
    llm = ScriptedLlm({"Go.": [call(tool), reply("Done.")]})
    agent, driver = await _host(llm)
    try:
        await driver.start_session()
        checks.check_completed(await driver.user_says("Go."))
        return _tool_response(llm)
    finally:
        await driver.aclose()
        await agent.aclose()


async def test_a_returned_model_is_the_response_object_dumped_by_alias() -> None:
    """The load-bearing one: the tool's declared return type *is* its contract. The
    model reads named fields — with ``from_`` spelled ``from``, matching the inbound
    path — and there is no ``result`` wrapper around them."""
    assert await _run("return_model") == {
        "status": "found",
        "legs": [{"from": "BLR", "to": "SGN", "on": None}],
    }


async def test_models_nested_in_a_returned_dict_are_dumped_in_place() -> None:
    """The dict keeps its own shape; only the models inside it change."""
    assert await _run("return_nested") == {
        "count": 1,
        "legs": [{"from": "SGN", "to": "BLR", "on": None}],
        "note": "hi",
    }


async def test_non_json_scalars_become_json_scalars() -> None:
    """``mode="json"`` — a ``date`` is resolved here, not deferred to a ``json.dumps``
    failure inside the transport where the error names neither tool nor field."""
    assert await _run("return_dates") == {
        "status": "ok",
        "legs": [{"from": "BLR", "to": "", "on": "2026-08-12"}],
    }


async def test_a_plain_dict_return_is_untouched() -> None:
    """No model anywhere ⇒ the SDK declines to interfere and ADK's own handling
    stands. This is what keeps every existing tool byte-identical."""
    assert await _run("return_plain") == {"status": "plain", "n": 3}


async def test_a_scalar_return_keeps_adks_result_wrapper() -> None:
    """ADK wraps a non-dict return under ``result``; the SDK does not change that."""
    assert await _run("return_scalar") == {"result": "just a string"}
