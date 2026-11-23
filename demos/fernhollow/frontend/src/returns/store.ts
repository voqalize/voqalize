/**
 * An order's return form, one store for both hands: the shopper's taps and the
 * agent's Stage moves (src/stage/orders.ts) write the same fields, and `by`
 * remembers who set each one for the agent's tag. The form belongs to one
 * delivered order (`/orders/return?order=FH-31042`) and starts empty: no item,
 * reason, condition, resolution or collection is chosen until someone says so.
 */
import { create } from "zustand";
import { getProduct } from "../data/catalog";
import { type AccountOrder, findOrder } from "../orders/tracking";
import type { By } from "../voice/events";
import { type ChoiceField, exchangeOptions, LAST_STEP, labelOf } from "./orders";

export type Who = By;

export interface ReturnsForm {
  /** The order the form is for. */
  order_number: string;
  /** The step in front, 1 to 5. */
  step: number;
  /** The furthest step the form has reached; a step up to it can be reopened. */
  reached: number;
  /** product_id → how many to return. */
  items: Record<string, number>;
  reason: string;
  condition: string;
  resolution: string;
  /** product_id → the option value to exchange to. */
  exchange: Record<string, string>;
  collection: string;
  pickup_window: string;
  by: Record<string, Who>;
  /** The field that changed last and its value, for `returns.field_filled`. */
  changed: { field: string; value: string; by: Who; stamp: number } | null;
  /** The step last opened, for `returns.step_reached`. */
  stepped: { step: number; by: Who; stamp: number } | null;
  /** The form was (re)started for an order, for `orders.return_started`. */
  started: { order_number: string; by: Who; stamp: number } | null;
  /** The return just submitted, for `returns.return_submitted`. */
  submitted: { reference: string; order_number: string; filled: string[]; by: Who; stamp: number } | null;
}

const EMPTY = {
  order_number: "",
  step: 1,
  reached: 1,
  items: {} as Record<string, number>,
  reason: "",
  condition: "",
  resolution: "",
  exchange: {} as Record<string, string>,
  collection: "",
  pickup_window: "",
  by: {} as Record<string, Who>,
  changed: null,
  stepped: null,
};

interface Api extends ReturnsForm {
  /** Begin the return for `order` (a no-op when the form is already on it). */
  start(order: string, by?: Who): void;
  setStep(step: number, by?: Who): void;
  setChoice(field: ChoiceField, value: string, by?: Who): void;
  setItem(productId: string, qty: number, by?: Who): void;
  setExchange(productId: string, value: string, by?: Who): void;
  /** Save the return, mark it submitted and clear the form. Only the
   *  visitor's own press sends one: any other hand is refused (null). */
  submit(by?: Who): StoredReturn | null;
  reset(): void;
}

const stamp = () => Date.now();

export const useReturns = create<Api>((set, get) => ({
  ...EMPTY,
  started: null,
  submitted: null,
  start(order, by = "visitor") {
    if (get().order_number === order) return;
    set({ ...EMPTY, items: {}, exchange: {}, by: {}, order_number: order, started: { order_number: order, by, stamp: stamp() } });
  },
  setStep(step, by = "visitor") {
    const next = Math.max(1, Math.min(LAST_STEP, step));
    if (next === get().step) return;
    set((s) => ({ step: next, reached: Math.max(s.reached, next), stepped: { step: next, by, stamp: stamp() } }));
  },
  setChoice(field, value, by = "visitor") {
    set((s) => {
      const next: Partial<ReturnsForm> = { [field]: value };
      const byNext = { ...s.by, [field]: by };
      // Drop-off has no collection window.
      if (field === "collection" && value !== "pickup") next.pickup_window = "";
      // Only an exchange keeps the options chosen to swap to.
      if (field === "resolution" && value !== "exchange") next.exchange = {};
      return { ...next, by: byNext, changed: { field, value, by, stamp: stamp() } };
    });
  },
  setItem(productId, qty, by = "visitor") {
    set((s) => {
      const items = { ...s.items };
      const exchange = { ...s.exchange };
      if (qty > 0) items[productId] = qty;
      else {
        delete items[productId];
        delete exchange[productId];
      }
      const field = `qty_${productId}`;
      return { items, exchange, by: { ...s.by, items: by, [field]: by }, changed: { field, value: String(Math.max(0, qty)), by, stamp: stamp() } };
    });
  },
  setExchange(productId, value, by = "visitor") {
    const field = `exchange_variant_${productId}`;
    set((s) => ({ exchange: { ...s.exchange, [productId]: value }, by: { ...s.by, [field]: by }, changed: { field, value, by, stamp: stamp() } }));
  },
  submit(by = "visitor") {
    if (by !== "visitor") return null;
    const s = get();
    const order = currentOrder(s);
    if (!order || firstMissing(s)) return null;
    const filled = filledNames(s);
    const stored = saveReturn({
      order_number: order.number,
      items: order.lines
        .filter((l) => s.items[l.product_id])
        .map((l) => ({
          product_id: l.product_id,
          title: getProduct(l.product_id)?.title ?? l.title,
          variant: l.variant,
          qty: s.items[l.product_id],
          ...(s.resolution === "exchange" && s.exchange[l.product_id] ? { exchange_to: s.exchange[l.product_id] } : {}),
        })),
      reason: s.reason,
      condition: s.condition,
      resolution: s.resolution,
      collection: s.collection,
      pickup_window: s.pickup_window,
    });
    set({ ...EMPTY, items: {}, exchange: {}, by: {}, submitted: { reference: stored.reference, order_number: order.number, filled, by, stamp: stamp() } });
    return stored;
  },
  reset() {
    set({ ...EMPTY, items: {}, exchange: {}, by: {} });
  },
}));

/**
 * Only the shopper's own hand sends a return (owner, round 2, F10). The form
 * notes every trusted pointer or key press on it; a script's `click()` or
 * `dispatchEvent` is never trusted, and the agent has no move that submits. A
 * submit with no such press just before it is the agent's, and is refused.
 */
let handAt = Number.NEGATIVE_INFINITY;
export const noteHand = (e: { isTrusted: boolean }) => {
  if (e.isTrusted) handAt = Date.now();
};
export const pressedByHand = (): boolean => Date.now() - handAt < 1500;

export const currentOrder = (s: Pick<ReturnsForm, "order_number">): AccountOrder | undefined => findOrder(s.order_number);

type FormView = Pick<ReturnsForm, "order_number" | "items" | "reason" | "condition" | "resolution" | "exchange" | "collection" | "pickup_window">;

const chosenLines = (form: FormView) => currentOrder(form)?.lines.filter((l) => form.items[l.product_id]) ?? [];

/** The fields a step still needs, by the form's names (for a refusal that names them). */
export function missingFields(form: FormView, step: number): string[] {
  const chosen = chosenLines(form);
  switch (step) {
    case 1:
      return chosen.length ? [] : ["items"];
    case 2:
      return [...(form.reason ? [] : ["reason"]), ...(form.condition ? [] : ["condition"])];
    case 3:
      if (!form.resolution) return ["resolution"];
      return form.resolution === "exchange"
        ? chosen.filter((l) => !form.exchange[l.product_id] && exchangeOptions(l).length).map((l) => `exchange_variant_${l.product_id}`)
        : [];
    case 4:
      return [...(form.collection ? [] : ["collection"]), ...(form.collection === "pickup" && !form.pickup_window ? ["pickup_window"] : [])];
    default:
      return [];
  }
}

/** What a step still needs, in the shopper's words; "" when it is complete. */
export function missingInStep(form: FormView, step: number): string {
  const gap = missingFields(form, step);
  if (!gap.length) return "";
  switch (step) {
    case 1:
      return "Tick at least one item to return.";
    case 2:
      return gap.includes("reason") ? "Choose a reason." : "Tell us the condition the items are in.";
    case 3:
      return gap.includes("resolution") ? "Choose how you would like this resolved." : "Pick the option you would like instead for each item.";
    case 4:
      return gap.includes("collection") ? "Choose collection or drop-off." : "Choose a collection window.";
    default:
      return "";
  }
}

/** The first step that still needs something, or null when the form is complete. */
export function firstMissing(form: FormView): { step: number; why: string; fields: string[] } | null {
  for (let step = 1; step < LAST_STEP; step++) {
    const fields = missingFields(form, step);
    if (fields.length) return { step, why: missingInStep(form, step), fields };
  }
  return null;
}

/** The names of the fields that hold something. */
export function filledNames(s: FormView): string[] {
  const out: string[] = [];
  if (Object.keys(s.items).length) out.push("items", ...Object.keys(s.items).map((id) => `qty_${id}`));
  for (const f of ["reason", "condition", "resolution", "collection", "pickup_window"] as const) if (s[f]) out.push(f);
  for (const id of Object.keys(s.exchange)) if (s.exchange[id]) out.push(`exchange_variant_${id}`);
  return out;
}

/** A done step's one-line summary. */
export function stepSummary(form: FormView, step: number): string {
  const chosen = chosenLines(form);
  switch (step) {
    case 1:
      return chosen.map((l) => `${form.items[l.product_id]} × ${getProduct(l.product_id)?.title ?? l.title}`).join(", ");
    case 2:
      return [labelOf("reason", form.reason), labelOf("condition", form.condition)].filter(Boolean).join(" · ");
    case 3:
      return [
        labelOf("resolution", form.resolution),
        ...(form.resolution === "exchange" ? chosen.filter((l) => form.exchange[l.product_id]).map((l) => `${l.variant} to ${form.exchange[l.product_id]}`) : []),
      ]
        .filter(Boolean)
        .join(" · ");
    case 4:
      return [labelOf("collection", form.collection), labelOf("pickup_window", form.pickup_window)].filter(Boolean).join(" · ");
    default:
      return "";
  }
}

// ── Submitted returns, kept in this browser ───────────────────────────────

export interface StoredReturn {
  reference: string;
  order_number: string;
  items: { product_id: string; title: string; variant: string; qty: number; exchange_to?: string }[];
  reason: string;
  condition: string;
  resolution: string;
  collection: string;
  pickup_window: string;
  submitted_at: string;
}

const KEY = "fernhollow-returns";

export function storedReturns(): StoredReturn[] {
  try {
    const all: unknown = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(all) ? (all as StoredReturn[]) : [];
  } catch {
    return [];
  }
}

export function saveReturn(r: Omit<StoredReturn, "reference" | "submitted_at">): StoredReturn {
  const all = storedReturns();
  const digits = r.order_number.replace(/\D/g, "");
  const n = all.filter((x) => x.order_number === r.order_number).length + 1;
  const stored: StoredReturn = { ...r, reference: `RT-${digits}-${n}`, submitted_at: new Date().toISOString() };
  try {
    localStorage.setItem(KEY, JSON.stringify([...all, stored]));
  } catch {
    /* storage unavailable: the confirmation still shows it from navigation state */
  }
  return stored;
}
