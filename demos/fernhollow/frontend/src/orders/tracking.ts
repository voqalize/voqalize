/**
 * The signed-in account's orders, one model for the orders page and the
 * return form: the authored demo orders (data/demo_orders.json, every one with
 * a `tracking` block) and the orders placed in this browser (src/state/orders.ts),
 * which start packed, booked into `placed_order`'s slot. Days are relative to
 * today, so the statuses hold whenever the demo runs.
 *
 * What the shopper (or the agent) does to an order is kept per browser: a
 * delivery day moved (only ever to one of the order's own authored slots), an
 * order cancelled (only while packed), an earlier delivery requested (only
 * while it is on the way — a request, never a promise).
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import ordersJson from "../../../data/demo_orders.json";
import { type PlacedOrder, daysSince, useOrders } from "../state/orders";
import { safeStorage } from "../state/storage";
import type { By } from "../voice/events";

export type Stage = "packed" | "on_the_way" | "out_for_delivery" | "delivered";
export type Status = Stage | "cancelled";
export type EventStage = "ordered" | Stage;

export interface OrderLine {
  product_id: string;
  variant_id: string;
  title: string;
  variant: string;
  qty: number;
  unit_price: number;
}
export interface TrackEvent {
  stage: EventStage;
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
export interface Tracking {
  stage: Stage;
  events: TrackEvent[];
  delivery: { slot?: string; days_from_now?: number; window?: string; hours?: string; stops_before?: number };
  slots: Slot[];
  can_reschedule: boolean;
  why_not?: string;
  two_person?: boolean;
}
export interface AccountOrder {
  number: string;
  name: string;
  placed_days_ago: number;
  delivered_days_ago: number | null;
  lines: OrderLine[];
  total: number;
  delivery_fee?: number;
  tracking: Tracking;
  /** Placed in this browser. */
  placed?: true;
}

const data = ordersJson as unknown as {
  return_window_days: number;
  orders: AccountOrder[];
  placed_order: { booked: string; slots: Slot[] };
};
export const RETURN_WINDOW_DAYS = data.return_window_days;
export const DEMO_ORDERS: AccountOrder[] = data.orders;
export const ACCOUNT_NAME = DEMO_ORDERS[0]?.name ?? "";

const clock = (iso: string) => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const h = d.getHours();
  const m = String(d.getMinutes()).padStart(2, "0");
  return `${h % 12 || 12}:${m} ${h < 12 ? "am" : "pm"}`;
};

/** An order placed in this browser, as the account reads it: packed, booked into the template's slot. */
export function asAccountOrder(o: PlacedOrder, now = Date.now()): AccountOrder {
  const ago = daysSince(o.placed_at, now);
  const time = clock(o.placed_at);
  return {
    number: o.number,
    name: o.name || ACCOUNT_NAME,
    placed_days_ago: ago,
    delivered_days_ago: null,
    lines: o.lines,
    total: o.total,
    placed: true,
    tracking: {
      stage: "packed",
      events: [
        { stage: "ordered", days_ago: ago, time, text: "Order placed" },
        { stage: "packed", days_ago: ago, time, text: "Packed at the Fernhollow warehouse and waiting for its van" },
      ],
      delivery: { slot: data.placed_order.booked },
      slots: data.placed_order.slots,
      can_reschedule: true,
    },
  };
}

/** Every order of the account: the ones placed here (newest first), then the demo orders. */
export function allOrders(placed: PlacedOrder[] = useOrders.getState().orders): AccountOrder[] {
  const own = [...placed].sort((a, b) => (b.placed_at ?? "").localeCompare(a.placed_at ?? "")).map((o) => asAccountOrder(o));
  return [...own, ...DEMO_ORDERS.filter((d) => !own.some((o) => o.number === d.number))];
}

/** "fh 31207", "31207", "FH-31207" → "FH-31207". */
export const normalOrderNumber = (s: string | null | undefined) => {
  const digits = (s ?? "").replace(/\D/g, "");
  return digits ? `FH-${digits}` : (s ?? "").trim().toUpperCase();
};
export const findOrder = (number: string | null | undefined): AccountOrder | undefined =>
  number ? allOrders().find((o) => o.number === normalOrderNumber(number)) : undefined;

// ── Labels ─────────────────────────────────────────────────────────────────

export const STATUS_LABEL: Record<Status, string> = {
  packed: "Packed",
  on_the_way: "On its way",
  out_for_delivery: "Out for delivery",
  delivered: "Delivered",
  cancelled: "Cancelled",
};
/** The timeline, in order. */
export const TIMELINE: { id: EventStage; label: string }[] = [
  { id: "ordered", label: "Ordered" },
  { id: "packed", label: "Packed" },
  { id: "on_the_way", label: "On its way" },
  { id: "out_for_delivery", label: "Out for delivery" },
  { id: "delivered", label: "Delivered" },
];

/** A day relative to today, shown "Thu 20 Nov". */
export function dayLabel(offset: number, now = new Date()): string {
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + offset);
  const wd = d.toLocaleDateString("en-GB", { weekday: "short" });
  const mo = d.toLocaleDateString("en-GB", { month: "short" });
  return `${wd} ${d.getDate()} ${mo}`;
}
export const relDay = (offset: number) => (offset === 0 ? "Today" : offset === 1 ? "Tomorrow" : offset === -1 ? "Yesterday" : dayLabel(offset));
export const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
/** "Sun 23 Nov, evening (5 pm to 9 pm)"; today's slot reads "today, afternoon (12 pm to 5 pm)". */
export const slotLabel = (s: Slot) => `${s.days_from_now === 0 ? "today" : dayLabel(s.days_from_now)}, ${s.window} (${s.hours})`;
/** "Sun 23 Nov morning", for a list of slots. */
export const slotShort = (s: Slot) => `${s.days_from_now === 0 ? "today" : dayLabel(s.days_from_now)} ${s.window}`;

// ── What was done to the orders, in this browser ───────────────────────────

export interface Done {
  order_number: string;
  by: By;
  stamp: number;
}
interface AccountState {
  /** order number → the slot id it was moved to. */
  moved: Record<string, string>;
  cancelled: Record<string, true>;
  earlier: Record<string, true>;
  /** The last change of each kind, for the events the agent hears (not kept). */
  movedEv: (Done & { slot: string }) | null;
  cancelledEv: Done | null;
  earlierEv: Done | null;
  move(order: string, slot: string, by?: By): void;
  cancel(order: string, by?: By): void;
  requestEarlier(order: string, by?: By): void;
}

export const useAccount = create<AccountState>()(
  persist(
    (set, get) => ({
      moved: {},
      cancelled: {},
      earlier: {},
      movedEv: null,
      cancelledEv: null,
      earlierEv: null,
      move(order, slot, by = "visitor") {
        set({ moved: { ...get().moved, [order]: slot }, movedEv: { order_number: order, slot, by, stamp: Date.now() } });
      },
      cancel(order, by = "visitor") {
        set({ cancelled: { ...get().cancelled, [order]: true }, cancelledEv: { order_number: order, by, stamp: Date.now() } });
      },
      requestEarlier(order, by = "visitor") {
        set({ earlier: { ...get().earlier, [order]: true }, earlierEv: { order_number: order, by, stamp: Date.now() } });
      },
    }),
    {
      name: "fernhollow-order-state",
      storage: safeStorage,
      partialize: (s) => ({ moved: s.moved, cancelled: s.cancelled, earlier: s.earlier }) as never,
    },
  ),
);

type Kept = Pick<AccountState, "moved" | "cancelled" | "earlier">;
const kept = (): Kept => useAccount.getState();

export function statusOf(o: AccountOrder, s: Kept = kept()): Status {
  return s.cancelled[o.number] ? "cancelled" : o.tracking.stage;
}
export const isOnTheWay = (st: Status) => st === "on_the_way" || st === "out_for_delivery";
export const canMove = (o: AccountOrder, s: Kept = kept()) => statusOf(o, s) === "packed" && o.tracking.can_reschedule && o.tracking.slots.length > 0;
export const canCancel = (o: AccountOrder, s: Kept = kept()) => statusOf(o, s) === "packed";

/** The slot the order is booked into now. */
export function bookedSlot(o: AccountOrder, moved: Record<string, string> = kept().moved): Slot | null {
  const id = moved[o.number] ?? o.tracking.delivery.slot;
  const s = o.tracking.slots.find((x) => x.id === id);
  if (s) return s;
  const d = o.tracking.delivery;
  if (d.days_from_now != null && d.window && d.hours) return { id: `d${d.days_from_now}-${d.window}`, days_from_now: d.days_from_now, window: d.window, hours: d.hours };
  return null;
}

export type Returnable =
  | { kind: "eligible"; days: number; daysLeft: number }
  | { kind: "outside_window"; days: number }
  | { kind: "not_delivered" }
  | { kind: "cancelled" };

export function returnable(o: AccountOrder, s: Kept = kept()): Returnable {
  const st = statusOf(o, s);
  if (st === "cancelled") return { kind: "cancelled" };
  if (st !== "delivered" || o.delivered_days_ago == null) return { kind: "not_delivered" };
  const days = o.delivered_days_ago;
  return days <= RETURN_WINDOW_DAYS ? { kind: "eligible", days, daysLeft: RETURN_WINDOW_DAYS - days } : { kind: "outside_window", days };
}

/** "Delivered 41 days ago, outside the 30-day return window". */
export const outsideWindowText = (days: number) => `Delivered ${days} days ago, outside the ${RETURN_WINDOW_DAYS}-day return window`;

/** Why a return cannot start, in the shopper's words; "" when it can. */
export function whyNoReturn(o: AccountOrder, s: Kept = kept()): string {
  const r = returnable(o, s);
  if (r.kind === "eligible") return "";
  if (r.kind === "cancelled") return `order ${o.number} was cancelled, so there is nothing to return`;
  if (r.kind === "outside_window") return `order ${o.number} was delivered ${r.days} days ago, outside the ${RETURN_WINDOW_DAYS}-day return window`;
  const st = statusOf(o, s);
  return `order ${o.number} is ${st === "packed" ? "still packed at the warehouse" : "on its way"} and not delivered yet, so a return can start once it arrives`;
}

// ── The orders page's view ─────────────────────────────────────────────────

/** The order the page has open, its day picker and its cancel confirmation. */
export const useOrderView = create<{
  open: string | null;
  /** The day picker is showing, with this slot chosen but not yet saved. */
  picking: boolean;
  pending: string | null;
  /** "Cancel order FH-31207?" is showing. */
  confirming: boolean;
  opened: Done | null;
  setOpen(n: string | null, by?: By): void;
  setPicking(v: boolean, pending?: string | null): void;
  setPending(slot: string): void;
  setConfirming(v: boolean): void;
}>((set) => ({
  open: null,
  picking: false,
  pending: null,
  confirming: false,
  opened: null,
  setOpen: (n, by = "visitor") =>
    set({ open: n, picking: false, pending: null, confirming: false, opened: n ? { order_number: n, by, stamp: Date.now() } : null }),
  setPicking: (picking, pending = null) => set({ picking, pending, confirming: false }),
  setPending: (pending) => set({ pending }),
  setConfirming: (confirming) => set({ confirming, picking: false, pending: null }),
}));
