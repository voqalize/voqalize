/**
 * What the adapter matches on, kept out of Chrome's translation.
 *
 * A visitor whose Chrome translates the university's pages into English would
 * see "Requirements and Fees" and "Tuition $277,456" where the adapter looks
 * for "Requisitos y Aranceles" and "Matrícula $277.456", and every cue the
 * brain wrote with the site's Spanish headings would miss. So the elements the
 * adapter matches on carry `translate="no"` and class `notranslate`, which
 * Chrome's translator honours, from `document_start` (`anchor.ts`) and again on
 * every change, before the translator gets to them: headings, the tab, pill
 * and accordion labels, the Carreras menu, the career's data and fee tables,
 * the visit cards' titles and buttons, the lead form, and our own widget. The
 * rest of the page still translates.
 *
 * The page's own language as it arrived is stamped on `<html>`
 * (`data-voqalize-lang`), so the adapter can tell the brain the page was
 * translated after all (`page_changed.translated`).
 */

const ANCHORS = [
  "h1", "h2", "h3", "h4", "h5",
  "[data-bs-toggle]",
  ".accordion-button",
  "#collapseCarreras p", "#collapseCarreras a",
  "#malla th", "#malla td", "#malla audio + p", "#malla p",
  "#requisitos_carrera td", "#requisitos_carrera th", "#requisitos_carrera p", "#requisitos_carrera li",
  "#collapseRequisitos li", "#collapseRequisitos p", "#collapseRequisitos h5",
  ".campo-programa",
  ".card-title", ".card-text", ".card .mt-auto a", ".card .mt-auto button",
  "form#admisionForm",
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

/** The page's language as the server sent it, before any translation. */
function stampLanguage(): void {
  const html = document.documentElement;
  if (html && !html.hasAttribute("data-voqalize-lang")) html.setAttribute("data-voqalize-lang", html.lang || "");
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
    stampLanguage();
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
  if (document.documentElement) {
    stampLanguage();
    anchor(document);
  }
}
