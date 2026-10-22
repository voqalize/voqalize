/**
 * What the adapter does to a page it does not own: wait for it, find words on
 * it, scroll the window under the fixed bars, draw the ring, type the way a
 * visitor types, and refuse anything that leads into checkout.
 *
 * cannonhome.cl is Magento 2 (Luma-derived theme, RequireJS, jQuery,
 * Knockout). Every move between pages is a full page load; listing filters,
 * sort and paging, and add-to-cart, are AJAX. Third-party trackers hold the
 * `load` event back for more than 15 s, so nothing here waits for it: a page
 * is ready once it is parsed, the selectors a move needs are there, and the DOM
 * has been quiet for a moment.
 */

/** Cannon Home's own "look here" colour: the deep red of every sale price
 *  (`.special-price .price`, #a01a1a in the theme's stylesheet). The brand's
 *  ink (#242128) is the colour of the text, so a dark ring would read as part
 *  of the page; the red reads on white, on the grey product photos and on the
 *  black bars. */
export const RING = "#a01a1a";
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
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[‘’´`]/g, "'")
    .replace(/[“”«»]/g, '"')
    .replace(/[‐-―]/g, "-")
    .replace(/\s*&\s*/g, " y ")
    .replace(/[¿¡]/g, "")
    .replace(/…/g, "")
    .replace(/^[\s"']+|[\s"'.:;,?!]+$/g, "")
    .trim();

export const visible = (el: Element | null | undefined): el is HTMLElement => {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};

/** `visible` as a plain answer, where a narrowing guard would narrow too far. */
export const shown = (el: Element): boolean => visible(el);

export async function waitFor<T>(fn: () => T | null | undefined | false, ms = WAIT_MS): Promise<T | null> {
  const until = Date.now() + ms;
  for (;;) {
    const v = fn();
    if (v) return v;
    if (Date.now() > until) return null;
    await sleep(100);
  }
}

/** Page order, for lists gathered from several selectors. */
export const inOrder = (a: Node, b: Node) =>
  a === b ? 0 : a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;

/** The best match for what the brain said among `items`: the same words, then
 *  one that starts with them, then one they start with, then one that holds
 *  them. */
export function best<T>(items: T[], text: (t: T) => string, said: string): T | null {
  const want = norm(said);
  if (!want) return null;
  const t = (i: T) => norm(text(i));
  return (
    items.find((i) => t(i) === want) ??
    items.find((i) => t(i).startsWith(want)) ??
    items.find((i) => want.startsWith(t(i)) && t(i).length > 3) ??
    items.find((i) => t(i).includes(want)) ??
    null
  );
}

/** A CLP amount as the site writes it ("$55.993", "Te faltan $120.010 …"):
 *  the digits of the first amount, or null. Dots group thousands; there are no
 *  decimals. Chrome's translator leaves the figures alone. */
export function money(text: string | null | undefined): number | null {
  const m = (text ?? "").match(/\$\s*([\d.]+)/) ?? (text ?? "").match(/(\d[\d.]*)/);
  if (!m) return null;
  const n = Number(m[1].replace(/\./g, ""));
  return Number.isFinite(n) ? n : null;
}

/** A `data-price-amount` (raw CLP, "55993" or "28495.0000"), or null. */
export function amount(el: Element | null | undefined): number | null {
  const raw = el?.getAttribute("data-price-amount");
  if (raw == null || raw === "") return null;
  const n = Math.round(Number(raw));
  return Number.isFinite(n) ? n : null;
}

/** The path of a link or address on this site ("/x.html"). */
export function pathOf(href: string | null | undefined): string {
  try {
    return new URL(href ?? "", location.origin).pathname;
  } catch {
    return "";
  }
}

const strip = (p: string) => (p || "/").replace(/\/+$/, "") || "/";
export const samePath = (a: string, b: string) => strip(pathOf(a)).toLowerCase() === strip(pathOf(b)).toLowerCase();

// ─── Never into checkout ──────────────────────────────────────────────────

/**
 * Everything that leads into checkout, a login or a payment, by structure:
 * the minicart's "Finalizar compra" (`#top-cart-btn-checkout`, the drawer's
 * primary button), the cart page's "Terminar pedido"
 * (`[data-role=proceed-to-checkout]`), any `.action.checkout`, the login
 * modal it opens, and the account pages. Structure, not words, because Chrome's
 * translator rewrites the words; the words are checked as well, as a second
 * net.
 */
const CHECKOUT = [
  "#top-cart-btn-checkout",
  "[data-role='proceed-to-checkout']",
  ".action.checkout",
  "button.checkout",
  ".checkout-methods-items",
  ".mc-btn--primary",
  "[data-action='checkout']",
  "aside.login-modal",
  ".block-customer-login",
  "#checkout",
].join(", ");
const CHECKOUT_WORDS = /finalizar compra|terminar pedido|ir a pagar|pagar ahora|comprar como invitado|proceed to checkout|go to checkout|\bcheckout\b|iniciar sesi[oó]n|\blog ?in\b|sign in/i;

/** A path Javier never loads: checkout (but not the bag, /checkout/cart/,
 *  nor adding to it), the account and login pages, payment returns. */
export function forbiddenPath(path: string): boolean {
  // Magento also routes every path under /index.php/ (/index.php/checkout/).
  const p = path.toLowerCase().replace(/^\/index\.php(?=\/|$)/, "").replace(/\/+$/, "") || "/";
  // The bag itself, and the add-to-bag form's own address.
  if (p === "/checkout/cart" || p === "/checkout/cart/index" || p.startsWith("/checkout/cart/add/")) return false;
  if (p.startsWith("/checkout")) return true;
  return /^\/(onestepcheckout|customer\/account|sales\/order|webpay|mercadopago|paypal|braintree)(\/|$)/.test(p);
}

/** Why `el` must not be pressed, or null. */
export function intoCheckout(el: Element): string | null {
  const hit = el.closest(CHECKOUT);
  if (hit) return `it is the checkout control (${hit.id ? `#${hit.id}` : hit.className || hit.tagName.toLowerCase()})`;
  const link = el.closest<HTMLAnchorElement>("a[href]");
  if (link) {
    const href = link.getAttribute("href") ?? "";
    if (href && !href.startsWith("#") && !href.startsWith("javascript:")) {
      const to = new URL(href, location.href);
      if (to.origin === location.origin && forbiddenPath(to.pathname)) return `it links to ${to.pathname}`;
    }
  }
  const button = el.closest<HTMLButtonElement | HTMLInputElement>("button, input[type=submit]");
  const form = button?.form ?? el.closest("form");
  if (button && form && (button as HTMLButtonElement).type === "submit") {
    const action = form.getAttribute("action") ?? "";
    if (action && forbiddenPath(new URL(action, location.href).pathname)) return `it submits to ${new URL(action, location.href).pathname}`;
  }
  const words = clean(`${el.textContent ?? ""} ${el.getAttribute("title") ?? ""} ${el.getAttribute("aria-label") ?? ""}`);
  if (words.length < 60 && CHECKOUT_WORDS.test(words)) return `it says "${words}"`;
  return null;
}

/** Click `el` as a visitor would, unless it leads into checkout: then refuse,
 *  and nothing is pressed. Every click the adapter makes goes through here. */
export function press(el: Element): void {
  const why = intoCheckout(el);
  if (why) throw new Error(`refused to press it: ${why}. Javier never goes into checkout; the visitor does that`);
  (el as HTMLElement).click();
}

/** Load another page of this site in this tab, unless it is checkout, an
 *  account page or another host. */
export function go(path: string): void {
  const to = new URL(path, location.origin);
  if (to.host.replace(/^www\./, "") !== location.host.replace(/^www\./, "")) {
    throw new Error(`${to.href} is not on ${location.host}; only this site's own pages open here`);
  }
  if (forbiddenPath(to.pathname)) throw new Error(`refused to open ${to.pathname}: Javier never goes into checkout or an account`);
  clearHighlight();
  location.assign(to.pathname + to.search + to.hash);
}

// ─── Scrolling ────────────────────────────────────────────────────────────

/** Bars that can be pinned to the top: the black "12 CUOTAS SIN INTERÉS"
 *  marquee (`#topbarCannonBar`, 32 px, fixed on every width) and, on a phone,
 *  the header under it (`header.page-header`, fixed). On a desktop the header
 *  and the menu scroll away, so only the marquee counts. */
const BARS = "#topbarCannonBar, header.page-header, .nav-sections, .sticky-header";

/** The height of whatever is pinned to the top of the viewport; bars count
 *  when they start where the bars above them end. */
export function headerHeight(): number {
  const bars = [...document.querySelectorAll<HTMLElement>(BARS)]
    .map((el) => ({ el, r: el.getBoundingClientRect() }))
    .filter(({ el, r }) => {
      if (r.height <= 0 || r.height > 220 || r.top < -2) return false;
      const pos = getComputedStyle(el).position;
      return pos === "fixed" || pos === "sticky";
    })
    .sort((a, b) => a.r.top - b.r.top);
  let h = 0;
  for (const { r } of bars) if (r.top <= h + 4) h = Math.max(h, r.bottom);
  return h;
}

function distance(el: Element, align: "top" | "center"): number {
  const r = el.getBoundingClientRect();
  const top = headerHeight() + 8;
  if (align === "center") {
    const room = window.innerHeight - top;
    return r.top - (top + Math.max(0, (room - r.height) / 2));
  }
  return r.top - top;
}

async function scrollEnded(): Promise<void> {
  let last = -1;
  let still = 0;
  const until = Date.now() + 2500;
  while (Date.now() < until) {
    await sleep(80);
    if (Math.abs(window.scrollY - last) < 1) {
      if (++still >= 3) return;
    } else {
      still = 0;
    }
    last = window.scrollY;
  }
}

/** Scroll the window so `el` sits under the bars (`top`) or in the middle of
 *  the screen, measuring again as late images move the page. */
export async function scrollTo(el: Element, align: "top" | "center" = "top"): Promise<void> {
  for (let pass = 0; pass < 3; pass++) {
    const delta = distance(el, align);
    if (Math.abs(delta) < 12) return;
    const max = document.documentElement.scrollHeight - window.innerHeight;
    const y = Math.min(Math.max(window.scrollY + delta, 0), max);
    if (Math.abs(y - window.scrollY) < 8) return;
    window.scrollBy({ top: y - window.scrollY, behavior: "smooth" });
    await scrollEnded();
  }
}

export async function scrollToTopOfPage(): Promise<void> {
  if (window.scrollY < 4) return;
  window.scrollTo({ top: 0, behavior: "smooth" });
  await scrollEnded();
}

// ─── The ring ─────────────────────────────────────────────────────────────

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
    ring.el.style.opacity = "1";
    Object.assign(ring.el.style, {
      transform: `translate(${b.left - 6}px, ${b.top - 6}px)`,
      width: `${b.right - b.left + 12}px`,
      height: `${b.bottom - b.top + 12}px`,
    });
  }
  ringFrame = requestAnimationFrame(follow);
}

/** Ring each group: one element, or several ringed as one box. */
export function highlight(...groups: (Element | Element[])[]): void {
  clearHighlight();
  for (const group of groups) {
    const targets = Array.isArray(group) ? group : [group];
    if (!boxOf(targets)) continue;
    const el = document.createElement("div");
    el.setAttribute("data-voqalize", "highlight");
    Object.assign(el.style, {
      position: "fixed",
      left: "0",
      top: "0",
      border: "3px solid var(--voqalize-ring)",
      borderRadius: "10px",
      pointerEvents: "none",
      zIndex: "2147483000",
      opacity: "0",
      transition: "opacity 300ms ease",
      animation: "voqalize-ring 1.4s ease-in-out 3",
    });
    // Outside <body>, whose `zoom: 0.8` would scale the ring off its target.
    document.documentElement.appendChild(el);
    rings.push({ el, targets });
  }
  follow();
  ringTimer = setTimeout(clearHighlight, RING_MS);
}

export function clearHighlight(): void {
  if (ringTimer) clearTimeout(ringTimer);
  cancelAnimationFrame(ringFrame);
  rings.forEach((r) => r.el.remove());
  rings = [];
}

export function styleThePage(): void {
  if (document.querySelector("style[data-voqalize=cannonhome]")) return;
  const style = document.createElement("style");
  style.setAttribute("data-voqalize", "cannonhome");
  style.textContent = `
    :root { --voqalize-ring: ${RING}; }
    @keyframes voqalize-ring {
      0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--voqalize-ring) 55%, transparent); }
      50% { box-shadow: 0 0 0 10px color-mix(in srgb, var(--voqalize-ring) 0%, transparent); }
    }
    /* In a call, GoPersonal's own voice and camera search in the search box
       would open the microphone a second time: hidden while Javier listens. */
    html[data-voqalize-call] .gp-amsearch-icons .gp-amsearch-icon:not(#gp-clear-icon) { display: none !important; }
  `;
  (document.head ?? document.documentElement).appendChild(style);
}

// ─── Waiting for a page ───────────────────────────────────────────────────

/**
 * The page has settled: parsed, its fonts in (or 1.5 s), and the DOM quiet
 * for a moment. Never the `load` event: GTM, Clarity, Contentsquare, VWO and
 * friends hold it back for more than 15 s on this site.
 */
export async function settled(): Promise<void> {
  if (document.readyState === "loading") {
    await new Promise<void>((r) => document.addEventListener("DOMContentLoaded", () => r(), { once: true }));
  }
  await Promise.race([document.fonts?.ready, sleep(1500)]);
  await quiet(document.body, 400, 2500);
}

/** `root` has not changed for `ms`, or `cap` has passed. */
export function quiet(root: Node, ms = 350, cap = 3000): Promise<void> {
  return new Promise<void>((resolve) => {
    let timer = setTimeout(done, ms);
    const obs = new MutationObserver(() => {
      clearTimeout(timer);
      timer = setTimeout(done, ms);
    });
    obs.observe(root, { childList: true, subtree: true, attributes: true, characterData: true });
    const stop = setTimeout(done, cap);
    function done() {
      obs.disconnect();
      clearTimeout(timer);
      clearTimeout(stop);
      resolve();
    }
  });
}

// ─── Typing ───────────────────────────────────────────────────────────────

function nativeSet(el: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement, value: string): void {
  const proto =
    el instanceof HTMLSelectElement
      ? HTMLSelectElement.prototype
      : el instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(el, value);
}

/** Set a field the way a finished edit does: the native setter (so Knockout
 *  sees it), then `input`, `change` and `blur`. Never a key event, so no
 *  Enter ever reaches a form. */
export function setValue(el: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement, value: string): void {
  nativeSet(el, value);
  for (const type of ["input", "change"]) el.dispatchEvent(new Event(type, { bubbles: true }));
  el.dispatchEvent(new Event("blur"));
  el.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
}

/** Type `text` into a focused search box one character at a time, at a
 *  visitor's pace, with an `input` event per character (Amasty's box is a
 *  Knockout `valueUpdate: 'input'` binding). No blur, which would close the
 *  dropdown, and no Enter, which would load the results page. */
export async function typeInto(el: HTMLInputElement, text: string, perKeyMs = 110): Promise<void> {
  el.focus({ preventScroll: true });
  nativeSet(el, "");
  el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "deleteContentBackward" }));
  let value = "";
  for (const ch of text) {
    value += ch;
    nativeSet(el, value);
    el.dispatchEvent(new InputEvent("input", { bubbles: true, data: ch, inputType: "insertText" }));
    el.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true, key: ch }));
    await sleep(perKeyMs);
  }
}

// ─── A move left for the next page ────────────────────────────────────────

/** Where a move that loads another page leaves the rest of itself, per tab
 *  and per origin, as `sessionStorage` is: a move never leaves the origin. */
const THEN_KEY = "voqalize.cannonhome.then";
/** A move left longer ago than this belongs to some other visit. */
const THEN_MAX_AGE_MS = 60_000;

export interface Leftover {
  command: string;
  payload: unknown;
  /** The brain's command this finishes, when it is not `command` (a search
   *  that opened a product finishes as `search_products`). */
  as?: string;
}

/** Leave `move` for the next page of this tab (or forget any, with null). */
export function leave(move: Leftover | null): void {
  try {
    if (move) sessionStorage.setItem(THEN_KEY, JSON.stringify({ ...move, at: Date.now() }));
    else sessionStorage.removeItem(THEN_KEY);
  } catch {
    // Storage refused: the page still loads, at its top.
  }
}

/** What the last page left to do here, taken once. */
export function takeLeftover(): Leftover | null {
  try {
    const raw = sessionStorage.getItem(THEN_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(THEN_KEY);
    const then = JSON.parse(raw) as Partial<Leftover> & { at?: number };
    if (typeof then.at === "number" && Date.now() - then.at > THEN_MAX_AGE_MS) return null;
    if (typeof then.command !== "string") return null;
    return { command: then.command, payload: then.payload ?? {}, ...(then.as ? { as: then.as } : {}) };
  } catch {
    return null;
  }
}
