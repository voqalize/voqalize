/**
 * Where the concierge's widget sits, read from the app itself
 * so every sheet counts, whoever opened it (a tap, or one of her moves).
 * Paynora's widget, adapted to a phone: everything is measured inside the
 * app's screen (`#screen`, the device frame's display on a desktop, the whole
 * window on a real phone), which is the containing block of the
 * widget, so `left`/`top` are relative to it.
 */
export interface ScreenBox {
  left: number;
  top: number;
  width: number;
  height: number;
}
/** The app's screen in the window's coordinates. */
export function screenBox(): ScreenBox {
  const r = document.getElementById("screen")?.getBoundingClientRect();
  return r ? { left: r.left, top: r.top, width: r.width, height: r.height } : { left: 0, top: 0, width: window.innerWidth, height: window.innerHeight };
}

const visible = (el: Element) => {
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};

/** Which overlay is open over the app, if any (sheets mark themselves `data-overlay="bottom"`). */
export function openOverlay(): "right" | "left" | "center" | "bottom" | null {
  const marks = [...document.querySelectorAll<HTMLElement>("#screen [data-overlay]")].filter(visible).map((el) => el.dataset.overlay);
  if (marks.includes("right")) return "right";
  if (marks.includes("left")) return "left";
  if (marks.includes("center")) return "center";
  if (marks.includes("bottom")) return "bottom";
  return null;
}

/** The top corner the concierge moves to while a sheet is open; `null` with nothing open. */
export function raisedCorner(): "tl" | "tr" | null {
  const o = openOverlay();
  if (o === null) return null;
  return o === "right" ? "tl" : "tr";
}

/** The visible boxes of the guest-only buttons and primary actions (`data-dock-avoid`), relative to the screen. */
export function avoidRects(): DOMRect[] {
  const s = screenBox();
  // What the app's scroll area clips (under the tab bar, above the header) is not on screen.
  const area = document.getElementById("app-scroll")?.getBoundingClientRect();
  const shown = (el: HTMLElement, r: DOMRect) => (el.closest("#app-scroll") && area ? r.bottom > area.top && r.top < area.bottom : r.bottom > s.top && r.top < s.top + s.height);
  return [...document.querySelectorAll<HTMLElement>("#screen [data-dock-avoid]")]
    .map((el) => [el, el.getBoundingClientRect()] as const)
    .filter(([el, r]) => r.width > 0 && shown(el, r))
    .map(([, r]) => r)
    .map((r) => new DOMRect(r.left - s.left, r.top - s.top, r.width, r.height));
}

/** Height of the bottom chrome (the tab bar) the widget keeps above. */
export function bottomBar(): number {
  const r = document.querySelector("#screen .tab-bar")?.getBoundingClientRect();
  return r && r.height ? r.height : 0;
}

/** Height of the top chrome (status bar and the page's sticky header). */
export function topBar(): number {
  const s = screenBox();
  const h = document.querySelector("#screen .page-header")?.getBoundingClientRect();
  const st = document.querySelector("#screen .status-bar")?.getBoundingClientRect();
  return Math.max(0, h ? h.bottom - s.top : 0, st ? st.bottom - s.top : 0);
}
