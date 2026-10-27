"""What Javier knows about Uno Salud Dental, in three layers, read once at import.

- **L1** (``knowledge/L1.md``) is always in his prompt: who Uno Salud is, the
  eleven specialties, how booking works for the visitor, Te llamamos,
  urgencias, the call center, payment and convenios in brief, and what the
  site does not publish.
- **L2** (``knowledge/L2/<topic>.md``) is a topic he reads with ``read_topic``
  when a question needs more than L1. Each file opens with ``# Title`` and a
  ``Sources:`` line.
- **L3** (``knowledge/L3/*.json``) is the data, built offline by
  ``knowledge/build.py`` from saved copies of the site:

  - ``anchors.json`` — the keyed catalogue of places a move can ring (the
    extension bundles the same file).
  - ``pages.json`` — every page's sections and FAQs, which ``search_site``
    searches and the brain checks every move against.
  - ``clinics.json`` — the 103 clinics, with their booking sucursal.
  - ``faqs.json``, ``promotions.json``, ``motivos.json``.

Every file may be missing or empty and this module still imports: the demos
backend serves every brain from one process, and one brain that cannot import
takes the others down with it. Nothing here reaches the site: it blocks
servers, and the brain runs where the site is not served.

Every comparison folds case and accents: "nunoa" is "Ñuñoa".
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

SITE_HOST = "www.unosalud.cl"
SITE = f"https://{SITE_HOST}"
BOOKING_PATH = "/agenda-tu-hora/"
#: The path the catalogue gives anchors that hold on every clinic page.
CLINIC_PAGE = "/clinicas/*/"

_L1_FALLBACK = (
    "Uno Salud Dental's website is www.unosalud.cl, and its booking is /agenda-tu-hora/. "
    "Nothing more is loaded: answer only from what you read with your tools, and offer the "
    "call center, 600 707 1010."
)

# ─── Text ──────────────────────────────────────────────────────────────────────

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
_STOP = frozenset(
    # English and Spanish words every passage has.
    """a an and are as at be by can do does for from has have how i in is it its me my of on
    or the to what which with you your el la los las un una unos unas de del y o en por para
    con que se su sus es al lo como mas tu te mi uno salud dental clinica clinicas""".split()  # noqa: SIM905
)


def fold(text: str) -> str:
    """Lower case, without accents: "Ñuñoa" → "nunoa"."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    """Folded words and numbers, without the words every passage has."""
    return [t for t in _TOKEN.findall(fold(text)) if t not in _STOP]


def norm(text: str) -> str:
    """Case, accents and whitespace folded."""
    return " ".join(fold(text).split())


def canonical_path(path_or_url: str) -> str:
    """``https://www.unosalud.cl/Clinicas/Moneda?a=1#b`` → ``/clinicas/moneda/``:
    the site's paths end in a slash."""
    raw = path_or_url.strip()
    parts = urlsplit(raw if "://" in raw else f"https://x{'' if raw.startswith('/') else '/'}{raw}")
    path = re.sub(r"/{2,}", "/", parts.path).strip("/").lower()
    return f"/{path}/" if path else "/"


def is_clinic_page(path: str) -> bool:
    p = canonical_path(path)
    return p.startswith("/clinicas/") and p != "/clinicas/"


#: Words a visitor says for a treatment, and the site's words for it.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "frenillos": ("ortodoncia", "brackets"),
    "brackets": ("ortodoncia", "frenillos"),
    "braces": ("ortodoncia", "brackets"),
    "alineadores": ("ortodoncia", "invisible"),
    "aligners": ("ortodoncia", "alineadores"),
    "limpieza": ("destartraje",),
    "cleaning": ("limpieza",),
    "implant": ("implante",),
    "implants": ("implantes",),
    "whitening": ("blanqueamiento",),
    "conducto": ("endodoncia",),
    "canal": ("endodoncia", "conducto"),
    "encias": ("periodoncia",),
    "gums": ("encias", "periodoncia"),
    "ninos": ("odontopediatria",),
    "children": ("odontopediatria",),
    "kids": ("odontopediatria",),
    "xray": ("radiografias",),
    "radiografia": ("radiografias",),
    "muela": ("extraccion", "cirugia"),
    "juicio": ("muelas", "cirugia"),
    "protesis": ("rehabilitacion",),
    "dentures": ("protesis", "rehabilitacion"),
    "bruxismo": ("plano", "relajacion"),
    "urgency": ("urgencias",),
    "emergency": ("urgencias",),
    "urgencia": ("urgencias",),
    "price": ("precio",),
    "prices": ("precios",),
    "cost": ("precio", "cuesta"),
    "plan": ("planes", "sonrisa"),
    "plans": ("planes", "sonrisa"),
    "insurance": ("seguro", "complementario"),
}


def _expand(words: list[str]) -> list[str]:
    out = list(words)
    for w in words:
        out.extend(_SYNONYMS.get(w, ()))
    return list(dict.fromkeys(out))


def _matches(want: str, have: set[str]) -> float:
    """1 for the word itself, 0.7 for a word it starts (implante → implantes), else 0."""
    if want in have:
        return 1.0
    if len(want) >= 4 and any(
        h.startswith(want) or (len(h) >= 4 and want.startswith(h)) for h in have
    ):
        return 0.7
    return 0.0


# ─── The layers ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Topic:
    id: str
    title: str
    text: str


@dataclass(frozen=True)
class Anchor:
    """A place a move can ring: on ``path`` (``/clinicas/*/`` for every clinic page)."""

    key: str
    path: str
    selector: str = ""
    text: str = ""
    es: str = ""
    en: str = ""
    faq: str = ""


@dataclass(frozen=True)
class Faq:
    key: str
    q: str
    a: str
    path: str


@dataclass(frozen=True)
class Section:
    heading: str
    anchor: str = ""
    text: str = ""


@dataclass(frozen=True)
class Page:
    path: str
    title: str
    kind: str = ""
    sections: tuple[Section, ...] = ()
    faqs: tuple[Faq, ...] = ()


@dataclass(frozen=True)
class Clinic:
    key: str
    id: str
    name: str
    address: str = ""
    comuna: str = ""
    region: str = ""
    hours: str = ""
    references: str = ""
    path: str = ""
    url: str = ""
    maps_url: str = ""
    booking_id: str = ""
    booking_name: str = ""
    booking_region: str = ""
    booking_comuna: str = ""


@dataclass(frozen=True)
class Promotion:
    key: str
    card: str
    landing: str
    valid_until: str = ""
    promo: str = ""
    summary: str = ""


@dataclass(frozen=True)
class Motivo:
    id: int
    name: str
    en: str = ""


@dataclass(frozen=True)
class Hit:
    """One search result: a page section, an FAQ, a clinic or a promotion."""

    kind: str
    title: str
    snippet: str
    score: float
    path: str | None = None
    anchor: str | None = None
    faq: str | None = None


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
        q = _expand(tokens(query))
        if not q:
            return []
        n = len(self.passages)
        phrase = norm(query)
        k1, b = 1.4, 0.75
        best: dict[tuple[str, str | None, str | None, str | None, str], Hit] = {}
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
            snippet = p.text[max(0, at - 80) : at + 280]
            h = p.hit
            key = (h.kind, h.path, h.anchor, h.faq, h.title)
            hit = Hit(h.kind, h.title, snippet, round(s, 2), h.path, h.anchor, h.faq)
            if key not in best or best[key].score < hit.score:
                best[key] = hit
        return sorted(best.values(), key=lambda h: -h.score)[:limit]


@dataclass
class Knowledge:
    l1: str
    topics: dict[str, Topic]
    pages: dict[str, Page]
    anchors: dict[str, Anchor] = field(default_factory=dict[str, Anchor])
    clinics: tuple[Clinic, ...] = ()
    faqs: tuple[Faq, ...] = ()
    promotions: tuple[Promotion, ...] = ()
    motivos: tuple[Motivo, ...] = ()
    _site: _Index = field(default_factory=_Index, repr=False)

    def __post_init__(self) -> None:
        # Indexed once, here: a search runs while the visitor waits.
        for p in self.pages.values():
            for s in p.sections:
                self._site.add(
                    Hit("page", f"{p.title} — {s.heading}", "", 0, p.path, s.anchor or None),
                    f"{s.heading}\n{s.text}",
                )
            for f in p.faqs:
                self._site.add(Hit("faq", f.q, "", 0, p.path, f.key, f.key), f"{f.q}\n{f.a}")
        for f in self.faqs:
            self._site.add(Hit("faq", f.q, "", 0, f.path, f.key, f.key), f"{f.q}\n{f.a}")
        for c in self.clinics:
            self._site.add(
                Hit("clinic", c.name, "", 0, c.path, f"clinicas_{c.key}"),
                f"{c.name}\n{c.address} {c.comuna} {c.region}\n{c.references}",
            )
        for pr in self.promotions:
            self._site.add(
                Hit("promotion", pr.card, "", 0, "/promociones/", f"promo_{pr.key}"),
                f"{pr.card}\n{pr.summary}",
            )
        self._site.done()

    # ── Lookups ──

    def page(self, path_or_url: str) -> Page | None:
        path = canonical_path(path_or_url)
        if (p := self.pages.get(path)) is not None:
            return p
        if is_clinic_page(path):
            return self.pages.get(CLINIC_PAGE)
        return None

    def anchor(self, key: str) -> Anchor | None:
        return self.anchors.get(key)

    def anchors_on(self, path: str) -> list[Anchor]:
        """The places of the page at ``path``."""
        p = canonical_path(path)
        want = CLINIC_PAGE if is_clinic_page(p) else p
        return [a for a in self.anchors.values() if a.path == want]

    def anchor_on(self, key: str, path: str) -> bool:
        a = self.anchors.get(key)
        if a is None:
            return False
        p = canonical_path(path)
        return a.path == p or (a.path == CLINIC_PAGE and is_clinic_page(p))

    def search(self, query: str, limit: int = 6) -> list[Hit]:
        return self._site.search(query, limit)

    def clinic(self, key_or_name: str) -> Clinic | None:
        want = norm(key_or_name)
        for c in self.clinics:
            if want in (c.key, norm(c.name), norm(c.path.strip("/").split("/")[-1])):
                return c
        return None

    def clinic_by_path(self, path: str) -> Clinic | None:
        p = canonical_path(path)
        return next((c for c in self.clinics if c.path == p), None)

    def find_clinics(self, query: str, n: int = 4) -> list[Clinic]:
        """Clinics by comuna, region, name, street, landmark or metro station,
        best first. A comuna said outright wins over a word in an address."""
        want = _expand(tokens(query))
        if not want:
            return []
        phrase = norm(query)
        scored: list[tuple[float, int, Clinic]] = []
        for i, c in enumerate(self.clinics):
            fields = (
                (c.comuna, 4.0),
                (c.name, 3.0),
                (c.booking_name, 2.0),
                (c.references, 2.0),
                (c.region, 1.0),
                (c.address, 1.5),
            )
            s = 0.0
            for text, weight in fields:
                have = set(tokens(text))
                s += weight * sum(_matches(w, have) for w in want)
                if len(phrase) > 3 and f" {phrase} " in f" {norm(text)} ":
                    s += weight * 2
            if s > 0:
                scored.append((s, -i, c))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        if not scored:
            return []
        top = scored[0][0]
        return [c for s, _, c in scored if s >= top * 0.5][:n]

    def comuna_sucursales(self, comuna: str) -> list[Clinic]:
        """The clinics the booking lists in a comuna."""
        f = norm(comuna)
        return [c for c in self.clinics if norm(c.comuna) == f or norm(c.booking_comuna) == f]

    def motivo(self, motivo: int) -> Motivo | None:
        return next((m for m in self.motivos if m.id == motivo), None)

    def promotion(self, key_or_code: str) -> Promotion | None:
        want = norm(key_or_code)
        for p in self.promotions:
            if want and want in (norm(p.key), norm(p.promo), norm(p.card)):
                return p
        return None


# ─── Loading ───────────────────────────────────────────────────────────────────


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("unosalud: {} not loaded: {}", path.name, exc)
        return None


def _rows(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        return []
    return [cast(dict[str, Any], d) for d in cast(list[Any], data) if isinstance(d, dict)]


def _str(value: Any) -> str:
    return " ".join(str(value).split()) if isinstance(value, str | int | float) else ""


def _topic(path: Path) -> Topic:
    text = path.read_text(encoding="utf-8")
    first = text.lstrip().splitlines()[0] if text.strip() else ""
    title = first.lstrip("# ").strip() if first.startswith("#") else path.stem
    return Topic(path.stem, title, text)


def _anchors(data: Any) -> dict[str, Anchor]:
    if not isinstance(data, dict):
        return {}
    out: dict[str, Anchor] = {}
    for key, raw in cast(dict[str, Any], data).items():
        if key.startswith("_") or not isinstance(raw, dict):
            continue
        v = cast(dict[str, Any], raw)
        label = cast(dict[str, Any], v.get("label") or {})
        out[key] = Anchor(
            key=key,
            path=_str(v.get("path")) or "/",
            selector=_str(v.get("selector")),
            text=_str(v.get("text")),
            es=_str(label.get("es")),
            en=_str(label.get("en")),
            faq=_str(v.get("faq")),
        )
    return out


def _pages(data: Any, anchors: dict[str, Anchor]) -> dict[str, Page]:
    faq_keys: dict[tuple[str, str], str] = {
        (a.path, a.faq): a.key for a in anchors.values() if a.faq
    }
    out: dict[str, Page] = {}
    for raw in _rows(data):
        path = _str(raw.get("path"))
        if not path:
            continue
        path = path if path == CLINIC_PAGE else canonical_path(path)
        sections = tuple(
            Section(_str(s.get("heading")), _str(s.get("anchor")), _str(s.get("text")))
            for s in _rows(raw.get("sections"))
            if _str(s.get("heading"))
        )
        faqs = tuple(
            Faq(
                faq_keys.get((path, _str(f.get("n"))), ""),
                _str(f.get("q")),
                _str(f.get("a")),
                path,
            )
            for f in _rows(raw.get("faqs"))
        )
        out[path] = Page(path, _str(raw.get("title")), _str(raw.get("kind")), sections, faqs)
    return out


def load(root: Path = ROOT) -> Knowledge:
    """Every layer under ``root``; whatever is missing is empty."""
    try:
        l1 = (root / "L1.md").read_text(encoding="utf-8").strip() or _L1_FALLBACK
    except OSError:
        logger.warning("unosalud: L1.md not found; Javier runs on the fallback")
        l1 = _L1_FALLBACK
    topics: dict[str, Topic] = {}
    for path in sorted((root / "L2").glob("*.md")) if (root / "L2").is_dir() else []:
        topics[path.stem] = _topic(path)
    l3 = root / "L3"
    anchors = _anchors(_read(l3 / "anchors.json"))
    clinic_fields = set(Clinic.__dataclass_fields__)
    clinics = tuple(
        Clinic(**{k: _str(v) for k, v in r.items() if k in clinic_fields})
        for r in _rows(_read(l3 / "clinics.json"))
        if _str(r.get("name")) and _str(r.get("key"))
    )
    faqs = tuple(
        Faq(_str(r.get("key")), _str(r.get("q")), _str(r.get("a")), "/preguntas-frecuentes/")
        for r in _rows(_read(l3 / "faqs.json"))
        if _str(r.get("q"))
    )
    promo_fields = set(Promotion.__dataclass_fields__)
    promotions = tuple(
        Promotion(**{k: _str(v) for k, v in r.items() if k in promo_fields})
        for r in _rows(_read(l3 / "promotions.json"))
        if _str(r.get("key"))
    )
    motivos = tuple(
        Motivo(int(r["id"]), _str(r.get("name")), _str(r.get("en")))
        for r in _rows(_read(l3 / "motivos.json"))
        if isinstance(r.get("id"), int)
    )
    return Knowledge(
        l1,
        topics,
        _pages(_read(l3 / "pages.json"), anchors),
        anchors=anchors,
        clinics=clinics,
        faqs=faqs,
        promotions=promotions,
        motivos=motivos,
    )


KNOWLEDGE = load()
"""The committed knowledge. Read through the module at session start, so a test
can put a fixture in its place."""

#: The topic names ``read_topic`` offers, fixed at import because they become a
#: ``Literal`` in its schema. A ``Literal`` cannot be empty.
TOPIC_IDS: tuple[str, ...] = tuple(KNOWLEDGE.topics) or ("empresa",)

__all__ = [
    "BOOKING_PATH",
    "CLINIC_PAGE",
    "KNOWLEDGE",
    "SITE",
    "SITE_HOST",
    "TOPIC_IDS",
    "Anchor",
    "Clinic",
    "Faq",
    "Hit",
    "Knowledge",
    "Motivo",
    "Page",
    "Promotion",
    "Section",
    "Topic",
    "canonical_path",
    "fold",
    "is_clinic_page",
    "load",
    "norm",
    "tokens",
]
