/**
 * cannonhome.cl, offline: trimmed copies of its pages (test/pages/) served at
 * their real addresses, the endpoints the adapter reads (`POST /graphql`, the
 * cart section, Amasty's autocomplete) answered with fixed bodies, and the
 * few behaviours of the site's own scripts the adapter relies on, simulated
 * (the quick filters' AJAX grid swap and pushState, the sorter, the search
 * box's dropdown, the quantity buttons, the AJAX add-to-cart and the bag
 * drawer). Everything else on the network is refused.
 *
 * With `goPersonal`, the search box behaves as on the live site: GoPersonal's
 * own dropdown (#gp-ac-dropdown) opens as the visitor types, shows the
 * products for what has been typed so far, empties while it fetches the whole
 * query and then shows them (test/pages/gp-autocomplete.html), while its
 * stylesheet hides Amasty's dropdown, which Amasty still fills.
 *
 * The bag's "Terminar pedido" opens the login window the live site renders
 * (test/pages/login-modal.html), whose "Comprar como invitado" links to the
 * guest checkout, /checkout (test/pages/checkout.html). Both were saved from
 * the live guest checkout on 2026-10-23 with one cheap item in the bag and
 * nothing typed, then trimmed: no scripts, styles, drawings, Knockout bindings
 * or form key. On the checkout, the delivery form's región and comuna
 * dropdowns (the comuna's list loads by AJAX once a región is chosen), the
 * phone prefix and the form's validation messages are simulated, as is the
 * password a known email brings up (`existe@example.com`).
 *
 * The adapter bundle (test/.build/adapter.js, `node test/build-adapter.mjs`)
 * is injected into every page at DOMContentLoaded, as `content.js` would be.
 */

import type { Page, Request, Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
export const ORIGIN = "https://cannonhome.cl";
const page = (name: string) => readFileSync(join(here, "pages", name), "utf8");

export const PRODUCT = "/sabanas-2-plazas-300-hilos-liso-fog.html";
export const CATEGORY = "/12-ropa-de-cama/20-sabanas";

/** What each address serves. Products not saved are served the saved one. */
function pageFor(path: string): string | null {
  if (path === "/" || path === "") return "home.html";
  if (path.startsWith(CATEGORY)) return "category.html";
  if (path.startsWith("/catalogsearch/result")) return "search.html";
  if (path.replace(/\/+$/, "") === "/checkout/cart") return "cart.html";
  if (path.replace(/\/+$/, "") === "/checkout") return "checkout.html";
  if (/^\/[a-z0-9-]+\.html$/.test(path)) return "product.html";
  return null;
}

/** The bag as Magento's customer-data section answers after the add. */
export const CART_SECTION = {
  cart: {
    summary_count: 2,
    subtotalAmount: "111986.0000",
    items: [
      {
        item_id: "1",
        product_name: "Sábanas 2 Plazas 300 Hilos Liso Fog",
        product_sku: "JSRSBH003P20Z",
        product_url: `${ORIGIN}${PRODUCT}`,
        qty: 2,
        product_price_value: 55993,
        product_regular_price_value: 79990,
      },
    ],
    freeShippingBar: { show: true, qualified: false, goal: 150000, current: 111986, remaining: 38014 },
  },
};

const gqlProduct = (sku: string, name: string, key: string, final: number, regular: number, stock = "IN_STOCK") => ({
  __typename: "SimpleProduct",
  sku,
  name,
  url_key: key,
  stock_status: stock,
  price_range: { minimum_price: { regular_price: { value: regular }, final_price: { value: final } } },
});

/** The catalogue behind `/graphql`: `products` lists what is in stock;
 *  `route` also answers the out-of-stock one; the rest does not exist. */
const CATALOGUE: Record<string, ReturnType<typeof gqlProduct>> = {
  "sabanas-2-plazas-300-hilos-liso-fog": gqlProduct("JSRSBH003P20Z", "Sábanas 2 Plazas 300 Hilos Liso Fog", "sabanas-2-plazas-300-hilos-liso-fog", 49990, 79990),
  "sabanas-2-plazas-300-hilos-liso-sand": gqlProduct("JSRSBH003P20S", "Sábanas 2 Plazas 300 Hilos Liso Sand", "sabanas-2-plazas-300-hilos-liso-sand", 55993, 79990),
  "funda-plumon-king-stone-washed-taupe": gqlProduct("FPKSWT", "Funda Plumón King Stone Washed Taupe", "funda-plumon-king-stone-washed-taupe", 39990, 39990, "OUT_OF_STOCK"),
};

export interface Seen {
  graphql: { method: string; query: string; variables: Record<string, unknown> }[];
  autocomplete: string[];
  goPersonal: string[];
  sections: number;
  pages: string[];
  /** The comuna lists asked for, by región id. */
  comunas: string[];
  /** Every request but a GET the pages sent (graphql aside): nothing is ever
   *  submitted from the checkout. */
  sent: string[];
}

/** The site's regions with the ids its comuna lists are asked by, and the
 *  comunas of two of them (2026-10-23). */
const REGIONS: [string, number][] = [
  ["Antofagasta", 652], ["Araucanía", 660], ["Arica y Parinacota", 650], ["Atacama", 653],
  ["Aysén del General Carlos Ibañez del Campo", 663], ["Bío Bío", 659], ["Coquimbo", 654],
  ["Libertador General Bernardo OHiggins", 656], ["Los Lagos", 662], ["Los Ríos", 661],
  ["Magallanes y la Antártica Chilena", 665], ["Maule", 657], ["Metropolitana", 664], ["Ñuble", 658],
  ["Tarapacá", 651], ["Valparaíso", 655],
];
const COMUNAS: Record<string, string[]> = {
  "664": ["Buin", "Cerrillos", "La Florida", "Las Condes", "Maipú", "Ñuñoa", "Providencia", "Puente Alto", "Santiago", "Vitacura"],
  "655": ["Quilpué", "Valparaíso", "Viña del Mar"],
};

async function answerGraphql(route: Route, request: Request, seen: Seen): Promise<void> {
  const body = (request.postDataJSON() ?? {}) as { query?: string; variables?: Record<string, unknown> };
  seen.graphql.push({ method: request.method(), query: body.query ?? "", variables: body.variables ?? {} });
  if (request.method() !== "POST") return route.fulfill({ status: 403, body: "GET is refused at the edge" });
  const data: Record<string, unknown> = {};
  const query = body.query ?? "";
  if (/products\s*\(/.test(query)) {
    const keys = (body.variables?.keys as string[] | undefined) ?? [];
    data.products = { items: keys.map((k) => CATALOGUE[k]).filter((p) => p && p.stock_status === "IN_STOCK") };
  }
  for (const [name, value] of Object.entries(body.variables ?? {})) {
    if (!/^u\d+$/.test(name)) continue;
    const key = String(value).replace(/\.html$/, "");
    data[`r${name.slice(1)}`] = CATALOGUE[key] ?? null;
  }
  return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data }) });
}

/** The site's own scripts, as far as the adapter leans on them. */
function simulateSite(): void {
  const ready = () => {
    const $ = <T extends Element>(sel: string) => document.querySelector<T>(sel);
    const amount = $(".toolbar-amount");
    const setCount = (n: number) => {
      const numbers = amount?.querySelectorAll(".toolbar-number");
      if (numbers?.length) numbers[numbers.length - 1].textContent = String(n);
    };
    const swap = (keep: (li: Element) => boolean, url: string) => {
      setTimeout(() => {
        const cards = [...document.querySelectorAll("ol.products li.product-item")];
        const kept = cards.filter(keep);
        cards.forEach((li) => !kept.includes(li) && li.remove());
        setCount(kept.length * 30);
        history.pushState({}, "", url);
      }, 350);
    };
    document.addEventListener("click", (e) => {
      const t = e.target as Element;
      const pill = t.closest(".qf__pill");
      if (pill) {
        const open = Boolean(pill.closest(".qf__group")?.classList.toggle("-open"));
        pill.setAttribute("aria-expanded", String(open));
        return;
      }
      if (t.closest(".qf__panel-close")) {
        t.closest(".qf__group")?.classList.remove("-open");
        t.closest(".qf__group")?.querySelector(".qf__pill")?.setAttribute("aria-expanded", "false");
        return;
      }
      const option = t.closest<HTMLAnchorElement>("a.qf__option-link");
      if (option) {
        e.preventDefault();
        const title = option.getAttribute("title") ?? "";
        option.classList.add("-active");
        const group = option.closest(".qf__group");
        group?.querySelector(".qf__pill")?.classList.add("-active");
        const label = group?.querySelector(".qf__pill-label");
        if (label) label.textContent = `${group?.querySelector(".qf__panel-title")?.textContent}: ${title}`;
        const word = title.toLowerCase().replace(/ hilos$/, "");
        swap((li) => (li.querySelector(".product-item-link")?.textContent ?? "").toLowerCase().includes(word), option.href);
        return;
      }
      if (t.closest(".minicart-wrapper a.action.showcart")) {
        e.preventDefault();
        $("aside.content-minicart-modal")?.classList.add("_show");
        return;
      }
      if (t.closest(".mc-header__close")) {
        $("aside.content-minicart-modal")?.classList.remove("_show");
        return;
      }
      const step = t.closest("#addQty, #minusQty");
      const qty = $<HTMLInputElement>("#qty");
      if (step && qty) {
        qty.value = String(Math.max(1, Number(qty.value) + (step.id === "addQty" ? 1 : -1)));
        const minus = $<HTMLButtonElement>("#minusQty");
        if (minus) minus.disabled = Number(qty.value) <= 1;
      }
    });
    $<HTMLSelectElement>("select#sorter")?.addEventListener("change", (e) => {
      const value = (e.target as HTMLSelectElement).value;
      // A test can slow the grid down (`__sortDelay`), as a slow network does.
      const delay = (window as unknown as { __sortDelay?: number }).__sortDelay ?? 350;
      setTimeout(() => {
        const list = $("ol.products");
        if (list) [...list.children].reverse().forEach((li) => list.appendChild(li));
        const url = new URL(location.href);
        url.searchParams.set("product_list_order", value);
        history.pushState({}, "", url.pathname + url.search);
      }, delay);
    });
    // Amasty's box: after three characters and a pause, its dropdown.
    let timer: ReturnType<typeof setTimeout> | null = null;
    document.addEventListener("input", (e) => {
      const input = (e.target as Element).closest<HTMLInputElement>("input.amsearch-input");
      if (!input) return;
      if (timer) clearTimeout(timer);
      timer = setTimeout(async () => {
        if (input.value.length < 3) return;
        const res = await fetch(`/amasty_xsearch/autocomplete/index/?q=${encodeURIComponent(input.value)}`, {
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        const section = $<HTMLElement>(".amsearch-result-section");
        if (!section) return;
        section.innerHTML = await res.text();
        section.style.display = "block";
      }, 500);
    });
    // The bag's login window: rendered (hidden) as Knockout renders it, shown
    // by "Terminar pedido", closed by its ×.
    if (document.body.classList.contains("checkout-cart-index")) {
      void fetch("/__fixture/login-modal.html")
        .then((r) => r.text())
        .then((html) => document.body.insertAdjacentHTML("beforeend", html));
      document.addEventListener("click", (e) => {
        const t = e.target as Element;
        if (t.closest("[data-role=proceed-to-checkout]")) $("aside.login-modal")?.classList.add("_show");
        if (t.closest("aside.login-modal .action-close")) $("aside.login-modal")?.classList.remove("_show");
      });
    }
    if (document.body.classList.contains("checkout-index-index")) simulateCheckout();
    // The AJAX add-to-cart: no page load; the bag slides in.
    $<HTMLFormElement>("#product_addtocart_form")?.addEventListener("submit", (e) => {
      e.preventDefault();
      const qty = Number($<HTMLInputElement>("#qty")?.value) || 1;
      setTimeout(() => {
        const counter = $(".minicart-wrapper .counter-number");
        if (counter) counter.textContent = String(qty);
        $("aside.content-minicart-modal")?.classList.add("_show");
      }, 400);
    });
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ready, { once: true });
  else ready();
}

/** The checkout's own scripts, as far as the adapter meets them. Declared
 *  inside `simulateSite`'s page so it serializes with it. */
function simulateCheckout(): void {
  const w = window as unknown as { __submitted: string[]; __regions: [string, number][]; __comunaDelay?: number };
  w.__submitted = [];
  const $ = <T extends Element>(sel: string, root: ParentNode = document) => root.querySelector<T>(sel);
  const form = $<HTMLFormElement>("#co-shipping-form")!;
  const regionBox = $<HTMLElement>(".field.region_id .cn-region-search", form)!;
  const comunaBox = $<HTMLElement>(".field.city_id .cn-region-search", form)!;
  let comunas: string[] = [];
  const menu = (box: HTMLElement, labels: string[]) => {
    box.querySelector(".cn-region-search__menu")?.remove();
    const items = labels.map((l, i) => `<li class="cn-region-search__item" role="option" id="o-${i}"><span class="cn-region-search__item-label">${l}</span></li>`).join("");
    box.insertAdjacentHTML(
      "beforeend",
      `<div class="cn-region-search__menu"><div class="cn-region-search__search"><input class="cn-region-search__input" type="text" placeholder="Buscar"></div><ul class="cn-region-search__list" role="listbox">${items}</ul></div>`,
    );
  };
  const setValue = (box: HTMLElement, label: string, placeholder: boolean) => {
    const v = box.querySelector(".cn-region-search__value")!;
    v.textContent = label;
    v.classList.toggle("is-placeholder", placeholder);
  };
  const error = (field: Element | null, message: string | null) => {
    field?.querySelector(".field-error")?.remove();
    if (field && message) field.insertAdjacentHTML("beforeend", `<div class="field-error"><span>${message}</span></div>`);
  };
  document.addEventListener("click", (e) => {
    const t = e.target as Element;
    const trigger = t.closest<HTMLButtonElement>(".cn-region-search__trigger");
    if (trigger) {
      const box = trigger.closest<HTMLElement>(".cn-region-search")!;
      if (trigger.getAttribute("aria-disabled") === "true") return;
      const open = box.classList.toggle("is-open");
      trigger.setAttribute("aria-expanded", String(open));
      if (open) menu(box, box === regionBox ? w.__regions.map(([l]) => l) : comunas);
      return;
    }
    const item = t.closest<HTMLElement>(".cn-region-search__item");
    if (item) {
      const box = item.closest<HTMLElement>(".cn-region-search")!;
      const label = item.textContent!.trim();
      setValue(box, label, false);
      box.classList.remove("is-open");
      error(box.closest(".field"), null);
      if (box === regionBox) {
        $<HTMLInputElement>("input[name=region]", form)!.value = label;
        const id = w.__regions.find(([l]) => l === label)![1];
        const comunaTrigger = comunaBox.querySelector(".cn-region-search__trigger")!;
        comunaTrigger.setAttribute("aria-disabled", "true");
        setValue(comunaBox, "Cargando…", true);
        comunas = [];
        setTimeout(async () => {
          comunas = (await (await fetch(`/rest/V1/zonification/city/getByCodeForCheckout/${id}`)).json()) as string[];
          comunaTrigger.setAttribute("aria-disabled", "false");
          setValue(comunaBox, "Por favor, selecciona una comuna", true);
        }, w.__comunaDelay ?? 600);
      } else {
        $<HTMLInputElement>("input[name=city]", form)!.value = label;
        const splits = $<HTMLElement>(".section-splits", form);
        if (splits) splits.style.display = "block";
      }
      return;
    }
    const flag = t.closest(".selected-flag");
    if (flag) {
      $(".country-list", form)?.classList.toggle("hide");
      return;
    }
    const country = t.closest<HTMLElement>("li.country");
    if (country) {
      $(".iti-flag", form)!.textContent = `+${country.dataset.dialCode}`;
      $(".country-list", form)?.classList.add("hide");
      return;
    }
    if (t.closest(".co-place-order__button, [data-role=opc-continue], #payment button")) w.__submitted.push(t.closest("button")?.className ?? "button");
  });
  document.addEventListener("submit", (e) => {
    e.preventDefault();
    w.__submitted.push((e.target as HTMLFormElement).id || "form");
  });
  // Knockout's validation, as the visitor finishes an edit.
  document.addEventListener("change", (e) => {
    const el = e.target as HTMLInputElement;
    if (el.id === "customer-email") {
      document.getElementById("customer-email-error")?.remove();
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(el.value)) {
        el.insertAdjacentHTML("afterend", `<div class="mage-error" id="customer-email-error">Ingrese una dirección de correo electrónico válida (Ej: johndoe@domain.com).</div>`);
      }
      const password = $<HTMLElement>("#customer-email-fieldset .field.password");
      if (password) password.style.display = el.value === "existe@example.com" ? "block" : "none";
      return;
    }
    const field = el.closest(".field");
    if (!field || !form.contains(el)) return;
    if (el.name === "telephone") error(field, /^\d{8}$/.test(el.value) ? null : "Ingresa un número de teléfono válido.");
    else if (field.classList.contains("_required")) error(field, el.value.trim() ? null : "Este es un campo obligatorio.");
  });
}

/** The products GoPersonal shows while only "sab…" has been typed: a bath
 *  sheet, as "sabanas" ranks first on the live site. */
const GP_PARTIAL = `<a class="gp-ac-product-card" href="https://cannonhome.cl/sabana-de-bano-aqua.html?gsIndex=0"><div class="gp-ac-product-img-wrap"></div><div><div class="gp-ac-product-brand"></div><div class="gp-ac-product-name">Sábana de Baño Aqua</div><div class="gp-ac-product-prices"><span class="gp-ac-price-only">$9.990</span></div></div></a>`;

export interface GoPersonalTiming {
  /** From the last key to the dropdown emptying for the whole query. */
  debounceMs: number;
  /** How long it stays empty while the query is fetched. */
  loadingMs: number;
}

/** GoPersonal's search box, as far as the adapter meets it. */
function simulateGoPersonal(o: GoPersonalTiming & { partial: string }): void {
  const ready = () => {
    const style = document.createElement("style");
    style.textContent = `
      .amsearch-result-section { display: none !important; }
      #gp-ac-dropdown { display: none; }
      #gp-ac-dropdown.open { display: flex; flex-direction: column; position: absolute; top: 120px; left: 150px; width: 720px; min-height: 240px; background: #fff; z-index: 10000; }
      #gp-ac-prods { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }`;
    document.head.appendChild(style);
    const dd = document.getElementById("gp-ac-dropdown");
    const prods = dd?.querySelector<HTMLElement>("#gp-ac-prods");
    const cats = dd?.querySelector<HTMLElement>("#gp-ac-cats-row");
    if (!dd || !prods || !cats) return;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let asked = 0;
    document.addEventListener("input", (e) => {
      const input = (e.target as Element).closest<HTMLInputElement>("input.amsearch-input");
      if (!input) return;
      if (timer) clearTimeout(timer);
      const q = input.value;
      if (q.length < 3) return;
      dd.classList.add("open");
      if (!prods.children.length) prods.innerHTML = o.partial;
      const mine = ++asked;
      timer = setTimeout(async () => {
        prods.innerHTML = "";
        cats.innerHTML = "";
        await new Promise((r) => setTimeout(r, o.loadingMs));
        const html = await (await fetch(`/__gp/search?q=${encodeURIComponent(q)}`)).text();
        if (mine !== asked) return;
        const doc = new DOMParser().parseFromString(html, "text/html");
        cats.innerHTML = doc.querySelector("template[data-part=cats]")?.innerHTML ?? "";
        prods.innerHTML = doc.querySelector("template[data-part=prods]")?.innerHTML ?? "";
      }, o.debounceMs);
    });
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ready, { once: true });
  else ready();
}

const ADAPTER = join(here, ".build", "adapter.js");

/** Serve the site on `page`, with the adapter injected; what it was asked. */
export async function serveSite(p: Page, opts: { goPersonal?: GoPersonalTiming } = {}): Promise<Seen> {
  const seen: Seen = { graphql: [], autocomplete: [], goPersonal: [], sections: 0, pages: [], comunas: [], sent: [] };
  const adapter = readFileSync(ADAPTER, "utf8");
  // The dropdown starts closed, as the site renders it before typing.
  await p.addInitScript(() => {
    document.addEventListener("DOMContentLoaded", () => {
      const section = document.querySelector<HTMLElement>(".amsearch-result-section");
      if (section) {
        section.innerHTML = "";
        section.style.display = "none";
      }
    });
  });
  await p.addInitScript(`window.__regions = ${JSON.stringify(REGIONS)};`);
  await p.addInitScript(`${simulateCheckout.toString()}\n(${simulateSite.toString()})();`);
  if (opts.goPersonal) await p.addInitScript(simulateGoPersonal, { ...opts.goPersonal, partial: GP_PARTIAL });
  await p.addInitScript({
    content: `document.addEventListener("DOMContentLoaded", () => { ${adapter}\n }, { once: true });`,
  });
  await p.context().route("**/*", (route) => route.abort());
  await p.route(`${ORIGIN}/**`, async (route, request) => {
    const url = new URL(request.url());
    if (url.pathname === "/graphql") return answerGraphql(route, request, seen);
    if (request.method() !== "GET") seen.sent.push(`${request.method()} ${url.pathname}`);
    if (url.pathname === "/__fixture/login-modal.html") return route.fulfill({ status: 200, contentType: "text/html", body: page("login-modal.html") });
    const comunaList = url.pathname.match(/^\/rest\/V1\/zonification\/city\/getByCodeForCheckout\/(\d+)$/);
    if (comunaList) {
      seen.comunas.push(comunaList[1]);
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(COMUNAS[comunaList[1]] ?? []) });
    }
    if (url.pathname.startsWith("/customer/section/load")) {
      seen.sections++;
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(CART_SECTION) });
    }
    if (url.pathname === "/__gp/search") {
      seen.goPersonal.push(url.searchParams.get("q") ?? "");
      return route.fulfill({ status: 200, contentType: "text/html", body: page("gp-autocomplete.html") });
    }
    if (url.pathname.startsWith("/amasty_xsearch/autocomplete")) {
      seen.autocomplete.push(url.searchParams.get("q") ?? "");
      return route.fulfill({ status: 200, contentType: "text/html", body: page("autocomplete.html") });
    }
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
  await p.waitForFunction(() => Boolean(window.voqalizeCannonhome));
}

export interface Emitted {
  event: string;
  payload: Record<string, unknown>;
}

/** Start the adapter's reports on this page, as the call does on bot-ready. */
export async function listen(p: Page): Promise<void> {
  await p.waitForFunction(() => Boolean(window.voqalizeCannonhome));
  await p.evaluate(() => {
    const w = window as unknown as { __events: unknown[] };
    w.__events = [];
    window.voqalizeCannonhome!.start((event, payload) => w.__events.push({ event, payload }));
  });
}

export const events = (p: Page) => p.evaluate(() => (window as unknown as { __events?: Emitted[] }).__events ?? []);

/** Wait for an event (the `n`th of that name) and return it. */
export async function waitForEvent(p: Page, name: string, test: (e: Emitted) => boolean = () => true, timeout = 15_000): Promise<Emitted> {
  const until = Date.now() + timeout;
  for (;;) {
    const hit = (await events(p)).find((e) => e.event === name && test(e));
    if (hit) return hit;
    if (Date.now() > until) throw new Error(`no ${name} event; got ${JSON.stringify((await events(p)).map((e) => e.event))}`);
    await p.waitForTimeout(100);
  }
}

export const run = (p: Page, command: string, payload: unknown) =>
  p.evaluate(([c, a]) => window.voqalizeCannonhome!.run(c as string, a), [command, payload] as const);
