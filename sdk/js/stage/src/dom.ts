/**
 * What every site adapter needs of a page it did not write: finding one
 * element by what a person would call it, bringing it out of a closed tab,
 * accordion or carousel, scrolling it into view under the site's own fixed
 * bars, pressing and filling it the way the site's scripts notice, and
 * waiting for the page.
 */

export const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
export const clean = (s: string | null | undefined) => (s ?? "").replace(/\s+/g, " ").trim();

/** Laid out with a size: what a person could see if it were scrolled to. */
export function visible(el: Element | null | undefined): el is HTMLElement {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
}

// ─── Locate ───────────────────────────────────────────────────────────────

/** One way to find an element. */
export type Strategy =
  | { css: string }
  | { testId: string }
  | { ariaLabel: string }
  | { role: string; name?: string }
  | { text: string; within?: string }
  | { id: string };

/** Strategies tried in order: the first that finds exactly one element wins. */
export type Locator = Strategy | { any_of: Strategy[] };

const norm = (s: string | null | undefined) =>
  clean(s)
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[‘’]/g, "'");

const IMPLICIT_ROLES: Record<string, string> = {
  button: "button, input[type=button], input[type=submit], input[type=reset], summary",
  link: "a[href]",
  heading: "h1, h2, h3, h4, h5, h6",
  checkbox: "input[type=checkbox]",
  radio: "input[type=radio]",
  textbox: "input:not([type]), input[type=text], input[type=email], input[type=tel], input[type=search], textarea",
  combobox: "select",
  tab: "",
  img: "img[alt]",
  listitem: "li",
  navigation: "nav",
  dialog: "dialog",
  region: "section[aria-label], section[aria-labelledby]",
};

/** The accessible name, near enough: aria-label, aria-labelledby, a label,
 *  alt, then the text. */
export function accessibleName(el: Element): string {
  const label = el.getAttribute("aria-label");
  if (label) return clean(label);
  const by = el.getAttribute("aria-labelledby");
  if (by) {
    const text = by
      .split(/\s+/)
      .map((id) => el.ownerDocument.getElementById(id)?.textContent ?? "")
      .join(" ");
    if (clean(text)) return clean(text);
  }
  if (el.id) {
    const forLabel = el.ownerDocument.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (forLabel) return clean(forLabel.textContent);
  }
  const alt = el.getAttribute("alt") ?? el.getAttribute("title");
  if (alt) return clean(alt);
  return clean(el.textContent);
}

function byStrategy(s: Strategy, root: ParentNode): Element[] {
  if ("css" in s) return [...root.querySelectorAll(s.css)];
  if ("testId" in s) return [...root.querySelectorAll(`[data-testid="${CSS.escape(s.testId)}"]`)];
  if ("id" in s) return [...root.querySelectorAll(`[id="${CSS.escape(s.id)}"]`)];
  if ("ariaLabel" in s) {
    const want = norm(s.ariaLabel);
    return [...root.querySelectorAll("[aria-label]")].filter((el) => norm(el.getAttribute("aria-label")) === want);
  }
  if ("role" in s) {
    const implicit = IMPLICIT_ROLES[s.role];
    const sel = `[role="${CSS.escape(s.role)}"]${implicit ? `, ${implicit}` : ""}`;
    const all = [...root.querySelectorAll(sel)].filter((el) => {
      const explicit = el.getAttribute("role");
      return !explicit || explicit === s.role;
    });
    if (s.name === undefined) return all;
    const want = norm(s.name);
    return all.filter((el) => norm(accessibleName(el)) === want);
  }
  // Text: the innermost elements whose own text is exactly it.
  const want = norm(s.text);
  const scope = s.within ? [...root.querySelectorAll(s.within)] : [root];
  const hits: Element[] = [];
  for (const sc of scope) {
    const all = [...(sc as ParentNode).querySelectorAll("*")];
    if (sc instanceof Element) all.unshift(sc);
    for (const el of all) {
      if (el.closest("[data-voqalize]")) continue;
      if (norm(el.textContent) !== want) continue;
      if ([...el.children].some((c) => norm(c.textContent) === want)) continue;
      hits.push(el);
    }
  }
  return hits;
}

/** The one element a locator names, or `null` when none or several match.
 *  With `any_of`, the first strategy that finds exactly one wins. Elements
 *  the layout hides are ignored when a laid-out one of the same match exists. */
export function locate(spec: Locator, root: ParentNode = document): Element | null {
  const strategies = "any_of" in spec ? spec.any_of : [spec];
  for (const s of strategies) {
    let found: Element[];
    try {
      found = byStrategy(s, root).filter((el) => !el.closest("[data-voqalize]"));
    } catch {
      continue; // an invalid selector is a strategy that found nothing
    }
    if (found.length > 1) {
      const shown = found.filter((el) => !hiddenByLayout(el));
      if (shown.length === 1) return shown[0]!;
    }
    if (found.length === 1) return found[0]!;
  }
  return null;
}

/** Hidden by the layout itself (`display: none` up the tree outside a closed
 *  disclosure), as a responsive twin is: never brought out. */
function hiddenByLayout(el: Element): boolean {
  for (let n: Element | null = el; n; n = n.parentElement) {
    if (n instanceof HTMLDetailsElement && !n.open) return false;
    if (n.getAttribute("role") === "tabpanel" || n.hasAttribute("aria-hidden")) return false;
    const view = n.ownerDocument.defaultView;
    if (view && view.getComputedStyle(n).display === "none") return true;
  }
  return false;
}

// ─── Reveal ───────────────────────────────────────────────────────────────

/** Open whatever hides `el` the way a person would: a closed `<details>`, the
 *  tab whose panel holds it, the trigger whose `aria-controls` names its
 *  collapsed container, a carousel slide out of view (its own control: a dot
 *  or a slide button naming it). Outermost first. Never restyles anything. */
export async function reveal(el: Element): Promise<void> {
  const chain: Element[] = [];
  for (let n: Element | null = el; n; n = n.parentElement) chain.unshift(n);
  for (const n of chain) {
    if (n instanceof HTMLDetailsElement && !n.open && !(el === n)) {
      const summary = n.querySelector(":scope > summary");
      if (summary) press(summary);
      else n.open = true;
      await settle(n);
      continue;
    }
    const id = n.id;
    if (!id) continue;
    const doc = n.ownerDocument;
    const esc = CSS.escape(id);
    const shown = visible(n);
    // A tab panel: its tab (ARIA, or Bootstrap's `data-toggle="tab"`).
    if (!shown) {
      const tab =
        doc.querySelector(
          `[role="tab"][aria-controls="${esc}"], [data-toggle="tab"][href="#${esc}"], ` +
            `[data-bs-toggle="tab"][href="#${esc}"], [data-bs-toggle="tab"][data-bs-target="#${esc}"]`,
        ) ?? (n.getAttribute("role") === "tabpanel" ? doc.getElementById(n.getAttribute("aria-labelledby") ?? "") : null);
      if (tab && tab.getAttribute("aria-selected") !== "true") {
        press(tab);
        await settle(n);
        continue;
      }
    }
    // A collapsed container: its trigger.
    const trigger = doc.querySelector(
      `[aria-controls="${esc}"][aria-expanded="false"], [data-target="#${esc}"][aria-expanded="false"], ` +
        `[data-bs-target="#${esc}"][aria-expanded="false"], a[href="#${esc}"][aria-expanded="false"]`,
    );
    if (trigger && !shown) {
      press(trigger);
      await settle(n);
      continue;
    }
    // A carousel slide: a control that names it.
    if (!onScreenWithin(n)) {
      const control = doc.querySelector(
        `[aria-controls="${esc}"]:not([aria-expanded]), [data-slide-to][data-target="#${esc}"], button[aria-labelledby="${esc}"]`,
      );
      if (control) {
        press(control);
        await settle(n);
      }
    }
  }
}

/** Inside its clipping parent's box: a slide that is not slid out of view. */
function onScreenWithin(el: Element): boolean {
  const r = el.getBoundingClientRect();
  for (let p = el.parentElement; p; p = p.parentElement) {
    const view = p.ownerDocument.defaultView;
    const style = view?.getComputedStyle(p);
    if (!style || (style.overflowX !== "hidden" && style.overflow !== "hidden")) continue;
    const pr = p.getBoundingClientRect();
    return r.right > pr.left + 1 && r.left < pr.right - 1;
  }
  return true;
}

async function settle(el: Element): Promise<void> {
  await waitFor(() => visible(el), 1200);
  await sleep(150);
}

// ─── Scroll ───────────────────────────────────────────────────────────────

/** Selectors that are often pinned to the top of a page. */
export const FIXED_DEFAULT = ["header", ".site-header", ".sticky-top", ".fixed-top", ".sticky-header", "[data-sticky]"];

/** The height of whatever is pinned to the top of the viewport (fixed or
 *  sticky, starting where the bars above it end). */
export function pinnedHeight(selectors: readonly string[] = FIXED_DEFAULT): number {
  const bars: DOMRect[] = [];
  for (const sel of selectors) {
    let els: NodeListOf<HTMLElement>;
    try {
      els = document.querySelectorAll<HTMLElement>(sel);
    } catch {
      continue;
    }
    for (const el of els) {
      if (el.closest("[data-voqalize]")) continue;
      const pos = getComputedStyle(el).position;
      if (pos !== "fixed" && pos !== "sticky") continue;
      const r = el.getBoundingClientRect();
      if (r.height > 0 && r.height < 240 && r.top >= -2 && r.top <= 130) bars.push(r);
    }
  }
  bars.sort((a, b) => a.top - b.top);
  let h = 0;
  for (const r of bars) if (r.top <= h + 4) h = Math.max(h, r.bottom);
  return h;
}

/** The least of a scroll a ring waits for (`MoveContext.scrollTo`): a slow
 *  smooth scroll never holds the cues behind it longer than this. */
export const RING_SCROLL_MS = 800;

async function scrollEnded(until: number, signal?: AbortSignal): Promise<void> {
  let last = -1;
  let still = 0;
  while (Date.now() < until && !signal?.aborted) {
    await sleep(80);
    if (Math.abs(window.scrollY - last) < 1) {
      if (++still >= 3) return;
    } else {
      still = 0;
    }
    last = window.scrollY;
  }
}

export interface ScrollOptions {
  align?: "top" | "center";
  fixed?: readonly string[];
  /** Wait for the scroll no longer than this (it carries on by itself). */
  maxMs?: number;
  /** Stop waiting at once: the next move is due. */
  signal?: AbortSignal;
}

/** Scroll the window so `el` sits under the pinned bars (`top`) or in the
 *  middle of the room left (`center`, the default; a tall element goes to the
 *  top). Measured again after each pass: late images above it move it. With
 *  `maxMs` or `signal`, stops waiting when either says so, wherever the
 *  scroll has got to; the ring follows its target as it moves anyway. */
export async function scrollToEl(el: Element, opts: ScrollOptions = {}): Promise<void> {
  const until = Date.now() + (opts.maxMs ?? 7500);
  for (let pass = 0; pass < 3; pass++) {
    if (opts.signal?.aborted || Date.now() >= until) return;
    const r = el.getBoundingClientRect();
    const head = pinnedHeight(opts.fixed ?? FIXED_DEFAULT);
    const room = window.innerHeight - head;
    const want = opts.align === "top" || r.height > room * 0.8 ? head + 16 : head + (room - r.height) / 2;
    const delta = r.top - want;
    if (Math.abs(delta) < 8) return;
    const max = document.documentElement.scrollHeight - window.innerHeight;
    const y = Math.min(Math.max(window.scrollY + delta, 0), Math.max(max, 0));
    if (Math.abs(y - window.scrollY) < 4) return;
    const reduced = matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    window.scrollBy({ top: y - window.scrollY, behavior: pass === 0 && !reduced ? "smooth" : "auto" });
    await scrollEnded(Math.min(until, Date.now() + 2500), opts.signal);
  }
}

// ─── Press and fill ───────────────────────────────────────────────────────

/** Click it as a person would: the pointer and mouse events a site may listen
 *  for, then the click. */
export function press(el: Element): void {
  const opts = { bubbles: true, cancelable: true, composed: true };
  const view = el.ownerDocument.defaultView;
  if (view?.PointerEvent) el.dispatchEvent(new view.PointerEvent("pointerdown", opts));
  el.dispatchEvent(new MouseEvent("mousedown", opts));
  if (view?.PointerEvent) el.dispatchEvent(new view.PointerEvent("pointerup", opts));
  el.dispatchEvent(new MouseEvent("mouseup", opts));
  (el as HTMLElement).click();
}

type Field = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;

/** Set a field's value through the native setter (so a framework that wraps
 *  `value` sees it), then `input`, `change`, `keyup` and `blur`, as a finished
 *  edit does. Never a key that submits. */
export function setValue(el: Element, value: string): void {
  const f = el as Field;
  const proto =
    el instanceof HTMLSelectElement
      ? HTMLSelectElement.prototype
      : el instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  if (setter) setter.call(f, value);
  else f.value = value;
  for (const type of ["input", "change"]) el.dispatchEvent(new Event(type, { bubbles: true }));
  el.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true }));
  el.dispatchEvent(new Event("blur"));
  el.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
}

// ─── Waiting ──────────────────────────────────────────────────────────────

/** Poll `fn` every 100 ms until it returns something truthy, or `ms` pass. */
export async function waitFor<T>(fn: () => T | null | undefined | false, ms: number): Promise<T | null> {
  const until = Date.now() + ms;
  for (;;) {
    const v = fn();
    if (v) return v;
    if (Date.now() > until) return null;
    await sleep(100);
  }
}

/** `el` has not changed for `quietMs`, or `maxMs` has passed. */
export function quiet(el: Node, quietMs = 350, maxMs = 3000): Promise<void> {
  return new Promise<void>((resolve) => {
    let timer = setTimeout(done, quietMs);
    const obs = new MutationObserver(() => {
      clearTimeout(timer);
      timer = setTimeout(done, quietMs);
    });
    obs.observe(el, { childList: true, subtree: true, attributes: true, characterData: true });
    const stop = setTimeout(done, maxMs);
    function done() {
      obs.disconnect();
      clearTimeout(timer);
      clearTimeout(stop);
      resolve();
    }
  });
}

/** How long the DOM must be still for `domSettled`, and the most it waits. */
export const SETTLE_QUIET_MS = 300;
export const SETTLE_MAX_MS = 1500;

/**
 * The page is parsed and its DOM has been still for `quietMs` (or `maxMs`
 * has passed since it was parsed). What a new page waits for before its
 * first press when its site gives no `ready()`: never the document's `load`,
 * which a site's trackers can hold back for more than 15 s.
 */
export async function domSettled(quietMs = SETTLE_QUIET_MS, maxMs = SETTLE_MAX_MS, doc: Document = document): Promise<void> {
  if (doc.readyState === "loading") {
    await new Promise<void>((r) => doc.addEventListener("DOMContentLoaded", () => r(), { once: true }));
  }
  await quiet(doc.body ?? doc.documentElement, quietMs, maxMs);
}
