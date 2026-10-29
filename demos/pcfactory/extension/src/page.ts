/**
 * What the adapter does to a page it does not own: wait for it, find words on
 * it, scroll the window under the header, type the way a visitor types, and
 * refuse anything that leads past Tipo de entrega, into a login or a payment.
 * The ring is Stage's spotlight (`site.ts` has its look); the waiting helpers
 * are Stage's too.
 *
 * www.pcfactory.cl is Modyo (Rails, server-rendered Liquid pages with
 * Bootstrap 4 and jQuery) with Vue 2 widgets mounted on each page: the
 * listing's filters and grid, the product page, the cart, the checkout, the
 * comparator and the "Producto agregado" window. Every move between pages is
 * a full load; filters, sort, add-to-cart and the cart's − / + stay in the
 * page and talk to `api.pcfactory.cl`. Trackers (GTM, Hotjar, Clarity, Retail
 * Rocket…) hold the `load` event back, so nothing here waits for it: a page is
 * ready once it is parsed, the selectors a move needs are there, and the DOM
 * has been quiet for a moment.
 */

import { clean, quiet, setValue, sleep, visible, waitFor as waitUntil } from "@voqalize/stage";

export { clean, quiet, setValue, sleep, visible };

export const WAIT_MS = 8000;

/**
 * For matching what the brain said against what the page shows: lower case,
 * without accents (á → a, ñ → n), with straight quotes and dashes, without
 * the ® the store prints after brands, and without the opening "¿"/"¡" and
 * closing punctuation either side may or may not have.
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

/** `visible` as a plain answer, where a narrowing guard would narrow too far. */
export const shown = (el: Element): boolean => visible(el);

/** Poll `fn` until it answers, or `ms` pass (8 s by default). */
export const waitFor = <T>(fn: () => T | null | undefined | false, ms = WAIT_MS): Promise<T | null> => waitUntil(fn, ms);

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

/** A CLP amount as the site writes it ("$1.066.990"): the digits of the first
 *  amount, or null. Pesos have no cents, so a dot, a comma or a thin space
 *  only groups the thousands (a page Chrome translated shows "$1,066,990"). */
export function money(text: string | null | undefined): number | null {
  const m = (text ?? "").match(/\$\s*(\d[\d.,  ]*)/) ?? (text ?? "").match(/(\d[\d.,  ]*)/);
  if (!m) return null;
  const n = Number(m[1].replace(/[.,  ]/g, ""));
  return Number.isFinite(n) ? n : null;
}

/** The path of a link or address on this site ("/producto/57233"). */
export function pathOf(href: string | null | undefined): string {
  try {
    return new URL(href ?? "", location.origin).pathname;
  } catch {
    return "";
  }
}

const strip = (p: string) => (p || "/").replace(/\/+$/, "") || "/";
export const samePath = (a: string, b: string) => strip(pathOf(a)).toLowerCase() === strip(pathOf(b)).toLowerCase();

/** A product's id from its path (`/producto/57233-lenovo-…`, `/producto/57233`),
 *  or from a bare id. */
export function productId(path: string | number | null | undefined): number | null {
  const s = String(path ?? "").trim();
  const m = s.match(/\/producto\/(\d+)/) ?? s.match(/^(\d+)(?:-|$)/);
  return m ? Number(m[1]) : null;
}

/** A product's canonical path, `/producto/<id>`: the brain and the page agree
 *  on it whatever slug or query a link carried. */
export const productPath = (id: number) => `/producto/${id}`;

// ─── No further than Tipo de entrega ──────────────────────────────────────

/**
 * The guest's way to the checkout: the cart (/carro) "Continuar"
 * (`a[aria-label="ir al checkout"]`, a full load to /checkout), then on
 * /checkout's first step, "Inicio de sesión", the right-hand card's
 * "Continuar como invitado" (→ /checkout/tipo-entrega). On Tipo de entrega
 * the visitor chooses store pickup or delivery; the address, RUT and contact
 * fields come after that choice, and step 3 is "Pago".
 *
 * Javier goes that far and no further. Allowed, by structure: the cart's
 * "Continuar" on /carro, and the guest button on /checkout's first step.
 * Refused wherever they are: every login control ("Hola, ingresa", "Inicia
 * sesión", "Crear nueva cuenta", "Regístrate", any password), the delivery
 * radios and stores of Tipo de entrega, and anything else on /checkout.
 * Words are checked as well, as a second net, because Chrome's translator
 * rewrites them.
 */
const NEVER = [
  "#login-dropdown",
  ".login-dropdown",
  "input[type=password]",
  "input[name=method]",
  "input[name=store]",
  "#withdraw",
  "#dispatch",
  ".identification .left",
  "[href*='/auth/realms/']",
  "[href*='/login']",
  "[href*='openid-connect']",
].join(", ");

/** What only the visitor types: a RUT (or RUN), a password, a card and its
 *  code or date, an address, a name, a phone, an email. Matched on a field's
 *  name, id, autocomplete, placeholder and label. */
const PRIVATE_FIELD =
  /\b(?:rut|run)\b|password|contrase|tarjeta|\bcard\b|\bcvv\b|\bcvc\b|vencimiento|direcci|address|\bcalle\b|n[uú]mero|depto|tel[eé]fono|phone|celular|e-?mail|correo|nombre|apellido|raz[oó]n social|\bgiro\b/i;

/** The only fields Javier types in: the header's search box and the cart's
 *  coupon box. */
const TYPEABLE = "#search-input-desktop, #search-input-mobile, input.cupon-input";

/** Why `el`, a form field, is the visitor's alone to type in, or null. */
export function privateField(el: Element): string | null {
  if (el instanceof HTMLInputElement && el.type === "password") return "it is a password field";
  if (el.matches(TYPEABLE)) return null;
  const id = el.id;
  const label = clean(id ? document.querySelector(`label[for="${CSS.escape(id)}"]`)?.textContent : el.closest("label")?.textContent);
  const words = [el.getAttribute("name"), id, el.getAttribute("autocomplete"), el.getAttribute("placeholder"), el.getAttribute("aria-label"), label]
    .filter(Boolean)
    .join(" ");
  if (PRIVATE_FIELD.test(words)) return `its field is the visitor's to type ("${label || el.getAttribute("placeholder") || el.getAttribute("name") || id}")`;
  return `Javier types only in the search box and the coupon box, not in "${label || el.getAttribute("placeholder") || id || el.tagName.toLowerCase()}"`;
}

const norm2 = (p: string) => p.toLowerCase().replace(/\/+$/, "") || "/";

/** The two checkout pages Javier may be on: the first step and Tipo de entrega. */
export function checkoutStep(path: string): "login" | "delivery" | null {
  const p = norm2(path);
  if (p === "/checkout") return "login";
  if (p === "/checkout/tipo-entrega") return "delivery";
  return null;
}

/** A path Javier never loads: the checkout past Tipo de entrega, the login,
 *  account and registration pages, a payment. */
export function forbiddenPath(path: string): boolean {
  const p = norm2(path);
  if (checkoutStep(p)) return false;
  if (p.startsWith("/checkout/")) return true;
  return /^\/(login|auth|realms|mi-cuenta|mis-compras|cuenta|registro|pago|webpay|transbank)(\/|$)/.test(p);
}

/** The steps Javier may press on the way to Tipo de entrega. */
function guestStep(el: Element): boolean {
  const here = norm2(location.pathname);
  if (here === "/carro") return Boolean(el.closest("aside.purchase-summary a[aria-label='ir al checkout']"));
  if (here === "/checkout") {
    const button = el.closest<HTMLElement>(".identification .right .identification__card > button");
    return Boolean(button && /invitad|guest/i.test(clean(button.textContent)));
  }
  return false;
}

const CHECKOUT_WORDS =
  /ir a pagar|\bpagar\b|webpay|finalizar compra|inicia(r)? sesi[oó]n|ingresa\b|crear (nueva )?cuenta|reg[ií]strate|mi cuenta|log ?in|sign (in|up)|create account|\bpay\b|place order/i;

/**
 * What a visitor does for themselves on the rest of the store, never Javier:
 * "Usar mi ubicación actual" on /tiendas (the device's location), the order
 * tracking form on /estado-despacho (a RUT and a boleta), the coupon cards'
 * "Copiar código" (the clipboard), the newsletter and the business quote
 * forms, and the human advisor's button.
 */
const OFF_LIMITS = [
  "#rut-purchase",
  "#folio-purchase",
  ".ticket-cupon-boton",
  "#pcfAssistanceWrapper",
  "form[action*='suscribe'] button",
  "form[action*='contacto-b2b'] button",
].join(", ");
const OFF_LIMITS_WORDS = /usar mi ubicaci[oó]n|copiar c[oó]digo|suscr[ií]b|cotiza con nosotros|^buscar$/i;

/** Why `el` is the visitor's own to press elsewhere on the store, or null. */
export function offLimits(el: Element): string | null {
  const hit = el.closest(OFF_LIMITS);
  if (hit) return `it is the visitor's own to press (${hit.id ? `#${hit.id}` : hit.className || hit.tagName.toLowerCase()})`;
  const words = clean(`${el.textContent ?? ""} ${el.getAttribute("aria-label") ?? ""}`);
  if (words.length < 40 && OFF_LIMITS_WORDS.test(words)) {
    // "Buscar" is off-limits only on the order tracking form; the header's search button is Javier's.
    if (/^buscar$/i.test(words) && norm2(location.pathname) !== "/estado-despacho") return null;
    return `it is the visitor's own to press ("${words}")`;
  }
  if (norm2(location.pathname) === "/estado-despacho" && el.closest("form")) return "the order tracking form is the visitor's (their RUT and boleta)";
  return null;
}

/** Why `el` must not be pressed, or null. */
export function intoCheckout(el: Element): string | null {
  const off = offLimits(el);
  if (off) return off;
  const never = el.closest(NEVER);
  if (never) return `it is a login control or the delivery choice (${never.id ? `#${never.id}` : never.className || never.tagName.toLowerCase()}), which are the visitor's`;
  if (el.matches("input:not([type=checkbox]), select, textarea")) {
    const why = privateField(el);
    if (why) return why;
  }
  if (guestStep(el)) return null;
  const here = norm2(location.pathname);
  if (here === "/checkout" || here.startsWith("/checkout/")) return `it is on the checkout (${here}), where Javier presses only "Continuar como invitado"`;
  const link = el.closest<HTMLAnchorElement>("a[href]");
  if (link) {
    const href = link.getAttribute("href") ?? "";
    if (href && !href.startsWith("#") && !href.startsWith("javascript:")) {
      const to = new URL(href, location.href);
      if (to.host.replace(/^www\./, "") !== "pcfactory.cl") return `it links off the store (${to.host})`;
      if (forbiddenPath(to.pathname) || checkoutStep(to.pathname)) return `it links to ${to.pathname}`;
    }
  }
  if (el.closest("a[aria-label='ir al checkout']")) return "it is the cart's Continuar, pressed only from the cart page";
  // A question's toggle in an FAQ may well say "pagar"; it opens an answer.
  if (el.closest("[data-toggle=collapse], [data-bs-toggle=collapse], [data-toggle=tab]")) return null;
  const words = clean(`${el.textContent ?? ""} ${el.getAttribute("title") ?? ""} ${el.getAttribute("aria-label") ?? ""}`);
  if (words.length < 40 && CHECKOUT_WORDS.test(words)) return `it says "${words}"`;
  return null;
}

/** Click `el` as a visitor would, unless it leads past Tipo de entrega, into a
 *  login or a payment: then refuse, and nothing is pressed. Every click the
 *  adapter makes goes through here. */
export function press(el: Element): void {
  const why = intoCheckout(el);
  if (why) throw new Error(`refused to press it: ${why}. Javier goes no further than Tipo de entrega; the login, the RUT, the address and the payment are the visitor's`);
  (el as HTMLElement).click();
}

/** Where `path` loads on this site, unless it is past Tipo de entrega, an
 *  account or login page, a payment or another host: then refuse. Every load
 *  a move makes is checked here first. */
export function target(path: string): string {
  const to = new URL(path, location.origin);
  if (to.host.replace(/^www\./, "") !== "pcfactory.cl") {
    throw new Error(`${to.href} is not on www.pcfactory.cl; only the store's own pages open here`);
  }
  if (forbiddenPath(to.pathname)) throw new Error(`refused to open ${to.pathname}: Javier never opens a login, an account page or the checkout past Tipo de entrega`);
  return to.origin + to.pathname + to.search + to.hash;
}

/** Load another page of this site in this tab, unless `target` refuses it. */
export function go(path: string): void {
  location.assign(target(path));
}

// ─── Scrolling ────────────────────────────────────────────────────────────

/** Room kept at the top for the main menu bar, which pins itself there (86
 *  px) the moment the window scrolls up: a target is never placed under it. */
export const HEADER_OFFSET = 100;

/** What sits over the bottom of the screen: the comparator's bar. */
function bottomBars(): number {
  const bar = document.querySelector<HTMLElement>("#pcf-comparator-summary.show");
  if (!bar || !visible(bar)) return 0;
  const r = bar.getBoundingClientRect();
  return r.top < window.innerHeight ? window.innerHeight - r.top : 0;
}

/** The height of what is pinned to the top now (the main menu bar on a
 *  scroll up), never less than the room it takes when it comes back. */
export function headerHeight(): number {
  const bar = document.querySelector<HTMLElement>("#main-menu");
  const r = bar?.getBoundingClientRect();
  const pinned = bar && r && getComputedStyle(bar).position === "fixed" && r.top >= -2 && r.height > 0 ? r.bottom : 0;
  return Math.max(HEADER_OFFSET, pinned + 8);
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
 *  comparator leave (`center`, the default), or just under the header when
 *  it is taller than that, measuring again as late images move the page. */
export async function scrollTo(el: Element, align: "top" | "center" = "center"): Promise<void> {
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

/** A list that scrolls inside the page (the store list on /tiendas, a
 *  window's body) brought round to `el` first: the window alone cannot. */
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

export function styleThePage(): void {
  if (document.querySelector("style[data-voqalize=pcfactory]")) return;
  const style = document.createElement("style");
  style.setAttribute("data-voqalize", "pcfactory");
  style.textContent = `
    /* In a call, pcFactory's own assistance button (its chat and video
       advisers, bottom-right) would be a second voice on the page: hidden
       while Javier is on. */
    html[data-voqalize-call] #pcfAssistanceWrapper,
    html[data-voqalize-call] #ocular-widget-container,
    html[data-voqalize-call] #ocular-widget-toggler,
    html[data-voqalize-call] #ocular-widget-popup,
    html[data-voqalize-call] #pcfChatContainer { display: none !important; }
  `;
  (document.head ?? document.documentElement).appendChild(style);
}

// ─── Waiting for a page ───────────────────────────────────────────────────

/**
 * The page has settled: parsed, its fonts in (or 1.5 s), and the DOM quiet
 * for a moment. Never the `load` event, which the trackers hold back.
 */
export async function settled(): Promise<void> {
  if (document.readyState === "loading") {
    await new Promise<void>((r) => document.addEventListener("DOMContentLoaded", () => r(), { once: true }));
  }
  await Promise.race([document.fonts?.ready, sleep(1500)]);
  await quiet(document.body, 400, 2500);
}

// ─── The store's API calls, watched ───────────────────────────────────────

/**
 * The Vue widgets fetch from `api.pcfactory.cl` with XMLHttpRequest: a
 * filter, a sort, an add or a coupon is done once its calls are back. Each
 * call is counted while it runs, and the last one's end is kept, so a move can
 * wait for the site's own answer rather than for a guessed delay.
 */
let inFlight = 0;
let lastDone = 0;
let watchingXhr = false;

export function watchApi(): void {
  if (watchingXhr || typeof XMLHttpRequest === "undefined") return;
  watchingXhr = true;
  const open = XMLHttpRequest.prototype.open;
  const send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (this: XMLHttpRequest & { __pcf?: boolean }, method: string, url: string | URL, ...rest: unknown[]) {
    this.__pcf = /api\.pcfactory\.cl/.test(String(url));
    return (open as (...a: unknown[]) => void).call(this, method, url, ...rest);
  } as typeof XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.send = function (this: XMLHttpRequest & { __pcf?: boolean }, body?: Document | XMLHttpRequestBodyInit | null) {
    if (this.__pcf) {
      inFlight++;
      this.addEventListener("loadend", () => {
        inFlight = Math.max(0, inFlight - 1);
        lastDone = Date.now();
      }, { once: true });
    }
    return send.call(this, body);
  };
}

/** No call of the site's to its API is running, and none ended in the last
 *  `idleMs`: what the page shows is its answer, not a moment of a redraw. */
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

function nativeSet(el: HTMLInputElement, value: string): void {
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(el, value);
}

/** Type `text` into the search box or the coupon box, one character at a
 *  time at a visitor's pace, with the key and `input` events each one sends
 *  (Vue's `v-model` listens to `input`). No Enter: the move presses the
 *  site's own button. Any other field is refused (`privateField`). */
export async function typeInto(el: HTMLInputElement, text: string, perKeyMs = 95): Promise<void> {
  if (!el.matches(TYPEABLE)) throw new Error(`refused to type: ${privateField(el) ?? "not the search or coupon box"}`);
  el.focus({ preventScroll: true });
  nativeSet(el, "");
  el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "deleteContentBackward" }));
  let value = "";
  for (const ch of text) {
    value += ch;
    el.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: ch }));
    nativeSet(el, value);
    el.dispatchEvent(new InputEvent("input", { bubbles: true, data: ch, inputType: "insertText" }));
    el.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true, key: ch }));
    await sleep(perKeyMs + (ch === " " ? 60 : 0));
  }
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

/** Set a range input's value as a drag leaves it: `input` (Vue's v-model),
 *  `change`, then the `mouseup` the listing's price filter applies on. */
export function setRange(el: HTMLInputElement, value: number): void {
  nativeSet(el, String(value));
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  el.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
}
