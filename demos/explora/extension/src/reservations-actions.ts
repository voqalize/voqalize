/**
 * The site adapter for reservations.explora.com, Explora's booking engine
 * (an Art2Fly IBE): Javier checks a lodge's availability with the visitor and
 * fills in, and sends, an expedition's enquiry.
 *
 * It registers his booking moves with Stage (`Moves`). Each rings what it is
 * about to change with Stage's spotlight before it changes it, and answers
 * with one result: what it did, `refuse()` for a day, a number of nights, a
 * room or a field the page does not offer (with what it does), an error for
 * anything else. `explora.send_enquiry` sends the visitor's own details, so
 * it is a confirmed move: the brain sends it only behind their tick.
 *
 * Every step of the site is a full page load, so a move that spans steps (the
 * lodge's calendar, then its rooms) is carried to the next page with
 * `loadThen`: the same move is made again there, with the same `call_ref`,
 * and this file picks it up from wherever the page now stands; that page
 * answers for it. Every move is idempotent for that reason.
 *
 *   /ibe/paso1        the lodge (`select#destination`, whose inline onchange
 *                     reloads), the inline jQuery UI datepicker
 *                     (`#check_in_calendar`, hidden `#check_in_date`, open days
 *                     in `window.lista_disponibles`) and the nights
 *                     (`select#nights`, filled by `getStay(date)` over AJAX);
 *   /ibe/paso2        the rooms and rates. `choose_room` sets a room's
 *                     travellers and bed and presses its own "Add this
 *                     room", which opens the room's summary (`add_room`, a
 *                     GET, in a Magnific Popup iframe) with its "Go to
 *                     check-out" button: he rings that button for the
 *                     visitor and never presses it. Another room is added
 *                     through the popup's "Add more rooms". Nothing on paso3;
 *   /ibe/expeditions  the enquiry form `#form-expeditions` (jQuery Validate and
 *                     a reCAPTCHA v2 checkbox the visitor ticks themselves).
 *
 * This runs in the page's own world (MAIN), so the site's jQuery, `getStay`
 * and `grecaptcha` are in reach.
 */

import { domSettled, type MoveContext, type Spotlight } from "@voqalize/stage";
import { type Adapter, type PageKit } from "@voqalize/stage/extension";

import { clean, norm, type PageContext, pick, scrollTo, setField, sleep, styleThePage, visible, waitFor } from "./dom";
import { focusTab, inCallLanguage } from "./explora-actions";
import { scene } from "./scene.gen";
import {
  asStage, type CheckAvailabilityArgs, type ChooseRoomArgs, type EnquiryFields, type EnquiryReport, type FillEnquiryArgs, MOVE,
  type NavigateArgs, type NightsOption, type RoomOption, type StayState,
} from "./site";
import { SITE } from "./site-language";

type CheckAvailability = CheckAvailabilityArgs;
type ChooseRoom = ChooseRoomArgs;
type FillEnquiry = FillEnquiryArgs;

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
/** This page's spotlight (Stage's), set when the adapter starts. */
let spot: Spotlight | null = null;

/** Ring `target` (one element, several as one box, or each on its own with
 *  `separate`) and hold the move a beat: what it acts on next is ringed. */
function ring(target: Element | Element[], opts: { separate?: boolean } = {}): Promise<void> {
  // Through the running move's context when there is one: the brain hears
  // it is ringing (its time given again) and the result says when it rang.
  return current ? current.ring(target, opts) : (spot?.ring(target, opts) ?? Promise.resolve());
}

/** The move running now (Stage runs one at a time), set by `held`. */
let current: MoveContext | null = null;

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

function enquiryState(): EnquiryReport | null {
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

/** Say what the page is: once the call is up on it, and again whenever the
 *  tab comes back to the front (Stage's host runs it). */
function report(raw: (event: string, payload: unknown) => void): void {
  const next = asStage(raw);
  next("page_changed", context());
}

function start(raw: (event: string, payload: unknown) => void): () => void {
  const next = asStage(raw);
  emitter = next;
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

/** Load `url` and make `move` again on the page it lands on, which answers
 *  for it. Refuses to load the same URL twice in a few seconds: the site sent
 *  us back somewhere else, and loading again would loop. */
async function go(c: MoveContext, url: string, move: string, args: unknown, what: string): Promise<never> {
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
  if (!c.loadThen) throw new Error(`this page cannot load ${what}`);
  return c.loadThen(url, { move, args });
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
  const cell = await waitFor(() => dayCell(date), 1500);
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

async function checkAvailability(p: CheckAvailability, c: MoveContext): Promise<string> {
  speak(p);
  const code = clean(p.hotel_code).toUpperCase();
  if (!code) c.refuse("hotel_code", "no lodge was named");
  const date = p.date ? clean(p.date) : "";
  if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) c.refuse("date", `'${p.date}' is not a date (YYYY-MM-DD)`);
  const s = step();

  // Already on this stay's rooms: just show them.
  if (
    s === "paso2" &&
    p.rooms &&
    param("hotel_code").toUpperCase() === code &&
    (!date || param("check_in_date") === date) &&
    (!p.nights || Number(param("nights")) === p.nights)
  ) {
    // The rooms are the effect: reported at once, ringed after the result.
    emit("stay_state", roomsState());
    const list = document.querySelector("#room-list") ?? document.querySelector("#search");
    if (list) {
      c.after(async () => {
        await scrollTo(list, "top");
        const items = roomItems();
        await ring(items.length ? items : list);
      });
    }
    return `the rooms for ${roomsHotel() || code}`;
  }

  if (s !== "paso1" || selectedHotel()?.code !== code) {
    // The lodge's own calendar: the lodge picker this page shows goes first.
    const picker = destination();
    if (picker && visible(picker)) {
      await scrollTo(picker);
      await ring(picker);
    }
    return go(c, paso1Url(code, date), MOVE.checkAvailability, p, `the lodge ${code}`);
  }

  const hotel = selectedHotel()!;
  const cal = calendar();
  const month = p.month ? clean(p.month).slice(0, 7) : "";
  if (month && !date && /^\d{4}-\d{2}$/.test(month) && cal) {
    await scrollTo(cal);
    await ring(cal);
    await showMonth(month);
  }
  if (date) {
    const open = openDays();
    if (!open.includes(date)) {
      const near = nearest(date, open);
      c.refuse(
        "date",
        `${date} is not an open arrival day at ${hotel.label}` + (near.length ? "" : "; it has no open days at all"),
        near,
      );
    }
    if (chosenDate() !== date) {
      if (cal) {
        await scrollTo(cal);
        await ring(dayCell(date) ?? cal);
      }
      await selectDate(date);
    }
  }

  if (p.nights && chosenDate()) {
    const offered = nightsOffered();
    if (!offered.some((o) => o.nights === p.nights)) {
      c.refuse(
        "nights",
        `${p.nights} nights are not offered from ${chosenDate()} at ${hotel.label}` +
          (offered.length ? "" : "; no stay is available that day"),
        offered.map((o) => String(o.nights)),
      );
    }
    const s = nightsSelect()!;
    if (Number(s.value) !== p.nights) {
      const box = nightsBox();
      if (box.length) {
        await scrollTo(box[box.length - 1]!);
        await ring(box);
      }
      setField(s, String(p.nights));
    }
  }

  // What the page now shows, reported at once, then ringed: the nights for
  // the day, else the calendar. The ring trails the result, unless the rooms
  // load next: then the nights stay ringed long enough to see first.
  const chosen = chosenDate();
  const state = datesState();
  if (state) emit("stay_state", state);
  const shown = async () => {
    if (chosen) {
      const box = nightsBox();
      if (box.length) {
        await scrollTo(box[box.length - 1]!);
        await ring(box);
      }
    } else if (cal) {
      await scrollTo(cal);
      await ring(cal);
    }
  };
  if (p.rooms) await shown();
  else c.after(shown);
  const nights = Number(nightsSelect()?.value) || 0;

  if (p.rooms) {
    if (!chosen) c.refuse("rooms", "choose an arrival day first: the rooms need a date and nights");
    if (nights <= 0) c.refuse("rooms", `no stay is available from ${chosen} at ${hotel.label}`);
    // The nights stayed ringed long enough to see before the page goes.
    return go(c, paso2Url(code, chosen, nights), MOVE.checkAvailability, { ...p, date: chosen, nights }, "the rooms");
  }
  if (!chosen) return `${hotel.label}: the calendar, showing ${state?.month ?? "its first month"}`;
  return `${hotel.label}: arriving ${chosen}` + (nights > 0 ? `, ${nights} nights selected` : "");
}

/** The calendar's cell for `date`, when it is in the month on screen. */
function dayCell(date: string): HTMLElement | null {
  const [y, m, d] = date.split("-").map(Number);
  if (!y || !m || !d) return null;
  return (
    calendar()?.querySelector<HTMLElement>(
      `td[data-handler=selectDay][data-year="${y}"][data-month="${m - 1}"] a[data-date="${d}"]`,
    ) ?? null
  );
}

// ─── choose_room ──────────────────────────────────────────────────────────

/** A room on paso2: its item, its code (`room_<RM>_name`) and its name. */
interface Room {
  item: HTMLElement;
  code: string;
  name: string;
}

function rooms(): Room[] {
  const out: Room[] = [];
  for (const item of roomItems()) {
    const span = item.querySelector<HTMLElement>("[id^=room_][id$=_name]");
    const code = span?.id.match(/^room_(.+)_name$/)?.[1];
    const name = clean(span?.textContent);
    if (code && name) out.push({ item, code, name });
  }
  return out;
}

/** The bed select's value for what was said: K (King) or T (Twin). */
function bedValue(select: HTMLSelectElement, want: string): HTMLOptionElement | null {
  const opts = [...select.options].filter((o) => o.value);
  const w = norm(want);
  const code = /^(k|king|queen|double|matrimonial|one bed|cama king|cama matrimonial)\b/.test(w)
    ? "K"
    : /^(t|twin|twins|two beds|separate|single|singles|individual|individuales|dos camas|camas separadas)\b/.test(w)
      ? "T"
      : "";
  return opts.find((o) => o.value === code) ?? pick(want, opts, (o) => o.text);
}

/** The room summary popup's "Go to check-out" button, inside its iframe
 *  (same origin): found to be ringed, never pressed. */
function checkoutButton(): HTMLElement | null {
  const frame = document.querySelector<HTMLIFrameElement>(".mfp-content iframe, iframe.mfp-iframe");
  let doc: Document | null = null;
  try {
    doc = frame?.contentDocument ?? null;
  } catch {
    return null;
  }
  if (!doc) return null;
  const all = [...doc.querySelectorAll<HTMLElement>("a, button, input[type=submit], input[type=button]")];
  const label = (el: HTMLElement) => clean(el instanceof HTMLInputElement ? el.value : el.textContent);
  return (
    all.find((el) => visible(el) && /check.?out|ir a pagar|pagar|finalizar/i.test(label(el))) ?? null
  );
}

/** The room summary popup's own control labelled `label`, inside its iframe
 *  or around it. Never its check-out. */
function popupControl(label: RegExp): HTMLElement | null {
  const frame = document.querySelector<HTMLIFrameElement>(".mfp-content iframe, iframe.mfp-iframe");
  let doc: Document | null = null;
  try {
    doc = frame?.contentDocument ?? null;
  } catch {
    doc = null;
  }
  const roots: ParentNode[] = [doc, document.querySelector(".mfp-wrap")].filter((r): r is Document | HTMLElement => r !== null);
  const text = (el: HTMLElement) => clean(el instanceof HTMLInputElement ? el.value : el.textContent);
  for (const root of roots) {
    const all = [...root.querySelectorAll<HTMLElement>("a, button, input[type=submit], input[type=button]")];
    const hit = all.find((el) => label.test(text(el)) && !/check.?out|pagar|finalizar/i.test(text(el)));
    if (hit) return hit;
  }
  return null;
}

const ADD_MORE = /add more rooms|agregar m[aá]s habitaciones|a[nñ]adir m[aá]s habitaciones|m[aá]s habitaciones/i;

/**
 * Put the last room's summary away before the next room is added: its "Add
 * more rooms", as a visitor would, else the popup's close. That button may
 * load the rooms again, so the rest of this move is kept for the next page
 * first, and taken back if the page stays.
 */
async function closeSummary(rest: ChooseRoom, c: MoveContext): Promise<void> {
  if (!document.querySelector(".mfp-wrap")) return;
  const more = popupControl(ADD_MORE);
  await c.keep({ move: MOVE.chooseRoom, args: rest });
  if (more) {
    await ring(more);
    more.click();
  }
  else {
    const jq = (window as unknown as { jQuery?: { magnificPopup?: { close?: () => void } } }).jQuery;
    if (jq?.magnificPopup?.close) jq.magnificPopup.close();
    else document.querySelector<HTMLElement>(".mfp-close")?.click();
  }
  const closed = await waitFor(() => !document.querySelector(".mfp-wrap"), 6000);
  // Still on this page: the move goes on here, not on the next one.
  await c.drop();
  if (!closed) throw new Error("the last room's summary is still open: its Add more rooms did not close it");
  await sleep(600);
}

/** Add `p.count` rooms (one by default), one after the other. */
async function chooseRoom(p: ChooseRoom, c: MoveContext): Promise<string> {
  const count = Math.max(1, Math.min(4, Math.round(p.count ?? 1)));
  let name = clean(p.room);
  for (let i = 0; i < count; i++) {
    await closeSummary({ ...p, count: count - i }, c);
    name = await addRoom(p, c);
  }
  return count > 1 ? `added ${count} ${name} rooms; the check-out button is on screen` : `added ${name}; the check-out button is on screen`;
}

async function addRoom(p: ChooseRoom, c: MoveContext): Promise<string> {
  if (step() !== "paso2") throw new Error("the rooms are not open: check a lodge's availability through to its rooms first");
  const list = rooms();
  if (!list.length) throw new Error("this stay has no rooms to choose");
  const names = list.map((r) => r.name);
  const want = clean(p.room);
  if (!want) c.refuse("room", "say which room", names);
  const room = pick(want, list, (r) => r.name);
  if (!room) return c.refuse("room", `no room "${want}" here`, names);
  const form = room.item.querySelector<HTMLFormElement>("form.room_form") ?? room.item.querySelector("form");
  const button = room.item.querySelector<HTMLButtonElement>("button.room-select, button[type=submit]");
  if (!form || !button) throw new Error(`${room.name} cannot be added on this page`);

  const travellers = document.getElementById(`room_${room.code}_nadults`) as HTMLSelectElement | null;
  const travellersOpt = p.travellers != null && travellers
    ? [...travellers.options].find((o) => Number(o.value) === p.travellers)
    : null;
  if (p.travellers != null && travellers && !travellersOpt) {
    const offered = [...travellers.options].map((o) => clean(o.text).toLowerCase());
    c.refuse("travellers", `${room.name} is for ${offered.join(" or ")}, not ${p.travellers}`, offered);
  }
  const bed = document.getElementById(`room_${room.code}_bedtype`) as HTMLSelectElement | null;
  const bedOpt = p.bed && bed ? bedValue(bed, p.bed) : null;
  if (p.bed && bed && !bedOpt) {
    const offered = [...bed.options].filter((o) => o.value).map((o) => clean(o.text));
    c.refuse("bed", `${room.name} has no '${p.bed}' bed; it has ${offered.join(" or ")}`, offered);
  }

  // The room, ringed long enough to see, before anything on it changes.
  await scrollTo(room.item, "center");
  await ring(room.item);
  // Its inline onchange (`adjust_price`) shows the price for that many.
  if (travellers && travellersOpt && travellers.value !== travellersOpt.value) setField(travellers, travellersOpt.value);
  if (bed && bedOpt && bed.value !== bedOpt.value) setField(bed, bedOpt.value);
  emit("stay_state", roomsState());
  // The site requires the bed type before it adds the room: the visitor says.
  if (bed && !bed.value) {
    const offered = [...bed.options].filter((o) => o.value).map((o) => clean(o.text));
    await ring(bed.closest(".left-label") ?? bed);
    c.refuse("bed", `${room.name} needs a bed type before it can be added: ${offered.join(" or ")}`, offered);
  }

  // Its own "Add this room": the site validates the form and opens the
  // room's summary in a popup (`add_room`, a GET). Never anything past it.
  await ring(button);
  button.click();
  const popup = await waitFor(() => document.querySelector<HTMLElement>(".mfp-content iframe, .mfp-wrap"), 4000);
  if (!popup) throw new Error(`pressed Add this room for ${room.name}, but its summary did not open`);
  const checkout = await waitFor(checkoutButton, 8000);
  if (checkout) {
    // Shown, never pressed: the visitor goes to check-out themselves.
    checkout.scrollIntoView({ block: "center" });
    await ring(checkout);
  } else {
    const content = document.querySelector<HTMLElement>(".mfp-content");
    if (content) await ring(content);
  }
  emit("stay_state", roomsState());
  if (!checkout) throw new Error(`${room.name}'s summary opened, but its check-out button did not show`);
  return room.name;
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

async function fillEnquiry(p: FillEnquiry, c: MoveContext): Promise<string> {
  speak(p);
  const code = clean(p.expedition_code).toUpperCase();
  if (!code) c.refuse("expedition_code", "no expedition was named");
  const form = enquiryForm();
  if (step() !== "expeditions" || param("expedition_request").toUpperCase() !== code || !form) {
    const url = `${BASE}/ibe/expeditions?expedition_request=${encodeURIComponent(code)}&language=${LANGUAGE}`;
    return go(c, url, MOVE.fillEnquiry, p, `the enquiry form for ${code}`);
  }

  const problems: [string, string][] = [];
  const filled: Field[] = [];
  const row = (el: Element) => el.closest(".control-value") ?? el;
  const values: Partial<Record<FieldKey, string | null>> = {
    title: p.title,
    first_name: p.first_name,
    last_name: p.last_name,
    email: p.email,
    phone: p.phone,
    country: p.country,
    message: p.message,
  };
  // The rows about to be filled, ringed before anything is typed in them.
  const toFill = FIELDS.filter(([key]) => values[key] != null && clean(String(values[key])) !== "")
    .map(([, name]) => field(form, name))
    .filter((el): el is Field => Boolean(el));
  if (toFill.length) {
    await scrollTo(row(toFill[0]!));
    await ring(toFill.map(row), { separate: true });
  }
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
        problems.push(["title", `title '${want}' is not on the form (Mr. or Ms.)`]);
        continue;
      }
      value = t;
      titleChosen = true;
    } else if (key === "country" && el instanceof HTMLSelectElement) {
      const opt = countryOption(el, want);
      if (!opt) {
        problems.push(["country", `nationality '${want}' is not on the form's list`]);
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
  if (firstEmpty) {
    await scrollTo(row(firstEmpty));
    // Each filled row on its own, as the form marks each.
    await ring(filled.length ? filled.map(row) : [row(firstEmpty)], { separate: true });
  } else if (captcha) {
    await scrollTo(captcha);
    await ring(captcha);
  }
  emit("enquiry_state", state);
  if (problems.length) {
    c.refuse(problems[0]![0], `filled the rest, but ${problems.map(([, why]) => why).join("; ")}`);
  }
  const keys = FIELDS.filter(([, name]) => filled.some((el) => el.name === name)).map(([k]) => k);
  return `the ${expeditionName() || code} enquiry form` + (keys.length ? `; filled ${keys.join(", ")}` : "");
}

// ─── send_enquiry ─────────────────────────────────────────────────────────

const KEY_OF: Record<string, string> = Object.fromEntries(FIELDS.map(([k, n]) => [n, k]));

async function sendEnquiry(c: MoveContext): Promise<string> {
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
      await ring(first.closest(".control-value") ?? first);
    }
    return c.refuse("form", `Send Message not pressed: ${why.join("; ")}`);
  }
  const button = form.querySelector<HTMLButtonElement>("button[type=submit]");
  if (!button) throw new Error("the form has no Send Message button");
  // The visitor's own details leave here: the button, ringed, then pressed.
  await scrollTo(button);
  await ring(button);
  javierSending = true;
  emit("enquiry_sent", { expedition: state.expedition, by: "javier" });
  if (BLOCK_SEND) {
    javierSending = false;
    return "Send Message not pressed (sending is blocked in this build)";
  }
  await sleep(200); // Let the event leave the page before it posts.
  button.click();
  return `pressed Send Message on the ${state.expedition || "expedition"} enquiry`;
}

// ─── site_language ────────────────────────────────────────────────────────

/** Whether anything has been typed or chosen in the enquiry form, by the
 *  visitor or by Javier: a reload would throw it away. */
function enquiryTouched(): boolean {
  const form = enquiryForm();
  if (!form) return false;
  if (titleChosen) return true;
  return [...form.querySelectorAll<Field>("input, textarea, select")].some((el) => {
    if (el instanceof HTMLInputElement && ["hidden", "submit", "button", "checkbox", "radio"].includes(el.type)) return false;
    if (el instanceof HTMLSelectElement) return el.name !== "title" && el.selectedIndex > 0;
    return clean(el.value) !== "";
  });
}

/**
 * Show this step in the call's language: the same GET page with
 * `?language=ES|EN` swapped in. Only where reloading loses nothing: paso1
 * (with the lodge and day picked carried in the URL), paso2 when its URL
 * carries the stay (the GET Continue makes), and the expedition enquiry while
 * nothing is filled in. Never paso3 or any other step, and never a re-post:
 * these three steps are GET pages, and this loads a new URL rather than
 * reloading. Where it is not safe the page stays as it is, without an error:
 * the call has moved language either way, and the next page Javier opens is
 * in it.
 */
async function siteLanguage({ language }: { language: "en" | "es" }, kit: PageKit): Promise<void> {
  const want = language === "es" ? "ES" : "EN";
  LANGUAGE = want;
  const s = step();
  const url = new URL(location.href);
  if (url.searchParams.get("language")?.toUpperCase() === want) return;
  if (s === "paso1") {
    const code = selectedHotel()?.code;
    if (code) url.searchParams.set("hotel_code", code);
    const day = chosenDate();
    if (day) url.searchParams.set("check_in_date", day);
  } else if (s === "paso2") {
    if (!["hotel_code", "check_in_date", "nights"].every((k) => url.searchParams.get(k))) {
      return void console.info("voqalize: these rooms were not opened by a GET; the page keeps its language");
    }
  } else if (s === "expeditions") {
    if (!url.searchParams.get("expedition_request") || enquiryTouched()) {
      return void console.info("voqalize: the enquiry has been filled in; the page keeps its language");
    }
  } else {
    return;
  }
  url.searchParams.set("language", want);
  kit.spotlight.clear();
  await kit.loadThen(url.href);
}

// ─── www.explora.com, from here ───────────────────────────────────────────

/** A www.explora.com page, from the booking site: in the call's language, and
 *  answered once the page it lands on is up. Nothing here points at it, so
 *  nothing is ringed before the page goes. */
async function navigate(args: NavigateArgs, c: MoveContext, kit: PageKit): Promise<never> {
  if (typeof args.path !== "string" || !args.path) return c.refuse("path", `not a path: ${String(args.path)}`);
  let url: URL;
  try {
    url = new URL(await inCallLanguage(args.path, kit), SITE);
  } catch (error) {
    return c.refuse("path", `not a page: ${args.path} (${String(error)})`);
  }
  if (!c.loadThen) throw new Error("this page cannot load www.explora.com");
  return c.loadThen(url.href);
}

// ─── The adapter ──────────────────────────────────────────────────────────

/** While Javier is moving the page, the watcher holds its reports. */
function held<A>(fn: (args: A, c: MoveContext) => Promise<string>): (args: A, c: MoveContext) => Promise<string> {
  return async (args, c) => {
    busy++;
    current = c;
    try {
      return await fn(args, c);
    } finally {
      busy--;
      if (current === c) current = null;
    }
  };
}

const NOT_HERE = "the booking site cannot show a section of www.explora.com";

/** reservations.explora.com's moves, registered with Stage, and what the page reports. */
export const reservationsAdapter: Adapter = (moves, kit) => {
  spot = kit.spotlight;
  styleThePage();
  watch();
  watchEnquiry();
  window.addEventListener("pagehide", () => kit.spotlight.clear());
  scene.registerAll(moves, {
    [MOVE.checkAvailability]: held(checkAvailability),
    [MOVE.chooseRoom]: held(chooseRoom),
    [MOVE.fillEnquiry]: held(fillEnquiry),
    [MOVE.sendEnquiry]: held((_, c) => sendEnquiry(c)),
    [MOVE.navigate]: (a, c) => navigate(a, c, kit),
    [MOVE.show]: (_, c) => c.refuse("target", NOT_HERE),
    [MOVE.faq]: (_, c) => c.refuse("question", NOT_HERE),
    [MOVE.twin]: (_, c) => c.refuse("language", "the booking site follows the call's language by itself"),
    [MOVE.focusTab]: focusTab,
  });
  return {
    context: () => ({ ...context() }),
    report,
    start,
    async command(command, payload) {
      if (command === "site_language") await siteLanguage(payload as { language: "en" | "es" }, kit);
    },
    // The booking site's own calendar and selects bind on DOMContentLoaded;
    // its `load` waits on trackers. A press waits for the page to settle.
    ready: () => domSettled(),
  };
};
