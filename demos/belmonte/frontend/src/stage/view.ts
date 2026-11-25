/**
 * X1: whenever the concierge rings or acts on something, the WHOLE group it
 * belongs to is brought into view inside the phone, not just the part it
 * points at: an option's whole row of choices, a charge's day, a slot's grid.
 * A group is the closest `[data-stage-group]` around the target (or the target
 * itself).
 *
 * `showWhole` scrolls every scroll area on the way out from the target,
 * innermost first, on both axes: a chip row, a sheet's body, and the app's own
 * scroll area (`#app-scroll`), where it keeps the group clear of the sticky
 * page header above and of the concierge's widget below. The window
 * itself never scrolls (the app lives in the phone). Every performer reaches it
 * through `inView(c)` (performers.ts), so it is the move's `c.scrollTo`, and
 * Stage's own `showThing` uses it too.
 */
import type { MoveContext } from "@voqalize/stage";

const MARGIN = 12;

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

/** What covers the app's scroll area at the top (the sticky page header) and the bottom (the concierge's widget). */
function appInsets(area: Element): { top: number; bottom: number } {
  const box = area.getBoundingClientRect();
  const head = area.querySelector(".page-header")?.getBoundingClientRect();
  const top = head ? Math.max(0, head.bottom - box.top) : 0;
  let bottom = 0;
  for (const sel of [".bw:not(.is-raised)"]) {
    const r = document.querySelector(sel)?.getBoundingClientRect();
    if (r && r.height && !(r.top < box.top + box.height / 2)) bottom = Math.max(bottom, box.bottom - r.top);
  }
  return { top, bottom: Math.min(bottom, box.height / 3) };
}

/**
 * Bring `target` (one element or several) and its whole group into view:
 * scroll areas innermost first. When the group is taller or wider than the
 * room, the target itself is what must show.
 */
export async function showWhole(target: Element | Element[]): Promise<void> {
  const els = (Array.isArray(target) ? target : [target]).filter(Boolean);
  const first = els[0];
  if (!first) return;
  const groups = [...new Set(els.map(groupOf))];
  const group = () => rectOf(groups.concat(els));
  const own = () => rectOf(els);

  let moved = false;
  for (let n = first.parentElement; n && n !== document.body && n !== document.documentElement; n = n.parentElement) {
    const can = scrollable(n);
    if (!can.x && !can.y) continue;
    const box = n.getBoundingClientRect();
    const inset = n.id === "app-scroll" ? appInsets(n) : { top: 0, bottom: 0 };
    const top = box.top + n.clientTop + inset.top;
    const left = box.left + n.clientLeft;
    const g = group();
    const o = own();
    const dy = can.y ? delta([g.top, g.bottom], [o.top, o.bottom], top + MARGIN, box.top + n.clientTop + n.clientHeight - inset.bottom - MARGIN) : 0;
    const dx = can.x ? delta([g.left, g.right], [o.left, o.right], left + 4, left + n.clientWidth - 4) : 0;
    if (Math.abs(dy) > 1 || Math.abs(dx) > 1) {
      n.scrollBy({ top: dy, left: dx, behavior: reduced() ? "auto" : "smooth" });
      moved = true;
    }
  }
  if (moved) await sleep(reduced() ? 0 : 380);
}

/** Show the whole group, then ring the target. */
export async function ringWhole(c: MoveContext, el: Element | Element[], label?: Parameters<MoveContext["ring"]>[1]) {
  const first = Array.isArray(el) ? el[0] : el;
  if (!first) return;
  await c.scrollTo(first);
  await c.ring(el, label);
}
