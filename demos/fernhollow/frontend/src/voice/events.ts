/**
 * UI → brain events (CONTRACT.md, "UI → brain events"). One function sends
 * them all. Until a call is live there is no sender and an event is only
 * logged (with `?debug=1`) — a gesture made off-call has no brain that missed it.
 *
 * Every event the shopper caused carries `by: "visitor"`; events that merely
 * report what Mira just did on screen carry `by: "mira"`.
 */
export type By = "visitor" | "mira";

export interface CartLine {
  product_id: string;
  variant_id: string;
  qty: number;
}

export interface UiEvents {
  page_viewed: { path: string };
  product_viewed: { product_id: string; variant_id: string };
  visible_products: { product_ids: string[] };
  variant_selected: { product_id: string; variant_id: string };
  filter_changed: { filters: Record<string, unknown> };
  room_board_edited: { slot: string; action: string };
  cart_changed: { lines: CartLine[]; total: number };
  confirm_result: { confirmed: boolean };
  shortlist_changed: { product_ids: string[] };
}
export type UiEventName = keyof UiEvents;

type Sender = (event: string, payload?: unknown) => void;
let sender: Sender | null = null;
const log: { event: string; payload: unknown; at: number }[] = [];
const listeners = new Set<() => void>();

/** The live call's `client.sendUIEvent`, or null when the call ends. */
export function setEventSender(next: Sender | null) {
  sender = next;
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
