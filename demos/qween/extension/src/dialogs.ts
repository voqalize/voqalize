/**
 * What of Qween's own is open over the page, for the widget to keep clear of.
 * Qween's dialogs are all `role=dialog`, and on a desktop they are full-height
 * drawers that slide in from the right edge, where the widget sits.
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

/** Tells `onChange` what is open whenever that changes, whoever opened it. */
export function watchDialogs(onChange: (open: Rect[]) => void): void {
  let last = "";
  let frame = 0;
  let rest = 0;
  const look = () => {
    frame = 0;
    const open = openDialogs();
    const key = JSON.stringify(open.map((r) => [r.left, r.top, r.right, r.bottom].map(Math.round)));
    if (key === last) return;
    last = key;
    onChange(open);
  };
  const soon = () => {
    if (!frame) frame = requestAnimationFrame(look);
    clearTimeout(rest);
    rest = window.setTimeout(look, DRAWER_SETTLE_MS);
  };
  new MutationObserver(soon).observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["class", "style", "open", "aria-hidden", "data-state"],
  });
  window.addEventListener("resize", soon);
  look();
}
