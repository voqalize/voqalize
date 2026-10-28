/**
 * Inside the HubSpot Meetings frame on enveedo.com/book-a-demo: the demo
 * scheduler (Elis Martinez; 15 mins, 30 mins or 1 hour, on Microsoft Teams).
 *
 * The scheduler is HubSpot's, in a cross-origin frame (meetings.hubspot.com),
 * so the page's own script cannot reach into it. This script runs in every
 * meetings.hubspot.com frame (`all_frames`) but acts only when the page
 * holding it is Enveedo's (`location.ancestorOrigins`), and takes its orders
 * from the page over `postMessage`:
 *
 *   - `state`: where the booking is — still loading, the calendar's open days
 *     (and, once a day is chosen, its times and the meeting lengths), or the
 *     details step and what is still empty;
 *   - `book`: choose a length, a day and a time, and fill in the first name,
 *     last name and email, as far as the order goes.
 *
 * Every change it sees, whoever caused it, goes back to the page as
 * `{ voqalizeMeetings: state }`.
 *
 * The frame's language follows the visitor's browser, not the page (a
 * Spanish browser gets Spanish labels and a 24-hour clock), so nothing here
 * matches visible words: HubSpot's test ids, ARIA state, `data-timestamp` and
 * its i18n keys only. Times are reported as "10:30am" whatever the clock.
 *
 * It never presses Confirm. While `DEMO_BLOCK_SUBMIT` is on, the visitor's
 * own press is stopped before HubSpot sees it and reported
 * (`voqalizeMeetingsScheduled`, `blocked: true`), so a preview call never puts
 * a real meeting in Enveedo's calendar.
 */

const DEMO_BLOCK_SUBMIT = true;
const PARENTS = /^https:\/\/(www\.)?enveedo\.com$/;
const WAIT_MS = 8000;

type Step = "loading" | "calendar" | "details" | "scheduled";

export interface BookOrder {
  duration?: string | null;
  day?: string | null;
  time?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
}

export interface MeetingsState {
  step: Step;
  duration: string;
  durations: string[];
  month: string;
  days: string[];
  date: string;
  times: string[];
  time: string;
  timezone: string;
  filled: { first_name: string; last_name: string; email: string };
  missing: string[];
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const clean = (s: string | null | undefined) => (s ?? "").replace(/\s+/g, " ").trim();

async function waitFor<T>(fn: () => T | null | undefined | false, ms = WAIT_MS): Promise<T | null> {
  const until = Date.now() + ms;
  for (;;) {
    const v = fn();
    if (v) return v;
    if (Date.now() > until) return null;
    await sleep(100);
  }
}

function parentOrigin(): string | null {
  const origins = location.ancestorOrigins;
  const top = origins && origins.length ? origins[0] : "";
  return PARENTS.test(top) ? top : null;
}

// ─── Times and days, whatever the clock ──────────────────────────────────

/** A time as "10:30am": from "10:30 am", "10:30am", "10.30 a. m.", "14:15",
 *  "2pm". A time without am/pm is read on a 24-hour clock. */
export function normTime(said: string | null | undefined): string {
  const flat = clean(said)
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace(/a\.?m\.?/, "am")
    .replace(/p\.?m\.?/, "pm")
    .replace(/h(rs?)?$/, "")
    .replace(".", ":");
  const m = flat.match(/^(\d{1,2})(?::(\d{2}))?(am|pm)?$/);
  if (!m) return flat;
  let h = Number(m[1]);
  const min = m[2] ?? "00";
  let ap = m[3];
  if (!ap) {
    ap = h >= 12 ? "pm" : "am";
    if (h > 12) h -= 12;
  }
  return `${h === 0 ? 12 : h}:${min}${ap}`;
}

const pad = (n: number) => String(n).padStart(2, "0");

/** The month names of the frame's language, English and Spanish, to read the
 *  month label ("October 2026", "octubre 2026"). */
function monthIndex(name: string): number {
  const want = clean(name).toLowerCase().replace(/\bde\b/g, "").trim();
  const langs = [document.documentElement.lang || "en", "en", "es"];
  for (const lang of langs) {
    for (let m = 0; m < 12; m++) {
      let label = "";
      try {
        label = new Intl.DateTimeFormat(lang, { month: "long", timeZone: "UTC" }).format(Date.UTC(2026, m, 15));
      } catch {
        continue;
      }
      if (label.toLowerCase() === want) return m;
    }
  }
  return -1;
}

/** The calendar's month as {year, month 0–11}, from its label. */
function shownMonth(): { year: number; month: number } | null {
  const label = clean(document.querySelector("[data-test-id=current-month-label]")?.textContent);
  const m = label.match(/^(.*?)\s*(\d{4})$/);
  if (!m) return null;
  const month = monthIndex(m[1]);
  return month < 0 ? null : { year: Number(m[2]), month };
}

/** The timezone's offset from UTC in minutes, from the picker's words
 *  ("UTC -04:00 Eastern Time"); remembered for the details step, which does
 *  not show it. */
let knownOffset: number | null = null;
function offset(): number | null {
  const text = clean(document.querySelector("[data-test-id=timezone-select]")?.textContent);
  const m = text.match(/UTC\s*([+-−])\s*(\d{1,2}):(\d{2})/i);
  if (m) knownOffset = (m[1] === "+" ? 1 : -1) * (Number(m[2]) * 60 + Number(m[3]));
  return knownOffset;
}

/** A start time (UTC epoch ms) as the scheduler shows it: the ISO day and
 *  "10:30am", in the timezone it shows times in. */
function localParts(ts: number): { day: string; time: string } {
  const off = offset();
  if (off !== null) {
    const d = new Date(ts + off * 60_000);
    const h = d.getUTCHours();
    return {
      day: `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`,
      time: `${h % 12 || 12}:${pad(d.getUTCMinutes())}${h < 12 ? "am" : "pm"}`,
    };
  }
  const d = new Date(ts);
  const h = d.getHours();
  return {
    day: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
    time: `${h % 12 || 12}:${pad(d.getMinutes())}${h < 12 ? "am" : "pm"}`,
  };
}

// ─── Reading the frame ──────────────────────────────────────────────────

const shown = (el: Element) => {
  const s = (el as HTMLElement).style;
  if (s && s.visibility === "hidden") return false;
  return getComputedStyle(el).visibility !== "hidden";
};

/** The open days of the month shown (other months' days are in the grid,
 *  hidden). */
const dayButtons = () =>
  [...document.querySelectorAll<HTMLButtonElement>("[data-test-id=available-date]")].filter(
    (b) => b.getAttribute("aria-disabled") !== "true" && shown(b),
  );
const anyDays = () => document.querySelectorAll("[data-test-id=available-date], [data-test-id=unavailable-date]").length > 0;
const slots = () => [...document.querySelectorAll<HTMLElement>("[data-test-id=time-picker-btn]")];
const input = (id: string) => document.querySelector<HTMLInputElement>(`[data-test-id=${id}]`);
const FIELDS = {
  first_name: "confirm-firstName-field",
  last_name: "confirm-lastName-field",
  email: "booking-form-field-email-input",
} as const;

/** The forward button when it is Confirm (the times step's "Next" shares its
 *  test id), by HubSpot's i18n key. */
function confirmButton(from?: Element | null): HTMLElement | null {
  const el = from ? from.closest?.("[data-test-id=forward-btn]") : document.querySelector("[data-test-id=forward-btn]");
  return el && el.querySelector('i18n-string[data-key^="buttons.confirm"]') ? (el as HTMLElement) : null;
}

/** The day number a day button shows ("28"), whatever its words. */
const dayNumber = (b: Element) => Number(clean(b.querySelector("span")?.textContent ?? b.textContent).match(/\d+/)?.[0] ?? NaN);

function isoOf(b: Element): string {
  const m = shownMonth();
  const n = dayNumber(b);
  return m && n ? `${m.year}-${pad(m.month + 1)}-${pad(n)}` : "";
}

/** The day last chosen, by the visitor's click or ours: the stepped layout
 *  hides the calendar once a day is chosen. */
let chosenDay = "";

function step(): Step {
  if (input(FIELDS.first_name)) return "details";
  if (slots().length || anyDays()) return "calendar";
  return "loading";
}

/** The meeting length, as the brain names it: "15 mins", "30 mins", "1 hour". */
function minutesOf(text: string): number {
  const t = clean(text).toLowerCase();
  const n = Number(t.match(/\d+/)?.[0] ?? NaN);
  if (Number.isNaN(n)) return NaN;
  return /hour|hora|heure|stunde|\bh\b/.test(t) ? n * 60 : n;
}
const lengthName = (min: number) => (min === 60 ? "1 hour" : min % 60 === 0 ? `${min / 60} hours` : `${min} mins`);
const durationButtons = () => [...document.querySelectorAll<HTMLElement>("#duration-select [role=radio]")];

function readState(): MeetingsState {
  const s = step();
  const durations = durationButtons();
  const chosenDuration = durations.find((d) => d.getAttribute("aria-checked") === "true");
  const base: MeetingsState = {
    step: s,
    duration: chosenDuration ? lengthName(minutesOf(chosenDuration.textContent ?? "")) : "",
    durations: durations.map((d) => lengthName(minutesOf(d.textContent ?? ""))),
    month: clean(document.querySelector("[data-test-id=current-month-label]")?.textContent),
    days: [],
    date: "",
    times: [],
    time: "",
    timezone: clean(document.querySelector("[data-test-id=timezone-select]")?.textContent),
    filled: { first_name: "", last_name: "", email: "" },
    missing: [],
  };
  offset();
  if (s === "details") {
    const ts = Number(document.querySelector("#meeting-confirmation-form")?.getAttribute("data-timestamp") ?? NaN);
    if (!Number.isNaN(ts)) {
      const p = localParts(ts);
      base.date = chosenDay || p.day;
      base.time = p.time;
    }
    for (const key of Object.keys(FIELDS) as (keyof typeof FIELDS)[]) {
      const el = input(FIELDS[key]);
      const v = clean(el?.value);
      base.filled[key] = v;
      if (!v || el?.getAttribute("aria-invalid") === "true") base.missing.push(key);
    }
    return base;
  }
  if (s === "calendar") {
    base.days = dayButtons().map(isoOf).filter(Boolean);
    const pressed = document.querySelector("[data-test-id=available-date][aria-pressed=true]");
    if (pressed) chosenDay = isoOf(pressed) || chosenDay;
    const times = slots();
    if (times.length) {
      base.times = times.map(slotTime);
      base.date = chosenDay || localParts(Number(times[0].getAttribute("data-timestamp"))).day;
    } else if (pressed) {
      base.date = chosenDay;
    }
  }
  return base;
}

/** A slot's start as "10:30am": its own words when they read as a time,
 *  else its timestamp. */
function slotTime(el: Element): string {
  const said = normTime(el.textContent);
  if (/^\d{1,2}:\d{2}(am|pm)$/.test(said)) return said;
  const ts = Number(el.getAttribute("data-timestamp"));
  return Number.isNaN(ts) ? said : localParts(ts).time;
}

// ─── Acting in it ───────────────────────────────────────────────────────

/** Set a value the way typing would, so React's state takes it, then leave
 *  the field: HubSpot checks the email on the server on its blur. */
function setNative(el: HTMLInputElement, value: string): void {
  el.focus();
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  el.blur();
}

const press = (el: HTMLElement) => {
  el.scrollIntoView({ block: "center" });
  el.click();
};

async function back(): Promise<void> {
  const b = document.querySelector<HTMLElement>("[data-test-id=back-btn]");
  if (b) press(b);
  await sleep(200);
}

/** The ISO day `said` names: "2026-11-04", or a bare day number of the month
 *  shown. */
function wantedDay(said: string): string | null {
  const iso = said.match(/(\d{4})-(\d{2})-(\d{2})/);
  if (iso) return `${iso[1]}-${iso[2]}-${iso[3]}`;
  const n = said.match(/\b(\d{1,2})\b/);
  const m = shownMonth();
  return n && m ? `${m.year}-${pad(m.month + 1)}-${pad(Number(n[1]))}` : null;
}

/** Page the calendar to the month of `iso`. */
async function toMonth(iso: string): Promise<string | null> {
  for (let i = 0; i < 4; i++) {
    const m = shownMonth();
    if (!m) return "the calendar's month could not be read";
    const [y, mo] = iso.split("-").map(Number);
    const diff = (y - m.year) * 12 + (mo - 1 - m.month);
    if (diff === 0) return null;
    const btn = document.querySelector<HTMLElement>(
      `[data-test-id=date-picker-header-${diff > 0 ? "next" : "prev"}-btn]`,
    );
    if (!btn || btn.getAttribute("aria-disabled") === "true") return `the calendar does not go to ${iso.slice(0, 7)}`;
    const label = clean(document.querySelector("[data-test-id=current-month-label]")?.textContent);
    press(btn);
    await waitFor(() => clean(document.querySelector("[data-test-id=current-month-label]")?.textContent) !== label, 4000);
    // The month's open days arrive a moment after its label.
    await waitFor(() => !document.querySelector("[data-loading=true]") && dayButtons().length > 0, 3000);
    await sleep(300);
  }
  return `the calendar did not reach ${iso.slice(0, 7)}`;
}

async function chooseDuration(said: string): Promise<string | null> {
  const want = minutesOf(said) || (/hour|hora/i.test(said) ? 60 : NaN);
  const options = durationButtons();
  if (!options.length) return null;
  const opt = options.find((o) => minutesOf(o.textContent ?? "") === want);
  if (!opt) return `no ${said} meeting; it offers ${options.map((o) => lengthName(minutesOf(o.textContent ?? ""))).join(", ")}`;
  if (opt.getAttribute("aria-checked") !== "true") {
    const before = slots().map((s) => s.getAttribute("data-timestamp")).join();
    press(opt);
    await waitFor(() => slots().map((s) => s.getAttribute("data-timestamp")).join() !== before, 3000);
    await sleep(200);
  }
  return null;
}

async function book(order: BookOrder): Promise<string | null> {
  // From the details step, a new day or time goes back to the times first.
  if (step() === "details" && (order.day || order.time || order.duration)) {
    await back();
    await waitFor(() => slots().length > 0, 4000);
  }
  if (order.day) {
    const iso = wantedDay(order.day);
    if (!iso) return `"${order.day}" is not a day; give it as 2026-11-04`;
    if (!(chosenDay === iso && slots().length)) {
      // The stepped layout shows the times instead of the calendar.
      if (!anyDays() && slots().length) {
        await back();
        await waitFor(anyDays, 4000);
      }
      const off = await toMonth(iso);
      if (off) return off;
      const btn = dayButtons().find((b) => isoOf(b) === iso);
      if (!btn) return `${iso} is not open; open days: ${dayButtons().map(isoOf).join(", ") || "none this month"}`;
      chosenDay = iso;
      press(btn);
      if (!(await waitFor(() => slots().length > 0, 5000))) return `${iso}'s times did not appear`;
      await sleep(200);
    }
  }
  if (order.duration && step() === "calendar") {
    if (!slots().length && !durationButtons().length) return "choose a day first: the meeting length is chosen with its times";
    const why = await chooseDuration(order.duration);
    if (why) return why;
  }
  if (order.time) {
    if (!slots().length) return "choose a day first: no times are showing";
    const want = normTime(order.time);
    const slot = slots().find((s) => slotTime(s) === want);
    if (!slot) return `no ${order.time} on ${chosenDay || "that day"}; open times: ${slots().map(slotTime).join(", ")}`;
    press(slot);
    if (!(await waitFor(() => input(FIELDS.first_name), 5000))) return "the details step did not open";
    await sleep(250);
  }
  return fillDetails(order);
}

/** What the visitor gave, kept for when the details step opens. */
let pending: Partial<Record<keyof typeof FIELDS, string>> = {};

async function fillDetails(order: BookOrder): Promise<string | null> {
  for (const key of Object.keys(FIELDS) as (keyof typeof FIELDS)[]) {
    const v = clean(order[key]);
    if (v) pending[key] = v;
  }
  if (step() !== "details") return null;
  for (const key of Object.keys(FIELDS) as (keyof typeof FIELDS)[]) {
    const v = pending[key];
    const el = input(FIELDS[key]);
    if (v && el && clean(el.value) !== v) {
      setNative(el, v);
      await sleep(60);
    }
  }
  pending = {};
  // HubSpot checks the email on its server: wait for its answer.
  const email = input(FIELDS.email);
  if (email && clean(email.value)) {
    await waitFor(() => {
      const msg = clean(document.getElementById(`${email.id}-validationMessage`)?.textContent);
      return !/…|\.\.\./.test(msg) && (email.getAttribute("aria-invalid") === "true" || !msg);
    }, 4500);
    if (email.getAttribute("aria-invalid") === "true") return `the scheduler refused the email "${clean(email.value)}"`;
  }
  return null;
}

// ─── Talking to the page ────────────────────────────────────────────────

let shownToast = 0;
function toast(btn: Element): void {
  if (Date.now() - shownToast < 1500) return;
  shownToast = Date.now();
  document.querySelector("[data-voqalize=toast]")?.remove();
  const note = document.createElement("p");
  note.setAttribute("data-voqalize", "toast");
  note.textContent = /^es/i.test(document.documentElement.lang)
    ? "Vista previa: esta reunión no se agendó en el calendario de Enveedo."
    : "Preview: this meeting was not booked in Enveedo's calendar.";
  Object.assign(note.style, { margin: "10px 0 0", color: "#7552E0", font: "500 13px/1.4 system-ui, sans-serif", textAlign: "center" });
  btn.insertAdjacentElement("afterend", note);
  setTimeout(() => note.remove(), 6000);
}

function start(): void {
  const parent = parentOrigin();
  if (!parent) return;
  let last = "";
  const report = (force = false) => {
    const s = readState();
    if (s.step === "loading" && !force) return;
    const key = JSON.stringify(s);
    if (!force && key === last) return;
    last = key;
    window.parent.postMessage({ voqalizeMeetings: s }, parent);
  };

  window.addEventListener("message", (e: MessageEvent) => {
    if (e.origin !== parent || e.source !== window.parent) return;
    const msg = (e.data as { voqalizeMeetingsCmd?: { id: number; cmd: string; order?: BookOrder } } | null)
      ?.voqalizeMeetingsCmd;
    if (!msg) return;
    const reply = (error: string | null) =>
      window.parent.postMessage({ voqalizeMeetingsDone: { id: msg.id, error, state: readState() } }, parent);
    if (msg.cmd === "state") return reply(null);
    if (msg.cmd === "book") {
      void book(msg.order ?? {})
        .catch((error: unknown) => String(error))
        .then((error) => {
          last = JSON.stringify(readState());
          reply(error);
        });
    }
  });

  // The visitor's own clicks on a day: remembered, since the stepped layout
  // hides the calendar once one is chosen.
  window.addEventListener(
    "click",
    (e) => {
      const day = (e.target as Element | null)?.closest?.("[data-test-id=available-date]");
      if (day) chosenDay = isoOf(day) || chosenDay;
    },
    true,
  );

  // Every change, whoever made it: reported as it settles.
  let timer: ReturnType<typeof setTimeout> | null = null;
  const settle = () => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      if (step() === "details" && Object.keys(pending).length) void fillDetails({});
      report();
    }, 350);
  };
  new MutationObserver(settle).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["aria-checked", "aria-pressed", "aria-disabled", "aria-invalid"] });
  document.addEventListener("input", settle, true);

  // Confirm is the visitor's. In this preview it is reported, then stopped
  // before HubSpot's own handler sees it (a React click on a type=button).
  let reported = 0;
  const onConfirm = (e: Event) => {
    if (e instanceof KeyboardEvent && e.key !== "Enter" && e.key !== " ") return;
    const btn = confirmButton(e.target as Element | null);
    if (!btn) return;
    if (DEMO_BLOCK_SUBMIT) {
      e.preventDefault();
      e.stopImmediatePropagation();
    }
    if (e.type !== "click" && e.type !== "keydown") return;
    if (Date.now() - reported < 1000) return;
    reported = Date.now();
    const s = readState();
    window.parent.postMessage(
      { voqalizeMeetingsScheduled: { date: s.date, time: s.time, filled: s.filled, blocked: DEMO_BLOCK_SUBMIT } },
      parent,
    );
    if (DEMO_BLOCK_SUBMIT) toast(btn);
  };
  for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup", "click", "keydown"]) {
    window.addEventListener(type, onConfirm, true);
  }

  report();
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
else start();
