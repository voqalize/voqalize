"""What Javier knows about Cannon Home, in three layers, read once at import.

- **L1** (``knowledge/L1.md``) is always in his prompt: who Cannon Home is, its
  categories, despacho, retiro, cambios and medios de pago in brief, the size
  words (1 plaza … super king), thread counts and towel weights.
- **L2** (``knowledge/L2/<topic>.md``) is a topic he reads with ``read_topic``
  when a question needs more than L1. Each file opens with ``# Title`` and a
  ``Sources:`` line.
- **L3** (``knowledge/L3/*.json``) is the data:

  - ``pages.json`` — the site's CMS and category pages, their sections and
    FAQs, which ``search_site`` searches and every cue is checked against.
  - ``site.json`` — redirects, the nav tree and layout probes.
  - ``products.json`` — the catalogue, one object a line: name, path, size,
    colour, material, thread count, towel weight, attributes and the ``family``
    a line's sizes and colours share. **No price and no stock, ever**: those
    are read live in the visitor's browser and reach the brain as app events.
  - ``categories.json`` — the categories, and the filter options each lists,
    so a filter he asks the listing for is one the site has.

The files are built offline (``knowledge/build.py``) and committed. Every one of
them may be missing or empty and this module still imports: the demos backend
serves every brain from one process, and one brain that cannot import takes the
others down with it.

The site is in Spanish and the visitor may ask in English, so every comparison
here folds case and accents, and the catalogue reads a visitor's words — "dos
plazas", "matrimonial", "white", "egyptian cotton" — as the site's own labels.
:meth:`Knowledge.find_products` runs while the visitor waits, inside the tool
budget, so everything it compares is folded and indexed once, at load.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from loguru import logger

ROOT = Path(__file__).parent / "knowledge"

#: The store. The canonical host is the bare domain: www redirects to it.
SITE_HOST = "cannonhome.cl"
SITE_HOSTS = frozenset({SITE_HOST, f"www.{SITE_HOST}"})
SITE = f"https://{SITE_HOST}"

_L1_FALLBACK = (
    "Cannon Home's online store is cannonhome.cl: sheets, towels, duvets, pillows, beds and "
    "home textiles, priced in Chilean pesos. Nothing more is loaded: answer only from what "
    "you read with your tools and what their screen reports."
)


# ─── Text ──────────────────────────────────────────────────────────────────────

_TOKEN = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)?")
_STOP = frozenset(
    # English and Spanish words every passage has.
    """a an and are as at be by can do does for from has have how i in is it its me my of on
    or the to what which with you your el la los las un una unos unas de del y o en por para
    con que se su sus es al lo como mas tu te mi""".split()  # noqa: SIM905
)
_QUOTES = str.maketrans(
    {chr(0x2018): "'", chr(0x2019): "'", chr(0x201C): '"', chr(0x201D): '"'}
    | {chr(0x2013): "-", chr(0x2014): "-"}
)


def fold(text: str) -> str:
    """Lower case, without accents: "Sábanas Plumón" → "sabanas plumon"."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    """Folded words and numbers, without the words every passage has."""
    return [t for t in _TOKEN.findall(fold(text)) if t not in _STOP]


def norm(text: str) -> str:
    """Case, accents, whitespace, curly quotes and dashes folded."""
    return " ".join(fold(text.translate(_QUOTES)).split())


def canonical_path(path_or_url: str) -> str:
    """``https://www.cannonhome.cl/Sabanas-King.html?a=1#b`` → ``/sabanas-king.html``."""
    raw = path_or_url.strip()
    parts = urlsplit(raw if "://" in raw else f"https://x{'' if raw.startswith('/') else '/'}{raw}")
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/").lower()
    return path or "/"


def on_site(url: str) -> bool:
    """Whether ``url`` is on the store (either host), or a bare path."""
    if "://" not in url:
        return True
    return (urlsplit(url).hostname or "").lower() in SITE_HOSTS


#: Words a visitor says, and the words the site writes for them.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "sheets": ("sabanas",),
    "sheet": ("sabanas",),
    "sabana": ("sabanas",),
    "towel": ("toalla",),
    "towels": ("toalla",),
    "toallas": ("toalla",),
    "duvet": ("plumon",),
    "comforter": ("plumon",),
    "plumones": ("plumon",),
    "pillow": ("almohada",),
    "pillows": ("almohada",),
    "almohadas": ("almohada",),
    "blanket": ("frazada",),
    "throw": ("manta",),
    "bedspread": ("cubrecama",),
    "quilt": ("quilt", "cubrecama"),
    "mattress": ("colchon",),
    "bed": ("cama",),
    "cotton": ("algodon",),
    "shipping": ("despacho",),
    "delivery": ("despacho",),
    "envio": ("despacho",),
    "returns": ("cambios", "devoluciones"),
    "return": ("cambios", "devoluciones"),
    "exchange": ("cambios",),
    "stores": ("tiendas",),
    "store": ("tiendas",),
    "pickup": ("retiro",),
    "payment": ("pago",),
    "installments": ("cuotas",),
}


def _expand(words: list[str]) -> list[str]:
    out = list(words)
    for w in words:
        out.extend(_SYNONYMS.get(w, ()))
    return list(dict.fromkeys(out))


def _matches(want: str, have: set[str] | frozenset[str]) -> float:
    """1 for the word itself, 0.7 for a word it starts (sabana → sabanas), else 0."""
    if want in have:
        return 1.0
    if len(want) >= 4 and any(
        h.startswith(want) or (len(h) >= 4 and want.startswith(h)) for h in have
    ):
        return 0.7
    return 0.0


# ─── What a visitor says, as the site labels it ────────────────────────────────

#: The bed sizes, as the site's ``Tamaño`` filter labels them, by key.
SIZE_LABELS: dict[str, str] = {
    "1": "1 Plaza",
    "1.5": "1.5 Plazas",
    "2": "2 Plazas",
    "king": "King",
    "super king": "Súper King",
}
#: How a visitor says a bed size, folded, longest first where one contains
#: another ("super king" before "king", "1,5 plazas" before "1 plaza"). Chile
#: sells by "plazas"; "matrimonial" and "queen" are the 2 plazas bed there.
_SIZE_WORDS: tuple[tuple[str, str], ...] = (
    (r"s[uú]per ?king|super-king|california king", "super king"),
    (r"king|\bkingsize\b", "king"),
    (
        r"(?:1|un[oa]?)\s*(?:[.,]\s*5|y medi[oa])\s*plazas?|plaza y media|1[.,]5\b"
        r"|full(?: size)?\b|double bed",
        "1.5",
    ),
    (r"(?:2|dos)\s*plazas?|matrimonial|queen", "2"),
    (r"(?:1|un[oa]?)\s*plazas?|individual|single|twin", "1"),
)
_SIZE_RX = tuple((re.compile(rf"\b(?:{rx})", re.IGNORECASE), key) for rx, key in _SIZE_WORDS)

#: Colour words: the stem both languages and both genders share, from the
#: visitor's word. "blancas", "white" and "Blanco" are one colour.
_COLOR_WORDS: dict[str, str] = {
    "white": "blanc",
    "black": "negr",
    "grey": "gris",
    "gray": "gris",
    "blue": "azul",
    "navy": "azul",
    "brown": "cafe",
    "green": "verd",
    "red": "roj",
    "pink": "rosad",
    "rosa": "rosad",
    "purple": "morad",
    "lilac": "lila",
    "yellow": "amarill",
    "orange": "naranj",
    "cream": "crud",
    "ivory": "marfil",
    "beige": "beig",
    "taupe": "taupe",
    "sand": "arena",
    "silver": "plat",
    "gold": "dorad",
    "turquoise": "turquesa",
    "aqua": "aqua",
    "coral": "coral",
    "mint": "menta",
}
#: The site's colour words, as stems: what a visitor's word is checked against.
_COLOR_STEMS = frozenset(
    """blanc negr gris azul cafe verd roj rosad morad lila amarill naranj crud marfil beig taupe
    arena plat dorad turquesa aqua coral menta celest burdeo terracota mostaz fucsia grafit
    perla humo hues chocolat camel salmon oliv musgo petroleo calipso""".split()  # noqa: SIM905
)


def color_stem(word: str) -> str | None:
    """A colour word's stem ("Blancas" → "blanc", "white" → "blanc"), or ``None``."""
    w = fold(word).strip()
    if not w:
        return None
    if w in _COLOR_WORDS:
        return _COLOR_WORDS[w]
    for cut in ("es", "s"):
        if w.endswith(cut) and len(w) > 4:
            w = w[: -len(cut)]
            break
    if w in _COLOR_STEMS:
        return w
    if w.endswith(("a", "o")) and w[:-1] in _COLOR_STEMS:
        return w[:-1]
    return next((s for s in _COLOR_STEMS if len(w) >= 4 and w.startswith(s)), None)


#: Materials: what a visitor says → the folded word the site writes.
_MATERIALS: tuple[tuple[str, str], ...] = (
    (r"poly ?cotton|polialgodon|algodon[- ]poliester", "polycotton"),
    (r"(?:100 ?% ?)?algod[oó]n|cotton|egyptian|egipcio|percal|percale|satin|saten", "algodon"),
    (r"poli[eé]ster|polyester", "poliester"),
    (r"microfibra|microfiber|microfibre", "microfibra"),
    (r"tencel|lyocell", "tencel"),
    (r"\blino\b|linen", "lino"),
    (r"bamb[uú]|bamboo", "bambu"),
    (r"plumas?\b|feathers?|down\b|plumon de ganso|ganso|goose", "pluma"),
    (r"\blana\b|wool", "lana"),
    (r"viscoel[aá]stic\w*|memory foam", "viscoelastic"),
    (r"sherpa", "sherpa"),
    (r"polar\b|fleece", "polar"),
    (r"flannel|franela", "franela"),
)
_MATERIAL_RX = tuple((re.compile(rf"\b(?:{rx})", re.IGNORECASE), key) for rx, key in _MATERIALS)

#: Product types: what a visitor says → the folded phrase the site's type,
#: category or name carries, and the words that make it another product
#: ("plumón" is not a "funda plumón"). Longest phrase first.
_TYPES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (r"fundas? (?:de )?plum[oó]n|duvet covers?", "funda plumon", ()),
    (r"fundas? (?:de )?almohadas?|pillow ?cases?|pillowcases?", "funda", ("plumon",)),
    (r"s[aá]banas? bajeras?|fitted sheets?|bajeras?", "bajera", ()),
    (r"s[aá]banas? (?:de )?ba[nñ]o|bath sheets?", "sabana de bano", ()),
    (r"toallas? (?:de )?playa|beach towels?|poncho", "playa", ()),
    (r"cubre ?colch[oó]n(?:es)?|mattress (?:protector|pad|cover)s?", "cubrecolchon", ()),
    (r"pisos? (?:de )?ba[nñ]o|bath ?mats?", "piso", ()),
    (r"batas?|bath ?robes?|robes?", "bata", ()),
    (r"toppers?", "topper", ()),
    (r"s[aá]banas?|sheets?|sheet sets?|juego de s[aá]banas", "sabana", ("bano", "funda", "bajera")),
    (r"toallas?|towels?", "toalla", ("playa",)),
    (r"plum[oó]n(?:es)?|duvets?|comforters?|edred[oó]n(?:es)?", "plumon", ("funda",)),
    (r"almohadas?|pillows?", "almohada", ("funda",)),
    (r"cubrecamas?|bedspreads?|quilts?|cobertor(?:es)?", "cubrecama", ()),
    (r"frazadas?|blankets?", "frazada", ()),
    (r"mantas?|pieceras?|throws?", "manta", ()),
    (r"cojin(?:es)?|coj[ií]n|cushions?", "cojin", ("funda",)),
    (r"colch[oó]n(?:es)?|mattress(?:es)?", "colchon", ("cubre",)),
    (r"camas? europeas?|box ?springs?|beds?\b|camas?\b", "cama", ("sofa", "base", "respaldo")),
    (r"alfombras?|rugs?", "alfombra", ()),
)
_TYPE_RX = tuple(
    (re.compile(rf"\b(?:{rx})\b", re.IGNORECASE), key, without) for rx, key, without in _TYPES
)
_THREADS = re.compile(r"\b(\d{3,4})\s*(?:hilos?|threads?|thread count|tc)\b", re.IGNORECASE)
_GSM = re.compile(r"\b(\d{3,4})\s*(?:g(?:r|rs)?(?:/m2|/m²|m2)?|gramos|gsm)\b", re.IGNORECASE)
_DIMENSIONS = re.compile(r"\b(\d{2,3})\s*x\s*(\d{2,3})\b", re.IGNORECASE)


def size_key(text: str | None) -> str | None:
    """The bed size ``text`` names, as a key of :data:`SIZE_LABELS`; a pillow's
    or towel's measures as ``"50x70"``; else ``None``."""
    if not text:
        return None
    said = fold(text).replace("½", ".5")
    for rx, key in _SIZE_RX:
        if rx.search(said):
            return key
    if (m := _DIMENSIONS.search(said)) is not None:
        return f"{m.group(1)}x{m.group(2)}"
    return None


def material_key(text: str | None) -> str | None:
    if not text:
        return None
    said = fold(text)
    return next((key for rx, key in _MATERIAL_RX if rx.search(said)), None)


def type_key(text: str | None) -> tuple[str, tuple[str, ...]] | None:
    """The product type ``text`` names: the site's folded phrase and the words
    that make a product another type."""
    if not text:
        return None
    said = fold(text)
    for rx, key, without in _TYPE_RX:
        if rx.search(said):
            return key, without
    return None


def _strip(rx: re.Pattern[str], text: str) -> str:
    return " ".join(rx.sub(" ", text).split())


def visitor_wishes(text: str) -> dict[str, Any]:
    """The size, colour, material, type, thread count and weight in what a
    visitor said, and the words left over. "Sábanas king blancas de 300 hilos"
    → type sabana, size king, color blanc, threads 300, nothing left."""
    said = fold(text).replace("½", ".5")
    out: dict[str, Any] = {}
    if (m := _THREADS.search(said)) is not None:
        out["threads"] = int(m.group(1))
        said = said[: m.start()] + " " + said[m.end() :]
    if (m := _GSM.search(said)) is not None:
        out["weight"] = int(m.group(1))
        said = said[: m.start()] + " " + said[m.end() :]
    for rx, key in _SIZE_RX:
        if rx.search(said):
            out["size"] = key
            said = _strip(rx, said)
            break
    else:
        if (m := _DIMENSIONS.search(said)) is not None:
            out["size"] = f"{m.group(1)}x{m.group(2)}"
            said = said[: m.start()] + " " + said[m.end() :]
    for rx, key, _ in _TYPE_RX:
        if rx.search(said):
            out["type"] = key
            said = _strip(rx, said)
            break
    for rx, key in _MATERIAL_RX:
        if rx.search(said):
            out["material"] = key
            said = _strip(rx, said)
            break
    rest: list[str] = []
    for w in tokens(said):
        if "color" not in out and (stem := color_stem(w)) is not None:
            out["color"] = stem
            continue
        if w in _FILLER:
            continue
        rest.append(w)
    out["words"] = rest
    return out


#: Words a visitor wraps a wish in, which name no product.
_FILLER = frozenset(
    """quiero busco buscando necesito tienes tienen hay algo alguna alguno algunas algunos
    unas unos uno dos plaza plazas cama camas color colores de en para mi tu muy bien que
    looking want need show me some any something please do have color colour size sizes
    tamano tamanos medida hilos hilo threads thread count g gr gramos lo la los las
    esta este estas estos la le les ver mostrar muestrame""".split()  # noqa: SIM905
)


# ─── The layers ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Topic:
    id: str
    title: str
    text: str


@dataclass(frozen=True)
class Faq:
    q: str
    a: str


@dataclass(frozen=True)
class Section:
    heading: str
    text: str = ""
    level: int = 0
    selector: str = ""
    items: tuple[str, ...] = ()
    """The block's other headings (cards, sub-sections): scroll targets too."""


@dataclass(frozen=True)
class Page:
    path: str
    title: str
    description: str = ""
    sections: tuple[Section, ...] = ()
    faqs: tuple[Faq, ...] = ()
    text: str = ""
    kind: str = ""
    """The crawl's page type: ``cms``, ``category``, ``home`` …"""
    unlisted: bool = False

    @property
    def headings(self) -> tuple[str, ...]:
        return tuple(s.heading for s in self.sections if s.heading)


@dataclass(frozen=True)
class Product:
    """One product of the catalogue: one size and one colour of a line. No
    price and no stock: those are only ever read live, on their screen."""

    sku: str
    name: str
    path: str
    brand: str = ""
    category: str = ""
    """The breadcrumb, e.g. ``Ropa de cama > Sábanas``."""
    categories: tuple[str, ...] = ()
    type: str = ""
    size: str | None = None
    color: str = ""
    material: str = ""
    threads: int | None = None
    weight_gsm: int | None = None
    attributes: tuple[tuple[str, str], ...] = ()
    summary: str = ""
    image: str = ""
    family: str = ""
    """What the line's other sizes and colours share (the SKU stem)."""

    def facts(self) -> str:
        """Its attributes, compactly, as the catalogue has them."""
        bits = [
            self.type,
            f"tamaño {self.size}" if self.size else "",
            f"color {self.color}" if self.color else "",
            self.material,
            f"{self.threads} hilos" if self.threads else "",
            f"{self.weight_gsm} g/m²" if self.weight_gsm else "",
            self.brand,
        ]
        return ", ".join(b for b in bits if b)


@dataclass(frozen=True)
class Category:
    path: str
    name: str
    parent: str = ""
    filters: tuple[str, ...] = ()
    """The listing's filter groups, by request var: ``tamano``, ``color``, ``hilos`` …"""
    options: tuple[tuple[str, tuple[str, ...]], ...] = ()
    """Each filter group's option labels, as the listing writes them."""

    def labels(self, var: str) -> tuple[str, ...]:
        return next((labels for v, labels in self.options if v == var), ())


@dataclass(frozen=True)
class Hit:
    """One search result: a page section or an FAQ."""

    kind: str
    title: str
    snippet: str
    score: float
    path: str | None = None
    section: str | None = None


@dataclass(frozen=True)
class Found:
    """What :meth:`Knowledge.find_products` found: the matches, the wishes it
    had to drop to find any, and the ones it could not read."""

    products: tuple[Product, ...]
    total: int = 0
    dropped: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()


@dataclass
class _Passage:
    hit: Hit
    text: str
    tf: Counter[str]
    length: int


class _Index:
    """BM25 over passages; the phrase itself, when a passage has it, counts for
    half as much again."""

    def __init__(self) -> None:
        self.passages: list[_Passage] = []
        self.df: Counter[str] = Counter()
        self.avg = 1.0

    def add(self, hit: Hit, text: str, weight: int = 1) -> None:
        toks = tokens(text)
        if not toks:
            return
        tf = Counter(toks)
        if weight > 1:
            tf = Counter({k: v * weight for k, v in tf.items()})
        self.df.update(tf.keys())
        self.passages.append(_Passage(hit, " ".join(text.split()), tf, len(toks)))

    def done(self) -> None:
        if self.passages:
            self.avg = sum(p.length for p in self.passages) / len(self.passages) or 1.0

    def search(self, query: str, limit: int) -> list[Hit]:
        q = _expand(tokens(query))
        if not q:
            return []
        n = len(self.passages)
        phrase = norm(query)
        k1, b = 1.4, 0.75
        best: dict[tuple[str, str | None, str | None, str], Hit] = {}
        for p in self.passages:
            s = 0.0
            for w in q:
                if (tf := p.tf.get(w, 0)) > 0:
                    idf = math.log(1 + (n - self.df[w] + 0.5) / (self.df[w] + 0.5))
                    s += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * p.length / self.avg))
            if s <= 0:
                continue
            low = norm(p.text)
            if phrase in low:
                s *= 1.5
                at = low.find(phrase)
            else:
                at = min((i for w in q if (i := low.find(w)) >= 0), default=0)
            snippet = p.text[max(0, at - 80) : at + 240]
            h = p.hit
            key = (h.kind, h.path, h.section, h.title)
            hit = Hit(h.kind, h.title, snippet, round(s, 2), h.path, h.section)
            if key not in best or best[key].score < hit.score:
                best[key] = hit
        return sorted(best.values(), key=lambda h: -h.score)[:limit]


@dataclass(frozen=True)
class _Row:
    """A product, folded once for the filter that runs while the visitor waits."""

    product: Product
    words: frozenset[str]
    """Every folded word of its name, type, category, colour, material, attributes."""
    name_words: frozenset[str]
    kind: str
    """Its type, name and last category, folded: what a type wish is checked against."""
    size: str | None
    colors: frozenset[str]
    material: str
    category_paths: frozenset[str]
    category_text: str


def _row(p: Product) -> _Row:
    attrs = " ".join(f"{k} {v}" for k, v in p.attributes)
    every = f"{p.name} {p.type} {p.category} {p.color} {p.material} {p.brand} {attrs}"
    leaf = p.category.split(">")[-1] if p.category else ""
    colors = {s for w in tokens(p.color) if (s := color_stem(w)) is not None}
    material = " ".join(
        dict.fromkeys(
            [fold(p.material), *(k for t in (p.material, p.name) if (k := material_key(t)))]
        )
    )
    return _Row(
        product=p,
        words=frozenset(tokens(every)),
        name_words=frozenset(tokens(p.name)),
        kind=norm(p.type) if p.type else norm(f"{p.name} {leaf}"),
        size=size_key(p.size) or size_key(p.name),
        colors=frozenset(colors),
        material=material,
        category_paths=frozenset(canonical_path(c) for c in p.categories),
        category_text=norm(p.category),
    )


@dataclass
class Knowledge:
    l1: str
    topics: dict[str, Topic]
    pages: dict[str, Page]
    redirects: dict[str, str] = field(default_factory=dict[str, str])
    products: dict[str, Product] = field(default_factory=dict[str, Product])
    """The catalogue, by canonical path (``/x.html``)."""
    categories: dict[str, Category] = field(default_factory=dict[str, Category])
    """The categories, by canonical path."""
    _site: _Index = field(default_factory=_Index, repr=False)
    _rows: list[_Row] = field(default_factory=list[_Row], repr=False)
    _families: dict[str, list[Product]] = field(
        default_factory=dict[str, list[Product]], repr=False
    )
    _by_sku: dict[str, Product] = field(default_factory=dict[str, Product], repr=False)
    _lines: dict[str, list[Product]] = field(default_factory=dict[str, list[Product]], repr=False)

    def __post_init__(self) -> None:
        # Indexed once, here: a search and a catalogue filter run while the
        # visitor waits.
        for p in self.pages.values():
            self._site.add(Hit("page", p.title, "", 0, path=p.path), f"{p.title}\n{p.description}")
            for s in p.sections:
                self._site.add(
                    Hit("page", p.title, "", 0, path=p.path, section=s.heading or None),
                    f"{s.heading}\n{' '.join(s.items)}\n{s.text}",
                )
            if not p.sections and p.text:
                self._site.add(Hit("page", p.title, "", 0, path=p.path), p.text)
            for faq in p.faqs:
                self._site.add(Hit("faq", faq.q, "", 0, path=p.path), f"{faq.q}\n{faq.a}")
        self._site.done()
        for product in self.products.values():
            self._rows.append(_row(product))
            self._by_sku[product.sku.upper()] = product
            key = product.family or _family_of(product)
            self._families.setdefault(key, []).append(product)
            self._lines.setdefault(_line_of(product), []).append(product)

    # ── Lookups ──

    def page(self, path_or_url: str) -> Page | None:
        """A site page, following the site's redirects."""
        path = canonical_path(path_or_url)
        path = self.redirects.get(path, path)
        return self.pages.get(path)

    def product(self, path_or_sku: str) -> Product | None:
        """A product by its path (or url), or its SKU."""
        raw = path_or_sku.strip()
        if not raw:
            return None
        if (by_sku := self._by_sku.get(raw.upper())) is not None:
            return by_sku
        path = canonical_path(raw)
        if not path.endswith(".html"):
            path += ".html"
        found = self.products.get(path)
        if found is None and path.count("/") > 1:
            # The sitemap's category-path duplicates (/plaza/<key>.html): the
            # canonical is always the flat one.
            found = self.products.get("/" + path.rsplit("/", 1)[-1])
        return found

    def category(self, path_or_url: str) -> Category | None:
        path = canonical_path(path_or_url)
        return self.categories.get(self.redirects.get(path, path))

    def search(self, query: str, limit: int = 6) -> list[Hit]:
        """The site's pages, sections and FAQs."""
        return self._site.search(query, limit)

    def siblings(self, product: Product) -> list[Product]:
        """The line's other sizes and colours, as separate products: its
        ``family`` (the SKU stem, which the store shares across sizes) and the
        products named like it but for the size and the colour."""
        family = self._families.get(product.family or _family_of(product), [])
        line = self._lines.get(_line_of(product), [])
        seen = {product.path}
        out: list[Product] = []
        for p in (*family, *line):
            if p.path not in seen:
                seen.add(p.path)
                out.append(p)
        return out

    def near_products(self, name: str, limit: int = 3) -> list[Product]:
        """The products whose name is closest to ``name``, loosely spelled."""
        want = norm(name)
        if not want or not self.products:
            return []
        scored = sorted(
            self.products.values(),
            key=lambda p: SequenceMatcher(None, want, norm(p.name)).ratio(),
            reverse=True,
        )
        return scored[:limit]

    def find_products(
        self,
        *,
        query: str | None = None,
        category: str | None = None,
        type: str | None = None,
        size: str | None = None,
        color: str | None = None,
        material: str | None = None,
        threads_min: int | None = None,
        threads_max: int | None = None,
        weight_min: int | None = None,
        weight_max: int | None = None,
        family_of: Product | None = None,
        limit: int = 8,
    ) -> Found:
        """The products that fit, best first. A visitor's own words are read as
        the site's labels ("dos plazas" is 2 Plazas, "white" is Blanco); a wish
        nothing fits is dropped, softest first, and named in ``dropped``.

        With ``family_of``, only that product's line: its other sizes and
        colours (the product page has no size picker; a size is another product)."""
        wishes = visitor_wishes(query or "")
        unknown: list[str] = []
        size_want = size_key(size) if size else wishes.get("size")
        if size and size_want is None:
            unknown.append(f"size '{size}'")
        color_want = None
        if color:
            color_want = next((s for w in tokens(color) if (s := color_stem(w))), None)
            if color_want is None:
                unknown.append(f"color '{color}'")
        else:
            color_want = wishes.get("color")
        material_want = material_key(material) or (fold(material) if material else None)
        material_want = material_want or wishes.get("material")
        kind = type_key(type) if type else None
        if type and kind is None:
            kind = (fold(type), ())
        if kind is None and (t := wishes.get("type")) is not None:
            kind = next(((k, w) for _, k, w in _TYPE_RX if k == t), None)
        if threads_min is None and threads_max is None and (n := wishes.get("threads")):
            threads_min = threads_max = int(n)
        if weight_min is None and weight_max is None and (g := wishes.get("weight")):
            weight_min = int(g) - 50
            weight_max = int(g) + 50
        words = [w for w in wishes.get("words", []) if len(w) > 1]
        cat_path = canonical_path(category) if category and category.startswith("/") else None
        cat_words = norm(category) if category and cat_path is None else None

        tests: list[tuple[str, Any]] = []
        if family_of is not None:
            family = {p.path for p in self.siblings(family_of)} | {family_of.path}
            tests.append(("line", lambda r: r.product.path in family))
        if cat_path is not None:
            tests.append(
                (
                    f"category ({category})",
                    lambda r: (
                        cat_path in r.category_paths
                        or any(c.startswith(cat_path + "/") for c in r.category_paths)
                    ),
                )
            )
        elif cat_words:
            tests.append((f"category ({category})", lambda r: cat_words in r.category_text))
        if kind is not None:
            phrase, without = kind
            tests.append(
                (
                    f"type ({type or phrase})",
                    lambda r: phrase in r.kind and not any(w in r.kind for w in without),
                )
            )
        if size_want is not None:
            tests.append((f"size ({SIZE_LABELS.get(size_want, size_want)})", _is_size(size_want)))
        if color_want is not None:
            tests.append((f"color ({color or color_want})", lambda r: color_want in r.colors))
        if material_want is not None:
            tests.append((f"material ({material or material_want})", _is_material(material_want)))
        if threads_min is not None or threads_max is not None:
            lo, hi = threads_min or 0, threads_max or 10**6
            label = f"{lo}" if lo == hi else f"{threads_min or ''}-{threads_max or ''}"
            tests.append(
                (
                    f"threads ({label})",
                    lambda r: r.product.threads is not None and lo <= r.product.threads <= hi,
                )
            )
        if weight_min is not None or weight_max is not None:
            wlo, whi = weight_min or 0, weight_max or 10**6
            tests.append(
                (
                    f"weight ({weight_min or ''}-{weight_max or ''} g/m²)",
                    lambda r: (
                        r.product.weight_gsm is not None and wlo <= r.product.weight_gsm <= whi
                    ),
                )
            )
        if words:
            want = _expand(words)
            tests.append(
                (
                    f"words ({' '.join(words)})",
                    lambda r: sum(_matches(w, r.words) >= 0.7 for w in want) >= max(1, len(words)),
                )
            )
        # Dropped first when nothing fits: the softest wish, then the next.
        order = ("words", "material", "threads", "weight", "color", "size", "type", "category")
        dropped: list[str] = []
        active = list(tests)
        while True:
            hits = [r for r in self._rows if all(t(r) for _, t in active)]
            if hits or not active:
                break
            drop = next((t for name in order for t in active if t[0].startswith(name)), None)
            if drop is None:  # Only the line itself is left: nothing of it fits.
                break
            active.remove(drop)
            dropped.append(drop[0])
        if not active and tests:
            hits = []

        same = fold(family_of.color) if family_of is not None else None

        def rank(r: _Row) -> tuple[float, str]:
            score = sum(_matches(w, r.name_words) for w in words)
            if same is not None and color_want is None and fold(r.product.color) == same:
                score += 1  # Another size of the line: its own colour first.
            return (-score, r.product.name)

        hits.sort(key=rank)
        return Found(
            tuple(r.product for r in hits[:limit]), len(hits), tuple(dropped), tuple(unknown)
        )

    def catalogue_index(self, cap: int = 5000) -> str:
        """The catalogue in brief, for the prompt: each category with how many
        products it has, and the sizes, thread counts and materials it carries."""
        if not self.products:
            return "(The catalogue is not loaded: find products with search_products.)"
        by_cat: dict[str, list[Product]] = {}
        for p in self.products.values():
            by_cat.setdefault(p.category or "Otros", []).append(p)
        lines: list[str] = []
        size = 0
        for cat, items in sorted(by_cat.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            sizes = sorted({p.size for p in items if p.size}, key=_size_order)
            threads = sorted({p.threads for p in items if p.threads})
            weights = sorted({p.weight_gsm for p in items if p.weight_gsm})
            materials = Counter(p.material for p in items if p.material).most_common(5)
            bits = [f"- {cat} ({len(items)})"]
            if sizes:
                bits.append(f"tamaños: {', '.join(sizes[:8])}")
            if threads:
                bits.append(f"hilos: {', '.join(str(t) for t in threads[:8])}")
            if weights:
                bits.append(f"g/m²: {', '.join(str(w) for w in weights[:6])}")
            if materials:
                bits.append(f"materiales: {', '.join(m for m, _ in materials)}")
            line = "; ".join(bits)
            size += len(line) + 1
            if size > cap:
                lines.append("- … and more: find_products searches all of them.")
                break
            lines.append(line)
        return "\n".join(lines)


def _is_size(want: str) -> Any:
    def test(r: _Row) -> bool:
        return r.size == want

    return test


def _is_material(want: str) -> Any:
    keys = want.split()

    def test(r: _Row) -> bool:
        return any(k in r.material for k in keys)

    return test


_SIZE_ORDER = {label: i for i, label in enumerate(SIZE_LABELS.values())}


def _size_order(label: str) -> tuple[int, str]:
    key = size_key(label)
    return (_SIZE_ORDER.get(SIZE_LABELS.get(key or "", ""), 99), label)


#: A line's sizes in its name and SKU: what siblings do not share.
_SIZE_IN_NAME = re.compile(
    r"\b(?:s[uú]per king|king|\d(?:[.,]5)? plazas?|\d{2,3} ?x ?\d{2,3}(?: ?cm)?)\b", re.IGNORECASE
)


def _family_of(p: Product) -> str:
    """The line a product belongs to when the catalogue gives no family: its
    name without the size."""
    return norm(_SIZE_IN_NAME.sub(" ", p.name))


def _line_of(p: Product) -> str:
    """A product's name without its size and its colour: what its other sizes
    and colours share ("Sábanas King 300 Hilos Blanco" → "sabanas 300 hilos")."""
    name = _SIZE_IN_NAME.sub(" ", fold(p.name))
    colour = set(tokens(p.color))
    kept = [w for w in tokens(name) if w not in colour and color_stem(w) is None]
    return " ".join(kept)


# ─── Loading ───────────────────────────────────────────────────────────────────


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning("cannonhome: {} not loaded: {}", path.name, exc)
        return None


def _read_json(path: Path, key: str = "pages") -> list[dict[str, Any]]:
    """A list of objects, or a dict of them keyed by path; anything else is empty."""
    data = _read(path)
    if isinstance(data, dict):
        data = cast(dict[str, Any], data)
        inner = data.get(key)
        if isinstance(inner, list | dict):
            data = inner
    if isinstance(data, dict):
        items: list[Any] = []
        for k, value in cast(dict[str, Any], data).items():
            if isinstance(value, dict):
                value = cast(dict[str, Any], value)
                items.append({"path": k, **value})
        data = items
    if not isinstance(data, list):
        return []
    return [cast(dict[str, Any], d) for d in cast(list[Any], data) if isinstance(d, dict)]


def _str(value: Any) -> str:
    return " ".join(str(value).split()) if isinstance(value, str | int | float) else ""


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and (m := re.match(r"\s*(\d+)", value)) is not None:
        return int(m.group(1))
    return None


def _strs(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    out: list[str] = []
    for v in cast(list[Any], value):
        if isinstance(v, str) and v.strip():
            out.append(" ".join(v.split()))
        elif isinstance(v, dict):
            v = cast(dict[str, Any], v)
            if t := _str(v.get("label") or v.get("text") or v.get("title") or v.get("name")):
                out.append(t)
    return tuple(out)


def _topic(path: Path) -> Topic:
    text = path.read_text(encoding="utf-8")
    first = text.lstrip().splitlines()[0] if text.strip() else ""
    title = first.lstrip("# ").strip() if first.startswith("#") else path.stem
    return Topic(path.stem, title, text)


def _section(raw: Any) -> Section | None:
    if isinstance(raw, str):
        return Section(" ".join(raw.split()))
    if not isinstance(raw, dict):
        return None
    raw = cast(dict[str, Any], raw)
    heading = _str(raw.get("heading") or raw.get("label") or raw.get("title"))
    if not heading:
        return None
    body = _str(raw.get("text"))
    items = _strs(raw.get("items"))
    level = _int(raw.get("level")) or 0
    selector = _str(raw.get("selector"))
    if heading.startswith("["):
        label = heading.split("]", 1)[-1].strip()
        return Section("", f"{label} {body}".strip(), 0, selector, items)
    return Section(heading, body, level, selector, items)


def _faq(raw: Any) -> Faq | None:
    if not isinstance(raw, dict):
        return None
    raw = cast(dict[str, Any], raw)
    q = _str(raw.get("q") or raw.get("question"))
    return Faq(q, _str(raw.get("a") or raw.get("answer"))) if q else None


def _page(raw: dict[str, Any]) -> Page | None:
    path = raw.get("path") or raw.get("url")
    if not isinstance(path, str) or not on_site(path):
        return None
    sections = tuple(s for r in cast(list[Any], raw.get("sections") or []) if (s := _section(r)))
    if not sections and (heads := _strs(raw.get("headings"))):
        sections = tuple(Section(h) for h in heads)
    return Page(
        path=canonical_path(path),
        title=_str(raw.get("title") or raw.get("h1")) or path,
        description=_str(raw.get("description") or raw.get("meta_description")),
        sections=sections,
        faqs=tuple(f for r in cast(list[Any], raw.get("faqs") or []) if (f := _faq(r))),
        text=_str(raw.get("text")),
        kind=_str(raw.get("type") or raw.get("kind")),
        unlisted=bool(raw.get("unlisted")),
    )


#: Keys a product must never carry here: the catalogue holds no price or stock.
PRICE_KEYS = frozenset(
    {"price", "prices", "final_price", "regular_price", "special_price", "stock", "in_stock"}
    | {"qty", "quantity", "stock_status", "price_range", "offers", "availability"}
)


def _product(raw: dict[str, Any]) -> Product | None:
    name, path = _str(raw.get("name")), raw.get("path") or raw.get("url")
    if not name or not isinstance(path, str) or not on_site(path):
        return None
    attrs_raw = raw.get("attributes")
    attrs: list[tuple[str, str]] = []
    if isinstance(attrs_raw, dict):
        for k, v in cast(dict[str, Any], attrs_raw).items():
            if fold(str(k)) in PRICE_KEYS:
                continue
            if value := _str(v):
                attrs.append((" ".join(k.split()), value))
    return Product(
        sku=_str(raw.get("sku")),
        name=name,
        path=canonical_path(path),
        brand=_str(raw.get("brand")),
        category=_str(raw.get("category")),
        categories=_strs(raw.get("categories")),
        type=_str(raw.get("type")),
        size=_str(raw.get("size")) or None,
        color=_str(raw.get("color")),
        material=_str(raw.get("material")),
        threads=_int(raw.get("threads")),
        weight_gsm=_int(raw.get("weight_gsm")),
        attributes=tuple(attrs),
        summary=_str(raw.get("summary"))[:300],
        image=_str(raw.get("image")),
        family=_str(raw.get("family")),
    )


def _options(raw: Any) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """A category's filter options: ``{var: [labels]}``, ``{var: {label,
    values: [labels]}}`` (the crawl's shape: the group's own name beside its
    options), or a list of groups (``{var|code, options|labels}``); labels may
    be strings or ``{label}``."""
    out: list[tuple[str, tuple[str, ...]]] = []
    if isinstance(raw, dict):
        for var, labels in cast(dict[str, Any], raw).items():
            if isinstance(labels, dict):
                group = cast(dict[str, Any], labels)
                labels = group.get("values") or group.get("options") or group.get("labels")
            if got := _strs(labels):
                out.append((var, got))
    elif isinstance(raw, list):
        for group in cast(list[Any], raw):
            if not isinstance(group, dict):
                continue
            g = cast(dict[str, Any], group)
            var = _str(g.get("var") or g.get("code") or g.get("request_var") or g.get("name"))
            labels = _strs(g.get("options") or g.get("labels") or g.get("values"))
            if var and labels:
                out.append((var, labels))
    return tuple(out)


def _category(raw: dict[str, Any]) -> Category | None:
    path = raw.get("path") or raw.get("url")
    if not isinstance(path, str) or not on_site(path):
        return None
    filters_raw = raw.get("filters")
    filters: list[str] = []
    options = _options(raw.get("options") or raw.get("filter_options"))
    if isinstance(filters_raw, list):
        for f in cast(list[Any], filters_raw):
            if isinstance(f, str):
                filters.append(f)
            elif isinstance(f, dict):
                f = cast(dict[str, Any], f)
                if var := _str(f.get("var") or f.get("code") or f.get("request_var")):
                    filters.append(var)
        if not options:
            options = _options(filters_raw)
    elif isinstance(filters_raw, dict):
        options = options or _options(filters_raw)
        filters.extend(cast(dict[str, Any], filters_raw))
    filters.extend(v for v, _ in options if v not in filters)
    return Category(
        path=canonical_path(path),
        name=_str(raw.get("name") or raw.get("title")) or path,
        parent=canonical_path(_str(raw.get("parent"))) if _str(raw.get("parent")) else "",
        filters=tuple(dict.fromkeys(filters)),
        options=options,
    )


def _redirects(site: Any) -> dict[str, str]:
    if not isinstance(site, dict):
        return {}
    raw = cast(dict[str, Any], site).get("redirects")
    if not isinstance(raw, dict):
        return {}
    return {
        canonical_path(k): canonical_path(v)
        for k, v in cast(dict[str, Any], raw).items()
        if isinstance(v, str)
    }


def load(root: Path = ROOT) -> Knowledge:
    """Every layer under ``root``; whatever is missing is empty."""
    try:
        l1 = (root / "L1.md").read_text(encoding="utf-8").strip() or _L1_FALLBACK
    except OSError:
        logger.warning("cannonhome: L1.md not found; Javier runs on the fallback")
        l1 = _L1_FALLBACK
    topics: dict[str, Topic] = {}
    for path in sorted((root / "L2").glob("*.md")) if (root / "L2").is_dir() else []:
        topics[path.stem] = _topic(path)
    l3 = root / "L3"
    pages = {p.path: p for raw in _read_json(l3 / "pages.json") if (p := _page(raw))}
    products = {
        p.path: p for raw in _read_json(l3 / "products.json", "products") if (p := _product(raw))
    }
    categories = {
        c.path: c
        for raw in _read_json(l3 / "categories.json", "categories")
        if (c := _category(raw))
    }
    return Knowledge(
        l1,
        topics,
        pages,
        redirects=_redirects(_read(l3 / "site.json")),
        products=products,
        categories=categories,
    )


KNOWLEDGE = load()
"""The committed knowledge. Read through the module at session start, so a test
can put a fixture in its place."""

#: The topic names ``read_topic`` offers, fixed at import because they become a
#: ``Literal`` in its schema. A ``Literal`` cannot be empty.
TOPIC_IDS: tuple[str, ...] = tuple(KNOWLEDGE.topics) or ("company",)


__all__ = [
    "KNOWLEDGE",
    "PRICE_KEYS",
    "SITE",
    "SITE_HOST",
    "SITE_HOSTS",
    "SIZE_LABELS",
    "TOPIC_IDS",
    "Category",
    "Faq",
    "Found",
    "Hit",
    "Knowledge",
    "Page",
    "Product",
    "Section",
    "Topic",
    "canonical_path",
    "color_stem",
    "fold",
    "load",
    "material_key",
    "norm",
    "on_site",
    "size_key",
    "tokens",
    "type_key",
    "visitor_wishes",
]
