// Trims pages saved from cannonhome.cl (rendered, `page.content()` after the
// site's scripts ran) into the small fixtures under test/pages/:
//
//   node test/make-fixtures.mjs <dir with the saved pages>
//
// Every <script> goes except the JSON-LD `Product`; so do stylesheets, inline
// <style>, iframes, comments, SVG drawings, trackers' nodes, GoPersonal's
// carousels, the footer, the mobile menu and the mega menu's panels, and every
// form key and data-post token. The DOM the adapter reads (ids, classes,
// data-* attributes, prices, the quick filters, the product page's form, tabs
// and gallery, the bag drawer) is kept as the site rendered it. A short
// stylesheet of our own stands in for the site's, hiding what the site hides
// until a click (filter panels, closed drawers, the dropdown).

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
  { from: "home.html", to: "home.html", rows: 3 },
  { from: "category.html", to: "category.html", cards: 6 },
  { from: "search-result.html", to: "search.html", cards: 4 },
  // Saved with an empty bag, whose drawer Knockout never rendered: the
  // drawer is the one saved after an add.
  { from: "pdp-sheets.html", to: "product.html", drawerFrom: "after-add.html" },
  { from: "cart-one-item.html", to: "cart.html" },
];

const FIXTURE_CSS = `
  /* Ours, standing in for the site's stylesheet: what it hides until a click. */
  body { margin: 0; font-family: Lato, sans-serif; }
  #topbarCannonBar { position: fixed; top: 0; left: 0; right: 0; height: 32px; overflow: hidden; background: #000; color: #fff; z-index: 120; }
  body.has-topbar-cannon { padding-top: 32px; }
  .qf__panel { display: none; }
  .qf__group.-open .qf__panel { display: block; }
  aside.modal-popup { display: none; }
  aside.modal-popup._show { display: block; position: fixed; top: 0; right: 0; width: 400px; height: 100vh; overflow: auto; background: #fff; z-index: 902; }
  .see-less { display: none; }
  #layered-filter-block { display: none; }
  .fotorama__nav__frame { display: inline-block; width: 80px; height: 80px; }
  .product-image-photo, .fotorama__img { width: 120px; height: 120px; object-fit: contain; }
  .whatsapp-link { position: fixed; right: 24px; bottom: 24px; width: 48px; height: 48px; }
  .desktop-hide { display: none; }
  ol.products { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; list-style: none; padding: 0; }
`;

function trim({ cards, rows }) {
  const drop = (sel) => document.querySelectorAll(sel).forEach((el) => el.remove());
  // Scripts, styles, frames and the rest of what does not render.
  for (const s of document.querySelectorAll("script")) {
    const keep = s.type === "application/ld+json" && /"@type"\s*:\s*"Product"/.test(s.textContent ?? "");
    if (!keep) s.remove();
  }
  drop("style, link, noscript, iframe, object, embed, template, meta[name=google-site-verification], base");
  const walker = document.createTreeWalker(document, NodeFilter.SHOW_COMMENT);
  const comments = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) comments.push(n);
  comments.forEach((c) => c.remove());
  document.querySelectorAll("svg").forEach((svg) => svg.replaceChildren());
  // Trackers' and widgets' nodes, carousels, the footer, the mobile menu.
  drop("[id^=gopersonal], [class*=gs_main_container], #mySidenav, #ninjamenus4, .ninjamenus-mobile-wrapper, .top-container, .page-bottom, .huincha");
  drop("#epik_localstore, .verificadoai-plp-rating, [id^=freshworks], #launcher-frame, [class*=survicate], .kiosko-qr-entry");
  drop("aside.modal-popup:not(.content-minicart-modal), .modals-overlay, .loading-mask");
  document.querySelector("footer")?.replaceChildren();
  drop("#ninjamenus7 .item-submenu, .category-cms, #layered-filter-block .filter-options, .product-list-rating-stars, .actions-secondary, .actions-secondary-2");
  // The bag drawer stays, closed.
  document.querySelectorAll("aside.content-minicart-modal").forEach((a) => a.classList.remove("_show"));
  document.body.classList.remove("_has-modal", "ajax-loading", "qf-panel-open");
  // Tokens.
  document.querySelectorAll("input[name=form_key]").forEach((i) => i.setAttribute("value", ""));
  document.querySelectorAll("[data-post]").forEach((el) => el.removeAttribute("data-post"));
  document.querySelectorAll("[data-mage-init], [data-bind]").forEach((el) => {
    el.removeAttribute("data-mage-init");
    el.removeAttribute("data-bind");
  });
  for (const el of document.querySelectorAll("[x-magento-init], [data-gtm], [data-gtag]")) {
    el.removeAttribute("x-magento-init");
  }
  // Images: the first of each card's carousel.
  document.querySelectorAll(".product-item .slick-slide:not(.slick-current)").forEach((el) => el.remove());
  if (cards) document.querySelectorAll("ol.products li.product-item").forEach((li, i) => i >= cards && li.remove());
  if (rows) {
    const all = [...document.querySelectorAll("#maincontent [data-content-type=row]")];
    all.forEach((r, i) => i >= rows && r.remove());
  }
  // Long text blocks kept short.
  for (const p of document.querySelectorAll("#maincontent .category-description, #description .value, #verificado_widget")) {
    if ((p.textContent ?? "").length > 600) p.replaceChildren(document.createTextNode((p.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 600)));
  }
  // Images: the shop's own only; trackers' pixels (Bing, Meta, TikTok…)
  // carry the saving session's ids.
  document.querySelectorAll("img").forEach((img) => {
    let host = "";
    try {
      host = new URL(img.getAttribute("src") ?? "", "https://cannonhome.cl").host;
    } catch {
      host = "";
    }
    if (host !== "cannonhome.cl" && host !== "www.cannonhome.cl") return img.remove();
    img.removeAttribute("srcset");
    img.removeAttribute("data-src");
  });
}

const browser = await chromium.launch();
const context = await browser.newContext({ javaScriptEnabled: false });
await context.route("**/*", (route) => route.abort());
const page = await context.newPage();

async function drawerOf(file) {
  await page.setContent(readFileSync(join(src, file), "utf8"), { waitUntil: "domcontentloaded" });
  await page.evaluate(trim, {});
  return page.evaluate(() => document.querySelector("aside.content-minicart-modal")?.outerHTML ?? "");
}

for (const spec of PAGES) {
  const drawer = spec.drawerFrom ? await drawerOf(spec.drawerFrom) : "";
  const html = readFileSync(join(src, spec.from), "utf8");
  await page.setContent(html, { waitUntil: "domcontentloaded" });
  // JavaScript is off for the page, not for `evaluate`.
  await page.evaluate(trim, spec);
  if (drawer) {
    await page.evaluate((outer) => {
      const old = document.querySelector("aside.content-minicart-modal");
      if (old) old.outerHTML = outer;
      else document.body.insertAdjacentHTML("beforeend", outer);
    }, drawer);
  }
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

// The search box's dropdown as Amasty renders it, for the autocomplete stub.
{
  const html = readFileSync(join(src, "search-autocomplete.html"), "utf8");
  await page.setContent(html, { waitUntil: "domcontentloaded" });
  const fragment = await page.evaluate(() => {
    const section = document.querySelector(".amsearch-result-section");
    if (!section) return "";
    section.querySelectorAll("script, style").forEach((el) => el.remove());
    section.querySelectorAll("svg").forEach((svg) => svg.replaceChildren());
    section.querySelectorAll("[data-bind], [data-mage-init]").forEach((el) => {
      el.removeAttribute("data-bind");
      el.removeAttribute("data-mage-init");
    });
    const walker = document.createTreeWalker(section, NodeFilter.SHOW_COMMENT);
    const comments = [];
    for (let n = walker.nextNode(); n; n = walker.nextNode()) comments.push(n);
    comments.forEach((c) => c.remove());
    section.querySelectorAll(".amsearch-products-section li.amsearch-item").forEach((li, i) => i >= 6 && li.remove());
    return section.innerHTML;
  });
  const out = fragment.replace(/\n\s*\n+/g, "\n").replace(/[ \t]{2,}/g, " ");
  writeFileSync(join(here, "pages", "autocomplete.html"), out);
  console.log(`autocomplete.html: ${(out.length / 1024).toFixed(1)} KB`);
}

await browser.close();
