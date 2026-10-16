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
        "/ai-personalized-video-marketing-software": Page(
            "/ai-personalized-video-marketing-software",
            "Marketing | Potion",
            sections=(Section("Manage inbound leads"),),
        ),
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
            "How much is it?": reply(
                "{page: /pricing/}{show: pricing plans} Plans start small. "
                "See the plans side by side?"
            ),
            "Show me HubSpot.": reply(
                "{page: /integrations}{show: HubSpot logo} Yes, it works with HubSpot."
            ),
            "Show me the Professional plan.": reply(
                "{show: Professional} Most teams land here. It has no limit."
            ),
            "How long can videos be?": reply(
                "{faq: how long can a video} Up to five minutes. Shorter works best."
            ),
            # He forgot to show what they asked about: their page goes first.
            "How do marketing teams use it?": reply(
                "Marketing teams clone themselves once. Every lead gets a video."
            ),
            # His own cue wins over the page their words name.
            "What does marketing cost?": reply(
                "{page: /pricing/} Plans start small. See them side by side?"
            ),
            "Tell me more about marketing.": reply("Webinar attendees get a follow-up, too."),
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
            "Where does it say video length?": reply(
                "{faq: how long can a video} Up to five minutes."
            ),
            # The model came back with nothing at all: asked once more.
            "Hello?": [reply(""), reply("I'm here. Want a quick tour?")],
            "Carry on.": reply("Sure, let's keep going."),
            # A move with no words: the model is asked once more, tools off.
            "Open the sign-up.": [
                call("open_signup"),
                reply("It's open beside this one. Want a hand with the first step?"),
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


NONE = {"path": None, "heading": None, "text": None, "faq": None}


def _cues(rig: object) -> list[dict[str, object]]:
    return [c["payload"] for c in rig.driver.ui_commands if c.get("command") == "cue"]  # type: ignore[attr-defined]


async def test_the_page_moves_only_by_cues() -> None:
    """No tool moves the page: a tool call ends the model's response, and one
    made before any words cost a second model call (dev call 60e6c24b, turns 7
    and 10: about 1.7 s each)."""
    async with demo("sendpotion", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        tools = {t.__name__ for t in rig.brain.tools}  # type: ignore[attr-defined]
        assert not tools & {"navigate", "show_section", "open_faq"}
        check_turn(rig, await rig.driver.user_says("How much is it?"))
        # The site's own spelling of the path and the heading.
        assert _cues(rig)[-1] == {
            **NONE,
            "at": "plans start small",
            "word": 0,
            "path": "/pricing/",
            "heading": "Pricing plans",
        }
        # A heading the page does not have: it goes, and rings the words.
        await rig.driver.user_says("Show me HubSpot.")
        assert _cues(rig)[-1] == {
            **NONE,
            "at": "yes it works",
            "word": 0,
            "path": "/integrations/",
            "text": "HubSpot logo",
        }


async def test_sections_and_faqs_are_checked_against_the_tab_in_front() -> None:
    llm = _llm()
    async with demo("sendpotion", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await _page(rig, "page_changed", PRICING_PAGE)
        await rig.driver.user_says("Show me the Professional plan.")
        assert _cues(rig)[-1] == {
            **NONE,
            "at": "most teams land",
            "word": 0,
            "text": "Professional",
        }
        # The page in front was read in with what they said.
        seen = _texts(llm.captured_contents[-1])
        assert "Its headings: Pricing plans; FAQs" in seen
        assert "Its plans: Starter, Professional, Enterprise" in seen
        await rig.driver.user_says("How long can videos be?")
        assert _cues(rig)[-1] == {
            **NONE,
            "at": "up to five",
            "word": 0,
            "faq": "How long can a video be?",
        }


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
        turn = await rig.driver.user_says("Open the sign-up.")
        check_turn(rig, turn)
        assert "Want a hand with the first step?" in turn.text


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
        assert _cues(rig) == [
            {
                **NONE,
                "at": "up to five",
                "word": 0,
                "path": "/pricing/",
                "faq": "How long can a video be?",
            }
        ]


async def test_what_they_asked_about_is_shown_when_his_reply_forgets_to() -> None:
    """Dev call 60e6c24b: told about marketing twice, screen unmoved."""
    async with demo("sendpotion", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        turn = await rig.driver.user_says("How do marketing teams use it?")
        check_turn(rig, turn)
        assert "{" not in turn.text
        marketing = "/ai-personalized-video-marketing-software/"
        assert _cues(rig) == [{**NONE, "at": "marketing teams clone", "word": 0, "path": marketing}]
        # His own cue wins over the page their words name.
        await rig.driver.user_says("What does marketing cost?")
        assert [c["path"] for c in _cues(rig)] == [marketing, "/pricing/"]
        # Nothing to add on the page they already have in front.
        await _page(
            rig,
            "page_changed",
            {**PRICING_PAGE, "path": marketing, "url": "x", "faqs": [], "plans": []},
        )
        await rig.driver.user_says("Tell me more about marketing.")
        assert len(_cues(rig)) == 2
    # Nor on the blog: a site page would open over the post they are reading.
    async with demo("sendpotion", _llm()) as rig:
        await rig.driver.start_session(init={"site": "blog", "path": "/x-1a2b"})
        await rig.driver.user_says("How do marketing teams use it?")
        assert _cues(rig) == []


def test_the_page_for_what_they_asked_about() -> None:
    marketing = "/ai-personalized-video-marketing-software"
    sales = "/ai-video-prospecting-software"
    assert sendpotion.asked_page("some use case about marketing with Potion?") == marketing
    assert sendpotion.asked_page("No, show me some use cases in sales.") == sales
    assert sendpotion.asked_page("We use HubSpot for sales") == "/integrations"
    assert sendpotion.asked_page("Show me the use cases") == "/use-cases"
    assert sendpotion.asked_page("Go back to the pricing tab.") is None
    assert sendpotion.asked_page("Mm-hmm") is None
    assert sendpotion.asked_page("Yeah, please show me.") is None
    # Every page it names is one the crawl has.
    crawl = kb.load()
    for path in [p for _, p in sendpotion._ASKED_PAGES] + ["/use-cases"]:
        assert crawl.page(path) is not None, path


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
