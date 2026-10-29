"""Agroplanet's knowledge: the loader, and the committed crawl once it exists.

The loader must take whatever the crawl leaves — a missing file, an empty one,
a broken one — and still import: the demos backend serves every brain from one
process. There is no product catalogue and no price or stock in any file:
products are read live, in the visitor's browser. A category is its code
(the router takes any slug), a product its SKU; categories resolve by name,
code or path; a facet is one the category lists; a cue is checked against the
pages the crawl kept. The committed files are checked only once they exist.

Run: ``cd demos && uv run pytest tests/test_agroplanet_knowledge.py``
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.agroplanet import brain as ag  # noqa: E402
from voqalize_demos._loaded.agroplanet import knowledge as kb  # noqa: E402

L3 = kb.ROOT / "L3"

CATEGORIES = [
    {
        "code": "AG01",
        "path": "/categoria/lubricantes_y_fluidos/AG01",
        "name": "Lubricantes Y Fluidos",
        "page_name": "Lubricantes y Grasas",
        "parent": "",
        "level": 1,
        "aliases": ["/categoria/lubricantes/AG01"],
        "products": 300,
        "facets": [],
    },
    {
        "code": "AG100",
        "path": "/categoria/lubricantes/AG100",
        "name": "Lubricantes",
        "parent": "/categoria/lubricantes_y_fluidos/AG01",
        "level": 2,
        "aliases": [],
        "products": 58,
        "facets": [
            {"name": "Marca", "param": "brand_search", "options": ["LUBRITEK (12)", "SHELL"]},
            {"name": "Viscosidad", "param": "C_DTE_VISCOSIDAD", "options": ["15W40", "10W30"]},
            {"name": "Precio", "param": "price", "options": ["$10.000 - $49.999"]},
        ],
    },
    {
        "code": "1000902",
        "path": "/categoria/aceite_de_motor/1000902",
        "name": "Aceite De Motor",
        "parent": "/categoria/lubricantes/AG100",
        "level": 3,
        "aliases": [],
        "products": 20,
        "facets": [],
    },
    {
        "code": "AG02",
        "path": "/categoria/baterias/AG02",
        "name": "Baterías",
        "parent": "",
        "level": 1,
        "aliases": [],
        "products": 80,
        "facets": [],
    },
    {
        "code": "1000908",
        "path": "/categoria/baterias_heavy_duty/1000908",
        "name": "Baterías Heavy Duty",
        "parent": "/categoria/baterias/AG02",
        "level": 3,
        "aliases": [],
        "products": 30,
        "facets": [],
    },
    {
        "code": "AG04",
        "path": "/categoria/rodamientos/AG04",
        "name": "Rodamientos",
        "parent": "",
        "level": 1,
        "aliases": [],
        "products": 900,
        "facets": [],
    },
    {
        "code": "AG159",
        "path": "/categoria/repuestos_para_rotofresa/AG159",
        "name": "Repuestos Para Rotofresa",
        "parent": "/categoria/repuestos_de_implementos/AG17",
        "level": 2,
        "aliases": [],
        "products": 40,
        "facets": [],
    },
]


def _write(root: Path) -> Path:
    (root / "L3").mkdir(parents=True)
    (root / "L3" / "categories.json").write_text(
        "[\n" + ",\n".join(json.dumps(c, ensure_ascii=False) for c in CATEGORIES) + "\n]",
        encoding="utf-8",
    )
    (root / "L3" / "stores.json").write_text(
        json.dumps(
            [
                {
                    "id": "SG0007",
                    "name": "Talca",
                    "address": "Av. San Miguel 2950",
                    "city": "Talca",
                    "region": "Maule",
                    "phone": "+56 9 8920 4716",
                    "hours": "Lunes a Viernes 09:15 a 18:15",
                },
                {
                    "id": "SG0018",
                    "name": "Los Ángeles",
                    "address": "Av. Alemania 650",
                    "city": "Los Ángeles",
                    "region": "Biobío",
                    "hours": "",
                },
                {
                    "id": "SG0011",
                    "name": "Vergara",
                    "address": "Vergara 450",
                    "city": "Santiago",
                    "region": "Metropolitana",
                },
            ]
        ),
        encoding="utf-8",
    )
    return root


def test_an_empty_or_missing_knowledge_folder_loads(tmp_path: Path) -> None:
    k = kb.load(tmp_path)
    assert k.pages == {} and k.categories == {} and k.topics == {} and k.stores == ()
    assert "Agroplanet" in k.l1
    assert k.find_category("baterias") is None
    # A prompt still builds on nothing.
    prompt = ag._prompt(k)
    assert "# Prices and stock" in prompt and "not loaded" in prompt


def test_broken_and_odd_files_are_skipped_not_raised(tmp_path: Path) -> None:
    (tmp_path / "L3").mkdir()
    (tmp_path / "L3" / "pages.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "L3" / "stores.json").write_text('"a string"', encoding="utf-8")
    (tmp_path / "L3" / "categories.json").write_text(
        json.dumps(
            [
                {"code": "AG1", "path": "https://otro-sitio.cl/categoria/x/AG1", "name": "Fuera"},
                {"code": "AG2", "path": "/categoria/sin-nombre/AG2"},
                "junk",
                {"path": "https://www.agroplanet.cl/categoria/ok/ag03", "name": "Ok"},
            ]
        ),
        encoding="utf-8",
    )
    k = kb.load(tmp_path)
    assert set(k.categories) == {"/categoria/ok/AG03"}
    # A code missing from the row is read off its path.
    assert k.categories["/categoria/ok/AG03"].code == "AG03"
    assert k.pages == {} and k.stores == ()


@pytest.mark.parametrize(
    ("said", "code"),
    [
        ("Lubricantes", "AG100"),
        ("lubricante", "AG100"),
        ("aceite", "AG100"),
        ("Lubricantes y Grasas", "AG01"),
        ("aceite de motor", "1000902"),
        ("engine oil", "1000902"),
        ("Baterías", "AG02"),
        ("baterias heavy duty", "1000908"),
        ("tractor battery", "1000908"),
        ("rulemanes", "AG04"),
        ("bearings", "AG04"),
        ("cuchillas de rotofresa", "AG159"),
        ("ag100", "AG100"),
        ("1000902", "1000902"),
        ("/categoria/lubricantes/AG100?q=::brand_search:LOCTITE&page=0", "AG100"),
        # The router takes any slug: the code names the category.
        ("/categoria/cualquier_cosa/ag100", "AG100"),
        ("/categoria/lubricantes/AG01", "AG01"),
        ("heladeras", None),
    ],
)
def test_a_category_resolves_by_name_code_or_path(
    tmp_path: Path, said: str, code: str | None
) -> None:
    k = kb.load(_write(tmp_path))
    got = k.find_category(said)
    assert (got.code if got else None) == code, (said, got)


def test_a_category_knows_its_top(tmp_path: Path) -> None:
    k = kb.load(_write(tmp_path))
    deep = k.find_category("aceite de motor")
    assert deep is not None and k.top_of(deep).name == "Lubricantes Y Fluidos"
    assert [c.name for c in k.tops()] == ["Lubricantes Y Fluidos", "Baterías", "Rodamientos"]
    assert len(k.unique_categories()) == len(CATEGORIES)


def test_facets_are_named_as_the_page_writes_them(tmp_path: Path) -> None:
    k = kb.load(_write(tmp_path))
    cat = k.find_category("lubricantes")
    assert cat is not None
    # A count is not an option; "marcas" and "brand" are the page's "Marca".
    assert cat.facet_names == ("Marca", "Viscosidad", "Precio")
    assert cat.facet("marcas") is cat.facet("brand") is not None
    assert cat.facet("Marca").options == ("LUBRITEK", "SHELL")  # type: ignore[union-attr]
    assert cat.facet("price") is cat.facet("Precio")
    assert cat.facet("Polaridad") is None


def test_stores_match_by_name_or_city(tmp_path: Path) -> None:
    k = kb.load(_write(tmp_path))
    assert k.store("la tienda de Talca").name == "Talca"  # type: ignore[union-attr]
    assert k.store("los angeles").name == "Los Ángeles"  # type: ignore[union-attr]
    assert k.store("en Los Ángeles").name == "Los Ángeles"  # type: ignore[union-attr]
    assert k.store("Santiago").name == "Vergara"  # type: ignore[union-attr]
    assert k.store("la de Vergara").phone == ""  # type: ignore[union-attr]
    assert k.store("Talca").phone == "+56 9 8920 4716"  # type: ignore[union-attr]
    assert k.store("Punta Arenas") is None


@pytest.mark.parametrize(
    ("raw", "sku", "path"),
    [
        (
            "https://www.agroplanet.cl/producto/aceite_lubritek_utf_semisintetico_19l/1173221?x=1",
            "1173221",
            "/producto/aceite_lubritek_utf_semisintetico_19l/1173221",
        ),
        ("/producto/Aceite_X/1173221", "1173221", "/producto/aceite_x/1173221"),
        ("1173221", "1173221", "/producto/producto/1173221"),
        ("/categoria/x/AG100", None, None),
    ],
)
def test_a_product_is_its_sku(raw: str, sku: str | None, path: str | None) -> None:
    assert kb.product_sku(raw) == sku
    assert kb.product_path(raw) == path
    if sku:
        assert kb.same_product(raw, f"/producto/otro/{sku}")


def test_a_search_is_its_words() -> None:
    assert kb.search_query("/busqueda/aceite%20hidraulico?q=x&page=1") == "aceite hidraulico"
    assert kb.search_path("Aceite  Hidráulico") == "/busqueda/aceite%20hidr%C3%A1ulico"
    assert kb.canonical_path("/busqueda/Bateria?q=bateria::brand_search:DGP") == "/busqueda/bateria"
    assert kb.search_query("/categoria/x/AG100") is None


def test_canonical_paths_keep_a_codes_case_and_fold_the_rest() -> None:
    assert kb.canonical_path("https://www.agroplanet.cl/Nuestras-Tiendas/?a=1") == (
        "/nuestras-tiendas"
    )
    assert kb.canonical_path("/inicio") == "/"
    assert kb.canonical_path("/categoria/Lubricantes/ag100?page=2") == (
        "/categoria/lubricantes/AG100"
    )
    assert kb.canonical_path("/marca/LUBRITEK") == "/marca/lubritek"


def test_filter_cues_validate_against_the_categorys_facets(tmp_path: Path) -> None:
    k = kb.load(_write(tmp_path))
    brain = ag.AgroplanetBrain(client=None, knowledge=k)  # type: ignore[arg-type]
    path = "/categoria/lubricantes/AG100"
    cat = k.category(path)
    assert brain._facet_options(path, cat, "marca", "lubritek y shell") == (
        "Marca",
        ["LUBRITEK", "SHELL"],
    )
    assert brain._facet_options(path, cat, "Viscosidad", "15w40") == ("Viscosidad", ["15W40"])
    assert brain._facet_options(path, cat, "precio", "$10.000 - $49.999") == (
        "Precio",
        ["$10.000 - $49.999"],
    )
    refused = brain._facet_options(path, cat, "Viscosidad", "0W20")
    assert isinstance(refused, str) and "it lists: 15W40, 10W30" in refused
    refused = brain._facet_options(path, cat, "Polaridad", "Derecha")
    assert isinstance(refused, str) and "no facet 'Polaridad'" in refused


def test_menu_cues_validate_against_the_top_categories(tmp_path: Path) -> None:
    k = kb.load(_write(tmp_path))
    brain = ag.AgroplanetBrain(client=None, knowledge=k)  # type: ignore[arg-type]
    assert brain._resolve_menu("lubricantes") == ["Lubricantes Y Fluidos"]
    assert brain._resolve_menu("Lubricantes y Grasas") == ["Lubricantes Y Fluidos"]
    assert brain._resolve_menu("rulemanes") == ["Rodamientos"]
    assert brain._resolve_menu("Baterías Heavy Duty") == ["Baterías"]
    assert brain._resolve_menu("Juguetería") is None
    # With no knowledge, the menu's own list as the site writes it.
    bare = ag.AgroplanetBrain(client=None, knowledge=kb.load(tmp_path / "none"))  # type: ignore[arg-type]
    assert bare._resolve_menu("neumáticos") == ["Neumáticos, Cámaras Y Llantas."]
    assert bare._resolve_menu("repuestos de tractor") == ["Repuestos De Tractor"]


# ─── The committed crawl ───────────────────────────────────────────────────────

_committed = pytest.mark.skipif(
    not (L3 / "categories.json").exists(), reason="the crawl is not committed yet"
)
#: Keys no knowledge file may carry: prices and stock are read live.
_PRICE_KEYS = re.compile(
    r'"(?:price|precio|stock|stock_level|stockLevel|regular_price|discountedPrice)"\s*:'
)


@_committed
def test_no_knowledge_file_holds_a_price_or_stock() -> None:
    for f in L3.glob("*.json"):
        assert not _PRICE_KEYS.search(f.read_text(encoding="utf-8")), f.name


@_committed
def test_the_committed_categories_are_the_stores_tree() -> None:
    k = kb.KNOWLEDGE
    cats = k.unique_categories()
    assert len(cats) >= 60
    assert all(c.path.startswith("/categoria/") and c.code for c in cats)
    tops = [c.name for c in k.tops()]
    assert 8 <= len(tops) <= 14, tops
    for top in ("Baterías", "Rodamientos", "Repuestos De Tractor", "Implementos Agrícolas"):
        assert top in tops, top
    for name, code in (("lubricantes", "AG100"), ("rodamientos", "AG04"), ("baterias", "AG02")):
        got = k.find_category(name)
        assert got is not None and got.code == code, (name, got)
    with_facets = [c for c in cats if c.facets]
    assert with_facets, "no category has its facets"
    for c in with_facets:
        assert all(f.name and len(f.options) <= 25 for f in c.facets), c.path


@_committed
def test_the_committed_stores_and_pages() -> None:
    k = kb.KNOWLEDGE
    if (L3 / "stores.json").exists():
        assert len(k.stores) == 22
        assert all(s.name and s.address and s.region for s in k.stores)
        assert k.store("Talca") is not None and k.store("Puerto Varas") is not None
    assert k.page("/") is not None
    assert k.page("/politica-despacho") is not None
    assert any(p.faqs for p in k.pages.values())


@_committed
def test_every_committed_heading_and_panel_is_a_cue_that_resolves() -> None:
    """A {show:} or {faq:} cue naming what a page writes resolves to it, on
    that page, as the page will look it up."""
    k = kb.KNOWLEDGE
    brain = ag.AgroplanetBrain(client=None, knowledge=k)  # type: ignore[arg-type]
    checked = 0
    for page in list(k.pages.values())[:40]:
        if ag._NEVER.match(page.path):
            # The quote form is reached by its move, never a cue.
            assert brain._resolve_page(page.path) is None, page.path
            continue
        brain._path = page.path
        brain._cue_path = page.path
        brain.page = None
        assert brain._resolve_page(page.path) == [page.path], page.path
        for heading in page.headings[:5]:
            assert brain._resolve_show(heading)[0] == heading[:80], (page.path, heading)
            checked += 1
        for faq in page.faqs[:3]:
            assert brain._resolve_faq(faq.q) is not None, (page.path, faq.q)
            checked += 1
    assert checked > 0


@_committed
def test_every_committed_top_category_is_a_menu_cue() -> None:
    k = kb.KNOWLEDGE
    brain = ag.AgroplanetBrain(client=None, knowledge=k)  # type: ignore[arg-type]
    for top in k.tops():
        if not top.hidden:
            assert brain._resolve_menu(top.name) == [top.name], top.name
        assert brain._known_path(top.path) == top.path, top.path


@_committed
def test_the_prompt_fits() -> None:
    prompt = ag._prompt(kb.KNOWLEDGE)
    # About four characters a token: the whole prompt under ~15k tokens.
    assert len(prompt) < 60_000, len(prompt)
    assert kb.KNOWLEDGE.l1 in prompt
