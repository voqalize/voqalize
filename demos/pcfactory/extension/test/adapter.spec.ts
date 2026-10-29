/**
 * The PC Factory adapter, end to end against trimmed copies of the store's
 * pages and its API (see site.ts): each move the brain sends, the events the
 * page answers with, the moves that survive a full page load, and the guard
 * that stops at Tipo de entrega.
 */

import { expect, type Page, test } from "@playwright/test";

import { CABLE, CATEGORY, type Emitted, events, listen, matches, open, ORIGIN, PRODUCT, run, SEARCH, serveSite, waitForEvent } from "./site";

/** `run` for a move that loads another page: the page may go before it answers. */
async function runAway(p: Page, command: string, payload: unknown): Promise<void> {
  await run(p, command, payload).catch((error: Error) => {
    if (!/context was destroyed|navigat/i.test(error.message)) throw error;
  });
}

/** The result a move carried to this page reports here. */
async function carried(p: Page, path: RegExp | string): Promise<Record<string, unknown>> {
  await p.waitForURL(typeof path === "string" ? `${ORIGIN}${path}` : path, { waitUntil: "domcontentloaded" });
  await listen(p);
  return (await waitForEvent(p, "stage_result", () => true, 30_000)).payload;
}

const named = (list: Emitted[], name: string) => list.filter((e) => matches(e, name));

/** Record every click with whether a ring was up around it at that moment. */
async function watchClicks(p: Page): Promise<void> {
  await p.evaluate(() => {
    const w = window as unknown as { __clicks: { what: string; ringed: boolean }[] };
    w.__clicks = [];
    document.addEventListener(
      "click",
      (e) => {
        const el = e.target as Element;
        const r = el.getBoundingClientRect();
        const rings = [...(document.querySelector("[data-voqalize=spotlight]")?.shadowRoot?.querySelectorAll(".ring") ?? [])];
        const ringed = rings.some((ring) => {
          const b = ring.getBoundingClientRect();
          // The ring keeps 3 px inside the viewport, so an element at its
          // very edge is ringed a few pixels short of that edge.
          return b.left <= r.left + 4 && b.top <= r.top + 4 && b.right >= r.right - 4 && b.bottom >= r.bottom - 4;
        });
        w.__clicks.push({ what: (el.textContent ?? "").trim().slice(0, 40) || el.id || el.className, ringed });
      },
      true,
    );
  });
}
const clicks = (p: Page) => p.evaluate(() => (window as unknown as { __clicks: { what: string; ringed: boolean }[] }).__clicks);

test.describe("context() and page_changed", () => {
  for (const [path, kind] of [
    ["/", "home"],
    [CATEGORY, "category"],
    [SEARCH, "search"],
    [PRODUCT, "product"],
    ["/carro", "cart"],
    ["/tiendas", "stores"],
    ["/centro-de-ayuda/compra-con-retiro-en-tienda", "help"],
    ["/checkout", "checkout"],
  ] as const) {
    test(`${path} is a ${kind} page`, async ({ page }) => {
      await serveSite(page);
      await open(page, path);
      const ctx = await page.evaluate(() => window.voqalizePcfactory!.context());
      expect(ctx.kind).toBe(kind);
      expect(ctx.site).toBe("www.pcfactory.cl");
      await listen(page);
      const first = (await events(page))[0]!;
      expect(first.event).toBe("page_changed");
      expect(first.payload.kind).toBe(kind);
    });
  }

  test("the home's headings are its sections, not the header or the cards", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    const ctx = await page.evaluate(() => window.voqalizePcfactory!.context());
    expect(ctx.headings).toEqual(expect.arrayContaining(["Te recomendamos", "Ofertas y Lanzamientos", "Cupones", "Computación"]));
    expect(ctx.headings.length).toBeLessThanOrEqual(80);
  });

  test("the help page lists its questions", async ({ page }) => {
    await serveSite(page);
    await open(page, "/centro-de-ayuda/compra-con-retiro-en-tienda");
    const ctx = await page.evaluate(() => window.voqalizePcfactory!.context());
    expect(ctx.faqs).toContain("¿Cuántos días tengo para hacer el retiro de mi compra en tienda?");
    expect(ctx.faqs).not.toContain("¿En qué podemos ayudarte?");
  });
});

test.describe("listings", () => {
  test("a category reports listing.shown: its facets as the page names them, the sort, twelve cards at most", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    await listen(page);
    const shown = await waitForEvent(page, "listing.shown");
    expect(shown.payload).toMatchObject({ path: CATEGORY, title: "Notebooks", count: 158, sort: "relevance" });
    const filters = shown.payload.filters as { facet: string; on: string[]; options: string[] }[];
    expect(filters.map((f) => f.facet)).toEqual(expect.arrayContaining(["Tiendas", "Marcas", "RAM"]));
    expect(filters.map((f) => f.facet)).not.toContain("Rango de precios");
    expect(filters.find((f) => f.facet === "Marcas")!.options).toContain("Lenovo");
    // Every option of every facet: none cut (dev call 8b363867).
    const inDom = await page.evaluate(() =>
      [...document.querySelectorAll("#panel-filters .panel-filters__filter")]
        .filter((g) => !g.querySelector("input[type=range]") && !/precio/i.test(g.textContent ?? ""))
        .map((g) => g.querySelectorAll(".form-check input[type=checkbox]").length),
    );
    expect(filters.map((f) => f.options.length).reduce((a, b) => a + b, 0)).toBe(inDom.reduce((a, b) => a + b, 0));
    const items = shown.payload.items as { path: string; name: string; price: number }[];
    expect(items[0]).toMatchObject({ path: "/producto/57695", price: 729990, regular_price: 1049990 });
    expect(items[0]!.name).toContain("Notebook 14-ep1330la");
  });

  test("a search's listing path carries its words and nothing else", async ({ page }) => {
    await serveSite(page);
    await open(page, `${SEARCH}&size=12`);
    await listen(page);
    const shown = await waitForEvent(page, "listing.shown");
    expect(shown.payload).toMatchObject({ path: "/busqueda-avanzada?search=monitor+27", title: 'Resultados para "monitor 27"', count: 76 });
  });

  test("commerce.filter: the group opened, the option ringed then ticked, the grid waited for; listing.filtered by him", async ({ page }) => {
    const seen = await serveSite(page);
    await open(page, CATEGORY);
    await listen(page);
    await watchClicks(page);
    const result = await run(page, "commerce.filter", ["Marcas", "Lenovo"]);
    expect(result.ok, result.error).toBe(true);
    expect(result.detail).toMatch(/^Marcas: Lenovo on; Notebooks: \d+ products/);
    const pressed = await clicks(page);
    expect(pressed.find((c) => c.what.startsWith("Lenovo"))?.ringed).toBe(true);
    expect(pressed.find((c) => c.what === "Marcas")?.ringed).toBe(true);
    expect(seen.api.some((a) => a.includes("/productos/query"))).toBe(true);
    const filtered = await waitForEvent(page, "listing.filtered");
    expect(filtered.by).toBe("agent");
    expect((filtered.payload.filters as { facet: string; on: string[] }[]).find((f) => f.facet === "Marcas")!.on).toEqual(["Lenovo"]);
  });

  test("commerce.filter refuses a filter or an option the listing does not offer, naming what it does", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    const noFacet = await run(page, "commerce.filter", ["Color", "Rojo"]);
    expect(noFacet.ok).toBe(false);
    expect(noFacet.result!.refused![0]).toMatchObject({ arg: "facet", options: expect.arrayContaining(["Marcas", "RAM", "Tiendas"]) });
    const noOption = await run(page, "commerce.filter", ["Marcas", "Sony"]);
    expect(noOption.ok).toBe(false);
    expect(noOption.result!.refused![0]).toMatchObject({ arg: "value", options: expect.arrayContaining(["Lenovo", "HP"]) });
  });

  test("commerce.sort: Ordenar por opened and its item pressed; listing.sorted says price_asc", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    await listen(page);
    const result = await run(page, "commerce.sort", ["price_asc"]);
    expect(result.ok, result.error).toBe(true);
    expect(result.detail).toContain("sorted Precio menor a mayor");
    const sorted = await waitForEvent(page, "listing.sorted");
    expect(sorted.payload.sort).toBe("price_asc");
    expect(decodeURIComponent(page.url())).toContain("sort=precio,asc");
    const newest = await run(page, "commerce.sort", ["newest"]);
    expect(newest.ok).toBe(false);
    expect(newest.result!.refused![0]!.options).toEqual(["Recomendados", "Precio menor a mayor", "Precio mayor a menor"]);
  });

  test("filter_listing from the home: carried across the load, then each filter, the price range and the sort", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    await runAway(page, "filter_listing", { category_path: CATEGORY, filters: ["Marcas: Lenovo", "RAM: 16GB"], min_price: 600000, max_price: 900000, sort: "price_desc" });
    const done = await carried(page, new RegExp(`${CATEGORY}`));
    expect(done.move).toBe("filter_listing");
    expect(done.outcome).toBe("applied");
    expect(done.detail).toContain("applied Marcas: Lenovo, RAM: 16GB, Rango de precios $600000 – $900000, sorted Precio mayor a menor");
    expect(page.url()).toContain("precioMin=600000");
    expect(page.url()).toContain("precioMax=900000");
  });

  test("filter_listing takes what it can: a bad entry and a missing option make it partial", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    const result = await run(page, "filter_listing", { category_path: CATEGORY, filters: ["Marcas: HP", "Foo", "RAM: 3GB"] });
    expect(result.ok, result.error).toBe(true);
    expect(result.result!.outcome).toBe("partial");
    expect(result.result!.refused!.map((r) => r.arg)).toEqual(["filters", "filters"]);
    expect(result.result!.refused![1]!.options).toContain("16GB");
  });

  test("filter_listing refuses an address that is not a listing", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    const result = await run(page, "filter_listing", { category_path: "/tiendas", filters: [] });
    expect(result.ok).toBe(false);
    expect(result.result!.refused![0]!.arg).toBe("category_path");
  });
});

test.describe("commerce.search", () => {
  test("types into the store's box, presses its button and reports the results page", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    await runAway(page, "commerce.search", { query: "Monitor 27", open_index: null });
    const done = await carried(page, /busqueda-avanzada\?search=monitor\+27/);
    expect(done.move).toBe("commerce.search");
    expect(done.detail).toContain('searched "Monitor 27"; Resultados para "monitor 27": 76 products');
  });

  test("with open_index, opens that result and finishes on the product", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    await runAway(page, "commerce.search", { query: "monitor 27", open_index: 1 });
    await page.waitForURL(/busqueda-avanzada/, { waitUntil: "domcontentloaded" });
    const done = await carried(page, /\/producto\/\d+$/);
    expect(done.move).toBe("commerce.search");
    expect(String(done.detail)).toContain("is on screen at $1066990 transferencia");
  });
});

test.describe("the product page", () => {
  test("open_product: carried there, product.shown from the page, product.checked from the API, then the tab", async ({ page }) => {
    const seen = await serveSite(page);
    await open(page, CATEGORY);
    await runAway(page, "open_product", { path: "/producto/57233-lenovo-notebook", tab: "specs" });
    const done = await carried(page, PRODUCT);
    expect(done.outcome).toBe("applied");
    expect(done.detail).toContain("opened Especificaciones");
    const shown = await waitForEvent(page, "product.shown");
    expect(shown.payload).toMatchObject({ path: PRODUCT, id: 57233, brand: "Lenovo", price: 1066990, card_price: 1099990, source: "page" });
    expect(shown.payload.specs).toEqual(expect.arrayContaining([{ label: "Procesador", value: "AMD Ryzen 7" }]));
    const checked = await waitForEvent(page, "product.checked");
    expect(checked.payload).toMatchObject({ path: PRODUCT, source: "api", price: 1066990, warranty: "Garantía del fabricante de 12 meses" });
    expect(seen.api).toEqual(expect.arrayContaining(["GET /pcfactory-services-catalogo/v1/catalogo/productos/57233/precio"]));
    expect(await page.locator("#specifics").isVisible()).toBe(true);
  });

  test("product.tab: warranty, stock by store and the photos", async ({ page }) => {
    await serveSite(page);
    await open(page, PRODUCT);
    expect((await run(page, "product.tab", ["warranty"])).detail).toBe("opened Garantía");
    expect(await page.locator("#warranty").isVisible()).toBe(true);
    expect((await run(page, "product.tab", ["stock"])).detail).toMatch(/^showed Disponibilidad: Internet \S+, \d+ stores with stock$/);
    expect((await run(page, "product.tab", ["photos"])).detail).toMatch(/^stepped the gallery through \d photos/);
  });

  test("{show: Procesador} opens Especificaciones and rings that row, centred under the header", async ({ page }) => {
    await serveSite(page);
    await open(page, PRODUCT);
    const result = await run(page, "page.show", ["Procesador"]);
    expect(result.detail).toBe("showed Procesador: AMD Ryzen 7");
    const top = await page.evaluate(() => {
      const row = [...document.querySelectorAll("#specifics tr")].find((r) => r.querySelector("strong")?.textContent?.trim() === "Procesador")!;
      return row.getBoundingClientRect().top;
    });
    expect(top).toBeGreaterThan(100);
    expect(top).toBeLessThan(700);
  });
});

test.describe("reads: find_products, check_prices, check_stock", () => {
  test("find_products searches the API with the brand's own name and reports products_found", async ({ page }) => {
    const seen = await serveSite(page);
    await open(page, "/");
    await listen(page);
    const result = await run(page, "find_products", { query: "notebook", brand: "lenovo", max_price: 900000, sort: "price_asc" });
    expect(result.ok, result.error).toBe(true);
    expect(seen.api.some((a) => /\/productos\?.*search=notebook.*marcas=Lenovo.*precioMax=900000.*sort=precio,asc/.test(a))).toBe(true);
    const found = await waitForEvent(page, "products_found");
    expect(found.payload).toMatchObject({ query: "notebook", total: 322 });
    expect((found.payload.items as unknown[]).length).toBeLessThanOrEqual(8);
    expect(page.url()).toBe(`${ORIGIN}/`);
  });

  test("find_products by category takes the brand's id, and refuses a brand it does not carry", async ({ page }) => {
    const seen = await serveSite(page);
    await open(page, "/");
    expect((await run(page, "find_products", { category_id: 425, brand: "HP" })).ok).toBe(true);
    expect(seen.api.some((a) => /\/productos\/query\?.*categorias=425.*marcas=73/.test(a))).toBe(true);
    const sony = await run(page, "find_products", { category_id: 425, brand: "Sony" });
    expect(sony.ok).toBe(false);
    expect(sony.result!.refused![0]).toMatchObject({ arg: "brand", options: expect.arrayContaining(["Lenovo"]) });
  });

  test("check_prices reads each product live and names the ones not found", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    await listen(page);
    const result = await run(page, "check_prices", { paths: ["/producto/8941-spektra-cable", "/producto/123"] });
    expect(result.detail).toContain("Cable USB 2.0 A/A 1.8m Extensión: $1490 transferencia, $1590 otros medios (ref. $1990)");
    const read = await waitForEvent(page, "prices_read");
    expect(read.payload.missing).toEqual(["/producto/123"]);
  });

  test("check_stock matches a store by its /tiendas name, rings its Disponibilidad row, and refuses one that is not a store", async ({ page }) => {
    await serveSite(page);
    await open(page, PRODUCT);
    await listen(page);
    const result = await run(page, "check_stock", { path: PRODUCT, store: "Mall Cenco Costanera" });
    expect(result.detail).toContain("Mall Costanera Center: 0");
    const read = await waitForEvent(page, "stock_read");
    expect(read.payload).toMatchObject({ path: PRODUCT, asked: "Mall Cenco Costanera", matched: "Mall Costanera Center" });
    expect((read.payload.stores as { qty: string }[]).every((s) => s.qty !== "0")).toBe(true);
    expect((await run(page, "check_stock", { path: PRODUCT, store: "maipu" })).detail).toContain("Mall Arauco Maipú");
    const none = await run(page, "check_stock", { path: PRODUCT, store: "Narnia" });
    expect(none.ok).toBe(false);
    expect(none.result!.refused![0]!.arg).toBe("store");
  });
});

test.describe("show and faq cues, stores", () => {
  test("{show:} rings a home section, a coupon card, and refuses words the page lacks", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    expect((await run(page, "page.show", ["Cupones"])).detail).toBe('showed "Cupones"');
    expect((await run(page, "page.show", ["LEN50"])).detail).toMatch(/^showed the coupon LEN50: \$50\.000/);
    const none = await run(page, "page.show", ["Unicornio dorado"]);
    expect(none.ok).toBe(false);
    expect(none.result!.refused![0]!.options).toContain("Te recomendamos");
  });

  test("{faq:} on a help page rings the question with its answer", async ({ page }) => {
    await serveSite(page);
    await open(page, "/centro-de-ayuda/compra-con-retiro-en-tienda");
    const result = await run(page, "page.faq", ["¿Cuántos días tengo para hacer el retiro de mi compra en tienda?"]);
    expect(result.detail).toBe('opened "¿Cuántos días tengo para hacer el retiro de mi compra en tienda?"');
  });

  test("stores.show: carried to /tiendas, the card ringed, Ver tienda pressed, store_shown with its hours and no manager", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    await runAway(page, "stores.show", ["Mall Cenco Costanera"]);
    const done = await carried(page, "/tiendas");
    expect(done.detail).toBe("Mall Cenco Costanera: Avenida Andrés Bello 2447, local 196, Providencia; hours Lunes a Viernes 10:00 a 20:00; Sábado 10:00 a 14:00");
    const shown = (await events(page)).find((e) => e.event === "store_shown")!;
    expect(shown.payload).toEqual({
      name: "Mall Cenco Costanera",
      address: "Avenida Andrés Bello 2447, local 196",
      city: "Providencia",
      region: "Región Metropolitana",
      zone: "Santiago",
      hours: "Lunes a Viernes 10:00 a 20:00; Sábado 10:00 a 14:00",
    });
    const bad = await run(page, "stores.show", ["Narnia"]);
    expect(bad.ok).toBe(false);
    expect(bad.result!.refused![0]!.options).toContain("Concepción");
  });
});

test.describe("the comparator, through its own bar", () => {
  test("compare.add ticks each card's box, rings the bar's Comparar, presses it and finishes on /comparador with the table", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    await listen(page);
    await watchClicks(page);
    await runAway(page, "compare.add", { paths: ["/producto/57695", "/producto/58436"], open: true });
    const done = await carried(page, /\/comparador\?prod1=57695&prod2=58436$/);
    expect(done.move).toBe("compare.add");
    expect(done.outcome, String(done.detail)).toBe("applied");
    expect(String(done.detail)).toMatch(/^pressed the comparator's Comparar; the comparison is on screen: .+ vs .+; \d+ rows with values: \d+ differ \(ID, Marca\), \d+ the same, \d+ with a value for only some$/);
    const shown = await waitForEvent(page, "compare.shown");
    const table = shown.payload as { items: { path: string; price: number }[]; rows: { label: string; values: string[] }[]; differs: string[]; category: string };
    expect(table.items.map((i) => i.path)).toEqual(["/producto/57695", "/producto/58436"]);
    expect(table.items.every((i) => i.price > 0)).toBe(true);
    expect(table.category).toBe("Notebooks");
    expect(table.rows.find((r) => r.label === "RAM")?.values).toHaveLength(2);
    expect(table.rows.every((r) => r.values.some(Boolean))).toBe(true);
    expect(table.differs).toContain("Marca");
  });

  test("the bar's Comparar is ringed before it is pressed", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    await page.evaluate(() => {
      const w = window as unknown as { __rang: boolean[] };
      w.__rang = [];
      const button = document.querySelector("#pcf-comparator-summary .compare-btn")!;
      button.addEventListener(
        "click",
        () => {
          const ring = document.querySelector("[data-voqalize=spotlight]")?.shadowRoot?.querySelector(".ring");
          w.__rang.push(Boolean(ring));
          sessionStorage.setItem("rang", JSON.stringify(w.__rang));
        },
        true,
      );
    });
    await runAway(page, "compare.add", { paths: ["/producto/57695", "/producto/58436"] });
    await page.waitForURL(/\/comparador/, { waitUntil: "domcontentloaded" });
    expect(await page.evaluate(() => sessionStorage.getItem("rang"))).toBe("[true]");
  });

  test("a product not on the listing is ticked on its own page, then the bar is used there", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    await runAway(page, "compare.add", { paths: ["/producto/57695", PRODUCT] });
    await page.waitForURL(`${ORIGIN}${PRODUCT}`, { waitUntil: "domcontentloaded" });
    const done = await carried(page, /\/comparador\?prod1=57695&prod2=57233$/);
    expect(done.outcome, String(done.detail)).toBe("applied");
    expect(String(done.detail)).toContain("pressed the comparator's Comparar");
  });

  test("the site's limits first: a fourth is refused, and so is a product of another category, before a box is ticked", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    const four = await run(page, "compare.add", { paths: ["/producto/57695", "/producto/58436", "/producto/55409", "/producto/57948"] });
    expect(four.ok).toBe(false);
    expect(four.error).toContain("the comparator holds at most 3");
    const mixed = await run(page, "compare.add", { paths: ["/producto/57695", CABLE] });
    expect(mixed.ok).toBe(false);
    expect(mixed.error).toContain("Sólo puedes comparar productos que pertenezcan a la misma categoría");
    expect(mixed.error).toContain("Notebooks and Cables Datos / USB");
    expect(await page.evaluate(() => localStorage.getItem("comparator-items") ?? "[]")).toBe("[]");
  });

  test("a product the comparator refuses: its own reason", async ({ page }) => {
    await serveSite(page);
    await page.addInitScript(() => localStorage.setItem("comparator-items", JSON.stringify([{ id: 1, nombre: "Cable", cat: "Cables" }])));
    await open(page, CATEGORY);
    const result = await run(page, "compare.add", { paths: ["/producto/57695"] });
    expect(result.ok).toBe(false);
    expect(result.error).toContain("Sólo puedes comparar productos que pertenezcan a la misma categoría");
  });

  test("on the product page, its own Comparar; one product leaves the bar up", async ({ page }) => {
    await serveSite(page);
    await open(page, PRODUCT);
    const result = await run(page, "compare.add", { paths: [PRODUCT] });
    expect(result.detail, result.error).toMatch(/^the comparator holds 1\/3: Notebook Gamer LOQe.*; Comparar opens with two or more$/);
  });

  test("compare.show rings a row across the products, switches on Destacar diferencias, rings the prices, refuses a row it lacks", async ({ page }) => {
    await serveSite(page);
    await open(page, "/comparador?prod1=57695&prod2=58436");
    await listen(page);
    const ram = await run(page, "compare.show", ["ram"]);
    expect(ram.detail, ram.error).toMatch(/^showed RAM: \S+ \| \S+$/);
    const top = await page.evaluate(() => [...document.querySelectorAll("#pcf-comparator tr")].find((r) => r.querySelector("th")?.textContent?.trim() === "RAM")!.getBoundingClientRect().top);
    expect(top).toBeGreaterThan(0);
    expect(top).toBeLessThan(900);
    const diff = await run(page, "compare.show", ["diferencias"]);
    expect(diff.detail).toMatch(/^Destacar diferencias is on: \d+ rows differ \(/);
    expect(await page.locator("#pcf-comparator tr.highlight-row").count()).toBeGreaterThan(0);
    const again = await waitForEvent(page, "compare.shown", (e) => e.payload.highlighted === true);
    expect(again.by).toBe("agent");
    expect((await run(page, "compare.show", ["precio"])).detail).toMatch(/^showed the prices: \$\d+ \| \$\d+$/);
    const none = await run(page, "compare.show", ["Unicornio"]);
    expect(none.ok).toBe(false);
    expect(none.result!.refused![0]!.options).toContain("RAM");
  });

  test("compare.remove takes a product out of the comparison and keeps the address honest; on a listing, Limpiar selección", async ({ page }) => {
    await serveSite(page);
    await open(page, "/comparador?prod1=57695&prod2=58436");
    await listen(page);
    const out = await run(page, "compare.remove", { path: "/producto/58436" });
    expect(out.detail, out.error).toMatch(/^took \/producto\/58436 out of the comparison; it shows 1: /);
    expect(page.url()).toBe(`${ORIGIN}/comparador?prod1=57695`);
    await open(page, CATEGORY);
    await page.evaluate(() => document.querySelector<HTMLInputElement>("#product-checkbox57695")!.click());
    const all = await run(page, "compare.remove", { all: true });
    expect(all.detail, all.error).toBe("the comparator holds 0/3");
  });
});

test.describe("the listing's own controls", () => {
  test("a redraw that empties the grid is never reported: no listing with 0 products, one listing.filtered", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    await listen(page);
    await waitForEvent(page, "listing.shown");
    await page.evaluate(() => ((window as unknown as { __slowRedraw: boolean }).__slowRedraw = true));
    const result = await run(page, "commerce.filter", ["Marcas", "Lenovo"]);
    expect(result.ok, result.error).toBe(true);
    await page.waitForTimeout(1500);
    const his = named(await events(page), "listing.").filter((e) => e.by === "agent");
    expect(his.map((e) => e.event)).toEqual(["listing.filtered"]);
    expect(his[0]!.call_ref).toBeTruthy();
    // And the visitor's own tick, which the page's watch reports.
    await page.evaluate(() => {
      const label = [...document.querySelectorAll("#panel-filters label")].find((l) => /^HP/.test(l.textContent?.trim() ?? ""))!;
      (label as HTMLElement).click();
    });
    await page.waitForTimeout(2500);
    const listings = named(await events(page), "listing.");
    expect(listings.filter((e) => e.payload.count === 0 || (e.payload.items as unknown[]).length === 0)).toEqual([]);
    expect(listings.some((e) => (e.payload.filters as { on: string[] }[]).some((f) => f.on.includes("HP")))).toBe(true);
  });

  test("an option the filters on left out is a note, not a refusal; one never offered is refused", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    await listen(page);
    await waitForEvent(page, "listing.shown");
    expect((await run(page, "commerce.filter", ["Marcas", "Lenovo"])).ok).toBe(true);
    // Lenovo narrowed the panel: it no longer offers 24GB (dev call 8b363867).
    await page.evaluate(() => {
      const box = [...document.querySelectorAll("#panel-filters .form-check")].find((b) => b.textContent?.trim().startsWith("24GB"));
      box?.remove();
    });
    const result = await run(page, "commerce.filter", ["RAM", "16GB, 24GB"]);
    expect(result.ok, result.error).toBe(true);
    expect(result.result!.outcome).toBe("applied");
    expect(result.detail).toMatch(/^RAM: 16GB on; not offered with the filters on: 24GB; /);
    const never = await run(page, "commerce.filter", ["RAM", "8GB, 3GB"]);
    expect(never.result!.outcome).toBe("partial");
  });

  test("filter_listing takes a filter off with its chip, every one with Limpiar todos, in place", async ({ page }) => {
    const seen = await serveSite(page);
    await open(page, CATEGORY);
    await run(page, "commerce.filter", ["Marcas", "Lenovo, HP"]);
    const loads = seen.pages.length;
    const off = await run(page, "filter_listing", { category_path: CATEGORY, remove: ["Marcas: HP"] });
    expect(off.detail, off.error).toContain("applied Marcas: HP off");
    expect(await page.locator("#panel-filters input:checked").count()).toBe(1);
    const clear = await run(page, "filter_listing", { category_path: CATEGORY, clear: true });
    expect(clear.detail, clear.error).toContain("applied every filter off (Limpiar todos)");
    expect(await page.locator("#panel-filters input:checked").count()).toBe(0);
    expect(seen.pages.length).toBe(loads);
  });

  test("filter_listing takes off a filter the wish lacks with its chip, not a reload", async ({ page }) => {
    const seen = await serveSite(page);
    await open(page, CATEGORY);
    await run(page, "commerce.filter", ["Marcas", "HP"]);
    const loads = seen.pages.length;
    const result = await run(page, "filter_listing", { category_path: CATEGORY, filters: ["Marcas: Lenovo"] });
    expect(result.detail, result.error).toContain("applied Marcas: HP off, Marcas: Lenovo");
    expect(seen.pages.length).toBe(loads);
  });

  test("filter_listing sets Productos por página in place, and turns the page with the pager (a load)", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    const size = await run(page, "filter_listing", { category_path: CATEGORY, size: 32 });
    expect(size.detail, size.error).toContain("applied 32 per page");
    expect(page.url()).toContain("size=32");
    const bad = await run(page, "filter_listing", { category_path: CATEGORY, size: 50 });
    expect(bad.ok).toBe(false);
    await runAway(page, "filter_listing", { category_path: CATEGORY, page: 2 });
    const done = await carried(page, /[?&]page=2/);
    expect(String(done.detail)).toMatch(/^page 2 of \d+; /);
  });

  test("a curated list (/busqueda?productos=…) is a listing", async ({ page }) => {
    await serveSite(page);
    await open(page, "/busqueda?productos=57695,58436&size=12&sort=sugeridos");
    expect((await page.evaluate(() => window.voqalizePcfactory!.context())).kind).toBe("category");
    await listen(page);
    const shown = await waitForEvent(page, "listing.shown");
    expect(shown.payload.path).toBe("/busqueda?productos=57695,58436");
  });
});

test.describe("the menu and the product page's windows", () => {
  test("menu.open opens Categorías on a category's panel, ringed; the next move closes it", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    const result = await run(page, "menu.open", ["computadores"]);
    expect(result.detail, result.error).toBe("opened Categorías on Computadores y Tablets: Notebooks, Tablets y eReaders");
    const none = await run(page, "menu.open", ["Juguetes"]);
    expect(none.ok).toBe(false);
    expect(none.result!.refused![0]!.options).toContain("Partes y Piezas / Componentes");
    await run(page, "page.show", ["Cupones"]);
    expect(await page.locator("#categories-dropdown.show").count()).toBe(0);
  });

  test("product.tab zoom, pickup and price_note: the gallery's photos, the pickup window, the ⓘ's words", async ({ page }) => {
    await serveSite(page);
    await open(page, PRODUCT);
    const zoom = await run(page, "product.tab", ["zoom"]);
    expect(zoom.detail, zoom.error).toBe("opened the big photos (3 photos) and stepped through 3; left open for the visitor");
    const pickup = await run(page, "product.tab", ["pickup"]);
    expect(await page.locator("#gallery-modal.show").count()).toBe(0);
    expect(pickup.detail, pickup.error).toBe("opened Disponibilidad de retiro en tienda: 2 stores have it (La Serena 1, Mall Plaza Vespucio 3); left open for the visitor");
    const note = await run(page, "product.tab", ["price_note"]);
    expect(note.detail, note.error).toBe('the store says of Transferencia / Débito: "Aplica cuando la compra es pagada en efectivo, depósito, débito o transferencia."');
  });
});

test.describe("what stays the visitor's", () => {
  test("Copiar código, Usar mi ubicación actual and the order tracking form are never pressed", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    const why = await page.evaluate(() => {
      const t = (window as unknown as { __voqalizeTest: Record<string, (x: unknown) => unknown> }).__voqalizeTest;
      const copy = document.querySelector(".ticket-cupon-boton") ?? Object.assign(document.createElement("button"), { className: "ticket-cupon-boton", textContent: "Copiar código" });
      const where = Object.assign(document.createElement("button"), { className: "pcf-link-btn", textContent: "Usar mi ubicación actual" });
      const rut = Object.assign(document.createElement("input"), { id: "rut-purchase" });
      document.body.append(where, rut);
      return { copy: t.intoCheckout!(copy), where: t.intoCheckout!(where), rut: t.intoCheckout!(rut) };
    });
    expect(why.copy).toMatch(/visitor's own/);
    expect(why.where).toMatch(/visitor's own/);
    expect(why.rut).toMatch(/visitor's own/);
  });
});

test.describe("the cart", () => {
  test("commerce.cart_add from a card, twice: the window closed between presses; cart.changed by him", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    await listen(page);
    const result = await run(page, "commerce.cart_add", { path: "/producto/57695", qty: 2 });
    expect(result.ok, result.error).toBe(true);
    expect(result.detail).toMatch(/^added 2 x /);
    expect(page.url()).toContain(CATEGORY);
    const changed = await waitForEvent(page, "cart.changed", (e) => (e.payload.count as number) === 2);
    expect(changed.by).toBe("agent");
    // The confirmation is left up a moment, then closed with Seguir comprando.
    await expect(page.locator("#pcf-modal-added-product.show")).toHaveCount(0, { timeout: 10_000 });
  });

  test("commerce.cart_add on the product page, three: Agregar al carro, then the page's own +", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    await runAway(page, "commerce.cart_add", { path: "/producto/8941", qty: 3 });
    const done = await carried(page, "/producto/8941");
    expect(done.outcome, String(done.detail)).toBe("applied");
    expect(String(done.detail)).toMatch(/^added 3 x Cable USB 2\.0 A\/A 1\.8m Extensión \(the cart line now has 3\); the cart has 3 items, \$4470 by transferencia$/);
    expect(await page.evaluate(() => localStorage.getItem("cartProducts"))).toBe('{"items":[{"id":8941,"cantidad":3,"origin":"PCF"}]}');
  });

  // Dev call 9ec9601a: the owner's Chrome had translated the product page, its
  // "Agregar al carro" read "Add to cart", and the move, matching the Spanish
  // words, found no button: 14 s, then "added 0, but the page shows no + for
  // more". The visitor then added it himself with the same button.
  test("commerce.cart_add on a product page Chrome translated: the button is found by what it is, and kept from the translator", async ({ page }) => {
    await serveSite(page);
    await open(page, PRODUCT);
    await listen(page);
    const kept = await page.evaluate(() => [...document.querySelectorAll("#product-detail button.pcf-btn--five")].map((b) => b.getAttribute("translate")));
    expect(kept.length).toBeGreaterThan(0);
    expect(kept.every((t) => t === "no")).toBe(true);
    // The translator, as it rewrites a button it was not kept from.
    await page.evaluate(() => {
      for (const b of document.querySelectorAll("#product-detail button.pcf-btn--five")) {
        for (const n of [...b.childNodes]) if (n.nodeType === Node.TEXT_NODE && /agregar/i.test(n.textContent ?? "")) n.remove();
        b.insertAdjacentHTML("beforeend", '<font style="vertical-align: inherit;"><font style="vertical-align: inherit;">Add to cart</font></font>');
      }
    });
    const result = await run(page, "commerce.cart_add", { path: PRODUCT, qty: 1 });
    expect(result.ok, result.error).toBe(true);
    expect(result.detail).toMatch(/^added 1 x Notebook Gamer LOQe/);
    expect(await page.evaluate(() => localStorage.getItem("cartProducts"))).toBe('{"items":[{"id":57233,"cantidad":1,"origin":"PCF"}]}');
    const changed = await waitForEvent(page, "cart.changed", (e) => e.payload.count === 1);
    expect(changed.by).toBe("agent");
  });

  test("commerce.cart_add on a product page with no Agregar al carro says so, not 'no + for more'", async ({ page }) => {
    await serveSite(page);
    await open(page, PRODUCT);
    await page.evaluate(() => document.querySelectorAll("#product-detail button.pcf-btn--five").forEach((b) => b.remove()));
    const result = await run(page, "commerce.cart_add", { path: PRODUCT, qty: 1 });
    expect(result.ok).toBe(false);
    expect(result.error).toMatch(/shows no Agregar al carro .*nothing was added/);
    expect(result.error).not.toMatch(/no \+ for more/);
  });

  test("commerce.cart_add on /comparador presses that column's own Agregar al carro, once per unit, and stays there", async ({ page }) => {
    await serveSite(page);
    await open(page, "/comparador?prod1=57695&prod2=58436");
    await listen(page);
    const result = await run(page, "commerce.cart_add", { path: "/producto/58436", qty: 2 });
    expect(result.ok, result.error).toBe(true);
    expect(result.detail).toMatch(/^added 2 x /);
    expect(result.moved).toBeFalsy();
    expect(page.url()).toBe(`${ORIGIN}/comparador?prod1=57695&prod2=58436`);
    expect(await page.evaluate(() => localStorage.getItem("cartProducts"))).toBe('{"items":[{"id":58436,"cantidad":2,"origin":"PCF"}]}');
    const changed = await waitForEvent(page, "cart.changed", (e) => e.payload.count === 2);
    expect(changed.by).toBe("agent");
  });

  test("commerce.cart_show: closes the Producto agregado window, and opens /carro", async ({ page }) => {
    await serveSite(page, { cart: [{ id: 8941, cantidad: 1 }] });
    await open(page, CATEGORY);
    await page.evaluate(() => {
      const m = document.querySelector<HTMLElement>("#pcf-modal-added-product")!;
      m.classList.add("show");
      m.style.display = "block";
    });
    expect((await run(page, "commerce.cart_show", { open: false })).detail).toBe("closed the Producto agregado window");
    await runAway(page, "commerce.cart_show", { open: true });
    const done = await carried(page, "/carro");
    expect(done.detail).toBe("the cart is on screen; the cart has 1 item, $1490 by transferencia: 1 × Cable USB 2.0 A/A 1.8m Extensión");
  });

  test("commerce.cart_update: + to 3, then Eliminar and its confirmation; a line not in the cart is refused", async ({ page }) => {
    await serveSite(page, { cart: [{ id: 8941, cantidad: 1 }] });
    await open(page, "/carro");
    await listen(page);
    const up = await run(page, "commerce.cart_update", { path: "/producto/8941", qty: 3 });
    expect(up.detail, up.error).toBe("Cable USB 2.0 A/A 1.8m Extensión set to 3; the cart has 3 items, $1490 by transferencia");
    const missing = await run(page, "commerce.cart_update", { path: PRODUCT, qty: 1 });
    expect(missing.ok).toBe(false);
    expect(missing.result!.refused![0]!.options).toEqual(["Cable USB 2.0 A/A 1.8m Extensión (/producto/8941)"]);
    const gone = await run(page, "commerce.cart_update", { path: "/producto/8941", qty: 0 });
    expect(gone.detail).toMatch(/^removed Cable USB 2\.0 A\/A 1\.8m Extensión; the cart has 0 items/);
    expect(await page.evaluate(() => localStorage.getItem("cartProducts"))).toBe('{"items":[]}');
  });

  test("apply_coupon types the code, presses Aplicar and reports what the store says", async ({ page }) => {
    await serveSite(page, { cart: [{ id: 8941, cantidad: 1 }] });
    await open(page, "/carro");
    const result = await run(page, "apply_coupon", { code: "len50" });
    expect(result.detail, result.error).toBe('pressed Aplicar for LEN50; the store says: "Cupón inválido."; total transferencia $1490');
    expect(await page.inputValue("input.cupon-input")).toBe("LEN50");
  });
});

test.describe("the checkout, as far as Tipo de entrega", () => {
  test("start_checkout: Continuar, then Continuar como invitado, then stops on Tipo de entrega with its options", async ({ page }) => {
    await serveSite(page, { cart: [{ id: 8941, cantidad: 1 }] });
    await open(page, "/carro");
    await runAway(page, "start_checkout", {});
    await page.waitForURL(`${ORIGIN}/checkout`, { waitUntil: "domcontentloaded" });
    const done = await carried(page, "/checkout/tipo-entrega");
    expect(done.move).toBe("start_checkout");
    expect(done.detail).toBe(
      "on Tipo de entrega as a guest; the visitor chooses: Retiro en tienda (Gratis) or Despacho a Domicilio. Javier stops here: the choice, the RUT, the address and the payment are theirs",
    );
    const state = await waitForEvent(page, "checkout.changed");
    expect(state.payload).toEqual({ step: "delivery", options: ["Retiro en tienda (Gratis)", "Despacho a Domicilio"], chosen: null });
    expect(await page.locator("#withdraw").isChecked()).toBe(false);
    expect(await page.locator("#dispatch").isChecked()).toBe(false);
  });

  test("the guard refuses the delivery choice, the login and every page past Tipo de entrega", async ({ page }) => {
    await serveSite(page);
    await open(page, "/checkout/tipo-entrega");
    const why = await page.evaluate(() => {
      const t = (window as unknown as { __voqalizeTest: Record<string, (x: unknown) => unknown> }).__voqalizeTest;
      const out: Record<string, unknown> = {};
      for (const sel of ["#withdraw", "#dispatch", "label[for=withdraw]", "input[name=store]"]) {
        const el = document.querySelector(sel);
        if (el) out[sel] = t.intoCheckout!(el);
      }
      for (const path of ["/checkout/pago", "/checkout/tipo-entrega", "/login", "/mi-cuenta", "/mis-compras", "/centro-de-ayuda/precios-y-medios-de-pago"]) out[path] = t.forbiddenPath!(path);
      try {
        t.target!("https://auth.pcfactory.cl/auth/realms/PCFactory");
      } catch (e) {
        out.auth = (e as Error).message;
      }
      return out;
    });
    expect(why["#withdraw"]).toMatch(/delivery choice/);
    expect(why["#dispatch"]).toMatch(/delivery choice/);
    expect(why["label[for=withdraw]"]).toMatch(/on the checkout/);
    expect(why["/checkout/pago"]).toBe(true);
    expect(why["/checkout/tipo-entrega"]).toBe(false);
    expect(why["/login"]).toBe(true);
    expect(why["/mi-cuenta"]).toBe(true);
    expect(why["/mis-compras"]).toBe(true);
    expect(why["/centro-de-ayuda/precios-y-medios-de-pago"]).toBe(false);
    expect(why.auth).toMatch(/not on www\.pcfactory\.cl/);
  });

  test("on /checkout only the guest button may be pressed; the login card is refused", async ({ page }) => {
    await serveSite(page);
    await open(page, "/checkout");
    const why = await page.evaluate(() => {
      const t = (window as unknown as { __voqalizeTest: Record<string, (x: unknown) => unknown> }).__voqalizeTest;
      const buttons = [...document.querySelectorAll(".identification button, .identification a")];
      return buttons.map((b) => [(b.textContent ?? "").trim(), t.intoCheckout!(b)]);
    });
    const byWords = Object.fromEntries(why as [string, unknown][]);
    expect(byWords["Continuar como invitado"]).toBeNull();
    expect(byWords["Inicia sesión"]).toBeTruthy();
    expect(byWords["Crear nueva cuenta"]).toBeTruthy();
  });

  test("the guard refuses a RUT or password field, and the header's login", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    const why = await page.evaluate(() => {
      const t = (window as unknown as { __voqalizeTest: Record<string, (x: unknown) => unknown> }).__voqalizeTest;
      const rut = document.createElement("input");
      rut.name = "rut";
      const pass = document.createElement("input");
      pass.type = "password";
      document.body.append(rut, pass);
      const login = document.querySelector("#login-dropdown");
      return { rut: t.privateField!(rut), pass: t.intoCheckout!(pass), login: login ? t.intoCheckout!(login) : "absent", search: t.privateField!(document.querySelector("#search-input-desktop")) };
    });
    expect(why.rut).toMatch(/visitor's to type/);
    expect(why.pass).toMatch(/password|login control/);
    expect(why.login).toMatch(/login control/);
    expect(why.search).toBeNull();
  });
});

test.describe("the page itself", () => {
  test("the ring is pcFactory's blue, and what the adapter matches is kept from the translator", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    await run(page, "page.show", ["Notebooks"]);
    const look = await page.evaluate(() => {
      const ring = document.querySelector("[data-voqalize=spotlight]")?.shadowRoot?.querySelector<HTMLElement>(".ring");
      return {
        ring: ring ? getComputedStyle(ring).borderTopColor : null,
        label: document.querySelector("#panel-filters label")?.getAttribute("translate"),
        name: document.querySelector("a.products__item h3")?.getAttribute("translate"),
      };
    });
    expect(look.ring).toBe("rgb(63, 89, 250)");
    expect(look.label).toBe("no");
    expect(look.name).toBe("no");
  });

  test("the assistance button hides while a call is on", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    const hidden = await page.evaluate(() => {
      const b = document.createElement("div");
      b.id = "pcfAssistanceWrapper";
      document.body.appendChild(b);
      document.documentElement.setAttribute("data-voqalize-call", "");
      return getComputedStyle(b).display;
    });
    expect(hidden).toBe("none");
  });

  test("a cart change the visitor makes is reported as theirs", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    await listen(page);
    await page.evaluate(() => localStorage.setItem("cartProducts", JSON.stringify({ items: [{ id: 8941, cantidad: 2, origin: "PCF" }] })));
    const changed = await waitForEvent(page, "cart.changed", (e) => e.payload.count === 2);
    expect(changed.by).toBe("visitor");
    expect(changed.payload).toEqual({ count: 2, subtotal: 2980, items: [{ path: "/producto/8941", name: "Cable USB 2.0 A/A 1.8m Extensión", qty: 2, price: 1490 }] });
  });

  test("every move in the scene has a performer", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    const ids = await page.evaluate(() => [...window.voqalizePcfactory!.commands]);
    expect(ids.sort()).toEqual(
      [
        "page.open", "page.show", "page.faq", "product.tab", "filter_listing", "open_product", "find_products", "check_prices", "check_stock",
        "stores.show", "compare.add", "compare.show", "compare.remove", "menu.open", "apply_coupon", "start_checkout",
        "commerce.filter", "commerce.sort", "commerce.search",
        "commerce.cart_add", "commerce.cart_update", "commerce.cart_show",
      ].sort(),
    );
    expect(named(await events(page), "nothing")).toEqual([]);
  });
});
