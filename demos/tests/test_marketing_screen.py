"""What Tanvi knows of the visitor's screen: the reports the browser sends, the note she reads
before each turn, and where_they_are. No model, no network.

The reports here are the ones the built site actually sends (``window.vq.view()``), at 390px and
at 1440px, for the cases from Samkeet's review: the Plug & Play steps on a phone, with the
animation below them, not on the right; and the retail page scrolled on past the checkout she
showed.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from voqalize_demos.discovery import discover

from voqalize.sdk import UserMessage
from voqalize.sdk.events import RTVIMessage, RTVIType

discover()

from voqalize_demos._loaded.marketing.brain import SITE_EVENTS, TanviBrain  # noqa: E402
from voqalize_demos._loaded.marketing.screen import Screen, Viewing  # noqa: E402
from voqalize_demos._loaded.marketing.site import (  # noqa: E402
    BLOCKS_BY_ID,
    SECTIONS_BY_ID,
    describe,
)

from ._marketing_fakes import (  # noqa: E402, F401
    FakeSession,
    brain_fixture,
    script,
    session_fixture,
    text,
)

VOICE = json.loads(
    (
        Path(__file__).resolve().parents[1]
        / "marketing"
        / "frontend"
        / "src"
        / "data"
        / "voice.json"
    ).read_text()
)

PHONE_WAYS = {
    "device": "phone",
    "layout": "tile",
    "section": "ways",
    "rows": [["ways.pnp_steps"], ["ways.pnp_demo"], ["ways.pnp_facts"]],
    "focus": "ways.pnp_steps",
    "heading": "Two ways to integrate.",
    "progress": 60,
    "showing": ["ways.plug_and_play", "ways.plug_and_play.step2"],
}
DESKTOP_WAYS = {
    **PHONE_WAYS,
    "device": "desktop",
    "layout": "beside",
    "rows": [["ways.tabs"], ["ways.pnp_steps", "ways.pnp_demo"], ["ways.pnp_facts"]],
}
RETAIL = {
    "device": "phone",
    "layout": "tile",
    "page": "retail",
    "rows": [["retail.scene2"]],
    "focus": "retail.scene2",
    "heading": "A checkout that fills itself in.",
    "progress": 34,
}
RETAIL_ON = {
    **RETAIL,
    "rows": [["retail.scene3"]],
    "focus": "retail.scene3",
    "heading": "A swap instead of a refund.",
    "progress": 52,
}


def viewing(**kw: object) -> Viewing:
    return Viewing.model_validate(kw)


def run(coro):
    return asyncio.run(coro)


# ── The blocks the browser names ─────────────────────────────────────────────


def test_every_block_is_a_part_of_a_real_section() -> None:
    assert len(BLOCKS_BY_ID) >= 30
    for b in VOICE["blocks"]:
        assert b["section"] in SECTIONS_BY_ID, b
        assert b["id"] == f"{b['section']}.{b['part']}"
        assert b["does"] and "!" not in b["does"]


def test_the_plug_and_play_steps_and_animation_are_named() -> None:
    for id_ in (
        "ways.pnp_steps",
        "ways.pnp_demo",
        "ways.dev_demo",
        "action.diagram",
        "handled.board",
        "pricing.switches",
    ):
        assert describe(id_), id_
    assert "knowledge base" in (describe("ways.pnp_demo") or "")


# ── The note before her turn ─────────────────────────────────────────────────


def test_on_a_phone_things_are_above_and_below() -> None:
    s = Screen()
    s.update(viewing(**PHONE_WAYS))
    note = s.note() or ""
    assert "a phone" in note and "do not say left or right" in note
    assert "side by side from left to right" not in note
    # The steps first, the animation below them, in the order the visitor sees them.
    assert note.index("Plug & Play steps") < note.index("Below that: The Plug & Play animation")
    assert (
        "What they are reading: The Plug & Play steps, 1 to 5, and a Go to Console button." in note
    )
    assert "Plug & Play step 2" in note  # the animation's step, and the tab


def test_on_a_computer_the_same_blocks_sit_side_by_side() -> None:
    s = Screen()
    s.update(viewing(**DESKTOP_WAYS))
    note = s.note() or ""
    assert "a computer" in note and "column on the left" in note
    assert (
        "side by side from left to right: The Plug & Play steps, 1 to 5, and a Go to Console button; The Plug & Play animation"
        in note
    )


def test_a_note_only_when_the_screen_changed() -> None:
    s = Screen()
    s.update(viewing(**RETAIL))
    assert s.note()
    assert s.note() is None
    s.update(viewing(**RETAIL))
    assert s.note() is None


def test_where_they_went_since_her_last_turn() -> None:
    s = Screen()
    s.update(viewing(**RETAIL))
    s.note()
    s.update(viewing(**RETAIL_ON))
    note = s.note() or ""
    assert "Since your last turn they moved: Scene 3, After the sale." in note
    assert "What they are reading: Scene 3, After the sale." in note
    assert "A swap instead of a refund." in note
    assert "Scene 2" not in note.split("Since your last turn")[1].split(".")[0]


def test_moving_to_another_page_and_what_they_looked_at_before() -> None:
    s = Screen()
    s.update(viewing(**PHONE_WAYS))
    s.note()
    s.update(viewing(**RETAIL))
    s.update(viewing(**RETAIL_ON))
    note = s.note() or ""
    assert (
        "they moved: the Retail and e-commerce page, at Scene 2, Buy; then Scene 3, After the sale."
        in note
    )
    assert "Earlier in this call they looked at the Two ways to integrate section." in note
    assert "Scene 2, Buy" in s.history() and "Plug & Play steps" in s.history()


def test_a_page_with_no_parts_is_named_by_its_heading() -> None:
    s = Screen()
    s.update(
        viewing(
            device="desktop",
            layout="beside",
            path="/privacy",
            title="Privacy policy",
            heading="What we collect",
            progress=40,
        )
    )
    note = s.note() or ""
    assert "the page Privacy policy" in note and '"What we collect"' in note
    assert "No part of it you have words for is in view." in note


def test_ids_the_site_no_longer_has_are_left_out() -> None:
    s = Screen()
    s.update(
        viewing(
            device="phone",
            layout="tile",
            section="ways",
            rows=[["ways.gone"], ["ways.pnp_demo"]],
            focus="ways.gone",
        )
    )
    note = s.note() or ""
    assert "gone" not in note and "At the top: The Plug & Play animation" in note
    assert "What they are reading" not in note


def test_tanvi_alone_in_the_middle() -> None:
    s = Screen()
    s.update(viewing(device="phone", layout="centre"))
    assert "nothing is open beside you" in (s.note() or "")


# ── Through the brain ────────────────────────────────────────────────────────


def test_viewing_arrives_over_rtvi_and_adds_nothing_until_her_turn(brain: TanviBrain) -> None:
    msg = RTVIMessage(type=RTVIType.UI_EVENT, data={"event": "viewing", "payload": PHONE_WAYS})
    assert isinstance(SITE_EVENTS.parse(msg), Viewing)
    before = len(brain._history)  # pyright: ignore[reportPrivateUsage]
    for _ in range(5):  # a scroll is many reports
        run(brain.on_rtvi(brain.session, msg))
    assert len(brain._history) == before  # pyright: ignore[reportPrivateUsage]
    assert brain.screen.now is not None and brain.screen.now.section == "ways"


def test_her_turn_reads_the_screen_after_their_words(
    brain: TanviBrain, session: FakeSession
) -> None:
    run(
        brain.on_rtvi(
            brain.session,
            RTVIMessage(type=RTVIType.UI_EVENT, data={"event": "viewing", "payload": PHONE_WAYS}),
        )
    )
    script(
        brain,
        [text("These are the Plug & Play steps. Do you have a website?")],
        [text("Sure. What else?")],
    )

    async def turn(said: str) -> None:
        async for _ in brain.on_user_message(brain.session, UserMessage(text=said)):
            pass

    run(turn("What's this part about?"))
    texts = [p.text or "" for c in brain._history for p in (c.parts or [])]  # pyright: ignore[reportPrivateUsage]
    said = texts.index("What's this part about?")
    assert texts[said + 1].startswith("(THEIR SCREEN")
    # Nothing moved: the next turn gets no second copy.
    run(turn("Okay."))
    assert (
        sum(
            t.startswith("(THEIR SCREEN")
            for t in [p.text or "" for c in brain._history for p in (c.parts or [])]
        )
        == 1
    )  # pyright: ignore[reportPrivateUsage]


def test_where_they_are_reads_the_screen(brain: TanviBrain) -> None:
    brain.note_for(viewing(**RETAIL))
    brain.note_for(viewing(**RETAIL_ON))
    where = run(brain.where_they_are())
    assert (
        "Retail and e-commerce page" in where
        and "What they are reading: Scene 3, After the sale." in where
    )
    assert (
        "Blocks they have read this call, in order: Scene 2, Buy; Scene 3, After the sale." in where
    )


def test_the_prompt_takes_positions_from_the_screen() -> None:
    from voqalize_demos._loaded.marketing.brain import SYSTEM_INSTRUCTION

    assert "THEIR SCREEN" in SYSTEM_INSTRUCTION
    assert "On a phone, never left or right." in SYSTEM_INSTRUCTION
    assert (
        "on the right?" not in SYSTEM_INSTRUCTION
        and "flight on the right" not in SYSTEM_INSTRUCTION
    )
