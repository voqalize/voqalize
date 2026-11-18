"""The gift edit and the showroom kiosk's three picks, ranked from the catalog.

Both are short lists for a handful of chosen answers, so every answer set is
ranked here once and written to ``backend/data/edits.json``: the brain says
what the page shows because both read the same list.

    cd demos && uv run python -m fernhollow.backend.edits   # or: python fernhollow/backend/edits.py

**Gifts** (``content/gift_guide.json``): who it is for, the occasion and a
budget chip. A category scores the recipient's and the occasion's weights for
it; a product scores that, how much of the budget it uses (closer to the budget
reads as more of a gift) and a sale. One pick per category first, so the list
is varied; the reason is the category's authored line plus the product's own
material and colour words.

**Kiosk** (``content/kiosk.json``): room, feel and spend per piece. A product of
the room scores the feel's words it carries (its own attribute words), a sale,
and how much of the spend it uses; one pick per category. A pick with none of
the feel's words is said as "within your spend" and nothing more.

No invented facts: titles, prices and words are the catalog's; a reason is an
authored line or a list of the product's own words.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from .catalog import CATALOG, DATA, DEMO, Product

__all__ = [
    "EDITS_PATH",
    "GIFTS",
    "KIOSK",
    "Pick",
    "budget_chip",
    "build",
    "gift_edit",
    "kiosk_picks",
]

GIFTS: dict[str, Any] = json.loads((DEMO / "content" / "gift_guide.json").read_text())
KIOSK: dict[str, Any] = json.loads((DEMO / "content" / "kiosk.json").read_text())
EDITS_PATH = DATA / "edits.json"


@dataclass(frozen=True)
class Pick:
    product_id: str
    variant_id: str
    reason: str

    def out(self) -> dict[str, str]:
        return {"product_id": self.product_id, "variant_id": self.variant_id, "reason": self.reason}


def _join(words: list[str]) -> str:
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def budget_chip(amount: float) -> int:
    """The largest budget chip at or under what was said, so a pick never goes
    over it ("under $90" is the $80 chip); the smallest chip below them all."""
    chips: list[int] = list(GIFTS["budgets"])
    under = [c for c in chips if c <= amount + 0.005]
    return max(under) if under else min(chips)


def _ids(kind: str) -> list[str]:
    return [str(x["id"]) for x in GIFTS[kind]]


def gift_edit(recipient: str, occasion: str, budget: float) -> list[Pick]:
    """The gift short list for one answer set (unknown ids weigh nothing)."""
    rec = next((r for r in GIFTS["recipients"] if r["id"] == recipient), {"weights": {}})
    occ = next((o for o in GIFTS["occasions"] if o["id"] == occasion), {"weights": {}})
    weights: dict[str, int] = {}
    for table in (occ["weights"], rec["weights"]):
        for cat, w in table.items():
            weights[cat] = weights.get(cat, 0) + int(w)
    scored: list[tuple[float, str]] = []
    for cat, w in weights.items():
        for pid in CATALOG.by_category.get(cat, []):
            p = CATALOG.products[pid]
            v = p.variant_for(None)
            if v.price > budget:
                continue
            score = w * 10 + (v.price / budget) * 3 + (1 if p.on_sale else 0)
            scored.append((score, pid))
    scored.sort(key=lambda t: (-t[0], t[1]))
    chosen = _spread([pid for _, pid in scored], int(GIFTS["picks"]))
    return [_gift_pick(CATALOG.products[pid]) for pid in chosen]


def _spread(ranked: list[str], n: int) -> list[str]:
    """The best ``n``, one per category first, then the next best of any."""
    out: list[str] = []
    cats: set[str] = set()
    for pid in ranked:
        cat = CATALOG.products[pid].category_slug
        if cat not in cats:
            out.append(pid)
            cats.add(cat)
        if len(out) == n:
            return out
    for pid in ranked:
        if pid not in out:
            out.append(pid)
        if len(out) == n:
            break
    return out


def _gift_pick(p: Product) -> Pick:
    angle = str(GIFTS["angles"].get(p.category_slug, "A good gift"))
    words = list(dict.fromkeys((*p.materials[:2], *p.colours[:2])))
    reason = f"{angle} — {_join(words)}." if words else f"{angle}."
    return Pick(p.id, p.variant_for(None).id, reason)


def _option(question: str, value: str) -> dict[str, Any] | None:
    q = next((q for q in KIOSK["questions"] if q["id"] == question), None)
    if q is None:
        return None
    return next((o for o in q["options"] if o["value"] == value), None)


def kiosk_picks(room: str, feel: str, budget: str) -> list[Pick]:
    """The kiosk's three picks for one answer set."""
    f = _option("feel", feel)
    b = _option("budget", budget)
    if f is None or b is None or room not in CATALOG.rooms:
        return []
    cap = b["max"]
    want = {*f["materials"], *f["colours"], *f["styles"]}
    in_room = [p for p in CATALOG.products.values() if p.room == room]
    top = cap if cap is not None else max(p.price for p in in_room)
    matched: list[tuple[float, str]] = []
    rest: list[tuple[float, str]] = []
    for p in in_room:
        v = p.variant_for(None)
        if cap is not None and v.price > cap:
            continue
        hits = len(want & set(p.words))
        use = v.price / top
        if hits:
            matched.append((hits * 10 + (2 if p.on_sale else 0) + use * 3, p.id))
        else:
            rest.append(((2 if p.on_sale else 0) + use * 3, p.id))
    matched.sort(key=lambda t: (-t[0], t[1]))
    rest.sort(key=lambda t: (-t[0], t[1]))
    n = int(KIOSK["picks"])
    chosen = _spread([pid for _, pid in matched], n)
    for pid in _spread([pid for _, pid in rest], n):
        if len(chosen) >= n:
            break
        if pid not in chosen:
            chosen.append(pid)
    return [_kiosk_pick(CATALOG.products[pid], want, str(f["line"])) for pid in chosen[:n]]


def _kiosk_pick(p: Product, want: set[str], line: str) -> Pick:
    words = [w for w in (*p.materials, *p.colours, *p.styles) if w in want][:2]
    if words:
        said = _join(words)
        reason = f"{said[0].upper()}{said[1:]}, for the {line} you asked for."
    else:
        reason = "Within your spend, for this room."
    return Pick(p.id, p.variant_for(None).id, reason)


def gift_key(recipient: str, occasion: str, budget: int) -> str:
    return f"{recipient}|{occasion}|{budget}"


def kiosk_key(room: str, feel: str, budget: str) -> str:
    return f"{room}|{feel}|{budget}"


def _kiosk_values(question: str) -> list[str]:
    q = next(q for q in KIOSK["questions"] if q["id"] == question)
    return [str(o["value"]) for o in q["options"]]


def build() -> dict[str, Any]:
    """Every answer set's list, as ``edits.json`` holds it."""
    gifts = {
        gift_key(r, o, b): [p.out() for p in gift_edit(r, o, b)]
        for r in _ids("recipients")
        for o in _ids("occasions")
        for b in GIFTS["budgets"]
    }
    kiosk = {
        kiosk_key(room, feel, budget): [p.out() for p in kiosk_picks(room, feel, budget)]
        for room in _kiosk_values("room")
        for feel in _kiosk_values("feel")
        for budget in _kiosk_values("budget")
    }
    return {
        "$comment": "Generated by backend/edits.py from content/gift_guide.json, content/kiosk.json and the catalog. Do not edit; rebuild.",
        "gifts": gifts,
        "kiosk": kiosk,
    }


def render() -> str:
    return json.dumps(build(), indent=1, ensure_ascii=False) + "\n"


@cache
def stored() -> dict[str, Any]:
    return json.loads(EDITS_PATH.read_text())


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else EDITS_PATH
    out.write_text(render())
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
