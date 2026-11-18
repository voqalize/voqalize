/**
 * Stage for the whole site: one `Moves` runtime with every performer
 * registered once, for the page's life, attached to the call's client while
 * there is one. Without a call the same runtime still runs (the `?debug=1`
 * console fires moves through it), so a move made by hand looks exactly like
 * the agent's.
 *
 * State events (CONTRACT.md, "Slices and events") go out through `sendEvent`,
 * with `by` from `moves.author()`: the agent while one of its moves acts and
 * for `AGENT_WINDOW_MS` after; otherwise the visitor.
 */
import { type EventData, type EventId, Moves, Spotlight, type StageClient, type StagePage, stagePage } from "@voqalize/stage";
import { create } from "zustand";
import { scene } from "./scene.gen";

type Spec = typeof scene.spec;

export const ACCENT = "#d9822b";

export const moves = new Moves(new Spotlight({ color: ACCENT, glow: "rgba(217, 130, 43, 0.32)", radius: 10 }), {
  fixed: [".site-header"],
});

let page: StagePage | null = null;

/** The call's client, put here by the voice dock while a call is up. */
export const useCall = create<{ client: StageClient | null; live: boolean }>(() => ({ client: null, live: false }));

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

/** The route changed (or the call just came up): the brain hears where the page is. */
export const announce = () => page?.hello();

// ─── The debug log ─────────────────────────────────────────────────────────

export interface LogLine {
  at: number;
  kind: "event" | "result";
  text: string;
}
export const useStageLog = create<{ lines: LogLine[] }>(() => ({ lines: [] }));
const log = (kind: LogLine["kind"], text: string) =>
  useStageLog.setState((s) => ({ lines: [...s.lines.slice(-80), { at: Date.now(), kind, text }] }));

/** A state event the spec declares, by whoever is acting now. */
export function sendEvent<E extends EventId<Spec>>(id: E, data: EventData<Spec, E>): void {
  const who = moves.author();
  const event = scene.event(id, data, who.by === "agent" && who.callRef ? { by: "agent", callRef: who.callRef } : { by: "visitor" });
  log("event", `${event.name} by ${event.by}${event.call_ref ? ` (${event.call_ref})` : ""}: ${JSON.stringify(event.data)}`);
  page?.send(event);
}

let n = 0;
/** Run a move by hand (the debug console): the same runtime, rings and all. */
export async function runByHand(id: string, args: unknown) {
  n += 1;
  const result = await moves.run(id, args, `debug-${n}`);
  log(
    "result",
    result
      ? `${id}: ${result.outcome}${result.detail ? ` · ${result.detail}` : ""}${result.refused?.length ? ` · refused ${JSON.stringify(result.refused)}` : ""}`
      : `${id}: carried on`,
  );
  return result;
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
  const path = to.split("?")[0];
  if (currentPath() === path && !to.includes("?")) return;
  go?.(to);
  await waitFor(() => currentPath() === path, 1500);
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
}

/** Poll until `find` returns something, at most `ms`. */
export async function waitFor<T>(find: () => T | null | undefined | false, ms = 1500): Promise<T | null> {
  const end = Date.now() + ms;
  for (;;) {
    const v = find();
    if (v) return v;
    if (Date.now() > end) return null;
    await new Promise((r) => setTimeout(r, 25));
  }
}

export const el = (selector: string) => document.querySelector(selector);
export const part = (name: string) => el(`[data-stage-part="${CSS.escape(name)}"]`);
export const thing = (name: string) => el(`[data-stage-thing="${CSS.escape(name)}"]`);
