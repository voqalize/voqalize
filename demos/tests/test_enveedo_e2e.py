"""Javier, Enveedo's guide, end to end over the wire — no network, no LLM key.

The real ``EnveedoBrain`` on a real ``brain_server`` socket, driven by the
conformance ``VoqalizeDriver``, with only the model scripted. The knowledge is a
small invented Enveedo in the crawl's own shape, put in place of the committed
one, and "today" is fixed, so no test depends on what the crawl found this week
or on the day it runs.

What this demo earns that others do not:

**The screen follows his voice, on the site's own places, in two languages.**
Every cue is checked against the catalogue (``anchors.json``), whose keys are
the same on the English and the Spanish pages: a key that is nowhere is
dropped, a place on one other page takes the visitor there, and what they
asked about is shown when his reply forgets to. He names English paths; the
page the visitor is on may be the /es/ twin.

**The demo is booked by voice.** ``book_demo`` opens the HubSpot scheduler;
its open days, times and details step come back from the page and are said in
the next quiet spell, with tools off; he never names a day it has not listed,
and a confirm the preview held back is said plainly.

**The visitor presses the button.** He fills the contact form and the SOC 2
request as they dictate them — the form's own country option, never a card or
a password — and the page tells him when only their part is left (the consent
box) and how the site answered their press. No Action can submit.

**English first, Spanish on the Spanish site.** The call opens in English
unless the visitor chose Spanish or started on /es/, follows the language they
speak, holds one they chose, and the site follows the call.

Run: ``cd demos && uv run pytest tests/test_enveedo_e2e.py``
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import (
    ScriptedOpenAI,
    call,
    input_texts,
    reply,
    reply_and_call,
    tool_results,
    tool_results_of,
)

from ._harness import _configs, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.enveedo import brain as ev  # noqa: E402
from voqalize_demos._loaded.enveedo import knowledge as kb  # noqa: E402
from voqalize_demos._loaded.enveedo.brain import (  # noqa: E402
    _IDLE_MS,
    _LANDED,
    _TALK_THROUGH_MS,
    TOGGLE_CONFIRM,
    asked_page_language,
    asked_target,
    country_option,
    for_the_voice,
    from_the_voice,
    greeting,
    language_of,
)
from voqalize_demos._loaded.enveedo.knowledge import (  # noqa: E402
    Anchor,
    Exit,
    Knowledge,
    Page,
    Section,
)

# ─── An invented Enveedo ───────────────────────────────────────────────────────

TODAY = date(2026, 10, 28)
HOME = "/"
ES_HOME = "/es/"
FRAMEWORKS = "/frameworks"
DEMO = "/book-a-demo"
CONTACT = "/contact"
TRUST = "/trust-center"
FAQ = "/faq"
PARTNERS = "/partners"
SPOS = "/security-performance-os"
GOLD = "https://info.enveedo.com/cdpo-ebook"
PDF = "https://enveedo.com/hubfs/platform.pdf"

CHROME = (Anchor("menu", "The top menu"), Anchor("footer", "The footer"))


def _page(path: str, kind: str, places: list[tuple[str, str, str]], *, lang: str = "en") -> Page:
    return Page(
        path=path,
        title=f"Enveedo {kind}",
        kind=kind,
        lang=lang,
        sections=tuple(Section(k, label, text) for k, label, text in places),
        text=" ".join(text for _, _, text in places),
    )


HOME_PLACES = [
    ("hero", "Hero: Security Program Management. Simplified.", "Transform fragmented tools."),
    ("how_it_works", "How Enveedo Works: four capability tabs", "Four core capabilities."),
    (
        "how_business_first",
        "How Enveedo Works tab: Business-First Risk Management",
        "Crown Jewels.",
    ),
    (
        "how_integration",
        "How Enveedo Works tab: Intelligent Integration",
        "Connect your tools via API.",
    ),
    ("how_reporting", "How Enveedo Works tab: Executive-Ready Reporting", "Reports for the board."),
    ("toggle_with", "The four cards switched to With Enveedo", "Unified Security Platform."),
    ("integrations", "Supported Integrations: logo carousel", "CrowdStrike Okta AWS Azure"),
    ("impact_stats", "Real-World Impact: 5x, 50%, 3x", "Faster risk assessment."),
]
FW_PLACES = [
    ("intro", "Frameworks: the Assessment module", "Assess compliance in real time."),
    ("fw_nis2", "Framework card: NIS2 Directive", "EU-wide cybersecurity rules."),
    ("fw_chile_21719", "Framework card: Chile Data Protection Law (21.719)", "Chile's new law."),
    ("contact_form", "How can we help? The contact form", "Name Last name Country"),
]

SITE = Knowledge(
    l1="## What the site does NOT say\n- **No pricing.**\n\n## Who Enveedo is\nA platform.",
    topics={
        "platform": kb.Topic("platform", "The platform", "# The platform\nSix modules."),
    },
    pages={
        HOME: _page(HOME, "home", HOME_PLACES),
        ES_HOME: _page(ES_HOME, "home", HOME_PLACES, lang="es"),
        FRAMEWORKS: _page(FRAMEWORKS, "frameworks", FW_PLACES),
        DEMO: _page(
            DEMO, "demo", [("demo_request", "Request a product demo", "Free risk assessment.")]
        ),
        CONTACT: _page(CONTACT, "contact", [("contact_form", "The contact form", "Name Email")]),
        TRUST: _page(
            TRUST,
            "trust",
            [
                ("soc2", "SOC 2 Compliance: the SOC 2 Type II report", "Type II report."),
                ("soc2_form", "Request the SOC 2 Type II report (form)", "First name"),
            ],
        ),
        FAQ: _page(FAQ, "faq", [("faq_start", "FAQ: How do I start using Enveedo?", "$2,500 USD")]),
        PARTNERS: _page(
            PARTNERS,
            "partners",
            [
                ("why_partner", "Why Partner with Enveedo?", "vCISO services at scale."),
                ("benefits", "Partners Benefits: multitenancy", "Multitenancy, marketplace."),
            ],
        ),
        SPOS: _page(
            SPOS, "enterprise", [("multi_workspace", "Unified Multi-Workspace Console", "")]
        ),
    },
    anchors={
        HOME: (
            *(
                Anchor(k, label, reveal=k.startswith(("how_b", "how_i", "how_r", "toggle")))
                for k, label, _ in HOME_PLACES
            ),
            *CHROME,
        ),
        ES_HOME: (*(Anchor(k, label) for k, label, _ in HOME_PLACES), *CHROME),
        FRAMEWORKS: (
            *(Anchor(k, label) for k, label, _ in FW_PLACES),
            Anchor("contact_submit", "Submit", hidden=True),
            *CHROME,
        ),
        DEMO: (Anchor("demo_request", "Request a product demo"), *CHROME),
        CONTACT: (
            Anchor("contact_form", "The contact form"),
            Anchor("contact_consent", "Consent", hidden=True),
            Anchor("contact_submit", "Submit", hidden=True),
            *CHROME,
        ),
        TRUST: (Anchor("soc2", "SOC 2 Compliance"), Anchor("soc2_form", "SOC 2 form"), *CHROME),
        FAQ: (Anchor("faq_start", "FAQ: How do I start?", reveal=True), *CHROME),
        PARTNERS: (Anchor("why_partner", "Why Partner"), Anchor("benefits", "Benefits"), *CHROME),
        SPOS: (Anchor("multi_workspace", "Unified Multi-Workspace Console"), *CHROME),
    },
    twins={
        HOME: ES_HOME,
        FRAMEWORKS: "/es/frameworks",
        DEMO: "/es/book-a-demo",
        CONTACT: "/es/contact",
        TRUST: "/es/trust-center",
        FAQ: "/es/faq",
        PARTNERS: "/es/partners",
        SPOS: "/es/security-performance-os",
    },
    exits={
        "scheduler": Exit(
            "scheduler",
            "Elis Martinez's HubSpot Meetings page",
            "https://meetings.hubspot.com/elis-martinez",
        ),
        "sign_in": Exit("sign_in", "Enveedo sign-in (customers)", "https://app.enveedo.com/login"),
        "blog": Exit("blog", "Cyber Pulse blog", "https://blog.enveedo.com/"),
        "blog_es": Exit("blog_es", "Cyber Pulse blog (Spanish)", "https://blog.enveedo.com/es"),
        "platform_pdf": Exit("platform_pdf", "The platform PDF", PDF),
    },
    library=(
        Exit("library_0", "The Gold Standard in Cyber Defense Planning and Optimization", GOLD),
        Exit(
            "library_1",
            "Securing the Future: Hail & Cotton's Cybersecurity Overhaul with Enveedo",
            "https://info.enveedo.com/hail-and-cotton-customer-story",
        ),
    ),
    contact={"phone": "+1 786 648 6418", "email": "info@enveedo.com"},
)


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every session reads the invented Enveedo, and he never nods unless a
    test asks him to: a nod is a unit of its own."""
    monkeypatch.setattr(kb, "KNOWLEDGE", SITE)
    monkeypatch.setattr(ev.kb, "KNOWLEDGE", SITE)
    monkeypatch.setattr(ev, "ACK_RATE", 0.0)
    monkeypatch.setattr(ev.EnveedoBrain, "today", property(lambda self: TODAY))
    yield


# ─── Reading the wire ──────────────────────────────────────────────────────────


def _texts(items: list[Any]) -> str:
    return input_texts(items)


async def _event(rig: object, event: str, payload: dict[str, object]) -> None:
    await rig.driver.send_ui_event(event, payload)  # type: ignore[attr-defined]
    # `on_rtvi` takes no floor and there is nothing to await: give it a moment.
    await asyncio.sleep(0.1)


def _idle_windows(rig: object) -> list[int | None]:
    return [c.idle.timeout_ms for c in _configs(rig) if c.idle is not None]  # type: ignore[arg-type]


def _commands(rig: object, name: str) -> list[dict[str, object]]:
    return [c["payload"] for c in rig.driver.ui_commands if c.get("command") == name]  # type: ignore[attr-defined]


def _cues(rig: object) -> list[dict[str, object]]:
    return _commands(rig, "cue")


NONE = {"path": None, "anchor": None, "text": None}


def _page_changed(path: str, **fields: object) -> dict[str, object]:
    return {"url": f"https://enveedo.com{path}", "path": path, "title": "", **fields}


def _demo_state(step: str, **fields: object) -> dict[str, object]:
    return {"step": step, **fields}


CALENDAR = _demo_state(
    "calendar",
    durations=["15 mins", "30 mins", "1 hour"],
    month="November 2026",
    days=["2026-11-03", "2026-11-04", "2026-11-06"],
    timezone="America/Santiago",
)

# ─── The script ────────────────────────────────────────────────────────────────


def _llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            # Language.
            "¿Cómo funciona la plataforma?": reply(
                "{page: /}{show: how_it_works} Parte por tu negocio. ¿Te muestro más?"
            ),
            "How does it work?": reply(
                "{page: /}{show: how_it_works} It starts from your business. "
                "{show: how_integration} Then it connects your tools. "
                "{show: how_nothing} And something that is not there. Shall I go on?"
            ),
            "I am asking you in English now": reply("Claro, sigo en español. ¿Qué buscas?"),
            "Can we speak Spanish?": reply_and_call(
                "Claro, seguimos en español.", "set_language", args={"language": "es"}
            ),
            "La página está en inglés": reply("Te la muestro en español."),
            # A place on one other page; what they asked about goes first.
            "Where do I start?": reply("{show: faq_start} Here is how to start."),
            "Do you integrate with CrowdStrike?": reply(
                "Yes, CrowdStrike is among the integrations shown."
            ),
            "Do you cover NIS2?": [
                call("find_framework", args={"query": "NIS 2"}),
                reply("{page: /frameworks}{show: fw_nis2} Yes, NIS2 is on the list."),
            ],
            "Do you cover the CMF rules?": [
                call("find_framework", args={"query": "CMF"}),
                reply("It isn't among the listed frameworks."),
            ],
            "The SOC 2 report?": reply(
                "{page: /trust-center}{show: soc2} The SOC 2 report is here."
            ),
            # The demo.
            "I'd like a demo.": reply_and_call(
                "I'm opening the demo scheduler.", "book_demo", args={}
            ),
            "open days": reply("The fourth or the sixth of November work. Which suits you?"),
            "The fourth, thirty minutes.": reply_and_call(
                "Choosing the fourth.",
                "book_demo",
                args={"day": "2026-11-04", "duration": "30 mins"},
            ),
            "now lists the times": reply("Ten thirty or two work. Which one?"),
            "Ten thirty.": reply_and_call(
                "Ten thirty it is. Your first name?", "book_demo", args={"time": "10:30am"}
            ),
            "Nine.": reply_and_call("Nine it is.", "book_demo", args={"time": "9:00pm"}),
            "details step": reply("The fourth at ten thirty. Your first name?"),
            "I'm Ana Torres, ana at acme dot com.": reply_and_call(
                "I've put a, n, a, at acme dot com.",
                "book_demo",
                args={"first_name": "Ana", "last_name": "Torres", "email": "ANA@acme.com"},
            ),
            "My email is ana acme.": reply_and_call(
                "Noted.", "book_demo", args={"email": "ana acme"}
            ),
            "the page held it back": reply("In this preview, the booking is not sent to Enveedo."),
            "did not do what you sent it": reply("The scheduler didn't take that."),
            "Book me tomorrow.": reply_and_call(
                "Choosing tomorrow.", "book_demo", args={"day": "tomorrow"}
            ),
            # The forms.
            "Please contact me, I'm Lucía.": reply_and_call(
                "Noted, Lucía. Your last name?",
                "fill_form",
                args={"form": "contact", "firstname": "Lucía"},
            ),
            "Pérez, from Spain, lucia at grupo dot es.": reply_and_call(
                "Spain is not on the list, so I chose Others.",
                "fill_form",
                args={
                    "form": "contact",
                    "lastname": "Pérez",
                    "country": "Spain",
                    "email": "LUCIA@grupo.es ",
                },
            ),
            "We are in Chile.": reply_and_call(
                "Chile, noted.", "fill_form", args={"form": "contact", "country": "chile"}
            ),
            "My card is 4111 1111 1111 1111.": reply_and_call(
                "Thanks.", "fill_form", args={"form": "contact", "message": "4111 1111 1111 1111"}
            ),
            "Send me the SOC 2 report, I'm the CISO.": reply_and_call(
                "I'm taking you to the request.",
                "fill_form",
                args={"form": "soc2", "job_title": "CISO", "phone": "+56 9 1234 5678"},
            ),
            "has everything you can fill": reply("It's ready. Tick consent and press Submit."),
            "confirmed the contact form was sent": reply("Thanks, Lucía. The team will reply."),
            "could not send the contact form": reply("It didn't go through. Press Submit again."),
            "refused the contact form": reply("Please check your email."),
            "fill_form not done": reply("I couldn't fill the form."),
            "And then?": reply("Go on."),
            # Links.
            "Open the Gold Standard eBook.": reply_and_call(
                "Opening it.", "open_link", args={"kind": "library", "name": "gold standard"}
            ),
            "Open the platform PDF.": reply_and_call(
                "Opening it.", "open_link", args={"kind": "pdf"}
            ),
            "Open some ebook about cats.": reply_and_call(
                "Let me look.", "open_link", args={"kind": "library", "name": "cats"}
            ),
            # Tabs, silent moves, promises.
            "Go back to the other tab.": reply_and_call(
                "There it is.", "switch_tab", args={"tab_id": "11"}
            ),
            "Show me the PDF.": [call("open_link", args={"kind": "pdf"})],
            "What about the price?": [reply("One moment."), reply("Pricing isn't published.")],
            # The voice.
            "Do you have SOC 2?": reply(
                "{page: /trust-center}{show: soc2} Yes, a SOC 2 Type II report, for any CISO."
            ),
        },
        default=reply("Go on."),
    )


# ─── Greeting, voice and language ──────────────────────────────────────────────


async def test_greeting_and_voice_reach_the_wire_in_english() -> None:
    async with demo("enveedo", _llm()) as rig:
        opener = await rig.driver.start_session(init={"path": "/", "tz": "America/Mexico_City"})
        check_greeting(rig, opener)
        assert opener is not None and opener.text == greeting("/", "en", SITE)
        assert opener.text.startswith("Hi, I'm Javier, your guide to Enveedo.")
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert _idle_windows(rig) == [_IDLE_MS]
        # The tab keeps the call's language; the page they are on stays.
        assert _commands(rig, "language_changed") == [{"language": "en", "site": "stay"}]


async def test_a_call_started_on_the_spanish_site_opens_in_spanish() -> None:
    llm = _llm()
    async with demo("enveedo", llm) as rig:
        opener = await rig.driver.start_session(
            init={"path": "/es/frameworks", "site_lang": "es", "tz": "America/Santiago"}
        )
        check_greeting(rig, opener)
        assert opener is not None and opener.text == greeting(FRAMEWORKS, "es", SITE)
        assert "marco" in opener.text
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _commands(rig, "language_changed") == [{"language": "es", "site": "stay"}]
        await rig.driver.user_says("¿Cómo funciona la plataforma?")
        context = _texts(llm.captured_inputs[-1])
        assert (
            "Today is Wednesday, October 28, 2026, in the visitor's time zone (America/Santiago)"
            in context
        )


async def test_spanish_chosen_on_the_toggle_before_the_call_holds() -> None:
    llm = _llm()
    async with demo("enveedo", llm) as rig:
        await rig.driver.start_session(init={"path": "/", "lang": "es"})
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        turn = await rig.driver.user_says("I am asking you in English now, okay?")
        assert "en español" in turn.text
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert "The visitor chose Spanish before the call" in _texts(llm.captured_inputs[-1])


@pytest.mark.parametrize(
    ("path", "en", "es"),
    [
        (FRAMEWORKS, "framework", "marco"),
        ("/es/partners", "MSPs and MSSPs", "programa de partners"),
        (DEMO, "book your demo", "agendar tu demo"),
        (TRUST, "SOC 2 report", "informe SOC 2"),
        ("/es/book-a-demo-rsa", "eBook", "eBook"),
        ("/privacy-policy", "What's your role?", "¿Cuál es tu rol?"),
    ],
)
def test_the_opener_follows_the_page_in_either_language(path: str, en: str, es: str) -> None:
    real = kb.load()
    assert en in greeting(path, "en", real) and es in greeting(path, "es", real)


async def test_spanish_heard_switches_both_legs_and_the_site_follows() -> None:
    async with demo("enveedo", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Cómo funciona la plataforma?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        # site "follow": the page in front loads its Spanish twin.
        assert _commands(rig, "language_changed")[-1] == {"language": "es", "site": "follow"}


async def test_the_toggle_switches_both_legs_and_confirms() -> None:
    async with demo("enveedo", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _event(rig, "language_requested", {"language": "es"})
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert turn.text == TOGGLE_CONFIRM["es"]


async def test_asking_for_spanish_switches_and_opens_no_page() -> None:
    async with demo("enveedo", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("Can we speak Spanish?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _cues(rig) == []


async def test_the_page_in_the_wrong_language_reloads_as_its_twin() -> None:
    llm = _llm()
    async with demo("enveedo", llm) as rig:
        await rig.driver.start_session(init={"path": "/es/", "site_lang": "es"})
        await _event(rig, "page_changed", _page_changed(FRAMEWORKS, lang="en", kind="frameworks"))
        await rig.driver.user_says("La página está en inglés, ¿me la muestras en español?")
        assert _commands(rig, "language_changed")[-1] == {"language": "es", "site": "twin"}
        assert "The page in front is loading in Spanish now" in _texts(llm.captured_inputs[-1])


@pytest.mark.parametrize(
    ("text", "sure", "lang"),
    [
        ("¿Puedes hablar en español?", True, "es"),
        ("¿Cuánto cuesta la plataforma?", True, "es"),
        ("Hola", True, None),
        ("Can you show me how the platform works?", True, "en"),
        ("Claro.", False, "es"),
        ("Sure, here it is.", False, "en"),
        ("{show: hero} Security Performance OS is the enterprise page, here it is.", False, "en"),
        ("Chile's Ley Marco de Ciberseguridad is on the list, and it is here.", False, "en"),
    ],
)
def test_the_language_a_line_is_in(text: str, sure: bool, lang: str | None) -> None:
    assert language_of(text, sure=sure) == lang


def test_a_remark_about_the_page_language_is_only_one_against_the_call() -> None:
    assert asked_page_language("La página está en inglés", "es", "en") == "es"
    assert asked_page_language("Show me the page in Spanish", "en", "en") is None
    assert asked_page_language("La página está en inglés", "es", "es") is None


# ─── Cues ──────────────────────────────────────────────────────────────────────


async def test_a_walkthrough_cues_reveal_places_and_drops_a_made_up_key() -> None:
    async with demo("enveedo", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("How does it work?")
        check_turn(rig, turn)
        assert "{" not in turn.text and "Then it connects your tools." in turn.text
        assert _cues(rig) == [
            {**NONE, "at": "it starts from", "word": 0, "path": HOME},
            {**NONE, "at": "it starts from", "word": 0, "anchor": "how_it_works"},
            {**NONE, "at": "then it connects", "word": 5, "anchor": "how_integration"},
        ]


async def test_a_walkthrough_of_the_modules_rings_each_card_as_he_names_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The real catalogue: the six module cards are places of their own.
    real = kb.load()
    monkeypatch.setattr(kb, "KNOWLEDGE", real)
    monkeypatch.setattr(ev.kb, "KNOWLEDGE", real)
    cards = [
        ("mod_crown_jewel", "Crown Jewel Analysis finds what matters most."),
        ("mod_risk_register", "Risk Register brings every risk into one place."),
        ("mod_compliance", "Compliance Management maps a control once."),
        ("mod_vendor_risk", "Vendor Risk Management scores your suppliers."),
        ("mod_incident_response", "Incident Response Manager runs your plans."),
        ("mod_roadmap", "Security Roadmap tracks progress."),
    ]
    said = " ".join(f"{{show: {key}}} {line}" for key, line in cards)
    llm = ScriptedOpenAI(
        {
            "What are the modules?": reply(
                f"{{show: modules}} Six modules, one program. {said} Which one matters most?"
            ),
            "Tell me about the risk register.": reply(
                "{show: mod_risk_register} Every risk in one place. It updates from your tools."
            ),
        }
    )
    async with demo("enveedo", llm) as rig:
        await rig.driver.start_session(init={"path": "/enveedo_platform"})
        await _event(
            rig,
            "page_changed",
            _page_changed(
                "/enveedo_platform",
                lang="en",
                kind="platform",
                anchors=["modules", *(k for k, _ in cards)],
            ),
        )
        await rig.driver.user_says("What are the modules?")
        shown = [c["anchor"] for c in _cues(rig) if c.get("anchor")]
        assert shown == ["modules", *(k for k, _ in cards)]
        assert all(c["path"] is None for c in _cues(rig)), "no page move: all on this page"
        rig.driver.ui_commands.clear()
        await rig.driver.user_says("Tell me about the risk register.")
        assert _cues(rig)[0]["anchor"] == "mod_risk_register"


async def test_a_place_on_one_other_page_takes_them_there() -> None:
    async with demo("enveedo", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Where do I start?")
        assert _cues(rig)[0] == {
            **NONE,
            "at": "here is how",
            "word": 0,
            "path": FAQ,
            "anchor": "faq_start",
        }


async def test_on_the_spanish_page_the_same_keys_ring_in_place() -> None:
    async with demo("enveedo", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/es/", "site_lang": "es"})
        await _event(
            rig,
            "page_changed",
            _page_changed(ES_HOME, lang="es", kind="home", anchors=["how_it_works"]),
        )
        await rig.driver.user_says("¿Cómo funciona la plataforma?")
        # He names the English path (the extension loads its twin); the place,
        # on the page in front, rings without another page move.
        assert _cues(rig) == [
            {**NONE, "at": "parte por tu", "word": 0, "path": HOME},
            {**NONE, "at": "parte por tu", "word": 0, "anchor": "how_it_works"},
        ]


async def test_what_they_asked_about_goes_first_when_his_reply_forgets() -> None:
    async with demo("enveedo", _llm()) as rig:
        await rig.driver.start_session(init={"path": FRAMEWORKS})
        await rig.driver.user_says("Do you integrate with CrowdStrike?")
        assert _cues(rig)[:2] == [
            {**NONE, "at": "yes crowdstrike is", "word": 0, "path": HOME},
            {**NONE, "at": "yes crowdstrike is", "word": 0, "path": HOME, "anchor": "integrations"},
        ]


def test_where_what_they_asked_about_is_shown() -> None:
    assert asked_target("Do you support NIS 2?") == (FRAMEWORKS, "fw_nis2")
    assert asked_target("¿Cubren la nueva ley de protección de datos?") == (
        FRAMEWORKS,
        "fw_chile_21719",
    )
    assert asked_target("We're an MSSP.") == (PARTNERS, "why_partner")
    assert asked_target("We have five subsidiaries in LATAM") == (SPOS, "multi_workspace")
    assert asked_target("Can I get your SOC 2 report?") == (TRUST, "soc2")
    # A country alone names no law; a demo, a form or the call's language is a tool's.
    assert asked_target("We are a company in Mexico.") is None
    assert asked_target("I'd like to book a demo.") is None
    assert asked_target("¿Puedes hablar en español?") is None


async def test_find_framework_names_the_card_and_never_invents_one() -> None:
    llm = _llm()
    async with demo("enveedo", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("Do you cover NIS2?")
        check_turn(rig, turn)
        found = tool_results(llm.captured_inputs[-1])["find_framework"]
        assert found.startswith("Found: NIS2 Directive (key fw_nis2")
        assert "{page: /frameworks}{show: fw_nis2}" in found
        assert _cues(rig)[-1] == {
            **NONE,
            "at": "yes nis two",
            "word": 0,
            "path": FRAMEWORKS,
            "anchor": "fw_nis2",
        }
        await rig.driver.user_says("Do you cover the CMF rules?")
        missing = tool_results(llm.captured_inputs[-1])["find_framework"]
        assert (
            missing.startswith("No card matches 'CMF'") and "never that it is supported" in missing
        )


# ─── The demo ──────────────────────────────────────────────────────────────────


async def test_the_demo_is_booked_by_voice_and_its_answers_said_in_the_quiet() -> None:
    llm = _llm()
    seen = llm.requests
    async with demo("enveedo", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("I'd like a demo.")
        check_turn(rig, turn)
        assert _commands(rig, "book_demo") == [
            {
                "duration": None,
                "day": None,
                "time": None,
                "first_name": None,
                "last_name": None,
                "email": None,
            }
        ]
        # Still loading: noted, nothing to say yet.
        await _event(rig, "demo_state", _demo_state("loading"))
        assert _idle_windows(rig)[-1] == _IDLE_MS
        # The open days arrive: said in the next quiet spell, tools off.
        await _event(rig, "demo_state", CALENDAR)
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        before = len(seen)
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "fourth or the sixth" in turn.text
        context = _texts(llm.captured_inputs[-1])
        assert "Open days: 2026-11-03; 2026-11-04; 2026-11-06." in context
        assert "Times are in America/Santiago." in context
        (talk,) = seen[before:]
        assert talk.get("tool_choice") == "none"
        # A day and a length; then the times; then a time.
        await rig.driver.user_says("The fourth, thirty minutes.")
        assert _commands(rig, "book_demo")[-1]["day"] == "2026-11-04"
        assert _commands(rig, "book_demo")[-1]["duration"] == "30 mins"
        await _event(
            rig,
            "demo_state",
            {
                **CALENDAR,
                "date": "2026-11-04",
                "duration": "30 mins",
                "times": ["10:30am", "2:00pm"],
            },
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "Ten thirty or two" in turn.text
        await rig.driver.user_says("Ten thirty.")
        last = _commands(rig, "book_demo")[-1]
        assert (last["day"], last["time"], last["duration"]) == (None, "10:30am", "30 mins")
        # The details step, and their details: what is filled stays.
        await _event(
            rig,
            "demo_state",
            _demo_state(
                "details",
                date="2026-11-04",
                time="10:30am",
                duration="30 mins",
                missing=["first_name", "last_name", "email"],
            ),
        )
        # His last reply already asked for the first name: the step is noted,
        # never talked through a second time (dev call f89030a6).
        assert _idle_windows(rig)[-1] == _IDLE_MS
        await rig.driver.user_says("I'm Ana Torres, ana at acme dot com.")
        last = _commands(rig, "book_demo")[-1]
        assert (last["first_name"], last["last_name"], last["email"]) == (
            "Ana",
            "Torres",
            "ana@acme.com",
        )
        await rig.driver.user_says("And then?")
        result = tool_results(llm.captured_inputs[-1])["book_demo"]
        assert "Spell the email back letter by letter" in result
        assert "Nothing is confirmed yet" in result
        # No Action can press the scheduler's confirm.
        assert not [a for a in rig.actions() if "submit" in a or "confirm" in a or "schedule" in a]


async def test_the_details_step_is_talked_through_when_he_has_not_asked_yet() -> None:
    llm = _llm()
    async with demo("enveedo", llm) as rig:
        await rig.driver.start_session(init={"path": "/book-a-demo"})
        await _event(rig, "demo_state", CALENDAR)
        await rig.driver.user_says("Nine.")
        await _event(
            rig,
            "demo_state",
            _demo_state(
                "details",
                date="2026-11-04",
                time="9:00pm",
                missing=["first_name", "last_name", "email"],
            ),
        )
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "Your first name?" in turn.text


async def test_a_held_back_confirm_is_said_plainly() -> None:
    llm = _llm()
    async with demo("enveedo", llm) as rig:
        await rig.driver.start_session(init={"path": DEMO})
        await _event(
            rig,
            "demo_scheduled",
            {
                "date": "2026-11-04",
                "time": "10:30am",
                "filled": {"first_name": "Ana"},
                "blocked": True,
            },
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "not sent to Enveedo" in turn.text
        assert "This preview held it back: nothing reached Enveedo's calendar." in _texts(
            llm.captured_inputs[-1]
        )


async def test_a_bad_email_and_a_failed_scheduler_move_are_said() -> None:
    llm = _llm()
    async with demo("enveedo", llm) as rig:
        await rig.driver.start_session(init={"path": DEMO})
        await rig.driver.user_says("My email is ana acme.")
        assert "book_demo" not in rig.actions()
        await rig.driver.user_says("And then?")
        assert tool_results_of(llm.captured_inputs[-1], "book_demo")[0].startswith(
            "Not filled: 'anaacme' is not an email address"
        )
        await _event(rig, "command_failed", {"command": "book_demo", "reason": "no scheduler"})
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "didn't take that" in turn.text
        assert "never say it did" in _texts(llm.captured_inputs[-1])


async def test_tomorrow_is_resolved_against_the_visitors_today() -> None:
    async with demo("enveedo", _llm()) as rig:
        await rig.driver.start_session(init={"path": DEMO})
        await rig.driver.user_says("Book me tomorrow.")
        assert _commands(rig, "book_demo")[-1]["day"] == "2026-10-29"


# ─── The forms ─────────────────────────────────────────────────────────────────


async def test_the_contact_form_is_filled_as_they_dictate_with_the_forms_country() -> None:
    llm = _llm()
    async with demo("enveedo", llm) as rig:
        await rig.driver.start_session(init={"path": CONTACT})
        await _event(rig, "page_changed", _page_changed(CONTACT, kind="contact", form="contact"))
        turn = await rig.driver.user_says("Please contact me, I'm Lucía.")
        check_turn(rig, turn)
        first = _commands(rig, "fill_form")[0]
        assert (
            first["form"] == "contact" and first["firstname"] == "Lucía" and first["email"] is None
        )
        await _event(rig, "command_done", {"command": "fill_form", "detail": "filled firstname"})
        await rig.driver.user_says("Pérez, from Spain, lucia at grupo dot es.")
        last = _commands(rig, "fill_form")[-1]
        assert (last["lastname"], last["country"], last["email"]) == (
            "Pérez",
            "Others",
            "lucia@grupo.es",
        )
        await rig.driver.user_says("And then?")
        result = tool_results(llm.captured_inputs[-1])["fill_form"]
        assert "Country set to the form's option «Others»: say it is not on the list" in result
        assert "Read the email back letter by letter" in result
        assert "they tick consent and press Submit themselves" in result


async def test_a_card_number_is_refused_and_a_country_is_the_forms_spelling() -> None:
    llm = _llm()
    async with demo("enveedo", llm) as rig:
        await rig.driver.start_session(init={"path": CONTACT})
        await rig.driver.user_says("My card is 4111 1111 1111 1111.")
        assert "fill_form" not in rig.actions()
        await rig.driver.user_says("We are in Chile.")
        assert _commands(rig, "fill_form")[-1]["country"] == "Chile"
        await rig.driver.user_says("And then?")
        results = tool_results_of(llm.captured_inputs[-1], "fill_form")
        assert results[0].startswith("Not filled: that looks like a card number")
    assert country_option("Estados Unidos") == "United States"
    assert country_option("México") == "Mexico"
    assert country_option("United Kingdom") == "Others"


async def test_the_soc2_request_off_its_page_opens_it_and_keeps_only_its_fields() -> None:
    llm = _llm()
    async with demo("enveedo", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Send me the SOC 2 report, I'm the CISO.")
        fill = _commands(rig, "fill_form")[0]
        assert fill["form"] == "soc2" and fill["job_title"] == "CISO" and fill["phone"] is None
        await rig.driver.user_says("And then?")
        result = tool_results(llm.captured_inputs[-1])["fill_form"]
        assert "The SOC 2 report request's page is opening" in result
        assert "phone is not on the SOC 2 request" in result


async def test_a_fill_asked_for_while_the_last_runs_waits_and_keeps_both() -> None:
    async with demo("enveedo", _llm()) as rig:
        await rig.driver.start_session(init={"path": CONTACT})
        await rig.driver.user_says("Please contact me, I'm Lucía.")
        await rig.driver.user_says("Pérez, from Spain, lucia at grupo dot es.")
        assert len(_commands(rig, "fill_form")) == 1, "a fill raced the last one"
        await _event(rig, "command_done", {"command": "fill_form", "detail": "filled firstname"})
        queued = _commands(rig, "fill_form")[1]
        assert queued["lastname"] == "Pérez" and queued["email"] == "lucia@grupo.es"


async def test_when_only_their_consent_is_left_he_says_so_once_in_the_quiet() -> None:
    llm = _llm()
    seen = llm.requests
    state = {
        "form": "contact",
        "filled": ["firstname", "lastname", "country", "email", "message"],
        "missing": ["consent"],
        "invalid": [],
        "values": {"firstname": "Lucía", "email": "lucia@grupo.es"},
        "ready": False,
        "by": "javier",
    }
    async with demo("enveedo", llm) as rig:
        await rig.driver.start_session(init={"path": CONTACT})
        await _event(rig, "form_state", state)
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        before = len(seen)
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "Tick consent and press Submit" in turn.text
        context = _texts(llm.captured_inputs[-1])
        assert "It holds: firstname: Lucía; email: lucia@grupo.es" in context
        (talk,) = seen[before:]
        assert talk.get("tool_choice") == "none"
        await _event(rig, "form_state", state)
        assert _idle_windows(rig)[-1] == _IDLE_MS


async def test_the_sites_answers_to_their_press_are_talked_through_never_called_sent() -> None:
    llm = _llm()
    async with demo("enveedo", llm) as rig:
        await rig.driver.start_session(init={"path": CONTACT})
        await _event(rig, "form_result", {"form": "contact", "outcome": "failed", "message": ""})
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "Press Submit again" in turn.text
        assert "info@enveedo.com" in _texts(llm.captured_inputs[-1])
        await _event(
            rig,
            "form_result",
            {
                "form": "contact",
                "outcome": "invalid",
                "message": "Invalid email.",
                "fields": ["email"],
            },
        )
        await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        context = _texts(llm.captured_inputs[-1])
        assert (
            "The site refused the contact form when they pressed Submit: Invalid email. (fields: email)"
            in context
        )
        await _event(
            rig, "form_result", {"form": "contact", "outcome": "sent", "message": "Thanks!"}
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "The team will reply" in turn.text
        assert "[The site confirmed the contact form was sent (Thanks!).]" in _texts(
            llm.captured_inputs[-1]
        )


async def test_a_fill_the_page_could_not_make_is_said() -> None:
    async with demo("enveedo", _llm()) as rig:
        await rig.driver.start_session(init={"path": CONTACT})
        await rig.driver.user_says("Please contact me, I'm Lucía.")
        await _event(rig, "command_failed", {"command": "fill_form", "reason": "no form"})
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "couldn't fill the form" in turn.text


# ─── Links, tabs, silent turns ─────────────────────────────────────────────────


async def test_links_open_in_a_new_tab_and_an_unknown_ebook_is_refused() -> None:
    llm = _llm()
    async with demo("enveedo", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Open the Gold Standard eBook.")
        assert _commands(rig, "open_link")[-1] == {
            "url": GOLD,
            "label": "The Gold Standard in Cyber Defense Planning and Optimization",
        }
        await rig.driver.user_says("Open the platform PDF.")
        assert _commands(rig, "open_link")[-1]["url"] == PDF
        await rig.driver.user_says("Open some ebook about cats.")
        await rig.driver.user_says("And then?")
        assert len(_commands(rig, "open_link")) == 2
        results = tool_results_of(llm.captured_inputs[-1], "open_link")
        assert "It is gated: they register there themselves." in results[0]
        assert results[-1].startswith("Not opened: no eBook or webinar matches 'cats'")


async def test_tabs_are_read_in_and_switching_is_checked() -> None:
    llm = _llm()
    async with demo("enveedo", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _event(
            rig,
            "tabs_changed",
            {
                "tabs": [
                    {"tab_id": "11", "url": "https://enveedo.com/", "title": "Home"},
                    {
                        "tab_id": "12",
                        "url": "https://enveedo.com/frameworks",
                        "title": "Frameworks",
                    },
                ],
                "active": "12",
            },
        )
        await rig.driver.user_says("Go back to the other tab.")
        assert "11: Home; 12: Frameworks (in front)" in _texts(llm.captured_inputs[-1])
        assert rig.command("focus_tab") == {"tab_id": "11"}
        assert _cues(rig) == []


async def test_a_silent_move_gets_his_written_line() -> None:
    async with demo("enveedo", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("Show me the PDF.")
        check_turn(rig, turn)
        assert turn.text.strip() == _LANDED["link"]["en"]


async def test_a_reply_that_only_promises_is_asked_once_more() -> None:
    async with demo("enveedo", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("What about the price?")
        check_turn(rig, turn)
        assert "Pricing isn't published" in turn.text


async def test_a_missed_cue_is_noted_quietly() -> None:
    llm = _llm()
    async with demo("enveedo", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _event(rig, "command_failed", {"command": "cue", "reason": "no place X"})
        await rig.driver.user_says("And then?")
        seen = _texts(llm.captured_inputs[-1])
        assert "A screen cue of yours did not land (no place X)" in seen
        assert "Tell the visitor plainly" not in seen


# ─── The voice ─────────────────────────────────────────────────────────────────


async def test_acronyms_are_said_as_people_say_them_and_read_back_as_written() -> None:
    llm = _llm()
    async with demo("enveedo", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("Do you have SOC 2?")
        check_turn(rig, turn)
        assert "a sock two Type II report, for any see-so." in turn.text, turn.text
        # The page waits for the words the voice says.
        assert _cues(rig)[0]["at"] == "yes a sock"
        await rig.driver.user_says("And then?")
        context = _texts(llm.captured_inputs[-1])
        assert "a SOC 2 Type II report, for any CISO." in context and "sock two" not in context


@pytest.mark.parametrize(
    ("written", "en", "es"),
    [
        ("SOC 2", "sock two", "sok dos"),
        ("ISO 27001", "ISO twenty-seven oh oh one", "ISO veintisiete mil uno"),
        ("ISO/IEC 42001:2023", "ISO forty-two oh oh one", "ISO cuarenta y dos mil uno"),
        ("a vCISO for MSSPs", "a vee see-so for M S S Ps", "a ve siso for eme ese ese pes"),
        ("NIS2 and GRC", "NIS two and G R C", "NIS dos and ge erre ce"),
        (
            "valued at $2,500 USD",
            "valued at two thousand five hundred dollars",
            "valued at dos mil quinientos dólares",
        ),
    ],
)
def test_the_voice_spelling_and_back(written: str, en: str, es: str) -> None:
    assert for_the_voice(written, "en") == en
    assert for_the_voice(written, "es") == es
    back = written.replace("ISO/IEC 42001:2023", "ISO 42001").replace(" USD", "")
    assert from_the_voice(en) == back and from_the_voice(es) == back


# ─── What he never says or does ────────────────────────────────────────────────


def test_the_prompt_carries_the_honesty_rules_and_the_buttons_stay_theirs() -> None:
    prompt = ev._prompt(SITE)
    for rule in (
        "The knowledge opens with what the site does NOT say",
        "Testimonials are anonymous: never name them.",
        '"More than forty-five frameworks" is the home page\'s claim; the frameworks page lists thirty-nine.',
        "Never say it is supported.",
        "YOU NEVER TICK THE BOX OR PRESS SUBMIT",
        "The final confirm button is theirs to press, always.",
        "in this preview the booking is not sent to Enveedo",
        "Never accept or decline the cookie banner",
        "never name a day",
        "Never send anyone to the footer's social icons",
        "The call starts in English unless the visitor chose Spanish or is on the Spanish site.",
    ):
        assert rule in prompt, rule
    assert "## What the site does NOT say" in prompt


def test_no_action_can_submit_or_tick() -> None:
    actions = {
        ev.Navigate,
        ev.Cue,
        ev.ShowSection,
        ev.OpenLink,
        ev.BookDemo,
        ev.FillForm,
        ev.FocusTab,
        ev.LanguageChanged,
    }
    for action in actions:
        fields = set(action.model_fields)
        assert not fields & {"submit", "send", "confirm", "consent", "press", "click"}, action
    assert set(ev.FillForm.model_fields) >= {"form", "firstname", "lastname", "email", "country"}


def test_the_brain_never_fetches_the_site() -> None:
    backend = Path(ev.__file__).parent
    for source in backend.glob("*.py"):
        text = source.read_text(encoding="utf-8")
        imports = r"^\s*(?:import|from)\s+(?:httpx|aiohttp|requests|socket|http\.client|urllib\.request)\b"
        assert not re.search(imports, text, re.MULTILINE), source


def test_his_lines_for_a_move_exist_in_both_languages() -> None:
    for kind, lines in _LANDED.items():
        assert set(lines) == {"en", "es"}, kind
        assert all(line.strip() for line in lines.values()), kind
    assert set(TOGGLE_CONFIRM) == {"en", "es"}


def test_the_floor_is_held_as_the_clini_guide_learned() -> None:
    assert ev.ACK_HOLD_AFTER_S >= 5.5 and ev.ACK_SORRY_AFTER_S >= 15
    assert ev.HOLD_WITHOUT_NOD_S <= 3.0
    assert (ev.MODEL, ev.REASONING) == ("gpt-6.1-terra", "low")


# ─── The committed knowledge ───────────────────────────────────────────────────


def _catalogue() -> dict[str, Any]:
    path = Path(kb.__file__).parent / "knowledge" / "L3" / "anchors.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_committed_catalogue_has_the_same_keys_in_both_languages() -> None:
    cat = _catalogue()
    pages = cat["pages"]
    assert {"/", "/es/", FRAMEWORKS, DEMO, CONTACT, TRUST, FAQ, PARTNERS, SPOS} <= set(pages)
    for path, entry in pages.items():
        twin = entry["twin"]
        if entry["lang"] != "en" or twin is None:
            continue
        assert pages[twin]["twin"] == path and pages[twin]["lang"] == "es"
        assert [a["key"] for a in entry["anchors"]] == [a["key"] for a in pages[twin]["anchors"]], (
            path
        )
    # The hidden content opens by its own control.
    home = {a["key"]: a for a in pages["/"]["anchors"]}
    for key in (
        "how_business_first",
        "how_integration",
        "how_automation",
        "how_reporting",
        "toggle_with",
        "toggle_without",
    ):
        assert set(home[key]["reveal"]) == {"click", "open"}, key
    faq = [a for a in pages[FAQ]["anchors"] if a["key"].startswith("faq_") and "reveal" in a]
    assert len(faq) == 15
    about = {a["key"] for a in pages["/about-us"]["anchors"] if "reveal" in a}
    assert about == {"tab_mission", "tab_vision", "tab_philosophy"}
    for path in (FRAMEWORKS, "/es/frameworks"):
        cards = [a for a in pages[path]["anchors"] if a["key"].startswith("fw_")]
        assert len(cards) == 39, path
    # The buttons are the adapter's, never offered.
    assert all(
        a.get("hidden")
        for a in pages[CONTACT]["anchors"]
        if a["key"].endswith(("_submit", "_consent"))
    )
    assert cat["_meta"]["scroll_offset_px"] == 90


def test_every_key_the_prompt_offers_is_in_the_catalogue() -> None:
    real = kb.load()
    if not real.pages:
        pytest.skip("no crawl committed yet")
    cat = _catalogue()
    keys = {a["key"] for page in cat["pages"].values() for a in page["anchors"]}
    keys |= {a["key"] for part in ("header", "footer") for a in cat[part]}
    prompt = ev._prompt(real)
    places = prompt.split("# Places on the site")[1]
    for key in re.findall(r"^\s+- ([a-z0-9_]+):", places, re.MULTILINE):
        assert key in keys, key
    for listed in re.findall(r"\(places: ([^)]*)\)", places):
        for key in listed.split(", "):
            assert key in keys, key
    # Every framework find_framework can name is a card on both pages.
    fw = {a["key"] for a in cat["pages"][FRAMEWORKS]["anchors"]}
    assert {f.key for f in real.frameworks} <= fw
    assert all(f.blurb for f in real.frameworks)
    # Every target a backstop or a named place shows is a real place.
    for _, (path, key) in ev._ASKED:
        if key is not None:
            assert key in {a.key for a in real.anchors_on(path)}, (path, key)
    for _, path, key in ev._NAMED:
        assert key in {a.key for a in real.anchors_on(path)}, (path, key)
    # The links the prompt names are the ones open_link opens.
    assert {"scheduler", "sign_in", "blog", "blog_es", "platform_pdf"} <= set(real.exits)
    assert any("Hail & Cotton" in x.label for x in real.library)
    # Spanish words find English paths.
    assert real.english_path("/es/book-a-demo-rsa") == "/book-a-demo-grl"
    assert all(not h.path.startswith("/es/") for h in real.search("evaluación de riesgos gratuita"))
    assert real.topics.keys() >= {"platform", "frameworks", "faq", "site-map", "booking-a-demo"}


@pytest.mark.parametrize(
    ("sentence", "key"),
    [
        # Dev call f89030a6: the six modules said with no cue rang only the
        # section's heading.
        ("Crown Jewel Analysis maps critical business functions to assets.", "mod_crown_jewel"),
        (
            "Risk Register tracks risks, while Compliance Management maps controls.",
            "mod_risk_register",
        ),
        ("Vendor Risk Management assesses suppliers.", "mod_vendor_risk"),
        ("Incident Response Manager organizes response plans.", "mod_incident_response"),
        ("Security Roadmap prioritizes initiatives and tracks progress.", "mod_roadmap"),
        ("El Registro de Riesgos consolida tus riesgos.", "mod_risk_register"),
        ("La Gestión de Cumplimiento mapea los controles una vez.", "mod_compliance"),
    ],
)
def test_a_module_he_names_rings_its_own_card(sentence: str, key: str) -> None:
    from enveedo.backend.brain import named_place

    assert named_place(sentence) == ("/enveedo_platform", key)
