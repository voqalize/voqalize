/**
 * What the adapters match on, kept out of Chrome's translation.
 *
 * The site is in Spanish only, and the owner tests with Chrome's translation
 * on: a translated page says "Opening hours" where the clinic page says
 * "Horario de atención", and "Select the reason" over the booking's motivos.
 * Most moves here go by the catalogue's selectors (`catalogue.ts`), which
 * translation does not touch; three layers keep the rest working whatever the
 * visitor reads:
 *
 *   1. The elements matched by their words carry `translate="no"` and class
 *      `notranslate`, which Chrome's translator honours, from
 *      `document_start` (`anchor.ts`) and again on every change, before the
 *      translator gets to them: headings, FAQ questions, the booking's
 *      selects, calendar, hours and summary, the forms' region lists.
 *   2. Each anchor's own words are kept in `data-voqalize-text` once the page
 *      is parsed, before the translator runs.
 *   3. A clinic page's facts (name, address, hours, references, the maps
 *      link) are read once the page is parsed, before any translation, and
 *      kept on `<html data-voqalize-clinic>` for the adapter (`clinicInfo`).
 */

/** Anchors on the site's pages. */
const SITE_ANCHORS = [
  "h1", "h2", "h3", "h4", "h5",
  "[id^=heading-faq-]",
  "summary",
  ".e-n-accordion-item-title",
  "#myTab a",
  "#mapa-list h3",
  ".card-location h3",
  "#REGION_2", "#COMUNA_2", "#NUMERO_DE_TRABAJADORES",
  "#mensaje",
  "[data-voqalize]",
].join(", ");

/** Anchors on the booking, by Dentalsoft's own ids. */
const BOOKING_ANCHORS = [
  "#dentalsoft-form fieldset h1", "#dentalsoft-form fieldset h2", "#dentalsoft-form fieldset h3",
  "#motivo", "#region", "#comuna", "#sucursal",
  "#datepicker-fecha",
  "#horarios",
  "#alert_sin_horarios",
  "#data-reserva",
  ".user_name",
  "#dentalsoft-error",
  "[data-voqalize]",
].join(", ");

const onBooking = () => /^\/agenda-tu-hora(\/|$)/i.test(location.pathname);

/** Keep one element out of the translator. */
export function untranslated(el: Element): void {
  if (el.getAttribute("translate") !== "no") el.setAttribute("translate", "no");
  if (!el.classList.contains("notranslate")) el.classList.add("notranslate");
}

/** Mark everything the adapter on this page matches on, under `root`. */
export function anchor(root: ParentNode = document): void {
  const selector = onBooking() ? BOOKING_ANCHORS : SITE_ANCHORS;
  if (root instanceof Element && root.matches(selector)) untranslated(root);
  for (const el of root.querySelectorAll(selector)) untranslated(el);
}

/** Keep each anchor's own words in `data-voqalize-text`, before any translation. */
export function remember(root: ParentNode = document): void {
  if (onBooking()) return;
  for (const el of root.querySelectorAll(SITE_ANCHORS)) {
    if (el.hasAttribute("data-voqalize-text") || el.closest("[data-voqalize]") || el.tagName === "SELECT") continue;
    const text = (el.textContent ?? "").replace(/\s+/g, " ").trim();
    if (text) el.setAttribute("data-voqalize-text", text);
  }
}

// ─── A clinic's page ─────────────────────────────────────────────────────────

/** What a clinic's own page says about it, in the page's own words. */
export interface ClinicInfo {
  name: string;
  address: string;
  hours: string;
  references: string;
  maps_url: string;
}

const CLINIC_KEY = "data-voqalize-clinic";
const tidy = (s: string | null | undefined) => (s ?? "").replace(/[​ ]/g, " ").replace(/\s+/g, " ").trim();
/** Lines of `el`'s text, one per `<br>` or block. */
function lines(el: Element | null | undefined): string[] {
  if (!el) return [];
  const copy = el.cloneNode(true) as Element;
  copy.querySelectorAll("br").forEach((br) => br.replaceWith("\n"));
  copy.querySelectorAll("p, div, li").forEach((b) => b.append("\n"));
  return (copy.textContent ?? "").split(/\n+/).map(tidy).filter(Boolean);
}

export const isClinicPage = (path = location.pathname) => /^\/clinicas\/[^/]+\/?$/i.test(path);

/**
 * Read a clinic page (`/clinicas/<slug>/`): its name (the hero's
 * "Uno Salud <name>", else the breadcrumb's last item), its address (the line
 * with the map marker), the box under "Horario de atención" and the one under
 * "Referencias", and its "¿Cómo llegar?" link to Google Maps (made from the
 * marker's coordinates when the link is missing).
 */
export function readClinic(doc: Document = document): ClinicInfo | null {
  const hero = doc.querySelector("main#site-main > header, main > header");
  if (!hero) return null;
  const name =
    tidy(hero.querySelector("h2.sr-only, h2")?.textContent).replace(/^Uno Salud\s+/i, "") ||
    tidy(doc.querySelector(".breadcrumb_last")?.textContent);
  const marker = [...hero.querySelectorAll("p")].find((p) => p.querySelector(".fa-map-marker, .fa-map-marker-alt") && !p.closest(".card-location"));
  const address = tidy(marker?.textContent).replace(/\s+,/g, ",");
  /** The lines after the bold label `label`, up to the next bold label. */
  const block = (label: RegExp) => {
    const head = [...hero.querySelectorAll("b, strong")].find((el) => label.test(tidy(el.textContent)));
    const p = head?.closest("p") ?? head?.parentElement;
    if (!p) return "";
    const out: string[] = [];
    for (let next = p.nextElementSibling; next; next = next.nextElementSibling) {
      if (next.querySelector("b, strong") && tidy(next.textContent).length < 40) break;
      out.push(...lines(next));
    }
    return out.join("; ");
  };
  const hours = block(/^horario de atenci[oó]n/i);
  const references = block(/^referencias/i);
  const link = hero.querySelector<HTMLAnchorElement>("#mapa-single a[href*='google.com/maps'], #mapa-single a[href*='maps.google'], a[href*='google.com/maps/dir']");
  let maps = link?.href ?? "";
  if (!maps) {
    const m = hero.querySelector<HTMLElement>("#mapa-single .marker[data-lat][data-lng], .marker[data-lat][data-lng]");
    if (m) maps = `https://www.google.com/maps/dir/?api=1&destination=${m.dataset.lat},${m.dataset.lng}`;
  }
  if (!name && !address && !hours) return null;
  return { name, address, hours, references, maps_url: maps };
}

/** The clinic's facts as the page had them before any translation. */
export function clinicInfo(): ClinicInfo | null {
  if (!isClinicPage()) return null;
  const kept = document.documentElement.getAttribute(CLINIC_KEY);
  if (kept) {
    try {
      return JSON.parse(kept) as ClinicInfo;
    } catch {
      /* Read it again. */
    }
  }
  return readClinic();
}

function keepClinic(): void {
  if (!isClinicPage() || document.documentElement.hasAttribute(CLINIC_KEY)) return;
  const info = readClinic();
  if (info) document.documentElement.setAttribute(CLINIC_KEY, JSON.stringify(info));
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
    keepClinic();
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", parsed, { once: true });
  else parsed();
}
