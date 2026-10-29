"""Javier on www.agroplanet.cl, with what pcfactory's round 2 learned on dev.

The real ``AgroplanetBrain`` on a real ``brain_server`` socket with only the
model scripted, as in ``test_agroplanet_e2e``, over its invented store. The
lessons are pcfactory's dev calls (``test_pcfactory_round2``), on the same
listing machinery:

- **A**: a listing reported while the grid redraws (no cards, count 0) never
  lands as "No products"; an empty listing lands only with the move's own
  result; the line says the listing as it stands when it is said.
- **B**: every option of a facet reaches him, and the prompt never lets him
  call an option missing.
- **C**: "at least a hundred amps" ticks 100, not every size above it.
- **D**: the landing line says its filters naturally and never ends a name on
  a word that leads into its cut.
- The listing's filters taken off and its pages turned, the big photo, one
  category read at a time (the whole tree is no topic).

Run: ``cd demos && uv run pytest tests/test_agroplanet_round2.py``
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from voqalize_demos.testing import ScriptedOpenAI, reply, reply_and_call

from ._harness import demo
from .test_agroplanet_e2e import (
    LUBRICANTES,
    LUBRITEK,
    LUBRITEK_NAME,
    STORE,
    _answer,
    _cues,
    _listing,
    _move,
    _product,
    _state,
    _store,  # noqa: F401  (the invented store, for every test here)
    ag,
    kb,
)

_DONE_MS = ag._DONE_MS

HEAVY_DUTY = "/categoria/baterias_heavy_duty/1000908"
#: Viscosidad on the full lubricants listing: "15W40" is past the first eight.
VISCOSIDAD = [
    "0W20",
    "5W30",
    "5W40",
    "10W30",
    "10W40",
    "15W40",
    "20W50",
    "75W90",
    "80W90",
    "85W140",
    "ATF",
    "SAE 90",
    "UTF",
]
AMPERAJE = ["45", "60", "75", "90", "100", "120", "150", "180", "200"]
BATTERY = "/producto/bateria_heavy_duty_12v_100ah/1200100"


def _full_listing(**over: Any) -> dict[str, Any]:
    return _listing(
        count=58,
        filters=[
            {"facet": "Marca", "on": [], "options": ["LUBRITEK", "SHELL", "MOBIL"]},
            {"facet": "Base", "on": [], "options": ["MINERAL", "SEMI-SINTETICO", "SINTETICO"]},
            {"facet": "Viscosidad", "on": [], "options": VISCOSIDAD},
        ],
        sort="relevance",
        **over,
    )


def _batteries(**over: Any) -> dict[str, Any]:
    return {
        "path": HEAVY_DUTY,
        "title": "Baterías Heavy Duty",
        "count": 30,
        "filters": [
            {"facet": "Amperaje", "on": [], "options": AMPERAJE},
            {"facet": "Marca", "on": [], "options": ["DGP", "BOSCH"]},
        ],
        "sort": "",
        "items": [{"path": BATTERY, "name": "Batería Heavy Duty 12V 100Ah", "price": 189990}],
    } | over


def _phantom(**over: Any) -> dict[str, Any]:
    """The listing as the page saw it mid-redraw: no cards, count 0, no sort."""
    return _listing(count=0, items=[], sort="", **over)


def _llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            "Solo los Lubritek.": reply("{filter: Marca | LUBRITEK} Te dejo solo los Lubritek."),
            "Los Lubritek en quince W cuarenta.": reply(
                "{filter: Marca | LUBRITEK} Te dejo los Lubritek. "
                "{filter: Viscosidad | 15W40} En quince W cuarenta."
            ),
            "Muéstrame los lubricantes.": reply_and_call(
                "Te muestro los lubricantes.", "filter_listing", args={"category": "Lubricantes"}
            ),
            "Los quince W cuarenta.": reply(
                "{filter: Viscosidad | 15w40} Te dejo los quince W cuarenta."
            ),
            "Y al menos cien amperes.": reply(
                "{filter: Amperaje | 100, 120, 150, 180, 200} De cien amperes o más."
            ),
            "Lubritek o Shell.": reply(
                "{filter: Marca | LUBRITEK, SHELL} Te dejo Lubritek y Shell."
            ),
            "Saca la marca y pasa a la página dos.": reply_and_call(
                "Te lo dejo así.",
                "filter_listing",
                args={"category": "Lubricantes", "remove": ["Marca: LUBRITEK"], "page": 2},
            ),
            "Borra todos los filtros.": reply_and_call(
                "Te los saco.", "filter_listing", args={"category": "Lubricantes", "clear": True}
            ),
            "Muéstrame la foto grande.": reply("{tab: zoom} Mira la foto grande."),
        }
    )


def _said_lines(rig: object) -> str:
    return " ".join(
        t
        for turn in rig.driver.turns.values()  # type: ignore[attr-defined]
        for unit in turn.units
        for t in unit.texts
    )


# ─── A: never "No products" from a grid mid-redraw ─────────────────────────────


async def test_a_filter_cue_never_lands_on_the_grid_mid_redraw() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": LUBRICANTES})
        await _state(rig, "listing.shown", _full_listing())
        await rig.driver.user_says("Solo los Lubritek.")
        assert [c["args"][:2] for c in _cues(rig)] == [["Marca", "LUBRITEK"]]
        on = [{"facet": "Marca", "on": ["LUBRITEK"], "options": ["LUBRITEK"]}]
        await _state(rig, "listing.filtered", _phantom(filters=on), by="agent")
        await _state(rig, "listing.sorted", _listing(count=12, filters=on), by="agent")
        await _answer(rig, "commerce.filter", detail="Marca: LUBRITEK on; 12 products")
        landed = await rig.driver.user_idle(level=1, idle_ms=_DONE_MS)
        assert landed.text.startswith("Aquí hay doce de Lubritek. El primero es Aceite LUBRITEK")
        assert "No aparece" not in _said_lines(rig)


async def test_a_filter_listing_load_never_lands_on_its_first_empty_report() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Muéstrame los lubricantes.")
        assert _move(rig, "filter_listing")["category_path"] == LUBRICANTES
        await _state(rig, "listing.shown", _phantom(), by="agent")
        await _state(rig, "listing.sorted", _full_listing(), by="agent")
        await _answer(rig, "filter_listing", detail="Lubricantes: 58 products")
        landed = await rig.driver.user_idle(level=1, idle_ms=_DONE_MS)
        assert landed.text.startswith("Aquí hay cincuenta y ocho. El primero es Aceite LUBRITEK")
        assert "No aparece" not in _said_lines(rig)


async def test_a_an_empty_listing_lands_only_with_the_moves_own_result() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": LUBRICANTES})
        await _state(rig, "listing.shown", _full_listing())
        await rig.driver.user_says("Solo los Lubritek.")
        on = [{"facet": "Marca", "on": ["LUBRITEK"], "options": ["LUBRITEK"]}]
        await _state(rig, "listing.filtered", _phantom(filters=on), by="agent")
        await _answer(rig, "commerce.filter", detail="Marca: LUBRITEK on; 0 products")
        landed = await rig.driver.user_idle(level=1, idle_ms=_DONE_MS)
        assert landed.text.startswith("No aparece ningún producto de Lubritek.")


async def test_a_the_line_waits_for_the_next_filter_and_says_the_newest_count() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": LUBRICANTES})
        await _state(rig, "listing.shown", _full_listing())
        await rig.driver.user_says("Los Lubritek en quince W cuarenta.")
        assert [c["args"][:2] for c in _cues(rig)] == [
            ["Marca", "LUBRITEK"],
            ["Viscosidad", "15W40"],
        ]
        brand = {"facet": "Marca", "on": ["LUBRITEK"], "options": ["LUBRITEK"]}
        await _state(rig, "listing.filtered", _listing(count=12, filters=[brand]), by="agent")
        visc = {"facet": "Viscosidad", "on": ["15W40"], "options": VISCOSIDAD}
        await _state(rig, "listing.filtered", _listing(count=4, filters=[brand, visc]), by="agent")
        landed = await rig.driver.user_idle(level=1, idle_ms=_DONE_MS)
        assert landed.text.startswith("Aquí hay cuatro de Lubritek, con quince W cuarenta."), (
            landed.text
        )
        assert "12" not in _said_lines(rig)


async def test_a_a_waiting_line_is_rebuilt_from_the_listing_as_it_stands() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": LUBRICANTES})
        await _state(rig, "listing.shown", _full_listing())
        await rig.driver.user_says("Solo los Lubritek.")
        brand = {"facet": "Marca", "on": ["LUBRITEK"], "options": ["LUBRITEK"]}
        await _state(rig, "listing.filtered", _listing(count=12, filters=[brand]), by="agent")
        # The visitor narrows it themselves before the line is said.
        visc = {"facet": "Viscosidad", "on": ["15W40"], "options": ["15W40"]}
        await _state(rig, "listing.filtered", _listing(count=4, filters=[brand, visc]))
        landed = await rig.driver.user_idle(level=1, idle_ms=_DONE_MS)
        assert landed.text.startswith("Aquí hay cuatro de Lubritek."), landed.text


# ─── B: every option reaches him ───────────────────────────────────────────────


def test_b_the_listing_read_lists_every_option_of_every_facet() -> None:
    note = ag._listing_note(ag.listing_view(_full_listing()), "es")
    assert "85W140" in note and "UTF" in note and "SAE 90" in note


def test_b_the_prompt_never_lets_him_call_an_option_missing() -> None:
    prompt = ag._prompt(STORE)
    assert "NEVER SAY AN OPTION OR A FILTER IS MISSING" in prompt
    assert '("+N more" are not); read_category gives' in prompt


async def test_b_an_option_past_the_first_eight_is_cued_as_the_listing_writes_it() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": LUBRICANTES})
        await _state(rig, "listing.shown", _full_listing())
        await rig.driver.user_says("Los quince W cuarenta.")
        assert [c["args"][:2] for c in _cues(rig)] == [["Viscosidad", "15W40"]]


# ─── C: only what they named ───────────────────────────────────────────────────


async def test_c_at_least_a_hundred_amps_ticks_a_hundred_only() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": HEAVY_DUTY})
        await _state(rig, "listing.shown", _batteries())
        await rig.driver.user_says("Y al menos cien amperes.")
        assert [c["args"][:2] for c in _cues(rig)] == [["Amperaje", "100"]]


async def test_c_two_options_they_named_both_stay() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": LUBRICANTES})
        await _state(rig, "listing.shown", _full_listing())
        await rig.driver.user_says("Lubritek o Shell.")
        assert [c["args"][:2] for c in _cues(rig)] == [["Marca", "LUBRITEK, SHELL"]]


def test_c_named_in_reads_numbers_and_codes_as_said() -> None:
    said = "y al menos cien amperes, aceite quince w cuarenta o de doce volts"
    assert ag.named_in("100", said)
    assert not ag.named_in("120", said)
    assert ag.named_in("15W40", said)
    assert not ag.named_in("10W30", said)
    assert ag.named_in("12V", said)
    assert ag.named_in("100", "at least one hundred amps")
    assert not ag.named_in("200", "at least one hundred amps")


def test_c_the_prompt_ticks_only_what_they_named() -> None:
    prompt = ag._prompt(STORE)
    assert "TICK ONLY WHAT THE VISITOR NAMED" in prompt
    assert "{filter: Amperaje | 100}, one option" in prompt


# ─── D: the landing line, said naturally ───────────────────────────────────────


def test_d_the_filters_are_said_naturally() -> None:
    listing = ag.listing_view(
        _listing(
            count=5,
            filters=[
                {"facet": "Marca", "on": ["LUBRITEK"], "options": []},
                {"facet": "Base", "on": ["MINERAL"], "options": []},
                {"facet": "Viscosidad", "on": ["15W40"], "options": []},
            ],
            items=[{"path": LUBRITEK, "name": LUBRITEK_NAME, "price": 80000}],
        )
    )
    named = [(f.facet, o) for f in listing.facets for o in f.on]
    es = ag.listing_line(listing, "es", named)
    en = ag.listing_line(listing, "en", named)
    assert es == (
        "Aquí hay cinco de Lubritek, con base mineral y 15W40. "
        "El primero es Aceite LUBRITEK UTF Semisintético, a ochenta mil pesos."
    ), es
    assert en == (
        "Here are five from Lubritek, with a mineral base and 15W40. "
        "The first is Aceite LUBRITEK UTF Semisintético, at eighty thousand pesos."
    ), en


def test_d_a_short_name_never_ends_on_a_word_that_leads_on() -> None:
    assert ag.short_name("Filtro Aceite Motor Perkins Serie 1000 Original") == (
        "Filtro Aceite Motor Perkins"
    )
    assert ag.short_name("Disco De Embrague Para John Deere 5045") == (
        "Disco De Embrague Para John Deere"
    )
    assert ag.short_name("Cuchillas Para Rotofresa Howard 60 x 8 mm") == (
        "Cuchillas Para Rotofresa Howard"
    )


# ─── The listing's filters off, its pages, the big photo ───────────────────────


async def test_filter_listing_takes_filters_off_and_turns_the_page() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": LUBRICANTES})
        await _state(rig, "listing.shown", _full_listing())
        await rig.driver.user_says("Saca la marca y pasa a la página dos.")
        assert _move(rig, "filter_listing") == {
            "category_path": LUBRICANTES,
            "filters": None,
            "sort": None,
            "remove": ["Marca: LUBRITEK"],
            "clear": None,
            "page": 2,
        }


async def test_filter_listing_clears_every_filter() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": LUBRICANTES})
        await rig.driver.user_says("Borra todos los filtros.")
        assert _move(rig, "filter_listing")["clear"] is True


async def test_the_big_photo_is_a_tab_cue_on_the_product() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": LUBRITEK})
        await _state(rig, "product.shown", _product())
        await rig.driver.user_says("Muéstrame la foto grande.")
        assert [(c["move"], c["args"]) for c in _cues(rig)] == [("product.tab", ["zoom"])]


# ─── One category at a time ────────────────────────────────────────────────────


async def test_read_category_reads_one_category_with_its_filters() -> None:
    async with demo("agroplanet", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        brain = cast("ag.AgroplanetBrain", rig.brain)
        out = await brain.read_category(ag.CategoryRequest(name="aceite"))
        assert out.startswith(f"Lubricantes (AG100) {LUBRICANTES}, under Lubricantes Y Fluidos")
        assert "Viscosidad: 15W40, 10W30, SAE 90" in out
        top = await brain.read_category(ag.CategoryRequest(name="Lubricantes y Grasas"))
        assert f"Under it: Lubricantes (AG100) {LUBRICANTES}" in top
        assert "Its listing is titled “Lubricantes y Grasas”." in top
        none = await brain.read_category(ag.CategoryRequest(name="heladeras"))
        assert none.startswith("No category matches 'heladeras'.")


def test_the_whole_tree_is_not_a_topic(tmp_path: Path) -> None:
    (tmp_path / "L2").mkdir()
    (tmp_path / "L2" / "categorias.md").write_text("# Categorías\n" + "x" * 1000)
    (tmp_path / "L2" / "despacho.md").write_text("# Despacho\nSources: x")
    assert set(kb.load(tmp_path).topics) == {"despacho"}
    assert "categorias" not in kb.TOPIC_IDS
