"""Cannon Home's knowledge: the loader, and the committed crawl once it exists.

The loader must take whatever the crawl leaves — a missing file, an empty one,
a broken one — and still import: the demos backend serves every brain from one
process. The catalogue it loads has no price and no stock, ever: prices are read
live, on the visitor's screen. The committed files are checked only once they
exist; until then those tests are skipped.

Run: ``cd demos && uv run pytest tests/test_cannonhome_knowledge.py``
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from voqalize_demos.discovery import discover

discover()

from voqalize_demos._loaded.cannonhome import brain as ch  # noqa: E402
from voqalize_demos._loaded.cannonhome import knowledge as kb  # noqa: E402

L3 = kb.ROOT / "L3"
PRODUCTS = L3 / "products.json"


def test_an_empty_or_missing_knowledge_folder_loads(tmp_path: Path) -> None:
    k = kb.load(tmp_path)
    assert k.products == {} and k.pages == {} and k.categories == {} and k.topics == {}
    assert "cannonhome.cl" in k.l1
    assert k.find_products(query="sábanas king").products == ()
    assert "not loaded" in k.catalogue_index()
    # A prompt still builds on nothing.
    assert "# Prices and stock" in ch._prompt(k)


def test_broken_and_odd_files_are_skipped_not_raised(tmp_path: Path) -> None:
    (tmp_path / "L3").mkdir()
    (tmp_path / "L3" / "pages.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "L3" / "categories.json").write_text('"a string"', encoding="utf-8")
    rows = [
        {"name": "Sábanas King Prueba Blanco", "path": "/sabanas-king-prueba.html", "size": "King"},
        {"name": "", "path": "/sin-nombre.html"},
        {"name": "Fuera", "path": "https://otro-sitio.cl/fuera.html"},
        "junk",
        # A price that slipped into the crawl is never read.
        {
            "name": "Toalla Prueba",
            "path": "https://www.cannonhome.cl/toalla-prueba.html",
            "attributes": {"Color": "Blanco", "Price": "9990", "stock": "4"},
            "threads": "300 hilos",
            "weight_gsm": None,
        },
    ]
    (tmp_path / "L3" / "products.json").write_text(json.dumps(rows), encoding="utf-8")
    k = kb.load(tmp_path)
    assert set(k.products) == {"/sabanas-king-prueba.html", "/toalla-prueba.html"}
    towel = k.products["/toalla-prueba.html"]
    assert towel.attributes == (("Color", "Blanco"),)
    assert towel.threads == 300
    assert k.product("https://cannonhome.cl/toalla-prueba.html") is towel
    assert k.product("/plaza/toalla-prueba.html") is towel


def test_categories_take_their_filter_options_in_either_shape(tmp_path: Path) -> None:
    (tmp_path / "L3").mkdir()
    cats = [
        {
            "path": "/12-ropa-de-cama/20-sabanas",
            "name": "Sábanas",
            "parent": "/12-ropa-de-cama",
            "filters": ["tamano", "color"],
            "options": {"tamano": ["2 Plazas", "King"], "color": [{"label": "Blanco"}]},
        },
        {
            "path": "/bano/toallas",
            "name": "Toallas",
            "filters": [{"var": "color", "options": ["Blanco", "Gris"]}],
        },
    ]
    (tmp_path / "L3" / "categories.json").write_text(json.dumps(cats), encoding="utf-8")
    k = kb.load(tmp_path)
    sheets = k.category("https://cannonhome.cl/12-ropa-de-cama/20-sabanas/")
    assert sheets is not None and sheets.labels("tamano") == ("2 Plazas", "King")
    assert sheets.labels("color") == ("Blanco",)
    towels = k.category("/bano/toallas")
    assert towels is not None and towels.filters == ("color",)
    assert towels.labels("color") == ("Blanco", "Gris")


def _committed() -> list[dict[str, object]]:
    if not PRODUCTS.exists():
        pytest.skip("the crawl has not committed L3/products.json yet")
    data = json.loads(PRODUCTS.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    return data


def test_the_committed_catalogue_has_no_price_or_stock_anywhere() -> None:
    rows = _committed()
    assert rows, "products.json is empty"
    for row in rows:
        keys = {kb.fold(str(k)) for k in row}
        assert not keys & kb.PRICE_KEYS, row
        attrs = row.get("attributes") or {}
        assert isinstance(attrs, dict)
        assert not {kb.fold(str(k)) for k in attrs} & kb.PRICE_KEYS, row


def test_the_committed_catalogue_loads_and_answers_inside_the_budget() -> None:
    import time

    rows = _committed()
    k = kb.load()
    assert len(k.products) >= 0.95 * len(rows)
    for p in k.products.values():
        assert p.path.endswith(".html") and p.name
    asks = ("sábanas king blancas 300 hilos", "toalla blanca", "plumón dos plazas", "almohada")
    for ask in asks:
        started = time.perf_counter()
        found = k.find_products(query=ask)
        assert (time.perf_counter() - started) * 1000 < 20, ask
        assert found.products, ask
    sheets = k.find_products(query="sábanas king 300 hilos").products
    assert sheets and all(kb.size_key(p.size) == "king" for p in sheets if p.size)


def test_every_page_the_backstop_names_is_in_the_crawl_once_there_is_one() -> None:
    k = kb.load()
    if not k.pages:
        pytest.skip("the crawl has not committed L3/pages.json yet")
    for _, paths in ch._ASKED_PAGES:
        assert any(p in ch._FIXED_PAGES or k.page(p) is not None for p in paths), paths
