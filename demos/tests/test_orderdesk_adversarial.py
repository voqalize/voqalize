"""Adversarial-eval scorer — arithmetic offline, one live smoke test.

``orderdesk/backend/eval/run_adversarial_eval.py`` is the deep-dive tool: it
romanizes every red-team utterance through gemini-3.1-flash-lite (the
production path), scores each result PASS / ASK_OK / WRONG, runs the traps, and
triangulates against the original corpus — see
``orderdesk/backend/eval/adversarial_report.md``.

This file is the part of it that belongs in CI. Two halves:

* **Offline (no API, no network).** The three-way scorer and the trap scorer are
  driven with hand-built ``Resolution`` objects, so every branch of the verdict
  arithmetic — including the ones the live corpus happens not to hit — is
  pinned. Plus the pure helpers (``clean_romanization``, ``_counts``,
  ``_fix_priority`` ordering, the seeded sample's determinism).
* **Live smoke (skipped without ``GEMINI_API_KEY``, and cheap).** Ten variants
  read out of the romanization cache, resolved and scored end to end — it
  proves the wiring, not the pass rate. It makes **zero** API calls when the
  cache is warm, which is the normal case.

**The floors are armed.** They were held back through the measurement round —
the eval's whole point was that the numbers were the *bug*, and a threshold
asserted at those rates would have frozen the isalpha gate, the FTS
short-circuit and the flat ``_CONFIDENCE`` table in as the spec. The
fix-priority list in ``adversarial_report.md`` §6 has now landed, so
``TestArmedFloors`` reads ``adversarial_results.json`` and asserts the post-fix
rates with a small margin. They run offline: the *authors'-romanization* column
is the one the offline runner always measures, and it is the column every gate
in the fix round was judged on. The Gemini column is asserted only when a run
actually populated it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

DEMOS = Path(__file__).resolve().parents[1]
EVAL_DIR = DEMOS / "orderdesk" / "backend" / "eval"
EVAL_SCRIPT = EVAL_DIR / "run_adversarial_eval.py"
CACHE_PATH = EVAL_DIR / "gemini_romanizations.json"
ADV_R1 = EVAL_DIR / "adv_corpus_r1.json"


def _load_eval_module() -> ModuleType:
    """Import ``run_adversarial_eval.py`` from its path — it lives next to the
    corpora in ``eval/``, not inside an importable package. Importing it must
    not need an API key: the genai client is built lazily on the first live
    call, which the offline tests never make."""
    name = "orderdesk_adversarial_eval"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, EVAL_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def adv() -> ModuleType:
    return _load_eval_module()


# ─── fake resolutions ─────────────────────────────────────────────────────────
#
# The scorer only ever reads ``status``, ``confidence``, ``sku.family``/``.code``
# /``.name``, ``family``, ``variants[].code`` and ``families[].family`` — so a
# namespace with those attributes exercises it exactly, with no sqlite and no
# dependence on what the catalog happens to contain today.


def _sku(family: str, code: str = "X0001", name: str = "X TABLET") -> SimpleNamespace:
    return SimpleNamespace(family=family, code=code, name=name)


def matched(family: str, confidence: float = 0.95) -> SimpleNamespace:
    return SimpleNamespace(
        status="matched",
        sku=_sku(family),
        family=family,
        variants=[],
        families=[],
        confidence=confidence,
    )


def multi_variant(family: str, confidence: float = 0.72, n: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        status="multi_variant",
        sku=None,
        family=family,
        variants=[_sku(family, f"C{i}") for i in range(n)],
        families=[],
        confidence=confidence,
    )


def multi_family(*families: str, confidence: float = 0.45) -> SimpleNamespace:
    return SimpleNamespace(
        status="multi_family",
        sku=None,
        family=None,
        variants=[],
        families=[SimpleNamespace(family=f) for f in families],
        confidence=confidence,
    )


def not_found() -> SimpleNamespace:
    return SimpleNamespace(
        status="not_found", sku=None, family=None, variants=[], families=[], confidence=0.0
    )


# ─── the three-way scorer ─────────────────────────────────────────────────────


class TestScoreStrict:
    """PASS / ASK_OK / WRONG, every branch."""

    def test_matched_right_family_passes(self, adv: ModuleType) -> None:
        verdict, _, ret = adv.score_strict(matched("VOLINI"), "VOLINI")
        assert verdict == "PASS"
        assert ret["family"] == "VOLINI"
        assert ret["confidence"] == 0.95

    def test_multi_variant_right_family_passes(self, adv: ModuleType) -> None:
        verdict, _, _ = adv.score_strict(multi_variant("TELMA"), "TELMA")
        assert verdict == "PASS"

    def test_multi_family_containing_right_family_passes(self, adv: ModuleType) -> None:
        verdict, reason, _ = adv.score_strict(multi_family("PANTOP", "PAN", "PANZA"), "PAN")
        assert verdict == "PASS"
        assert "#2" in reason  # the rank is recorded, not just the membership

    def test_not_found_is_ask_ok_never_pass(self, adv: ModuleType) -> None:
        verdict, reason, _ = adv.score_strict(not_found(), "VOLINI")
        assert verdict == "ASK_OK"
        assert reason == "not_found"

    def test_multi_family_without_right_family_below_threshold_is_ask_ok(
        self, adv: ModuleType
    ) -> None:
        # 0.45 is what search._CONFIDENCE actually pays a name-stage multi_family:
        # the agent asks again, so it costs a turn but hands over nothing.
        verdict, _, _ = adv.score_strict(multi_family("CANDID", "CINOD", confidence=0.45), "VOLINI")
        assert verdict == "ASK_OK"

    @pytest.mark.parametrize("res_factory", [matched, multi_variant])
    def test_wrong_family_is_wrong_at_any_confidence(self, adv: ModuleType, res_factory) -> None:
        # "any confidence" is the point: a quiet wrong answer still puts the
        # wrong drug on the order, it just does it without sounding sure.
        for confidence in (0.95, 0.62, 0.5, 0.11):
            verdict, reason, _ = adv.score_strict(res_factory("JOINTACE", confidence), "ZINETAC")
            assert verdict == "WRONG", confidence
            assert "JOINTACE" in reason and "ZINETAC" in reason

    def test_multi_family_ranking_a_wrong_family_first_at_threshold_is_wrong(
        self, adv: ModuleType
    ) -> None:
        verdict, reason, _ = adv.score_strict(
            multi_family("R CINEX", "RANTAC", confidence=0.55), "SINEX"
        )
        assert verdict == "WRONG"
        assert "R CINEX" in reason

    def test_the_confident_threshold_is_the_weakest_actionable_result(
        self, adv: ModuleType
    ) -> None:
        # CONFIDENT must sit exactly on search._CONFIDENCE[("phonetic",
        # "multi_variant")] — the weakest result the brain still acts on. If the
        # engine's table moves, this test is the thing that notices.
        search = adv.search_mod
        assert adv.CONFIDENT == search._CONFIDENCE[("phonetic", "multi_variant")] == 0.5

    def test_pass_is_the_only_verdict_that_counts_as_a_pass(self, adv: ModuleType) -> None:
        counts = adv._counts(["PASS", "PASS", "ASK_OK", "WRONG", "WRONG", "WRONG"])
        assert counts == {
            "total": 6,
            "PASS": 2,
            "ASK_OK": 1,
            "WRONG": 3,
            "pass_rate": 0.3333,
            "ask_ok_rate": 0.1667,
            "wrong_rate": 0.5,
        }

    def test_empty_counts_do_not_divide_by_zero(self, adv: ModuleType) -> None:
        assert adv._counts([])["pass_rate"] == 0.0


# ─── the trap scorer ──────────────────────────────────────────────────────────


class TestTraps:
    """Absent brands must not resolve confidently; collisions must not lose."""

    ABSENT = {
        "kind": "absent",
        "query_devanagari": "ज़िनटैक",
        "target_family": None,
        "must_not_win": None,
        "note": "ZINETAC is not in this catalog.",
    }
    ABSENT_NAMED = {**ABSENT, "must_not_win": "R CINEX"}
    COLLISION = {
        "kind": "collision",
        "query_devanagari": "सीनॉड दस",
        "target_family": "CINOD",
        "must_not_win": "CANDID",
        "note": "",
    }

    def test_absent_not_found_passes(self, adv: ModuleType) -> None:
        t = adv.score_trap(self.ABSENT, "zinetac", not_found())
        assert t.verdict == "PASS" and t.severity == "none"

    def test_absent_low_confidence_multi_family_passes(self, adv: ModuleType) -> None:
        # multi_family is the agent asking, not the agent handing something over.
        t = adv.score_trap(self.ABSENT, "zinetac", multi_family("JOINTACE", confidence=0.32))
        assert t.verdict == "PASS"

    def test_absent_confident_match_fails_and_records_what_it_matched(
        self, adv: ModuleType
    ) -> None:
        t = adv.score_trap(self.ABSENT, "zinetac", multi_variant("JOINTACE", confidence=0.5))
        assert t.verdict == "FAIL"
        assert t.returned["family"] == "JOINTACE"
        assert "JOINTACE" in t.detail

    @pytest.mark.parametrize(
        ("confidence", "severity"),
        [(0.95, "critical"), (0.82, "critical"), (0.62, "high"), (0.5, "medium")],
    )
    def test_absent_severity_tracks_confidence(
        self, adv: ModuleType, confidence: float, severity: str
    ) -> None:
        t = adv.score_trap(self.ABSENT, "q", matched("JOINTACE", confidence))
        assert (t.verdict, t.severity) == ("FAIL", severity)

    def test_absent_hitting_the_predicted_twin_escalates(self, adv: ModuleType) -> None:
        # The red team named the exact wrong brand; landing on it is worse than
        # landing on some arbitrary one at the same confidence.
        plain = adv.score_trap(self.ABSENT_NAMED, "q", multi_variant("JOINTACE", 0.5))
        named = adv.score_trap(self.ABSENT_NAMED, "q", multi_variant("R CINEX", 0.5))
        assert plain.severity == "medium"
        assert named.severity == "high"

    def test_collision_target_matched_passes(self, adv: ModuleType) -> None:
        assert adv.score_trap(self.COLLISION, "cinod 10", matched("CINOD")).verdict == "PASS"

    def test_collision_losing_to_the_named_twin_is_critical(self, adv: ModuleType) -> None:
        t = adv.score_trap(self.COLLISION, "cinod 10", matched("CANDID"))
        assert (t.verdict, t.severity) == ("FAIL", "critical")

    def test_collision_target_first_in_multi_family_passes(self, adv: ModuleType) -> None:
        t = adv.score_trap(self.COLLISION, "cinod 10", multi_family("CINOD", "CANDID"))
        assert t.verdict == "PASS" and "#1" in t.detail

    def test_collision_twin_outranking_target_fails(self, adv: ModuleType) -> None:
        t = adv.score_trap(self.COLLISION, "cinod 10", multi_family("CANDID", "CINOD"))
        assert (t.verdict, t.severity) == ("FAIL", "high")
        assert "#1" in t.detail and "#2" in t.detail

    def test_collision_target_absent_from_multi_family_fails(self, adv: ModuleType) -> None:
        t = adv.score_trap(self.COLLISION, "cinod 10", multi_family("VOLINI", "TELMA"))
        assert t.verdict == "FAIL"

    def test_collision_not_found_fails(self, adv: ModuleType) -> None:
        # Unlike an absent brand, a *real* catalog brand that never surfaces is
        # a miss, not a clean refusal.
        assert adv.score_trap(self.COLLISION, "cinod 10", not_found()).verdict == "FAIL"

    def test_every_r1_trap_has_the_shape_the_scorer_reads(self, adv: ModuleType) -> None:
        traps = json.loads(ADV_R1.read_text(encoding="utf-8"))["traps"]
        assert len(traps) == 20
        for t in traps:
            assert t["kind"] in ("absent", "collision")
            assert t["query_devanagari"]
            if t["kind"] == "collision":
                assert t["target_family"], t
            else:
                assert t["target_family"] is None, t


# ─── pure helpers ─────────────────────────────────────────────────────────────


class TestHelpers:
    @pytest.mark.parametrize(
        ("raw", "want"),
        [
            ("rantac 150", "rantac 150"),
            ('  "rantac 150"  ', "rantac 150"),
            ("rantac 150\nor maybe zinetac", "rantac 150"),
            ("`pan 40`.", "pan 40"),
            ("“montair lc”", "montair lc"),
            ("", ""),
        ],
    )
    def test_clean_romanization(self, adv: ModuleType, raw: str, want: str) -> None:
        assert adv.clean_romanization(raw) == want

    def test_devanagari_leak_detection(self, adv: ModuleType) -> None:
        # Production's brain._check_english rejects exactly this and forces a
        # retry, so the eval flags it rather than silently scoring it.
        assert adv.has_devanagari("वोलिनी") is True
        assert adv.has_devanagari("volini gel") is False

    def test_cache_key_includes_model_and_prompt_version(self, adv: ModuleType, tmp_path) -> None:
        r = adv.Romanizer(cache_path=tmp_path / "cache.json")
        key = r.key("वोलिनी")
        assert adv.MODEL in key and adv.Romanizer.PROMPT_VERSION in key and "वोलिनी" in key

    def test_a_cold_romanizer_needs_no_api_key(self, adv: ModuleType, tmp_path) -> None:
        r = adv.Romanizer(cache_path=tmp_path / "nope.json")
        assert r.cached("anything") is None and r.calls == 0

    def test_cache_round_trips(self, adv: ModuleType, tmp_path) -> None:
        path = tmp_path / "cache.json"
        r = adv.Romanizer(cache_path=path)
        r.cache[r.key("वोलिनी")] = "volini"
        r.save()
        again = adv.Romanizer(cache_path=path)
        assert again.cached("वोलिनी") == "volini"

    def test_retry_after_reads_the_servers_own_delay(self, adv: ModuleType) -> None:
        blob = "429 RESOURCE_EXHAUSTED {'retryDelay': '38s'} ..."
        assert adv.Romanizer._retry_after(blob) == 38.0
        assert adv.Romanizer._retry_after("500 INTERNAL") is None

    def test_the_original_sample_is_seeded_and_reproducible(self, adv: ModuleType) -> None:
        import random

        everything = adv.original_variants()
        assert len(everything) > adv.SAMPLE_N
        pick = lambda: random.Random(adv.SAMPLE_SEED).sample(everything, adv.SAMPLE_N)  # noqa: E731
        assert [v["devanagari"] for v in pick()] == [v["devanagari"] for v in pick()]

    def test_fix_priority_orders_by_severity_times_frequency(self, adv: ModuleType) -> None:
        # A synthetic aggregate: `wrong-boundary-split` is owned by exactly one
        # fix, and it is the only class with any volume — so that fix must come
        # out on top whatever the hand-written severities say.
        # `total` has to be present and non-zero: `_fix_priority` uses it to skip
        # attack classes the column never scored, which is how the offline run
        # keeps the pending Gemini column out of the ranking.
        per_attack = {
            "wrong-boundary-split": {"gemini": {"total": 40, "WRONG": 30, "ASK_OK": 10}},
        }
        ranked = adv._fix_priority({"per_attack": per_attack})
        assert ranked[0]["id"] == "fts-short-circuit"
        assert ranked[0]["wrong"] == 30
        assert [f["score"] for f in ranked] == sorted((f["score"] for f in ranked), reverse=True)

    def test_old_tier_rule_is_looser_than_strict_in_exactly_one_place(
        self, adv: ModuleType
    ) -> None:
        """The A-vs-A″ gap in the report rests on this one clause, so it is
        pinned: the old T1/T2 bar passed a result whose returned variant list
        merely *contained* the expected SKU code, even when the result was a
        confident ``multi_variant`` on a different family — a different drug on
        the pharmacist's screen. Strict scoring calls that WRONG."""
        res = multi_variant("CANDID", n=2)
        res.variants[0].code = "SKU-LIV-DS"
        assert adv.old_tier_pass(res, "LIV 52", "SKU-LIV-DS") is True
        assert adv.score_strict(res, "LIV 52")[0] == "WRONG"

    def test_old_tier_rule_agrees_with_strict_everywhere_else(self, adv: ModuleType) -> None:
        cases = [
            (matched("RANTAC"), "RANTAC"),
            (matched("UB RUN"), "RANTAC"),
            (multi_variant("TELMA"), "TELMA"),
            (multi_family("PANTOP", "PAN"), "PAN"),
            (multi_family("PANTOP", "PANZA"), "PAN"),
            (not_found(), "VOLINI"),
        ]
        for res, family in cases:
            # No SKU code in play, so the one divergent clause cannot fire.
            old = adv.old_tier_pass(res, family, "SKU-NOT-RETURNED")
            assert old == (adv.score_strict(res, family)[0] == "PASS")

    def test_offline_run_leaves_the_model_column_unrun(self, adv: ModuleType) -> None:
        """``--offline`` must mark the model column, not quietly reuse the
        authors' strings under the model's name."""
        corpus = {
            "entries": [
                {
                    "family": "VOLINI",
                    "name": "VOLINI GEL",
                    "sku_code": "SKU1",
                    "variants": [{"devanagari": "वोलिनी", "romanized": ["volini"], "attack": "t"}],
                }
            ]
        }
        rows = adv.run_corpus(corpus, "fake.json", None)
        assert len(rows) == 1
        assert rows[0].gemini_verdict == adv.UNRUN
        assert rows[0].gemini == ""
        assert rows[0].author_verdict in adv.VERDICTS
        # ...and the aggregate must drop the UNRUN column rather than score it.
        agg = adv.aggregate(rows)
        assert agg["overall"]["gemini"]["total"] == 0
        assert agg["overall"]["author"]["total"] == 1

    def test_every_fix_names_real_attack_classes(self, adv: ModuleType) -> None:
        """The fix list is evidence-driven only if its `attacks` keys exist in
        the corpora — a typo would silently zero a fix's frequency."""
        known = set()
        for path in adv.ADV_FILES:
            data = json.loads(path.read_text(encoding="utf-8"))
            known |= {v["attack"] for e in data["entries"] for v in e["variants"]}
        for fix in adv.FIXES:
            unknown = set(fix["attacks"]) - known
            assert not unknown, f"{fix['id']} references unknown attack classes: {unknown}"


# ─── live smoke ───────────────────────────────────────────────────────────────

_HAS_KEY = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


@pytest.mark.skipif(not _HAS_KEY, reason="no GEMINI_API_KEY — the live path is opt-in")
def test_live_smoke_ten_variants(adv: ModuleType) -> None:
    """Ten cached variants, end to end: romanize → resolve → score.

    This asserts the *wiring*, not the pass rate. With a warm cache it makes
    zero API calls; cold, it makes at most ten (paced under the free tier's
    15 rpm). Every variant must produce one of the three verdicts and a
    non-empty English search string — which is the contract production depends
    on, since brain.py rejects a tool argument carrying Devanagari.
    """
    corpus = json.loads(adv.ADV_FILES[0].read_text(encoding="utf-8"))
    variants = [(e["family"], v) for e in corpus["entries"][:10] for v in e["variants"][:1]]
    assert len(variants) == 10

    romanizer = adv.Romanizer()
    if not CACHE_PATH.exists():
        pytest.skip("no romanization cache — run run_adversarial_eval.py first")

    verdicts = []
    for family, variant in variants:
        query = romanizer.romanize(variant["devanagari"])
        assert query and not adv.has_devanagari(query), (variant["devanagari"], query)
        verdict, reason, returned = adv.score_strict(adv.resolve(query), family)
        assert verdict in adv.VERDICTS
        assert reason and isinstance(returned, dict) and "status" in returned
        verdicts.append(verdict)

    assert len(verdicts) == 10
    # The cache made this free; if it didn't, the run is still under the free
    # tier's per-minute budget.
    assert romanizer.calls <= 10


# ─── the armed floors ─────────────────────────────────────────────────────────
#
# Set from the post-fix run (2026-08-03, authors'-romanization column), each a
# small margin under what the engine measured. WRONG_CEILING is the one that
# matters: a pharmacy cares about wrong drugs, not about being asked twice —
# which is why the PASS floors sit well below the measured rates. Truncation and
# garble *should* degrade into ASK_OK, and chasing PASS there is how precision
# gets sold back.

OVERALL_PASS_FLOOR = 0.78  # measured 82.7%
OVERALL_WRONG_CEILING = 0.010  # measured 0.44% (2 / 450)
CORPUS_PASS_FLOORS = {
    "adv_corpus_r1.json": 0.80,  # measured 85.8% — hostile pharmacist
    "adv_corpus_r2.json": 0.72,  # measured 79.6% — STT damage
}
# 0.015 is "no more than two WRONGs in a 225-row corpus"; a third trips it.
CORPUS_WRONG_CEILING = 0.015
TRAP_PASS_FLOOR = 18  # measured 19 / 20
COLLISION_PASS_FLOOR = 10  # measured 11 / 12
# Triangulation on the original corpus — the no-regression half of the gate.
ORIGINAL_OLD_TIER_FLOOR = 0.995  # measured 99.8%
ORIGINAL_STRICT_FLOOR = 0.950  # measured 95.8%


@pytest.fixture(scope="module")
def results() -> dict:
    path = EVAL_DIR / "adversarial_results.json"
    if not path.exists():
        pytest.skip("no adversarial_results.json — run run_adversarial_eval.py first")
    return json.loads(path.read_text(encoding="utf-8"))


class TestArmedFloors:
    """The post-fix rates, asserted. Offline: the authors'-romanization column
    is always measured, and it is the column the fix round was judged on."""

    def test_overall_author_column(self, results: dict) -> None:
        overall = results["aggregate"]["overall"]["author"]
        assert overall["total"] >= 450, f"corpus looks truncated: {overall['total']} rows"
        assert overall["wrong_rate"] <= OVERALL_WRONG_CEILING, (
            f"WRONG {overall['wrong_rate']:.2%} ({overall['WRONG']} rows) is above the "
            f"{OVERALL_WRONG_CEILING:.1%} ceiling — a WRONG is a different drug on the "
            "order. See adversarial_report.md before loosening this."
        )
        assert overall["pass_rate"] >= OVERALL_PASS_FLOOR, (
            f"PASS {overall['pass_rate']:.1%} fell below {OVERALL_PASS_FLOOR:.0%}"
        )

    def test_per_corpus_author_column(self, results: dict) -> None:
        for name, floor in CORPUS_PASS_FLOORS.items():
            stats = results["aggregate"]["per_corpus"][name]["author"]
            assert stats["wrong_rate"] <= CORPUS_WRONG_CEILING, (
                f"{name}: WRONG {stats['wrong_rate']:.2%} ({stats['WRONG']} rows)"
            )
            assert stats["pass_rate"] >= floor, (
                f"{name}: PASS {stats['pass_rate']:.1%} fell below {floor:.0%}"
            )

    def test_traps_and_their_severities(self, results: dict) -> None:
        traps = results["traps"]
        assert traps["counts"].get("PASS", 0) >= TRAP_PASS_FLOOR
        # Severity is the real assertion: a *medium* trap failure is an option
        # card that missed a family. A high or critical one is the engine
        # confidently handing over the brand the red team predicted it would.
        bad = {sev: n for sev, n in traps["by_severity"].items() if sev in ("high", "critical")}
        assert not bad, f"trap failures at high/critical severity: {bad}"
        collisions = [r for r in traps["rows"] if r["kind"] == "collision"]
        passed = sum(r["verdict"] == "PASS" for r in collisions)
        assert passed >= COLLISION_PASS_FLOOR, f"collision traps {passed}/{len(collisions)}"

    def test_original_corpus_does_not_regress(self, results: dict) -> None:
        full = results["triangulation"]["original_corpus_any_romanization_full"]
        assert full["pass_rate"] >= ORIGINAL_OLD_TIER_FLOOR, (
            f"old T1/T2 on the original corpus fell to {full['pass_rate']:.1%}"
        )
        assert full["strict_pass_rate"] >= ORIGINAL_STRICT_FLOOR, (
            f"strict scoring on the original corpus fell to {full['strict_pass_rate']:.1%}"
        )

    @pytest.mark.skipif(not _HAS_KEY, reason="no GEMINI_API_KEY — the live column is opt-in")
    def test_model_column_when_it_was_run(self, results: dict) -> None:
        """The Gemini column only exists after a non-``--offline`` run. When it
        does, it must clear the same WRONG ceiling — the romanizer sits in front
        of the engine in production, so its damage counts."""
        overall = results["aggregate"]["overall"]["gemini"]
        if not overall["total"]:
            pytest.skip("model column unrun (--offline) — nothing to assert")
        assert overall["wrong_rate"] <= OVERALL_WRONG_CEILING
        assert overall["pass_rate"] >= OVERALL_PASS_FLOOR
