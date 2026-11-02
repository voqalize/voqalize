/**
 * Orders the shopper placed in this browser (CONTRACT.md v4), kept in
 * localStorage `fernhollow-orders` in the contract's shape. This is a demo
 * with no delivery, so an order counts as delivered the moment it is placed.
 * The returns desk lists these first, and the brain hears them as
 * `orders_known` on connect and whenever the list changes.
 */
import { create } from "zustand";
import { getProduct, getVariant } from "../data/catalog";
import { emit, onSenderReady } from "../voice/events";

export interface PlacedOrder {
  number: string;
  email: string;
  name: string;
  placed_at: string;
  lines: { product_id: string; variant_id: string; title: string; variant: string; qty: number; unit_price: number }[];
  total: number;
  status: "delivered";
}

const KEY = "fernhollow-orders";

function load(): PlacedOrder[] {
  try {
    const all = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(all) ? all.filter((o) => o && typeof o.number === "string" && Array.isArray(o.lines)) : [];
  } catch {
    return [];
  }
}

export const useOrders = create<{ orders: PlacedOrder[] }>(() => ({ orders: load() }));

/** Whole days since an ISO time, never negative. */
export const daysSince = (iso: string, now = Date.now()) => Math.max(0, Math.floor((now - Date.parse(iso)) / 86_400_000));

export function savePlacedOrder(o: {
  number: string;
  email: string;
  name: string;
  lines: { product_id: string; variant_id: string; qty: number }[];
  total: number;
}): PlacedOrder {
  const placed: PlacedOrder = {
    number: o.number,
    email: o.email,
    name: o.name,
    placed_at: new Date().toISOString(),
    lines: o.lines.map((l) => {
      const p = getProduct(l.product_id);
      const v = p ? getVariant(p, l.variant_id) : null;
      return {
        product_id: l.product_id,
        variant_id: l.variant_id,
        title: p?.title ?? l.product_id,
        variant: v?.title ?? "",
        qty: l.qty,
        unit_price: v?.price ?? 0,
      };
    }),
    total: o.total,
    status: "delivered",
  };
  const orders = [...useOrders.getState().orders.filter((x) => x.number !== placed.number), placed];
  try {
    localStorage.setItem(KEY, JSON.stringify(orders));
  } catch {
    /* storage unavailable: the order lives for this page only */
  }
  useOrders.setState({ orders });
  return placed;
}

/** What `orders_known` carries: each order, newest first, with its age in days. */
export function ordersKnown(orders = useOrders.getState().orders) {
  return [...orders]
    .sort((a, b) => b.placed_at.localeCompare(a.placed_at))
    .map((o) => ({ ...o, placed_days_ago: daysSince(o.placed_at), delivered_days_ago: daysSince(o.placed_at) }));
}

const report = () => emit("orders_known", { orders: ordersKnown() });
useOrders.subscribe(report);
onSenderReady(report);
