"""A demo on OpenAI, end to end over the wire — no network, no LLM key.

New demos start on :class:`voqalize.sdk.openai.OpenAIBrain` (the existing ones stay
on ``GeminiBrain``). This is the proof that the host serves one: a small brain,
defined here rather than as a demo folder (discovery would serve a folder in
production), hosted on a real ``brain_server`` socket through :func:`demo_from`
and driven by the conformance ``VoqalizeDriver``, with only the model scripted by
:class:`~voqalize_demos.testing.ScriptedOpenAI`. Plus the host's own half: the
OpenAI router, the lazily built client, and the key read from the environment.

Run: ``cd demos && uv run pytest tests/test_openai_host.py``
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import APIRouter
from openai import AsyncOpenAI
from voqalize_demos import session as host
from voqalize_demos.testing import ScriptedOpenAI, reply, reply_and_call

from voqalize.sdk import Action, Session
from voqalize.sdk.openai import OpenAIBrain

from ._harness import check_greeting, check_turn, demo_from

_GREETING = "Hi, I'm the concierge. What can I find for you?"


class OpenRoom(Action):
    room_id: str


class Concierge(OpenAIBrain):
    """The shape a new demo's ``brain.py`` takes: the client injected, a fixed
    greeting, and one tool that drives the screen and returns at once."""

    def __init__(self, *, client: AsyncOpenAI) -> None:
        super().__init__(
            client=client,
            system_instruction="You are a hotel concierge. Say one short line and act.",
            model="gpt-6-sol",
            reasoning="low",
        )
        self.opened: list[str] = []

    async def greet(self, session: Session) -> str:
        return _GREETING

    @property
    def tools(self) -> list[Any]:
        return [self.open_room]

    async def open_room(self, action: OpenRoom) -> str:
        """Put one room's page on the guest's screen."""
        self.opened.append(action.room_id)
        self.session.dispatch(action)
        return f"room {action.room_id} is on screen"


def _llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            "Show me the sea view room.": reply_and_call(
                # Flat: OpenAIBrain declares a model parameter's fields directly,
                # so the call carries room_id, not action={"room_id": ...}.
                "Here's the sea view room.",
                "open_room",
                room_id="sea-view",
            ),
            "How big is it?": reply("Forty square metres, with a balcony."),
        }
    )


def _build(llm: ScriptedOpenAI) -> Concierge:
    # The fake stands in for the client structurally, as ScriptedGemini does.
    return Concierge(client=llm)  # type: ignore[arg-type]


async def test_an_openai_brain_speaks_runs_its_tool_and_dispatches() -> None:
    llm = _llm()
    async with demo_from("concierge", lambda: _build(llm)) as rig:
        greeting = await rig.driver.start_session()
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == _GREETING

        t1 = await rig.driver.user_says("Show me the sea view room.")
        check_turn(rig, t1, units=1)
        assert "sea view room" in t1.text
        assert isinstance(rig.brain, Concierge)
        assert rig.brain.opened == ["sea-view"]
        assert rig.actions() == ["open_room"]
        assert rig.command("open_room") == {"room_id": "sea-view"}
        # One request: the tool is unmarked, so its result waits for the next one.
        assert len(llm.requests) == 1

        t2 = await rig.driver.user_says("How big is it?")
        check_turn(rig, t2, units=1)
        assert "Forty square metres" in t2.text

    first, second = llm.requests
    assert first["stream"] is True and first["store"] is False
    assert first["model"] == "gpt-6-sol"
    assert first["reasoning"] == {"effort": "low"}
    assert [t["name"] for t in first["tools"]] == ["open_room"]
    assert llm.captured_instructions[0].startswith("You are a hotel concierge.")
    # The tool's result rides in the next request, after the call that made it.
    outputs = [i for i in second["input"] if i.get("type") == "function_call_output"]
    assert [json.loads(o["output"]) for o in outputs] == [{"result": "room sea-view is on screen"}]
    assert {"role": "user", "content": "How big is it?"} in llm.captured_inputs[1]


async def test_a_scripted_call_to_an_undeclared_tool_fails_the_test() -> None:
    llm = ScriptedOpenAI({"hello": reply_and_call("Hi.", "not_a_tool")})
    with pytest.raises(AssertionError, match="does not declare"):
        stream = await llm.responses.create(
            model="m", input=[{"role": "user", "content": "hello"}], stream=True, tools=[]
        )
        _ = [e async for e in stream]


async def test_tool_choice_none_drops_the_scripted_calls() -> None:
    llm = ScriptedOpenAI({"hello": reply_and_call("Hi.", "open_room", room_id="a")})
    tools = [{"type": "function", "name": "open_room", "parameters": {}}]
    stream = await llm.responses.create(
        model="m",
        input=[{"role": "user", "content": "hello"}],
        stream=True,
        tools=tools,
        tool_choice="none",
    )
    events = [e.type async for e in stream]
    assert events == ["response.output_text.delta", "response.completed"]


# ─── The host ─────────────────────────────────────────────────────────────────


def test_settings_read_the_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-test-not-real")
    settings = host.Settings.from_env()
    assert settings.openai_api_key == "sk-test-not-real"
    assert settings.gemini_api_key == "gm-test-not-real"


def test_settings_default_the_openai_key_to_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert host.Settings.from_env().openai_api_key == ""


def test_the_openai_router_builds_and_no_client_exists_until_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The app graph is built with no key (tests, CI, a fresh container), so the
    router must build and the runtime must hold no client until a session reads
    it, and then exactly one, shared."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    built: list[AsyncOpenAI] = []

    def build(client: AsyncOpenAI) -> Concierge:
        built.append(client)
        return Concierge(client=client)

    router = host.make_openai_brain_router("concierge", build)
    assert isinstance(router, APIRouter)
    assert [getattr(r, "path", None) for r in router.routes] == ["/concierge"]
    assert built == [], "the factory ran before any session was dialed"

    runtime = host._Runtime(
        settings=host.Settings(
            gemini_api_key="",
            openai_api_key="sk-test-not-real",
            brain_pubkeys=(),
            allow_unverified=False,
        )
    )
    assert "openai" not in vars(runtime)
    assert "client" not in vars(runtime)
    client = runtime.openai
    assert isinstance(client, AsyncOpenAI)
    assert client.api_key == "sk-test-not-real"
    assert runtime.openai is client
    assert "client" not in vars(runtime), "reading the OpenAI client built the Gemini one"
