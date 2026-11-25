"""Kosha Homes, end to end: the real brain on a real socket, only the model scripted.

The property guide on ``/`` and ``/listings`` narrows the homes (the sidebar
filters as one Stage move), rings a home with a cue, compares two and works out
an EMI; the visit booker on ``/listing/<id>`` finds the slots where the buyer's
day meets the sales team's diary and books one only after a spoken yes. The
character, voice and languages come from ``demos/property/persona.json``.

Run: ``cd demos && uv run pytest tests/test_property_e2e.py``
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedOpenAI, call, reply, reply_and_call, tool_results_of

from voqalize.conformance import VoqalizeDriver
from voqalize.sdk.openai import _input as _openai_input  # pyright: ignore[reportPrivateUsage]
from voqalize.sdk.wire import ConfigureFrame

from ._harness import DemoRig, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.property import homes as h  # noqa: E402
from voqalize_demos._loaded.property.brain import REJOIN, PropertyBrain  # noqa: E402
from voqalize_demos._loaded.property.lines import GREETING, NUDGE  # noqa: E402
from voqalize_demos._loaded.property.persona import PERSONA  # noqa: E402


@pytest.fixture(autouse=True)
def _no_call_carried_between_tests() -> Iterator[None]:
    """Every test here opens the same session id, and a dropped call is held for
    a redial to rejoin (CONTRACT.md, "Redial"): clear the store around each
    test, so no test rejoins the one before it. Real session ids never repeat."""
    REJOIN.clear()
    yield
    REJOIN.clear()


def _moves(rig: DemoRig, move: str | None = None) -> list[dict[str, Any]]:
    out = [
        dict(c.get("payload") or {})
        for c in rig.driver.ui_commands
        if c.get("command") == "stage_move"
    ]
    return [m for m in out if move is None or m["move"] == move]


def _cues(rig: DemoRig) -> list[dict[str, Any]]:
    return [
        dict(c.get("payload") or {})
        for c in rig.driver.ui_commands
        if c.get("command") == "stage_cue"
    ]


async def _answer(rig: DemoRig, move: str) -> None:
    """The page answers every ``move`` it was sent with ``applied``; the next
    move waits for that, as one at a time on the page."""
    for m in _moves(rig, move):
        await rig.driver.send_ui_event(
            "stage_result",
            {"call_ref": m["call_ref"], "move": move, "outcome": "applied", "detail": "done"},
        )
    await asyncio.sleep(0.1)


async def _phone_typed(rig: DemoRig, listing_id: str = "BLR-101", typed: bool = True) -> None:
    """The visitor typed (or cleared) a mobile number on the visit form: the page
    says only whether one is in, never the number."""
    await rig.driver.send_ui_event(
        "stage_event",
        {
            "name": "visit.phone_typed",
            "by": "visitor",
            "data": {"listing_id": listing_id, "typed": typed},
        },
    )
    await asyncio.sleep(0.1)


def _brain(rig: DemoRig) -> PropertyBrain:
    brain = rig.brain
    assert isinstance(brain, PropertyBrain)
    return brain


def _filed(rig: DemoRig, name: str) -> list[str]:
    """Every result of tool ``name`` in the brain's context. A tool whose answer
    the brain says itself (K0 R4) is read by the model with the next message, so
    its result is not in this turn's one request."""
    return tool_results_of(_openai_input(list(_brain(rig)._history)), name)  # pyright: ignore[reportPrivateUsage]


def _inputs(llm: ScriptedOpenAI, i: int = -1) -> str:
    return json.dumps(llm.captured_inputs[i], ensure_ascii=False)


# ─── Persona and languages ────────────────────────────────────────────────────


async def test_the_guide_greets_in_the_persona_voice() -> None:
    async with demo("property", ScriptedOpenAI()) as rig:
        greeting = await rig.driver.start_session(init={"page": "/", "lang": "en"})
        check_greeting(rig, greeting)
        check_voice_pair(rig, voice=PERSONA.voices["en"], language="en")
        assert greeting is not None and PERSONA.name in greeting.text
        assert "property guide" in greeting.text
        assert _brain(rig).job == "guide"


async def test_hindi_from_the_toggle_moves_both_legs_and_the_greeting() -> None:
    async with demo("property", ScriptedOpenAI()) as rig:
        greeting = await rig.driver.start_session(
            init={"page": "/demos/property/listings", "lang": "hi"}
        )
        check_greeting(rig, greeting)
        check_voice_pair(rig, voice=PERSONA.voices["hi"], language="hi")
        assert greeting is not None and "नमस्ते" in greeting.text


async def test_the_listing_page_lands_on_the_visit_booker() -> None:
    async with demo("property", ScriptedOpenAI()) as rig:
        greeting = await rig.driver.start_session(init={"page": "/listing/BLR-101", "lang": "en"})
        assert greeting is not None
        assert h.LISTINGS["BLR-101"]["title"] in greeting.text
        assert "site visit" in greeting.text
        assert _brain(rig).job == "booker"


async def test_hindi_asked_mid_call_moves_both_legs_and_the_toggle() -> None:
    llm = ScriptedOpenAI(
        {
            "Hindi mein baat karein?": reply_and_call(
                "ज़रूर, अब हिंदी में बात करते हैं।", "set_language", language="hindi"
            )
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        check_turn(rig, await rig.driver.user_says("Hindi mein baat karein?"))
        await asyncio.sleep(0.1)
        check_voice_pair(rig, voice=PERSONA.voices["hi"], language="hi")
        assert rig.command("language_changed") == {"language": "hi"}


async def test_the_tile_toggle_switches_mid_call_and_says_so() -> None:
    async with demo("property", ScriptedOpenAI()) as rig:
        await rig.driver.start_session(init={"page": "/", "lang": "en"})
        await rig.driver.send_ui_event("language_requested", {"language": "hi", "by": "visitor"})
        await asyncio.sleep(0.1)
        check_voice_pair(rig, voice=PERSONA.voices["hi"], language="hi")
        assert rig.command("language_changed") == {"language": "hi"}
        assert _brain(rig).lang == "hi"
        said = await rig.driver.user_idle()
        assert said.text.startswith("ज़रूर")


# ─── The guide ────────────────────────────────────────────────────────────────

_ASK = "Two or three BHK in Bengaluru under 1.5 crore, I work at Cedarline Tech Park."


def _guide() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            _ASK: reply_and_call(
                "Let me narrow that down.",
                "search_homes",
                city="bengaluru",
                deal="buy",
                bhk=[2, 3],
                budget_max=15000000,
                office="Cedarline Tech Park",
                max_km=8,
            ),
            "Compare the first two.": call("compare_homes", listing_ids=["BLR-101", "BLR-105"]),
            "What would the EMI be on the first one?": call("estimate_emi", listing_id="BLR-101"),
            "Save it.": reply_and_call("Saved.", "shortlist_home", listing_id="BLR-101"),
        }
    )


async def test_the_guide_narrows_the_listings_and_rings_a_home() -> None:
    llm = _guide()
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/listings", "lang": "en"})
        turn = await rig.driver.user_says(_ASK)
        check_turn(rig, turn)
        (move,) = _moves(rig, "listings.filter")
        args = move["args"]
        assert args["city"] == "bengaluru" and args["deal"] == "buy"
        assert args["bhk"] == ["2", "3"] and args["budget_max"] == 15000000
        assert args["office"] == "cedarline" and args["max_km"] == 8
        # The count the model reads is the count the page's rule gives.
        expected = h.search(h.Search.of({**args, "bhk": [2, 3]}))
        (result,) = _filed(rig, "search_homes")
        assert f"The screen shows {len(expected)} homes" in result
        assert expected[0]["id"] in result
        # The pitch is the brain's own line, in the same turn: one model request.
        assert f"{len(expected)} homes fit" in turn.text
        assert expected[0]["society"] in turn.text
        assert len(llm.requests) == 1
        (cue,) = _cues(rig)
        assert cue["move"] == "listings.show" and cue["args"] == [expected[0]["id"]]
        assert "{" not in turn.text


async def test_the_guide_compares_works_out_the_emi_and_shortlists() -> None:
    llm = _guide()
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/listings"})
        check_turn(rig, await rig.driver.user_says("Compare the first two."))
        assert _moves(rig, "compare.show")[0]["args"] == {"ids": ["BLR-101", "BLR-105"]}
        (rows,) = _filed(rig, "compare_homes")
        assert h.short(h.LISTINGS["BLR-105"]["price"]) in rows
        await _answer(rig, "compare.show")

        check_turn(rig, await rig.driver.user_says("What would the EMI be on the first one?"))
        (emi_move,) = _moves(rig, "emi.show")
        assert emi_move["args"] == {
            "listing_id": "BLR-101",
            "down_pct": 20,
            "tenure_years": 20,
            "lender": "sahyadri",
        }
        e = h.emi(h.LISTINGS["BLR-101"]["price"], 20, 20, "sahyadri")
        (said,) = _filed(rig, "estimate_emi")
        assert h.inr(e.emi) in said and "8.4%" in said
        await _answer(rig, "emi.show")

        check_turn(rig, await rig.driver.user_says("Save it."))
        assert _moves(rig, "shortlist.set")[0]["args"] == {"listing_id": "BLR-101", "on": True}
        assert _brain(rig).shortlisted == ["BLR-101"]


async def test_what_the_visitor_ticks_is_the_search_the_guide_keeps() -> None:
    llm = ScriptedOpenAI({"Anything ready to move?": reply("Let me look.")})
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/listings"})
        await rig.driver.send_ui_event(
            "stage_event",
            {
                "name": "search.changed",
                "by": "visitor",
                "data": {
                    "summary": "Pune, 2 BHK",
                    "count": 4,
                    "city": "pune",
                    "bhk": [2],
                    "ids": ["PNQ-102"],
                },
            },
        )
        await asyncio.sleep(0.1)
        brain = _brain(rig)
        assert brain.search.city == "pune" and brain.search.bhk == [2]
        await rig.driver.user_says("Anything ready to move?")
        seen = _inputs(llm)
        assert "The visitor changed the search: Pune, 2 BHK" in seen
        assert "Search: Pune, 2 BHK" in seen


async def test_a_ring_the_page_refused_is_told_to_the_model() -> None:
    llm = ScriptedOpenAI(
        {
            "Show me Kosha Aranya.": reply_and_call(
                "Opening it.", "open_listing", listing_id="BLR-101"
            ),
            "So?": reply("It did not open."),
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        await rig.driver.user_says("Show me Kosha Aranya.")
        (move,) = _moves(rig, "site.go")
        await rig.driver.send_ui_event(
            "stage_result",
            {
                "call_ref": move["call_ref"],
                "move": "site.go",
                "outcome": "failed",
                "detail": "the page did not load",
            },
        )
        await asyncio.sleep(0.1)
        await rig.driver.user_says("So?")
        assert "did not land" in _inputs(llm)


# ─── The visit booker ─────────────────────────────────────────────────────────


def _afternoon() -> tuple[str, str]:
    """The first Saturday afternoon slot free at Kosha Aranya, as the page shows it."""
    x = h.LISTINGS["BLR-101"]
    saturday = next(d for d in h.visit_days() if d.weekday() == 5)
    slot = h.free_slots(x, saturday, "afternoon")[0]
    return saturday.isoformat(), slot.id


async def test_the_booker_finds_a_slot_and_books_only_on_yes() -> None:
    day, slot = _afternoon()
    llm = ScriptedOpenAI(
        {
            "Saturday afternoon?": call(
                "visit_slots", listing_id="BLR-101", day="saturday", part="afternoon"
            ),
            "The first one. I'm Ravi, two of us.": call(
                "propose_visit", listing_id="BLR-101", slot=slot, name="Ravi", visitors=2
            ),
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/listing/BLR-101", "lang": "en"})
        check_turn(rig, await rig.driver.user_says("Saturday afternoon?"))
        (shown,) = _moves(rig, "visit.slots")
        assert shown["args"] == {"listing_id": "BLR-101", "day": day, "part": "afternoon"}
        (free,) = _filed(rig, "visit_slots")
        assert slot in free
        # The sales team's own bookings are never offered.
        for booked in h.PROJECTS["kosha-aranya"]["team"]["booked"]["sat"]:
            assert f"{day}T{booked}" not in free

        check_turn(rig, await rig.driver.user_says("The first one. I'm Ravi, two of us."))
        assert not _moves(rig, "visit.book"), "booked before the buyer said yes"
        assert _brain(rig).pending is not None
        # The form fills as said; the mobile number is the visitor's to type (X9).
        (fill,) = _moves(rig, "visit.fill")
        assert fill["args"] == {
            "listing_id": "BLR-101",
            "slot": slot,
            "name": "Ravi",
            "visitors": 2,
        }
        await _answer(rig, "visit.fill")
        await _phone_typed(rig)
        confirm = await rig.driver.user_idle()
        check_turn(rig, confirm, units=1)
        assert "Ravi" in confirm.text and "the two of you" in confirm.text

        yes = await rig.driver.user_says("Yes, please book it.")
        check_turn(rig, yes, units=1)
        assert yes.units[0].text == "Booking it now."
        (book,) = _moves(rig, "visit.book")
        assert book["args"] == {
            "listing_id": "BLR-101",
            "slot": slot,
            "name": "Ravi",
            "visitors": 2,
        }
        requests = len(llm.requests)

        await rig.driver.send_ui_event(
            "stage_result",
            {
                "call_ref": book["call_ref"],
                "move": "visit.book",
                "outcome": "applied",
                "detail": f"visit booked, {h.reference('BLR-101', slot)}",
            },
        )
        await asyncio.sleep(0.1)
        done = await rig.driver.user_idle()
        check_turn(rig, done, units=1)
        text = done.units[0].text
        assert text.startswith("Done, Ravi!"), "a personal confirmation"
        assert h.PROJECTS["kosha-aranya"]["team"]["contact"] in text
        assert len(llm.requests) == requests, "the yes and the outcome needed no model call"
        assert f"kosha-aranya|{slot}" in _brain(rig).taken


async def test_a_slot_the_team_has_taken_cannot_be_held() -> None:
    saturday = next(d for d in h.visit_days() if d.weekday() == 5)
    taken = f"{saturday.isoformat()}T10:00"
    llm = ScriptedOpenAI(
        {
            "Ten o'clock Saturday, I'm Ravi.": call(
                "propose_visit", listing_id="BLR-101", slot=taken, name="Ravi"
            )
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/listing/BLR-101"})
        turn = await rig.driver.user_says("Ten o'clock Saturday, I'm Ravi.")
        (said,) = _filed(rig, "propose_visit")
        assert "not a free slot" in said
        assert turn.text.startswith("That time isn't free.")
        assert _brain(rig).pending is None


async def test_moving_to_a_listing_switches_the_job() -> None:
    llm = ScriptedOpenAI({"Can I see it this weekend?": reply("Which day suits you?")})
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/listings"})
        assert _brain(rig).job == "guide"
        await rig.driver.send_ui_event(
            "stage_event",
            {
                "name": "screen.viewed",
                "by": "visitor",
                "data": {"path": "/listing/HYD-104", "page": "listing", "listing_id": "HYD-104"},
            },
        )
        await asyncio.sleep(0.1)
        assert _brain(rig).job == "booker" and _brain(rig).listing_id == "HYD-104"
        await rig.driver.user_says("Can I see it this weekend?")
        assert "your job here is booking a site visit" in _inputs(llm)


def test_the_page_and_the_brain_share_one_slot_rule() -> None:
    """The reference format and the closed days follow CONTRACT.md."""
    assert h.reference("BLR-104", "2026-11-22T10:30") == "KV-104-221030"
    x = h.LISTINGS["BLR-101"]  # Kosha Aranya: no visits on Wednesdays
    wednesday = next(d for d in h.visit_days() if d.weekday() == 2)
    assert h.day_slots(x, wednesday) is None
    assert h.inr(11400000) == "₹1,14,00,000"
    assert h.short(11400000) == "₹1.14 crore"


# ─── Redial: a call outlives a dropped brain socket ───────────────────────────


def _redials(driver: VoqalizeDriver) -> list[bool | None]:
    return [
        r.config.redial.enabled
        for r in driver.requests
        if isinstance(r, ConfigureFrame) and r.config.redial is not None
    ]


def _stage_moves(driver: VoqalizeDriver, move: str) -> list[dict[str, Any]]:
    return [
        dict(c.get("payload") or {})
        for c in driver.ui_commands
        if c.get("command") == "stage_move" and (c.get("payload") or {}).get("move") == move
    ]


async def test_a_dropped_socket_rejoins_the_call_where_it_was() -> None:
    """Mid-booking: the call started on /listings in English, moved to a
    listing (the booker), switched to Hindi, searched, shortlisted and held a
    visit for a yes; then the brain's socket drops without a hang-up. Karthik
    turned redial on; Voqalize dials again for the same session with the same
    init; the new socket's brain adopts the call — job, listing, language,
    search, shortlist, the held visit and the model's history — says no second
    hello, and the buyer's yes books the visit that was held."""
    from voqalize_demos.discovery import build_for

    from voqalize.conformance import (
        BrainServer,
        DirectConnection,
        generate_keypair,
        mint_voqalize_token,
    )

    day, slot = _afternoon()
    llm = ScriptedOpenAI(
        {
            "Hindi mein baat karein?": reply_and_call(
                "ज़रूर, अब हिंदी में बात करते हैं।", "set_language", language="hindi"
            ),
            "Save it.": reply_and_call("Saved.", "shortlist_home", listing_id="BLR-101"),
            "Saturday afternoon?": [
                call("visit_slots", listing_id="BLR-101", day="saturday", part="afternoon"),
                reply("शनिवार दोपहर कुछ स्लॉट खाली हैं।"),
            ],
            "The first one. I'm Ravi, two of us.": [
                call("propose_visit", listing_id="BLR-101", slot=slot, name="Ravi", visitors=2),
                reply("रवि, दो लोगों के लिए बुक कर दूँ?"),
            ],
            "What did I ask you to save?": reply("Kosha Aranya."),
        }
    )
    build = build_for("property")
    built: list[PropertyBrain] = []

    def _build() -> Any:
        brain = build(llm)  # type: ignore[arg-type]
        built.append(brain)  # type: ignore[arg-type]
        return brain

    keypair = generate_keypair()
    server = BrainServer(_build, host="127.0.0.1", port=0, public_keys=keypair.public_pem)
    port = await server.start()
    sid = "property-redial-e2e"
    init = {"page": "/listings", "lang": "en"}

    def driver() -> VoqalizeDriver:
        token = mint_voqalize_token(
            private_key_pem=keypair.private_pem,
            session_id=sid,
            agent_id="property",
        )
        return VoqalizeDriver(
            DirectConnection(f"ws://127.0.0.1:{port}", sid, token=token),
            session_id=sid,
            default_timeout=10.0,
        )

    first, second = driver(), driver()
    try:
        await first.open()
        greeting = await first.start_session(init=init)
        assert greeting is not None and PERSONA.name in greeting.text
        assert _redials(first) == [True], "redial is turned on with the voice, before the greeting"
        await first.user_says("Hindi mein baat karein?")
        await asyncio.sleep(0.1)
        await first.send_ui_event(
            "stage_event",
            {
                "name": "screen.viewed",
                "by": "visitor",
                "data": {"path": "/listing/BLR-101", "page": "listing", "listing_id": "BLR-101"},
            },
        )
        await asyncio.sleep(0.1)
        await first.user_says("Save it.")
        await first.user_says("Saturday afternoon?")
        await first.user_says("The first one. I'm Ravi, two of us.")
        await first.send_ui_event(
            "stage_event",
            {
                "name": "visit.phone_typed",
                "by": "visitor",
                "data": {"listing_id": "BLR-101", "typed": True},
            },
        )
        await asyncio.sleep(0.1)
        before = built[-1]
        assert before.phone_typed
        assert before.job == "booker" and before.listing_id == "BLR-101"
        assert before.lang == "hi" and before.shortlisted == ["BLR-101"]
        assert before.pending is not None and before.pending.slot == slot
        assert not _stage_moves(first, "visit.book")

        # The socket drops: no End, no close code a hang-up would send.
        await first.aclose()
        for _ in range(50):
            if len(REJOIN):
                break
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.1)
        assert len(REJOIN) == 1, "the dropped call is held for a redial"

        # Voqalize redials: the same session id, the same init.
        await second.open()
        again = await second.start_session(init=init, greeting_timeout=0.5)
        assert again is None, "no second greeting on a rejoined call"
        after = built[-1]
        assert after is not before
        assert after.job == "booker" and after.listing_id == "BLR-101", "the page it moved to"
        assert after.lang == "hi" and after.shortlisted == ["BLR-101"]
        assert after.pending is not None and after.pending.slot == slot, "the held visit"
        assert _redials(second) == [True]
        # Both legs come back in the language the call had moved to, not init's.
        check_voice_pair(
            DemoRig(name="property", server=server, driver=second, _built=[]),
            voice=PERSONA.voices["hi"],
            language="hi",
        )

        requests = len(llm.requests)
        yes = await second.user_says("Yes, please book it.")
        assert yes.units, "the call carried on after the drop"
        (book,) = _stage_moves(second, "visit.book")
        assert book["args"] == {
            "listing_id": "BLR-101",
            "slot": slot,
            "name": "Ravi",
            "visitors": 2,
        }
        assert len(llm.requests) == requests, "the yes to the held visit needed no model call"
        await second.send_ui_event(
            "stage_result",
            {
                "call_ref": book["call_ref"],
                "move": "visit.book",
                "outcome": "applied",
                "detail": f"visit booked, {h.reference('BLR-101', slot)}",
            },
        )
        await asyncio.sleep(0.1)
        assert f"kosha-aranya|{slot}" in after.taken, "the booking in flight landed on this call"

        await second.user_says("What did I ask you to save?")
        last = json.dumps(llm.captured_inputs[-1], ensure_ascii=False)
        assert "Hindi mein baat karein?" in last and "Save it." in last, "the history came across"
        rehello = GREETING["booker"]["hi"].format(
            name=PERSONA.name, title=h.LISTINGS["BLR-101"]["title"]
        )
        assert rehello not in last, "no second hello reached the model's history"
        assert day in last or slot in last
    finally:
        await second.aclose()
        await server.aclose()


async def test_a_redial_that_finds_nothing_starts_fresh_and_a_hang_up_is_let_go() -> None:
    """A redial reaching a process that never held the call (a deploy) carries
    on as a new conversation; a held call is let go two minutes after its
    socket closes (a hang-up looks the same from here), and kept however long
    it runs while the socket is up."""
    from voqalize_demos._loaded.property.rejoin import KEEP_AFTER_DROP_S, KEEP_LIVE_S, Rejoin

    now = [0.0]
    store: Rejoin[object] = Rejoin(clock=lambda: now[0])
    a, b = object(), object()
    store.hold("s1", a)
    store.dropped("s1", b)  # not the brain held: nothing changes
    now[0] = KEEP_AFTER_DROP_S + 1
    assert store.take("s1") is a, "a live call is kept however long it runs"
    store.hold("s1", a)
    store.dropped("s1", a)
    store.dropped("s1", a)  # on_session_end runs at least once: a second run changes nothing
    now[0] += KEEP_AFTER_DROP_S - 1
    assert len(store) == 1
    now[0] += 2
    assert store.take("s1") is None and len(store) == 0, "expired two minutes after the drop"
    assert store.take("never-held") is None
    store.hold("s2", a)
    now[0] += KEEP_LIVE_S + 1
    assert len(store) == 0, "a socket that never reported closing is let go after twelve hours"


async def test_a_redial_after_expiry_starts_a_new_conversation() -> None:
    """A redial that comes after the held call expired finds nothing: the brain
    starts from init and greets, as a new call on the same page would."""
    from voqalize_demos._loaded.property import rejoin

    llm = ScriptedOpenAI(
        {"Save it.": reply_and_call("Saved.", "shortlist_home", listing_id="BLR-101")}
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/listing/BLR-101", "lang": "en"})
        await rig.driver.user_says("Save it.")
        held = _brain(rig)
        assert held.shortlisted == ["BLR-101"]
    # The socket closed; expire it by moving the store's clock on.
    real = REJOIN._clock  # pyright: ignore[reportPrivateUsage]
    try:
        REJOIN._clock = lambda: real() + rejoin.KEEP_AFTER_DROP_S + 1  # pyright: ignore[reportPrivateUsage]
        assert len(REJOIN) == 0
    finally:
        REJOIN._clock = real  # pyright: ignore[reportPrivateUsage]
    async with demo("property", ScriptedOpenAI()) as rig:
        greeting = await rig.driver.start_session(init={"page": "/listing/BLR-101", "lang": "en"})
        check_greeting(rig, greeting)
        fresh = _brain(rig)
        assert fresh is not held and fresh.shortlisted == [] and fresh.pending is None


async def test_no_redial_is_asked_of_a_voqalize_that_does_not_offer_it() -> None:
    """``configure`` raises for redial without the capability: Karthik asks only
    where it is offered, and the call starts the same either way."""
    from voqalize.sdk.wire import Capability

    async with demo("property", ScriptedOpenAI()) as rig:
        rig.driver.capabilities.discard(Capability.REDIAL)
        greeting = await rig.driver.start_session(init={"page": "/", "lang": "en"})
        check_greeting(rig, greeting)
        assert _redials(rig.driver) == []
        check_voice_pair(rig, voice=PERSONA.voices["en"], language="en")


# ─── Amounts in speech, both ways (X8) ────────────────────────────────────────

from voqalize_demos._loaded.property.spoken import (  # noqa: E402
    SpokenAmounts,
    amounts_note,
    implausible,
    parse_amounts,
    speak_text,
)


@pytest.mark.parametrize(
    ("written", "lang", "spoken"),
    [
        # A range with the scale said once is still read wrong by the TTS ("eight rupees to 12 lakh"): each end in full.
        (
            "Homes from ₹1.25 to 1.5 crore.",
            "en",
            "Homes from one point two five to one point five crore rupees.",
        ),
        # Every price over a crore had the shape Voqalize's TTS read as rupees and paise
        # ("₹1.14 crore" → "one rupee and fourteen paisa crore"); since speech 174bd6ef it
        # reads it right, so it goes as written.
        (
            f"BLR-101 is {h.short(11400000)}, 1085 sq ft.",
            "en",
            "BLR-101 is ₹1.14 crore, 1085 sq ft.",
        ),
        ("Under 1.5 crore, two fit.", "en", "Under one point five crore, two fit."),
        ("It's ₹94 lakh.", "en", None),
        (
            "₹42,000 a month, deposit ₹2.5 lakh.",
            "en",
            None,
        ),
        (
            "Homes from ₹80 lakh to ₹1.2 crore.",
            "en",
            None,
        ),
        (
            "Prices of ₹1.14\u20131.5 crore.",
            "en",
            "Prices of one point one four to one point five crore rupees.",
        ),
        (
            "Loan ₹91.2 lakh, total interest ₹1.07 Cr.",
            "en",
            None,
        ),
        ("Rates of 8.25\u20138.9% a year.", "en", "Rates of 8.25% to 8.9% a year."),
        # Plain amounts, percentages, ids, references and times are left to the TTS.
        ("An EMI of ₹88,123 a month at 8.4%, ₹10,507 per sq ft.", "en", None),
        ("Reference KV-104-221030, Saturday 22 Nov at 10:30 am.", "en", None),
        # Hindi: Devanagari scale with the ₹ mark (सवा, डेढ़, साढ़े); any other decimal
        # as whole rupees, never एक दशमलव एक चार करोड़.
        ("यह ₹1.14 करोड़ का है।", "hi", "यह ₹1,14,00,000 का है।"),
        ("यह ₹1.25 crore का है।", "hi", "यह ₹1.25 करोड़ का है।"),
        ("बजट ₹1.5 Cr तक।", "hi", "बजट ₹1.5 करोड़ तक।"),
        ("यह ₹92.5 लाख का है।", "hi", "यह ₹92.5 लाख का है।"),
        ("₹80 लाख से ₹1.2 करोड़ तक।", "hi", "₹80 लाख से ₹1,20,00,000 तक।"),
        ("EMI ₹88,123 महीना, ब्याज 8.4%।", "hi", None),
    ],
)
def test_amounts_are_written_the_way_the_voice_reads_them(
    written: str, lang: str, spoken: str | None
) -> None:
    assert speak_text(written, lang) == (written if spoken is None else spoken)


@pytest.mark.parametrize(
    ("heard", "rupees"),
    [
        # (value, low end of a range or None) for each amount said.
        (
            "Two or three BHK in Bengaluru under 1.5 crore.",
            [(2, None), (3, None), (15000000, None)],
        ),
        ("under 1.5 Cr", [(15000000, None)]),
        ("around 94 lakhs", [(9400000, None)]),
        ("1 to 1.5 crore", [(15000000, 10000000)]),
        ("1-1.5 cr", [(15000000, 10000000)]),
        ("between 80 lakh and 1.2 crore", [(12000000, 8000000)]),
        ("between 1 and 1.5 crore", [(15000000, 10000000)]),
        ("80 lakh and 1.2 crore", [(8000000, None), (12000000, None)]),
        ("one and a half crore", [(15000000, None)]),
        ("dedh crore tak", [(15000000, None)]),
        ("1 crore 25 lakh", [(12500000, None)]),
        ("one point two crore", [(12000000, None)]),
        ("rent around 40 to 50 thousand a month", [(50000, 40000)]),
        ("45k a month", [(45000, None)]),
        ("45 hazaar mahina", [(45000, None)]),
        ("forty two thousand a month", [(42000, None)]),
        ("सवा करोड़ तक", [(12500000, None)]),
        ("90 लाख से सवा करोड़ के बीच", [(12500000, 9000000)]),
        ("पचास हज़ार महीना", [(50000, None)]),
        ("साढ़े तीन लाख deposit", [(350000, None)]),
        ("लगभग ₹\u0967,\u0968\u096b,\u0966\u0966\u0966", [(125000, None)]),
        ("₹1,25,000 and ₹2 lakh", [(125000, None), (200000, None)]),
    ],
)
def test_spoken_amounts_parse_to_rupees(
    heard: str, rupees: list[tuple[float, float | None]]
) -> None:
    assert [(a.value, a.low) for a in parse_amounts(heard)] == rupees


async def test_an_amount_split_across_streamed_chunks_is_still_said_whole() -> None:
    """A model streams tokens: "₹1." then "14 cr" then "ore". The rewrite waits for the
    amount to finish; the unit's start and end pass through as they came."""
    from voqalize.sdk import SpeechChunk, SpeechEnd, SpeechStart

    async def stream() -> Any:
        yield SpeechStart()
        for piece in ["Kosha Aranya is ₹1.", "14 cr", "ore; a rent of ₹42,", "000 a month."]:
            yield SpeechChunk(piece)
        yield SpeechEnd()

    out = [e async for e in SpokenAmounts(lambda: "en").wrap(stream())]
    assert isinstance(out[0], SpeechStart) and isinstance(out[-1], SpeechEnd)
    text = "".join(e.text for e in out if isinstance(e, SpeechChunk))
    assert text == "Kosha Aranya is ₹1.14 crore; a rent of ₹42,000 a month."


def test_an_implausible_budget_is_confirmed_back_never_used() -> None:
    why = implausible({"budget_max": 15}, "buy", ["under 1.5 crore"])
    assert why is not None and why.startswith("Not done")
    assert "₹1,50,00,000" in why and "₹1.5 crore, right?" in why
    rent = implausible({"budget_max": 45}, "rent", ["around 45 thousand a month"])
    assert rent is not None and "₹45,000, right?" in rent
    # A buy budget of a rent's size is not one a buyer means either.
    assert implausible({"budget_max": 45000}, "buy", ["45 thousand"]) is not None
    assert implausible({"budget_min": 10000000, "budget_max": 15000000}, "buy", []) is None
    assert implausible({"budget_max": 45000}, "rent", []) is None
    assert implausible({"budget_max": 45000}, None, []) is None
    assert amounts_note("between 1 and 1.5 crore") == (
        "[Amounts they said, in rupees: '1 and 1.5 crore' = 10000000 to 15000000 rupees.]"
    )
    assert amounts_note("yes please") is None


_BUDGET = "Two BHK in Bengaluru, between 1 and 1.5 crore."
_MISHEARD = "Actually make it under dedh crore."


async def test_amounts_are_spoken_as_words_and_a_wrong_budget_is_confirmed() -> None:
    """Over the wire: the budget he said reaches the model in rupees; the price the model
    writes as "₹1.14 crore" reaches the voice as written (the TTS reads it); and a budget passed as ₹15 for
    "dedh crore" never reaches the listings: the tool asks for "₹1.5 crore" back."""
    s = h.Search(city="bengaluru", bhk=[2], budget_min=10000000, budget_max=15000000)
    first = h.search(s)[0]
    llm = ScriptedOpenAI(
        {
            _BUDGET: reply_and_call(
                "Let me narrow that down.",
                "search_homes",
                city="bengaluru",
                bhk=[2],
                budget_min=10000000,
                budget_max=15000000,
            ),
            _MISHEARD: call("search_homes", budget_max=15),
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/listings", "lang": "en"})
        turn = await rig.driver.user_says(_BUDGET)
        check_turn(rig, turn)
        told = _inputs(llm)
        assert "'1 and 1.5 crore' = 10000000 to 15000000 rupees" in told
        (move,) = _moves(rig, "listings.filter")
        assert move["args"]["budget_min"] == 10000000 and move["args"]["budget_max"] == 15000000
        said = " ".join(u.text for u in turn.units)
        assert speak_text(h.short(first["price"]), "en") in said
        await _answer(rig, "listings.filter")

        turn = await rig.driver.user_says(_MISHEARD)
        result = _filed(rig, "search_homes")[-1]
        assert result.startswith("Not done") and "₹1,50,00,000" in result
        assert len(_moves(rig, "listings.filter")) == 1
        assert _brain(rig).search.budget_max == 15000000
        said = " ".join(u.text for u in turn.units)
        assert "₹1.5 crore, right?" in said


#: A Hindi sentence ends in the danda (U+0964/U+0965, inside the Devanagari block); an
#: amount right before it, or before "?" or ",", is said as it is mid-sentence.
_SENTENCE_END_AMOUNTS = [
    ("hi", "आपका लोन ", "₹13.6 लाख"),
    ("hi", "कुल ", "₹1.25 करोड़"),
    ("hi", "", "₹13.6 लाख"),
    ("hi", "कवर ", "₹10 लाख"),
    ("en", "Your cover is ", "₹10 lakh"),
    ("en", "The total is ", "₹1.5 crore"),
]


@pytest.mark.parametrize(("lang", "before", "amount"), _SENTENCE_END_AMOUNTS)
@pytest.mark.parametrize("end", ["।", "॥", "?", ","])
def test_an_amount_before_the_danda_is_said_as_mid_sentence(
    lang: str, before: str, amount: str, end: str
) -> None:
    rest = " बाकी" if lang == "hi" else " left"
    mid = speak_text(f"{before}{amount}{rest}", lang)
    assert mid.endswith(rest)
    assert speak_text(f"{before}{amount}{end}", lang) == mid.removesuffix(rest) + end


@pytest.mark.parametrize(
    ("written", "spoken"),
    [
        ("₹13.6 लाख।", "₹13,60,000।"),
        ("आपका लोन ₹13.6 लाख॥", "आपका लोन ₹13,60,000॥"),
        ("Your cover is ₹10 lakh।", "Your cover is ₹10 lakh।"),
    ],
)
def test_amounts_before_the_danda(written: str, spoken: str) -> None:
    assert speak_text(written, "hi" if "लाख" in written else "en") == spoken


# ─── Whitespace around a rewritten amount ─────────────────────────────────────

#: Amounts as a piece of streamed speech may start or end with them, with and without ₹.
_WS_AMOUNTS = [
    ("en", "7.2 lakh"),
    ("en", "₹7.2 lakh"),
    ("en", "1.14 crore"),
    ("en", "₹1.14 crore"),
    ("en", "₹8 to 12 lakh"),
    ("en", "Rs 5 lakh"),
    ("hi", "7.2 लाख"),
    ("hi", "₹7.2 लाख"),
    ("hi", "₹1.25 करोड़"),
    ("hi", "₹8 से 12 लाख"),
]


@pytest.mark.parametrize(("lang", "amount"), _WS_AMOUNTS)
@pytest.mark.parametrize(("before", "after"), [(" ", ""), ("", " "), (" ", " "), ("Fees: ", ", ")])
def test_a_rewritten_amount_keeps_the_whitespace_around_it(
    lang: str, amount: str, before: str, after: str
) -> None:
    """The stream is rewritten in pieces, and a piece may start or end with a space: a
    leading space eaten with the amount ran "It costs" into "seven point two lakh"."""
    assert speak_text(f"{before}{amount}{after}", lang) == (
        f"{before}{speak_text(amount, lang)}{after}"
    )


async def _ws_streamed(units: list[list[str]], lang: str) -> str:
    from voqalize.sdk import SpeechChunk, SpeechEnd, SpeechStart

    async def stream() -> Any:
        for unit in units:
            yield SpeechStart()
            for piece in unit:
                yield SpeechChunk(piece)
            yield SpeechEnd()

    out = [e async for e in SpokenAmounts(lambda: lang).wrap(stream())]
    return "".join(e.text for e in out if isinstance(e, SpeechChunk))


@pytest.mark.parametrize(
    ("lang", "sentence"),
    [
        ("en", "It costs 7.2 lakh a year."),
        ("en", "The flat is ₹1.14 crore now."),
        ("hi", "यह ₹7.2 लाख का है।"),
        ("en", "Fees: 7.2 lakh a year."),
        ("hi", "शुल्क: 7.2 लाख है।"),
    ],
)
async def test_every_two_chunk_split_speaks_like_the_whole_sentence(
    lang: str, sentence: str
) -> None:
    """However the model's tokens fall, the voice hears what the whole sentence rewrites to;
    so it does when the amount opens a second unit (" 7.2 lakh a year." after "It costs")."""
    whole = speak_text(sentence, lang)
    for i in range(1, len(sentence)):
        head, tail = sentence[:i], sentence[i:]
        assert await _ws_streamed([[head, tail]], lang) == whole, (head, tail)
        if tail[0] == " " and tail[1] in "₹0123456789":  # an amount starts the second unit
            assert await _ws_streamed([[head], [tail]], lang) == whole, (head, tail)


# ─── The K0 audit: the guide sells, no turn ends silent, the mobile is typed ────
# Each test pins one problem the real-model audit found (FEEDBACK K0; transcripts
# beside the PR). The model is scripted; what is checked is what the brain does
# with its call: the search on screen, what the tool tells the model to say next,
# and the brain's own lines.


async def test_the_guide_greeting_leads_with_the_first_questions() -> None:
    async with demo("property", ScriptedOpenAI()) as rig:
        greeting = await rig.driver.start_session(init={"page": "/", "lang": "en"})
        assert greeting is not None
        assert "buy or rent" in greeting.text and "which city" in greeting.text


async def test_an_office_named_by_its_area_sets_the_commute() -> None:
    """A1/B1: "I work at the tech park in Whitefield" was re-asked as "which tech
    park?" twice and never filtered. The area alone names the office."""
    llm = ScriptedOpenAI(
        {
            "I work in Whitefield.": reply_and_call(
                "Let me sort by your commute.", "search_homes", office="Whitefield"
            )
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        turn = await rig.driver.user_says("I work in Whitefield.")
        (move,) = _moves(rig, "listings.filter")
        assert move["args"]["office"] == "cedarline"
        assert move["args"]["city"] == "bengaluru"
        assert "km from Cedarline Tech Park" in turn.text
        (said,) = _filed(rig, "search_homes")
        assert "never ask which office" in said


async def test_a_crore_budget_is_a_home_to_buy_not_a_question() -> None:
    """C1/F2: "3 BHK in Hyderabad up to 1.5 crore" showed a rental and asked
    "buy or rent?"."""
    llm = ScriptedOpenAI(
        {
            "3 BHK in Hyderabad up to 1.5 crore.": reply_and_call(
                "Let me look.", "search_homes", city="hyderabad", bhk=[3], budget_max=15000000
            )
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/listings"})
        turn = await rig.driver.user_says("3 BHK in Hyderabad up to 1.5 crore.")
        (move,) = _moves(rig, "listings.filter")
        assert move["args"]["deal"] == "buy"
        assert all(h.LISTINGS[i]["deal"] == "buy" for i in _brain(rig).results)
        assert "buy or rent" not in turn.text, "not the next question"
        (said,) = _filed(rig, "search_homes")
        assert "never ask buy or rent" in said


async def test_around_a_budget_offers_a_home_a_little_over_but_shows_the_budget() -> None:
    """A2/E1 and R4 1-2: "about 90 lakh" found nothing at exactly ₹90 lakh. A
    buyer who says "around" is offered a home up to 10% over, said with how far
    over and its price once; the screen keeps exactly the budget they said."""
    said_text = "2 BHK in Bengaluru, budget around 90 lakh."
    llm = ScriptedOpenAI(
        {
            said_text: reply_and_call(
                "Let me look.",
                "search_homes",
                city="bengaluru",
                deal="buy",
                bhk=[2],
                budget_max=9000000,
                around=True,
            )
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        turn = await rig.driver.user_says(said_text)
        (move,) = _moves(rig, "listings.filter")
        assert move["args"]["budget_max"] == 9000000, "the screen shows what they said"
        assert _brain(rig).wanted.budget_max == 9000000
        assert "Palm Grove Residency" in turn.text and "4% over" in turn.text
        assert turn.text.count("₹94 lakh") == 1, "the price said once"
        assert len(llm.requests) == 1


async def test_nothing_fitting_offers_the_nearest_home_and_how_far_over() -> None:
    """E1 and R4 1-2: nothing at ₹85 lakh. The answer names the nearest home and
    how far over it is and asks to widen; the screen and the next search keep the
    budget they said (it was widened to ₹94 lakh on screen before)."""
    llm = ScriptedOpenAI(
        {
            "2 BHK in Bengaluru up to 85 lakh.": reply_and_call(
                "Let me look.",
                "search_homes",
                city="bengaluru",
                deal="buy",
                bhk=[2],
                budget_max=8500000,
            )
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        turn = await rig.driver.user_says("2 BHK in Bengaluru up to 85 lakh.")
        (move,) = _moves(rig, "listings.filter")
        assert move["args"]["budget_max"] == 8500000
        assert _brain(rig).results == []
        assert "Palm Grove Residency" in turn.text and "about 11% over" in turn.text
        assert "raise the budget" in turn.text
        (said,) = _filed(rig, "search_homes")
        assert "BLR-112" in said and "not on screen" in said
        assert _brain(rig).wanted.budget_max == 8500000


async def test_a_stretch_never_leaks_into_the_next_search() -> None:
    """R4 1: "around 1 crore" (nothing near it), then "between 80 lakh and 1.2
    crore": the tool got ₹1.2 crore but the screen showed ₹1.29 crore, carried
    from the stretched search. Every filter is exactly what was said, and "around
    1 crore" is never silently stretched 29%."""
    llm = ScriptedOpenAI(
        {
            "Three BHK in Bangalore, around 1 crore.": reply_and_call(
                "Let me look.",
                "search_homes",
                city="bengaluru",
                bhk=[3],
                budget_max=10000000,
                around=True,
            ),
            "Make it between 80 lakh and 1.2 crore.": call(
                "search_homes", budget_min=8000000, budget_max=12000000
            ),
            "Two or three BHK is fine.": call("search_homes", bhk=[2, 3]),
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        first = await rig.driver.user_says("Three BHK in Bangalore, around 1 crore.")
        assert "Saffron Court" in first.text and "about 29% over" in first.text
        assert "raise the budget" in first.text
        assert first.text.count("₹1.29 crore") == 1, "the price said once"
        await _answer(rig, "listings.filter")
        second = await rig.driver.user_says("Make it between 80 lakh and 1.2 crore.")
        assert "about 8% over" in second.text
        await _answer(rig, "listings.filter")
        third = await rig.driver.user_says("Two or three BHK is fine.")
        filters = [m["args"] for m in _moves(rig, "listings.filter")]
        assert [f["budget_max"] for f in filters] == [10000000, 12000000, 12000000]
        assert [f["budget_min"] for f in filters] == [None, 8000000, 8000000]
        assert "homes fit what you told me" in third.text


async def test_the_pitch_asks_the_next_question_once_then_nudges() -> None:
    """A3/A4: the guide re-asked "which tech park?" after the buyer moved on, and
    never offered a visit. The pitch asks one next question, never the same one
    twice, and once the homes are few, nudges to a site visit."""
    llm = ScriptedOpenAI(
        {
            "Buying in Bengaluru, up to 2 crore.": reply_and_call(
                "Let me look.", "search_homes", city="bengaluru", deal="buy", budget_max=20000000
            ),
            "Ready to move, please.": reply_and_call("Sure.", "search_homes", possession="ready"),
            "Two bedrooms, I work in Whitefield, near a school.": reply_and_call(
                "Narrowing.", "search_homes", bhk=[2], office="Whitefield", school_km=2
            ),
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/"})
        first = await rig.driver.user_says("Buying in Bengaluru, up to 2 crore.")
        assert "How many bedrooms do you need?" in first.text
        await _answer(rig, "listings.filter")
        second = await rig.driver.user_says("Ready to move, please.")
        assert "How many bedrooms" not in second.text, "a question is never asked twice"
        await _answer(rig, "listings.filter")
        third = await rig.driver.user_says("Two bedrooms, I work in Whitefield, near a school.")
        assert any(n in third.text for n in NUDGE["buy"]["en"]), third.text
        best = h.LISTINGS[_brain(rig).results[0]]
        assert best["society"] in third.text


async def test_tell_me_more_opens_the_home_and_describes_it() -> None:
    """R4 3: "Tell me more about the first one" only described it. It opens the
    home on screen, like "Can I see it?", and the brain describes it and asks the
    day, in the same turn."""
    llm = ScriptedOpenAI(
        {
            "Tell me more about the first one.": reply_and_call(
                "Opening it.", "open_listing", listing_id="BLR-112"
            ),
            "Does it have a gym?": call("home_facts", listing_id="BLR-105"),
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/listings"})
        turn = await rig.driver.user_says("Tell me more about the first one.")
        (go,) = _moves(rig, "site.go")
        assert go["args"] == {"path": "/listing/BLR-112"}
        assert "Here's Palm Grove Residency" in turn.text and "sq ft" in turn.text
        assert "Which day would suit you" in turn.text
        assert len(llm.requests) == 1
    # A question about a home asked from the list opens it too.
    REJOIN.clear()
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/listings"})
        await rig.driver.user_says("Does it have a gym?")
        assert _moves(rig, "site.go")[0]["args"] == {"path": "/listing/BLR-105"}


async def test_opening_a_home_offers_the_visit_and_never_stops_there() -> None:
    """B2: "Can I see it?" opened the listing with "I'll open it for you." and
    the call stopped. Opening a home says the home and asks the day."""
    llm = ScriptedOpenAI(
        {
            "Can I see the cheaper one?": reply_and_call(
                "Opening it.", "open_listing", listing_id="PNQ-115"
            )
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/listings"})
        turn = await rig.driver.user_says("Can I see the cheaper one?")
        (said,) = _filed(rig, "open_listing")
        assert "visit booker" in said
        assert turn.text.startswith("Opening it.")
        assert "Which day would suit you" in turn.text
        assert "₹29,000 a month" in turn.text


async def test_compare_names_the_home_that_suits_them_better() -> None:
    """C2: the comparison was read out row by row with no verdict and no next step."""
    llm = ScriptedOpenAI(
        {
            "I work at Cedarline.": reply_and_call("Noted.", "search_homes", office="cedarline"),
            "Compare these two.": call("compare_homes", listing_ids=["BLR-105", "BLR-112"]),
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/listings"})
        await rig.driver.user_says("I work at Cedarline.")
        await _answer(rig, "listings.filter")
        turn = await rig.driver.user_says("Compare these two.")
        assert "Palm Grove Residency suits you better" in turn.text
        assert "2.1 km from Cedarline Tech Park" in turn.text
        assert "site visit" in turn.text
        (said,) = _filed(rig, "compare_homes")
        assert "Carpet area" in said


async def test_two_homes_emis_compared_on_one_screen_move() -> None:
    """C3: two EMIs were two emi.show moves (the second replaced the first) and a
    reply with every figure and no next step."""
    llm = ScriptedOpenAI(
        {
            "Which has the lower EMI with 30 percent down?": call(
                "estimate_emi", listing_id="HYD-110", down_pct=30, also=["HYD-106"]
            )
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/compare"})
        turn = await rig.driver.user_says("Which has the lower EMI with 30 percent down?")
        assert len(_moves(rig, "emi.show")) == 1
        mine = h.emi(h.LISTINGS["HYD-110"]["price"], 30, 20, "sahyadri").emi
        theirs = h.emi(h.LISTINGS["HYD-106"]["price"], 30, 20, "sahyadri").emi
        assert h.inr(mine) in turn.text and h.inr(theirs) in turn.text
        assert "is lower" in turn.text
        assert "EMI" not in turn.text.rsplit(".", 2)[-2], "the nudge after an EMI is a visit"


async def test_a_weekend_visit_offers_both_days() -> None:
    """D1: "this weekend" got "Saturday or Sunday?" instead of the free times."""
    llm = ScriptedOpenAI(
        {"This weekend, any time.": call("visit_slots", listing_id="BLR-101", day="weekend")}
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/listing/BLR-101"})
        turn = await rig.driver.user_says("This weekend, any time.")
        (said,) = _filed(rig, "visit_slots")
        assert "This weekend:" in said and "Saturday" in said and "Sunday" in said
        assert "Saturday" in turn.text and "Sunday" in turn.text
        (shown,) = _moves(rig, "visit.slots")
        assert date.fromisoformat(shown["args"]["day"]).weekday() >= 5


async def test_the_mobile_number_is_typed_never_said_and_one_yes_books() -> None:
    """X9 and D2-D6: the booker never asked for a phone at all, and the outcome was
    a reference read aloud. Now the form fills as said, the Mobile box is the
    visitor's to type, a yes before it is in books nothing, the typed number
    brings the ONE confirmation, and the booked line is personal."""
    _, slot = _afternoon()
    llm = ScriptedOpenAI(
        {
            "The first one. I'm Ravi Kumar, two of us.": call(
                "propose_visit", listing_id="BLR-101", slot=slot, name="Ravi Kumar", visitors=2
            ),
            "My number is 98765 43210.": reply("Please type it in the box instead."),
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/listing/BLR-101"})
        held = await rig.driver.user_says("The first one. I'm Ravi Kumar, two of us.")
        assert "type your mobile number" in held.text and "Ravi" not in held.text
        (said,) = _filed(rig, "propose_visit")
        assert "never say it" in said
        (fill,) = _moves(rig, "visit.fill")
        assert set(fill["args"]) == {"listing_id", "slot", "name", "visitors"}, "no phone sent"
        await _answer(rig, "visit.fill")

        await rig.driver.user_says("My number is 98765 43210.")
        seen = _inputs(llm)
        assert "They said a phone number aloud" in seen

        early = await rig.driver.user_says("Yes, book it.")
        assert "type your mobile number" in early.text
        assert not _moves(rig, "visit.book"), "no booking before the number is typed"

        await _phone_typed(rig)
        confirm = await rig.driver.user_idle()
        assert confirm.text.startswith("Thanks, Ravi")
        assert "the two of you" in confirm.text
        requests = len(llm.requests)

        yes = await rig.driver.user_says("Yes.")
        assert yes.text == "Booking it now."
        (book,) = _moves(rig, "visit.book")
        await rig.driver.send_ui_event(
            "stage_result",
            {
                "call_ref": book["call_ref"],
                "move": "visit.book",
                "outcome": "applied",
                "detail": "ok",
            },
        )
        await asyncio.sleep(0.1)
        done = await rig.driver.user_idle()
        assert done.text.startswith("Done, Ravi!")
        assert "you both" in done.text and "photo ID" in done.text
        assert h.reference("BLR-101", slot) not in done.text, "no code read aloud"
        assert len(llm.requests) == requests, "the confirmation and the outcome are the brain's"


async def test_the_hindi_booking_is_confirmed_in_hindi() -> None:
    """R8 for Kosha: the confirmation and the outcome are whole Hindi sentences,
    the day and time in Hindi too."""
    _, slot = _afternoon()
    llm = ScriptedOpenAI(
        {
            "पहला वाला, मेरा नाम अमित है।": call(
                "propose_visit", listing_id="BLR-101", slot=slot, name="अमित", visitors=1
            )
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/listing/BLR-101", "lang": "hi"})
        held = await rig.driver.user_says("पहला वाला, मेरा नाम अमित है।")
        assert "मोबाइल नंबर टाइप कर दीजिए" in held.text
        await _answer(rig, "visit.fill")
        await _phone_typed(rig)
        confirm = await rig.driver.user_idle()
        assert confirm.text.startswith("धन्यवाद अमित जी")
        assert "शनिवार" in confirm.text and "दोपहर" in confirm.text
        await rig.driver.user_says("हाँ।")
        (book,) = _moves(rig, "visit.book")
        await rig.driver.send_ui_event(
            "stage_result",
            {
                "call_ref": book["call_ref"],
                "move": "visit.book",
                "outcome": "applied",
                "detail": "ok",
            },
        )
        await asyncio.sleep(0.1)
        done = await rig.driver.user_idle()
        assert done.text.startswith("हो गया, अमित जी!")
        assert "शनिवार" in done.text
        assert not any(w in done.text for w in ("booked", "Saturday", "bring"))


async def test_the_name_is_said_once_in_a_hindi_reply() -> None:
    """R4 4: "अमित जी" twice in one turn, once in the model's lead-in and again in
    the brain's line. The brain's line drops the name the model already said,
    and the filled-form line never carries it."""
    _, slot = _afternoon()
    llm = ScriptedOpenAI(
        {
            "शनिवार दोपहर, मैं अमित वर्मा हूँ।": reply_and_call(
                "ठीक है अमित जी।",
                "propose_visit",
                listing_id="BLR-101",
                slot=slot,
                name="अमित वर्मा",
                visitors=2,
            )
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/listing/BLR-101", "lang": "hi"})
        await _phone_typed(rig)
        turn = await rig.driver.user_says("शनिवार दोपहर, मैं अमित वर्मा हूँ।")
        assert turn.text.count("अमित") == 1, turn.text
        assert "बुक कर दूँ?" in turn.text


async def test_the_hindi_pitch_is_short_spoken_hindi_in_one_request() -> None:
    """R4 4-5: a stiff written Hindi lead-in, then a second model request of
    several seconds for the pitch. The lead-in is the model's few words; the
    pitch is the brain's own spoken Hindi line, said in the same turn."""
    llm = ScriptedOpenAI(
        {
            "बेंगलुरु में 2 BHK, बजट 1.2 करोड़ तक।": reply_and_call(
                "एक सेकंड, देखता हूँ।",
                "search_homes",
                city="bengaluru",
                deal="buy",
                bhk=[2],
                budget_max=12000000,
            )
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/", "lang": "hi"})
        turn = await rig.driver.user_says("बेंगलुरु में 2 BHK, बजट 1.2 करोड़ तक।")
        assert len(llm.requests) == 1, "the pitch needs no second model request"
        assert "आपके हिसाब से" in turn.text and "सबसे अच्छा Palm Grove Residency है" in turn.text
        assert "कितने BHK" not in turn.text, "never a question they answered"
        assert "short, warm, conversational Hindi" in llm.captured_instructions[-1]
