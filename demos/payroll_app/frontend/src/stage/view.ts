/**
 * X1: whenever the agent rings or acts on something, the WHOLE group it
 * belongs to is brought into view first, not just the part it points at: a
 * claim's row, both regime cards, a leave request card, a drawer's amounts,
 * the employee form's field. A group is the closest `[data-stage-group]`
 * around the target (or the target itself).
 *
 * `showWhole` scrolls every inner scroll area on the way (a table's frame
 * under its sticky header row, the sidebar, a drawer's body) on both axes,
 * innermost first, then the window: under the sticky top bar and the "viewing
 * as" banner, and clear of the idle dock and the call tile (wherever it was
 * dragged) when there is room. It scrolls again when the first scroll landed
 * short (a sticky panel moves with the page).
 *
 * `wholeMoves` (installed as `Moves`' `extend` in `runtime.ts`) makes every
 * move's `c.scrollTo` this, and makes `c.ring` show the whole group before it
 * rings, so no performer can ring something half off screen. The `?debug=1`
 * audit (`audit.ts`) checks every ring as it happens. The site
 * (`demos/payroll_site`) carries the same core.
 */
import type { MoveContext } from "@voqalize/stage";

/** Bars that stay at the top while the page scrolls under them. */
const TOP_BARS = [".topbar", ".viewas-banner"];
/** Sticky boxes that never scroll away with the page. */
const PINNED_STICKY = ".sidebar, .topbar, .viewas-banner";
/** Fixed boxes over the page a target should clear: the idle dock pill and the call tile. */
const OVERLAYS = [".dock:not(.is-hidden):not(.is-calling)", ".call-tile.is-tile", ".call-tile.is-mini"];

// ─── shared core: identical in payroll_site and payroll_app below this line ───

const MARGIN = 12;

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const reduced = () => {
  try {
    return !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
};

const shown = new Set<Element>();
/** What the agent is showing or ringing right now: the call tile (and the app's idle dock) keep off it. */
export function shownNow(): DOMRect[] {
  return [...shown].filter((e) => e.isConnected).map((e) => e.getBoundingClientRect());
}

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

/** How far to move one axis so `want` (or, if it cannot fit, its start with `min` still in) is inside [lo, hi]. */
function delta(want: [number, number], min: [number, number], lo: number, hi: number): number {
  if (want[1] - want[0] <= hi - lo) {
    if (want[0] < lo) return want[0] - lo;
    if (want[1] > hi) return want[1] - hi;
    return 0;
  }
  let d = want[0] - lo;
  if (min[1] - min[0] <= hi - lo && min[1] - d > hi) d = min[1] - hi;
  return d;
}

/** Inside a fixed box (a drawer, the lead card, the call tile) or a bar that never scrolls away: the window's scroll does not move it. */
function pinned(el: Element): boolean {
  for (let n: Element | null = el; n && n !== document.body; n = n.parentElement) {
    const p = getComputedStyle(n).position;
    if (p === "fixed") return true;
    if (p === "sticky" && n.matches(PINNED_STICKY)) return true;
  }
  return false;
}

/** The height the top bars take once the page has scrolled under them. */
function headHeight(): number {
  let h = 0;
  for (const el of document.querySelectorAll<HTMLElement>(TOP_BARS.join(","))) {
    const s = getComputedStyle(el);
    if (s.position !== "sticky" && s.position !== "fixed") continue;
    const r = el.getBoundingClientRect();
    if (r.height > 0 && r.height < 240) h = Math.max(h, (Number.parseFloat(s.top) || 0) + r.height);
  }
  return h;
}

/**
 * What sits over the page and should not hide a target: the idle dock pill and
 * the call tile (wherever it was dragged), and any fixed card the demo names.
 * Each is a box the target should clear, when there is room for it.
 */
function overlays(target: Element[]): DOMRect[] {
  const out: DOMRect[] = [];
  for (const el of document.querySelectorAll<HTMLElement>(OVERLAYS.join(","))) {
    if (target.some((t) => el.contains(t) || t.contains(el))) continue;
    const s = getComputedStyle(el);
    if (s.display === "none" || s.visibility === "hidden" || Number(s.opacity) === 0) continue;
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight) out.push(r);
  }
  return out;
}

/**
 * The clear band [lo, hi] of the window for a box spanning `left..right`:
 * under the top bars and clear of any overlay in its columns: one at the foot
 * (the dock, a parked tile) lowers `hi`, one at the top (a raised tile) raises
 * `lo`. `hard` is the band with the top bars only.
 */
function band(left: number, right: number, target: Element[]): { lo: number; hi: number; hardLo: number; hardHi: number } {
  const hardLo = headHeight() + MARGIN;
  const hardHi = window.innerHeight - MARGIN;
  let lo = hardLo;
  let hi = hardHi;
  const own = rectOf(target);
  const mid = (own.top + own.bottom) / 2;
  for (const r of overlays(target)) {
    if (r.right <= left || r.left >= right) continue;
    // An overlay at the foot, or below the target's middle, ends the band; one above it starts it.
    const below = r.top > window.innerHeight * 0.6 || (r.bottom > window.innerHeight * 0.4 && (r.top + r.bottom) / 2 >= mid);
    if (below) hi = Math.min(hi, r.top - 8);
    else lo = Math.max(lo, r.bottom + 8);
  }
  if (hi - lo < 120) return { lo: hardLo, hi: hardHi, hardLo, hardHi };
  return { lo, hi, hardLo, hardHi };
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

/** Wait (up to ~700 ms) until `el` stops moving: a drawer sliding in, a card opening. */
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
 * inner scroll areas first, innermost out, then the window, then once more
 * (a sticky panel's place moves with the window, so the first scroll can land
 * short), then the inner areas again.
 */
export async function showWhole(target: Element | Element[]): Promise<void> {
  const els = (Array.isArray(target) ? target : [target]).filter((e) => e?.isConnected);
  const first = els[0];
  if (!first) return;
  const groups = [...new Set(els.map(groupOf))];
  const smooth = !reduced();
  // What a move shows is a place the call tile keeps off (`shownNow`, read by
  // the tile's blockers) while it is rung; a scroll event makes the tile look
  // again. Not a DOM mark: the page must not change before the ring.
  shown.clear();
  for (const e of els) shown.add(e);
  window.dispatchEvent(new Event("scroll"));
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
      const o = rectOf(els);
      // A sticky header row inside this area (a table's head) covers its top.
      const th = n.querySelector("thead");
      const headIn = th && !els.some((e) => th.contains(e)) && getComputedStyle(th.querySelector("th") ?? th).position === "sticky" ? th.getBoundingClientRect().height : 0;
      const dy = can.y ? delta([g.top, g.bottom], [o.top, o.bottom], top + 6 + headIn, top + n.clientHeight - 6) : 0;
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

  // How far the window must move, or 0 when the group already shows (clear of overlays when it can be).
  const need = (): number => {
    const g = rectOf(groups.concat(els));
    const o = rectOf(els);
    const b = band(g.left, g.right, els);
    // The group when it fits under the top bars, else the target itself.
    const box = g.height <= b.hardHi - b.hardLo ? g : o;
    if (box.height <= b.hi - b.lo) {
      // It fits clear of the overlays too: whole, centred in the clear band.
      if (box.top >= b.lo - 1 && box.bottom <= b.hi + 1) return 0;
      return box.top - (b.lo + (b.hi - b.lo - box.height) / 2);
    }
    // Too tall to clear the overlays: as much of it as fits from its start,
    // with the target itself clear of them (the dock, the call tile).
    const ownClear = o.height <= b.hi - b.lo;
    const lo = ownClear ? b.lo : b.hardLo;
    const hi = ownClear ? b.hi : b.hardHi;
    if (box.top >= b.hardLo - 1 && box.top <= lo + 1 && o.top >= lo - 1 && o.bottom <= hi + 1) return 0;
    return delta([box.top, box.bottom], [o.top, o.bottom], lo, hi);
  };
  // After the first scroll, move again only for the target itself: the call
  // tile moves with the page (it keeps off the page's buttons and off the
  // target), and chasing it would push the target back under it.
  const ownCovered = (): boolean => {
    const o = rectOf(els);
    const b = band(o.left, o.right, els);
    if (o.top < b.hardLo - 1 || o.bottom > b.hardHi + 1) return o.height <= b.hardHi - b.hardLo || o.top < b.hardLo - 1;
    return overlays(els).some((r) => r.left < o.right && r.right > o.left && r.top < o.bottom && r.bottom > o.top);
  };
  for (let pass = 0; pass < 3; pass++) {
    if (pass > 0 && !ownCovered()) break;
    const d = need();
    const max = document.documentElement.scrollHeight - window.innerHeight;
    const y = Math.min(Math.max(window.scrollY + d, 0), Math.max(max, 0));
    if (Math.abs(y - window.scrollY) < 2) break;
    window.scrollTo({ top: y, behavior: smooth && pass === 0 ? "smooth" : "auto" });
    await settled(smooth && pass === 0 ? 900 : 120);
    // The call tile can move when the page does (it keeps off the page's
    // buttons): let it land before measuring again.
    const tile = document.querySelector(".call-tile.is-tile, .call-tile.is-mini");
    if (tile) await still(tile);
  }
  await inner("auto");
}

/**
 * True when `el`'s whole group shows in the window under the top bars and in
 * every scroll area around it (for a group taller than the room, `el`
 * itself; for `el` taller still, its start). For `?debug=1` and tests.
 */
export function groupInView(el: Element): boolean {
  const fixedBox = pinned(el);
  const lo = fixedBox ? 0 : headHeight();
  const floor = window.innerHeight;
  let g = rectOf([groupOf(el), el]);
  if (g.height > floor - lo) g = rectOf([el]);
  const tall = g.height > floor - lo;
  if (g.top < lo - 1 || (tall ? g.top > floor : g.bottom > floor + 1)) return false;
  for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) {
    const can = scrollable(n);
    if (!can.x && !can.y) continue;
    const c = n.getBoundingClientRect();
    const box = groupOf(el).contains(n) ? rectOf([el]) : g;
    if (can.y && (box.top < c.top - 1 || (box.height <= c.height && box.bottom > c.bottom + 1))) return false;
    if (can.x && (box.left < c.left - 1 || (box.width <= c.width && box.right > c.right + 1))) return false;
  }
  return true;
}

/** Every ring shows its target's whole group first (X1): the move context's `scrollTo` and `ring`, wrapped. */
export function wholeMoves(c: MoveContext, audit?: (ring: MoveContext["ring"]) => MoveContext["ring"]): Partial<MoveContext> {
  // The audit (debug only) checks each target after the scroll, as it rings.
  const raw = audit ? audit(c.ring.bind(c)) : c.ring.bind(c);
  return {
    scrollTo: (el: Element) => showWhole(el),
    ring: async (el, opts) => {
      // `showWhole` puts the target in `shownNow` for the tile; it stays there
      // while the ring lingers on screen, until the next move shows something.
      try {
        await showWhole(el);
        await raw(el, opts);
      } finally {
        const mine = new Set(shown);
        setTimeout(() => {
          if ([...mine].every((e) => shown.has(e)) && mine.size === shown.size) shown.clear();
        }, 4000);
      }
    },
  };
}

/** Show the whole group, then ring the target (`c.ring` does both in this app; kept for the performers). */
export async function ringWhole(c: MoveContext, el: Element | Element[], label?: string) {
  await c.ring(el, label);
}
