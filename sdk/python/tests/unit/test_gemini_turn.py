"""`GeminiBrain` turns one AFC stream into speech units, and takes AFC's record.

google-genai runs the tools and loops for us, so a turn that calls a tool and
then speaks about the result arrives as *one* stream spanning every hop. Two
rules cut it into units, and both are tested here:

  * a unit closes on ``finish_reason``, which lands on the last chunk of a hop;
  * a unit opens on the first spoken text after a close — lazily, so a hop that
    only calls a tool opens none at all.

The context is written from both sides of that seam. The **order** comes from
the stream, where the parts arrive as the model produced them; the tool
**responses** come from ``automatic_function_calling_history``, which is the only
place they exist — google-genai feeds them to the model and never to us.

The stand-in below is faithful to both. It runs each tool the moment it yields
the chunk carrying the call, and it keeps the record the same way the live API
does: opening as the contents it was handed, growing only once a hop is over, so
a hop's responses are first visible on the next hop's first chunk.

`tests/contract/test_brain_contract.py` states the engine-agnostic clauses this
brain has to satisfy (a turn ends, every call is answered, `tools` is read once,
...) once, against every engine. This file is what needs the real AFC stand-in
to exercise: the streaming/unit-boundary rules above, and other behavior AFC
itself is responsible for.
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
from voqalize.sdk.events import Finalize, Speech, SpeechChunk, SpeechEnd, SpeechStart, UserMessage
from voqalize.sdk.gemini import GeminiBrain, speaks
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


async def _drain(brain: GeminiBrain, session: Session) -> list[Speech]:
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


def _history(brain: GeminiBrain) -> list[str]:
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


async def test_a_call_whose_response_never_came_back_leaves_the_context() -> None:
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
        if isinstance(ev, SpeechChunk):
            break
    await gen.aclose()

    assert _shape(seen) == ["[", "One "]
    # The tool ran and was answered before the cut, so both stay in the context.
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


async def test_a_turn_reports_what_it_cost_and_never_what_was_said() -> None:
    """The only direct measure of context growth, and the one we did not have.

    A 123-second production call was found to be re-sending twenty-one full cart
    snapshots — ~4,700 tokens of them — and the only way to know that was to
    reconstruct the context from a transcript afterwards. One INFO line per turn
    makes it a number instead. ``hops`` is on it because under automatic function
    calling a turn is several requests and ``prompt`` is only the last, largest
    one; the two together say whether a turn is wide or merely long.

    The line carries counts and nothing else — speech is never a log field."""
    lines: list[str] = []
    sink = logger.add(lines.append, level="INFO", format="{message}")
    try:
        script = [*_calls("ping"), *_text("Pong.")]
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

    ``open`` is separate from ``speak`` on purpose. A turn that calls a tool first
    starts streaming at once and still says nothing for another hop."""
    lines: list[str] = []
    sink = logger.add(lines.append, level="INFO", format="{message}")
    try:
        brain, session = await _brain([*_calls("ping"), *_text("Pong.")])
        await _drain(brain, session)
    finally:
        logger.remove(sink)

    turn = next(line for line in lines if line.startswith("turn:"))
    open_ms, speak_ms, total_ms = (_millis(turn, f) for f in ("open", "speak", "total"))
    assert open_ms is not None and speak_ms is not None and total_ms is not None
    assert 0 <= open_ms <= speak_ms <= total_ms


async def test_a_turn_that_never_spoke_reports_no_time_to_speech() -> None:
    """A moment that never came is not a zero either. A tool-only hop, or a turn a
    barge-in cut before the first word, has no time-to-speech to report."""
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


# ─── Speaking from the call ───────────────────────────────────────────────────


class _Aide(GeminiBrain):
    """A brain whose slow tool says what it is doing, and whose quiet one does
    not."""

    def __init__(self, client: Any) -> None:
        super().__init__(client=client, system_instruction="be brief")

    @property
    def tools(self) -> list[Any]:
        return [self.look_up, self.log_it]

    @speaks("Checking")
    async def look_up(self) -> str:
        """Go and find out."""
        return "found"

    async def log_it(self) -> str:
        """Write it down where the caller cannot see."""
        return "noted"


async def _aide(script: list[types.GenerateContentResponse]) -> tuple[_Aide, Session]:
    brain, _, session = await _open(_Aide(_ScriptedClient(script)))
    return brain, session


async def test_a_declared_tool_speaks_the_moment_it_is_called() -> None:
    """The whole point: the call's name arrives on the first hop and the model's
    first word does not arrive until its last, so the acknowledgement is spoken
    a round trip — measured at ~2.2 s — before there is anything to say."""
    brain, session = await _aide(_calls("look_up") + _text("Two are left."))

    assert _shape(await _drain(brain, session)) == [
        "[",
        "Checking",
        "]",
        "[",
        "Two are left.",
        "]",
    ]


async def test_an_undeclared_tool_stays_silent() -> None:
    """Opt-in, because a tool the caller should not hear about is a real case."""
    brain, session = await _aide(_calls("log_it") + _text("Done."))

    assert _shape(await _drain(brain, session)) == ["[", "Done.", "]"]


async def test_the_acknowledgement_is_spoken_once_a_turn() -> None:
    """Two tool hops are not two announcements. The wait is one wait, and
    "Checking… checking…" is a stutter, not information."""
    script = _calls("look_up") + _calls("look_up") + _text("Both are in.")
    brain, session = await _aide(script)

    assert _shape(await _drain(brain, session)).count("Checking") == 1


async def test_a_turn_that_already_spoke_does_not_go_back_and_acknowledge() -> None:
    """The acknowledgement buys the *first* word of a turn. Once the caller is
    being spoken to, it buys nothing and only interrupts."""
    script = _text("Let me see.", done=True) + _calls("look_up") + _text("Two are left.")
    brain, session = await _aide(script)

    assert "Checking" not in _shape(await _drain(brain, session))


async def test_the_acknowledgement_is_in_the_context_on_the_unit_that_called() -> None:
    """Speech the model did not write is speech the model does not know about —
    and a model that does not know it already said "Checking" says it again. It
    goes on the calling unit rather than a unit of its own, because a model turn
    inserted between a ``function_call`` and its ``function_response`` is not a
    conversation Gemini takes back."""
    brain, session = await _aide(_calls("look_up") + _text("Two are left."))
    await _drain(brain, session)

    assert _history(brain)[1:] == [
        "model: call:look_up|Checking",
        "user: resp:look_up",
        "model: Two are left.",
    ]


async def test_the_acknowledgement_awaits_its_own_finalize() -> None:
    """It is real speech, so Voqalize reports it like any other unit — and
    ``on_finalize`` pops one unit per report. A unit spoken but not enqueued
    would hand the acknowledgement's report to the *answer*, and rewrite the
    answer down to "Checking"."""
    brain, session = await _aide(_calls("look_up") + _text("Two are left."))
    await _drain(brain, session)

    await brain.on_finalize(session, Finalize(speech_id=1, heard="Check", generated="Checking"))
    await brain.on_finalize(
        session, Finalize(speech_id=2, heard="Two are left.", generated="Two are left.")
    )

    assert _history(brain)[1:] == [
        "model: call:look_up|Check",
        "user: resp:look_up",
        "model: Two are left.",
    ]


def test_the_mark_never_reaches_the_model() -> None:
    """It is ours, not a field of the declaration: the schema google-genai builds
    is the name, the docstring and the parameter, and an extra attribute on the
    closure changes none of them."""
    brain = _Aide(_ScriptedClient([]))

    assert brain._acks(brain.tools) == {"look_up": "Checking"}  # pyright: ignore[reportPrivateUsage]

    declared = list(brain._turn_config().tools or [])  # pyright: ignore[reportPrivateUsage]
    schema = types.GenerateContentConfig(tools=declared)
    assert "Checking" not in str(schema.tools)
