"""The Petwell website demo — Tushar at its front desk — end to end over the wire,
no network, no LLM key.

The real ``PetwellBrain`` — the shipping ``demos/petwell/backend/brain.py``, its
real prompt, its real tools, its real branch catalog — hosted on a real
``brain_server`` socket and driven by the conformance ``VoqalizeDriver``, with only
the *model* scripted. See ``tests/_harness.py`` for what every demo's e2e proves.

**Only ``show_slots`` carries ``@needs_result_now``** — which times are still
free is something only the slot book knows, so that turn is two requests: the
call, then the times offered. Every other tool shows what the model named from
its prompt and says its line with the call, one request per turn.

The browser→brain leg is everything the visitor does on the page — every
click, each form field once they pause typing — and all of it is recorded
quietly: a visitor driving the page is never talked at. What they did reaches
the model as context, ahead of whatever they say next.

Language follows the visitor the way the kiosk's does: ``switch_language`` only
records the switch, the brain moves both legs after the turn and says a written
line in the new language, and Hindi in English letters is caught in Python.

Run: ``cd demos && uv run pytest tests/test_petwell_e2e.py``
"""

from __future__ import annotations

import asyncio
import datetime as dt

from google.genai import types
from voqalize_demos.discovery import discover
from voqalize_demos.testing import Reply, ScriptedGemini, call, reply, reply_and_call

from ._harness import DemoRig, _configs, _last, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.petwell.app_events import (  # noqa: E402
    BookingRestarted,
    ServicePicked,
    SlotPicked,
    VisitTypePicked,
)
from voqalize_demos._loaded.petwell.brain import (  # noqa: E402
    BookingUpdate,
    ChooseSlot,
    PetwellBrain,
)
from voqalize_demos._loaded.petwell.catalog import slots_for  # noqa: E402
from voqalize_demos._loaded.petwell.language import GREETING, SWITCH_LINE  # noqa: E402

VOICE = "omnivoice/gaurav"
LANGUAGE = "en"

# Always a bookable day that is not today, so "past times today" never trims it.
TOMORROW = (dt.datetime.now(dt.UTC) + dt.timedelta(hours=5, minutes=30)).date() + dt.timedelta(
    days=1
)
DAY = TOMORROW.isoformat()
FREE = slots_for("mum-powai", DAY, "clinic")


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
            # One sentence answers four steps: one call carries all four, under one line.
            "I want to get my dog vaccinated at your Powai branch.": Reply(
                text="Happy to help — a vaccination at Petwell Powai. Which day suits you?",
                calls=(
                    (
                        "update_booking",
                        {
                            "update": {
                                "visit_type": "clinic",
                                "city": "Mumbai",
                                "branch_id": "mum-powai",
                                "service_id": "vaccination",
                            }
                        },
                    ),
                ),
            ),
            # The one read: the call, then — with the free times in hand — the offer.
            "Tomorrow please.": [
                reply_and_call("Let me check tomorrow.", "show_slots", query={"date": DAY}),
                reply(f"Tomorrow I have {FREE[0]} or {FREE[1]} free. Which works?"),
            ],
            "The first one.": reply_and_call(
                "Done. May I have your name and your pet's name?",
                "choose_slot",
                action={"date": DAY, "time": FREE[0]},
            ),
            "I'm Riya and he's Bruno, a beagle. 98200 12345.": Reply(
                text="Thanks Riya. Please check the summary and tap Send Request.",
                calls=(
                    (
                        "fill_details",
                        {
                            "action": {
                                "owner_name": "Riya",
                                "pet_name": "Bruno",
                                "pet_type": "dog",
                                "phone": "9820012345",
                                "notes": "Annual vaccination",
                            }
                        },
                    ),
                    ("show_review", {}),
                ),
            ),
            "What's my reference?": reply("It's PW-123456 — Powai will call you shortly."),
            "My dog ate rat poison!": reply_and_call(
                "Please come in now — the helpline is on your screen.",
                "show_emergency",
                query={"city": "Mumbai"},
            ),
            "Book me in Kolkata.": reply_and_call(
                "Our Kolkata hospital opens soon — could another city work?",
                "update_booking",
                update={"city": "Kolkata"},
            ),
        }
    )


async def test_greeting_and_voice_reach_the_wire() -> None:
    """The desk greets, and its declared English voice lands on **both** legs
    before the greeting audio does."""
    async with demo("petwell", _llm()) as rig:
        greeting = await rig.driver.start_session()
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == GREETING["English"]
        check_voice_pair(rig, voice=VOICE, language=LANGUAGE)


async def test_a_clinic_booking_drives_the_screen_to_send_request() -> None:
    """The whole clinic flow, by voice: the screen moves under every line, the
    slot read takes the one extra request, and Send Request — the visitor's own
    tap — is recorded quietly, so the desk knows the reference when asked."""
    llm = _llm()
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session()

        before = len(llm.captured_contents)
        t1 = await rig.driver.user_says("I want to get my dog vaccinated at your Powai branch.")
        check_turn(rig, t1, units=1)
        assert len(llm.captured_contents) - before == 1, "an unmarked tool took a second request"

        before = len(llm.captured_contents)
        t2 = await rig.driver.user_says("Tomorrow please.")
        check_turn(rig, t2)
        assert len(llm.captured_contents) - before == 2, "the slot read did not hold the turn"
        assert FREE[0] in _results(llm.captured_contents[-1])["show_slots"]

        await rig.driver.user_says("The first one.")
        await rig.driver.user_says("I'm Riya and he's Bruno, a beagle. 98200 12345.")

        assert rig.actions() == [
            "start_booking",
            "choose_city",
            "choose_branch",
            "choose_service",
            "show_slots",
            "choose_slot",
            "fill_details",
            "show_review",
        ], rig.actions()
        slots = rig.command("show_slots")
        assert slots["branch_id"] == "mum-powai" and slots["date"] == DAY
        assert slots["times"] == FREE
        assert rig.command("choose_slot") == {"date": DAY, "time": FREE[0]}
        details = rig.command("fill_details")
        assert details["pet_name"] == "Bruno" and details["phone"] == "9820012345"

        sent = len(rig.driver.ui_commands)
        await rig.driver.send_ui_event(
            "appointment_requested",
            {"ref": "PW-123456", "owner_name": "Riya", "pet_name": "Bruno", "phone": "9820012345"},
        )
        await asyncio.sleep(0.1)
        assert len(rig.driver.ui_commands) == sent, "Send Request drove the screen"
        quiet = await rig.driver.user_idle(level=1, idle_ms=3000, timeout=1.0)
        assert quiet.units == [], "the desk spoke over a visitor's own tap"
        turn = await rig.driver.user_says("What's my reference?")
        check_turn(rig, turn, units=1)
        told = [
            p.text or ""
            for c in llm.captured_contents[-1]
            if c.role == "user"
            for p in (c.parts or [])
        ]
        note = next(t for t in told if "Send Request" in t)
        assert "PW-123456" in note and "Petwell Powai" in note, note
        # The screen line in front of the question says the request went out.
        screen = [t for t in told if t.startswith("[SCREEN NOW")][-1]
        assert "request SENT, reference PW-123456" in screen, screen


async def test_a_time_that_is_not_free_is_refused() -> None:
    """``choose_slot`` checks the slot book: a taken time is an error the model
    reads, and the screen does not move."""
    taken = next(
        f"{h:02d}:{m:02d}" for h in range(9, 20) for m in (0, 30) if f"{h:02d}:{m:02d}" not in FREE
    )
    llm = ScriptedGemini(
        {
            "Powai, vaccination.": Reply(
                text="Sure.",
                calls=(
                    (
                        "update_booking",
                        {"update": {"visit_type": "clinic", "branch_id": "mum-powai"}},
                    ),
                ),
            ),
            "Book the taken one.": reply_and_call(
                "Booking that.", "choose_slot", action={"date": DAY, "time": taken}
            ),
            "Okay.": reply("Sorry, that one's gone."),
        }
    )
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Powai, vaccination.")
        await rig.driver.user_says("Book the taken one.")
        assert "choose_slot" not in rig.actions()
        await rig.driver.user_says("Okay.")
        assert "not free" in _results(llm.captured_contents[-1])["choose_slot"]


async def test_an_emergency_opens_the_helpline_instead_of_booking() -> None:
    """A pet in danger is not booked: the emergency panel opens with the
    region's helpline and that city's 24x7 branches."""
    async with demo("petwell", _llm()) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("My dog ate rat poison!")
        check_turn(rig, turn, units=1)
        sos = rig.command("show_emergency")
        assert sos["city"] == "Mumbai"
        assert sos["helpline"] == "+91 90000 02222"
        assert sos["branch_ids"] == ["mum-mahalaxmi"]


async def test_an_opening_soon_city_shows_but_cannot_be_booked() -> None:
    """Kolkata is on screen, flagged opening soon; its branch refuses a booking."""
    async with demo("petwell", _llm()) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Book me in Kolkata.")
        assert rig.command("choose_city") == {"city": "Kolkata"}
        brain = rig.brain
        assert isinstance(brain, PetwellBrain)
        refused = await brain.update_booking(BookingUpdate(branch_id="kol-ballygunge"))
        assert "NOT DONE" in refused and "opening soon" in refused, refused
        assert brain.branch_id is None


async def test_a_tap_is_recorded_quietly_and_used_on_the_next_turn() -> None:
    """A branch tapped on screen changes the desk's picture of the screen and
    says nothing; when the visitor next speaks, the desk carries on from it."""
    llm = ScriptedGemini(
        {
            "Clinic visit in Mumbai.": Reply(
                text="Which branch is closest?",
                calls=(("update_booking", {"update": {"visit_type": "clinic", "city": "Mumbai"}}),),
            ),
            "What next?": reply("Churchgate it is — what's the visit for?"),
        }
    )
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Clinic visit in Mumbai.")

        await rig.driver.send_ui_event("branch_picked", {"branch_id": "mum-churchgate"})
        await asyncio.sleep(0.1)
        quiet = await rig.driver.user_idle(level=1, idle_ms=3000, timeout=1.0)
        assert quiet.units == [], [u.text for u in quiet.units]
        brain = rig.brain
        assert isinstance(brain, PetwellBrain) and brain.branch_id == "mum-churchgate"

        await rig.driver.user_says("What next?")
        screen = [t for t in _user_lines(llm.captured_contents[-1]) if t.startswith("[SCREEN NOW")]
        assert "branch: Petwell Churchgate" in screen[-1], screen[-1]


async def test_a_branch_chosen_in_silence_is_still_said() -> None:
    """The model picks the branch and says nothing: the brain says the branch's
    own line, with no second request."""
    llm = ScriptedGemini(
        {
            "Powai.": call("update_booking", update={"branch_id": "mum-powai"}),
        }
    )
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session()
        before = len(llm.captured_contents)
        turn = await rig.driver.user_says("Powai.")
        check_turn(rig, turn, units=1)
        (line,) = (u.text for u in turn.units)
        assert line == "Petwell Powai it is. What's the visit for?", line
        assert len(llm.captured_contents) - before == 1, "a silent turn asked the model again"


# ─── The website ───────────────────────────────────────────────────────────────


def _legs(rig: DemoRig) -> tuple[str, str, str]:
    """The voice, the spoken language and the heard language now on the wire."""
    configs = _configs(rig)
    return (
        _last(configs, lambda c: c.tts.voice if c.tts else None),
        _last(configs, lambda c: c.tts.language if c.tts else None),
        _last(configs, lambda c: c.stt.language if c.stt else None),
    )


async def test_the_desk_moves_the_visitor_around_the_site() -> None:
    """Browsing is not booking: a branch question points at the locations page,
    a health question opens the Health Hub article it is about."""
    llm = ScriptedGemini(
        {
            "Where is your Lucknow branch?": reply_and_call(
                "Our Lucknow branch is in Gomti Nagar.", "show_branches", action={"city": "lucknow"}
            ),
            "My puppy is not vaccinated, is parvo dangerous?": reply_and_call(
                "Yes — here's our article on parvo.",
                "open_article",
                action={"article_id": "parvovirus"},
            ),
            "Show me your services.": reply_and_call(
                "Here are our services.", "navigate", action={"page": "services"}
            ),
        }
    )
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Where is your Lucknow branch?")
        await rig.driver.user_says("My puppy is not vaccinated, is parvo dangerous?")
        await rig.driver.user_says("Show me your services.")
        assert rig.actions() == ["show_branches", "open_article", "navigate"], rig.actions()
        assert rig.command("show_branches") == {"city": "Lucknow"}
        assert rig.command("open_article") == {"article_id": "parvovirus"}
        assert rig.command("navigate") == {"page": "services"}


async def test_every_click_and_field_reaches_the_desk_and_none_is_answered() -> None:
    """The reported gap: the visitor typed their name and the desk never knew.
    Every click and every field they pause on reaches the desk — page, booking
    choices, typing — and none of it makes the desk speak. The next time they
    talk to it, it already knows."""
    llm = ScriptedGemini({"What do you need from me?": reply("Just your pet's name and phone.")})
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session()
        for event, payload in (
            ("article_opened", {"article_id": "parvovirus"}),
            ("booking_opened", {"service_id": "vaccination"}),
            ("city_picked", {"city": "Mumbai"}),
            ("branch_picked", {"branch_id": "mum-powai"}),
            ("slot_picked", {"date": DAY, "time": FREE[0]}),
            ("detail_edited", {"field": "owner_name", "value": "Abhishek"}),
            ("detail_edited", {"field": "notes", "value": "Due for his booster"}),
        ):
            await rig.driver.send_ui_event(event, payload)
        await asyncio.sleep(0.2)
        quiet = await rig.driver.user_idle(level=1, idle_ms=3000, timeout=1.0)
        assert quiet.units == [], "a visitor driving the page was talked at"
        assert rig.actions() == [], "the visitor's clicks drove the screen from the brain"

        brain = rig.brain
        assert isinstance(brain, PetwellBrain)
        assert brain.details == {"owner_name": "Abhishek", "notes": "Due for his booster"}
        assert brain.booking_step() == "details"

        await rig.driver.user_says("What do you need from me?")
        told = _user_lines(llm.captured_contents[-1])
        assert any("typed their owner name: 'Abhishek'" in t for t in told), told
        screen = [t for t in told if t.startswith("[SCREEN NOW")][-1]
        assert "owner name 'Abhishek'" in screen, screen
        assert "details still needed: pet name, phone" in screen, screen


async def test_the_review_waits_for_every_required_field_including_the_message() -> None:
    """The message is mandatory: the desk will not show the review until the
    owner's name, pet's name, phone and message are on the form."""
    async with demo("petwell", ScriptedGemini({})) as rig:
        await rig.driver.start_session()
        brain = rig.brain
        assert isinstance(brain, PetwellBrain)
        await brain.update_booking(BookingUpdate(visit_type="clinic", branch_id="mum-powai"))
        for field, value in (
            ("owner_name", "Riya"),
            ("pet_name", "Bruno"),
            ("phone", "9820012345"),
        ):
            await rig.driver.send_ui_event("detail_edited", {"field": field, "value": value})
        await asyncio.sleep(0.1)
        refused = await brain.show_review()
        assert "NOT DONE" in refused and "message" in refused, refused
        assert "show_review" not in rig.actions()

        await rig.driver.send_ui_event("detail_edited", {"field": "notes", "value": "Limping"})
        await asyncio.sleep(0.1)
        shown = await brain.show_review()
        await asyncio.sleep(0.1)
        assert "review_shown" in shown and "show_review" in rig.actions(), shown


# ─── Language ──────────────────────────────────────────────────────────────────


async def test_the_page_can_open_the_call_in_hindi() -> None:
    """The page's language rides the connect request: Tushar greets in Hindi and
    both legs are Hindi before his first word."""
    async with demo("petwell", ScriptedGemini({})) as rig:
        greeting = await rig.driver.start_session(init={"language": "Hindi"})
        assert greeting is not None and greeting.text == GREETING["Hindi"]
        check_voice_pair(rig, voice=VOICE, language="hi")


async def test_a_language_the_page_does_not_offer_opens_in_english() -> None:
    async with demo("petwell", ScriptedGemini({})) as rig:
        greeting = await rig.driver.start_session(init={"language": "Klingon"})
        assert greeting is not None and greeting.text == GREETING["English"]
        check_voice_pair(rig, voice=VOICE, language="en")


async def test_the_switch_line_is_said_in_the_new_language_after_the_voice_moves() -> None:
    """The model calls switch_language alone; the brain moves both legs, then says
    a written line in Tamil, in the new voice — one model request, and the page
    is told to stay English."""
    heard = "Naan Tamil la pesalama?"
    llm = ScriptedGemini({heard: call("switch_language", to={"language": "Tamil"})})
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session()
        before = len(llm.captured_contents)
        turn = await rig.driver.user_says(heard)
        assert [u.text for u in turn.units] == [SWITCH_LINE["Tamil"]]
        assert _legs(rig) == (VOICE, "ta", "ta")
        assert len(llm.captured_contents) - before == 1, "the switch line asked the model"
        assert rig.command("language_changed") == {"language": "Tamil", "screen_language": "en"}


async def test_hindi_in_english_letters_moves_both_legs_and_the_page() -> None:
    """Hindi heard by the English recognizer is caught in Python: both legs move
    before the model runs, and the website follows into Hindi."""
    heard = "Mera kutta bimar hai, mujhe appointment chahiye."
    llm = ScriptedGemini({heard: reply("ज़रूर, क्लिनिक विज़िट या घर पर?")})
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says(heard)
        brain = rig.brain
        assert isinstance(brain, PetwellBrain) and brain.language == "Hindi"
        assert _legs(rig) == (VOICE, "hi", "hi")
        assert rig.command("language_changed") == {"language": "Hindi", "screen_language": "hi"}


async def test_english_heard_in_hindi_goes_back_to_english() -> None:
    llm = ScriptedGemini({"": reply("Sure.")})
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session(init={"language": "Hindi"})
        await rig.driver.user_says("आई वांट टू बुक एन अपॉइंटमेंट फॉर माय डॉग")
        brain = rig.brain
        assert isinstance(brain, PetwellBrain) and brain.language == "English"
        assert _legs(rig) == (VOICE, "en", "en")


async def test_a_garbled_english_turn_is_switched_without_being_asked() -> None:
    """The local call that did not switch: a Hindi opener reached the English
    recognizer as "Uh much" and the desk answered in English. Nobody picks a
    language here, so the desk has to hear it — the model calls switch_language
    alone on that one turn, and the visitor is answered in Hindi, by the Hindi
    voice, with the page following."""
    llm = ScriptedGemini({"Uh much": call("switch_language", to={"language": "Hindi"})})
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session()
        turn = await rig.driver.user_says("Uh much")
        assert [u.text for u in turn.units] == [SWITCH_LINE["Hindi"]]
        assert _legs(rig) == (VOICE, "hi", "hi")
        assert rig.command("language_changed") == {"language": "Hindi", "screen_language": "hi"}


def test_the_prompt_teaches_both_directions_and_no_picker() -> None:
    """Switching is the model's to notice, so the prompt carries the kiosk's
    teaching: garbled English means another language, English spelled in another
    script means English, and when unsure ask in both."""
    brain = PetwellBrain(client=ScriptedGemini({}))  # pyright: ignore[reportArgumentType]
    prompt = brain.system_instruction
    for section in (
        "HOW TO TELL THEY ARE NOT SPEAKING ENGLISH",
        "HOW TO TELL THEY HAVE GONE BACK TO ENGLISH",
        "SURE, OR NOT SURE",
        "Uh much",
        "nobody picks a language on the page",
    ):
        assert section in prompt, section


async def test_there_is_no_language_event_from_the_page() -> None:
    """A language event the page might still send is ignored: nothing moves."""
    async with demo("petwell", ScriptedGemini({})) as rig:
        await rig.driver.start_session()
        await rig.driver.send_ui_event("language_picked", {"language": "Hindi"})
        await asyncio.sleep(0.1)
        assert _legs(rig) == (VOICE, "en", "en")


async def test_a_silent_turn_in_hindi_is_covered_in_hindi() -> None:
    """The fallback line follows the call's language: a turn that moved the page
    and said nothing is covered with a written Hindi line, not the English one."""
    llm = ScriptedGemini({"पवई": call("update_booking", update={"branch_id": "mum-powai"})})
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session(init={"language": "Hindi"})
        turn = await rig.driver.user_says("पवई")
        (line,) = (u.text for u in turn.units)
        assert line != "Petwell Powai it is. What's the visit for?"
        assert any("\u0900" <= ch <= "\u097f" for ch in line), line


def test_the_health_hub_ids_match_the_page() -> None:
    """The brain opens articles by id and the page renders them from its own copy
    (``frontend/src/hub.ts``), so the two lists of ids must be the same list."""
    import re
    from pathlib import Path

    from voqalize_demos._loaded.petwell.hub import ARTICLES

    page = Path(__file__).resolve().parents[1] / "petwell" / "frontend" / "src" / "hub.ts"
    ids_on_page = re.findall(r"^    id: '([a-z0-9-]+)',$", page.read_text(), re.M)
    assert ids_on_page == [a["id"] for a in ARTICLES]
    dental = {"periodontal-disease", "brushing-teeth", "dental-abscess", "tooth-extraction"}
    assert dental <= set(ids_on_page)


# ─── Grounding: what is said has to match what is on screen ───────────────────


def _user_lines(contents: list[types.Content]) -> list[str]:
    return [p.text or "" for c in contents if c.role == "user" for p in (c.parts or [])]


async def test_a_branch_claimed_but_never_chosen_is_shown_as_not_chosen() -> None:
    """The reported call: the desk said "I've started the booking at the Hyderabad
    branch" with no call behind it, and the screen sat on location. Every turn now
    opens with the screen as it actually is, so the next request is told the
    branch is NOT CHOSEN — whatever was said before."""
    llm = ScriptedGemini(
        {
            "Mumbai please.": Reply(
                text="Done — I've selected our Powai branch for you.",
                calls=(("update_booking", {"update": {"visit_type": "clinic", "city": "Mumbai"}}),),
            ),
            "The screen did not change.": reply("Sorry — which branch would you like?"),
        }
    )
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Mumbai please.")
        await rig.driver.user_says("The screen did not change.")
        screen = [t for t in _user_lines(llm.captured_contents[-1]) if t.startswith("[SCREEN NOW")]
        assert screen, "no screen line in front of the turn"
        latest = screen[-1]
        assert "city: Mumbai" in latest and "branch: NOT CHOSEN" in latest, latest
        assert "LOCATION — choose the branch" in latest, latest


async def test_a_city_with_one_branch_selects_it_on_screen() -> None:
    """Nothing to ask in Hyderabad, so the branch is selected in the same call —
    the screen moves on without waiting on a branch the model may never name."""
    llm = ScriptedGemini(
        {
            "Hyderabad.": Reply(
                text="Our Jubilee Hills hospital. What's the visit for?",
                calls=(
                    (
                        "update_booking",
                        {"update": {"visit_type": "clinic", "city": "Hyderabad"}},
                    ),
                ),
            )
        }
    )
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Hyderabad.")
        assert rig.actions() == ["start_booking", "choose_city", "choose_branch"], rig.actions()
        assert rig.command("choose_branch") == {"branch_id": "hyd-jubilee-hills"}
        brain = rig.brain
        assert isinstance(brain, PetwellBrain) and brain.booking_step() == "service"


async def test_a_city_petwell_is_not_in_is_answered_with_the_nearest_one() -> None:
    """The reported hallucination: asked about Chennai, the desk offered
    "Hyderabad or Bengaluru". The prompt states what Petwell has — every branch,
    and the nearest Petwell city for each region — and names no other city; a
    booking anywhere else is refused with NOT DONE, the screen untouched."""
    brain = PetwellBrain(client=ScriptedGemini({}))  # pyright: ignore[reportArgumentType]
    prompt = brain.system_instruction
    assert "this is every Petwell hospital" in prompt
    assert "South India → Hyderabad" in prompt
    assert "SAY WHAT YOU HAVE DONE" in prompt
    for elsewhere in ("Bengaluru", "Bangalore", "Chennai", "Pune"):
        assert elsewhere not in prompt, f"the prompt names {elsewhere}"

    llm = ScriptedGemini(
        {"Bengaluru.": reply_and_call("Checking.", "update_booking", update={"city": "Bengaluru"})}
    )
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Bengaluru.")
        assert rig.actions() == [], rig.actions()
        await rig.driver.user_says("Okay.")
        result = _results(llm.captured_contents[-1])["update_booking"]
        assert "NOT DONE" in result and "nearest Petwell city" in result, result


async def test_a_reason_before_a_branch_keeps_the_branch_missing() -> None:
    """A reason named before the branch is kept, and the tool says plainly that
    the branch is still to choose — the page stays on location."""
    llm = ScriptedGemini(
        {
            "My dog has ticks, Mumbai.": Reply(
                text="Skin and allergy, in Mumbai — which branch?",
                calls=(
                    (
                        "update_booking",
                        {
                            "update": {
                                "visit_type": "clinic",
                                "city": "Mumbai",
                                "service_id": "skin",
                            }
                        },
                    ),
                ),
            ),
            "Powai.": reply_and_call("Powai.", "update_booking", update={"branch_id": "mum-powai"}),
        }
    )
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("My dog has ticks, Mumbai.")
        await rig.driver.user_says("Powai.")
        first = next(
            str((p.function_response.response or {})["result"])
            for c in llm.captured_contents[-1]
            for p in (c.parts or [])
            if p.function_response is not None and p.function_response.name == "update_booking"
        )
        assert "'branch': 'NOT CHOSEN'" in first and "Skin & allergy" in first, first
        brain = rig.brain
        assert isinstance(brain, PetwellBrain) and brain.booking_step() == "slot"


async def test_mixed_speech_right_after_a_switch_does_not_flip_the_language() -> None:
    """The reported call flipped Tamil → Hindi → English → Tamil in two minutes.
    After a switch the desk's own English check waits two turns, so one sentence
    with English in it does not move the call back."""
    english_in_devanagari = "आई वांट टू बुक एन अपॉइंटमेंट फॉर माय डॉग"
    llm = ScriptedGemini(
        {
            "Mujhe Hindi mein baat karni hai.": call("switch_language", to={"language": "Hindi"}),
            "": reply("ज़रूर।"),
        }
    )
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Mujhe Hindi mein baat karni hai.")
        brain = rig.brain
        assert isinstance(brain, PetwellBrain) and brain.language == "Hindi"
        for _ in range(2):
            await rig.driver.user_says(english_in_devanagari)
            assert brain.language == "Hindi", "a mixed turn right after a switch moved it"
        await rig.driver.user_says(english_in_devanagari)
        assert brain.language == "English", "a settled call should still follow plain English"


async def test_the_desk_drops_what_the_page_drops() -> None:
    """The desk's picture follows the page's own setters: a new visit type drops
    a reason that does not fit it and the chosen time, a new reason drops the
    time, and a restart puts the visit back to a clinic visit."""
    brain = PetwellBrain(client=ScriptedGemini({}))  # pyright: ignore[reportArgumentType]
    brain.panel_open = True
    brain.city, brain.branch_id, brain.service_id = "Mumbai", "mum-powai", "vaccination"
    brain.apply_event(SlotPicked(date=DAY, time=FREE[0]))
    assert brain.booking_step() == "details"

    brain.apply_event(ServicePicked(service_id="dental"))
    assert brain.time is None and brain.service_id == "dental"

    brain.apply_event(SlotPicked(date=DAY, time=FREE[0]))
    brain.apply_event(VisitTypePicked(visit_type="home"))
    assert brain.service_id is None, "a clinic reason survived the switch to a home visit"
    assert brain.time is None, "a clinic time survived the switch to a home visit"

    brain.apply_event(BookingRestarted())
    assert brain.visit_type == "clinic", "the page resets to a clinic visit; the desk did not"


async def test_a_day_outside_the_window_cannot_be_chosen() -> None:
    """choose_slot holds the same window show_slots does — no day past the
    seventh, whatever the slot book would say for it."""
    brain = PetwellBrain(client=ScriptedGemini({}))  # pyright: ignore[reportArgumentType]
    brain.branch_id = "mum-powai"
    far = (TOMORROW + dt.timedelta(days=30)).isoformat()
    result = await brain.choose_slot(
        ChooseSlot(date=far, time=slots_for("mum-powai", far, "clinic")[0])
    )
    assert result.startswith("NOT DONE"), result
    assert brain.time is None


async def test_showing_another_day_drops_the_chosen_time() -> None:
    """The page clears a chosen time when show_slots puts a day's times up; so
    does the desk, or SCREEN NOW would claim a time the page no longer holds."""
    later = (TOMORROW + dt.timedelta(days=1)).isoformat()
    llm = ScriptedGemini(
        {
            "Powai, for a vaccination.": reply_and_call(
                "Petwell Powai it is.",
                "update_booking",
                update={"city": "Mumbai", "branch_id": "mum-powai", "service_id": "vaccination"},
            ),
            "The first one tomorrow.": reply_and_call(
                "Done.", "choose_slot", action={"date": DAY, "time": FREE[0]}
            ),
            "What about the day after?": reply_and_call(
                "Let me look.", "show_slots", query={"date": later}
            ),
        }
    )
    async with demo("petwell", llm) as rig:
        await rig.driver.start_session()
        await rig.driver.user_says("Powai, for a vaccination.")
        await rig.driver.user_says("The first one tomorrow.")
        brain = rig.brain
        assert isinstance(brain, PetwellBrain) and brain.time == FREE[0]
        await rig.driver.user_says("What about the day after?")
        assert brain.time is None and brain.booking_step() == "slot"
