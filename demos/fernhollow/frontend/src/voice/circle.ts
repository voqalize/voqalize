/**
 * Circle to ask (CONTRACT.md v3): the shopper draws a loop round things on
 * the page, and what is inside it becomes "these" for Emily.
 *
 * A thing is any element tagged `data-fh-thing="<kind>:<id>"` (product,
 * category, room, article). This module holds the geometry (which boxes a
 * loop holds), the smoothing of the stroke, and the selection itself, which
 * outlives navigation until the shopper or Emily clears it.
 */
import { create } from "zustand";
import { type By, emit, onSenderReady } from "./events";

export type ThingKind = "product" | "category" | "room" | "article";
export interface Thing {
  kind: ThingKind;
  id: string;
}
export interface Point {
  x: number;
  y: number;
}
export interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

export const MAX_SELECTED = 8;
const KINDS = new Set<ThingKind>(["product", "category", "room", "article"]);

export function parseThing(tag: string | null | undefined): Thing | null {
  if (!tag) return null;
  const i = tag.indexOf(":");
  const kind = tag.slice(0, i) as ThingKind;
  const id = tag.slice(i + 1);
  return i > 0 && KINDS.has(kind) && id ? { kind, id } : null;
}
export const thingKey = (t: Thing) => `${t.kind}:${t.id}`;

/** Ray casting: is `p` inside the closed polygon `loop`? */
export function inside(p: Point, loop: Point[]): boolean {
  let hit = false;
  for (let i = 0, j = loop.length - 1; i < loop.length; j = i++) {
    const a = loop[i];
    const b = loop[j];
    if (a.y > p.y !== b.y > p.y && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y || 1e-9) + a.x) hit = !hit;
  }
  return hit;
}

/** The share of `box` the loop encloses, sampled on a 7 × 7 grid. */
export function coverage(box: Box, loop: Point[]): number {
  if (loop.length < 3 || box.width <= 0 || box.height <= 0) return 0;
  const N = 7;
  let n = 0;
  for (let i = 0; i < N; i++)
    for (let j = 0; j < N; j++) {
      const p = { x: box.left + ((i + 0.5) / N) * box.width, y: box.top + ((j + 0.5) / N) * box.height };
      if (inside(p, loop)) n++;
    }
  return n / (N * N);
}

/**
 * The things a loop selects: each whose box is at least half inside, once,
 * in reading order (top to bottom, then left to right), at most eight.
 */
export function thingsInLoop(loop: Point[], candidates: { thing: Thing; box: Box }[], min = 0.5): Thing[] {
  const seen = new Set<string>();
  return candidates
    .filter((c) => coverage(c.box, loop) >= min)
    .sort((a, b) => (Math.abs(a.box.top - b.box.top) > 24 ? a.box.top - b.box.top : a.box.left - b.box.left))
    .map((c) => c.thing)
    .filter((t) => {
      const k = thingKey(t);
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    })
    .slice(0, MAX_SELECTED);
}

/** Every tagged thing on screen right now, with its box. Nested tags count once, by the outer one. */
export function thingsOnScreen(root: ParentNode = document): { thing: Thing; box: Box; el: Element }[] {
  const out: { thing: Thing; box: Box; el: Element }[] = [];
  for (const el of root.querySelectorAll("[data-fh-thing]")) {
    if (el.parentElement?.closest("[data-fh-thing]")) continue;
    const thing = parseThing(el.getAttribute("data-fh-thing"));
    const r = el.getBoundingClientRect();
    if (!thing || r.width === 0 || r.bottom < 0 || r.top > window.innerHeight) continue;
    out.push({ thing, el, box: { left: r.left, top: r.top, width: r.width, height: r.height } });
  }
  return out;
}

/** The loop's length, to tell a circle from a stray Shift-click. */
export function pathLength(pts: Point[]): number {
  let d = 0;
  for (let i = 1; i < pts.length; i++) d += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
  return d;
}

/** A smooth SVG path through the points (quadratic curves through the midpoints). */
export function smoothPath(pts: Point[], close = false): string {
  if (pts.length < 2) return pts.length ? `M${pts[0].x},${pts[0].y}` : "";
  let d = `M${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const mx = (pts[i].x + pts[i + 1].x) / 2;
    const my = (pts[i].y + pts[i + 1].y) / 2;
    d += ` Q${pts[i].x.toFixed(1)},${pts[i].y.toFixed(1)} ${mx.toFixed(1)},${my.toFixed(1)}`;
  }
  const last = pts[pts.length - 1];
  d += ` L${last.x.toFixed(1)},${last.y.toFixed(1)}`;
  return close ? `${d} Z` : d;
}

// ── The selection ──────────────────────────────────────────────────────────

interface SelectionState {
  things: Thing[];
  page: string;
  /** The next touch circle adds to the selection ("+ Add more" on the chip). */
  addNext: boolean;
  select(things: Thing[], page: string): void;
  /** Add to what is selected: kept in order, new ones after, once each, eight at most. */
  add(things: Thing[], page: string): void;
  clear(by?: By): void;
}

export const useSelection = create<SelectionState>((set, get) => ({
  things: [],
  page: "",
  addNext: false,
  add(things, page) {
    const have = get().things;
    const keys = new Set(have.map(thingKey));
    const all = [...have, ...things.filter((t) => !keys.has(thingKey(t)))].slice(0, MAX_SELECTED);
    set({ things: all, page, addNext: false });
    if (all.length) emit("selection", { things: all, gesture: "circle", page });
  },
  select(things, page) {
    if (get().things.length) emit("selection_cleared", {});
    set({ things, page, addNext: false });
    emit("selection", { things, gesture: "circle", page });
  },
  clear(by = "visitor") {
    if (!get().things.length) return;
    set({ things: [], page: "", addNext: false });
    // Emily's own clear_selection is hers; the event reports the shopper's.
    if (by === "visitor") emit("selection_cleared", {});
  },
}));

// A circle drawn before the call started still reaches the brain once it connects.
onSenderReady(() => {
  const { things, page } = useSelection.getState();
  if (things.length) emit("selection", { things, gesture: "circle", page });
});
