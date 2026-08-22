"""The Returns Assistant demo, end to end over the wire — no network, no LLM key.

The real ``SupportBrain`` — the shipping ``demos/support/backend/brain.py``, its
real prompt, its real eleven tools, its real order catalog — hosted on a real
``brain_server`` socket and driven by the conformance ``VoqalizeDriver``, with only
the *model* scripted. See ``tests/_harness.py`` for what every demo's e2e proves.

Support is the demo that also earns a **browser→brain** test: the photo the
shopper captures arrives as an RTVI client message, and the brain answers it on
the interaction Voqalize minted for that message. That path has no spoken turn to
hang an assertion on, so nothing else in the suite covers it.

Run: ``cd demos && uv run pytest tests/test_support_e2e.py``
"""

from __future__ import annotations

import base64

from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, reply, reply_and_call

from ._harness import check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.support.brain import _GREETING  # noqa: E402

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
                reply_and_call("Let me pull that order up.", "open_order", order_id="VQ-10588"),
                reply("I see the BT Mic Pro and the Sonic buds on order VQ-10588."),
            ],
            "The Sonic buds. I want to send them back.": [
                reply_and_call(
                    "Starting the return.",
                    "start_return",
                    order_id="VQ-10588",
                    item_id="buds-sonic",
                    reason="Audio cuts out intermittently",
                ),
                reply_and_call("Could you show me the box?", "request_photo"),
                reply("Thanks — hold the box up to the camera."),
            ],
            # The photo turn arrives as a client message, not speech: the brain
            # sends the image plus a verify instruction as the user turn, so the
            # key is the distinctive phrase in that instruction.
            "Verify it now": [
                reply_and_call(
                    "Checking the photo.",
                    "set_photo_check",
                    matches=True,
                    box_present=True,
                    note="Retail box visible, seal intact",
                ),
                reply_and_call(
                    "That works.",
                    "fill_return_form",
                    reason="Audio cuts out intermittently",
                    condition="Opened — defective",
                    refund_method="original_payment",
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
    """Two spoken turns, each a tool round-trip, with the exact ``ui_command``
    payloads ``/orders`` renders — including the two tools the second turn fires
    inside one bracket, which is what puts the camera on screen."""
    async with demo("support", _llm()) as rig:
        await rig.driver.start_session()

        t1 = await rig.driver.user_says("My earbuds from last week keep cutting out.")
        check_turn(rig, t1, inferences=2)

        t2 = await rig.driver.user_says("The Sonic buds. I want to send them back.")
        check_turn(rig, t2, inferences=3)

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


async def test_an_uploaded_photo_takes_the_floor_and_answers() -> None:
    """The browser→brain path: a captured photo arrives as an RTVI client message
    on its own interaction, and the brain answers *on that interaction*.

    This is the leg with no user speech behind it — if the brain answered on the
    wrong interaction, or never took the floor, the shopper would hold a box up to
    a silent camera. The tool loop must run here exactly as it does for speech."""
    async with demo("support", _llm()) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("The Sonic buds. I want to send them back.")

        photo = await rig.driver.client_message(
            "photo_upload",
            {"image": PHOTO_DATA_URL, "item_id": "buds-sonic"},
        )
        check_turn(rig, photo, inferences=3)

        check = rig.command("set_photo_check")
        assert check["matches"] is True
        assert check["box_present"] is True
        # `passed` is the brain's own conjunction, not something the model returns.
        assert check["passed"] is True

        form = rig.command("fill_return_form")
        assert form["reason"] == "Audio cuts out intermittently"
        assert form["refund_method"] == "original_payment"


async def test_the_photo_turn_is_prompted_over_the_heard_transcript() -> None:
    """The verification turn is not a fresh conversation: the brain rebuilds the
    working context from what Voqalize heard, then appends the image. So the model
    sees the spoken turn that started the return, and the photo lands last."""
    llm = _llm()
    async with demo("support", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("The Sonic buds. I want to send them back.")
        await rig.driver.client_message(
            "photo_upload",
            {"image": PHOTO_DATA_URL, "item_id": "buds-sonic"},
        )

    # Calls 1-3 are the spoken turn; call 4 opens the photo turn.
    photo_turn = llm.captured_contents[3]
    roles = [c.role for c in photo_turn]
    assert roles[0] == "user", roles
    spoken = "".join(p.text or "" for p in (photo_turn[0].parts or []))
    assert spoken == "The Sonic buds. I want to send them back."

    last = photo_turn[-1]
    assert last.role == "user"
    parts = last.parts or []
    assert parts[0].inline_data is not None, "the captured image never reached the model"
    assert "Verify it now" in (parts[-1].text or "")
