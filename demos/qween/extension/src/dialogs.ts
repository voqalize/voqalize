/**
 * What of Qween's own is over the page, for the widget to keep clear of: the
 * dialogs that open over it, and the furniture fixed to the screen for good.
 * Qween's dialogs are all `role=dialog`, and on a desktop they are full-height
 * drawers that slide in from the right edge, where the widget sits. On a phone
 * the furniture is the purchase bar across the bottom of a product page and the
 * Concierge button that floats above it, both in the corner the widget takes.
 */

import type { Rect } from "./widget";

/** How long Qween's drawers take to slide, with some to spare: after a change
 *  on the page, it is looked at again once they have come to rest. */
const DRAWER_SETTLE_MS = 800;

/**
 * Qween's open dialogs, where each will come to rest. Every one of them is
 * `role=dialog`, and on a desktop they are full-height drawers sliding in from
 * the right edge. A drawer is measured without the transforms that slide it,
 * so the widget can start moving the moment one starts coming in.
 */
export function openDialogs(): Rect[] {
  const rects: Rect[] = [];
  for (const el of document.querySelectorAll<HTMLElement>("[role=dialog],[aria-modal=true]")) {
    if (el.closest("[data-voqalize]")) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1 || getComputedStyle(el).visibility === "hidden") continue;
    let dx = 0;
    let dy = 0;
    for (let n: Element | null = el; n && n !== document.body; n = n.parentElement) {
      const t = getComputedStyle(n).transform;
      if (!t || t === "none") continue;
      const m = new DOMMatrixReadOnly(t);
      dx += m.m41;
      dy += m.m42;
    }
    rects.push({ left: r.left - dx, top: r.top - dy, right: r.right - dx, bottom: r.bottom - dy });
  }
  return rects;
}

/** The page's fixed elements, found by a walk of the whole page. The walk is
 *  the expensive part, so it is cached and redone only once the page has
 *  changed, and not more often than this; the cached elements are measured
 *  afresh every time. */
const RESCAN_MS = 1000;
/** A fixed element covering more of the screen than this is a layer of the
 *  page, not furniture: Qween's product gallery is fixed and fills the screen
 *  behind the scrolling content on a phone, and takes the top two-thirds of it
 *  on a desktop. Their bars and buttons cover a sixth at most. */
const LAYER_SHARE = 1 / 3;
/** How often what was found is measured again, unprompted. */
const REMEASURE_MS = 1000;

let fixed: HTMLElement[] = [];
let scannedAt = -Infinity;
let stale = true;

function scanFixed(): void {
  fixed = [];
  for (const el of document.body.querySelectorAll<HTMLElement>("*")) {
    if (getComputedStyle(el).position === "fixed" && !el.closest("[data-voqalize]")) fixed.push(el);
  }
  scannedAt = performance.now();
  stale = false;
}

/**
 * What is fixed to the screen and stays: where each piece is now, on screen,
 * and not hidden. Dialogs are not counted here, and nor is a layer filling most
 * of the screen.
 */
export function furniture(): Rect[] {
  if (stale && performance.now() - scannedAt >= RESCAN_MS) scanFixed();
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const rects: Rect[] = [];
  for (const el of fixed) {
    if (!el.isConnected || el.closest("[role=dialog],[aria-modal=true]")) continue;
    const r = el.getBoundingClientRect();
    const w = Math.min(r.right, vw) - Math.max(r.left, 0);
    const h = Math.min(r.bottom, vh) - Math.max(r.top, 0);
    if (w < 1 || h < 1 || w * h > vw * vh * LAYER_SHARE) continue;
    const style = getComputedStyle(el);
    if (style.visibility === "hidden" || style.opacity === "0") continue;
    rects.push({ left: r.left, top: r.top, right: r.right, bottom: r.bottom });
  }
  return rects;
}

/** Tells `onChange` what is open and what is fixed whenever either changes,
 *  whoever changed it. */
export function watchDialogs(onChange: (open: Rect[], fixed: Rect[]) => void): void {
  let last = "";
  let frame = 0;
  let rest = 0;
  let rescan = 0;
  const key = (rects: Rect[]) => rects.map((r) => [r.left, r.top, r.right, r.bottom].map(Math.round));
  const look = () => {
    frame = 0;
    const open = openDialogs();
    const kept = furniture();
    // The page changed too soon after the last walk to walk it again: once
    // that is allowed, look again, or a bar that came would go unseen.
    clearTimeout(rescan);
    if (stale) rescan = window.setTimeout(look, RESCAN_MS);
    const now = JSON.stringify([key(open), key(kept)]);
    if (now === last) return;
    last = now;
    onChange(open, kept);
  };
  const soon = () => {
    if (!frame) frame = requestAnimationFrame(look);
    clearTimeout(rest);
    rest = window.setTimeout(look, DRAWER_SETTLE_MS);
  };
  new MutationObserver(() => {
    stale = true;
    soon();
  }).observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["class", "style", "open", "aria-hidden", "data-state"],
  });
  window.addEventListener("resize", soon);
  // A bar can come and go with the scroll, its classes unchanged, and Qween's
  // Concierge button fades in by a CSS animation, which no mutation reports:
  // what was found is measured again every so often too. Measuring is cheap;
  // only the walk that finds them is not, and this does not walk.
  window.addEventListener("scroll", soon, { passive: true });
  setInterval(look, REMEASURE_MS);
  scanFixed();
  look();
}
