"""Name/pack parsing + phonetics for the OrderDesk catalog — stdlib only.

Shared by ``build_catalog.py`` (offline, once) and ``search.py`` (per query), so
the tokens the index is built from are *exactly* the tokens a query is scored
against. Everything here is pure and deterministic: same input, same output, no
I/O, no state.

The parsing model is two-level (DESIGN.md §2):

* **family** — the brand root a pharmacist actually says ("TELMA", "VOLINI",
  "4 QUIN"). It is NOT "name minus the form word": that fractures TELMA into 24
  one-SKU families. The root is the leading token(s), extended only while the
  root so far is too weak to be a brand (single letters, digits, generic
  prefixes like NEW) — which is what recovers the real multi-word roots
  ("4 QUIN", "A TO Z", "D GAIN", "NEW FOLINAL").
* **variant axes** — what is left after the root: ``strength`` ("40 MG",
  "40/6.25", "0.05%"), ``form`` ("TABLET", "EYE DROPS", "DRY SYRUP") and
  ``variant_label`` (the leftover suffix line: "H", "AM", "CT", "JOINT XPERT").

``phonetic_key`` is a small metaphone-ish coder tuned for Hindi-transliteration
artifacts (V/W, VH/V, PH/F, EE/I, OO/U, T/TH, D/DH, K/C/Q, J/Z, S/SH) — it is
what recovers "abeyvee" → ABEVIA and "woliny" → VOLINI. ``phonetic_keys`` adds
the confusions that would be *destructive* to fold into the key itself (B/V,
soft C/G, the epenthetic vowel of "isporlac") as **alternate** keys, indexed and
probed alongside the canonical one and scored a notch below it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ─── name cleaning ────────────────────────────────────────────────────────────

# Product_Name carries a trailing "-<CODE>" suffix (…"-J0031270", …"-PROD4392").
_CODE_SUFFIX_RE = re.compile(r"-[A-Z0-9]+$")
# Some rows carry a stray backtick or a unicode NBSP inside the name.
_JUNK_RE = re.compile("[`\u00a0]")  # backtick and no-break space — both real in the CSV
_WS_RE = re.compile(r"\s+")


def normalize_ws(text: str) -> str:
    """Collapse NBSP/backticks/runs of whitespace into single spaces."""
    return _WS_RE.sub(" ", _JUNK_RE.sub(" ", text)).strip()


def clean_product_name(raw: str) -> str:
    """``'TELMA 40 TABLET-J0031270'`` → ``'TELMA 40 TABLET'`` (display form)."""
    name = normalize_ws(raw)
    name = _CODE_SUFFIX_RE.sub("", name).strip()
    return normalize_ws(name)


# ─── tokenisation ─────────────────────────────────────────────────────────────

# Hyphens and slashes-between-words are separators ("TELMA 80-AZ", "4 QUIN-BROM",
# "AUGMENTIN ES-600"), but a numeric ratio must survive whole ("40/6.25").
_TIMES = "\u00d7"  # U+00D7, the pharma way to write a strip count ("1 x 15")
_SPLIT_RE = re.compile("[-\u2013\u2014_+&,()\\[\\]]+")  # hyphen, en dash, em dash, and friends
_TOKEN_RE = re.compile(r"[A-Z0-9][A-Z0-9./%]*")


def tokenize(text: str) -> list[str]:
    """Uppercase token list. Ratios (``40/6.25``) and percents (``0.05%``) stay
    whole; hyphens and punctuation split."""
    upper = _SPLIT_RE.sub(" ", normalize_ws(text).upper())
    out: list[str] = []
    for tok in _TOKEN_RE.findall(upper):
        tok = tok.rstrip(".")
        # A bare word-slash-word ("VITAMIN A/D") splits; a numeric ratio does not.
        if "/" in tok and not _RATIO_RE.fullmatch(tok):
            out.extend(p.rstrip(".") for p in tok.split("/") if p)
        elif tok:
            out.append(tok)
    return out


def search_text(text: str) -> str:
    """The exact string the index is keyed on and a query is compared against —
    uppercase, hyphens flattened to spaces (``'SHELCAL-500 TABLET'`` →
    ``'SHELCAL 500 TABLET'``), so ``"shelcal 500"`` is a clean prefix of it."""
    return " ".join(tokenize(text))


def fts_terms(text: str) -> list[str]:
    """Query terms for the word index — split exactly the way the builder splits
    the text it indexed, so ``40/6.25`` becomes ``40``, ``6``, ``25`` on both
    sides and a query can never ask for a token that could not have been stored."""
    return [t for t in re.findall(r"[A-Za-z0-9]+", text.upper()) if t]


def query_tokens(text: str) -> list[str]:
    """:func:`tokenize` for the *query* side, minus the Hindi form and filler
    vocabulary (:data:`QUERY_STOP_WORDS`).

    Catalog names never go through this — the index is built from
    :func:`tokenize` — so the two sides still agree on every word that can
    actually appear in a product name. What this removes is the wrapper a
    pharmacist speaks the brand inside ("रैनटैक की गोली दे दीजिए"), which the
    scorer would otherwise charge ``_MISS`` for against the very SKU it wanted
    and which the phonetic net would otherwise try to read as a brand.
    """
    return [tok for tok in tokenize(text) if tok not in QUERY_STOP_WORDS]


# ─── vocabulary ───────────────────────────────────────────────────────────────

#: Dosage forms, alias → canonical. The value is what lands in ``form``.
FORM_WORDS: dict[str, str] = {
    "TABLET": "TABLET",
    "TABLETS": "TABLET",
    "TAB": "TABLET",
    "TABS": "TABLET",
    "TAOLET": "TABLET",
    "DT": "TABLET",
    "CAPSULE": "CAPSULE",
    "CAPSULES": "CAPSULE",
    "CAP": "CAPSULE",
    "CAPS": "CAPSULE",
    "SYRUP": "SYRUP",
    "SYP": "SYRUP",
    "SUSPENSION": "SUSPENSION",
    "SUSP": "SUSPENSION",
    "DROPS": "DROPS",
    "DROP": "DROPS",
    "GEL": "GEL",
    "EMULGEL": "EMULGEL",
    "CREAM": "CREAM",
    "LOTION": "LOTION",
    "OINTMENT": "OINTMENT",
    "OINT": "OINTMENT",
    "POWDER": "POWDER",
    "GRANULES": "GRANULES",
    "SACHET": "SACHET",
    "SACHETS": "SACHET",
    "INJECTION": "INJECTION",
    "INJ": "INJECTION",
    "INFUSION": "INFUSION",
    "VIAL": "INJECTION",
    "AMPOULE": "INJECTION",
    "PFS": "INJECTION",
    "SOLUTION": "SOLUTION",
    "LIQUID": "LIQUID",
    "SERUM": "SERUM",
    "SPRAY": "SPRAY",
    "SOAP": "SOAP",
    "BAR": "SOAP",
    "SHAMPOO": "SHAMPOO",
    "CONDITIONER": "CONDITIONER",
    "TOOTHPASTE": "TOOTHPASTE",
    "PASTE": "PASTE",
    "MOUTHWASH": "MOUTHWASH",
    "FACEWASH": "FACEWASH",
    "WASH": "WASH",
    "CLEANSER": "CLEANSER",
    "SCRUB": "SCRUB",
    "MOISTURIZER": "MOISTURIZER",
    "SUNSCREEN": "SUNSCREEN",
    "BALM": "BALM",
    "INHALER": "INHALER",
    "ROTACAP": "ROTACAP",
    "ROTACAPS": "ROTACAP",
    "RESPULES": "RESPULES",
    "RESPICAP": "RESPICAP",
    "RESPICAPS": "RESPICAP",
    "TRANSHALER": "INHALER",
    "MDI": "INHALER",
    "TRANSCAPS": "CAPSULE",
    "LOZENGES": "LOZENGES",
    "GUMMIES": "GUMMIES",
    "GUM": "GUM",
    "CHEWS": "GUMMIES",
    "SUPPOSITORY": "SUPPOSITORY",
    "ENEMA": "ENEMA",
    "PESSARY": "PESSARY",
    "OIL": "OIL",
    "EMULSION": "EMULSION",
    "SUSPENTION": "SUSPENSION",
    "KIT": "KIT",
    "PATCH": "PATCH",
    "WIPES": "WIPES",
    "STRIP": "STRIPS",
    "STRIPS": "STRIPS",
    "CARTRIDGE": "CARTRIDGE",
    "PENFILL": "PENFILL",
    "PEN": "PEN",
    "SHOT": "SHOT",
    "REFILL": "REFILL",
    "MASK": "MASK",
    "CONDOM": "CONDOM",
    "CONDOMS": "CONDOM",
    "DISKETTES": "DISKETTES",
    "BRUSH": "BRUSH",
    "DEVICE": "DEVICE",
    "MONITOR": "MONITOR",
    "SYRINGE": "SYRINGE",
    "TONER": "TONER",
    "MASSAGER": "MASSAGER",
}

#: The same vocabulary in Hindi, in the spellings a romanizer produces. These
#: are **query-side only** — no Indian product name contains them, and every one
#: of them was checked against the built ``tokens`` table before being added, so
#: dropping them from a query can never hide a real catalog word. They are not
#: merged into :data:`FORM_WORDS` because ``parse_name`` runs over catalog names
#: and must keep meaning exactly what it meant before.
#:
#: The value is the form they imply, or "" for the generic "medicine" words. The
#: form is not currently used to narrow (a spoken "goli" is weaker evidence than
#: a spoken "tablet"); what matters is that the word leaves ``q.tokens`` so it
#: cannot cost ``_MISS`` and cannot displace the brand from the head position.
HINDI_FORM_WORDS: dict[str, str] = {
    "GOLI": "TABLET",
    "GOLIYAN": "TABLET",
    "GOLIYAAN": "TABLET",
    "GOLIYA": "TABLET",
    "TIKIYA": "TABLET",
    "TIKIA": "TABLET",
    "TIKKI": "TABLET",
    "SHEESHI": "SYRUP",
    "SHISHI": "SYRUP",
    "SHISI": "SYRUP",
    "BOTAL": "SYRUP",
    "SIRAP": "SYRUP",
    "SHARBAT": "SYRUP",
    "MALHAM": "OINTMENT",
    "MARHAM": "OINTMENT",
    "MALAM": "OINTMENT",
    "SUI": "INJECTION",
    "TIKA": "INJECTION",
    "BOOND": "DROPS",
    "BOONDE": "DROPS",
    "BOONDEIN": "DROPS",
    "MANJAN": "TOOTHPASTE",
    "CHURAN": "POWDER",
    "CHURNA": "POWDER",
    "PUDIYA": "SACHET",
    "POTLI": "SACHET",
    "DAWA": "",
    "DAWAI": "",
    "DAWAA": "",
    "DAVA": "",
    "DAVAI": "",
    "PATTA": "",
    "PATTE": "",
    "DABBA": "",
    "PACKET": "",
}

#: Politeness, quantity and complaint words a pharmacist wraps the brand in
#: ("वोलिनी वाली ट्यूब दे दीजिए", "निमुलिड दे दो दर्द वाली"). Same rule as above:
#: query-side only, and every entry verified absent from the catalog index.
#: Without this list `de dijiye` reaches the phonetic net and lands on DAJIO —
#: which was eight of the twenty-six confident-wrong results in the first
#: adversarial run, and the single largest cluster in it.
HINDI_FILLERS = frozenset(
    {
        # "the one that is" / "give me"
        "WALA",
        "WALI",
        "WALE",
        "VALA",
        "VALI",
        "VALE",
        "DE",
        "DO",
        "DENA",
        "DEDO",
        "DIJIYE",
        "DIJIYA",
        "DIJIE",
        "DEDIJIYE",
        "DIJIYEGA",
        "CHAHIYE",
        "CHAIYE",
        "CHAHIE",
        "BHEJ",
        "BHEJO",
        "BHEJIYE",
        "LAGA",
        "LAGAO",
        # particles and pronouns
        "BHI",
        "KA",
        "KI",
        "KE",
        "KO",
        "HAI",
        "HAIN",
        "YE",
        "WO",
        "WOH",
        "ZARA",
        "THODA",
        "MUJHE",
        "AUR",
        "BAS",
        "JI",
        "PLEASE",
        # the complaint the brand is *for*, never part of its name
        "DARD",
        "KHANSI",
        "KHAANSI",
        "KHASI",
        "NAAK",
        "NAK",
        "PET",
        "BUKHAR",
        "SARDI",
        "ZUKAM",
        "JUKAM",
    }
)

#: Everything a query drops before it is tokenised into brand candidates.
QUERY_STOP_WORDS = frozenset(HINDI_FORM_WORDS) | HINDI_FILLERS

#: Route/qualifier words that belong *with* the following form word — the pill
#: label a pharmacist reads is "EYE DROPS", not "DROPS".
ROUTE_WORDS = frozenset(
    {
        "EYE",
        "EAR",
        "NASAL",
        "ORAL",
        "VAGINAL",
        "RECTAL",
        "DENTAL",
        "SKIN",
        "BODY",
        "FACE",
        "FOOT",
        "HAIR",
        "DRY",
        "MOUTH",
        "EYE/EAR",
    }
)

#: Generic leading words that are never a brand on their own.
_GENERIC_PREFIX = frozenset({"NEW", "DR", "THE", "MY"})

#: Units that may trail a number ("40 MG") or be fused to it ("60000IU").
_UNITS = ("MG", "MCG", "GM", "KG", "IU", "ML", "MEQ", "LAC", "MU", "G", "L", "%")
_UNIT_SET = frozenset(_UNITS)

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_RATIO_RE = re.compile(r"\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)+")
_FUSED_RE = re.compile(r"(\d+(?:\.\d+)?)(MG|MCG|GM|KG|IU|ML|MEQ|LAC|MU|G|L|%)")
_PCT_RE = re.compile(r"\d+(?:\.\d+)?%")


def is_number(token: str) -> bool:
    return bool(_NUMBER_RE.fullmatch(token))


def is_strengthish(token: str) -> bool:
    """True for anything a pharmacist would hear as a strength: 40, 40/6.25,
    500MG, 0.05%."""
    return bool(
        _NUMBER_RE.fullmatch(token)
        or _RATIO_RE.fullmatch(token)
        or _FUSED_RE.fullmatch(token)
        or _PCT_RE.fullmatch(token)
    )


def is_form_word(token: str) -> bool:
    return token in FORM_WORDS


# ─── family root ──────────────────────────────────────────────────────────────


def _weak(tokens: list[str]) -> bool:
    """A root is 'weak' while it cannot plausibly be a brand on its own: all
    tokens are 1-2 chars or digits ("4", "A TO", "D"), or it is a generic
    prefix ("NEW")."""
    if not tokens:
        return True
    if len(tokens) == 1 and tokens[0] in _GENERIC_PREFIX:
        return True
    return all(len(t) <= 2 or t.isdigit() for t in tokens)


def family_root(tokens: list[str], *, max_tokens: int = 3) -> list[str]:
    """The brand-root tokens of a tokenised product name.

    Normally the first token ("TELMA 40 TABLET" → TELMA). Extended only while the
    root so far is weak, which is what keeps the real multi-word roots together
    ("4 QUIN", "A TO Z", "D GAIN", "NEW FOLINAL") without fracturing the strong
    ones. Extension stops right after absorbing a number, so "B 29" and
    "B 29 LC" land in the same family.
    """
    if not tokens:
        return []
    root = [tokens[0]]
    i = 1
    while i < len(tokens) and len(root) < max_tokens and _weak(root):
        nxt = tokens[i]
        if is_form_word(nxt) or nxt in ROUTE_WORDS:
            break
        root.append(nxt)
        i += 1
        if is_strengthish(nxt):
            break  # a number closes the root: "B 29", "UV 50", "D 500"
    return root


# ─── strength / form / variant ────────────────────────────────────────────────


def _fmt_measure(number: str, unit: str) -> str:
    return f"{number}%" if unit == "%" else f"{number} {unit}"


@dataclass(frozen=True)
class ParsedName:
    """The parse of one cleaned product name."""

    family: str
    variant_label: str
    form: str
    strength: str


def parse_name(name_clean: str) -> ParsedName:
    """Split a cleaned product name into family / variant_label / form / strength."""
    tokens = tokenize(name_clean)
    root = family_root(tokens)
    rest = tokens[len(root) :]

    strength = ""
    form = ""
    used: set[int] = set()

    # -- strength: the first strength-ish run in the remainder.
    i = 0
    while i < len(rest):
        tok = rest[i]
        nxt = rest[i + 1] if i + 1 < len(rest) else ""
        if tok == "SPF" and is_number(nxt):
            strength, used = f"SPF {nxt}", used | {i, i + 1}
            break
        if _PCT_RE.fullmatch(tok) or _RATIO_RE.fullmatch(tok):
            strength = tok
            used.add(i)
            if nxt in _UNIT_SET:
                strength = _fmt_measure(tok, nxt)
                used.add(i + 1)
            break
        fused = _FUSED_RE.fullmatch(tok)
        if fused:
            strength = _fmt_measure(fused.group(1), fused.group(2))
            used.add(i)
            break
        if is_number(tok):
            strength = tok
            used.add(i)
            if nxt in _UNIT_SET:
                strength = _fmt_measure(tok, nxt)
                used.add(i + 1)
            break
        i += 1

    # -- form: the last form word, plus an immediately preceding route word.
    for idx in range(len(rest) - 1, -1, -1):
        tok = rest[idx]
        if idx in used or not is_form_word(tok):
            continue
        canonical = FORM_WORDS[tok]
        used.add(idx)
        if idx > 0 and rest[idx - 1] in ROUTE_WORDS and (idx - 1) not in used:
            used.add(idx - 1)
            canonical = f"{rest[idx - 1]} {canonical}"
        form = canonical
        break

    # -- variant label: whatever is left, in order. A unit token is dropped only
    # when it trails a number ("BA 300 MG TABLET" → the MG is noise); a bare
    # unit-looking letter after the brand is a real variant line and must
    # survive ("PAN-L", "ACERA-L", "BETAMIL GM", "AMYSTOP-G").
    leftover: list[str] = []
    for idx, tok in enumerate(rest):
        if idx in used or tok in ROUTE_WORDS:
            continue
        if tok in _UNIT_SET:
            prev = rest[idx - 1] if idx else (root[-1] if root else "")
            if is_strengthish(prev):
                continue
        leftover.append(tok)

    return ParsedName(
        family=" ".join(root),
        variant_label=" ".join(leftover),
        form=form,
        strength=strength,
    )


def canonical_form(text: str) -> str:
    """Map a spoken form hint ("drops", "eye drop", "tab") onto catalog form
    vocabulary. Returns "" when nothing in the hint is a known form."""
    parts = []
    for tok in tokenize(text):
        if tok in ROUTE_WORDS:
            parts.append(tok)
        elif is_form_word(tok):
            parts.append(FORM_WORDS[tok])
    if not parts:
        return ""
    if len(parts) > 1 and parts[0] in ROUTE_WORDS:
        return " ".join(parts[:2])
    return parts[-1]


def canonical_strength(text: str) -> str:
    """Normalise a spoken strength hint ("40", "40mg", "40 MG") → "40 MG"/"40"."""
    tokens = tokenize(text)
    for i, tok in enumerate(tokens):
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        fused = _FUSED_RE.fullmatch(tok)
        if fused:
            return _fmt_measure(fused.group(1), fused.group(2))
        if _PCT_RE.fullmatch(tok) or _RATIO_RE.fullmatch(tok):
            return tok
        if is_number(tok):
            return _fmt_measure(tok, nxt) if nxt in _UNIT_SET else tok
    return ""


def strength_number(strength: str) -> str:
    """The leading number of a strength string ("40 MG" → "40")."""
    match = _NUMBER_RE.match(strength.strip())
    return match.group(0) if match else ""


# ─── pack size ────────────────────────────────────────────────────────────────

_PACK_COUNT_RE = re.compile(r"^(\d+)\s*(?:'S|S|T|TAB|TABS|TB|C|CAP|CAPS|N|NO|PCS|PC)?$")
_PACK_MEASURE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(ML|GM|G|MG|KG|L|LTR|GMS)$")


def _pack_atom(raw: str) -> str:
    text = normalize_ws(raw).upper().replace("\u2019", "'").rstrip(".")
    text = re.sub(r"[,'`]\s*S$", "'S", text)
    text = text.replace("'S", "'S")
    if not text:
        return ""
    measure = _PACK_MEASURE_RE.match(text)
    if measure:
        unit = {"GMS": "GM", "G": "GM", "LTR": "L"}.get(measure.group(2), measure.group(2))
        return f"{measure.group(1)} {unit}"
    count = _PACK_COUNT_RE.match(text)
    if count:
        return f"{count.group(1)}'S"
    if text in {"VAIL", "1VAIL", "VIAL", "1VIAL"}:
        return "VIAL"
    fused = re.match(r"^(\d+(?:\.\d+)?)\s*([A-Z]+)$", text)
    if fused:
        return f"{fused.group(1)} {fused.group(2)}"
    return text


def normalize_pack_size(raw: str) -> str:
    """Pack_Size column → one display form.

    ``10`S`` → ``10'S``; ``15,S`` → ``15'S``; ``10T`` → ``10'S``; ``1*15`` →
    ``1x15``; ``100GM`` → ``100 GM``; ``1*42 GM`` → ``1x42 GM`` (with U+00D7).
    """
    text = normalize_ws(raw or "")
    if not text:
        return ""
    if "*" in text:
        left, _, right = text.partition("*")
        left_norm = normalize_ws(left).upper() or "1"
        right_raw = normalize_ws(right).upper()
        # "1*15" is 1 strip of 15 — the multiplier already says "count", so the
        # right side stays a bare number ("1x15"), not "1x15'S".
        right_norm = right_raw if _PACK_COUNT_RE.match(right_raw) else _pack_atom(right)
        if right_norm.endswith("'S"):
            right_norm = right_norm[:-2]
        left_num = re.match(r"^(\d+)", left_norm)
        return f"{left_num.group(1) if left_num else left_norm}{_TIMES}{right_norm}"
    return _pack_atom(text)


# ─── spoken numbers ───────────────────────────────────────────────────────────

_NUMBER_WORDS: dict[str, int] = {
    "ZERO": 0,
    "ONE": 1,
    "TWO": 2,
    "THREE": 3,
    "FOUR": 4,
    "FIVE": 5,
    "SIX": 6,
    "SEVEN": 7,
    "EIGHT": 8,
    "NINE": 9,
    "TEN": 10,
    "ELEVEN": 11,
    "TWELVE": 12,
    "THIRTEEN": 13,
    "FOURTEEN": 14,
    "FIFTEEN": 15,
    "SIXTEEN": 16,
    "SEVENTEEN": 17,
    "EIGHTEEN": 18,
    "NINETEEN": 19,
    "TWENTY": 20,
    "THIRTY": 30,
    "FORTY": 40,
    "FOURTY": 40,
    "FIFTY": 50,
    "SIXTY": 60,
    "SEVENTY": 70,
    "EIGHTY": 80,
    "NINETY": 90,
}
_SCALE_WORDS: dict[str, int] = {"HUNDRED": 100, "THOUSAND": 1000}

#: The same table in Hindi. A pharmacist speaking Hindi says the *strength* in
#: Hindi too ("पैनटॉप चालीस", "रैनटैक डेढ़ सौ"), and until these were here the
#: number survived as an unexplainable word token: charged ``_MISS`` (-6)
#: against the very SKU it identifies while ``_STRENGTH_HIT`` (+12) went unpaid.
#:
#: Spellings are the ones a romanizer actually writes, several per number. Three
#: obvious candidates are **deliberately absent** because the built catalog
#: already contains them as real tokens — ``TIN`` (5 postings), ``SAT`` (a
#: family) and ``BIS`` (3 postings). ``TEEN`` is kept: one posting, and "teen
#: sau" is far commoner than that one product.
_HINDI_NUMBER_WORDS: dict[str, int] = {
    "EK": 1,
    "DOO": 2,
    "TEEN": 3,
    "TEN": 3,
    "CHAR": 4,
    "CHAAR": 4,
    "PAANCH": 5,
    "PANCH": 5,
    "PAANCHH": 5,
    "CHHAH": 6,
    "CHHE": 6,
    "CHEH": 6,
    "CHAH": 6,
    "CHHAY": 6,
    "CHHEH": 6,
    "SAAT": 7,
    "AATH": 8,
    "AAT": 8,
    "NAU": 9,
    "NAV": 9,
    "DAS": 10,
    "DUS": 10,
    "DASH": 10,
    "GYARAH": 11,
    "BARAH": 12,
    "TERAH": 13,
    "CHAUDAH": 14,
    "PANDRAH": 15,
    "SOLAH": 16,
    "SATRAH": 17,
    "ATHARAH": 18,
    "UNNIS": 19,
    "BEES": 20,
    "BEESS": 20,
    "PACHCHEES": 25,
    "PACHEES": 25,
    "PACHIS": 25,
    "PACCHIS": 25,
    "TEES": 30,
    "TEESS": 30,
    "CHALIS": 40,
    "CHAALIS": 40,
    "CHALEES": 40,
    "CHAALEES": 40,
    "PACHAS": 50,
    "PACHAAS": 50,
    "PACHCHAS": 50,
    "PANCHAS": 50,
    "PACHASS": 50,
    "SAATH": 60,
    "SAITH": 60,
    "SATH": 60,
    "SATTAR": 70,
    "SATTAAR": 70,
    "ASSI": 80,
    "ASI": 80,
    "ASSEE": 80,
    "NABBE": 90,
    "NABBEY": 90,
    "NAVVE": 90,
}
_HINDI_SCALE_WORDS: dict[str, int] = {"SAU": 100, "HAZAR": 1000, "HAZAAR": 1000}

#: डेढ़ / ढाई / आधा — the fractional cardinals that have no English one-word
#: equivalent and are exactly how 150 and 250 are said at a counter.
_FRACTION_VALUES: dict[str, float] = {
    "DEDH": 1.5,
    "DEDHA": 1.5,
    "DEDHH": 1.5,
    "DHEDH": 1.5,
    "DHAI": 2.5,
    "DHAAI": 2.5,
    "DHAEE": 2.5,
    "DHHAI": 2.5,
    "ADHA": 0.5,
    "ADHAA": 0.5,
    "AADHA": 0.5,
}
#: सवा / पौने — a quarter more, a quarter less, *of the unit that follows*:
#: "sawa teen" is 3.25 but "sawa sau" is 125.
_FRACTION_MODS: dict[str, float] = {
    "SAWA": 0.25,
    "SAVA": 0.25,
    "SAWAA": 0.25,
    "PAUNE": -0.25,
    "PONE": -0.25,
    "PAUNA": -0.25,
}

#: Number words that only count as numbers in the right company — see
#: :func:`spoken_numbers`. The value is the unambiguous spelling to rewrite to.
_CONTEXT_NUMBER_WORDS: dict[str, str] = {"DO": "DOO", "DOH": "DOO"}

_ALL_NUMBER_WORDS = {**_NUMBER_WORDS, **_HINDI_NUMBER_WORDS}
_ALL_SCALE_WORDS = {**_SCALE_WORDS, **_HINDI_SCALE_WORDS}


def is_number_word(token: str) -> bool:
    """True for anything that opens a spoken-number run, English or Hindi."""
    return token in _ALL_NUMBER_WORDS or token in _FRACTION_VALUES or token in _FRACTION_MODS


def _fmt_number(value: float) -> str:
    """``150.0`` → ``"150"``; ``3.25`` → ``"3.25"``."""
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _fold_run(run: list[str]) -> str:
    """One run of number words → the digits a pharmacist means.

    Strengths are *said* as digit groups, not as arithmetic: "six fifty" is 650
    and "six two five" is 625, while "five hundred" is 500 and "twenty five" is
    25. So: a scale word multiplies, a tens+ones pair adds, and anything else
    concatenates.

    The Hindi fractions sit in front of that rule rather than inside it, because
    they modify the *unit* that follows them: "sawa sau" is 125 (a quarter more
    than a hundred) while "sawa teen" is 3.25 (a quarter more than three).
    """
    if not run:
        return ""
    modifier = 0.0
    if run[0] in _FRACTION_MODS:
        modifier = _FRACTION_MODS[run[0]]
        run = run[1:]
        if not run:  # a bare "सवा" says nothing on its own
            return ""
    if run[0] in _FRACTION_VALUES:
        value = _FRACTION_VALUES[run[0]] + modifier
        for word in run[1:]:
            if word in _ALL_SCALE_WORDS:
                value *= _ALL_SCALE_WORDS[word]
            else:
                break
        return _fmt_number(value)

    whole: int | None = None
    scaled = False
    for word in run:
        if word in _ALL_SCALE_WORDS:
            whole = (whole if whole is not None else 1) * _ALL_SCALE_WORDS[word]
            scaled = True
            continue
        digit = _ALL_NUMBER_WORDS.get(word)
        if digit is None:  # a fraction word mid-run — stop, it starts a new unit
            break
        if whole is None:
            whole = digit
        elif whole % 100 == 0 and 0 < digit < 100:
            whole += digit  # "six hundred fifty" → 650, "do sau pachas" → 250
        elif whole % 10 == 0 and 0 < digit < 10:
            whole += digit  # "sixty five" → 65, "six twenty five" → 620 + 5
        else:
            whole = int(f"{whole}{digit}")  # "six fifty" → 650, "six two five" → 625
    if whole is None:
        return ""
    # "sawa teen" adds a quarter of one; "sawa sau" already multiplied.
    return _fmt_number(whole * (1 + modifier) if scaled else whole + modifier)


#: Number words long enough to be recognised glued onto the end of a brand
#: ("eritelchalis", "oxetolteensau"), longest first so CHAALIS beats CHAR.
_FUSED_NUMBER_WORDS = tuple(
    sorted(
        (w for w in (*_ALL_NUMBER_WORDS, *_ALL_SCALE_WORDS, *_FRACTION_VALUES) if len(w) >= 3),
        key=len,
        reverse=True,
    )
)

#: What has to survive at the front for the stem to still look like a brand.
_MIN_FUSED_NUMBER_STEM = 4


def split_fused_number(token: str) -> tuple[str, list[str]]:
    """``"ERITELCHALIS"`` → ``("ERITEL", ["CHALIS"])``; ``"OXETOLTEENSAU"`` →
    ``("OXETOL", ["TEEN", "SAU"])``; ``("", [])`` when nothing is glued on.

    An STT decoder that loses the word boundary between a brand and its
    Hindi-spoken strength produces one long token that is neither a brand nor a
    number, so the phonetic net never runs and the strength is never credited.
    Peeling the number words off the tail gives back both.
    """
    word = re.sub(r"[^A-Z]", "", (token or "").upper())
    tail: list[str] = []
    while True:
        for number in _FUSED_NUMBER_WORDS:
            if word.endswith(number) and len(word) - len(number) >= _MIN_FUSED_NUMBER_STEM:
                tail.insert(0, number)
                word = word[: -len(number)]
                break
        else:
            break
    return (word, tail) if tail else ("", [])


def spoken_numbers(text: str) -> str:
    """Rewrite spelled-out numbers as digits ("telma forty" → "TELMA 40",
    "रैनटैक डेढ़ सौ" → "RANTAC 150", "eritelchalis" → "ERITEL 40").

    Only ever used as a *second* attempt at a query (a brand can legitimately
    contain a number word — SEVEN SEAS), never on catalog names.
    """
    tokens: list[str] = []
    for token in tokenize(text):
        stem, tail = ("", []) if is_number_word(token) else split_fused_number(token)
        tokens.extend([stem, *tail] if stem else [token])

    # "दो" is two *and* the imperative "give" — "do sau" is 200 but "de do" is
    # "hand it over". Only the reading that a scale word or a fraction demands
    # is taken; everywhere else DO stays a word and the filler list drops it.
    for i, token in enumerate(tokens):
        if token not in _CONTEXT_NUMBER_WORDS:
            continue
        after = tokens[i + 1] if i + 1 < len(tokens) else ""
        before = tokens[i - 1] if i else ""
        if after in _ALL_SCALE_WORDS or before in _FRACTION_MODS:
            tokens[i] = _CONTEXT_NUMBER_WORDS[token]

    out: list[str] = []
    run: list[str] = []
    for token in [*tokens, ""]:
        if is_number_word(token) or (token in _ALL_SCALE_WORDS and run):
            run.append(token)
            continue
        if run:
            out.append(_fold_run(run))
            run = []
        if token:
            out.append(token)
    return " ".join(t for t in out if t)


# ─── phonetics ────────────────────────────────────────────────────────────────

_VOWELS = frozenset("AEIOUY")

# Order matters: digraphs collapse before single letters, so PH→F beats P+H and
# CH→K beats C→K + H-drop.
_DIGRAPHS = (
    ("PH", "F"),
    ("WH", "V"),
    ("VH", "V"),  # व्ह ("bevhon", "moovh") — the aspirated व a romanizer spells VH
    ("GH", "G"),
    ("KH", "K"),
    ("TH", "T"),
    ("DH", "D"),
    ("BH", "B"),
    ("CHH", "K"),
    ("CH", "K"),
    ("SH", "S"),
    ("ZH", "J"),
    ("QU", "K"),
    ("KW", "K"),
    ("CK", "K"),
    ("SC", "S"),
    ("PS", "S"),
    ("EE", "I"),
    ("OO", "U"),
    ("AA", "A"),
    ("IE", "I"),
    ("EA", "I"),
    ("OU", "U"),
    ("AI", "E"),
    ("AY", "E"),
    ("EY", "I"),
    ("AU", "O"),
)
_SINGLES = str.maketrans({"C": "K", "Q": "K", "Z": "J", "W": "V", "X": "K"})


def phonetic_key(token: str) -> str:
    """A small metaphone-ish key, tuned for Hindi-transliteration artifacts.

    Collapses V/W, PH/F, EE/I, OO/U, T/TH, D/DH, K/C/Q, J/Z, S/SH, drops
    non-initial vowels and doubled letters, and folds any initial vowel to "A"
    (so ABEVIA / OBEVIA / abeyvee all land on ``ABV``).

    >>> phonetic_key("VOLINI"), phonetic_key("woliny")
    ('VLN', 'VLN')
    >>> phonetic_key("ABEVIA"), phonetic_key("abeyvee")
    ('ABV', 'ABV')
    """
    word = re.sub(r"[^A-Z]", "", (token or "").upper())
    if not word:
        return ""
    for src, dst in _DIGRAPHS:
        word = word.replace(src, dst)
    word = word.translate(_SINGLES)
    # X → KS would double the K it already collapsed to; keep it single.
    out: list[str] = []
    for i, ch in enumerate(word):
        if ch in _VOWELS:
            if i == 0:
                out.append("A")  # any initial vowel folds together
            continue
        if out and out[-1] == ch:
            continue
        out.append(ch)
    key = "".join(out)
    return key or "A"


def phonetic_bucket(key: str, width: int = 4) -> str:
    """The blocking prefix used for near-collisions (ABV vs ABVS)."""
    return key[:width]


# ─── alternate phonetic keys ──────────────────────────────────────────────────
#
# Some confusions are too destructive to fold *into* the key. Folding B into V
# would turn ABEVIA's ``ABV`` into a two-letter ``AV`` for every B-brand in the
# catalog, and the phonetic net is only safe because its keys are specific. So
# these live as *alternate* keys instead: a token is indexed (and probed) under
# its canonical key **plus** the keys it would have had under each confusion,
# and a match through an alternate is scored a notch below a canonical one
# (``search._PHON_ALT``). Both ``build_catalog`` and ``search`` call
# :func:`phonetic_keys`, so the index and a query cannot disagree about them.

#: C/G go soft before a front vowel — the reason "OMNIGEL" is heard as
#: "omnijel" and "PLACENTREX" as "plasentraks". Word-level, because the key
#: coder has already sent C to K and cannot tell the two C's apart afterwards.
_SOFT_C_RE = re.compile(r"C(?=[EIY])")
_SOFT_G_RE = re.compile(r"G(?=[EIY])")

#: The shortest alternate worth carrying. Below this a key is barely a key.
_MIN_ALT_KEY = 2


def _dedupe_runs(key: str) -> str:
    out: list[str] = []
    for ch in key:
        if not out or out[-1] != ch:
            out.append(ch)
    return "".join(out)


def _key_folds(key: str) -> list[str]:
    """The confusions that are cheapest to express on the finished key."""
    out = [key]
    # व is written B as often as V/W once it has been through a phone line:
    # "bolini"/VOLINI, "vecosules"/BECOSULES, "bebon"/BEVON. Both sides fold to
    # V, so the two spellings meet on one alternate.
    for candidate in list(out):
        folded = _dedupe_runs(candidate.replace("B", "V"))
        if folded != candidate:
            out.append(folded)
    # An epenthetic vowel props up a word-initial s-cluster ("isporlac" for
    # SPORLAC, "istamlo" for STAMLO); phonetic_key folds it to a leading A.
    for candidate in list(out):
        if len(candidate) >= 4 and candidate[0] == "A" and candidate[1] == "S":
            out.append(candidate[1:])
    return out


def spoken_shape(token: str) -> str:
    """The token rewritten in the *folded alphabet* — vowels kept, every
    consonant confusion applied.

    ``phonetic_key`` throws the vowels away, which makes it a good bucket and a
    poor yardstick. When two tokens have met on an alternate key, the question
    "how alike are they, really?" has to be asked in the alphabet they agreed
    on, or a genuine B/V pair scores no better than an accident:

    >>> spoken_shape("bolini"), spoken_shape("VOLINI")   # the same word
    ('VOLINI', 'VOLINI')
    >>> spoken_shape("abivays"), spoken_shape("AVAS")    # not the same word
    ('AVIVES', 'AVAS')
    """
    word = re.sub(r"[^A-Z]", "", (token or "").upper())
    word = _SOFT_G_RE.sub("J", _SOFT_C_RE.sub("S", word))
    for src, dst in _DIGRAPHS:
        word = word.replace(src, dst)
    return _dedupe_runs(word.translate(_SINGLES).replace("B", "V"))


def phonetic_keys(token: str) -> list[str]:
    """Every key ``token`` may be found under — canonical first, then alternates.

    >>> phonetic_keys("VOLINI")
    ['VLN']
    >>> phonetic_keys("bolini")
    ['BLN', 'VLN']
    >>> phonetic_keys("OMNIGEL")
    ['AMNGL', 'AMNJL']
    >>> phonetic_keys("isporlac")
    ['ASPRLK', 'SPRLK']
    """
    word = re.sub(r"[^A-Z]", "", (token or "").upper())
    primary = phonetic_key(word)
    if not primary:
        return []
    soft = _SOFT_G_RE.sub("J", _SOFT_C_RE.sub("S", word))
    bases = [primary] if soft == word else [primary, phonetic_key(soft)]
    keys: list[str] = []
    for base in bases:
        for key in _key_folds(base):
            if key not in keys and (key == primary or len(key) >= _MIN_ALT_KEY):
                keys.append(key)
    return keys


# ─── fused form words ─────────────────────────────────────────────────────────

#: Form words that arrive glued to the brand in fast speech ("volnijel",
#: "beplexfort", "omnijel"), in the spellings a romanizer produces. Longest
#: first, so FORTE is stripped before FORT and SPRAY before SPRA.
_FUSED_SUFFIXES = tuple(
    sorted(
        # English form words. Kept whitespace-delimited rather than as a list
        # literal (SIM905): one quoted, comma'd item per word would be 60-odd
        # lines of punctuation for a table whose whole point is that it reads as
        # prose.
        "GEL JEL SPRAY SPREY SPRAI CREAM KREAM FORTE FORT TABLET TAB SYRUP SIRUP "  # noqa: SIM905
        "DROPS DROP POWDER OINTMENT LOTION CAPSULE BALM PLUS "
        # Hindi form words — the same thing said in the other language.
        "GOLI GOLIYAN GOLIYAAN TIKIYA TIKIA SHEESHI SHISHI BOTAL SHARBAT "
        "MALHAM MARHAM MALAM CHURAN CHURNA MANJAN DAWA DAWAI DAVAI "
        # Hindi fillers, which glue on just as readily as form words do
        # ("setafilwala", "nimuliddedo") and are pure noise once detached.
        "WALA WALI WALE VALA VALI DEDO DEDIJIYE DIJIYE CHAHIYE".split(),
        key=len,
        reverse=True,
    )
)

#: What has to be left over for the stem to still be a brand.
_MIN_FUSED_STEM = 4


def fused_stem(token: str) -> str:
    """``"VOLNIJEL"`` → ``"VOLNI"``, ``"BEPLEXFORT"`` → ``"BEPLEX"``,
    ``"NIMULIDDEDO"`` → ``"NIMULID"``; ``""`` when the token carries no glued
    form word (or nothing brand-sized is left).

    Fast speech runs the form word into the brand, and the fused token's
    phonetic key then overruns the family's by two or three characters — far
    enough that no prefix can bridge it. Stripping the suffix gives the phonetic
    stage a second, brand-shaped probe; the fused token is still probed too, so
    a brand that genuinely ends in one of these words (OMNIGEL) loses nothing.

    Suffixes are peeled repeatedly, because Hindi stacks them — "goli wali" glues
    down to one token as readily as one word does.
    """
    word = re.sub(r"[^A-Z]", "", (token or "").upper())
    stem = word
    while True:
        for suffix in _FUSED_SUFFIXES:
            if stem.endswith(suffix) and len(stem) - len(suffix) >= _MIN_FUSED_STEM:
                stem = stem[: -len(suffix)]
                break
        else:
            break
    return stem if stem != word else ""
