/**
 * Bring what the agent is pointing at fully into view (owner, round 1, X1):
 * not just the one option, but the whole group it belongs to — the Colour
 * group of the filter rail, a step of the return form, the delivery days —
 * scrolled inside every scroll area that holds it (the sticky filter rail,
 * a drawer, a list) and then in the window, clear of the sticky header above
 * and the agent's dock below.
 *
 * The group is the nearest ancestor marked `data-reveal-group` (or the
 * element itself). A group taller than the room it has is aligned to its top,
 * as long as the element itself still shows; otherwise it moves as little as
 * it can. Every move the agent makes calls this before it rings, so a ring is
 * never half off screen.
 */

/** The band at the bottom of the viewport the dock may cover, in px. */
const DOCK_BAND = 96;
const GAP = 12;

const reduced = () => {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
};
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** The group to show whole for `el`. */
export function groupOf(el: Element): Element {
  return el.closest("[data-reveal-group]") ?? el;
}

function scrollers(el: Element): HTMLElement[] {
  const out: HTMLElement[] = [];
  for (let p = el.parentElement; p && p !== document.body && p !== document.documentElement; p = p.parentElement) {
    const s = getComputedStyle(p);
    if (/(auto|scroll|overlay)/.test(s.overflowY) && p.scrollHeight > p.clientHeight + 1) out.push(p);
  }
  return out;
}

/** How far to scroll a box of [top, bottom] so `want` (and at least `must`) shows inside [lo, hi]. */
function delta(want: DOMRect, must: DOMRect, lo: number, hi: number): number {
  const room = hi - lo;
  if (want.height > room) {
    // Too tall to show whole: its top under `lo`, unless that hides the element itself.
    let d = want.top - lo;
    if (must.bottom - d > hi) d = must.bottom - hi;
    return d;
  }
  if (want.top < lo) return want.top - lo;
  if (want.bottom > hi) return want.bottom - hi;
  return 0;
}

function headerBottom(): number {
  const bars = [...document.querySelectorAll<HTMLElement>(".site-header, [data-pinned]")];
  let h = 0;
  for (const b of bars) {
    const s = getComputedStyle(b);
    if (s.position !== "fixed" && s.position !== "sticky") continue;
    const r = b.getBoundingClientRect();
    if (r.height > 0 && r.top <= 4) h = Math.max(h, r.bottom);
  }
  return h;
}

function dockBand(): number {
  // The dock sits at the bottom unless a drawer moved it to a top corner.
  const dock = document.querySelector(".dock:not(.is-raised):not(.is-hidden)");
  return dock ? DOCK_BAND : GAP;
}

async function windowSettled(maxMs: number): Promise<void> {
  const end = Date.now() + maxMs;
  let last = -1;
  let still = 0;
  while (Date.now() < end) {
    await wait(60);
    if (Math.abs(window.scrollY - last) < 1) {
      if (++still >= 2) return;
    } else still = 0;
    last = window.scrollY;
  }
}

/**
 * Scroll `el`'s whole group into view: inner scroll areas first, then the
 * window, then the inner areas again (a sticky rail's place moves with the
 * window). Resolves once the scroll has settled, at most ~900 ms.
 */
export async function revealGroup(el: Element, group: Element = groupOf(el)): Promise<void> {
  if (!el.isConnected) return;
  const smooth = !reduced();
  for (let pass = 0; pass < 2; pass++) {
    for (const box of scrollers(group)) {
      const c = box.getBoundingClientRect();
      const d = delta(group.getBoundingClientRect(), el.getBoundingClientRect(), c.top + 6, c.bottom - 6);
      if (Math.abs(d) > 2) box.scrollTop += d;
    }
    const top = headerBottom() + GAP;
    const bottom = window.innerHeight - dockBand();
    // A sticky box (the filter rail) does not move with the window: only
    // what is outside such a box scrolls the window.
    const anchor = scrollers(group).find((b) => getComputedStyle(b).position === "sticky") ?? group;
    const d = delta(anchor.getBoundingClientRect(), el.getBoundingClientRect(), top, bottom);
    if (Math.abs(d) > 4) {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      const y = Math.min(Math.max(window.scrollY + d, 0), Math.max(max, 0));
      window.scrollTo({ top: y, behavior: smooth && pass === 0 ? "smooth" : "auto" });
      await windowSettled(smooth ? 800 : 120);
    } else if (pass === 0) {
      continue;
    } else {
      break;
    }
  }
}

/** True when all of `el`'s group shows (for tests and the debug console). */
export function groupInView(el: Element): boolean {
  const g = groupOf(el).getBoundingClientRect();
  if (g.top < headerBottom() - 1 || g.bottom > window.innerHeight + 1) return false;
  return scrollers(groupOf(el)).every((b) => {
    const c = b.getBoundingClientRect();
    return g.top >= c.top - 1 && g.bottom <= c.bottom + 1;
  });
}
