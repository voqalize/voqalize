"""The avatar demo, end to end over the wire — no network, no LLM key.

The real ``AvatarBrain`` — the shipping ``demos/avatar/backend/brain.py``, its
real prompt, its real tools, its real section index — hosted on a real
``brain_server`` socket and driven by the conformance ``VoqalizeDriver``, with
only the *model* scripted. See ``tests/_harness.py`` for what every demo's e2e
proves.

Avatar is the demo that earns its own **server-message** assertions. Everything
that makes it worth linking from the library's front door — the greeting wave,
a gesture on request, the voice that moves with the face — is a message on a
lane nothing else in this suite reads. None of it is
visible in a transcript: a call where the wave never fired and the face sat
still transcribes exactly like a call where it worked.

**Only ``show_section`` carries the mark.** It hands back the lines the answer is
made from, so a turn that calls it is asked again at once: a pointing line, the
scroll, then the answer. ``perform`` is a gesture, so its line and the call share
one response and the turn ends with it. The scripts are written in that shape,
and the tests count requests where the shape is the point.

Run: ``cd demos && uv run pytest tests/test_avatar_e2e.py``
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import pytest
from google.genai import types
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply, reply_and_call

from voqalize.sdk.wire import ConfigureFrame, EndFrame, RTVIType, SpeechEndFrame

from ._harness import DemoRig, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.avatar import brain as brain_module  # noqa: E402
from voqalize_demos._loaded.avatar.brain import _GREETING, _SIGN_OFF  # noqa: E402
from voqalize_demos._loaded.avatar.content import SECTIONS  # noqa: E402

# The default avatar is `tanya`, and `tanya` is female — so a call that names no
# face opens on her kokoro voice, which is not the voice the agent is
# provisioned with (``omnivoice/gaurav``): the brain has to move it.
VOICE = "kokoro/ava"
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


def _states(rig: DemoRig) -> list[str | None]:
    return [m.get("state") for m in _avatar_messages(rig) if m.get("cmd") == "state"]


def _actions(rig: DemoRig) -> list[str]:
    return [str(m.get("id")) for m in _avatar_messages(rig) if m.get("cmd") == "action"]


async def _settle() -> None:
    """Let a client message reach ``on_rtvi``.

    A client message takes no floor and so completes no turn — there is nothing
    to await. Frames on one connection are ordered, so anything sent before the
    next turn is ingested by it; a test asserting on the *message itself*, with
    no turn behind it, has to give the callback a moment instead."""
    await asyncio.sleep(0.1)


def _results(contents: list[types.Content]) -> dict[str, str]:
    """Every tool result one request carried, by tool name."""
    return {
        p.function_response.name or "": str((p.function_response.response or {})["result"])
        for c in contents
        for p in (c.parts or [])
        if p.function_response is not None
    }


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            # `show_section` is marked: the pointing line and the scroll in one
            # response, then a second request, carrying the section's lines,
            # answers from them.
            "How does the lipsync stay in step?": [
                reply_and_call(
                    "Here's the timeline.", "show_section", request={"section": "lipsync"}
                ),
                reply(
                    "Two legs write one track — a fast one from the text, an accurate one behind it."
                ),
            ],
            # `perform` is not marked: the line and the wave in one response, and
            # nothing follows it this turn.
            "Wave at me.": reply_and_call(
                "An action. It completes on its own and leaves nothing behind.",
                "perform",
                request={"gesture": "wave_hello"},
            ),
            "How are you different from HeyGen?": [
                reply_and_call(
                    "Here's the comparison.", "show_section", request={"section": "compare"}
                ),
                reply("They stream video. I send the browser a few instructions."),
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

    The female English pair lands on both legs before the greeting audio,
    because the call opens on ``tanya``."""
    async with demo("avatar", _llm()) as rig:
        greeting = await rig.driver.start_session()
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == _GREETING
        check_voice_pair(rig, voice=VOICE, language=LANGUAGE)
        assert _actions(rig) == [], "nothing may be gestured before the page is on"

        await rig.driver.send_ui_event("ready", {})
        await _settle()
        assert _actions(rig) == ["GESTURE_GREET"], _avatar_messages(rig)

        # Once per session: a client that reconnects and re-announces must not
        # re-greet in the middle of a sentence.
        await rig.driver.send_ui_event("ready", {})
        await _settle()
        assert _actions(rig) == ["GESTURE_GREET"], _avatar_messages(rig)


async def test_a_question_scrolls_the_page_to_the_section_it_is_answered_from() -> None:
    """The documentation moves first, and only an id and a heading travel.

    The page holds the prose — it is the link target from the library's README
    and has to read on its own — so the wire carries the section the answer is
    coming from and nothing else. The model chooses an id; the heading is looked
    up in ``content.py``, so it cannot scroll the reader to a heading the page
    does not have.

    ``show_section`` is marked, so the answer is a second request of the same
    turn — and that request carries the section's lines, which is what the
    answer is made from."""
    llm = _llm()
    async with demo("avatar", llm) as rig:
        await rig.driver.start_session()
        before = len(llm.captured_contents)
        turn = await rig.driver.user_says("How does the lipsync stay in step?")
        check_turn(rig, turn, units=2)
        assert len(llm.captured_contents) - before == 2
        handed = _results(llm.captured_contents[-1])["show_section"]
        assert "The clock starts at the first sound of the reply." in handed, handed

        assert rig.actions() == ["show_section"], rig.actions()
        section = rig.command("show_section")
        assert section["id"] == "lipsync"
        assert section["title"] == "How the mouth stays in sync"
        # The prose stays on the page: nothing but the id and the heading travels.
        assert set(section) == {"id", "title"}, section


async def test_the_video_avatar_question_scrolls_to_the_comparison() -> None:
    """ "How is this different from HeyGen?" is the first question people ask, so
    it has its own section and the brain can scroll to it by id."""
    async with demo("avatar", _llm()) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("How are you different from HeyGen?")
        check_turn(rig, turn, units=2)
        section = rig.command("show_section")
        assert section == {"id": "compare", "title": "Compared with video avatar services"}


def test_everything_the_brain_is_handed_to_say_is_short_sentences() -> None:
    """The length control, pinned where it actually lives.

    The prompt asks for short sentences, and the model kept to it until a tool
    handed back a paragraph — the material an answer arrives with is what gets
    read aloud, at the length it arrived. So the fixed lines and every section's
    notes stay short enough that reading them verbatim is still a short turn."""
    lines = {"greeting": _GREETING, "sign-off": _SIGN_OFF}
    lines.update({f"notes[{s.id}]": s.notes for s in SECTIONS})
    for name, text in lines.items():
        for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
            words = len(sentence.split())
            assert words <= 14, f"{name}: {words} words — {sentence!r}"


async def test_the_face_picked_before_the_call_is_the_voice_the_opener_uses() -> None:
    """The pairing, asserted where it is actually decided.

    A face and a voice are one choice. The visitor makes it on the strip before dialling and it rides
    the connect request; the brain has to apply it before the opener is
    synthesised, because a greeting in the other speaker's voice is the whole
    defect this arrangement exists to remove.

    ``tushar`` is male and the default face is female — so a brain that ignored
    ``init`` and dressed every call as the default would still produce audio,
    and this is the assertion that catches it."""
    async with demo("avatar", _llm()) as rig:
        greeting = await rig.driver.start_session(
            init={"surface": "avatar-web", "avatar": "tushar"}
        )
        assert greeting is not None and greeting.text == _GREETING
        check_voice_pair(rig, voice="omnivoice/gaurav", language="en")

        # Exactly one, and before the greeting. A second would mean something
        # still moves the voice mid-call, which is the thing that was removed.
        configs = [r.config for r in rig.driver.requests if isinstance(r, ConfigureFrame)]
        voices = [c.tts.voice for c in configs if c.tts and c.tts.voice]
        assert voices == ["omnivoice/gaurav"], voices
        # Both language legs, because `Config` refuses a half-stated pair and
        # this is the check that the demo did not learn to send one anyway.
        only = configs[0]
        assert only.tts is not None and only.stt is not None
        assert only.tts.language == "en" and only.stt.language == "en"
        assert only.stt.patience == 2, only.stt


async def test_tess_speaks_in_her_own_kokoro_voice() -> None:
    """tess and tanya are both American and female, and both kokoro. A table that
    gave tess tanya's voice would pass every gender check, so this pins hers."""
    async with demo("avatar", _llm()) as rig:
        await rig.driver.start_session(init={"surface": "avatar-web", "avatar": "tess"})
        check_voice_pair(rig, voice="kokoro/sarah", language="en")


async def test_an_unknown_face_wears_the_default_in_its_own_voice() -> None:
    """The payload is browser-supplied on a public page, so a stale build or a
    hand-edited request must produce a working call rather than a failed one —
    and the face it falls back to must arrive with that face's voice, not the
    agent's."""
    async with demo("avatar", _llm()) as rig:
        await rig.driver.start_session(init={"avatar": "not-a-face"})
        check_voice_pair(rig, voice=VOICE, language="en")


async def test_a_gesture_is_one_action_on_the_wire_and_holds_no_state() -> None:
    """A gesture completes on its own, so the wire carries one action and no state
    — the brain leaves states to the pipeline, which infers them itself.

    ``perform`` is not marked: the line that explains the gesture and the gesture
    go out in one response, and the model is not asked again after it."""
    llm = _llm()
    async with demo("avatar", llm) as rig:
        await rig.driver.start_session()
        before = len(llm.captured_contents)
        turn = await rig.driver.user_says("Wave at me.")
        check_turn(rig, turn, units=1)
        assert len(llm.captured_contents) - before == 1, "an unmarked tool took a second request"

        # No greeting wave in this test (the page never announced itself), so
        # this is the only action on the wire.
        assert _actions(rig) == ["GESTURE_GREET"], _avatar_messages(rig)
        assert _states(rig) == [], _avatar_messages(rig)


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

        await rig.driver.send_ui_event("pick_avatar", {"key": "tushar"})
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


async def test_the_demo_says_goodbye_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Past the cap, every later stimulus is silence — not a second goodbye.

    Both stimuli that check the clock reach the sign-off, and one of them is not
    hypothetical: the runtime ticks idle a few seconds after the goodbye
    finishes, on every capped call. Measured before this guard, on a real
    session — the line was spoken at 124s and again at 140s, over a session the
    brain had already ended."""
    monkeypatch.setattr(brain_module, "_LIMIT_S", 0.0)
    async with demo("avatar", _llm()) as rig:
        await rig.driver.start_session()
        first = await rig.driver.user_says("Anything at all.")
        assert first is not None and first.units[0].text == _SIGN_OFF

        again = await rig.driver.user_idle()
        assert not (again and again.units), "the demo said goodbye a second time"

        once_more = await rig.driver.user_says("Still here.")
        assert not (once_more and once_more.units), "the demo said goodbye a third time"


async def test_a_gesture_made_in_silence_is_still_said() -> None:
    """The prompt has the model speak with every call; this is the turn where it
    did not. The brain names the gesture the visitor just saw — one request, no
    second ask — and the line never reaches the model's context."""
    llm = ScriptedGemini(
        {
            "Can you nod?": call("perform", request={"gesture": "nod"}),
            "Nice.": reply("Thanks."),
        }
    )
    async with demo("avatar", llm) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("Can you nod?")
        check_turn(rig, turn, units=1)
        assert [u.text for u in turn.units] == ["That's a nod."]
        assert _actions(rig) == ["ACK_NOD"], _avatar_messages(rig)
        assert len(llm.captured_contents) == 1, "a silent turn asked the model again"

        await rig.driver.user_says("Nice.")
        spoken = " ".join(
            part.text or ""
            for content in llm.captured_contents[-1]
            if content.role == "model"
            for part in content.parts or []
        )
        assert "That's a nod." not in spoken, "the brain's line reached the context"
