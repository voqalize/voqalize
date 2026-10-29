// Trims pages saved from www.pcfactory.cl (rendered, `page.content()` after
// the site's scripts and Vue widgets ran) into the small fixtures under
// test/pages/:
//
//   node test/make-fixtures.mjs <dir with the saved pages>
//
// The saved pages are home.html, category.html (/categoria/computadores-y-
// tablets/notebooks/notebooks), search.html (/busqueda-avanzada?search=
// monitor+27), product.html (/producto/57233), cart-live.html (/carro with one
// item, 8941), tiendas.html, help.html (/centro-de-ayuda/compra-con-retiro-
// en-tienda), checkout-live.html (/checkout, the first step, as a guest) and
// tipo-entrega-live.html (/checkout/tipo-entrega, nothing chosen).
//
// Every <script> goes except the JSON-LD `Product`; so do stylesheets, inline
// <style>, iframes, comments, SVG drawings, images' addresses, Vue's
// `data-v-*` marks, the categories window's panels, the mobile menu, the
// footer, the Retail Rocket rails' looped copies and the hero carousel's other
// slides. The DOM the adapter reads (ids, classes, data-* attributes, prices,
// the filter panel, the grid's cards, the product page's tabs, specifications,
// stock and gallery, the cart's rows and summary, the store cards, the
// checkout's cards and radios) is kept as the site rendered it. A short
// stylesheet of our own stands in for the site's: Bootstrap's display classes,
// and what it hides until a click (collapses, windows, tab panes, menus).

import { chromium } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = process.argv[2];
if (!src) {
  console.error("usage: node test/make-fixtures.mjs <dir with the saved pages>");
  process.exit(2);
}

/** Saved page → fixture, and how much of it to keep. */
const PAGES = [
  { from: "home.html", to: "home.html", slides: 5 },
  { from: "category.html", to: "category.html", cards: 6 },
  { from: "search.html", to: "search.html", cards: 4 },
  { from: "product.html", to: "product.html" },
  { from: "cart-live.html", to: "cart.html" },
  { from: "tiendas.html", to: "tiendas.html" },
  { from: "help.html", to: "help.html" },
  { from: "checkout-live.html", to: "checkout.html" },
  { from: "tipo-entrega-live.html", to: "tipo-entrega.html" },
];

const FIXTURE_CSS = `
  /* Ours, standing in for the site's stylesheet: Bootstrap's display classes
     at a desktop width, and what it hides until a click. */
  body { margin: 0; font-family: Ubuntu, Arial, sans-serif; }
  .d-flex { display: flex; } .d-block { display: block; } .d-grid { display: grid; } .d-inline-block { display: inline-block; }
  .d-none { display: none !important; }
  .d-md-block, .d-lg-block, .d-xl-block { display: block !important; }
  .d-md-flex, .d-lg-flex, .d-xl-flex { display: flex !important; }
  .d-md-inline-block, .d-lg-inline-block, .d-xl-inline-block { display: inline-block !important; }
  .d-md-none, .d-lg-none, .d-xl-none { display: none !important; }
  .collapse:not(.show) { display: none; }
  .modal { display: none; }
  .modal.show { display: block; position: fixed; inset: 10% 20% auto 20%; background: #fff; z-index: 1050; }
  .tab-pane:not(.active) { display: none; }
  .dropdown-menu { display: none; }
  .dropdown-menu.show { display: block; }
  #pcf-comparator-summary { display: none; }
  #pcf-comparator-summary.show { display: flex; position: fixed; left: 0; right: 0; bottom: 0; height: 200px; background: #212425; color: #fff; z-index: 1030; }
  img { width: 120px; height: 120px; }
  section[data-section-name="Lista productos"] { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
  .gm-style-iw { display: block; padding: 8px; border: 1px solid #ccc; }
`;

function trim({ cards, slides }) {
  const drop = (sel) => document.querySelectorAll(sel).forEach((el) => el.remove());
  for (const s of document.querySelectorAll("script")) {
    const keep = s.type === "application/ld+json" && /"@type"\s*:\s*"Product"/.test(s.textContent ?? "");
    if (!keep) s.remove();
  }
  drop("style, link, noscript, iframe, object, embed, template, meta, base");
  const walker = document.createTreeWalker(document, NodeFilter.SHOW_COMMENT);
  const comments = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) comments.push(n);
  comments.forEach((c) => c.remove());
  document.querySelectorAll("svg").forEach((svg) => svg.replaceChildren());
  // The categories window's panels, the mobile menu, the footer, trackers'
  // and chats' nodes, the Retail Rocket rails' looped copies.
  drop(".categories-dropdown-list__panel, .menu-wrapper, #mobile-categories, [id^=ocular], #pcfChatContainer, [id^=batBeacon], [id^=_hj]");
  drop(".swiper-slide-duplicate, #carousel-home-mobile, #gallery-modal, #pickup-modal");
  document.querySelector("footer")?.replaceChildren();
  // The hero carousel: its first slide.
  document.querySelectorAll(".carousel-item:not(.active)").forEach((el) => el.closest("#carousel-home-desktop") && el.remove());
  if (slides) {
    for (const rail of document.querySelectorAll(".rr-widget, .swiper-wrapper")) {
      [...rail.querySelectorAll(":scope .rr-swiper-slide")].forEach((s, i) => i >= slides && s.remove());
    }
  }
  if (cards) {
    const grid = document.querySelector('section[data-section-name="Lista productos"]');
    [...(grid?.children ?? [])].forEach((c, i) => i >= cards && c.remove());
    // The "Los favoritos" rail under the grid is not the listing.
    document.querySelectorAll("#main-layout .rr-widget").forEach((w) => w.remove());
  }
  // The product page's long description and its rails.
  for (const el of document.querySelectorAll("#product-description, #about .tab-content-text")) {
    if ((el.textContent ?? "").length > 600) el.replaceChildren(document.createTextNode((el.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 600)));
  }
  if (document.body.className.includes("show-producto")) document.querySelectorAll("#main-layout .rr-widget").forEach((w) => w.remove());
  // Images: no addresses (nothing loads offline).
  document.querySelectorAll("img").forEach((img) => {
    img.removeAttribute("srcset");
    img.removeAttribute("src");
    img.removeAttribute("data-src");
  });
  // Vue's scoped marks, and style attributes Bootstrap's scripts left.
  for (const el of document.querySelectorAll("*")) {
    for (const a of [...el.attributes]) if (a.name.startsWith("data-v-")) el.removeAttribute(a.name);
  }
  document.querySelectorAll(".modal.show").forEach((m) => {
    m.classList.remove("show");
    m.removeAttribute("style");
  });
  document.querySelectorAll(".modal-backdrop").forEach((b) => b.remove());
  document.body.classList.remove("modal-open");
}

const browser = await chromium.launch();
const context = await browser.newContext({ javaScriptEnabled: false });
await context.route("**/*", (route) => route.abort());
const page = await context.newPage();

for (const spec of PAGES) {
  const html = readFileSync(join(src, spec.from), "utf8");
  await page.setContent(html, { waitUntil: "domcontentloaded" });
  // JavaScript is off for the page, not for `evaluate`.
  await page.evaluate(trim, spec);
  await page.evaluate((css) => {
    const style = document.createElement("style");
    style.setAttribute("data-fixture", "");
    style.textContent = css;
    document.head.appendChild(style);
  }, FIXTURE_CSS);
  let out = await page.evaluate(() => `<!doctype html>\n${document.documentElement.outerHTML}`);
  out = out.replace(/\n\s*\n+/g, "\n").replace(/[ \t]{2,}/g, " ");
  writeFileSync(join(here, "pages", spec.to), out);
  console.log(`${spec.to}: ${(out.length / 1024).toFixed(1)} KB`);
}

await browser.close();
