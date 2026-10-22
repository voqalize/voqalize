"""What Javier knows about Universidad Alberto Hurtado, in three layers, read once at import.

- **L1** (``knowledge/L1.md``) is always in his prompt: what the university is,
  its faculties and careers, how admission works, becas and gratuidad, the
  campus, visits, postgrado, and how the three sites are laid out.
- **L2** (``knowledge/L2/<topic>.md``) is a topic he reads with ``read_topic``
  when a question needs more than L1. Each file opens with ``# Title`` and a
  ``Sources:`` line.
- **L3** (``knowledge/L3/``) is the sites themselves: ``pages.json`` (every
  page's sections, cards and FAQs), ``carreras.json`` (the undergraduate
  careers) and ``programas.json`` (the postgraduate programmes), which the
  search tools search and which the brain checks every move against.

**No fees, dates, PAES minimums or weights are in any layer.** They change
every year and the site itself disagrees with itself about them (the
/aranceles/ page is last year's), so they are read live, in the visitor's
browser, from the page in front (:mod:`.protocol`). The knowledge test holds the
files to that.

The university's sites are three hosts — admision.uahurtado.cl (undergraduate
admission, where most of a prospective student's time goes),
postgrados.uahurtado.cl and www.uahurtado.cl — so a page is keyed by its host
and path together (:func:`page_key`), never by a bare path. In his cues and the
prompt an admision page is written as its path (``/carreras/psicologia/``) and
the others with their host (``www.uahurtado.cl/la-universidad/campus/``).

The files are built offline and committed. Every one of them may be missing or
empty and this module still imports: the demos backend serves every brain from
one process, and one brain that cannot import takes the others down with it.

The site is in Spanish and the visitor may ask in English, so every comparison
here folds case and accents: "psicologia" is "Psicología".
"""

from __future__ import annotations

import dataclasses
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

ADMISION = "admision.uahurtado.cl"
POSTGRADOS = "postgrados.uahurtado.cl"
WWW = "www.uahurtado.cl"
#: The hosts the extension runs on and Javier moves between. The bare domain
#: is the institutional site's.
HOSTS = (ADMISION, POSTGRADOS, WWW)
_ALIASES = {"uahurtado.cl": WWW}
#: Hosts he may open in a new tab and leave alone there: the PAES simulator,
#: whose form creates a lead, and the university's other sites.
LINK_DOMAIN = "uahurtado.cl"

#: The career page's tabs, by the id the catalogue lists them by, as the page
#: labels them: what a ``show`` cue names to open one.
CAREER_TAB_LABELS = {
    "malla": "Malla Curricular",
    "descripcion_carrera": "Descripción de la Carrera",
    "requisitos_carrera": "Requisitos y Aranceles",
    "beneficios": "Beneficios y Oportunidades",
    "conectados": "Estamos Conectados",
    "investigando": "Estamos Investigando",
    "titulados": "Los Titulados de la Carrera",
}

_L1_FALLBACK = (
    "Universidad Alberto Hurtado's admission site is admision.uahurtado.cl. Nothing more is "
    "loaded: answer only from what you read with your tools and from the screen."
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
    | {chr(0x2013): "-", chr(0x2014): "-"}
)
_APOSTROPHES = str.maketrans({chr(0x00B4): "'", chr(0x2019): "'", chr(0x0060): "'"})


def fold(text: str) -> str:
    """Lower case, without accents: "Psicología Ñuñoa" → "psicologia nunoa"."""
    decomposed = unicodedata.normalize("NFKD", text.lower().translate(_APOSTROPHES))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    """Folded words and numbers, without the words every passage has."""
    return [t for t in _TOKEN.findall(fold(text)) if t not in _STOP]


def norm(text: str) -> str:
    """Case, accents, whitespace, curly quotes and dashes folded."""
    return " ".join(fold(text.translate(_QUOTES)).split())


def page_key(url_or_path: str, host: str = ADMISION) -> str | None:
    """A page's key, its host and path: ``https://admision.uahurtado.cl/Carreras/Psicologia/?a#b``
    → ``admision.uahurtado.cl/carreras/psicologia``. A bare path is on ``host``
    (admision, unless said); ``www.uahurtado.cl/x`` without a scheme works too.
    ``None`` for a page on any other site."""
    raw = url_or_path.strip()
    if not raw:
        return None
    if "://" not in raw:
        head = raw.split("/", 1)[0].lower()
        raw = f"https://{raw}" if "." in head and head.endswith(LINK_DOMAIN) else raw
    if "://" in raw:
        parts = urlsplit(raw)
        where = parts.netloc.lower().split(":")[0]
        where = _ALIASES.get(where, where)
        path = parts.path
    else:
        where = host
        path = urlsplit(f"https://x{'' if raw.startswith('/') else '/'}{raw}").path
    if where not in HOSTS:
        return None
    path = re.sub(r"/{2,}", "/", path).rstrip("/").lower()
    return f"{where}{path or '/'}"


def page_url(key: str) -> str:
    """The URL a key loads, with the trailing slash WordPress writes."""
    return f"https://{key}" + ("" if key.endswith("/") else "/")


def short(key: str) -> str:
    """A key as the prompt and his cues write it: an admision page by its
    path, ``/carreras/psicologia/``; the others with their host."""
    host, _, rest = key.partition("/")
    path = f"/{rest}/" if rest else "/"
    return path if host == ADMISION else f"{host}{path}"


def host_of(key: str) -> str:
    return key.partition("/")[0]


def is_link_url(url: str) -> bool:
    """Whether ``url`` is on one of the university's own sites, any of them."""
    parts = urlsplit(url.strip())
    where = parts.netloc.lower().split(":")[0]
    return parts.scheme == "https" and (where == LINK_DOMAIN or where.endswith(f".{LINK_DOMAIN}"))


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
    hidden: bool = False
    """Not laid out on the page (a carousel's other slides, a hidden h1): searched,
    never scrolled to."""


@dataclass(frozen=True)
class Card:
    title: str
    text: str = ""
    href: str = ""


@dataclass(frozen=True)
class Page:
    key: str
    title: str
    description: str = ""
    kind: str = "page"
    sections: tuple[Section, ...] = ()
    faqs: tuple[Faq, ...] = ()
    cards: tuple[Card, ...] = ()
    text: str = ""
    toggles: tuple[str, ...] = ()
    """Tab, pill and accordion labels: a ``show`` cue on one opens it."""

    @property
    def headings(self) -> tuple[str, ...]:
        return tuple(s.heading for s in self.sections if s.heading and not s.hidden)

    @property
    def url(self) -> str:
        return page_url(self.key)


@dataclass(frozen=True)
class Career:
    """One undergraduate career, as admision.uahurtado.cl lists it. No fees and
    no PAES weights: those are read live off its page."""

    slug: str
    name: str
    url: str
    faculty: str = ""
    area: str = ""
    title_awarded: str = ""
    grado: str = ""
    duration: str = ""
    campus: str = ""
    jornada: str = ""
    modalidad: str = ""
    summary: str = ""
    tabs: tuple[str, ...] = ()
    has_audiomalla: bool = False
    aliases: tuple[str, ...] = ()
    menu_group: str = ""
    """Its group in the Carreras menu, which is its faculty's."""
    malla_pdf: str = ""
    admision_directa: bool = False

    @property
    def key(self) -> str:
        return page_key(self.url) or f"{ADMISION}/carreras/{self.slug}"

    @property
    def tab_labels(self) -> tuple[str, ...]:
        return tuple(CAREER_TAB_LABELS.get(t, t) for t in self.tabs)


@dataclass(frozen=True)
class Program:
    """One postgraduate programme, as postgrados.uahurtado.cl lists it. No fees
    and no dates: read live off its page."""

    slug: str
    name: str
    url: str
    type: str = ""
    area: str = ""
    modalidad: str = ""
    duration: str = ""
    summary: str = ""
    aliases: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return page_key(self.url) or f"{POSTGRADOS}/programa/{self.slug}"


@dataclass(frozen=True)
class Hit:
    """One search result: a page section, a card, an FAQ, a career or a programme."""

    kind: str
    title: str
    snippet: str
    score: float
    key: str | None = None
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
            key = (h.kind, h.key, h.section, h.title)
            hit = Hit(h.kind, h.title, snippet, round(s, 2), h.key, h.section)
            if key not in best or best[key].score < hit.score:
                best[key] = hit
        return sorted(best.values(), key=lambda h: -h.score)[:limit]


def _words(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", fold(text)))


@dataclass
class Knowledge:
    l1: str
    topics: dict[str, Topic]
    pages: dict[str, Page]
    careers: dict[str, Career] = field(default_factory=dict[str, Career])
    programs: dict[str, Program] = field(default_factory=dict[str, Program])
    _site: _Index = field(default_factory=_Index, repr=False)
    _careers: _Index = field(default_factory=_Index, repr=False)
    _programs: _Index = field(default_factory=_Index, repr=False)

    def __post_init__(self) -> None:
        # Indexed once, here: a search runs while the visitor waits.
        for p in self.pages.values():
            self._site.add(Hit("page", p.title, "", 0, key=p.key), f"{p.title}\n{p.description}")
            for s in p.sections:
                self._site.add(
                    Hit("page", p.title, "", 0, key=p.key, section=s.heading or None),
                    f"{s.heading}\n{s.text}",
                )
            if not p.sections and p.text:
                self._site.add(Hit("page", p.title, "", 0, key=p.key), p.text)
            for card in p.cards:
                self._site.add(
                    Hit("card", card.title, "", 0, key=p.key), f"{card.title}\n{card.text}"
                )
            for faq in p.faqs:
                self._site.add(Hit("faq", faq.q, "", 0, key=p.key), f"{faq.q}\n{faq.a}")
        for c in self.careers.values():
            names = " ".join([c.name, *c.aliases])
            self._careers.add(Hit("career", c.name, "", 0, key=c.key), names, weight=4)
            about = " ".join([c.faculty, c.area, c.title_awarded, c.campus, c.jornada, c.modalidad])
            self._careers.add(Hit("career", c.name, "", 0, key=c.key), about, weight=2)
            self._careers.add(Hit("career", c.name, "", 0, key=c.key), c.summary)
        for p in self.programs.values():
            names = " ".join([p.name, *p.aliases])
            self._programs.add(Hit("program", p.name, "", 0, key=p.key), names, weight=4)
            about = " ".join([p.type, p.area, p.modalidad])
            self._programs.add(Hit("program", p.name, "", 0, key=p.key), about, weight=2)
            self._programs.add(Hit("program", p.name, "", 0, key=p.key), p.summary)
        self._site.done()
        self._careers.done()
        self._programs.done()

    # ── Lookups ──

    def page(self, url_or_path: str) -> Page | None:
        """A crawled page, or a career's or programme's own page (which the
        crawl may have missed) as a bare one."""
        key = page_key(url_or_path)
        if key is None:
            return None
        if (p := self.pages.get(key)) is not None:
            return p
        for c in self.careers.values():
            if c.key == key:
                return Page(key, c.name, kind="career", text=c.summary, toggles=c.tab_labels)
        for g in self.programs.values():
            if g.key == key:
                return Page(key, g.name, kind="program", text=g.summary)
        return None

    def career(self, said: str) -> Career | None:
        """The career by its slug, page, name or alias (folded, whole first,
        then the one it begins, then the one containing it)."""
        return _named(said, self.careers)

    def program(self, said: str) -> Program | None:
        return _named(said, self.programs)

    def career_at(self, url: str) -> Career | None:
        key = page_key(url)
        return next((c for c in self.careers.values() if c.key == key), None)

    def program_at(self, url: str) -> Program | None:
        key = page_key(url)
        return next((p for p in self.programs.values() if p.key == key), None)

    def named_career(self, text: str) -> Career | None:
        """The career ``text`` names by the whole of its name or an alias; the
        longest wins, so "Ingeniería Civil en Informática" is not "Ingeniería"."""
        return _named_in(text, self.careers)

    def named_program(self, text: str) -> Program | None:
        return _named_in(text, self.programs)

    def search(self, query: str, limit: int = 6) -> list[Hit]:
        """The sites' pages, sections, cards and FAQs."""
        return self._site.search(query, limit)

    def find_careers(self, query: str, limit: int = 8) -> list[Career]:
        hits = self._careers.search(query, limit * 2)
        out = [c for h in hits if (c := self._career_by_key(h.key)) is not None]
        return list(dict.fromkeys(out))[:limit]

    def find_programs(self, query: str, limit: int = 8) -> list[Program]:
        hits = self._programs.search(query, limit * 3)
        out = [p for h in hits if (p := self._program_by_key(h.key)) is not None]
        return list(dict.fromkeys(out))[:limit]

    def faculties(self) -> dict[str, list[Career]]:
        """The careers by faculty, in the catalogue's order."""
        out: dict[str, list[Career]] = {}
        for c in self.careers.values():
            out.setdefault(c.menu_group or c.faculty or "Otras", []).append(c)
        return out

    def _career_by_key(self, key: str | None) -> Career | None:
        return next((c for c in self.careers.values() if c.key == key), None)

    def _program_by_key(self, key: str | None) -> Program | None:
        return next((p for p in self.programs.values() if p.key == key), None)


def _named[T: (Career, Program)](said: str, items: dict[str, T]) -> T | None:
    if (hit := items.get(said.strip().lower())) is not None:
        return hit
    key = page_key(said) if ("/" in said or "uahurtado" in said) else None
    if key is not None and (hit := next((i for i in items.values() if i.key == key), None)):
        return hit
    want = _words(said)
    if not want:
        return None
    named = [(i, [_words(n) for n in (i.name, *i.aliases)]) for i in items.values()]
    for test in (
        lambda n: n == want,
        lambda n: n.startswith(want),
        lambda n: want in n,
        lambda n: len(n) > 5 and n in want,
    ):
        found = [i for i, names in named if any(n and test(n) for n in names)]
        if found:
            # The shortest name of those that fit: "Ingeniería Comercial", not
            # its CEV evening twin.
            return min(found, key=lambda i: len(i.name))
    return None


def _named_in[T: (Career, Program)](text: str, items: dict[str, T]) -> T | None:
    said = f" {_words(text)} "
    best: tuple[int, T] | None = None
    for i in items.values():
        for n in (i.name, *i.aliases):
            name = _words(n)
            if len(name) >= 4 and f" {name} " in said and (best is None or len(name) > best[0]):
                best = (len(name), i)
    return best[1] if best else None


# ─── Loading ───────────────────────────────────────────────────────────────────


def _read_json(path: Path) -> list[dict[str, Any]]:
    """A list of objects, or a dict of them keyed by path; anything else is empty."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("uahurtado: {} not loaded: {}", path.name, exc)
        return []
    if isinstance(data, dict):
        data = cast(dict[str, Any], data)
        inner = data.get("pages") or data.get("carreras") or data.get("programas")
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
    if isinstance(value, str):
        return tuple(s.strip() for s in value.split(",") if s.strip())
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


def _topic(path: Path, root: Path) -> Topic:
    text = path.read_text(encoding="utf-8")
    first = text.lstrip().splitlines()[0] if text.strip() else ""
    title = first.lstrip("# ").strip() if first.startswith("#") else path.stem
    rel = path.relative_to(root).with_suffix("")
    return Topic("-".join(rel.parts), title, text)


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
    return Section(heading, body, hidden=bool(raw.get("hidden")))


def _page(raw: dict[str, Any]) -> Page | None:
    where = raw.get("url") or raw.get("path")
    if not isinstance(where, str):
        return None
    host = _str(raw.get("host")) or ADMISION
    key = page_key(where, host if host in HOSTS else ADMISION)
    if key is None:
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
    accordions = _dicts(raw.get("accordions"))
    toggles = tuple(dict.fromkeys([*_strs(raw.get("tabs")), *_strs(accordions)]))
    if not faqs:
        # An accordion of questions is the page's FAQ (Gratuidad's is).
        faqs = tuple(
            Faq(q, _str(a.get("text") or a.get("answer")))
            for a in accordions
            if (q := _str(a.get("label"))) and (q.endswith("?") or q.startswith("¿"))
        )
    return Page(
        key=key,
        title=_str(raw.get("title")) or short(key),
        description=_str(raw.get("description")),
        kind=_str(raw.get("kind")) or "page",
        sections=sections,
        faqs=faqs,
        cards=cards,
        text=_str(raw.get("text")),
        toggles=toggles,
    )


def _pages(raws: list[dict[str, Any]]) -> dict[str, Page]:
    """The crawl's pages by key. Career and programme pages are one template
    record each (``.../carreras/*``), which is not a page, plus a light record
    per slug naming it: each slug's page takes the template's headings and
    toggles, with a career's tab ids read as the labels the page shows."""
    templates: dict[str, Page] = {}
    pages: dict[str, Page] = {}
    for raw in raws:
        page = _page(raw)
        if page is None:
            continue
        if page.key.endswith("/*") or page.kind == "template":
            templates[_str(raw.get("title")) or page.kind] = page
            continue
        pages[page.key] = page
    for raw in raws:
        name = _str(raw.get("template"))
        key = page_key(_str(raw.get("url")) or "")
        if not name or key is None or key not in pages or name not in templates:
            continue
        own, shape = pages[key], templates[name]
        toggles = tuple(CAREER_TAB_LABELS.get(t, t) for t in own.toggles) or shape.toggles
        pages[key] = dataclasses.replace(
            own,
            sections=own.sections or shape.sections,
            toggles=toggles,
            faqs=own.faqs or shape.faqs,
        )
    return pages


def _career(raw: dict[str, Any]) -> Career | None:
    slug, name, url = _str(raw.get("slug")), _str(raw.get("name")), _str(raw.get("url"))
    if not (slug and name):
        return None
    return Career(
        slug=slug,
        name=name,
        url=url or page_url(f"{ADMISION}/carreras/{slug}"),
        faculty=_str(raw.get("faculty")),
        area=_str(raw.get("area")),
        title_awarded=_str(raw.get("title_awarded")),
        grado=_str(raw.get("grado")),
        duration=_str(raw.get("duration")),
        campus=_str(raw.get("campus")),
        jornada=_str(raw.get("jornada")),
        modalidad=_str(raw.get("modalidad")),
        summary=_str(raw.get("summary")),
        tabs=_strs(raw.get("tabs")),
        has_audiomalla=bool(raw.get("has_audiomalla")),
        aliases=_strs(raw.get("aliases")),
        menu_group=_str(raw.get("menu_group")),
        malla_pdf=_str(raw.get("malla_pdf")),
        admision_directa=bool(raw.get("admision_directa")),
    )


def _program(raw: dict[str, Any]) -> Program | None:
    slug, name, url = _str(raw.get("slug")), _str(raw.get("name")), _str(raw.get("url"))
    if not (slug and name):
        return None
    return Program(
        slug=slug,
        name=name,
        url=url or page_url(f"{POSTGRADOS}/programa/{slug}"),
        type=_str(raw.get("type")),
        area=_str(raw.get("area")),
        modalidad=_str(raw.get("modalidad")),
        duration=_str(raw.get("duration")),
        summary=_str(raw.get("summary")),
        aliases=_strs(raw.get("aliases")),
    )


def load(root: Path = ROOT) -> Knowledge:
    """Every layer under ``root``; whatever is missing is empty."""
    try:
        l1 = (root / "L1.md").read_text(encoding="utf-8").strip() or _L1_FALLBACK
    except OSError:
        logger.warning("uahurtado: L1.md not found; Javier runs on the fallback")
        l1 = _L1_FALLBACK
    topics: dict[str, Topic] = {}
    l2 = root / "L2"
    for path in sorted(l2.rglob("*.md")) if l2.is_dir() else []:
        topic = _topic(path, l2)
        topics[topic.id] = topic
    pages = _pages(_read_json(root / "L3" / "pages.json"))
    careers = {
        c.slug: c for raw in _read_json(root / "L3" / "carreras.json") if (c := _career(raw))
    }
    programs = {
        p.slug: p for raw in _read_json(root / "L3" / "programas.json") if (p := _program(raw))
    }
    return Knowledge(l1, topics, pages, careers, programs)


KNOWLEDGE = load()
"""The committed knowledge. Read through the module at session start, so a test
can put a fixture in its place."""

#: The topic names ``read_topic`` offers, fixed at import because they become a
#: ``Literal`` in its schema. A ``Literal`` cannot be empty.
TOPIC_IDS: tuple[str, ...] = tuple(KNOWLEDGE.topics) or ("admision",)

__all__ = [
    "ADMISION",
    "CAREER_TAB_LABELS",
    "HOSTS",
    "KNOWLEDGE",
    "POSTGRADOS",
    "TOPIC_IDS",
    "WWW",
    "Card",
    "Career",
    "Faq",
    "Hit",
    "Knowledge",
    "Page",
    "Program",
    "Section",
    "Topic",
    "fold",
    "host_of",
    "is_link_url",
    "load",
    "norm",
    "page_key",
    "page_url",
    "short",
    "tokens",
]
