/**
 * X1: whenever the agent rings or acts on something, the WHOLE group it
 * belongs to is brought into view, not just the part it points at: every
 * add-on when one is toggled, both claim types, the documents still owed, a
 * policy section around the clause she marks. A group is the closest
 * `[data-stage-group]` around the target (or the target itself); a group
 * taller than the room falls back to the target.
 *
 * `showWhole` scrolls every inner scroll area on the way on both axes (the
 * quote tabs' row, the policy's contents rail), then the window, under the
 * sticky header and clear of the dock band when there is room. It is the
 * site's `MoveContext.scrollTo` (installed in `host.ts`), so every
 * `c.scrollTo` and Stage's own markup moves use it.
 *
 * Adapted from Paynora's `stage/view.ts` (demos/payroll_app), kept here so the
 * demo stays self-contained.
 */
import { pinnedHeight } from "@voqalize/stage";

const MARGIN = 12;
/** The bottom band the idle dock and the call tile can sit in, kept clear when there is room. */
const BOTTOM_BAND = 84;
const FIXED = [".site-header"];

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const reduced = () => !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

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

/** How far to move one axis so `want` (or, if it cannot fit, `min`) is inside [lo, hi]. */
function delta(want: [number, number], min: [number, number], lo: number, hi: number): number {
  const fits = want[1] - want[0] <= hi - lo;
  const [a, b] = fits ? want : min;
  if (a < lo) return a - lo;
  if (b > hi) return Math.min(b - hi, a - lo);
  return 0;
}

/** Inside a fixed box (the dock, the call tile) or the sticky header: the window's scroll does not move it. */
function pinned(el: Element): boolean {
  for (let n: Element | null = el; n && n !== document.body; n = n.parentElement) {
    const p = getComputedStyle(n).position;
    if (p === "fixed") return true;
    // The header never scrolls away; a sticky side panel (the breakdown, the claim's steps) still moves with the page.
    if (p === "sticky" && n.matches(".site-header")) return true;
  }
  return false;
}

/**
 * Bring `target` (one element or several) and its whole group into view:
 * inner scroll areas first, innermost out, then the window. When the group is
 * taller or wider than the room, the target itself is what must show.
 * `scrollWindow` is the window scroll to use (Stage's own, with its timing).
 */
export async function showWhole(target: Element | Element[], scrollWindow?: (el: Element) => Promise<void>): Promise<void> {
  const els = (Array.isArray(target) ? target : [target]).filter(Boolean);
  const first = els[0];
  if (!first) return;
  const groups = [...new Set(els.map(groupOf))];
  const group = () => rectOf(groups.concat(els));
  const own = () => rectOf(els);

  // Inner scroll areas, innermost first.
  let moved = false;
  for (let n = first.parentElement; n && n !== document.body && n !== document.documentElement; n = n.parentElement) {
    const can = scrollable(n);
    if (!can.x && !can.y) continue;
    const box = n.getBoundingClientRect();
    const top = box.top + n.clientTop;
    const left = box.left + n.clientLeft;
    const g = group();
    const o = own();
    const dy = can.y ? delta([g.top, g.bottom], [o.top, o.bottom], top + MARGIN, top + n.clientHeight - MARGIN) : 0;
    const dx = can.x ? delta([g.left, g.right], [o.left, o.right], left + 4, left + n.clientWidth - 4) : 0;
    if (Math.abs(dy) > 1 || Math.abs(dx) > 1) {
      n.scrollBy({ top: dy, left: dx, behavior: reduced() ? "auto" : "smooth" });
      moved = true;
    }
  }
  if (moved) await sleep(reduced() ? 0 : 320);

  // The window.
  if (pinned(first)) return;
  const head = pinnedHeight(FIXED);
  const lo = head + MARGIN;
  const hiClear = window.innerHeight - BOTTOM_BAND;
  const hi = window.innerHeight - MARGIN;
  const g = group();
  const o = own();
  const groupFits = g.height <= hi - lo;
  const box = groupFits ? g : o;
  // Already whole on screen (clear of the dock band when it can be): leave the page still.
  if (box.top >= lo - 1 && box.bottom <= (box.height <= hiClear - lo ? hiClear : hi) + 1) return;
  const pick = groupFits ? (groups.length === 1 && !els.includes(groups[0]!) ? groups[0]! : null) : null;
  const scrollEl = pick ?? (els.length === 1 ? first : null);
  if (scrollEl && scrollWindow) {
    await scrollWindow(scrollEl);
    return;
  }
  // Several targets with no one group element: centre their union.
  const room = window.innerHeight - head;
  const want = box.height > room * 0.8 ? head + 16 : head + (room - box.height) / 2;
  window.scrollBy({ top: box.top - want, behavior: reduced() ? "auto" : "smooth" });
  await sleep(reduced() ? 0 : 450);
}
