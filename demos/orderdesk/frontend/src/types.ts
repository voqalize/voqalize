// Shared shapes for OrderDesk. Owned by the integration contract (DESIGN.md §1);
// both the UI (pages/store) and the scenario data (data.ts) import from here.
//
// The catalog and line-item shapes are not written here at all: they come off
// `actions.gen.ts`, generated from backend/brain.py's Actions, and are
// re-exported below so a reader of this file still sees the whole contract.
// What stays hand-written is what the browser owns — the snapshot it sends
// back, the scenario data, and the app's own phases.

export type {
  DisambigChoice,
  DisambigQuestion,
  FamilyWire,
  LineItemView,
  SkuWire,
} from "./actions.gen";

import type { LineItemView } from "./actions.gen";

/**
 * "resolving" — just heard, free text, grey and shimmering; "multi_family" —
 * 2-5 candidate families as option cards; "multi_variant" — one family,
 * several SKUs, pills on the differing axes; "matched" — locked to a SKU,
 * qty stepper live; "not_found" — no catalog hit, manual search affordance.
 */
export type LineItemStatus = LineItemView["status"];

export type LineItemSource = LineItemView["source"];

// ---------- browser -> brain snapshot (state_sync) ----------

export interface SnapshotItem {
  id: string;
  spoken_text: string;
  status: LineItemStatus;
  sku_code: string | null;
  sku_name: string | null;
  pack_size: string | null;
  quantity: number | null;
  source: LineItemSource;
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
