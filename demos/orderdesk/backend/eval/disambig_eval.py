"""Disambiguation quality — does the model ask the *sharpest* question?

DESIGN §7-bis is the contract: a spoken line that matches ≥5 SKUs never becomes
twenty pills. The brain hands the model a compact candidate table and the model
calls ``ask_choice(question, choices)``; the brain validates 2-4 choices, every
code known, the union covering every candidate. This harness replays that exact
loop against the **real** ``gemini-3.1-flash-lite`` over the **real**
``catalog.db``, with a deterministic oracle standing in for the pharmacist.

The oracle knows a hidden target SKU. Each round it taps the choice that keeps
the target (the smallest such group when several do), the candidate list narrows
to that group, and the model is asked again — until ≤4 candidates remain (the
screen takes over with leaf pills) or three rounds are spent. A target that
appears in *no* choice is a coverage failure: the pharmacist's product fell off
the screen, which is the one outcome the demo cannot survive.

What it measures, per round and aggregated:

* **validity** — 2-4 choices, every code in the current candidate set, the union
  covering all of them (first attempt; a repair round is counted separately, the
  way the brain's retriable tool error would let the model correct itself).
* **rounds-to-≤4** against the information bound ``ceil(log4(N/4))`` — the model
  is not allowed to be much worse than a perfect four-way split.
* **partition balance** — ``largest_group / (N / num_choices)``. 1.0 is a
  perfectly even split; 3.0 means one pill swallowed the list and the answer
  eliminated almost nothing.
* **question text quality** — empty/overlong/duplicated labels, code lists
  leaking into pill text.

Thresholds (DESIGN §7-bis, gating the demo): validity ≥98%, average rounds ≤2,
max rounds 3.

Run the full eval (≈190 model calls, ~6 minutes)::

    cd demos && set -a; source ~/apps/voqalcloud/.env; set +a
    uv run python orderdesk/backend/eval/disambig_eval.py

Artifacts land next to this file: ``disambig_results.json`` (every trial, every
round) and ``disambig_report.md`` (aggregates, per-family table, failures, three
full transcripts, verdict). ``demos/tests/test_orderdesk_disambig.py`` imports
this module and runs a small smoke subset; it skips when there is no API key.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import os
import random
import re
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
BRAIN = BACKEND / "brain.py"
RESULTS = HERE / "disambig_results.json"
REPORT = HERE / "disambig_report.md"

MODEL = "gemini-3.1-flash-lite"
SEED = 20260803
MAX_ROUNDS = 3
LEAF_CAP = 4  # ≤4 candidates → the screen shows leaf pills, no more questions
MIN_FAMILY = 5  # ≥5 candidates → a question is owed
FAMILIES = 20
TARGETS_PER_FAMILY = 4
MAX_LABEL = 44  # a pill label longer than this does not fit on the row
MAX_QUESTION = 160

#: DESIGN §7-bis, the gate.
THRESHOLDS = {"validity": 0.98, "avg_rounds": 2.0, "max_rounds": 3}

_PKG = "orderdesk_backend"


# ─── the catalog (search.py if it is there, the CSV if it is not) ─────────────


def load_backend() -> ModuleType:
    """Import ``demos/orderdesk/backend/`` in place and hand back ``search``."""
    if _PKG not in sys.modules:
        pkg = ModuleType(_PKG)
        pkg.__path__ = [str(BACKEND)]  # type: ignore[attr-defined]
        sys.modules[_PKG] = pkg
    return import_module(f"{_PKG}.search")


@dataclass(frozen=True)
class Sku:
    """The seven fields a candidate line shows. Mirrors ``search.SkuView``."""

    code: str
    name: str
    family: str
    variant_label: str
    form: str
    strength: str
    pack_size: str
    mrp: float


def _from_search(mod: ModuleType) -> tuple[dict[str, list[Sku]], str]:
    """Every family with ≥5 SKUs, straight out of ``catalog.db``."""
    rows = (
        mod.connection()
        .execute(
            "SELECT family, COUNT(*) FROM products GROUP BY family HAVING COUNT(*) >= ?",
            (MIN_FAMILY,),
        )
        .fetchall()
    )
    out: dict[str, list[Sku]] = {}
    for family, _ in rows:
        skus = mod.skus_in_family(family)
        if len(skus) >= MIN_FAMILY:
            out[family] = [
                Sku(
                    code=s.code,
                    name=s.name,
                    family=s.family,
                    variant_label=s.variant_label,
                    form=s.form,
                    strength=s.strength,
                    pack_size=s.pack_size,
                    mrp=s.mrp,
                )
                for s in skus
            ]
    return out, "search.py / catalog.db"


def _from_csv() -> tuple[dict[str, list[Sku]], str]:
    """Fallback: group ``enterro_products.csv`` by brand root ourselves.

    Only reached if ``search.py`` or ``catalog.db`` is missing. Every raw
    ``Product_Name`` carries its own code as a suffix (``TELMA 40 TABLET-J0031270``)
    — strip that first or every family fractures. The brand root is then the leading
    run of name tokens before the first strength number, hyphen suffix or dosage-form
    word: coarser than ``build_catalog.py``'s rule, but it recovers the big families
    well enough to keep the eval runnable while the core is being written."""
    import csv

    path = BACKEND.parent / "data" / "enterro_products.csv"
    forms = {
        "TABLET",
        "TABLETS",
        "CAPSULE",
        "CAPSULES",
        "SYRUP",
        "GEL",
        "CREAM",
        "OINTMENT",
        "INJECTION",
        "DROPS",
        "SUSPENSION",
        "SPRAY",
        "LOTION",
        "POWDER",
        "SOAP",
        "OIL",
        "SACHET",
        "KIT",
        "SOLUTION",
        "LIQUID",
        "CHEWABLE",
        "MG",
        "ML",
        "GM",
    }

    def get(row: dict[str, Any], *names: str) -> str:
        """The first column present under any of its plausible header spellings."""
        return next((str(row[n]).strip() for n in names if row.get(n)), "")

    families: dict[str, list[Sku]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            raw = get(row, "Product_Name", "name", "PRODUCT_NAME").upper()
            code = get(row, "Product_Code", "code", "PRODUCT_CODE").upper()
            if not raw or not code:
                continue
            name = re.sub(rf"[\s-]*{re.escape(code)}\s*$", "", raw).strip(" -")
            name = re.sub(r"\s+", " ", name)
            tokens = [t for t in re.split(r"[\s/]+", name) if t]
            if not tokens:
                continue
            # The brand root is the first token up to its hyphen suffix ("TELMA-H"
            # → TELMA), except that a leading bare number belongs to the name and
            # the root runs on ("4 QUIN", "5 HTP"). Checked against catalog.db:
            # 94% of rows land in the same family search.py gives them, and every
            # family §7-bis names comes out at exactly the right size.
            head = re.split(r"[-,.()]", tokens[0])[0].strip()
            family = head
            if head.isdigit() and len(tokens) > 1:
                family = f"{head} {re.split(r'[-,.()]', tokens[1])[0].strip()}"
            try:
                mrp = float(get(row, "MRP", "mrp") or 0)
            except ValueError:
                mrp = 0.0
            families[family].append(
                Sku(
                    code=code,
                    name=name,
                    family=family,
                    variant_label=name[len(family) :].strip(" -"),
                    form=next((t for t in reversed(tokens) if t.strip("-,.()") in forms), ""),
                    strength=next((t for t in tokens if re.fullmatch(r"[\d./]+", t)), ""),
                    pack_size=get(row, "Pack_Size", "pack_size", "Pack"),
                    mrp=mrp,
                )
            )
    return {f: s for f, s in families.items() if len(s) >= MIN_FAMILY}, "CSV fallback"


def catalog_families(wait_s: float = 0.0) -> tuple[dict[str, list[Sku]], str]:
    """Candidate sets, preferring the real search core; poll briefly for it."""
    deadline = time.monotonic() + wait_s
    while True:
        try:
            mod = load_backend()
            ready = hasattr(mod, "skus_in_family") and hasattr(mod, "sku_by_code")
            if ready and (BACKEND / "catalog.db").exists():
                return _from_search(mod)
        except Exception:  # pragma: no cover — search.py still being written
            pass
        if time.monotonic() >= deadline:
            break
        time.sleep(2.0)
    return _from_csv()


# ─── sampling (seeded, stratified, anchored on the families DESIGN names) ─────

#: Families §7-bis calls out by name — always in the sample, so the report's
#: transcripts are the ones a reader can check against the demo script.
ANCHORS = ("TELMA", "GLYCOMET", "SHELCAL", "VOLINI", "PAN", "MOX", "THYRONORM", "4 QUIN")


def bucket_of(n: int) -> str:
    return "5-8" if n <= 8 else "9-15" if n <= 15 else "16+"


def sample_families(
    families: dict[str, list[Sku]], count: int = FAMILIES, seed: int = SEED
) -> list[str]:
    """Up to ``count`` families, stratified across the three size buckets."""
    rng = random.Random(seed)
    by_bucket: dict[str, list[str]] = defaultdict(list)
    for name, skus in families.items():
        by_bucket[bucket_of(len(skus))].append(name)
    for names in by_bucket.values():
        names.sort()
        rng.shuffle(names)

    order = ["16+", "9-15", "5-8"]
    quota = {b: count // 3 + (1 if i < count % 3 else 0) for i, b in enumerate(order)}
    chosen: dict[str, list[str]] = {b: [] for b in order}
    for anchor in ANCHORS:  # the named families take their bucket's slots first
        if anchor in families:
            bucket = bucket_of(len(families[anchor]))
            if len(chosen[bucket]) < quota[bucket]:
                chosen[bucket].append(anchor)
    for b in order:
        pool = [n for n in by_bucket[b] if n not in chosen[b]]
        while len(chosen[b]) < quota[b] and pool:
            chosen[b].append(pool.pop())
    return [n for b in order for n in chosen[b]]


def pick_targets(skus: list[Sku], k: int = TARGETS_PER_FAMILY, seed: int = SEED) -> list[Sku]:
    """``k`` hidden targets, spread across the family's distinct variants."""
    rng = random.Random(seed)
    groups: dict[str, list[Sku]] = defaultdict(list)
    for sku in skus:
        groups[sku.variant_label or sku.name].append(sku)
    lanes = list(groups.values())
    for lane in lanes:
        rng.shuffle(lane)
    rng.shuffle(lanes)
    want, picks, depth = min(k, len(skus)), [], 0
    while len(picks) < want:
        progressed = False
        for lane in lanes:
            if depth < len(lane):
                picks.append(lane[depth])
                progressed = True
                if len(picks) == want:
                    break
        if not progressed:
            break
        depth += 1
    return picks


# ─── the prompt (brain.py's own fragment when it exists) ─────────────────────

FALLBACK_FRAGMENT = """DISAMBIGUATION — ask the sharpest question, never read the list

When a spoken product matches five or more catalog SKUs you never read the options
aloud and you never put twenty pills on the screen. You call `ask_choice` exactly
once, with a question that splits the candidates as evenly as possible, and then you
ask that SAME question aloud in one short Hindi sentence.

Rules the brain enforces (a violation comes back as a retriable tool error):
- 2 to 4 choices. Never more — four pills is what the row can show.
- Every code in `sku_codes` must be a code from the candidate table you were just
  shown. Never invent a code, never repeat one in two choices.
- The union of all `sku_codes` must cover EVERY candidate. No SKU may be orphaned:
  if the pharmacist wanted the one you dropped, the order is wrong.

The quality bar:
- Choose the axis that splits most evenly. Whatever the pharmacist answers, most of
  the list must die. Maximise elimination, not politeness.
- Group on a meaningful axis, in this order of preference: the suffix / variant line
  (TELMA vs TELMA-AM vs TELMA-H), then form (tablet vs syrup vs injection vs gel),
  then a strength band (20/40 vs 80). Never lead with pack-size trivia.
- Labels are short English pill text — a couple of words, meaningfully distinct from
  each other, never a list of codes and never a number range nobody says out loud.
- At most two rounds to a leaf for 24 candidates. Think log base four.
- A choice that keeps a single SKU is a leaf pill. Four or fewer candidates left means
  the screen shows the leaf pills itself, so there is nothing left to ask."""


#: A section heading in the brain's instruction: unindented, not a bullet, and
#: opening with a run of capitals — "PACE — keep the order moving:" counts, but
#: "Never read it." and the indented worked-example lines do not.
_HEADING = re.compile(r"[A-Z][A-Z0-9 ''/&()]{2,}?\s*(—|--|-|:|$)")


def _section(text: str) -> str | None:
    """The DISAMBIGUATION block of a prompt string, up to the next CAPS heading."""
    lines = text.splitlines()
    start = next(
        (i for i, ln in enumerate(lines) if re.match(r"\s*[#*\s]*DISAMBIGUAT", ln, re.I)),
        None,
    )
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        line = lines[j].strip("#* ")
        unindented = line and lines[j] == lines[j].lstrip() and not line.startswith("-")
        if unindented and _HEADING.match(line):
            end = j
            break
    return "\n".join(lines[start:end]).strip() or None


def prompt_fragment() -> tuple[str, str]:
    """``(fragment, provenance)`` — brain.py's guidance if it has landed yet.

    Parsed, not imported: the brain pulls in the SDK and the ADK, and this eval
    must run while brain.py is still being written by another agent."""
    if BRAIN.exists():
        try:
            tree = ast.parse(BRAIN.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover — mid-edit file
            tree = None
        consts: dict[str, str] = {}
        for node in getattr(tree, "body", []):
            target = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
            elif isinstance(node, ast.AnnAssign):
                target = node.target
            assigned = getattr(node, "value", None)  # only Assign/AnnAssign have one
            literal = isinstance(assigned, ast.Constant) and isinstance(assigned.value, str)
            if isinstance(target, ast.Name) and literal:
                consts[target.id] = assigned.value
        for name, value in consts.items():
            if "DISAMBIG" in name.upper() and len(value) > 200:
                return value.strip(), f"brain.py :: {name}"
        for name, value in consts.items():
            block = _section(value)
            if block and len(block) > 200:
                return block, f"brain.py :: {name} (DISAMBIGUATION section)"
    return FALLBACK_FRAGMENT, "fallback (DESIGN §7-bis, brain.py had none)"


SYSTEM_PREFIX = (
    "You are the MedSetu order desk — a Hindi-speaking voice agent taking a B2B pharma "
    "order. The catalog is the authority; you are the interface. The pharmacist has "
    "named a product that matches several SKUs and you must narrow it down with as few "
    "questions as possible.\n\n"
)

ASK_CHOICE_DOC = (
    "Ask the pharmacist ONE narrowing question about an ambiguous line item. The "
    "choices become the pills on their screen and the question is what you say aloud. "
    "2-4 choices; every sku_code must come from the candidate table; the choices "
    "together must cover every candidate."
)


def render_table(skus: list[Sku]) -> str:
    """The compact candidate table the tool result hands the model (§7-bis)."""
    head = ("code", "name", "variant", "form", "strength", "pack", "mrp")
    rows = [
        (
            s.code,
            s.name,
            s.variant_label or "-",
            s.form or "-",
            s.strength or "-",
            s.pack_size or "-",
            f"{s.mrp:g}",
        )
        for s in skus
    ]
    widths = [max(len(str(r[i])) for r in (head, *rows)) for i in range(len(head))]
    line = lambda r: "  ".join(str(c).ljust(w) for c, w in zip(r, widths, strict=True)).rstrip()  # noqa: E731
    return "\n".join([line(head), *(line(r) for r in rows)])


def opening_turn(family: str, skus: list[Sku]) -> str:
    return (
        f'The pharmacist said "{family.lower()}". The catalog returns {len(skus)} '
        f"candidate SKUs — too many to read out and too many for pills:\n\n"
        f"{render_table(skus)}\n\n"
        f"Call ask_choice now with the sharpest question for these {len(skus)} candidates."
    )


def next_turn(skus: list[Sku], answer: str) -> dict[str, Any]:
    return {
        "status": "narrowed",
        "pharmacist_answered": answer,
        "remaining": len(skus),
        "candidates": render_table(skus),
        "instruction": (
            f"Still {len(skus)} candidates — more than the {LEAF_CAP} the screen can show as "
            "leaf pills. Call ask_choice again on exactly these, with a different axis."
        ),
    }


# ─── the model call ───────────────────────────────────────────────────────────


def _declaration(types: Any) -> Any:
    return types.FunctionDeclaration(
        name="ask_choice",
        description=ASK_CHOICE_DOC,
        parameters=types.Schema(
            type="OBJECT",
            properties={
                # Accepted but unused here: the harness runs one row at a time, and
                # brain.py's prompt example passes it — the schema must not fight it.
                "item_id": types.Schema(type="STRING", description="The row being narrowed."),
                "question": types.Schema(
                    type="STRING",
                    description="The one short question you will ask aloud, in English here.",
                ),
                "choices": types.Schema(
                    type="ARRAY",
                    description="2 to 4 choices whose sku_codes cover every candidate.",
                    items=types.Schema(
                        type="OBJECT",
                        properties={
                            "label": types.Schema(
                                type="STRING", description="Short English pill label."
                            ),
                            "sku_codes": types.Schema(
                                type="ARRAY",
                                items=types.Schema(type="STRING"),
                                description="The candidate codes this choice keeps.",
                            ),
                        },
                        required=["label", "sku_codes"],
                    ),
                ),
            },
            required=["question", "choices"],
        ),
    )


class Model:
    """One google-genai client, forced to call ``ask_choice`` every turn.

    Shared across the worker threads, so it also owns the pacer: the free-tier
    key 429s somewhere north of two calls a second, and a rate-limited trial is
    a hole in the dataset, not a finding about the model."""

    def __init__(self, system: str, model: str = MODEL, rpm: int = 100) -> None:
        import threading

        from google import genai
        from google.genai import types

        self.types = types
        self.client = genai.Client()
        self.model = model
        self._gate = threading.Lock()
        self._interval = 60.0 / max(rpm, 1)
        self._next_at = 0.0
        self.config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.0,
            tools=[types.Tool(function_declarations=[_declaration(types)])],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="ANY", allowed_function_names=["ask_choice"]
                )
            ),
        )
        self.calls = 0

    def _pace(self) -> None:
        with self._gate:
            wait = self._next_at - time.monotonic()
            self._next_at = max(self._next_at, time.monotonic()) + self._interval
        if wait > 0:
            time.sleep(wait)

    def call(self, contents: list[Any], attempts: int = 6) -> tuple[Any, Any]:
        """``(function_call_args, model_content)``; retries 429/5xx with backoff."""
        delay = 5.0
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                self._pace()
                self.calls += 1
                resp = self.client.models.generate_content(
                    model=self.model, contents=contents, config=self.config
                )
                content = resp.candidates[0].content
                for part in content.parts or []:
                    if getattr(part, "function_call", None):
                        return dict(part.function_call.args or {}), content
                raise RuntimeError(f"no function call in response: {resp.text!r}")
            except Exception as exc:  # every transport error retries
                last = exc
                text = f"{type(exc).__name__}: {exc}"
                retriable = any(
                    m in text
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
                        "no function call",
                    )
                )
                if not retriable or attempt == attempts - 1:
                    break
                time.sleep(delay + random.random())
                delay *= 2
        raise RuntimeError(f"model call failed after {attempts} attempts: {last}")


# ─── validation, oracle, metrics ──────────────────────────────────────────────


@dataclass
class RoundResult:
    index: int
    n_candidates: int
    candidates: list[str]
    question: str
    choices: list[dict[str, Any]]
    valid: bool
    errors: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    balance: float | None = None
    repaired: bool = False
    chosen_label: str | None = None
    remaining: int | None = None


def validate(choices: list[dict[str, Any]], candidates: list[Sku]) -> tuple[list[str], list[str]]:
    """``(hard errors, quality flags)`` — the brain's check plus the text bar."""
    known = {s.code for s in candidates}
    errors, flags = [], []
    if not 2 <= len(choices) <= 4:
        errors.append(f"choice count {len(choices)} outside 2-4")
    seen: set[str] = set()
    covered: set[str] = set()
    for choice in choices:
        codes = [str(c).strip().upper() for c in (choice.get("sku_codes") or [])]
        label = str(choice.get("label") or "")
        unknown = [c for c in codes if c not in known]
        if unknown:
            errors.append(f"unknown codes in {label!r}: {', '.join(sorted(set(unknown))[:5])}")
        if not codes:
            errors.append(f"choice {label!r} keeps no SKU")
        dupes = {c for c in codes if c in covered}
        if dupes:
            flags.append(f"overlapping codes in {label!r} ({len(dupes)})")
        if not label.strip():
            flags.append("empty label")
        elif len(label) > MAX_LABEL:
            flags.append(f"label over {MAX_LABEL} chars: {label[:30]!r}…")
        if re.search(r"\bJ0\d{4,}", label):
            flags.append(f"code leaked into label {label!r}")
        key = label.strip().lower()
        if key in seen:
            flags.append(f"duplicate label {label!r}")
        seen.add(key)
        covered |= set(codes) & known
    missing = known - covered
    if missing:
        errors.append(f"{len(missing)} candidate(s) uncovered: {', '.join(sorted(missing)[:5])}")
    return errors, flags


def balance_score(choices: list[dict[str, Any]], candidates: list[Sku]) -> float:
    """``largest / (N / k)`` — 1.0 is a perfectly even partition."""
    known = {s.code for s in candidates}
    sizes = [
        len({str(c).strip().upper() for c in (ch.get("sku_codes") or [])} & known) for ch in choices
    ]
    if not sizes or not any(sizes):
        return float("inf")
    return max(sizes) / (len(known) / len(sizes))


def oracle(choices: list[dict[str, Any]], target: str, candidates: list[Sku]) -> dict | None:
    """The simulated pharmacist: the smallest choice that still holds the target."""
    known = {s.code for s in candidates}
    holding = [
        (len({str(c).strip().upper() for c in (ch.get("sku_codes") or [])} & known), i, ch)
        for i, ch in enumerate(choices)
        if target in {str(c).strip().upper() for c in (ch.get("sku_codes") or [])}
    ]
    if not holding:
        return None
    return min(holding, key=lambda t: (t[0], t[1]))[2]


def bound(n: int) -> int:
    """The information-theoretic floor: rounds of a perfect 4-way split to ≤4."""
    return 0 if n <= LEAF_CAP else math.ceil(math.log(n / LEAF_CAP, 4))


# ─── one trial ────────────────────────────────────────────────────────────────


def run_trial(model: Model, family: str, skus: list[Sku], target: Sku) -> dict[str, Any]:
    """Narrow ``skus`` down to the hidden ``target``, the way the demo would."""
    types = model.types
    contents = [types.Content(role="user", parts=[types.Part(text=opening_turn(family, skus))])]
    candidates = list(skus)
    rounds: list[RoundResult] = []
    outcome = "max_rounds"

    for index in range(1, MAX_ROUNDS + 1):
        if len(candidates) <= LEAF_CAP:
            outcome = "success"
            break
        try:
            args, content = model.call(contents)
        except Exception as exc:
            outcome = "model_error"
            rounds.append(
                RoundResult(
                    index,
                    len(candidates),
                    [s.code for s in candidates],
                    "",
                    [],
                    valid=False,
                    errors=[str(exc)[:300]],
                )
            )
            break
        contents.append(content)

        question = str(args.get("question") or "")
        choices = [dict(c) for c in (args.get("choices") or [])]
        errors, flags = validate(choices, candidates)
        record = RoundResult(
            index=index,
            n_candidates=len(candidates),
            candidates=[s.code for s in candidates],
            question=question,
            choices=[
                {
                    "label": str(c.get("label") or ""),
                    "sku_codes": [str(x).upper() for x in (c.get("sku_codes") or [])],
                }
                for c in choices
            ],
            valid=not errors,
            errors=errors,
            flags=flags,
            balance=None if errors else round(balance_score(choices, candidates), 3),
        )
        if not question.strip():
            record.flags.append("empty question")
        elif len(question) > MAX_QUESTION:
            record.flags.append(f"question over {MAX_QUESTION} chars")

        if errors:
            # The brain's retriable tool error — one repair attempt, as in production.
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(
                            name="ask_choice",
                            response={
                                "status": "invalid",
                                "errors": errors,
                                "instruction": (
                                    "Your choice set was rejected. Call ask_choice again on the "
                                    f"same {len(candidates)} candidates: 2-4 choices, only codes "
                                    "from the table, and every candidate in exactly one choice."
                                ),
                            },
                        )
                    ],
                )
            )
            try:
                args, content = model.call(contents)
            except Exception as exc:
                rounds.append(record)
                outcome = "model_error"
                record.errors.append(str(exc)[:300])
                break
            contents.append(content)
            question = str(args.get("question") or "")
            choices = [dict(c) for c in (args.get("choices") or [])]
            errors2, flags2 = validate(choices, candidates)
            record.repaired = True
            record.flags += flags2
            record.errors += [f"(repair) {e}" for e in errors2]
            record.question = question
            record.choices = [
                {
                    "label": str(c.get("label") or ""),
                    "sku_codes": [str(x).upper() for x in (c.get("sku_codes") or [])],
                }
                for c in choices
            ]
            record.balance = None if errors2 else round(balance_score(choices, candidates), 3)
            if errors2:
                rounds.append(record)
                outcome = "invalid"
                break

        picked = oracle(choices, target.code, candidates)
        if picked is None:
            rounds.append(record)
            outcome = "coverage_failure"
            break
        record.chosen_label = str(picked.get("label") or "")
        kept = {str(c).strip().upper() for c in (picked.get("sku_codes") or [])}
        narrowed = [s for s in candidates if s.code in kept]
        record.remaining = len(narrowed)
        rounds.append(record)

        if len(narrowed) == len(candidates):
            outcome = "stalled"
            break
        candidates = narrowed
        if len(candidates) <= LEAF_CAP:
            outcome = "success" if target.code in {s.code for s in candidates} else "target_lost"
            break
        contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part.from_function_response(
                        name="ask_choice", response=next_turn(candidates, record.chosen_label)
                    )
                ],
            )
        )

    if outcome == "success" and target.code not in {s.code for s in candidates}:
        outcome = "target_lost"

    return {
        "family": family,
        "size": len(skus),
        "bucket": bucket_of(len(skus)),
        "target": target.code,
        "target_label": " ".join(
            p for p in (target.variant_label, target.strength, target.form, target.pack_size) if p
        )
        or target.name,
        "target_name": target.name,
        "outcome": outcome,
        "rounds": len(rounds),
        "bound": bound(len(skus)),
        "final_candidates": [s.code for s in candidates],
        "log": [asdict(r) for r in rounds],
    }


# ─── the run ──────────────────────────────────────────────────────────────────


def build_trials(
    families: dict[str, list[Sku]], n_families: int, n_targets: int, seed: int = SEED
) -> list[tuple[str, list[Sku], Sku]]:
    picked = sample_families(families, n_families, seed)
    trials = []
    for i, family in enumerate(picked):
        skus = families[family]
        for target in pick_targets(skus, n_targets, seed + i):
            trials.append((family, skus, target))
    return trials


def run_eval(
    n_families: int = FAMILIES,
    n_targets: int = TARGETS_PER_FAMILY,
    workers: int = 4,
    wait_for_backend: float = 0.0,
    progress: bool = False,
    rpm: int = 100,
) -> dict[str, Any]:
    families, source = catalog_families(wait_for_backend)
    fragment, provenance = prompt_fragment()
    model = Model(SYSTEM_PREFIX + fragment, rpm=rpm)
    trials = build_trials(families, n_families, n_targets)

    started = time.time()
    done = [0]

    def one(t: tuple[str, list[Sku], Sku]) -> dict[str, Any]:
        result = run_trial(model, *t)
        done[0] += 1
        if progress:
            print(
                f"  [{done[0]:>3}/{len(trials)}] {result['family']:<16} n={result['size']:<3} "
                f"→ {result['outcome']} in {result['rounds']} round(s)",
                flush=True,
            )
        return result

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, trials))

    # A transport failure is a hole in the dataset, not a measurement. Sweep the
    # rate-limited trials again, serially, after letting the minute roll over.
    stragglers = [i for i, r in enumerate(results) if r["outcome"] == "model_error"]
    if stragglers:
        if progress:
            print(f"  retrying {len(stragglers)} rate-limited trial(s) serially…", flush=True)
        time.sleep(30)
        for i in stragglers:
            retried = run_trial(model, *trials[i])
            if progress:
                print(f"  [retry] {retried['family']:<16} → {retried['outcome']}", flush=True)
            if retried["outcome"] != "model_error":
                results[i] = retried

    return {
        "meta": {
            "model": MODEL,
            "seed": SEED,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "candidate_source": source,
            "prompt_fragment_source": provenance,
            "prompt_fragment": fragment,
            "families_eligible": len(families),
            "families_sampled": len({t[0] for t in trials}),
            "trials": len(trials),
            "model_calls": model.calls,
            "wall_seconds": round(time.time() - started, 1),
            "thresholds": THRESHOLDS,
        },
        "trials": results,
        "aggregate": aggregate(results),
    }


def aggregate(trials: list[dict[str, Any]]) -> dict[str, Any]:
    """Everything the report's verdict is computed from."""
    rounds = [r for t in trials for r in t["log"]]
    scored = [r for r in rounds if r["question"] or r["choices"]]
    first_ok = [r for r in scored if not r["repaired"] and not r["errors"]]
    balances = [r["balance"] for r in rounds if r.get("balance") not in (None, float("inf"))]
    counts: dict[str, int] = defaultdict(int)
    for t in trials:
        counts[t["outcome"]] += 1
    flags: dict[str, int] = defaultdict(int)
    for r in rounds:
        for f in r["flags"]:
            flags[re.split(r"[:(]", f)[0].strip()] += 1

    completed = [
        t for t in trials if t["outcome"] in {"success", "target_lost", "max_rounds", "stalled"}
    ]
    successes = [t for t in trials if t["outcome"] == "success"]
    all_rounds = [t["rounds"] for t in completed] or [0]
    excess = [t["rounds"] - t["bound"] for t in successes]
    return {
        "trials": len(trials),
        "choice_sets": len(scored),
        "validity": round(len(first_ok) / len(scored), 4) if scored else 0.0,
        "repairs": sum(1 for r in scored if r["repaired"]),
        "repairs_that_worked": sum(1 for r in scored if r["repaired"] and not r["errors"]),
        "success_rate": round(len(successes) / len(trials), 4) if trials else 0.0,
        "avg_rounds": round(statistics.mean(all_rounds), 3),
        "avg_rounds_successful": round(statistics.mean([t["rounds"] for t in successes]), 3)
        if successes
        else None,
        "max_rounds": max(all_rounds),
        "avg_excess_over_bound": round(statistics.mean(excess), 3) if excess else None,
        "at_or_under_bound": sum(1 for e in excess if e <= 0),
        "avg_balance": round(statistics.mean(balances), 3) if balances else None,
        "median_balance": round(statistics.median(balances), 3) if balances else None,
        "worst_balance": round(max(balances), 3) if balances else None,
        "coverage_failures": counts.get("coverage_failure", 0),
        "outcomes": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "quality_flags": dict(sorted(flags.items(), key=lambda kv: -kv[1])),
    }


def verdict(agg: dict[str, Any]) -> tuple[bool, list[tuple[str, str, str, bool]]]:
    checks = [
        (
            "choice-set validity",
            f"{agg['validity']:.1%}",
            f"≥ {THRESHOLDS['validity']:.0%}",
            agg["validity"] >= THRESHOLDS["validity"],
        ),
        (
            "average rounds",
            f"{agg['avg_rounds']}",
            f"≤ {THRESHOLDS['avg_rounds']}",
            agg["avg_rounds"] <= THRESHOLDS["avg_rounds"],
        ),
        (
            "max rounds",
            f"{agg['max_rounds']}",
            f"≤ {THRESHOLDS['max_rounds']}",
            agg["max_rounds"] <= THRESHOLDS["max_rounds"],
        ),
        ("coverage failures", f"{agg['coverage_failures']}", "0", agg["coverage_failures"] == 0),
    ]
    return all(c[3] for c in checks), checks


# ─── the report ───────────────────────────────────────────────────────────────


def _trial_penalty(t: dict[str, Any]) -> tuple:
    """Sort key for "worst trial": failures first, then rounds, then balance."""
    rank = {
        "coverage_failure": 0,
        "target_lost": 1,
        "invalid": 2,
        "model_error": 2,
        "stalled": 3,
        "max_rounds": 4,
        "success": 5,
    }
    worst_balance = max((r["balance"] for r in t["log"] if r.get("balance")), default=0)
    return (rank.get(t["outcome"], 5), -t["rounds"] + t["bound"], -worst_balance)


def transcript(t: dict[str, Any], families: dict[str, list[Sku]]) -> str:
    by_code = {s.code: s for s in families.get(t["family"], [])}
    out = [
        f"#### `{t['family']}` — {t['size']} SKUs, hidden target **{t['target']}** "
        f"({t['target_name']})",
        "",
        "Candidate table handed to the model:",
        "",
        "```",
        render_table([by_code[c] for c in t["log"][0]["candidates"] if c in by_code])
        if t["log"]
        else "(no rounds)",
        "```",
        "",
    ]
    for r in t["log"]:
        out.append(
            f"**Round {r['index']}** — {r['n_candidates']} candidates"
            + (" · REPAIRED after a rejected choice set" if r["repaired"] else "")
        )
        out.append("")
        out.append(f"> {r['question']}")
        out.append("")
        for c in r["choices"]:
            mark = " ← pharmacist taps this" if c["label"] == r["chosen_label"] else ""
            codes = ", ".join(c["sku_codes"][:6]) + ("…" if len(c["sku_codes"]) > 6 else "")
            out.append(f"- **{c['label']}** ({len(c['sku_codes'])}): {codes}{mark}")
        if r["balance"] is not None:
            out.append(f"\nbalance {r['balance']} · narrows to {r['remaining']}")
        if r["errors"]:
            out.append(f"\n:x: {'; '.join(r['errors'])}")
        if r["flags"]:
            out.append(f"\n:warning: {'; '.join(r['flags'])}")
        out.append("")
    out.append(
        f"**Outcome:** {t['outcome']} in {t['rounds']} round(s) "
        f"(bound {t['bound']}); left on screen: "
        f"{', '.join(t['final_candidates'])}\n"
    )
    return "\n".join(out)


def write_report(data: dict[str, Any], families: dict[str, list[Sku]], path: Path = REPORT) -> Path:
    meta, agg, trials = data["meta"], data["aggregate"], data["trials"]
    ok, checks = verdict(agg)
    lines: list[str] = []
    a = lines.append

    a("# Disambiguation quality — real-model eval")
    a("")
    a(
        f"`{meta['model']}` · {meta['trials']} trials over {meta['families_sampled']} families "
        f"({meta['families_eligible']} eligible in the catalog) · {meta['model_calls']} model calls "
        f"· {meta['wall_seconds']}s · seed {meta['seed']}"
    )
    a("")
    a(f"- Candidate sets: **{meta['candidate_source']}**")
    a(f"- Prompt fragment: **{meta['prompt_fragment_source']}**")
    a(f"- Generated: {meta['generated_at']}")
    a("")
    a("## Verdict")
    a("")
    a(f"**{'PASS' if ok else 'FAIL'}** against DESIGN §7-bis.")
    a("")
    a("| gate | measured | threshold | |")
    a("| --- | --- | --- | --- |")
    for name, got, want, passed in checks:
        a(f"| {name} | {got} | {want} | {'PASS' if passed else 'FAIL'} |")
    a("")
    a("## Aggregate")
    a("")
    a("| metric | value |")
    a("| --- | --- |")
    for key in (
        "trials",
        "choice_sets",
        "validity",
        "repairs",
        "repairs_that_worked",
        "success_rate",
        "avg_rounds",
        "avg_rounds_successful",
        "max_rounds",
        "avg_excess_over_bound",
        "at_or_under_bound",
        "avg_balance",
        "median_balance",
        "worst_balance",
        "coverage_failures",
    ):
        a(f"| {key.replace('_', ' ')} | {agg[key]} |")
    a("")
    a(f"Outcomes: {', '.join(f'`{k}` {v}' for k, v in agg['outcomes'].items())}")
    a("")
    if agg["quality_flags"]:
        a(
            f"Question-text flags: {', '.join(f'`{k}` {v}' for k, v in agg['quality_flags'].items())}"
        )
    else:
        a("Question-text flags: none.")
    a("")

    a("## Per family")
    a("")
    a("| family | SKUs | bucket | trials | success | avg rounds | bound | avg balance | validity |")
    a("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    by_family: dict[str, list[dict]] = defaultdict(list)
    for t in trials:
        by_family[t["family"]].append(t)
    for family, group in sorted(by_family.items(), key=lambda kv: (-kv[1][0]["size"], kv[0])):
        rounds = [r for t in group for r in t["log"] if r["question"] or r["choices"]]
        good = [r for r in rounds if not r["repaired"] and not r["errors"]]
        bal = [r["balance"] for r in rounds if r.get("balance")]
        wins = sum(1 for t in group if t["outcome"] == "success")
        avg_bal = f"{statistics.mean(bal):.2f}" if bal else "-"
        validity = f"{len(good)}/{len(rounds)}" if rounds else "-"
        a(
            f"| `{family}` | {group[0]['size']} | {group[0]['bucket']} | {len(group)} | "
            f"{wins}/{len(group)} | {statistics.mean([t['rounds'] for t in group]):.2f} | "
            f"{group[0]['bound']} | {avg_bal} | {validity} |"
        )
    a("")

    failures = [t for t in trials if t["outcome"] != "success"]
    a(f"## Failures ({len(failures)})")
    a("")
    if failures:
        a("| family | n | target | outcome | rounds | why |")
        a("| --- | --- | --- | --- | --- | --- |")
        for t in sorted(failures, key=_trial_penalty):
            why = "; ".join(e for r in t["log"] for e in r["errors"]) or (
                f"ran out of rounds with {len(t['final_candidates'])} left"
                if t["outcome"] == "max_rounds"
                else "chosen group did not shrink the list"
                if t["outcome"] == "stalled"
                else "target was in no choice"
                if t["outcome"] == "coverage_failure"
                else t["outcome"]
            )
            a(
                f"| `{t['family']}` | {t['size']} | {t['target']} | {t['outcome']} | "
                f"{t['rounds']} | {why[:180]} |"
            )
    else:
        a("None — every trial narrowed to ≤4 candidates with the target still on screen.")
    a("")

    a("## Worst five trials")
    a("")
    for t in sorted(trials, key=_trial_penalty)[:5]:
        worst = max((r["balance"] for r in t["log"] if r.get("balance")), default=None)
        a(
            f"- `{t['family']}` (n={t['size']}, target {t['target']}) — **{t['outcome']}** in "
            f"{t['rounds']} round(s) vs bound {t['bound']}, worst balance {worst}. "
            + (
                "; ".join(e for r in t["log"] for e in r["errors"])
                or "; ".join(f for r in t["log"] for f in r["flags"])
                or "no hard error — cost only."
            )
        )
    a("")

    a("## Transcripts")
    a("")
    for t in featured(trials):
        a(transcript(t, families))
    return _write(path, "\n".join(lines) + "\n")


def featured(trials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One TELMA-sized (16+), one VOLINI-sized (9-15), one 5-6 SKU family."""
    out = []
    for bucket, prefer in (("16+", "TELMA"), ("9-15", "VOLINI"), ("5-8", None)):
        pool = [t for t in trials if t["bucket"] == bucket]
        if bucket == "5-8":
            pool = [t for t in pool if t["size"] <= 6] or pool
        if not pool:
            continue
        pick = next((t for t in pool if t["family"] == prefer), None) or pool[0]
        out.append(pick)
    return out


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--families", type=int, default=FAMILIES)
    ap.add_argument("--targets", type=int, default=TARGETS_PER_FAMILY)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--rpm", type=int, default=100, help="client-side rate cap")
    ap.add_argument("--wait", type=float, default=0.0, help="seconds to poll for search.py")
    ap.add_argument("--out", type=Path, default=HERE)
    args = ap.parse_args(argv)

    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        print(
            "GEMINI_API_KEY is not set — `set -a; source ~/apps/voqalcloud/.env; set +a` first.",
            file=sys.stderr,
        )
        return 2

    print(f"disambig eval · {MODEL} · {args.families} families x {args.targets} targets")
    data = run_eval(
        args.families, args.targets, args.workers, args.wait, progress=True, rpm=args.rpm
    )
    families, _ = catalog_families()
    results = _write(args.out / RESULTS.name, json.dumps(data, indent=2, ensure_ascii=False))
    report = write_report(data, families, args.out / REPORT.name)

    agg = data["aggregate"]
    ok, checks = verdict(agg)
    print()
    for name, got, want, passed in checks:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}: {got} (want {want})")
    print(f"\n{'PASS' if ok else 'FAIL'} · {results} · {report}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
