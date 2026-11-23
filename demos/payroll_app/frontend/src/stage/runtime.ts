/**
 * Stage for the whole app: ONE `Moves` (with its spotlight in Paynora's
 * green), made at start and independent of any call, so `?debug=1` and the
 * tests run the same performers a live call does. When a call exists,
 * `attach` puts it on that client with `stagePage`; until then results and
 * events are only logged.
 *
 * Every state event goes through `emit`, which takes `by` from
 * `moves.author()`: the agent while one of its moves acts (and a beat after),
 * else the visitor.
 */
import { Moves, Spotlight, type StageClient, type StagePage, stagePage } from "@voqalize/stage";
import type { EventData, EventId } from "@voqalize/stage";
import { PRODUCT } from "../lib/data";
import { scene } from "./scene.gen";

type Spec = typeof scene.spec;

export const moves = new Moves(new Spotlight({ color: PRODUCT.brand.palette.primary, radius: 8 }), {
  fixed: [".topbar"],
});

let page: StagePage | null = null;

export interface LoggedEvent {
  kind: "event" | "result" | "site";
  name: string;
  by?: string;
  data: unknown;
  at: number;
}
const log: LoggedEvent[] = [];
const listeners = new Set<() => void>();
function push(e: LoggedEvent) {
  log.push(e);
  if (log.length > 80) log.shift();
  listeners.forEach((fn) => fn());
}
export const eventLog = () => log;
export function onEventLog(fn: () => void) {
  listeners.add(fn);
  return () => void listeners.delete(fn);
}
export const logResult = (name: string, data: unknown) => push({ kind: "result", name, data, at: Date.now() });

/** A Stage state event, from the spec's slice, by whoever made the change. */
export function emit<E extends EventId<Spec>>(id: E, data: EventData<Spec, E>) {
  const who = moves.author();
  const ev = scene.event(id, data, who);
  push({ kind: "event", name: id, by: ev.by, data: ev.data, at: Date.now() });
  try {
    page?.send(ev);
  } catch (err) {
    console.warn("stage event not sent", err);
  }
}

/** Put Stage on the live call's client. Returns the detach. */
export function attach(client: StageClient, onSiteCommand: (command: string, payload: unknown) => void): () => void {
  page?.detach();
  const p = stagePage(client, moves, {
    onSiteCommand: (command, payload) => {
      push({ kind: "site", name: command, data: payload, at: Date.now() });
      onSiteCommand(command, payload);
    },
  });
  page = p;
  return () => {
    p.detach();
    if (page === p) page = null;
  };
}

/** `stage_hello` for the page in front (on connect and on every route change). */
export const hello = () => page?.hello();
