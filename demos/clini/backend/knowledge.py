"""What Javier knows about Clini, in three layers, read once at import.

- **L1** (``knowledge/L1.md``) is always in his prompt: what Clini is, its
  services and prices in brief, Fonasa and convenios, the sedes, how to book,
  and the site's navigation.
- **L2** (``knowledge/L2/<topic>.md``) is a topic he reads with ``read_topic``
  when a question needs more than L1. Each file opens with ``# Title`` and a
  ``Sources:`` line.
- **L3** (``knowledge/L3/*.json``) is the data:

  - ``pages.json`` — the site itself, every page's sections, FAQs, tabs and
    forms, which ``search_site`` searches and which the brain checks every move
    against: a path he navigates to, a section he scrolls to, an FAQ he opens.
  - ``blog.json`` — the blog posts, lightly (title, description, headings).
  - ``site.json`` — redirects and probes; the redirects let an old link
    (``/contacto``) resolve to the page it lands on.
  - ``branches.json`` — the 20 sedes from /ubicaciones (``find_branches``).
  - ``prices.json`` — the cotizador's catalogue, offline (``offline_prices``):
    the fallback when the live price lookup fails.
  - ``agenda_services.json`` — agenda-web's services and prestaciones
    (``agenda_service``), the codes ``OpenAgenda`` is checked against.

The files are built offline (``knowledge/build.py``) and committed. Every one of
them may be missing or empty and this module still imports: the demos backend
serves every brain from one process, and one brain that cannot import takes the
others down with it.

The site is in Spanish and the visitor may ask in English, so every comparison
here folds case and accents: "pediatria" is "Pediatría".
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

#: The site (Webflow) and the booking, which is its own host and opens top-level.
SITE_HOST = "www.clini.cl"
SITE = f"https://{SITE_HOST}"
AGENDA_HOST = "agenda-web.clini.cl"
AGENDA = f"https://{AGENDA_HOST}"

_L1_FALLBACK = (
    "Clini's website is www.clini.cl, and its online booking is agenda-web.clini.cl. "
    "Nothing more is loaded: answer only from what you read with your tools."
)


# ─── Text ──────────────────────────────────────────────────────────────────────

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
_STOP = frozenset(
    # English and Spanish words every passage has.
    """a an and are as at be by can do does for from has have how i in is it its me my of on
    or the to what which with you your el la los las un una unos unas de del y o en por para
    con que se su sus es al lo como mas tu te mi""".split()  # noqa: SIM905
)
#: Curly quotes and dashes, folded to their plain forms (by code point: they look alike).
_QUOTES = str.maketrans(
    {chr(0x2018): "'", chr(0x2019): "'", chr(0x201C): '"', chr(0x201D): '"'}
    | {chr(0x2013): "-", chr(0x2014): "-"}
)


def fold(text: str) -> str:
    """Lower case, without accents: "Pediatría Ñuñoa" → "pediatria nunoa"."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    """Folded words and numbers, without the words every passage has."""
    return [t for t in _TOKEN.findall(fold(text)) if t not in _STOP]


def norm(text: str) -> str:
    """Case, accents, whitespace, curly quotes and dashes folded."""
    return " ".join(fold(text.translate(_QUOTES)).split())


def canonical_path(path_or_url: str) -> str:
    """``https://www.clini.cl/Convenios-Salud/?a=1#b`` → ``/convenios-salud``."""
    raw = path_or_url.strip()
    parts = urlsplit(raw if "://" in raw else f"https://x{'' if raw.startswith('/') else '/'}{raw}")
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/").lower()
    return path or "/"


#: Words a visitor says for an exam, and the words the catalogue uses for it.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "rm": ("resonancia",),
    "resonancias": ("resonancia",),
    "mri": ("resonancia",),
    "tac": ("tomografia",),
    "scanner": ("tomografia", "tac"),
    "escaner": ("tomografia", "tac"),
    "tc": ("tomografia",),
    "eco": ("ecografia",),
    "ecografias": ("ecografia",),
    "ultrasound": ("ecografia",),
    "rx": ("radiografia",),
    "rayos": ("radiografia",),
    "xray": ("radiografia",),
    "mamo": ("mamografia",),
    "mammogram": ("mamografia",),
    "pet": ("pet",),
    "ecg": ("electrocardiograma",),
    "electro": ("electrocardiograma",),
    "knee": ("rodilla",),
    "shoulder": ("hombro",),
    "hip": ("cadera",),
    "spine": ("columna",),
    "brain": ("cerebro",),
    "blood": ("sangre",),
    "fasting": ("ayuno",),
}


def _expand(words: list[str]) -> list[str]:
    out = list(words)
    for w in words:
        out.extend(_SYNONYMS.get(w, ()))
    return list(dict.fromkeys(out))


def _covered(words: list[str], have: set[str]) -> int:
    """How many of the visitor's words (or a synonym of each) ``have`` holds."""
    return sum(
        1 for w in words if any(_matches(x, have) >= 0.7 for x in (w, *_SYNONYMS.get(w, ())))
    )


def _matches(want: str, have: set[str]) -> float:
    """1 for the word itself, 0.7 for a word it starts (rodilla → rodillas), else 0."""
    if want in have:
        return 1.0
    if len(want) >= 4 and any(
        h.startswith(want) or (len(h) >= 4 and want.startswith(h)) for h in have
    ):
        return 0.7
    return 0.0


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
class FormField:
    name: str
    label: str = ""
    type: str = ""
    required: bool = False
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class Form:
    id: str
    name: str
    fields: tuple[FormField, ...] = ()
    submit: str = ""


@dataclass(frozen=True)
class Page:
    path: str
    title: str
    description: str = ""
    sections: tuple[Section, ...] = ()
    faqs: tuple[Faq, ...] = ()
    tabs: tuple[str, ...] = ()
    forms: tuple[Form, ...] = ()
    text: str = ""
    kind: str = ""
    """The crawl's page type: ``core``, ``lasik``, ``imaging``, ``blog`` …"""
    unlisted: bool = False
    """No other page links it, or the sitemap leaves it out (a campaign landing)."""

    @property
    def headings(self) -> tuple[str, ...]:
        return tuple(s.heading for s in self.sections if s.heading)

    @property
    def subheadings(self) -> tuple[str, ...]:
        return tuple(i for s in self.sections for i in s.items)


@dataclass(frozen=True)
class Branch:
    """A sede, as /ubicaciones lists it."""

    name: str
    address: str = ""
    comuna: str = ""
    region: str = ""
    services: tuple[str, ...] = ()
    hours: str = ""
    book_link: tuple[str, ...] = ()


@dataclass(frozen=True)
class Price:
    """One item of the cotizador's catalogue. Prices are CLP; ``fonasa`` is the
    Fonasa Nivel 1 copago (tramos B, C and D)."""

    id: int
    nombre: str
    codigo: str = ""
    categoria: str = ""
    servicio: str = ""
    fonasa: int | None = None
    particular: int | None = None
    contraste: bool = False
    preparacion: str = ""


@dataclass(frozen=True)
class Prestacion:
    code: int
    name: str


@dataclass(frozen=True)
class Region:
    code: int
    name: str
    default: bool = False


@dataclass(frozen=True)
class AgendaService:
    """One agenda-web service: ``?servicio=<servicio>[&prestacion=<code>]``."""

    servicio: int
    name: str
    url: str = ""
    prestaciones: tuple[Prestacion, ...] = ()
    regions: tuple[Region, ...] = ()
    sectors: tuple[str, ...] = ()
    linked_from: tuple[str, ...] = ()
    """The site pages that link it; empty means the site never offers it."""

    def prestacion(self, code: int) -> Prestacion | None:
        return next((p for p in self.prestaciones if p.code == code), None)

    def deep_link(self, prestacion: int | None = None) -> str:
        url = self.url or f"{AGENDA}/?servicio={self.servicio}"
        return f"{url}&prestacion={prestacion}" if prestacion is not None else url


@dataclass(frozen=True)
class Hit:
    """One search result: a page section, an FAQ, a sede or a blog post."""

    kind: str
    """``page``, ``faq``, ``branch`` or ``post``."""
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


@dataclass
class Knowledge:
    l1: str
    topics: dict[str, Topic]
    pages: dict[str, Page]
    """The site's pages, by canonical path (not the blog)."""
    posts: dict[str, Page] = field(default_factory=dict[str, Page])
    """The blog posts, by canonical path."""
    redirects: dict[str, str] = field(default_factory=dict[str, str])
    branches: tuple[Branch, ...] = ()
    prices: tuple[Price, ...] = ()
    agenda: dict[int, AgendaService] = field(default_factory=dict[int, AgendaService])
    _site: _Index = field(default_factory=_Index, repr=False)

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
        for b in self.branches:
            about = (
                f"{b.name}\n{b.comuna} {b.region}\n{b.address}\n{' '.join(b.services)}\n{b.hours}"
            )
            self._site.add(Hit("branch", b.name, "", 0, path="/ubicaciones", section=b.name), about)
        for post in self.posts.values():
            hit = Hit("post", post.title, "", 0, path=post.path)
            self._site.add(hit, f"{post.title}\n{post.description}", weight=2)
            self._site.add(hit, f"{' '.join(post.headings)}\n{post.text}")
        self._site.done()

    # ── Lookups ──

    def page(self, path_or_url: str) -> Page | None:
        """A site page or a blog post, following the site's redirects."""
        path = canonical_path(path_or_url)
        path = self.redirects.get(path, path)
        return self.pages.get(path) or self.posts.get(path)

    def near_paths(self, path_or_url: str, limit: int = 3) -> list[str]:
        want = canonical_path(path_or_url)
        scored = sorted(
            self.pages, key=lambda p: SequenceMatcher(None, want, p).ratio(), reverse=True
        )
        return scored[:limit]

    def search(self, query: str, limit: int = 6) -> list[Hit]:
        """The site's pages, sections and FAQs, the sedes and the blog posts."""
        return self._site.search(query, limit)

    def find_branches(self, query: str, n: int = 3) -> list[Branch]:
        """Sedes by comuna, region, name, street or service, best first; a tie
        goes to the sede that offers more."""
        said = tokens(query)
        want = _expand(said)
        if not want:
            return []
        phrase = norm(query)
        scored: list[tuple[int, float, int, Branch]] = []
        for i, b in enumerate(self.branches):
            fields = (
                (b.comuna, 3.0),
                (b.name, 3.0),
                (b.region, 2.0),
                (" ".join(b.services), 2.0),
                (b.address, 1.0),
            )
            s = 0.0
            for text, weight in fields:
                have = set(tokens(text))
                s += weight * sum(_matches(w, have) for w in want)
                if len(phrase) > 3 and phrase in norm(text):
                    s += weight
            if s > 0:
                every = set(
                    tokens(f"{b.name} {b.comuna} {b.region} {' '.join(b.services)} {b.address}")
                )
                scored.append((_covered(said, every), s + 0.1 * len(b.services), -i, b))
        # Only the sedes that answer as much of the question as the best one does.
        top = max((t[0] for t in scored), default=0)
        scored = sorted(
            (t for t in scored if t[0] == top), key=lambda t: (t[1], t[2]), reverse=True
        )
        return [t[3] for t in scored[:n]]

    def offline_prices(self, query: str, n: int = 6) -> list[Price]:
        """The catalogue's items for an exam, best first: every word the visitor
        said counts, a shorter name wins a tie (the plain exam before "ambas")."""
        said = tokens(query)
        want = _expand(said)
        if not want:
            return []
        scored: list[tuple[int, float, Price]] = []
        for p in self.prices:
            name = set(tokens(p.nombre))
            about = set(tokens(f"{p.categoria} {p.servicio}"))
            hits = [max(_matches(w, name), 0.6 * _matches(w, about)) for w in want]
            if not any(h >= 0.7 for h in hits):
                continue
            scored.append((_covered(said, name | about), sum(hits) - 0.02 * len(name), p))
        # Only the items that name as much of the exam as the best one does.
        top = max((t[0] for t in scored), default=0)
        scored = sorted((t for t in scored if t[0] == top), key=lambda t: -t[1])
        return [t[2] for t in scored[:n]]

    def agenda_service(self, servicio: int) -> AgendaService | None:
        return self.agenda.get(servicio)


# ─── Loading ───────────────────────────────────────────────────────────────────


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("clini: {} not loaded: {}", path.name, exc)
        return None


def _read_json(path: Path) -> list[dict[str, Any]]:
    """A list of objects, or a dict of them keyed by path; anything else is empty."""
    data = _read(path)
    if isinstance(data, dict):
        data = cast(dict[str, Any], data)
        inner = data.get("pages")
        if isinstance(inner, list | dict):
            data = inner
    if isinstance(data, dict):
        items: list[Any] = []
        for key, value in cast(dict[str, Any], data).items():
            if isinstance(value, dict):
                value = cast(dict[str, Any], value)
                items.append({"path": key, **value})
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
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
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
    # A block with no heading of its own is labelled by the crawl in brackets
    # ("[section-4380086] FONASA Tramos B, C y D"): searchable, but nothing the
    # page can scroll to by heading, so it is not offered as one.
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


def _form(raw: Any) -> Form | None:
    if not isinstance(raw, dict):
        return None
    raw = cast(dict[str, Any], raw)
    fields: list[FormField] = []
    for f in cast(list[Any], raw.get("fields") or []):
        if not isinstance(f, dict):
            continue
        f = cast(dict[str, Any], f)
        name = _str(
            f.get("name")
            or f.get("id")
            or f.get("data_name")
            or f.get("label")
            or f.get("placeholder")
        )
        if not name or _str(f.get("type")) in ("hidden", "submit"):
            continue
        fields.append(
            FormField(
                name=name,
                label=_str(f.get("label") or f.get("placeholder")),
                type=_str(f.get("type")),
                required=bool(f.get("required")),
                options=_strs(f.get("options")),
            )
        )
    name = _str(raw.get("name") or raw.get("data_name") or raw.get("data-name") or raw.get("id"))
    return Form(
        id=_str(raw.get("id")),
        name=name,
        fields=tuple(fields),
        submit=_str(raw.get("submit") or raw.get("submit_label") or raw.get("submit_text")),
    )


def _page(raw: dict[str, Any]) -> Page | None:
    path = raw.get("path") or raw.get("url")
    if not isinstance(path, str):
        return None
    sections = tuple(s for r in cast(list[Any], raw.get("sections") or []) if (s := _section(r)))
    if not sections and (heads := _strs(raw.get("headings"))):
        sections = tuple(Section(h) for h in heads)
    tabs_raw = cast(list[Any], raw.get("tabs") or [])
    tabs: list[str] = []
    for t in tabs_raw:
        if isinstance(t, dict):
            t = cast(dict[str, Any], t)
            if isinstance(labels := t.get("labels"), list):
                tabs.extend(_strs(labels))
                continue
        tabs.extend(_strs([t]))
    return Page(
        path=canonical_path(path),
        title=_str(raw.get("title")) or path,
        description=_str(raw.get("description") or raw.get("meta_description")),
        sections=sections,
        faqs=tuple(f for r in cast(list[Any], raw.get("faqs") or []) if (f := _faq(r))),
        tabs=tuple(dict.fromkeys(tabs)),
        forms=tuple(f for r in cast(list[Any], raw.get("forms") or []) if (f := _form(r))),
        text=_str(raw.get("text")),
        kind=_str(raw.get("type") or raw.get("kind")),
        unlisted=bool(raw.get("unlisted")),
    )


def _branch(raw: dict[str, Any]) -> Branch | None:
    name = _str(raw.get("name"))
    if not name:
        return None
    links = raw.get("book_link")
    return Branch(
        name=name,
        address=_str(raw.get("address")),
        comuna=_str(raw.get("comuna")),
        region=_str(raw.get("region")),
        services=_strs(raw.get("services")),
        hours=_str(raw.get("hours")),
        book_link=_strs(links)
        if isinstance(links, list)
        else ((_str(links),) if _str(links) else ()),
    )


def _price(raw: dict[str, Any]) -> Price | None:
    pid, name = _int(raw.get("id")), _str(raw.get("nombre"))
    if pid is None or not name:
        return None
    return Price(
        id=pid,
        nombre=name,
        codigo=_str(raw.get("codigo")),
        categoria=_str(raw.get("categoria")),
        servicio=_str(raw.get("servicio")),
        fonasa=_int(raw.get("precioFonasa")),
        particular=_int(raw.get("precioParticular")),
        contraste=bool(raw.get("requiereContraste")),
        preparacion=_str(raw.get("preparacion")),
    )


def _agenda(data: Any) -> dict[int, AgendaService]:
    if not isinstance(data, dict):
        return {}
    out: dict[int, AgendaService] = {}
    for key, value in cast(dict[str, Any], data).items():
        code = _int(key)
        if code is None or not isinstance(value, dict):
            continue
        v = cast(dict[str, Any], value)
        pres: list[Prestacion] = []
        for p in cast(list[Any], v.get("prestaciones") or []):
            if isinstance(p, dict):
                p = cast(dict[str, Any], p)
                if (c := _int(p.get("code"))) is not None:
                    pres.append(Prestacion(c, _str(p.get("name"))))
        regions: list[Region] = []
        for r in cast(list[Any], v.get("regions") or []):
            if isinstance(r, dict):
                r = cast(dict[str, Any], r)
                if (c := _int(r.get("code"))) is not None:
                    regions.append(Region(c, _str(r.get("name")), bool(r.get("default"))))
        out[code] = AgendaService(
            servicio=code,
            name=_str(v.get("name")),
            url=_str(v.get("url")),
            prestaciones=tuple(pres),
            regions=tuple(regions),
            sectors=_strs(v.get("sectors")),
            linked_from=_strs(v.get("linked_from")),
        )
    return out


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
        logger.warning("clini: L1.md not found; Javier runs on the fallback")
        l1 = _L1_FALLBACK
    topics: dict[str, Topic] = {}
    for path in sorted((root / "L2").glob("*.md")) if (root / "L2").is_dir() else []:
        topics[path.stem] = _topic(path)
    l3 = root / "L3"
    pages = {p.path: p for raw in _read_json(l3 / "pages.json") if (p := _page(raw))}
    posts = {p.path: p for raw in _read_json(l3 / "blog.json") if (p := _page(raw))}
    return Knowledge(
        l1,
        topics,
        pages,
        posts=posts,
        redirects=_redirects(_read(l3 / "site.json")),
        branches=tuple(b for raw in _read_json(l3 / "branches.json") if (b := _branch(raw))),
        prices=tuple(p for raw in _read_json(l3 / "prices.json") if (p := _price(raw))),
        agenda=_agenda(_read(l3 / "agenda_services.json")),
    )


KNOWLEDGE = load()
"""The committed knowledge. Read through the module at session start, so a test
can put a fixture in its place."""

#: The topic names ``read_topic`` offers, fixed at import because they become a
#: ``Literal`` in its schema. A ``Literal`` cannot be empty.
TOPIC_IDS: tuple[str, ...] = tuple(KNOWLEDGE.topics) or ("company",)


def find_branches(query: str, n: int = 3) -> list[Branch]:
    """``KNOWLEDGE.find_branches``, read through the module (a test may swap it)."""
    return KNOWLEDGE.find_branches(query, n)


def offline_prices(query: str, n: int = 6) -> list[Price]:
    """``KNOWLEDGE.offline_prices``, read through the module."""
    return KNOWLEDGE.offline_prices(query, n)


def agenda_service(servicio: int) -> AgendaService | None:
    """``KNOWLEDGE.agenda_service``, read through the module."""
    return KNOWLEDGE.agenda_service(servicio)


__all__ = [
    "AGENDA",
    "AGENDA_HOST",
    "KNOWLEDGE",
    "SITE",
    "SITE_HOST",
    "TOPIC_IDS",
    "AgendaService",
    "Branch",
    "Faq",
    "Form",
    "FormField",
    "Hit",
    "Knowledge",
    "Page",
    "Prestacion",
    "Price",
    "Region",
    "Section",
    "Topic",
    "agenda_service",
    "canonical_path",
    "find_branches",
    "fold",
    "load",
    "norm",
    "offline_prices",
    "tokens",
]
