"""Phonetic-search floor — the whole corpus, every run.

``orderdesk/backend/eval/run_phonetic_eval.py`` is the deep-dive tool (headline
numbers, the full failure table, tuning targets grouped by root cause — see
``orderdesk/backend/eval/phonetic_report.md``). This test is the cheap tripwire
that belongs in CI: it runs the *same* corpus through the *same*
``search.resolve()`` and asserts the aggregate floors don't regress.

The floors track what the engine actually achieves, a small margin below it —
they started loose (0.80 / 0.70), the alternate-key round of tuning (B/V, soft
C/G, epenthetic vowels, VH, fused form words — see ``phonetic_report.md``) took
them to 0.97 / 0.95, and the adversarial fix round (Hindi numerals and form
words, brand-digit splitting, length-proportional key windows, coverage-aware
confidence) took the engine to 99.8% overall with no bucket under 99.3%:

* per-variant T1+T2 (pass = the family or exact SKU was surfaced by at least
  one of a variant's romanizations) — **>= 0.99 overall** (measured 99.8%)
* per-variant T1+T2 — **>= 0.98 in every bucket** (measured 100/100/100/99.3)

~600 variants / ~1,300 romanizations, no LLM, no network — this runs in low
single-digit seconds, well under the 30s budget.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1] / "orderdesk" / "backend" / "eval"
EVAL_SCRIPT = EVAL_DIR / "run_phonetic_eval.py"

OVERALL_FLOOR = 0.99
PER_BUCKET_FLOOR = 0.98


def _load_eval_module() -> ModuleType:
    """Import ``run_phonetic_eval.py`` from its path — it lives next to the
    corpus files in ``eval/``, not inside an importable package."""
    name = "orderdesk_phonetic_eval"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, EVAL_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def phonetic_agg() -> dict:
    mod = _load_eval_module()
    corpora = mod.load_corpus()
    rom_results = mod.run_all(corpora)
    variants = mod.rollup_variants(rom_results)
    return mod.aggregate(rom_results, variants)


def test_corpus_files_present() -> None:
    files = sorted(EVAL_DIR.glob("corpus_p*.json"))
    assert len(files) == 4, f"expected 4 corpus files in {EVAL_DIR}, found {len(files)}"


def test_per_variant_overall_floor(phonetic_agg: dict) -> None:
    overall = phonetic_agg["variant_level"]["overall"]
    assert overall["total"] >= 500, f"corpus looks truncated: only {overall['total']} variants"
    assert overall["pass_rate"] >= OVERALL_FLOOR, (
        f"per-variant T1+T2 pass rate {overall['pass_rate']:.1%} fell below the "
        f"{OVERALL_FLOOR:.0%} floor — see orderdesk/backend/eval/phonetic_report.md "
        "for the failure breakdown before touching search.py/normalize.py"
    )


def test_per_variant_bucket_floors(phonetic_agg: dict) -> None:
    by_bucket = phonetic_agg["variant_level"]["by_bucket"]
    assert by_bucket, "no buckets found — did the corpus files load?"
    failures = {
        bucket: stats["pass_rate"]
        for bucket, stats in by_bucket.items()
        if stats["pass_rate"] < PER_BUCKET_FLOOR
    }
    assert not failures, (
        f"bucket(s) below the {PER_BUCKET_FLOOR:.0%} per-variant floor: {failures} — "
        "see orderdesk/backend/eval/phonetic_report.md"
    )
