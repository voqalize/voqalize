"""`GeminiBrain` reconciles its context from finalizes, one per unit it opened.

`tests/contract/test_brain_contract.py` states that rule once and runs it
against every engine — this file only covers what is specific to `GeminiBrain`:
`append_to_context` has to stay invisible to reconciliation, whatever type it
holds.

No model call happens here — the units are opened by hand, exactly as `respond`
opens them while streaming. `test_gemini_turn.py` covers the streaming itself.
"""

from __future__ import annotations

from google import genai
from google.genai import types

from voqalize.sdk import Session
from voqalize.sdk.brain import _adapter_for
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
    adapter = _adapter_for(brain, _Silent())
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


def _heard(text: str, *, speech_id: int = 0, interrupted: bool = False) -> Finalize:
    """One finalize. ``interrupted`` is a comparison rather than a flag, so a cut
    unit is one whose generated text runs past what the caller heard."""
    generated = text + " ...and the tail nobody heard." if interrupted else text
    return Finalize(speech_id=speech_id, heard=text, generated=generated)


# ─── And what an append does to all of it ─────────────────────────────────────


def _appended(brain: GeminiBrain) -> list[str]:
    return [
        "".join(p.text or "" for p in (c.parts or [])) for c in brain._history if c.role == "user"
    ]


async def test_an_appended_content_is_not_a_unit_to_reconcile() -> None:
    """`append_to_context` writes into the same list reconciliation rewrites, so it
    has to be invisible to it.

    It is, and structurally rather than by luck: the queue holds unit objects, and
    reconciliation removes and rewrites *by identity*. An appended content is
    neither in the queue nor identical to anything in it, so a finalize cannot land
    on it however badly the truncation lines up.
    """
    brain, session = await _brain()
    _speak(brain, "there are three options this morning")
    brain.append_to_context(
        types.Content(role="user", parts=[types.Part(text="ON SCREEN: the flights tab")])
    )

    await brain.on_finalize(session, _heard("there are three", interrupted=True))

    assert _texts(brain) == ["there are three"]
    assert _appended(brain) == ["ON SCREEN: the flights tab"]


async def test_an_append_does_not_save_an_unanswered_call() -> None:
    """The one thing the provider validates is that the last step is not an
    unanswered call — and an append is enough to satisfy it, which means an append
    can leave a broken context looking well-formed. So this cleanup can never be
    relaxed on the grounds that the API would catch it.
    """
    brain, _ = await _brain()
    unit = brain._open_unit()  # pyright: ignore[reportPrivateUsage]
    part = types.Part(function_call=types.FunctionCall(name="search_flights", args={}))
    brain._extend_unit(unit, part)  # pyright: ignore[reportPrivateUsage]
    brain.append_to_context(
        types.Content(role="user", parts=[types.Part(text="ON SCREEN: the flights tab")])
    )

    brain._drop_unanswered([(unit, part)])  # pyright: ignore[reportPrivateUsage]

    assert _appended(brain) == ["ON SCREEN: the flights tab"]
    # The call went; the append stayed.
    assert [c.role for c in brain._history] == ["user"]  # pyright: ignore[reportPrivateUsage]
