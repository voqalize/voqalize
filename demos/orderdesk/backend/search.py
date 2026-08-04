"""Deterministic catalog resolution over ``catalog.db`` — the demo's spine.

A pharmacist says "volini" and means one of ten SKUs; says "woliny spray" and
means the same brand through a phone line; says "telma 40" and means exactly one
row. This module turns each of those into a :class:`Resolution` the brain can act
on **without asking the model to guess** — no LLM, no network, no randomness. The
model's only job is to read ``differing_axes`` and ask one short question.

Everything runs off one read-only sqlite connection opened lazily at module
level, so the first ``resolve()`` pays the open and every later one is a few
indexed lookups (<50 ms warm, typically <5 ms).

The pipeline (DESIGN.md §2, in order — each stage only runs if the previous one
found nothing):

1. **exact / prefix** on ``name_clean``. Index-friendly and does most of the
   work: "telma 40" prefixes exactly one row, "volini" prefixes ten, "4 quin"
   prefixes six. The prefix is token-bounded (``q + " "``) so "PAN" never
   reaches into "PANTOP".
2. **per-token prefix**, AND-ed, over the ``tokens`` inverted index (plain
   sqlite, not fts5 — see ``build_catalog.py``: the interpreter that runs this
   demo has no fts5 module). Handles out-of-order and partial words. If the AND
   is too strict (a spoken pack size appears in no name), the numeric terms are
   dropped and it is retried.
3. **phonetic** on the brand-ish tokens — the misheard-brand net. Scored by key
   match *plus* a spelling-similarity tiebreak plus brand breadth, because
   VOLINI, VELIN and VILANO all share the key ``VLN`` and only one of them is
   what a pharmacist shouting over a counter meant. Each token is probed under
   every key ``normalize.phonetic_keys`` gives it — the canonical one and the
   *alternates* for the confusions too destructive to fold into a key ("bolini"
   probes ``BLN`` and ``VLN``) — and a token with a form word fused onto it
   ("volnijel") probes its stem as well.

Then one uniform scorer ranks every candidate, survivors are everything within
:data:`_BAND` of the best (so a decisive winner stands alone and a genuine tie
stays a tie), and the survivors are grouped by family into
matched / multi_variant / multi_family / not_found.
"""

from __future__ import annotations

import re
import sqlite3
import sys
from bisect import bisect_left
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Any

try:  # package import (brain) vs flat import (script / test harness)
    from .normalize import (
        FORM_WORDS,
        canonical_form,
        canonical_strength,
        fts_terms,
        fused_stem,
        is_number_word,
        is_strengthish,
        phonetic_keys,
        query_tokens,
        search_text,
        split_fused_number,
        spoken_numbers,
        spoken_shape,
        strength_number,
    )
except ImportError:  # pragma: no cover — the flat-import path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from normalize import (  # type: ignore[no-redef]
        FORM_WORDS,
        canonical_form,
        canonical_strength,
        fts_terms,
        fused_stem,
        is_number_word,
        is_strengthish,
        phonetic_keys,
        query_tokens,
        search_text,
        split_fused_number,
        spoken_numbers,
        spoken_shape,
        strength_number,
    )

DB_PATH = Path(__file__).resolve().parent / "catalog.db"

#: The axes a follow-up question can be about, **in verbal-question priority**.
#: The brain builds its one question from ``differing_axes[0]``, so the order is
#: part of the contract: form is the crispest thing to ask out loud ("4 Quin —
#: drops or ointment?"), then strength, then the suffix line. Pack size is last
#: because a pack list reads far better as on-screen pills than as speech.
AXES = ("form", "strength", "variant_label", "pack_size")

_UNIT_TOKENS = frozenset({"MG", "MCG", "GM", "KG", "IU", "ML", "MEQ", "LAC", "MU", "G", "L", "%"})

# ─── scoring weights ──────────────────────────────────────────────────────────
# Tuned against ~20 real pharmacist phrasings (see tests). The one invariant that
# matters: a *decisive* signal (whole-name prefix, matching pack size) must
# outweigh _BAND, and an incidental one (a shared word) must not.

_EXACT_NAME = 100.0  # name_clean == query
_PREFIX_NAME = 60.0  # name_clean starts with "query "
_TOKEN_HIT = 10.0  # query token is a whole name token
_TOKEN_PREFIX = 6.0  # query token prefixes a name token ("cetaph" → CETAPHIL)
_FAMILY_HEAD = 8.0  # query starts on this family's first word
_STRENGTH_HIT = 12.0  # leftover number is this SKU's strength
_PACK_HIT = 14.0  # leftover number is this SKU's pack size
_MISS = -6.0  # query token this SKU cannot explain
_EXTRA_TOKEN = -0.5  # per unexplained name token — prefer the concise SKU
_IN_STOCK = 0.5  # last-resort tiebreak

_PHON_EXACT = 30.0  # phonetic key identical
_PHON_NEAR = 16.0  # phonetic key one character off (ABV vs ABVS)
_PHON_FUZZY = 8.0  # phonetic key one *interior* edit off (MNTRLS vs MNTR) — the weakest claim
_PHON_SIM = 40.0  # scaled by the difflib ratio between the spoken token and the brand
_PHON_BREADTH = 12.0  # scaled by min(1, sku_count/8) — deep brands are said more often
_PHON_ALT = 4.0  # charged when the two sides met on an *alternate* key, not the canonical one

#: How much of a family's phonetic score is staked on *coverage* — the share of
#: the spoken brand the probe that found it actually accounts for. At 0.5 a
#: family that explains half the utterance keeps three quarters of its score, and
#: one that explains a quarter keeps five eighths.
#:
#: It has to be a multiplier rather than a bonus, because the thing it is fixing
#: is a *ratio*. "pan kriyo flat" is PANKREOFLAT, and PAN matches the first word
#: of it perfectly — exact key, similarity 1.0, a hundred SKUs deep. No additive
#: term survives that. What sinks it is that a perfect answer to a quarter of the
#: question is not three quarters of an answer.
_PHON_COVER = 0.5

#: Charged to a *short* family that a much longer token landed on. A four-letter
#: family is a phonetic attractor — REST, NEBI, WAL sit inside the key space of
#: dozens of longer brands — so "sinarest" reaching REST has to outscore that
#: penalty with real similarity, which it cannot.
_PHON_SHORT = 14.0
_PHON_SHORT_MAX = 4  # family compact length at or under which the penalty applies

# Spelling floors under the phonetic net. Without them every key collision is a
# match and COLDACT (genuinely absent from this catalog — the demo's not_found
# item) comes back as CALDIKIND. A key that matches exactly has already earned
# some trust, so it is held to a lower bar than a key that is merely close.
_PHON_SIM_EXACT = 0.45
_PHON_SIM_NEAR = 0.50
#: An alternate key is a looser claim, so it is held to a much higher bar —
#: and to a bar measured in the folded alphabet (``normalize.spoken_shape``),
#: where a real B/V pair scores ~1.0 and a coincidence scores ~0.6.
_PHON_SIM_ALT = 0.72
#: An interior-edit hit is the loosest claim of all, and — like an alternate — it
#: is judged in the folded alphabet, because the whole point of reaching for it
#: is that the *keys* have already disagreed. "ratak"/RANTAC differ by a dropped
#: nasal and score 0.91 there against 0.73 raw; "aksitol"/OXETOL are genuinely
#: different words and score 0.62 either way.
_PHON_SIM_FUZZY = 0.70

# ─── confidence discipline ────────────────────────────────────────────────────
# The stage a candidate came out of says how it was found, not how *well*. A
# clipped word, a two-letter family and a skeleton-only key hit all reach the
# scorer looking exactly like a clean recovery, and the old 9-cell table handed
# each of them the same 0.62 as a real one. So the stage now only sets a
# ceiling; what a resolution actually claims is that ceiling scaled by quality —
# the shape agreement between what was *said* and the family that answered.
#
# Below :data:`_QUALITY_FLOOR` no answer is asserted at all: matched and
# multi_variant become multi_family (a question) or not_found. Asking twice
# costs a pharmacist five seconds; a confident wrong family costs a wrong
# medicine, so the trade is never close.

#: At or above this, the stage's own confidence stands unreduced.
_QUALITY_FULL = 0.80
#: Under this, the engine refuses to name a family. Set just under the shape
#: agreement of a genuine phone-line mangling ("woliny" → VOLINI, 0.83) and just
#: over a three-letter truncation ("zan" → ZANDU, 0.75), which is the line the
#: adversarial corpus draws between a brand recovered and a brand guessed.
_QUALITY_FLOOR = 0.82

#: The bar when the family was recovered by *joining words the speaker said
#: separately* — "thairo norm" → THYRONORM, "phal jil" → ALZIL.
#:
#: Those joins are the net's most productive trick and its least evidenced one.
#: Every other probe is a word somebody actually said; a gram is a word the
#: engine decided they meant to say, and it manufactures a longer token, which
#: buys full coverage and a similarity measured over more characters — every term
#: in the score moves the same way at once. Holding the guess to a higher bar
#: costs almost nothing, because a family that misses it is still listed first on
#: the option card. It just stops being asserted.
_QUALITY_FUSED = 0.92

#: …and under *this*, a family is not even worth putting on a card. A question
#: is only worth asking when at least one of its options could be the answer:
#: "zan" is worth showing ZANDU for, "coldact" — a brand this catalog does not
#: carry — is worth showing nothing for, and the half-point between their shape
#: scores (0.75 against CLINDAC's 0.71) is the entire difference.
_QUALITY_MIN = 0.72

#: Survivor band. Anything within this of the best score stays a candidate, so
#: ambiguity is *found* rather than declared: a lone winner clears the band and
#: becomes ``matched``, ten tied VOLINI SKUs all stay and become ``multi_variant``.
_BAND = 10.0

_MAX_VARIANTS = 8
_MAX_FAMILIES = 5
_FTS_LIMIT = 300
_HIGH = "￿"  # sorts after every token byte: the open end of a prefix range


# ─── views (the wire shapes) ──────────────────────────────────────────────────


@dataclass(frozen=True)
class SkuView:
    """One catalog row. ``wire()`` is ``SkuWire`` in ``frontend/src/types.ts``."""

    code: str
    name: str
    family: str
    variant_label: str
    form: str
    strength: str
    pack_size: str
    mrp: float
    ptr: float
    stock: int
    manufacturer: str
    scheme: str

    def wire(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "family": self.family,
            "variant_label": self.variant_label,
            "form": self.form,
            "strength": self.strength,
            "pack_size": self.pack_size,
            "mrp": self.mrp,
            "ptr": self.ptr,
            "stock": self.stock,
            "manufacturer": self.manufacturer,
            "scheme": self.scheme,
        }

    def label(self) -> str:
        """The shortest human line that still identifies this SKU on a pill."""
        parts = [p for p in (self.variant_label, self.strength, self.form, self.pack_size) if p]
        return " ".join(parts) or self.name


@dataclass(frozen=True)
class FamilyView:
    """A brand root. ``wire()`` is ``FamilyWire`` in ``frontend/src/types.ts``."""

    family: str
    manufacturers: list[str]
    forms: list[str]
    sku_count: int
    hint: str

    def wire(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "manufacturers": list(self.manufacturers),
            "forms": list(self.forms),
            "sku_count": self.sku_count,
            "hint": self.hint,
        }


@dataclass(frozen=True)
class Resolution:
    """What the catalog can say about one spoken line item."""

    status: str  # "matched" | "multi_variant" | "multi_family" | "not_found"
    sku: SkuView | None = None
    family: str | None = None
    variants: list[SkuView] = field(default_factory=list)
    families: list[FamilyView] = field(default_factory=list)
    differing_axes: list[str] = field(default_factory=list)
    confidence: float = 0.0


# ─── connection ───────────────────────────────────────────────────────────────

_conn: sqlite3.Connection | None = None


def connection() -> sqlite3.Connection:
    """The process-wide read-only connection, opened on first use."""
    global _conn
    if _conn is None:
        if not DB_PATH.exists():  # pragma: no cover — a missing build
            raise RuntimeError(
                f"orderdesk: {DB_PATH} is missing — run `python {Path(__file__).parent}"
                "/build_catalog.py` to build it from the CSV"
            )
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _conn = conn
    return _conn


#: Every column the scorer or the wire needs — ``name_clean`` is scoring-only.
_COLUMNS = (
    "code, name, name_clean, family, variant_label, form, strength, pack_size, "
    "mrp, ptr, stock, manufacturer, scheme"
)


def _sku(row: sqlite3.Row) -> SkuView:
    return SkuView(
        code=row["code"],
        name=row["name"],
        family=row["family"],
        variant_label=row["variant_label"],
        form=row["form"],
        strength=row["strength"],
        pack_size=row["pack_size"],
        mrp=float(row["mrp"]),
        ptr=float(row["ptr"]),
        stock=int(row["stock"]),
        manufacturer=row["manufacturer"],
        scheme=row["scheme"],
    )


# ─── query parsing ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Query:
    tokens: list[str]  # ["VOLINI", "GEL", "100", "GM"]
    text: str  # "VOLINI GEL 100 GM" — compared against name_clean
    measures: list[str]  # per token: the number fused with its unit ("100GM")
    brandish: list[str]  # every probe the phonetic net gets: words, grams, stems
    words: list[str]  # just the brand-ish words, in the order they were said
    grams: frozenset[str]  # the probes that join words the speaker said apart
    span: int  # characters of spoken brand a probe has to account for


#: A brand with its strength run into it — "ZIFI200", "PANTOP40". The stem has to
#: be word-sized so that a genuine alphanumeric code is left alone.
_DIGIT_TAIL_RE = re.compile(r"([A-Z]{3,})(\d+)")


def _split_digit_tail(token: str) -> list[str]:
    """``"ZIFI200"`` → ``["ZIFI", "200"]``; anything else → ``[token]``.

    An STT decoder writes the strength straight onto the brand whenever the
    speaker does not pause, and the fused token is then a word the catalog has
    never seen: no name prefixes it, no token row carries it, and its phonetic
    key runs three characters past the brand's. Splitting it costs nothing when
    the token was never fused and recovers both halves when it was.
    """
    match = _DIGIT_TAIL_RE.fullmatch(token)
    if not match or match[1] in _UNIT_TOKENS or match[1] in FORM_WORDS:
        return [token]
    return [match[1], match[2]]


def _parse_query(query: str) -> _Query:
    tokens = [part for tok in query_tokens(query) for part in _split_digit_tail(tok)]
    measures: list[str] = []
    for i, tok in enumerate(tokens):
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        measures.append(f"{tok}{nxt}" if is_strengthish(tok) and nxt in _UNIT_TOKENS else tok)
    spoken = [
        tok
        for tok in tokens
        if len(tok) >= 2 and tok.isalpha() and tok not in FORM_WORDS and tok not in _UNIT_TOKENS
    ]
    words = [
        tok
        for tok in spoken
        # A spoken number is a strength, never a brand. Letting "chalis" or
        # "forty" into the net *on its own* gives it a brand-shaped probe for a
        # word that names no brand, and the family it lands on is pure noise.
        if len(tok) >= 3 and not is_number_word(tok)
    ]
    # A brand heard as two or three words ("thairo norm", "pan kriyo flat") must
    # still find the one-word brand, so adjacent runs are joined up as extra
    # phonetic probes — the mirror of the squashed rows the builder writes for
    # "4 QUIN" → 4QUIN. These are built from every spoken word, number words and
    # two-letter words included: "nau rok ind" is NUROKIND and "uv doo" is UV
    # DOUX, and neither survives being told that "nau" is a nine.
    pairs = [a + b for a, b in pairwise(spoken)]
    pairs += [a + b + c for a, b, c in zip(spoken, spoken[1:], spoken[2:], strict=False)]
    # …and the same brand heard as *one* word ("volnijel", "beplexfort") probes
    # its stem too, since a fused form word pushes the key clean past the
    # family's. The fused token is still probed, so OMNIGEL keeps working.
    stems = [stem for stem in (fused_stem(word) for word in words) if stem]
    # …and a brand with a Hindi strength glued on ("eritelchalis") probes the
    # brand half, which is the only half that names anything.
    stems += [stem for stem, _tail in (split_fused_number(word) for word in words) if stem]
    return _Query(
        tokens=tokens,
        text=" ".join(tokens),
        measures=measures,
        brandish=list(dict.fromkeys([*words, *pairs, *stems])),
        words=words,
        grams=frozenset(pairs),
        # Every spoken word counts against coverage, including the ones that are
        # too short or too numeric to be probed on their own — "chhah tan" is
        # eight characters of brand however the six is spelled, and a family that
        # answers for three of them has answered for three of them.
        span=max(1, sum(len(word) for word in spoken)),
    )


# ─── candidate gathering ──────────────────────────────────────────────────────


def _by_name(conn: sqlite3.Connection, text: str) -> list[sqlite3.Row]:
    """Exact hits plus token-bounded prefix hits, in one indexed range scan."""
    lo, hi = f"{text} ", f"{text}!"  # "!" is the byte after " "
    return conn.execute(
        f"SELECT {_COLUMNS} FROM products WHERE name_clean = ? OR (name_clean >= ? AND name_clean < ?)",
        (text, lo, hi),
    ).fetchall()


def _fts(conn: sqlite3.Connection, terms: list[str]) -> list[sqlite3.Row]:
    """Rows whose text carries *every* term as a word or a word prefix.

    Plain sqlite over the ``tokens`` inverted index, deliberately: the uv-built
    CPython that runs this demo links a sqlite with no fts5 module, and an fts5
    index would take out exactly the prefix queries ("thyro" mid-typing) while
    whole-word queries kept working. Each term is one range scan of the token
    primary key; the per-term row sets are intersected here.
    """
    if not terms:
        return []
    params: list[Any] = []
    clauses: list[str] = []
    for term in sorted(terms, key=len, reverse=True):  # most selective term first
        clauses.append("p.rowid IN (SELECT ref FROM tokens WHERE token >= ? AND token < ?)")
        params += [term, term + _HIGH]
    params.append(_FTS_LIMIT)
    # Shortest name first: with no bm25 to lean on, the concise product ("PAN 40
    # TABLET") is the better guess than the long one — and it is only a cut, the
    # scorer re-ranks whatever survives it.
    return conn.execute(
        f"SELECT {', '.join('p.' + c for c in _COLUMNS.split(', '))} FROM products p "
        f"WHERE {' AND '.join(clauses)} "
        "ORDER BY LENGTH(p.name_clean), p.code LIMIT ?",
        params,
    ).fetchall()


def _fts_relaxed(conn: sqlite3.Connection, q: _Query) -> tuple[list[sqlite3.Row], bool]:
    """``(rows, complete)`` — the AND over every term, then over the words only,
    then dropping the tail. ``complete`` is False exactly when the tail was
    dropped, i.e. when the rows returned do not answer for the whole utterance.

    "volini gel 100 gm" has no name carrying "100" (the pack size lives in its
    own column), so the strict AND is empty and the word-only retry is what
    finds the two VOLINI GEL rows — the scorer then picks the 100 GM one. That
    retry is still *complete*: every spoken word is accounted for.

    Dropping the tail is a different thing entirely. It answers a question
    nobody asked — the first word or two of a damaged brand — and until the
    caller was told so, that answer short-circuited the phonetic stage: a query
    whose brand was mangled beyond its second syllable would find some unrelated
    catalog word sharing its first three letters and never reach the net built
    to recover it.
    """
    terms = fts_terms(q.text)
    for attempt in (terms, [t for t in terms if not t.isdigit() and t not in _UNIT_TOKENS]):
        if attempt and (rows := _fts(conn, attempt)):
            return rows, True
    words = [t for t in terms if not t.isdigit()]
    brand = set(q.words)
    for cut in range(len(words) - 1, 0, -1):
        if rows := _fts(conn, words[:cut]):
            # Losing a form word off the end costs nothing — "itch guard plus
            # cream" still names ITCH GUARD PLUS. Losing a *brand* word is the
            # case this flag exists for.
            return rows, not (set(words[cut:]) & brand)
    return [], False


@lru_cache(maxsize=4096)
def _shape(token: str) -> str:
    """``normalize.spoken_shape``, memoized — the same few thousand brand-root
    tokens come back out of the ``phonetic`` table on every query."""
    return spoken_shape(token)


# ─── the phonetic index ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class _PhonRow:
    token: str
    family: str
    alt: int


@dataclass(frozen=True)
class _PhonIndex:
    """The whole ``phonetic`` table in memory, plus the two lookups sqlite could
    not give cheaply.

    It is a small table — ~11k rows over ~8.5k distinct keys, none longer than
    nine characters — and holding it costs a couple of megabytes once. What that
    buys is the *skeleton* map: every key indexed under each of its one-character
    deletions, which turns "is there a stored key within one interior edit of
    this one" into a handful of dict lookups. Done in SQL that is a full table
    scan per probe; done here it is free, and the ±1 key-length window that used
    to be the net's outer wall can open up without costing latency.
    """

    by_key: dict[str, tuple[_PhonRow, ...]]
    keys: list[str]  # sorted — the prefix ranges are bisected out of this
    skeletons: dict[str, tuple[str, ...]]
    counts: dict[str, int]  # family → SKU count

    def prefixed(self, prefix: str) -> list[str]:
        lo = bisect_left(self.keys, prefix)
        hi = bisect_left(self.keys, prefix + _HIGH, lo)
        return self.keys[lo:hi]

    def inserted(self, key: str) -> tuple[str, ...]:
        """Stored keys that are *key* with one character inserted — the dropped
        nasal, the swallowed consonant: RTK ("ratak") reaching RNTK (RANTAC)."""
        return self.skeletons.get(key, ())

    def edit1(self, key: str) -> set[str]:
        """Stored keys one insertion, deletion or substitution away from *key*."""
        out: set[str] = set(self.inserted(key))
        for gap in _deletions(key):
            if gap in self.by_key:
                out.add(gap)  # stored key has one char less
            out.update(self.skeletons.get(gap, ()))  # one char different
        out.discard(key)
        return out

    def clipped(self, key: str, window: int) -> list[str]:
        """Stored keys that *key* extends — the brand with something glued to
        its end. ``MNTRLS`` ("montair els ee") reaches ``MNTR`` (MONTAIR); no
        amount of prefix scanning ever will, because the extra characters are on
        the query's side."""
        return [
            key[:cut]
            for cut in range(len(key) - 1, max(2, len(key) - window) - 1, -1)
            if key[:cut] in self.by_key
        ]


def _deletions(word: str) -> list[str]:
    return [word[:i] + word[i + 1 :] for i in range(len(word))]


_phon_index: _PhonIndex | None = None


def _phonetic_index(conn: sqlite3.Connection) -> _PhonIndex:
    global _phon_index
    if _phon_index is None:
        by_key: dict[str, list[_PhonRow]] = {}
        skeletons: dict[str, set[str]] = {}
        for row in conn.execute("SELECT token, key, family, alt FROM phonetic"):
            key = row["key"]
            if key not in by_key:
                by_key[key] = []
                if len(key) >= 4:  # a skeleton of a 3-char key is every brand
                    for gap in _deletions(key):
                        skeletons.setdefault(gap, set()).add(key)
            by_key[key].append(_PhonRow(row["token"], row["family"], row["alt"]))
        counts = dict(conn.execute("SELECT family, COUNT(*) FROM products GROUP BY family"))
        _phon_index = _PhonIndex(
            by_key={k: tuple(v) for k, v in by_key.items()},
            keys=sorted(by_key),
            skeletons={k: tuple(sorted(v)) for k, v in skeletons.items()},
            counts=counts,
        )
    return _phon_index


@dataclass(frozen=True)
class _PhonHit:
    """One family the net reached, and how well it was reached."""

    score: float  # what the scorer adds to every SKU of the family
    sim: float  # spelling agreement with the probe that found it
    cover: float  # how much of the spoken brand that probe was
    probe: str  # the probe itself — which spoken words this family has paid for


#: How far a stored key's length may differ from the probe's, by probe length.
#: A three-character key is a whole syllable, so one character of slack is the
#: difference between two brands; a seven-character key has room for a dropped
#: nasal *and* an epenthetic vowel and still be the same word said badly.
def _key_window(key: str) -> int:
    return 1 if len(key) <= 4 else 2


def _phonetic_families(conn: sqlite3.Connection, q: _Query) -> dict[str, _PhonHit]:
    """Brand-root families a misheard token could have meant, with a score.

    Key equality alone is not enough to choose: VOLINI / VELIN / VILANO all key
    to ``VLN``. The spelling-similarity term is what makes "woliny" land on
    VOLINI, and the breadth term breaks the remaining ties toward the brand a
    counter actually stocks ten of.

    Each token is probed under every key :func:`normalize.phonetic_keys` gives
    it — the canonical one and the alternates for the confusions the coder
    refuses to fold ("bolini" probes both ``BLN`` and ``VLN``). A hit through an
    alternate on *either* side pays ``_PHON_ALT`` and is held to the stricter
    spelling floor, so the alternates widen the net without flattening the
    ranking the canonical keys produce.

    Three things shape the ranking beyond the raw key match:

    * **coverage** — a probe that is the whole spoken brand outranks one that is
      half of it, which is what lets NEBICARD beat NEBI for "nebi card";
    * **breadth scaled by similarity** — depth is a tiebreak between plausible readings,
      not a reason to prefer an implausible deep brand to a plausible thin one,
      so the breadth bonus is now paid in proportion to how well the two words
      actually agree;
    * **shortness** — a four-letter family sits inside the key space of dozens
      of longer brands and attracts every one of them, so it pays for the
      privilege unless the spoken word is short too.
    """
    index = _phonetic_index(conn)
    span = q.span
    scores: dict[str, _PhonHit] = {}
    for token in q.brandish:
        # A one-character key is every brand at once — the alternates are already
        # length-guarded, this drops a degenerate *canonical* one.
        keys = [k for k in phonetic_keys(token) if len(k) >= 2]
        shape = _shape(token)
        cover = min(1.0, len(token) / span)
        seen: dict[str, tuple[float, float]] = {}  # family → (score, sim)
        for rank, key in enumerate(keys):
            window = _key_window(key)
            # Best claim wins per stored key: exact ⊐ prefix-near ⊐ interior edit.
            classes: dict[str, int] = {}
            for stored in index.prefixed(key):
                classes[stored] = 0 if stored == key else 1
            if len(key) > 3:
                for stored in index.prefixed(key[:-1]):  # stored key one char shorter
                    classes.setdefault(stored, 1)
            # The three bounded fuzzy probes, each one a different way for the
            # two keys to have come apart. A three-character key is a whole
            # syllable and only gets the insertion probe; from four up it gets
            # the full one-edit neighbourhood; the clipped probe answers for
            # everything a speaker ran onto the end of the brand.
            for stored in index.inserted(key) if len(key) >= 3 else ():
                classes.setdefault(stored, 2)
            if len(key) >= 4:
                for stored in index.edit1(key):
                    classes.setdefault(stored, 2)
                for stored in index.clipped(key, window):
                    classes.setdefault(stored, 2)
            for stored, klass in classes.items():
                if abs(len(stored) - len(key)) > window:
                    continue
                for row in index.by_key[stored]:
                    alt = bool(rank) or bool(row.alt)
                    # An alternate or fuzzy match is judged in the folded alphabet
                    # the two sides agreed on: "bolini"/VOLINI are the same word
                    # there (1.0) while "abivays"/AVAS are not (0.6) — and only
                    # the first is what the B/V alternate was opened for.
                    folded = alt or klass == 2
                    sim = (
                        SequenceMatcher(None, shape, _shape(row.token)).ratio()
                        if folded
                        else SequenceMatcher(None, token, row.token).ratio()
                    )
                    floor = (
                        _PHON_SIM_ALT
                        if alt
                        else (_PHON_SIM_EXACT, _PHON_SIM_NEAR, _PHON_SIM_FUZZY)[klass]
                    )
                    if sim < floor:
                        continue
                    score = (_PHON_EXACT, _PHON_NEAR, _PHON_FUZZY)[klass] + _PHON_SIM * sim
                    if alt:
                        score -= _PHON_ALT
                    prev = seen.get(row.family)
                    if prev is None or score > prev[0]:
                        seen[row.family] = (score, sim)
        for family, (score, sim) in seen.items():
            breadth = _PHON_BREADTH * min(1.0, index.counts.get(family, 1) / 8.0) * sim
            total = (score + breadth) * (1.0 - _PHON_COVER + _PHON_COVER * cover)
            compact = family.replace(" ", "")
            if len(compact) <= _PHON_SHORT_MAX and len(token) >= len(compact) + 2:
                total -= _PHON_SHORT
            prev = scores.get(family)
            if prev is None or total > prev.score:
                scores[family] = _PhonHit(score=total, sim=sim, cover=cover, probe=token)
    return scores


def _skus_of(conn: sqlite3.Connection, families: list[str]) -> list[sqlite3.Row]:
    marks = ",".join("?" * len(families))
    return conn.execute(
        f"SELECT {_COLUMNS} FROM products WHERE family IN ({marks})", tuple(families)
    ).fetchall()


# ─── scoring ──────────────────────────────────────────────────────────────────


def _score(row: sqlite3.Row, q: _Query, *, spare_brand: str = "") -> float:
    """Rank one row against the query.

    ``spare_brand`` is the phonetic probe that vouched for this row's family. The
    words *inside that probe* are exempt from the miss penalty — the family score
    already paid for them, and charging again punishes exactly the family the
    phonetics recovered ("thairo norm" → THYRONORM, whose name contains neither
    spoken word). Words outside it are not exempt, which is the difference
    between "pan kriyo flat" being answered and being ignored: PAN is vouched for
    by the probe ``PAN`` and nothing else in the utterance is, so PAN still
    carries two misses while PANKREOFLAT carries none.
    """
    name_tokens: list[str] = row["name_clean"].split()
    name_set = set(name_tokens)
    strength_keys = {
        row["strength"],
        row["strength"].replace(" ", ""),
        strength_number(row["strength"]),
    } - {""}
    pack_keys = {
        row["pack_size"],
        row["pack_size"].replace(" ", ""),
        strength_number(row["pack_size"]),
    } - {""}

    score = 0.0
    if row["name_clean"] == q.text:
        score += _EXACT_NAME
    elif row["name_clean"].startswith(f"{q.text} "):
        score += _PREFIX_NAME

    explained = 0
    prev_measure = False
    for tok, measure in zip(q.tokens, q.measures, strict=True):
        if tok in name_set:
            score += _TOKEN_HIT
            explained += 1
            prev_measure = False
        elif len(tok) >= 3 and any(nt.startswith(tok) for nt in name_tokens):
            score += _TOKEN_PREFIX
            explained += 1
            prev_measure = False
        elif tok in strength_keys or measure in strength_keys:
            score += _STRENGTH_HIT
            prev_measure = True
        elif tok in pack_keys or measure in pack_keys:
            score += _PACK_HIT
            prev_measure = True
        elif tok in _UNIT_TOKENS and prev_measure:
            pass  # the unit rode along with the number that already scored
        elif spare_brand and tok in spare_brand:
            prev_measure = False  # already priced by the phonetic family score
        else:
            score += _MISS
            prev_measure = False

    # The bonus for opening on this family's first word. It is matched against
    # the first *brand-ish* word as well as the literal first token, because a
    # pharmacist opens on the brand about as often as not — "do ranitidine",
    # "mujhe telma" and "2 volini gel" all forfeited this against exactly the
    # family they named.
    head = row["family"].split()[:1]
    if head and head[0] in {*q.tokens[:1], *q.words[:1]}:
        score += _FAMILY_HEAD
    score += _EXTRA_TOKEN * max(0, len(name_tokens) - explained)
    if row["stock"] > 0:
        score += _IN_STOCK
    return score


def _variant_key(scored: tuple[float, sqlite3.Row]) -> tuple[Any, ...]:
    """Rank order: best score first, then the plain brand, then alphabetical.

    This is what *selects* — search results, and which survivors make the pill
    row when there are more than ``_MAX_VARIANTS`` of them.
    """
    score, row = scored
    return (
        -round(score, 3),
        row["variant_label"] != "",
        row["variant_label"],
        row["form"],
        _num_key(row["strength"]),
        row["strength"],
        _num_key(row["pack_size"]),
        row["code"],
    )


def _pill_key(scored: tuple[float, sqlite3.Row]) -> tuple[Any, ...]:
    """Display order for a chosen set: the plain brand first, then its lines.

    "Volini, Volini Maxx, Volini Plus" reads like a shelf; the same three sorted
    by score reads like a scoreboard. Selection already happened by score, so
    reordering here costs nothing and the row scans naturally left to right.
    """
    score, row = scored
    return (
        row["variant_label"] != "",
        row["form"],
        _num_key(row["strength"]),
        row["strength"],
        row["variant_label"],
        _num_key(row["pack_size"]),
        -round(score, 3),
        row["code"],
    )


def _num_key(text: str) -> float:
    number = strength_number(text)
    return float(number) if number else 0.0


# ─── family view ──────────────────────────────────────────────────────────────


def _forms_phrase(forms: list[str]) -> str:
    """``["EYE DROPS", "EYE OINTMENT"]`` → ``"eye drops/ointment"``."""
    out: list[str] = []
    lead = ""
    for form in forms[:3]:
        words = form.lower().split()
        if not words:
            continue
        if not out:
            lead = words[0] if len(words) > 1 else ""
            out.append(" ".join(words))
        else:
            out.append(" ".join(words[1:]) if lead and words[0] == lead else " ".join(words))
    return "/".join(p for p in out if p)


def _family_view(conn: sqlite3.Connection, family: str) -> FamilyView:
    rows = conn.execute(
        "SELECT manufacturer, form, COUNT(*) c FROM products WHERE family = ? "
        "GROUP BY manufacturer, form ORDER BY c DESC, form",
        (family,),
    ).fetchall()
    manufacturers = list(dict.fromkeys(r["manufacturer"] for r in rows if r["manufacturer"]))
    forms = list(dict.fromkeys(r["form"] for r in rows if r["form"]))
    count = sum(r["c"] for r in rows)
    bits = [
        "/".join(manufacturers[:2]),
        _forms_phrase(forms),
        f"{count} SKU{'s' if count != 1 else ''}",
    ]
    return FamilyView(
        family=family,
        manufacturers=manufacturers,
        forms=forms,
        sku_count=count,
        hint=" · ".join(b for b in bits if b),
    )


# ─── public API ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Candidates:
    rows: list[sqlite3.Row]
    stage: str  # "name" | "fts" | "phonetic" | "none"
    phonetic: dict[str, _PhonHit]  # per-family bonus for the rows that came from the net

    def hit(self, family: str) -> _PhonHit | None:
        return self.phonetic.get(family)

    def stage_of(self, family: str) -> str:
        """Which stage actually produced the winner, now that two pools can mix."""
        if self.stage != "phonetic":
            return self.stage
        return "phonetic" if family in self.phonetic else "fts"


def _gather(conn: sqlite3.Connection, q: _Query) -> _Candidates:
    """The three stages, in order — but the word index no longer gets to *end*
    the search on a partial answer.

    An exact or token-bounded-prefix name hit is decisive and still short-
    circuits. A complete word-index hit — one that accounts for every spoken
    word — is decisive too. What used to be treated as equally decisive, and is
    not, is the tail-dropped retry: "montairelsee" fails the AND, so the loop
    drops the tail, "montair" alone hits, and the phonetic net that would have
    recovered MONTAIR LC never ran at all. Worse, when the damaged brand's first
    syllable happens to prefix an *unrelated* catalog word, that word won
    outright.

    So a partial word-index answer no longer preempts the net: both pools are
    gathered and scored together, each row under the treatment its own provenance
    earns, and the winner decides which stage the answer came from.
    """
    if rows := _by_name(conn, q.text):
        return _Candidates(rows=rows, stage="name", phonetic={})
    fts_rows, complete = _fts_relaxed(conn, q)
    if fts_rows and complete:
        return _Candidates(rows=fts_rows, stage="fts", phonetic={})
    families = _phonetic_families(conn, q)
    if families:
        best = dict(sorted(families.items(), key=lambda kv: (-kv[1].score, kv[0]))[:_MAX_FAMILIES])
        rows = _skus_of(conn, list(best))
        rows += [row for row in fts_rows if row["family"] not in best]
        return _Candidates(rows=rows, stage="phonetic", phonetic=best)
    if fts_rows:
        return _Candidates(rows=fts_rows, stage="fts", phonetic={})
    return _Candidates(rows=[], stage="none", phonetic={})


def _quality(q: _Query, family: str) -> float:
    """How well the family that answered agrees with the brand that was spoken,
    in the folded alphabet of :func:`normalize.spoken_shape` — 1.0 for a brand
    heard correctly, ~0.83 for one mangled by a phone line, ~0.75 for one
    truncated to three letters, and lower still for a skeleton collision.

    This is the term the old confidence table had no way to express. Every probe
    the net was given is measured against the family, and the best one counts,
    so a brand said as two words is judged on the whole thing rather than on its
    louder half — but nothing here can *raise* a score, only decline to trust it.
    """
    compact = "".join(family.split())
    target = _shape(compact)
    if not target or not q.words:
        return 1.0
    best = 0.0
    for probe in q.brandish:
        shape = _shape(probe)
        if shape:
            best = max(best, SequenceMatcher(None, shape, target).ratio())
    return best


def _confidence(stage: str, status: str, quality: float) -> float:
    """The stage's confidence, scaled by :func:`_quality`.

    At full quality the published number is exactly the table's, so the pins that
    other code reads off it (the eval's ``CONFIDENT`` line at 0.5) are unmoved.
    Below that it falls away, and below :data:`_QUALITY_FLOOR` the caller has
    already refused to assert the status at all.
    """
    base = _CONFIDENCE[(stage, status)]
    if quality >= _QUALITY_FULL:
        return base
    reach = (quality - _QUALITY_FLOOR) / (_QUALITY_FULL - _QUALITY_FLOOR)
    return round(base * (0.6 + 0.4 * max(0.0, min(1.0, reach))), 2)


_CONFIDENCE = {
    ("name", "matched"): 0.95,
    ("fts", "matched"): 0.82,
    ("phonetic", "matched"): 0.62,
    ("name", "multi_variant"): 0.72,
    ("fts", "multi_variant"): 0.62,
    ("phonetic", "multi_variant"): 0.5,
    ("name", "multi_family"): 0.45,
    ("fts", "multi_family"): 0.4,
    ("phonetic", "multi_family"): 0.32,
}


_STATUS_RANK = {"matched": 3, "multi_variant": 2, "multi_family": 1, "not_found": 0}


def resolve(
    query: str,
    *,
    form_hint: str | None = None,
    strength_hint: str | None = None,
) -> Resolution:
    """Resolve one spoken line item against the catalog.

    ``form_hint`` ("drops", "gel") and ``strength_hint`` ("40", "50 mcg") are
    what the pharmacist said *about* the product; they narrow the survivors when
    they can, and are ignored when nothing matches them (a wrong hint must never
    turn a good hit into ``not_found``).

    Numbers spoken as words are tried both ways. The brain transliterates Hindi
    speech, so "टेल्मा फोर्टी" can arrive as either "telma 40" or "telma forty";
    the digit rewrite is a *second* attempt rather than a replacement, because
    some brands really are spelled with a number word (SEVEN SEAS), and the
    better of the two answers wins.
    """
    first = _resolve_once(query, form_hint, strength_hint)
    spoken = spoken_numbers(query)
    if spoken and spoken != search_text(query):
        second = _resolve_once(spoken, form_hint, strength_hint)
        if (_STATUS_RANK[second.status], second.confidence) > (
            _STATUS_RANK[first.status],
            first.confidence,
        ):
            return second
    return first


def _resolve_once(
    query: str,
    form_hint: str | None,
    strength_hint: str | None,
) -> Resolution:
    conn = connection()
    q = _parse_query(query)
    if not q.tokens:
        return Resolution(status="not_found")

    found = _gather(conn, q)
    if not found.rows:
        return Resolution(status="not_found")

    scored = _narrow(
        [(_row_score(row, q, found), row) for row in found.rows],
        form_hint,
        strength_hint,
    )

    best = max(score for score, _ in scored)
    survivors = sorted((it for it in scored if it[0] >= best - _BAND), key=_variant_key)

    families = list(dict.fromkeys(row["family"] for _, row in survivors))
    stage = found.stage_of(families[0])
    # A name-stage hit *is* the brand, spelled the way the catalog spells it —
    # there is nothing left for a similarity term to second-guess.
    quality = 1.0 if stage == "name" else _quality(q, families[0])
    hit = found.hit(families[0])
    # A *stem* probe ("volnijel" → VOLNI) is a word somebody said with a form
    # word peeled off it; a *gram* is two words the engine decided were one.
    # Only the second is a guess about what was meant.
    floor = _QUALITY_FUSED if hit is not None and hit.probe in q.grams else _QUALITY_FLOOR

    if len(families) == 1 and quality >= floor:
        shown = sorted(survivors[:_MAX_VARIANTS], key=_pill_key)
        variants = [_sku(row) for _, row in shown]
        if len(variants) == 1:
            return Resolution(
                status="matched",
                sku=variants[0],
                family=families[0],
                confidence=_confidence(stage, "matched", quality),
            )
        return Resolution(
            status="multi_variant",
            family=families[0],
            variants=variants,
            differing_axes=differing_axes(variants),
            confidence=_confidence(stage, "multi_variant", quality),
        )

    # Either the survivors genuinely span families, or one family survived
    # without enough of the spoken word in it to be said out loud. Both are the
    # same answer — a question — so both are built the same way.
    ranked = _ranked_families(survivors if len(families) > 1 else scored)[: _MAX_FAMILIES * 3]
    quality_of = {family: _quality(q, family) for family in ranked}
    if max(quality_of.values(), default=0.0) < _QUALITY_MIN:
        # Nothing here a pharmacist would recognise as what they said. A card of
        # five brands that all sound wrong is worse than admitting the miss.
        return Resolution(status="not_found")
    # Score picks the options; quality decides which of them gets to lead. The
    # two disagree exactly when a deep or short family outscores a better-sounding
    # thin one, and on a card of options the better-sounding one belongs first.
    ranked.sort(key=lambda family: quality_of[family] < _QUALITY_MIN)
    ranked = ranked[:_MAX_FAMILIES]
    if len(ranked) < 2:
        return Resolution(status="not_found")

    return Resolution(
        status="multi_family",
        families=[_family_view(conn, family) for family in ranked],
        confidence=_confidence(found.stage_of(ranked[0]), "multi_family", quality_of[ranked[0]]),
    )


def _row_score(row: sqlite3.Row, q: _Query, found: _Candidates) -> float:
    """One row's score under the treatment its own provenance earns.

    The two pools ``_gather`` may hand back are scored side by side: a row the
    phonetic net vouched for gets the family bonus and is spared the miss penalty
    on the brand it was recovered from, and a row the word index found on a
    partial match gets neither.
    """
    hit = found.hit(row["family"])
    if hit is None:
        return _score(row, q)
    return _score(row, q, spare_brand=hit.probe) + hit.score


def _ranked_families(scored: list[tuple[float, sqlite3.Row]]) -> list[str]:
    """Every family among these rows, best score first. Uncapped: the caller
    re-orders by quality before it cuts, so a family that sounds right must not
    have been thrown away for sounding right in sixth place."""
    per_family: dict[str, float] = {}
    for score, row in scored:
        per_family[row["family"]] = max(per_family.get(row["family"], score), score)
    return [family for family, _ in sorted(per_family.items(), key=lambda kv: (-kv[1], kv[0]))]


def _narrow(
    scored: list[tuple[float, sqlite3.Row]],
    form_hint: str | None,
    strength_hint: str | None,
) -> list[tuple[float, sqlite3.Row]]:
    """Keep only the candidates a spoken hint allows — if any survive."""
    form = canonical_form(form_hint or "")
    if form:
        kept = [it for it in scored if _form_matches(it[1]["form"], form)]
        scored = kept or scored
    strength = canonical_strength(strength_hint or "")
    if strength:
        number = strength_number(strength)
        kept = [
            it
            for it in scored
            if it[1]["strength"] == strength
            or (number and strength_number(it[1]["strength"]) == number)
        ]
        scored = kept or scored
    return scored


def _form_matches(form: str, wanted: str) -> bool:
    """A bare "drops" matches "EYE DROPS"; "eye drops" does not match "EAR DROPS"."""
    if not form:
        return False
    want = wanted.split()
    have = form.split()
    return have[-len(want) :] == want if len(want) <= len(have) else False


def differing_axes(skus: list[SkuView]) -> list[str]:
    """The axes that actually differ across these SKUs — the question to ask."""
    return [axis for axis in AXES if len({getattr(sku, axis) for sku in skus}) > 1]


def search(query: str, limit: int = 8) -> list[SkuView]:
    """Ranked SKUs for the manual search bar (no grouping, no ambiguity model)."""
    conn = connection()
    q = _parse_query(query)
    if not q.tokens:
        return []
    found = _gather(conn, q)
    if not found.rows and (spoken := spoken_numbers(query)) != q.text:
        q = _parse_query(spoken)
        found = _gather(conn, q)
    scored = [(_row_score(row, q, found), row) for row in found.rows]
    return [_sku(row) for _, row in sorted(scored, key=_variant_key)[: max(0, limit)]]


def sku_by_code(code: str) -> SkuView | None:
    """One SKU by its ``Product_Code`` — how the brain honours order history."""
    row = (
        connection()
        .execute(f"SELECT {_COLUMNS} FROM products WHERE code = ?", ((code or "").strip().upper(),))
        .fetchone()
    )
    return _sku(row) if row else None


def skus_in_family(family: str) -> list[SkuView]:
    """Every SKU of a brand root, in pill order."""
    rows = (
        connection()
        .execute(
            f"SELECT {_COLUMNS} FROM products WHERE family = ?", ((family or "").strip().upper(),)
        )
        .fetchall()
    )
    return [_sku(row) for _, row in sorted(((0.0, r) for r in rows), key=_variant_key)]
