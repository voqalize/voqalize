/**
 * What the adapter matches on, kept out of Chrome's translation.
 *
 * The site is in Spanish only, and a parent whose Chrome translates it into
 * English sees "1st GRADE" and "Reference values" where the adapter looks for
 * "1º BÁSICO" and "Valores referenciales" — the words the brain knows them by.
 * The Clini guide learned this on a live call. Two layers keep the moves
 * working whatever the visitor reads:
 *
 *   1. The elements the adapter matches on carry `translate="no"` and class
 *      `notranslate`, which Chrome's translator honours, from
 *      `document_start` (`anchor.ts`) and again on every change, before the
 *      translator gets to them: the headings, the accordions' buttons, and the
 *      admission page's lines with the fees and the admission status, so they
 *      are read as the school wrote them. The rest of the page still
 *      translates.
 *   2. Each anchor's own words are kept in `data-voqalize-text` once the page
 *      is parsed, before the translator runs, and the logic prefers
 *      structural signals (an accordion is its button and its pane, a fee is
 *      "UF" and a number) over Spanish labels.
 */

/** Headings, accordion buttons, card titles and anything of ours. */
const ANCHORS = [
  "h1", "h2", "h3", "h4", "h5",
  ".accordion-button",
  ".card-title",
  "[data-voqalize]",
].join(", ");

/** A line the brain is read live: a fee ("UF 85") or an admission line. */
const LIVE_LINE = /\bUF\s*\d|^\s*admisi[oó]n\b/i;

/** Keep one element out of the translator. */
export function untranslated(el: Element): void {
  if (el.getAttribute("translate") !== "no") el.setAttribute("translate", "no");
  if (!el.classList.contains("notranslate")) el.classList.add("notranslate");
}

/** Mark everything the adapter matches on, under `root`. */
export function anchor(root: ParentNode = document): void {
  if (root instanceof Element && root.matches(ANCHORS)) untranslated(root);
  for (const el of root.querySelectorAll(ANCHORS)) untranslated(el);
  if (!/^\/admision\//i.test(location.pathname)) return;
  const paragraphs = root instanceof Element && root.matches("p") ? [root] : [...root.querySelectorAll("main p")];
  for (const p of paragraphs) if (LIVE_LINE.test(p.textContent ?? "")) untranslated(p);
}

/** Keep each anchor's own words in `data-voqalize-text`, before any translation. */
export function remember(root: ParentNode = document): void {
  for (const el of root.querySelectorAll(ANCHORS)) {
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
