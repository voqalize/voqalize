"""The Aura Bank support demo, end to end over the wire — no network, no LLM key.

The real ``AuraBrain`` — the shipping ``demos/aura/backend/brain.py``, its real
prompt, its real thirty-odd tools — hosted on a real ``brain_server`` socket and
driven by the conformance ``VoqalizeDriver``, with only the *model* scripted. See
``tests/_harness.py`` for what every demo's e2e proves.

Aura is the demo that carries the secure flow, and what these tests pin is that
**nothing waits on the customer**. ``show_auth_popup`` puts a sign-in on screen
and returns in the same breath; the customer authorises it in their own time, or
never; the brain mints the token when the browser reports they did, and hands it
to the model as a line of context. The ordering that a wait used to enforce is
carried instead by the signatures — a tool that needs a token refuses without one
— so the four tests below are the four states that actually occur: opened, taken,
dismissed, and skipped.

Run: ``cd demos && uv run pytest tests/test_aura_e2e.py``
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from google.genai import interactions as gi
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.aura.brain import _GREETING  # noqa: E402

VOICE = "omnivoice/gauri"
LANGUAGE = "en"

#: The header every token the brain mints starts with — HS256, JWT — base64url'd.
#: Its presence in a blob means something got signed.
_JWT_HEAD = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."

#: A well-formed JWT the brain never signed — our header, junk signature. What the
#: model would produce if it filled the parameter in rather than wait to be handed
#: one.
FORGED = _JWT_HEAD + "eyJzdWIiOiJjdXNfMSJ9.not_our_signature"


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            "How do I add a payee?": [
                reply_and_call(
                    "Let me show you.",
                    "play_help_video",
                    video_id="add-payee",
                    start_sec=12,
                ),
                reply_and_call("First, open Payments.", "highlight_step", index=1),
                reply("Then tap Add Payee and enter their account number."),
            ],
            "What's my balance?": [
                reply_and_call("I'll put a secure sign-in on your screen.", "show_auth_popup"),
                reply("Authorise that whenever you're ready and I'll pull it up."),
            ],
            "Anything else I should know?": [reply("Nothing else — take your time.")],
            "Just tell me the number.": [
                reply_and_call(
                    "One moment.",
                    "get_account_balance",
                    authenticated_context=FORGED,
                    account_id="ac_918021004321",
                ),
                reply("I'll need you to sign in first — the sign-in is on your screen."),
            ],
        }
    )


def _tool_results(llm: ScriptedGemini) -> str:
    """Every tool result the brain put in front of the model, as one blob.

    A tool's outcome never reaches the wire — the customer hears only the sentence
    the model built from it — so the model's *next* prompt is the only place it is
    visible. On the interactions engine that prompt is the ``input`` of the next
    ``interactions.create``: the brain runs the tool itself, between hops, and
    appends a :class:`gi.FunctionResultStep` carrying the result as
    ``json.dumps({"result": ...})``. Unwrap that one level — asserting on the raw
    JSON matches nothing whose result contains a quote."""
    out: list[str] = []
    for request in llm.aio.interactions.requests:
        for step in request.get("input") or []:
            if not isinstance(step, gi.FunctionResultStep):
                continue
            try:
                payload = json.loads(str(step.result))
            except (TypeError, ValueError):
                payload = {"result": step.result}
            out.append(str(payload.get("result", payload)))
    return " ".join(out)


def _context_text(llm: ScriptedGemini) -> str:
    """Everything the brain appended to the context as the customer's own words.

    What the customer does on screen reaches the model exactly one way: ``on_rtvi``
    appends a line saying what they did. It takes no floor, so it is invisible
    until the *next* request carries the whole context along with it."""
    out: list[str] = []
    for request in llm.aio.interactions.requests:
        for step in request.get("input") or []:
            if isinstance(step, gi.UserInputStep):
                out.extend(str(getattr(c, "text", "") or "") for c in (step.content or []))
    return " ".join(out)


def _auth_nonce(rig: Any) -> str:
    """The nonce the brain stamped on the sign-in it just put on screen.

    It is what makes the browser's answer trustworthy: minted here, carried out
    with the dialog, and good for that one dialog once."""
    opened = rig.command("open_auth")
    nonce = str(opened["nonce"])
    assert nonce, opened
    return nonce


async def test_greeting_and_voice_reach_the_wire() -> None:
    """Aria greets with a fixed line — no model call on the start path — and her
    declared female English voice lands on **both** legs before that audio."""
    async with demo("aura", _llm()) as rig:
        greeting = await rig.driver.start_session()
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == _GREETING
        check_voice_pair(rig, voice=VOICE, language=LANGUAGE)


async def test_narrating_a_help_video_drives_the_screen() -> None:
    """Three model calls in one turn: play the clip muted, then highlight steps as
    Aria narrates. The ``start_sec`` is the one the console seeks to, so it has to
    survive as an int rather than the model's string."""
    async with demo("aura", _llm()) as rig:
        await rig.driver.start_session()

        turn = await rig.driver.user_says("How do I add a payee?")
        check_turn(rig, turn, units=3)

        assert rig.actions() == ["play_help_video", "highlight_step"], rig.actions()
        video = rig.command("play_help_video")
        assert video["video_id"] == "add-payee"
        assert video["start_sec"] == 12
        assert rig.command("highlight_step")["index"] == 1


async def test_the_signin_goes_up_and_the_turn_finishes_without_it() -> None:
    """The turn completes with the sign-in still untouched on screen.

    This is the whole point of the shape. The old tool awaited the browser, which
    meant the customer sat mic-muted for as long as they took to read a sheet —
    gagged precisely while being asked to act. Now the tool announces and returns:
    the customer keeps the floor, keeps the call, and can answer the sheet in a
    minute or not at all."""
    llm = _llm()
    async with demo("aura", llm) as rig:
        await rig.driver.start_session()

        turn = await rig.driver.user_says("What's my balance?")
        check_turn(rig, turn, units=2)

        assert rig.actions() == ["open_auth"], rig.actions()
        assert _auth_nonce(rig)

    results = _tool_results(llm)
    assert "'status': 'sign_in_opened'" in results
    # Nothing was minted. The result talks *about* an authenticated_context — it is
    # telling the model to wait for one — but no token exists, because the customer
    # has not signed in and the brain is the only thing that can sign.
    assert _JWT_HEAD not in results


async def test_signing_in_hands_the_model_a_token_it_could_not_have_written() -> None:
    """The browser reports the sign-in, and the token appears in the *context*.

    The server — not the model — mints it, in ``_complete_auth``, on the browser's
    report that the customer completed a real on-screen authorisation. That is the
    property the whole design rests on: the signing key is reachable by exactly one
    path, and it does not run through the model. What the model gets is an opaque
    string it was handed, in a line of context describing what the customer did."""
    llm = _llm()
    async with demo("aura", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("What's my balance?")

        await rig.driver.send_client_message("auth_complete", {"nonce": _auth_nonce(rig)})
        # `send_client_message` returns once the frame is sent, not once `on_rtvi`
        # has run it (it takes no floor, so there is nothing to await) — give the
        # append a beat before the next turn's prompt is built.
        await asyncio.sleep(0.1)

        turn = await rig.driver.user_says("Anything else I should know?")
        check_turn(rig, turn, units=1)

    context = _context_text(llm)
    assert "authorised the secure sign-in" in context
    # A JWT the model never wrote: our header, three dot-separated segments.
    assert f"authenticated_context is {_JWT_HEAD}" in context


async def test_a_dismissed_signin_tells_the_model_so_instead_of_stalling() -> None:
    """The customer closing the sheet is an answer, and it reaches the model.

    Nothing is waiting on it any more, so the failure this guards is quieter than
    the old one: not a bot muted for ninety seconds, but a bot that goes on
    believing a sign-in is pending and asks the customer to authorise a sheet that
    is no longer there."""
    llm = _llm()
    async with demo("aura", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("What's my balance?")

        await rig.driver.send_client_message("auth_cancelled", {"nonce": _auth_nonce(rig)})
        await asyncio.sleep(0.1)

        turn = await rig.driver.user_says("Anything else I should know?")
        check_turn(rig, turn, units=1)

    context = _context_text(llm)
    assert "closed the secure sign-in without signing in" in context
    assert _JWT_HEAD not in context


async def test_a_forged_token_is_refused_and_the_model_is_sent_back_a_step() -> None:
    """The must-happen-before edge, exercised by skipping it.

    With nothing blocking, a model is perfectly able to call ``get_account_balance``
    the moment it sees the sign-in go up, filling in a plausible-looking token. The
    signature is what stops it: the parameter is mandatory, the brain verifies it
    against this session's salt, and a forgery earns an error naming the step that
    has not happened. The failure path *is* the enforcement — so it is asserted as
    a completed, speaking turn, not merely as a status string."""
    llm = _llm()
    async with demo("aura", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("What's my balance?")

        turn = await rig.driver.user_says("Just tell me the number.")
        check_turn(rig, turn, units=2)

    results = _tool_results(llm)
    assert "'status': 'not_authenticated'" in results
    assert "call show_auth_popup()" in results.lower()
    # No balance leaked past the guard.
    assert "balance" not in results.lower().split("'status': 'not_authenticated'")[1]
