"""How a room is put together, and what goes with what — authored, not learned.

A recipe is the slots a designer fills for a room, each from one or more
catalog categories, with the share of the budget that slot usually takes. The
goes-with map says which categories sit beside an anchor piece. Both are
design rules, not product facts: they decide which products are *considered*;
what is said about a product still comes only from the catalog.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

__all__ = ["FINISHING", "GOES_WITH", "RECIPES", "Recipe", "Slot"]


@dataclass(frozen=True)
class Slot:
    name: str  # "desk", "chair" — what the room board calls the tile
    label: str  # how Emily says it
    categories: tuple[str, ...]
    share: float  # usual share of the room budget
    long_hours_share: float | None = None  # the share when they sit for long hours
    # A word the title must carry to fill this slot. The source catalog files a
    # few pieces oddly (a carafe under table lamps, a bath rug under rugs); a
    # room set only takes a piece whose own title says it is the thing.
    title_has: str = ""


@dataclass(frozen=True)
class Recipe:
    room: str
    label: str
    slots: tuple[Slot, ...]

    def slot(self, name: str) -> Slot | None:
        return next((s for s in self.slots if s.name == name), None)


RECIPES: Mapping[str, Recipe] = {
    "home-office": Recipe(
        "home-office",
        "home office",
        (
            Slot("desk", "desk", ("desks",), 0.32, 0.27, r"desk|workstation|bureau"),
            Slot("chair", "office chair", ("office-chairs",), 0.24, 0.36, r"chair"),
            Slot("lamp", "lamp", ("table-lamps", "floor-lamps"), 0.10, 0.08, r"lamp|light"),
            Slot("shelving", "shelving", ("shelving",), 0.20, 0.17, r"shel|book|rack|unit|storage"),
            Slot("rug", "rug", ("rugs",), 0.14, 0.12, r"^(?!.*\bbath\b).*\b(rug|runner)\b"),
        ),
    ),
    "living": Recipe(
        "living",
        "living room",
        (
            Slot("sofa", "sofa", ("sofas",), 0.42),
            Slot("coffee_table", "coffee table", ("coffee-tables",), 0.16),
            Slot("rug", "rug", ("rugs",), 0.14, title_has=r"^(?!.*\bbath\b).*\b(rug|runner)\b"),
            Slot("lamp", "floor lamp", ("floor-lamps",), 0.10, title_has=r"lamp|light"),
            Slot("tv_stand", "media unit", ("entertainment-centers-tv-stands",), 0.13),
            Slot("pillows", "throw pillow", ("throw-pillows",), 0.05),
        ),
    ),
    "dining": Recipe(
        "dining",
        "dining room",
        (
            Slot("table", "dining table", ("dining-tables",), 0.45),
            Slot("chairs", "dining chair", ("dining-chairs",), 0.22),
            Slot("light", "chandelier", ("chandeliers",), 0.18),
            Slot("rug", "rug", ("rugs",), 0.10, title_has=r"^(?!.*\bbath\b).*\b(rug|runner)\b"),
            Slot("serveware", "serveware", ("serveware",), 0.05),
        ),
    ),
    "bedroom": Recipe(
        "bedroom",
        "bedroom",
        (
            Slot("bed", "bed", ("beds-bed-frames",), 0.45),
            Slot("quilt", "quilt", ("quilts-comforters",), 0.12),
            Slot("sheets", "sheets", ("bed-sheets",), 0.08),
            Slot("lamp", "bedside lamp", ("table-lamps",), 0.10, title_has=r"lamp|light"),
            Slot("curtains", "curtains", ("curtains-drapes",), 0.10),
            Slot("rug", "rug", ("rugs",), 0.15, title_has=r"^(?!.*\bbath\b).*\b(rug|runner)\b"),
        ),
    ),
    "bath": Recipe(
        "bath",
        "bathroom",
        (
            Slot("mirror", "mirror", ("mirrors",), 0.40),
            Slot("mat", "bath mat", ("bath-mats-rugs",), 0.15),
            Slot("towels", "towels", ("bath-towels-washcloths",), 0.20),
            Slot("basket", "storage basket", ("household-storage-baskets",), 0.15),
            Slot("candle", "candle holder", ("candle-holders",), 0.10),
        ),
    ),
    "kitchen": Recipe(
        "kitchen",
        "kitchen",
        (
            Slot("cookware", "cookware", ("cookware",), 0.40),
            Slot("storage", "food storage", ("food-storage",), 0.20),
            Slot("dinnerware", "dinnerware", ("dinnerware",), 0.25),
            Slot("serveware", "serveware", ("serveware",), 0.15),
        ),
    ),
    "decor": Recipe(
        "decor",
        "decor",
        (
            Slot("art", "artwork", ("artwork",), 0.35),
            Slot("mirror", "mirror", ("mirrors",), 0.25),
            Slot("vase", "vase", ("vases",), 0.12),
            Slot("flora", "faux botanical", ("artificial-flora",), 0.10),
            Slot("candle", "candle holder", ("candle-holders",), 0.08),
            Slot("frame", "picture frame", ("picture-frames",), 0.10),
        ),
    ),
}

# The categories that are finishing touches: what suggest_finish offers at the cart.
FINISHING = (
    "artwork",
    "vases",
    "artificial-flora",
    "candle-holders",
    "picture-frames",
    "throw-pillows",
    "clocks",
    "household-storage-baskets",
)

_DECOR = ("artwork", "vases", "artificial-flora", "candle-holders", "picture-frames", "clocks")

# anchor category → the categories that sit beside it
GOES_WITH: Mapping[str, tuple[str, ...]] = {
    "desks": ("office-chairs", "table-lamps", "floor-lamps", "shelving", "rugs", *_DECOR),
    "office-chairs": ("desks", "rugs", "floor-lamps", "table-lamps", "throw-pillows"),
    "shelving": ("desks", "household-storage-baskets", "vases", "picture-frames", "clocks"),
    "sofas": (
        "coffee-tables",
        "throw-pillows",
        "rugs",
        "floor-lamps",
        "entertainment-centers-tv-stands",
        "artwork",
        "mirrors",
    ),
    "coffee-tables": ("sofas", "rugs", "vases", "candle-holders", "artificial-flora"),
    "entertainment-centers-tv-stands": ("sofas", "rugs", "floor-lamps", "vases", "clocks"),
    "rugs": ("sofas", "coffee-tables", "desks", "beds-bed-frames", "dining-tables"),
    "floor-lamps": ("sofas", "desks", "office-chairs", "rugs"),
    "table-lamps": ("desks", "beds-bed-frames", "quilts-comforters", "shelving"),
    "throw-pillows": ("sofas", "quilts-comforters", "rugs", "office-chairs"),
    "artwork": ("sofas", "desks", "beds-bed-frames", "dining-tables", "picture-frames", "mirrors"),
    "mirrors": ("sofas", "entertainment-centers-tv-stands", "candle-holders", "vases"),
    "clocks": ("desks", "shelving", "sofas", "dining-tables"),
    "dining-tables": ("dining-chairs", "chandeliers", "rugs", "serveware", "dinnerware", "vases"),
    "dining-chairs": ("dining-tables", "chandeliers", "rugs"),
    "chandeliers": ("dining-tables", "dining-chairs", "mirrors"),
    "dinnerware": ("serveware", "barware", "dining-tables", "candle-holders"),
    "serveware": ("dinnerware", "barware", "dining-tables"),
    "barware": ("serveware", "dinnerware", "candle-holders"),
    "beds-bed-frames": (
        "quilts-comforters",
        "bed-sheets",
        "table-lamps",
        "curtains-drapes",
        "rugs",
        "throw-pillows",
        "artwork",
    ),
    "quilts-comforters": ("beds-bed-frames", "bed-sheets", "throw-pillows", "curtains-drapes"),
    "bed-sheets": ("beds-bed-frames", "quilts-comforters", "throw-pillows"),
    "curtains-drapes": ("beds-bed-frames", "sofas", "rugs", "quilts-comforters"),
    "bath-mats-rugs": ("bath-towels-washcloths", "mirrors", "household-storage-baskets"),
    "bath-towels-washcloths": ("bath-mats-rugs", "household-storage-baskets", "candle-holders"),
    "household-storage-baskets": ("shelving", "bath-towels-washcloths", "throw-pillows"),
    "cookware": ("food-storage", "serveware", "dinnerware"),
    "food-storage": ("cookware", "household-storage-baskets", "serveware"),
    "vases": ("artificial-flora", "coffee-tables", "dining-tables", "shelving", "candle-holders"),
    "artificial-flora": ("vases", "coffee-tables", "dining-tables", "shelving"),
    "candle-holders": ("dining-tables", "coffee-tables", "vases", "mirrors"),
    "picture-frames": ("shelving", "desks", "artwork", "clocks"),
}
