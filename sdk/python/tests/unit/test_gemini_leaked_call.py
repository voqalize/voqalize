"""A function call the model writes out as text is never spoken, and the turn
recovers.

At MINIMAL thinking a Gemini model occasionally emits its call as words instead
of as a ``function_call`` part. On a live travel session the user asked for the
Dubai trip and heard ``certain_tool_call "name": "default_api:read_screen"`` read
aloud, and no tool ran. ``GeminiBrain.respond`` now holds a unit's opening only
while it could still be one, speaks none of a unit that is, and asks once more.

The other half matters as much: ordinary speech must not wait. The ordering tests
here interleave the model's chunks with what the brain yields, so a piece that
was held back for even one chunk shows as a reordering.
"""

from __future__ import annotations

from typing import Any

import pytest
from google.genai import types
from loguru import logger

from tests.unit.test_gemini_turn import (
    _calls,  # pyright: ignore[reportPrivateUsage]
    _chunk,  # pyright: ignore[reportPrivateUsage]
    _Coach,  # pyright: ignore[reportPrivateUsage]
    _history,  # pyright: ignore[reportPrivateUsage]
    _open,  # pyright: ignore[reportPrivateUsage]
    _ScriptedModels,  # pyright: ignore[reportPrivateUsage]
    _shape,  # pyright: ignore[reportPrivateUsage]
    _text,  # pyright: ignore[reportPrivateUsage]
)
from voqalize.sdk.events import Speech, SpeechChunk, SpeechEnd, UserMessage
from voqalize.sdk.gemini import (
    _RETRY_NOTE,  # pyright: ignore[reportPrivateUsage]
    _SPOKEN_CALL_HEADS,  # pyright: ignore[reportPrivateUsage]
    _looks_like_call,  # pyright: ignore[reportPrivateUsage]
    _Unit,  # pyright: ignore[reportPrivateUsage]
)

Script = list[types.GenerateContentResponse]

#: What the model wrote on the failing smoke run, as text, verbatim.
_LEAKED = 'certain_tool_call\n  "name": "default_api:read_screen",\n  "arguments": {}\n}'


class _Requests:
    """Stands in for ``client.aio.models`` across several requests: one script per
    request, each run by the same AFC stand-in the turn tests use. ``log`` gets a
    line each time the model hands over a chunk, so a test can interleave it with
    what the brain yields."""

    def __init__(self, *scripts: Script) -> None:
        self._scripts = list(scripts)
        self.requests: list[list[types.Content]] = []
        self.log: list[str] = []

    async def generate_content_stream(self, *, model: str, contents: Any, config: Any) -> Any:
        self.requests.append(list(contents))
        inner = _ScriptedModels(self._scripts.pop(0))
        stream = await inner.generate_content_stream(model=model, contents=contents, config=config)

        async def logged() -> Any:
            async for chunk in stream:
                self.log.append(f"model:{''.join(p.text or '' for p in _texts(chunk))}")
                yield chunk

        return logged()


def _texts(chunk: types.GenerateContentResponse) -> list[types.Part]:
    return [
        p
        for c in chunk.candidates or []
        for p in ((c.content.parts or []) if c.content else [])
        if p.text
    ]


class _Client:
    def __init__(self, *scripts: Script) -> None:
        self.aio = self
        self.models = _Requests(*scripts)


async def _run(*scripts: Script) -> tuple[_Coach, _Requests, list[Speech]]:
    client = _Client(*scripts)
    brain, _, session = await _open(_Coach(client))
    events: list[Speech] = []
    async for ev in brain.on_user_message(session, UserMessage(text="hello")):
        if isinstance(ev, SpeechChunk):
            client.models.log.append(f"spoke:{ev.text}")
        events.append(ev)
    return brain, client.models, events


def _malformed() -> types.GenerateContentResponse:
    """The last chunk of a hop whose function call did not parse."""
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=[]),
                finish_reason=types.FinishReason.MALFORMED_FUNCTION_CALL,
            )
        ]
    )


# ─── A call written as text ───────────────────────────────────────────────────


async def test_a_call_written_as_text_is_not_spoken_and_the_turn_asks_again() -> None:
    """The smoke-run failure, replayed. The leaked text never reaches the wire,
    the request goes once more, and the second answer runs the tool and speaks."""
    lines: list[str] = []
    sink = logger.add(lines.append, level="WARNING", format="{message}")
    try:
        brain, models, events = await _run(
            _text(*_LEAKED.split(" ")),
            _calls("ping") + _text("Opening it."),
        )
    finally:
        logger.remove(sink)

    assert _shape(events) == ["[", "Opening it.", "]"]
    assert brain.ran == ["ping"]
    assert len(models.requests) == 2
    assert models.requests[1][-1] is _RETRY_NOTE
    # The leaked unit left the context, and the note was never in it.
    assert _history(brain) == [
        "user: hello",
        "model: call:ping",
        "user: resp:ping",
        "model: Opening it.",
    ]
    assert any("function call as text" in line for line in lines)
    assert not any("read_screen" in line for line in lines), "model output reached the log"


async def test_a_malformed_function_call_asks_again() -> None:
    """``MALFORMED_FUNCTION_CALL`` ends the hop with nothing to run, so AFC ends the
    stream and the turn would be silent. It is the same failure without the text."""
    brain, models, events = await _run([_malformed()], _text("Here it is."))

    assert _shape(events) == ["[", "Here it is.", "]"]
    assert len(models.requests) == 2
    assert _history(brain) == ["user: hello", "model: Here it is."]


async def test_speech_before_a_malformed_call_stays_spoken_and_heard() -> None:
    """What went out was heard, so it stays in the context; the call after it did
    not run, so the turn asks again from there."""
    brain, models, events = await _run(
        [_chunk([types.Part(text="Sure, opening it.")]), _malformed()],
        _calls("ping") + _text("Done."),
    )

    assert _shape(events) == ["[", "Sure, opening it.", "]", "[", "Done.", "]"]
    assert len(models.requests) == 2
    assert _history(brain)[:2] == ["user: hello", "model: Sure, opening it."]


async def test_it_asks_once_and_a_second_leak_ends_the_turn_silent() -> None:
    """Once. A model that writes the call as text twice ends the turn without a
    word, and with a context that holds nothing it did not say."""
    brain, models, events = await _run(_text(_LEAKED), _text("```tool_code\nping()\n```"))

    assert _shape(events) == []
    assert len(models.requests) == 2
    assert _history(brain) == ["user: hello"]


async def test_a_leak_the_model_recovers_from_itself_is_not_asked_again() -> None:
    """A hop that leaks text and also makes a real call keeps going under AFC, so
    there is nothing to recover: the text is dropped and the turn continues."""
    script = [
        _chunk([types.Part(text='{"name": "ping"}')]),
        _chunk([types.Part(function_call=types.FunctionCall(name="ping", args={}))]),
        _chunk([], finish=True),
        *_text("Pong."),
    ]
    brain, models, events = await _run(script)

    assert _shape(events) == ["[", "Pong.", "]"]
    assert len(models.requests) == 1
    assert _history(brain) == ["user: hello", "model: call:ping", "user: resp:ping", "model: Pong."]


# ─── Speech is not held ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "pieces",
    [
        ("Sure, the tool ", "is {ready} ", "and default_api is fine."),
        ("दुबई वाली ट्रिप ", "खोल रही हूँ, ", "{एक पल}।"),
        ("3 options: ", "tool_call is a word here."),
    ],
    ids=["english", "devanagari", "digit"],
)
async def test_speech_is_spoken_the_moment_it_arrives(pieces: tuple[str, ...]) -> None:
    """Each piece reaches the wire before the model hands over the next one —
    zero added delay — whatever it goes on to say mid-sentence."""
    _, models, events = await _run(_text(*pieces))

    assert _shape(events) == ["[", *pieces, "]"]
    assert models.log == [line for p in pieces for line in (f"model:{p}", f"spoke:{p}")] + [
        "model:"
    ]


async def test_an_opening_brace_that_is_speech_is_released() -> None:
    """A unit that opens with ``{`` waits for its first word, and speaks it — the
    held piece and the one that settled it, in order, with nothing lost."""
    brain, models, events = await _run(_text("{", "Dubai} is open, ", "shall I continue?"))

    assert _shape(events) == ["[", "{", "Dubai} is open, ", "shall I continue?", "]"]
    assert models.log[:4] == [
        "model:{",
        "model:Dubai} is open, ",
        "spoke:{",
        "spoke:Dubai} is open, ",
    ]
    assert len(models.requests) == 1
    assert _history(brain)[-1] == "model: {|Dubai} is open, |shall I continue?"


async def test_an_opening_held_to_the_end_of_its_hop_is_spoken() -> None:
    """An opening still undecided when the hop ends is speech: nothing it wrote is
    a call. The whole wait is that one hop's remaining chunks."""
    _, models, events = await _run(_text("Default"))

    assert _shape(events) == ["[", "Default", "]"]
    assert len(models.requests) == 1


# ─── A call written as text after speech began ────────────────────────────────


async def test_a_call_after_speech_is_cut_where_it_begins_and_the_turn_asks_again() -> None:
    """The words before the call go out and stay said; the call is never spoken,
    never kept, and the speech ends at the cut rather than when the hop does. The
    retry answers without repeating what the user already heard."""
    lines: list[str] = []
    sink = logger.add(lines.append, level="WARNING", format="{message}")
    try:
        brain, models, events = await _run(
            _text("Sure, opening it. ", 'default_api:read_screen()\n{"x": 1}'),
            _calls("ping") + _text("It's open."),
        )
    finally:
        logger.remove(sink)

    assert _shape(events) == ["[", "Sure, opening it. ", "]", "[", "It's open.", "]"]
    assert brain.ran == ["ping"]
    assert len(models.requests) == 2
    assert models.requests[1][-1] is _RETRY_NOTE
    assert _history(brain) == [
        "user: hello",
        "model: Sure, opening it. ",
        "model: call:ping",
        "user: resp:ping",
        "model: It's open.",
    ]
    assert any("after speech began" in line for line in lines)
    assert not any("read_screen" in line for line in lines), "model output reached the log"


async def test_the_speech_ends_at_the_cut_not_at_the_end_of_the_hop() -> None:
    """The ``SpeechEnd`` goes out on the chunk that carried the marker, before the
    model hands over the rest of its call."""
    client = _Client(_text("Sure. ", "certain_tool_call", ' "name": "ping"', "}"), _text("Ok."))
    brain, _, session = await _open(_Coach(client))
    async for ev in brain.on_user_message(session, UserMessage(text="hello")):
        if isinstance(ev, SpeechEnd):
            client.models.log.append("end")
    assert client.models.log[:3] == ["model:Sure. ", "model:certain_tool_call", "end"]


@pytest.mark.parametrize(
    "pieces",
    [
        ("Sure. default", "_api:read_screen()"),
        ("Sure. certain_", "tool_call"),
        ("Sure. `", "``tool_code\nping()\n```"),
        ('Sure. {"na', 'me": "ping"}'),
        ("Sure. {", '"name": "ping"}'),
        ("Sure. <tool", "_call>ping</tool_call>"),
    ],
    ids=["default_api", "certain_tool_call", "fence", "json-key", "json-brace", "tag"],
)
async def test_a_marker_split_across_chunks_is_still_cut(pieces: tuple[str, ...]) -> None:
    """The start of a marker at the end of a chunk is held — only that — and the
    next chunk decides it."""
    brain, models, events = await _run(_text(*pieces), _text("Ok."))

    assert _shape(events) == ["[", "Sure. ", "]", "[", "Ok.", "]"]
    assert models.log[:2] == [f"model:{pieces[0]}", "spoke:Sure. "]
    assert _history(brain) == ["user: hello", "model: Sure. ", "model: Ok."]


async def test_a_held_tail_that_turns_out_to_be_speech_goes_out_whole() -> None:
    """``default`` at the end of a chunk could be ``default_api:``; the next chunk
    says it is not, and it is spoken — held for that one chunk, and nothing more
    than that word was."""
    brain, models, events = await _run(_text("The default", " plan is fine."))

    assert _shape(events) == ["[", "The ", "default", " plan is fine.", "]"]
    assert models.log[:2] == ["model:The default", "spoke:The "]
    assert len(models.requests) == 1
    assert _history(brain)[-1] == "model: The default| plan is fine."


async def test_a_tail_held_to_the_end_of_its_hop_is_spoken() -> None:
    _, models, events = await _run(_text("Use the default"))

    assert _shape(events) == ["[", "Use the ", "default", "]"]
    assert len(models.requests) == 1


async def test_a_barge_in_after_the_cut_keeps_what_was_heard() -> None:
    """Closed while the leaked call is still streaming: the words before it stay
    the model's own, and none of the call is kept."""
    client = _Client(_text("Sure. ", "default_api:read_screen", "()"), _text("Ok."))
    brain, _, session = await _open(_Coach(client))
    gen = brain.on_user_message(session, UserMessage(text="hello"))
    seen: list[Speech] = []
    async for ev in gen:
        seen.append(ev)
        if isinstance(ev, SpeechEnd):
            break
    await gen.aclose()

    assert _shape(seen) == ["[", "Sure. ", "]"]
    assert _history(brain) == ["user: hello", "model: Sure. "]


async def test_a_call_after_speech_in_a_unit_that_also_called_is_not_asked_again() -> None:
    """The model made the real call too, so AFC hops on and nothing is stranded."""
    script = [
        _chunk([types.Part(text="Sure. default_api:ping()")]),
        _chunk([types.Part(function_call=types.FunctionCall(name="ping", args={}))]),
        _chunk([], finish=True),
        *_text("Pong."),
    ]
    brain, models, events = await _run(script)

    assert _shape(events) == ["[", "Sure. ", "]", "[", "Pong.", "]"]
    assert len(models.requests) == 1
    assert _history(brain) == [
        "user: hello",
        "model: Sure. |call:ping",
        "user: resp:ping",
        "model: Pong.",
    ]


_LONGEST_HEAD = max(len(h) for h in _SPOKEN_CALL_HEADS)
_SPEECH = (
    "Sure, the Dubai trip is open; the default plan is fine, tools are ready, "
    "and a call-back is booked for Tuesday at 4. "
    "दुबई वाली ट्रिप खोल रही हूँ, {एक पल}। "
    "Certainly — the <b>best</b> option is `Goa`, or [1, 2] of them."
)


@pytest.mark.parametrize("size", [1, 2, 3, 5, 8, 13])
def test_speech_holds_at_most_a_marker_head_and_loses_nothing(size: int) -> None:
    """The latency bound, as a property: whatever the chunking, nothing past the
    opening is held longer than the longest marker head, and every character comes
    out once, in order."""
    unit = _Unit(content=types.Content(role="model", parts=[]))
    out: list[str] = []
    for i in range(0, len(_SPEECH), size):
        out += unit.release(_SPEECH[i : i + size])
        if unit.leaked is False:
            assert len(unit.tail) <= _LONGEST_HEAD, repr(unit.tail)
    out += unit.settle(malformed=False)

    assert unit.leaked is False
    assert "".join(out) == _SPEECH


def test_speech_chunked_at_words_holds_nothing() -> None:
    """What a model streams in practice: each piece goes out whole the moment it
    arrives, in English and in Devanagari."""
    unit = _Unit(content=types.Content(role="model", parts=[]))
    for word in _SPEECH.split(" "):
        piece = word + " "
        assert unit.release(piece) == [piece]


@pytest.mark.parametrize(
    ("text", "verdict"),
    [
        (_LEAKED, True),
        ("default_api.open_itinerary(id='x')", True),
        ("print(default_api.read_screen())", True),
        ('{"name": "read_screen", "args": {}}', True),
        ('{\n  "name"', True),
        ('[{"function": "x"}]', True),
        ("<tool_call>", True),
        ("```json\n{", True),
        ("read_screen()", True),
        ("Sure, opening it.", False),
        ("Certainly.", False),
        ("Tools are ready.", False),
        ("दुबई वाली ट्रिप खुल गई।", False),
        ("{Dubai} is open", False),
        ('"Dubai" is open', False),
        ("<b>bold", False),
        ("[1, 2]", False),
        ("Default", None),
        ("certain", None),
        ("{", None),
        ('{"na', None),
        ("", None),
    ],
)
def test_the_opening_decides(text: str, verdict: bool | None) -> None:
    assert _looks_like_call(text) is verdict
