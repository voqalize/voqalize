"""``LiteLLMBrain``: the voice core on any model LiteLLM reaches.

Pins LiteLLM's half: chat messages out, streamed deltas back, a tool call
assembled from its pieces, the forced-tool shape the Responses bridge needs, and
the counts.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Literal

import pytest
from pydantic import BaseModel

from voqalize.sdk import Finalize, SpeechChunk, UserMessage
from voqalize.sdk import litellm as layer
from voqalize.sdk.litellm import LiteLLMBrain
from voqalize.sdk.voice import ToolChoice

# ─── The API, scripted ────────────────────────────────────────────────────────


def _chunk(content: str | None = None, calls: list[Any] | None = None, usage: Any = None) -> Any:
    delta = SimpleNamespace(content=content, tool_calls=calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=usage)


def _piece(index: int, *, id: str | None = None, name: str | None = None, args: str = "") -> Any:
    return SimpleNamespace(index=index, id=id, function=SimpleNamespace(name=name, arguments=args))


def _usage(prompt: int = 100, completion: int = 30, cached: int = 0, reasoning: int = 10) -> Any:
    return SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        prompt_tokens_details=SimpleNamespace(cached_tokens=cached),
        completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
    )


def _end(usage: Any = None) -> Any:
    return SimpleNamespace(choices=[], usage=usage or _usage())


class _Fake:
    def __init__(self, script: list[list[Any]]) -> None:
        self.script = list(script)
        self.requests: list[dict[str, Any]] = []

    async def acompletion(self, **kwargs: Any) -> Any:
        import copy

        self.requests.append(copy.deepcopy(kwargs))
        chunks = self.script.pop(0)

        async def stream() -> Any:
            for c in chunks:
                yield c

        return stream()


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(script: list[list[Any]]) -> _Fake:
        f = _Fake(script)
        monkeypatch.setattr(layer.litellm, "acompletion", f.acompletion)
        return f

    return install


class _Section(BaseModel):
    """Which section to open."""

    section: Literal["pricing", "security"]


class _Guide(LiteLLMBrain):
    def __init__(self, model: str = "anthropic/claude-x", **kwargs: Any) -> None:
        super().__init__(system_instruction="be brief", model=model, **kwargs)
        self.ran: list[str] = []

    @property
    def tools(self) -> list[Any]:
        return [self.open_section, self.ping]

    async def open_section(self, args: _Section) -> str:
        """Open a section."""
        self.ran.append(args.section)
        return "ok"

    async def ping(self) -> str:
        """Ping."""
        return "pong"


class _Session:
    can_report_steps = False


async def _drain(brain: _Guide, text: str = "hello") -> list[str]:
    session: Any = _Session()
    return [
        e.text
        async for e in brain.on_user_message(session, UserMessage(text))
        if isinstance(e, SpeechChunk)
    ]


async def test_a_call_in_pieces_runs_once_whole(fake: Any) -> None:
    f = fake(
        [
            [
                _chunk("Opening it."),
                _chunk(calls=[_piece(0, id="call_9", name="open_section", args='{"sec')]),
                _chunk(calls=[_piece(0, args='tion": "security"}')]),
                _end(),
            ]
        ]
    )
    brain = _Guide()
    assert await _drain(brain) == ["Opening it."]
    assert brain.ran == ["security"]
    assert len(f.requests) == 1


async def test_the_context_goes_back_as_chat_messages(fake: Any) -> None:
    f = fake(
        [
            [
                _chunk("Opening it."),
                _chunk(calls=[_piece(0, id="call_9", name="ping", args="{}")]),
                _end(),
            ],
            [_chunk("Sure."), _end()],
        ]
    )
    brain = _Guide(reasoning="low")
    await _drain(brain)
    session: Any = _Session()
    await brain.on_finalize(session, Finalize(1, "Opening it.", "Opening it."))
    await _drain(brain, "thanks")

    second = f.requests[1]
    assert second["reasoning_effort"] == "low"
    # drop_params would drop it silently for a model LiteLLM does not list as reasoning,
    # and the model would answer at its default effort.
    assert second["allowed_openai_params"] == ["reasoning_effort"]
    assert second["drop_params"] is True
    assert second["stream_options"] == {"include_usage": True}
    messages = second["messages"]
    assert messages[0] == {"role": "system", "content": "be brief"}
    assert messages[1] == {"role": "user", "content": "hello"}
    assert messages[2]["role"] == "assistant"
    assert messages[2]["content"] == "Opening it."
    assert messages[2]["tool_calls"] == [
        {"id": "call_9", "type": "function", "function": {"name": "ping", "arguments": "{}"}}
    ]
    assert messages[3]["role"] == "tool"
    assert messages[3]["tool_call_id"] == "call_9"
    assert messages[4] == {"role": "user", "content": "thanks"}


async def test_a_forced_tool_is_named(fake: Any) -> None:
    f = fake([[_chunk(calls=[_piece(0, id="c", name="ping", args="{}")]), _end()]])
    session: Any = _Session()
    _ = [e async for e in _Guide().respond_with(session, tools=ToolChoice.only("ping"))]
    req = f.requests[0]
    assert req["tool_choice"] == {"type": "function", "function": {"name": "ping"}}
    assert len(req["tools"]) == 2


async def test_through_the_responses_bridge_a_forced_tool_is_the_only_one(fake: Any) -> None:
    """LiteLLM's Responses bridge passes a named tool_choice on in a shape OpenAI
    refuses; "only this tool, and you must call it" is the same request."""
    f = fake([[_chunk(calls=[_piece(0, id="c", name="ping", args="{}")]), _end()]])
    session: Any = _Session()
    brain = _Guide(model="openai/responses/gpt-6-sol")
    _ = [e async for e in brain.respond_with(session, tools=ToolChoice.only("ping"))]
    req = f.requests[0]
    assert req["tool_choice"] == "required"
    assert [t["function"]["name"] for t in req["tools"]] == ["ping"]


async def test_tools_off_is_none(fake: Any) -> None:
    f = fake([[_chunk("Ok."), _end()]])
    session: Any = _Session()
    _ = [e async for e in _Guide().respond_with(session, tools=ToolChoice.NONE)]
    assert f.requests[0]["tool_choice"] == "none"


def test_usage_counts_reasoning_and_cache_writes_apart() -> None:
    usage = layer._usage(_usage(prompt=900, completion=50, cached=512, reasoning=20))  # pyright: ignore[reportPrivateUsage]
    assert (usage.input, usage.cached_input, usage.output, usage.reasoning) == (900, 512, 30, 20)
    assert usage.cache_write is None

    anthropic = SimpleNamespace(
        prompt_tokens=900,
        completion_tokens=10,
        prompt_tokens_details=None,
        completion_tokens_details=None,
        cache_creation_input_tokens=700,
    )
    usage = layer._usage(anthropic)  # pyright: ignore[reportPrivateUsage]
    assert (usage.cache_write, usage.reasoning, usage.output) == (700, None, 10)


def test_the_provider_is_the_company_at_the_end_of_the_route() -> None:
    company = layer._company  # pyright: ignore[reportPrivateUsage]
    assert company("openai/responses/gpt-6-sol") == "openai"
    assert company("anthropic/claude-haiku-5-5") == "anthropic"
    assert company("gemini/gemini-3.5-flash") == "google"
    assert company("vertex_ai/gemini-3.5-flash") == "google"
    assert company("gpt-6-sol") == ""
