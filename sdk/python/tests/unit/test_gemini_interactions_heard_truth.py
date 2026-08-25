"""`GeminiInteractionsBrain` reconciles its context from finalizes, one per
unit it opened.

The rule is the same one `GeminiBrain` follows, and it is the reason this SDK
holds the conversation itself rather than letting the API hold it: the brain
commits what the caller *heard*, and only the runtime knows that. It reports
every speech unit it minted exactly once — including the ones that never reached
a speaker, as heard-nothing — which is what lets the queue be a plain FIFO.

What differs is the *shape* being rewritten. A turn here is a list of steps, and
the unit is one ``model_output`` step, held by identity and edited in place. So a
tool call sitting between two spoken units is a step of its own rather than a
part inside one, and cutting a unit down cannot disturb it.

No model call happens here — the units are opened by hand, exactly as `respond`
opens them while streaming. `test_gemini_interactions_turn.py` covers the
streaming itself.
"""

from __future__ import annotations

from google import genai
from google.genai import interactions as gi

from voqalize.sdk import Session
from voqalize.sdk.brain import adapter_for
from voqalize.sdk.events import Finalize
from voqalize.sdk.gemini_interactions import GeminiInteractionsBrain
from voqalize.sdk.wire import Frame, SessionStartFrame


class _Silent:
    """An emitter that keeps nothing: these tests read history, not the wire."""

    def send(self, frame: Frame) -> None:
        pass


async def _brain() -> tuple[GeminiInteractionsBrain, Session]:
    brain = GeminiInteractionsBrain(
        client=genai.Client(api_key="not-used-no-call-is-made"),
        system_instruction="be brief",
    )
    adapter = adapter_for(brain, _Silent())
    await adapter.handle_frame(SessionStartFrame(turn_id=1, session_id="s"))
    session = adapter._session  # pyright: ignore[reportPrivateUsage]
    assert session is not None
    return brain, session


def _texts(brain: GeminiInteractionsBrain) -> list[str]:
    return [
        "".join(c.text for c in (s.content or []) if isinstance(c, gi.TextContent))
        for s in brain._history
        if isinstance(s, gi.ModelOutputStep)
    ]


def _speak(brain: GeminiInteractionsBrain, text: str) -> None:
    """One unit of generated speech, as `respond` builds it while streaming: the
    step goes into history, and it joins the queue because it opened a speech
    unit on the wire and one finalize is therefore coming back for it."""
    step = gi.ModelOutputStep(content=[gi.TextContent(text=text)])
    brain._history.append(step)
    brain._awaiting.append(step)  # pyright: ignore[reportPrivateUsage]


def _tool_call(brain: GeminiInteractionsBrain, name: str) -> None:
    """A hop that says nothing: the model called a tool and spoke no words. It is
    history and nothing else — no speech unit was ever opened, so no finalize is
    coming, so it never joins the queue."""
    brain._history.append(gi.FunctionCallStep(id=f"call_{name}", name=name, arguments={}))


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


async def test_a_unit_nobody_heard_leaves_the_context() -> None:
    """Generated ahead of playout and beaten to the speaker by a barge-in. A model
    turn with nothing in it is not a turn, so the whole step goes rather than
    sitting there as something the model thinks it said."""
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

    calls = [s for s in brain._history if isinstance(s, gi.FunctionCallStep)]
    assert [s.name for s in calls] == ["search_flights"]
    assert _texts(brain) == ["there are three"]


async def test_a_dropped_unit_leaves_the_steps_around_it_untouched() -> None:
    """The step is dropped by *identity*, not by value. Two empty steps are equal
    as pydantic models, so an equality-based removal takes whichever it meets
    first — and the context loses a step the caller did hear."""
    brain, session = await _brain()
    _speak(brain, "let me look that up")
    _tool_call(brain, "search_flights")
    _speak(brain, "and here is the part nobody will ever hear")

    await brain.on_finalize(session, _heard("", speech_id=1, interrupted=True))
    await brain.on_finalize(session, _heard("", speech_id=2, interrupted=True))

    assert [type(s).__name__ for s in brain._history] == ["FunctionCallStep"]


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

    assert _texts(brain) == ["let me look that up", "there are three"]


async def test_a_finalize_with_nothing_awaiting_is_the_greeting() -> None:
    """`greet` is spoken by the SDK, not generated here, so the finalize is the
    only record of it. Without this the model does not know it greeted and opens
    a second time."""
    brain, session = await _brain()

    await brain.on_finalize(session, _heard("hi, travel desk here"))

    assert _texts(brain) == ["hi, travel desk here"]


# ─── And what an append does to all of it ─────────────────────────────────────


def _appended(brain: GeminiInteractionsBrain) -> list[str]:
    return [
        "".join(c.text for c in (s.content or []) if isinstance(c, gi.TextContent))
        for s in brain._history
        if isinstance(s, gi.UserInputStep)
    ]


async def test_an_appended_step_is_not_a_unit_to_reconcile() -> None:
    """`append_to_context` writes into the same list reconciliation rewrites, so it
    has to be invisible to it.

    It is, and structurally rather than by luck: the queue holds step objects, and
    reconciliation removes and rewrites *by identity* — which this engine already
    has to do, since two freshly opened steps are equal as pydantic models. An
    appended step is neither in the queue nor identical to anything in it.
    """
    brain, session = await _brain()
    _speak(brain, "there are three options this morning")
    brain.append_to_context(
        gi.UserInputStep(content=[gi.TextContent(text="ON SCREEN: the flights tab")])
    )

    await brain.on_finalize(session, _heard("there are three", interrupted=True))

    assert _texts(brain) == ["there are three"]
    assert _appended(brain) == ["ON SCREEN: the flights tab"]


async def test_an_append_does_not_save_an_unanswered_call() -> None:
    """The one thing this API validates is that the last step is not an unanswered
    call — and an append is enough to satisfy it, which means an append can leave a
    broken context looking well-formed. So this cleanup can never be relaxed on the
    grounds that the API would catch it.
    """
    brain, _ = await _brain()
    _tool_call(brain, "search_flights")
    brain.append_to_context(
        gi.UserInputStep(content=[gi.TextContent(text="ON SCREEN: the flights tab")])
    )

    brain._drop_unanswered()  # pyright: ignore[reportPrivateUsage]

    assert _appended(brain) == ["ON SCREEN: the flights tab"]
    # The call went; the append stayed.
    assert [type(s).__name__ for s in brain._history] == ["UserInputStep"]
