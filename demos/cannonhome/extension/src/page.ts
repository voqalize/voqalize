/**
 * What the adapter does to a page it does not own: wait for it, find words on
 * it, scroll the window under the fixed bars, type the way a visitor types,
 * and refuse anything that leads into checkout. The ring is Stage's spotlight
 * (`site.ts` has its look); the waiting and field helpers are Stage's too.
 *
 * cannonhome.cl is Magento 2 (Luma-derived theme, RequireJS, jQuery,
 * Knockout). Every move between pages is a full page load; listing filters,
 * sort and paging, and add-to-cart, are AJAX. Third-party trackers hold the
 * `load` event back for more than 15 s, so nothing here waits for it: a page
 * is ready once it is parsed, the selectors a move needs are there, and the DOM
 * has been quiet for a moment.
 */

import { clean, quiet, setValue, sleep, visible, waitFor as waitUntil } from "@voqalize/stage";

export { clean, quiet, setValue, sleep, visible };

export const WAIT_MS = 8000;

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

/** A CLP amount as the site writes it ("$55.993", "Te faltan $120.010 …"):
 *  the digits of the first amount, or null. Dots group thousands; there are no
 *  decimals. Chrome's translator leaves the figures alone. */
export function money(text: string | null | undefined): number | null {
  // Pesos have no cents, so a dot, a comma or a thin space only groups the
  // thousands: the store writes "$55.993", and a page the browser has
  // translated to English shows "$55,993" (a live call, 2026-10-23, read "55").
  const m = (text ?? "").match(/\$\s*(\d[\d.,  ]*)/) ?? (text ?? "").match(/(\d[\d.,  ]*)/);
  if (!m) return null;
  const n = Number(m[1].replace(/[.,  ]/g, ""));
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

// ─── As far as the delivery form, never past it ───────────────────────────

/**
 * The checkout is one page, /checkout (`body.checkout-index-index`): the
 * contact email, the delivery form (`#co-shipping-form`: región, comuna,
 * address, name, RUT, phone), the delivery method, then "Método de Pago"
 * (`#payment`) and the sticky "Completa los pasos" / place-order button
 * (`.co-place-order`). The guest gets there from the bag: "Terminar pedido"
 * opens a login window whose "Comprar como invitado" is a plain link to
 * /checkout.
 *
 * Javier goes that far and no further. Allowed, by structure: the bag page's
 * "Terminar pedido", the login window's guest link (and nothing else in that
 * window), and on /checkout the delivery form's región and comuna pickers and
 * its phone prefix. Everything else on /checkout is refused, and these are
 * refused wherever they are, before anything is allowed: the payment step,
 * the place-order bar, "Continuar compra", the delivery method (the visitor
 * chooses it; a store pickup asks for a RUT), the coupon and gift-card
 * boxes, every login control and password field. Words are checked as well,
 * as a second net, because Chrome's translator rewrites them.
 */
const PAST_THE_FORM = [
  "#payment",
  "#checkout-step-payment",
  "#co-payment-form",
  ".checkout-payment-method",
  ".payment-method",
  ".payment-methods",
  ".co-place-order",
  ".co-place-order__button",
  "[data-role='opc-continue']",
  ".address-confirm-buttons-container",
  ".checkout-agreements",
  "#opc-shipping_method",
  ".split-shipping-container",
  ".wrapper-who-receive",
  "#discount-form",
  "#giftcard-form",
  ".giftcard",
  ".block-customer-login",
  "#login-form-modal",
  "a.action.remind",
  "button.action.login",
  ".btn-social",
  ".btn-google",
  "input[type=password]",
  ".password-view-trigger",
].join(", ");

/** What the visitor alone types: a RUT (or RUN), a password, a card and its
 *  code or date, a company's invoice details, a gift card. Matched on a
 *  field's name, id, autocomplete, placeholder and label. */
const PRIVATE_FIELD = /\b(?:rut|run)\b|password|contrase|tarjeta|\bcard\b|\bcvv\b|\bcvc\b|\bcc-|vencimiento|expira|raz[oó]n social|\bgiro\b|gift ?card|giftcard/i;

/** Why `el`, a form field, is the visitor's alone to type in, or null. */
export function privateField(el: Element): string | null {
  if (el instanceof HTMLInputElement && el.type === "password") return "it is a password field";
  if (el.closest(PAST_THE_FORM)) return "it is past the delivery form (the payment, the delivery method or a login)";
  const field = el.closest(".field");
  const id = el.id;
  const label = clean(field?.querySelector("label")?.textContent ?? (id ? document.querySelector(`label[for="${CSS.escape(id)}"]`)?.textContent : ""));
  // Some of the site's fields carry a function's source as `autocomplete`.
  const auto = el.getAttribute("autocomplete") ?? "";
  const words = [el.getAttribute("name"), id, /function/.test(auto) ? "" : auto, el.getAttribute("placeholder"), label, field?.getAttribute("name")]
    .filter(Boolean)
    .join(" ");
  if (PRIVATE_FIELD.test(words)) return `its field is the visitor's to type ("${label || el.getAttribute("name") || id}")`;
  return null;
}

/** A path on the checkout's one page, /checkout (and Magento's aliases). */
export function checkoutPage(path: string): boolean {
  const p = path.toLowerCase().replace(/^\/index\.php(?=\/|$)/, "").replace(/\/+$/, "") || "/";
  return p === "/checkout" || p === "/checkout/index" || p === "/checkout/index/index";
}

/** The steps Javier may press on the way to the delivery form, and on it. */
function guestStep(el: Element): boolean {
  const body = document.body?.classList;
  if (el.closest("[data-role='proceed-to-checkout']") && body?.contains("checkout-cart-index")) return true;
  const guest = el.closest<HTMLAnchorElement>("aside.login-modal a[href]");
  if (guest) {
    const to = new URL(guest.getAttribute("href") ?? "", location.href);
    const words = clean(guest.textContent);
    return to.origin === location.origin && checkoutPage(to.pathname) && !to.hash && !/sesi[oó]n|log ?in|sign|google|crear|cuenta|account/i.test(words);
  }
  if (body?.contains("checkout-index-index")) {
    return Boolean(
      el.closest(
        "#co-shipping-form .field.region_id .cn-region-search, #co-shipping-form .field.city_id .cn-region-search, #co-shipping-form .field.telephone .flag-container",
      ),
    );
  }
  return false;
}

/**
 * Everything else that leads into checkout, a login or a payment, by
 * structure: the minicart's "Finalizar compra" (`#top-cart-btn-checkout`, the
 * drawer's primary button), any `.action.checkout`, the login modal, every
 * control on /checkout, and the account pages.
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
const CHECKOUT_WORDS =
  /finalizar compra|terminar pedido|ir a pagar|\bpagar\b|pagar ahora|realizar pedido|completa los pasos|continuar compra|comprar como invitado|crear cuenta|webpay|proceed to checkout|go to checkout|place order|pay now|\bcheckout\b|iniciar sesi[oó]n|\blog ?in\b|sign in|google/i;

/** A path Javier never loads: past the delivery form (the payment, the
 *  order's success page, any /checkout/… but the bag), the account and login
 *  pages, payment returns. The bag (/checkout/cart/, and adding to it) and the
 *  checkout's one page (/checkout) are allowed. */
export function forbiddenPath(path: string): boolean {
  // Magento also routes every path under /index.php/ (/index.php/checkout/).
  const p = path.toLowerCase().replace(/^\/index\.php(?=\/|$)/, "").replace(/\/+$/, "") || "/";
  // The bag itself, and the add-to-bag form's own address.
  if (p === "/checkout/cart" || p === "/checkout/cart/index" || p.startsWith("/checkout/cart/add/")) return false;
  if (checkoutPage(p)) return false;
  if (p.startsWith("/checkout")) return true;
  return /^\/(onestepcheckout|customer\/account|sales\/order|webpay|mercadopago|paypal|braintree)(\/|$)/.test(p);
}

/** Why `el` must not be pressed, or null. */
export function intoCheckout(el: Element): string | null {
  const past = el.closest(PAST_THE_FORM);
  if (past) return `it is past the delivery form (${past.id ? `#${past.id}` : past.className || past.tagName.toLowerCase()}): a login, the delivery method or the payment, which are the visitor's`;
  if (el.matches("input, select, textarea")) {
    const why = privateField(el);
    if (why) return why;
  }
  if (guestStep(el)) return null;
  const hit = el.closest(CHECKOUT);
  if (hit) return `it is the checkout control (${hit.id ? `#${hit.id}` : hit.className || hit.tagName.toLowerCase()})`;
  const link = el.closest<HTMLAnchorElement>("a[href]");
  if (link) {
    const href = link.getAttribute("href") ?? "";
    if (href && !href.startsWith("#") && !href.startsWith("javascript:")) {
      const to = new URL(href, location.href);
      // A link to the checkout is pressed only as the login window's guest link.
      if (to.origin === location.origin && (forbiddenPath(to.pathname) || checkoutPage(to.pathname))) return `it links to ${to.pathname}`;
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
  if (why) throw new Error(`refused to press it: ${why}. Javier goes no further than the delivery form; the RUT, a login and the payment are the visitor's`);
  (el as HTMLElement).click();
}

/** Where `path` loads on this site, unless it is checkout past the delivery
 *  form, an account page or another host: then refuse. Every load a move
 *  makes is checked here first. */
export function target(path: string): string {
  const to = new URL(path, location.origin);
  if (to.host.replace(/^www\./, "") !== location.host.replace(/^www\./, "")) {
    throw new Error(`${to.href} is not on ${location.host}; only this site's own pages open here`);
  }
  if (forbiddenPath(to.pathname)) throw new Error(`refused to open ${to.pathname}: Javier never goes into checkout past the delivery form, or an account`);
  if (checkoutPage(to.pathname) && to.hash && !/^#shipping$/i.test(to.hash)) {
    throw new Error(`refused to open ${to.pathname}${to.hash}: Javier never goes into checkout past the delivery form`);
  }
  return to.origin + to.pathname + to.search + to.hash;
}

/** Load another page of this site in this tab, unless `target` refuses it. */
export function go(path: string): void {
  location.assign(target(path));
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
  if (document.querySelector("style[data-voqalize=cannonhome]")) return;
  const style = document.createElement("style");
  style.setAttribute("data-voqalize", "cannonhome");
  style.textContent = `
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
