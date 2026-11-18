/**
 * The account's orders page: the demo orders that carry a `tracking` block
 * (data/demo_orders.json — authored sample data), read as backend/tracking.py
 * reads them. Days are relative to today; a delivery day the shopper (or the
 * agent) moves is kept in this browser per order, and only ever to one of the
 * order's own authored slots.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import ordersJson from "../../../data/demo_orders.json";
import { safeStorage } from "../state/storage";
import type { By } from "../voice/events";

export type Stage = "ordered" | "packed" | "out_for_delivery" | "delivered";
export interface TrackEvent {
  stage: Stage;
  days_ago: number;
  time: string;
  text: string;
}
export interface Slot {
  id: string;
  days_from_now: number;
  window: string;
  hours: string;
}
export interface TrackedOrder {
  number: string;
  name: string;
  email: string;
  placed_days_ago: number;
  delivered_days_ago: number | null;
  status: string;
  total: number;
  delivery_fee?: number;
  lines: { product_id: string; variant_id: string; title: string; variant: string; qty: number; unit_price: number }[];
  tracking: {
    stage: Stage;
    events: TrackEvent[];
    delivery: { slot?: string; days_from_now?: number; window?: string; hours?: string; stops_before?: number };
    slots: Slot[];
    can_reschedule: boolean;
    why_not?: string;
    two_person?: boolean;
  };
}

const all = (ordersJson as unknown as { orders: (TrackedOrder & { tracking?: TrackedOrder["tracking"] })[] }).orders;
export const TRACKED: TrackedOrder[] = all.filter((o): o is TrackedOrder => !!o.tracking);
export const getTracked = (number: string | null | undefined) => {
  const digits = (number ?? "").replace(/\D/g, "");
  return TRACKED.find((o) => o.number === `FH-${digits}`);
};

export const STAGES: { id: Stage; label: string }[] = [
  { id: "ordered", label: "Ordered" },
  { id: "packed", label: "Packed" },
  { id: "out_for_delivery", label: "Out for delivery" },
  { id: "delivered", label: "Delivered" },
];
export const STAGE_LABEL: Record<Stage, string> = { ordered: "Ordered", packed: "Packed", out_for_delivery: "On the van today", delivered: "Delivered" };

/** A day relative to today, shown "Thu 20 Nov". */
export function dayLabel(offset: number, now = new Date()): string {
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + offset);
  const wd = d.toLocaleDateString("en-GB", { weekday: "short" });
  const mo = d.toLocaleDateString("en-GB", { month: "short" });
  return `${wd} ${d.getDate()} ${mo}`;
}
export const relDay = (offset: number) => (offset === 0 ? "Today" : offset === 1 ? "Tomorrow" : offset === -1 ? "Yesterday" : dayLabel(offset));
export const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Delivery slots moved in this browser: order number → slot id. */
export const useDelivery = create<{
  moved: Record<string, string>;
  changed: { order_number: string; slot: string; by: By; stamp: number } | null;
  move(order: string, slot: string, by?: By): void;
}>()(
  persist(
    (set, get) => ({
      moved: {},
      changed: null,
      move(order, slot, by = "visitor") {
        set({ moved: { ...get().moved, [order]: slot }, changed: { order_number: order, slot, by, stamp: Date.now() } });
      },
    }),
    { name: "fernhollow-delivery", storage: safeStorage, partialize: (s) => ({ moved: s.moved }) as never },
  ),
);

/** The slot the order is booked into now. */
export function bookedSlot(o: TrackedOrder, moved: Record<string, string>): Slot | null {
  const id = moved[o.number] ?? o.tracking.delivery.slot;
  const s = o.tracking.slots.find((x) => x.id === id);
  if (s) return s;
  const d = o.tracking.delivery;
  if (d.days_from_now != null && d.window && d.hours) return { id: `d${d.days_from_now}-${d.window}`, days_from_now: d.days_from_now, window: d.window, hours: d.hours };
  return null;
}

/** The order the page has open, and whether its day picker is showing. */
export const useOrderView = create<{
  open: string | null;
  /** The day picker is showing, with this slot chosen but not yet saved. */
  picking: boolean;
  pending: string | null;
  opened: { order_number: string; by: By; stamp: number } | null;
  setOpen(n: string | null, by?: By): void;
  setPicking(v: boolean, pending?: string | null): void;
  setPending(slot: string): void;
}>((set) => ({
  open: null,
  picking: false,
  pending: null,
  opened: null,
  setOpen: (n, by = "visitor") => set({ open: n, picking: false, pending: null, opened: n ? { order_number: n, by, stamp: Date.now() } : null }),
  setPicking: (picking, pending = null) => set({ picking, pending }),
  setPending: (pending) => set({ pending }),
}));
