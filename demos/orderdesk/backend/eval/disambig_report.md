# Disambiguation quality — real-model eval

`gemini-3.1-flash-lite` · 80 trials over 20 families (944 eligible in the catalog) · 193 model calls · 386.2s · seed 20260803

- Candidate sets: **search.py / catalog.db**
- Prompt fragment: **brain.py :: _INSTRUCTION (DISAMBIGUATION section)**
- Generated: 2026-08-03T11:38:30+00:00

## Verdict

**PASS** against DESIGN §7-bis.

| gate | measured | threshold | |
| --- | --- | --- | --- |
| choice-set validity | 100.0% | ≥ 98% | PASS |
| average rounds | 1.363 | ≤ 2.0 | PASS |
| max rounds | 3 | ≤ 3 | PASS |
| coverage failures | 0 | 0 | PASS |

## Aggregate

| metric | value |
| --- | --- |
| trials | 80 |
| choice sets | 109 |
| validity | 1.0 |
| repairs | 0 |
| repairs that worked | 0 |
| success rate | 1.0 |
| avg rounds | 1.363 |
| avg rounds successful | 1.363 |
| max rounds | 3 |
| avg excess over bound | 0.062 |
| at or under bound | 70 |
| avg balance | 1.394 |
| median balance | 1.333 |
| worst balance | 2.0 |
| coverage failures | 0 |

Outcomes: `success` 80

Question-text flags: none.

## Per family

| family | SKUs | bucket | trials | success | avg rounds | bound | avg balance | validity |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `TELMA` | 26 | 16+ | 4 | 4/4 | 2.25 | 2 | 1.25 | 9/9 |
| `DERMADEW` | 25 | 16+ | 4 | 4/4 | 2.25 | 2 | 1.39 | 9/9 |
| `GLIMESTAR` | 21 | 16+ | 4 | 4/4 | 1.75 | 2 | 1.55 | 7/7 |
| `FORACORT` | 18 | 16+ | 4 | 4/4 | 1.75 | 2 | 1.39 | 7/7 |
| `TAXIM` | 18 | 16+ | 4 | 4/4 | 1.25 | 2 | 1.93 | 5/5 |
| `SHELCAL` | 17 | 16+ | 4 | 4/4 | 2.00 | 2 | 1.32 | 8/8 |
| `GLYCOMET` | 16 | 16+ | 4 | 4/4 | 1.75 | 1 | 1.30 | 7/7 |
| `CEFOLAC` | 12 | 9-15 | 4 | 4/4 | 1.75 | 1 | 1.49 | 7/7 |
| `MOX` | 11 | 9-15 | 4 | 4/4 | 1.00 | 1 | 1.36 | 4/4 |
| `SALBAIR` | 11 | 9-15 | 4 | 4/4 | 1.00 | 1 | 1.46 | 4/4 |
| `METROGYL` | 10 | 9-15 | 4 | 4/4 | 1.00 | 1 | 1.60 | 4/4 |
| `NEXPRO` | 10 | 9-15 | 4 | 4/4 | 1.00 | 1 | 1.20 | 4/4 |
| `PAN` | 10 | 9-15 | 4 | 4/4 | 1.00 | 1 | 1.20 | 4/4 |
| `VOLINI` | 10 | 9-15 | 4 | 4/4 | 1.50 | 1 | 1.73 | 6/6 |
| `THYRONORM` | 8 | 5-8 | 4 | 4/4 | 1.00 | 1 | 1.12 | 4/4 |
| `4 QUIN` | 6 | 5-8 | 4 | 4/4 | 1.00 | 1 | 1.33 | 4/4 |
| `WIKORYL` | 6 | 5-8 | 4 | 4/4 | 1.00 | 1 | 1.50 | 4/4 |
| `DAPASACH` | 5 | 5-8 | 4 | 4/4 | 1.00 | 1 | 1.20 | 4/4 |
| `GFH` | 5 | 5-8 | 4 | 4/4 | 1.00 | 1 | 1.20 | 4/4 |
| `STARVOG` | 5 | 5-8 | 4 | 4/4 | 1.00 | 1 | 1.20 | 4/4 |

## Failures (0)

None — every trial narrowed to ≤4 candidates with the target still on screen.

## Worst five trials

- `VOLINI` (n=10, target PROD4927) — **success** in 2 round(s) vs bound 1, worst balance 2.0. no hard error — cost only.
- `VOLINI` (n=10, target J0051923) — **success** in 2 round(s) vs bound 1, worst balance 2.0. no hard error — cost only.
- `DERMADEW` (n=25, target J0009553) — **success** in 3 round(s) vs bound 2, worst balance 1.75. no hard error — cost only.
- `CEFOLAC` (n=12, target J0040893) — **success** in 2 round(s) vs bound 1, worst balance 1.75. no hard error — cost only.
- `CEFOLAC` (n=12, target J0006886) — **success** in 2 round(s) vs bound 1, worst balance 1.75. no hard error — cost only.

## Transcripts

#### `TELMA` — 26 SKUs, hidden target **J0031280** (TELMA AM TABLET)

Candidate table handed to the model:

```
code      name                            variant   form    strength       pack  mrp
J0031267  TELMA 20 TABLET                 -         TABLET  20             15'S  60.74
J0031270  TELMA 40 TABLET                 -         TABLET  40             15'S  106.47
J0031274  TELMA 80 TABLET                 -         TABLET  80             15'S  163.16
J0031276  TELMA ACT 40/5/6.25 TABLET      ACT       TABLET  40/5/6.25      15'S  184.68
J0031280  TELMA AM TABLET                 AM        TABLET  -              15'S  315.47
J0031283  TELMA AMH 40 TABLET             AMH       TABLET  40             15'S  313.59
J0031284  TELMA AMH 80 TABLET             AMH       TABLET  80             15'S  430.78
J0051763  TELMA-AZ TABLET                 AZ        TABLET  -              10'S  174.37
J0031286  TELMA 80-AZ TABLET              AZ        TABLET  80             10'S  196.41
J0031288  TELMA BETA 25 TABLET            BETA      TABLET  25             10'S  238.12
PROD7131  TELMA BETA AM TABLET            BETA AM   TABLET  -              10'S  162
J0050848  TELMA-BS 5 MG TABLET            BS        TABLET  5 MG           10'S  140.63
J0031293  TELMA CT 40/12.5 TABLET         CT        TABLET  40/12.5        15'S  303.28
J0031294  TELMA CT 40/6.25 TABLET         CT        TABLET  40/6.25        15'S  279.38
J0031297  TELMA CT 80/6.25 TABLET         CT        TABLET  80/6.25        15'S  451.41
J0031299  TELMA D TABLET                  D         TABLET  -              10'S  163.13
J0031305  TELMA H TABLET                  H         TABLET  -              15'S  344.53
J0031301  TELMA 80 H TABLET               H         TABLET  80             15'S  492.19
J0031307  TELMA LN 40 TABLET              LN        TABLET  40             15'S  286.41
PROD7138  TELMA LN 40/20 MG TABLET        LN        TABLET  40/20 MG       15'S  221.25
J0031308  TELMA LN 80 TABLET              LN        TABLET  80             15'S  470.16
PROD6455  TELMA LNB 25 MG TABLET          LNB       TABLET  25 MG          15'S  191.25
PROD4215  TELMA MCT 6.25/25/40 MG TABLET  MCT       TABLET  6.25/25/40 MG  10'S  135.94
J0043070  TELMA MCT 25/12.5 TABLET        MCT       TABLET  25/12.5        10'S  161.72
J0043071  TELMA MCT 50/12.5 TABLET        MCT       TABLET  50/12.5        10'S  192.19
PROD4001  TELMA MCT 50 6.25 TABLET        MCT 6.25  TABLET  50             10'S  135.93
```

**Round 1** — 26 candidates

> Which Telma line?

- **Plain Telma** (3): J0031267, J0031270, J0031274
- **Telma AM / AMH / AZ / BETA** (8): J0031280, J0031283, J0031284, J0051763, J0031286, J0031288… ← pharmacist taps this
- **Telma CT / H / D** (6): J0031293, J0031294, J0031297, J0031299, J0031305, J0031301
- **Telma LN / LNB / MCT** (9): J0031307, PROD7138, J0031308, PROD6455, PROD4215, J0043070…

balance 1.385 · narrows to 8

**Round 2** — 8 candidates

> Which variant?

- **Telma AM / AMH** (3): J0031280, J0031283, J0031284 ← pharmacist taps this
- **Telma AZ / BS** (3): J0051763, J0031286, J0050848
- **Telma BETA / BETA AM** (2): J0031288, PROD7131

balance 1.125 · narrows to 3

**Outcome:** success in 2 round(s) (bound 2); left on screen: J0031280, J0031283, J0031284

#### `VOLINI` — 10 SKUs, hidden target **PROD1551** (VOLINI SPRAY)

Candidate table handed to the model:

```
code      name                      variant      form   strength  pack     mrp
J0034539  VOLINI GEL                -            GEL    -         75 GM    272
J0034534  VOLINI GEL                -            GEL    -         100 GM   349
PROD1551  VOLINI SPRAY              -            SPRAY  -         1×42 GM  175
J0051604  VOLINI JOINT XPERT GEL    JOINT XPERT  GEL    -         20 GM    97.5
J0044262  VOLINI JOINT XPERT GEL    JOINT XPERT  GEL    -         50 GM    225
J0051923  VOLINI MAXX SPRAY         MAXX         SPRAY  -         25 GM    110
PROD4392  VOLINI MAXX SPRAY         MAXX         SPRAY  -         55 GM    243
PROD2856  VOLINI PAIN RELIEF GEL    PAIN RELIEF  GEL    -         12 GM    50
PROD2699  VOLINI PAIN RELIEF GEL    PAIN RELIEF  GEL    -         20 GM    103.13
PROD4927  VOLINI PAIN RELIEF SPRAY  PAIN RELIEF  SPRAY  -         62 GM    233
```

**Round 1** — 10 candidates

> Which Volini variant?

- **Volini Gel (Standard)** (2): J0034539, J0034534
- **Volini Spray (Standard)** (1): PROD1551 ← pharmacist taps this
- **Volini Joint Xpert Gel** (2): J0051604, J0044262
- **Volini Maxx or Pain Relief variants** (5): J0051923, PROD4392, PROD2856, PROD2699, PROD4927

balance 2.0 · narrows to 1

**Outcome:** success in 1 round(s) (bound 1); left on screen: PROD1551

#### `4 QUIN` — 6 SKUs, hidden target **J0037800** (4 QUIN EYE OINTMENT)

Candidate table handed to the model:

```
code      name                   variant  form          strength  pack  mrp
J0002080  4 QUIN EYE DROPS       -        EYE DROPS     -         5 ML  160.31
J0037800  4 QUIN EYE OINTMENT    -        EYE OINTMENT  -         5 GM  141.56
J0050198  4 QUIN-BROM EYE DROPS  BROM     EYE DROPS     -         5 ML  181.88
J0002079  4 QUIN-D EYE DROPS     D        EYE DROPS     -         5 ML  112.5
PROD3873  4 QUIN KT EYE DROPS    KT       EYE DROPS     -         5 ML  135
PROD3865  4 QUIN LOT EYE DROPS   LOT      EYE DROPS     -         5 ML  225.94
```

**Round 1** — 6 candidates

> Which 4 Quin variant?

- **Plain 4 Quin** (2): J0002080, J0037800 ← pharmacist taps this
- **4 Quin with additives (Brom/D/KT/Lot)** (4): J0050198, J0002079, PROD3873, PROD3865

balance 1.333 · narrows to 2

**Outcome:** success in 1 round(s) (bound 1); left on screen: J0002080, J0037800

