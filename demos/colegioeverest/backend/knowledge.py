"""What Javier knows about Colegio Everest, in three layers, read once at import.

- **L1** (``knowledge/L1.md``) is always in his prompt. It opens with what the
  site does *not* say (start times, class sizes, results, open days, admission
  scholarships), then who the school is, the cycles and the age rule, admission
  2027 (its windows, the eight steps, the process fee), vacancies, the fees in
  short, English, formation, sport and facilities, the contacts, the calls to
  action and the menu.
- **L2** (``knowledge/L2/<topic>.md``) is a topic he reads with ``read_topic``
  when a question needs more than L1. Each file opens with ``# Title`` and a
  ``Sources:`` line.
- **L3** (``knowledge/L3/``) is the site itself, built by
  ``knowledge/build.py`` from the live pages and the school's PDFs:
  ``pages.json`` (every page's places with the words they show, and the latest
  news posts), which ``search_site`` searches; ``anchors.json``, the catalogue
  of places a move can target, which the brain checks every cue against and the
  extension bundles to find them; ``levels.json`` (the seventeen levels a child
  can enter in 2027, with the admission page's age rule and window, the 2027
  vacancies and the fee bands); ``documents.json`` (every PDF the site links,
  and three it serves unlinked); ``site.json`` (the menus, the footer, the calls
  to action that leave the site, the phones).

The files are built offline and committed. Every one of them may be missing or
empty and this module still imports: the demos backend serves every brain from
one process, and one brain that cannot import takes the others down with it.
The brain itself never fetches the site: it runs where the site does not
answer.

The site is in Spanish and the visitor may ask in English, so every comparison
here folds case and accents: "Kinder" is "Kínder".
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

SITE_HOST = "www.colegioeverest.cl"
SITE = f"https://{SITE_HOST}"

_L1_FALLBACK = (
    "Colegio Everest's website is www.colegioeverest.cl. Nothing more is loaded: answer only "
    "from what you read with your tools and what the screen shows."
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
    """Lower case, without accents: "Kínder" → "kinder"."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    """Folded words and numbers, without the words every passage has."""
    return [t for t in _TOKEN.findall(fold(text)) if t not in _STOP]


def norm(text: str) -> str:
    """Case, accents, whitespace, curly quotes and dashes folded."""
    return " ".join(fold(text.translate(_QUOTES)).split())


def canonical_path(path_or_url: str) -> str:
    """``https://www.colegioeverest.cl/Contacto?a=1#b`` → ``/contacto/``: the
    site's own shape, with its trailing slash, lower case."""
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
    offered it (``hidden`` ones are the adapter's own: a field, a button, a
    slider's arrow)."""

    key: str
    label: str
    hidden: bool = False


@dataclass(frozen=True)
class Level:
    """A level a child can enter in 2027, as the admission page and the
    vacancies PDF give it."""

    key: str
    name: str
    cycle: str
    age_text: str
    """The admission page's own age rule, verbatim; empty from Kínder up, where
    the site gives none."""
    min_age_months: int | None
    born_by: date | None
    """The last birth date that meets the age rule at the cut-off."""
    age_if_sequence: int | None
    """From Kínder up: the age the usual sequence would give. NOT the site's."""
    window_text: str
    opens: date | None
    closes: date | None
    place: str
    """The admission page's ``fecha_*`` card for this level's window."""
    vacancies: int | None
    priority_neep: int
    fee_band_2026: str
    fee_band_2027: str
    admission_day: str
    results: str


@dataclass(frozen=True)
class FeeBand:
    key: str
    label: str
    matricula: str
    cuota: str
    anual: str


@dataclass(frozen=True)
class Fees:
    """One year's fee table, as its PDF writes it (UF)."""

    year: str
    source: str
    linked: bool
    bands: dict[str, FeeBand]
    cuotas: int
    seguro: str
    note: str
    extras: dict[str, dict[str, str]] = field(default_factory=dict[str, dict[str, str]])
    """``bono_incorporacion`` (2026) or ``familia_numerosa`` (2027), by child."""


@dataclass(frozen=True)
class Document:
    """A PDF the school serves: its URL, the words its links carry, the pages
    that link it, and what it is (``note``) when the crawl said so."""

    url: str
    labels: tuple[str, ...]
    pages: tuple[str, ...]
    linked: bool
    file: str
    note: str = ""
    broken: bool = False
    """The site links it and the server answers 404."""

    @property
    def name(self) -> str:
        return self.note or next((x for x in self.labels if len(x) > 14), "") or self.file


@dataclass(frozen=True)
class Exit:
    """A call to action that leaves the site: the application, the visit, a
    portal. Opened in a new tab, never filled."""

    key: str
    label: str
    url: str
    note: str


@dataclass(frozen=True)
class Hit:
    """One search result: a place on a page, or a news post."""

    kind: str
    """``page`` or ``post``."""
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
    """Per path, the places a move can target there: the page's own, then the
    header's and the footer's where the page has them; posts take the post
    template's."""
    post_anchors: tuple[Anchor, ...] = ()
    levels: tuple[Level, ...] = ()
    fees: dict[str, Fees] = field(default_factory=dict[str, Fees])
    documents: tuple[Document, ...] = ()
    exits: dict[str, Exit] = field(default_factory=dict[str, Exit])
    phones: dict[str, str] = field(default_factory=dict[str, str])
    cutoff: date | None = None
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

    def level(self, key: str) -> Level | None:
        want = norm(key).replace(" ", "_")
        return next(
            (lv for lv in self.levels if lv.key == want or norm(lv.name) == norm(key)), None
        )

    def search(self, query: str, limit: int = 6) -> list[Hit]:
        """The site's pages, places and news posts."""
        return self._site.search(query, limit)


# ─── Loading ───────────────────────────────────────────────────────────────────


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("colegioeverest: {} not loaded: {}", path.name, exc)
        return None


def _dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], v) for v in cast(list[Any], value) if isinstance(v, dict)]


def _dict(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _str(value: Any) -> str:
    return " ".join(str(value).split()) if isinstance(value, str | int | float) else ""


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _topic(path: Path) -> Topic:
    text = path.read_text(encoding="utf-8")
    first = text.lstrip().splitlines()[0] if text.strip() else ""
    title = first.lstrip("# ").strip() if first.startswith("#") else path.stem
    return Topic(path.stem, title, text)


def _page(raw: dict[str, Any]) -> Page | None:
    path = raw.get("path")
    if not isinstance(path, str) or raw.get("empty") or raw.get("kind") == "unguided":
        return None
    sections = tuple(
        Section(key, _str(s.get("heading")), str(s.get("text") or "").strip())
        for s in _dicts(raw.get("sections"))
        if (key := _str(s.get("key")))
    )
    return Page(
        path=canonical_path(path),
        title=_str(raw.get("title")) or path,
        kind=_str(raw.get("kind")) or "page",
        sections=sections,
        text=_str(raw.get("text")),
        date=_str(raw.get("date")),
    )


def _anchors(rows: Any) -> tuple[Anchor, ...]:
    return tuple(
        Anchor(key, _str(a.get("label")), bool(a.get("hidden")))
        for a in _dicts(rows)
        if (key := _str(a.get("key")))
    )


def _level(raw: dict[str, Any]) -> Level | None:
    key = _str(raw.get("key"))
    if not key:
        return None
    return Level(
        key=key,
        name=_str(raw.get("name")) or key,
        cycle=_str(raw.get("cycle")),
        age_text=_str(raw.get("age_text")),
        min_age_months=_int(raw.get("min_age_months")),
        born_by=_date(raw.get("born_by")),
        age_if_sequence=_int(raw.get("age_if_sequence")),
        window_text=_str(raw.get("window_text")),
        opens=_date(raw.get("opens")),
        closes=_date(raw.get("closes")),
        place=_str(raw.get("place")),
        vacancies=_int(raw.get("vacancies")),
        priority_neep=_int(raw.get("priority_neep")) or 0,
        fee_band_2026=_str(raw.get("fee_band_2026")),
        fee_band_2027=_str(raw.get("fee_band_2027")),
        admission_day=_str(raw.get("admission_day")),
        results=_str(raw.get("results")),
    )


def _fees(year: str, raw: dict[str, Any]) -> Fees:
    bands = {
        key: FeeBand(
            key,
            _str(b.get("label")),
            _str(b.get("matricula")),
            _str(b.get("cuota")),
            _str(b.get("anual")),
        )
        for key, value in _dict(raw.get("bands")).items()
        if (b := _dict(value))
    }
    extras = {
        name: {k: _str(v) for k, v in _dict(raw.get(name)).items()}
        for name in ("bono_incorporacion", "familia_numerosa")
        if raw.get(name)
    }
    return Fees(
        year=year,
        source=_str(raw.get("source")),
        linked=bool(raw.get("linked")),
        bands=bands,
        cuotas=_int(raw.get("cuotas")) or 10,
        seguro=_str(raw.get("seguro")),
        note=_str(raw.get("note")),
        extras=extras,
    )


def _document(raw: dict[str, Any]) -> Document | None:
    url = _str(raw.get("url"))
    if not url:
        return None
    labels = tuple(_str(x) for x in cast(list[Any], raw.get("labels") or []) if _str(x))
    pages = tuple(_str(x) for x in cast(list[Any], raw.get("pages") or []) if _str(x))
    return Document(
        url=url,
        labels=labels,
        pages=pages,
        linked=bool(raw.get("linked")),
        file=_str(raw.get("file")) or url.rsplit("/", 1)[-1],
        note=_str(raw.get("note")),
        broken=raw.get("status") == 404,
    )


def load(root: Path = ROOT) -> Knowledge:
    """Every layer under ``root``; whatever is missing is empty."""
    try:
        l1 = (root / "L1.md").read_text(encoding="utf-8").strip() or _L1_FALLBACK
    except OSError:
        logger.warning("colegioeverest: L1.md not found; Javier runs on the fallback")
        l1 = _L1_FALLBACK
    topics: dict[str, Topic] = {}
    for path in sorted((root / "L2").glob("*.md")) if (root / "L2").is_dir() else []:
        topics[path.stem] = _topic(path)
    pages = {p.path: p for raw in _dicts(_read(root / "L3" / "pages.json")) if (p := _page(raw))}
    cat = _dict(_read(root / "L3" / "anchors.json"))
    header = _anchors(cat.get("header"))
    footer = _anchors(cat.get("footer"))
    anchors: dict[str, tuple[Anchor, ...]] = {}
    for path, value in _dict(cat.get("pages")).items():
        entry = _dict(value)
        own = _anchors(entry.get("anchors"))
        anchors[canonical_path(path)] = (
            own + (header if entry.get("header") else ()) + (footer if entry.get("footer") else ())
        )
    post = _anchors(cat.get("post")) + header + footer
    lv = _dict(_read(root / "L3" / "levels.json"))
    levels = tuple(x for raw in _dicts(lv.get("levels")) if (x := _level(raw)))
    fees = {year: _fees(year, _dict(raw)) for year, raw in _dict(lv.get("fees")).items()}
    cutoff = _date(_dict(lv.get("_meta")).get("cutoff"))
    documents = tuple(
        d for raw in _dicts(_read(root / "L3" / "documents.json")) if (d := _document(raw))
    )
    site = _dict(_read(root / "L3" / "site.json"))
    exits: dict[str, Exit] = {}
    for key, value in _dict(site.get("ctas")).items():
        c = _dict(value)
        urls = [u for u in cast(list[Any], c.get("urls") or []) if isinstance(u, str)]
        if urls:
            exits[key] = Exit(key, _str(c.get("label")), urls[0], _str(c.get("note")))
    phones = {k: _str(v) for k, v in _dict(site.get("phones")).items() if _str(v)}
    return Knowledge(
        l1, topics, pages, anchors, post, levels, fees, documents, exits, phones, cutoff
    )


KNOWLEDGE = load()
"""The committed knowledge. Read through the module at session start, so a test
can put a fixture in its place."""

#: The topic names ``read_topic`` offers, fixed at import because they become a
#: ``Literal`` in its schema. A ``Literal`` cannot be empty.
TOPIC_IDS: tuple[str, ...] = tuple(KNOWLEDGE.topics) or ("admision",)

__all__ = [
    "KNOWLEDGE",
    "SITE",
    "SITE_HOST",
    "TOPIC_IDS",
    "Anchor",
    "Document",
    "Exit",
    "FeeBand",
    "Fees",
    "Hit",
    "Knowledge",
    "Level",
    "Page",
    "Section",
    "Topic",
    "canonical_path",
    "fold",
    "load",
    "norm",
    "tokens",
]
