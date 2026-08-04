# `orderdesk/backend/eval/` — the two make-or-break evals

OrderDesk lives or dies on two things a demo script cannot fake:

1. **Recall** — a Hindi speaker says "वोलिनी" and the ASR hands us `wolini`, `volaini`,
   `bolini`. Does the catalog still find it? → `run_phonetic_eval.py`
2. **Disambiguation quality** — "टेल्मा" matches 26 SKUs. Does the model ask the *sharpest*
   question, or does it read a list? → `disambig_eval.py` (DESIGN §7-bis)

Both run against the shipping `catalog.db` and the shipping code — no fixtures of
convenience. Each has a cheap tripwire in `demos/tests/` so a regression fails CI before it
fails on stage.

| eval | runner | artifacts | tripwire |
| --- | --- | --- | --- |
| phonetic recall | `run_phonetic_eval.py` | `corpus_p*.json`, `phonetic_results.json`, `phonetic_report.md` | `tests/test_orderdesk_phonetics.py` |
| disambiguation | `disambig_eval.py` | `disambig_results.json`, `disambig_report.md` | `tests/test_orderdesk_disambig.py` |

---

## `disambig_eval.py` — is the question sharp?

The naive UX for 26 matches is 26 pills. §7-bis says we never do that: at ≥5 candidates the
tool result hands the model a compact candidate table and the model must call
`ask_choice(question, choices)`; the brain then validates 2–4 choices, every code known, the
union covering every candidate.

This harness replays that exact loop against the **real** `gemini-3.1-flash-lite` — same
prompt fragment the brain ships, same tool declaration — with a deterministic oracle in the
pharmacist's chair.

**The loop.** A family with N ≥ 5 SKUs and one hidden target. The model sees the table and
asks. The oracle taps the choice that still holds the target (the *smallest* such choice, so
the model gets no credit for a lazy catch-all). Candidates narrow to that group and the model
is asked again — until ≤4 remain (the screen takes over with leaf pills) or three rounds are
spent. A target that sits in **no** choice is a coverage failure: the pharmacist's product
fell off the screen, and that is the one outcome the demo cannot survive.

**Candidate sets** come from `search.skus_in_family()` over `catalog.db` — every family with
≥5 SKUs (944 of them). A seeded, stratified sample takes 20 across the three size buckets
(5–8, 9–15, 16+), always including the families DESIGN names by hand (TELMA, GLYCOMET,
SHELCAL, VOLINI, PAN, MOX, THYRONORM, 4 QUIN) so the report's transcripts are checkable
against the demo script. Four hidden targets per family, spread across distinct variants.
If `search.py`/`catalog.db` are missing the harness falls back to grouping
`data/enterro_products.csv` by brand root and says so in the report header.

**The prompt fragment** is extracted from `brain.py` at run time — the DISAMBIGUATION section
of `_INSTRUCTION`, parsed with `ast` rather than imported (the brain pulls in the SDK and the
ADK; the eval must not). If the section is absent the harness uses its own §7-bis-faithful
fallback, and the report names which one was used. *This matters:* the eval measures the
prompt the demo actually ships, so tightening the prompt shows up here immediately.

### What is measured

| metric | meaning |
| --- | --- |
| **validity** | 2–4 choices, every `sku_code` in the current candidate set, the union covering all of them — first attempt. A rejected set gets one repair round (the brain's retriable tool error), counted separately. |
| **rounds-to-≤4** | against the information bound `ceil(log4(N/4))`. 26 SKUs = 2 rounds if the split is perfect. |
| **balance** | `largest_group / (N / num_choices)`. 1.0 is a perfectly even partition; 3.0 means one pill swallowed the list and the answer eliminated nothing. |
| **question text** | empty / overlong / duplicated labels, SKU codes leaking into pill text, questions too long to say aloud. |
| **coverage failures** | the target was in no choice. Must be zero. |

### Thresholds (DESIGN §7-bis — these gate the demo)

validity ≥ 98% · average rounds ≤ 2 · max rounds 3 · zero coverage failures.

### Running it

```bash
cd demos
set -a; source ~/apps/voqalcloud/.env; set +a   # GEMINI_API_KEY
uv run python orderdesk/backend/eval/disambig_eval.py
```

≈190 model calls, ~6 minutes, exit 0 only if every gate passes. Writes
`disambig_results.json` (every trial, every round, every choice set) and
`disambig_report.md` (verdict, aggregates, per-family table, failure table, worst five
trials, and three full transcripts — one 16+ family, one 9–15, one 5–6).

Useful flags: `--families N --targets N` to shrink the sweep, `--workers N` and `--rpm N` if
the key is rate-limited (the harness paces itself, retries 429/5xx with backoff, and sweeps
any rate-limited trial again serially at the end — a transport failure is a hole in the
dataset, not a finding about the model).

### The tripwire

`demos/tests/test_orderdesk_disambig.py` has two halves. The offline half tests the harness's
own arithmetic — validation, the oracle, the log₄ bound, the seeded sample, and the CSV
fallback's family sizes against `catalog.db` — so a bug in the *measurement* can never
quietly pass the *measurement*. The live half runs six trials
(TELMA 26, VOLINI 10, THYRONORM 8 × two targets, ~10 calls, ~11s) against the same
thresholds, and **skips** cleanly when there is no `GEMINI_API_KEY`. The full sweep stays
behind `__main__` so CI stays cheap.

---

## `run_phonetic_eval.py` — does the catalog find it at all?

No LLM in that loop: ~600 hand-built Devanagari variants of real SKUs, each with several
plausible romanizations, go straight into `search.resolve()`. Corpus in `corpus_p*.json`,
headline and per-bucket breakdown in `phonetic_report.md`. See that report and the runner's
docstring for its tiers and floors.
