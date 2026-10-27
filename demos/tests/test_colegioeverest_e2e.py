"""Javier, Colegio Everest's guide, end to end over the wire — no network, no LLM key.

The real ``ColegioEverestBrain`` on a real ``brain_server`` socket, driven by
the conformance ``VoqalizeDriver``, with only the model scripted. The knowledge
is a small invented Colegio Everest in the crawl's own shape, put in place of
the committed one, and "today" is fixed, so no test depends on what the crawl
found this week or on the day it runs.

What this demo earns that others do not:

**The screen follows his voice, on the site's own places.** Every cue is
checked against the catalogue of places (``anchors.json``): a key that is not
there is dropped, a place that is on one other page only takes the visitor
there, and what they asked about is shown when his reply forgets to.

**The child's level, by the site's rule.** ``find_level`` places a child for
2027 from a birth date, an age or the grade they are in now, says the window
has closed when it has, gives the published vacancies and fees with their
words, marks a level the site gives no age for as an estimate, and names the
card to show.

**The visitor presses the button.** He fills the contact form as they dictate
it — only what they said, never a RUT — and the page tells him when it is
complete and when the site answered their press; he says so in the next quiet
spell, with tools off. No Action can submit. The application and the visit
booking only ever open in a new tab.

**Spanish first, and "tú".** The site is Chilean, so the call opens in Spanish,
follows a visitor who speaks English, and holds a language they chose.

Run: ``cd demos && uv run pytest tests/test_colegioeverest_e2e.py``
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

from voqalize_demos._loaded.colegioeverest import brain as ce  # noqa: E402
from voqalize_demos._loaded.colegioeverest import knowledge as kb  # noqa: E402
from voqalize_demos._loaded.colegioeverest.brain import (  # noqa: E402
    _IDLE_MS,
    _LANDED,
    _SAY_READY,
    _TALK_THROUGH_MS,
    ADMISSIONS_EMAIL,
    TOGGLE_CONFIRM,
    asked_target,
    grade_key,
    greeting,
    language_of,
    place_child,
)
from voqalize_demos._loaded.colegioeverest.knowledge import (  # noqa: E402
    Anchor,
    Document,
    Exit,
    FeeBand,
    Fees,
    Knowledge,
    Level,
    Page,
    Section,
)

# ─── An invented Colegio Everest ───────────────────────────────────────────────

TODAY = date(2026, 10, 27)
HOME = "/"
ADM = "/bienvenidos-al-proceso-de-admision-del-colegio-everest/"
CONTACT = "/contacto/"
ENGLISH = "/nuestro-modelo-educativo/ingles-intensivo/"
INFRA = "/nuestro-colegio/infraestructura/"
HISTORY = "/nuestro-colegio/historia/"
BOOKINGS = "https://bookings.cloud.microsoft/bookwithme/user/x%40colegioeverest.cl?anonymous"
ALEXIA_FORM = "https://colegioeverest.alexiaeducl.com/AcWeb/paginas/publicas/FormularioMatriculacion.aspx?token=t"
VACANTES = "https://www.colegioeverest.cl/wp-content/uploads/2026/03/VACANTES-EVEREST-2027.pdf"
VALORES_2027 = "https://www.colegioeverest.cl/wp-content/uploads/2026/10/Ver-valores-de-matricula-y-colegiaturas-2027_.pdf"

CHROME = (
    Anchor("menu_principal", "Menú principal"),
    Anchor("pie_contacto", "Pie: dirección y teléfono"),
    Anchor("pie_mapa", "Pie: mapa de Google del colegio"),
)


def _level(
    key: str,
    name: str,
    *,
    months: int | None,
    born_by: date | None,
    seq: int | None,
    window: str,
    opens: date,
    closes: date,
    place: str,
    vacancies: int,
    band: str,
) -> Level:
    return Level(
        key=key,
        name=name,
        cycle="I" if months is not None or key == "kinder" else "II",
        age_text=f"{months // 12} años cumplidos al 31 de marzo 2027" if months else "",
        min_age_months=months,
        born_by=born_by,
        age_if_sequence=seq,
        window_text=window,
        opens=opens,
        closes=closes,
        place=place,
        vacancies=vacancies,
        priority_neep=1 if key == "prekinder" else 0,
        fee_band_2026="",
        fee_band_2027=band,
        admission_day="Come and Play" if months else "Evaluación de inglés y entrevista",
        results="tres semanas después del Admission Day",
    )


# Invented, in the crawl's shape: the names are the site's kind, the facts ours.
SITE = Knowledge(
    l1="Colegio Everest is a Catholic school in Lo Barnechea (invented for tests).",
    topics={},
    pages={
        HOME: Page(
            HOME,
            "Bienvenidos al Everest",
            kind="home",
            sections=(
                Section("hero", "Portada: Bienvenidos al Everest", "Comunidad educativa."),
                Section("noticias", "Noticias: carrusel de las últimas noticias", ""),
            ),
        ),
        ADM: Page(
            ADM,
            "Bienvenidos al Proceso de Admisión del Colegio Everest",
            kind="admission",
            sections=(
                Section("fechas", "Fechas de Postulación", "Prekínder Playgroup Kínder"),
                Section("fecha_playgroup", "Fechas: Playgroup 2027 (3 años)", "1 al 15 de abril"),
                Section("fecha_prekinder", "Fechas: Prekínder 2027 (4 años)", "familias nuevas"),
                Section("pasos", "Pasos de Postulación", "ocho pasos"),
                Section("paso_4_visita", "Paso 4: Visita nuestro colegio", "Agenda AQUÍ"),
                Section("paso_6_admission_day", "Paso 6: Admission Day", "Come and Play"),
                Section("vacantes", "Botón Vacantes 2027 (PDF)", ""),
                Section("valores", "Botón Valores 2026 (PDF)", ""),
            ),
        ),
        CONTACT: Page(
            CONTACT,
            "Contacto",
            kind="contact",
            sections=(Section("formulario", "Formulario de contacto", ""),),
        ),
        ENGLISH: Page(
            ENGLISH,
            "Inglés Intensivo",
            kind="education",
            sections=(
                Section("intro", "Inglés intensivo: Marco Común Europeo", ""),
                Section("ruta", "La ruta del inglés: A1, A2, B1, B2", ""),
                Section("certificaciones", "Certificaciones Cambridge B2 y C1", ""),
            ),
        ),
        INFRA: Page(
            INFRA,
            "Infraestructura",
            kind="school",
            sections=(Section("galeria", "Galería de fotos", ""),),
        ),
        HISTORY: Page(
            HISTORY,
            "Historia",
            kind="school",
            sections=(Section("fundacion_1995", "1995: fundación", ""),),
        ),
    },
    anchors={
        HOME: (
            Anchor("hero", "Portada"),
            Anchor("noticias", "Noticias"),
            Anchor("noticias_carrusel", "Carrusel de noticias"),
            Anchor("noticias_siguiente", "Flecha", hidden=True),
            *CHROME,
        ),
        ADM: (
            Anchor("fechas", "Fechas de Postulación"),
            Anchor("fecha_playgroup", "Fechas: Playgroup 2027"),
            Anchor("fecha_prekinder", "Fechas: Prekínder 2027"),
            Anchor("fecha_kinder_iv_medio", "Fechas: Kínder a IV medio 2027"),
            Anchor("pasos", "Pasos de Postulación"),
            Anchor("paso_4_visita", "Paso 4: Visita nuestro colegio"),
            Anchor("paso_6_admission_day", "Paso 6: Admission Day"),
            Anchor("vacantes", "Botón Vacantes 2027"),
            Anchor("valores", "Botón Valores 2026"),
            Anchor("encargada_admision", "Encargada de Admisión"),
            Anchor("cta_agendar_visita", "Agenda AQUÍ", hidden=True),
            *CHROME,
        ),
        CONTACT: (
            Anchor("formulario", "Formulario de contacto"),
            Anchor("submit", "Enviar", hidden=True),
            *CHROME,
        ),
        ENGLISH: (
            Anchor("intro", "Inglés"),
            Anchor("ruta", "Ruta"),
            Anchor("certificaciones", "Cambridge"),
            *CHROME,
        ),
        INFRA: (Anchor("galeria", "Galería"), *CHROME),
        HISTORY: (Anchor("fundacion_1995", "Fundación"), *CHROME),
        "/informacion-practica/casino/": (Anchor("valores", "Valores del casino"), *CHROME),
    },
    levels=(
        _level(
            "playgroup",
            "Playgroup",
            months=36,
            born_by=date(2024, 3, 31),
            seq=None,
            window="1 al 15 de abril de 2026",
            opens=date(2026, 4, 1),
            closes=date(2026, 4, 15),
            place="fecha_playgroup",
            vacancies=29,
            band="mb_b_pg",
        ),
        _level(
            "prekinder",
            "Prekínder",
            months=48,
            born_by=date(2023, 3, 31),
            seq=None,
            window="Familias nuevas 20 de febrero al 10 de marzo 2026",
            opens=date(2026, 2, 20),
            closes=date(2026, 3, 10),
            place="fecha_prekinder",
            vacancies=40,
            band="pk_k",
        ),
        _level(
            "kinder",
            "Kínder",
            months=None,
            born_by=None,
            seq=5,
            window="julio a septiembre 2026",
            opens=date(2026, 7, 1),
            closes=date(2026, 9, 30),
            place="fecha_kinder_iv_medio",
            vacancies=2,
            band="pk_k",
        ),
        _level(
            "1_basico",
            "1° básico",
            months=None,
            born_by=None,
            seq=6,
            window="julio a septiembre 2026",
            opens=date(2026, 7, 1),
            closes=date(2026, 9, 30),
            place="fecha_kinder_iv_medio",
            vacancies=0,
            band="b1_4",
        ),
    ),
    fees={
        "2027": Fees(
            year="2027",
            source=VALORES_2027,
            linked=False,
            bands={
                "mb_b_pg": FeeBand(
                    "mb_b_pg", "Mini Bambolino - Bambolino - Playgroup", "10,646", "10,57", "105,68"
                ),
                "pk_k": FeeBand("pk_k", "Prekinder y Kinder", "15,996", "19,33", "193,34"),
                "b1_4": FeeBand("b1_4", "1° a 4° básico", "15,996", "19,56", "195,62"),
            },
            cuotas=10,
            seguro="",
            note="",
        )
    },
    documents=(
        Document(
            VACANTES,
            ("Vacantes 2027",),
            (ADM,),
            True,
            "VACANTES-EVEREST-2027.pdf",
            "Vacantes 2027 por nivel",
        ),
        Document(
            VALORES_2027,
            (),
            (),
            False,
            "Ver-valores-de-matricula-y-colegiaturas-2027_.pdf",
            "Valores 2027 (UF): matrícula y colegiatura por nivel",
        ),
        Document(
            "https://www.colegioeverest.cl/wp-content/uploads/2021/07/Protocolo-COVID.pdf",
            ("Descargar Aquí",),
            (),
            True,
            "Protocolo-COVID.pdf",
            "Protocolo COVID",
            broken=True,
        ),
    ),
    exits={
        "postulacion": Exit("postulacion", "Postulación ONLINE (Alexia)", ALEXIA_FORM, ""),
        "visita": Exit("visita", "Agenda AQUÍ (Microsoft Bookings)", BOOKINGS, ""),
        "alexia": Exit(
            "alexia",
            "Alexia (plataforma de apoderados)",
            "https://colegioeverest.alexiaeducl.com/",
            "",
        ),
    },
    cutoff=date(2027, 3, 31),
)


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every session reads the invented school on a fixed day, and he never
    nods unless a test asks him to: a nod is a unit of its own."""
    monkeypatch.setattr(kb, "KNOWLEDGE", SITE)
    monkeypatch.setattr(ce, "ACK_RATE", 0.0)
    monkeypatch.setattr(ce, "_today", lambda: TODAY)
    yield


# ─── Reading the wire ──────────────────────────────────────────────────────────


def _results(items: list[Any]) -> dict[str, str]:
    return tool_results(items)


def _all_results(items: list[Any], name: str) -> list[str]:
    return tool_results_of(items, name)


def _texts(items: list[Any]) -> str:
    return input_texts(items)


async def _page(rig: object, event: str, payload: dict[str, object]) -> None:
    await rig.driver.send_ui_event(event, payload)  # type: ignore[attr-defined]
    # `on_rtvi` takes no floor and there is nothing to await: give it a moment.
    await asyncio.sleep(0.1)


def _idle_windows(rig: object) -> list[int | None]:
    return [c.idle.timeout_ms for c in _configs(rig) if c.idle is not None]  # type: ignore[arg-type]


def _commands(rig: object, name: str) -> list[dict[str, object]]:
    return [c["payload"] for c in rig.driver.ui_commands if c.get("command") == name]  # type: ignore[attr-defined]


def _language_changes(rig: object) -> list[object]:
    return _commands(rig, "language_changed")


def _cues(rig: object) -> list[dict[str, object]]:
    return _commands(rig, "cue")


NONE = {"path": None, "anchor": None, "text": None}


def _page_changed(path: str, **fields: object) -> dict[str, object]:
    return {"url": f"https://www.colegioeverest.cl{path}", "path": path, "title": "", **fields}


READY = {
    "form": "contact",
    "filled": ["nombre", "email", "asunto", "mensaje"],
    "missing": [],
    "invalid": [],
    "values": {"nombre": "Carolina", "email": "caro@gmail.com"},
    "ready": True,
    "by": "javier",
}

# ─── The script ────────────────────────────────────────────────────────────────


def _llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            # English heard: both legs move before he answers.
            "can you tell me how admission works": reply(
                f"{{page: {ADM}}}{{show: pasos}} There are eight steps. Want to hear them?"
            ),
            "¿Cómo es la admisión?": reply(
                f"{{page: {ADM}}}{{show: pasos}} Son ocho pasos. "
                "{show: paso_4_visita} Después visitas el colegio. "
                "{show: paso_inventado} Y luego algo que no existe. ¿Te cuento más?"
            ),
            "¿Tienen inglés?": reply(f"{{page: {ENGLISH}}} Sí, inglés intensivo. Te muestro."),
            # Spanish heard with English chosen: he answers in English.
            "¿Tienen inglés de verdad?": reply(
                f"{{page: {ENGLISH}}} Yes, intensive English. Want to see?"
            ),
            "I am asking you in English now": reply("Claro, te sigo en español. ¿Qué buscas?"),
            "¿Puedes hablar en inglés?": reply_and_call(
                "Sure, let's continue in English.", "set_language", args={"language": "en"}
            ),
            # A place on one other page, and the same place on the page in front.
            "¿Quedan cupos?": [
                reply("{show: vacantes} Aquí están las vacantes publicadas."),
                reply("{show: vacantes} Aquí están las vacantes publicadas."),
            ],
            # A key two pages share: the admission page's.
            "Muéstrame los valores.": reply("{show: valores} Aquí están los valores publicados."),
            # He forgot to show what they asked about: the place goes first.
            "¿Cuánto cuesta el colegio?": reply(
                "Los valores están en UF. La colegiatura anual es 193,34 UF."
            ),
            # A level named outright, with no show cue.
            "¿Y para los más chicos?": reply(
                f"{{page: {ADM}}} Playgroup pide tres años cumplidos. ¿Cuándo nació?"
            ),
            # The child's level.
            "Mi hija nació el 3 de mayo de 2022.": [
                call("find_level", args={"birth_date": "2022-05-03"}),
                reply(
                    f"{{page: {ADM}}}{{show: fecha_prekinder}} Le correspondería Prekínder. "
                    "La postulación ya cerró."
                ),
            ],
            "Mi hijo nació en junio de 2021.": [
                call("find_level", args={"birth_date": "2021-06-15"}),
                reply("Sería Kínder, como estimación."),
            ],
            "Está en Kínder ahora.": [
                call("find_level", args={"current_grade": "Kínder"}),
                reply("Entonces pasaría a primero básico."),
            ],
            "Nació en diciembre de 2025.": [
                call("find_level", args={"birth_date": "2025-12-01"}),
                reply("Todavía es muy chiquito."),
            ],
            "Nació el treinta de febrero.": [
                call("find_level", args={"birth_date": "2022-02-30"}),
                reply("¿Me repites la fecha?"),
            ],
            # The calls to action.
            "Quiero agendar una visita.": reply_and_call(
                "Te abro la agenda de visitas en una pestaña nueva.", "book_visit"
            ),
            "Quiero postular ya.": reply_and_call(
                "Ten a mano el certificado de nacimiento. Te abro la postulación.",
                "open_application",
            ),
            "Ábreme las vacantes en PDF.": reply_and_call(
                "Te abro el documento.",
                "open_link",
                args={"kind": "document", "name": "vacantes 2027"},
            ),
            "¿Y los valores del 2027?": reply_and_call(
                "Te abro los valores.",
                "open_link",
                args={"kind": "document", "name": "valores 2027"},
            ),
            "¿Y el protocolo COVID?": reply_and_call(
                "Te lo busco.", "open_link", args={"kind": "document", "name": "protocolo covid"}
            ),
            "Ábreme Alexia, soy apoderado.": reply_and_call(
                "Te abro Alexia.", "open_link", args={"kind": "portal", "name": "alexia"}
            ),
            # The contact form, field by field.
            "Prefiero que me contacten, me llamo Carolina.": reply_and_call(
                "Perfecto, Carolina. ¿Cuál es tu correo?",
                "fill_contact_form",
                args={"nombre": "Carolina"},
            ),
            "Mi correo es CARO arroba gmail punto com.": reply_and_call(
                "Anoté c, a, r, o, arroba, gmail, punto, com.",
                "fill_contact_form",
                args={"email": "CARO @gmail.com"},
            ),
            "Mi correo es caro gmail.": reply_and_call(
                "Anoté tu correo.", "fill_contact_form", args={"email": "caro gmail"}
            ),
            "Mi celular es más 56 9 1234 5678.": reply_and_call(
                "Lo pongo en el mensaje.",
                "fill_contact_form",
                args={
                    "asunto": "Admisión 2027, Prekínder",
                    "mensaje": "Hola, soy mamá de Sofía. Nos interesa Prekínder 2027. "
                    "Mi celular es +56 9 1234 5678.",
                },
            ),
            "Mi RUT es 12.345.678-5.": reply_and_call(
                "Gracias.", "fill_contact_form", args={"mensaje": "RUT 12.345.678-5"}
            ),
            "Listo, ¿qué falta?": reply_and_call(
                "Ya está todo. Revisa y presiona Enviar.",
                "fill_contact_form",
                args={"asunto": "Admisión 2027"},
            ),
            # The sliders.
            "Muéstrame más fotos.": reply_and_call(
                "Te muestro la galería.",
                "slide",
                args={"slider": "galeria", "direction": "next"},
            ),
            # Talk-throughs, keyed on the page's answer.
            "The contact form is complete": reply(
                "Ya está todo. Presiona Enviar cuando lo revises."
            ),
            "confirmed the message was sent": reply(
                "Gracias, Carolina. El colegio te responde por correo."
            ),
            "security check": reply("Falta la verificación de seguridad."),
            "The site refused the form": reply("Revisa tu correo, por favor."),
            "fill_contact_form not done": reply("No pude completar el formulario."),
            "¿Y entonces?": reply("Te cuento."),
            # Tabs.
            "Vuelve a la otra pestaña.": reply_and_call(
                "Ahí está.", "switch_tab", args={"tab_id": "11"}
            ),
            # A move with no words gets his written line at once.
            "Agéndame la visita.": [call("book_visit")],
            # A reply that only promises more says nothing: asked once more.
            "¿Y los camarines?": [reply("Un momento."), reply("El sitio no lo dice.")],
        }
    )


# ─── Greeting and voice ────────────────────────────────────────────────────────


async def test_greeting_and_voice_reach_the_wire_in_spanish() -> None:
    """A written opener, and javier in Spanish on both legs before it."""
    async with demo("colegioeverest", _llm()) as rig:
        opener = await rig.driver.start_session(init={"surface": "colegioeverest-ext", "path": "/"})
        check_greeting(rig, opener)
        assert opener is not None and opener.text == greeting("/", "es")
        assert opener.text.startswith("Hola, soy Javier, tu guía del Colegio Everest.")
        assert "tu hijo o hija" in opener.text
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _idle_windows(rig) == [_IDLE_MS]
        assert _language_changes(rig) == []


@pytest.mark.parametrize(
    ("path", "words"),
    [
        (ADM, "¿Cuándo nació?"),
        (CONTACT, "escribirle al colegio"),
        (INFRA, "las instalaciones"),
        ("/tour-virtual/", "tour virtual"),
        (ENGLISH, "el inglés"),
        ("/nuestro-modelo-educativo/ciclos/", "los ciclos"),
        ("/hito-religioso-kinder/", "¿Qué edad tiene tu hijo o hija?"),
    ],
)
def test_the_opener_follows_the_page(path: str, words: str) -> None:
    assert words in greeting(path, "es")
    assert greeting(path, "en").startswith("Hi, I'm Javier, your guide to Colegio Everest.")


async def test_a_call_started_in_english_opens_in_english_and_holds() -> None:
    llm = _llm()
    async with demo("colegioeverest", llm) as rig:
        opener = await rig.driver.start_session(init={"path": "/", "lang": "en"})
        check_greeting(rig, opener)
        assert opener is not None and opener.text == greeting("/", "en")
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        turn = await rig.driver.user_says("¿Tienen inglés de verdad?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert "The visitor chose English before the call" in _texts(llm.captured_inputs[-1])


async def test_the_toggle_switches_both_legs_and_confirms_each_way() -> None:
    async with demo("colegioeverest", _llm()) as rig:
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
        await _page(rig, "language_requested", {"language": "es"})
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert turn.text == TOGGLE_CONFIRM["es"]
        # Chosen on the toggle, it holds whatever they speak.
        turn = await rig.driver.user_says("I am asking you in English now, okay?")
        assert "en español" in turn.text
        check_voice_pair(rig, voice="omnivoice/javier", language="es")


async def test_english_heard_switches_before_he_answers_and_spanish_switches_back() -> None:
    async with demo("colegioeverest", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("Hi, can you tell me how admission works?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        turn = await rig.driver.user_says("¿Tienen inglés?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _language_changes(rig) == [{"language": "en"}, {"language": "es"}]


async def test_asking_for_english_switches_and_opens_no_page() -> None:
    async with demo("colegioeverest", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Puedes hablar en inglés?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert _cues(rig) == []


@pytest.mark.parametrize(
    ("text", "sure", "lang"),
    [
        ("¿Puedes hablar en inglés?", True, "es"),
        ("Quiero postular a mi hijo", True, "es"),
        ("Hola", True, None),
        ("Can you show me the admission process?", True, "en"),
        ("Prekínder", True, None),
        ("Claro.", False, "es"),
        ("Sure, here it is.", False, "en"),
        ("{show: fecha_prekinder} That is the Prekínder card, here it is.", False, "en"),
    ],
)
def test_the_language_a_line_is_in(text: str, sure: bool, lang: str | None) -> None:
    assert language_of(text, sure=sure) == lang


# ─── Cues ──────────────────────────────────────────────────────────────────────


async def test_the_admission_tour_cues_are_checked_against_the_catalogue() -> None:
    async with demo("colegioeverest", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Cómo es la admisión?")
        check_turn(rig, turn)
        assert "{" not in turn.text and "Después visitas el colegio." in turn.text
        # The page; its places by key; a key that is nowhere, dropped.
        assert _cues(rig) == [
            {**NONE, "at": "son ocho pasos", "word": 0, "path": ADM},
            {**NONE, "at": "son ocho pasos", "word": 0, "path": ADM, "anchor": "pasos"},
            {**NONE, "at": "despues visitas el", "word": 3, "path": ADM, "anchor": "paso_4_visita"},
        ]


async def test_a_place_on_one_other_page_takes_them_there_and_on_theirs_it_rings_in_place() -> None:
    async with demo("colegioeverest", _llm()) as rig:
        await rig.driver.start_session(init={"path": HOME})
        await rig.driver.user_says("¿Quedan cupos?")
        assert _cues(rig)[0] == {
            **NONE,
            "at": "aqui estan las",
            "word": 0,
            "path": ADM,
            "anchor": "vacantes",
        }
        await _page(rig, "page_changed", _page_changed(ADM, kind="admission", anchors=["vacantes"]))
        await rig.driver.user_says("¿Quedan cupos?")
        assert _cues(rig)[-1] == {**NONE, "at": "aqui estan las", "word": 0, "anchor": "vacantes"}


async def test_a_key_several_pages_share_is_the_admission_pages() -> None:
    async with demo("colegioeverest", _llm()) as rig:
        await rig.driver.start_session(init={"path": HOME})
        await rig.driver.user_says("Muéstrame los valores.")
        assert _cues(rig) == [
            {**NONE, "at": "aqui estan los", "word": 0, "path": ADM, "anchor": "valores"}
        ]


async def test_what_they_asked_about_goes_first_and_uf_is_said_in_words() -> None:
    async with demo("colegioeverest", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Cuánto cuesta el colegio?")
        check_turn(rig, turn)
        # He forgot the cue: the admission page, then the fees' place, go first.
        assert _cues(rig)[0] == {**NONE, "at": "los valores estan", "word": 0, "path": ADM}
        assert _cues(rig)[1] == {
            **NONE,
            "at": "los valores estan",
            "word": 0,
            "path": ADM,
            "anchor": "valores",
        }
        assert "ciento noventa y tres coma treinta y cuatro u efe" in turn.text, turn.text
        assert "193,34" not in turn.text


async def test_a_level_named_outright_rings_its_card() -> None:
    async with demo("colegioeverest", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("¿Y para los más chicos?")
        assert {
            **NONE,
            "at": "playgroup pide tres",
            "word": 0,
            "path": ADM,
            "anchor": "fecha_playgroup",
        } in _cues(rig)


def test_where_what_they_asked_about_is_shown() -> None:
    for ask, target in (
        ("¿Cuánto cuesta?", (ADM, "valores")),
        ("How much is the tuition?", (ADM, "valores")),
        ("¿Quedan vacantes?", (ADM, "vacantes")),
        ("¿Cuándo se postula?", (ADM, "fechas")),
        ("¿Cómo es el Admission Day?", (ADM, "paso_6_admission_day")),
        ("¿Cómo postulo?", (ADM, "pasos")),
        ("¿Dan los exámenes de Cambridge?", (ENGLISH, "certificaciones")),
        ("¿Es bilingüe?", (ENGLISH, "intro")),
        ("¿Tienen gimnasio?", (INFRA, "galeria")),
        ("¿Tienen tour virtual?", ("/tour-virtual/", "tour")),
        ("¿Dónde queda el colegio?", ("", "pie_mapa")),
        ("¿Cuál es la historia del colegio?", (HISTORY, None)),
    ):
        assert asked_target(ask) == target, ask
    for ask in (
        # Moved by their tools, not by a cue.
        "Quiero dejar un mensaje",
        "Me llamo Carolina",
        "Ábreme el PDF de vacantes",
        "Quiero agendar una visita",
        "Vuelve a la otra pestaña.",
        # A request about the call's own language is not a place.
        "Can you speak English?",
        "¿Puedes hablar en inglés?",
        "Mm-hmm",
    ):
        assert asked_target(ask) is None, ask


# ─── The child's level ─────────────────────────────────────────────────────────


def test_a_child_is_placed_by_the_sites_rule() -> None:
    def name(**kw: object) -> str | tuple[str, bool]:
        placed = place_child(SITE, today=TODAY, **kw)  # type: ignore[arg-type]
        return placed if isinstance(placed, str) else (placed.level.name, placed.estimated)

    # Ages the site gives: the cut-off is 31 March 2027.
    assert name(birth_date=date(2022, 5, 3)) == ("Prekínder", False)
    assert name(birth_date=date(2023, 3, 31)) == ("Prekínder", False)
    assert name(birth_date=date(2023, 4, 1)) == ("Playgroup", False)
    # From Kínder up the site gives none: the usual sequence, as an estimate.
    assert name(birth_date=date(2021, 6, 15)) == ("Kínder", True)
    assert name(birth_date=date(2020, 6, 15)) == ("1° básico", True)
    # The grade they are in now: the next one, by the site's order.
    assert name(current_grade="Kínder") == ("1° básico", False)
    assert name(current_grade="Prekinder") == ("Kínder", False)
    assert name(level="Playgroup") == ("Playgroup", False)
    # An age today: about five months more at the cut-off.
    assert name(age_months_today=40) == ("Playgroup", False)
    assert str(name(birth_date=date(2025, 12, 1))).startswith("Too young for 2027")
    assert grade_key("tercero básico") == "3_basico"
    assert grade_key("IV medio") == "iv_medio"
    assert grade_key("I medio") == "i_medio"
    assert grade_key("segundo medio") == "ii_medio"


async def test_find_level_says_the_window_closed_and_gives_vacancies_fees_and_card() -> None:
    llm = _llm()
    async with demo("colegioeverest", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("Mi hija nació el 3 de mayo de 2022.")
        check_turn(rig, turn)
        result = _results(llm.captured_inputs[-1])["find_level"]
        assert result.startswith("Level for 2027: Prekínder (cycle I)")
        assert "CLOSED on 2026-03-10 (today is 2026-10-27)" in result
        assert "Vacancies 2027" in result and "40 (say: cuarenta)" in result
        assert "193,34 UF (say: ciento noventa y tres coma treinta y cuatro UF)" in result
        assert "not linked on the site" in result
        assert "{show: fecha_prekinder}" in result
        assert "The window has closed: say so honestly" in result
        assert "ESTIMATE" not in result
        assert {
            **NONE,
            "at": "le corresponderia prekinder",
            "word": 0,
            "path": ADM,
            "anchor": "fecha_prekinder",
        } in _cues(rig)


async def test_find_level_marks_an_estimate_and_never_invents_an_age_rule() -> None:
    llm = _llm()
    async with demo("colegioeverest", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Mi hijo nació en junio de 2021.")
        result = _results(llm.captured_inputs[-1])["find_level"]
        assert result.startswith("Level for 2027: Kínder")
        assert "ESTIMATE: the site gives no age rule from Kínder up" in result
        assert "age rule: «" not in result
        await rig.driver.user_says("Está en Kínder ahora.")
        result = _results(llm.captured_inputs[-1])["find_level"]
        assert result.startswith("Level for 2027: 1° básico")
        assert "0 (say: cero)" in result and "None: say so" in result
        await rig.driver.user_says("Nació en diciembre de 2025.")
        assert _results(llm.captured_inputs[-1])["find_level"].startswith("Too young for 2027")
        await rig.driver.user_says("Nació el treinta de febrero.")
        assert "is not a date" in _results(llm.captured_inputs[-1])["find_level"]


# ─── The calls to action ───────────────────────────────────────────────────────


async def test_the_visit_and_the_application_open_in_a_new_tab_and_nothing_more() -> None:
    llm = _llm()
    async with demo("colegioeverest", llm) as rig:
        await rig.driver.start_session(init={"path": ADM})
        await rig.driver.user_says("Quiero agendar una visita.")
        await rig.driver.user_says("Quiero postular ya.")
        await rig.driver.user_says("¿Y entonces?")
        assert _commands(rig, "open_link") == [
            {"url": BOOKINGS, "label": "Agenda AQUÍ (Microsoft Bookings)"},
            {"url": ALEXIA_FORM, "label": "Postulación ONLINE (Alexia)"},
        ]
        results = _results(llm.captured_inputs[-1])
        assert "they choose a day and time there themselves" in results["book_visit"]
        assert (
            "the child's RUN and details, which you never ask for or type"
            in results["open_application"]
        )


async def test_documents_and_portals_open_and_a_broken_one_is_refused() -> None:
    llm = _llm()
    async with demo("colegioeverest", llm) as rig:
        await rig.driver.start_session(init={"path": ADM})
        await rig.driver.user_says("Ábreme las vacantes en PDF.")
        await rig.driver.user_says("¿Y los valores del 2027?")
        await rig.driver.user_says("¿Y el protocolo COVID?")
        await rig.driver.user_says("Ábreme Alexia, soy apoderado.")
        await rig.driver.user_says("¿Y entonces?")
        urls = [c["url"] for c in _commands(rig, "open_link")]
        assert urls == [VACANTES, VALORES_2027, "https://colegioeverest.alexiaeducl.com/"]
        results = _all_results(llm.captured_inputs[-1], "open_link")
        assert "The site itself does not link this one" in results[1]
        assert results[2].startswith("Not opened: no document matches 'protocolo covid'")
        assert "they log in there themselves" in results[3]


# ─── The contact form ──────────────────────────────────────────────────────────


async def test_the_contact_form_is_filled_as_they_dictate_only_what_they_said() -> None:
    llm = _llm()
    async with demo("colegioeverest", llm) as rig:
        await rig.driver.start_session(init={"path": CONTACT})
        await _page(rig, "page_changed", _page_changed(CONTACT, kind="contact", form="contact"))
        turn = await rig.driver.user_says("Prefiero que me contacten, me llamo Carolina.")
        check_turn(rig, turn)
        assert _commands(rig, "fill_contact_form") == [
            {"nombre": "Carolina", "email": None, "asunto": None, "mensaje": None}
        ]
        # The page answers the fill: the next one may go.
        await _page(
            rig, "command_done", {"command": "fill_contact_form", "detail": "filled nombre"}
        )
        await rig.driver.user_says("Mi correo es CARO arroba gmail punto com.")
        assert _commands(rig, "fill_contact_form")[-1]["email"] == "caro@gmail.com"
        await _page(rig, "command_done", {"command": "fill_contact_form", "detail": "filled email"})
        await rig.driver.user_says("Mi celular es más 56 9 1234 5678.")
        last = _commands(rig, "fill_contact_form")[-1]
        assert last["asunto"] == "Admisión 2027, Prekínder"
        assert "+56 9 1234 5678" in str(last["mensaje"])
        await rig.driver.user_says("¿Y entonces?")
        result = _results(llm.captured_inputs[-1])["fill_contact_form"]
        assert "Never say it is sent" in result
        # Nothing he can send presses the button.
        assert not [a for a in rig.actions() if "submit" in a or "send" in a]


async def test_an_email_that_is_not_one_and_a_rut_are_refused() -> None:
    llm = _llm()
    async with demo("colegioeverest", llm) as rig:
        await rig.driver.start_session(init={"path": CONTACT})
        await rig.driver.user_says("Mi correo es caro gmail.")
        await rig.driver.user_says("Mi RUT es 12.345.678-5.")
        await rig.driver.user_says("¿Y entonces?")
        assert "fill_contact_form" not in rig.actions()
        results = _all_results(llm.captured_inputs[-1], "fill_contact_form")
        assert results[0].startswith("Not filled: email 'carogmail' is not an address")
        assert results[1].startswith("Not filled: that looks like a RUT")


async def test_a_fill_off_the_contact_page_takes_them_to_it() -> None:
    llm = _llm()
    async with demo("colegioeverest", llm) as rig:
        await rig.driver.start_session(init={"path": ADM})
        await rig.driver.user_says("Prefiero que me contacten, me llamo Carolina.")
        assert _commands(rig, "fill_contact_form")[0]["nombre"] == "Carolina"
        await rig.driver.user_says("¿Y entonces?")
        result = _results(llm.captured_inputs[-1])["fill_contact_form"]
        assert "The contact page is opening" in result and "keep talking" in result


async def test_a_fill_asked_for_while_the_last_runs_waits_and_keeps_both() -> None:
    async with demo("colegioeverest", _llm()) as rig:
        await rig.driver.start_session(init={"path": CONTACT})
        await rig.driver.user_says("Prefiero que me contacten, me llamo Carolina.")
        await rig.driver.user_says("Mi correo es CARO arroba gmail punto com.")
        await rig.driver.user_says("Mi celular es más 56 9 1234 5678.")
        assert len(_commands(rig, "fill_contact_form")) == 1, "a fill raced the last one"
        await _page(
            rig, "command_done", {"command": "fill_contact_form", "detail": "filled nombre"}
        )
        queued = _commands(rig, "fill_contact_form")[1]
        assert queued["email"] == "caro@gmail.com" and "+56 9 1234 5678" in str(queued["mensaje"])


async def test_a_complete_form_is_said_once_in_the_quiet_with_tools_off() -> None:
    llm = _llm()
    seen = llm.requests
    async with demo("colegioeverest", llm) as rig:
        await rig.driver.start_session(init={"path": CONTACT})
        await _page(rig, "form_state", READY)
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        before = len(seen)
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "Presiona Enviar" in turn.text
        context = _texts(llm.captured_inputs[-1])
        assert _SAY_READY in context
        assert "It holds: nombre: Carolina; email: caro@gmail.com" in context
        (talk,) = seen[before:]
        assert talk.get("tool_choice") == "none"
        # The same state again is not said twice.
        await _page(rig, "form_state", READY)
        assert _idle_windows(rig)[-1] == _IDLE_MS


async def test_a_complete_form_he_already_called_ready_is_not_said_again() -> None:
    async with demo("colegioeverest", _llm()) as rig:
        await rig.driver.start_session(init={"path": CONTACT})
        await rig.driver.user_says("Listo, ¿qué falta?")
        await _page(rig, "command_done", {"command": "fill_contact_form", "detail": "filled"})
        await _page(rig, "form_state", READY)
        assert _TALK_THROUGH_MS not in _idle_windows(rig)


async def test_their_press_confirmed_by_the_site_is_thanked() -> None:
    llm = _llm()
    async with demo("colegioeverest", llm) as rig:
        await rig.driver.start_session(init={"path": CONTACT})
        await _page(rig, "form_state", READY)
        await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        await _page(
            rig,
            "form_result",
            {
                "form": "contact",
                "outcome": "sent",
                "message": "Gracias por tu mensaje.",
                "fields": [],
            },
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "te responde por correo" in turn.text
        context = _texts(llm.captured_inputs[-1])
        assert (
            "[The site confirmed the contact form was sent (Gracias por tu mensaje.).]" in context
        )


async def test_the_security_check_and_a_refusal_are_talked_through_and_never_called_sent() -> None:
    llm = _llm()
    async with demo("colegioeverest", llm) as rig:
        await rig.driver.start_session(init={"path": CONTACT})
        await _page(
            rig, "form_result", {"form": "contact", "outcome": "spam", "message": "", "fields": []}
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "verificación de seguridad" in turn.text
        await _page(
            rig,
            "form_result",
            {
                "form": "contact",
                "outcome": "invalid",
                "message": "Hay un error.",
                "fields": ["email"],
            },
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        context = _texts(llm.captured_inputs[-1])
        assert (
            "The site refused the form when they pressed «Enviar»: Hay un error. (fields: email)"
            in context
        )
        assert "Never say it was sent." in context


async def test_a_fill_the_page_could_not_make_is_said() -> None:
    async with demo("colegioeverest", _llm()) as rig:
        await rig.driver.start_session(init={"path": CONTACT})
        await rig.driver.user_says("Prefiero que me contacten, me llamo Carolina.")
        await _page(rig, "command_failed", {"command": "fill_contact_form", "reason": "no form"})
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "No pude completar" in turn.text


async def test_a_slide_off_its_page_opens_that_page_first() -> None:
    llm = _llm()
    async with demo("colegioeverest", llm) as rig:
        await rig.driver.start_session(init={"path": HOME})
        await rig.driver.user_says("Muéstrame más fotos.")
        assert _commands(rig, "slide") == [{"slider": "galeria", "direction": "next"}]
        await rig.driver.user_says("¿Y entonces?")
        assert f"Its page ({INFRA}) is opening first" in _results(llm.captured_inputs[-1])["slide"]


# ─── What he never says or does ────────────────────────────────────────────────


def test_the_prompt_carries_what_the_site_does_not_say_and_the_right_address() -> None:
    prompt = ce._prompt(SITE, TODAY)
    for rule in (
        "The knowledge below opens with what the site does NOT say",
        "Today every published 2027 application window has closed",
        "estos datos se van modificando",
        "never as the site's rule",
        "never converted to pesos",
        ADMISSIONS_EMAIL,
        "a mistake of the site. Never repeat that one",
        "YOU NEVER PRESS IT",
        "Never ask for, repeat or type a RUT or RUN, a password or a card",
        "Never fill the complaints form",
        "Never wait for a page and never stop talking because one is loading",
    ):
        assert rule in prompt, rule
    assert "josefina" not in prompt.lower()


def test_no_action_can_send_a_form() -> None:
    from voqalize.sdk import Action

    actions = [
        v
        for v in vars(ce).values()
        if isinstance(v, type) and issubclass(v, Action) and v is not Action
    ]
    names = {a.__voqal_action__ for a in actions}  # type: ignore[attr-defined]
    assert names == {
        "navigate",
        "cue",
        "show_section",
        "open_link",
        "slide",
        "fill_contact_form",
        "focus_tab",
        "language_changed",
    }
    for a in actions:
        assert not [f for f in a.model_fields if re.search(r"submit|send|captcha|rut|run\b", f)], a


def test_the_brain_never_fetches_the_site() -> None:
    """The brain runs far from Chile, where the site does not answer. No module
    of the brain opens a connection of its own."""
    backend = Path(ce.__file__).parent
    for source in backend.glob("*.py"):
        text = source.read_text(encoding="utf-8")
        imports = r"^\s*(?:import|from)\s+(?:httpx|aiohttp|requests|socket|http\.client|urllib\.request)\b"
        assert not re.search(imports, text, re.MULTILINE), source


def test_the_committed_knowledge_loads_and_every_offered_key_is_in_the_catalogue() -> None:
    real = kb.load()
    if not real.pages:
        pytest.skip("no crawl committed yet")
    assert {HOME, ADM, CONTACT, ENGLISH, INFRA, "/tour-virtual/"} <= set(real.pages)
    assert len(real.levels) == 17 and real.cutoff == date(2027, 3, 31)
    assert {"2026", "2027"} <= set(real.fees)
    assert {"postulacion", "visita"} <= set(real.exits)
    # Every level's card is a place on the admission page.
    adm = {a.key for a in real.anchors_on(ADM)}
    assert all(lv.place in adm for lv in real.levels), [lv.place for lv in real.levels]
    # Every key the prompt offers is a place the extension can find.
    catalogue = json.loads(
        (Path(kb.__file__).parent / "knowledge" / "L3" / "anchors.json").read_text(encoding="utf-8")
    )
    keys = {a["key"] for page in catalogue["pages"].values() for a in page["anchors"]}
    keys |= {a["key"] for part in ("header", "footer", "post") for a in catalogue[part]}
    prompt = ce._prompt(real, TODAY)
    places = prompt.split("# Places on the site")[1]
    for key in re.findall(r"^\s+- ([a-z0-9_]+):", places, re.MULTILINE):
        assert key in keys, key
    for listed in re.findall(r"\(places: ([^)]*)\)", places):
        for key in listed.split(", "):
            assert key in keys, key
    # The documents the prompt names are ones open_link finds.
    brain = ce.ColegioEverestBrain(client=None, knowledge=real, today=TODAY)  # type: ignore[arg-type]
    for name in (
        "vacantes 2027",
        "valores 2027",
        "valores 2026",
        "proyecto educativo",
        "RICE 2027",
    ):
        assert brain.document(name) is not None, name
    # The real levels, by the real rule.
    placed = place_child(real, birth_date=date(2022, 5, 3), today=TODAY)
    assert not isinstance(placed, str) and placed.level.key == "prekinder"


# ─── Tabs and silent turns ─────────────────────────────────────────────────────


async def test_tabs_are_read_in_and_switching_is_checked() -> None:
    llm = _llm()
    async with demo("colegioeverest", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(
            rig,
            "tabs_changed",
            {
                "tabs": [
                    {"tab_id": "11", "url": "https://www.colegioeverest.cl/", "title": "Inicio"},
                    {
                        "tab_id": "12",
                        "url": f"https://www.colegioeverest.cl{ADM}",
                        "title": "Admisión",
                    },
                ],
                "active": "12",
            },
        )
        await rig.driver.user_says("Vuelve a la otra pestaña.")
        assert "11: Inicio; 12: Admisión (in front)" in _texts(llm.captured_inputs[-1])
        assert rig.command("focus_tab") == {"tab_id": "11"}
        assert _cues(rig) == []


async def test_a_silent_move_gets_his_written_line() -> None:
    async with demo("colegioeverest", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("Agéndame la visita.")
        check_turn(rig, turn)
        assert turn.text.strip() == _LANDED["visit"]["es"]


async def test_a_reply_that_only_promises_is_asked_once_more() -> None:
    async with demo("colegioeverest", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Y los camarines?")
        check_turn(rig, turn)
        assert "El sitio no lo dice" in turn.text


async def test_a_missed_cue_is_noted_quietly() -> None:
    llm = _llm()
    async with demo("colegioeverest", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(rig, "command_failed", {"command": "cue", "reason": "no place X"})
        await rig.driver.user_says("¿Y entonces?")
        seen = _texts(llm.captured_inputs[-1])
        assert "A screen cue of yours did not land (no place X)" in seen
        assert "Tell the visitor plainly" not in seen


def test_his_lines_for_a_move_exist_in_both_languages() -> None:
    for kind, lines in _LANDED.items():
        assert set(lines) == {"en", "es"}, kind
        assert all(line.strip() for line in lines.values()), kind
    assert set(TOGGLE_CONFIRM) == {"en", "es"}


def test_the_floor_is_held_as_the_clini_guide_learned() -> None:
    assert ce.ACK_HOLD_AFTER_S >= 5.5 and ce.ACK_SORRY_AFTER_S >= 15
    assert ce.HOLD_WITHOUT_NOD_S <= 3.0
