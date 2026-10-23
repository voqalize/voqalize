"""The figures a career or programme page shows, read and worked out here.

The page reports what it shows as text and table rows (:mod:`.protocol`); this
module turns them into numbers, does the PAES arithmetic, and writes each
figure the way the voice must say it. None of it fetches anything: a fee comes
from the visitor's browser or not at all.

**Fees** are free text on the career's "Requisitos y Aranceles" tab: "Año 2027
Matrícula $277.456 Arancel anual $7.167.421 Titulación 11 UF", in several
spellings ("Arancel: $3.427.149", a "Descuento" block after it on online
careers). :func:`parse_fees` reads them tolerantly.

**Weights** are the table beside it: NEM, Ranking, Competencia lectora,
Matemática, "Historia y Ciencias Sociales / Ciencias" at "10% ó 10%" (the
higher of the two counts), sometimes Matemática 2, then the minimum weighted
score and the minimum average of Lectora and Matemática. :func:`estimate`
weighs the visitor's own scores with them. The model never does this sum: a
weighted average said aloud is a number nobody can check.

**Spoken numbers**: the voice reads "$7.167.421" digit group by digit group,
and a model asked to write it in words reshapes it as often as not. So every
figure handed to the model carries its words (:func:`pesos_es`,
:func:`pesos_en`), and :func:`money_for_the_voice` turns any amount still in
digits into words before the voice reads it.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# ─── Numbers as words ──────────────────────────────────────────────────────────

_ES_UNITS = [
    "cero",
    "uno",
    "dos",
    "tres",
    "cuatro",
    "cinco",
    "seis",
    "siete",
    "ocho",
    "nueve",
    "diez",
    "once",
    "doce",
    "trece",
    "catorce",
    "quince",
    "dieciséis",
    "diecisiete",
    "dieciocho",
    "diecinueve",
    "veinte",
    "veintiuno",
    "veintidós",
    "veintitrés",
    "veinticuatro",
    "veinticinco",
    "veintiséis",
    "veintisiete",
    "veintiocho",
    "veintinueve",
]
_ES_TENS = [
    "_",
    "_",
    "_",
    "treinta",
    "cuarenta",
    "cincuenta",
    "sesenta",
    "setenta",
    "ochenta",
    "noventa",
]
_ES_HUNDREDS = [
    "_",
    "ciento",
    "doscientos",
    "trescientos",
    "cuatrocientos",
    "quinientos",
    "seiscientos",
    "setecientos",
    "ochocientos",
    "novecientos",
]


def _es_below_1000(n: int, short: bool) -> str:
    """0 < n < 1000. ``short``: "un" for a final one, before a noun or "mil"."""
    if n == 100:
        return "cien"
    hundreds, rest = divmod(n, 100)
    out: list[str] = []
    if hundreds:
        out.append(_ES_HUNDREDS[hundreds])
    if rest:
        if rest < 30:
            word = _ES_UNITS[rest]
        else:
            tens, unit = divmod(rest, 10)
            word = _ES_TENS[tens] + (f" y {_ES_UNITS[unit]}" if unit else "")
        if short:
            word = re.sub(r"veintiuno$", "veintiún", word)
            word = re.sub(r"\buno$", "un", word)
        out.append(word)
    return " ".join(out)


def number_es(n: int, *, short: bool = False) -> str:
    """``n`` in Spanish words: 7167421 → "siete millones ciento sesenta y siete
    mil cuatrocientos veintiuno"; with ``short``, a final "uno" is "un"
    ("veintiún pesos")."""
    if n < 0:
        return f"menos {number_es(-n, short=short)}"
    if n == 0:
        return "cero"
    millions, rest = divmod(n, 1_000_000)
    thousands, units = divmod(rest, 1000)
    out: list[str] = []
    if millions:
        out.append("un millón" if millions == 1 else f"{number_es(millions, short=True)} millones")
    if thousands:
        out.append("mil" if thousands == 1 else f"{_es_below_1000(thousands, True)} mil")
    if units:
        out.append(_es_below_1000(units, short))
    return " ".join(out)


_EN_UNITS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_EN_TENS = ["_", "_", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _en_below_1000(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    out: list[str] = []
    if hundreds:
        out.append(f"{_EN_UNITS[hundreds]} hundred")
    if rest:
        if rest < 20:
            out.append(_EN_UNITS[rest])
        else:
            tens, unit = divmod(rest, 10)
            out.append(_EN_TENS[tens] + (f"-{_EN_UNITS[unit]}" if unit else ""))
    return " ".join(out)


def number_en(n: int) -> str:
    """``n`` in English words: 7167421 → "seven million one hundred sixty-seven
    thousand four hundred twenty-one"."""
    if n < 0:
        return f"minus {number_en(-n)}"
    if n == 0:
        return "zero"
    parts: list[str] = []
    for size, name in ((1_000_000_000, "billion"), (1_000_000, "million"), (1000, "thousand")):
        if n >= size:
            parts.append(f"{_en_below_1000(n // size)} {name}")
            n %= size
    if n:
        parts.append(_en_below_1000(n))
    return " ".join(parts)


def pesos_es(n: int) -> str:
    """An amount of Chilean pesos as said: "doscientos setenta y siete mil
    cuatrocientos cincuenta y seis pesos"; "siete millones de pesos"."""
    if n == 1:
        return "un peso"
    of = " de" if n >= 1_000_000 and n % 1_000_000 == 0 else ""
    return f"{number_es(n, short=True)}{of} pesos"


def pesos_en(n: int) -> str:
    return "one peso" if n == 1 else f"{number_en(n)} pesos"


def decimal_es(x: float) -> str:
    """682.5 → "seiscientos ochenta y dos coma cinco"; whole numbers plainly."""
    whole, frac = f"{x:.2f}".split(".")
    frac = frac.rstrip("0")
    out = number_es(int(whole))
    if frac:
        out += " coma " + (
            f"cero {number_es(int(frac))}" if frac.startswith("0") else number_es(int(frac))
        )
    return out


def decimal_en(x: float) -> str:
    whole, frac = f"{x:.2f}".split(".")
    frac = frac.rstrip("0")
    out = number_en(int(whole))
    return out + (" point " + " ".join(_EN_UNITS[int(d)] for d in frac) if frac else "")


def amount(text: str) -> int | None:
    """ "$7.167.421" → 7167421; anything without digits → ``None``."""
    digits = re.sub(r"\D", "", text)
    return int(digits) if digits else None


#: A peso amount still in digits: "$7.167.421", "$ 277.456", "$7,167,421".
_MONEY = re.compile(r"\$\s?(\d{1,3}(?:[.,]\d{3})+|\d+)(?![\d.,]*\d)")
#: An amount in UF: "11 UF", "10,5 UF".
_UF = re.compile(r"\b(\d+)(?:[.,](\d+))?\s*UF\b")


def money_for_the_voice(text: str, lang: str) -> str:
    """``text`` with every peso amount and UF count in digits said in words, in
    ``lang`` ("es" or "en"): the voice reads digit groups one by one."""

    def pesos(m: re.Match[str]) -> str:
        n = amount(m.group(1))
        if n is None:
            return m.group(0)
        return pesos_es(n) if lang == "es" else pesos_en(n)

    def uf(m: re.Match[str]) -> str:
        whole, frac = int(m.group(1)), m.group(2)
        if lang == "es":
            said = number_es(whole) + (f" coma {number_es(int(frac))}" if frac else "")
        else:
            said = number_en(whole) + (
                f" point {' '.join(_EN_UNITS[int(d)] for d in frac)}" if frac else ""
            )
        return f"{said} UF"

    return _UF.sub(uf, _MONEY.sub(pesos, text))


# ─── Fees ──────────────────────────────────────────────────────────────────────


def _clean(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).replace("\xa0", " ").split())


_YEAR = re.compile(r"A[ñn]o\s*(20\d\d)", re.IGNORECASE)
_MATRICULA = re.compile(r"Matr[ií]cula\s*:?[^$\d]{0,12}\$\s?(\d[\d.,]*)", re.IGNORECASE)
_ARANCEL = re.compile(r"Arancel(?:\s+anual|\s+total)?\s*:?[^$\d]{0,12}\$\s?(\d[\d.,]*)", re.I)
_TITULACION = re.compile(r"(?:Titulaci[oó]n|Graduaci[oó]n)\s*:?\s*(\d+(?:[.,]\d+)?)\s*UF", re.I)
_DISCOUNT = re.compile(r"Descuentos?\s*:?\s*(.{3,200})", re.IGNORECASE)


@dataclass(frozen=True)
class Fees:
    """One career's fees, as its page wrote them."""

    year: int | None = None
    matricula: int | None = None
    arancel: int | None = None
    titulacion_uf: str | None = None
    discount: str = ""
    raw: str = ""

    @property
    def found(self) -> bool:
        return self.matricula is not None or self.arancel is not None


def parse_fees(text: str) -> Fees:
    """The fees in the free text of an Aranceles block; fields it lacks are ``None``."""
    t = _clean(text)
    year = _YEAR.search(t)
    mat = _MATRICULA.search(t)
    ara = _ARANCEL.search(t)
    tit = _TITULACION.search(t)
    disc = _DISCOUNT.search(t)
    return Fees(
        year=int(year.group(1)) if year else None,
        matricula=amount(mat.group(1)) if mat else None,
        arancel=amount(ara.group(1)) if ara else None,
        titulacion_uf=tit.group(1).replace(",", ".") if tit else None,
        discount=disc.group(1).strip() if disc else "",
        raw=t,
    )


def _cl(n: int) -> str:
    """An amount as Chile writes it: 7.167.421."""
    return f"{n:,}".replace(",", ".")


def describe_fees(fees: Fees, lang: str) -> str:
    """The fees for a note to the model, each with the words to say it in."""
    say = pesos_es if lang == "es" else pesos_en
    parts: list[str] = []
    if fees.year:
        parts.append(f"year {fees.year}")
    if fees.matricula is not None:
        parts.append(f"Matrícula ${_cl(fees.matricula)} — say “{say(fees.matricula)}”")
    if fees.arancel is not None:
        parts.append(f"Arancel anual ${_cl(fees.arancel)} — say “{say(fees.arancel)}”")
    if fees.titulacion_uf:
        n = fees.titulacion_uf
        words = money_for_the_voice(f"{n.replace('.', ',')} UF", lang)
        parts.append(f"Titulación {n} UF — say “{words}”")
    if fees.discount:
        parts.append(f"discount on the page: {fees.discount}")
    return "; ".join(parts)


# ─── Postgraduate money and dates ──────────────────────────────────────────────

_MONEY_ITEM = re.compile(
    r"([A-Za-zÁÉÍÓÚáéíóúÑñ][A-Za-zÁÉÍÓÚáéíóúÑñ ]{1,40}?)\s*:?\s*\$\s?(\d{1,3}(?:[.,]\d{3})+|\d+)"
)
_DATE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d\d)\b")
_ISO_DATE = re.compile(r"^(20\d\d)-?(\d\d)-?(\d\d)$")
_MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]
_MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


#: "01 octubre 2026", "1 de octubre de 2026": how the REST API and the page write a date.
_NAMED_DATE = re.compile(
    r"\b(\d{1,2})\s+(?:de\s+)?(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|octubre|noviembre|diciembre)\s+(?:de\s+|del\s+)?(20\d\d)\b"
)


def money_items(text: str) -> list[tuple[str, int]]:
    """Each "Label $N" in ``text``: [("Arancel Total", 5250000), ("Matrícula", 200000)]."""
    out: list[tuple[str, int]] = []
    for m in _MONEY_ITEM.finditer(_clean(text)):
        label = " ".join(m.group(1).split()[-3:])
        if (n := amount(m.group(2))) is not None:
            out.append((label, n))
    return out


def date_of(text: str) -> tuple[int, int, int] | None:
    """(year, month, day) of "01-10-2026", "30/10/2026", "20261001" or "2026-10-01"."""
    t = text.strip()
    if m := _ISO_DATE.match(t):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    elif m := _DATE.search(t):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    elif m := _NAMED_DATE.search(_fold(t)):
        d, mo, y = int(m.group(1)), _MESES.index(m.group(2)) + 1, int(m.group(3))
    else:
        return None
    return (y, mo, d) if 1 <= mo <= 12 and 1 <= d <= 31 else None


def date_said(text: str, lang: str) -> str:
    """A date as written on the site, as words: "1 de octubre de 2026"; the
    text itself when it is no date."""
    when = date_of(text)
    if when is None:
        return text
    y, mo, d = when
    if lang == "es":
        return f"{d} de {_MESES[mo - 1]} de {y}"
    return f"{_MONTHS[mo - 1]} {d}, {y}"


def dates_in(text: str) -> list[str]:
    """Every dd/mm/yyyy date in ``text``, as written."""
    return [m.group(0) for m in _DATE.finditer(text)]


# ─── PAES weights ──────────────────────────────────────────────────────────────

Criterion = str
#: The criteria a weights table can carry, in the order the site lists them.
CRITERIA: tuple[Criterion, ...] = (
    "nem",
    "ranking",
    "lectora",
    "matematica",
    "historia_ciencias",
    "historia",
    "ciencias",
    "m2",
)
NAMES_ES = {
    "nem": "NEM",
    "ranking": "Ranking",
    "lectora": "Competencia Lectora",
    "matematica": "Matemática",
    "historia_ciencias": "Historia o Ciencias, la más alta",
    "historia": "Historia y Ciencias Sociales",
    "ciencias": "Ciencias",
    "m2": "Matemática 2",
}

_PERCENT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).split())


def _criterion(label: str) -> Criterion | str | None:
    f = _fold(label)
    if "minimo" in f and "ponderado" in f:
        return "min_weighted"
    if "minimo" in f and ("promedio" in f or "lym" in f or "l y m" in f):
        return "min_avg_lm"
    if "nem" in f.split() or f.startswith("nem") or "notas de ensenanza media" in f:
        return "nem"
    if "ranking" in f:
        return "ranking"
    if "lectora" in f or "lenguaje" in f:
        return "lectora"
    if re.search(r"matematica\s*(2|ii)\b|\bm2\b", f):
        return "m2"
    if "matematica" in f or re.search(r"\bm1\b", f):
        return "matematica"
    if "historia" in f and "ciencias" in f.replace("ciencias sociales", ""):
        return "historia_ciencias"
    if "historia" in f:
        return "historia"
    if "ciencias" in f:
        return "ciencias"
    return None


@dataclass(frozen=True)
class Weights:
    """A career's PAES weights, as fractions of one, and its minimums."""

    weights: dict[Criterion, float] = field(default_factory=dict[Criterion, float])
    min_weighted: int | None = None
    min_avg_lm: int | None = None
    rows: tuple[tuple[str, str], ...] = ()

    @property
    def total(self) -> float:
        return round(sum(self.weights.values()), 4)

    @property
    def found(self) -> bool:
        return bool(self.weights)


def parse_weights(rows: list[tuple[str, str]]) -> Weights:
    """The weights table's rows (label, value as written) as :class:`Weights`.
    "10% ó 10%" on the Historia/Ciencias row is one weight for the higher of
    the two; a dash or a blank is no weight."""
    weights: dict[Criterion, float] = {}
    minimum: dict[str, int] = {}
    for label, value in rows:
        kind = _criterion(label)
        if kind is None:
            continue
        if kind in ("min_weighted", "min_avg_lm"):
            if m := _NUMBER.search(value.replace(".", "")):
                minimum[kind] = int(float(m.group(0).replace(",", ".")))
            continue
        if m := _PERCENT.search(value):
            weights[kind] = float(m.group(1).replace(",", ".")) / 100
    return Weights(
        weights,
        minimum.get("min_weighted"),
        minimum.get("min_avg_lm"),
        tuple(rows),
    )


def describe_weights(w: Weights) -> str:
    parts = [f"{NAMES_ES[k]} {round(v * 100, 2):g}%" for k, v in w.weights.items()]
    if w.min_weighted is not None:
        parts.append(
            "minimum weighted score: none (the table says 0)"
            if w.min_weighted == 0
            else f"minimum weighted score {w.min_weighted}"
        )
    if w.min_avg_lm is not None:
        parts.append(f"minimum average of Lectora and Matemática {w.min_avg_lm}")
    return "; ".join(parts)


@dataclass(frozen=True)
class Scores:
    """The visitor's own scores, in PAES points (100 to 1000). NEM and Ranking
    are their converted scores, not their grade average."""

    nem: int | None = None
    ranking: int | None = None
    lectora: int | None = None
    matematica: int | None = None
    historia: int | None = None
    ciencias: int | None = None
    m2: int | None = None


@dataclass(frozen=True)
class Estimate:
    score: float | None
    parts: tuple[tuple[Criterion, float, int, float], ...] = ()
    """(criterion, weight, points, points times weight), in the table's order."""
    missing: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()
    used_for_hc: str | None = None
    meets_weighted: bool | None = None
    avg_lm: float | None = None
    meets_avg: bool | None = None
    weights: Weights = field(default_factory=Weights)


_POINTS = (100, 1000)


def estimate(w: Weights, s: Scores) -> Estimate:
    """The visitor's weighted score for a career, from its own weights.

    Every weighted criterion needs a score; the Historia/Ciencias slot takes
    the higher of the two they gave. A NEM or Ranking said as a grade (6.2)
    is not a score: it is reported as a problem, never converted here. The
    minimums are compared as the table states them; a minimum of 0 is none."""
    problems: list[str] = []
    given = {k: v for k, v in vars(s).items() if v is not None}
    for k, v in given.items():
        if not _POINTS[0] <= v <= _POINTS[1]:
            if k in ("nem", "ranking") and v <= 7:
                problems.append(
                    f"{NAMES_ES[k]} {v} is a grade average, not a score: ask for their "
                    f"{NAMES_ES[k]} score in points (it is on their DEMRE results)"
                )
            else:
                problems.append(f"{NAMES_ES[k]} {v} is outside 100 to 1000 points")
    if not w.found:
        return Estimate(None, problems=(*problems, "the page gave no weights"), weights=w)
    if abs(w.total - 1.0) > 0.011:
        problems.append(f"the weights on the page add up to {round(w.total * 100, 2):g}%")
    parts: list[tuple[Criterion, float, int, float]] = []
    missing: list[str] = []
    used: str | None = None
    for k, weight in w.weights.items():
        if weight <= 0:
            continue
        if k == "historia_ciencias":
            options = {n: given[n] for n in ("historia", "ciencias") if n in given}
            if not options:
                missing.append("Historia o Ciencias")
                continue
            used = max(options, key=lambda n: options[n])
            points = options[used]
        elif k in given:
            points = given[k]
        else:
            missing.append(NAMES_ES[k])
            continue
        parts.append((k, weight, points, round(points * weight, 2)))
    bad = any("grade average" in p or "outside" in p for p in problems)
    score = None if missing or bad else round(sum(p[3] for p in parts), 2)
    meets_weighted = None
    if score is not None and w.min_weighted is not None:
        meets_weighted = w.min_weighted == 0 or score >= w.min_weighted
    avg = None
    meets_avg = None
    if s.lectora is not None and s.matematica is not None:
        avg = round((s.lectora + s.matematica) / 2, 2)
        if w.min_avg_lm is not None:
            meets_avg = w.min_avg_lm == 0 or avg >= w.min_avg_lm
    return Estimate(
        score,
        tuple(parts),
        tuple(missing),
        tuple(problems),
        used,
        meets_weighted,
        avg,
        meets_avg,
        w,
    )


def describe_estimate(e: Estimate, lang: str) -> str:
    """The estimate for a note to the model, with the words for its numbers."""
    say = decimal_es if lang == "es" else decimal_en
    out: list[str] = []
    if e.problems:
        out.append("Problems: " + "; ".join(e.problems) + ".")
    if e.missing:
        out.append("Still missing to compute it: " + ", ".join(e.missing) + ".")
    if e.score is not None:
        steps = ", ".join(
            f"{NAMES_ES[k]} {p} x {round(wt * 100, 2):g}% = {c:g}" for k, wt, p, c in e.parts
        )
        out.append(f"Weighted score {e.score:g} — say “{say(e.score)}” ({steps}).")
        if e.used_for_hc:
            out.append(f"For Historia o Ciencias the higher one counts: {NAMES_ES[e.used_for_hc]}.")
        w = e.weights
        if w.min_weighted is not None:
            out.append(
                "The table sets no minimum weighted score (it says 0)."
                if w.min_weighted == 0
                else f"Minimum weighted score {w.min_weighted}: "
                + ("it is above it." if e.meets_weighted else "it is below it.")
            )
    if e.avg_lm is not None and e.weights.min_avg_lm is not None:
        out.append(
            f"Average of Lectora and Matemática {e.avg_lm:g} — say “{say(e.avg_lm)}” — against "
            f"the minimum of {e.weights.min_avg_lm}: "
            + ("it meets it." if e.meets_avg else "it does not reach it.")
        )
    return " ".join(out)


__all__ = [
    "CRITERIA",
    "Estimate",
    "Fees",
    "Scores",
    "Weights",
    "amount",
    "date_of",
    "date_said",
    "dates_in",
    "decimal_en",
    "decimal_es",
    "describe_estimate",
    "describe_fees",
    "describe_weights",
    "estimate",
    "money_for_the_voice",
    "money_items",
    "number_en",
    "number_es",
    "parse_fees",
    "parse_weights",
    "pesos_en",
    "pesos_es",
]
