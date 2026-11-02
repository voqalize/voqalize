/**
 * Brain → UI command payloads, as CONTRACT.md writes them. The brain side
 * generates `actions.gen.ts` from its own source; until then these are the
 * hand-written shapes the controller accepts. Every field the contract marks
 * optional is optional here, and the controller tolerates nulls.
 */
import type { ContractFilters } from "../data/catalog";
import type { CartLine } from "./events";

export interface Brief {
  room?: string | null;
  uses?: string[];
  materials?: string[];
  colours?: string[];
  styles?: string[];
  budget?: number | null;
}

export interface Piece {
  slot: string;
  product_id: string;
  variant_id: string;
  title: string;
  price: number;
  compare_at?: number | null;
  image: string;
  reason: string;
}

export interface CompareRow {
  label: string;
  values: string[];
  /** Index into `values` of the winning cell. */
  winner?: number | null;
}

export interface Swap {
  slot: string;
  from_id: string;
  to_id: string;
  was: number;
  now: number;
}

export interface Commands {
  navigate: { page: string };
  show_products: { title: string; query: string; product_ids: string[]; count: number };
  apply_filters: { filters: ContractFilters; product_ids: string[]; count: number; assumption?: string | null };
  remove_filter: { key: string; product_ids: string[]; count: number };
  open_product: { product_id: string; variant_id?: string | null; focus?: "options" | "highlights" | "price" | null };
  select_variant: { product_id: string; variant_id: string };
  highlight: { target: string };
  update_brief: { brief: Brief; products_left: number };
  show_room_set: { room: string; budget: number; total: number; pieces: Piece[] };
  swap_piece: { slot: string; old_product_id: string; piece: Piece; total: number };
  show_compare: { product_ids: string[]; rows: CompareRow[]; summary: string };
  show_goes_with: { anchor_id: string; items: { product_id: string; reason: string }[] };
  show_more_like: { anchor_id: string; items: { product_id: string; differences: string[] }[] };
  show_savings: { swaps: Swap[]; saved: number; moved_to?: string | null };
  update_shortlist: { product_ids: string[] };
  confirm_add: { lines: CartLine[]; label: string };
  cart_updated: { lines: CartLine[]; total: number; saved: number };
  suggest_finish: { product_id: string; reason: string };
  open_policy: { topic: string };
  undo: Record<string, never>;
  checkout_fill: { field: string; value: string };
  checkout_step: { step: string };
  confirm_place_order: { total: number; label: string };
  order_placed: { order_number: string; total: number };
  show_choices: { product_ids: string[]; label: string };
  clear_choices: Record<string, never>;
}

export type CommandName = keyof Commands;

export const COMMAND_NAMES: CommandName[] = [
  "navigate",
  "show_products",
  "apply_filters",
  "remove_filter",
  "open_product",
  "select_variant",
  "highlight",
  "update_brief",
  "show_room_set",
  "swap_piece",
  "show_compare",
  "show_goes_with",
  "show_more_like",
  "show_savings",
  "update_shortlist",
  "confirm_add",
  "cart_updated",
  "suggest_finish",
  "open_policy",
  "undo",
  "checkout_fill",
  "checkout_step",
  "confirm_place_order",
  "order_placed",
  "show_choices",
  "clear_choices",
];
