# Phonetic search eval — orderdesk catalog

1258 romanizations · 600 variants · 4 corpus files · 3.1s

No LLM in this loop — every romanized string goes straight to `search.resolve()`. Tiers: **T1** exact SKU (or right family when the entry only expects a family), **T2** right family surfaced some other way (matched-wrong-sku, multi_variant, multi_family, or the sku code present among returned variants), **T3** a near-family neighbour came back in a multi_family result but not the right one, **MISS** nothing useful. Pass = T1 + T2.

## Headline

| level | total | T1 | T2 | T3 | MISS | pass (T1+T2) |
| --- | --- | --- | --- | --- | --- | --- |
| per-romanization (strict) | 1258 | 556 | 546 | 2 | 154 | **87.6%** |
| per-variant (any romanization) | 600 | 370 | 229 | 0 | 1 | **99.8%** |

## Per bucket

| bucket | variants | var pass | rom | rom pass |
| --- | --- | --- | --- | --- |
| `dentals-aspiration-numbers` | 150 | 100.0% | 315 | 88.9% |
| `sibilants-zjxq-phf` | 150 | 100.0% | 346 | 85.3% |
| `vowels-compounds-suffixes` | 150 | 100.0% | 296 | 81.1% |
| `vw-vowels-clusters` | 150 | 99.3% | 301 | 95.3% |

## Full failure table (1 variants at T3/MISS)

| bucket | family | sku | devanagari | romanizations tried | best tier | what came back |
| --- | --- | --- | --- | --- | --- | --- |
| vw-vowels-clusters | ZOCON | J0036014 | सोकॉन | `socon`; `sokaun` | MISS | `socon`→not_found; `sokaun`→not_found |

## Tuning targets — failures grouped by root cause

Tags are heuristic groupings (a variant can carry more than one), each grounded in a specific place `normalize.py` does or doesn't handle the pattern. See the module docstrings for `search_text`, `phonetic_key`, and `spoken_numbers`.

### `single-letter-substitution (J↔S not folded by _SINGLES/_DIGRAPHS)` — 1 variant(s)

- `सोकॉन` → `socon`, `sokaun` (expected ZOCON / J0036014)

