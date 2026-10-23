/**
 * The site adapter: drive cannonhome.cl from the outside, with no help from
 * Cannon Home's developers.
 *
 * The brain sends a Voqalize `ui-command` ({command, payload}) and `run`
 * performs it on the page in front, one move at a time; the page reports back
 * through `start`, which calls `emit(event, payload)`:
 *
 *   - `page_changed` for every page the visitor lands on, whoever took them;
 *   - `product_shown` on a product page: read from the page at once, then
 *     confirmed by one `POST /graphql` (`source: "graphql"`), because the HTML
 *     is served from Fastly's cache and its price and stock can be hours old;
 *   - `listing_shown` on a category or search listing, and again after every
 *     AJAX grid update (filters, sort, paging), whoever made it;
 *   - `search_suggest` whenever the search box's dropdown shows products;
 *   - `prices_read` for `check_prices`;
 *   - `cart_state` after an add, when the bag opens, and when it changes;
 *   - `checkout_state` on the checkout's delivery form: which fields hold
 *     something (never what), which are missing, what the form flags;
 *   - `command_done` / `command_failed` for each move, which the brain waits on
 *     before he says it happened.
 *
 * The site, for a script like this: Magento 2.4 (Luma-derived theme
 * `Cannon/cannon`, RequireJS, jQuery, Knockout), Amasty Xsearch for the search
 * box, Amasty Shopby for the listing filters, a custom quick-filter bar
 * (`.qf__group`), fotorama for the gallery. Every product is a simple product:
 * each size and colour is its own page, so there is no option to pick on a
 * product page. Moving between pages is a full load, so a move to another page
 * leaves the rest of itself in `sessionStorage` (`page.ts leave()`) and the
 * adapter on the next page finishes it. Filters, sort and paging are AJAX with
 * `history.pushState`; add-to-cart is AJAX and slides the bag in by itself.
 *
 * Nothing here goes past the checkout's delivery form: every click goes
 * through `press`, every load through `go` (`page.ts`). They let Javier take a
 * guest from the bag to the form ("Terminar pedido", then "Comprar como
 * invitado") and pick the form's región and comuna, and refuse every login,
 * the delivery method, the payment step and the place-order button. Fields
 * are filled only through `fillField`, which refuses the RUT, any password and
 * anything of the payment, whatever the brain sends.
 */

import {
  amount, best, boxOf, clean, clearHighlight, go, headerHeight, highlight, inOrder, leave, type Leftover, money,
  norm, pathOf, press, privateField, quiet, samePath, scrollTo, scrollToTopOfPage, setValue, settled, shown, sleep,
  styleThePage, takeLeftover, typeInto, visible, waitFor,
} from "./page";

declare global {
  interface Window {
    voqalizeCannonhome?: Adapter;
  }
}

export interface Adapter {
  /** Perform one of the brain's page Actions. Never throws. */
  run(command: string, payload: unknown): Promise<RunResult>;
  /** What the visitor is looking at now, as a `page_changed` payload. */
  context(): PageContext;
  /** Report the page, the state on it, and a move left over from the last
   *  page, through `emit`, until the returned stop. */
  start(emit: (event: string, payload: unknown) => void): () => void;
  /** The Actions `run` performs. */
  readonly commands: readonly string[];
}

/** How a move went. `detail` says in English what is now on screen; `moved`
 *  means it went on to another page, which reports it done or failed from
 *  there. */
export interface RunResult {
  ok: boolean;
  error?: string;
  detail?: string;
  moved?: boolean;
}

/** The moves the brain waits on, whose success is reported as `command_done`. */
export const DONE_COMMANDS = new Set([
  "search_products", "filter_listing", "open_product", "check_prices", "add_to_cart", "show_cart",
  "start_checkout", "fill_checkout",
]);

export type Kind = "home" | "category" | "search" | "product" | "cart" | "checkout" | "page";

export interface PageContext {
  site: string;
  url: string;
  path: string;
  title: string;
  kind: Kind;
  /** Section headings a visitor can be taken to, in page order. */
  headings: string[];
  /** The FAQ questions on the page. */
  faqs: string[];
}

const MAX_HEADINGS = 80;
const MAX_FAQS = 120;
const MAX_LISTED = 30;
const MAX_SUGGESTED = 6;
const MAX_PRICED = 6;
const REPORT_DEBOUNCE_MS = 450;

// ─── Where we are ─────────────────────────────────────────────────────────

/** What sort of page this is, from Magento's own body classes (layout
 *  handles), which no translator touches. */
export function kindOf(): Kind {
  const b = document.body?.classList;
  if (!b) return "page";
  if (b.contains("catalog-product-view")) return "product";
  if (b.contains("catalog-category-view")) return "category";
  if (b.contains("catalogsearch-result-index")) return "search";
  if (b.contains("checkout-cart-index")) return "cart";
  if (b.contains("checkout-index-index")) return "checkout";
  if (b.contains("cms-index-index")) return "home";
  return "page";
}

/** The page's content: Magento's main column. */
const main = (): HTMLElement =>
  document.querySelector<HTMLElement>("#maincontent") ?? document.querySelector<HTMLElement>(".page-main") ?? document.body;

/** Not the page's content: the bars, menus and footer, the bag and other
 *  modals, GoPersonal's injected carousels, the WhatsApp button, the sticky
 *  add-to-cart bar, and our own. */
const CHROME = [
  "#topbarCannonBar", "header.page-header", ".nav-sections", "footer", ".page-footer",
  "aside.modal-popup", ".modals-wrapper", "[id^=gopersonal]", "#whatsapp-link", ".whatsapp-link-mobile",
  "#sticky-addtocart-bar", "#layered-filter-block", ".toolbar", ".qf-bar", ".breadcrumbs",
  "[data-voqalize]",
].join(", ");
const inChrome = (el: Element) => Boolean(el.closest(CHROME));

interface Faq {
  question: string;
  block: HTMLElement;
  toggle: HTMLElement | null;
  isOpen: () => boolean;
  answer: () => HTMLElement[];
}

/** The page's FAQs, the way the knowledge crawl reads them (so the names the
 *  brain has match): accordion titles that ask a question, and h2–h4 headings
 *  that ask one, with the blocks up to the next heading as the answer. */
function faqItems(): Faq[] {
  const root = main();
  const items: Faq[] = [];
  for (const t of root.querySelectorAll<HTMLElement>("[data-role=title], .accordion-title, details > summary")) {
    if (inChrome(t) || t.closest(".product.data.items")) continue;
    const question = clean(t.innerText || t.textContent);
    if (!/\?/.test(question)) continue;
    const content = t.nextElementSibling as HTMLElement | null;
    const details = t.closest("details");
    items.push({
      question,
      block: (details as HTMLElement | null) ?? t,
      toggle: t,
      isOpen: () => (details ? details.open : Boolean(content && shown(content))),
      answer: () => (content ? [content] : []),
    });
  }
  const known = new Set(items.map((i) => norm(i.question)));
  for (const h of root.querySelectorAll<HTMLElement>("h2, h3, h4")) {
    if (inChrome(h)) continue;
    const text = clean(h.innerText || h.textContent).replace(/^\d+[.)]\s*/, "");
    if (!(/\?\s*$/.test(text) || /^¿/.test(text)) || known.has(norm(text))) continue;
    items.push({ question: text, block: h, toggle: null, isOpen: () => true, answer: () => answerAfter(h) });
  }
  return items.sort((a, b) => inOrder(a.block, b.block));
}

/** The blocks after heading `h` up to the next heading. */
function answerAfter(h: HTMLElement): HTMLElement[] {
  const out: HTMLElement[] = [];
  for (let el = h.nextElementSibling; el && !el.matches("h1, h2, h3, h4") && out.length < 8; el = el.nextElementSibling) {
    if (el instanceof HTMLElement && shown(el)) out.push(el);
  }
  return out;
}

interface Head {
  el: HTMLElement;
  text: string;
}

function headings(): Head[] {
  const found: Head[] = [];
  for (const h of main().querySelectorAll<HTMLElement>("h1, h2, h3, h4")) {
    if (inChrome(h) || !shown(h)) continue;
    const text = clean(h.innerText || h.textContent);
    if (text.length <= 1 || /:\s*$/.test(text)) continue;
    found.push({ el: h, text });
  }
  found.sort((a, b) => inOrder(a.el, b.el));
  const seen = new Set<string>();
  return found.filter((h) => !seen.has(norm(h.text)) && seen.add(norm(h.text)));
}

function context(): PageContext {
  return {
    site: "site",
    url: location.href,
    path: location.pathname,
    title: document.title,
    kind: kindOf(),
    headings: headings()
      .map((h) => h.text)
      .slice(0, MAX_HEADINGS),
    faqs: faqItems()
      .map((f) => f.question)
      .slice(0, MAX_FAQS),
  };
}

// ─── Reporting ────────────────────────────────────────────────────────────

let emitter: ((event: string, payload: unknown) => void) | null = null;
/** Outcomes that happened before anyone listened (a move left from the last
 *  page, finished before the call rejoined on this one). */
const backlog: [string, unknown][] = [];
/** The latest of each state report on this page, and what each listener was
 *  last sent, so a report is sent once and a late listener gets the latest. */
const latest = new Map<string, unknown>();
const sent = new WeakMap<object, Map<string, string>>();

function emit(event: string, payload: unknown): void {
  if (emitter) emitter(event, payload);
  else backlog.push([event, payload]);
}

/** A state report (product, listing, suggestions, bag): sent unless this
 *  listener already has exactly it. */
function report(event: string, payload: unknown): void {
  latest.set(event, payload);
  if (!emitter) return;
  const key = JSON.stringify(payload);
  let mine = sent.get(emitter);
  if (!mine) sent.set(emitter, (mine = new Map()));
  if (mine.get(event) === key) return;
  mine.set(event, key);
  emitter(event, payload);
}

// ─── The product page ─────────────────────────────────────────────────────

interface ProductShown {
  path: string;
  sku: string;
  name: string;
  price: number | null;
  regular_price: number | null;
  in_stock: boolean | null;
  qty: number | null;
  specs: Record<string, string>;
  rating: number | null;
  reviews: number | null;
  source: "page" | "graphql";
}

/** The page's JSON-LD `Product`, server-rendered. */
function ldProduct(): Record<string, unknown> | null {
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const data = JSON.parse(s.textContent ?? "") as unknown;
      for (const node of Array.isArray(data) ? data : [data]) {
        if (node && typeof node === "object" && (node as Record<string, unknown>)["@type"] === "Product") {
          return node as Record<string, unknown>;
        }
      }
    } catch {
      // Not JSON; the next block.
    }
  }
  return null;
}

const productForm = () => document.querySelector<HTMLFormElement>("form#product_addtocart_form");

/** The right column of the product page (the one holding the form; the
 *  theme renders a second, for phones, holding only the title). */
function productInfo(): HTMLElement | null {
  return productForm()?.closest<HTMLElement>(".product-info-main") ?? document.querySelector<HTMLElement>(".product-info-main");
}

/** Final and struck prices in a price box; the struck one only when it is
 *  higher (a product on no sale shows no old price). */
function pricesIn(box: Element | null): { price: number | null; regular_price: number | null } {
  const price = amount(box?.querySelector("[data-price-type=finalPrice]"));
  const old = amount(box?.querySelector("[data-price-type=oldPrice]"));
  return { price, regular_price: old != null && price != null && old > price ? old : null };
}

/** The specifications table: label → value, the labels as the site writes
 *  them. A label listed twice (the site lists Color twice on some sheets)
 *  keeps both values. */
function specs(): Record<string, string> {
  const out: Record<string, string> = {};
  for (const row of document.querySelectorAll("#product-attribute-specs-table tr")) {
    const label = clean(row.querySelector("th")?.textContent);
    const value = clean(row.querySelector("td")?.textContent);
    if (!label || !value) continue;
    if (!out[label]) out[label] = value;
    else if (!out[label].split(" / ").includes(value)) out[label] = `${out[label]} / ${value}`;
  }
  return out;
}

function readProduct(): ProductShown | null {
  const form = productForm();
  if (kindOf() !== "product" || !form) return null;
  const info = productInfo();
  const ld = ldProduct();
  const { price, regular_price } = pricesIn(info?.querySelector(".product-info-price") ?? info);
  const stockEl = form.querySelector(".stock");
  const offers = (ld?.offers as Record<string, unknown>[] | undefined)?.[0];
  const in_stock = stockEl?.classList.contains("available")
    ? true
    : stockEl?.classList.contains("unavailable")
      ? false
      : typeof offers?.availability === "string"
        ? /InStock/i.test(offers.availability)
        : null;
  const qtyRaw = document.querySelector<HTMLInputElement>("input#stock")?.value;
  const qty = qtyRaw != null && qtyRaw !== "" && Number.isFinite(Number(qtyRaw)) ? Math.round(Number(qtyRaw)) : null;
  // verificado.ai's widget: "Score 4,7 de 5" and "(4,7) 17 opiniones"; the
  // JSON-LD rating is the platform's own and can differ.
  const widget = info?.querySelector(".verificadoai-product-rating");
  const scoreText = widget?.querySelector("[aria-label]")?.getAttribute("aria-label") ?? widget?.textContent ?? "";
  const score = scoreText.match(/(\d+[.,]\d+|\d+)/);
  const count = (widget?.textContent ?? "").match(/\)\s*(\d+)/);
  const agg = ld?.aggregateRating as Record<string, unknown> | undefined;
  return {
    path: location.pathname,
    sku: form.dataset.productSku || clean(info?.querySelector(".product-sku")?.textContent) || String(ld?.sku ?? ""),
    name: form.dataset.productName || clean(info?.querySelector("h1.product-name")?.textContent) || String(ld?.name ?? ""),
    price: price ?? (typeof offers?.price === "number" ? offers.price : null),
    regular_price,
    in_stock,
    qty: in_stock === false ? 0 : qty,
    specs: specs(),
    rating: score ? Number(score[1].replace(",", ".")) : typeof agg?.ratingValue === "number" ? agg.ratingValue : null,
    reviews: count ? Number(count[1]) : typeof agg?.reviewCount === "number" ? agg.reviewCount : null,
    source: "page",
  };
}

// ─── GraphQL, same origin, POST only (GET is refused at the edge) ─────────

const PRODUCT_FIELDS =
  "sku name url_key stock_status price_range { minimum_price { regular_price { value } final_price { value } } }";

interface GqlProduct {
  sku?: string;
  name?: string;
  url_key?: string;
  stock_status?: string;
  price_range?: { minimum_price?: { regular_price?: { value?: number }; final_price?: { value?: number } } };
}

async function gql<T>(query: string, variables: Record<string, unknown>): Promise<T> {
  const res = await fetch("/graphql", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ query, variables }),
  });
  if (!res.ok) throw new Error(`the shop's catalogue answered ${res.status}`);
  const body = (await res.json()) as { data?: T; errors?: { message?: string }[] };
  if (!body.data) throw new Error(`the shop's catalogue refused the read: ${body.errors?.[0]?.message ?? "no data"}`);
  return body.data;
}

const keyOf = (path: string) => pathOf(path).replace(/^\/+/, "").replace(/\.html$/i, "");
const productPath = (path: string) => {
  const p = pathOf(path.trim());
  return p.endsWith(".html") ? p : `${p.replace(/\/+$/, "")}.html`;
};

function priced(p: GqlProduct) {
  const final = p.price_range?.minimum_price?.final_price?.value ?? null;
  const regular = p.price_range?.minimum_price?.regular_price?.value ?? null;
  return {
    price: final != null ? Math.round(final) : null,
    regular_price: regular != null && final != null && regular > final ? Math.round(regular) : null,
    in_stock: p.stock_status ? p.stock_status === "IN_STOCK" : null,
  };
}

/** `route(url:)` for each path: it answers out-of-stock products too, which
 *  `products(...)` hides (the shop does not display them). */
async function routes(paths: string[]): Promise<Map<string, GqlProduct>> {
  const out = new Map<string, GqlProduct>();
  if (!paths.length) return out;
  const vars: Record<string, string> = {};
  const decl = paths.map((_, i) => `$u${i}: String!`).join(", ");
  const body = paths
    .map((p, i) => {
      vars[`u${i}`] = `${keyOf(p)}.html`;
      return `r${i}: route(url: $u${i}) { ... on ProductInterface { ${PRODUCT_FIELDS} } }`;
    })
    .join(" ");
  const data = await gql<Record<string, GqlProduct | null>>(`query (${decl}) { ${body} }`, vars);
  paths.forEach((p, i) => {
    const hit = data[`r${i}`];
    if (hit && hit.sku) out.set(keyOf(p), hit);
  });
  return out;
}

/** Confirm the product page's price and stock live, once per page. */
let confirming: Promise<void> | null = null;
function confirmProduct(): Promise<void> {
  if (confirming) return confirming;
  confirming = (async () => {
    const page = readProduct();
    if (!page) return;
    try {
      const hit = (await routes([page.path])).get(keyOf(page.path));
      if (!hit) return;
      const live = priced(hit);
      report("product_shown", {
        ...page,
        sku: hit.sku || page.sku,
        name: hit.name || page.name,
        ...live,
        // GraphQL has no quantity; the page's is kept while the two agree.
        qty: live.in_stock === false ? 0 : live.in_stock === page.in_stock ? page.qty : null,
        source: "graphql",
      } satisfies ProductShown);
    } catch (error) {
      console.info("voqalize: the live price read failed; the page's stands", error);
    }
  })();
  return confirming;
}

// ─── Listings ─────────────────────────────────────────────────────────────

interface ListingItem {
  name: string;
  path: string;
  price: number | null;
  regular_price: number | null;
}

/** The listing's product grid (Amasty swaps its content on every filter). */
const productList = () =>
  document.querySelector<HTMLElement>("#amasty-shopby-product-list") ??
  document.querySelector<HTMLElement>(".column.main") ??
  main();

function cards(): HTMLElement[] {
  return [...productList().querySelectorAll<HTMLElement>("ol.products li.product-item, .products-grid li.product-item")].filter(
    (li) => !li.closest("[id^=gopersonal]"),
  );
}

/** The quick-filter groups: request variable → the labels active in it. */
function activeFilters(): Record<string, string> {
  const out: Record<string, string> = {};
  for (const g of document.querySelectorAll<HTMLElement>(".qf__group[data-qf-request-var]")) {
    const labels = [...g.querySelectorAll<HTMLElement>(".qf__option-link.-active")].map(
      (a) => a.getAttribute("title") || clean(a.querySelector(".qf__option-label")?.textContent),
    );
    if (labels.length) out[g.dataset.qfRequestVar!] = labels.join(", ");
  }
  // Search pages have no quick filters: the drawer's "now shopping by" list.
  for (const item of document.querySelectorAll(".filter-current .item")) {
    const label = clean(item.querySelector(".filter-label")?.textContent);
    const value = clean(item.querySelector(".filter-value")?.textContent);
    if (label && value && !Object.values(out).includes(value)) out[norm(label)] = value;
  }
  return out;
}

function listingCount(): number | null {
  const amountEl = document.querySelector(".toolbar-products-plp .toolbar-amount, .toolbar-amount");
  const numbers = [...(amountEl?.querySelectorAll(".toolbar-number") ?? [])];
  const last = numbers[numbers.length - 1];
  if (last) return money(last.textContent);
  return money(amountEl?.textContent);
}

function readListing() {
  const items: ListingItem[] = cards()
    .slice(0, MAX_LISTED)
    .map((li) => {
      const a = li.querySelector<HTMLAnchorElement>("a.product-item-link");
      return { name: clean(a?.textContent), path: pathOf(a?.href), ...pricesIn(li.querySelector(".price-box")) };
    })
    .filter((i) => i.name && i.path);
  return {
    path: location.pathname,
    title: clean(document.querySelector("h1.page-title, #page-title-heading")?.textContent) || document.title,
    count: listingCount(),
    filters: activeFilters(),
    sort: document.querySelector<HTMLSelectElement>("select#sorter")?.value || undefined,
    items,
  };
}

const isListing = () => kindOf() === "category" || kindOf() === "search";

/** A fingerprint of the grid, to tell when an AJAX update has landed. */
const gridKey = () => {
  const l = readListing();
  // Not the sorter's value: setValue changes it at once, before the grid lands.
  return JSON.stringify([location.pathname + location.search, l.count, l.items.slice(0, 4).map((i) => i.path)]);
};

// ─── The search box ───────────────────────────────────────────────────────

function searchInput(): HTMLInputElement | null {
  const all = [...document.querySelectorAll<HTMLInputElement>("input.amsearch-input")];
  return all.find(shown) ?? null;
}

/** goPersonal's autocomplete (`#gp-ac-dropdown`, under <body>) replaces
 *  Amasty's on the live site: its stylesheet hides `.amsearch-result-section`
 *  with `display: none !important`. Amasty's stays the fallback. */
const gpDropdown = () => document.querySelector<HTMLElement>("#gp-ac-dropdown");
const SUGGEST_CARDS = "a.gp-ac-product-card, .amsearch-products-section li.amsearch-item";
const resultSection = (): HTMLElement | null => {
  const gp = gpDropdown();
  if (gp?.classList.contains("open") && shown(gp)) return gp;
  return document.querySelector<HTMLElement>(".amsearch-result-section");
};

function readSuggest() {
  const section = resultSection();
  const items = [...(section?.querySelectorAll<HTMLElement>(SUGGEST_CARDS) ?? [])]
    .slice(0, MAX_SUGGESTED)
    .map((li) => {
      if (li.matches("a.gp-ac-product-card")) {
        return {
          name: clean(li.querySelector(".gp-ac-product-name")?.textContent || li.querySelector("img")?.getAttribute("alt")),
          path: pathOf((li as HTMLAnchorElement).href),
          price: money(li.querySelector(".gp-ac-price-final, .gp-ac-price-only")?.textContent),
        };
      }
      const a = li.querySelector<HTMLAnchorElement>("a.product-item-link") ?? li.querySelector<HTMLAnchorElement>("a.amsearch-link");
      return {
        name: clean(a?.getAttribute("title") || a?.textContent),
        path: pathOf(a?.href || li.dataset.clickUrl),
        price: amount(li.querySelector("[data-price-type=finalPrice]")),
      };
    })
    .filter((i) => i.name && i.path);
  const categories = [
    ...(section?.querySelectorAll<HTMLAnchorElement>("a.gp-ac-cat-pill, .amsearch-categories-section a.amsearch-link, .-category a.amsearch-link") ?? []),
  ].map((a) => clean(a.getAttribute("title") || a.textContent));
  return { query: searchInput()?.value ?? document.querySelector<HTMLInputElement>("input.amsearch-input")?.value ?? "", items, categories: [...new Set(categories)] };
}

const suggestShown = () => {
  const section = resultSection();
  return Boolean(section && shown(section) && section.querySelector(SUGGEST_CARDS));
};

/** A search move is typing and waiting for its products. */
let searching = false;

/** Products in the dropdown that stay for a moment, not the last keystroke's:
 *  GoPersonal's box searches as it is typed, so right after the last key it
 *  can still show the products for "sabanas 300 hil", then empties while it
 *  fetches the whole query. The caller first lets its debounce fire. */
async function waitForSuggest(ms: number): Promise<boolean> {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (!(await waitFor(suggestShown, Math.max(0, end - Date.now())))) return false;
    await quiet(resultSection()!, 600, 2500);
    if (suggestShown()) return true;
  }
  return false;
}

// ─── The bag ──────────────────────────────────────────────────────────────

interface CartItem {
  name: string;
  path: string;
  qty: number;
  price: number | null;
}

interface CartState {
  items: CartItem[];
  count: number;
  subtotal: number | null;
  free_shipping_left: number | null;
}

const minicartOpen = () => Boolean(document.querySelector("aside.content-minicart-modal._show"));
const counter = () => clean(document.querySelector(".minicart-wrapper .counter-number")?.textContent);

/** The bag from Magento's own customer-data section (what the drawer itself
 *  renders from), else from the drawer or the bag page as they stand. */
async function readCart(): Promise<CartState> {
  try {
    const res = await fetch(`/customer/section/load/?sections=cart&force_new_section_timestamp=true&_=${Date.now()}`, {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
    });
    if (!res.ok) throw new Error(String(res.status));
    const body = (await res.json()) as { cart?: Record<string, unknown> };
    const c = body.cart;
    if (!c) throw new Error("no cart section");
    const items = ((c.items as Record<string, unknown>[] | undefined) ?? []).map((i) => ({
      name: clean(String(i.product_name ?? "")),
      path: pathOf(String(i.product_url ?? "")),
      qty: Number(i.qty) || 0,
      price: i.product_price_value != null ? Math.round(Number(i.product_price_value)) : null,
    }));
    // An empty bag sends the bar as {show: false, remaining: 0}: no answer, not "reached".
    const shownBar = c.freeShippingBar as { show?: boolean; qualified?: boolean; remaining?: number } | undefined;
    const bar = shownBar && shownBar.show !== false ? shownBar : undefined;
    return {
      items,
      count: Number(c.summary_count) || items.reduce((n, i) => n + i.qty, 0),
      subtotal: c.subtotalAmount != null ? Math.round(Number(c.subtotalAmount)) : null,
      free_shipping_left: bar ? (bar.qualified ? 0 : bar.remaining != null ? Math.max(0, Math.round(Number(bar.remaining))) : null) : null,
    };
  } catch {
    return cartFromPage();
  }
}

function cartFromPage(): CartState {
  const lines = [...document.querySelectorAll<HTMLElement>("#minicart-content-wrapper .mc-line")];
  let items: CartItem[] = lines.map((line) => {
    const a = line.querySelector<HTMLAnchorElement>(".mc-line__name a");
    return {
      name: clean(a?.textContent),
      path: pathOf(a?.href),
      qty: Number(line.querySelector<HTMLInputElement>("input.cart-item-qty")?.value || line.querySelector<HTMLElement>("input.cart-item-qty")?.dataset.itemQty) || 0,
      price: money(line.querySelector(".mc-price--now")?.textContent),
    };
  });
  if (!items.length && kindOf() === "cart") {
    items = [...document.querySelectorAll<HTMLElement>("tbody.cart.item")].map((row) => {
      const a = row.querySelector<HTMLAnchorElement>(".product-item-name a");
      return {
        name: clean(a?.textContent),
        path: pathOf(a?.href),
        qty: Number(row.querySelector<HTMLInputElement>("input.qty")?.value) || 0,
        price: money(row.querySelector(".col.price .cart-price .price")?.textContent),
      };
    });
  }
  const bar = document.querySelector(".main-progress-bar");
  const message = document.querySelector(".main-progress-bar__message")?.textContent;
  return {
    items,
    count: money(counter()) ?? items.reduce((n, i) => n + i.qty, 0),
    subtotal: money(document.querySelector(".mc-total-row--grand .mc-total-row__value")?.textContent),
    free_shipping_left: bar?.classList.contains("main-progress-bar--qualified") ? 0 : message ? money(message) : null,
  };
}

/** The bag the brain was last told about, kept across this tab's page loads:
 *  removing a line from the drawer reloads the page, so no watcher sees it. */
const CART_SEEN_KEY = "voqalize.cannonhome.cart";
const cartSig = (c: CartState) => JSON.stringify([c.count, c.items.map((i) => [i.path, i.qty])]);

function reportCart(c: CartState): void {
  report("cart_state", c);
  try {
    sessionStorage.setItem(CART_SEEN_KEY, cartSig(c));
  } catch {
    // Storage refused: a reload's change goes unreported until the next read.
  }
}

/** On a fresh page: report the bag if it is not the one last reported. */
async function cartIfChanged(): Promise<void> {
  let seen: string | null = null;
  try {
    seen = sessionStorage.getItem(CART_SEEN_KEY);
  } catch {
    return;
  }
  if (seen === null) return;
  const c = await readCart();
  if (cartSig(c) !== seen) reportCart(c);
}

const cartLine = (c: CartState) =>
  c.count
    ? `the bag has ${c.count} item${c.count === 1 ? "" : "s"}${c.subtotal != null ? `, subtotal $${c.subtotal}` : ""}${
        c.free_shipping_left ? `, $${c.free_shipping_left} short of free shipping (RM)` : c.free_shipping_left === 0 ? ", free shipping reached (RM)" : ""
      }`
    : "the bag is empty";

// ─── Moves ────────────────────────────────────────────────────────────────

/** A payload's extra flag, set when a move is finished on the page it
 *  loaded: it never loads another (a redirect would loop it). */
interface Arrived {
  arrived?: boolean;
}

// search_products ───────────────────────────────────────────────────────────

async function searchProducts(p: { query: string; open_index?: number | null } & Arrived): Promise<string | null> {
  const query = clean(p.query);
  if (!query) throw new Error("say what to search for");
  let input = searchInput();
  if (!input) {
    // On a phone's home the box hides behind a button.
    const opener = [...document.querySelectorAll<HTMLElement>("button.btn-search, .block-search .label")].find(shown);
    if (opener) {
      press(opener);
      input = await waitFor(searchInput, 1500);
    }
  }
  if (!input) throw new Error("the search box is not on this page");
  await scrollToTopOfPage();
  highlight(input.closest("form") ?? input);
  // While he types, the dropdown shows what the box has so far ("sab…"); the
  // watcher stays quiet, and this move reports the products for the query.
  searching = true;
  try {
    await typeInto(input, query);
    await sleep(1200);
    if (!(await waitForSuggest(9000))) throw new Error(`the search box showed no products for "${query}"`);
  } finally {
    searching = false;
  }
  const suggest = readSuggest();
  report("search_suggest", suggest);
  highlight(resultSection()!);
  const list = suggest.items.map((i) => `${i.name} ($${i.price ?? "?"})`).join("; ");
  if (p.open_index != null) {
    const item = suggest.items[p.open_index];
    if (!item) throw new Error(`the dropdown has ${suggest.items.length} products; there is no number ${p.open_index + 1}`);
    const card = [...resultSection()!.querySelectorAll<HTMLElement>(SUGGEST_CARDS)][p.open_index];
    if (card) highlight(card);
    await sleep(700);
    leave({ command: "open_product", payload: { path: item.path, tab: null }, as: "search_products" });
    go(item.path);
    return null;
  }
  return `typed "${query}" in the search box; the dropdown shows ${suggest.items.length} products: ${list}${
    suggest.categories.length ? `; categories: ${suggest.categories.join(", ")}` : ""
  }`;
}

// filter_listing ────────────────────────────────────────────────────────────

type Sort = "price_asc" | "price_desc" | "relevance" | "newest";

interface FilterListing extends Arrived {
  category_path: string;
  size?: string | null;
  color?: string | null;
  threads?: string | null;
  material?: string | null;
  sort?: Sort | null;
}

/** The brain's filter names, as the site's request variables. */
const FILTER_VARS = { size: "tamano", color: "color", threads: "hilos", material: "material" } as const;

/** For options written several ways ("1,5 plazas", "1.5 Plazas", "Súper
 *  King", "300 hilos" vs "300"). */
const squash = (s: string) => norm(s).replace(/(\d),(\d)/g, "$1.$2").replace(/\bhilos?\b/g, "").replace(/[^a-z0-9.]/g, "");

function findOption(group: HTMLElement, said: string): HTMLAnchorElement | null {
  const options = [...group.querySelectorAll<HTMLAnchorElement>("a.qf__option-link")];
  const title = (o: HTMLAnchorElement) => o.getAttribute("title") || clean(o.querySelector(".qf__option-label")?.textContent);
  const want = squash(said);
  return (
    options.find((o) => squash(title(o)) === want) ??
    best(options, title, said) ??
    options.find((o) => squash(title(o)).startsWith(want) && want.length >= 2) ??
    null
  );
}

/** The listing's path without Amasty's filter segments, as a prefix test. */
const onCategory = (category: string) => {
  const here = location.pathname.replace(/\/+$/, "").toLowerCase();
  const want = pathOf(category).replace(/\/+$/, "").toLowerCase();
  return here === want || here.startsWith(`${want}/`);
};

async function waitForGrid(before: string): Promise<boolean> {
  const changed = await waitFor(() => gridKey() !== before, 10_000);
  await quiet(productList(), 400, 3000);
  return Boolean(changed);
}

async function filterListing(p: FilterListing): Promise<string | null> {
  if (typeof p.category_path !== "string" || !p.category_path.trim()) throw new Error("say which category, as a path like /12-ropa-de-cama/20-sabanas");
  const target = pathOf(p.category_path.trim());
  const wanted = (Object.keys(FILTER_VARS) as (keyof typeof FILTER_VARS)[])
    .filter((k) => p[k])
    .map((k) => ({ key: k, variable: FILTER_VARS[k], said: String(p[k]) }));

  // Another page, or this listing with filters the wish does not have: load
  // the category clean, and finish there.
  const active = activeFilters();
  const stray = Object.entries(active).some(([v, labels]) => {
    const w = wanted.find((x) => x.variable === v);
    return !w || labels.split(", ").some((l) => squash(l) !== squash(w.said));
  });
  if (!p.arrived && (!isListing() || !onCategory(target) || stray)) {
    leave({ command: "filter_listing", payload: { ...p, arrived: true } });
    go(target);
    return null;
  }
  if (!isListing()) throw new Error(`${target} did not open as a product listing (now on ${location.pathname})`);
  await waitFor(() => document.querySelector(".qf__group, ol.products"), 6000);

  const applied: string[] = [];
  const problems: string[] = [];
  for (const w of wanted) {
    const group = document.querySelector<HTMLElement>(`.qf__group[data-qf-request-var="${w.variable}"]`);
    if (!group) {
      const offered = [...document.querySelectorAll<HTMLElement>(".qf__group[data-qf-request-var]")].map((g) => g.dataset.qfRequestVar);
      problems.push(`this listing has no ${w.key} filter (it offers: ${offered.join(", ") || "none"})`);
      continue;
    }
    const option = findOption(group, w.said);
    if (!option) {
      const offered = [...group.querySelectorAll("a.qf__option-link")].map((o) => o.getAttribute("title")).filter(Boolean);
      problems.push(`no ${w.key} "${w.said}" here (it offers: ${offered.join(", ")})`);
      continue;
    }
    const label = option.getAttribute("title") ?? w.said;
    if (option.classList.contains("-active")) {
      applied.push(`${w.key} ${label}`);
      continue;
    }
    // Open the pill so the visitor sees the choice, then choose it.
    const pill = group.querySelector<HTMLElement>(".qf__pill");
    await scrollTo(group.closest(".toolbar, .qf-bar") ?? group, "top");
    if (pill && !shown(option)) {
      press(pill);
      await waitFor(() => shown(option), 1200);
    }
    highlight(shown(option) ? option : (pill ?? group));
    await sleep(500);
    const before = gridKey();
    // Should the click load the filter's own page instead (the site's script
    // not up yet), the next page carries on from here.
    leave({ command: "filter_listing", payload: { ...p, arrived: true } });
    press(option);
    const landed = await waitForGrid(before);
    leave(null);
    if (!landed) problems.push(`the grid did not change after choosing ${label}`);
    else applied.push(`${w.key} ${label}`);
  }

  if (p.sort) {
    const sorter = document.querySelector<HTMLSelectElement>("select#sorter");
    const values = [...(sorter?.options ?? [])].map((o) => o.value);
    const want = p.sort === "newest" ? ["new"] : p.sort === "relevance" ? ["relevance", "position"] : [p.sort];
    const value = want.find((v) => values.includes(v));
    if (!sorter || !value) problems.push(`this listing cannot sort by ${p.sort}`);
    else if (sorter.value !== value) {
      const before = gridKey();
      await scrollTo(sorter.closest(".toolbar") ?? sorter, "top");
      highlight(sorter);
      setValue(sorter, value);
      if (await waitForGrid(before)) applied.push(`sorted ${p.sort}`);
      else problems.push(`the grid did not change after sorting by ${p.sort}`);
    } else applied.push(`sorted ${p.sort}`);
  }

  // Close an open filter panel so the grid shows: its × on a phone; on a
  // desktop the × is hidden and the pill toggles the panel.
  for (const group of document.querySelectorAll<HTMLElement>(".qf__group.-open")) {
    const close = group.querySelector<HTMLElement>(".qf__panel-close");
    const pill = group.querySelector<HTMLElement>(".qf__pill");
    if (close && shown(close)) press(close);
    else if (pill) press(pill);
    await waitFor(() => !group.classList.contains("-open"), 800);
  }
  const listing = readListing();
  report("listing_shown", listing);
  const first = listing.items[0];
  const grid = productList().querySelector("ol.products") ?? productList();
  await scrollTo(grid, "top");
  highlight(grid);
  if (wanted.length && !applied.length && problems.length) throw new Error(problems.join("; "));
  return [
    `${listing.title}: ${listing.count ?? "?"} products`,
    applied.length ? `applied ${applied.join(", ")}` : "",
    first ? `first card ${first.name} ($${first.price ?? "?"})` : "no products",
    ...problems,
  ]
    .filter(Boolean)
    .join("; ");
}

// open_product ──────────────────────────────────────────────────────────────

type Tab = "descripcion" | "especificaciones" | "calificaciones" | "fotos";

const TAB_IDS: Record<Exclude<Tab, "fotos">, string> = {
  descripcion: "tab-label-description",
  especificaciones: "tab-label-product.attributes",
  calificaciones: "tab-label-verificado_widget",
};

/** Open one of the product page's tabs the way a visitor does, by its title;
 *  should Magento's tabs widget not be up yet, show its panel directly. */
async function openTab(tab: Exclude<Tab, "fotos">): Promise<string> {
  const title = document.getElementById(TAB_IDS[tab]);
  if (!title) throw new Error(`this product page has no ${tab} tab`);
  const panel = document.getElementById(title.getAttribute("aria-controls") ?? "");
  await scrollTo(title, "top");
  const open = () => Boolean(panel && shown(panel) && panel.getAttribute("aria-hidden") !== "true");
  if (!open()) {
    press(title.querySelector("a.data.switch") ?? title);
    if (!(await waitFor(open, 1200)) && panel) {
      for (const other of document.querySelectorAll<HTMLElement>(".product.data.items > .data.item.title")) other.classList.remove("active");
      for (const other of document.querySelectorAll<HTMLElement>(".product.data.items > .data.item.content")) {
        other.style.display = "none";
        other.setAttribute("aria-hidden", "true");
      }
      title.classList.add("active");
      title.setAttribute("aria-expanded", "true");
      panel.style.display = "block";
      panel.setAttribute("aria-hidden", "false");
    }
  }
  // The specifications fold under "Ver más".
  const more = panel?.querySelector<HTMLElement>(":scope > .see-more");
  if (more && shown(more)) press(more);
  await sleep(250);
  const box = boxOf([title, ...(panel ? [panel] : [])]);
  const tall = box ? box.bottom - box.top > window.innerHeight * 0.8 : false;
  await scrollTo(title, tall ? "top" : "center");
  highlight(tall ? title : [title, ...(panel ? [panel] : [])]);
  return `opened the ${tab} tab`;
}

/** Step the gallery through a few photos, by its thumbnails. */
async function showPhotos(): Promise<string> {
  const frames = [...document.querySelectorAll<HTMLElement>(".fotorama__nav__frame")];
  const gallery = document.querySelector<HTMLElement>(".product.media, .gallery-placeholder, .fotorama") ?? frames[0];
  if (!gallery) throw new Error("this product page has no gallery");
  await scrollTo(gallery, "top");
  highlight(gallery);
  const steps = Math.min(3, Math.max(0, frames.length - 1));
  for (let i = 1; i <= steps; i++) {
    await sleep(1100);
    press(frames[i]);
  }
  return `stepped the gallery through ${steps + 1} of ${frames.length || 1} photos`;
}

async function openProduct(p: { path: string; tab?: Tab | null } & Arrived): Promise<string | null> {
  if (typeof p.path !== "string" || !p.path.trim()) throw new Error("say which product, as a path like /x.html");
  const target = productPath(p.path);
  if (!p.arrived && !samePath(location.pathname, target)) {
    leave({ command: "open_product", payload: { ...p, arrived: true } });
    go(target);
    return null;
  }
  const form = await waitFor(productForm, 8000);
  if (!form || kindOf() !== "product") throw new Error(`${target} did not open as a product page (now on ${location.pathname})`);
  let did = "";
  if (p.tab === "fotos") did = await showPhotos();
  else if (p.tab) did = await openTab(p.tab);
  else {
    await scrollToTopOfPage();
    const info = productInfo();
    if (info) highlight([...info.querySelectorAll(".product-data-container, .product-info-price")]);
  }
  const product = readProduct();
  if (product) report("product_shown", latestProductFor(product));
  void confirmProduct();
  return [
    product ? `${product.name} is on screen at $${product.price ?? "?"}${product.in_stock === false ? ", out of stock" : ""}` : "the product page is on screen",
    did,
  ]
    .filter(Boolean)
    .join("; ");
}

/** The live (GraphQL) read wins over the page's once it is in. */
function latestProductFor(page: ProductShown): ProductShown {
  const live = latest.get("product_shown") as ProductShown | undefined;
  return live?.source === "graphql" && live.path === page.path ? live : page;
}

// check_prices ──────────────────────────────────────────────────────────────

async function checkPrices(p: { paths: string[] }): Promise<string> {
  const paths = [...new Set((Array.isArray(p.paths) ? p.paths : []).filter((x) => typeof x === "string" && x.trim()).map(productPath))].slice(
    0,
    MAX_PRICED,
  );
  if (!paths.length) throw new Error("say which products, as paths like /x.html");
  const keys = paths.map(keyOf);
  const found = new Map<string, GqlProduct>();
  const data = await gql<{ products?: { items?: GqlProduct[] } }>(
    `query ($keys: [String]) { products(filter: { url_key: { in: $keys } }, pageSize: 20) { items { ${PRODUCT_FIELDS} } } }`,
    { keys },
  );
  for (const item of data.products?.items ?? []) if (item.url_key) found.set(item.url_key.toLowerCase(), item);
  // `products` hides what is out of stock; `route` names it.
  const unseen = paths.filter((x) => !found.has(keyOf(x).toLowerCase()));
  if (unseen.length) for (const [k, v] of await routes(unseen)) found.set(k.toLowerCase(), v);
  const here = kindOf() === "product" ? readProduct() : null;
  const items = paths
    .filter((x) => found.has(keyOf(x).toLowerCase()))
    .map((path) => {
      const hit = found.get(keyOf(path).toLowerCase())!;
      const live = priced(hit);
      return {
        path,
        sku: hit.sku ?? "",
        name: hit.name ?? "",
        ...live,
        qty: live.in_stock === false ? 0 : here && samePath(here.path, path) ? here.qty : null,
      };
    });
  const missing = paths.filter((x) => !found.has(keyOf(x).toLowerCase()));
  report("prices_read", { items, missing });
  return [
    items.map((i) => `${i.name}: $${i.price ?? "?"}${i.regular_price ? ` (was $${i.regular_price})` : ""}, ${i.in_stock ? "in stock" : "out of stock"}`).join("; "),
    missing.length ? `not found: ${missing.join(", ")}` : "",
  ]
    .filter(Boolean)
    .join("; ");
}

// add_to_cart ───────────────────────────────────────────────────────────────

/** Magento's add-to-cart widget is bound to the form (a jQuery submit
 *  handler): before that, a press would post the form as a plain page load.
 *  A page without RequireJS (a saved copy) has nothing to wait for. */
function addToCartReady(form: HTMLFormElement): boolean {
  const w = window as unknown as { require?: unknown; jQuery?: { _data?: (el: Element, key: string) => Record<string, unknown> | undefined } };
  if (!w.require) return true;
  const events = w.jQuery?._data?.(form, "events");
  return Boolean(events && events.submit);
}

async function setQty(qty: number): Promise<number> {
  const input = document.querySelector<HTMLInputElement>("#product_addtocart_form input#qty");
  if (!input) throw new Error("this product page has no quantity box");
  const now = () => Number(input.value) || 1;
  for (let guard = 0; now() !== qty && guard < 12; guard++) {
    const button = document.querySelector<HTMLButtonElement>(now() < qty ? "#addQty" : "#minusQty");
    const was = now();
    if (button && !button.disabled) {
      press(button);
      await sleep(220);
    }
    if (now() === was) {
      // The buttons did nothing (their script not up): type it.
      setValue(input, String(qty));
      break;
    }
  }
  return now();
}

async function addToCart(p: { path: string; qty?: number } & Arrived): Promise<string | null> {
  if (typeof p.path !== "string" || !p.path.trim()) throw new Error("say which product, as a path like /x.html");
  const qty = Math.round(Number(p.qty ?? 1));
  if (!Number.isFinite(qty) || qty < 1 || qty > 10) throw new Error(`a quantity from 1 to 10, not ${p.qty}`);
  const target = productPath(p.path);
  if (!p.arrived && !samePath(location.pathname, target)) {
    leave({ command: "add_to_cart", payload: { ...p, arrived: true } });
    go(target);
    return null;
  }
  const form = await waitFor(productForm, 8000);
  if (!form || kindOf() !== "product") throw new Error(`${target} did not open as a product page (now on ${location.pathname})`);
  if (form.querySelector(".stock.unavailable")) throw new Error("the page says this product is out of stock; nothing was added");
  const button = form.querySelector<HTMLButtonElement>("#product-addtocart-button");
  if (!button) throw new Error("this product page has no Agregar button");
  await waitFor(() => addToCartReady(form), 10_000);
  await scrollTo(form.querySelector(".box-tocart") ?? form, "center");
  const set = await setQty(qty);
  if (set !== qty) throw new Error(`the quantity box shows ${set}, not ${qty}; nothing was added`);
  highlight(form.querySelector(".box-tocart") ?? button);
  await sleep(400);
  const before = counter();
  press(button);
  const confirmed = await waitFor(() => minicartOpen() || counter() !== before, 9000);
  await sleep(300);
  const cart = await readCart();
  reportCart(cart);
  const line = cart.items.find((i) => samePath(i.path, target));
  if (!confirmed && !line) throw new Error("pressed Agregar, but the bag did not change; ask the visitor to check the bag");
  if (minicartOpen()) highlight(document.querySelector("aside.content-minicart-modal._show .modal-inner-wrap") ?? document.querySelector("aside.content-minicart-modal._show")!);
  const name = readProduct()?.name ?? target;
  return `added ${qty} × ${name}${line ? ` (the bag line now has ${line.qty})` : ""}; ${cartLine(cart)}${minicartOpen() ? "; the bag drawer is open" : ""}`;
}

// show_cart ─────────────────────────────────────────────────────────────────

async function showCart(p: { open?: boolean }): Promise<string | null> {
  if (p.open === false) {
    if (!minicartOpen()) return "the bag drawer was already closed";
    // The drawer's own ×, else Magento's modal close.
    const close =
      document.querySelector<HTMLElement>("aside.content-minicart-modal._show .mc-header__close") ??
      document.querySelector<HTMLElement>("aside.content-minicart-modal._show [data-role=closeBtn]");
    if (!close) throw new Error("the bag drawer has no close button");
    press(close);
    if (!(await waitFor(() => !minicartOpen(), 3000))) throw new Error("the bag drawer did not close");
    return "closed the bag drawer";
  }
  if (!minicartOpen()) {
    const trigger = [...document.querySelectorAll<HTMLElement>(".minicart-wrapper a.action.showcart")].find(shown);
    if (!trigger) throw new Error("this page has no bag button");
    await scrollToTopOfPage();
    // Before the drawer's script is up, the same press loads the bag page,
    // which is the bag too.
    press(trigger);
    if (!(await waitFor(minicartOpen, 4000))) throw new Error("the bag drawer did not open");
  }
  await quiet(document.querySelector("#minicart-content-wrapper") ?? document.body, 300, 1500);
  const cart = await readCart();
  reportCart(cart);
  highlight(document.querySelector("aside.content-minicart-modal._show .modal-inner-wrap") ?? document.querySelector("aside.content-minicart-modal._show")!);
  return `opened the bag drawer; ${cartLine(cart)}`;
}

// start_checkout, fill_checkout ────────────────────────────────────────────

/** The delivery form's fields Javier may fill, by the brain's names, in the
 *  form's order. The RUT field sits among them and is never one of them. */
const FILL_ORDER = ["email", "region", "comuna", "street", "number", "apartment", "first_name", "last_name", "phone"] as const;
type FillKey = (typeof FILL_ORDER)[number];
type TextKey = Exclude<FillKey, "email" | "region" | "comuna">;

/** The delivery form's `.field[name=…]` (Knockout's data scope) per field. */
const FIELD_SCOPES: Record<string, string> = {
  "shippingAddress.firstname": "first_name",
  "shippingAddress.lastname": "last_name",
  "shippingAddress.custom_attributes.rut": "rut",
  "shippingAddress.street.0": "street",
  "shippingAddress.street.1": "number",
  "shippingAddress.street.2": "apartment",
  "shippingAddress.telephone": "phone",
  "shippingAddress.region_id": "region",
  "shippingAddress.custom_attributes.city_id": "comuna",
};
const TEXT_INPUTS: Record<TextKey, string> = {
  street: "input[name='street[0]']",
  number: "input[name='street[1]']",
  apartment: "input[name='street[2]']",
  first_name: "input[name='firstname']",
  last_name: "input[name='lastname']",
  phone: ".field.telephone input[name='telephone']:not([type=hidden])",
};
const FIELD_LABEL: Record<string, string> = {
  email: "email", region: "región", comuna: "comuna", street: "dirección", number: "número", apartment: "depto/casa",
  first_name: "nombre", last_name: "apellidos", phone: "teléfono", rut: "RUT", delivery: "método de envío",
};

const onCheckout = () => kindOf() === "checkout";
const shippingForm = () => document.querySelector<HTMLFormElement>("#checkout #co-shipping-form, form#co-shipping-form");
const emailInput = () =>
  document.querySelector<HTMLInputElement>("#checkout form[data-role='email-with-possible-login'] input[type=email], #checkout input#customer-email");
const emailForm = () => emailInput()?.closest("form") ?? null;
const pickerOf = (key: "region" | "comuna") =>
  shippingForm()?.querySelector<HTMLElement>(`.field.${key === "region" ? "region_id" : "city_id"} .cn-region-search`) ?? null;
const pickedIn = (box: HTMLElement | null) => {
  const v = box?.querySelector(".cn-region-search__value");
  return v && !v.classList.contains("is-placeholder") ? clean(v.textContent) : "";
};
const filledIn = (el: HTMLInputElement | null | undefined) => Boolean(el && el.value.trim());

interface CheckoutState {
  filled: string[];
  missing: string[];
  invalid: { field: string; message: string }[];
  region: string;
  comuna: string;
  email_has_account: boolean;
  delivery_options: string[];
  delivery: string;
  payment_open: boolean;
}

/** The delivery form as it stands: which fields hold something, never what
 *  (but the región and comuna, the site's own names); what is missing; what
 *  the form flags, in its words. The RUT is only ever checked for being empty,
 *  and nothing of the payment step is read. */
function readCheckout(): CheckoutState {
  const form = shippingForm();
  const filled: string[] = [];
  const missing: string[] = [];
  const invalid: { field: string; message: string }[] = [];
  const region = pickedIn(pickerOf("region"));
  const comuna = pickedIn(pickerOf("comuna"));
  const has: Record<string, boolean> = {
    email: filledIn(emailInput()),
    region: Boolean(region),
    comuna: Boolean(comuna),
    rut: filledIn(form?.querySelector<HTMLInputElement>(".field.rut input, input[name*='rut' i]")),
  };
  for (const [key, sel] of Object.entries(TEXT_INPUTS)) has[key] = filledIn(form?.querySelector<HTMLInputElement>(sel));
  const order = ["email", "region", "comuna", "street", "number", "apartment", "first_name", "last_name", "rut", "phone"];
  const required = new Set(["email", "region", "comuna", "street", "number", "first_name", "last_name", "rut", "phone"]);
  for (const key of order) {
    if (has[key]) filled.push(key);
    else if (required.has(key)) missing.push(key);
  }
  // The form's messages, under each field (Magento's `.field-error`, jQuery
  // validate's `.mage-error`), named by the field's data scope.
  const errors = [...(form?.querySelectorAll<HTMLElement>(".field-error, div.mage-error") ?? []), ...(emailForm()?.querySelectorAll<HTMLElement>(".field-error, div.mage-error, #customer-email-error") ?? [])];
  for (const err of errors) {
    const message = clean(err.textContent);
    if (!message || !shown(err)) continue;
    const field = err.closest(".field");
    const key = field?.closest("#customer-email-fieldset, form[data-role='email-with-possible-login']") ? "email" : FIELD_SCOPES[field?.getAttribute("name") ?? ""];
    if (key && !invalid.some((i) => i.field === key)) invalid.push({ field: key, message: message.slice(0, 160) });
  }
  const methods = [...document.querySelectorAll<HTMLInputElement>("#checkout input[name=common_shipping_type]")].filter((r) => shown(r.closest(".method-content") ?? r));
  const methodName = (r: HTMLInputElement) =>
    clean((r.closest(".title-method") ?? r.closest(".method-content"))?.querySelector(".main-method-title p, .method-head-group > span > span")?.textContent ?? r.value);
  const chosen = methods.find((r) => r.checked);
  if (methods.length && !chosen) missing.push("delivery");
  if (chosen) filled.push("delivery");
  const password = [...(emailForm()?.querySelectorAll<HTMLInputElement>("input[type=password]") ?? [])].some(shown);
  const payment = document.querySelector("#checkout-step-payment");
  return {
    filled,
    missing,
    invalid,
    region,
    comuna,
    email_has_account: password,
    delivery_options: methods.map(methodName),
    delivery: chosen ? methodName(chosen) : "",
    payment_open: Boolean(payment && shown(payment)),
  };
}

const reportCheckout = () => {
  if (onCheckout() && shippingForm()) report("checkout_state", readCheckout());
};

/** The form is up: Knockout has rendered the delivery form and the email. */
const formReady = () => (shippingForm() && emailInput() && pickerOf("region") ? shippingForm() : null);

/** Take the visitor to the delivery form, then do `then` there (a fill). From
 *  any page: the bag first; on the bag, "Terminar pedido", then the login
 *  window's "Comprar como invitado" (a link to /checkout). Each load carries
 *  the rest in `sessionStorage`. */
async function toCheckout(then: Leftover | null, arrived: boolean): Promise<string | null> {
  if (onCheckout()) {
    const form = await waitFor(formReady, 20_000);
    if (!form) throw new Error("the checkout opened, but its delivery form did not show");
    if (/payment/i.test(location.hash)) throw new Error("the checkout is at its payment step, which is the visitor's");
    if (then) {
      const r = await perform(then.command, then.payload);
      if (!r.ok) throw new Error(r.error);
      return r.detail ?? "";
    }
    await scrollTo(emailForm() ?? form, "top");
    highlight(emailForm() ?? form);
    reportCheckout();
    return `the guest checkout's delivery form is open (${describeCheckout(readCheckout())})`;
  }
  const as = then?.command ?? "start_checkout";
  if (arrived) throw new Error(`the checkout did not open (now on ${location.pathname}); the bag may be empty`);
  if (kindOf() !== "cart") {
    leave({ command: "start_checkout", payload: { then }, as });
    go("/checkout/cart/");
    return null;
  }
  if (!document.querySelector("tbody.cart.item") && document.querySelector(".cart-empty")) throw new Error("the bag is empty; there is nothing to check out");
  const button = await waitFor(() => [...document.querySelectorAll<HTMLElement>("button[data-role='proceed-to-checkout']")].find(shown), 8000);
  if (!button) throw new Error("the bag page has no Terminar pedido button");
  // The window "Terminar pedido" opens is Knockout's: pressed before it has
  // rendered, it opens empty.
  await waitFor(() => document.querySelector("#block-login a[href]"), 10_000);
  await scrollTo(button, "center");
  highlight(button);
  await sleep(500);
  press(button);
  const guest = await waitFor(
    () =>
      [...document.querySelectorAll<HTMLAnchorElement>("aside.login-modal._show a[href]")].find((a) => {
        const to = new URL(a.href, location.href);
        return /^\/checkout\/?$/i.test(to.pathname) && shown(a);
      }),
    12_000,
  );
  leave({ command: "start_checkout", payload: { then, arrived: true }, as });
  if (guest) {
    highlight(guest);
    await sleep(700);
    press(guest);
  } else {
    // The window did not render its links: "Comprar como invitado" is only
    // this link.
    go("/checkout");
  }
  return null;
}

function describeCheckout(c: CheckoutState): string {
  const names = (keys: string[]) => keys.map((k) => FIELD_LABEL[k] ?? k).join(", ");
  const bits = [c.filled.length ? `filled: ${names(c.filled)}` : "nothing filled yet"];
  if (c.missing.length) bits.push(`missing: ${names(c.missing)}`);
  if (c.invalid.length) bits.push(`the form flags ${c.invalid.map((i) => `${FIELD_LABEL[i.field] ?? i.field} ("${i.message}")`).join(", ")}`);
  return bits.join("; ");
}

async function startCheckout(p: { then?: Leftover | null } & Arrived): Promise<string | null> {
  return toCheckout(p.then ?? null, Boolean(p.arrived));
}

/** Type `value` into one of the form's own text fields, as a finished edit
 *  (Knockout's `value` binding updates on `change` and `keyup`), unless the
 *  field is the visitor's alone or the value does not fit it. */
async function fillField(el: HTMLInputElement, value: string, label: string): Promise<void> {
  const why = privateField(el);
  if (why) throw new Error(`refused ${label}: ${why}`);
  const max = el.maxLength > 0 ? el.maxLength : Infinity;
  if (value.length > max) throw new Error(`${label} takes at most ${max} characters`);
  await scrollTo(el, "center");
  el.focus({ preventScroll: true });
  setValue(el, value);
  el.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true, key: "Unidentified" }));
  if (el.value !== value) throw new Error(`${label} did not take what was typed (it shows ${el.value.length} characters)`);
}

/** Pick `said` in the form's región or comuna list (its own searchable
 *  dropdown); the comuna's list loads by AJAX once a región is chosen. */
async function pick(key: "region" | "comuna", said: string): Promise<string> {
  const box = pickerOf(key);
  const trigger = box?.querySelector<HTMLButtonElement>(".cn-region-search__trigger");
  if (!box || !trigger) throw new Error(`the form has no ${FIELD_LABEL[key]} list`);
  if (norm(pickedIn(box)) === norm(said)) return pickedIn(box);
  if (key === "comuna" && !pickedIn(pickerOf("region"))) throw new Error("the comuna list opens once a región is chosen; choose the región first");
  const open = () => trigger.getAttribute("aria-disabled") !== "true" && !trigger.disabled;
  if (!(await waitFor(open, key === "comuna" ? 8000 : 3000))) {
    throw new Error(key === "comuna" ? "the comuna list opens once a región is chosen; choose the región first" : "the región list is locked");
  }
  await scrollTo(box, "center");
  if (!box.classList.contains("is-open")) press(trigger);
  const label = (li: HTMLElement) => clean(li.querySelector(".cn-region-search__item-label")?.textContent ?? li.textContent);
  const items = await waitFor(() => {
    const li = [...box.querySelectorAll<HTMLElement>(".cn-region-search__item")];
    return li.length ? li : null;
  }, 8000);
  const hit = items ? best(items, label, said) : null;
  if (!hit) {
    if (box.classList.contains("is-open")) press(trigger);
    const listed = (items ?? []).map(label);
    const near = listed.filter((l) => norm(l)[0] === norm(said)[0]).slice(0, 12);
    throw new Error(`no ${FIELD_LABEL[key]} "${said}" in the form's list${listed.length ? `; it lists ${(near.length ? near : listed.slice(0, 12)).join(", ")}${listed.length > 12 ? "…" : ""}` : " (it is empty)"}`);
  }
  const name = label(hit);
  hit.scrollIntoView({ block: "nearest" });
  press(hit);
  if (!(await waitFor(() => norm(pickedIn(box)) === norm(name), 4000))) throw new Error(`${FIELD_LABEL[key]} "${name}" did not stay chosen`);
  return name;
}

/** Choose the phone's prefix (+56 9 for a mobile, +56 2 for a Santiago line)
 *  from the first of the nine digits; the other eight go in the field. */
async function phonePrefix(first: string): Promise<void> {
  const box = shippingForm()?.querySelector<HTMLElement>(".field.telephone .flag-container");
  if (!box) return;
  const want = `56 ${first}`;
  const now = clean(box.querySelector(".iti-flag, .selected-flag")?.textContent).replace(/^\+/, "");
  if (now === `+${want}` || now === want) return;
  const flag = box.querySelector<HTMLElement>(".selected-flag");
  if (!flag) throw new Error("the phone field has no prefix to choose");
  press(flag);
  const li = await waitFor(() => box.querySelector<HTMLElement>(`li.country[data-dial-code="${want}"]`), 3000);
  if (!li) throw new Error(`the phone field has no +${want} prefix`);
  press(li);
  if (!(await waitFor(() => clean(box.querySelector(".iti-flag, .selected-flag")?.textContent).replace(/^\+/, "") === want, 2000))) {
    throw new Error(`the phone prefix did not change to +${want}`);
  }
}

type FillCheckout = Partial<Record<FillKey, string | null>>;

async function fillCheckout(p: FillCheckout & { arrived?: boolean }): Promise<string | null> {
  const given = FILL_ORDER.filter((k) => typeof p[k] === "string" && p[k]!.trim());
  if (!given.length) throw new Error("say what to fill: email, región, comuna, dirección, número, depto/casa, nombre, apellidos or teléfono");
  if (!onCheckout()) {
    const payload: Record<string, string> = {};
    for (const k of given) payload[k] = p[k]!;
    return toCheckout({ command: "fill_checkout", payload }, Boolean(p.arrived));
  }
  if (/payment/i.test(location.hash)) throw new Error("the checkout is at its payment step, which is the visitor's; nothing was filled");
  const form = await waitFor(formReady, 15_000);
  if (!form) throw new Error("the checkout's delivery form is not on screen");
  const done: string[] = [];
  const failed: string[] = [];
  const touched: Element[] = [];
  for (const key of given) {
    const value = clean(p[key]);
    const label = FIELD_LABEL[key];
    try {
      if (key === "email") {
        const el = emailInput()!;
        await fillField(el, value, label);
        touched.push(el);
      } else if (key === "region" || key === "comuna") {
        const name = await pick(key, value);
        touched.push(pickerOf(key)!);
        done.push(`${label} ${name}`);
        continue;
      } else if (key === "phone") {
        const digits = value.replace(/\D/g, "");
        if (!/^[92]\d{8}$/.test(digits)) throw new Error("a Chilean number is nine digits, starting with 9 or 2");
        await phonePrefix(digits[0]);
        const el = form.querySelector<HTMLInputElement>(TEXT_INPUTS.phone);
        if (!el) throw new Error("the form has no phone field");
        await fillField(el, digits.slice(1), label);
        touched.push(el.closest(".field") ?? el);
      } else {
        const el = form.querySelector<HTMLInputElement>(TEXT_INPUTS[key]);
        if (!el) throw new Error(`the form has no ${label} field`);
        await fillField(el, value, label);
        touched.push(el);
      }
      done.push(label);
    } catch (error) {
      failed.push(`${label}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  // Knockout's validation shows on blur; give it a moment, then report.
  await quiet(form, 300, 1500);
  const state = readCheckout();
  report("checkout_state", state);
  if (touched.length) highlight(touched);
  if (!done.length) throw new Error(`nothing was filled: ${failed.join("; ")}`);
  return `filled ${done.join(", ")}${failed.length ? `; not filled: ${failed.join("; ")}` : ""}; ${describeCheckout(state)}; nothing was pressed after the fields`;
}

// Cue moves: navigate, show_section, open_faq (clini's) ────────────────────

async function navigate(p: { path: string; heading?: string | null; text?: string | null; faq?: string | null } & Arrived) {
  if (typeof p.path !== "string" || !p.path.trim()) throw new Error("say which page to go to, as a path");
  const target = new URL(p.path.trim(), location.origin);
  const rest: Leftover | null = p.faq
    ? { command: "open_faq", payload: { question: p.faq } }
    : p.heading || p.text
      ? { command: "show_section", payload: { heading: p.heading ?? null, text: p.text ?? null } }
      : null;
  if (!samePath(location.pathname, target.pathname) || (target.search && target.search !== location.search)) {
    leave(rest);
    go(target.pathname + target.search + target.hash);
    return null;
  }
  if (rest) {
    const r = await perform(rest.command, rest.payload);
    if (!r.ok) throw new Error(r.error);
    return r.detail ?? "";
  }
  await scrollToTopOfPage();
  return `${location.pathname} is on screen`;
}

const original = (el: Element | null | undefined) => el?.getAttribute("data-voqalize-text") ?? "";

function findHeading(heading: string): HTMLElement | null {
  const all = headings();
  return best(all, (x) => x.text, heading)?.el ?? best(all, (x) => original(x.el), heading)?.el ?? null;
}

/** What a heading heads: its Page Builder row or column when that fits on
 *  the screen, else the heading and the blocks after it. */
function sectionOf(h: HTMLElement): HTMLElement[] {
  const fits = (el: HTMLElement) => {
    const b = boxOf([el]);
    return !b || b.bottom - b.top < window.innerHeight * 1.3;
  };
  const more = (el: HTMLElement) => clean(el.textContent).length > clean(h.textContent).length + 20;
  for (let el = h.parentElement; el && el !== main(); el = el.parentElement) {
    if (el.matches("[data-content-type=row], [data-content-type=column], section, .block, li") && more(el) && fits(el)) return [el];
  }
  return [h, ...answerAfter(h)];
}

function smallestContaining(root: Element, text: string): HTMLElement | null {
  const want = norm(text);
  if (!want) return null;
  let found: HTMLElement | null = null;
  let bestLen = Infinity;
  for (const el of root.querySelectorAll<HTMLElement>("*")) {
    if (inChrome(el) || /^(SCRIPT|STYLE|NOSCRIPT|svg|IFRAME)$/i.test(el.tagName) || !visible(el)) continue;
    const t = norm(el.textContent);
    if (t.includes(want) && t.length < bestLen) [found, bestLen] = [el, t.length];
  }
  return found;
}

async function showSection(p: { heading?: string | null; text?: string | null }) {
  const h = p.heading ? findHeading(p.heading) : null;
  if (p.heading && !h && !p.text) {
    throw new Error(`no heading "${p.heading}" on ${location.pathname}; it has: ${context().headings.slice(0, 25).join(" | ") || "no headings"}`);
  }
  if (p.text) {
    const el = (h && sectionOf(h).map((s) => smallestContaining(s, p.text!)).find(Boolean)) || smallestContaining(main(), p.text);
    if (!el) throw new Error(`"${p.text}" is not on ${location.pathname}`);
    await scrollTo(el, el.getBoundingClientRect().height > window.innerHeight * 0.7 ? "top" : "center");
    highlight(el);
    return `showed "${p.text}"`;
  }
  if (!h) throw new Error("say which heading or text to show");
  const section = sectionOf(h);
  const box = boxOf(section);
  const height = box ? box.bottom - box.top : Infinity;
  const room = window.innerHeight - headerHeight() - 32;
  await scrollTo(height <= room ? section[0] : h, height <= room ? "center" : "top");
  highlight(height > window.innerHeight * 1.3 ? h : section);
  return `showed "${clean(h.textContent)}"`;
}

async function openFaq(p: { question: string }) {
  const all = faqItems();
  const item = best(all, (f) => f.question, p.question ?? "") ?? best(all, (f) => original(f.block), p.question ?? "");
  if (!item) {
    throw new Error(`no FAQ "${p.question}" on ${location.pathname}${all.length ? `; it has: ${all.map((f) => f.question).slice(0, 15).join(" | ")}` : ""}`);
  }
  await scrollTo(item.block, "center");
  if (!item.isOpen() && item.toggle) {
    press(item.toggle);
    await waitFor(item.isOpen, 2000);
    await sleep(300);
  }
  const group = [item.block, ...item.answer()];
  const box = boxOf(group);
  await scrollTo(item.block, box && box.bottom - box.top > window.innerHeight * 0.7 ? "top" : "center");
  highlight(group);
  return `opened "${item.question}"`;
}

// ─── Running moves, one at a time ─────────────────────────────────────────

type Command = (payload: never) => Promise<string | null>;

const COMMANDS: Record<string, Command> = {
  search_products: searchProducts,
  filter_listing: filterListing,
  open_product: openProduct,
  check_prices: checkPrices,
  add_to_cart: addToCart,
  show_cart: showCart,
  start_checkout: startCheckout,
  fill_checkout: fillCheckout,
  navigate,
  show_section: showSection,
  open_faq: openFaq,
};

async function perform(command: string, payload: unknown): Promise<RunResult> {
  const fn = COMMANDS[command];
  if (!fn) return { ok: false, error: `the page on ${location.host} cannot ${command}` };
  try {
    const detail = await fn((payload ?? {}) as never);
    // `null`: the move went on to another page, which finishes it.
    if (detail === null) return { ok: true, moved: true };
    return { ok: true, detail };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

/** One move at a time: a move waits for the one before it to finish (a
 *  filter for its grid, an add for the bag), whoever sent them. */
let running: Promise<unknown> = Promise.resolve();
function run(command: string, payload: unknown): Promise<RunResult> {
  const turn = running.then(() => perform(command, payload));
  running = turn.catch(() => undefined);
  return turn;
}

/** Finish the move a page of this tab started before it loaded this one,
 *  once this page has settled. */
async function finishLeftover(): Promise<void> {
  const then = takeLeftover();
  if (!then) return;
  await settled();
  const result = await run(then.command, then.payload);
  const command = then.as ?? (then.command === "show_section" || then.command === "open_faq" || then.command === "navigate" ? "cue" : then.command);
  if (!result.ok) emit("command_failed", { command, error: result.error ?? "failed" });
  else if (!result.moved && DONE_COMMANDS.has(command)) emit("command_done", { command, detail: result.detail ?? "" });
}

// ─── Watching the page ────────────────────────────────────────────────────

let lastUrl: string | null = null;

/** The URL changed without a load (Amasty's pushState after a filter, a
 *  history step): the page is reported again. */
function urlChanged(): void {
  const here = location.origin + location.pathname + location.search;
  if (here === lastUrl) return;
  lastUrl = here;
  if (emitter) emitter("page_changed", context());
}

function watchUrl(): void {
  lastUrl = location.origin + location.pathname + location.search;
  for (const name of ["pushState", "replaceState"] as const) {
    const original = history[name].bind(history);
    history[name] = (...args: Parameters<History["pushState"]>) => {
      const out = original(...args);
      queueMicrotask(urlChanged);
      return out;
    };
  }
  window.addEventListener("popstate", urlChanged);
  window.addEventListener("hashchange", urlChanged);
}

/** `fn` once changes pause for `ms`, and at least every `most` while they
 *  never pause (the cards' image carousels move all the time). */
function debounced(fn: () => void, ms = REPORT_DEBOUNCE_MS, most = 1500): () => void {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let first = 0;
  return () => {
    if (timer) clearTimeout(timer);
    if (!first) first = Date.now();
    const wait = Math.max(0, Math.min(ms, first + most - Date.now()));
    timer = setTimeout(() => {
      timer = null;
      first = 0;
      fn();
    }, wait);
  };
}

/** Grid updates (filters, sort, paging) on a listing; the search dropdown on
 *  any page; the bag drawer's lines. Each reported when it settles. */
function watchState(): () => void {
  const observers: MutationObserver[] = [];
  const watch = (el: Element | null, fn: () => void) => {
    if (!el) return;
    const obs = new MutationObserver(debounced(fn));
    obs.observe(el, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["class", "style"] });
    observers.push(obs);
  };
  if (isListing()) {
    watch(main(), () => {
      urlChanged();
      report("listing_shown", readListing());
    });
  }
  for (const el of new Set([gpDropdown(), document.querySelector(".amsearch-result-section")?.parentElement ?? null])) {
    watch(el, () => {
      if (!searching && suggestShown()) report("search_suggest", readSuggest());
    });
  }
  if (onCheckout()) {
    // The delivery form, whoever types in it: reported as it settles. Its
    // fields are Knockout's and render late, so the whole checkout is watched,
    // with the edits the visitor finishes.
    const again = debounced(reportCheckout, 600, 2500);
    const root = document.querySelector("#checkout") ?? document.body;
    const obs = new MutationObserver(again);
    obs.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ["class", "style", "aria-invalid"] });
    observers.push(obs);
    for (const type of ["change", "focusout"]) document.addEventListener(type, again, true);
    observers.push({ disconnect: () => ["change", "focusout"].forEach((type) => document.removeEventListener(type, again, true)) } as MutationObserver);
  }
  let bag = cartKey();
  watch(document.querySelector("#minicart-content-wrapper"), () => {
    const now = cartKey();
    if (now === bag) return;
    bag = now;
    void readCart().then(reportCart);
  });
  return () => observers.forEach((o) => o.disconnect());
}

const cartKey = () => {
  const c = cartFromPage();
  return JSON.stringify([c.count, c.items.map((i) => [i.path, i.qty])]);
};

/** This page's state, read now: the product, the listing, the bag page. */
function readState(): void {
  const kind = kindOf();
  if (kind === "product") {
    const product = readProduct();
    if (product) report("product_shown", latestProductFor(product));
    void confirmProduct();
  } else if (kind === "category" || kind === "search") {
    report("listing_shown", readListing());
  }
  if (kind === "checkout") void waitFor(formReady, 20_000).then((form) => form && reportCheckout());
  if (kind === "cart") void readCart().then(reportCart);
  else void cartIfChanged();
}

let stopWatching: (() => void) | null = null;

function start(next: (event: string, payload: unknown) => void): () => void {
  emitter = next;
  lastUrl = location.origin + location.pathname + location.search;
  next("page_changed", context());
  for (const [event, payload] of latest) report(event, payload);
  for (const [event, payload] of backlog.splice(0)) next(event, payload);
  readState();
  stopWatching ??= watchState();
  return () => {
    if (emitter === next) {
      emitter = null;
      stopWatching?.();
      stopWatching = null;
    }
  };
}

if (!window.voqalizeCannonhome) {
  styleThePage();
  watchUrl();
  // The state is read at once (a call that rejoins after a load gets it the
  // moment it listens), and the move left from the last page is finished.
  void settled().then(readState);
  void finishLeftover();
  window.voqalizeCannonhome = { run, context, start, commands: Object.keys(COMMANDS) };
}

// Exported for the end-to-end tests.
export { readCart, readListing, readProduct, readSuggest };
