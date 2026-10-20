"""``OpenAIBrain``: the voice core on OpenAI's Responses API.

The voice behaviour itself — speech before a call, results filed for the next
request, heard truth, the leaked-call guard — is pinned once, against Gemini, in
``test_gemini_*``. These pin OpenAI's half: what a request carries, how the
stream is read, and how the context goes back in.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Literal

from pydantic import BaseModel

from voqalize.sdk import Finalize, Speech, SpeechChunk, SpeechEnd, SpeechStart, UserMessage
from voqalize.sdk.openai import OpenAIBrain
from voqalize.sdk.voice import ToolChoice, needs_result_now

# ─── The API, scripted ────────────────────────────────────────────────────────


def _ev(type: str, **fields: Any) -> SimpleNamespace:
    return SimpleNamespace(type=type, **fields)


def _say(*pieces: str) -> list[SimpleNamespace]:
    return [_ev("response.output_text.delta", delta=p) for p in pieces]


def _call(name: str, arguments: str = "{}", call_id: str = "c1") -> SimpleNamespace:
    item = SimpleNamespace(type="function_call", call_id=call_id, name=name, arguments=arguments)
    return _ev("response.output_item.done", item=item)


class _Reasoning(BaseModel):
    type: Literal["reasoning"] = "reasoning"
    id: str = "rs_1"
    summary: list[Any] = []
    encrypted_content: str = "opaque"
    status: str = "completed"


def _thought() -> SimpleNamespace:
    return _ev("response.output_item.done", item=_Reasoning())


def _done(
    input: int = 100, cached: int = 0, write: int = 0, output: int = 10, reasoning: int = 0
) -> SimpleNamespace:
    usage = SimpleNamespace(
        input_tokens=input,
        input_tokens_details=SimpleNamespace(cached_tokens=cached, cache_write_tokens=write),
        output_tokens=output,
        output_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
    )
    return _ev("response.completed", response=SimpleNamespace(usage=usage))


class _Stream:
    def __init__(self, events: list[SimpleNamespace]) -> None:
        self._events = events

    def __aiter__(self) -> Any:
        return self._gen()

    async def _gen(self) -> Any:
        for event in self._events:
            yield event


class _Responses:
    """Stands in for ``client.responses``: one scripted response per request."""

    def __init__(self, script: list[list[SimpleNamespace]]) -> None:
        self._script = list(script)
        self.requests: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> _Stream:
        # Copied as the API serialises it: the brain goes on editing its context.
        import copy

        self.requests.append(copy.deepcopy(kwargs))
        return _Stream(self._script.pop(0))


class _Client:
    def __init__(self, script: list[list[SimpleNamespace]]) -> None:
        self.responses = _Responses(script)


# ─── A brain ──────────────────────────────────────────────────────────────────


class _Section(BaseModel):
    """Which section to open."""

    section: Literal["pricing", "security"]


class _Guide(OpenAIBrain):
    def __init__(self, client: Any, **kwargs: Any) -> None:
        super().__init__(client=client, system_instruction="be brief", model="gpt-x", **kwargs)
        self.ran: list[str] = []

    @property
    def tools(self) -> list[Any]:
        return [self.open_section, self.where]

    async def open_section(self, args: _Section) -> str:
        """Open a section."""
        self.ran.append(f"open:{args.section}")
        return "ok"

    @needs_result_now
    async def where(self) -> str:
        """Where they are."""
        self.ran.append("where")
        return "on pricing"


class _Session:
    can_report_usage = False


async def _drain(brain: _Guide, text: str = "hello") -> list[Speech]:
    return [ev async for ev in brain.on_user_message(_Session(), UserMessage(text))]  # pyright: ignore[reportArgumentType]


def _shape(events: list[Speech]) -> list[str]:
    out: list[str] = []
    for ev in events:
        if isinstance(ev, SpeechStart):
            out.append("[")
        elif isinstance(ev, SpeechEnd):
            out.append("]")
        elif isinstance(ev, SpeechChunk):
            out.append(ev.text)
    return out


# ─── The request ──────────────────────────────────────────────────────────────


async def test_the_request_keeps_the_conversation_here() -> None:
    client = _Client([[*_say("Hi."), _done()]])
    brain = _Guide(client, reasoning="low")
    await _drain(brain)

    [req] = client.responses.requests
    assert req["store"] is False
    assert "previous_response_id" not in req
    assert req["instructions"] == "be brief"
    assert req["reasoning"] == {"effort": "low"}
    assert req["include"] == ["reasoning.encrypted_content"]
    assert req["input"] == [{"role": "user", "content": "hello"}]
    assert req["tool_choice"] == "auto"


async def test_a_model_parameter_is_declared_flat() -> None:
    client = _Client([[*_say("Hi."), _done()]])
    await _drain(_Guide(client))

    tools = {t["name"]: t for t in client.responses.requests[0]["tools"]}
    assert tools["open_section"]["description"] == "Open a section."
    params = tools["open_section"]["parameters"]
    assert params["properties"]["section"]["enum"] == ["pricing", "security"]
    assert params["required"] == ["section"]
    assert tools["where"]["parameters"]["properties"] == {}


async def test_no_reasoning_setting_sends_none() -> None:
    client = _Client([[*_say("Hi."), _done()]])
    await _drain(_Guide(client))
    assert "reasoning" not in client.responses.requests[0]
    assert "include" not in client.responses.requests[0]


async def test_options_reach_every_request() -> None:
    client = _Client([[*_say("Hi."), _done()]])
    await _drain(_Guide(client, options={"prompt_cache_key": "emily"}))
    assert client.responses.requests[0]["prompt_cache_key"] == "emily"


async def test_tool_choice_maps_to_the_api() -> None:
    client = _Client(
        [[*_say("Ok."), _done()], [_call("open_section", '{"section": "pricing"}'), _done()]]
    )
    brain = _Guide(client)
    session: Any = _Session()
    _ = [e async for e in brain.respond_with(session, tools=ToolChoice.NONE)]
    _ = [e async for e in brain.respond_with(session, tools=ToolChoice.only("open_section"))]

    first, second = client.responses.requests
    assert first["tool_choice"] == "none"
    assert second["tool_choice"] == {"type": "function", "name": "open_section"}


# ─── The stream and the context ───────────────────────────────────────────────


async def test_speech_goes_out_before_the_call_and_the_result_is_filed() -> None:
    client = _Client(
        [[*_say("Opening ", "it now."), _call("open_section", '{"section": "pricing"}'), _done()]]
    )
    brain = _Guide(client)
    events = await _drain(brain)

    assert _shape(events) == ["[", "Opening ", "it now.", "]"]
    assert brain.ran == ["open:pricing"]
    # One request: the result waits for the user's next message.
    assert len(client.responses.requests) == 1
    roles = [t.role for t in brain._history]  # pyright: ignore[reportPrivateUsage]
    assert roles == ["user", "model", "results"]


async def test_the_context_goes_back_in_as_responses_items() -> None:
    client = _Client(
        [
            [
                _thought(),
                *_say("Opening it."),
                _call("open_section", '{"section": "pricing"}'),
                _done(),
            ],
            [*_say("Sure."), _done()],
        ]
    )
    brain = _Guide(client)
    events = await _drain(brain)
    await brain.on_finalize(_Session(), Finalize(1, "Opening it.", "Opening it."))  # pyright: ignore[reportArgumentType]
    del events
    await _drain(brain, "thanks")

    second = client.responses.requests[1]["input"]
    assert second[0] == {"role": "user", "content": "hello"}
    assert second[1]["type"] == "reasoning"
    assert second[1]["encrypted_content"] == "opaque"
    assert "status" not in second[1]
    assert second[2] == {"role": "assistant", "content": "Opening it."}
    assert second[3] == {
        "type": "function_call",
        "call_id": "c1",
        "name": "open_section",
        "arguments": '{"section": "pricing"}',
    }
    assert second[4]["type"] == "function_call_output"
    assert second[4]["call_id"] == "c1"
    assert '"result":"ok"' in second[4]["output"]
    assert second[5] == {"role": "user", "content": "thanks"}


async def test_heard_truth_cuts_the_reply_and_drops_reasoning_left_with_nothing() -> None:
    client = _Client(
        [[_thought(), *_say("One. ", "Two. ", "Three."), _done()], [*_say("Ok."), _done()]]
    )
    brain = _Guide(client)
    await _drain(brain)
    # The user heard nothing of it: the words leave, and the reasoning that
    # produced them goes too, since the API refuses reasoning that precedes nothing.
    await brain.on_finalize(_Session(), Finalize(1, "", "One. Two. Three."))  # pyright: ignore[reportArgumentType]
    await _drain(brain, "again")

    assert client.responses.requests[1]["input"] == [
        {"role": "user", "content": "hello"},
        {"role": "user", "content": "again"},
    ]


async def test_heard_truth_keeps_the_heard_prefix() -> None:
    client = _Client([[*_say("One. ", "Two. ", "Three."), _done()], [*_say("Ok."), _done()]])
    brain = _Guide(client)
    await _drain(brain)
    await brain.on_finalize(_Session(), Finalize(1, "One. Tw", "One. Two. Three."))  # pyright: ignore[reportArgumentType]
    await _drain(brain, "again")

    assert client.responses.requests[1]["input"][1] == {"role": "assistant", "content": "One. Tw"}


async def test_a_marked_tool_asks_again_with_its_result() -> None:
    client = _Client([[_call("where"), _done()], [*_say("You are on pricing."), _done()]])
    brain = _Guide(client)
    events = await _drain(brain)

    assert brain.ran == ["where"]
    assert _shape(events) == ["[", "You are on pricing.", "]"]
    second = client.responses.requests[1]["input"]
    assert second[-1]["type"] == "function_call_output"
    assert "on pricing" in second[-1]["output"]


async def test_bad_arguments_go_back_to_the_model_as_an_error() -> None:
    client = _Client([[_call("open_section", '{"section": "nowhere"}'), _done()]])
    brain = _Guide(client)
    await _drain(brain)

    assert brain.ran == []
    results = brain._history[-1]  # pyright: ignore[reportPrivateUsage]
    assert '"error"' in results.parts[0]["output"]


async def test_a_refusal_is_spoken() -> None:
    client = _Client([[_ev("response.refusal.delta", delta="I can't help with that."), _done()]])
    assert _shape(await _drain(_Guide(client))) == ["[", "I can't help with that.", "]"]


async def test_usage_counts_reasoning_apart_from_output() -> None:
    from voqalize.sdk.openai import _usage  # pyright: ignore[reportPrivateUsage]

    usage = _usage(
        _done(input=5000, cached=4096, write=900, output=60, reasoning=20).response.usage
    )
    assert usage is not None
    assert (usage.input, usage.cached_input, usage.cache_write) == (5000, 4096, 900)
    assert (usage.output, usage.reasoning) == (40, 20)


async def test_a_failed_response_raises() -> None:
    import pytest

    failed = _ev("response.failed", response=SimpleNamespace(error="server_error"))
    client = _Client([[failed]])
    with pytest.raises(RuntimeError, match="server_error"):
        await _drain(_Guide(client))
