"""Phonetic / transliteration robustness — does ``resolve()`` survive a spoken
Hindi product name once it has gone through romanization?

The corpus (``corpus_p1.json``..``corpus_p4.json``) is ~100 real catalog
products, each given several *devanagari* respellings a pharmacist might say
(vowel length, aspirate confusion, sibilant confusion, spelled-out letters,
fused fast speech, ...), and each devanagari spelling given 2-3 plausible
*romanizations* — the ASR/LLM transliteration a voice pipeline would actually
produce. This harness feeds every one of those romanizations straight to
``search.resolve()`` (no LLM in the loop — this is the deterministic catalog
core) and scores what comes back against what the corpus says should have
been findable.

Tier ladder (best tier wins per *variant* — a variant passes if ANY of its
romanizations reaches a passing tier, mirroring production where the LLM picks
one transliteration but any plausible one should work):

  T1 sku_exact  — status matched and sku.code == entry.sku_code, OR
                  (expect=="family" and matched with sku.family == entry.family)
  T2 family_hit — the entry's family was surfaced some other way: matched with
                  the right family (wrong SKU), multi_variant with the right
                  family, the right family among multi_family's families, or
                  the entry's sku_code among the returned variants' codes
  T3 near_miss  — multi_family came back, the right family is absent, but at
                  least one returned family shares the entry family's first 4
                  characters or its phonetic key (a near neighbour was found,
                  just not ranked into the top slot)
  MISS          — not_found, or a multi_family/matched/multi_variant result
                  that doesn't share anything with the intended family

Two levels are scored: per-romanization (strict — every individual query must
clear the bar) and per-variant (any-romanization — the headline number,
because production only needs one plausible transliteration to land).

Run:

    cd demos && uv run python orderdesk/backend/eval/run_phonetic_eval.py

Artifacts land next to this file: ``phonetic_results.json`` (every
romanization scored, plus per-variant/per-bucket rollups) and
``phonetic_report.md`` (the human-readable headline + failure + tuning-target
report, written by a separate pass over ``phonetic_results.json`` — see
``_write_report`` below, invoked automatically at the end of ``main``).
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
CORPUS_FILES = sorted(HERE.glob("corpus_p*.json"))
RESULTS_PATH = HERE / "phonetic_results.json"
REPORT_PATH = HERE / "phonetic_report.md"

_PKG = "orderdesk_backend"

TIERS = ("T1", "T2", "T3", "MISS")
PASS_TIERS = ("T1", "T2")
_RANK = {"T1": 0, "T2": 1, "T3": 2, "MISS": 3}


def _load_backend() -> tuple[ModuleType, ModuleType]:
    """Import ``demos/orderdesk/backend/`` in place, the way the other evals do."""
    if _PKG not in sys.modules:
        pkg = ModuleType(_PKG)
        pkg.__path__ = [str(BACKEND)]  # type: ignore[attr-defined]
        sys.modules[_PKG] = pkg
    search = import_module(f"{_PKG}.search")
    normalize = import_module(f"{_PKG}.normalize")
    return search, normalize


search_mod, normalize_mod = _load_backend()
resolve = search_mod.resolve
phonetic_key = normalize_mod.phonetic_key


# ─── corpus loading ────────────────────────────────────────────────────────


def load_corpus() -> list[dict[str, Any]]:
    """Every ``{bucket, entries}`` file, in filename order."""
    corpora = []
    for path in CORPUS_FILES:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_source"] = path.name
        corpora.append(data)
    return corpora


# ─── scoring one query ─────────────────────────────────────────────────────


def _family_key(family: str) -> str:
    return phonetic_key(family.replace(" ", ""))


def score_query(res: Any, entry: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """``(tier, returned)`` — ``returned`` is a compact summary of what ``res`` was."""
    ef = entry["family"]
    esku = entry["sku_code"]
    expect = entry["expect"]
    status = res.status

    returned: dict[str, Any] = {"status": status}
    if status == "matched" and res.sku is not None:
        returned["sku_code"] = res.sku.code
        returned["family"] = res.sku.family
    elif status == "multi_variant":
        returned["family"] = res.family
        returned["variant_codes"] = [v.code for v in res.variants]
    elif status == "multi_family":
        returned["families"] = [f.family for f in res.families]

    # T1
    if status == "matched" and res.sku is not None:
        if res.sku.code == esku:
            return "T1", returned
        if expect == "family" and res.sku.family == ef:
            return "T1", returned

    # T2 — any of the four alternative conditions
    variant_codes = {v.code for v in res.variants}
    is_t2 = (
        (status == "matched" and res.sku is not None and res.sku.family == ef)
        or (status == "multi_variant" and res.family == ef)
        or (status == "multi_family" and ef in {f.family for f in res.families})
        or (esku in variant_codes)
    )
    if is_t2:
        return "T2", returned

    # T3 — only meaningful for multi_family: a near neighbour, not the family itself
    if status == "multi_family":
        prefix = ef[:4]
        key = _family_key(ef)
        for f in res.families:
            if f.family[:4] == prefix or _family_key(f.family) == key:
                return "T3", returned

    return "MISS", returned


# ─── running the whole corpus ──────────────────────────────────────────────


@dataclass
class RomResult:
    bucket: str
    sku_code: str
    name: str
    family: str
    expect: str
    devanagari: str
    query: str
    tier: str
    returned: dict[str, Any]


def run_all(corpora: list[dict[str, Any]]) -> list[RomResult]:
    out: list[RomResult] = []
    for corpus in corpora:
        bucket = corpus["bucket"]
        for entry in corpus["entries"]:
            for variant in entry["variants"]:
                for query in variant["romanized"]:
                    res = resolve(query)
                    tier, returned = score_query(res, entry)
                    out.append(
                        RomResult(
                            bucket=bucket,
                            sku_code=entry["sku_code"],
                            name=entry["name"],
                            family=entry["family"],
                            expect=entry["expect"],
                            devanagari=variant["devanagari"],
                            query=query,
                            tier=tier,
                            returned=returned,
                        )
                    )
    return out


@dataclass
class VariantResult:
    bucket: str
    sku_code: str
    name: str
    family: str
    expect: str
    devanagari: str
    romanized: list[str]
    tier: str  # best across its romanizations
    per_query: list[RomResult]


def rollup_variants(rom_results: list[RomResult]) -> list[VariantResult]:
    """Group romanization results back into their variant (one devanagari
    spelling + its romanizations), keeping the best tier reached."""
    groups: dict[tuple[str, str, str], list[RomResult]] = defaultdict(list)
    order: list[tuple[str, str, str]] = []
    for r in rom_results:
        key = (r.bucket, r.sku_code, r.devanagari)
        if key not in groups:
            order.append(key)
        groups[key].append(r)
    out = []
    for key in order:
        rs = groups[key]
        best = min(rs, key=lambda r: _RANK[r.tier])
        out.append(
            VariantResult(
                bucket=rs[0].bucket,
                sku_code=rs[0].sku_code,
                name=rs[0].name,
                family=rs[0].family,
                expect=rs[0].expect,
                devanagari=rs[0].devanagari,
                romanized=[r.query for r in rs],
                tier=best.tier,
                per_query=rs,
            )
        )
    return out


# ─── aggregation ────────────────────────────────────────────────────────────


def _tier_counts(tiers: list[str]) -> dict[str, Any]:
    c = Counter(tiers)
    total = len(tiers)
    passed = sum(c[t] for t in PASS_TIERS)
    return {
        "total": total,
        "counts": {t: c.get(t, 0) for t in TIERS},
        "pass_rate": round(passed / total, 4) if total else 0.0,
    }


def aggregate(rom_results: list[RomResult], variants: list[VariantResult]) -> dict[str, Any]:
    overall_rom = _tier_counts([r.tier for r in rom_results])
    overall_var = _tier_counts([v.tier for v in variants])

    by_bucket_rom: dict[str, Any] = {}
    by_bucket_var: dict[str, Any] = {}
    buckets = sorted({r.bucket for r in rom_results})
    for b in buckets:
        by_bucket_rom[b] = _tier_counts([r.tier for r in rom_results if r.bucket == b])
        by_bucket_var[b] = _tier_counts([v.tier for v in variants if v.bucket == b])

    return {
        "romanization_level": {"overall": overall_rom, "by_bucket": by_bucket_rom},
        "variant_level": {"overall": overall_var, "by_bucket": by_bucket_var},
    }


# ─── writing results.json ──────────────────────────────────────────────────


def _rom_wire(r: RomResult) -> dict[str, Any]:
    return {
        "bucket": r.bucket,
        "sku_code": r.sku_code,
        "name": r.name,
        "family": r.family,
        "expect": r.expect,
        "devanagari": r.devanagari,
        "query": r.query,
        "tier": r.tier,
        "returned": r.returned,
    }


def _variant_wire(v: VariantResult) -> dict[str, Any]:
    return {
        "bucket": v.bucket,
        "sku_code": v.sku_code,
        "name": v.name,
        "family": v.family,
        "expect": v.expect,
        "devanagari": v.devanagari,
        "romanized": v.romanized,
        "tier": v.tier,
        "per_query": [_rom_wire(r) for r in v.per_query],
    }


def write_results(
    rom_results: list[RomResult], variants: list[VariantResult], agg: dict[str, Any], path: Path
) -> Path:
    data = {
        "meta": {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "corpus_files": [p.name for p in CORPUS_FILES],
            "romanizations": len(rom_results),
            "variants": len(variants),
        },
        "aggregate": agg,
        "romanizations": [_rom_wire(r) for r in rom_results],
        "variants": [_variant_wire(v) for v in variants],
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# ─── report ─────────────────────────────────────────────────────────────────


def _classify_root_cause(v: VariantResult) -> list[str]:
    """Best-effort tag(s) for *why* a failing variant likely died, grounded in
    what ``normalize.py``'s ``phonetic_key``/``spoken_numbers`` actually do — each
    rule below compares the family's own key against the query's key (both run
    through the *exact* ``phonetic_key`` the engine uses) and names the specific
    fold ``_SINGLES``/``_DIGRAPHS`` is missing. A variant can carry more than one
    tag; the fallback ``ungrouped`` means none of these specific shapes fired."""
    tags: set[str] = set()
    fam_key = _family_key(v.family)
    number_words = {
        "EK",
        "DO",
        "TEEN",
        "CHAR",
        "PAANCH",
        "CHHE",
        "SAAT",
        "AATH",
        "NAU",
        "DUS",
        "BEES",
        "TEES",
        "CHALIS",
        "PACHAS",
        "SAATH",
        "STTAR",
        "ASSI",
        "NABBE",
        "PACHEES",
        "PACHIS",
        "CHAALIS",
        "CHALEES",
        "CHALLIS",
    }
    for q in v.romanized:
        toks = q.upper().split()
        if any(t.rstrip(".,") in number_words for t in toks):
            tags.add(
                "hindi-number-word-not-normalized (spoken_numbers only knows English spellings)"
            )
        if any(len(t) == 1 and t.isalpha() for t in toks) and len(toks) >= 3:
            tags.add("spelled-out-letters (name read letter by letter)")

        qtok = q.replace(" ", "")
        qkey = phonetic_key(qtok)
        if not fam_key or not qkey:
            continue

        bv = lambda k: k.replace("B", "V")  # noqa: E731 — B is never folded to V/W in _SINGLES
        if (fam_key != qkey and bv(fam_key) == bv(qkey)) or (
            fam_key[0] != qkey[0] and {fam_key[0], qkey[0]} <= {"B", "V"}
        ):
            tags.add(
                "b-v-confusion (व heard/spelled as both V/W and B — _SINGLES folds W→V but not B)"
            )

        if fam_key != qkey and (
            fam_key.replace("G", "J") == qkey or qkey.replace("G", "J") == fam_key
        ):
            tags.add("soft-g-gel-vs-jel (G/J not folded — Z→J exists in _SINGLES, G→J does not)")

        if fam_key != qkey and (
            fam_key.replace("VH", "V") == qkey or qkey.replace("VH", "V") == fam_key
        ):
            tags.add(
                "vh-cluster-insertion (व्ह romanized as an extra 'h' the family key doesn't have)"
            )

        if qkey.startswith("A") and not fam_key.startswith("A") and qkey[1:] == fam_key:
            tags.add(
                "epenthetic-i-before-consonant-cluster (leading vowel folds to 'A' in phonetic_key; "
                "the family key has no leading vowel to match against)"
            )

        if (
            len(qkey) >= 2
            and len(fam_key) >= 2
            and qkey[0] == fam_key[0]
            and qkey[-1] == fam_key[-1]
            and len(qkey) <= len(fam_key) - 2
        ):
            tags.add("dropped-middle-syllable (unstressed syllable elided, e.g. omni→om)")

        if (
            qkey[:3] == fam_key[:3]
            and abs(len(qkey) - len(fam_key)) >= 2
            and "dropped-middle-syllable" not in tags
        ):
            tags.add("fused-suffix-or-extra-word (query key runs long past the brand key)")

        if len(qkey) == len(fam_key) and qkey != fam_key and not tags:
            diffs = [i for i, (a, b) in enumerate(zip(fam_key, qkey, strict=True)) if a != b]
            if len(diffs) == 1:
                i = diffs[0]
                tags.add(
                    f"single-letter-substitution ({fam_key[i]}↔{qkey[i]} not folded by _SINGLES/_DIGRAPHS)"
                )
        if len(qkey) == len(fam_key) - 1 and not tags:
            for i in range(len(fam_key)):
                if fam_key[:i] + fam_key[i + 1 :] == qkey:
                    tags.add(
                        "cluster-reduction (an interior consonant dropped, e.g. a liquid like R)"
                    )
                    break

    if not tags:
        joined = "".join(v.romanized[0].split())
        if len(v.romanized[0].split()) == 1 and len(joined) > 10:
            tags.add("fused-fast-speech (long single fused token)")
    return sorted(tags) or ["ungrouped"]


def write_report(
    rom_results: list[RomResult],
    variants: list[VariantResult],
    agg: dict[str, Any],
    path: Path,
    *,
    wall_seconds: float,
) -> Path:
    lines: list[str] = []
    a = lines.append

    a("# Phonetic search eval — orderdesk catalog")
    a("")
    a(
        f"{len(rom_results)} romanizations · {len(variants)} variants · "
        f"{len(CORPUS_FILES)} corpus files · {wall_seconds:.1f}s"
    )
    a("")
    a(
        "No LLM in this loop — every romanized string goes straight to "
        "`search.resolve()`. Tiers: **T1** exact SKU (or right family when the "
        "entry only expects a family), **T2** right family surfaced some other "
        "way (matched-wrong-sku, multi_variant, multi_family, or the sku code "
        "present among returned variants), **T3** a near-family neighbour came "
        "back in a multi_family result but not the right one, **MISS** nothing "
        "useful. Pass = T1 + T2."
    )
    a("")

    a("## Headline")
    a("")
    ov_r = agg["romanization_level"]["overall"]
    ov_v = agg["variant_level"]["overall"]
    a("| level | total | T1 | T2 | T3 | MISS | pass (T1+T2) |")
    a("| --- | --- | --- | --- | --- | --- | --- |")
    a(
        f"| per-romanization (strict) | {ov_r['total']} | {ov_r['counts']['T1']} | "
        f"{ov_r['counts']['T2']} | {ov_r['counts']['T3']} | {ov_r['counts']['MISS']} | "
        f"**{ov_r['pass_rate']:.1%}** |"
    )
    a(
        f"| per-variant (any romanization) | {ov_v['total']} | {ov_v['counts']['T1']} | "
        f"{ov_v['counts']['T2']} | {ov_v['counts']['T3']} | {ov_v['counts']['MISS']} | "
        f"**{ov_v['pass_rate']:.1%}** |"
    )
    a("")

    a("## Per bucket")
    a("")
    a("| bucket | variants | var pass | rom | rom pass |")
    a("| --- | --- | --- | --- | --- |")
    for b in sorted(agg["variant_level"]["by_bucket"]):
        vb = agg["variant_level"]["by_bucket"][b]
        rb = agg["romanization_level"]["by_bucket"][b]
        a(
            f"| `{b}` | {vb['total']} | {vb['pass_rate']:.1%} | {rb['total']} | {rb['pass_rate']:.1%} |"
        )
    a("")

    failing = [v for v in variants if v.tier in ("T3", "MISS")]
    a(f"## Full failure table ({len(failing)} variants at T3/MISS)")
    a("")
    a("| bucket | family | sku | devanagari | romanizations tried | best tier | what came back |")
    a("| --- | --- | --- | --- | --- | --- | --- |")
    for v in sorted(failing, key=lambda v: (v.bucket, v.family, v.devanagari)):
        roms = "; ".join(f"`{q}`" for q in v.romanized)
        backs = []
        for r in v.per_query:
            ret = r.returned
            if ret["status"] == "matched":
                backs.append(f"`{r.query}`→matched {ret.get('sku_code')}/{ret.get('family')}")
            elif ret["status"] == "multi_variant":
                backs.append(f"`{r.query}`→multi_variant {ret.get('family')}")
            elif ret["status"] == "multi_family":
                fams = ", ".join(ret.get("families", [])[:4])
                backs.append(f"`{r.query}`→multi_family [{fams}]")
            else:
                backs.append(f"`{r.query}`→not_found")
        a(
            f"| {v.bucket} | {v.family} | {v.sku_code} | {v.devanagari} | {roms} | "
            f"{v.tier} | {'; '.join(backs)} |"
        )
    a("")

    a("## Tuning targets — failures grouped by root cause")
    a("")
    a(
        "Tags are heuristic groupings (a variant can carry more than one), each "
        "grounded in a specific place `normalize.py` does or doesn't handle the "
        "pattern. See the module docstrings for `search_text`, `phonetic_key`, "
        "and `spoken_numbers`."
    )
    a("")
    by_tag: dict[str, list[VariantResult]] = defaultdict(list)
    for v in failing:
        for tag in _classify_root_cause(v):
            by_tag[tag].append(v)
    for tag, group in sorted(by_tag.items(), key=lambda kv: -len(kv[1])):
        a(f"### `{tag}` — {len(group)} variant(s)")
        a("")
        for v in group[:6]:
            a(
                f"- `{v.devanagari}` → {', '.join(f'`{q}`' for q in v.romanized)} (expected {v.family} / {v.sku_code})"
            )
        if len(group) > 6:
            a(f"- … and {len(group) - 6} more")
        a("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ─── entry point ────────────────────────────────────────────────────────────


def main() -> int:
    started = time.time()
    corpora = load_corpus()
    print(f"phonetic eval · {len(corpora)} corpus files")
    rom_results = run_all(corpora)
    variants = rollup_variants(rom_results)
    agg = aggregate(rom_results, variants)
    wall = time.time() - started

    results_path = write_results(rom_results, variants, agg, RESULTS_PATH)
    report_path = write_report(rom_results, variants, agg, REPORT_PATH, wall_seconds=wall)

    ov_r = agg["romanization_level"]["overall"]
    ov_v = agg["variant_level"]["overall"]
    print(f"per-romanization pass: {ov_r['pass_rate']:.1%} ({ov_r['total']} queries)")
    print(f"per-variant pass:      {ov_v['pass_rate']:.1%} ({ov_v['total']} variants)")
    print(f"wrote {results_path}")
    print(f"wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
