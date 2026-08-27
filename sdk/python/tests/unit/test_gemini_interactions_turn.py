"""`GeminiInteractionsBrain` runs its own tool loop, one interaction per hop.

There is no automatic function calling on this API, so everything the automatic
path hides is on show here: the loop, the coercion, the result written back. What
the API gives in exchange is a turn told in *steps* — bracketed by ``step.start``
and ``step.stop``, with a call and its result linked by id rather than position.

The stand-in below is faithful to the stream, which is the only way a fake here is
a gate rather than a decoration:

  * ``step.start`` carries the step's **skeleton** — a function call arrives with
    its ``id`` and ``name`` and no arguments at all;
  * the arguments follow as ``arguments_delta`` fragments of a JSON *string*,
    split mid-token, exactly as the wire splits them;
  * ``interaction.completed`` carries **no** steps, because a streamed one never
    does;
  * and it runs no tools, because on this API nobody does that but us.

`tests/contract/test_brain_contract.py` states the engine-agnostic clauses this
brain has to satisfy (a turn ends, every call is answered, `tools` is read once,
...) once, against every engine. This file is what needs the real interactions
stand-in to exercise: the loop this engine drives itself, argument assembly from
deltas, and other behavior the Interactions API is responsible for.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

import pytest
from google.genai import interactions as gi
from pydantic import BaseModel, Field

from voqalize.sdk import Session
from voqalize.sdk.actions import Action
from voqalize.sdk.brain import _adapter_for
from voqalize.sdk.events import Chunk, Speech, SpeechEnd, SpeechStart, UserMessage
from voqalize.sdk.gemini_interactions import GeminiInteractionsBrain
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


@dataclass
class _Scripted:
    """One step as the stream delivers it: a skeleton, then its deltas."""

    step: gi.Step
    deltas: list[Any] = field(default_factory=list)


def _says(*chunks: str) -> _Scripted:
    """A `model_output` step — the only kind that is speech."""
    return _Scripted(gi.ModelOutputStep(), [gi.TextDelta(text=c) for c in chunks])


def _thinks(signature: str = "c2ln") -> _Scripted:
    """A `thought` step. Its signature arrives as a delta and nowhere else."""
    return _Scripted(gi.ThoughtStep(), [gi.ThoughtSignatureDelta(signature=signature)])


def _calls(name: str, **arguments: Any) -> _Scripted:
    """A `function_call` step, with its arguments split across two deltas.

    The skeleton really is argument-less on the wire, and the JSON really is
    fragmented mid-token — a fake that delivered them whole would let a brain
    that read `step.start.arguments` pass.
    """
    payload = json.dumps(arguments)
    cut = len(payload) // 2
    return _Scripted(
        gi.FunctionCallStep(id=f"call_{name}", name=name, arguments={}),
        [
            gi.ArgumentsDelta(arguments=payload[:cut]),
            gi.ArgumentsDelta(arguments=payload[cut:]),
        ],
    )


async def _events(hop: list[_Scripted]) -> AsyncIterator[gi.InteractionSSEEvent]:
    resource = gi.InteractionSseEventInteraction(id="int_1", status="completed")
    yield gi.InteractionCreatedEvent(interaction=resource)
    for index, scripted in enumerate(hop):
        yield gi.StepStart(index=index, step=scripted.step)
        for delta in scripted.deltas:
            yield gi.StepDelta(index=index, delta=delta)
        yield gi.StepStop(index=index)
    # No steps on it: a streamed lifecycle payload omits what only a
    # non-streaming Interaction carries.
    yield gi.InteractionCompletedEvent(interaction=resource)


class _ScriptedInteractions:
    """Stands in for ``client.aio.interactions``. It replays hops and keeps every
    request, because what went over is half of what these tests are about."""

    def __init__(self, hops: list[list[_Scripted]]) -> None:
        self._hops = list(hops)
        self.requests: list[dict[str, Any]] = []

    async def create(self, **request: Any) -> AsyncIterator[gi.InteractionSSEEvent]:
        self.requests.append(request)
        return _events(self._hops.pop(0) if self._hops else [])

    @property
    def inputs(self) -> list[list[gi.Step]]:
        """What each hop was handed, as steps."""
        return [list(r["input"]) for r in self.requests]


class _ScriptedClient:
    def __init__(self, hops: list[list[_Scripted]]) -> None:
        self.aio = self
        self.interactions = _ScriptedInteractions(hops)


# ─── A brain with three tools ─────────────────────────────────────────────────


class _Show(Action):
    """Put a section of the screen in front of the caller."""

    name: str


class _Section(BaseModel):
    """Which part of the screen to show."""

    name: Literal["glucose", "meals"] = Field(description="Section to show.")


class _Coach(GeminiInteractionsBrain):
    def __init__(self, client: Any, **kwargs: Any) -> None:
        super().__init__(client=client, system_instruction="be brief", **kwargs)
        self.ran: list[str] = []
        self.seen: tuple[Session | None, int | None] = (None, None)

    @property
    def tools(self) -> list[Any]:
        return [self.show, self.ping, self.boom]

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


async def _brain(*hops: list[_Scripted]) -> tuple[_Coach, Session]:
    brain, _, session = await _open(_Coach(_ScriptedClient(list(hops))))
    return brain, session


async def _open[B: GeminiInteractionsBrain](brain: B) -> tuple[B, _Wire, Session]:
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
        elif isinstance(ev, Chunk):
            out.append(ev.text)
    return out


def _history(brain: GeminiInteractionsBrain) -> list[str]:
    """History as ``kind: what-is-in-it``, enough to read the shape at a glance."""
    return [_one(step) for step in brain._history]


def _one(step: gi.Step) -> str:
    if isinstance(step, gi.UserInputStep | gi.ModelOutputStep):
        kind = "user" if isinstance(step, gi.UserInputStep) else "model"
        said = "".join(c.text for c in (step.content or []) if isinstance(c, gi.TextContent))
        return f"{kind}: {said}"
    if isinstance(step, gi.FunctionCallStep):
        return f"call: {step.name}{json.dumps(step.arguments, sort_keys=True)}"
    if isinstance(step, gi.FunctionResultStep):
        return f"result: {step.name} -> {step.result}"
    if isinstance(step, gi.ThoughtStep):
        return f"thought: {step.signature}"
    return type(step).__name__


# ─── Units of speech ──────────────────────────────────────────────────────────


async def test_a_thought_is_not_spoken_and_keeps_its_signature() -> None:
    """A thought is reasoning, not speech. It belongs in the context — Gemini 3
    wants its own thought handed back, signed — and the signature exists nowhere
    but the delta that carries it."""
    brain, session = await _brain([_thinks("c2lnbmVk"), _says("Good evening.")])

    assert _shape(await _drain(brain, session)) == ["[", "Good evening.", "]"]
    assert _history(brain)[1] == "thought: c2lnbmVk"


async def test_a_stream_that_ends_without_closing_the_step_still_closes_the_unit() -> None:
    """A `SpeechStart` with no `SpeechEnd` is a wire violation, so the end of the
    stream closes the unit whether or not `step.stop` ever arrived."""

    async def truncated(**_: Any) -> AsyncIterator[gi.InteractionSSEEvent]:
        async def gen() -> AsyncIterator[gi.InteractionSSEEvent]:
            yield gi.StepStart(index=0, step=gi.ModelOutputStep())
            yield gi.StepDelta(index=0, delta=gi.TextDelta(text="Cut short"))

        return gen()

    brain, session = await _brain([])
    brain._client.interactions.create = truncated  # pyright: ignore[reportPrivateUsage]

    assert _shape(await _drain(brain, session)) == ["[", "Cut short", "]"]


# ─── The tool loop ────────────────────────────────────────────────────────────


async def test_the_arguments_are_assembled_from_the_deltas() -> None:
    """`step.start` carries no arguments at all; they arrive afterwards as
    fragments of a JSON string, split wherever the wire felt like it."""
    brain, session = await _brain(
        [_calls("show", args={"name": "glucose"})],
        [_says("There.")],
    )

    await _drain(brain, session)

    assert brain.ran == ["show:glucose"]
    assert _history(brain)[1] == 'call: show{"args": {"name": "glucose"}}'


async def test_a_result_answers_its_call_by_id() -> None:
    """The pair is named, not counted. Position-matching is what quietly corrupts
    a context when a turn is cut between a call and its answer."""
    brain, session = await _brain([_calls("ping")], [_says("All set.")])

    await _drain(brain, session)

    call = next(s for s in brain._history if isinstance(s, gi.FunctionCallStep))
    result = next(s for s in brain._history if isinstance(s, gi.FunctionResultStep))
    assert result.call_id == call.id
    assert result.is_error is None, "unset, as the API leaves it — the flag is for failures"
    assert _history(brain) == [
        "user: hello",
        "call: ping{}",
        'result: ping -> {"result": "pong"}',
        "model: All set.",
    ]


async def test_a_tool_that_raises_is_answered_and_marked_as_an_error() -> None:
    """The model is told, because a call with no answer is not a conversation it
    will accept. We are told too — `is_error` is the half the automatic path has
    no room for, where a failure arrives as an ordinary payload the model
    narrates as success."""
    brain, session = await _brain([_calls("boom")], [_says("Sorry.")])

    await _drain(brain, session)

    result = next(s for s in brain._history if isinstance(s, gi.FunctionResultStep))
    assert result.is_error is True
    assert json.loads(str(result.result)) == {"error": "kaboom"}


async def test_a_tool_the_brain_does_not_have_is_answered_not_dropped() -> None:
    """A model that invents a tool still has to be answered, or the next turn
    carries a call with nothing beside it."""
    brain, session = await _brain([_calls("teleport")], [_says("Sorry.")])

    await _drain(brain, session)

    result = next(s for s in brain._history if isinstance(s, gi.FunctionResultStep))
    assert result.is_error is True
    assert "teleport" in str(result.result)
    assert brain.ran == []


async def test_the_budget_ends_the_turn_in_speech() -> None:
    """A model that never stops calling would otherwise leave the caller in
    silence. On the last hop the declarations stay — so the context still
    reads — and `tool_choice` says answer."""
    brain, _, session = await _open(
        _Coach(
            _ScriptedClient([[_calls("ping")], [_calls("ping")], [_says("Fine, done.")]]),
            max_tool_hops=2,
        )
    )

    assert _shape(await _drain(brain, session)) == ["[", "Fine, done.", "]"]

    requests = brain._client.interactions.requests  # pyright: ignore[reportPrivateUsage]
    assert len(requests) == 3
    assert [r["generation_config"].tool_choice for r in requests] == [None, None, "none"]
    assert all(r["tools"] for r in requests), "the declarations never left"


# ─── Interruption ─────────────────────────────────────────────────────────────


async def test_a_call_whose_result_never_came_back_leaves_the_context() -> None:
    """A barge-in lands wherever it lands, and may cut between a call and the
    result we were about to write. Gemini will not accept a `function_call` with
    nothing answering it, so it goes. Whether the tool ran is not ours to know:
    the context records what completed, and the side effect stands."""
    brain, session = await _brain([_says("Hi."), _calls("ping")])

    gen = brain.on_user_message(session, UserMessage(text="hello"))
    seen = [ev async for ev in _until_speech_end(gen)]
    await gen.aclose()

    assert _shape(seen) == ["[", "Hi.", "]"]
    assert _history(brain) == ["user: hello", "model: Hi."]


async def _until_speech_end(gen: Any) -> AsyncIterator[Speech]:
    async for ev in gen:
        yield ev
        if isinstance(ev, SpeechEnd):
            return


async def test_a_barge_in_mid_turn_closes_the_generator_cleanly() -> None:
    """A cancelled turn closes this generator by throwing `GeneratorExit` at the
    yield. An async generator that yields while closing raises instead of tearing
    down — so the trailing `SpeechEnd` must never be in a `finally`."""
    brain, session = await _brain([_calls("ping")], [_says("One ", "two ", "three")])

    gen = brain.on_user_message(session, UserMessage(text="hello"))
    seen = []
    async for ev in gen:
        seen.append(ev)
        if isinstance(ev, Chunk):
            break
    await gen.aclose()

    assert _shape(seen) == ["[", "One "]
    # The tool ran and was answered before the cut, so both stay.
    assert _history(brain)[:3] == [
        "user: hello",
        "call: ping{}",
        'result: ping -> {"result": "pong"}',
    ]


# ─── What goes over ───────────────────────────────────────────────────────────


async def test_every_hop_carries_the_whole_context_and_stores_nothing() -> None:
    """Stateless by construction: no `previous_interaction_id`, `store=False`, and
    the conversation lives in `history`. Server-side state cannot be told that the
    caller only heard half of a sentence, which is the one thing this SDK's
    context is for."""
    brain, session = await _brain([_calls("ping")], [_says("All set.")])

    await _drain(brain, session)

    requests = brain._client.interactions.requests  # pyright: ignore[reportPrivateUsage]
    assert [r["store"] for r in requests] == [False, False]
    assert not any("previous_interaction_id" in r for r in requests)
    inputs = brain._client.interactions.inputs  # pyright: ignore[reportPrivateUsage]
    assert [len(hop) for hop in inputs] == [1, 3], "user; then user + call + result"


def _user(text: str) -> gi.UserInputStep:
    return gi.UserInputStep(content=[gi.TextContent(text=text)])


async def test_append_to_context_lands_where_it_was_called() -> None:
    """Appended once, in place, in front of what the caller says next — and as the
    caller's own kind of step, not as a tool result, which on this API is a
    different kind and never wears the caller's."""
    brain, _, session = await _open(_Coach(_ScriptedClient([[_calls("ping")], [_says("Sure.")]])))
    brain.append_to_context(_user("on the meals tab"))

    await _drain(brain, session)

    inputs = brain._client.interactions.inputs  # pyright: ignore[reportPrivateUsage]
    assert [_one(step) for step in inputs[1]] == [
        "user: on the meals tab",
        "user: hello",
        "call: ping{}",
        'result: ping -> {"result": "pong"}',
    ]


async def test_appending_mid_turn_lands_in_the_turn_that_is_running() -> None:
    """Immediately means immediately, including from inside a tool.

    `grounding()` was re-read on every hop, so hop two silently re-argued from a
    screen hop one had never seen. This is the opposite: one append, at the point
    it was made, and every hop from there on carries it. Hop one is untouched —
    which is what makes each request an extension of the last rather than a
    re-rendering of it.

    Where "the point it was made" falls is this engine's own business, and here it
    is between a function call and its result — this loop writes the result after
    the tool returns, and the tool appended first. The API takes that: it validates
    no pairing at all, beyond refusing a request whose *last* step is an unanswered
    call. `GeminiBrain` puts the same append ahead of the call instead, because AFC
    runs the tool before it hands over the chunk that records it. Both are
    append-only, both extend the last request, and neither is a position a brain
    should be written to depend on.
    """

    class _Moving(_Coach):
        async def ping(self) -> str:
            """Move the screen from under the turn, as a caller's thumb does."""
            self.append_to_context(_user("now on the meals tab"))
            return "pong"

    brain, _, session = await _open(
        _Moving(_ScriptedClient([[_calls("ping")], [_says("Sure.")], [_says("Right.")]]))
    )
    brain.append_to_context(_user("on the glucose tab"))

    await _drain(brain, session)
    inputs = brain._client.interactions.inputs  # pyright: ignore[reportPrivateUsage]
    assert [_one(step) for step in inputs[0]] == [
        "user: on the glucose tab",
        "user: hello",
    ]
    assert [_one(step) for step in inputs[1]] == [
        "user: on the glucose tab",
        "user: hello",
        "call: ping{}",
        "user: now on the meals tab",
        'result: ping -> {"result": "pong"}',
    ]

    # And the next turn extends that — the wedged append stays exactly where it
    # landed rather than being re-rendered somewhere tidier.
    await _drain(brain, session)
    inputs = brain._client.interactions.inputs  # pyright: ignore[reportPrivateUsage]
    was = [_one(step) for step in inputs[1]]
    now = [_one(step) for step in inputs[2]]
    assert now[: len(was)] == was
    assert now[len(was) :] == ["model: Sure.", "user: hello"]


async def test_append_to_context_rejects_the_steps_it_does_not_own() -> None:
    """Every kind of step but the caller's is either the model's to write or this
    class's to write back. A brain that appends a model output is telling the model
    it already said something it never did."""
    brain, _, _ = await _open(_Coach(_ScriptedClient([[_says("Sure.")]])))
    with pytest.raises(ValueError, match="UserInputStep"):
        brain.append_to_context(  # pyright: ignore[reportArgumentType]
            gi.ModelOutputStep(content=[gi.TextContent(text="of course, doctor")])
        )
    assert brain._history == []  # pyright: ignore[reportPrivateUsage]


# ─── Declarations ─────────────────────────────────────────────────────────────


def _declared(brain: GeminiInteractionsBrain) -> dict[str, gi.Function]:
    from voqalize.sdk.gemini_interactions import _declare

    return {fn.__name__: _declare(fn) for fn in brain.tools}


async def test_the_method_is_the_declaration() -> None:
    """One pydantic model, one docstring, no second copy — and the same list
    `GeminiBrain` takes, so a brain moves between the two classes untouched."""
    declared = _declared(_Coach(_ScriptedClient([])))

    assert set(declared) == {"show", "ping", "boom"}
    assert declared["show"].description == "Put a section of the screen in front of the caller."
    schema = declared["show"].parameters
    assert schema["properties"]["args"]["properties"]["name"] == {
        "description": "Section to show.",
        "enum": ["glucose", "meals"],
        "title": "Name",
        "type": "string",
    }
    assert declared["ping"].parameters is None


async def test_nothing_callable_is_declared() -> None:
    """The declaration is data. Nothing about the brain crosses to google-genai,
    which is why this class needs none of the care the automatic path does about
    what a deep copy of a config would take with it."""
    for function in _declared(_Coach(_ScriptedClient([]))).values():
        assert isinstance(function, gi.Function)
        assert json.loads(function.model_dump_json())["type"] == "function"


# ─── The session ──────────────────────────────────────────────────────────────


async def test_a_tool_that_drives_the_screen_is_stamped_with_the_turn_it_ran_in() -> None:
    """It runs inside the turn task, so `dispatch` is correlated to the turn the
    model is answering with nothing plumbed through — and the screen changes
    before the sentence about it starts."""

    class _Screen(_Coach):
        async def show(self, args: _Section) -> str:
            """Put a section of the screen in front of the caller."""
            self.session.dispatch(_Show(name=args.name))
            return "shown"

    brain, wire, _ = await _open(
        _Screen(_ScriptedClient([[_calls("show", args={"name": "glucose"})], [_says("There.")]]))
    )
    await _turn(brain)

    commands = [f for f in wire.frames if isinstance(f, RTVIFrame)]
    assert [(f.data or {}).get("payload") for f in commands] == [{"name": "glucose"}]
    assert [f.turn_id for f in commands] == [2]
    assert wire.frames.index(commands[0]) < next(
        i for i, f in enumerate(wire.frames) if isinstance(f, SpeechStartFrame)
    )
