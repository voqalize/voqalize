"""Fernhollow's catalog as the brain reads it: the shared ``catalog.json`` plus the
indexes :mod:`build_index` precomputed from it.

Everything is loaded once, at import, into plain dicts and lists, so every
lookup a tool makes is a dictionary read. Nothing here is computed per call
that could have been computed offline.

The facts the brain may state about a product are exactly these: its title,
category, room, price and sale price, option values, collections, intro and
highlights — and the material, colour and style words found in those (each with
the phrase it came from). An image similarity ranks; it is never a fact.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, cast

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent
CATALOG_PATH = DEMO / "data" / "catalog.json"
DATA = HERE / "data"
POLICIES_PATH = DEMO / "content" / "policies.json"
JOURNAL_DIR = DEMO / "content" / "journal"

__all__ = [
    "CATALOG",
    "CATEGORIES",
    "PRODUCTS",
    "Catalog",
    "Product",
    "money",
]


@dataclass(frozen=True)
class Variant:
    id: str
    title: str
    option: str
    value: str
    price: float
    compare_at: float | None
    image: str


@dataclass(frozen=True)
class Product:
    """One product, with the attribute words found in its own text."""

    id: str
    title: str
    category: str
    category_slug: str
    room: str
    collections: tuple[str, ...]
    intro: str
    highlights: tuple[str, ...]
    price: float
    compare_at: float | None
    on_sale: bool
    option_name: str
    option_values: tuple[str, ...]
    variants: tuple[Variant, ...]
    image: str
    materials: tuple[str, ...]
    colours: tuple[str, ...]
    styles: tuple[str, ...]
    comfort: tuple[str, ...]
    # word → the phrase of the product's own text it was found in
    sources: dict[str, str] = field(default_factory=dict, compare=False, hash=False)

    @property
    def words(self) -> frozenset[str]:
        return _words(self)

    def variant_for(self, value: str | None) -> Variant:
        """The variant carrying option ``value`` (case-insensitive), else the first."""
        if value:
            for v in self.variants:
                if v.value.lower() == value.lower():
                    return v
        return self.variants[0]

    def price_text(self) -> str:
        """The price as the page shows it, with the was-price when on sale."""
        if self.on_sale and self.compare_at:
            return f"{money(self.price)}, was {money(self.compare_at)}"
        return money(self.price)


@cache
def _words(p: Product) -> frozenset[str]:
    return frozenset((*p.materials, *p.colours, *p.styles))


def money(amount: float) -> str:
    """``$1,150`` or ``$349.99`` — the catalog's own figure, never rounded."""
    if abs(amount - round(amount)) < 0.005:
        return f"${round(amount):,}"
    return f"${amount:,.2f}"


@dataclass(frozen=True)
class Category:
    name: str
    slug: str
    room: str
    count: int


class Catalog:
    """The loaded catalog and its precomputed indexes."""

    def __init__(self) -> None:
        raw = json.loads(CATALOG_PATH.read_text())
        attrs: dict[str, Any] = _read("attributes.json")
        self.rooms: tuple[str, ...] = tuple(raw["rooms"])
        self.categories: dict[str, Category] = {
            c["slug"]: Category(c["name"], c["slug"], c["room"], c["count"])
            for c in raw["categories"]
        }
        self.products: dict[str, Product] = {}
        for p in raw["products"]:
            a = attrs.get(p["id"], {})
            option: dict[str, Any] = p["options"][0] if p["options"] else {"name": "", "values": []}
            variants = tuple(
                Variant(
                    id=str(v["id"]),
                    title=v["title"],
                    option=option["name"],
                    value=str(v["options"].get(option["name"], v["title"])),
                    price=float(v["price"]),
                    compare_at=float(v["compareAtPrice"]) if v["compareAtPrice"] else None,
                    image=v.get("image") or "",
                )
                for v in p["variants"]
            )
            first = variants[0]
            images = p.get("images") or []
            self.products[p["id"]] = Product(
                id=p["id"],
                title=p["title"],
                category=p["category"],
                category_slug=p["categorySlug"],
                room=p["room"],
                collections=tuple(p["collections"]),
                intro=p["intro"],
                highlights=tuple(p["highlights"]),
                price=float(p["priceMin"]),
                compare_at=first.compare_at,
                on_sale=bool(p["onSale"]) and first.compare_at is not None,
                option_name=option["name"],
                option_values=tuple(option["values"]),
                variants=variants,
                image=images[0]["file"] if images else "",
                materials=tuple(w for w, _ in a.get("materials", [])),
                colours=tuple(w for w, _ in a.get("colours", [])),
                styles=tuple(w for w, _ in a.get("styles", [])),
                comfort=tuple(w for w, _ in a.get("comfort", [])),
                sources={
                    w: phrase
                    for key in ("materials", "colours", "styles", "comfort")
                    for w, phrase in a.get(key, [])
                },
            )
        self.order: list[str] = [p["id"] for p in raw["products"]]
        order = self.order
        self.by_category: dict[str, list[str]] = {}
        for p in self.products.values():
            self.by_category.setdefault(p.category_slug, []).append(p.id)
        # id → [(id, similarity 0..100)], same category, most alike first
        self.similar: dict[str, list[tuple[str, int]]] = {
            k: [(order[v[n]], v[n + 1]) for n in range(0, len(v), 2)]
            for k, v in _read("similar.json").items()
        }
        pairs: dict[str, Any] = _read("pairs.json")
        # (id, id) → similarity 0..100, for the category pairs a room or a
        # goes-with list puts side by side, and within each category
        self.pair_sim: dict[tuple[str, str], int] = {
            (a, b): s for a, items in self.similar.items() for b, s in items
        }
        for key, block in pairs.items():
            a_cat, b_cat = key.split("|")
            rows = self.by_category[a_cat]
            cols = self.by_category[b_cat]
            for i, row in enumerate(cast(list[list[int]], block)):
                for j, s in enumerate(row):
                    self.pair_sim[(rows[i], cols[j])] = s
                    self.pair_sim[(cols[j], rows[i])] = s
        # id → category → [(id, score, reason)]
        self.goes_with: dict[str, dict[str, list[tuple[str, int, str]]]] = {
            pid: {cat: [(order[i], s, r) for i, s, r in items] for cat, items in by_cat.items()}
            for pid, by_cat in _read("goes_with.json").items()
        }
        # room → slot → candidate ids, cheapest first
        self.room_slots: dict[str, dict[str, list[str]]] = {
            room: {slot: [order[i] for i in v["ids"]] for slot, v in slots.items()}
            for room, slots in _read("rooms.json").items()
        }
        self.search: dict[str, list[str]] = {
            t: [order[i] for i in ids] for t, ids in _read("search.json").items()
        }
        self.vocab: dict[str, Any] = _read("vocab.json")
        # "image" when the neighbours came from image embeddings, "words" when
        # the index was rebuilt without the images
        self.similarity_source: str = str(self.vocab.get("similarity", "words"))

    def get(self, pid: str) -> Product | None:
        return self.products.get(pid)

    def sim(self, a: str, b: str) -> int:
        """How alike two products look, 0..100 — for ranking only."""
        if a == b:
            return 100
        return self.pair_sim.get((a, b), 0)


def _read(name: str) -> Any:
    return json.loads((DATA / name).read_text())


CATALOG = Catalog()
PRODUCTS = CATALOG.products
CATEGORIES = CATALOG.categories
