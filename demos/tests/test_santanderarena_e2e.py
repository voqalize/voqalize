"""Javier, Santander Arena's guide, end to end over the wire — no network, no LLM key.

The real ``SantanderBrain`` on a real ``brain_server`` socket, driven by the
conformance ``VoqalizeDriver``, with only the model scripted. The knowledge is a
small invented arena in the crawl's own shape, put in place of the committed
one, so no test depends on what the crawl found this week. Its shows are dated
from today, since the billboard leaves out what has already happened.

What this demo earns that others do not:

**Nothing on the page is invented.** A path, a heading, a card and an FAQ are
checked before they reach the page, and so is every ticket link he opens; the
assertion worth making is on what crossed the wire, and on what did not.

**The purchase is the visitor's.** Tickets, parking and VIP are opened on
Puntoticket, from the knowledge or from the button the live page reported, and
never from a link to anywhere else.

**Spanish first.** The site is Chilean, so the call opens in Spanish, follows a
visitor who speaks English, and holds a language they chose.

Run: ``cd demos && uv run pytest tests/test_santanderarena_e2e.py``
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from google.genai import types
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply, reply_and_call

from ._harness import _configs, check_greeting, check_turn, check_voice_pair, demo
from .test_sendpotion_latam import spain_words

discover()

from voqalize_demos._loaded.santanderarena import brain as santander  # noqa: E402
from voqalize_demos._loaded.santanderarena import knowledge as kb  # noqa: E402
from voqalize_demos._loaded.santanderarena.brain import (  # noqa: E402
    _IDLE_MS,
    _LANDED,
    _TALK_THROUGH_MS,
    TOGGLE_CONFIRM,
    asked_page,
    greeting,
    language_of,
    named_card,
)
from voqalize_demos._loaded.santanderarena.cues import CueParser, RawCue, words  # noqa: E402
from voqalize_demos._loaded.santanderarena.knowledge import (  # noqa: E402
    Card,
    Event,
    Faq,
    Knowledge,
    Page,
    Section,
    Ticket,
)

# ─── An invented arena ─────────────────────────────────────────────────────────

_MESES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

TODAY = date.today()
# Far enough apart that no two share a month, and far enough from today that
# Santiago's date and this machine's agree on which side of today each is.
SOON = TODAY + timedelta(days=12)
LATER = TODAY + timedelta(days=50)
LATEST = TODAY + timedelta(days=120)
PAST = TODAY - timedelta(days=10)


def _spoken(d: date) -> str:
    return f"{d.day} de {_MESES[d.month - 1]}"


CAMILO = "/nuestra-cartelera/conciertos/camilo"
NICKY = "/nuestra-cartelera/conciertos/nicky-jam"
OREJA = "/nuestra-cartelera/conciertos/la-oreja-de-van-gogh"
BUNKERS = "/nuestra-cartelera/conciertos/los-bunkers"
FAQS = "/preguntas-frecuentes"
PARKING = "/estacionamientos"

PT = "https://www.puntoticket.com"
CAMILO_TICKETS = f"{PT}/camilo-santander-arena"
CAMILO_PARKING = f"{PT}/estacionamiento-camilo"
CAMILO_VIP = f"{PT}/experiencias-vip-camilo"
NICKY_TICKETS = f"{PT}/nicky-jam"
PARKING_BOOKING = f"{PT}/estacionamiento-general"


def _event(name: str, path: str, when: date, category: str, **urls: str) -> Event:
    return Event(
        name=name,
        path=path,
        category=category,
        date_text=_spoken(when),
        time_text="21:00 hrs",
        date=when.isoformat(),
        summary=f"{name} en Santander Arena (inventado para las pruebas).",
        **urls,
    )


# Invented, in the crawl's shape: the names are the arena's kind, the facts ours.
SITE = Knowledge(
    l1="Santander Arena is a concert arena in Santiago (invented for tests).",
    topics={},
    pages={
        "/": Page(
            "/",
            "Inicio | Santander Arena",
            kind="home",
            sections=(
                Section("Próximos eventos", "Camilo Nicky Jam"),
                Section("Espacios para disfrutar en Santander Arena", "Bares Terrazas"),
            ),
        ),
        "/cartelera": Page(
            "/cartelera",
            "Cartelera | Santander Arena",
            sections=(Section("Cartelera"),),
            cards=(Card("CAMILO"), Card("NICKY JAM"), Card("LA OREJA DE VAN GOGH")),
        ),
        "/cupula-santander-arena": Page(
            "/cupula-santander-arena",
            "Cúpula | Santander Arena",
            sections=(Section("Cúpula Santander Arena", "Un espacio para fans."),),
        ),
        "/bares": Page(
            "/bares",
            "Bares | Santander Arena",
            sections=(Section("Bares", "Tragos antes del show."),),
            cards=(Card("Bar Central"), Card("Bar Terraza Sur")),
        ),
        "/experiencias": Page(
            "/experiencias",
            "Experiencias VIP | Santander Arena",
            sections=(Section("Experiencias VIP"), Section("Pre Show")),
            cards=(Card("Santander Suites"), Card("Box")),
        ),
        PARKING: Page(
            PARKING,
            "Estacionamientos | Santander Arena",
            sections=(Section("Estacionamientos", "Se compra por show."),),
            tickets=(Ticket("Ir a la reservación", PARKING_BOOKING, "Estacionamientos"),),
        ),
        FAQS: Page(
            FAQS,
            "Preguntas frecuentes | Santander Arena",
            sections=(Section("Preguntas frecuentes"),),
            faqs=(
                Faq("¿Pueden entrar menores de edad?", "Sí, con un adulto."),
                Faq("¿Puedo entrar con comida?", "No."),
            ),
        ),
        CAMILO: Page(
            CAMILO, "CAMILO | Santander Arena", kind="event", sections=(Section("CAMILO"),)
        ),
        NICKY: Page(
            NICKY, "NICKY JAM | Santander Arena", kind="event", sections=(Section("NICKY JAM"),)
        ),
    },
    events={
        CAMILO: _event(
            "CAMILO",
            CAMILO,
            SOON,
            "Pop latino",
            tickets_url=CAMILO_TICKETS,
            parking_url=CAMILO_PARKING,
            vip_url=CAMILO_VIP,
        ),
        NICKY: _event("NICKY JAM", NICKY, LATER, "Reggaetón", tickets_url=NICKY_TICKETS),
        OREJA: _event("LA OREJA DE VAN GOGH", OREJA, LATEST, "Pop rock"),
        BUNKERS: _event("LOS BUNKERS", BUNKERS, PAST, "Rock chileno", tickets_url=f"{PT}/x"),
    },
)


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every session reads the invented arena, and he never nods unless a test
    asks him to: a nod is a unit of its own."""
    monkeypatch.setattr(kb, "KNOWLEDGE", SITE)
    monkeypatch.setattr(santander, "ACK_RATE", 0.0)
    yield


# ─── Reading the wire ──────────────────────────────────────────────────────────


def _results(contents: list[types.Content]) -> dict[str, str]:
    return {
        p.function_response.name or "": str((p.function_response.response or {})["result"])
        for c in contents
        for p in (c.parts or [])
        if p.function_response is not None
    }


def _texts(contents: list[types.Content]) -> str:
    return "\n".join(p.text or "" for c in contents for p in (c.parts or []))


async def _page(rig: object, event: str, payload: dict[str, object]) -> None:
    await rig.driver.send_ui_event(event, payload)  # type: ignore[attr-defined]
    # `on_rtvi` takes no floor and there is nothing to await: give it a moment.
    await asyncio.sleep(0.1)


def _idle_windows(rig: object) -> list[int | None]:
    return [c.idle.timeout_ms for c in _configs(rig) if c.idle is not None]  # type: ignore[arg-type]


def _language_changes(rig: object) -> list[object]:
    return [
        c["payload"]
        for c in rig.driver.ui_commands  # type: ignore[attr-defined]
        if c.get("command") == "language_changed"
    ]


def _commands(rig: object, name: str) -> list[dict[str, object]]:
    return [c["payload"] for c in rig.driver.ui_commands if c.get("command") == name]  # type: ignore[attr-defined]


def _cues(rig: object) -> list[dict[str, object]]:
    return _commands(rig, "cue")


NONE = {"path": None, "heading": None, "text": None, "faq": None}


def _page_changed(path: str, **fields: object) -> dict[str, object]:
    return {
        "url": f"https://www.santanderarena.cl{path}",
        "path": path,
        "title": "",
        "kind": "page",
        **fields,
    }


# ─── The script ────────────────────────────────────────────────────────────────


def _llm() -> ScriptedGemini:
    return ScriptedGemini(
        {
            # English heard: both legs move before he answers.
            "can you tell me what is on this weekend": reply(
                "{page: /cartelera} Camilo plays soon. Want me to open his page?"
            ),
            "¿Qué conciertos hay este mes?": reply(
                "{page: /cartelera} Camilo viene pronto. ¿Te abro su página?"
            ),
            # Cues: out of the speech, checked against the site, sent to the page.
            "Muéstrame la cartelera.": reply(
                "{page: /cartelera}{show: camilo} Camilo llega pronto. "
                "{page: /luna}{show: la cupula} Hay mucho más. "
                "{faq: menores de edad} Los menores entran con un adulto."
            ),
            "Muéstrame la cúpula.": reply(
                "{page: /cupula-santander-arena}{show: cupula} Es el corazón de los fans."
            ),
            "¿Qué bares hay?": reply(
                "{page: /bares}{show: bar central} El Bar Central queda junto a la cancha."
            ),
            # He forgot to show what they asked about: their page goes first.
            "¿Dónde puedo estacionar el auto?": reply(
                "Hay estacionamiento en el recinto. Se compra para cada show."
            ),
            "Where can I park my car?": reply(
                "There is parking at the arena. You buy it for each show."
            ),
            # Spanish heard with English chosen: he answers in English.
            "¿Dónde estaciono? Quiero saber el precio.": reply(
                "There is parking at the arena. It is sold for each show."
            ),
            "I am asking you in English now": reply("Claro, te sigo en español. ¿Qué buscas?"),
            "Tell me about Nicky Jam.": reply("He closes the year in style. Want his tickets?"),
            "Can you show me the bars?": reply("There are two bars inside. Want the first one?"),
            "¿Puedes hablar en inglés?": reply_and_call(
                "Sure, let's continue in English.", "set_language", request={"language": "en"}
            ),
            # Reads come back within the turn.
            "¿Cuándo viene Nicky Jam?": [
                call("find_events", request={"query": "Nicky Jam"}),
                reply("{page: /nuestra-cartelera/conciertos/nicky-jam} Viene pronto."),
            ],
            "¿Algo de rock?": [
                call("find_events", request={"query": "rock"}),
                reply("Hay un show de pop rock."),
            ],
            "¿Qué hay en el mes?": [
                call("find_events", request={"query": _MESES[LATER.month - 1]}),
                reply("Hay un show ese mes."),
            ],
            "¿Qué viene?": [call("find_events", request={"query": ""}), reply("Mucho.")],
            # Tickets, parking and VIP, on Puntoticket.
            "Quiero entradas para Camilo.": reply_and_call(
                "Te abrí los tickets.", "open_tickets", request={"event": "Camilo"}
            ),
            "Y el estacionamiento para Camilo.": reply_and_call(
                "Listo.", "open_tickets", request={"event": "CAMILO", "kind": "parking"}
            ),
            "Y la experiencia VIP de Camilo.": reply_and_call(
                "Listo.", "open_tickets", request={"event": CAMILO, "kind": "vip"}
            ),
            "Compra las de este show.": reply_and_call(
                "Te los abrí.", "open_tickets", request={"event": "Camilo"}
            ),
            "Quiero reservar el estacionamiento.": reply_and_call(
                "Te la abrí.", "open_tickets", request={"label": "Ir a la reservación"}
            ),
            "Entradas para Metallica.": reply_and_call(
                "Déjame ver.", "open_tickets", request={"event": "Metallica"}
            ),
            "Nicky Jam parking.": reply_and_call(
                "Let me see.", "open_tickets", request={"event": "Nicky Jam", "kind": "parking"}
            ),
            "Ábreme ese botón.": reply_and_call(
                "Déjame ver.", "open_tickets", request={"label": "Comprar tickets"}
            ),
            "¿Y entonces?": reply("Te cuento."),
            # Tabs.
            "Vuelve a la otra pestaña.": reply_and_call(
                "Ahí está.", "switch_tab", request={"tab_id": "11"}
            ),
            "Muéstrame la pestaña noventa.": reply_and_call(
                "Aquí.", "switch_tab", request={"tab_id": "90"}
            ),
            # A move with no words: the model is asked once more, tools off; a
            # second silence gets his written line.
            "Ábreme los tickets de Camilo.": [
                call("open_tickets", request={"event": "Camilo"}),
                reply("Te los abrí en otra pestaña. ¿Te muestro dónde estacionar?"),
            ],
            "Ábreme el VIP de Camilo.": [
                call("open_tickets", request={"event": "Camilo", "kind": "vip"}),
                reply(""),
            ],
            # A reply that only promises more says nothing: asked once more.
            "¿Y los food trucks?": [
                reply("Un momento."),
                reply("Hay food trucks en la explanada. ¿Te los muestro?"),
            ],
            # Spain's spelling, said as Latin America says it.
            "¿Hay vídeos del show?": reply("Sí, hay un vídeo del show en la página."),
        }
    )


# ─── Greeting and voice ────────────────────────────────────────────────────────


async def test_greeting_and_voice_reach_the_wire_in_spanish() -> None:
    """A written opener, and javier in Spanish on both legs before it."""
    async with demo("santanderarena", _llm()) as rig:
        opener = await rig.driver.start_session(init={"surface": "santander-ext", "path": "/"})
        check_greeting(rig, opener)
        assert opener is not None and opener.text == greeting("/", "es", SITE)
        assert opener.text.startswith("Hola, soy Javier")
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _idle_windows(rig) == [_IDLE_MS]
        assert _language_changes(rig) == []


async def test_the_opener_follows_the_page_and_names_the_show() -> None:
    async with demo("santanderarena", _llm()) as rig:
        opener = await rig.driver.start_session(init={"path": f"{CAMILO}/"})
        assert opener is not None
        assert opener.text == greeting(CAMILO, "es", SITE)
        assert "¿Te cuento sobre Camilo, o te ayudo" in opener.text
    async with demo("santanderarena", _llm()) as rig:
        opener = await rig.driver.start_session(init={"path": PARKING})
        assert opener is not None and "estacionar" in opener.text
    assert greeting(NICKY, "en", SITE).endswith(
        "Shall I tell you about Nicky Jam, or help you plan your night?"
    )


async def test_a_call_started_in_english_opens_in_english_and_holds() -> None:
    llm = _llm()
    async with demo("santanderarena", llm) as rig:
        opener = await rig.driver.start_session(init={"path": "/", "lang": "en"})
        check_greeting(rig, opener)
        assert opener is not None and opener.text == greeting("/", "en", SITE)
        assert opener.text.startswith("Hi, I'm Javier")
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        # Spanish heard, and the chosen English holds.
        turn = await rig.driver.user_says("¿Dónde estaciono? Quiero saber el precio.")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert _language_changes(rig) == []
        assert "The visitor chose English before the call" in _texts(llm.captured_contents[-1])


async def test_the_toggle_switches_both_legs_and_confirms_each_way() -> None:
    async with demo("santanderarena", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        # The language already spoken: nothing to do.
        await _page(rig, "language_requested", {"language": "es"})
        assert _language_changes(rig) == []
        await _page(rig, "language_requested", {"language": "en"})
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        # The widget's toggle is told at once, not left to guess from his voice.
        assert rig.command("language_changed") == {"language": "en"}
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert turn.text == TOGGLE_CONFIRM["en"]
        assert _idle_windows(rig)[-1] == _IDLE_MS
        await _page(rig, "language_requested", {"language": "es"})
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert turn.text == TOGGLE_CONFIRM["es"]
        assert _language_changes(rig) == [{"language": "en"}, {"language": "es"}]
        # Chosen on the toggle, it holds whatever they speak.
        turn = await rig.driver.user_says("I am asking you in English now, okay?")
        assert "en español" in turn.text
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _language_changes(rig) == [{"language": "en"}, {"language": "es"}]


async def test_english_heard_switches_before_he_answers_and_spanish_switches_back() -> None:
    async with demo("santanderarena", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("Hi, can you tell me what is on this weekend?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert rig.command("language_changed") == {"language": "en"}
        turn = await rig.driver.user_says("¿Qué conciertos hay este mes?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _language_changes(rig) == [{"language": "en"}, {"language": "es"}]


async def test_asking_for_english_switches_and_opens_no_page() -> None:
    async with demo("santanderarena", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Puedes hablar en inglés?")
        check_turn(rig, turn)
        assert "let's continue in English" in turn.text
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert _language_changes(rig) == [{"language": "en"}]
        assert _cues(rig) == []


@pytest.mark.parametrize(
    ("text", "sure", "lang"),
    [
        ("¿Puedes hablar en inglés?", True, "es"),
        ("Quiero ver los conciertos de noviembre", True, "es"),
        ("Hola", True, None),
        ("Can you show me the bars?", True, "en"),
        ("Camilo", True, None),
        ("Okay.", True, None),
        # His own first words are few: one of a language is enough.
        ("Claro.", False, "es"),
        ("Sure, here it is.", False, "en"),
        # A cue is the site's Spanish inside any reply: an English reply stays
        # English, and a Spanish one Spanish.
        ("{show: Espacios para disfrutar en Santander Arena} There are bars.", False, "en"),
        ("{page: /bares}{show: Bares} Los bares abren temprano.", False, "es"),
    ],
)
def test_the_language_a_line_is_in(text: str, sure: bool, lang: str | None) -> None:
    assert language_of(text, sure=sure) == lang


# ─── Cues ──────────────────────────────────────────────────────────────────────


async def test_cues_leave_the_speech_and_are_checked_against_the_site() -> None:
    async with demo("santanderarena", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("Muéstrame la cartelera.")
        check_turn(rig, turn)
        assert "{" not in turn.text and "}" not in turn.text
        assert "Camilo llega pronto." in turn.text
        # The page; a card in the site's own spelling; the invented page and
        # words the page does not have, dropped; an FAQ on another page, opened
        # there.
        assert _cues(rig) == [
            {**NONE, "at": "camilo llega pronto", "word": 0, "path": "/cartelera"},
            {
                **NONE,
                "at": "camilo llega pronto",
                "word": 0,
                "path": "/cartelera",
                "text": "CAMILO",
            },
            {
                **NONE,
                "at": "los menores entran",
                "word": 6,
                "path": FAQS,
                "faq": "¿Pueden entrar menores de edad?",
            },
        ]


async def test_a_heading_is_matched_without_its_accents_and_a_card_on_the_next_page() -> None:
    async with demo("santanderarena", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Muéstrame la cúpula.")
        cupula = "/cupula-santander-arena"
        assert _cues(rig) == [
            {**NONE, "at": "es el corazon", "word": 0, "path": cupula},
            {
                **NONE,
                "at": "es el corazon",
                "word": 0,
                "path": cupula,
                "heading": "Cúpula Santander Arena",
            },
        ]
        await rig.driver.user_says("¿Qué bares hay?")
        assert _cues(rig)[2:] == [
            {**NONE, "at": "el bar central", "word": 0, "path": "/bares"},
            {**NONE, "at": "el bar central", "word": 0, "path": "/bares", "text": "Bar Central"},
        ]


async def test_what_they_asked_about_is_shown_when_his_reply_forgets_to() -> None:
    async with demo("santanderarena", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Dónde puedo estacionar el auto?")
        check_turn(rig, turn)
        assert "{" not in turn.text
        assert _cues(rig) == [{**NONE, "at": "hay estacionamiento en", "word": 0, "path": PARKING}]
        # Nothing to add on the page they already have in front.
        await _page(rig, "page_changed", _page_changed(PARKING, headings=["Estacionamientos"]))
        await rig.driver.user_says("¿Dónde puedo estacionar el auto?")
        assert len(_cues(rig)) == 1
    # In English too, and a show they name opens that show's page.
    async with demo("santanderarena", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Where can I park my car?")
        assert _cues(rig) == [{**NONE, "at": "there is parking", "word": 0, "path": PARKING}]
        await rig.driver.user_says("Tell me about Nicky Jam.")
        assert _cues(rig)[1:] == [{**NONE, "at": "he closes the", "word": 0, "path": NICKY}]
        # "Show me" is no ask for the billboard: the bars are.
        await rig.driver.user_says("Can you show me the bars?")
        assert [c["path"] for c in _cues(rig)[2:]][:1] == ["/bares"]


def test_the_page_for_what_they_asked_about() -> None:
    for ask, path in (
        ("¿Dónde puedo estacionar?", PARKING),
        ("Where can I park?", PARKING),
        ("¿Qué conciertos hay?", "/cartelera"),
        ("What's coming up?", "/cartelera"),
        ("Muéstrame la cupula", "/cupula-santander-arena"),
        ("¿Cómo es la Cúpula?", "/cupula-santander-arena"),
        ("Tell me about the suites", "/santander-suites"),
        ("Where can I get a drink?", "/bares"),
        ("¿Hay food trucks?", "/food-trucks"),
        ("Tell me about Nicky Jam", NICKY),
        ("¿Cuándo viene la oreja de van gogh?", OREJA),
        # A specific page beats the billboard, which "show me" also names.
        ("Can you show me the bars?", "/bares"),
        ("Show me the terraces before the show", "/terrazas"),
        ("Tell me about the box", "/box"),
    ):
        assert asked_page(ask, SITE) == path, ask
    for ask in (
        "Go back to the other tab.",
        "Vuelve a la otra pestaña.",
        "Mm-hmm",
        "Sí, por favor.",
        # A request about the call's own language is not a page.
        "Can you speak English?",
        "¿Puedes hablar en inglés?",
        "Hablemos en español.",
        "Claro, seguimos en español.",
        "Sure, let's continue in English.",
    ):
        assert asked_page(ask, SITE) is None, ask


def test_a_sentence_names_a_card_on_the_page() -> None:
    cards = ["CAMILO", "NICKY JAM", "Bar Central", "Box", "Santander Suites"]
    assert named_card("Camilo llega el cinco.", cards) == "CAMILO"
    assert named_card("And Nicky Jam closes the year.", cards) == "NICKY JAM"
    assert named_card("El Bar Central está junto a la cancha.", cards) == "Bar Central"
    assert named_card("The Box seats ten.", cards) == "Box"
    # A one-word title only as a name, not as an ordinary word.
    assert named_card("Bring a box of tissues.", cards) is None
    assert named_card("Las Santander Suites son privadas.", cards) == "Santander Suites"
    assert named_card("Hay bares y terrazas.", cards) is None


# ─── Reads ─────────────────────────────────────────────────────────────────────


async def test_find_events_by_artist_genre_and_month() -> None:
    llm = _llm()
    async with demo("santanderarena", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("¿Cuándo viene Nicky Jam?")
        found = _results(llm.captured_contents[-1])["find_events"]
        assert found.startswith(f"- NICKY JAM — {_spoken(LATER)} / 21:00 hrs — path: {NICKY}")
        assert "can open: tickets" in found
        assert "CAMILO" not in found
        await rig.driver.user_says("¿Algo de rock?")
        found = _results(llm.captured_contents[-1])["find_events"]
        assert "LA OREJA DE VAN GOGH" in found
        assert "LOS BUNKERS" not in found  # Rock too, but past.
        await rig.driver.user_says("¿Qué hay en el mes?")
        found = _results(llm.captured_contents[-1])["find_events"]
        assert found.splitlines()[0].startswith("- NICKY JAM")
        assert "CAMILO" not in found and "OREJA" not in found


async def test_an_empty_query_lists_whats_coming_soonest_first() -> None:
    llm = _llm()
    async with demo("santanderarena", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("¿Qué viene?")
        found = _results(llm.captured_contents[-1])["find_events"]
        listed = [line.split(" — ")[0] for line in found.splitlines() if line.startswith("- ")]
        assert listed == ["- CAMILO", "- NICKY JAM", "- LA OREJA DE VAN GOGH"]
        # An empty query matched nothing because it asked for nothing.
        assert "No show matches" not in found
        assert "can open: tickets, parking, vip" in found.splitlines()[0]


def test_the_prompt_lists_only_whats_coming() -> None:
    prompt = santander._prompt(SITE, TODAY)
    events = prompt.split("# Events coming up")[1].split("# Site pages")[0]
    assert events.index("CAMILO") < events.index("NICKY JAM") < events.index("LA OREJA")
    assert "LOS BUNKERS" not in events
    # The site map leaves the shows' own pages to the events list.
    pages = prompt.split("# Site pages")[1]
    assert "/cartelera" in pages and CAMILO not in pages


# ─── Tickets ───────────────────────────────────────────────────────────────────


async def test_tickets_parking_and_vip_open_on_puntoticket() -> None:
    async with demo("santanderarena", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Quiero entradas para Camilo.")
        await rig.driver.user_says("Y el estacionamiento para Camilo.")
        await rig.driver.user_says("Y la experiencia VIP de Camilo.")
        assert _commands(rig, "open_tickets") == [
            {"url": CAMILO_TICKETS, "label": "Comprar tickets — Camilo"},
            {"url": CAMILO_PARKING, "label": "Comprar estacionamiento — Camilo"},
            {"url": CAMILO_VIP, "label": "Compra Experiencias VIP — Camilo"},
        ]


async def test_the_button_on_the_shows_page_in_front_wins() -> None:
    live = f"{PT}/camilo-santander-arena-nueva-fecha"
    async with demo("santanderarena", _llm()) as rig:
        await rig.driver.start_session(init={"path": CAMILO})
        await _page(
            rig,
            "page_changed",
            _page_changed(
                f"{CAMILO}/",
                kind="event",
                headings=["CAMILO"],
                tickets=[{"label": "Comprar tickets", "url": live, "near": "CAMILO"}],
            ),
        )
        await rig.driver.user_says("Compra las de este show.")
        assert rig.command("open_tickets") == {"url": live, "label": "Comprar tickets — Camilo"}
    # A reservation on the parking page: the button's words, on the page in front.
    async with demo("santanderarena", _llm()) as rig:
        await rig.driver.start_session(init={"path": PARKING})
        await _page(
            rig,
            "page_changed",
            _page_changed(
                PARKING,
                tickets=[
                    {
                        "label": "Ir a la reservación",
                        "url": PARKING_BOOKING,
                        "near": "Estacionamientos",
                    }
                ],
            ),
        )
        await rig.driver.user_says("Quiero reservar el estacionamiento.")
        assert rig.command("open_tickets") == {
            "url": PARKING_BOOKING,
            "label": "Ir a la reservación",
        }


async def test_an_unknown_show_or_a_link_off_puntoticket_is_refused() -> None:
    llm = _llm()
    async with demo("santanderarena", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Entradas para Metallica.")
        await rig.driver.user_says("Nicky Jam parking.")
        # A link the page reports to anywhere but Puntoticket is not opened.
        await _page(
            rig,
            "page_changed",
            _page_changed(
                "/bares",
                tickets=[{"label": "Comprar tickets", "url": "https://tickets.example/buy"}],
            ),
        )
        await rig.driver.user_says("Ábreme ese botón.")
        await rig.driver.user_says("¿Y entonces?")
        assert "open_tickets" not in rig.actions()
        said = _texts(llm.captured_contents[-1])
        results = [
            str((p.function_response.response or {})["result"])
            for c in llm.captured_contents[-1]
            for p in (c.parts or [])
            if p.function_response is not None
        ]
        assert results[0].startswith("Not opened: no show 'Metallica'. Shows: CAMILO, NICKY JAM")
        assert results[1].startswith(
            "Not opened: NICKY JAM's page has no 'Comprar estacionamiento'"
        )
        assert results[2] == (
            "Not opened: say which show. The page in front has these ticket links: Comprar tickets."
        )
        assert "tickets.example" not in said


# ─── Tabs and silent turns ─────────────────────────────────────────────────────


async def test_tabs_are_read_in_and_switching_is_checked() -> None:
    llm = _llm()
    async with demo("santanderarena", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(
            rig,
            "tabs_changed",
            {
                "tabs": [
                    {
                        "tab_id": "11",
                        "url": "https://www.santanderarena.cl/bares",
                        "title": "Bares",
                    },
                    {
                        "tab_id": "12",
                        "url": f"https://www.santanderarena.cl{CAMILO}",
                        "title": "CAMILO",
                    },
                ],
                "active": "12",
            },
        )
        await rig.driver.user_says("Vuelve a la otra pestaña.")
        assert "11: Bares; 12: CAMILO (in front)" in _texts(llm.captured_contents[-1])
        assert rig.command("focus_tab") == {"tab_id": "11"}
        await rig.driver.user_says("Muéstrame la pestaña noventa.")
        assert rig.actions().count("focus_tab") == 1
        # Neither ask about a tab opened a page.
        assert _cues(rig) == []


async def test_a_silent_move_is_talked_about_or_gets_his_line() -> None:
    async with demo("santanderarena", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("Ábreme los tickets de Camilo.")
        check_turn(rig, turn)
        assert "¿Te muestro dónde estacionar?" in turn.text
        turn = await rig.driver.user_says("Ábreme el VIP de Camilo.")
        check_turn(rig, turn)
        assert turn.text.strip() == _LANDED["tickets"]["es"]
        assert [c["url"] for c in _commands(rig, "open_tickets")] == [CAMILO_TICKETS, CAMILO_VIP]


async def test_a_reply_that_only_promises_is_asked_once_more() -> None:
    """Explora's dev call ed9846d5: his whole reply was "One moment.", and the
    visitor sat in silence."""
    async with demo("santanderarena", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/food-trucks"})
        turn = await rig.driver.user_says("¿Y los food trucks?")
        check_turn(rig, turn)
        assert "Hay food trucks en la explanada" in turn.text


async def test_a_missed_cue_is_noted_quietly() -> None:
    llm = _llm()
    async with demo("santanderarena", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(rig, "command_failed", {"command": "cue", "reason": "no heading X"})
        await rig.driver.user_says("¿Y entonces?")
        seen = _texts(llm.captured_contents[-1])
        assert "A screen cue of yours did not land (no heading X)" in seen
        assert "Tell the visitor plainly" not in seen


# ─── Latin American Spanish ────────────────────────────────────────────────────


def test_his_lines_for_a_move_exist_in_both_languages() -> None:
    for kind, lines in _LANDED.items():
        assert set(lines) == {"en", "es"}, kind
        assert all(line.strip() for line in lines.values()), kind
    assert set(TOGGLE_CONFIRM) == {"en", "es"}


def _his_spanish_lines() -> list[str]:
    """Every Spanish line the brain writes itself, rather than the model."""
    lines = [
        TOGGLE_CONFIRM["es"],
        santander._INTRO["es"],
        santander._GREETING["es"],
        santander._EVENT_GREETING["es"],
        *(opener["es"] for _, opener in santander._OPENERS),
        *(line["es"] for line in _LANDED.values()),
        *(line for kind in santander._ACK_LINES["es"].values() for line in kind),
        *santander._ACK_HOLD["es"],
        santander._ACK_SORRY["es"],
    ]
    pages = ["/", "/cartelera", "/experiencias", "/santander-suites", PARKING, FAQS, CAMILO]
    return lines + [greeting(path, "es", SITE) for path in pages]


@pytest.mark.parametrize("line", _his_spanish_lines())
def test_his_own_spanish_lines_are_latin_american(line: str) -> None:
    assert spain_words(line, habits=True) == [], line


async def test_spains_video_is_said_as_latin_america_says_it() -> None:
    assert santander.latin_american("Un vídeo y dos Vídeos.") == "Un video y dos Videos."
    async with demo("santanderarena", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Hay vídeos del show?")
        assert "hay un video del show" in turn.text and "vídeo" not in turn.text


def test_the_prompt_asks_for_latin_american_spanish() -> None:
    prompt = santander._prompt(SITE, TODAY)
    for rule in (
        "neutral Latin American Spanish",
        'never "vosotros"',
        '"celular", never "móvil"',
        '"está bien" or "perfecto", never "vale"',
        '"¿Qué día te queda bien?", not "te viene bien"',
        "the simple past",
    ):
        assert rule in prompt, rule


# ─── The cue parser, in Spanish ────────────────────────────────────────────────


def _run(*chunks: str) -> tuple[str, list[RawCue]]:
    p = CueParser()
    spoken = ""
    cues: list[RawCue] = []
    for c in chunks:
        text, got = p.feed(c)
        spoken += text
        cues += got
    text, got = p.flush()
    return spoken + text, cues + got


def test_words_fold_accents_as_the_page_hears_them() -> None:
    assert words(f"¿Está aquí la Cúpula? Ñandú{chr(0x2019)}s") == [
        "esta",
        "aqui",
        "la",
        "cupula",
        "nandu's",
    ]


def test_spanish_cues_leave_the_speech_and_anchor_without_accents() -> None:
    spoken, cues = _run(
        "{page: /cupula-santander-arena}{show: Cúpula Santander Arena} Está en el cen",
        "tro del arena. {faq: ¿Pueden entrar menores de edad?} Sí, con un adulto.",
    )
    assert spoken == " Está en el centro del arena. Sí, con un adulto."
    assert [(c.kind, c.value, c.at, c.word) for c in cues] == [
        ("page", "/cupula-santander-arena", "esta en el", 0),
        ("show", "Cúpula Santander Arena", "esta en el", 0),
        ("faq", "¿Pueden entrar menores de edad?", "si con un", 6),
    ]
