/**
 * The Agroplanet adapter, end to end against trimmed copies of the app's
 * routes and its API (see site.ts): each move the brain sends, the events the
 * page answers with, the moves that move the app to another route and finish
 * there without a load, the watchers picked again on every route, and the
 * guard that keeps the RUT, "Crear cotización" and the login the visitor's.
 */

import { expect, type Page, test } from "@playwright/test";

import { CATEGORY, type Emitted, events, HIDDEN, listen, matches, open, PRODUCT, run, SEARCH, serveSite, waitForEvent } from "./site";

const named = (list: Emitted[], name: string) => list.filter((e) => matches(e, name));

/** Record every click with whether a ring was up around it at that moment. */
async function watchClicks(p: Page): Promise<void> {
  await p.evaluate(() => {
    const w = window as unknown as { __clicks: { what: string; id: string; ringed: boolean }[] };
    w.__clicks = [];
    document.addEventListener(
      "click",
      (e) => {
        const el = e.target as Element;
        const r = el.getBoundingClientRect();
        const rings = [...(document.querySelector("[data-voqalize=spotlight]")?.shadowRoot?.querySelectorAll(".ring") ?? [])];
        const ringed = rings.some((ring) => {
          const b = ring.getBoundingClientRect();
          return b.left <= r.left + 4 && b.top <= r.top + 4 && b.right >= r.right - 4 && b.bottom >= r.bottom - 4;
        });
        w.__clicks.push({ what: (el.textContent ?? "").trim().slice(0, 40) || el.className.toString(), id: el.id, ringed });
      },
      true,
    );
  });
}
const clicks = (p: Page) => p.evaluate(() => (window as unknown as { __clicks: { what: string; id: string; ringed: boolean }[] }).__clicks);

/** A marker outside `<app-root>`, where the widget lives: it must outlive
 *  every route change. */
const plantMarker = (p: Page) => p.evaluate(() => document.body.appendChild(Object.assign(document.createElement("div"), { id: "widget-marker" })));
const markerAlive = (p: Page) => p.evaluate(() => Boolean(document.querySelector("#widget-marker")?.isConnected));

test.describe("context() and page_changed", () => {
  for (const [path, kind] of [
    ["/", "home"],
    [CATEGORY, "category"],
    [SEARCH, "search"],
    [PRODUCT, "product"],
    ["/carro", "cart"],
    ["/cotizacion", "quote"],
    ["/nuestras-tiendas", "stores"],
    ["/cambios-devoluciones", "policy"],
  ] as const) {
    test(`${path} is a ${kind} page`, async ({ page }) => {
      await serveSite(page, { cart: [{ code: "1173221", name: "Aceite LUBRITEK UTF Semisintético 19L", qty: 1 }] });
      await open(page, path);
      const ctx = await page.evaluate(() => window.voqalizeAgroplanet!.context());
      expect(ctx.kind).toBe(kind);
      expect(ctx.site).toBe("www.agroplanet.cl");
      await listen(page);
      const first = (await events(page))[0]!;
      expect(first.event).toBe("page_changed");
      expect(first.payload.kind).toBe(kind);
    });
  }

  test("the home's headings are its section titles, not the header, the SEO heading or the cards", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    const ctx = await page.evaluate(() => window.voqalizeAgroplanet!.context());
    expect(ctx.headings).toEqual(expect.arrayContaining(["CATEGORÍAS"]));
    expect(ctx.headings.some((h) => /^Aprovecha estas oportunidades/.test(h))).toBe(true);
    expect(ctx.headings.some((h) => /Autoplanet\.cl/.test(h))).toBe(false);
  });

  test("a policy page lists its panels as questions, not the footer's or the menu's", async ({ page }) => {
    await serveSite(page);
    await open(page, "/cambios-devoluciones");
    const ctx = await page.evaluate(() => window.voqalizeAgroplanet!.context());
    expect(ctx.faqs).toEqual(expect.arrayContaining(["Garantía Legal", "Restitución de dinero"]));
    expect(ctx.faqs).not.toContain("Te ayudamos");
    expect(ctx.faqs).not.toContain("Baterías");
  });
});

test.describe("the app's routes", () => {
  test("page.open moves the app in place: no load, the widget's slot kept, the watchers picked again for each route", async ({ page }) => {
    const seen = await serveSite(page);
    await open(page, "/");
    await listen(page);
    await plantMarker(page);
    const toListing = await run(page, "page.open", { path: CATEGORY });
    expect(toListing.ok, toListing.error).toBe(true);
    const listing = await waitForEvent(page, "listing.shown");
    expect(listing.payload).toMatchObject({ path: CATEGORY, title: "Lubricantes", count: 58 });
    expect(named(await events(page), "page_changed").map((e) => e.payload.kind)).toContain("category");
    const toProduct = await run(page, "open_product", { path: PRODUCT });
    expect(toProduct.ok, toProduct.error).toBe(true);
    await waitForEvent(page, "product.checked");
    expect(named(await events(page), "page_changed").map((e) => e.payload.kind)).toEqual(expect.arrayContaining(["category", "product"]));
    // The visitor's back button: the router again, and the listing reported again.
    const before = named(await events(page), "page_changed").length;
    await page.evaluate(() => history.back());
    await expect.poll(async () => named(await events(page), "page_changed").slice(before).map((e) => e.payload.kind), { timeout: 10_000 }).toContain("category");
    expect(seen.pages).toEqual(["/"]);
    expect(await markerAlive(page)).toBe(true);
  });

  test("a press on one of the page's own links is the visitor's: reported as theirs", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    await listen(page);
    await waitForEvent(page, "listing.shown");
    await page.locator("app-plp-grid a[href*='/producto/']").first().click();
    const shown = await waitForEvent(page, "product.shown");
    expect(shown.by).toBe("visitor");
    expect(shown.payload).toMatchObject({ sku: "1173221", name: "Aceite LUBRITEK UTF Semisintético 19L", price: 80000, maker_code: "AGPLUBLTUTFBLD" });
  });
});

test.describe("listings", () => {
  test("a category reports listing.shown: every option of every facet from the store's answer, the sort, twelve cards at most", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    await listen(page);
    const shown = await waitForEvent(page, "listing.shown");
    expect(shown.payload).toMatchObject({ path: CATEGORY, title: "Lubricantes", count: 58, sort: "relevance" });
    const filters = shown.payload.filters as { facet: string; on: string[]; options: string[] }[];
    expect(filters.map((f) => f.facet)).toEqual(expect.arrayContaining(["Precio", "Base", "Viscosidad", "Marca"]));
    expect(filters.find((f) => f.facet === "Marca")!.options).toEqual(expect.arrayContaining(["LUBRITEK", "MOBIL", "WULKAN"]));
    const items = shown.payload.items as { path: string; name: string; price: number | null }[];
    expect(items.length).toBeLessThanOrEqual(12);
    expect(items[0]).toMatchObject({ path: PRODUCT, price: 80000 });
  });

  test("a card that says Confirmar precio en tienda has no price", async ({ page }) => {
    await serveSite(page);
    await open(page, SEARCH);
    await listen(page);
    const shown = await waitForEvent(page, "listing.shown");
    expect(shown.payload).toMatchObject({ path: SEARCH, title: 'Resultados para "bateria"', count: 88 });
    const items = shown.payload.items as { name: string; price: number | null }[];
    expect(items.find((i) => /Cable de Bateria Negativo/.test(i.name))?.price).toBeNull();
  });

  test("commerce.filter: the panel opened, the option ringed then ticked, the grid waited for; listing.filtered by him", async ({ page }) => {
    const seen = await serveSite(page);
    await open(page, CATEGORY);
    await listen(page);
    await waitForEvent(page, "listing.shown");
    await watchClicks(page);
    const result = await run(page, "commerce.filter", ["Marca", "LUBRITEK, MOBIL", CATEGORY]);
    expect(result.ok, result.error).toBe(true);
    expect(result.detail).toMatch(/^Marca: LUBRITEK, Marca: MOBIL on; Lubricantes: \d+ products/);
    const pressed = await clicks(page);
    expect(pressed.find((c) => c.what === "LUBRITEK")?.ringed).toBe(true);
    expect(pressed.find((c) => c.what === "Marca")?.ringed).toBe(true);
    expect(seen.api.some((a) => a.includes("getCategory?code=AG100&q=::brand_search:LUBRITEK"))).toBe(true);
    const filtered = named(await events(page), "listing.filtered");
    expect(filtered.length).toBeGreaterThan(0);
    const last = filtered[filtered.length - 1]!;
    expect(last.by).toBe("agent");
    expect((last.payload.filters as { facet: string; on: string[] }[]).find((f) => f.facet === "Marca")!.on).toEqual(["LUBRITEK", "MOBIL"]);
    // Never a listing mid-redraw: no report with no products.
    expect(named(await events(page), "listing.").every((e) => (e.payload.count as number) > 0)).toBe(true);
    expect(decodeURIComponent(page.url())).toContain("q=::brand_search:LUBRITEK:brand_search:MOBIL");
  });

  test("commerce.filter refuses a filter or an option the listing does not offer, naming every one it does", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    const noFacet = await run(page, "commerce.filter", ["Color", "Rojo"]);
    expect(noFacet.ok).toBe(false);
    expect(noFacet.result!.refused![0]).toMatchObject({ arg: "facet", options: expect.arrayContaining(["Marca", "Viscosidad"]) });
    const noOption = await run(page, "commerce.filter", ["Marca", "SONY"]);
    expect(noOption.ok).toBe(false);
    expect(noOption.result!.refused![0]!.arg).toBe("value");
    expect(noOption.result!.refused![0]!.options!.length).toBeGreaterThanOrEqual(15);
  });

  test("commerce.sort: Ordenar por opened and its item pressed; listing.sorted says price_asc", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    await listen(page);
    await waitForEvent(page, "listing.shown");
    const result = await run(page, "commerce.sort", ["price_asc"]);
    expect(result.ok, result.error).toBe(true);
    expect(result.detail).toContain("sorted Menor precio");
    const sorted = await waitForEvent(page, "listing.sorted");
    expect(sorted.payload.sort).toBe("price_asc");
    expect(page.url()).toContain("sort=price-asc");
    const newest = await run(page, "commerce.sort", ["newest"]);
    expect(newest.ok).toBe(false);
    expect(newest.result!.refused![0]!.options).toEqual(["Menor precio", "Mayor precio", "Relevancia"]);
  });

  test("filter_listing from the home: the app moved there, then each filter named, the sort and the page, in place", async ({ page }) => {
    const seen = await serveSite(page);
    await open(page, "/");
    const result = await run(page, "filter_listing", { category_path: CATEGORY, filters: ["Marca: LUBRITEK"], sort: "price_desc", page: null });
    expect(result.ok, result.error).toBe(true);
    expect(result.detail).toContain("applied Marca: LUBRITEK, sorted Mayor precio");
    expect(seen.pages).toEqual(["/"]);
    expect(decodeURIComponent(page.url())).toContain("sort=price-desc");
  });

  test("filter_listing takes off what it is asked, keeps what it is not, clears, and turns the page", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    await run(page, "commerce.filter", ["Marca", "LUBRITEK, MOBIL"]);
    const off = await run(page, "filter_listing", { category_path: CATEGORY, remove: ["Marca: MOBIL"] });
    expect(off.ok, off.error).toBe(true);
    expect(off.detail).toContain("Marca: MOBIL off");
    expect(decodeURIComponent(page.url())).toContain("brand_search:LUBRITEK");
    expect(decodeURIComponent(page.url())).not.toContain("MOBIL");
    // A filter named while another is on: the other stays.
    const more = await run(page, "filter_listing", { category_path: CATEGORY, filters: ["Marca: SHELL"] });
    expect(more.ok, more.error).toBe(true);
    expect(decodeURIComponent(page.url())).toContain("brand_search:LUBRITEK:brand_search:SHELL");
    const clear = await run(page, "filter_listing", { category_path: CATEGORY, clear: true });
    expect(clear.ok, clear.error).toBe(true);
    expect(clear.detail).toContain("every filter off");
    expect(new URL(page.url()).searchParams.get("q") ?? "").not.toContain("brand_search");
    const paged = await run(page, "filter_listing", { category_path: CATEGORY, page: 2 });
    expect(paged.ok, paged.error).toBe(true);
    expect(paged.detail).toContain("page 2 of 2");
    expect(new URL(page.url()).searchParams.get("page")).toBe("1");
    const tooFar = await run(page, "filter_listing", { category_path: CATEGORY, page: 9 });
    expect(tooFar.ok).toBe(false);
    expect(tooFar.result!.refused![0]).toMatchObject({ arg: "page", options: ["1", "2"] });
  });

  test("filter_listing refuses an address that is not a listing", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    const result = await run(page, "filter_listing", { category_path: "/nuestras-tiendas", filters: [] });
    expect(result.ok).toBe(false);
    expect(result.result!.refused![0]!.arg).toBe("category_path");
  });
});

test.describe("commerce.search", () => {
  test("types into the header's box, rings the suggestions, presses Enter: the results in place", async ({ page }) => {
    const seen = await serveSite(page);
    await open(page, "/");
    await listen(page);
    const result = await run(page, "commerce.search", { query: "bateria", open_index: null });
    expect(result.ok, result.error).toBe(true);
    expect(result.detail).toContain('searched "bateria"; Resultados para "bateria": 88 products');
    expect(seen.api.some((a) => a.startsWith("GET /search/autocomplete/SearchBox?term=bat"))).toBe(true);
    expect(seen.pages).toEqual(["/"]);
    await waitForEvent(page, "listing.shown", (e) => e.payload.path === SEARCH);
  });

  test("open_index opens that suggestion's product", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    const result = await run(page, "commerce.search", { query: "bateria", open_index: 0 });
    expect(result.ok, result.error).toBe(true);
    expect(result.detail).toMatch(/opened the suggestion/);
    expect(page.url()).toContain("/producto/");
  });
});

test.describe("the category menu", () => {
  test("menu.open: Todas las categorías pressed, the category hovered, its flyout up; the next move folds it", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    await watchClicks(page);
    const result = await run(page, "menu.open", { category: "Repuestos De Tractor" });
    expect(result.ok, result.error).toBe(true);
    expect(result.detail).toContain("opened Todas las categorías at Repuestos De Tractor: Sistema Hidráulico");
    expect((await clicks(page)).find((c) => /Todas las categor/.test(c.what))?.ringed).toBe(true);
    expect(await page.locator("#acordeon-main").isVisible()).toBe(true);
    const unknown = await run(page, "menu.open", { category: "Juguetería" });
    expect(unknown.ok).toBe(false);
    expect(unknown.result!.refused![0]!.options).toEqual(expect.arrayContaining(["Baterías", "Lubricantes Y Fluidos"]));
    await run(page, "page.show", { target: "CATEGORÍAS" });
    expect(await page.locator("#acordeon-main").isVisible()).toBe(false);
  });
});

test.describe("the product page", () => {
  test("open_product with specs: product.shown from the page, product.checked from the store, Especificaciones ringed", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    await listen(page);
    const result = await run(page, "open_product", { path: "/producto/x/1173221", tab: "specs" });
    expect(result.ok, result.error).toBe(true);
    expect(result.detail).toContain("Aceite LUBRITEK UTF Semisintético 19L is on screen at $80000");
    expect(result.detail).toContain("País Chile");
    const shown = await waitForEvent(page, "product.shown");
    expect(shown.by).toBe("agent");
    expect((shown.payload.specs as { label: string }[]).map((s) => s.label)).toContain("Peso bruto de caja (kg)");
    const checked = await waitForEvent(page, "product.checked");
    expect(checked.payload).toMatchObject({ sku: "1173221", price: 80000, price_hidden: false, stock: "inStock", stock_level: 632, discount: null });
  });

  test("a hidden price is reported hidden, never as a number", async ({ page }) => {
    await serveSite(page);
    await open(page, HIDDEN);
    await listen(page);
    const shown = await waitForEvent(page, "product.shown");
    expect(shown.payload).toMatchObject({ sku: "139083", price: null, price_hidden: true });
    const checked = await waitForEvent(page, "product.checked");
    expect(checked.payload).toMatchObject({ price: null, price_hidden: true });
    const price = await run(page, "product.tab", { tab: "price" });
    expect(price.detail).toContain("Confirmar precio en tienda");
  });

  test("product.tab: details, photos, zoom and price; a specification row by its label", async ({ page }) => {
    await serveSite(page);
    await open(page, PRODUCT);
    for (const tab of ["details", "photos", "zoom", "price"]) {
      const r = await run(page, "product.tab", { tab });
      expect(r.ok, `${tab}: ${r.error}`).toBe(true);
    }
    const row = await run(page, "page.show", { target: "País" });
    expect(row.detail).toBe("showed País: Chile");
  });
});

test.describe("reads", () => {
  test("check_prices, find_products and check_stock read the store's API and report", async ({ page }) => {
    await serveSite(page);
    await open(page, PRODUCT);
    await listen(page);
    const prices = await run(page, "check_prices", { paths: [PRODUCT, HIDDEN] });
    expect(prices.ok, prices.error).toBe(true);
    const read = await waitForEvent(page, "prices_read");
    const items = read.payload.items as { sku: string; price: number | null; price_hidden: boolean }[];
    expect(items).toEqual(expect.arrayContaining([expect.objectContaining({ sku: "1173221", price: 80000 }), expect.objectContaining({ sku: "139083", price: null, price_hidden: true })]));
    const found = await run(page, "find_products", { query: "bateria", brand: null, category_code: null, sort: null });
    expect(found.ok, found.error).toBe(true);
    expect((await waitForEvent(page, "products_found")).payload).toMatchObject({ query: "bateria", total: 88, suggestion: "batería" });
    const stock = await run(page, "check_stock", { path: PRODUCT, store: "Chillán" });
    expect(stock.ok, stock.error).toBe(true);
    expect((await waitForEvent(page, "stock_read")).payload).toMatchObject({ sku: "1173221", online: "inStock", stores: [], matched: "Chillan" });
    const noStore = await run(page, "check_stock", { path: PRODUCT, store: "Arica" });
    expect(noStore.ok).toBe(false);
  });
});

test.describe("the cart and the quote", () => {
  test("cart_add 2: Agregar al carro, then the stepper's + (its id is #minus-…); cart.changed by him", async ({ page }) => {
    const seen = await serveSite(page);
    await open(page, PRODUCT);
    await listen(page);
    await watchClicks(page);
    const result = await run(page, "commerce.cart_add", { path: PRODUCT, qty: 2 });
    expect(result.ok, result.error).toBe(true);
    expect(result.detail).toContain("added 2 x Aceite LUBRITEK UTF Semisintético 19L");
    expect(seen.api.filter((a) => a.startsWith("POST /cart/add"))).toHaveLength(1);
    expect(seen.api.some((a) => a.startsWith("POST /cart/update entryNumber=0&quantity=2"))).toBe(true);
    const pressed = await clicks(page);
    expect(pressed.find((c) => c.what === "Agregar al carro")?.ringed).toBe(true);
    expect(pressed.some((c) => c.id === "minus-1173221" || c.what === "add")).toBe(true);
    expect(pressed.some((c) => /^cotizar$/i.test(c.what))).toBe(false);
    const changed = await waitForEvent(page, "cart.changed", (e) => e.payload.count === 2);
    expect(changed.by).toBe("agent");
  });

  test("cart_update on /carro: + and − by their icons, 0 by Eliminar", async ({ page }) => {
    const seen = await serveSite(page, { cart: [{ code: "1173221", name: "Aceite LUBRITEK UTF Semisintético 19L", qty: 1 }] });
    await open(page, "/");
    const up = await run(page, "commerce.cart_update", { path: "/producto/x/1173221", qty: 3 });
    expect(up.ok, up.error).toBe(true);
    expect(up.detail).toContain("set to 3; the cart has 3 items, $240000");
    const down = await run(page, "commerce.cart_update", { path: "/producto/x/1173221", qty: 2 });
    expect(down.ok, down.error).toBe(true);
    expect(seen.api.filter((a) => a.startsWith("POST /cart/update")).map((a) => a.match(/quantity=(\d+)/)![1])).toEqual(["2", "3", "2"]);
    const gone = await run(page, "commerce.cart_update", { path: "/producto/x/1173221", qty: 0 });
    expect(gone.ok, gone.error).toBe(true);
    expect(gone.detail).toContain("removed");
    expect(seen.api.some((a) => a.startsWith("GET /cart/delete?entryNumber=0"))).toBe(true);
    expect(seen.pages).toEqual(["/"]);
  });

  test("start_quote then fill_quote: every field but the RUT, the región and comuna chosen, Crear cotización never pressed", async ({ page }) => {
    await serveSite(page, { cart: [{ code: "1173221", name: "Aceite LUBRITEK UTF Semisintético 19L", qty: 1 }] });
    await open(page, "/carro");
    await listen(page);
    await watchClicks(page);
    const started = await run(page, "start_quote", {});
    expect(started.ok, started.error).toBe(true);
    expect(started.detail).toContain("on the Formulario de cotización");
    expect(new URL(page.url()).pathname).toBe("/cotizacion");
    const first = await waitForEvent(page, "quote.changed");
    expect(first.payload).toMatchObject({ step: "form", items: 1, total: 80000 });
    expect(first.payload.missing).toContain("rut");
    const filled = await run(page, "fill_quote", {
      name: "Prueba Voqalize", phone: "+56 9 1234 5678", email: "prueba@example.com", region: "Metropolitana", commune: "Santiago", street: "Test", number: "1", unit: null, notes: "Retiro en tienda",
    });
    expect(filled.ok, filled.error).toBe(true);
    expect(filled.detail).toContain("filled name, phone, email, region, commune, street, number, notes; still missing: rut");
    expect(await page.locator("app-form-user-quote [formcontrolname=rut]").inputValue()).toBe("");
    expect(await page.locator("app-form-user-quote [formcontrolname=phone]").inputValue()).toBe("912345678");
    expect(await page.locator("mat-select#commune").getAttribute("data-value")).toBe("Santiago centro");
    expect(await page.evaluate(() => (window as unknown as { __pressedCrear: number }).__pressedCrear)).toBe(0);
    expect((await clicks(page)).some((c) => /crear cotizaci/i.test(c.what))).toBe(false);
    const last = named(await events(page), "quote.changed").pop()!;
    expect(last.payload).toMatchObject({ step: "form", missing: ["rut"] });
    // Field names only: nothing the visitor said is in the report.
    expect(JSON.stringify(last.payload)).not.toMatch(/Prueba|example|912345678|Test/);
  });

  test("fill_quote refuses a phone the form cannot take, and goes on with the rest", async ({ page }) => {
    await serveSite(page, { cart: [{ code: "1173221", name: "Aceite LUBRITEK UTF Semisintético 19L", qty: 1 }] });
    await open(page, "/cotizacion");
    const r = await run(page, "fill_quote", { name: "Prueba Voqalize", phone: "1234" });
    expect(r.ok, r.error).toBe(true);
    expect(r.result!.outcome).toBe("partial");
    expect(r.result!.refused![0]!.arg).toBe("phone");
  });
});

test.describe("the guard", () => {
  test("the RUT is never typed, Crear cotización never pressed, the login and payment never touched", async ({ page }) => {
    await serveSite(page, { cart: [{ code: "1173221", name: "Aceite LUBRITEK UTF Semisintético 19L", qty: 1 }] });
    await open(page, "/cotizacion");
    const outcome = await page.evaluate(async () => {
      const t = (window as unknown as { __voqalizeTest: Record<string, (...a: unknown[]) => unknown> }).__voqalizeTest;
      const tries: Record<string, string> = {};
      const attempt = async (name: string, fn: () => unknown) => {
        try {
          await fn();
          tries[name] = "done";
        } catch (e) {
          tries[name] = (e as Error).message;
        }
      };
      await attempt("rut", () => t.typeInto!(document.querySelector("app-form-user-quote [formcontrolname=rut]"), "11.111.111-1", 1));
      await attempt("crear", () => t.press!([...document.querySelectorAll("app-form-user-quote button")].find((b) => /crear/i.test(b.textContent ?? ""))));
      await attempt("login", () => t.press!(document.querySelector("app-icon-sign-in")));
      await attempt("registrate", () => t.target!("/registrate"));
      await attempt("confirmacion", () => t.target!("/cotizacion/confirmacion"));
      await attempt("offsite", () => t.target!("https://www.webpay.cl/form-pay/53532"));
      await attempt("name", () => t.typeInto!(document.querySelector("app-form-user-quote [formcontrolname=name]"), "Ana", 1));
      return { tries, rut: (document.querySelector("app-form-user-quote [formcontrolname=rut]") as HTMLInputElement).value };
    });
    expect(outcome.rut).toBe("");
    expect(outcome.tries.rut).toContain("refused to type");
    expect(outcome.tries.crear).toContain("Crear cotización");
    expect(outcome.tries.login).toContain("refused to press");
    expect(outcome.tries.registrate).toContain("refused to open /registrate");
    expect(outcome.tries.confirmacion).toContain("refused to open");
    expect(outcome.tries.offsite).toContain("not on www.agroplanet.cl");
    expect(outcome.tries.name).toBe("done");
  });

  test("the product page's Cotizar is refused: it adds and opens the quote in one press", async ({ page }) => {
    await serveSite(page);
    await open(page, PRODUCT);
    const why = await page.evaluate(() => {
      const t = (window as unknown as { __voqalizeTest: { refusal(el: Element): string | null } }).__voqalizeTest;
      return t.refusal([...document.querySelectorAll("app-product-info button")].find((b) => /cotizar/i.test(b.textContent ?? ""))!);
    });
    expect(why).toContain("Cotizar");
  });
});

test.describe("show, faq, stores", () => {
  test("the home's splash window is closed before anything scrolls", async ({ page }) => {
    await serveSite(page, { splash: true });
    await open(page, "/");
    expect(await page.locator("app-generic-dialog").count()).toBe(1);
    const r = await run(page, "page.show", { target: "CATEGORÍAS" });
    expect(r.ok, r.error).toBe(true);
    expect(await page.locator("app-generic-dialog").count()).toBe(0);
    expect(await page.evaluate(() => document.documentElement.classList.contains("cdk-global-scrollblock"))).toBe(false);
    expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
  });

  test("page.faq opens a panel by its title, also cut short", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    const r = await run(page, "page.faq", { question: "Garantía Legal", path: "/cambios-devoluciones" });
    expect(r.ok, r.error).toBe(true);
    expect(await page.locator("mat-expansion-panel.mat-expanded", { hasText: "Garantía Legal" }).count()).toBeGreaterThan(0);
    const cut = await run(page, "page.faq", { question: "¿Cómo cambio un producto si vivo en una ciudad", path: null });
    expect(cut.ok, cut.error).toBe(true);
    expect(cut.detail).toContain("¿Cómo cambio un producto si vivo en una ciudad muy lejana");
  });

  test("stores.show finds a store on another page of the list, and one by its city", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    await listen(page);
    const osorno = await run(page, "stores.show", { name: "Osorno" });
    expect(osorno.ok, osorno.error).toBe(true);
    expect((await waitForEvent(page, "store_shown")).payload).toMatchObject({ name: "Osorno" });
    const serena = await run(page, "stores.show", { name: "La Serena" });
    expect(serena.ok, serena.error).toBe(true);
    expect(serena.detail).toMatch(/^Coquimbo:/);
    const concepcion = await run(page, "stores.show", { name: "Concepción" });
    expect(concepcion.ok, concepcion.error).toBe(true);
  });

  test("the anchors keep Chrome's translator off what the adapter matches", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    const marked = await page.evaluate(() =>
      ["mat-panel-title", "app-plp-grid p.title", "a.mat-menu-trigger"].map((s) => document.querySelector(s)?.getAttribute("translate")),
    );
    expect(marked).toEqual(["no", "no", "no"]);
  });
});
