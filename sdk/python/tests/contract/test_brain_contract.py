"""What every brain owes Voqalize, asserted against every brain we ship.

A brain is a small piece of glue with a provider on one side and the wire on the
other, and there will be many of them — one per framework worth serving. The
framework changes; the job does not. This suite is that job, written once and run
against each engine in `engines.py`, so that adding brain number three is a
matter of writing an `Engine` and reading the failures.

The nine clauses, in the order they appear below:

1. **A unit of speech opens lazily and always closes.** The runtime interrupts a
   unit, so a unit is the grain of an apology; a hop that only calls a tool must
   mint none, and no `SpeechStart` may go out without its `SpeechEnd`.
2. **Every call is answered.** A transcript holding a call with no result is one
   the provider will reject on the next hop, and the call it is missing is the
   one thing the model is waiting on.
3. **A tool that raises is answered with the failure**, not dropped — the model
   has to be able to say the booking did not go through.
4. **A turn ends.** However many hops the model asks for, the budget is real.
5. **The method is the declaration.** Name and docstring travel; nothing else has
   to be written twice.
6. **A tool runs in the turn**, with :attr:`~voqalize.sdk.Brain.session` and
   :attr:`~voqalize.sdk.Brain.turn` set, on the loop, `async def` or refused.
7. **`tools` is read once per turn**, so a brain may offer one caller a tool it
   does not offer everyone and still be consistent for the length of a turn.
8. **Heard truth.** The transcript commits what the caller *heard*: cut off, keep
   the delivered prefix; heard by nobody, drop the unit; and match finalizes to
   units first-in-first-out, which is what the runtime's exactly-once guarantee
   buys. A finalize with nothing waiting is the greeting.
9. **Grounding is per turn and lands before the caller's latest words**, so the
   model reads the screen as context for the question and not as the question.

What is *not* here is as deliberate. Nothing above names ``types.Content`` or
``gi.Step``; an invariant that cannot be said without one is a property of a
provider rather than of a brain, and lives in that engine's own suite.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from voqalize.sdk.events import Finalize, Speech, UserMessage
from voqalize.sdk.wire import UserMessageFrame

from .engines import ENGINES, IDS, Call, Engine, calls, open_call, says, shape

pytestmark = pytest.mark.parametrize("engine", ENGINES, ids=IDS)


async def _drain(brain: Any) -> list[Speech]:
    _, _, session = await open_call(brain._engine, brain)
    return [ev async for ev in brain.on_user_message(session, UserMessage(text="hello"))]


async def _turn(engine: Engine, *hops: Any, **kwargs: Any) -> tuple[Any, list[Speech]]:
    brain = engine.brain(*hops, **kwargs)
    brain._engine = engine
    return brain, await _drain(brain)


async def _dial(engine: Engine, *hops: Any) -> Any:
    """One turn driven the way Voqalize drives it — through the adapter, so the
    turn runs in its own task with the ambient turn set."""
    brain = engine.brain(*hops)
    _, _, _ = await open_call(engine, brain)
    adapter = brain._adapter
    await adapter.handle_frame(UserMessageFrame(turn_id=2, text="hello"))
    while adapter._turns:
        await asyncio.gather(*list(adapter._turns))
    return brain


def _heard(text: str, *, speech_id: int = 0, interrupted: bool = False) -> Finalize:
    return Finalize(speech_id=speech_id, heard=text, interrupted=interrupted)


def _kinds(lines: list[str], prefix: str) -> list[str]:
    return [line for line in lines if line.startswith(prefix)]


def _unanswered(lines: list[str]) -> list[str]:
    """Calls with no result behind them, by name."""
    called = [line.split("{")[0].removeprefix("call: ") for line in _kinds(lines, "call: ")]
    answered = [
        line.split(" -> ")[0].removeprefix("result: ") for line in _kinds(lines, "result: ")
    ]
    for name in answered:
        if name in called:
            called.remove(name)
    return called


# ─── 1. A unit of speech opens lazily and always closes ───────────────────────


async def test_a_plain_turn_is_one_unit(engine: Engine) -> None:
    _, events = await _turn(engine, says("Good ", "evening."))

    assert shape(events) == ["[", "Good ", "evening.", "]"]


async def test_a_silent_hop_opens_no_unit(engine: Engine) -> None:
    """The whole reason for opening lazily. Under a per-hop unit this turn emits
    an empty `SpeechStart`/`SpeechEnd` pair around the tool call, and the runtime
    is owed a finalize for a unit that was never spoken — so every finalize after
    it lands on the wrong unit for the rest of the call."""
    _, events = await _turn(engine, calls(Call("ping")), says("Pong."))

    assert shape(events) == ["[", "Pong.", "]"]


async def test_speech_either_side_of_a_tool_is_two_units(engine: Engine) -> None:
    """Two units, because the caller can interrupt between them and the runtime
    needs somewhere to stop."""
    _, events = await _turn(
        engine, [*says("Let me look."), *calls(Call("ping"))], says("Found it.")
    )

    assert shape(events) == ["[", "Let me look.", "]", "[", "Found it.", "]"]


async def test_a_turn_never_leaves_a_unit_open(engine: Engine) -> None:
    _, events = await _turn(engine, calls(Call("ping")), says("Pong."))

    assert shape(events).count("[") == shape(events).count("]") == 1


# ─── 2 & 3. Every call is answered, including the ones that fail ──────────────


async def test_a_tool_gets_the_arguments_the_model_sent(engine: Engine) -> None:
    brain, _ = await _turn(
        engine, calls(Call("show", {"args": {"name": "glucose"}})), says("There.")
    )

    assert brain.ran == ["show:glucose"]


async def test_every_call_is_answered(engine: Engine) -> None:
    brain, _ = await _turn(
        engine, calls(Call("ping"), Call("show", {"args": {"name": "meals"}})), says("Done.")
    )

    assert _unanswered(engine.transcript(brain)) == []


async def test_a_tool_that_raises_is_answered_not_dropped(engine: Engine) -> None:
    """The model must be able to tell the caller it did not work. A dropped call
    leaves it waiting on an answer that is never coming, and the provider
    rejecting the next hop is the *better* of the two outcomes."""
    brain, events = await _turn(engine, calls(Call("boom")), says("That failed."))

    lines = engine.transcript(brain)
    assert _unanswered(lines) == []
    assert any("boom" in line and "kaboom" in line for line in _kinds(lines, "result: "))
    assert shape(events) == ["[", "That failed.", "]"]


async def test_calls_run_in_the_order_the_model_produced_them(engine: Engine) -> None:
    """Parallel on the wire, sequential here. Two tools that touch the same screen
    have to land the way the model meant them to."""
    brain, _ = await _turn(
        engine,
        calls(
            Call("show", {"args": {"name": "glucose"}}),
            Call("ping"),
            Call("show", {"args": {"name": "meals"}}),
        ),
        says("Done."),
    )

    assert brain.ran == ["show:glucose", "ping", "show:meals"]


# ─── 4. A turn ends ───────────────────────────────────────────────────────────


async def test_a_model_that_only_calls_tools_still_ends(engine: Engine) -> None:
    """A model that keeps calling and never speaks is a call that never gets its
    answer back. The budget is what makes that a bounded disappointment."""
    brain, events = await _turn(engine, *[calls(Call("ping"))] * 20, max_tool_hops=3)

    assert brain.ran.count("ping") <= 3
    assert shape(events).count("[") == shape(events).count("]")


# ─── 5. The method is the declaration ─────────────────────────────────────────


async def test_the_method_is_the_declaration(engine: Engine) -> None:
    """The name and the docstring are what the model reads. Nothing about a tool
    is written twice, so nothing about it can drift."""
    brain = engine.brain()

    assert engine.declare(brain) == {
        "show": "Put a section of the screen in front of the caller.",
        "ping": "Say hello to nothing in particular.",
        "boom": "Fail.",
    }


async def test_the_declarations_go_with_every_request(engine: Engine) -> None:
    brain, _ = await _turn(engine, calls(Call("ping")), says("Pong."))

    sent = engine.declared(brain)
    assert sent, "at least one request went out"
    assert all(names == ["show", "ping", "boom"] for names in sent)


# ─── 6. A tool runs in the turn ───────────────────────────────────────────────


async def test_a_tool_reaches_the_session_and_the_turn(engine: Engine) -> None:
    """A tool that drives the screen needs both: the session to send on, and the
    turn to stamp it with, so a command generated before a barge-in is dropped
    rather than landing after the caller has moved on."""
    brain = await _dial(engine, calls(Call("ping")), says("Pong."))

    session, turn = brain.seen
    assert session is not None
    assert turn is not None


async def test_a_sync_tool_is_refused(engine: Engine) -> None:
    """We run tools inside the turn's task. A synchronous one would hold the event
    loop for as long as it runs, and the first `await` it grows is a rewrite."""

    class _Sync(engine.coach):
        @property
        def tools(self) -> list[Any]:
            return [self.blocking]

        def blocking(self) -> str:
            """Not a coroutine."""
            return "ok"

    brain = engine.brain()
    brain.__class__ = _Sync
    with pytest.raises(TypeError, match="must be `async def`"):
        engine.declare(brain)


# ─── 7. `tools` is read once per turn ─────────────────────────────────────────


async def test_the_tools_are_read_once_per_turn(engine: Engine) -> None:
    """The list is a property, so a brain can offer a caller a tool it does not
    offer everyone — decided as late as the turn it is needed for, and fixed for
    the length of that turn however many hops it takes."""
    brain, _ = await _turn(engine, calls(Call("ping")), says("Pong."))

    assert brain.read_tools == 1


# ─── 8. Heard truth ───────────────────────────────────────────────────────────


async def _reconciling(engine: Engine) -> tuple[Any, Any]:
    brain = engine.brain()
    brain._engine = engine
    _, _, session = await open_call(engine, brain)
    return brain, session


def _said(engine: Engine, brain: Any) -> list[str]:
    return [line.removeprefix("model: ") for line in _kinds(engine.transcript(brain), "model: ")]


async def test_a_unit_heard_in_full_stays_as_it_was(engine: Engine) -> None:
    brain, session = await _reconciling(engine)
    engine.speak(brain, "the flight leaves at nine")

    await brain.on_finalize(session, _heard("the flight leaves at nine"))

    assert _said(engine, brain) == ["the flight leaves at nine"]


async def test_a_unit_cut_off_keeps_only_what_was_delivered(engine: Engine) -> None:
    """The caller talked over it. The rest was never said, so the model must not
    be able to refer back to it — that is how an agent ends up citing a sentence
    the caller never heard."""
    brain, session = await _reconciling(engine)
    engine.speak(brain, "the flight leaves at nine and connects through frankfurt")

    await brain.on_finalize(session, _heard("the flight leaves at", interrupted=True))

    assert _said(engine, brain) == ["the flight leaves at"]


async def test_a_unit_nobody_heard_leaves_the_transcript(engine: Engine) -> None:
    """Generated ahead of playout and beaten to the speaker by a barge-in. A model
    turn with nothing in it is not a turn, so it goes rather than sitting there as
    something the model thinks it said."""
    brain, session = await _reconciling(engine)
    engine.speak(brain, "and here is the part nobody will ever hear")

    await brain.on_finalize(session, _heard("", interrupted=True))

    assert engine.transcript(brain) == []


async def test_a_silent_tool_hop_is_never_reconciled(engine: Engine) -> None:
    """A hop that only calls a tool is what the model *did*, not something it said.
    Nothing was minted for it and nothing comes back for it — so it is not in the
    queue at all, and the finalize behind it belongs to the reply. Put it in the
    queue and the reply's heard text lands on the tool call, and every later turn
    is off by one for the rest of the call."""
    brain, session = await _reconciling(engine)
    engine.silent_call(brain, "ping")
    engine.speak(brain, "there are three options this morning")

    await brain.on_finalize(session, _heard("there are three", interrupted=True))

    lines = engine.transcript(brain)
    assert _kinds(lines, "call: ") == ["call: ping{}"]
    assert _said(engine, brain)[-1] == "there are three"


async def test_finalizes_are_matched_to_units_in_order(engine: Engine) -> None:
    """The queue is a plain FIFO, which is what the exactly-once guarantee buys:
    the n-th finalize belongs to the n-th unit the brain opened."""
    brain, session = await _reconciling(engine)
    engine.speak(brain, "let me look that up")
    engine.silent_call(brain, "ping")
    engine.speak(brain, "there are three options this morning")

    await brain.on_finalize(session, _heard("let me look that up", speech_id=1))
    await brain.on_finalize(session, _heard("there are three", speech_id=2, interrupted=True))

    assert _said(engine, brain) == ["let me look that up", "there are three"]


async def test_a_finalize_with_nothing_awaiting_is_the_greeting(engine: Engine) -> None:
    """`greet` is spoken by the SDK, not generated here, so the finalize is the
    only record of it. Without this the model does not know it greeted and opens
    a second time."""
    brain, session = await _reconciling(engine)

    await brain.on_finalize(session, _heard("hi, travel desk here"))

    assert _said(engine, brain) == ["hi, travel desk here"]


# ─── 9. Grounding is per turn, before the caller's latest words ───────────────


async def test_grounding_lands_before_the_latest_user_turn(engine: Engine) -> None:
    """The screen is context for the question, so it goes in front of it. Behind
    it and the model answers the note instead of the caller."""

    class _Grounded(engine.coach):
        def grounding(self) -> str | None:
            return "on screen: glucose"

    brain = engine.brain(says("Right."))
    brain.__class__ = _Grounded
    brain._engine = engine
    await _drain(brain)

    for texts in engine.grounding_seen(brain):
        assert texts[-2:] == ["on screen: glucose", "hello"]
