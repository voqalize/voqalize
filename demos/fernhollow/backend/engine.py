"""Mira's design engines — pure functions over the precomputed catalog.

Every function here is deterministic and reads only dicts the catalog loaded at
import, so each answers in well under a millisecond to a few milliseconds:
the brief and the question that narrows it most, a whole room for a brief and a
budget, one piece swapped, what goes with a piece, look-alikes with one change,
a comparison, a stretched budget, and shopper words mapped to filters with the
assumption said out loud.

What they return is ids, catalog prices and reason codes built from the words
the catalog itself uses. A reason never claims anything an image similarity
suggested: similarity only decides the order.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from functools import cache
from typing import Literal

from . import words as w
from .catalog import CATALOG, Product, money
from .recipes import GOES_WITH, RECIPES, Recipe, Slot

__all__ = [
    "Brief",
    "Filters",
    "Piece",
    "RoomSet",
    "build_room",
    "compare",
    "goes_with",
    "map_terms",
    "more_like",
    "next_question",
    "products_left",
    "stretch_budget",
    "swap_piece",
]

Dim = Literal["room", "styles", "materials", "colours", "budget", "uses"]

TASTE_DIMS: tuple[Dim, ...] = ("styles", "materials", "colours")


# ─── Words → catalog words ────────────────────────────────────────────────────


def _present(key: str) -> set[str]:
    return {word for word, _ in CATALOG.vocab[key]}


_PRESENT = {k: _present(k) for k in ("materials", "colours", "styles")}


@dataclass(frozen=True)
class Mapped:
    """Shopper terms for one list, as catalog words, and what was assumed."""

    words: tuple[str, ...]
    assumptions: tuple[str, ...]
    unmatched: tuple[str, ...]


def _listing(words: Sequence[str]) -> str:
    if len(words) <= 1:
        return "".join(words)
    if len(words) > 5:
        return ", ".join(words[:5]) + " and similar"
    return ", ".join(words[:-1]) + " and " + words[-1]


def map_terms(kind: Literal["materials", "colours", "styles"], terms: Iterable[str]) -> Mapped:
    """Map what the shopper said to the words the catalog uses.

    A word the list has is itself. A broad word ("wood", "neutral") expands to
    the catalog words it covers, and that is an assumption said aloud. A style
    the catalog never uses maps to its nearest one, also said aloud. Anything
    else is reported back unmatched, never guessed."""
    present = _PRESENT[kind]
    vocab = {"materials": w.MATERIALS, "colours": w.COLOURS, "styles": w.STYLES}[kind]
    families = {"materials": w.MATERIAL_FAMILIES, "colours": w.COLOUR_FAMILIES}.get(kind, {})
    out: list[str] = []
    assumptions: list[str] = []
    unmatched: list[str] = []
    for raw in terms:
        term = w.normalise(raw).strip()
        if not term:
            continue
        if term in families:
            covered = [x for x in families[term] if x in present]
            if covered:
                out += covered
                if covered != [term]:
                    assumptions.append(f"I read '{raw}' as {_listing(covered)}")
                continue
        found = [x for x in w.find(term, vocab) if x in present]
        if found:
            out += found
            continue
        if kind == "styles" and term in w.STYLE_NEAREST:
            near = w.STYLE_NEAREST[term]
            out.append(near)
            assumptions.append(f"nothing here is described as '{raw}', so I went with {near}")
            continue
        unmatched.append(raw)
    return Mapped(tuple(dict.fromkeys(out)), tuple(assumptions), tuple(unmatched))


# ─── The brief ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Brief:
    """What the shopper has told Mira, as catalog words."""

    room: str | None = None
    uses: tuple[str, ...] = ()
    materials: tuple[str, ...] = ()
    colours: tuple[str, ...] = ()
    styles: tuple[str, ...] = ()
    budget: float | None = None
    # dimensions the shopper was asked and had no preference on
    skipped: tuple[Dim, ...] = ()

    @property
    def long_hours(self) -> bool:
        return "long hours" in self.uses

    def wanted(self) -> frozenset[str]:
        return frozenset((*self.materials, *self.colours, *self.styles))

    def key(self) -> tuple[object, ...]:
        return (
            self.room,
            self.uses,
            self.materials,
            self.colours,
            self.styles,
            self.budget,
        )


def room_categories(room: str | None) -> list[str]:
    if room is None or room not in RECIPES:
        return list(CATALOG.by_category)
    return list(dict.fromkeys(c for s in RECIPES[room].slots for c in s.categories))


def _matches(p: Product, brief: Brief) -> bool:
    if brief.materials and not set(p.materials) & set(brief.materials):
        return False
    if brief.colours and not set(p.colours) & set(brief.colours):
        return False
    return not (brief.styles and not set(p.styles) & set(brief.styles))


def products_left(brief: Brief) -> list[str]:
    """The products of the brief's room that fit every taste it names."""
    out: list[str] = []
    for cat in room_categories(brief.room):
        for pid in CATALOG.by_category[cat]:
            if _matches(CATALOG.products[pid], brief):
                out.append(pid)
    return out


@dataclass(frozen=True)
class Question:
    dim: Dim | Literal["ready"]
    text: str
    options: tuple[str, ...] = ()


_ROOM_WORDS = {r: RECIPES[r].label for r in RECIPES}


def _dim_values(dim: Dim, ids: list[str]) -> Counter[str]:
    c: Counter[str] = Counter()
    for pid in ids:
        p = CATALOG.products[pid]
        c.update({"styles": p.styles, "materials": p.materials, "colours": p.colours}[dim])
    return c


def _narrowing(dim: Dim, ids: list[str]) -> float | None:
    """Expected share of ``ids`` kept once the shopper names a value of ``dim``,
    each value as likely as it is common. Lower narrows more; ``None`` when the
    dimension cannot split these products."""
    values = _dim_values(dim, ids)
    if len(values) < 2 or not ids:
        return None
    total = sum(values.values())
    return sum((n / total) * (n / len(ids)) for n in values.values())


def next_question(brief: Brief) -> Question:
    """The one question to ask next: the room first, then the taste that splits
    what is left most evenly, then the budget, then — for a home office — the
    hours they sit, then the remaining tastes until two are known."""
    if brief.room is None:
        return Question(
            "room",
            "Which room are we working on?",
            tuple(_ROOM_WORDS[r] for r in ("living", "bedroom", "home-office", "dining")),
        )
    ids = products_left(brief)
    open_dims: list[Dim] = [
        d for d in TASTE_DIMS if not getattr(brief, d) and d not in brief.skipped
    ]
    known = sum(1 for d in TASTE_DIMS if getattr(brief, d))

    def best_taste() -> Question | None:
        ranked: list[tuple[float, Dim]] = sorted(
            ((n, d) for d in open_dims if (n := _narrowing(d, ids)) is not None),
            key=lambda t: (t[0], TASTE_DIMS.index(t[1])),
        )
        if not ranked:
            return None
        dim = ranked[0][1]
        opts = tuple(v for v, _ in _dim_values(dim, ids).most_common(3))
        text = {
            "styles": "What feel are you after — {}?",
            "materials": "Any material you love — {}?",
            "colours": "Which colours do you lean to — {}?",
        }[dim].format(_or(opts))
        return Question(dim, text, opts)

    if known == 0 and (q := best_taste()) is not None:
        return q
    if brief.budget is None and "budget" not in brief.skipped:
        return Question("budget", "What budget should the whole room come in under?")
    if brief.room == "home-office" and not brief.uses and "uses" not in brief.skipped:
        return Question("uses", "Will you sit there for long hours?", ("yes", "no"))
    if known < 2 and (q := best_taste()) is not None:
        return q
    return Question("ready", "That's enough to design with — shall I put the room together?")


def _or(opts: Sequence[str]) -> str:
    if len(opts) <= 1:
        return "".join(opts)
    return ", ".join(opts[:-1]) + " or " + opts[-1]


# ─── Rooms ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Piece:
    slot: str
    product_id: str
    variant_id: str
    reason: str

    @property
    def product(self) -> Product:
        return CATALOG.products[self.product_id]


@dataclass(frozen=True)
class RoomSet:
    room: str
    budget: float | None
    pieces: tuple[Piece, ...]

    @property
    def total(self) -> float:
        return round(sum(p.product.price for p in self.pieces), 2)

    def piece(self, slot: str) -> Piece | None:
        return next((p for p in self.pieces if p.slot == slot), None)

    def with_piece(self, new: Piece) -> RoomSet:
        return replace(self, pieces=tuple(new if p.slot == new.slot else p for p in self.pieces))


@dataclass(frozen=True)
class RoomError:
    reason: str
    lowest_total: float | None = None


def _share(slot: Slot, brief: Brief) -> float:
    if brief.long_hours and slot.long_hours_share is not None:
        return slot.long_hours_share
    return slot.share


def _taste(p: Product, brief: Brief) -> float:
    score = 0.0
    if brief.materials and set(p.materials) & set(brief.materials):
        score += 1.2
    if brief.colours and set(p.colours) & set(brief.colours):
        score += 1.0
    if brief.styles and set(p.styles) & set(brief.styles):
        score += 1.0
    return score


def _comfort(p: Product, slot: Slot, brief: Brief) -> float:
    if brief.long_hours and slot.name == "chair":
        return 1.5 * min(len(p.comfort), 3) / 3
    return 0.0


def _median(values: list[float]) -> float:
    s = sorted(values)
    return s[len(s) // 2]


def _target(slot: Slot, recipe: Recipe, brief: Brief) -> float:
    if brief.budget is not None:
        return _share(slot, brief) * brief.budget
    return _median([CATALOG.products[i].price for i in room_slot_ids(recipe.room, slot.name)])


def _solo(p: Product, slot: Slot, recipe: Recipe, brief: Brief) -> float:
    """A piece's own score: the brief's tastes, comfort where it matters, and how
    close it sits to the slot's usual share of the budget."""
    target = _target(slot, recipe, brief)
    fit = abs(p.price - target) / target if target else 0.0
    return _taste(p, brief) + _comfort(p, slot, brief) - 1.0 * min(fit, 2.0)


def _with(p: Product, others: Iterable[Product]) -> float:
    """How well a piece sits with the pieces already chosen: a shared material
    or colour word, and how alike they look."""
    score = 0.0
    for o in others:
        score += 0.012 * CATALOG.sim(p.id, o.id)
        if set(p.materials) & set(o.materials):
            score += 0.25
        if set(p.colours) & set(o.colours):
            score += 0.15
    return score


BEAM = 24
PER_SLOT = 14


# A room is designed for the adult who asked; pieces made for a child, a baby or
# a pet are found by search and filters, never put into a room set.
_NOT_IN_ROOM_SETS = re.compile(r"\b(children|child|kids?|teen|baby|pet)\b", re.IGNORECASE)


@cache
def room_slot_ids(room: str, slot: str) -> list[str]:
    """A slot's candidates, cheapest first: never a piece made for a child, and
    only pieces whose title names the slot's thing."""
    spec = RECIPES[room].slot(slot)
    must = re.compile(spec.title_has, re.IGNORECASE) if spec and spec.title_has else None
    return [
        i
        for i in CATALOG.room_slots[room][slot]
        if not _NOT_IN_ROOM_SETS.search(CATALOG.products[i].title)
        and (must is None or must.search(CATALOG.products[i].title))
    ]


def _candidates(slot: Slot, recipe: Recipe, brief: Brief, exclude: set[str]) -> list[Product]:
    ids = [i for i in room_slot_ids(recipe.room, slot.name) if i not in exclude]
    ranked = sorted(ids, key=lambda i: (-_solo(CATALOG.products[i], slot, recipe, brief), i))
    keep = ranked[:PER_SLOT] + ids[:3]  # the three cheapest keep a tight budget feasible
    return [CATALOG.products[i] for i in dict.fromkeys(keep)]


def build_room(brief: Brief, *, exclude: Sequence[str] = ()) -> RoomSet | RoomError:
    """One piece per slot of the room's recipe: the set that best fits the
    brief's tastes and shares materials and colours, within the budget, with the
    chair given a bigger share and its comfort weighed when they sit long hours."""
    if brief.room is None or brief.room not in RECIPES:
        return RoomError("no room chosen yet")
    recipe = RECIPES[brief.room]
    slots = recipe.slots
    cheapest = [CATALOG.products[room_slot_ids(recipe.room, s.name)[0]].price for s in slots]
    if brief.budget is not None and sum(cheapest) > brief.budget:
        return RoomError("budget below the lowest set", round(sum(cheapest), 2))
    pools = [_candidates(s, recipe, brief, set(exclude)) for s in slots]
    solo = [
        {p.id: _solo(p, s, recipe, brief) for p in pool}
        for s, pool in zip(slots, pools, strict=True)
    ]
    rest_min = [sum(cheapest[i + 1 :]) for i in range(len(slots))]
    beam: list[tuple[float, float, tuple[Product, ...]]] = [(0.0, 0.0, ())]
    for n, pool in enumerate(pools):
        grown: list[tuple[float, float, tuple[Product, ...]]] = []
        for score, total, chosen in beam:
            for p in pool:
                t = total + p.price
                if brief.budget is not None and t + rest_min[n] > brief.budget + 1e-6:
                    continue
                grown.append((score + solo[n][p.id] + _with(p, chosen), t, (*chosen, p)))
        grown.sort(key=lambda g: (-g[0], g[1], tuple(p.id for p in g[2])))
        beam = grown[:BEAM]
        if not beam:
            return RoomError("no set fits", round(sum(cheapest), 2))
    _, _, chosen = beam[0]
    pieces: list[Piece] = []
    for s, p in zip(slots, chosen, strict=True):
        pieces.append(_piece(s, p, brief, [q for q in chosen if q.id != p.id]))
    return RoomSet(recipe.room, brief.budget, tuple(pieces))


def _piece(slot: Slot, p: Product, brief: Brief, others: Sequence[Product]) -> Piece:
    return Piece(slot.name, p.id, p.variants[0].id, reason_for(p, slot, brief, others))


def reason_for(p: Product, slot: Slot, brief: Brief, others: Sequence[Product]) -> str:
    """Why this piece, in the catalog's own words — never from a photo."""
    if brief.long_hours and slot.name == "chair" and p.comfort:
        return f"{_cap(p.comfort[0])}, for long hours"
    for key in ("materials", "styles", "colours"):
        hit = [x for x in getattr(p, key) if x in getattr(brief, key)]
        if hit:
            return f"{_cap(hit[0])}, as you asked"
    for o in others:
        common = [x for x in p.materials if x in o.materials]
        if common:
            return f"{_cap(common[0])}, like the {_label_of(o)}"
    for o in others:
        common = [x for x in p.colours if x in o.colours]
        if common:
            return f"{_cap(common[0])}, like the {_label_of(o)}"
    if p.on_sale:
        return "On sale"
    return "Sits with the rest of the room"


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _label_of(p: Product) -> str:
    for recipe in RECIPES.values():
        for s in recipe.slots:
            if p.category_slug in s.categories:
                return s.label
    return p.category.lower()


def swap_piece(
    room: RoomSet,
    brief: Brief,
    slot_name: str,
    *,
    want: Sequence[str] = (),
    cheaper: bool = False,
    product_id: str | None = None,
    seen: Sequence[str] = (),
) -> Piece | RoomError:
    """Another piece for one slot, the rest of the room held still: the named
    product, or the best one not yet shown that keeps the room in budget —
    cheaper, or carrying the wanted words, when asked."""
    recipe = RECIPES[room.room]
    slot = recipe.slot(slot_name)
    current = room.piece(slot_name)
    if slot is None or current is None:
        return RoomError(f"no {slot_name} in this room")
    others = [p.product for p in room.pieces if p.slot != slot_name]
    if product_id is not None:
        p = CATALOG.products.get(product_id)
        if p is None or p.category_slug not in slot.categories:
            return RoomError(f"that is not a {slot.label}")
        return _piece(slot, p, brief, others)
    room_without = room.total - current.product.price
    wanted = set(want)
    best: tuple[float, str] | None = None
    for pid in room_slot_ids(recipe.room, slot_name):
        if pid == current.product_id or pid in seen:
            continue
        p = CATALOG.products[pid]
        if cheaper and p.price >= current.product.price:
            continue
        if wanted and not wanted & p.words:
            continue
        if room.budget is not None and room_without + p.price > room.budget + 1e-6:
            continue
        score = _solo(p, slot, recipe, brief) + _with(p, others)
        if best is None or score > best[0] or (score == best[0] and pid < best[1]):
            best = (score, pid)
    if best is None:
        return RoomError("nothing else fits")
    return _piece(slot, CATALOG.products[best[1]], brief, others)


# ─── Goes with, more like, compare ────────────────────────────────────────────


@dataclass(frozen=True)
class Item:
    product_id: str
    reason: str = ""
    differences: tuple[str, ...] = ()
    variant_id: str | None = None


_REASON = {
    "material": "Shares the {}",
    "colour": "Same {} tone",
    "style": "Same {} feel",
}


def _reason_text(code: str, anchor: Product) -> str:
    if ":" in code:
        kind, word = code.split(":", 1)
        return _REASON[kind].format(word)
    return f"Picked to sit with the {_label_of(anchor)}"


def goes_with(
    anchor_id: str, *, category: str | None = None, exclude: Sequence[str] = (), limit: int = 4
) -> list[Item]:
    """Pieces to sit beside the anchor: one category's best, or the best of
    each compatible category in turn."""
    anchor = CATALOG.products[anchor_id]
    lists = CATALOG.goes_with.get(anchor_id, {})
    skip = set(exclude)
    if category is not None:
        pool = [x for x in lists.get(category, []) if x[0] not in skip]
        return [Item(i, _reason_text(r, anchor)) for i, _, r in pool[:limit]]
    out: list[Item] = []
    depth = 0
    cats = [c for c in GOES_WITH.get(anchor.category_slug, ()) if c in lists]
    taken_cats: set[str] = set()
    while len(out) < limit and depth < 5 and cats:
        for cat in cats:
            if cat in taken_cats and depth == 0:
                continue
            pool = [
                x
                for x in lists[cat]
                if x[0] not in skip and x[0] not in {o.product_id for o in out}
            ]
            if depth < len(pool) and pool:
                i, _, r = pool[0]
                out.append(Item(i, _reason_text(r, anchor)))
                taken_cats.add(cat)
            if len(out) >= limit:
                break
        depth += 1
    return out[:limit]


Change = Literal["cheaper", "on_sale", "option", "material", "colour", "style"]


def more_like(
    anchor_id: str, change: Change, value: str | None = None, *, limit: int = 4
) -> tuple[list[Item], str | None]:
    """Look-alikes of the anchor from its own category, with one thing changed:
    cheaper, on sale, offered in an option value, or carrying a material,
    colour or style word the anchor does not. Also returns the anchor's own
    variant id when the anchor itself comes in the asked option value."""
    anchor = CATALOG.products[anchor_id]
    out: list[Item] = []
    own: str | None = None
    target = w.normalise(value or "").strip()
    if change == "option" and target:
        for v in anchor.variants:
            if v.value.lower() == target:
                own = v.id
    for pid, _sim in CATALOG.similar.get(anchor_id, []):
        p = CATALOG.products[pid]
        diffs: list[str] = []
        variant: str | None = None
        if change == "cheaper":
            if p.price >= anchor.price:
                continue
            diffs.append(f"{money(p.price)} against {money(anchor.price)}")
        elif change == "on_sale":
            if not p.on_sale or p.compare_at is None:
                continue
            diffs.append(f"on sale at {money(p.price)}, was {money(p.compare_at)}")
        elif change == "option":
            match = next((v for v in p.variants if v.value.lower() == target), None)
            if match is None:
                continue
            variant = match.id
            diffs.append(f"comes in {match.value}")
        else:
            key = {"material": "materials", "colour": "colours", "style": "styles"}[change]
            mapped = map_terms(key, [value or ""]).words  # type: ignore[arg-type]
            have = [x for x in getattr(p, key) if x in mapped and x not in getattr(anchor, key)]
            if not have:
                continue
            diffs.append(have[0])
        if change != "cheaper":
            diffs.append(money(p.price))
        out.append(Item(pid, differences=tuple(diffs), variant_id=variant))
        if len(out) >= limit:
            break
    return out, own


@dataclass(frozen=True)
class Row:
    label: str
    values: tuple[str, ...]
    winner: int | None = None


@dataclass(frozen=True)
class Comparison:
    product_ids: tuple[str, ...]
    rows: tuple[Row, ...]
    summary: str


def _fit(p: Product, brief: Brief) -> list[str]:
    wanted = brief.wanted()
    return [x for x in (*p.materials, *p.styles, *p.colours) if x in wanted]


def compare(ids: Sequence[str], brief: Brief) -> Comparison:
    """Two or three products side by side. Ordered by how much of the brief each
    fits, then comfort when they sit long hours, then price; each row names
    its winner where one exists."""
    products = [CATALOG.products[i] for i in dict.fromkeys(ids) if i in CATALOG.products]
    long_hours = brief.long_hours or all(p.category_slug == "office-chairs" for p in products)
    products.sort(
        key=lambda p: (-len(_fit(p, brief)), -(len(p.comfort) if long_hours else 0), p.price, p.id)
    )
    rows: list[Row] = []

    def lowest(values: list[float]) -> int | None:
        m = min(values)
        return values.index(m) if values.count(m) == 1 else None

    def most(counts: list[int]) -> int | None:
        m = max(counts)
        return counts.index(m) if m > 0 and counts.count(m) == 1 else None

    rows.append(
        Row("Price", tuple(p.price_text() for p in products), lowest([p.price for p in products]))
    )
    if brief.wanted():
        fits = [_fit(p, brief) for p in products]
        rows.append(
            Row(
                "Fits your brief",
                tuple(", ".join(f) or "—" for f in fits),
                most([len(f) for f in fits]),
            )
        )
    if long_hours:
        comfort = [list(p.comfort) for p in products]
        rows.append(
            Row(
                "For long hours",
                tuple(", ".join(c) or "—" for c in comfort),
                most([len(c) for c in comfort]),
            )
        )
    for label, key in (("Material", "materials"), ("Colour", "colours"), ("Style", "styles")):
        vals = tuple(", ".join(getattr(p, key)) or "—" for p in products)
        if any(v != "—" for v in vals):
            rows.append(Row(label, vals))
    rows.append(
        Row("Options", tuple(f"{p.option_name}: {', '.join(p.option_values)}" for p in products))
    )
    summary = _summary(products, rows)
    return Comparison(tuple(p.id for p in products), tuple(rows), summary)


def _summary(products: Sequence[Product], rows: Sequence[Row]) -> str:
    """One sentence naming who wins what, from the rows themselves."""
    wins: dict[int, list[str]] = {}
    for row in rows:
        if row.winner is not None:
            label = {
                "Price": "costs less",
                "Fits your brief": "fits more of your brief",
                "For long hours": "is built more for long hours",
            }[row.label]
            wins.setdefault(row.winner, []).append(label)
    if not wins:
        return "They are close; it comes down to which look you prefer."
    parts = [f"{products[i].title} {' and '.join(v)}" for i, v in sorted(wins.items())]
    return "; ".join(parts) + "."


# ─── Stretching the budget ────────────────────────────────────────────────────


@dataclass(frozen=True)
class Swap:
    slot: str
    from_id: str
    to_id: str

    @property
    def was(self) -> float:
        return CATALOG.products[self.from_id].price

    @property
    def now(self) -> float:
        return CATALOG.products[self.to_id].price


@dataclass(frozen=True)
class Stretch:
    room: RoomSet
    swaps: tuple[Swap, ...]
    saved: float
    upgrade: Swap | None
    moved_to: str | None


LOOKALIKE = 70  # how alike a stand-in must look to replace a piece, 0..100


@cache
def _lookalike_floor() -> int:
    """With image vectors the threshold is an image similarity; the word-overlap
    fallback (an index built without the images) scores lower, so it asks for less."""
    return LOOKALIKE if CATALOG.similarity_source == "image" else 20


def stretch_budget(room: RoomSet, brief: Brief, priority: str | None = None) -> Stretch:
    """Swap pieces for on-sale look-alikes at their real sale prices, then spend
    the saving on the shopper's priority slot — the chair when they sit long
    hours, unless they named another."""
    recipe = RECIPES[room.room]
    if priority is None and brief.long_hours and recipe.slot("chair") is not None:
        priority = "chair"
    floor = _lookalike_floor()
    swaps: list[Swap] = []
    new = room
    for piece in room.pieces:
        if piece.slot == priority:
            continue
        cur = piece.product
        slot = recipe.slot(piece.slot)
        assert slot is not None
        for pid, sim in CATALOG.similar.get(cur.id, []):
            p = CATALOG.products[pid]
            if sim < floor:
                break
            if not p.on_sale or p.price >= cur.price:
                continue
            # A stand-in may give up one of the brief's tastes, never more.
            if _taste(p, brief) < _taste(cur, brief) - 1.0 - 1e-9:
                continue
            others = [q.product for q in new.pieces if q.slot != piece.slot]
            swaps.append(Swap(piece.slot, cur.id, p.id))
            new = new.with_piece(_piece(slot, p, brief, others))
            break
    saved = round(sum(s.was - s.now for s in swaps), 2)
    upgrade: Swap | None = None
    if priority is not None and saved > 0 and (cur_piece := new.piece(priority)) is not None:
        slot = recipe.slot(priority)
        assert slot is not None
        cur = cur_piece.product
        others = [q.product for q in new.pieces if q.slot != priority]
        best: tuple[float, str] | None = None
        for pid in room_slot_ids(recipe.room, priority):
            p = CATALOG.products[pid]
            if p.price <= cur.price or p.price > cur.price + saved + 1e-6:
                continue
            score = _taste(p, brief) + 2 * _comfort(p, slot, brief) + _with(p, others)
            if score <= _taste(cur, brief) + 2 * _comfort(cur, slot, brief) + _with(cur, others):
                continue
            if best is None or score > best[0] or (score == best[0] and pid < best[1]):
                best = (score, pid)
        if best is not None:
            upgrade = Swap(priority, cur.id, best[1])
            new = new.with_piece(_piece(slot, CATALOG.products[best[1]], brief, others))
    return Stretch(new, tuple(swaps), saved, upgrade, upgrade.slot if upgrade else None)


# ─── Filters ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Filters:
    room: str | None = None
    category: str | None = None
    materials: tuple[str, ...] = ()
    colours: tuple[str, ...] = ()
    styles: tuple[str, ...] = ()
    price_min: float | None = None
    price_max: float | None = None
    on_sale: bool | None = None
    assumptions: tuple[str, ...] = field(default=(), compare=False)

    def results(self) -> list[str]:
        """The matching products, closest to the filters first, then cheapest."""
        if self.category is not None:
            cats = [self.category]
        elif self.room is not None:
            cats = [c for c, cat in CATALOG.categories.items() if cat.room == self.room]
        else:
            cats = list(CATALOG.by_category)
        out: list[tuple[float, str]] = []
        for cat in cats:
            for pid in CATALOG.by_category.get(cat, []):
                p = CATALOG.products[pid]
                if self.materials and not set(p.materials) & set(self.materials):
                    continue
                if self.colours and not set(p.colours) & set(self.colours):
                    continue
                if self.styles and not set(p.styles) & set(self.styles):
                    continue
                if self.price_min is not None and p.price < self.price_min:
                    continue
                if self.price_max is not None and p.price > self.price_max:
                    continue
                if self.on_sale and not p.on_sale:
                    continue
                out.append((p.price, pid))
        out.sort()
        return [pid for _, pid in out]
