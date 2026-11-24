/**
 * `?debug=1` only: the X1 audit. Every ring the agent makes is checked, at the
 * moment it rings, for whether the target's whole group (its closest
 * `[data-stage-group]`, or the target when the group is taller than the room)
 * is on screen: inside the window, inside every scroll area around it, and
 * not under anything that sits on top of the page (the sticky top bars, a
 * table's sticky header row, the idle dock, the call tile). The answers go to
 * `window.__paynoraRings`; `window.__paynoraMove` fires a move by hand and
 * `window.__paynoraInView(selector)` checks any element. Nothing here runs
 * outside debug mode.
 */
import type { MoveContext, Moves } from "@voqalize/stage";

const groupOf = (el: Element): Element => el.closest("[data-stage-group]") ?? el;

export interface RingCheck {
  thing: string;
  inView: boolean;
  why?: string;
  /** Covered by a box over the page with no room to clear it: the group is taller than the band beside that box. */
  unavoidable?: boolean;
}

/** What sits on top of the page; a target inside one of these is not covered by it. */
const COVERS = [".topbar", ".viewas-banner", ".site-header", ".dock:not(.is-hidden):not(.is-calling)", ".call-tile.is-tile", ".call-tile.is-mini", ".lead-card", ".lead-tab"];

interface Box {
  top: number;
  bottom: number;
  left: number;
  right: number;
}
const boxOf = (els: Element[]): Box => {
  const rs = els.map((e) => e.getBoundingClientRect()).filter((r) => r.width || r.height);
  if (!rs.length) return { top: 0, bottom: 0, left: 0, right: 0 };
  return {
    top: Math.min(...rs.map((r) => r.top)),
    bottom: Math.max(...rs.map((r) => r.bottom)),
    left: Math.min(...rs.map((r) => r.left)),
    right: Math.max(...rs.map((r) => r.right)),
  };
};
const overlaps = (a: Box, b: Box) => a.left < b.right - 1 && a.right > b.left + 1 && a.top < b.bottom - 1 && a.bottom > b.top + 1;

function clips(el: Element): Element[] {
  const out: Element[] = [];
  for (let n = el.parentElement; n && n !== document.body && n !== document.documentElement; n = n.parentElement) {
    const s = getComputedStyle(n);
    if (/(auto|scroll|hidden|clip)/.test(s.overflowY + s.overflowX) && (n.scrollHeight > n.clientHeight + 1 || n.scrollWidth > n.clientWidth + 1)) out.push(n);
  }
  return out;
}

/** Is `el`'s whole group on screen and uncovered? With the reason when not. */
export function checkInView(el: Element): { inView: boolean; why?: string; unavoidable?: boolean } {
  if (!el.isConnected) return { inView: false, why: "gone" };
  const group = groupOf(el);
  let box = boxOf([group, el]);
  const covers = [...document.querySelectorAll(COVERS.join(","))].filter((c) => {
    if (c.contains(el) || el.contains(c)) return false;
    const r = c.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(c).visibility !== "hidden";
  });
  // A sticky table header row covers the rows of its own table only.
  for (const th of el.closest("table")?.querySelectorAll("thead") ?? []) if (!th.contains(el) && getComputedStyle(th.querySelector("th") ?? th).position === "sticky") covers.push(th);
  // Inside a fixed box (a drawer, the brief) the top bars are under it, not over it.
  const fixedBox = (() => {
    for (let n: Element | null = el; n && n !== document.body; n = n.parentElement) if (getComputedStyle(n).position === "fixed") return true;
    return false;
  })();
  if (fixedBox) for (let i = covers.length - 1; i >= 0; i--) if (covers[i]!.matches(".topbar, .viewas-banner, .site-header")) covers.splice(i, 1);
  const head = Math.max(0, ...covers.filter((c) => c.getBoundingClientRect().top <= 1 && c.matches(".topbar, .viewas-banner, .site-header")).map((c) => c.getBoundingClientRect().bottom));
  // A group taller than the room: the target itself must show.
  const room = window.innerHeight - head;
  if (box.bottom - box.top > room - 8) box = boxOf([el]);
  // A group wider than the screen (a table row on a phone): the target itself, across.
  if (box.right - box.left > window.innerWidth) {
    const own = boxOf([el]);
    box = { ...box, left: own.left, right: own.right };
  }
  // A target taller than the room itself: it must show from its start, under the top bars.
  const tall = box.bottom - box.top > room;
  if (tall) {
    if (box.top < head - 3 || box.top > head + room / 2) return { inView: false, why: `tall target starts at y ${Math.round(box.top)}, room ${Math.round(head)}..${window.innerHeight}` };
    box = { ...box, bottom: Math.min(box.bottom, window.innerHeight) };
  }
  if (box.top < -1 || box.bottom > window.innerHeight + 1) {
    const why = `window y ${Math.round(box.top)}..${Math.round(box.bottom)} of ${window.innerHeight}`;
    // The group cannot fit beside a box over the page (the call tile on a phone): the target itself must show, clear.
    const own = boxOf([el]);
    const side = covers.filter((c) => !c.matches(".topbar, .viewas-banner, .site-header")).map((c) => c.getBoundingClientRect()).filter((r) => r.left < box.right && r.right > box.left);
    const tight = side.some((r) => box.bottom - box.top > (r.top + r.height / 2 > window.innerHeight / 2 ? r.top - head : window.innerHeight - r.bottom) - 16);
    if (tight && own.top >= head - 1 && own.bottom <= window.innerHeight + 1 && !covers.some((c) => overlaps(own, c.getBoundingClientRect()))) {
      return { inView: false, why: `${why}, taller than the room beside the call tile; the target itself shows clear`, unavoidable: true };
    }
    return { inView: false, why };
  }
  if (box.left < -1 || box.right > window.innerWidth + 1) return { inView: false, why: `window x ${Math.round(box.left)}..${Math.round(box.right)} of ${window.innerWidth}` };
  for (const c of clips(el)) {
    const r = c.getBoundingClientRect();
    const g = group.contains(c) ? boxOf([el]) : box;
    const s = getComputedStyle(c);
    const y = s.overflowY !== "visible";
    const x = s.overflowX !== "visible";
    if ((y && (g.top < r.top - 1 || g.bottom > r.bottom + 1)) || (x && (g.left < r.left - 1 || g.right > r.right + 1))) {
      return { inView: false, why: `clipped by ${c.className || c.tagName} ${Math.round(g.top)}..${Math.round(g.bottom)} in ${Math.round(r.top)}..${Math.round(r.bottom)}` };
    }
  }
  for (const c of covers) {
    // A tall target runs under whatever sits at the foot of the screen; only its start must be clear.
    if (tall && !c.matches(".topbar, .viewas-banner, .site-header")) continue;
    const r = c.getBoundingClientRect();
    if (!overlaps(box, r)) continue;
    const why = `under ${(c.className || c.tagName).toString().split(" ").slice(0, 2).join(".")}`;
    // The room left above (or below) that box, under the top bars: if the group cannot fit there, no scroll clears it.
    const free = r.top + r.height / 2 > window.innerHeight / 2 ? r.top - head : window.innerHeight - r.bottom;
    if (!c.matches(".topbar, .viewas-banner, .site-header") && box.bottom - box.top > free - 16) {
      // The group cannot clear it: the target itself must, when it fits there.
      const own = boxOf([el]);
      if (!overlaps(own, r)) continue;
      if (own.bottom - own.top > free - 16) return { inView: false, why: `${why} (taller than the room beside it)`, unavoidable: true };
      return { inView: false, why: `${why} (the target itself)` };
    }
    return { inView: false, why };
  }
  return { inView: true };
}

const name = (el: Element) =>
  el.getAttribute("data-stage-thing") ??
  el.getAttribute("data-stage-label") ??
  el.getAttribute("data-stage-part") ??
  `${el.tagName.toLowerCase()}${el.className ? `.${String(el.className).split(" ")[0]}` : ""}`;

type W = {
  __paynoraRings?: RingCheck[];
  __paynoraMove?: (id: string, args: unknown) => Promise<unknown>;
  __paynoraInView?: (selector: string) => RingCheck;
  __paynoraFake?: (on: boolean) => void;
};

/** Log the ring's targets as they ring (debug only); returns the context's ring wrapped. */
export function auditRing(ring: MoveContext["ring"]): MoveContext["ring"] {
  return async (el, opts) => {
    const log = (window as unknown as W).__paynoraRings;
    if (log) {
      for (const e of Array.isArray(el) ? el : [el]) if (e) log.push({ thing: name(e), ...checkInView(e) });
    }
    await ring(el, opts);
  };
}

/** Install the window hooks (debug only). */
export function installAudit(moves: Moves, fake: (on: boolean) => void) {
  const w = window as unknown as W;
  let n = 0;
  w.__paynoraRings = [];
  w.__paynoraMove = (id, args) => moves.run(id, args, `audit-${++n}`);
  w.__paynoraInView = (selector) => {
    const el = document.querySelector(selector);
    return el ? { thing: name(el), ...checkInView(el) } : { thing: selector, inView: false, why: "not found" };
  };
  w.__paynoraFake = fake;
}
