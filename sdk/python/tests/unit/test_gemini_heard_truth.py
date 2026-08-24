"""`GeminiBrain` reconciles its transcript from finalizes, one per unit it opened.

The brain commits what the caller *heard*. It learns that only from the runtime,
which reports every speech unit it minted exactly once — including the ones that
never reached a speaker, as heard-nothing. That guarantee is what lets the queue
be a plain FIFO: the n-th finalize belongs to the n-th unit, so a unit that was
generated and never delivered leaves the transcript instead of sitting in it as a
sentence the model believes it said.

No model call happens here — the units are opened by hand, exactly as `respond`
opens them while streaming. `test_gemini_turn.py` covers the streaming itself.
"""

from __future__ import annotations

from google import genai
from google.genai import types

from voqalize.sdk import Session
from voqalize.sdk.brain import adapter_for
from voqalize.sdk.events import Finalize
from voqalize.sdk.gemini import GeminiBrain
from voqalize.sdk.wire import Frame, SessionStartFrame


class _Silent:
    """An emitter that keeps nothing: these tests read history, not the wire."""

    def send(self, frame: Frame) -> None:
        pass


async def _brain() -> tuple[GeminiBrain, Session]:
    brain = GeminiBrain(
        client=genai.Client(api_key="not-used-no-call-is-made"),
        system_instruction="be brief",
    )
    adapter = adapter_for(brain, _Silent())
    await adapter.handle_frame(SessionStartFrame(turn_id=1, session_id="s"))
    session = adapter._session  # pyright: ignore[reportPrivateUsage]
    assert session is not None
    return brain, session


def _texts(brain: GeminiBrain) -> list[str]:
    return [
        "".join(p.text or "" for p in (c.parts or [])) for c in brain._history if c.role == "model"
    ]


def _speak(brain: GeminiBrain, text: str) -> None:
    """One unit of generated speech, as `respond` builds it while streaming: it
    goes into history, and it joins the queue because it opened a speech unit on
    the wire and one finalize is therefore coming back for it."""
    unit = brain._open_unit()  # pyright: ignore[reportPrivateUsage]
    brain._extend_unit(unit, types.Part(text=text))  # pyright: ignore[reportPrivateUsage]
    brain._awaiting.append(unit)  # pyright: ignore[reportPrivateUsage]


def _tool_call(brain: GeminiBrain, name: str) -> None:
    """A hop that says nothing: the model called a tool and spoke no words. It is
    history and nothing else — no speech unit was ever opened, so no finalize is
    coming, so it never joins the queue."""
    unit = brain._open_unit()  # pyright: ignore[reportPrivateUsage]
    brain._extend_unit(  # pyright: ignore[reportPrivateUsage]
        unit, types.Part(function_call=types.FunctionCall(name=name, args={}))
    )


def _heard(text: str, *, speech_id: int = 0, interrupted: bool = False) -> Finalize:
    return Finalize(speech_id=speech_id, heard=text, interrupted=interrupted)


async def test_a_unit_heard_in_full_stays_as_it_was() -> None:
    """The ordinary turn: generated and delivered agree, so nothing moves."""
    brain, session = await _brain()
    _speak(brain, "the flight leaves at nine")

    await brain.on_finalize(session, _heard("the flight leaves at nine"))

    assert _texts(brain) == ["the flight leaves at nine"]


async def test_a_unit_cut_off_keeps_only_what_was_delivered() -> None:
    """The caller talked over it. The rest was never said, so the model must not
    be able to refer back to it — that is how an agent ends up citing a sentence
    the caller never heard."""
    brain, session = await _brain()
    _speak(brain, "the flight leaves at nine and connects through frankfurt")

    await brain.on_finalize(session, _heard("the flight leaves at", interrupted=True))

    assert _texts(brain) == ["the flight leaves at"]


async def test_a_unit_nobody_heard_leaves_the_transcript() -> None:
    """Generated ahead of playout and beaten to the speaker by a barge-in. A model
    turn with nothing in it is not a turn, so it goes rather than sitting there
    as something the model thinks it said."""
    brain, session = await _brain()
    _speak(brain, "and here is the part nobody will ever hear")

    await brain.on_finalize(session, _heard("", interrupted=True))

    assert _texts(brain) == [], "no trace of it anywhere"
    assert not brain._history


async def test_a_silent_tool_hop_is_never_reconciled() -> None:
    """A hop that only calls a tool is what the model *did*, not something it said.
    Nothing was minted for it and nothing comes back for it — so it is not in the
    queue at all, and the finalize behind it belongs to the reply. Put it in the
    queue and the reply's heard text lands on the tool call, the call is rewritten
    to a sentence, and every later turn is off by one for the rest of the call."""
    brain, session = await _brain()
    _tool_call(brain, "search_flights")
    _speak(brain, "there are three options this morning")

    await brain.on_finalize(session, _heard("there are three", interrupted=True))

    calls = [p.function_call for c in brain._history for p in (c.parts or []) if p.function_call]
    assert [c.name for c in calls if c] == ["search_flights"]
    assert _texts(brain) == ["", "there are three"]


async def test_finalizes_are_matched_to_units_in_order() -> None:
    """The queue is a plain FIFO, which is what the exactly-once guarantee buys:
    the n-th finalize belongs to the n-th unit the brain opened. One turn can hold
    several — the model narrates, calls a tool, then reports back — and they come
    home in order."""
    brain, session = await _brain()
    _speak(brain, "let me look that up")
    _tool_call(brain, "search_flights")
    _speak(brain, "there are three options this morning")

    await brain.on_finalize(session, _heard("let me look that up", speech_id=1))
    await brain.on_finalize(session, _heard("there are three", speech_id=2, interrupted=True))

    assert _texts(brain) == ["let me look that up", "", "there are three"]


async def test_a_finalize_with_nothing_awaiting_is_the_greeting() -> None:
    """`greet` is spoken by the SDK, not generated here, so the finalize is the
    only record of it. Without this the model does not know it greeted and opens
    a second time."""
    brain, session = await _brain()

    await brain.on_finalize(session, _heard("hi, travel desk here"))

    assert _texts(brain) == ["hi, travel desk here"]
