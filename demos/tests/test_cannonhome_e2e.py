"""Javier, Cannon Home's voice guide, end to end over the wire — no network, no LLM key.

The real ``CannonHomeBrain`` on a real ``brain_server`` socket, driven by the
conformance ``VoqalizeDriver``, with only the model scripted. The knowledge is a
small invented store in the crawl's own shape — pages, listings and a catalogue
of a few products — put in place of the committed one: no test depends on what
the crawl found this week.

What this demo earns that others do not:

**No price he did not just read.** The catalogue has no prices; the brain never
fetches the store. Prices come only from the visitor's screen, as app events, and
every tool result carries one only once the screen has shown it. A live read
wins over the page's cached copy.

**A size is another product.** The product page has no size picker: "¿la tienes
en king?" is the line's King product, found in the catalogue and opened.

**The cart, never the checkout.** He adds to the cart with the quantity said;
nothing he sends ever reaches the checkout.

Run: ``cd demos && uv run pytest tests/test_cannonhome_e2e.py``
"""

from __future__ import annotations

import asyncio
import statistics
import time
from collections.abc import Iterator
from typing import Any

import pytest
from google.genai import types
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedGemini, call, reply, reply_and_call

from ._harness import _configs, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.cannonhome import brain as ch  # noqa: E402
from voqalize_demos._loaded.cannonhome import knowledge as kb  # noqa: E402
from voqalize_demos._loaded.cannonhome.brain import (  # noqa: E402
    _IDLE_MS,
    _TALK_THROUGH_MS,
    TOGGLE_CONFIRM,
    greeting,
    language_of,
)
from voqalize_demos._loaded.cannonhome.knowledge import (  # noqa: E402
    Category,
    Faq,
    Knowledge,
    Page,
    Product,
    Section,
)

SHEETS = "/12-ropa-de-cama/20-sabanas"
DESPACHO = "/politicas-de-despacho"
S2 = "/sabanas-2-plazas-300-hilos-inventadas-blanco.html"
SK = "/sabanas-king-300-hilos-inventadas-blanco.html"
S15 = "/sabanas-1-5-plazas-300-hilos-inventadas-blanco.html"
S2G = "/sabanas-2-plazas-300-hilos-inventadas-gris.html"
TOWEL = "/toalla-inventada-blanco-700g.html"
DUVET = "/plumon-inventado-2-plazas.html"


def _sheet(size: str, slug: str, color: str, sku: str) -> Product:
    return Product(
        sku=sku,
        name=f"Sábanas {size} 300 Hilos Inventadas {color}",
        path=f"/sabanas-{slug}-300-hilos-inventadas-{color.lower()}.html",
        brand="Cannon Home",
        category="Ropa de Cama > Sábanas",
        categories=(SHEETS,),
        type="Juego de Sábanas",
        size=size,
        color=color,
        material="100% Algodón",
        threads=300,
        family=f"JSINV300-{color[0]}",
        summary="Juego de sábanas inventado para las pruebas.",
    )


# An invented store in the crawl's shape: the names and paths are ours.
STORE = Knowledge(
    l1="Cannon Home vende ropa de cama y baño (inventado para las pruebas).",
    topics={},
    pages={
        "/": Page("/", "Cannon Home", sections=(Section("Novedades"),), kind="home"),
        DESPACHO: Page(
            DESPACHO,
            "Políticas de despacho | Cannon Home",
            sections=(
                Section("Despacho a domicilio", "Despachamos a todo Chile."),
                Section("Plazos de entrega", "De dos a cuatro días hábiles en Santiago."),
            ),
            faqs=(Faq("¿Cuánto demora mi pedido?", "De dos a cuatro días hábiles."),),
        ),
        "/preguntas-frecuentes": Page(
            "/preguntas-frecuentes",
            "Preguntas frecuentes",
            sections=(Section("Compras y pagos"),),
            faqs=(Faq("¿Puedo pagar en cuotas?", "Sí, hasta doce cuotas sin interés."),),
        ),
        "/politicas-de-cambios-y-devoluciones": Page(
            "/politicas-de-cambios-y-devoluciones",
            "Cambios y devoluciones",
            sections=(Section("Garantía legal"),),
        ),
        SHEETS: Page(SHEETS, "Sábanas", sections=(Section("Sábanas"),), kind="category"),
    },
    products={
        p.path: p
        for p in (
            _sheet("2 Plazas", "2-plazas", "Blanco", "JSINV300P20B"),
            _sheet("King", "king", "Blanco", "JSINV300P25B"),
            _sheet("1.5 Plazas", "1-5-plazas", "Blanco", "JSINV300P15B"),
            _sheet("2 Plazas", "2-plazas", "Gris", "JSINV300P20G"),
            Product(
                sku="TOINV700B",
                name="Toalla Inventada Blanco 700g",
                path=TOWEL,
                category="Baño > Toallas",
                type="Toallas de Baño",
                color="Blanco",
                material="100% Algodón",
                weight_gsm=700,
                family="TOINV700",
            ),
            Product(
                sku="PPINV01P20",
                name="Plumón Inventado 2 Plazas",
                path=DUVET,
                category="Ropa de Cama > Plumones",
                type="Plumones de Plumas",
                size="2 Plazas",
                color="Blanco",
                material="Pluma",
                family="PPINV01",
            ),
        )
    },
    categories={
        SHEETS: Category(
            SHEETS,
            "Sábanas",
            filters=("tamano", "color", "hilos", "material"),
            options=(
                ("tamano", ("1 Plaza", "1.5 Plazas", "2 Plazas", "King", "Súper King")),
                ("color", ("Blanco", "Gris", "Azul")),
                ("hilos", ("144", "200", "300")),
                ("material", ("Polycotton", "100% Algodón")),
            ),
        )
    },
)

PRODUCT_PAGE = {
    "site": "site",
    "url": f"https://cannonhome.cl{S2}",
    "path": S2,
    "title": "Sábanas 2 Plazas 300 Hilos Inventadas Blanco",
    "kind": "product",
    "headings": ["Descripción", "Especificaciones"],
    "faqs": [],
}


def _shown(
    path: str = S2, price: int | None = 30000, source: str = "page", **over: Any
) -> dict[str, Any]:
    return {
        "path": path,
        "sku": "JSINV300P20B",
        "name": STORE.products[path].name if path in STORE.products else "Algo",
        "price": price,
        "regular_price": 45000,
        "in_stock": True,
        "qty": None,
        "specs": {"Hilos": "300", "Tamaño": "2 Plazas"},
        "rating": 4.5,
        "reviews": 12,
        "source": source,
    } | over


@pytest.fixture(autouse=True)
def _store(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every session reads the invented store, and he never nods unless a test
    asks him to: a nod is a unit of its own."""
    monkeypatch.setattr(kb, "KNOWLEDGE", STORE)
    monkeypatch.setattr(ch, "ACK_RATE", 0.0)
    yield


def _results(contents: list[types.Content]) -> dict[str, str]:
    return {
        p.function_response.name or "": str((p.function_response.response or {})["result"])
        for c in contents
        for p in (c.parts or [])
        if p.function_response is not None
    }


def _every(contents: list[types.Content], name: str) -> list[str]:
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
            "Hola, ¿cómo estás?": reply("Muy bien. ¿Qué estás buscando hoy?"),
            "How much is shipping?": reply(
                "{page: /politicas-de-despacho} It takes two to four working days."
            ),
            "¿Cuánto demora el despacho?": reply("Llega en dos a cuatro días hábiles."),
            "Muéstrame los plazos.": reply(
                "{page: /politicas-de-despacho}{show: plazos de entrega} Llega en pocos días. "
                "{page: /no-existe} {page: /checkout} {faq: cuanto demora mi pedido} "
                "Esa es la pregunta."
            ),
            "¿Y las toallas?": reply("Un momento."),
            "Busco sábanas king blancas de 300 hilos.": [
                call("find_products", request={"query": "sábanas king blancas 300 hilos"}),
                reply("Tengo unas de algodón. ¿Te las abro?"),
            ],
            "¿Y de dos plazas?": [
                call("find_products", request={"query": "sábanas 2 plazas"}),
                reply("También hay."),
            ],
            "¿Cuál es mejor?": 2
            * [
                call("compare_products", request={"paths": [S2, SK]}),
                reply("Son iguales salvo el tamaño."),
            ],
            "¿La tienes en king?": [
                call("find_products", request={"size": "king"}),
                reply_and_call("Sí, también en king.", "open_product", request={"path": SK}),
            ],
            "¿Y en morado?": [
                call("find_products", request={"color": "morado"}),
                reply("En morado no la tengo."),
            ],
            "Ábreme las de dos plazas.": reply_and_call(
                "Te abro las de dos plazas.", "open_product", request={"path": S2}
            ),
            "Ábreme las king.": call("open_product", request={"path": SK}),
            "Y agrégala al carro.": reply_and_call(
                "Te la agrego.", "add_to_cart", request={"path": SK, "qty": 1}
            ),
            "Agrégame dos al carro.": reply_and_call(
                "Te agrego dos al carro.", "add_to_cart", request={"path": S2, "qty": 2}
            ),
            "Agrégame quince.": reply_and_call(
                "Te agrego quince.", "add_to_cart", request={"path": S2, "qty": 15}
            ),
            "Agrega una que no existe.": reply_and_call(
                "Te la agrego.", "add_to_cart", request={"path": "/inventada-de-verdad.html"}
            ),
            "Filtra las king blancas.": reply_and_call(
                "Te filtro la lista.",
                "filter_listing",
                request={
                    "category_path": SHEETS,
                    "size": "king",
                    "color": "blancas",
                    "sort": "price_asc",
                },
            ),
            "Filtra las de seda.": reply_and_call(
                "Te filtro.",
                "filter_listing",
                request={"category_path": SHEETS, "material": "seda"},
            ),
            "¿Cuánto cuestan las dos?": reply_and_call(
                "Te reviso los precios.", "check_prices", request={"paths": [S2, SK]}
            ),
            "Busca toalla blanca.": reply_and_call(
                "La busco.", "search_products", request={"query": "toalla blanca"}
            ),
            "Ábreme la primera toalla.": reply_and_call(
                "Te abro la primera.",
                "search_products",
                request={"query": "toalla blanca", "open_index": 1},
            ),
            "Can I speak in English?": reply_and_call(
                "Sure, let's continue in English.",
                "add_to_cart",
                request={"path": S2, "qty": 1},
            ),
            # The page's answers to his moves, talked through in the quiet spell.
            "The page answered what you sent it": reply(
                "{page: /politicas-de-despacho} Esto es lo que hizo la página."
            ),
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


def _recording(llm: ScriptedGemini) -> list[types.GenerateContentConfig]:
    seen: list[types.GenerateContentConfig] = []
    answer = llm.answer

    def recording(*, model: str, contents: object, config: types.GenerateContentConfig) -> object:
        seen.append(config)
        return answer(model=model, contents=contents, config=config)

    llm.answer = recording
    return seen


_TOOLS_OFF = types.ToolConfig(
    function_calling_config=types.FunctionCallingConfig(mode=types.FunctionCallingConfigMode.NONE)
)


# ─── Voice and language ────────────────────────────────────────────────────────


async def test_the_greeting_is_spanish_and_the_voice_reaches_the_wire() -> None:
    async with demo("cannonhome", _llm()) as rig:
        opener = await rig.driver.start_session(init={"surface": "cannonhome-ext", "path": "/"})
        check_greeting(rig, opener)
        assert opener is not None
        assert opener.text == ch.for_the_voice(greeting("/", "es"))
        assert opener.text.startswith("Hola, soy Javier, tu guía de voz de Cannon Home.")
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _idle_windows(rig) == [_IDLE_MS]


async def test_the_toggle_moves_both_legs_to_english_and_confirms() -> None:
    async with demo("cannonhome", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(rig, "language_requested", {"language": "en"})
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert rig.command("language_changed") == {"language": "en"}
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert turn.text == TOGGLE_CONFIRM["en"]


async def test_a_call_started_in_english_greets_in_english() -> None:
    async with demo("cannonhome", _llm()) as rig:
        opener = await rig.driver.start_session(init={"path": "/", "lang": "en"})
        assert opener is not None and opener.text == greeting("/", "en")
        assert opener.text.startswith("Hi, I'm Javier, Cannon Home's voice guide.")
        check_voice_pair(rig, voice="omnivoice/javier", language="en")


async def test_english_heard_moves_the_call_and_spanish_brings_it_back() -> None:
    async with demo("cannonhome", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("How much is shipping?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        await rig.driver.user_says("Hola, ¿cómo estás?")
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _commands(rig, "language_changed") == [{"language": "en"}, {"language": "es"}]


@pytest.mark.parametrize(
    ("text", "sure", "lang"),
    [
        ("¿Cuánto cuestan las sábanas king?", True, "es"),
        ("Busco una toalla blanca", True, "es"),
        ("Hola", True, None),
        ("King", True, None),
        ("Do you have these sheets in king?", True, "en"),
        ("Claro.", False, "es"),
        ("{show: Plazos de entrega} It's about two days for you.", False, "en"),
    ],
)
def test_the_language_a_line_is_in(text: str, sure: bool, lang: str | None) -> None:
    assert language_of(text, sure=sure) == lang


@pytest.mark.parametrize(
    ("path", "words"),
    [
        ("/", "¿Qué estás buscando?"),
        ("/12-ropa-de-cama/20-sabanas", "tus sábanas"),
        ("/12-ropa-de-cama/20-sabanas/king_1", "tus sábanas"),
        ("/bano/toallas/toallas-de-bano", "tus toallas"),
        ("/12-ropa-de-cama/plumones", "tu plumón"),
        ("/12-ropa-de-cama/fundas-plumon", "funda de plumón"),
        (S2, "este producto"),
        ("/checkout/cart", "tu carro"),
        ("/blog/novedades.html", "¿Qué estás buscando?"),
    ],
)
def test_the_opener_follows_the_page(path: str, words: str) -> None:
    line = greeting(path, "es")
    assert line.startswith("Hola, soy Javier")
    assert words in line, line
    assert greeting(path, "en").startswith("Hi, I'm Javier")


def test_the_store_name_in_capitals_is_handed_to_the_voice_as_words() -> None:
    assert ch.for_the_voice("Bienvenido a CANNON HOME.") == "Bienvenido a Cannon Home."
    assert ch.names_for_the_voice("Sábanas CANNON.") == "Sábanas Cannon."


@pytest.mark.parametrize(
    ("amount", "es", "en"),
    [
        (28495, "veintiocho mil cuatrocientos noventa y cinco pesos", None),
        (121000, "ciento veintiún mil pesos", "one hundred and twenty-one thousand pesos"),
        (231990, "doscientos treinta y un mil novecientos noventa pesos", None),
        (100, "cien pesos", "one hundred pesos"),
        (1_000_000, "un millón de pesos", "one million pesos"),
        (55993, "cincuenta y cinco mil novecientos noventa y tres pesos", None),
        (28495, None, "twenty-eight thousand four hundred and ninety-five pesos"),
        (150005, None, "one hundred and fifty thousand and five pesos"),
    ],
)
def test_pesos_are_said_as_a_chilean_says_them(amount: int, es: str | None, en: str | None) -> None:
    assert ch.pesos(amount) == "$" + f"{amount:,}".replace(",", ".")
    if es is not None:
        assert ch.pesos_said(amount, "es") == es
    if en is not None:
        assert ch.pesos_said(amount, "en") == en


# ─── Cues ──────────────────────────────────────────────────────────────────────

NONE = {"path": None, "heading": None, "text": None, "faq": None}


async def test_cues_leave_the_speech_and_are_checked_against_the_site() -> None:
    async with demo("cannonhome", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("Muéstrame los plazos.")
        check_turn(rig, turn)
        assert "{" not in turn.text and "}" not in turn.text
        # The page as the store links it; the heading in the site's spelling;
        # an invented page and the checkout dropped; the FAQ on the page.
        cues = _commands(rig, "cue")
        assert cues == [
            {**NONE, "at": "llega en pocos", "word": 0, "path": DESPACHO},
            {
                **NONE,
                "at": "llega en pocos",
                "word": 0,
                "path": DESPACHO,
                "heading": "Plazos de entrega",
            },
            {
                **NONE,
                "at": "esa es la",
                "word": 4,
                "path": DESPACHO,
                "faq": "¿Cuánto demora mi pedido?",
            },
        ], cues


async def test_what_they_asked_about_is_shown_when_his_reply_forgets_to() -> None:
    async with demo("cannonhome", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("¿Cuánto demora el despacho?")
        assert _commands(rig, "cue")[0] == {
            **NONE,
            "at": "llega en dos",
            "word": 0,
            "path": DESPACHO,
        }


def test_the_page_for_what_they_asked_about() -> None:
    asked = ch.asked_page
    assert asked("¿Cuánto demora el despacho?") == DESPACHO
    assert asked("How long does delivery take?") == DESPACHO
    assert asked("¿Puedo retirar en tienda?") == "/retiro-tiendas"
    assert asked("¿Cómo hago un cambio?") == "/politicas-de-cambios-y-devoluciones"
    assert asked("Quiero devolver algo") == "/politicas-de-cambios-y-devoluciones"
    assert asked("¿Dónde quedan las tiendas?") == "/stores"
    assert asked("preguntas frecuentes") == "/preguntas-frecuentes"
    assert asked("¿Qué tengo en mi carro?") == "/checkout/cart"
    assert asked("¿Puedo pagar con tarjeta?", STORE) == "/preguntas-frecuentes"
    # Adding to the cart is a move, not the cart page.
    assert asked("Agrégalo al carro") is None
    assert asked("Add it to my cart") is None
    assert asked("Busco sábanas king") is None
    for ask in ("¿Puedes hablar en inglés?", "Can we continue in English?", "Vuelve a la pestaña"):
        assert asked(ask) is None, ask


# ─── Finding products, and their prices ────────────────────────────────────────


async def test_the_catalogue_reads_their_words_and_quotes_no_price_it_did_not_see() -> None:
    llm = _llm()
    async with demo("cannonhome", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Busco sábanas king blancas de 300 hilos.")
        found = _results(llm.captured_contents[-1])["find_products"]
        assert f"Sábanas King 300 Hilos Inventadas Blanco — {SK}" in found
        assert S2 not in found.split("\n")[1].split(";")[0], found
        # Its other sizes, each its own product, by path.
        assert f"other sizes: 1.5 Plazas {S15}" in found or f"2 Plazas {S2}" in found
        assert "$" not in found and "pesos" not in found
        assert "say one only once their screen has shown it" in found

        # The listing on their screen shows a price: now, and only for that one.
        await _page(
            rig,
            "listing_shown",
            {
                "path": SHEETS,
                "title": "Sábanas",
                "count": 2,
                "filters": {"tamano": "2 Plazas"},
                "sort": "",
                "items": [{"name": "Sábanas 2 Plazas", "path": S2, "price": 55990}],
            },
        )
        await rig.driver.user_says("¿Y de dos plazas?")
        found = _every(llm.captured_contents[-1], "find_products")[-1]
        (line,) = [x for x in found.splitlines() if x.startswith("- ") and f"— {S2};" in x]
        assert "$55.990" in line and "cincuenta y cinco mil novecientos noventa pesos" in line
        assert "on the listing" in line
        # The line that showed a price is the only one that carries one.
        assert [x for x in found.splitlines() if "$" in x] == [line]
        assert "[The listing in front: “Sábanas”" in _texts(llm.captured_contents[-1])


async def test_compare_says_price_not_read_yet_and_a_live_read_wins_over_the_page() -> None:
    llm = _llm()
    async with demo("cannonhome", llm) as rig:
        await rig.driver.start_session(init={"path": S2})
        await rig.driver.user_says("¿Cuál es mejor?")
        compared = _results(llm.captured_contents[-1])["compare_products"]
        assert compared.count("; price not read yet.") == 2
        assert "$" not in compared and "Never guess one" in compared

        # The page reads its own (cached) copy, then the live check.
        await _page(rig, "page_changed", PRODUCT_PAGE)
        await _page(rig, "product_shown", _shown(price=30000, source="page"))
        await _page(rig, "product_shown", _shown(price=28495, source="graphql"))
        # A later cached copy does not undo the live read.
        await _page(rig, "product_shown", _shown(price=30000, source="page"))
        await rig.driver.user_says("¿Cuál es mejor?")
        seen = _texts(llm.captured_contents[-1])
        assert "[The product page in front: “Sábanas 2 Plazas 300 Hilos Inventadas Blanco”" in seen
        assert "a live check follows" in seen
        assert "[Live check of “Sábanas 2 Plazas 300 Hilos Inventadas Blanco”" in seen
        assert "The page showed $30.000, an older copy: say this one." in seen
        assert "Especificaciones: Hilos: 300; Tamaño: 2 Plazas." in seen
        compared = _every(llm.captured_contents[-1], "compare_products")[-1]
        (two,) = [x for x in compared.splitlines() if S2 in x]
        assert "$28.495" in two and "read live" in two and "$30.000" not in two
        (king,) = [x for x in compared.splitlines() if SK in x]
        assert "price not read yet" in king and "$" not in king


async def test_on_a_product_page_another_size_is_its_sibling_opened() -> None:
    """No size picker on the page: "¿la tienes en king?" is the line's King."""
    llm = _llm()
    async with demo("cannonhome", llm) as rig:
        await rig.driver.start_session(init={"path": S2})
        await _page(rig, "page_changed", PRODUCT_PAGE)
        await _page(rig, "product_shown", _shown())
        turn = await rig.driver.user_says("¿La tienes en king?")
        check_turn(rig, turn)
        found = _every(llm.captured_contents[-1], "find_products")[-1]
        assert found.startswith(
            f"The line of “Sábanas 2 Plazas 300 Hilos Inventadas Blanco” ({S2}):"
        )
        assert f"— {SK};" in found and "$" not in found.split(SK)[1].split("\n")[0]
        assert rig.command("open_product") == {"path": SK, "tab": None}
        # A colour the line does not have: said, with the line it does have.
        await rig.driver.user_says("¿Y en morado?")
        found = _every(llm.captured_contents[-1], "find_products")[-1]
        assert "Without color (morado)" in found


def test_visitor_words_are_read_as_the_sites_labels() -> None:
    w = kb.visitor_wishes("Quiero sábanas king blancas de 300 hilos")
    assert (w["type"], w["size"], w["color"], w["threads"], w["words"]) == (
        "sabana",
        "king",
        "blanc",
        300,
        [],
    )
    assert kb.size_key("1,5 plazas") == "1.5"
    assert kb.size_key("plaza y media") == "1.5"
    assert kb.size_key("dos plazas") == "2"
    assert kb.size_key("matrimonial") == "2"
    assert kb.size_key("queen") == "2"
    assert kb.size_key("Súper King") == "super king"
    assert kb.size_key("super king") == "super king"
    assert kb.size_key("king") == "king"
    assert kb.size_key("1 Plaza") == "1"
    assert kb.size_key("50 x 70 cm") == "50x70"
    assert kb.color_stem("white") == kb.color_stem("Blancas") == "blanc"
    assert kb.color_stem("grises") == "gris"
    assert kb.material_key("egyptian cotton") == "algodon"
    found = STORE.find_products(query="egyptian cotton sheets queen")
    assert {p.path for p in found.products} == {S2, S2G}
    assert STORE.find_products(query="toalla de 700 gramos").products[0].path == TOWEL
    assert STORE.find_products(query="duvet").products[0].path == DUVET


def _synthetic(n: int = 2000) -> Knowledge:
    sizes = ("1 Plaza", "1.5 Plazas", "2 Plazas", "King", "Súper King")
    colors = ("Blanco", "Gris", "Azul", "Beige", "Taupe", "Rosado", "Verde", "Negro")
    kinds = (
        ("Sábanas", "Juego de Sábanas", "Ropa de Cama > Sábanas"),
        ("Plumón", "Plumones Microfibra", "Ropa de Cama > Plumones"),
        ("Funda Plumón", "Funda de Plumón", "Ropa de Cama > Fundas Plumón"),
        ("Cubrecama", "Cubrecamas y Quilts", "Ropa de Cama > Cubrecamas"),
    )
    products: dict[str, Product] = {}
    i = 0
    while len(products) < n:
        name, kind, cat = kinds[i % len(kinds)]
        size = sizes[(i // 4) % len(sizes)]
        color = colors[(i // 20) % len(colors)]
        threads = (144, 200, 300, 400, 600)[(i // 160) % 5]
        path = f"/{kb.fold(name).replace(' ', '-')}-{i}.html"
        products[path] = Product(
            sku=f"SKU{i:05d}",
            name=f"{name} {size} {threads} Hilos Diseño {i // 40} {color}",
            path=path,
            category=cat,
            type=kind,
            size=size,
            color=color,
            material=("100% Algodón", "Polycotton", "Microfibra")[i % 3],
            threads=threads,
            family=f"FAM{i // 40}-{color}",
            attributes=(("Estilo", "Liso"), ("Marca", "Cannon Home")),
        )
        i += 1
    return Knowledge("", {}, {}, products=products)


def test_find_products_stays_well_inside_the_tool_budget_on_two_thousand_products() -> None:
    big = _synthetic()
    asks = [
        {"query": "sábanas king blancas 300 hilos"},
        {"query": "plumón de dos plazas gris"},
        {"query": "quilt super king beige algodón"},
        {"query": "something nothing matches at all"},
        {"type": "sábanas", "size": "1,5 plazas", "color": "azul", "threads_min": 300},
        {"query": "funda plumón king", "material": "microfibra"},
    ]
    times: list[float] = []
    for _ in range(5):
        for ask in asks:
            started = time.perf_counter()
            big.find_products(**ask)
            times.append((time.perf_counter() - started) * 1000)
    assert statistics.median(times) < 8, times
    assert max(times) < 20, times
    hit = big.find_products(query="sábanas king blancas 300 hilos").products[0]
    assert (hit.size, hit.color, hit.threads) == ("King", "Blanco", 300)
    started = time.perf_counter()
    siblings = big.siblings(hit)
    assert (time.perf_counter() - started) * 1000 < 5 and siblings


# ─── Moves ─────────────────────────────────────────────────────────────────────


async def test_a_move_returns_at_once_and_claims_nothing() -> None:
    llm = _llm()
    async with demo("cannonhome", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        before = len(llm.calls)
        turn = await rig.driver.user_says("Ábreme las de dos plazas.")
        check_turn(rig, turn)
        assert rig.command("open_product") == {"path": S2, "tab": None}
        assert len(llm.calls) == before + 1
        await rig.driver.user_says("Sigamos.")
        opened = _every(llm.captured_contents[-1], "open_product")[-1]
        assert "Sent to the page; it has not happened yet. Say only what you are doing" in opened
        assert "never that it is done" in opened


async def test_a_move_with_no_words_says_its_line_without_asking_again() -> None:
    llm = _llm()
    async with demo("cannonhome", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        before = len(llm.calls)
        turn = await rig.driver.user_says("Ábreme las king.")
        assert rig.command("open_product") == {"path": SK, "tab": None}
        assert turn.text == ch._LANDED["product"]["es"]
        assert len(llm.calls) == before + 1


async def test_the_pages_answer_is_talked_through_once_with_tools_off() -> None:
    llm = _llm()
    seen = _recording(llm)
    async with demo("cannonhome", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Ábreme las de dos plazas.")
        assert _idle_windows(rig)[-1] == _IDLE_MS
        # The product page answers the move: talked through in the short quiet spell.
        await _page(rig, "product_shown", _shown(source="graphql", price=28495))
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        before = len(seen)
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert "Esto es lo que hizo la página." in turn.text
        (talk,) = seen[before:]
        assert talk.tool_config == _TOOLS_OFF
        said = _texts(llm.captured_contents[-1])
        assert (
            "The page answered what you sent it: open_product done: the product page shows" in said
        )
        # His talk-through's page cue: a move is the page they are on, so it may
        # cue; but nothing is talked through twice.
        assert _idle_windows(rig)[-1] == _IDLE_MS
        await rig.driver.user_idle(level=1, idle_ms=_IDLE_MS)
        assert (
            "The page answered what you sent it"
            not in _texts(llm.captured_contents[-1])[len(said) :]
        )


async def test_a_failed_move_is_said_plainly_and_either_field_name_is_read() -> None:
    llm = _llm()
    async with demo("cannonhome", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Ábreme las de dos plazas.")
        await _page(rig, "command_failed", {"command": "open_product", "error": "page not found"})
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        seen = _texts(llm.captured_contents[-1])
        assert "[Not done on the page (open_product): page not found." in seen
        assert "open_product not done: page not found" in seen
        # The sibling extensions name it `reason`: read too, never dropped.
        await rig.driver.user_says("Busca toalla blanca.")
        await _page(rig, "command_failed", {"command": "search_products", "reason": "no box"})
        await rig.driver.user_says("Sigamos.")
        assert "(search_products): no box." in _texts(llm.captured_contents[-1])


async def test_the_pages_answer_is_not_talked_through_when_the_visitor_speaks_first() -> None:
    llm = _llm()
    async with demo("cannonhome", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Busca toalla blanca.")
        assert rig.command("search_products") == {"query": "toalla blanca", "open_index": None}
        await _page(
            rig,
            "search_suggest",
            {
                "query": "toalla blanca",
                "items": [{"name": "Toalla Inventada Blanco 700g", "path": TOWEL, "price": 13990}],
                "categories": ["Toallas de baño"],
            },
        )
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        await rig.driver.user_says("Sigamos.")
        seen = _texts(llm.captured_contents[-1])
        assert (
            "[The search box suggests for “toalla blanca”: 1. Toalla Inventada Blanco 700g" in seen
        )
        assert "$13.990 (say: trece mil novecientos noventa pesos)" in seen
        assert "The page answered what you sent it" not in seen
        assert _idle_windows(rig)[-1] == _IDLE_MS


async def test_one_move_at_a_time_the_next_follows_the_answer() -> None:
    llm = _llm()
    async with demo("cannonhome", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Ábreme las king.")
        await rig.driver.user_says("Y agrégala al carro.")
        assert _commands(rig, "add_to_cart") == [], "an add was sent while the page loaded"
        await rig.driver.user_says("Sigamos.")
        queued = _every(llm.captured_contents[-1], "add_to_cart")[-1]
        assert queued.startswith("Queued, not sent yet: the page is still working")
        # The product page answers the open: the add goes now, and only then.
        await _page(rig, "product_shown", _shown(path=SK, price=40000))
        assert _commands(rig, "add_to_cart") == [{"path": SK, "qty": 1}]


async def test_add_to_cart_carries_the_quantity_and_nothing_reaches_the_checkout() -> None:
    llm = _llm()
    async with demo("cannonhome", llm) as rig:
        await rig.driver.start_session(init={"path": S2})
        await rig.driver.user_says("Agrégame dos al carro.")
        assert rig.command("add_to_cart") == {"path": S2, "qty": 2}
        await _page(
            rig,
            "cart_state",
            {
                "items": [{"name": "Sábanas 2 Plazas", "path": S2, "qty": 2, "price": 28495}],
                "count": 2,
                "subtotal": 56990,
                "free_shipping_left": 93010,
            },
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        seen = _texts(llm.captured_contents[-1])
        assert "add_to_cart done: the cart has 2 items" in seen
        assert "$93.010 (say: noventa y tres mil diez pesos) more for free shipping" in seen
        assert "Finalizar compra is theirs to press" in seen
        # Out of range, or not a product: refused, nothing sent.
        await rig.driver.user_says("Agrégame quince.")
        await rig.driver.user_says("Agrega una que no existe.")
        await rig.driver.user_says("Sigamos.")
        refused = _every(llm.captured_contents[-1], "add_to_cart")
        assert any("the quantity is one to ten" in r for r in refused)
        assert any("is not a product the store has" in r for r in refused)
        assert len(_commands(rig, "add_to_cart")) == 1
        # Nothing he sent names the checkout, the account or a payment.
        for c in rig.driver.ui_commands:  # type: ignore[attr-defined]
            wire = str(c).lower()
            assert "checkout" not in wire.replace("/checkout/cart", ""), c
            assert not {"pay", "login", "rut"} & set(wire.replace('"', " ").split()), c
        assert not {"checkout", "place_order", "pay"} & set(rig.actions())


async def test_filters_are_the_listings_own_options() -> None:
    llm = _llm()
    async with demo("cannonhome", llm) as rig:
        await rig.driver.start_session(init={"path": SHEETS})
        await rig.driver.user_says("Filtra las king blancas.")
        assert rig.command("filter_listing") == {
            "category_path": SHEETS,
            "size": "King",
            "color": "Blanco",
            "threads": None,
            "material": None,
            "sort": "price_asc",
        }
        await _page(rig, "command_done", {"command": "filter_listing", "detail": "filtered"})
        await rig.driver.user_says("Filtra las de seda.")
        await rig.driver.user_says("Sigamos.")
        refused = _every(llm.captured_contents[-1], "filter_listing")[-1]
        assert refused == (
            "Not done: material 'seda' is not an option of this listing "
            "(it lists: Polycotton, 100% Algodón)."
        )
        assert len(_commands(rig, "filter_listing")) == 1


async def test_check_prices_reads_live_and_says_what_was_not_found() -> None:
    llm = _llm()
    async with demo("cannonhome", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("¿Cuánto cuestan las dos?")
        assert rig.command("check_prices") == {"paths": [S2, SK]}
        await _page(
            rig,
            "prices_read",
            {
                "items": [
                    {
                        "path": S2,
                        "sku": "JSINV300P20B",
                        "name": "Sábanas 2 Plazas",
                        "price": 28495,
                        "regular_price": 56990,
                        "in_stock": True,
                        "qty": None,
                    }
                ],
                "missing": [SK],
            },
        )
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        seen = _texts(llm.captured_contents[-1])
        assert "[Live prices: Sábanas 2 Plazas" in seen and "$28.495" in seen
        assert f"Not found: {SK} — not buyable right now" in seen
        assert "check_prices done: read 1 live prices, 1 not found" in seen


async def test_a_question_about_the_call_moves_nothing() -> None:
    async with demo("cannonhome", _llm()) as rig:
        await rig.driver.start_session(init={"path": S2})
        await rig.driver.user_says("Can I speak in English?")
        assert "add_to_cart" not in rig.actions()


async def test_a_reply_that_only_promises_is_asked_again_with_tools_off() -> None:
    llm = _llm()
    seen = _recording(llm)
    async with demo("cannonhome", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        before = len(seen)
        await rig.driver.user_says("¿Y las toallas?")
        first, again = seen[before:]
        assert first.tool_config is None
        assert again.tool_config == _TOOLS_OFF


async def test_the_prompt_carries_the_stores_rules() -> None:
    prompt = ch._prompt(STORE, ch.date(2030, 3, 4))
    assert "Today is Monday, 04 March 2030, in Santiago." in prompt
    for rule in (
        "# Prices and stock",
        "# Sizes and colours",
        "# The cart",
        "CHECKOUT IS THEIRS",
        'A line that says "Live check" wins',
        "you can't see the price right now, and open the product",
        "no size or colour picker",
        "then one product on their screen with its live price",
        '"carro" or "carro de compras", never "cesta"',
        f"- {SHEETS} — Sábanas (tamaño: 1 Plaza, 1.5 Plazas",
        "- Ropa de Cama > Sábanas (4); tamaños: 1.5 Plazas, 2 Plazas, King; hilos: 300",
    ):
        assert rule in prompt, rule


async def test_the_first_suggestion_the_model_names_is_the_pages_index_zero() -> None:
    """The model counts suggestions from 1, as the visitor does; the adapter
    indexes the dropdown from 0."""
    async with demo("cannonhome", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Ábreme la primera toalla.")
        assert rig.command("search_products") == {"query": "toalla blanca", "open_index": 0}
