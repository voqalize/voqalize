"""Javier, Figurella's guide, end to end over the wire — no network, no LLM key.

The real ``FigurellaBrain`` on a real ``brain_server`` socket, driven by the
conformance ``VoqalizeDriver``, with only the model scripted. The knowledge is a
small invented Figurella in the crawl's own shape, put in place of the
committed one, so no test depends on what the crawl found this week.

What this demo earns that others do not:

**The screen follows his voice, on the site's own places.** Every cue is
checked against the catalogue of places (``anchors.json``): a key that is not
there is dropped, a place on another page takes the visitor there, an FAQ
question opens on the FAQ page, and what she asked about is shown when his
reply forgets to.

**She presses the button.** He fills the booking form as she dictates it — only
what she said, a phone exactly as she said it, never a RUT — and the page tells
him when it is complete and when the site answered her press; he says so in the
next quiet spell, with tools off. No Action can submit.

**Nothing is invented.** No price, no plan length, no session count: the prompt
says so and the knowledge has none.

**Spanish first, and "tú".** The site is Chilean, so the call opens in Spanish,
follows a visitor who speaks English, and holds a language she chose.

Run: ``cd demos && uv run pytest tests/test_figurella_e2e.py``
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from google.genai import types
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply, reply_and_call

from ._harness import _configs, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.figurella import brain as fg  # noqa: E402
from voqalize_demos._loaded.figurella import knowledge as kb  # noqa: E402
from voqalize_demos._loaded.figurella.brain import (  # noqa: E402
    _IDLE_MS,
    _LANDED,
    _SAY_READY,
    _TALK_THROUGH_MS,
    TOGGLE_CONFIRM,
    asked_target,
    greeting,
    language_of,
    said_digits,
)
from voqalize_demos._loaded.figurella.comunas import nearest  # noqa: E402
from voqalize_demos._loaded.figurella.knowledge import (  # noqa: E402
    Anchor,
    Branch,
    Convenio,
    Faq,
    Knowledge,
    Page,
    Section,
)

# ─── An invented Figurella ─────────────────────────────────────────────────────

HOME = "/"
METHOD = "/metodo-figurella/"
PLANS = "/planes/"
FAQ = "/preguntas-frecuentes/"
FRANCHISE = "/franquicias/"
MAP = "https://goo.gl/maps/59M2H8SUbz1CEhU76"

FOOTER = (Anchor("contacto", "El formulario de reserva"), Anchor("form", "form", hidden=True))

# Invented, in the crawl's shape: the names are the site's kind, the facts ours.
SITE = Knowledge(
    l1="Figurella is a body-shaping centre in Santiago (invented for tests).",
    topics={},
    pages={
        HOME: Page(
            HOME,
            "Figurella - Centro de Modelamiento Corporal",
            kind="home",
            sections=(
                Section("intro", "Sé quien quieras ser: 15 años en Chile", "Método italiano."),
                Section("plan_novias", "Plan Novias (resumen)", "Para tu matrimonio."),
                Section("sucursales", "Las siete sucursales", "Vitacura Costanera"),
                Section("sucursal_vitacura", "Sucursal Vitacura (tarjeta)", "Juan XXIII 6370"),
                Section("sucursal_costanera", "Sucursal Costanera (tarjeta)", "Nueva Tajamar 289"),
            ),
        ),
        METHOD: Page(
            METHOD,
            "Método Figurella - Figurella",
            kind="method",
            sections=(
                Section("paso_1", "Paso uno: movimientos localizados en cápsula térmica", ""),
                Section("paso_2", "Paso dos: oxigenoterapia", "baño de oxígeno"),
                Section("paso_3", "Paso tres: presoterapia", "drenaje linfático"),
            ),
        ),
        PLANS: Page(
            PLANS,
            "Planes - Figurella",
            kind="plans",
            sections=(
                Section("plan_novias", "Plan Novias", "Rediseña tu silueta."),
                Section("plan_intensivo", "Plan Intensivo", "Adelgaza."),
            ),
        ),
        FAQ: Page(
            FAQ,
            "Preguntas frecuentes - Figurella",
            kind="faq",
            faqs=(
                Faq("¿Cuánto cuesta Figurella?", "faq_precio", "No contamos con un precio fijo."),
                Faq("¿Cómo puedo obtener un abdomen plano?", "faq_abdomen", "Cápsula."),
            ),
        ),
        FRANCHISE: Page(FRANCHISE, "Franquicias - Figurella", kind="franchise"),
    },
    anchors={
        HOME: (
            Anchor("intro", "Sé quien quieras ser"),
            Anchor("plan_novias", "Plan Novias (resumen)"),
            Anchor("sucursales", "Las siete sucursales"),
            Anchor("sucursal_vitacura", "Sucursal Vitacura (tarjeta)"),
            Anchor("sucursal_costanera", "Sucursal Costanera (tarjeta)"),
            Anchor("sucursal_vitacura_pedir_hora", "Pedir hora", hidden=True),
            *FOOTER,
        ),
        METHOD: (
            Anchor("paso_1", "Paso uno: movimientos localizados"),
            Anchor("paso_2", "Paso dos: oxigenoterapia"),
            Anchor("paso_3", "Paso tres: presoterapia"),
            *FOOTER,
        ),
        PLANS: (
            Anchor("plan_novias", "Plan Novias"),
            Anchor("plan_intensivo", "Plan Intensivo"),
            *FOOTER,
        ),
        FAQ: (Anchor("hero", "Preguntas frecuentes"), *FOOTER),
        FRANCHISE: (Anchor("beneficios", "Beneficios"), Anchor("socios", "Formulario")),
        "/convenios/": (Anchor("convenio_banmedica", "Convenio Isapre Banmédica"), *FOOTER),
    },
    branches=(
        Branch(
            "vitacura",
            "Vitacura",
            "Juan XXIII 6370, Vitacura.",
            "+56 9 6310 1871",
            ("Lunes a viernes de 8:00 a 21:30 h.",),
            MAP,
            "vitacura@figurella.cl",
            "sucursal_vitacura",
        ),
        Branch(
            "costanera",
            "Costanera",
            "Nueva Tajamar 289, Las Condes.",
            "+56 9 8529 8379",
            ("Lunes a viernes de 8:00 a 21:30 h.",),
            "https://goo.gl/maps/wpndktmeYhFG67Bf8",
            "costanera@figurella.cl",
            "sucursal_costanera",
        ),
        Branch(
            "las_perdices",
            "Las Perdices",
            "Av. Las Perdices 2990, local 17, Peñalolén.",
            "+56 9 4190 2523",
            (),
            "",
            "lasperdices@figurella.cl",
            "sucursal_las_perdices",
            whatsapp="+56987794441",
        ),
        Branch(
            "montemar",
            "Montemar",
            "Las Pelargonias 842, local 101, Concón",
            "",
            (),
            "",
            "",
            "",
            "+56998991355",
        ),
    ),
    convenios=(
        Convenio("banmedica", "Isapre Banmédica", "convenio_banmedica", "30% de Descuento", ""),
    ),
)


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every session reads the invented Figurella, and he never nods unless a
    test asks him to: a nod is a unit of its own."""
    monkeypatch.setattr(kb, "KNOWLEDGE", SITE)
    monkeypatch.setattr(fg, "ACK_RATE", 0.0)
    yield


# ─── Reading the wire ──────────────────────────────────────────────────────────


def _results(contents: list[types.Content]) -> dict[str, str]:
    return {
        p.function_response.name or "": str((p.function_response.response or {})["result"])
        for c in contents
        for p in (c.parts or [])
        if p.function_response is not None
    }


def _all_results(contents: list[types.Content], name: str) -> list[str]:
    return [
        str((p.function_response.response or {})["result"])
        for c in contents
        for p in (c.parts or [])
        if p.function_response is not None and p.function_response.name == name
    ]


def _texts(contents: list[types.Content]) -> str:
    return "\n".join(p.text or "" for c in contents for p in (c.parts or []))


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


NONE = {"path": None, "anchor": None, "text": None, "faq": None}


def _page_changed(path: str, **fields: object) -> dict[str, object]:
    return {"url": f"https://figurella.cl{path}", "path": path, "title": "", **fields}


READY = {
    "form": "booking",
    "filled": ["nombre", "telefono", "email", "comuna", "sucursal", "mensaje"],
    "missing": [],
    "invalid": [],
    "values": {"nombre": "Ana", "sucursal": "Vitacura"},
    "consent": True,
    "ready": True,
    "by": "javier",
}

# ─── The script ────────────────────────────────────────────────────────────────


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            # English heard: both legs move before he answers.
            "can you tell me how it works": reply(
                "{page: /metodo-figurella/}{show: paso_1} Each session has three steps. Want to hear them?"
            ),
            "¿Cómo funciona?": reply(
                "{page: /metodo-figurella/}{show: paso_1} Cada sesión tiene tres pasos. "
                "{show: paso_2} Después viene la oxigenoterapia. "
                "{show: paso_inventado} Y luego algo que no existe. ¿Te cuento más?"
            ),
            "¿Qué planes tienen?": reply("{page: /planes/} Hay cinco planes. Te muestro uno."),
            # Spanish heard with English chosen: he answers in English.
            "¿Cuántos planes hay?": reply(
                "{page: /planes/} There are five plans. Want to see one?"
            ),
            "I am asking you in English now": reply("Claro, te sigo en español. ¿Qué buscas?"),
            "¿Puedes hablar en inglés?": reply_and_call(
                "Sure, let's continue in English.", "set_language", request={"language": "en"}
            ),
            # A place on another page, and the same place on the page in front.
            "Me caso en marzo.": [
                reply("{show: plan_novias} Tenemos un plan para novias."),
                reply("{show: plan_novias} Tenemos un plan para novias."),
            ],
            # He forgot to show what she asked about: the question goes first.
            "¿Cuánto cuesta?": reply("No hay un precio fijo. Se define en la evaluación gratis."),
            "¿Y la pregunta del precio?": reply("{faq: cuanto cuesta} Aquí está la respuesta."),
            # A partner named outright, in English, with no show cue.
            "Do you have an agreement with Banmédica?": reply(
                "{page: /convenios/} Yes, thirty percent off for Banmédica members. "
                "Shall I book your free evaluation?"
            ),
            # Branches.
            "Vivo en Ñuñoa.": [
                call("find_branch", request={"comuna": "Ñuñoa"}),
                reply("{page: /}{show: sucursal_costanera} La más cercana es Costanera."),
            ],
            "Vivo en Viña del Mar.": [
                call("find_branch", request={"comuna": "Viña del Mar"}),
                reply("Las sucursales están en Santiago."),
            ],
            "¿Cómo llego a Vitacura?": reply_and_call(
                "Te abrí el mapa.", "open_map", request={"branch": "vitacura"}
            ),
            "¿Y a Saturno?": reply_and_call(
                "No tengo ese mapa.", "open_map", request={"branch": "Saturno"}
            ),
            # The booking form, field by field.
            "Quiero reservar, me llamo Ana.": reply_and_call(
                "Perfecto, Ana. ¿Cuál es tu teléfono?",
                "fill_booking_form",
                request={"nombre": "Ana"},
            ),
            "Mi teléfono es nueve ocho siete seis cinco cuatro tres dos uno.": reply_and_call(
                "Anoté nueve, ocho, siete, seis, cinco, cuatro, tres, dos, uno. ¿Está bien?",
                "fill_booking_form",
                request={"telefono": "+56 9 8765 4321"},
            ),
            "Mi número es 912345678.": reply_and_call(
                "Anoté tu número.", "fill_booking_form", request={"telefono": "912345678"}
            ),
            "Mi número es 9 1234 5678, cámbialo.": reply_and_call(
                "Anoté tu número.", "fill_booking_form", request={"telefono": "912345679"}
            ),
            "Mi correo es ANA arroba gmail punto com.": reply_and_call(
                "Anoté a, n, a, arroba, gmail, punto, com.",
                "fill_booking_form",
                request={"email": "ANA @gmail.com"},
            ),
            "Mi RUT es 12.345.678-5.": reply_and_call(
                "Gracias.", "fill_booking_form", request={"comuna": "12.345.678-5"}
            ),
            "Quiero Montemar.": reply_and_call(
                "Te cuento.", "fill_booking_form", request={"sucursal": "Montemar"}
            ),
            "En Vitacura, y quiero el plan novias.": reply_and_call(
                "Listo.",
                "fill_booking_form",
                request={
                    "comuna": "Vitacura",
                    "sucursal": "vitacura",
                    "mensaje": "Me caso en marzo. Me interesa el Plan Novias.",
                },
            ),
            "Márcala, y quiero bajar de peso.": reply_and_call(
                "Listo. Revisa los datos y presiona Reservar mi diagnóstico.",
                "fill_booking_form",
                request={"sucursal": "Vitacura", "mensaje": "Quiero bajar de peso."},
            ),
            "Me llamo Carla, quiero una franquicia.": reply_and_call(
                "Te ayudo.", "fill_franchise_form", request={"nombre": "Carla"}
            ),
            # Talk-throughs, keyed on the page's answer.
            "The form is complete": reply(
                "Ya está todo. Presiona Reservar mi diagnóstico cuando lo revises."
            ),
            "the site confirmed it was sent": reply("Felicitaciones, Ana. Te van a contactar."),
            "The site refused the form": reply("Revisa tu teléfono, por favor."),
            "fill_booking_form not done": reply("No pude completar el formulario."),
            "¿Y entonces?": reply("Te cuento."),
            # Tabs.
            "Vuelve a la otra pestaña.": reply_and_call(
                "Ahí está.", "switch_tab", request={"tab_id": "11"}
            ),
            # A move with no words gets his written line at once.
            "Ábreme el mapa de Vitacura.": [call("open_map", request={"branch": "Vitacura"})],
            # A reply that only promises more says nothing: asked once more.
            "¿Y los camarines?": [reply("Un momento."), reply("Los camarines son cómodos.")],
        }
    )


# ─── Greeting and voice ────────────────────────────────────────────────────────


async def test_greeting_and_voice_reach_the_wire_in_spanish() -> None:
    """A written opener, and javier in Spanish on both legs before it."""
    async with demo("figurella", _llm()) as rig:
        opener = await rig.driver.start_session(init={"surface": "figurella-ext", "path": "/"})
        check_greeting(rig, opener)
        assert opener is not None and opener.text == greeting("/", "es")
        assert opener.text.startswith("Hola, soy Javier, tu guía de Figurella.")
        assert "diagnóstico corporal gratis" in opener.text
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _idle_windows(rig) == [_IDLE_MS]
        assert _language_changes(rig) == []


@pytest.mark.parametrize(
    ("path", "words"),
    [
        ("/planes/", "el plan que te calza"),
        ("/metodo-figurella/", "paso a paso"),
        ("/convenios/", "banco, isapre o colegio"),
        ("/historias-de-exito/", "historias de mujeres"),
        ("/preguntas-frecuentes/", "tus dudas"),
        ("/franquicias/", "abrir un Figurella"),
        ("/capsula-termica-y-sus-beneficios/", "¿Qué te gustaría lograr?"),
    ],
)
def test_the_opener_follows_the_page(path: str, words: str) -> None:
    assert words in greeting(path, "es")
    assert greeting(path, "en").startswith("Hi, I'm Javier, your guide to Figurella.")


async def test_a_call_started_in_english_opens_in_english_and_holds() -> None:
    llm = _llm()
    async with demo("figurella", llm) as rig:
        opener = await rig.driver.start_session(init={"path": "/", "lang": "en"})
        check_greeting(rig, opener)
        assert opener is not None and opener.text == greeting("/", "en")
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        turn = await rig.driver.user_says("¿Cuántos planes hay?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert "The visitor chose English before the call" in _texts(llm.captured_contents[-1])


async def test_the_toggle_switches_both_legs_and_confirms_each_way() -> None:
    async with demo("figurella", _llm()) as rig:
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
        # Chosen on the toggle, it holds whatever she speaks.
        turn = await rig.driver.user_says("I am asking you in English now, okay?")
        assert "en español" in turn.text
        check_voice_pair(rig, voice="omnivoice/javier", language="es")


async def test_english_heard_switches_before_he_answers_and_spanish_switches_back() -> None:
    async with demo("figurella", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("Hi, can you tell me how it works?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        turn = await rig.driver.user_says("¿Qué planes tienen?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _language_changes(rig) == [{"language": "en"}, {"language": "es"}]


async def test_asking_for_english_switches_and_opens_no_page() -> None:
    async with demo("figurella", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Puedes hablar en inglés?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert _cues(rig) == []


@pytest.mark.parametrize(
    ("text", "sure", "lang"),
    [
        ("¿Puedes hablar en inglés?", True, "es"),
        ("Quiero bajar de peso", True, "es"),
        ("Hola", True, None),
        ("Can you show me the plans?", True, "en"),
        ("Novias", True, None),
        ("Claro.", False, "es"),
        ("Sure, here it is.", False, "en"),
        ("{show: plan_novias} That is the bridal plan, here it is.", False, "en"),
    ],
)
def test_the_language_a_line_is_in(text: str, sure: bool, lang: str | None) -> None:
    assert language_of(text, sure=sure) == lang


# ─── Cues ──────────────────────────────────────────────────────────────────────


async def test_the_method_tour_cues_are_checked_against_the_catalogue() -> None:
    async with demo("figurella", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Cómo funciona?")
        check_turn(rig, turn)
        assert "{" not in turn.text and "Después viene la oxigenoterapia." in turn.text
        # The page; its places by key; a key that is nowhere, dropped.
        assert _cues(rig) == [
            {**NONE, "at": "cada sesion tiene", "word": 0, "path": METHOD},
            {**NONE, "at": "cada sesion tiene", "word": 0, "path": METHOD, "anchor": "paso_1"},
            {**NONE, "at": "despues viene la", "word": 5, "path": METHOD, "anchor": "paso_2"},
        ]


async def test_a_place_on_another_page_takes_her_there_and_on_hers_it_rings_in_place() -> None:
    async with demo("figurella", _llm()) as rig:
        await rig.driver.start_session(init={"path": METHOD})
        await rig.driver.user_says("Me caso en marzo.")
        assert _cues(rig) == [
            {**NONE, "at": "tenemos un plan", "word": 0, "path": PLANS, "anchor": "plan_novias"},
        ]
        # On the home page its summary of the plan is in front: rung there.
        await _page(rig, "page_changed", _page_changed(HOME, kind="home", anchors=["plan_novias"]))
        await rig.driver.user_says("Me caso en marzo.")
        assert _cues(rig)[1] == {
            **NONE,
            "at": "tenemos un plan",
            "word": 0,
            "anchor": "plan_novias",
        }


async def test_a_question_opens_on_the_faq_page_by_its_key_or_its_words() -> None:
    async with demo("figurella", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Cuánto cuesta?")
        check_turn(rig, turn)
        # He forgot the cue: the question she asked about goes first.
        assert _cues(rig) == [
            {**NONE, "at": "no hay un", "word": 0, "path": FAQ, "faq": "faq_precio"},
        ]
        await _page(rig, "page_changed", _page_changed(FAQ, kind="faq", faqs=["faq_precio"]))
        await rig.driver.user_says("¿Y la pregunta del precio?")
        assert _cues(rig)[1] == {**NONE, "at": "aqui esta la", "word": 0, "faq": "faq_precio"}


async def test_a_partner_named_outright_rings_its_card() -> None:
    async with demo("figurella", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/", "lang": "en"})
        await rig.driver.user_says("Do you have an agreement with Banmédica?")
        assert _cues(rig) == [
            {**NONE, "at": "yes thirty percent", "word": 0, "path": "/convenios/"},
            {
                **NONE,
                "at": "yes thirty percent",
                "word": 0,
                "path": "/convenios/",
                "anchor": "convenio_banmedica",
            },
        ]


def test_where_what_she_asked_about_is_shown() -> None:
    for ask, target in (
        ("¿Cuánto cuesta?", (FAQ, None, "faq_precio")),
        ("How much does it cost?", (FAQ, None, "faq_precio")),
        ("Me caso en marzo", (PLANS, "plan_novias", None)),
        ("Tuve una guagua hace poco", (PLANS, "plan_mama_reciente", None)),
        ("Tengo celulitis", (PLANS, "plan_curvas_perfectas", None)),
        ("¿Y para mis muslos?", (FAQ, None, "faq_muslos_gluteos")),
        ("¿Qué es la presoterapia?", (METHOD, "paso_3", None)),
        ("¿Cómo funciona una sesión?", (METHOD, None, None)),
        ("¿Tienen convenio con mi isapre?", ("/convenios/", None, None)),
        ("¿Dónde están?", (HOME, "sucursales", None)),
        ("¿La garantía es por escrito?", (HOME, "garantia", None)),
        ("Quiero abrir una franquicia", (FRANCHISE, None, None)),
    ):
        assert asked_target(ask) == target, ask
    for ask in (
        # Moved by their tools, not by a cue.
        "Quiero reservar mi evaluación",
        "Me llamo Ana",
        "¿Cómo llego a Vitacura?",
        "Vuelve a la otra pestaña.",
        # A request about the call's own language is not a place.
        "Can you speak English?",
        "¿Puedes hablar en inglés?",
        "Mm-hmm",
    ):
        assert asked_target(ask) is None, ask


# ─── Branches ──────────────────────────────────────────────────────────────────


def test_the_nearest_branch_by_comuna() -> None:
    assert nearest("Ñuñoa") == ("costanera", "las_perdices")
    assert nearest("Las Condes, cerca del Parque Arauco") == ("colon", "costanera")
    assert nearest("La Florida")[0] == "las_perdices"  # type: ignore[index]
    assert nearest("Colina") == ("chicureo",)
    assert nearest("Lo Barnechea")[0] == "tabancura"  # type: ignore[index]
    assert nearest("Viña del Mar") == ("montemar",)
    assert nearest("Marte") is None


async def test_find_branch_names_the_nearest_with_its_card_and_he_shows_it() -> None:
    llm = _llm()
    async with demo("figurella", llm) as rig:
        await rig.driver.start_session(init={"path": METHOD})
        await rig.driver.user_says("Vivo en Ñuñoa.")
        result = _results(llm.captured_contents[-1])["find_branch"]
        assert result.startswith(
            "Nearest to Ñuñoa, by address: Costanera (place sucursal_costanera)"
        )
        assert "Las Perdices" in result and "WhatsApp +56987794441" in result
        assert "she chooses" in result
        assert _cues(rig)[-1] == {
            **NONE,
            "at": "la mas cercana",
            "word": 0,
            "path": HOME,
            "anchor": "sucursal_costanera",
        }
        await rig.driver.user_says("Vivo en Viña del Mar.")
        result = _results(llm.captured_contents[-1])["find_branch"]
        assert "Montemar" in result and "not in the booking form" in result


async def test_a_branchs_map_opens_in_a_new_tab_and_an_unknown_one_is_refused() -> None:
    llm = _llm()
    async with demo("figurella", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("¿Cómo llego a Vitacura?")
        await rig.driver.user_says("¿Y a Saturno?")
        assert _commands(rig, "open_link") == [{"url": MAP, "label": "Cómo llegar a Vitacura"}]
        await rig.driver.user_says("¿Y entonces?")
        assert _results(llm.captured_contents[-1])["open_map"].startswith("Not opened: no map for")


# ─── The booking form ──────────────────────────────────────────────────────────


async def test_the_form_is_filled_as_she_dictates_only_what_she_said() -> None:
    llm = _llm()
    async with demo("figurella", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(rig, "page_changed", _page_changed(HOME, kind="home", form="booking"))
        turn = await rig.driver.user_says("Quiero reservar, me llamo Ana.")
        check_turn(rig, turn)
        assert _commands(rig, "fill_booking_form") == [
            {
                "nombre": "Ana",
                "telefono": None,
                "email": None,
                "comuna": None,
                "sucursal": None,
                "mensaje": None,
            }
        ]
        # The page answers the fill: the next one may go.
        await _page(
            rig, "command_done", {"command": "fill_booking_form", "detail": "filled nombre"}
        )
        await rig.driver.user_says(
            "Mi teléfono es nueve ocho siete seis cinco cuatro tres dos uno."
        )
        # Her digits, the +56 she did not say kept as the model wrote it, no spaces.
        assert _commands(rig, "fill_booking_form")[-1]["telefono"] == "+56987654321"
        await _page(
            rig, "command_done", {"command": "fill_booking_form", "detail": "filled telefono"}
        )
        await rig.driver.user_says("Mi correo es ANA arroba gmail punto com.")
        assert _commands(rig, "fill_booking_form")[-1]["email"] == "ana@gmail.com"
        await _page(rig, "command_done", {"command": "fill_booking_form", "detail": "filled email"})
        await rig.driver.user_says("En Vitacura, y quiero el plan novias.")
        last = _commands(rig, "fill_booking_form")[-1]
        assert last["sucursal"] == "Vitacura" and last["comuna"] == "Vitacura"
        assert str(last["mensaje"]).startswith("Me caso en marzo.")
        await rig.driver.user_says("¿Y entonces?")
        result = _results(llm.captured_contents[-1])["fill_booking_form"]
        assert "Never say it is sent" in result
        # Nothing he can send presses the button.
        assert not [a for a in rig.actions() if "submit" in a or "send" in a]


async def test_a_phone_that_is_not_what_she_said_is_refused() -> None:
    llm = _llm()
    async with demo("figurella", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Mi número es 9 1234 5678, cámbialo.")
        assert "fill_booking_form" not in rig.actions()
        await rig.driver.user_says("¿Y entonces?")
        result = _results(llm.captured_contents[-1])["fill_booking_form"]
        assert result.startswith("Not filled: telefono 9 1 2 3 4 5 6 7 9 is not what she said")
        assert "(she said 9 1 2 3 4 5 6 7 8)" in result
    assert said_digits("nueve ocho 7 seis") == "9876"


async def test_never_a_rut_and_never_a_branch_the_form_does_not_have() -> None:
    llm = _llm()
    async with demo("figurella", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Mi RUT es 12.345.678-5.")
        await rig.driver.user_says("Quiero Montemar.")
        await rig.driver.user_says("¿Y entonces?")
        assert "fill_booking_form" not in rig.actions()
        results = _all_results(llm.captured_contents[-1], "fill_booking_form")
        assert results[0].startswith("Not filled: that looks like a RUT")
        assert "Montemar is only in the WhatsApp button" in results[1]


async def test_a_fill_off_the_form_takes_her_to_it() -> None:
    llm = _llm()
    async with demo("figurella", llm) as rig:
        await rig.driver.start_session(init={"path": FRANCHISE})
        await _page(
            rig, "page_changed", _page_changed(FRANCHISE, kind="franchise", form="franchise")
        )
        await rig.driver.user_says("Quiero reservar, me llamo Ana.")
        assert _commands(rig, "fill_booking_form")[0]["nombre"] == "Ana"
        await rig.driver.user_says("¿Y entonces?")
        result = _results(llm.captured_contents[-1])["fill_booking_form"]
        assert "the home page is opening with it" in result


async def test_a_fill_asked_for_while_the_last_runs_waits_and_keeps_both() -> None:
    async with demo("figurella", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Quiero reservar, me llamo Ana.")
        await rig.driver.user_says("Mi número es 912345678.")
        await rig.driver.user_says("Mi correo es ANA arroba gmail punto com.")
        assert len(_commands(rig, "fill_booking_form")) == 1, "a fill raced the last one"
        await _page(
            rig, "command_done", {"command": "fill_booking_form", "detail": "filled nombre"}
        )
        queued = _commands(rig, "fill_booking_form")[1]
        assert queued["telefono"] == "912345678" and queued["email"] == "ana@gmail.com"


async def test_a_complete_form_is_said_once_in_the_quiet_with_tools_off() -> None:
    llm = _llm()
    seen: list[types.GenerateContentConfig] = []
    answer = llm.answer

    def recording(*, model: str, contents: object, config: types.GenerateContentConfig) -> object:
        seen.append(config)
        return answer(model=model, contents=contents, config=config)

    llm.answer = recording  # type: ignore[method-assign]
    async with demo("figurella", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(rig, "form_state", READY)
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        before = len(seen)
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "Presiona Reservar mi diagnóstico" in turn.text
        context = _texts(llm.captured_contents[-1])
        assert _SAY_READY in context
        assert "It holds: nombre: Ana; sucursal: Vitacura" in context
        (talk,) = seen[before:]
        assert talk.tool_config == types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode=types.FunctionCallingConfigMode.NONE
            )
        )
        # The same state again is not said twice.
        await _page(rig, "form_state", READY)
        assert _idle_windows(rig)[-1] == _IDLE_MS


async def test_a_complete_form_he_already_called_ready_is_not_said_again() -> None:
    async with demo("figurella", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Márcala, y quiero bajar de peso.")
        await _page(rig, "command_done", {"command": "fill_booking_form", "detail": "filled"})
        await _page(rig, "form_state", READY)
        assert _TALK_THROUGH_MS not in _idle_windows(rig)


async def test_her_press_confirmed_by_the_site_is_congratulated_with_the_branch() -> None:
    llm = _llm()
    async with demo("figurella", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(rig, "form_state", READY)
        await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        await _page(
            rig,
            "form_result",
            {"form": "booking", "outcome": "sent", "message": "Enviado.", "fields": []},
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "Felicitaciones" in turn.text
        context = _texts(llm.captured_contents[-1])
        assert "the Vitacura branch will contact her by phone or WhatsApp" in context
        assert "[The site confirmed the booking form was sent (Enviado.).]" in context


async def test_the_sites_refusal_is_talked_through_and_never_called_sent() -> None:
    llm = _llm()
    async with demo("figurella", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(
            rig,
            "form_result",
            {
                "form": "booking",
                "outcome": "error",
                "message": "Hay un error.",
                "fields": ["telefono"],
            },
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        context = _texts(llm.captured_contents[-1])
        assert (
            "The site refused the form when she pressed the button: Hay un error. (fields: telefono)"
            in context
        )
        assert "Never say it was sent." in context


async def test_a_fill_the_page_could_not_make_is_said() -> None:
    llm = _llm()
    async with demo("figurella", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Quiero reservar, me llamo Ana.")
        await _page(rig, "command_failed", {"command": "fill_booking_form", "reason": "no form"})
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "No pude completar" in turn.text


async def test_the_franchise_form_is_filled_on_its_page() -> None:
    llm = _llm()
    async with demo("figurella", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Me llamo Carla, quiero una franquicia.")
        assert _commands(rig, "fill_franchise_form") == [
            {"nombre": "Carla", "telefono": None, "email": None}
        ]
        await rig.driver.user_says("¿Y entonces?")
        assert (
            "The franchise page is opening"
            in _results(llm.captured_contents[-1])["fill_franchise_form"]
        )


# ─── What he never says or does ────────────────────────────────────────────────


def test_the_prompt_forbids_what_the_site_does_not_say() -> None:
    prompt = fg._prompt(SITE)
    for rule in (
        "The site publishes no price, no plan length, no number of sessions",
        "explained and signed at the centre",
        "YOU NEVER PRESS IT",
        "Never ask for or write a RUT, a password, a card number",
        "Never judge her weight or her body",
        "No medical promises and no medical advice",
        "Success stories are their own experiences, never a promise of hers",
        "No branch lists Sunday hours",
    ):
        assert rule in prompt, rule


def test_no_action_can_send_a_form() -> None:
    from voqalize.sdk import Action

    actions = [
        v
        for v in vars(fg).values()
        if isinstance(v, type) and issubclass(v, Action) and v is not Action
    ]
    names = {a.__voqal_action__ for a in actions}  # type: ignore[attr-defined]
    assert names == {
        "navigate",
        "cue",
        "show_section",
        "open_faq",
        "open_link",
        "fill_booking_form",
        "fill_franchise_form",
        "focus_tab",
        "language_changed",
    }
    for a in actions:
        assert not [f for f in a.model_fields if re.search(r"submit|send|consent|rut", f)], a


def test_the_brain_never_fetches_the_site() -> None:
    """The brain runs far from Chile, where the site does not answer. No module
    of the brain opens a connection of its own."""
    backend = Path(fg.__file__).parent
    for source in backend.glob("*.py"):
        text = source.read_text(encoding="utf-8")
        imports = r"^\s*(?:import|from)\s+(?:httpx|aiohttp|requests|socket|http\.client|urllib\.request)\b"
        assert not re.search(imports, text, re.MULTILINE), source


def test_the_committed_knowledge_loads_and_every_offered_key_is_in_the_catalogue() -> None:
    real = kb.load()
    if not real.pages:
        pytest.skip("no crawl committed yet")
    assert {HOME, METHOD, PLANS, FAQ, FRANCHISE, "/convenios/", "/historias-de-exito/"} <= set(
        real.pages
    )
    assert len([b for b in real.branches if b.anchor]) == 7
    assert real.branch("montemar") is not None and not real.branch("montemar").anchor  # type: ignore[union-attr]
    assert len(real.convenios) == 14
    assert {f.key for f in real.faqs()} >= {"faq_precio", "faq_frecuencia", "faq_abdomen"}
    # Every key the prompt offers is a place the extension can find.
    catalogue = json.loads(
        (Path(kb.__file__).parent / "knowledge" / "L3" / "anchors.json").read_text(encoding="utf-8")
    )
    keys = {a["key"] for page in catalogue["pages"].values() for a in page["anchors"]}
    keys |= {a["key"] for a in catalogue["footer"]} | {a["key"] for a in catalogue["faqs"]}
    keys |= {a["key"] for a in catalogue["post"]}
    prompt = fg._prompt(real)
    places = prompt.split("# Places on the site")[1]
    for key in re.findall(r"^\s+- (?:question )?([a-z0-9_]+):", places, re.MULTILINE):
        assert key in keys, key
    # No price in anything he reads: the site has none.
    money = re.compile(r"\$\s?\d|\bCLP\b|\d+\s?(?:pesos|UF)\b", re.IGNORECASE)
    assert not money.search(prompt)
    assert not any(money.search(t.text) for t in real.topics.values())


# ─── Tabs and silent turns ─────────────────────────────────────────────────────


async def test_tabs_are_read_in_and_switching_is_checked() -> None:
    llm = _llm()
    async with demo("figurella", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(
            rig,
            "tabs_changed",
            {
                "tabs": [
                    {"tab_id": "11", "url": "https://figurella.cl/", "title": "Inicio"},
                    {"tab_id": "12", "url": "https://figurella.cl/planes/", "title": "Planes"},
                ],
                "active": "12",
            },
        )
        await rig.driver.user_says("Vuelve a la otra pestaña.")
        assert "11: Inicio; 12: Planes (in front)" in _texts(llm.captured_contents[-1])
        assert rig.command("focus_tab") == {"tab_id": "11"}
        assert _cues(rig) == []


async def test_a_silent_move_gets_his_written_line() -> None:
    async with demo("figurella", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("Ábreme el mapa de Vitacura.")
        check_turn(rig, turn)
        assert turn.text.strip() == _LANDED["map"]["es"]


async def test_a_reply_that_only_promises_is_asked_once_more() -> None:
    async with demo("figurella", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Y los camarines?")
        check_turn(rig, turn)
        assert "Los camarines son cómodos" in turn.text


async def test_a_missed_cue_is_noted_quietly() -> None:
    llm = _llm()
    async with demo("figurella", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(rig, "command_failed", {"command": "cue", "reason": "no place X"})
        await rig.driver.user_says("¿Y entonces?")
        seen = _texts(llm.captured_contents[-1])
        assert "A screen cue of yours did not land (no place X)" in seen
        assert "Tell the visitor plainly" not in seen


def test_his_lines_for_a_move_exist_in_both_languages() -> None:
    for kind, lines in _LANDED.items():
        assert set(lines) == {"en", "es"}, kind
        assert all(line.strip() for line in lines.values()), kind
    assert set(TOGGLE_CONFIRM) == {"en", "es"}


def test_the_floor_is_held_as_the_clini_guide_learned() -> None:
    assert fg.ACK_HOLD_AFTER_S >= 5.5 and fg.ACK_SORRY_AFTER_S >= 15
    assert fg.HOLD_WITHOUT_NOD_S <= 3.0
