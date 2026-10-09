"""Qween's catalogue as the brain sees it: the feed, the index, and the URL grammar.

Three things live here, and each exists so the model never has to guess.

**The vocabulary.** Every category, metal, stone, shape, style and collection the
model may name is a ``Literal`` below, in the words a shopper uses, and each maps
to the label Qween's own feed prints. A name the model invents is a validation
error, not a filter that quietly matches nothing.

**The URL grammar.** Qween's listing is pure URL state: ``/catalog`` takes the
facet keys of the search index behind the grid. Which form each key takes was
read off the live site on 2026-09-29, one URL at a time, and is recorded in
``ecommerce-program/qween/research/site-actions.md``: most keys want the feed's
label in UPPER_SNAKE (``mtp=ROSE_BLOOM_GOLD``, ``stp=FW_PEARL``), but style and
collection want the label itself (``stl=Mini Solitaire``, ``dc=Qween's Armour``) —
UPPER_SNAKE there returns an empty grid. :func:`catalog_params` is the one place
that knows which.

**The index.** Qween publishes a product feed with one item per purchasable
variant (``/feed-products.xml``, offered in their ``llms.txt``). It is fetched,
parsed once and shared by every session. It is what the agent quotes a price
from, so it obeys the one rule prices have here: nothing older than
:data:`QUOTE_LIMIT_S` is ever quoted. A stale index is refreshed in the
background, and until it is back the agent reads the price off the page instead.
"""

from __future__ import annotations

import asyncio
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal, get_args

from loguru import logger

FEED_URL = "https://www.qween.com/feed-products.xml"

#: Refresh the index once it is this old. Their prices move with the gold rate.
REFRESH_AFTER_S = 6 * 3600
#: Never quote a price from an index older than this.
QUOTE_LIMIT_S = 24 * 3600

_G = "{http://base.google.com/ns/1.0}"


def _titled[N: str](names: tuple[N, ...], exceptions: dict[str, str]) -> dict[N, str]:
    """Each name title-cased, which is how the feed prints most of them, except
    where ``exceptions`` says otherwise."""
    return {n: exceptions.get(n, n.title()) for n in names}


# ─── The vocabulary ───────────────────────────────────────────────────────────

CategoryName = Literal[
    "rings",
    "earrings",
    "pendants",
    "nose pins",
    "necklaces",
    "chain with pendant",
    "bangles",
    "mangalsutra",
    "bracelets",
]
CATEGORIES: dict[CategoryName, str] = {
    "rings": "Rings",
    "earrings": "Earrings",
    "pendants": "Pendants",
    "nose pins": "Nose Pins",
    "necklaces": "Necklaces",
    "chain with pendant": "Chain with Pendant",
    "bangles": "Bangles",
    "mangalsutra": "Mangalsutra",
    "bracelets": "Bracelets",
}

KindName = Literal["studs", "drops", "hoops", "bands", "nose rings"]


@dataclass(frozen=True)
class Kind:
    category: CategoryName
    product_type: str
    """The feed's ``product_type``, e.g. ``Earrings > Hoops``."""
    word: str
    """What the site's text search is given for it: the grid has no facet for
    a sub-type, but its search matches names, and the names carry the word."""


KINDS: dict[KindName, Kind] = {
    "studs": Kind("earrings", "Earrings > Studs", "stud"),
    "drops": Kind("earrings", "Earrings > Drops", "drop"),
    "hoops": Kind("earrings", "Earrings > Hoops", "hoop"),
    "bands": Kind("rings", "Rings > Bands", "band"),
    "nose rings": Kind("nose pins", "Nose Pins > Nose Ring", "nose ring"),
}

MetalName = Literal[
    "desert noon",
    "snowfall white",
    "rose bloom",
    "champagne fizz",
    "clover green",
    "cloudy grey",
    "solid sunrise",
]
METALS: dict[MetalName, str] = {
    "desert noon": "Desert Noon Gold",
    "snowfall white": "Snowfall White Gold",
    "rose bloom": "Rose Bloom Gold",
    "champagne fizz": "Champagne Fizz Gold",
    "clover green": "Clover Green Gold",
    "cloudy grey": "Cloudy Grey Gold",
    "solid sunrise": "Solid Sunrise Gold",
}
#: What each of Qween's golds is in ordinary words, for the prompt and the tools.
METAL_PLAIN: dict[MetalName, str] = {
    "desert noon": "yellow gold",
    "snowfall white": "white gold",
    "rose bloom": "rose gold",
    "champagne fizz": "a pale champagne yellow",
    "clover green": "green gold",
    "cloudy grey": "grey gold",
    "solid sunrise": "pure 24 karat gold",
}

KaratName = Literal["9", "14", "18", "24"]
KARATS: dict[KaratName, str] = {k: f"{k} KT Gold" for k in get_args(KaratName)}

StoneName = Literal[
    "diamond",
    "solitaire",
    "pink sapphire",
    "blue sapphire",
    "yellow sapphire",
    "orange sapphire",
    "ruby",
    "ruby ombre",
    "emerald",
    "citrine",
    "pearl",
    "tourmaline",
    "opal",
    "garnet",
    "topaz",
    "peridot",
    "rhodolite",
    "aquamarine",
    "tanzanite",
    "amethyst",
    "onyx",
    "quartz",
    "mother of pearl",
    "tsavorite",
]
#: The feed's stone labels. Most are the name title-cased; the pearl is not.
STONES: dict[StoneName, str] = _titled(
    get_args(StoneName),
    {
        "pearl": "Fw Pearl",
        "mother of pearl": "Mother Of Pearl",
    },
)

ShapeName = Literal[
    "round",
    "oval",
    "pear",
    "princess",
    "marquise",
    "baguette",
    "emerald cut",
    "heart",
    "octagon",
    "cushion",
    "trillion",
]
SHAPES: dict[ShapeName, str] = _titled(
    get_args(ShapeName),
    {
        "emerald cut": "Emerald",
    },
)

StyleName = Literal[
    "studded",
    "classic",
    "plain",
    "geometric",
    "modern",
    "eternity",
    "floral",
    "mini solitaire",
    "crossover",
    "cluster",
    "vanki",
    "butterfly",
    "stackable",
    "three stone",
    "hearts",
    "star",
    "spiral",
    "infinity",
    "signet",
    "padlock",
    "detachable",
    "ombre",
    "multi sapphires",
    "affirmations",
]
STYLES: dict[StyleName, str] = _titled(
    get_args(StyleName),
    {
        "geometric": "Geometry",
    },
)

CollectionName = Literal[
    "classics",
    "stairway to power",
    "qween's armour",
    "wolf collection",
    "disco diva",
    "the one",
    "qween of eden",
    "the maharani",
    "paris at midnight",
    "wild rose",
]
COLLECTIONS: dict[CollectionName, str] = _titled(
    get_args(CollectionName),
    {
        "qween's armour": "Qween's Armour",
    },
)
#: The collections with an editorial page of their own (``/collection/<slug>``);
#: the rest are a filtered grid.
COLLECTION_PAGES: dict[CollectionName, str] = {
    "stairway to power": "stairway-to-power",
    "the one": "the-one",
    "wolf collection": "wolf-collection",
}

SortName = Literal["relevance", "price low to high", "price high to low"]
SORTS: dict[SortName, str | None] = {
    "relevance": None,
    "price low to high": "fpc:asc",
    "price high to low": "fpc:desc",
}


def upper_snake(label: str) -> str:
    """``Rose Bloom Gold`` → ``ROSE_BLOOM_GOLD``: the form most facet keys take."""
    return re.sub(r"[^A-Z0-9]+", "_", label.upper()).strip("_")


# ─── What a search asks for ───────────────────────────────────────────────────


@dataclass(frozen=True)
class Query:
    category: CategoryName | None = None
    kind: KindName | None = None
    metals: tuple[MetalName, ...] = ()
    stones: tuple[StoneName, ...] = ()
    shapes: tuple[ShapeName, ...] = ()
    styles: tuple[StyleName, ...] = ()
    collection: CollectionName | None = None
    price_min: int | None = None
    price_max: int | None = None
    sort: SortName = "relevance"


def catalog_params(q: Query) -> dict[str, list[str]]:
    """The ``/catalog`` query string for ``q``, as Qween's grid reads it.

    Repeated keys are OR within a facet, the way their own filter drawer builds
    them; different keys are AND."""
    params: dict[str, list[str]] = {}
    category = q.category or (KINDS[q.kind].category if q.kind else None)
    if category:
        params["cat"] = [CATEGORIES[category]]
    if q.kind:
        params["q"] = [KINDS[q.kind].word]
    if q.metals:
        params["mtp"] = [upper_snake(METALS[m]) for m in q.metals]
    if q.stones:
        params["stp"] = [upper_snake(STONES[s]) for s in q.stones]
    if q.shapes:
        params["ssp"] = [upper_snake(SHAPES[s]) for s in q.shapes]
    if q.styles:
        params["stl"] = [STYLES[s] for s in q.styles]
    if q.collection:
        params["dc"] = [COLLECTIONS[q.collection]]
    if q.price_min is not None or q.price_max is not None:
        low = q.price_min or 0
        params["fpc"] = [f"{low}-{q.price_max}" if q.price_max is not None else f"{low}-"]
    if sort := SORTS[q.sort]:
        params["sort"] = [sort]
    return params


# ─── The index ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Variant:
    """One purchasable variant: a metal colour at a purity, with its own price."""

    code: str
    metal: str
    """The feed's label, e.g. ``Rose Bloom Gold``."""
    karat: str
    """``18 KT Gold``."""
    price: int
    """Rupees, taxes included."""
    metal_weight: str = ""
    diamond_quality: str = ""
    solitaire_quality: str = ""
    solitaire_weight: str = ""


@dataclass(frozen=True)
class Piece:
    """One design, with every variant the feed lists for it."""

    group_id: str
    slug: str
    name: str
    description: str
    category: str
    product_type: str
    stones: tuple[str, ...]
    shapes: tuple[str, ...]
    styles: tuple[str, ...]
    collection: str
    variants: tuple[Variant, ...]

    @property
    def metals(self) -> list[str]:
        return list(dict.fromkeys(v.metal for v in self.variants))

    @property
    def karats(self) -> list[str]:
        return list(dict.fromkeys(v.karat for v in self.variants))

    def variant(self, code: str | None) -> Variant | None:
        return next((v for v in self.variants if v.code == code), None)

    def pick(self, metal: str | None = None, karat: str | None = None) -> Variant | None:
        """The variant with this metal and purity, or the nearest one that has
        whichever was named; the lowest-priced when several fit."""
        fits = [
            v
            for v in self.variants
            if (metal is None or v.metal == metal) and (karat is None or v.karat == karat)
        ]
        return min(fits, key=lambda v: v.price) if fits else None


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


#: The words in a piece's name that say only what kind of piece it is. What is
#: left is its family: Qween names a set's pieces alike — "Close Circle Ring",
#: "Close Circle Earrings" — and the feed has no other link between them.
_KIND_WORDS = frozenset(
    [
        "a",
        "the",
        "of",
        "and",
        "with",
        "diamond",
        "gold",
        "ring",
        "rings",
        "band",
        "bands",
        "earring",
        "earrings",
        "stud",
        "studs",
        "hoop",
        "hoops",
        "drop",
        "drops",
        "jhumka",
        "jhumkas",
        "pendant",
        "necklace",
        "chain",
        "bangle",
        "bracelet",
        "nose",
        "pin",
        "mangalsutra",
    ]
)
#: Collections too broad to make two pieces a pair: the house line holds most of
#: the catalogue, and a piece outside any collection has none to share.
_HOUSE_COLLECTIONS = frozenset({"", "Classics"})


def _family(name: str) -> str:
    return " ".join(w for w in re.findall(r"[a-z]+", name.lower()) if w not in _KIND_WORDS)


@dataclass
class Catalog:
    pieces: list[Piece]
    fetched_at: float
    by_slug: dict[str, Piece] = field(init=False)
    by_code: dict[str, tuple[Piece, Variant]] = field(init=False)
    by_family: dict[str, list[Piece]] = field(init=False)

    def __post_init__(self) -> None:
        self.by_slug = {p.slug: p for p in self.pieces}
        self.by_code = {v.code: (p, v) for p in self.pieces for v in p.variants}
        self.by_family = {}
        for p in self.pieces:
            if family := _family(p.name):
                self.by_family.setdefault(family, []).append(p)

    # ── Reading the feed ─────────────────────────────────────────────────

    @classmethod
    def parse(cls, xml: bytes, *, fetched_at: float | None = None) -> Catalog:
        root = ET.fromstring(xml)
        groups: dict[str, list[ET.Element]] = {}
        for item in root.iter("item"):
            groups.setdefault(item.findtext(f"{_G}item_group_id") or "", []).append(item)
        pieces = [p for items in groups.values() if (p := _piece(items)) is not None]
        return cls(pieces=pieces, fetched_at=time.time() if fetched_at is None else fetched_at)

    @property
    def age_s(self) -> float:
        return time.time() - self.fetched_at

    # ── Searching it ─────────────────────────────────────────────────────

    def search(self, q: Query) -> list[tuple[Piece, list[Variant]]]:
        """Every piece ``q`` matches, with the variants that match it.

        The same facets the grid applies, applied the same way: OR within a
        facet, AND across them. Metal and price are per variant, the rest per
        piece."""
        category = q.category or (KINDS[q.kind].category if q.kind else None)
        metals = {METALS[m] for m in q.metals}
        stones = {STONES[s] for s in q.stones}
        shapes = {SHAPES[s] for s in q.shapes}
        styles = {STYLES[s] for s in q.styles}
        found: list[tuple[Piece, list[Variant]]] = []
        for p in self.pieces:
            if category and p.category != CATEGORIES[category]:
                continue
            if q.kind:
                kind = KINDS[q.kind]
                if p.product_type != kind.product_type and kind.word not in p.name.lower():
                    continue
            if stones and not stones & set(p.stones):
                continue
            if shapes and not shapes & set(p.shapes):
                continue
            if styles and not styles & set(p.styles):
                continue
            if q.collection and p.collection != COLLECTIONS[q.collection]:
                continue
            variants = [
                v
                for v in p.variants
                if (not metals or v.metal in metals)
                and (q.price_min is None or v.price >= q.price_min)
                and (q.price_max is None or v.price <= q.price_max)
            ]
            if variants:
                found.append((p, variants))
        if q.sort == "price low to high":
            found.sort(key=lambda f: min(v.price for v in f[1]))
        elif q.sort == "price high to low":
            found.sort(key=lambda f: -max(v.price for v in f[1]))
        return found

    def pairs(self, piece: Piece, limit: int) -> list[tuple[Piece, str]]:
        """Pieces of another kind that go with ``piece``, each with why: its own
        set first — the same name made as another kind — then its collection,
        when it has one of its own, then its stone in the same cut and style.
        One of each kind, so earrings for a ring are not three pairs of
        earrings."""
        found: list[tuple[Piece, str]] = []
        kinds = {piece.category}

        def take(candidates: Iterable[Piece], why: str) -> None:
            for p in candidates:
                if p.category not in kinds and len(found) < limit:
                    kinds.add(p.category)
                    found.append((p, why))

        if family := _family(piece.name):
            take(self.by_family.get(family, []), "made as a set with it")
        if (collection := piece.collection) not in _HOUSE_COLLECTIONS:
            if "collection" not in collection.lower():
                collection += " collection"
            take(
                (p for p in self.pieces if p.collection == piece.collection),
                f"from the same {collection}",
            )
        # Otherwise, a stylist's match: its stone — the coloured one, when it
        # has one — in the same cut and style, nearest it in price.
        stones = set(piece.stones) - {"Diamond", "Solitaire"} or set(piece.stones)
        if stones and len(found) < limit:
            low = min(v.price for v in piece.variants)
            alike = [
                p
                for p in self.pieces
                if stones & set(p.stones)
                and set(piece.shapes) & set(p.shapes)
                and set(piece.styles) & set(p.styles)
            ]
            alike.sort(key=lambda p: abs(min(v.price for v in p.variants) - low))
            take(alike, "the same stone and cut")
        return found

    def named(self, text: str, among: Iterable[Piece] | None = None) -> Piece | None:
        """The piece whose name best matches ``text``: exact first, then the most
        words in common. ``None`` when nothing shares a word."""
        pool = list(among) if among is not None else self.pieces
        want = text.strip().lower()
        for p in pool:
            if p.name.lower() == want or p.slug == want:
                return p
        words = _words(want) - {"the", "a", "ring", "earrings", "pendant", "one"}
        best: tuple[float, Piece] | None = None
        for p in pool:
            have = _words(p.name)
            common = len(words & have)
            if not common:
                continue
            score = common / len(words | have)
            if best is None or score > best[0]:
                best = (score, p)
        return best[1] if best else None


def _detail(item: ET.Element) -> dict[str, str]:
    out: dict[str, str] = {}
    for d in item.findall(f"{_G}product_detail"):
        name = d.findtext(f"{_G}attribute_name")
        if name:
            out[name] = (d.findtext(f"{_G}attribute_value") or "").strip()
    return out


def _split(value: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in value.split(",") if x.strip())


def _price(text: str | None) -> int | None:
    m = re.match(r"\s*([\d.]+)", text or "")
    return round(float(m.group(1))) if m else None


def _piece(items: Sequence[ET.Element]) -> Piece | None:
    first = items[0]
    link = first.findtext("link") or ""
    slug = m.group(1) if (m := re.search(r"/product/([^/?#]+)", link)) else ""
    product_type = (first.findtext(f"{_G}product_type") or "").strip()
    if not slug or not product_type:
        return None
    variants: list[Variant] = []
    stones: dict[str, None] = {}
    shapes: dict[str, None] = {}
    styles: dict[str, None] = {}
    collection = ""
    for item in items:
        d = _detail(item)
        price = _price(item.findtext(f"{_G}price"))
        code = item.findtext(f"{_G}id") or ""
        if price is None or not code:
            continue
        variants.append(
            Variant(
                code=code,
                metal=d.get("Metal Colour") or item.findtext(f"{_G}color") or "",
                karat=d.get("Metal Purity", ""),
                price=price,
                metal_weight=d.get("Metal Weight", ""),
                diamond_quality=d.get("Diamond Quality", ""),
                solitaire_quality=d.get("Solitaire Quality", ""),
                solitaire_weight=d.get("Solitaire Weight", ""),
            )
        )
        stones.update(dict.fromkeys(_split(d.get("Stone Type", ""))))
        shapes.update(dict.fromkeys(_split(d.get("Stone Shape", ""))))
        styles.update(dict.fromkeys(_split(d.get("Style", ""))))
        collection = collection or d.get("Collection", "")
    if not variants:
        return None
    return Piece(
        group_id=first.findtext(f"{_G}item_group_id") or "",
        slug=slug,
        name=(first.findtext("title") or "").strip(),
        description=(first.findtext("description") or "").strip(),
        category=product_type.split(" > ")[0],
        product_type=product_type,
        stones=tuple(stones),
        shapes=tuple(shapes),
        styles=tuple(styles),
        collection=collection,
        variants=tuple(variants),
    )


# ─── Keeping it fresh ─────────────────────────────────────────────────────────


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Voqalize-QweenDemo/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


async def _fetch_feed() -> Catalog:
    started = time.monotonic()
    xml = await asyncio.to_thread(_download, FEED_URL)
    catalog = await asyncio.to_thread(Catalog.parse, xml)
    logger.info(
        "qween: feed indexed — {} pieces in {:.1f}s",
        len(catalog.pieces),
        time.monotonic() - started,
    )
    return catalog


class FeedCache:
    """The one index every session shares, refreshed in the background.

    A session never waits on the network for longer than it asks to: the index is
    warmed when a call starts, and a tool that finds it still loading says so
    rather than holding the turn."""

    def __init__(self, fetch: Callable[[], Awaitable[Catalog]] = _fetch_feed) -> None:
        self._fetch = fetch
        self._catalog: Catalog | None = None
        self._loading: asyncio.Task[None] | None = None

    def prime(self, catalog: Catalog) -> None:
        """Install an index directly — a test's fixture, with no network."""
        self._catalog = catalog

    def warm(self) -> None:
        """Start a refresh if the index is missing or old and none is running."""
        if self._catalog is not None and self._catalog.age_s < REFRESH_AFTER_S:
            return
        if self._loading is not None and not self._loading.done():
            return
        self._loading = asyncio.get_running_loop().create_task(self._refresh())

    async def _refresh(self) -> None:
        try:
            self._catalog = await self._fetch()
        except Exception as exc:  # a failed refresh keeps the old index
            logger.warning("qween: feed refresh failed: {}", exc)

    def current(self) -> Catalog | None:
        """The index, if it is young enough to quote a price from."""
        c = self._catalog
        return c if c is not None and c.age_s < QUOTE_LIMIT_S else None

    async def ready(self, timeout_s: float) -> Catalog | None:
        """The index, waiting at most ``timeout_s`` for a load under way."""
        if (c := self.current()) is not None:
            return c
        self.warm()
        if self._loading is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._loading), timeout_s)
            except TimeoutError:
                return None
        return self.current()


#: Shared by every session in the process.
FEED = FeedCache()


def rupees(amount: int) -> str:
    """₹ in the Indian grouping a shopper reads: 1,84,500."""
    s = str(amount)
    if len(s) <= 3:
        return f"₹{s}"
    head, tail = s[:-3], s[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return "₹" + ",".join(groups) + "," + tail


def price_span(variants: Sequence[Variant]) -> str:
    low, high = min(v.price for v in variants), max(v.price for v in variants)
    return rupees(low) if low == high else f"{rupees(low)} to {rupees(high)}"
