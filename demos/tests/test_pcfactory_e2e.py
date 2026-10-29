"""Javier, PC Factory's voice tech advisor, end to end over the wire — no network, no LLM key.

The real ``PcFactoryBrain`` on a real ``brain_server`` socket, driven by the
conformance ``VoqalizeDriver``, with only the model scripted. The knowledge is a
small invented store in the crawl's own shape — pages, a category with its
facets, two stores — put in place of the committed one: no test depends on what
the crawl found this week.

What this demo earns that others do not:

**The catalogue is read live, and he narrates with cues.** "¿Qué me
recomiendas?" is ``find_products``: the page reads the store's own catalogue in
the visitor's browser and the products come back as an event; he talks them
through, opens the best one with a page cue, and walks its specifications with
a tab cue and a ring per spec as he says it.

**Three prices, the transfer one first.** Every line he is given carries the
Transferencia / Débito price with how to say it, the card price beside it, and
the reference price only as a real saving.

**Only after a yes, and never past Tipo de entrega.** An add, a coupon or the
checkout is refused unless the visitor asked for it or said yes; the checkout
stops at Tipo de entrega, and a RUT, a password or a card they say is never
sent anywhere.

Run: ``cd demos && uv run pytest tests/test_pcfactory_e2e.py``
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any, cast

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import (
    ScriptedOpenAI,
    input_texts,
    reply,
    reply_and_call,
    tool_results_of,
)

from ._harness import _configs, check_greeting, check_turn, check_voice_pair, demo

discover()

from voqalize_demos._loaded.pcfactory import brain as pc  # noqa: E402
from voqalize_demos._loaded.pcfactory import knowledge as kb  # noqa: E402
from voqalize_demos._loaded.pcfactory.brain import (  # noqa: E402
    _DONE_MS,
    _IDLE_MS,
    _TALK_THROUGH_MS,
    TOGGLE_CONFIRM,
    greeting,
)
from voqalize_demos._loaded.pcfactory.knowledge import (  # noqa: E402
    Category,
    Facet,
    Faq,
    Knowledge,
    Page,
    Section,
    Store,
)

NOTEBOOKS = "/categoria/computadores-y-tablets/notebooks/notebooks"
RETIRO = "/centro-de-ayuda/compra-con-retiro-en-tienda"
LENOVO = "/producto/57233"
HP = "/producto/57695"
LENOVO_NAME = "Notebook Lenovo IdeaPad Slim 3 15IRH8 Intel Core i5-13420H 16GB 512GB SSD"
HP_NAME = "Notebook HP 14-ep1330la Intel Core i5 8GB 512GB SSD"

STORE = Knowledge(
    l1="pcFactory es una tienda chilena de tecnología. Compiled 2026-10-29.",
    topics={},
    pages={
        "/": Page(
            "/",
            "pc Factory, Compra y retira de inmediato en tienda - pcfactory.cl",
            sections=(
                Section("Te recomendamos"),
                Section("Ofertas y Lanzamientos"),
                Section("Cupones", "LEN50 $50.000 dcto. Adicional. Vence el 02 de Noviembre."),
            ),
            kind="home",
        ),
        RETIRO: Page(
            RETIRO,
            "Compra con retiro en tienda",
            sections=(Section("Retiro en tienda", "El retiro en tienda es gratis."),),
            faqs=(
                Faq(
                    "¿Cuánto tiempo tengo para retirar mi compra?",
                    "Tienes 15 días hábiles desde la emisión de la boleta.",
                ),
            ),
            kind="help",
        ),
        "/tiendas": Page("/tiendas", "Localizador de tiendas", kind="stores"),
    },
    categories={
        NOTEBOOKS: Category(
            id=425,
            path=NOTEBOOKS,
            name="Notebooks",
            parent="/categoria/computadores-y-tablets/notebooks",
            level=3,
            products=158,
            facets=(
                Facet("Marcas", "marcas", ("Lenovo", "HP", "ASUS", "Acer")),
                Facet("RAM", "735~22~", ("8GB", "16GB", "32GB")),
                Facet("Procesador", "735~1~", ("Intel Core i5", "AMD Ryzen 7")),
                Facet("Tiendas", "sucursales", ("Internet", "Maipú", "Costanera Center")),
            ),
        ),
        "/categoria/computadores-y-tablets": Category(
            id=636,
            path="/categoria/computadores-y-tablets",
            name="Computadores y Tablets",
            level=1,
        ),
    },
    stores=(
        Store("2", "Maipú", "Santiago", "Av. Pajaritos 2000", "Maipú", "Metropolitana"),
        Store("7", "Costanera Center", "Santiago", "Av. Andrés Bello 2425", "Providencia"),
        Store("21", "Concepción", "Sur", "Barros Arana 500", "Concepción", "Biobío"),
    ),
)

#: The two notebooks find_products reads for "notebook hasta 700 mil".
FOUND = {
    "query": "notebook",
    "category_id": 425,
    "brand": None,
    "min_price": None,
    "max_price": 700000,
    "total": 41,
    "items": [
        {
            "path": LENOVO,
            "id": 57233,
            "name": LENOVO_NAME,
            "brand": "Lenovo",
            "price": 599990,
            "card_price": 619990,
            "regular_price": 799990,
            "stock": "+100",
        },
        {
            "path": HP,
            "id": 57695,
            "name": HP_NAME,
            "brand": "HP",
            "price": 529990,
            "card_price": 546390,
            "regular_price": 529990,
            "stock": "5",
        },
    ],
}

SPECS = [
    {"label": "Procesador", "value": "Intel Core i5-13420H"},
    {"label": "Memoria RAM", "value": "16 GB DDR5"},
    {"label": "Almacenamiento", "value": "512 GB SSD"},
    {"label": "Pantalla", "value": '15.6" FHD'},
]


def _product(source: str = "page", **over: Any) -> dict[str, Any]:
    return {
        "path": LENOVO,
        "id": 57233,
        "name": LENOVO_NAME,
        "brand": "Lenovo",
        "price": 599990,
        "card_price": 619990,
        "regular_price": 799990,
        "online_stock": "+100",
        "stores_with_stock": 12,
        "warranty": "12 meses",
        "promo_until": "2026-11-02",
        "specs": SPECS,
        "source": source,
    } | over


def _listing(**over: Any) -> dict[str, Any]:
    return {
        "path": NOTEBOOKS,
        "title": "Notebooks",
        "count": 38,
        "filters": [
            {"facet": "Marcas", "on": ["Lenovo"], "options": ["Lenovo", "HP", "ASUS"]},
            {"facet": "RAM", "on": [], "options": ["8GB", "16GB"]},
        ],
        "sort": "",
        "items": [
            {"path": LENOVO, "name": LENOVO_NAME, "price": 599990, "regular_price": 799990},
        ],
    } | over


@pytest.fixture(autouse=True)
def _store(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every session reads the invented store."""
    monkeypatch.setattr(kb, "KNOWLEDGE", STORE)
    yield


def _texts(items: list[Any]) -> str:
    return input_texts(items)


def _llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            "Hola, ¿cómo estás?": reply("Muy bien. ¿Qué estás buscando hoy?"),
            "I need a laptop for university. What do you recommend?": reply(
                "Happy to help. What's your budget?"
            ),
            "¿Qué notebook me recomiendas? Es para la U, hasta setecientos mil.": reply_and_call(
                "Te busco opciones.",
                "find_products",
                args={"query": "notebook", "category": "Notebooks", "max_price": 700000},
            ),
            # The products the page read, talked through: he opens the best one.
            "find_products done": reply(
                "{page: /producto/57233} Te abro el Lenovo, el que más te conviene. "
                "Cuesta quinientos noventa y nueve mil pesos con transferencia."
            ),
            "Cuéntame de sus especificaciones.": reply(
                "{tab: specs} Mira las especificaciones. {show: procesador} Trae un Core i cinco, "
                "rápido para todo. {show: memoria ram} Con dieciséis gigas de RAM. "
                "{show: Tarjeta Inventada} Y nada más."
            ),
            "Ábreme el HP.": reply_and_call("Te abro el HP.", "open_product", args={"path": HP}),
            "Muéstrame los Lenovo con dieciséis gigas.": reply(
                "{filter: Marcas | lenovo} Te dejo solo los Lenovo. "
                "{filter: RAM | 16 GB} Con dieciséis gigas. "
                "{sort: menor precio} Y del más barato al más caro."
            ),
            "¿Y con pantalla OLED?": reply("{filter: Pantalla | OLED} Te dejo los OLED."),
            "¿Me sirve este?": reply_and_call(
                "Te sirve para la U.", "add_to_cart", args={"path": LENOVO, "qty": 1}
            ),
            "Sí, agrégalo.": reply_and_call(
                "Te lo agrego al carro.", "add_to_cart", args={"path": LENOVO, "qty": 1}
            ),
            "Sigamos.": reply("Claro, sigamos."),
            "Sí, quiero pagar.": reply_and_call(
                "Te llevo al tipo de entrega.", "start_checkout", args={}
            ),
            "Elige tú el despacho.": reply("Eso lo eliges tú en la página."),
            "Mi RUT es 12.345.678-5, ¿lo pones tú?": reply_and_call(
                "Eso lo completas tú en la página.",
                "search_products",
                args={"query": "12.345.678-5"},
            ),
            "¿Lo tienen en la tienda de Maipú?": reply_and_call(
                "Te reviso el stock en Maipú.", "check_stock", args={"store": "maipu"}
            ),
            "check_stock done": reply("{store: Maipú} En Maipú quedan tres."),
            "¿Cuánto tiempo tengo para retirar?": reply("Tienes quince días hábiles."),
        }
    )


async def _page(rig: object, event: str, payload: dict[str, object]) -> None:
    await rig.driver.send_ui_event(event, payload)  # type: ignore[attr-defined]
    # `on_rtvi` takes no floor and there is nothing to await: give it a moment.
    await asyncio.sleep(0.1)


async def _state(rig: object, name: str, data: dict[str, Any], *, by: str = "visitor") -> None:
    """One of the page's Stage state events, as the extension sends it."""
    await _page(rig, "stage_event", {"name": name, "by": by, "data": data})


def _commands(rig: object, name: str) -> list[dict[str, Any]]:
    return [
        c["payload"]
        for c in rig.driver.ui_commands  # type: ignore[attr-defined]
        if c.get("command") == name
    ]


def _cues(rig: object) -> list[dict[str, Any]]:
    return _commands(rig, "stage_cue")


def _moves(rig: object, move: str) -> list[dict[str, Any]]:
    return [m["args"] for m in _commands(rig, "stage_move") if m["move"] == move]


def _move(rig: object, move: str) -> dict[str, Any]:
    sent = _moves(rig, move)
    assert sent, f"no {move} move: {[m['move'] for m in _commands(rig, 'stage_move')]}"
    return sent[0]


async def _answer(rig: object, move: str, outcome: str = "applied", detail: str = "") -> None:
    """The page's one result for the last ``move`` sent."""
    sent = [m for m in [*_commands(rig, "stage_move"), *_cues(rig)] if m["move"] == move]
    assert sent, f"no {move} was sent"
    await _page(
        rig,
        "stage_result",
        {"call_ref": sent[-1]["call_ref"], "move": move, "outcome": outcome, "detail": detail},
    )


def _idle_windows(rig: object) -> list[int | None]:
    return [c.idle.timeout_ms for c in _configs(rig) if c.idle is not None]  # type: ignore[arg-type]


# ─── Voice, language and the greeting ──────────────────────────────────────────


async def test_the_greeting_is_spanish_short_and_the_voice_reaches_the_wire() -> None:
    async with demo("pcfactory", _llm()) as rig:
        opener = await rig.driver.start_session(init={"surface": "pcfactory-ext", "path": "/"})
        check_greeting(rig, opener)
        assert opener is not None
        assert opener.text == pc.for_the_voice(greeting("/", "es"))
        assert opener.text.startswith("Hola, soy Javier, tu asesor de voz de PC Factory.")
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _idle_windows(rig) == [_IDLE_MS]


@pytest.mark.parametrize(
    ("path", "words"),
    [
        ("/", "¿Qué estás buscando?"),
        (NOTEBOOKS, "tu notebook"),
        ("/categoria/partes-y-piezas-componentes/tarjetas-graficas", "tarjeta de video"),
        ("/busqueda-avanzada?search=monitor+27", "estos resultados"),
        (f"{LENOVO}-lenovo-ideapad?origin=PCF", "este producto"),
        ("/carro", "tu carro"),
        ("/checkout/tipo-entrega", "los eliges tú"),
        ("/tiendas", "tienda más cercana"),
    ],
)
def test_the_opener_follows_the_page(path: str, words: str) -> None:
    line = greeting(path, "es")
    assert line.startswith("Hola, soy Javier")
    assert words in line, line
    assert len(line.split()) <= 26, line
    assert greeting(path, "en").startswith("Hi, I'm Javier, PC Factory's voice advisor.")


async def test_the_toggle_moves_both_legs_to_english_and_confirms() -> None:
    async with demo("pcfactory", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(rig, "language_requested", {"language": "en"})
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert rig.command("language_changed") == {"language": "en"}
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert turn.text == TOGGLE_CONFIRM["en"]


async def test_english_heard_moves_the_call_and_spanish_brings_it_back() -> None:
    async with demo("pcfactory", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("I need a laptop for university. What do you recommend?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        await rig.driver.user_says("Hola, ¿cómo estás?")
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _commands(rig, "language_changed") == [{"language": "en"}, {"language": "es"}]


def test_the_brand_is_said_as_pc_factory() -> None:
    assert pc.for_the_voice("Bienvenido a pcFactory.") == "Bienvenido a PC Factory."
    assert pc.names_for_the_voice("PCFACTORY y pc Factory") == "PC Factory y PC Factory"
    assert pc.names_for_the_voice("www.pcfactory.cl") == "www.pcfactory.cl"


# ─── Finding, opening and narrating a product ──────────────────────────────────


async def test_find_products_reads_live_and_he_opens_the_best_with_a_cue() -> None:
    llm = _llm()
    async with demo("pcfactory", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        before = len(llm.requests)
        turn = await rig.driver.user_says(
            "¿Qué notebook me recomiendas? Es para la U, hasta setecientos mil."
        )
        check_turn(rig, turn)
        # A move, not a marked read: one request, and the words said first.
        assert len(llm.requests) == before + 1
        assert turn.text.startswith("Te busco opciones.")
        assert _move(rig, "find_products") == {
            "query": "notebook",
            "category_id": 425,
            "brand": None,
            "min_price": None,
            "max_price": 700000,
            "sort": None,
        }
        # The page's read, then its result: talked through in the short spell.
        await _page(rig, "products_found", FOUND)
        await _answer(rig, "find_products", detail="41 products; 2 shown")
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        talk = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, talk)
        seen = _texts(llm.captured_inputs[-1])
        assert llm.requests[-1].get("tool_choice") == "none"
        assert "find_products done: 41 products; 2 shown" in seen
        # Each product with its three prices: transfer first, with how to say it.
        assert (
            f"1. {LENOVO_NAME} ({LENOVO}), Lenovo: Transferencia / Débito $599.990 (say: "
            "quinientos noventa y nueve mil novecientos noventa pesos), otros medios de pago "
            "$619.990" in seen
        )
        assert "precio de referencia $799.990, a real saving of 25%" in seen
        # The HP's reference price is its own price: no saving to claim.
        assert "$529.990, a real saving" not in seen
        # He opens the one he recommends with a page cue, by an id he read.
        (opened,) = _cues(rig)
        assert (opened["move"], opened["args"]) == ("page.open", [LENOVO])
        assert opened["at"].startswith("Te abro el Lenovo")


async def test_on_the_product_he_walks_its_specs_as_he_says_them() -> None:
    async with demo("pcfactory", _llm()) as rig:
        await rig.driver.start_session(init={"path": f"{LENOVO}-lenovo-ideapad?origin=PCF"})
        await _state(rig, "product.shown", _product())
        await _state(rig, "product.checked", _product("api", price=589990))
        turn = await rig.driver.user_says("Cuéntame de sus especificaciones.")
        check_turn(rig, turn)
        assert "{" not in turn.text
        cues = [(c["move"], c["args"]) for c in _cues(rig)]
        # The tab, then each spec row by its label as the page writes it; a
        # label the product does not have is rung as written, never invented
        # into another row.
        assert cues == [
            ("product.tab", ["specs"]),
            ("page.show", ["Procesador"]),
            ("page.show", ["Memoria RAM"]),
            ("page.show", ["Tarjeta Inventada"]),
        ]
        anchors = [c["at"] for c in _cues(rig)]
        assert anchors[0].startswith("Mira las especificaciones.")
        assert anchors[1].startswith("Trae un Core i cinco")
        assert anchors[2].startswith("Con dieciséis gigas")


async def test_the_live_read_wins_and_carries_the_specs() -> None:
    llm = _llm()
    async with demo("pcfactory", llm) as rig:
        await rig.driver.start_session(init={"path": LENOVO})
        await _state(rig, "product.shown", _product())
        await _state(rig, "product.checked", _product("api", price=589990, specs=[]))
        # A late page copy never undoes the live read.
        await _state(rig, "product.shown", _product(price=650000))
        brain = cast("pc.PcFactoryBrain", rig.brain)
        read = await brain.read_screen(pc.ReadRequest(slice="product"))
        assert "Transferencia / Débito $589.990" in read
        assert "Procesador: Intel Core i5-13420H" in read
        assert "In stock in 12 stores (approximate, 20 minutes behind)." in read


async def test_open_product_lands_with_its_written_line() -> None:
    llm = _llm()
    async with demo("pcfactory", llm) as rig:
        await rig.driver.start_session(init={"path": NOTEBOOKS})
        await _state(
            rig,
            "listing.shown",
            _listing(
                items=[
                    {"path": HP, "name": HP_NAME, "price": 529990},
                ]
            ),
        )
        turn = await rig.driver.user_says("Ábreme el HP.")
        check_turn(rig, turn)
        assert _move(rig, "open_product") == {"path": HP, "tab": None}
        await _state(
            rig,
            "product.shown",
            _product(path=HP, id=57695, name=HP_NAME, price=529990, regular_price=529990),
            by="agent",
        )
        assert _idle_windows(rig)[-1] == _DONE_MS
        asked = len(llm.requests)
        landed = await rig.driver.user_idle(level=1, idle_ms=_DONE_MS)
        assert landed.text.startswith(
            "Aquí está el Notebook HP, a quinientos veintinueve mil novecientos noventa pesos "
            "con transferencia."
        )
        assert len(llm.requests) == asked + 1


# ─── Filters he narrates ───────────────────────────────────────────────────────


async def test_filter_cues_are_the_listings_own_facets_and_options() -> None:
    async with demo("pcfactory", _llm()) as rig:
        await rig.driver.start_session(init={"path": NOTEBOOKS})
        turn = await rig.driver.user_says("Muéstrame los Lenovo con dieciséis gigas.")
        check_turn(rig, turn)
        assert "{" not in turn.text and "filter" not in turn.text
        assert [(c["move"], c["args"]) for c in _cues(rig)] == [
            ("commerce.filter", ["Marcas", "Lenovo", NOTEBOOKS]),
            ("commerce.filter", ["RAM", "16GB", NOTEBOOKS]),
            ("commerce.sort", ["price_asc", NOTEBOOKS]),
        ]
        # The filtered listing lands: his written line names it.
        await _state(
            rig,
            "listing.filtered",
            _listing(
                filters=[
                    {"facet": "Marcas", "on": ["Lenovo"], "options": []},
                    {"facet": "RAM", "on": ["16GB"], "options": []},
                ],
                count=12,
            ),
            by="agent",
        )
        # The sort of the same reply is still to land: his line waits for it,
        # and then names every filter of the turn, the facets said naturally.
        await _state(
            rig,
            "listing.sorted",
            _listing(
                filters=[
                    {"facet": "Marcas", "on": ["Lenovo"], "options": []},
                    {"facet": "RAM", "on": ["16GB"], "options": []},
                ],
                count=12,
                sort="price_asc",
            ),
            by="agent",
        )
        landed = await rig.driver.user_idle(level=1, idle_ms=_DONE_MS)
        assert landed.text.startswith(
            "Aquí hay 12 de Lenovo, con 16GB de RAM. El primero es el Notebook Lenovo IdeaPad"
        ), landed.text


async def test_a_facet_the_listing_lacks_is_never_sent_and_is_said() -> None:
    llm = _llm()
    async with demo("pcfactory", llm) as rig:
        await rig.driver.start_session(init={"path": NOTEBOOKS})
        await rig.driver.user_says("¿Y con pantalla OLED?")
        assert _cues(rig) == []
        await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        seen = _texts(llm.captured_inputs[-1])
        assert (
            "[Not done on the page ({filter: Pantalla | OLED}): this listing has no facet" in seen
        )
        assert "it has: Marcas, RAM, Procesador, Tiendas" in seen


# ─── The cart: only after a yes ────────────────────────────────────────────────


async def test_add_to_cart_waits_for_a_yes_and_then_says_it_is_done() -> None:
    llm = _llm()
    async with demo("pcfactory", llm) as rig:
        await rig.driver.start_session(init={"path": LENOVO})
        await _state(rig, "product.shown", _product())
        # The model called it on a question: refused, nothing sent.
        await rig.driver.user_says("¿Me sirve este?")
        assert _moves(rig, "commerce.cart_add") == []
        # The yes: sent.
        await rig.driver.user_says("Sí, agrégalo.")
        refused = tool_results_of(llm.captured_inputs[-1], "add_to_cart")
        assert any("they have not asked to add it to the cart" in r for r in refused)
        assert _moves(rig, "commerce.cart_add") == [{"path": LENOVO, "qty": 1}]
        await _state(
            rig,
            "cart.changed",
            {
                "count": 1,
                "subtotal": 599990,
                "items": [{"path": LENOVO, "name": LENOVO_NAME, "qty": 1, "price": 599990}],
            },
            by="agent",
        )
        await _answer(rig, "commerce.cart_add", detail=f"added 1 x {LENOVO_NAME}; the cart has 1")
        assert _idle_windows(rig)[-1] == _DONE_MS
        done = await rig.driver.user_idle(level=1, idle_ms=_DONE_MS)
        check_turn(rig, done)
        assert done.text.startswith("Listo, Notebook Lenovo IdeaPad Slim 3 ya está en tu carro.")
        brain = cast("pc.PcFactoryBrain", rig.brain)
        cart = await brain.read_screen(pc.ReadRequest(slice="cart"))
        assert "Total Transferencia / Débito $599.990" in cart
        assert "Delivery is priced only in the checkout; store pickup is free." in cart


async def test_checkout_goes_as_a_guest_and_stops_at_tipo_de_entrega() -> None:
    llm = _llm()
    async with demo("pcfactory", llm) as rig:
        await rig.driver.start_session(init={"path": "/carro"})
        await _state(
            rig,
            "cart.changed",
            {
                "count": 1,
                "subtotal": 599990,
                "items": [{"path": LENOVO, "name": LENOVO_NAME, "qty": 1}],
            },
        )
        await rig.driver.user_says("Sí, quiero pagar.")
        assert _move(rig, "start_checkout") == {}
        await _state(
            rig,
            "checkout.changed",
            {
                "step": "delivery",
                "options": ["Retiro en tienda", "Despacho a Domicilio"],
                "chosen": "",
            },
            by="agent",
        )
        await _answer(rig, "start_checkout", detail="on Tipo de entrega")
        done = await rig.driver.user_idle(level=1, idle_ms=_DONE_MS)
        assert done.text.startswith(
            "Listo, aquí eliges retiro en tienda, que es gratis, o despacho a domicilio."
        )
        seen = _texts(llm.captured_inputs[-1])
        assert (
            "Tipo de entrega step: Retiro en tienda, Despacho a Domicilio — theirs to choose"
            in seen
        )
        assert "The RUT, any password, the address and the payment are theirs to type." in seen
        # Asked to choose for them: nothing is sent.
        await rig.driver.user_says("Elige tú el despacho.")
        sent = {m["move"] for m in _commands(rig, "stage_move")}
        assert sent == {"start_checkout"}
        for c in rig.driver.ui_commands:  # type: ignore[attr-defined]
            wire = str(c).lower()
            assert "login" not in wire and "rut" not in wire.replace("route", ""), c


async def test_a_rut_they_say_is_never_sent_or_repeated() -> None:
    llm = _llm()
    async with demo("pcfactory", llm) as rig:
        await rig.driver.start_session(init={"path": "/checkout/tipo-entrega"})
        turn = await rig.driver.user_says("Mi RUT es 12.345.678-5, ¿lo pones tú?")
        check_turn(rig, turn)
        assert "12.345.678" not in turn.text
        seen = _texts(llm.captured_inputs[-1])
        assert "What the visitor just said holds a RUT. Never repeat it" in seen
        assert _moves(rig, "commerce.search") == []
        await rig.driver.user_says("Sigamos.")
        refused = tool_results_of(llm.captured_inputs[-1], "search_products")
        assert any("that holds a RUT, which is theirs to type" in r for r in refused)
        for c in rig.driver.ui_commands:  # type: ignore[attr-defined]
            assert "12.345.678" not in str(c), c


def test_no_cue_opens_the_checkout_the_account_or_a_payment() -> None:
    for path in ("/checkout", "/checkout/tipo-entrega", "/checkout/pago", "/mi-cuenta", "/login"):
        assert pc._NEVER.match(kb.canonical_path(path)), path
    assert not pc._NEVER.match("/carro")


@pytest.mark.parametrize(
    ("kind", "last", "ok"),
    [
        ("cart", "Sí, dale.", True),
        ("cart", "Ya.", True),
        ("cart", "Agrégalo al carro.", True),
        ("cart", "¿Cuánto cuesta?", False),
        ("cart", "No, todavía no.", False),
        ("coupon", "Aplica el cupón LEN50.", True),
        ("checkout", "Quiero pagar.", True),
        ("checkout", "¿Y la garantía?", False),
    ],
)
def test_a_confirmed_move_needs_their_ask_or_their_yes(kind: str, last: str, ok: bool) -> None:
    assert pc.consents(kind, last) is ok


# ─── Stock by store, and the stores ────────────────────────────────────────────


async def test_stock_in_a_store_is_read_and_the_store_shown() -> None:
    llm = _llm()
    async with demo("pcfactory", llm) as rig:
        await rig.driver.start_session(init={"path": LENOVO})
        await _state(rig, "product.shown", _product())
        await rig.driver.user_says("¿Lo tienen en la tienda de Maipú?")
        # The product in front, the store by its listed name.
        assert _move(rig, "check_stock") == {"path": LENOVO, "store": "Maipú"}
        await _page(
            rig,
            "stock_read",
            {
                "path": LENOVO,
                "id": 57233,
                "name": LENOVO_NAME,
                "online": "+100",
                "stores": [
                    {"name": "Maipú", "zone": "Santiago", "qty": "3", "pickup": True},
                    {"name": "Concepción", "zone": "Sur", "qty": "1", "pickup": True},
                ],
                "asked": "maipu",
                "matched": "Maipú",
            },
        )
        await _answer(rig, "check_stock", detail="Maipú: 3")
        talk = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, talk)
        seen = _texts(llm.captured_inputs[-1])
        assert "approximate, 20 minutes behind: online +100; in stores: Maipú (Santiago) 3" in seen
        assert "The store they asked about, Maipú, has 3." in seen
        (store,) = _cues(rig)
        assert (store["move"], store["args"]) == ("stores.show", ["Maipú"])


async def test_a_question_on_a_product_page_is_answered_in_place() -> None:
    """On a product, "¿cuánto tiempo tengo para retirar?" never takes them
    off it to the retiro page on its own."""
    async with demo("pcfactory", _llm()) as rig:
        await rig.driver.start_session(init={"path": LENOVO})
        await rig.driver.user_says("¿Cuánto tiempo tengo para retirar?")
        assert _cues(rig) == []


def test_the_prompt_teaches_narration_with_cues_and_the_three_prices() -> None:
    prompt = pc._prompt(STORE, pc.date(2030, 3, 4))
    assert "Today is Monday, 04 March 2030, in Santiago." in prompt
    assert "OPEN WITH A CUE" in prompt
    assert '"{tab: specs} Mira las especificaciones. {show: Procesador}' in prompt
    assert 'The headline is "Transferencia / Débito"' in prompt
    assert "Delivery is priced only in the checkout" in prompt
    assert "Notebooks (id 425) /categoria/computadores-y-tablets/notebooks/notebooks" in prompt
    assert "RAM: 8GB, 16GB, 32GB" in prompt
    assert "Santiago: Maipú, Costanera Center (Providencia)" in prompt
    assert "THE RUT, ANY PASSWORD, A CARD AND THE ADDRESS ARE THEIRS" in prompt
