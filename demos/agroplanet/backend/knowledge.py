"""What Javier knows about Agroplanet, in three layers, read once at import.

- **L1** (``knowledge/L1.md``) is always in his prompt: who Agroplanet is, its
  top categories, how buying works (the cart, then Cotizar: a quote, not an
  online payment), despacho, retiro, garantía and how to reach a person.
- **L2** (``knowledge/L2/<topic>.md``) is a topic he reads with ``read_topic``
  when a question needs more than L1. Each file opens with ``# Title`` and a
  ``Sources:`` line.
- **L3** (``knowledge/L3/*.json``) is the data:

  - ``pages.json`` — the site's information and policy pages, their sections
    and accordion panels, which ``search_site`` searches and every cue is
    checked against.
  - ``categories.json`` — the category tree: each node's code (``AG01``,
    ``AG100``, ``1000902``), path (``/categoria/<slug>/<code>``), name, parent
    and the facets its listing offers with their options, so a filter he asks
    the listing for is one the site has.
  - ``stores.json`` — the 22 stores: name, address, city, región, phone, hours.
  - ``site.json`` — the nav and notes of the crawl.

**There is no product catalogue here, and no price or stock, ever.** Prices
move and some are only confirmed in store: Javier finds products live, in the
visitor's browser, with the ``find_products`` move, and every price he says is
one the page read this call.

The files are built offline and committed. Every one of them may be missing or
empty and this module still imports: the demos backend serves every brain from
one process, and one brain that cannot import takes the others down with it.

The site is one Angular app whose router takes any slug: a category is its
code (``/categoria/<anything>/AG100``) and a product its SKU
(``/producto/<anything>/1173221``). So a category is looked up by its code and
a product named by its SKU; the slug is only what the address shows.

The site is in Spanish and the visitor may ask in English, so every comparison
here folds case and accents.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote, unquote, urlsplit

from loguru import logger

ROOT = Path(__file__).parent / "knowledge"

#: The store. The canonical host is www: the bare domain redirects to it.
SITE_HOST = "www.agroplanet.cl"
SITE_HOSTS = frozenset({SITE_HOST, "agroplanet.cl"})
SITE = f"https://{SITE_HOST}"

_L1_FALLBACK = (
    "Agroplanet (www.agroplanet.cl) is a Chilean store of agricultural parts and supplies, "
    '"Pasión por el campo desde 1956": tractor parts, bearings, batteries, lubricants, '
    "tyres, agro-hardware and implements, with stores across Chile. It sells by quote: the "
    "cart's Cotizar opens a quote form, and a seller follows up. Prices are in Chilean pesos. "
    "Nothing more is loaded: answer only from what you read with your tools and what their "
    "screen reports."
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
    """Lower case, without accents: "Baterías De Arranque" → "baterias de arranque"."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    """Folded words and numbers, without the words every passage has."""
    return [t for t in _TOKEN.findall(fold(text)) if t not in _STOP]


def norm(text: str) -> str:
    """Case, accents, whitespace, curly quotes and dashes folded."""
    return " ".join(fold(text.translate(_QUOTES)).split())


def _split(path_or_url: str) -> tuple[str, str]:
    """The decoded path (``//`` folded, no trailing ``/``) and the query."""
    raw = path_or_url.strip()
    parts = urlsplit(raw if "://" in raw else f"https://x{'' if raw.startswith('/') else '/'}{raw}")
    path = unquote(re.sub(r"/{2,}", "/", parts.path)).rstrip("/") or "/"
    return path, parts.query


#: A product's address: ``/producto/<slug>/<sku>``; the router takes any slug.
_PRODUCT = re.compile(r"^/producto/(?:([^/]+)/)?([A-Za-z0-9][\w-]*)$", re.IGNORECASE)
#: A category's address: ``/categoria/<slug>/<code>``; the code names it.
_CATEGORY = re.compile(r"^/categoria/([^/]+)/([A-Za-z0-9_-]+)$", re.IGNORECASE)
#: What a bare SKU looks like when said or written alone.
_BARE_SKU = re.compile(r"^\d{4,9}$")
#: What a bare category code looks like: AG01, AG100, 1000902.
_BARE_CODE = re.compile(r"^(?:AG\d{2,3}|\d{6,7})$", re.IGNORECASE)


def canonical_path(path_or_url: str) -> str:
    """One spelling per page: ``https://www.agroplanet.cl/Nuestras-Tiendas/?a=1``
    → ``/nuestras-tiendas``; ``/inicio`` → ``/``. A category keeps its code's
    case (``/categoria/lubricantes/AG100``), a product its SKU
    (:func:`product_path`), and a search is :func:`search_path` of its words."""
    path, _ = _split(path_or_url)
    if (product := product_path(path)) is not None:
        return product
    if (m := _CATEGORY.match(path)) is not None:
        return f"/categoria/{m.group(1).lower()}/{m.group(2).upper()}"
    if (q := search_query(path)) is not None:
        return search_path(q)
    low = path.lower()
    return "/" if low == "/inicio" else low


def product_sku(path_or_url: str) -> str | None:
    """The SKU in a product's path or url (``/producto/aceite_x/1173221`` →
    ``1173221``), or a bare SKU; ``None`` when it is no product."""
    raw = path_or_url.strip()
    if _BARE_SKU.match(raw):
        return raw
    path, _ = _split(raw)
    m = _PRODUCT.match(path)
    return m.group(2) if m else None


def product_path(path_or_url: str) -> str | None:
    """A product's path as the page links it, ``/producto/<slug>/<sku>`` (the
    slug lower-cased, no query); ``None`` when it is no product. A bare SKU
    gets the slug ``producto``: the router takes any."""
    raw = path_or_url.strip()
    if _BARE_SKU.match(raw):
        return f"/producto/producto/{raw}"
    path, _ = _split(raw)
    m = _PRODUCT.match(path)
    if m is None:
        return None
    return f"/producto/{(m.group(1) or 'producto').lower()}/{m.group(2)}"


def same_product(a: str | None, b: str | None) -> bool:
    """Whether two paths (or SKUs) name one product: the SKU decides."""
    sa = product_sku(a) if a else None
    return sa is not None and sa == (product_sku(b) if b else None)


#: The search results page: ``/busqueda/<words>``.
SEARCH_PATH = "/busqueda"


def search_query(path_or_url: str) -> str | None:
    """The words of a search results address (``/busqueda/aceite%20motor`` →
    ``aceite motor``), or ``None`` when it is not one."""
    path, _ = _split(path_or_url)
    if not path.lower().startswith(SEARCH_PATH + "/"):
        return None
    return " ".join(path[len(SEARCH_PATH) + 1 :].replace("+", " ").split())


def search_path(query: str) -> str:
    """The search results address for ``query``, as the site builds it: the
    words lower-cased, one space between them, the path segment encoded."""
    return f"{SEARCH_PATH}/" + quote(" ".join(query.lower().split()), safe="")


def on_site(url: str) -> bool:
    """Whether ``url`` is on the store (either host), or a bare path."""
    if "://" not in url:
        return True
    return (urlsplit(url).hostname or "").lower() in SITE_HOSTS


#: Words a visitor says, and the words the site writes for them.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "bearing": ("rodamientos", "rodamiento"),
    "bearings": ("rodamientos", "rodamiento"),
    "ruleman": ("rodamientos", "rodamiento"),
    "rulemanes": ("rodamientos", "rodamiento"),
    "rodamiento": ("rodamientos",),
    "battery": ("baterias", "bateria"),
    "batteries": ("baterias", "bateria"),
    "bateria": ("baterias",),
    "oil": ("aceite", "lubricantes"),
    "aceite": ("aceites", "lubricantes"),
    "aceites": ("lubricantes",),
    "lubricante": ("lubricantes",),
    "grease": ("grasas",),
    "grasa": ("grasas",),
    "coolant": ("refrigerante", "anticongelante"),
    "tire": ("neumaticos", "neumatico"),
    "tires": ("neumaticos", "neumatico"),
    "tyre": ("neumaticos", "neumatico"),
    "tyres": ("neumaticos", "neumatico"),
    "llanta": ("llantas",),
    "rim": ("llantas",),
    "cubierta": ("neumaticos", "neumatico"),
    "goma": ("neumaticos",),
    "neumatico": ("neumaticos",),
    "tube": ("camaras",),
    "camara": ("camaras",),
    "blade": ("cuchillas",),
    "blades": ("cuchillas",),
    "cuchilla": ("cuchillas",),
    "rotovator": ("rotovatores", "rotofresa"),
    "rototiller": ("rotofresa", "rotovatores"),
    "rotavator": ("rotovatores", "rotofresa"),
    "rastra": ("rastras",),
    "harrow": ("rastras",),
    "plow": ("arados", "arado"),
    "plough": ("arados", "arado"),
    "arado": ("arados",),
    "baler": ("pasteria",),
    "enfardadora": ("pasteria",),
    "empacadora": ("pasteria",),
    "fardo": ("pasteria",),
    "spreader": ("abonadores", "abonador"),
    "fertilizadora": ("abonador", "abonadores"),
    "abonadora": ("abonador", "abonadores"),
    "mower": ("desmalezadoras", "segadoras"),
    "desmalezadora": ("desmalezadoras",),
    "rozadora": ("desmalezadoras",),
    "brushcutter": ("desbrozadora",),
    "orilladora": ("desbrozadora",),
    "sprayer": ("pulverizadores", "fumigacion"),
    "fumigadora": ("pulverizadores", "fumigacion"),
    "pulverizador": ("pulverizadores",),
    "seeder": ("sembradora", "sembradoras"),
    "sembradora": ("sembradoras",),
    "filter": ("filtro",),
    "filters": ("filtro",),
    "filtros": ("filtro",),
    "seal": ("retenes",),
    "reten": ("retenes",),
    "clutch": ("embrague",),
    "brakes": ("frenos",),
    "brake": ("frenos",),
    "freno": ("frenos",),
    "pump": ("bomba",),
    "hydraulic": ("hidraulico", "hidraulica"),
    "pto": ("toma", "fuerza", "tdf"),
    "tdf": ("toma", "fuerza"),
    "cardan": ("cardanes", "crucetas"),
    "tractor": ("tractor", "repuestos"),
    "tractors": ("tractor",),
    "implement": ("implementos",),
    "implemento": ("implementos",),
    "generator": ("generadores",),
    "generador": ("generadores",),
    "motobomba": ("motobombas",),
    "boots": ("botas",),
    "gloves": ("guantes", "proteccion", "manos"),
    "fence": ("cerco",),
    "wire": ("alambre",),
    "twine": ("rafia",),
    "shipping": ("despacho",),
    "delivery": ("despacho",),
    "envio": ("despacho",),
    "returns": ("devoluciones", "cambios"),
    "return": ("devoluciones", "cambios"),
    "warranty": ("garantia",),
    "stores": ("tiendas",),
    "store": ("tiendas",),
    "sucursal": ("tiendas",),
    "sucursales": ("tiendas",),
    "pickup": ("retiro",),
    "quote": ("cotizacion",),
    "cotizar": ("cotizacion",),
    "payment": ("pago", "webpay"),
    "privacy": ("privacidad", "datos"),
}


def _expand(words: list[str]) -> list[str]:
    out = list(words)
    for w in words:
        out.extend(_SYNONYMS.get(w, ()))
    return list(dict.fromkeys(out))


def _plural_free(word: str) -> str:
    """A Spanish or English word without its plural: "baterias" → "bateria",
    "neumaticos" → "neumatico", "abonadores" → "abonador"."""
    if len(word) > 5 and word.endswith("es") and word[-3] in "rnld":
        return word[:-2]
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]
    return word


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
    """The page's accordion panels: title and the answer under it."""
    text: str = ""
    kind: str = ""
    """The crawl's page type: ``home``, ``policy``, ``stores``, ``page`` …"""
    unlisted: bool = False

    @property
    def headings(self) -> tuple[str, ...]:
        return tuple(s.heading for s in self.sections if s.heading)


#: Facet names the page and the store's API write differently, folded: one name.
_FACET_ALIASES: dict[str, str] = {
    "marcas": "marca",
    "brand": "marca",
    "brands": "marca",
    "categorias": "categoria",
    "category": "categoria",
    "categories": "categoria",
    "price": "precio",
    "precios": "precio",
    "viscosity": "viscosidad",
    "polarity": "polaridad",
    "amperage": "amperaje",
    "amperes": "amperaje",
    "cca": "cca (-18 grados)",
    "arranque en frio": "cca (-18 grados)",
}


def facet_key(name: str) -> str:
    """A facet's name, folded to the one key the page and the API share:
    "Marca" and "Marcas" are one facet, "Precio" and "price" too."""
    key = norm(name)
    return _FACET_ALIASES.get(key, key)


@dataclass(frozen=True)
class Facet:
    """One filter group of a listing, and its options as the listing writes them."""

    name: str
    """As the listing writes it ("Marca", "Viscosidad", "Precio")."""
    param: str = ""
    """The store's query code (``brand_search``, ``C_DTE_VISCOSIDAD``)."""
    options: tuple[str, ...] = ()
    """The busiest few, without the "(count)"."""
    total: int = 0
    """How many options the panel has (0: as many as ``options``)."""


@dataclass(frozen=True)
class Category:
    code: str
    """The store's code: ``AG01`` (top), ``AG100``, ``1000902``."""
    path: str
    name: str
    parent: str = ""
    """The parent's code (or path, as the crawl wrote it); empty at the top."""
    level: int = 0
    aliases: tuple[str, ...] = ()
    """Other paths of the same node, as links write them."""
    products: int | None = None
    facets: tuple[Facet, ...] = ()
    hidden: bool = False
    """Not shown in the menu's flyout (the CMS hides it), though its listing works."""
    page_name: str = ""
    """What the listing itself titles it, when the menu says otherwise
    ("Lubricantes y Grasas" for the menu's "Lubricantes Y Fluidos")."""

    @property
    def names(self) -> tuple[str, ...]:
        same = not self.page_name or norm(self.page_name) == norm(self.name)
        return (self.name,) if same else (self.name, self.page_name)

    def facet(self, name: str) -> Facet | None:
        """The facet ``name`` names, as this listing writes it."""
        want = facet_key(name)
        for f in self.facets:
            if facet_key(f.name) == want:
                return f
        for f in self.facets:
            key = facet_key(f.name)
            if len(want) >= 3 and (key.startswith(want) or want.startswith(key)):
                return f
        return None

    @property
    def facet_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.facets)


@dataclass(frozen=True)
class Store:
    id: str
    name: str
    zone: str = ""
    address: str = ""
    city: str = ""
    region: str = ""
    hours: str = ""
    phone: str = ""

    @property
    def names(self) -> tuple[str, ...]:
        return (self.name,)


@dataclass(frozen=True)
class Hit:
    """One search result: a page section or an accordion panel."""

    kind: str
    title: str
    snippet: str
    score: float
    path: str | None = None
    section: str | None = None


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

    def add(self, hit: Hit, text: str) -> None:
        toks = tokens(text)
        if not toks:
            return
        tf = Counter(toks)
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


@dataclass
class Knowledge:
    l1: str
    topics: dict[str, Topic]
    pages: dict[str, Page]
    redirects: dict[str, str] = field(default_factory=dict[str, str])
    categories: dict[str, Category] = field(default_factory=dict[str, Category])
    """The categories, by canonical path; an alias path maps to its node too."""
    stores: tuple[Store, ...] = ()
    nav: tuple[str, ...] = ()
    _site: _Index = field(default_factory=_Index, repr=False)
    _by_code: dict[str, Category] = field(default_factory=dict[str, Category], repr=False)

    def __post_init__(self) -> None:
        # Indexed once, here: a search runs while the visitor waits.
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
        for c in sorted(self.categories.values(), key=lambda c: (c.level or 9, c.path)):
            if c.code and c.code.upper() not in self._by_code:
                self._by_code[c.code.upper()] = c
        for c in list(self.categories.values()):
            for alias in c.aliases:
                self.categories.setdefault(canonical_path(alias), c)

    # ── Lookups ──

    def page(self, path_or_url: str) -> Page | None:
        """A site page, following the site's redirects."""
        path = canonical_path(path_or_url)
        path = self.redirects.get(path, path)
        return self.pages.get(path)

    def category(self, path_or_url: str) -> Category | None:
        """The category at this address: by its code, whatever its slug (the
        router takes any), else by the path itself."""
        path = canonical_path(path_or_url)
        path = self.redirects.get(path, path)
        if (m := _CATEGORY.match(path)) is not None and (
            hit := self._by_code.get(m.group(2).upper())
        ) is not None:
            return hit
        return self.categories.get(path)

    def category_by_code(self, code: str) -> Category | None:
        return self._by_code.get(code.strip().upper())

    def category_of(self, path_or_url: str) -> Category | None:
        """The category a listing's address belongs to (its query aside)."""
        return self.category(path_or_url)

    def parent_of(self, cat: Category) -> Category | None:
        """The node above ``cat``, by the code or path the crawl wrote."""
        if not cat.parent:
            return None
        if cat.parent.startswith("/"):
            return self.category(cat.parent)
        return self.category_by_code(cat.parent)

    def top_of(self, cat: Category) -> Category:
        """The top-level category ``cat`` is under (itself, at the top)."""
        seen: set[str] = set()
        while cat.level != 1 and cat.code not in seen:
            seen.add(cat.code)
            up = self.parent_of(cat)
            if up is None:
                break
            cat = up
        return cat

    def children(self, cat: Category) -> list[Category]:
        """The categories right under ``cat``, by the path or code the crawl
        wrote as their parent."""
        parents = {cat.path, cat.code, *cat.aliases}
        return [
            c
            for c in self.unique_categories()
            if c.parent and (c.parent in parents or canonical_path(c.parent) in parents)
        ]

    def tops(self) -> list[Category]:
        """The top-level categories, as the menu lists them."""
        return [c for c in self.unique_categories() if c.level == 1]

    def find_category(self, said: str) -> Category | None:
        """The category ``said`` names: a path, a code, or a name in either
        language, singular or plural ("baterías de arranque", "rodamientos",
        "tractor batteries"). The same name at two levels is the deeper one,
        whose listing has the facets."""
        raw = said.strip()
        if not raw:
            return None
        if raw.startswith("/"):
            return self.category(raw)
        if _BARE_CODE.match(raw):
            return self.category_by_code(raw)
        named = tokens(_CATEGORY_WORDS.get(norm(raw), raw))
        own = {_plural_free(w) for w in named if w not in _CATEGORY_FILLER}
        want = [_plural_free(w) for w in _expand(named) if w not in _CATEGORY_FILLER]
        if not want:
            return None
        unique = self.unique_categories()
        exact = [
            c for c in unique if any({_plural_free(w) for w in tokens(n)} == own for n in c.names)
        ]
        if exact:
            return max(
                exact, key=lambda c: (not c.hidden, bool(c.facets), c.level, c.products or 0)
            )
        scored: list[tuple[float, bool, int, int, Category]] = []
        for c in unique:
            score = 0.0
            for n in c.names:
                have = {_plural_free(w) for w in tokens(n)} - _CATEGORY_FILLER
                hits = sum(1 for w in set(want) if w in have)
                if have and hits:
                    # Every word of the name said, and few words more: the closest.
                    score = max(score, hits / len(have) + hits / len(set(want)))
            if score > 0:
                scored.append((score, not c.hidden, -c.level, c.products or 0, c))
        if not scored:
            return None
        # The closest; between equals, a shown one, then the broader one.
        scored.sort(key=lambda s: (-s[0], -s[1], -s[2], -s[3]))
        best = scored[0]
        return best[4] if best[0] >= 1.0 else None

    def store(self, said: str) -> Store | None:
        """The store ``said`` names: its name, else its city or address
        ("Talca", "en Los Ángeles", "la de Vergara")."""
        want = norm(_STORE_WORDS.sub("", said.strip()))
        if not want or not self.stores:
            return None
        for test in (
            lambda s: any(norm(n) == want for n in s.names),
            lambda s: norm(s.city) == want,
            lambda s: any(norm(n).startswith(want) or want.startswith(norm(n)) for n in s.names),
            lambda s: any(want in norm(n) for n in s.names),
            lambda s: want in norm(s.address),
            lambda s: bool(s.city) and want in norm(s.city),
        ):
            hit = next((s for s in self.stores if test(s)), None)
            if hit is not None:
                return hit
        return None

    def search(self, query: str, limit: int = 6) -> list[Hit]:
        """The site's pages, sections and accordion panels."""
        return self._site.search(query, limit)

    def unique_categories(self) -> list[Category]:
        """Each category once: one row per code, and an alias path is not
        another one."""
        rows = {id(c): c for c in self.categories.values()}.values()
        return [c for c in rows if not c.code or self._by_code.get(c.code.upper()) is c]


#: Names a visitor says for a category, folded, and the site's name for it.
_CATEGORY_WORDS: dict[str, str] = {
    "bateria": "baterias",
    "battery": "baterias",
    "batteries": "baterias",
    "bateria de tractor": "baterias heavy duty",
    "tractor battery": "baterias heavy duty",
    "bateria de camion": "baterias heavy duty",
    "rodamiento": "rodamientos",
    "ruleman": "rodamientos",
    "rulemanes": "rodamientos",
    "bearing": "rodamientos",
    "bearings": "rodamientos",
    "aceite": "lubricantes",
    "aceites": "lubricantes",
    "oil": "lubricantes",
    "lubricante": "lubricantes",
    "aceite de motor": "aceite de motor",
    "aceite hidraulico": "aceite hidraulico",
    "hydraulic oil": "aceite hidraulico",
    "engine oil": "aceite de motor",
    "grasa": "grasas",
    "grease": "grasas",
    "neumatico": "neumaticos agricolas",
    "neumaticos": "neumaticos camaras y llantas",
    "neumatico agricola": "neumaticos agricolas",
    "neumatico de tractor": "neumaticos agricolas",
    "tractor tire": "neumaticos agricolas",
    "tractor tyre": "neumaticos agricolas",
    "tire": "neumaticos camaras y llantas",
    "tires": "neumaticos camaras y llantas",
    "tyres": "neumaticos camaras y llantas",
    "cubierta": "neumaticos agricolas",
    "llanta": "llantas",
    "camara": "camaras agricolas",
    "ferreteria": "agroferreteria",
    "hardware": "agroferreteria",
    "repuesto de tractor": "repuestos de tractor",
    "repuestos tractor": "repuestos de tractor",
    "tractor parts": "repuestos de tractor",
    "implemento": "implementos agricolas",
    "implementos": "implementos agricolas",
    "implements": "implementos agricolas",
    "repuesto de implemento": "repuestos de implementos",
    "rotofresa": "rotofresa",
    "rotovator": "repuestos para rotovatores",
    "cuchillas de rotofresa": "repuestos para rotofresa",
    "pasteria": "repuestos de pasteria",
    "enfardadora": "repuestos de pasteria",
    "abonador": "abonador",
    "abonadora": "abonador",
    "desmalezadora": "desmalezadoras",
    "insumos": "insumos agricolas",
    "maquinaria": "maquinaria",
    "tractor nuevo": "tractor para venta",
    "tractores": "tractor para venta",
}

#: How a visitor wraps a store's name: "la tienda de Talca", "en Los Ángeles".
_STORE_WORDS = re.compile(
    r"^(?:(?:en|in|at)\s+)?(?:(?:la|el|the)\s+)?"
    r"(?:(?:tienda|sucursal|store|local|agroplanet)\s+)?"
    r"(?:(?:de|del|en|in|at)\s+)?(?:(?:la|el|the)\s+)?",
    re.IGNORECASE,
)

#: Words that name no category on their own.
_CATEGORY_FILLER = frozenset({"y", "de", "para", "the", "and", "for", "un", "una", "con"})


# ─── Loading ───────────────────────────────────────────────────────────────────


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning("agroplanet: {} not loaded: {}", path.name, exc)
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
    if isinstance(value, bool):
        return ""
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
            if t := _str(
                v.get("label") or v.get("text") or v.get("title") or v.get("name") or v.get("valor")
            ):
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
    q = _str(raw.get("q") or raw.get("question") or raw.get("title"))
    return Faq(q, _str(raw.get("a") or raw.get("answer") or raw.get("text"))) if q else None


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
        faqs=tuple(
            f for r in cast(list[Any], raw.get("faqs") or raw.get("panels") or []) if (f := _faq(r))
        ),
        text=_str(raw.get("text")),
        kind=_str(raw.get("type") or raw.get("kind")),
        unlisted=bool(raw.get("unlisted")),
    )


def _facet(raw: Any) -> Facet | None:
    if not isinstance(raw, dict):
        return None
    raw = cast(dict[str, Any], raw)
    name = _str(raw.get("name") or raw.get("nombre"))
    if not name:
        return None
    options = tuple(
        re.sub(r"\s*\(\d+\)$", "", o) for o in _strs(raw.get("options") or raw.get("values"))
    )
    return Facet(
        name,
        _str(raw.get("param") or raw.get("code")),
        options[:25],
        max(_int(raw.get("total")) or 0, len(options[:25])),
    )


def _category(raw: dict[str, Any]) -> Category | None:
    path = raw.get("path") or raw.get("url")
    if not isinstance(path, str) or not on_site(path):
        return None
    name = _str(raw.get("name") or raw.get("nombre") or raw.get("title"))
    if not name:
        return None
    path = canonical_path(path)
    code = _str(raw.get("code") or raw.get("id"))
    if not code and (m := _CATEGORY.match(path)) is not None:
        code = m.group(2)
    parent = raw.get("parent")
    return Category(
        code=code.upper(),
        path=path,
        name=name,
        parent=_str(parent) if isinstance(parent, str | int) else "",
        level=_int(raw.get("level")) or 0,
        aliases=tuple(canonical_path(a) for a in _strs(raw.get("aliases")) if on_site(a)),
        products=_int(raw.get("products")),
        facets=tuple(
            f for r in cast(list[Any], raw.get("facets") or []) if (f := _facet(r)) is not None
        ),
        hidden=raw.get("hidden") is True or raw.get("visible") is False,
        page_name=_str(raw.get("page_name")),
    )


def _store(raw: dict[str, Any]) -> Store | None:
    name = _str(raw.get("name") or raw.get("nombre") or raw.get("displayName"))
    if not name:
        return None
    return Store(
        id=_str(raw.get("id") or raw.get("code")),
        name=name,
        zone=_str(raw.get("zone") or raw.get("zona")),
        address=_str(raw.get("address") or raw.get("direccion")),
        city=_str(raw.get("city") or raw.get("ciudad") or raw.get("town")),
        region=_str(raw.get("region")),
        hours=_str(raw.get("hours") or raw.get("horario")),
        phone=_str(raw.get("phone") or raw.get("telefono")),
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


def _nav(site: Any) -> tuple[str, ...]:
    if not isinstance(site, dict):
        return ()
    return _strs(cast(dict[str, Any], site).get("nav"))


#: L2 files that are not topics to read whole. ``categorias`` is the whole
#: category tree with every filter (45 KB): read once, it would ride in every
#: later request of the call (pcfactory dev call 2a2304d8, ~34k tokens). The
#: brain reads one category at a time instead (``read_category``).
_NOT_TOPICS = frozenset({"categorias"})


def load(root: Path = ROOT) -> Knowledge:
    """Every layer under ``root``; whatever is missing is empty."""
    try:
        l1 = (root / "L1.md").read_text(encoding="utf-8").strip() or _L1_FALLBACK
    except OSError:
        logger.warning("agroplanet: L1.md not found; Javier runs on the fallback")
        l1 = _L1_FALLBACK
    topics: dict[str, Topic] = {}
    for path in sorted((root / "L2").glob("*.md")) if (root / "L2").is_dir() else []:
        if path.stem in _NOT_TOPICS:
            continue
        topics[path.stem] = _topic(path)
    l3 = root / "L3"
    pages = {p.path: p for raw in _read_json(l3 / "pages.json") if (p := _page(raw))}
    categories: dict[str, Category] = {}
    for raw in _read_json(l3 / "categories.json", "categories"):
        if (c := _category(raw)) is not None:
            categories.setdefault(c.path, c)
    stores = tuple(s for raw in _read_json(l3 / "stores.json", "stores") if (s := _store(raw)))
    site = _read(l3 / "site.json")
    return Knowledge(
        l1,
        topics,
        pages,
        redirects=_redirects(site),
        categories=categories,
        stores=stores,
        nav=_nav(site),
    )


KNOWLEDGE = load()
"""The committed knowledge. Read through the module at session start, so a test
can put a fixture in its place."""

#: The topic names ``read_topic`` offers, fixed at import because they become a
#: ``Literal`` in its schema. A ``Literal`` cannot be empty.
TOPIC_IDS: tuple[str, ...] = tuple(KNOWLEDGE.topics) or ("company",)

__all__ = [
    "KNOWLEDGE",
    "SEARCH_PATH",
    "SITE",
    "SITE_HOST",
    "SITE_HOSTS",
    "TOPIC_IDS",
    "Category",
    "Facet",
    "Faq",
    "Hit",
    "Knowledge",
    "Page",
    "Section",
    "Store",
    "Topic",
    "canonical_path",
    "facet_key",
    "fold",
    "load",
    "norm",
    "on_site",
    "product_path",
    "product_sku",
    "same_product",
    "search_path",
    "search_query",
    "tokens",
]
