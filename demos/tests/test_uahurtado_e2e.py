"""Javier, Universidad Alberto Hurtado's guide, end to end over the wire — no network, no LLM key.

The real ``UahurtadoBrain`` on a real ``brain_server`` socket, driven by the
conformance ``VoqalizeDriver``, with only the model scripted. The knowledge is
a small invented university in the crawl's own shape, put in place of the
committed one, so no test depends on what the crawl found this week. Its fees
and weights are invented too, and they reach the brain the only way real ones
do: from the page, as events.

What this demo earns that others do not:

**Every figure is read live, in the visitor's browser.** A fee or a weight is
said only after the page reported it; a read that fails is said as a failure;
nothing the brain knows carries one.

**The arithmetic is the brain's.** The weighted score is worked out from the
career's own weights and handed to the model with its words.

**Three hosts.** A page is its whole URL; a cue to www or postgrados keeps its
host; a move after a page cue waits for that page.

**Forms are filled, never sent.** No RUT, no Enviar, no sign-up opened.

Run: ``cd demos && uv run pytest tests/test_uahurtado_e2e.py``
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
from .test_sendpotion_latam import spain_words

discover()

from voqalize_demos._loaded.uahurtado import brain as uah  # noqa: E402
from voqalize_demos._loaded.uahurtado import knowledge as kb  # noqa: E402
from voqalize_demos._loaded.uahurtado.brain import (  # noqa: E402
    _IDLE_MS,
    _LANDED,
    _TALK_THROUGH_MS,
    TOGGLE_CONFIRM,
    asked_page,
    asks_call_language,
    greeting,
    language_of,
)
from voqalize_demos._loaded.uahurtado.knowledge import (  # noqa: E402
    Career,
    Faq,
    Knowledge,
    Page,
    Program,
    Section,
)

# ─── An invented university ────────────────────────────────────────────────────

ADM = "https://admision.uahurtado.cl"
WWW = "https://www.uahurtado.cl"
POS = "https://postgrados.uahurtado.cl"
PSICO = f"{ADM}/carreras/psicologia/"
DERECHO = f"{ADM}/carreras/derecho/"
INFORMATICA = f"{ADM}/carreras/ingenieria-civil-en-informatica/"
CAMPUS = f"{WWW}/la-universidad/campus/campus-patrimonial/"
MAGISTER = f"{POS}/programa/magister-intervencion-psicosocial/"
TABS = (
    "Datos Académicos",
    "Descripción",
    "Requisitos y Aranceles",
    "Beneficios",
    "Perfil de Egreso",
)


def _career(slug: str, name: str, faculty: str, **more: Any) -> Career:
    return Career(
        slug=slug,
        name=name,
        url=f"{ADM}/carreras/{slug}/",
        faculty=faculty,
        duration="10 semestres",
        jornada="Diurna",
        campus="Casa Central",
        tabs=TABS,
        **more,
    )


SITE = Knowledge(
    l1="Universidad Alberto Hurtado is a university in Santiago (invented for tests).",
    topics={},
    pages={
        "admision.uahurtado.cl/": Page(
            "admision.uahurtado.cl/",
            "Admisión UAH",
            kind="home",
            sections=(Section("Oferta Académica"), Section("Audiomallas")),
        ),
        "admision.uahurtado.cl/becas-y-beneficios": Page(
            "admision.uahurtado.cl/becas-y-beneficios",
            "Becas y Beneficios | Admisión UAH",
            sections=(
                Section("Becas y Beneficios 2026"),
                Section("Beca Excelencia Académica UAH", "Para los mejores puntajes PAES."),
            ),
        ),
        "admision.uahurtado.cl/gratuidad-universitaria": Page(
            "admision.uahurtado.cl/gratuidad-universitaria",
            "Gratuidad | Admisión UAH",
            sections=(Section("Gratuidad Universitaria 2027"),),
            faqs=(Faq("¿Qué es la gratuidad?", "Un beneficio del Estado."),),
        ),
        "admision.uahurtado.cl/ven-y-conocenos": Page(
            "admision.uahurtado.cl/ven-y-conocenos",
            "Ven y Conócenos | Admisión UAH",
            sections=(Section("Ven y Conócenos"),),
        ),
        "www.uahurtado.cl/la-universidad/campus/campus-patrimonial": Page(
            "www.uahurtado.cl/la-universidad/campus/campus-patrimonial",
            "Campus Patrimonial - Universidad Alberto Hurtado",
            sections=(Section("UBICACIÓN", "Casa Central, Av. Libertador 1825."),),
        ),
        "postgrados.uahurtado.cl/": Page(
            "postgrados.uahurtado.cl/", "Postgrados UAH", sections=(Section("Magíster"),)
        ),
    },
    careers={
        "psicologia": _career(
            "psicologia", "Psicología", "Facultad de Psicología", has_audiomalla=True
        ),
        "derecho": _career("derecho", "Derecho", "Facultad de Derecho"),
        "ingenieria-civil-en-informatica": _career(
            "ingenieria-civil-en-informatica",
            "Ingeniería Civil en Informática",
            "Facultad de Ingeniería",
            aliases=("informática",),
        ),
    },
    programs={
        "magister-intervencion-psicosocial": Program(
            slug="magister-intervencion-psicosocial",
            name="Magíster en Intervención Psicosocial",
            url=MAGISTER,
            type="magister",
            area="Psicología",
            modalidad="presencial",
        ),
    },
)


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every session reads the invented university, and he never nods unless
    a test asks him to: a nod is a unit of its own."""
    monkeypatch.setattr(kb, "KNOWLEDGE", SITE)
    monkeypatch.setattr(uah, "ACK_RATE", 0.0)
    monkeypatch.setattr(uah, "HOLD_WITHOUT_NOD_S", 30.0)
    yield


# ─── What the page reports ─────────────────────────────────────────────────────

FEES_TEXT = "Aranceles Año 2027 Matrícula $277.456 Arancel anual $7.167.421 Titulación 11 UF."
WEIGHTS = [
    {"label": "NEM", "value": "10%"},
    {"label": "Ranking", "value": "20%"},
    {"label": "Competencia lectora", "value": "30%"},
    {"label": "Matemática", "value": "30%"},
    {"label": "Historia y Ciencias Sociales / Ciencias", "value": "10% ó 10%"},
    {"label": "Puntaje ponderado mínimo de postulación", "value": "0"},
    {"label": "Puntaje promedio LyM mínimo de postulación", "value": "570"},
]
FORM = {
    "fields": ["nombre", "apellido", "rut", "email", "fono", "consulta", "carrera"],
    "career": "Psicología",
}


def _page_changed(url: str, **fields: object) -> dict[str, object]:
    return {"url": url, "title": "", "kind": "page", **fields}


def _career_page(**sheet: object) -> dict[str, object]:
    return _page_changed(
        PSICO,
        title="Psicología | Admisión UAH",
        kind="career",
        toggles=list(TABS),
        headings=["Psicología", "Datos Académicos"],
        career={
            "slug": "psicologia",
            "name": "Psicología",
            "facts": [{"label": "Duración", "value": "10 semestres"}],
            "tabs": list(TABS),
            "has_audiomalla": True,
            "audiomalla_label": "Directora de Psicología",
            **sheet,
        },
        form=FORM,
    )


async def _page(rig: object, event: str, payload: dict[str, object]) -> None:
    await rig.driver.send_ui_event(event, payload)  # type: ignore[attr-defined]
    # `on_rtvi` takes no floor and there is nothing to await: give it a moment.
    await asyncio.sleep(0.1)


def _results(contents: list[types.Content]) -> dict[str, str]:
    return {
        p.function_response.name or "": str((p.function_response.response or {})["result"])
        for c in contents
        for p in (c.parts or [])
        if p.function_response is not None
    }


def _texts(contents: list[types.Content]) -> str:
    return "\n".join(p.text or "" for c in contents for p in (c.parts or []))


def _idle_windows(rig: object) -> list[int | None]:
    return [c.idle.timeout_ms for c in _configs(rig) if c.idle is not None]  # type: ignore[arg-type]


def _commands(rig: object, name: str) -> list[dict[str, object]]:
    return [c["payload"] for c in rig.driver.ui_commands if c.get("command") == name]  # type: ignore[attr-defined]


def _cues(rig: object) -> list[dict[str, object]]:
    return _commands(rig, "cue")


NONE = {"url": None, "heading": None, "text": None, "faq": None}


# ─── Greeting, voice and language ──────────────────────────────────────────────


async def test_he_greets_in_spanish_with_javier_on_both_legs() -> None:
    async with demo("uahurtado", ScriptedGemini()) as rig:
        turn = await rig.driver.start_session(init={"url": f"{ADM}/", "path": "/"})
        check_greeting(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert turn.text.startswith("Hola, soy Javier, tu guía de la Universidad Alberto Hurtado.")
        assert _idle_windows(rig)[0] == _IDLE_MS


async def test_the_opener_follows_the_page_the_call_starts_on() -> None:
    assert "¿Te cuento sobre Psicología" in greeting(PSICO, "es", SITE)
    assert "postgrado" in greeting(MAGISTER, "es", SITE)
    assert "becas" in greeting(f"{ADM}/becas-y-beneficios/", "es", SITE)
    assert "campus" in greeting(CAMPUS, "es", SITE)
    assert greeting(f"{ADM}/", "en", SITE).startswith("Hi, I'm Javier")


async def test_a_chosen_english_holds_from_the_start() -> None:
    llm = ScriptedGemini({"Hola, ¿qué carreras hay?": reply("There are many careers.")})
    async with demo("uahurtado", llm) as rig:
        turn = await rig.driver.start_session(init={"url": f"{ADM}/", "lang": "en"})
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert turn.text.startswith("Hi, I'm Javier")
        await rig.driver.user_says("Hola, ¿qué carreras hay?")
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert "[The visitor chose English before the call." in _texts(llm.captured_contents[-1])


async def test_the_toggle_switches_both_legs_and_confirms() -> None:
    async with demo("uahurtado", ScriptedGemini()) as rig:
        await rig.driver.start_session(init={"url": f"{ADM}/"})
        await _page(rig, "language_requested", {"language": "en"})
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert turn.text == TOGGLE_CONFIRM["en"]
        assert _commands(rig, "language_changed")[-1] == {"language": "en"}


async def test_english_heard_moves_both_legs_before_he_answers() -> None:
    llm = ScriptedGemini(
        {"What careers do you have in engineering?": reply("There are several in engineering.")}
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": f"{ADM}/"})
        turn = await rig.driver.user_says("What careers do you have in engineering?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="en")


def test_a_career_taught_in_english_is_not_a_request_about_the_call() -> None:
    assert asks_call_language("¿Puedes hablar en inglés?")
    assert asks_call_language("Can we speak Spanish?")
    assert not asks_call_language("¿La carrera se dicta en inglés?")
    assert not asks_call_language("Are the classes taught in English?")


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("¿Cuánto cuesta estudiar Psicología?", "es"),
        ("Quiero saber si me alcanza el puntaje", "es"),
        ("How much does it cost to study here?", "en"),
        ("Psicología", None),
        ("ok", None),
    ],
)
def test_the_language_is_read_from_words(text: str, lang: str | None) -> None:
    assert language_of(text) == lang


# ─── Cues: the screen follows his voice, on three hosts ────────────────────────


async def test_cues_leave_the_speech_and_carry_whole_urls() -> None:
    llm = ScriptedGemini(
        {
            "Háblame de Psicología.": reply(
                "{page: /carreras/psicologia/} Te abro la carrera. Psicología dura diez "
                "semestres. {show: Descripción} Forma psicólogos con mirada social."
            ),
            "¿Dónde queda la universidad?": reply(
                "{page: www.uahurtado.cl/la-universidad/campus/campus-patrimonial/} Está en "
                "Santiago centro. {show: UBICACIÓN} La Casa Central está junto al metro."
            ),
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": f"{ADM}/"})
        turn = await rig.driver.user_says("Háblame de Psicología.")
        check_turn(rig, turn)
        assert "{" not in turn.text and "Psicología dura diez semestres." in turn.text
        cues = _cues(rig)
        assert cues[0] == {**NONE, "at": "te abro la", "word": 0, "url": PSICO}
        assert cues[1] == {
            **NONE,
            "at": "forma psicologos con",
            "word": 8,
            "url": PSICO,
            "heading": "Descripción",
        }
        await _page(rig, "page_changed", _career_page())
        await rig.driver.user_says("¿Dónde queda la universidad?")
        campus = [c for c in _cues(rig) if c["url"] == CAMPUS]
        assert campus[0]["at"] == "esta en santiago"
        assert campus[1]["heading"] == "UBICACIÓN"


async def test_an_invented_page_is_dropped_and_he_is_told() -> None:
    llm = ScriptedGemini(
        {
            "¿Tienen medicina?": reply("{page: /carreras/medicina/} No tenemos Medicina."),
            "Ok.": reply("Te cuento otras."),
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": f"{ADM}/"})
        await rig.driver.user_says("¿Tienen medicina?")
        assert _cues(rig) == []
        await rig.driver.user_says("Ok.")
        assert "named no page of the sites" in _texts(llm.captured_contents[-1])


async def test_a_tab_on_the_page_in_front_is_a_show_cue() -> None:
    llm = ScriptedGemini(
        {"¿Qué piden?": reply("{show: requisitos y aranceles} Aquí están los requisitos.")}
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": PSICO})
        await _page(rig, "page_changed", _career_page())
        await rig.driver.user_says("¿Qué piden?")
        assert _cues(rig) == [
            {**NONE, "at": "aqui estan los", "word": 0, "heading": "Requisitos y Aranceles"}
        ]


async def test_a_reply_that_forgets_the_page_gets_the_asked_one() -> None:
    llm = ScriptedGemini(
        {"¿Qué becas tienen?": reply("Hay becas por excelencia académica y otras.")}
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": f"{ADM}/"})
        await rig.driver.user_says("¿Qué becas tienen?")
        assert _cues(rig)[0]["url"] == f"{ADM}/becas-y-beneficios/"


def test_asked_pages_read_the_visitors_words() -> None:
    assert asked_page("Háblame de informática", SITE) == (
        "admision.uahurtado.cl/carreras/ingenieria-civil-en-informatica"
    )
    assert asked_page("¿Hay gratuidad?", SITE) == "admision.uahurtado.cl/gratuidad-universitaria"
    assert asked_page("Where is the campus?", SITE) == (
        "www.uahurtado.cl/la-universidad/campus/campus-patrimonial"
    )
    assert asked_page("Busco un magíster", SITE) == "postgrados.uahurtado.cl/"
    # A postgraduate word wins over the undergraduate career it names.
    assert asked_page("Busco un magíster en psicología", SITE) == "postgrados.uahurtado.cl/"
    assert asked_page("El magíster en intervención psicosocial", SITE) == (
        "postgrados.uahurtado.cl/programa/magister-intervencion-psicosocial"
    )
    # A figure is read by its own tool, which moves the page itself.
    assert asked_page("¿Cuánto cuesta Psicología?", SITE) is None
    assert asked_page("¿Puedes hablar en inglés?", SITE) is None


# ─── Fees: read live, said with their words ────────────────────────────────────


async def test_fees_on_the_page_in_front_are_said_at_once_and_the_tab_opens() -> None:
    llm = ScriptedGemini(
        {
            "¿Cuánto cuesta?": [
                call("read_fees", request={}),
                reply(
                    "Para dos mil veintisiete la matrícula cuesta doscientos setenta y siete mil."
                ),
            ]
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": PSICO})
        await _page(rig, "page_changed", _career_page(fees_text=FEES_TEXT))
        turn = await rig.driver.user_says("¿Cuánto cuesta?")
        check_turn(rig, turn)
        result = _results(llm.captured_contents[-1])["read_fees"]
        assert "Read just now from Psicología's page" in result
        assert "Matrícula $277.456 — say “doscientos setenta y siete mil cuatrocientos" in result
        assert "Arancel anual $7.167.421 — say “siete millones ciento sesenta y siete mil" in result
        assert "Titulación 11 UF — say “once UF”" in result
        assert "year 2027" in result
        assert rig.command("show_admission") == {
            "url": PSICO,
            "slug": "psicologia",
            "focus": "fees",
        }
        # The page's own read follows; already told, it is not talked through again.
        await _page(
            rig,
            "admission_read",
            {"slug": "psicologia", "url": PSICO, "fees_text": FEES_TEXT, "weights": WEIGHTS},
        )
        assert _idle_windows(rig)[-1] == _IDLE_MS


async def test_fees_not_yet_read_are_never_guessed_and_arrive_from_the_page() -> None:
    llm = ScriptedGemini(
        {
            "¿Cuánto cuesta Derecho?": [
                call("read_fees", request={"career": "Derecho"}),
                reply("Te abro los aranceles de Derecho."),
            ],
            "The page answered": reply("La matrícula cuesta doscientos mil pesos."),
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": f"{ADM}/"})
        turn = await rig.driver.user_says("¿Cuánto cuesta Derecho?")
        check_turn(rig, turn)
        result = _results(llm.captured_contents[-1])["read_fees"]
        assert "never a figure yet" in result
        assert "$" not in result
        assert rig.command("show_admission") == {"url": DERECHO, "slug": "derecho", "focus": "fees"}
        await _page(
            rig,
            "admission_read",
            {
                "slug": "derecho",
                "url": DERECHO,
                "fees_text": "Año 2027 Matrícula: $200.000 Arancel: $5.000.000 Titulación 9 UF",
                "api_fees_text": "Año 2027 Matrícula $200.000 Arancel anual $5.000.000",
            },
        )
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        seen = _texts(llm.captured_contents[-1])
        assert "Fees for Derecho, read just now from the page" in seen
        assert "say “cinco millones de pesos”" in seen
        assert "say “doscientos mil pesos”" in seen


async def test_a_failed_read_is_said_as_one() -> None:
    llm = ScriptedGemini(
        {
            "¿Cuánto cuesta Derecho?": [
                call("read_fees", request={"career": "Derecho"}),
                reply("Te abro los aranceles."),
            ],
            "not done": reply("No puedo ver los aranceles ahora mismo."),
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": f"{ADM}/"})
        await rig.driver.user_says("¿Cuánto cuesta Derecho?")
        await _page(
            rig,
            "command_failed",
            {"command": "show_admission", "reason": "no Requisitos y Aranceles tab on the page"},
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "No puedo ver los aranceles" in turn.text
        seen = _texts(llm.captured_contents[-1])
        assert "you cannot see the fees or the weights right now" in seen


# ─── "¿Me alcanza?": the arithmetic is the brain's ─────────────────────────────


async def test_the_weighted_score_is_worked_out_from_the_pages_weights() -> None:
    llm = ScriptedGemini(
        {
            "Saqué": [
                call(
                    "estimate_score",
                    request={
                        "nem": 700,
                        "ranking": 720,
                        "lectora": 750,
                        "matematica": 680,
                        "historia": 600,
                        "ciencias": 650,
                    },
                ),
                reply("Tu puntaje ponderado estimado es setecientos ocho."),
            ]
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": PSICO})
        await _page(rig, "page_changed", _career_page(weights=WEIGHTS))
        await rig.driver.user_says("Saqué 750 en lectora y 680 en matemática.")
        result = _results(llm.captured_contents[-1])["estimate_score"]
        assert "Weighted score 708 — say “setecientos ocho”" in result
        assert "For Historia o Ciencias the higher one counts: Ciencias." in result
        assert "against the minimum of 570: it meets it." in result
        assert rig.command("show_admission")["focus"] == "requirements"


async def test_a_grade_average_is_not_taken_for_a_score() -> None:
    llm = ScriptedGemini(
        {
            "NEM": [
                call("estimate_score", request={"nem": 6, "lectora": 700, "matematica": 650}),
                reply("Necesito tu puntaje NEM en puntos."),
            ]
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": PSICO})
        await _page(rig, "page_changed", _career_page(weights=WEIGHTS))
        await rig.driver.user_says("Tengo NEM 6,2.")
        result = _results(llm.captured_contents[-1])["estimate_score"]
        assert "is a grade average, not a score" in result
        assert "Weighted score" not in result


async def test_scores_for_a_career_not_in_front_wait_for_its_weights() -> None:
    llm = ScriptedGemini(
        {
            "Derecho": [
                call(
                    "estimate_score",
                    request={"career": "Derecho", "lectora": 700, "matematica": 600},
                ),
                reply("Reviso las ponderaciones de Derecho."),
            ],
            "Their estimate": reply("Con esos puntajes llegas a seiscientos cincuenta."),
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": f"{ADM}/"})
        await rig.driver.user_says("¿Me alcanza para Derecho?")
        result = _results(llm.captured_contents[-1])["estimate_score"]
        assert "never a score yet" in result
        await _page(
            rig,
            "admission_read",
            {
                "slug": "derecho",
                "url": DERECHO,
                "weights": [
                    {"label": "Competencia lectora", "value": "50%"},
                    {"label": "Matemática", "value": "50%"},
                ],
            },
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        seen = _texts(llm.captured_contents[-1])
        assert "Weighted score 650 — say “seiscientos cincuenta”" in seen


# ─── The menu, the audiomalla, visits ──────────────────────────────────────────


async def test_the_careers_menu_opens_at_a_faculty() -> None:
    llm = ScriptedGemini(
        {
            "ingeniería": reply_and_call(
                "En ingeniería está Ingeniería Civil en Informática.",
                "show_careers",
                request={"faculty": "ingenieria"},
            )
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": f"{ADM}/"})
        await rig.driver.user_says("¿Qué carreras de ingeniería tienen?")
        assert rig.command("open_career_menu") == {
            "faculty": "Facultad de Ingeniería",
            "url": f"{ADM}/",
        }
        # It opened as he said it would: nothing more to say about it.
        await _page(rig, "command_done", {"command": "open_career_menu", "detail": "rung"})
        assert _idle_windows(rig)[-1] == _IDLE_MS


async def test_the_audiomalla_plays_and_he_keeps_quiet_until_it_ends() -> None:
    llm = ScriptedGemini(
        {
            "directora": reply_and_call("Te pongo el audio, escucha.", "play_audiomalla"),
            "audiomalla finished": reply("¿Qué te pareció?"),
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": PSICO})
        await _page(rig, "page_changed", _career_page())
        await rig.driver.user_says("Sí, quiero escuchar a la directora.")
        assert rig.command("play_audiomalla") == {"url": PSICO}
        await _page(rig, "command_done", {"command": "play_audiomalla", "detail": "playing"})
        assert _idle_windows(rig)[-1] == _IDLE_MS
        quiet = await rig.driver.user_idle(level=1, idle_ms=_IDLE_MS, timeout=1.0)
        assert not quiet.text.strip()
        await _page(rig, "audiomalla_ended", {"finished": True})
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert turn.text == "¿Qué te pareció?"


VISITS = [
    {
        "title": "Talleres de Primavera",
        "text": "14 de noviembre",
        "open": True,
        "signup_label": "Inscribirse aquí",
    },
    {"title": "Ensayo PAES", "text": "REALIZADO", "done": True},
]


async def test_a_past_visit_is_never_offered_and_a_signup_is_only_rung() -> None:
    llm = ScriptedGemini(
        {
            "ensayo": [
                call("show_signup", request={"visit": "Ensayo PAES"}),
                reply("Ese ya pasó."),
            ],
            "talleres": reply_and_call(
                "Aquí te puedes inscribir.", "show_signup", request={"visit": "talleres"}
            ),
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": f"{ADM}/ven-y-conocenos/"})
        await _page(rig, "page_changed", _page_changed(f"{ADM}/ven-y-conocenos/", visits=VISITS))
        await rig.driver.user_says("Quiero ir al ensayo.")
        assert "already happened" in _results(llm.captured_contents[-1])["show_signup"]
        assert "show_signup" not in rig.actions()
        seen = _texts(llm.captured_contents[-1])
        assert "Already held (REALIZADO, never offer them): Ensayo PAES." in seen
        await rig.driver.user_says("Me interesan los talleres.")
        assert rig.command("show_signup") == {"title": "Talleres de Primavera"}


# ─── The contact form: filled, never sent, never a RUT ─────────────────────────


async def test_the_form_is_filled_as_dictated_without_a_rut_or_a_send() -> None:
    llm = ScriptedGemini(
        {
            "Me llamo": reply_and_call(
                "Listo, lo completo.",
                "fill_lead_form",
                request={
                    "nombre": "Ana",
                    "apellido": "Pérez",
                    "email": "Ana.Perez @Correo.cl",
                    "fono": "+56 9 1234 5678",
                    "consulta": "Consulta por arancel 2027 de Psicología",
                    "focus_rut": True,
                },
            ),
            "The page answered": reply("Revisa tus datos y presiona Enviar."),
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": PSICO})
        await _page(rig, "page_changed", _career_page())
        await rig.driver.user_says(
            "Me llamo Ana Pérez, ana punto perez arroba correo punto cl, fono +56 9 1234 5678."
        )
        filled = rig.command("fill_lead_form")
        assert filled == {
            "nombre": "Ana",
            "apellido": "Pérez",
            "email": "ana.perez@correo.cl",
            "fono": "+56912345678",
            "consulta": "Consulta por arancel 2027 de Psicología",
            "carrera": None,
            "via": None,
            "focus_rut": True,
        }
        await _page(rig, "lead_form_state", {"filled": ["nombre"], "missing": ["rut"]})
        await _page(rig, "command_done", {"command": "fill_lead_form", "detail": "filled"})
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "presiona Enviar" in turn.text
        assert not {"submit", "send", "send_lead_form"} & set(rig.actions())


async def test_a_rut_is_never_typed_and_a_reshaped_phone_is_refused() -> None:
    llm = ScriptedGemini(
        {
            "RUT": [
                call("fill_lead_form", request={"nombre": "12.345.678-5"}),
                reply("Tu RUT lo escribes tú."),
            ],
            "fono": [
                call("fill_lead_form", request={"fono": "912345679"}),
                reply("¿Me repites tu número?"),
            ],
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": PSICO})
        await _page(rig, "page_changed", _career_page())
        await rig.driver.user_says("Mi RUT es 12.345.678-5.")
        assert "You never type a RUT" in _results(llm.captured_contents[-1])["fill_lead_form"]
        await rig.driver.user_says("Mi fono es 9 1234 5678.")
        assert (
            "is not what the visitor said" in _results(llm.captured_contents[-1])["fill_lead_form"]
        )
        assert "fill_lead_form" not in rig.actions()
        assert "12.345.678-5" not in str(rig.driver.ui_commands)


async def test_a_page_without_the_form_opens_one_and_a_career_is_picked_from_the_list() -> None:
    llm = ScriptedGemini(
        {
            "contacten": call("fill_lead_form", request={"nombre": "Ana"}),
            "derecho": reply_and_call(
                "Lo completo.", "fill_lead_form", request={"carrera": "derecho"}
            ),
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": CAMPUS})
        await _page(rig, "page_changed", _page_changed(CAMPUS))
        turn = await rig.driver.user_says("Quiero que me contacten.")
        # No career seen yet: the admision home, whose form lists them all.
        assert _page_loads(rig) == [f"{ADM}/"]
        assert turn.text == _LANDED["to_form"]["es"]
        assert "fill_lead_form" not in rig.actions()
        await _page(
            rig,
            "page_changed",
            _page_changed(
                f"{ADM}/",
                kind="home",
                form={
                    "fields": ["nombre", "email", "rut", "fono", "consulta", "carrera"],
                    "career_options": ["Psicología", "Derecho"],
                },
            ),
        )
        assert rig.command("fill_lead_form")["nombre"] == "Ana"
        await _page(rig, "command_done", {"command": "fill_lead_form", "detail": "filled"})
        await rig.driver.user_says("Para derecho.")
        assert _commands(rig, "fill_lead_form")[-1]["carrera"] == "Derecho"


# ─── Postgrado ─────────────────────────────────────────────────────────────────

REQUISITOS = (
    "Valores Arancel Total $5.250.000 Matrícula $200.000 Graduación 10 UF. Matrícula "
    "anticipada: formaliza antes del 30/10/2026 y obtén 30% de descuento en el arancel."
)


async def test_a_programme_is_found_and_its_values_read_from_the_page() -> None:
    llm = ScriptedGemini(
        {
            "magíster": [
                call("find_programs", request={"query": "intervención psicosocial"}),
                reply("Está el Magíster en Intervención Psicosocial."),
            ],
            "cuesta": [
                call("read_program", request={}),
                reply("El arancel total es cinco millones doscientos cincuenta mil pesos."),
            ],
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": f"{POS}/"})
        await rig.driver.user_says("Busco un magíster en psicología.")
        found = _results(llm.captured_contents[-1])["find_programs"]
        assert "Magíster en Intervención Psicosocial — postgrados.uahurtado.cl/programa/" in found
        await _page(
            rig,
            "page_changed",
            _page_changed(
                MAGISTER,
                kind="program",
                program={
                    "slug": "magister-intervencion-psicosocial",
                    "name": "Magíster en Intervención Psicosocial",
                    "requisitos_text": REQUISITOS,
                    "accordion": ["Descripción General", "Requisitos y Valores"],
                },
            ),
        )
        await rig.driver.user_says("¿Cuánto cuesta?")
        result = _results(llm.captured_contents[-1])["read_program"]
        assert "Arancel Total $5.250.000 — say “cinco millones doscientos cincuenta mil pesos”" in (
            result
        )
        assert "30/10/2026 (30 de octubre de 2026)" in result
        assert rig.command("show_program") == {
            "url": MAGISTER,
            "slug": "magister-intervencion-psicosocial",
        }


# ─── One move at a time; a move waits for the page a cue is loading ───────────


async def test_a_move_asked_while_another_runs_is_queued_then_sent() -> None:
    llm = ScriptedGemini(
        {
            "Derecho": [
                call("read_fees", request={"career": "Derecho"}),
                reply("Te abro los aranceles."),
            ],
            "menú": reply_and_call("Te abro el menú.", "show_careers", request={}),
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": f"{ADM}/"})
        await rig.driver.user_says("¿Cuánto cuesta Derecho?")
        await rig.driver.user_says("Y ábreme el menú.")
        assert "open_career_menu" not in rig.actions()
        assert "Queued, not sent yet" in _results(llm.captured_contents[-1]).get(
            "show_careers", "Queued, not sent yet"
        )
        await _page(
            rig, "admission_read", {"slug": "derecho", "url": DERECHO, "fees_text": FEES_TEXT}
        )
        assert "open_career_menu" in rig.actions()


async def test_a_queued_move_survives_a_link_opened_meanwhile() -> None:
    llm = ScriptedGemini(
        {
            "Derecho": [
                call("read_fees", request={"career": "Derecho"}),
                reply("Te abro los aranceles."),
            ],
            "menú": reply_and_call("Te abro el menú.", "show_careers", request={}),
            "simulador": reply_and_call(
                "Te abro el simulador.", "open_link", request={"kind": "simulador"}
            ),
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": f"{ADM}/"})
        await rig.driver.user_says("¿Cuánto cuesta Derecho?")
        await rig.driver.user_says("Y ábreme el menú.")
        await rig.driver.user_says("Y el simulador también.")
        assert "open_link" in rig.actions()
        assert "open_career_menu" not in rig.actions()
        await _page(
            rig, "admission_read", {"slug": "derecho", "url": DERECHO, "fees_text": FEES_TEXT}
        )
        assert "open_career_menu" in rig.actions()


async def test_a_form_fill_after_a_page_cue_waits_for_that_page() -> None:
    llm = ScriptedGemini(
        {
            "contacten": reply_and_call(
                "{page: /carreras/psicologia/} Te llevo a Psicología y completo el formulario.",
                "fill_lead_form",
                request={"nombre": "Ana"},
            )
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": f"{ADM}/"})
        await _page(rig, "page_changed", _page_changed(f"{ADM}/", form=FORM))
        await rig.driver.user_says("Quiero que me contacten de Psicología, soy Ana.")
        assert _cues(rig)[0]["url"] == PSICO
        assert "fill_lead_form" not in rig.actions()
        await _page(rig, "page_changed", _career_page())
        assert rig.command("fill_lead_form")["nombre"] == "Ana"


# ─── A move whose page is not in front opens that page first ───────────────────
#
# Call f6dbda3e (dev, 2026-10-23): on Ingeniería Civil en Informática the
# visitor said "I would like to do a visit"; no page opened, then on "Yeah."
# he said "you can sign up right here" while show_signup was refused on the
# career page; with a {page: /ven-y-conocenos/} cue in the next reply it was
# refused again, judged on the page still in front. On /ven-y-conocenos/,
# "Can you show me the contact form?" got "right at the top" and a refused
# fill_lead_form: that page has no form. Each took the visitor correcting him.

VEN = f"{ADM}/ven-y-conocenos/"
TOURS = [
    {
        "title": "Visitas guiadas",
        "text": "Desde el 1 de octubre",
        "open": True,
        "signup_label": "Inscribirse aquí",
    },
    {"title": "UAH ABIERTA / ENSAYO PAES", "text": "REALIZADO", "done": True},
]


def _page_loads(rig: object) -> list[object]:
    """The pages his cues load: a cue with a URL and nothing to ring there."""
    return [c["url"] for c in _cues(rig) if c["url"] and not (c["heading"] or c["text"])]


def _informatica_page() -> dict[str, object]:
    return _page_changed(
        INFORMATICA,
        title="Ingeniería Civil en Informática | Admisión UAH",
        kind="career",
        toggles=list(TABS),
        headings=["Ingeniería Civil en Informática", "Datos Académicos"],
        career={
            "slug": "ingenieria-civil-en-informatica",
            "name": "Ingeniería Civil en Informática",
        },
        form={**FORM, "career": "Ingeniería Civil en Informática"},
    )


def test_a_visit_asked_in_english_is_the_visits_page() -> None:
    for said in ("I would like to do a visit to this university.", "Can I visit the campus?"):
        assert asked_page(said, SITE) == "admision.uahurtado.cl/ven-y-conocenos", said


async def test_a_signup_asked_on_another_page_opens_the_visits_page_then_rings_it() -> None:
    llm = ScriptedGemini(
        {
            "Yeah": reply_and_call(
                "Here are our upcoming activities.", "show_signup", request={"visit": "visitas"}
            )
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": INFORMATICA, "lang": "en"})
        await _page(rig, "page_changed", _informatica_page())
        await rig.driver.user_says("Yeah.")
        assert _page_loads(rig) == [VEN]
        assert "show_signup" not in rig.actions()
        await _page(rig, "page_changed", _page_changed(VEN, visits=TOURS))
        assert rig.command("show_signup") == {"title": "Visitas guiadas"}


async def test_a_signup_after_a_page_cue_waits_for_the_visits_page() -> None:
    llm = ScriptedGemini(
        {
            "card": reply_and_call(
                "{page: /ven-y-conocenos/} Here is our Ven y Conócenos page.",
                "show_signup",
                request={"visit": "Visitas guiadas"},
            )
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": INFORMATICA, "lang": "en"})
        await _page(rig, "page_changed", _informatica_page())
        await rig.driver.user_says("I can't see which card you mean.")
        assert _page_loads(rig) == [VEN]
        assert "show_signup" not in rig.actions()
        # The page it leaves may report itself again first: that is not the one.
        await _page(rig, "page_changed", _informatica_page())
        assert "show_signup" not in rig.actions()
        await _page(rig, "page_changed", _page_changed(VEN, visits=TOURS))
        assert rig.command("show_signup") == {"title": "Visitas guiadas"}


async def test_a_signup_whose_page_never_comes_is_said_as_not_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(uah, "_PAGE_WAIT_S", 0.3)
    llm = ScriptedGemini(
        {
            "tour": reply_and_call(
                "I'm taking you to the visits page.", "show_signup", request={"visit": "visitas"}
            ),
            "The page answered": reply("The visits page did not open."),
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": INFORMATICA, "lang": "en"})
        await _page(rig, "page_changed", _informatica_page())
        await rig.driver.user_says("Show me the guided tour.")
        await asyncio.sleep(0.5)
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert turn.text == "The visits page did not open."
        assert "show_signup not done" in _texts(llm.captured_contents[-1])
        assert "show_signup" not in rig.actions()


async def test_the_form_asked_on_a_page_without_one_opens_the_career_and_fills_there() -> None:
    llm = ScriptedGemini(
        {
            "contact form": reply_and_call(
                "Here is the contact form.", "fill_lead_form", request={}
            ),
            "Ana": reply_and_call(
                "Done, I put your name in.", "fill_lead_form", request={"nombre": "Ana"}
            ),
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": INFORMATICA, "lang": "en"})
        await _page(rig, "page_changed", _informatica_page())
        await _page(rig, "page_changed", _page_changed(VEN, visits=TOURS))
        await rig.driver.user_says("Can you show me the contact form at least?")
        # The career he was on, whose form is at its top.
        assert _page_loads(rig) == [INFORMATICA]
        await _page(rig, "page_changed", _informatica_page())
        assert "fill_lead_form" not in rig.actions()  # nothing to fill yet
        await rig.driver.user_says("My name is Ana.")
        result = _results(llm.captured_contents[-1])["fill_lead_form"]
        assert "Ingeniería Civil en Informática's page is opening" in result
        assert rig.command("fill_lead_form")["nombre"] == "Ana"


async def test_a_name_given_on_a_page_without_the_form_is_filled_once_the_career_loads() -> None:
    llm = ScriptedGemini(
        {
            "contacten": reply_and_call(
                "Te llevo al formulario.", "fill_lead_form", request={"nombre": "Ana"}
            )
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": INFORMATICA})
        await _page(rig, "page_changed", _informatica_page())
        await _page(rig, "page_changed", _page_changed(VEN, visits=TOURS))
        await rig.driver.user_says("Quiero que me contacten, soy Ana.")
        assert _page_loads(rig) == [INFORMATICA]
        assert "fill_lead_form" not in rig.actions()
        await _page(rig, "page_changed", _informatica_page())
        assert rig.command("fill_lead_form")["nombre"] == "Ana"


# ─── His own words ─────────────────────────────────────────────────────────────


async def test_prices_in_digits_are_said_in_words_and_uf_as_chile_says_it() -> None:
    llm = ScriptedGemini(
        {
            "precio": reply("La matrícula es $277.456 y la titulación 11 UF."),
            "Gracias": reply("De nada."),
        }
    )
    async with demo("uahurtado", llm) as rig:
        await rig.driver.start_session(init={"url": PSICO})
        turn = await rig.driver.user_says("Dime el precio.")
        assert "doscientos setenta y siete mil cuatrocientos cincuenta y seis pesos" in turn.text
        assert "once u efe" in turn.text
        assert "$" not in turn.text
        await rig.driver.user_says("Gracias.")
        seen = _texts(llm.captured_contents[-1])
        assert "u efe" not in seen


def test_his_lines_for_a_move_exist_in_both_languages() -> None:
    for line, said in _LANDED.items():
        assert set(said) == {"en", "es"}, line
        assert all(s.strip() for s in said.values()), line


def test_his_own_spanish_lines_are_latin_american() -> None:
    lines = [
        *(said["es"] for said in _LANDED.values()),
        uah._INTRO["es"],
        uah._GREETING["es"],
        *(opener["es"] for _, opener in uah._OPENERS),
        TOGGLE_CONFIRM["es"],
    ]
    for line in lines:
        assert spain_words(line, habits=True) == [], line


@pytest.mark.parametrize(
    ("written", "said"),
    [
        ("01 octubre 2026", "1 de octubre de 2026"),
        ("31-03-2027", "31 de marzo de 2027"),
        ("20270402", "2 de abril de 2027"),
    ],
)
def test_dates_as_the_api_and_the_page_write_them_are_read(written: str, said: str) -> None:
    from voqalize_demos._loaded.uahurtado.admission import date_said

    assert date_said(written, "es") == said
