/**
 * Stage for the whole site: one `Moves` runtime with every performer registered
 * for the page's life, attached to the call's client while there is one.
 * Without a call the same runtime still runs (the `?debug=1` console fires moves
 * through it), so a move made by hand looks exactly like the agent's.
 *
 * What the visitor (or a move) changes in the store goes to the agent as the
 * spec's state events (`report.ts`), with `by` from `moves.author()`.
 */
import { Moves, Spotlight, type StageClient, type StagePage, stagePage, type EventData, type EventId } from "@voqalize/stage";
import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { create } from "zustand";
import { BRAND, SITE } from "../data/product";
import { startReporting } from "./report";
import { scene } from "./scene.gen";
import { performers } from "./performers";
import { auditRing, installAudit } from "./audit";
import { wholeMoves } from "./view";
import { useFakeCall } from "../voice/fakeCall";

const debug = new URLSearchParams(window.location.search).has("debug");

type Spec = typeof scene.spec;

export const moves = new Moves(
  new Spotlight({ color: BRAND.palette.accent, glow: "rgba(232, 163, 61, 0.32)", radius: 12, width: 3 }),
  {
    fixed: [".site-header"],
    // X1: every scroll a move makes, and every ring, first shows the target's
    // whole group, clear of the header, the dock, the call tile and the brief (`view.ts`).
    extend: (c) => wholeMoves(c, debug ? auditRing : undefined),
  },
);
if (debug) installAudit(moves, (on) => useFakeCall.setState({ state: on ? "listening" : "idle" }));
scene.registerAll(moves, performers());

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
  reportScreen();
  return () => {
    mine.detach();
    if (page === mine) page = null;
  };
}

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

/** A typed site event outside the spec (the language toggle). */
export function sendSiteEvent(name: string, payload: Record<string, unknown>): void {
  log("event", `${name}: ${JSON.stringify(payload)}`);
  useCall.getState().client?.sendUIEvent(name, payload);
}

let n = 0;
/** Run a move by hand (the debug console): the same runtime, rings and all. */
export async function runByHand(id: string, args: unknown): Promise<void> {
  n += 1;
  const result = await moves.run(id, args, `debug-${n}`);
  log(
    "result",
    result
      ? `${id}: ${result.outcome}${result.detail ? ` · ${result.detail}` : ""}${result.refused?.length ? ` · refused ${JSON.stringify(result.refused)}` : ""}`
      : `${id}: carried on`,
  );
}

// ─── Navigation from a performer ───────────────────────────────────────────

let go: ((to: string) => void) | null = null;
let here = "/";
export const currentPath = () => here;

/** Go to `to` (a router path) unless already there, and wait for it to draw. */
export async function goTo(to: string): Promise<void> {
  if (here === to) return;
  go?.(to);
  const end = Date.now() + 1500;
  while (here !== to && Date.now() < end) await new Promise((r) => setTimeout(r, 30));
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
}

export function titleOf(path: string): string {
  const pages = SITE.pages as Record<string, string>;
  if (path.startsWith("/modules/")) return `Module: ${path.split("/")[2]}`;
  return pages[path] ?? path;
}

function reportScreen(): void {
  sendEvent("screen.viewed", { path: here, title: titleOf(here) });
}

/** Mounted once inside the router: binds navigation and reports each page. */
export function StageHost(): null {
  const navigate = useNavigate();
  const location = useLocation();
  useEffect(() => {
    go = (to) => navigate(to);
    return () => {
      go = null;
    };
  }, [navigate]);
  useEffect(() => {
    here = location.pathname.replace(/\/$/, "") || "/";
    reportScreen();
  }, [location.pathname]);
  useEffect(() => startReporting(sendEvent, () => moves.author().by === "agent"), []);
  return null;
}

// ─── DOM lookups the performers share ──────────────────────────────────────

export const thing = (name: string) => document.querySelector(`[data-stage-thing="${CSS.escape(name)}"]`);
export const part = (name: string) => document.querySelector(`[data-stage-part="${CSS.escape(name)}"]`);

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
