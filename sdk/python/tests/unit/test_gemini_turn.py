"""`GeminiBrain` owns its tool loop: it speaks first, and a result waits.

Each request is one response. A tool runs the moment its call arrives in the
stream, after the speech before it has gone out, and its result is filed in the
context right after the call. The turn ends when the stream does — unless the
response called a tool marked `needs_result_now`, and then the model is asked
again at once, with every result, up to `max_tool_hops` times.

The stand-in below is a model and nothing more: each request plays the next
response of the script, up to and including its `finish_reason`, and records the
contents it was sent. It runs no tools, because google-genai with automatic
function calling disabled runs none either — if a tool ran, the brain ran it.

`tests/contract/test_brain_contract.py` states the engine-agnostic clauses this
brain has to satisfy (a turn ends, every call is answered, `tools` is read once,
...) once, against every engine. This file is what needs the scripted model to
exercise: the unit boundaries, the loop, the watchdog and the log line.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Literal

import pytest
from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field

from voqalize.sdk import Session
from voqalize.sdk.actions import Action
from voqalize.sdk.brain import _adapter_for
from voqalize.sdk.events import Speech, SpeechChunk, SpeechEnd, SpeechStart, UserMessage
from voqalize.sdk.gemini import TOOL_BUDGET_MS, GeminiBrain, needs_result_now
from voqalize.sdk.wire import (
    Frame,
    RTVIFrame,
    SessionStartFrame,
    SpeechStartFrame,
    UserMessageFrame,
)


class _Wire:
    """An emitter that keeps what the brain put on the wire."""

    def __init__(self) -> None:
        self.frames: list[Frame] = []

    def send(self, frame: Frame) -> None:
        self.frames.append(frame)


# ─── The model, scripted ──────────────────────────────────────────────────────


def _text(*chunks: str, done: bool = True) -> list[types.GenerateContentResponse]:
    """One hop that speaks. Each string is its own chunk, as the API streams."""
    out = [_chunk([types.Part(text=t)]) for t in chunks]
    if done:
        out.append(_chunk([], finish=True))
    return out


def _calls(*names: str) -> list[types.GenerateContentResponse]:
    """One hop that only calls tools, and says nothing."""
    return [
        _chunk(
            [
                types.Part(function_call=types.FunctionCall(name=n, args=_ARGS.get(n, {})))
                for n in names
            ]
        ),
        _chunk([], finish=True),
    ]


_ARGS = {"show": {"args": {"name": "glucose"}}}


def _chunk(parts: list[types.Part], *, finish: bool = False) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=parts),
                finish_reason=types.FinishReason.STOP if finish else None,
            )
        ]
    )


def _without_calls(chunk: types.GenerateContentResponse) -> types.GenerateContentResponse:
    candidates = [
        c.model_copy(
            update={
                "content": types.Content(
                    role="model",
                    parts=[p for p in (c.content.parts or []) if not p.function_call]
                    if c.content
                    else [],
                )
            }
        )
        for c in chunk.candidates or []
    ]
    return chunk.model_copy(update={"candidates": candidates})


class _ScriptedModels:
    """Stands in for ``client.aio.models``: one scripted response per request."""

    def __init__(self, script: list[types.GenerateContentResponse]) -> None:
        self._script = list(script)
        #: The contents of every request, in order.
        self.requests: list[list[types.Content]] = []
        #: Whether each request allowed a function call.
        self.may_call: list[bool] = []

    @property
    def contents(self) -> list[types.Content]:
        """What the last request carried."""
        return self.requests[-1]

    async def generate_content_stream(self, *, model: str, contents: Any, config: Any) -> Any:
        # Copied now, as the API serialises it now: the brain goes on writing
        # its history while the stream plays.
        self.requests.append([c.model_copy(deep=True) for c in contents])
        # google-genai deep-copies the config, so this does too: it is the step
        # that would clone a brain handed over as a bound method.
        config = config.model_copy(deep=True)
        if config.tools:
            assert config.automatic_function_calling.disable, "AFC would run the tools"
        fc = config.tool_config and config.tool_config.function_calling_config
        may_call = not (fc and fc.mode == types.FunctionCallingConfigMode.NONE)
        self.may_call.append(may_call)
        response: list[types.GenerateContentResponse] = []
        while self._script:
            chunk = self._script.pop(0)
            if not may_call:
                # What the model does when it may not call: it answers instead.
                chunk = _without_calls(chunk)
            response.append(chunk)
            if any(c.finish_reason for c in chunk.candidates or []):
                break

        async def gen() -> Any:
            for chunk in response:
                yield chunk

        return gen()


class _ScriptedClient:
    def __init__(self, script: list[types.GenerateContentResponse]) -> None:
        self.aio = self
        self.models = _ScriptedModels(script)


# ─── A brain with three tools ─────────────────────────────────────────────────


class _Show(Action):
    """Put a section of the screen in front of the caller."""

    name: str


class _Section(BaseModel):
    """Which part of the screen to show."""

    name: Literal["glucose", "meals"] = Field(description="Section to show.")


class _Coach(GeminiBrain):
    def __init__(self, client: Any) -> None:
        super().__init__(client=client, system_instruction="be brief")
        self.ran: list[str] = []
        self.seen: tuple[Session | None, int | None] = (None, None)

    @property
    def tools(self) -> list[Any]:
        return [self.show, self.ping, self.boom, self.lookup, self.slow]

    async def show(self, args: _Section) -> str:
        """Put a section of the screen in front of the caller."""
        self.ran.append(f"show:{args.name}")
        return "shown"

    async def ping(self) -> str:
        """Say hello to nothing in particular."""
        self.ran.append("ping")
        self.seen = self.session
        return "pong"

    async def boom(self) -> str:
        """Fail."""
        raise ValueError("kaboom")

    @needs_result_now
    async def lookup(self) -> int:
        """Read a number the model needs to answer."""
        self.ran.append("lookup")
        return 42

    async def slow(self) -> str:
        """Take longer than a tool may."""
        await asyncio.sleep(TOOL_BUDGET_MS * 2 / 1000)
        self.ran.append("slow")
        return "done"


async def _brain(script: list[types.GenerateContentResponse]) -> tuple[_Coach, Session]:
    brain, _, session = await _open(_Coach(_ScriptedClient(script)))
    return brain, session


async def _open[B: GeminiBrain](brain: B) -> tuple[B, _Wire, Session]:
    wire = _Wire()
    adapter = _adapter_for(brain, wire)
    await adapter.handle_frame(SessionStartFrame(turn_id=1, session_id="s"))
    session = adapter._session  # pyright: ignore[reportPrivateUsage]
    assert session is not None
    brain._adapter = adapter  # pyright: ignore[reportAttributeAccessIssue]
    return brain, wire, session


async def _turn(brain: _Coach, text: str = "hello") -> None:
    """Drive one turn the way Voqalize does — through the adapter, so the turn is
    spawned in its own task with `_current_turn` set."""
    adapter = brain._adapter  # pyright: ignore[reportAttributeAccessIssue]
    await adapter.handle_frame(UserMessageFrame(turn_id=2, text=text))
    while adapter._turns:  # pyright: ignore[reportPrivateUsage]
        await asyncio.gather(*list(adapter._turns))  # pyright: ignore[reportPrivateUsage]


async def _drain(brain: _Coach, session: Session) -> list[Speech]:
    return [ev async for ev in brain.on_user_message(session, UserMessage(text="hello"))]


def _shape(events: list[Speech]) -> list[str]:
    out = []
    for ev in events:
        if isinstance(ev, SpeechStart):
            out.append("[")
        elif isinstance(ev, SpeechEnd):
            out.append("]")
        elif isinstance(ev, SpeechChunk):
            out.append(ev.text)
    return out


def _history(brain: _Coach) -> list[str]:
    """History as ``role: what-is-in-it``, enough to read the shape at a glance."""
    out = []
    for content in brain._history:
        bits = []
        for part in content.parts or []:
            if part.text:
                bits.append(part.text)
            if part.function_call:
                bits.append(f"call:{part.function_call.name}")
            if part.function_response:
                bits.append(f"resp:{part.function_response.name}")
        out.append(f"{content.role}: {'|'.join(bits)}")
    return out


# ─── The two rules ────────────────────────────────────────────────────────────


async def test_a_thought_is_not_spoken() -> None:
    """Thought parts carry text that is reasoning, not speech. They belong in the
    context — Gemini 3 wants them handed back — and never on the wire."""
    script = [
        _chunk([types.Part(text="weighing it up", thought=True)]),
        _chunk([types.Part(text="Good evening.")]),
        _chunk([], finish=True),
    ]
    brain, session = await _brain(script)

    assert _shape(await _drain(brain, session)) == ["[", "Good evening.", "]"]
    assert "weighing it up" in _history(brain)[1]


async def test_a_stream_that_ends_without_a_finish_reason_still_closes_the_unit() -> None:
    """A `SpeechStart` with no `SpeechEnd` is a wire violation, so the end of the
    stream closes the unit whatever the model said about why it stopped."""
    brain, session = await _brain(_text("Cut short", done=False))

    assert _shape(await _drain(brain, session)) == ["[", "Cut short", "]"]


# ─── The loop ─────────────────────────────────────────────────────────────────


def _requests(brain: GeminiBrain) -> list[list[types.Content]]:
    return brain._client.models.requests  # pyright: ignore[reportPrivateUsage, reportAttributeAccessIssue]


def _said(contents: list[types.Content]) -> list[str]:
    return [
        f"resp:{p.function_response.name}"
        for c in contents
        for p in c.parts or []
        if p.function_response
    ]


async def test_a_turn_that_only_acks_ends_after_one_request() -> None:
    """The hop this program removes. The model calls a tool whose result it does
    not need to speak, the tool runs, and the turn ends with the stream: no
    second request, and the result is in the context for the next one."""
    brain, session = await _brain(_calls("ping") + _text("never asked for"))

    await _drain(brain, session)

    assert brain.ran == ["ping"]
    assert len(_requests(brain)) == 1
    assert _history(brain) == ["user: hello", "model: call:ping", "user: resp:ping"]


async def test_a_result_that_waited_reaches_the_model_with_the_next_message() -> None:
    """Deferred, not dropped: the next user message is sent after the response,
    as its own user turn — the shape verified on live Gemini."""
    brain, session = await _brain(_calls("ping") + _text("It was pong."))

    await _drain(brain, session)
    await _drain(brain, session)

    second = _requests(brain)[1]
    assert [c.role for c in second] == ["user", "model", "user", "user"]
    assert _said(second) == ["resp:ping"]
    assert _history(brain)[-1] == "model: It was pong."


async def test_a_call_that_needs_its_result_now_asks_again_with_every_result() -> None:
    """One marked call in a response is enough to ask again, and that request
    carries every result the response produced, marked or not."""
    brain, session = await _brain(_calls("ping", "lookup") + _text("It's 42."))

    assert _shape(await _drain(brain, session)) == ["[", "It's 42.", "]"]

    assert len(_requests(brain)) == 2
    assert _said(_requests(brain)[1]) == ["resp:ping", "resp:lookup"]
    assert _history(brain) == [
        "user: hello",
        "model: call:ping|call:lookup",
        "user: resp:ping|resp:lookup",
        "model: It's 42.",
    ]


async def test_max_tool_hops_stops_a_chain_of_marked_calls() -> None:
    """``max_tool_hops`` is how many times one turn may ask again. A model that
    keeps calling a marked tool is asked once more with calls switched off, so
    the turn still ends in something the user hears."""

    class _Short(_Coach):
        def __init__(self, client: Any) -> None:
            GeminiBrain.__init__(self, client=client, system_instruction="x", max_tool_hops=2)
            self.ran = []

    lines: list[str] = []
    sink = logger.add(lines.append, level="WARNING", format="{message}")
    try:
        script = _calls("lookup") * 2 + [
            _chunk([types.Part(function_call=types.FunctionCall(name="lookup", args={}))]),
            *_text("It's 42."),
        ]
        brain, _, session = await _open(_Short(_ScriptedClient(script)))
        events = await _drain(brain, session)  # pyright: ignore[reportArgumentType]
    finally:
        logger.remove(sink)

    models = brain._client.models  # pyright: ignore[reportAttributeAccessIssue]
    assert models.may_call == [True, True, False], "two hops that ran a tool, then an answer"
    assert brain.ran == ["lookup"] * 2
    assert _shape(events) == ["[", "It's 42.", "]"]
    assert any("max_tool_hops=2" in line for line in lines)


async def test_speech_before_a_call_is_heard_before_the_tool_runs() -> None:
    """ "Opening it now." goes out, then the screen opens. A tool that ran first
    would hold the line back for as long as the tool took."""
    order: list[str] = []

    class _Watched(_Coach):
        async def ping(self) -> str:
            """Note when it ran."""
            order.append("tool")
            return "pong"

    brain, _, session = await _open(
        _Watched(
            _ScriptedClient(
                [
                    _chunk([types.Part(text="Opening it now.")]),
                    _chunk([types.Part(function_call=types.FunctionCall(name="ping", args={}))]),
                    _chunk([], finish=True),
                ]
            )
        )
    )
    async for ev in brain.on_user_message(session, UserMessage(text="hello")):
        order += _shape([ev])

    assert order == ["[", "Opening it now.", "tool", "]"]
    assert _history(brain) == ["user: hello", "model: Opening it now.|call:ping", "user: resp:ping"]


async def test_a_response_carries_the_id_of_the_call_it_answers() -> None:
    call = types.FunctionCall(name="ping", args={}, id="call-7")
    brain, session = await _brain([_chunk([types.Part(function_call=call)], finish=True)])

    await _drain(brain, session)

    response = brain._history[-1].parts[0].function_response  # pyright: ignore[reportOptionalSubscript, reportPrivateUsage]
    assert response is not None
    assert (response.id, response.name, response.response) == (
        "call-7",
        "ping",
        {"result": "pong"},
    )


async def test_a_tool_that_raises_answers_with_the_error() -> None:
    """What google-genai's own loop did, kept: the model reads ``{'error': …}``,
    and the failure is logged, because the model may well say it succeeded."""
    lines: list[str] = []
    sink = logger.add(lines.append, level="WARNING", format="{message}")
    try:
        brain, session = await _brain(_calls("boom"))
        await _drain(brain, session)
    finally:
        logger.remove(sink)

    response = brain._history[-1].parts[0].function_response  # pyright: ignore[reportOptionalSubscript, reportPrivateUsage]
    assert response is not None and "kaboom" in str((response.response or {})["error"])
    assert any(line.startswith("tool boom failed") for line in lines)


async def test_a_call_to_a_tool_not_declared_answers_with_an_error() -> None:
    brain, session = await _brain(_calls("nonesuch"))

    await _drain(brain, session)

    response = brain._history[-1].parts[0].function_response  # pyright: ignore[reportOptionalSubscript, reportPrivateUsage]
    assert response is not None and "nonesuch" in str((response.response or {})["error"])


async def test_a_slow_tool_is_logged_and_still_counts() -> None:
    """The watchdog warns and does nothing else: the tool finishes, its result
    is filed, and nothing is cancelled or reordered."""
    lines: list[str] = []
    sink = logger.add(lines.append, level="WARNING", format="{message}")
    try:
        brain, session = await _brain(_calls("slow"))
        await _drain(brain, session)
    finally:
        logger.remove(sink)

    assert brain.ran == ["slow"]
    assert _history(brain)[-1] == "user: resp:slow"
    slow = [line for line in lines if "over the" in line]
    assert len(slow) == 1 and slow[0].startswith("tool _Coach.slow took ")


async def test_a_fast_tool_is_not_logged() -> None:
    lines: list[str] = []
    sink = logger.add(lines.append, level="WARNING", format="{message}")
    try:
        brain, session = await _brain(_calls("ping"))
        await _drain(brain, session)
    finally:
        logger.remove(sink)

    assert lines == []


async def test_a_barge_in_during_a_tool_drops_that_call_and_keeps_the_ones_that_ran() -> None:
    """A call is in the context before its tool returns. Cut there, and it has no
    response and never will; Gemini will not accept it on the next turn, so it
    goes. A call before it that ran and was answered stays, answer and all."""
    started = asyncio.Event()

    class _Stuck(_Coach):
        async def slow(self) -> str:
            """Never return."""
            started.set()
            await asyncio.Event().wait()
            return "never"

    brain, _, session = await _open(_Stuck(_ScriptedClient(_calls("ping", "slow"))))

    async def run() -> None:
        async for _ in brain.on_user_message(session, UserMessage(text="hello")):
            pass

    task = asyncio.create_task(run())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert _history(brain) == ["user: hello", "model: call:ping", "user: resp:ping"]


async def test_a_barge_in_on_the_speech_before_a_call_leaves_no_call_behind() -> None:
    """The speech before a call goes out first, so a barge-in can land there,
    before the call is in the context or its tool has run."""
    brain, session = await _brain(
        [
            _chunk(
                [
                    types.Part(text="Opening it now."),
                    types.Part(function_call=types.FunctionCall(name="ping", args={})),
                ]
            ),
            _chunk([], finish=True),
        ]
    )

    gen = brain.on_user_message(session, UserMessage(text="hello"))
    async for ev in gen:
        if isinstance(ev, SpeechChunk):
            break
    await gen.aclose()

    assert brain.ran == []
    assert _history(brain) == ["user: hello", "model: Opening it now."]


async def test_a_barge_in_mid_turn_closes_the_generator_cleanly() -> None:
    """A cancelled turn closes this generator by throwing `GeneratorExit` at the
    yield. An async generator that yields while closing raises instead of tearing
    down — so the trailing `SpeechEnd` must never be in a `finally`."""
    script = [
        _chunk([types.Part(function_call=types.FunctionCall(name="ping", args={}))]),
        *_text("One ", "two ", "three"),
    ]
    brain, session = await _brain(script)

    gen = brain.on_user_message(session, UserMessage(text="hello"))
    seen = []
    async for ev in gen:
        seen.append(ev)
        if isinstance(ev, SpeechChunk):
            break
    await gen.aclose()

    assert _shape(seen) == ["[", "One "]
    # The tool ran and was answered before the cut, so both stay in the context.
    assert _history(brain)[:3] == ["user: hello", "model: call:ping|One ", "user: resp:ping"]


def _user(text: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part(text=text)])


async def test_append_to_context_lands_where_it_was_called() -> None:
    """Appended once, in place, in front of what the caller says next — not
    re-rendered onto the request the way `grounding()` did."""
    brain, _, session = await _open(_Coach(_ScriptedClient(_text("Sure."))))
    brain.append_to_context(_user("the caller is looking at the meals tab"))

    await _drain(brain, session)

    sent = brain._client.models.contents  # pyright: ignore[reportPrivateUsage]
    assert [p.text for c in sent for p in (c.parts or [])] == [
        "the caller is looking at the meals tab",
        "hello",
    ]
    assert _history(brain)[:2] == [
        "user: the caller is looking at the meals tab",
        "user: hello",
    ]


async def test_appending_mid_turn_lands_in_the_turn_that_is_running() -> None:
    """Immediately means immediately, including from inside a tool.

    `grounding()` was re-read per hop, so a turn silently re-argued from whatever
    the screen said last. This is the opposite: one append, at the point it was
    made. The SDK does not hold it back for a quiet moment — what to append and
    when is the developer's.

    The one thing it may not do is split a call from its answer, so the answer
    is filed directly after the call and the append lands behind both.
    """

    class _Moving(_Coach):
        async def ping(self) -> str:
            """Move the screen from under the turn, as a caller's thumb does."""
            self.append_to_context(_user("now on the meals tab"))
            return "pong"

    brain, _, session = await _open(_Moving(_ScriptedClient(_calls("ping"))))
    await _drain(brain, session)

    assert _history(brain) == [
        "user: hello",
        "model: call:ping",
        "user: resp:ping",
        "user: now on the meals tab",
    ]


async def test_append_to_context_rejects_the_model_side() -> None:
    """The model's half of a conversation is written by the model. A brain that
    puts words in its mouth is telling it that it already said them."""
    brain, _, _ = await _open(_Coach(_ScriptedClient(_text("Sure."))))
    with pytest.raises(ValueError, match="user content"):
        brain.append_to_context(
            types.Content(role="model", parts=[types.Part(text="of course, doctor")])
        )
    assert brain._history == []  # pyright: ignore[reportPrivateUsage]


# ─── Declarations ─────────────────────────────────────────────────────────────


def _declared(brain: GeminiBrain) -> list[Any]:
    return list(brain._turn_config().tools or [])  # pyright: ignore[reportPrivateUsage]


async def test_the_method_is_the_declaration() -> None:
    """One pydantic model, one docstring, no second copy. A tool with no
    parameters declares none at all rather than an empty object."""
    from google.genai import _transformers

    client = genai.Client(api_key="not-used-no-call-is-made")
    brain = _Coach(client)
    declared = {
        fd.name: fd
        for fn in _declared(brain)
        for fd in (_transformers.t_tool(client, fn).function_declarations or [])
    }

    assert set(declared) == {"show", "ping", "boom", "lookup", "slow"}
    assert declared["show"].description == "Put a section of the screen in front of the caller."
    schema = declared["show"].parameters_json_schema
    assert schema is not None
    section = schema["properties"]["args"]["properties"]["name"]
    assert section == {
        "description": "Section to show.",
        "enum": ["glucose", "meals"],
        "title": "Name",
        "type": "string",
    }
    assert declared["ping"].parameters_json_schema is None


async def test_a_tool_is_callable_the_way_the_loop_calls_it() -> None:
    """The declaration being right does not mean the call is.

    The loop builds a tool's arguments with google-genai's own conversion, which
    reads ``inspect.signature``, not the schema it sent. Every brain module uses ``from __future__ import annotations``, so a
    method's own annotations are strings — and a string where a model class should
    be makes ``isinstance`` raise, which google-genai turns into
    ``{'error': ...}`` and hands to the model. The model then tells the caller it
    did the thing. Nothing else here can see that: the schema is correct, the
    stream is well-formed, and the tool simply never runs."""
    from google.genai import _extra_utils

    brain = _Coach(_ScriptedClient([]))
    show = next(fn for fn in _declared(brain) if fn.__name__ == "show")

    assert inspect.signature(show).parameters["args"].annotation is _Section
    await _extra_utils.invoke_function_from_dict_args_async({"args": {"name": "glucose"}}, show)
    assert brain.ran == ["show:glucose"]


async def test_the_brain_is_not_handed_to_google_genai() -> None:
    """google-genai deep-copies the config it is given, on every request, and
    ``copy.deepcopy`` of a bound method copies ``__self__``
    with it, by definition. A brain that crossed that line would have its tools
    called on a *clone*: ``self.session.dispatch`` reaching nothing, the
    context written to an object no one reads, the model told ``ok``, and not
    one thing on the wire to say so. So a bound method never crosses it — what is
    declared is a plain function, which ``deepcopy`` leaves alone."""
    brain = _Coach(_ScriptedClient([]))

    config = brain._turn_config()  # pyright: ignore[reportPrivateUsage]
    declared = list(config.tools or [])
    assert not any(hasattr(fn, "__self__") for fn in declared)

    copied = list(config.model_copy(deep=True).tools or [])
    assert copied == declared, "deepcopy left them alone; nothing was cloned"

    await next(fn for fn in copied if fn.__name__ == "show")(_Section(name="glucose"))
    assert brain.ran == ["show:glucose"], "it ran on this brain, not on a copy of it"


def test_the_declared_tool_is_the_method_and_the_method_is_untouched() -> None:
    """The closure carries the name, the docstring and the resolved signature, so
    the declaration Gemini reads is the method the developer wrote — and the
    method itself comes back exactly as it went in, annotations still the strings
    ``from __future__ import annotations`` made them."""
    brain = _Coach(_ScriptedClient([]))

    show = next(fn for fn in _declared(brain) if fn.__name__ == "show")
    assert show.__doc__ == _Coach.show.__doc__
    assert inspect.signature(show).parameters["args"].annotation is _Section

    assert not hasattr(_Coach.show, "__signature__")
    assert _Coach.show.__annotations__["args"] == "_Section"


async def test_tools_are_not_shared_between_brains() -> None:
    """The declarations are bound methods, so two sessions of the same brain drive
    two different screens."""
    a, _ = await _brain(_text("x"))
    b, _ = await _brain(_text("x"))

    await asyncio.gather(*(fn() for fn in _declared(a) if fn.__name__ == "ping"))

    assert a.ran == ["ping"]
    assert b.ran == []


async def test_a_tool_that_drives_the_screen_is_stamped_with_the_turn_it_ran_in() -> None:
    """The whole reason a tool needs `self.session`. It runs inside the turn task,
    so `dispatch` is correlated to the turn the model is answering with nothing
    plumbed through — and a call that comes before the speech changes the screen
    before the sentence about it starts."""

    class _Screen(_Coach):
        async def show(self, args: _Section) -> str:
            """Put a section of the screen in front of the caller."""
            self.session.dispatch(_Show(name=args.name))
            return "shown"

    script = [
        _chunk([types.Part(function_call=types.FunctionCall(name="show", args=_ARGS["show"]))]),
        *_text("There."),
    ]
    brain, wire, _ = await _open(_Screen(_ScriptedClient(script)))
    await _turn(brain)

    commands = [f for f in wire.frames if isinstance(f, RTVIFrame)]
    assert [(f.data or {}).get("payload") for f in commands] == [{"name": "glucose"}]
    assert [f.turn_id for f in commands] == [2]
    # The screen moved before the coach opened her mouth about it.
    assert wire.frames.index(commands[0]) < next(
        i for i, f in enumerate(wire.frames) if isinstance(f, SpeechStartFrame)
    )


async def test_a_turn_reports_what_it_cost_and_never_what_was_said() -> None:
    """The only direct measure of context growth, and the one we did not have.

    A 123-second production call was found to be re-sending twenty-one full cart
    snapshots — ~4,700 tokens of them — and the only way to know that was to
    reconstruct the context from a transcript afterwards. One INFO line per turn
    makes it a number instead. ``hops`` is on it because a turn that asks again
    for a result is several requests and ``prompt`` is only the last, largest
    one; the two together say whether a turn is wide or merely long.

    The line carries counts and nothing else — speech is never a log field."""
    lines: list[str] = []
    sink = logger.add(lines.append, level="INFO", format="{message}")
    try:
        script = [*_calls("lookup"), *_text("Pong.")]
        script[-1].usage_metadata = types.GenerateContentResponseUsageMetadata(
            prompt_token_count=1400,
            cached_content_token_count=1024,
            candidates_token_count=17,
            thoughts_token_count=42,
        )
        brain, session = await _brain(script)
        await _drain(brain, session)
    finally:
        logger.remove(sink)

    turn = next(line for line in lines if line.startswith("turn:"))
    assert "hops=2" in turn and "prompt=1400" in turn
    assert "calls=1" in turn and "awaited=1" in turn and "speechless=no" in turn
    assert "cached=1024" in turn and "output=17" in turn and "thoughts=42" in turn
    assert "hello" not in turn and "Pong" not in turn, "speech reached the log"


def _millis(turn: str, field: str) -> int | None:
    """The value of one ``field=…ms`` on the turn line, or None for ``none``."""
    value = next(part for part in turn.split() if part.startswith(f"{field}=")).split("=")[1]
    return None if value == "none" else int(value.removesuffix("ms"))


async def test_a_turn_reports_the_silence_the_caller_sat_through() -> None:
    """Row 18 of the demo-quality tracker — 2.9 to 5.2 seconds of brain before the
    first word — was measured off a transcript, because the brain itself said
    nothing about time. ``speak`` is that number at the source, and it sits beside
    ``hops`` and ``prompt`` so a slow turn can be attributed rather than guessed at:
    one slow round trip and three fast ones re-sending a bloated context look
    identical from the outside and are different bugs.

    ``open`` is separate from ``speak`` on purpose. A turn that waits on a tool's
    result starts streaming at once and says nothing for another request."""
    lines: list[str] = []
    sink = logger.add(lines.append, level="INFO", format="{message}")
    try:
        brain, session = await _brain([*_calls("lookup"), *_text("Pong.")])
        await _drain(brain, session)
    finally:
        logger.remove(sink)

    turn = next(line for line in lines if line.startswith("turn:"))
    open_ms, speak_ms, total_ms = (_millis(turn, f) for f in ("open", "speak", "total"))
    assert open_ms is not None and speak_ms is not None and total_ms is not None
    assert 0 <= open_ms <= speak_ms <= total_ms


async def test_a_turn_that_never_spoke_reports_no_time_to_speech() -> None:
    """A moment that never came is not a zero either. A turn that only called a
    tool, or one a barge-in cut before the first word, has no time-to-speech to
    report — and says it was speechless, which is the number a brain owner
    watches now that no second request hides it."""
    lines: list[str] = []
    sink = logger.add(lines.append, level="INFO", format="{message}")
    try:
        brain, session = await _brain(_calls("ping"))
        await _drain(brain, session)
    finally:
        logger.remove(sink)
    turn = next(line for line in lines if line.startswith("turn:"))
    assert _millis(turn, "speak") is None
    assert _millis(turn, "open") is not None
    assert "hops=1 calls=1 awaited=0 speechless=yes" in turn


async def test_a_turn_the_model_reported_no_counts_for_still_reports_its_time() -> None:
    """A count we do not have is not a zero. Logging ``prompt=0`` for a turn whose
    usage the API simply did not report would put a made-up number in the one place
    we go to read real ones — so the counts clause is dropped, not filled in.

    The times are ours and always known, and a turn the API declined to account for
    is not one to go quiet about: it may be exactly the pathological one."""
    lines: list[str] = []
    sink = logger.add(lines.append, level="INFO", format="{message}")
    try:
        brain, session = await _brain(_text("Hi."))
        await _drain(brain, session)
    finally:
        logger.remove(sink)
    turn = next(line for line in lines if line.startswith("turn:"))
    assert "no usage reported" in turn
    assert "prompt=" not in turn and "cached=" not in turn
    assert _millis(turn, "speak") is not None
    assert "Hi" not in turn, "speech reached the log"


# ─── The mark ─────────────────────────────────────────────────────────────────


def test_the_mark_is_an_attribute_and_nothing_else() -> None:
    """It changes neither what the tool returns nor how it is called, so it
    stacks with anything and reads the same through a bound method."""

    async def free() -> str:
        return "x"

    assert needs_result_now(free) is free
    brain = _Coach(_ScriptedClient([]))
    assert getattr(brain.lookup, "__voqalize_needs_result_now__", False) is True
    assert not hasattr(brain.ping, "__voqalize_needs_result_now__")


def test_the_declared_tool_carries_the_mark() -> None:
    """The loop asks the wrapper, never the model, so a model cannot make a tool
    wait — and a free function in the list is marked the same way."""
    from voqalize.sdk.gemini import (
        _needs_result_now,  # pyright: ignore[reportPrivateUsage]
    )

    @needs_result_now
    async def balance() -> int:
        """A free function tool."""
        return 1

    class _Free(_Coach):
        @property
        def tools(self) -> list[Any]:
            return [self.ping, self.lookup, balance]

    marked = {fn.__name__: _needs_result_now(fn) for fn in _declared(_Free(_ScriptedClient([])))}
    assert marked == {"ping": False, "lookup": True, "balance": True}


def test_automatic_function_calling_is_off() -> None:
    """If it were on, google-genai would run the tools too, and every call would
    run twice."""
    config = _Coach(_ScriptedClient([]))._turn_config()  # pyright: ignore[reportPrivateUsage]
    assert config.automatic_function_calling is not None
    assert config.automatic_function_calling.disable is True
