# Adversarial phonetic eval — orderdesk catalog

450 held-out variants · 20 traps · 150-variant in-sample control · **Gemini column PENDING** (see the banner below) · 4s

> ## ⚠ PARTIAL RUN — the production-path column is not measured yet
> 
> The romanizer column needs ~620 calls to `gemini-3.1-flash-lite`. Google's free tier meters that model at **500 requests per project per day**, and this project's daily bucket was already spent when the run started — the two other keys on this machine are IP-restricted and Vertex AI is not enabled on `voqal-cloud-dev`, so there was no second bucket to rotate into.
> 
> **What IS measured below, and is real:** the strict three-way scoring on both held-out adversarial corpora using the corpus authors' own `romanized[]` strings, the traps, and the old-method number on the original corpus. That is the *generalization* half of the honesty story — held-out vs in-sample — with the *romanization* half still outstanding.
> 
> **What is NOT measured:** anything that needs the LLM to write the search string. Those cells say `pending`, never a borrowed number. Because the authors' strings are best-of-two and written by someone who already knew the answer, every figure below is an **upper bound** on what the Gemini column will show — the opposite direction of error from the usual caveat, and the reason the missing column matters.
> 
> **To finish it** (the romanization cache makes it resumable — it already holds what landed):
> 
> ```
> cd demos && set -a && source ~/apps/voqalcloud/.env && set +a && \
>     uv run python orderdesk/backend/eval/run_adversarial_eval.py
> ```
> 
> Quota resets at midnight US-Pacific. `GEMINI_API_KEYS` accepts a comma-separated list if more than one project's key is available.

## What this measures that the 99.5% didn't

The earlier `phonetic_report.md` number is a **fit** statistic with two holes. This run closes both.

1. **In-sample tuning.** `corpus_p1..p4` are the corpora `normalize.py`'s alternate-key round was tuned against. `adv_corpus_r1` (hostile-pharmacist phrasings) and `adv_corpus_r2` (STT decoder damage) were written afterwards, against the engine's documented mechanisms, and never tuned against.
2. **Author-friendly romanizations.** The old harness fed the corpus authors' own `romanized[]` strings to `resolve()` and passed a variant if *any* of them landed. Production has one romanizer: the LLM, reading a Devanagari transcript and writing one English search string. Here every variant's Devanagari goes to `gemini-3.1-flash-lite` with a prompt distilled from `brain.py`'s *LANGUAGE — TOOL ARGUMENTS ARE ENGLISH, ALWAYS* section, and that **single** string is what `resolve()` sees.

> **These numbers are a floor.** The romanizer here gets no PHARMACY CONTEXT — no order history, no usual items. Production gives the model both, and a model that already knows this store buys MONTAIR every month reads `मोंटियर` differently. Read every figure below as a conservative lower bound on the deployed system.

### Verdicts

| verdict | meaning | what the pharmacist experiences |
| --- | --- | --- |
| **PASS** | the right family surfaced (matched / multi_variant on it, or it is in the multi_family list) | the row locks, or one short question locks it |
| **ASK_OK** | `not_found`, or a low-confidence `multi_family` without the right family and **no** wrong match ≥ 0.5 | the agent says it didn't find it and asks again — one lost turn |
| **WRONG** | matched / multi_variant on the **wrong family** at any confidence, or multi_family ranking a wrong family first at ≥ 0.5 | a different drug lands on the order, and the agent sounds sure |

ASK_OK is never counted as a pass. WRONG is the number a pharmacy cares about.

## 1. The triangulation

| measurement | corpus | romanizer | scoring | n | PASS | ASK_OK | WRONG |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **A. the old 99.5% method** | original p1–p4 (tuned on) | authors' `romanized[]`, best-of | family surfaced | 600 | **99.8%** | – | – |
| A′. same method, same sample | original p1–p4 sample | authors' `romanized[]`, best-of | old T1/T2 | 150 | **100.0%** | – | – |
| A″. same corpus, strict scoring | original p1–p4 (tuned on) | authors' `romanized[]`, best-of | strict 3-way | 600 | **95.8%** | – | – |
| **B. in-sample, production path** | original p1–p4 sample (seed 20260803) | Gemini, one string | strict 3-way | 150 | *pending* | *pending* | *pending* |
| **C. held-out, production path** | adversarial r1+r2 | Gemini, one string | strict 3-way | 450 | *pending* | *pending* | *pending* |
| C′. held-out, authors' strings | adversarial r1+r2 | authors' `romanized[]`, best-of | strict 3-way | 450 | **82.7%** | 16.9% | **0.4%** |

What the two measurable rows already say:

- **A″ → C′ (95.8% → 82.7%) is the generalization gap, measured cleanly.** Both rows use the *same* romanizer (the authors' strings, best-of) and the *same* strict scoring. The only variable is which corpus: the one the engine was tuned against, versus the one written afterwards to attack its documented mechanisms. Nothing about the LLM is involved in this comparison, which is exactly why it survives the missing column.
- **C′'s WRONG rate is 0.4% (2/450) on the authors' own best-of-two strings.** These are the charitable romanizations. The pharmacy-relevant number therefore starts here and can only get worse once one LLM reading replaces best-of-two.
- **A → A″ (99.8% → 95.8%) is the scoring gap, on the tuned corpus alone.** Nothing changed but the rule. The old T1/T2 bar counted a pass whenever the expected SKU appeared anywhere in the returned variant list — including inside a *confident `multi_variant` on a different family*, which on a real order desk is a different drug on the screen. Strict scoring calls those WRONG.
- **Rows B and C stay empty on purpose.** Substituting the authors' number for the model's would reproduce precisely the dishonesty this eval was built to remove.

## 2. Per corpus — strict three-way, the corpus authors' `romanized[]`, best-of (**not** the production path)

| corpus | lens | n | PASS | ASK_OK | **WRONG** | wrong count |
| --- | --- | --- | --- | --- | --- | --- |
| `adv_corpus_r1.json` | hostile-pharmacist | 225 | 85.8% | 14.2% | **0.0%** | 0 |
| `adv_corpus_r2.json` | stt-damage | 225 | 79.6% | 19.6% | **0.9%** | 2 |

## 3. Per attack class

Sorted by WRONG rate — the top of this table is the fix list's evidence. Column: the corpus authors' `romanized[]`, best-of (**not** the production path).

| attack class | n | PASS | ASK_OK | **WRONG** | wrong count |
| --- | --- | --- | --- | --- | --- |
| `3-truncation` | 45 | 55.6% | 42.2% | **2.2%** | 1 |
| `5-confidence-collapse` | 45 | 62.2% | 35.6% | **2.2%** | 1 |
| `1-real-word-capture` | 45 | 91.1% | 8.9% | **0.0%** | 0 |
| `2-boundary-destruction` | 45 | 97.8% | 2.2% | **0.0%** | 0 |
| `4-matra-error` | 45 | 91.1% | 8.9% | **0.0%** | 0 |
| `dialect-vowel-damage` | 44 | 86.4% | 13.6% | **0.0%** | 0 |
| `fused-filler-tail` | 38 | 76.3% | 23.7% | **0.0%** | 0 |
| `hindi-form-word-only` | 35 | 100.0% | 0.0% | **0.0%** | 0 |
| `hindi-word-substitution` | 34 | 82.3% | 17.6% | **0.0%** | 0 |
| `dropped-syllable-nasal` | 28 | 78.6% | 21.4% | **0.0%** | 0 |
| `wrong-boundary-split` | 17 | 82.3% | 17.6% | **0.0%** | 0 |
| `strength-misattached` | 8 | 100.0% | 0.0% | **0.0%** | 0 |
| `brand-digit-fusion` | 7 | 100.0% | 0.0% | **0.0%** | 0 |
| `bv-fold-collision` | 7 | 100.0% | 0.0% | **0.0%** | 0 |
| `wrong-boundary-fusion` | 7 | 71.4% | 28.6% | **0.0%** | 0 |

## 4. Traps — 19/20 pass

`absent` (8): a brand a pharmacist really says that is **not in this catalog**. Pass = `not_found`, or nothing at ≥ 0.5. `collision` (12): a real catalog brand with a near-twin. Pass = the target surfaced **and** the twin did not outrank it.

*(Romanizer for this section: the corpus authors' first `romanized[]` string, because the Gemini column is pending. One fixed plausible reading per trap — the traps ask what the catalog does with such a reading, and that question is answerable either way.)*

| kind | said (Devanagari) | searched for | expected | got | verdict | severity |
| --- | --- | --- | --- | --- | --- | --- |
| absent | ज़िनटैक डेढ़ सौ दे दो | `zinetac dedh sau de do` | nothing confident | multi_family at 0.32 — nothing confident | PASS | – |
| absent | डेकड्रान की गोली चाहिए | `decdan ki goli chahiye` | nothing confident | not_found at 0.0 — nothing confident | PASS | – |
| absent | ज़ंडू बाम दे दो | `zandu balm de do` | nothing confident | not_found at 0.0 — nothing confident | PASS | – |
| absent | अल्ट्रासेट की गोली दे दीजिए | `ultracet ki goli de dijiye` | nothing confident (not ULTRACID) | multi_family at 0.32 — nothing confident | PASS | – |
| absent | कोल्डारिन वाली गोली | `coldarin wali goli` | nothing confident (not CALADRYL) | multi_family at 0.32 — nothing confident | PASS | – |
| absent | साइनेक्स नाक वाला स्प्रे | `sinex naak wala spray` | nothing confident (not R CINEX) | multi_family at 0.32 — nothing confident | PASS | – |
| absent | निमुलिड दे दो दर्द वाली | `nimulid de do dard wali` | nothing confident (not NUMLO) | not_found at 0.0 — nothing confident | PASS | – |
| absent | अल्कासोल की शीशी दे दो | `alkasol ki sheeshi de do` | nothing confident | multi_family at 0.32 — nothing confident | PASS | – |
| collision | सीनॉड दस वाली गोली दे दो | `seenod das wali goli de do` | CINOD (not CANDID) | multi_variant on CINOD | PASS | – |
| collision | सेंसोडीन वाला मंजन दे दो | `sensodeen wala manjan de do` | SENSODYNE (not SENSODENT) | multi_family lists SENSODYNE at #1 | PASS | – |
| collision | ग्लाइसीनॉर्म ओडी साठ | `glycinorm od saath` | GLYCINORM (not GLUCONORM) | matched on GLYCINORM | PASS | – |
| collision | रोज़ूवास दस वाली गोली | `rozoovas das wali goli` | ROSUVAS (not ROSUWISE) | multi_family lists ROSUVAS at #1 | PASS | – |
| collision | ओरटील पाँच सौ | `orateel paanch sau` | ORATIL (not ERITEL) | multi_variant on ORATIL | PASS | – |
| collision | अटरैक्स पच्चीस | `ataraks pachchees` | ATARAX (not EUTHYROX) | matched on ATARAX | PASS | – |
| collision | इमीसेट एमडी चार दे दो | `imeeset emdee char de do` | EMESET (not EMSITA) | multi_family lists EMESET at #2 | PASS | – |
| collision | अक्सिटोल तीन सौ | `aksitol teen sau` | OXETOL (not ECITELO) | multi_family ['BACSTOL', 'ARACHITOL', 'ACCSTOP', 'ACNESOL', 'ACUTROL'] — OXETOL absent | **FAIL** | **medium** |
| collision | कार्डिबास सवा तीन एमजी | `kardibas sawa teen mg` | CARDIVAS (not CARDIBIS) | multi_family lists CARDIVAS at #1 | PASS | – |
| collision | अस्कोरील एलएस खाँसी की दवा | `askoreel els khansi ki dawa` | ASCORIL (not ISRYL) | multi_family lists ASCORIL at #1 | PASS | – |
| collision | नोवामाक्स दो सौ पचास की शीशी | `novamaks do sau pachas ki sheeshi` | NOVAMOX (not NOVOMIX) | multi_family lists NOVAMOX at #1 | PASS | – |
| collision | असोमेक्स ढाई वाली गोली | `asomeks dhai wali goli` | ASOMEX (not ESOMAC) | matched on ASOMEX | PASS | – |

**Failing traps by severity:** medium × 1


### The SINEX → R CINEX class

**Not reproduced on this run** — `sinex naak wala spray` → multi_family at 0.32 — nothing confident. The class stays on the watch list: it is a key-neighbourhood collision between a nasal spray and a TB combination, and the mechanisms that produced it (flat `_PHON_BREADTH`, constant `_CONFIDENCE`) are unchanged. The romanization the model happened to write is what saved it, and that is not a property the engine guarantees.

## 5. The ten worst confident-wrong results

Ordered by the confidence the engine reported. Each of these is a row that turns green on the pharmacist's screen carrying a drug nobody asked for. Column: the corpus authors' `romanized[]`, best-of (**not** the production path).

| # | said (Devanagari) | searched for | wanted | got | conf | attack |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | मेथी ताल | `methi taal` | MEFTAL | matched → METITAL (METITAL TABLET) | **0.62** | `5-confidence-collapse` |
| 2 | वोलिन | `volin` | LEVOLIN | multi_variant → VOLINI | **0.62** | `3-truncation` |

## 6. Fix priority

Ordered by severity × frequency, where frequency is the WRONG + ASK_OK volume in the attack classes each mechanism owns (WRONG double-weighted). Every item names the exact code that produces the behaviour. Frequencies from: the corpus authors' `romanized[]`, best-of (**not** the production path). These are the *charitable* frequencies; the Gemini column can only move volume up, and the ordering is unlikely to change because it is driven by which mechanism owns which attack class, not by the absolute counts.

| # | fix | mechanism | owns (attack classes) | wrong | wrong+ask | score |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **Leading-token FTS short-circuit hands the query to the wrong brand before phonetics runs** | `search.py `_gather` / `_fts_relaxed` (the `words[:cut]` tail-drop loop)` | `1-real-word-capture`, `3-truncation`, `hindi-word-substitution`, `2-boundary-destruction`, `wrong-boundary-split` | 1 | 34 | 108 |
| 2 | **Confidence is a per-stage constant — no coverage or length discipline** | `search.py `_CONFIDENCE` (a 9-cell lookup on `(stage, status)`)` | `5-confidence-collapse`, `1-real-word-capture`, `hindi-word-substitution` | 1 | 27 | 87 |
| 3 | **The ±1 key-length window is too tight for syllable loss and too loose for short keys** | `search.py `_phonetic_families` (`abs(len(row['key']) - len(key)) > 1`)` | `dropped-syllable-nasal`, `3-truncation`, `4-matra-error` | 1 | 30 | 64 |
| 4 | **Hindi form words pollute the query and `_FAMILY_HEAD` is forfeited** | `normalize.py `FORM_WORDS` + search.py `_score`'s `_FAMILY_HEAD`` | `hindi-form-word-only`, `hindi-word-substitution`, `fused-filler-tail` | 0 | 15 | 30 |
| 5 | **Hindi numerals and spoken suffixes are never unfolded** | `normalize.py `spoken_numbers` (English number words only)` | `fused-filler-tail`, `strength-misattached`, `dialect-vowel-damage` | 0 | 15 | 30 |
| 6 | **Short, deep families act as attractors under `_PHON_BREADTH`** | `search.py `_phonetic_families` (`_PHON_BREADTH * min(1, count/8)`)` | `bv-fold-collision`, `1-real-word-capture`, `dialect-vowel-damage` | 0 | 10 | 20 |
| 7 | **`_parse_query`'s `tok.isalpha()` gate drops every digit-fused brand token** | `search.py `_parse_query` (the `brandish` filter)` | `brand-digit-fusion`, `2-boundary-destruction`, `strength-misattached` | 0 | 1 | 3 |

### 1. Leading-token FTS short-circuit hands the query to the wrong brand before phonetics runs

*search.py `_gather` / `_fts_relaxed` (the `words[:cut]` tail-drop loop)*

`_gather` stops at the first stage that returns rows, and `_fts_relaxed` keeps cutting the query down until *something* matches — including down to the first word alone. A damaged brand whose first three letters happen to prefix an unrelated catalog token wins on that prefix, the phonetic stage never runs, and the result is a confident `matched`/`multi_variant` (0.82/0.62) on a brand that was never said. This is the single biggest manufacturer of WRONG (as opposed to ASK_OK) results. Fix: require the surviving cut to explain a real share of the query, and merge the FTS and phonetic candidate pools rather than short-circuiting.

### 2. Confidence is a per-stage constant — no coverage or length discipline

*search.py `_CONFIDENCE` (a 9-cell lookup on `(stage, status)`)*

Every `fts`+`matched` result is 0.82 whether the query explained the whole name or one three-letter prefix of it; every `phonetic`+`matched` is 0.62 whether the spelling similarity was 0.95 or the 0.45 floor. The engine cannot express doubt, so the brain cannot ask instead of guessing — this is what converts near-misses into WRONG instead of ASK_OK. Fix: multiply the stage constant by a coverage term (explained tokens / query tokens) and by the realized phonetic similarity, and let the brain's ask-again path trigger below a threshold.

### 3. The ±1 key-length window is too tight for syllable loss and too loose for short keys

*search.py `_phonetic_families` (`abs(len(row['key']) - len(key)) > 1`)*

A dropped nasal or an elided medial syllable moves the phonetic key by two characters (`MNTR`→`MTR`→`MT`), which the window rejects outright — the right family is never even scored. Meanwhile a 2-character key inside the window reaches half the catalog. Fix: make the window proportional to key length, and gate short keys on the spelling-similarity floor instead of on length alone.

### 4. Hindi form words pollute the query and `_FAMILY_HEAD` is forfeited

*normalize.py `FORM_WORDS` + search.py `_score`'s `_FAMILY_HEAD`*

`FORM_WORDS` is an English list: `goli`, `tikiya`, `shishi`, `manjan`, `sheeshi`, `dawa` are not in it, so they stay in `q.tokens`, each costs `_MISS`, and — worse — when the Hindi word lands *first* (`goli wala rantac`) the `_FAMILY_HEAD` +8 that separates the right family from its neighbours is forfeited because `q.tokens[:1]` no longer holds the brand. Fix: extend `FORM_WORDS` with the Hindi/romanized form and filler vocabulary, and test `_FAMILY_HEAD` against any leading *brandish* token rather than token 0.

### 5. Hindi numerals and spoken suffixes are never unfolded

*normalize.py `spoken_numbers` (English number words only)*

`spoken_numbers` knows `forty`→40 but not `chalis`, `dedh sau`, `sawa`, `dhai`, `pachees`. A Hindi-spoken strength therefore survives as an unexplainable word token and is charged `_MISS` (-6) against the very SKU it identifies, while `_STRENGTH_HIT` (+12) is never paid. Fix: a Hindi numeral table (including the fractional forms सवा/डेढ़/ढाई) folded in `spoken_numbers`, which `resolve()` already tries as a second pass.

### 6. Short, deep families act as attractors under `_PHON_BREADTH`

*search.py `_phonetic_families` (`_PHON_BREADTH * min(1, count/8)`)*

Breadth pays up to +12 for a family with eight or more SKUs, independent of how well the token actually matched. A short-keyed deep brand therefore outranks a long-keyed exact-ish one, which is the mechanism behind the absent-brand traps landing on real catalog brands. Fix: scale breadth by the similarity that earned the candidacy (`_PHON_SIM * sim` already computed) instead of adding it flat.

### 7. `_parse_query`'s `tok.isalpha()` gate drops every digit-fused brand token

*search.py `_parse_query` (the `brandish` filter)*

`brandish` keeps only tokens where `len(tok) >= 3 and tok.isalpha()`. A brand the STT fused with its strength — `montair10`, `pan40`, `telma40` — fails `isalpha()` and never reaches the phonetic stage at all, so the misheard-brand net that the whole design leans on is simply not run. Fix: split a trailing/leading digit run off the token and probe the alpha stem (the digits are already carried by `measures`).

## 7. What is deliberately not here

- **No pass-rate thresholds in CI yet.** `demos/tests/test_orderdesk_adversarial.py` tests the scorer's arithmetic offline and smoke-tests ten cached variants live; its floor assertions are `xfail`/skipped with a comment, to be armed after the fix round lands. Arming a threshold at today's measured number would freeze the bug in place as the spec.
- **No order history.** See the note at the top: production's PHARMACY CONTEXT would raise every PASS number here, and would raise it most on exactly the damaged-brand cases that fail. This eval measures the engine, not the deployed conversation.
- **One romanization per variant, temperature 0.** No best-of-n, no retry on a bad reading — production's English guard does force one retry, which this under-counts.

