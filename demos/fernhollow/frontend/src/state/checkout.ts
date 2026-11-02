/**
 * Checkout's state, one store for both hands: the shopper's typing and
 * Emily's `checkout_fill` / `checkout_step` (CONTRACT.md v2) write the same
 * fields, under the contract's field names, which are also the inputs' `name`s.
 * Placing the order is `placeOrder`, the same for the button and for
 * `order_placed`.
 */
import { create } from "zustand";
import { deliveryFor } from "../data/content";
import { type By, emit } from "../voice/events";
import { type Line, priced, useCart } from "./cart";

export const CHECKOUT_FIELDS = [
  "email",
  "phone",
  "first_name",
  "last_name",
  "address1",
  "address2",
  "city",
  "region",
  "postcode",
  "country",
  "delivery",
] as const;
export type CheckoutField = (typeof CHECKOUT_FIELDS)[number];
export type Address = Record<CheckoutField, string>;

export const CHECKOUT_STEPS = ["contact", "shipping", "review"] as const;
export type CheckoutStep = (typeof CHECKOUT_STEPS)[number];

export const STEP_OF_FIELD: Record<CheckoutField, CheckoutStep> = {
  email: "contact",
  phone: "contact",
  first_name: "shipping",
  last_name: "shipping",
  address1: "shipping",
  address2: "shipping",
  city: "shipping",
  region: "shipping",
  postcode: "shipping",
  country: "shipping",
  delivery: "shipping",
};

export const LABELS: Record<CheckoutField, string> = {
  email: "Email",
  phone: "Phone (optional)",
  first_name: "First name",
  last_name: "Last name",
  address1: "Address",
  address2: "Apartment, suite, floor (optional)",
  city: "City",
  region: "State or region",
  postcode: "Postal code",
  country: "Country",
  delivery: "Delivery notes (optional)",
};

export const COUNTRIES = ["United States", "Canada", "United Kingdom", "Ireland", "Australia", "New Zealand"];

export const REQUIRED: CheckoutField[] = ["email", "first_name", "last_name", "address1", "city", "postcode", "country"];

const EMPTY: Address = {
  email: "",
  phone: "",
  first_name: "",
  last_name: "",
  address1: "",
  address2: "",
  city: "",
  region: "",
  postcode: "",
  country: "United States",
  delivery: "",
};

export interface Order {
  number: string;
  placedAt: string;
  lines: Line[];
  subtotal: number;
  saved: number;
  delivery: number;
  address: Address;
}

interface CheckoutState {
  address: Address;
  step: CheckoutStep;
  by: Partial<Record<CheckoutField, By>>;
  /** Emily asked the shopper to confirm placing the order. */
  confirm: { total: number; label: string } | null;
  set(field: CheckoutField, value: string, by?: By): void;
  setStep(step: CheckoutStep, by?: By): void;
  reset(): void;
}

function load(): Address {
  try {
    return { ...EMPTY, ...JSON.parse(sessionStorage.getItem("fh-address") ?? "{}") };
  } catch {
    return { ...EMPTY };
  }
}
function keep(a: Address) {
  try {
    sessionStorage.setItem("fh-address", JSON.stringify(a));
  } catch {
    /* storage unavailable */
  }
}

const typing = new Map<string, ReturnType<typeof setTimeout>>();

export const useCheckout = create<CheckoutState>((set, get) => ({
  address: load(),
  step: "contact",
  by: {},
  confirm: null,
  set(field, value, by = "visitor") {
    const address = { ...get().address, [field]: value };
    keep(address);
    set((s) => ({ address, by: { ...s.by, [field]: by } }));
    // Typing is reported once the shopper pauses; Emily's fill at once.
    clearTimeout(typing.get(field));
    if (by === "visitor") typing.set(field, setTimeout(() => emit("checkout_changed", { field }, by), 800));
    else emit("checkout_changed", { field }, by);
  },
  setStep(step, by = "visitor") {
    if (get().step === step) return;
    set({ step });
    emit("checkout_step_reached", { step }, by);
  },
  reset: () => set({ address: { ...EMPTY }, step: "contact", by: {}, confirm: null }),
}));

/** What a step still needs, in the shopper's words; empty when it is complete. */
export function missingIn(step: CheckoutStep, a: Address): { field: CheckoutField; why: string }[] {
  const out: { field: CheckoutField; why: string }[] = [];
  for (const f of REQUIRED) {
    if (STEP_OF_FIELD[f] !== step) continue;
    if (!a[f].trim()) out.push({ field: f, why: `Enter your ${LABELS[f].toLowerCase()}.` });
  }
  if (step === "contact" && a.email.trim() && !/^\S+@\S+\.\S+$/.test(a.email.trim())) {
    out.push({ field: "email", why: "Enter an email address like name@example.com." });
  }
  return out;
}

/** Place the order: store it like any other, clear the cart, return it. */
export function placeOrder(number?: string): Order | null {
  const lines = useCart.getState().lines;
  if (!lines.length) return null;
  const { total, saved } = priced(lines);
  const order: Order = {
    number: number || `FH-${String(Date.now()).slice(-6)}`,
    placedAt: new Date().toISOString(),
    lines,
    subtotal: total,
    saved,
    delivery: deliveryFor(total),
    address: useCheckout.getState().address,
  };
  try {
    sessionStorage.setItem("fh-order", JSON.stringify(order));
    const all = JSON.parse(localStorage.getItem("fernhollow-orders") ?? "[]");
    localStorage.setItem("fernhollow-orders", JSON.stringify([...all, order]));
    sessionStorage.removeItem("fh-address");
  } catch {
    /* storage unavailable: the confirmation reads navigation state */
  }
  useCheckout.getState().reset();
  return order;
}
