"""The Aura Bank support demo, end to end over the wire — no network, no LLM key.

The real ``AuraBrain`` — the shipping ``demos/aura/backend/brain.py``, its real
prompt, its real thirty-odd tools — hosted on a real ``brain_server`` socket and
driven by the conformance ``VoqalizeDriver``, with only the *model* scripted. See
``tests/_harness.py`` for what every demo's e2e proves.

Aura is the only demo with a **blocking** tool: ``authenticate`` opens a sign-in
dialog and waits for the browser to report the customer finished, and the server
mints the session token *there* — which is precisely why the model can never
produce one. Testing that needs a turn in flight and a client message sent into
it, so it lives here rather than in the cross-demo sweep. Its failure mode is the
worst one a voice agent has: a tool that never unblocks leaves the bot silent
with the floor held, which no assertion on a completed turn can see.

Run: ``cd demos && uv run pytest tests/test_aura_e2e.py``
"""

from __future__ import annotations

import asyncio
import json

from google.genai import interactions as gi
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.aura.brain import _GREETING  # noqa: E402

VOICE = "omnivoice/gauri"
LANGUAGE = "en"


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
                reply_and_call("Let me get you signed in securely.", "authenticate"),
                reply("You're signed in — which account would you like?"),
            ],
        }
    )


def _tool_results(llm: ScriptedGemini) -> str:
    """Every tool result the brain put in front of the model, as one blob.

    A blocking tool's outcome never reaches the wire — the customer hears only the
    sentence the model built from it — so the model's *next* prompt is the only
    place it is visible. On the interactions engine that prompt is the ``input``
    of the next ``interactions.create``: the brain runs the tool itself, between
    hops, and appends a :class:`gi.FunctionResultStep` carrying the result as
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


async def test_the_signin_blocks_until_the_browser_reports_back() -> None:
    """The full secure handshake, with the turn in flight.

    ``authenticate`` opens the dialog and *waits*: the tool call has not returned,
    so the turn cannot finish until the browser answers. Then the server — not the
    model — mints the token, which is the property the whole design rests on: the
    token is only reachable after a real on-screen authorisation, so no amount of
    prompt injection produces one. Assert it in the model's next prompt, since
    that is the only place a tool result is ever visible."""
    llm = _llm()
    async with demo("aura", llm) as rig:
        await rig.driver.start_session()

        turn = asyncio.create_task(rig.driver.user_says("What's my balance?"))
        try:
            commands = await rig.driver.collect_ui_commands(min_count=1)
            opened = commands[0]
            assert opened["command"] == "open_auth", commands
            nonce = opened["payload"]["nonce"]
            # The nonce binds this dialog to the waiting future; without it the
            # browser's answer resolves nothing and the turn hangs to timeout.
            assert nonce
            assert not turn.done(), "authenticate returned before the customer signed in"

            await rig.driver.send_client_message("auth_complete", {"nonce": nonce})
            completed = await turn
        finally:
            turn.cancel()

        # Two units: the line before the dialog, and the line after the browser
        # answered. The second one only exists if the tool actually unblocked and
        # the brain took a second hop.
        check_turn(rig, completed, units=2)

    results = _tool_results(llm)
    assert "'status': 'authenticated'" in results
    # A JWT the model never wrote: three dot-separated segments, minted by the
    # brain in `_complete_auth` after the browser reported the sign-in.
    assert "'authenticated_context': 'ey" in results


async def test_a_dismissed_signin_unblocks_instead_of_sitting_muted() -> None:
    """The customer closing the dialog must unblock the tool immediately.

    Without the cancel path the future waits out its ninety-second timeout with the
    floor held — the caller says "no thanks", and the bot goes silent for a minute
    and a half. So the cancel is asserted as a *completed turn that still speaks*,
    not merely as a status string."""
    llm = _llm()
    async with demo("aura", llm) as rig:
        await rig.driver.start_session()

        turn = asyncio.create_task(rig.driver.user_says("What's my balance?"))
        try:
            commands = await rig.driver.collect_ui_commands(min_count=1)
            assert commands[0]["command"] == "open_auth", commands
            await rig.driver.send_client_message(
                "auth_cancelled", {"nonce": commands[0]["payload"]["nonce"]}
            )
            completed = await turn
        finally:
            turn.cancel()

        check_turn(rig, completed, units=2)

    results = _tool_results(llm)
    assert "'status': 'declined'" in results
    assert "authenticated_context" not in results
