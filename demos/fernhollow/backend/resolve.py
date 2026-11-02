"""Which product the shopper means — resolved, or honestly ambiguous.

A spoken reference ("the second one", "the left one", "the walnut one", "the
moduler oak sofa with deep seat") is matched against, in order of how likely
the shopper means it:

1. the product being pointed at (hover, focus or tap, at most 5 s old) — for
   "this", "that", "it";
2. the choices on screen, when Emily has just asked "which one?";
3. the products visible on screen, with their layout (rows and columns), so
   positions resolve;
4. the shortlist and the room board;
5. the whole catalog.

A name is matched by a fuzzy score robust to transcription noise: word overlap
where each spoken word may match a title word by character trigrams (so
"moduler" still finds "modular") or by a phonetic key (so "bowclay" finds
"boucle"), plus the trigram similarity of the whole phrase, plus option values
("in walnut") and attribute words. A pool with one clearly best candidate
answers; a pool whose top two to four are close answers *ambiguous*, with the
difference that tells them apart, and the brain asks one short question. It
never guesses between close candidates, and never asks when one is clearly
meant. The thresholds are pinned by tests on real catalog cases.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import cache
from typing import Literal

from . import words as w
from .catalog import CATALOG, Product, money

__all__ = [
    "CLEAR_MARGIN",
    "MIN_SCORE",
    "Layout",
    "Resolution",
    "resolve",
    "score",
]

#: A candidate must score at least this to be meant at all (0..1).
MIN_SCORE = 0.45
#: The best must beat the runner-up by this much to be clearly meant; within it
#: the two are close, and Emily asks.
CLEAR_MARGIN = 0.08
#: How old a pointing may be and still be "this one".
POINTING_S = 5.0

_STOP = frozenset(
    [
        "the",
        "a",
        "an",
        "one",
        "this",
        "that",
        "it",
        "with",
        "and",
        "in",
        "of",
        "for",
        "to",
        "on",
        "my",
        "me",
        "i",
        "want",
        "show",
        "like",
        "please",
        "see",
        "look",
        "at",
        "those",
        "these",
        "them",
        "there",
        "here",
        "which",
    ]
)
_DEICTIC = re.compile(
    r"^\s*(this|that|it|this one|that one|the one i'?m (on|pointing at)|here)\s*[.!?]?\s*$"
)
_ORDINAL = {
    "first": 1,
    "1st": 1,
    "one": 1,
    "second": 2,
    "2nd": 2,
    "two": 2,
    "third": 3,
    "3rd": 3,
    "three": 3,
    "fourth": 4,
    "4th": 4,
    "four": 4,
    "fifth": 5,
    "five": 5,
    "sixth": 6,
    "six": 6,
}


@dataclass(frozen=True)
class Layout:
    """Where a product sits on screen: row and column, from 0 at the top left."""

    product_id: str
    row: int
    col: int


@dataclass(frozen=True)
class Resolution:
    kind: Literal["one", "choose", "none"]
    product_id: str | None = None
    candidates: tuple[str, ...] = ()
    question: str = ""
    source: str = ""
    scores: tuple[tuple[str, float], ...] = field(default=(), compare=False)


# ─── Matching ─────────────────────────────────────────────────────────────────


def _stem(t: str) -> str:
    """seats, seating → seat: a listener hears the word, not its ending."""
    for suffix in ("ing", "es", "s"):
        if t.endswith(suffix) and len(t) - len(suffix) >= 3 and not t.endswith("ss"):
            return t[: -len(suffix)]
    return t


def _tokens(text: str) -> list[str]:
    return [_stem(t) for t in re.findall(r"[a-z0-9à-ÿ]+", w.normalise(text)) if t not in _STOP]


@cache
def _grams(text: str) -> frozenset[str]:
    s = f"  {text} "
    return frozenset(s[i : i + 3] for i in range(len(s) - 2))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


@cache
def _phonetic(word: str) -> str:
    """A small phonetic key: vowels after the first letter dropped, look-alike
    consonants folded, doubled letters merged — enough for "boucle"/"bookle",
    "settee"/"setty", "loveseat"/"love seat"."""
    word = word.replace("ph", "f").replace("ck", "k").replace("qu", "k").replace("x", "ks")
    out = word[:1]
    fold = str.maketrans("cgjkqszdtbpv", "kkkkksstttpp")
    for ch in word[1:].translate(fold):
        if ch in "aeiouyhw":
            continue
        if not out.endswith(ch):
            out += ch
    return out


@cache
def _product_text(pid: str) -> tuple[tuple[str, ...], frozenset[str], frozenset[str]]:
    p = CATALOG.products[pid]
    title = _tokens(p.title)
    extra = [t for v in p.option_values for t in _tokens(v)] + [
        t for x in (*p.materials, *p.colours, *p.styles) for t in _tokens(x)
    ]
    return tuple(title), frozenset(extra), _grams(" ".join(title))


def _word_match(spoken: str, words: Sequence[str]) -> float:
    best = 0.0
    g = _grams(spoken)
    key = _phonetic(spoken)
    for t in words:
        if t == spoken:
            return 1.0
        sim = _jaccard(g, _grams(t))
        if len(spoken) > 3 and len(t) > 3 and _phonetic(t) == key:
            sim = max(sim, 0.85)
        best = max(best, sim)
    return best if best >= 0.5 else 0.0


def score(spoken: str, pid: str) -> float:
    """How well ``spoken`` names product ``pid``, 0..1."""
    toks = _tokens(spoken)
    if not toks:
        return 0.0
    title, extra, title_grams = _product_text(pid)
    per = [max(_word_match(t, title), 0.8 * _word_match(t, list(extra))) for t in toks]
    coverage = sum(per) / len(per)
    # how much of the title the shopper said: a short name still matches a long title
    said = sum(1 for t in title if any(_word_match(s, [t]) >= 0.5 for s in toks))
    title_cover = said / len(title) if title else 0.0
    phrase = _jaccard(_grams(" ".join(toks)), title_grams)
    return round(0.55 * coverage + 0.25 * phrase + 0.20 * title_cover, 4)


# ─── Positions ────────────────────────────────────────────────────────────────


def _position(
    spoken: str, ordered: Sequence[str], layout: Sequence[Layout]
) -> str | None | Literal[False]:
    """A product named by its place on screen; ``False`` when the words name a
    place but nothing is there; ``None`` when they name no place."""
    s = w.normalise(spoken)
    m = re.search(
        r"\b(first|second|third|fourth|fifth|sixth|1st|2nd|3rd|4th|[1-6])\b"
        r"|\b(?:number|option|choice|no)\s+(one|two|three|four|five|six)\b"
        r"|^\s*(?:the\s+)?(one|two|three|four|five|six)\s*[.!?]?\s*$",
        s,
    )
    only_number = (
        re.fullmatch(r"\s*(?:the\s+)?(?:number\s+)?\S+(?:\s+one)?\s*[.!?]?\s*", s) is not None
    )
    if "last" in s.split() and ordered and ("one" in s or len(_tokens(s)) <= 1):
        return ordered[-1]
    rows = sorted({x.row for x in layout})
    cols = sorted({x.col for x in layout})
    if layout and re.search(r"\b(left|right|middle|centre|center|top|bottom)\b", s):
        pick = list(layout)
        if "top" in s and rows:
            pick = [x for x in pick if x.row == rows[0]]
        if "bottom" in s and rows:
            pick = [x for x in pick if x.row == rows[-1]]
        row_cols = sorted({x.col for x in pick}) or cols
        if "left" in s and row_cols:
            pick = [x for x in pick if x.col == row_cols[0]]
        elif "right" in s and row_cols:
            pick = [x for x in pick if x.col == row_cols[-1]]
        elif re.search(r"\b(middle|centre|center)\b", s) and len(row_cols) >= 3:
            pick = [x for x in pick if x.col == row_cols[len(row_cols) // 2]]
        if len(pick) == 1:
            return pick[0].product_id
        if m is not None and pick:
            n = _number(m)
            ordered_pick = [x.product_id for x in sorted(pick, key=lambda x: (x.row, x.col))]
            return ordered_pick[n - 1] if 1 <= n <= len(ordered_pick) else False
        return None
    if m is not None and (only_number or re.search(r"\b(one|option|choice)\b", s)):
        n = _number(m)
        return ordered[n - 1] if 1 <= n <= len(ordered) else False
    return None


def _number(m: re.Match[str]) -> int:
    token = next(g for g in m.groups() if g)
    return _ORDINAL.get(token) or int(token)


# ─── The difference that tells candidates apart ───────────────────────────────


def _where(pid: str, layout: Sequence[Layout]) -> str:
    spot = next((x for x in layout if x.product_id == pid), None)
    if spot is None or not layout:
        return ""
    rows = sorted({x.row for x in layout})
    cols = sorted({x.col for x in layout if x.row == spot.row})
    parts: list[str] = []
    if len(rows) > 1:
        parts.append("top" if spot.row == rows[0] else "bottom" if spot.row == rows[-1] else "")
    if len(cols) > 1:
        parts.append(
            "left" if spot.col == cols[0] else "right" if spot.col == cols[-1] else "middle"
        )
    where = " ".join(p for p in parts if p)
    if where == "middle":
        return "in the middle"
    return f"on the {where}" if where else ""


def _distinct(p: Product, others: Sequence[Product]) -> str:
    """A word of this product's own title no other candidate's title has."""
    theirs = {t for o in others for t in _tokens(o.title)}
    for t in _tokens(p.title):
        if t not in theirs and len(t) > 2:
            return t
    return ""


def question(candidates: Sequence[str], layout: Sequence[Layout]) -> str:
    """One short question naming the difference: "Which one: one, the … on
    the left, or two, the … at $2,950?" """
    products = [CATALOG.products[i] for i in candidates]
    parts: list[str] = []
    numbers = ("one", "two", "three", "four")
    prices = {p.price for p in products}
    for n, p in enumerate(products):
        others = [o for o in products if o.id != p.id]
        word = _distinct(p, others)
        bits = [f"the {word} one" if word else "the one"]
        where = _where(p.id, layout)
        if where:
            bits.append(where)
        if not word and len(prices) == len(products):
            bits.append(f"at {money(p.price)}")
        parts.append(f"{numbers[n]}, {' '.join(bits)}")
    joined = ", ".join(parts[:-1]) + f", or {parts[-1]}" if len(parts) > 1 else parts[0]
    return f"Which one: {joined}?"


# ─── Resolution ───────────────────────────────────────────────────────────────


@cache
def _vocab() -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, set[str]]]:
    """word → products whose title or attributes carry it; trigram → words;
    phonetic key → words. Built once, so a catalog-wide match scores only the
    products that share a word, a near-spelling or a sound with what was said."""
    by_word: dict[str, set[str]] = {}
    for pid in CATALOG.products:
        title, extra, _ = _product_text(pid)
        for t in (*title, *extra):
            by_word.setdefault(t, set()).add(pid)
    by_gram: dict[str, set[str]] = {}
    by_key: dict[str, set[str]] = {}
    for t in by_word:
        for g in _grams(t):
            by_gram.setdefault(g, set()).add(t)
        by_key.setdefault(_phonetic(t), set()).add(t)
    return by_word, by_gram, by_key


def _catalog_pool(spoken: str, limit: int = 60) -> list[str]:
    by_word, by_gram, by_key = _vocab()
    hits: dict[str, int] = {}
    for tok in _tokens(spoken):
        near = set(by_key.get(_phonetic(tok), ())) if len(tok) > 3 else set()
        g = _grams(tok)
        counts: dict[str, int] = {}
        for gram in g:
            for word in by_gram.get(gram, ()):
                counts[word] = counts.get(word, 0) + 1
        near |= {word for word, n in counts.items() if n >= max(2, len(g) // 2)}
        for word in near:
            for pid in by_word[word]:
                hits[pid] = hits.get(pid, 0) + 1
    ranked = sorted(hits, key=lambda pid: (-hits[pid], pid))
    return ranked[:limit]


def _rank(spoken: str, pool: Sequence[str]) -> list[tuple[str, float]]:
    ranked = [(pid, score(spoken, pid)) for pid in dict.fromkeys(pool) if pid in CATALOG.products]
    ranked.sort(key=lambda t: (-t[1], t[0]))
    return ranked


def _decide(
    spoken: str, pool: Sequence[str], source: str, layout: Sequence[Layout]
) -> Resolution | None:
    ranked = _rank(spoken, pool)
    if not ranked or ranked[0][1] < MIN_SCORE:
        return None
    top = ranked[0][1]
    close = [(pid, s) for pid, s in ranked if top - s < CLEAR_MARGIN and s >= MIN_SCORE]
    if len(close) == 1:
        return Resolution("one", ranked[0][0], source=source, scores=tuple(ranked[:4]))
    cands = tuple(pid for pid, _ in close[:4])
    return Resolution(
        "choose",
        candidates=cands,
        question=question(cands, layout),
        source=source,
        scores=tuple(ranked[:4]),
    )


#: A name that matches something elsewhere in the catalog this much better than
#: anything on screen means that other thing, not a near-miss on screen.
ELSEWHERE_MARGIN = 0.15


def _catalog(spoken: str) -> Resolution:
    r = _decide(spoken, _catalog_pool(spoken), "catalog", ())
    if r is None:
        return Resolution("none", source="catalog")
    if r.kind == "choose" and not _alike(spoken, r.candidates):
        # Close matches from different kinds of thing are not a choice between
        # look-alikes: the shopper has not said enough to offer any.
        return Resolution("none", source="catalog", scores=r.scores)
    return r


def _alike(spoken: str, candidates: Sequence[str]) -> bool:
    """Close catalog matches are a real choice when they are one kind of thing,
    or when the shopper said two or more words and every candidate carries
    them all ("walnut lamp"); "the walnut one" across a carafe, a lamp and a
    mirror is not."""
    if len({CATALOG.products[i].category_slug for i in candidates}) == 1:
        return True
    said = set(_tokens(spoken))
    return len(said) >= 2 and all(said <= set(_product_text(i)[0]) for i in candidates)


def _best(r: Resolution) -> float:
    return r.scores[0][1] if r.scores else 0.0


def resolve(
    spoken: str,
    *,
    pointing: str | None = None,
    pointing_age_s: float | None = None,
    choices: Sequence[str] = (),
    visible: Sequence[str] = (),
    layout: Sequence[Layout] = (),
    saved: Sequence[str] = (),
    open_product: str | None = None,
    scope: Literal["auto", "screen", "catalog"] = "auto",
) -> Resolution:
    """The product ``spoken`` names, or the candidates to ask between."""
    fresh = (
        pointing
        if pointing and pointing_age_s is not None and pointing_age_s <= POINTING_S
        else None
    )
    if _DEICTIC.match(w.normalise(spoken)):
        pid = fresh or open_product or (visible[0] if len(visible) == 1 else None)
        if pid:
            return Resolution("one", pid, source="pointing" if pid == fresh else "screen")
        return Resolution("none", source="pointing")
    if choices:
        where = _position(spoken, choices, [x for x in layout if x.product_id in choices])
        if isinstance(where, str):
            return Resolution("one", where, source="choices")
        if (r := _decide(spoken, choices, "choices", layout)) is not None:
            return r
    near: Resolution | None = None
    if visible and scope != "catalog":
        ordered = [x.product_id for x in sorted(layout, key=lambda x: (x.row, x.col))] or list(
            visible
        )
        where = _position(spoken, ordered, layout)
        if isinstance(where, str):
            return Resolution("one", where, source="screen")
        if where is False:
            return Resolution("none", source="screen")
        near = _decide(spoken, visible, "screen", layout)
    if near is None and fresh and score(spoken, fresh) >= MIN_SCORE:
        return Resolution("one", fresh, source="pointing")
    if near is None and saved and scope != "catalog":
        near = _decide(spoken, saved, "saved", ())
    if scope == "screen":
        return near or Resolution("none", source="screen")
    if near is not None and _best(near) >= 0.95:
        return near
    far = _catalog(spoken)
    if near is None:
        return far
    # Something on screen half-matches; the catalog may hold what was really said.
    if far.kind != "none" and _best(far) - _best(near) >= ELSEWHERE_MARGIN:
        return far
    return near


# Built at import, like every other index, so the first reference of a call is
# as fast as the hundredth.
_vocab()
