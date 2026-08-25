"""`GeminiBrain` turns one AFC stream into speech units, and takes AFC's record.

google-genai runs the tools and loops for us, so a turn that calls a tool and
then speaks about the result arrives as *one* stream spanning every hop. Two
rules cut it into units, and both are tested here:

  * a unit closes on ``finish_reason``, which lands on the last chunk of a hop;
  * a unit opens on the first spoken text after a close — lazily, so a hop that
    only calls a tool opens none at all.

The transcript is written from both sides of that seam. The **order** comes from
the stream, where the parts arrive as the model produced them; the tool
**responses** come from ``automatic_function_calling_history``, which is the only
place they exist — google-genai feeds them to the model and never to us.

The stand-in below is faithful to both. It runs each tool the moment it yields
the chunk carrying the call, and it keeps the record the same way the live API
does: opening as the contents it was handed, growing only once a hop is over, so
a hop's responses are first visible on the next hop's first chunk.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Literal

import pytest
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from voqalize.sdk import Session
from voqalize.sdk.actions import Action
from voqalize.sdk.brain import adapter_for
from voqalize.sdk.events import Chunk, Speech, SpeechEnd, SpeechStart, UserMessage
from voqalize.sdk.gemini import GeminiBrain
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


class _ScriptedModels:
    """Stands in for ``client.aio.models``, including AFC's tool execution and the
    record it keeps of it."""

    def __init__(self, script: list[types.GenerateContentResponse]) -> None:
        self._script = script
        self.contents: list[types.Content] = []

    async def generate_content_stream(self, *, model: str, contents: Any, config: Any) -> Any:
        self.contents = list(contents)
        # google-genai deep-copies the config, so this does too: it is the step
        # that would clone a brain handed over as a bound method.
        config = config.model_copy(deep=True)
        tools = {fn.__name__: fn for fn in (config.tools or [])}

        async def gen() -> Any:
            record = list(self.contents)
            # What this hop's chunks carry: the record as it stood before it.
            seen = list(record)
            hop: list[list[types.Part]] = []
            responses: list[types.Part] = []
            for chunk in self._script:
                parts = [
                    p
                    for c in chunk.candidates or []
                    for p in ((c.content.parts or []) if c.content else [])
                ]
                hop.append(parts)
                for part in parts:
                    if not (part.function_call and part.function_call.name):
                        continue
                    # AFC runs the tool before it yields the chunk, and builds the
                    # declared pydantic model out of the JSON on the way in.
                    name = part.function_call.name
                    fn = tools[name]
                    try:
                        result = await fn(**_coerce(fn, part.function_call.args or {}))
                    except Exception as exc:  # what google-genai does with a raising tool
                        response: dict[str, Any] = {"error": str(exc)}
                    else:
                        response = {"result": result}
                    responses.append(
                        types.Part.from_function_response(name=name, response=response)
                    )
                yield chunk.model_copy(update={"automatic_function_calling_history": list(seen)})
                if any(c.finish_reason for c in chunk.candidates or []):
                    if responses:
                        record.extend(types.Content(role="model", parts=p) for p in hop)
                        record.append(types.Content(role="user", parts=responses))
                        seen = list(record)
                    hop, responses = [], []

        return gen()


def _coerce(fn: Any, args: dict[str, Any]) -> dict[str, Any]:
    """Read off `inspect.signature`, which is where AFC reads it."""
    params = inspect.signature(fn).parameters
    return {
        k: params[k].annotation(**v)
        if k in params and isinstance(v, dict) and issubclass(params[k].annotation, BaseModel)
        else v
        for k, v in args.items()
    }


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


async def _brain(script: list[types.GenerateContentResponse]) -> tuple[_Coach, Session]:
    brain, _, session = await _open(_Coach(_ScriptedClient(script)))
    return brain, session


async def _open[B: GeminiBrain](brain: B) -> tuple[B, _Wire, Session]:
    wire = _Wire()
    adapter = adapter_for(brain, wire)
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


async def test_a_plain_turn_is_one_unit() -> None:
    brain, session = await _brain(_text("Good ", "evening."))

    assert _shape(await _drain(brain, session)) == ["[", "Good ", "evening.", "]"]


async def test_a_silent_tool_hop_opens_no_unit() -> None:
    """The whole reason for opening lazily. Under a per-hop unit this turn emits
    an empty `SpeechStart`/`SpeechEnd` pair around the tool call, and the runtime
    mints a speech unit for a hop that never made a sound."""
    brain, session = await _brain(_calls("ping") + _text("Done."))

    assert _shape(await _drain(brain, session)) == ["[", "Done.", "]"]
    assert brain.ran == ["ping"]
    assert len(brain._awaiting) == 1  # pyright: ignore[reportPrivateUsage]


async def test_speech_either_side_of_a_tool_is_two_units() -> None:
    """`finish_reason` is the only boundary between hops, and there is one per
    hop — so a turn that narrates, calls a tool, then reports back is two units
    of speech under one turn id."""
    script = _text("Let me look.") + _calls("ping") + _text("All set.")
    brain, session = await _brain(script)

    assert _shape(await _drain(brain, session)) == [
        "[",
        "Let me look.",
        "]",
        "[",
        "All set.",
        "]",
    ]
    assert len(brain._awaiting) == 2  # pyright: ignore[reportPrivateUsage]


async def test_a_thought_is_not_spoken() -> None:
    """Thought parts carry text that is reasoning, not speech. They belong in the
    transcript — Gemini 3 wants them handed back — and never on the wire."""
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


# ─── History ──────────────────────────────────────────────────────────────────


async def test_tool_responses_land_in_history_in_hop_order() -> None:
    """The order is the stream's and the payload is AFC's. Its record grows
    between hops, so a hop's responses arrive on the first chunk of the next one —
    which is where they belong, after the call and before the answer. File them
    anywhere else and the model reads a response before the call it answers."""
    script = _calls("ping") + _text("All set.")
    brain, session = await _brain(script)

    await _drain(brain, session)

    assert _history(brain) == [
        "user: hello",
        "model: call:ping",
        "user: resp:ping",
        "model: All set.",
    ]


async def test_a_tool_that_raises_reaches_the_model_as_an_error() -> None:
    """google-genai turns any exception into `{'error': str(e)}` and hands it to
    the model, which will otherwise tell the caller it did the thing. We do not
    interpose to catch it — we read it out of the record, which is how it becomes
    visible on our side too."""
    brain, session = await _brain(_calls("boom") + _text("Sorry."))

    await _drain(brain, session)

    responses = [
        p.function_response for c in brain._history for p in (c.parts or []) if p.function_response
    ]
    assert [r.response for r in responses if r] == [{"error": "kaboom"}]


async def test_a_call_whose_response_never_came_back_leaves_the_transcript() -> None:
    """A hop's responses only reach us on the chunk after it, so a call at the end
    of the stream — a barge-in, or the hop budget running out — may have none and
    never will. Gemini will not accept a `function_call` with no
    `function_response` beside it on the next turn, so it goes."""
    brain, session = await _brain(_text("Hi.") + _calls("ping"))

    await _drain(brain, session)

    assert brain.ran == ["ping"], "the tool still ran; the side effect stands"
    assert _history(brain) == ["user: hello", "model: Hi."]


async def test_a_barge_in_mid_turn_closes_the_generator_cleanly() -> None:
    """A cancelled turn closes this generator by throwing `GeneratorExit` at the
    yield. An async generator that yields while closing raises instead of tearing
    down — so the trailing `SpeechEnd` must never be in a `finally`."""
    script = _calls("ping") + _text("One ", "two ", "three")
    brain, session = await _brain(script)

    gen = brain.on_user_message(session, UserMessage(text="hello"))
    seen = []
    async for ev in gen:
        seen.append(ev)
        if isinstance(ev, Chunk):
            break
    await gen.aclose()

    assert _shape(seen) == ["[", "One "]
    # The tool ran and was answered before the cut, so both stay in the transcript.
    assert _history(brain)[:3] == ["user: hello", "model: call:ping", "user: resp:ping"]


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

    Where "the point it was made" falls is this engine's, and it is not where a
    reader expects: AFC runs the tool before it hands us the chunk that records
    the call, so the append lands *ahead* of the call it came out of.
    `GeminiInteractionsBrain` drives its own loop and puts it behind. Both are
    append-only, both extend the last request, and neither is something a brain
    should be written to depend on.
    """

    class _Moving(_Coach):
        async def ping(self) -> str:
            """Move the screen from under the turn, as a caller's thumb does."""
            self.append_to_context(_user("now on the meals tab"))
            return "pong"

    brain, _, session = await _open(_Moving(_ScriptedClient([*_calls("ping"), *_text("Sure.")])))
    await _drain(brain, session)

    assert _history(brain) == [
        "user: hello",
        "user: now on the meals tab",
        "model: call:ping",
        "user: resp:ping",
        "model: Sure.",
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

    assert set(declared) == {"show", "ping", "boom"}
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


async def test_a_tool_is_callable_the_way_afc_calls_it() -> None:
    """The declaration being right does not mean the call is.

    AFC builds a tool's arguments from ``inspect.signature``, not from the schema
    it sent. Every brain module uses ``from __future__ import annotations``, so a
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
    """google-genai deep-copies the config it is given — on entry and again on
    every AFC hop — and ``copy.deepcopy`` of a bound method copies ``__self__``
    with it, by definition. A brain that crossed that line would have its tools
    called on a *clone*: ``self.session.dispatch`` reaching nothing, the
    transcript written to an object no one reads, the model told ``ok``, and not
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


async def test_a_sync_tool_is_refused() -> None:
    """AFC runs a synchronous tool on a worker thread, off the loop, where the
    first `await` the tool grows is a rewrite. Half-working is the failure mode we
    refuse."""

    class _Sync(_Coach):
        @property
        def tools(self) -> list[Any]:
            return [self.blocking]

        def blocking(self) -> str:
            """Not a coroutine."""
            return "ok"

    with pytest.raises(TypeError, match="must be `async def`"):
        _declared(_Sync(_ScriptedClient([])))


async def test_the_tools_are_read_once_per_turn() -> None:
    """The list is a property, not a decorator swept at construction — so a brain
    can offer a caller a tool it does not offer everyone, decided as late as the
    turn it is needed for."""

    class _Gated(_Coach):
        unlocked = False

        @property
        def tools(self) -> list[Any]:
            return [self.show, self.ping] if self.unlocked else [self.ping]

    brain = _Gated(_ScriptedClient([]))
    assert [fn.__name__ for fn in _declared(brain)] == ["ping"]

    brain.unlocked = True
    assert [fn.__name__ for fn in _declared(brain)] == ["show", "ping"]


async def test_tools_are_not_shared_between_brains() -> None:
    """The declarations are bound methods, so two sessions of the same brain drive
    two different screens."""
    a, _ = await _brain(_text("x"))
    b, _ = await _brain(_text("x"))

    await asyncio.gather(*(fn() for fn in _declared(a) if fn.__name__ == "ping"))

    assert a.ran == ["ping"]
    assert b.ran == []


async def test_a_tool_reaches_the_session() -> None:
    """A tool cannot take `session` as a parameter — the signature *is* the schema,
    so the model would try to fill it. It reads the brain instead, which is sound
    because a brain is one instance per call."""
    brain, _, session = await _open(_Coach(_ScriptedClient(_calls("ping") + _text("Done."))))
    await _turn(brain)

    assert brain.seen is session


async def test_a_tool_that_drives_the_screen_is_stamped_with_the_turn_it_ran_in() -> None:
    """The whole reason a tool needs `self.session`. It runs inside the turn task,
    so `dispatch` is correlated to the turn the model is answering with nothing
    plumbed through — and the screen changes before the sentence about it starts."""

    class _Screen(_Coach):
        async def show(self, args: _Section) -> str:
            """Put a section of the screen in front of the caller."""
            self.session.dispatch(_Show(name=args.name))
            return "shown"

    brain, wire, _ = await _open(_Screen(_ScriptedClient(_calls("show") + _text("There."))))
    await _turn(brain)

    commands = [f for f in wire.frames if isinstance(f, RTVIFrame)]
    assert [(f.data or {}).get("payload") for f in commands] == [{"name": "glucose"}]
    assert [f.turn_id for f in commands] == [2]
    # The screen moved before the coach opened her mouth about it.
    assert wire.frames.index(commands[0]) < next(
        i for i, f in enumerate(wire.frames) if isinstance(f, SpeechStartFrame)
    )
