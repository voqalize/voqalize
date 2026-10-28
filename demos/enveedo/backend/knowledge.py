"""What Javier knows about Enveedo, in three layers, read once at import.

- **L1** (``knowledge/L1.md``) is always in his prompt. It opens with what the
  site does *not* say (pricing, a trial, customer counts, funding, a named
  award), then who Enveedo is, its audiences, the platform's modules, the
  Security Performance OS pillars, the proof the site gives, the frameworks in
  short, partners, cyber insurance, trust, the calls to action and contacts.
- **L2** (``knowledge/L2/<topic>.md``) is a topic he reads with ``read_topic``
  when a question needs more than L1. Each file opens with ``# Title`` and a
  ``Sources:`` line.
- **L3** (``knowledge/L3/``) is the site itself, built by
  ``knowledge/build.py`` from the live pages in both languages:
  ``pages.json`` (every page's places with the words they show), which
  ``search_site`` searches; ``anchors.json``, the catalogue of places a move
  can target, which the brain checks every cue against and the extension
  bundles to find them; ``site.json`` (the English↔Spanish twins, the links
  that leave the site, the contact details).

The knowledge is written in English; the site is English at ``/…`` and Spanish
at ``/es/…`` with the same slugs, and the catalogue's keys are the same on
both. The brain always names English paths: :func:`english_path` takes a
Spanish one back to its twin.

The files are built offline and committed. Every one of them may be missing or
empty and this module still imports: the demos backend serves every brain from
one process, and one brain that cannot import takes the others down with it.
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

SITE_HOST = "enveedo.com"
SITE = f"https://{SITE_HOST}"

_L1_FALLBACK = (
    "Enveedo's website is enveedo.com: a security program management platform. Nothing more "
    "is loaded: answer only from what you read with your tools and what the screen shows."
)

# ─── Text ──────────────────────────────────────────────────────────────────────

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
_STOP = frozenset(
    # English and Spanish words every passage has.
    """a an and are as at be by can do does for from has have how i in is it its me my of on
    or the to what which with you your el la los las un una unos unas de del y o en por para
    con que se su sus es al lo como mas tu te mi enveedo""".split()  # noqa: SIM905
)
_QUOTES = str.maketrans(
    {chr(0x2018): "'", chr(0x2019): "'", chr(0x201C): '"', chr(0x201D): '"'}
    | {chr(0x2013): "-", chr(0x2014): "-", chr(0x00AB): '"', chr(0x00BB): '"'}
)


def fold(text: str) -> str:
    """Lower case, without accents: "Gestión" → "gestion"."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    """Folded words and numbers, without the words every passage has."""
    return [t for t in _TOKEN.findall(fold(text)) if t not in _STOP]


def norm(text: str) -> str:
    """Case, accents, whitespace, curly quotes and dashes folded."""
    return " ".join(fold(text.translate(_QUOTES)).split())


def canonical_path(path_or_url: str) -> str:
    """``https://enveedo.com/Frameworks/?hsLang=es#x`` → ``/frameworks``: lower
    case, no trailing slash, except the two home pages, ``/`` and ``/es/``."""
    raw = path_or_url.strip()
    parts = urlsplit(raw if "://" in raw else f"https://x{'' if raw.startswith('/') else '/'}{raw}")
    path = re.sub(r"/{2,}", "/", parts.path).lower().rstrip("/")
    if path in ("", "/"):
        return "/"
    return "/es/" if path == "/es" else path


def is_spanish(path: str) -> bool:
    return canonical_path(path).startswith("/es/")


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
    lang: str = "en"
    twin: str | None = None
    sections: tuple[Section, ...] = ()
    text: str = ""

    @property
    def headings(self) -> tuple[str, ...]:
        return tuple(s.heading for s in self.sections if s.heading)

    def section(self, key: str) -> Section | None:
        return next((s for s in self.sections if s.key == key), None)


@dataclass(frozen=True)
class Anchor:
    """A place a move can target: its key, its label, whether the model is
    offered it (``hidden`` ones are the adapter's own: a consent box, a
    Submit), and whether the page opens it first (a tab, an accordion, the
    Without/With toggle)."""

    key: str
    label: str
    hidden: bool = False
    reveal: bool = False


@dataclass(frozen=True)
class Exit:
    """A link that leaves the site: opened in a new tab, never filled."""

    key: str
    label: str
    url: str


@dataclass(frozen=True)
class Framework:
    """One of the 39 cards on /frameworks."""

    key: str
    name: str
    group: str
    """``infosec``, ``ai`` or ``privacy``, as the page groups them."""
    aliases: tuple[str, ...]
    """How a visitor says it, folded: "nis 2", "ley marco de ciberseguridad"."""
    blurb: str = ""


#: The 39 framework cards, with the ways a visitor names them. The card key is
#: the catalogue's; the blurb is read from the crawl when it is loaded.
FRAMEWORKS: tuple[Framework, ...] = tuple(
    Framework(key, name, group, tuple(norm(a) for a in aliases))
    for key, name, group, aliases in (
        (
            "fw_iso_27001",
            "ISO/IEC 27001:2022",
            "infosec",
            ("iso 27001", "27001", "iso27001", "isms"),
        ),
        (
            "fw_soc2",
            "SOC 2 Readiness",
            "infosec",
            ("soc 2", "soc2", "soc ii", "soc two", "soc dos", "aicpa", "trust services criteria"),
        ),
        ("fw_tisax", "TISAX ISA", "infosec", ("tisax", "automotive", "automotriz", "vda isa")),
        (
            "fw_nist_800_82",
            "NIST SP 800-82",
            "infosec",
            ("800-82", "800 82", "ics security", "scada", "ot security", "industrial control"),
        ),
        (
            "fw_iso_9001",
            "ISO/IEC 9001:2015",
            "infosec",
            ("iso 9001", "9001", "quality management", "gestion de calidad"),
        ),
        (
            "fw_nist_csf",
            "NIST CSF v2.0",
            "infosec",
            ("nist csf", "csf", "cybersecurity framework", "nist cybersecurity", "csf 2"),
        ),
        ("fw_hipaa", "HIPAA Security Rule", "infosec", ("hipaa", "health data", "datos de salud")),
        ("fw_iso_27002", "ISO/IEC 27002:2022", "infosec", ("iso 27002", "27002")),
        (
            "fw_nis2",
            "NIS2 Directive",
            "infosec",
            ("nis2", "nis 2", "nis two", "nis dos", "nis directive", "directiva nis"),
        ),
        ("fw_dora", "DORA", "infosec", ("dora", "digital operational resilience", "2022/2554")),
        (
            "fw_pci_dss",
            "PCI DSS v4.0.1",
            "infosec",
            ("pci", "pci dss", "pci-dss", "card data", "tarjetas"),
        ),
        (
            "fw_iso_31000",
            "ISO/IEC 31000:2018",
            "infosec",
            ("iso 31000", "31000", "risk management standard"),
        ),
        (
            "fw_iso_27017_csc",
            "ISO/IEC 27017:2015 (CSC)",
            "infosec",
            ("27017", "iso 27017", "cloud customer", "cloud security"),
        ),
        (
            "fw_ens",
            "ENS",
            "infosec",
            (
                "ens",
                "esquema nacional de seguridad",
                "national security framework",
                "spain",
                "espana",
                "ccn-stic",
            ),
        ),
        (
            "fw_cis",
            "CIS CSC V8.1",
            "infosec",
            ("cis", "cis controls", "cis csc", "cis 8", "controles cis"),
        ),
        (
            "fw_iso_22301",
            "ISO/IEC 22301:2019",
            "infosec",
            ("iso 22301", "22301", "business continuity", "continuidad de negocio"),
        ),
        (
            "fw_iso_27017_csp",
            "ISO/IEC 27017:2015 (CSP)",
            "infosec",
            ("cloud provider", "cloud service provider", "27017 csp"),
        ),
        (
            "fw_nist_800_171",
            "NIST SP 800-171 Rev. 3",
            "infosec",
            ("800-171", "800 171", "cui", "controlled unclassified", "cmmc"),
        ),
        (
            "fw_eu_ai_act",
            "EU AI Act",
            "ai",
            (
                "ai act",
                "eu ai act",
                "ley de ia",
                "ley europea de inteligencia artificial",
                "reglamento de ia",
            ),
        ),
        (
            "fw_nist_ai_rmf",
            "NIST AI RMF 600-1",
            "ai",
            ("ai rmf", "nist ai", "600-1", "ai risk management framework"),
        ),
        (
            "fw_iso_42001",
            "ISO/IEC 42001:2023",
            "ai",
            ("iso 42001", "42001", "aims", "ai management system"),
        ),
        (
            "fw_gdpr",
            "GDPR",
            "privacy",
            (
                "gdpr",
                "rgpd",
                "general data protection regulation",
                "reglamento general de proteccion de datos",
            ),
        ),
        (
            "fw_enveedo_pia",
            "Enveedo PIA",
            "privacy",
            ("pia", "privacy impact assessment", "evaluacion de impacto", "dpia"),
        ),
        (
            "fw_colombia_data",
            "Colombia Data Protection Law",
            "privacy",
            ("colombia", "ley 1581", "1581", "habeas data"),
        ),
        (
            "fw_mexico_public",
            "Mexico Data Protection Law (Public)",
            "privacy",
            ("mexico public", "sujetos obligados", "ley general de proteccion de datos personales"),
        ),
        (
            "fw_anexo_28",
            "Anexo 28 RMF 2024",
            "privacy",
            ("anexo 28", "annex 28", "rmf", "sat", "contabilidad electronica"),
        ),
        (
            "fw_nist_privacy",
            "NIST Privacy Framework v1.0",
            "privacy",
            ("nist privacy", "privacy framework"),
        ),
        (
            "fw_argentina_data",
            "Argentina Data Protection Law",
            "privacy",
            ("argentina", "ley 25326", "25,326", "25.326"),
        ),
        (
            "fw_mexico_private",
            "Mexico Data Protection Law (Private)",
            "privacy",
            ("lfpdppp", "mexico", "mexico private", "particulares"),
        ),
        (
            "fw_chile_cyber_law",
            "Chile Cybersecurity Law",
            "privacy",
            (
                "ley marco de ciberseguridad",
                "21.663",
                "21663",
                "chile cybersecurity",
                "ley de ciberseguridad",
                "anci",
            ),
        ),
        (
            "fw_circular_co_sa",
            "Circular CO SA 17.18/24",
            "privacy",
            ("circular co sa", "17.18/24", "co sa"),
        ),
        ("fw_iso_27701", "ISO/IEC 27701:2025", "privacy", ("iso 27701", "27701", "pims")),
        (
            "fw_chile_21719",
            "Chile Data Protection Law (21.719)",
            "privacy",
            (
                "21.719",
                "21719",
                "chile new data law",
                "chile's new data law",
                "nueva ley de datos",
                "nueva ley de proteccion de datos",
                "chile data protection",
                "ley de proteccion de datos chile",
            ),
        ),
        ("fw_peru_data", "Peru Data Protection Law", "privacy", ("peru", "ley 29733", "29733")),
        (
            "fw_chile_19628",
            "Chile Data Protection Law (No. 19628)",
            "privacy",
            ("19.628", "19628", "chile old data law", "ley 19628"),
        ),
        ("fw_lgpd", "LGPD", "privacy", ("lgpd", "brazil", "brasil")),
        (
            "fw_ce_007",
            "CE 007/2018 Requirements",
            "privacy",
            ("ce 007", "007/2018", "circular externa 007", "superfinanciera"),
        ),
        ("fw_panama_data", "Panama Data Protection Law", "privacy", ("panama", "ley 81")),
        (
            "fw_costa_rica_data",
            "Costa Rica Data Protection Law",
            "privacy",
            ("costa rica", "ley 8968", "8968"),
        ),
    )
)


@dataclass(frozen=True)
class Hit:
    """One search result: a place on a page."""

    title: str
    snippet: str
    score: float
    path: str
    """The English path, whatever language matched."""
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
        best: dict[tuple[str, str | None], Hit] = {}
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
            key = (h.path, h.section)
            hit = Hit(h.title, snippet, round(s, 2), h.path, h.section)
            if key not in best or best[key].score < hit.score:
                best[key] = hit
        return sorted(best.values(), key=lambda h: -h.score)[:limit]


@dataclass
class Knowledge:
    l1: str
    topics: dict[str, Topic]
    pages: dict[str, Page]
    """Every page by its own path, English and Spanish."""
    anchors: dict[str, tuple[Anchor, ...]] = field(default_factory=dict[str, tuple[Anchor, ...]])
    """Per path (either language), the places a move can target there: the
    page's own, then the header's and the footer's where the page has them."""
    twins: dict[str, str] = field(default_factory=dict[str, str])
    """English path → Spanish path."""
    exits: dict[str, Exit] = field(default_factory=dict[str, Exit])
    library: tuple[Exit, ...] = ()
    """The gated eBooks and webinars, by their labels."""
    contact: dict[str, str] = field(default_factory=dict[str, str])
    frameworks: tuple[Framework, ...] = FRAMEWORKS
    _site: _Index = field(default_factory=_Index, repr=False)

    def __post_init__(self) -> None:
        self._english = {es: en for en, es in self.twins.items()}
        # Indexed once, here: a search runs while the visitor waits. A Spanish
        # page's words find its English path.
        for p in self.pages.values():
            en = self.english_path(p.path)
            self._site.add(Hit(p.title, "", 0, en), f"{p.title}\n{p.text}")
            for s in p.sections:
                self._site.add(Hit(p.title, "", 0, en, s.key), f"{s.heading}\n{s.text}")
        self._site.done()
        # Each card's own words, from the English frameworks page.
        fw = self.pages.get("/frameworks")
        if fw is not None:
            self.frameworks = tuple(
                f
                if (s := fw.section(f.key)) is None
                else Framework(f.key, f.name, f.group, f.aliases, s.text)
                for f in self.frameworks
            )

    # ── Lookups ──

    def english_path(self, path_or_url: str) -> str:
        """The English twin of a path, or the path itself."""
        path = canonical_path(path_or_url)
        if path in self._english:
            return self._english[path]
        if path == "/es/":
            return "/"
        if path.startswith("/es/") and (en := path[3:]) in self.twins:
            return en
        return path

    def spanish_path(self, path: str) -> str | None:
        return self.twins.get(self.english_path(path))

    def page(self, path_or_url: str) -> Page | None:
        return self.pages.get(canonical_path(path_or_url))

    def anchors_on(self, path: str) -> tuple[Anchor, ...]:
        """The places a move can target on ``path``; a Spanish path with no
        catalogue of its own takes its English twin's keys."""
        path = canonical_path(path)
        if path in self.anchors:
            return self.anchors[path]
        return self.anchors.get(self.english_path(path), ())

    def search(self, query: str, limit: int = 6) -> list[Hit]:
        """The site's pages and places, in either language; English paths."""
        return self._site.search(query, limit)

    def find_framework(self, query: str) -> list[Framework]:
        """The cards ``query`` names: an alias or the name inside it, best first;
        else the cards whose words it shares most."""
        q = norm(query)
        if not q:
            return []
        qs = f" {re.sub(r'[^a-z0-9./ -]', ' ', q)} "
        named: list[tuple[int, Framework]] = []
        for f in self.frameworks:
            names = (norm(f.name), *f.aliases)
            hit = max(
                (
                    len(a)
                    for a in names
                    if a and re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", qs)
                ),
                default=0,
            )
            if hit:
                named.append((hit, f))
        if named:
            named.sort(key=lambda x: -x[0])
            return [f for _, f in named]
        want = set(tokens(query)) - {
            "law",
            "ley",
            "framework",
            "data",
            "datos",
            "protection",
            "proteccion",
        }
        scored = [
            (len(want & set(tokens(f"{f.name} {' '.join(f.aliases)}"))), f) for f in self.frameworks
        ]
        best = max((s for s, _ in scored), default=0)
        return [f for s, f in scored if s and s == best]


# ─── Loading ───────────────────────────────────────────────────────────────────


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("enveedo: {} not loaded: {}", path.name, exc)
        return None


def _dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], v) for v in cast(list[Any], value) if isinstance(v, dict)]


def _dict(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _str(value: Any) -> str:
    return " ".join(str(value).split()) if isinstance(value, str | int | float) else ""


def _topic(path: Path) -> Topic:
    text = path.read_text(encoding="utf-8")
    first = text.lstrip().splitlines()[0] if text.strip() else ""
    title = first.lstrip("# ").strip() if first.startswith("#") else path.stem
    return Topic(path.stem, title, text)


def _page(raw: dict[str, Any]) -> Page | None:
    path = raw.get("path")
    if not isinstance(path, str) or raw.get("empty"):
        return None
    sections = tuple(
        Section(key, _str(s.get("heading")), str(s.get("text") or "").strip())
        for s in _dicts(raw.get("sections"))
        if (key := _str(s.get("key")))
    )
    twin = _str(raw.get("twin"))
    return Page(
        path=canonical_path(path),
        title=_str(raw.get("title")) or path,
        kind=_str(raw.get("kind")) or "page",
        lang=_str(raw.get("lang")) or "en",
        twin=canonical_path(twin) if twin else None,
        sections=sections,
        text=_str(raw.get("text")),
    )


def _anchors(rows: Any) -> tuple[Anchor, ...]:
    return tuple(
        Anchor(key, _str(a.get("label")), bool(a.get("hidden")), bool(a.get("reveal")))
        for a in _dicts(rows)
        if (key := _str(a.get("key")))
    )


def load(root: Path = ROOT) -> Knowledge:
    """Every layer under ``root``; whatever is missing is empty."""
    try:
        l1 = (root / "L1.md").read_text(encoding="utf-8").strip() or _L1_FALLBACK
    except OSError:
        logger.warning("enveedo: L1.md not found; Javier runs on the fallback")
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
    site = _dict(_read(root / "L3" / "site.json"))
    twins = {
        canonical_path(en): canonical_path(es)
        for en, es in _dict(site.get("twins")).items()
        if isinstance(es, str) and es
    }
    exits = {
        key: Exit(key, _str(c.get("label")), _str(c.get("url")))
        for key, value in _dict(site.get("exits")).items()
        if _str((c := _dict(value)).get("url"))
    }
    library = tuple(
        Exit(f"library_{i}", _str(x.get("label")), _str(x.get("url")))
        for i, x in enumerate(_dicts(site.get("library")))
        if _str(x.get("url"))
    )
    contact = {k: _str(v) for k, v in _dict(site.get("contact")).items() if _str(v)}
    return Knowledge(l1, topics, pages, anchors, twins, exits, library, contact)


KNOWLEDGE = load()
"""The committed knowledge. Read through the module at session start, so a test
can put a fixture in its place."""

#: The topic names ``read_topic`` offers, fixed at import because they become a
#: ``Literal`` in its schema. A ``Literal`` cannot be empty.
TOPIC_IDS: tuple[str, ...] = tuple(KNOWLEDGE.topics) or ("platform",)

__all__ = [
    "FRAMEWORKS",
    "KNOWLEDGE",
    "SITE",
    "SITE_HOST",
    "TOPIC_IDS",
    "Anchor",
    "Exit",
    "Framework",
    "Hit",
    "Knowledge",
    "Page",
    "Section",
    "Topic",
    "canonical_path",
    "fold",
    "is_spanish",
    "load",
    "norm",
    "tokens",
]
