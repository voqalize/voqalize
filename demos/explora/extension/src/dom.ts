/**
 * What both site adapters share: the ring Javier draws around what he is
 * talking about, scrolling the window under Explora's fixed header, waiting
 * for the page, and setting a form field the way the site's own scripts
 * notice.
 *
 * Both hosts scroll the window itself (no smooth-scroll library), and both
 * reload the whole page on every move, so nothing here survives a page: each
 * load starts it afresh.
 */

/** What every adapter offers the call (`content.ts`). */
export interface Adapter {
  /** Perform one of the brain's page Actions. Never throws. */
  run(command: string, payload: unknown): Promise<{ ok: boolean; error?: string }>;
  /** What the visitor is looking at now, as a `page_changed` payload. */
  context(): PageContext;
  /** Report what the page shows and every booking step through `emit`, until
   *  the returned stop. The page as it stands is reported first. */
  start(emit: (event: string, payload: unknown) => void): () => void;
  /** The Actions `run` performs. */
  readonly commands: readonly string[];
}

export interface PageContext {
  site: "site" | "reservations";
  url: string;
  path: string;
  title: string;
  headings: string[];
  faqs: string[];
  tabs: string[];
  links: string[];
}

declare global {
  interface Window {
    /** The adapter for the host this page is on. */
    voqalizeExplora?: Adapter;
  }
}

/** A warm terracotta, which reads on Explora's black-and-sand pages, for the ring. */
export const RING = "#C2410C";
const RING_RGB = "194, 65, 12";
const RING_MS = 5500;
export const WAIT_MS = 8000;

export const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
export const clean = (s: string | null | undefined) => (s ?? "").replace(/\s+/g, " ").trim();
/** For matching what the brain said against what the page shows: case,
 *  accents, curly quotes, dashes and closing punctuation folded. */
export const norm = (s: string | null | undefined) =>
  clean(s)
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[‘’]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[‐-―]/g, "-")
    .replace(/\s*&\s*/g, " and ")
    .replace(/[.:?!\s]+$/, "")
    .trim();

export const visible = (el: Element | null | undefined): el is HTMLElement => {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};

export async function waitFor<T>(fn: () => T | null | undefined | false, ms = WAIT_MS): Promise<T | null> {
  const until = Date.now() + ms;
  for (;;) {
    const v = fn();
    if (v) return v;
    if (Date.now() > until) return null;
    await sleep(100);
  }
}

/** The best of `options` for `want`: exact, then prefix either way, then
 *  contains — as the brain matches it. */
export function pick<T>(want: string, options: T[], label: (o: T) => string): T | null {
  const w = norm(want);
  if (!w) return null;
  const labelled = options.map((o) => [norm(label(o)), o] as const);
  for (const test of [
    (o: string) => o === w,
    (o: string) => o.startsWith(w),
    (o: string) => w.startsWith(o) && o.length > w.length / 2,
    (o: string) => o.includes(w),
  ]) {
    const hit = labelled.find(([o]) => o && test(o));
    if (hit) return hit[1];
  }
  return null;
}

// ─── Scrolling ────────────────────────────────────────────────────────────

/** The height of whatever is pinned to the top of the viewport: Explora's
 *  fixed header, and a destination's or expedition's sticky sub-menu. */
export function headerHeight(): number {
  let h = 0;
  for (const el of document.querySelectorAll<HTMLElement>(
    "header#masthead, .site-header, .explora-submenu, .sticky-top, .fixed-top, header",
  )) {
    if (el.closest("[data-voqalize]") || el.matches("#sticky-booking, .fixed-bottom")) continue;
    const style = getComputedStyle(el);
    if (style.position !== "fixed" && style.position !== "sticky") continue;
    const r = el.getBoundingClientRect();
    if (r.height > 0 && r.height < 240 && r.top <= 130) h = Math.max(h, r.bottom);
  }
  return h;
}

/** Scroll the window so `el` sits under the header (`top`) or in the middle. */
export async function scrollTo(el: Element, where: "top" | "center" = "center"): Promise<void> {
  for (let pass = 0; pass < 3; pass++) {
    const r = el.getBoundingClientRect();
    const head = headerHeight();
    const room = window.innerHeight - head;
    const want = where === "top" || r.height > room * 0.8 ? head + 16 : head + (room - r.height) / 2;
    const delta = r.top - want;
    if (Math.abs(delta) < 4) return;
    window.scrollBy({ top: delta, behavior: pass === 0 ? "smooth" : "auto" });
    await waitFor(() => Math.abs(el.getBoundingClientRect().top - want) < 4, 1200);
    // Lazy images above it may have loaded and pushed it down: go again.
  }
}

// ─── The ring ─────────────────────────────────────────────────────────────
// Drawn over the page, never on Explora's own elements, and moved with its
// targets every frame: carousels slide and lazy images grow under it.

let rings: { el: HTMLElement; targets: Element[] }[] = [];
let ringFrame = 0;
let ringTimer: ReturnType<typeof setTimeout> | null = null;

/** `el`'s box in this window's viewport, also for an element inside a
 *  same-origin iframe (the booking site's room summary popup). */
function rectIn(el: Element): { left: number; top: number; right: number; bottom: number } {
  const r = el.getBoundingClientRect();
  let { left, top, right, bottom } = r;
  for (let win: Window | null = el.ownerDocument.defaultView; win && win !== window && win.frameElement; win = win.parent) {
    const frame = win.frameElement as HTMLElement;
    const f = frame.getBoundingClientRect();
    const dx = f.left + frame.clientLeft;
    const dy = f.top + frame.clientTop;
    left += dx;
    right += dx;
    top += dy;
    bottom += dy;
  }
  return { left, top, right, bottom };
}

function boxOf(targets: Element[]) {
  const rs = targets.filter(visible).map(rectIn);
  if (!rs.length) return null;
  return {
    left: Math.min(...rs.map((r) => r.left)),
    top: Math.min(...rs.map((r) => r.top)),
    right: Math.max(...rs.map((r) => r.right)),
    bottom: Math.max(...rs.map((r) => r.bottom)),
  };
}

function follow(): void {
  for (const ring of rings) {
    const b = boxOf(ring.targets);
    if (!b) {
      ring.el.style.opacity = "0";
      continue;
    }
    // A full-bleed block is ringed inside the screen's edges, where it shows.
    const left = Math.max(b.left - 6, 3);
    const right = Math.min(b.right + 6, document.documentElement.clientWidth - 3);
    Object.assign(ring.el.style, {
      transform: `translate(${left}px, ${b.top - 6}px)`,
      width: `${Math.max(right - left, 0)}px`,
      height: `${b.bottom - b.top + 12}px`,
    });
  }
  ringFrame = requestAnimationFrame(follow);
}

/** Ring each group: one element, or several ringed as one box. */
export function highlight(...groups: (Element | Element[])[]): void {
  clearHighlight();
  styleThePage();
  for (const group of groups) {
    const targets = Array.isArray(group) ? group : [group];
    if (!boxOf(targets)) continue;
    const el = document.createElement("div");
    el.setAttribute("data-voqalize", "highlight");
    Object.assign(el.style, {
      position: "fixed",
      left: "0",
      top: "0",
      border: `2px solid ${RING}`,
      borderRadius: "10px",
      pointerEvents: "none",
      zIndex: "2147483000",
      opacity: "0",
      transition: "opacity 300ms ease",
      animation: "voqalize-ring 1.4s ease-in-out 3",
    });
    document.body.appendChild(el);
    rings.push({ el, targets });
  }
  follow();
  requestAnimationFrame(() => rings.forEach((r) => (r.el.style.opacity = "1")));
  ringTimer = setTimeout(clearHighlight, RING_MS);
}

export function clearHighlight(): void {
  if (ringTimer) clearTimeout(ringTimer);
  cancelAnimationFrame(ringFrame);
  rings.forEach((r) => r.el.remove());
  rings = [];
}

/** The page's own corner widgets stand aside while the extension runs: the
 *  TalkCenter chat launcher sits exactly where Javier's widget does. */
export function styleThePage(): void {
  if (document.querySelector("style[data-voqalize=explora]")) return;
  const style = document.createElement("style");
  style.setAttribute("data-voqalize", "explora");
  style.textContent = `
    #tc-button-container, #tc-button-mask, #tc-window-container { display: none !important; }
    .grecaptcha-badge { visibility: hidden !important; }
    @keyframes voqalize-ring {
      0%, 100% { box-shadow: 0 0 0 0 rgba(${RING_RGB}, 0.45); }
      50% { box-shadow: 0 0 0 9px rgba(${RING_RGB}, 0); }
    }
  `;
  (document.head ?? document.documentElement).appendChild(style);
}

// ─── Forms ────────────────────────────────────────────────────────────────

/** Set a field's value through the native setter, and tell the page's own
 *  scripts (jQuery Validate, inline `onchange`) as a person's typing would. */
export function setField(el: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement, value: string): void {
  const proto =
    el instanceof HTMLSelectElement
      ? HTMLSelectElement.prototype
      : el instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(el, value);
  for (const type of ["input", "change", "keyup", "blur"]) el.dispatchEvent(new Event(type, { bubbles: true }));
}
