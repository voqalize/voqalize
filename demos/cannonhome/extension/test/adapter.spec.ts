/**
 * The Cannon Home adapter, end to end against trimmed copies of the shop's
 * pages (see site.ts): each Action the brain sends, the events the page
 * answers with, the moves that survive a full page load, and the guard that
 * keeps every click out of checkout.
 */

import { expect, type Page, test } from "@playwright/test";

import { type BagLine, CART_SECTION, CATEGORY, type Emitted, events, listen, open, ORIGIN, PRODUCT, run, serveSite, waitForEvent } from "./site";

/** `run` for a move that loads another page: the page may go before it answers. */
async function runAway(p: Page, command: string, payload: unknown): Promise<void> {
  await run(p, command, payload).catch((error: Error) => {
    if (!/context was destroyed|navigat/i.test(error.message)) throw error;
  });
}

const named = (list: Emitted[], name: string) => list.filter((e) => e.event === name);

test.describe("context() and page_changed", () => {
  for (const [path, kind] of [
    ["/", "home"],
    [CATEGORY, "category"],
    ["/catalogsearch/result/?q=toalla+blanca", "search"],
    [PRODUCT, "product"],
    ["/checkout/cart/", "cart"],
  ] as const) {
    test(`${path} is a ${kind} page`, async ({ page }) => {
      await serveSite(page);
      await open(page, path);
      const ctx = await page.evaluate(() => window.voqalizeCannonhome!.context());
      expect(ctx.kind).toBe(kind);
      expect(ctx.path).toBe(new URL(path, ORIGIN).pathname);
      expect(ctx.site).toBe("site");
      await listen(page);
      const first = (await events(page))[0];
      expect(first.event).toBe("page_changed");
      expect(first.payload.kind).toBe(kind);
    });
  }

  test("headings come from the main column, not the header or footer", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    const ctx = await page.evaluate(() => window.voqalizeCannonhome!.context());
    expect(ctx.headings[0]).toBe("Sábanas");
    expect(ctx.headings.length).toBeLessThanOrEqual(80);
  });
});

test.describe("search_products", () => {
  test("types the query at a visitor's pace and reports the dropdown", async ({ page }) => {
    const seen = await serveSite(page);
    await open(page, "/");
    await listen(page);
    const result = await run(page, "search_products", { query: "sabanas king", open_index: null });
    expect(result.ok, result.error).toBe(true);
    expect(result.detail).toContain('typed "sabanas king"');
    expect(await page.inputValue("input.amsearch-input")).toBe("sabanas king");
    // One request per pause, as Amasty makes it, not one per key.
    expect(seen.autocomplete).toContain("sabanas king");
    const suggest = await waitForEvent(page, "search_suggest");
    const items = suggest.payload.items as { name: string; path: string; price: number }[];
    expect(suggest.payload.query).toBe("sabanas king");
    expect(items).toHaveLength(6);
    expect(items[0]).toEqual({ name: "Sábanas King 200 Hilos Sunflower", path: "/sabanas-king-200-hilos-sunflower.html", price: 32495 });
    expect(suggest.payload.categories).toEqual(["Sale Cannon Home > Sábanas Sale", "Ropa de Cama > Sábanas"]);
    // No Enter: the page did not load the results.
    expect(page.url()).toBe(`${ORIGIN}/`);
  });

  test("with open_index, opens that product and finishes there", async ({ page }) => {
    await serveSite(page);
    await open(page, "/");
    await runAway(page, "search_products", { query: "sabanas king", open_index: 2 });
    await page.waitForURL(`${ORIGIN}/sabanas-king-200-hilos-stone.html`);
    await listen(page);
    const done = await waitForEvent(page, "command_done");
    expect(done.payload.command).toBe("search_products");
    await waitForEvent(page, "product_shown");
  });

  test("a query with no dropdown fails, and says so", async ({ page }) => {
    await serveSite(page);
    await page.route(`${ORIGIN}/amasty_xsearch/**`, (route) => route.fulfill({ status: 200, body: "" }));
    await open(page, "/");
    const result = await run(page, "search_products", { query: "zzz", open_index: null });
    expect(result.ok).toBe(false);
    expect(result.error).toContain("no products");
  });
});

test.describe("filter_listing", () => {
  test("applies the pills by request variable and option title, waits for each grid, and sorts", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    await listen(page);
    const result = await run(page, "filter_listing", {
      category_path: CATEGORY, size: "2 plazas", color: "blanco", threads: null, material: null, sort: "price_asc",
    });
    expect(result.ok, result.error).toBe(true);
    expect(result.detail).toContain("applied size 2 Plazas, color Blanco, sorted price_asc");
    await expect(page.locator('.qf__group[data-qf-request-var="tamano"] a.qf__option-link.-active')).toHaveAttribute("title", "2 Plazas");
    await expect(page.locator('.qf__group[data-qf-request-var="color"] a.qf__option-link.-active')).toHaveAttribute("title", "Blanco");
    expect(await page.inputValue("select#sorter")).toBe("price_asc");
    // Amasty pushes the filter's address; the page is reported again.
    expect(page.url()).toContain("product_list_order=price_asc");
    const listings = named(await events(page), "listing_shown");
    const last = listings[listings.length - 1].payload;
    expect(last.filters).toEqual({ tamano: "2 Plazas", color: "Blanco" });
    expect(last.sort).toBe("price_asc");
    expect(last.items).toEqual([
      { name: "Sábanas 2 Plazas 300 Hilos Liso Blanco", path: "/sabanas-2-plaza-300-hilos-liso-1.html", price: 55990, regular_price: 79990 },
    ]);
    expect(last.count).toBe(30);
    expect(named(await events(page), "page_changed").length).toBeGreaterThan(1);
  });

  test("threads match '300' to the option '300 hilos'", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    const result = await run(page, "filter_listing", { category_path: CATEGORY, size: null, color: null, threads: "300", material: null, sort: null });
    expect(result.ok, result.error).toBe(true);
    await expect(page.locator('.qf__group[data-qf-request-var="hilos"] a.qf__option-link.-active')).toHaveAttribute("title", "300 hilos");
  });

  test("an option the listing does not offer fails with the ones it does", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    const result = await run(page, "filter_listing", { category_path: CATEGORY, size: "cuna", color: null, threads: null, material: null, sort: null });
    expect(result.ok).toBe(false);
    expect(result.error).toContain('no size "cuna"');
    expect(result.error).toContain("King");
  });

  test("from another page, loads the category and finishes there (the move survives the load)", async ({ page }) => {
    const seen = await serveSite(page);
    await open(page, "/");
    await runAway(page, "filter_listing", { category_path: CATEGORY, size: "King", color: null, threads: null, material: null, sort: null });
    await page.waitForURL(/20-sabanas/);
    await listen(page);
    const done = await waitForEvent(page, "command_done");
    expect(done.payload.command).toBe("filter_listing");
    expect(String(done.payload.detail)).toContain("applied size King");
    expect(seen.pages).toContain(CATEGORY);
    await expect(page.locator('.qf__group[data-qf-request-var="tamano"] a.qf__option-link.-active')).toHaveAttribute("title", "King");
  });
});

test.describe("listing_shown after the visitor's own filtering", () => {
  test("a grid swap the visitor made is reported", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    await listen(page);
    await waitForEvent(page, "listing_shown");
    await page.evaluate(() => (document.querySelector('.qf__group[data-qf-request-var="color"] a.qf__option-link[title="Rosa"]') as HTMLElement).click());
    const swapped = await waitForEvent(page, "listing_shown", (e) => (e.payload.filters as Record<string, string>).color === "Rosa");
    expect((swapped.payload.items as { name: string }[]).map((i) => i.name)).toEqual(["Sábanas 2 Plazas 300 Hilos Liso Rosado"]);
  });
});

test.describe("open_product", () => {
  test("reads the page at once, then confirms by one POST /graphql", async ({ page }) => {
    const seen = await serveSite(page);
    // The live read takes a moment, as it does over the network.
    await page.route(`${ORIGIN}/graphql`, async (route) => {
      await new Promise((r) => setTimeout(r, 1500));
      await route.fallback();
    });
    await open(page, PRODUCT);
    await listen(page);
    const fromPage = await waitForEvent(page, "product_shown", (e) => e.payload.source === "page");
    expect(fromPage.payload).toMatchObject({ price: 55993, regular_price: 79990, in_stock: true, qty: 69, sku: "JSRSBH003P20Z" });
    const live = await waitForEvent(page, "product_shown", (e) => e.payload.source === "graphql");
    const order = named(await events(page), "product_shown").map((e) => e.payload.source);
    expect(order).toEqual(["page", "graphql"]);
    expect(live.payload).toMatchObject({
      path: PRODUCT, sku: "JSRSBH003P20Z", name: "Sábanas 2 Plazas 300 Hilos Liso Fog",
      price: 49990, regular_price: 79990, in_stock: true, qty: 69, rating: 4.7, reviews: 17, source: "graphql",
    });
    expect((live.payload.specs as Record<string, string>)["Hilos"]).toBe("300 hilos");
    expect((live.payload.specs as Record<string, string>)["Color"]).toBe("Gris / Blanco");
    expect(seen.graphql.every((g) => g.method === "POST")).toBe(true);
    expect(seen.graphql.filter((g) => /route/.test(g.query))).toHaveLength(1);
  });

  test("opens the Especificaciones tab", async ({ page }) => {
    await serveSite(page);
    await open(page, PRODUCT);
    const result = await run(page, "open_product", { path: PRODUCT, tab: "especificaciones" });
    expect(result.ok, result.error).toBe(true);
    expect(result.detail).toContain("opened the especificaciones tab");
    await expect(page.locator('[id="product.attributes"]')).toBeVisible();
    await expect(page.locator("#product-attribute-specs-table")).toBeVisible();
  });

  test("steps the gallery for fotos", async ({ page }) => {
    await serveSite(page);
    await open(page, PRODUCT);
    await page.evaluate(() => {
      (window as unknown as { __thumbs: number }).__thumbs = 0;
      document.querySelectorAll(".fotorama__nav__frame").forEach((f) => f.addEventListener("click", () => (window as unknown as { __thumbs: number }).__thumbs++));
    });
    const result = await run(page, "open_product", { path: PRODUCT, tab: "fotos" });
    expect(result.ok, result.error).toBe(true);
    expect(await page.evaluate(() => (window as unknown as { __thumbs: number }).__thumbs)).toBe(3);
  });

  test("from a listing, loads the product and finishes there (the move survives the load)", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    await runAway(page, "open_product", { path: "sabanas-2-plazas-300-hilos-liso-fog", tab: "calificaciones" });
    await page.waitForURL(`${ORIGIN}${PRODUCT}`);
    await listen(page);
    const done = await waitForEvent(page, "command_done");
    expect(done.payload).toMatchObject({ command: "open_product" });
    expect(String(done.payload.detail)).toContain("calificaciones");
    await waitForEvent(page, "product_shown");
  });
});

test.describe("check_prices", () => {
  test("one POST for products, route() for the ones it hides, and the rest missing", async ({ page }) => {
    const seen = await serveSite(page);
    await open(page, CATEGORY);
    await listen(page);
    const result = await run(page, "check_prices", {
      paths: ["/sabanas-2-plazas-300-hilos-liso-sand.html", "/funda-plumon-king-stone-washed-taupe.html", "/no-existe.html"],
    });
    expect(result.ok, result.error).toBe(true);
    const read = await waitForEvent(page, "prices_read");
    expect(read.payload.items).toEqual([
      { path: "/sabanas-2-plazas-300-hilos-liso-sand.html", sku: "JSRSBH003P20S", name: "Sábanas 2 Plazas 300 Hilos Liso Sand", price: 55993, regular_price: 79990, in_stock: true, qty: null },
      { path: "/funda-plumon-king-stone-washed-taupe.html", sku: "FPKSWT", name: "Funda Plumón King Stone Washed Taupe", price: 39990, regular_price: null, in_stock: false, qty: 0 },
    ]);
    expect(read.payload.missing).toEqual(["/no-existe.html"]);
    const posts = seen.graphql.filter((g) => g.method === "POST");
    expect(posts).toHaveLength(2);
    expect(posts[0].query).toContain("products(filter: { url_key: { in: $keys } }");
    expect(posts[1].variables).toEqual({ u0: "funda-plumon-king-stone-washed-taupe.html", u1: "no-existe.html" });
    // It moves nothing.
    expect(page.url()).toBe(`${ORIGIN}${CATEGORY}`);
  });
});

test.describe("add_to_cart and show_cart", () => {
  test("sets the quantity with + and presses Agregar; reports the bag", async ({ page }) => {
    const seen = await serveSite(page);
    await open(page, PRODUCT);
    await listen(page);
    const result = await run(page, "add_to_cart", { path: PRODUCT, qty: 2 });
    expect(result.ok, result.error).toBe(true);
    expect(await page.inputValue("#qty")).toBe("2");
    await expect(page.locator("aside.content-minicart-modal")).toHaveClass(/_show/);
    const cart = await waitForEvent(page, "cart_state");
    expect(cart.payload).toEqual({
      items: [{ name: "Sábanas 2 Plazas 300 Hilos Liso Fog", path: PRODUCT, qty: 2, price: 55993 }],
      count: 2,
      subtotal: 111986,
      free_shipping_left: 38014,
    });
    expect(seen.sections).toBeGreaterThan(0);
    expect(result.detail).toContain("added 2 × Sábanas 2 Plazas 300 Hilos Liso Fog");
    expect(result.detail).toContain("$38014 short of free shipping");
  });

  test("from another page, opens the product first and adds there", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    await runAway(page, "add_to_cart", { path: PRODUCT, qty: 1 });
    await page.waitForURL(`${ORIGIN}${PRODUCT}`);
    await listen(page);
    const done = await waitForEvent(page, "command_done");
    expect(done.payload.command).toBe("add_to_cart");
    await waitForEvent(page, "cart_state");
  });

  test("a quantity out of 1–10 is refused and nothing is pressed", async ({ page }) => {
    await serveSite(page);
    await open(page, PRODUCT);
    const result = await run(page, "add_to_cart", { path: PRODUCT, qty: 12 });
    expect(result.ok).toBe(false);
    await expect(page.locator("aside.content-minicart-modal")).not.toHaveClass(/_show/);
  });

  test("with the cart section unreachable, the bag is read from the drawer", async ({ page }) => {
    await serveSite(page);
    await page.route(`${ORIGIN}/customer/section/load/**`, (route) => route.fulfill({ status: 500, body: "" }));
    await open(page, PRODUCT);
    await listen(page);
    const opened = await run(page, "show_cart", { open: true });
    expect(opened.ok, opened.error).toBe(true);
    const cart = await waitForEvent(page, "cart_state");
    expect(cart.payload).toEqual({
      items: [{ name: "Almohada Viscoelástica Ergo 50x70 cm", path: "/almohada-viscoelastica-ergo-50x70-cm.html", qty: 1, price: 29990 }],
      count: 1,
      subtotal: 29990,
      free_shipping_left: 120010,
    });
  });

  test("show_cart opens the drawer, reports the bag, and closes it", async ({ page }) => {
    await serveSite(page);
    await open(page, PRODUCT);
    await listen(page);
    const opened = await run(page, "show_cart", { open: true });
    expect(opened.ok, opened.error).toBe(true);
    await expect(page.locator("aside.content-minicart-modal")).toHaveClass(/_show/);
    const cart = await waitForEvent(page, "cart_state");
    expect(cart.payload.count).toBe(CART_SECTION.cart.summary_count);
    const closed = await run(page, "show_cart", { open: false });
    expect(closed.ok, closed.error).toBe(true);
    await expect(page.locator("aside.content-minicart-modal")).not.toHaveClass(/_show/);
  });
});

test.describe("never past the delivery form", () => {
  test("the guard refuses Finalizar compra and checkout links, allows the bag and the bag page's Terminar pedido", async ({ page }) => {
    await serveSite(page);
    await open(page, PRODUCT);
    const onProduct = await page.evaluate(() => {
      const t = (window as unknown as { __voqalizeTest: { press(el: Element): void; intoCheckout(el: Element): string | null } }).__voqalizeTest;
      const tryPress = (sel: string) => {
        const el = document.querySelector(sel);
        if (!el) return `missing ${sel}`;
        try {
          t.press(el);
          return "pressed";
        } catch (error) {
          return String((error as Error).message);
        }
      };
      const link = document.createElement("a");
      link.href = "/checkout/";
      link.textContent = "Continuar";
      document.body.appendChild(link);
      const english = document.createElement("button");
      english.textContent = "Proceed to checkout";
      document.body.appendChild(english);
      return {
        finalizar: tryPress("#top-cart-btn-checkout"),
        link: tryPress("a[href='/checkout/']"),
        english: t.intoCheckout(english),
        close: t.intoCheckout(document.querySelector(".mc-header__close")!),
        bag: t.intoCheckout(document.querySelector(".minicart-wrapper a.action.showcart")!),
        agregar: t.intoCheckout(document.querySelector("#product-addtocart-button")!),
      };
    });
    expect(onProduct.finalizar).toMatch(/^refused to press it/);
    expect(onProduct.link).toMatch(/^refused to press it: it links to \/checkout\//);
    expect(onProduct.english).not.toBeNull();
    expect(onProduct.close).toBeNull();
    expect(onProduct.bag).toBeNull();
    expect(onProduct.agregar).toBeNull();
    expect(page.url()).toBe(`${ORIGIN}${PRODUCT}`);

    await open(page, "/checkout/cart/");
    const onCart = await page.evaluate(() => {
      const t = (window as unknown as { __voqalizeTest: { press(el: Element): void; forbiddenPath(p: string): boolean } }).__voqalizeTest;
      let pressed = "pressed";
      try {
        t.press(document.querySelector("[data-role=proceed-to-checkout]")!);
      } catch (error) {
        pressed = String((error as Error).message);
      }
      return {
        pressed,
        paths: ["/checkout/", "/checkout", "/checkout/cart/", "/checkout/cart/add/uenc/x/product/1/", "/customer/account/login/", "/onestepcheckout/"].map(
          (p) => [p, t.forbiddenPath(p)],
        ),
      };
    });
    // "Terminar pedido" on the bag page opens the login window, nothing more.
    expect(onCart.pressed).toBe("pressed");
    expect(Object.fromEntries(onCart.paths)).toEqual({
      "/checkout/": false,
      "/checkout": false,
      "/checkout/cart/": false,
      "/checkout/cart/add/uenc/x/product/1/": false,
      "/customer/account/login/": true,
      "/onestepcheckout/": true,
    });
    expect(page.url()).toBe(`${ORIGIN}/checkout/cart/`);
  });

  test("no move loads checkout past the delivery form, even when asked", async ({ page }) => {
    await serveSite(page);
    await open(page, PRODUCT);
    for (const path of ["/checkout/onepage/success/", "/checkout#payment", "/customer/account/login/", "/webpay/return/"]) {
      const nav = await run(page, "navigate", { path });
      expect(nav.ok, path).toBe(false);
      expect(nav.error, path).toContain("never goes into checkout");
    }
    const product = await run(page, "open_product", { path: "/checkout/index.html", tab: null });
    expect(product.ok).toBe(false);
    expect(page.url()).toBe(`${ORIGIN}${PRODUCT}`);
  });
});

test.describe("one move at a time", () => {
  test("a second move waits for the first one's grid", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    await listen(page);
    await waitForEvent(page, "listing_shown");
    await page.evaluate(() => {
      const w = window as unknown as { __order: string[] };
      w.__order = [];
      const a = window.voqalizeCannonhome!;
      void a.run("filter_listing", { category_path: "/12-ropa-de-cama/20-sabanas", size: "King", color: null, threads: null, material: null, sort: null }).then(() => w.__order.push("filter"));
      void a.run("check_prices", { paths: ["/sabanas-2-plazas-300-hilos-liso-sand.html"] }).then(() => w.__order.push("prices"));
    });
    await page.waitForFunction(() => (window as unknown as { __order: string[] }).__order.length === 2, null, { timeout: 20_000 });
    expect(await page.evaluate(() => (window as unknown as { __order: string[] }).__order)).toEqual(["filter", "prices"]);
  });
});

test.describe("translation anchors", () => {
  test("what the adapter matches on is marked translate=no", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    for (const sel of ["h1.page-title", ".qf__group", "a.qf__option-link", "a.product-item-link", ".toolbar-amount"]) {
      await expect(page.locator(sel).first()).toHaveAttribute("translate", "no");
    }
    await open(page, PRODUCT);
    for (const sel of ["h1.product-name", "#product-attribute-specs-table", '[id="tab-label-product.attributes"]']) {
      await expect(page.locator(sel).first()).toHaveAttribute("translate", "no");
    }
  });
});

// ─── As the live site behaves (found by the live smoke run, 2026-10-22) ───

/** GoPersonal's timing, slowed so that the products for "sab…" are still up
 *  when the adapter first looks after typing (1.2 s), then the dropdown
 *  empties, then the whole query's products come. */
const GP_TIMING = { debounceMs: 1400, loadingMs: 800 };

const GP_ITEMS = [
  { name: "Sábanas King 300 Hilos Sage", path: "/sabanas-king-300-hilos-sage.html", price: 62990 },
  { name: "Sábanas Súper King 300 Hilos Sage", path: "/sabanas-super-king-300-hilos-sage.html", price: 69993 },
  { name: "Set 2 Toallas Bordada Merida Blanco", path: "/set-2-toallas-bordada-merida-blanco.html", price: 8990 },
  { name: "Sábanas 2 Plazas 300 Hilos Gris", path: "/sabanas-2-plazas-300-hilos-gris.html", price: 55993 },
];

test.describe("search_products on GoPersonal's dropdown", () => {
  test("reads GoPersonal's cards and categories, not Amasty's hidden dropdown", async ({ page }) => {
    const seen = await serveSite(page, { goPersonal: GP_TIMING });
    await open(page, "/");
    await listen(page);
    const result = await run(page, "search_products", { query: "sabanas 300 hilos", open_index: null });
    expect(result.ok, result.error).toBe(true);
    // Amasty filled its own dropdown too, which the page hides.
    expect(seen.autocomplete).toContain("sabanas 300 hilos");
    expect(seen.goPersonal).toContain("sabanas 300 hilos");
    const suggests = named(await events(page), "search_suggest");
    const last = suggests[suggests.length - 1].payload;
    expect(last.items).toEqual(GP_ITEMS);
    expect(last.categories).toEqual(["Juego de sábanas", "Toallas de baño"]);
    expect(result.detail).toContain("the dropdown shows 4 products: Sábanas King 300 Hilos Sage ($62990)");
    expect(result.detail).toContain("Set 2 Toallas Bordada Merida Blanco ($8990)");
  });

  test("survives the products for what was typed so far, then the empty dropdown, then the query's", async ({ page }) => {
    await serveSite(page, { goPersonal: GP_TIMING });
    await open(page, "/");
    await listen(page);
    // What the dropdown shows, every 100 ms, while the move runs.
    await page.evaluate(() => {
      const w = window as unknown as { __shown: string[] };
      w.__shown = [];
      const tick = setInterval(() => {
        if (!w.__shown.length && !document.querySelector("#gp-ac-dropdown.open")) return;
        const names = [...document.querySelectorAll("#gp-ac-dropdown.open .gp-ac-product-name")].map((n) => n.textContent ?? "");
        const now = names.length ? names[0] : "(empty)";
        if (w.__shown[w.__shown.length - 1] !== now) w.__shown.push(now);
      }, 100);
      setTimeout(() => clearInterval(tick), 15_000);
    });
    const result = await run(page, "search_products", { query: "sabanas 300 hilos", open_index: null });
    expect(result.ok, result.error).toBe(true);
    const shown = await page.evaluate(() => (window as unknown as { __shown: string[] }).__shown);
    expect(shown).toEqual(["Sábana de Baño Aqua", "(empty)", "Sábanas King 300 Hilos Sage"]);
    expect(result.detail).not.toContain("Aqua");
    // Nothing reported the partial dropdown, neither the move nor the watcher.
    for (const s of named(await events(page), "search_suggest")) {
      expect((s.payload.items as { name: string }[]).map((i) => i.name)).not.toContain("Sábana de Baño Aqua");
    }
  });

  test("with open_index, opens that GoPersonal card's product, without its tracking query", async ({ page }) => {
    const seen = await serveSite(page, { goPersonal: GP_TIMING });
    await open(page, "/");
    await runAway(page, "search_products", { query: "sabanas 300 hilos", open_index: 1 });
    await page.waitForURL(`${ORIGIN}/sabanas-super-king-300-hilos-sage.html`);
    await listen(page);
    const done = await waitForEvent(page, "command_done");
    expect(done.payload.command).toBe("search_products");
    await waitForEvent(page, "product_shown");
    expect(seen.pages).toContain("/sabanas-super-king-300-hilos-sage.html");
  });
});

test.describe("never into checkout, by Magento's /index.php/ routes", () => {
  test("the guard refuses pressing /index.php/checkout/ and loading /index.php/customer/account/login/, and allows the bag", async ({ page }) => {
    await serveSite(page);
    await open(page, PRODUCT);
    const got = await page.evaluate(() => {
      const t = (window as unknown as { __voqalizeTest: { press(el: Element): void; forbiddenPath(p: string): boolean } }).__voqalizeTest;
      const link = document.createElement("a");
      link.href = "/index.php/checkout/";
      link.textContent = "Continuar";
      document.body.appendChild(link);
      let pressed = "pressed";
      try {
        t.press(link);
      } catch (error) {
        pressed = String((error as Error).message);
      }
      return {
        pressed,
        paths: Object.fromEntries(
          ["/index.php/checkout/", "/index.php/checkout", "/INDEX.PHP/checkout/onepage/", "/index.php/checkout/onepage/success/", "/index.php/customer/account/login/", "/index.php/checkout/cart/", "/index.php"].map((p) => [
            p,
            t.forbiddenPath(p),
          ]),
        ),
      };
    });
    expect(got.pressed).toMatch(/^refused to press it: it links to \/index\.php\/checkout\//);
    expect(got.paths).toEqual({
      // The checkout's one page is the delivery form: loadable; past it, not.
      "/index.php/checkout/": false,
      "/index.php/checkout": false,
      "/INDEX.PHP/checkout/onepage/": true,
      "/index.php/checkout/onepage/success/": true,
      "/index.php/customer/account/login/": true,
      "/index.php/checkout/cart/": false,
      "/index.php": false,
    });
    for (const path of ["/index.php/checkout/onepage/success/", "/index.php/customer/account/login/"]) {
      const nav = await run(page, "navigate", { path });
      expect(nav.ok, path).toBe(false);
      expect(nav.error).toContain("never goes into checkout");
    }
    expect(page.url()).toBe(`${ORIGIN}${PRODUCT}`);
  });
});

/** The bag after its last line is removed, as the cart section answers it. */
const EMPTY_CART = {
  cart: {
    summary_count: 0,
    subtotalAmount: "0.0000",
    items: [],
    freeShippingBar: { show: false, qualified: false, goal: 0, current: 0, remaining: 0 },
  },
};

test.describe("the bag, as the live site reports it", () => {
  test("an empty bag has no free-shipping answer, not 'reached'", async ({ page }) => {
    await serveSite(page);
    await page.route(`${ORIGIN}/customer/section/load/**`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(EMPTY_CART) }),
    );
    await open(page, PRODUCT);
    await listen(page);
    const opened = await run(page, "show_cart", { open: true });
    expect(opened.ok, opened.error).toBe(true);
    const cart = await waitForEvent(page, "cart_state");
    expect(cart.payload).toEqual({ items: [], count: 0, subtotal: 0, free_shipping_left: null });
    expect(opened.detail).toContain("the bag is empty");
    expect(opened.detail).not.toContain("free shipping reached");
  });

  test("a bag changed by a page load (the drawer's Eliminar reloads the page) is reported again", async ({ page }) => {
    await serveSite(page);
    let section: object = CART_SECTION;
    await page.route(`${ORIGIN}/customer/section/load/**`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(section) }),
    );
    await open(page, PRODUCT);
    await listen(page);
    const added = await run(page, "add_to_cart", { path: PRODUCT, qty: 2 });
    expect(added.ok, added.error).toBe(true);
    await waitForEvent(page, "cart_state", (e) => e.payload.count === 2);

    // The same bag after a load: nothing to say.
    await page.reload({ waitUntil: "domcontentloaded" });
    await listen(page);
    await waitForEvent(page, "product_shown");
    await page.waitForTimeout(2500);
    expect(named(await events(page), "cart_state")).toEqual([]);

    // The line removed, then the page reloaded: the empty bag is reported.
    section = EMPTY_CART;
    await page.reload({ waitUntil: "domcontentloaded" });
    await listen(page);
    const empty = await waitForEvent(page, "cart_state");
    expect(empty.payload).toEqual({ items: [], count: 0, subtotal: 0, free_shipping_left: null });
  });
});

test.describe("filter_listing, as the live site behaves", () => {
  test("closes the filter panel it opened when the panel's × is hidden (desktop)", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    // cannonhome.cl shows the panel's × only on a phone; a desktop closes the
    // panel with its pill.
    await page.addStyleTag({ content: ".qf__panel-close { display: none !important; }" });
    const result = await run(page, "filter_listing", { category_path: CATEGORY, size: null, color: "Blanco", threads: null, material: null, sort: null });
    expect(result.ok, result.error).toBe(true);
    await expect(page.locator('.qf__group[data-qf-request-var="color"] a.qf__option-link.-active')).toHaveAttribute("title", "Blanco");
    await expect(page.locator(".qf__group.-open")).toHaveCount(0);
  });

  test("closes the filter panel with its × when it shows (phone)", async ({ page }) => {
    await serveSite(page);
    await open(page, CATEGORY);
    const result = await run(page, "filter_listing", { category_path: CATEGORY, size: null, color: "Blanco", threads: null, material: null, sort: null });
    expect(result.ok, result.error).toBe(true);
    await expect(page.locator(".qf__group.-open")).toHaveCount(0);
  });

  test("reads the sorted grid only once it lands, not when the sorter's value changes", async ({ page }) => {
    await page.addInitScript(() => {
      (window as unknown as { __sortDelay: number }).__sortDelay = 1500;
    });
    await serveSite(page);
    await open(page, CATEGORY);
    await listen(page);
    const before = await page.evaluate(() => [...document.querySelectorAll("ol.products li.product-item a.product-item-link")].map((a) => a.textContent?.trim()));
    const result = await run(page, "filter_listing", { category_path: CATEGORY, size: null, color: null, threads: null, material: null, sort: "price_desc" });
    expect(result.ok, result.error).toBe(true);
    expect(result.detail).toContain("sorted price_desc");
    // The simulated sort reverses the grid after 1.5 s.
    const sortedFirst = before[before.length - 1]!;
    expect(result.detail).toContain(`first card ${sortedFirst}`);
    const listings = named(await events(page), "listing_shown");
    const last = listings[listings.length - 1].payload;
    expect((last.items as { name: string }[])[0].name).toBe(sortedFirst);
    expect(page.url()).toContain("product_list_order=price_desc");
  });
});

// ─── The checkout's delivery form ─────────────────────────────────────────

const CHECKOUT = "/checkout";
/** Obviously fake test data, as the live check uses. */
const FAKE = {
  email: "test@example.com",
  region: "metropolitana",
  comuna: "nunoa",
  street: "Calle Falsa",
  number: "123",
  apartment: "45",
  first_name: "Ana",
  last_name: "Prueba",
  phone: "912345678",
};

interface Guard {
  press(el: Element): void;
  intoCheckout(el: Element): string | null;
  forbiddenPath(p: string): boolean;
  privateField(el: Element): string | null;
}

/** The form's fields as they stand, for the tests (the adapter reports none of these values). */
const formValues = (p: Page) =>
  p.evaluate(() => {
    const v = (sel: string) => document.querySelector<HTMLInputElement>(sel)?.value ?? null;
    const picked = (field: string) => document.querySelector(`#co-shipping-form .field.${field} .cn-region-search__value`)?.textContent?.trim();
    return {
      email: v("#customer-email"),
      password: v("#customer-password"),
      region: picked("region_id"),
      comuna: picked("city_id"),
      street: v("input[name='street[0]']"),
      number: v("input[name='street[1]']"),
      apartment: v("input[name='street[2]']"),
      first_name: v("input[name=firstname]"),
      last_name: v("input[name=lastname]"),
      rut: v("input[name='custom_attributes[rut]']"),
      phone: v(".field.telephone input[name=telephone]:not([type=hidden])"),
      prefix: document.querySelector(".field.telephone .iti-flag")?.textContent?.trim(),
      submitted: (window as unknown as { __submitted: string[] }).__submitted,
    };
  });

test.describe("start_checkout", () => {
  test("from the bag, presses Terminar pedido, then Comprar como invitado (never a login), and finishes on the delivery form", async ({ page }) => {
    const seen = await serveSite(page);
    await open(page, "/checkout/cart/");
    await listen(page);
    await runAway(page, "start_checkout", {});
    await page.waitForURL(`${ORIGIN}${CHECKOUT}`, { timeout: 25_000 });
    await listen(page);
    const done = await waitForEvent(page, "command_done", (e) => e.payload.command === "start_checkout", 20_000);
    expect(done.payload.detail).toContain("the guest checkout's delivery form is open");
    const state = await waitForEvent(page, "checkout_state");
    expect(state.payload.missing).toEqual(["email", "region", "comuna", "street", "number", "first_name", "last_name", "rut", "phone"]);
    // The guest link was pressed: the checkout, and never a login or account page.
    expect(seen.pages).toEqual(["/checkout/cart/", CHECKOUT]);
    expect(seen.sent).toEqual([]);
  });

  test("from a product page, goes to the bag first and carries the move across both loads", async ({ page }) => {
    const seen = await serveSite(page);
    await open(page, PRODUCT);
    await runAway(page, "start_checkout", {});
    await page.waitForURL(`${ORIGIN}${CHECKOUT}`, { timeout: 30_000 });
    await listen(page);
    await waitForEvent(page, "command_done", (e) => e.payload.command === "start_checkout", 20_000);
    expect(seen.pages).toEqual([PRODUCT, "/checkout/cart/", CHECKOUT]);
  });

  test("fill_checkout from the bag opens the guest checkout and fills there (the move survives the load)", async ({ page }) => {
    await serveSite(page);
    await open(page, "/checkout/cart/");
    await runAway(page, "fill_checkout", { email: FAKE.email, region: "Metropolitana", comuna: "Providencia" });
    await page.waitForURL(`${ORIGIN}${CHECKOUT}`, { timeout: 25_000 });
    await listen(page);
    const done = await waitForEvent(page, "command_done", (e) => e.payload.command === "fill_checkout", 20_000);
    expect(done.payload.detail).toContain("filled email, región Metropolitana, comuna Providencia");
    const got = await formValues(page);
    expect([got.email, got.region, got.comuna]).toEqual([FAKE.email, "Metropolitana", "Providencia"]);
  });
});

test.describe("fill_checkout", () => {
  test("fills every allowed field, picks the comuna once its región's list loads, and reports names, never values", async ({ page }) => {
    const seen = await serveSite(page);
    await open(page, CHECKOUT);
    await listen(page);
    const r = await run(page, "fill_checkout", FAKE);
    expect(r.ok, r.error).toBe(true);
    expect(r.detail).toContain("filled email, región Metropolitana, comuna Ñuñoa, dirección, número, depto/casa, nombre, apellidos, teléfono");
    expect(r.detail).toContain("nothing was pressed after the fields");
    const got = await formValues(page);
    expect(got).toEqual({
      email: FAKE.email,
      password: "",
      region: "Metropolitana",
      comuna: "Ñuñoa",
      street: "Calle Falsa",
      number: "123",
      apartment: "45",
      first_name: "Ana",
      last_name: "Prueba",
      rut: "",
      // +56 9 is the prefix; the other eight digits go in the field, unchanged.
      phone: "12345678",
      prefix: "+56 9",
      submitted: [],
    });
    expect(seen.comunas).toEqual(["664"]);
    const state = await waitForEvent(page, "checkout_state", (e) => (e.payload.filled as string[]).includes("phone"));
    expect(state.payload).toMatchObject({
      filled: ["email", "region", "comuna", "street", "number", "apartment", "first_name", "last_name", "phone"],
      missing: ["rut", "delivery"],
      invalid: [],
      region: "Metropolitana",
      comuna: "Ñuñoa",
      email_has_account: false,
      payment_open: false,
    });
    // What the visitor's details are never leaves the page.
    const wire = JSON.stringify(await events(page));
    for (const value of [FAKE.email, "Calle Falsa", "Prueba", "912345678", "12345678"]) expect(wire).not.toContain(value);
    expect(seen.sent).toEqual([]);
  });

  test("a Santiago landline gets the +56 2 prefix and its own eight digits", async ({ page }) => {
    await serveSite(page);
    await open(page, CHECKOUT);
    const r = await run(page, "fill_checkout", { phone: "223456789" });
    expect(r.ok, r.error).toBe(true);
    const got = await formValues(page);
    expect([got.prefix, got.phone]).toEqual(["+56 2", "23456789"]);
  });

  test("never fills the RUT, a password or anything of the payment, whatever it is sent", async ({ page }) => {
    await serveSite(page);
    await open(page, CHECKOUT);
    const r = await run(page, "fill_checkout", { first_name: "Ana", rut: "12.345.678-5", password: "secreto", card: "4111111111111111" });
    expect(r.ok, r.error).toBe(true);
    expect(r.detail).toMatch(/^filled nombre;/);
    const got = await formValues(page);
    expect([got.first_name, got.rut, got.password]).toEqual(["Ana", "", ""]);
    const fields = await page.evaluate(() => {
      const t = (window as unknown as { __voqalizeTest: Guard }).__voqalizeTest;
      const why = (sel: string) => {
        const el = document.querySelector(sel);
        return el ? t.privateField(el) : `missing ${sel}`;
      };
      return {
        rut: why("input[name='custom_attributes[rut]']"),
        password: why("#customer-password"),
        rutEmpresa: why("#checkout_rut_empresa"),
        whoReceivesRut: why("#who_receive_rut"),
        giftcard: why("#giftcard-code"),
        email: why("#customer-email"),
        firstname: why("input[name=firstname]"),
        street: why("input[name='street[0]']"),
        phone: why(".field.telephone input[name=telephone]:not([type=hidden])"),
      };
    });
    expect(fields.rut).toMatch(/visitor's to type/);
    expect(fields.password).toMatch(/password/);
    expect(fields.rutEmpresa).not.toBeNull();
    expect(fields.whoReceivesRut).not.toBeNull();
    expect(fields.giftcard).not.toBeNull();
    expect([fields.email, fields.firstname, fields.street, fields.phone]).toEqual([null, null, null, null]);
  });

  test("refuses the continue-to-payment and place-order buttons, the delivery method and every login, and allows only the form's pickers", async ({ page }) => {
    await serveSite(page);
    await open(page, CHECKOUT);
    const got = await page.evaluate(() => {
      const t = (window as unknown as { __voqalizeTest: Guard }).__voqalizeTest;
      const tryPress = (sel: string) => {
        const el = document.querySelector(sel);
        if (!el) return `missing ${sel}`;
        try {
          t.press(el);
          return "pressed";
        } catch (error) {
          return String((error as Error).message);
        }
      };
      return {
        placeOrder: tryPress(".co-place-order__button"),
        terms: tryPress("#co-place-order-terms"),
        continueToPayment: tryPress("[data-role=opc-continue]"),
        homeDelivery: tryPress("#common_shipping_type_homedelivery"),
        invoice: tryPress("#checkout_request_invoice"),
        login: tryPress("#checkout a.action.remind"),
        createAccount: tryPress("#checkout a[href^='/customer/account/create']"),
        guestLinkHere: tryPress("#checkout .new-user a[href='/checkout']"),
        coupon: tryPress("#discount-form button"),
        region: t.intoCheckout(document.querySelector("#co-shipping-form .field.region_id .cn-region-search__trigger")!),
        comuna: t.intoCheckout(document.querySelector("#co-shipping-form .field.city_id .cn-region-search__trigger")!),
        prefix: t.intoCheckout(document.querySelector("#co-shipping-form .field.telephone .selected-flag")!),
        submitted: (window as unknown as { __submitted: string[] }).__submitted,
      };
    });
    for (const key of ["placeOrder", "terms", "continueToPayment", "homeDelivery", "invoice", "login", "createAccount", "guestLinkHere", "coupon"] as const) {
      expect(got[key], key).toMatch(/^refused to press it/);
    }
    expect([got.region, got.comuna, got.prefix]).toEqual([null, null, null]);
    expect(got.submitted).toEqual([]);
    expect(page.url()).toBe(`${ORIGIN}${CHECKOUT}`);
  });

  test("a comuna before any región, or one not in the list, fails and says what the list has", async ({ page }) => {
    await serveSite(page);
    await open(page, CHECKOUT);
    const early = await run(page, "fill_checkout", { comuna: "Providencia" });
    expect(early.ok).toBe(false);
    expect(early.error).toContain("choose the región first");
    const wrong = await run(page, "fill_checkout", { region: "Valparaíso", comuna: "Providencia" });
    expect(wrong.ok).toBe(true);
    expect(wrong.detail).toContain("filled región Valparaíso; not filled: comuna: no comuna \"Providencia\" in the form's list; it lists Quilpué, Valparaíso, Viña del Mar");
    const region = await run(page, "fill_checkout", { region: "Atlántida" });
    expect(region.ok).toBe(false);
    expect(region.error).toContain('no región "Atlántida"');
  });

  test("the form's own messages are reported with the field, and an email with an account brings its password, left empty", async ({ page }) => {
    await serveSite(page);
    await open(page, CHECKOUT);
    await listen(page);
    const r = await run(page, "fill_checkout", { email: "existe@example.com", phone: "912" });
    expect(r.ok, r.error).toBe(true);
    expect(r.detail).toContain("not filled: teléfono: a Chilean number is nine digits");
    const state = await waitForEvent(page, "checkout_state", (e) => e.payload.email_has_account === true);
    expect(state.payload.filled).toEqual(["email"]);
    expect((await formValues(page)).password).toBe("");
    // The visitor types a short phone themselves: the form's message is read.
    await page.fill(".field.telephone input[name=telephone]:not([type=hidden])", "123");
    await page.locator(".field.telephone input[name=telephone]:not([type=hidden])").blur();
    const flagged = await waitForEvent(page, "checkout_state", (e) => (e.payload.invalid as unknown[]).length > 0);
    expect(flagged.payload.invalid).toEqual([{ field: "phone", message: "Ingresa un número de teléfono válido." }]);
  });
});

test.describe("the bag's login window", () => {
  test("only Comprar como invitado may be pressed; the login, Google, Crear Cuenta and the password are refused", async ({ page }) => {
    await serveSite(page);
    await open(page, "/checkout/cart/");
    await page.waitForSelector("aside.login-modal a[href='/checkout']", { state: "attached" });
    await page.click("[data-role=proceed-to-checkout]");
    const got = await page.evaluate(() => {
      const t = (window as unknown as { __voqalizeTest: Guard }).__voqalizeTest;
      const why = (sel: string) => {
        const el = document.querySelector(`aside.login-modal ${sel}`);
        return el ? t.intoCheckout(el) : `missing ${sel}`;
      };
      return {
        guest: why("a[href='/checkout']"),
        login: why("button.action.login"),
        google: why(".btn-google"),
        create: why("a[href^='/customer/account/create']"),
        forgot: why("a[href*='forgotpassword']"),
        password: why("#customer-password"),
        email: why("#customer-email"),
      };
    });
    expect(got.guest).toBeNull();
    for (const key of ["login", "google", "create", "forgot", "password", "email"] as const) expect(got[key], key).not.toBeNull();
  });
});

// ─── Changing the bag (update_cart_item) ──────────────────────────────────
//
// A live call (2026-10-23): the visitor asked Javier to make two grey sets
// one, and he could not. The drawer posts each − and + by AJAX and its bin
// asks "¿Seguro…?" first; the bag page reloads on every change.

const PILLOW = "/almohada-viscoelastica-ergo-50x70-cm.html";
const FOG: BagLine = { id: "11", name: "Sábanas 2 Plazas 300 Hilos Liso Fog", path: PRODUCT, qty: 2, price: 55993 };
const ERGO: BagLine = { id: "12", name: "Almohada Viscoelástica Ergo 50x70 cm", path: PILLOW, qty: 1, price: 29990 };

/** After a move that reloads the bag page, perhaps more than once: the page
 *  whose bag `ready` holds, listened to, and the move's answer there. */
async function settledBagPage(page: Page, ready: () => boolean): Promise<Emitted> {
  await expect.poll(ready, { timeout: 30_000 }).toBe(true);
  for (;;) {
    await page.waitForLoadState("domcontentloaded");
    try {
      await listen(page);
      return await waitForEvent(page, "command_done", (e) => e.payload.command === "update_cart_item", 8000);
    } catch (error) {
      if (!/context was destroyed|navigat|no command_done/i.test(String(error))) throw error;
    }
  }
}

test.describe("update_cart_item", () => {
  test("in the drawer: − sets a line's quantity, the bin and Aceptar take one out; each reports the bag", async ({ page }) => {
    const seen = await serveSite(page, { bag: [FOG, ERGO] });
    await open(page, PRODUCT);
    await listen(page);
    const fewer = await run(page, "update_cart_item", { path: PRODUCT, qty: 1 });
    expect(fewer.ok, fewer.error).toBe(true);
    expect(fewer.detail).toContain("set Sábanas 2 Plazas 300 Hilos Liso Fog to 1 in the bag (it had 2)");
    expect(fewer.detail).toContain("the bag has 2 items");
    await expect(page.locator("aside.content-minicart-modal")).toHaveClass(/_show/);
    const cart = await waitForEvent(page, "cart_state", (e) => e.payload.count === 2);
    expect(cart.payload.items).toEqual([
      { name: FOG.name, path: PRODUCT, qty: 1, price: 55993 },
      { name: ERGO.name, path: PILLOW, qty: 1, price: 29990 },
    ]);
    expect(seen.sent).toContain("POST /checkout/sidebar/updateItemQty/");

    const out = await run(page, "update_cart_item", { path: PILLOW, qty: 0 });
    expect(out.ok, out.error).toBe(true);
    expect(out.detail).toContain(`took ${ERGO.name} out of the bag`);
    expect(seen.bag.map((l) => l.id)).toEqual([FOG.id]);
    expect(seen.sent).toContain("POST /checkout/sidebar/removeItem/");
    await waitForEvent(page, "cart_state", (e) => e.payload.count === 1);
    // More of it: + until it has three.
    const more = await run(page, "update_cart_item", { path: PRODUCT, qty: 3 });
    expect(more.ok, more.error).toBe(true);
    expect(seen.bag).toEqual([{ ...FOG, qty: 3 }]);
    // Nothing reached the checkout.
    expect(seen.sent.filter((s) => !/sidebar\/(updateItemQty|removeItem)/.test(s))).toEqual([]);
  });

  test("a line not in the bag, or a quantity out of 0–10, is refused and nothing is pressed", async ({ page }) => {
    const seen = await serveSite(page, { bag: [FOG] });
    await open(page, PRODUCT);
    const missing = await run(page, "update_cart_item", { path: PILLOW, qty: 0 });
    expect(missing.ok).toBe(false);
    expect(missing.error).toContain(`${PILLOW} is not in the bag; the bag has ${FOG.name} (${PRODUCT}) ×2`);
    const many = await run(page, "update_cart_item", { path: PRODUCT, qty: 11 });
    expect(many.ok).toBe(false);
    const same = await run(page, "update_cart_item", { path: PRODUCT, qty: 2 });
    expect(same.ok, same.error).toBe(true);
    expect(same.detail).toContain("already has 2 in the bag; nothing changed");
    expect(seen.sent).toEqual([]);
  });

  test("on the bag page: the line's new quantity is sent as the page's − sends it, and the reloaded page confirms it", async ({ page }) => {
    const seen = await serveSite(page, { bag: [{ ...FOG, qty: 3 }, ERGO] });
    await open(page, "/checkout/cart/");
    await expect(page.locator("tbody.cart.item")).toHaveCount(2);
    await runAway(page, "update_cart_item", { path: PRODUCT, qty: 1 });
    const done = await settledBagPage(page, () => seen.bag.find((l) => l.id === FOG.id)?.qty === 1);
    expect(done.payload.detail).toContain("set Sábanas 2 Plazas 300 Hilos Liso Fog to 1 in the bag");
    // One request with the quantity asked, whatever the step, and one reload.
    expect(seen.sent).toEqual(["POST /checkout/sidebar/updateItemQty/"]);
    const cart = await waitForEvent(page, "cart_state");
    expect(cart.payload.count).toBe(2);
    await expect(page.locator("tbody.cart.item input.qty").first()).toHaveValue("1");
  });

  test("on the bag page: the line is removed as the drawer's Aceptar removes it, and the reloaded page reports it gone", async ({ page }) => {
    const seen = await serveSite(page, { bag: [FOG, ERGO] });
    await open(page, "/checkout/cart/");
    await expect(page.locator("tbody.cart.item")).toHaveCount(2);
    await runAway(page, "update_cart_item", { path: PRODUCT, qty: 0 });
    const done = await settledBagPage(page, () => !seen.bag.some((l) => l.id === FOG.id));
    expect(done.payload.detail).toContain(`took ${FOG.name} out of the bag; the bag has 1 item`);
    expect(seen.sent).toEqual(["POST /checkout/sidebar/removeItem/"]);
    const cart = await waitForEvent(page, "cart_state");
    expect(cart.payload.items).toEqual([{ name: ERGO.name, path: PILLOW, qty: 1, price: 29990 }]);
  });

  test("from the checkout, the move goes to the bag page first", async ({ page }) => {
    const seen = await serveSite(page, { bag: [FOG] });
    await open(page, "/checkout");
    await runAway(page, "update_cart_item", { path: PRODUCT, qty: 0 });
    const done = await settledBagPage(page, () => seen.bag.length === 0);
    expect(done.payload.detail).toContain("the bag is empty");
    expect(page.url()).toBe(`${ORIGIN}/checkout/cart/`);
  });
});

test("a price written the English way (a translated page: $29,990) is read in full, not as 29", async ({ page }) => {
  await serveSite(page);
  await page.route(`${ORIGIN}/customer/section/load/**`, (route) => route.fulfill({ status: 500, body: "" }));
  await open(page, PRODUCT);
  await page.evaluate(() => {
    document.querySelectorAll(".mc-price--now, .mc-total-row--grand .mc-total-row__value").forEach((el) => (el.textContent = "$29,990"));
    const bar = document.querySelector(".main-progress-bar__message");
    if (bar) bar.textContent = "You are $120,010 away from Free Shipping, RM only";
  });
  await listen(page);
  const opened = await run(page, "show_cart", { open: true });
  expect(opened.ok, opened.error).toBe(true);
  const cart = await waitForEvent(page, "cart_state");
  expect(cart.payload).toEqual({
    items: [{ name: "Almohada Viscoelástica Ergo 50x70 cm", path: PILLOW, qty: 1, price: 29990 }],
    count: 1,
    subtotal: 29990,
    free_shipping_left: 120010,
  });
});
