"""What Javier knows about Figurella Chile, in three layers, read once at import.

- **L1** (``knowledge/L1.md``) is always in his prompt: what Figurella is, the
  method, the five plans, the FAQ, the success stories, the agreements, the
  seven branches, the booking form, franchises, the blog, and — first — what
  the site does not say (no prices, no plan durations, the written guarantee's
  terms unpublished).
- **L2** (``knowledge/L2/<topic>.md``) is a topic he reads with ``read_topic``
  when a question needs more than L1. Each file opens with ``# Title`` and a
  ``Sources:`` line.
- **L3** (``knowledge/L3/``) is the site itself, built by
  ``knowledge/build.py`` from the live pages: ``pages.json`` (every page's
  places with the words they show, the FAQ's answers, the blog's posts), which
  ``search_site`` searches; ``anchors.json``, the catalogue of places a move
  can target, which the brain checks every cue against and the extension
  bundles to find them; ``branches.json`` and ``convenios.json``.

The files are built offline and committed. Every one of them may be missing or
empty and this module still imports: the demos backend serves every brain from
one process, and one brain that cannot import takes the others down with it.
The brain itself never fetches the site: it runs where the site does not
answer.

The site is in Spanish and the visitor may ask in English, so every comparison
here folds case and accents: "Colon" is "Colón".
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

SITE_HOST = "figurella.cl"
SITE = f"https://{SITE_HOST}"

_L1_FALLBACK = (
    "Figurella Chile's website is figurella.cl. Nothing more is loaded: answer only from "
    "what you read with your tools and what the screen shows."
)

# ─── Text ──────────────────────────────────────────────────────────────────────

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
_STOP = frozenset(
    # English and Spanish words every passage has.
    """a an and are as at be by can do does for from has have how i in is it its me my of on
    or the to what which with you your el la los las un una unos unas de del y o en por para
    con que se su sus es al lo como mas tu te mi""".split()  # noqa: SIM905
)
_QUOTES = str.maketrans(
    {chr(0x2018): "'", chr(0x2019): "'", chr(0x201C): '"', chr(0x201D): '"'}
    | {chr(0x2013): "-", chr(0x2014): "-", chr(0x00AB): '"', chr(0x00BB): '"'}
)


def fold(text: str) -> str:
    """Lower case, without accents: "Colón" → "colon"."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    """Folded words and numbers, without the words every passage has."""
    return [t for t in _TOKEN.findall(fold(text)) if t not in _STOP]


def norm(text: str) -> str:
    """Case, accents, whitespace, curly quotes and dashes folded."""
    return " ".join(fold(text.translate(_QUOTES)).split())


def canonical_path(path_or_url: str) -> str:
    """``https://figurella.cl/Planes?a=1#b`` → ``/planes/``: the site's own
    shape, with its trailing slash, lower case."""
    raw = path_or_url.strip()
    parts = urlsplit(raw if "://" in raw else f"https://x{'' if raw.startswith('/') else '/'}{raw}")
    path = re.sub(r"/{2,}", "/", parts.path).lower().strip("/")
    return f"/{path}/" if path else "/"


# ─── The layers ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Topic:
    id: str
    title: str
    text: str


@dataclass(frozen=True)
class Faq:
    """A question of the FAQ's accordion: its words, its key, its answer."""

    q: str
    key: str
    a: str = ""


@dataclass(frozen=True)
class Section:
    """A place on a page: the catalogue's key, its label, the words it shows."""

    key: str
    heading: str
    text: str = ""


@dataclass(frozen=True)
class Page:
    path: str
    title: str
    kind: str = "page"
    sections: tuple[Section, ...] = ()
    faqs: tuple[Faq, ...] = ()
    text: str = ""
    date: str = ""

    @property
    def headings(self) -> tuple[str, ...]:
        return tuple(s.heading for s in self.sections if s.heading)

    def section(self, key: str) -> Section | None:
        return next((s for s in self.sections if s.key == key), None)


@dataclass(frozen=True)
class Anchor:
    """A place a move can target: its key, its label, whether the model is
    offered it (``hidden`` ones are the adapter's own: a button, a field)."""

    key: str
    label: str
    hidden: bool = False


@dataclass(frozen=True)
class Branch:
    key: str
    name: str
    address: str
    phone: str
    hours: tuple[str, ...]
    maps: str
    form_value: str
    anchor: str
    whatsapp: str = ""
    note: str = ""


@dataclass(frozen=True)
class Convenio:
    key: str
    partner: str
    anchor: str
    discount: str
    text: str


@dataclass(frozen=True)
class Hit:
    """One search result: a place on a page, an FAQ answer, or a blog post."""

    kind: str
    """``page``, ``faq`` or ``post``."""
    title: str
    snippet: str
    score: float
    path: str | None = None
    section: str | None = None
    """The catalogue key of the place, for a cue."""


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
    anchors: dict[str, tuple[Anchor, ...]] = field(default_factory=dict[str, tuple[Anchor, ...]])
    """Per path, the places a move can target there (the page's own, then the
    footer's where the page has it); posts take the post template's."""
    post_anchors: tuple[Anchor, ...] = ()
    branches: tuple[Branch, ...] = ()
    convenios: tuple[Convenio, ...] = ()
    _site: _Index = field(default_factory=_Index, repr=False)

    def __post_init__(self) -> None:
        # Indexed once, here: a search runs while the visitor waits.
        for p in self.pages.values():
            kind = "post" if p.kind == "post" else "page"
            self._site.add(Hit(kind, p.title, "", 0, path=p.path), f"{p.title}\n{p.text}")
            for s in p.sections:
                self._site.add(
                    Hit(kind, p.title, "", 0, path=p.path, section=s.key),
                    f"{s.heading}\n{s.text}",
                )
            for faq in p.faqs:
                self._site.add(
                    Hit("faq", faq.q, "", 0, path=p.path, section=faq.key), f"{faq.q}\n{faq.a}"
                )
        self._site.done()

    # ── Lookups ──

    def page(self, path_or_url: str) -> Page | None:
        return self.pages.get(canonical_path(path_or_url))

    def anchors_on(self, path: str) -> tuple[Anchor, ...]:
        """The places a move can target on ``path``; a post's are the template's."""
        path = canonical_path(path)
        if path in self.anchors:
            return self.anchors[path]
        page = self.pages.get(path)
        return self.post_anchors if page is not None and page.kind == "post" else ()

    def faqs(self) -> tuple[Faq, ...]:
        return tuple(f for p in self.pages.values() for f in p.faqs)

    def branch(self, key: str) -> Branch | None:
        want = norm(key).replace(" ", "_")
        return next((b for b in self.branches if b.key == want or norm(b.name) == norm(key)), None)

    def search(self, query: str, limit: int = 6) -> list[Hit]:
        """The site's pages, places, FAQ answers and blog posts."""
        return self._site.search(query, limit)


# ─── Loading ───────────────────────────────────────────────────────────────────


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("figurella: {} not loaded: {}", path.name, exc)
        return None


def _dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], v) for v in cast(list[Any], value) if isinstance(v, dict)]


def _str(value: Any) -> str:
    return " ".join(str(value).split()) if isinstance(value, str | int | float) else ""


def _topic(path: Path) -> Topic:
    text = path.read_text(encoding="utf-8")
    first = text.lstrip().splitlines()[0] if text.strip() else ""
    title = first.lstrip("# ").strip() if first.startswith("#") else path.stem
    return Topic(path.stem, title, text)


def _page(raw: dict[str, Any]) -> Page | None:
    path = raw.get("path")
    if not isinstance(path, str):
        return None
    sections = tuple(
        Section(key, _str(s.get("heading")), str(s.get("text") or "").strip())
        for s in _dicts(raw.get("sections"))
        if (key := _str(s.get("key")))
    )
    faqs = tuple(
        Faq(q, _str(f.get("key")) or q, _str(f.get("a")))
        for f in _dicts(raw.get("faqs"))
        if (q := _str(f.get("q")))
    )
    return Page(
        path=canonical_path(path),
        title=_str(raw.get("title")) or path,
        kind=_str(raw.get("kind")) or "page",
        sections=sections,
        faqs=faqs,
        text=_str(raw.get("text")),
        date=_str(raw.get("date")),
    )


def _anchors(rows: Any) -> tuple[Anchor, ...]:
    return tuple(
        Anchor(key, _str(a.get("label")), bool(a.get("hidden")))
        for a in _dicts(rows)
        if (key := _str(a.get("key")))
    )


def load(root: Path = ROOT) -> Knowledge:
    """Every layer under ``root``; whatever is missing is empty."""
    try:
        l1 = (root / "L1.md").read_text(encoding="utf-8").strip() or _L1_FALLBACK
    except OSError:
        logger.warning("figurella: L1.md not found; Javier runs on the fallback")
        l1 = _L1_FALLBACK
    topics: dict[str, Topic] = {}
    for path in sorted((root / "L2").glob("*.md")) if (root / "L2").is_dir() else []:
        topics[path.stem] = _topic(path)
    pages = {p.path: p for raw in _dicts(_read(root / "L3" / "pages.json")) if (p := _page(raw))}
    cat = _read(root / "L3" / "anchors.json")
    cat = cast(dict[str, Any], cat) if isinstance(cat, dict) else {}
    footer = _anchors(cat.get("footer"))
    anchors: dict[str, tuple[Anchor, ...]] = {}
    raw_pages = cat.get("pages")
    for path, entry in cast(
        dict[str, Any], raw_pages if isinstance(raw_pages, dict) else {}
    ).items():
        if not isinstance(entry, dict):
            continue
        entry = cast(dict[str, Any], entry)
        own = _anchors(entry.get("anchors"))
        anchors[canonical_path(path)] = own + (footer if entry.get("footer") else ())
    post = _anchors(cat.get("post")) + footer
    branches = tuple(
        Branch(
            key=_str(b.get("key")),
            name=_str(b.get("name")),
            address=_str(b.get("address")),
            phone=_str(b.get("phone")),
            hours=tuple(_str(h) for h in cast(list[Any], b.get("hours") or []) if _str(h)),
            maps=_str(b.get("maps")),
            form_value=_str(b.get("form_value")),
            anchor=_str(b.get("anchor")),
            whatsapp=_str(b.get("whatsapp")),
            note=_str(b.get("note")),
        )
        for b in _dicts(_read(root / "L3" / "branches.json"))
        if _str(b.get("key"))
    )
    convenios = tuple(
        Convenio(
            key=_str(c.get("key")),
            partner=_str(c.get("partner")),
            anchor=_str(c.get("anchor")),
            discount=_str(c.get("discount")),
            text=_str(c.get("text")),
        )
        for c in _dicts(_read(root / "L3" / "convenios.json"))
        if _str(c.get("key"))
    )
    return Knowledge(l1, topics, pages, anchors, post, branches, convenios)


KNOWLEDGE = load()
"""The committed knowledge. Read through the module at session start, so a test
can put a fixture in its place."""

#: The topic names ``read_topic`` offers, fixed at import because they become a
#: ``Literal`` in its schema. A ``Literal`` cannot be empty.
TOPIC_IDS: tuple[str, ...] = tuple(KNOWLEDGE.topics) or ("consejos",)

__all__ = [
    "KNOWLEDGE",
    "SITE",
    "SITE_HOST",
    "TOPIC_IDS",
    "Anchor",
    "Branch",
    "Convenio",
    "Faq",
    "Hit",
    "Knowledge",
    "Page",
    "Section",
    "Topic",
    "canonical_path",
    "fold",
    "load",
    "norm",
    "tokens",
]
