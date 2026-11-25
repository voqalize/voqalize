/**
 * Stage for the whole site: one `Moves` runtime with every performer
 * registered for the page's life, attached to the call's client while there is
 * one. Without a call the same runtime still runs (the `?debug=1` console fires
 * moves through it), so a move made by hand looks exactly like the agent's.
 *
 * State events (CONTRACT.md, "Page → brain") go out through `sendEvent`, with
 * `by` taken from `moves.author()`: the agent while one of its moves acts, and
 * for a moment after; otherwise the visitor.
 */
import { Moves, Spotlight, type StageClient, type StagePage, stagePage } from "@voqalize/stage";
import type { EventData, EventId } from "@voqalize/stage";
import { create } from "zustand";
import { scene } from "./scene.gen";
import { showWhole } from "./view";

type Spec = typeof scene.spec;

export const moves = new Moves(new Spotlight({ color: "#d6246e", glow: "rgba(214, 36, 110, 0.28)", radius: 12 }), {
  fixed: [".site-header"],
  // X1: every scroll a move makes shows the target's whole group, inner
  // scroll areas (the filter column or sheet, day tabs, tables) included,
  // then the window with Stage's own scroll and timing.
  extend: (c) => {
    const windowScroll = c.scrollTo;
    return { scrollTo: (el: Element) => showWhole(el, windowScroll) };
  },
});

let page: StagePage | null = null;

/** The call's client, put here by the voice dock while a call is up. */
export const useCall = create<{ client: StageClient | null; live: boolean; begin: (() => void) | null }>(() => ({
  client: null,
  live: false,
  begin: null,
}));

/** Attach Stage to the call's client; returns the detach. */
export function attachCall(client: StageClient, lang: string, onSiteCommand: (command: string, payload: unknown) => void): () => void {
  page?.detach();
  page = stagePage(client, moves, { lang, onSiteCommand });
  const mine = page;
  return () => {
    mine.detach();
    if (page === mine) page = null;
  };
}

/** The route changed: the agent hears where the page is now. */
export const announce = () => page?.hello();

export interface LogLine {
  at: number;
  kind: "event" | "result";
  text: string;
}
export const useStageLog = create<{ lines: LogLine[] }>(() => ({ lines: [] }));
const log = (kind: LogLine["kind"], text: string) =>
  useStageLog.setState((s) => ({ lines: [...s.lines.slice(-60), { at: Date.now(), kind, text }] }));

/** A state event the spec declares, by whoever is acting now. */
export function sendEvent<E extends EventId<Spec>>(id: E, data: EventData<Spec, E>): void {
  const who = moves.author();
  const event = scene.event(id, data, who.by === "agent" ? { by: "agent", callRef: who.callRef } : { by: "visitor" });
  log("event", `${event.name} by ${event.by}: ${JSON.stringify(event.data)}`);
  page?.send(event);
}

let n = 0;
/** Run a move by hand (the debug console): the same runtime, rings and all. */
export async function runByHand(id: string, args: unknown): Promise<void> {
  n += 1;
  const result = await moves.run(id, args, `debug-${n}`);
  log("result", result ? `${id}: ${result.outcome}${result.detail ? ` · ${result.detail}` : ""}${result.refused?.length ? ` · refused ${JSON.stringify(result.refused)}` : ""}` : `${id}: carried on`);
}

// ─── Navigation from a performer ───────────────────────────────────────────

let go: ((to: string) => void) | null = null;
let here: () => string = () => "/";
export function bindRouter(navigate: (to: string) => void, current: () => string): () => void {
  go = navigate;
  here = current;
  return () => {
    go = null;
  };
}
export const currentPath = () => here();

/** Go to `to` (a router path) unless already there, and wait for the page to draw. */
export async function goTo(to: string): Promise<void> {
  if (currentPath() === to.split("?")[0] && !to.includes("?")) return;
  go?.(to);
  await waitFor(() => currentPath() === to.split("?")[0], 1500);
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
}

/** Poll until `find` returns something, at most `ms`. */
export async function waitFor<T>(find: () => T | null | undefined | false, ms = 1200): Promise<T | null> {
  const end = Date.now() + ms;
  for (;;) {
    const v = find();
    if (v) return v;
    if (Date.now() > end) return null;
    await new Promise((r) => setTimeout(r, 30));
  }
}

export const el = (selector: string) => document.querySelector(selector);
export const part = (name: string) => el(`[data-stage-part="${CSS.escape(name)}"]`);
export const thing = (name: string) => el(`[data-stage-thing="${CSS.escape(name)}"]`);
