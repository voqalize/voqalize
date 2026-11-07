/**
 * Where the widget sits on the page: the anchors, snapping to the nearest
 * one, free placement with clamping, keeping clear of page elements, and
 * remembering a moved widget.
 *
 * The geometry is the Site Agent snippet's (`loader/place.ts`), ported so the
 * widget lands where the snippet's tile did: a margin from the edges, bottom
 * anchors a little higher than the margin, and the same fallback order when
 * an anchor is blocked. `bottom-center` is new here.
 *
 * Everything is pure math on rectangles except `PlacementController`, which
 * holds the result as a store, and `rememberedPlace`/`rememberPlace`, which
 * read and write storage inside try/catch: storage can be missing, full,
 * blocked by the browser or throw on access in a sandboxed frame, and none of
 * that may stop the widget from appearing.
 */

import type { Anchor, MoveMode, RememberMode } from "../config/types.js";
import { Store } from "./store.js";

export interface Size {
  width: number;
  height: number;
}

export interface Point {
  x: number;
  y: number;
}

export interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface Viewport extends Size {}

/** The snippet's bottom anchors sit this much higher than the margin. */
export const BOTTOM_LIFT = 4;

export const ANCHORS: readonly Anchor[] = [
  "bottom-right",
  "bottom-left",
  "bottom-center",
  "top-right",
  "top-left",
  "middle-right",
  "middle-left",
];

export interface Margins {
  x: number;
  y: number;
  /** Height at the top the widget never covers. */
  topClear: number;
}

export function marginsFrom(offset: number | { x: number; y: number }, topClear = 0): Margins {
  return typeof offset === "number"
    ? { x: offset, y: offset, topClear }
    : { x: offset.x, y: offset.y, topClear };
}

/** The top-left corner of a box of `size` placed at `anchor`. */
export function boxAt(anchor: Anchor, size: Size, view: Viewport, m: Margins): Point {
  const [vertical, horizontal] = anchor.split("-") as [string, string];
  let x: number;
  if (horizontal === "left") x = m.x;
  else if (horizontal === "right") x = view.width - m.x - size.width;
  else x = (view.width - size.width) / 2;
  let y: number;
  if (vertical === "top") y = m.y + m.topClear;
  else if (vertical === "bottom") y = view.height - m.y - BOTTOM_LIFT - size.height;
  else y = (view.height - size.height) / 2;
  return clampPoint({ x, y }, size, view, m);
}

/** Keep a box of `size` at `p` inside the viewport, its margins and `topClear`. */
export function clampPoint(p: Point, size: Size, view: Viewport, m: Margins): Point {
  const minX = m.x;
  const maxX = Math.max(minX, view.width - m.x - size.width);
  const minY = m.y + m.topClear;
  const maxY = Math.max(minY, view.height - m.y - size.height);
  return {
    x: Math.min(maxX, Math.max(minX, p.x)),
    y: Math.min(maxY, Math.max(minY, p.y)),
  };
}

function centre(p: Point, size: Size): Point {
  return { x: p.x + size.width / 2, y: p.y + size.height / 2 };
}

/** The anchor whose box centre is closest to where a box at `p` was dropped. */
export function nearestAnchor(
  p: Point,
  size: Size,
  view: Viewport,
  m: Margins,
  anchors: readonly Anchor[] = ANCHORS,
): Anchor {
  const c = centre(p, size);
  let best = anchors[0] ?? "bottom-right";
  let bestDistance = Infinity;
  for (const anchor of anchors) {
    const a = centre(boxAt(anchor, size, view, m), size);
    const distance = (a.x - c.x) ** 2 + (a.y - c.y) ** 2;
    if (distance < bestDistance) {
      bestDistance = distance;
      best = anchor;
    }
  }
  return best;
}

export function overlaps(a: Rect, b: Rect): boolean {
  return a.left < b.left + b.width && b.left < a.left + a.width && a.top < b.top + b.height && b.top < a.top + a.height;
}

/**
 * The order anchors are tried in when `preferred` is blocked: the same side,
 * bottom then middle then top, then the other side the same way, then the
 * bottom centre. The snippet's order, with the centre added last.
 */
export function fallbackOrder(preferred: Anchor): Anchor[] {
  const side = preferred.endsWith("left") ? "left" : preferred.endsWith("right") ? "right" : "right";
  const other = side === "left" ? "right" : "left";
  const order: Anchor[] = [preferred];
  for (const s of [side, other]) {
    for (const v of ["bottom", "middle", "top"]) {
      const anchor = `${v}-${s}` as Anchor;
      if (!order.includes(anchor)) order.push(anchor);
    }
  }
  if (!order.includes("bottom-center")) order.push("bottom-center");
  return order;
}

function rectAt(p: Point, size: Size): Rect {
  return { left: p.x, top: p.y, width: size.width, height: size.height };
}

/**
 * Where a box goes when it must keep clear of `avoid`: the preferred anchor
 * if it is clear; else the box lifted above whatever it overlaps at that
 * anchor, if that still fits; else the first clear anchor in
 * `fallbackOrder`; else the preferred anchor regardless — a widget over a
 * page element beats no widget.
 */
export function clearPlace(
  preferred: Anchor,
  size: Size,
  view: Viewport,
  m: Margins,
  avoid: readonly Rect[],
): { anchor: Anchor; point: Point } {
  const at = boxAt(preferred, size, view, m);
  const hits = avoid.filter((r) => overlaps(rectAt(at, size), r));
  if (hits.length === 0) return { anchor: preferred, point: at };

  if (preferred.startsWith("bottom")) {
    const lifted = { x: at.x, y: Math.min(...hits.map((r) => r.top)) - m.y - size.height };
    if (lifted.y >= m.y + m.topClear && !avoid.some((r) => overlaps(rectAt(lifted, size), r))) {
      return { anchor: preferred, point: lifted };
    }
  }

  for (const anchor of fallbackOrder(preferred).slice(1)) {
    const p = boxAt(anchor, size, view, m);
    if (!avoid.some((r) => overlaps(rectAt(p, size), r))) return { anchor, point: p };
  }
  return { anchor: preferred, point: at };
}

// ------------------------------------------------------------------ remember

/** A place a visitor moved the widget to. Free places are stored as viewport fractions. */
export type RememberedPlace = { anchor: Anchor } | { free: { fx: number; fy: number } };

export function rememberKey(agent: string | undefined): string {
  return `voqalize:widget:place:${agent ?? "default"}`;
}

function storageFor(remember: RememberMode, scope: typeof globalThis): Storage | null {
  try {
    if (remember === "tab") return scope.sessionStorage ?? null;
    if (remember === "site") return scope.localStorage ?? null;
  } catch {
    // Access itself throws in a sandboxed frame or with site data blocked.
  }
  return null;
}

export function rememberedPlace(
  remember: RememberMode,
  agent: string | undefined,
  scope: typeof globalThis = globalThis,
): RememberedPlace | null {
  const storage = storageFor(remember, scope);
  if (!storage) return null;
  try {
    const raw = storage.getItem(rememberKey(agent));
    if (!raw) return null;
    const value = JSON.parse(raw) as unknown;
    if (typeof value !== "object" || value === null) return null;
    const v = value as Record<string, unknown>;
    if (typeof v.anchor === "string" && (ANCHORS as readonly string[]).includes(v.anchor)) {
      return { anchor: v.anchor as Anchor };
    }
    const free = v.free as Record<string, unknown> | undefined;
    if (free && typeof free.fx === "number" && typeof free.fy === "number") {
      const fx = Math.min(1, Math.max(0, free.fx));
      const fy = Math.min(1, Math.max(0, free.fy));
      return { free: { fx, fy } };
    }
  } catch {
    // A corrupt or unreadable entry is no entry.
  }
  return null;
}

export function rememberPlace(
  remember: RememberMode,
  agent: string | undefined,
  place: RememberedPlace,
  scope: typeof globalThis = globalThis,
): void {
  const storage = storageFor(remember, scope);
  if (!storage) return;
  try {
    storage.setItem(rememberKey(agent), JSON.stringify(place));
  } catch {
    // Full or blocked: the place is simply not remembered.
  }
}

// ---------------------------------------------------------------- controller

export interface PlacementSnapshot {
  anchor: Anchor;
  /** Top-left of the widget, in viewport px. */
  point: Point;
  /** Whether the widget is where a drag left it rather than at an anchor. */
  free: boolean;
  dragging: boolean;
}

export interface PlacementOptions {
  anchor: Anchor;
  move: MoveMode;
  remember: RememberMode;
  offset: number | { x: number; y: number };
  topClear: number;
  agent?: string;
  /** Touch screens only snap: free placement under a thumb lands anywhere. */
  touch?: boolean;
  scope?: typeof globalThis;
}

export class PlacementController extends Store<PlacementSnapshot> {
  private readonly options: PlacementOptions;
  private readonly margins: Margins;
  private size: Size = { width: 0, height: 0 };
  private view: Viewport = { width: 0, height: 0 };
  private avoid: Rect[] = [];
  private preferred: Anchor;
  private freeAt: { fx: number; fy: number } | null = null;
  private dragFrom: { pointer: Point; box: Point } | null = null;

  constructor(options: PlacementOptions) {
    super({ anchor: options.anchor, point: { x: 0, y: 0 }, free: false, dragging: false });
    this.options = options;
    this.margins = marginsFrom(options.offset, options.topClear);
    this.preferred = options.anchor;
    if (options.move !== "fixed") {
      const remembered = rememberedPlace(options.remember, options.agent, options.scope);
      if (remembered && "anchor" in remembered) this.preferred = remembered.anchor;
      else if (remembered && this.mode() === "free") this.freeAt = remembered.free;
    }
  }

  private mode(): MoveMode {
    return this.options.touch && this.options.move === "free" ? "snap" : this.options.move;
  }

  /** The widget's size, the viewport, and the rectangles to keep clear of. */
  layout(size: Size, view: Viewport, avoid: readonly Rect[] = []): void {
    this.size = size;
    this.view = view;
    this.avoid = [...avoid];
    this.place();
  }

  startDrag(pointer: Point): boolean {
    if (this.mode() === "fixed") return false;
    this.dragFrom = { pointer, box: this.getSnapshot().point };
    this.set({ dragging: true });
    return true;
  }

  drag(pointer: Point): void {
    if (!this.dragFrom) return;
    const p = {
      x: this.dragFrom.box.x + pointer.x - this.dragFrom.pointer.x,
      y: this.dragFrom.box.y + pointer.y - this.dragFrom.pointer.y,
    };
    this.set({ point: clampPoint(p, this.size, this.view, this.margins) });
  }

  endDrag(): void {
    if (!this.dragFrom) return;
    this.dragFrom = null;
    const { point } = this.getSnapshot();
    if (this.mode() === "free") {
      const roomX = Math.max(1, this.view.width - this.size.width);
      const roomY = Math.max(1, this.view.height - this.size.height);
      this.freeAt = { fx: point.x / roomX, fy: point.y / roomY };
      rememberPlace(this.options.remember, this.options.agent, { free: this.freeAt }, this.options.scope);
    } else {
      this.freeAt = null;
      this.preferred = nearestAnchor(point, this.size, this.view, this.margins);
      rememberPlace(this.options.remember, this.options.agent, { anchor: this.preferred }, this.options.scope);
    }
    this.set({ dragging: false });
    this.place();
  }

  private place(): void {
    if (this.dragFrom) return;
    if (this.freeAt) {
      const roomX = Math.max(0, this.view.width - this.size.width);
      const roomY = Math.max(0, this.view.height - this.size.height);
      const point = clampPoint(
        { x: this.freeAt.fx * roomX, y: this.freeAt.fy * roomY },
        this.size,
        this.view,
        this.margins,
      );
      this.set({ point, free: true, anchor: nearestAnchor(point, this.size, this.view, this.margins) });
      return;
    }
    const { anchor, point } = clearPlace(this.preferred, this.size, this.view, this.margins, this.avoid);
    this.set({ anchor, point, free: false });
  }
}
