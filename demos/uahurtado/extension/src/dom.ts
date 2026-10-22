/**
 * What the site adapter leans on: matching what the brain said against what
 * the page shows, telling what is laid out at this width from a mobile copy
 * the layout hides, scrolling under the university's sticky header, the ring
 * Javier draws around what he is talking about, reading an element's text as
 * the page shows it, and setting a form field the way the site's own scripts
 * notice.
 *
 * The three hosts are WordPress themes on Bootstrap 5 with the window as the
 * scroller; every move between pages reloads the whole page, so nothing here
 * outlives one.
 */

export const RING_FALLBACK = "#F26522";
const RING_MS = 5500;
export const WAIT_MS = 8000;

export const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
export const clean = (s: string | null | undefined) => (s ?? "").replace(/\s+/g, " ").trim();

/**
 * For matching what the brain said against what the page shows: lower case,
 * without accents (á → a, ñ → n), with straight quotes and dashes, and without
 * the opening "¿"/"¡" and closing punctuation either side may or may not have.
 */
export const norm = (s: string | null | undefined) =>
  clean(s)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[‘’´`]/g, "'")
    .replace(/[“”«»]/g, '"')
    .replace(/[‐-―]/g, "-")
    .replace(/\s*&\s*/g, " y ")
    .replace(/[¿¡]/g, "")
    .replace(/…/g, "")
    .replace(/^[\s"']+|[\s"'.:;,?!]+$/g, "")
    .trim();

/** Has a box on screen now (not zero-sized, not in a `display: none`). */
export const visible = (el: Element | null | undefined): el is HTMLElement => {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};

/** Laid out: in the render tree at all, whatever its size. */
export const laidOut = (el: Element) =>
  !!((el as HTMLElement).offsetWidth || (el as HTMLElement).offsetHeight || el.getClientRects().length);

/** A pane the adapter can open: a closed Bootstrap tab pane or collapse. */
const CLOSED = ".tab-pane:not(.active), .collapse:not(.show)";

/** Hidden by the layout itself, not by a pane the adapter can open: inside a
 *  responsive copy that is `display: none` at this width (`d-none`,
 *  `d-md-none`, `d-lg-none`…), the mobile twin of a desktop block. Explora
 *  learned this on dev call 0a304d89: every cue on a hidden twin failed. */
export function layoutHidden(el: Element): boolean {
  for (let p: Element | null = el; p && p !== document.body; p = p.parentElement) {
    if (laidOut(p)) return false;
    if (!p.matches(CLOSED) && getComputedStyle(p).display === "none") return true;
  }
  return false;
}

/** What may be reported and used at this width: on screen with a size, or
 *  hidden only by a closed pane the adapter can open. A zero-size copy and a
 *  copy the layout hides are not. */
export const usable = (el: Element) => visible(el) || (!laidOut(el) && !layoutHidden(el));

export async function waitFor<T>(fn: () => T | null | undefined | false, ms = WAIT_MS): Promise<T | null> {
  const until = Date.now() + ms;
  for (;;) {
    const v = fn();
    if (v) return v;
    if (Date.now() > until) return null;
    await sleep(80);
  }
}

/** Page order, for lists gathered from several selectors. */
export const inOrder = (a: Node, b: Node) =>
  a === b ? 0 : a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;

/**
 * The best match for what the brain said among `items`: the same words, then
 * one that starts with them, then one they start with, then one that holds
 * them. Among equals, the copy laid out at this width wins over a hidden twin.
 */
export function best<T>(items: T[], text: (t: T) => string, said: string, el?: (t: T) => Element): T | null {
  const want = norm(said);
  if (!want) return null;
  const t = (i: T) => norm(text(i));
  const tests = [
    (i: T) => t(i) === want,
    (i: T) => t(i).startsWith(want),
    (i: T) => want.startsWith(t(i)) && t(i).length > 3,
    (i: T) => t(i).includes(want),
  ];
  for (const test of tests) {
    const hits = items.filter(test);
    if (!hits.length) continue;
    return (el && hits.find((h) => visible(el(h)))) || hits[0];
  }
  return null;
}

/**
 * Looser still, for a form's options: Spanish's paired endings ("destacadas/os",
 * "Licenciado (a)") and a word's gender and number set aside, so "deportistas
 * destacados" finds "Deportistas destacadas/os".
 */
export const loose = (s: string | null | undefined) =>
  norm(s)
    .replace(/\s*\/\s*(as|os|a|o)\b/g, "")
    .replace(/\s*\((as|os|a|o)\)/g, "")
    .split(/\s+/)
    .map((w) => (w.length > 3 ? w.replace(/(as|os|es|a|o|e|s)$/, "") : w))
    .join(" ");

// ─── Scrolling ────────────────────────────────────────────────────────────

/** The height of whatever is pinned to the top of the viewport: the sticky
 *  black header (`header.header.sticky-top`) on every host. */
export function headerHeight(): number {
  let h = 0;
  for (const el of document.querySelectorAll<HTMLElement>("header, .sticky-top, .fixed-top")) {
    if (el.closest("[data-voqalize]")) continue;
    const pos = getComputedStyle(el).position;
    if (pos !== "fixed" && pos !== "sticky") continue;
    const r = el.getBoundingClientRect();
    if (r.height > 0 && r.height < 240 && r.top <= 130) h = Math.max(h, pos === "sticky" ? r.height : r.bottom);
  }
  return h;
}

/** Scroll the window so `el` sits under the header (`top`) or in the middle;
 *  measured again and corrected, since lazy images above it move the page. */
export async function scrollTo(el: Element, where: "top" | "center" = "center"): Promise<void> {
  for (let pass = 0; pass < 3; pass++) {
    const r = el.getBoundingClientRect();
    const head = headerHeight();
    const room = window.innerHeight - head;
    const want = where === "top" || r.height > room * 0.8 ? head + 16 : head + (room - r.height) / 2;
    const delta = r.top - want;
    if (Math.abs(delta) < 4) return;
    const max = document.documentElement.scrollHeight - window.innerHeight;
    const y = Math.min(Math.max(window.scrollY + delta, 0), max);
    if (Math.abs(y - window.scrollY) < 4) return;
    window.scrollTo({ top: y, behavior: pass === 0 ? "smooth" : "auto" });
    // Done when the window is where it was sent, which may be short of `want`
    // at the foot of the page.
    await waitFor(() => Math.abs(window.scrollY - y) < 2, 1200);
  }
}

// ─── The ring ─────────────────────────────────────────────────────────────
// Drawn over the page, never on the university's own elements, and moved with
// its targets every frame: a pane that fades in, a menu that slides open.

let rings: { el: HTMLElement; targets: Element[] }[] = [];
let ringFrame = 0;
let ringTimer: ReturnType<typeof setTimeout> | null = null;

export function boxOf(targets: Element[]) {
  const rs = targets.filter(visible).map((el) => el.getBoundingClientRect());
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
      border: "2px solid var(--voqalize-ring)",
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

/** The site's accent: the fill of its primary buttons ("Enviar"). */
function accent(): string {
  const btn = document.querySelector(".btn-primary");
  const bg = btn ? getComputedStyle(btn).backgroundColor : "";
  return /^rgba?\(/.test(bg) && !/,\s*0\)$/.test(bg) ? bg : RING_FALLBACK;
}

export function styleThePage(): void {
  if (document.querySelector("style[data-voqalize=uahurtado]")) return;
  const style = document.createElement("style");
  style.setAttribute("data-voqalize", "uahurtado");
  style.textContent = `
    :root { --voqalize-ring: ${RING_FALLBACK}; }
    @keyframes voqalize-ring {
      0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--voqalize-ring) 55%, transparent); }
      50% { box-shadow: 0 0 0 10px color-mix(in srgb, var(--voqalize-ring) 0%, transparent); }
    }
  `;
  (document.head ?? document.documentElement).appendChild(style);
  const paint = () => document.documentElement.style.setProperty("--voqalize-ring", accent());
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", paint, { once: true });
  else paint();
}

// ─── Text ─────────────────────────────────────────────────────────────────

const BLOCK = /^(P|DIV|LI|UL|OL|H[1-6]|TR|TABLE|TBODY|THEAD|SECTION|ARTICLE|BLOCKQUOTE|FIGURE|DL|DT|DD)$/;

/**
 * An element's text as the page writes it on screen, one line per paragraph,
 * list item, table row or `<br>`: the rendered nodes' text, never an
 * attribute (the fee cells' `data-sheets-value` hold last year's figures).
 * It reads a pane the same whether the pane is open or not.
 */
export function textOf(root: Element | null | undefined): string {
  if (!root) return "";
  const parts: string[] = [];
  const walk = (n: Node) => {
    if (n.nodeType === Node.TEXT_NODE) {
      parts.push(n.nodeValue ?? "");
      return;
    }
    if (!(n instanceof Element)) return;
    if (/^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE|svg|BUTTON|SELECT|IFRAME)$/i.test(n.tagName)) return;
    if (n.matches("[data-voqalize]")) return;
    if (n.tagName === "BR") return void parts.push("\n");
    const block = BLOCK.test(n.tagName);
    if (block) parts.push("\n");
    for (const c of n.childNodes) walk(c);
    if (n.tagName === "TD" || n.tagName === "TH") parts.push(" | ");
    if (block) parts.push("\n");
  };
  walk(root);
  return parts
    .join("")
    .split("\n")
    .map((line) => line.replace(/[ \t\u00a0]+/g, " ").replace(/\s*\|\s*$/, "").trim())
    .filter(Boolean)
    .join("\n");
}

// ─── Forms ────────────────────────────────────────────────────────────────

/** Set a field's value through the native setter, and tell the page's own
 *  scripts as a person's typing would: the form's inline `onchange` composes
 *  nombre_y_apellido, the theme's validation listens for `blur`. */
export function setField(el: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement, value: string): void {
  const proto =
    el instanceof HTMLSelectElement
      ? HTMLSelectElement.prototype
      : el instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(el, value);
  for (const type of ["input", "change", "blur", "focusout"]) el.dispatchEvent(new Event(type, { bubbles: true }));
}
