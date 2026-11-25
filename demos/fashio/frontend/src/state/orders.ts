/**
 * The customer's orders as the pages show them: the sample orders (dated from
 * today, IST) merged with what this browser did (orders placed at checkout,
 * cancelled here, items returned here), plus the page-local state of /orders
 * (the selected order, the cancel dialog) and /returns (the return form).
 *
 * The merge is a pure function (`mergeOrders`) so the tests and the
 * performers use exactly what the page renders.
 */
import { useMemo } from "react";
import { create } from "zustand";
import { type Order, type OrderItem, refundNote, sampleOrders, todayIST } from "../data/shop";
import { useStore } from "./store";

export interface ViewItem extends OrderItem {
  /** The return reference when a return for this item was requested here. */
  returnRef?: string;
}

export interface ViewOrder extends Omit<Order, "items"> {
  items: ViewItem[];
  /** Cancelled in this browser (the shopper pressed Cancel order). */
  cancelledHere?: boolean;
}

/** Sample orders + this browser's placed, cancelled and returned. Newest first. */
export function mergeOrders(sample: Order[], placed: Order[], cancelled: string[], returns: Record<string, string>, today: string = todayIST()): ViewOrder[] {
  const all = [...placed, ...sample.filter((s) => !placed.some((p) => p.id === s.id))];
  return all.map((o) => {
    const items: ViewItem[] = o.items.map((i) => {
      const ref = returns[`${o.id}|${i.product_id}`];
      return ref ? { ...i, returnRef: ref } : { ...i };
    });
    if (cancelled.includes(o.id) && o.status !== "cancelled") {
      return {
        ...o,
        items,
        status: "cancelled",
        cancelledHere: true,
        eta: undefined,
        events: [...o.events, { date: today, time: "", status: "cancelled", text: `Cancelled by you before dispatch. ${refundNote(o)}` }],
      };
    }
    return { ...o, items };
  });
}

/** The returned set `returnCheck` takes: `<order id>|<product id>`. */
export const returnedSet = (returns: Record<string, string>) => new Set(Object.keys(returns));

/** The merged orders now (outside React: performers). */
export function ordersNow(): ViewOrder[] {
  const s = useStore.getState();
  return mergeOrders(sampleOrders(), s.placed, s.cancelled, s.returns);
}
export const findOrder = (id: string | null | undefined): ViewOrder | undefined => {
  if (!id) return undefined;
  const want = id.trim().toUpperCase();
  return ordersNow().find((o) => o.id === want);
};

/** The merged orders, re-rendering when this browser's orders change. */
export function useOrders(): ViewOrder[] {
  const placed = useStore((s) => s.placed);
  const cancelled = useStore((s) => s.cancelled);
  const returns = useStore((s) => s.returns);
  return useMemo(() => mergeOrders(sampleOrders(), placed, cancelled, returns), [placed, cancelled, returns]);
}

// ─── /orders ──────────────────────────────────────────────────────────────

interface OrdersUi {
  selected: string | null;
  /** The order whose cancel dialog is open. */
  cancelFor: string | null;
  select: (id: string | null) => void;
  openCancel: (id: string | null) => void;
}

export const useOrdersUi = create<OrdersUi>((set) => ({
  selected: null,
  cancelFor: null,
  select: (selected) => set({ selected }),
  openCancel: (cancelFor) => set({ cancelFor }),
}));

/** The selected order, merged. */
export function useSelectedOrder(): ViewOrder | undefined {
  const orders = useOrders();
  const id = useOrdersUi((s) => s.selected);
  return orders.find((o) => o.id === id);
}

// ─── /returns ─────────────────────────────────────────────────────────────

export interface ReturnForm {
  order_id: string | null;
  product_id: number | null;
  reason: string | null;
  unused: boolean;
  tags: boolean;
  /** Set once the shopper pressed Submit return. */
  reference: string | null;
}

const EMPTY: ReturnForm = { order_id: null, product_id: null, reason: null, unused: false, tags: false, reference: null };

interface ReturnStore extends ReturnForm {
  /** Start the form for an order (nothing chosen unless `item` is given). */
  start: (orderId: string | null, item?: number | null) => void;
  patch: (p: Partial<ReturnForm>) => void;
}

export const useReturnForm = create<ReturnStore>((set) => ({
  ...EMPTY,
  start: (order_id, item) => set({ ...EMPTY, order_id, product_id: item ?? null }),
  patch: (p) => set(p),
}));

/** Item + reason + both ticks: Submit return can be pressed. */
export const formReady = (f: ReturnForm) => !!(f.order_id && f.product_id != null && f.reason && f.unused && f.tags && !f.reference);
