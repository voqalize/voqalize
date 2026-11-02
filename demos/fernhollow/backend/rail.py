"""A listing page's filter rail, and the shopper's words mapped onto it — by the
facet's TYPE, never by its name.

The page describes its rail in ``listing_viewed``: each facet has a ``kind``,
and the kind decides how a spoken constraint can land on it.

``options``
    values to tick (Category, Material, Finish, Fabric, Style, Height…). A word
    matches a value exactly, by a near spelling, by naming the facet with it
    ("walnut finish"), or — a broad word from the fixed lists — several values
    ("wood" → Oak and Walnut), which is an assumption said aloud.
``toggle``
    one switch ("On sale"): matched by its own label or name.
``bands`` / ``range``
    numbers: "under 300", "over 2 thousand", "between 2 and 4 hundred" become
    a min and/or max on the facet the words name, else the page's only numeric
    facet. A band label ("Under $300") matches as an option would.
``sort``
    the page's sort options, by what people say ("cheapest first").

Nothing here names a facet the store happens to have: a facet the brain has
never seen works the same way, by its kind. A multi-part request is split into
its constraints; each one the page can express becomes its own move, and the
rest are reported, so one part the page cannot do never blocks the others.

When the page in front cannot express the named things at all,
:func:`best_page` picks the room or category page whose rail (from the
catalog's own options) can.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from . import words as w
from .catalog import CATALOG

__all__ = [
    "SORTS",
    "Band",
    "Facet",
    "Plan",
    "best_page",
    "facets_from",
    "map_words",
    "numbers",
    "page_facets",
    "plan",
    "sort_key",
    "whole",
]

# ─── The rail, typed ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Band:
    label: str
    min: float | None = None
    max: float | None = None


@dataclass(frozen=True)
class Facet:
    name: str
    kind: str  # "options" | "toggle" | "bands" | "range"
    values: tuple[str, ...] = ()
    active: tuple[str, ...] = ()
    bands: tuple[Band, ...] = ()
    min: float | None = None
    max: float | None = None

    @property
    def numeric(self) -> bool:
        return self.kind in ("bands", "range")


def _value(v: Any) -> str:
    if isinstance(v, Mapping):
        return str(v.get("value") or v.get("label") or "")  # pyright: ignore[reportUnknownMemberType]
    return str(v)


def facets_from(raw: Any, active: Mapping[str, Sequence[str]] | None = None) -> list[Facet]:
    """The page's facets in either shape it has sent: the typed list
    (``[{name, kind, values, bands, active, min, max}]``) or the first
    ``{name: [values]}`` map, which is all ``options``."""
    out: list[Facet] = []
    if isinstance(raw, Mapping):
        for name, values in raw.items():  # pyright: ignore[reportUnknownVariableType]
            kind = "toggle" if [_value(x) for x in values] == [str(name)] else "options"  # pyright: ignore[reportUnknownArgumentType]
            out.append(
                Facet(
                    str(name),
                    kind,
                    tuple(_value(x) for x in values),  # pyright: ignore[reportUnknownArgumentType]
                    tuple((active or {}).get(str(name), ())),
                )
            )
        return out
    for f in raw or []:
        f = dict(f)
        bands = tuple(
            Band(str(b.get("label", "")), b.get("min"), b.get("max")) for b in f.get("bands") or []
        )
        values = tuple(_value(x) for x in f.get("values") or [])
        on = f.get("active")
        if on is True:  # a toggle that is on
            on = list(values[:1]) or [str(f.get("name", ""))]
        elif not isinstance(on, list):
            on = []
        out.append(
            Facet(
                name=str(f.get("name", "")),
                kind=str(f.get("kind", "options")),
                values=values,
                active=tuple(str(x) for x in on),
                bands=bands,
                min=f.get("min"),
                max=f.get("max"),
            )
        )
    return out


# ─── Numbers and comparatives ─────────────────────────────────────────────────

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}  # fmt: skip
_SCALE = {"hundred": 100, "thousand": 1000, "k": 1000, "grand": 1000}
_NUM = re.compile(
    r"(\d[\d,]*(?:\.\d+)?|" + "|".join(sorted(_UNITS, key=len, reverse=True)) + r")"
    r"(?:\s*(hundred|thousand|grand|k)\b)?",
    re.IGNORECASE,
)


def _numbers(text: str) -> list[tuple[float, float]]:
    """Each number in ``text`` and the scale word it carried (1 for none)."""
    out: list[tuple[float, float]] = []
    for m in _NUM.finditer(text):
        raw = m.group(1).lower().replace(",", "")
        n = float(_UNITS[raw]) if raw in _UNITS else float(raw)
        scale = float(_SCALE[m.group(2).lower()]) if m.group(2) else 1.0
        out.append((n * scale, scale))
    return out


def numbers(text: str) -> tuple[float | None, float | None] | None:
    """A min and max from spoken comparatives, or ``None`` when ``text`` names
    no number. "Between 2 and 4 hundred": the scale reaches back to the 2."""
    s = w.normalise(text).replace("$", " ")
    found = _numbers(s)
    if not found:
        return None
    if len(found) >= 2 and re.search(r"\b(between|from|to|and|-)\b", s):
        (a, a_scale), (b, b_scale) = found[0], found[1]
        if b_scale > 1 and a_scale == 1 and a * b_scale <= b:
            a *= b_scale  # "between 2 and 4 hundred": the scale reaches back
        return (min(a, b), max(a, b))
    n = found[0][0]
    if re.search(
        r"\b(under|below|less than|up to|at most|max|maximum|no more than|cheaper than|within)\b", s
    ):
        return (None, n)
    if re.search(r"\b(over|above|more than|at least|min|minimum|from|upwards of)\b", s):
        return (n, None)
    if re.search(r"\b(around|about|roughly)\b", s):
        return (round(n * 0.8, 2), round(n * 1.2, 2))
    return (None, n)


# ─── Sort ─────────────────────────────────────────────────────────────────────

#: What people say for the usual sort orders.
SORTS: Mapping[str, tuple[str, ...]] = {
    "price-asc": ("cheapest", "lowest price", "price low", "low to high", "least expensive"),
    "price-desc": ("most expensive", "highest price", "price high", "high to low", "priciest"),
    "sale": ("on sale", "sale first", "deals", "discount"),
    "featured": ("featured", "default", "recommended"),
}


def sort_key(said: str, options: Sequence[str] = ()) -> str | None:
    """The sort option for what was said — one of the page's ``options`` when
    it gave them, else one of :data:`SORTS`."""
    s = w.normalise(said).strip()
    keys = list(options) or list(SORTS)
    for key in keys:
        if s == w.normalise(key).strip():
            return key
    for key, phrases in SORTS.items():
        if key in keys and any(p in s for p in phrases):
            return key
    scored = sorted(((_near(s, w.normalise(k)), k) for k in keys), reverse=True)
    if scored and scored[0][0] >= 0.4:
        return scored[0][1]
    return None


# ─── Words onto options ───────────────────────────────────────────────────────


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


def _norm(s: str) -> str:
    return w.normalise(s).strip()


def _hint(said: str, names: Sequence[str]) -> tuple[str | None, str]:
    """A facet named before or after the value: "material ceramic", "walnut
    finish", "Finish: walnut"."""
    for f in names:
        n = _norm(f)
        if said.startswith(n + " "):
            return f, said[len(n) + 1 :].strip()
        if said.endswith(" " + n):
            return f, said[: -len(n) - 1].strip()
    return None, said


def map_words(words: Sequence[str], facets: Mapping[str, Sequence[str]]) -> RailMap:
    """The shopper's words as (facet, value) pairs of a rail's option values."""
    values = [(f, v, _norm(v)) for f, vs in facets.items() for v in vs]
    out: list[tuple[str, str]] = []
    assumptions: list[str] = []
    unmatched: list[str] = []
    for raw in words:
        said = _norm(raw)
        if not said:
            continue
        facet_hint, said = _hint(said, list(facets))
        pool = [x for x in values if facet_hint is None or x[0] == facet_hint]
        exact = [(f, v) for f, v, n in pool if n == said]
        if exact:
            out += exact[:1]
            continue
        family = [(f, v) for f, v, n in pool if n in _family(said)]
        if family:
            out += family
            assumptions.append(f"I read '{raw}' as {' and '.join(v for _, v in family)}")
            continue
        scored = sorted(((_near(said, n), f, v) for f, v, n in pool), reverse=True)
        if (
            scored
            and scored[0][0] >= 0.4
            and (len(scored) == 1 or scored[0][0] - scored[1][0] > 0.1)
        ):
            _, f, v = scored[0]
            out.append((f, v))
            if _norm(v) != said:
                assumptions.append(f"I took '{raw}' as {v}")
            continue
        unmatched.append(raw)
    return RailMap(tuple(dict.fromkeys(out)), tuple(assumptions), tuple(unmatched))


# ─── A whole request onto a typed rail ────────────────────────────────────────


@dataclass
class Plan:
    """The moves for the parts the page can express, and the parts it cannot."""

    moves: list[tuple[str, dict[str, Any]]] = field(
        default_factory=list[tuple[str, dict[str, Any]]]
    )
    assumptions: list[str] = field(default_factory=list[str])
    unmatched: list[str] = field(default_factory=list[str])
    matched_words: int = 0


def whole(n: float) -> float | int:
    """300.0 as 300, for the page."""
    return int(n) if float(n).is_integer() else n


_PRICEY = re.compile(r"price|cost|\$|dollar", re.IGNORECASE)


def _numeric_facet(said: str, facets: Sequence[Facet]) -> Facet | None:
    numeric = [f for f in facets if f.numeric]
    named = [f for f in numeric if _norm(f.name) in said]
    if named:
        return named[0]
    priced = [f for f in numeric if _PRICEY.search(f.name) or any("$" in b.label for b in f.bands)]
    if priced:
        return priced[0]
    return numeric[0] if len(numeric) == 1 else None


def plan(
    constraints: Sequence[str],
    facets: Sequence[Facet],
    *,
    sort: str | None = None,
    sort_options: Sequence[str] = (),
    price: tuple[float | None, float | None] | None = None,
    price_anyway: bool = False,
) -> Plan:
    """Every spoken constraint onto the rail, by facet type."""
    out = Plan()
    options = {
        f.name: [*f.values, *(b.label for b in f.bands)]
        for f in facets
        if f.kind in ("options", "bands")
    }
    for raw in constraints:
        said = _norm(raw)
        if not said:
            continue
        # a toggle, by its own label or name
        toggle = next(
            (
                f
                for f in facets
                if f.kind == "toggle"
                and (_norm(f.name) in said or any(_norm(v) in said for v in f.values))
            ),
            None,
        )
        if toggle is not None:
            value = toggle.values[0] if toggle.values else toggle.name
            if value not in toggle.active:
                out.moves.append(("listing.filter", {"facet": toggle.name, "value": value}))
            out.matched_words += 1
            continue
        # a number onto a bands / range facet
        bounds = numbers(said)
        if bounds is not None:
            target = _numeric_facet(said, facets)
            if target is None and not price_anyway:
                out.unmatched.append(raw)
                continue
            args: dict[str, Any] = {"facet": target.name if target else "Price"}
            if bounds[0] is not None:
                args["min"] = whole(bounds[0])
            if bounds[1] is not None:
                args["max"] = whole(bounds[1])
            out.moves.append(("listing.range", args))
            continue
        # a value (or band label) of an options / bands facet
        m = map_words([raw], options)
        if m.filters:
            active = {f.name: f.active for f in facets}
            for f, v in m.filters:
                if v in active.get(f, ()):
                    continue
                out.moves.append(("listing.filter", {"facet": f, "value": v}))
            out.assumptions += m.assumptions
            out.matched_words += 1
            continue
        out.unmatched.append(raw)
    if price is not None and (price[0] is not None or price[1] is not None):
        target = _numeric_facet("price", facets)
        if target is not None:
            args = {"facet": target.name}
            if price[0] is not None:
                args["min"] = whole(price[0])
            if price[1] is not None:
                args["max"] = whole(price[1])
            out.moves.append(("listing.range", args))
        elif price_anyway:
            args = {"facet": "Price"}
            if price[0] is not None:
                args["min"] = whole(price[0])
            if price[1] is not None:
                args["max"] = whole(price[1])
            out.moves.append(("listing.range", args))
        else:
            out.unmatched.append("price")
    if sort:
        key = sort_key(sort, sort_options)
        if key is not None:
            out.moves.append(("listing.sort", {"by": key}))
        else:
            out.unmatched.append(sort)
    return out


# ─── The page that can ────────────────────────────────────────────────────────


@cache
def page_facets(page: str) -> dict[str, tuple[str, ...]]:
    """The option values a room or category page's rail offers, from its
    products' own options."""
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
