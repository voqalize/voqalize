"""Numbers, pesos and UF as the voice must say them.

Taken from the Universidad Alberto Hurtado guide (``demos/uahurtado``,
``admission.py``), where it was earned: the voice reads "$45.000" or
"102,58 UF" digit group by digit group, and a model asked to write an amount
in words reshapes it as often as not. So every figure handed to the model
carries its words (:func:`pesos_es`, :func:`uf_es`), and
:func:`money_for_the_voice` turns any amount still in digits into words before
the voice reads it. Nothing here fetches anything.
"""

from __future__ import annotations

import re

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
#: An amount in UF: "11 UF", "10,5 UF", "102,58 UF".
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
        # "189,00" is a whole 189; "10,05" keeps its zero: "diez coma cero cinco".
        whole, frac = int(m.group(1)), (m.group(2) or "").rstrip("0")
        if lang == "es":
            lead = "cero " * (len(frac) - len(frac.lstrip("0")))
            said = number_es(whole) + (f" coma {lead}{number_es(int(frac))}" if frac else "")
        else:
            said = number_en(whole) + (
                f" point {' '.join(_EN_UNITS[int(d)] for d in frac)}" if frac else ""
            )
        return f"{said} UF"

    return _UF.sub(uf, _MONEY.sub(pesos, text))


def uf_es(value: str) -> str:
    """A UF figure as the PDFs write it ("102,58", "10,646", "14.6") in Spanish
    words: "ciento dos coma cincuenta y ocho UF"."""
    return money_for_the_voice(f"{value.strip()} UF", "es")


def uf_en(value: str) -> str:
    """The same figure in English words: "one hundred two point five eight UF"."""
    return money_for_the_voice(f"{value.strip()} UF", "en")


__all__ = [
    "decimal_en",
    "decimal_es",
    "money_for_the_voice",
    "number_en",
    "number_es",
    "pesos_en",
    "pesos_es",
    "uf_en",
    "uf_es",
]
