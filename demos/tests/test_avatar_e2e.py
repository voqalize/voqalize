"""The avatar demo, end to end over the wire — no network, no LLM key.

The real ``AvatarBrain`` — the shipping ``demos/avatar/backend/brain.py``, its
real prompt, its real five tools, its real section index — hosted on a real
``brain_server`` socket and driven by the conformance ``VoqalizeDriver``, with
only the *model* scripted. See ``tests/_harness.py`` for what every demo's e2e
proves.

Avatar is the demo that earns its own **server-message** assertions. Everything
that makes it worth linking from the library's front door — the greeting wave,
the working claim held across a deliberate pause, the voice that moves with the
face — is a message on a lane nothing else in this suite reads. None of it is
visible in a transcript: a call where the wave never fired and the face sat
still transcribes exactly like a call where it worked.

Run: ``cd demos && uv run pytest tests/test_avatar_e2e.py``
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply, reply_and_call

from voqalize.sdk.wire import ConfigureFrame, EndFrame, RTVIType, SpeechEndFrame

from ._harness import DemoRig, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.avatar import brain as brain_module  # noqa: E402
from voqalize_demos._loaded.avatar.brain import _GREETING, _SIGN_OFF  # noqa: E402

# The default avatar is `arjun`, and `arjun` is male — so the call opens on the
# male reference clip, which is also the voice the agent is provisioned with, and
# any switch to a female avatar has to move it.
VOICE = "omnivoice/gaurav"
LANGUAGE = "en"


def _avatar_messages(rig: DemoRig) -> list[dict[str, Any]]:
    """Every ``{"type": "avatar", …}`` envelope the brain put on the wire, in order.

    This is the whole avatar integration seen from the outside: an RTVI
    ``server-message``, which is a lane the runtime forwards without reading. A
    page mounting ``@voqalize/avatar`` receives exactly these dicts."""
    return [
        f.data
        for f in rig.driver.rtvi
        if f.type is RTVIType.SERVER_MESSAGE
        and isinstance(f.data, dict)
        and f.data.get("type") == "avatar"
    ]


def _claims(rig: DemoRig) -> list[str | None]:
    return [m.get("state") for m in _avatar_messages(rig) if m.get("cmd") == "claim"]


def _actions(rig: DemoRig) -> list[str]:
    return [str(m.get("id")) for m in _avatar_messages(rig) if m.get("cmd") == "action"]


async def _settle() -> None:
    """Let a client message reach ``on_rtvi``.

    A client message takes no floor and so completes no turn — there is nothing
    to await. Frames on one connection are ordered, so anything sent before the
    next turn is ingested by it; a test asserting on the *message itself*, with
    no turn behind it, has to give the callback a moment instead."""
    await asyncio.sleep(0.1)


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            "How does the lipsync stay in step?": [
                reply_and_call(
                    "Here's the timeline.", "show_section", request={"section": "lipsync"}
                ),
                reply(
                    "Two legs write one track — a fast one from the text, an accurate one behind it."
                ),
            ],
            "Why does the pipeline not know when you're working?": [
                # The shape the prompt demands: a holding line out loud, THEN the
                # dig. A silent deep_dive is the failure mode this scripts against.
                reply_and_call(
                    "Give me a second, let me pull that up.",
                    "deep_dive",
                    request={"topic": "who can see what", "section": "states"},
                ),
                reply(
                    "The pipeline watches turns; it can't see inside a brain on the far side of a socket."
                ),
            ],
            "Show me thinking.": [
                reply_and_call("Here it is.", "demonstrate", request={"state": "THINKING"}),
                reply("That's a claim — durable, and any fact outranks it."),
            ],
            "Wave at me.": [
                call("perform", request={"gesture": "wave_hello"}),
                reply("An action. It completes on its own and leaves nothing behind."),
            ],
            "Anything at all.": reply("Ask me how the mouth stays in step."),
        }
    )


async def test_it_greets_with_a_wave_and_its_voice_reaches_the_wire() -> None:
    """The first thing a visitor gets is a gesture they did not ask for.

    The wave is the demo's first argument — that the face is driven from the
    server — and it is deliberately **not** sent from ``greet``: a brain is
    dialled at pipeline start, before the browser's data channel exists, so a
    server message emitted there is dropped where nothing can see it. Audio is
    queued by the transport and does not have that problem, which is exactly why
    the bug would have been invisible: the greeting would still be heard. So the
    page says it is listening and the wave answers that, once.

    The male English pair lands on both legs before the greeting audio,
    because the call opens on ``arjun``."""
    async with demo("avatar", _llm()) as rig:
        greeting = await rig.driver.start_session()
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == _GREETING
        check_voice_pair(rig, voice=VOICE, language=LANGUAGE)
        assert _actions(rig) == [], "nothing may be gestured before the page is on"

        await rig.driver.send_client_message("ready", {})
        await _settle()
        assert _actions(rig) == ["GESTURE_GREET"], _avatar_messages(rig)

        # Once per session: a client that reconnects and re-announces must not
        # re-greet in the middle of a sentence.
        await rig.driver.send_client_message("ready", {})
        await _settle()
        assert _actions(rig) == ["GESTURE_GREET"], _avatar_messages(rig)


async def test_a_question_scrolls_the_page_to_the_section_it_is_answered_from() -> None:
    """The documentation moves first, and only an id and a heading travel.

    The page holds the prose — it is the link target from the library's README
    and has to read on its own — so the wire carries the section the answer is
    coming from and nothing else. The model chooses an id; the heading is looked
    up in ``content.py``, so it cannot scroll the reader to a heading the page
    does not have."""
    async with demo("avatar", _llm()) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("How does the lipsync stay in step?")
        check_turn(rig, turn, units=2)

        assert rig.actions() == ["show_section"], rig.actions()
        section = rig.command("show_section")
        assert section["id"] == "lipsync"
        assert section["title"] == "How the mouth stays in sync"
        # The prose stays on the page: nothing but the id and the heading travels.
        assert set(section) == {"id", "title"}, section


async def test_the_face_picked_before_the_call_is_the_voice_the_opener_uses() -> None:
    """The pairing, asserted where it is actually decided.

    Nine faces share two recorded reference speakers, so a face and a voice are
    one choice. The visitor makes it on the strip before dialling and it rides
    the connect request; the brain has to apply it before the opener is
    synthesised, because a greeting in the other speaker's voice is the whole
    defect this arrangement exists to remove.

    ``meera`` is female, and the agent this demo runs on is provisioned male —
    so a brain that ignored ``init`` and let the agent's own voice stand would
    still produce audio, and this is the assertion that catches it."""
    async with demo("avatar", _llm()) as rig:
        greeting = await rig.driver.start_session(init={"surface": "avatar-web", "avatar": "meera"})
        assert greeting is not None and greeting.text == _GREETING
        check_voice_pair(rig, voice="omnivoice/gauri", language="en")

        # Exactly one, and before the greeting. A second would mean something
        # still moves the voice mid-call, which is the thing that was removed.
        configs = [r.config for r in rig.driver.requests if isinstance(r, ConfigureFrame)]
        voices = [c.tts.voice for c in configs if c.tts and c.tts.voice]
        assert voices == ["omnivoice/gauri"], voices
        # Both language legs, because `Config` refuses a half-stated pair and
        # this is the check that the demo did not learn to send one anyway.
        only = configs[0]
        assert only.tts is not None and only.stt is not None
        assert only.tts.language == "en" and only.stt.language == "en"


async def test_an_unknown_face_falls_back_to_one_the_agent_can_already_speak() -> None:
    """The payload is browser-supplied on a public page, so a stale build or a
    hand-edited request must produce a working call rather than a failed one —
    and the fallback must not itself be a mismatch. ``arjun`` is the default
    precisely because the agent is provisioned with the voice it is paired
    with."""
    async with demo("avatar", _llm()) as rig:
        await rig.driver.start_session(init={"avatar": "not-a-face"})
        check_voice_pair(rig, voice="omnivoice/gaurav", language="en")


async def test_the_deliberate_dig_claims_working_out_loud_and_clears_it() -> None:
    """The beat the whole demo is built around, asserted as a sequence.

    The holding line is spoken *before* the claim goes out — a silent pause is
    the thing this replaces — and the claim is cleared explicitly rather than
    left for the next factual boundary to retire, because a claim left standing
    while the model is silent is a face that never comes back."""
    async with demo("avatar", _llm()) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("Why does the pipeline not know when you're working?")
        check_turn(rig, turn, units=2)

        assert turn.units[0].text.startswith("Give me a second")
        assert _claims(rig) == ["WORKING", None], _avatar_messages(rig)
        assert rig.command("working_on")["topic"] == "who can see what"
        # The dig ends on the section it dug through, so the answer has the
        # documentation for it open in front of the visitor.
        assert rig.command("show_section")["id"] == "states"


async def test_claims_and_actions_are_two_different_things_on_the_wire() -> None:
    """A demonstrated state is a claim; a gesture is an action. Both go out on the
    same lane under the same envelope, and the demo's whole explanation of the
    difference is only true if the messages differ."""
    async with demo("avatar", _llm()) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Show me thinking.")
        assert _claims(rig) == ["THINKING", None], _avatar_messages(rig)

        await rig.driver.user_says("Wave at me.")
        # No greeting wave in this test (the page never announced itself), so
        # this is the only action on the wire — and no further claims.
        assert _actions(rig) == ["GESTURE_GREET"]
        assert _claims(rig) == ["THINKING", None]


async def test_the_strip_cannot_move_the_voice_once_the_call_is_up() -> None:
    """The mid-call pick is gone, and this is the assertion that keeps it gone.

    It used to be the demo's showpiece: click a face, the voice follows. It was
    also its worst moment — the voice changing in the middle of an answer is the
    one thing a listener always notices. The page locks the strip for the length
    of the call; this is the brain half, so a page that ships the old behaviour
    by accident cannot resurrect it on its own."""
    async with demo("avatar", _llm()) as rig:
        await rig.driver.start_session()
        before = len([r for r in rig.driver.requests if isinstance(r, ConfigureFrame)])

        await rig.driver.send_client_message("pick_avatar", {"key": "naina"})
        await _settle()

        after = [r.config for r in rig.driver.requests if isinstance(r, ConfigureFrame)]
        assert len(after) == before, "a mid-call pick moved the voice"
        assert "switch_avatar" not in rig.actions(), rig.actions()


async def test_the_call_is_capped_and_ends_on_a_wave(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two minutes, enforced in the brain rather than on the page.

    The cap is checked at the turn boundary so a sentence in flight finishes.
    What it produces is fixed — a wave, one written line, the end card, then the
    hang-up — because at the cap the interesting question is whether the demo
    closes gracefully, and a generated goodbye is one more thing that can take
    four seconds to arrive.

    The clock is patched to zero rather than waited out: what is under test is
    the ordering (speech, then card, then end), and that is the same at zero
    seconds as at a hundred and twenty."""
    monkeypatch.setattr(brain_module, "_LIMIT_S", 0.0)
    async with demo("avatar", _llm()) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("Anything at all.")

        assert turn is not None and turn.units[0].text == _SIGN_OFF
        assert _actions(rig)[-1] == "GESTURE_GOODBYE"
        assert rig.command("show_end_card")["reason"] == "time_limit"

        # And the hang-up is *after* the goodbye, which is the ordering rule the
        # sign-off relies on: `end` is called once the SDK has consumed
        # everything the generator yielded, so the line is on the wire before
        # the end frame is. A hang-up that raced the speech would cut it off.
        kinds = [type(r.frame) for r in rig.driver.log]
        assert EndFrame in kinds, "the brain did not hang up at the cap"
        assert kinds.index(EndFrame) > len(kinds) - 1 - kinds[::-1].index(SpeechEndFrame)
