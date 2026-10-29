/**
 * What the adapter matches on and reports, kept out of Chrome's translation.
 *
 * The owner's Chrome translates Spanish pages into English. Translated,
 * "Marcas" can become "Brands", "Especificaciones" "Specifications", "Precio
 * menor a mayor" "Price low to high", and a heading or option Javier was told
 * by the brain no longer matches; the names he reports would no longer match
 * the catalogue either. Two layers keep the moves working whatever the
 * visitor reads:
 *
 *   1. The elements the adapter matches on or reads aloud carry
 *      `translate="no"` and class `notranslate`, which Chrome's translator
 *      honours, from `document_start` (`anchor.ts`) and again on every change
 *      (the Vue widgets render after load and re-render on every filter),
 *      before the translator gets to them. The rest of the page still
 *      translates.
 *   2. The logic never depends on a Spanish label where a structural signal
 *      exists: filter groups by their header's id, product ids from links and
 *      `data-gtag-id`, tabs by id (`#specifics-tab`), stock rows by class, the
 *      checkout by its path and its cards (`page.ts`).
 */

/** Headings and FAQ questions in the main column; the filter panel, its
 *  applied-filter chips, the sort and page-size menus; product names on
 *  cards, rails, the product page, the cart, the "Producto agregado" window
 *  and the comparator; the comparison page's table (its row labels, values
 *  and group titles); the product page's tab titles, specifications and stock
 *  by store, and its pickup window; the Categorías menu; the store cards;
 *  coupon codes; the listing's count. */
const ANCHORS = [
  "#main-layout h1", "#main-layout h2", "#main-layout h3", "#main-layout h4",
  "#main-layout .accordion-button",
  "#panel-filters .panel-filters__filter__header", "#panel-filters label", ".pcf-select__dropdown",
  "a.products__item h3", ".products__item__info__brand", ".rr-item__name",
  "#product-title", "#tabs", "#specifics", "#stock",
  ".card-list-product__name", ".title-count-cart", ".purchase-summary",
  "#pcf-modal-added-product .modal-body", "#pcf-comparator-summary h2",
  "section.panel-filters-applied", "#pcf-comparator .comparator-table", "#pcf-comparator .table-title-custom",
  "#pickup-modal .stock__list", "#categories-dropdown-list", ".categories-dropdown-list__panel",
  ".card-tabs h3", ".card-tabs h6", ".ticket-cupon-text",
  "p.d-block.mb-12",
  "[data-voqalize]",
].join(", ");

/** Keep one element out of the translator. */
export function untranslated(el: Element): void {
  if (el.getAttribute("translate") !== "no") el.setAttribute("translate", "no");
  if (!el.classList.contains("notranslate")) el.classList.add("notranslate");
}

/** Mark everything the adapter matches on, under `root`. */
export function anchor(root: ParentNode = document): void {
  if (root instanceof Element && root.matches(ANCHORS)) untranslated(root);
  for (const el of root.querySelectorAll(ANCHORS)) untranslated(el);
}

/**
 * Keep each heading's own words in `data-voqalize-text` once the page is
 * parsed, before the translator runs: should Chrome translate it anyway, a
 * move still finds it by the words the brain knows it by.
 */
export function remember(root: ParentNode = document): void {
  for (const el of root.querySelectorAll("#main-layout h1, #main-layout h2, #main-layout h3, #main-layout h4")) {
    if (el.hasAttribute("data-voqalize-text") || el.closest("[data-voqalize]")) continue;
    const text = (el.textContent ?? "").replace(/\s+/g, " ").trim();
    if (text) el.setAttribute("data-voqalize-text", text);
  }
}

let watching = false;

/** Anchor the page now and on every change, for as long as it lives. */
export function watchAnchors(): void {
  if (watching) return;
  watching = true;
  let queued = false;
  const pending = new Set<ParentNode>();
  const flush = () => {
    queued = false;
    const roots = [...pending];
    pending.clear();
    for (const r of roots) if (!(r instanceof Node) || r.isConnected) anchor(r);
  };
  const obs = new MutationObserver((records) => {
    for (const r of records) {
      for (const n of r.addedNodes) if (n instanceof Element) pending.add(n);
      if (r.type === "attributes" && r.target instanceof Element) pending.add(r.target);
    }
    if (pending.size && !queued) {
      queued = true;
      // A microtask: before the translator, which works on a later task.
      queueMicrotask(flush);
    }
  });
  obs.observe(document, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });
  if (document.documentElement) anchor(document);
  // The Vue widgets render their headings after the page is parsed, so they
  // are remembered then and once more when they have come in.
  const later = () => {
    remember();
    setTimeout(() => remember(), 2500);
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", later, { once: true });
  else later();
}
