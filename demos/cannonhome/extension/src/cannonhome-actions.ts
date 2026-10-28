/**
 * The site adapter: drive cannonhome.cl from the outside, with no help from
 * Cannon Home's developers.
 *
 * Javier's moves arrive through Stage (`@voqalize/stage`): each is a move
 * registered here (`registerMoves`), made on the page in front, one at a
 * time, ringed with the spotlight before it acts, and answered with one
 * `stage_result`. The page reports what it shows through `start`, which calls
 * `emit(event, payload)`, whoever moved it:
 *
 *   - `page_changed` for every page the visitor lands on, whoever took them;
 *   - `prices_read` for `check_prices`.
 *
 * What their screen holds is Stage state (`cannonhome/scene.json`): each change
 * goes as a named `stage_event` (`scene.event`), with only the fields its
 * slice declares, and `by: "agent"` with the move's `call_ref` when one of
 * Javier's moves made it:
 *
 *   - `product.shown` on a product page, read from the page at once, then
 *     `product.checked` once one `POST /graphql` confirms it, because the HTML
 *     is served from Fastly's cache and its price and stock can be hours old;
 *   - `listing.shown` on a category or search listing, and `listing.filtered`
 *     / `listing.sorted` after an AJAX grid update on the same listing,
 *     whoever made it;
 *   - `search.suggested` whenever the search box's dropdown shows products;
 *   - `cart.changed` after an add, when the bag opens, and when it changes;
 *   - `checkout.changed` on the checkout's delivery form: which fields hold
 *     something (never what), which are missing, what the form flags.
 *
 * The site, for a script like this: Magento 2.4 (Luma-derived theme
 * `Cannon/cannon`, RequireJS, jQuery, Knockout), Amasty Xsearch for the search
 * box, Amasty Shopby for the listing filters, a custom quick-filter bar
 * (`.qf__group`), fotorama for the gallery. Every product is a simple product:
 * each size and colour is its own page, so there is no option to pick on a
 * product page. Moving between pages is a full load, so a move to another page
 * carries the rest of itself to it (`load`, `keep`), and the next page
 * finishes it with the same call. Filters, sort and paging are AJAX with
 * `history.pushState`; add-to-cart is AJAX and slides the bag in by itself.
 *
 * Nothing here goes past the checkout's delivery form: every click goes
 * through `press`, every load through `target` (`page.ts`). They let Javier take a
 * guest from the bag to the form ("Terminar pedido", then "Comprar como
 * invitado") and pick the form's región and comuna, and refuse every login,
 * the delivery method, the payment step and the place-order button. Fields
 * are filled only through `fillField`, which refuses the RUT, any password and
 * anything of the payment, whatever the brain sends.
 */

import type { MoveContext, Moves, Performer, PerformResult, Refusal, StageEvent } from "@voqalize/stage";
import type { Adapter } from "@voqalize/stage/extension";

import { scene } from "./scene.gen";

import {
  amount, best, boxOf, clean, headerHeight, inOrder, money, norm, pathOf, press, privateField, quiet, samePath, scrollTo,
  scrollToTopOfPage, setValue, settled, shown, sleep, styleThePage, target, typeInto, visible, waitFor,
} from "./page";

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
/** The latest of each state report on this page, and what each listener was
 *  last sent, so a report is sent once and a late listener gets the latest. */
const latest = new Map<string, unknown>();
const sent = new WeakMap<object, Map<string, string>>();

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
  emitter(...onTheWire(event, payload));
}

/** Javier's move in progress, or just finished: a change on the page then is
 *  his, reported with the move's `call_ref`. */
let agent: { callRef: string; until: number } | null = null;
/** A change this soon after his move finished is still the move's. */
const AGENT_WINDOW_MS = 500;

/** `perform`, with what it changes on the page reported as his. */
function asAgent<A>(perform: Performer<A>): Performer<A> {
  return async (args, c) => {
    agent = { callRef: c.callRef, until: Number.POSITIVE_INFINITY };
    try {
      return await perform(args, c);
    } finally {
      agent = { callRef: c.callRef, until: Date.now() + AGENT_WINDOW_MS };
    }
  };
}

function who(): { by: "visitor" | "agent"; callRef?: string } {
  return agent && Date.now() <= agent.until ? { by: "agent", callRef: agent.callRef } : { by: "visitor" };
}

/** The listing last reported in this tab, kept across a load (a filter link
 *  may load the page): a new report of the same one is a filter or a sort,
 *  not a new listing. */
const LAST_LISTING = "voqalize.cannonhome.listing";
type Seen = { path: string; filters: string; sort: string };

function lastListing(): Seen | null {
  try {
    return JSON.parse(sessionStorage.getItem(LAST_LISTING) ?? "null") as Seen | null;
  } catch {
    return null;
  }
}

function sawListing(seen: Seen): void {
  try {
    sessionStorage.setItem(LAST_LISTING, JSON.stringify(seen));
  } catch {
    // No storage here: the next report of it reads as a new listing.
  }
}

/** A state report as it goes to the brain: a Stage state event for what the
 *  screen holds, the site's own event for the rest. */
function onTheWire(event: string, payload: unknown): [string, unknown] {
  const by = who();
  let ev: StageEvent | null = null;
  switch (event) {
    case "product_shown": {
      const p = payload as ProductShown;
      ev = scene.event(
        p.source === "graphql" ? "product.checked" : "product.shown",
        { ...p, specs: Object.entries(p.specs).map(([label, value]) => ({ label, value })) },
        by,
      );
      break;
    }
    case "listing_shown": {
      const l = payload as ReturnType<typeof readListing>;
      const filters = JSON.stringify(l.filters);
      const sort = l.sort ?? "";
      // The listing itself, not its address: a filter may add its options to
      // the path (`/20-sabanas/rosa`), and taking it off takes them away.
      const here = l.path.replace(/\/+$/, "");
      const before = lastListing();
      const same = before !== null && (here === before.path || here.startsWith(`${before.path}/`) || before.path.startsWith(`${here}/`));
      const name = same && before.filters !== filters ? "listing.filtered" : same && before.sort !== sort ? "listing.sorted" : "listing.shown";
      sawListing({ path: same && before.path.length < here.length ? before.path : here, filters, sort });
      ev = scene.event(
        name,
        {
          path: l.path,
          title: l.title,
          count: l.count,
          filters: Object.entries(l.filters).map(([facet, on]) => ({ facet, on: on.split(", "), options: [] })),
          sort: l.sort ?? null,
          items: l.items,
        },
        by,
      );
      break;
    }
    case "search_suggest":
      ev = scene.event("search.suggested", payload as ReturnType<typeof readSuggest>, by);
      break;
    case "cart_state":
      ev = scene.event("cart.changed", payload as CartState, by);
      break;
    case "checkout_state":
      ev = scene.event("checkout.changed", payload as CheckoutState, by);
      break;
  }
  return ev ? ["stage_event", ev] : [event, payload];
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
      const qty = Number(row.querySelector<HTMLInputElement>("input.qty")?.value) || 0;
      // The bag page's price column is the line's total: one unit is that over the quantity.
      const total = money(row.querySelector(".col.price .cart-price .price")?.textContent);
      return { name: clean(a?.textContent), path: pathOf(a?.href), qty, price: total != null && qty ? Math.round(total / qty) : total };
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
//
// Every move is a Stage move, registered with `Moves` (`registerMoves`): its
// performer finds the target, rings it with the spotlight before it acts, and
// returns a short detail of what it did; a refusal names the argument and
// what the page offers instead (`c.refuse`); an error is the move failing. A
// move that loads another page carries the rest of itself to it (`load`,
// `keep`): the next page makes it, with the same call, and reports it.

/** A move's arguments, with its flag for a move finished on the page it
 *  loaded: it never loads another (a redirect would loop it). */
interface Arrived {
  arrived?: boolean;
}

/** The rest of a move, for the next page of this tab. */
interface Then {
  move: string;
  args: unknown;
}

/** Load `path` in this tab, with the rest of the move for the page it lands
 *  on (without it, the move is done once that page is up); refused before
 *  anything moves if `path` is past the delivery form, an account page or
 *  another host. The move goes on there: `null`. */
async function load(c: MoveContext, path: string, then?: Then): Promise<null> {
  const url = target(path);
  if (!c.loadThen) throw new Error("this page cannot load another and carry the move there");
  await c.loadThen(url, then);
  return null;
}

/** Ring `el` with the spotlight; resolves after Stage's beat, so what is
 *  pressed next is already ringed, and the ring stays up its dwell. */
function ring(c: MoveContext, el: Element | Element[]): Promise<void> {
  return c.ring(el);
}

/** A link on this page to `path`, to ring before loading it. */
function linkTo(path: string): HTMLAnchorElement | null {
  return (
    [...main().querySelectorAll<HTMLAnchorElement>("a[href]")].find((a) => shown(a) && !inChrome(a) && samePath(a.href, path)) ??
    null
  );
}

// search_products ───────────────────────────────────────────────────────────

async function searchProducts(p: { query: string; open_index?: number | null } & Arrived, c: MoveContext): Promise<string | null> {
  const query = clean(p.query);
  if (!query) c.refuse("query", "say what to search for");
  let input = searchInput();
  if (!input) {
    // On a phone's home the box hides behind a button.
    const opener = [...document.querySelectorAll<HTMLElement>("button.btn-search, .block-search .label")].find(shown);
    if (opener) {
      await ring(c, opener);
      press(opener);
      input = await waitFor(searchInput, 1500);
    }
  }
  if (!input) throw new Error("the search box is not on this page");
  await scrollToTopOfPage();
  await ring(c, input.closest("form") ?? input);
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
  // The dropdown is the effect: ringed after the result, unless a card of
  // it is pressed next.
  if (p.open_index != null) await ring(c, resultSection()!);
  else c.after(() => ring(c, resultSection()!));
  const list = suggest.items.map((i) => `${i.name} ($${i.price ?? "?"})`).join("; ");
  if (p.open_index != null) {
    const item = suggest.items[p.open_index];
    if (!item) {
      c.refuse("open_index", `the dropdown has ${suggest.items.length} products; there is no number ${p.open_index + 1}`, suggest.items.map((i) => i.name));
    }
    const card = [...resultSection()!.querySelectorAll<HTMLElement>(SUGGEST_CARDS)][p.open_index];
    if (card) await ring(c, card);
    return load(c, item.path, { move: "open_product", args: { path: item.path, tab: null, arrived: true } });
  }
  return `typed "${query}" in the search box; the dropdown shows ${suggest.items.length} products: ${list}${
    suggest.categories.length ? `; categories: ${suggest.categories.join(", ")}` : ""
  }`;
}

// filter_listing, and the filter and sort cues ─────────────────────────────

type Sort = "price_asc" | "price_desc" | "relevance" | "newest";

/** One option, or several of one filter (the listing then shows any of them);
 *  a plain string from an older brain is one. */
type Said = string | string[] | null;

interface FilterListing extends Arrived {
  category_path: string;
  size?: Said;
  color?: Said;
  threads?: Said;
  material?: Said;
  sort?: Sort | null;
  /** Set on the page the combined filter address loaded: the filters are
   *  checked there, and never loaded a second time. */
  combined?: boolean;
}

/** The brain's filter names, as the site's request variables. */
const FILTER_VARS = { size: "tamano", color: "color", threads: "hilos", material: "material" } as const;
/** What a filter cue may name its facet, as the site's request variables. */
const FACETS: Record<string, string> = {
  tamano: "tamano", talla: "tamano", size: "tamano", color: "color", colour: "color",
  hilos: "hilos", threads: "hilos", material: "material",
};
const FACET_SAID: Record<string, string> = { tamano: "Tamaño", color: "Color", hilos: "Hilos", material: "Material" };

/** For options written several ways ("1,5 plazas", "1.5 Plazas", "Súper
 *  King", "300 hilos" vs "300"). */
const squash = (s: string) => norm(s).replace(/(\d),(\d)/g, "$1.$2").replace(/\bhilos?\b/g, "").replace(/[^a-z0-9.]/g, "");

const optionTitle = (o: HTMLAnchorElement) => o.getAttribute("title") || clean(o.querySelector(".qf__option-label")?.textContent);

/** Each option in what was sent: a list's items, or a cue's labels with ", "
 *  between them ("Blanco, Beige"). No option label has a comma and a space;
 *  "1,5" has no space. */
const saidValues = (said: Said | undefined): string[] =>
  (Array.isArray(said) ? said : said ? [said] : [])
    .flatMap((s) => String(s).split(/,\s+/))
    .map((s) => s.trim())
    .filter(Boolean);

/** The options on now, in every quick filter. */
function activeOptions(): Option[] {
  return [...document.querySelectorAll<HTMLAnchorElement>(".qf__group[data-qf-request-var] a.qf__option-link.-active")].map((option) => {
    const group = option.closest<HTMLElement>(".qf__group")!;
    return { variable: group.dataset.qfRequestVar!, group, option, label: optionTitle(option) };
  });
}

/** Whether `o` is on now: looked up again, as the store may have redrawn the
 *  bar since it was found. */
function isOn(o: Option): boolean {
  return activeOptions().some((a) => a.variable === o.variable && (o.option.dataset.qfValue ? a.option.dataset.qfValue === o.option.dataset.qfValue : squash(a.label) === squash(o.label)));
}

/** The listing's own path, without the options' path segments Amasty pushes
 *  (`/20-sabanas/beige-blanco_1`): the base a filter address is built on. */
function listingBase(): string {
  const here = location.pathname.replace(/\/+$/, "");
  const aliases = new Set(
    // An option that is on links to the address without it: the listing's own,
    // on a page filtered by it alone. Only the others name options.
    [...document.querySelectorAll<HTMLAnchorElement>("a.qf__option-link:not(.-active)")].flatMap((a) => {
      try {
        return (new URL(a.href, location.href).pathname.split("/").pop() ?? "").split("-");
      } catch {
        return [];
      }
    }),
  );
  const last = here.split("/").pop() ?? "";
  return last && last.split("-").every((s) => aliases.has(s)) ? here.slice(0, -last.length - 1) || "/" : here || "/";
}

function findOption(group: HTMLElement, said: string): HTMLAnchorElement | null {
  const options = [...group.querySelectorAll<HTMLAnchorElement>("a.qf__option-link")];
  const want = squash(said);
  return (
    options.find((o) => squash(optionTitle(o)) === want) ??
    best(options, optionTitle, said) ??
    options.find((o) => squash(optionTitle(o)).startsWith(want) && want.length >= 2) ??
    null
  );
}

const offeredFacets = () =>
  [...document.querySelectorAll<HTMLElement>(".qf__group[data-qf-request-var]")].map((g) => g.dataset.qfRequestVar!).filter(Boolean);

/** The listing's path without Amasty's filter segments, as a prefix test. */
const onCategory = (category: string) => {
  const here = location.pathname.replace(/\/+$/, "").toLowerCase();
  const want = pathOf(category).replace(/\/+$/, "").toLowerCase();
  return here === want || here.startsWith(`${want}/`);
};

async function waitForGrid(before: string, ms = 10_000): Promise<boolean> {
  const changed = await waitFor(() => gridKey() !== before, ms);
  if (changed) await quiet(productList(), 400, 3000);
  return Boolean(changed);
}

/** How long a filter's press may change nothing before the option's own
 *  address is loaded instead; a fetch the site shows under way gets up to
 *  `FILTER_PRESS_MAX_MS`. */
const FILTER_PRESS_MS = 3000;
const FILTER_PRESS_MAX_MS = 10_000;
/** How long a filter waits for the store's filter scripts after a load,
 *  before it presses anyway (a dev call on 2026-10-28 waited out a 10 s cap on
 *  a listing loaded 21 s before, and the press then worked). */
const FILTERS_READY_MS = 3000;

/**
 * The listing's filter scripts are up. The quick-filter bar marks its root
 * `data-qf-ready` once it is bound, and hands a press on to Amasty's own
 * filter, whose AJAX widget sits on the body: a press before both does
 * nothing at all — no grid change and no load (dev, 2026-10-28: "King"
 * pressed 0.4 s after a load, then 13 s of nothing, where the same press
 * worked on a page loaded 40 s before). A page without RequireJS (a saved
 * copy) has nothing to wait for.
 */
function filtersReady(): boolean {
  return filtersWaitingOn() === null;
}

/** What the listing's filter scripts are still missing, or `null` when they
 *  are up: logged when a filter presses without them. */
function filtersWaitingOn(): string | null {
  const w = window as unknown as { require?: unknown; jQuery?: { data?: (el: Element, key: string) => unknown } };
  if (!w.require) return null;
  const root = document.querySelector("[data-qf-root]");
  if (!root) return "no [data-qf-root] quick-filter bar";
  if (root.getAttribute("data-qf-ready") !== "1") return `[data-qf-root] has data-qf-ready=${JSON.stringify(root.getAttribute("data-qf-ready"))}`;
  const data = w.jQuery?.data;
  if (!data) return null;
  // jQuery UI keeps a widget under its full name, "mage-amShopbyAjax".
  if (data(document.body, "mage-amShopbyAjax") ?? data(document.body, "mageAmShopbyAjax")) return null;
  return "no amShopbyAjax widget on <body>";
}

/** Wait a short while for the filter scripts; then press anyway, saying
 *  which part of them never showed. */
async function awaitFilters(): Promise<void> {
  if (await waitFor(filtersReady, FILTERS_READY_MS)) return;
  console.warn(`voqalize: the filter scripts are not up after ${FILTERS_READY_MS} ms (${filtersWaitingOn()}); pressing anyway`);
}

/** The store is fetching a filtered grid: Amasty's overlay, or an option the
 *  bar marks pending. */
function filtering(): boolean {
  const overlay = document.querySelector("#amasty-shopby-overlay");
  return Boolean((overlay && shown(overlay)) || document.querySelector(".qf__option-link.-pending-on, .qf__option.-pending-on"));
}

/** One option of one quick filter, found by what was said. */
interface Option {
  variable: string;
  group: HTMLElement;
  option: HTMLAnchorElement;
  label: string;
}

/** How choosing one option went: applied (or already on), or why not. */
type Applied = { ok: true; label: string } | Missed;
type Missed = { ok: false; why: string; arg: "facet" | "value"; options: string[] };

function optionFor(variable: string, said: string, name = FACET_SAID[variable] ?? variable): Option | Missed {
  const group = document.querySelector<HTMLElement>(`.qf__group[data-qf-request-var="${variable}"]`);
  if (!group) {
    return { ok: false, arg: "facet", why: `this listing has no ${name} filter`, options: offeredFacets() };
  }
  const option = findOption(group, said);
  if (!option) {
    const offered = [...group.querySelectorAll<HTMLAnchorElement>("a.qf__option-link")].map(optionTitle).filter(Boolean);
    return { ok: false, arg: "value", why: `no ${name} "${said}" here`, options: offered };
  }
  return { variable, group, option, label: optionTitle(option) || said };
}

/**
 * Choose one option of one quick filter, as the visitor would: scroll to the
 * bar, wait for the store's filter scripts, open the filter's pill, ring the
 * option, a beat, press it, and wait for the grid. A press that changed
 * nothing loads the option's own address (the store serves it filtered), as
 * does a press that loads it by itself: either way the next page carries
 * `then` on, and this is `null`.
 *
 * It adds: every option already on stays on. The live store's quick filters
 * take several options of one filter (on a Beige listing, Blanco links to
 * `/beige-blanco_1`, and `?color=6826,6889` shows both, 211 sheets where Beige
 * alone shows 40; checked 2026-10-28). A press that put this one on and took
 * another off loads the address with all of them, as does a press that
 * changed nothing while others are on (the option's own link may not carry
 * them). `base` is the listing's path, for that address.
 */
async function applyFacet(
  c: MoveContext,
  variable: string,
  said: string,
  then: Then,
  name = FACET_SAID[variable] ?? variable,
  base = listingBase(),
): Promise<Applied | null> {
  const found = optionFor(variable, said, name);
  if ("ok" in found) return found;
  const { group, option, label } = found;
  if (option.classList.contains("-active")) return { ok: true, label };
  const kept = activeOptions();
  const args = then.args as { reloaded?: boolean };
  const all = () => load(c, filteredUrl(base, [...kept, found]), { ...then, args: { ...args, reloaded: true } });
  const pill = group.querySelector<HTMLElement>(".qf__pill");
  await scrollTo(group.closest(".toolbar, .qf-bar") ?? group, "top");
  await awaitFilters();
  if (pill && !shown(option)) {
    await ring(c, pill);
    press(pill);
    await waitFor(() => shown(option), 1200);
  }
  await ring(c, shown(option) ? option : (pill ?? group));
  const before = gridKey();
  await c.keep(then);
  press(option);
  let landed = await waitForGrid(before, FILTER_PRESS_MS);
  if (!landed && filtering()) landed = await waitForGrid(before, FILTER_PRESS_MAX_MS - FILTER_PRESS_MS);
  await c.drop();
  if (landed) {
    // The press replaced what was on: the address with every one of them.
    const lost = kept.filter((k) => !isOn(k));
    if (!lost.length) return { ok: true, label };
    if (!args.reloaded) return all();
    return { ok: false, arg: "value", why: `choosing ${label} took ${lost.map((k) => k.label).join(", ")} off`, options: [] };
  }
  // Nothing took the press: the option's own address is the same filter
  // (with the others on, the address with all of them). Loaded once per
  // move, so a store that ignores it cannot loop it.
  const href = option.getAttribute("href");
  if (!args.reloaded && kept.length) return all();
  if (href && !args.reloaded) return load(c, href, { ...then, args: { ...args, reloaded: true } });
  return { ok: false, arg: "value", why: `the grid did not change after choosing ${label}`, options: [] };
}

/** The listing at `path` filtered by every option in `chosen`, as one
 *  address: the store takes each filter as its request variable and option
 *  id (`?tamano=5625&hilos=5700`), for any number of them. (Its path form,
 *  `/king_1-200_hilos`, comes back unfiltered past two, checked on the live
 *  store on 2026-10-28.) */
function filteredUrl(path: string, chosen: Option[]): string {
  const params = new URLSearchParams();
  for (const o of chosen) {
    const value = o.option.dataset.qfValue;
    if (!value) continue;
    const had = params.get(o.variable);
    params.set(o.variable, had ? `${had},${value}` : value);
  }
  // Several options of one filter, by a bare comma, as the store's own links
  // write them (`?color=6826,6889`; it also takes `%2C`).
  const query = params.toString().replace(/%2C/gi, ",");
  return pathOf(path) + (query ? `?${query}` : "");
}

/** Sort the listing by `sort`, the sorter ringed first. */
async function applySort(c: MoveContext, sort: Sort): Promise<Applied> {
  const sorter = document.querySelector<HTMLSelectElement>("select#sorter");
  const values = [...(sorter?.options ?? [])].map((o) => o.value);
  const want = sort === "newest" ? ["new"] : sort === "relevance" ? ["relevance", "position"] : [sort];
  const value = want.find((v) => values.includes(v));
  if (!sorter || !value) return { ok: false, arg: "value", why: `this listing cannot sort by ${sort}`, options: values };
  if (sorter.value === value) return { ok: true, label: `sorted ${sort}` };
  const before = gridKey();
  await scrollTo(sorter.closest(".toolbar") ?? sorter, "top");
  await ring(c, sorter);
  setValue(sorter, value);
  if (!(await waitForGrid(before))) return { ok: false, arg: "value", why: `the grid did not change after sorting by ${sort}`, options: [] };
  return { ok: true, label: `sorted ${sort}` };
}

/** Close an open filter panel so the grid shows: its × on a phone; on a
 *  desktop the × is hidden and the pill toggles the panel. */
async function closePanels(): Promise<void> {
  for (const group of document.querySelectorAll<HTMLElement>(".qf__group.-open")) {
    const close = group.querySelector<HTMLElement>(".qf__panel-close");
    const pill = group.querySelector<HTMLElement>(".qf__pill");
    if (close && shown(close)) press(close);
    else if (pill) press(pill);
    await waitFor(() => !group.classList.contains("-open"), 800);
  }
}

/** The listing as it now stands, reported: a detail. Its grid is scrolled to
 *  and ringed after the move's result, which goes as soon as the grid has
 *  landed: that ring points at the effect, it acts on nothing. */
async function showGrid(c: MoveContext): Promise<string> {
  const listing = readListing();
  report("listing_shown", listing);
  // Looked up again when ringed: the store may swap the grid again meanwhile.
  const grid = () => productList().querySelector("ol.products") ?? productList();
  c.after(async () => {
    await scrollTo(grid(), "top");
    await ring(c, grid());
  });
  const first = listing.items[0];
  return `${listing.title}: ${listing.count ?? "?"} products; ${first ? `first card ${first.name} ($${first.price ?? "?"})` : "no products"}`;
}

/** Before a listing move: the listing at `path` must be the one in front, or
 *  it is loaded and the move carried there. */
async function onListing(c: MoveContext, path: string | null | undefined, arrived: boolean, then: Then): Promise<null | true> {
  if (path && !arrived && (!isListing() || !onCategory(path))) return load(c, path, then);
  if (!isListing()) throw new Error(`${path ?? location.pathname} is not a product listing (now on ${location.pathname})`);
  await waitFor(() => document.querySelector(".qf__group, ol.products"), 6000);
  return true;
}

async function filterListing(p: FilterListing, c: MoveContext): Promise<string | null | PerformResult> {
  if (typeof p.category_path !== "string" || !p.category_path.trim()) c.refuse("category_path", "say which category, as a path like /12-ropa-de-cama/20-sabanas");
  const path = pathOf(p.category_path.trim());
  // One entry per option: a filter of several options is several entries.
  const wanted = (Object.keys(FILTER_VARS) as (keyof typeof FILTER_VARS)[]).flatMap((k) =>
    saidValues(p[k]).map((said) => ({ key: k, variable: FILTER_VARS[k], said })),
  );
  const again: Then = { move: c.move, args: { ...p, arrived: true } };
  // Another page, or this listing with options on that the wish does not
  // have (compared as sets, per filter): load the category clean, and finish
  // there.
  const stray = Object.entries(activeFilters()).some(([v, labels]) => {
    const asked = wanted.filter((x) => x.variable === v).map((x) => squash(x.said));
    return labels.split(", ").some((l) => !asked.includes(squash(l)));
  });
  const here = !p.arrived && isListing() && onCategory(path);
  if ((await onListing(c, path, Boolean(p.arrived), again)) === null) return null;

  // Several options to choose (or this listing's own filters to drop): each
  // ringed where it sits, then one load of the address that has them all —
  // about 3 s, where a press each, a grid each, took 13 to 22. Two options of
  // one filter are one variable with both ids (`?color=6826,6889`).
  if (!p.combined) {
    await waitFor(() => document.querySelector(".qf__group"), 3000);
    const chosen = wanted.map((w) => optionFor(w.variable, w.said, w.key)).filter((o): o is Option => !("ok" in o));
    const todo = chosen.filter((o) => !o.option.classList.contains("-active"));
    if (chosen.length && (todo.length >= 2 || (here && stray))) {
      const marks = todo.map((o) => (shown(o.option) ? o.option : (o.group.querySelector<HTMLElement>(".qf__pill") ?? o.group)));
      if (marks.length) {
        await scrollTo(marks[0].closest(".toolbar, .qf-bar") ?? marks[0], "top");
        await c.ring(marks, { separate: true, label: todo.map((o) => o.label).join(" · ") });
      }
      return load(c, filteredUrl(path, chosen), { move: c.move, args: { ...p, arrived: true, combined: true } });
    }
  }
  if (here && stray) return load(c, path, again);

  // What is on, by the argument that asked for it, as the listing writes it.
  const on: { key: string; option: Option }[] = [];
  // What the listing could not take, by the argument that asked for it.
  const missed: Refusal[] = [];
  for (const w of wanted) {
    if (p.combined) {
      // The address that has them all is loaded: checked, never pressed again.
      const found = optionFor(w.variable, w.said, w.key);
      if ("ok" in found) missed.push({ arg: w.key, why: found.why, options: found.options });
      else if (!found.option.classList.contains("-active")) {
        missed.push({ arg: w.key, why: `${w.key} ${found.label} is not on after loading the listing with it`, options: [] });
      } else on.push({ key: w.key, option: found });
      continue;
    }
    const got = await applyFacet(c, w.variable, w.said, again, w.key, path);
    if (got === null) return null;
    if (!got.ok) {
      missed.push({ arg: w.key, why: got.why, options: got.options });
      continue;
    }
    const found = optionFor(w.variable, got.label, w.key);
    if (!("ok" in found)) on.push({ key: w.key, option: found });
  }
  // Every option asked for is checked on at the end: a later press may have
  // taken an earlier one off.
  const applied = new Map<string, string[]>();
  for (const { key, option } of on) {
    if (isOn(option)) applied.set(key, [...(applied.get(key) ?? []), option.label]);
    else missed.push({ arg: key, why: `${key} ${option.label} is not on any more`, options: [] });
  }
  const done = [...applied].map(([key, labels]) => `${key} ${labels.join(" + ")}`);
  if (p.sort) {
    const got = await applySort(c, p.sort);
    if (got.ok) done.push(got.label);
    else missed.push({ arg: "sort", why: got.why, options: got.options });
  }
  await closePanels();
  const grid = await showGrid(c);
  if (wanted.length && !done.length && missed.length) {
    throw new Error(missed.map((m) => (m.options?.length ? `${m.why} (it offers: ${m.options.join(", ")})` : m.why)).join("; "));
  }
  // Some but not all: a partial outcome, never taken for the whole wish; what
  // it could not take rides in `refused`, with what the listing offers.
  if (done.length && missed.length) {
    return { outcome: "partial", detail: `applied ${done.join(", ")}; ${grid}`, refused: missed };
  }
  return [grid, done.length ? `applied ${done.join(", ")}` : ""].filter(Boolean).join("; ");
}

/** The filter cue: one option of one filter, as its words are said, or
 *  several of one filter (`Color | Blanco, Beige`). Each is added to what is
 *  on — the options already on stay on — and every one is checked on at the
 *  end: one that is not makes it `partial`, naming it, never `applied`. */
async function filterCue(p: { facet: string; value?: string | null; path?: string | null } & Arrived, c: MoveContext): Promise<string | null | PerformResult> {
  const variable = FACETS[norm(p.facet ?? "")] ?? (offeredFacets().includes(p.facet) ? p.facet : null);
  if (!variable) c.refuse("facet", `a listing has no filter "${p.facet}"`, offeredFacets());
  const values = saidValues(p.value);
  if (!values.length) c.refuse("value", "say which option, as the listing writes it");
  const then: Then = { move: c.move, args: { ...p, arrived: true } };
  if ((await onListing(c, p.path, Boolean(p.arrived), then)) === null) return null;
  const base = p.path ? pathOf(p.path) : listingBase();
  const name = FACET_SAID[variable] ?? variable;
  const on: Option[] = [];
  const missed: Missed[] = [];
  for (const value of values) {
    const got = await applyFacet(c, variable, value, then, name, base);
    if (got === null) return null;
    if (!got.ok) {
      missed.push(got);
      continue;
    }
    const found = optionFor(variable, got.label, name);
    if (!("ok" in found)) on.push(found);
  }
  const done: string[] = [];
  for (const o of on) {
    if (isOn(o)) done.push(o.label);
    else missed.push({ ok: false, arg: "value", why: `${name} ${o.label} is not on any more`, options: [] });
  }
  if (!done.length) c.refuse(missed[0]?.arg ?? "value", missed.map((m) => m.why).join("; "), missed[0]?.options ?? []);
  await closePanels();
  const grid = await showGrid(c);
  const detail = `${name} ${done.join(", ")} applied; ${grid}`;
  if (missed.length) return { outcome: "partial", detail, refused: missed.map((m) => ({ arg: m.arg, why: m.why, options: m.options })) };
  return detail;
}

/** The sort cue. */
async function sortCue(p: { order: string; path?: string | null } & Arrived, c: MoveContext): Promise<string | null> {
  const orders: Sort[] = ["price_asc", "price_desc", "relevance", "newest"];
  const order = orders.find((o) => o === p.order);
  if (!order) c.refuse("order", `no sort "${p.order}"`, orders);
  if ((await onListing(c, p.path, Boolean(p.arrived), { move: c.move, args: { ...p, arrived: true } })) === null) return null;
  const got = await applySort(c, order);
  if (!got.ok) c.refuse(got.arg, got.why, got.options);
  return `${got.label}; ${await showGrid(c)}`;
}

// open_product, product_tab ─────────────────────────────────────────────────

type Tab = "descripcion" | "especificaciones" | "calificaciones" | "fotos";

const TAB_IDS: Record<Exclude<Tab, "fotos">, string> = {
  descripcion: "tab-label-description",
  especificaciones: "tab-label-product.attributes",
  calificaciones: "tab-label-verificado_widget",
};

/** Open one of the product page's tabs the way a visitor does, by its title,
 *  ringed first; should Magento's tabs widget not be up yet, show its panel
 *  directly. */
async function openTab(tab: Exclude<Tab, "fotos">, c: MoveContext): Promise<string> {
  const title = document.getElementById(TAB_IDS[tab]);
  if (!title) c.refuse("tab", `this product page has no ${tab} tab`, Object.keys(TAB_IDS).filter((t) => document.getElementById(TAB_IDS[t as keyof typeof TAB_IDS])));
  const panel = document.getElementById(title.getAttribute("aria-controls") ?? "");
  await scrollTo(title, "top");
  const open = () => Boolean(panel && shown(panel) && panel.getAttribute("aria-hidden") !== "true");
  if (!open()) {
    await ring(c, title);
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
  if (more && shown(more)) {
    await ring(c, more);
    press(more);
  }
  await sleep(250);
  const box = boxOf([title, ...(panel ? [panel] : [])]);
  const tall = box ? box.bottom - box.top > window.innerHeight * 0.8 : false;
  await scrollTo(title, tall ? "top" : "center");
  await ring(c, tall ? title : [title, ...(panel ? [panel] : [])]);
  return `opened the ${tab} tab`;
}

/** Step the gallery through a few photos, by its thumbnails, ringed first. */
async function showPhotos(c: MoveContext): Promise<string> {
  const frames = [...document.querySelectorAll<HTMLElement>(".fotorama__nav__frame")];
  const gallery = document.querySelector<HTMLElement>(".product.media, .gallery-placeholder, .fotorama") ?? frames[0];
  if (!gallery) throw new Error("this product page has no gallery");
  await scrollTo(gallery, "top");
  await ring(c, gallery);
  const steps = Math.min(3, Math.max(0, frames.length - 1));
  for (let i = 1; i <= steps; i++) {
    await sleep(1100);
    press(frames[i]);
  }
  return `stepped the gallery through ${steps + 1} of ${frames.length || 1} photos`;
}

async function productTab(p: { tab: Tab }, c: MoveContext): Promise<string> {
  if (kindOf() !== "product") throw new Error(`no product page is on screen (now on ${location.pathname})`);
  return p.tab === "fotos" ? showPhotos(c) : openTab(p.tab, c);
}

async function openProduct(p: { path: string; tab?: Tab | null } & Arrived, c: MoveContext): Promise<string | null> {
  if (typeof p.path !== "string" || !p.path.trim()) c.refuse("path", "say which product, as a path like /x.html");
  const path = productPath(p.path);
  if (!p.arrived && !samePath(location.pathname, path)) {
    // Its card or link on this page, when it has one, is ringed first.
    const link = linkTo(path);
    if (link) await ring(c, link.closest("li.product-item") ?? link);
    return load(c, path, { move: c.move, args: { ...p, arrived: true } });
  }
  const form = await waitFor(productForm, 8000);
  if (!form || kindOf() !== "product") throw new Error(`${path} did not open as a product page (now on ${location.pathname})`);
  let did = "";
  if (p.tab === "fotos") did = await showPhotos(c);
  else if (p.tab) did = await openTab(p.tab, c);
  else {
    // The product is the effect: its name and price are ringed after the
    // result, which goes as soon as the page is up.
    c.after(async () => {
      await scrollToTopOfPage();
      const info = productInfo();
      if (info) await ring(c, [...info.querySelectorAll(".product-data-container, .product-info-price")]);
    });
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

// check_prices: a read, nothing on the page moves ──────────────────────────

async function checkPrices(p: { paths: string[] }, c: MoveContext): Promise<string> {
  const paths = [...new Set((Array.isArray(p.paths) ? p.paths : []).filter((x) => typeof x === "string" && x.trim()).map(productPath))].slice(
    0,
    MAX_PRICED,
  );
  if (!paths.length) c.refuse("paths", "say which products, as paths like /x.html");
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

const drawer = () =>
  document.querySelector("aside.content-minicart-modal._show .modal-inner-wrap") ?? document.querySelector("aside.content-minicart-modal._show");

async function addToCart(p: { path: string; qty?: number } & Arrived, c: MoveContext): Promise<string | null> {
  if (typeof p.path !== "string" || !p.path.trim()) c.refuse("path", "say which product, as a path like /x.html");
  const qty = Math.round(Number(p.qty ?? 1));
  if (!Number.isFinite(qty) || qty < 1 || qty > 10) c.refuse("qty", `a quantity from 1 to 10, not ${p.qty}`);
  const path = productPath(p.path);
  if (!p.arrived && !samePath(location.pathname, path)) return load(c, path, { move: c.move, args: { ...p, arrived: true } });
  const form = await waitFor(productForm, 8000);
  if (!form || kindOf() !== "product") throw new Error(`${path} did not open as a product page (now on ${location.pathname})`);
  if (form.querySelector(".stock.unavailable")) throw new Error("the page says this product is out of stock; nothing was added");
  const button = form.querySelector<HTMLButtonElement>("#product-addtocart-button");
  if (!button) throw new Error("this product page has no Agregar button");
  await waitFor(() => addToCartReady(form), 10_000);
  await scrollTo(form.querySelector(".box-tocart") ?? form, "center");
  await ring(c, form.querySelector(".box-tocart") ?? button);
  const set = await setQty(qty);
  if (set !== qty) throw new Error(`the quantity box shows ${set}, not ${qty}; nothing was added`);
  await sleep(400);
  const before = counter();
  press(button);
  const confirmed = await waitFor(() => minicartOpen() || counter() !== before, 9000);
  await sleep(300);
  const cart = await readCart();
  reportCart(cart);
  const line = cart.items.find((i) => samePath(i.path, path));
  if (!confirmed && !line) throw new Error("pressed Agregar, but the bag did not change; ask the visitor to check the bag");
  const open = drawer();
  if (open) await ring(c, open);
  const name = readProduct()?.name ?? path;
  return `added ${qty} × ${name}${line ? ` (the bag line now has ${line.qty})` : ""}; ${cartLine(cart)}${minicartOpen() ? "; the bag drawer is open" : ""}`;
}

// show_cart ─────────────────────────────────────────────────────────────────

async function showCart(p: { open?: boolean }, c: MoveContext): Promise<string | null> {
  if (p.open === false) {
    if (!minicartOpen()) return "the bag drawer was already closed";
    // The drawer's own ×, else Magento's modal close.
    const close =
      document.querySelector<HTMLElement>("aside.content-minicart-modal._show .mc-header__close") ??
      document.querySelector<HTMLElement>("aside.content-minicart-modal._show [data-role=closeBtn]");
    if (!close) throw new Error("the bag drawer has no close button");
    await ring(c, close);
    press(close);
    if (!(await waitFor(() => !minicartOpen(), 3000))) throw new Error("the bag drawer did not close");
    c.spotlight.clear();
    return "closed the bag drawer";
  }
  await openDrawer(c);
  const cart = await readCart();
  reportCart(cart);
  const open = drawer();
  if (open) await ring(c, open);
  return `opened the bag drawer; ${cartLine(cart)}`;
}

// update_cart_item ──────────────────────────────────────────────────────────

/** How many presses one change may take, across the bag page's reloads. */
const MAX_CART_STEPS = 12;

interface JQueryish {
  _data?: (el: Element | Document, key: string) => Record<string, { selector?: string }[]> | undefined;
}
const jq = () => (window as unknown as { require?: unknown; jQuery?: JQueryish });

/** Knockout has bound the drawer's control `el` (its click goes through jQuery). */
function bound(el: Element): boolean {
  const w = jq();
  if (!w.require) return true;
  return Boolean(w.jQuery?._data?.(el, "events")?.click);
}

const drawerLine = (path: string) =>
  [...document.querySelectorAll<HTMLElement>("aside.content-minicart-modal._show #minicart-content-wrapper .mc-line")].find((l) =>
    samePath(l.querySelector<HTMLAnchorElement>(".mc-line__name a")?.href ?? "", path),
  ) ?? null;

const bagRow = (path: string) =>
  [...document.querySelectorAll<HTMLElement>("tbody.cart.item")].find((r) => samePath(r.querySelector<HTMLAnchorElement>(".product-item-name a")?.href ?? "", path)) ??
  null;

/** The bag's line for `path` as the store's cart section has it, polled
 *  until `done` holds or `ms` passes; the last read either way. */
async function lineUntil(path: string, done: (qty: number) => boolean, ms: number): Promise<{ cart: CartState; qty: number }> {
  const until = Date.now() + ms;
  for (;;) {
    const cart = await readCart();
    const qty = cart.items.find((i) => samePath(i.path, path))?.qty ?? 0;
    if (done(qty) || Date.now() > until) return { cart, qty };
    await sleep(600);
  }
}

/** The page's form key, as the site's own forms post it. */
const formKey = () =>
  [...document.querySelectorAll<HTMLInputElement>("input[name=form_key]")].map((i) => i.value).find(Boolean) ||
  decodeURIComponent(document.cookie.match(/(?:^|;\s*)form_key=([^;]+)/)?.[1] ?? "");

/** Set bag line `id` to `qty`, or remove it with 0, with the request the
 *  drawer's own − / + and Aceptar send (same origin, the page's form key). */
async function sendLine(id: string, qty: number): Promise<void> {
  const key = formKey();
  if (!key) throw new Error("the page has no form key; nothing was changed");
  const body = new URLSearchParams(qty === 0 ? { item_id: id, form_key: key } : { item_id: id, item_qty: String(qty), form_key: key });
  const res = await fetch(qty === 0 ? "/checkout/sidebar/removeItem/" : "/checkout/sidebar/updateItemQty/", {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-Requested-With": "XMLHttpRequest", "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", Accept: "application/json" },
    body: body.toString(),
  });
  const answer = (await res.json().catch(() => null)) as { success?: boolean; error_message?: string } | null;
  if (!res.ok || !answer?.success) throw new Error(`the store did not take the change${answer?.error_message ? `: ${answer.error_message}` : ""}; nothing was changed`);
}

/** The drawer, opened as the visitor would (the bag button, ringed first),
 *  with its lines up. */
async function openDrawer(c: MoveContext): Promise<void> {
  if (!minicartOpen()) {
    const trigger = [...document.querySelectorAll<HTMLElement>(".minicart-wrapper a.action.showcart")].find(shown);
    if (!trigger) throw new Error("this page has no bag button");
    await scrollToTopOfPage();
    await ring(c, trigger);
    // Before the drawer's script is up, the same press loads the bag page,
    // which is the bag too.
    press(trigger);
    if (!(await waitFor(minicartOpen, 4000))) throw new Error("the bag drawer did not open");
  }
  await quiet(document.querySelector("#minicart-content-wrapper") ?? document.body, 300, 1500);
}

/**
 * Set the bag line of `path` to `qty`, or take it out with 0, as the visitor
 * would: in the drawer (− and + post the line's new quantity by AJAX; the
 * bin asks "¿Seguro…?" and its Aceptar removes the line), or, on the bag page
 * (/checkout/cart), with that same request and the reload the page's own
 * controls make; the move is checked on the page it loads. The line is found
 * by its product link, never by its words, and ringed before it changes.
 * Reports `cart_state`.
 */
async function updateCartItem(p: { path: string; qty: number; steps?: number; name?: string } & Arrived, c: MoveContext): Promise<string | null> {
  if (typeof p.path !== "string" || !p.path.trim()) c.refuse("path", "say which bag line, as its product path like /x.html");
  const qty = Math.round(Number(p.qty));
  if (!Number.isFinite(qty) || qty < 0 || qty > 10) c.refuse("qty", `a quantity from 0 (take it out) to 10, not ${p.qty}`);
  const path = productPath(p.path);
  const steps = Number(p.steps) || 0;
  const now = await lineUntil(path, () => true, 0);
  const line = now.cart.items.find((i) => samePath(i.path, path));
  const name = line?.name || p.name || path;
  const finished = async (cart: CartState, said: string) => {
    reportCart(cart);
    const row = kindOf() === "cart" ? bagRow(path) : drawerLine(path);
    if (row) await ring(c, row);
    return `${said}; ${cartLine(cart)}`;
  };
  if (!line) {
    // Back from the press that took it out: done.
    if (p.arrived && qty === 0) return finished(now.cart, `took ${name} out of the bag`);
    const has = now.cart.items.map((i) => `${i.name} (${i.path}) ×${i.qty}`);
    c.refuse("path", `${path} is not in the bag; ${has.length ? `the bag has ${has.join("; ")}` : "the bag is empty"}`, now.cart.items.map((i) => i.path));
  }
  if (line.qty === qty) {
    return finished(now.cart, p.arrived ? `set ${name} to ${qty} in the bag` : `${name} already has ${qty} in the bag; nothing changed`);
  }
  if (steps >= MAX_CART_STEPS) throw new Error(`the bag line of ${name} has ${line.qty}, not ${qty}, after ${steps} presses`);
  const rest = (): Then => ({ move: c.move, args: { path, qty, name, steps: steps + 1, arrived: true } });

  if (kindOf() === "checkout") {
    // The checkout's own summary has no controls: the bag page does.
    return load(c, "/checkout/cart/", rest());
  }

  if (kindOf() === "cart") {
    // The bag page. Its − and + post the line's new quantity to the same
    // endpoint the drawer uses and reload the page, and its Quitar is a
    // `data-post` link; but live, after the first of those reloads, the page's
    // own handlers stop answering (2026-10-23: − ignored, Quitar followed
    // `href="#"`). So the row is shown, its id read off it, and the change
    // sent as the drawer sends it, once, whatever the step; then the page
    // reloads as the site's own controls do, and the move is checked there.
    const row = await waitFor(() => bagRow(path), 8000);
    if (!row) throw new Error(`the bag page shows no row for ${name}`);
    const id = row.querySelector<HTMLElement>("[data-cart-item]")?.dataset.cartItem ?? row.querySelector<HTMLElement>("[data-item-id]")?.dataset.itemId;
    if (!id) throw new Error(`the bag page's row for ${name} has no line id`);
    await scrollTo(row, "center");
    await ring(c, row.querySelector(qty === 0 ? "a.action-delete" : ".control.qty") ?? row);
    await sendLine(id, qty);
    return load(c, location.pathname + location.search, rest());
  }

  // Any other page: the drawer. Pressed before its script is up, the bag
  // button loads the bag page instead, which carries the move on.
  await c.keep(rest());
  await openDrawer(c);
  await c.drop();
  const el = await waitFor(() => drawerLine(path), 8000);
  // The drawer is still drawing the bag from before (live, right after an
  // add): the bag page always shows it, so the move carries on there.
  if (!el) return load(c, "/checkout/cart/", rest());
  await scrollTo(el, "center");
  await ring(c, el);
  if (qty === 0) {
    const bin = el.querySelector<HTMLElement>("a.mc-line__remove, .action.delete");
    if (!bin) throw new Error(`the drawer's line for ${name} has no Eliminar`);
    if (!(await waitFor(() => bound(bin), 10_000))) throw new Error("the bag drawer's own scripts did not start; nothing was removed");
    press(bin);
    // "¿Seguro que desea eliminar este artículo…?" — its Aceptar removes it.
    const accept = await waitFor(() => document.querySelector<HTMLElement>("aside.modal-popup.confirm._show button.action-accept"), 4000);
    // Taking the line out may reload the page: the rest is kept for it.
    await c.keep(rest());
    if (accept) {
      await ring(c, accept);
      press(accept);
    }
    const after = await lineUntil(path, (n) => n === 0, 12_000);
    await c.drop();
    if (after.qty !== 0) throw new Error(`pressed Eliminar on ${name}, but it is still in the bag`);
    return finished(after.cart, `took ${name} out of the bag`);
  }
  let have = line.qty;
  for (let guard = steps; have !== qty && guard < MAX_CART_STEPS; guard++) {
    const button = el.isConnected ? el : drawerLine(path);
    const step = button?.querySelector<HTMLElement>(qty > have ? ".mc-qty__btn.btn-plus" : ".mc-qty__btn.btn-min");
    if (!step) throw new Error(`the drawer's line for ${name} has no ${qty > have ? "+" : "−"} button`);
    if (!(await waitFor(() => bound(step), 10_000))) throw new Error("the bag drawer's own scripts did not start; nothing was changed");
    const was = have;
    press(step);
    have = (await lineUntil(path, (n) => n !== was, 10_000)).qty;
    if (have === was) throw new Error(`pressed ${qty > was ? "+" : "−"} on ${name} in the drawer, but the bag still has ${was}`);
  }
  const after = await lineUntil(path, () => true, 0);
  if (have !== qty) throw new Error(`the bag line of ${name} has ${have}, not ${qty}`);
  return finished(after.cart, `set ${name} to ${qty} in the bag (it had ${line.qty})`);
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

type FillCheckout = Partial<Record<FillKey, string | null>> & Arrived;

/** Take the visitor to the delivery form, then fill it with `fill`, if given.
 *  From any page: the bag first; on the bag, "Terminar pedido", then the login
 *  window's "Comprar como invitado" (a link to /checkout). Each load carries
 *  the rest of the move (`args`, this move's own) to the next page. */
async function toCheckout(c: MoveContext, args: Arrived & Record<string, unknown>, fill: FillCheckout | null): Promise<string | null | PerformResult> {
  if (onCheckout()) {
    const form = await waitFor(formReady, 20_000);
    if (!form) throw new Error("the checkout opened, but its delivery form did not show");
    if (/payment/i.test(location.hash)) throw new Error("the checkout is at its payment step, which is the visitor's");
    if (fill) return fillCheckout({ ...fill, arrived: true }, c);
    await scrollTo(emailForm() ?? form, "top");
    await ring(c, emailForm() ?? form);
    reportCheckout();
    return `the guest checkout's delivery form is open (${describeCheckout(readCheckout())})`;
  }
  if (args.arrived) throw new Error(`the checkout did not open (now on ${location.pathname}); the bag may be empty`);
  if (kindOf() !== "cart") return load(c, "/checkout/cart/", { move: c.move, args });
  if (!document.querySelector("tbody.cart.item") && document.querySelector(".cart-empty")) throw new Error("the bag is empty; there is nothing to check out");
  const button = await waitFor(() => [...document.querySelectorAll<HTMLElement>("button[data-role='proceed-to-checkout']")].find(shown), 8000);
  if (!button) throw new Error("the bag page has no Terminar pedido button");
  // The window "Terminar pedido" opens is Knockout's: pressed before it has
  // rendered, it opens empty.
  await waitFor(() => document.querySelector("#block-login a[href]"), 10_000);
  await scrollTo(button, "center");
  await ring(c, button);
  press(button);
  const guest = await waitFor(
    () =>
      [...document.querySelectorAll<HTMLAnchorElement>("aside.login-modal._show a[href]")].find((a) => {
        const to = new URL(a.href, location.href);
        return /^\/checkout\/?$/i.test(to.pathname) && shown(a);
      }),
    12_000,
  );
  const there: Then = { move: c.move, args: { ...args, arrived: true } };
  // The window did not render its links: "Comprar como invitado" is only
  // this link.
  if (!guest) return load(c, "/checkout", there);
  await ring(c, guest);
  await c.keep(there);
  press(guest);
  return null;
}

function describeCheckout(s: CheckoutState): string {
  const names = (keys: string[]) => keys.map((k) => FIELD_LABEL[k] ?? k).join(", ");
  const bits = [s.filled.length ? `filled: ${names(s.filled)}` : "nothing filled yet"];
  if (s.missing.length) bits.push(`missing: ${names(s.missing)}`);
  if (s.invalid.length) bits.push(`the form flags ${s.invalid.map((i) => `${FIELD_LABEL[i.field] ?? i.field} ("${i.message}")`).join(", ")}`);
  return bits.join("; ");
}

async function startCheckout(p: Arrived, c: MoveContext): Promise<string | null | PerformResult> {
  return toCheckout(c, { ...p }, null);
}

/** Type `value` into one of the form's own text fields, ringed first, as a
 *  finished edit (Knockout's `value` binding updates on `change` and
 *  `keyup`), unless the field is the visitor's alone or the value does not
 *  fit it. */
async function fillField(c: MoveContext, el: HTMLInputElement, value: string, label: string): Promise<void> {
  const why = privateField(el);
  if (why) throw new Error(`refused ${label}: ${why}`);
  const max = el.maxLength > 0 ? el.maxLength : Infinity;
  if (value.length > max) throw new Error(`${label} takes at most ${max} characters`);
  await scrollTo(el, "center");
  await ring(c, el.closest(".field") ?? el);
  el.focus({ preventScroll: true });
  setValue(el, value);
  el.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true, key: "Unidentified" }));
  if (el.value !== value) throw new Error(`${label} did not take what was typed (it shows ${el.value.length} characters)`);
}

/** Pick `said` in the form's región or comuna list (its own searchable
 *  dropdown), ringed first; the comuna's list loads by AJAX once a región is
 *  chosen. */
async function pick(c: MoveContext, key: "region" | "comuna", said: string): Promise<string> {
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
  await ring(c, box);
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
async function phonePrefix(c: MoveContext, first: string): Promise<void> {
  const box = shippingForm()?.querySelector<HTMLElement>(".field.telephone .flag-container");
  if (!box) return;
  const want = `56 ${first}`;
  const now = clean(box.querySelector(".iti-flag, .selected-flag")?.textContent).replace(/^\+/, "");
  if (now === `+${want}` || now === want) return;
  const flag = box.querySelector<HTMLElement>(".selected-flag");
  if (!flag) throw new Error("the phone field has no prefix to choose");
  // A visible change: rung first, like every other press.
  await ring(c, box.closest(".field") ?? box);
  press(flag);
  const li = await waitFor(() => box.querySelector<HTMLElement>(`li.country[data-dial-code="${want}"]`), 3000);
  if (!li) throw new Error(`the phone field has no +${want} prefix`);
  press(li);
  if (!(await waitFor(() => clean(box.querySelector(".iti-flag, .selected-flag")?.textContent).replace(/^\+/, "") === want, 2000))) {
    throw new Error(`the phone prefix did not change to +${want}`);
  }
}

async function fillCheckout(p: FillCheckout, c: MoveContext): Promise<string | null | PerformResult> {
  const given = FILL_ORDER.filter((k) => typeof p[k] === "string" && p[k]!.trim());
  if (!given.length) c.refuse("fields", "say what to fill: email, región, comuna, dirección, número, depto/casa, nombre, apellidos or teléfono", [...FILL_ORDER]);
  if (!onCheckout()) {
    const fill: FillCheckout = {};
    for (const k of given) fill[k] = p[k]!;
    return toCheckout(c, { ...p }, fill);
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
        await fillField(c, el, value, label);
        touched.push(el);
      } else if (key === "region" || key === "comuna") {
        const name = await pick(c, key, value);
        touched.push(pickerOf(key)!);
        done.push(`${label} ${name}`);
        continue;
      } else if (key === "phone") {
        const digits = value.replace(/\D/g, "");
        if (!/^[92]\d{8}$/.test(digits)) throw new Error("a Chilean number is nine digits, starting with 9 or 2");
        await phonePrefix(c, digits[0]);
        const el = form.querySelector<HTMLInputElement>(TEXT_INPUTS.phone);
        if (!el) throw new Error("the form has no phone field");
        await fillField(c, el, digits.slice(1), label);
        touched.push(el.closest(".field") ?? el);
      } else {
        const el = form.querySelector<HTMLInputElement>(TEXT_INPUTS[key]);
        if (!el) throw new Error(`the form has no ${label} field`);
        await fillField(c, el, value, label);
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
  if (touched.length) await ring(c, touched);
  if (!done.length) throw new Error(`nothing was filled: ${failed.join("; ")}`);
  const detail = `filled ${done.join(", ")}${failed.length ? `; not filled: ${failed.join("; ")}` : ""}; ${describeCheckout(state)}; nothing was pressed after the fields`;
  // Some fields but not all: partial, so it is never taken for the whole form.
  return failed.length ? { outcome: "partial", detail } : detail;
}

// The page, show and faq cues ───────────────────────────────────────────────

/** The page cue: open `path` at its top, its link on this page ringed first
 *  when it has one; on it already, its top. */
async function openPage(p: { path: string }, c: MoveContext): Promise<string | null> {
  if (typeof p.path !== "string" || !p.path.trim()) c.refuse("path", "say which page to go to, as a path");
  const to = new URL(p.path.trim(), location.origin);
  if (!samePath(location.pathname, to.pathname) || (to.search && to.search !== location.search)) {
    target(to.pathname + to.search + to.hash);
    const link = linkTo(to.pathname);
    if (link) await ring(c, link);
    return load(c, to.pathname + to.search + to.hash);
  }
  await scrollToTopOfPage();
  const title = headings()[0]?.el;
  if (title) await ring(c, title);
  return `${location.pathname} is on screen`;
}

/** On `path` first, when the cue names another page: the rest goes there. */
async function onPage(c: MoveContext, path: string | null | undefined, then: Then): Promise<boolean> {
  if (!path || samePath(location.pathname, new URL(path, location.origin).pathname)) return true;
  await load(c, path, then);
  return false;
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

/** The show cue: a heading of the page, scrolled to and ringed with what it
 *  heads; or, when no heading is called that, the smallest block with those
 *  words. */
async function showSection(p: { target: string; path?: string | null }, c: MoveContext): Promise<string | null> {
  const want = clean(p.target);
  if (!want) c.refuse("target", "say which heading or words to show");
  if (!(await onPage(c, p.path, { move: c.move, args: { target: want, path: null } }))) return null;
  const h = findHeading(want);
  if (h) {
    const section = sectionOf(h);
    const box = boxOf(section);
    const height = box ? box.bottom - box.top : Infinity;
    const room = window.innerHeight - headerHeight() - 32;
    await scrollTo(height <= room ? section[0] : h, height <= room ? "center" : "top");
    await ring(c, height > window.innerHeight * 1.3 ? h : section);
    return `showed "${clean(h.textContent)}"`;
  }
  const el = smallestContaining(main(), want);
  if (!el) c.refuse("target", `no heading or words "${want}" on ${location.pathname}`, context().headings.slice(0, 25));
  await scrollTo(el, el.getBoundingClientRect().height > window.innerHeight * 0.7 ? "top" : "center");
  await ring(c, el);
  return `showed "${want}"`;
}

/** The faq cue: the question ringed, opened, and ringed with its answer. */
async function openFaq(p: { question: string; path?: string | null }, c: MoveContext): Promise<string | null> {
  const question = clean(p.question);
  if (!question) c.refuse("question", "say which question");
  if (!(await onPage(c, p.path, { move: c.move, args: { question, path: null } }))) return null;
  const all = faqItems();
  const item = best(all, (f) => f.question, question) ?? best(all, (f) => original(f.block), question);
  if (!item) c.refuse("question", `no FAQ "${question}" on ${location.pathname}`, all.map((f) => f.question).slice(0, 15));
  await scrollTo(item.block, "center");
  if (!item.isOpen() && item.toggle) {
    await ring(c, item.block);
    press(item.toggle);
    await waitFor(item.isOpen, 2000);
    await sleep(300);
  }
  const group = [item.block, ...item.answer()];
  const box = boxOf(group);
  await scrollTo(item.block, box && box.bottom - box.top > window.innerHeight * 0.7 ? "top" : "center");
  await ring(c, group);
  return `opened "${item.question}"`;
}

// ─── Registering the moves ────────────────────────────────────────────────

/** Every move this page makes, by the id the brain names it with: its class,
 *  a cue's argument names and the arguments' types come from
 *  `cannonhome/scene.json`, and a move left out does not compile. */
export function registerMoves(moves: Moves): void {
  scene.registerAll(moves, {
    "page.open": asAgent(openPage),
    "page.show": asAgent(showSection),
    "page.faq": asAgent(openFaq),
    "commerce.filter": asAgent(filterCue),
    "commerce.sort": asAgent(sortCue),
    "commerce.search": asAgent(searchProducts),
    filter_listing: asAgent(filterListing),
    open_product: asAgent(openProduct),
    product_tab: asAgent(productTab),
    check_prices: asAgent(checkPrices),
    "commerce.cart_show": asAgent(showCart),
    "commerce.cart_add": asAgent(addToCart),
    "commerce.cart_update": asAgent(updateCartItem),
    start_checkout: asAgent(startCheckout),
    fill_checkout: asAgent(fillCheckout),
  });
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

/** Report the page and the state on it through `next`, as it changes, until
 *  the returned stop: from the moment the agent can hear this page. */
export function start(next: (event: string, payload: unknown) => void): () => void {
  emitter = next;
  lastUrl = location.origin + location.pathname + location.search;
  for (const [event, payload] of latest) report(event, payload);
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

let prepared = false;

/** Ready the page, once: its style, the URL watch, and its state read as soon
 *  as it settles (a page that loads mid-call reports it the moment it listens). */
export function prepare(): void {
  if (prepared) return;
  prepared = true;
  styleThePage();
  watchUrl();
  void settled().then(readState);
}

/** The page in front, as it stands: once the agent can hear this page (before
 *  `start`), and again each time the tab comes back to the front (Stage's
 *  host runs it). */
export function reportPage(next: (event: string, payload: unknown) => void): void {
  next("page_changed", context());
}

/** Cannon Home's adapter for `@voqalize/stage/extension`: its moves, what the
 *  visitor is looking at for the session's start, and its reports. */
export const cannonhome: Adapter = (moves) => {
  registerMoves(moves);
  prepare();
  return {
    context: () => {
      const ctx = context();
      return { site: ctx.site, path: ctx.path, url: ctx.url, title: ctx.title };
    },
    report: reportPage,
    start,
    // The store's own scripts bind late, and its `load` waits on trackers
    // for over 15 s: a press waits for the page to settle, never for `load`.
    ready: settled,
  };
};

// Exported for the end-to-end tests.
export { context, readCart, readListing, readProduct, readSuggest };
