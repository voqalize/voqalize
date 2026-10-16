"""Tushar, SendPotion's guide, end to end over the wire — no network, no LLM key.

The real ``SendPotionBrain`` on a real ``brain_server`` socket, driven by the
conformance ``VoqalizeDriver``, with only the model scripted. The knowledge is a
small invented site and blog in the crawl's own shape, put in place of the
committed one, so no test depends on what the crawl found this week.

What this demo earns that others do not:

**Nothing on the page is invented.** A path, a heading, an FAQ and a blog post
are checked before they reach the page; the assertion worth making is on what
crossed the wire, and on what did not.

**The visitor's tabs are his screen.** Which tabs are open and which is in front
reaches the model with what the visitor says, and switching is checked against
that list.

**The booking is the visitor's.** The demo calendar fills as they talk, never
schedules, and what it shows after his turn is talked through in a short quiet
spell.

Run: ``cd demos && uv run pytest tests/test_sendpotion_e2e.py``
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from google.genai import types
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply, reply_and_call

from ._harness import _configs, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.sendpotion import brain as sendpotion  # noqa: E402
from voqalize_demos._loaded.sendpotion import knowledge as kb  # noqa: E402
from voqalize_demos._loaded.sendpotion.brain import (  # noqa: E402
    _BLOG_GREETING,
    _GREETING,
    _IDLE_MS,
    _TALK_THROUGH_MS,
)
from voqalize_demos._loaded.sendpotion.knowledge import (  # noqa: E402
    Faq,
    Knowledge,
    Page,
    Post,
    Section,
)

AGENCY = "https://blog.sendpotion.com/how-agencies-win-clients-1a2b3c"
VSL = "https://blog.sendpotion.com/ten-vsl-mistakes-4d5e6f"

# An invented site in the crawl's shape: the names and figures are ours.
SITE = Knowledge(
    l1="Potion makes personal videos. Plans start at nine dollars (invented for tests).",
    topics={},
    pages={
        "/": Page("/", "Home | Potion", sections=(Section("Clone yourself", "One video."),)),
        "/pricing": Page(
            "/pricing",
            "Pricing | Potion",
            sections=(Section("Pricing plans", "Starter Professional Enterprise"), Section("FAQs")),
            faqs=(Faq("How long can a video be?", "Up to five minutes. Shorter works best."),),
        ),
        "/integrations": Page(
            "/integrations", "Integrations | Potion", sections=(Section("Works with HubSpot"),)
        ),
        "/demo": Page("/demo", "Book a demo — Potion", sections=(Section("Book a demo"),)),
        "/faq": Page(
            "/faq",
            "FAQ | Potion",
            sections=(Section("FAQs"),),
            faqs=(Faq("Can I cancel anytime?", "Yes, from your account."),),
        ),
    },
    posts={
        AGENCY: Post(
            AGENCY,
            "How agencies win clients with video",
            summary="Agency outreach with personal videos.",
            use_cases=("agency growth", "cold outreach"),
            headings=("Why video", "The three-step sequence"),
        ),
        VSL: Post(
            VSL,
            "Ten video sales letter mistakes",
            summary="What to avoid in a VSL.",
            use_cases=("video sales letter",),
            headings=("Mistake one",),
        ),
    },
)

PRICING_PAGE = {
    "site": "site",
    "url": "https://sendpotion.com/pricing/",
    "path": "/pricing/",
    "title": "Pricing | Potion",
    "kind": "page",
    "headings": ["Pricing plans", "FAQs"],
    "faqs": ["How long can a video be?"],
    "plans": ["Starter", "Professional", "Enterprise"],
}


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every session reads the invented site, and he never nods unless a test
    asks him to: a nod is a unit of its own."""
    monkeypatch.setattr(kb, "KNOWLEDGE", SITE)
    monkeypatch.setattr(sendpotion, "ACK_RATE", 0.0)
    yield


def _results(contents: list[types.Content]) -> dict[str, str]:
    return {
        p.function_response.name or "": str((p.function_response.response or {})["result"])
        for c in contents
        for p in (c.parts or [])
        if p.function_response is not None
    }


def _texts(contents: list[types.Content]) -> str:
    return "\n".join(p.text or "" for c in contents for p in (c.parts or []))


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            "How much is it?": reply_and_call(
                "Plans start small. See the plans side by side?",
                "navigate",
                request={"path": "/pricing/", "heading": "pricing plans"},
            ),
            "Take me to the moon page.": reply_and_call(
                "Here it is.", "navigate", request={"path": "/moon"}
            ),
            "Show me HubSpot.": reply_and_call(
                "Yes, it works with HubSpot.",
                "navigate",
                request={"path": "/integrations", "heading": "HubSpot logo"},
            ),
            "Show me the Professional plan.": reply_and_call(
                "Most teams land here.", "show_section", request={"text": "Professional"}
            ),
            "Show me the testimonials.": reply_and_call(
                "Here.", "show_section", request={"heading": "Testimonials"}
            ),
            "How long can videos be?": reply_and_call(
                "Up to five minutes.", "open_faq", request={"question": "how long can a video"}
            ),
            "Show me the plans, flat.": reply_and_call(
                "Here are the plans.", "show_section", heading="Pricing plans"
            ),
            "I run an agency and want more clients.": [
                call("find_blog_posts", request={"use_case": "agency growth cold outreach"}),
                reply_and_call(
                    "Outreach is your use case. I've opened the best post for you.",
                    "recommend_posts",
                    request={
                        "heading": "For agency outreach",
                        "posts": [
                            {"url": AGENCY + "/", "why": "How agencies win clients"},
                            {"url": "https://blog.sendpotion.com/invented-999", "why": "Made up"},
                            {"url": VSL, "why": "Sharper sales videos"},
                        ],
                    },
                ),
            ],
            "Take me to the sequence part.": reply_and_call(
                "It's three steps.",
                "open_post",
                request={"url": AGENCY, "heading": "three-step sequence"},
            ),
            "I'd like a demo.": reply_and_call(
                "Happy to set that up. Here's the calendar.", "book_demo", request={}
            ),
            "calendar is on their screen": reply(
                "Tuesday, Wednesday and Thursday are open. Which suits you?"
            ),
            "Tuesday at three, I'm Jane, jane@acme.test.": reply_and_call(
                "I've put jane at acme dot test. Is that right?",
                "book_demo",
                request={
                    "day": "tuesday october 20",
                    "time": "3:00pm",
                    "name": "Jane",
                    "email": "jane@acme.test",
                },
            ),
            "Add that we're an agency of ten.": reply_and_call(
                "Added.", "book_demo", request={"notes": "Agency of ten, wants outreach videos."}
            ),
            "details step is on their screen": reply(
                "Tuesday at three it is. Press Schedule Event when ready."
            ),
            "pressed Schedule Event": reply("Thanks, Jane. This preview held it back."),
            "Let me sign up.": reply_and_call("Opening the sign-up.", "open_signup"),
            "Go back to the pricing tab.": reply_and_call(
                "Here's pricing.", "switch_tab", request={"tab_id": "11"}
            ),
            "Show me tab ninety.": reply_and_call("Here.", "switch_tab", request={"tab_id": "90"}),
            "What's on this tab?": reply("It's the agency post."),
            # Cues: out of the speech, checked against the site, sent to the page.
            "How does it work?": reply(
                "{page: /}{show: clone yourself} One recording becomes many. "
                "{show: the pink button} Each one is personal. {page: /moon} "
                "{faq: can i cancel anytime} Cancel whenever you like."
            ),
            # Asked about an FAQ that is on another page: it opens there.
            "Where does it say video length?": reply_and_call(
                "Up to five minutes.", "open_faq", request={"question": "how long can a video"}
            ),
            # The model came back with nothing at all: asked once more.
            "Hello?": [reply(""), reply("I'm here. Want a quick tour?")],
            "Carry on.": reply("Sure, let's keep going."),
            # A page move with no words: the model is asked once more, tools off.
            "Show me integrations.": [
                call("navigate", request={"path": "/integrations"}),
                reply("It plugs into your CRM. Which one do you use?"),
            ],
        }
    )


async def _page(rig: object, event: str, payload: dict[str, object]) -> None:
    await rig.driver.send_ui_event(event, payload)  # type: ignore[attr-defined]
    # `on_rtvi` takes no floor and there is nothing to await: give it a moment.
    await asyncio.sleep(0.1)


def _idle_windows(rig: object) -> list[int | None]:
    return [c.idle.timeout_ms for c in _configs(rig) if c.idle is not None]  # type: ignore[arg-type]


async def test_greeting_and_voice_reach_the_wire() -> None:
    """A written opener, and gaurav in English on both legs before it."""
    async with demo("sendpotion", _llm()) as rig:
        greeting = await rig.driver.start_session(
            init={"surface": "sendpotion-ext", "site": "site", "path": "/"}
        )
        check_greeting(rig, greeting)
        assert greeting is not None and greeting.text == _GREETING
        check_voice_pair(rig, voice="omnivoice/gaurav", language="en")
        assert _idle_windows(rig) == [_IDLE_MS]


async def test_the_opener_follows_the_page_and_the_blog() -> None:
    async with demo("sendpotion", _llm()) as rig:
        greeting = await rig.driver.start_session(init={"site": "site", "path": "/pricing/"})
        assert greeting is not None and "plan" in greeting.text
    async with demo("sendpotion", _llm()) as rig:
        greeting = await rig.driver.start_session(init={"site": "blog", "path": "/x-1a2b"})
        assert greeting is not None and greeting.text == _BLOG_GREETING


async def test_navigate_lands_on_the_section_and_refuses_an_invented_page() -> None:
    llm = _llm()
    async with demo("sendpotion", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        check_turn(rig, await rig.driver.user_says("How much is it?"))
        # The site's own spelling of the path and the heading.
        assert rig.command("navigate") == {
            "path": "/pricing/",
            "heading": "Pricing plans",
            "text": None,
            "faq": None,
        }
        await rig.driver.user_says("Take me to the moon page.")
        assert rig.actions().count("navigate") == 1
        # A heading the page does not have: it goes, and rings the words.
        await rig.driver.user_says("Show me HubSpot.")
        moves = [c["payload"] for c in rig.driver.ui_commands if c.get("command") == "navigate"]
        assert moves[-1] == {
            "path": "/integrations/",
            "heading": None,
            "text": "HubSpot logo",
            "faq": None,
        }
        assert "Not opened: /moon is not a page" in _results(llm.captured_contents[-1])["navigate"]


async def test_sections_and_faqs_are_checked_against_the_tab_in_front() -> None:
    llm = _llm()
    async with demo("sendpotion", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await _page(rig, "page_changed", PRICING_PAGE)
        await rig.driver.user_says("Show me the Professional plan.")
        assert rig.command("show_section") == {"heading": None, "text": "Professional"}
        # The page in front was read in with what they said.
        seen = _texts(llm.captured_contents[-1])
        assert "Its headings: Pricing plans; FAQs" in seen
        assert "Its plans: Starter, Professional, Enterprise" in seen
        await rig.driver.user_says("Show me the testimonials.")
        assert rig.actions().count("show_section") == 1
        await rig.driver.user_says("How long can videos be?")
        assert rig.command("open_faq") == {"question": "How long can a video be?"}
        # Gemini sometimes sends a tool's fields flat, without ``request``.
        await rig.driver.user_says("Show me the plans, flat.")
        assert rig.actions().count("show_section") == 2


async def test_blog_posts_are_found_recommended_and_never_invented() -> None:
    llm = _llm()
    async with demo("sendpotion", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("I run an agency and want more clients.")
        found = _results(llm.captured_contents[-1])["find_blog_posts"]
        assert f"url: {AGENCY}" in found
        listed = rig.command("open_posts")
        assert listed["heading"] == "For agency outreach"
        assert [p["url"] for p in listed["posts"]] == [AGENCY, VSL]
        assert listed["posts"][0]["title"] == "How agencies win clients with video"
        assert listed["open"] == AGENCY
        await rig.driver.user_says("Take me to the sequence part.")
        assert rig.command("open_post") == {"url": AGENCY, "heading": "The three-step sequence"}


async def test_the_demo_fills_as_they_talk_and_is_never_scheduled() -> None:
    llm = _llm()
    async with demo("sendpotion", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("I'd like a demo.")
        assert rig.command("book_demo") == {
            "day": None,
            "time": None,
            "name": None,
            "email": None,
            "notes": None,
        }
        # The calendar's open days arrive after his turn: a quiet visitor hears
        # them in the short quiet spell.
        await _page(
            rig,
            "demo_state",
            {
                "step": "calendar",
                "month": "October 2026",
                "days": ["Tuesday, October 20", "Wednesday, October 21", "Thursday, October 22"],
                "timezone": "India Standard Time",
            },
        )
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "Which suits you?" in turn.text
        assert _idle_windows(rig)[-1] == _IDLE_MS

        # The day is the calendar's own label; the details carry over and add up.
        await rig.driver.user_says("Tuesday at three, I'm Jane, jane@acme.test.")
        booked = [c["payload"] for c in rig.driver.ui_commands if c.get("command") == "book_demo"]
        assert booked[-1] == {
            "day": "Tuesday, October 20",
            "time": "3:00pm",
            "name": "Jane",
            "email": "jane@acme.test",
            "notes": None,
        }
        await rig.driver.user_says("Add that we're an agency of ten.")
        booked = [c["payload"] for c in rig.driver.ui_commands if c.get("command") == "book_demo"]
        assert booked[-1]["name"] == "Jane" and booked[-1]["email"] == "jane@acme.test"
        assert booked[-1]["notes"] == "Agency of ten, wants outreach videos."
        assert "schedule" not in " ".join(rig.actions()).lower()

        await _page(
            rig,
            "demo_state",
            {
                "step": "details",
                "date": "Tuesday, October 20",
                "time": "3:00pm",
                "filled": {"name": "Jane", "email": "jane@acme.test", "notes": ""},
                "missing": [],
            },
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "Schedule Event" in turn.text

        await _page(
            rig,
            "demo_scheduled",
            {"date": "Tuesday, October 20", "time": "3:00pm", "blocked": True},
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "held it back" in turn.text
        assert "held it back from SendPotion's calendar" in _texts(llm.captured_contents[-1])


async def test_tabs_are_read_in_and_switching_is_checked() -> None:
    llm = _llm()
    async with demo("sendpotion", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await _page(
            rig,
            "tabs_changed",
            {
                "tabs": [
                    {"tab_id": "11", "url": "https://sendpotion.com/pricing/", "title": "Pricing"},
                    {"tab_id": "12", "url": AGENCY, "title": "How agencies win clients"},
                ],
                "active": "12",
            },
        )
        await rig.driver.user_says("What's on this tab?")
        seen = _texts(llm.captured_contents[-1])
        assert "11: Pricing; 12: How agencies win clients (in front)" in seen
        await rig.driver.user_says("Go back to the pricing tab.")
        assert rig.command("focus_tab") == {"tab_id": "11"}
        await rig.driver.user_says("Show me tab ninety.")
        assert rig.actions().count("focus_tab") == 1


async def test_signup_opens_and_a_silent_move_is_talked_about() -> None:
    async with demo("sendpotion", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("Let me sign up.")
        assert "open_signup" in rig.actions()
        turn = await rig.driver.user_says("Show me integrations.")
        check_turn(rig, turn)
        assert "Which one do you use?" in turn.text


async def test_cues_leave_the_speech_and_move_the_page_with_it() -> None:
    async with demo("sendpotion", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        turn = await rig.driver.user_says("How does it work?")
        check_turn(rig, turn)
        assert "{" not in turn.text and "}" not in turn.text
        assert "One recording becomes many." in turn.text
        cues = [c["payload"] for c in rig.driver.ui_commands if c.get("command") == "cue"]
        # The page cue to where they already are; the heading in the site's
        # spelling; words that are no heading rung as words; the invented page
        # dropped; and an FAQ on another page, opened there.
        none = {"path": None, "heading": None, "text": None, "faq": None}
        assert cues == [
            {**none, "at": "one recording becomes", "word": 0, "path": "/"},
            {**none, "at": "one recording becomes", "word": 0, "heading": "Clone yourself"},
            {**none, "at": "each one is", "word": 4, "text": "the pink button"},
            {
                **none,
                "at": "cancel whenever you",
                "word": 8,
                "path": "/faq/",
                "faq": "Can I cancel anytime?",
            },
        ]


async def test_an_faq_on_another_page_is_opened_there() -> None:
    async with demo("sendpotion", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("Where does it say video length?")
        assert rig.command("navigate") == {
            "path": "/pricing/",
            "heading": None,
            "text": None,
            "faq": "How long can a video be?",
        }


async def test_a_missed_cue_is_noted_quietly() -> None:
    llm = _llm()
    async with demo("sendpotion", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await _page(rig, "command_failed", {"command": "cue", "reason": "no heading X"})
        await rig.driver.user_says("Carry on.")
        seen = _texts(llm.captured_contents[-1])
        assert "A screen cue of yours did not land (no heading X)" in seen
        assert "Tell the visitor plainly" not in seen


async def test_a_reply_with_nothing_in_it_is_asked_for_again() -> None:
    async with demo("sendpotion", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        turn = await rig.driver.user_says("Hello?")
        check_turn(rig, turn)
        assert "Want a quick tour?" in turn.text
