/**
 * What the adapter matches on and reports, kept out of Chrome's translation.
 *
 * The owner's Chrome translates Spanish pages into English. Translated, "2
 * Plazas" can become "2 Seats", "Sábanas" "Sheets", "Especificaciones"
 * "Specifications", and a heading Javier was told by the brain no longer
 * matches; the names he reports would no longer match the catalogue either.
 * Two layers keep the moves working whatever the visitor reads:
 *
 *   1. The elements the adapter matches on or reads aloud carry
 *      `translate="no"` and class `notranslate`, which Chrome's translator
 *      honours, from `document_start` (`anchor.ts`) and again on every change
 *      (filters and the search dropdown re-render by AJAX), before the
 *      translator gets to them. The rest of the page still translates.
 *   2. The logic never depends on a Spanish label where a structural signal
 *      exists: filters by `data-qf-request-var` and the option's `title`,
 *      prices by `data-price-amount`, stock by class, tabs by id, checkout by
 *      id and role (`page.ts`).
 */

/** Headings and FAQ titles in the main column; the quick filters and the
 *  full filter drawer; product names on cards, in the search dropdown, on the
 *  product page and in the bag; the product page's tab titles and its
 *  specifications table; the listing's count. */
const ANCHORS = [
  "#maincontent h1", "#maincontent h2", "#maincontent h3", "#maincontent h4",
  "#maincontent [data-role=title]", "#maincontent .accordion-title", "#maincontent summary",
  ".qf__group", ".qf__option-link", ".qf__pill-label",
  "#layered-filter-block .filter-options-title", "#layered-filter-block a",
  "a.product-item-link", ".amsearch-result-section .amsearch-link",
  "h1.product-name", ".product-brand-title", ".product.data.items > .data.item.title",
  "#product-attribute-specs-table",
  ".mc-line__name", ".product-item-name",
  ".toolbar-amount", "#sorter",
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
  for (const el of root.querySelectorAll("#maincontent h1, #maincontent h2, #maincontent h3, #maincontent h4")) {
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
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => remember(), { once: true });
  else remember();
}
