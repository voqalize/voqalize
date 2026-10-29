/**
 * The site adapter: drive www.pcfactory.cl from the outside, with no help from
 * pcFactory's developers.
 *
 * Javier's moves arrive through Stage (`@voqalize/stage`): each is a move
 * registered here (`registerMoves`), made on the page in front, one at a
 * time, ringed with the spotlight before it acts, and answered with one
 * `stage_result`. The page reports what it shows through `start`, which calls
 * `emit(event, payload)`, whoever moved it:
 *
 *   - `page_changed` for every page the visitor lands on, whoever took them;
 *   - `prices_read`, `products_found`, `stock_read`, `store_shown` and
 *     `compare_shown` for the moves that read them.
 *
 * What their screen holds is Stage state (`pcfactory/scene.json`): each change
 * goes as a named `stage_event` (`scene.event`), with only the fields its
 * slice declares, and `by: "agent"` with the move's `call_ref` when one of
 * Javier's moves made it:
 *
 *   - `product.shown` on a product page, read from the page at once, then
 *     `product.checked` from the store's own API (`/productos/{id}`, its
 *     `/precio` and `/stock`), because the HTML is cached at the edge;
 *   - `listing.shown` on a category or search listing, and `listing.filtered`
 *     / `listing.sorted` after the grid changes on the same listing, whoever
 *     changed it;
 *   - `cart.changed` whenever the cart (`localStorage.cartProducts`) changes;
 *   - `checkout.changed` on the checkout's first step and on Tipo de entrega.
 *
 * The site, for a script like this: Modyo pages with Vue 2 widgets (the
 * filters and grid, the product page, the cart, the checkout, the comparator,
 * the "Producto agregado" window) over a public API at `api.pcfactory.cl`
 * (CORS `*`), which the reads here call too. Moving between pages is a full
 * load, so a move to another page carries the rest of itself to it (`load`,
 * `keep`), and the next page finishes it with the same call. Filters, sort,
 * add-to-cart and the cart's − / + stay in the page.
 *
 * Nothing here goes past Tipo de entrega: every click goes through `press`,
 * every load through `target`, every keystroke through `typeInto` (`page.ts`).
 * They let Javier take a guest from the cart to Tipo de entrega ("Continuar",
 * then "Continuar como invitado"), and refuse every login, the delivery
 * choice, the payment and any field but the search and coupon boxes.
 */

import type { MoveContext, Moves, PerformResult, Refusal, StageEvent } from "@voqalize/stage";
import type { Adapter } from "@voqalize/stage/extension";

import type { CompareShown, PricesRead, ProductsFound, StockRead, StoreShown } from "./actions.gen";
import { scene } from "./scene.gen";

import {
  apiSettled, best, boxOf, checkoutStep, clean, headerHeight, inOrder, money, norm, pathOf, press, productId, productPath, quiet,
  samePath, scrollTo, scrollToTopOfPage, setRange, settled, shown, sleep, styleThePage, target, typeInto, visible, waitFor, watchApi,
} from "./page";

export type Kind = "home" | "category" | "search" | "product" | "cart" | "checkout" | "stores" | "help" | "page";
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

const SITE_NAME = "www.pcfactory.cl";
const API = "https://api.pcfactory.cl/pcfactory-services-catalogo/v1/catalogo";
const CART_API = "https://api.pcfactory.cl/pcfactory-services-carro-compra/v1/carro";
const MAX_HEADINGS = 80;
const MAX_FAQS = 120;
const MAX_LISTED = 12;
const MAX_OPTIONS = 25;
const MAX_SPECS = 40;
const MAX_FOUND = 8;
const MAX_PRICED = 6;
/** The comparator's own limit: "Comparador (3/3)". */
const MAX_COMPARED = 3;
const REPORT_DEBOUNCE_MS = 450;

// ─── Where we are ─────────────────────────────────────────────────────────

/** What sort of page this is, from Modyo's body classes (which no translator
 *  touches), else from the path. */
export function kindOf(): Kind {
  const b = document.body?.classList;
  const p = location.pathname.toLowerCase().replace(/\/+$/, "") || "/";
  if (b?.contains("context-home") || p === "/") return "home";
  if (b?.contains("context-custom-show-producto") || p.startsWith("/producto/")) return "product";
  if (b?.contains("context-custom-show-categoria") || p.startsWith("/categoria/")) return "category";
  if (b?.contains("context-custom-show-busqueda-avanzada") || p === "/busqueda-avanzada") return "search";
  if (b?.contains("context-custom-show-carro") || p === "/carro") return "cart";
  if (b?.contains("context-custom-show-checkout") || p.startsWith("/checkout")) return "checkout";
  if (b?.contains("context-custom-show-tiendas") || p === "/tiendas") return "stores";
  if (p.startsWith("/centro-de-ayuda")) return "help";
  return "page";
}

/** The page's content: Modyo's main layout. */
const main = (): HTMLElement => document.querySelector<HTMLElement>("#main-layout") ?? document.body;

/** Not the page's content: the header and footer, the site's windows, the
 *  comparator, the assistance button, the help centre's topic menu, and our
 *  own. */
const CHROME = [
  "header#header", "#header", "footer", ".modal", "#pcf-comparator-summary", "#pcfAssistanceWrapper", "[id^=ocular]",
  "#categories-dropdown", ".menu-wrapper", "#huincha_cyber", "#tag-express-sale", "#accordionMainFAQ", "[data-voqalize]",
].join(", ");
const inChrome = (el: Element) => Boolean(el.closest(CHROME));

/** Things the adapter matches by their own kind (cards, rows), not as headings. */
const NOT_HEADINGS = "#panel-filters, a.products__item, .rr-item, .card-list-product, #specifics, .ticket-col, .card-tabs, .accordion-button, #comparator, .step";

interface Faq {
  question: string;
  block: HTMLElement;
  toggle: HTMLElement | null;
  isOpen: () => boolean;
  answer: () => HTMLElement[];
}

/** The page's FAQs: the event pages' accordions (a button holding the
 *  question, its answer a Bootstrap collapse), and the help centre's
 *  questions, headings that ask one, with the blocks up to the next heading
 *  as the answer. */
function faqItems(): Faq[] {
  const root = main();
  const items: Faq[] = [];
  for (const t of root.querySelectorAll<HTMLElement>(".accordion-button, [data-toggle=collapse], [data-bs-toggle=collapse]")) {
    if (inChrome(t) || t.closest("#panel-filters")) continue;
    const question = clean(t.innerText || t.textContent);
    if (!/\?\s*$/.test(question)) continue;
    const sel = t.getAttribute("data-target") ?? t.getAttribute("data-bs-target") ?? (t.getAttribute("aria-controls") ? `#${t.getAttribute("aria-controls")}` : "");
    let content: HTMLElement | null = null;
    try {
      content = sel ? document.querySelector<HTMLElement>(sel) : null;
    } catch {
      content = null;
    }
    items.push({
      question,
      block: t.closest<HTMLElement>(".accordion-item, .card") ?? t,
      toggle: t,
      isOpen: () => Boolean(content && (content.classList.contains("show") || shown(content))),
      answer: () => (content ? [content] : []),
    });
  }
  const known = new Set(items.map((i) => norm(i.question)));
  for (const h of root.querySelectorAll<HTMLElement>("h2, h3, h4, h5")) {
    if (inChrome(h) || h.closest("button, .accordion-button, a")) continue;
    const text = clean(h.innerText || h.textContent).replace(/^\d+[.)]\s*/, "");
    if (!(/\?\s*$/.test(text) || /^¿/.test(text)) || known.has(norm(text))) continue;
    items.push({ question: text, block: h, toggle: null, isOpen: () => true, answer: () => answerAfter(h) });
  }
  return items.sort((a, b) => inOrder(a.block, b.block));
}

/** The blocks after heading `h` up to the next heading. */
function answerAfter(h: HTMLElement): HTMLElement[] {
  const out: HTMLElement[] = [];
  for (let el = h.nextElementSibling; el && !el.matches("h1, h2, h3, h4, h5") && out.length < 8; el = el.nextElementSibling) {
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
    if (inChrome(h) || h.closest(NOT_HEADINGS) || !shown(h)) continue;
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
    site: SITE_NAME,
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

/** A state report (product, listing, cart, checkout): sent unless this
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

/** A read a move made (prices, products, stock, a store, the comparator):
 *  sent every time, since the brain asked for it. */
function told(event: string, payload: unknown): void {
  emitter?.(event, payload);
}

/** Who changed what the page reports now: the page kit's answer (his move
 *  acting, just done, or carried here and not yet made; else the visitor). */
let who: () => { by: "visitor" | "agent"; callRef?: string } = () => ({ by: "visitor" });

/** The listing last reported in this tab, kept across a load: a new report of
 *  the same one is a filter or a sort, not a new listing. */
const LAST_LISTING = "voqalize.pcfactory.listing";
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
      const p = payload as ProductState;
      ev = scene.event(p.source === "api" ? "product.checked" : "product.shown", p, by);
      break;
    }
    case "listing_shown": {
      const l = payload as ListingState;
      const filters = JSON.stringify([l.filters.map((f) => [f.facet, f.on]), l.price]);
      const sort = l.sort ?? "";
      const before = lastListing();
      const same = before !== null && before.path === l.path;
      const name = same && before.filters !== filters ? "listing.filtered" : same && before.sort !== sort ? "listing.sorted" : "listing.shown";
      sawListing({ path: l.path, filters, sort });
      const { price: _price, ...slice } = l;
      ev = scene.event(name, slice, by);
      break;
    }
    case "cart_state":
      ev = scene.event("cart.changed", payload as CartState, by);
      break;
    case "checkout_state":
      ev = scene.event("checkout.changed", payload as CheckoutState, by);
      break;
  }
  return ev ? ["stage_event", ev] : [event, payload];
}

// ─── The store's API ──────────────────────────────────────────────────────

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { credentials: "omit", ...init });
  if (!r.ok) throw new Error(`the store's API answered ${r.status} for ${new URL(url).pathname}`);
  return (await r.json()) as T;
}

interface ApiPrice {
  efectivo?: number | null;
  normal?: number | null;
  referencia?: number | null;
  promocion?: { termino?: string | null } | boolean | null;
}
interface ApiProduct {
  id: number;
  nombre?: string;
  marca?: { nombre?: string } | string;
  stock?: { aproximado?: string };
  especificaciones?: { grupo?: string; detalle?: { nombre?: string; valor?: string }[] }[];
  garantia?: { mesesDuracion?: number; plazo?: { descripcion?: string } };
}
interface ApiStock {
  disponibilidad?: { zona?: string; sucursales?: { nombre?: string; aproximado?: string; retiro?: boolean }[] }[];
}
interface ApiItem {
  id: number;
  nombre: string;
  marca?: string;
  stock?: string;
  precio?: ApiPrice;
}

const productApi = (id: number) => getJson<ApiProduct>(`${API}/productos/${id}`);
const priceApi = (id: number) => getJson<{ precio?: ApiPrice }>(`${API}/productos/${id}/precio`).then((r) => r.precio ?? {});
const stockApi = (id: number) => getJson<ApiStock>(`${API}/productos/${id}/stock`);

/** Pesos as integers; the API writes some as 1490.0000. */
const pesos = (n: unknown): number | null => (typeof n === "number" && Number.isFinite(n) && n > 0 ? Math.round(n) : null);
const brandOf = (m: ApiProduct["marca"]) => (typeof m === "string" ? m : (m?.nombre ?? null));

interface StockRow {
  name: string;
  zone: string;
  qty: string;
  pickup: boolean;
}

function stockRows(s: ApiStock): { online: string | null; stores: StockRow[] } {
  let online: string | null = null;
  const stores: StockRow[] = [];
  for (const z of s.disponibilidad ?? []) {
    for (const x of z.sucursales ?? []) {
      const name = clean(x.nombre);
      const qty = clean(x.aproximado) || "0";
      if (/^internet$/i.test(name)) online = qty;
      else stores.push({ name, zone: clean(z.zona), qty, pickup: x.retiro !== false });
    }
  }
  return { online, stores };
}

// ─── The stores ───────────────────────────────────────────────────────────

/** pcFactory's 28 stores (/tiendas and the stock API, 2026-10-29): the name
 *  the stock list writes, the name the store page writes where it differs, the
 *  comuna or city, the region, and the store page's zone tab. Used to match
 *  what the visitor calls a store ("el de Costanera", "en Maipú"). */
const STORES: [stock: string, page: string | null, city: string, region: string, zone: string][] = [
  ["Calama (Mall Plaza)", null, "Calama", "Antofagasta", "Norte"],
  ["Antofagasta", null, "Antofagasta", "Antofagasta", "Norte"],
  ["Copiapó", "Mall Plaza Copiapó", "Copiapó", "Atacama", "Norte"],
  ["La Serena", null, "La Serena", "Coquimbo", "Norte"],
  ["Viña del Mar", null, "Viña del Mar", "Valparaíso", "Norte"],
  ["Cantagallo", null, "Vitacura", "Región Metropolitana", "Santiago"],
  ["Huérfanos", null, "Santiago Centro", "Región Metropolitana", "Santiago"],
  ["Las Condes", null, "Las Condes", "Región Metropolitana", "Santiago"],
  ["Manuel Montt", null, "Providencia", "Región Metropolitana", "Santiago"],
  ["Mall Arauco Maipú", null, "Maipú", "Región Metropolitana", "Santiago"],
  ["Mall Costanera Center", "Mall Cenco Costanera", "Providencia", "Región Metropolitana", "Santiago"],
  ["Mall Plaza Norte", null, "Huechuraba", "Región Metropolitana", "Santiago"],
  ["Mall Plaza Oeste", null, "Cerrillos", "Región Metropolitana", "Santiago"],
  ["Mall Florida Center", "Mall Cenco Florida", "La Florida", "Región Metropolitana", "Santiago"],
  ["Mall Plaza Vespucio", null, "La Florida", "Región Metropolitana", "Santiago"],
  ["Open Kennedy", null, "Las Condes", "Región Metropolitana", "Santiago"],
  ["Mall Plaza Egaña", null, "La Reina", "Región Metropolitana", "Santiago"],
  ["Vitacura", null, "Vitacura", "Región Metropolitana", "Santiago"],
  ["Curicó", null, "Curicó", "Maule", "Sur"],
  ["Talca", null, "Talca", "Maule", "Sur"],
  ["Chillán", null, "Chillán", "Ñuble", "Sur"],
  ["Talcahuano (Mall Trébol)", null, "Talcahuano", "Biobío", "Sur"],
  ["Concepción", null, "Concepción", "Biobío", "Sur"],
  ["Los Ángeles", null, "Los Ángeles", "Biobío", "Sur"],
  ["Temuco", null, "Temuco", "Araucanía", "Sur"],
  ["Valdivia", null, "Valdivia", "Los Ríos", "Sur"],
  ["Osorno", null, "Osorno", "Los Lagos", "Sur"],
  ["Puerto Montt", "Puerto Montt Mall Paseo Costanera", "Puerto Montt", "Los Lagos", "Sur"],
];

const storeRow = (name: string) => STORES.find((s) => norm(s[0]) === norm(name) || (s[1] !== null && norm(s[1]) === norm(name))) ?? null;

/**
 * The stores among `names` that `said` means: a store's own name (either the
 * stock list's or the store page's), else a zone ("Santiago", "Sur"), else a
 * comuna or city, else a store whose name holds the words. Accents and case
 * fold away.
 */
function storesMeant(said: string, names: string[]): string[] {
  const want = norm(said).replace(/^(la |el )?(tienda|sucursal|store)( de| en)? /, "").replace(/^(mall|en|de) /, (m) => (m === "mall " ? m : ""));
  if (!want) return [];
  const aliases = names.map((n) => ({ n, all: [n, storeRow(n)?.[1] ?? ""].filter(Boolean) }));
  const exact = aliases.filter((a) => a.all.some((x) => norm(x) === want));
  if (exact.length) return exact.map((a) => a.n);
  const zone = names.filter((n) => norm(storeRow(n)?.[4] ?? "") === want);
  if (zone.length) return zone;
  const city = names.filter((n) => {
    const c = norm(storeRow(n)?.[2] ?? "");
    return c && (c === want || want.includes(c) || c.startsWith(want));
  });
  if (city.length) return city;
  const words = aliases.filter((a) => a.all.some((x) => norm(x).includes(want) || (want.length > 4 && want.includes(norm(x)))));
  return words.map((a) => a.n);
}

// ─── The product page ─────────────────────────────────────────────────────

interface ProductState {
  path: string;
  id: number | null;
  name: string;
  brand: string | null;
  price: number | null;
  card_price: number | null;
  regular_price: number | null;
  online_stock: string | null;
  stores_with_stock: number | null;
  warranty: string | null;
  promo_until: string | null;
  specs: { label: string; value: string }[];
  source: "page" | "api";
}

const onProductPage = () => kindOf() === "product";

/** The specifications table (the Especificaciones tab, rendered even while
 *  hidden): label → value, in order. */
function specRows(): { row: HTMLElement; label: string; value: string }[] {
  const out: { row: HTMLElement; label: string; value: string }[] = [];
  for (const row of document.querySelectorAll<HTMLElement>("#specifics tr")) {
    const cells = row.querySelectorAll("td");
    const label = clean(row.querySelector("td strong")?.textContent ?? cells[0]?.textContent);
    const value = clean(cells[cells.length - 1]?.textContent);
    if (label && value && cells.length >= 2) out.push({ row, label, value });
  }
  return out;
}

/** The Disponibilidad list's rows: Internet first, then every store. */
function stockList(): { el: HTMLElement; name: string; qty: string }[] {
  const out: { el: HTMLElement; name: string; qty: string }[] = [];
  for (const p of document.querySelectorAll<HTMLElement>("#stock .stock__list__zone, #stock .stock__list__location")) {
    const bullets = p.querySelector(".bullets");
    if (bullets) out.push({ el: p, name: clean(bullets.textContent), qty: clean(p.querySelector("strong")?.textContent) || "0" });
    else if (p.classList.contains("stock__list__zone")) {
      const spans = p.querySelectorAll("span");
      if (spans.length >= 2) out.push({ el: p, name: clean(spans[0]!.textContent), qty: clean(spans[spans.length - 1]!.textContent) });
    }
  }
  return out;
}

function readProduct(): ProductState | null {
  if (!onProductPage()) return null;
  const nameEl = document.querySelector("#product-title .product-title__product-name");
  if (!nameEl) return null;
  const id = productId(location.pathname) ?? (Number(clean(document.querySelector(".detail__info__id strong")?.textContent)) || null);
  const price = money(document.querySelector(".detail__prices__cash")?.textContent);
  const ref = money(document.querySelector(".detail__prices__reference")?.textContent);
  const list = stockList();
  const online = list.find((r) => /^internet$/i.test(r.name));
  const warrantyText = clean(document.querySelector("#warranty")?.textContent);
  const months = warrantyText.match(/fabricante de\s+(\d+)\s+meses/i);
  const expiry = clean(document.querySelector(".detail__expiry-date")?.textContent).match(/\bal\s+\S+\s+(\d{2}\/\d{2}\/\d{4}(?:\s+\d{2}:\d{2})?)/i);
  return {
    path: id ? productPath(id) : location.pathname,
    id,
    name: clean(nameEl.textContent),
    brand: clean(document.querySelector("#product-title .product-title__product-brand")?.textContent) || null,
    price,
    card_price: money(document.querySelector(".detail__prices__normal")?.textContent),
    regular_price: ref != null && price != null && ref > price ? ref : null,
    online_stock: online?.qty ?? null,
    stores_with_stock: list.length ? list.filter((r) => !/^internet$/i.test(r.name) && r.qty !== "0").length : null,
    warranty: months ? `Garantía del fabricante de ${months[1]} meses` : warrantyText ? warrantyText.replace(/^Plazo\s*/i, "").split(/(?<=\.)\s/)[0]!.slice(0, 120) : null,
    promo_until: expiry ? expiry[1]! : null,
    specs: specRows()
      .slice(0, MAX_SPECS)
      .map(({ label, value }) => ({ label, value })),
    source: "page",
  };
}

/** The store's live read of product `id`. */
async function productFromApi(id: number): Promise<ProductState> {
  const [p, price, stock] = await Promise.all([productApi(id), priceApi(id), stockApi(id).catch(() => ({}) as ApiStock)]);
  const rows = stockRows(stock);
  const cash = pesos(price.efectivo);
  const ref = pesos(price.referencia);
  const months = p.garantia?.mesesDuracion;
  const promo = typeof price.promocion === "object" && price.promocion ? price.promocion.termino : null;
  return {
    path: productPath(id),
    id,
    name: clean(p.nombre),
    brand: brandOf(p.marca),
    price: cash,
    card_price: pesos(price.normal),
    regular_price: ref != null && cash != null && ref > cash ? ref : null,
    online_stock: rows.online ?? p.stock?.aproximado ?? null,
    stores_with_stock: rows.stores.filter((s) => s.qty !== "0").length,
    warranty: months && months > 6 ? `Garantía del fabricante de ${months} meses` : (p.garantia?.plazo?.descripcion ?? null),
    promo_until: promo ? promo.replace(/:\d{2}(\.\d+)?$/, "") : null,
    specs: (p.especificaciones ?? [])
      .flatMap((g) => g.detalle ?? [])
      .map((d) => ({ label: clean(d.nombre), value: clean(d.valor) }))
      .filter((d) => d.label && d.value)
      .slice(0, MAX_SPECS),
    source: "api",
  };
}

let confirming: Promise<void> | null = null;
/** product.checked for the product in front, once per page. */
function confirmProduct(): Promise<void> {
  const id = productId(location.pathname);
  if (!onProductPage() || !id) return Promise.resolve();
  confirming ??= productFromApi(id)
    .then((p) => {
      if (productId(location.pathname) === id) report("product_shown", p);
    })
    .catch(() => {
      confirming = null;
    });
  return confirming;
}

/** The live read wins over the page's once it is in. */
function latestProductFor(page: ProductState): ProductState {
  const live = latest.get("product_shown") as ProductState | undefined;
  return live?.source === "api" && live.path === page.path ? live : page;
}

// ─── Listings ─────────────────────────────────────────────────────────────

interface ListingItem {
  path: string;
  name: string;
  price: number | null;
  regular_price: number | null;
}
interface ListingFilter {
  facet: string;
  on: string[];
  options: string[];
}
interface ListingState {
  path: string;
  title: string;
  count: number | null;
  filters: ListingFilter[];
  sort: string | null;
  items: ListingItem[];
  /** The price range in the address, for telling a price filter from a sort;
   *  not part of the slice. */
  price: string;
}

const isListing = () => kindOf() === "category" || kindOf() === "search";
/** The listing's grid has rendered (the Vue widget fills it after load). */
const gridUp = () => cards().length > 0 || listingCount() === 0;
const gridSection = () =>
  document.querySelector<HTMLElement>('section[data-section-name="Lista productos"]') ?? document.querySelector<HTMLElement>("section.products");

/** The grid's cards, in order (the "Los favoritos" rail under it is not the
 *  listing). */
function cards(): HTMLAnchorElement[] {
  const grid = gridSection();
  return [...(grid ?? main()).querySelectorAll<HTMLAnchorElement>("a.products__item")].filter((a) => !a.closest(".rr-widget, .rr-item"));
}

function cardId(a: Element): number | null {
  const n = Number(clean(a.querySelector(".products__item__info__id strong")?.textContent));
  return Number.isInteger(n) && n > 0 ? n : productId(pathOf((a as HTMLAnchorElement).href));
}

const cardName = (a: Element) => clean(a.getAttribute("data-content-name") ?? a.querySelector("h3")?.textContent);

function cardItem(a: HTMLAnchorElement): ListingItem | null {
  const id = cardId(a);
  if (!id) return null;
  const price = money(a.querySelector("p.products__item__info__price")?.textContent);
  const ref = money(a.querySelector(".products__item__info__reference_price del")?.textContent);
  return { path: productPath(id), name: cardName(a), price, regular_price: ref != null && price != null && ref > price ? ref : null };
}

interface Group {
  el: HTMLElement;
  name: string;
  button: HTMLElement;
  content: HTMLElement | null;
}

/** The filter panel's groups (`#panel-filters`, an accordion): h4 headers on
 *  a category, h3 on a search, each with its button and its collapse. */
function groups(): Group[] {
  const out: Group[] = [];
  for (const el of document.querySelectorAll<HTMLElement>("#panel-filters .panel-filters__filter")) {
    const button = el.querySelector<HTMLElement>(".panel-filters__filter__header button");
    if (!button) continue;
    const id = button.getAttribute("aria-controls");
    out.push({ el, name: clean(button.textContent), button, content: (id ? document.getElementById(id) : null) ?? el.querySelector<HTMLElement>(".collapse") });
  }
  return out;
}

const isPriceGroup = (g: Group) => /precio/i.test(g.name) || Boolean(g.content?.querySelector("input[type=range]"));

interface Opt {
  input: HTMLInputElement;
  label: HTMLLabelElement;
  text: string;
}

/** A group's options: each checkbox and its label, the label's words without
 *  the "(count)" after them. */
function options(g: Group): Opt[] {
  const out: Opt[] = [];
  for (const box of g.content?.querySelectorAll<HTMLElement>(".form-check") ?? []) {
    const input = box.querySelector<HTMLInputElement>("input[type=checkbox]");
    const label = box.querySelector<HTMLLabelElement>("label");
    if (!input || !label) continue;
    const text = clean(label.querySelector("span")?.textContent ?? label.textContent?.replace(/\(\d+\)\s*$/, ""));
    if (text) out.push({ input, label, text });
  }
  return out;
}

function listingCount(): number | null {
  for (const el of main().querySelectorAll<HTMLElement>("p")) {
    const m = clean(el.textContent).match(/de\s+([\d.]+)\s+resultados/i);
    if (m) return Number(m[1]!.replace(/\./g, ""));
  }
  const m = clean(document.querySelector(".panel-filters-header__results")?.textContent).match(/([\d.]+)/);
  return m ? Number(m[1]!.replace(/\./g, "")) : null;
}

type Sort = "price_asc" | "price_desc" | "relevance";

function sortOf(): Sort | null {
  const toggle = document.querySelector("#dropdown-order");
  const said = norm(toggle?.textContent);
  if (/menor a mayor/.test(said)) return "price_asc";
  if (/mayor a menor/.test(said)) return "price_desc";
  const param = new URLSearchParams(location.search).get("sort") ?? "";
  if (/asc/.test(param)) return "price_asc";
  if (/desc/.test(param)) return "price_desc";
  return toggle ? "relevance" : null;
}

const searchWords = () => clean(new URLSearchParams(location.search).get("search")?.replace(/\+/g, " "));

/** A listing's own address: the category path, or the search with its words. */
function listingPath(): string {
  if (kindOf() === "search") return `/busqueda-avanzada?search=${searchWords().toLowerCase().split(" ").filter(Boolean).join("+")}`;
  return location.pathname.replace(/\/+$/, "");
}

function readListing(): ListingState {
  const facets: ListingFilter[] = groups()
    .filter((g) => !isPriceGroup(g))
    .map((g) => {
      const opts = options(g);
      return { facet: g.name, on: opts.filter((o) => o.input.checked).map((o) => o.text), options: opts.map((o) => o.text).slice(0, MAX_OPTIONS) };
    });
  const q = new URLSearchParams(location.search);
  const title =
    kindOf() === "search"
      ? `Resultados para "${searchWords()}"`
      : clean(document.querySelector(".panel-filters-header__childcategory")?.textContent) || clean(main().querySelector("h1")?.textContent) || document.title;
  return {
    path: listingPath(),
    title,
    count: listingCount(),
    filters: facets,
    sort: sortOf(),
    items: cards()
      .map(cardItem)
      .filter((x): x is ListingItem => x !== null)
      .slice(0, MAX_LISTED),
    price: `${q.get("precioMin") ?? ""}-${q.get("precioMax") ?? ""}`,
  };
}

/** What the grid shows now, to tell when it changed. */
const gridKey = () => JSON.stringify([cards().map(cardId), listingCount(), sortOf(), location.search]);

/** The grid has changed from `before` and the store's calls since `since`
 *  are back, then the DOM has been quiet a moment. */
async function waitForGrid(before: string, since: number, ms = 10_000): Promise<boolean> {
  const changed = await waitFor(() => gridKey() !== before, ms);
  await apiSettled(since, 2500);
  await quiet(gridSection() ?? main(), 300, 1500);
  return Boolean(changed) || gridKey() !== before;
}

// ─── The cart ─────────────────────────────────────────────────────────────

interface CartItem {
  path: string;
  name: string;
  qty: number;
  price: number | null;
}
interface CartState {
  count: number;
  subtotal: number | null;
  items: CartItem[];
}

interface Stored {
  id: number;
  cantidad: number;
  origin?: string;
}

/** The cart as the site keeps it, in this browser: `localStorage.cartProducts`. */
function storedCart(): Stored[] {
  try {
    const raw = JSON.parse(localStorage.getItem("cartProducts") ?? "null") as { items?: Stored[] } | null;
    return (raw?.items ?? []).filter((i) => Number.isInteger(Number(i.id)));
  } catch {
    return [];
  }
}
const storedQty = (id: number) => storedCart().find((i) => Number(i.id) === id)?.cantidad ?? 0;

const cartRows = () => [...document.querySelectorAll<HTMLElement>(".card-list-product[data-gtag-id]")].filter(shown);
const rowQty = (row: HTMLElement) => Number(row.querySelector<HTMLInputElement>("input.pcf-value-input")?.value) || Number(row.getAttribute("data-gtag-cant")) || 0;

/** The summary's "Total Transferencia / Débito". */
function summaryTotal(): number | null {
  for (const p of document.querySelectorAll<HTMLElement>("aside.purchase-summary p")) {
    if (/total transferencia/i.test(clean(p.textContent))) return money(p.nextElementSibling?.textContent);
  }
  return null;
}

/** The cart page, read from its rows and summary. */
function cartFromPage(): CartState {
  const items = cartRows().map((row) => {
    const id = Number(row.getAttribute("data-gtag-id"));
    return {
      path: productPath(id),
      name: clean(row.getAttribute("data-gtag-name") ?? row.querySelector(".card-list-product__name")?.textContent),
      qty: rowQty(row),
      price: money(row.querySelector(".card-list-product__price")?.textContent),
    };
  });
  return { count: items.reduce((n, i) => n + i.qty, 0), subtotal: summaryTotal(), items };
}

interface StatusAnswer {
  items?: { producto?: { id?: number; nombre?: string; precio?: ApiPrice }; cantidad?: number }[];
  total?: ApiPrice;
}

/** The cart now: on the cart page, its rows; elsewhere, the stored lines
 *  priced by the store's own `POST /carro/status`, as the cart page does. */
async function readCart(): Promise<CartState> {
  if (kindOf() === "cart" && cartRows().length) return cartFromPage();
  const stored = storedCart();
  if (!stored.length) return { count: 0, subtotal: 0, items: [] };
  try {
    const answer = await getJson<StatusAnswer>(`${CART_API}/status`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ items: stored.map((i) => ({ id: Number(i.id), cantidad: i.cantidad, origin: i.origin ?? "PCF", empresa: "PCFACTORY" })) }),
    });
    const items = (answer.items ?? []).map((l) => ({
      path: productPath(Number(l.producto?.id)),
      name: clean(l.producto?.nombre),
      qty: Number(l.cantidad) || 0,
      price: pesos(l.producto?.precio?.efectivo),
    }));
    return { count: items.reduce((n, i) => n + i.qty, 0), subtotal: pesos(answer.total?.efectivo), items };
  } catch {
    const items = stored.map((i) => ({ path: productPath(Number(i.id)), name: "", qty: i.cantidad, price: null }));
    return { count: items.reduce((n, i) => n + i.qty, 0), subtotal: null, items };
  }
}

const CART_SEEN_KEY = "voqalize.pcfactory.cart";
const cartSig = (c: CartState) => JSON.stringify([c.count, c.subtotal, c.items.map((i) => [i.path, i.qty])]);

function reportCart(c: CartState): void {
  try {
    sessionStorage.setItem(CART_SEEN_KEY, cartSig(c));
  } catch {
    // No storage: the next page reports the cart again.
  }
  report("cart_state", c);
}

/** On a new page: the cart, only when it is not what this tab last reported. */
async function cartIfChanged(): Promise<void> {
  const c = await readCart();
  let seen: string | null = null;
  try {
    seen = sessionStorage.getItem(CART_SEEN_KEY);
  } catch {
    seen = null;
  }
  if (seen !== cartSig(c)) reportCart(c);
}

const cartLine = (c: CartState) =>
  `the cart has ${c.count} item${c.count === 1 ? "" : "s"}${c.subtotal != null ? `, $${c.subtotal} by transferencia` : ""}`;

const addedModal = () => document.querySelector<HTMLElement>("#pcf-modal-added-product.show");

/** Close the "Producto agregado" window with its own "Seguir comprando". */
async function closeAdded(): Promise<boolean> {
  const modal = addedModal();
  if (!modal) return false;
  const keep =
    [...modal.querySelectorAll<HTMLElement>("button")].find((b) => /seguir comprando/i.test(clean(b.textContent)) && shown(b)) ??
    modal.querySelector<HTMLElement>(".btn-close-cart");
  if (keep) press(keep);
  if (!(await waitFor(() => !addedModal(), 2500))) {
    // No Bootstrap to animate it out (a saved copy): hide it as it would.
    modal.classList.remove("show");
    modal.style.display = "none";
    document.querySelectorAll(".modal-backdrop").forEach((b) => b.remove());
    document.body.classList.remove("modal-open");
  }
  return true;
}

// ─── The checkout ─────────────────────────────────────────────────────────

interface CheckoutState {
  step: "login" | "delivery" | "payment" | "other";
  options: string[];
  chosen: string | null;
}

const methodOptions = () => [...document.querySelectorAll<HTMLInputElement>("input[type=radio][name=method]")];
const guestButton = () =>
  [...document.querySelectorAll<HTMLElement>(".identification .right .identification__card > button, .identification__card > button")].find(
    (b) => /invitad|guest/i.test(clean(b.textContent)) && shown(b),
  ) ?? null;

function methodLabel(r: HTMLInputElement): string {
  const label = clean(document.querySelector(`label[for="${CSS.escape(r.id)}"]`)?.textContent) || r.value;
  const tag = clean(r.closest(".method-option")?.querySelector(".method-option__tag")?.textContent);
  return tag ? `${label} (${tag})` : label;
}

function readCheckout(): CheckoutState {
  const step = checkoutStep(location.pathname);
  const active = norm(document.querySelector(".step.active .step__title")?.textContent);
  if (/^pago/.test(active)) return { step: "payment", options: [], chosen: null };
  if (step === "delivery" || methodOptions().length) {
    const radios = methodOptions();
    const chosen = radios.find((r) => r.checked);
    return { step: "delivery", options: radios.map(methodLabel), chosen: chosen ? methodLabel(chosen) : null };
  }
  if (step === "login") {
    const buttons = [...document.querySelectorAll<HTMLElement>(".identification button, .identification a")].map((b) => clean(b.textContent)).filter(Boolean);
    return { step: "login", options: buttons, chosen: null };
  }
  return { step: "other", options: [], chosen: null };
}

/** The checkout's step, once its widget has drawn its choices. */
const reportCheckout = () => {
  if (kindOf() !== "checkout") return;
  const state = readCheckout();
  if (state.step !== "other" && state.step !== "payment" && !state.options.length) return;
  report("checkout_state", state);
};

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

interface Then {
  move: string;
  args: unknown;
}

/** Load `path` in this tab, with the rest of the move for the page it lands
 *  on; refused before anything moves if `path` is past Tipo de entrega, an
 *  account page or another host. The move goes on there: `null`. */
async function load(c: MoveContext, path: string, then?: Then): Promise<null> {
  const url = target(path);
  if (!c.loadThen) throw new Error("this page cannot load another and carry the move there");
  await c.loadThen(url, then);
  return null;
}

const again = (c: MoveContext, p: object): Then => ({ move: c.move, args: { ...p, arrived: true } });

/** A link or card on this page to product `id`, to ring before loading it. */
function productLink(id: number): HTMLElement | null {
  const card = cards().find((a) => cardId(a) === id && shown(a));
  if (card) return card;
  for (const a of main().querySelectorAll<HTMLAnchorElement>("a[href*='/producto/']")) {
    if (productId(pathOf(a.href)) === id && shown(a) && !inChrome(a)) return a.closest<HTMLElement>(".rr-item") ?? a;
  }
  return null;
}

/** A link on this page to `path`, to ring before loading it. */
function linkTo(path: string): HTMLAnchorElement | null {
  return [...main().querySelectorAll<HTMLAnchorElement>("a[href]")].find((a) => shown(a) && !inChrome(a) && samePath(a.href, path)) ?? null;
}

/** The first row of the grid, to point at after it changed. */
function firstRow(): HTMLElement[] {
  const all = cards().filter(shown);
  if (!all.length) return [];
  const top = all[0]!.getBoundingClientRect().top;
  return all.filter((a) => Math.abs(a.getBoundingClientRect().top - top) < 20);
}

/** The listing as it now stands, reported: a detail. Its first row is
 *  scrolled to and ringed after the move's result, which goes as soon as the
 *  grid has landed: that ring points at the effect, it acts on nothing. */
function showGrid(c: MoveContext): string {
  const listing = readListing();
  report("listing_shown", listing);
  c.after(async () => {
    const row = firstRow();
    if (!row.length) return;
    await scrollTo(row[0]!, "center");
    await c.ring(row);
  });
  const first = listing.items[0];
  return `${listing.title}: ${listing.count ?? "?"} products${listing.sort && listing.sort !== "relevance" ? `, sorted ${listing.sort}` : ""}; ${
    first ? `first card ${first.name} ($${first.price ?? "?"})` : "no products"
  }`;
}

// commerce.search ──────────────────────────────────────────────────────────

const searchBox = () => [...document.querySelectorAll<HTMLInputElement>("#search-input-desktop, #search-input-mobile")].find(shown) ?? null;
const searchButton = () => [...document.querySelectorAll<HTMLElement>("#search-btn-desktop, #search-btn-mobile")].find(shown) ?? null;

/** The results address the site's own search builds: its words, lower case,
 *  joined by "+". */
const searchUrl = (query: string) => `/busqueda-avanzada?search=${query.toLowerCase().split(/\s+/).filter(Boolean).map(encodeURIComponent).join("+")}`;

async function searchProducts(p: { query: string; open_index?: number | null } & Arrived, c: MoveContext): Promise<string | null> {
  const query = clean(p.query);
  if (!query) c.refuse("query", "say what to search for");
  if (!p.arrived) {
    const input = searchBox();
    if (!input) throw new Error("the search box is not on this page");
    await scrollToTopOfPage();
    await c.ring(input.closest("form, .input-group") ?? input, query);
    await typeInto(input, query);
    await c.beat(350);
    const button = searchButton();
    const then = again(c, p);
    if (button) {
      await c.ring(button);
      // The site's button loads the results page itself (`location.href`); the
      // rest of the move waits for it there.
      await c.keep(then);
      press(button);
      if (await waitFor(() => document.visibilityState === "hidden" || location.pathname === "/busqueda-avanzada", 4000)) await sleep(4000);
      await c.drop();
    }
    return load(c, searchUrl(query), then);
  }
  if (kindOf() !== "search") throw new Error(`the search did not open its results (now on ${location.pathname})`);
  await waitFor(gridUp, 10_000);
  await quiet(gridSection() ?? main(), 300, 1500);
  if (p.open_index != null) {
    const all = cards();
    const card = all[p.open_index];
    if (!card) c.refuse("open_index", `the results show ${all.length} products; there is no number ${p.open_index + 1}`, all.map(cardName).slice(0, 12));
    report("listing_shown", readListing());
    await scrollTo(card, "center");
    await c.ring(card, cardName(card));
    const id = cardId(card)!;
    return load(c, productPath(id), { move: "open_product", args: { path: productPath(id), tab: null, arrived: true } });
  }
  return `searched "${query}"; ${showGrid(c)}`;
}

// filter_listing, and the filter and sort cues ─────────────────────────────

/** A listing the brain named: a category path, or a search with its words. */
function wantedListing(raw: string): { path: string; search: string | null } | null {
  try {
    const u = new URL(raw.trim(), location.origin);
    const path = u.pathname.replace(/\/+$/, "");
    if (path === "/busqueda-avanzada") {
      const words = clean(u.searchParams.get("search")?.replace(/\+/g, " "));
      return words ? { path, search: words } : null;
    }
    if (!path.startsWith("/categoria/")) return null;
    return { path, search: null };
  } catch {
    return null;
  }
}

function onWantedListing(w: { path: string; search: string | null }): boolean {
  if (!isListing()) return false;
  if (w.search !== null) return kindOf() === "search" && norm(searchWords()) === norm(w.search);
  return samePath(location.pathname, w.path);
}

const listingUrl = (w: { path: string; search: string | null }) => (w.search !== null ? searchUrl(w.search) : w.path);

/** The group the brain named, by the panel's words ("Marcas", "RAM"), with
 *  the singulars and English a brain may say. */
const FACET_ALIASES: Record<string, string> = {
  marca: "marcas", brand: "marcas", brands: "marcas", tienda: "tiendas", store: "tiendas", stores: "tiendas", sucursal: "tiendas",
  categoria: "categorias", category: "categorias", precio: "rango de precios", price: "rango de precios",
};
function findGroup(facet: string): Group | null {
  const all = groups();
  const said = norm(facet);
  return best(all, (g) => g.name, FACET_ALIASES[said] ?? facet) ?? null;
}

async function openGroup(c: MoveContext, g: Group): Promise<Group> {
  const isOpen = () => Boolean(g.content && (g.content.classList.contains("show") || shown(g.content)));
  await scrollTo(g.button, "center");
  if (!isOpen()) {
    await c.ring(g.button, g.name);
    press(g.button);
    if (!(await waitFor(isOpen, 1500)) && g.content) {
      // No Bootstrap to animate it open (a saved copy): open it as it would.
      g.content.classList.add("show");
      g.button.setAttribute("aria-expanded", "true");
    }
    await sleep(350);
  }
  return g;
}

type Applied = { ok: true; label: string; already?: boolean };
type Missed = { ok: false; arg: string; why: string; options: string[] };

/** Tick one option of one group with the listing's own checkbox, as a visitor
 *  does: the group opened if folded, the option scrolled to and ringed, its
 *  label pressed, then the grid waited for. */
async function applyOption(c: MoveContext, facet: string, value: string, arg = "value", facetArg = "facet"): Promise<Applied | Missed> {
  const g = findGroup(facet);
  const names = groups().map((x) => x.name);
  if (!g) return { ok: false, arg: facetArg, why: `this listing has no filter "${facet}"`, options: names };
  if (isPriceGroup(g)) return { ok: false, arg: facetArg, why: `"${g.name}" takes a minimum and a maximum price, not an option`, options: names };
  await openGroup(c, g);
  const opt = best(options(g), (o) => o.text, value);
  if (!opt) return { ok: false, arg, why: `${g.name} has no option "${value}"`, options: options(g).map((o) => o.text).slice(0, MAX_OPTIONS) };
  if (opt.input.checked) return { ok: true, label: `${g.name}: ${opt.text}`, already: true };
  await scrollTo(opt.label, "center");
  await c.ring(opt.label.closest(".form-check") ?? opt.label, `${g.name}: ${opt.text}`);
  const before = gridKey();
  const since = Date.now();
  c.progress("waiting_site");
  press(opt.label);
  await waitForGrid(before, since);
  // The panel re-renders after each filter: the option is looked up again.
  const now = findGroup(g.name);
  const back = now ? best(options(now), (o) => o.text, opt.text) : null;
  if (!back?.input.checked) return { ok: false, arg, why: `${g.name} ${opt.text} did not stay ticked`, options: [] };
  return { ok: true, label: `${g.name}: ${opt.text}` };
}

/** "Rango de precios": its two sliders set as a drag would leave them, one
 *  after the other, each waited for (the second set before the first's grid
 *  is back is undone by it). */
async function applyPrice(c: MoveContext, min: number | null | undefined, max: number | null | undefined): Promise<Applied | Missed> {
  const g = groups().find(isPriceGroup);
  if (!g) return { ok: false, arg: "min_price", why: "this listing has no price range", options: groups().map((x) => x.name) };
  await openGroup(c, g);
  const ranges = () => [...(g.content?.querySelectorAll<HTMLInputElement>("input[type=range]") ?? [])];
  if (ranges().length < 2) return { ok: false, arg: "min_price", why: "the price range has no sliders", options: [] };
  const lo = Number(ranges()[0]!.min);
  const hi = Number(ranges()[0]!.max);
  await scrollTo(g.content!, "center");
  await c.ring(g.content!.querySelector(".price-range") ?? g.content!, `$${min ?? lo} – $${max ?? hi}`);
  const set = async (i: 0 | 1, v: number) => {
    const before = gridKey();
    const since = Date.now();
    c.progress("waiting_site");
    setRange(ranges()[i]!, Math.min(Math.max(v, lo), hi));
    await waitForGrid(before, since);
  };
  // A bound at or past the range's own end is no filter at all.
  if (min != null && min > lo) await set(0, min);
  if (max != null && max < hi) await set(1, max);
  const q = new URLSearchParams(location.search);
  const gotMin = Number(q.get("precioMin") ?? NaN);
  const gotMax = Number(q.get("precioMax") ?? NaN);
  const minOk = min == null || min <= lo || Math.abs(gotMin - min) <= 1;
  const maxOk = max == null || max >= hi || Math.abs(gotMax - max) <= 1;
  if (!minOk || !maxOk) {
    return { ok: false, arg: max != null ? "max_price" : "min_price", why: `the price range shows $${q.get("precioMin") ?? lo} – $${q.get("precioMax") ?? hi}`, options: [`$${lo}`, `$${hi}`] };
  }
  return { ok: true, label: `Rango de precios $${Number.isFinite(gotMin) ? gotMin : lo} – $${Number.isFinite(gotMax) ? gotMax : hi}` };
}

const SORT_WORDS: Record<Sort, RegExp> = { price_asc: /menor a mayor/i, price_desc: /mayor a menor/i, relevance: /recomendad/i };

/** "Ordenar por": the menu opened, then its item pressed. */
async function applySort(c: MoveContext, sort: string): Promise<Applied | Missed> {
  const toggle = [...document.querySelectorAll<HTMLElement>("#dropdown-order")].find(shown) ?? document.querySelector<HTMLElement>("#dropdown-order");
  const items = () => [...(toggle?.closest(".dropdown")?.querySelectorAll<HTMLElement>(".dropdown-item") ?? [])];
  const offered = items().map((i) => clean(i.textContent));
  if (!toggle) return { ok: false, arg: "order", why: "this listing has no Ordenar por", options: [] };
  if (!(sort in SORT_WORDS)) return { ok: false, arg: "order", why: `this listing cannot sort by ${sort}`, options: offered };
  if (sortOf() === sort) return { ok: true, label: `sorted ${clean(toggle.textContent)}`, already: true };
  const item = items().find((i) => SORT_WORDS[sort as Sort].test(clean(i.textContent)));
  if (!item) return { ok: false, arg: "order", why: `Ordenar por has no ${sort}`, options: offered };
  await scrollTo(toggle.closest("section") ?? toggle, "center");
  await c.ring(toggle, "Ordenar por");
  press(toggle);
  await waitFor(() => item.closest(".dropdown-menu.show") ?? (shown(item) ? item : null), 1200);
  if (shown(item)) await c.ring(item, clean(item.textContent));
  const before = gridKey();
  const since = Date.now();
  c.progress("waiting_site");
  press(item);
  await waitForGrid(before, since);
  if (sortOf() !== sort) return { ok: false, arg: "order", why: `the listing still shows ${clean(toggle.textContent)}`, options: offered };
  return { ok: true, label: `sorted ${clean(item.textContent)}` };
}

/** "Facet: Option" as the brain writes each filter. */
function parseFilter(raw: unknown): { facet: string; value: string } | null {
  if (typeof raw !== "string") return null;
  const i = raw.indexOf(":");
  if (i <= 0) return null;
  const facet = clean(raw.slice(0, i));
  const value = clean(raw.slice(i + 1));
  return facet && value ? { facet, value } : null;
}

/** Filters on now that the brain did not ask for: ticked options, or a price
 *  range in the address. */
function strayFilters(wanted: { facet: string; value: string }[], min: unknown, max: unknown): boolean {
  for (const g of groups()) {
    if (isPriceGroup(g)) continue;
    for (const o of options(g)) {
      if (!o.input.checked) continue;
      const asked = wanted.some((w) => findGroup(w.facet) === g && best([o], (x) => x.text, w.value));
      if (!asked) return true;
    }
  }
  const q = new URLSearchParams(location.search);
  return (q.has("precioMin") && min == null) || (q.has("precioMax") && max == null);
}

interface FilterListing extends Arrived {
  category_path: string;
  filters?: unknown[] | null;
  min_price?: number | null;
  max_price?: number | null;
  sort?: Sort | null;
  clean?: boolean;
}

async function filterListing(p: FilterListing, c: MoveContext): Promise<string | null | PerformResult> {
  if (typeof p.category_path !== "string" || !p.category_path.trim()) c.refuse("category_path", "say which listing, as /categoria/... or /busqueda-avanzada?search=...");
  const want = wantedListing(p.category_path);
  if (!want) c.refuse("category_path", `"${p.category_path}" is not a listing; use a /categoria/... path from the category list, or /busqueda-avanzada?search=...`);
  const raw = Array.isArray(p.filters) ? p.filters : [];
  const wanted = raw.map(parseFilter).filter((x): x is { facet: string; value: string } => x !== null);
  const bad = raw.filter((x) => !parseFilter(x));
  if (!p.arrived && !onWantedListing(want)) return load(c, listingUrl(want), again(c, p));
  if (!isListing()) throw new Error(`${listingUrl(want)} did not open as a listing (now on ${location.pathname})`);
  await waitFor(() => document.querySelector("#panel-filters .panel-filters__filter") && gridUp(), 10_000);
  await quiet(main(), 300, 1500);
  // This listing with filters on that the wish does not have: loaded clean
  // once, and finished there.
  if (!p.clean && strayFilters(wanted, p.min_price, p.max_price)) return load(c, listingUrl(want), { move: c.move, args: { ...p, arrived: true, clean: true } });

  const done: string[] = [];
  const missed: Refusal[] = bad.map((x) => ({ arg: "filters", why: `"${String(x)}" is not "Facet: Option"`, options: [] }));
  for (const w of wanted) {
    const got = await applyOption(c, w.facet, w.value, "filters", "filters");
    if (got.ok) done.push(got.label);
    else missed.push({ arg: got.arg, why: got.why, options: got.options });
  }
  if (p.min_price != null || p.max_price != null) {
    const got = await applyPrice(c, p.min_price, p.max_price);
    if (got.ok) done.push(got.label);
    else missed.push({ arg: got.arg, why: got.why, options: got.options });
  }
  if (p.sort) {
    const got = await applySort(c, p.sort);
    if (got.ok) done.push(got.label);
    else missed.push({ arg: "sort", why: got.why, options: got.options });
  }
  const grid = showGrid(c);
  const asked = wanted.length + bad.length + (p.min_price != null || p.max_price != null ? 1 : 0) + (p.sort ? 1 : 0);
  if (asked && !done.length && missed.length) {
    const first = missed[0]!;
    c.refuse(first.arg, missed.map((m) => m.why).join("; "), first.options ?? []);
  }
  if (done.length && missed.length) return { outcome: "partial", detail: `applied ${done.join(", ")}; ${grid}`, refused: missed };
  return [grid, done.length ? `applied ${done.join(", ")}` : ""].filter(Boolean).join("; ");
}

/** Before a cue on a listing: the listing at `path` must be the one in front,
 *  or it is loaded and the cue carried there. */
async function onListing(c: MoveContext, path: string | null | undefined, arrived: boolean, then: Then): Promise<boolean> {
  const want = path ? wantedListing(path) : null;
  if (path && !want) c.refuse("path", `"${path}" is not a listing`);
  if (want && !arrived && !onWantedListing(want)) {
    await load(c, listingUrl(want), then);
    return false;
  }
  if (!isListing()) throw new Error(`no product listing is on screen (now on ${location.pathname})`);
  await waitFor(() => document.querySelector("#panel-filters .panel-filters__filter") && cards().length, 8000);
  return true;
}

/** The filter cue: one option of one group, as its words are said, or several
 *  of one group joined by commas. Each is added to what is on; every one is
 *  checked on at the end, and one that is not makes it `partial`. */
async function filterCue(p: { facet: string; value?: string | null; path?: string | null } & Arrived, c: MoveContext): Promise<string | null | PerformResult> {
  if (!clean(p.facet)) c.refuse("facet", "say which filter, as the listing names it", groups().map((g) => g.name));
  // `{filter: Marcas: Lenovo}` arrives as one argument.
  let facet = clean(p.facet);
  let value = clean(p.value);
  if (!value && facet.includes(":")) [facet, value] = [clean(facet.split(":")[0]), clean(facet.split(":").slice(1).join(":"))];
  if (!(await onListing(c, p.path, Boolean(p.arrived), again(c, p)))) return null;
  const g = findGroup(facet);
  if (!g) c.refuse("facet", `this listing has no filter "${facet}"`, groups().map((x) => x.name));
  if (!value) c.refuse("value", `say which ${g.name}`, isPriceGroup(g) ? [] : options(g).map((o) => o.text).slice(0, MAX_OPTIONS));
  const done: string[] = [];
  const missed: Missed[] = [];
  for (const v of value.split(",").map(clean).filter(Boolean)) {
    const got = await applyOption(c, g.name, v);
    if (got.ok) done.push(got.label);
    else missed.push(got);
  }
  if (!done.length) c.refuse(missed[0]!.arg, missed.map((m) => m.why).join("; "), missed[0]!.options);
  const detail = `${done.join(", ")} on; ${showGrid(c)}`;
  if (missed.length) return { outcome: "partial", detail, refused: missed.map((m) => ({ arg: m.arg, why: m.why, options: m.options })) };
  return detail;
}

/** The sort cue. */
async function sortCue(p: { order: string; path?: string | null } & Arrived, c: MoveContext): Promise<string | null> {
  if (!(await onListing(c, p.path, Boolean(p.arrived), again(c, p)))) return null;
  const got = await applySort(c, p.order);
  if (!got.ok) c.refuse(got.arg, got.why, got.options);
  return `${got.label}; ${showGrid(c)}`;
}

// open_product, product.tab ─────────────────────────────────────────────────

type Tab = "about" | "specs" | "warranty" | "stock" | "photos";

const TAB_IDS: Record<"about" | "specs" | "warranty", string> = { about: "about-tab", specs: "specifics-tab", warranty: "warranty-tab" };

/** Open one of the product page's tabs the way a visitor does, by its title,
 *  ringed first; should Bootstrap's tabs not be up yet, show its pane
 *  directly. With `ringPane`, the tab and its pane are ringed after. */
async function openTab(tab: "about" | "specs" | "warranty", c: MoveContext, ringPane = true): Promise<string> {
  const title = document.getElementById(TAB_IDS[tab]);
  if (!title) c.refuse("tab", `this product page has no ${tab} tab`, Object.keys(TAB_IDS).filter((t) => document.getElementById(TAB_IDS[t as keyof typeof TAB_IDS])));
  const pane = document.getElementById(title.getAttribute("aria-controls") ?? "");
  const isOpen = () => Boolean(pane && pane.classList.contains("active") && shown(pane));
  await scrollTo(title.closest("#tabs") ?? title, "top");
  if (!isOpen()) {
    await c.ring(title, clean(title.textContent));
    press(title);
    if (!(await waitFor(isOpen, 1200)) && pane) {
      for (const other of document.querySelectorAll<HTMLElement>("#tabs .nav-link")) {
        other.classList.remove("active");
        other.setAttribute("aria-selected", "false");
      }
      for (const other of pane.parentElement?.querySelectorAll<HTMLElement>(":scope > .tab-pane") ?? []) other.classList.remove("active", "show");
      title.classList.add("active");
      title.setAttribute("aria-selected", "true");
      pane.classList.add("active", "show");
    }
    await sleep(250);
  }
  if (ringPane) {
    const box = boxOf([title, ...(pane ? [pane] : [])]);
    const tall = box ? box.bottom - box.top > window.innerHeight - headerHeight() - 40 : false;
    await scrollTo(title.closest("#tabs") ?? title, tall ? "top" : "center");
    await c.ring(tall ? title : [title, ...(pane ? [pane] : [])], clean(title.textContent));
  }
  return `opened ${clean(title.textContent)}`;
}

async function showStock(c: MoveContext): Promise<string> {
  const stock = document.querySelector<HTMLElement>("#stock");
  if (!stock) c.refuse("tab", "this product page has no Disponibilidad list", ["about", "specs", "warranty", "photos"]);
  await scrollTo(stock, "center");
  await c.ring(stock, "Disponibilidad");
  const list = stockList();
  const online = list.find((r) => /^internet$/i.test(r.name));
  return `showed Disponibilidad: Internet ${online?.qty ?? "?"}, ${list.filter((r) => !/^internet$/i.test(r.name) && r.qty !== "0").length} stores with stock`;
}

/** Step the gallery through a few photos by its thumbnails, ringed first (on
 *  a phone, the carousel's own next). */
async function showPhotos(c: MoveContext): Promise<string> {
  const gallery = document.querySelector<HTMLElement>("#gallery");
  if (!gallery) throw new Error("this product page has no gallery");
  const thumbs = [...gallery.querySelectorAll<HTMLElement>(".gallery-thumbs .gallery-thumbs__holder")].filter((t) => shown(t) && !t.hasAttribute("data-toggle"));
  await scrollTo(gallery, "center");
  await c.ring(gallery, "fotos");
  const steps = Math.min(3, Math.max(0, thumbs.length - 1));
  for (let i = 1; i <= steps; i++) {
    await sleep(1100);
    press(thumbs[i]!);
  }
  if (!steps) {
    const next = gallery.querySelector<HTMLElement>(".carousel-control-next");
    if (next && shown(next)) {
      await sleep(1100);
      press(next);
    }
  }
  const total = gallery.querySelectorAll(".gallery-thumbs .gallery-thumbs__holder img, #gallery-mobile-carousel .carousel-item").length;
  return `stepped the gallery through ${steps + 1} photos${total ? ` of ${Math.max(total, steps + 1)}` : ""}`;
}

async function productTab(p: { tab: Tab }, c: MoveContext): Promise<string> {
  if (!onProductPage()) throw new Error(`no product page is on screen (now on ${location.pathname})`);
  if (p.tab === "photos") return showPhotos(c);
  if (p.tab === "stock") return showStock(c);
  if (p.tab in TAB_IDS) return openTab(p.tab as keyof typeof TAB_IDS, c);
  c.refuse("tab", `no tab "${p.tab}"`, ["about", "specs", "warranty", "stock", "photos"]);
}

const productUp = () => document.querySelector("#product-title .product-title__product-name") && document.querySelector(".detail__prices__cash, .detail__prices");

async function openProduct(p: { path: string; tab?: Tab | null } & Arrived, c: MoveContext): Promise<string | null> {
  const id = productId(p.path);
  if (!id) c.refuse("path", "say which product, as /producto/<id>");
  if (!p.arrived && !(onProductPage() && productId(location.pathname) === id)) {
    // Its card or link on this page, when it has one, is ringed first.
    const link = productLink(id);
    if (link) {
      await scrollTo(link, "center");
      await c.ring(link);
    }
    return load(c, productPath(id), again(c, p));
  }
  await waitFor(productUp, 10_000);
  if (!onProductPage() || productId(location.pathname) !== id) throw new Error(`${productPath(id)} did not open as a product page (now on ${location.pathname})`);
  const product = readProduct();
  if (product) report("product_shown", latestProductFor(product));
  void confirmProduct();
  let did = "";
  if (p.tab) did = await productTab({ tab: p.tab }, c);
  else {
    // The product is the effect: its name and prices are ringed after the
    // result, which goes as soon as the page is up.
    c.after(async () => {
      await scrollToTopOfPage();
      const parts = [document.querySelector("#product-title"), document.querySelector(".detail__prices")].filter((x): x is Element => x !== null);
      if (parts.length) await c.ring(parts);
    });
  }
  return [
    product
      ? `${product.name} is on screen at $${product.price ?? "?"} transferencia${product.card_price ? ` ($${product.card_price} otros medios)` : ""}; Internet stock ${product.online_stock ?? "?"}`
      : "the product page is on screen",
    did,
  ]
    .filter(Boolean)
    .join("; ");
}

// find_products, check_prices, check_stock: reads ──────────────────────────

const SORT_PARAM: Record<string, string> = { price_asc: "precio,asc", price_desc: "precio,desc" };

interface FindProducts {
  query?: string | null;
  category_id?: number | null;
  brand?: string | null;
  min_price?: number | null;
  max_price?: number | null;
  sort?: Sort | null;
}

interface Facet {
  nombre: string;
  param: string;
  items: { id?: number | null; valor: string }[];
}

async function findProducts(p: FindProducts, c: MoveContext): Promise<string> {
  const query = clean(p.query);
  const category = Number.isInteger(p.category_id) ? (p.category_id as number) : null;
  if (!query && !category) c.refuse("query", "say what to look for, or a category id");
  const q = new URLSearchParams({ page: "0", size: String(MAX_FOUND) });
  let endpoint: string;
  let facetsUrl: string;
  if (query) {
    endpoint = `${API}/productos`;
    q.set("search", query.toLowerCase());
    if (category) {
      const fam = await getJson<{ nombre?: string }[]>(`https://api.pcfactory.cl/api-dex-catalog/v1/catalog/category/PCF/family/${category}`).catch(() => []);
      const name = fam.find(Boolean)?.nombre;
      if (!name) c.refuse("category_id", `no category ${category}`);
      q.set("categorias", name);
    }
    facetsUrl = `${API}/productos/facets?search=${encodeURIComponent(query.toLowerCase())}`;
  } else {
    endpoint = `${API}/productos/query`;
    q.set("categorias", String(category));
    facetsUrl = `${API}/productos/query/facets?categorias=${category}`;
  }
  if (p.brand) {
    // Search takes a brand by its name, a category by its id: both read off
    // the store's own facets for these products.
    const facets = await getJson<{ items?: Facet[] }>(facetsUrl).catch(() => ({ items: [] as Facet[] }));
    const brands = facets.items?.find((f) => f.param === "marcas")?.items ?? [];
    const hit = best(brands, (b) => b.valor, p.brand);
    if (!hit) c.refuse("brand", `no ${p.brand} among these products`, brands.map((b) => b.valor).slice(0, MAX_OPTIONS));
    q.set("marcas", query ? hit.valor : String(hit.id));
  }
  if (p.min_price != null) q.set("precioMin", String(Math.round(p.min_price)));
  if (p.max_price != null) q.set("precioMax", String(Math.round(p.max_price)));
  if (p.sort && SORT_PARAM[p.sort]) q.set("sort", SORT_PARAM[p.sort]!);
  const answer = await getJson<{ content?: { items?: ApiItem[]; pageable?: { totalElements?: number } } }>(`${endpoint}?${q.toString().replace(/%2C/g, ",")}`);
  const items = (answer.content?.items ?? []).slice(0, MAX_FOUND).map((i) => {
    const cash = pesos(i.precio?.efectivo);
    const ref = pesos(i.precio?.referencia);
    return {
      path: productPath(i.id),
      id: i.id,
      name: clean(i.nombre),
      brand: clean(i.marca) || undefined,
      price: cash,
      card_price: pesos(i.precio?.normal),
      regular_price: ref != null && cash != null && ref > cash ? ref : null,
      stock: clean(i.stock) || undefined,
    };
  });
  const total = answer.content?.pageable?.totalElements ?? items.length;
  told("products_found", {
    query: query || null,
    category_id: category,
    brand: p.brand ?? null,
    min_price: p.min_price ?? null,
    max_price: p.max_price ?? null,
    total,
    items,
  } satisfies ProductsFound);
  return `${total} products match; ${items
    .slice(0, 4)
    .map((i) => `${i.name} ($${i.price ?? "?"}, ${i.path})`)
    .join("; ") || "none"}`;
}

async function checkPrices(p: { paths: string[] }, c: MoveContext): Promise<string> {
  const ids = [...new Set((Array.isArray(p.paths) ? p.paths : []).map((x) => productId(x)).filter((x): x is number => x !== null))].slice(0, MAX_PRICED);
  if (!ids.length) c.refuse("paths", "say which products, as /producto/<id> paths");
  const reads = await Promise.all(
    ids.map(async (id) => {
      try {
        const [prod, price, stock] = await Promise.all([productApi(id), priceApi(id), stockApi(id).catch(() => ({}) as ApiStock)]);
        const cash = pesos(price.efectivo);
        const ref = pesos(price.referencia);
        return {
          path: productPath(id),
          id,
          name: clean(prod.nombre),
          price: cash,
          card_price: pesos(price.normal),
          regular_price: ref != null && cash != null && ref > cash ? ref : null,
          online_stock: stockRows(stock).online ?? prod.stock?.aproximado ?? undefined,
        };
      } catch {
        return productPath(id);
      }
    }),
  );
  const items = reads.filter((r): r is Exclude<typeof r, string> => typeof r !== "string");
  const missing = reads.filter((r): r is string => typeof r === "string");
  told("prices_read", { items, missing } satisfies PricesRead);
  return [
    items.map((i) => `${i.name}: $${i.price ?? "?"} transferencia, $${i.card_price ?? "?"} otros medios${i.regular_price ? ` (ref. $${i.regular_price})` : ""}, Internet stock ${i.online_stock ?? "?"}`).join("; "),
    missing.length ? `not found: ${missing.join(", ")}` : "",
  ]
    .filter(Boolean)
    .join("; ");
}

async function checkStock(p: { path: string; store?: string | null }, c: MoveContext): Promise<string> {
  const id = productId(p.path);
  if (!id) c.refuse("path", "say which product, as /producto/<id>");
  const [prod, stock] = await Promise.all([productApi(id), stockApi(id)]);
  const rows = stockRows(stock);
  const asked = clean(p.store) || null;
  let matched: string[] = [];
  if (asked) {
    matched = storesMeant(asked, rows.stores.map((s) => s.name));
    if (!matched.length) c.refuse("store", `no pcFactory store "${asked}"`, rows.stores.map((s) => s.name));
  }
  const payload: StockRead & { stores: StockRow[]; name: string } = {
    path: productPath(id),
    id,
    name: clean(prod.nombre),
    online: rows.online ?? undefined,
    stores: rows.stores.filter((s) => s.qty !== "0"),
    asked,
    matched: matched.length ? matched.join(", ") : null,
  };
  told("stock_read", payload);
  // On the product's own page: its Disponibilidad list, the store asked about
  // ringed in it.
  if (onProductPage() && productId(location.pathname) === id) {
    const list = stockList();
    const hits = matched.length ? list.filter((r) => matched.some((m) => norm(m) === norm(r.name))).map((r) => r.el) : [];
    const box = document.querySelector<HTMLElement>("#stock");
    const ringed = hits.length ? hits : box ? [box] : [];
    if (ringed.length) {
      await scrollTo(ringed[0]!, "center");
      await c.ring(ringed, hits.length ? matched.join(", ") : "Disponibilidad");
    }
  }
  const at = matched.map((m) => `${m}: ${rows.stores.find((s) => s.name === m)?.qty ?? "0"}`).join(", ");
  return `${payload.name}: Internet ${rows.online ?? "?"}; ${payload.stores.length} stores with stock${at ? `; ${at}` : ""}`;
}

// stores.show ───────────────────────────────────────────────────────────────

interface StoreCard {
  el: HTMLElement;
  name: string;
  address: string;
  city: string;
  region: string;
}

function storeCards(): StoreCard[] {
  return [...document.querySelectorAll<HTMLElement>(".card.card-tabs[data-content-name]")].map((el) => {
    const [city = "", region = ""] = clean(el.querySelector("h6")?.textContent).split(/\s+-\s+/);
    return { el, name: clean(el.querySelector("h3")?.textContent) || clean(el.getAttribute("data-content-name")), address: clean(el.querySelector("p")?.textContent), city, region };
  });
}

/** The map card Google draws for "Ver tienda": its Dirección and Horarios
 *  (the line after them naming the store's manager is left out). */
function mapCard(): { el: HTMLElement; address: string; hours: string } | null {
  const el = [...document.querySelectorAll<HTMLElement>(".gm-style-iw, .gm-style-iw-c")].find(shown);
  if (!el) return null;
  const lines = (el.innerText || el.textContent || "").split("\n").map(clean).filter(Boolean);
  const after = (word: RegExp, stop: RegExp) => {
    const i = lines.findIndex((l) => word.test(l));
    if (i < 0) return [];
    const out: string[] = [];
    for (const l of lines.slice(i + 1)) {
      if (stop.test(l)) break;
      out.push(l);
    }
    return out;
  };
  const stop = /^(direcci[oó]n|horarios?|jefe de tienda|ver en google maps)$/i;
  return { el, address: after(/^direcci[oó]n$/i, stop).join(", "), hours: after(/^horarios?$/i, stop).join("; ") };
}

async function showStore(p: { name: string } & Arrived, c: MoveContext): Promise<string | null> {
  const said = clean(p.name);
  if (!said) c.refuse("name", "say which store");
  if (kindOf() !== "stores") {
    if (p.arrived) throw new Error(`/tiendas did not open (now on ${location.pathname})`);
    return load(c, "/tiendas", again(c, p));
  }
  await waitFor(() => storeCards().length, 8000);
  const all = storeCards();
  const names = storesMeant(said, all.map((s) => s.name));
  const card = all.find((s) => s.name === names[0]) ?? null;
  if (!card) c.refuse("name", `no store "${said}" on /tiendas`, all.map((s) => s.name));
  if (!shown(card.el)) {
    // A zone tab hides it: "Todas" shows every store again.
    const everyone = document.querySelector<HTMLElement>(".box-show__cont .nav-tabs a.nav-link");
    if (everyone) {
      await c.ring(everyone);
      press(everyone);
      await waitFor(() => shown(card.el), 2000);
    }
  }
  await scrollTo(card.el, "center");
  await c.ring(card.el, card.name);
  const button = [...card.el.querySelectorAll<HTMLElement>("button.btn-store")].find(shown);
  let map: ReturnType<typeof mapCard> = null;
  if (button) {
    c.progress("waiting_site");
    press(button);
    map = await waitFor(() => {
      const m = mapCard();
      return m && norm(m.el.textContent).includes(norm(card.name).slice(0, 6)) ? m : null;
    }, 5000);
    map ??= mapCard();
  }
  const row = storeRow(card.name);
  const shownStore: StoreShown = { name: card.name, address: card.address, city: card.city, region: card.region, zone: row?.[4] ?? "", hours: map?.hours ?? "" };
  told("store_shown", shownStore);
  if (map) {
    const el = map.el;
    c.after(async () => {
      await scrollTo(el, "center");
      await c.ring(el, card.name);
    });
  }
  return `${card.name}: ${card.address}, ${card.city}${map?.hours ? `; hours ${map.hours}` : "; the map card shows no hours"}`;
}

// compare.add ───────────────────────────────────────────────────────────────

/** What the comparator holds, as the site keeps it (`comparator-items`). */
function compared(): { id: number; name: string }[] {
  try {
    const raw = JSON.parse(localStorage.getItem("comparator-items") ?? "[]") as { id?: number; nombre?: string }[];
    return raw.filter((x) => Number.isInteger(x.id)).map((x) => ({ id: x.id!, name: clean(x.nombre) }));
  } catch {
    return [];
  }
}

const comparatorPanel = () => document.querySelector<HTMLElement>("#pcf-comparator-summary.show");

async function compareAdd(p: { paths: string[] }, c: MoveContext): Promise<string | PerformResult> {
  const ids = [...new Set((Array.isArray(p.paths) ? p.paths : []).map((x) => productId(x)).filter((x): x is number => x !== null))];
  if (!ids.length) c.refuse("paths", "say which products, as /producto/<id> paths");
  const holding = compared();
  const adding = ids.filter((id) => !holding.some((h) => h.id === id));
  if (holding.length + adding.length > MAX_COMPARED) {
    c.refuse("paths", `the comparator holds ${MAX_COMPARED} products and already has ${holding.length}; take some out with its "Limpiar selección" first`, holding.map((h) => h.name));
  }
  const missing: number[] = [];
  const added: number[] = [];
  const refusedBy = new Map<number, string>();
  for (const id of adding) {
    const pdp = onProductPage() && productId(location.pathname) === id;
    if (pdp) {
      const button = [...document.querySelectorAll<HTMLElement>("#product-title button.pcf-link-btn")].find((b) => /compar/i.test(clean(b.textContent)) && shown(b));
      if (!button) {
        missing.push(id);
        continue;
      }
      await scrollTo(button, "center");
      await c.ring(button, "Comparar");
      press(button);
    } else {
      // The card's box itself, never its label: the label's click reaches the
      // card's link and opens the product.
      const input = document.querySelector<HTMLInputElement>(`input#product-checkbox${id}`);
      const card = input?.closest<HTMLElement>("a.products__item");
      if (!input || !card) {
        missing.push(id);
        continue;
      }
      await scrollTo(card, "center");
      await c.ring(card.querySelector(".products__item__compare") ?? card, `Comparar ${cardName(card)}`);
      if (!input.checked) press(input);
    }
    c.progress("confirming");
    const took = await waitFor(() => compared().some((h) => h.id === id) || clean(document.querySelector("#pcf-comparator-summary")?.getAttribute("data-alert")), 3000);
    if (took === true) added.push(id);
    else {
      // The comparator's own refusal ("Sólo puedes comparar productos que
      // pertenezcan a la misma categoría…").
      const alert = typeof took === "string" ? took : "";
      if (alert) refusedBy.set(id, alert);
      missing.push(id);
    }
  }
  const now = compared();
  const offered = cards().map(cardName).slice(0, 12);
  const why = (ids: number[]) =>
    ids
      .map((id) => (refusedBy.has(id) ? `${productPath(id)}: the comparator says "${refusedBy.get(id)}"` : `${productPath(id)} is not on the page in front (open its listing or its page first)`))
      .join("; ");
  if (adding.length && !added.length) c.refuse("paths", why(missing), refusedBy.size ? now.map((h) => h.name) : offered);
  told("compare_shown", { items: now.map((h) => ({ path: productPath(h.id), name: h.name })) } satisfies CompareShown);
  const panel = comparatorPanel();
  if (panel) c.after(() => c.ring(panel, `Comparador (${now.length}/${MAX_COMPARED})`));
  const detail = `the comparator holds ${now.length}/${MAX_COMPARED}: ${now.map((h) => h.name).join("; ")}`;
  if (missing.length) {
    return { outcome: "partial", detail, refused: [{ arg: "paths", why: why(missing), options: refusedBy.size ? [] : offered }] };
  }
  return detail;
}

// commerce.cart_add, cart_show, cart_update ─────────────────────────────────

const pdpAddButton = () =>
  [...document.querySelectorAll<HTMLButtonElement>("#product-detail button.pcf-btn--five, .add-to-cart-fixed button")].find(
    (b) => /agregar al carro/i.test(clean(b.textContent)) && shown(b),
  ) ?? null;

/** The product page's own − / + once the product is in the cart: its
 *  "Agregar al carro" turns into this stepper after the first add. */
const pdpStepper = () => [...document.querySelectorAll<HTMLElement>("#product-detail .counter-input")].find(shown) ?? null;

async function addToCart(p: { path: string; qty?: number } & Arrived, c: MoveContext): Promise<string | null | PerformResult> {
  const id = productId(p.path);
  if (!id) c.refuse("path", "say which product, as /producto/<id>");
  const qty = Math.round(Number(p.qty ?? 1));
  if (!Number.isFinite(qty) || qty < 1 || qty > 10) c.refuse("qty", `a quantity from 1 to 10, not ${p.qty}`);
  const pdp = onProductPage() && productId(location.pathname) === id;
  const card = !pdp ? cards().find((a) => cardId(a) === id && shown(a)) : undefined;
  if (!pdp && !card) {
    if (p.arrived) throw new Error(`${productPath(id)} did not open as a product page (now on ${location.pathname})`);
    return load(c, productPath(id), again(c, p));
  }
  const start = storedQty(id);
  let left = qty;
  if (pdp) {
    await waitFor(() => pdpAddButton() ?? pdpStepper(), 10_000);
    const button = pdpAddButton();
    if (button) {
      await scrollTo(button, "center");
      await c.ring(button, "Agregar al carro");
      c.progress("waiting_site");
      press(button);
      if (!(await waitFor(() => storedQty(id) > start, 9000))) throw new Error("pressed Agregar al carro, but the cart did not change; ask the visitor to check the cart");
      left--;
      await waitFor(addedModal, 2500);
    }
    // No quantity box before the add: once in the cart, the button becomes
    // the page's own − / +, and each + adds one more.
    if (left > 0) {
      await closeAdded();
      const stepper = await waitFor(pdpStepper, 4000);
      const plus = stepper?.querySelector<HTMLElement>(".btn-plus");
      if (!stepper || !plus) throw new Error(`added ${storedQty(id) - start}, but the page shows no + for more`);
      await scrollTo(stepper, "center");
      await c.ring(stepper, `+ ${left}`);
      for (; left > 0; left--) {
        const was = storedQty(id);
        c.progress("waiting_site");
        press(plus);
        if (!(await waitFor(() => storedQty(id) > was, 6000))) break;
        await sleep(300);
      }
    }
  } else {
    const button = card!.querySelector<HTMLElement>("button.products__item__info__add-to-cart");
    if (!button) throw new Error("this card shows no Agregar al carro (out of stock?); nothing was added");
    await scrollTo(card!, "center");
    await c.ring(card!, "Agregar al carro");
    // A card's button adds one each press; the window that confirms it is
    // closed before the next.
    for (; left > 0; left--) {
      if (left < qty) {
        await closeAdded();
        await sleep(400);
      }
      const was = storedQty(id);
      c.progress("waiting_site");
      press(button);
      if (!(await waitFor(() => storedQty(id) > was, 9000))) {
        if (left === qty) throw new Error("pressed Agregar al carro, but the cart did not change; ask the visitor to check the cart");
        break;
      }
      await waitFor(addedModal, 2500);
    }
  }
  await sleep(300);
  const cart = await readCart();
  reportCart(cart);
  const line = cart.items.find((l) => l.path === productPath(id));
  const name = line?.name || (pdp ? readProduct()?.name : cardName(card!)) || productPath(id);
  const added = storedQty(id) - start;
  // The confirmation is the effect: ringed, left up long enough to read, then
  // closed with its own "Seguir comprando" (`commerce.cart_show` opens the
  // cart instead).
  c.after(async () => {
    const modal = addedModal();
    if (!modal) return;
    await c.ring(modal.querySelector(".modal-content") ?? modal, "Producto agregado");
    await sleep(2200);
    if (addedModal()) await closeAdded();
  });
  const detail = `added ${added} x ${name}${line ? ` (the cart line now has ${line.qty})` : ""}; ${cartLine(cart)}`;
  if (added < qty) return { outcome: "partial", detail, refused: [{ arg: "qty", why: `only ${added} of ${qty} went in`, options: [] }] };
  return detail;
}

async function showCart(p: { open?: boolean } & Arrived, c: MoveContext): Promise<string | null> {
  if (p.open === false) {
    const modal = addedModal();
    if (!modal) return "nothing of the cart was open";
    const close = modal.querySelector<HTMLElement>(".btn-close-cart") ?? modal;
    await c.ring(close);
    await closeAdded();
    c.spotlight.clear();
    return "closed the Producto agregado window";
  }
  if (kindOf() !== "cart") {
    if (p.arrived) throw new Error(`the cart did not open (now on ${location.pathname})`);
    const link =
      [...(addedModal()?.querySelectorAll<HTMLElement>("a[href$='/carro']") ?? [])].find(shown) ??
      [...document.querySelectorAll<HTMLElement>("#header a[href$='/carro'], header a[href$='/carro']")].find(shown);
    if (link) await c.ring(link, "Carro");
    return load(c, "/carro", again(c, p));
  }
  await waitFor(() => cartRows().length || /vac[ií]o|no tienes/i.test(clean(main().textContent).slice(0, 4000)), 8000);
  await quiet(main(), 300, 1500);
  const cart = await readCart();
  reportCart(cart);
  c.after(async () => {
    await scrollToTopOfPage();
    const parts = [document.querySelector(".title-count-cart"), ...cartRows().slice(0, 3), document.querySelector("aside.purchase-summary")].filter(
      (x): x is Element => x !== null && visible(x),
    );
    if (parts.length) await c.ring(parts, "Tu carro");
  });
  return `the cart is on screen; ${cartLine(cart)}${cart.items.length ? `: ${cart.items.map((i) => `${i.qty} × ${i.name}`).join("; ")}` : ""}`;
}

/** How many presses one change may take. */
const MAX_CART_STEPS = 12;

async function onCart(c: MoveContext, p: object & Arrived): Promise<boolean> {
  if (kindOf() !== "cart") {
    if (p.arrived) throw new Error(`the cart did not open (now on ${location.pathname})`);
    await load(c, "/carro", again(c, p));
    return false;
  }
  await waitFor(() => cartRows().length, 8000);
  await quiet(main(), 300, 1500);
  return true;
}

async function updateCartItem(p: { path: string; qty: number } & Arrived, c: MoveContext): Promise<string | null> {
  const id = productId(p.path);
  if (!id) c.refuse("path", "say which product, as /producto/<id>");
  const qty = Math.round(Number(p.qty));
  if (!Number.isFinite(qty) || qty < 0 || qty > 20) c.refuse("qty", `a quantity from 0 to 20, not ${p.qty}`);
  if (!(await onCart(c, p))) return null;
  const rowOf = () => cartRows().find((r) => Number(r.getAttribute("data-gtag-id")) === id) ?? null;
  const row = rowOf();
  if (!row) c.refuse("path", `${productPath(id)} is not in the cart`, cartFromPage().items.map((i) => `${i.name} (${i.path})`));
  const name = clean(row.getAttribute("data-gtag-name"));
  await scrollTo(row, "center");
  if (qty === 0) {
    const remove = [...row.querySelectorAll<HTMLElement>("a[href='#delete-product-modal'], .pcf-link-vaciar")].find(shown);
    if (!remove) throw new Error("the cart line has no Eliminar");
    await c.ring(row, `Eliminar ${name}`);
    press(remove);
    const dialog = await waitFor(() => document.querySelector<HTMLElement>("#delete-product-modal.show"), 3000);
    const confirm = [...(dialog ?? document).querySelectorAll<HTMLElement>("#delete-product-modal button")].find((b) => /^eliminar$/i.test(clean(b.textContent)));
    if (!confirm) throw new Error("the cart's ¿Confirmas…? window did not open; nothing was removed");
    if (dialog) await c.ring(dialog.querySelector(".modal-content") ?? dialog, "Eliminar");
    c.progress("waiting_site");
    press(confirm);
    if (!(await waitFor(() => !rowOf() && storedQty(id) === 0, 8000))) throw new Error("pressed Eliminar, but the line is still in the cart");
  } else {
    await c.ring(row, `${name}: ${qty}`);
    for (let step = 0; step < MAX_CART_STEPS; step++) {
      const r = rowOf();
      if (!r) throw new Error("the cart line went away");
      const now = rowQty(r);
      if (now === qty) break;
      const button = r.querySelector<HTMLElement>(now < qty ? "button.pcf-value-button.positive" : "button.pcf-value-button.negative");
      if (!button || (button as HTMLButtonElement).disabled) throw new Error(`the cart's ${now < qty ? "+" : "−"} cannot be pressed at ${now}`);
      c.progress("waiting_site");
      press(button);
      if (!(await waitFor(() => rowOf() && rowQty(rowOf()!) !== now, 6000))) throw new Error(`pressed ${now < qty ? "+" : "−"}, but the line stayed at ${now}`);
      await sleep(250);
    }
    const r = rowOf();
    if (!r || rowQty(r) !== qty) throw new Error(`the line shows ${r ? rowQty(r) : 0}, not ${qty}`);
  }
  await quiet(main(), 400, 2500);
  const cart = await readCart();
  reportCart(cart);
  const summary = document.querySelector("aside.purchase-summary");
  if (summary) c.after(() => c.ring(summary));
  return `${qty === 0 ? `removed ${name}` : `${name} set to ${qty}`}; ${cartLine(cart)}`;
}

async function applyCoupon(p: { code: string } & Arrived, c: MoveContext): Promise<string | null> {
  const code = clean(p.code).toUpperCase();
  if (!code) c.refuse("code", "say the coupon's code, as the site writes it (LEN50)");
  if (!(await onCart(c, p))) return null;
  const input = [...document.querySelectorAll<HTMLInputElement>("input.cupon-input")].find(shown);
  if (!input) throw new Error("the cart shows no Cupón de descuento box");
  const section = input.closest<HTMLElement>(".purchase-summary__coupon-section, .cupon-descuento") ?? input;
  await scrollTo(section, "center");
  await c.ring(section, `Cupón ${code}`);
  await typeInto(input, code, 110);
  const button = await waitFor(() => {
    const b = section.querySelector<HTMLButtonElement>("button.cupon-btn") ?? document.querySelector<HTMLButtonElement>("button.cupon-btn");
    return b && !b.disabled ? b : null;
  }, 3000);
  if (!button) throw new Error("the coupon box's Aplicar stays disabled");
  await c.ring(button, "Aplicar");
  const before = new Set([...section.querySelectorAll<HTMLElement>("p, span, small, div")].map((e) => clean(e.textContent)));
  const totalBefore = summaryTotal();
  const since = Date.now();
  c.progress("waiting_site");
  press(button);
  await apiSettled(since, 8000);
  await quiet(main(), 400, 2500);
  // The store's answer: what the coupon section says now that it did not.
  const said = [...section.querySelectorAll<HTMLElement>("p, span, small, div")]
    .filter((e) => !e.children.length || e.matches("p, small"))
    .map((e) => clean(e.textContent))
    .filter((t) => t && !before.has(t) && !/^cup[oó]n de descuento$/i.test(t) && t !== code && t.length < 200);
  const message = [...new Set(said)].join(" ") || clean(document.querySelector(".cupon-body .invalid-feedback, .cupon-body .text-danger, .cupon-body .text-success")?.textContent);
  const cart = await readCart();
  reportCart(cart);
  c.after(async () => {
    const s = document.querySelector("aside.purchase-summary");
    if (s) await c.ring(s);
  });
  const total = summaryTotal();
  return `pressed Aplicar for ${code}; the store says: "${message || "nothing"}"; total transferencia ${totalBefore != null && total != null && total !== totalBefore ? `$${totalBefore} → $${total}` : `$${total ?? "?"}`}`;
}

// start_checkout ────────────────────────────────────────────────────────────

/** The checkout as far as Tipo de entrega: the cart's "Continuar" (a full
 *  load to /checkout), then "Continuar como invitado", then the delivery
 *  choice reported, never made. Each step carries the rest of the move. */
async function startCheckout(p: Arrived & { step?: string }, c: MoveContext): Promise<string | null> {
  if (kindOf() === "cart") {
    await waitFor(() => cartRows().length, 8000);
    if (!cartRows().length) throw new Error("the cart is empty; add something first");
    const go = [...document.querySelectorAll<HTMLElement>("aside.purchase-summary a[aria-label='ir al checkout']")].find(shown);
    if (!go) throw new Error("the cart shows no Continuar");
    await scrollTo(go, "center");
    await c.ring(go, "Continuar");
    // "Continuar" loads /checkout itself; the rest of the move waits there.
    await c.keep(again(c, { step: "login" }));
    c.progress("waiting_site");
    press(go);
    if (!(await waitFor(() => checkoutStep(location.pathname), 12_000))) {
      await c.drop();
      throw new Error("pressed Continuar, but the checkout did not open");
    }
    // Still here: the site moved to /checkout without a load.
    await sleep(1500);
  } else if (!checkoutStep(location.pathname)) {
    if (p.arrived) throw new Error(`the cart did not open (now on ${location.pathname})`);
    return load(c, "/carro", again(c, {}));
  }
  if (checkoutStep(location.pathname) === "login") {
    const guest = await waitFor(guestButton, 12_000);
    if (!guest) throw new Error("the checkout's first step shows no Continuar como invitado");
    report("checkout_state", readCheckout());
    await scrollTo(guest, "center");
    await c.ring(guest, "Continuar como invitado");
    await c.keep(again(c, { step: "delivery" }));
    c.progress("waiting_site");
    press(guest);
    // Its own router may move to Tipo de entrega without a load.
    if (!(await waitFor(() => checkoutStep(location.pathname) === "delivery" && methodOptions().length, 12_000))) {
      throw new Error("pressed Continuar como invitado, but Tipo de entrega did not open");
    }
  }
  await waitFor(() => methodOptions().length, 12_000);
  const state = readCheckout();
  report("checkout_state", state);
  if (state.step !== "delivery") throw new Error(`the checkout is on ${state.step}, not Tipo de entrega`);
  const choices = [...document.querySelectorAll<HTMLElement>(".method-option")].filter(shown);
  if (choices.length) {
    await scrollTo(choices[0]!.closest("section")?.parentElement ?? choices[0]!, "center");
    await c.ring(choices, "Tipo de entrega");
  }
  return `on Tipo de entrega as a guest; the visitor chooses: ${state.options.join(" or ")}. Javier stops here: the choice, the RUT, the address and the payment are theirs`;
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
    if (link) await c.ring(link);
    return load(c, to.pathname + to.search + to.hash);
  }
  await scrollToTopOfPage();
  const title = headings()[0]?.el ?? document.querySelector("#product-title");
  if (title) await c.ring(title);
  return `${location.pathname} is on screen`;
}

/** On `path` first, when the cue names another page: the rest goes there. */
async function onPage(c: MoveContext, path: string | null | undefined, then: Then): Promise<boolean> {
  if (!path) return true;
  const to = new URL(path, location.origin);
  if (samePath(location.pathname, to.pathname) && (!to.search || to.search === location.search)) return true;
  await load(c, to.pathname + to.search, then);
  return false;
}

const original = (el: Element | null | undefined) => el?.getAttribute("data-voqalize-text") ?? "";

function findHeading(heading: string): HTMLElement | null {
  const all = headings();
  return best(all, (x) => x.text, heading)?.el ?? best(all, (x) => original(x.el), heading)?.el ?? null;
}

const rank = (h: Element) => Number(h.tagName.slice(1)) || 6;

/** What a heading heads: the largest block around it that holds no other
 *  heading of its rank and fits on the screen, else the heading and the
 *  blocks after it. */
function sectionOf(h: HTMLElement): HTMLElement[] {
  let found: HTMLElement | null = null;
  for (let el = h.parentElement; el && el !== main() && el !== document.body; el = el.parentElement) {
    const others = [...el.querySelectorAll("h1, h2, h3")].filter((x) => x !== h && shown(x) && !x.closest(NOT_HEADINGS));
    if (others.some((x) => rank(x) <= rank(h))) break;
    const b = boxOf([el]);
    if (b && b.bottom - b.top > window.innerHeight * 1.1) break;
    found = el;
  }
  return found && clean(found.textContent).length > clean(h.textContent).length + 20 ? [found] : [h, ...answerAfter(h)];
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

/** Product cards on the page, in the grid and in the home's rails (a rail's
 *  looped copies left out). */
function productCards(): { el: HTMLElement; name: string }[] {
  const out: { el: HTMLElement; name: string }[] = cards().map((a) => ({ el: a as HTMLElement, name: cardName(a) }));
  for (const slide of main().querySelectorAll<HTMLElement>(".rr-swiper-slide:not(.swiper-slide-duplicate), .rr-item")) {
    const item = slide.matches(".rr-item") ? slide : (slide.querySelector<HTMLElement>(".rr-item") ?? slide);
    const name = clean(slide.getAttribute("data-name") ?? item.querySelector(".rr-item__name")?.textContent);
    if (name && !out.some((o) => o.el === item || o.el.contains(item))) out.push({ el: item, name });
  }
  return out;
}

/** Whether `el` is on the screen sideways (a carousel's card can be off its
 *  edge). */
const inViewSideways = (el: Element) => {
  const r = el.getBoundingClientRect();
  return r.left >= -4 && r.right <= window.innerWidth + 4;
};

async function ringThere(c: MoveContext, el: HTMLElement | HTMLElement[], label: string): Promise<void> {
  const els = Array.isArray(el) ? el : [el];
  const box = boxOf(els);
  const tall = box ? box.bottom - box.top > window.innerHeight - headerHeight() - 40 : false;
  await scrollTo(els[0]!, tall ? "top" : "center");
  await c.ring(els, label);
}

/** The show cue: a heading of the page with what it heads; a specification
 *  row by its label (the Especificaciones tab opened first); a store, a
 *  coupon or a product card by its name; a question; or, when nothing is
 *  called that, the smallest block with those words. */
async function showSection(p: { target: string; path?: string | null }, c: MoveContext): Promise<string | null> {
  const want = clean(p.target);
  if (!want) c.refuse("target", "say which heading or words to show");
  if (!(await onPage(c, p.path, { move: c.move, args: { target: want, path: null } }))) return null;
  // The rails and the store list render after the page: wait for the words.
  await waitFor(() => findHeading(want) || smallestContaining(main(), want), 3000);

  if (onProductPage()) {
    const tabs: Record<string, Tab> = { "sobre este producto": "about", especificaciones: "specs", garantia: "warranty", disponibilidad: "stock", fotos: "photos" };
    const tab = tabs[norm(want)];
    if (tab) return `${await productTab({ tab }, c)}`;
    const row = best(specRows(), (r) => r.label, want);
    if (row && norm(row.label).length >= Math.min(4, norm(want).length)) {
      await openTab("specs", c, false);
      await ringThere(c, row.row, `${row.label}: ${row.value}`);
      return `showed ${row.label}: ${row.value}`;
    }
  }
  const h = findHeading(want);
  if (h) {
    await ringThere(c, sectionOf(h), clean(h.textContent));
    return `showed "${clean(h.textContent)}"`;
  }
  if (kindOf() === "stores") {
    const all = storeCards().filter((s) => shown(s.el));
    const hit = all.find((s) => s.name === storesMeant(want, all.map((x) => x.name))[0]);
    if (hit) {
      await ringThere(c, hit.el, hit.name);
      return `showed the store ${hit.name}: ${hit.address}, ${hit.city}`;
    }
  }
  const coupon = [...main().querySelectorAll<HTMLElement>(".ticket-col")].find(
    (t) => norm(t.querySelector(".ticket-cupon-text")?.textContent) === norm(want) || norm(t.textContent).includes(norm(want)),
  );
  if (coupon && shown(coupon)) {
    await ringThere(c, coupon.querySelector<HTMLElement>(".ticket-pseudo") ?? coupon, clean(coupon.querySelector(".ticket-cupon-text")?.textContent) || want);
    const part = (sel: string) => clean(coupon.querySelector(sel)?.textContent);
    const what = [part(".ticket-card-monto"), part(".ticket-card-subtitle"), part(".ticket-card-productos")].filter(Boolean).join(" ");
    return `showed the coupon ${part(".ticket-cupon-text")}: ${what}${part(".ticket-card-vencimiento") ? `; ${part(".ticket-card-vencimiento")}` : ""}`;
  }
  const all = productCards();
  const card = best(all.filter((x) => shown(x.el) && inViewSideways(x.el)), (x) => x.name, want) ?? best(all.filter((x) => shown(x.el)), (x) => x.name, want);
  if (card) {
    await ringThere(c, card.el, card.name);
    return `showed the product ${card.name}`;
  }
  const faq = best(faqItems(), (f) => f.question, want);
  if (faq) return openFaq({ question: faq.question }, c);
  const el = smallestContaining(main(), want);
  if (!el) c.refuse("target", `no heading or words "${want}" on ${location.pathname}`, context().headings.slice(0, 25));
  await ringThere(c, el, want);
  return `showed "${want}"`;
}

/** The faq cue: the question ringed, opened, and ringed with its answer. */
async function openFaq(p: { question: string; path?: string | null }, c: MoveContext): Promise<string | null> {
  const question = clean(p.question);
  if (!question) c.refuse("question", "say which question");
  if (!(await onPage(c, p.path, { move: c.move, args: { question, path: null } }))) return null;
  await waitFor(() => faqItems().length, 3000);
  const all = faqItems();
  const item = best(all, (f) => f.question, question) ?? best(all, (f) => original(f.block), question);
  if (!item) c.refuse("question", `no question "${question}" on ${location.pathname}`, all.map((f) => f.question).slice(0, 15));
  await scrollTo(item.block, "center");
  if (!item.isOpen() && item.toggle) {
    await c.ring(item.block, item.question);
    press(item.toggle);
    if (!(await waitFor(item.isOpen, 2000))) {
      // No Bootstrap to animate it open (a saved copy): open it as it would.
      for (const a of item.answer()) a.classList.add("show");
    }
    await sleep(300);
  }
  const group = [item.block, ...item.answer()];
  const box = boxOf(group);
  await scrollTo(item.block, box && box.bottom - box.top > window.innerHeight * 0.7 ? "top" : "center");
  await c.ring(group, item.question);
  return `opened "${item.question}"`;
}

// ─── Registering the moves ────────────────────────────────────────────────

/** Every move this page makes, by the id the brain names it with: its class,
 *  a cue's argument names and the arguments' types come from
 *  `pcfactory/scene.json`, and a move left out does not compile. */
export function registerMoves(moves: Moves): void {
  who = () => moves.author();
  scene.registerAll(moves, {
    "page.open": openPage,
    "page.show": showSection,
    "page.faq": openFaq,
    "product.tab": productTab,
    "stores.show": showStore,
    "commerce.filter": filterCue,
    "commerce.sort": sortCue,
    "commerce.search": searchProducts,
    "commerce.cart_add": addToCart,
    "commerce.cart_update": updateCartItem,
    "commerce.cart_show": showCart,
    "compare.add": compareAdd,
    filter_listing: filterListing,
    open_product: openProduct,
    find_products: findProducts,
    check_prices: checkPrices,
    check_stock: checkStock,
    apply_coupon: applyCoupon,
    start_checkout: startCheckout,
  });
}

// ─── Watching the page ────────────────────────────────────────────────────

let lastUrl: string | null = null;

/** The URL changed without a load (the listing's replaceState after a filter,
 *  the checkout's router): the page is reported again. */
function urlChanged(): void {
  const here = location.origin + location.pathname + location.search;
  if (here === lastUrl) return;
  lastUrl = here;
  if (emitter) emitter("page_changed", context());
  if (kindOf() === "checkout") reportCheckout();
}

function watchUrl(): void {
  lastUrl = location.origin + location.pathname + location.search;
  for (const name of ["pushState", "replaceState"] as const) {
    const before = history[name].bind(history);
    history[name] = (...args: Parameters<History["pushState"]>) => {
      const out = before(...args);
      queueMicrotask(urlChanged);
      return out;
    };
  }
  window.addEventListener("popstate", urlChanged);
  window.addEventListener("hashchange", urlChanged);
}

/** `fn` once changes pause for `ms`, and at least every `most` while they
 *  never pause (the rails' carousels move all the time). */
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

/** The cart, whoever changed it: the site writes `localStorage.cartProducts`
 *  on every add and − / +, in this tab (watched at the write) or another (the
 *  `storage` event). */
let watchingCart = false;
const cartChanged = debounced(() => void readCart().then(reportCart), 600, 2500);
function watchCart(): void {
  if (watchingCart) return;
  watchingCart = true;
  const setItem = Storage.prototype.setItem;
  Storage.prototype.setItem = function (this: Storage, key: string, value: string) {
    const out = setItem.call(this, key, value);
    if (key === "cartProducts" && this === window.localStorage) cartChanged();
    return out;
  };
  window.addEventListener("storage", (e) => {
    if (e.key === "cartProducts") cartChanged();
  });
}

/** Grid updates (filters, sort) on a listing, the cart page's lines and the
 *  checkout's steps, each reported when it settles. */
function watchState(): () => void {
  const observers: MutationObserver[] = [];
  const watch = (el: Element | null, fn: () => void, ms?: number) => {
    if (!el) return;
    const obs = new MutationObserver(debounced(fn, ms));
    obs.observe(el, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["class"] });
    observers.push(obs);
  };
  if (isListing()) {
    watch(main(), () => {
      urlChanged();
      if (gridUp()) report("listing_shown", readListing());
    });
  }
  if (kindOf() === "product") {
    watch(main(), () => {
      const product = readProduct();
      if (product) report("product_shown", latestProductFor(product));
    }, 800);
  }
  if (kindOf() === "checkout") watch(main(), reportCheckout, 600);
  return () => observers.forEach((o) => o.disconnect());
}

/** This page's state, read now: the product, the listing, the checkout, the
 *  cart. */
function readState(): void {
  const kind = kindOf();
  if (kind === "product") {
    // The page's read first (the Vue widget renders after the page settles),
    // then the store's live one.
    void waitFor(productUp, 10_000).then(() => {
      const product = readProduct();
      if (product) report("product_shown", latestProductFor(product));
      void confirmProduct();
    });
  } else if (kind === "category" || kind === "search") {
    if (gridUp()) report("listing_shown", readListing());
  } else if (kind === "checkout") reportCheckout();
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

/** Ready the page, once: its style, the URL, API and cart watches, and its
 *  state read as soon as it settles (a page that loads mid-call reports it the
 *  moment it listens). */
export function prepare(): void {
  if (prepared) return;
  prepared = true;
  styleThePage();
  watchUrl();
  watchApi();
  watchCart();
  void settled().then(readState);
}

/** The page in front, as it stands: once the agent can hear this page (before
 *  `start`), and again each time the tab comes back to the front (Stage's
 *  host runs it). */
export function reportPage(next: (event: string, payload: unknown) => void): void {
  next("page_changed", context());
}

/** PC Factory's adapter for `@voqalize/stage/extension`: its moves, what the
 *  visitor is looking at for the session's start, and its reports. */
export const pcfactory: Adapter = (moves, kit) => {
  registerMoves(moves);
  who = () => kit.author();
  prepare();
  return {
    context: () => {
      const ctx = context();
      return { site: ctx.site, path: ctx.path, url: ctx.url, title: ctx.title, kind: ctx.kind };
    },
    report: reportPage,
    start,
    // The Vue widgets mount after the page is parsed, and `load` waits on
    // trackers: a press waits for the page to settle, never for `load`.
    ready: settled,
  };
};

// Exported for the end-to-end tests.
export { context, readCart, readCheckout, readListing, readProduct };
