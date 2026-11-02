"""The filter rail of a listing page, as the brain maps the shopper's words to it.

A room or category page filters by the option values of its own products —
``Material: Ceramic``, ``Finish: Walnut`` — and the page reports exactly which
facets and values its rail offers (``listing_viewed``). This module maps what
the shopper said onto those labels:

- a word that is one of the rail's values ("ceramic" → Material: Ceramic);
- a near spelling of one (character trigrams), for transcription noise;
- a broad word the fixed lists expand ("wood" → Oak and Walnut, when the rail
  offers those), which is an assumption said aloud.

When the page in front cannot express a request, :func:`best_page` names the
room or category page whose rail can, from the catalog's own option values, so
Emily goes there and filters on its rail rather than on a page of her own.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache

from . import words as w
from .catalog import CATALOG

__all__ = ["SORTS", "RailMap", "best_page", "map_words", "page_facets", "sort_key"]

#: The page's own sort control: its keys, and what a shopper says for each.
SORTS: Mapping[str, tuple[str, ...]] = {
    "price-asc": ("cheapest", "lowest price", "price low", "low to high", "least expensive"),
    "price-desc": ("most expensive", "highest price", "price high", "high to low", "priciest"),
    "sale": ("on sale", "sale first", "deals", "discount"),
    "featured": ("featured", "default", "recommended"),
}


def sort_key(said: str) -> str | None:
    """The sort control's key for what was said, or ``None``."""
    s = w.normalise(said).strip()
    if s in SORTS:
        return s
    for key, phrases in SORTS.items():
        if any(p in s for p in phrases):
            return key
    return None


@dataclass(frozen=True)
class RailMap:
    filters: tuple[tuple[str, str], ...]  # (facet, value), the rail's own labels
    assumptions: tuple[str, ...]
    unmatched: tuple[str, ...]


def _grams(text: str) -> frozenset[str]:
    s = f"  {text} "
    return frozenset(s[i : i + 3] for i in range(len(s) - 2))


def _near(a: str, b: str) -> float:
    ga, gb = _grams(a), _grams(b)
    return len(ga & gb) / len(ga | gb) if ga and gb else 0.0


def _family(word: str) -> tuple[str, ...]:
    for families in (w.MATERIAL_FAMILIES, w.COLOUR_FAMILIES):
        if word in families:
            return families[word]
    return ()


def map_words(words: Sequence[str], facets: Mapping[str, Sequence[str]]) -> RailMap:
    """The shopper's words as the rail's (facet, value) pairs."""
    values = [(f, v, w.normalise(v).strip()) for f, vs in facets.items() for v in vs]
    out: list[tuple[str, str]] = []
    assumptions: list[str] = []
    unmatched: list[str] = []
    for raw in words:
        said = w.normalise(raw).strip()
        if not said:
            continue
        # "material ceramic", "finish: walnut" name the facet too
        facet_hint = next(
            (f for f in facets if said.startswith(w.normalise(f).strip() + " ")), None
        )
        if facet_hint is not None:
            said = said[len(w.normalise(facet_hint).strip()) + 1 :].strip()
        pool = [x for x in values if facet_hint is None or x[0] == facet_hint]
        exact = [(f, v) for f, v, n in pool if n == said]
        if exact:
            out += exact[:1]
            continue
        family = [(f, v) for f, v, n in pool if n in _family(said)]
        if family:
            out += family
            names = " and ".join(v for _, v in family)
            assumptions.append(f"I read '{raw}' as {names}")
            continue
        scored = sorted(((_near(said, n), f, v) for f, v, n in pool), reverse=True)
        if (
            scored
            and scored[0][0] >= 0.4
            and (len(scored) == 1 or scored[0][0] - scored[1][0] > 0.1)
        ):
            _, f, v = scored[0]
            out.append((f, v))
            if w.normalise(v).strip() != said:
                assumptions.append(f"I took '{raw}' as {v}")
            continue
        unmatched.append(raw)
    return RailMap(tuple(dict.fromkeys(out)), tuple(assumptions), tuple(unmatched))


@cache
def page_facets(page: str) -> dict[str, tuple[str, ...]]:
    """The rail a room or category page offers, from its products' options."""
    kind, _, ident = page.partition("/")
    if kind == "category":
        ids = CATALOG.by_category.get(ident, [])
    elif kind == "room":
        ids = [p.id for p in CATALOG.products.values() if p.room == ident]
    else:
        return {}
    facets: dict[str, list[str]] = {}
    for pid in ids:
        p = CATALOG.products[pid]
        for v in p.option_values:
            vals = facets.setdefault(p.option_name, [])
            if v not in vals:
                vals.append(v)
    return {f: tuple(vs) for f, vs in facets.items()}


def _pages() -> list[str]:
    return [f"category/{c}" for c in CATALOG.categories] + [f"room/{r}" for r in CATALOG.rooms]


def best_page(
    words: Sequence[str], *, category: str | None = None, room: str | None = None
) -> tuple[str, RailMap] | None:
    """The room or category page whose rail can express every word — the one
    the shopper named if it can, else the category that can with the most
    products, else a room."""
    named = [f"category/{category}"] if category else [f"room/{room}"] if room else []
    candidates = named or _pages()
    best: tuple[int, int, str, RailMap] | None = None
    for page in candidates:
        m = map_words(words, page_facets(page))
        if m.unmatched or (words and not m.filters):
            continue
        kind, _, ident = page.partition("/")
        size = (
            len(CATALOG.by_category.get(ident, []))
            if kind == "category"
            else sum(1 for p in CATALOG.products.values() if p.room == ident)
        )
        rank = (0 if kind == "category" else 1, -size)
        if best is None or rank < (best[0], best[1]):
            best = (rank[0], rank[1], page, m)
    if best is None:
        return None
    return best[2], best[3]
