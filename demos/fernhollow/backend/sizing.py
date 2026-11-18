"""The size guide's finder: the shopper's answers to a size and the guide's reason.

Everything comes from ``content/size_guide.json`` — the questions, which one is
asked when, and the rules that pick a size — so the /size-guide page and the
brain pick the same size for the same answers. A size is picked only where the
catalog sells sizes (beds and bedding: Queen or King; vases and faux stems:
Small or Large); rugs and curtains get the guide's placement advice and no size,
because Fernhollow sells them by fabric.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .catalog import CATALOG, DEMO, Product, Variant

__all__ = [
    "GUIDE",
    "Advice",
    "advice_for",
    "advise",
    "next_question",
    "prune",
    "question",
    "section",
    "size_of",
    "sized_products",
]

GUIDE: dict[str, Any] = json.loads((DEMO / "content" / "size_guide.json").read_text())
_FINDER: dict[str, Any] = GUIDE["finder"]


@dataclass(frozen=True)
class Advice:
    size: str | None
    why: str
    section: str


def question(qid: str) -> dict[str, Any] | None:
    return next((q for q in _FINDER["questions"] if q["id"] == qid), None)


def section(sid: str) -> dict[str, Any] | None:
    return next((s for s in GUIDE["sections"] if s["id"] == sid), None)


def _holds(when: dict[str, str], answers: dict[str, str]) -> bool:
    return all(answers.get(k) == v for k, v in when.items())


def valid(qid: str, value: str) -> bool:
    q = question(qid)
    return q is not None and any(o["value"] == value for o in q["options"])


def prune(answers: dict[str, str]) -> dict[str, str]:
    """The answers that still apply: one whose question's ``when`` no longer
    holds (mattress moved from none to king drops sleepers and room) goes,
    as it does on the page."""
    out = dict(answers)
    changed = True
    while changed:
        changed = False
        for qid in list(out):
            q = question(qid)
            if q is None or not _holds(q.get("when", {}), out):
                del out[qid]
                changed = True
    return out


def next_question(answers: dict[str, str]) -> dict[str, Any] | None:
    """The first question that applies to these answers and is not answered."""
    for q in _FINDER["questions"]:
        if q["id"] in answers:
            continue
        if _holds(q.get("when", {}), answers):
            return q
    return None


def advise(answers: dict[str, str]) -> Advice | None:
    """The guide's answer once there is one: a size and why for beds and vases;
    the chosen placement's advice for rugs and curtains."""
    kind = answers.get("kind")
    for rule in _FINDER["rules"]:
        if _holds(rule["if"], answers):
            return Advice(str(rule["size"]), str(rule["why"]), "beds" if kind == "bed" else "vases")
    if kind == "rug" and (layout := answers.get("layout")):
        s = section("rugs") or {}
        item = next((x for x in s.get("layouts", []) if x["id"] == layout), None)
        if item is not None:
            return Advice(None, f"{item['label']}: {item['text']}", "rugs")
    if kind == "curtains" and (drop := answers.get("drop")):
        s = section("curtains") or {}
        item = next((x for x in s.get("drops", []) if x["id"] == drop), None)
        if item is not None:
            return Advice(None, f"{item['label']}: {item['text']}", "curtains")
    return None


def size_of(p: Product) -> tuple[str, ...]:
    """The Size option's values a product carries, or none."""
    return p.option_values if p.option_name == "Size" else ()


def sized_products(section_id: str, size: str | None = None) -> list[tuple[Product, Variant]]:
    """The section's products, each with the variant of ``size`` when it sells
    it (else its first), cheapest first."""
    s = section(section_id)
    if s is None:
        return []
    out: list[tuple[Product, Variant]] = []
    for cat in s["categories"]:
        for pid in CATALOG.by_category.get(cat, []):
            p = CATALOG.products[pid]
            sizes = {x.lower() for x in size_of(p)}
            if section_id in ("beds", "vases") and not sizes:
                continue
            if size is not None and sizes and size.lower() not in sizes:
                continue
            out.append((p, p.variant_for(size)))
    out.sort(key=lambda t: (t[1].price, t[0].id))
    return out


def advice_for(p: Product) -> str | None:
    """Which finder question settles the size of this product, by its section."""
    for s in GUIDE["sections"]:
        if p.category_slug in s["categories"]:
            return str(s["id"])
    return None
