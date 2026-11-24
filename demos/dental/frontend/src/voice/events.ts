/**
 * Page → brain events (CONTRACT.md, "Page → brain events"), typed by the
 * brain's generated `events.gen.ts`. One function sends them all. Until a call
 * is live there is no sender and an event is only logged — a gesture made
 * off-call has no brain that missed it. Every event carries `by`.
 */
import type { AppEvent, AppEventName } from "./events.gen";

export type By = "visitor" | "agent";

export type UiEvents = { [E in AppEventName]: Omit<Extract<AppEvent, { event: E }>["payload"], "by"> };
export type UiEventName = keyof UiEvents;

type Sender = (event: string, payload?: unknown) => void;
let sender: Sender | null = null;
const log: { event: string; payload: unknown; at: number; sent: boolean }[] = [];
const listeners = new Set<() => void>();
const ready = new Set<() => void>();

/** The live call's `client.sendUIEvent`, or null when the call ends. */
export function setEventSender(next: Sender | null) {
  sender = next;
  if (next) ready.forEach((fn) => fn());
}

export const isLive = () => sender !== null;

/** Run `fn` each time a call's sender arrives (on connect). */
export function onSenderReady(fn: () => void) {
  ready.add(fn);
  return () => {
    ready.delete(fn);
  };
}

export function emit<E extends UiEventName>(event: E, payload: UiEvents[E], by: By = "visitor") {
  const body = { ...payload, by };
  log.push({ event, payload: body, at: Date.now(), sent: !!sender });
  if (log.length > 80) log.shift();
  listeners.forEach((l) => l());
  if (debugMode()) console.debug(`[dental] ui-event ${event}`, body);
  try {
    sender?.(event, body);
  } catch (err) {
    console.warn("ui-event not sent", err);
  }
}

export const eventLog = () => log;
export function onEventLog(fn: () => void) {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function debugMode(): boolean {
  try {
    if (new URLSearchParams(window.location.search).has("debug")) sessionStorage.setItem("dantika-debug", "1");
    return sessionStorage.getItem("dantika-debug") === "1";
  } catch {
    return new URLSearchParams(window.location.search).get("debug") === "1";
  }
}
