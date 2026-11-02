/**
 * UI → brain events (CONTRACT.md, "UI → brain events"). One function sends
 * them all. Until a call is live there is no sender and an event is only
 * logged (with `?debug=1`) — a gesture made off-call has no brain that missed it.
 *
 * Every event the shopper caused carries `by: "visitor"`; events that merely
 * report what Emily just did on screen carry `by: "emily"`.
 */
import type { AppEvent, AppEventName } from "./actions.gen";

export type By = "visitor" | "emily";

export interface CartLine {
  product_id: string;
  variant_id: string;
  qty: number;
}

/** The app's own events, typed by the brain's generated `actions.gen.ts`
 *  (Stage's `stage_*` events are Stage's to send). */
type Generated = { [E in Exclude<AppEventName, `stage_${string}`>]: Omit<Extract<AppEvent, { event: E }>["payload"], "by"> };

/** Events the brain's generated file does not carry yet; where both name one, this shape wins. */
interface Pending {
  /** A listing page as the shopper sees it: its rail, what is on, the sort and the count (CONTRACT.md v5). */
  listing_viewed: {
    page: string;
    title: string;
    /** Each facet of the rail by its kind; values and labels exactly as the rail shows them. */
    facets: {
      name: string;
      kind: "options" | "toggle" | "bands" | "range";
      values?: string[];
      multi?: boolean;
      bands?: { label: string; min?: number; max?: number }[];
      min?: number;
      max?: number;
      active?: string[] | true;
    }[];
    sort: { value: string; options: string[] };
    count: number;
  };

  /** The shopper's answer on a confirm prompt; a yes that placed an order carries its number. */
  confirm_result: { confirmed: boolean; order_number?: string };
  orders_known: {
    orders: {
      number: string;
      email: string;
      name: string;
      placed_at: string;
      placed_days_ago: number;
      delivered_days_ago: number;
      lines: { product_id: string; variant_id: string; title: string; variant: string; qty: number; unit_price: number }[];
      total: number;
      status: string;
    }[];
  };
}

export type UiEvents = Omit<Generated, keyof Pending> & Pending;
export type UiEventName = keyof UiEvents;


type Sender = (event: string, payload?: unknown) => void;
let sender: Sender | null = null;
const log: { event: string; payload: unknown; at: number }[] = [];
const listeners = new Set<() => void>();

/** The live call's `client.sendUIEvent`, or null when the call ends. */
export function setEventSender(next: Sender | null) {
  sender = next;
  if (next) ready.forEach((fn) => fn());
}

/** True while a call is live (a sender is attached). */
export const isLive = () => sender !== null;

const ready = new Set<() => void>();
/** Run `fn` each time a call's sender arrives (on connect). */
export function onSenderReady(fn: () => void) {
  ready.add(fn);
  return () => ready.delete(fn);
}

export function emit<E extends UiEventName>(event: E, payload: UiEvents[E], by: By = "visitor") {
  const body = { ...payload, by };
  log.push({ event, payload: body, at: Date.now() });
  if (log.length > 60) log.shift();
  listeners.forEach((l) => l());
  if (debugMode()) console.debug(`[fernhollow] ui-event ${event}`, body);
  try {
    sender?.(event, body);
  } catch (err) {
    console.warn("ui-event not sent", err);
  }
}

export const eventLog = () => log;
export function onEventLog(fn: () => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function debugMode(): boolean {
  try {
    if (new URLSearchParams(window.location.search).has("debug")) sessionStorage.setItem("fh-debug", "1");
    return sessionStorage.getItem("fh-debug") === "1";
  } catch {
    return new URLSearchParams(window.location.search).get("debug") === "1";
  }
}
