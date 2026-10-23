/**
 * The booking adapter: agenda-web.clini.cl, where labs, imaging and cardiology
 * are booked. ASP.NET Razor Pages, one page per `servicio`
 * (`/?servicio=64&prestacion=804`), with a vanilla-JS controller that keeps
 * every control's id stable:
 *
 *   step 1  `section.search-card`: region `#regionSelect`, prestación (a
 *           combobox over the hidden native `#prestacionSelect`), and
 *           `#btnBuscar`. A deep link with `prestacion` searches by itself.
 *   results `#calendarMonths` (one month at a time, `#nextCalendarMonth`), day
 *           buttons named by their `aria-label` ("jueves, 22 de octubre de 2026
 *           con agenda disponible"), `#btnPeriodAm`/`#btnPeriodPm`, one
 *           `section.center-group` per centre (only the first open; the rest
 *           open by their `.center-toggle`), `button.time-button`, "Ver más
 *           horas", `#selectedSummary` and `#btnContinuar`.
 *   step 2  `section#bookingStep` (after the service's notice
 *           `#serviceIndicationAlert`, "Entendido"): the visit's summary and
 *           `#patientForm`, which ends in `#btnAgendar` ("AGENDAR").
 *   done    `#bookingSuccessStep`.
 *
 * What Javier never does here, whatever he is asked: press `#btnAgendar` (the
 * visitor books, after reCAPTCHA, by their own press), tick `#consentPrivacy`
 * (it is the visitor's consent to give), or type into `#patientRut` (the RUT is
 * the visitor's to type; a valid one makes the page look the patient up, which
 * is theirs to start). He points at those, and rings them.
 *
 * The booking's state goes to the brain as `agenda_state`, on load and after
 * every change, whoever made it.
 */

import { isoOfLabel, stampCalendar } from "./anchors";
import {
  best, chileanMobile, clean, highlight, leave, norm, pickOption, quiet, scrollTo, setValue, sleep, visible, waitFor,
} from "./page";

const SEARCH_MS = 20_000;
const DEBOUNCE_MS = 400;
/** Every open day of the month on screen. */
const MAX_DAYS = 31;
const MAX_TIMES = 24;
const MAX_INDICATIONS = 600;

const byId = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T | null;
const shownEl = (id: string) => visible(byId(id));

// ─── Reading the page ─────────────────────────────────────────────────────

/**
 * A day button's date, "2026-10-22": the stamp `anchors.ts` put on it when the
 * booking drew it (read from its label while that was still Spanish, else from
 * its month and day number), else its label now, in either language.
 */
function dateOf(b: HTMLElement): string | null {
  if (!b.dataset.voqalizeDate) stampCalendar();
  return b.dataset.voqalizeDate ?? isoOfLabel(b.getAttribute("aria-label"));
}

const dayButtons = () => [...document.querySelectorAll<HTMLButtonElement>("#calendarMonths button.calendar-day-button")];
/** A day with hours, by the booking's own classes, never its label's words:
 *  `is-available`, not disabled (a day without is `no-availability` or
 *  `is-out-of-range`, and disabled). */
const hasTimes = (b: HTMLButtonElement) =>
  !b.disabled &&
  b.getAttribute("aria-disabled") !== "true" &&
  !b.classList.contains("no-availability") &&
  !b.classList.contains("is-out-of-range") &&
  (b.classList.contains("is-available") || Boolean(b.querySelector(".calendar-day-availability-dot")));
const availableDays = () => dayButtons().filter(hasTimes);
const activeDay = () => dayButtons().find((b) => b.classList.contains("active")) ?? null;
const groups = () => [...document.querySelectorAll<HTMLElement>("#timesGrid section.center-group")];
const titleOf = (g: HTMLElement) => clean(g.querySelector(".center-title")?.textContent);
const isOpen = (g: HTMLElement) =>
  g.classList.contains("is-open") || g.querySelector(".center-toggle")?.getAttribute("aria-expanded") === "true";
const timeButtons = (g: ParentNode) => [...g.querySelectorAll<HTMLButtonElement>("button.time-button")];

const resultsShown = () =>
  Boolean(byId("schedulerGrid")?.classList.contains("has-results") || byId("availabilityColumn")?.classList.contains("show"));
const bookingShown = () => byId("bookingStep")?.getAttribute("aria-hidden") === "false" || Boolean(byId("bookingStep")?.classList.contains("show"));
const doneShown = () => {
  const s = byId("bookingSuccessStep");
  return Boolean(s && (s.classList.contains("show") || (visible(s) && s.getAttribute("aria-hidden") !== "true")));
};

function servicio(): number | null {
  const v = new URLSearchParams(location.search).get("servicio") ?? byId<HTMLInputElement>("appointmentServiceCode")?.value;
  const n = Number(v);
  return v && Number.isFinite(n) ? n : null;
}

function selected(sel: HTMLSelectElement | null): { value: number | null; text: string } {
  const o = sel?.selectedOptions[0];
  const n = Number(o?.value);
  return { value: o?.value && Number.isFinite(n) ? n : null, text: clean(o?.textContent) };
}

/** The patient fields still empty or refused, by the brain's names. A field
 *  the page disabled (a known patient's masked data) counts as done. */
/** The one patient field the page lets go empty. */
const OPTIONAL = ["maternal_last_name"];

function invalidFields(): string[] {
  const out: string[] = [];
  const fields: [string, string][] = [
    ["rut", "patientRut"],
    ["name", "patientName"],
    ["last_name", "patientLastName"],
    ["maternal_last_name", "patientMaternalLastName"],
    ["birth_date", "patientBirthDate"],
    ["sex", "patientSex"],
    ["phone", "patientPhone"],
    ["email", "patientEmail"],
  ];
  for (const [name, id] of fields) {
    const el = byId<HTMLInputElement | HTMLSelectElement>(id);
    // Disabled with a value: a registered patient's data, masked. Disabled
    // and empty: the page is waiting for the RUT before it opens the field.
    if (!el || (el.disabled && el.value.trim())) continue;
    const error = byId(`${id}Error`);
    const required = el.required || OPTIONAL.indexOf(name) < 0;
    const bad =
      (required && !el.value.trim()) ||
      el.classList.contains("is-invalid") ||
      Boolean(error && visible(error) && clean(error.textContent));
    if (bad) out.push(name);
  }
  const consent = byId<HTMLInputElement>("consentPrivacy");
  if (consent && !consent.checked) out.push("consent");
  return out;
}

export interface AgendaState {
  step: "search" | "results" | "booking" | "done";
  document: "rut" | "passport";
  centre: string;
  month: string;
  servicio: number | null;
  servicio_name: string;
  prestacion: number | null;
  prestacion_name: string;
  region: number | null;
  days: string[];
  centres: string[];
  day: string;
  times: string[];
  selected: string;
  indications: string;
  invalid: string[];
  ready: boolean;
}

export function agendaState(): AgendaState {
  const step = doneShown() ? "done" : bookingShown() ? "booking" : resultsShown() ? "results" : "search";
  const prest = selected(byId<HTMLSelectElement>("prestacionSelect"));
  const region = selected(byId<HTMLSelectElement>("regionSelect"));
  const open = groups().find(isOpen);
  const alert = byId("serviceIndicationAlert");
  const listed = step !== "search";
  const indications = [
    alert && visible(alert) ? clean(byId("serviceIndicationAlertText")?.textContent) : "",
    step === "booking"
      ? clean(byId("appointmentIndicationsContent")?.textContent ?? byId("appointmentIndications")?.textContent).replace(/\s*Ver más\.*\s*/g, " ")
      : "",
  ]
    .filter(Boolean)
    .join(" · ")
    .slice(0, MAX_INDICATIONS);
  const agendar = byId<HTMLButtonElement>("btnAgendar");
  return {
    step,
    document: documentType(),
    // The centre whose hours `times` are: the one group the booking opened.
    centre: listed && open ? titleOf(open) : "",
    month: listed ? (monthShown() ?? "") : "",
    servicio: servicio(),
    servicio_name: clean(document.querySelector(".service-box .service-name")?.textContent),
    prestacion: prest.value,
    prestacion_name: prest.text,
    region: region.value,
    days: listed ? openDays() : [],
    centres: listed ? groups().map(titleOf).filter(Boolean) : [],
    // agenda-web marks the chosen day `.active`: the day `times` belong to.
    day: listed ? ((() => { const a = activeDay(); return a ? (dateOf(a) ?? "") : ""; })()) : "",
    times: open ? timeButtons(open).filter(visible).map((b) => clean(b.textContent)).slice(0, MAX_TIMES) : [],
    selected: clean(byId("selectedSummary")?.textContent),
    indications,
    invalid: step === "booking" ? invalidFields() : [],
    ready: step === "booking" && Boolean(agendar && !agendar.disabled),
  };
}

/** The open days of the month on screen, YYYY-MM-DD. */
function openDays(): string[] {
  return [...new Set(availableDays().map(dateOf).filter((d): d is string => Boolean(d)))].slice(0, MAX_DAYS);
}

/** The patient form's document switch: RUT, or a passport for a visitor
 *  without one. */
function documentType(): "rut" | "passport" {
  const hidden = byId<HTMLInputElement>("patientDocumentType")?.value;
  if (hidden) return /pasaporte/i.test(hidden) ? "passport" : "rut";
  return byId("btnDocumentPassport")?.getAttribute("aria-pressed") === "true" ? "passport" : "rut";
}

export function agendaContext() {
  const headings = [...document.querySelectorAll<HTMLElement>("h1, h2, h3")]
    .filter((h) => visible(h) && !h.closest("[data-voqalize]"))
    .map((h) => clean(h.innerText))
    .filter((t) => t.length > 1);
  return {
    site: "agenda" as const,
    url: location.href,
    path: location.pathname + location.search,
    title: document.title,
    kind: "agenda",
    headings: [...new Set(headings)].slice(0, 30),
    faqs: [],
    plans: [],
  };
}

// ─── Reporting ────────────────────────────────────────────────────────────

let report: (() => void) | null = null;

/** Send `agenda_state` now (debounced), as a step ends. */
function reportNow(): void {
  report?.();
}

/**
 * Report the booking's state through `emit` on load and whenever it changes:
 * a step the brain asked for, or the visitor's own clicks and typing. Debounced,
 * and only when something the brain is told about changed.
 */
export function watchAgenda(emit: (event: string, payload: unknown) => void): () => void {
  let last = "";
  let timer: ReturnType<typeof setTimeout> | null = null;
  const send = () => {
    timer = null;
    const state = agendaState();
    const key = JSON.stringify(state);
    if (key === last) return;
    last = key;
    emit("agenda_state", state);
  };
  const soon = () => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(send, DEBOUNCE_MS);
  };
  const obs = new MutationObserver(soon);
  for (const id of ["schedulerGrid", "bookingStep", "bookingSuccessStep", "serviceIndicationAlert", "regionSelect", "prestacionSelect"]) {
    const el = byId(id);
    if (el) obs.observe(el, { childList: true, subtree: true, attributes: true, characterData: true, attributeFilter: undefined });
  }
  const form = byId("patientForm");
  form?.addEventListener("input", soon, true);
  form?.addEventListener("change", soon, true);
  report = soon;
  send();
  return () => {
    obs.disconnect();
    form?.removeEventListener("input", soon, true);
    form?.removeEventListener("change", soon, true);
    if (timer) clearTimeout(timer);
    if (report === soon) report = null;
  };
}

// ─── Steps ────────────────────────────────────────────────────────────────

/** The page's controller is up: the search card is there, and a deep link's
 *  own search (with `prestacion`) has come back. */
async function ready(): Promise<void> {
  const ok = await waitFor(() => byId("btnBuscar") || byId("bookingStep"), 10_000);
  if (!ok) throw new Error("the booking page did not load");
  if (new URLSearchParams(location.search).get("prestacion") && !resultsShown() && !bookingShown()) {
    await waitFor(() => resultsShown() || noResults(), SEARCH_MS);
  }
  const grid = byId("schedulerGrid");
  if (grid) await quiet(grid, 400, 4000);
  if (resultsShown() && !bookingShown()) await timesSettled();
}

/** The search came back with nothing to offer, in the page's words. */
function noResults(): string | null {
  const text = clean(byId("availabilityDescription")?.textContent);
  // In Spanish (the element is kept untranslated), or as Chrome put it.
  return /no (hay|existe|se encontr|fue posible)|sin disponibilidad|no (\w+ )?(found|available|availability)|could not find|unable to find/i.test(text)
    ? text
    : null;
}

async function search(): Promise<void> {
  const button = await waitFor(() => {
    const b = byId<HTMLButtonElement>("btnBuscar");
    return b && !b.disabled ? b : null;
  }, 6000);
  if (!button) throw new Error("the search button stays disabled: choose a region and a prestación first");
  const grid = byId("timesGrid");
  const before = grid?.innerHTML ?? "";
  highlight(button);
  button.click();
  await waitFor(() => (resultsShown() && (byId("timesGrid")?.innerHTML ?? "") !== before) || noResults(), SEARCH_MS);
  if (!noResults()) await timesSettled();
  const none = noResults();
  if (none) throw new Error(`no availability: ${none}`);
}

const dayList = () => openDays().join(", ");

/** The month on screen, as "YYYY-MM". */
function monthShown(): string | null {
  stampCalendar();
  const card = document.querySelector<HTMLElement>("#calendarMonths .calendar-month-card");
  if (card?.dataset.voqalizeMonth) return card.dataset.voqalizeMonth;
  const first = dayButtons()[0];
  return first ? (dateOf(first)?.slice(0, 7) ?? null) : null;
}

async function chooseDay(iso: string): Promise<void> {
  const want = iso.trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(want)) throw new Error(`"${iso}" is not a date as YYYY-MM-DD`);
  const find = () => dayButtons().find((b) => dateOf(b) === want);
  for (let n = 0; n < 4 && !find(); n++) {
    const shownMonth = monthShown();
    if (!shownMonth) break;
    const nav = byId<HTMLButtonElement>(want.slice(0, 7) < shownMonth ? "previousCalendarMonth" : "nextCalendarMonth");
    if (!nav || nav.disabled) break;
    nav.click();
    await quiet(byId("calendarMonths") ?? document.body, 300, 2000);
  }
  const day = find();
  if (!day) throw new Error(`the calendar does not reach ${iso}; days with times: ${dayList() || "none"}`);
  if (!hasTimes(day)) {
    throw new Error(`no times on ${iso}; days with times: ${dayList() || "none"}`);
  }
  if (!day.classList.contains("active")) {
    const before = byId("timesGrid")?.innerHTML ?? "";
    day.click();
    await waitFor(() => (byId("timesGrid")?.innerHTML ?? "") !== before, 8000);
    await timesSettled();
  }
  highlight(day);
}

/** The day's hours are still loading: the booking's spinner in the grid. */
const timesLoading = () => Boolean(byId("timesGrid")?.querySelector(".spinner-border"));

/** Wait for a day's (or half's) hours to come back: centres listed, or the
 *  booking's own "no times" line, with no spinner. */
async function timesSettled(): Promise<void> {
  await waitFor(() => !timesLoading() && (groups().length > 0 || Boolean(byId("timesGrid")?.querySelector(".no-times"))), 12_000);
  await quiet(byId("schedulerGrid") ?? document.body, 300, 3000);
}

async function choosePeriod(period: "AM" | "PM"): Promise<void> {
  const b = byId<HTMLButtonElement>(period === "AM" ? "btnPeriodAm" : "btnPeriodPm");
  if (!b || b.getAttribute("aria-pressed") === "true") return;
  const before = byId("timesGrid")?.innerHTML ?? "";
  b.click();
  await waitFor(() => (byId("timesGrid")?.innerHTML ?? "") !== before, 8000);
  await timesSettled();
}

async function expand(g: HTMLElement): Promise<void> {
  if (isOpen(g)) return;
  g.querySelector<HTMLElement>(".center-toggle")?.click();
  await waitFor(() => isOpen(g), 2000);
  await sleep(200);
}

/** The time button in `g`, opening "Ver más horas" as often as it takes. */
async function timeIn(g: HTMLElement, time: string): Promise<HTMLButtonElement | null> {
  for (let n = 0; n < 6; n++) {
    const hit = timeButtons(g).find((b) => clean(b.textContent) === time);
    if (hit) return hit;
    const more = g.querySelector<HTMLButtonElement>("button.btn-show-more-times");
    if (!more || !visible(more)) return null;
    more.click();
    await sleep(300);
  }
  return null;
}

const hhmm = (t: string) => {
  const m = /^(\d{1,2}):(\d{2})/.exec(t.trim());
  if (!m || Number(m[1]) > 23 || Number(m[2]) > 59) return null;
  return `${m[1].padStart(2, "0")}:${m[2]}`;
};

/** A centre's own name: the part after "|" ("CENTRO DE SALUD | QUINTA
 *  VERGARA" → "QUINTA VERGARA"), which is the same in any language. */
const afterBar = (s: string) => clean(s).replace(/^.*\|\s*/, "");
const centreName = (g: HTMLElement) => afterBar(titleOf(g));

/** The centre group the brain named, compared on the name after "|" on both
 *  sides, accent- and case-folded; then as given. */
function findCentre(all: HTMLElement[], want: string): HTMLElement | null {
  const name = norm(afterBar(want));
  return (
    all.find((g) => norm(centreName(g)) === name) ??
    best(all, centreName, afterBar(want)) ??
    best(all, titleOf, want) ??
    null
  );
}

/** Hold `time` at `centre` (or wherever it is offered) and continue to the
 *  patient form; the centre it was held at. */
async function chooseTime(time: string, centre: string | null): Promise<string> {
  const all = groups();
  if (!all.length) throw new Error("there are no times on screen for that day");
  let g: HTMLElement | null = null;
  if (centre) {
    g = findCentre(all, centre);
    if (!g) throw new Error(`no centre "${centre}" on ${describeDay()}, the day now on screen; centres that day: ${all.map(titleOf).join(" | ")}`);
  }
  let button: HTMLButtonElement | null = null;
  for (const candidate of g ? [g] : all) {
    if (timeButtons(candidate).some((b) => clean(b.textContent) === time) || (g && candidate === g)) {
      await expand(candidate);
      button = await timeIn(candidate, time);
      if (button) {
        g = candidate;
        break;
      }
    }
  }
  if (!button && !g) {
    // Behind "Ver más horas" somewhere: each centre in turn.
    for (const candidate of all) {
      await expand(candidate);
      button = await timeIn(candidate, time);
      if (button) {
        g = candidate;
        break;
      }
    }
  }
  if (!button || !g) {
    const where = g ? ` at ${titleOf(g)}` : "";
    const offered = (g ? timeButtons(g) : all.flatMap(timeButtons)).map((b) => clean(b.textContent));
    throw new Error(`no ${time}${where} on this day; times: ${[...new Set(offered)].slice(0, MAX_TIMES).join(", ") || "none"}`);
  }
  await scrollTo(button, "center");
  button.click();
  await waitFor(() => clean(byId("selectedSummary")?.textContent), 3000);
  highlight(button);
  await sleep(500);
  const next = byId<HTMLButtonElement>("btnContinuar");
  if (!next) throw new Error("there is no Continuar button");
  next.click();
  const alert = byId("serviceIndicationAlert");
  await waitFor(() => bookingShown() || (alert && visible(alert)), 12_000);
  if (alert && visible(alert)) {
    // The service's notice comes first (where samples are taken, fasting…);
    // the brain reads it from `agenda_state` before it is accepted here.
    reportNow();
    await sleep(DEBOUNCE_MS + 200);
    byId("btnAcceptServiceIndicationAlert")?.click();
    await waitFor(() => !visible(alert), 3000);
  }
  if (!(await waitFor(bookingShown, 8000))) {
    const status = clean(byId("availabilityDescription")?.textContent);
    throw new Error(`the time could not be held${status ? `: ${status}` : ""}`);
  }
  const card = document.querySelector<HTMLElement>("#bookingStep .appointment-summary-card") ?? byId("bookingStep");
  if (card) {
    await scrollTo(byId("bookingStep") ?? card, "top");
    highlight(card);
  }
  return titleOf(g);
}

interface Pick {
  day?: string | null;
  time?: string | null;
  centre?: string | null;
  period?: "AM" | "PM" | null;
}

/** Whether the patient form is open for exactly the day, time and centre
 *  asked: going back to the calendar for them would take the form down and
 *  put it back, and could clear what the visitor typed. The summary and the
 *  centre titles are kept from translation (`anchors.ts`). */
function alreadyHeld(day: string | null | undefined, t: string | null, centre: string | null | undefined): boolean {
  if (!(day || t || centre) || !bookingShown()) return false;
  const summary = norm(byId("selectedSummary")?.textContent);
  if (!summary) return false;
  const shown = activeDay();
  if (day && (!shown || dateOf(shown) !== day)) return false;
  if (t && !summary.includes(t)) return false;
  if (centre) {
    const name = norm(afterBar(centre));
    const open = groups().find(isOpen);
    if (!(open && norm(centreName(open)) === name) && !summary.includes(name)) return false;
  }
  return true;
}

/** Take the steps given; what is on screen after them, in English, for the
 *  brain (`command_done`). */
async function pick({ day, time, centre, period }: Pick): Promise<string> {
  const t = time ? hhmm(time) : null;
  if (time && !t) throw new Error(`"${time}" is not a time as HH:MM`);
  if (alreadyHeld(day, t, centre)) return `already selected, nothing changed: ${describe()}`;
  if ((day || t || centre) && bookingShown()) {
    byId("btnBackToAvailability")?.click();
    await waitFor(() => !bookingShown(), 4000);
    await sleep(300);
  }
  if (day) await chooseDay(day);
  const half = period ?? (t ? (Number(t.slice(0, 2)) < 12 ? "AM" : "PM") : null);
  if (half) await choosePeriod(half);
  if (t) {
    const at = await chooseTime(t, centre ?? null);
    const shown = activeDay();
    const on = (shown && dateOf(shown)) || day || "";
    return `selected ${weekday(on)}${on} ${t} at ${at}; the patient form is open (${describeForm()})`;
  }
  if (centre) {
    const all = groups();
    const g = findCentre(all, centre);
    if (!g) throw new Error(`no centre "${centre}" on ${describeDay()}, the day now on screen; centres that day: ${all.map(titleOf).join(" | ")}`);
    await expand(g);
    await scrollTo(g, "top");
    highlight(g);
    await sleep(200);
    const times = timeButtons(g).filter(visible).map((b) => clean(b.textContent));
    return `showing ${titleOf(g)} on ${describeDay()}: ${list(times) || "no hours"}`;
  }
  if (day || half) {
    const grid = byId("timesGrid");
    if (grid) {
      await scrollTo(grid, "top");
      highlight(grid);
    }
  }
  return describe();
}

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
/** "2026-10-27" → "Tue " (with the space), or "" for no date. */
function weekday(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return "";
  return `${WEEKDAYS[new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])).getDay()]} `;
}

const list = (xs: string[], max = 8) => (xs.length > max ? `${xs.slice(0, max).join(", ")}…` : xs.join(", "));

function describeDay(): string {
  const a = activeDay();
  const iso = a ? dateOf(a) : null;
  return iso ? `${weekday(iso)}${iso}` : "the selected day";
}

function describeForm(): string {
  const s = agendaState();
  const need = s.invalid.filter((f) => f !== "consent");
  return `document ${s.document === "passport" ? "passport" : "RUT"}; ${need.length ? `still empty or invalid: ${need.join(", ")}` : "every field is in"}${s.ready ? "; AGENDAR is ready for the visitor" : ""}`;
}

/** What the booking shows now, in English, for the brain. */
function describe(): string {
  const s = agendaState();
  if (s.step === "done") return "the booking's confirmation is on screen";
  if (s.step === "booking") return `the patient form is open for ${s.selected || "the chosen time"} (${describeForm()})`;
  if (s.step === "results") {
    const parts = [`month ${s.month || "unknown"}`, s.days.length ? `${s.days.length} open days: ${list(s.days, 10)}` : "no open day marked yet"];
    if (s.day) parts.push(`selected day ${weekday(s.day)}${s.day}`);
    if (s.centre) parts.push(`hours at ${s.centre}: ${list(s.times) || "none listed"}`);
    return `the calendar is showing ${s.prestacion_name || s.servicio_name || "the service"}: ${parts.join("; ")}`;
  }
  return "the search form is showing; no search has come back yet";
}

interface OpenAgenda extends Pick {
  servicio: number;
  prestacion?: number | null;
  region?: number | null;
}

/** `null` when the move continues on the service's own page, which reports
 *  it done from there. */
async function openAgenda(p: OpenAgenda): Promise<string | null> {
  if (p.servicio && servicio() !== Number(p.servicio)) {
    // Another service is another page: the rest of the move waits for it.
    const url = new URL("/", location.origin);
    url.searchParams.set("servicio", String(p.servicio));
    if (p.prestacion) url.searchParams.set("prestacion", String(p.prestacion));
    leave({ command: "open_agenda", payload: p });
    location.assign(url.pathname + url.search);
    return null;
  }
  await ready();
  let again = false;
  const region = byId<HTMLSelectElement>("regionSelect");
  if (p.region && region && region.value !== String(p.region)) {
    const option = [...region.options].find((o) => o.value === String(p.region));
    if (!option) {
      const known = [...region.options].filter((o) => o.value).map((o) => `${o.value} ${clean(o.text)}`);
      throw new Error(`region ${p.region} is not offered for this service; regions: ${known.join(" | ")}`);
    }
    setValue(region, option.value);
    highlight(region);
    again = true;
    await sleep(500);
  }
  const prest = byId<HTMLSelectElement>("prestacionSelect");
  if (p.prestacion && prest && prest.value !== String(p.prestacion)) {
    const option = [...prest.options].find((o) => o.value === String(p.prestacion));
    if (!option) {
      const known = [...prest.options].filter((o) => o.value).map((o) => `${o.value} ${clean(o.text)}`);
      throw new Error(`prestación ${p.prestacion} is not offered here; prestaciones: ${known.join(" | ")}`);
    }
    if (bookingShown()) {
      byId("btnBackToAvailability")?.click();
      await waitFor(() => !bookingShown(), 4000);
    }
    setValue(prest, option.value);
    highlight(byId("prestacionPicker") ?? prest);
    again = true;
    await sleep(400);
  }
  if (again || (!resultsShown() && !bookingShown())) await search();
  let done: string;
  if (p.day || p.time || p.centre || p.period) done = await pick(p);
  else {
    if (resultsShown() && !bookingShown()) {
      const column = byId("availabilityColumn");
      if (column) {
        await scrollTo(column, "top");
        highlight(column);
      }
    }
    done = describe();
  }
  reportNow();
  return done;
}

async function agendaPick(p: Pick): Promise<string> {
  await ready();
  if (!resultsShown() && !bookingShown()) await search();
  const done = await pick(p);
  reportNow();
  return done;
}

interface Patient {
  name?: string | null;
  last_name?: string | null;
  maternal_last_name?: string | null;
  birth_date?: string | null;
  sex?: "F" | "M" | "O" | null;
  phone?: string | null;
  email?: string | null;
  focus_rut?: boolean | null;
  document?: "rut" | "passport" | null;
}

const FIELD_KEYS = ["name", "last_name", "maternal_last_name", "birth_date", "sex", "phone", "email"] as const;

/** Switch the form's document to a RUT or a passport, as the visitor would,
 *  by its own button (which empties the document box, so only when it
 *  differs). Whether it switched. */
async function chooseDocument(want: "rut" | "passport"): Promise<boolean> {
  if (documentType() === want) return false;
  const button = byId<HTMLButtonElement>(want === "passport" ? "btnDocumentPassport" : "btnDocumentRut");
  if (!button) throw new Error(`there is no ${want === "passport" ? "Pasaporte" : "RUT"} switch on this form`);
  button.click();
  await waitFor(() => documentType() === want, 2000);
  await sleep(200);
  return documentType() === want;
}

/**
 * Fill the patient's fields the visitor said, with the page's own formatting
 * and checks. A field the page locked (a known patient's masked data) is left
 * alone. The document (RUT or passport, switched by `document`) is focused and
 * ringed for the visitor to type, never typed; the consent box and "AGENDAR"
 * are ringed for the visitor to press, never pressed. What was done, in
 * English, for the brain.
 */
async function fillPatient(p: Patient): Promise<string> {
  if (!bookingShown()) throw new Error("the booking form is not open yet: pick a day and a time first (agenda_pick)");
  const alert = byId("serviceIndicationAlert");
  if (alert && visible(alert)) {
    byId("btnAcceptServiceIndicationAlert")?.click();
    await waitFor(() => !visible(alert), 3000);
  }
  const rut = byId<HTMLInputElement>("patientRut");
  const done: string[] = [];
  if (p.document === "rut" || p.document === "passport") {
    if (await chooseDocument(p.document)) done.push(`switched the document to ${p.document === "passport" ? "Pasaporte" : "RUT"}`);
  }
  const doc = documentType() === "passport" ? "passport number" : "RUT";
  // The page looks the document up again (and empties a new patient's
  // fields) when its box loses focus. The visitor has just typed it and it
  // still has the focus, so that blur is let happen now and its lookup
  // awaited, before anything is filled, or the visitor's next click would
  // wipe the fill.
  if (rut && document.activeElement === rut && !done.length) {
    rut.blur();
    await sleep(150);
  }
  await waitFor(() => !/buscando/i.test(byId("patientLookupStatus")?.textContent ?? ""), 6000);
  await sleep(200);
  // The page keeps every other field shut until the visitor's RUT or passport
  // is in and looked up (a registered patient's come back masked): he points
  // at it.
  const waiting = byId<HTMLInputElement>("patientName");
  const asked = FIELD_KEYS.some((k) => p[k] !== null && p[k] !== undefined && p[k] !== "");
  if (rut && waiting?.disabled && !waiting.value.trim()) {
    await scrollTo(rut, "center");
    rut.focus({ preventScroll: true });
    highlight(rut);
    reportNow();
    if (asked) {
      throw new Error(
        `nothing was filled: the page opens the patient's fields only after the visitor types their ${doc} in the document box (a RUT, or a passport number with the Pasaporte switch); that box is focused and ringed for them: ask them to type it, then fill the rest`,
      );
    }
    return [...done, `the ${doc} box is focused and ringed for the visitor to type; the other fields open once it is in`].join("; ");
  }
  const touched: HTMLElement[] = [];
  const filled: string[] = [];
  const locked: string[] = [];
  const problems: string[] = [];
  const put = (name: string, id: string, value: string | null | undefined, check?: (v: string) => string | null, why?: string) => {
    if (value === null || value === undefined || !String(value).trim()) return;
    const el = byId<HTMLInputElement | HTMLSelectElement>(id);
    if (!el) return;
    if (el.disabled || (el as HTMLInputElement).readOnly) return void locked.push(name);
    let v = String(value).trim();
    if (check) {
      const fixed = check(v);
      if (fixed === null) return void problems.push(`${name} "${v}" refused${why ? `: ${why}` : ""}`);
      v = fixed;
    }
    setValue(el, v);
    touched.push(el);
    filled.push(name);
  };
  put("name", "patientName", p.name);
  put("last_name", "patientLastName", p.last_name);
  put("maternal_last_name", "patientMaternalLastName", p.maternal_last_name);
  put("birth_date", "patientBirthDate", p.birth_date, (v) => (/^\d{4}-\d{2}-\d{2}$/.test(v) ? v : null), "not a date as YYYY-MM-DD");
  put("sex", "patientSex", p.sex, (v) => {
    const sel = byId<HTMLSelectElement>("patientSex");
    const want = v.toUpperCase();
    const byValue = sel && [...sel.options].find((o) => o.value.toUpperCase() === want);
    return byValue?.value ?? (sel ? (pickOption(sel, v)?.value ?? null) : null);
  });
  put(
    "phone",
    "patientPhone",
    p.phone,
    (v) => {
      const digits = chileanMobile(v);
      return /^9\d{8}$/.test(digits) ? digits : null;
    },
    "the form takes a Chilean mobile (9 digits starting with 9); nothing was typed there: ask for one, never change the digits",
  );
  put("email", "patientEmail", p.email, (v) => (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) ? v : null), "not an email address");
  await sleep(300);
  const state = agendaState();
  const consent = byId<HTMLInputElement>("consentPrivacy");
  const agendar = byId<HTMLButtonElement>("btnAgendar");
  if ((p.focus_rut || done.length) && rut) {
    await scrollTo(rut, "center");
    rut.focus({ preventScroll: true });
    highlight(rut);
  } else if (state.ready && agendar) {
    await scrollTo(agendar, "center");
    highlight(agendar);
  } else if (consent && state.invalid.length === 1 && state.invalid[0] === "consent") {
    const row = consent.closest<HTMLElement>(".form-check, label, div") ?? consent;
    await scrollTo(row, "center");
    highlight(row);
  } else if (touched.length) {
    await scrollTo(touched[0], "center");
    highlight(touched);
  }
  reportNow();
  if (locked.length) problems.push(`left as the page has them (a registered patient's data is locked): ${locked.join(", ")}`);
  // Nothing landed: a failure. Something did: done, with what was refused.
  if (problems.length && !filled.length && !done.length) throw new Error(problems.join("; "));
  if (filled.length) done.push(`filled ${filled.join(", ")}`);
  if (p.focus_rut && rut) done.push(`the ${doc} box is focused for the visitor to type`);
  done.push(...problems);
  done.push(describeForm());
  return done.join("; ");
}

/** The move on the booking under way: the next waits for it, whatever it is.
 *  Two at once click the same calendar against each other — on dev call
 *  2fd742d5 a pick for the 28th ran inside an open still waiting for 07:00 at
 *  Buin, and the open then failed on the pick's day. */
let running: Promise<unknown> = Promise.resolve();

function oneAtATime<P, R>(move: (payload: P) => Promise<R>): (payload: P) => Promise<R> {
  return (payload: P) => {
    const turn = running.then(() => move(payload));
    // A failed move is answered on its own; the next one still runs.
    running = turn.catch(() => undefined);
    return turn;
  };
}

export function agendaCommands(): Record<string, (payload: never) => Promise<string | null | void>> {
  return {
    open_agenda: oneAtATime(openAgenda) as (payload: never) => Promise<string | null>,
    agenda_pick: oneAtATime(agendaPick) as (payload: never) => Promise<string>,
    fill_agenda_patient: oneAtATime(fillPatient) as (payload: never) => Promise<string>,
  };
}
