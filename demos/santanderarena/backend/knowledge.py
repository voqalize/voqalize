"""What Javier knows about Santander Arena, in three layers, read once at import.

- **L1** (``knowledge/L1.md``) is always in his prompt: what the arena is, what
  is on, the premium experiences, the fan spaces, food and drink, getting there,
  tickets, and the site's navigation.
- **L2** (``knowledge/L2/<topic>.md``) is a topic he reads with ``read_topic``
  when a question needs more than L1. Each file opens with ``# Title`` and a
  ``Sources:`` line.
- **L3** (``knowledge/L3/pages.json``, ``events.json``) is the site itself —
  every page's sections, cards, FAQs and ticket links, and every event on the
  billboard — which ``search_site`` and ``find_events`` search and which the
  brain checks every move against: a path he navigates to, a section he
  scrolls to, a ticket link he opens.

The files are built offline (``knowledge/build.py``) and committed. Every one of
them may be missing or empty and this module still imports: the demos backend
serves every brain from one process, and one brain that cannot import takes the
others down with it.

The site is in Spanish and the visitor may ask in English, so every comparison
here folds case and accents: "cupula" is "Cúpula".
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from loguru import logger

ROOT = Path(__file__).parent / "knowledge"

SITE_HOST = "www.santanderarena.cl"
SITE = f"https://{SITE_HOST}"
#: Where the site sends a visitor to buy or book: tickets, parking and VIP
#: experiences on Puntoticket, and private events on the arena's reservations
#: site, which still carries the arena's old name.
TICKET_HOSTS = ("puntoticket.com", "reservas.movistararena.cl")

_L1_FALLBACK = (
    "Santander Arena's website is www.santanderarena.cl. Nothing more is loaded: "
    "answer only from what you read with your tools."
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


#: The site writes some apostrophes as an acute accent (U+00B4), as in its Jack
#: Daniel bar; they read as the plain apostrophe.
_APOSTROPHES = str.maketrans({chr(0x00B4): "'", chr(0x2019): "'", chr(0x0060): "'"})


def fold(text: str) -> str:
    """Lower case, without accents: "Cúpula Ñandú" → "cupula nandu"."""
    decomposed = unicodedata.normalize("NFKD", text.lower().translate(_APOSTROPHES))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    """Folded words and numbers, without the words every passage has."""
    return [t for t in _TOKEN.findall(fold(text)) if t not in _STOP]


def norm(text: str) -> str:
    """Case, accents, whitespace, curly quotes and dashes folded."""
    return " ".join(fold(text.translate(_QUOTES)).split())


def canonical_path(path_or_url: str) -> str:
    """``https://www.santanderarena.cl/Bares/?a=1#b`` → ``/bares``."""
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


def is_ticket_url(url: str) -> bool:
    """Whether ``url`` is on a site the arena sends visitors to buy on."""
    host = urlsplit(url.strip()).netloc.lower()
    return any(host == h or host.endswith(f".{h}") for h in TICKET_HOSTS)


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


@dataclass(frozen=True)
class Card:
    """A card on a page: an event, a bar, an experience, a piece of news."""

    title: str
    text: str = ""
    href: str = ""


@dataclass(frozen=True)
class Ticket:
    """A link that leaves the site to buy: its button, where it goes, and the
    card or page it sits on."""

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
    tickets: tuple[Ticket, ...] = ()
    text: str = ""

    @property
    def headings(self) -> tuple[str, ...]:
        return tuple(s.heading for s in self.sections if s.heading)


@dataclass(frozen=True)
class Event:
    """One show on the billboard, as its own page lists it."""

    name: str
    path: str
    category: str = ""
    date_text: str = ""
    time_text: str = ""
    date: str = ""
    """ISO, ``2026-11-05``; empty when the page gives none."""
    time: str = ""
    summary: str = ""
    description: str = ""
    tickets_url: str = ""
    parking_url: str = ""
    vip_url: str = ""

    @property
    def when(self) -> str:
        return " / ".join(x for x in (self.date_text, self.time_text) if x) or self.date


@dataclass(frozen=True)
class Hit:
    """One search result: a page section, a card, an FAQ or an event."""

    kind: str
    """``page``, ``card``, ``faq`` or ``event``."""
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
    events: dict[str, Event] = field(default_factory=dict[str, Event])
    _site: _Index = field(default_factory=_Index, repr=False)
    _events: _Index = field(default_factory=_Index, repr=False)

    def __post_init__(self) -> None:
        # Indexed once, here: a search runs while the visitor waits.
        for p in self.pages.values():
            if p.kind == "event" and p.path in self.events:
                # A show's page repeats the same blocks as every other show's
                # ("Completa tu noche…"), which would bury the pages a search is
                # for; the show itself is in the events index.
                continue
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
                self._site.add(Hit("faq", faq.q, "", 0, path=p.path), f"{faq.q}\n{faq.a}")
        for e in self.events.values():
            about = " ".join([e.name, e.category, e.date_text, e.date, e.summary])
            self._events.add(Hit("event", e.name, "", 0, path=e.path), about, weight=3)
            self._events.add(Hit("event", e.name, "", 0, path=e.path), e.description)
        self._site.done()
        self._events.done()

    # ── Lookups ──

    def page(self, path_or_url: str) -> Page | None:
        return self.pages.get(canonical_path(path_or_url))

    def event(self, name_or_path: str) -> Event | None:
        """The event at that path, or by its name (folded, whole or begun)."""
        if (e := self.events.get(canonical_path(name_or_path))) is not None:
            return e
        want = norm(name_or_path)
        if not want:
            return None
        named = [e for e in self.events.values() if norm(e.name) == want]
        named = named or [e for e in self.events.values() if norm(e.name).startswith(want)]
        named = named or [e for e in self.events.values() if want in norm(e.name)]
        # A show the arena has played before is on the billboard twice (Luciano
        # Pereyra in 2025 and in 2026): the one still to come, soonest first.
        today = date.today().isoformat()
        named.sort(key=lambda e: (bool(e.date) and e.date < today, e.date or "9999"))
        return named[0] if named else None

    def ticket_urls(self) -> set[str]:
        """Every link the site gives to buy something, by its canonical URL."""
        urls = {canonical_url(t.url) for p in self.pages.values() for t in p.tickets}
        for e in self.events.values():
            urls |= {canonical_url(u) for u in (e.tickets_url, e.parking_url, e.vip_url) if u}
        return urls

    def search(self, query: str, limit: int = 6) -> list[Hit]:
        """The site's pages, sections, cards and FAQs."""
        return self._site.search(query, limit)

    def find_events(self, query: str, limit: int = 6) -> list[Hit]:
        """Events on the billboard, best first, one hit per event."""
        return self._events.search(query, limit)


# ─── Loading ───────────────────────────────────────────────────────────────────


def _read_json(path: Path) -> list[dict[str, Any]]:
    """A list of objects, or a dict of them keyed by path; anything else is empty."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("santanderarena: {} not loaded: {}", path.name, exc)
        return []
    if isinstance(data, dict):
        data = cast(dict[str, Any], data)
        inner = data.get("pages") or data.get("events")
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
    if items := _strs(raw.get("items")):
        body = f"{body} {'; '.join(items)}".strip()
    return Section(heading, body)


def _page(raw: dict[str, Any]) -> Page | None:
    path = raw.get("path") or raw.get("url")
    if not isinstance(path, str):
        return None
    sections = tuple(s for r in cast(list[Any], raw.get("sections") or []) if (s := _section(r)))
    if not sections and (heads := _strs(raw.get("headings"))):
        sections = tuple(Section(h) for h in heads)
    faqs = tuple(
        Faq(q, _str(f.get("a") or f.get("answer")))
        for f in _dicts(raw.get("faqs"))
        if (q := _str(f.get("q") or f.get("question")))
    )
    cards = tuple(
        Card(t, _str(c.get("text")), _str(c.get("href")))
        for c in _dicts(raw.get("cards"))
        if (t := _str(c.get("title")))
    )
    tickets = tuple(
        Ticket(_str(t.get("label")), u, _str(t.get("near")))
        for t in _dicts(raw.get("tickets"))
        if (u := _str(t.get("url")))
    )
    return Page(
        path=canonical_path(path),
        title=_str(raw.get("title")) or path,
        description=_str(raw.get("description")),
        kind=_str(raw.get("kind")) or "page",
        sections=sections,
        faqs=faqs,
        cards=cards,
        tickets=tickets,
        text=_str(raw.get("text")),
    )


def _event(raw: dict[str, Any]) -> Event | None:
    path = raw.get("path") or raw.get("url")
    if not isinstance(path, str) or not (name := _str(raw.get("name") or raw.get("title"))):
        return None
    return Event(
        name=name,
        path=canonical_path(path),
        category=_str(raw.get("category")),
        date_text=_str(raw.get("date_text")),
        time_text=_str(raw.get("time_text")),
        date=_str(raw.get("date")),
        time=_str(raw.get("time")),
        summary=_str(raw.get("summary")),
        description=_str(raw.get("description")),
        tickets_url=_str(raw.get("tickets_url")),
        parking_url=_str(raw.get("parking_url")),
        vip_url=_str(raw.get("vip_url")),
    )


def load(root: Path = ROOT) -> Knowledge:
    """Every layer under ``root``; whatever is missing is empty."""
    try:
        l1 = (root / "L1.md").read_text(encoding="utf-8").strip() or _L1_FALLBACK
    except OSError:
        logger.warning("santanderarena: L1.md not found; Javier runs on the fallback")
        l1 = _L1_FALLBACK
    topics: dict[str, Topic] = {}
    for path in sorted((root / "L2").glob("*.md")) if (root / "L2").is_dir() else []:
        topics[path.stem] = _topic(path)
    pages = {p.path: p for raw in _read_json(root / "L3" / "pages.json") if (p := _page(raw))}
    events = {e.path: e for raw in _read_json(root / "L3" / "events.json") if (e := _event(raw))}
    return Knowledge(l1, topics, pages, events)


KNOWLEDGE = load()
"""The committed knowledge. Read through the module at session start, so a test
can put a fixture in its place."""

#: The topic names ``read_topic`` offers, fixed at import because they become a
#: ``Literal`` in its schema. A ``Literal`` cannot be empty.
TOPIC_IDS: tuple[str, ...] = tuple(KNOWLEDGE.topics) or ("events-and-tickets",)

__all__ = [
    "KNOWLEDGE",
    "SITE",
    "SITE_HOST",
    "TOPIC_IDS",
    "Card",
    "Event",
    "Faq",
    "Hit",
    "Knowledge",
    "Page",
    "Section",
    "Ticket",
    "Topic",
    "canonical_path",
    "canonical_url",
    "fold",
    "is_ticket_url",
    "load",
    "norm",
    "tokens",
]
