/**
 * What the adapter does to a page it does not own: wait for it, find words on
 * it, move inside the app, scroll the window under the header, type the way a
 * visitor types, and refuse anything that leads into a login, a payment, the
 * RUT or "Crear cotización". The ring is Stage's spotlight (`site.ts` has its
 * look); the waiting helpers are Stage's too.
 *
 * www.agroplanet.cl is one Angular app (Angular Material, `<app-root>`) over a
 * JSON API at `api.agroplanet.cl/webapi/` (SAP Hybris underneath). Every move
 * between its pages is the app's own router: the document never reloads, the
 * route's component is swapped inside `mat-sidenav-content`, and the address
 * changes with `history.pushState`. A page is ready once its route's
 * component has drawn what a move needs and the DOM has been quiet a moment;
 * nothing waits for `load`, which trackers (GTM, Facebook, Retargetly…) hold
 * back on the first load only.
 *
 * The store sells by quote: there is no checkout and no online payment. The
 * cart's "Cotizar" opens the Formulario de cotización (/cotizacion); Javier
 * may type there everything but the RUT, and the visitor presses "Crear
 * cotización" themselves.
 */

import { clean, quiet, setValue, sleep, visible, waitFor as waitUntil } from "@voqalize/stage";

export { clean, quiet, setValue, sleep, visible };

export const WAIT_MS = 8000;

export const HOST = "agroplanet.cl";

/**
 * For matching what the brain said against what the page shows: lower case,
 * without accents (á → a, ñ → n), with straight quotes and dashes, without
 * the opening "¿"/"¡" and closing punctuation either side may or may not have.
 */
export const norm = (s: string | null | undefined) =>
  clean(s)
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[®™]/g, "")
    .replace(/[‘’´`]/g, "'")
    .replace(/[“”«»]/g, '"')
    .replace(/[‐-―]/g, "-")
    .replace(/\s*&\s*/g, " y ")
    .replace(/[¿¡]/g, "")
    .replace(/…/g, "")
    .replace(/\s+/g, " ")
    .replace(/^[\s"']+|[\s"'.:;,?!]+$/g, "")
    .trim();

/** Only the letters and digits of `norm`: "Bio-Bio" and "Biobío", "O'Higgins"
 *  and "OHiggins" are one. */
export const bare = (s: string | null | undefined) => norm(s).replace(/[^a-z0-9ñ]+/g, "");

/** `visible` as a plain answer, where a narrowing guard would narrow too far. */
export const shown = (el: Element): boolean => visible(el);

/** Poll `fn` until it answers, or `ms` pass (8 s by default). */
export const waitFor = <T>(fn: () => T | null | undefined | false, ms = WAIT_MS): Promise<T | null> => waitUntil(fn, ms);

/** Page order, for lists gathered from several selectors. */
export const inOrder = (a: Node, b: Node) =>
  a === b ? 0 : a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;

/** The best match for what the brain said among `items`: the same words, then
 *  one that starts with them, then one they start with, then one that holds
 *  them; last, the same letters without spaces or dashes. */
export function best<T>(items: T[], text: (t: T) => string, said: string): T | null {
  const want = norm(said);
  if (!want) return null;
  const t = (i: T) => norm(text(i));
  return (
    items.find((i) => t(i) === want) ??
    items.find((i) => t(i).startsWith(want)) ??
    items.find((i) => want.startsWith(t(i)) && t(i).length > 3) ??
    items.find((i) => t(i).includes(want)) ??
    items.find((i) => bare(text(i)) === bare(said)) ??
    null
  );
}

/** A CLP amount as the site writes it ("$80.000"): the digits of the first
 *  amount, or null. Pesos have no cents, so a dot, a comma or a thin space
 *  only groups the thousands (a page Chrome translated shows "$80,000"). */
export function money(text: string | null | undefined): number | null {
  const m = (text ?? "").match(/\$\s*(\d[\d.,  ]*)/) ?? (text ?? "").match(/(\d[\d.,  ]*)/);
  if (!m) return null;
  const n = Number(m[1].replace(/[.,  ]/g, ""));
  return Number.isFinite(n) ? n : null;
}

/** The path of a link or address on this site. */
export function pathOf(href: string | null | undefined): string {
  try {
    return new URL(href ?? "", location.origin).pathname;
  } catch {
    return "";
  }
}

const strip = (p: string) => decodeURIComponent((p || "/").replace(/\/+$/, "") || "/");
export const samePath = (a: string, b: string) => {
  try {
    return strip(pathOf(a)).toLowerCase() === strip(pathOf(b)).toLowerCase();
  } catch {
    return false;
  }
};

/**
 * A product's SKU from its path (`/producto/aceite_lubritek_utf_semisintetico
 * _19l/1173221`, `/producto/x/1173221`), from Hybris' own (`…/p/1173221`), or
 * from a bare SKU. The slug means nothing to the app: it routes by the SKU.
 */
export function productSku(path: string | number | null | undefined): string | null {
  const s = String(path ?? "").trim();
  const m = s.match(/\/producto\/(?:[^/?#]*\/)?(\d{3,})(?:[/?#]|$)/i) ?? s.match(/\/p\/(\d{3,})(?:[/?#]|$)/) ?? s.match(/^(\d{3,})$/);
  return m ? m[1]! : null;
}

/** A slug as the site writes them: lower case, no accents, words joined by
 *  "_" ("Aceite LUBRITEK UTF 19L" → "aceite_lubritek_utf_19l"). */
export const slug = (name: string) =>
  norm(name)
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "") || "producto";

/** A product's path, `/producto/<slug>/<sku>`: the brain and the page match
 *  products by the SKU, whatever slug a link carried. */
export const productPath = (sku: string, name = "") => `/producto/${slug(name)}/${sku}`;

// ─── Never a login, a payment, the RUT or "Crear cotización" ─────────────

/**
 * The quote is as far as Javier goes: the cart's "Cotizar" opens the
 * Formulario de cotización, he types what the visitor said yes to (name,
 * phone, email, región, comuna, street, number, unit, notes) and stops. The
 * RUT is theirs to type and "Crear cotización" theirs to press.
 *
 * Refused wherever they are: the header's login ("¡Hola! Inicia Sesión", its
 * dropdown with "Iniciar Sesión" and "Regístrate"), any password field, the
 * quote's "Crear cotización", the product page's "Cotizar" (it adds to the
 * cart and opens the quote in one press; he adds with "Agregar al carro"),
 * and every link off the store (Webpay, the help site, WhatsApp) or to its
 * login, registration and account pages. Words are checked as well, as a
 * second net, because Chrome's translator rewrites them.
 */
const NEVER = [
  "app-icon-sign-in",
  "app-dialog-suggestions",
  "input[type=password]",
  "app-form-user-quote button.btn-round-orange-fill",
  "app-form-user-quote button[type=submit]",
  "app-product-info button.btn-round-orange-empty",
  "app-product-info button.btn-cotizar",
  "[href*='/registrate']",
  "[href*='/acceso-revision']",
  "[href*='/perfil']",
  "[href*='webpay']",
].join(", ");

/** What only the visitor types: a RUT (or RUN), a password, a card and its
 *  code or date. Matched on a field's name, form control, id, autocomplete,
 *  placeholder and label. */
const PRIVATE_FIELD = /\b(?:rut|run)\b|password|contrase|tarjeta|\bcard\b|\bcvv\b|\bcvc\b|vencimiento/i;

/** The header's search box (two copies: the header's and the sticky bar's). */
export const SEARCH_BOX = "#smartSearchId";

/** The quote form's fields Javier may type in, once the visitor said yes: by
 *  their Angular form control. */
export const QUOTE_FIELDS = ["name", "phone", "email", "street", "numberAddress", "depto", "reference"] as const;
const QUOTE_TYPEABLE = QUOTE_FIELDS.map((f) => `app-form-user-quote [formcontrolname="${f}"]`).join(", ");

/** The words a field goes by: its control, name, id, autocomplete,
 *  placeholder, aria-label and label. */
function fieldWords(el: Element): string {
  const id = el.id;
  const label = clean(
    (id ? document.querySelector(`label[for="${CSS.escape(id)}"]`)?.textContent : null) ??
      el.closest("mat-form-field")?.querySelector("mat-label")?.textContent ??
      el.closest("label")?.textContent,
  );
  return [el.getAttribute("formcontrolname"), el.getAttribute("name"), id, el.getAttribute("autocomplete"), el.getAttribute("placeholder"), el.getAttribute("aria-label"), label]
    .filter(Boolean)
    .join(" ");
}

/** Why `el`, a form field, is not Javier's to type in, or null. The RUT and
 *  any password or card field are refused first, whatever else they are. */
export function privateField(el: Element): string | null {
  if (el instanceof HTMLInputElement && el.type === "password") return "it is a password field";
  const words = fieldWords(el);
  if (el.getAttribute("formcontrolname") === "rut" || PRIVATE_FIELD.test(words)) {
    return `its field is the visitor's to type ("${clean(el.closest("mat-form-field")?.querySelector("mat-label")?.textContent) || el.getAttribute("placeholder") || el.getAttribute("formcontrolname") || el.id}")`;
  }
  if (el.matches(SEARCH_BOX)) return null;
  if (el.matches(QUOTE_TYPEABLE) && quotePage()) return null;
  return `Javier types only in the search box and the quote form, not in "${el.getAttribute("placeholder") || el.getAttribute("formcontrolname") || el.id || el.tagName.toLowerCase()}"`;
}

const lower = (p: string) => decodeURIComponent(p).toLowerCase().replace(/\/+$/, "") || "/";

/** The Formulario de cotización is in front. */
export const quotePage = () => lower(location.pathname) === "/cotizacion";

/** A path Javier never opens: the login, registration and account pages, the
 *  quote's confirmation (only the visitor's own press gets there), and
 *  Autoplanet's old checkout still in the app. */
export function forbiddenPath(path: string): boolean {
  const p = lower(path);
  return /^\/(registrate|acceso-revision|perfil|activar|sesion-expirada|no-autorizado|revision|checkout|login|mi-cuenta)(\/|$)/.test(p) || /^\/cotizacion\/./.test(p);
}

const NEVER_WORDS =
  /crear cotizaci[oó]n|\bpagar\b|webpay|finalizar compra|inicia(r)? sesi[oó]n|reg[ií]strate|crear (nueva )?cuenta|mi cuenta|log ?in|sign (in|up)|create (account|quote)|\bpay\b|place order/i;

/** Why `el` must not be pressed, or null. */
export function refusal(el: Element): string | null {
  const never = el.closest(NEVER);
  if (never) {
    if (never.matches("app-form-user-quote button, app-form-user-quote button *")) return `it is "Crear cotización", which only the visitor presses`;
    if (never.closest("app-product-info")) return "it is the product page's Cotizar, which adds to the cart and opens the quote in one press; Javier adds with Agregar al carro, then the cart's Cotizar";
    return `it is a login, registration or payment control (${never.tagName.toLowerCase()}${never.id ? `#${never.id}` : ""}), which are the visitor's`;
  }
  if (el.matches("input:not([type=checkbox]), textarea")) {
    const why = privateField(el);
    if (why) return why;
  }
  const link = el.closest<HTMLAnchorElement>("a[href]");
  if (link) {
    const href = link.getAttribute("href") ?? "";
    if (href && !href.startsWith("#") && !href.startsWith("javascript:")) {
      const to = new URL(href, location.href);
      if (to.host.replace(/^www\./, "") !== HOST) return `it links off the store (${to.host})`;
      if (forbiddenPath(to.pathname)) return `it links to ${to.pathname}`;
    }
  }
  // A policy page's panel may well say "pagar"; it opens an answer.
  if (el.closest("mat-expansion-panel-header")) return null;
  const words = clean(`${el.textContent ?? ""} ${el.getAttribute("title") ?? ""} ${el.getAttribute("aria-label") ?? ""}`);
  if (words.length < 40 && NEVER_WORDS.test(words)) return `it says "${words}"`;
  return null;
}

/** Click `el` as a visitor would, unless it is a login, a payment or "Crear
 *  cotización": then refuse, and nothing is pressed. Every click the adapter
 *  makes goes through here. */
export function press(el: Element): void {
  const why = refusal(el);
  if (why) throw new Error(`refused to press it: ${why}. Javier stops at the Formulario de cotización; the login, the RUT, "Crear cotización" and any payment are the visitor's`);
  (el as HTMLElement).click();
}

/** Hover `el` as a pointer does: the category menu opens its flyout on it. */
export function hover(el: Element): void {
  const why = refusal(el);
  if (why) throw new Error(`refused to point at it: ${why}`);
  for (const type of ["pointerover", "mouseover", "mouseenter", "mousemove"]) {
    el.dispatchEvent(new MouseEvent(type, { bubbles: type !== "mouseenter", cancelable: true, view: window }));
  }
}

/** Where `path` goes on this site, unless it is a login, account or
 *  confirmation page or another host: then refuse. Every route change and
 *  every load a move makes is checked here first. */
export function target(path: string): string {
  const to = new URL(path, location.origin);
  if (to.host.replace(/^www\./, "") !== HOST) {
    throw new Error(`${to.href} is not on www.agroplanet.cl; only the store's own pages open here`);
  }
  if (forbiddenPath(to.pathname)) throw new Error(`refused to open ${to.pathname}: Javier never opens a login, an account page or the quote's confirmation`);
  return to.origin + to.pathname + to.search + to.hash;
}

/** Move the app to `path` without a load, as its own router does: the address
 *  pushed, then the `popstate` Angular's router listens to. */
export function routeTo(path: string): void {
  const to = new URL(target(path));
  history.pushState(null, "", to.pathname + to.search + to.hash);
  window.dispatchEvent(new PopStateEvent("popstate", { state: null }));
}

/** Load `path` in this tab (a full load), unless `target` refuses it. */
export function go(path: string): void {
  location.assign(target(path));
}

// ─── Scrolling ────────────────────────────────────────────────────────────

/** Room kept at the top: the compact header (64 px, fixed) comes in once the
 *  window is past ~150 px, so a target is never placed under it. */
export const HEADER_OFFSET = 80;

/** What sits over the bottom of the screen: the cookie bar, until accepted. */
function bottomBars(): number {
  const bar = document.querySelector<HTMLElement>(".cookies-wrapper");
  if (!bar || !visible(bar)) return 0;
  const r = bar.getBoundingClientRect();
  return r.top < window.innerHeight ? window.innerHeight - r.top : 0;
}

/** The height of what is pinned to the top now (the compact header), never
 *  less than the room it takes when it comes in. */
export function headerHeight(): number {
  const bar = document.querySelector<HTMLElement>("app-sticky-header-desktop mat-toolbar.shadow-sticky");
  const r = bar?.getBoundingClientRect();
  const pinned = bar && r && getComputedStyle(bar).position === "fixed" && r.top >= -2 && r.height > 0 ? r.bottom : 0;
  return Math.max(HEADER_OFFSET, pinned + 12);
}

function distance(el: Element, align: "top" | "center"): number {
  const r = el.getBoundingClientRect();
  const top = headerHeight();
  const room = window.innerHeight - top - bottomBars();
  if (align === "center" && r.height < room) return r.top - (top + (room - r.height) / 2);
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

/** Scroll the window so `el` sits in the middle of what the header and the
 *  cookie bar leave (`center`, the default), or just under the header when
 *  it is taller than that, measuring again as late images move the page. The
 *  home's empty splash window, which locks scrolling, is closed first. */
export async function scrollTo(el: Element, align: "top" | "center" = "center"): Promise<void> {
  await closeSplash();
  innerScroll(el);
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

/** A list that scrolls inside the page (a filter panel's options, the
 *  category menu's flyout) brought round to `el` first: the window alone
 *  cannot. */
function innerScroll(el: Element): void {
  for (let box = el.parentElement; box && box !== document.body && box !== document.documentElement; box = box.parentElement) {
    const style = getComputedStyle(box);
    if (!/(auto|scroll)/.test(style.overflowY) || box.scrollHeight <= box.clientHeight + 4) continue;
    const r = el.getBoundingClientRect();
    const b = box.getBoundingClientRect();
    const delta = r.top - b.top - Math.max(0, (box.clientHeight - r.height) / 2);
    box.scrollTop += delta;
    return;
  }
}

export async function scrollToTopOfPage(): Promise<void> {
  await closeSplash();
  if (window.scrollY < 4) return;
  window.scrollTo({ top: 0, behavior: "smooth" });
  await scrollEnded();
}

// ─── Boxes ────────────────────────────────────────────────────────────────

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

// ─── The site's own windows ───────────────────────────────────────────────

/**
 * The home's splash window: on every full load of `/` the app opens an empty
 * `mat-dialog` (its CMS slot has no banner) whose backdrop covers the page
 * and whose `cdk-global-scrollblock` on `<html>` stops all scrolling. Closed
 * with its own "×" before any scroll and when a call starts.
 */
export async function closeSplash(): Promise<boolean> {
  const dialog = document.querySelector<HTMLElement>("app-generic-dialog");
  if (!dialog) return false;
  const close = dialog.querySelector<HTMLElement>(".close");
  if (close) close.click();
  else document.querySelector<HTMLElement>(".cdk-overlay-backdrop")?.click();
  await waitFor(() => !document.querySelector("app-generic-dialog") && !document.documentElement.classList.contains("cdk-global-scrollblock"), 1500);
  return true;
}

/** The cookie bar's "Entendido", pressed once a call starts, so the bar (100
 *  px, full width, fixed to the bottom) stops covering what he rings. Pressing
 *  it is what a visitor does to read the page; it stores the site's own
 *  `accept-cookies`. */
export function acceptCookies(): void {
  const bar = document.querySelector<HTMLElement>(".cookies-wrapper");
  if (!bar) return;
  const ok = [...bar.querySelectorAll<HTMLElement>("button")].find((b) => /entendido|got it|understood/i.test(clean(b.textContent)));
  ok?.click();
}

/**
 * The page's style during a call (`html[data-voqalize-call]`). Our widget
 * already sits at z-index 2147483001, above everything the site pins (the
 * phone menu's sidenav at 40000, the compact header at 10001, the cookie bar
 * at 10000, Material's overlays and WhatsApp at 1000); the rule below only
 * keeps the site's scroll-to-top square from sitting on the widget's row on a
 * phone. Nothing of the site is hidden: it has no chat of its own.
 */
export function styleThePage(): void {
  if (document.querySelector("style[data-voqalize=agroplanet]")) return;
  const style = document.createElement("style");
  style.setAttribute("data-voqalize", "agroplanet");
  style.textContent = `
    html[data-voqalize-call] .back-to-top { z-index: 1000 !important; }
  `;
  (document.head ?? document.documentElement).appendChild(style);
}

// ─── Waiting for a page ───────────────────────────────────────────────────

/**
 * The page has settled: parsed, the app's shell drawn (`app-master`), its
 * fonts in (or 1.5 s), and the DOM quiet for a moment. Never the `load`
 * event, which the trackers hold back.
 */
export async function settled(): Promise<void> {
  if (document.readyState === "loading") {
    await new Promise<void>((r) => document.addEventListener("DOMContentLoaded", () => r(), { once: true }));
  }
  await waitFor(() => document.querySelector("app-master, app-root > *"), 8000);
  await Promise.race([document.fonts?.ready, sleep(1500)]);
  await quiet(document.body, 400, 2500);
}

// ─── The store's API calls, watched ───────────────────────────────────────

/**
 * The app calls `api.agroplanet.cl/webapi/` with Angular's HttpClient
 * (XMLHttpRequest); a filter, a sort, an add or a route is done once its
 * calls are back. Each call is counted while it runs, fetches too, and the
 * last one's end kept, so a move can wait for the site's own answer rather
 * than for a guessed delay. Every answer is also handed to `onApi`
 * listeners: the adapter keeps the listings' and the cart's.
 */
let inFlight = 0;
let lastDone = 0;
let watching = false;
const API_RE = /api\.agroplanet\.cl\/webapi\//;
const listeners: ((url: string, method: string, body: () => unknown) => void)[] = [];

/** The page's own `fetch`, as it was before `watchApi`: the adapter's own
 *  reads go through it, so they never count as the site's calls (a move
 *  waiting for the site must not wait for its own reads). */
export const ownFetch: typeof fetch = typeof window !== "undefined" && window.fetch ? window.fetch.bind(window) : (undefined as unknown as typeof fetch);

/** Hear each answer of the store's API: its address, method and parsed body
 *  (read lazily; null when it was not JSON). */
export function onApi(fn: (url: string, method: string, body: () => unknown) => void): void {
  listeners.push(fn);
}

function heard(url: string, method: string, body: () => unknown): void {
  for (const fn of listeners) {
    try {
      fn(url, method, body);
    } catch {
      // A listener's failure is its own.
    }
  }
}

const once = <T>(fn: () => T) => {
  let done = false;
  let value: T;
  return () => {
    if (!done) [done, value] = [true, fn()];
    return value;
  };
};

export function watchApi(): void {
  if (watching) return;
  watching = true;
  if (typeof XMLHttpRequest !== "undefined") {
    const open = XMLHttpRequest.prototype.open;
    const send = XMLHttpRequest.prototype.send;
    type Xhr = XMLHttpRequest & { __agro?: { url: string; method: string } };
    XMLHttpRequest.prototype.open = function (this: Xhr, method: string, url: string | URL, ...rest: unknown[]) {
      this.__agro = API_RE.test(String(url)) ? { url: new URL(String(url), location.href).href, method: method.toUpperCase() } : undefined;
      return (open as (...a: unknown[]) => void).call(this, method, url, ...rest);
    } as typeof XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.send = function (this: Xhr, body?: Document | XMLHttpRequestBodyInit | null) {
      const call = this.__agro;
      if (call) {
        inFlight++;
        // Read at readyState 4: on agroplanet.cl something reading the same
        // requests leaves `status` at 0 by the time `load` and `loadend`
        // fire, so the answer is taken the moment it is complete.
        let answer: { status: number; text: string | null; json: unknown } | null = null;
        const complete = () => {
          if (answer || this.readyState !== 4) return;
          let text: string | null = null;
          try {
            text = this.responseType === "" || this.responseType === "text" ? this.responseText : null;
          } catch {
            text = null;
          }
          answer = { status: this.status, text, json: this.responseType === "json" ? this.response : undefined };
        };
        this.addEventListener("readystatechange", complete);
        this.addEventListener(
          "loadend",
          () => {
            complete();
            inFlight = Math.max(0, inFlight - 1);
            lastDone = Date.now();
            const got = answer;
            if (got && got.status >= 200 && got.status < 300) {
              heard(call.url, call.method, once(() => {
                try {
                  return got.json !== undefined ? got.json : got.text ? JSON.parse(got.text) : null;
                } catch {
                  return null;
                }
              }));
            }
          },
          { once: true },
        );
      }
      return send.call(this, body);
    };
  }
  if (typeof window.fetch === "function") {
    const fetchBefore = window.fetch.bind(window);
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (!API_RE.test(url)) return fetchBefore(input, init);
      inFlight++;
      try {
        const r = await fetchBefore(input, init);
        if (r.ok) {
          const copy = r.clone();
          let body: unknown = null;
          await copy.json().then((b) => (body = b), () => null);
          heard(new URL(url, location.href).href, (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase(), () => body);
        }
        return r;
      } finally {
        inFlight = Math.max(0, inFlight - 1);
        lastDone = Date.now();
      }
    };
  }
}

/** None of the site's calls to its API is out, and none ended in the last
 *  `idleMs`: the page shows the store's answer, not a redraw in between. */
export const apiIdle = (idleMs = 250): boolean => inFlight === 0 && Date.now() - lastDone >= idleMs;

/** The site's calls to its API are back and none has run for `idleMs`, or
 *  `ms` passed. True when at least one call ended since `since`. */
export async function apiSettled(since: number, ms = 10_000, idleMs = 350): Promise<boolean> {
  const until = Date.now() + ms;
  while (Date.now() < until) {
    if (inFlight === 0 && lastDone >= since && Date.now() - lastDone >= idleMs) return true;
    await sleep(80);
  }
  return lastDone >= since;
}

// ─── Typing ───────────────────────────────────────────────────────────────

function nativeSet(el: HTMLInputElement | HTMLTextAreaElement, value: string): void {
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(el, value);
}

/** Type `text` into the search box or a field of the quote form, one
 *  character at a time at a visitor's pace, with the key and `input` events
 *  each one sends (Angular's forms listen to `input`; the search box's
 *  suggestions to `keyup`). Leaving the field (`change`, `blur`) is `leave`'s.
 *  No Enter: the move presses it when it means
 *  to. Any other field, the RUT first, is refused (`privateField`). */
export async function typeInto(el: HTMLInputElement | HTMLTextAreaElement, text: string, perKeyMs = 95): Promise<void> {
  const why = privateField(el);
  if (why) throw new Error(`refused to type: ${why}`);
  el.focus({ preventScroll: true });
  nativeSet(el, "");
  el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "deleteContentBackward" }));
  let value = "";
  for (const ch of text) {
    value += ch;
    // With the key's code: the search box's suggestions listen to `keyup`
    // and read `keyCode`, as a keyboard sends it.
    const up = ch.toUpperCase();
    const keyCode = /^[A-Z0-9]$/.test(up) ? up.charCodeAt(0) : ch === " " ? 32 : 0;
    const key = { bubbles: true, key: ch, code: /^[A-Z]$/.test(up) ? `Key${up}` : /^\d$/.test(ch) ? `Digit${ch}` : "", keyCode, which: keyCode } as KeyboardEventInit;
    el.dispatchEvent(new KeyboardEvent("keydown", key));
    nativeSet(el, value);
    el.dispatchEvent(new InputEvent("input", { bubbles: true, data: ch, inputType: "insertText" }));
    el.dispatchEvent(new KeyboardEvent("keyup", key));
    await sleep(perKeyMs + (ch === " " ? 60 : 0));
  }
  // No `change` yet: a browser sends it when the field is left (`leave`),
  // and the search box closes its suggestions on it.
}

/** Leave a field as a visitor's next click does: `blur` and `focusout`, which
 *  Angular's forms read as touched. */
export function leave(el: HTMLElement): void {
  el.dispatchEvent(new Event("change", { bubbles: true }));
  el.dispatchEvent(new FocusEvent("blur"));
  el.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
  el.blur();
}

/** Press Enter in `el` as the keyboard does: keydown, keypress, keyup. The
 *  search box submits its form on it. */
export function enter(el: HTMLElement): void {
  for (const type of ["keydown", "keypress", "keyup"]) {
    el.dispatchEvent(new KeyboardEvent(type, { bubbles: true, cancelable: true, key: "Enter", code: "Enter", keyCode: 13, which: 13 } as KeyboardEventInit));
  }
}
