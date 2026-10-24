"""What Javier knows about ssilva.cl, in three layers, read once at import.

- **L1** (``knowledge/L1.md``) is always in his prompt: who Ssilva is, how buying
  works in Chile in plain words, the site, and the roster of projects.
- **L2** is read on demand: a guide (``knowledge/L2/<topic>.md``) with
  ``read_topic``, every fact of one project (``knowledge/L2/proyectos/<slug>.md``)
  with ``read_project``.
- **L3** (``knowledge/L3/projects.json``, ``pages.json``) is the site itself:
  the roster ``find_projects`` filters, and every page with its sections in
  order, which the brain checks every move against — a page he opens, a section
  he scrolls to, a typology he selects.

The files are built offline (``knowledge/build.py``) and committed, so the brain
needs no network. Every one of them may be missing or empty and this module
still imports: the demos backend serves every brain from one process, and one
brain that cannot import takes the others down with it.
"""

from __future__ import annotations

import contextlib
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

_L1_FALLBACK = (
    "Ssilva (SSILVA Gestión Inmobiliaria) sells real-estate projects in Chile on ssilva.cl. "
    "Nothing more is loaded: answer only from what you read with your tools."
)

# ─── The site's filter vocabulary ──────────────────────────────────────────────

Region = str
"""``metropolitana``, ``valparaiso`` or ``otros``: the list's region filter."""
Property = str
"""``departamento``, ``casa``, ``oficina`` or ``local``: its property filter."""

#: The list filter's ids (``select#region``, ``select#property``), and the
#: commune checkboxes (``#commune<id>``), which only the Región Metropolitana has.
REGION_IDS: dict[Region, int] = {"metropolitana": 17, "valparaiso": 557, "otros": 556}
PROPERTY_IDS: dict[Property, int] = {"departamento": 34, "casa": 193, "oficina": 35, "local": 36}
COMMUNE_IDS: dict[str, int] = {
    "Las Condes": 18,
    "La Dehesa": 570,
    "Chicureo": 186,
    "Santiago": 363,
    "Estación Central": 564,
    "La Florida": 185,
    "Huechuraba": 190,
    "Macúl": 187,
    "Conchalí": 192,
    "Vitacura": 293,
}
REGION_LABELS: dict[Region, str] = {
    "metropolitana": "Región Metropolitana",
    "valparaiso": "Región de Valparaíso",
    "otros": "Otros",
}
PROPERTY_LABELS: dict[Property, str] = {
    "departamento": "departamentos",
    "casa": "casas",
    "oficina": "oficinas",
    "local": "locales comerciales",
}

#: What a visitor calls a region, folded.
_REGION_WORDS: dict[str, Region] = {
    "metropolitana": "metropolitana",
    "region metropolitana": "metropolitana",
    "rm": "metropolitana",
    "santiago": "metropolitana",
    "capital": "metropolitana",
    "valparaiso": "valparaiso",
    "region de valparaiso": "valparaiso",
    "v region": "valparaiso",
    "quinta region": "valparaiso",
    "5th region": "valparaiso",
    "costa": "valparaiso",
    "la costa": "valparaiso",
    "playa": "valparaiso",
    "la playa": "valparaiso",
    "mar": "valparaiso",
    "coast": "valparaiso",
    "the coast": "valparaiso",
    "beach": "valparaiso",
    "seaside": "valparaiso",
    "litoral": "valparaiso",
    "otros": "otros",
    "otra": "otros",
    "other": "otros",
    "sur": "otros",
    "south": "otros",
    "sur de chile": "otros",
}
#: What a visitor calls a type of property, folded.
_PROPERTY_WORDS: dict[str, Property] = {
    "departamento": "departamento",
    "departamentos": "departamento",
    "depto": "departamento",
    "deptos": "departamento",
    "depa": "departamento",
    "apartment": "departamento",
    "apartments": "departamento",
    "apartamento": "departamento",
    "flat": "departamento",
    "condo": "departamento",
    "casa": "casa",
    "casas": "casa",
    "house": "casa",
    "houses": "casa",
    "townhouse": "casa",
    "oficina": "oficina",
    "oficinas": "oficina",
    "office": "oficina",
    "offices": "oficina",
    "local": "local",
    "locales": "local",
    "local comercial": "local",
    "locales comerciales": "local",
    "shop": "local",
    "store": "local",
    "retail": "local",
    "commercial": "local",
}
#: What a visitor calls a place, folded → the comuna as the site writes it.
_COMUNA_ALIASES: dict[str, str] = {
    "vina": "Viña del Mar",
    "vina del mar": "Viña del Mar",
    "recreo": "Viña del Mar",
    "santiago centro": "Santiago",
    "centro de santiago": "Santiago",
    "downtown santiago": "Santiago",
    "barrio brasil": "Santiago",
    "barrio italia": "Santiago",
    "lo barnechea": "La Dehesa",
    "dehesa": "La Dehesa",
    "colina": "Chicureo",
    "macul": "Macúl",
    "renaca": "Reñaca",
    "cochoa": "Reñaca",
    "marbella": "Maitencillo",
    "zapallar": "Maitencillo",
    "pucon": "Pucón",
    "villarrica": "Pucón",
    "conchali": "Conchalí",
    "estacion central": "Estación Central",
}
#: The site's estados, and what a visitor calls them, folded.
ESTADOS = (
    "En blanco",
    "Inicio de obras",
    "En verde",
    "Obra gruesa",
    "Término de obra",
    "Próxima entrega",
    "Entrega inmediata",
)
_BUILDING = ("Inicio de obras", "En verde", "Obra gruesa", "Término de obra", "Próxima entrega")
_ESTADO_WORDS: dict[str, tuple[str, ...]] = {
    "entrega inmediata": ("Entrega inmediata",),
    "inmediata": ("Entrega inmediata",),
    "listo": ("Entrega inmediata",),
    "lista": ("Entrega inmediata",),
    "ready": ("Entrega inmediata",),
    "move in ready": ("Entrega inmediata",),
    "move-in ready": ("Entrega inmediata",),
    "immediate": ("Entrega inmediata",),
    "immediate delivery": ("Entrega inmediata",),
    "en blanco": ("En blanco",),
    "blanco": ("En blanco",),
    "off plan": ("En blanco",),
    "off-plan": ("En blanco",),
    "pre-construction": ("En blanco",),
    "preconstruction": ("En blanco",),
    "en verde": ("En verde",),
    "verde": ("En verde",),
    "en construccion": _BUILDING,
    "construccion": _BUILDING,
    "under construction": _BUILDING,
    "building": _BUILDING,
    "obra gruesa": ("Obra gruesa",),
    "termino de obra": ("Término de obra",),
    "inicio de obras": ("Inicio de obras",),
    "inicio de obra": ("Inicio de obras",),
}
#: The site's profiles, and what a visitor calls them, folded.
_PERFIL_WORDS: dict[str, str] = {
    "vivir": "Para vivir",
    "para vivir": "Para vivir",
    "habitar": "Para vivir",
    "live": "Para vivir",
    "to live": "Para vivir",
    "home": "Para vivir",
    "primera vivienda": "Para vivir",
    "first home": "Para vivir",
    "invertir": "Para invertir",
    "para invertir": "Para invertir",
    "inversion": "Para invertir",
    "inversionista": "Para invertir",
    "invest": "Para invertir",
    "investment": "Para invertir",
    "investor": "Para invertir",
    "rent": "Para invertir",
    "arrendar": "Para invertir",
    "segunda vivienda": "Segunda vivienda",
    "second home": "Segunda vivienda",
    "holiday home": "Segunda vivienda",
    "vacation home": "Segunda vivienda",
    "veraneo": "Segunda vivienda",
    "casa de playa": "Segunda vivienda",
    "beach house": "Segunda vivienda",
}


# ─── Text ──────────────────────────────────────────────────────────────────────

_TOKEN = re.compile(r"[a-z0-9ñ]+")
_STOP = frozenset(
    "a an and are as at be by can do does for from has have how i in is it its me my of on or "  # noqa: SIM905
    "the to what which with you your de del el la las los un una unos unas y o en con por para "
    "que es son se su sus al lo le mi tu".split()
)
#: Curly quotes and dashes, folded to their plain forms (by code point: they look alike).
_QUOTES = str.maketrans(
    {chr(0x2018): "'", chr(0x2019): "'", chr(0x201C): '"', chr(0x201D): '"'}
    | {chr(0x2013): "-", chr(0x2014): "-"}
)


def fold(text: str) -> str:
    """Case, accents, curly quotes, dashes and whitespace folded: "Viña" is "vina"."""
    text = unicodedata.normalize("NFKD", text.translate(_QUOTES))
    return " ".join(
        "".join(c for c in text if not unicodedata.combining(c)).lower().replace("ñ", "n").split()
    )


def norm(text: str) -> str:
    """Case, whitespace, curly quotes and dashes folded; accents kept."""
    return " ".join(text.translate(_QUOTES).lower().split())


def tokens(text: str) -> list[str]:
    """Folded words and numbers, without the words every passage has."""
    return [t for t in _TOKEN.findall(fold(text)) if t not in _STOP]


def canonical_path(path_or_url: str) -> str:
    """``https://www.ssilva.cl/Estocolmo/?a=1#b`` → ``/estocolmo``."""
    raw = path_or_url.strip()
    parts = urlsplit(raw if "://" in raw else f"https://x{'' if raw.startswith('/') else '/'}{raw}")
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/").lower()
    return path or "/"


def site_path(path: str) -> str:
    """A path as the site links it: with its trailing slash."""
    path = canonical_path(path)
    return "/" if path == "/" else f"{path}/"


#: The words Chrome's page translation puts in a typology's label, and the
#: site's own: a visitor reading ssilva.cl in English sees "2D | 2B BUTTERFLY"
#: for "2D | 2B MARIPOSA" (dev call ec152777).
_TYPOLOGY_WORDS = (
    (re.compile(r"\bbutterfly\b"), "mariposa"),
    (re.compile(r"\b(?:studio|study)\b"), "estudio"),
    (re.compile(r"\boffices?\b"), "oficina"),
    (re.compile(r"\bliving(?: room)?\b"), "estar"),
)


def typology_key(label: str) -> str:
    """``2D | 2B`` and ``2d|2b`` are one typology, and so are ``2D | 2B
    MARIPOSA`` and its translation ``2D | 2B BUTTERFLY``."""
    folded = fold(label)
    for rx, word in _TYPOLOGY_WORDS:
        folded = rx.sub(word, folded)
    return re.sub(r"[\s|\-]+", "", folded)


def match_typology(want: str, options: list[str] | tuple[str, ...]) -> str | None:
    """The typology label among ``options`` that ``want`` names: the same,
    else the only one it begins, else the only one that begins it."""
    w = typology_key(want)
    if not w:
        return None
    keyed = [(typology_key(o), o) for o in options]
    for k, o in keyed:
        if k == w:
            return o
    starts = [o for k, o in keyed if k.startswith(w)]
    if len(starts) >= 1:
        return min(starts, key=len)
    inside = [o for k, o in keyed if w.startswith(k)]
    return max(inside, key=len) if inside else None


# ─── The layers ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Topic:
    id: str
    title: str
    text: str


@dataclass(frozen=True)
class Section:
    heading: str
    key: str = ""
    """The canonical name the page scrolls to (``galería``, ``tipologías`` …),
    or empty for a heading that has none."""
    text: str = ""


@dataclass(frozen=True)
class Page:
    path: str
    title: str
    kind: str = "page"
    """``home``, ``projects``, ``project``, ``quote`` or ``page``."""
    project: str = ""
    """The project's slug, on a project or cotizar page."""
    sections: tuple[Section, ...] = ()
    text: str = ""

    @property
    def headings(self) -> tuple[str, ...]:
        return tuple(s.heading for s in self.sections if s.heading)

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(s.key for s in self.sections if s.key))


@dataclass(frozen=True)
class Units:
    typology: str
    count: int
    desde_uf: int | None
    hasta_uf: int | None


@dataclass(frozen=True)
class Project:
    slug: str
    name: str
    site_name: str
    path: str
    """The project page as the site links it (``/estocolmo/``); empty if none."""
    quote_path: str
    comuna: str
    region: Region
    tipos: tuple[Property, ...]
    desde_uf: int | None
    dormitorios: tuple[int, ...]
    estado: str
    perfil: tuple[str, ...]
    listed: bool = True
    banos: str = ""
    superficie_m2: int | None = None
    address: str = ""
    typologies: tuple[str, ...] = ()
    status: str = ""
    tour: bool = False
    lead_form: bool = False
    gallery_slides: int = 0
    phone: str = ""
    email: str = ""
    hours: str = ""
    units: tuple[Units, ...] = ()

    def line(self) -> str:
        """One line of a result list, in the site's words."""
        rooms = " y ".join(str(n) for n in self.dormitorios)
        parts = [
            f"{self.name} — {self.comuna} ({REGION_LABELS.get(self.region, self.region)})",
            "/".join(PROPERTY_LABELS.get(t, t) for t in self.tipos),
            f"desde {format_uf(self.desde_uf)} UF" if self.desde_uf else "",
            f"{rooms} dormitorios" if rooms else "",
            self.estado,
            "perfil: " + ", ".join(self.perfil) if self.perfil else "",
            f"path: {self.path}" if self.path else "no page of its own",
        ]
        return " · ".join(p for p in parts if p)


def format_uf(n: int | None) -> str:
    """``13976`` → ``13.976``, as the site writes it."""
    return "" if n is None else f"{n:,}".replace(",", ".")


@dataclass(frozen=True)
class Hit:
    """One search result: a page section, a guide or a project."""

    kind: str
    """``page``, ``topic`` or ``project``."""
    title: str
    snippet: str
    score: float
    path: str | None = None
    section: str | None = None
    ref: str | None = None
    """The topic id or the project slug."""


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
        phrase = fold(query)
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
            low = fold(p.text)
            if phrase in low:
                s *= 1.5
                at = low.find(phrase)
            else:
                at = min((i for w in q if (i := low.find(w)) >= 0), default=0)
            snippet = p.text[max(0, at - 80) : at + 240]
            h = p.hit
            key = (h.kind, h.path, h.ref, h.section)
            hit = Hit(h.kind, h.title, snippet, round(s, 2), h.path, h.section, h.ref)
            if key not in best or best[key].score < hit.score:
                best[key] = hit
        return sorted(best.values(), key=lambda h: -h.score)[:limit]


# ─── Filtering the roster ──────────────────────────────────────────────────────


def _split(value: str) -> list[str]:
    return [v.strip() for v in re.split(r",|;|/|\by\b|\bo\b|\band\b|\bor\b", value) if v.strip()]


def region_of(value: str | None) -> Region | None:
    """The list's region for what the visitor called it, or ``None``."""
    if not value:
        return None
    f = fold(value).removeprefix("region de ").removeprefix("region ")
    if f in _REGION_WORDS:
        return _REGION_WORDS[f]
    return next((r for w, r in _REGION_WORDS.items() if len(w) > 3 and w in f), None)


def property_of(value: str | None) -> Property | None:
    """The list's property type for what the visitor called it, or ``None``."""
    if not value:
        return None
    f = fold(value)
    if f in _PROPERTY_WORDS:
        return _PROPERTY_WORDS[f]
    return next((p for w, p in _PROPERTY_WORDS.items() if re.search(rf"\b{w}\b", f)), None)


def perfil_of(value: str | None) -> str | None:
    if not value:
        return None
    f = fold(value)
    if f in _PERFIL_WORDS:
        return _PERFIL_WORDS[f]
    return next((p for w, p in _PERFIL_WORDS.items() if re.search(rf"\b{w}\b", f)), None)


def estados_of(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    f = fold(value)
    if f in _ESTADO_WORDS:
        return _ESTADO_WORDS[f]
    for e in ESTADOS:
        if fold(e) == f:
            return (e,)
    hits = [es for w, es in _ESTADO_WORDS.items() if re.search(rf"\b{re.escape(w)}\b", f)]
    return max(hits, key=len) if hits else ()


@dataclass(frozen=True)
class Found:
    """What ``find_projects`` found: the matches, and the filters it had to
    drop to find any."""

    projects: tuple[Project, ...]
    dropped: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()
    """Values it could not read (a comuna it does not know)."""


# ─── Knowledge ─────────────────────────────────────────────────────────────────


@dataclass
class Knowledge:
    l1: str
    topics: dict[str, Topic]
    pages: dict[str, Page]
    projects: dict[str, Project] = field(default_factory=dict[str, Project])
    project_texts: dict[str, str] = field(default_factory=dict[str, str])
    _index: _Index = field(default_factory=_Index, repr=False)

    def __post_init__(self) -> None:
        # Indexed once, here: a search runs while the visitor waits.
        for p in self.pages.values():
            if p.kind in ("project", "quote"):
                continue
            self._index.add(Hit("page", p.title, "", 0, path=p.path), f"{p.title}\n{p.text}")
            for s in p.sections:
                self._index.add(
                    Hit("page", p.title, "", 0, path=p.path, section=s.heading or None),
                    f"{s.heading}\n{s.text}",
                )
        for t in self.topics.values():
            self._index.add(Hit("topic", t.title, "", 0, ref=t.id), t.text)
        for slug, pr in self.projects.items():
            text = self.project_texts.get(slug) or pr.line()
            hit = Hit("project", pr.name, "", 0, path=pr.path or None, ref=slug)
            self._index.add(hit, f"{pr.name} {pr.site_name} {pr.comuna}", weight=3)
            self._index.add(hit, text)
        self._index.done()

    # ── Lookups ──

    def page(self, path_or_url: str) -> Page | None:
        return self.pages.get(canonical_path(path_or_url))

    def project_at(self, path_or_url: str) -> Project | None:
        """The project whose page (or cotizar page) this is."""
        page = self.page(path_or_url)
        if page is not None and page.project:
            return self.projects.get(page.project)
        return None

    def project(self, name: str) -> Project | None:
        """The project ``name`` names: its name, its name on the site, its slug
        or its page, spelled loosely ("estocolmo", "Edificio Uniq", "el Limit")."""
        if not name.strip():
            return None
        if name.strip().startswith("/") or "ssilva.cl" in name:
            return self.project_at(name)
        want = _name_key(name)
        if not want:
            return None
        scored: list[tuple[float, Project]] = []
        for p in self.projects.values():
            keys = {_name_key(p.name), _name_key(p.site_name), _name_key(p.slug.replace("-", " "))}
            if want in keys:
                return p
            best = 0.0
            words = set(want.split())
            for k in keys:
                if not k:
                    continue
                ratio = min(len(want), len(k)) / max(len(want), len(k))
                if words <= set(k.split()):
                    best = max(best, 0.8 + 0.15 * ratio)
                elif set(k.split()) <= words:
                    best = max(best, 0.7 + 0.15 * ratio)
                best = max(best, SequenceMatcher(None, want, k).ratio())
            scored.append((best, p))
        scored.sort(key=lambda s: -s[0])
        if not scored or scored[0][0] < 0.62:
            return None
        if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.04 and scored[0][0] < 0.95:
            return None  # Two projects fit as well: "Lagunamar", "Parque el Rodeo".
        return scored[0][1]

    def project_text(self, p: Project) -> str:
        return self.project_texts.get(p.slug) or p.line()

    def search(self, query: str, limit: int = 6) -> list[Hit]:
        """The site's pages, the guides and the projects."""
        return self._index.search(query, limit)

    def find_projects(
        self,
        *,
        comuna: str | None = None,
        region: str | None = None,
        tipo: str | None = None,
        dormitorios: int | None = None,
        max_uf: float | None = None,
        min_uf: float | None = None,
        estado: str | None = None,
        perfil: str | None = None,
    ) -> Found:
        """The listed projects that fit, cheapest first. A filter nothing fits
        is dropped, least important first, and named in ``dropped``."""
        unknown: list[str] = []
        comunas: set[str] = set()
        regions: set[Region] = set()
        if comuna:
            for part in _split(comuna):
                found = self._comuna(part)
                if found:
                    comunas.add(found)
                elif (r := region_of(part)) is not None:
                    regions.add(r)
                else:
                    unknown.append(part)
        if region:
            r = region_of(region)
            if r is not None:
                regions.add(r)
            elif (c := self._comuna(region)) is not None:
                comunas.add(c)
            else:
                unknown.append(region)
        kind = property_of(tipo)
        if tipo and kind is None:
            unknown.append(tipo)
        states = estados_of(estado)
        if estado and not states:
            unknown.append(estado)
        profile = perfil_of(perfil)
        if perfil and profile is None:
            unknown.append(perfil)

        tests: list[tuple[str, Any]] = []
        if comunas or regions:
            label = ", ".join(sorted(comunas) + [REGION_LABELS[r] for r in sorted(regions)])
            tests.append((f"place ({label})", lambda p: p.comuna in comunas or p.region in regions))
        if kind is not None:
            tests.append((f"tipo ({kind})", lambda p: kind in p.tipos))
        if dormitorios is not None:
            want = int(dormitorios)
            tests.append(
                (
                    f"dormitorios ({want})",
                    lambda p: (
                        want in p.dormitorios
                        or (want == 0 and any("estudio" in fold(t) for t in p.typologies))
                    ),
                )
            )
        if max_uf is not None:
            tests.append(
                (f"max_uf ({max_uf:g})", lambda p: p.desde_uf is not None and p.desde_uf <= max_uf)
            )
        if min_uf is not None:
            tests.append(
                (f"min_uf ({min_uf:g})", lambda p: p.desde_uf is not None and p.desde_uf >= min_uf)
            )
        if states:
            tests.append((f"estado ({', '.join(states)})", lambda p: p.estado in states))
        if profile is not None:
            tests.append((f"perfil ({profile})", lambda p: profile in p.perfil))

        listed = [p for p in self.projects.values() if p.listed]
        # Dropped first when nothing fits: the softest wish, then the next.
        order = ("perfil", "estado", "min_uf", "dormitorios", "tipo", "max_uf", "place")
        dropped: list[str] = []
        active = list(tests)
        while True:
            hits = [p for p in listed if all(t(p) for _, t in active)]
            if hits or not active:
                break
            drop = next((t for name in order for t in active if t[0].startswith(name)), active[-1])
            active.remove(drop)
            dropped.append(drop[0])
        hits.sort(key=lambda p: (p.desde_uf or 10**9, p.name))
        return Found(tuple(hits), tuple(dropped), tuple(unknown))

    def _comuna(self, value: str) -> str | None:
        f = fold(value)
        if not f:
            return None
        names = {fold(p.comuna): p.comuna for p in self.projects.values() if p.listed}
        if f in names:
            return names[f]
        if f in _COMUNA_ALIASES:
            return _COMUNA_ALIASES[f]
        for alias, name in _COMUNA_ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", f):
                return name
        for key, name in names.items():
            if re.search(rf"\b{re.escape(key)}\b", f):
                return name
        return None


_NAME_NOISE = frozenset(
    [
        "edificio",
        "proyecto",
        "condominio",
        "oficinas",
        "parque",
        "el",
        "la",
        "los",
        "las",
        "de",
        "del",
        "the",
        "project",
        "building",
        "condo",
    ]
)


def _name_key(name: str) -> str:
    return " ".join(w for w in re.findall(r"[a-z0-9]+", fold(name)) if w not in _NAME_NOISE)


# ─── Loading ───────────────────────────────────────────────────────────────────


def _read_json(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("ssilva: {} not loaded: {}", path.name, exc)
        return []
    if not isinstance(data, list):
        return []
    return [cast(dict[str, Any], d) for d in cast(list[Any], data) if isinstance(d, dict)]


def _str(value: Any) -> str:
    return " ".join(str(value).split()) if isinstance(value, str | int | float) else ""


def _strs(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(_str(v) for v in cast(list[Any], value) if _str(v))


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _topic(path: Path) -> Topic:
    text = path.read_text(encoding="utf-8")
    first = text.lstrip().splitlines()[0] if text.strip() else ""
    title = first.lstrip("# ").strip() if first.startswith("#") else path.stem
    return Topic(path.stem, title, text)


def _page(raw: dict[str, Any]) -> Page | None:
    path = raw.get("path")
    if not isinstance(path, str):
        return None
    sections: list[Section] = []
    for s in cast(list[Any], raw.get("sections") or []):
        if isinstance(s, dict):
            s = cast(dict[str, Any], s)
            heading, key = _str(s.get("heading")), _str(s.get("key"))
            if heading or key:
                sections.append(Section(heading, key, _str(s.get("text"))))
    return Page(
        path=canonical_path(path),
        title=_str(raw.get("title")) or path,
        kind=_str(raw.get("kind")) or "page",
        project=_str(raw.get("project")),
        sections=tuple(sections),
        text=_str(raw.get("text")),
    )


def _project(raw: dict[str, Any]) -> Project | None:
    slug, name = _str(raw.get("slug")), _str(raw.get("name"))
    if not slug or not name:
        return None
    units: list[Units] = []
    for u in cast(list[Any], raw.get("units") or []):
        if isinstance(u, dict):
            u = cast(dict[str, Any], u)
            units.append(
                Units(
                    _str(u.get("typology")),
                    _int(u.get("count")) or 0,
                    _int(u.get("desde_uf")),
                    _int(u.get("hasta_uf")),
                )
            )
    rooms = cast(list[Any], raw.get("dormitorios") or [])
    return Project(
        slug=slug,
        name=name,
        site_name=_str(raw.get("site_name")) or name,
        path=_str(raw.get("path")),
        quote_path=_str(raw.get("quote_path")),
        comuna=_str(raw.get("comuna")),
        region=_str(raw.get("region")) or "otros",
        tipos=_strs(raw.get("tipos")) or ("departamento",),
        desde_uf=_int(raw.get("desde_uf")),
        dormitorios=tuple(n for r in rooms if (n := _int(r)) is not None),
        estado=_str(raw.get("estado")),
        perfil=_strs(raw.get("perfil")),
        listed=bool(raw.get("listed", True)),
        banos=_str(raw.get("banos")),
        superficie_m2=_int(raw.get("superficie_m2")),
        address=_str(raw.get("address")),
        typologies=_strs(raw.get("typologies")),
        status=_str(raw.get("status")),
        tour=bool(raw.get("tour")),
        lead_form=bool(raw.get("lead_form")),
        gallery_slides=_int(raw.get("gallery_slides")) or 0,
        phone=_str(raw.get("phone")),
        email=_str(raw.get("email")),
        hours=_str(raw.get("hours")),
        units=tuple(units),
    )


def load(root: Path = ROOT) -> Knowledge:
    """Every layer under ``root``; whatever is missing is empty."""
    try:
        l1 = (root / "L1.md").read_text(encoding="utf-8").strip() or _L1_FALLBACK
    except OSError:
        logger.warning("ssilva: L1.md not found; Javier runs on the fallback")
        l1 = _L1_FALLBACK
    topics: dict[str, Topic] = {}
    for path in sorted((root / "L2").glob("*.md")) if (root / "L2").is_dir() else []:
        topics[path.stem] = _topic(path)
    projects = {
        p.slug: p for raw in _read_json(root / "L3" / "projects.json") if (p := _project(raw))
    }
    texts: dict[str, str] = {}
    for slug in projects:
        with contextlib.suppress(OSError):
            texts[slug] = (root / "L2" / "proyectos" / f"{slug}.md").read_text(encoding="utf-8")
    pages = {p.path: p for raw in _read_json(root / "L3" / "pages.json") if (p := _page(raw))}
    return Knowledge(l1, topics, pages, projects, texts)


KNOWLEDGE = load()
"""The committed knowledge. Read through the module at session start, so a test
can put a fixture in its place."""

#: The guide names ``read_topic`` offers, fixed at import because they become a
#: ``Literal`` in its schema. A ``Literal`` cannot be empty.
TOPIC_IDS: tuple[str, ...] = tuple(KNOWLEDGE.topics) or ("comprar-en-chile",)

__all__ = [
    "COMMUNE_IDS",
    "ESTADOS",
    "KNOWLEDGE",
    "PROPERTY_IDS",
    "PROPERTY_LABELS",
    "REGION_IDS",
    "REGION_LABELS",
    "TOPIC_IDS",
    "Found",
    "Hit",
    "Knowledge",
    "Page",
    "Project",
    "Section",
    "Topic",
    "Units",
    "canonical_path",
    "estados_of",
    "fold",
    "format_uf",
    "load",
    "match_typology",
    "norm",
    "perfil_of",
    "property_of",
    "region_of",
    "site_path",
    "tokens",
    "typology_key",
]
