/**
 * X1: whenever Meera rings or acts on something, the WHOLE group it belongs to
 * is brought into view, not just the part she points at: the sign-in panel
 * around a field, the booking summary around Confirm, an appointment card
 * around its change sheet, the calendar around a slot. A group is the closest
 * `[data-stage-group]` around the target (or the target itself). Paynora's
 * `view.ts`, adapted to the clinic's sticky header.
 *
 * `showWhole` scrolls every inner scroll area on the way (the calendar's
 * columns, a picker) on both axes, then the window, under the sticky header
 * and clear of the dock band when there is room. `wholeView` installs it as
 * every performer's `c.scrollTo` (the app's `useStage` takes no `extend`, so
 * the performers are wrapped instead), and `ringAll` shows several targets
 * together before ringing them.
 */
import type { MoveContext, Performers } from "@voqalize/stage";
import { pinnedHeight } from "@voqalize/stage";

const MARGIN = 12;
/** The bottom band the idle dock and the call tile can sit in, kept clear when there is room. */
const BOTTOM_BAND = 84;
const FIXED = [".site-header"];

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const reduced = () => {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
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

/** How far to move one axis so `want` (or, if it cannot fit, `min`) is inside [lo, hi]. */
function delta(want: [number, number], min: [number, number], lo: number, hi: number): number {
  const fits = want[1] - want[0] <= hi - lo;
  const [a, b] = fits ? want : min;
  if (a < lo) return a - lo;
  if (b > hi) return Math.min(b - hi, a - lo);
  return 0;
}

/** Inside a fixed box (the callback card, the call tile) or the header: the window's scroll does not move it. */
function pinned(el: Element): boolean {
  for (let n: Element | null = el; n && n !== document.body; n = n.parentElement) {
    const p = getComputedStyle(n).position;
    if (p === "fixed") return true;
    if (p === "sticky" && n.matches(".site-header")) return true;
  }
  return false;
}

/**
 * Bring `target` (one element or several) and its whole group into view:
 * inner scroll areas first, innermost out, then the window. When the group is
 * taller or wider than the room, the target itself is what must show.
 */
export async function showWhole(target: Element | Element[]): Promise<void> {
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
  const box = g.height <= hi - lo ? g : own();
  const bottom = box.height <= hiClear - lo ? hiClear : hi;
  // Already whole on screen (clear of the dock band when it can be): leave the page still.
  if (box.top >= lo - 1 && box.bottom <= bottom + 1) return;
  // Taller than the room: its top under the header. Otherwise move as little as it takes.
  const dy = box.height > bottom - lo ? box.top - lo : box.top < lo ? box.top - lo : box.bottom - bottom;
  window.scrollBy({ top: dy, behavior: reduced() ? "auto" : "smooth" });
  await sleep(reduced() ? 0 : 450);
}

/** Show several targets together (and their groups), then ring them all. */
export async function ringAll(c: MoveContext, els: Element[], label?: string) {
  if (!els.length) return;
  await showWhole(els);
  await c.ring(els, label);
}

/** Every performer, with `c.scrollTo` showing the target's whole group (X1). */
export function wholeView<P extends Performers<never>>(performers: P): P {
  const out: Record<string, unknown> = {};
  for (const [id, perform] of Object.entries(performers as Record<string, (args: unknown, c: MoveContext) => unknown>)) {
    out[id] = (args: unknown, c: MoveContext) => {
      Object.assign(c, { scrollTo: (el: Element) => showWhole(el) });
      return perform(args, c);
    };
  }
  return out as P;
}
