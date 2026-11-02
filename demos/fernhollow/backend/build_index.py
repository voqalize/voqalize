"""Offline: every index the brain reads, precomputed from the catalog.

    cd demos && uv run python fernhollow/backend/build_index.py \\
        --vectors ~/Desktop/voqalize/havenly-data/fernhollow-clip.json

Stdlib only. Writes ``backend/data/``:

``attributes.json``
    id → the material, colour, style and comfort words found in the product's
    own title, intro, highlights and option names (:mod:`words`), each with the
    phrase it came from. Alt text is not read.
``vocab.json``
    the words of each list that occur in the catalog, with counts, and every
    option value — the prompt names only these.
``search.json``
    word → product positions: title words, category words and attribute words.
``similar.json``
    id → the other products of its category, most alike first, as a flat
    ``[position, similarity 0..100, …]`` list (top 30; a position is the
    product's index in ``catalog.json``).
``pairs.json``
    for every category pair that a room recipe or a goes-with list puts side by
    side, the image similarity of each product pair, row-major over the
    catalog's own order within each category.
``goes_with.json``
    id → compatible category → the top five pieces (by position) to sit beside
    it, with a score and the reason code (a shared material, colour or style word, else ``look``).
``rooms.json``
    per room recipe and slot: the candidate ids, cheapest first, and the
    cheapest price.

The vectors come from :mod:`embed_images` (OpenCLIP, run once, not committed).
A similarity only ranks — two pieces that look alike sit together — and is
never said as a fact. Without ``--vectors`` the similarity falls back to shared
words, so the indexes can still be rebuilt on a machine without the images.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from . import words as w
    from .recipes import GOES_WITH, RECIPES
except ImportError:  # run as a script
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import words as w  # type: ignore[no-redef]
    from recipes import GOES_WITH, RECIPES  # type: ignore[no-redef]

HERE = Path(__file__).resolve().parent
CATALOG = HERE.parent / "data" / "catalog.json"
OUT = HERE / "data"
NEIGHBOURS = 30
GOES_WITH_TOP = 5

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_TOKEN = re.compile(r"[a-z]+")
_STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "the",
        "with",
        "in",
        "of",
        "for",
        "to",
        "on",
        "by",
        "from",
        "your",
        "our",
        "its",
        "at",
        "as",
        "or",
        "is",
        "it",
        "this",
        "that",
    ]
)


def _sources(p: dict[str, Any]) -> list[str]:
    """The product's own text, phrase by phrase: title, intro sentences,
    highlights, option names. Never alt text."""
    out = [p["title"]]
    out += [s for s in _SENTENCE.split(p["intro"]) if s.strip()]
    out += list(p["highlights"])
    out += [o["name"] for o in p["options"]]
    return out


# A word naming only the room around the product ("on tile or wood floors",
# "complements modern interiors", "pairs with rustic, modern, or eclectic
# décor") is not the product's own material or style: the noun it qualifies
# follows straight after it, or after a list of more such words.
_SETTING = (
    r"floors?|flooring|furniture|interiors?|surfaces?|d[e\u00e9]cor|cabinets?|spaces?"
    r"|settings?|surroundings|schemes?"
)
_BETWEEN = (
    r"or|and|both|any|tiled|tile|eclectic|scandinavian-inspired|bathroom|bedroom|kitchen"
    r"|living|dining|office|"
    + "|".join(sorted({*w.STYLES, *w.MATERIALS, *w.COLOURS}, key=len, reverse=True))
)
_AROUND = re.compile(rf"^(?:[\s,]+(?:{_BETWEEN})){{0,4}}[\s,]+(?:{_SETTING})(?![a-z])")
# …or something it is said to sit beside: "blends seamlessly with wood or concrete".
_BESIDE = re.compile(
    r"(?<![a-z])(?:blends?|pairs?|complements?|matches|harmoni[sz]es?|contrasts?|suits?|works?|goes)"
    rf"(?![a-z])[^.]{{0,40}}(?<![a-z])(?:with|alongside|against)(?:[\s,]+(?:{_BETWEEN}))*[\s,]+$"
)


def _about_surroundings(word: str, phrase: str, vocab: Mapping[str, str]) -> bool:
    """True when every mention of ``word`` in ``phrase`` names something around
    the product rather than the product."""
    text = w.normalise(phrase)
    forms = [f for f, canon in vocab.items() if canon == word]
    seen = False
    for form in forms:
        for m in re.finditer(rf"(?<![a-z]){re.escape(form)}(?![a-z])", text):
            seen = True
            if not (_AROUND.match(text[m.end() :]) or _BESIDE.search(text[: m.start()] + " ")):
                return False
    return seen


def _attributes(p: dict[str, Any]) -> dict[str, list[list[str]]]:
    lists = {
        "materials": w.MATERIALS,
        "colours": w.COLOURS,
        "styles": w.STYLES,
        "comfort": w.COMFORT,
    }
    out: dict[str, list[list[str]]] = {}
    for key, vocab in lists.items():
        found: dict[str, str] = {}
        for phrase in _sources(p):
            for word in w.find(phrase, vocab):
                if key != "comfort" and _about_surroundings(word, phrase, vocab):
                    continue
                found.setdefault(word, phrase.strip())
        if found:
            out[key] = [[word, phrase] for word, phrase in found.items()]
    return out


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def _word_sim(a: dict[str, Any], b: dict[str, Any]) -> float:
    def ws(x: dict[str, Any]) -> set[str]:
        return {word for k in ("materials", "colours", "styles") for word, _ in x.get(k, [])}

    sa, sb = ws(a), ws(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / math.sqrt(len(sa) * len(sb))


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("--vectors", type=Path, default=None)
    args = parser.parse_args()

    catalog = json.loads(CATALOG.read_text())
    products: list[dict[str, Any]] = catalog["products"]
    by_id = {p["id"]: p for p in products}
    by_cat: dict[str, list[str]] = {}
    for p in products:
        by_cat.setdefault(p["categorySlug"], []).append(p["id"])

    attrs = {p["id"]: _attributes(p) for p in products}
    # Product references in the larger files are positions in the catalog's own
    # order, which keeps them small; the brain decodes them at load.
    pos = {p["id"]: n for n, p in enumerate(products)}

    vectors: dict[str, list[float]] = {}
    if args.vectors is not None:
        vectors = json.loads(Path(args.vectors).expanduser().read_text())["vectors"]
        missing = [p["id"] for p in products if p["id"] not in vectors]
        if missing:
            raise SystemExit(f"no vector for {len(missing)} products, e.g. {missing[:3]}")

    def sim(a: str, b: str) -> int:
        if vectors:
            return max(0, round(_cos(vectors[a], vectors[b]) * 100))
        return round(_word_sim(attrs[a], attrs[b]) * 100)

    # ── vocab ────────────────────────────────────────────────────────────
    vocab: dict[str, Any] = {}
    for key in ("materials", "colours", "styles", "comfort"):
        c: Counter[str] = Counter(word for a in attrs.values() for word, _ in a.get(key, []))
        vocab[key] = [[word, n] for word, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))]
    values: Counter[str] = Counter(v for p in products for o in p["options"] for v in o["values"])
    vocab["similarity"] = "image" if vectors else "words"
    vocab["option_values"] = [
        [v, n] for v, n in sorted(values.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    # ── search ───────────────────────────────────────────────────────────
    index: dict[str, set[str]] = {}
    for p in products:
        tokens = set(_TOKEN.findall(w.normalise(p["title"] + " " + p["category"])))
        tokens |= {
            t
            for key in ("materials", "colours", "styles")
            for word, _ in attrs[p["id"]].get(key, [])
            for t in word.split()
        }
        for t in tokens - _STOP:
            if len(t) > 2:
                index.setdefault(t, set()).add(p["id"])
    search = {t: sorted(pos[i] for i in ids) for t, ids in sorted(index.items())}

    # ── similar ──────────────────────────────────────────────────────────
    similar: dict[str, list[int]] = {}
    for ids in by_cat.values():
        for a in ids:
            ranked = sorted(((b, sim(a, b)) for b in ids if b != a), key=lambda t: (-t[1], t[0]))
            similar[a] = [x for b, s in ranked[:NEIGHBOURS] for x in (pos[b], s)]

    # ── pairs ────────────────────────────────────────────────────────────
    wanted: set[tuple[str, str]] = set()
    for recipe in RECIPES.values():
        cats = [c for s in recipe.slots for c in s.categories]
        for i, a in enumerate(cats):
            for b in cats[i + 1 :]:
                if a != b:
                    wanted.add((min(a, b), max(a, b)))
    for a, others in GOES_WITH.items():
        for b in others:
            if a != b:
                wanted.add((min(a, b), max(a, b)))
    pairs: dict[str, list[list[int]]] = {}
    for a_cat, b_cat in sorted(wanted):
        pairs[f"{a_cat}|{b_cat}"] = [[sim(a, b) for b in by_cat[b_cat]] for a in by_cat[a_cat]]

    def pair_sim(a: str, b: str) -> int:
        ca, cb = by_id[a]["categorySlug"], by_id[b]["categorySlug"]
        if ca == cb:
            return sim(a, b)
        if (ca, cb) > (cb, ca):
            a, b, ca, cb = b, a, cb, ca
        return pairs[f"{ca}|{cb}"][by_cat[ca].index(a)][by_cat[cb].index(b)]

    # ── goes with ────────────────────────────────────────────────────────
    goes: dict[str, dict[str, list[list[Any]]]] = {}
    for p in products:
        pa = attrs[p["id"]]
        out: dict[str, list[list[Any]]] = {}
        for cat in GOES_WITH.get(p["categorySlug"], ()):
            if cat == p["categorySlug"]:
                continue
            scored: list[tuple[int, str, str]] = []
            for b in by_cat[cat]:
                pb = attrs[b]
                reason = "look"
                shared = 0
                for key, code in (
                    ("materials", "material"),
                    ("colours", "colour"),
                    ("styles", "style"),
                ):
                    common = [x for x, _ in pa.get(key, []) if x in {y for y, _ in pb.get(key, [])}]
                    if common:
                        shared += 1
                        if reason == "look":
                            reason = f"{code}:{common[0]}"
                score = round(0.6 * pair_sim(p["id"], b) + 20 * shared)
                scored.append((score, b, reason))
            scored.sort(key=lambda t: (-t[0], t[1]))
            out[cat] = [[pos[b], s, r] for s, b, r in scored[:GOES_WITH_TOP]]
        goes[p["id"]] = out

    # ── rooms ────────────────────────────────────────────────────────────
    rooms: dict[str, Any] = {}
    for room, recipe in RECIPES.items():
        slots: dict[str, Any] = {}
        for s in recipe.slots:
            ids = sorted(
                (i for c in s.categories for i in by_cat[c]),
                key=lambda i: (by_id[i]["priceMin"], i),
            )
            slots[s.name] = {"ids": [pos[i] for i in ids], "min": by_id[ids[0]]["priceMin"]}
        rooms[room] = slots

    OUT.mkdir(exist_ok=True)
    files = {
        "attributes.json": attrs,
        "vocab.json": vocab,
        "search.json": search,
        "similar.json": similar,
        "pairs.json": pairs,
        "goes_with.json": goes,
        "rooms.json": rooms,
    }
    for name, data in files.items():
        path = OUT / name
        path.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n")
        print(f"{name}: {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
