"""Javier, Agroplanet's voice parts adviser, end to end over the wire — no network, no LLM key.

The real ``AgroplanetBrain`` on a real ``brain_server`` socket, driven by the
conformance ``VoqalizeDriver``, with only the model scripted. The knowledge is a
small invented store in the crawl's own shape — pages, categories with their
facets, three stores — put in place of the committed one: no test depends on
what the crawl found this week.

What this demo earns that others do not:

**The catalogue is read live, and he narrates with cues.** "¿Qué aceite me
recomiendas?" is ``find_products``: the page reads the store's own catalogue in
the visitor's browser and the products come back as an event; he talks them
through, opens the best one with a page cue, walks its specifications with a
tab cue and a ring per row, and opens the category menu on a top category.

**One price, or none.** Every line he is given carries the price with how to
say it and the struck price only as a real saving; a product the store shows
as "Confirmar precio en tienda" carries no price at all, and the line says so.

**A quote, not a checkout.** An add, the quote form or a field typed into it
is refused unless the visitor asked for it or said yes; the form is filled
with what they said, and a RUT, a password or a card they say is never sent
anywhere. "Crear cotización" is theirs.

Run: ``cd demos && uv run pytest tests/test_agroplanet_e2e.py``
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

from voqalize_demos._loaded.agroplanet import brain as ag  # noqa: E402
from voqalize_demos._loaded.agroplanet import knowledge as kb  # noqa: E402
from voqalize_demos._loaded.agroplanet.brain import (  # noqa: E402
    _DONE_MS,
    _FORM_PATIENCE,
    _IDLE_MS,
    _TALK_THROUGH_MS,
    TOGGLE_CONFIRM,
    greeting,
)
from voqalize_demos._loaded.agroplanet.knowledge import (  # noqa: E402
    Category,
    Facet,
    Faq,
    Knowledge,
    Page,
    Section,
    Store,
)

LUBRICANTES = "/categoria/lubricantes/AG100"
DESPACHO = "/politica-despacho"
LUBRITEK = "/producto/aceite_lubritek_utf_semisintetico_19l/1173221"
SHELL = "/producto/aceite_shell_rimula_r4_15w40_20l/1180001"
BUJES = "/producto/bujes_de_biela_55_4107_semi_federal_mogul/139083"
LUBRITEK_NAME = "Aceite LUBRITEK UTF Semisintético 19L"
SHELL_NAME = "Aceite Shell Rimula R4 15W40 20L"
BUJES_NAME = "Bujes de Biela 55 4107 Semi Federal Mogul"

STORE = Knowledge(
    l1="Agroplanet es una tienda chilena de repuestos agrícolas. Compiled 2026-10-29.",
    topics={},
    pages={
        "/": Page(
            "/",
            "Agroplanet | Repuestos agrícolas",
            sections=(
                Section("Aprovecha estas oportunidades en Octubre"),
                Section("CATEGORÍAS", "Repuestos para tractor, pastería, lubricantes."),
            ),
            kind="home",
        ),
        DESPACHO: Page(
            DESPACHO,
            "Política de despacho",
            sections=(Section("Despacho a domicilio", "Despachamos a todo Chile."),),
            faqs=(
                Faq(
                    "¿Cuánto demora el despacho?",
                    "Entre 3 y 7 días hábiles según la comuna.",
                ),
            ),
            kind="policy",
        ),
        "/nuestras-tiendas": Page("/nuestras-tiendas", "Nuestras tiendas", kind="stores"),
    },
    categories={
        "/categoria/lubricantes_y_fluidos/AG01": Category(
            code="AG01",
            path="/categoria/lubricantes_y_fluidos/AG01",
            name="Lubricantes Y Fluidos",
            level=1,
            page_name="Lubricantes y Grasas",
        ),
        LUBRICANTES: Category(
            code="AG100",
            path=LUBRICANTES,
            name="Lubricantes",
            parent="/categoria/lubricantes_y_fluidos/AG01",
            level=2,
            products=58,
            facets=(
                Facet("Precio", "price", ("$10.000 - $49.999", "$50.000 - $149.999")),
                Facet("Base", "C_DTE_BASE", ("MINERAL", "SEMISINTETICO")),
                Facet("Viscosidad", "C_DTE_VISCOSIDAD", ("15W40", "10W30", "SAE 90")),
                Facet("Marca", "brand_search", ("LUBRITEK", "SHELL", "MOBIL")),
            ),
        ),
        "/categoria/baterias/AG02": Category(
            code="AG02", path="/categoria/baterias/AG02", name="Baterías", level=1
        ),
        "/categoria/baterias_heavy_duty/1000908": Category(
            code="1000908",
            path="/categoria/baterias_heavy_duty/1000908",
            name="Baterías Heavy Duty",
            parent="/categoria/baterias/AG02",
            level=3,
        ),
    },
    stores=(
        Store(
            "SG0007",
            "Talca",
            address="Av. San Miguel 2950",
            city="Talca",
            region="Maule",
            hours="Lunes a Viernes 09:15 a 18:15",
            phone="+56 9 8920 4716",
        ),
        Store("SG0010", "Los Ángeles", address="Av. Alemania 650", city="Los Ángeles"),
        Store("SG0016", "Puerto Varas", address="Ruta 5 Sur km 1017", region="Los Lagos"),
    ),
)

#: The oils find_products reads for "aceite 15w40".
FOUND = {
    "query": "aceite 15w40",
    "category_code": "AG100",
    "brand": None,
    "total": 14,
    "items": [
        {
            "path": SHELL,
            "sku": "1180001",
            "name": SHELL_NAME,
            "brand": "SHELL",
            "price": 95990,
            "regular_price": 119990,
            "discount": 20,
            "stock": "inStock",
            "stock_level": 40,
        },
        {
            "path": LUBRITEK,
            "sku": "1173221",
            "name": LUBRITEK_NAME,
            "brand": "LUBRITEK",
            "price": 80000,
            "regular_price": 80000,
            "stock": "lowStock",
            "stock_level": 3,
        },
        {
            "path": BUJES,
            "sku": "139083",
            "name": BUJES_NAME,
            "brand": "FEDERAL MOGUL",
            "price": 22000,
            "price_hidden": True,
            "stock": "inStock",
        },
    ],
}

SPECS = [
    {"label": "Unidades por caja", "value": "1"},
    {"label": "País", "value": "Chile"},
    {"label": "Viscosidad", "value": "SAE 10W30"},
]


def _product(source: str = "page", **over: Any) -> dict[str, Any]:
    return {
        "path": LUBRITEK,
        "sku": "1173221",
        "name": LUBRITEK_NAME,
        "brand": "LUBRITEK",
        "maker_code": "AGPLUBLTUTFBLD",
        "price": 80000,
        "stock": "inStock",
        "stock_level": 635,
        "description": "Aceite para transmisión y sistema hidráulico de tractores.",
        "specs": SPECS,
        "source": source,
    } | over


def _listing(**over: Any) -> dict[str, Any]:
    return {
        "path": LUBRICANTES,
        "title": "Lubricantes",
        "count": 58,
        "filters": [
            {"facet": "Marca", "on": [], "options": ["LUBRITEK", "SHELL", "MOBIL"]},
            {"facet": "Viscosidad", "on": [], "options": ["15W40", "10W30"]},
        ],
        "sort": "",
        "items": [
            {"path": LUBRITEK, "name": LUBRITEK_NAME, "price": 80000},
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
            "Hola, ¿cómo estás?": reply("Muy bien. ¿Para qué máquina buscas?"),
            "I need oil for my tractor. What do you recommend?": reply(
                "Happy to help. Is it for the engine or the hydraulics?"
            ),
            "¿Qué aceite me recomiendas? Es quince W cuarenta para el motor.": reply_and_call(
                "Te busco opciones.",
                "find_products",
                args={"query": "aceite 15w40", "category": "Lubricantes"},
            ),
            # The products the page read, talked through: he opens the best one.
            "find_products done": reply(
                f"{{page: {SHELL}}} Te abro el Shell, el que más te conviene. "
                "Está a noventa y cinco mil novecientos noventa pesos."
            ),
            "Cuéntame de sus especificaciones.": reply(
                "{tab: specs} Mira las especificaciones. {show: pais} Es hecho en Chile. "
                "{show: viscosidad} Es diez W treinta. {show: Fila Inventada} Y nada más."
            ),
            "Ábreme el Lubritek.": reply_and_call(
                "Te abro el Lubritek.", "open_product", args={"path": LUBRITEK}
            ),
            "Muéstrame los Lubritek en quince W cuarenta.": reply(
                "{filter: Marca | lubritek} Te dejo solo los Lubritek. "
                "{filter: Viscosidad | 15w40} En quince W cuarenta. "
                "{sort: menor precio} Y del más barato al más caro."
            ),
            "¿Y de base sintética total?": reply(
                "{filter: Tipo de aceite | Sintético} Te dejo los sintéticos."
            ),
            "¿Qué tienen en lubricantes?": reply(
                "{menu: lubricantes} Aquí está todo lo de lubricantes. "
                "{menu: Categoría Inventada} Y nada más."
            ),
            "¿Me sirve este?": reply_and_call(
                "Te sirve para el hidráulico.", "add_to_cart", args={"path": LUBRITEK, "qty": 1}
            ),
            "Sí, agrégalo.": reply_and_call(
                "Te lo agrego al carro.", "add_to_cart", args={"path": LUBRITEK, "qty": 2}
            ),
            "Sigamos.": reply("Claro, sigamos."),
            # Dev call 370ecb04: the add asked after a no, "cart" heard as "cut".
            "No, can you add this to cut?": reply_and_call(
                "I'll add it to your cart.", "add_to_cart", args={"path": LUBRITEK, "qty": 1}
            ),
            # A refused add: the yes is asked for in the same turn.
            "Ask for that yes now": reply("¿Te lo agrego al carro?"),
            "Sí, quiero cotizar.": reply_and_call(
                "Te llevo al formulario de cotización.", "start_quote", args={}
            ),
            "¿Cuánto demora?": reply_and_call(
                "Lo anoto.", "fill_quote", args={"name": "Juan Pérez"}
            ),
            "Me llamo Juan Pérez, mi teléfono es nueve ocho siete seis cinco cuatro tres dos uno.": (
                reply_and_call(
                    "Anoté nueve, ocho, siete, seis, cinco, cuatro, tres, dos, uno.",
                    "fill_quote",
                    args={"name": "Juan Pérez", "phone": "9 8765 4321"},
                )
            ),
            "Mi correo es juan arroba campo punto cl.": reply_and_call(
                "Lo anoto.", "fill_quote", args={"email": "juan arroba campo"}
            ),
            "Mi RUT es 12.345.678-5, ¿lo pones tú?": reply_and_call(
                "El RUT lo completas tú en la página.",
                "fill_quote",
                args={"notes": "RUT 12.345.678-5"},
            ),
            "Pon el RUT, por favor.": reply_and_call(
                "El RUT lo completas tú.", "search_products", args={"query": "12.345.678-5"}
            ),
            "¿La tienen en la tienda de Talca?": reply_and_call(
                "Te reviso el stock en Talca.", "check_stock", args={"store": "talca"}
            ),
            "check_stock done": reply("{store: Talca} En Talca está disponible."),
            "¿Cuánto demora el despacho?": reply("Entre tres y siete días hábiles."),
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


def _patience(rig: object) -> list[int | None]:
    return [c.stt.patience for c in _configs(rig) if c.stt is not None]  # type: ignore[arg-type]


_QUOTE_FORM = {"step": "form", "filled": [], "missing": ["name", "rut", "phone", "email"]}


# ─── Voice, language and the greeting ──────────────────────────────────────────


async def test_the_greeting_is_spanish_short_and_the_voice_reaches_the_wire() -> None:
    async with demo("agroplanet", _llm()) as rig:
        opener = await rig.driver.start_session(init={"surface": "agroplanet-ext", "path": "/"})
        check_greeting(rig, opener)
        assert opener is not None
        assert opener.text == ag.for_the_voice(greeting("/", "es"))
        assert opener.text.startswith("Hola, soy Javier, de Agroplanet.")
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _idle_windows(rig) == [_IDLE_MS]


@pytest.mark.parametrize(
    ("path", "words"),
    [
        ("/", "¿Para qué máquina es?"),
        ("/categoria/baterias/AG02", "tu batería"),
        ("/categoria/baterías_de_arranque/AG108", "tu batería"),
        ("/categoria/lubricantes/AG01", "tu aceite"),
        ("/categoria/neumaticos_camaras_y_llantas./AG05", "Qué medida"),
        ("/categoria/rodamientos/AG04", "tu rodamiento"),
        ("/categoria/repuestos_de_tractor/AG10", "Qué tractor tienes"),
        ("/categoria/insumos_agricolas/AG16", "esta categoría"),
        ("/busqueda/bateria", "estos resultados"),
        ("/marca/lubritek", "esta marca"),
        (f"{LUBRITEK}?utm=x", "este producto"),
        ("/carro", "tu carro"),
        ("/cotizacion", "el RUT lo pones tú"),
        ("/nuestras-tiendas", "tienda más cercana"),
        ("/politica-despacho", "el despacho"),
        ("/cambios-devoluciones", "los cambios"),
    ],
)
def test_the_opener_follows_the_page(path: str, words: str) -> None:
    line = greeting(path, "es")
    assert line.startswith("Hola, soy Javier, de Agroplanet. ")
    assert words in line, line
    assert len(line.split()) <= 26, line
    # The first sentence, the one heard before anything else, is short.
    assert len(line.split(".")[0].split()) <= 6
    assert greeting(path, "en").startswith("Hi, I'm Javier, from Agroplanet.")


async def test_the_toggle_moves_both_legs_to_english_and_confirms() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(rig, "language_requested", {"language": "en"})
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        assert rig.command("language_changed") == {"language": "en"}
        turn = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, turn)
        assert turn.text == TOGGLE_CONFIRM["en"]


async def test_english_heard_moves_the_call_and_spanish_brings_it_back() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("I need oil for my tractor. What do you recommend?")
        check_turn(rig, turn)
        check_voice_pair(rig, voice="omnivoice/javier", language="en")
        await rig.driver.user_says("Hola, ¿cómo estás?")
        check_voice_pair(rig, voice="omnivoice/javier", language="es")
        assert _commands(rig, "language_changed") == [{"language": "en"}, {"language": "es"}]


def test_the_brand_and_the_measures_are_said_as_the_field_says_them() -> None:
    assert ag.for_the_voice("Bienvenido a AgroPlanet.") == "Bienvenido a Agroplanet."
    assert ag.names_for_the_voice("www.agroplanet.cl") == "www.agroplanet.cl"
    assert ag.for_the_voice("Un aceite 15W40 y una batería de 12V y 100Ah.") == (
        "Un aceite quince W cuarenta y una batería de doce volts y cien amperes hora."
    )
    assert ag.for_the_voice("Un tractor de 50 HP.") == "Un tractor de cincuenta hache pe."
    assert ag.english_for_the_voice("A 12V battery, 15W-40 oil, 50 HP.") == (
        "A twelve volt battery, fifteen W forty oil, fifty horsepower."
    )


# ─── Finding, opening and narrating a product ──────────────────────────────────


async def test_find_products_reads_live_and_he_opens_the_best_with_a_cue() -> None:
    llm = _llm()
    async with demo("agroplanet", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        before = len(llm.requests)
        turn = await rig.driver.user_says(
            "¿Qué aceite me recomiendas? Es quince W cuarenta para el motor."
        )
        check_turn(rig, turn)
        # A move, not a marked read: one request, and the words said first.
        assert len(llm.requests) == before + 1
        assert turn.text.startswith("Te busco opciones.")
        assert _move(rig, "find_products") == {
            "query": "aceite 15w40",
            "category_code": "AG100",
            "brand": None,
            "sort": None,
        }
        # The page's read, then its result: talked through in the short spell.
        await _page(rig, "products_found", FOUND)
        await _answer(rig, "find_products", detail="14 products; 3 shown")
        assert _idle_windows(rig)[-1] == _TALK_THROUGH_MS
        talk = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, talk)
        seen = _texts(llm.captured_inputs[-1])
        assert llm.requests[-1].get("tool_choice") == "none"
        assert "find_products done: 14 products; 3 shown" in seen
        # Each product with its price and how to say it, and its stock in words.
        assert (
            f"1. {SHELL_NAME} ({SHELL}), SHELL: price $95.990 (say: noventa y cinco mil "
            "novecientos noventa pesos), before $119.990, a real saving of 20%, available "
            "online (say: está disponible)" in seen
        )
        # The Lubritek's struck price is its own price: no saving to claim.
        assert "$80.000 (say: ochenta mil pesos), few units left online" in seen
        # A price the store hides is never given, even when the read has one.
        assert f"{BUJES_NAME} ({BUJES}), FEDERAL MOGUL: price NOT shown" in seen
        assert "$22.000" not in seen
        # He opens the one he recommends with a page cue, by a path he read.
        (opened,) = _cues(rig)
        assert (opened["move"], opened["args"]) == ("page.open", [SHELL])
        assert opened["at"].startswith("Te abro el Shell")


async def test_on_the_product_he_walks_its_specs_as_he_says_them() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": f"{LUBRITEK}?utm_source=x"})
        await _state(rig, "product.shown", _product())
        await _state(rig, "product.checked", _product("api", price=74000))
        turn = await rig.driver.user_says("Cuéntame de sus especificaciones.")
        check_turn(rig, turn)
        assert "{" not in turn.text
        cues = [(c["move"], c["args"]) for c in _cues(rig)]
        # The section, then each spec row by its label as the page writes it; a
        # label the product does not have is rung as written, never invented
        # into another row.
        assert cues == [
            ("product.tab", ["specs"]),
            ("page.show", ["País"]),
            ("page.show", ["Viscosidad"]),
            ("page.show", ["Fila Inventada"]),
        ]
        anchors = [c["at"] for c in _cues(rig)]
        assert anchors[0].startswith("Mira las especificaciones.")
        assert anchors[1].startswith("Es hecho en Chile")
        assert anchors[2].startswith("Es diez W treinta")


async def test_the_live_read_wins_and_carries_the_specs() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": LUBRITEK})
        await _state(rig, "product.shown", _product())
        await _state(rig, "product.checked", _product("api", price=74000, specs=[]))
        # A late page copy never undoes the live read.
        await _state(rig, "product.shown", _product(price=90000))
        brain = cast("ag.AgroplanetBrain", rig.brain)
        read = await brain.read_screen(ag.ReadRequest(slice="product"))
        assert "price $74.000 (say: setenta y cuatro mil pesos)" in read
        assert "País: Chile" in read
        assert "Código Fabricante AGPLUBLTUTFBLD" in read
        assert "available online (say: está disponible)" in read
        assert "635" not in read


async def test_a_price_the_store_hides_is_never_given() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": BUJES})
        await _state(
            rig,
            "product.shown",
            _product(path=BUJES, sku="139083", name=BUJES_NAME, price=None, price_hidden=True),
        )
        brain = cast("ag.AgroplanetBrain", rig.brain)
        read = await brain.read_screen(ag.ReadRequest(slice="product"))
        assert 'price NOT shown: the page says "Confirmar precio en tienda"' in read
        assert "say:" not in read.split("Detalle")[0].replace("say: está disponible", "")
        product = ag.ProductShown.model_validate(
            {"path": BUJES, "name": BUJES_NAME, "price": 22000, "price_hidden": True}
        )
        line = ag.product_line(product, "es")
        assert line == "Aquí está el producto: Bujes de Biela, y su precio se confirma en tienda."


async def test_open_product_lands_with_its_written_line() -> None:
    llm = _llm()
    async with demo("agroplanet", llm) as rig:
        await rig.driver.start_session(init={"path": LUBRICANTES})
        await _state(rig, "listing.shown", _listing())
        turn = await rig.driver.user_says("Ábreme el Lubritek.")
        check_turn(rig, turn)
        assert _move(rig, "open_product") == {"path": LUBRITEK, "tab": None}
        await _state(rig, "product.shown", _product(stock="lowStock"), by="agent")
        assert _idle_windows(rig)[-1] == _DONE_MS
        asked = len(llm.requests)
        landed = await rig.driver.user_idle(level=1, idle_ms=_DONE_MS)
        assert landed.text.startswith(
            "Aquí está el producto: Aceite LUBRITEK UTF Semisintético, a ochenta mil pesos. "
            "Quedan pocas unidades."
        )
        assert len(llm.requests) == asked + 1


async def test_a_product_never_read_is_never_opened() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": LUBRICANTES})
        brain = cast("ag.AgroplanetBrain", rig.brain)
        out = await brain.open_product(ag.OpenProductRequest(path="/producto/x/999999"))
        assert out.startswith("Not done: '/producto/x/999999' is not a product")
        assert _moves(rig, "open_product") == []
        # The slug is the page's: a SKU it listed opens by the path it linked.
        await _state(rig, "listing.shown", _listing())
        assert brain._known_path("/producto/otro_nombre/1173221") == LUBRITEK


# ─── Filters and the menu he narrates ──────────────────────────────────────────


async def test_filter_cues_are_the_listings_own_facets_and_options() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/categoria/lubricantes/ag100?q=&page=0"})
        turn = await rig.driver.user_says("Muéstrame los Lubritek en quince W cuarenta.")
        check_turn(rig, turn)
        assert "{" not in turn.text and "filter" not in turn.text
        assert [(c["move"], c["args"]) for c in _cues(rig)] == [
            ("commerce.filter", ["Marca", "LUBRITEK", LUBRICANTES]),
            ("commerce.filter", ["Viscosidad", "15W40", LUBRICANTES]),
            ("commerce.sort", ["price_asc", LUBRICANTES]),
        ]
        # The filtered listing lands: his written line names it.
        await _state(
            rig,
            "listing.filtered",
            _listing(
                filters=[
                    {"facet": "Marca", "on": ["LUBRITEK"], "options": []},
                    {"facet": "Viscosidad", "on": ["15W40"], "options": []},
                ],
                count=4,
            ),
            by="agent",
        )
        landed = await rig.driver.user_idle(level=1, idle_ms=_DONE_MS)
        assert landed.text.startswith(
            "Aquí hay cuatro de Lubritek, con quince W cuarenta. El primero es Aceite LUBRITEK"
        )


async def test_a_facet_the_listing_lacks_is_never_sent_and_is_said() -> None:
    llm = _llm()
    async with demo("agroplanet", llm) as rig:
        await rig.driver.start_session(init={"path": LUBRICANTES})
        await rig.driver.user_says("¿Y de base sintética total?")
        assert _cues(rig) == []
        await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        seen = _texts(llm.captured_inputs[-1])
        assert (
            "[Not done on the page ({filter: Tipo de aceite | Sintético}): this listing has "
            "no facet" in seen
        )
        assert "it has: Precio, Base, Viscosidad, Marca" in seen


async def test_the_menu_cue_opens_a_top_category_as_the_menu_writes_it() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        turn = await rig.driver.user_says("¿Qué tienen en lubricantes?")
        check_turn(rig, turn)
        # "lubricantes" is the menu's "Lubricantes Y Fluidos"; a category the
        # menu does not have is never sent.
        assert [(c["move"], c["args"]) for c in _cues(rig)] == [
            ("menu.open", ["Lubricantes Y Fluidos"])
        ]
        brain = cast("ag.AgroplanetBrain", rig.brain)
        # A deeper category opens the menu on the top it sits under.
        assert brain._resolve_menu("baterías heavy duty") == ["Baterías"]
        assert brain._resolve_menu("BATERIAS") == ["Baterías"]


# ─── The cart and the quote: only after a yes ──────────────────────────────────


async def test_add_to_cart_waits_for_a_yes_and_then_says_it_is_done() -> None:
    llm = _llm()
    async with demo("agroplanet", llm) as rig:
        await rig.driver.start_session(init={"path": LUBRITEK})
        await _state(rig, "product.shown", _product())
        # The model called it on a question: refused, nothing sent.
        await rig.driver.user_says("¿Me sirve este?")
        assert _moves(rig, "commerce.cart_add") == []
        # The yes: sent.
        await rig.driver.user_says("Sí, agrégalo.")
        refused = tool_results_of(llm.captured_inputs[-1], "add_to_cart")
        assert any("they have not asked to add it to the cart" in r for r in refused)
        assert _moves(rig, "commerce.cart_add") == [{"path": LUBRITEK, "qty": 2}]
        await _state(
            rig,
            "cart.changed",
            {
                "count": 2,
                "subtotal": 160000,
                "items": [{"path": LUBRITEK, "name": LUBRITEK_NAME, "qty": 2, "price": 80000}],
            },
            by="agent",
        )
        await _answer(rig, "commerce.cart_add", detail=f"added 2 x {LUBRITEK_NAME}; the cart has 2")
        assert _idle_windows(rig)[-1] == _DONE_MS
        done = await rig.driver.user_idle(level=1, idle_ms=_DONE_MS)
        check_turn(rig, done)
        assert done.text.startswith("Listo, Aceite LUBRITEK UTF Semisintético ya está en tu carro.")
        brain = cast("ag.AgroplanetBrain", rig.brain)
        cart = await brain.read_screen(ag.ReadRequest(slice="cart"))
        assert "Total $160.000 (say: ciento sesenta mil pesos)" in cart
        assert "Agroplanet sells by quote" in cart and "Webpay" in cart


async def test_an_add_asked_after_a_no_and_heard_as_cut_is_sent_at_once() -> None:
    """Dev call 370ecb04: "No, can you add this to cut?" on the product page.
    The leading no only corrected him, and "cut" is the cart misheard: the
    move goes at once, with no second ask."""
    llm = _llm()
    async with demo("agroplanet", llm) as rig:
        await rig.driver.start_session(init={"path": LUBRITEK})
        await _state(rig, "product.shown", _product())
        await rig.driver.user_says("No, can you add this to cut?")
        assert _moves(rig, "commerce.cart_add") == [{"path": LUBRITEK, "qty": 1}]


async def test_a_refused_add_asks_for_the_yes_in_the_same_turn() -> None:
    """Dev call 370ecb04: the refusal waited ~25 s for an idle line ("It
    wasn't added yet"). The brain now asks the yes in the turn it refused."""
    llm = _llm()
    async with demo("agroplanet", llm) as rig:
        await rig.driver.start_session(init={"path": LUBRITEK})
        await _state(rig, "product.shown", _product())
        turn = await rig.driver.user_says("¿Me sirve este?")
        check_turn(rig, turn)
        assert _moves(rig, "commerce.cart_add") == []
        assert turn.text.startswith("Te sirve para el hidráulico."), turn.text
        assert "¿Te lo agrego al carro?" in turn.text, turn.text


async def test_the_quote_form_is_reached_after_a_yes_and_filled_with_what_they_said() -> None:
    llm = _llm()
    async with demo("agroplanet", llm) as rig:
        await rig.driver.start_session(init={"path": "/carro"})
        await _state(
            rig,
            "cart.changed",
            {
                "count": 1,
                "subtotal": 80000,
                "items": [{"path": LUBRITEK, "name": LUBRITEK_NAME, "qty": 1}],
            },
        )
        await rig.driver.user_says("Sí, quiero cotizar.")
        assert _move(rig, "start_quote") == {}
        await _state(rig, "quote.changed", _QUOTE_FORM | {"items": 1, "total": 80000}, by="agent")
        await _answer(rig, "start_quote", detail="on the Formulario de cotización")
        # On the form, the recognizer waits longer between digits and letters.
        assert _patience(rig)[-1] == _FORM_PATIENCE
        done = await rig.driver.user_idle(level=1, idle_ms=_DONE_MS)
        assert done.text.startswith(
            "Listo, este es el formulario de cotización. ¿Te ayudo a completarlo?"
        )
        seen = _texts(llm.captured_inputs[-1])
        assert "Still missing: Nombre Completo / Razón Social, Teléfono, Correo electrónico" in seen
        assert "The RUT is still empty: theirs to type." in seen
        # A question is no yes: nothing typed.
        await rig.driver.user_says("¿Cuánto demora?")
        assert _moves(rig, "fill_quote") == []
        # What they said for the form is typed, the phone as digits.
        await rig.driver.user_says(
            "Me llamo Juan Pérez, mi teléfono es nueve ocho siete seis cinco cuatro tres dos uno."
        )
        sent = _move(rig, "fill_quote")
        assert {k: v for k, v in sent.items() if v is not None} == {
            "name": "Juan Pérez",
            "phone": "987654321",
        }
        # An email that is not one is asked again, never typed.
        await rig.driver.user_says("Mi correo es juan arroba campo punto cl.")
        # A tool's result reaches the model with the next request.
        await rig.driver.user_says("Sigamos.")
        results = tool_results_of(llm.captured_inputs[-1], "fill_quote")
        assert any("is not an email address; ask them to spell it" in r for r in results)
        assert len(_moves(rig, "fill_quote")) == 1


async def test_a_rut_they_say_is_never_sent_or_repeated() -> None:
    llm = _llm()
    async with demo("agroplanet", llm) as rig:
        await rig.driver.start_session(init={"path": "/cotizacion"})
        await _state(rig, "quote.changed", _QUOTE_FORM)
        turn = await rig.driver.user_says("Mi RUT es 12.345.678-5, ¿lo pones tú?")
        check_turn(rig, turn)
        assert "12.345.678" not in turn.text
        seen = _texts(llm.captured_inputs[-1])
        assert "What the visitor just said holds a RUT. Never repeat it" in seen
        assert _moves(rig, "fill_quote") == []
        await rig.driver.user_says("Pon el RUT, por favor.")
        refused = tool_results_of(llm.captured_inputs[-1], "fill_quote")
        assert any("that holds a RUT, which is theirs to type" in r for r in refused)
        await rig.driver.user_says("Sigamos.")
        refused = tool_results_of(llm.captured_inputs[-1], "search_products")
        assert any("that holds a RUT, which is theirs to type" in r for r in refused)
        for c in rig.driver.ui_commands:  # type: ignore[attr-defined]
            assert "12.345.678" not in str(c), c
    # The form's move has no field a RUT could ride in.
    assert "rut" not in ag.FillQuoteArgs.model_fields
    assert "rut" not in ag.FillQuoteRequest.model_fields


def test_no_cue_opens_the_quote_form_the_account_or_a_payment() -> None:
    for path in (
        "/cotizacion",
        "/cotizacion/confirmacion",
        "/registrate",
        "/acceso-revision",
        "/perfil",
        "/checkout/payment",
    ):
        assert ag._NEVER.match(kb.canonical_path(path)), path
    assert not ag._NEVER.match("/carro")
    assert not ag._NEVER.match("/cotizaciones-antiguas")


@pytest.mark.parametrize(
    ("kind", "last", "ok"),
    [
        ("cart", "Sí, dale.", True),
        ("cart", "Ya.", True),
        ("cart", "Agrégalo al carro.", True),
        ("cart", "¿Cuánto cuesta?", False),
        ("cart", "No, todavía no.", False),
        # Dev call 370ecb04, and pcfactory 9ec9601a's natural ways to ask or say yes.
        ("cart", "No, can you add this to cut?", True),
        ("cart", "Can you add this to the card?", True),
        ("cart", "Put it in the car.", True),
        ("cart", "Add these two to my cards.", True),
        ("cart", "Oh so sorry, can you add this in the cart first?", True),
        ("cart", "Sí, agrégalo.", True),
        ("cart", "Add it.", True),
        ("cart", "Ok, dale.", True),
        ("cart", "Ponlo en el carro.", True),
        ("cart", "Súmalo.", True),
        ("cart", "Perfect.", True),
        ("cart", "Sounds good.", True),
        ("cart", "Of course.", True),
        ("cart", "Por supuesto.", True),
        ("cart", "Please do.", True),
        ("cart", "Mm-hmm.", True),
        ("cart", "Lo quiero.", True),
        ("cart", "No, add it to my cart.", True),
        ("cart", "Wait, add two.", True),
        ("cart", "No.", False),
        ("cart", "No, don't add it.", False),
        ("cart", "No lo agregues.", False),
        ("cart", "No, mejor no lo agregues.", False),
        ("cart", "Lo quiero ver.", False),
        ("cart", "Es sumamente caro.", False),
        ("cart", "Go to the card section.", False),
        ("cart", "What is your address?", False),
        ("cart", "Cut it shorter.", False),
        ("quote", "Quiero cotizar.", True),
        ("quote", "Lo quiero comprar.", True),
        ("quote", "¿Y la garantía?", False),
        ("form", "Mi correo es juan@campo.cl", True),
        ("form", "Me llamo Juan.", True),
        ("form", "Mi teléfono es 9 8765 4321.", True),
        ("form", "¿Cuánto demora?", False),
    ],
)
def test_a_confirmed_move_needs_their_ask_or_their_yes(kind: str, last: str, ok: bool) -> None:
    assert ag.consents(kind, last) is ok


# ─── Stock by store, and the stores ────────────────────────────────────────────


async def test_stock_in_a_store_is_read_and_the_store_shown() -> None:
    llm = _llm()
    async with demo("agroplanet", llm) as rig:
        await rig.driver.start_session(init={"path": LUBRITEK})
        await _state(rig, "product.shown", _product())
        await rig.driver.user_says("¿La tienen en la tienda de Talca?")
        # The product in front, the store by its listed name.
        assert _move(rig, "check_stock") == {"path": LUBRITEK, "store": "Talca"}
        await _page(
            rig,
            "stock_read",
            {
                "path": LUBRITEK,
                "sku": "1173221",
                "name": LUBRITEK_NAME,
                "online": "inStock",
                "online_level": 635,
                "stores": [
                    {"name": "Talca", "city": "Talca", "qty": 3, "status": "lowStock"},
                    {"name": "Los Ángeles", "city": "Los Ángeles", "qty": 0},
                ],
                "asked": "talca",
                "matched": "Talca",
            },
        )
        await _answer(rig, "check_stock", detail="Talca: 3")
        talk = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, talk)
        seen = _texts(llm.captured_inputs[-1])
        assert (
            "available online (say: está disponible); in stores: Talca (Talca): few units; "
            "Los Ángeles (Los Ángeles): none" in seen
        )
        assert "The store they asked about, Talca: few units." in seen
        (store,) = _cues(rig)
        assert (store["move"], store["args"]) == ("stores.show", ["Talca"])


async def test_a_question_on_a_product_page_is_answered_in_place() -> None:
    """On a product, "¿cuánto demora el despacho?" never takes them off it to
    the despacho page on its own."""
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": LUBRITEK})
        await rig.driver.user_says("¿Cuánto demora el despacho?")
        assert _cues(rig) == []


async def test_a_question_elsewhere_shows_its_page() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("¿Cuánto demora el despacho?")
        assert [(c["move"], c["args"]) for c in _cues(rig)][:1] == [("page.open", [DESPACHO])]


def test_the_prompt_teaches_narration_with_cues_and_the_quote() -> None:
    prompt = ag._prompt(STORE, ag.date(2030, 3, 4))
    assert "Today is Monday, 04 March 2030, in Santiago." in prompt
    assert "OPEN WITH A CUE" in prompt
    assert "{menu: Category} opens" in prompt
    assert '"Confirmar precio en tienda" instead of a price. NEVER say a price' in prompt
    assert "Agroplanet sells by quote: there is no online payment." in prompt
    assert "Lubricantes (AG100) /categoria/lubricantes/AG100" in prompt
    assert "Viscosidad: 15W40, 10W30, SAE 90" in prompt
    assert "Maule: Talca" in prompt
    assert "THE RUT IS THEIRS" in prompt
    assert "read it back digit by digit" in prompt
    assert "/politica-despacho — Política de despacho" in prompt


# ─── Prices said in words (dev call 370ecb04) ──────────────────────────────────


def test_a_price_bucket_lands_said_in_words_and_counts_too() -> None:
    """ "Here are 3 with $50.000 - $149.999" was read from the facet as the
    listing writes it; "Here are 5 with Mineral" was no sentence."""
    bucket = ag.listing_view(
        _listing(
            count=3,
            filters=[{"facet": "Precio", "on": ["$50.000 - $149.999"], "options": []}],
        )
    )
    named = [(f.facet, o) for f in bucket.facets for o in f.on]
    assert ag.listing_line(bucket, "en", named).startswith(
        "Here are three between fifty thousand and one hundred and forty-nine thousand pesos. "
    )
    assert ag.listing_line(bucket, "es", named).startswith(
        "Aquí hay tres entre cincuenta mil y ciento cuarenta y nueve mil pesos. "
    )
    mineral = ag.listing_view(
        _listing(count=5, filters=[{"facet": "Base", "on": ["Mineral"], "options": []}])
    )
    named = [(f.facet, o) for f in mineral.facets for o in f.on]
    assert ag.listing_line(mineral, "en", named).startswith("Here are five with a mineral base. ")
    assert ag.listing_line(mineral, "es", named).startswith("Aquí hay cinco con base mineral. ")
    assert ag.filters_said([("Precio", "Más de $500.000")], "en") == (
        "over five hundred thousand pesos"
    )
    assert ag.filters_said([("Precio", "Más de $500.000")], "es") == (
        "de más de quinientos mil pesos"
    )
    assert ag.filters_said([("Rareza", "Alta")], "en") == "filtered by Rareza: Alta"


def test_any_peso_amount_reaches_the_voice_in_words() -> None:
    assert ag.english_for_the_voice("Here are 3 with $50.000 - $149.999.") == (
        "Here are 3 between fifty thousand and one hundred and forty-nine thousand pesos."
    )
    assert ag.for_the_voice("Está a $80.000, o más de $1.000.000.") == (
        "Está a ochenta mil pesos, o más de un millón de pesos."
    )


def test_the_listing_note_says_its_price_buckets_and_the_prompt_maps_dollars() -> None:
    listing = ag.listing_view(
        _listing(
            filters=[
                {"facet": "Precio", "on": [], "options": ["$50.000 - $149.999", "Más de $500.000"]}
            ]
        )
    )
    note = ag._listing_note(listing, "en")
    assert (
        "$50.000 - $149.999 is “between fifty thousand and one hundred and forty-nine "
        "thousand pesos”" in note
    )
    prompt = ag._prompt(STORE)
    assert "PRICES ON AGROPLANET ARE CHILEAN PESOS" in prompt
    assert "Never ask whether they meant pesos" in prompt
