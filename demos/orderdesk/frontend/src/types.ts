// Shared shapes for OrderDesk. Owned by the integration contract (DESIGN.md §1);
// both the UI (pages/store) and the scenario data (data.ts) import from here.
// The wire shapes (SkuWire, FamilyWire, LineItemView, OrderSnapshot) mirror
// backend/brain.py's typed Actions — every field is emitted by pydantic, so
// nothing here is optional unless it is genuinely nullable on the wire.

// ---------- catalog wire shapes (emitted by the brain's Actions) ----------

export interface SkuWire {
  code: string;          // Product_Code — the stable SKU id
  name: string;          // clean English name, no trailing -CODE suffix
  family: string;        // brand root, e.g. "VOLINI", "4 QUIN"
  variant_label: string; // suffix line: "MAXX", "JOINT XPERT", "CT 40/6.25", "" if none
  form: string;          // "TABLET" | "GEL" | "SPRAY" | ... | ""
  strength: string;      // "40 MG", "0.05%", "" if none
  pack_size: string;     // normalized, e.g. "10'S", "5ML", "20 GM"
  mrp: number;
  ptr: number;           // price to retailer — the number a pharmacist cares about
  stock: number;
  manufacturer: string;
  scheme: string;        // "" or e.g. "10 + 1, 5 + 9.09%"
}

export interface FamilyWire {
  family: string;
  manufacturers: string[];
  forms: string[];
  sku_count: number;     // the family's TRUE size in the catalog. Compared against how
                         // many of its SKUs actually reached `LineItemView.candidates`
                         // (which is capped), this is what tells the browser whether a
                         // card can narrow in place or must open the search panel.
  hint: string;          // one short human line, e.g. "ENTOD · eye drops/ointment · 6 SKUs"
}

// ---------- line items ----------

export type LineItemStatus =
  | "resolving"      // just heard — free text, grey, shimmering
  | "multi_family"   // 2-5 candidate families — option cards
  | "multi_variant"  // one family, several SKUs — pills on the differing axes
  | "matched"        // locked to a SKU — solid row, qty stepper live
  | "not_found";     // no catalog hit — muted, manual search affordance

// ---------- disambiguation (the sharpest-question mechanic) ----------
// When many SKUs match, the agent does NOT dump them all. It asks ONE
// LLM-generated question with 2-4 choice pills, each pill either a leaf SKU or
// a group that narrows the candidate set; repeated at most once more.

export interface DisambigChoice {
  label: string;               // short English pill label, e.g. "Eye drops", "CT combos", "Plain 40/80"
  sku_code: string | null;     // set when this choice IS a single SKU (leaf)
  narrows_to: string[];        // candidate sku_codes remaining if chosen (leaf → [that code])
}

export interface DisambigQuestion {
  text: string;                // on-screen question, English, e.g. "Which Telma line?"
  choices: DisambigChoice[];   // 2-4; union MUST cover every current candidate
}

export interface LineItemView {
  id: string;                  // "li1"... brain-assigned for agent items, "m1"... for manual adds
  spoken_text: string;         // English transliteration of what was heard
  query: string;               // search string actually used
  quantity: number | null;
  status: LineItemStatus;
  sku: SkuWire | null;         // set when matched
  family: string | null;       // set when matched / multi_variant
  variants: SkuWire[];         // leaf pill choices when candidates ≤ 4 (small sets skip questions)
  families: FamilyWire[];      // option cards (multi_family), else []
  candidates: SkuWire[];       // FULL current candidate set (≤24) when ambiguous, else []
  question: DisambigQuestion | null; // when set, renders INSTEAD of variants/families
  differing_axes: string[];    // subset of ["variant_label","form","strength","pack_size"]
  note: string | null;         // short agent note shown on the row
  source: "agent" | "manual";
}

// ---------- browser -> brain snapshot (state_sync) ----------

export interface SnapshotItem {
  id: string;
  spoken_text: string;
  status: LineItemStatus;
  sku_code: string | null;
  sku_name: string | null;
  pack_size: string | null;
  quantity: number | null;
  source: "agent" | "manual";
  candidate_codes: string[];   // current candidate sku_codes when ambiguous (lets the
                               // agent see a pill-tap narrowing and ask the next question)
}

export interface OrderSnapshot {
  screen: "order" | "confirmed";
  items: SnapshotItem[];
  total_mrp: number;
  item_count: number;
  confirmed: boolean;
}

// ---------- scenarios (data.ts) ----------

export interface Pharmacy {
  id: string;
  name: string;                // "Gupta Medical Store"
  owner: string;               // "Ramesh Gupta"
  city: string;
  area: string;
  since: string;               // "Customer since 2014"
  volume_line: string;         // "₹4.2L / month · ~30 orders"
  credit_line: string;         // "21-day credit · clean record"
  tags: string[];              // ["chronic-heavy", "high volume"]
  hue: number;                 // card accent hue, keeps the two personas visually apart
}

export interface PriorCall {
  day: string;                 // "Day 1 — Mon"
  summary: string;             // CRM-entry summary of that call
  commitment?: string;
}

export interface OrderHistoryItem {
  sku_code: string;            // REAL Product_Code from the catalog
  name: string;                // REAL clean product name
  pack_size: string;
  qty: number;
  when: string;                // "last Tuesday"
}

export interface Scenario {
  id: string;                  // "gupta-d1"
  pharmacy_id: string;
  day_label: string;           // "Day 1"
  title: string;               // "The first morning call"
  call_type: "first_order" | "ambiguous_day" | "reorder" | "scheme_day" | "momentum";
  chip: string;                // short picker chip
  context_bullets: string[];   // what the agent walks in knowing (picker cell + payload)
  try_hints: string[];         // presenter hints — romanized Hinglish lines to SPEAK (screen is English-only, no Devanagari)
  prior_calls: PriorCall[];
  order_history: OrderHistoryItem[];
  usual_items: string[];       // spoken names for "मेरा रेगुलर ऑर्डर" (empty if n/a)
  objective: string;           // today's call objective — steers the opener
  nudge: string;               // the 9 AM push-notification body
}

// ---------- app phases ----------

export type Phase = "picker" | "incoming" | "call" | "ended";
