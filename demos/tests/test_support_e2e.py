"""The Returns Assistant demo, end to end over the wire — no network, no LLM key.

The real ``SupportBrain`` — the shipping ``demos/support/backend/brain.py``, its
real prompt, its real ten tools, its real order catalog — hosted on a real
``brain_server`` socket and driven by the conformance ``VoqalizeDriver``, with only
the *model* scripted. See ``tests/_harness.py`` for what every demo's e2e proves.

Support is the demo that also earns a **browser→brain** test: the photo the
shopper captures arrives as an RTVI client message and folds into the context
without taking the floor — an upload must never put the assistant's voice over
someone still working the camera. What answers it is ``on_user_idle``, once the
shopper is quiet: the leg nothing else in the suite covers, and the reason this
brain arms an idle window at all.

Run: ``cd demos && uv run pytest tests/test_support_e2e.py``
"""

from __future__ import annotations

import asyncio
import base64

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

from voqalize.sdk.wire import ConfigureFrame

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.support.brain import _GREETING, _IDLE_MS  # noqa: E402

VOICE = "omnivoice/gaurav"
LANGUAGE = "en"

# A one-pixel PNG. The brain base64-decodes the data URL before handing the bytes
# to the model, so this has to be real base64 — but not a real photo, since the
# model that would look at it is scripted.
_PIXEL = base64.b64encode(bytes.fromhex("89504e470d0a1a0a")).decode()
PHOTO_DATA_URL = f"data:image/png;base64,{_PIXEL}"


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            "My earbuds from last week keep cutting out.": [
                reply_and_call(
                    "Let me pull that order up.",
                    "open_order",
                    action={"order_id": "VQ-10588"},
                ),
                reply("I see the BT Mic Pro and the Sonic buds on order VQ-10588."),
            ],
            "The Sonic buds. I want to send them back.": [
                reply_and_call(
                    "Starting the return.",
                    "start_return",
                    action={
                        "order_id": "VQ-10588",
                        "item_id": "buds-sonic",
                        "reason": "Audio cuts out intermittently",
                    },
                ),
                reply_and_call("Could you show me the box?", "request_photo"),
                reply("Thanks — hold the box up to the camera."),
            ],
            # The photo takes no floor (see ``SupportBrain.on_rtvi``); the idle
            # tick that follows it is what opens the turn, and the photo's own
            # verify instruction is then the newest thing said — so the key is the
            # distinctive phrase inside it, matched as a substring.
            "Verify it now": [
                reply_and_call(
                    "Checking the photo.",
                    "set_photo_check",
                    result={
                        "matches": True,
                        "box_present": True,
                        "note": "Retail box visible, seal intact",
                    },
                ),
                reply_and_call(
                    "That works.",
                    "fill_return_form",
                    action={
                        "reason": "Audio cuts out intermittently",
                        "condition": "Opened — defective",
                        "refund_method": "original_payment",
                    },
                ),
                reply("Photo checks out — your return form is filled in."),
            ],
        }
    )


async def test_greeting_and_voice_reach_the_wire() -> None:
    """The assistant greets, and its declared male English voice lands on **both**
    legs before the greeting audio does."""
    async with demo("support", _llm()) as rig:
        greeting = await rig.driver.start_session()
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == _GREETING
        check_voice_pair(rig, voice=VOICE, language=LANGUAGE)


async def test_the_return_flow_drives_the_screen() -> None:
    """Two spoken turns, each a tool round-trip, with the exact ``ui-command``
    payloads ``/orders`` renders — including the two tools the second turn fires
    inside one bracket, which is what puts the camera on screen."""
    async with demo("support", _llm()) as rig:
        await rig.driver.start_session()

        t1 = await rig.driver.user_says("My earbuds from last week keep cutting out.")
        check_turn(rig, t1, units=2)

        t2 = await rig.driver.user_says("The Sonic buds. I want to send them back.")
        check_turn(rig, t2, units=3)

        assert rig.actions() == [
            "open_order",
            "start_return",
            "request_photo",
        ], rig.actions()

        assert rig.command("open_order")["order_id"] == "VQ-10588"

        started = rig.command("start_return")
        assert started["order_id"] == "VQ-10588"
        # The browser highlights the row by item id; the brain resolves it against
        # the real catalog, so an id that stops existing fails here, not on screen.
        assert started["item_id"] == "buds-sonic"
        assert started["reason"] == "Audio cuts out intermittently"


async def test_the_idle_window_reaches_the_wire() -> None:
    """The assistant asks Voqalize to tell it when the shopper goes quiet.

    Idle detection is off unless a brain asks for it, and without it the photo
    below could never be answered: an upload is answered on the next idle
    stimulus, and a session that gets no idle stimulus never answers one."""
    async with demo("support", _llm()) as rig:
        await rig.driver.start_session()

    configs = [r.config for r in rig.driver.requests if isinstance(r, ConfigureFrame)]
    timeouts = [c.idle.timeout_ms for c in configs if c.idle is not None]
    assert timeouts == [_IDLE_MS], configs


async def test_a_photo_lands_silently_and_the_next_idle_answers_it() -> None:
    """The browser→brain path: a captured photo folds into the context via
    ``on_rtvi`` — no floor taken, no screen command, because a shopper working the
    camera is not a shopper to be talked over. The verdict comes on the next idle
    tick, without the shopper having to announce the upload, and that is where the
    verification tools run."""
    async with demo("support", _llm()) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("The Sonic buds. I want to send them back.")
        before = len(rig.driver.ui_commands)

        await rig.driver.send_client_message(
            "photo_upload",
            {"image": PHOTO_DATA_URL, "item_id": "buds-sonic"},
        )
        assert len(rig.driver.ui_commands) == before, "photo_upload drove the screen"
        await asyncio.sleep(0.1)

        # The shopper says nothing at all — they uploaded, and that is their answer.
        turn = await rig.driver.user_idle(level=1, idle_ms=_IDLE_MS)
        check_turn(rig, turn, units=3)

        check = rig.command("set_photo_check")
        assert check["matches"] is True
        assert check["box_present"] is True
        # `passed` is the brain's own conjunction, not something the model returns.
        assert check["passed"] is True

        form = rig.command("fill_return_form")
        assert form["reason"] == "Audio cuts out intermittently"
        assert form["refund_method"] == "original_payment"


async def test_a_quiet_shopper_with_nothing_pending_is_left_alone() -> None:
    """Silence is the default, and it is what makes the hook safe to arm.

    A shopper reading their screen is not a shopper to be prompted. The assistant
    takes the floor on an idle tick only when the screen owes them a reply —
    every other tick it says nothing, however many times Voqalize raises one."""
    async with demo("support", _llm()) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("The Sonic buds. I want to send them back.")

        for level in (1, 2, 3):
            turn = await rig.driver.user_idle(level=level, idle_ms=_IDLE_MS, timeout=1.0)
            assert turn.units == [], f"level {level} spoke: {[u.text for u in turn.units]}"


async def test_the_photo_turn_is_prompted_over_the_heard_transcript() -> None:
    """The verification call is not a fresh conversation: the brain rebuilds the
    working context from what Voqalize heard — the shopper's own turn still in
    it — and the photo, folded in via ``on_rtvi``, is what the model actually
    reads last."""
    llm = _llm()
    async with demo("support", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("The Sonic buds. I want to send them back.")
        await rig.driver.send_client_message(
            "photo_upload",
            {"image": PHOTO_DATA_URL, "item_id": "buds-sonic"},
        )
        await asyncio.sleep(0.1)
        await rig.driver.user_idle(level=1, idle_ms=_IDLE_MS)

    # One call per turn — the second call is the one the photo rides into.
    photo_turn = llm.captured_contents[-1]

    last = photo_turn[-1]
    assert last.role == "user"
    parts = last.parts or []
    assert parts[0].inline_data is not None, "the captured image never reached the model"
    assert "Verify it now" in (parts[-1].text or "")

    # The heard conversation is still in there, not replaced by the photo.
    spoken_texts = [
        "".join(p.text or "" for p in (c.parts or []) if p.text)
        for c in photo_turn
        if c.role == "user"
    ]
    assert "The Sonic buds. I want to send them back." in spoken_texts
