/**
 * The returns form's state, one store for both hands: the shopper's clicks and
 * Emily's Stage moves (src/stage/performers.ts) write the same fields, and
 * `by` remembers who set each one for the "Emily" tag.
 */
import { create } from "zustand";
import { type ChoiceField, type DemoOrder, RETURN_WINDOW_DAYS, eligibility, exchangeOptions, findOrder, normalOrderNumber } from "./orders";

export type Who = "visitor" | "emily";

export interface ReturnsForm {
  step: number;
  /** The furthest step the form has reached; a step up to it can be reopened. */
  reached: number;
  order_number: string;
  email: string;
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
  /** The field that changed last, for the state event. */
  changed: { field: string; stamp: number } | null;
}

const EMPTY: Omit<ReturnsForm, "by" | "changed"> = {
  step: 1,
  reached: 1,
  order_number: "",
  email: "",
  items: {},
  reason: "",
  condition: "",
  resolution: "",
  exchange: {},
  collection: "",
  pickup_window: "",
};

interface Api extends ReturnsForm {
  setStep(step: number): void;
  setOrderNumber(value: string, by?: Who): void;
  setEmail(value: string, by?: Who): void;
  setChoice(field: ChoiceField, value: string, by?: Who): void;
  setItem(productId: string, qty: number, by?: Who): void;
  setExchange(productId: string, value: string, by?: Who): void;
  reset(orderNumber?: string, by?: Who): void;
}

export const useReturns = create<Api>((set, get) => ({
  ...EMPTY,
  by: {},
  changed: null,
  setStep: (step) =>
    set((s) => {
      const next = Math.max(1, Math.min(6, step));
      return { step: next, reached: Math.max(s.reached, next) };
    }),
  setOrderNumber(value, by = "visitor") {
    const prev = get().order_number;
    const next = value;
    // A different order clears what was chosen for the last one.
    const sameOrder = normalOrderNumber(prev) === normalOrderNumber(next);
    set((s) => ({
      order_number: next,
      items: sameOrder ? s.items : {},
      exchange: sameOrder ? s.exchange : {},
      by: { ...s.by, order_number: by },
      changed: { field: "order_number", stamp: Date.now() },
    }));
  },
  setEmail: (email, by = "visitor") => set((s) => ({ email, by: { ...s.by, email: by }, changed: { field: "email", stamp: Date.now() } })),
  setChoice(field, value, by = "visitor") {
    set((s) => {
      const next: Partial<ReturnsForm> = { [field]: value };
      // Drop-off has no collection window.
      if (field === "collection" && value !== "pickup") next.pickup_window = "";
      return { ...next, by: { ...s.by, [field]: by }, changed: { field, stamp: Date.now() } };
    });
  },
  setItem(productId, qty, by = "visitor") {
    set((s) => {
      const items = { ...s.items };
      if (qty > 0) items[productId] = qty;
      else delete items[productId];
      return { items, by: { ...s.by, items: by, [`qty_${productId}`]: by }, changed: { field: `qty_${productId}`, stamp: Date.now() } };
    });
  },
  setExchange(productId, value, by = "visitor") {
    const field = `exchange_variant_${productId}`;
    set((s) => ({ exchange: { ...s.exchange, [productId]: value }, by: { ...s.by, [field]: by }, changed: { field, stamp: Date.now() } }));
  },
  reset(orderNumber = "", by = "visitor") {
    set({ ...EMPTY, order_number: orderNumber, items: {}, exchange: {}, by: orderNumber ? { order_number: by } : {}, changed: null });
  },
}));

/** What a step still needs, in the shopper's words; "" when it is complete. */
export function missingInStep(form: ReturnsForm, step: number): string {
  const order = currentOrder(form);
  const elig = order ? eligibility(order) : null;
  const chosen = order?.lines.filter((l) => form.items[l.product_id]) ?? [];
  switch (step) {
    case 1:
      if (!order) return "Enter an order number from your confirmation email.";
      if (!form.email.trim()) return "Enter the email you used for the order.";
      if (form.email.trim().toLowerCase() !== order.email.toLowerCase()) return "That email does not match this order.";
      if (elig?.kind === "not_delivered") return "This order has not been delivered yet. You can start a return once it arrives.";
      if (elig?.kind === "outside_window") return `This order was delivered ${elig.days} days ago, outside the ${RETURN_WINDOW_DAYS}-day window.`;
      return "";
    case 2:
      return chosen.length ? "" : "Choose at least one item to return.";
    case 3:
      return !form.reason ? "Choose a reason." : !form.condition ? "Tell us the condition of the items." : "";
    case 4:
      if (!form.resolution) return "Choose how you would like this resolved.";
      if (form.resolution === "exchange" && chosen.some((l) => !form.exchange[l.product_id] && exchangeOptions(l).length)) {
        return "Pick the option you would like instead for each item.";
      }
      return "";
    case 5:
      return !form.collection ? "Choose collection or drop-off." : form.collection === "pickup" && !form.pickup_window ? "Choose a collection window." : "";
    default:
      return "";
  }
}

/** The fields a step still needs, by the form's names (for a refusal that names them). */
export function missingFields(form: ReturnsForm, step: number): string[] {
  const order = currentOrder(form);
  const chosen = order?.lines.filter((l) => form.items[l.product_id]) ?? [];
  switch (step) {
    case 1:
      return [...(order ? [] : ["order_number"]), ...(form.email.trim() && order && form.email.trim().toLowerCase() === order.email.toLowerCase() ? [] : ["email"])];
    case 2:
      return chosen.length ? [] : ["items"];
    case 3:
      return [...(form.reason ? [] : ["reason"]), ...(form.condition ? [] : ["condition"])];
    case 4:
      if (!form.resolution) return ["resolution"];
      return form.resolution === "exchange"
        ? chosen.filter((l) => !form.exchange[l.product_id] && exchangeOptions(l).length).map((l) => `exchange_variant_${l.product_id}`)
        : [];
    case 5:
      return [...(form.collection ? [] : ["collection"]), ...(form.collection === "pickup" && !form.pickup_window ? ["pickup_window"] : [])];
    default:
      return [];
  }
}

/** The first step that still needs something, or null when the form is complete. */
export function firstMissing(form: ReturnsForm): { step: number; why: string } | null {
  for (let step = 1; step <= 5; step++) {
    const why = missingInStep(form, step);
    if (why) return { step, why };
  }
  return null;
}

export const currentOrder = (s: ReturnsForm): DemoOrder | undefined => findOrder(s.order_number);

/** The names of the fields that hold something — never their values. */
export function filledNames(s: ReturnsForm): string[] {
  const out: string[] = [];
  if (s.order_number) out.push("order_number");
  if (s.email) out.push("email");
  if (Object.keys(s.items).length) out.push("items", ...Object.keys(s.items).map((id) => `qty_${id}`));
  for (const f of ["reason", "condition", "resolution", "collection", "pickup_window"] as const) if (s[f]) out.push(f);
  for (const id of Object.keys(s.exchange)) if (s.exchange[id]) out.push(`exchange_variant_${id}`);
  return out;
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
    return JSON.parse(localStorage.getItem(KEY) ?? "[]");
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
