/**
 * What both site adapters share: scrolling the window under Explora's fixed
 * header, waiting for the page, matching what the brain named against what
 * the page shows, and setting a form field the way the site's own scripts
 * notice. The ring Javier draws around what he is talking about is Stage's
 * spotlight (`@voqalize/stage`), in Explora's terracotta (`site.ts`).
 *
 * Both hosts scroll the window itself (no smooth-scroll library), and both
 * reload the whole page on every move, so nothing here survives a page: each
 * load starts it afresh.
 */

/** What a page reports as `page_changed`. */
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

/** The page's own corner widgets stand aside while the extension runs: the
 *  TalkCenter chat launcher sits exactly where Javier's widget does. */
export function styleThePage(): void {
  if (document.querySelector("style[data-voqalize=explora]")) return;
  const style = document.createElement("style");
  style.setAttribute("data-voqalize", "explora");
  style.textContent = `
    #tc-button-container, #tc-button-mask, #tc-window-container { display: none !important; }
    .grecaptcha-badge { visibility: hidden !important; }
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
