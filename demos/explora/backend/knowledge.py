"""What Javier knows about Explora, in three layers, read once at import.

- **L1** (``knowledge/L1.md``) is always in his prompt: what Explora is, its
  lodges and expeditions in brief, what a stay includes, how to book.
- **L2** (``knowledge/L2/<topic>.md``) is a topic he reads with ``read_topic``
  when a question needs more than L1. Each file opens with ``# Title`` and a
  ``Sources:`` line.
- **L3** (``knowledge/L3/*.json``) is the site itself — every crawled page's
  sections, accordions and tabs, the lodges with their own sub-pages, and the
  reservations site's hotels and nationalities — which ``search_site``
  searches and which the brain checks every move against: a path he opens, a
  section he scrolls to, a lodge he checks availability for.

The files are built offline (``knowledge/build_main.py``,
``knowledge/build_lodges.py``) and committed. Every one of them may be missing
or empty and this module still imports: the demos backend serves every brain
from one process, and one brain that cannot import takes the others down with
it.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from loguru import logger

ROOT = Path(__file__).parent / "knowledge"

#: The two hosts: the WordPress site, and the booking engine beside it.
SITE_HOST = "www.explora.com"
RESERVATIONS_HOST = "reservations.explora.com"

_L1_FALLBACK = (
    "Explora's website is www.explora.com, and its booking site is "
    "reservations.explora.com. Nothing more is loaded: answer only from what you "
    "read with your tools."
)
#: The L3 files that are not pages.
_NOT_PAGES = frozenset({"reservations.json"})


# ─── Text ──────────────────────────────────────────────────────────────────────

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
_STOP = frozenset(
    "a an and are as at be by can do does for from has have how "  # noqa: SIM905
    "i in is it its me my of on or the to what which with you your".split()
)
#: Curly quotes and dashes, folded to their plain forms (by code point: they look alike).
_QUOTES = str.maketrans(
    {chr(0x2018): "'", chr(0x2019): "'", chr(0x201C): '"', chr(0x201D): '"'}
    | {chr(0x2013): "-", chr(0x2014): "-"}
)
#: Accents folded away for matching: "Chaltén" is "chalten".
_ACCENTS = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")


def tokens(text: str) -> list[str]:
    """Lower-cased words and numbers, without the words every passage has."""
    return [t for t in _TOKEN.findall(text.translate(_ACCENTS).lower()) if t not in _STOP]


def norm(text: str) -> str:
    """Case, whitespace, accents, curly quotes and dashes folded."""
    return " ".join(text.translate(_QUOTES).translate(_ACCENTS).lower().split())


def canonical_path(path_or_url: str) -> str:
    """``https://www.explora.com/Lodge/Atacama-Lodge/?a=1#b`` → ``/lodge/atacama-lodge``."""
    raw = path_or_url.strip()
    parts = urlsplit(raw if "://" in raw else f"https://x{'' if raw.startswith('/') else '/'}{raw}")
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/").lower()
    return path or "/"


def site_path(path: str) -> str:
    """The path as the site links it: with its trailing slash."""
    return "/" if path == "/" else f"{path}/"


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
class Page:
    path: str
    title: str
    description: str = ""
    kind: str = "other"
    """home, destination, lodge, expedition, experience, offer, about, post or other."""
    sections: tuple[Section, ...] = ()
    faqs: tuple[Faq, ...] = ()
    tabs: tuple[str, ...] = ()
    """The labels of the page's in-page tabs and accordions."""
    text: str = ""

    @property
    def headings(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(s.heading for s in self.sections if s.heading))


@dataclass(frozen=True)
class Hotel:
    """One choice in the reservations site's hotel list."""

    code: str
    label: str
    group: str = ""
    flow: str = "booking"
    """``booking`` (dates, nights, then rooms) or ``enquiry`` (an expedition's form)."""


@dataclass(frozen=True)
class Hit:
    """One search result: a section of a page, or an FAQ on a page."""

    kind: str
    """``page`` or ``faq``."""
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
        best: dict[tuple[str, str | None, str | None], Hit] = {}
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
            key = (h.kind, h.path, h.section if h.kind == "page" else h.title)
            hit = Hit(h.kind, h.title, snippet, round(s, 2), h.path, h.section)
            if key not in best or best[key].score < hit.score:
                best[key] = hit
        return sorted(best.values(), key=lambda h: -h.score)[:limit]


@dataclass
class Knowledge:
    l1: str
    topics: dict[str, Topic]
    pages: dict[str, Page]
    hotels: tuple[Hotel, ...] = ()
    #: The reservations form's nationality list, as (code, label).
    countries: tuple[tuple[str, str], ...] = ()
    #: A path the site redirects, to the page it lands on.
    redirects: dict[str, str] = field(default_factory=dict[str, str])
    _site: _Index = field(default_factory=_Index, repr=False)

    def __post_init__(self) -> None:
        # Indexed once, here: a search runs while the visitor waits.
        for p in self.pages.values():
            self._site.add(
                Hit("page", p.title, "", 0, path=p.path), f"{p.title}\n{p.description}", weight=2
            )
            for s in p.sections:
                self._site.add(
                    Hit("page", p.title, "", 0, path=p.path, section=s.heading or None),
                    f"{s.heading}\n{s.text}",
                )
            if not p.sections and p.text:
                self._site.add(Hit("page", p.title, "", 0, path=p.path), p.text)
            for faq in p.faqs:
                self._site.add(Hit("faq", faq.q, "", 0, path=p.path), f"{faq.q}\n{faq.a}")
        self._site.done()

    # ── Lookups ──

    def page(self, path_or_url: str) -> Page | None:
        path = canonical_path(path_or_url)
        return self.pages.get(path) or self.pages.get(self.redirects.get(path, ""))

    def hotel(self, code_or_name: str) -> Hotel | None:
        """A hotel by its code ("EATA") or by words of its label ("Atacama")."""
        want = norm(code_or_name)
        for h in self.hotels:
            if h.code.lower() == want:
                return h
        for h in self.hotels:
            if want and want in norm(h.label):
                return h
        return None

    def country(self, name_or_code: str) -> tuple[str, str] | None:
        """The nationality the reservations form lists, by its name or code."""
        want = norm(name_or_code)
        if not want:
            return None
        for test in (
            lambda c, label: c.lower() == want,
            lambda c, label: norm(label) == want,
            lambda c, label: norm(label).startswith(want),
            lambda c, label: want in norm(label),
        ):
            for code, label in self.countries:
                if code and test(code, label):
                    return code, label
        return None

    def search(self, query: str, limit: int = 6) -> list[Hit]:
        """The site's pages, sections and FAQs."""
        return self._site.search(query, limit)


# ─── Loading ───────────────────────────────────────────────────────────────────


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("explora: {} not loaded: {}", path.name, exc)
        return None


def _dicts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = cast(dict[str, Any], value).get("pages") or []
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], d) for d in cast(list[Any], value) if isinstance(d, dict)]


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


def _topic(path: Path) -> Topic:
    text = path.read_text(encoding="utf-8")
    first = text.lstrip().splitlines()[0] if text.strip() else ""
    title = first.lstrip("# ").strip() if first.startswith("#") else path.stem
    return Topic(path.stem, title, text)


def _sections(raw: Any) -> list[Section]:
    out: list[Section] = []
    for r in cast(list[Any], raw or []):
        if not isinstance(r, dict):
            continue
        r = cast(dict[str, Any], r)
        heading = _str(r.get("heading") or r.get("label") or r.get("title"))
        body = _str(r.get("text"))
        if items := _strs(r.get("items")):
            body = f"{body} {'; '.join(items)}".strip()
        if heading or body:
            out.append(Section(heading, body))
    return out


def _faqs(raw: Any) -> list[Faq]:
    out: list[Faq] = []
    for r in cast(list[Any], raw or []):
        if isinstance(r, dict):
            r = cast(dict[str, Any], r)
            if q := _str(r.get("q") or r.get("question")):
                out.append(Faq(q, _str(r.get("a") or r.get("answer"))))
    return out


def _page(raw: dict[str, Any]) -> Page | None:
    """One crawled page. A lodge record also carries its sub-pages' sections
    (``tabs`` with a ``url``), its rooms and its explorations, which are folded
    into it as sections so they are searchable on the page that has them."""
    path = raw.get("path") or raw.get("url")
    if not isinstance(path, str):
        return None
    sections = _sections(raw.get("sections"))
    tabs: list[str] = []
    for t in cast(list[Any], raw.get("tabs") or []):
        if not isinstance(t, dict):
            continue
        t = cast(dict[str, Any], t)
        labels = _strs(t.get("labels")) or ((_str(t.get("label")),) if t.get("label") else ())
        tabs.extend(labels)
        # A tab that is the page's own pane: its text is on this page.
        if _str(t.get("mechanism")) in ("", "inpage", "anchor"):
            sections.extend(_sections(t.get("sections")))
            for pane in cast(list[Any], t.get("panes") or []):
                if isinstance(pane, dict):
                    pane = cast(dict[str, Any], pane)
                    sections.append(Section(_str(pane.get("label")), _str(pane.get("text"))))
    for key in ("rooms", "explorations"):
        for r in cast(list[Any], raw.get(key) or []):
            if isinstance(r, dict):
                r = cast(dict[str, Any], r)
                name = _str(r.get("name"))
                extra = " ".join(
                    _str(r.get(k)) for k in ("difficulty", "duration", "text") if r.get(k)
                )
                if name:
                    sections.append(Section("", f"{name}: {extra}".strip()))
    title = _str(raw.get("title") or raw.get("name")) or path
    return Page(
        path=canonical_path(path),
        title=title,
        description=_str(raw.get("description")),
        kind=_str(raw.get("kind")) or "other",
        sections=tuple(sections),
        faqs=tuple(dict.fromkeys(_faqs(raw.get("faqs")))),
        tabs=tuple(dict.fromkeys(t for t in tabs if t)),
        text=_str(raw.get("text")),
    )


def _merge(a: Page, b: Page) -> Page:
    """Two crawls of one page: the richer one, with the other's FAQs and tabs."""
    rich, poor = (a, b) if len(a.sections) >= len(b.sections) else (b, a)
    seen = {s.heading for s in rich.sections if s.heading}
    extra = tuple(s for s in poor.sections if s.heading and s.heading not in seen)
    return Page(
        path=rich.path,
        title=rich.title,
        description=rich.description or poor.description,
        kind=rich.kind if rich.kind != "other" else poor.kind,
        sections=rich.sections + extra,
        faqs=tuple(dict.fromkeys(rich.faqs + poor.faqs)),
        tabs=tuple(dict.fromkeys(rich.tabs + poor.tabs)),
        text=rich.text or poor.text,
    )


def load(root: Path = ROOT) -> Knowledge:
    """Every layer under ``root``; whatever is missing is empty."""
    try:
        l1 = (root / "L1.md").read_text(encoding="utf-8").strip() or _L1_FALLBACK
    except OSError:
        logger.warning("explora: L1.md not found; Javier runs on the fallback")
        l1 = _L1_FALLBACK
    topics: dict[str, Topic] = {}
    for path in sorted((root / "L2").glob("*.md")) if (root / "L2").is_dir() else []:
        topics[path.stem] = _topic(path)
    pages: dict[str, Page] = {}
    redirects: dict[str, str] = {}
    l3 = root / "L3"
    for file in sorted(l3.glob("*.json")) if l3.is_dir() else []:
        if file.name in _NOT_PAGES:
            continue
        for raw in _dicts(_read_json(file)):
            if (p := _page(raw)) is None:
                continue
            pages[p.path] = _merge(pages[p.path], p) if p.path in pages else p
            asked = raw.get("requested_path")
            if isinstance(asked, str) and canonical_path(asked) != p.path:
                redirects[canonical_path(asked)] = p.path
    hotels: list[Hotel] = []
    countries: list[tuple[str, str]] = []
    resv = _read_json(l3 / "reservations.json") if (l3 / "reservations.json").exists() else None
    if isinstance(resv, dict):
        resv = cast(dict[str, Any], resv)
        for h in _dicts(resv.get("hotels")):
            if (code := _str(h.get("value"))) and (label := _str(h.get("label"))):
                hotels.append(Hotel(code, label, _str(h.get("group")), _str(h.get("flow"))))
        for c in _dicts(resv.get("nationalities")):
            if (code := _str(c.get("value"))) and (label := _str(c.get("label"))):
                countries.append((code, label))
    return Knowledge(l1, topics, pages, tuple(hotels), tuple(countries), redirects)


KNOWLEDGE = load()
"""The committed knowledge. Read through the module at session start, so a test
can put a fixture in its place."""

#: The topic names ``read_topic`` offers, fixed at import because they become a
#: ``Literal`` in its schema. A ``Literal`` cannot be empty.
TOPIC_IDS: tuple[str, ...] = tuple(KNOWLEDGE.topics) or ("lodges",)

__all__ = [
    "KNOWLEDGE",
    "RESERVATIONS_HOST",
    "SITE_HOST",
    "TOPIC_IDS",
    "Faq",
    "Hit",
    "Hotel",
    "Knowledge",
    "Page",
    "Section",
    "Topic",
    "canonical_path",
    "load",
    "norm",
    "site_path",
    "tokens",
]
