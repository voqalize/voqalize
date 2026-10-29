"""What Javier knows about PC Factory, in three layers, read once at import.

- **L1** (``knowledge/L1.md``) is always in his prompt: who pcFactory is, its
  top categories, the three prices and what each means, despacho, retiro,
  garantía, medios de pago and Empresas in brief.
- **L2** (``knowledge/L2/<topic>.md``) is a topic he reads with ``read_topic``
  when a question needs more than L1. Each file opens with ``# Title`` and a
  ``Sources:`` line.
- **L3** (``knowledge/L3/*.json``) is the data:

  - ``pages.json`` — the site's information, event and category landing pages,
    their sections and FAQs, which ``search_site`` searches and every cue is
    checked against.
  - ``categories.json`` — the category tree: each node's id, path, name, the
    other paths of the same id, and the facets its listing offers with their
    options, so a filter he asks the listing for is one the site has.
  - ``stores.json`` — the 28 stores: name, zone, address, city, región, hours.
  - ``site.json`` — the nav and notes of the crawl.

**There is no product catalogue here, and no price or stock, ever.** The store
has tens of thousands of products whose prices move daily: Javier finds them
live, in the visitor's browser, with the ``find_products`` move, and every
price he says is one the page read this call.

The files are built offline (``knowledge/build.py``) and committed. Every one of
them may be missing or empty and this module still imports: the demos backend
serves every brain from one process, and one brain that cannot import takes the
others down with it.

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
from urllib.parse import parse_qs, urlsplit

from loguru import logger

ROOT = Path(__file__).parent / "knowledge"

#: The store. The canonical host is www: the bare domain redirects to it.
SITE_HOST = "www.pcfactory.cl"
SITE_HOSTS = frozenset({SITE_HOST, "pcfactory.cl"})
SITE = f"https://{SITE_HOST}"

_L1_FALLBACK = (
    'pcFactory (say it "PC Factory") is a Chilean technology retailer, www.pcfactory.cl: '
    "notebooks, gamer, graphics cards, monitors, smartphones and components, with stores "
    "across Chile. Prices are in Chilean pesos. Nothing more is loaded: answer only from what "
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
    """Lower case, without accents: "Tarjetas Gráficas" → "tarjetas graficas"."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    """Folded words and numbers, without the words every passage has."""
    return [t for t in _TOKEN.findall(fold(text)) if t not in _STOP]


def norm(text: str) -> str:
    """Case, accents, whitespace, curly quotes and dashes folded."""
    return " ".join(fold(text.translate(_QUOTES)).split())


def canonical_path(path_or_url: str) -> str:
    """``https://www.pcfactory.cl/Tiendas/?a=1#b`` → ``/tiendas``; a product's
    page is ``/producto/<id>`` whatever its slug (:func:`product_path`)."""
    raw = path_or_url.strip()
    parts = urlsplit(raw if "://" in raw else f"https://x{'' if raw.startswith('/') else '/'}{raw}")
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/").lower()
    path = path or "/"
    return product_path(path) or path


_PRODUCT = re.compile(r"^/producto/(\d+)(?:[-/].*)?$", re.IGNORECASE)


def product_id(path_or_url: str) -> int | None:
    """The product id in a product's path or url, or in a bare id."""
    raw = path_or_url.strip()
    if raw.isdigit():
        return int(raw)
    parts = urlsplit(raw if "://" in raw else f"https://x{'' if raw.startswith('/') else '/'}{raw}")
    m = _PRODUCT.match(re.sub(r"/{2,}", "/", parts.path))
    return int(m.group(1)) if m else None


def product_path(path_or_url: str) -> str | None:
    """A product's canonical path, ``/producto/<id>`` (no slug, no query), as
    the page reports it; ``None`` when it is no product."""
    pid = product_id(path_or_url)
    return f"/producto/{pid}" if pid is not None else None


#: The search results page: the one listing whose address is its query.
SEARCH_PATH = "/busqueda-avanzada"


def search_query(path_or_url: str) -> str | None:
    """The words of a search results address (``/busqueda-avanzada?search=a+b``
    → ``a b``), or ``None`` when it is not one."""
    raw = path_or_url.strip()
    parts = urlsplit(raw if "://" in raw else f"https://x{'' if raw.startswith('/') else '/'}{raw}")
    if parts.path.rstrip("/").lower() != SEARCH_PATH:
        return None
    words = parse_qs(parts.query).get("search", [""])[0]
    return " ".join(words.replace("+", " ").split())


def search_path(query: str) -> str:
    """The search results address for ``query``, as the site builds it: the
    words lower-cased and joined by ``+``."""
    return f"{SEARCH_PATH}?search=" + "+".join(fold(query).split())


def on_site(url: str) -> bool:
    """Whether ``url`` is on the store (either host), or a bare path."""
    if "://" not in url:
        return True
    return (urlsplit(url).hostname or "").lower() in SITE_HOSTS


#: Words a visitor says, and the words the site writes for them.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "laptop": ("notebook", "notebooks"),
    "laptops": ("notebook", "notebooks"),
    "notebook": ("notebooks",),
    "portatil": ("notebook", "notebooks"),
    "computer": ("computadores",),
    "computador": ("computadores",),
    "pc": ("computadores", "escritorio"),
    "desktop": ("escritorio", "desktop"),
    "phone": ("smartphones",),
    "phones": ("smartphones",),
    "celular": ("smartphones",),
    "celulares": ("smartphones",),
    "telefono": ("smartphones",),
    "graphics": ("tarjetas", "graficas"),
    "gpu": ("tarjetas", "graficas"),
    "video": ("graficas",),
    "screen": ("monitores",),
    "monitor": ("monitores",),
    "printer": ("impresoras",),
    "impresora": ("impresoras",),
    "headphones": ("audifonos",),
    "audifono": ("audifonos",),
    "mouse": ("mouses",),
    "keyboard": ("teclados",),
    "teclado": ("teclados",),
    "tv": ("smart", "tv"),
    "console": ("consolas",),
    "consola": ("consolas",),
    "processor": ("procesadores",),
    "cpu": ("procesadores",),
    "procesador": ("procesadores",),
    "motherboard": ("placas", "madres"),
    "ram": ("memorias",),
    "memory": ("memorias",),
    "ssd": ("almacenamiento", "ssd"),
    "disk": ("discos", "almacenamiento"),
    "router": ("routers",),
    "shipping": ("despacho",),
    "delivery": ("despacho",),
    "envio": ("despacho",),
    "returns": ("devolucion", "garantia"),
    "return": ("devolucion", "garantia"),
    "warranty": ("garantia",),
    "stores": ("tiendas",),
    "store": ("tiendas",),
    "pickup": ("retiro",),
    "payment": ("pago", "medios"),
    "installments": ("cuotas",),
    "coupon": ("cupon", "cupones"),
    "business": ("empresas",),
}


def _expand(words: list[str]) -> list[str]:
    out = list(words)
    for w in words:
        out.extend(_SYNONYMS.get(w, ()))
    return list(dict.fromkeys(out))


def _plural_free(word: str) -> str:
    """A Spanish or English word without its plural: "notebooks" → "notebook",
    "tarjetas" → "tarjeta", "monitores" → "monitor"."""
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
    text: str = ""
    kind: str = ""
    """The crawl's page type: ``home``, ``help``, ``category``, ``page`` …"""
    unlisted: bool = False

    @property
    def headings(self) -> tuple[str, ...]:
        return tuple(s.heading for s in self.sections if s.heading)


#: Facet names the page and the store's API write differently, folded: one name.
_FACET_ALIASES: dict[str, str] = {
    "sucursales": "tiendas",
    "sucursal": "tiendas",
    "tienda": "tiendas",
    "stores": "tiendas",
    "store": "tiendas",
    "marca": "marcas",
    "brand": "marcas",
    "brands": "marcas",
    "categoria": "categorias",
    "category": "categorias",
    "categories": "categorias",
    "memoria ram": "ram",
    "memory": "ram",
    "precio": "rango de precios",
    "price": "rango de precios",
}


def facet_key(name: str) -> str:
    """A facet's name, folded to the one key the page and the API share:
    "Sucursales" and "Tiendas" are one facet, "Marca" and "Marcas" too."""
    key = norm(name)
    return _FACET_ALIASES.get(key, key)


#: How the page writes a facet whose API name differs.
_FACET_ON_PAGE = {"sucursales": "Tiendas"}


@dataclass(frozen=True)
class Facet:
    """One filter group of a listing, and its options as the listing writes them."""

    name: str
    """As the listing writes it ("Marcas", "RAM", "Tiendas")."""
    param: str = ""
    """The store's request parameter (``marcas``, ``735~22~``)."""
    options: tuple[str, ...] = ()
    """At most 25, without the "(count)"."""


@dataclass(frozen=True)
class Category:
    id: int | None
    path: str
    name: str
    parent: str = ""
    level: int = 0
    aliases: tuple[str, ...] = ()
    """Other paths of the same id: one leaf can sit under several parents."""
    products: int | None = None
    facets: tuple[Facet, ...] = ()

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
    stock_name: str = ""
    """How the store's stock read names it, when not as /tiendas does
    ("Mall Costanera Center" for "Mall Cenco Costanera")."""

    @property
    def names(self) -> tuple[str, ...]:
        return (self.name, self.stock_name) if self.stock_name else (self.name,)


@dataclass(frozen=True)
class Hit:
    """One search result: a page section or an FAQ."""

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
    _by_id: dict[int, Category] = field(default_factory=dict[int, Category], repr=False)

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
        # One leaf can sit under several parents, each its own row with the
        # others as aliases: the one with the shortest path stands for the id.
        for c in sorted(self.categories.values(), key=lambda c: (c.path.count("/"), c.path)):
            if c.id is not None and c.id not in self._by_id:
                self._by_id[c.id] = c
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
        """The category at exactly this path (or one of its aliases)."""
        path = canonical_path(path_or_url)
        return self.categories.get(self.redirects.get(path, path))

    def category_by_id(self, cid: int) -> Category | None:
        return self._by_id.get(cid)

    def category_of(self, path_or_url: str) -> Category | None:
        """The category a listing's address belongs to: the address itself
        when it is a category, else the nearest category above it."""
        path = canonical_path(path_or_url)
        while path and path != "/":
            if (cat := self.category(path)) is not None:
                return cat
            path = path.rsplit("/", 1)[0] or "/"
        return None

    def find_category(self, said: str) -> Category | None:
        """The category ``said`` names: a path, an id, or a name in either
        language, singular or plural ("notebook gamer", "tarjetas de video",
        "graphics cards"). The same name at two levels is the deeper one,
        whose listing has the facets."""
        raw = said.strip()
        if not raw:
            return None
        if raw.startswith("/"):
            return self.category(raw) or self.category_of(raw)
        if raw.isdigit():
            return self.category_by_id(int(raw))
        named = tokens(_CATEGORY_WORDS.get(norm(raw), raw))
        own = {_plural_free(w) for w in named if w not in _CATEGORY_FILLER}
        want = [_plural_free(w) for w in _expand(named) if w not in _CATEGORY_FILLER]
        if not want:
            return None
        unique = self.unique_categories()
        exact = [c for c in unique if {_plural_free(w) for w in tokens(c.name)} == own]
        if exact:
            return max(exact, key=lambda c: (bool(c.facets), c.level, c.products or 0))
        scored: list[tuple[float, int, int, Category]] = []
        for c in unique:
            have = {_plural_free(w) for w in tokens(c.name)}
            if not have:
                continue
            hits = sum(1 for w in want if w in have)
            if hits == 0:
                continue
            # Every word of the name said, and few words more: the closest.
            score = hits / len(have) + hits / len(want)
            scored.append((score, c.level, c.products or 0, c))
        if not scored:
            return None
        scored.sort(key=lambda s: (-s[0], -s[1], -s[2]))
        best = scored[0]
        return best[3] if best[0] >= 1.0 else None

    def store(self, said: str) -> Store | None:
        """The store ``said`` names: its name, else its comuna or city
        ("Maipú", "en Concepción", "la del Costanera")."""
        want = norm(_STORE_WORDS.sub("", said.strip()))
        if not want or not self.stores:
            return None
        for test in (
            lambda s: any(norm(n) == want for n in s.names),
            lambda s: any(norm(n).startswith(want) or want.startswith(norm(n)) for n in s.names),
            lambda s: any(want in norm(n) for n in s.names),
            lambda s: norm(s.city) == want,
            lambda s: want in norm(s.address),
            lambda s: bool(s.city) and want in norm(s.city),
        ):
            hit = next((s for s in self.stores if test(s)), None)
            if hit is not None:
                return hit
        return None

    def search(self, query: str, limit: int = 6) -> list[Hit]:
        """The site's pages, sections and FAQs."""
        return self._site.search(query, limit)

    def unique_categories(self) -> list[Category]:
        """Each category once: one row per id (the one that stands for it), and
        an alias path is not another one."""
        rows = {id(c): c for c in self.categories.values()}.values()
        return [c for c in rows if c.id is None or self._by_id.get(c.id) is c]


#: Names a visitor says for a category, folded, and the site's name for it.
_CATEGORY_WORDS: dict[str, str] = {
    "laptop": "notebooks",
    "laptops": "notebooks",
    "gaming laptop": "notebooks gamer",
    "gaming laptops": "notebooks gamer",
    "notebook gamer": "notebooks gamer",
    "portatil": "notebooks",
    "graphics card": "tarjetas graficas",
    "graphics cards": "tarjetas graficas",
    "tarjeta de video": "tarjetas graficas",
    "tarjetas de video": "tarjetas graficas",
    "tarjeta grafica": "tarjetas graficas",
    "gpu": "tarjetas graficas",
    "celular": "smartphones",
    "celulares": "smartphones",
    "phone": "smartphones",
    "phones": "smartphones",
    "telefono": "smartphones",
    "monitor": "monitores",
    "monitor gamer": "monitores",
    "screen": "monitores",
    "tv": "smart tv",
    "television": "smart tv",
    "televisor": "smart tv",
    "procesador": "procesadores",
    "cpu": "procesadores",
    "placa madre": "placas madres",
    "motherboard": "placas madres",
    "ram": "memorias",
    "memoria ram": "memorias",
    "fuente de poder": "fuentes de poder",
    "psu": "fuentes de poder",
    "gabinete": "gabinetes",
    "case": "gabinetes",
    "impresora": "impresoras hogar y oficina",
    "printer": "impresoras hogar y oficina",
    "consola": "consolas",
    "console": "consolas",
    "pc gamer": "desktops gamer",
    "desktop gamer": "desktops gamer",
    "audifonos": "audifonos",
    "headphones": "audifonos",
    "tablet": "tablets",
}

#: How a visitor wraps a store's name: "la tienda de Maipú", "en el Costanera".
_STORE_WORDS = re.compile(
    r"^(?:(?:en|in|at)\s+)?(?:(?:la|el|the)\s+)?(?:(?:tienda|sucursal|store|local|mall)\s+)?"
    r"(?:(?:de|del|en|in|at)\s+)?(?:(?:la|el|the)\s+)?",
    re.IGNORECASE,
)

#: Words that name no category on their own.
_CATEGORY_FILLER = frozenset({"y", "de", "para", "the", "and", "for", "un", "una"})


# ─── Loading ───────────────────────────────────────────────────────────────────


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning("pcfactory: {} not loaded: {}", path.name, exc)
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


def _facet(raw: Any) -> Facet | None:
    if not isinstance(raw, dict):
        return None
    raw = cast(dict[str, Any], raw)
    name = _str(raw.get("name") or raw.get("nombre"))
    if not name:
        return None
    name = _FACET_ON_PAGE.get(norm(name), name)
    options = tuple(
        re.sub(r"\s*\(\d+\)$", "", o) for o in _strs(raw.get("options") or raw.get("items"))
    )
    return Facet(name, _str(raw.get("param")), options[:25])


def _category(raw: dict[str, Any]) -> Category | None:
    path = raw.get("path") or raw.get("url")
    if not isinstance(path, str) or not on_site(path):
        return None
    name = _str(raw.get("name") or raw.get("nombre") or raw.get("title"))
    if not name:
        return None
    parent = raw.get("parent")
    return Category(
        id=_int(raw.get("id")),
        path=canonical_path(path),
        name=name,
        parent=_str(parent) if isinstance(parent, str | int) else "",
        level=_int(raw.get("level")) or 0,
        aliases=tuple(canonical_path(a) for a in _strs(raw.get("aliases")) if on_site(a)),
        products=_int(raw.get("products")),
        facets=tuple(
            f for r in cast(list[Any], raw.get("facets") or []) if (f := _facet(r)) is not None
        ),
    )


def _store(raw: dict[str, Any]) -> Store | None:
    name = _str(raw.get("name") or raw.get("nombre"))
    if not name:
        return None
    return Store(
        id=_str(raw.get("id")),
        name=name,
        zone=_str(raw.get("zone") or raw.get("zona")),
        address=_str(raw.get("address") or raw.get("direccion")),
        city=_str(raw.get("city") or raw.get("ciudad")),
        region=_str(raw.get("region")),
        hours=_str(raw.get("hours") or raw.get("horario")),
        stock_name=_str(raw.get("stock_name")),
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
#: category tree with every filter (95 KB): read once on dev call 2a2304d8, it
#: carried ~34k tokens into every later request of the call. The brain reads
#: one category at a time instead (``read_category``), from categories.json.
_NOT_TOPICS = frozenset({"categorias"})


def load(root: Path = ROOT) -> Knowledge:
    """Every layer under ``root``; whatever is missing is empty."""
    try:
        l1 = (root / "L1.md").read_text(encoding="utf-8").strip() or _L1_FALLBACK
    except OSError:
        logger.warning("pcfactory: L1.md not found; Javier runs on the fallback")
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
    "product_id",
    "product_path",
    "search_path",
    "search_query",
    "tokens",
]
