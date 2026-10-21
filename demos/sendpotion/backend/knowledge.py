"""What Javier knows about SendPotion, in three layers, read once at import.

- **L1** (``knowledge/L1.md``) is always in his prompt: what SendPotion is,
  who it is for, the product in brief, pricing in brief, how to start.
- **L2** (``knowledge/L2/<topic>.md``) is a topic he reads with ``read_topic``
  when a question needs more than L1. Each file opens with ``# Title`` and a
  ``Sources:`` line.
- **L3** (``knowledge/L3/pages.json``, ``blog.json``) is the site itself —
  every page's sections, FAQs, tabs and forms, and every blog post — which
  ``search_site`` and ``find_posts`` search and which the brain checks every
  move against: a path he navigates to, a section he scrolls to, a post he
  opens.

The files are built offline (``knowledge/build.py``) and committed. Every one of
them may be missing or empty and this module still imports: the demos backend
serves every brain from one process, and one brain that cannot import takes the
others down with it.
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

#: The two hosts. The product site is Webflow; the blog is its own host.
SITE_HOST = "sendpotion.com"
BLOG_HOST = "blog.sendpotion.com"

_L1_FALLBACK = (
    "SendPotion's website is sendpotion.com, and its blog is blog.sendpotion.com. "
    "Nothing more is loaded: answer only from what you read with your tools."
)


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


def tokens(text: str) -> list[str]:
    """Lower-cased words and numbers, without the words every passage has."""
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


def norm(text: str) -> str:
    """Case, whitespace, curly quotes and dashes folded."""
    return " ".join(text.translate(_QUOTES).lower().split())


def canonical_path(path_or_url: str) -> str:
    """``https://sendpotion.com/Pricing/?a=1#b`` → ``/pricing``."""
    raw = path_or_url.strip()
    parts = urlsplit(raw if "://" in raw else f"https://x{'' if raw.startswith('/') else '/'}{raw}")
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/").lower()
    return path or "/"


def canonical_url(url: str) -> str:
    """A blog URL without its query, fragment, trailing slash or ``www``."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/")
    return f"https://{host}{path}"


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

    @property
    def headings(self) -> tuple[str, ...]:
        return tuple(s.heading for s in self.sections if s.heading)


@dataclass(frozen=True)
class Post:
    url: str
    title: str
    subtitle: str = ""
    author: str = ""
    date: str = ""
    tags: tuple[str, ...] = ()
    summary: str = ""
    use_cases: tuple[str, ...] = ()
    headings: tuple[str, ...] = ()
    text: str = ""


@dataclass(frozen=True)
class Hit:
    """One search result: a page, an FAQ on a page, or a blog post."""

    kind: str
    """``page``, ``faq`` or ``post``."""
    title: str
    snippet: str
    score: float
    path: str | None = None
    url: str | None = None
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
        best: dict[tuple[str, str | None, str | None, str | None], Hit] = {}
        for p in self.passages:
            s = 0.0
            for w in q:
                if (tf := p.tf.get(w, 0)) > 0:
                    idf = math.log(1 + (n - self.df[w] + 0.5) / (self.df[w] + 0.5))
                    s += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * p.length / self.avg))
            if s <= 0:
                continue
            low = p.text.lower()
            if phrase in low:
                s *= 1.5
                at = low.find(phrase)
            else:
                at = min((i for w in q if (i := low.find(w)) >= 0), default=0)
            snippet = p.text[max(0, at - 80) : at + 240]
            h = p.hit
            key = (h.kind, h.path, h.url, h.section if h.kind != "post" else None)
            hit = Hit(h.kind, h.title, snippet, round(s, 2), h.path, h.url, h.section)
            if key not in best or best[key].score < hit.score:
                best[key] = hit
        return sorted(best.values(), key=lambda h: -h.score)[:limit]


@dataclass
class Knowledge:
    l1: str
    topics: dict[str, Topic]
    pages: dict[str, Page]
    posts: dict[str, Post] = field(default_factory=dict[str, Post])
    _site: _Index = field(default_factory=_Index, repr=False)
    _blog: _Index = field(default_factory=_Index, repr=False)

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
            for faq in p.faqs:
                self._site.add(Hit("faq", faq.q, "", 0, path=p.path), f"{faq.q}\n{faq.a}")
        for post in self.posts.values():
            hit = Hit("post", post.title, "", 0, url=post.url)
            # What a post is for weighs more than any one paragraph of it.
            about = " ".join([post.title, post.subtitle, post.summary, *post.use_cases, *post.tags])
            self._blog.add(hit, about, weight=3)
            self._blog.add(hit, f"{' '.join(post.headings)}\n{post.text}")
        self._site.done()
        self._blog.done()

    # ── Lookups ──

    def page(self, path_or_url: str) -> Page | None:
        return self.pages.get(canonical_path(path_or_url))

    def post(self, url: str) -> Post | None:
        return self.posts.get(canonical_url(url))

    def near_paths(self, path_or_url: str, limit: int = 3) -> list[str]:
        want = canonical_path(path_or_url)
        scored = sorted(
            self.pages, key=lambda p: SequenceMatcher(None, want, p).ratio(), reverse=True
        )
        return scored[:limit]

    def search(self, query: str, limit: int = 6) -> list[Hit]:
        """The product site's pages, sections and FAQs."""
        return self._site.search(query, limit)

    def find_posts(self, query: str, limit: int = 5) -> list[Hit]:
        """Blog posts, best first, one hit per post."""
        return self._blog.search(query, limit)


# ─── Loading ───────────────────────────────────────────────────────────────────


def _read_json(path: Path) -> list[dict[str, Any]]:
    """A list of objects, or a dict of them keyed by path; anything else is empty."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("sendpotion: {} not loaded: {}", path.name, exc)
        return []
    if isinstance(data, dict):
        data = cast(dict[str, Any], data)
        inner = data.get("pages") or data.get("posts")
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
    if items:
        body = f"{body} {'; '.join(items)}".strip()
    # A block with no heading of its own is labelled by the crawl in brackets
    # ("[pt-definition] Generate videos from"): searchable, but nothing the page
    # can scroll to by heading, so it is not offered as one.
    if heading.startswith("["):
        label = heading.split("]", 1)[-1].strip()
        return Section("", f"{label} {body}".strip())
    return Section(heading, body)


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
        name = _str(f.get("name") or f.get("id") or f.get("label") or f.get("placeholder"))
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
    )


def _post(raw: dict[str, Any]) -> Post | None:
    url = raw.get("url") or raw.get("path")
    if not isinstance(url, str) or not (title := _str(raw.get("title"))):
        return None
    if url.startswith("/"):
        url = f"https://{BLOG_HOST}{url}"
    return Post(
        url=canonical_url(url),
        title=title,
        subtitle=_str(raw.get("subtitle")),
        author=_str(raw.get("author")),
        date=_str(raw.get("date")),
        tags=_strs(raw.get("tags")),
        summary=_str(raw.get("summary")),
        use_cases=_strs(raw.get("use_cases")),
        headings=_strs(raw.get("headings")),
        text=_str(raw.get("text")),
    )


def load(root: Path = ROOT) -> Knowledge:
    """Every layer under ``root``; whatever is missing is empty."""
    try:
        l1 = (root / "L1.md").read_text(encoding="utf-8").strip() or _L1_FALLBACK
    except OSError:
        logger.warning("sendpotion: L1.md not found; Javier runs on the fallback")
        l1 = _L1_FALLBACK
    topics: dict[str, Topic] = {}
    for path in sorted((root / "L2").glob("*.md")) if (root / "L2").is_dir() else []:
        topics[path.stem] = _topic(path)
    pages = {p.path: p for raw in _read_json(root / "L3" / "pages.json") if (p := _page(raw))}
    posts = {p.url: p for raw in _read_json(root / "L3" / "blog.json") if (p := _post(raw))}
    return Knowledge(l1, topics, pages, posts)


KNOWLEDGE = load()
"""The committed knowledge. Read through the module at session start, so a test
can put a fixture in its place."""

#: The topic names ``read_topic`` offers, fixed at import because they become a
#: ``Literal`` in its schema. A ``Literal`` cannot be empty.
TOPIC_IDS: tuple[str, ...] = tuple(KNOWLEDGE.topics) or ("company",)

__all__ = [
    "BLOG_HOST",
    "KNOWLEDGE",
    "SITE_HOST",
    "TOPIC_IDS",
    "Faq",
    "Form",
    "FormField",
    "Hit",
    "Knowledge",
    "Page",
    "Post",
    "Section",
    "Topic",
    "canonical_path",
    "canonical_url",
    "load",
    "norm",
    "tokens",
]
