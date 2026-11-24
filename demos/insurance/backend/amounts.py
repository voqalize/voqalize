"""Indian rupee amounts, both ways: what the customer said into a number, and a
number into words the voice reads naturally.

**Heard.** The recognizer writes an amount however it heard it: "1.5 lakhs",
"1,50,000", "one lakh fifty thousand", "around 1 and half lakhs", "15k", "dedh
lakh", "डेढ़ लाख", Devanagari digits. The model passes the customer's own words, and
:func:`parse` turns any of them into rupees. The claim form once kept only the
digits of "1.5 lakh" and stored ₹15 (I2): nothing here drops a unit.

**Spoken.** The voice reads words reliably; a written figure such as "₹1.25 Cr"
it can read as "1 rupee 25 crore" (B6). :func:`words` writes an amount the
Indian way ("one lakh fifty thousand rupees", "डेढ़ लाख रुपये"), and
:func:`speakable` rewrites every written amount in a line before it is spoken;
:class:`SpokenAmounts` does the same to a stream of model text, holding back
only a figure that may still be arriving. The screen keeps ₹1,50,000.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# ─── Number words ─────────────────────────────────────────────────────────────

_EN_ONES = [
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

#: 0-99 in Hindi: every number has its own word.
_HI_0_99 = [
    "शून्य",
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
    "चौवालीस",
    "पैंतालीस",
    "छियालीस",
    "सैंतालीस",
    "अड़तालीस",
    "उनचास",
    "पचास",
    "इक्यावन",
    "बावन",
    "तिरपन",
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
    "इक्यानबे",
    "बानबे",
    "तिरानबे",
    "चौरानबे",
    "पंचानबे",
    "छियानबे",
    "सत्तानबे",
    "अट्ठानबे",
    "निन्यानबे",
]
assert len(_HI_0_99) == 100


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


#: Words heard for a number, English and Hindi (Devanagari and as typed in Latin).
_NUMBER_WORDS: dict[str, float] = {
    **{w: i for i, w in enumerate(_EN_ONES)},
    **{w: 10 * i for i, w in enumerate(_EN_TENS) if w != "_"},
    "a": 1,
    "an": 1,
    "ek": 1,
    "do": 2,
    "teen": 3,
    "char": 4,
    "chaar": 4,
    "paanch": 5,
    "panch": 5,
    "chhe": 6,
    "che": 6,
    "saat": 7,
    "aath": 8,
    "nau": 9,
    "das": 10,
    "gyarah": 11,
    "barah": 12,
    "baarah": 12,
    "pandrah": 15,
    "bees": 20,
    "pachees": 25,
    "pachchis": 25,
    "pachis": 25,
    "tees": 30,
    "chalis": 40,
    "chaalis": 40,
    "pachas": 50,
    "pachaas": 50,
    "saath": 60,
    "sattar": 70,
    "assi": 80,
    "nabbe": 90,
    **{_nfc(w): i for i, w in enumerate(_HI_0_99)},
    _nfc("पांच"): 5,
    _nfc("छः"): 6,
}

#: Multipliers. "k" and "l" also arrive glued to digits ("15k", "1.5L").
_UNITS: dict[str, int] = {
    "hundred": 100,
    "sau": 100,
    _nfc("सौ"): 100,
    "thousand": 1_000,
    "k": 1_000,
    "hazaar": 1_000,
    "hazar": 1_000,
    "hajar": 1_000,
    "hazaar.": 1_000,
    _nfc("हज़ार"): 1_000,
    _nfc("हजार"): 1_000,
    "lakh": 100_000,
    "lakhs": 100_000,
    "lac": 100_000,
    "lacs": 100_000,
    "lakhs.": 100_000,
    "l": 100_000,
    _nfc("लाख"): 100_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
    "cr": 10_000_000,
    "karod": 10_000_000,
    "karor": 10_000_000,
    _nfc("करोड़"): 10_000_000,
    _nfc("करोड"): 10_000_000,
}

#: Hindi fraction words: a value of their own (dedh = 1.5), or a change to the
#: number after them (sava do = 2.25, saade teen = 3.5, paune do = 1.75).
_WHOLE_FRACTIONS = {
    "dedh": 1.5,
    "derh": 1.5,
    "dhai": 2.5,
    "dhaai": 2.5,
    _nfc("डेढ़"): 1.5,
    _nfc("डेढ"): 1.5,
    _nfc("ढाई"): 2.5,
}
_SHIFTS = {
    "sava": 0.25,
    "sawa": 0.25,
    "saade": 0.5,
    "saadhe": 0.5,
    "sade": 0.5,
    "paune": -0.25,
    _nfc("सवा"): 0.25,
    _nfc("साढ़े"): 0.5,
    _nfc("साढे"): 0.5,
    _nfc("पौने"): -0.25,
}

_APPROX = frozenset(
    [
        "around",
        "about",
        "approximately",
        "approx",
        "roughly",
        "nearly",
        "almost",
        "some",
        "like",
        "lagbhag",
        "karib",
        "kareeb",
        "takreeban",
    ]
    + [_nfc(w) for w in ("लगभग", "करीब", "क़रीब", "तकरीबन", "तक़रीबन", "कोई")]
)
_RANGE_SPLIT = re.compile(
    r"\s(?:to|or|se|till|until|upto|up to|से|या|तक)\s|\s*[-\u2013\u2014]\s*(?=\d)",
    re.IGNORECASE,
)
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
#: Devanagari letters and digits, not the danda (।, ॥) that ends a Hindi sentence.
_DEVANAGARI_WORD = "ऀ-ॣ०-ॿ"
_TOKEN = re.compile(rf"\d+(?:\.\d+)?|[a-z]+\.?|[{_DEVANAGARI_WORD}]+")


@dataclass(frozen=True)
class Amount:
    """Rupees heard, and how sure the words were."""

    rupees: int
    #: "around", "about", "lagbhag": the customer gave an estimate.
    approx: bool = False
    #: The lower end, when the customer gave a range ("one to one and a half lakh").
    low: int | None = None


def _clean(text: str) -> str:
    t = _nfc(text).translate(_DEVANAGARI_DIGITS).lower()
    t = re.sub(r"(?<=\d),(?=\d)", "", t)
    t = re.sub(r"₹|\brs\.?|\binr\b|\brupees?\b|\brupaye\b|\brupay\b|रुपये|रुपए|रुपया|रु\.?", " ", t)
    # "one point five" → 1.5
    t = re.sub(
        r"\b(\w+) point (\w+)\b",
        lambda m: (
            f"{_NUMBER_WORDS[m.group(1)]:g}.{int(_NUMBER_WORDS[m.group(2)])}"
            if m.group(1) in _NUMBER_WORDS
            and m.group(2) in _NUMBER_WORDS
            and _NUMBER_WORDS[m.group(2)] < 10
            else m.group(0)
        ),
        t,
    )
    # Glued units: "15k", "1.5l", "2cr", "1.5lakh".
    t = re.sub(r"(\d)(k|l|cr|lakhs?|lacs?|crores?)\b", r"\1 \2", t)
    return t


def _one(text: str) -> tuple[float, int, bool] | None:
    """(rupees, largest unit used, approx) for one amount in words or figures."""
    tokens = _TOKEN.findall(_clean(text))
    total = 0.0
    current = 0.0
    shift = 0.0
    seen = False
    biggest = 1
    last_unit = 1
    approx = False
    i = 0
    while i < len(tokens):
        tok = tokens[i].rstrip(".") if not tokens[i][0].isdigit() else tokens[i]
        if tok in _APPROX:
            approx = True
        elif tok[0].isdigit():
            current += float(tok) + shift
            shift, seen = 0.0, True
        elif tok in _WHOLE_FRACTIONS:
            current += _WHOLE_FRACTIONS[tok]
            seen = True
        elif tok in _SHIFTS:
            shift = _SHIFTS[tok]
        elif tok == "half":
            # "one and a half lakh", "1 and half lakhs", "half a lakh", "a lakh and a half"
            if current:
                current += 0.5
            elif last_unit > 100 and i + 1 >= len(tokens):
                total += last_unit / 2
            else:
                current = 0.5
            seen = True
            if i + 1 < len(tokens) and tokens[i + 1] in ("a", "an"):
                i += 1
        elif tok == "quarter":
            current = current + 0.25 if current else 0.25
            seen = True
        elif tok in _UNITS:
            unit = _UNITS[tok]
            biggest = max(biggest, unit)
            last_unit = unit
            # "lakh" alone is one lakh; "sava lakh" is one and a quarter.
            base = current or 1 + shift
            shift = 0.0
            if unit == 100:
                current = base * 100
            else:
                total += base * unit
                current = 0.0
            seen = True
        elif tok in _NUMBER_WORDS and tok not in ("a", "an", "do"):
            current += _NUMBER_WORDS[tok] + shift
            shift, seen = 0.0, True
        elif tok in ("a", "an") and i + 1 < len(tokens) and tokens[i + 1].rstrip(".") in _UNITS:
            current += 1
        elif tok == "do" and (
            i + 1 < len(tokens)
            and (tokens[i + 1] in _UNITS or (i > 0 and tokens[i - 1] in _SHIFTS))
        ):
            current += 2 + shift
            shift, seen = 0.0, True
        i += 1
    if not seen:
        return None
    return total + current, biggest, approx


def parse(text: str) -> Amount | None:
    """Rupees in what the customer said, or None when it holds no amount.

    "around 1 and half lakhs" → ₹1,50,000 (approx); "one lakh fifty thousand"
    → ₹1,50,000; "15k" → ₹15,000; "dedh lakh" → ₹1,50,000; "1 to 1.5 lakh" →
    ₹1,50,000 with ₹1,00,000 as the low end."""
    if not str(text).strip():
        return None
    t = _nfc(str(text))
    # "between one and one and a half lakh": the first "and" splits the range.
    between = re.match(r"(.*?)\bbetween\s+(.+?)\s+and\s+(.+)$", t, re.IGNORECASE)
    if between:
        t = f"{between.group(1)} {between.group(2)} to {between.group(3)}"
    parts = [p for p in _RANGE_SPLIT.split(t) if p.strip()]
    found = [x for x in (_one(p) for p in parts) if x is not None]
    if not found:
        return None
    approx = any(a for _, _, a in found)
    if len(found) == 1:
        return Amount(round(found[0][0]), approx=approx)
    (lo, lo_unit, _), (hi, hi_unit, _) = found[0], found[-1]
    # "1 to 1.5 lakh": the unit said once belongs to both ends.
    if lo_unit < hi_unit and lo * hi_unit <= hi * 10:
        lo *= hi_unit
    lo, hi = sorted((lo, hi))
    return Amount(round(hi), approx=True, low=round(lo))


# ─── Written ──────────────────────────────────────────────────────────────────


def inr(amount: float) -> str:
    """₹1,50,000 — Indian digit grouping, to the rupee."""
    n = round(abs(amount))
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return ("-" if amount < 0 else "") + "₹" + s


# ─── Spoken ───────────────────────────────────────────────────────────────────


def _en_below_1000(n: int) -> str:
    parts: list[str] = []
    if n >= 100:
        parts.append(f"{_EN_ONES[n // 100]} hundred")
        n %= 100
        if n:
            parts.append("and")
    if n >= 20:
        parts.append(_EN_TENS[n // 10] + (f"-{_EN_ONES[n % 10]}" if n % 10 else ""))
    elif n or not parts:
        parts.append(_EN_ONES[n])
    return " ".join(parts)


def _hi_below_1000(n: int) -> str:
    parts: list[str] = []
    if n >= 100:
        parts.append(f"{_HI_0_99[n // 100]} सौ")
        n %= 100
    if n or not parts:
        parts.append(_HI_0_99[n])
    return " ".join(parts)


def _grouped(n: int) -> list[tuple[int, str]]:
    """Indian groups, largest first: crore, lakh, thousand, the rest."""
    out: list[tuple[int, str]] = []
    crore, n = divmod(n, 10_000_000)
    lakh, n = divmod(n, 100_000)
    thousand, rest = divmod(n, 1_000)
    for value, unit in ((crore, "crore"), (lakh, "lakh"), (thousand, "thousand"), (rest, "")):
        if value:
            out.append((value, unit))
    return out


_HI_UNIT = {"crore": "करोड़", "lakh": "लाख", "thousand": "हज़ार", "": ""}


def _hi_fraction(n: int) -> str | None:
    """सवा / डेढ़ / ढाई / साढ़े / पौने for an amount that is exactly a quarter
    step of a crore, lakh or thousand: how a Hindi speaker says it."""
    for unit, word in ((10_000_000, "करोड़"), (100_000, "लाख"), (1_000, "हज़ार")):
        if n < unit or (n * 4) % unit:
            continue
        quarters = n * 4 // unit
        whole, q = divmod(quarters, 4)
        if q == 0 or whole >= 100:
            return None
        if quarters == 6:
            return f"डेढ़ {word}"
        if quarters == 10:
            return f"ढाई {word}"
        if q == 1:
            return f"सवा {word}" if whole == 1 else f"सवा {_HI_0_99[whole]} {word}"
        if q == 2 and whole >= 3:
            return f"साढ़े {_HI_0_99[whole]} {word}"
        if q == 3:
            return f"पौने {_HI_0_99[whole + 1]} {word}"
        return None
    return None


def words(amount: float, lang: str = "en", *, rupees: bool = True) -> str:
    """An amount the way it is said: "one lakh fifty thousand rupees",
    "डेढ़ लाख रुपये", "forty-four thousand seven hundred and seventy-five rupees"."""
    n = round(abs(amount))
    if lang == "hi":
        said = _hi_fraction(n) or (
            " ".join(f"{_hi_below_1000(v)} {_HI_UNIT[u]}".strip() for v, u in _grouped(n)) or "शून्य"
        )
        return f"{said} {'रुपया' if n == 1 else 'रुपये'}" if rupees else said
    groups = _grouped(n)
    parts = [f"{_en_below_1000(v)} {u}".strip() for v, u in groups]
    if len(groups) > 1 and groups[-1][1] == "" and groups[-1][0] < 100:
        parts[-1] = "and " + parts[-1]
    said = " ".join(parts) or "zero"
    if rupees:
        said += " rupee" if n == 1 else " rupees"
    return said


#: A written amount in model text or a line: "₹1,50,000", "₹1.5 lakh", "Rs 500",
#: "1.25 crore", "10 lakh", "₹44,775 a year", "1,50,000 रुपये", "15 हज़ार".
_WRITTEN = re.compile(
    r"(?P<cur>₹|\bRs\.?|\bINR)?\s?"
    r"(?P<num>(?<![\w./-])\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|(?<![\w./-])\d+(?:\.\d+)?)"
    r"(?:\s?(?P<unit>lakhs?|lacs?|crores?|cr|Cr|L|k|K|thousand|लाख|करोड़|करोड|हज़ार|हजार)"
    rf"(?![\w{_DEVANAGARI_WORD}]))?"
    r"(?:\s(?P<tail>rupees|rupee|रुपये|रुपए))?",
)

_UNIT_OF = {
    "lakh": 100_000,
    "lakhs": 100_000,
    "lac": 100_000,
    "lacs": 100_000,
    "l": 100_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
    "cr": 10_000_000,
    "k": 1_000,
    "thousand": 1_000,
    "लाख": 100_000,
    "करोड़": 10_000_000,
    "करोड": 10_000_000,
    "हज़ार": 1_000,
    "हजार": 1_000,
}


def speakable(text: str, lang: str = "en") -> str:
    """``text`` with every written amount in words, for the voice. A bare number
    with no rupee sign, no Indian grouping and no lakh/crore (a year, a clause,
    a policy or account number) is left as it is."""

    def say(m: re.Match[str]) -> str:
        cur, num, unit, tail = m.group("cur"), m.group("num"), m.group("unit"), m.group("tail")
        grouped = "," in num
        if not (cur or unit or tail or grouped):
            return m.group(0)
        if unit in ("L", "k", "K") and not cur:
            return m.group(0)  # "15k steps", "a 4K screen": not ours to read
        value = float(num.translate(_DEVANAGARI_DIGITS).replace(",", ""))
        if unit:
            value *= _UNIT_OF[_nfc(unit).lower()]
        lead = " " if m.group(0).startswith(" ") else ""
        return lead + words(value, lang, rupees=bool(cur or tail))

    return _WRITTEN.sub(say, _nfc(text))


#: The end of a stream that may be a written amount still arriving.
_PENDING = re.compile(
    rf"(?:(?:₹|\bRs\.?|\bINR)\s?)?\d[\d,.]*(?:\s?[A-Za-z{_DEVANAGARI_WORD}]*)?$|(?:₹|\bRs\.?|\bINR)\s?$"
)


class SpokenAmounts:
    """Model text on its way to the voice, its written amounts said in words.

    Pieces arrive a few tokens at a time, so "₹1," may end one and "50,000" start
    the next: a tail that may still be an amount is held until the piece after it
    settles it (or the unit ends), and everything else passes straight through."""

    def __init__(self, lang: str) -> None:
        self.lang = lang
        self._held = ""

    def feed(self, piece: str) -> str:
        text = self._held + piece
        m = _PENDING.search(text)
        cut = m.start() if m else len(text)
        self._held = text[cut:]
        return speakable(text[:cut], self.lang) if cut else ""

    def flush(self) -> str:
        text, self._held = self._held, ""
        return speakable(text, self.lang) if text else ""
