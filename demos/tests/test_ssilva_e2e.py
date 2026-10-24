"""Javier, Ssilva's guide, end to end over the wire — no network, no LLM key.

The real ``SsilvaBrain`` on a real ``brain_server`` socket, driven by the
conformance ``VoqalizeDriver``, with only the model scripted. The knowledge is a
small site in the crawl's own shape, put in place of the committed one, so no
test depends on what the crawl found this week.

What this demo earns that others do not:

**Nothing on the page is invented.** A path, a section, a typology and a
project to ring on the list are checked before they reach the page; the
assertion worth making is on what crossed the wire, and on what did not.

**The quote form is the visitor's.** It fills as they talk, maps what they say
to the form's own options, never presses Enviar, and what the form reports after
his turn is talked through in a short quiet spell.

**Spanish first.** The call opens in Spanish; English heard, the toggle and
``set_language`` move both legs together.

Run: ``cd demos && uv run pytest tests/test_ssilva_e2e.py``
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

from voqalize_demos._loaded.ssilva import brain as ssilva  # noqa: E402
from voqalize_demos._loaded.ssilva import knowledge as kb  # noqa: E402
from voqalize_demos._loaded.ssilva.brain import (  # noqa: E402
    _IDLE_MS,
    _TALK_THROUGH_MS,
    TOGGLE_CONFIRM,
    greeting,
)
from voqalize_demos._loaded.ssilva.knowledge import (  # noqa: E402
    Knowledge,
    Page,
    Project,
    Section,
)


def _project_page(path: str, title: str, slug: str, *keys: str) -> Page:
    return Page(
        path,
        title,
        kind="project",
        project=slug,
        sections=(Section("MÁS VERDE PARA TU VIDA"), *(Section(k.capitalize(), k) for k in keys)),
    )


# A small site in the crawl's shape.
SITE = Knowledge(
    l1="Ssilva sells projects in Chile (a test site).",
    topics={},
    pages={
        "/": Page("/", "Inicio", kind="home", sections=(Section("Somos Ssilva"),)),
        "/proyectos": Page(
            "/proyectos",
            "Proyectos",
            kind="projects",
            sections=(Section("ENCUENTRA TU NUEVA VIVIENDA"),),
        ),
        "/centro-de-negocios": Page(
            "/centro-de-negocios",
            "Centro de Negocios",
            sections=(
                Section(
                    "Nuestro Proceso", text="Evaluación, asesoría financiera, crédito hipotecario."
                ),
                Section(
                    "¡Beneficios y promociones!",
                    text="Desde el 0% de pie y hasta en 60 cuotas. Arriendo garantizado 20 meses.",
                ),
            ),
        ),
        "/estocolmo": _project_page(
            "/estocolmo",
            "Estocolmo",
            "estocolmo",
            "galería",
            "tipologías",
            "amenidades",
            "estado",
            "contacto",
        ),
        "/canalbeagle": _project_page(
            "/canalbeagle",
            "Canal Beagle",
            "canal-beagle",
            "tipologías",
            "galería",
            "amenidades",
            "contacto",
        ),
        "/isla-picton": _project_page(
            "/isla-picton", "Isla Picton", "isla-picton", "galería", "tipologías"
        ),
        "/distrito-barroso": _project_page(
            "/distrito-barroso",
            "Distrito Barroso",
            "distrito-barroso",
            "galería",
            "tipologías",
            "amenidades",
        ),
    },
    projects={
        "estocolmo": Project(
            slug="estocolmo",
            name="Estocolmo",
            site_name="ESTOCOLMO",
            path="/estocolmo/",
            quote_path="/proyectos/cotizar/estocolmo/",
            comuna="Las Condes",
            region="metropolitana",
            tipos=("departamento",),
            desde_uf=13976,
            dormitorios=(2, 3),
            estado="Entrega inmediata",
            perfil=("Para vivir",),
            typologies=("2D | 3B", "3D | 3B"),
            lead_form=True,
        ),
        "canal-beagle": Project(
            slug="canal-beagle",
            name="Canal Beagle",
            site_name="CANAL BEAGLE",
            path="/canalbeagle/",
            quote_path="/proyectos/cotizar/canal-beagle/",
            comuna="Viña del Mar",
            region="valparaiso",
            tipos=("departamento",),
            desde_uf=3654,
            dormitorios=(2, 3),
            estado="Entrega inmediata",
            perfil=("Para invertir", "Para vivir", "Segunda vivienda"),
            typologies=("2D | 2B",),
            lead_form=True,
        ),
        "isla-picton": Project(
            slug="isla-picton",
            name="Isla Picton",
            site_name="ISLA PICTON",
            path="/isla-picton/",
            quote_path="/proyectos/cotizar/isla-picton/",
            comuna="Viña del Mar",
            region="valparaiso",
            tipos=("departamento",),
            desde_uf=2372,
            dormitorios=(1, 2),
            estado="En blanco",
            perfil=("Para invertir", "Para vivir"),
            typologies=("1D | 1B", "2D | 1B", "2D | 2B"),
            lead_form=True,
        ),
        "distrito-barroso": Project(
            slug="distrito-barroso",
            name="Distrito Barroso",
            site_name="DISTRITO BARROSO",
            path="/distrito-barroso/",
            quote_path="/proyectos/cotizar/distrito-barroso/",
            comuna="Santiago",
            region="metropolitana",
            tipos=("departamento",),
            desde_uf=2582,
            dormitorios=(1, 2),
            estado="En verde",
            perfil=("Para invertir", "Para vivir"),
            typologies=("1D | 1B", "2D | 1B", "2D | 2B", "2D | 2B MARIPOSA"),
            lead_form=True,
        ),
    },
    project_texts={"estocolmo": "# Estocolmo\n- Address: Estocolmo 661, Las Condes.\n"},
)

ESTOCOLMO_PAGE = {
    "url": "https://www.ssilva.cl/estocolmo/",
    "path": "/estocolmo/",
    "title": "ESTOCOLMO | SSilva",
    "kind": "project",
    "project": "Estocolmo",
    "headings": ["MÁS VERDE PARA TU VIDA", "TIPOLOGIAS QUE SE ADAPTAN A TUS NECESIDADES"],
    "sections": ["galería", "tipologías", "amenidades", "estado", "contacto", "formulario"],
    "typologies": ["2D | 3B", "3D | 3B"],
    "typology": "2D | 3B",
    "price": "Desde 13.976 UF",
    "status": "Entrega inmediata",
}
# Distrito Barroso as a visitor reading ssilva.cl through Chrome's translation
# sees it (dev call ec152777): the title and a typology label in English.
BARROSO_PAGE = {
    "url": "https://www.ssilva.cl/distrito-barroso/",
    "path": "/distrito-barroso/",
    "title": "BARROSO DISTRICT | SSilva",
    "kind": "project",
    "project": "BARROSO DISTRICT",
    "headings": ["THE NEW CITY CENTER", "Types that adapt to your needs"],
    "sections": ["galería", "tipologías", "formulario", "amenidades"],
    "typologies": ["1D | 1B", "2D | 1B", "2D | 2B", "2D | 2B BUTTERFLY"],
    "typology": "1D | 1B",
    "price": "Desde 2,582 UF",
    "status": "In Green",
    "photos": ["depto grande", "depto pequeno", "quincho", "cowork"],
    "amenity_photos": ["piscina", "gourmet"],
}
LIST_PAGE = {
    "url": "https://www.ssilva.cl/proyectos/?region=17",
    "path": "/proyectos/",
    "title": "Projects | SSilva",
    "kind": "projects",
    "headings": ["FIND YOUR NEW HOME"],
}
INGRESOS = [
    "Menos de $1.000.000",
    "Entre $1.000.000 a $1.200.000",
    "Entre $1.200.000 a $1.500.000",
    "Entre $1.500.000 a $1.800.000",
    "Más de $7.000.000",
]
PIES = ["No tengo ahorro", "Menos de $2.000.000", "Entre $2.000.000 a $5.000.000"]


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every session reads the small site, and he never nods unless a test asks
    him to: a nod is a unit of its own."""
    monkeypatch.setattr(kb, "KNOWLEDGE", SITE)
    monkeypatch.setattr(ssilva, "ACK_RATE", 0.0)
    yield


def _results(contents: list[types.Content]) -> dict[str, str]:
    return {
        p.function_response.name or "": str((p.function_response.response or {})["result"])
        for c in contents
        for p in (c.parts or [])
        if p.function_response is not None
    }


def _all_results(contents: list[types.Content], name: str) -> list[str]:
    """Every result of tool ``name`` in a request, oldest first."""
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
            # A project walked top to bottom: a page, a section, a typology, and
            # a section this page does not have, dropped.
            "Muéstrame Estocolmo.": reply(
                "{page: /estocolmo/} Te abro Estocolmo. {show: galería} Aquí ves las fotos. "
                "{plan: 2d|3b} Este tiene dos dormitorios y tres baños. {show: tour} "
                "Y tiene un recorrido. ¿Te muestro las amenidades?"
            ),
            # On the page: his words alone ring the part he describes.
            "¿Qué amenidades tiene?": reply(
                "Tiene mucho para compartir. Hay piscina, gimnasio y quincho en el edificio. "
                "¿Quieres ver las tipologías?"
            ),
            "¿Y el de tres dormitorios?": reply(
                "Es más amplio. El de tres dormitorios y tres baños es para familias grandes. "
                "¿Lo cotizamos?"
            ),
            # The visitor names a project; the reply forgets to open it.
            "Háblame de Canal Beagle.": reply("Está en Viña del Mar. Tiene entrega inmediata."),
            "Busco un departamento de dos dormitorios en Viña.": [
                call("find_projects", request={"comuna": "Viña", "dormitorios": 2}),
                reply_and_call(
                    "Hay dos en Viña del Mar. ¿Lo buscas para vivir o para invertir?",
                    "show_projects",
                    request={
                        "region": "valparaiso",
                        "highlight": ["isla picton", "Canal Beagle", "Torre Inventada"],
                    },
                ),
            ],
            "Quiero ver los de Las Condes.": reply_and_call(
                "Te muestro Las Condes.",
                "show_projects",
                request={"communes": ["las condes"], "property": "departamentos"},
            ),
            "Quiero cotizar.": reply_and_call(
                "{show: formulario} Perfecto, lo completamos juntos. ¿Me dices tu RUT y correo?",
                "fill_lead_form",
                request={"firstname": "Ana", "lastname": "Pérez Soto"},
            ),
            "Mi RUT es 12.345.678-5 y mi correo ana.perez@gmail.com": reply_and_call(
                "Anoté el correo ana punto pérez arroba gmail punto com. ¿Está bien?",
                "fill_lead_form",
                request={
                    "rut": "123456785",
                    "email": "Ana.Perez@gmail.com",
                    "motivo": "para vivir",
                },
            ),
            "Mi RUT es 12.345.678-9": reply_and_call(
                "Déjame revisarlo.", "fill_lead_form", request={"rut": "12.345.678-9"}
            ),
            "Mi celular es 9 1234 5678. Sigamos.": reply_and_call(
                "Pasamos al segundo paso.",
                "fill_lead_form",
                request={"phone": "9 1234 5678", "next_step": True, "ingreso": "un millón y medio"},
            ),
            "Step two of the quote form": reply(
                "Ya estamos en el segundo paso. ¿Qué tipología te interesa?"
            ),
            "Gano un millón y medio, y tengo tres millones ahorrados.": reply_and_call(
                "Lo dejé en el rango de un millón y medio. ¿Está bien?",
                "fill_lead_form",
                request={"ingreso": "1500000", "pie": "3 millones"},
            ),
            "pressed Enviar": reply("Gracias, Ana. Esta vista previa no lo envió."),
            "Quiero cotizar en la portada.": reply_and_call(
                "Abramos el proyecto primero.", "fill_lead_form", request={"firstname": "Ana"}
            ),
            # English heard: the call moves to English before he answers.
            "Hi, can you show me projects in Las Condes please?": reply(
                "There are three in Las Condes. Want to see them?"
            ),
            "¿Puedes hablar en inglés?": reply_and_call(
                "Sure, I'll speak English.", "set_language", request={"language": "en"}
            ),
            "Ábreme el tour.": reply_and_call("Te abro el recorrido.", "open_tour"),
            "Muéstrame la piscina.": reply_and_call(
                "Aquí están las fotos.", "show_photos", request={"which": "amenities", "index": 2}
            ),
            # Several projects, talked through as the list opens: each card is
            # rung as he names it, once the list his show_projects opens is up.
            "Busco para invertir en Santiago.": reply_and_call(
                "Hay dos que te sirven. Distrito Barroso está en Santiago centro. "
                "{show: Estocolmo} Estocolmo está en Las Condes. ¿Cuál te interesa?",
                "show_projects",
                request={"region": "metropolitana", "highlight": ["Distrito Barroso", "Estocolmo"]},
            ),
            # The same names with no list to ring them on: no card cue at all.
            "¿Cuáles están en Santiago?": reply("Distrito Barroso está en Santiago centro."),
            # On the list: his words alone ring the card he talks about.
            "¿Cuál me recomiendas?": reply(
                "Para invertir, Distrito Barroso. Está a pasos del metro. ¿Te lo abro?"
            ),
            # The floor plan, asked in English on a translated page.
            "Show me the floor plan of the butterfly one.": reply_and_call(
                "Here is the butterfly layout. "
                "This is the two-bedroom, one-bathroom one, for comparison.",
                "show_floor_plan",
                request={"typology": "2D | 2B MARIPOSA"},
            ),
            "Muéstrame las fotos en grande.": reply_and_call(
                "{photo: 1} Aquí ves el departamento grande. {photo: amenidades 2} Y esta es la "
                "zona gourmet. {photo: 9} Y una que no existe.",
                "show_photos",
                request={"which": "gallery", "index": 1, "fullscreen": True},
            ),
            "Pon una presentación.": reply_and_call(
                "Van pasando solas.", "slideshow", request={"play": True, "seconds": 30}
            ),
            "La siguiente.": reply_and_call("Esta es la siguiente.", "step_photo"),
            "Escríbeles por WhatsApp.": reply_and_call("Abro WhatsApp.", "open_whatsapp"),
            "¿Qué es Estocolmo?": [
                call("read_project", request={"name": "estocolmo"}),
                reply("Es un proyecto en Las Condes."),
            ],
            "Sigue.": reply("Claro, seguimos."),
            # A move with no words: the model is asked once more, tools off.
            "Ábreme WhatsApp.": [
                call("open_whatsapp"),
                reply("Ya está abierto. ¿Te ayudo con algo del proyecto?"),
            ],
            # A reply that only promises is asked again (Explora's dev call
            # ed9846d5: his whole reply was "One moment.").
            "¿Dónde queda?": [
                reply("Un momento."),
                reply("Queda en Las Condes, cerca del metro."),
            ],
        }
    )


async def _page(rig: object, event: str, payload: dict[str, object]) -> None:
    await rig.driver.send_ui_event(event, payload)  # type: ignore[attr-defined]
    # `on_rtvi` takes no floor and there is nothing to await: give it a moment.
    await asyncio.sleep(0.1)


def _idle_windows(rig: object) -> list[int | None]:
    return [c.idle.timeout_ms for c in _configs(rig) if c.idle is not None]  # type: ignore[arg-type]


def _cues(rig: object) -> list[dict[str, object]]:
    return [c["payload"] for c in rig.driver.ui_commands if c.get("command") == "cue"]  # type: ignore[attr-defined]


def _commands(rig: object, name: str) -> list[dict[str, object]]:
    return [c["payload"] for c in rig.driver.ui_commands if c.get("command") == name]  # type: ignore[attr-defined]


NONE = {
    "path": None,
    "heading": None,
    "text": None,
    "typology": None,
    "card": None,
    "photo": None,
    "photos": None,
}


async def test_greeting_opens_in_spanish_on_both_legs() -> None:
    async with demo("ssilva", _llm()) as rig:
        opener = await rig.driver.start_session(init={"path": "/"})
        check_greeting(rig, opener)
        assert opener is not None and opener.text == greeting("/", SITE, "es")
        assert opener.text.startswith("Hola, soy Javier")
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _idle_windows(rig) == [_IDLE_MS]


async def test_the_opener_names_the_project_and_its_price_in_words() -> None:
    async with demo("ssilva", _llm()) as rig:
        opener = await rig.driver.start_session(init={"path": "/estocolmo/"})
        assert opener is not None
        assert "Estocolmo" in opener.text
        assert "trece mil novecientas setenta y seis UF" in opener.text
    async with demo("ssilva", _llm()) as rig:
        opener = await rig.driver.start_session(init={"path": "/estocolmo/", "lang": "en"})
        assert opener is not None and opener.text.startswith("Hi, I'm Javier")
        assert "thirteen thousand nine hundred seventy-six UF" in opener.text
        check_voice_pair(rig, voice="omnivoice/javier", language="en")


async def test_a_walk_through_a_project_moves_the_page_with_his_voice() -> None:
    async with demo("ssilva", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        tools = {t.__name__ for t in rig.brain.tools}  # type: ignore[attr-defined]
        assert not tools & {"navigate", "show_section", "select_typology"}
        turn = await rig.driver.user_says("Muéstrame Estocolmo.")
        check_turn(rig, turn)
        assert "{" not in turn.text and "Te abro Estocolmo." in turn.text
        # The page, its gallery and the typology in the page's own label; the
        # tour this page does not have, dropped.
        assert _cues(rig) == [
            {**NONE, "at": "te abro estocolmo", "word": 0, "path": "/estocolmo/"},
            {**NONE, "at": "aqui ves las", "word": 3, "path": "/estocolmo/", "heading": "galería"},
            {
                **NONE,
                "at": "este tiene dos",
                "word": 7,
                "path": "/estocolmo/",
                "typology": "2D | 3B",
            },
        ]


async def test_on_the_page_his_words_ring_what_he_describes() -> None:
    llm = _llm()
    async with demo("ssilva", llm) as rig:
        await rig.driver.start_session(init={"path": "/estocolmo/"})
        await _page(rig, "page_changed", ESTOCOLMO_PAGE)
        await rig.driver.user_says("¿Qué amenidades tiene?")
        # The page in front was read in with what they said.
        seen = _texts(llm.captured_contents[-1])
        assert "the project page of Estocolmo (/estocolmo/)" in seen
        assert "Typologies: 2D | 3B; 3D | 3B (selected: 2D | 3B)" in seen
        assert _cues(rig) == [
            {**NONE, "at": "hay piscina gimnasio", "word": 4, "heading": "amenidades"}
        ]
        await rig.driver.user_says("¿Y el de tres dormitorios?")
        assert _cues(rig)[-1] == {**NONE, "at": "el de tres", "word": 3, "typology": "3D | 3B"}


async def test_a_project_they_name_is_opened_when_his_reply_forgets_to() -> None:
    async with demo("ssilva", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Háblame de Canal Beagle.")
        assert _cues(rig)[0] == {**NONE, "at": "esta en vina", "word": 0, "path": "/canalbeagle/"}


async def test_projects_are_found_and_rung_on_the_list() -> None:
    llm = _llm()
    async with demo("ssilva", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Busco un departamento de dos dormitorios en Viña.")
        found = _results(llm.captured_contents[-1])["find_projects"]
        assert "Isla Picton" in found and "Canal Beagle" in found and "Estocolmo" not in found
        assert "path: /canalbeagle/" in found
        assert "dos mil trescientas setenta y dos UF" in found
        # Names as the cards write them; the invented one left out.
        assert rig.command("show_projects") == {
            "region": "valparaiso",
            "property": None,
            "communes": [],
            "highlight": ["ISLA PICTON", "CANAL BEAGLE"],
            "paths": ["/isla-picton/", "/canalbeagle/"],
        }
        await _page(
            rig,
            "projects_listed",
            {
                "count": 2,
                "region": "valparaiso",
                "communes": [],
                "projects": ["ISLA PICTON", "CANAL BEAGLE"],
            },
        )
        await rig.driver.user_says("Quiero ver los de Las Condes.")
        assert "The project list shows 2 projects for valparaiso" in _texts(
            llm.captured_contents[-1]
        )
        assert _commands(rig, "show_projects")[-1] == {
            "region": "metropolitana",
            "property": "departamento",
            "communes": ["Las Condes"],
            "highlight": [],
            "paths": [],
        }


async def test_the_quote_form_fills_as_they_talk_and_is_never_sent() -> None:
    llm = _llm()
    async with demo("ssilva", llm) as rig:
        await rig.driver.start_session(init={"path": "/estocolmo/"})
        await _page(rig, "page_changed", ESTOCOLMO_PAGE)
        await rig.driver.user_says("Quiero cotizar.")
        assert _cues(rig)[-1]["heading"] == "formulario"
        assert rig.command("fill_lead_form") == {
            "firstname": "Ana",
            "lastname": "Pérez Soto",
            "rut": None,
            "email": None,
            "phone": None,
            "motivo": None,
            "tipologia": None,
            "ingreso": None,
            "pie": None,
            "next_step": False,
        }
        # The RUT checked and written as the site writes it; the email as typed
        # to the form; "para vivir" is the form's "Habitar".
        await rig.driver.user_says("Mi RUT es 12.345.678-5 y mi correo ana.perez@gmail.com")
        filled = _commands(rig, "fill_lead_form")[-1]
        assert filled["rut"] == "12.345.678-5"
        assert filled["email"] == "ana.perez@gmail.com"
        assert filled["motivo"] == "Habitar"
        assert filled["firstname"] is None  # What is filled stays: only what is new.
        # A RUT whose last digit is wrong is not filled.
        await rig.driver.user_says("Mi RUT es 12.345.678-9")
        assert len(_commands(rig, "fill_lead_form")) == 2
        # Step two's answer before its options are known is kept, not typed in.
        await rig.driver.user_says("Mi celular es 9 1234 5678. Sigamos.")
        step = _commands(rig, "fill_lead_form")[-1]
        assert step["phone"] == "9 1234 5678" and step["next_step"] is True
        assert step["ingreso"] is None
        # His last turn's results reach the model with this one.
        refused = _all_results(llm.captured_contents[-1], "fill_lead_form")
        assert any("does not check out" in r for r in refused), refused
        # The form's second step, with its options, arrives after his turn.
        await _page(
            rig,
            "lead_form",
            {
                "step": "details",
                "filled": {"firstname": "Ana", "email": "ana.perez@gmail.com"},
                "missing": ["tipologia", "ingreso", "pie"],
                "options": {
                    "tipologia": ["2 dormitorios", "3 dormitorios"],
                    "ingreso": INGRESOS,
                    "pie": PIES,
                },
            },
        )
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        seen = _texts(llm.captured_contents[-1])
        assert "Options for ingreso líquido: Menos de $1.000.000 |" in seen
        assert "un millón y medio" in seen  # What they said before, to fill in now.
        # Amounts as said land on the form's own ranges.
        await rig.driver.user_says("Gano un millón y medio, y tengo tres millones ahorrados.")
        filled = _commands(rig, "fill_lead_form")[-1]
        assert filled["ingreso"] == "Entre $1.500.000 a $1.800.000"
        assert filled["pie"] == "Entre $2.000.000 a $5.000.000"
        assert "enviar" not in " ".join(rig.actions()).lower()
        # Enviar is the visitor's; this preview held it back.
        await _page(rig, "lead_submitted", {"blocked": True})
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert "no lo envió" in turn.text
        assert "This preview held it back: nothing was sent to Ssilva" in _texts(
            llm.captured_contents[-1]
        )


async def test_the_form_waits_for_a_project_page() -> None:
    llm = _llm()
    async with demo("ssilva", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Quiero cotizar en la portada.")
        assert "fill_lead_form" not in rig.actions()
        await rig.driver.user_says("Sigue.")
        assert "Not filled yet" in _results(llm.captured_contents[-1])["fill_lead_form"]


async def test_english_heard_moves_both_legs_before_he_answers() -> None:
    async with demo("ssilva", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("Hi, can you show me projects in Las Condes please?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert rig.command("language_changed") == {"language": "en"}


async def test_the_toggle_switches_and_confirms_and_the_choice_holds() -> None:
    async with demo("ssilva", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(rig, "language_requested", {"language": "en"})
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert rig.command("language_changed") == {"language": "en"}
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        assert turn.text == TOGGLE_CONFIRM["en"]
        # Chosen: Spanish spoken to him is still answered in English.
        await rig.driver.user_says("Sigue.")
        check_voice_pair(rig, voice="omnivoice/javier", language="en")


async def test_asked_in_words_he_switches_with_set_language() -> None:
    async with demo("ssilva", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("¿Puedes hablar en inglés?")
        await asyncio.sleep(0.1)
        check_voice_pair(rig, voice="omnivoice/javier", language="en")


async def test_the_tour_photos_and_whatsapp_are_checked_against_the_page() -> None:
    async with demo("ssilva", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/estocolmo/"})
        await _page(rig, "page_changed", ESTOCOLMO_PAGE)
        await rig.driver.user_says("Ábreme el tour.")
        assert "open_tour" not in rig.actions()  # This page has no tour.
        await rig.driver.user_says("Muéstrame la piscina.")
        assert rig.command("show_photos") == {"which": "amenities", "index": 2, "fullscreen": True}
        await rig.driver.user_says("Escríbeles por WhatsApp.")
        assert "open_whatsapp" in rig.actions()


async def test_events_reach_the_model_as_screen_lines() -> None:
    llm = _llm()
    async with demo("ssilva", llm) as rig:
        await rig.driver.start_session(init={"path": "/estocolmo/"})
        await _page(
            rig,
            "typology_shown",
            {
                "label": "2D | 3B",
                "price": "Desde 13.976 UF",
                "total_area": "147,13",
                "bedrooms": "2",
                "bathrooms": "3",
                "orientation": "NP",
            },
        )
        await _page(rig, "command_failed", {"command": "open_tour", "reason": "no tour"})
        await _page(rig, "command_failed", {"command": "cue", "reason": "no heading X"})
        await rig.driver.user_says("Sigue.")
        seen = _texts(llm.captured_contents[-1])
        assert "[On screen: typology 2D | 3B, Desde 13.976 UF, área total 147,13" in seen
        assert "That did not happen on the page (open_tour: no tour)" in seen
        assert "A screen cue of yours did not land (no heading X)" in seen


async def test_a_read_comes_back_within_the_turn() -> None:
    llm = _llm()
    async with demo("ssilva", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Qué es Estocolmo?")
        check_turn(rig, turn)
        read = _results(llm.captured_contents[-1])["read_project"]
        assert "Estocolmo 661" in read and "{page: /estocolmo/}" in read


async def test_a_silent_move_is_talked_about() -> None:
    async with demo("ssilva", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/estocolmo/"})
        turn = await rig.driver.user_says("Ábreme WhatsApp.")
        check_turn(rig, turn)
        assert "Ya está abierto." in turn.text


async def test_a_reply_that_only_promises_is_asked_again() -> None:
    async with demo("ssilva", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/estocolmo/"})
        turn = await rig.driver.user_says("¿Dónde queda?")
        check_turn(rig, turn)
        assert "Queda en Las Condes" in turn.text


async def test_projects_he_names_are_rung_on_the_list_as_he_says_them() -> None:
    llm = _llm()
    async with demo("ssilva", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        # Named on the home page, before his show_projects: kept, and sent
        # after it, so the list it opens rings each card as he names it.
        await rig.driver.user_says("Busco para invertir en Santiago.")
        commands = [c["command"] for c in rig.driver.ui_commands]  # type: ignore[attr-defined]
        cards = [c for c in _cues(rig) if c["card"]]
        assert [(c["card"], c["text"], c["at"]) for c in cards] == [
            ("/distrito-barroso/", "DISTRITO BARROSO", "distrito barroso esta"),
            ("/estocolmo/", "ESTOCOLMO", "estocolmo esta en"),
        ]
        assert commands.index("show_projects") < len(commands) - 2
        assert all(c["path"] is None for c in cards)
        assert rig.command("show_projects")["paths"] == ["/distrito-barroso/", "/estocolmo/"]
        # With no list opened, the same sentence rings nothing.
        before = len(_cues(rig))
        await rig.driver.user_says("¿Cuáles están en Santiago?")
        assert not [c for c in _cues(rig)[before:] if c["card"]]
        # On the list, his words alone ring the card, once.
        await _page(rig, "page_changed", LIST_PAGE)
        await rig.driver.user_says("¿Cuál me recomiendas?")
        assert [c["card"] for c in _cues(rig) if c["card"]][-1] == "/distrito-barroso/"
        assert [c["card"] for c in _cues(rig)].count("/distrito-barroso/") == 2


async def test_a_list_ring_that_missed_is_not_talked_about() -> None:
    llm = _llm()
    async with demo("ssilva", llm) as rig:
        await rig.driver.start_session(init={"path": "/proyectos/"})
        await _page(
            rig,
            "command_failed",
            {"command": "show_projects", "reason": "ESTOCOLMO is not among these 15 projects"},
        )
        await rig.driver.user_says("Sigue.")
        seen = _texts(llm.captured_contents[-1])
        assert "Do not mention it" in seen
        assert "Tell the visitor plainly" not in seen


async def test_the_floor_plan_opens_by_its_label_through_a_translated_page() -> None:
    llm = _llm()
    async with demo("ssilva", llm) as rig:
        await rig.driver.start_session(init={"path": "/distrito-barroso/", "lang": "en"})
        await _page(rig, "page_changed", BARROSO_PAGE)
        await rig.driver.user_says("Show me the floor plan of the butterfly one.")
        # The site's own name, not the translated title, and what the photos show.
        seen = _texts(llm.captured_contents[-1])
        assert "the project page of Distrito Barroso (/distrito-barroso/)" in seen
        assert "Gallery photos: 1 depto grande; 2 depto pequeno; 3 quincho; 4 cowork." in seen
        # The plan in the label the page shows; his words select the typology
        # they describe, "two-bedroom, one-bathroom" included.
        assert rig.command("show_floor_plan") == {"typology": "2D | 2B BUTTERFLY"}
        plans = [c["typology"] for c in _cues(rig) if c["typology"]]
        assert plans == ["2D | 2B BUTTERFLY", "2D | 1B"]
        await _page(
            rig,
            "photo_shown",
            {"which": "plan", "index": 1, "total": 1, "caption": "2D | 2B BUTTERFLY · 56.65 m²"},
        )
        await rig.driver.user_says("Sigue.")
        assert "[On screen: the floor plan 2D | 2B BUTTERFLY · 56.65 m²." in _texts(
            llm.captured_contents[-1]
        )


async def test_photos_full_screen_one_at_a_time_and_a_slideshow() -> None:
    llm = _llm()
    async with demo("ssilva", llm) as rig:
        await rig.driver.start_session(init={"path": "/distrito-barroso/"})
        await _page(rig, "page_changed", BARROSO_PAGE)
        await rig.driver.user_says("Muéstrame las fotos en grande.")
        assert rig.command("show_photos") == {"which": "gallery", "index": 1, "fullscreen": True}
        # A photo per sentence, as he says it; one the gallery does not have, dropped.
        photos = [(c["photos"], c["photo"]) for c in _cues(rig) if c["photo"]]
        assert photos == [("gallery", 1), ("amenities", 2)]
        await rig.driver.user_says("Pon una presentación.")
        assert rig.command("slideshow") == {"play": True, "which": None, "seconds": 15}
        # The slideshow is news when it starts and when it stops, not per photo.
        show = {"which": "gallery", "total": 4, "playing": True}
        await _page(rig, "photo_shown", {**show, "index": 1, "caption": "depto grande"})
        await _page(rig, "photo_shown", {**show, "index": 2, "caption": "depto pequeno"})
        await _page(
            rig, "photo_shown", {**show, "index": 3, "caption": "quincho", "playing": False}
        )
        await rig.driver.user_says("La siguiente.")
        assert rig.command("step_photo") == {"back": False}
        seen = _texts(llm.captured_contents[-1])
        assert "a slideshow of the gallery photos, from gallery photo 1 of 4 (depto grande)" in seen
        assert "depto pequeno" not in seen.split("slideshow of the gallery photos")[1]
        assert "[The slideshow stopped on gallery photo 3 of 4 (quincho).]" in seen
        await _page(rig, "viewer_closed", {"which": "gallery"})
        await rig.driver.user_says("Sigue.")
        assert "[The visitor closed the full-screen view.]" in _texts(llm.captured_contents[-1])
