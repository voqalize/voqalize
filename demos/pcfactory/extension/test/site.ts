/**
 * www.pcfactory.cl, offline: trimmed copies of its pages (test/pages/, made by
 * make-fixtures.mjs from pages saved live on 2026-10-29) served at their real
 * addresses, the store's API at api.pcfactory.cl answered with bodies saved
 * the same day (test/pages/api/), and the few behaviours of the site's own
 * scripts the adapter relies on, simulated:
 *
 *   - Bootstrap's collapses (the filter groups, the FAQs), tabs and the
 *     "Ordenar por" menu;
 *   - the listing's Vue widget: a ticked filter, a sort or a price range
 *     calls the API (by XMLHttpRequest, as the widget does), then redraws the
 *     grid and rewrites the address with `replaceState`;
 *   - the search button's `location.href` to the results;
 *   - "Agregar al carro" on a card or the product page (`localStorage
 *     .cartProducts`, the "Producto agregado" window, and on the product page
 *     the − / + the button turns into), and "Seguir comprando";
 *   - the cart page's − / +, "Eliminar" and its ¿Confirmas…? window, the
 *     coupon box ("Cupón inválido."), and "Continuar" to /checkout;
 *   - "Continuar como invitado" to /checkout/tipo-entrega;
 *   - the comparator (`comparator-items`, its panel, and its refusal of a
 *     product of another category);
 *   - /tiendas' "Ver tienda", which opens Google's map card.
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
export const ORIGIN = "https://www.pcfactory.cl";
const API_HOST = "https://api.pcfactory.cl";
const page = (name: string) => readFileSync(join(here, "pages", name), "utf8");
const api = (name: string) => readFileSync(join(here, "pages", "api", `${name}.json`), "utf8");

export const PRODUCT = "/producto/57233";
export const CABLE = "/producto/8941";
export const CATEGORY = "/categoria/computadores-y-tablets/notebooks/notebooks";
export const SEARCH = "/busqueda-avanzada?search=monitor+27";

/** What each address serves. Products not saved are served the saved one. */
function pageFor(path: string): string | null {
  const p = path.replace(/\/+$/, "") || "/";
  if (p === "/") return "home.html";
  if (p.startsWith("/categoria/")) return "category.html";
  if (p === "/busqueda-avanzada") return "search.html";
  if (/^\/producto\/\d+/.test(p)) return "product.html";
  if (p === "/carro") return "cart.html";
  if (p === "/tiendas") return "tiendas.html";
  if (p.startsWith("/centro-de-ayuda")) return "help.html";
  if (p === "/checkout") return "checkout.html";
  if (p === "/checkout/tipo-entrega") return "tipo-entrega.html";
  return null;
}

/** The two products the API knows, for `/carro/status`. */
const CATALOGUE: Record<number, { nombre: string; efectivo: number; normal: number }> = {
  8941: { nombre: "Cable USB 2.0 A/A 1.8m Extensión", efectivo: 1490, normal: 1590 },
  57233: { nombre: "Notebook Gamer LOQe Gen 10 AMD Ryzen 7-7735HS NVIDIA RTX 4050 15.6\" FHD 144Hz 16GB RAM 512GB Windows 11 Home Luna Grey  83S00001CL", efectivo: 1066990, normal: 1099990 },
};

export interface Seen {
  /** Every call to the store's API, as "METHOD /path?query". */
  api: string[];
  /** The pages loaded, path and query. */
  pages: string[];
}

const CORS = { "access-control-allow-origin": "*", "access-control-allow-headers": "content-type", "access-control-allow-methods": "GET, POST, PUT, OPTIONS" };

async function answerApi(route: Route, seen: Seen): Promise<void> {
  const request = route.request();
  const url = new URL(request.url());
  if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS });
  seen.api.push(`${request.method()} ${url.pathname}${url.search}`);
  const json = (body: string, status = 200) => route.fulfill({ status, headers: { ...CORS, "content-type": "application/json" }, body });
  const p = url.pathname;
  let m: RegExpMatchArray | null;
  if ((m = p.match(/\/catalogo\/productos\/(\d+)(\/precio|\/stock)?$/))) {
    const id = m[1];
    const kind = m[2] === "/precio" ? "precio" : m[2] === "/stock" ? "stock" : "product";
    if (id !== "57233" && id !== "8941") return json('{"error":"not found"}', 404);
    return json(api(`${kind}-${id}`));
  }
  if (p.endsWith("/catalogo/productos/facets")) return json(api("facets-notebook"));
  if (p.endsWith("/catalogo/productos")) return json(api("search-notebook"));
  if (p.endsWith("/catalogo/productos/query/facets")) return json(api("facets-425"));
  if (p.endsWith("/catalogo/productos/query")) return json(api("query-425"));
  if ((m = p.match(/\/category\/PCF\/family\/(\d+)$/))) return json(JSON.stringify([{ id: Number(m[1]), nombre: m[1] === "995" ? "Monitores" : "Notebooks" }]));
  if (p.endsWith("/carro/status")) {
    const body = JSON.parse(request.postData() ?? "{}") as { items?: { id: number; cantidad: number }[] };
    // A product the catalogue above does not hold is priced as the grid's first card.
    const known = (id: number) => CATALOGUE[id] ?? { nombre: `Producto ${id}`, efectivo: 729990, normal: 752590 };
    const items = (body.items ?? []).map((i) => ({ producto: { id: i.id, nombre: known(i.id).nombre, precio: { efectivo: known(i.id).efectivo, normal: known(i.id).normal } }, cantidad: i.cantidad }));
    const total = items.reduce((n, i) => n + i.cantidad * i.producto.precio.efectivo, 0);
    return json(JSON.stringify({ items, total: { efectivo: total } }));
  }
  return json("{}");
}

/**
 * The site's own scripts, as far as the adapter leans on them. Declared here
 * and serialized into each page, so everything it uses is inside it.
 */
function simulateSite(): void {
  const SIM_API = "https://api.pcfactory.cl/pcfactory-services-catalogo/v1/catalogo/productos/query?page=0&size=12&categorias=425";
  const xhr = () =>
    new Promise<void>((r) => {
      const x = new XMLHttpRequest();
      x.open("GET", SIM_API);
      x.onloadend = () => r();
      x.send();
    });
  const ls = (): { items: { id: number; cantidad: number; origin: string }[] } => JSON.parse(localStorage.getItem("cartProducts") ?? '{"items":[]}');
  const setLs = (v: unknown) => localStorage.setItem("cartProducts", JSON.stringify(v));
  const bump = (id: number, d: number) => {
    const c = ls();
    let it = c.items.find((i) => i.id === id);
    if (!it) c.items.push((it = { id, cantidad: 0, origin: "PCF" }));
    it.cantidad += d;
    c.items = c.items.filter((i) => i.cantidad > 0);
    setLs(c);
  };
  const show = (m: Element | null) => {
    if (!m) return;
    m.classList.add("show");
    (m as HTMLElement).style.display = "block";
  };
  const hide = (m: Element | null) => {
    if (!m) return;
    m.classList.remove("show");
    (m as HTMLElement).style.display = "";
  };
  const setParam = (k: string, v: string | null) => {
    const u = new URL(location.href);
    if (v == null) u.searchParams.delete(k);
    else u.searchParams.set(k, v);
    history.replaceState(null, "", u);
  };
  const grid = () => document.querySelector('section[data-section-name="Lista productos"]');
  const cardEls = () => [...(grid()?.children ?? [])];
  const countEl = () => [...document.querySelectorAll("p")].find((p) => /de\s+[\d.]+\s+resultados/.test(p.textContent ?? ""));
  const setCount = (n: number) => {
    const p = countEl();
    if (p) p.textContent = (p.textContent ?? "").replace(/de\s+[\d.]+\s+resultados/, `de ${n} resultados`);
  };
  /** The listing widget's answer to a change: the API called, then the grid
   *  redrawn a moment later. */
  const regrid = async (change: () => void) => {
    await xhr();
    await new Promise((r) => setTimeout(r, 120));
    change();
  };
  const productIdHere = () => Number(location.pathname.match(/\/producto\/(\d+)/)?.[1] ?? 0);

  document.addEventListener(
    "click",
    (e) => {
      const t = e.target as Element;
      const col = t.closest("[data-toggle=collapse], [data-bs-toggle=collapse]");
      if (col) {
        e.preventDefault();
        const sel = col.getAttribute("data-target") ?? col.getAttribute("data-bs-target");
        const c = sel ? document.querySelector(sel) : null;
        if (c) {
          c.classList.toggle("show");
          col.setAttribute("aria-expanded", String(c.classList.contains("show")));
        }
        return;
      }
      const tab = t.closest<HTMLAnchorElement>("[data-toggle=tab]");
      if (tab) {
        e.preventDefault();
        document.querySelectorAll("#tabs .nav-link").forEach((a) => a.classList.remove("active"));
        tab.classList.add("active");
        const pane = document.querySelector(tab.getAttribute("href") ?? "");
        pane?.parentElement?.querySelectorAll(":scope > .tab-pane").forEach((p) => p.classList.remove("active", "show"));
        pane?.classList.add("active", "show");
        return;
      }
      if (t.closest("#dropdown-order")) {
        e.preventDefault();
        t.closest(".dropdown")?.querySelector(".dropdown-menu")?.classList.toggle("show");
        return;
      }
      const item = t.closest(".pcf-select__dropdown .dropdown-item");
      if (item) {
        const dd = item.closest(".dropdown")!;
        dd.querySelector(".dropdown-menu")?.classList.remove("show");
        dd.querySelectorAll(".dropdown-item").forEach((i) => i.classList.remove("active"));
        item.classList.add("active");
        const words = (item.textContent ?? "").trim();
        void regrid(() => {
          const toggle = dd.querySelector("#dropdown-order")!;
          toggle.firstChild!.textContent = ` ${words} `;
          for (const c of cardEls().reverse()) grid()!.appendChild(c);
          setParam("sort", /menor/.test(words) ? "precio,asc" : /mayor/.test(words) ? "precio,desc" : null);
        });
        return;
      }
      if (t.closest("#search-btn-desktop")) {
        e.preventDefault();
        const q = (document.querySelector<HTMLInputElement>("#search-input-desktop")?.value ?? "").trim().toLowerCase().split(/\s+/).join("+");
        location.href = `/busqueda-avanzada?search=${q || "*"}`;
        return;
      }
      const cardButton = t.closest("button.products__item__info__add-to-cart");
      if (cardButton) {
        e.preventDefault();
        e.stopPropagation();
        const id = Number(cardButton.closest("a.products__item")?.querySelector(".products__item__info__id strong")?.textContent);
        setTimeout(() => {
          bump(id, 1);
          show(document.querySelector("#pcf-modal-added-product"));
        }, 150);
        return;
      }
      const pdpAdd = t.closest("#product-detail button.pcf-btn--five");
      if (pdpAdd && /agregar/i.test(pdpAdd.textContent ?? "")) {
        const id = productIdHere();
        setTimeout(() => {
          bump(id, 1);
          show(document.querySelector("#pcf-modal-added-product"));
          // The button becomes the page's − / +, as it does live.
          for (const b of document.querySelectorAll("#product-detail button.pcf-btn--five")) {
            if (/agregar/i.test(b.textContent ?? "")) b.outerHTML = '<div class="counter-input d-flex"><button class="btn-minus">−</button><input id="input-desk" type="number" value="1"><button class="btn-plus">+</button></div>';
          }
        }, 150);
        return;
      }
      if (t.closest("#product-detail .btn-plus")) {
        setTimeout(() => bump(productIdHere(), 1), 120);
        return;
      }
      if (t.closest("#pcf-modal-added-product [data-dismiss=modal]")) {
        hide(document.querySelector("#pcf-modal-added-product"));
        return;
      }
      const qty = t.closest(".card-list-product .pcf-value-button");
      if (qty) {
        const row = qty.closest<HTMLElement>(".card-list-product")!;
        const id = Number(row.getAttribute("data-gtag-id"));
        const input = row.querySelector<HTMLInputElement>("input.pcf-value-input")!;
        const v = Math.max(1, (Number(input.value) || 1) + (qty.classList.contains("positive") ? 1 : -1));
        setTimeout(() => {
          input.value = String(v);
          row.setAttribute("data-gtag-cant", String(v));
          const c = ls();
          const line = c.items.find((i) => i.id === id);
          if (line) line.cantidad = v;
          setLs(c);
        }, 120);
        return;
      }
      const del = t.closest(".card-list-product a[href='#delete-product-modal']");
      if (del) {
        e.preventDefault();
        (window as unknown as { __deleting: Element }).__deleting = del.closest(".card-list-product")!;
        show(document.querySelector("#delete-product-modal"));
        return;
      }
      const confirm = t.closest("#delete-product-modal button");
      if (confirm) {
        hide(document.querySelector("#delete-product-modal"));
        const row = (window as unknown as { __deleting?: Element }).__deleting;
        if (row && /eliminar/i.test(confirm.textContent ?? "")) {
          const id = Number(row.getAttribute("data-gtag-id"));
          row.remove();
          const c = ls();
          c.items = c.items.filter((i) => i.id !== id);
          setLs(c);
        }
        return;
      }
      const coupon = t.closest("button.cupon-btn");
      if (coupon) {
        void xhr().then(() => {
          const body = coupon.closest(".cupon-body")!;
          let msg = body.querySelector(".cupon-msg");
          if (!msg) {
            msg = document.createElement("p");
            msg.className = "cupon-msg";
            body.appendChild(msg);
          }
          msg.textContent = "Cupón inválido.";
        });
        return;
      }
      if (t.closest("a[aria-label='ir al checkout']")) {
        e.preventDefault();
        location.href = "/checkout";
        return;
      }
      const guest = t.closest(".identification__card > button");
      if (guest && /invitado/i.test(guest.textContent ?? "")) {
        location.href = "/checkout/tipo-entrega";
        return;
      }
      const store = t.closest("button.btn-store");
      if (store) {
        const card = store.closest(".card-tabs")!;
        document.querySelector(".gm-style-iw")?.remove();
        const iw = document.createElement("div");
        iw.className = "gm-style-iw gm-style-iw-c";
        iw.innerText = [
          card.querySelector("h3")?.textContent?.trim(),
          "Dirección",
          card.querySelector("p")?.textContent?.trim(),
          "Horarios",
          "Lunes a Viernes 10:00 a 20:00",
          "Sábado 10:00 a 14:00",
          "Jefe de tienda",
          "Nombre Apellido",
          "Ver en google maps",
        ].join("\n");
        (document.querySelector("#map, .map, #main-layout") ?? document.body).appendChild(iw);
        return;
      }
      const compare = t.closest("#product-title button.pcf-link-btn");
      if (compare) addCompared(productIdHere(), document.querySelector(".product-title__product-name")?.textContent?.trim() ?? "", "Notebooks", null);
    },
    true,
  );

  function addCompared(id: number, nombre: string, cat: string, box: HTMLInputElement | null): void {
    const panel = document.querySelector("#pcf-comparator-summary");
    const items = JSON.parse(localStorage.getItem("comparator-items") ?? "[]") as { id: number; nombre: string; cat: string }[];
    if (items.length && items[0]!.cat !== cat) {
      panel?.setAttribute("data-alert", "Sólo puedes comparar productos que pertenezcan a la misma categoría. Los productos seleccionados pertenecen a categorías diferentes.");
      if (box) box.checked = false;
      return;
    }
    panel?.setAttribute("data-alert", "");
    if (!items.some((i) => i.id === id)) items.push({ id, nombre, cat });
    localStorage.setItem("comparator-items", JSON.stringify(items));
    panel?.classList.remove("hide");
    panel?.classList.add("show");
  }

  document.addEventListener(
    "change",
    (e) => {
      const input = e.target as HTMLInputElement;
      if (input.type === "checkbox" && input.closest("#panel-filters")) {
        void regrid(() => {
          const cards = cardEls();
          if (cards.length > 1) cards[cards.length - 1]!.remove();
          setCount(cardEls().length + 10);
          const on = [...document.querySelectorAll<HTMLInputElement>("#panel-filters input:checked")].map((i) => i.id).join(",");
          setParam("f", on || null);
        });
      }
      if (input.id?.startsWith("product-checkbox")) {
        const card = input.closest("a.products__item");
        const name = card?.getAttribute("data-content-name") ?? "";
        const cat = card?.querySelector("img")?.getAttribute("data-gtag-category") ?? "";
        addCompared(Number(input.id.replace("product-checkbox", "")), name, cat, input);
      }
    },
    true,
  );

  // The coupon box's Aplicar is enabled once something is typed (Vue's v-model).
  document.addEventListener(
    "input",
    (e) => {
      const input = e.target as HTMLInputElement;
      if (!input.matches?.("input.cupon-input")) return;
      const button = input.closest(".cupon-input-group")?.querySelector<HTMLButtonElement>("button.cupon-btn");
      if (button) button.disabled = !input.value.trim();
    },
    true,
  );

  document.addEventListener(
    "mouseup",
    (e) => {
      const input = e.target as HTMLInputElement;
      if (input.type !== "range") return;
      const [lo, hi] = [...document.querySelectorAll<HTMLInputElement>("#panel-filters input[type=range]")];
      void regrid(() => {
        setParam("precioMin", lo!.value);
        setParam("precioMax", hi!.value);
        const cards = cardEls();
        if (cards.length > 1) cards[cards.length - 1]!.remove();
        setCount(cardEls().length + 5);
      });
    },
    true,
  );
}

const ADAPTER = join(here, ".build", "adapter.js");

export async function serveSite(p: Page, opts: { cart?: { id: number; cantidad: number }[] } = {}): Promise<Seen> {
  const seen: Seen = { api: [], pages: [] };
  const adapter = readFileSync(ADAPTER, "utf8");
  if (opts.cart) {
    const cart = JSON.stringify({ items: opts.cart.map((i) => ({ ...i, origin: "PCF" })) });
    await p.addInitScript(`if (!sessionStorage.getItem("__cartSet")) { localStorage.setItem("cartProducts", ${JSON.stringify(cart)}); sessionStorage.setItem("__cartSet", "1"); }`);
  }
  await p.addInitScript(`(${simulateSite.toString()})();`);
  await p.addInitScript({ content: `document.addEventListener("DOMContentLoaded", () => { ${adapter}\n }, { once: true });` });
  await p.context().route("**/*", (route) => route.abort());
  await p.route(`${API_HOST}/**`, (route) => answerApi(route, seen));
  await p.route(`${ORIGIN}/**`, async (route, request) => {
    const url = new URL(request.url());
    const file = request.resourceType() === "document" ? pageFor(url.pathname) : null;
    if (!file) return route.fulfill({ status: 404, body: "" });
    seen.pages.push(url.pathname + url.search);
    return route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: page(file) });
  });
  return seen;
}

/** Load `path` and wait for the adapter to be up. */
export async function open(p: Page, path: string): Promise<void> {
  await p.goto(`${ORIGIN}${path}`, { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => Boolean(window.voqalizePcfactory));
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
  await p.waitForFunction(() => Boolean(window.voqalizePcfactory));
  await p.evaluate(() => {
    const w = window as unknown as { __events: unknown[] };
    w.__events = [];
    window.voqalizePcfactory!.start((event, payload) => w.__events.push({ event, payload }));
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
  p.evaluate(([c, a]) => window.voqalizePcfactory!.run(c as string, a), [command, payload] as const);
