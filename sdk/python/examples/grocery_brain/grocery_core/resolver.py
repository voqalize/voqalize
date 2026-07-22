"""Deterministic resolution: raw item text → ranked candidates → a decision.

Pure functions, no I/O — the ``service`` calls ``rank``/``decide`` after the
(background) MCP search. Kept deterministic so it's unit-testable and so the
"confirm or clarify" behaviour is predictable, not model-dependent.
"""

from __future__ import annotations

import re

from .models import Candidate, ItemState, Product

# Words to ignore when matching the spoken phrase to product names.
_STOP = {
    "of",
    "a",
    "an",
    "the",
    "some",
    "please",
    "get",
    "add",
    "need",
    "want",
    "buy",
    "for",
    "me",
    "my",
    "and",
    "to",
    "few",
    "couple",
    "bit",
    "little",
    "packet",
    "packets",
    "pack",
    "packs",
    "bottle",
    "bottles",
    "box",
    "boxes",
    "kg",
    "kgs",
    "g",
    "gram",
    "grams",
    "litre",
    "litres",
    "liter",
    "ltr",
    "ml",
    "dozen",
    "piece",
    "pieces",
    "pcs",
    "x",
}


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t and t not in _STOP]


def _score(item_tokens: list[str], product: Product) -> float:
    name = product.name.lower()
    brand = product.brand.lower()
    score = 0.0
    for t in item_tokens:
        if brand and t in brand:
            score += 3.0  # brand mention is a strong signal
        if t in name:
            score += 1.0
    if product.in_stock:
        score += 0.25
    return score


def rank(item_text: str, products: list[Product], limit: int = 3) -> list[Candidate]:
    """Top distinct product candidates, each with its sensible default variant."""
    toks = tokens(item_text)
    scored: list[tuple[float, Product]] = []
    for p in products:
        if p.default_variant is None:
            continue
        scored.append((_score(toks, p), p))
    # higher score first; cheaper default breaks ties (a friendly default)
    scored.sort(key=lambda sp: (-sp[0], sp[1].default_variant.offer_price))  # type: ignore[union-attr]
    out: list[Candidate] = []
    for s, p in scored[:limit]:
        v = p.default_variant
        assert v is not None
        out.append(Candidate(product=p, variant=v, score=s))
    return out


def decide(candidates: list[Candidate]) -> tuple[ItemState, Candidate | None, list[Candidate]]:
    """Auto-match when one option clearly dominates; else ask to clarify.

    Returns (state, chosen, shortlist).
    """
    if not candidates:
        return ItemState.UNAVAILABLE, None, []
    top = candidates[0]
    if len(candidates) == 1:
        return ItemState.MATCHED, top, candidates
    # Confident when the top clearly out-scores the runner-up (e.g. an explicit
    # brand mention), otherwise present the choice.
    if top.score >= candidates[1].score + 3.0:
        return ItemState.MATCHED, top, [top]
    return ItemState.NEEDS_CLARIFICATION, None, candidates


def pick(candidates: list[Candidate], choice: str | int) -> Candidate | None:
    """Resolve a clarification answer to a candidate.

    ``choice`` may be a 1-based index ("2"), or free text matching a brand or
    name fragment ("the Amul one", "multigrain").
    """
    if not candidates:
        return None
    if isinstance(choice, int):
        return candidates[choice - 1] if 1 <= choice <= len(candidates) else None
    raw = str(choice).strip().lower()
    if raw.isdigit():
        i = int(raw)
        if 1 <= i <= len(candidates):
            return candidates[i - 1]
    ordinals = {
        "first": 1,
        "second": 2,
        "third": 3,
        "1st": 1,
        "2nd": 2,
        "3rd": 3,
        "last": len(candidates),
    }
    if raw in ordinals:
        return candidates[ordinals[raw] - 1]
    # best token overlap against brand + name
    want = set(tokens(raw))
    best: tuple[float, Candidate] | None = None
    for c in candidates:
        hay = set(tokens(f"{c.product.brand} {c.product.name} {c.variant.qty_desc}"))
        overlap = len(want & hay)
        if overlap and (best is None or overlap > best[0]):
            best = (overlap, c)
    return best[1] if best else None
