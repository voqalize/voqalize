/**
 * What the adapters match on, kept out of Chrome's translation.
 *
 * A visitor whose Chrome translates Clini's pages into English sees "HEALTH
 * CENTER | QUINTA VERGARA" and "Thursday, October 22, 2026 with schedule
 * available" where the adapters look for "CENTRO DE SALUD | QUINTA VERGARA" and
 * "con agenda". Two layers keep the moves working whatever the visitor reads:
 *
 *   1. The elements the adapters match on carry `translate="no"` and class
 *      `notranslate`, which Chrome's translator honours, from
 *      `document_start` (`anchor.ts`) and again on every change, before the
 *      translator gets to them. The rest of the page still translates.
 *   2. The logic never depends on a Spanish label where a structural signal
 *      exists: a day's date is stamped on its button (`data-voqalize-date`)
 *      the moment the booking renders it, read from its label while that is
 *      still the page's own, else from its day number and its month; a day's
 *      availability is its class; a centre is compared on its name after "|".
 */

/** Anchors on www.clini.cl: headings, FAQ questions and every dropdown's
 *  toggle (a sede's "Ver horarios" too), tab links, the sedes' names. */
const SITE_ANCHORS = [
  "h1", "h2", "h3", "h4",
  ".w-dropdown-toggle",
  ".faq-question",
  "summary",
  ".w-tab-link",
  ".caja-ubicaciones h5", ".caja-ubicaciones h6",
  ".w-dyn-item h5", ".w-dyn-item h6",
  "[data-voqalize]",
].join(", ");

/** Anchors on agenda-web.clini.cl, by the booking's own stable ids. */
const AGENDA_ANCHORS = [
  "#calendarMonths",
  "#calendarMonthStatus",
  "#timesGrid .center-title",
  "#timesTitle",
  "button.time-button",
  ".service-name",
  "#prestacionSearch",
  "#prestacionOptionsList",
  "#prestacionSelect",
  "#regionSelect",
  "#selectedSummary",
  "#availabilityDescription",
  "#patientLookupStatus",
  "#btnDocumentRut",
  "#btnDocumentPassport",
  "#patientDocumentLabel",
  "#appointmentCenter",
  "#appointmentService",
  "#appointmentBenefit",
  "#appointmentDate",
  "#appointmentTime",
  "#appointmentAddress",
  "[data-voqalize]",
].join(", ");

const onAgenda = () => /^agenda-web\.clini\.cl$/i.test(location.host);

/** Keep one element out of the translator. */
export function untranslated(el: Element): void {
  if (el.getAttribute("translate") !== "no") el.setAttribute("translate", "no");
  if (!el.classList.contains("notranslate")) el.classList.add("notranslate");
}

function mark(root: ParentNode, selector: string): void {
  if (root instanceof Element && root.matches(selector)) untranslated(root);
  for (const el of root.querySelectorAll(selector)) untranslated(el);
}

// ─── The booking's calendar ────────────────────────────────────────────────

const MONTHS_ES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];
const MONTHS_EN = [
  "january", "february", "march", "april", "may", "june",
  "july", "august", "september", "october", "november", "december",
];

const fold = (s: string | null | undefined) =>
  (s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
const pad = (n: number | string) => String(n).padStart(2, "0");
const monthIndex = (word: string) => {
  const w = fold(word);
  const es = MONTHS_ES.indexOf(w);
  if (es >= 0) return es + 1;
  const en = MONTHS_EN.findIndex((m) => m === w || (w.length >= 3 && m.startsWith(w)));
  return en >= 0 ? en + 1 : 0;
};

/** A day button's label, Spanish ("jueves, 22 de octubre de 2026 con agenda
 *  disponible") or as Chrome translates it ("Thursday, October 22, 2026 …"),
 *  as "2026-10-22". */
export function isoOfLabel(label: string | null | undefined): string | null {
  const t = fold(label);
  let m = t.match(/(\d{1,2}) de ([a-z]+) de (\d{4})/);
  if (m) {
    const month = monthIndex(m[2]);
    return month ? `${m[3]}-${pad(month)}-${pad(m[1])}` : null;
  }
  m = t.match(/([a-z]+) (\d{1,2}),? (\d{4})/);
  if (m) {
    const month = monthIndex(m[1]);
    return month ? `${m[3]}-${pad(month)}-${pad(m[2])}` : null;
  }
  m = t.match(/(\d{1,2}) (?:of )?([a-z]+),? (\d{4})/);
  if (m) {
    const month = monthIndex(m[2]);
    return month ? `${m[3]}-${pad(month)}-${pad(m[1])}` : null;
  }
  return null;
}

/** A month's title, "Octubre 2026" or "October 2026", as "2026-10". */
export function monthOfTitle(title: string | null | undefined): string | null {
  const m = fold(title).match(/([a-z]+)(?: de)? (\d{4})/);
  if (!m) return null;
  const month = monthIndex(m[1]);
  return month ? `${m[2]}-${pad(month)}` : null;
}

/**
 * Stamp each day of the booking's calendar with its date, and each month card
 * with its month. agenda-web draws one month at a time, a button per day from
 * the 1st, after the week's leading fillers, so a button's date is its label
 * read before any translation, else its month and its day number.
 */
export function stampCalendar(root: ParentNode = document): void {
  for (const card of root.querySelectorAll<HTMLElement>("#calendarMonths .calendar-month-card")) {
    const buttons = [...card.querySelectorAll<HTMLButtonElement>("button.calendar-day-button")];
    if (!buttons.length) continue;
    let month = card.dataset.voqalizeMonth ?? null;
    if (!month) {
      for (const b of buttons) {
        const iso = b.dataset.voqalizeDate ?? isoOfLabel(b.getAttribute("aria-label"));
        if (iso) {
          month = iso.slice(0, 7);
          break;
        }
      }
      month ??= monthOfTitle(card.querySelector(".calendar-month-title")?.textContent);
      if (month) card.dataset.voqalizeMonth = month;
    }
    buttons.forEach((b, i) => {
      if (b.dataset.voqalizeDate) return;
      const fromLabel = isoOfLabel(b.getAttribute("aria-label"));
      const n = Number((b.querySelector(".calendar-day-number")?.textContent ?? "").trim()) || i + 1;
      const iso = fromLabel ?? (month ? `${month}-${pad(n)}` : null);
      if (iso) b.dataset.voqalizeDate = iso;
    });
  }
}

/** Mark everything the adapter on this host matches on, under `root`. */
export function anchor(root: ParentNode = document): void {
  if (onAgenda()) {
    mark(root, AGENDA_ANCHORS);
    stampCalendar(document);
  } else {
    mark(root, SITE_ANCHORS);
  }
}

/**
 * On www.clini.cl, keep each anchor's own words in `data-voqalize-text` once
 * the page is parsed, before the translator runs: should Chrome translate it
 * anyway (the visitor's "translate this part too"), a move still finds it by
 * the words the brain knows it by.
 */
export function remember(root: ParentNode = document): void {
  if (onAgenda()) return;
  for (const el of root.querySelectorAll(SITE_ANCHORS)) {
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
  obs.observe(document, { childList: true, subtree: true, attributes: true, attributeFilter: ["aria-label", "class"] });
  if (document.documentElement) anchor(document);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => remember(), { once: true });
  else remember();
}
