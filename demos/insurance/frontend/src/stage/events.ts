/**
 * State events, page → brain. The stores call `emit` after every change; the
 * host (src/stage/host.ts) sets the sink while a call is attached and turns each
 * into `scene.event(id, data, moves.author())`, so a change a move made is the
 * agent's and anything else the visitor's. Off-call nothing is sent; in debug
 * mode every event is logged for the console.
 */
import type { EventData, EventId } from "@voqalize/stage";
import { scene } from "./scene.gen";

type Spec = typeof scene.spec;
export type EventName = EventId<Spec>;
export type Sink = <E extends EventName>(id: E, data: EventData<Spec, E>) => void;

let sink: Sink | null = null;
const log: { id: string; data: unknown; at: number; sent: boolean }[] = [];
const listeners = new Set<() => void>();

export function setEventSink(next: Sink | null) {
  sink = next;
}

export function emit<E extends EventName>(id: E, data: EventData<Spec, E>) {
  log.push({ id, data, at: Date.now(), sent: !!sink });
  if (log.length > 60) log.shift();
  for (const fn of listeners) fn();
  try {
    sink?.(id, data);
  } catch (err) {
    console.warn("chhatri: could not send", id, err);
  }
}

export const eventLog = () => log;
export function onEventLog(fn: () => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
