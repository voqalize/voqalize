"""Javier on www.pcfactory.cl, round 2: what the owner found on dev, end to end.

The real ``PcFactoryBrain`` on a real ``brain_server`` socket with only the
model scripted, as in ``test_pcfactory_e2e``, over its invented store. Each
test is named for the call that taught it:

- **A** (31a45613, 8b363867): a listing reported while the grid redraws (no
  cards, count 0) never lands as "No products"; an empty listing lands only
  with the move's own result; the line says the listing as it stands when it
  is said, never an older count.
- **B** (8b363867): every option of a facet reaches him, "INTEL Core i7" too,
  and the prompt never lets him call an option missing.
- **C** (8b363867): "at least sixteen" ticks 16GB, not every size above it.
- **D** (2a2304d8, 31a45613): the landing line says its filters naturally
  and never cuts a name before its number.
- The comparator, through its own bar, and the comparison walked row by row
  with ``{compare: …}`` cues; the menu cue, the listing's chips, sizes and
  pages, the curated lists.

Run: ``cd demos && uv run pytest tests/test_pcfactory_round2.py``
"""

from __future__ import annotations

from typing import Any

from voqalize_demos.testing import ScriptedOpenAI, reply, reply_and_call, tool_results_of

from ._harness import demo
from .test_pcfactory_e2e import (
    HP,
    HP_NAME,
    LENOVO,
    LENOVO_NAME,
    NOTEBOOKS,
    STORE,
    _answer,
    _cues,
    _listing,
    _move,
    _page,
    _state,
    _store,  # noqa: F401  (the invented store, for every test here)
    _texts,
    pc,
)

_DONE_MS = pc._DONE_MS
_TALK_THROUGH_MS = pc._TALK_THROUGH_MS

#: Procesador on the full notebooks listing, as the page sent it on dev call
#: 8b363867: "INTEL Core i7" is the 19th.
PROCESADOR = [
    "A18 Pro",
    "AMD Ryzen 3",
    "AMD Ryzen 5",
    "AMD Ryzen 7",
    "AMD Ryzen 9",
    "AMD Ryzen AI 5",
    "AMD Ryzen AI 5 PRO",
    "AMD Ryzen AI 7",
    "AMD Ryzen AI 7 PRO",
    "AMD Ryzen AI 9",
    "Apple M5",
    "Chip M5",
    "Intel Core 3",
    "Intel Core 5",
    "Intel Core 7",
    "Intel Core 9",
    "INTEL Core i3",
    "INTEL Core i5",
    "INTEL Core i7",
    "INTEL Core i9",
    "INTEL Core Ultra 5",
    "INTEL Core Ultra 7",
    "INTEL Core Ultra 9",
    "Qualcomm Snapdragon X",
    "Snapdragon X Elite",
]
RAM = ["12GB", "16GB", "24GB", "32GB", "48GB", "64GB", "8GB"]
THINKPAD = "Notebook AI PC ThinkPad T14 Gen 6 Intel Core Ultra 5 225U 16GB 512GB SSD"
CMP = f"/comparador?prod1={LENOVO.split('/')[-1]}&prod2={HP.split('/')[-1]}"


def _full_listing(**over: Any) -> dict[str, Any]:
    return _listing(
        count=157,
        filters=[
            {"facet": "Marcas", "on": [], "options": ["Lenovo", "HP", "ASUS"]},
            {"facet": "Procesador", "on": [], "options": PROCESADOR},
            {"facet": "RAM", "on": [], "options": RAM},
        ],
        sort="relevance",
        **over,
    )


def _phantom(**over: Any) -> dict[str, Any]:
    """The listing as the page saw it mid-redraw: no cards, count 0, no sort."""
    return _listing(count=0, items=[], sort="", **over)


def _llm() -> ScriptedOpenAI:
    return ScriptedOpenAI(
        {
            "Solo los Lenovo.": reply("{filter: Marcas | Lenovo} Te dejo solo los Lenovo."),
            "Los Lenovo con dieciséis.": reply(
                "{filter: Marcas | Lenovo} Te dejo los Lenovo. "
                "{filter: RAM | 16GB} Con dieciséis gigas."
            ),
            "Muéstrame los notebooks.": reply_and_call(
                "Te muestro los notebooks.",
                "filter_listing",
                args={"category": "Notebooks"},
            ),
            "Con procesador Intel i7.": reply(
                "{filter: Procesador | Intel Core i7} Te dejo los Core i siete."
            ),
            "Y al menos dieciséis G B de RAM.": reply(
                "{filter: RAM | 16GB, 24GB, 32GB, 48GB, 64GB} Con dieciséis gigas o más."
            ),
            "Lenovo o HP.": reply("{filter: Marcas | Lenovo, HP} Te dejo Lenovo y HP."),
            "Compáralos.": reply_and_call(
                "Te los comparo.", "compare_products", args={"paths": [LENOVO, HP]}
            ),
            "Compara cuatro.": reply_and_call(
                "Te los comparo.",
                "compare_products",
                args={"paths": [LENOVO, HP, "/producto/1", "/producto/2"]},
            ),
            "¿En qué se diferencian?": reply(
                "{compare: procesador} El primero trae un Core i cinco y el HP también. "
                "{compare: memoria} El Lenovo tiene dieciséis gigas, el HP ocho. "
                "{compare: differences} Te marco en verde lo que cambia. "
                "{compare: Tarjeta Inventada} Y nada más."
            ),
            "Saca el HP de la comparación.": reply_and_call(
                "Lo saco.", "remove_from_comparison", args={"path": HP}
            ),
            "¿Qué venden?": reply(
                "{menu: computadores} Computadores y tablets. {menu: Gamer} Y todo lo gamer."
            ),
            "Saca la marca y muéstrame treinta y dos, página dos.": reply_and_call(
                "Te lo dejo así.",
                "filter_listing",
                args={
                    "category": "Notebooks",
                    "remove": ["Marcas: Lenovo"],
                    "size": 32,
                    "page": 2,
                },
            ),
            "Ábreme las fotos grandes del HP.": reply_and_call(
                "Te abro el HP.", "open_product", args={"path": HP, "tab": "zoom"}
            ),
            "Filtra estos por Lenovo.": reply("{filter: Marcas | Lenovo} Te dejo los Lenovo."),
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
    async with demo("pcfactory", _llm()) as rig:
        await rig.driver.start_session(init={"path": NOTEBOOKS})
        await _state(rig, "listing.shown", _full_listing())
        await rig.driver.user_says("Solo los Lenovo.")
        assert [c["args"][:2] for c in _cues(rig)] == [["Marcas", "Lenovo"]]
        # 31a45613: the page reported the grid while it redrew, then the real one.
        lenovo_on = [{"facet": "Marcas", "on": ["Lenovo"], "options": ["Lenovo"]}]
        await _state(rig, "listing.filtered", _phantom(filters=lenovo_on), by="agent")
        await _state(rig, "listing.sorted", _listing(count=45, filters=lenovo_on), by="agent")
        await _answer(rig, "commerce.filter", detail="Marcas: Lenovo on; Notebooks: 45 products")
        landed = await rig.driver.user_idle(level=1, idle_ms=_DONE_MS)
        assert landed.text.startswith("Aquí hay 45 de Lenovo. El primero es el Notebook Lenovo")
        assert "No aparece" not in _said_lines(rig)


async def test_a_filter_listing_load_never_lands_on_its_first_empty_report() -> None:
    llm = _llm()
    async with demo("pcfactory", llm) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("Muéstrame los notebooks.")
        assert _move(rig, "filter_listing")["category_path"] == NOTEBOOKS
        # 8b363867: count 0 right after the load, then 157.
        await _state(rig, "listing.shown", _phantom(), by="agent")
        await _state(rig, "listing.sorted", _full_listing(), by="agent")
        await _answer(rig, "filter_listing", detail="Notebooks: 157 products")
        landed = await rig.driver.user_idle(level=1, idle_ms=_DONE_MS)
        assert landed.text.startswith("Aquí hay 157. El primero es el Notebook Lenovo IdeaPad")
        assert "No aparece" not in _said_lines(rig)


async def test_a_an_empty_listing_lands_only_with_the_moves_own_result() -> None:
    async with demo("pcfactory", _llm()) as rig:
        await rig.driver.start_session(init={"path": NOTEBOOKS})
        await _state(rig, "listing.shown", _full_listing())
        await rig.driver.user_says("Solo los Lenovo.")
        lenovo_on = [{"facet": "Marcas", "on": ["Lenovo"], "options": ["Lenovo"]}]
        await _state(rig, "listing.filtered", _phantom(filters=lenovo_on), by="agent")
        await _answer(rig, "commerce.filter", detail="Marcas: Lenovo on; Notebooks: 0 products")
        landed = await rig.driver.user_idle(level=1, idle_ms=_DONE_MS)
        assert landed.text.startswith("No aparece ningún producto de Lenovo.")


async def test_a_the_line_waits_for_the_next_filter_and_says_the_newest_count() -> None:
    async with demo("pcfactory", _llm()) as rig:
        await rig.driver.start_session(init={"path": NOTEBOOKS})
        await _state(rig, "listing.shown", _full_listing())
        await rig.driver.user_says("Los Lenovo con dieciséis.")
        assert [c["args"][:2] for c in _cues(rig)] == [["Marcas", "Lenovo"], ["RAM", "16GB"]]
        lenovo = {"facet": "Marcas", "on": ["Lenovo"], "options": ["Lenovo"]}
        await _state(rig, "listing.filtered", _listing(count=38, filters=[lenovo]), by="agent")
        # 8b363867: "Here are 38 in Lenovo" was said 5 s late, over 21 on screen.
        ram = {"facet": "RAM", "on": ["16GB"], "options": ["16GB", "32GB", "8GB"]}
        await _state(rig, "listing.filtered", _listing(count=21, filters=[lenovo, ram]), by="agent")
        landed = await rig.driver.user_idle(level=1, idle_ms=_DONE_MS)
        assert landed.text.startswith("Aquí hay 21 de Lenovo, con 16GB de RAM."), landed.text
        assert "38" not in _said_lines(rig)


async def test_a_a_waiting_line_is_rebuilt_from_the_listing_as_it_stands() -> None:
    async with demo("pcfactory", _llm()) as rig:
        await rig.driver.start_session(init={"path": NOTEBOOKS})
        await _state(rig, "listing.shown", _full_listing())
        await rig.driver.user_says("Solo los Lenovo.")
        lenovo = {"facet": "Marcas", "on": ["Lenovo"], "options": ["Lenovo"]}
        await _state(rig, "listing.filtered", _listing(count=38, filters=[lenovo]), by="agent")
        # The visitor narrows it themselves before the line is said.
        ram = {"facet": "RAM", "on": ["16GB"], "options": ["16GB"]}
        await _state(rig, "listing.filtered", _listing(count=21, filters=[lenovo, ram]))
        landed = await rig.driver.user_idle(level=1, idle_ms=_DONE_MS)
        assert landed.text.startswith("Aquí hay 21 de Lenovo."), landed.text


# ─── B: every option reaches him ───────────────────────────────────────────────


def test_b_the_listing_read_lists_every_option_of_every_facet() -> None:
    note = pc._listing_note(pc.listing_view(_full_listing()), "es")
    assert "INTEL Core i7" in note
    assert "Snapdragon X Elite" in note
    search = pc._listing_note(
        pc.listing_view(_listing(path="/busqueda-avanzada?search=notebook+lenovo")), "es"
    )
    assert "for a spec, filter_listing on the category" in search


def test_b_the_prompt_never_lets_him_call_an_option_missing() -> None:
    prompt = pc._prompt(STORE)
    assert "NEVER SAY AN OPTION OR A FILTER IS MISSING" in prompt
    assert "A search results listing (/busqueda-avanzada) filters only by Tiendas" in prompt


async def test_b_a_processor_past_the_first_eight_is_cued_as_the_listing_writes_it() -> None:
    llm = _llm()
    async with demo("pcfactory", llm) as rig:
        await rig.driver.start_session(init={"path": NOTEBOOKS})
        await _state(rig, "listing.shown", _full_listing())
        await rig.driver.user_says("Con procesador Intel i7.")
        assert [c["args"][:2] for c in _cues(rig)] == [["Procesador", "INTEL Core i7"]]


# ─── C: only what they named ───────────────────────────────────────────────────


async def test_c_at_least_sixteen_ticks_sixteen_only() -> None:
    async with demo("pcfactory", _llm()) as rig:
        await rig.driver.start_session(init={"path": NOTEBOOKS})
        await _state(rig, "listing.shown", _full_listing())
        await rig.driver.user_says("Y al menos dieciséis G B de RAM.")
        assert [c["args"][:2] for c in _cues(rig)] == [["RAM", "16GB"]]


async def test_c_two_options_they_named_both_stay() -> None:
    async with demo("pcfactory", _llm()) as rig:
        await rig.driver.start_session(init={"path": NOTEBOOKS})
        await _state(rig, "listing.shown", _full_listing())
        await rig.driver.user_says("Lenovo o HP.")
        assert [c["args"][:2] for c in _cues(rig)] == [["Marcas", "Lenovo, HP"]]


def test_c_named_in_reads_numbers_and_codes_as_said() -> None:
    said = "y al menos dieciséis G B de RAM con intel i siete o i7"
    assert pc.named_in("16GB", said)
    assert not pc.named_in("32GB", said)
    assert pc.named_in("INTEL Core i7", said)
    assert pc.named_in("16GB", "at least sixteen gigs")
    assert not pc.named_in("64GB", "at least sixteen gigs")
    assert pc.named_in("HP", "lenovo o h p")


def test_c_the_prompt_ticks_only_what_they_named() -> None:
    prompt = pc._prompt(STORE)
    assert "TICK ONLY WHAT THE VISITOR NAMED" in prompt
    assert "{filter: RAM | 16GB}, one option" in prompt


# ─── D: the landing line, said naturally ───────────────────────────────────────


def test_d_the_filters_are_said_naturally_and_the_maker_once() -> None:
    listing = pc.listing_view(
        _listing(
            count=5,
            filters=[
                {"facet": "Marcas", "on": ["Lenovo"], "options": []},
                {"facet": "Fabricante del Procesador", "on": ["INTEL"], "options": []},
                {"facet": "Procesador", "on": ["INTEL Core i7"], "options": []},
                {"facet": "RAM", "on": ["16GB"], "options": []},
            ],
            items=[{"path": "/producto/1", "name": THINKPAD, "price": 999990}],
        )
    )
    named = [(f.facet, o) for f in listing.facets for o in f.on]
    es = pc.listing_line(listing, "es", named)
    en = pc.listing_line(listing, "en", named)
    assert es.startswith(
        "Aquí hay 5 de Lenovo, con Intel Core i7 y 16GB de RAM. "
        "El primero es el Notebook AI PC ThinkPad T14 Gen 6, a novecientos"
    ), es
    assert en.startswith(
        "Here are 5 from Lenovo, with Intel Core i7 and 16GB of RAM. "
        "The first is the Notebook AI PC ThinkPad T14 Gen 6, at nine hundred"
    ), en
    assert "INTEL," not in es and " en Lenovo" not in es


def test_d_a_short_name_never_ends_before_its_number() -> None:
    assert pc.short_name(THINKPAD) == "Notebook AI PC ThinkPad T14 Gen 6"
    assert pc.short_name("Notebook Lenovo ThinkPad E14 Gen Intel Core i5") == (
        "Notebook Lenovo ThinkPad E14"
    )
    assert pc.short_name(LENOVO_NAME) == "Notebook Lenovo IdeaPad Slim 3"


# ─── The comparator ────────────────────────────────────────────────────────────


def _comparison(**over: Any) -> dict[str, Any]:
    return {
        "path": CMP,
        "category": "Notebooks",
        "items": [
            {"path": LENOVO, "name": LENOVO_NAME, "brand": "Lenovo", "price": 599990},
            {"path": HP, "name": HP_NAME, "brand": "HP", "price": 529990},
        ],
        "rows": [
            {"group": "Especificaciones Generales", "label": "Marca", "values": ["Lenovo", "HP"]},
            {"group": "Procesador", "label": "Procesador", "values": ["Core i5", "Core i5"]},
            {"group": "Memoria", "label": "Memoria RAM", "values": ["16GB", "8GB"]},
            {"group": "Pantalla", "label": "Tasa de refresco", "values": ["", "60Hz"]},
        ],
        "differs": ["Marca", "Memoria RAM"],
        "highlighted": False,
    } | over


async def test_compare_products_goes_through_the_bar_to_the_comparison_page() -> None:
    llm = _llm()
    async with demo("pcfactory", llm) as rig:
        await rig.driver.start_session(init={"path": NOTEBOOKS})
        await _state(
            rig,
            "listing.shown",
            _listing(
                items=[
                    {"path": LENOVO, "name": LENOVO_NAME, "price": 599990},
                    {"path": HP, "name": HP_NAME, "price": 529990},
                ]
            ),
        )
        await rig.driver.user_says("Compáralos.")
        assert _move(rig, "compare.add") == {"paths": [LENOVO, HP], "open": True}
        await rig.driver.user_says("Compara cuatro.")
        # The comparison page comes up: he hears its rows, the differing first.
        await _page(rig, "page_changed", {"path": "/comparador", "url": CMP, "kind": "compare"})
        await _state(rig, "compare.shown", _comparison(), by="agent")
        await _answer(rig, "compare.add", detail="pressed the comparator's Comparar; …")
        await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        seen = _texts(llm.captured_inputs[-1])
        assert "Rows that differ (cue one with {compare: Label}): Marca: Lenovo | HP" in seen
        assert "Memoria RAM: 16GB | 8GB" in seen
        assert (
            "for only some of them (say plainly that one has no value): "
            "Tasa de refresco: (none) | 60Hz" in seen
        )
        assert "The same in all: Procesador: Core i5" in seen
        assert "compare_products done" in seen
        # The tool's answer to four, filed for this next request.
        refused = tool_results_of(llm.captured_inputs[-1], "compare_products")
        assert any("two or three" in r for r in refused), refused


async def test_compare_cues_ring_rows_and_differences_on_the_comparison() -> None:
    llm = _llm()
    async with demo("pcfactory", llm) as rig:
        await rig.driver.start_session(init={"path": CMP})
        await _page(rig, "page_changed", {"path": "/comparador", "url": CMP, "kind": "compare"})
        await _state(rig, "compare.shown", _comparison())
        await rig.driver.user_says("¿En qué se diferencian?")
        assert [(c["move"], c["args"]) for c in _cues(rig)] == [
            ("compare.show", ["Procesador"]),
            ("compare.show", ["Memoria RAM"]),
            ("compare.show", ["diferencias"]),
        ]
        await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        seen = _texts(llm.captured_inputs[-1])
        assert "the comparison has no row 'Tarjeta Inventada'" in seen


async def test_remove_from_comparison_sends_compare_remove() -> None:
    async with demo("pcfactory", _llm()) as rig:
        await rig.driver.start_session(init={"path": CMP})
        await _page(rig, "page_changed", {"path": "/comparador", "url": CMP, "kind": "compare"})
        await _state(rig, "compare.shown", _comparison())
        await rig.driver.user_says("Saca el HP de la comparación.")
        assert _move(rig, "compare.remove") == {"path": HP, "all": None}


def test_the_prompt_walks_the_comparison_row_by_row() -> None:
    prompt = pc._prompt(STORE)
    assert "ROW BY ROW, ONE ROW PER SENTENCE" in prompt
    assert '"Notebooks" and "Notebooks Gamer" are two' in prompt
    assert "{compare: diferencias}" in prompt


# ─── The menu, the listing's chips, sizes and pages, curated lists ─────────────


async def test_the_menu_cue_names_the_stores_top_category() -> None:
    async with demo("pcfactory", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await rig.driver.user_says("¿Qué venden?")
        cues = [(c["move"], c["args"]) for c in _cues(rig)]
        tops = [c.name for c in STORE.unique_categories() if c.level == 1]
        assert [m for m, _ in cues] == ["menu.open", "menu.open"]
        assert cues[0][1] == [pc._match("computadores", tops) or "computadores"]


async def test_filter_listing_takes_filters_off_and_sets_size_and_page() -> None:
    async with demo("pcfactory", _llm()) as rig:
        await rig.driver.start_session(init={"path": NOTEBOOKS})
        await _state(rig, "listing.shown", _listing())
        await rig.driver.user_says("Saca la marca y muéstrame treinta y dos, página dos.")
        sent = _move(rig, "filter_listing")
        assert sent["remove"] == ["Marcas: Lenovo"]
        assert sent["size"] == 32
        assert sent["page"] == 2


async def test_a_tab_that_needs_the_product_in_front_is_offered_after_it_opens() -> None:
    llm = _llm()
    async with demo("pcfactory", llm) as rig:
        await rig.driver.start_session(init={"path": NOTEBOOKS})
        await _state(
            rig, "listing.shown", _listing(items=[{"path": HP, "name": HP_NAME, "price": 1}])
        )
        await rig.driver.user_says("Ábreme las fotos grandes del HP.")
        assert _move(rig, "open_product") == {"path": HP, "tab": None}
        await rig.driver.user_idle(level=1, idle_ms=_TALK_THROUGH_MS)
        said = tool_results_of(llm.captured_inputs[-1], "open_product")
        assert any("{tab: zoom} opens that" in r for r in said), said


async def test_a_curated_list_is_a_listing_its_cues_filter() -> None:
    curated = "/busqueda?productos=56755,56830,56215"
    async with demo("pcfactory", _llm()) as rig:
        await rig.driver.start_session(init={"path": "/"})
        await _page(
            rig,
            "page_changed",
            {"path": "/busqueda", "url": f"https://www.pcfactory.cl{curated}", "kind": "category"},
        )
        await _state(rig, "listing.shown", _listing(path=curated, title="Ofertas"))
        await rig.driver.user_says("Filtra estos por Lenovo.")
        assert [c["args"] for c in _cues(rig)] == [["Marcas", "Lenovo", curated]]
