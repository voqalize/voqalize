"""The fixed word lists — the only attribute vocabulary Emily has.

A product *has* a material, colour or style only when one of these words is in
its own title, intro, highlights or option names; the word is kept with the
phrase it came from (:mod:`build_index`). Nothing is inferred from a photo or
guessed from a category, and alt text is not read: it describes the
photograph, not the product.

Each list maps a surface form to its canonical word, so "wooden" and "wood",
"aluminium" and "aluminum", "bouclé" and "boucle" are one word. Families are the
shopper's broad words ("wood", "neutral", "light wood") and expand to the
canonical words they cover; a filter that expands one says so aloud (the
``assumption`` on ``apply_filters``).

Multi-word forms are matched before single words, longest first, so
"cast iron" is iron-the-material once, not "cast" and "iron".
"""

from __future__ import annotations

import re
from collections.abc import Mapping

__all__ = [
    "COLOURS",
    "COLOUR_FAMILIES",
    "COMFORT",
    "MATERIALS",
    "MATERIAL_FAMILIES",
    "STYLES",
    "STYLE_NEAREST",
    "find",
    "normalise",
]

# surface form → canonical word
MATERIALS: Mapping[str, str] = {
    "solid wood": "wood",
    "engineered wood": "engineered wood",
    "wooden": "wood",
    "wood": "wood",
    "oak": "oak",
    "walnut": "walnut",
    "ash": "ash",
    "birch": "birch",
    "teak": "teak",
    "mahogany": "mahogany",
    "maple": "maple",
    "pine": "pine",
    "eucalypt": "eucalyptus",
    "eucalyptus": "eucalyptus",
    "acacia": "acacia",
    "mango wood": "mango wood",
    "beech": "beech",
    "cherry": "cherry",
    "elm": "elm",
    "cedar": "cedar",
    "bamboo": "bamboo",
    "rattan": "rattan",
    "wicker": "wicker",
    "cane": "cane",
    "jute": "jute",
    "sisal": "sisal",
    "seagrass": "seagrass",
    "wool": "wool",
    "linen": "linen",
    "cotton": "cotton",
    "silk": "silk",
    "velvet": "velvet",
    "boucle": "boucle",
    "bouclé": "boucle",
    "leather": "leather",
    "suede": "suede",
    "mesh": "mesh",
    "canvas": "canvas",
    "cashmere": "cashmere",
    "microfiber": "microfiber",
    "microfibre": "microfiber",
    "polyester": "polyester",
    "chenille": "chenille",
    "faux fur": "faux fur",
    "sherpa": "sherpa",
    "metal": "metal",
    "steel": "steel",
    "stainless steel": "steel",
    "cast iron": "iron",
    "iron": "iron",
    "wrought iron": "iron",
    "brass": "brass",
    "aluminum": "aluminum",
    "aluminium": "aluminum",
    "copper": "copper",
    "chrome": "chrome",
    "bronze": "bronze",
    "nickel": "nickel",
    "pewter": "pewter",
    "marble": "marble",
    "travertine": "travertine",
    "granite": "granite",
    "slate": "slate",
    "concrete": "concrete",
    "glass": "glass",
    "glassware": "glass",
    "diatomite": "diatomite",
    "diatomaceous earth": "diatomite",
    "sateen": "sateen",
    "percale": "percale",
    "terry": "terry",
    "beeswax": "beeswax",
    "velour": "velour",
    "crystal": "crystal",
    "ceramic": "ceramic",
    "porcelain": "porcelain",
    "stoneware": "stoneware",
    "earthenware": "earthenware",
    "resin": "resin",
    "paper": "paper",
    "rice paper": "paper",
    "rope": "rope",
    "enamel": "enamel",
    "lacquer": "lacquer",
    "upholstered": "upholstered",
    "memory foam": "memory foam",
    "foam": "foam",
    "plywood": "plywood",
    "silicone": "silicone",
    "acrylic": "acrylic",
    "plastic": "plastic",
    "terrazzo": "terrazzo",
    "cork": "cork",
    "mirrored": "mirror glass",
}

COLOURS: Mapping[str, str] = {
    "white": "white",
    "ivory": "ivory",
    "cream": "cream",
    "off-white": "cream",
    "beige": "beige",
    "sand": "sand",
    "sandstone": "sand",
    "oatmeal": "oatmeal",
    "taupe": "taupe",
    "greige": "taupe",
    "grey": "grey",
    "gray": "grey",
    "stone": "stone",
    "charcoal": "charcoal",
    "graphite": "charcoal",
    "black": "black",
    "ebony": "black",
    "brown": "brown",
    "chestnut": "chestnut",
    "chocolate": "brown",
    "espresso": "brown",
    "caramel": "caramel",
    "camel": "camel",
    "tan": "tan",
    "cognac": "cognac",
    "honey": "honey",
    "terracotta": "terracotta",
    "rust": "rust",
    "clay": "clay",
    "red": "red",
    "burgundy": "burgundy",
    "pink": "pink",
    "blush": "blush",
    "rose": "rose",
    "coral": "coral",
    "orange": "orange",
    "yellow": "yellow",
    "mustard": "mustard",
    "ochre": "ochre",
    "gold": "gold",
    "golden": "gold",
    "champagne": "champagne",
    "silver": "silver",
    "green": "green",
    "sage": "sage",
    "olive": "olive",
    "emerald": "emerald",
    "moss": "moss",
    "blue": "blue",
    "navy": "navy",
    "indigo": "indigo",
    "teal": "teal",
    "purple": "purple",
    "plum": "plum",
    "lavender": "lavender",
    "neutral": "neutral",
}

STYLES: Mapping[str, str] = {
    "minimalist": "minimalist",
    "minimal": "minimalist",
    "modern": "modern",
    "organic": "organic",
    "classic": "classic",
    "contemporary": "contemporary",
    "sculptural": "sculptural",
    "rustic": "rustic",
    "luxury": "luxury",
    "luxurious": "luxury",
    "vintage": "vintage",
    "modular": "modular",
}

# A shopper's broad material word → the canonical words it covers.
MATERIAL_FAMILIES: Mapping[str, tuple[str, ...]] = {
    "wood": (
        "wood",
        "oak",
        "walnut",
        "ash",
        "birch",
        "teak",
        "mahogany",
        "maple",
        "pine",
        "eucalyptus",
        "acacia",
        "mango wood",
        "beech",
        "cherry",
        "elm",
        "cedar",
        "bamboo",
        "engineered wood",
        "plywood",
    ),
    "light wood": ("ash", "birch", "maple", "oak", "pine", "beech", "bamboo"),
    "dark wood": ("walnut", "mahogany", "teak", "cherry"),
    "metal": (
        "metal",
        "steel",
        "iron",
        "brass",
        "aluminum",
        "copper",
        "chrome",
        "bronze",
        "nickel",
        "pewter",
    ),
    "natural fibre": ("jute", "sisal", "seagrass", "rattan", "wicker", "cane"),
    "natural fiber": ("jute", "sisal", "seagrass", "rattan", "wicker", "cane"),
    "stone": ("marble", "travertine", "granite", "slate", "concrete", "terrazzo"),
    "fabric": (
        "linen",
        "cotton",
        "wool",
        "velvet",
        "boucle",
        "chenille",
        "upholstered",
        "polyester",
        "microfiber",
    ),
}

COLOUR_FAMILIES: Mapping[str, tuple[str, ...]] = {
    "neutral": (
        "neutral",
        "white",
        "ivory",
        "cream",
        "beige",
        "sand",
        "oatmeal",
        "taupe",
        "grey",
        "stone",
    ),
    "light": ("white", "ivory", "cream", "beige", "sand", "oatmeal"),
    "dark": ("black", "charcoal", "brown", "chestnut", "navy"),
    "warm": (
        "caramel",
        "camel",
        "tan",
        "cognac",
        "honey",
        "terracotta",
        "rust",
        "clay",
        "mustard",
        "ochre",
        "gold",
    ),
    "earthy": ("terracotta", "rust", "clay", "caramel", "olive", "moss", "sand", "ochre"),
    "green": ("green", "sage", "olive", "emerald", "moss"),
    "blue": ("blue", "navy", "indigo", "teal"),
    "brown": ("brown", "chestnut", "caramel", "camel", "tan", "cognac"),
    "grey": ("grey", "charcoal", "stone", "taupe"),
    "pink": ("pink", "blush", "rose", "coral"),
}

# A style word the catalog does not use → the nearest one it does, and why.
STYLE_NEAREST: Mapping[str, str] = {
    "scandinavian": "minimalist",
    "scandi": "minimalist",
    "japandi": "minimalist",
    "japanese": "minimalist",
    "clean": "minimalist",
    "simple": "minimalist",
    "mid-century": "vintage",
    "mid century": "vintage",
    "midcentury": "vintage",
    "retro": "vintage",
    "antique": "vintage",
    "traditional": "classic",
    "timeless": "classic",
    "elegant": "classic",
    "industrial": "modern",
    "sleek": "modern",
    "farmhouse": "rustic",
    "cottage": "rustic",
    "boho": "organic",
    "bohemian": "organic",
    "natural": "organic",
    "earthy": "organic",
    "glam": "luxury",
    "opulent": "luxury",
    "art deco": "luxury",
    "statement": "sculptural",
    "artistic": "sculptural",
    "flexible": "modular",
}

# Words in a product's own highlights that say it is built for long sitting.
COMFORT: Mapping[str, str] = {
    "ergonomic": "ergonomic",
    "lumbar": "lumbar support",
    "memory foam": "memory foam",
    "long hours": "long hours",
    "long work days": "long hours",
    "long workdays": "long hours",
    "all-day": "long hours",
    "all day": "long hours",
    "adjustable": "adjustable",
    "height-adjustable": "adjustable",
    "tilt": "adjustable",
    "breathable": "breathable",
    "cushioned": "cushioned",
    "padded": "cushioned",
    "posture": "posture support",
    "support": "support",
}


def normalise(text: str) -> str:
    """Lower case, curly quotes straightened, everything but letters, digits,
    hyphens and spaces turned to a space."""
    text = text.lower().replace("\u2019", "'")
    return re.sub(r"[^a-z0-9à-ÿ\- ]+", " ", text)


_PATTERNS: dict[int, list[tuple[re.Pattern[str], str, str]]] = {}


def _compiled(vocab: Mapping[str, str]) -> list[tuple[re.Pattern[str], str, str]]:
    key = id(vocab)
    if key not in _PATTERNS:
        forms = sorted(vocab, key=lambda f: (-len(f), f))
        _PATTERNS[key] = [
            (re.compile(rf"(?<![a-zà-ÿ]){re.escape(f)}(?![a-zà-ÿ])"), f, vocab[f]) for f in forms
        ]
    return _PATTERNS[key]


def find(text: str, vocab: Mapping[str, str]) -> list[str]:
    """The canonical words of ``vocab`` in ``text``, in first-seen order, each
    once. Longer forms win: a span matched by "cast iron" is not matched again."""
    s = normalise(text)
    taken = [False] * len(s)
    hits: list[tuple[int, str]] = []
    for pattern, _form, word in _compiled(vocab):
        for m in pattern.finditer(s):
            if any(taken[m.start() : m.end()]):
                continue
            for i in range(m.start(), m.end()):
                taken[i] = True
            hits.append((m.start(), word))
    out: list[str] = []
    for _, word in sorted(hits):
        if word not in out:
            out.append(word)
    return out
