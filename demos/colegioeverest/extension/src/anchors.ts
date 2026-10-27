/**
 * What the adapter matches on, kept out of Chrome's translation.
 *
 * The site is in Spanish only, and a visitor whose Chrome translates it into
 * English sees "Admission Dates" where the adapter may look for "Fechas de
 * Postulación". The Clini guide learned this on a live call. Most moves here go
 * by the catalogue's selectors (GenerateBlocks' classes, slick's arrows, the
 * contact form's field names), which translation does not touch; two layers
 * keep the rest working whatever the visitor reads:
 *
 *   1. The elements matched by their words carry `translate="no"` and class
 *      `notranslate`, which Chrome's translator honours, from
 *      `document_start` (`anchor.ts`) and again on every change, before the
 *      translator gets to them: the headings and the GenerateBlocks headlines.
 *      The rest of the page still translates.
 *   2. Each anchor's own words are kept in `data-voqalize-text` once the page
 *      is parsed, before the translator runs.
 */

/** Headings, GenerateBlocks' headlines, and anything of ours. */
const ANCHORS = [
  "h1", "h2", "h3", "h4", "h5",
  ".gb-headline",
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

/** Keep each anchor's own words in `data-voqalize-text`, before any translation. */
export function remember(root: ParentNode = document): void {
  for (const el of root.querySelectorAll(ANCHORS)) {
    if (el.hasAttribute("data-voqalize-text") || el.closest("[data-voqalize]") || el.tagName === "SELECT") continue;
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
    for (const r of records) for (const n of r.addedNodes) if (n instanceof Element) pending.add(n);
    if (pending.size && !queued) {
      queued = true;
      // A microtask: before the translator, which works on a later task.
      queueMicrotask(flush);
    }
  });
  obs.observe(document, { childList: true, subtree: true });
  if (document.documentElement) anchor(document);
  const parsed = () => {
    anchor(document);
    remember();
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", parsed, { once: true });
  else parsed();
}
