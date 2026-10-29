/**
 * The site adapter: drive www.agroplanet.cl from the outside, with no help
 * from Agroplanet's developers.
 *
 * Javier's moves arrive through Stage (`@voqalize/stage`): each is a move
 * registered here (`registerMoves`), made on the page in front, one at a
 * time, ringed with the spotlight before it acts, and answered with one
 * `stage_result`. The page reports what it shows through `start`, which calls
 * `emit(event, payload)`, whoever moved it:
 *
 *   - `page_changed` for every page the visitor lands on, whoever took them,
 *     on every route change of the app as well as on a load;
 *   - `prices_read`, `products_found`, `stock_read`, `fit_read` and
 *     `store_shown` for the moves that read them.
 *
 * What their screen holds is Stage state (`agroplanet/scene.json`): each
 * change goes as a named `stage_event` (`scene.event`), with only the fields
 * its slice declares, and `by: "agent"` with the move's `call_ref` when one
 * of Javier's moves made it:
 *
 *   - `product.shown` on a product page, read from the page, then
 *     `product.checked` from the store's own API (`product/getProductDetail`);
 *   - `listing.shown` on a category, search or brand listing, and
 *     `listing.filtered` / `listing.sorted` after the grid changes on the same
 *     listing, whoever changed it;
 *   - `cart.changed` whenever the cart changes (the app's `cart/add`,
 *     `cart/update`, `cart/delete`), read from `minicart/cart/rollover`;
 *   - `quote.changed` on the Formulario de cotización, on arrival and after a
 *     change: which fields are filled and which are missing, never a value.
 *
 * The site, for a script like this: one Angular app (Angular Material) over a
 * JSON API at `api.agroplanet.cl/webapi/` whose session is a cookie, so the
 * reads here call it with the visitor's own cookies and see their cart. Every
 * move between pages is the app's router: no load. A move to another page
 * moves the app there itself (`navigate`: the page's own link when one is on
 * screen, else the router's `pushState` + `popstate`), waits for the route to
 * draw, and finishes in place; only if the route never draws does it fall
 * back to a full load that carries the rest of the move (`load`). Because no
 * load comes between pages, every route change re-reads the page and picks
 * its watchers again (`urlChanged`).
 *
 * Nothing here goes past the quote form: every click goes through `press`,
 * every route and load through `target`, every keystroke through `typeInto`
 * (`page.ts`). They refuse the login, the RUT, "Crear cotización" and any
 * payment.
 */

import type { MoveContext, Moves, PerformResult, Refusal, StageEvent } from "@voqalize/stage";
import type { Adapter } from "@voqalize/stage/extension";

import type { FitBrand, FitRead, FoundItem, PriceItem, PricesRead, ProductsFound, StockRead, StoreShown } from "./actions.gen";
import { scene } from "./scene.gen";

import {
  apiIdle, apiSettled, bare, best, boxOf, clean, closeSplash, enter, guardSplash, headerHeight, hover, inOrder, leave, money, norm, onApi, ownFetch, pathOf, press, productPath,
  productSku, QUOTE_FIELDS, quiet, routeTo, samePath, scrollTo, scrollToTopOfPage, SEARCH_BOX, settled, shown, sleep, styleThePage, target,
  typeInto, visible, waitFor, watchApi,
} from "./page";

export type Kind = "home" | "category" | "search" | "brand" | "product" | "cart" | "quote" | "stores" | "policy" | "page";
export interface PageContext {
  site: string;
  url: string;
  path: string;
  title: string;
  kind: Kind;
  /** Section headings a visitor can be taken to, in page order. */
  headings: string[];
  /** The accordion panel titles on the page. */
  faqs: string[];
}

const SITE_NAME = "www.agroplanet.cl";
const API = "https://api.agroplanet.cl/webapi";
const MAX_HEADINGS = 80;
const MAX_FAQS = 80;
const MAX_LISTED = 12;
/** A facet's options, all of them: an option cut from the report is one
 *  Javier says is not there (pcfactory dev call 8b363867). The cap only
 *  guards against a runaway list. */
const MAX_OPTIONS = 120;
const MAX_SPECS = 40;
const MAX_FOUND = 8;
const MAX_PRICED = 6;
const REPORT_DEBOUNCE_MS = 450;
/** How long a route may take to draw before a move gives up on moving the
 *  app and loads the page instead. */
const ROUTE_MS = 12_000;

// ─── Where we are ─────────────────────────────────────────────────────────

/** The policy pages: accordions of the store's terms. */
const POLICY = /^\/(politica-despacho|garantia-devoluciones|cambios-devoluciones|politica-proteccion-datos|politicas-de-privacidad|politica-transparencia|terminos-y-condiciones|bases-promociones-vigentes)$/;

/** What sort of page this is, from the app's route (no translator touches
 *  an address). */
export function kindOf(): Kind {
  const p = decodeURIComponent(location.pathname).toLowerCase().replace(/\/+$/, "") || "/";
  if (p === "/" || p === "/inicio") return "home";
  if (p.startsWith("/producto/")) return "product";
  if (p.startsWith("/categoria/")) return "category";
  if (p.startsWith("/busqueda/")) return "search";
  if (p.startsWith("/marca/")) return "brand";
  if (p === "/carro") return "cart";
  if (p === "/cotizacion" || p.startsWith("/cotizacion/")) return "quote";
  if (p === "/nuestras-tiendas") return "stores";
  if (POLICY.test(p)) return "policy";
  return "page";
}

/** The page's content: the app's content pane (the header, menu and footer
 *  are inside it too, and left out by `CHROME`). */
const main = (): HTMLElement =>
  document.querySelector<HTMLElement>("app-master mat-sidenav-content") ?? document.querySelector<HTMLElement>("app-root") ?? document.body;

/** The route's own component: what the router swaps on every move. */
function routeEl(): HTMLElement | null {
  const outlets = main().querySelectorAll("router-outlet");
  const last = outlets[outlets.length - 1];
  return (last?.nextElementSibling as HTMLElement | null) ?? null;
}

/** Not the page's content: the top bar, the header and its sticky copy, the
 *  category menu, the breadcrumb, the footer, Material's overlays, the
 *  cookie bar, WhatsApp, and our own. */
const CHROME = [
  "#appTopBar", "app-top-bar", "app-header-desktop", "app-sticky-header-desktop", "app-menu-desktop", "app-breadcrumb", "app-footer",
  ".cdk-overlay-container", ".cookies-wrapper", ".whatsapp-float", ".back-to-top", "[data-voqalize]",
].join(", ");
const inChrome = (el: Element) => Boolean(el.closest(CHROME));

/** The section titles the app writes as styled text rather than headings: the
 *  home's rails ("Aprovecha estas oportunidades…", "CATEGORÍAS"), the product
 *  page's "Detalle del Producto" and "Especificaciones", the cart's and the
 *  quote's cards. */
const SECTION_TITLES = [
  "app-category-home div.fw-700.fs18",
  "app-product-tabs .title p",
  "app-cart .bb-spec p.fw-bold",
  "app-form-user-quote span.fs18",
  "app-resumen span.fs-16.fw-700",
].join(", ");

/** Things the adapter matches by their own kind (cards, panels, rows), not
 *  as headings. */
const NOT_HEADINGS = "app-plp-filter, app-plp-grid, mat-expansion-panel-header, app-product-card, app-store-list mat-card, .h1-SEO";

interface Faq {
  question: string;
  block: HTMLElement;
  toggle: HTMLElement | null;
  isOpen: () => boolean;
  answer: () => HTMLElement[];
}

/** The page's accordion panels (the policy pages are nothing else): each
 *  `mat-expansion-panel`, its title the question; not the filter panel's, the
 *  menu's, the footer's or the phone copy of the product's details. */
function faqItems(): Faq[] {
  const items: Faq[] = [];
  for (const panel of main().querySelectorAll<HTMLElement>("mat-expansion-panel")) {
    if (inChrome(panel) || panel.closest("app-plp-filter, app-product-tabs, #comentarProductoMobile")) continue;
    const header = panel.querySelector<HTMLElement>(":scope > mat-expansion-panel-header");
    const title = header?.querySelector<HTMLElement>("mat-panel-title");
    if (!header || !title) continue;
    const first = title.querySelector<HTMLElement>("h1, h2, h3, h4, h5, p, span");
    const question = clean(first?.textContent) || clean(title.textContent);
    if (!question) continue;
    items.push({
      question,
      block: panel,
      toggle: header,
      isOpen: () => panel.classList.contains("mat-expanded"),
      answer: () => [panel.querySelector<HTMLElement>(".mat-expansion-panel-content")].filter((x): x is HTMLElement => x !== null),
    });
  }
  return items.sort((a, b) => inOrder(a.block, b.block));
}

interface Head {
  el: HTMLElement;
  text: string;
}

function headings(): Head[] {
  const found: Head[] = [];
  for (const h of main().querySelectorAll<HTMLElement>(`h1, h2, h3, h4, ${SECTION_TITLES}`)) {
    if (inChrome(h) || h.closest(NOT_HEADINGS) || !shown(h)) continue;
    const text = clean(h.innerText || h.textContent).replace(/\s*\|\s*$/, "");
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

/** The route in front has drawn what its kind shows. */
function routeUp(kind = kindOf()): boolean {
  switch (kind) {
    case "home":
      // Its rails' titles come from the CMS after the route draws.
      return Boolean(document.querySelector("app-category-home div.fw-700.fs18"));
    case "product":
      return Boolean(document.querySelector("app-product-info h2.black-name"));
    case "category":
    case "search":
    case "brand":
      return gridUp();
    case "cart":
      return Boolean(document.querySelector("app-cart-product") || /vac[ií]o|empty/i.test(clean(document.querySelector("app-cart")?.textContent)));
    case "quote":
      return Boolean(document.querySelector("app-form-user-quote form") || (document.querySelector("app-quote") && !document.querySelector("app-form-user-quote")));
    case "stores":
      return Boolean(document.querySelector("app-store-list mat-card"));
    default:
      return clean(routeEl()?.textContent).length > 20;
  }
}

// ─── Reporting ────────────────────────────────────────────────────────────

let emitter: ((event: string, payload: unknown) => void) | null = null;
/** The latest of each state report on this page, and what each listener was
 *  last sent, so a report is sent once and a late listener gets the latest. */
const latest = new Map<string, unknown>();
const sent = new WeakMap<object, Map<string, string>>();

/** A state report (product, listing, cart, quote): sent unless this listener
 *  already has exactly it. */
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

/** A read a move made (prices, products, stock, a store): sent every time,
 *  since the brain asked for it. */
function told(event: string, payload: unknown): void {
  emitter?.(event, payload);
}

/** Who changed what the page reports now: the page kit's answer (his move
 *  acting, just done, or carried here and not yet made; else the visitor). */
let who: () => { by: "visitor" | "agent"; callRef?: string } = () => ({ by: "visitor" });

/** The listing last reported in this tab, kept across a load: a new report of
 *  the same one is a filter or a sort, not a new listing. */
const LAST_LISTING = "voqalize.agroplanet.listing";
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
      const filters = JSON.stringify(l.filters.map((f) => [f.facet, f.on]));
      const sort = l.sort ?? "";
      const before = lastListing();
      const same = before !== null && before.path === l.path;
      const name = same && before.filters !== filters ? "listing.filtered" : same && before.sort !== sort ? "listing.sorted" : "listing.shown";
      sawListing({ path: l.path, filters, sort });
      ev = scene.event(name, l, by);
      break;
    }
    case "cart_state":
      ev = scene.event("cart.changed", payload as CartState, by);
      break;
    case "quote_state":
      ev = scene.event("quote.changed", payload as QuoteState, by);
      break;
  }
  return ev ? ["stage_event", ev] : [event, payload];
}

// ─── The store's API ──────────────────────────────────────────────────────

/** The API's envelope: `{statusCode, isValid, data}`. */
interface Envelope<T> {
  statusCode?: number;
  isValid?: boolean;
  data?: T;
}

/** A GET to the store's API with the visitor's own cookies (its CORS allows
 *  www.agroplanet.cl with credentials), as the app's own calls go: the cart
 *  read here is theirs. */
async function getJson<T>(url: string): Promise<T> {
  const r = await ownFetch(url, { credentials: "include", headers: { accept: "application/json" } });
  if (!r.ok) throw new Error(`the store's API answered ${r.status} for ${new URL(url).pathname}`);
  const env = (await r.json()) as Envelope<T>;
  if (env.isValid === false || env.data == null) throw new Error(`the store's API had no answer for ${new URL(url).pathname}`);
  return env.data;
}

interface ApiPrice {
  value?: number | null;
  formattedValue?: string;
}
interface ApiStock {
  stockLevelStatus?: { code?: string } | null;
  stockLevel?: number | null;
}
interface ApiProduct {
  code: string;
  name?: string;
  brand?: string | null;
  description?: string | null;
  summary?: string | null;
  manufacturer?: string | null;
  manufacturerCode?: string | null;
  price?: ApiPrice | null;
  hidePriceByCategory?: boolean | null;
  stock?: ApiStock | null;
  unitInBox?: number | null;
  country?: { name?: string } | null;
  ancho?: number | null;
  altura?: number | null;
  longitud?: number | null;
  pesoBruto?: number | null;
  hidePesoBruto?: boolean | null;
  /** The store's offer: the pages hide it (`hideDiscount`), the mini-cart's
   *  subtotal applies it. */
  discountedPrice?: ApiPrice | null;
  discountPercentage?: number | null;
  /** The badges over the brand: `{LABEL1: {value: "Venta en Verde", visible}}`. */
  labelProductInfoMap?: Record<string, { value?: string | null; visible?: boolean | null } | null> | null;
  breadCrumb?: { name?: string | null; categoryCode?: string | null }[] | null;
  /** The data sheets: `[{name: "Ficha Técnica", url}]`. */
  data_sheet?: { name?: string | null; url?: string | null }[] | null;
  /** Feature groups; `C_DTE_EQUIVALENCIA_*` are the Equivalencias. */
  classifications?: { code?: string; name?: string; features?: { name?: string; featureValues?: { value?: string }[] | null }[] | null }[] | null;
}

const productApi = (sku: string) => getJson<ApiProduct>(`${API}/product/getProductDetail?productCode=${encodeURIComponent(sku)}`);

/** Pesos as integers; the API writes them as 80000.0. */
const pesos = (n: unknown): number | null => (typeof n === "number" && Number.isFinite(n) && n > 0 ? Math.round(n) : null);

type StockStatus = "inStock" | "lowStock" | "outOfStock" | "";
const stockStatus = (s: ApiStock | null | undefined): StockStatus => {
  const code = s?.stockLevelStatus?.code ?? "";
  return code === "inStock" || code === "lowStock" || code === "outOfStock" ? code : "";
};

/** The store's offer on a product, when it has a real one below the price
 *  its page shows: the price the mini-cart's subtotal charges and its
 *  percentage. A hidden price has none. */
function offerOf(p: ApiProduct): { offer_price: number; discount: number } | null {
  if (p.hidePriceByCategory === true) return null;
  const price = pesos(p.price?.value);
  const offer = pesos(p.discountedPrice?.value);
  if (price == null || offer == null || offer >= price) return null;
  const pct = typeof p.discountPercentage === "number" && p.discountPercentage > 0 ? Math.round(p.discountPercentage) : Math.round(((price - offer) * 100) / price);
  return pct >= 1 ? { offer_price: offer, discount: pct } : null;
}

/** The badge over the brand ("Venta en Verde"), from the API. */
const apiLabel = (p: ApiProduct) =>
  clean(
    Object.values(p.labelProductInfoMap ?? {})
      .filter((l) => l && l.visible !== false && clean(l.value))
      .map((l) => l!.value)[0],
  ) || null;

/** Where the product sits in the store, from the API's breadcrumb. */
const apiCategory = (p: ApiProduct) =>
  (p.breadCrumb ?? [])
    .filter((b) => b.categoryCode && b.categoryCode !== "agroplanetProducts" && clean(b.name))
    .map((b) => clean(b.name))
    .join(" > ") || null;

/** Equivalencias, from the API's feature groups. */
function apiEquivalents(p: ApiProduct): { label: string; value: string }[] {
  return (p.classifications ?? [])
    .filter((c) => /EQUIVALENCIA/i.test(c.code ?? ""))
    .flatMap((c) => (c.features ?? []).map((f) => ({ label: clean(f.name), value: (f.featureValues ?? []).map((v) => clean(v.value)).filter(Boolean).join(", ") })))
    .filter((r) => r.label && r.value);
}

/** The Especificaciones the product page draws, from the same fields. */
function apiSpecs(p: ApiProduct): { label: string; value: string }[] {
  const n = (v: number | null | undefined) => (typeof v === "number" ? String(Math.round(v * 100) / 100) : "");
  return [
    { label: "Unidades por caja", value: n(p.unitInBox) },
    { label: "País", value: clean(p.country?.name) },
    { label: "Ancho de caja (cm)", value: n(p.ancho) },
    { label: "Altura de caja (cm)", value: n(p.altura) },
    { label: "Longitud de caja (cm)", value: n(p.longitud) },
    { label: "Peso bruto de caja (kg)", value: p.hidePesoBruto ? "" : n(p.pesoBruto) },
  ].filter((r) => r.value);
}

// ─── The stores ───────────────────────────────────────────────────────────

/** Agroplanet's 22 stores (/nuestras-tiendas and `store/findStoreByRegion
 *  AndCommune`, 2026-10-29): the name its card writes, the city of its
 *  address, and the región. Used to match what the visitor calls a store
 *  ("la de Concepción", "en La Serena"). */
const STORES: [name: string, city: string, region: string][] = [
  ["Coquimbo", "La Serena", "Coquimbo"],
  ["Ovalle", "Ovalle", "Coquimbo"],
  ["Quillota", "Quillota", "Valparaíso"],
  ["Rancagua", "Rancagua", "O'Higgins"],
  ["Curico", "Curicó", "Maule"],
  ["Talca", "Talca", "Maule"],
  ["Chillan", "Chillán", "Ñuble"],
  ["Concepcion", "Concepción", "Biobío"],
  ["Temuco", "Temuco", "Araucanía"],
  ["Casablanca", "Casablanca", "Valparaíso"],
  ["Vergara", "Santiago", "Metropolitana"],
  ["Santa Cruz", "Santa Cruz", "O'Higgins"],
  ["Los Andes", "Los Andes", "Valparaíso"],
  ["Linares", "Linares", "Maule"],
  ["Puerto Varas", "Puerto Varas", "Los Lagos"],
  ["San Fernando", "San Fernando", "O'Higgins"],
  ["Los Angeles", "Los Ángeles", "Biobío"],
  ["Osorno", "Osorno", "Los Lagos"],
  ["Melipilla", "Melipilla", "Metropolitana"],
  ["Victoria", "Victoria", "Araucanía"],
  ["San Felipe", "San Felipe", "Valparaíso"],
  ["Parral", "Parral", "Maule"],
];

/**
 * The store names among `names` that `said` means: a store's own name, else
 * the city of its address ("La Serena" is the Coquimbo store), else a región
 * (all of its stores), else a store whose name holds the words. Accents and
 * case fold away.
 */
function storesMeant(said: string, names: string[]): string[] {
  const want = norm(said)
    .replace(/^(la |el )?(tienda|sucursal|store)( de| en)? /, "")
    .replace(/^(en|de) /, "")
    .replace(/^tienda /, "");
  if (!want) return [];
  const row = (n: string) => STORES.find((s) => norm(s[0]) === norm(n));
  const exact = names.filter((n) => norm(n) === want);
  if (exact.length) return exact;
  const city = names.filter((n) => norm(row(n)?.[1]) === want);
  if (city.length) return city;
  const region = names.filter((n) => bare(row(n)?.[2]) === bare(want) || (want.length > 4 && bare(row(n)?.[2]).startsWith(bare(want))));
  if (region.length) return region;
  return names.filter((n) => norm(n).includes(want) || (want.length > 4 && want.includes(norm(n))));
}

// ─── The product page ─────────────────────────────────────────────────────

interface ProductState {
  path: string;
  sku: string | null;
  name: string;
  brand: string | null;
  maker_code: string | null;
  price: number | null;
  regular_price: number | null;
  discount: number | null;
  offer_price: number | null;
  price_hidden: boolean;
  stock: string | null;
  stock_level: number | null;
  description: string | null;
  label: string | null;
  category: string | null;
  specs: { label: string; value: string }[];
  equivalents: { label: string; value: string }[];
  docs: string[];
  related: { name: string; path: string; price: number | null }[];
  source: "page" | "api";
}

const onProductPage = () => kindOf() === "product";
const info = () => document.querySelector<HTMLElement>("app-product-info");

/** The value after a label the product page writes as "Label:" + span. */
function labelled(root: Element | null, label: RegExp): string {
  if (!root) return "";
  for (const span of root.querySelectorAll("span")) {
    if (label.test(clean(span.textContent))) return clean(span.nextElementSibling?.textContent);
  }
  return "";
}

/** The SKU the product page in front shows ("SKU: 1173221"), else its path's. */
const pageSku = () => labelled(info(), /^SKU:?$/i) || productSku(location.pathname);

/** "Confirmar precio en tienda" in place of a price (the store's
 *  `hidePriceByCategory`). */
const priceHiddenIn = (el: Element | null | undefined) => /confirmar precio en tienda|confirm (?:the )?price in (?:the )?store/i.test(clean(el?.textContent));

/** A product's Especificaciones on its page: the label/value rows (the
 *  data sheets' "Descargar" rows left out). */
function specRows(): { row: HTMLElement; label: string; value: string }[] {
  const out: { row: HTMLElement; label: string; value: string }[] = [];
  for (const row of document.querySelectorAll<HTMLElement>("app-product-tabs .mt-20 > div")) {
    const cells = [...row.querySelectorAll<HTMLElement>(":scope > .p-20")];
    if (cells.length !== 2) continue;
    const label = clean(cells[0]!.textContent);
    const value = clean(cells[1]!.textContent);
    if (label && value) out.push({ row, label, value });
  }
  return out;
}

/** The Equivalencias block under Especificaciones (some parts): each row's
 *  label ("Equivalencia OEM") and its codes. */
function equivalenceRows(): { row: HTMLElement; label: string; value: string }[] {
  const out: { row: HTMLElement; label: string; value: string }[] = [];
  const title = [...document.querySelectorAll<HTMLElement>("app-product-tabs .title")].find((t) => /^(?:equivalencias?|equivalen)/.test(norm(t.textContent)));
  const block = title?.parentElement;
  if (!block) return out;
  for (const row of block.querySelectorAll<HTMLElement>("div")) {
    const cells = [...row.querySelectorAll<HTMLElement>(":scope > .p-20")];
    if (cells.length !== 2) continue;
    const label = clean(cells[0]!.textContent);
    const value = clean(cells[1]!.textContent);
    if (label && value) out.push({ row, label, value });
  }
  return out;
}

/** The data sheets' rows: "Hoja de Seguridad", "Ficha Técnica", each with its
 *  "Descargar" link (a PDF in a new tab, never opened here). */
function docRows(): { row: HTMLElement; label: string; link: HTMLAnchorElement }[] {
  const out: { row: HTMLElement; label: string; link: HTMLAnchorElement }[] = [];
  for (const link of document.querySelectorAll<HTMLAnchorElement>("app-product-tabs .ficha_tecnica a, app-product-tabs a[href*='documento-tecnico']")) {
    const cell = link.closest<HTMLElement>(".p-15, .p-20");
    const row = cell?.parentElement;
    const label = clean(row?.querySelector(":scope > .p-15, :scope > .p-20")?.textContent);
    // The phone's copy of the card repeats them: one row per data sheet.
    if (row && label && !out.some((d) => d.row === row || (norm(d.label) === norm(label) && (shown(d.row) || !shown(row))))) out.push({ row, label, link });
  }
  return out;
}

/** "Complemente su compra": the carousel of products the store suggests with
 *  this one (some products only). */
const relatedBox = () =>
  [...document.querySelectorAll<HTMLElement>("app-products-carousel")].find((c) => !c.closest("app-category-home") && clean(c.textContent).length > 0) ?? null;

function relatedItems(): { name: string; path: string; price: number | null }[] {
  const box = relatedBox();
  const out: { name: string; path: string; price: number | null }[] = [];
  for (const card of box?.querySelectorAll<HTMLElement>("app-product-card") ?? []) {
    const a = card.querySelector<HTMLAnchorElement>("a[href*='/producto/']");
    const sku = productSku(pathOf(a?.href));
    const name = clean(card.querySelector("p.h-p, p.title")?.textContent) || clean(card.querySelector("img")?.getAttribute("alt"));
    if (!sku || !name || out.some((r) => productSku(r.path) === sku)) continue;
    out.push({ name, path: productPath(sku, name), price: priceHiddenIn(card) ? null : money(card.querySelector(".new-price")?.textContent) });
  }
  return out.slice(0, 8);
}

/** The badge over the brand ("Venta en Verde"). */
const pageLabel = () => clean(info()?.querySelector("p[class*='label-'] span, p[class*='label-']")?.textContent) || null;

/** Where the product sits, from the breadcrumb (its own name and "inicio"
 *  left out). */
function pageCategory(): string | null {
  const links = [...document.querySelectorAll<HTMLAnchorElement>("app-breadcrumb li a")].filter((a) => pathOf(a.href) !== "/");
  return links.map((a) => clean(a.textContent)).filter(Boolean).join(" > ") || null;
}

/** A section of the product page's details card, by its title: "Detalle del
 *  Producto" or "Especificaciones" (both always drawn, one after the other). */
function tabSection(title: RegExp): { title: HTMLElement; block: HTMLElement } | null {
  const t = [...document.querySelectorAll<HTMLElement>("app-product-tabs .title")].find((x) => title.test(norm(x.textContent)) && shown(x));
  if (!t) return null;
  return { title: t, block: (t.parentElement as HTMLElement | null) ?? t };
}

function readProduct(): ProductState | null {
  if (!onProductPage()) return null;
  const box = info();
  const nameEl = box?.querySelector("h2.black-name");
  if (!box || !nameEl) return null;
  const sku = pageSku();
  const prices = box.querySelector(".prices-plp");
  const hidden = priceHiddenIn(box);
  const price = hidden ? null : money(prices?.querySelector(".new-price")?.textContent);
  const old = hidden ? null : money(prices?.querySelector(".old-price, del, s, .before-price")?.textContent);
  const name = clean(nameEl.textContent);
  return {
    path: sku ? productPath(sku, name) : location.pathname,
    sku,
    name,
    brand: clean(box.querySelector("a.black-brand")?.textContent) || null,
    maker_code: labelled(box, /^(?:c[oó]digo fabricante|manufacturer(?:'s)? code):?$/i) || null,
    price,
    regular_price: old != null && price != null && old > price ? old : null,
    discount: old != null && price != null && old > price ? Math.round(((old - price) * 100) / old) : null,
    offer_price: null,
    price_hidden: hidden,
    stock: null,
    stock_level: null,
    description: clean(document.querySelector("app-product-tabs p.format")?.textContent).slice(0, 400) || null,
    label: pageLabel(),
    category: pageCategory(),
    specs: specRows()
      .slice(0, MAX_SPECS)
      .map(({ label, value }) => ({ label, value })),
    equivalents: equivalenceRows().map(({ label, value }) => ({ label, value })),
    docs: docRows().map((d) => d.label),
    related: relatedItems(),
    source: "page",
  };
}

/**
 * The store's live read of product `sku`. The price is the one its page and
 * its cart write (`price`); the store hides its offers on the pages
 * (`hideDiscount`) and the mini-cart's subtotal applies them: the API's
 * `discountedPrice` and `discountPercentage`, reported as `offer_price` and
 * `discount`. A hidden price ("Confirmar precio en tienda") is reported as
 * hidden, never as a number, and has no offer.
 */
async function productFromApi(sku: string): Promise<ProductState> {
  const p = await productApi(sku);
  const hidden = p.hidePriceByCategory === true;
  const name = clean(p.name);
  return {
    path: productPath(p.code || sku, name),
    sku: p.code || sku,
    name,
    brand: clean(p.brand) || null,
    maker_code: clean(p.manufacturerCode ?? p.manufacturer) || null,
    price: hidden ? null : pesos(p.price?.value),
    regular_price: null,
    discount: offerOf(p)?.discount ?? null,
    offer_price: offerOf(p)?.offer_price ?? null,
    price_hidden: hidden,
    stock: stockStatus(p.stock) || null,
    stock_level: typeof p.stock?.stockLevel === "number" ? p.stock.stockLevel : null,
    description: clean((p.description ?? p.summary)?.replace(/<[^>]+>/g, " ")).slice(0, 400) || null,
    label: apiLabel(p),
    category: apiCategory(p),
    specs: apiSpecs(p),
    equivalents: apiEquivalents(p),
    docs: (p.data_sheet ?? []).map((d) => clean(d.name)).filter(Boolean),
    related: [],
    source: "api",
  };
}

let confirming: { sku: string; done: Promise<void> } | null = null;
/** product.checked for the product in front, once per product. */
function confirmProduct(): Promise<void> {
  const sku = productSku(location.pathname);
  if (!onProductPage() || !sku) return Promise.resolve();
  if (confirming?.sku === sku) return confirming.done;
  const done = productFromApi(sku)
    .then((p) => {
      if (productSku(location.pathname) !== sku) return;
      latest.set("product_shown", p);
      const page = readProduct();
      report("product_shown", page && page.sku === p.sku ? latestProductFor(page) : p);
    })
    .catch(() => {
      if (confirming?.sku === sku) confirming = null;
    });
  confirming = { sku, done };
  return done;
}

/** The live read wins over the page's once it is in; what only the page
 *  draws (the related products, rows the API lacks) is kept from the page. */
function latestProductFor(page: ProductState): ProductState {
  const live = latest.get("product_shown") as ProductState | undefined;
  if (live?.source !== "api" || live.sku !== page.sku) return page;
  return {
    ...live,
    related: live.related.length ? live.related : page.related,
    equivalents: live.equivalents.length ? live.equivalents : page.equivalents,
    docs: live.docs.length ? live.docs : page.docs,
    label: live.label ?? page.label,
    category: live.category ?? page.category,
  };
}

const productUp = (sku?: string | null) => {
  const name = document.querySelector("app-product-info h2.black-name");
  return Boolean(name && clean(name.textContent) && (!sku || pageSku() === sku));
};

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
}

const isListing = () => ["category", "search", "brand"].includes(kindOf());
/** The listing's own "no results": a search's `app-no-results` ("No logramos
 *  encontrar resultados"), or the words. */
const noResults = () =>
  Boolean(document.querySelector("app-no-results")) ||
  /no logramos encontrar|no (se )?encontr|sin resultados|0 resultados|no results|not found|could not find/i.test(
    clean(document.querySelector("app-plp-grid, app-product-search, app-category, app-brand-search")?.textContent).slice(0, 2000),
  );

/** The count a search page shows ("( 443 )"); a category shows none. */
function shownCount(): number | null {
  for (const el of document.querySelectorAll<HTMLElement>("app-product-search .gray-search")) {
    const m = clean(el.textContent).match(/^\(\s*([\d.]+)\s*\)$/);
    if (m) return Number(m[1]!.replace(/\./g, ""));
  }
  return null;
}
/**
 * The listing's grid has drawn, and is the store's answer: cards in it with
 * none of the store's calls still out, or its own "no results" once they are
 * back. While the app redraws (a filter, a sort, a page, a route) the grid
 * is empty or stale for a moment: that moment is never a listing (pcfactory
 * dev calls 31a45613, 8b363867: "no products", then "correction: there are").
 */
const gridUp = () => Boolean(document.querySelector("app-plp-filter")) && (cards().length > 0 || noResults()) && apiIdle();

/** While one of his moves waits for the grid it changed, the page's own
 *  watch does not report it: the move reports the settled listing itself. */
let gridPending = 0;
async function changingGrid<T>(fn: () => Promise<T>): Promise<T> {
  gridPending++;
  try {
    return await fn();
  } finally {
    gridPending--;
  }
}

/** The grid's cards, in order: each card is one link to its product. */
function cards(): HTMLAnchorElement[] {
  return [...document.querySelectorAll<HTMLAnchorElement>("app-plp-grid a[href*='/producto/']")];
}

const cardSku = (a: Element) => productSku(pathOf((a as HTMLAnchorElement).href));
const cardName = (a: Element) => clean(a.querySelector(".h-name p.title, p.title")?.textContent) || clean(a.querySelector("img")?.getAttribute("alt"));

function cardItem(a: HTMLAnchorElement): ListingItem | null {
  const sku = cardSku(a);
  if (!sku) return null;
  const prices = a.querySelector(".prices");
  const price = priceHiddenIn(prices) ? null : money(prices?.querySelector(".new-price")?.textContent);
  const old = priceHiddenIn(prices) ? null : money(prices?.querySelector(".old-price, del, s, .before-price")?.textContent);
  return { path: productPath(sku, cardName(a)), name: cardName(a), price, regular_price: old != null && price != null && old > price ? old : null };
}

interface Group {
  el: HTMLElement;
  name: string;
  header: HTMLElement;
  panel: HTMLElement;
}

/** The facet a listing's campaign switches are reported as: one switch per
 *  campaign ("Agrofertas Octubre"), its options the campaigns. */
const CAMPAIGN = "Campaña";
const CAMPAIGN_CODE = /^C_AG_BUSQUEDA_/;
const CAMPAIGN_WORDS = /^(?:campana|campanas|campaign|campaigns|oferta|ofertas|offer|offers|promocion|promociones)$/;

/** The listing's facets as the store's API answers them, its campaign
 *  facets (one per campaign, each with one value) folded into "Campaña". */
function facetsOf(api: ApiListing | null): { name: string; values: ApiFacetValue[] }[] {
  const out: { name: string; values: ApiFacetValue[] }[] = [];
  let campaigns: { name: string; values: ApiFacetValue[] } | null = null;
  for (const f of api?.data?.facets ?? []) {
    if (!clean(f.name)) continue;
    if (CAMPAIGN_CODE.test(f.code ?? "")) {
      if (!campaigns) out.unshift((campaigns = { name: CAMPAIGN, values: [] }));
      campaigns.values.push(...(f.values ?? []));
      continue;
    }
    out.push({ name: clean(f.name), values: f.values ?? [] });
  }
  return out;
}

interface Toggle {
  name: string;
  el: HTMLElement;
  toggle: HTMLElement;
  label: HTMLElement;
  on: boolean;
}

/** The listing's campaign switches (`.SPECIALFILTER-filter`: the campaign's
 *  title and a Material slide toggle; a press on the title does nothing, on
 *  the toggle's label switches it). */
function toggles(): Toggle[] {
  const out: Toggle[] = [];
  for (const el of document.querySelectorAll<HTMLElement>("app-plp-filter .SPECIALFILTER-filter")) {
    const toggle = el.querySelector<HTMLElement>("mat-slide-toggle");
    if (!toggle) continue;
    const name = clean(el.querySelector("span.fw-700, span")?.textContent) || clean(el.textContent);
    const input = toggle.querySelector<HTMLInputElement>("input");
    const on = toggle.classList.contains("mat-checked") || input?.getAttribute("aria-checked") === "true" || Boolean(input?.checked);
    out.push({ name, el, toggle, label: toggle.querySelector<HTMLElement>("label") ?? toggle, on });
  }
  return out;
}

/** The campaign the brain named: "Campaña: Agrofertas Octubre", or the
 *  campaign as the facet ("Agrofertas Octubre: sí"). */
function campaignMeant(facet: string, value: string, offered: string[]): string | null {
  const byValue = best(offered, (x) => x, value);
  if (CAMPAIGN_WORDS.test(norm(facet).replace(/\s+/g, "")) || norm(facet) === norm(CAMPAIGN)) return byValue ?? (offered.length === 1 && !value ? offered[0]! : null);
  return best(offered, (x) => x, facet) ? (byValue ?? best(offered, (x) => x, facet)) : null;
}

/** Switch one campaign on or off with its own toggle, as a visitor does: the
 *  switch scrolled to and ringed, its label pressed, the grid waited for,
 *  then what is on read back from the store's answer. */
async function flipCampaign(c: MoveContext, name: string, on: boolean, arg: string): Promise<Applied | Missed> {
  const known = await apiOptions(CAMPAIGN);
  const offered = known?.options ?? [];
  const already = known ? Boolean(best(known.on, (x) => x, name)) : false;
  if (already === on) return on ? { ok: true, label: `${CAMPAIGN}: ${name}`, already: true } : { ok: false, arg, why: `"${CAMPAIGN}: ${name}" is not on`, options: known?.on ?? [] };
  // By its title, or, on a page whose words a translator rewrote, by its place.
  const all = toggles();
  const t = best(all, (x) => x.name, name) ?? (all.length === offered.length ? all[offered.findIndex((o) => o === name)] : undefined) ?? (all.length === 1 ? all[0] : undefined);
  if (!t) return { ok: false, arg, why: `this listing shows no switch "${name}"`, options: offered };
  await scrollTo(t.el, "center");
  await c.ring(t.el, name);
  const before = gridKey();
  const since = Date.now();
  c.progress("waiting_site");
  await changingGrid(async () => {
    press(t.label);
    await waitForGrid(before, since);
  });
  const now = await apiOptions(CAMPAIGN);
  const isOn = Boolean(now && best(now.on, (x) => x, name));
  if (isOn !== on) return { ok: false, arg, why: `${name} stayed ${on ? "off" : "on"}`, options: [] };
  return { ok: true, label: on ? `${CAMPAIGN}: ${name}` : `${CAMPAIGN}: ${name} off` };
}

/** The filter panel's facets (`app-filter-element`, each a Material
 *  expansion panel; a folded one draws no options until it opens). */
function groups(): Group[] {
  const out: Group[] = [];
  for (const el of document.querySelectorAll<HTMLElement>("app-plp-filter app-filter-element")) {
    const panel = el.querySelector<HTMLElement>("mat-expansion-panel");
    const header = panel?.querySelector<HTMLElement>("mat-expansion-panel-header");
    const name = clean(header?.querySelector("mat-panel-title")?.textContent);
    if (panel && header && name) out.push({ el, name, header, panel });
  }
  return out;
}

const isOpen = (g: Group) => g.panel.classList.contains("mat-expanded");

interface Opt {
  box: HTMLElement;
  label: HTMLElement;
  text: string;
  checked: boolean;
}

/** A facet's options as drawn: each `mat-checkbox`, its words without the
 *  "(count)" a theme may add. */
function options(g: Group): Opt[] {
  const out: Opt[] = [];
  for (const box of g.panel.querySelectorAll<HTMLElement>("mat-checkbox")) {
    const label = box.querySelector<HTMLElement>("label") ?? box;
    const text = clean(box.querySelector(".mat-checkbox-label")?.textContent?.replace(/\(\d+\)\s*$/, ""));
    const input = box.querySelector<HTMLInputElement>("input[type=checkbox]");
    if (text) out.push({ box, label, text, checked: box.classList.contains("mat-checkbox-checked") || Boolean(input?.checked) });
  }
  return out;
}

type Sort = "price_asc" | "price_desc" | "relevance";

const SORT_CODES: Record<Sort, string> = { price_asc: "price-asc", price_desc: "price-desc", relevance: "" };

function sortOf(): Sort | null {
  if (!isListing()) return null;
  const param = new URLSearchParams(location.search).get("sort") ?? "";
  if (param === "price-asc") return "price_asc";
  if (param === "price-desc") return "price_desc";
  return "relevance";
}

/** The words of a search listing (`/busqueda/<words>`). */
const searchWords = () => clean(decodeURIComponent(location.pathname.replace(/^\/busqueda\//i, "").replace(/\/+$/, "")).replace(/[+_]/g, " "));

/** A category's code, the last part of its path (`/categoria/lubricantes/AG100`). */
const categoryCode = (path = location.pathname) => decodeURIComponent(path.replace(/\/+$/, "").split("/").pop() ?? "");

/** A listing's own address: its path, with the filters and the sort it has on
 *  left out (they are the listing's state, not which listing it is). */
function listingPath(): string {
  // The app writes a category's slug as it likes after a filter
  // ("/categoria/Lubricantes/AG100"): one listing, one path.
  const path = decodeURIComponent(location.pathname.replace(/\/+$/, ""));
  const m = path.match(/^\/categoria\/([^/]+)\/([^/]+)$/i);
  return m ? `/categoria/${m[1]!.toLowerCase()}/${m[2]}` : path.toLowerCase();
}

/** The API call the app makes for the listing in front, as it makes it. A
 *  brand page keeps its page out of the address (it pages in place, 20 a
 *  page: `pageSize=0`), so its page is the pager's. */
function listingRequest(): string | null {
  const q = new URLSearchParams(location.search);
  const page = kindOf() === "brand" ? String(pageNow() - 1) : q.get("page") || "0";
  const sort = q.get("sort") ?? "";
  const kind = kindOf();
  if (kind === "category") return `${API}/category/getCategory?code=${categoryCode()}&q=${q.get("q") ?? ""}&page=${page}&sort=${sort}&pageSize=40`;
  if (kind === "search") return `${API}/search/refineSearch?q=${q.get("q") || searchWords()}&page=${page}&sort=${sort}&pageSize=40`;
  if (kind === "brand") {
    const brand = categoryCode().toUpperCase();
    return `${API}/category/getCategory?code=agroplanetProducts&q=${q.get("q") || `:relevance:brand_search:${brand}`}&page=${page}&sort=${sort}&pageSize=0`;
  }
  return null;
}

/** An API address as a key: its path and its parameters, decoded and sorted
 *  (the app writes `q=::brand_search:X` unencoded, a fetch may encode it). */
function apiKey(url: string): string {
  try {
    const u = new URL(url);
    const params = [...u.searchParams.entries()].map(([k, v]) => `${k}=${v}`).sort();
    return `${u.pathname}?${params.join("&")}`;
  } catch {
    return url;
  }
}

interface ApiFacetValue {
  name?: string;
  count?: number;
  selected?: boolean;
}
interface ApiListing {
  name?: string;
  data?: {
    results?: (ApiProduct & { discountPercentage?: number | null })[];
    pagination?: { totalNumberOfResults?: number; currentPage?: number; numberOfPages?: number };
    facets?: { name?: string; code?: string; values?: ApiFacetValue[] }[];
    spellingSuggestion?: { suggestion?: string } | null;
  };
}

/** The listings' answers the app got (and ours), by their address. */
const listings = new Map<string, ApiListing>();
onApi((url, _method, body) => {
  if (!/\/(category\/getCategory|search\/refineSearch)\?/.test(url)) return;
  const env = body() as Envelope<ApiListing> | null;
  if (env?.data) listings.set(apiKey(url), env.data);
});

/** The listing in front, as the store's API answers it: the app's own answer
 *  when it was heard, else the same call made here. */
async function listingData(): Promise<ApiListing | null> {
  const url = listingRequest();
  if (!url) return null;
  const key = apiKey(url);
  const had = listings.get(key);
  if (had) return had;
  try {
    const got = await getJson<ApiListing>(url);
    listings.set(key, got);
    return got;
  } catch {
    return null;
  }
}

async function readListing(): Promise<ListingState> {
  const kind = kindOf();
  const api = await listingData();
  const facets: ListingFilter[] = facetsOf(api).map((f) => ({
    facet: f.name,
    on: f.values.filter((v) => v.selected).map((v) => clean(v.name)),
    options: f.values.map((v) => clean(v.name)).filter(Boolean).slice(0, MAX_OPTIONS),
  }));
  const title =
    kind === "search"
      ? `Resultados para "${searchWords()}"`
      : kind === "brand"
        ? clean(api?.name) && api?.name !== "agroplanetProducts"
          ? clean(api?.name)
          : categoryCode().toUpperCase()
        : clean(api?.name) || clean(document.querySelector("app-breadcrumb li:last-child")?.textContent) || document.title.replace(/\s*\|.*$/, "");
  return {
    path: listingPath(),
    title,
    count: api?.data?.pagination?.totalNumberOfResults ?? shownCount() ?? (cards().length || (noResults() ? 0 : null)),
    filters: facets,
    sort: sortOf(),
    items: cards()
      .map(cardItem)
      .filter((x): x is ListingItem => x !== null)
      .slice(0, MAX_LISTED),
  };
}

const reportListing = async () => {
  if (!isListing() || gridPending || !(await waitFor(gridUp, 3000)) || gridPending) return;
  const listing = await readListing();
  if (listingPath() === listing.path) report("listing_shown", listing);
};

/** What the grid shows now, to tell when it changed. */
const gridKey = () => JSON.stringify([cards().map(cardSku), location.search, kindOf() === "brand" ? pageNow() : 0]);

/** The grid has changed from `before` and the store's calls since `since`
 *  are back, then the DOM has been quiet a moment. */
async function waitForGrid(before: string, since: number, ms = 10_000): Promise<boolean> {
  const changed = await waitFor(() => gridKey() !== before && gridUp(), ms);
  await apiSettled(since, 2500);
  await quiet(document.querySelector("app-plp-grid") ?? main(), 300, 800);
  await waitFor(gridUp, 3000);
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

interface ApiEntry {
  entryNumber?: number;
  quantity?: number;
  basePrice?: ApiPrice | null;
  totalPrice?: ApiPrice | null;
  product?: { code?: string; name?: string } | null;
}

const cartRows = () => [...document.querySelectorAll<HTMLElement>("app-cart app-cart-product")].filter((r) => r.querySelector("a[href*='/producto/']"));
const rowSku = (row: Element) => productSku(pathOf(row.querySelector<HTMLAnchorElement>("a[href*='/producto/']")?.href));
const rowName = (row: Element) => clean(row.querySelector("a.nombre-producto-color, h3 a")?.textContent);
const qtyInput = (root: Element | null) => root?.querySelector<HTMLInputElement>("app-input-update-quantity input[type=number]") ?? null;
const rowQty = (row: Element) => Number(qtyInput(row)?.value) || 0;

/** The cart page's Total. */
function pageTotal(): number | null {
  for (const b of document.querySelectorAll<HTMLElement>("app-cart b")) {
    if (/^total:?$/i.test(clean(b.textContent))) {
      const right = b.closest(".ng-star-inserted, div")?.parentElement?.parentElement?.querySelector(".text-right b, .text-right");
      const v = money(right?.textContent);
      if (v != null) return v;
    }
  }
  const amounts = [...document.querySelectorAll<HTMLElement>("app-cart .text-right b")].filter(shown).map((e) => money(e.textContent));
  return amounts.find((v) => v != null) ?? null;
}

/**
 * The cart now, from the store's own `minicart/cart/rollover` with the
 * visitor's cookie: each line's unit price as the cart page writes it
 * (`basePrice`), and its total; on the cart page itself, the Total it shows.
 */
async function readCart(): Promise<CartState> {
  const entries = await getJson<ApiEntry[]>(`${API}/minicart/cart/rollover`).catch(() => null);
  if (!entries) {
    // No answer: the cart page's own rows, when it is in front.
    const items = cartRows().map((row) => ({ path: productPath(rowSku(row) ?? "", rowName(row)), name: rowName(row), qty: rowQty(row), price: money(row.querySelector("p.fw-500")?.textContent) }));
    return { count: items.reduce((n, i) => n + i.qty, 0), subtotal: kindOf() === "cart" ? pageTotal() : null, items };
  }
  const items = entries.map((e) => {
    const name = clean(e.product?.name);
    return { path: productPath(clean(e.product?.code), name), name, qty: Number(e.quantity) || 0, price: pesos(e.basePrice?.value) };
  });
  const listed = items.reduce((n, i) => n + i.qty * (i.price ?? 0), 0);
  return { count: items.reduce((n, i) => n + i.qty, 0), subtotal: kindOf() === "cart" && cartRows().length ? (pageTotal() ?? listed) : items.length ? listed : 0, items };
}

const CART_SEEN_KEY = "voqalize.agroplanet.cart";
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

const cartLine = (c: CartState) => `the cart has ${c.count} item${c.count === 1 ? "" : "s"}${c.subtotal != null ? `, $${c.subtotal}` : ""}`;

/** Every change the app made to the cart (`cart/add`, `cart/update`,
 *  `cart/delete`), counted, so a press can wait for its own. */
let cartWrites = 0;

/** The − and + of a quantity stepper (`app-input-update-quantity`). Their ids
 *  are swapped in the app: `#minus-…` is the "+" and `#add-…` the "−"; the
 *  icon each draws ("add", "remove") and its class say which is which. */
function stepper(root: Element | null): { minus: HTMLButtonElement | null; plus: HTMLButtonElement | null; input: HTMLInputElement | null } {
  const q = root?.querySelector("app-input-update-quantity") ?? null;
  const buttons = [...(q?.querySelectorAll<HTMLButtonElement>("button") ?? [])];
  const icon = (b: Element) => clean(b.querySelector("mat-icon")?.textContent);
  const plus = buttons.find((b) => icon(b) === "add" || b.classList.contains("buttonAdd") || b.id.startsWith("minus-")) ?? null;
  const minus = buttons.find((b) => b !== plus && (icon(b) === "remove" || /buttonMinus/.test(b.className) || b.id.startsWith("add-"))) ?? null;
  return { minus, plus, input: q?.querySelector<HTMLInputElement>("input[type=number]") ?? null };
}

// ─── The quote ────────────────────────────────────────────────────────────

interface QuoteState {
  step: "form" | "done" | "other";
  filled: string[];
  missing: string[];
  items: number | null;
  total: number | null;
}

/** The quote form's controls by the names the brain uses for them. */
const CONTROLS: [control: string, field: string, required: boolean][] = [
  ["name", "name", true],
  ["rut", "rut", true],
  ["phone", "phone", true],
  ["email", "email", true],
  ["region", "region", true],
  ["comune", "commune", true],
  ["street", "street", true],
  ["numberAddress", "number", true],
  ["depto", "unit", false],
  ["reference", "notes", false],
];

const form = () => document.querySelector<HTMLElement>("app-form-user-quote form");
const control = (name: string) => form()?.querySelector<HTMLElement>(`[formcontrolname="${name}"]`) ?? null;

/** Whether a control holds something: a field's value, a select's chosen
 *  option (not its "Seleccionar …" placeholder). Its value is never read
 *  out. */
function hasValue(el: HTMLElement | null): boolean {
  if (!el) return false;
  if (el.tagName === "MAT-SELECT") {
    const text = clean(el.querySelector(".mat-select-value-text")?.textContent);
    return Boolean(text) && !/^(?:seleccionar|select)/i.test(text) && !el.querySelector(".mat-select-placeholder");
  }
  return Boolean(clean((el as HTMLInputElement).value));
}

function readQuote(): QuoteState {
  const p = decodeURIComponent(location.pathname).toLowerCase().replace(/\/+$/, "");
  if (p.startsWith("/cotizacion/")) return { step: "done", filled: [], missing: [], items: null, total: null };
  if (p !== "/cotizacion" || !form()) return { step: "other", filled: [], missing: [], items: null, total: null };
  const filled: string[] = [];
  const missing: string[] = [];
  for (const [name, field, required] of CONTROLS) {
    const el = control(name);
    if (!el) continue;
    if (hasValue(el)) filled.push(field);
    else if (required) missing.push(field);
  }
  const summary = document.querySelector("app-resumen");
  const count = clean(summary?.textContent).match(/\((\d+)\s+(?:productos?|products?)\)/i);
  let total: number | null = null;
  for (const s of summary?.querySelectorAll("span") ?? []) {
    if (/^total:?$/i.test(clean(s.textContent))) total = money(s.parentElement?.nextElementSibling?.textContent);
  }
  return { step: "form", filled, missing, items: count ? Number(count[1]) : null, total };
}

const reportQuote = () => {
  if (kindOf() !== "quote") return;
  report("quote_state", readQuote());
};

// ─── Moves ────────────────────────────────────────────────────────────────
//
// Every move is a Stage move, registered with `Moves` (`registerMoves`): its
// performer finds the target, rings it with the spotlight before it acts, and
// returns a short detail of what it did; a refusal names the argument and
// what the page offers instead (`c.refuse`); an error is the move failing. A
// move to another page moves the app there and goes on in place
// (`navigate`); only when the route never draws does it load the page and
// carry the rest of itself there (`load`, `again`).

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
 *  on; refused before anything moves if `path` is a login, an account page
 *  or another host. The move goes on there: `null`. */
async function load(c: MoveContext, path: string, then?: Then): Promise<null> {
  const url = target(path);
  if (!c.loadThen) throw new Error("this page cannot load another and carry the move there");
  await c.loadThen(url, then);
  return null;
}

const again = (c: MoveContext, p: object): Then => ({ move: c.move, args: { ...p, arrived: true } });

/** `path` is the page in front: the same path, and the same query when it
 *  names one. */
function here(path: string): boolean {
  const to = new URL(path, location.origin);
  if (to.pathname.startsWith("/producto/")) return onProductPage() && productSku(to.pathname) === productSku(location.pathname);
  return samePath(location.pathname, to.pathname) && (!to.search || new URLSearchParams(to.search).toString() === new URLSearchParams(location.search).toString());
}

/** A link on this page to `path`, to ring and press: a product by its SKU,
 *  anything else by its path. */
function linkTo(path: string): HTMLAnchorElement | null {
  const sku = path.startsWith("/producto/") ? productSku(path) : null;
  const to = new URL(path, location.origin);
  return (
    [...main().querySelectorAll<HTMLAnchorElement>("a[href]")].find((a) => {
      if (!shown(a) || a.target === "_blank" || inChrome(a) || a.closest("app-breadcrumb")) return false;
      const u = new URL(a.href, location.origin);
      if (u.host !== location.host) return false;
      if (sku) return productSku(u.pathname) === sku;
      return samePath(u.pathname, to.pathname) && (u.search || "") === (to.search || "");
    }) ?? null
  );
}

/**
 * Move the app to `path` as a visitor would: the page's own link to it when
 * one is on screen (ringed, then pressed: the app's router takes the click),
 * else the router itself (`routeTo`). Then wait for the address and for
 * `ready`, the route's own content. True once there, in place. When the
 * route does not draw in time and `then` is given, the page is loaded
 * instead and the rest of the move carried there: false (the move's result
 * comes from that page).
 */
async function navigate(c: MoveContext, path: string, ready: () => unknown, then?: Then): Promise<boolean> {
  const url = new URL(target(path));
  const want = url.pathname + url.search;
  if (here(want) && ready()) return true;
  // A listing still redrawing replaces its cards: their links settle first.
  if (isListing()) await waitFor(gridUp, 3000);
  let link = linkTo(want);
  const before = routeEl();
  if (link) {
    await scrollTo(link, "center");
    await c.ring(link);
    // Pressed only while it is still the page's: a link the app has just
    // replaced would load the page instead of moving the app.
    if (!link.isConnected) link = linkTo(want);
  }
  if (link) {
    press(link);
    if (!(await waitFor(() => here(want), 1500))) routeTo(want);
  } else {
    routeTo(want);
  }
  c.progress("waiting_site");
  const arrived = await waitFor(() => here(want) && (routeEl() !== before || kindOf() === "product" || isListing()) && ready(), ROUTE_MS);
  if (arrived) {
    await quiet(main(), 300, 1500);
    return true;
  }
  if (then) {
    await load(c, want, then);
    return false;
  }
  throw new Error(`${want} did not open (now on ${location.pathname})`);
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
async function showGrid(c: MoveContext): Promise<string> {
  const listing = await readListing();
  report("listing_shown", listing);
  c.after(async () => {
    const row = firstRow();
    if (!row.length) return;
    await scrollTo(row[0]!, "center");
    await c.ring(row);
  });
  const first = listing.items[0];
  if (listing.count === 0 || (!first && noResults())) return `${listing.title}: no results (the page says "No logramos encontrar resultados")`;
  return `${listing.title}: ${listing.count ?? "?"} products${listing.sort && listing.sort !== "relevance" ? `, sorted ${listing.sort}` : ""}; ${
    first ? `first card ${first.name} (${first.price != null ? `$${first.price}` : "precio a confirmar en tienda"})` : "no products"
  }`;
}

// menu.open ────────────────────────────────────────────────────────────────

const menuPanel = () => document.querySelector<HTMLElement>("#acordeon-main");
const menuToggle = () => document.querySelector<HTMLElement>("app-menu-desktop .hamburger-menu-icon a");
const menuIsOpen = () => {
  const m = menuPanel();
  return Boolean(m && !m.hidden && visible(m));
};
const menuItems = () => [...document.querySelectorAll<HTMLElement>("#acordeon-main a.mat-item-menu-a")];
const itemName = (a: Element) => clean(a.querySelector(".item-menu-headline")?.textContent ?? a.textContent);
/** The flyout of the item hovered: a drawer beside the list. */
const flyout = () => {
  const f = document.querySelector<HTMLElement>("#acordeon-main mat-sidenav.mat-drawer-opened, #acordeon-main app-submenu-desktop");
  return f && f.querySelector(".categorie") && visible(f.querySelector(".categorie")!) ? f : null;
};

/** "Todas las categorías" folded again, as its own toggle does. */
async function closeMenu(): Promise<boolean> {
  if (!menuIsOpen()) return false;
  const toggle = menuToggle();
  if (toggle) press(toggle);
  if (!(await waitFor(() => !menuIsOpen(), 1500))) {
    const m = menuPanel();
    if (m) m.hidden = true;
  }
  return true;
}

async function openMenu(p: { category: string }, c: MoveContext): Promise<string> {
  const want = clean(p.category);
  if (!want) c.refuse("category", "say which top category", menuItems().map(itemName));
  await closeSplash();
  await scrollToTopOfPage();
  const toggle = await waitFor(menuToggle, 6000);
  if (!toggle) throw new Error("the page shows no Todas las categorías");
  if (!menuIsOpen()) {
    await c.ring(toggle, "Todas las categorías");
    press(toggle);
    if (!(await waitFor(menuIsOpen, 2500))) throw new Error("pressed Todas las categorías, but the menu did not open");
  }
  await waitFor(() => menuItems().length, 3000);
  const item = best(menuItems(), itemName, want);
  if (!item) c.refuse("category", `the menu has no "${want}"`, menuItems().map(itemName));
  const name = itemName(item);
  await c.ring(item, name);
  hover(item);
  const fly = await waitFor(() => {
    const f = flyout();
    return f && norm(f.textContent).includes(norm(name).slice(0, 8)) ? f : null;
  }, 3000);
  if (!fly) throw new Error(`pointed at ${name}, but its flyout did not open`);
  await sleep(200);
  // The flyout is the effect: ringed with the item after the result.
  c.after(() => c.ring([item, fly.querySelector<HTMLElement>(".submenu-lateral") ?? fly], { label: name, separate: true }));
  const subs = [...fly.querySelectorAll<HTMLElement>(".categorie a")].map((a) => clean(a.textContent)).filter(Boolean);
  return `opened Todas las categorías at ${name}: ${subs.slice(0, 18).join(", ")}${subs.length > 18 ? ` and ${subs.length - 18} more` : ""}`;
}

// commerce.search ──────────────────────────────────────────────────────────

const searchBox = () => [...document.querySelectorAll<HTMLInputElement>(SEARCH_BOX)].find(shown) ?? null;
/** The suggestion panel under the box in front (the sticky header has its own
 *  copy of both). */
const suggestions = () => [...document.querySelectorAll<HTMLElement>("#suggestContainer")].find((s) => s.getClientRects().length > 0) ?? null;
/** The suggestion panel's rows: its products (a row with a picture). */
const suggestedProducts = () => [...(suggestions()?.querySelectorAll<HTMLElement>(".mat-option") ?? [])].filter((r) => r.querySelector("img, p"));

/** The results address the app's own search builds: `/busqueda/<words>`. */
const searchUrl = (query: string) => `/busqueda/${encodeURIComponent(clean(query).toLowerCase())}`;

async function searchProducts(p: { query: string; open_index?: number | null }, c: MoveContext): Promise<string | null> {
  const query = clean(p.query);
  if (!query) c.refuse("query", "say what to search for");
  await scrollToTopOfPage();
  const input = await waitFor(searchBox, 6000);
  if (!input) throw new Error("the search box is not on this page");
  await c.ring(input.closest("form, app-smart-search") ?? input, query);
  await typeInto(input, query);
  // The app's suggestions come after three letters: a moment to see them.
  const panel = await waitFor(() => (suggestions() && shown(suggestions()!) ? suggestions() : null), 3500);
  if (panel) await c.ring(panel, "Sugerencias");
  if (p.open_index != null) {
    // The products come into the panel after its words.
    const index = p.open_index;
    await waitFor(() => suggestedProducts().length > index, 5000);
    const rows = suggestedProducts();
    const row = rows[p.open_index];
    if (!row) c.refuse("open_index", `the suggestions show ${rows.length} products; there is no number ${p.open_index + 1}`, rows.map((r) => clean(r.textContent)).slice(0, 8));
    const name = clean(row.querySelector("p")?.textContent);
    await c.ring(row, name);
    c.progress("waiting_site");
    press(row);
    if (!(await waitFor(() => onProductPage() && productUp(), ROUTE_MS))) throw new Error(`pressed the suggestion ${name}, but its product did not open (now on ${location.pathname})`);
    await quiet(main(), 300, 1500);
    const product = readProduct();
    if (product) report("product_shown", latestProductFor(product));
    void confirmProduct();
    return `searched "${query}" and opened the suggestion ${product?.name ?? name}`;
  }
  // Enter, as the visitor would; the magnifier, then the router, if not.
  const want = searchUrl(query);
  c.progress("waiting_site");
  enter(input);
  if (!(await waitFor(() => kindOf() === "search", 2000))) {
    const button = [...document.querySelectorAll<HTMLElement>("app-smart-search button.search-btn")].find(shown);
    if (button) press(button);
    if (!(await waitFor(() => kindOf() === "search", 2000))) routeTo(want);
  }
  if (!(await waitFor(() => kindOf() === "search" && gridUp(), ROUTE_MS))) throw new Error(`the search did not open its results (now on ${location.pathname})`);
  await apiSettled(Date.now() - 4000, 3000);
  await quiet(main(), 300, 1500);
  return `searched "${query}"; ${await showGrid(c)}`;
}

// filter_listing, and the filter and sort cues ─────────────────────────────

/** A listing the brain named: a category, a search or a brand. */
function wantedListing(raw: string): { path: string; kind: "category" | "search" | "brand" } | null {
  try {
    const u = new URL(raw.trim(), location.origin);
    const path = decodeURIComponent(u.pathname.replace(/\/+$/, ""));
    if (/^\/categoria\/[^/]+\/[^/]+$/i.test(path)) return { path, kind: "category" };
    if (/^\/busqueda\/[^/]+$/i.test(path)) return { path, kind: "search" };
    if (/^\/marca\/[^/]+$/i.test(path)) return { path, kind: "brand" };
    return null;
  } catch {
    return null;
  }
}

function onWantedListing(w: { path: string; kind: string }): boolean {
  if (kindOf() !== w.kind) return false;
  if (w.kind === "category") return norm(categoryCode(w.path)) === norm(categoryCode());
  return bare(w.path) === bare(listingPath());
}

/** The facet the brain named, by the panel's words ("Marca", "Viscosidad"),
 *  with the plurals and English a brain may say. */
const FACET_ALIASES: Record<string, string> = {
  marcas: "marca", brand: "marca", brands: "marca", categorias: "categoria", category: "categoria", price: "precio", precios: "precio",
  viscosity: "viscosidad", polarity: "polaridad",
};
function findGroup(facet: string): Group | null {
  const said = norm(facet);
  return best(groups(), (g) => g.name, FACET_ALIASES[said] ?? facet) ?? null;
}

/** The facet's panel opened, its options drawn. The app re-draws the whole
 *  filter panel when a listing's answer comes in, so the facet is looked up
 *  afresh until its options are on screen. */
async function openGroup(c: MoveContext, g: Group): Promise<Group> {
  let now = g;
  for (let attempt = 0; attempt < 3; attempt++) {
    now = (g.el.isConnected ? g : findGroup(g.name)) ?? g;
    if (isOpen(now) && options(now).some((o) => shown(o.box))) return now;
    await scrollTo(now.header, "center");
    if (!isOpen(now)) {
      await c.ring(now.header, now.name);
      press(now.header);
    }
    const ready = await waitFor(() => {
      const fresh = (now.el.isConnected ? now : findGroup(g.name)) ?? now;
      return isOpen(fresh) && options(fresh).some((o) => shown(o.box)) ? fresh : null;
    }, 2500);
    if (ready) {
      await sleep(250);
      return ready;
    }
  }
  return now;
}

type Applied = { ok: true; label: string; already?: boolean };
type Missed = { ok: false; arg: string; why: string; options: string[] };

/** The options of a facet as the store's API lists them for the listing in
 *  front (a folded panel draws none). */
async function apiOptions(facet: string): Promise<{ name: string; options: string[]; on: string[] } | null> {
  const all = facetsOf(await listingData());
  const f = best(all, (x) => x.name, FACET_ALIASES[norm(facet)] ?? facet);
  if (!f) return null;
  return { name: f.name, options: f.values.map((v) => clean(v.name)), on: f.values.filter((v) => v.selected).map((v) => clean(v.name)) };
}

/** Tick one option of one facet with the listing's own checkbox, as a
 *  visitor does: the panel opened if folded, the option scrolled to and
 *  ringed, its label pressed, then the grid waited for. The app re-draws the
 *  panel folded after each filter, so what is on is read back from the
 *  store's answer. */
async function applyOption(c: MoveContext, facet: string, value: string, arg = "value", facetArg = "facet"): Promise<Applied | Missed> {
  const campaigns = (await apiOptions(CAMPAIGN))?.options ?? [];
  const campaign = campaigns.length ? campaignMeant(facet, value, campaigns) : null;
  if (campaign) return flipCampaign(c, campaign, true, arg);
  if (CAMPAIGN_WORDS.test(norm(facet).replace(/\s+/g, "")) || norm(facet) === norm(CAMPAIGN)) {
    return { ok: false, arg: facetArg, why: campaigns.length ? `${CAMPAIGN} has no "${value}"` : "this listing has no campaign switch", options: campaigns };
  }
  const g = findGroup(facet);
  const names = groups().map((x) => x.name);
  if (!g) return { ok: false, arg: facetArg, why: `this listing has no filter "${facet}"`, options: names };
  const known = await apiOptions(g.name);
  const already = known ? best(known.on, (x) => x, value) : null;
  if (already) return { ok: true, label: `${g.name}: ${already}`, already: true };
  const open = await openGroup(c, g);
  const opt = best(options(open), (o) => o.text, value);
  if (!opt) return { ok: false, arg, why: `${g.name} has no option "${value}"`, options: (options(open).length ? options(open).map((o) => o.text) : (known?.options ?? [])).slice(0, MAX_OPTIONS) };
  if (opt.checked) return { ok: true, label: `${g.name}: ${opt.text}`, already: true };
  await scrollTo(opt.box, "center");
  await c.ring(opt.box, `${g.name}: ${opt.text}`);
  const before = gridKey();
  const since = Date.now();
  c.progress("waiting_site");
  await changingGrid(async () => {
    press(opt.label);
    await waitForGrid(before, since);
  });
  const now = await apiOptions(g.name);
  if (!now || !best(now.on, (x) => x, opt.text)) return { ok: false, arg, why: `${g.name} ${opt.text} did not stay ticked`, options: [] };
  return { ok: true, label: `${g.name}: ${opt.text}` };
}

/** Each item of "Ordenar por", by its words, or what Chrome's translator
 *  makes of them should it reach the menu (it is kept from it: anchors.ts). */
const SORT_WORDS: Record<Sort, RegExp> = {
  price_asc: /menor precio|(?:lower|lowest) price|price:? low/i,
  price_desc: /mayor precio|(?:higher|highest) price|price:? high/i,
  relevance: /relevancia|relevance/i,
};

/** "Ordenar por": its menu's trigger, which writes the sort in front. */
const sortTrigger = () =>
  [...document.querySelectorAll<HTMLElement>("app-category a.mat-menu-trigger, app-product-search a.mat-menu-trigger, app-brand-search a.mat-menu-trigger, app-plp-grid a.mat-menu-trigger")].find(
    (a) => shown(a) && /relevancia|precio|relevance|price/i.test(clean(a.textContent)),
  ) ?? null;
const sortItems = () => [...document.querySelectorAll<HTMLElement>(".cdk-overlay-container .mat-menu-panel [role=menuitem]")].filter(shown);

/** "Ordenar por": the menu opened, then its item pressed. */
async function applySort(c: MoveContext, sort: string): Promise<Applied | Missed> {
  const toggle = sortTrigger();
  const offered = ["Menor precio", "Mayor precio", "Relevancia"];
  if (!toggle) return { ok: false, arg: "order", why: "this listing has no Ordenar por", options: [] };
  if (!(sort in SORT_WORDS)) return { ok: false, arg: "order", why: `this listing cannot sort by ${sort}`, options: offered };
  if (sortOf() === sort) return { ok: true, label: `sorted ${clean(toggle.textContent).replace(/arrow_drop_down/, "").trim()}`, already: true };
  await scrollTo(toggle, "center");
  await c.ring(toggle.parentElement ?? toggle, "Ordenar por");
  press(toggle);
  const item = await waitFor(() => sortItems().find((i) => SORT_WORDS[sort as Sort].test(clean(i.textContent))), 2000);
  if (!item) return { ok: false, arg: "order", why: `Ordenar por has no ${sort}`, options: sortItems().map((i) => clean(i.textContent)) };
  await c.ring(item, clean(item.textContent));
  const before = gridKey();
  const since = Date.now();
  c.progress("waiting_site");
  await changingGrid(async () => {
    press(item);
    await waitForGrid(before, since);
  });
  if (sortOf() !== sort) return { ok: false, arg: "order", why: `the listing still shows ${clean(sortTrigger()?.textContent).replace(/arrow_drop_down/, "").trim()}`, options: offered };
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

interface FilterListing extends Arrived {
  category_path: string;
  filters?: unknown[] | null;
  sort?: Sort | null;
  remove?: unknown[] | null;
  clear?: boolean | null;
  page?: number | null;
}

/** The listing at `want`: the app moved there when it is not the one in
 *  front. The filters on stay on: the move takes off only what it is asked
 *  to (`remove`, `clear`). */
async function onListing(c: MoveContext, want: { path: string; kind: string }, p: object & Arrived): Promise<boolean> {
  if (onWantedListing(want) && gridUp()) return true;
  if (p.arrived && onWantedListing(want)) return true;
  return navigate(c, want.path, () => gridUp() && Boolean(document.querySelector("app-filter-element")), again(c, p));
}

/** Take one filter off with its own checkbox, unticked in place (the panel
 *  opened first), the grid waited for; read back from the store's answer. */
async function removeFilter(c: MoveContext, facet: string, value: string): Promise<Applied | Missed> {
  const campaigns = (await apiOptions(CAMPAIGN))?.options ?? [];
  const campaign = campaigns.length ? campaignMeant(facet, value, campaigns) : null;
  if (campaign) return flipCampaign(c, campaign, false, "remove");
  const known = await apiOptions(facet);
  const on = known ? best(known.on, (x) => x, value) : null;
  const offered = facetsOf(await listingData()).flatMap((f) => f.values.filter((v) => v.selected).map((v) => `${f.name}: ${clean(v.name)}`));
  if (!known || !on) return { ok: false, arg: "remove", why: `"${facet}: ${value}" is not on`, options: offered };
  const g = findGroup(known.name);
  if (!g) return { ok: false, arg: "remove", why: `this listing shows no filter "${known.name}"`, options: offered };
  const open = await openGroup(c, g);
  const opt = best(options(open), (o) => o.text, on);
  if (!opt) return { ok: false, arg: "remove", why: `${g.name} shows no "${on}" to untick`, options: offered };
  await scrollTo(opt.box, "center");
  await c.ring(opt.box, `${g.name}: ${opt.text}`);
  const before = gridKey();
  const since = Date.now();
  c.progress("waiting_site");
  await changingGrid(async () => {
    press(opt.label);
    await waitForGrid(before, since);
  });
  const now = await apiOptions(g.name);
  if (now && best(now.on, (x) => x, opt.text)) return { ok: false, arg: "remove", why: `${g.name} ${opt.text} stayed on`, options: [] };
  return { ok: true, label: `${g.name}: ${opt.text} off` };
}

/** Every filter off: the listing's own "Borrar Filtros" where it shows (the
 *  filter drawer of a narrow window), else each one unticked in turn, as a
 *  visitor on a desktop does. */
async function clearFilters(c: MoveContext): Promise<Applied | Missed> {
  const on = () =>
    listingData().then((api) => facetsOf(api).flatMap((f) => f.values.filter((v) => v.selected).map((v) => ({ facet: f.name, value: clean(v.name) }))));
  const first = await on();
  if (!first.length) return { ok: true, label: "no filters were on", already: true };
  const button = [...document.querySelectorAll<HTMLElement>("app-plp-filter button")].find((b) => /borrar filtros|(?:clear|delete|remove) (?:the )?filters/i.test(clean(b.textContent)) && shown(b));
  if (button) {
    await scrollTo(button, "center");
    await c.ring(button, "Borrar Filtros");
    const before = gridKey();
    const since = Date.now();
    c.progress("waiting_site");
    await changingGrid(async () => {
      press(button);
      await waitForGrid(before, since);
    });
  } else {
    for (const f of first) {
      const got = await removeFilter(c, f.facet, f.value);
      if (!got.ok) return { ok: false, arg: "clear", why: got.why, options: [] };
    }
  }
  return (await on()).length ? { ok: false, arg: "clear", why: "filters stayed on", options: [] } : { ok: true, label: "every filter off" };
}

/** The page in front, 1 for the first: the pager's current number (a brand
 *  page never writes its page in the address), else the address's (which
 *  counts from 0). */
function pageNow(): number {
  const current = [...document.querySelectorAll<HTMLElement>("app-custom-paginator-controls .item.current")].find(shown);
  const n = Number(clean(current?.textContent));
  if (Number.isInteger(n) && n > 0) return n;
  return (Number(new URLSearchParams(location.search).get("page")) || 0) + 1;
}
const pageLinks = () => [...document.querySelectorAll<HTMLElement>("app-custom-paginator-controls .item a")].filter(shown);
const pagerNext = () => [...document.querySelectorAll<HTMLElement>("app-custom-paginator-controls .pagination-next a")].find(shown) ?? null;

/** Page `n` of the listing with its own page links (the arrow when its
 *  number is not shown yet), in place; the app does not scroll for it. */
async function turnPage(c: MoveContext, n: number): Promise<Applied | Missed> {
  const last = (await listingData())?.data?.pagination?.numberOfPages ?? 1;
  if (n > last) return { ok: false, arg: "page", why: `the listing has ${last} page${last === 1 ? "" : "s"}`, options: Array.from({ length: Math.min(last, 12) }, (_, i) => String(i + 1)) };
  for (let step = 0; step < 12 && pageNow() !== n; step++) {
    const link = pageLinks().find((a) => clean(a.textContent) === String(n)) ?? (pageNow() < n ? pagerNext() : null);
    if (!link) break;
    await scrollTo(link, "center");
    await c.ring(link.closest(".item, .pagination-next") ?? link, `Página ${n}`);
    const before = gridKey();
    const since = Date.now();
    c.progress("waiting_site");
    await changingGrid(async () => {
      press(link);
      await waitForGrid(before, since);
    });
  }
  return pageNow() === n ? { ok: true, label: `page ${n} of ${last}` } : { ok: false, arg: "page", why: `the listing stayed on page ${pageNow()}`, options: [] };
}

async function filterListing(p: FilterListing, c: MoveContext): Promise<string | null | PerformResult> {
  if (typeof p.category_path !== "string" || !p.category_path.trim()) c.refuse("category_path", "say which listing, as /categoria/<slug>/<code> or /busqueda/<words>");
  const want = wantedListing(p.category_path);
  if (!want) c.refuse("category_path", `"${p.category_path}" is not a listing; use a /categoria/<slug>/<code> path from the category list, or /busqueda/<words>`);
  const raw = Array.isArray(p.filters) ? p.filters : [];
  const wanted = raw.map(parseFilter).filter((x): x is { facet: string; value: string } => x !== null);
  const bad = raw.filter((x) => !parseFilter(x));
  const offRaw = Array.isArray(p.remove) ? p.remove : [];
  const off = offRaw.map(parseFilter).filter((x): x is { facet: string; value: string } => x !== null);
  if (p.page != null && (!Number.isInteger(p.page) || p.page < 1)) c.refuse("page", `a page from 1, not ${p.page}`);
  if (!(await onListing(c, want, p))) return null;
  if (!isListing()) throw new Error(`${want.path} did not open as a listing (now on ${location.pathname})`);
  await waitFor(() => document.querySelector("app-filter-element") && gridUp(), 10_000);
  await quiet(main(), 300, 1500);

  const done: string[] = [];
  const missed: Refusal[] = [
    ...bad.map((x) => ({ arg: "filters", why: `"${String(x)}" is not "Facet: Option"`, options: [] })),
    ...offRaw.filter((x) => !parseFilter(x)).map((x) => ({ arg: "remove", why: `"${String(x)}" is not "Facet: Option"`, options: [] })),
  ];
  const take = (got: Applied | Missed, arg?: string) => {
    if (got.ok) done.push(got.label);
    else missed.push({ arg: arg ?? got.arg, why: got.why, options: got.options });
  };
  // Off first, in place; then only the options named, one at a time (one
  // already on stays on); then the sort; then the page.
  if (p.clear) take(await clearFilters(c));
  for (const o of off) take(await removeFilter(c, o.facet, o.value));
  for (const w of wanted) take(await applyOption(c, w.facet, w.value, "filters", "filters"));
  if (p.sort) take(await applySort(c, p.sort), "sort");
  if (p.page != null && p.page !== pageNow()) take(await turnPage(c, p.page));
  const grid = await showGrid(c);
  const asked = wanted.length + bad.length + offRaw.length + (p.clear ? 1 : 0) + (p.sort ? 1 : 0) + (p.page != null ? 1 : 0);
  if (asked && !done.length && missed.length) {
    const first = missed[0]!;
    c.refuse(first.arg, missed.map((m) => m.why).join("; "), first.options ?? []);
  }
  if (done.length && missed.length) return { outcome: "partial", detail: `applied ${done.join(", ")}; ${grid}`, refused: missed };
  return [grid, done.length ? `applied ${done.join(", ")}` : ""].filter(Boolean).join("; ");
}

/** Before a cue on a listing: the listing at `path` must be the one in front,
 *  or the app is moved there. */
async function cueListing(c: MoveContext, path: string | null | undefined, p: object & Arrived): Promise<boolean> {
  const want = path ? wantedListing(path) : null;
  if (path && !want) c.refuse("path", `"${path}" is not a listing`);
  if (want && !(await onListing(c, want, p))) return false;
  if (!isListing()) throw new Error(`no product listing is on screen (now on ${location.pathname})`);
  await waitFor(() => document.querySelector("app-filter-element") && gridUp(), 8000);
  return true;
}

/** The filter cue: one option of one facet, as its words are said, or several
 *  of one facet joined by commas. Each is added to what is on; one that does
 *  not take makes it `partial`. */
async function filterCue(p: { facet: string; value?: string | null; path?: string | null } & Arrived, c: MoveContext): Promise<string | null | PerformResult> {
  if (!clean(p.facet)) c.refuse("facet", "say which filter, as the listing names it", groups().map((g) => g.name));
  // `{filter: Marca: LUBRITEK}` arrives as one argument.
  let facet = clean(p.facet);
  let value = clean(p.value);
  if (!value && facet.includes(":")) [facet, value] = [clean(facet.split(":")[0]), clean(facet.split(":").slice(1).join(":"))];
  if (!(await cueListing(c, p.path, p))) return null;
  // A campaign's switch ("{filter: Campaña | Agrofertas Octubre}").
  const campaigns = (await apiOptions(CAMPAIGN))?.options ?? [];
  if (campaignMeant(facet, value, campaigns) || CAMPAIGN_WORDS.test(norm(facet).replace(/\s+/g, "")) || norm(facet) === norm(CAMPAIGN)) {
    const got = await applyOption(c, facet, value, "value", "facet");
    if (!got.ok) c.refuse(got.arg, got.why, got.options);
    return `${got.label} on; ${await showGrid(c)}`;
  }
  const g = findGroup(facet);
  if (!g) c.refuse("facet", `this listing has no filter "${facet}"`, [...(campaigns.length ? [CAMPAIGN] : []), ...groups().map((x) => x.name)]);
  if (!value) c.refuse("value", `say which ${g.name}`, ((await apiOptions(g.name))?.options ?? []).slice(0, MAX_OPTIONS));
  const done: string[] = [];
  const missed: Missed[] = [];
  for (const v of value.split(",").map(clean).filter(Boolean)) {
    const got = await applyOption(c, g.name, v);
    if (got.ok) done.push(got.label);
    else missed.push(got);
  }
  if (!done.length) c.refuse(missed[0]!.arg, missed.map((m) => m.why).join("; "), missed[0]!.options);
  const detail = `${done.join(", ")} on; ${await showGrid(c)}`;
  if (missed.length) return { outcome: "partial", detail, refused: missed.map((m) => ({ arg: m.arg, why: m.why, options: m.options })) };
  return detail;
}

/** The sort cue. */
async function sortCue(p: { order: string; path?: string | null } & Arrived, c: MoveContext): Promise<string | null> {
  if (!(await cueListing(c, p.path, p))) return null;
  const got = await applySort(c, p.order);
  if (!got.ok) c.refuse(got.arg, got.why, got.options);
  return `${got.label}; ${await showGrid(c)}`;
}

// open_product, product.tab ─────────────────────────────────────────────────

type Tab = "details" | "specs" | "photos" | "zoom" | "price" | "docs" | "related";
const TABS: Tab[] = ["details", "specs", "photos", "zoom", "price", "docs", "related"];

async function ringThere(c: MoveContext, el: HTMLElement | HTMLElement[], label: string): Promise<void> {
  const els = Array.isArray(el) ? el : [el];
  const box = boxOf(els);
  const tall = box ? box.bottom - box.top > window.innerHeight - headerHeight() - 40 : false;
  await scrollTo(els[0]!, tall ? "top" : "center");
  await c.ring(els, label);
}

/** "Detalle del Producto" or "Especificaciones": the section scrolled to and
 *  ringed (its "Ver más" pressed first when the card is folded). */
async function showDetails(tab: "details" | "specs", c: MoveContext): Promise<string> {
  const section = tabSection(tab === "specs" ? /^(?:especificaciones|specifications)/ : /^(?:detalle del producto|product detail)/);
  if (!section) c.refuse("tab", `this product page has no ${tab === "specs" ? "Especificaciones" : "Detalle del Producto"}`, TABS);
  const more = [...document.querySelectorAll<HTMLElement>("app-product-tabs button.swatchButton")].find((b) => shown(b) && /ver m[aá]s|(?:see|show|view|read) more/i.test(clean(b.textContent)));
  if (more && tab === "specs") {
    await scrollTo(more, "center");
    await c.ring(more, "Ver más");
    press(more);
    await sleep(400);
  }
  const label = clean(section.title.textContent);
  await ringThere(c, section.block, label);
  if (tab === "specs") {
    const rows = specRows();
    return `showed Especificaciones: ${rows.map((r) => `${r.label} ${r.value}`).join("; ") || "no rows"}`;
  }
  return `showed ${label}`;
}

/** Step the gallery through a few photos: its thumbnails, or its own next
 *  arrow; a product with one photo has it ringed. */
async function showPhotos(c: MoveContext): Promise<string> {
  const gallery = document.querySelector<HTMLElement>("app-product-image");
  if (!gallery) throw new Error("this product page has no gallery");
  const thumbs = [...gallery.querySelectorAll<HTMLElement>(".leftBlock .swiper-slide mat-card")].filter(shown);
  await scrollToTopOfPage();
  await c.ring(gallery, "fotos");
  const steps = Math.min(3, Math.max(0, thumbs.length - 1));
  for (let i = 1; i <= steps; i++) {
    await sleep(1100);
    press(thumbs[i]!);
  }
  let stepped = steps;
  if (!steps) {
    const next = gallery.querySelector<HTMLElement>(".contenido .swiper-button-next:not([hidden]):not(.swiper-button-disabled)");
    for (let i = 0; next && shown(next) && i < 3 && !next.classList.contains("swiper-button-disabled"); i++) {
      await sleep(1100);
      press(next);
      stepped++;
    }
  }
  const total = Math.max(thumbs.length, gallery.querySelectorAll(".contenido .swiper-slide").length, 1);
  return stepped ? `stepped the gallery through ${stepped + 1} of ${total} photos` : `the product has ${total} photo${total === 1 ? "" : "s"}; ringed the gallery`;
}

/** The big photo: the main photo's own zoom (`app-product-zoom`, a press on
 *  the photo enlarges it in place, and the pointer moves across it), left
 *  zoomed for the visitor; a press again, or the next move, folds it. */
async function zoomPhoto(c: MoveContext): Promise<string> {
  await scrollToTopOfPage();
  const zoomImg = () => [...document.querySelectorAll<HTMLElement>("app-product-image app-product-zoom img")].find((i) => shown(i) && inViewSideways(i)) ?? null;
  // The zoom is drawn once the pointer is over the main photo.
  const photo = [...document.querySelectorAll<HTMLElement>("app-product-image .contenido .swiper-slide-active, app-product-image .contenido img")].find(shown);
  if (photo && !zoomImg()) {
    const r = photo.getBoundingClientRect();
    for (const type of ["pointerover", "mouseover", "mouseenter", "mousemove"]) {
      photo.dispatchEvent(new MouseEvent(type, { bubbles: type !== "mouseenter", view: window, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 }));
    }
    await waitFor(zoomImg, 1500);
  }
  const img = zoomImg();
  if (!img) c.refuse("tab", "this product page has no big photo to open", TABS.filter((t) => t !== "zoom"));
  const frame = img.closest<HTMLElement>("app-product-zoom") ?? img;
  await c.ring(frame, "Foto");
  const before = img.getAttribute("style") ?? "";
  const r = img.getBoundingClientRect();
  const at = (fx: number, fy: number, type: string) =>
    img.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window, clientX: r.left + r.width * fx, clientY: r.top + r.height * fy }));
  at(0.5, 0.5, "mouseenter");
  at(0.5, 0.5, "mouseover");
  at(0.5, 0.5, "mousemove");
  at(0.5, 0.5, "mousedown");
  at(0.5, 0.5, "mouseup");
  press(img);
  await sleep(500);
  // A small pass around the middle, as a pointer looking closer would: the
  // zoom pans with the pointer, pixel for pixel, from where it was pressed.
  for (const [dx, dy] of [[-24, -16], [0, 0], [24, 16], [0, 0]] as const) {
    at(0.5 + dx / r.width, 0.5 + dy / r.height, "mousemove");
    await sleep(400);
  }
  const zoomed = (img.getAttribute("style") ?? "") !== before || /zoom/i.test(frame.className);
  await c.ring(frame, "Foto");
  return zoomed ? "opened the big photo (the page's zoom) and moved across it; left open" : "pressed the photo to enlarge it";
}

/** The price with its buttons: "Cotizar" and "Agregar al carro" (or the
 *  quantity they turn into), or "Confirmar precio en tienda". */
async function showPrice(c: MoveContext): Promise<string> {
  const box = info();
  if (!box) throw new Error("this product page shows no price");
  const hidden = priceHiddenIn(box);
  const price = box.querySelector<HTMLElement>(hidden ? "p.bg-yellow" : ".prices-plp") ?? box.querySelector<HTMLElement>(".prices-plp");
  const buttons = [...box.querySelectorAll<HTMLElement>("#addToCart, app-input-update-quantity")].find(shown)?.closest<HTMLElement>("div.ng-star-inserted, div") ?? null;
  const parts = [price, buttons].filter((x): x is HTMLElement => x !== null && shown(x));
  if (!parts.length) throw new Error("this product page shows no price");
  await scrollToTopOfPage();
  await c.ring(parts, hidden ? "Confirmar precio en tienda" : clean(price?.textContent));
  const p = readProduct();
  return hidden ? "the page says Confirmar precio en tienda: no price is published for it" : `showed the price $${p?.price ?? "?"} and its buttons`;
}

/** The data sheets: their rows ("Hoja de Seguridad", "Ficha Técnica") with
 *  their "Descargar" buttons, ringed and never pressed (each opens a PDF in
 *  a new tab, the visitor's to open). The specifications' "Ver más" is
 *  pressed first when the card is folded. */
async function showDocs(c: MoveContext): Promise<string> {
  let rows = docRows().filter((d) => shown(d.row));
  if (!rows.length && docRows().length) {
    const more = [...document.querySelectorAll<HTMLElement>("app-product-tabs button.swatchButton")].find((b) => shown(b) && /ver m[aá]s|(?:see|show|view|read) more/i.test(clean(b.textContent)));
    if (more) {
      await scrollTo(more, "center");
      await c.ring(more, "Ver más");
      press(more);
      await waitFor(() => docRows().some((d) => shown(d.row)), 1500);
    }
    rows = docRows().filter((d) => shown(d.row));
  }
  if (!rows.length) c.refuse("tab", "this product has no data sheet (no Hoja de Seguridad or Ficha Técnica)", TABS.filter((t) => t !== "docs"));
  const labels = rows.map((r) => r.label);
  await ringThere(c, rows.map((r) => r.row), labels.join(" · "));
  return `showed ${labels.join(" and ")} with their Descargar buttons (each opens a PDF in a new tab; not opened)`;
}

/** "Complemente su compra": the carousel scrolled to and ringed. */
async function showRelated(c: MoveContext): Promise<string> {
  const box = relatedBox();
  const items = relatedItems();
  if (!box || !items.length) c.refuse("tab", "this product has no related products (no Complemente su compra)", TABS.filter((t) => t !== "related"));
  await ringThere(c, box, clean(box.querySelector("span.fs-18, span")?.textContent) || "Complemente su compra");
  return `showed Complemente su compra: ${items
    .slice(0, 5)
    .map((i) => `${i.name}${i.price != null ? ` ($${i.price})` : ""}`)
    .join("; ")}`;
}

async function productTab(p: { tab: Tab }, c: MoveContext): Promise<string> {
  if (!onProductPage()) throw new Error(`no product page is on screen (now on ${location.pathname})`);
  await waitFor(() => productUp(), 8000);
  if (p.tab === "docs") return showDocs(c);
  if (p.tab === "related") {
    // The carousel draws after the product (its own call).
    await waitFor(() => relatedItems().length, 3000);
    return showRelated(c);
  }
  if (p.tab === "photos") return showPhotos(c);
  if (p.tab === "zoom") return zoomPhoto(c);
  if (p.tab === "price") return showPrice(c);
  if (p.tab === "details" || p.tab === "specs") return showDetails(p.tab, c);
  c.refuse("tab", `no tab "${p.tab}"`, TABS);
}

async function openProduct(p: { path: string; tab?: Tab | null } & Arrived, c: MoveContext): Promise<string | null> {
  const sku = productSku(p.path);
  if (!sku) c.refuse("path", "say which product, as /producto/<slug>/<sku>");
  if (!(await navigate(c, productPath(sku, p.path.split("/")[2] ?? ""), () => productUp(sku), again(c, p)))) return null;
  if (!onProductPage() || pageSku() !== sku) throw new Error(`${p.path} did not open as a product page (now on ${location.pathname})`);
  const product = readProduct();
  if (product) report("product_shown", latestProductFor(product));
  void confirmProduct();
  let did = "";
  if (p.tab) did = await productTab({ tab: p.tab }, c);
  else {
    // The product is the effect: its name and price are ringed after the
    // result, which goes as soon as the page is up.
    c.after(async () => {
      await scrollToTopOfPage();
      const box = info();
      const parts = [box?.querySelector("h2.black-name"), box?.querySelector(".prices-plp, p.bg-yellow")].filter((x): x is Element => Boolean(x));
      if (parts.length) await c.ring(parts);
    });
  }
  return [
    product
      ? `${product.name} is on screen ${product.price_hidden ? "with Confirmar precio en tienda (no price published)" : `at $${product.price ?? "?"}`}; SKU ${product.sku}`
      : "the product page is on screen",
    did,
  ]
    .filter(Boolean)
    .join("; ");
}

// find_products, check_prices, check_stock: reads ──────────────────────────

interface FindProducts {
  query?: string | null;
  category_code?: string | null;
  brand?: string | null;
  sort?: Sort | null;
}

const itemOf = (r: ApiProduct): FoundItem => {
  const hidden = r.hidePriceByCategory === true;
  const name = clean(r.name);
  return {
    path: productPath(r.code, name),
    sku: r.code,
    name,
    brand: clean(r.brand),
    price: hidden ? null : pesos(r.price?.value),
    regular_price: null,
    discount: offerOf(r)?.discount ?? null,
    offer_price: offerOf(r)?.offer_price ?? null,
    price_hidden: hidden,
    stock: stockStatus(r.stock),
    stock_level: typeof r.stock?.stockLevel === "number" ? r.stock.stockLevel : null,
  };
};

async function findProducts(p: FindProducts, c: MoveContext): Promise<string> {
  const query = clean(p.query);
  const category = clean(p.category_code);
  if (!query && !category && !clean(p.brand)) c.refuse("query", "say what to look for, a category code or a brand");
  const sort = p.sort ? SORT_CODES[p.sort] ?? "" : "";
  const request = (q: string) =>
    query
      ? `${API}/search/refineSearch?q=${encodeURIComponent(q)}&page=0&sort=${sort}&pageSize=40`
      : `${API}/category/getCategory?code=${encodeURIComponent(category || "agroplanetProducts")}&q=${encodeURIComponent(q)}&page=0&sort=${sort}&pageSize=40`;
  const scoped = (words: string) => (words ? (category ? `${words}::category:${category}` : words) : "");
  let q = scoped(query);
  let answer = await getJson<ApiListing>(request(q));
  // Nothing for the words as said, and the store suggests a spelling
  // ("cuchiya" → "cuchilla"): that, once, said so in the report.
  const suggested = clean(answer.data?.spellingSuggestion?.suggestion);
  let retried: string | null = null;
  if (query && !(answer.data?.pagination?.totalNumberOfResults ?? answer.data?.results?.length ?? 0) && suggested && norm(suggested) !== norm(query)) {
    const again = await getJson<ApiListing>(request(scoped(suggested))).catch(() => null);
    if (again) {
      answer = again;
      q = scoped(suggested);
      retried = suggested;
    }
  }
  if (p.brand) {
    // A brand by the store's own facet for these products.
    const facet = (answer.data?.facets ?? []).find((f) => f.code === "brand_search" || /^marca$/i.test(clean(f.name)));
    const values = (facet?.values ?? []) as (ApiFacetValue & { code?: string })[];
    const hit = best(values, (v) => clean(v.name), p.brand);
    if (!hit) c.refuse("brand", `no ${p.brand} among these products`, values.map((v) => clean(v.name)).slice(0, MAX_OPTIONS));
    q = `${q}${q.includes("::") ? ":" : "::"}brand_search:${hit.code ?? clean(hit.name)}`;
    answer = await getJson<ApiListing>(request(q));
  }
  const items = (answer.data?.results ?? []).slice(0, MAX_FOUND).map(itemOf);
  const total = answer.data?.pagination?.totalNumberOfResults ?? items.length;
  told("products_found", {
    query: query || null,
    category_code: category || null,
    brand: p.brand ?? null,
    total,
    suggestion: suggested || clean(answer.data?.spellingSuggestion?.suggestion) || null,
    retried_with: retried,
    items,
  } satisfies ProductsFound);
  return `${retried ? `nothing for "${query}"; searched the store's suggestion "${retried}": ` : ""}${total} products match; ${items
    .slice(0, 4)
    .map((i) => `${i.name} (${i.price_hidden ? "precio a confirmar en tienda" : `$${i.price ?? "?"}`}, ${i.path})`)
    .join("; ") || "none"}`;
}

async function checkPrices(p: { paths: string[] }, c: MoveContext): Promise<string> {
  const skus = [...new Set((Array.isArray(p.paths) ? p.paths : []).map((x) => productSku(x)).filter((x): x is string => x !== null))].slice(0, MAX_PRICED);
  if (!skus.length) c.refuse("paths", "say which products, as /producto/<slug>/<sku> paths");
  const reads = await Promise.all(
    skus.map(async (sku) => {
      try {
        return itemOf(await productApi(sku)) satisfies PriceItem;
      } catch {
        return sku;
      }
    }),
  );
  const items = reads.filter((r): r is FoundItem => typeof r !== "string");
  const missing = reads.filter((r): r is string => typeof r === "string").map((sku) => productPath(sku));
  told("prices_read", { items, missing } satisfies PricesRead);
  return [
    items.map((i) => `${i.name}: ${i.price_hidden ? "Confirmar precio en tienda (no price published)" : `$${i.price ?? "?"}`}, stock ${i.stock || "?"}${i.stock_level != null ? ` (${i.stock_level})` : ""}`).join("; "),
    missing.length ? `not found: ${missing.join(", ")}` : "",
  ]
    .filter(Boolean)
    .join("; ");
}

async function checkStock(p: { path: string; store?: string | null }, c: MoveContext): Promise<string> {
  const sku = productSku(p.path);
  if (!sku) c.refuse("path", "say which product, as /producto/<slug>/<sku>");
  const asked = clean(p.store) || null;
  let matched: string[] = [];
  if (asked) {
    matched = storesMeant(asked, STORES.map((s) => s[0]));
    if (!matched.length) c.refuse("store", `no Agroplanet store "${asked}"`, STORES.map((s) => s[0]));
  }
  const prod = await productApi(sku);
  const online = stockStatus(prod.stock);
  const level = typeof prod.stock?.stockLevel === "number" ? prod.stock.stockLevel : null;
  // The store publishes one stock for the product, not a stock per store
  // (`stockByStore` repeats it, `findStoreStockByRegionAndCommune` is empty).
  const payload: StockRead = {
    path: productPath(sku, clean(prod.name)),
    sku,
    name: clean(prod.name),
    online,
    online_level: level,
    stores: [],
    asked,
    matched: matched.length ? matched.join(", ") : null,
  };
  told("stock_read", payload);
  // On the product's own page: its price and buttons ringed.
  if (onProductPage() && pageSku() === sku) {
    const box = info()?.querySelector<HTMLElement>(".prices-plp, p.bg-yellow");
    if (box) await ringThere(c, box, clean(prod.name));
  }
  return `${payload.name}: stock ${online || "unknown"}${level != null ? ` (${level} units)` : ""}; the store does not publish stock by store${matched.length ? ` (asked about ${matched.join(", ")})` : ""}`;
}

// check_fit ─────────────────────────────────────────────────────────────────

/** The store's compatibility records for a part (`product/getPartAppRecords`,
 *  the drill the Autoplanet site draws as "Compatibilidad" and Agroplanet's
 *  product page leaves out): makes, then a make's models, a model's years, a
 *  year's engines. "No existen resultados" is no records. */
interface FitTree {
  lstBrand?: { brand?: string; count?: number }[] | null;
  lstModel?: { brand?: string; model?: string; count?: number }[] | null;
  lstYear?: { year?: string | number; count?: number }[] | null;
  lstEngine?: { engine?: string; notas?: unknown[] | null }[] | null;
}
const fitApi = (sku: string, drill: { brand?: string; model?: string; year?: string } = {}) => {
  const q = new URLSearchParams({ productCode: sku });
  for (const [k, v] of Object.entries(drill)) if (v) q.set(k, v);
  return getJson<FitTree>(`${API}/product/getPartAppRecords?${q.toString().replace(/\+/g, "%20")}`).catch(() => ({}) as FitTree);
};

/** What a farmer calls a make: "MF", "Massey", "John Deere", "JD". */
const MAKE_ALIASES: Record<string, string> = {
  mf: "massey ferguson", massey: "massey ferguson", masey: "massey ferguson", "masey ferguson": "massey ferguson", jd: "john deere", deere: "john deere", nh: "new holland",
  case: "case international", "case ih": "case international", deutz: "deutz-fahr", "deutz fahr": "deutz-fahr", valtra: "valtra-valmet", valmet: "valtra-valmet",
};
const MAX_FIT_BRANDS = 4;
const MAX_FIT_MODELS = 30;

/** A model as the catalogue writes it, from what was said: "290" is "290",
 *  "MF 290" too; never "2900". */
function modelMeant(said: string, models: string[]): string | null {
  const want = bare(said);
  if (!want) return null;
  const exact = models.find((m) => bare(m) === want);
  if (exact) return exact;
  const token = models.find((m) => norm(m).split(/[\s/-]+/).some((t) => bare(t) === want));
  return token ?? models.find((m) => want.endsWith(bare(m)) && bare(m).length >= 3) ?? null;
}

async function checkFit(p: { path: string; brand?: string | null; model?: string | null; year?: string | null }, c: MoveContext): Promise<string> {
  const sku = productSku(p.path);
  if (!sku) c.refuse("path", "say which product, as /producto/<slug>/<sku>");
  const asked = { brand: clean(p.brand) || null, model: clean(p.model) || null, year: clean(p.year) || null };
  const [tree, prod] = await Promise.all([fitApi(sku), productApi(sku).catch(() => null)]);
  const name = clean(prod?.name) || (onProductPage() && pageSku() === sku ? clean(info()?.querySelector("h2.black-name")?.textContent) : "");
  const makes = (tree.lstBrand ?? []).filter((b) => clean(b.brand));
  const universal = makes.length > 0 && makes.every((b) => norm(b.brand) === "universal");
  const brands: FitBrand[] = [];
  const out: FitRead = { path: productPath(sku, name), sku, name, universal, brands, total: makes.reduce((n, b) => n + (Number(b.count) || 0), 0) || null, ...asked, matched: null, match: null, missing: null };
  if (!universal && makes.length) {
    const said = asked.brand ? (MAKE_ALIASES[norm(asked.brand)] ?? asked.brand) : null;
    const make = said ? (best(makes, (b) => clean(b.brand), said) ?? makes.find((b) => bare(b.brand).startsWith(bare(said)))) : null;
    if (asked.brand && !make) {
      out.matched = false;
      out.missing = asked.brand;
    }
    // The makes it is listed for; below the one asked (or each, when few),
    // its models; below the model asked, its years; below the year, engines.
    const drill = make ? [make] : !asked.brand && makes.length <= MAX_FIT_BRANDS ? makes : [];
    for (const b of makes) brands.push({ brand: clean(b.brand), count: Number(b.count) || null, models: [], years: [], engines: [] });
    for (const b of drill) {
      const row = brands.find((x) => x.brand === clean(b.brand))!;
      const models = ((await fitApi(sku, { brand: clean(b.brand) })).lstModel ?? []).map((m) => clean(m.model)).filter(Boolean);
      row.models = models.slice(0, MAX_FIT_MODELS);
      // The model asked, under the make asked (or under any make, when none was).
      if (!asked.model || out.matched === true || (make && b !== make)) continue;
      const model = modelMeant(asked.model, models);
      if (!model) {
        if (make) [out.matched, out.missing] = [false, `${row.brand} ${asked.model}`];
        continue;
      }
      row.models = [model];
      const years = ((await fitApi(sku, { brand: row.brand, model })).lstYear ?? []).map((y) => clean(String(y.year ?? ""))).filter(Boolean);
      row.years = years;
      const wantYear = asked.year;
      const year = wantYear ? (years.find((y) => y === wantYear) ?? (wantYear.length === 2 ? years.find((y) => y.endsWith(wantYear)) : undefined)) : undefined;
      if (wantYear && !year) {
        [out.matched, out.missing] = [false, `${row.brand} ${model} del ${wantYear}`];
        continue;
      }
      if (year) {
        row.years = [year];
        row.engines = ((await fitApi(sku, { brand: row.brand, model, year })).lstEngine ?? []).map((e) => clean(e.engine)).filter(Boolean).slice(0, 6);
      }
      out.matched = true;
      out.missing = null;
      out.match = [row.brand, model, year ?? (years.length > 1 ? `${years[0]} to ${years[years.length - 1]}` : (years[0] ?? ""))].filter(Boolean).join(" ");
    }
    if (asked.model && !make && !asked.brand && out.matched === null) [out.matched, out.missing] = [false, asked.model];
    if (make && !asked.model && out.matched === null) [out.matched, out.match] = [true, clean(make.brand)];
  } else if (universal || asked.brand) {
    out.matched = universal ? null : false;
  }
  if (universal) brands.splice(0);
  told("fit_read", out);
  // On the part's own page: its name ringed while he answers.
  if (onProductPage() && pageSku() === sku) {
    const box = info();
    const parts = [box?.querySelector<HTMLElement>("h2.black-name"), box?.querySelector<HTMLElement>("a.black-brand")].filter((x): x is HTMLElement => Boolean(x));
    if (parts.length) await ringThere(c, parts, name);
  }
  const listed = universal ? "UNIVERSAL (a generic part)" : makes.length ? makes.map((b) => clean(b.brand)).join(", ") : "no machine (no records)";
  const verdict = out.matched === true ? `; ${out.match} is listed` : out.matched === false ? `; ${out.missing} is not listed` : "";
  return `${name || sku}: listed for ${listed}${verdict}`;
}

// stores.show ───────────────────────────────────────────────────────────────

interface StoreCard {
  el: HTMLElement;
  name: string;
  address: string;
  city: string;
  phone: string;
  hours: string;
}

/** The value after a "Label:" span on a store card. */
function cardField(el: Element, label: RegExp): string {
  for (const s of el.querySelectorAll("span.field-mobile")) {
    if (label.test(clean(s.textContent))) return clean(s.nextElementSibling?.textContent);
  }
  return "";
}

function storeCards(): StoreCard[] {
  return [...document.querySelectorAll<HTMLElement>("app-store-list mat-card")]
    .map((el) => {
      const title = el.querySelector(".fs20");
      const name = clean(title?.querySelectorAll("b")[1]?.textContent ?? title?.textContent?.replace(/^(?:tienda|store)/i, ""));
      const address = cardField(el, /^(?:direcci[oó]n|address)/i);
      const city = clean(address.split(",").slice(-2, -1)[0]);
      const hours = [...el.querySelectorAll<HTMLElement>("span")]
        .filter((s) => !s.querySelector("span") && /^(lunes|martes|s[aá]bado|domingo|monday|tuesday|saturday|sunday)/i.test(clean(s.textContent)))
        .map((s) => clean(s.textContent))
        .join("; ");
      return { el, name, address, city, phone: cardField(el, /^(?:t[eé]l[eé]fono|telephone|phone)/i), hours };
    })
    .filter((s) => s.name);
}

/** The store list's own page numbers (it shows ten stores a page). */
const storePages = () =>
  [...document.querySelectorAll<HTMLElement>("app-store-list pagination-controls li a, app-store-list pagination-template li a")].filter(
    (a) => shown(a) && /^\d+$/.test(clean(a.textContent).replace(/^page\s*/i, "")),
  );

async function showStore(p: { name: string } & Arrived, c: MoveContext): Promise<string | null> {
  const said = clean(p.name);
  if (!said) c.refuse("name", "say which store");
  const names = storesMeant(said, STORES.map((s) => s[0]));
  if (!names.length) c.refuse("name", `no Agroplanet store "${said}"`, STORES.map((s) => s[0]));
  if (!(await navigate(c, "/nuestras-tiendas", () => storeCards().length, again(c, p)))) return null;
  await waitFor(() => storeCards().length, 8000);
  const find = () => storeCards().find((s) => names.some((n) => bare(n) === bare(s.name))) ?? null;
  let card = find();
  // Ten stores a page, in the order of the store's list: the page it is on
  // pressed by its number, else each page in turn.
  const pageOf = Math.floor(STORES.findIndex((s) => bare(s[0]) === bare(names[0]!)) / 10) + 1;
  const tried = new Set<string>();
  for (let i = 0; !card && i < 4; i++) {
    const pages = storePages();
    const current = clean(document.querySelector("app-store-list li.current")?.textContent).match(/\d+/)?.[0] ?? "1";
    tried.add(current);
    const num = (a: Element) => clean(a.textContent).match(/\d+/)?.[0] ?? "";
    const next = pages.find((a) => num(a) === String(pageOf) && !tried.has(num(a))) ?? pages.find((a) => !tried.has(num(a)));
    if (!next) break;
    await scrollTo(next, "center");
    await c.ring(next, `página ${clean(next.textContent).match(/\d+/)?.[0]}`);
    const before = storeCards()[0]?.name;
    press(next);
    await waitFor(() => storeCards()[0]?.name !== before, 3000);
    card = find();
  }
  if (!card) c.refuse("name", `no store "${said}" on /nuestras-tiendas`, STORES.map((s) => s[0]));
  await ringThere(c, card.el, card.name);
  const store: StoreShown = { name: card.name, address: card.address, city: card.city, phone: card.phone, hours: card.hours };
  told("store_shown", store);
  return `${card.name}: ${card.address}; ${card.phone ? `tel. ${card.phone}; ` : ""}${card.hours || "no hours on its card"}${names.length > 1 ? `; also ${names.filter((n) => bare(n) !== bare(card.name)).join(", ")}` : ""}`;
}

// commerce.cart_add, cart_show, cart_update ─────────────────────────────────

/** The product page's "Agregar al carro", by its id, never its words: the
 *  owner's Chrome translates the page, and a translated "Add to cart" is the
 *  same button (pcfactory dev call 9ec9601a). Kept from the translator too
 *  (anchors.ts). */
const addButton = () => [...document.querySelectorAll<HTMLButtonElement>("app-product-info #addToCart, app-product-info #addToCart2")].find(shown) ?? null;
const pdpStepper = () => {
  const q = [...document.querySelectorAll<HTMLElement>("app-product-info app-input-update-quantity")].find(shown);
  return q ? (q.parentElement as HTMLElement) : null;
};

/** Press `button` and wait for the app's own write to the cart. */
async function cartPress(c: MoveContext, button: HTMLElement, ms = 9000): Promise<boolean> {
  const was = cartWrites;
  const since = Date.now();
  c.progress("waiting_site");
  press(button);
  const took = await waitFor(() => cartWrites > was, ms);
  await apiSettled(since, 3000);
  return Boolean(took);
}

async function addToCart(p: { path: string; qty?: number } & Arrived, c: MoveContext): Promise<string | null | PerformResult> {
  const sku = productSku(p.path);
  if (!sku) c.refuse("path", "say which product, as /producto/<slug>/<sku>");
  const qty = Math.round(Number(p.qty ?? 1));
  if (!Number.isFinite(qty) || qty < 1 || qty > 20) c.refuse("qty", `a quantity from 1 to 20, not ${p.qty}`);
  if (!(await navigate(c, productPath(sku, p.path.split("/")[2] ?? ""), () => productUp(sku), again(c, p)))) return null;
  if (pageSku() !== sku) throw new Error(`${p.path} did not open as a product page (now on ${location.pathname})`);
  await waitFor(() => addButton() ?? pdpStepper(), 10_000);
  if (!addButton() && !pdpStepper()) {
    throw new Error("the product page shows no Agregar al carro (out of stock, or its price is confirmed in store?); nothing was added");
  }
  const start = (await readCart()).items.find((i) => productSku(i.path) === sku)?.qty ?? 0;
  let left = qty;
  const button = addButton();
  if (button) {
    await scrollTo(button, "center");
    await c.ring(button, "Agregar al carro");
    if (!(await cartPress(c, button))) throw new Error("pressed Agregar al carro, but the cart did not change; ask the visitor to check the cart");
    left--;
  }
  // The button turns into the page's own − / +: each + adds one more.
  if (left > 0) {
    const box = await waitFor(pdpStepper, 4000);
    const { plus, input } = stepper(box);
    if (!box || !plus) throw new Error("added it, but the page shows no + for more");
    await scrollTo(box, "center");
    await c.ring(box, `+ ${left}`);
    for (; left > 0; left--) {
      const was = Number(input?.value) || 0;
      if (!(await cartPress(c, plus, 6000))) break;
      await waitFor(() => (Number(input?.value) || 0) > was, 1500);
      await sleep(250);
    }
  }
  await sleep(300);
  const cart = await readCart();
  reportCart(cart);
  const line = cart.items.find((l) => productSku(l.path) === sku);
  const name = line?.name || readProduct()?.name || p.path;
  const added = (line?.qty ?? 0) - start;
  // The quantity the button turned into is the effect: ringed after.
  c.after(async () => {
    const box = pdpStepper();
    if (box) await c.ring(box, `Cantidad: ${line?.qty ?? qty}`);
  });
  const detail = `added ${added} x ${name}${line ? ` (the cart line now has ${line.qty})` : ""}; ${cartLine(cart)}`;
  if (added < qty) return { outcome: "partial", detail, refused: [{ arg: "qty", why: `only ${added} of ${qty} went in`, options: [] }] };
  return detail;
}

/** The mini-cart (the header cart's menu), when it is open. */
const miniCart = () => [...document.querySelectorAll<HTMLElement>(".cdk-overlay-container .mat-menu-panel.preCart, .cdk-overlay-container app-mini-cart")].find(shown) ?? null;

const cartUp = () => routeUp("cart");

async function showCart(p: { open?: boolean } & Arrived, c: MoveContext): Promise<string | null> {
  if (p.open === false) {
    const mini = miniCart();
    if (!mini) return "nothing of the cart was open";
    document.querySelector<HTMLElement>(".cdk-overlay-backdrop")?.click();
    await waitFor(() => !miniCart(), 1500);
    c.spotlight.clear();
    return "closed the mini-cart";
  }
  if (!(await navigate(c, "/carro", cartUp, again(c, p)))) return null;
  await quiet(main(), 300, 1500);
  const cart = await readCart();
  reportCart(cart);
  c.after(async () => {
    await scrollToTopOfPage();
    const parts = [...document.querySelectorAll<HTMLElement>("app-cart .bloque-izquierdo mat-card, app-cart .bloque-derecho mat-card")].filter((x) => visible(x)).slice(0, 2);
    if (parts.length) await c.ring(parts, "Carro de Compra");
  });
  return `the cart is on screen; ${cartLine(cart)}${cart.items.length ? `: ${cart.items.map((i) => `${i.qty} × ${i.name}`).join("; ")}` : ""}`;
}

/** A cart line's "Eliminar", by what it is: the line's one link with no
 *  address (its name links to the product), its words only to choose
 *  between two. Kept from the translator too (anchors.ts). */
function removeLink(row: Element): HTMLElement | null {
  const links = [...row.querySelectorAll<HTMLElement>("a:not([href])")].filter(shown);
  return (
    links.find((a) => /^(?:eliminar|delete|remove)$/i.test(clean(a.textContent))) ??
    (links.length === 1 ? links[0]! : null) ??
    links.find((a) => a.querySelector("span.text-underline")) ??
    null
  );
}

/** The cart's "Cotizar", by what it is: its orange button (the summary's,
 *  or the sticky bar's `#cartPay`), never its words. */
const quoteButton = () =>
  [...document.querySelectorAll<HTMLElement>("app-cart #cartPay, app-cart button.btn-round-orange-fill")].find(shown) ??
  [...document.querySelectorAll<HTMLElement>("app-cart button")].find((b) => /^(?:cotizar|quote|get a quote|request a quote)$/i.test(clean(b.textContent)) && shown(b)) ??
  null;

/** How many presses one change may take. */
const MAX_CART_STEPS = 20;

async function updateCartItem(p: { path: string; qty: number } & Arrived, c: MoveContext): Promise<string | null> {
  const sku = productSku(p.path);
  if (!sku) c.refuse("path", "say which product, as /producto/<slug>/<sku>");
  const qty = Math.round(Number(p.qty));
  if (!Number.isFinite(qty) || qty < 0 || qty > 20) c.refuse("qty", `a quantity from 0 to 20, not ${p.qty}`);
  if (!(await navigate(c, "/carro", cartUp, again(c, p)))) return null;
  await waitFor(() => cartRows().length, 8000);
  await quiet(main(), 300, 1500);
  const rowOf = () => cartRows().find((r) => rowSku(r) === sku) ?? null;
  const row = rowOf();
  if (!row) c.refuse("path", `${p.path} is not in the cart`, cartRows().map((r) => `${rowName(r)} (${productPath(rowSku(r) ?? "", rowName(r))})`));
  const name = rowName(row);
  await scrollTo(row, "center");
  if (qty === 0) {
    const remove = removeLink(row);
    if (!remove) throw new Error("the cart line has no Eliminar");
    await c.ring(row, `Eliminar ${name}`);
    await cartPress(c, remove);
    // A confirmation window, should the app ask.
    const confirm = await waitFor(
      () =>
        [...document.querySelectorAll<HTMLElement>(".cdk-overlay-container mat-dialog-container button")].find(
          (b) => /eliminar|aceptar|s[ií]\b|delete|remove|accept|^ok$|yes/i.test(clean(b.textContent)) && shown(b),
        ),
      800,
    );
    if (confirm) await cartPress(c, confirm);
    if (!(await waitFor(() => !rowOf(), 8000))) throw new Error("pressed Eliminar, but the line is still in the cart");
  } else {
    await c.ring(row, `${name}: ${qty}`);
    for (let step = 0; step < MAX_CART_STEPS; step++) {
      const r = rowOf();
      if (!r) throw new Error("the cart line went away");
      const now = rowQty(r);
      if (now === qty) break;
      const { plus, minus } = stepper(r);
      const button = now < qty ? plus : minus;
      if (!button || button.disabled) throw new Error(`the cart's ${now < qty ? "+" : "−"} cannot be pressed at ${now}`);
      await cartPress(c, button, 6000);
      if (!(await waitFor(() => rowOf() && rowQty(rowOf()!) !== now, 4000))) throw new Error(`pressed ${now < qty ? "+" : "−"}, but the line stayed at ${now}`);
      await sleep(200);
    }
    const r = rowOf();
    if (!r || rowQty(r) !== qty) throw new Error(`the line shows ${r ? rowQty(r) : 0}, not ${qty}`);
  }
  await quiet(main(), 400, 2500);
  const cart = await readCart();
  reportCart(cart);
  const summary = document.querySelector<HTMLElement>("app-cart .bloque-derecho mat-card");
  if (summary) c.after(() => c.ring(summary));
  return `${qty === 0 ? `removed ${name}` : `${name} set to ${qty}`}; ${cartLine(cart)}`;
}

// start_quote, fill_quote ───────────────────────────────────────────────────

const quoteUp = () => Boolean(form());

/** The Formulario de cotización: the cart's "Cotizar" pressed (on the cart
 *  page, opened first), then the form reported, every field still the
 *  visitor's to see. */
async function startQuote(p: Arrived, c: MoveContext): Promise<string | null> {
  if (kindOf() !== "quote") {
    if (!(await navigate(c, "/carro", cartUp, again(c, p)))) return null;
    await waitFor(() => cartRows().length, 6000);
    if (!cartRows().length) throw new Error("the cart is empty; add something first");
    const go = quoteButton();
    if (!go) throw new Error("the cart shows no Cotizar");
    await scrollTo(go, "center");
    await c.ring(go, "Cotizar");
    c.progress("waiting_site");
    press(go);
    if (!(await waitFor(() => kindOf() === "quote" && quoteUp(), ROUTE_MS))) throw new Error(`pressed Cotizar, but the quote form did not open (now on ${location.pathname})`);
    await quiet(main(), 300, 1500);
  }
  await waitFor(quoteUp, 8000);
  const state = readQuote();
  report("quote_state", state);
  const card = document.querySelector<HTMLElement>("app-form-user-quote mat-card");
  if (card) c.after(() => ringThere(c, card, "Formulario de cotización"));
  return `on the Formulario de cotización (${state.items ?? "?"} products, total $${state.total ?? "?"}); still to fill: ${state.missing.join(", ") || "nothing"}. The RUT and Crear cotización are the visitor's`;
}

interface FillQuote extends Arrived {
  name?: string | null;
  phone?: string | null;
  email?: string | null;
  region?: string | null;
  commune?: string | null;
  street?: string | null;
  number?: string | null;
  unit?: string | null;
  notes?: string | null;
}

/** The brain's field → the form's control, in the form's order. */
const TEXT_FIELDS: [arg: keyof FillQuote, control: (typeof QUOTE_FIELDS)[number], label: string][] = [
  ["name", "name", "Nombre Completo / Razón Social"],
  ["phone", "phone", "Teléfono"],
  ["email", "email", "Correo electrónico"],
  ["street", "street", "Calle"],
  ["number", "numberAddress", "Número"],
  ["unit", "depto", "Dpto / casa / Oficina"],
  ["notes", "reference", "Instrucciones"],
];

/** A Chilean phone as the form takes it: nine digits, without +56. */
function phoneDigits(raw: string): string | null {
  let d = raw.replace(/\D/g, "");
  if (d.length === 11 && d.startsWith("56")) d = d.slice(2);
  return d.length === 9 ? d : null;
}

/** Choose `value` in a Material select of the form: its trigger pressed, the
 *  matching option (accents and dashes folded) ringed and pressed. */
async function choose(c: MoveContext, id: "region" | "commune", value: string, label: string): Promise<{ ok: true; text: string } | Missed> {
  const select = document.querySelector<HTMLElement>(`app-form-user-quote mat-select#${id}`);
  if (!select) return { ok: false, arg: id, why: `the form shows no ${label}`, options: [] };
  const trigger = select.querySelector<HTMLElement>(".mat-select-trigger") ?? select;
  await scrollTo(select, "center");
  await c.ring(select.closest("mat-form-field") ?? select, label);
  const optionsNow = () => [...document.querySelectorAll<HTMLElement>(".cdk-overlay-container mat-option")].filter((o) => shown(o) && o.getAttribute("aria-disabled") !== "true");
  for (let i = 0; i < 2 && !optionsNow().length; i++) {
    press(trigger);
    await waitFor(() => optionsNow().length, 2500);
  }
  const all = optionsNow();
  if (!all.length) return { ok: false, arg: id, why: `${label} offers no options yet${id === "commune" ? " (choose the región first)" : ""}`, options: [] };
  const opt = best(all, (o) => clean(o.textContent), value);
  if (!opt) {
    const names = all.map((o) => clean(o.textContent));
    document.querySelector<HTMLElement>(".cdk-overlay-backdrop")?.click();
    return { ok: false, arg: id, why: `${label} has no "${value}"`, options: names.slice(0, 60) };
  }
  const text = clean(opt.textContent);
  opt.scrollIntoView({ block: "nearest" });
  await c.ring(opt, text);
  const since = Date.now();
  press(opt);
  await waitFor(() => !optionsNow().length, 2000);
  await apiSettled(since, 2500);
  return { ok: true, text };
}

/**
 * The quote form, filled with what the visitor said yes to: each field typed
 * at a visitor's pace (and left, so the form validates it), the región and
 * comuna chosen from their own lists. Never the RUT, never "Crear
 * cotización": `typeInto` refuses the one and `press` the other, whatever
 * arrives.
 */
async function fillQuote(p: FillQuote, c: MoveContext): Promise<string | null | PerformResult> {
  const given = [...TEXT_FIELDS.map((f) => f[0]), "region", "commune"].filter((k) => clean(p[k as keyof FillQuote] as string | null | undefined));
  if (!given.length) c.refuse("name", "say what to write in the form: name, phone, email, region, commune, street, number, unit or notes");
  if (!(await navigate(c, "/cotizacion", quoteUp, again(c, p)))) return null;
  await waitFor(quoteUp, 8000);
  await quiet(main(), 300, 1500);
  const done: string[] = [];
  const missed: Refusal[] = [];
  const typeField = async ([arg, name, label]: (typeof TEXT_FIELDS)[number]) => {
    let value = clean(p[arg] as string | null | undefined);
    if (!value) return;
    const el = control(name) as HTMLInputElement | HTMLTextAreaElement | null;
    if (!el) {
      missed.push({ arg, why: `the form shows no ${label}`, options: [] });
      return;
    }
    if (arg === "phone") {
      const digits = phoneDigits(value);
      if (!digits) {
        missed.push({ arg, why: `the form takes a phone of nine digits (912345678), not "${value}"`, options: [] });
        return;
      }
      value = digits;
    }
    await scrollTo(el, "center");
    await c.ring(el.closest("mat-form-field") ?? el, label);
    await typeInto(el, value, 70);
    leave(el);
    await sleep(150);
    done.push(arg);
  };
  for (const f of TEXT_FIELDS.slice(0, 3)) await typeField(f);
  if (clean(p.region)) {
    const got = await choose(c, "region", clean(p.region), "Región");
    if (got.ok) done.push("region");
    else missed.push({ arg: "region", why: got.why, options: got.options });
  }
  if (clean(p.commune)) {
    // The comunas load once the región is chosen.
    await waitFor(() => hasValue(control("region")), 1500);
    const got = await choose(c, "commune", clean(p.commune), "Comuna");
    if (got.ok) done.push("commune");
    else missed.push({ arg: "commune", why: got.why, options: got.options });
  }
  for (const f of TEXT_FIELDS.slice(3)) await typeField(f);
  await quiet(main(), 300, 1500);
  const state = readQuote();
  report("quote_state", state);
  const button =
    [...document.querySelectorAll<HTMLElement>("app-form-user-quote button")].find((b) => /crear cotizaci|create (?:a |the )?quot/i.test(clean(b.textContent))) ??
    document.querySelector<HTMLElement>("app-form-user-quote button.btn-round-orange-fill");
  const rut = control("rut");
  // What is left is the visitor's: the RUT, then "Crear cotización".
  c.after(async () => {
    const parts = [rut?.closest("mat-form-field"), button].filter((x): x is Element => Boolean(x) && shown(x as Element));
    if (parts.length) {
      await scrollTo(parts[0]!, "center");
      await c.ring(parts, "RUT y Crear cotización: tuyos");
    }
  });
  const detail = `filled ${done.join(", ") || "nothing"}; still missing: ${state.missing.join(", ") || "nothing"}. The visitor types the RUT and presses Crear cotización`;
  if (!done.length && missed.length) c.refuse(String(missed[0]!.arg), missed.map((m) => m.why).join("; "), missed[0]!.options ?? []);
  if (missed.length) return { outcome: "partial", detail, refused: missed };
  return detail;
}

// The page, show and faq cues ───────────────────────────────────────────────

/** The page cue: open `path` at its top, in the app; on it already, its top. */
async function openPage(p: { path: string } & Arrived, c: MoveContext): Promise<string | null> {
  if (typeof p.path !== "string" || !p.path.trim()) c.refuse("path", "say which page to go to, as a path");
  const to = new URL(p.path.trim(), location.origin);
  const path = to.pathname + to.search;
  target(path);
  if (!here(path) || !routeUp()) {
    const kind = kindFor(to.pathname);
    if (!(await navigate(c, path, () => routeUp(kind), again(c, p)))) return null;
    await scrollToTopOfPage();
    return `${decodeURIComponent(location.pathname)} is on screen${headings()[0] ? `: ${headings()[0]!.text}` : ""}`;
  }
  await scrollToTopOfPage();
  const title = headings()[0]?.el ?? info();
  if (title) await c.ring(title);
  return `${decodeURIComponent(location.pathname)} is on screen`;
}

/** The kind of page at `path`, before the app is there. */
function kindFor(path: string): Kind {
  const p = decodeURIComponent(path).toLowerCase().replace(/\/+$/, "") || "/";
  if (p === "/" || p === "/inicio") return "home";
  if (p.startsWith("/producto/")) return "product";
  if (p.startsWith("/categoria/")) return "category";
  if (p.startsWith("/busqueda/")) return "search";
  if (p.startsWith("/marca/")) return "brand";
  if (p === "/carro") return "cart";
  if (p.startsWith("/cotizacion")) return "quote";
  if (p === "/nuestras-tiendas") return "stores";
  if (POLICY.test(p)) return "policy";
  return "page";
}

/** On `path` first, when the cue names another page: the app moved there. */
async function onPage(c: MoveContext, path: string | null | undefined, p: Record<string, unknown> & Arrived): Promise<boolean> {
  if (!path) return true;
  const to = new URL(path, location.origin);
  if (here(to.pathname + to.search)) return true;
  const kind = kindFor(to.pathname);
  return navigate(c, to.pathname + to.search, () => routeUp(kind), again(c, p));
}

const original = (el: Element | null | undefined) => el?.getAttribute("data-voqalize-text") ?? "";

function findHeading(heading: string): HTMLElement | null {
  const all = headings();
  return best(all, (x) => x.text, heading)?.el ?? best(all, (x) => original(x.el), heading)?.el ?? null;
}

/** What a heading heads: the largest block around it that holds no other
 *  heading and fits on the screen, else the heading alone. */
function sectionOf(h: HTMLElement): HTMLElement[] {
  let found: HTMLElement | null = null;
  const all = headings().map((x) => x.el);
  for (let el = h.parentElement; el && el !== main() && el !== document.body; el = el.parentElement) {
    if (all.some((x) => x !== h && el.contains(x))) break;
    const b = boxOf([el]);
    if (b && b.bottom - b.top > window.innerHeight * 1.1) break;
    found = el;
  }
  return found && clean(found.textContent).length > clean(h.textContent).length + 20 ? [found] : [h];
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

/** The home's parts that have no heading, by the words a visitor uses. */
const HOME_PARTS: [words: RegExp, selector: string, label: string][] = [
  [/^(banner|banners|carrusel|ofertas del mes|hero|portada|promociones)$/, "app-main-carousel, #mainCarrusel", "Ofertas"],
  [/^(marcas|brands)$/, "app-brands-carousel-home", "Marcas"],
];

/** Product cards on the page: the grid's and the home's rails'. */
function productCards(): { el: HTMLElement; name: string }[] {
  const out: { el: HTMLElement; name: string }[] = cards().map((a) => ({ el: a as HTMLElement, name: cardName(a) }));
  for (const card of main().querySelectorAll<HTMLElement>("app-product-card")) {
    const name = clean(card.querySelector("p.title, .h-name p, img")?.textContent) || clean(card.querySelector("img")?.getAttribute("alt"));
    if (name && !out.some((o) => o.el.contains(card))) out.push({ el: card, name });
  }
  return out;
}

/** Whether `el` is on the screen sideways (a carousel's card can be off its
 *  edge). */
const inViewSideways = (el: Element) => {
  const r = el.getBoundingClientRect();
  return r.left >= -4 && r.right <= window.innerWidth + 4;
};

/** The show cue: a heading of the page with what it heads; on a product page
 *  its sections and a specification row by its label; a home part with no
 *  heading; a store card; a product card by its name; a question; or, when
 *  nothing is called that, the smallest block with those words. */
async function showSection(p: { target: string; path?: string | null } & Arrived, c: MoveContext): Promise<string | null> {
  const want = clean(p.target);
  if (!want) c.refuse("target", "say which heading or words to show");
  if (!(await onPage(c, p.path, { ...p, target: want, path: null }))) return null;
  // The rails and the store list draw after the route: wait for the words.
  await waitFor(() => findHeading(want) || smallestContaining(main(), want), 3000);

  if (onProductPage()) {
    const tabs: Record<string, Tab> = {
      "detalle del producto": "details", detalle: "details", especificaciones: "specs", fotos: "photos", foto: "zoom", zoom: "zoom", precio: "price",
      "hoja de seguridad": "docs", "ficha tecnica": "docs", "complemente su compra": "related",
    };
    const tab = tabs[norm(want)];
    if (tab) return productTab({ tab }, c);
    const row = best([...specRows(), ...equivalenceRows()], (r) => r.label, want);
    if (row && norm(row.label).length >= Math.min(4, norm(want).length)) {
      await ringThere(c, row.row, `${row.label}: ${row.value}`);
      return `showed ${row.label}: ${row.value}`;
    }
  }
  const h = findHeading(want);
  if (h) {
    await ringThere(c, sectionOf(h), clean(h.textContent));
    return `showed "${clean(h.textContent)}"`;
  }
  if (kindOf() === "home") {
    const part = HOME_PARTS.find(([words]) => words.test(norm(want)));
    const el = part ? document.querySelector<HTMLElement>(part[1]) : null;
    if (part && el) {
      await ringThere(c, el, part[2]);
      return `showed the home's ${part[2]}`;
    }
  }
  if (kindOf() === "stores") {
    const all = storeCards().filter((s) => shown(s.el));
    const names = storesMeant(want, all.map((x) => x.name));
    const hit = all.find((s) => s.name === names[0]);
    if (hit) {
      await ringThere(c, hit.el, hit.name);
      return `showed the store ${hit.name}: ${hit.address}`;
    }
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

/** The faq cue: the panel ringed, opened with its own header, and ringed
 *  with its answer. */
async function openFaq(p: { question: string; path?: string | null } & Arrived, c: MoveContext): Promise<string | null> {
  const question = clean(p.question);
  if (!question) c.refuse("question", "say which question");
  if (!(await onPage(c, p.path, { ...p, question, path: null }))) return null;
  await waitFor(() => faqItems().length, 4000);
  const all = faqItems();
  const item = best(all, (f) => f.question, question) ?? best(all, (f) => original(f.block.querySelector("mat-panel-title *")), question);
  if (!item) c.refuse("question", `no question "${question}" on ${location.pathname}`, all.map((f) => f.question).slice(0, 15));
  await scrollTo(item.block, "center");
  if (!item.isOpen() && item.toggle) {
    await c.ring(item.toggle, item.question);
    press(item.toggle);
    await waitFor(item.isOpen, 2000);
    await sleep(350);
  }
  const group = [item.block];
  const box = boxOf(group);
  await scrollTo(item.block, box && box.bottom - box.top > window.innerHeight * 0.7 ? "top" : "center");
  await c.ring(group, item.question);
  return `opened "${item.question}"`;
}

// ─── Registering the moves ────────────────────────────────────────────────

/** A move made with the category menu folded first: the flyout one move
 *  opened closes itself on the next. A move means a call: the home's late
 *  splash window is watched for from then (`guardSplash`). */
const menuFolded =
  <A, R>(fn: (p: A, c: MoveContext) => Promise<R>) =>
  async (p: A, c: MoveContext): Promise<R> => {
    guardSplash();
    await closeMenu().catch(() => false);
    return fn(p, c);
  };

/** Every move this page makes, by the id the brain names it with: its class,
 *  a cue's argument names and the arguments' types come from
 *  `agroplanet/scene.json`, and a move left out does not compile. */
export function registerMoves(moves: Moves): void {
  who = () => moves.author();
  scene.registerAll(moves, {
    "page.open": menuFolded(openPage),
    "page.show": menuFolded(showSection),
    "page.faq": menuFolded(openFaq),
    "menu.open": openMenu,
    "product.tab": menuFolded(productTab),
    "stores.show": menuFolded(showStore),
    "commerce.filter": menuFolded(filterCue),
    "commerce.sort": menuFolded(sortCue),
    "commerce.search": menuFolded(searchProducts),
    "commerce.cart_add": menuFolded(addToCart),
    "commerce.cart_update": menuFolded(updateCartItem),
    "commerce.cart_show": menuFolded(showCart),
    filter_listing: menuFolded(filterListing),
    open_product: menuFolded(openProduct),
    find_products: menuFolded(findProducts),
    check_prices: menuFolded(checkPrices),
    check_stock: menuFolded(checkStock),
    check_fit: menuFolded(checkFit),
    start_quote: menuFolded(startQuote),
    fill_quote: menuFolded(fillQuote),
  });
}

// ─── Watching the page ────────────────────────────────────────────────────

let lastUrl: string | null = null;
let routeGen = 0;
let stopWatching: (() => void) | null = null;

/**
 * The address changed without a load: the app's router moved (a link, his
 * move, the visitor's back button) or a listing took a filter, a sort or a
 * page. Once the new route has drawn, its watchers are picked again (a
 * product page watches other things than a listing), the page is reported
 * (`page_changed`), and its state read.
 */
function urlChanged(): void {
  const now = location.origin + location.pathname + location.search;
  if (now === lastUrl) return;
  lastUrl = now;
  const gen = ++routeGen;
  void (async () => {
    await waitFor(() => routeUp(), 8000);
    await quiet(main(), 300, 2000);
    if (gen !== routeGen) return;
    if (emitter) {
      stopWatching?.();
      stopWatching = watchState();
      emitter("page_changed", context());
    }
    readState();
  })();
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
  window.addEventListener("popstate", () => queueMicrotask(urlChanged));
  window.addEventListener("hashchange", urlChanged);
}

/** `fn` once changes pause for `ms`, and at least every `most` while they
 *  never pause (the home's carousels move all the time). */
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

/** The cart, whoever changed it: the app's own `cart/add`, `cart/update` and
 *  `cart/delete`, heard as they come back. */
const cartChanged = debounced(() => void readCart().then(reportCart), 600, 2500);
onApi((url, method) => {
  if (/\/cart\/(add|update|delete)\b/.test(url) || (method === "POST" && /\/cart\//.test(url))) {
    cartWrites++;
    cartChanged();
  }
});

/** What the route in front shows, each reported when it settles: a
 *  listing's grid, a product, the cart's lines, the quote form. Picked by the
 *  route's kind, again on every route change. */
function watchState(): () => void {
  const observers: MutationObserver[] = [];
  const cleanups: (() => void)[] = [];
  const watch = (el: Element | null, fn: () => void, ms?: number) => {
    if (!el) return;
    const obs = new MutationObserver(debounced(fn, ms));
    obs.observe(el, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["class"] });
    observers.push(obs);
  };
  const kind = kindOf();
  if (isListing()) watch(document.querySelector("app-plp-grid") ?? main(), () => void reportListing());
  if (kind === "product") {
    watch(document.querySelector("app-product-info") ?? main(), () => {
      const product = readProduct();
      if (product) report("product_shown", latestProductFor(product));
    }, 800);
  }
  if (kind === "quote") {
    watch(document.querySelector("app-quote") ?? main(), reportQuote, 600);
    // Typing changes no DOM a watcher sees: the form's own input events.
    const onInput = debounced(reportQuote, 800);
    document.addEventListener("input", onInput, true);
    document.addEventListener("focusout", onInput, true);
    cleanups.push(() => {
      document.removeEventListener("input", onInput, true);
      document.removeEventListener("focusout", onInput, true);
    });
  }
  return () => {
    observers.forEach((o) => o.disconnect());
    cleanups.forEach((f) => f());
  };
}

/** This page's state, read now: the product, the listing, the quote, the
 *  cart. */
function readState(): void {
  const kind = kindOf();
  if (kind === "product") {
    // The page's read first, then the store's live one.
    void waitFor(() => productUp(), 10_000).then(() => {
      const product = readProduct();
      if (product) report("product_shown", latestProductFor(product));
      void confirmProduct();
    });
  } else if (isListing()) {
    void waitFor(gridUp, 10_000).then(() => reportListing());
  } else if (kind === "quote") {
    void waitFor(quoteUp, 8000).then(reportQuote);
  }
  if (kind === "cart") void readCart().then(reportCart);
  else void cartIfChanged();
}

/** Report the page and the state on it through `next`, as it changes, until
 *  the returned stop: from the moment the agent can hear this page. */
export function start(next: (event: string, payload: unknown) => void): () => void {
  emitter = next;
  lastUrl = location.origin + location.pathname + location.search;
  for (const [event, payload] of latest) report(event, payload);
  readState();
  stopWatching ??= watchState();
  // The page was reported as it stood when the agent could first hear it,
  // which on a fresh load can be before the app drew the route: once it has,
  // again if its headings or panels came in since, and the route's watchers
  // picked for what it shows now.
  const first = JSON.stringify(context());
  const url = lastUrl;
  void waitFor(() => routeUp(), 10_000).then(async () => {
    await quiet(main(), 300, 2000);
    if (emitter !== next || lastUrl !== url) return;
    stopWatching?.();
    stopWatching = watchState();
    const now = context();
    if (JSON.stringify(now) !== first) next("page_changed", now);
  });
  return () => {
    if (emitter === next) {
      emitter = null;
      stopWatching?.();
      stopWatching = null;
    }
  };
}

let prepared = false;

/** Ready the page, once: its style, the address and API watches, and its
 *  state read as soon as it settles (a page that loads mid-call reports it
 *  the moment it listens). */
export function prepare(): void {
  if (prepared) return;
  prepared = true;
  styleThePage();
  watchUrl();
  watchApi();
  void settled().then(readState);
}

/** The page in front, as it stands: once the agent can hear this page (before
 *  `start`), and again each time the tab comes back to the front (Stage's
 *  host runs it). */
export function reportPage(next: (event: string, payload: unknown) => void): void {
  next("page_changed", context());
}

/** Agroplanet's adapter for `@voqalize/stage/extension`: its moves, what the
 *  visitor is looking at for the session's start, and its reports. */
export const agroplanet: Adapter = (moves, kit) => {
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
    // The app draws its routes after the document is parsed, and `load`
    // waits on trackers: a press waits for the shell to settle, never for
    // `load`.
    ready: settled,
  };
};

// Exported for the end-to-end tests.
export { context, readCart, readListing, readProduct, readQuote };
