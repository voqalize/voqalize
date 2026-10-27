"""Javier, CLINI's voice guide, end to end over the wire — no network, no LLM key.

The real ``CliniBrain`` on a real ``brain_server`` socket, driven by the
conformance ``VoqalizeDriver``, with only the model scripted. The knowledge is a
small invented site in the crawl's own shape, put in place of the committed one,
and Clini's price and booking endpoints are answered by a fake: no test depends
on what the crawl found this week, or on what is free at a sede today.

What this demo earns that others do not:

**Spanish first.** The call opens in Spanish, the site's language, and moves
both legs to English for the toggle or for English heard.

**Prices and hours are Clini's own, read server side.** The price list answers,
or its saved copy does; the booking's days and hours are formatted for the voice.

**The booking is the visitor's.** He opens and fills the booking and the LASIK
form, checked against the booking list; he never carries a RUT, never presses
AGENDAR, and talks each step the page reports through.

Run: ``cd demos && uv run pytest tests/test_clini_e2e.py``
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import httpx
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

from voqalize_demos._loaded.clini import brain as clini  # noqa: E402
from voqalize_demos._loaded.clini import clini_api  # noqa: E402
from voqalize_demos._loaded.clini import knowledge as kb  # noqa: E402
from voqalize_demos._loaded.clini.brain import (  # noqa: E402
    _IDLE_MS,
    _TALK_THROUGH_MS,
    TOGGLE_CONFIRM,
    greeting,
    language_of,
)
from voqalize_demos._loaded.clini.knowledge import (  # noqa: E402
    AgendaService,
    Branch,
    Faq,
    Knowledge,
    Page,
    Prestacion,
    Price,
    Region,
    Section,
)

RM = "/imagenes/resonancias-fonasa-1"

#: The real GET, before the fixture below puts the offline one in its place.
REAL_GET_JSON = clini_api._get_json

# An invented site in the crawl's shape: the names, sedes and figures are ours.
SITE = Knowledge(
    l1="CLINI hace exámenes a precio Fonasa Nivel 1 (inventado para las pruebas).",
    topics={},
    pages={
        "/": Page("/", "CLINI: Inicio", sections=(Section("¿Qué necesitas hacer en CLINI?"),)),
        RM: Page(
            RM,
            "Agenda tu Resonancia Magnética | Fonasa",
            sections=(
                Section("Exámenes de Resonancia Magnética", "Rodilla, columna, cerebro."),
                Section("Precios de Resonancias", "RM rodilla desde cincuenta mil."),
            ),
            faqs=(Faq("¿Necesito orden médica?", "Sí, una orden médica."),),
        ),
        "/cirugia-lasik": Page(
            "/cirugia-lasik",
            "Cirugía LASIK | Precio desde $381.250 en CLINI",
            sections=(Section("¡Agenda tu evaluación gratuita!", "Evaluación gratis."),),
        ),
        "/ubicaciones": Page(
            "/ubicaciones",
            "En CLINI estamos cada vez mas cerca de ti",
            sections=(Section("Horarios y Ubicaciones CLINI", "Sedes."),),
        ),
        "/laboratorio": Page(
            "/laboratorio", "Laboratorio Fonasa Nivel 1 | CLINI", sections=(Section("Laboratorio"),)
        ),
        "/resultados": Page(
            "/resultados", "Resultados", sections=(Section("Resultados de Exámenes CLINI"),)
        ),
        "/ahorra-fonasa-1": Page(
            "/ahorra-fonasa-1", "Ahorra con Fonasa", sections=(Section("Ahorra con Fonasa"),)
        ),
    },
    branches=(
        Branch(
            "Sede Inventada Plaza Norte",
            address="Calle Falsa 123",
            comuna="Ñuñoa",
            region="Región Metropolitana",
            services=("Laboratorio", "Imagenología"),
            hours="Lunes a Viernes: 08:00 a 20:00hrs",
        ),
        Branch(
            "Sede Inventada Sur",
            address="Avenida Prueba 9",
            comuna="Temuco",
            region="Región de La Araucanía",
            services=("Toma de Muestras",),
            hours="Sábado: 08:00 a 13:00hrs",
        ),
    ),
    prices=(
        Price(1, "RM Rodilla Unilateral", servicio="RM", fonasa=80000, particular=160000),
        Price(2, "Hemograma Inventado", servicio="LAB", fonasa=1000, particular=2000),
    ),
    agenda={
        64: AgendaService(
            64,
            "Resonancia",
            prestaciones=(Prestacion(804, "RM Rodilla"), Prestacion(81, "RM Columna")),
            regions=(Region(5, "Región de Valparaíso"), Region(13, "Región Metropolitana", True)),
        ),
        62: AgendaService(
            62,
            "Laboratorio",
            prestaciones=(Prestacion(30, "Toma De Muestra"),),
            regions=(Region(13, "Región Metropolitana", True),),
        ),
        # The LASIK evaluation: the booking knows it, the site never links it.
        74: AgendaService(74, "Eval cir.lasik", prestaciones=(Prestacion(39, "Control Lasik"),)),
    },
)

HOME = {
    "site": "site",
    "url": "https://www.clini.cl/",
    "path": "/",
    "title": "CLINI: Inicio",
    "kind": "page",
    "headings": ["¿Qué necesitas hacer en CLINI?"],
    "faqs": [],
    "plans": [],
}

#: Monday the fourth of March 2030, and the rest of that week: far from today.
MON, TUE = "2030-03-04", "2030-03-05"


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every session reads the invented site, nothing reaches Clini's hosts, and
    he never nods unless a test asks him to: a nod is a unit of its own."""
    monkeypatch.setattr(kb, "KNOWLEDGE", SITE)
    monkeypatch.setattr(clini, "ACK_RATE", 0.0)
    monkeypatch.setattr(clini, "NO_HOURS_HOLD_S", 0.05)

    async def offline(url: str, params: dict[str, str], timeout: float) -> Any:
        raise clini_api.LookupFailed(f"no network in tests: {url}")

    monkeypatch.setattr(clini_api, "_get_json", offline)
    clini_api.clear_cache()
    yield
    clini_api.clear_cache()


def _results(items: list[Any]) -> dict[str, str]:
    return tool_results(items)


def _every(items: list[Any], name: str) -> list[str]:
    return tool_results_of(items, name)


def _texts(items: list[Any]) -> str:
    return input_texts(items)


def _llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            "Hola, ¿cómo estás?": reply("Muy bien. ¿En qué te ayudo hoy?"),
            # The model sometimes writes only a promise (Explora's dev call ed9846d5).
            "¿Y para la mamografía?": reply("Un momento."),
            # Spanish chosen, English spoken, Spanish answered, even from a sliver.
            "can you show me the MRI prices?": reply(
                chunks=[" C", "on Fonasa sale ochenta mil pesos. ¿Te busco una hora?"]
            ),
            "How much is a knee MRI?": reply(
                "{page: /imagenes/resonancias-fonasa-1} About eighty thousand pesos with Fonasa."
            ),
            "¿Me muestras la resonancia?": reply(
                "{page: /imagenes/resonancias-fonasa-1}{show: examenes de resonancia} "
                "Aquí están las resonancias. {show: el botón rosado} Se agenda en línea. "
                "{show: Rodilla, columna} Rodilla y columna. "
                "{page: /no-existe} {faq: necesito orden medica} Sí, con orden médica."
            ),
            "Quiero agendar una resonancia.": reply("Claro, te cuento cómo se agenda."),
            "¿Cuánto cuesta una resonancia de rodilla?": [
                call("quote_price", args={"query": "resonancia rodilla"}),
                reply("Con Fonasa sale ochenta mil pesos."),
            ],
            "¿Hay hora para resonancia de rodilla?": [
                call("check_availability", args={"servicio": 64, "prestacion": 804}),
                reply("Hay hora el lunes cuatro de marzo. ¿Te sirve?"),
            ],
            "¿Hay hora para resonancia?": [
                call("check_availability", args={"servicio": 64}),
                reply("¿De rodilla o de columna?"),
            ],
            "¿Hay hora para sangre el martes?": [
                call("check_availability", args={"servicio": 62, "day": TUE}),
                reply("El martes no queda; el miércoles sí."),
            ],
            "Agéndame la evaluación LASIK en la agenda.": reply_and_call(
                "Eso va por el formulario.", "open_agenda", args={"servicio": 74}
            ),
            "Resonancia de columna, en Arica.": reply_and_call(
                "Te abro la agenda.", "open_agenda", args={"servicio": 64, "prestacion": 999}
            ),
            "Agenda la rodilla el lunes a las siete y cuarenta en Tobalaba.": reply_and_call(
                "Listo, te abrí la agenda.",
                "open_agenda",
                args={
                    "servicio": 64,
                    "prestacion": 804,
                    "day": MON,
                    "centre": "CENTRO DE SALUD | METRO TOBALABA",
                    "time": "7:40",
                },
            ),
            "Mejor el martes.": reply_and_call(
                "Cambio al martes.", "agenda_pick", args={"day": TUE}
            ),
            "shows its open days": reply("Hay hora el lunes y el martes. ¿Cuál prefieres?"),
            "patient form is open": reply("Tu hora es el lunes. ¿Me dices tu nombre?"),
            "Soy Ana Pérez Soto, mi celular es +56 9 1234 5678.": 2
            * [
                reply_and_call(
                    "Anoto tu celular.",
                    "fill_agenda_patient",
                    # The model wrote a RUT it should not have: it never reaches the page.
                    args={
                        "name": "Ana",
                        "last_name": "Pérez",
                        "maternal_last_name": "Soto",
                        "phone": "+56 9 1234 5678",
                        "rut": "12.345.678-5",
                    },
                )
            ],
            "Mi correo es ana@correo.cl, y el RUT lo escribo yo.": reply_and_call(
                "Escribe tu RUT en el campo que marqué.",
                "fill_agenda_patient",
                args={"email": " Ana@Correo.cl ", "focus_rut": True},
            ),
            "Everything on the booking form is complete": reply("Listo. Presiona AGENDAR tú."),
            "shows the hour as booked": reply("Felicitaciones, quedó agendada."),
            "Quiero la evaluación LASIK, soy Juan, Cruz Blanca, en Los Leones.": reply_and_call(
                "Completo el formulario.",
                "fill_lasik_form",
                args={
                    "name": "Juan Rojas",
                    "prevision": "cruz blanca",
                    "location": "los leones",
                    "phone": "912345678",
                    "email": "juan@correo.cl",
                },
            ),
            "Mi previsión es Isapre Inventada, en Valdivia.": reply_and_call(
                "Veamos.",
                "fill_lasik_form",
                args={"prevision": "Isapre Inventada", "location": "Valdivia"},
            ),
            "LASIK evaluation form is complete": reply("Ya está. Presiona Agendar evaluación."),
            "Ábreme traumatología.": reply_and_call(
                "Te abro la agenda de traumatología.",
                "open_link",
                args={"kind": "reservo", "key": "Traumatología"},
            ),
            "Ábreme pediatría.": reply_and_call(
                "Veamos.", "open_link", args={"kind": "reservo", "key": "pediatría"}
            ),
            "¿Dónde veo mis resultados de imágenes?": reply_and_call(
                "Te abro el portal.", "open_link", args={"kind": "results_imaging"}
            ),
            "¿Tienen sede en Ñuñoa?": [
                call("find_branch", args={"query": "Ñuñoa"}),
                reply("{page: /ubicaciones}{show: Sede Inventada Plaza Norte} Sí, en Ñuñoa."),
            ],
            "Cámbiame el día a mañana.": 2
            * [reply_and_call("Veamos.", "agenda_pick", args={"day": TUE})],
            "Te abro la agenda de la rodilla.": 2
            * [
                reply_and_call(
                    "Te abro la agenda.", "open_agenda", args={"servicio": 64, "prestacion": 804}
                )
            ],
            # The page's answers to his moves, talked through in the quiet spell.
            "The page answered what you sent it": reply(
                # A site cue while the booking comes to the front: dropped.
                "{page: /imagenes/resonancias-fonasa-1} Esto es lo que hizo la agenda."
            ),
            "Las diez en Quinta Vergara.": reply_and_call(
                "Te selecciono las diez.",
                "agenda_pick",
                args={"day": MON, "time": "10:00", "centre": "CENTRO DE SALUD | QUINTA"},
            ),
            "No tengo RUT, soy extranjero.": reply_and_call(
                "Elige Pasaporte.",
                "fill_agenda_patient",
                args={"document": "passport", "focus_rut": True},
            ),
            "my phone is eight one four seven five one four one seven nine": reply_and_call(
                # Reshaped to look Chilean: refused, never sent.
                "Let me add it.",
                "fill_agenda_patient",
                args={"phone": "914751417"},
            ),
            "it is eight one four seven five one four one seven nine, really": reply_and_call(
                "Adding it.", "fill_agenda_patient", args={"phone": "8147514179"}
            ),
            "Can I speak in English?": reply_and_call(
                "Sure, let's continue in English.",
                "fill_agenda_patient",
                args={"focus_rut": True},
            ),
            "¿Cuánto sale con Fonasa la resonancia?": reply(
                "{show: Precios de Resonancias} Con Fonasa la rodilla sale ochenta mil pesos."
            ),
            "¿Qué pestañas tengo?": reply("Tienes el sitio y la agenda."),
            "Sigamos.": reply("Claro, sigamos."),
        }
    )


async def _page(rig: object, event: str, payload: dict[str, object]) -> None:
    await rig.driver.send_ui_event(event, payload)  # type: ignore[attr-defined]
    # `on_rtvi` takes no floor and there is nothing to await: give it a moment.
    await asyncio.sleep(0.1)


def _idle_windows(rig: object) -> list[int | None]:
    return [c.idle.timeout_ms for c in _configs(rig) if c.idle is not None]  # type: ignore[arg-type]


def _commands(rig: object, name: str) -> list[dict[str, Any]]:
    return [
        c["payload"]
        for c in rig.driver.ui_commands  # type: ignore[attr-defined]
        if c.get("command") == name
    ]


def _language_changes(rig: object) -> list[object]:
    return _commands(rig, "language_changed")


# ─── Voice and language ────────────────────────────────────────────────────────


async def test_the_greeting_is_spanish_and_the_voice_reaches_the_wire() -> None:
    """A written opener, and javier in Spanish on both legs before it."""
    async with demo("clini", _llm()) as rig:
        opener = await rig.driver.start_session(
            init={"surface": "clini-ext", "site": "site", "path": "/"}
        )
        check_greeting(rig, opener)
        assert opener is not None
        assert opener.text == clini.for_the_voice(greeting("/", "site", "es"))
        assert opener.text.startswith("Hola, soy Javier, tu guía de voz de Clini.")
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _idle_windows(rig) == [_IDLE_MS]


async def test_the_toggle_moves_both_legs_to_english_and_confirms() -> None:
    async with demo("clini", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await _page(rig, "language_requested", {"language": "en"})
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert rig.command("language_changed") == {"language": "en"}
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert turn.text == TOGGLE_CONFIRM["en"]


async def test_a_call_started_in_english_greets_in_english() -> None:
    async with demo("clini", _llm()) as rig:
        opener = await rig.driver.start_session(init={"site": "site", "path": "/", "lang": "en"})
        assert opener is not None and opener.text == greeting("/", "site", "en")
        assert opener.text.startswith("Hi, I'm Javier, Clini's voice guide.")
        check_voice_pair(rig, voice="omnivoice/javier", language="en")


async def test_a_language_chosen_on_the_site_holds_on_the_booking() -> None:
    """The extension keeps the choice for every Clini host, and the booking's
    tab sends it at connect: dev call 03a45037 redialled there in Spanish."""
    async with demo("clini", _llm()) as rig:
        opener = await rig.driver.start_session(init={"site": "agenda", "path": "/", "lang": "en"})
        assert opener is not None and opener.text == greeting("/", "agenda", "en")
        check_voice_pair(rig, voice="omnivoice/javier", language="en")


async def test_a_chosen_language_holds_when_the_visitor_speaks_the_other() -> None:
    async with demo("clini", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/", "lang": "es"})
        turn = await rig.driver.user_says("I'm asking, can you show me the MRI prices?")
        assert "Con Fonasa sale" in turn.text
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _language_changes(rig) == []


async def test_english_heard_moves_the_call_and_spanish_brings_it_back() -> None:
    async with demo("clini", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        turn = await rig.driver.user_says("How much is a knee MRI?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        await rig.driver.user_says("Hola, ¿cómo estás?")
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _language_changes(rig) == [{"language": "en"}, {"language": "es"}]


@pytest.mark.parametrize(
    ("text", "sure", "lang"),
    [
        ("¿Cuánto cuesta una resonancia?", True, "es"),
        ("Necesito una hora para el laboratorio", True, "es"),
        ("¿Atienden Fonasa en la sede de Maipú?", True, "es"),
        ("Hola", True, None),
        ("Fonasa", True, None),
        ("How much is an MRI of the knee?", True, "en"),
        ("Can you book it for me?", True, "en"),
        ("Claro.", False, "es"),
        # A cue is the site's Spanish inside an English reply.
        ("{show: Precios de Resonancias} It's about eighty thousand pesos.", False, "en"),
    ],
)
def test_the_language_a_line_is_in(text: str, sure: bool, lang: str | None) -> None:
    assert language_of(text, sure=sure) == lang


@pytest.mark.parametrize(
    ("path", "site", "words"),
    [
        ("/cirugia-lasik", "site", "evaluación gratuita"),
        ("/cirugia-lasik/temuco", "site", "evaluación gratuita"),
        ("/imagenes/resonancias-magneticas/rodilla", "site", "resonancia"),
        ("/imagenes/ecografia-fonasa-nivel-1", "site", "examen de imágenes"),
        ("/cardiologia/ecocardiograma-fonasa-1", "site", "cardiológico"),
        ("/agendamiento-cardiologia", "site", "cardiológico"),
        ("/laboratorio/maipu", "site", "laboratorio"),
        ("/consultas-medicas", "site", "especialidades"),
        ("/ubicaciones", "site", "sede"),
        ("/convenios-salud/caja-los-andes", "site", "convenios"),
        ("/ahorra-fonasa-1", "site", "Fonasa"),
        ("/resultados", "site", "resultados"),
        ("/blog", "site", "artículo"),
        ("/agendamiento", "site", "agendar"),
        ("/", "agenda", "elegir tu hora"),
        ("/somos-clini", "site", "cotizo un examen"),
    ],
)
def test_the_opener_follows_the_page(path: str, site: str, words: str) -> None:
    line = greeting(path, site, "es")
    assert line.startswith("Hola, soy Javier")
    assert words in line, line
    assert greeting(path, site, "en").startswith("Hi, I'm Javier")


async def test_the_site_name_in_capitals_is_handed_to_the_voice_as_a_word() -> None:
    assert clini.for_the_voice("Bienvenido a CLINI.") == "Bienvenido a Clini."
    assert clini.names_for_the_voice("Welcome to CLINI, CLINICA.") == "Welcome to Clini, CLINICA."


# ─── Cues ──────────────────────────────────────────────────────────────────────

NONE = {"path": None, "heading": None, "text": None, "faq": None, "lead": None}


async def test_cues_leave_the_speech_and_are_checked_against_the_site() -> None:
    async with demo("clini", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        turn = await rig.driver.user_says("¿Me muestras la resonancia?")
        check_turn(rig, turn)
        assert "{" not in turn.text and "}" not in turn.text
        # The page they asked for, opened ahead of the answer and not again
        # for his own cue; with its trailing slash; the heading in the site's
        # spelling, accents and case folded; words that are no heading rung as
        # words when the page has them, and dropped when it does not; the
        # invented page dropped; and the FAQ on the page the reply is on.
        path = RM + "/"
        assert _commands(rig, "cue") == [
            {**NONE, "at": "", "word": 0, "path": path, "lead": "now"},
            {
                **NONE,
                "at": "aqui estan las",
                "word": 0,
                "path": path,
                "heading": "Exámenes de Resonancia Magnética",
            },
            {
                **NONE,
                "at": "rodilla y columna",
                "word": 8,
                "path": path,
                "text": "Rodilla, columna",
            },
            {
                **NONE,
                "at": "si con orden",
                "word": 11,
                "path": path,
                "faq": "¿Necesito orden médica?",
            },
        ]


async def test_what_they_asked_about_is_shown_when_his_reply_forgets_to() -> None:
    async with demo("clini", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("¿Cuánto cuesta una resonancia de rodilla?")
        # Opened ahead of the answer (no nod: at once), and his reply, which
        # brings no cue of its own, does not open it a second time.
        assert _commands(rig, "cue") == [
            {**NONE, "at": "", "word": 0, "path": RM + "/", "lead": "now"}
        ]


async def test_the_page_a_reply_opens_first_is_opened_before_its_words() -> None:
    """Prod, 2026-10-22: every page load drops the call for 3 to 6 s while it
    rejoins. Opened at the answer's first word, that silence was the answer's."""
    async with demo("clini", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        # A booking ask is not led: its reply opens the booking's own tab. The
        # page his reply opens first still goes before its words.
        await rig.driver.user_says("Quiero agendar una resonancia.")
        assert _commands(rig, "cue") == [
            {**NONE, "at": "claro te cuento", "word": 0, "path": RM + "/", "lead": "now"}
        ]


async def test_a_page_asked_for_is_opened_while_his_nod_plays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clini, "ACK_RATE", 1.0)
    async with demo("clini", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        turn = await rig.driver.user_says("¿Cuánto cuesta una resonancia de rodilla?")
        nods = [n for lines in clini._ACK_LINES["es"].values() for n in lines]
        assert any(turn.text.startswith(n) for n in nods), turn.text
        assert _commands(rig, "cue") == [
            {**NONE, "at": "", "word": 0, "path": RM + "/", "lead": "nod"}
        ]


def test_the_page_for_what_they_asked_about() -> None:
    asked = clini.asked_page
    assert asked("¿Cuánto cuesta una resonancia de rodilla?") == RM
    assert asked("Quiero agendar una resonancia") == RM
    assert asked("I need an MRI") == RM
    assert asked("¿Necesito ayuno para el hemograma?") == "/indicaciones"
    assert asked("¿Dónde quedan las sedes?") == "/ubicaciones"
    assert asked("¿Atienden Fonasa?") == "/ahorra-fonasa-1"
    assert asked("Quiero operarme la vista con LASIK") == "/cirugia-lasik"
    assert asked("holter de presión") == "/cardiologia/realiza-tu-holter-de-presion-mapa-en-clini"
    assert asked("un holter") == "/cardiologia/realiza-tu-holter-de-ritmo-en-clini"
    assert asked("¿Dónde veo mis resultados?") == "/resultados"
    assert asked("Vuelve a la pestaña de la agenda") is None
    assert asked("Mm-hmm") is None
    for ask in (
        "¿Puedes hablar en inglés?",
        "Hablemos en español.",
        "Can we continue in English?",
        "Claro, seguimos en español.",
    ):
        assert asked(ask) is None, ask


# ─── Prices ────────────────────────────────────────────────────────────────────

_KNEE = {
    "id": 77,
    "nombre": "RM Rodilla Unilateral",
    "codigo": "0405010",
    "categoria": "Resonancia",
    "servicio": "RM",
    "requiereContraste": False,
    "precioFonasa": 88280,
    "precioParticular": 176560,
    "preparacion": "Sin preparación especial",
}


async def test_a_price_comes_from_the_price_list_then_from_its_saved_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[dict[str, str]] = []

    async def cotizador(url: str, params: dict[str, str], timeout: float) -> Any:
        asked.append(params)
        assert url == clini_api.COTIZADOR
        return [_KNEE, {"nombre": ""}, "junk"]

    monkeypatch.setattr(clini_api, "_get_json", cotizador)
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        turn = await rig.driver.user_says("¿Cuánto cuesta una resonancia de rodilla?")
        check_turn(rig, turn)
        quoted = _results(llm.captured_inputs[-1])["quote_price"]
        assert asked == [{"handler": "Buscar", "q": "resonancia rodilla"}]
        assert "live" in quoted
        assert (
            "- RM Rodilla Unilateral — Fonasa $88.280 / particular $176.560; RM; "
            "preparación: Sin preparación especial"
        ) in quoted

    async def down(url: str, params: dict[str, str], timeout: float) -> Any:
        raise clini_api.LookupFailed("timed out")

    monkeypatch.setattr(clini_api, "_get_json", down)
    clini_api.clear_cache()
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("¿Cuánto cuesta una resonancia de rodilla?")
        quoted = _results(llm.captured_inputs[-1])["quote_price"]
        assert "saved copy" in quoted and "may have changed" in quoted
        assert "RM Rodilla Unilateral — Fonasa $80.000 / particular $160.000" in quoted
        assert "Hemograma" not in quoted


def test_prices_and_days_are_written_as_the_site_and_a_chilean_say_them() -> None:
    assert clini_api.pesos(88280) == "$88.280"
    assert clini_api.pesos(1580) == "$1.580"
    assert clini_api.pesos(None) == "sin precio publicado"
    assert clini_api.day_es(MON, now=clini_api.date(2030, 1, 1)) == "lunes 4 de marzo"
    assert clini_api.day_es(TUE, now=clini_api.date(2030, 3, 4)) == "mañana, martes 5 de marzo"
    assert clini_api.day_es(MON, now=clini_api.date(2030, 3, 4)) == "hoy, lunes 4 de marzo"


# ─── Open hours ────────────────────────────────────────────────────────────────


def _hours(times: list[str], centre: str = "CENTRO DE SALUD | METRO TOBALABA") -> dict[str, Any]:
    return {
        "exito": True,
        "dias": [
            {
                "fecha": MON,
                "tieneDisponibilidad": True,
                "centros": [
                    {
                        "codigo": "29",
                        "nombre": centre,
                        "direccion": "LUIS THAYER OJEDA 073",
                        "horarios": [{"agendaId": "1", "hora": t} for t in times],
                    }
                ],
            }
        ],
    }


def _booking(calls: list[dict[str, str]]) -> Any:
    async def answer(url: str, params: dict[str, str], timeout: float) -> Any:
        assert url == clini_api.AGENDA
        calls.append(params)
        if params["handler"] == "Disponibilidad":
            return {
                "exito": True,
                "dias": [
                    {"fecha": MON, "tieneDisponibilidad": True, "centros": []},
                    {"fecha": TUE, "tieneDisponibilidad": False, "centros": []},
                    {"fecha": "2030-03-06", "tieneDisponibilidad": True, "centros": []},
                ],
            }
        if params["handler"] == "HorariosDia":
            assert params["fase"] == "prioritarios"
            return _hours(["07:40", "08:00"] if params["periodo"] == "AM" else ["15:20"])
        raise AssertionError(f"a call the brain must never make: {params}")

    return answer


async def test_open_hours_are_read_from_the_booking_and_said_by_sede(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []
    monkeypatch.setattr(clini_api, "_get_json", _booking(calls))
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        turn = await rig.driver.user_says("¿Hay hora para resonancia de rodilla?")
        check_turn(rig, turn)
        found = _results(llm.captured_inputs[-1])["check_availability"]
        assert found.splitlines()[0] == "Resonancia — RM Rodilla, Región Metropolitana."
        assert "First days with free hours: 2030-03-04 (lunes 4 de marzo); 2030-03-06" in found
        assert (
            "- CENTRO DE SALUD | METRO TOBALABA (LUIS THAYER OJEDA 073): 07:40, 08:00, 15:20"
        ) in found
        # The open days, and the first one's morning and afternoon. With nothing
        # cached, today's hours are asked beside the days, in case today is it.
        assert [c for c in calls if c["handler"] == "Disponibilidad"] == [
            {
                "handler": "Disponibilidad",
                "servicio": "64",
                "prestacion": "804",
                "region": "13",
                "buscarPrimera": "true",
            }
        ]
        hours = {(c["fecha"], c["periodo"]) for c in calls if c["handler"] == "HorariosDia"}
        assert {(MON, "AM"), (MON, "PM")} <= hours
        # And the next open day's, asked for next: in the background.
        assert {day for day, _ in hours} <= {MON, "2030-03-06", clini_api.today().isoformat()}
        # Every call is a read: never the booking itself, never a patient lookup.
        assert not {c["handler"] for c in calls} & {"AgendarCitaMedica", "PacientePorDocumento"}


async def test_a_servicio_with_several_prestaciones_asks_which_first() -> None:
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("¿Hay hora para resonancia?")
        found = _results(llm.captured_inputs[-1])["check_availability"]
        assert found == "Ask which one first: Resonancia has 804 RM Rodilla; 81 RM Columna."


async def test_a_day_with_no_hours_gives_the_next_one_and_the_lab_takes_a_sector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []
    monkeypatch.setattr(clini_api, "_get_json", _booking(calls))
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("¿Hay hora para sangre el martes?")
        found = _results(llm.captured_inputs[-1])["check_availability"]
        # The days from the one asked for: the fake lists an earlier one too.
        assert "2030-03-05 (martes 5 de marzo) has no free hours; the next is 2030-03-06" in found
        assert "2030-03-04" not in found
        # One prestación, taken for them; the RM laboratorio search is by sector.
        (days,) = [c for c in calls if c["handler"] == "Disponibilidad"]
        assert days["prestacion"] == "30" and days["sector"] == "TODOS"
        assert days["desde"] == TUE


async def test_a_booking_that_does_not_answer_is_said_plainly() -> None:
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("¿Hay hora para resonancia de rodilla?")
        found = _results(llm.captured_inputs[-1])["check_availability"]
        assert found.startswith("The booking did not answer just now.")


# ─── The booking ───────────────────────────────────────────────────────────────


def _agenda_state(**over: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "step": "results",
        "servicio": 64,
        "servicio_name": "Resonancia",
        "prestacion": 804,
        "prestacion_name": "RM Rodilla",
        "region": 13,
        "days": [MON, TUE],
        "centres": ["CENTRO DE SALUD | METRO TOBALABA"],
        "times": [],
        "selected": "",
        "indications": "",
        "invalid": [],
        "ready": False,
    }
    return state | over


async def test_open_agenda_checks_the_codes_against_the_booking_list() -> None:
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("Agéndame la evaluación LASIK en la agenda.")
        await rig.driver.user_says("Resonancia de columna, en Arica.")
        await rig.driver.user_says("Sigamos.")
        assert "open_agenda" not in rig.actions()
        # Neither the unlinked LASIK evaluation nor an invented prestación.
        lasik, invented = _every(llm.captured_inputs[-1], "open_agenda")
        assert lasik == (
            "Not done: 74 is not a servicio of the booking. The booking list has: "
            "62 Laboratorio; 64 Resonancia."
        )
        assert invented == (
            "Not done: Resonancia has no prestación 999. It has: 804 RM Rodilla; 81 RM Columna."
        )


async def test_the_booking_opens_steps_through_and_is_talked_through() -> None:
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        turn = await rig.driver.user_says(
            "Agenda la rodilla el lunes a las siete y cuarenta en Tobalaba."
        )
        check_turn(rig, turn)
        assert rig.command("open_agenda") == {
            "servicio": 64,
            "prestacion": 804,
            "region": None,
            "day": MON,
            "centre": "CENTRO DE SALUD | METRO TOBALABA",
            "time": "07:40",
        }
        # The booking reports its open days on its way to the Monday they
        # chose: noted, and not asked about again (prod, 2026-10-22, "¿Qué día
        # te acomoda?" with the day already given). Nor is the quiet nudged.
        await _page(rig, "agenda_state", _agenda_state())
        assert _idle_windows(rig)[-1] == _IDLE_MS
        before = len(llm.requests)
        turn = await rig.driver.user_idle(level=1, idle_ms=_IDLE_MS)
        assert turn.text == "" and len(llm.requests) == before
        # Its answer is talked through, in the short quiet spell, with the
        # note saying the days as a Chilean says them.
        await _page(rig, "command_done", {"command": "open_agenda", "detail": "results shown"})
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        seen = _texts(llm.captured_inputs[-1])
        assert (
            "[The booking shows its calendar and hours, for Resonancia — RM Rodilla, region 13. "
            "Open days: 2030-03-04 (lunes 4 de marzo); 2030-03-05 (martes 5 de marzo)."
        ) in seen
        assert "The page answered what you sent it: open_agenda done: results shown" in seen
        assert "shows its open days and they have not spoken" not in seen
        assert _idle_windows(rig)[-1] == _IDLE_MS

        # A later pick on the tab already open, once the open has answered.
        await rig.driver.user_says("Mejor el martes.")
        assert _commands(rig, "agenda_pick")[-1] == {
            "day": TUE,
            "time": None,
            "centre": None,
            "period": None,
        }

        # The patient form opens: talked through, with the RUT left to them.
        await _page(
            rig,
            "agenda_state",
            _agenda_state(
                step="booking",
                selected="MARTES, 5 DE MARZO DE 2030 A LAS 07:40 (AM) · TOBALABA",
                indications="Llegar 15 minutos antes.",
                invalid=["rut", "name", "phone", "consent"],
            ),
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "¿Me dices tu nombre?" in turn.text
        seen = _texts(llm.captured_inputs[-1])
        assert "Indications: Llegar 15 minutos antes." in seen
        assert "Still missing or invalid: rut, name, phone, consent." in seen


async def test_the_patient_form_is_filled_without_a_rut_and_never_booked() -> None:
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "agenda", "path": "/"})
        # Before an hour is picked there is no form to fill.
        await _page(rig, "agenda_state", _agenda_state())
        await rig.driver.user_says("Soy Ana Pérez Soto, mi celular es +56 9 1234 5678.")
        assert "fill_agenda_patient" not in rig.actions()

        await _page(rig, "agenda_state", _agenda_state(step="booking", invalid=["rut"]))
        await rig.driver.user_says("Soy Ana Pérez Soto, mi celular es +56 9 1234 5678.")
        (early,) = _every(llm.captured_inputs[-1], "fill_agenda_patient")
        assert "the patient form opens once they pick an hour" in early
        filled = rig.command("fill_agenda_patient")
        assert "rut" not in filled
        assert filled == {
            "name": "Ana",
            "last_name": "Pérez",
            "maternal_last_name": "Soto",
            "birth_date": None,
            "sex": None,
            "phone": "912345678",
            "email": None,
            "document": None,
            "focus_rut": False,
        }
        # What is filled stays; the email is tidied; the RUT field rung.
        await _page(rig, "command_done", {"command": "fill_agenda_patient", "detail": "filled"})
        await rig.driver.user_says("Mi correo es ana@correo.cl, y el RUT lo escribo yo.")
        # Sent, not done: the page has not answered yet.
        sent = _every(llm.captured_inputs[-1], "fill_agenda_patient")[-1]
        assert "Sent to the page; it has not happened yet." in sent
        assert "The celular sent: 9 1 2 3 4 5 6 7 8." in sent
        last = _commands(rig, "fill_agenda_patient")[-1]
        assert last["name"] == "Ana" and last["phone"] == "912345678"
        assert last["email"] == "ana@correo.cl" and last["focus_rut"] is True
        await rig.driver.user_says("Sigamos.")
        said = _every(llm.captured_inputs[-1], "fill_agenda_patient")[-1]
        assert "The email sent: ana@correo.cl." in said
        assert "they type it themselves" in said
        wire = str(rig.driver.ui_commands)  # type: ignore[attr-defined]
        assert "12.345.678-5" not in wire and "rut" not in {
            k for p in _commands(rig, "fill_agenda_patient") for k in p
        }
        assert not {"agendar", "submit", "book"} & set(rig.actions())

        # Complete: AGENDAR is theirs.
        await _page(rig, "agenda_state", _agenda_state(step="booking", invalid=[], ready=True))
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "Presiona AGENDAR tú." in turn.text
        # Booked, by their press: congratulated, even unasked.
        await _page(rig, "agenda_state", _agenda_state(step="done", selected="MARTES 5"))
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "Felicitaciones" in turn.text


async def test_a_step_the_visitor_took_is_noted_and_not_talked_over() -> None:
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "agenda", "path": "/"})
        await _page(rig, "agenda_state", _agenda_state())
        assert _idle_windows(rig) == [_IDLE_MS]
        await rig.driver.user_says("Sigamos.")
        assert "Open days: 2030-03-04 (lunes 4 de marzo)" in _texts(llm.captured_inputs[-1])


async def test_agenda_tabs_are_read_in_and_a_pick_needs_one() -> None:
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("Cámbiame el día a mañana.")
        assert "agenda_pick" not in rig.actions()
        await _page(
            rig,
            "tabs_changed",
            {
                "tabs": [
                    {"tab_id": "1", "url": "https://www.clini.cl/", "title": "CLINI"},
                    {
                        "tab_id": "2",
                        "url": "https://agenda-web.clini.cl/?servicio=64",
                        "title": "Agenda",
                    },
                ],
                "active": "2",
            },
        )
        await _page(rig, "page_changed", HOME)
        await rig.driver.user_says("¿Qué pestañas tengo?")
        seen = _texts(llm.captured_inputs[-1])
        assert "1: CLINI; 2: Agenda (the booking) (in front)" in seen
        (refused,) = _every(llm.captured_inputs[-1], "agenda_pick")
        assert refused == "Not done: no booking tab is open. Use open_agenda first."
        await rig.driver.user_says("Cámbiame el día a mañana.")
        assert _commands(rig, "agenda_pick") == [
            {"day": TUE, "time": None, "centre": None, "period": None}
        ]


async def test_a_failed_booking_step_is_talked_through_instead_of_the_step() -> None:
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("Agenda la rodilla el lunes a las siete y cuarenta en Tobalaba.")
        await _page(rig, "agenda_state", _agenda_state())
        await _page(rig, "command_failed", {"command": "open_agenda", "reason": "no 07:40"})
        # The open days are not talked through; the failure is.
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        seen = _texts(llm.captured_inputs[-1])
        assert "[Not done on the page (open_agenda): no 07:40." in seen
        assert "The page answered what you sent it: open_agenda not done: no 07:40." in seen
        assert "shows its open days and they have not spoken" not in seen


async def test_a_booking_move_returns_at_once_and_claims_nothing() -> None:
    """The tool sends and returns: it never waits on the page, and its result
    says nothing has happened yet (dev call 5ff8b052, "I selected ten in the
    morning" while the page refused the pick)."""
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        before = len(llm.requests)
        turn = await rig.driver.user_says("Te abro la agenda de la rodilla.")
        check_turn(rig, turn)
        assert rig.command("open_agenda")["servicio"] == 64
        # One request: the turn did not ask the model again with the result.
        assert len(llm.requests) == before + 1
        await rig.driver.user_says("Sigamos.")
        opened = _every(llm.captured_inputs[-1], "open_agenda")[-1]
        assert opened.startswith("Opening the booking for Resonancia — RM Rodilla.")
        assert "Sent to the page; it has not happened yet. Say only what you are doing" in opened
        assert "never that it is done" in opened


async def test_the_pages_answers_are_noted_and_talked_through_once() -> None:
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "agenda", "path": "/"})
        await _page(rig, "agenda_state", _agenda_state(step="booking", invalid=["rut"]))
        await rig.driver.user_says("No tengo RUT, soy extranjero.")
        assert _idle_windows(rig)[-1] == _IDLE_MS
        # Two answers close together: one talk-through says both.
        reason = "the form did not answer"
        await _page(rig, "command_failed", {"command": "fill_agenda_patient", "reason": reason})
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        await _page(rig, "command_done", {"command": "fill_agenda_patient", "detail": "late"})
        before = len(llm.requests)
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert len(llm.requests) == before + 1
        seen = _texts(llm.captured_inputs[-1])
        assert f"[Not done on the page (fill_agenda_patient): {reason}." in seen
        assert (
            f"The page answered what you sent it: fill_agenda_patient not done: {reason}."
        ) in seen
        # A second answer to a move already answered is a note, not a second ask.
        assert "fill_agenda_patient done: late" not in seen
        # Said, and not again in the next quiet spell.
        assert _idle_windows(rig)[-1] == _IDLE_MS
        await rig.driver.user_idle(level=1, idle_ms=_IDLE_MS)
        assert (
            "The page answered what you sent it" not in _texts(llm.captured_inputs[-1])[len(seen) :]
        )


async def test_the_pages_answer_is_not_talked_through_when_the_visitor_speaks_first() -> None:
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "agenda", "path": "/"})
        await _page(rig, "agenda_state", _agenda_state(days=[MON], day=MON, times=["10:00"]))
        await rig.driver.user_says("Las diez en Quinta Vergara.")
        await _page(
            rig, "command_done", {"command": "agenda_pick", "detail": "selected 10:00 at QUINTA"}
        )
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        await rig.driver.user_says("Sigamos.")
        seen = _texts(llm.captured_inputs[-1])
        # In the context for his answer to them; no talk-through of its own.
        assert "[The page confirms agenda_pick: selected 10:00 at QUINTA.]" in seen
        assert "The page answered what you sent it" not in seen
        assert _idle_windows(rig)[-1] == _IDLE_MS


async def test_no_free_hours_only_when_the_booking_shows_neither_days_nor_hours() -> None:
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("Te abro la agenda de la rodilla.")
        # Translated: the calendar's days are unreadable, the hours are not.
        await _page(rig, "agenda_state", _agenda_state(days=[], times=["14:40"], day=""))
        await asyncio.sleep(0.1)
        await rig.driver.user_says("Sigamos.")
        seen = _texts(llm.captured_inputs[-1])
        assert "The calendar's open days could not be read; the hours below are on screen" in seen
        assert "no open days and no hours" not in seen
        # Empty for a moment, then the hours: still nothing to say about none.
        await _page(rig, "agenda_state", _agenda_state(days=[], times=[]))
        await _page(rig, "agenda_state", _agenda_state(times=["08:50"], day=MON))
        await asyncio.sleep(0.1)
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS  # the hours, to talk through
        await rig.driver.user_says("Sigamos.")
        assert "no open days and no hours" not in _texts(llm.captured_inputs[-1])
        # Empty, and it stays empty: now he says so.
        await rig.driver.user_says("Te abro la agenda de la rodilla.")
        await _page(rig, "agenda_state", _agenda_state(days=[], times=[]))
        await asyncio.sleep(0.15)
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "The booking shows no open days and no hours for this search." in _texts(
            llm.captured_inputs[-1]
        )


async def test_a_visitor_without_a_rut_is_switched_to_the_passport() -> None:
    prompt = clini._prompt(SITE, clini_api.date(2030, 3, 4))
    assert "chooses Pasaporte" in prompt and "never send a visitor to WhatsApp" in prompt
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "agenda", "path": "/"})
        await _page(rig, "agenda_state", _agenda_state(step="booking", invalid=["rut"]))
        await rig.driver.user_says("No tengo RUT, soy extranjero.")
        sent = rig.command("fill_agenda_patient")
        assert sent["document"] == "passport" and sent["focus_rut"] is True
        await _page(
            rig,
            "agenda_state",
            _agenda_state(step="booking", invalid=["rut"], document="passport"),
        )
        await rig.driver.user_says("Sigamos.")
        said = _every(llm.captured_inputs[-1], "fill_agenda_patient")[-1]
        assert "The passport number field is ringed: they type it themselves." in said
        assert "The form is set to the passport (Pasaporte)." in _texts(llm.captured_inputs[-1])


async def test_a_phone_is_never_reshaped_to_fit_a_chilean_mobile() -> None:
    """Dev call 03a45037: 8147514179 said, 914751417 sent."""
    assert clini.said_digits("eight one four seven five 1 4 one seven nine") == "8147514179"
    assert clini.said_digits("nueve uno dos, 345 6789") == "9123456789"
    pairs = "nueve, ochenta y dos, cuarenta y seis, treinta y dos, cero dos"
    assert clini.said_digits(pairs) == "982463202"
    assert clini.said_digits("noventa, veintidós y diez") == "902210"
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "agenda", "path": "/", "lang": "en"})
        await _page(rig, "agenda_state", _agenda_state(step="booking", invalid=["phone"]))
        await rig.driver.user_says("my phone is eight one four seven five one four one seven nine")
        await rig.driver.user_says(
            "it is eight one four seven five one four one seven nine, really"
        )
        reshaped = _every(llm.captured_inputs[-1], "fill_agenda_patient")[-1]
        assert (
            "celular: 9 1 4 7 5 1 4 1 7 is not what the visitor said (8 1 4 7 5 1 4 1 7 9)"
        ) in reshaped
        await rig.driver.user_says("Sigamos.")
        said = _every(llm.captured_inputs[-1], "fill_agenda_patient")[-1]
        assert "is not a Chilean celular, nine digits starting with 9" in said
        assert "never change or invent digits" in said
        assert all(c["phone"] is None for c in _commands(rig, "fill_agenda_patient"))


async def test_a_question_about_the_call_touches_no_booking() -> None:
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "agenda", "path": "/"})
        await _page(rig, "agenda_state", _agenda_state(step="booking", invalid=["rut"]))
        await rig.driver.user_says("Can I speak in English?")
        assert "fill_agenda_patient" not in rig.actions()


async def test_no_site_cue_pulls_the_visitor_off_the_booking_it_opened() -> None:
    """Dev call 5ff8b052: a page cue right after open_agenda brought the site
    tab back over the booking, before the booking's tab had even reported."""
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("Te abro la agenda de la rodilla.")
        # The page answers before the booking's tab has reported itself: his
        # talk-through cues a page of the site, and it is dropped.
        await _page(rig, "command_done", {"command": "open_agenda", "detail": "results shown"})
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "Esto es lo que hizo la agenda." in turn.text
        assert not [c for c in _commands(rig, "cue") if c["path"]], _commands(rig, "cue")
        # While the booking is in front, an exam question moves no page either.
        await _page(rig, "page_changed", {**HOME, "site": "agenda", "path": "/", "kind": "agenda"})
        await rig.driver.user_says("How much is a knee MRI?")
        assert not [c for c in _commands(rig, "cue") if c["path"]], _commands(rig, "cue")


async def test_a_section_shown_on_the_page_keeps_the_backstop_from_moving_it() -> None:
    """Dev call 03a45037: "with Fonasa", said about a section of the page in
    front, opened the Fonasa page over it."""
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": RM})
        await rig.driver.user_says("¿Cuánto sale con Fonasa la resonancia?")
        cues = _commands(rig, "cue")
        assert [c["heading"] for c in cues] == ["Precios de Resonancias"], cues
        assert not [c for c in cues if c["path"]], cues


async def test_morning_and_afternoon_hours_are_asked_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []
    booking = _booking(calls)
    in_flight = 0
    most = 0

    async def answer(url: str, params: dict[str, str], timeout: float) -> Any:
        nonlocal in_flight, most
        in_flight += 1
        most = max(most, in_flight)
        await asyncio.sleep(0)
        try:
            return await booking(url, params, timeout)
        finally:
            in_flight -= 1

    monkeypatch.setattr(clini_api, "_get_json", answer)
    found = await clini_api.availability(64, 804, 13, MON)
    # The day asked for: its hours are asked beside its open days, not after.
    assert sorted(c["handler"] for c in calls) == ["Disponibilidad", "HorariosDia", "HorariosDia"]
    assert most == 3, "the AM and PM hours were asked one after the other"
    assert found.centres[0].times == ("07:40", "08:00", "15:20")


async def test_availability_on_the_booking_in_front_is_answered_from_it() -> None:
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "agenda", "path": "/"})
        await _page(
            rig,
            "agenda_state",
            _agenda_state(
                day=MON, centre="CENTRO DE SALUD | METRO TOBALABA", times=["07:40", "08:00"]
            ),
        )
        await rig.driver.user_says("¿Hay hora para resonancia de rodilla?")
        found = _results(llm.captured_inputs[-1])["check_availability"]
        assert found.startswith("From the booking on their screen.")
        assert "Hours at CENTRO DE SALUD | METRO TOBALABA on 2030-03-04" in found


# ─── The LASIK form ────────────────────────────────────────────────────────────


async def test_the_lasik_form_is_filled_with_the_forms_own_options() -> None:
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/cirugia-lasik"})
        await rig.driver.user_says(
            "Quiero la evaluación LASIK, soy Juan, Cruz Blanca, en Los Leones."
        )
        assert rig.command("fill_lasik_form") == {
            "name": "Juan Rojas",
            "email": "juan@correo.cl",
            "phone": "912345678",
            "prevision": "CruzBlanca",
            "location": "Santiago - Lyon",
            "focus_rut": False,
        }
        await _page(
            rig,
            "lasik_form_state",
            {"filled": ["name", "email", "phone", "prevision", "location"], "missing": ["rut"]},
        )
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        await _page(
            rig,
            "lasik_form_state",
            {
                "filled": ["name", "rut", "email", "phone", "prevision", "location"],
                "missing": [],
                "valid": True,
            },
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "Presiona Agendar evaluación." in turn.text
        assert "It is complete: the visitor presses" in _texts(llm.captured_inputs[-1])
        # An option the form does not have is refused, and what was filled stays.
        await rig.driver.user_says("Mi previsión es Isapre Inventada, en Valdivia.")
        last = _commands(rig, "fill_lasik_form")[-1]
        assert last["prevision"] == "CruzBlanca" and last["location"] == "Santiago - Lyon"
        await rig.driver.user_says("Sigamos.")
        said = _every(llm.captured_inputs[-1], "fill_lasik_form")[-1]
        assert "Not filled, ask again: previsión" in said and "where (the form lists" in said


def test_the_lasik_options_are_matched_as_a_visitor_says_them() -> None:
    assert clini.prevision_option("fonasa") == "Fonasa"
    assert clini.prevision_option("Banmedica") == "Banmédica"
    assert clini.prevision_option("nueva mas vida") == "Nueva Más Vida"
    assert clini.prevision_option("Isapre X") is None
    assert clini.lasik_location("Metro Tobalaba") == "Santiago - LTO"
    assert clini.lasik_location("Santa Lucía") == "Santiago - Metro Santa Lucía"
    assert clini.lasik_location("temuco") == "Temuco"
    assert clini.lasik_location("Valdivia") is None
    assert clini.mobile("+56 9 8246 3202") == "982463202"
    assert clini.mobile("22 994 4003") is None


# ─── Links and sedes ───────────────────────────────────────────────────────────


async def test_links_are_resolved_by_the_brain_and_an_unknown_one_refused() -> None:
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/consultas-medicas"})
        await rig.driver.user_says("Ábreme traumatología.")
        assert rig.command("open_link") == {
            "kind": "reservo",
            "key": "traumatologia",
            "url": "https://agendamiento.reservo.cl/makereserva/agenda_multisucursal/"
            "r0KRDfl0c0kMvl2A1Q19A3z1i659XG",
        }
        await rig.driver.user_says("Ábreme pediatría.")
        assert len(_commands(rig, "open_link")) == 1
        await rig.driver.user_says("¿Dónde veo mis resultados de imágenes?")
        refused = _every(llm.captured_inputs[-1], "open_link")[-1]
        assert refused.startswith("Not opened: Clini has no reservo link for 'pediatría'.")
        assert _commands(rig, "open_link")[-1] == {
            "kind": "results_imaging",
            "key": None,
            "url": "https://app.dalca.cl/portal/clini?access_type=email",
        }


def test_every_link_is_on_a_host_the_extension_allows() -> None:
    import re

    allowed = re.compile(
        r"^https://(?:[a-z0-9-]+\.)*(?:clini\.cl|agendamiento\.reservo\.cl|app\.dalca\.cl"
        r"|clini\.medipasspro\.com|wa\.me)/"
    )
    for kind, table in clini._LINKS.items():
        for key, url in table.items():
            assert allowed.match(url), (kind, key, url)


async def test_a_sede_is_found_and_shown() -> None:
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("¿Tienen sede en Ñuñoa?")
        found = _results(llm.captured_inputs[-1])["find_branch"]
        assert found.startswith(
            "- Sede Inventada Plaza Norte — Calle Falsa 123, Ñuñoa, Región Metropolitana; "
            "horario: Lunes a Viernes: 08:00 a 20:00hrs; atiende: Laboratorio, Imagenología"
        )
        assert "Temuco" not in found
        assert _commands(rig, "cue")[-1]["text"] == "Sede Inventada Plaza Norte"


async def test_the_prompt_carries_the_booking_list_and_today() -> None:
    prompt = clini._prompt(SITE, clini_api.date(2030, 3, 4))
    assert "Today is Monday, 04 March 2030, in Santiago." in prompt
    assert "- 64 Resonancia — prestaciones: 804 RM Rodilla; 81 RM Columna" in prompt
    assert "- 62 Laboratorio — prestaciones: 30 Toma De Muestra" in prompt
    assert "Eval cir.lasik" not in prompt
    for rule in (
        "THE RUT OR PASSPORT IS THEIRS TO TYPE",
        "chooses Pasaporte",
        "document passport",
        "AGENDAR STAYS THEIRS TO PRESS",
        "SAMU",
        'never "usted"',
    ):
        assert rule in prompt, rule


def test_every_page_the_backstop_names_and_every_servicio_is_in_the_crawl() -> None:
    crawl = kb.load()
    for _, path in clini._ASKED_PAGES:
        assert crawl.page(path) is not None, path
    assert set(clini._services(crawl)) == set(clini._BOOKABLE)


async def test_a_form_locked_until_the_rut_is_a_cue_to_ask_for_it() -> None:
    """agenda-web unlocks the patient fields only once a valid RUT is typed."""
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "agenda", "path": "/"})
        await _page(
            rig,
            "agenda_state",
            _agenda_state(step="booking", day=MON, invalid=["rut"], times=[]),
        )
        await _page(
            rig,
            "command_failed",
            {"command": "fill_agenda_patient", "reason": "ask the visitor to type their RUT"},
        )
        await rig.driver.user_says("Sigamos.")
        seen = _texts(llm.captured_inputs[-1])
        assert "Nothing was filled yet" in seen and "chosen Pasaporte" in seen
        assert "Do not say it failed" not in seen
        assert "That did not happen on the page" not in seen


async def test_a_reply_that_only_promises_is_asked_again_with_tools_off() -> None:
    """ "Un momento." and nothing after it is silence to the visitor, so the
    brain asks once more, as it does for an empty reply: function-calling
    mode NONE over the same tools."""
    llm = _llm()
    seen = llm.requests
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        before = len(seen)
        await rig.driver.user_says("¿Y para la mamografía?")
        first, again = seen[before:]
        assert first.get("tool_choice") == "auto"
        assert again.get("tool_choice") == "none"


# ─── Latency: one client, deadlines, prefetch (dev call 2fd742d5) ─────────────


def _days_body(*days: tuple[str, bool]) -> dict[str, Any]:
    return {
        "exito": True,
        "dias": [{"fecha": d, "tieneDisponibilidad": has, "centros": []} for d, has in days],
    }


async def test_one_kept_alive_client_carries_every_lookup_within_a_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every GET rides one client, warmed before the first question; a lookup
    answers within its deadline with what it has, and what missed it goes on."""
    seen: list[httpx.Request] = []

    async def clini(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "HEAD":
            return httpx.Response(200)
        params = request.url.params
        if params["handler"] == "Disponibilidad":
            if params["prestacion"] == "81":
                await asyncio.sleep(5)
            return httpx.Response(200, json=_days_body((MON, True), ("2030-03-06", True)))
        if params["fecha"] == "2030-03-06":
            await asyncio.sleep(5)
        return httpx.Response(200, json=_hours(["07:40"] if params["periodo"] == "AM" else []))

    monkeypatch.setattr(clini_api, "_get_json", REAL_GET_JSON)
    monkeypatch.setattr(clini_api, "_transport", httpx.MockTransport(clini))
    monkeypatch.setattr(clini_api, "_client", None)
    clini_api.warm()
    await asyncio.gather(*list(clini_api._background))  # pyright: ignore[reportPrivateUsage]
    assert sorted(r.url.host for r in seen) == [
        "agenda-web.clini.cl",
        "agenda-web.clini.cl",
        "cotizador-web.clini.cl",
    ]
    clini_api.warm()  # warm already: nothing more is sent
    assert len(seen) == 3
    client = clini_api._http()  # pyright: ignore[reportPrivateUsage]

    found = await clini_api.availability(64, 804, 13, MON)
    assert found.day == MON and found.centres[0].times == ("07:40",)
    assert clini_api._http() is client, "a lookup opened a client of its own"  # pyright: ignore[reportPrivateUsage]
    asked = len(seen)

    # Another day of the same search: its open days are already known, and
    # its slow hours miss the deadline without failing the answer.
    loop = asyncio.get_running_loop()
    started = loop.time()
    late = await clini_api.availability(64, 804, 13, "2030-03-06", deadline=0.2)
    assert loop.time() - started < 1.0
    assert late.days == ("2030-03-06",) and late.day == "2030-03-06" and late.centres == ()
    assert [r.url.params["handler"] for r in seen[asked:]] == ["HorariosDia", "HorariosDia"]

    # Open days that miss it: slow, and still running for the next ask.
    with pytest.raises(clini_api.LookupSlow):
        await clini_api.availability(64, 81, 13, deadline=0.2)
    assert any(r.url.params.get("prestacion") == "81" for r in seen)


async def test_the_open_days_are_one_answer_whatever_day_they_are_asked_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ "Is there one tomorrow?" after "when is the first?" reads the days
    already listed (dev call 2fd742d5, T25 looked them up again)."""
    calls: list[dict[str, str]] = []
    monkeypatch.setattr(clini_api, "_get_json", _booking(calls))
    await clini_api.availability(64, 804, 13)
    found = await clini_api.availability(64, 804, 13, "2030-03-06")
    assert found.day == "2030-03-06"
    assert [c["handler"] for c in calls].count("Disponibilidad") == 1


async def test_a_booking_that_shows_an_exam_has_its_hours_looked_up_before_the_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []
    monkeypatch.setattr(clini_api, "_get_json", _booking(calls))
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "agenda", "path": "/"})
        await _page(rig, "agenda_state", _agenda_state())
        hours = {(c["fecha"], c["periodo"]) for c in calls if c["handler"] == "HorariosDia"}
        # Its first two open days, morning and afternoon.
        assert {(MON, "AM"), (MON, "PM"), ("2030-03-06", "AM"), ("2030-03-06", "PM")} <= hours
        asked = len(calls)
        # The same search reported again starts nothing new.
        await _page(rig, "agenda_state", _agenda_state(day=MON))
        assert len(calls) == asked
        await rig.driver.user_says("¿Hay hora para resonancia de rodilla?")
        assert len(calls) == asked, "the question did not find the prefetched hours"
        found = _results(llm.captured_inputs[-1])["check_availability"]
        assert "First days with free hours: 2030-03-04 (lunes 4 de marzo)" in found
        # The booking is open on it: a day there is picked, not looked up.
        assert "The booking tab is open on this exam" in found and "agenda_pick" in found


def _quick_llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            # The model's usual booking move: the call alone, no words.
            "Ábreme la agenda de la rodilla.": call(
                "open_agenda", args={"servicio": 64, "prestacion": 804}
            ),
            "Mejor el martes.": 2
            * [reply_and_call("Cambio al martes.", "agenda_pick", args={"day": TUE})],
            "Mejor el lunes.": 2
            * [reply_and_call("Cambio al lunes.", "agenda_pick", args={"day": MON})],
            "Cuéntame de la preparación.": reply(
                chunks=["No necesitas ayuno. ", "Llega quince minutos antes. ", "¿Algo más?"],
                chunk_delay=0.15,
            ),
            # A talk-through that tries to move the booking by itself.
            "The page answered what you sent it": reply_and_call(
                "Listo, ya está abierta la agenda.",
                "fill_agenda_patient",
                args={"focus_rut": True},
            ),
            "¿Y qué horario tienen los sábados?": reply(
                chunks=["Los sábados ", "abren a las ocho."], chunk_delay=0.3
            ),
            "mi celular es nueve uno dos tres cuatro cinco seis siete ocho": reply_and_call(
                "Te lo anoto. Es nueve, uno, dos, tres, cuatro, cinco, seis, siete, ocho.",
                "fill_agenda_patient",
                args={"phone": "912345678"},
            ),
            "Sigamos.": reply("Claro, sigamos."),
        }
    )


async def test_a_booking_move_with_no_words_says_its_line_without_asking_again() -> None:
    """Ten booking moves in ten came back speechless on dev call 2fd742d5, and
    each cost a second model request, 2.3 to 5.2 s of silence: the move's own
    written line is said instead, at once, in the call's language."""
    llm = _quick_llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        before = len(llm.requests)
        turn = await rig.driver.user_says("Ábreme la agenda de la rodilla.")
        check_turn(rig, turn)
        assert rig.command("open_agenda")["servicio"] == 64
        assert turn.text == clini._LANDED["agenda"]["es"]
        assert len(llm.requests) == before + 1


async def test_one_booking_move_at_a_time_the_next_follows_the_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dev call 2fd742d5: a pick sent while the booking was still opening
    raced it, and the open then failed on the pick's day."""
    llm = _quick_llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("Ábreme la agenda de la rodilla.")
        await _page(rig, "agenda_state", _agenda_state())
        await rig.driver.user_says("Mejor el martes.")
        assert _commands(rig, "agenda_pick") == [], "a pick was sent while the open ran"
        await rig.driver.user_says("Sigamos.")
        queued = _every(llm.captured_inputs[-1], "agenda_pick")[-1]
        assert queued.startswith("Queued, not sent yet: the booking is still opening")
        # The open answers: the pick goes now, and only then.
        await _page(rig, "command_done", {"command": "open_agenda", "detail": "results shown"})
        assert _commands(rig, "agenda_pick") == [
            {"day": TUE, "time": None, "centre": None, "period": None}
        ]
        # A move queued behind one that fails is dropped, and said.
        await rig.driver.user_says("Mejor el lunes.")
        assert len(_commands(rig, "agenda_pick")) == 1
        await _page(rig, "command_failed", {"command": "agenda_pick", "reason": "no 5 March"})
        assert len(_commands(rig, "agenda_pick")) == 1
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        seen = _texts(llm.captured_inputs[-1])
        assert "agenda_pick not done: no 5 March (so agenda_pick, asked for while it ran" in seen
        # A move the page never answered stops holding the next one up.
        monkeypatch.setitem(clini._MOVE_TAKES_S, "", 0.0)
        await rig.driver.user_says("Mejor el lunes.")
        await rig.driver.user_says("Mejor el martes.")
        assert [c["day"] for c in _commands(rig, "agenda_pick")] == [TUE, MON, TUE]


async def test_a_talk_through_waits_for_his_turn_and_runs_with_tools_off() -> None:
    """Dev call 2fd742d5, T27: a page answer arriving mid-turn shortened the
    idle window under his own reply, which the quiet spell then cut; and that
    talk-through had filled the form again by itself."""
    llm = _quick_llm()
    seen = llm.requests
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("Ábreme la agenda de la rodilla.")
        speaking = asyncio.create_task(rig.driver.user_says("Cuéntame de la preparación."))
        await asyncio.sleep(0.1)
        await rig.driver.send_ui_event(
            "command_done", {"command": "open_agenda", "detail": "results shown"}
        )
        await asyncio.sleep(0.15)
        assert not speaking.done()
        assert _idle_windows(rig)[-1] == _IDLE_MS, "the idle was shortened under his reply"
        await speaking
        await asyncio.sleep(0.1)
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        before = len(seen)
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "Listo, ya está abierta la agenda." in turn.text
        assert "fill_agenda_patient" not in rig.actions()
        (talk,) = seen[before:]
        assert talk.get("tool_choice") == "none"


async def test_dead_air_with_no_nod_is_held_with_a_late_nod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dev call 2fd742d5, T23 to T25: a turn the nod skipped sat in ten seconds
    of silence, because a hold was only ever said after a nod."""
    monkeypatch.setattr(clini, "HOLD_WITHOUT_NOD_S", 0.1)
    llm = _quick_llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        turn = await rig.driver.user_says("¿Y qué horario tienen los sábados?", quiet_for=1.0)
        check_turn(rig, turn)
        late = [n for n in clini._ACK_LINES["es"]["question"] if turn.text.startswith(n)]
        assert late, turn.text
        assert turn.text.endswith("Los sábados abren a las ocho.")
    # A nod holds longer before its hold line, and the apology waits longer still.
    assert clini.ACK_HOLD_AFTER_S >= 5.5 and clini.ACK_SORRY_AFTER_S >= 15


async def test_a_celular_is_filled_the_moment_it_is_said_then_read_back() -> None:
    """Dev call 2fd742d5, T19 to T21: the read-back rule had him leave the
    phone the visitor had just given empty."""
    prompt = clini._prompt(SITE, clini_api.date(2030, 3, 4))
    assert "Fill a celular or an email the moment they say it, then read it back" in prompt
    llm = _quick_llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "agenda", "path": "/"})
        await _page(rig, "agenda_state", _agenda_state(step="booking", invalid=["phone"]))
        await rig.driver.user_says("mi celular es nueve uno dos tres cuatro cinco seis siete ocho")
        assert rig.command("fill_agenda_patient")["phone"] == "912345678"


# ─── The prod calls of 2026-10-22 ──────────────────────────────────────────────


def _retro_llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            "¿Hay hora para resonancia de rodilla?": [
                call("check_availability", args={"servicio": 64, "prestacion": 804}),
                reply("Hay hora el lunes en Tobalaba. ¿Te sirve?"),
            ],
            # A sede find_branch knows and the booking does not list for it.
            "Sí, en la Sede Inventada Plaza Norte.": reply_and_call(
                "Te abro la agenda.",
                "open_agenda",
                args={"servicio": 64, "prestacion": 804, "day": MON},
            ),
            # The sede they chose, dropped from the call (prod: "centre": null).
            "Sí, en Tobalaba.": reply_and_call(
                "Te abro la agenda.",
                "open_agenda",
                args={"servicio": 64, "prestacion": 804, "day": MON, "time": "07:40"},
            ),
            "Agenda la rodilla el lunes a las siete y cuarenta en Tobalaba.": reply_and_call(
                "Te abro la agenda.",
                "open_agenda",
                args={
                    "servicio": 64,
                    "prestacion": 804,
                    "day": MON,
                    "centre": "CENTRO DE SALUD | METRO TOBALABA",
                    "time": "7:40",
                },
            ),
            "Las siete y cuarenta en Tobalaba.": reply_and_call(
                "Te selecciono las siete y cuarenta.",
                "agenda_pick",
                args={"day": MON, "time": "07:40", "centre": "TOBALABA"},
            ),
            "Las diez en Quinta Vergara.": reply_and_call(
                "Te selecciono las diez.",
                "agenda_pick",
                args={"day": MON, "time": "10:00", "centre": "CENTRO DE SALUD | QUINTA"},
            ),
            # The model's usual fill: the call alone, no words.
            "Me llamo Ana, soy mujer, mi celular es nueve nueve nueve dos dos dos ocho cinco "
            "cero cuatro.": call(
                "fill_agenda_patient",
                args={"name": "Ana", "sex": "F", "phone": "9992228504"},
            ),
            "Me llamo Pedro Rojas.": call(
                "fill_agenda_patient", args={"name": "Pedro", "last_name": "Rojas", "sex": "M"}
            ),
            "Mi teléfono es el nueve nueve nueve.": call("fill_agenda_patient", args={}),
            "¿Me ayudas con el examen?": reply(
                "{faq: necesito orden medica} ¿Qué examen necesitas hacerte hoy? Te ayudo con eso."
            ),
            "Perfecto, muchas gracias por tu ayuda.": reply(
                chunks=["Un placer ", "ayudarte."], chunk_delay=0.3
            ),
            "¿Cuánto cuesta el hemograma?": [
                call("quote_price", args={"query": "hemograma"}),
                reply("Con Fonasa sale mil pesos."),
            ],
            "Sigamos.": reply("Claro, sigamos."),
        }
    )


async def test_an_hour_is_offered_and_booked_only_at_a_centre_the_booking_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prod: Tobalaba offered for a lab booking agenda-web does not take there,
    accepted, and sent as ``centre: null``; the visitor gave up."""
    prompt = clini._prompt(SITE, clini_api.date(2030, 3, 4))
    assert "OFFER AN ONLINE HOUR ONLY AT A CENTRE check_availability OR THE BOOKING" in prompt
    assert "walk-ins by order of arrival" in prompt
    monkeypatch.setattr(clini_api, "_get_json", _booking([]))
    llm = _retro_llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("¿Hay hora para resonancia de rodilla?")
        found = _results(llm.captured_inputs[-1])["check_availability"]
        assert (
            "Centres bookable online for this exam: CENTRO DE SALUD | METRO TOBALABA. Offer an "
            "hour only at one of these"
        ) in found
        # A sede the booking does not list: not opened, and said so.
        await rig.driver.user_says("Sí, en la Sede Inventada Plaza Norte.")
        assert "open_agenda" not in rig.actions()
        await rig.driver.user_says("Sigamos.")
        (refused,) = _every(llm.captured_inputs[-1], "open_agenda")
        assert refused.startswith("Not opened: the sede they chose (inventada, norte)")
        assert "it lists only CENTRO DE SALUD | METRO TOBALABA" in refused
        # The listed sede they named, left out of the call: put back in.
        await rig.driver.user_says("Sí, en Tobalaba.")
        assert rig.command("open_agenda")["centre"] == "CENTRO DE SALUD | METRO TOBALABA"


async def test_a_pick_already_on_its_way_or_on_screen_is_not_sent_again() -> None:
    """Prod: a pick of the hour the open had chosen took the patient form down
    and put it back, twice."""
    llm = _retro_llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("Agenda la rodilla el lunes a las siete y cuarenta en Tobalaba.")
        await rig.driver.user_says("Las siete y cuarenta en Tobalaba.")
        await rig.driver.user_says("Sigamos.")
        (pending,) = _every(llm.captured_inputs[-1], "agenda_pick")
        assert pending.startswith("Not sent: the booking is already on its way to exactly that")
        await _page(rig, "command_done", {"command": "open_agenda", "detail": "form open"})
        assert _commands(rig, "agenda_pick") == []

    llm = _retro_llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "agenda", "path": "/"})
        selected = "LUNES, 4 DE MARZO DE 2030 A LAS 10:00 (AM) · CENTRO DE SALUD | QUINTA"
        form = _agenda_state(
            step="booking", day=MON, centre="CENTRO DE SALUD | QUINTA", selected=selected
        )
        await _page(rig, "agenda_state", form)
        await rig.driver.user_says("Las diez en Quinta Vergara.")
        await rig.driver.user_says("Sigamos.")
        (shown,) = _every(llm.captured_inputs[-1], "agenda_pick")
        assert shown.startswith(f"Not sent: that is already selected on their screen ({selected})")
        assert _commands(rig, "agenda_pick") == []


async def test_a_call_the_model_makes_with_tools_off_is_not_run() -> None:
    """Prod: an idle turn with tools off ran an ``agenda_pick``. The model does not
    always honour the mode; the scripted model is made not to, here."""
    llm = _quick_llm()
    answer = llm.answer

    def ignoring(request: dict[str, Any]) -> Any:
        return answer({**request, "tool_choice": "auto"})

    llm.answer = ignoring  # type: ignore[method-assign]
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("Ábreme la agenda de la rodilla.")
        await _page(rig, "command_done", {"command": "open_agenda", "detail": "results shown"})
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "Listo, ya está abierta la agenda." in turn.text
        assert "fill_agenda_patient" not in rig.actions()
        await rig.driver.user_says("Sigamos.")
        (result,) = _every(llm.captured_inputs[-1], "fill_agenda_patient")
        assert result.startswith("Not run: this turn could only speak")


async def test_his_line_on_a_fill_says_what_the_fill_did() -> None:
    """Prod: "Te lo completo en el formulario de la agenda." after a fill that
    took nothing; a celular counted wrong by the model; sex filled from a name."""
    prompt = clini._prompt(SITE, clini_api.date(2030, 3, 4))
    assert "NEVER COUNT OR JUDGE THE DIGITS YOURSELF" in prompt
    assert "Never guess it from a name or a voice" in prompt
    assert "quedó lista tu hora" in prompt
    llm = _retro_llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "agenda", "path": "/"})
        await _page(rig, "agenda_state", _agenda_state(step="booking", invalid=["name"]))
        turn = await rig.driver.user_says(
            "Me llamo Ana, soy mujer, mi celular es nueve nueve nueve dos dos dos ocho cinco "
            "cero cuatro."
        )
        assert turn.text == (
            "Te anoto tu nombre y tu sexo en el formulario. " + clini._ASK_AGAIN["phone"]["es"]
        )
        assert rig.command("fill_agenda_patient")["sex"] == "F"
        await _page(rig, "command_done", {"command": "fill_agenda_patient", "detail": "filled"})
        # Sex the visitor never said is not filled, and asked for.
        turn = await rig.driver.user_says("Me llamo Pedro Rojas.")
        assert turn.text == (
            "Te anoto tu nombre y tu apellido paterno en el formulario. "
            + clini._ASK_AGAIN["sex"]["es"]
        )
        await _page(rig, "command_done", {"command": "fill_agenda_patient", "detail": "filled"})
        # A fill that took nothing says so, and asks again.
        turn = await rig.driver.user_says("Mi teléfono es el nueve nueve nueve.")
        assert turn.text == clini._ASK_AGAIN[""]["es"]
        await rig.driver.user_says("Sigamos.")
        results = _every(llm.captured_inputs[-1], "fill_agenda_patient")
        assert "(10 digits given)" in results[0]
        assert "sex: they did not say it" in results[1]
        # Ana's sex stays as she said it; Pedro's guess never reached the page.
        assert [c["sex"] for c in _commands(rig, "fill_agenda_patient")] == ["F", "F", "F"]


async def test_patience_is_raised_while_the_patient_form_is_dictated() -> None:
    """Prod: at the call's patience a dictated name or celular came in pieces,
    each a turn that cancelled the last."""
    async with demo("clini", _retro_llm()) as rig:
        await rig.driver.start_session(init={"site": "agenda", "path": "/"})

        def patience() -> list[int | None]:
            return [c.stt.patience for c in _configs(rig) if c.stt is not None]

        assert patience() == [clini.CLINI_PATIENCE]
        await _page(rig, "agenda_state", _agenda_state(step="booking", invalid=["rut"]))
        assert patience()[-1] == clini.FORM_PATIENCE
        await _page(rig, "agenda_state", _agenda_state(step="booking", invalid=[], ready=True))
        assert patience()[-1] == clini.CLINI_PATIENCE
        assert all(c.stt.language is None for c in _configs(rig)[1:] if c.stt is not None)


def test_nods_fit_what_was_said() -> None:
    """Prod: "Entendido, gracias por avisarme." for "Me gustaría cotizar mi
    examen."; "Dame un momento mientras lo busco." for a thank-you."""
    assert clini.nod_kind("Me gustaría cotizar mi examen.") == "request"
    assert clini.nod_kind("No, yo Javier, yo quiero agendar una resonancia.") == "request"
    assert all("avisarme" not in n for n in clini._ACK_LINES["es"]["statement"])
    assert clini.is_closing("Voy a completar el resto. Muchas gracias.")
    assert not clini.is_closing("Gracias, ¿y cuánto cuesta?")
    assert clini.HOLD_WITHOUT_NOD_S >= 3.0


async def test_a_thank_you_gets_no_hold_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clini, "HOLD_WITHOUT_NOD_S", 0.1)
    async with demo("clini", _retro_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        turn = await rig.driver.user_says("Perfecto, muchas gracias por tu ayuda.", quiet_for=1.0)
        assert turn.text == "Un placer ayudarte."


async def test_an_faq_rung_on_a_sentence_it_is_not_about_is_dropped() -> None:
    """Prod: "¿Qué examen necesitas hacerte?" rang "¿Qué es mejor estar en
    fonasa o isapre?"."""
    async with demo("clini", _retro_llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": RM})
        await rig.driver.user_says("¿Me ayudas con el examen?")
        assert not [c for c in _commands(rig, "cue") if c["faq"]], _commands(rig, "cue")


async def test_a_lab_price_looks_up_the_labs_hours_before_they_are_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prod: the lab search took its whole 6 s deadline when asked."""
    started: list[tuple[int, int, int | None]] = []
    monkeypatch.setattr(clini_api, "prefetch", lambda s, p, r: started.append((s, p, r)))
    llm = _retro_llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("¿Cuánto cuesta el hemograma?")
        assert "Hemograma Inventado" in _results(llm.captured_inputs[-1])["quote_price"]
        assert (62, 30, 13) in started
