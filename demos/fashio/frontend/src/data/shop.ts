/**
 * Fashio's authored content (`data/store.json`) and the customer's orders
 * (`data/orders.json`), with the shared rules for dates, the bag, orders,
 * cancelling and returns (CONTRACT.md). The brain implements the same rules in
 * `backend/fashio.py`.
 */
import ordersRaw from "../../../data/orders.json";
import storeRaw from "../../../data/store.json";
import { type Product, getProduct } from "./catalog";

export const STORE = storeRaw as unknown as StoreData;
export const POLICY = STORE.policies;

export interface SizeChart {
  title: string;
  unit: string;
  columns: string[];
  rows: string[][];
  how: string;
}

export interface Campaign {
  id: string;
  title: string;
  kicker: string;
  copy: string;
  filter: Record<string, unknown>;
  tone: string;
}

export interface StoreData {
  brand: { name: string; tagline: string; support_phone: string; support_hours: string; store: { name: string; city: string; floor: string } };
  policies: {
    delivery: { free_over: number; fee: number; days_min: number; days_max: number; cod: boolean; summary: string };
    changes: { summary: string };
    cancel_statuses: string[];
    returns: { window_days: number; conditions: string[]; not_returnable_types: string[]; refund: string; pickup: string; summary: string };
    gift_wrap: { price: number; note_max: number; summary: string };
  };
  statuses: Record<string, string>;
  size_charts: Record<string, SizeChart>;
  fit: { slim_words: string[]; loose_words: string[]; tall_cm: number; short_cm: number; length_types: string[] };
  campaigns: Campaign[];
  home_rails: { title: string; filter: Record<string, unknown> }[];
  gifts: {
    recipients: string[];
    occasions: string[];
    recipient_gender: Record<string, string | null>;
    budgets: number[];
    ideas: Record<string, string[]>;
    festive_occasions: string[];
  };
  kiosk: { floor_assistant: string; idle_title: string; idle_copy: string };
}

// ─── Dates (IST) ──────────────────────────────────────────────────────────────

/** Today's date in Asia/Kolkata, YYYY-MM-DD. */
export function todayIST(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}
export function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
export function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86400000);
}
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** 27 Nov 2026 */
export function fmtDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}
/** Fri, 27 Nov */
export function fmtDay(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  const wd = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][d.getUTCDay()];
  return `${wd}, ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}

// ─── Orders ───────────────────────────────────────────────────────────────────

export type Status = "placed" | "packed" | "shipped" | "out_for_delivery" | "delivered" | "cancelled" | "return_requested";

export interface OrderItem {
  product_id: number;
  size: string;
  qty: number;
  price: number;
  gift?: boolean;
  note?: string;
}

export interface Address {
  name: string;
  line: string;
  city: string;
  pin: string;
}

export interface Order {
  id: string;
  /** Dates as YYYY-MM-DD (resolved from the data's day offsets). */
  placed: string;
  status: Status;
  eta?: string;
  delivered?: string;
  payment: string;
  address: Address;
  items: OrderItem[];
  events: { date: string; time: string; status: string; text: string }[];
  courier: { name: string; awb: string } | null;
  /** Placed in this browser at checkout. */
  local?: boolean;
}

interface RawOrder {
  id: string;
  placed: number;
  status: Status;
  eta?: number;
  delivered?: number;
  payment: string;
  address: Address;
  items: OrderItem[];
  events: { day: number; time: string; status: string; text: string }[];
  courier: { name: string; awb: string } | null;
}

export const CUSTOMER = (ordersRaw as { customer: { name: string; first: string; city: string } }).customer;

/** The sample orders, dated from today (IST). */
export function sampleOrders(today: string = todayIST()): Order[] {
  return (ordersRaw as unknown as { orders: RawOrder[] }).orders.map((o) => ({
    ...o,
    placed: addDays(today, o.placed),
    eta: o.eta != null ? addDays(today, o.eta) : undefined,
    delivered: o.delivered != null ? addDays(today, o.delivered) : undefined,
    events: o.events.map((e) => ({ date: addDays(today, e.day), time: e.time, status: e.status, text: e.text })),
  }));
}

export const statusLabel = (s: string): string => STORE.statuses[s] ?? s;
export const canCancel = (o: Order): boolean => POLICY.cancel_statuses.includes(o.status);
export const orderTotal = (o: Order): number => o.items.reduce((t, i) => t + i.price * i.qty, 0);

export interface ReturnCheck {
  ok: boolean;
  /** Why not, in one line the page shows (and the brain says in its own words). */
  why?: string;
  daysLeft?: number;
}

/** Whether `item` of `o` can be returned today (CONTRACT.md, Returns). */
export function returnCheck(o: Order, productId: number | null, returned: Set<string>, today: string = todayIST()): ReturnCheck {
  if (o.status !== "delivered" || !o.delivered) return { ok: false, why: "Returns open once the order is delivered." };
  const since = daysBetween(o.delivered, today);
  const left = POLICY.returns.window_days - since;
  if (left < 0) return { ok: false, why: `Delivered on ${fmtDate(o.delivered)}: the ${POLICY.returns.window_days}-day return window closed on ${fmtDate(addDays(o.delivered, POLICY.returns.window_days))}.` };
  if (productId != null) {
    const p: Product | undefined = getProduct(productId);
    if (p && POLICY.returns.not_returnable_types.includes(p.type)) return { ok: false, why: "Fragrances cannot be returned." };
    if (returned.has(`${o.id}|${productId}`)) return { ok: false, why: "A return for this item is already requested." };
  }
  return { ok: true, daysLeft: left };
}

export const returnRef = (orderId: string, productId: number) => `RTN-${orderId.replace(/\D/g, "")}-${productId}`;

// ─── Bag ──────────────────────────────────────────────────────────────────────

export interface BagLine {
  product_id: number;
  size: string;
  qty: number;
  gift: boolean;
  note: string;
}

export const lineKey = (id: number | string, size: string) => `${id}|${size}`;

export interface BagTotals {
  count: number;
  subtotal: number;
  mrp: number;
  delivery: number;
  wrap: number;
  total: number;
}

export function bagTotals(lines: BagLine[]): BagTotals {
  let subtotal = 0;
  let mrp = 0;
  let count = 0;
  let wrap = 0;
  for (const l of lines) {
    const p = getProduct(l.product_id);
    if (!p) continue;
    subtotal += p.price * l.qty;
    mrp += p.mrp * l.qty;
    count += l.qty;
    if (l.gift) wrap += POLICY.gift_wrap.price * l.qty;
  }
  const delivery = count === 0 || subtotal >= POLICY.delivery.free_over ? 0 : POLICY.delivery.fee;
  return { count, subtotal, mrp, delivery, wrap, total: subtotal + delivery + wrap };
}

// ─── Service pages (orders, returns) ─────────────────────────────────────────

/** The return reasons the scene's `returns.fill` takes, with the page's labels. */
export const RETURN_REASONS: { id: string; label: string }[] = [
  { id: "size_small", label: "Too small" },
  { id: "size_large", label: "Too large" },
  { id: "not_as_pictured", label: "Looks different from the pictures" },
  { id: "quality", label: "Quality not as expected" },
  { id: "changed_mind", label: "Changed my mind" },
  { id: "damaged", label: "Arrived damaged" },
  { id: "wrong_item", label: "Received the wrong item" },
];
export const reasonLabel = (id: string): string => RETURN_REASONS.find((r) => r.id === id)?.label ?? id;

/** The tracking steps in order (a cancelled order leaves the line). */
export const TRACK_STEPS: Status[] = ["placed", "packed", "shipped", "out_for_delivery", "delivered"];

/** How a cancelled order's money comes back, from the payment method. */
export function refundNote(o: Pick<Order, "payment">): string {
  if (/cash on delivery/i.test(o.payment)) return "Nothing was charged: it was a cash on delivery order.";
  return `Refunded to your ${o.payment} within 5 to 7 days.`;
}

/** The return pickup date: within `pickup` (2) days of the request. */
export const PICKUP_DAYS = 2;
export const pickupDate = (today: string = todayIST()): string => addDays(today, PICKUP_DAYS);
