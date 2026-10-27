"""Javier, Saint George's College's guide, end to end over the wire — no network, no LLM key.

The real ``SaintGeorgeBrain`` on a real ``brain_server`` socket, driven by the
conformance ``VoqalizeDriver``, with only the model scripted. The knowledge is a
small invented school in the crawl's own shape, put in place of the committed
one, so no test depends on what the crawl found this week.

What this demo earns that others do not:

**What changes is read live, in the visitor's browser.** The fees, the
admission status and the calendar are asked of the page (``show_fees``,
``show_events``), which reads them and answers with an event; he says them
only from that answer, once his own speech is over, with tools off. A failed
read is said as a failure, never guessed.

**Nothing is sent for them.** The site has no form: the contact card readies
an email the parent opens and sends; a RUT never goes in it; nothing on the
wire claims it was sent. Logins open in a new tab only from the site's links.

**One move at a time.** A move the page answers holds the next until it has.

**Spanish first, and "tú".** The site is Chilean, so the call opens in
Spanish, follows a visitor who speaks English, and holds a language they chose.

Run: ``cd demos && uv run pytest tests/test_saintgeorge_e2e.py``
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import (
    ScriptedOpenAI,
    call,
    every_tool_result,
    input_texts,
    reply,
    reply_and_call,
    tool_results,
)

from ._harness import _configs, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.saintgeorge import brain as sg  # noqa: E402
from voqalize_demos._loaded.saintgeorge import knowledge as kb  # noqa: E402
from voqalize_demos._loaded.saintgeorge.brain import (  # noqa: E402
    _IDLE_MS,
    _LANDED,
    _TALK_THROUGH_MS,
    ADMISSIONS_EMAIL,
    TOGGLE_CONFIRM,
    asked_page,
    greeting,
    language_of,
)
from voqalize_demos._loaded.saintgeorge.knowledge import (  # noqa: E402
    Card,
    Faq,
    Knowledge,
    Link,
    Page,
    Section,
)

# ─── An invented school ────────────────────────────────────────────────────────

ADMISION = "/admision/admision"
INFANT = "/unidad/infant"
ELEMENTARY = "/unidad/elementary"
SPORTS = "/formacion-integral/area-deportiva"
MUSICAL = "/familia/musical-the-lion-king"
SCHEDULE = "https://saintgeorge.cl/wp-content/uploads/2025/10/Horario-Deporte-2026.pdf"
TICKETS = "https://ticketplus.cl/events/musical-the-lion-king"

# Invented, in the crawl's shape: the names are the school's kind, the facts ours.
SITE = Knowledge(
    l1="Saint George's College is a school in Santiago (invented for tests).",
    topics={},
    pages={
        "/": Page(
            "/",
            "Saint George's College | Inicio",
            kind="home",
            sections=(
                Section("Nuestra comunidad", "Infant Elementary Junior Senior"),
                Section("La misión que nos convoca", "Un colegio de la Congregación."),
                Section("Nuestros valores que guían la acción educativa", "Respeto Caridad"),
            ),
            cards=(Card("Infant"), Card("Elementary")),
        ),
        INFANT: Page(
            INFANT,
            "Infant",
            kind="unit",
            sections=(Section("Infant", "Pre-Kínder y Kínder."),),
            faqs=(Faq("Dirección y equipo Infant", ""), Faq("PRE KINDER", ""), Faq("KINDER", "")),
        ),
        ELEMENTARY: Page(
            ELEMENTARY,
            "Elementary",
            kind="unit",
            sections=(Section("Elementary", "De primero a cuarto básico."),),
            faqs=(
                Faq("Dirección y equipo Elementary", ""),
                Faq("1º BÁSICO", ""),
                Faq("2º BÁSICO", ""),
            ),
        ),
        ADMISION: Page(
            ADMISION,
            "Admisión",
            sections=(Section("Admisión", "Escribir a admisiones."),),
        ),
        SPORTS: Page(
            SPORTS,
            "Área Deportiva",
            sections=(Section("Área Deportiva", "Sin especialización temprana."),),
            faqs=(Faq("CONOCE AL EQUIPO", ""),),
            links=(Link("HORARIOS DEPORTE 2026", SCHEDULE, "Área Deportiva"),),
        ),
        MUSICAL: Page(
            MUSICAL,
            "The Lion King",
            sections=(Section("The Lion King", "Funciones en noviembre."),),
            links=(Link("", TICKETS, "The Lion King"),),
        ),
    },
)


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every session reads the invented school, and he never nods unless a
    test asks him to: a nod is a unit of its own."""
    monkeypatch.setattr(kb, "KNOWLEDGE", SITE)
    monkeypatch.setattr(sg, "ACK_RATE", 0.0)
    yield


# ─── Reading the wire ──────────────────────────────────────────────────────────


def _results(items: list[Any]) -> dict[str, str]:
    return tool_results(items)


def _texts(items: list[Any]) -> str:
    return input_texts(items)


async def _page(rig: object, event: str, payload: dict[str, object]) -> None:
    await rig.driver.send_ui_event(event, payload)  # type: ignore[attr-defined]
    # `on_rtvi` takes no floor and there is nothing to await: give it a moment.
    await asyncio.sleep(0.1)


def _idle_windows(rig: object) -> list[int | None]:
    return [c.idle.timeout_ms for c in _configs(rig) if c.idle is not None]  # type: ignore[arg-type]


def _language_changes(rig: object) -> list[object]:
    return _commands(rig, "language_changed")


def _commands(rig: object, name: str) -> list[dict[str, object]]:
    return [c["payload"] for c in rig.driver.ui_commands if c.get("command") == name]  # type: ignore[attr-defined]


def _cues(rig: object) -> list[dict[str, object]]:
    return _commands(rig, "cue")


NONE = {"path": None, "heading": None, "text": None, "faq": None}


def _page_changed(path: str, **fields: object) -> dict[str, object]:
    return {"url": f"https://saintgeorge.cl{path}/", "path": f"{path}/", "title": "", **fields}


FEES = {
    "url": "https://saintgeorge.cl/admision/admision/",
    "heading": "Valores referenciales año 2026",
    "fees": [
        {"label": "Cuota de Incorporación por estudiante", "value": "UF 85", "note": ""},
        {"label": "Matrícula anual por estudiante", "value": "UF 13,5", "note": ""},
        {
            "label": "Colegiatura mensual por estudiante",
            "value": "UF 18",
            "note": "(puede variar dependiendo el nivel)",
        },
    ],
    "status": [
        "Admisión 2027: Para información de vacantes disponibles escribir a admisiones@saintgeorge.cl",
        "Admisión Pre Kínder 2028: Información a partir de noviembre.",
    ],
}

EVENTS = {
    "today": "2026-10-22",
    "events": [
        # Under way since before today: the calendar sends what has not ended.
        {"date": "2026-10-16", "time": "", "end": "2026-10-23", "title": "Semana Amarilla"},
        {
            "date": "2026-10-23",
            "time": "08:15",
            "end": "2026-10-23",
            "title": "Liturgia de la palabra de 2°E",
        },
        {
            "date": "2026-10-27",
            "time": "",
            "end": "2026-10-27",
            "title": "Visita de los abuelos PKA y PKG 10:00 hrs.",
        },
        {"date": "2026-10-30", "time": "", "end": "2026-11-02", "title": "Fin de semana largo"},
        {
            "date": "2026-11-05",
            "time": "",
            "end": "2026-11-05",
            "title": "Reunión de apoderados Kínder",
        },
        {
            "date": "2026-11-20",
            "time": "19:00",
            "end": "2026-11-20",
            "title": "Musical The Lion King",
        },
    ],
}

# ─── The script ────────────────────────────────────────────────────────────────


def _llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            # English heard: both legs move before he answers.
            "can you tell me about the school": reply(
                "{page: /}{show: Nuestra comunidad} We have four units. Want to see them?"
            ),
            "¿Qué unidades tienen?": reply(
                "{page: /}{show: Nuestra comunidad} Tenemos cuatro unidades. ¿Te muestro una?"
            ),
            # Spanish heard with English chosen: he answers in English.
            "¿Qué niveles tienen?": reply(
                "{page: /}{show: Nuestra comunidad} There are four units. Want to see one?"
            ),
            "I am asking you in English now": reply("Claro, te sigo en español. ¿Qué buscas?"),
            "¿Puedes hablar en inglés?": reply_and_call(
                "Sure, let's continue in English.", "set_language", args={"language": "en"}
            ),
            # The home tour, and a grade by its words whatever its ordinal mark.
            "Cuéntame del colegio.": reply(
                "{page: /}{show: Nuestra comunidad} Somos una comunidad grande. "
                "{show: la mision que nos convoca} Somos un colegio católico. "
                "{page: /luna}{show: Nuestros valores} Siete valores nos guían."
            ),
            "Mi hija tiene seis años.": reply(
                "{page: /unidad/elementary}{faq: 1° basico} Sería primero básico. "
                "{show: DESCRIPCION} Aquí está su curso."
            ),
            "¿Y Kínder?": [
                reply("{faq: KINDER} Kínder es el segundo año de Infant."),
                reply("{faq: KINDER} Kínder es el segundo año de Infant."),
            ],
            # He forgot to show what they asked about: their page goes first.
            "¿Tienen deportes?": reply(
                "Sí, muchos. El programa evita la especialización temprana."
            ),
            "¿Cuánto cuesta?": reply_and_call(
                "Te muestro los valores en la página de admisión.", "show_fees"
            ),
            "¿Cómo es la admisión?": reply_and_call(
                "Te muestro la admisión.", "show_fees", args={"about": "admission"}
            ),
            "¿Qué eventos vienen para Kínder?": reply_and_call(
                "Te muestro el calendario.", "show_events", args={"query": "Kínder"}
            ),
            "¿Qué viene en noviembre?": reply_and_call(
                "Te muestro el calendario.", "show_events", args={"query": "noviembre"}
            ),
            "¿Qué viene en diciembre?": reply_and_call(
                "Te muestro el calendario.", "show_events", args={"query": "diciembre"}
            ),
            "Y los eventos también.": reply_and_call("Claro.", "show_events", args={"query": ""}),
            # Talk-throughs, keyed on the page's answer.
            "show_fees done": reply(
                "La cuota de incorporación es de ochenta y cinco UF. ¿Te ayudo a escribir a admisiones?"
            ),
            "show_fees not done": reply("Ahora no puedo ver los valores. Están en la página."),
            "show_events done": reply("El cinco de noviembre hay reunión de Kínder."),
            "show_contact_card done": reply(
                "Listo, el correo está en pantalla para que lo envíes."
            ),
            "email button": reply("Ya está en tu correo, listo para que lo revises y lo envíes."),
            # The contact card.
            "Quiero escribirle a admisión.": reply_and_call(
                "Claro. ¿Cómo te llamas?",
                "show_contact_card",
                args={"parent_name": "", "question": ""},
            ),
            "Me llamo Ana, mi RUT es 12.345.678-5.": reply_and_call(
                "Gracias, Ana.",
                "show_contact_card",
                args={
                    "parent_name": "Ana",
                    "child_age": "5",
                    "question": "Mi RUT es 12.345.678-5. ¿Hay vacantes?",
                },
            ),
            "Me llamo Ana Pérez, es para mi hija de cinco.": reply_and_call(
                "Listo, Ana. Te dejé el correo en pantalla.",
                "show_contact_card",
                args={
                    "parent_name": "Ana Pérez",
                    "child": "daughter",
                    "child_age": "cinco años",
                    "grade": "Kínder 2027",
                    "question": "¿Hay vacantes para Kínder 2027?",
                },
            ),
            "Write to admissions for me, I'm Tom.": reply_and_call(
                "Done, Tom. The email is on your screen.",
                "show_contact_card",
                args={
                    "parent_name": "Tom",
                    "child": "son",
                    "grade": "3rd grade",
                    "question": "Can we visit the school?",
                },
            ),
            # Links: the page's own, the knowledge's, the portals; never elsewhere.
            "Ábreme el horario de deportes.": reply_and_call(
                "Te lo abrí.",
                "open_link",
                args={"kind": "document", "label": "horarios deporte"},
            ),
            "Quiero entradas para el musical.": reply_and_call(
                "Te abrí las entradas.", "open_link", args={"kind": "musical_tickets"}
            ),
            "Ábreme Schoolnet.": reply_and_call(
                "Te abrí Schoolnet.", "open_link", args={"kind": "schoolnet"}
            ),
            "Ábreme ese documento.": reply_and_call(
                "Te lo abrí.", "open_link", args={"kind": "document", "label": "Reglamento"}
            ),
            "¿Y entonces?": reply("Te cuento."),
            # Tabs.
            "Vuelve a la otra pestaña.": reply_and_call(
                "Ahí está.", "switch_tab", args={"tab_id": "11"}
            ),
            # A move with no words gets his written line at once.
            "Ábreme las entradas.": [call("open_link", args={"kind": "musical_tickets"})],
            # A reply that only promises more says nothing: asked once more.
            "¿Y el casino?": [reply("Un momento."), reply("El casino tiene menús mensuales.")],
        }
    )


# ─── Greeting and voice ────────────────────────────────────────────────────────


async def test_greeting_and_voice_reach_the_wire_in_spanish() -> None:
    """A written opener, and javier in Spanish on both legs before it."""
    async with demo("saintgeorge", _llm()) as rig:
        opener = await rig.driver.start_session(init={"surface": "saintgeorge-ext", "path": "/"})
        check_greeting(rig, opener)
        assert opener is not None and opener.text == greeting("/", "es")
        assert opener.text.startswith("Hola, soy Javier, tu guía del Saint George's College.")
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _idle_windows(rig) == [_IDLE_MS]
        assert _language_changes(rig) == []


@pytest.mark.parametrize(
    ("path", "words"),
    [
        ("/admision/admision/", "admisión y los valores"),
        ("/admision/admision-programa-moreau/", "Programa Moreau"),
        ("/unidad/junior/", "esta unidad y sus cursos"),
        ("/familia/calendario/", "próximos eventos"),
        ("/familia/musical-the-lion-king/", "The Lion King"),
        ("/colegio/historia/", "¿Qué edad tiene tu hijo o hija?"),
    ],
)
def test_the_opener_follows_the_page(path: str, words: str) -> None:
    assert words in greeting(path, "es")
    assert greeting(path, "en").startswith("Hi, I'm Javier, your guide to Saint George's College.")


async def test_a_call_started_in_english_opens_in_english_and_holds() -> None:
    llm = _llm()
    async with demo("saintgeorge", llm) as rig:
        opener = await rig.driver.start_session(init={"path": "/", "lang": "en"})
        check_greeting(rig, opener)
        assert opener is not None and opener.text == greeting("/", "en")
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        turn = await rig.driver.user_says("¿Qué niveles tienen?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert _language_changes(rig) == []
        assert "The visitor chose English before the call" in _texts(llm.captured_inputs[-1])


async def test_the_toggle_switches_both_legs_and_confirms_each_way() -> None:
    async with demo("saintgeorge", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(rig, "language_requested", {"language": "es"})
        assert _language_changes(rig) == []
        await _page(rig, "language_requested", {"language": "en"})
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert rig.command("language_changed") == {"language": "en"}
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert turn.text == TOGGLE_CONFIRM["en"]
        assert _idle_windows(rig)[-1] == _IDLE_MS
        await _page(rig, "language_requested", {"language": "es"})
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert turn.text == TOGGLE_CONFIRM["es"]
        # Chosen on the toggle, it holds whatever they speak.
        turn = await rig.driver.user_says("I am asking you in English now, okay?")
        assert "en español" in turn.text
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _language_changes(rig) == [{"language": "en"}, {"language": "es"}]


async def test_english_heard_switches_before_he_answers_and_spanish_switches_back() -> None:
    async with demo("saintgeorge", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("Hi, can you tell me about the school?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        turn = await rig.driver.user_says("¿Qué unidades tienen?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _language_changes(rig) == [{"language": "en"}, {"language": "es"}]


async def test_asking_for_english_switches_and_opens_no_page() -> None:
    async with demo("saintgeorge", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Puedes hablar en inglés?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert _language_changes(rig) == [{"language": "en"}]
        assert _cues(rig) == []


@pytest.mark.parametrize(
    ("text", "sure", "lang"),
    [
        ("¿Puedes hablar en inglés?", True, "es"),
        ("Mi hija tiene cinco años", True, "es"),
        ("Hola", True, None),
        ("Can you show me the school?", True, "en"),
        ("Kínder", True, None),
        ("Claro.", False, "es"),
        ("Sure, here it is.", False, "en"),
        ("{faq: 1º BÁSICO} That is first grade, here it is.", False, "en"),
    ],
)
def test_the_language_a_line_is_in(text: str, sure: bool, lang: str | None) -> None:
    assert language_of(text, sure=sure) == lang


# ─── Cues ──────────────────────────────────────────────────────────────────────


async def test_the_home_tour_cues_are_checked_against_the_site() -> None:
    async with demo("saintgeorge", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/colegio/historia"})
        turn = await rig.driver.user_says("Cuéntame del colegio.")
        check_turn(rig, turn)
        assert "{" not in turn.text and "Somos un colegio católico." in turn.text
        # The page; its sections in the site's own spelling; an invented page,
        # and the cue after it on that page, dropped.
        assert _cues(rig) == [
            {**NONE, "at": "somos una comunidad", "word": 0, "path": "/"},
            {
                **NONE,
                "at": "somos una comunidad",
                "word": 0,
                "path": "/",
                "heading": "Nuestra comunidad",
            },
            {
                **NONE,
                "at": "somos un colegio",
                "word": 4,
                "path": "/",
                "heading": "La misión que nos convoca",
            },
            {
                **NONE,
                "at": "siete valores nos",
                "word": 8,
                "path": "/",
                "heading": "Nuestros valores que guían la acción educativa",
            },
        ]


async def test_a_grade_opens_by_its_words_and_an_invented_heading_is_dropped() -> None:
    async with demo("saintgeorge", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Mi hija tiene seis años.")
        assert _cues(rig) == [
            {**NONE, "at": "seria primero basico", "word": 0, "path": ELEMENTARY},
            {
                **NONE,
                "at": "seria primero basico",
                "word": 0,
                "path": ELEMENTARY,
                "faq": "1º BÁSICO",
            },
        ]


async def test_a_grade_on_another_units_page_opens_there() -> None:
    async with demo("saintgeorge", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(
            rig, "page_changed", _page_changed("/", kind="home", headings=["Nuestra comunidad"])
        )
        await rig.driver.user_says("¿Y Kínder?")
        assert _cues(rig) == [
            {**NONE, "at": "kinder es el", "word": 0, "path": INFANT, "faq": "KINDER"},
        ]
        # On the unit's own page, the live accordion is opened in place.
        await _page(
            rig, "page_changed", _page_changed(INFANT, kind="unit", faqs=["PRE KINDER", "KINDER"])
        )
        await rig.driver.user_says("¿Y Kínder?")
        assert _cues(rig)[1] == {**NONE, "at": "kinder es el", "word": 0, "faq": "KINDER"}


async def test_what_they_asked_about_is_shown_when_his_reply_forgets_to() -> None:
    async with demo("saintgeorge", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Tienen deportes?")
        check_turn(rig, turn)
        assert _cues(rig)[0] == {**NONE, "at": "si muchos", "word": 0, "path": SPORTS}


def test_the_page_for_what_they_asked_about() -> None:
    for ask, path in (
        ("¿Tienen deportes?", SPORTS),
        ("Do you have sports?", SPORTS),
        ("¿Cómo es Kínder?", INFANT),
        ("Tell me about the Programa Moreau", "/admision/admision-programa-moreau"),
        ("¿Qué es Cambridge English?", "/formacion-integral/direccion_de_estudios"),
        ("Tell me about the Lion King musical", MUSICAL),
        ("¿Cómo postulo?", ADMISION),
        ("¿Cuáles son sus valores?", "/"),
        # A specific page beats the home page, which "comunidad" also names.
        ("La comunidad de Elementary", ELEMENTARY),
    ):
        assert asked_page(ask) == path, ask
    for ask in (
        # Moved by their tools, not by a cue.
        "¿Cuánto cuesta?",
        "How much is the tuition?",
        "¿Qué eventos vienen?",
        "What's coming up?",
        "Quiero escribirle a admisión por correo.",
        "Entradas para el musical",
        "Vuelve a la otra pestaña.",
        # A request about the call's own language is not a page.
        "Can you speak English?",
        "¿Puedes hablar en inglés?",
        "Mm-hmm",
    ):
        assert asked_page(ask) is None, ask


# ─── The fees, read live ───────────────────────────────────────────────────────


async def test_the_fees_are_read_on_the_page_and_said_only_from_that_read() -> None:
    llm = _llm()
    seen = llm.requests
    async with demo("saintgeorge", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Cuánto cuesta?")
        check_turn(rig, turn)
        # The move returned at once and no cue raced it to the page.
        assert rig.command("show_fees") == {"path": ADMISION, "about": "fees"}
        assert _cues(rig) == []
        await rig.driver.user_says("¿Y entonces?")
        result = _results(llm.captured_inputs[-1])["show_fees"]
        assert result.startswith("Sent: the page is opening the admission page")
        assert "UF" not in result
        # The page reads them and answers; he says them in the next quiet spell.
        await _page(rig, "fees_read", FEES)
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        before = len(seen)
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "ochenta y cinco UF" in turn.text
        context = _texts(llm.captured_inputs[-1])
        assert "Cuota de Incorporación por estudiante: UF 85" in context
        assert (
            "Colegiatura mensual por estudiante: UF 18 (puede variar dependiendo el nivel)"
            in context
        )
        assert "Admisión Pre Kínder 2028: Información a partir de noviembre." in context
        assert "Say these values now, exactly as the page writes them" in context
        (talk,) = seen[before:]
        assert talk.get("tool_choice") == "none"
        assert _idle_windows(rig)[-1] == _IDLE_MS


async def test_admission_status_asks_for_the_status_lines() -> None:
    llm = _llm()
    async with demo("saintgeorge", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("¿Cómo es la admisión?")
        assert rig.command("show_fees") == {"path": ADMISION, "about": "admission"}
        await _page(rig, "fees_read", FEES)
        await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "Say what the page says about admission now" in _texts(llm.captured_inputs[-1])


async def test_a_failed_read_is_said_as_a_failure_never_guessed() -> None:
    llm = _llm()
    async with demo("saintgeorge", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("¿Cuánto cuesta?")
        await _page(
            rig, "command_failed", {"command": "show_fees", "reason": "no fees on the page"}
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "no puedo ver los valores" in turn.text
        context = _texts(llm.captured_inputs[-1])
        assert "You cannot see the fees right now: never guess them." in context
        assert "never guess a value or a date" in context


def test_the_prompt_says_fees_and_dates_only_from_a_live_read() -> None:
    prompt = sg._prompt(SITE)
    assert "ONLY from a bracketed line the page read during this call" in prompt
    assert "call show_fees" in prompt and "call show_events" in prompt
    # The levels, with each grade's accordion as its page writes it.
    assert f"- Elementary — {ELEMENTARY} — grade accordions: 1º BÁSICO; 2º BÁSICO" in prompt
    assert "- Senior — /unidad/senior — grade accordions: 9°; 10°; 11°; 12°" in prompt


def test_the_brain_never_fetches_the_site() -> None:
    """The brain runs far from Chile, where the site does not answer: every
    live read is the visitor's browser's. No module of the brain opens a
    connection of its own."""
    backend = Path(sg.__file__).parent
    for source in backend.glob("*.py"):
        text = source.read_text(encoding="utf-8")
        imports = r"^\s*(?:import|from)\s+(?:httpx|aiohttp|requests|socket|http\.client|urllib\.request)\b"
        assert not re.search(imports, text, re.MULTILINE), source


def test_the_committed_knowledge_loads_and_holds_no_fee_value() -> None:
    """The crawl and the topics wrote this year's fees down; they are taken out
    as the layers load, so neither the prompt nor a search can quote them, and
    the site's empty pages are left out so no move lands on one."""
    real = kb.load()
    if not real.pages:
        pytest.skip("no crawl committed yet")
    assert {INFANT, ELEMENTARY, ADMISION, SPORTS, MUSICAL} <= set(real.pages)
    assert "/admision" not in real.pages and "/formacion-integral" not in real.pages
    fee = re.compile(r"\bUF\s*\d", re.IGNORECASE)
    assert not fee.search(sg._prompt(real))
    assert not any(fee.search(t.text) for t in real.topics.values())
    for hit in real.search("valores referenciales matrícula colegiatura cuota", 10):
        assert not fee.search(hit.snippet), hit
    assert kb.redact_fees("Matrícula: UF 13,5 y UF 18.") == (
        "Matrícula: UF (read live: show_fees) y UF (read live: show_fees)."
    )
    # The admission status is read live too: no layer says which years are open.
    status = re.compile(r"Admisi[oó]n (?:Pre K[ií]nder )?\d{4}: (?!\(read live)", re.IGNORECASE)
    assert not status.search(sg._prompt(real))
    assert not any(status.search(t.text) for t in real.topics.values())
    assert not status.search(real.pages[ADMISION].text)
    assert "a partir de noviembre" not in real.pages[ADMISION].text
    assert kb.redact_live("Admisión 2027: Escribir a admisiones@saintgeorge.cl Valores: UF 85") == (
        'Admisión 2027: (read live: show_fees about="admission") Valores: UF (read live: show_fees)'
    )


# ─── The calendar, read live ───────────────────────────────────────────────────


async def test_the_calendar_is_read_in_the_browser_and_the_asked_events_said() -> None:
    llm = _llm()
    async with demo("saintgeorge", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("¿Qué eventos vienen para Kínder?")
        assert rig.command("show_events") == {"path": "/familia/calendario", "count": 30}
        await _page(rig, "events_read", EVENTS)
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        context = _texts(llm.captured_inputs[-1])
        assert (
            "the next events matching 'Kínder': 2026-11-05 (jueves): Reunión de apoderados Kínder."
            in context
        )
        assert "Liturgia" not in context.split("matching 'Kínder'")[1].split("]")[0]
        assert "Say the two or three of these that matter to this family" in context


async def test_a_month_with_nothing_says_so_and_names_whats_coming() -> None:
    llm = _llm()
    async with demo("saintgeorge", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("¿Qué viene en diciembre?")
        await _page(rig, "events_read", EVENTS)
        await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        context = _texts(llm.captured_inputs[-1])
        assert "None of the coming events matches what they asked" in context
        assert "2026-10-23 (viernes) 08:15: Liturgia de la palabra de 2°E" in context


async def test_an_event_under_way_is_said_by_when_it_ends() -> None:
    llm = _llm()
    async with demo("saintgeorge", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("¿Qué viene en noviembre?")
        await _page(rig, "events_read", EVENTS)
        await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        context = _texts(llm.captured_inputs[-1])
        listed = context.split("matching 'noviembre': ")[1].split("]")[0]
        # A span that runs into the month matches it; one over before it does not.
        assert listed.startswith(
            "2026-10-30 (viernes) to 2026-11-02 (lunes): Fin de semana largo; "
            "2026-11-05 (jueves): Reunión de apoderados Kínder"
        )
        assert "Semana Amarilla" not in listed
        assert "never as if it were still to start" in context


async def test_the_whole_list_puts_a_running_week_first_with_its_end() -> None:
    llm = _llm()
    async with demo("saintgeorge", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("¿Qué viene en diciembre?")
        await _page(rig, "events_read", EVENTS)
        await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        context = _texts(llm.captured_inputs[-1])
        assert "under way, until 2026-10-23 (viernes): Semana Amarilla" in context


async def test_one_move_at_a_time_the_next_follows_the_answer() -> None:
    llm = _llm()
    async with demo("saintgeorge", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("¿Cuánto cuesta?")
        await rig.driver.user_says("Y los eventos también.")
        assert _commands(rig, "show_events") == [], "the calendar raced the fees"
        await rig.driver.user_says("¿Y entonces?")
        queued = _results(llm.captured_inputs[-1])["show_events"]
        assert queued.startswith("Queued, not sent yet: the page is still working on show_fees")
        await _page(rig, "fees_read", FEES)
        assert len(_commands(rig, "show_events")) == 1


# ─── The contact card ──────────────────────────────────────────────────────────


async def test_the_card_needs_their_details_and_never_takes_a_rut() -> None:
    llm = _llm()
    async with demo("saintgeorge", llm) as rig:
        await rig.driver.start_session(init={"path": ADMISION})
        await rig.driver.user_says("Quiero escribirle a admisión.")
        await rig.driver.user_says("Me llamo Ana, mi RUT es 12.345.678-5.")
        await rig.driver.user_says("¿Y entonces?")
        assert "show_contact_card" not in rig.actions()
        results = every_tool_result(llm.captured_inputs[-1])
        assert results[0].startswith("Not shown: ask for their name and the child's age")
        assert results[1].startswith("Not shown: a RUT is never written in the email.")


async def test_the_card_readies_the_email_in_spanish_and_sends_nothing() -> None:
    llm = _llm()
    async with demo("saintgeorge", llm) as rig:
        await rig.driver.start_session(init={"path": ADMISION})
        turn = await rig.driver.user_says("Me llamo Ana Pérez, es para mi hija de cinco.")
        check_turn(rig, turn)
        card = rig.command("show_contact_card")
        assert card["to"] == ADMISSIONS_EMAIL
        assert card["language"] == "es"
        assert card["subject"] == "Consulta de admisión: Kínder 2027"
        assert card["body"].startswith(
            "Hola,\n\nMi nombre es Ana Pérez. Les escribo por la admisión de mi hija, de cinco años, "
            "para Kínder 2027."
        )
        assert "¿Hay vacantes para Kínder 2027?" in card["body"]
        assert card["phone"] == "+56 2 2355 6181"
        # The page puts it up; the parent presses its button; he says it is
        # in their mail, never that it was sent.
        await _page(rig, "command_done", {"command": "show_contact_card", "detail": "on screen"})
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        await _page(rig, "contact_used", {"via": "email"})
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        context = _texts(llm.captured_inputs[-1])
        assert "The visitor pressed the email button" in context
        assert "never that it was sent" in context


async def test_the_card_is_in_english_when_the_call_is() -> None:
    async with demo("saintgeorge", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/", "lang": "en"})
        await rig.driver.user_says("Write to admissions for me, I'm Tom.")
        card = rig.command("show_contact_card")
        assert card["language"] == "en"
        assert card["subject"] == "Admissions enquiry: 3rd grade"
        assert card["body"].startswith(
            "Hello,\n\nMy name is Tom. I am writing about admission for my son, for 3rd grade."
        )
    assert sg.mailto(ADMISSIONS_EMAIL, "Consulta de admisión", "Hola,\nAna").startswith(
        "mailto:admisiones@saintgeorge.cl?subject=Consulta%20de%20admisi%C3%B3n&body=Hola%2C%0AAna"
    )


# ─── Links ─────────────────────────────────────────────────────────────────────


async def test_documents_tickets_and_portals_open_from_the_sites_own_links() -> None:
    llm = _llm()
    async with demo("saintgeorge", llm) as rig:
        await rig.driver.start_session(init={"path": SPORTS})
        await _page(
            rig,
            "page_changed",
            _page_changed(
                SPORTS,
                faqs=["CONOCE AL EQUIPO"],
                links=[{"label": "HORARIOS DEPORTE 2026", "url": SCHEDULE, "near": ""}],
            ),
        )
        await rig.driver.user_says("Ábreme el horario de deportes.")
        await rig.driver.user_says("Quiero entradas para el musical.")
        await rig.driver.user_says("Ábreme Schoolnet.")
        assert _commands(rig, "open_link") == [
            {"url": SCHEDULE, "label": "HORARIOS DEPORTE 2026"},
            {"url": TICKETS, "label": "Entradas The Lion King"},
            {
                "url": "https://schoolnet.colegium.com/webapp/es_CL/login",
                "label": "Schoolnet",
            },
        ]
        # Buying is no page move, and a login says they log in themselves.
        assert all(c.get("path") != MUSICAL for c in _cues(rig))
        await rig.driver.user_says("¿Y entonces?")
        assert "logs in there themselves" in _results(llm.captured_inputs[-1])["open_link"]


async def test_a_link_nowhere_on_the_site_or_off_its_hosts_is_refused() -> None:
    llm = _llm()
    async with demo("saintgeorge", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(
            rig,
            "page_changed",
            _page_changed(
                "/", links=[{"label": "Reglamento", "url": "https://evil.example/r.pdf"}]
            ),
        )
        await rig.driver.user_says("Ábreme ese documento.")
        await rig.driver.user_says("¿Y entonces?")
        assert "open_link" not in rig.actions()
        assert _results(llm.captured_inputs[-1])["open_link"].startswith(
            "Not opened: no document 'Reglamento'"
        )


# ─── Tabs and silent turns ─────────────────────────────────────────────────────


async def test_tabs_are_read_in_and_switching_is_checked() -> None:
    llm = _llm()
    async with demo("saintgeorge", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(
            rig,
            "tabs_changed",
            {
                "tabs": [
                    {"tab_id": "11", "url": "https://saintgeorge.cl/", "title": "Inicio"},
                    {
                        "tab_id": "12",
                        "url": "https://saintgeorge.cl/unidad/infant/",
                        "title": "Infant",
                    },
                ],
                "active": "12",
            },
        )
        await rig.driver.user_says("Vuelve a la otra pestaña.")
        assert "11: Inicio; 12: Infant (in front)" in _texts(llm.captured_inputs[-1])
        assert rig.command("focus_tab") == {"tab_id": "11"}
        assert _cues(rig) == []


async def test_a_silent_move_gets_his_written_line() -> None:
    async with demo("saintgeorge", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("Ábreme las entradas.")
        check_turn(rig, turn)
        assert turn.text.strip() == _LANDED["link"]["es"]


async def test_a_reply_that_only_promises_is_asked_once_more() -> None:
    async with demo("saintgeorge", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Y el casino?")
        check_turn(rig, turn)
        assert "El casino tiene menús mensuales" in turn.text


async def test_a_missed_cue_is_noted_quietly() -> None:
    llm = _llm()
    async with demo("saintgeorge", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(rig, "command_failed", {"command": "cue", "reason": "no heading X"})
        await rig.driver.user_says("¿Y entonces?")
        seen = _texts(llm.captured_inputs[-1])
        assert "A screen cue of yours did not land (no heading X)" in seen
        assert "Tell the visitor plainly" not in seen


def test_his_lines_for_a_move_exist_in_both_languages() -> None:
    for kind, lines in _LANDED.items():
        assert set(lines) == {"en", "es"}, kind
        assert all(line.strip() for line in lines.values()), kind
    assert set(TOGGLE_CONFIRM) == {"en", "es"}


def test_the_floor_is_held_as_the_clini_guide_learned() -> None:
    assert sg.ACK_HOLD_AFTER_S >= 5.5 and sg.ACK_SORRY_AFTER_S >= 15
    assert sg.HOLD_WITHOUT_NOD_S <= 3.0
