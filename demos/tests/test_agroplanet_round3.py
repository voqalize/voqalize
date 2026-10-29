"""Javier on www.agroplanet.cl, with what the site's second scrape found.

The real ``AgroplanetBrain`` on a real ``brain_server`` socket with only the
model scripted, as in ``test_agroplanet_e2e``, over its invented store (plus
Agroferretería with the month's campaign switch). What it earns:

- **Does it fit my tractor**: a farmer who names his machine gets
  ``check_fit`` (the store's compatibility records, read in his browser) before
  a recommendation; the line says what the catalogue lists, UNIVERSAL as a
  generic part, and never a fit it does not show.
- **The offer the cart applies**: the page shows the full price and the
  mini-cart applies the store's offer; he says the shown price and the
  percentage the cart takes off, never a final price.
- **The month's campaign switch** ("Agrofertas Octubre") is a filter like any
  other, by cue or by ``filter_listing``, under the facet "Campaña".
- **Part numbers** are searched as read; a product's Equivalencias are rung by
  their label.
- **Data sheets and related products** are tabs of the product; "Venta en
  Verde" and the tractor for sale are said as the store says them.
- **Search outcomes**: the store's suggested spelling searched once, said so;
  nothing found said as nothing.

Run: ``cd demos && uv run pytest tests/test_agroplanet_round3.py``
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from typing import Any, cast

import pytest
from voqalize_demos.discovery import discover
from voqalize_demos.testing import ScriptedOpenAI, input_texts, reply, reply_and_call

from ._harness import check_turn, demo
from .test_agroplanet_e2e import (
    _TALK_THROUGH_MS,
    LUBRICANTES,
    LUBRITEK,
    STORE,
    _answer,
    _cues,
    _listing,
    _move,
    _page,
    _product,
    _state,
    ag,
    kb,
)
from .test_agroplanet_e2e import _store as _store  # the invented store, a fixture

discover()

from voqalize_demos._loaded.agroplanet import app_events as ev  # noqa: E402

AG15 = "/categoria/agroferreteria/AG15"
MF_PART = "/producto/manguera_de_filtro_hidraulico_massey_ferguson_290/123794"
MF_NAME = "Manguera de Filtro Hidráulico MASSEY FERGUSON 290"
KIT = "/producto/kit_ahoyador_power_pro_gp415xt_3_brocas/1171555"
TRACTOR = "/producto/tractor_lovol_te254_25hp/1184833"
BKT = "/producto/neumatico_bkt_8.3_36_8pr_tr135_tt/1184899"
BOMBA = "/producto/bomba_de_agua_0.014.3346.4_same/126615"

#: The invented store, with Agroferretería and its campaign switch.
STORE3 = dataclasses.replace(
    STORE,
    categories={
        **STORE.categories,
        AG15: kb.Category(
            code="AG15",
            path=AG15,
            name="Agroferretería",
            level=1,
            products=562,
            facets=(
                kb.Facet(
                    "Campaña",
                    "C_AG_BUSQUEDA_PLP_AGROFERRETERIAOCTUBRE",
                    ("Agrofertas Octubre",),
                    1,
                ),
                kb.Facet("Marca", "brand_search", ("WULKAN", "POWER PRO"), 64),
            ),
        ),
    },
)


@pytest.fixture(autouse=True)
def _store3(monkeypatch: pytest.MonkeyPatch, _store: None) -> Iterator[None]:
    """After the e2e's store: the same, with Agroferretería."""
    monkeypatch.setattr(kb, "KNOWLEDGE", STORE3)
    yield


def _llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            "¿Le sirve a mi Massey Ferguson 290?": reply_and_call(
                "Te reviso para qué tractores sirve.",
                "check_fit",
                args={"brand": "Massey Ferguson", "model": "290"},
            ),
            "check_fit done": reply(
                "Sí. Según el catálogo de Agroplanet, sirve para tu Massey Ferguson 290. "
                "¿Te la agrego al carro?"
            ),
            "Tengo el código RE45827, ¿lo tienen?": reply_and_call(
                "Te lo busco.", "find_products", args={"query": "RE45827"}
            ),
            "Muéstrame solo las ofertas.": reply(
                "{filter: Campaña | Agrofertas Octubre} Te dejo solo las agrofertas del mes."
            ),
            "¿Y las agrofertas?": reply("{filter: Ofertas | agrofertas} Te dejo las ofertas."),
            "Llévame a las ofertas de agroferretería.": reply_and_call(
                "Te llevo a las agrofertas.",
                "filter_listing",
                args={"category": "Agroferretería", "filters": ["Agrofertas Octubre"]},
            ),
            "¿Tiene ficha técnica?": reply(
                "{tab: ficha técnica} Sí, aquí están sus fichas. "
                "{tab: complemente su compra} Y esto es lo que va con ella."
            ),
            "¿A qué código equivale?": reply(
                "{show: equivalencia oem} Equivale al cero catorce, treinta y tres, cuarenta y seis."
            ),
        }
    )


def _texts(llm: ScriptedOpenAI) -> str:
    return input_texts(llm.captured_inputs[-1])


# ─── Does it fit my tractor ────────────────────────────────────────────────────


async def test_a_machine_named_is_checked_with_check_fit_before_a_recommendation() -> None:
    llm = _llm()
    async with demo("agroplanet", llm) as rig:
        await rig.driver.start_session(init={"path": MF_PART})
        await _state(rig, "product.shown", _product(path=MF_PART, sku="123794", name=MF_NAME))
        turn = await rig.driver.user_says("¿Le sirve a mi Massey Ferguson 290?")
        check_turn(rig, turn)
        assert turn.text.startswith("Te reviso para qué tractores sirve.")
        # The part in front, the machine as he said it: the page drills it.
        assert _move(rig, "check_fit") == {
            "path": MF_PART,
            "brand": "Massey Ferguson",
            "model": "290",
            "year": None,
        }
        await _page(
            rig,
            "fit_read",
            {
                "path": MF_PART,
                "sku": "123794",
                "name": MF_NAME,
                "universal": False,
                "brands": [
                    {
                        "brand": "MASSEY FERGUSON",
                        "count": 197,
                        "models": ["290"],
                        "years": [str(y) for y in range(1980, 1996)],
                    }
                ],
                "total": 197,
                "brand": "Massey Ferguson",
                "model": "290",
                "matched": True,
                "match": "MASSEY FERGUSON 290 1980 to 1995",
            },
        )
        await _answer(rig, "check_fit", detail="MASSEY FERGUSON 290 is listed")
        talk = await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        check_turn(rig, talk)
        seen = _texts(llm)
        assert "listed for MASSEY FERGUSON (197 machines): models 290; years 1980 to 1995" in seen
        assert "They asked about a Massey Ferguson 290: the catalogue LISTS IT" in seen
        assert "según el catálogo de Agroplanet" in seen
        assert talk.text.startswith("Sí. Según el catálogo de Agroplanet")


def test_the_fit_line_never_claims_what_the_catalogue_does_not_show() -> None:
    no = ev.FitRead(
        path=MF_PART,
        name=MF_NAME,
        brands=[ev.FitBrand(brand="MASSEY FERGUSON", count=197, models=["265", "290"])],
        brand="Massey Ferguson",
        model="5400",
        matched=False,
        missing="MASSEY FERGUSON 5400",
    )
    note = ag._fit_note(no)
    assert "the catalogue does NOT list it (MASSEY FERGUSON 5400 is not among them)" in note
    assert "Never say it fits" in note
    universal = ag._fit_note(
        ev.FitRead(path=MF_PART, name="Neumático", universal=True, brand="Ford")
    )
    assert "listed as UNIVERSAL — a generic part, for no one machine; it names no Ford" in universal
    none = ag._fit_note(ev.FitRead(path=MF_PART, name=MF_NAME, brand="John Deere"))
    assert "it lists no machine for this part. NEVER say it fits a John Deere" in none
    prompt = ag._prompt(STORE3)
    assert "WHEN A FARMER NAMES HIS MACHINE" in prompt
    assert '"UNIVERSAL" in the catalogue means a generic part' in prompt
    assert "find_products with the make and model in the words" in prompt


async def test_check_fit_needs_a_part() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        brain = cast("ag.AgroplanetBrain", rig.brain)
        out = await brain.check_fit(ag.CheckFitRequest(brand="John Deere"))
        assert out.startswith("Not read: which part?")


# ─── The offer the cart applies ────────────────────────────────────────────────


def test_an_offer_is_said_as_the_shown_price_and_the_cart_discount_in_words() -> None:
    kit = ag.product_view(
        _product(
            "api",
            path=KIT,
            sku="1171555",
            name="Kit Ahoyador POWER PRO GP415XT + 3 Brocas",
            price=360000,
            offer_price=288000,
            discount=20,
            specs=[],
        )
    )
    note = ag._product_note(kit, "es")
    assert (
        "OFFER: the page shows $360.000; the store applies 20% off in the cart, about "
        "$288.000 (say: doscientos ochenta y ocho mil pesos)" in note
    )
    assert "never promise it as the final price" in note
    # No offer below the price, no line about one.
    plain = ag.product_view(_product("api", price=80000, offer_price=80000, discount=0))
    assert "OFFER" not in ag._product_note(plain, "es")
    hidden = ag.product_view(_product("api", price=None, price_hidden=True, offer_price=7000))
    assert "OFFER" not in ag._product_note(hidden, "es")
    prompt = ag._prompt(STORE3)
    assert "THE STORE'S OFFERS ARE APPLIED IN THE CART" in prompt
    assert "doscientos ochenta y ocho mil" in prompt


async def test_live_prices_carry_the_offer_and_say_it_in_words() -> None:
    llm = ScriptedOpenAI({"x": reply("Listo.")}, default=reply("Claro."))
    async with demo("agroplanet", llm) as rig:
        await rig.driver.start_session(init={"path": LUBRITEK})
        await _page(
            rig,
            "prices_read",
            {
                "items": [
                    {
                        "path": LUBRITEK,
                        "sku": "1173221",
                        "name": "Aceite LUBRITEK",
                        "price": 80000,
                        "offer_price": 74000,
                        "discount": 7,
                        "stock": "inStock",
                    }
                ]
            },
        )
        turn = await rig.driver.user_says("¿Y el precio?")
        check_turn(rig, turn)
        seen = _texts(llm)
        assert "price $80.000 (say: ochenta mil pesos), OFFER: the page shows $80.000" in seen
        assert "applies 7% off in the cart, about $74.000 (say: setenta y cuatro mil pesos)" in seen


# ─── The month's campaign switch ───────────────────────────────────────────────


def _ag15(**over: Any) -> dict[str, Any]:
    return (
        _listing(
            path=AG15,
            title="Agroferreteria",
            count=562,
            filters=[
                {"facet": "Campaña", "on": [], "options": ["Agrofertas Octubre"]},
                {"facet": "Marca", "on": [], "options": ["WULKAN", "POWER PRO"]},
            ],
            items=[],
        )
        | over
    )


async def test_the_campaign_switch_is_a_filter_cue_by_its_facet_or_its_name() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": AG15})
        await _state(rig, "listing.shown", _ag15())
        await rig.driver.user_says("Muéstrame solo las ofertas.")
        await rig.driver.user_says("¿Y las agrofertas?")
        cues = [(c["move"], c["args"]) for c in _cues(rig)]
        assert cues == [
            ("commerce.filter", ["Campaña", "Agrofertas Octubre", AG15]),
            ("commerce.filter", ["Campaña", "Agrofertas Octubre", AG15]),
        ]
        landed = ag.listing_view(
            _ag15(
                count=18,
                filters=[{"facet": "Campaña", "on": ["Agrofertas Octubre"], "options": []}],
                items=[{"path": KIT, "name": "Kit Ahoyador POWER PRO GP415XT", "price": 360000}],
            )
        )
        assert ag.listing_line(landed, "es", [("Campaña", "Agrofertas Octubre")]).startswith(
            "Aquí hay dieciocho en Agrofertas Octubre."
        )


async def test_filter_listing_takes_them_to_the_category_with_the_switch_on() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Llévame a las ofertas de agroferretería.")
        assert _move(rig, "filter_listing") == {
            "category_path": AG15,
            "filters": ["Campaña: Agrofertas Octubre"],
            "sort": None,
            "remove": None,
            "clear": None,
            "page": None,
        }
        brain = cast("ag.AgroplanetBrain", rig.brain)
        out = await brain.filter_listing(
            ag.FilterRequest(category=LUBRICANTES, filters=["Campaña: Agrofertas Octubre"])
        )
        assert out.startswith("Not done: this listing has no facet 'Campaña'")


def test_the_offers_topic_and_l1_point_at_the_banner_and_the_switch() -> None:
    real = kb.load()
    assert "ofertas" in real.topics
    topic = real.topics["ofertas"].text
    assert "Hasta 67% de descuento en repuestos de implementos" in topic
    assert "Agrofertas Octubre" in topic
    assert "$" not in topic
    assert "`ofertas`" in real.l1
    ag15 = real.category("/categoria/agroferreteria/AG15")
    assert ag15 is not None
    assert ag15.facets[0].name == "Campaña"
    assert ag15.facets[0].options == ("Agrofertas Octubre",)
    prompt = ag._prompt(real)
    assert "This month's offers" in prompt
    assert '"solo las ofertas"' in prompt


# ─── Part numbers, equivalents, data sheets, related, badges ───────────────────


async def test_a_part_number_is_searched_as_read_and_an_equivalence_rung_by_its_label() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Tengo el código RE45827, ¿lo tienen?")
        assert _move(rig, "find_products")["query"] == "RE45827"
        prompt = ag._prompt(STORE3)
        assert "PART NUMBERS." in prompt
        assert "exactly as they read it" in prompt
        assert '"Equivalencia <marca>" facets' in prompt

    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": BOMBA})
        bomba = _product(
            "api",
            path=BOMBA,
            sku="126615",
            name="Bomba de Agua 0.014.3346.4 SAME",
            price=None,
            price_hidden=True,
            equivalents=[{"label": "Equivalencia OEM", "value": "0.014.3346.4, 1433464"}],
        )
        await _state(rig, "product.checked", bomba)
        brain = cast("ag.AgroplanetBrain", rig.brain)
        read = await brain.read_screen(ag.ReadRequest(slice="product"))
        assert "Equivalencias (the codes it replaces; cue a row by its label): " in read
        assert "Equivalencia OEM: 0.014.3346.4, 1433464" in read
        await rig.driver.user_says("¿A qué código equivale?")
        assert [(c["move"], c["args"]) for c in _cues(rig)] == [("page.show", ["Equivalencia OEM"])]


async def test_data_sheets_and_related_products_are_tabs_of_the_product() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": LUBRITEK})
        await _state(
            rig,
            "product.shown",
            _product(
                docs=["Hoja de Seguridad", "Ficha Técnica"],
                related=[{"name": "Grasa Lubritek 1kg", "path": "/producto/grasa/1170001"}],
            ),
        )
        brain = cast("ag.AgroplanetBrain", rig.brain)
        read = await brain.read_screen(ag.ReadRequest(slice="product"))
        assert "Data sheets: Hoja de Seguridad, Ficha Técnica ({tab: docs}" in read
        assert "Complemente su compra ({tab: related}): Grasa Lubritek 1kg" in read
        await rig.driver.user_says("¿Tiene ficha técnica?")
        assert [(c["move"], c["args"]) for c in _cues(rig)] == [
            ("product.tab", ["docs"]),
            ("product.tab", ["related"]),
        ]
        # A later page copy without them keeps what the store's read had.
        await _state(rig, "product.shown", _product())
        assert brain.product is not None and brain.product.docs == [
            "Hoja de Seguridad",
            "Ficha Técnica",
        ]


async def test_venta_en_verde_and_the_tractor_are_said_as_the_store_says_them() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": BKT})
        await _state(
            rig,
            "product.checked",
            _product(
                "api",
                path=BKT,
                sku="1184899",
                name="Neumático BKT 8.3-36 8PR TR135 TT",
                label="Venta en Verde",
                stock="outOfStock",
            ),
        )
        brain = cast("ag.AgroplanetBrain", rig.brain)
        read = await brain.read_screen(ag.ReadRequest(slice="product"))
        assert 'Its badge: "Venta en Verde". The site never explains Venta en Verde' in read
        assert "never explain or guess it" in read
        await _state(
            rig,
            "product.checked",
            _product(
                "api",
                path=TRACTOR,
                sku="1184833",
                name="TRACTOR LOVOL TE254 25HP",
                price=None,
                price_hidden=True,
                category="Maquinaria > Tractor para Venta > 25 HP",
            ),
        )
        read = await brain.read_screen(ag.ReadRequest(slice="product"))
        assert "In the store under: Maquinaria > Tractor para Venta > 25 HP." in read
        assert "It is machinery the store sells: its price is confirmed in store" in read
        assert 'price NOT shown: the page says "Confirmar precio en tienda"' in read
    prompt = ag._prompt(STORE3)
    assert '"Venta en Verde" is a badge' in prompt
    assert "LOVOL TE254" in prompt


# ─── Search outcomes ───────────────────────────────────────────────────────────


def test_the_spelling_the_store_suggests_is_said_and_nothing_is_said_as_nothing() -> None:
    retried = ev.ProductsFound(
        query="cuchiya",
        total=136,
        suggestion="cuchilla",
        retried_with="cuchilla",
        items=[ev.FoundItem(path="/producto/cuchilla/130707", name="Cuchilla CNH", price=9000)],
    )
    note = ag._found_note(retried, "es")
    assert note.startswith("[find_products for “cuchilla”: 136 match")
    assert (
        '“cuchiya” found nothing, so the store\'s suggested spelling "cuchilla" was searched'
        in note
    )
    empty = ag._found_note(ev.ProductsFound(query="xyzqwe", total=0), "es")
    assert empty.startswith("[find_products found nothing for “xyzqwe”: the store has no product")
    assert "Say so plainly" in empty
    prompt = ag._prompt(STORE3)
    assert "searches that once by itself" in prompt
    assert "twenty on a brand page" in prompt
    assert "20 on a brand page" in ag.FilterRequest.model_fields["page"].description  # type: ignore[operator]
