# OrderDesk — B2B order intake over voice (pharma vertical)

Demo name: `orderdesk` (folder, URL `/demos/orderdesk`, brain `wss://brain.voqalize.com/orderdesk`).
In-app brand: **MedSetu** — "India's largest B2B pharma distributor". Marketing positioning is
*B2B order intake*; medicines are the vertical it's demonstrated on.

The pitch: a pharmacist gets a 9 AM push notification, joins a Hindi voice call, and rattles off
a bulk order. Every spoken line lands instantly as a free-text line item, resolves against a
**real 20,148-SKU sqlite catalog** (deterministic FTS + phonetic search — not mocked), and walks a
visible state machine to a confirmed SKU. Ambiguity becomes on-screen pills or one minimal verbal
question. The pharmacist confirms the order manually.

Patterns: sugar (persona picker, push-notification call start, per-session system prompt),
travel (AdkBrain + typed `Action` + `useUiCommand` + `state_sync` grounding),
legal (task-tray *feel* — but our resolution is real backend work, not client-paced fiction).

---

## 1. File ownership (build agents MUST stay in their lane)

| Owner | Files |
|---|---|
| A (catalog) | `data/enterro_products.csv`, `backend/build_catalog.py`, `backend/normalize.py`, `backend/search.py`, `backend/catalog.db`, `demos/tests/test_orderdesk_search.py` |
| B (brain) | `backend/brain.py`, `backend/routes.py`, `backend/__init__.py`, `demos/tests/test_orderdesk_brain.py` |
| C (frontend) | everything under `frontend/` EXCEPT `src/data.ts` and `src/types.ts` |
| D (scenarios) | `frontend/src/data.ts` ONLY |
| orchestrator | this file, `frontend/src/types.ts`, manifest/cloudbuild/seed wiring |

`frontend/src/types.ts` already exists (written by the orchestrator) — it is the single TS source
for every shared shape below. Import from it; do not redeclare.

---

## 2. Catalog & search (backend/search.py) — the deterministic core

Source CSV: `demos/orderdesk/data/enterro_products.csv` (20,148 rows). Columns of interest:
`Product_ID, Product_Code, Product_Name, MRP, PTR, Available_Stock, manufacture, Pack_Size, Scheme`.
`Product_Name` carries a trailing `-<CODE>` suffix — strip it (`re.sub(r'-[A-Z0-9]+$', '', name)`).

### Parsing model (two-level, validated against the data)
- **family** = brand root: leading tokens before the first strength/suffix/form token, e.g.
  `TELMA`, `VOLINI`, `4 QUIN`, `AUGMENTIN`. Naive "name minus form" fractures TELMA into 24
  one-SKU families — do NOT do that. Build the family by grouping on a normalized brand root
  (first 1–2 tokens with heuristics; validate: TELMA→~24 SKUs, VOLINI→10, 4 QUIN→6).
- **variant axes** parsed per SKU: `variant_label` (suffix line: `H`, `AM`, `CT 40/6.25`,
  `JOINT XPERT`, `MAXX`…), `strength` (`40 MG`, `0.05%`), `form` (TABLET/GEL/SPRAY/DROPS/…,
  ~30 form words), `pack_size` (from Pack_Size column, normalized).

### sqlite schema (`catalog.db`, committed, built by `build_catalog.py`, stdlib only)
```sql
products(code PK, product_id, name, name_clean, family, variant_label, form, strength,
         pack_size, mrp REAL, ptr REAL, stock INT, manufacturer, scheme)
tokens(token, rowid)  -- WITHOUT ROWID inverted index; prefix query = range scan per term.
                      -- NOT fts5: the uv-managed CPython that runs the brains (and the
                      -- Docker image) links sqlite without the fts5 module. Guard test
                      -- test_the_catalog_needs_no_fts5 keeps it that way.
phonetic(token TEXT, key TEXT, family TEXT, alt INT)  -- one row per brand token per key it
                      -- can be heard under: the metaphone-style key (alt 0) plus the
                      -- alternates of the confusions too destructive to fold into a key
                      -- (B/V, soft C/G, epenthetic vowels) at alt 1, scored a notch lower.
+ indexes on family, form
```
Phonetic key: implement a small metaphone-like `phonetic_key(token)` in `normalize.py`
(shared by builder + search). Must make ABEVIA / "abeyvee" / ABIWAYS collide or near-collide,
and survive Hindi-transliteration artifacts (V/W, VH/V, PH/F, EE/I, OO/U, T/TH, D/DH, K/C/Q,
J/Z, S/SH). `phonetic_keys(token)` wraps it with the alternates above — builder and search
both call it, so index and query agree by construction — and `spoken_shape(token)` is the
vowel-preserving folded spelling an alternate match is scored against.

### Public API (exact signatures — brain B codes against this)
```python
@dataclass(frozen=True)
class SkuView:
    code: str; name: str; family: str; variant_label: str; form: str
    strength: str; pack_size: str; mrp: float; ptr: float
    stock: int; manufacturer: str; scheme: str
    def wire(self) -> dict[str, Any]: ...   # exact SkuWire shape from types.ts

@dataclass(frozen=True)
class FamilyView:
    family: str; manufacturers: list[str]; forms: list[str]
    sku_count: int; hint: str               # hint: short human line, e.g. "ENTOD · eye drops/ointment · 6 SKUs"
    def wire(self) -> dict[str, Any]: ...

@dataclass(frozen=True)
class Resolution:
    status: str          # "matched" | "multi_variant" | "multi_family" | "not_found"
    sku: SkuView | None          # set when matched
    family: str | None           # set when matched / multi_variant
    variants: list[SkuView]      # ≤ 8, when multi_variant (or the pack-size choices)
    families: list[FamilyView]   # ≤ 5, when multi_family
    differing_axes: list[str]    # subset of ["variant_label","form","strength","pack_size"] that
                                 # actually DIFFER among candidates — the minimal-question engine
    confidence: float            # 0..1

def resolve(query: str, *, form_hint: str | None = None,
            strength_hint: str | None = None) -> Resolution
def search(query: str, limit: int = 8) -> list[SkuView]     # ranked, for manual search bar
def sku_by_code(code: str) -> SkuView | None
def skus_in_family(family: str) -> list[SkuView]
```

### Resolution ranking (deterministic, in order)
1. Exact / prefix match on `name_clean` → single hit ⇒ `matched` (confidence ≥ 0.9).
2. FTS5 per-token prefix query (`tok*`) on name_clean+family; hints narrow by form/strength.
3. Phonetic fallback on brand tokens when 1–2 give nothing.
4. Group survivors by family:
   - 1 family, 1 SKU ⇒ `matched`
   - 1 family, N SKUs ⇒ `multi_variant`, compute `differing_axes` (only axes with >1 distinct value)
   - 2–5 families ⇒ `multi_family`; >5 ⇒ keep best 5 by rank
   - 0 ⇒ `not_found`
5. `resolve()` must complete in <50 ms warm. Module-level lazy connection, `check_same_thread=False`
   read-only URI; DB path resolved relative to `__file__`.

Tests must cover: "volini" (multi_variant, axes incl. variant_label+pack), "4 quin" (family with
drops/ointment/KT/LOT), "telma 40" (matched or pack-only variant), "dolo 650"-style absent brands,
phonetic "abevia"/"abeyvee", pack-size disambiguation, hint narrowing.

---

## 3. Wire contract (Actions brain→browser, messages browser→brain)

All strings on the wire are **English only** (screen is always English).

### LineItemView (the render state each action carries; see types.ts)
```ts
{ id: string;                       // "li1", "li2" — brain is the numbering authority for agent items
  spoken_text: string;              // English transliteration of what was heard, e.g. "volini spray"
  query: string;                    // search string actually used
  quantity: number | null;
  status: "resolving" | "multi_family" | "multi_variant" | "matched" | "not_found";
  sku: SkuWire | null;
  family: string | null;
  variants: SkuWire[];              // pill choices when multi_variant
  families: FamilyWire[];           // option cards when multi_family
  differing_axes: string[];
  note: string | null;              // short agent note, e.g. "eye drops or ointment?"
  source: "agent" | "manual"; }
```

### Typed Actions (Python `Action` subclasses in brain.py → `frontend/src/actions.gen.ts`, generated)
| wire name | fields | when |
|---|---|---|
| `upsert_items` | `items: LineItemView[]` | add or update line items (full render state, frontend diffs by id) |
| `remove_items` | `ids: string[]` | agent removed items |
| `highlight_item` | `id: string; note: string \| null` | agent is asking about this row ("Which Quin?") |
| `show_search_results` | `query: string; results: SkuWire[]` | reply to the manual search bar |
| `show_variants` | `item_id: string; family: string; results: SkuWire[]; differing_axes: string[]` | reply to `list_variants` — the siblings for one row's inline **Change variant** strip (`results` capped at 24, `differing_axes` labels the pills) |
| `order_note` | `text: string` | one-line banner (e.g. scheme/stock callout) |

### Browser → brain (silent client messages)
- `state_sync` `{ screen: OrderSnapshot }` — debounced 250 ms, on connect + every store `rev` bump.
  ```ts
  OrderSnapshot = { screen: "order" | "confirmed";
    items: { id; spoken_text; status; sku_code; sku_name; pack_size; quantity; source }[];
    total_mrp: number; item_count: number; confirmed: boolean }
  ```
  Browser snapshot is the **authoritative cart** (travel pattern) — it also carries manual taps
  (pill choice, manual add, qty edit, delete, confirm). Pill tap = frontend locally promotes the
  item to `matched` using the candidate SkuWire it already holds, bumps rev.
- `catalog_search` `{ query: string }` — manual search bar keystrokes (debounced ~300 ms, ≥2 chars).
  Brain answers floor-free with a `show_search_results` action (session-scoped, no speech).
- `list_variants` `{ item_id: string, family: string }` — the **Change variant** control on a
  matched row. Brain answers floor-free with `show_variants` (session-scoped, no inference, no
  speech — a tap must never make the agent talk over him). Empty `results` is a legitimate answer,
  same contract as the search bar; the brain never raises here. The row is untouched until he
  picks: the pick is a local re-lock (new `sku`, **quantity preserved**, `pinned`, rev bump), and
  the agent learns of it through `state_sync`'s `sku_code` (§7-bis, absorb).

### Confirm
Manual only. Confirm button enables when every item is `matched` with quantity ≥ 1 (blocked rows
listed). Tap → store sets `confirmed: true`, state_sync fires, UI shows order-placed screen
(order no. `MS-<hhmm>-<n>`). Agent sees `screen:"confirmed"` in grounding and closes in one line
when it next speaks.

---

## 4. LLM tools (brain.py, ADK-native: `async def` methods, docstring = only prose the model sees)

| tool | signature | behavior |
|---|---|---|
| `add_items` | `(items: list[SpokenItem]) -> dict` | For each: assign id, emit `upsert_items` with status `resolving`, then run `resolve()` (real, fast), emit `upsert_items` again with the outcome. Return per-item compact summary (below). |
| `refine_item` | `(item_id: str, query: str) -> dict` | re-resolve with a better English query; emits `upsert_items` |
| `choose` | `(item_id: str, sku_code: str, quantity: int \| None) -> dict` | verbal confirm ⇒ `matched`; emits `upsert_items` |
| `ask_choice` | `(item_id: str, question: str, choices: list[Choice]) -> dict` | the sharpest question on a row with ≥5 candidates (§7-bis); validated, emits `upsert_items` |
| `set_quantity` | `(item_id: str, quantity: int) -> dict` | absolute quantity; emits `upsert_items` |
| `adjust_quantity` | `(item_id: str, delta: int) -> dict` | **relative** quantity ("दस और डाल दो"), clamped at 1 — zero is `remove_items`, and the docstring says so; emits `upsert_items` |
| `change_variant` | `(item_id: str, want: str) -> dict` | swap the SKU **within the row's family**, quantity kept. Ranks `skus_in_family(family)` by `want` (never a fresh `resolve()`, so it cannot jump brands): one hit ⇒ re-lock; several ⇒ back onto the row as variants/candidates so the normal pill/question machinery takes over; none ⇒ retriable error naming the family's axes, row left **unchanged** and said to be unchanged. Emits `upsert_items` |
| `remove_items` | `(item_ids: list[str]) -> dict` | emits `remove_items`. An ambiguous reference removes **nothing** |
| `highlight` | `(item_id: str, note: str \| None) -> dict` | emits `highlight_item` |

**Reference tolerance.** `set_quantity`, `adjust_quantity`, `change_variant`, `remove_items` and
`highlight` all take *either* the row id *or* the product name, through one shared
`OrderDesk._row_for(ref) -> LineItemView | None`: exact `item_id` first, then a case-insensitive
whole match on `spoken_text` / `sku.name` / `family`, then containment. Two rows matching ⇒ a
retriable error listing `matching_ids`, never a guess (these tools delete rows and swap
medicines). Only field names/types/required survive into the ADK schema, so the tolerance is
stated in each **docstring**, not in a field description. A Devanagari reference comes back as the
English-only error rather than "no such item".

```python
class SpokenItem(BaseModel):
    text: str                      # English transliteration of the product as heard
    quantity: int | None = None
    form_hint: str | None = None   # "tablet"/"gel"/"drops"… if spoken
    strength_hint: str | None = None
```
**English-only guard**: a field validator on every str field of every tool model rejects
non-ASCII with a `ValueError` whose message tells the model to resend in English letters
(coercion layer turns it into a retriable tool error — this is the demo-able guardrail).

**Tool return = the minimal-question engine.** Per item:
```python
{ "id": "li1", "status": "multi_variant", "family": "4 QUIN",
  "ask_about": ["form"],                       # only axes that differ
  "options": ["EYE DROPS 5ML ₹160", "EYE OINTMENT 5GM ₹142", ...],  # ≤8, short
  "guidance": "Ask ONE short question about: form. The options are on screen." }
```
matched ⇒ `{status:"matched", name, pack_size, mrp, scheme}`; not_found ⇒ suggestion to retry
`refine_item` with alternate spelling.

### Brain shape
- `OrderDeskBrain(AdkBrain)`, lazy build (travel pattern: per-session fields set before first
  `agent` access). `routes.py`: `NAME = "orderdesk"`, `build(llm)`, `router = make_brain_router(...)`.
- Session payload (from frontend `buildBrainPayload`) → system instruction at session start,
  sugar-style: scenario JSON appended as `PHARMACY CONTEXT (authoritative...)`.
- `grounding()` → `"CURRENT ORDER SCREEN (authoritative, reflects manual edits): " + json(browser_state)`
  plus a `PENDING:` line listing unresolved item ids/questions. Prefer browser snapshot over mirror.
- `on_client_message`: `catalog_search` → `search()` → floor-free `show_search_results`;
  everything else → `super()` (keeps state_sync default).
- Greeting: instant Hindi hello + generated opener continuing from `joined_from_nudge`
  (morning order prompt), grounded in prior calls + order history.
- Pipeline/language: STT `vql-stt` `hi`, TTS `omnivoice/gauri` `hi` (set in frontend config).

### System prompt (Hindi + TTS discipline — copy the exact rules from sugar `brain.py:59-137`
lang section and lead_qual `brain.py:74-77`)
- Speak Hindi in Devanagari; English loanwords transliterated to Devanagari; NEVER Latin script
  in speech.
- **Every tool argument string is clean English** — the screen is always English.
- TTS cannot pronounce medicine names well ⇒ minimize speaking brand names. Point at the screen:
  "स्क्रीन पर ऑप्शन देखिए", say counts/prices/quantities in Hindi words. When a name must be
  spoken, keep it to the shortest brand root ("वोलिनी").
- Minimal-question rule: ask ONLY about `ask_about` axes, one short question, options are on
  screen ("4 Quin — drops या ointment?"). Never read a list aloud.
- Flow: keep taking items while earlier ones resolve; batch questions at natural pauses; user
  confirms the order manually — agent's job is a fully green cart, then prompt to press Confirm.
- Corrections: voice ("वोलिनी हटा दो", "20 नहीं 12 करो") → tools; manual edits arrive via
  grounding — acknowledge, don't re-do.
- Order history enables "मेरा रेगुलर ऑर्डर लगा दो" ⇒ one `add_items` call with the usual items.

---

## 5. Frontend (React 19 + Vite 6, standalone, sugar's form factor)

- `vite.config.ts`: base `/demos/orderdesk/`, dev port **5760**, `/api` proxy like sugar.
- Screens (Phase machine like sugar: `picker → incoming → call → ended`):
  1. **PickerScreen** — "Distributor CRM" console: 2 pharmacy personas × 3 day-scenarios,
     cells show day_label/title/chip/context_bullets; presenter ContextPanel beside the phone
     (walks-in-knowing / previous calls / order history / try-hints). **The entire UI — including
     nudges and presenter hints — is English/Latin script only. Hindi exists ONLY in audio;
     presenter hints are romanized Hinglish ("Volini de do"), never Devanagari.**
  2. **IncomingSequence** — sugar's lock-screen push notification verbatim in spirit: 9:02 AM
     clock, MedSetu notification card, chime, "Join call" / "Snooze".
  3. **OrderScreen** — the product: search bar (manual `catalog_search` round trip), line-item
     list, sticky cart bar (items/total/Confirm). **All UI text English.**
  4. **Order-placed screen** + EndedScreen.
- **Line-item row is the hero.** Status-driven presentation:
  - `resolving`: greyed row, spoken text, shimmer.
  - `multi_variant`: row shows family name + amber "choose" state; **pills** for the differing
    axes (each pill = one SkuWire; label = only what differs, e.g. `DROPS 5ML ₹160` vs `OINTMENT 5GM ₹142`).
  - `multi_family`: 2–5 option cards (family + hint line).
  - `matched`: solid row — name, pack, MRP/PTR, scheme badge if any, stock hint, qty stepper.
  - `not_found`: muted row + "not in catalog" + manual search affordance.
  - `highlight_item` → scroll to + pulse the row, show `note` as a speech-bubble chip.
- Store: sugar-style context + reducer; one `handleUiCommand` narrowing on `command`
  against the generated `actions.gen.ts` — every field non-optional, `default` exhaustive.
- Session: `useVoqalSession` like sugar's `SugarCoach.tsx` (connect on mount at call phase,
  `enableMic`, register agentSend, debounced state_sync on rev). Hindi pipeline hints.
- Visual identity: NOT sugar's evergreen. B2B distributor tone — think dense, capable, trade-app:
  deep blue/slate + saffron accent, Inter + Noto Sans Devanagari stack (presenter panel shows
  Hindi hints). Status colors: grey resolving / amber ambiguous / green matched.
- Env/config: copy sugar's `config.ts` shape; `VITE_AGENT_ID` / `VITE_PUBLISHABLE_KEY` generic
  names (build.mjs maps `VITE_ORDERDESK_AGENT` / `VITE_ORDERDESK_PK`).
- Dev affordance: `window.__orderdesk.ui(...)` / `.sendText(...)` in DEV.

---

## 6. Scenarios (frontend/src/data.ts — types in types.ts)

2 pharmacies × 3 days, all product references REAL rows from the CSV:
- **Gupta Medical Store** (Karol Bagh, Delhi — owner Ramesh Gupta, 12 yrs, high volume, GNM-style
  chronic-heavy counter): D1 clean first order (happy path: TELMA 40, SHELCAL, DOLO-alternative
  etc. — verify each exists in CSV); D2 the ambiguity day (VOLINI unspecified, 4 QUIN drops vs
  ointment, phonetic ABEVIA-vs-ABIWAYS style pair found in the CSV, THYRONORM strength);
  D3 "मेरा रेगुलर ऑर्डर" reorder from history + two corrections mid-flight.
- **New Sanjivani Pharmacy** (Pune, Kothrud — owner Priya Deshmukh, newer store, OTC/derm-heavy):
  D1 onboarding + small mixed order; D2 pack-size and scheme day (items where Scheme column is
  non-empty — agent surfaces the deal); D3 momentum day: bigger order, one not_found item,
  one manual-search add.
- Each scenario: `context_bullets` (what the agent walks in knowing), `prior_calls` (CRM
  summaries — the "Day n-1" entries), `order_history` (real SKU codes+names+qty), `objective`,
  `nudge` (the 9 AM push text — Hinglish in Latin script, no Devanagari), `try_hints` (what the
  presenter should say in Hindi, written as romanized Hinglish — screen stays English-only),
  `usual_items` for D3.
- `buildBrainPayload(scenario)` → `{ language: "Hindi", scenario: {...} }` exactly as consumed
  by brain B (§4): pharmacy, prior_calls, order_history, todays_call_objective, joined_from_nudge.

---

## 7-bis. Sharpest-question disambiguation (make-or-break #2)

The naive UX for 20 matches is 20 pills. We never do that. Contract:

- **≤4 candidates** → leaf pills directly (`variants`, no question). This is the only case
  where pills are SKUs by default.
- **≥5 candidates** → the tool result hands the LLM a compact candidate table (code,
  variant_label, form, strength, pack_size, mrp — one line each) plus guidance, and the LLM
  calls the new tool:

  ```python
  async def ask_choice(item_id: str, question: str, choices: list[Choice]) -> dict
  class Choice(BaseModel):
      label: str                 # short English pill label
      sku_codes: list[str]       # the candidates this choice keeps
  ```
  The brain VALIDATES: 2–4 choices; every code ∈ current candidates; union covers ALL
  candidates (uncovered/unknown codes → retriable tool error naming them). It emits
  `UpsertItems` with `question` (choices become `DisambigChoice`: leaf if one code) and the
  full `candidates` list, then returns the narrowed structure. The LLM asks the SAME question
  aloud in one short Hindi sentence.
- **Question quality bar** (prompted + eval-enforced): choose the axis/grouping that splits
  most evenly (maximize elimination whatever the answer); group labels must be meaningfully
  distinct (suffix line, form, strength band — never pack-size trivia first); ≤4 pills; at
  most 2 rounds to a leaf for ≤24 candidates (log₄ bound).
- **Pill tap (frontend, local-first):** leaf pill → matched instantly. Group pill → narrow
  `candidates` to `narrows_to`; if ≤4 remain, synthesize leaf pills locally (labels from the
  axes that still differ); else show "N left — answer or tap" and let state_sync
  (`candidate_codes` per item) tell the agent to fire the next `ask_choice`.
- **Family card tap = the same local narrow, not a search.** A `multi_family` row's brand cards
  look like a picker, so they must behave like one. The brain therefore populates
  `row.candidates` with the union of the candidate families' SKUs **regardless of the question
  floor** (`_widen`, still capped at 24) — the ≥5 floor governs only what the *model* is told
  (`_brief` reads the candidate table from 5 up; under it a `multi_family` row still gets "ask
  which brand"). Tapping a card filters `candidates` to `sku.family === family` and reuses the
  post-narrow rule above; rev bumps so `state_sync` carries the new `candidate_codes`.
  The one honest exception: the candidate set is capped, so a family whose SKUs were truncated
  cannot be narrowed locally. Derived, no new wire field —
  `candidates.filter(c => c.family === f.family).length === f.sku_count` means the browser holds
  that family whole; anything else falls back to the scoped search panel **and the card must say
  so** (`Search N SKUs 🔍` vs `N SKUs →`). A control must never look like a pick and behave like
  a search.
- **Inline variant edit on a matched row** (`list_variants` → `show_variants`, §3): the family is
  usually right and only the variant wrong. A quiet *Change variant* control opens a strip **on
  that row** — siblings as pills labelled by `differing_axes`, current SKU marked, scrollable past
  ~8, dismissable. `PILL_CAP` governs *questions*; this is a deliberate browse he asked for. The
  pick re-locks locally (quantity preserved, rev bump). By voice the same edit is
  `change_variant` (§4).
- **Manual edits propagate through `absorb`.** `state_sync`'s per-row `sku_code`, `quantity` and
  `candidate_codes` are all folded back into the brain's mirror. Trust follows ownership: the
  candidate set is the brain's fact and only ever narrows (an unknown code is ignored), while the
  SKU and quantity are the browser's — a row naming a different code is re-locked from the catalog
  and goes `matched`, candidates and question spent. Without that fold a later `change_variant`
  would re-resolve from the family he already moved off.
- **Verbal answer path:** the agent maps the spoken answer to the same narrowing and either
  `choose()`s a leaf or `ask_choice()`s again on the remainder.
- **Eval (real Gemini, `gemini-3.1-flash-lite`):** `backend/eval/disambig_eval.py` replays
  every catalog family with ≥5 SKUs through the actual prompt fragment + `ask_choice`
  declaration; a deterministic oracle answers for a hidden target SKU. Metrics: choice-set
  validity (coverage/pill-cap), rounds-to-leaf vs the information-theoretic bound,
  partition-balance score, and a failure table. Thresholds gate the demo: validity ≥98%,
  avg rounds ≤2, max rounds 3.

## 7. Registration / production

- `demos/manifest.json`: add orderdesk card ("OrderDesk — B2B order intake…").
- `demos/cloudbuild.brains-vm.yaml`: `_EXPECTED_DEMOS` 10 → 11.
- `demos/cloudbuild.web.yaml`: `_ORDERDESK_AGENT` / `_ORDERDESK_PK` substitutions + env mapping.
- Seed script `demos/orderdesk/bin/seed.md` + script per control-plane MCP flow
  (`create_agent` → brain_url `wss://brain.voqalize.com/orderdesk`, `create_api_key`
  publishable with allowed_origins) — mirrors docs/reference/mcp.md.
