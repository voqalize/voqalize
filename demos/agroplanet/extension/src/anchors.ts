/**
 * What the adapter matches on and reports, kept out of Chrome's translation.
 *
 * The owner's Chrome translates Spanish pages into English. Translated,
 * "Marca" can become "Brand", "Especificaciones" "Specifications", "Menor
 * precio" "Lowest price", and a heading or option Javier was told
 * by the brain no longer matches; the names he reports would no longer match
 * the catalogue either. Two layers keep the moves working whatever the
 * visitor reads:
 *
 *   1. The elements the adapter matches on or reads aloud carry
 *      `translate="no"` and class `notranslate`, which Chrome's translator
 *      honours, from `document_start` (`anchor.ts`) and again on every change
 *      (the Angular app draws every route after the document and re-draws
 *      the filter panel on every filter),
 *      before the translator gets to them. The rest of the page still
 *      translates.
 *   2. The logic never depends on a Spanish label where a structural signal
 *      exists: products by the SKU in their links, the page's kind by its
 *      route, the quote form's fields by their `formcontrolname`, the
 *      stepper's − and + by their icons, what a filter put on by the store's
 *      own answer (`page.ts`, `agroplanet-actions.ts`).
 */

/** Headings and the home's section titles; the policy pages' panel titles;
 *  the category menu and its flyout; the filter panel and the sort menu;
 *  product names on cards, the product page, the cart and the quote's
 *  summary; the product page's section titles and specifications; the store
 *  cards; the quote form's labels and its región and comuna options; and
 *  every button a cart or quote move presses or reads (Agregar al carro and
 *  its stepper, the price box with "Confirmar precio en tienda", the cart
 *  line's Eliminar and its confirmation, the cart's Cotizar and totals, the
 *  quote's selects, summary and Crear cotización, the product page's Ver
 *  más, the pagers, the menu's toggle), and every Material icon, whose words
 *  ("add", "remove") are the stepper's + and −. The moves find these by
 *  structure where they can; this keeps the words the brain and the moves
 *  name them by (pcfactory dev call 9ec9601a). */
const ANCHORS = [
  "mat-sidenav-content h1", "mat-sidenav-content h2", "mat-sidenav-content h3", "mat-sidenav-content h4",
  "app-category-home div.fw-700.fs18", "mat-panel-title",
  "#acordeon-main .item-menu-headline", "#acordeon-main app-submenu-desktop",
  "app-plp-filter", ".cdk-overlay-container .mat-menu-panel", "a.mat-menu-trigger",
  "app-plp-grid p.title", "app-plp-grid .black-text", "app-product-card p.title",
  "app-product-info h2.black-name", "app-product-info a.black-brand", "app-product-tabs .title", "app-product-tabs .mt-20",
  "app-cart-product h3", "app-resumen a", "app-store-list mat-card .fs20", "app-store-list .field-mobile",
  "app-form-user-quote mat-label", ".cdk-overlay-container mat-option", "#suggestContainer",
  // The buttons and words the cart and quote moves press or read: kept in
  // Spanish, as the moves name them.
  "mat-icon", "app-product-info #addToCart", "app-product-info #addToCart2", "app-product-info app-input-update-quantity",
  "app-product-info .prices-plp", "app-plp-grid .prices", "app-cart-product a:not([href])", "app-cart button",
  "app-cart .text-right", "app-cart b", ".cdk-overlay-container mat-dialog-container", "app-resumen",
  "app-form-user-quote mat-select", "app-form-user-quote button", "app-product-tabs button.swatchButton",
  "app-custom-paginator-controls", "app-store-list pagination-controls", "app-store-list mat-card",
  "app-menu-desktop .hamburger-menu-icon",
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
  for (const el of root.querySelectorAll("mat-sidenav-content h1, mat-sidenav-content h2, mat-sidenav-content h3, mat-sidenav-content h4, app-category-home div.fw-700.fs18, mat-panel-title > *")) {
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
    for (const r of roots) {
      if (r instanceof Node && !r.isConnected) continue;
      anchor(r);
      // A route the app just drew: its headings' own words kept too.
      if (document.readyState !== "loading") remember(r);
    }
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
  // The app draws its routes after the document is parsed, so headings are
  // remembered then and once more when they have come in, and again as each
  // route draws (the watcher above sees them come).
  const later = () => {
    remember();
    setTimeout(() => remember(), 2500);
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", later, { once: true });
  else later();
}
