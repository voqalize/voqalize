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

import pytest
from google.genai import types
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply, reply_and_call

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

    async def offline(url: str, params: dict[str, str], timeout: float) -> Any:
        raise clini_api.LookupFailed(f"no network in tests: {url}")

    monkeypatch.setattr(clini_api, "_get_json", offline)
    clini_api.clear_cache()
    yield
    clini_api.clear_cache()


def _results(contents: list[types.Content]) -> dict[str, str]:
    return {
        p.function_response.name or "": str((p.function_response.response or {})["result"])
        for c in contents
        for p in (c.parts or [])
        if p.function_response is not None
    }


def _every(contents: list[types.Content], name: str) -> list[str]:
    """Every result of tool ``name`` in one request, in order. A tool that is not a
    read is answered in the request after its turn: the visitor's next message."""
    return [
        str((p.function_response.response or {})["result"])
        for c in contents
        for p in (c.parts or [])
        if p.function_response is not None and p.function_response.name == name
    ]


def _texts(contents: list[types.Content]) -> str:
    return "\n".join(p.text or "" for c in contents for p in (c.parts or []))


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
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
                "{page: /no-existe} {faq: necesito orden medica} Sí, con orden médica."
            ),
            "¿Cuánto cuesta una resonancia de rodilla?": [
                call("quote_price", request={"query": "resonancia rodilla"}),
                reply("Con Fonasa sale ochenta mil pesos."),
            ],
            "¿Hay hora para resonancia de rodilla?": [
                call("check_availability", request={"servicio": 64, "prestacion": 804}),
                reply("Hay hora el lunes cuatro de marzo. ¿Te sirve?"),
            ],
            "¿Hay hora para resonancia?": [
                call("check_availability", request={"servicio": 64}),
                reply("¿De rodilla o de columna?"),
            ],
            "¿Hay hora para sangre el martes?": [
                call("check_availability", request={"servicio": 62, "day": TUE}),
                reply("El martes no queda; el miércoles sí."),
            ],
            "Agéndame la evaluación LASIK en la agenda.": reply_and_call(
                "Eso va por el formulario.", "open_agenda", request={"servicio": 74}
            ),
            "Resonancia de columna, en Arica.": reply_and_call(
                "Te abro la agenda.", "open_agenda", request={"servicio": 64, "prestacion": 999}
            ),
            "Agenda la rodilla el lunes a las siete y cuarenta en Tobalaba.": reply_and_call(
                "Listo, te abrí la agenda.",
                "open_agenda",
                request={
                    "servicio": 64,
                    "prestacion": 804,
                    "day": MON,
                    "centre": "CENTRO DE SALUD | METRO TOBALABA",
                    "time": "7:40",
                },
            ),
            "Mejor el martes.": reply_and_call(
                "Cambio al martes.", "agenda_pick", request={"day": TUE}
            ),
            "shows its open days": reply("Hay hora el lunes y el martes. ¿Cuál prefieres?"),
            "patient form is open": reply("Tu hora es el lunes. ¿Me dices tu nombre?"),
            "Soy Ana Pérez Soto, mi celular es +56 9 1234 5678.": 2
            * [
                reply_and_call(
                    "Anoté tu celular, nueve uno dos tres.",
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
                request={"email": " Ana@Correo.cl ", "focus_rut": True},
            ),
            "Everything on the booking form is complete": reply("Listo. Presiona AGENDAR tú."),
            "shows the hour as booked": reply("Felicitaciones, quedó agendada."),
            "Quiero la evaluación LASIK, soy Juan, Cruz Blanca, en Los Leones.": reply_and_call(
                "Completo el formulario.",
                "fill_lasik_form",
                request={
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
                request={"prevision": "Isapre Inventada", "location": "Valdivia"},
            ),
            "LASIK evaluation form is complete": reply("Ya está. Presiona Agendar evaluación."),
            "Ábreme traumatología.": reply_and_call(
                "Te abro la agenda de traumatología.",
                "open_link",
                request={"kind": "reservo", "key": "Traumatología"},
            ),
            "Ábreme pediatría.": reply_and_call(
                "Veamos.", "open_link", request={"kind": "reservo", "key": "pediatría"}
            ),
            "¿Dónde veo mis resultados de imágenes?": reply_and_call(
                "Te abro el portal.", "open_link", request={"kind": "results_imaging"}
            ),
            "¿Tienen sede en Ñuñoa?": [
                call("find_branch", request={"query": "Ñuñoa"}),
                reply("{page: /ubicaciones}{show: Sede Inventada Plaza Norte} Sí, en Ñuñoa."),
            ],
            "Cámbiame el día a mañana.": 2
            * [reply_and_call("Veamos.", "agenda_pick", request={"day": TUE})],
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

NONE = {"path": None, "heading": None, "text": None, "faq": None}


async def test_cues_leave_the_speech_and_are_checked_against_the_site() -> None:
    async with demo("clini", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        turn = await rig.driver.user_says("¿Me muestras la resonancia?")
        check_turn(rig, turn)
        assert "{" not in turn.text and "}" not in turn.text
        # The page with its trailing slash; the heading in the site's spelling,
        # accents and case folded; words that are no heading rung as words; the
        # invented page dropped; and the FAQ on the page the reply is on.
        path = RM + "/"
        assert _commands(rig, "cue") == [
            {**NONE, "at": "aqui estan las", "word": 0, "path": path},
            {
                **NONE,
                "at": "aqui estan las",
                "word": 0,
                "path": path,
                "heading": "Exámenes de Resonancia Magnética",
            },
            {**NONE, "at": "se agenda en", "word": 4, "path": path, "text": "el botón rosado"},
            {
                **NONE,
                "at": "si con orden",
                "word": 8,
                "path": path,
                "faq": "¿Necesito orden médica?",
            },
        ]


async def test_what_they_asked_about_is_shown_when_his_reply_forgets_to() -> None:
    async with demo("clini", _llm()) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("¿Cuánto cuesta una resonancia de rodilla?")
        assert _commands(rig, "cue")[0] == {
            **NONE,
            "at": "con fonasa sale",
            "word": 0,
            "path": RM + "/",
        }


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
        assert url == clini_api.COTIZADOR and timeout <= 3.0
        return [_KNEE, {"nombre": ""}, "junk"]

    monkeypatch.setattr(clini_api, "_get_json", cotizador)
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        turn = await rig.driver.user_says("¿Cuánto cuesta una resonancia de rodilla?")
        check_turn(rig, turn)
        quoted = _results(llm.captured_contents[-1])["quote_price"]
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
        quoted = _results(llm.captured_contents[-1])["quote_price"]
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
        assert url == clini_api.AGENDA and timeout <= 4.0
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
        found = _results(llm.captured_contents[-1])["check_availability"]
        assert found.splitlines()[0] == "Resonancia — RM Rodilla, Región Metropolitana."
        assert "First days with free hours: 2030-03-04 (lunes 4 de marzo); 2030-03-06" in found
        assert (
            "- CENTRO DE SALUD | METRO TOBALABA (LUIS THAYER OJEDA 073): 07:40, 08:00, 15:20"
        ) in found
        assert [c["handler"] for c in calls] == ["Disponibilidad", "HorariosDia", "HorariosDia"]
        assert calls[0] == {
            "handler": "Disponibilidad",
            "servicio": "64",
            "prestacion": "804",
            "region": "13",
            "buscarPrimera": "true",
        }
        # Every call is a read: never the booking itself, never a patient lookup.
        assert not {c["handler"] for c in calls} & {"AgendarCitaMedica", "PacientePorDocumento"}


async def test_a_servicio_with_several_prestaciones_asks_which_first() -> None:
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("¿Hay hora para resonancia?")
        found = _results(llm.captured_contents[-1])["check_availability"]
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
        found = _results(llm.captured_contents[-1])["check_availability"]
        assert "2030-03-05 (martes 5 de marzo) has no free hours; the next is 2030-03-04" in found
        # One prestación, taken for them; the RM laboratorio search is by sector.
        assert calls[0]["prestacion"] == "30" and calls[0]["sector"] == "TODOS"
        assert calls[0]["desde"] == TUE


async def test_a_booking_that_does_not_answer_is_said_plainly() -> None:
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("¿Hay hora para resonancia de rodilla?")
        found = _results(llm.captured_contents[-1])["check_availability"]
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
        lasik, invented = _every(llm.captured_contents[-1], "open_agenda")
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
        # The booking reports its open days: he talks them through in the short
        # quiet spell, and the note says the days as a Chilean says them.
        await _page(rig, "agenda_state", _agenda_state())
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "¿Cuál prefieres?" in turn.text
        seen = _texts(llm.captured_contents[-1])
        assert (
            "[The booking shows its calendar and hours, for Resonancia — RM Rodilla, region 13. "
            "Open days: 2030-03-04 (lunes 4 de marzo); 2030-03-05 (martes 5 de marzo)."
        ) in seen
        assert _idle_windows(rig)[-1] == _IDLE_MS

        # A later pick on the tab already open.
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
        seen = _texts(llm.captured_contents[-1])
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
        (early,) = _every(llm.captured_contents[-1], "fill_agenda_patient")
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
            "focus_rut": False,
        }
        # What is filled stays; the email is tidied and read back; the RUT field rung.
        await rig.driver.user_says("Mi correo es ana@correo.cl, y el RUT lo escribo yo.")
        last = _commands(rig, "fill_agenda_patient")[-1]
        assert last["name"] == "Ana" and last["phone"] == "912345678"
        assert last["email"] == "ana@correo.cl" and last["focus_rut"] is True
        await rig.driver.user_says("Sigamos.")
        said = _every(llm.captured_contents[-1], "fill_agenda_patient")[-1]
        assert "Read the email back: ana@correo.cl." in said
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
        assert "Open days: 2030-03-04 (lunes 4 de marzo)" in _texts(llm.captured_contents[-1])


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
        seen = _texts(llm.captured_contents[-1])
        assert "1: CLINI; 2: Agenda (the booking) (in front)" in seen
        (refused,) = _every(llm.captured_contents[-1], "agenda_pick")
        assert refused == "Not done: no booking tab is open. Use open_agenda first."
        await rig.driver.user_says("Cámbiame el día a mañana.")
        assert _commands(rig, "agenda_pick") == [
            {"day": TUE, "time": None, "centre": None, "period": None}
        ]


async def test_a_failed_booking_step_cancels_its_talk_through() -> None:
    llm = _llm()
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        await rig.driver.user_says("Agenda la rodilla el lunes a las siete y cuarenta en Tobalaba.")
        await _page(rig, "agenda_state", _agenda_state())
        await _page(rig, "command_failed", {"command": "open_agenda", "reason": "no 07:40"})
        assert _idle_windows(rig)[-1] == _IDLE_MS
        await rig.driver.user_says("Sigamos.")
        assert "That did not happen on the page (open_agenda: no 07:40)" in _texts(
            llm.captured_contents[-1]
        )


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
        assert "It is complete: the visitor presses" in _texts(llm.captured_contents[-1])
        # An option the form does not have is refused, and what was filled stays.
        await rig.driver.user_says("Mi previsión es Isapre Inventada, en Valdivia.")
        last = _commands(rig, "fill_lasik_form")[-1]
        assert last["prevision"] == "CruzBlanca" and last["location"] == "Santiago - Lyon"
        await rig.driver.user_says("Sigamos.")
        said = _every(llm.captured_contents[-1], "fill_lasik_form")[-1]
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
        refused = _every(llm.captured_contents[-1], "open_link")[-1]
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
        found = _results(llm.captured_contents[-1])["find_branch"]
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
        "THE RUT IS THEIRS TO TYPE",
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
        seen = _texts(llm.captured_contents[-1])
        assert "keeps its other fields locked until the visitor types their RUT" in seen
        assert "That did not happen on the page" not in seen


async def test_a_reply_that_only_promises_is_asked_again_with_tools_off() -> None:
    """ "Un momento." and nothing after it is silence to the visitor, so the
    brain asks once more, as it does for an empty reply: function-calling
    mode NONE over the same tools."""
    llm = _llm()
    seen: list[types.GenerateContentConfig] = []
    answer = llm.answer

    def recording(*, model: str, contents: object, config: types.GenerateContentConfig) -> object:
        seen.append(config)
        return answer(model=model, contents=contents, config=config)

    llm.answer = recording
    async with demo("clini", llm) as rig:
        await rig.driver.start_session(init={"site": "site", "path": "/"})
        before = len(seen)
        await rig.driver.user_says("¿Y para la mamografía?")
        first, again = seen[before:]
        assert first.tool_config is None
        assert again.tool_config == types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode=types.FunctionCallingConfigMode.NONE
            )
        )
