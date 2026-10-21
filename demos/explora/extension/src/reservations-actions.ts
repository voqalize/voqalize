/**
 * The site adapter for reservations.explora.com, Explora's booking engine
 * (an Art2Fly IBE): Javier checks a lodge's availability with the visitor and
 * fills in, and sends, an expedition's enquiry.
 *
 * Every step of the site is a full page load, so a move that spans steps (the
 * lodge's calendar, then its rooms) is carried to the next page with
 * `loadThen`: the call runs the same command again there, and this file picks
 * it up from wherever the page now stands. Every command is idempotent for
 * that reason.
 *
 *   /ibe/paso1        the lodge (`select#destination`, whose inline onchange
 *                     reloads), the inline jQuery UI datepicker
 *                     (`#check_in_calendar`, hidden `#check_in_date`, open days
 *                     in `window.lista_disponibles`) and the nights
 *                     (`select#nights`, filled by `getStay(date)` over AJAX);
 *   /ibe/paso2        the rooms and rates. Javier never goes past it: no
 *                     "Add this room", no check-out, nothing on paso3;
 *   /ibe/expeditions  the enquiry form `#form-expeditions` (jQuery Validate and
 *                     a reCAPTCHA v2 checkbox the visitor ticks themselves).
 *
 * This runs in the page's own world (MAIN), so the site's jQuery, `getStay`
 * and `grecaptcha` are in reach.
 */

import type {
  CheckAvailability,
  EnquiryFields,
  EnquiryState,
  FillEnquiry,
  NightsOption,
  RoomOption,
  StayState,
} from "./actions.gen";
import {
  clean,
  clearHighlight,
  highlight,
  norm,
  pick,
  scrollTo,
  setField,
  sleep,
  styleThePage,
  visible,
  waitFor,
  type Adapter,
  type PageContext,
} from "./dom";
import { loadThen } from "./hub";

/**
 * When true, `send_enquiry` reports `enquiry_sent` (so the conversation goes
 * on as if it had gone) but never presses Send Message: for demos and tests
 * where no enquiry may reach Explora's expedition team. A visitor's own press
 * of the button is never blocked.
 */
const BLOCK_SEND = false;

const BASE = "https://reservations.explora.com";
/** The site's language for the pages Javier opens (`?language=EN|ES`, sticky
 *  for the browser session): the call's, as each move carries it. */
let LANGUAGE: "EN" | "ES" = "EN";
const speak = (p: { language?: string | null }) => {
  LANGUAGE = p.language === "ES" ? "ES" : "EN";
};
/** How many open arrival days a `stay_state` carries. */
const OPEN_DAYS_MAX = 60;
const NIGHTS_MS = 12000;

// ─── The page's own scripts ───────────────────────────────────────────────

interface JQ {
  (target: unknown): JQ;
  fn?: { valid?: unknown; datepicker?: unknown };
  datepicker(method: string, value?: unknown): unknown;
  empty(): JQ;
  append(html: string): JQ;
  valid?(): boolean;
  validate?(): Validator;
}

interface Validator {
  form(): boolean;
  element(el: Element): boolean | undefined;
  errorList: { element: HTMLElement; message: string }[];
}

interface Page {
  jQuery?: JQ;
  lista_disponibles?: string[];
  getStay?: (date: string) => void;
  grecaptcha?: { getResponse(id?: number): string };
}

const page = () => window as unknown as Page;

function captchaTicked(): boolean {
  try {
    return (page().grecaptcha?.getResponse() ?? "") !== "";
  } catch {
    // Not rendered yet.
    return false;
  }
}

// ─── Where the page is ────────────────────────────────────────────────────

type Step = "paso1" | "paso2" | "expeditions" | "other";

function step(): Step {
  const path = location.pathname.replace(/\/+$/, "").toLowerCase();
  if (path === "" || path === "/ibe" || path.endsWith("/paso1")) return "paso1";
  if (path.endsWith("/paso2")) return "paso2";
  if (path.endsWith("/expeditions")) return "expeditions";
  return "other";
}

const STEP_LABEL: Record<Step, string> = {
  paso1: "Travel details",
  paso2: "Rooms",
  expeditions: "Expedition enquiry",
  other: "Booking",
};

const param = (name: string) => new URLSearchParams(location.search).get(name) ?? "";

const destination = () => document.querySelector<HTMLSelectElement>("select#destination");
/** The nights select of paso1 (paso2 has a `div#nights` of its own). */
const nightsSelect = () => document.querySelector<HTMLSelectElement>("select#nights");
const calendar = () => document.querySelector<HTMLElement>("#check_in_calendar");
const enquiryForm = () => document.querySelector<HTMLFormElement>("#form-expeditions");
/** The reCAPTCHA checkbox itself (its iframe's box), not its wide container. */
const captchaBox = () =>
  document.querySelector("#c_recaptcha iframe[title=reCAPTCHA]")?.parentElement ??
  document.querySelector("#c_recaptcha");

function selectedHotel(): { code: string; label: string } | null {
  const s = destination();
  if (!s || !s.value) return null;
  return { code: s.value, label: clean(s.selectedOptions[0]?.textContent) };
}

function localDay(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Every open arrival day of the lodge, from tomorrow (the calendar's
 *  `minDate: 1`), soonest first. */
function openDays(): string[] {
  const today = localDay(new Date());
  const all = (page().lista_disponibles ?? []).filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d) && d > today);
  return [...new Set(all)].sort();
}

const MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
  "october", "november", "december"];
const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
  "octubre", "noviembre", "diciembre"];

/** The first month the calendar shows, as `YYYY-MM`, read off its title
 *  ("March 2027", or "Marzo 2027" in Spanish). */
function shownMonth(): string | null {
  const title = clean(document.querySelector("#check_in_calendar .ui-datepicker-title")?.textContent).toLowerCase();
  const year = title.match(/\b(20\d\d)\b/)?.[1];
  const i = MONTHS.findIndex((m) => title.includes(m));
  const j = i >= 0 ? i : MESES.findIndex((m) => title.includes(m));
  return year && j >= 0 ? `${year}-${String(j + 1).padStart(2, "0")}` : null;
}

/** Turn the calendar to `month` (`YYYY-MM`) with its own arrows, so the
 *  visitor sees the month they asked about. */
async function showMonth(month: string): Promise<void> {
  for (let i = 0; i < 40; i++) {
    const at = shownMonth();
    if (!at || at === month) return;
    const arrow = document.querySelector<HTMLElement>(
      at < month ? "#check_in_calendar .ui-datepicker-next" : "#check_in_calendar .ui-datepicker-prev",
    );
    if (!arrow || arrow.classList.contains("ui-state-disabled")) return;
    arrow.click();
    await sleep(60);
  }
}

function nearest(date: string, days: string[], n = 6): string[] {
  const at = Date.parse(date);
  return [...days]
    .sort((a, b) => Math.abs(Date.parse(a) - at) - Math.abs(Date.parse(b) - at))
    .slice(0, n)
    .sort();
}

type NightsState = "empty" | "loading" | "loaded";

function nightsState(): NightsState {
  const opts = [...(nightsSelect()?.options ?? [])];
  if (!opts.length) return "empty";
  if (opts.some((o) => /please wait|espere/i.test(o.text))) return "loading";
  // Before a day is picked the select holds one placeholder option, value "".
  return opts.every((o) => o.value !== "") ? "loaded" : "empty";
}

/** "5 nights (from US$ 1,140 / night )" → "5 nights (from US$ 1,140 a night
 *  per person)": the page's own note says the rate is one person's, in a
 *  double room. */
function nightsLabel(text: string): string {
  const label = clean(text);
  // Some lodges (Machu Picchu) list bare numbers, with no rate.
  if (/^\d+$/.test(label)) return `${label} nights`;
  return label
    .replace(/\s*\/\s*(night|noche)\s*\)/i, " a night per person)")
    .replace(/\s+\)/g, ")");
}

function nightsOffered(): NightsOption[] {
  return [...(nightsSelect()?.options ?? [])]
    .filter((o) => Number(o.value) > 0)
    .map((o) => ({ nights: Number(o.value), label: nightsLabel(o.text) }));
}

/** The arrival day chosen: the hidden field counts once its nights have
 *  loaded (it is pre-filled with tomorrow before anyone picks). */
function chosenDate(): string {
  if (nightsState() !== "loaded") return "";
  return document.querySelector<HTMLInputElement>("#check_in_date")?.value ?? "";
}

// ─── What the page shows ──────────────────────────────────────────────────

function headings(): string[] {
  const out: string[] = [];
  for (const el of document.querySelectorAll("h1, h2, h3, h4, .control-label")) {
    // The rooms themselves are in `stay_state`.
    if (el.closest("[data-voqalize], .mfp-hide, .room-item")) continue;
    if (!visible(el)) continue;
    const text = clean(el.textContent);
    if (text && text.length < 120 && !out.includes(text)) out.push(text);
    if (out.length >= 14) break;
  }
  return out;
}

function expeditionName(): string {
  return (
    clean(enquiryForm()?.querySelector<HTMLInputElement>("input[name=expedition_name]")?.value) ||
    clean(document.querySelector("#titulo h2")?.textContent)
  );
}

function context(): PageContext {
  const s = step();
  let detail = "";
  if (s === "paso1") detail = selectedHotel()?.label ?? "";
  else if (s === "paso2") detail = roomsHotel();
  else if (s === "expeditions") detail = expeditionName();
  return {
    site: "reservations",
    url: location.href,
    path: location.pathname,
    title: detail ? `${STEP_LABEL[s]}: ${detail}` : STEP_LABEL[s],
    headings: headings(),
    faqs: [],
    tabs: [],
    links: [],
  };
}

// ─── Stay state: paso1 and paso2 ──────────────────────────────────────────

function datesState(): StayState | null {
  const hotel = selectedHotel();
  if (!hotel) return null;
  const date = chosenDate();
  const state: StayState = {
    step: "dates",
    hotel_code: hotel.code,
    hotel: hotel.label,
    month: clean(document.querySelector("#check_in_calendar .ui-datepicker-title")?.textContent),
    // From the month on screen: the days the visitor is looking at.
    open_days: openDays()
      .filter((d) => d >= `${shownMonth() ?? "0000-00"}-01`)
      .slice(0, OPEN_DAYS_MAX),
  };
  if (date) {
    state.date = date;
    state.nights = nightsOffered();
    const chosen = Number(nightsSelect()?.value) || 0;
    if (chosen > 0) state.chosen_nights = chosen;
  }
  return state;
}

function roomsHotel(): string {
  const box = document.querySelector("#ticket #hotel");
  const text = clean(box?.textContent).replace(/^hotel\s*/i, "");
  return text || clean(document.querySelector("#titulo h2")?.textContent);
}

const roomItems = () => [...document.querySelectorAll<HTMLElement>("#room-list .room-item")];

const money = (s: string | null | undefined) => clean(s).replace(/^([A-Z]{0,3}\$)\s*/, "$1 ");
const amount = (s: string | null | undefined) => Number(clean(s).replace(/[^\d.]/g, "")) || 0;

/** One room's line: its stay total for the travellers selected, the total a
 *  night, and how many are left. */
function roomText(item: HTMLElement, nights: number): string {
  const price = item.querySelector(".room-rate .current-price");
  const total = amount(price?.querySelector(".price")?.textContent ?? price?.textContent);
  const currency = clean(price?.querySelector(".currency")?.textContent) || "US$";
  const travellers = clean(item.querySelector<HTMLSelectElement>("select[name=nadults]")?.selectedOptions[0]?.text);
  const parts: string[] = [];
  if (total) {
    let line = `${currency} ${total.toLocaleString("en-US")}`;
    if (nights > 0) line += ` for ${nights} nights`;
    if (travellers) line += `, ${travellers.toLowerCase()}`;
    if (nights > 0) line += ` (${currency} ${Math.round(total / nights).toLocaleString("en-US")} a night)`;
    parts.push(line);
  } else if (price) {
    parts.push(money(price.textContent));
  }
  const old = item.querySelector(".room-rate .old-price");
  if (old && visible(old) && amount(old.textContent) > total) parts.push(`special price, was ${money(old.textContent)}`);
  const left = clean(item.querySelector(".rooms-left")?.textContent);
  if (left) parts.push(left.toLowerCase());
  return parts.join("; ");
}

function roomsState(): StayState {
  const nights = Number(param("nights")) || amount(document.querySelector("#ticket #nights")?.textContent);
  const rooms: RoomOption[] = roomItems()
    .map((item) => ({
      name: clean(item.querySelector("[id^=room_][id$=_name]")?.textContent ?? item.querySelector(".room-detail h3")?.textContent),
      text: roomText(item, nights),
    }))
    .filter((r) => r.name);
  return {
    step: "rooms",
    hotel_code: param("hotel_code").toUpperCase(),
    hotel: roomsHotel(),
    date: param("check_in_date"),
    chosen_nights: nights,
    rooms,
  };
}

function stayState(): StayState | null {
  const s = step();
  if (s === "paso1") return datesState();
  if (s === "paso2") return roomsState();
  return null;
}

// ─── Enquiry state: /ibe/expeditions ──────────────────────────────────────

type FieldKey = keyof EnquiryFields;
const FIELDS: [FieldKey, string][] = [
  ["title", "title"],
  ["first_name", "firstname"],
  ["last_name", "lastname"],
  ["email", "email"],
  ["phone", "phone"],
  ["country", "country"],
  ["message", "message"],
];

type Field = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;
const field = (form: HTMLFormElement, name: string) => form.querySelector<Field>(`[name="${name}"]`);

/** The title select defaults to "Mr.": it counts as filled only once someone
 *  chose it, Javier or the visitor. */
let titleChosen = false;

function enquiryState(): EnquiryState | null {
  const form = enquiryForm();
  if (!form) return null;
  const filled: EnquiryFields = {};
  const missing: string[] = [];
  for (const [key, name] of FIELDS) {
    const el = field(form, name);
    let value = clean(el?.value);
    if (key === "title" && !titleChosen) value = "";
    if (key === "country" && el instanceof HTMLSelectElement && value) value = clean(el.selectedOptions[0]?.text);
    filled[key] = value;
    if (!value) missing.push(key);
  }
  return {
    expedition: expeditionName(),
    expedition_code:
      clean(form.querySelector<HTMLInputElement>("input[name=expedition_id]")?.value) ||
      param("expedition_request").toUpperCase(),
    filled,
    missing,
    captcha: captchaTicked(),
  };
}

// ─── Reporting ────────────────────────────────────────────────────────────

let emitter: ((event: string, payload: unknown) => void) | null = null;
/** What was reported before the call took the page: the latest of each. */
const queued = new Map<string, unknown>();
/** While Javier is moving the page, the watcher holds its reports. */
let busy = 0;
let lastStay = "";
let lastEnquiry = "";

function emit(event: string, payload: unknown): void {
  if (event === "stay_state") lastStay = JSON.stringify(payload);
  if (event === "enquiry_state") lastEnquiry = JSON.stringify(payload);
  if (emitter) emitter(event, payload);
  else queued.set(event, payload);
}

function reportState(): void {
  const stay = stayState();
  if (stay) emit("stay_state", stay);
  const enquiry = enquiryState();
  if (enquiry) emit("enquiry_state", enquiry);
}

let enquiryChangedAt = 0;
let enquiryPending = "";
let lastCaptcha: boolean | null = null;

/** Every half second: the visitor's own date, nights, travellers, fields and
 *  reCAPTCHA tick. Field edits settle for ~600 ms first; a tick goes at once. */
function watch(): void {
  setInterval(() => {
    if (busy) return;
    const s = step();
    if (s === "paso1" || s === "paso2") {
      if (s === "paso1" && nightsState() === "loading") return;
      const stay = stayState();
      if (!stay) return;
      const sig = JSON.stringify(stay);
      if (sig !== lastStay) emit("stay_state", stay);
    } else if (s === "expeditions") {
      const state = enquiryState();
      if (!state) return;
      const sig = JSON.stringify(state);
      const captchaMoved = lastCaptcha !== null && state.captcha !== lastCaptcha;
      lastCaptcha = state.captcha ?? false;
      if (sig === lastEnquiry) return;
      if (sig !== enquiryPending) {
        enquiryPending = sig;
        enquiryChangedAt = Date.now();
      }
      if (captchaMoved || Date.now() - enquiryChangedAt >= 600) emit("enquiry_state", state);
    }
  }, 500);
}

/** Set by Javier's own press, so the submit it causes is not reported twice. */
let javierSending = false;

function watchEnquiry(): void {
  document.addEventListener(
    "change",
    (e) => {
      const t = e.target as Element | null;
      if (e.isTrusted && t instanceof HTMLSelectElement && t.name === "title" && t.closest("#form-expeditions")) {
        titleChosen = true;
      }
    },
    true,
  );
  // jQuery Validate stops an invalid form's submit before it bubbles up to the
  // window, so reaching here means the form is complete and is posting.
  window.addEventListener("submit", (e) => {
    const form = e.target as HTMLFormElement | null;
    if (!form || form.id !== "form-expeditions" || e.defaultPrevented || javierSending) return;
    if (!captchaTicked()) return;
    emit("enquiry_sent", { expedition: expeditionName(), by: "visitor" });
  });
}

function start(next: (event: string, payload: unknown) => void): () => void {
  emitter = next;
  next("page_changed", context());
  // The page's state as it stands now replaces any queued one.
  queued.delete("stay_state");
  queued.delete("enquiry_state");
  for (const [event, payload] of queued) next(event, payload);
  queued.clear();
  reportState();
  return () => {
    if (emitter === next) emitter = null;
  };
}

// ─── Moving between steps ─────────────────────────────────────────────────

const GO_KEY = "voqalize-explora-resv-go";

/** Load `url` with `then` for the page it lands on. Refuses to load the same
 *  URL twice in a few seconds: the site sent us back somewhere else, and
 *  loading again would loop. */
async function go(url: string, then: { command: string; payload: unknown }, what: string): Promise<void> {
  try {
    const last = JSON.parse(sessionStorage.getItem(GO_KEY) ?? "null") as { url: string; at: number } | null;
    if (last && last.url === url && Date.now() - last.at < 15000) {
      sessionStorage.removeItem(GO_KEY);
      throw new Error(`the booking site did not open ${what}`);
    }
    sessionStorage.setItem(GO_KEY, JSON.stringify({ url, at: Date.now() }));
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("the booking site")) throw error;
    // Storage blocked: no loop guard, carry on.
  }
  await loadThen(url, then);
}

function paso1Url(code: string, date: string | null | undefined): string {
  const q = new URLSearchParams({ hotel_code: code });
  if (date) q.set("check_in_date", date);
  q.set("language", LANGUAGE);
  return `${BASE}/ibe/paso1?${q}`;
}

/** What Continue on paso1 submits (GET), with the language. */
function paso2Url(code: string, date: string, nights: number): string {
  const q = new URLSearchParams({ session_id: "", hotel_code: code, check_in_date: date, nights: String(nights) });
  q.set("language", LANGUAGE);
  return `${BASE}/ibe/paso2?${q}`;
}

// ─── check_availability ───────────────────────────────────────────────────

/** Pick `date` on the inline calendar the way a click does, so the site's
 *  onSelect empties #nights and calls getStay(date); wait for the nights. */
async function selectDate(date: string): Promise<void> {
  const $ = page().jQuery;
  const cal = calendar();
  if (!$ || !cal) throw new Error("the booking calendar is not on the page");
  // setDate moves the view to the day's month (and fills the hidden field)
  // but does not fire onSelect; the day's own cell, clicked, does.
  $("#check_in_calendar").datepicker("setDate", date);
  const [y, m, d] = date.split("-").map(Number);
  const cell = await waitFor(
    () =>
      cal.querySelector<HTMLElement>(
        `td[data-handler=selectDay][data-year="${y}"][data-month="${m - 1}"] a[data-date="${d}"]`,
      ),
    1500,
  );
  if (cell) cell.click();
  else {
    $("#nights").empty().append('<option value="">Please wait...</option>');
    page().getStay?.(date);
  }
  const loaded = await waitFor(() => nightsState() === "loaded", NIGHTS_MS);
  if (!loaded) throw new Error(`the nights for ${date} did not load on the booking site`);
}

function nightsBox(): Element[] {
  const s = nightsSelect();
  if (!s) return [];
  const label = document.querySelector("#noches");
  return label && visible(label) ? [label, s] : [s];
}

async function checkAvailability(p: CheckAvailability): Promise<void> {
  speak(p);
  const code = clean(p.hotel_code).toUpperCase();
  if (!code) throw new Error("no lodge was named");
  const date = p.date ? clean(p.date) : "";
  if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new Error(`'${p.date}' is not a date (YYYY-MM-DD)`);
  const then = { command: "check_availability", payload: p };
  const s = step();

  // Already on this stay's rooms: just show them.
  if (
    s === "paso2" &&
    p.rooms &&
    param("hotel_code").toUpperCase() === code &&
    (!date || param("check_in_date") === date) &&
    (!p.nights || Number(param("nights")) === p.nights)
  ) {
    const list = document.querySelector("#room-list") ?? document.querySelector("#search");
    if (list) {
      await scrollTo(list, "top");
      const items = roomItems();
      highlight(items.length ? items : list);
    }
    emit("stay_state", roomsState());
    return;
  }

  if (s !== "paso1" || selectedHotel()?.code !== code) {
    await go(paso1Url(code, date), then, `the lodge ${code}`);
    return;
  }

  const hotel = selectedHotel()!;
  const cal = calendar();
  const month = p.month ? clean(p.month).slice(0, 7) : "";
  if (month && !date && /^\d{4}-\d{2}$/.test(month)) await showMonth(month);
  if (date) {
    const open = openDays();
    if (!open.includes(date)) {
      const near = nearest(date, open);
      throw new Error(
        `${date} is not an open arrival day at ${hotel.label}. ` +
          (near.length ? `The nearest open days: ${near.join(", ")}.` : "It has no open days at all."),
      );
    }
    if (chosenDate() !== date) {
      if (cal) await scrollTo(cal);
      await selectDate(date);
    }
  }

  if (p.nights && chosenDate()) {
    const offered = nightsOffered();
    if (!offered.some((o) => o.nights === p.nights)) {
      throw new Error(
        `${p.nights} nights are not offered from ${chosenDate()} at ${hotel.label}. ` +
          (offered.length ? `Offered: ${offered.map((o) => o.nights).join(", ")} nights.` : "No stay is available that day."),
      );
    }
    const s = nightsSelect()!;
    if (Number(s.value) !== p.nights) setField(s, String(p.nights));
  }

  const chosen = chosenDate();
  if (chosen) {
    const box = nightsBox();
    if (box.length) {
      await scrollTo(box[box.length - 1]);
      highlight(box);
    }
  } else if (cal) {
    await scrollTo(cal);
    highlight(cal);
  }
  const state = datesState();
  if (state) emit("stay_state", state);

  if (p.rooms) {
    const nights = Number(nightsSelect()?.value) || 0;
    if (!chosen) throw new Error("choose an arrival day first: the rooms need a date and nights");
    if (nights <= 0) throw new Error(`no stay is available from ${chosen} at ${hotel.label}`);
    await sleep(900); // Let the visitor see the nights before the page goes.
    await go(paso2Url(code, chosen, nights), { command: "check_availability", payload: { ...p, date: chosen, nights } }, "the rooms");
  }
}

// ─── fill_enquiry ─────────────────────────────────────────────────────────

function titleValue(want: string): string | null {
  const w = norm(want).replace(/\.$/, "");
  if (["mr", "sr", "senor", "mister", "sir", "male", "man"].includes(w)) return "Mr.";
  if (["ms", "mrs", "miss", "sra", "srta", "senora", "senorita", "madam", "female", "woman"].includes(w)) return "Ms.";
  return null;
}

/** The nationality option for an ISO code ("US"), or for its label: "AL" is
 *  both Albania and DR Congo (the value gives the first, Albania), and "FR"
 *  and "FX" are both France, so a label picks the exact option. */
function countryOption(select: HTMLSelectElement, want: string): HTMLOptionElement | null {
  const opts = [...select.options].filter((o) => o.value);
  const code = want.trim().toUpperCase();
  if (/^[A-Z]{2}$/.test(code)) {
    const hit = opts.find((o) => o.value.toUpperCase() === code);
    if (hit) return hit;
  }
  return pick(want, opts, (o) => o.text);
}

async function fillEnquiry(p: FillEnquiry): Promise<void> {
  speak(p);
  const code = clean(p.expedition_code).toUpperCase();
  if (!code) throw new Error("no expedition was named");
  const form = enquiryForm();
  if (step() !== "expeditions" || param("expedition_request").toUpperCase() !== code || !form) {
    const url = `${BASE}/ibe/expeditions?expedition_request=${encodeURIComponent(code)}&language=${LANGUAGE}`;
    await go(url, { command: "fill_enquiry", payload: p }, `the enquiry form for ${code}`);
    return;
  }

  const problems: string[] = [];
  const filled: Field[] = [];
  const values: Partial<Record<FieldKey, string | null>> = {
    title: p.title,
    first_name: p.first_name,
    last_name: p.last_name,
    email: p.email,
    phone: p.phone,
    country: p.country,
    message: p.message,
  };
  for (const [key, name] of FIELDS) {
    const raw = values[key];
    if (raw == null || clean(String(raw)) === "") continue;
    const el = field(form, name);
    if (!el) continue;
    const want = key === "message" ? String(raw).trim() : clean(String(raw));
    let value = want;
    if (key === "title") {
      const t = titleValue(want);
      if (!t) {
        problems.push(`title '${want}' is not on the form (Mr. or Ms.)`);
        continue;
      }
      value = t;
      titleChosen = true;
    } else if (key === "country" && el instanceof HTMLSelectElement) {
      const opt = countryOption(el, want);
      if (!opt) {
        problems.push(`nationality '${want}' is not on the form's list`);
        continue;
      }
      if (el.selectedOptions[0] !== opt) {
        // By index, so a shared code ("AL") lands on the option asked for.
        el.selectedIndex = opt.index;
        for (const type of ["input", "change", "blur"]) el.dispatchEvent(new Event(type, { bubbles: true }));
      }
      filled.push(el);
      continue;
    }
    if (el.value !== value) setField(el, value);
    filled.push(el);
  }

  // Show what was filled the way the form itself marks it (green or an error).
  const validator = page().jQuery && page().jQuery!(form).validate?.();
  for (const el of filled) {
    try {
      validator?.element(el);
    } catch {
      /* Validate not set up on this page: the fields are still filled. */
    }
  }

  const state = enquiryState()!;
  const firstEmpty = FIELDS.filter(([k]) => k !== "title")
    .filter(([k]) => state.missing?.includes(k))
    .map(([, name]) => field(form, name))
    .find((el): el is Field => Boolean(el));
  const captcha = captchaBox();
  const row = (el: Element) => el.closest(".control-value") ?? el;
  if (firstEmpty) {
    await scrollTo(row(firstEmpty));
    highlight(...(filled.length ? filled.map(row) : [row(firstEmpty)]));
  } else if (captcha) {
    await scrollTo(captcha);
    highlight(captcha);
  }
  emit("enquiry_state", state);
  if (problems.length) throw new Error(`filled the rest, but ${problems.join("; ")}`);
}

// ─── send_enquiry ─────────────────────────────────────────────────────────

const KEY_OF: Record<string, string> = Object.fromEntries(FIELDS.map(([k, n]) => [n, k]));

async function sendEnquiry(): Promise<void> {
  const form = enquiryForm();
  if (step() !== "expeditions" || !form) throw new Error("no expedition enquiry form is open");
  const state = enquiryState()!;
  const empty = (state.missing ?? []).filter((k) => k !== "title");
  const invalid: string[] = [];
  const validator = page().jQuery && page().jQuery!(form).validate?.();
  if (validator) {
    if (!validator.form()) {
      for (const e of validator.errorList) {
        const key = KEY_OF[e.element.getAttribute("name") ?? ""];
        if (key && !empty.includes(key) && !invalid.includes(key)) invalid.push(key);
      }
    }
  } else if (!form.checkValidity()) {
    invalid.push("some fields");
  }
  const ticked = captchaTicked();
  if (empty.length || invalid.length || !ticked) {
    const why: string[] = [];
    if (empty.length) why.push(`still empty: ${empty.join(", ")}`);
    if (invalid.length) why.push(`not valid: ${invalid.join(", ")}`);
    if (!ticked) why.push("I'm not a robot is not ticked yet (only the visitor can tick it)");
    const first =
      empty.concat(invalid).map((k) => FIELDS.find(([key]) => key === k)?.[1])
        .map((n) => (n ? field(form, n) : null))
        .find((el): el is Field => Boolean(el)) ?? captchaBox();
    if (first) {
      await scrollTo(first);
      highlight(first.closest(".control-value") ?? first);
    }
    throw new Error(`Send Message not pressed: ${why.join("; ")}`);
  }
  const button = form.querySelector<HTMLButtonElement>("button[type=submit]");
  if (!button) throw new Error("the form has no Send Message button");
  javierSending = true;
  emit("enquiry_sent", { expedition: state.expedition, by: "javier" });
  if (BLOCK_SEND) {
    javierSending = false;
    return;
  }
  await scrollTo(button);
  await sleep(200); // Let the event leave the page before it posts.
  button.click();
}

// ─── The adapter ──────────────────────────────────────────────────────────

const COMMANDS: Record<string, (payload: never) => Promise<void>> = {
  check_availability: checkAvailability,
  fill_enquiry: fillEnquiry,
  send_enquiry: sendEnquiry,
};

const WHAT: Record<string, string> = {
  navigate: "open www.explora.com pages",
  show_section: "show a section of www.explora.com",
  open_faq: "open www.explora.com's questions",
};

async function run(command: string, payload: unknown): Promise<{ ok: boolean; error?: string }> {
  const fn = COMMANDS[command];
  if (!fn) return { ok: false, error: `the booking site cannot ${WHAT[command] ?? command.replace(/_/g, " ")}` };
  busy++;
  try {
    await fn((payload ?? {}) as never);
    return { ok: true };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  } finally {
    busy--;
  }
}

if (location.host === "reservations.explora.com" && !window.voqalizeExplora) {
  styleThePage();
  watch();
  watchEnquiry();
  window.addEventListener("pagehide", clearHighlight);
  window.voqalizeExplora = { run, context, start, commands: Object.keys(COMMANDS) } satisfies Adapter;
}

export {};
