"""What Javier knows about Saint George's College, in three layers, read once at import.

- **L1** (``knowledge/L1.md``) is always in his prompt: what the school is, its
  units and levels, admissions, formation, families, contact, and the site's
  navigation.
- **L2** (``knowledge/L2/<topic>.md``) is a topic he reads with ``read_topic``
  when a question needs more than L1. Each file opens with ``# Title`` and a
  ``Sources:`` line.
- **L3** (``knowledge/L3/pages.json``) is the site itself — every page's
  sections, accordions, cards and links out (documents, tickets, portals) —
  which ``search_site`` searches and which the brain checks every move against:
  a path he navigates to, a section he scrolls to, an accordion he opens, a
  link he opens.

The files are built offline (``knowledge/build.py``) and committed. Every one of
them may be missing or empty and this module still imports: the demos backend
serves every brain from one process, and one brain that cannot import takes the
others down with it.

What changes during the year — fees, admission status, the calendar — is
deliberately not trusted from here: the extension reads it off the visitor's
own page while the call is on (see ``brain.py``). So every fee the crawl or a
topic wrote down ("UF 85") and the admission page's status lines ("Admisión
2027: …") are taken out as the layers load, and a search can never hand the
model last month's value. Pages the site serves empty (its
broken parent pages, its unused post types) are left out, so no move lands on
one. The brain itself never fetches the site.

The site is in Spanish and the visitor may ask in English, so every comparison
here folds case, accents and the ordinal marks: "1° basico" is "1º BÁSICO".
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
from urllib.parse import urlsplit

from loguru import logger

ROOT = Path(__file__).parent / "knowledge"

SITE_HOST = "saintgeorge.cl"
SITE = f"https://{SITE_HOST}"
#: Where the site itself sends a visitor, and so where Javier may open a new
#: tab: its own documents, the musical's tickets, the families' portals (each a
#: login he only opens when asked), the careers portal, and the community's
#: own sites.
LINK_HOSTS = (
    "saintgeorge.cl",
    "ticketplus.cl",
    "schoolnet.colegium.com",
    "lirmi.com",
    "profejobs.cl",
    "cdasaintgeorge.cl",
    "oldgeorgians.cl",
    "congregaciondesantacruz.cl",
    "sites.google.com",
    "instagram.com",
    "linkedin.com",
)

_L1_FALLBACK = (
    "Saint George's College's website is saintgeorge.cl. Nothing more is loaded: "
    "answer only from what you read with your tools and what the screen shows."
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
#: Apostrophes the site writes as other marks (a curly one in its name), and the
#: ordinal marks its grades carry ("1º BÁSICO", "9°"), which NFKD would turn
#: into an "o" for one and leave for the other.
_MARKS = str.maketrans(
    {chr(0x00B4): "'", chr(0x2019): "'", chr(0x0060): "'"}
    | {chr(0x00BA): "", chr(0x00B0): "", chr(0x00AA): ""}
)


#: A fee as the site writes it: "UF 85", "UF 13,5".
_FEE = re.compile(r"\bUF\s*\d+(?:[.,]\d+)*", re.IGNORECASE)
_FEE_LIVE = "UF (read live: show_fees)"


def redact_fees(text: str) -> str:
    """``text`` with every fee value taken out: fees are only ever read live."""
    return _FEE.sub(_FEE_LIVE, text)


#: The admission page's status lines, "Admisión 2027: …", "Admisión Pre Kínder
#: 2028: …", up to the next bold label or the end of the line.
_ADMISSION_LABEL = r"\bAdmisi[oó]n(?:\s+Pre[\s-]*K[ií]nder)?\s+\d{4}\s*:"
_ADMISSION = re.compile(
    rf"({_ADMISSION_LABEL}).*?(?=\s*(?:{_ADMISSION_LABEL}|\bValores\b|\bConsultas\s*:|\n|$))",
    re.IGNORECASE,
)
_ADMISSION_LIVE = r'\1 (read live: show_fees about="admission")'


def redact_live(text: str) -> str:
    """``text`` with what is only ever read live taken out: the fees and the
    admission status."""
    return _ADMISSION.sub(_ADMISSION_LIVE, redact_fees(text))


def fold(text: str) -> str:
    """Lower case, without accents or ordinal marks: "1º BÁSICO" → "1 basico"."""
    decomposed = unicodedata.normalize("NFKD", text.lower().translate(_MARKS))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    """Folded words and numbers, without the words every passage has."""
    return [t for t in _TOKEN.findall(fold(text)) if t not in _STOP]


def norm(text: str) -> str:
    """Case, accents, ordinals, whitespace, curly quotes and dashes folded."""
    return " ".join(fold(text.translate(_QUOTES)).split())


def canonical_path(path_or_url: str) -> str:
    """``https://saintgeorge.cl/Admision/Admision/?a=1#b`` → ``/admision/admision``."""
    raw = path_or_url.strip()
    parts = urlsplit(raw if "://" in raw else f"https://x{'' if raw.startswith('/') else '/'}{raw}")
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/").lower()
    return path or "/"


def canonical_url(url: str) -> str:
    """A URL without its fragment or trailing slash, with its host lower-cased."""
    parts = urlsplit(url.strip())
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/")
    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.scheme or 'https'}://{parts.netloc.lower()}{path}{query}"


def is_link_url(url: str) -> bool:
    """Whether ``url`` is https on a host the site itself links to."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    if parts.scheme != "https":
        return False
    return any(host == h or host.endswith(f".{h}") for h in LINK_HOSTS)


# ─── The layers ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Topic:
    id: str
    title: str
    text: str


@dataclass(frozen=True)
class Faq:
    """An accordion on a page: its button's words, and what opens under it."""

    q: str
    a: str


@dataclass(frozen=True)
class Section:
    heading: str
    text: str = ""


@dataclass(frozen=True)
class Card:
    """A card on a page: a unit, a newsletter issue, a person."""

    title: str
    text: str = ""
    href: str = ""


@dataclass(frozen=True)
class Link:
    """A link that leaves the page: a document, the tickets, a portal. Its
    button's words, where it goes, and what it sits under."""

    label: str
    url: str
    near: str = ""


@dataclass(frozen=True)
class Page:
    path: str
    title: str
    description: str = ""
    kind: str = "page"
    sections: tuple[Section, ...] = ()
    faqs: tuple[Faq, ...] = ()
    cards: tuple[Card, ...] = ()
    links: tuple[Link, ...] = ()
    text: str = ""

    @property
    def headings(self) -> tuple[str, ...]:
        return tuple(s.heading for s in self.sections if s.heading)


@dataclass(frozen=True)
class Hit:
    """One search result: a page section, a card, an accordion or a link."""

    kind: str
    """``page``, ``card``, ``faq`` or ``link``."""
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
        q = tokens(query)
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
    _site: _Index = field(default_factory=_Index, repr=False)

    def __post_init__(self) -> None:
        # Indexed once, here: a search runs while the visitor waits.
        for p in self.pages.values():
            self._site.add(Hit("page", p.title, "", 0, path=p.path), f"{p.title}\n{p.description}")
            for s in p.sections:
                self._site.add(
                    Hit("page", p.title, "", 0, path=p.path, section=s.heading or None),
                    f"{s.heading}\n{s.text}",
                )
            if not p.sections and p.text:
                self._site.add(Hit("page", p.title, "", 0, path=p.path), p.text)
            for card in p.cards:
                self._site.add(
                    Hit("card", card.title, "", 0, path=p.path), f"{card.title}\n{card.text}"
                )
            for faq in p.faqs:
                # An accordion's body is mostly names in a table: its button's
                # words find it, the names are not what anyone searches for.
                self._site.add(Hit("faq", faq.q, "", 0, path=p.path), f"{faq.q}\n{faq.a[:300]}")
            for link in p.links:
                self._site.add(
                    Hit("link", link.label, "", 0, path=p.path), f"{link.label}\n{link.near}"
                )
        self._site.done()

    # ── Lookups ──

    def page(self, path_or_url: str) -> Page | None:
        return self.pages.get(canonical_path(path_or_url))

    def links(self) -> list[tuple[str, Link]]:
        """Every link out the crawl saw, with the page it is on."""
        return [(p.path, link) for p in self.pages.values() for link in p.links]

    def link_urls(self) -> set[str]:
        """Every link the site gives, by its canonical URL."""
        return {canonical_url(link.url) for _, link in self.links()}

    def search(self, query: str, limit: int = 6) -> list[Hit]:
        """The site's pages, sections, cards, accordions and links."""
        return self._site.search(query, limit)


# ─── Loading ───────────────────────────────────────────────────────────────────


def _read_json(path: Path) -> list[dict[str, Any]]:
    """A list of objects (a JSON array, or one object per line), or a dict of
    them keyed by path; anything else is empty."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("saintgeorge: {} not loaded: {}", path.name, exc)
        return []
    try:
        data: Any = json.loads(raw)
    except ValueError:
        # One record per line, as the crawl writes them.
        data = []
        for line in raw.splitlines():
            line = line.strip().rstrip(",")
            if not line or line in "[]":
                continue
            try:
                data.append(json.loads(line))
            except ValueError:
                continue
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


def _dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], v) for v in cast(list[Any], value) if isinstance(v, dict)]


def _topic(path: Path) -> Topic:
    text = path.read_text(encoding="utf-8")
    first = text.lstrip().splitlines()[0] if text.strip() else ""
    title = first.lstrip("# ").strip() if first.startswith("#") else path.stem
    return Topic(path.stem, title, redact_live(text))


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
    if items := _strs(raw.get("items")):
        body = f"{body} {'; '.join(items)}".strip()
    return Section(heading, redact_live(body))


def _links(raw: dict[str, Any]) -> tuple[Link, ...]:
    """The page's links out, under whichever name the crawl gave them:
    ``tickets`` (Santander Arena's shape), ``documents``, ``links``."""
    out: list[Link] = []
    seen: set[str] = set()
    for key in ("tickets", "documents", "links", "external"):
        for t in _dicts(raw.get(key)):
            url = _str(t.get("url") or t.get("href"))
            if not url or url in seen:
                continue
            seen.add(url)
            label = _str(t.get("label") or t.get("title") or t.get("text"))
            out.append(Link(label, url, _str(t.get("near") or t.get("group"))))
    return tuple(out)


def _page(raw: dict[str, Any]) -> Page | None:
    path = raw.get("path") or raw.get("url")
    if not isinstance(path, str) or raw.get("empty") is True:
        return None
    sections = tuple(s for r in cast(list[Any], raw.get("sections") or []) if (s := _section(r)))
    if not sections and (heads := _strs(raw.get("headings"))):
        sections = tuple(Section(h) for h in heads)
    faqs = tuple(
        Faq(q, redact_live(_str(f.get("a") or f.get("answer"))))
        for f in _dicts(raw.get("faqs") or raw.get("accordions"))
        if (q := _str(f.get("q") or f.get("question") or f.get("label")))
    )
    cards = tuple(
        Card(t, _str(c.get("text")), _str(c.get("href")))
        for c in _dicts(raw.get("cards"))
        if (t := _str(c.get("title")))
    )
    return Page(
        path=canonical_path(path),
        title=_str(raw.get("title")) or path,
        description=_str(raw.get("description")),
        kind=_str(raw.get("kind")) or "page",
        sections=sections,
        faqs=faqs,
        cards=cards,
        links=_links(raw),
        text=redact_live(_str(raw.get("text"))),
    )


def load(root: Path = ROOT) -> Knowledge:
    """Every layer under ``root``; whatever is missing is empty."""
    try:
        l1 = redact_live((root / "L1.md").read_text(encoding="utf-8").strip()) or _L1_FALLBACK
    except OSError:
        logger.warning("saintgeorge: L1.md not found; Javier runs on the fallback")
        l1 = _L1_FALLBACK
    topics: dict[str, Topic] = {}
    for path in sorted((root / "L2").glob("*.md")) if (root / "L2").is_dir() else []:
        topics[path.stem] = _topic(path)
    pages = {p.path: p for raw in _read_json(root / "L3" / "pages.json") if (p := _page(raw))}
    return Knowledge(l1, topics, pages)


KNOWLEDGE = load()
"""The committed knowledge. Read through the module at session start, so a test
can put a fixture in its place."""

#: The topic names ``read_topic`` offers, fixed at import because they become a
#: ``Literal`` in its schema. A ``Literal`` cannot be empty.
TOPIC_IDS: tuple[str, ...] = tuple(KNOWLEDGE.topics) or ("admissions",)

__all__ = [
    "KNOWLEDGE",
    "LINK_HOSTS",
    "SITE",
    "SITE_HOST",
    "TOPIC_IDS",
    "Card",
    "Faq",
    "Hit",
    "Knowledge",
    "Link",
    "Page",
    "Section",
    "Topic",
    "canonical_path",
    "canonical_url",
    "fold",
    "is_link_url",
    "load",
    "norm",
    "redact_fees",
    "redact_live",
    "tokens",
]
