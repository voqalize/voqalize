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
from typing import Any

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedOpenAI, call, reply, reply_and_call, tool_results_of

from voqalize.conformance import VoqalizeDriver
from voqalize.sdk.wire import ConfigureFrame

from ._harness import DemoRig, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.property import homes as h  # noqa: E402
from voqalize_demos._loaded.property.brain import REJOIN, PropertyBrain  # noqa: E402
from voqalize_demos._loaded.property.lines import GREETING  # noqa: E402
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


def _brain(rig: DemoRig) -> PropertyBrain:
    brain = rig.brain
    assert isinstance(brain, PropertyBrain)
    return brain


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
    s = h.Search(
        city="bengaluru", deal="buy", bhk=[2, 3], budget_max=15000000, office="cedarline", max_km=8
    )
    first = h.search(s)[0]["id"]
    return ScriptedOpenAI(
        {
            _ASK: [
                reply_and_call(
                    "Let me narrow that down.",
                    "search_homes",
                    city="bengaluru",
                    deal="buy",
                    bhk=[2, 3],
                    budget_max=15000000,
                    office="Cedarline Tech Park",
                    max_km=8,
                ),
                reply(f"{{show: {first}}} The closest one is a short drive from your office."),
            ],
            "Compare the first two.": [
                call("compare_homes", listing_ids=["BLR-101", "BLR-105"]),
                reply("Kosha Meadows is cheaper; Aranya is closer to the metro."),
            ],
            "What would the EMI be on the first one?": [
                call("estimate_emi", listing_id="BLR-101"),
                reply("About ninety-one thousand a month over twenty years."),
            ],
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
        (result,) = tool_results_of(llm.captured_inputs[-1], "search_homes")
        assert f"{len(expected)} homes match" in result
        assert expected[0]["id"] in result
        (cue,) = _cues(rig)
        assert cue["move"] == "listings.show" and cue["args"] == [expected[0]["id"]]
        assert "{" not in turn.text


async def test_the_guide_compares_works_out_the_emi_and_shortlists() -> None:
    llm = _guide()
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/listings"})
        check_turn(rig, await rig.driver.user_says("Compare the first two."))
        assert _moves(rig, "compare.show")[0]["args"] == {"ids": ["BLR-101", "BLR-105"]}
        (rows,) = tool_results_of(llm.captured_inputs[-1], "compare_homes")
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
        (said,) = tool_results_of(llm.captured_inputs[-1], "estimate_emi")
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
            "Saturday afternoon?": [
                call("visit_slots", listing_id="BLR-101", day="saturday", part="afternoon"),
                reply("Saturday afternoon has a few free slots."),
            ],
            "The first one. I'm Ravi, two of us.": [
                call("propose_visit", listing_id="BLR-101", slot=slot, name="Ravi", visitors=2),
                reply("Shall I book it for Ravi, two visitors?"),
            ],
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/listing/BLR-101", "lang": "en"})
        check_turn(rig, await rig.driver.user_says("Saturday afternoon?"))
        (shown,) = _moves(rig, "visit.slots")
        assert shown["args"] == {"listing_id": "BLR-101", "day": day, "part": "afternoon"}
        (free,) = tool_results_of(llm.captured_inputs[-1], "visit_slots")
        assert slot in free
        # The sales team's own bookings are never offered.
        for booked in h.PROJECTS["kosha-aranya"]["team"]["booked"]["sat"]:
            assert f"{day}T{booked}" not in free

        check_turn(rig, await rig.driver.user_says("The first one. I'm Ravi, two of us."))
        assert not _moves(rig, "visit.book"), "booked before the buyer said yes"
        assert _brain(rig).pending is not None

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
        assert h.reference("BLR-101", slot) in text
        assert h.PROJECTS["kosha-aranya"]["team"]["contact"] in text
        assert len(llm.requests) == requests, "the yes and the outcome needed no model call"
        assert f"kosha-aranya|{slot}" in _brain(rig).taken


async def test_a_slot_the_team_has_taken_cannot_be_held() -> None:
    saturday = next(d for d in h.visit_days() if d.weekday() == 5)
    taken = f"{saturday.isoformat()}T10:00"
    llm = ScriptedOpenAI(
        {
            "Ten o'clock Saturday, I'm Ravi.": [
                call("propose_visit", listing_id="BLR-101", slot=taken, name="Ravi"),
                reply("That one is taken."),
            ]
        }
    )
    async with demo("property", llm) as rig:
        await rig.driver.start_session(init={"page": "/listing/BLR-101"})
        await rig.driver.user_says("Ten o'clock Saturday, I'm Ravi.")
        (said,) = tool_results_of(llm.captured_inputs[-1], "propose_visit")
        assert "not a free slot" in said
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
            tenant_id="demo",
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
        before = built[-1]
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
