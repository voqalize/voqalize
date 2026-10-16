/**
 * Inside the Calendly frame on sendpotion.com/demo/ — the demo booking form.
 *
 * The booking form is Calendly's, in a cross-origin frame, so the page's own
 * script cannot reach into it. This script runs in that frame only when the
 * page holding it is SendPotion's (`location.ancestorOrigins`), and takes its
 * orders from the page over `postMessage`:
 *
 *   - `state`: report where the booking is — the calendar's open days, the
 *     chosen day's times, or the details step and what is still empty;
 *   - `book`: choose a day and a time, press Next, and fill in the name, email
 *     and notes the visitor gave, as far as they go.
 *
 * Every change it sees, whoever caused it, goes back to the page as
 * `{ voqalizeCalendly: state }`. It never presses "Schedule Event": that is
 * the visitor's. While `DEMO_BLOCK_SUBMIT` is on, their press is reported and
 * stopped, so a demo call never puts a real meeting in SendPotion's calendar.
 */

const DEMO_BLOCK_SUBMIT = true;
const PARENTS = /^https:\/\/(www\.)?sendpotion\.com$/;
const WAIT_MS = 8000;

type Step = "calendar" | "details" | "scheduled";

interface Fill {
  name?: string | null;
  email?: string | null;
  notes?: string | null;
}

interface BookOrder {
  day?: string | null;
  time?: string | null;
  fill?: Fill;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const clean = (s: string | null | undefined) => (s ?? "").replace(/\s+/g, " ").trim();
const fold = (s: string | null | undefined) => clean(s).toLowerCase().replace(/[.,]/g, "");

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

// ─── Reading the frame ──────────────────────────────────────────────────

const dayButtons = () =>
  [...document.querySelectorAll<HTMLButtonElement>("button[aria-label*=' - Times available']")].filter(
    (b) => !b.disabled,
  );
const timeButtons = () => [...document.querySelectorAll<HTMLButtonElement>("button[data-container='time-button']")];
const field = (name: string) =>
  document.querySelector<HTMLInputElement | HTMLTextAreaElement>(
    name === "notes" ? "form textarea[name^='question']" : `form input[name='${name}']`,
  );
const scheduleButton = () =>
  [...document.querySelectorAll<HTMLButtonElement>("form button[type=submit]")].find((b) =>
    /schedule/i.test(b.textContent ?? ""),
  ) ?? null;

function step(): Step {
  if (/confirmed|scheduled/i.test(location.pathname) || document.querySelector("[data-component='confirmation-page']")) {
    return "scheduled";
  }
  return field("full_name") ? "details" : "calendar";
}

/** "Friday, October 16 - Times available" → "Friday, October 16". */
const dayLabel = (b: HTMLButtonElement) => clean((b.getAttribute("aria-label") ?? "").split(" - ")[0]);

function chosenDay(): string | null {
  const m = location.search.match(/[?&]date=(\d{4}-\d{2}-\d{2})/);
  if (m) {
    const d = new Date(`${m[1]}T12:00:00`);
    return d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  }
  const pressed = document.querySelector<HTMLButtonElement>("button[aria-label*=' - Times available'][aria-pressed='true']");
  return pressed ? dayLabel(pressed) : null;
}

function chosenTime(): string | null {
  const m = location.pathname.match(/\/(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})/);
  if (!m) return null;
  const h = Number(m[2]);
  return `${h % 12 || 12}:${m[3]}${h < 12 ? "am" : "pm"}`;
}

function month(): string {
  const title = [...document.querySelectorAll("[data-testid='title'], [data-container='month'], h2, div")]
    .map((e) => clean(e.textContent))
    .find((t) => /^(January|February|March|April|May|June|July|August|September|October|November|December) \d{4}$/.test(t));
  return title ?? "";
}

function timezone(): string {
  const tz = [...document.querySelectorAll("button")].find((b) => /time\s*\(/i.test(b.innerText) || /Time$/m.test(b.innerText));
  return tz ? clean(tz.innerText.split("\n")[0]) : "";
}

function state() {
  const s = step();
  if (s === "details") {
    const filled = { name: clean(field("full_name")?.value), email: clean(field("email")?.value), notes: clean(field("notes")?.value) };
    return {
      step: s,
      date: chosenDay() ?? "",
      time: chosenTime() ?? "",
      timezone: timezone(),
      filled,
      missing: (["name", "email"] as const).filter((k) => !filled[k]),
    };
  }
  return {
    step: s,
    month: month(),
    days: dayButtons().map(dayLabel),
    date: chosenDay() ?? "",
    times: timeButtons().map((b) => clean(b.getAttribute("data-start-time") ?? b.textContent)),
    timezone: timezone(),
  };
}

// ─── Acting in it ───────────────────────────────────────────────────────

/** Set a value the way typing would, so React's state takes it. */
function setNative(el: HTMLInputElement | HTMLTextAreaElement, value: string): void {
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

/** Whether ``said`` ("October 21", "21", "Tuesday", "Tuesday 21st") names the
 * day labelled ``label`` ("Wednesday, October 21"). */
function sameDay(said: string, label: string): boolean {
  const want = fold(said).replace(/(\d+)(st|nd|rd|th)\b/g, "$1");
  const have = fold(label);
  if (have === want) return true;
  const num = want.match(/\b(\d{1,2})\b/)?.[1];
  const words = want.split(" ").filter((w) => w.length > 2 && !/^\d/.test(w));
  if (num && have.match(/(\d{1,2})$/)?.[1] !== num) return false;
  return words.every((w) => have.includes(w));
}

/** The open day ``said`` names, among the days on the calendar. */
function findDay(said: string): HTMLButtonElement | null {
  const days = dayButtons();
  return days.find((b) => fold(dayLabel(b)) === fold(said)) ?? days.find((b) => sameDay(said, dayLabel(b))) ?? null;
}

/** "3pm", "3:00 pm", "15:00" → Calendly's "3:00pm". */
function normTime(said: string): string {
  const m = fold(said).replace(/\s+/g, "").match(/^(\d{1,2})(?::(\d{2}))?(am|pm)?$/);
  if (!m) return fold(said).replace(/\s+/g, "");
  let h = Number(m[1]);
  const min = m[2] ?? "00";
  let ap = m[3];
  if (!ap) {
    ap = h >= 12 ? "pm" : "am";
    if (h > 12) h -= 12;
  }
  return `${h === 0 ? 12 : h}:${min}${ap}`;
}

async function book(order: BookOrder): Promise<string | null> {
  if (step() === "details" && (order.day || order.time)) {
    const back = document.querySelector<HTMLButtonElement>("button[aria-label*='back' i], button[aria-label*='Go to previous' i]");
    back?.click();
    await waitFor(() => step() === "calendar", 4000);
  }
  if (step() === "calendar") {
    // The day already chosen, with its times showing: on to the time. Once a
    // day is chosen a narrow Calendly swaps the day grid for its times, so
    // asking for the same day again found no day button and never reached
    // the time (dev call 56e87ed1).
    const chosen = chosenDay();
    const already = !!order.day && !!chosen && sameDay(order.day, chosen) && timeButtons().length > 0;
    if (order.day && !already) {
      if (dayButtons().length === 0 && timeButtons().length > 0) {
        // Another day, from the times view: back to the grid first.
        const back = document.querySelector<HTMLButtonElement>(
          "button[aria-label*='back' i], button[aria-label*='Go to previous' i]",
        );
        back?.click();
        await waitFor(() => dayButtons().length > 0, 3000);
      }
      const day = (await waitFor(() => findDay(order.day!), 3000)) ?? null;
      if (!day) return `no open day matches "${order.day}"; open days: ${dayButtons().map(dayLabel).join(", ") || "none this month"}`;
      day.click();
      await waitFor(() => timeButtons().length > 0, 4000);
    }
    if (order.time) {
      const want = normTime(order.time);
      const times = timeButtons();
      const t = times.find((b) => fold(b.getAttribute("data-start-time")).replace(/\s+/g, "") === want);
      if (!t) {
        const open = times.map((b) => clean(b.getAttribute("data-start-time"))).join(", ");
        return `no ${order.time} slot on ${chosenDay() ?? "that day"}; open times: ${open || "choose a day first"}`;
      }
      t.click();
      const next = await waitFor(() =>
        [...document.querySelectorAll<HTMLButtonElement>("button")].find((b) => clean(b.textContent) === "Next" || /^Next /.test(b.getAttribute("aria-label") ?? "")),
      );
      if (!next) return "the Next button did not appear after choosing the time";
      next.click();
      if (!(await waitFor(() => field("full_name")))) return "the details step did not open";
      await sleep(300);
    }
  }
  if (order.fill) await fillDetails(order.fill);
  return null;
}

let pending: Fill = {};

/** Fill the details step, or keep the values for when it opens. */
async function fillDetails(fill: Fill): Promise<void> {
  pending = { ...pending, ...Object.fromEntries(Object.entries(fill).filter(([, v]) => v)) };
  if (step() !== "details") return;
  const map: [keyof Fill, string][] = [
    ["name", "full_name"],
    ["email", "email"],
    ["notes", "notes"],
  ];
  for (const [key, name] of map) {
    const value = pending[key];
    const el = field(name);
    if (value && el && clean(el.value) !== clean(value)) {
      setNative(el, value);
      await sleep(40);
    }
  }
}

// ─── Talking to the page ────────────────────────────────────────────────

function start(): void {
  const parent = parentOrigin();
  if (!parent) return;
  let last = "";
  const report = (force = false) => {
    const s = state();
    const key = JSON.stringify(s);
    if (!force && key === last) return;
    last = key;
    window.parent.postMessage({ voqalizeCalendly: s }, parent);
  };

  window.addEventListener("message", (e: MessageEvent) => {
    if (e.origin !== parent || e.source !== window.parent) return;
    const msg = (e.data as { voqalizeCalendlyCmd?: { id: number; cmd: string; order?: BookOrder } })?.voqalizeCalendlyCmd;
    if (!msg) return;
    const reply = (error: string | null) =>
      window.parent.postMessage({ voqalizeCalendlyDone: { id: msg.id, error, state: state() } }, parent);
    if (msg.cmd === "state") return reply(null);
    if (msg.cmd === "book") {
      void book(msg.order ?? {})
        .catch((error: unknown) => String(error))
        .then((error) => {
          report(true);
          reply(error);
        });
    }
  });

  // A field the visitor typed in, a day they clicked: reported as it settles.
  let timer: ReturnType<typeof setTimeout> | null = null;
  const settle = () => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      if (step() === "details" && Object.keys(pending).length) void fillDetails({});
      report();
    }, 400);
  };
  new MutationObserver(settle).observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener("input", settle, true);

  // Schedule Event is the visitor's. In a demo it is reported, then stopped.
  const onSchedule = (e: Event) => {
    const b = (e.target as Element | null)?.closest?.("button");
    const submit = e.type === "submit" || (b && b === scheduleButton());
    if (!submit) return;
    window.parent.postMessage({ voqalizeCalendlyScheduled: { ...state(), blocked: DEMO_BLOCK_SUBMIT } }, parent);
    if (!DEMO_BLOCK_SUBMIT) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const btn = scheduleButton();
    if (btn && !document.querySelector("[data-voqalize=toast]")) {
      const note = document.createElement("p");
      note.setAttribute("data-voqalize", "toast");
      note.textContent = "Demo: this meeting was not booked in SendPotion's calendar.";
      Object.assign(note.style, { margin: "10px 0 0", color: "#2B1B6B", font: "500 13px/1.4 system-ui, sans-serif" });
      btn.insertAdjacentElement("afterend", note);
      setTimeout(() => note.remove(), 6000);
    }
  };
  window.addEventListener("click", onSchedule, true);
  window.addEventListener("submit", onSchedule, true);

  report(true);
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
else start();

export {};
