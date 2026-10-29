/**
 * www.agroplanet.cl, offline: trimmed copies of its routes as the Angular app
 * drew them (test/pages/, made by make-fixtures.mjs from pages saved live on
 * 2026-10-29) served at their real addresses, the store's API at
 * api.agroplanet.cl answered from bodies saved the same day (test/pages/api/)
 * with a cart kept here, and the few behaviours of the app the adapter leans
 * on, simulated:
 *
 *   - the router: a press on one of its links, or `pushState` + `popstate`,
 *     swaps the route's component (the element after the last
 *     `<router-outlet>`) and the breadcrumb for the next route's, without a
 *     load, a moment after the route's own API call (by XMLHttpRequest, as
 *     the app's HttpClient makes them);
 *   - a listing: the facet panels fold and open, a ticked option asks the API
 *     for the listing with it (the API answers with the saved one, filtered by
 *     brand, sorted, its facets marked), then the grid is redrawn from that
 *     answer and the panels folded again; "Ordenar por" and its menu; the
 *     page links;
 *   - the search box's suggestions after three letters, and Enter;
 *   - "Todas las categorías", its list and the flyout a hovered item opens;
 *   - "Agregar al carro" and the stepper it turns into (its ids swapped, as
 *     the app's are), the cart page's − / +, "Eliminar" and "Cotizar";
 *   - the quote form: its región and comuna selects, the validation that
 *     enables "Crear cotización" (pressing it is recorded, never answered);
 *   - the store list's pages, the policy panels, the home's splash window,
 *     the cookie bar's "Entendido", the product photo's zoom.
 *
 * Everything else on the network is refused. The adapter bundle
 * (test/.build/adapter.js, `node test/build-adapter.mjs`) is injected into
 * every page at DOMContentLoaded, as `content.js` would be.
 */

import type { Page, Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
export const ORIGIN = "https://www.agroplanet.cl";
const API_HOST = "https://api.agroplanet.cl";
const page = (name: string) => readFileSync(join(here, "pages", name), "utf8");
const api = <T = unknown>(name: string) => JSON.parse(readFileSync(join(here, "pages", "api", `${name}.json`), "utf8")) as T;

export const PRODUCT = "/producto/aceite_lubritek_utf_semisintetico_19l/1173221";
export const HIDDEN = "/producto/bujes_de_biela_55_4107_semi_federal_mogul/139083";
export const CATEGORY = "/categoria/lubricantes/AG100";
export const SEARCH = "/busqueda/bateria";

/** What each address serves; any other product is the saved one under its
 *  own SKU. */
function pageFor(path: string): string | null {
  const p = decodeURIComponent(path).replace(/\/+$/, "").toLowerCase() || "/";
  if (p === "/" || p === "/inicio") return page("home.html");
  if (p.startsWith("/categoria/")) return page("category.html");
  if (p.startsWith("/busqueda/")) return page("search.html");
  const sku = p.match(/^\/producto\/(?:[^/]*\/)?(\d+)$/)?.[1];
  if (sku === "139083") return page("product-hidden.html");
  if (sku) return page("product.html").replaceAll("1173221", sku);
  if (p === "/carro") return page("cart.html");
  if (p === "/cotizacion") return page("cotizacion.html");
  if (p === "/nuestras-tiendas") return page("tiendas.html");
  if (p === "/cambios-devoluciones") return page("cambios-devoluciones.html");
  return null;
}

export interface Seen {
  /** Every call to the store's API, as "METHOD /path?query [body]". */
  api: string[];
  /** The documents loaded (full loads only), path and query. */
  pages: string[];
}

interface Line {
  code: string;
  name: string;
  qty: number;
}

const CORS = { "access-control-allow-origin": ORIGIN, "access-control-allow-credentials": "true", "access-control-allow-headers": "*", "access-control-allow-methods": "GET, POST" };

type Listing = {
  data: {
    name?: string;
    data: {
      results: { code: string; name: string; brand?: string; price?: { value?: number } }[];
      pagination: { totalNumberOfResults: number; numberOfPages: number; currentPage: number };
      facets: { name: string; code: string; values: { name: string; count?: number; selected?: boolean; query: { query: { value: string } } }[] }[];
      sorts?: unknown;
    };
  };
};

/** The listing the API answers for `q`, `sort` and `page`: the saved one, its
 *  results narrowed to the brands ticked and ordered by price, each facet
 *  value marked and carrying the query that toggles it, as Hybris does. */
function listingFor(name: "category-AG100" | "search-bateria", q: string, sort: string, page: number): Listing {
  const body = api<Listing>(name);
  const d = body.data.data;
  const parts = q.split(":");
  const text = parts[0] ?? "";
  const pairs: [string, string][] = [];
  for (let i = 2; i + 1 < parts.length; i += 2) if (parts[i]) pairs.push([parts[i]!, parts[i + 1]!.replace(/\+/g, " ")]);
  const toggled = (code: string, value: string) => {
    const has = pairs.some(([c, v]) => c === code && v === value);
    const next = has ? pairs.filter(([c, v]) => !(c === code && v === value)) : [...pairs, [code, value] as [string, string]];
    return next.length ? `${text}::${next.map(([c, v]) => `${c}:${v}`).join(":")}` : text;
  };
  for (const f of d.facets) {
    for (const v of f.values) {
      v.selected = pairs.some(([c, val]) => c === f.code && val === v.name);
      v.query = { query: { value: toggled(f.code, v.name) } };
    }
  }
  const brands = pairs.filter(([c]) => c === "brand_search").map(([, v]) => v);
  let results = brands.length ? d.results.filter((r) => brands.includes(r.brand ?? "")) : [...d.results];
  const total = pairs.length ? results.length : d.pagination.totalNumberOfResults;
  if (sort === "price-asc") results.sort((a, b) => (a.price?.value ?? 0) - (b.price?.value ?? 0));
  if (sort === "price-desc") results.sort((a, b) => (b.price?.value ?? 0) - (a.price?.value ?? 0));
  // A second page: the saved first, the other way round.
  if (page > 0) results = results.reverse();
  d.results = results;
  d.pagination = { ...d.pagination, totalNumberOfResults: total, numberOfPages: Math.max(1, Math.ceil(total / 40)), currentPage: page };
  return body;
}

async function answerApi(route: Route, seen: Seen, cart: Line[]): Promise<void> {
  const request = route.request();
  const url = new URL(request.url());
  if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers: { ...CORS, "access-control-allow-origin": "*" } });
  const post = request.postData() ?? "";
  seen.api.push(`${request.method()} ${url.pathname.replace("/webapi", "")}${url.search}${post ? ` ${post}` : ""}`);
  const json = (body: unknown, status = 200) => route.fulfill({ status, headers: { ...CORS, "content-type": "application/json" }, body: JSON.stringify(body) });
  const ok = (data: unknown) => json({ statusCode: 200, isValid: true, data });
  const p = url.pathname.replace(/^\/webapi\/+/, "/");
  const q = url.searchParams;
  const form = new URLSearchParams(post);
  if (p === "/category/getCategory") return json(listingFor("category-AG100", q.get("q") ?? "", q.get("sort") ?? "", Number(q.get("page")) || 0));
  if (p === "/search/refineSearch") return json(listingFor("search-bateria", q.get("q") ?? "bateria", q.get("sort") ?? "", Number(q.get("page")) || 0));
  if (p === "/search/autocomplete/SearchBox") return json(api("autocomplete-bateria"));
  if (p === "/product/getProductDetail") {
    const sku = q.get("productCode") ?? "";
    if (sku === "1173221" || sku === "139083") return json(api(`product-${sku}`));
    if (/^\d+$/.test(sku)) {
      const body = api<{ data: Record<string, unknown> }>("product-1173221");
      return json({ ...body, data: { ...body.data, code: sku, name: `Producto ${sku}` } });
    }
    return json({ statusCode: 404, isValid: false, data: null });
  }
  const entry = api<{ basePrice: { value: number }; totalPrice: { value: number } }>("rollover-entry");
  const entries = () =>
    cart.map((l, i) => ({ ...entry, entryNumber: i, quantity: l.qty, totalPrice: { value: l.qty * entry.basePrice.value }, product: { code: l.code, name: l.name } }));
  if (p === "/minicart/cart/rollover") return ok(entries());
  if (p === "/minicart/cart/minicart") return ok({ totalUnitCount: cart.reduce((n, l) => n + l.qty, 0) });
  if (p === "/cart/add") {
    const code = form.get("productCodePost") ?? "";
    const line = cart.find((l) => l.code === code);
    if (line) line.qty += Number(form.get("quantity")) || 1;
    else cart.push({ code, name: code === "1173221" ? "Aceite LUBRITEK UTF Semisintético 19L" : `Producto ${code}`, qty: Number(form.get("quantity")) || 1 });
    return ok({ headerMessage: "Ha sido añadido a su pedido" });
  }
  if (p === "/cart/update") {
    const line = cart[Number(form.get("entryNumber"))];
    const qty = Number(form.get("quantity"));
    if (line) line.qty = qty;
    if (line && qty <= 0) cart.splice(cart.indexOf(line), 1);
    return ok({});
  }
  if (p === "/cart/delete") {
    cart.splice(Number(q.get("entryNumber")), 1);
    return ok({ infoMessage: "El Producto ha sido eliminado del carro." });
  }
  if (p === "/product/getRegions") return json(api("regions"));
  if (p === "/product/getComunes") return json(api("comunes-CL-MP"));
  return ok({});
}

/** What the page's simulation needs that it cannot fetch: the región and
 *  comuna lists, the stores of the list's later pages. */
function fixtureData() {
  const regions = api<{ data: { isocode: string; name: string }[] }>("regions").data;
  const comunes = api<{ data: { code: string; name: string }[] }>("comunes-CL-MP").data;
  const stores = [
    ["Casablanca", "Av. Constitución 359 , CASABLANCA, Valparaiso"], ["Vergara", "Vergara 47 , SANTIAGO, Metropolitana"], ["Santa Cruz", "Av. Ramón Sanfurgo 190 , SANTA CRUZ, Libertador Bernardo O'Higgins"],
    ["Los Andes", "Carlos Díaz 57 , LOS ANDES, Valparaiso"], ["Linares", "Av. Aníbal León Bustos 631 , LINARES, Maule"], ["Puerto Varas", "Av. Gramado SN Lote 1-A , PUERTO VARAS, Los Lagos"],
    ["San Fernando", "Av. Bernardo O’Higgins 124 , SAN FERNANDO, Libertador Bernardo O'Higgins"], ["Los Angeles", "Av. Sor Vicenta 2690 , LOS ANGELES, Bio-Bio"], ["Osorno", "Av. Bulnes 535 , OSORNO, Los Lagos"],
    ["Melipilla", "Vicuña Mackenna 479 , MELIPILLA, Metropolitana"], ["Victoria", "Av. Maturana 125 , VICTORIA, Araucania"], ["San Felipe", "Chacabuco 171 , SAN FELIPE, Valparaiso"], ["Parral", "Av. Dr. Patricio Blanco 330 , PARRAL, Maule"],
  ];
  return { regions: regions.map((r) => r.name), comunes: comunes.map((c) => c.name), stores };
}

/**
 * The app's own scripts, as far as the adapter leans on them. Declared here
 * and serialized into each page, so everything it uses is inside it.
 */
function simulateSite(data: { regions: string[]; comunes: string[]; stores: string[][] }, opts: { splash: boolean }): void {
  const API = "https://api.agroplanet.cl/webapi";
  const w = window as unknown as Record<string, unknown>;
  w.__pressedCrear = 0;
  const xhr = <T = unknown>(method: string, url: string, body?: string) =>
    new Promise<T>((resolve) => {
      const x = new XMLHttpRequest();
      x.open(method, url);
      x.withCredentials = true;
      if (body) x.setRequestHeader("content-type", "application/x-www-form-urlencoded;");
      x.onloadend = () => {
        try {
          resolve(JSON.parse(x.responseText) as T);
        } catch {
          resolve(null as T);
        }
      };
      x.send(body ?? null);
    });
  const later = (ms: number) => new Promise((r) => setTimeout(r, ms));
  const pesos = (n: number) => `$${Math.round(n).toLocaleString("es-CL")}`;
  const kind = () => {
    const p = decodeURIComponent(location.pathname).toLowerCase();
    if (p.startsWith("/categoria/")) return "category";
    if (p.startsWith("/busqueda/")) return "search";
    if (p.startsWith("/producto/")) return "product";
    if (p === "/carro") return "cart";
    if (p === "/cotizacion") return "quote";
    if (p === "/nuestras-tiendas") return "stores";
    return "page";
  };
  const slug = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");

  // ── The router ──────────────────────────────────────────────────────────
  const outlet = () => {
    const all = document.querySelectorAll("mat-sidenav-content router-outlet");
    return all[all.length - 1]?.nextElementSibling ?? null;
  };
  async function render(path: string): Promise<void> {
    await xhr("GET", `${API}/config/getSessionData`);
    const r = await fetch(`/__fixture?path=${encodeURIComponent(path)}`);
    if (!r.ok) return;
    const doc = new DOMParser().parseFromString(await r.text(), "text/html");
    const all = doc.querySelectorAll("mat-sidenav-content router-outlet");
    const next = all[all.length - 1]?.nextElementSibling;
    const now = outlet();
    if (next && now) now.replaceWith(document.importNode(next, true));
    const crumb = doc.querySelector("app-breadcrumb");
    if (crumb) document.querySelector("app-breadcrumb")?.replaceWith(document.importNode(crumb, true));
    document.title = doc.title;
    await afterRoute();
  }
  async function afterRoute(): Promise<void> {
    if (kind() === "category" || kind() === "search") await syncListing();
    if (kind() === "cart") await syncCart();
  }
  const navigate = (path: string) => {
    history.pushState(null, "", path);
    void render(path);
  };
  window.addEventListener("popstate", () => void render(location.pathname + location.search));

  // ── A listing ───────────────────────────────────────────────────────────
  type Facet = { name: string; code: string; values: { name: string; selected?: boolean; query: { query: { value: string } } }[] };
  type Answer = { data: { name?: string; data: { results: { code: string; name: string; brand?: string; price?: { value?: number }; hidePriceByCategory?: boolean }[]; facets: Facet[] } } };
  let template: Element | null = null;
  let facets: Facet[] = [];
  const listingUrl = () => {
    const q = new URLSearchParams(location.search);
    const code = location.pathname.split("/").pop();
    if (kind() === "search") return `${API}/search/refineSearch?q=${q.get("q") || decodeURIComponent(location.pathname.split("/").pop() ?? "")}&page=${q.get("page") || 0}&sort=${q.get("sort") ?? ""}&pageSize=40`;
    return `${API}/category/getCategory?code=${code}&q=${q.get("q") ?? ""}&page=${q.get("page") || 0}&sort=${q.get("sort") ?? ""}&pageSize=40`;
  };
  async function syncListing(): Promise<void> {
    const answer = await xhr<Answer>("GET", listingUrl());
    await later(120);
    if (!answer?.data) return;
    facets = answer.data.data.facets;
    const grid = document.querySelector("app-plp-grid");
    const cards = [...(grid?.querySelectorAll("a[href*='/producto/']") ?? [])].map((a) => a.closest(".m-04") ?? a);
    template ??= cards[0]?.cloneNode(true) as Element | null;
    const holder = cards[0]?.parentElement ?? grid?.querySelector(".ng-star-inserted:not(.list-box)");
    cards.forEach((c) => c.remove());
    for (const r of answer.data.data.results.slice(0, 8)) {
      if (!template || !holder) break;
      const card = template.cloneNode(true) as Element;
      card.querySelector("a")?.setAttribute("href", `/producto/${slug(r.name)}/${r.code}`);
      const title = card.querySelector("p.title");
      if (title) title.textContent = ` ${r.name} `;
      const brand = card.querySelector("p.black-text");
      if (brand) brand.textContent = ` ${r.brand ?? ""}`;
      const prices = card.querySelector(".prices");
      if (prices) prices.innerHTML = r.hidePriceByCategory ? `<p class="bg-yellow fw-500 mt-1 p-05"><span>Confirmar precio en tienda</span></p>` : `<div><span class="new-price">${pesos(r.price?.value ?? 0)}</span></div>`;
      holder.appendChild(card);
    }
    // The panels drawn again, folded but Precio, each box as the answer says.
    for (const el of document.querySelectorAll("app-filter-element")) {
      const panel = el.querySelector("mat-expansion-panel");
      const name = (panel?.querySelector("mat-panel-title")?.textContent ?? "").trim();
      if (!/precio/i.test(name)) panel?.classList.remove("mat-expanded");
      const f = facets.find((x) => x.name === name);
      for (const box of el.querySelectorAll("mat-checkbox")) {
        const label = (box.querySelector(".mat-checkbox-label")?.textContent ?? "").trim();
        box.classList.toggle("mat-checkbox-checked", Boolean(f?.values.find((v) => v.name === label)?.selected));
      }
    }
    const sort = new URLSearchParams(location.search).get("sort") ?? "";
    const trigger = [...document.querySelectorAll("a.mat-menu-trigger")].find((a) => /relevancia|precio/i.test(a.textContent ?? ""));
    const words = sort === "price-asc" ? "Menor precio" : sort === "price-desc" ? "Mayor precio" : "Relevancia";
    if (trigger?.querySelector(".mat-button-wrapper")?.firstChild) trigger.querySelector(".mat-button-wrapper")!.firstChild!.textContent = ` ${words}`;
  }
  const setListing = (changes: Record<string, string>) => {
    const u = new URL(location.href);
    for (const [k, v] of Object.entries(changes)) u.searchParams.set(k, v);
    for (const k of ["q", "page", "sort"]) if (!u.searchParams.has(k)) u.searchParams.set(k, k === "page" ? "0" : "");
    history.pushState(null, "", decodeURIComponent(u.pathname + u.search));
    void syncListing();
  };

  // ── The cart ────────────────────────────────────────────────────────────
  type Entry = { entryNumber: number; quantity: number; product: { code: string } };
  async function syncCart(): Promise<void> {
    const r = await xhr<{ data: Entry[] }>("GET", `${API}/minicart/cart/rollover`);
    const entries = r?.data ?? [];
    for (const row of document.querySelectorAll("app-cart-product")) {
      const code = row.querySelector("a[href*='/producto/']")?.getAttribute("href")?.split("/").pop();
      const e = entries.find((x) => x.product.code === code);
      if (!e) row.remove();
      else (row.querySelector("input[type=number]") as HTMLInputElement).value = String(e.quantity);
    }
    totals();
    if (!document.querySelector("app-cart-product")) {
      const cart = document.querySelector("app-cart");
      if (cart) cart.innerHTML = `<div class="cart-style"><p>Tu carro está vacío</p></div>`;
    }
  }
  const stepperHtml = (sku: string, qty: number) =>
    `<span class="fs-14 fw-500 color-text">Cantidad: </span><app-input-update-quantity class="w-35 ml-1"><div class="inputQuantityUpdate"><div class="main"><button id="add-${sku}" class="buttonMinusDisabled"><mat-icon class="mat-icon notranslate">remove</mat-icon></button><input type="number" id="${sku}"><button class="buttonAdd" id="minus-${sku}"><mat-icon class="mat-icon notranslate">add</mat-icon></button></div></div></app-input-update-quantity>`;

  // ── The quote form ──────────────────────────────────────────────────────
  const validate = () => {
    const formEl = document.querySelector("app-form-user-quote form");
    if (!formEl) return;
    let valid = true;
    for (const el of formEl.querySelectorAll<HTMLElement>("[formcontrolname]")) {
      const name = el.getAttribute("formcontrolname")!;
      const value = el.tagName === "MAT-SELECT" ? (el.getAttribute("data-value") ?? "") : (el as HTMLInputElement).value;
      const ok = name === "depto" || name === "reference" || (name === "phone" ? /^\d{9}$/.test(value) : value.trim().length >= (name === "email" ? 7 : 1));
      el.classList.toggle("ng-valid", ok);
      el.classList.toggle("ng-invalid", !ok);
      valid &&= ok;
    }
    const button = formEl.querySelector<HTMLButtonElement>("button.btn-round-orange-fill");
    if (button) button.disabled = !valid;
  };
  const overlay = () => document.querySelector(".cdk-overlay-container") ?? document.body.appendChild(Object.assign(document.createElement("div"), { className: "cdk-overlay-container" }));
  const closeOverlay = () => overlay().replaceChildren();
  function openSelect(select: HTMLElement): void {
    const list = select.id === "region" ? data.regions : data.comunes;
    if (select.id === "commune" && !document.querySelector("mat-select#region")?.getAttribute("data-value")) return;
    const panel = document.createElement("div");
    panel.className = "cdk-overlay-pane";
    panel.innerHTML = `<div class="cdk-overlay-backdrop"></div><div class="mat-select-panel" role="listbox"><mat-option class="mat-option" aria-disabled="true"><span class="mat-option-text">Seleccionar</span></mat-option>${list
      .map((n) => `<mat-option class="mat-option" role="option" aria-disabled="false"><span class="mat-option-text">${n}</span></mat-option>`)
      .join("")}</div>`;
    overlay().replaceChildren(panel);
    panel.querySelector(".cdk-overlay-backdrop")?.addEventListener("click", closeOverlay);
    for (const o of panel.querySelectorAll<HTMLElement>("mat-option[aria-disabled=false]")) {
      o.addEventListener("click", () => {
        const name = o.textContent!.trim();
        select.setAttribute("data-value", name);
        select.querySelector(".mat-select-value-text span")!.textContent = name;
        closeOverlay();
        if (select.id === "region") void xhr("GET", `${API}/product/getComunes?regionIsoCode=CL-MP`);
        validate();
      });
    }
  }

  // ── The menu ────────────────────────────────────────────────────────────
  function flyout(name: string): void {
    const menu = document.querySelector("#acordeon-main");
    menu?.querySelector("mat-sidenav.mat-drawer-opened")?.remove();
    const fly = document.createElement("mat-sidenav");
    fly.className = "mat-drawer mat-sidenav mat-drawer-opened";
    fly.setAttribute("style", "position: absolute; left: 288px; top: 0; width: 900px; background: #fff;");
    fly.innerHTML = `<app-submenu-desktop><div class="submenu-lateral"><div><a href="/categoria/x/AG10">${name}</a> Ver todo</div>${["Sistema Hidráulico", "Toma De Fuerza", "Embrague"]
      .map((s, i) => `<div><div class="mb-1 categorie fs14 fw-600"><a class="deco-none black-text fs16 pt-05" href="/categoria/${slug(s)}/AG1${70 + i}">${s}</a></div></div>`)
      .join("")}</div></app-submenu-desktop>`;
    menu?.appendChild(fly);
  }

  let storeCards: Element[] | null = null;

  /** The cart page's totals, as the app writes them after a change. */
  const totals = () => {
    let sum = 0;
    for (const row of document.querySelectorAll("app-cart-product")) sum += (Number((row.querySelector("input[type=number]") as HTMLInputElement | null)?.value) || 0) * 80000;
    document.querySelectorAll("app-cart .text-right b, app-cart div.text-right").forEach((el) => {
      if (!el.querySelector("b")) el.textContent = ` ${pesos(sum)} `;
    });
  };

  // ── Presses ─────────────────────────────────────────────────────────────
  document.addEventListener(
    "click",
    (e) => {
      const t = e.target as Element;
      if (t.closest("app-generic-dialog .close")) {
        document.querySelector("app-generic-dialog")?.closest(".cdk-overlay-pane, div")?.remove();
        document.documentElement.classList.remove("cdk-global-scrollblock");
        return;
      }
      if (t.closest(".cookies-wrapper button") && /entendido/i.test(t.closest("button")!.textContent ?? "")) {
        document.querySelector(".cookies-wrapper")?.remove();
        return;
      }
      const toggle = t.closest("app-menu-desktop .hamburger-menu-icon a");
      const menu = document.querySelector<HTMLElement>("#acordeon-main");
      if (toggle && menu) {
        menu.hidden = !menu.hidden;
        menu.querySelectorAll("mat-expansion-panel").forEach((p) => p.classList.toggle("mat-expanded", !menu.hidden));
        if (menu.hidden) menu.querySelector("mat-sidenav.mat-drawer-opened")?.remove();
        return;
      }
      if (menu && !menu.hidden && !t.closest("#acordeon-main")) {
        menu.hidden = true;
        menu.querySelector("mat-sidenav.mat-drawer-opened")?.remove();
      }
      const header = t.closest("mat-expansion-panel-header");
      if (header && !header.closest("#acordeon-main")) {
        header.closest("mat-expansion-panel")?.classList.toggle("mat-expanded");
        return;
      }
      const box = t.closest("app-filter-element mat-checkbox");
      if (box) {
        e.preventDefault();
        const name = (box.closest("mat-expansion-panel")?.querySelector("mat-panel-title")?.textContent ?? "").trim();
        const label = (box.querySelector(".mat-checkbox-label")?.textContent ?? "").trim();
        const value = facets.find((f) => f.name === name)?.values.find((v) => v.name === label);
        if (value) setListing({ q: value.query.query.value, page: "0" });
        return;
      }
      const trigger = t.closest("a.mat-menu-trigger");
      if (trigger && /relevancia|precio/i.test(trigger.textContent ?? "")) {
        const pane = document.createElement("div");
        pane.innerHTML = `<div class="mat-menu-panel" role="menu"><div class="mat-menu-content">${["Menor precio", "Mayor precio", "Relevancia"]
          .map((x) => `<button class="mat-menu-item" role="menuitem"><span>${x}</span></button>`)
          .join("")}</div></div>`;
        overlay().replaceChildren(pane);
        return;
      }
      const item = t.closest(".mat-menu-panel [role=menuitem]");
      if (item) {
        const words = item.textContent ?? "";
        closeOverlay();
        setListing({ sort: /menor/i.test(words) ? "price-asc" : /mayor/i.test(words) ? "price-desc" : "", page: "0" });
        return;
      }
      const pageLink = t.closest("app-custom-paginator-controls .item a, app-custom-paginator-controls .pagination-next a");
      if (pageLink) {
        const now = Number(new URLSearchParams(location.search).get("page")) || 0;
        const n = pageLink.closest(".pagination-next") ? now + 1 : Number(pageLink.textContent?.trim()) - 1;
        setListing({ page: String(n) });
        return;
      }
      const storePage = t.closest("app-store-list pagination-controls li a");
      if (storePage) {
        const n = Number(storePage.textContent?.match(/\d+/)?.[0] ?? 1);
        const list = document.querySelector("app-store-list .listStoreFinder");
        storeCards ??= [...document.querySelectorAll("app-store-list mat-card")].map((c) => c.cloneNode(true) as Element);
        const cards = n === 1
          ? storeCards.map((c) => c.cloneNode(true) as Element)
          : data.stores.slice((n - 2) * 10, (n - 2) * 10 + 10).map((s) => {
              const c = storeCards![0]!.cloneNode(true) as Element;
              c.querySelectorAll(".fs20 b")[1]!.textContent = s[0]!;
              const addr = [...c.querySelectorAll("span.field-mobile")].find((x) => /direcci/i.test(x.textContent ?? ""))?.nextElementSibling;
              if (addr) addr.textContent = ` ${s[1]} `;
              return c;
            });
        list?.replaceChildren(...cards);
        // The pager drawn again: the current page a number, the others links.
        for (const ul of document.querySelectorAll("app-store-list pagination-controls ul")) {
          const items = [1, 2, 3].map((k) => (k === n ? `<li class="current"><span>${k}</span></li>` : `<li><a tabindex="0"><span class="show-for-sr">page </span><span>${k}</span></a></li>`));
          ul.innerHTML = items.join("");
        }
        return;
      }
      const add = t.closest("app-product-info #addToCart, app-product-info #addToCart2");
      if (add) {
        const sku = location.pathname.split("/").pop()!;
        void xhr("POST", `${API}/cart/add`, `productCodePost=${sku}&stweb=633&ststore=633&quantity=1&haveService=false`).then(async () => {
          await xhr("GET", `${API}/minicart/cart/rollover`);
          const holder = add.parentElement!;
          holder.innerHTML = stepperHtml(sku, 1);
          (holder.querySelector("input") as HTMLInputElement).value = "1";
        });
        return;
      }
      const step = t.closest("app-input-update-quantity button");
      if (step) {
        const q = step.closest("app-input-update-quantity")!;
        const input = q.querySelector("input") as HTMLInputElement;
        const plus = step.querySelector("mat-icon")?.textContent === "add";
        const next = Math.max(1, (Number(input.value) || 1) + (plus ? 1 : -1));
        const row = step.closest("app-cart-product");
        const entry = row ? [...document.querySelectorAll("app-cart-product")].indexOf(row) : 0;
        void xhr("POST", `${API}/cart/update`, `entryNumber=${entry}&quantity=${next}&haveService=false`).then(() => {
          input.value = String(next);
          totals();
        });
        return;
      }
      const remove = t.closest("app-cart-product a");
      if (remove && /eliminar/i.test(remove.textContent ?? "")) {
        const row = remove.closest("app-cart-product")!;
        const entry = [...document.querySelectorAll("app-cart-product")].indexOf(row);
        void xhr("GET", `${API}/cart/delete?entryNumber=${entry}&serviceData=false`).then(() => syncCart());
        return;
      }
      const cotizar = t.closest("app-cart button");
      if (cotizar && /cotizar/i.test(cotizar.textContent ?? "")) {
        navigate("/cotizacion");
        return;
      }
      if (t.closest("app-form-user-quote button.btn-round-orange-fill")) {
        (w.__pressedCrear as number)++;
        return;
      }
      const select = t.closest<HTMLElement>("app-form-user-quote mat-select");
      if (select) {
        openSelect(select);
        return;
      }
      const suggestion = t.closest("#suggestContainer .mat-option");
      if (suggestion) {
        const href = suggestion.getAttribute("data-href");
        document.querySelector("#suggestContainer")?.remove();
        if (href) navigate(href);
        return;
      }
      const zoom = t.closest<HTMLElement>("app-product-zoom img");
      if (zoom) {
        zoom.style.transform = zoom.style.transform ? "" : "translate(-270px, -270px)";
        return;
      }
      // The router's links.
      const a = t.closest<HTMLAnchorElement>("a[href]");
      if (a && !e.defaultPrevented && !a.target && a.host === location.host && !a.getAttribute("href")!.startsWith("#")) {
        e.preventDefault();
        navigate(a.pathname + a.search);
      }
    },
    false,
  );

  document.addEventListener("mouseover", (e) => {
    const t = e.target as Element;
    const item = t.closest("#acordeon-main a.mat-item-menu-a");
    if (item) flyout((item.querySelector(".item-menu-headline")?.textContent ?? "").trim());
    const photo = t.closest("app-product-image .contenido");
    if (photo && !photo.querySelector("app-product-zoom")) {
      const slide = photo.querySelector(".swiper-slide") ?? photo;
      slide.insertAdjacentHTML("afterbegin", `<app-product-zoom><img class="imagen-zoom-tamaño cursor-zoom" style="" alt="zoom"></app-product-zoom>`);
    }
  });

  // The search box: suggestions after three letters, Enter for the results.
  document.addEventListener("input", (e) => {
    const input = e.target as HTMLInputElement;
    if (input.matches?.("#smartSearchId")) {
      const term = input.value.trim();
      if (term.length < 3) return;
      void xhr<{ data: { suggestions: { term: string }[]; products: { code: string; name: string; price?: { value?: number } }[] } }>("GET", `${API}/search/autocomplete/SearchBox?term=${encodeURIComponent(term)}`).then((r) => {
        if (!r?.data || input.value.trim() !== term) return;
        document.querySelector("#suggestContainer")?.remove();
        const box = document.createElement("div");
        box.id = "suggestContainer";
        box.className = "ac-container bg-white";
        box.innerHTML = `<div><span class="fs14 text-muted">Sugerencias:</span></div>${r.data.suggestions.map((s) => `<div class="mat-option-top-search"><p class="fs14 fw-bold">${s.term}</p></div>`).join("")}${r.data.products
          .map((p) => `<div><div class="mat-option" data-href="/producto/${slug(p.name)}/${p.code}"><div><img class="thumbnail"></div><div><p class="fs14">${p.name}</p></div></div></div>`)
          .join("")}`;
        input.closest("form")?.appendChild(box);
      });
    }
    if ((e.target as Element).closest?.("app-form-user-quote")) validate();
  });
  document.addEventListener("keydown", (e) => {
    const input = e.target as HTMLInputElement;
    if (e.key === "Enter" && input.matches?.("#smartSearchId") && input.value.trim()) {
      document.querySelector("#suggestContainer")?.remove();
      navigate(`/busqueda/${encodeURIComponent(input.value.trim().toLowerCase())}`);
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    if (opts.splash && kind() === "page" && location.pathname === "/") {
      overlay().innerHTML = `<div class="cdk-overlay-backdrop"></div><div class="cdk-overlay-pane video-dialog"><mat-dialog-container><app-generic-dialog><span class="close">×</span></app-generic-dialog></mat-dialog-container></div>`;
      document.documentElement.classList.add("cdk-global-scrollblock");
    }
    validate();
    void afterRoute();
  });
}

const ADAPTER = join(here, ".build", "adapter.js");

export async function serveSite(p: Page, opts: { cart?: Line[]; splash?: boolean } = {}): Promise<Seen> {
  const seen: Seen = { api: [], pages: [] };
  const cart: Line[] = (opts.cart ?? []).map((l) => ({ ...l }));
  const adapter = readFileSync(ADAPTER, "utf8");
  await p.addInitScript(`(${simulateSite.toString()})(${JSON.stringify(fixtureData())}, ${JSON.stringify({ splash: Boolean(opts.splash) })});`);
  await p.addInitScript({ content: `document.addEventListener("DOMContentLoaded", () => { ${adapter}\n }, { once: true });` });
  await p.context().route("**/*", (route) => route.abort());
  await p.route(`${API_HOST}/**`, (route) => answerApi(route, seen, cart));
  await p.route(`${ORIGIN}/**`, async (route, request) => {
    const url = new URL(request.url());
    if (url.pathname === "/__fixture") {
      const body = pageFor(url.searchParams.get("path") ?? "/");
      return route.fulfill({ status: body ? 200 : 404, contentType: "text/html; charset=utf-8", body: body ?? "" });
    }
    const body = request.resourceType() === "document" ? pageFor(url.pathname) : null;
    if (!body) return route.fulfill({ status: 404, body: "" });
    seen.pages.push(url.pathname + url.search);
    return route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body });
  });
  return seen;
}

/** Load `path` and wait for the adapter to be up. */
export async function open(p: Page, path: string): Promise<void> {
  await p.goto(`${ORIGIN}${path}`, { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => Boolean(window.voqalizeAgroplanet));
}

export interface Emitted {
  event: string;
  payload: Record<string, unknown>;
  /** A state event's author: "visitor", or "agent" for one of his moves. */
  by?: unknown;
  call_ref?: unknown;
}

/** A Stage state event as a test reads it: its name (`listing.filtered`) and
 *  the data its slice took; every other event as sent. */
function flat(e: Emitted): Emitted {
  if (e.event !== "stage_event") return e;
  const p = e.payload;
  return { event: String(p.name), payload: (p.data ?? {}) as Record<string, unknown>, by: p.by, call_ref: p.call_ref };
}

/** Whether `e` is `name`, or, for a name ending in ".", any state event of
 *  that slice (`"listing."`: shown, filtered or sorted). */
export const matches = (e: Emitted, name: string) => e.event === name || (name.endsWith(".") && e.event.startsWith(name));

/** Start the adapter's reports on this page, as the call does on bot-ready. */
export async function listen(p: Page): Promise<void> {
  await p.waitForFunction(() => Boolean(window.voqalizeAgroplanet));
  await p.evaluate(() => {
    const w = window as unknown as { __events: unknown[] };
    w.__events = [];
    window.voqalizeAgroplanet!.start((event, payload) => w.__events.push({ event, payload }));
  });
}

export const events = async (p: Page) =>
  (await p.evaluate(() => (window as unknown as { __events?: Emitted[] }).__events ?? [])).map(flat);

/** Wait for an event (the first of that name passing `test`) and return it. */
export async function waitForEvent(p: Page, name: string, test: (e: Emitted) => boolean = () => true, timeout = 15_000): Promise<Emitted> {
  const until = Date.now() + timeout;
  for (;;) {
    const hit = (await events(p)).find((e) => matches(e, name) && test(e));
    if (hit) return hit;
    if (Date.now() > until) throw new Error(`no ${name} event; got ${JSON.stringify((await events(p)).map((e) => e.event))}`);
    await p.waitForTimeout(100);
  }
}

export const run = (p: Page, command: string, payload: unknown) =>
  p.evaluate(([c, a]) => window.voqalizeAgroplanet!.run(c as string, a), [command, payload] as const);
