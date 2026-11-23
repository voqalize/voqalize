/**
 * Orders the shopper placed in this browser (CONTRACT.md v4), kept in
 * localStorage `fernhollow-orders`. The shopper is signed in, so an order
 * carries the account's name and never an email. A new order is packed at the
 * warehouse, booked into `placed_order`'s slot (src/orders/tracking.ts reads
 * it so), and can still be moved or cancelled. The orders page lists these
 * first, and the brain hears them as `orders_known` on connect and whenever
 * the list changes.
 */
import { create } from "zustand";
import { getProduct, getVariant } from "../data/catalog";
import { emit, onSenderReady } from "../voice/events";

export interface PlacedOrder {
  number: string;
  name: string;
  placed_at: string;
  lines: { product_id: string; variant_id: string; title: string; variant: string; qty: number; unit_price: number }[];
  total: number;
  status: "packed";
}

const KEY = "fernhollow-orders";

type Raw = Record<string, unknown>;
const str = (v: unknown) => (typeof v === "string" ? v : "");
const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : 0);

/** One stored order in the contract shape, whatever build wrote it. Orders saved
 *  before v4 carry `placedAt`, cart-style lines and the address instead of
 *  `name`/`total`; they are upgraded here rather than dropped, so a shopper's
 *  earlier orders never break the orders page. An email, if one was stored,
 *  is dropped: the account is signed in and nothing needs it. */
export function normalizeOrder(raw: unknown): PlacedOrder | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Raw;
  if (typeof o.number !== "string" || !Array.isArray(o.lines)) return null;
  const address = (o.address && typeof o.address === "object" ? o.address : {}) as Raw;
  const lines = (o.lines as Raw[])
    .filter((l) => l && typeof l === "object" && typeof l.product_id === "string")
    .map((l) => {
      const p = getProduct(str(l.product_id));
      const v = p ? getVariant(p, str(l.variant_id)) : null;
      return {
        product_id: str(l.product_id),
        variant_id: str(l.variant_id),
        title: str(l.title) || p?.title || str(l.product_id),
        variant: str(l.variant) || v?.title || "",
        qty: Math.max(1, Math.round(num(l.qty)) || 1),
        unit_price: num(l.unit_price) || v?.price || 0,
      };
    });
  const placed = str(o.placed_at) || str(o.placedAt);
  const name = str(o.name) || [str(address.first_name), str(address.last_name)].filter(Boolean).join(" ");
  const total =
    num(o.total) || num(o.subtotal) + num(o.delivery) || lines.reduce((t, l) => t + l.qty * l.unit_price, 0);
  return {
    number: o.number,
    name,
    placed_at: placed && !Number.isNaN(Date.parse(placed)) ? placed : new Date(0).toISOString(),
    lines,
    total: Math.round(total * 100) / 100,
    status: "packed",
  };
}

function load(): PlacedOrder[] {
  try {
    const all: unknown = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    if (!Array.isArray(all)) return [];
    const orders = all.map(normalizeOrder).filter((o): o is PlacedOrder => o !== null);
    localStorage.setItem(KEY, JSON.stringify(orders)); // write back the upgraded shape once
    return orders;
  } catch {
    return [];
  }
}

export const useOrders = create<{ orders: PlacedOrder[] }>(() => ({ orders: load() }));

/** Whole days since an ISO time, never negative. */
export const daysSince = (iso: string, now = Date.now()) => Math.max(0, Math.floor((now - Date.parse(iso)) / 86_400_000));

export function savePlacedOrder(o: {
  number: string;
  /** Accepted from checkout and never kept. */
  email?: string;
  name: string;
  lines: { product_id: string; variant_id: string; qty: number }[];
  total: number;
}): PlacedOrder {
  const placed: PlacedOrder = {
    number: o.number,
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
    status: "packed",
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

/**
 * What `orders_known` carries: each order, newest first, with its age in days.
 * Packed, so not delivered (`delivered_days_ago: null`); `email` is sent empty
 * only because the event's type still names it — nothing reads it.
 */
export function ordersKnown(orders = useOrders.getState().orders) {
  return [...orders]
    .sort((a, b) => (b.placed_at ?? "").localeCompare(a.placed_at ?? ""))
    .map((o) => ({
      ...o,
      email: "",
      placed_days_ago: daysSince(o.placed_at),
      // The event's type (voice/events.ts) still says number; the brain's OrderIn takes null.
      delivered_days_ago: null as unknown as number,
    }));
}

const report = () => emit("orders_known", { orders: ordersKnown() });
useOrders.subscribe(report);
onSenderReady(report);
