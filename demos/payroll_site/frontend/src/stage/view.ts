/**
 * Bring what a move is about to ring into view as a whole (owner, round 1,
 * X1): not just the one element, but the group it belongs to — the whole
 * price breakdown, the whole set of module checkboxes, the whole slot list of
 * the day, the whole booking form — so nothing the agent points at is cut off.
 *
 * A group is the closest ancestor marked `data-stage-group`. Inner scroll
 * areas (the brief's body, the phone's day strip) are scrolled first, then the
 * page through Stage's own `c.scrollTo`. When the group is taller than the
 * screen, the elements themselves are brought in instead, all of them when
 * they fit together.
 */
import { type MoveContext, pinnedHeight } from "@voqalize/stage";

const GROUP = "[data-stage-group]";
const FIXED = [".site-header"];
const PAD = 12;

type R = { top: number; bottom: number; left: number; right: number };

function union(els: Element[]): R {
  const rs = els.map((e) => e.getBoundingClientRect());
  return {
    top: Math.min(...rs.map((r) => r.top)),
    bottom: Math.max(...rs.map((r) => r.bottom)),
    left: Math.min(...rs.map((r) => r.left)),
    right: Math.max(...rs.map((r) => r.right)),
  };
}

/** The scrollable ancestors of `el`, innermost first (not the page itself). */
function scrollers(el: Element): HTMLElement[] {
  const out: HTMLElement[] = [];
  for (let p = el.parentElement; p && p !== document.body && p !== document.documentElement; p = p.parentElement) {
    const s = getComputedStyle(p);
    const y = /(auto|scroll)/.test(s.overflowY) && p.scrollHeight > p.clientHeight + 1;
    const x = /(auto|scroll)/.test(s.overflowX) && p.scrollWidth > p.clientWidth + 1;
    if (x || y) out.push(p);
  }
  return out;
}

function inFixed(el: Element): boolean {
  for (let p: Element | null = el; p && p !== document.body; p = p.parentElement) {
    if (getComputedStyle(p).position === "fixed") return true;
  }
  return false;
}

const reduced = () => !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** Scroll `s` so `r` (viewport coordinates) is inside it; false when it already was. */
function scrollWithin(s: HTMLElement, r: R): boolean {
  const b = s.getBoundingClientRect();
  const edge = (lo: number, hi: number, blo: number, bhi: number) =>
    lo < blo + PAD ? lo - blo - PAD : hi > bhi - PAD ? Math.min(hi - bhi + PAD, lo - blo - PAD) : 0;
  const dy = edge(r.top, r.bottom, b.top, b.bottom);
  const dx = edge(r.left, r.right, b.left, b.right);
  if (Math.abs(dy) < 2 && Math.abs(dx) < 2) return false;
  if (typeof s.scrollBy === "function") s.scrollBy({ top: dy, left: dx, behavior: reduced() ? "auto" : "smooth" });
  else {
    s.scrollTop += dy;
    s.scrollLeft += dx;
  }
  return true;
}

/** Where the screen's free room ends: above the agent's dock pill when it
 *  sits at the bottom (not during a call, when the pill is gone). */
function bottomEdge(): number {
  const d = document.querySelector(".dock");
  if (!d || /\bis-(calling|hidden|raised)\b/.test(d.className)) return window.innerHeight;
  const top = d.getBoundingClientRect().top;
  return top > 0 ? Math.min(window.innerHeight, top - 8) : window.innerHeight;
}

/** The window's room between the pinned header and the dock, in px. */
function room(): { head: number; height: number; bottom: number } {
  const head = pinnedHeight(FIXED);
  const bottom = bottomEdge();
  return { head, height: bottom - head, bottom };
}

/** Scroll the page so the box `r` sits in the room (centred when it fits). */
async function scrollPageTo(r: R): Promise<void> {
  const { head, height } = room();
  const h = r.bottom - r.top;
  const want = h > height - 2 * PAD ? head + PAD : head + (height - h) / 2;
  const delta = r.top - want;
  if (Math.abs(delta) < 8) return;
  window.scrollBy({ top: delta, behavior: reduced() ? "auto" : "smooth" });
  // Wait for it, at most about as long as Stage's own scroll waits.
  const until = Date.now() + 800;
  let last = -1;
  while (Date.now() < until) {
    await sleep(80);
    if (Math.abs(window.scrollY - last) < 1) return;
    last = window.scrollY;
  }
}

/** True when every element is wholly on screen, under the header. */
export function wholeInView(els: Element[]): boolean {
  if (!els.length) return true;
  const r = union(els);
  const { head, bottom } = room();
  return r.top >= head && r.bottom <= bottom && r.left >= 0 && r.right <= window.innerWidth;
}

/** Bring `target` (one element or several) and its group into view. */
export async function bringIntoView(c: MoveContext, target: Element | Element[]): Promise<void> {
  const els = (Array.isArray(target) ? target : [target]).filter(Boolean);
  if (!els.length) return;
  const first = els[0];
  const g = first.closest(GROUP);
  const group = g && els.every((e) => g.contains(e)) ? g : null;

  // Inner scroll areas first, innermost out: the group when it fits in one.
  let moved = false;
  for (const s of scrollers(first)) {
    const box = group && group !== s && s.contains(group) ? group.getBoundingClientRect() : null;
    const fits = box && box.height <= s.clientHeight - 2 * PAD && box.width <= s.clientWidth - 2 * PAD;
    moved = scrollWithin(s, fits ? box : union(els)) || moved;
  }
  if (moved) await sleep(reduced() ? 0 : 320);

  // A fixed panel (the brief) does not move with the page.
  if (inFixed(first)) return;

  const { height } = room();
  if (group && group.getBoundingClientRect().height <= height - 2 * PAD) {
    if (wholeInView([group])) return;
    await c.scrollTo(group);
    // Stage centres under the header; the dock may still cover its foot.
    if (!wholeInView([group])) await scrollPageTo(union([group]));
    return;
  }
  if (wholeInView(els)) return;
  if (els.length === 1) {
    await c.scrollTo(first);
    if (!wholeInView(els) && first.getBoundingClientRect().height <= height - 2 * PAD) await scrollPageTo(union(els));
  } else await scrollPageTo(union(els));
}
