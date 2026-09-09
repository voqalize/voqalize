// Shared shapes for OrderDesk. Owned by the integration contract (DESIGN.md §1);
// both the UI (pages/store) and the scenario data (data.ts) import from here.
//
// The catalog shapes are not written here at all: `SkuWire`, `FamilyWire` and the
// question shapes come off `actions.gen.ts`, generated from backend/brain.py's
// Actions, and are re-exported below so a reader of this file still sees the whole
// contract. What stays hand-written is what the browser owns — the row it renders,
// the scenario data, and the app's own phases.

export type {
  DisambigChoice,
  DisambigQuestion,
  FamilyWire,
  SkuWire,
} from "./actions.gen";

import type { DisambigQuestion, FamilyWire, SkuWire } from "./actions.gen";

/**
 * The catalog's verdict on a row. "multi_family" — 2-5 candidate families as option
 * cards; "multi_variant" — one family, several SKUs, pills on the differing axes;
 * "matched" — locked to a SKU, qty stepper live; "not_found" — no catalog hit,
 * manual search affordance.
 *
 * `null` is a row with no verdict yet — opened, not yet looked at. There is no
 * "resolving" member and no shimmer: the brain's resolver is synchronous and
 * in-process, so `row_opened` and the row's outcome arrive in the same tick. The
 * grey "Looking up…" state was measured at 0.06–0.3 ms, a fraction of one frame,
 * and was never once painted.
 */
export type LineItemStatus =
  | "multi_family"
  | "multi_variant"
  | "matched"
  | "not_found";

export type LineItemSource = "agent" | "manual";

/**
 * One order row, as this screen holds it.
 *
 * It is deliberately **not** a generated type. Nothing sends a whole row: the brain
 * has its own mirror and tells this screen one change at a time (`row_matched`,
 * `row_question`, `row_quantity`…), and the pharmacist's thumb moves rows here
 * without asking anyone. Both pictures are built from the same events; neither is a
 * copy of the other, and there is no merge to get wrong.
 */
export interface LineItem {
  id: string;
  /** What was heard, before any catalog work — the row's title until it matches. */
  spoken_text: string;
  /** The English query the row was last resolved on. */
  query: string;
  quantity: number | null;
  /** The catalog's verdict; `null` until one lands. See {@link LineItemStatus}. */
  status: LineItemStatus | null;
  sku: SkuWire | null;
  family: string | null;
  /** Leaf pills: ≤4 SKUs the pharmacist can settle the row by pointing at. */
  variants: SkuWire[];
  /** Brand cards, when several families could answer to what he said. */
  families: FamilyWire[];
  /** The full candidate set behind a question, once a row is too wide for pills. */
  candidates: SkuWire[];
  question: DisambigQuestion | null;
  differing_axes: string[];
  /** The agent's short aside on this row (`highlight_item`), until the row moves. */
  note: string | null;
  source: LineItemSource;
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
