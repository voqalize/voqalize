// Trims pages saved from www.agroplanet.cl (rendered, `page.content()` after
// the Angular app drew the route and its API answers came in) into the small
// fixtures under test/pages/:
//
//   node test/make-fixtures.mjs <dir with the saved pages>
//
// The saved pages are home.html (/), category.html (/categoria/lubricantes/
// AG100, every filter panel opened so their options are drawn), search.html
// (/busqueda/bateria, the same), product.html (/producto/…/1173221),
// product-hidden.html (/producto/…/139083, "Confirmar precio en tienda"),
// tiendas.html (/nuestras-tiendas), cambios-devoluciones.html, cart.html
// (/carro with 1173221 in it) and cotizacion.html (/cotizacion, nothing
// typed). The second pass (2026-10-29) added category-ag15.html
// (/categoria/agroferreteria/AG15, its "Agrofertas Octubre" switch off),
// brand.html (/marca/bkt, 20 a page), search-empty.html (/busqueda/xyzqwe,
// "No logramos encontrar resultados"), product-related.html (126615: its
// Equivalencias and "Complemente su compra"), product-tractor.html (1184833,
// the tractor for sale) and product-label.html (1184899, "Venta en Verde").
// A page missing from the folder is skipped, so one pass's pages can be
// trimmed again without the other's.
//
// Every <script>, stylesheet, inline <style>, iframe, comment and SVG drawing
// goes; so do images' addresses, Angular's `_ngcontent-*` / `_nghost-*`
// marks, Material's live-announcer, and the inline styles flex-layout wrote
// (except a `display: none`, which is how it hides a phone-only copy). The
// grids keep their first cards, the home's rails their first slides. The DOM
// the adapter reads (component tags, classes, ids, form controls, the filter
// panels and their checkboxes, the cards' links and prices, the product's
// info, details and specifications, the cart's rows and steppers, the quote
// form and its summary, the store cards, the policy panels) is kept as the
// app drew it. A short stylesheet of our own stands in for Material's: what
// it hides until a press (folded panels, `hidden`, the overlays).

import { chromium } from "@playwright/test";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
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
  { from: "category.html", to: "category.html", cards: 8 },
  { from: "search.html", to: "search.html", cards: 8 },
  { from: "product.html", to: "product.html" },
  { from: "product-hidden.html", to: "product-hidden.html" },
  { from: "tiendas.html", to: "tiendas.html" },
  { from: "cambios-devoluciones.html", to: "cambios-devoluciones.html" },
  { from: "cart.html", to: "cart.html" },
  { from: "cotizacion.html", to: "cotizacion.html" },
  { from: "category-ag15.html", to: "category-ag15.html", cards: 8 },
  { from: "brand.html", to: "brand.html", cards: 8, options: 12 },
  { from: "search-empty.html", to: "search-empty.html" },
  { from: "product-related.html", to: "product-related.html" },
  { from: "product-tractor.html", to: "product-tractor.html" },
  { from: "product-label.html", to: "product-label.html" },
];

const FIXTURE_CSS = `
  /* Ours, standing in for Angular Material's stylesheet: what it hides until
     a press, and a desktop layout rough enough to scroll. */
  body { margin: 0; font-family: Roboto, Arial, sans-serif; }
  [hidden] { display: none !important; }
  .cdk-visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  mat-expansion-panel:not(.mat-expanded) > .mat-expansion-panel-content { display: none; }
  app-sticky-header-desktop, mat-sidenav.sidenav, .mat-drawer-backdrop { display: none; }
  .cdk-overlay-container { position: fixed; top: 0; left: 0; width: 100%; height: 0; z-index: 1000; }
  .cdk-overlay-container > * { position: absolute; top: 200px; left: 400px; background: #fff; }
  .cdk-overlay-backdrop { position: fixed !important; inset: 0; top: 0 !important; left: 0 !important; background: rgba(0,0,0,.3) !important; }
  html.cdk-global-scrollblock { overflow: hidden; position: fixed; width: 100%; }
  #acordeon-main { position: absolute; left: 0; top: 156px; width: 100%; background: #fff; z-index: 500; }
  img { width: 120px; height: 120px; }
  app-plp-grid > div, app-plp-grid .ng-star-inserted > div { }
  app-plp-grid a { display: inline-block; width: 280px; vertical-align: top; margin: 4px; }
  .cookies-wrapper { position: fixed; bottom: 0; left: 0; right: 0; height: 100px; background: #fff; z-index: 10000; }
  .whatsapp-float { display: none; }
`;

function trim({ cards, slides, options }) {
  const drop = (sel) => document.querySelectorAll(sel).forEach((el) => el.remove());
  drop("script, style, link, noscript, iframe, object, embed, template, meta, base, .cdk-live-announcer-element");
  const walker = document.createTreeWalker(document, NodeFilter.SHOW_COMMENT);
  const comments = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) comments.push(n);
  comments.forEach((c) => c.remove());
  document.querySelectorAll("svg").forEach((svg) => svg.replaceChildren());
  // The overlays the save caught (a splash, a menu), and the home's banner
  // slides past the first.
  document.querySelectorAll(".cdk-overlay-container").forEach((o) => o.replaceChildren());
  document.documentElement.classList.remove("cdk-global-scrollblock");
  if (slides) {
    for (const wrapper of document.querySelectorAll(".swiper-wrapper")) {
      [...wrapper.children].forEach((s, i) => i >= slides && s.remove());
    }
  }
  if (cards) {
    const all = [...document.querySelectorAll("app-plp-grid a[href*='/producto/']")];
    all.forEach((a, i) => i >= cards && (a.closest(".m-04") ?? a).remove());
  }
  // A brand's panels list every option (hundreds): the first few kept.
  if (options) {
    for (const panel of document.querySelectorAll("app-filter-element mat-expansion-panel")) {
      [...panel.querySelectorAll("mat-checkbox")].forEach((box, i) => i >= options && (box.closest("li, .ng-star-inserted") ?? box).remove());
    }
  }
  // The filter panels as the app first draws them: "Precio" open, the rest
  // folded (they were opened for the save, so their options are here).
  for (const panel of document.querySelectorAll("app-filter-element mat-expansion-panel")) {
    if (!/precio/i.test(panel.querySelector("mat-panel-title")?.textContent ?? "")) {
      panel.classList.remove("mat-expanded");
      panel.querySelector("mat-expansion-panel-header")?.classList.remove("mat-expanded");
    }
  }
  // The footer: its panels' titles, not their links.
  document.querySelectorAll("app-footer .mat-expansion-panel-body").forEach((b) => b.replaceChildren());
  // Long texts: the product's description and the policy panels' answers.
  for (const el of document.querySelectorAll("app-product-tabs p.format, #comentarProductoMobile p, .mat-expansion-panel-body p, .mat-expansion-panel-body li")) {
    const text = (el.textContent ?? "").replace(/\s+/g, " ").trim();
    if (text.length > 400) el.replaceChildren(document.createTextNode(text.slice(0, 400)));
  }
  // Images: no addresses (nothing loads offline).
  document.querySelectorAll("img").forEach((img) => {
    img.removeAttribute("srcset");
    img.removeAttribute("src");
    img.removeAttribute("data-src");
  });
  // Angular's scoped marks; flex-layout's inline styles but its hiding.
  for (const el of document.querySelectorAll("*")) {
    for (const a of [...el.attributes]) {
      if (/^_ng(content|host)-/.test(a.name) || /^(fx|ngclass)/i.test(a.name)) el.removeAttribute(a.name);
    }
    const style = el.getAttribute("style");
    if (style !== null) {
      if (/display:\s*none/.test(style)) el.setAttribute("style", "display: none;");
      else el.removeAttribute("style");
    }
  }
}

const browser = await chromium.launch();
const context = await browser.newContext({ javaScriptEnabled: false });
await context.route("**/*", (route) => route.abort());
const page = await context.newPage();

for (const spec of PAGES) {
  if (!existsSync(join(src, spec.from))) continue;
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
