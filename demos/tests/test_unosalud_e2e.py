"""Javier, Uno Salud Dental's voice guide, end to end over the wire — no network, no LLM key.

The real ``UnoSaludBrain`` on a real ``brain_server`` socket, driven by the
conformance ``VoqalizeDriver``, with only the model scripted. The knowledge is
the committed one: it is built offline from saved pages, so it does not move
under a test.

What this demo earns that others do not:

**Spanish first**, as Clini: the call opens in Spanish and moves both legs to
English for the toggle or for English heard.

**The booking starts with the visitor.** The RUT, the terms and the captcha
are theirs; he opens the booking, says why, and keeps what they chose (motivo,
clinic, day) until the booking reaches those steps, then takes them. He reads
the hours the booking lists, refuses one it does not, never carries a RUT, and
leaves "Registrarse", "Confirmar cita" and every ENVIAR to them.

**The screen follows his voice**, by keys of the anchor catalogue the extension
bundles.

Run: ``cd demos && uv run pytest tests/test_unosalud_e2e.py``
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import (
    ScriptedOpenAI,
    call,
    input_texts,
    reply,
    reply_and_call,
    tool_results_of,
)

from ._harness import _configs, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.unosalud import brain as unosalud  # noqa: E402
from voqalize_demos._loaded.unosalud.brain import (  # noqa: E402
    _IDLE_MS,
    _TALK_THROUGH_MS,
    TOGGLE_CONFIRM,
    greeting,
    language_of,
)

ORTO = "/especialidades/ortodoncia/"
HOME = {
    "url": "https://www.unosalud.cl/",
    "path": "/",
    "title": "Clínica Dental Odontológica | Uno Salud Dental",
    "kind": "home",
    "anchors": ["home_especialidades", "home_clinicas"],
    "faqs": [],
    "form": "none",
}
BOOKING = {
    "url": "https://www.unosalud.cl/agenda-tu-hora/",
    "path": "/agenda-tu-hora/",
    "title": "Agenda tu hora",
    "kind": "booking",
    "form": "booking",
}
#: A day far from today, and its hours.
DAY = "2030-03-04"


@pytest.fixture(autouse=True)
def _quiet_nods(monkeypatch: pytest.MonkeyPatch) -> None:
    """He never nods unless a test asks him to: a nod is a unit of its own."""
    monkeypatch.setattr(unosalud, "ACK_RATE", 0.0)


def _every(items: list[Any], name: str) -> list[str]:
    return tool_results_of(items, name)


def _texts(items: list[Any]) -> str:
    return input_texts(items)


def _llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            "Hola, ¿cómo estás?": reply("Muy bien. ¿En qué te ayudo hoy?"),
            "How much are the braces for me?": reply(
                "{show: ortodoncia_precios} Metal braces start at three hundred eighty-three "
                "thousand five hundred pesos."
            ),
            "¿Cuánto cuestan los brackets?": reply(
                "{show: ortodoncia_precios} Hay tres tipos. {show: ortodoncia_tab_metalicos} Los "
                "metálicos parten en trescientos ochenta y tres mil quinientos pesos. "
                "{show: ortodoncia_inventado} Eso es todo. {faq: faq_ortodoncia_3} Y aquí está "
                "la pregunta."
            ),
            "¿Atienden urgencias?": reply("Sí, en todas las clínicas."),
            "¿Tienen clínica en Providencia?": [
                call("find_clinic", args={"query": "Providencia"}),
                reply(
                    "{page: /clinicas/}{show: clinicas_manuel_montt} Sí, en Manuel Montt "
                    "doscientos diecisiete."
                ),
            ],
            "Quiero agendar una limpieza.": reply_and_call(
                "Te abro la reserva.", "open_booking", args={}
            ),
            "Quiero la promoción de ortodoncia.": reply_and_call(
                "Te abro la reserva con la promoción.",
                "open_booking",
                args={"promo": "ortodoncia_oct"},
            ),
            "En Manuel Montt, para una limpieza.": reply_and_call(
                "Perfecto, lo marco apenas puedas.",
                "booking_pick",
                args={"motivo": 14, "clinic": "manuel_montt"},
            ),
            "El lunes cuatro.": reply_and_call(
                "Te marco el lunes.", "booking_pick", args={"date": DAY}
            ),
            "A las nueve de la noche.": reply_and_call(
                "Veamos.", "booking_pick", args={"time": "21:00"}
            ),
            "A las diez y media.": reply_and_call(
                "Te marco las diez y media.", "booking_pick", args={"time": "10:30"}
            ),
            "¿Qué días hay?": 2
            * [reply_and_call("Reviso los próximos días.", "booking_scan", args={"days": 3})],
            "Soy Ana Pérez Soto, mi celular es nueve uno dos tres cuatro cinco seis siete ocho.": 2
            * [
                reply_and_call(
                    "Te anoto.",
                    "fill_booking_patient",
                    # The model wrote a RUT it should not have: it never reaches the page.
                    args={
                        "nombre": "Ana",
                        "paterno": "Pérez",
                        "materno": "Soto",
                        "phone": "+56 9 1234 5678",
                        "rut": "12.345.678-5",
                    },
                )
            ],
            "my phone is eight one four seven five one four one seven nine": reply_and_call(
                # Reshaped to look Chilean: refused, never sent.
                "Adding it.",
                "fill_booking_patient",
                args={"phone": "914751417"},
            ),
            "Prefiero que me llamen. Soy Juan Rojas, juan@correo.cl, 912345678, Ñuñoa, Santiago.": (
                reply_and_call(
                    "Te lo completo.",
                    "fill_callback_form",
                    args={
                        "nombre": "Juan",
                        "apellidos": "Rojas",
                        "email": " Juan@Correo.cl ",
                        "phone": "912345678",
                        "region": "Santiago",
                        "comuna": "Ñuñoa",
                    },
                )
            ),
            "Somos una empresa de 120 personas, Acme, yo soy Carla de RRHH.": reply_and_call(
                "Te lo completo.",
                "fill_company_form",
                args={
                    "nombre": "Carla",
                    "empresa": "Acme",
                    "cargo": "RRHH",
                    "trabajadores": 120,
                    "region": "Región Metropolitana",
                },
            ),
            "¿Cómo llego a Moneda?": reply_and_call(
                "Te abro el mapa.", "open_link", args={"clinic": "moneda"}
            ),
            "¿Puedes hablar en inglés?": reply_and_call(
                "Sure, let's continue in English.", "set_language", args={"language": "en"}
            ),
            "Can I speak in English?": reply_and_call(
                "Sure, let's continue in English.", "booking_pick", args={"motivo": 14}
            ),
            # The page's reports, talked through in the quiet spell.
            "first step, and its RUT field is ringed": reply(
                "Escribe tu RUT, marca los términos y No soy un robot, y presiona Continuar."
            ),
            "The booking says this patient already has an hour booked": reply(
                "Ya tienes una hora. Llama al seis cero cero, siete cero siete, uno cero uno cero."
            ),
            "shows the hours for the selected day": reply(
                "El lunes hay a las nueve, a las diez y media y a las once. ¿Cuál prefieres?"
            ),
            "read the next open days": reply("Hay hora el lunes y el martes. ¿Cuál prefieres?"),
            "shows the review": reply("Quedó lista para confirmar. Presiona Confirmar cita tú."),
            "The page answered what you sent it": reply("La reserva no pudo marcar eso."),
            "Sigamos.": reply("Claro, sigamos."),
        }
    )


async def _page(rig: object, event: str, payload: dict[str, object]) -> None:
    await rig.driver.send_ui_event(event, payload)  # type: ignore[attr-defined]
    await asyncio.sleep(0.1)


def _idle_windows(rig: object) -> list[int | None]:
    return [c.idle.timeout_ms for c in _configs(rig) if c.idle is not None]  # type: ignore[arg-type]


def _commands(rig: object, name: str) -> list[dict[str, Any]]:
    return [
        c["payload"]
        for c in rig.driver.ui_commands  # type: ignore[attr-defined]
        if c.get("command") == name
    ]


def _state(step: str, **fields: object) -> dict[str, object]:
    return {"step": step, **fields}


# ─── Voice and language ────────────────────────────────────────────────────────


async def test_the_greeting_is_spanish_and_the_voice_reaches_the_wire() -> None:
    async with demo("unosalud", _llm()) as rig:
        opener = await rig.driver.start_session(init={"surface": "unosalud-ext", "path": "/"})
        check_greeting(rig, opener)
        assert opener is not None
        assert opener.text == greeting("/", "es")
        assert opener.text.startswith("Hola, soy Javier, tu guía de voz de Uno Salud Dental.")
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _idle_windows(rig) == [_IDLE_MS]


async def test_the_toggle_moves_both_legs_to_english_and_confirms() -> None:
    async with demo("unosalud", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(rig, "language_requested", {"language": "en"})
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert rig.command("language_changed") == {"language": "en"}
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert turn.text == TOGGLE_CONFIRM["en"]


async def test_a_call_started_in_english_greets_in_english() -> None:
    async with demo("unosalud", _llm()) as rig:
        opener = await rig.driver.start_session(init={"path": ORTO, "lang": "en"})
        assert opener is not None and opener.text == greeting(ORTO, "en")
        assert opener.text.startswith("Hi, I'm Javier, Uno Salud Dental's voice guide.")
        check_voice_pair(rig, voice="omnivoice/javier", language="en")


async def test_english_heard_moves_the_call_and_spanish_brings_it_back() -> None:
    async with demo("unosalud", _llm()) as rig:
        await rig.driver.start_session(init={"path": ORTO})
        turn = await rig.driver.user_says("How much are the braces for me?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        await rig.driver.user_says("Hola, ¿cómo estás?")
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _commands(rig, "language_changed") == [{"language": "en"}, {"language": "es"}]


async def test_asking_for_english_switches_by_set_language() -> None:
    async with demo("unosalud", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("¿Puedes hablar en inglés?")
        await asyncio.sleep(0.1)
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert rig.command("language_changed") == {"language": "en"}
        # Asked about the call, the booking is not touched.
        await rig.driver.user_says("Can I speak in English?")
        assert "booking_pick" not in rig.actions()


@pytest.mark.parametrize(
    ("text", "sure", "lang"),
    [
        ("¿Cuánto cuesta un implante?", True, "es"),
        ("Me duele una muela", True, "es"),
        ("Hola", True, None),
        ("Fonasa", True, None),
        ("How much is a dental implant for me?", True, "en"),
        ("Claro.", False, "es"),
        ("{show: ortodoncia_precios} It's about ninety thousand pesos.", False, "en"),
    ],
)
def test_the_language_a_line_is_in(text: str, sure: bool, lang: str | None) -> None:
    assert language_of(text, sure=sure) == lang


@pytest.mark.parametrize(
    ("path", "words"),
    [
        ("/especialidades/ortodoncia/", "brackets"),
        ("/especialidades/implantes-dentales/", "implante"),
        ("/clinicas/", "comuna"),
        ("/urgencias/", "atiendan pronto"),
        ("/agenda-tu-hora/", "reserva"),
        ("/landing/convenio-empresa/", "empresas"),
        ("/", "agendar tu hora"),
    ],
)
def test_the_opener_follows_the_page(path: str, words: str) -> None:
    line = greeting(path, "es")
    assert line.startswith("Hola, soy Javier")
    assert words in line, line
    assert greeting(path, "en").startswith("Hi, I'm Javier")


# ─── Cues ──────────────────────────────────────────────────────────────────────

NONE: dict[str, object] = {"path": "", "anchor": "", "text": "", "faq": "", "lead": None}


async def test_cues_name_places_by_key_and_an_unknown_key_is_dropped() -> None:
    async with demo("unosalud", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(rig, "page_changed", HOME)
        turn = await rig.driver.user_says("¿Cuánto cuestan los brackets?")
        check_turn(rig, turn)
        assert "{" not in turn.text and "}" not in turn.text
        cues = _commands(rig, "cue")
        # The page they asked about, opened while he thinks; the price block
        # and the metal tab on it; the invented key dropped; the FAQ there.
        assert cues[0] == {**NONE, "at": "", "word": 0, "path": ORTO, "lead": "now"}
        assert {
            **NONE,
            "at": "hay tres tipos",
            "word": 0,
            "path": ORTO,
            "anchor": "ortodoncia_precios",
        } in cues
        assert any(c["anchor"] == "ortodoncia_tab_metalicos" for c in cues)
        assert not any("inventado" in str(c) for c in cues)
        assert any(c["faq"] == "faq_ortodoncia_3" for c in cues)


async def test_what_they_asked_about_is_shown_when_his_reply_forgets_to() -> None:
    async with demo("unosalud", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("¿Atienden urgencias?")
        assert _commands(rig, "cue")[0] == {
            **NONE,
            "at": "",
            "word": 0,
            "path": "/urgencias/",
            "lead": "now",
        }


async def test_a_clinic_is_found_and_its_row_shown() -> None:
    llm = _llm()
    async with demo("unosalud", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Tienen clínica en Providencia?")
        check_turn(rig, turn)
        (found,) = _every(llm.captured_inputs[-1], "find_clinic")
        assert "Manuel Montt (key manuel_montt): Av. Manuel Montt #217, Providencia" in found
        assert "In the booking: MANUEL MONTT (METRO M. MONTT)" in found
        cues = _commands(rig, "cue")
        assert cues[0]["path"] == "/clinicas/"
        assert any(c["anchor"] == "clinicas_manuel_montt" for c in cues)


async def test_a_clinic_page_reports_its_hours_and_they_reach_him() -> None:
    llm = _llm()
    async with demo("unosalud", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(
            rig,
            "page_changed",
            {
                "path": "/clinicas/teatinos/",
                "title": "Dentistas en Teatinos",
                "kind": "clinic",
                "anchors": ["clinica_horario", "clinica_mapa"],
                "clinic": {
                    "name": "Teatinos",
                    "address": "Teatinos #333",
                    "hours": "Lunes a viernes: 9:00 a 19:00 hrs.",
                    "references": "Metro La Moneda",
                    "maps_url": "https://www.google.com/maps/dir/?api=1&destination=1,2",
                },
            },
        )
        await rig.driver.user_says("Sigamos.")
        seen = _texts(llm.captured_inputs[-1])
        assert "Hours, as its page shows them: Lunes a viernes: 9:00 a 19:00 hrs." in seen


async def test_a_clinic_map_opens_from_the_table_only() -> None:
    async with demo("unosalud", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("¿Cómo llego a Moneda?")
        (opened,) = _commands(rig, "open_link")
        assert opened["url"].startswith("https://www.google.com/maps/dir/?api=1&destination=")


# ─── The booking ───────────────────────────────────────────────────────────────


async def test_the_booking_opens_and_its_first_step_is_explained_as_theirs() -> None:
    llm = _llm()
    async with demo("unosalud", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("Quiero agendar una limpieza.")
        check_turn(rig, turn)
        assert rig.command("open_booking") == {"promo": ""}
        # No site page moved under the booking it opened.
        assert _commands(rig, "cue") == []
        await _page(rig, "page_changed", BOOKING)
        await _page(rig, "booking_state", _state("getPAC"))
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "No soy un robot" in turn.text
        seen = _texts(llm.captured_inputs[-1])
        assert "the RUT identifies the patient's clinical record" in seen


async def test_a_promotion_carries_its_code_into_the_booking() -> None:
    llm = _llm()
    async with demo("unosalud", llm) as rig:
        await rig.driver.start_session(init={"path": "/promociones/"})
        await rig.driver.user_says("Quiero la promoción de ortodoncia.")
        assert rig.command("open_booking") == {"promo": "ortodonciaoctnov26"}


async def test_choices_before_the_rut_are_kept_and_taken_at_their_step() -> None:
    llm = _llm()
    async with demo("unosalud", llm) as rig:
        await rig.driver.start_session(init={"path": "/agenda-tu-hora/"})
        await _page(rig, "page_changed", BOOKING)
        await _page(rig, "booking_state", _state("getPAC"))
        await rig.driver.user_says("En Manuel Montt, para una limpieza.")
        assert "booking_pick" not in rig.actions()
        await rig.driver.user_says("Sigamos.")
        (kept,) = _every(llm.captured_inputs[-1], "booking_pick")
        assert kept.startswith("Kept, not sent yet: the booking is still at its first step")
        # The visitor typed their RUT and continued; a known patient confirms.
        await _page(rig, "booking_state", _state("getPAC", rut_entered=True))
        await _page(rig, "booking_state", _state("getMRes"))
        assert _commands(rig, "booking_pick") == [
            {
                "motivo": 14,
                "region": "REGIÓN METROPOLITANA",
                "comuna": "PROVIDENCIA",
                "sucursal": "52",
                "date": "",
                "time": "",
            }
        ]
        # The RUT never travels.
        assert "rut" not in str(rig.driver.ui_commands).lower().replace("rut_entered", "")  # type: ignore[attr-defined]


async def test_a_patient_with_an_hour_already_is_a_dead_end_said_kindly() -> None:
    llm = _llm()
    async with demo("unosalud", llm) as rig:
        await rig.driver.start_session(init={"path": "/agenda-tu-hora/"})
        await _page(rig, "page_changed", BOOKING)
        await _page(rig, "booking_state", _state("notsetRH"))
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "seis cero cero, siete cero siete" in turn.text
        assert "600 707 1010 digit by digit" in _texts(llm.captured_inputs[-1])


async def test_the_days_hours_are_read_and_only_a_listed_hour_is_picked() -> None:
    llm = _llm()
    async with demo("unosalud", llm) as rig:
        await rig.driver.start_session(init={"path": "/agenda-tu-hora/"})
        await _page(rig, "page_changed", BOOKING)
        await _page(rig, "booking_state", _state("getHor", motivo=14, sucursal="MANUEL MONTT"))
        await rig.driver.user_says("El lunes cuatro.")
        assert _commands(rig, "booking_pick")[-1]["date"] == DAY
        await _page(rig, "command_done", {"command": "booking_pick", "detail": "day selected"})
        await _page(
            rig,
            "booking_state",
            _state("getHor", date=DAY, slots=["09:00", "10:30", "11:00"], sucursal="MANUEL MONTT"),
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "a las diez y media" in turn.text
        seen = _texts(llm.captured_inputs[-1])
        assert (
            "Day selected: 2030-03-04 (lunes 4 de marzo). Its hours: 09:00; 10:30; 11:00." in seen
        )
        # An hour it does not list is refused, never sent.
        await rig.driver.user_says("A las nueve de la noche.")
        await rig.driver.user_says("Sigamos.")
        refused = _every(llm.captured_inputs[-1], "booking_pick")[-1]
        assert refused.startswith("Not picked: 21:00 is not an hour the booking lists")
        await rig.driver.user_says("A las diez y media.")
        assert _commands(rig, "booking_pick")[-1]["time"] == "10:30"
        # The review: "Confirmar cita" is theirs.
        await _page(
            rig,
            "booking_state",
            _state(
                "getDC",
                summary={
                    "fecha": "04-03-2030",
                    "hora": "10:30",
                    "direccion": "Av. Manuel Montt #217",
                },
            ),
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "Presiona Confirmar cita tú." in turn.text
        assert not {"confirm", "confirmar_cita", "submit"} & set(rig.actions())


async def test_the_next_open_days_are_scanned_and_talked_through() -> None:
    llm = _llm()
    async with demo("unosalud", llm) as rig:
        await rig.driver.start_session(init={"path": "/agenda-tu-hora/"})
        await rig.driver.user_says("¿Qué días hay?")
        assert "booking_scan" not in rig.actions()
        await _page(rig, "page_changed", BOOKING)
        await _page(rig, "booking_state", _state("getHor"))
        await rig.driver.user_says("¿Qué días hay?")
        assert rig.command("booking_scan") == {"from_date": "", "days": 3}
        await _page(rig, "command_done", {"command": "booking_scan", "detail": "3 days read"})
        await _page(
            rig,
            "booking_state",
            _state(
                "getHor",
                date=DAY,
                slots=["09:00"],
                days=[
                    {"date": DAY, "times": ["09:00"]},
                    {"date": "2030-03-05", "times": ["15:00"]},
                ],
            ),
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "lunes y el martes" in turn.text
        assert "Open days read: 2030-03-04 (lunes 4 de marzo): 09:00" in _texts(
            llm.captured_inputs[-1]
        )


async def test_the_patient_form_is_filled_without_a_rut_and_read_back() -> None:
    llm = _llm()
    said = "Soy Ana Pérez Soto, mi celular es nueve uno dos tres cuatro cinco seis siete ocho."
    async with demo("unosalud", llm) as rig:
        await rig.driver.start_session(init={"path": "/agenda-tu-hora/"})
        await _page(rig, "page_changed", BOOKING)
        # Before the RUT step is done there is no form to fill.
        await _page(rig, "booking_state", _state("getPAC"))
        await rig.driver.user_says(said)
        assert "fill_booking_patient" not in rig.actions()
        await _page(rig, "booking_state", _state("setPAC", rut_entered=True))
        await rig.driver.user_says(said)
        filled = rig.command("fill_booking_patient")
        assert filled == {
            "nombre": "Ana",
            "paterno": "Pérez",
            "materno": "Soto",
            "birth_date": "",
            "email": "",
            "phone": "912345678",
            "confirm_existing": False,
        }
        wire = str(rig.driver.ui_commands)  # type: ignore[attr-defined]
        assert "12.345.678-5" not in wire
        await rig.driver.user_says("Sigamos.")
        result = _every(llm.captured_inputs[-1], "fill_booking_patient")[-1]
        assert "The celular sent: 9 1 2 3 4 5 6 7 8; read it back digit by digit." in result
        assert "'Registrarse' is theirs to press" in result


async def test_a_phone_is_never_reshaped_to_fit() -> None:
    llm = _llm()
    async with demo("unosalud", llm) as rig:
        await rig.driver.start_session(init={"path": "/agenda-tu-hora/"})
        await _page(rig, "booking_state", _state("setPAC", rut_entered=True))
        await rig.driver.user_says("my phone is eight one four seven five one four one seven nine")
        await rig.driver.user_says("Sigamos.")
        (result,) = _every(llm.captured_inputs[-1], "fill_booking_patient")
        assert "is not what the visitor said (8 1 4 7 5 1 4 1 7 9)" in result
        assert all(c["phone"] == "" for c in _commands(rig, "fill_booking_patient"))


async def test_a_failed_booking_step_is_talked_through() -> None:
    llm = _llm()
    async with demo("unosalud", llm) as rig:
        await rig.driver.start_session(init={"path": "/agenda-tu-hora/"})
        await _page(rig, "booking_state", _state("getHor"))
        await rig.driver.user_says("El lunes cuatro.")
        await _page(rig, "command_failed", {"command": "booking_pick", "reason": "day disabled"})
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        seen = _texts(llm.captured_inputs[-1])
        assert "[Not done on the page (booking_pick): day disabled." in seen
        assert "The page answered what you sent it: booking_pick not done: day disabled." in seen
        assert _idle_windows(rig)[-1] == _IDLE_MS


# ─── The lead forms ────────────────────────────────────────────────────────────


async def test_the_callback_form_is_filled_and_the_rut_left_to_them() -> None:
    llm = _llm()
    async with demo("unosalud", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says(
            "Prefiero que me llamen. Soy Juan Rojas, juan@correo.cl, 912345678, Ñuñoa, Santiago."
        )
        assert rig.command("fill_callback_form") == {
            "form": "te_llamamos",
            "nombre": "Juan",
            "apellidos": "Rojas",
            "email": "juan@correo.cl",
            "phone": "912345678",
            "region": "Región Metropolitana",
            "comuna": "Ñuñoa",
        }
        await _page(
            rig,
            "callback_form_state",
            {"form": "te_llamamos", "filled": ["nombre", "email"], "missing": ["RUT"]},
        )
        await rig.driver.user_says("Sigamos.")
        seen = _texts(llm.captured_inputs[-1])
        assert "RUT not typed yet (theirs to type)" in seen
        assert (
            "ENVIAR is theirs to press."
            in _every(llm.captured_inputs[-1], "fill_callback_form")[-1]
        )


async def test_the_company_form_takes_the_forms_own_size_option() -> None:
    llm = _llm()
    async with demo("unosalud", llm) as rig:
        await rig.driver.start_session(init={"path": "/landing/convenio-empresa/"})
        await rig.driver.user_says("Somos una empresa de 120 personas, Acme, yo soy Carla de RRHH.")
        filled = rig.command("fill_company_form")
        assert filled["trabajadores"] == "Entre 200 a 500 trabajadores"
        assert filled["empresa"] == "Acme" and filled["region"] == "Región Metropolitana"
        await rig.driver.user_says("Sigamos.")
        result = _every(llm.captured_inputs[-1], "fill_company_form")[-1]
        assert "no option between 50 and 200 employees" in result


async def test_a_choice_for_a_step_already_behind_is_left_to_the_visitor() -> None:
    llm = _llm()
    async with demo("unosalud", llm) as rig:
        await rig.driver.start_session(init={"path": "/agenda-tu-hora/"})
        await _page(rig, "booking_state", _state("getHor", motivo=14, sucursal="MONEDA"))
        await rig.driver.user_says("En Manuel Montt, para una limpieza.")
        await rig.driver.user_says("Sigamos.")
        result = _every(llm.captured_inputs[-1], "booking_pick")[-1]
        assert result.startswith("Not picked: Not sent: the motivo and the clinic")
        assert "they press Volver themselves" in result
        assert "booking_pick" not in rig.actions()
