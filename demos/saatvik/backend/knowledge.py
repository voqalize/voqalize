"""What Sunny knows about Saatvik, in three layers, read once at import.

- **L1** (``knowledge/L1.md``) is always in his prompt: the company, the product
  families, the national subsidy scheme, the ways to reach a person.
- **L2** (``knowledge/L2/<topic>.md``) is a topic he reads with ``read_topic``
  when a question needs more than L1. Each file opens with ``# Title`` and a
  ``Sources:`` line.
- **L3** (``knowledge/L3/pages.json``, ``documents.json``) is the site itself —
  every page's headings, FAQs and text, and every product PDF page by page — which
  ``search_site`` searches and which the brain checks every move against: a path
  he navigates to, a section he scrolls to, a quote he highlights in a PDF.

The files are built offline (``knowledge/build.py``) and committed. Every one of
them may be missing or empty and this module still imports: the demos backend
serves every brain from one process, and one brain that cannot import takes the
others down with it. A Sunny without L3 says she cannot find a page; she never
crashes the server.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from loguru import logger

ROOT = Path(__file__).parent / "knowledge"

#: What he knows when ``L1.md`` is missing: enough to be honest, nothing to quote.
_L1_FALLBACK = (
    "Saatvik Green Energy makes solar modules and offers rooftop and ground-mount "
    "solar projects across India. Its website is www.saatvikgroup.com. Nothing more "
    "is loaded: answer only from what you read with your tools."
)


# ─── Text ──────────────────────────────────────────────────────────────────────

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
# A word list reads as words, so it stays a split string.
_STOP = frozenset(
    "a an and are as at be by can do does for from has have how "  # noqa: SIM905
    "i in is it its me my of on or the to what which with you your".split()
)
#: Curly quotes and dashes, folded to their plain forms (escaped: they look alike).
_QUOTES = str.maketrans(
    {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-"}
)


def tokens(text: str) -> list[str]:
    """Lower-cased words and numbers, without the words every passage has."""
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


def norm(text: str) -> str:
    """Case, whitespace, curly quotes and dashes folded: how two copies of one
    sentence — the model's and the page's — are compared."""
    return " ".join(text.translate(_QUOTES).lower().split())


#: Paths the site answers with a permanent redirect, by their targets. Next's
#: router follows one softly, but with an extra round trip, and the page then
#: reports the target's path; so a move goes straight there. Found 2026-10-14 by
#: fetching every crawled path with ``RSC: 1``: every other path answers with
#: the router's own payload.
REDIRECTS: dict[str, str] = {
    "/contact-us": "/contact",
    "/saatvik-solar-gti-inverter": "/inverters",
    "/epc-solutions/carport-solar-solutions": "/epc-solutions/carport",
    "/epc-solutions/roof-top": "/epc-solutions/rooftop/commercial",
}


#: Pages the prompt's site map leaves out, by path prefix: blog posts, press
#: releases and investor filings, which search reaches, and which would crowd
#: the products out of the map.
SKIP_IN_MAP: tuple[str, ...] = (
    "/newsroom/blogs/",
    "/newsroom/press-release/",
    "/investors/",
)


def canonical_path(path_or_url: str) -> str:
    """``https://www.saatvikgroup.com/Products/X/?a=1#b`` → ``/products/x``."""
    raw = path_or_url.strip()
    parts = urlsplit(raw if "://" in raw else f"https://x{'' if raw.startswith('/') else '/'}{raw}")
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/").lower()
    return path or "/"


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
    """A heading and the text under it, up to the next heading."""

    heading: str
    text: str


@dataclass(frozen=True)
class Page:
    path: str
    title: str
    description: str = ""
    headings: tuple[str, ...] = ()
    faqs: tuple[Faq, ...] = ()
    text: str = ""
    documents: tuple[str, ...] = ()
    sections: tuple[Section, ...] = ()
    #: The spec tabs the page shows (ELECTRICAL, MECHANICAL, WARRANTY on a module).
    tabs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Word:
    """One word read off a page image by OCR, and where it sits: fractions of
    the page, from its top left corner."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class Box:
    """A rectangle on a page, in fractions of the page from its top left corner."""

    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class Document:
    id: str
    url: str
    title: str
    kind: str
    pages: dict[int, str]
    linked_from: tuple[str, ...] = ()
    words: dict[int, tuple[Word, ...]] = field(default_factory=dict[int, tuple[Word, ...]])
    """The OCR words of a page whose text is drawn as outlines, which the
    viewer's text layer cannot find: a quote there is marked by its boxes."""


@dataclass(frozen=True)
class QuoteMatch:
    """Where a quote is: its page, the page's own words for it, and on a page
    read by OCR, the boxes to mark (empty on a page with a text layer)."""

    page: int
    text: str
    boxes: tuple[Box, ...] = ()


@dataclass(frozen=True)
class Hit:
    """One search result: a page, an FAQ on a page, or one page of a PDF."""

    kind: str
    """``page``, ``faq`` or ``document``."""
    title: str
    snippet: str
    score: float
    path: str | None = None
    document_id: str | None = None
    page: int | None = None


@dataclass
class _Passage:
    hit: Hit
    text: str
    tf: Counter[str]
    length: int


@dataclass
class Knowledge:
    l1: str
    topics: dict[str, Topic]
    pages: dict[str, Page]
    documents: dict[str, Document]
    _passages: list[_Passage] = field(default_factory=list[_Passage], repr=False)
    _df: Counter[str] = field(default_factory=Counter[str], repr=False)
    _avg: float = 1.0

    def __post_init__(self) -> None:
        # Indexed once, here: a search runs while the visitor waits, inside the
        # tool budget, so it only scores.
        for p in self.pages.values():
            head = f"{p.title} {' '.join(p.headings)}"
            if p.path in REDIRECTS:
                continue  # the same page as its target, which is indexed itself
            self._add(Hit("page", p.title, "", 0, path=p.path), f"{head}\n{p.text}")
            for faq in p.faqs:
                self._add(Hit("faq", faq.q, "", 0, path=p.path), f"{faq.q}\n{faq.a}")
        for d in self.documents.values():
            for n, text in d.pages.items():
                self._add(Hit("document", d.title, "", 0, document_id=d.id, page=n), text)
        if self._passages:
            self._avg = sum(p.length for p in self._passages) / len(self._passages) or 1.0

    def _add(self, hit: Hit, text: str) -> None:
        toks = tokens(text)
        if not toks:
            return
        tf = Counter(toks)
        self._df.update(tf.keys())
        self._passages.append(_Passage(hit, " ".join(text.split()), tf, len(toks)))

    # ── Lookups ──

    def page(self, path_or_url: str) -> Page | None:
        """The page at this path or URL, if the site has one; a redirect's target
        for a path the site redirects."""
        path = canonical_path(path_or_url)
        return self.pages.get(REDIRECTS.get(path, path))

    def near_paths(self, path_or_url: str, limit: int = 3) -> list[str]:
        """Paths that look like this one: what to offer instead of a refusal."""
        want = canonical_path(path_or_url)
        scored = sorted(
            self.pages, key=lambda p: SequenceMatcher(None, want, p).ratio(), reverse=True
        )
        return scored[:limit]

    def search(self, query: str, limit: int = 6) -> list[Hit]:
        """BM25 over every page body, FAQ and PDF page; the phrase itself, when a
        passage has it, counts for half as much again."""
        q = tokens(query)
        if not q:
            return []
        n = len(self._passages)
        phrase = norm(query)
        k1, b = 1.4, 0.75
        out: list[Hit] = []
        for p in self._passages:
            s = 0.0
            for w in q:
                if (tf := p.tf.get(w, 0)) > 0:
                    idf = math.log(1 + (n - self._df[w] + 0.5) / (self._df[w] + 0.5))
                    s += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * p.length / self._avg))
            if s <= 0:
                continue
            low = p.text.lower()
            if phrase in low:
                s *= 1.5
                at = low.find(phrase)
            else:
                at = min((i for w in q if (i := low.find(w)) >= 0), default=0)
            snippet = p.text[max(0, at - 80) : at + 240]
            hit = p.hit
            out.append(
                Hit(hit.kind, hit.title, snippet, round(s, 2), hit.path, hit.document_id, hit.page)
            )
        out.sort(key=lambda h: -h.score)
        return out[:limit]

    def find_quote(self, document_id: str, page: int, quote: str) -> QuoteMatch | None:
        """Where ``quote`` is in the document: the asked page first, then the rest.

        Exact after folding case and whitespace, or, for a short slip of the
        model's (a dropped word, a unit spelt out) or the OCR's (``(y)`` for a
        gamma), a window of the page's own words that matches at least
        :data:`_QUOTE_MATCH`. What comes back is the page's spelling, which is
        what the viewer's text layer can find; on a page read by OCR, the
        boxes of exactly those words too."""
        doc = self.documents.get(document_id)
        if doc is None or not norm(quote):
            return None
        order = [page, *sorted(n for n in doc.pages if n != page)]
        for n in order:
            if (ocr := doc.words.get(n)) is not None:
                words = [w.text for w in ocr]
                if (span := _span(words, quote)) is not None:
                    i, j, _ = span
                    return QuoteMatch(n, " ".join(words[i:j]), _boxes(ocr[i:j]))
            elif (text := doc.pages.get(n)) is not None:
                words = text.split()
                if (span := _span(words, quote)) is not None:
                    i, j, whole = span
                    # Inside a word boundary we cannot cut; the viewer folds too.
                    return QuoteMatch(n, " ".join(words[i:j]) if whole else quote.strip())
        return None


#: How alike a window of the page's words and the model's quote must be, by
#: difflib's ratio, to count as the same words: a dropped or added short word in
#: a ten-word quote still clears it, a different figure does not.
_QUOTE_MATCH = 0.88

#: Padding round a marked OCR line, in fractions of the page: the mark sits
#: just outside the ink rather than on it.
_PAD_X, _PAD_Y = 0.003, 0.002


def _span(words: list[str], quote: str) -> tuple[int, int, bool] | None:
    """The words ``[i, j)`` that hold ``quote``, and whether they are exactly
    it rather than a little more (it starts or ends inside a word), or ``None``."""
    want = norm(quote)
    folded = [norm(w) for w in words]
    joined = " ".join(folded)
    if (at := joined.find(want)) >= 0:
        # The words the match touches, even where it starts or ends inside one.
        starts: list[int] = []
        pos = 0
        for f in folded:
            starts.append(pos)
            pos += len(f) + 1
        end = at + len(want)
        i = max(k for k, s in enumerate(starts) if s <= at)
        j = max(k for k, s in enumerate(starts) if s < end) + 1
        return i, j, " ".join(folded[i:j]) == want
    size = len(want.split())
    best, at, width = 0.0, -1, size
    for w in range(max(1, size - 2), size + 3):
        for i in range(len(words) - w + 1):
            r = SequenceMatcher(None, want, " ".join(folded[i : i + w])).ratio()
            if r > best:
                best, at, width = r, i, w
    if best >= _QUOTE_MATCH and at >= 0:
        return at, at + width, True
    return None


def _boxes(words: tuple[Word, ...]) -> tuple[Box, ...]:
    """One rectangle per line the words run over, padded and kept on the page.
    A word is on the line so far when it overlaps it by half its height and
    sits to its right; otherwise it starts the next one."""
    lines: list[list[float]] = []
    for w in words:
        last = lines[-1] if lines else None
        if last is not None:
            overlap = min(last[3], w.y1) - max(last[1], w.y0)
            if w.x0 >= last[0] and overlap >= 0.5 * min(last[3] - last[1], w.y1 - w.y0):
                last[:] = [
                    min(last[0], w.x0),
                    min(last[1], w.y0),
                    max(last[2], w.x1),
                    max(last[3], w.y1),
                ]
                continue
        lines.append([w.x0, w.y0, w.x1, w.y1])
    out: list[Box] = []
    for x0, y0, x1, y1 in lines:
        x0, y0 = max(0.0, x0 - _PAD_X), max(0.0, y0 - _PAD_Y)
        x1, y1 = min(1.0, x1 + _PAD_X), min(1.0, y1 + _PAD_Y)
        out.append(Box(round(x0, 4), round(y0, 4), round(x1 - x0, 4), round(y1 - y0, 4)))
    return tuple(out)


# ─── Loading ───────────────────────────────────────────────────────────────────


def _read_json(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("saatvik: {} not loaded: {}", path.name, exc)
        return []
    if not isinstance(data, list):
        return []
    return [cast(dict[str, Any], d) for d in cast(list[Any], data) if isinstance(d, dict)]


def _strs(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(v) for v in cast(list[Any], value) if isinstance(v, str))


def _topic(path: Path) -> Topic:
    text = path.read_text(encoding="utf-8")
    first = text.lstrip().splitlines()[0] if text.strip() else ""
    title = first.lstrip("# ").strip() if first.startswith("#") else path.stem
    return Topic(path.stem, title, text)


def _page(raw: dict[str, Any]) -> Page | None:
    if not isinstance(path := raw.get("path"), str):
        return None
    faqs: list[Faq] = []
    for f in cast(list[Any], raw.get("faqs") or []):
        if isinstance(f, dict):
            f = cast(dict[str, Any], f)
            faqs.append(Faq(str(f.get("q", "")), str(f.get("a", ""))))
    return Page(
        path=canonical_path(path),
        title=str(raw.get("title") or path),
        description=str(raw.get("description") or ""),
        headings=_strs(raw.get("headings")),
        faqs=tuple(faqs),
        text=str(raw.get("text") or ""),
        documents=_strs(raw.get("documents")),
        sections=tuple(_sections(raw.get("sections"))),
        tabs=_strs(raw.get("tabs")),
    )


def _sections(value: Any) -> list[Section]:
    out: list[Section] = []
    for s in cast(list[Any], value or []):
        if isinstance(s, dict):
            s = cast(dict[str, Any], s)
            if heading := str(s.get("heading") or "").strip():
                out.append(Section(heading, str(s.get("text") or "")))
    return out


def _document(raw: dict[str, Any]) -> Document | None:
    doc_id, url = raw.get("id"), raw.get("url")
    if not isinstance(doc_id, str) or not isinstance(url, str):
        return None
    pages: dict[int, str] = {}
    words: dict[int, tuple[Word, ...]] = {}
    for p in cast(list[Any], raw.get("pages") or []):
        if isinstance(p, dict):
            p = cast(dict[str, Any], p)
            if isinstance(n := p.get("n"), int):
                pages[n] = str(p.get("text") or "")
                if p.get("ocr") and (ocr := _words(p.get("words"))):
                    words[n] = ocr
    return Document(
        id=doc_id,
        url=url,
        title=str(raw.get("title") or doc_id),
        kind=str(raw.get("kind") or ""),
        pages=pages,
        linked_from=tuple(canonical_path(p) for p in _strs(raw.get("linked_from"))),
        words=words,
    )


def _words(raw: Any) -> tuple[Word, ...]:
    """``[[word, x0, y0, x1, y1], ...]`` as :class:`Word`; a malformed entry is dropped."""
    out: list[Word] = []
    for w in cast(list[Any], raw) if isinstance(raw, list) else []:
        if not isinstance(w, list):
            continue
        w = cast(list[Any], w)
        if len(w) != 5 or not isinstance(w[0], str) or not w[0].strip():
            continue
        try:
            x0, y0, x1, y1 = (float(v) for v in w[1:])
        except (TypeError, ValueError):
            continue
        out.append(Word(w[0], x0, y0, x1, y1))
    return tuple(out)


def load(root: Path = ROOT) -> Knowledge:
    """Every layer under ``root``; whatever is missing is empty."""
    try:
        l1 = (root / "L1.md").read_text(encoding="utf-8").strip() or _L1_FALLBACK
    except OSError:
        logger.warning("saatvik: L1.md not found; Tushar runs on the fallback")
        l1 = _L1_FALLBACK
    topics: dict[str, Topic] = {}
    for path in sorted((root / "L2").glob("*.md")) if (root / "L2").is_dir() else []:
        topics[path.stem] = _topic(path)
    pages = {p.path: p for raw in _read_json(root / "L3" / "pages.json") if (p := _page(raw))}
    documents = {
        d.id: d for raw in _read_json(root / "L3" / "documents.json") if (d := _document(raw))
    }
    return Knowledge(l1, topics, pages, documents)


KNOWLEDGE = load()
"""The committed knowledge. Read through the module at session start, so a test
can put a fixture in its place."""

#: The topic names ``read_topic`` offers, fixed at import because they become a
#: ``Literal`` in its schema. A ``Literal`` cannot be empty, so a checkout with no
#: L2 yet offers one name that reads back as "not written yet".
TOPIC_IDS: tuple[str, ...] = tuple(KNOWLEDGE.topics) or ("company",)

__all__ = [
    "KNOWLEDGE",
    "TOPIC_IDS",
    "Box",
    "Document",
    "Faq",
    "Hit",
    "Knowledge",
    "Page",
    "QuoteMatch",
    "Topic",
    "Word",
    "canonical_path",
    "load",
    "norm",
    "tokens",
]
