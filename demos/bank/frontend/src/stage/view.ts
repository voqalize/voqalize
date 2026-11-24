/**
 * X1: whenever Arjun rings or acts on something, the WHOLE group it belongs to
 * is brought into view first, not just the part he points at: both accounts on
 * the dashboard, the transaction filters, a field with its choices, the EMI
 * table, the loan calculator, the confirmation sheet's buttons. A group is the
 * closest `[data-stage-group]` around the target (or the target itself).
 *
 * `showWhole` scrolls every inner scroll area on the way (the compare table's
 * frame, the transaction detail panel, a bottom sheet's body, the app's
 * sidebar) on both axes, innermost first, then the window: under the sticky
 * site header, clear of the phone tab bar and of the agent's dock when there
 * is room. A group taller than the room shows from its top, as long as the
 * target itself still shows.
 *
 * `withWhole(c)` (applied to every performer in `host.ts`'s `useMove`) makes
 * the move's `c.scrollTo` this, and makes `c.ring` show the whole group before
 * it rings, so no performer can ring something half off screen. Adapted from
 * Paynora's `stage/view.ts`; the bank's `useStage` has no `extend` hook, so the
 * wrap happens at registration instead.
 */
import type { MoveContext } from "@voqalize/stage";

const MARGIN = 12;
/** The bottom band the idle dock and the call tile can sit in, kept clear when there is room. */
const DOCK_BAND = 84;
/** Bars that stay at the top while the page scrolls under them. */
const FIXED = [".site-header", ".ax-top"];

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const reduced = () => {
  try {
    return !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
};

/** The group a target belongs to: its closest `[data-stage-group]`, else itself. */
export function groupOf(el: Element): Element {
  return el.closest("[data-stage-group]") ?? el;
}

interface Rect {
  top: number;
  bottom: number;
  left: number;
  right: number;
  width: number;
  height: number;
}
const rectOf = (els: Element[]): Rect => {
  const rs = els.map((e) => e.getBoundingClientRect()).filter((r) => r.width || r.height);
  if (!rs.length) return { top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0 };
  const top = Math.min(...rs.map((r) => r.top));
  const bottom = Math.max(...rs.map((r) => r.bottom));
  const left = Math.min(...rs.map((r) => r.left));
  const right = Math.max(...rs.map((r) => r.right));
  return { top, bottom, left, right, width: right - left, height: bottom - top };
};

function scrollable(el: Element): { y: boolean; x: boolean } {
  const s = getComputedStyle(el);
  const can = (v: string) => v === "auto" || v === "scroll" || v === "overlay";
  return {
    y: can(s.overflowY) && el.scrollHeight > el.clientHeight + 1,
    x: can(s.overflowX) && el.scrollWidth > el.clientWidth + 1,
  };
}

/** How far to move one axis so `want` (or, if it cannot fit, its top with `min` still in) is inside [lo, hi]. */
function delta(want: [number, number], min: [number, number], lo: number, hi: number): number {
  if (want[1] - want[0] <= hi - lo) {
    if (want[0] < lo) return want[0] - lo;
    if (want[1] > hi) return want[1] - hi;
    return 0;
  }
  // Too big for the room: its start at `lo`, unless that pushes the target
  // itself out (a target too big itself, a wide table row, shows from its start).
  let d = want[0] - lo;
  if (min[1] - min[0] <= hi - lo && min[1] - d > hi) d = min[1] - hi;
  return d;
}

/** Inside a fixed box (the confirmation sheet, the phone's detail sheet, the menu drawer) or the sticky sidebar: the window's scroll does not move it. */
function pinned(el: Element): boolean {
  for (let n: Element | null = el; n && n !== document.body; n = n.parentElement) {
    const p = getComputedStyle(n).position;
    if (p === "fixed") return true;
    if (p === "sticky" && n.matches(".ax-side, .site-header, .ax-detail")) return true;
  }
  return false;
}

/**
 * The height the top bars take once the page has scrolled: a sticky header
 * below the utility strip is not stuck yet at the top of the page, but it will
 * be after the scroll this computes, so its own height counts either way.
 */
function headHeight(): number {
  let h = 0;
  for (const el of document.querySelectorAll<HTMLElement>(FIXED.join(","))) {
    if (el.closest("[data-voqalize]")) continue;
    const s = getComputedStyle(el);
    if (s.position !== "sticky" && s.position !== "fixed") continue;
    const r = el.getBoundingClientRect();
    if (r.height > 0 && r.height < 240) h = Math.max(h, (Number.parseFloat(s.top) || 0) + r.height);
  }
  return h;
}

/** What covers the bottom of the viewport: the phone tab bar, and the dock band above it. */
function bottomCover(): { hard: number; soft: number } {
  let hard = 0;
  for (const el of document.querySelectorAll<HTMLElement>(".ax-tabs")) {
    if (getComputedStyle(el).position !== "fixed") continue;
    const r = el.getBoundingClientRect();
    if (r.height > 0 && r.bottom >= window.innerHeight - 2) hard = Math.max(hard, window.innerHeight - r.top);
  }
  return { hard, soft: hard + DOCK_BAND };
}

async function settled(maxMs: number): Promise<void> {
  const end = Date.now() + maxMs;
  let last = -1;
  let still = 0;
  while (Date.now() < end) {
    await sleep(60);
    if (Math.abs(window.scrollY - last) < 1) {
      if (++still >= 2) return;
    } else still = 0;
    last = window.scrollY;
  }
}

/** Wait (up to ~700 ms) until `el` stops moving: a sheet sliding up, a panel opening. */
async function still(el: Element): Promise<void> {
  const end = Date.now() + 700;
  let last = "";
  let same = 0;
  while (Date.now() < end) {
    const r = el.getBoundingClientRect();
    const now = `${Math.round(r.top)},${Math.round(r.left)},${Math.round(r.height)}`;
    if (now === last) {
      if (++same >= 2) return;
    } else same = 0;
    last = now;
    await sleep(50);
  }
}

/**
 * Bring `target` (one element or several) and its whole group into view:
 * inner scroll areas first, innermost out, then the window, then the inner
 * areas once more (a sticky panel's place moves with the window).
 */
export async function showWhole(target: Element | Element[]): Promise<void> {
  const els = (Array.isArray(target) ? target : [target]).filter((e) => e?.isConnected);
  const first = els[0];
  if (!first) return;
  const groups = [...new Set(els.map(groupOf))];
  const group = () => rectOf(groups.concat(els));
  const own = () => rectOf(els);
  const smooth = !reduced();
  if (pinned(first)) await still(first);

  const inner = async (behavior: ScrollBehavior) => {
    let moved = false;
    for (let n = first.parentElement; n && n !== document.body && n !== document.documentElement; n = n.parentElement) {
      const can = scrollable(n);
      if (!can.x && !can.y) continue;
      const box = n.getBoundingClientRect();
      const top = box.top + n.clientTop;
      const left = box.left + n.clientLeft;
      // A group that is this scroll area or holds it says nothing about where to scroll inside it.
      const g = rectOf(groups.filter((gr) => !gr.contains(n)).concat(els));
      const o = own();
      const dy = can.y ? delta([g.top, g.bottom], [o.top, o.bottom], top + 6, top + n.clientHeight - 6) : 0;
      const dx = can.x ? delta([g.left, g.right], [o.left, o.right], left + 4, left + n.clientWidth - 4) : 0;
      if (Math.abs(dy) > 1 || Math.abs(dx) > 1) {
        n.scrollBy({ top: dy, left: dx, behavior });
        moved = true;
      }
    }
    if (moved && behavior === "smooth") await sleep(340);
  };

  await inner(smooth ? "smooth" : "auto");
  if (pinned(first)) return;

  const lo = headHeight() + MARGIN;
  const cover = bottomCover();
  const hi = window.innerHeight - Math.max(cover.hard, 0) - MARGIN;
  const hiClear = window.innerHeight - cover.soft;
  const g = group();
  const o = own();
  const fits = g.height <= hi - lo;
  const box = fits ? g : o;
  const bottom = box.height <= hiClear - lo ? hiClear : hi;
  // Already whole on screen (clear of the dock band when it can be): leave the page still.
  if (box.top >= lo - 1 && box.bottom <= bottom + 1) return;
  let d: number;
  if (fits) {
    // Centre the group in the clear room.
    d = g.top - (lo + (bottom - lo - g.height) / 2);
  } else {
    // The target itself clear of the dock band when it fits there.
    d = delta([g.top, g.bottom], [o.top, o.bottom], lo, o.height <= hiClear - lo ? hiClear : hi);
  }
  const max = document.documentElement.scrollHeight - window.innerHeight;
  const y = Math.min(Math.max(window.scrollY + d, 0), Math.max(max, 0));
  if (Math.abs(y - window.scrollY) < 2) return;
  window.scrollTo({ top: y, behavior: smooth ? "smooth" : "auto" });
  await settled(smooth ? 900 : 120);
  await inner("auto");
}

/**
 * True when `el`'s whole group shows in the window and in every scroll area
 * around it (or, for a group taller than the room, its start and `el` itself
 * do). For the X1 audit and `?debug=1`.
 */
export function groupInView(el: Element): boolean {
  const fixedBox = pinned(el);
  const lo = fixedBox ? 0 : headHeight();
  const floor = window.innerHeight - (fixedBox ? 0 : bottomCover().hard);
  const inside = (b: Rect, top: number, bottom: number, left: number, right: number, y: boolean, x: boolean) => {
    // A box bigger than the room it has must show from its start.
    if (y && (b.top < top - 1 || (b.height <= bottom - top ? b.bottom > bottom + 1 : b.top > bottom))) return false;
    if (x && (b.left < left - 1 || (b.width <= right - left ? b.right > right + 1 : b.left > right))) return false;
    return true;
  };
  let g = rectOf([groupOf(el), el]);
  if (g.height > floor - lo) g = rectOf([el]);
  if (!inside(g, lo, floor, 0, window.innerWidth, true, false)) return false;
  for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) {
    const can = scrollable(n);
    if (!can.x && !can.y) continue;
    const c = n.getBoundingClientRect();
    const grp = groupOf(el);
    let box = grp.contains(n) ? rectOf([el]) : g;
    if ((can.y && box.height > c.height) || (can.x && box.width > c.width)) box = rectOf([el]);
    if (!inside(box, c.top, c.bottom, c.left, c.right, can.y, can.x)) return false;
  }
  return true;
}

/** `?debug=1` only: every ring's target and whether its whole group was in view as it rang (X1 audit). */
type RingLog = { thing: string; inView: boolean }[];

/** The move's context with `scrollTo` showing the whole group, and `ring` doing that before it rings. */
export function withWhole(c: MoveContext): MoveContext {
  const ring = c.ring.bind(c);
  c.scrollTo = (el: Element) => showWhole(el);
  c.ring = async (el, opts) => {
    await showWhole(el);
    const log = (window as unknown as { __bankRings?: RingLog }).__bankRings;
    const first = Array.isArray(el) ? el[0] : el;
    if (log && first) log.push({ thing: first.getAttribute("data-stage-thing") ?? first.tagName, inView: groupInView(first) });
    await ring(el, opts);
  };
  return c;
}
