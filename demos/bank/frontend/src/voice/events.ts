/**
 * UI → brain events (CONTRACT.md, "Page → brain events"). One function sends
 * them all. Until a call is live there is no sender and an event is only logged
 * (with `?debug=1`): a gesture made off-call has no brain that missed it.
 *
 * Every event says who caused it: `by: "visitor"` for the customer's own taps,
 * `by: "agent"` when it reports what the agent just did on screen.
 */
export type By = "visitor" | "agent";

export interface UiEvents {
  page_viewed: { path: string; screen: string; signed_in: boolean };
  /** The customer's own sign-in: who they are, never the mobile number or PIN. */
  signed_in: { name: string; first_name: string };
  /** Sign in pressed with a number or PIN of the wrong shape (never the digits). */
  sign_in_failed: { problem: "mobile" | "pin" };
  signed_out: Record<string, never>;
  txn_opened: { txn_id: string };
  card_control_changed: { card: "debit" | "credit"; control: string; value: string };
  action_done: { action_id: string; kind: string; outcome: "done" | "cancelled"; reference?: string; summary: string };
  form_changed: { form: "open_account" | "card_apply" | "loan_apply"; step: number; filled: string[]; missing: string[] };
  form_submitted: { form: "open_account" | "card_apply" | "loan_apply"; reference: string; summary: string };
  cards_profile_changed: { dining: number; online: number; groceries: number; travel: number; fuel: number; utilities: number; other: number; top: string[] };
  loan_calc_changed: { loan_type: string; amount: number; tenure_months: number; rate: number; emi: number };
  language_requested: { language: "en" | "hi" };
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

/** True while a call is live (a sender is attached). */
export const isLive = () => sender !== null;

/**
 * Who is acting right now: inside a Stage performer (and for a moment after),
 * a change is the agent's. Performers wrap their store writes in `asAgent`.
 */
let agentUntil = 0;
export function asAgent<T>(fn: () => T): T {
  agentUntil = Date.now() + 600;
  return fn();
}
export const currentBy = (): By => (Date.now() <= agentUntil ? "agent" : "visitor");

export function emit<E extends UiEventName>(event: E, payload: UiEvents[E], by: By = currentBy()) {
  const body = { ...payload, by };
  log.push({ event, payload: body, at: Date.now() });
  if (log.length > 80) log.shift();
  listeners.forEach((l) => l());
  if (debugMode()) console.debug(`[bank] ui-event ${event}`, body);
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
    if (new URLSearchParams(window.location.search).has("debug")) sessionStorage.setItem("globalbank-debug", "1");
    return sessionStorage.getItem("globalbank-debug") === "1";
  } catch {
    return new URLSearchParams(window.location.search).get("debug") === "1";
  }
}
