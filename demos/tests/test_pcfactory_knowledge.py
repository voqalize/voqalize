"""PC Factory's knowledge: the loader, and the committed crawl once it exists.

The loader must take whatever the crawl leaves — a missing file, an empty one,
a broken one — and still import: the demos backend serves every brain from one
process. There is no product catalogue and no price or stock in any file:
products are read live, in the visitor's browser. Categories resolve by name,
alias, id or path; a facet is one the category lists; a cue is checked against
the pages the crawl kept. The committed files are checked only once they exist.

Run: ``cd demos && uv run pytest tests/test_pcfactory_knowledge.py``
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.pcfactory import brain as pc  # noqa: E402
from voqalize_demos._loaded.pcfactory import knowledge as kb  # noqa: E402

L3 = kb.ROOT / "L3"

CATEGORIES = [
    {
        "id": 636,
        "path": "/categoria/computadores-y-tablets",
        "name": "Computadores y Tablets",
        "parent": None,
        "level": 1,
        "aliases": [],
        "products": 2000,
        "facets": [],
    },
    {
        "id": 735,
        "path": "/categoria/computadores-y-tablets/notebooks",
        "name": "Notebooks",
        "parent": "/categoria/computadores-y-tablets",
        "level": 2,
        "aliases": [],
        "products": 400,
        "facets": [],
    },
    {
        "id": 425,
        "path": "/categoria/computadores-y-tablets/notebooks/notebooks",
        "name": "Notebooks",
        "parent": "/categoria/computadores-y-tablets/notebooks",
        "level": 3,
        "aliases": [],
        "products": 158,
        "facets": [
            {"name": "Marcas", "param": "marcas", "options": ["Lenovo", "HP (38)"]},
            {"name": "RAM", "param": "735~22~", "options": ["8GB", "16GB"]},
            {"name": "Sucursales", "param": "sucursales", "options": ["Internet", "Maipú"]},
        ],
    },
    {
        "id": 916,
        "path": "/categoria/computadores-y-tablets/notebooks/notebooks-gamer",
        "name": "Notebooks Gamer",
        "parent": "/categoria/computadores-y-tablets/notebooks",
        "level": 3,
        "aliases": ["/categoria/gamer-y-poder-grafico/notebooks-gamer"],
        "products": 60,
        "facets": [],
    },
    {
        "id": 334,
        "path": "/categoria/partes-y-piezas-componentes/tarjetas-graficas",
        "name": "Tarjetas Gráficas",
        "parent": "/categoria/partes-y-piezas-componentes",
        "level": 2,
        "aliases": [],
        "products": 120,
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
                    "id": "2",
                    "name": "Maipú",
                    "zone": "Santiago",
                    "address": "Av. Pajaritos 2000",
                    "city": "Maipú",
                    "region": "Metropolitana",
                    "hours": "",
                },
                {
                    "id": "7",
                    "name": "Costanera Center",
                    "zone": "Santiago",
                    "address": "Av. Andrés Bello 2425",
                    "city": "Providencia",
                    "region": "Metropolitana",
                    "hours": "Lunes a Domingo 10:00 a 21:00",
                },
            ]
        ),
        encoding="utf-8",
    )
    return root


def test_an_empty_or_missing_knowledge_folder_loads(tmp_path: Path) -> None:
    k = kb.load(tmp_path)
    assert k.pages == {} and k.categories == {} and k.topics == {} and k.stores == ()
    assert "PC Factory" in k.l1
    assert k.find_category("notebooks") is None
    # A prompt still builds on nothing.
    prompt = pc._prompt(k)
    assert "# Prices and stock" in prompt and "not loaded" in prompt


def test_broken_and_odd_files_are_skipped_not_raised(tmp_path: Path) -> None:
    (tmp_path / "L3").mkdir()
    (tmp_path / "L3" / "pages.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "L3" / "stores.json").write_text('"a string"', encoding="utf-8")
    (tmp_path / "L3" / "categories.json").write_text(
        json.dumps(
            [
                {"id": 1, "path": "https://otro-sitio.cl/categoria/x", "name": "Fuera"},
                {"id": 2, "path": "/categoria/sin-nombre"},
                "junk",
                {"id": "3", "path": "https://www.pcfactory.cl/categoria/ok", "name": "Ok"},
            ]
        ),
        encoding="utf-8",
    )
    k = kb.load(tmp_path)
    assert set(k.categories) == {"/categoria/ok"}
    assert k.categories["/categoria/ok"].id == 3
    assert k.pages == {} and k.stores == ()


@pytest.mark.parametrize(
    ("said", "cid"),
    [
        ("Notebooks", 425),
        ("notebook", 425),
        ("laptops", 425),
        ("notebooks gamer", 916),
        ("gaming laptop", 916),
        ("tarjetas de video", 334),
        ("Tarjeta Gráfica", 334),
        ("graphics cards", 334),
        ("916", 916),
        ("/categoria/computadores-y-tablets/notebooks/notebooks?size=12&marcas=299", 425),
        ("/categoria/gamer-y-poder-grafico/notebooks-gamer", 916),
        ("heladeras", None),
    ],
)
def test_a_category_resolves_by_name_alias_id_or_path(
    tmp_path: Path, said: str, cid: int | None
) -> None:
    k = kb.load(_write(tmp_path))
    got = k.find_category(said)
    assert (got.id if got else None) == cid, (said, got)


def test_an_alias_path_is_the_same_category(tmp_path: Path) -> None:
    k = kb.load(_write(tmp_path))
    alias = k.category("/categoria/gamer-y-poder-grafico/notebooks-gamer")
    assert alias is not None and alias.id == 916
    assert len(k.unique_categories()) == len(CATEGORIES)


def test_facets_are_named_as_the_page_writes_them(tmp_path: Path) -> None:
    k = kb.load(_write(tmp_path))
    cat = k.find_category("notebooks")
    assert cat is not None
    # The API's "Sucursales" is the page's "Tiendas"; a count is not an option.
    assert cat.facet_names == ("Marcas", "RAM", "Tiendas")
    assert cat.facet("tiendas") is cat.facet("Sucursales") is not None
    assert cat.facet("marca") is not None and cat.facet("Marca").options == ("Lenovo", "HP")  # type: ignore[union-attr]
    assert cat.facet("Pantalla") is None


def test_stores_match_by_name_or_comuna(tmp_path: Path) -> None:
    k = kb.load(_write(tmp_path))
    assert k.store("la tienda de Maipú").name == "Maipú"  # type: ignore[union-attr]
    assert k.store("maipu").name == "Maipú"  # type: ignore[union-attr]
    assert k.store("el Costanera").name == "Costanera Center"  # type: ignore[union-attr]
    assert k.store("Providencia").name == "Costanera Center"  # type: ignore[union-attr]
    assert k.store("Punta Arenas") is None


@pytest.mark.parametrize(
    ("raw", "path"),
    [
        (
            "https://www.pcfactory.cl/producto/57233-lenovo-ideapad-slim-3?origin=PCF",
            "/producto/57233",
        ),
        ("/producto/57233", "/producto/57233"),
        ("57233", "/producto/57233"),
        ("/categoria/x", None),
    ],
)
def test_a_product_is_its_id(raw: str, path: str | None) -> None:
    assert kb.product_path(raw) == path


def test_a_search_is_its_words() -> None:
    assert kb.search_query("/busqueda-avanzada?search=monitor+27&size=12") == "monitor 27"
    assert kb.search_path("Monitor 27") == "/busqueda-avanzada?search=monitor+27"
    assert kb.search_query("/categoria/x") is None


def test_filter_cues_validate_against_the_categorys_facets(tmp_path: Path) -> None:
    k = kb.load(_write(tmp_path))
    brain = pc.PcFactoryBrain(client=None, knowledge=k)  # type: ignore[arg-type]
    path = "/categoria/computadores-y-tablets/notebooks/notebooks"
    cat = k.category(path)
    assert brain._facet_options(path, cat, "marca", "lenovo y hp") == ("Marcas", ["Lenovo", "HP"])
    assert brain._facet_options(path, cat, "RAM", "16 gb") == ("RAM", ["16GB"])
    assert brain._facet_options(path, cat, "Tiendas", "Maipu") == ("Tiendas", ["Maipú"])
    refused = brain._facet_options(path, cat, "RAM", "64GB")
    assert isinstance(refused, str) and "it lists: 8GB, 16GB" in refused
    refused = brain._facet_options(path, cat, "Pantalla", "OLED")
    assert isinstance(refused, str) and "no facet 'Pantalla'" in refused


# ─── The committed crawl ───────────────────────────────────────────────────────

_committed = pytest.mark.skipif(
    not (L3 / "categories.json").exists(), reason="the crawl is not committed yet"
)
#: Keys no knowledge file may carry: prices and stock are read live.
_PRICE_KEYS = re.compile(r'"(?:price|precio|efectivo|stock|card_price|regular_price)"\s*:')


@_committed
def test_no_knowledge_file_holds_a_price_or_stock() -> None:
    for f in L3.glob("*.json"):
        assert not _PRICE_KEYS.search(f.read_text(encoding="utf-8")), f.name


@_committed
def test_the_committed_categories_are_the_stores_tree() -> None:
    k = kb.KNOWLEDGE
    cats = k.unique_categories()
    assert len(cats) >= 16
    assert all(c.path.startswith("/categoria/") for c in cats)
    tops = [c for c in cats if c.level == 1]
    assert 12 <= len(tops) <= 20
    for name in ("notebooks", "tarjetas graficas", "monitores", "smartphones"):
        assert k.find_category(name) is not None, name
    with_facets = [c for c in cats if c.facets]
    assert with_facets, "no category has its facets"
    for c in with_facets:
        assert all(f.name and len(f.options) <= 25 for f in c.facets), c.path


@_committed
def test_the_committed_stores_and_pages() -> None:
    k = kb.KNOWLEDGE
    if (L3 / "stores.json").exists():
        assert 20 <= len(k.stores) <= 40
        assert all(s.name and s.zone for s in k.stores)
    assert "/" in k.pages or k.page("/") is not None
    assert any(p.path.startswith("/centro-de-ayuda") and p.faqs for p in k.pages.values())


@_committed
def test_every_committed_heading_and_faq_is_a_cue_that_resolves() -> None:
    """A {show:} or {faq:} cue naming what a page writes resolves to it, on
    that page, as the page will look it up."""
    k = kb.KNOWLEDGE
    brain = pc.PcFactoryBrain(client=None, knowledge=k)  # type: ignore[arg-type]
    checked = 0
    for page in list(k.pages.values())[:40]:
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
def test_the_prompt_fits() -> None:
    prompt = pc._prompt(kb.KNOWLEDGE)
    # About four characters a token: the whole prompt under ~15k tokens.
    assert len(prompt) < 60_000, len(prompt)
    assert kb.KNOWLEDGE.l1 in prompt
