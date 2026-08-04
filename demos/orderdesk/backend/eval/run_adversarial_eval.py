"""Adversarial phonetic eval — the honest number, through the production path.

``run_phonetic_eval.py`` reported 99.5%. That number has two holes, and this
harness exists to close both of them:

1. **In-sample tuning.** ``corpus_p1..p4`` were the corpora the alternate-key
   round of ``normalize.py`` was tuned *against*. A pass rate measured on the
   set you tuned on is a fit statistic, not a generalization statistic. The two
   red-team corpora here (``adv_corpus_r1.json`` — "hostile-pharmacist"
   phrasings; ``adv_corpus_r2.json`` — "stt-damage" decoder failures) were
   written after that tuning, against the engine's *documented* mechanisms, and
   were never tuned against.

2. **Author-friendly romanizations.** The old harness fed the corpus authors'
   own ``romanized[]`` strings to ``resolve()`` and passed a variant if *any*
   of them landed. Production has exactly one romanizer — the LLM in the brain,
   reading a Devanagari STT transcript and writing one English search string.
   A human author writing "rantac wala dedh sau de do" already knows the answer
   is RANTAC; the model does not. So here **every variant's Devanagari is sent
   to gemini-3.1-flash-lite** (the same model family the brain runs on) with a
   prompt distilled from ``brain.py``'s LANGUAGE — TOOL ARGUMENTS ARE ENGLISH,
   ALWAYS section, temperature 0, one call per variant, and *that single string*
   is what ``resolve()`` gets. Results are cached to
   ``gemini_romanizations.json`` so re-runs cost nothing.

   The romanizer is given **no order history and no pharmacy context**. Real
   production has both (the brain's PHARMACY CONTEXT block lists the store's
   usual items), which is real evidence a model uses to disambiguate a mangled
   brand. Every number here is therefore *conservative* — a lower bound.

Scoring is strict and three-way, because "didn't find it" and "found the wrong
drug" are not the same failure in a pharmacy:

  PASS    — the right family was surfaced (matched / multi_variant on the right
            family, or the right family present in a multi_family list).
  ASK_OK  — not_found, or a low-confidence multi_family that lacks the right
            family but also carries no *wrong* matched/multi_variant at >= 0.5.
            The agent would say "ये कैटलॉग में नहीं मिला" and ask again: a lost
            turn, not a lost patient. Counted separately, never as PASS.
  WRONG   — matched or multi_variant on the WRONG family at any confidence, or
            a multi_family ranking a wrong family first at >= 0.5. This is the
            dangerous class: the agent hands over a different drug and sounds
            sure. The WRONG rate is the number a pharmacy cares about.

Also here: the traps from ``adv_corpus_r1.json`` (8 *absent* brands that must
not resolve to anything confident, 12 *collision* pairs where a real catalog
brand must beat its near-twin), and a triangulation pass that runs the SAME
strict Gemini-romanized scoring over a seeded 150-variant sample of the
ORIGINAL corpus — so the in-sample/held-out gap is measured with one method on
both sides instead of being asserted.

Run:

    cd demos && set -a && source ~/apps/voqalcloud/.env && set +a && \\
        uv run python orderdesk/backend/eval/run_adversarial_eval.py

Artifacts land next to this file: ``gemini_romanizations.json`` (the cache),
``adversarial_results.json`` (every scored query) and ``adversarial_report.md``.
Nothing in the engine, the corpora, or the earlier eval files is touched.
"""

from __future__ import annotations

import json
import os
import random
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent

ADV_FILES = [HERE / "adv_corpus_r1.json", HERE / "adv_corpus_r2.json"]
ORIG_FILES = sorted(HERE.glob("corpus_p*.json"))
CACHE_PATH = HERE / "gemini_romanizations.json"
RESULTS_PATH = HERE / "adversarial_results.json"
REPORT_PATH = HERE / "adversarial_report.md"

MODEL = "gemini-3.1-flash-lite"
SAMPLE_N = 150
SAMPLE_SEED = 20260803

_PKG = "orderdesk_backend"

#: Above this, a result is "confident" — the threshold the three-way scorer and
#: the trap scorer both read. It sits exactly on ``_CONFIDENCE[("phonetic",
#: "multi_variant")]`` (0.5), the weakest result the brain still acts on.
CONFIDENT = 0.5

VERDICTS = ("PASS", "ASK_OK", "WRONG")

#: What a row carries when the Gemini column could not be measured — the free
#: tier caps ``gemini-3.1-flash-lite`` at 500 requests per project per day and a
#: cold run needs ~620. ``UNRUN`` is deliberately *not* a verdict: it never
#: enters a rate, and the report renders those cells as "pending" rather than
#: quietly borrowing the authors' number to stand in for the model's.
UNRUN = "UNRUN"


def _load_backend() -> tuple[ModuleType, ModuleType]:
    """Import ``demos/orderdesk/backend/`` in place, the way the other evals do."""
    if _PKG not in sys.modules:
        pkg = ModuleType(_PKG)
        pkg.__path__ = [str(BACKEND)]  # type: ignore[attr-defined]
        sys.modules[_PKG] = pkg
    return import_module(f"{_PKG}.search"), import_module(f"{_PKG}.normalize")


search_mod, normalize_mod = _load_backend()
resolve = search_mod.resolve


# ─── the romanizer — the production path, distilled ───────────────────────────
#
# Lifted from brain.py's _INSTRUCTION: the opening role line, the whole
# "LANGUAGE — TOOL ARGUMENTS ARE ENGLISH, ALWAYS" section including its five
# worked transliterations, and the English-only guard's consequence. What is
# deliberately NOT here: the PHARMACY CONTEXT block (order history, usual
# items). Production has it; we withhold it so the number is a floor.

ROMANIZER_SYSTEM = """You are the MedSetu order desk — a Hindi-speaking voice agent for India's largest B2B pharma distributor, taking a stock order from a pharmacist standing behind their counter. Every product they name lands as a row on their screen and is resolved against the real MedSetu catalog.

LANGUAGE — TOOL ARGUMENTS ARE ENGLISH, ALWAYS:
- The screen is English and the catalog is English. EVERY string you pass to a tool — item text, query, note — is in clean English letters. Transliterate what you heard: "वोलिनी" → "volini", "चार क्विन" → "4 quin", "थायरोनॉर्म" → "thyronorm", "पैन फोर्टी" → "pan 40", "अबीवेज़" → "abiways".
- A tool argument containing Devanagari is rejected and you will have to call again. Do not let that happen.

YOUR TASK RIGHT NOW: you are given one STT transcript of what the pharmacist just said, in Devanagari. Write the product name you would search the catalog for, in English letters only — your best reading of the brand (and the strength or form if they spoke one). Drop filler, politeness and quantity words that are not part of the product. Numbers spoken as Hindi words become digits.

Output just the search string, on one line. No quotes, no explanation, no alternatives."""

ROMANIZER_USER = "The pharmacist said (STT transcript, Devanagari): '{utterance}'"


def api_keys() -> list[str]:
    """Every key this run may spend, most-preferred first.

    The free tier meters ``gemini-3.1-flash-lite`` at **15 requests per minute
    and 500 per day, per project**. A cold run of this eval is ~620 calls, so a
    single free-tier key cannot finish it in one day — the run dies two thirds
    of the way in with ``GenerateRequestsPerDayPerProjectPerModel-FreeTier``.
    ``GEMINI_API_KEYS`` therefore accepts a comma-separated list; the romanizer
    rotates to the next key when one exhausts its *daily* bucket, and paces each
    key independently under the per-minute one. With one key set (the normal
    case, ``GEMINI_API_KEY``) the behaviour is unchanged.
    """
    joined = os.environ.get("GEMINI_API_KEYS", "")
    keys = [k.strip() for k in joined.split(",") if k.strip()]
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        value = (os.environ.get(name) or "").strip()
        if value and value not in keys:
            keys.append(value)
    return keys


class Romanizer:
    """gemini-3.1-flash-lite behind a JSON cache and a rate pacer.

    The cache is keyed on ``(model, prompt-version, utterance)`` so a prompt
    edit invalidates itself instead of silently reusing yesterday's strings. It
    is loaded once, written once at the end (plus periodically during a long
    run), and a fully warm cache makes the whole eval offline and free.
    """

    #: Bump when ``ROMANIZER_SYSTEM`` changes — it is part of the cache key.
    PROMPT_VERSION = "v1"

    #: The key is on the free tier, which meters gemini-3.1-flash-lite at 15
    #: requests per minute per project. The pacer sits just under that and the
    #: 429 handler honours the server's own ``retryDelay`` — a rate-limited run
    #: is a hole in the dataset, not a finding about the engine.
    def __init__(self, *, rpm: int = 13, cache_path: Path = CACHE_PATH) -> None:
        self.cache_path = cache_path
        self.cache: dict[str, str] = {}
        if cache_path.exists():
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            self.cache = dict(raw.get("romanizations", {}))
        self._clients: list[Any] | None = None
        self._config: Any = None
        self._exhausted: set[int] = set()  # key indices that hit the daily bucket
        self._cursor = 0
        self._gate = threading.Lock()
        self._cache_lock = threading.Lock()
        self._interval = 60.0 / max(rpm, 1)
        self._next_at: list[float] = []
        self.calls = 0
        self.hits = 0
        self.keys_used: set[int] = set()

    # cache key ---------------------------------------------------------------

    def key(self, utterance: str) -> str:
        return f"{MODEL}|{self.PROMPT_VERSION}|{utterance}"

    def cached(self, utterance: str) -> str | None:
        return self.cache.get(self.key(utterance))

    # the call ----------------------------------------------------------------

    def _lazy_clients(self) -> list[Any]:
        """Built on first live call, so importing this module needs no API key."""
        if self._clients is None:
            with self._gate:
                if self._clients is None:
                    from google import genai
                    from google.genai import types

                    keys = api_keys()
                    if not keys:
                        raise RuntimeError(
                            "no GEMINI_API_KEY — run with "
                            "`set -a; source ~/apps/voqalcloud/.env; set +a`"
                        )
                    self._config = types.GenerateContentConfig(
                        system_instruction=ROMANIZER_SYSTEM,
                        temperature=0.0,
                    )
                    self._next_at = [0.0] * len(keys)
                    self._clients = [genai.Client(api_key=k) for k in keys]
        return self._clients

    def _checkout(self) -> int:
        """The next usable key index, paced. Raises when every key is spent."""
        with self._gate:
            live = [i for i in range(len(self._clients or [])) if i not in self._exhausted]
            if not live:
                raise RuntimeError(
                    "every GEMINI key has exhausted its free-tier daily bucket "
                    f"({len(self._exhausted)} key(s), 500 requests/day/model each). "
                    "The cache holds what did land — re-run after the quota resets and "
                    "it picks up where it stopped."
                )
            index = live[self._cursor % len(live)]
            self._cursor += 1
            now = time.monotonic()
            wait = self._next_at[index] - now
            self._next_at[index] = max(self._next_at[index], now) + self._interval
            self.keys_used.add(index)
        if wait > 0:
            time.sleep(wait)
        return index

    def _retire(self, index: int) -> None:
        """Take a key out of rotation — its *daily* bucket is gone."""
        with self._gate:
            if index not in self._exhausted:
                self._exhausted.add(index)
                print(f"    key #{index + 1} exhausted its daily quota — rotating")

    @staticmethod
    def _retry_after(blob: str) -> float | None:
        """The server's own ``retryDelay`` out of a 429 body, in seconds."""
        marker = "'retryDelay': '"
        if marker not in blob:
            return None
        tail = blob.split(marker, 1)[1].split("'", 1)[0]
        try:
            return float(tail.rstrip("s"))
        except ValueError:  # pragma: no cover — an unexpected shape
            return None

    def romanize(self, utterance: str, attempts: int = 9) -> str:
        """One English search string for one Devanagari utterance."""
        hit = self.cached(utterance)
        if hit is not None:
            self.hits += 1
            return hit
        clients = self._lazy_clients()
        delay = 4.0
        last: Exception | None = None
        for attempt in range(attempts):
            index = self._checkout()
            try:
                self.calls += 1
                resp = clients[index].models.generate_content(
                    model=MODEL,
                    contents=ROMANIZER_USER.format(utterance=utterance),
                    config=self._config,
                )
                text = clean_romanization(resp.text or "")
                if not text:
                    raise RuntimeError(f"empty romanization for {utterance!r}")
                with self._cache_lock:
                    self.cache[self.key(utterance)] = text
                return text
            except Exception as exc:
                last = exc
                blob = f"{type(exc).__name__}: {exc}"
                # A *daily* 429 will never clear inside this run, so waiting on
                # it is dead time: retire the key and go straight to the next.
                if "PerDayPerProject" in blob:
                    self._retire(index)
                    continue
                retriable = any(
                    m in blob
                    for m in (
                        "429",
                        "500",
                        "502",
                        "503",
                        "504",
                        "RESOURCE_EXHAUSTED",
                        "UNAVAILABLE",
                        "INTERNAL",
                        "DEADLINE",
                        "timeout",
                        "Timeout",
                        "empty romanization",
                    )
                )
                if not retriable or attempt == attempts - 1:
                    break
                time.sleep((self._retry_after(blob) or delay) + random.random())
                delay = min(delay * 2, 60.0)
        raise RuntimeError(f"romanization failed after {attempts} attempts: {last}")

    def romanize_many(self, utterances: list[str], workers: int = 3) -> dict[str, str]:
        """Every utterance romanized, cache-first, modest concurrency.

        The cache is flushed every 25 completions: at 13 rpm a full cold run is
        the better part of an hour, and a crash 40 minutes in must not throw
        away 40 minutes of calls."""
        todo = [u for u in dict.fromkeys(utterances) if self.cached(u) is None]
        if todo:
            print(f"  gemini: {len(todo)} live calls ({len(utterances) - len(todo)} cached)")
            done = 0
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for _ in pool.map(self.romanize, todo):
                    done += 1
                    if done % 25 == 0:
                        print(f"    {done}/{len(todo)}", flush=True)
                        self.save()
            self.save()
        return {u: self.romanize(u) for u in dict.fromkeys(utterances)}

    def save(self) -> None:
        with self._cache_lock:
            payload = {
                "meta": {
                    "model": MODEL,
                    "prompt_version": self.PROMPT_VERSION,
                    "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "count": len(self.cache),
                },
                "romanizations": self.cache,
            }
        self.cache_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def clean_romanization(text: str) -> str:
    """The model's raw output → the string a tool call would carry.

    One line, no surrounding quotes, no trailing period — the same tidying the
    brain's argument coercion would do before ``resolve()`` ever sees it.
    """
    lines = (text or "").strip().splitlines()
    out = lines[0].strip() if lines else ""
    # Peel quotes and sentence punctuation until it stops changing — a model
    # that writes ``` `pan 40`. ``` has wrapped the answer in both.
    while True:
        peeled = out.strip().strip("\"'`“”‘’").strip(".,;:").strip()
        if peeled == out:
            return out
        out = peeled


def has_devanagari(text: str) -> bool:
    """True if the model leaked script the brain's English guard would reject."""
    return any("ऀ" <= ch <= "ॿ" for ch in text)


# ─── the strict three-way scorer ──────────────────────────────────────────────


def summarize(res: Any) -> dict[str, Any]:
    """A compact, JSON-safe picture of one ``Resolution``."""
    out: dict[str, Any] = {"status": res.status, "confidence": res.confidence}
    if res.status == "matched" and res.sku is not None:
        out["family"] = res.sku.family
        out["sku_code"] = res.sku.code
        out["sku_name"] = res.sku.name
    elif res.status == "multi_variant":
        out["family"] = res.family
        out["variant_codes"] = [v.code for v in res.variants][:8]
    elif res.status == "multi_family":
        out["families"] = [f.family for f in res.families]
    return out


def score_strict(res: Any, family: str) -> tuple[str, str, dict[str, Any]]:
    """``(verdict, reason, returned)`` for one resolution against one family.

    The whole eval's headline arithmetic lives in these fifteen lines, so the
    offline tests in ``demos/tests/test_orderdesk_adversarial.py`` drive it
    directly with hand-built resolutions — no API, no database.
    """
    returned = summarize(res)
    status = res.status

    if status in ("matched", "multi_variant"):
        got = returned.get("family")
        if got == family:
            return "PASS", f"{status} on the right family", returned
        return "WRONG", f"{status} on {got} (wanted {family})", returned

    if status == "multi_family":
        families = returned.get("families", [])
        if family in families:
            return "PASS", f"multi_family lists {family} at #{families.index(family) + 1}", returned
        if res.confidence >= CONFIDENT and families:
            return "WRONG", f"multi_family ranks {families[0]} first at {res.confidence}", returned
        return "ASK_OK", f"multi_family without {family} at {res.confidence}", returned

    return "ASK_OK", "not_found", returned


# ─── running a corpus ─────────────────────────────────────────────────────────


@dataclass
class VariantResult:
    corpus: str
    lens: str
    sku_code: str
    name: str
    family: str
    attack: str
    devanagari: str
    gemini: str
    gemini_verdict: str
    gemini_reason: str
    gemini_returned: dict[str, Any]
    author_romanized: list[str] = field(default_factory=list)
    author_verdict: str = ""
    author_reason: str = ""
    author_returned: dict[str, Any] = field(default_factory=dict)
    why: str = ""
    devanagari_leak: bool = False


_VERDICT_RANK = {"PASS": 0, "ASK_OK": 1, "WRONG": 2}


def best_author_verdict(family: str, romanized: list[str]) -> tuple[str, str, dict[str, Any]]:
    """The authors' romanizations, best-of — the *secondary* (old-method-ish)
    number. Best-of is generous on purpose: it is the charitable reading of the
    old harness, so the gap it leaves against the Gemini column is the honest
    size of the "author knew the answer" effect."""
    best: tuple[str, str, dict[str, Any]] | None = None
    for query in romanized:
        verdict, reason, returned = score_strict(resolve(query), family)
        cand = (verdict, f"`{query}` → {reason}", returned)
        if best is None or _VERDICT_RANK[verdict] < _VERDICT_RANK[best[0]]:
            best = cand
        if verdict == "PASS":
            break
    return best or ("ASK_OK", "no romanizations", {})


def run_corpus(
    corpus: dict[str, Any], source: str, romanizer: Romanizer | None, *, with_authors: bool = True
) -> list[VariantResult]:
    """Every variant of one corpus, scored. ``romanizer=None`` runs the whole
    thing offline: the authors'-strings column is still measured in full and the
    Gemini column is left ``UNRUN`` rather than substituted."""
    lens = corpus.get("lens") or corpus.get("bucket") or source
    utterances = [v["devanagari"] for e in corpus["entries"] for v in e["variants"]]
    strings = romanizer.romanize_many(utterances) if romanizer else {}

    out: list[VariantResult] = []
    for entry in corpus["entries"]:
        for variant in entry["variants"]:
            dev = variant["devanagari"]
            gem = strings.get(dev, "")
            if gem:
                verdict, reason, returned = score_strict(resolve(gem), entry["family"])
            else:
                verdict, reason, returned = UNRUN, "gemini column not run", {}
            row = VariantResult(
                corpus=source,
                lens=lens,
                sku_code=entry["sku_code"],
                name=entry["name"],
                family=entry["family"],
                attack=variant.get("attack", "(none)"),
                devanagari=dev,
                gemini=gem,
                gemini_verdict=verdict,
                gemini_reason=reason,
                gemini_returned=returned,
                why=variant.get("why", ""),
                devanagari_leak=has_devanagari(gem),
            )
            if with_authors and variant.get("romanized"):
                av, ar, aret = best_author_verdict(entry["family"], variant["romanized"])
                row.author_romanized = list(variant["romanized"])
                row.author_verdict, row.author_reason, row.author_returned = av, ar, aret
            out.append(row)
    return out


# ─── traps ────────────────────────────────────────────────────────────────────


@dataclass
class TrapResult:
    kind: str
    query_devanagari: str
    gemini: str
    target_family: str | None
    must_not_win: str | None
    verdict: str  # "PASS" | "FAIL"
    severity: str  # "none" | "low" | "medium" | "high" | "critical"
    detail: str
    returned: dict[str, Any]
    note: str = ""
    romanizer: str = "gemini"  # "gemini" | "authors-first"


def _severity(confidence: float) -> str:
    if confidence >= 0.8:
        return "critical"
    if confidence >= 0.6:
        return "high"
    if confidence >= CONFIDENT:
        return "medium"
    return "low"


def score_trap(trap: dict[str, Any], gemini: str, res: Any) -> TrapResult:
    """Absent brands must not resolve confidently; collisions must not lose."""
    returned = summarize(res)
    base: dict[str, Any] = {
        "kind": trap["kind"],
        "query_devanagari": trap["query_devanagari"],
        "gemini": gemini,
        "target_family": trap.get("target_family"),
        "must_not_win": trap.get("must_not_win"),
        "returned": returned,
        "note": trap.get("note", ""),
    }

    if trap["kind"] == "absent":
        if res.status in ("matched", "multi_variant") and res.confidence >= CONFIDENT:
            got = returned.get("family")
            hit_the_named_twin = bool(trap.get("must_not_win")) and got == trap["must_not_win"]
            sev = _severity(res.confidence)
            if hit_the_named_twin and sev == "medium":
                sev = "high"  # the red team predicted this exact wrong brand
            return TrapResult(
                verdict="FAIL",
                severity=sev,
                detail=f"{res.status} on {got} at {res.confidence} for an absent brand",
                **base,
            )
        return TrapResult(
            verdict="PASS",
            severity="none",
            detail=f"{res.status} at {res.confidence} — nothing confident",
            **base,
        )

    # collision: the target must surface, and the twin must not outrank it
    target = trap["target_family"]
    twin = trap.get("must_not_win")
    if res.status in ("matched", "multi_variant"):
        got = returned.get("family")
        if got == target:
            return TrapResult(
                verdict="PASS", severity="none", detail=f"{res.status} on {target}", **base
            )
        sev = "critical" if got == twin else _severity(res.confidence)
        return TrapResult(
            verdict="FAIL",
            severity=sev,
            detail=f"{res.status} on {got} at {res.confidence} (wanted {target})",
            **base,
        )
    if res.status == "multi_family":
        families = returned.get("families", [])
        if target not in families:
            return TrapResult(
                verdict="FAIL",
                severity="high" if twin and twin in families else "medium",
                detail=f"multi_family {families} — {target} absent",
                **base,
            )
        ti = families.index(target)
        if twin and twin in families and families.index(twin) < ti:
            return TrapResult(
                verdict="FAIL",
                severity="high",
                detail=f"multi_family ranks {twin} (#{families.index(twin) + 1}) above "
                f"{target} (#{ti + 1})",
                **base,
            )
        return TrapResult(
            verdict="PASS",
            severity="none",
            detail=f"multi_family lists {target} at #{ti + 1}",
            **base,
        )
    return TrapResult(
        verdict="FAIL", severity="medium", detail=f"not_found — {target} never surfaced", **base
    )


def run_traps(traps: list[dict[str, Any]], romanizer: Romanizer | None) -> list[TrapResult]:
    """Traps, Gemini-romanized. Offline, the *first* author romanization stands
    in — traps are 20 hand-written probes whose whole point is what the catalog
    does with a plausible reading, and a single fixed reading is still one
    honest reading. ``TrapResult.romanizer`` records which it was."""
    strings = romanizer.romanize_many([t["query_devanagari"] for t in traps]) if romanizer else {}
    out: list[TrapResult] = []
    for trap in traps:
        query = strings.get(trap["query_devanagari"]) or trap["romanized"][0]
        result = score_trap(trap, query, resolve(query))
        result.romanizer = "gemini" if strings else "authors-first"
        out.append(result)
    return out


# ─── triangulation: the original corpus, both methods ─────────────────────────


def original_variants() -> list[dict[str, Any]]:
    """Every ``corpus_p*.json`` variant, flattened with its entry's identity."""
    out: list[dict[str, Any]] = []
    for path in ORIG_FILES:
        data = json.loads(path.read_text(encoding="utf-8"))
        for entry in data["entries"]:
            for variant in entry["variants"]:
                out.append(
                    {
                        "corpus": path.name,
                        "bucket": data.get("bucket", path.stem),
                        "sku_code": entry["sku_code"],
                        "name": entry["name"],
                        "family": entry["family"],
                        "devanagari": variant["devanagari"],
                        "romanized": list(variant["romanized"]),
                    }
                )
    return out


def old_tier_pass(res: Any, family: str, sku_code: str) -> bool:
    """The old harness's T1+T2 rule, reproduced from ``run_phonetic_eval.score_query``
    so the headline A row is the *actual* 99.5% number and not a restatement of my
    stricter one. Note the final clause: the old rule scored a pass whenever the
    expected SKU appeared anywhere in the returned variant list — including inside a
    confident ``multi_variant`` on a **different** family. That one clause is the
    whole A-vs-A″ gap below."""
    if (
        res.status == "matched"
        and res.sku is not None
        and (res.sku.code == sku_code or res.sku.family == family)
    ):
        return True
    if res.status == "multi_variant" and res.family == family:
        return True
    if res.status == "multi_family" and family in {f.family for f in res.families}:
        return True
    return bool(sku_code) and sku_code in {v.code for v in res.variants}


def old_method_rate(variants: list[dict[str, Any]]) -> dict[str, Any]:
    """The 99.5%-style number — pass if ANY author romanization clears the old
    T1/T2 bar — alongside the same best-of-romanizations run re-scored under the
    strict 3-way rule, so the report can show what the scoring change alone costs
    before any romanizer or corpus changes hands."""
    passed = strict = 0
    for v in variants:
        hit = tight = False
        for query in v["romanized"]:
            res = resolve(query)
            hit = hit or old_tier_pass(res, v["family"], v.get("sku_code", ""))
            tight = tight or score_strict(res, v["family"])[0] == "PASS"
        passed += hit
        strict += tight
    total = len(variants)
    return {
        "total": total,
        "pass": passed,
        "pass_rate": _rate(passed, total),
        "strict_pass": strict,
        "strict_pass_rate": _rate(strict, total),
    }


def _rate(n: int, total: int) -> float:
    return round(n / total, 4) if total else 0.0


def run_original_sample(romanizer: Romanizer | None) -> dict[str, Any]:
    """The apples-to-apples middle column: the SAME strict Gemini-romanized
    scoring on a seeded 150-variant sample of the corpus the engine was tuned
    on. Same method on both sides, so the difference is the generalization gap
    and not a difference in how the two sides were measured."""
    everything = original_variants()
    rng = random.Random(SAMPLE_SEED)
    sample = rng.sample(everything, min(SAMPLE_N, len(everything)))
    strings = romanizer.romanize_many([v["devanagari"] for v in sample]) if romanizer else {}

    rows: list[dict[str, Any]] = []
    for v in sample:
        gem = strings.get(v["devanagari"], "")
        if gem:
            verdict, reason, returned = score_strict(resolve(gem), v["family"])
        else:
            verdict, reason, returned = UNRUN, "gemini column not run", {}
        rows.append(
            {
                "bucket": v["bucket"],
                "family": v["family"],
                "sku_code": v["sku_code"],
                "devanagari": v["devanagari"],
                "gemini": gem,
                "verdict": verdict,
                "reason": reason,
                "returned": returned,
            }
        )
    return {
        "seed": SAMPLE_SEED,
        "n": len(sample),
        "counts": _counts([r["verdict"] for r in rows if r["verdict"] != UNRUN]),
        "old_method_same_sample": old_method_rate(sample),
        "old_method_full_corpus": old_method_rate(everything),
        "rows": rows,
    }


# ─── aggregation ──────────────────────────────────────────────────────────────


def _counts(verdicts: list[str]) -> dict[str, Any]:
    c = Counter(verdicts)
    total = len(verdicts)
    return {
        "total": total,
        **{v: c.get(v, 0) for v in VERDICTS},
        "pass_rate": _rate(c.get("PASS", 0), total),
        "ask_ok_rate": _rate(c.get("ASK_OK", 0), total),
        "wrong_rate": _rate(c.get("WRONG", 0), total),
    }


def aggregate(rows: list[VariantResult]) -> dict[str, Any]:
    per_corpus: dict[str, Any] = {}
    for corpus in sorted({r.corpus for r in rows}):
        sub = [r for r in rows if r.corpus == corpus]
        per_corpus[corpus] = {
            "lens": sub[0].lens,
            "gemini": _counts([r.gemini_verdict for r in sub if r.gemini_verdict != UNRUN]),
            "author": _counts([r.author_verdict for r in sub if r.author_verdict]),
        }
    per_attack: dict[str, Any] = {}
    for attack in sorted({r.attack for r in rows}):
        sub = [r for r in rows if r.attack == attack]
        per_attack[attack] = {
            "corpora": sorted({r.corpus for r in sub}),
            "gemini": _counts([r.gemini_verdict for r in sub if r.gemini_verdict != UNRUN]),
            "author": _counts([r.author_verdict for r in sub if r.author_verdict]),
        }
    return {
        "overall": {
            "gemini": _counts([r.gemini_verdict for r in rows if r.gemini_verdict != UNRUN]),
            "author": _counts([r.author_verdict for r in rows if r.author_verdict]),
        },
        "per_corpus": per_corpus,
        "per_attack": per_attack,
    }


def worst_confident_wrong(
    rows: list[VariantResult], limit: int = 10, column: str = "gemini"
) -> list[VariantResult]:
    """WRONG results ordered by how sure the engine sounded — matched beats
    multi_variant at equal confidence, because matched is what locks a row
    green with no question asked. ``column`` selects which romanizer's results
    to rank, so the offline run still gets a worst-offenders table."""
    verdict = f"{column}_verdict"
    payload = f"{column}_returned"
    wrongs = [r for r in rows if getattr(r, verdict) == "WRONG"]
    return sorted(
        wrongs,
        key=lambda r: (
            -float(getattr(r, payload).get("confidence", 0.0)),
            0 if getattr(r, payload).get("status") == "matched" else 1,
            r.family,
        ),
    )[:limit]


# ─── results.json ─────────────────────────────────────────────────────────────


def write_results(
    rows: list[VariantResult],
    traps: list[TrapResult],
    agg: dict[str, Any],
    triangulation: dict[str, Any],
    path: Path,
    *,
    wall_seconds: float,
    romanizer: Romanizer | None,
) -> Path:
    trap_counts = Counter(t.verdict for t in traps)
    data = {
        "meta": {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "model": MODEL,
            "prompt_version": Romanizer.PROMPT_VERSION,
            "corpora": [p.name for p in ADV_FILES],
            "variants": len(rows),
            "traps": len(traps),
            "gemini_calls_this_run": romanizer.calls if romanizer else 0,
            "cache_hits": romanizer.hits if romanizer else 0,
            "api_keys_rotated": len(romanizer.keys_used) if romanizer else 0,
            "wall_seconds": round(wall_seconds, 1),
            "no_order_history": True,
            "gemini_column_run": agg["overall"]["gemini"]["total"] > 0,
        },
        "aggregate": agg,
        "traps": {
            "counts": {"PASS": trap_counts.get("PASS", 0), "FAIL": trap_counts.get("FAIL", 0)},
            "by_severity": dict(Counter(t.severity for t in traps if t.verdict == "FAIL")),
            "rows": [asdict(t) for t in traps],
        },
        "triangulation": {
            "original_corpus_any_romanization_full": triangulation["old_method_full_corpus"],
            "original_corpus_any_romanization_sample": triangulation["old_method_same_sample"],
            "original_corpus_gemini_strict_sample": {
                "seed": triangulation["seed"],
                "n": triangulation["n"],
                **triangulation["counts"],
            },
            "adversarial_gemini_strict": agg["overall"]["gemini"],
            "adversarial_author_strict": agg["overall"]["author"],
        },
        "original_sample_rows": triangulation["rows"],
        "variants": [asdict(r) for r in rows],
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# ─── report ───────────────────────────────────────────────────────────────────

#: The fix list, written against the mechanisms the two red-team reports named.
#: ``frequency`` is filled in at report time from the attack classes each item
#: is responsible for, so the ordering is evidence-driven rather than a hunch.
FIXES: list[dict[str, Any]] = [
    {
        "id": "isalpha-gate",
        "title": "`_parse_query`'s `tok.isalpha()` gate drops every digit-fused brand token",
        "where": "search.py `_parse_query` (the `brandish` filter)",
        "detail": (
            "`brandish` keeps only tokens where `len(tok) >= 3 and tok.isalpha()`. A "
            "brand the STT fused with its strength — `montair10`, `pan40`, `telma40` — "
            "fails `isalpha()` and never reaches the phonetic stage at all, so the "
            "misheard-brand net that the whole design leans on is simply not run. Fix: "
            "split a trailing/leading digit run off the token and probe the alpha stem "
            "(the digits are already carried by `measures`)."
        ),
        "attacks": ["brand-digit-fusion", "2-boundary-destruction", "strength-misattached"],
        "severity": 3,
    },
    {
        "id": "fts-short-circuit",
        "title": "Leading-token FTS short-circuit hands the query to the wrong brand before phonetics runs",
        "where": "search.py `_gather` / `_fts_relaxed` (the `words[:cut]` tail-drop loop)",
        "detail": (
            "`_gather` stops at the first stage that returns rows, and `_fts_relaxed` "
            "keeps cutting the query down until *something* matches — including down to "
            "the first word alone. A damaged brand whose first three letters happen to "
            "prefix an unrelated catalog token wins on that prefix, the phonetic stage "
            "never runs, and the result is a confident `matched`/`multi_variant` "
            "(0.82/0.62) on a brand that was never said. This is the single biggest "
            "manufacturer of WRONG (as opposed to ASK_OK) results. Fix: require the "
            "surviving cut to explain a real share of the query, and merge the FTS and "
            "phonetic candidate pools rather than short-circuiting."
        ),
        "attacks": [
            "1-real-word-capture",
            "3-truncation",
            "hindi-word-substitution",
            "2-boundary-destruction",
            "wrong-boundary-split",
        ],
        "severity": 3,
    },
    {
        "id": "hindi-unfolding",
        "title": "Hindi numerals and spoken suffixes are never unfolded",
        "where": "normalize.py `spoken_numbers` (English number words only)",
        "detail": (
            "`spoken_numbers` knows `forty`→40 but not `chalis`, `dedh sau`, `sawa`, "
            "`dhai`, `pachees`. A Hindi-spoken strength therefore survives as an "
            "unexplainable word token and is charged `_MISS` (-6) against the very SKU "
            "it identifies, while `_STRENGTH_HIT` (+12) is never paid. Fix: a Hindi "
            "numeral table (including the fractional forms सवा/डेढ़/ढाई) folded in "
            "`spoken_numbers`, which `resolve()` already tries as a second pass."
        ),
        "attacks": ["fused-filler-tail", "strength-misattached", "dialect-vowel-damage"],
        "severity": 2,
    },
    {
        "id": "key-window",
        "title": "The ±1 key-length window is too tight for syllable loss and too loose for short keys",
        "where": "search.py `_phonetic_families` (`abs(len(row['key']) - len(key)) > 1`)",
        "detail": (
            "A dropped nasal or an elided medial syllable moves the phonetic key by two "
            "characters (`MNTR`→`MTR`→`MT`), which the window rejects outright — the "
            "right family is never even scored. Meanwhile a 2-character key inside the "
            "window reaches half the catalog. Fix: make the window proportional to key "
            "length, and gate short keys on the spelling-similarity floor instead of on "
            "length alone."
        ),
        "attacks": ["dropped-syllable-nasal", "3-truncation", "4-matra-error"],
        "severity": 2,
    },
    {
        "id": "form-word-pollution",
        "title": "Hindi form words pollute the query and `_FAMILY_HEAD` is forfeited",
        "where": "normalize.py `FORM_WORDS` + search.py `_score`'s `_FAMILY_HEAD`",
        "detail": (
            "`FORM_WORDS` is an English list: `goli`, `tikiya`, `shishi`, `manjan`, "
            "`sheeshi`, `dawa` are not in it, so they stay in `q.tokens`, each costs "
            "`_MISS`, and — worse — when the Hindi word lands *first* "
            "(`goli wala rantac`) the `_FAMILY_HEAD` +8 that separates the right family "
            "from its neighbours is forfeited because `q.tokens[:1]` no longer holds the "
            "brand. Fix: extend `FORM_WORDS` with the Hindi/romanized form and filler "
            "vocabulary, and test `_FAMILY_HEAD` against any leading *brandish* token "
            "rather than token 0."
        ),
        "attacks": ["hindi-form-word-only", "hindi-word-substitution", "fused-filler-tail"],
        "severity": 2,
    },
    {
        "id": "short-attractors",
        "title": "Short, deep families act as attractors under `_PHON_BREADTH`",
        "where": "search.py `_phonetic_families` (`_PHON_BREADTH * min(1, count/8)`)",
        "detail": (
            "Breadth pays up to +12 for a family with eight or more SKUs, independent of "
            "how well the token actually matched. A short-keyed deep brand therefore "
            "outranks a long-keyed exact-ish one, which is the mechanism behind the "
            "absent-brand traps landing on real catalog brands. Fix: scale breadth by "
            "the similarity that earned the candidacy (`_PHON_SIM * sim` already "
            "computed) instead of adding it flat."
        ),
        "attacks": ["bv-fold-collision", "1-real-word-capture", "dialect-vowel-damage"],
        "severity": 2,
    },
    {
        "id": "confidence-discipline",
        "title": "Confidence is a per-stage constant — no coverage or length discipline",
        "where": "search.py `_CONFIDENCE` (a 9-cell lookup on `(stage, status)`)",
        "detail": (
            "Every `fts`+`matched` result is 0.82 whether the query explained the whole "
            "name or one three-letter prefix of it; every `phonetic`+`matched` is 0.62 "
            "whether the spelling similarity was 0.95 or the 0.45 floor. The engine "
            "cannot express doubt, so the brain cannot ask instead of guessing — this "
            "is what converts near-misses into WRONG instead of ASK_OK. Fix: multiply "
            "the stage constant by a coverage term (explained tokens / query tokens) and "
            "by the realized phonetic similarity, and let the brain's ask-again path "
            "trigger below a threshold."
        ),
        "attacks": ["5-confidence-collapse", "1-real-word-capture", "hindi-word-substitution"],
        "severity": 3,
    },
]


def _fix_priority(agg: dict[str, Any], column: str = "gemini") -> list[dict[str, Any]]:
    """Order the fix list by severity × the WRONG+ASK_OK volume it owns."""
    per_attack = agg["per_attack"]
    out = []
    for fix in FIXES:
        bad = 0
        wrong = 0
        seen = []
        for attack in fix["attacks"]:
            stats = per_attack.get(attack, {}).get(column)
            if not stats or not stats.get("total"):
                continue
            seen.append(attack)
            wrong += stats["WRONG"]
            bad += stats["WRONG"] + stats["ASK_OK"]
        out.append(
            {
                **fix,
                "attacks_seen": seen,
                "bad": bad,
                "wrong": wrong,
                "score": fix["severity"] * (2 * wrong + bad),
            }
        )
    return sorted(out, key=lambda f: (-f["score"], f["id"]))


def _pct(x: float) -> str:
    return f"{x:.1%}"


def write_report(
    rows: list[VariantResult],
    traps: list[TrapResult],
    agg: dict[str, Any],
    tri: dict[str, Any],
    path: Path,
    *,
    wall_seconds: float,
) -> Path:
    lines: list[str] = []
    a = lines.append
    ov = agg["overall"]["gemini"]
    ova = agg["overall"]["author"]
    gemini_ran = ov["total"] > 0

    a("# Adversarial phonetic eval — orderdesk catalog")
    a("")
    a(
        f"{len(rows)} held-out variants · {len(traps)} traps · {SAMPLE_N}-variant "
        f"in-sample control · "
        + (
            f"romanized by `{MODEL}` at temperature 0"
            if gemini_ran
            else "**Gemini column PENDING** (see the banner below)"
        )
        + f" · {wall_seconds:.0f}s"
    )
    a("")
    if not gemini_ran:
        a(
            "> ## ⚠ PARTIAL RUN — the production-path column is not measured yet\n"
            "> \n"
            f"> The romanizer column needs ~620 calls to `{MODEL}`. Google's free tier "
            "meters that model at **500 requests per project per day**, and this "
            "project's daily bucket was already spent when the run started — the two "
            "other keys on this machine are IP-restricted and Vertex AI is not enabled "
            "on `voqal-cloud-dev`, so there was no second bucket to rotate into.\n"
            "> \n"
            "> **What IS measured below, and is real:** the strict three-way scoring on "
            "both held-out adversarial corpora using the corpus authors' own "
            "`romanized[]` strings, the traps, and the old-method number on the original "
            "corpus. That is the *generalization* half of the honesty story — held-out "
            "vs in-sample — with the *romanization* half still outstanding.\n"
            "> \n"
            "> **What is NOT measured:** anything that needs the LLM to write the search "
            "string. Those cells say `pending`, never a borrowed number. Because the "
            "authors' strings are best-of-two and written by someone who already knew "
            "the answer, every figure below is an **upper bound** on what the Gemini "
            "column will show — the opposite direction of error from the usual caveat, "
            "and the reason the missing column matters.\n"
            "> \n"
            "> **To finish it** (the romanization cache makes it resumable — it already "
            "holds what landed):\n"
            "> \n"
            "> ```\n"
            "> cd demos && set -a && source ~/apps/voqalcloud/.env && set +a && \\\n"
            ">     uv run python orderdesk/backend/eval/run_adversarial_eval.py\n"
            "> ```\n"
            "> \n"
            "> Quota resets at midnight US-Pacific. `GEMINI_API_KEYS` accepts a "
            "comma-separated list if more than one project's key is available."
        )
        a("")
    a("## What this measures that the 99.5% didn't")
    a("")
    a(
        "The earlier `phonetic_report.md` number is a **fit** statistic with two holes. "
        "This run closes both."
    )
    a("")
    a(
        "1. **In-sample tuning.** `corpus_p1..p4` are the corpora `normalize.py`'s "
        "alternate-key round was tuned against. `adv_corpus_r1` (hostile-pharmacist "
        "phrasings) and `adv_corpus_r2` (STT decoder damage) were written afterwards, "
        "against the engine's documented mechanisms, and never tuned against."
    )
    a(
        "2. **Author-friendly romanizations.** The old harness fed the corpus authors' "
        "own `romanized[]` strings to `resolve()` and passed a variant if *any* of them "
        "landed. Production has one romanizer: the LLM, reading a Devanagari transcript "
        "and writing one English search string. Here every variant's Devanagari goes to "
        f"`{MODEL}` with a prompt distilled from `brain.py`'s "
        "*LANGUAGE — TOOL ARGUMENTS ARE ENGLISH, ALWAYS* section, and that **single** "
        "string is what `resolve()` sees."
    )
    a("")
    a(
        "> **These numbers are a floor.** The romanizer here gets no PHARMACY CONTEXT — "
        "no order history, no usual items. Production gives the model both, and a model "
        "that already knows this store buys MONTAIR every month reads `मोंटियर` "
        "differently. Read every figure below as a conservative lower bound on the "
        "deployed system."
    )
    a("")
    a("### Verdicts")
    a("")
    a("| verdict | meaning | what the pharmacist experiences |")
    a("| --- | --- | --- |")
    a(
        "| **PASS** | the right family surfaced (matched / multi_variant on it, or it "
        "is in the multi_family list) | the row locks, or one short question locks it |"
    )
    a(
        "| **ASK_OK** | `not_found`, or a low-confidence `multi_family` without the "
        "right family and **no** wrong match ≥ 0.5 | the agent says it didn't find it "
        "and asks again — one lost turn |"
    )
    a(
        "| **WRONG** | matched / multi_variant on the **wrong family** at any "
        "confidence, or multi_family ranking a wrong family first at ≥ 0.5 | a "
        "different drug lands on the order, and the agent sounds sure |"
    )
    a("")
    a("ASK_OK is never counted as a pass. WRONG is the number a pharmacy cares about.")
    a("")

    # ── triangulation ──────────────────────────────────────────────────────
    a("## 1. The triangulation")
    a("")
    full = tri["old_method_full_corpus"]
    same = tri["old_method_same_sample"]
    gem_s = tri["counts"]
    a("| measurement | corpus | romanizer | scoring | n | PASS | ASK_OK | WRONG |")
    a("| --- | --- | --- | --- | --- | --- | --- | --- |")
    a(
        f"| **A. the old 99.5% method** | original p1–p4 (tuned on) | authors' "
        f"`romanized[]`, best-of | family surfaced | {full['total']} | "
        f"**{_pct(full['pass_rate'])}** | – | – |"
    )
    a(
        f"| A′. same method, same sample | original p1–p4 sample | authors' "
        f"`romanized[]`, best-of | old T1/T2 | {same['total']} | "
        f"**{_pct(same['pass_rate'])}** | – | – |"
    )
    a(
        f"| A″. same corpus, strict scoring | original p1–p4 (tuned on) | authors' "
        f"`romanized[]`, best-of | strict 3-way | {full['total']} | "
        f"**{_pct(full['strict_pass_rate'])}** | – | – |"
    )
    pend = "*pending*"
    a(
        f"| **B. in-sample, production path** | original p1–p4 sample (seed "
        f"{tri['seed']}) | Gemini, one string | strict 3-way | {SAMPLE_N} | "
        + (
            f"**{_pct(gem_s['pass_rate'])}** | {_pct(gem_s['ask_ok_rate'])} | "
            f"**{_pct(gem_s['wrong_rate'])}** |"
            if gemini_ran
            else f"{pend} | {pend} | {pend} |"
        )
    )
    a(
        f"| **C. held-out, production path** | adversarial r1+r2 | Gemini, one string | "
        f"strict 3-way | {len(rows)} | "
        + (
            f"**{_pct(ov['pass_rate'])}** | {_pct(ov['ask_ok_rate'])} | "
            f"**{_pct(ov['wrong_rate'])}** |"
            if gemini_ran
            else f"{pend} | {pend} | {pend} |"
        )
    )
    a(
        f"| C′. held-out, authors' strings | adversarial r1+r2 | authors' "
        f"`romanized[]`, best-of | strict 3-way | {ova['total']} | "
        f"**{_pct(ova['pass_rate'])}** | {_pct(ova['ask_ok_rate'])} | "
        f"**{_pct(ova['wrong_rate'])}** |"
    )
    a("")
    if gemini_ran:
        a("Reading the three gaps:")
        a("")
        a(
            f"- **A″ → B ({_pct(same['strict_pass_rate'])} → {_pct(gem_s['pass_rate'])}) "
            "is the romanization gap** — same corpus, same engine, same strict scoring; "
            "the only change is who writes the search string. One LLM reading of a "
            "transcript, versus best-of two human-authored spellings written by someone "
            "who already knew the answer. (A → A″ is the *scoring* gap, held separate on "
            "purpose so the two are never confused for one another.)"
        )
        a(
            f"- **B → C ({_pct(gem_s['pass_rate'])} → {_pct(ov['pass_rate'])}) is the "
            "generalization gap** — same method on both sides, the only change is that "
            "the held-out corpus was not tuned against."
        )
        a(
            f"- **C′ → C ({_pct(ova['pass_rate'])} → {_pct(ov['pass_rate'])})** "
            "re-measures the romanization gap on the adversarial corpus, which is the "
            "more honest place to measure it: these variants are hard for *both* readers."
        )
    else:
        a("What the two measurable rows already say:")
        a("")
        a(
            f"- **A″ → C′ ({_pct(full['strict_pass_rate'])} → {_pct(ova['pass_rate'])}) is "
            "the generalization gap, measured cleanly.** Both rows use the *same* romanizer "
            "(the authors' strings, best-of) and the *same* strict scoring. The only "
            "variable is which corpus: the one the engine was tuned against, versus the "
            "one written afterwards to attack its documented mechanisms. Nothing about "
            "the LLM is involved in this comparison, which is exactly why it survives "
            "the missing column."
        )
        a(
            f"- **C′'s WRONG rate is {_pct(ova['wrong_rate'])} "
            f"({ova['WRONG']}/{ova['total']}) on the authors' own best-of-two strings.** "
            "These are the charitable romanizations. The pharmacy-relevant number "
            "therefore starts here and can only get worse once one LLM reading replaces "
            "best-of-two."
        )
        a(
            f"- **A → A″ ({_pct(full['pass_rate'])} → {_pct(full['strict_pass_rate'])}) is "
            "the scoring gap, on the tuned corpus alone.** Nothing changed but the rule. "
            "The old T1/T2 bar counted a pass whenever the expected SKU appeared anywhere "
            "in the returned variant list — including inside a *confident `multi_variant` "
            "on a different family*, which on a real order desk is a different drug on the "
            "screen. Strict scoring calls those WRONG."
        )
        a(
            "- **Rows B and C stay empty on purpose.** Substituting the authors' number "
            "for the model's would reproduce precisely the dishonesty this eval was "
            "built to remove."
        )
    a("")

    # The column every table below reports. When the model column is pending,
    # the authors'-strings column is reported *under its own name* — it is a
    # real measurement of the same engine, just a more charitable romanizer.
    col = "gemini" if gemini_ran else "author"
    col_label = (
        f"`{MODEL}`, one string per variant"
        if gemini_ran
        else "the corpus authors' `romanized[]`, best-of (**not** the production path)"
    )

    # ── per corpus ─────────────────────────────────────────────────────────
    a(f"## 2. Per corpus — strict three-way, {col_label}")
    a("")
    a("| corpus | lens | n | PASS | ASK_OK | **WRONG** | wrong count |")
    a("| --- | --- | --- | --- | --- | --- | --- |")
    for corpus, stats in agg["per_corpus"].items():
        g = stats[col]
        a(
            f"| `{corpus}` | {stats['lens']} | {g['total']} | {_pct(g['pass_rate'])} | "
            f"{_pct(g['ask_ok_rate'])} | **{_pct(g['wrong_rate'])}** | {g['WRONG']} |"
        )
    a("")

    # ── per attack class ───────────────────────────────────────────────────
    a("## 3. Per attack class")
    a("")
    a(
        "Sorted by WRONG rate — the top of this table is the fix list's evidence. "
        f"Column: {col_label}."
    )
    a("")
    a("| attack class | n | PASS | ASK_OK | **WRONG** | wrong count |")
    a("| --- | --- | --- | --- | --- | --- |")
    ordered = sorted(
        agg["per_attack"].items(),
        key=lambda kv: (-kv[1][col]["wrong_rate"], -kv[1][col]["total"]),
    )
    for attack, stats in ordered:
        g = stats[col]
        a(
            f"| `{attack}` | {g['total']} | {_pct(g['pass_rate'])} | "
            f"{_pct(g['ask_ok_rate'])} | **{_pct(g['wrong_rate'])}** | {g['WRONG']} |"
        )
    a("")

    # ── traps ──────────────────────────────────────────────────────────────
    passed = [t for t in traps if t.verdict == "PASS"]
    failed = [t for t in traps if t.verdict == "FAIL"]
    a(f"## 4. Traps — {len(passed)}/{len(traps)} pass")
    a("")
    absent = [t for t in traps if t.kind == "absent"]
    collision = [t for t in traps if t.kind == "collision"]
    a(
        f"`absent` ({len(absent)}): a brand a pharmacist really says that is **not in "
        "this catalog**. Pass = `not_found`, or nothing at ≥ 0.5. "
        f"`collision` ({len(collision)}): a real catalog brand with a near-twin. Pass = "
        "the target surfaced **and** the twin did not outrank it."
    )
    a("")
    if traps and traps[0].romanizer != "gemini":
        a(
            "*(Romanizer for this section: the corpus authors' first `romanized[]` "
            "string, because the Gemini column is pending. One fixed plausible reading "
            "per trap — the traps ask what the catalog does with such a reading, and "
            "that question is answerable either way.)*"
        )
        a("")
    a("| kind | said (Devanagari) | searched for | expected | got | verdict | severity |")
    a("| --- | --- | --- | --- | --- | --- | --- |")
    for t in traps:
        expected = t.target_family or "nothing confident"
        if t.must_not_win:
            expected += f" (not {t.must_not_win})"
        mark = "PASS" if t.verdict == "PASS" else "**FAIL**"
        sev = "–" if t.severity == "none" else f"**{t.severity}**"
        a(
            f"| {t.kind} | {t.query_devanagari} | `{t.gemini}` | {expected} | "
            f"{t.detail} | {mark} | {sev} |"
        )
    a("")
    if failed:
        by_sev = Counter(t.severity for t in failed)
        a(
            "**Failing traps by severity:** "
            + ", ".join(f"{k} × {v}" for k, v in sorted(by_sev.items()))
        )
        a("")
        for t in failed:
            if t.severity in ("critical", "high"):
                a(
                    f"- **{t.severity.upper()} — {t.kind}**: `{t.gemini}` → {t.detail}. "
                    + (t.note.split(". ")[0] + "." if t.note else "")
                )
        a("")
    sinex = [t for t in traps if "साइनेक्स" in t.query_devanagari]
    if sinex:
        s = sinex[0]
        a("### The SINEX → R CINEX class")
        a("")
        landed = s.returned.get("family") or ", ".join(s.returned.get("families", []))
        if s.verdict == "FAIL" and "R CINEX" in (landed or ""):
            a(
                f"**Reproduced exactly.** `{s.gemini}` → {s.detail}. SINEX is a nasal "
                "decongestant spray; R CINEX is rifampicin + isoniazid, a tuberculosis "
                "combination that is prescription-only and dangerous to dispense on a "
                "mishearing. The two share a phonetic key neighbourhood and R CINEX is "
                "the deeper family, so `_PHON_BREADTH` (+12 flat for ≥ 8 SKUs) pushes it "
                "over the line while `_CONFIDENCE` reports the stage constant with no "
                "coverage discipline. This single example is the argument for fixes "
                "`short-attractors` and `confidence-discipline` together."
            )
        elif s.verdict == "FAIL":
            a(
                f"**The class reproduces, on a different brand.** `{s.gemini}` → "
                f"{s.detail}. SINEX (a nasal decongestant spray) is absent from this "
                f"catalog, and the engine handed over {landed} anyway rather than "
                "saying so. The red team's specific prediction was R CINEX — "
                "rifampicin + isoniazid, a prescription-only TB combination — which is "
                "what makes this class dangerous rather than merely wrong: the "
                "mechanism (flat `_PHON_BREADTH` favouring the deeper family, plus a "
                "`_CONFIDENCE` constant that cannot express doubt) does not care which "
                "neighbour it lands on. Fixes `short-attractors` and "
                "`confidence-discipline`."
            )
        else:
            a(
                f"**Not reproduced on this run** — `{s.gemini}` → {s.detail}. The class "
                "stays on the watch list: it is a key-neighbourhood collision between a "
                "nasal spray and a TB combination, and the mechanisms that produced it "
                "(flat `_PHON_BREADTH`, constant `_CONFIDENCE`) are unchanged. The "
                "romanization the model happened to write is what saved it, and that is "
                "not a property the engine guarantees."
            )
        a("")

    # ── worst confident-wrong ──────────────────────────────────────────────
    worst = worst_confident_wrong(rows, 10, column=col)
    a("## 5. The ten worst confident-wrong results")
    a("")
    a(
        "Ordered by the confidence the engine reported. Each of these is a row that "
        f"turns green on the pharmacist's screen carrying a drug nobody asked for. "
        f"Column: {col_label}."
    )
    a("")
    a("| # | said (Devanagari) | searched for | wanted | got | conf | attack |")
    a("| --- | --- | --- | --- | --- | --- | --- |")
    for i, r in enumerate(worst, 1):
        ret = getattr(r, f"{col}_returned")
        got = f"{ret.get('status')} → {ret.get('family') or ', '.join(ret.get('families', []))}"
        if ret.get("sku_name"):
            got += f" ({ret['sku_name']})"
        # In the authors' column the reason carries the string that actually
        # produced this verdict ("`ran tak tikiya` → matched on …").
        searched = r.gemini
        if not searched and r.author_reason.startswith("`"):
            searched = r.author_reason.split("`")[1]
        a(
            f"| {i} | {r.devanagari} | `{searched}` | {r.family} | {got} | "
            f"**{ret.get('confidence')}** | `{r.attack}` |"
        )
    a("")
    leaks = [r for r in rows if r.devanagari_leak]
    if leaks:
        a(
            f"({len(leaks)} romanizations leaked Devanagari — production's "
            "`_check_english` guard would reject those and force a retry, so they are "
            "pessimistic here.)"
        )
        a("")

    # ── fix priority ───────────────────────────────────────────────────────
    a("## 6. Fix priority")
    a("")
    a(
        "Ordered by severity × frequency, where frequency is the WRONG + ASK_OK volume "
        "in the attack classes each mechanism owns (WRONG double-weighted). Every item "
        f"names the exact code that produces the behaviour. Frequencies from: {col_label}."
        + (
            ""
            if gemini_ran
            else " These are the *charitable* frequencies; the Gemini column can only "
            "move volume up, and the ordering is unlikely to change because it is "
            "driven by which mechanism owns which attack class, not by the absolute "
            "counts."
        )
    )
    a("")
    a("| # | fix | mechanism | owns (attack classes) | wrong | wrong+ask | score |")
    a("| --- | --- | --- | --- | --- | --- | --- |")
    ranked = _fix_priority(agg, column=col)
    for i, f in enumerate(ranked, 1):
        a(
            f"| {i} | **{f['title']}** | `{f['where']}` | "
            f"{', '.join('`' + x + '`' for x in f['attacks_seen'])} | {f['wrong']} | "
            f"{f['bad']} | {f['score']} |"
        )
    a("")
    for i, f in enumerate(ranked, 1):
        a(f"### {i}. {f['title']}")
        a("")
        a(f"*{f['where']}*")
        a("")
        a(f["detail"])
        a("")

    a("## 7. What is deliberately not here")
    a("")
    a(
        "- **No pass-rate thresholds in CI yet.** `demos/tests/test_orderdesk_adversarial.py` "
        "tests the scorer's arithmetic offline and smoke-tests ten cached variants live; "
        "its floor assertions are `xfail`/skipped with a comment, to be armed after the "
        "fix round lands. Arming a threshold at today's measured number would freeze the "
        "bug in place as the spec."
    )
    a(
        "- **No order history.** See the note at the top: production's PHARMACY CONTEXT "
        "would raise every PASS number here, and would raise it most on exactly the "
        "damaged-brand cases that fail. This eval measures the engine, not the deployed "
        "conversation."
    )
    a(
        "- **One romanization per variant, temperature 0.** No best-of-n, no retry on a "
        "bad reading — production's English guard does force one retry, which this "
        "under-counts."
    )
    a("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ─── entry point ──────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """``--offline`` scores everything that needs no API and leaves the model
    column ``UNRUN``. It exists because the free tier's 500-requests-per-day cap
    can make the full run impossible on a given day, and a partial-but-labelled
    artifact beats no artifact — and beats one with a borrowed number in it."""
    args = list(sys.argv[1:] if argv is None else argv)
    offline = "--offline" in args
    started = time.time()
    romanizer = None if offline else Romanizer()
    if romanizer is None:
        print("adversarial eval · OFFLINE — the model column will be left unmeasured")
    else:
        print(f"adversarial eval · model {MODEL} · cache {len(romanizer.cache)} entries")

    rows: list[VariantResult] = []
    traps: list[TrapResult] = []
    for path in ADV_FILES:
        corpus = json.loads(path.read_text(encoding="utf-8"))
        print(f"· {path.name} — {len(corpus['entries'])} entries", flush=True)
        rows += run_corpus(corpus, path.name, romanizer)
        if corpus.get("traps"):
            print(f"· {path.name} — {len(corpus['traps'])} traps", flush=True)
            traps += run_traps(corpus["traps"], romanizer)

    print("· triangulation — original corpus, same strict method", flush=True)
    tri = run_original_sample(romanizer)
    if romanizer is not None:
        romanizer.save()

    agg = aggregate(rows)
    wall = time.time() - started
    write_results(rows, traps, agg, tri, RESULTS_PATH, wall_seconds=wall, romanizer=romanizer)
    write_report(rows, traps, agg, tri, REPORT_PATH, wall_seconds=wall)

    ov = agg["overall"]["gemini"]
    ova = agg["overall"]["author"]
    print()
    if ov["total"]:
        print(
            f"adversarial Gemini-strict : PASS {_pct(ov['pass_rate'])} · "
            f"ASK_OK {_pct(ov['ask_ok_rate'])} · WRONG {_pct(ov['wrong_rate'])}"
        )
        print(
            f"in-sample Gemini-strict   : PASS {_pct(tri['counts']['pass_rate'])} · "
            f"WRONG {_pct(tri['counts']['wrong_rate'])}"
        )
    else:
        print("adversarial Gemini-strict : PENDING — no model calls made")
    print(
        f"adversarial author-strict : PASS {_pct(ova['pass_rate'])} · "
        f"ASK_OK {_pct(ova['ask_ok_rate'])} · WRONG {_pct(ova['wrong_rate'])}"
    )
    print(f"old T1/T2 (full original) : PASS {_pct(tri['old_method_full_corpus']['pass_rate'])}")
    print(
        "strict, authors' strings  : PASS "
        f"{_pct(tri['old_method_full_corpus']['strict_pass_rate'])} (same corpus, same strings)"
    )
    tc = Counter(t.verdict for t in traps)
    print(f"traps                     : {tc.get('PASS', 0)}/{len(traps)} pass")
    if romanizer is not None:
        print(f"gemini calls this run     : {romanizer.calls} ({romanizer.hits} cache hits)")
    print(f"wrote {RESULTS_PATH}")
    print(f"wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
