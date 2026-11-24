"""Amounts in speech, both ways (FEEDBACK X8), adapted from the bank demo's.

**Out (brain → voice).** The screen shows ₹1,500 to ₹2,500; the voice must say
it the way a Bengaluru front desk does. Voqalize's TTS normalises text before
the voice model reads it, and in English one of its rules reads any rupee amount
with exactly two decimals as rupees and paise, so "₹1.25 crore" reaches the
voice as "one rupee and twenty five paisa crore" and a "₹1.25k" would fare no
better. :func:`speak_text` rewrites every amount into a form that chain reads
right (the forms are the ones the bank and insurance demos verified against the
chain; see the README, "Amounts in speech"):

- Plain rupees (₹500, ₹6,500, ₹12,000) go as written: the chain reads them in
  thousand and lakh, in English and in Hindi.
- A range says both ends with the rupee mark and a word between them: a dash
  ("₹8,000-₹18,000", "₹1,500-2,500") becomes "to" (से in Hindi).
- Thousands written short ("₹1.5k", "₹15 thousand", "₹8 हज़ार") become whole
  rupees (₹1,500, ₹15,000, ₹8,000).
- Lakh and crore: in English spelled out ("one point two five crore rupees");
  in Hindi a quarter step is said the Hindi way in words ("सवा करोड़ रुपये",
  "डेढ़ लाख रुपये"), a whole number keeps the ₹ with the Devanagari scale
  ("₹8 लाख"), and any other decimal becomes whole rupees.
- Rupees and paise ("₹12.50") are said in words, so no ₹ amount with two
  decimals ever reaches the TTS.

:class:`SpokenAmounts` applies it to a brain's speech as it streams, holding back
only the last few words while they could still be part of an amount.

**In (voice → brain).** No tool here takes an amount from the patient (the
desk's tools take a service, a slot, a phone number and a code), so nothing is
filled from one. A patient may still ask about money in words ("anything under
dedh hazaar?", "is it more than 10k?"): :func:`parse_amounts` reads digits with
Indian or Western commas, lakh / crore / thousand / hazaar / k, number words in
English and Hindi (Devanagari or Latin), "one and a half", dedh, dhai, sava,
saade, paune, decimals, Devanagari digits and "around" / lagbhag, and
:func:`amounts_note` hands the model what they said in rupees.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import AsyncGenerator, Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from voqalize.sdk import Speech, SpeechChunk, SpeechEnd

from .clinic import rupees

# ─── Numbers as words ─────────────────────────────────────────────────────────

_ONES = [
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
_TENS = ["_", "_", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _below_hundred(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + (f" {_ONES[ones]}" if ones else "")


def _below_thousand(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts = [f"{_ONES[hundreds]} hundred"] if hundreds else []
    if rest or not parts:
        parts.append(_below_hundred(rest))
    return " ".join(parts)


def en_cardinal(n: int) -> str:
    """A whole number in Indian English: crore, lakh, thousand ("one crore twenty five lakh")."""
    if n < 1000:
        return _below_thousand(n)
    parts: list[str] = []
    for size, word in ((10_000_000, "crore"), (100_000, "lakh"), (1_000, "thousand")):
        if n >= size:
            head, n = divmod(n, size)
            parts.append(f"{en_cardinal(head)} {word}")
    if n:
        parts.append(_below_thousand(n))
    return " ".join(parts)


def en_number(raw: str) -> str:
    """Digits as written ("1.25", "12", "1,25,000") in English words ("one point two five")."""
    digits = raw.replace(",", "")
    head, _, frac = digits.partition(".")
    said = en_cardinal(int(head or "0"))
    if frac:
        said += " point " + " ".join(_ONES[int(d)] for d in frac)
    return said


#: Hindi 1 to 99 in Devanagari, as the voice says them and the Indic recogniser writes them.
_HI_DEVANAGARI = [
    "एक",
    "दो",
    "तीन",
    "चार",
    "पाँच",
    "छह",
    "सात",
    "आठ",
    "नौ",
    "दस",
    "ग्यारह",
    "बारह",
    "तेरह",
    "चौदह",
    "पंद्रह",
    "सोलह",
    "सत्रह",
    "अठारह",
    "उन्नीस",
    "बीस",
    "इक्कीस",
    "बाईस",
    "तेईस",
    "चौबीस",
    "पच्चीस",
    "छब्बीस",
    "सत्ताईस",
    "अट्ठाईस",
    "उनतीस",
    "तीस",
    "इकतीस",
    "बत्तीस",
    "तैंतीस",
    "चौंतीस",
    "पैंतीस",
    "छत्तीस",
    "सैंतीस",
    "अड़तीस",
    "उनतालीस",
    "चालीस",
    "इकतालीस",
    "बयालीस",
    "तैंतालीस",
    "चवालीस",
    "पैंतालीस",
    "छियालीस",
    "सैंतालीस",
    "अड़तालीस",
    "उनचास",
    "पचास",
    "इक्यावन",
    "बावन",
    "तिरेपन",
    "चौवन",
    "पचपन",
    "छप्पन",
    "सत्तावन",
    "अट्ठावन",
    "उनसठ",
    "साठ",
    "इकसठ",
    "बासठ",
    "तिरसठ",
    "चौंसठ",
    "पैंसठ",
    "छियासठ",
    "सड़सठ",
    "अड़सठ",
    "उनहत्तर",
    "सत्तर",
    "इकहत्तर",
    "बहत्तर",
    "तिहत्तर",
    "चौहत्तर",
    "पचहत्तर",
    "छिहत्तर",
    "सतहत्तर",
    "अठहत्तर",
    "उन्यासी",
    "अस्सी",
    "इक्यासी",
    "बयासी",
    "तिरासी",
    "चौरासी",
    "पचासी",
    "छियासी",
    "सत्तासी",
    "अट्ठासी",
    "नवासी",
    "नब्बे",
    "इक्यानवे",
    "बानवे",
    "तिरानवे",
    "चौरानवे",
    "पंचानवे",
    "छियानवे",
    "सत्तानवे",
    "अट्ठानवे",
    "निन्यानवे",
]
assert len(_HI_DEVANAGARI) == 99


def hi_quarter(raw: str) -> str | None:
    """A quarter-step number the Hindi way (1.5 डेढ़, 2.5 ढाई, 1.25 सवा, 3.5 साढ़े तीन,
    2.75 पौने तीन), or None when it is whole or not a quarter step."""
    try:
        value = Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None
    quarters = value * 4
    if quarters != quarters.to_integral_value() or value == value.to_integral_value():
        return None
    whole, q = divmod(int(quarters), 4)
    if whole < 1 or whole >= 99:
        return None
    if value == Decimal("1.5"):
        return "डेढ़"
    if value == Decimal("2.5"):
        return "ढाई"
    if q == 1:
        return "सवा" if whole == 1 else f"सवा {_HI_DEVANAGARI[whole - 1]}"
    if q == 2:
        return f"साढ़े {_HI_DEVANAGARI[whole - 1]}"
    return f"पौने {_HI_DEVANAGARI[whole]}"


# ─── Brain → voice ────────────────────────────────────────────────────────────

_NUM = r"\d[\d,]*(?:\.\d+)?"
_DEVANAGARI = "ऀ-ॿ"
_CUR = r"₹|(?<![A-Za-z])Rs\.?|(?<![A-Za-z])INR"
#: Scale words as a model writes them; "L" (lakh) and "k" only right after a digit.
_SCALE = (
    r"lakhs?|lacs?|crores?|cr|thousand|लाख|करो(?:\u095c|\u0921\u093c)|करोड"
    r"|ह(?:\u095b|\u091c\u093c?)ार"
)
_SCALED = re.compile(
    rf"(?<![\w.,])(?P<cur>{_CUR})?[ \t]*(?P<a>{_NUM})"
    rf"(?:[ \t]*(?:[-\u2013\u2014]|\bto\b|से)[ \t]*(?P<cur2>₹)?[ \t]*(?P<b>{_NUM}))?"
    rf"[ \t]*(?:(?P<scale>{_SCALE})|(?<=\d)(?P<L>L)|(?<=\d)(?P<k>k))(?![A-Za-z{_DEVANAGARI}])"
    rf"(?:[ \t]+(?P<word>rupees|रुपये|रुपए))?",
    re.IGNORECASE,
)
_PCT_RANGE = re.compile(
    r"(?<![\w.,])(\d+(?:\.\d+)?)[ \t]*%?[ \t]*(?:[-\u2013\u2014]|\bto\b|से)[ \t]*(\d+(?:\.\d+)?)[ \t]*%"
)
#: Two rupee amounts with a dash (or "to" / से) between them: "₹8,000-₹18,000", "₹1,500-2,500".
_RUPEE_RANGE = re.compile(
    rf"(?<![\w.,])(?:{_CUR})[ \t]*(?P<a>\d[\d,]*(?<=\d))[ \t]*(?:[-\u2013\u2014]|\bto\b|से)[ \t]*"
    rf"(?:{_CUR})?[ \t]*(?P<b>\d[\d,]*(?<=\d))(?![\d.])"
)
#: Rupees and paise: "₹12.50".
_PAISE = re.compile(rf"(?<![\w.,])(?:{_CUR})[ \t]*(?P<r>\d[\d,]*)\.(?P<p>\d\d)(?!\d)")


def _scale_of(m: re.Match[str]) -> tuple[int, str, str]:
    """The scale's size, its English word and its Hindi word."""
    if m["k"]:
        return 1_000, "thousand", "हज़ार"
    s = (m["scale"] or "L").lower()
    if s.startswith(("l", "ल")):
        return 100_000, "lakh", "लाख"
    if s.startswith(("t", "ह")):
        return 1_000, "thousand", "हज़ार"
    return 10_000_000, "crore", "करोड़"


def _whole(raw: str, size: int) -> str:
    """A scaled amount as whole rupees in Indian grouping: "1.5" thousand → ₹1,500."""
    return rupees(round(Decimal(raw.replace(",", "")) * size))


def _hi_end(raw: str, size: int, hindi: str, *, money: bool, last: bool) -> str:
    """One end of a lakh or crore amount for the Hindi voice."""
    said = hi_quarter(raw)
    if said is not None:
        return f"{said} {hindi}" + (" रुपये" if money and last else "")
    if "." not in raw:
        return f"₹{raw} {hindi}" if money else f"{raw} {hindi}"
    return _whole(raw, size) if money else f"{raw} {hindi}"


def _scaled(m: re.Match[str], lang: str) -> str:
    if (m["L"] or m["k"]) and not m["cur"]:  # "5L", "4k" with no rupee mark: not money.
        return m[0]
    size, english, hindi = _scale_of(m)
    money = bool(m["cur"] or m["cur2"] or m["word"])
    a, end = m["a"], m["b"]
    to = "से" if lang == "hi" else "to"
    if size == 1_000:
        if not money:  # "2 thousand steps": as written.
            return m[0]
        return _whole(a, size) + (f" {to} {_whole(end, size)}" if end else "")
    if lang == "hi":
        first = _hi_end(a, size, hindi, money=money, last=not end)
        if not end:
            return first
        return f"{first} से {_hi_end(end, size, hindi, money=money, last=True)}"
    said = en_number(a) + (f" to {en_number(end)}" if end else "")
    return f"{said} {english}" + (" rupees" if money else "")


def _paise(m: re.Match[str], lang: str) -> str:
    whole, paise = int(m["r"].replace(",", "")), int(m["p"])
    if lang == "hi":
        return f"₹{m['r']}" + (f" और {_HI_DEVANAGARI[paise - 1]} पैसे" if paise else "")
    said = f"{en_cardinal(whole)} {'rupee' if whole == 1 else 'rupees'}"
    return said + (f" and {en_cardinal(paise)} paise" if paise else "")


#: A dash between two amounts already said in full ("₹8 lakh", dash, "₹12 lakh"): silent raw.
_DASH_AFTER_SCALE = re.compile(
    rf"(lakh|crore|rupees|लाख|करो(?:\u095c|\u0921\u093c))[ \t]*[-\u2013\u2014][ \t]*(?=₹|\d|(?:{'|'.join(_ONES[1:] + _TENS[2:])})\b)"
)


def speak_text(text: str, lang: str) -> str:
    """``text`` as the voice should be given it, in ``lang`` ("en" or "hi")."""
    to = "से" if lang == "hi" else "to"
    out = _PCT_RANGE.sub(lambda m: f"{m[1]}% {to} {m[2]}%", text)
    out = _SCALED.sub(lambda m: _scaled(m, lang), out)
    out = _RUPEE_RANGE.sub(lambda m: f"₹{m['a']} {to} ₹{m['b']}", out)
    out = _PAISE.sub(lambda m: _paise(m, lang), out)
    return _DASH_AFTER_SCALE.sub(lambda m: f"{m[1]} {to} ", out)


#: A word that leaves the amount before it unfinished: the next word may extend it.
_OPEN_WORD = re.compile(r"(?:[\d₹%]|^(?:to|से|-|\u2013|\u2014|and|point|rs\.?|inr)$)", re.IGNORECASE)


def _settled(buffer: str) -> int:
    """How much of ``buffer`` can be spoken now: up to the last space whose word before it
    cannot be part of an amount still being written ("₹1.25" waits for "crore")."""
    for m in reversed(list(re.finditer(r"\s+", buffer))):
        before = buffer[: m.start()].rsplit(None, 1)
        if not before:
            return 0
        if not _OPEN_WORD.search(before[-1]):
            return m.end()
    return 0


class SpokenAmounts:
    """Rewrites a brain's speech with :func:`speak_text` as it streams. The unit's start
    and end pass through untouched, so ids and finalizes are the SDK's own."""

    def __init__(self, lang: Callable[[], str]) -> None:
        self._lang = lang

    async def wrap(self, speech: AsyncGenerator[Speech, None]) -> AsyncGenerator[Speech, None]:
        held = ""
        try:
            async for event in speech:
                if isinstance(event, SpeechChunk):
                    held += event.text
                    cut = _settled(held)
                    if cut:
                        ready, held = held[:cut], held[cut:]
                        yield SpeechChunk(speak_text(ready, self._lang()))
                    continue
                if isinstance(event, SpeechEnd) and held:
                    yield SpeechChunk(speak_text(held, self._lang()))
                    held = ""
                yield event
        finally:
            await speech.aclose()


# ─── Voice → brain ────────────────────────────────────────────────────────────


def _nfc(text: str) -> str:
    """One spelling for a nukta (ड़ is one code point or ड and a dot below)."""
    return unicodedata.normalize("NFC", text)


def _nfc_keys(table: Mapping[str, float]) -> dict[str, float]:
    return {_nfc(k): v for k, v in table.items()}


_EN_WORDS: dict[str, float] = {w: float(i) for i, w in enumerate(_ONES)} | {
    w: float(i * 10) for i, w in enumerate(_TENS) if w != "_"
}
_HI_WORDS: dict[str, float] = _nfc_keys(
    {w: float(i) for i, w in enumerate(_HI_DEVANAGARI, 1)}
    | {
        "पांच": 5,
        "छः": 6,
        "छे": 6,
        "पन्द्रह": 15,
        "चौवालीस": 44,
        "तिरपन": 53,
    }
)
#: Hindi in Latin letters: a number only right before a scale or another number ("do lakh",
#: never the English "do").
_HI_LATIN = {
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6,
    "chhah": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12,
    "baarah": 12, "terah": 13, "chaudah": 14, "pandrah": 15, "solah": 16, "satrah": 17,
    "atharah": 18, "unnis": 19, "bees": 20, "pachees": 25, "pachchees": 25, "pachis": 25,
    "tees": 30, "chalis": 40, "chaalis": 40, "pachas": 50, "pachaas": 50, "saath": 60,
    "sattar": 70, "assi": 80, "nabbe": 90,
}  # fmt: skip
_SCALES: dict[str, float] = _nfc_keys({
    "hundred": 100, "sau": 100, "सौ": 100,
    "thousand": 1_000, "k": 1_000, "hazaar": 1_000, "hazar": 1_000, "hajar": 1_000,
    "हज़ार": 1_000, "हजार": 1_000,
    "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "lacs": 100_000, "lack": 100_000,
    "lakhs.": 100_000, "लाख": 100_000,
    "million": 1_000_000,
    "crore": 10_000_000, "crores": 10_000_000, "cr": 10_000_000, "करोड़": 10_000_000,
    "करोड": 10_000_000,
})  # fmt: skip
#: Words that are a number by themselves before a scale: dedh lakh, dhai hazaar, sava crore.
_WHOLE_FRACTIONS: dict[str, float] = _nfc_keys({
    "dedh": 1.5, "derh": 1.5, "डेढ़": 1.5, "डेढ": 1.5,
    "dhai": 2.5, "dhaai": 2.5, "adhai": 2.5, "arhai": 2.5, "ढाई": 2.5, "अढ़ाई": 2.5,
})  # fmt: skip
#: Words that change the number after them: sava do (2¼), saade teen (3½), paune do (1¾).
_PREFIX_FRACTIONS: dict[str, float] = _nfc_keys({
    "sava": 0.25, "sawa": 0.25, "savaa": 0.25, "सवा": 0.25,
    "saade": 0.5, "sade": 0.5, "saadhe": 0.5, "sadhe": 0.5, "साढ़े": 0.5, "साढे": 0.5,
    "paune": -0.25, "पौने": -0.25,
})  # fmt: skip
_APPROX = {_nfc(w) for w in {
    "around", "about", "approximately", "approx", "roughly", "nearly", "almost", "lagbhag",
    "karib", "kareeb", "takreeban", "लगभग", "करीब", "क़रीब", "तकरीबन",
}}  # fmt: skip
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_TOKEN = re.compile(r"\d+(?:,\d+)*(?:\.\d+)?|[a-z]+\.?|[ऀ-ॣॱ-ॿ]+")


@dataclass(frozen=True)
class Heard:
    """One amount in what the recogniser heard."""

    value: float
    #: The words it was said in, as heard.
    said: str
    #: Said with a scale or a fraction word (lakh, hazaar, dedh): the kind a model misreads.
    scaled: bool
    #: Said with "around", "about", lagbhag.
    approx: bool


def _is_number(tok: str, nxt: str | None) -> bool:
    if tok[0].isdigit() or tok in _EN_WORDS or tok in _HI_WORDS:
        return True
    if tok in _WHOLE_FRACTIONS or tok in _PREFIX_FRACTIONS:
        return True
    return tok in _HI_LATIN and nxt is not None and (nxt in _SCALES or _is_number(nxt, None))


def parse_amounts(text: str) -> list[Heard]:
    """Every amount in ``text``, in rupees, in the order said."""
    text = _nfc(text)
    norm = text.lower().translate(_DEVANAGARI_DIGITS)
    toks: list[tuple[str, int, int]] = []
    #: Token indexes a stop or a comma follows: an amount never runs past one.
    stops: set[int] = set()
    for m in _TOKEN.finditer(norm):
        tok = m[0].rstrip(".") or m[0]
        if m.end() > m.start() + len(tok) or norm[m.end() : m.end() + 1] in (
            ".",
            ",",
            ";",
            "?",
            "!",
            "।",
        ):
            stops.add(len(toks))
        toks.append((tok, m.start(), m.start() + len(tok)))
    words = [t for t, _, _ in toks]
    out: list[Heard] = []
    i, approx = 0, False
    while i < len(words):
        w = words[i]
        nxt = words[i + 1] if i + 1 < len(words) else None
        after = words[i + 2] if i + 2 < len(words) else None
        starts = (
            _is_number(w, nxt)
            or (w in ("a", "half") and nxt in _SCALES)
            or (w == "half" and nxt in ("a", "an") and after in _SCALES)
        )
        if not starts:
            approx = w in _APPROX or (approx and w in ("of", "ki", "ka", "rs", "rupees", "₹"))
            i += 1
            continue
        begin = toks[i][1]
        total, current, scaled, prefix = 0.0, 0.0, False, 0.0
        end = i
        while end < len(words):
            w = words[end]
            nxt = words[end + 1] if end + 1 < len(words) else None
            after = words[end + 2] if end + 2 < len(words) else None
            if w[0].isdigit():
                current += float(w.replace(",", ""))
            elif w in _EN_WORDS:
                current += _EN_WORDS[w]
            elif w in _HI_WORDS:
                current += _HI_WORDS[w]
            elif w in _HI_LATIN and _is_number(w, nxt):
                current += _HI_LATIN[w]
            elif w in _WHOLE_FRACTIONS:
                current += _WHOLE_FRACTIONS[w]
                scaled = True
            elif w in _PREFIX_FRACTIONS:
                prefix = _PREFIX_FRACTIONS[w]
                scaled = True
                if nxt in _SCALES:  # "sava lakh" is 1¼ lakh
                    current += 1
            elif w == "a" and nxt in _SCALES and current == 0:
                current = 1
            elif w == "half" and current == 0 and nxt in ("a", "an") and after in _SCALES:
                current, end = 0.5, end + 1  # "half a lakh"
                scaled = True
            elif w == "half" and current == 0 and nxt in _SCALES:
                current, scaled = 0.5, True
            elif w == "and" and nxt == "a" and after == "half" and current:
                current, end, scaled = current + 0.5, end + 2, True
            elif w == "and" and nxt == "half" and current:
                current, end, scaled = current + 0.5, end + 1, True
            elif w == "and" and nxt is not None and _is_number(nxt, after) and (current or total):
                pass  # "two thousand and eighty"
            elif w == "point" and nxt is not None and (nxt[0].isdigit() or nxt in _EN_WORDS):
                frac, end = "", end + 1
                while end < len(words) and (words[end].isdigit() or words[end] in _ONES[:10]):
                    tok = words[end]
                    frac += tok if tok.isdigit() else str(_ONES.index(tok))
                    end += 1
                current += float(f"0.{frac}") if frac else 0
                continue
            elif w in _SCALES and (current or prefix):
                size = _SCALES[w]
                current += prefix
                prefix = 0.0
                if size == 100:
                    current *= 100
                else:
                    total += current * size
                    current = 0.0
                    scaled = True
            else:
                break
            end += 1
            if end - 1 in stops:
                break
        value = total + current + prefix
        last = toks[end - 1][2] if end > i else toks[i][2]
        if value > 0:
            out.append(Heard(round(value, 2), text[begin:last], scaled, approx))
        approx = False
        i = max(end, i + 1)
    return out


def amounts_note(text: str) -> str | None:
    """A note for the model when the customer said an amount in words or with a scale
    ("one and a half lakh" = 150000), so the number it passes is the number they said."""
    said = [h for h in parse_amounts(text) if h.scaled]
    if not said:
        return None
    parts = [
        f"'{h.said}' = {'about ' if h.approx else ''}{h.value:,.0f} rupees".replace(",", "")
        for h in said
    ]
    return f"[Amounts they said, in rupees: {'; '.join(parts)}.]"
