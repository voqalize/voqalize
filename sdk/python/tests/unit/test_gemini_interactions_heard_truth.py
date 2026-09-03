"""`GeminiInteractionsBrain` reconciles its context from finalizes, one per
unit it opened.

`tests/contract/test_brain_contract.py` states that rule once and runs it
against every engine. What is specific to this engine, and covered only here: a
turn is a list of steps, the unit is one ``model_output`` step held by identity,
and a step dropped by reconciliation must not disturb the steps around it —
plus `append_to_context`, which has to stay invisible to reconciliation
whatever step type it holds.

No model call happens here — the units are opened by hand, exactly as `respond`
opens them while streaming. `test_gemini_interactions_turn.py` covers the
streaming itself.
"""

from __future__ import annotations

from google import genai
from google.genai import interactions as gi

from voqalize.sdk import Session
from voqalize.sdk.brain import _adapter_for
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
    adapter = _adapter_for(brain, _Silent())
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


def _speak(brain: GeminiInteractionsBrain, text: str) -> int:
    """One unit of generated speech, as `respond` builds it while streaming: the
    step goes into history, and it joins the queue because it opened a speech
    unit on the wire and one finalize is therefore coming back for it."""
    step = gi.ModelOutputStep(content=[gi.TextContent(text=text)])
    brain._history.append(step)
    speech_id = brain.session.next_speech_id()
    brain._awaiting[speech_id] = step  # pyright: ignore[reportPrivateUsage]
    return speech_id


def _tool_call(brain: GeminiInteractionsBrain, name: str) -> None:
    """A hop that says nothing: the model called a tool and spoke no words. It is
    history and nothing else — no speech unit was ever opened, so no finalize is
    coming, so it never joins the queue."""
    brain._history.append(gi.FunctionCallStep(id=f"call_{name}", name=name, arguments={}))


def _heard(text: str, *, speech_id: int = 1, interrupted: bool = False) -> Finalize:
    """One finalize. ``interrupted`` is a comparison rather than a flag, so a cut
    unit is one whose generated text runs past what the caller heard."""
    generated = text + " ...and the tail nobody heard." if interrupted else text
    return Finalize(speech_id=speech_id, heard=text, generated=generated)


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
