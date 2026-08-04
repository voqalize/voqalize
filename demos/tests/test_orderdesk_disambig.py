"""The disambiguation quality gate — DESIGN §7-bis, against the real model.

Two halves, deliberately:

* **Always** — the harness's own arithmetic (validation, the oracle, the
  information bound, the seeded stratified sample). No network, no key, so a
  bug in the *measurement* can never quietly pass the *measurement*.
* **When `GEMINI_API_KEY` is set** — a six-trial smoke subset through real
  ``gemini-3.1-flash-lite``: TELMA (26 SKUs), VOLINI (10) and THYRONORM (8), two
  hidden targets each, asserted against the shipping thresholds. Roughly ten
  model calls, so CI stays cheap; the full ~190-call sweep lives behind
  ``python orderdesk/backend/eval/disambig_eval.py``.

Without a key the smoke half skips — it does not fail. A model that cannot be
reached is not a model that asks bad questions.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

EVAL_PY = (
    Path(__file__).resolve().parents[1] / "orderdesk" / "backend" / "eval" / "disambig_eval.py"
)


def _load_eval() -> ModuleType:
    """Load the eval script by path — it is a runnable, not a package."""
    spec = importlib.util.spec_from_file_location("orderdesk_disambig_eval", EVAL_PY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ev = _load_eval()

HAS_KEY = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
live = pytest.mark.skipif(not HAS_KEY, reason="no GEMINI_API_KEY — the live eval is opt-in")


def _sku(code: str, **kw) -> object:
    base = {
        "name": code,
        "family": "F",
        "variant_label": "",
        "form": "TABLET",
        "strength": "",
        "pack_size": "10'S",
        "mrp": 1.0,
    }
    return ev.Sku(code=code, **{**base, **kw})


FOUR = [_sku(c) for c in ("A1", "A2", "B1", "B2")]


# ─── the harness's own arithmetic (no network) ────────────────────────────────


def test_validation_accepts_a_clean_partition():
    choices = [{"label": "A", "sku_codes": ["A1", "A2"]}, {"label": "B", "sku_codes": ["B1", "B2"]}]
    errors, flags = ev.validate(choices, FOUR)
    assert errors == [] and flags == []
    assert ev.balance_score(choices, FOUR) == 1.0


def test_validation_catches_the_three_things_the_brain_rejects():
    """One choice, an invented code, and an orphaned candidate — §7-bis's contract."""
    too_few = ev.validate([{"label": "everything", "sku_codes": ["A1", "A2", "B1", "B2"]}], FOUR)[0]
    assert any("choice count" in e for e in too_few)

    invented = ev.validate(
        [
            {"label": "A", "sku_codes": ["A1", "A2", "Z9"]},
            {"label": "B", "sku_codes": ["B1", "B2"]},
        ],
        FOUR,
    )[0]
    assert any("unknown codes" in e for e in invented)

    orphan = ev.validate(
        [{"label": "A", "sku_codes": ["A1"]}, {"label": "B", "sku_codes": ["B1", "B2"]}], FOUR
    )[0]
    assert any("uncovered" in e and "A2" in e for e in orphan)


def test_quality_flags_are_advisory_not_fatal():
    choices = [
        {"label": "", "sku_codes": ["A1", "A2"]},
        {"label": "x" * 80, "sku_codes": ["A2", "B1", "B2"]},
    ]
    errors, flags = ev.validate(choices, FOUR)
    assert errors == []  # everything is covered — the choice set is still valid
    assert any("empty label" in f for f in flags)
    assert any("over" in f for f in flags)
    assert any("overlapping" in f for f in flags)


def test_balance_score_punishes_a_lopsided_split():
    lopsided = [
        {"label": "one", "sku_codes": ["A1"]},
        {"label": "rest", "sku_codes": ["A2", "B1", "B2"]},
    ]
    assert ev.balance_score(lopsided, FOUR) == pytest.approx(1.5)


def test_oracle_takes_the_smallest_group_holding_the_target():
    choices = [
        {"label": "wide", "sku_codes": ["A1", "A2", "B1"]},
        {"label": "tight", "sku_codes": ["A1"]},
        {"label": "other", "sku_codes": ["B2"]},
    ]
    assert ev.oracle(choices, "A1", FOUR)["label"] == "tight"
    assert ev.oracle(choices, "ZZ", FOUR) is None  # coverage failure


def test_information_bound_is_log_base_four():
    assert ev.bound(4) == 0
    assert ev.bound(16) == 1  # one perfect four-way split leaves 4
    assert ev.bound(26) == 2
    assert ev.bound(64) == 2  # 64 → 16 → 4
    assert ev.bound(100) == 3


def test_sample_is_seeded_stratified_and_anchored():
    families, _ = ev.catalog_families()
    assert len(families) > 50, "the catalog should have plenty of ≥5-SKU families"
    picked = ev.sample_families(families, 20)
    assert picked == ev.sample_families(families, 20), "the sample must be reproducible"
    assert len(picked) == 20
    buckets = {ev.bucket_of(len(families[f])) for f in picked}
    assert buckets == {"5-8", "9-15", "16+"}
    assert {"TELMA", "VOLINI"} <= set(picked), "the families DESIGN names must be covered"
    assert all(len(families[f]) >= ev.MIN_FAMILY for f in picked)


def test_targets_spread_across_the_family_variants():
    families, _ = ev.catalog_families()
    targets = ev.pick_targets(families["TELMA"], 4)
    assert len(targets) == 4
    assert len({t.code for t in targets}) == 4
    assert len({t.variant_label for t in targets}) >= 3, "targets must not pile on one variant"


def test_the_prompt_fragment_teaches_the_quality_bar():
    fragment, provenance = ev.prompt_fragment()
    assert len(fragment) > 200 and "ask_choice" in fragment
    low = fragment.lower()
    assert "cover" in low or "uncovered" in low, "coverage rule must be in the prompt"
    assert "pack size" in low, "the never-lead-with-pack-size rule must be in the prompt"
    assert provenance.startswith(("brain.py", "fallback"))


def test_candidate_table_carries_every_axis_the_question_can_use():
    families, source = ev.catalog_families()
    table = ev.render_table(families["VOLINI"])
    assert source.startswith("search.py"), f"catalog.db should be the source, got {source}"
    for column in ("code", "name", "variant", "form", "strength", "pack", "mrp"):
        assert column in table.splitlines()[0]
    assert len(table.splitlines()) == len(families["VOLINI"]) + 1


def test_the_csv_fallback_still_finds_the_same_families():
    """The no-catalog.db path must not quietly measure a different catalog.

    Every raw ``Product_Name`` carries its own code as a suffix; forgetting to
    strip it fractures TELMA from 26 SKUs into 7, which would make the eval look
    easy for the wrong reason."""
    from_csv, source = ev._from_csv()
    from_db, _ = ev.catalog_families()
    assert source == "CSV fallback"
    for name in ("TELMA", "VOLINI", "SHELCAL", "THYRONORM", "4 QUIN", "PAN", "GLYCOMET"):
        assert len(from_csv[name]) == len(from_db[name]), name


# ─── the live gate (opt-in, ~10 model calls) ──────────────────────────────────


@live
def test_smoke_subset_meets_the_design_thresholds():
    """TELMA / VOLINI / THYRONORM x 2 targets, through the real model."""
    data = ev.run_eval(n_families=3, n_targets=2, workers=2)
    agg = data["aggregate"]

    stalled = [t for t in data["trials"] if t["outcome"] == "model_error"]
    if stalled:  # rate limits are a transport problem, not a quality signal
        pytest.skip(f"{len(stalled)}/{len(data['trials'])} trials could not reach the model")

    assert data["meta"]["candidate_source"].startswith("search.py")
    assert agg["trials"] == 6
    assert agg["validity"] >= ev.THRESHOLDS["validity"], agg
    assert agg["avg_rounds"] <= ev.THRESHOLDS["avg_rounds"], agg
    assert agg["max_rounds"] <= ev.THRESHOLDS["max_rounds"], agg
    assert agg["coverage_failures"] == 0, agg
    assert agg["success_rate"] == 1.0, agg

    ok, _ = ev.verdict(agg)
    assert ok


@live
def test_a_twenty_six_sku_family_never_becomes_twenty_six_pills():
    """The make-or-break shape: TELMA is one question, ≤4 pills, target kept."""
    families, _ = ev.catalog_families()
    fragment, _ = ev.prompt_fragment()
    model = ev.Model(ev.SYSTEM_PREFIX + fragment)
    skus = families["TELMA"]
    target = ev.pick_targets(skus, 1)[0]

    trial = ev.run_trial(model, "TELMA", skus, target)
    if trial["outcome"] == "model_error":
        pytest.skip("could not reach the model")

    first = trial["log"][0]
    assert 2 <= len(first["choices"]) <= 4, "never more than four pills"
    assert first["valid"], first["errors"]
    assert first["remaining"] < len(skus) / 2, "round one must halve the list at least"
    assert trial["outcome"] == "success"
    assert len(trial["final_candidates"]) <= ev.LEAF_CAP
    assert target.code in trial["final_candidates"]
