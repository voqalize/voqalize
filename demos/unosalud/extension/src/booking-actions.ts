/**
 * The booking's adapter: /agenda-tu-hora/ on www.unosalud.cl, Dentalsoft's
 * jQuery wizard (`form#dentalsoft-form`), always in a tab of its own.
 *
 * One document, one `<fieldset>` per step, shown and hidden in place; `#step`
 * holds the step the server last answered with. The steps:
 *
 *   getPAC    the RUT, the terms box and the captcha: the visitor's alone.
 *             Javier rings `#rut` and waits; he never types it, never ticks
 *             `#conditions`, never touches the captcha, never presses
 *             `#ingresar-rut`.
 *   setPAC    a new patient's details: he fills them as dictated and rings
 *             "Registrarse" (`#registro-paciente`), which the visitor presses.
 *   setEF     an existing patient's contact details (optional): he may fill
 *             them and press "Continuar" (`#actualiza-datos`).
 *   notsetRH  the patient already has an appointment: a dead end.
 *   getMRes   the motivo (`#motivo`, 14–23), then `#selecciona-motivo`.
 *   getSuc    región, comuna and clínica (`#region` → `#comuna` →
 *             `#sucursal`, filled client-side from `#jsonSucursales` on each
 *             change), then `#continue_getSuc`.
 *   getHor    the inline calendar (fengyuanchen's datepicker): a day's press
 *             asks the server for its hours, shown as `#horarios
 *             .option_hora`, or `#alert_sin_horarios`. Pressing an hour moves
 *             on to the review by itself.
 *   getDC     the review (`#data-reserva`): he reads it and rings "Confirmar
 *             cita" (`#confirma-cita`), which the visitor presses.
 *   setRH     booked. A payment link may show (`#container_link_pago`): never
 *             followed.
 *
 * jQuery and the datepicker listen to native events, so a field is set by its
 * value and `input`/`change`, and a press is a click. Every press and fill
 * goes through `guards.ts`. `booking_state` is reported after every change of
 * step, hours or error, whoever made it (the visitor's own presses too).
 */

import type { BookingState } from "./actions.gen";
import { GuardError, press } from "./guards";
import { canonical } from "./catalogue";
import { chileanMobile, clean, highlight, norm, pickOption, quiet, scrollTo, setValue, sleep, typeDigits, visible, waitFor } from "./page";

type Step = "getPAC" | "setPAC" | "setEF" | "notsetRH" | "getMRes" | "getSuc" | "getHor" | "getDC" | "setRH" | "unknown";
const STEPS: readonly Step[] = ["getPAC", "setPAC", "setEF", "notsetRH", "getMRes", "getSuc", "getHor", "getDC", "setRH"];

/** How long a step's server answer may take. */
const SERVER_MS = 20_000;
const DEBOUNCE_MS = 400;
const MAX_SCAN_DAYS = 14;
const MAX_MONTHS_AHEAD = 4;

const byId = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T | null;
const form = () => byId<HTMLFormElement>("dentalsoft-form");
const hidden = (el: Element | null) => !el || el.classList.contains("d-none");

/** When Javier last moved the booking, for the widget to keep clear of it. */
export let lastMove = 0;

// ─── Reading the booking ──────────────────────────────────────────────────

/** The step on screen: the fieldset showing, else `#step`. */
export function currentStep(): Step {
  const f = form();
  if (!f) return "unknown";
  const showing = [...f.querySelectorAll<HTMLFieldSetElement>(":scope > fieldset")].filter((fs) => !hidden(fs));
  if (showing.length === 1 && (STEPS as readonly string[]).includes(showing[0].id)) return showing[0].id as Step;
  const v = byId<HTMLInputElement>("step")?.value ?? "";
  return (STEPS as readonly string[]).includes(v) ? (v as Step) : "unknown";
}

const selected = (id: string) => {
  const s = byId<HTMLSelectElement>(id);
  const o = s?.selectedOptions[0];
  return o && o.value && o.value !== "0" ? clean(o.text) : "";
};

const pad = (n: number | string) => String(n).padStart(2, "0");
/** "27-10-2026" → "2026-10-27". */
const isoOfDmy = (s: string) => {
  const m = s.trim().match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
  return m ? `${m[3]}-${pad(m[2])}-${pad(m[1])}` : "";
};
/** "2026-10-27" → "27-10-2026". */
const dmyOfIso = (s: string) => {
  const m = s.trim().match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  return m ? `${pad(m[3])}-${pad(m[2])}-${m[1]}` : "";
};

const slotEls = () => [...document.querySelectorAll<HTMLElement>("#horarios .option_hora")];
const slots = () => slotEls().map((el) => hhmm(el.textContent ?? "")).filter(Boolean);
/** The day's "no hours" notice is up (by its class: on a phone its column
 *  may be folded away while it says so). */
const noSlots = () => Boolean(byId("alert_sin_horarios")) && !hidden(byId("alert_sin_horarios"));
const hoursLoading = () => clean(byId("loading-horas")?.textContent).length > 0;

function hhmm(t: string): string {
  const m = clean(t).match(/(\d{1,2})[:.h](\d{2})/);
  return m ? `${pad(m[1])}:${m[2]}` : "";
}

/** The review's rows, by the brain's names. */
function summary(): BookingState["summary"] {
  const rows = [...document.querySelectorAll<HTMLTableRowElement>("#data-reserva tr")];
  if (!rows.length) return null;
  const out: Record<string, string> = { paciente: "", fecha: "", hora: "", odontologo: "", direccion: "", referencia: "" };
  const keys: [RegExp, string][] = [
    [/^paciente/, "paciente"], [/^fecha/, "fecha"], [/^hora/, "hora"], [/^odontolog/, "odontologo"],
    [/^direccion/, "direccion"], [/^referencia/, "referencia"],
  ];
  for (const r of rows) {
    const label = norm(r.querySelector("th")?.textContent);
    const value = clean(r.querySelector("td")?.textContent);
    const key = keys.find(([re]) => re.test(label))?.[1];
    if (key) out[key] = value;
  }
  return out as unknown as BookingState["summary"];
}

/** The days a scan read, kept for the state until the clinic changes. */
let scanned: { date: string; times: string[] }[] = [];
let scannedFor = "";

export function bookingState(): BookingState {
  const step = currentStep();
  const err = byId("dentalsoft-error");
  const sucursal = selected("sucursal");
  if (scannedFor && scannedFor !== sucursal) scanned = [];
  return {
    step,
    rut_entered: Boolean(byId<HTMLInputElement>("rut")?.value.trim()),
    patient_first_name: step === "setEF" ? clean(byId("setEF")?.querySelector(".user_name")?.textContent) : "",
    motivo: Number(byId<HTMLSelectElement>("motivo")?.value) || 0,
    region: selected("region"),
    comuna: selected("comuna"),
    sucursal,
    date: isoOfDmy(byId<HTMLInputElement>("fecha")?.value ?? ""),
    slots: step === "getHor" ? slots() : [],
    days: scanned,
    no_slots: step === "getHor" && noSlots(),
    summary: step === "getDC" || step === "setRH" ? summary() : null,
    error: err && !hidden(err) ? clean(err.textContent) : "",
    booked: step === "setRH",
  } as BookingState;
}

export function bookingContext() {
  return {
    url: location.href,
    path: canonical(location.pathname),
    title: document.title,
    kind: "booking" as const,
    anchors: [] as string[],
    faqs: [] as string[],
    form: "booking" as const,
    clinic: null,
  };
}

let report: (() => void) | null = null;

/** `booking_state` on load and after every change, whoever made it. */
export function watchBooking(emit: (event: string, payload: unknown) => void): () => void {
  let last = "";
  let timer: ReturnType<typeof setTimeout> | null = null;
  const send = () => {
    timer = null;
    const state = bookingState();
    const key = JSON.stringify(state);
    if (key === last) return;
    last = key;
    emit("booking_state", state);
  };
  let lastStep = "";
  const soon = () => {
    if (timer) clearTimeout(timer);
    // A new step is reported at once, so none is lost to the next; the rest
    // (hours arriving, lists filling) once the page settles.
    const step = currentStep();
    if (step !== lastStep) {
      lastStep = step;
      return send();
    }
    timer = setTimeout(send, DEBOUNCE_MS);
  };
  const obs = new MutationObserver(soon);
  const f = form();
  if (f) {
    for (const fs of f.querySelectorAll(":scope > fieldset")) obs.observe(fs, { attributes: true, attributeFilter: ["class"] });
    for (const id of ["horarios", "alert_sin_horarios", "data-reserva", "loading-horas", "region", "comuna", "sucursal"]) {
      const el = byId(id);
      if (el) obs.observe(el, { childList: true, subtree: true, attributes: true, characterData: true });
    }
    f.addEventListener("change", soon, true);
  }
  const err = byId("dentalsoft-error");
  if (err) obs.observe(err, { attributes: true, childList: true, subtree: true, characterData: true });
  report = soon;
  lastStep = currentStep();
  send();
  return () => {
    obs.disconnect();
    f?.removeEventListener("change", soon, true);
    if (timer) clearTimeout(timer);
    if (report === soon) report = null;
  };
}

// ─── Moving it ────────────────────────────────────────────────────────────

const errorText = () => {
  const err = byId("dentalsoft-error");
  return err && !hidden(err) ? clean(err.textContent) : "";
};

/** Wait until the step is no longer `from` (the server answered), or the
 *  booking shows an error. The new step, or a failure. */
async function leaveStep(from: Step, ms = SERVER_MS): Promise<Step> {
  const gone = await waitFor(() => currentStep() !== from || errorText(), ms);
  const err = errorText();
  if (err) throw new Error(`the booking answered: ${err}`);
  if (!gone) throw new Error(`the booking stayed on ${from}: the server did not answer, or a field was refused`);
  await sleep(200);
  return currentStep();
}

function needStep(want: Step | Step[], what: string): void {
  const now = currentStep();
  const ok = Array.isArray(want) ? want.includes(now) : now === want;
  if (!ok) throw new Error(`the booking is on ${now}, not ${Array.isArray(want) ? want.join("/") : want}: ${what} cannot be done now`);
}

function ringStep(step: Step): void {
  const ring: Record<Step, string[]> = {
    getPAC: ["rut"],
    setPAC: ["registro-paciente"],
    setEF: ["actualiza-datos"],
    notsetRH: ["notsetRH"],
    getMRes: ["motivo"],
    getSuc: ["region", "comuna", "sucursal"],
    getHor: ["datepicker-fecha", "horarios"],
    getDC: ["confirma-cita"],
    setRH: ["setRH"],
    unknown: ["dentalsoft-form"],
  };
  const els = ring[step].map((id) => byId(id)).filter((el): el is HTMLElement => visible(el));
  if (els.length) highlight(els);
}

/** What the brain hears once a move is done: the step, and what it shows. */
function describe(): string {
  const s = bookingState();
  const parts = [`the booking is on ${s.step}`];
  if (s.motivo) parts.push(`motivo ${s.motivo}`);
  if (s.sucursal) parts.push(`clinic ${s.sucursal} (${s.comuna}, ${s.region})`);
  if (s.date) parts.push(`day ${s.date}`);
  if (s.step === "getHor") parts.push(s.no_slots ? "no hours that day" : s.slots?.length ? `hours: ${s.slots.join(", ")}` : "no day picked yet");
  if (s.summary) parts.push(`review: ${Object.entries(s.summary).filter(([, v]) => v).map(([k, v]) => `${k} ${v}`).join("; ")}`);
  if (s.step === "getDC") parts.push("«Confirmar cita» is ringed for the visitor to press");
  if (s.step === "getPAC") parts.push("the visitor types the RUT, ticks the terms, solves «No soy un robot» and presses Continuar");
  if (s.error) parts.push(`error: ${s.error}`);
  return parts.join("; ");
}

// open_booking ───────────────────────────────────────────────────────────

async function openBooking({ promo }: { promo?: string | null }): Promise<string | null> {
  if (!(await waitFor(form, 10_000))) throw new Error("the booking page did not load");
  const want = (promo ?? "").trim();
  const have = new URLSearchParams(location.search).get("promo") ?? "";
  // The promotion's code rides in the address; the page is loaded again with
  // it while the visitor has not started (nothing typed on the first step).
  if (want && want !== have && currentStep() === "getPAC" && !byId<HTMLInputElement>("rut")?.value) {
    const url = new URL(location.href);
    url.searchParams.set("promo", want);
    location.assign(url.pathname + url.search);
    return null;
  }
  lastMove = Date.now();
  const step = currentStep();
  const target = step === "getPAC" ? byId("rut") : byId(step);
  if (target) await scrollTo(target, "center");
  if (step === "getPAC") byId("rut")?.focus({ preventScroll: true });
  ringStep(step);
  report?.();
  return describe();
}

// fill_booking_patient ───────────────────────────────────────────────────

interface Patient {
  nombre?: string | null;
  paterno?: string | null;
  materno?: string | null;
  birth_date?: string | null;
  email?: string | null;
  phone?: string | null;
  confirm_existing?: boolean | null;
}

/** The booking's phones take a Chilean mobile, typed into the mask. */
function phoneDigits(said: string): string {
  const d = chileanMobile(said);
  if (!/^9\d{8}$/.test(d)) {
    throw new Error(`phone "${said}" refused: the booking takes a Chilean mobile (9 digits starting with 9); nothing was typed: ask for it again, never change the digits`);
  }
  return d;
}

function typePhone(el: HTMLInputElement, digits: string): void {
  // The mask's own prefix (+56) is typed too, as a visitor's keys would reach
  // it: a mask that has not inserted it yet takes it as typed.
  typeDigits(el, digits);
  if (el.value.replace(/\D/g, "") !== `56${digits}`) typeDigits(el, `56${digits}`);
}

async function fillPatient(p: Patient): Promise<string> {
  needStep(["setPAC", "setEF"], "the patient's details");
  lastMove = Date.now();
  const step = currentStep();
  const done: string[] = [];
  const problems: string[] = [];
  const text = (id: string, value: string | null | undefined, name: string) => {
    const el = byId<HTMLInputElement>(id);
    if (!value?.trim() || !el) return;
    setValue(el, value.trim());
    done.push(name);
  };
  if (step === "setPAC") {
    const names: [string, string | null | undefined][] = [["nombre", p.nombre], ["paterno", p.paterno], ["materno", p.materno]];
    for (const [id, v] of names) {
      if (v && (v.trim().length < 3 || /\d/.test(v))) problems.push(`${id} "${v}" refused: at least 3 letters, no digits`);
      else text(id, v, id);
    }
    if (p.birth_date) {
      const dmy = dmyOfIso(p.birth_date);
      if (!dmy) problems.push(`birth_date "${p.birth_date}" refused: give it as YYYY-MM-DD`);
      else text("fecnac", dmy, "birth_date");
    }
    text("new_emailpac", p.email, "email");
    if (p.phone) {
      try {
        const el = byId<HTMLInputElement>("new_fono");
        if (el) {
          typePhone(el, phoneDigits(p.phone));
          done.push("phone");
        }
      } catch (e) {
        problems.push(e instanceof Error ? e.message : String(e));
      }
    }
    await sleep(150);
    const missing = ["nombre", "paterno", "materno", "fecnac", "new_emailpac", "new_fono"].filter((id) => {
      const v = byId<HTMLInputElement>(id)?.value.trim() ?? "";
      if (id === "new_fono") return v.replace(/\D/g, "").length < 11;
      return v.length < (id === "fecnac" ? 10 : id === "new_emailpac" ? 5 : 3);
    });
    const button = byId("registro-paciente");
    if (!missing.length && button) {
      await scrollTo(button, "center");
      highlight(button);
    } else {
      const els = missing.map((id) => byId(id)).filter((el): el is HTMLElement => Boolean(el));
      if (els[0]) await scrollTo(els[0], "center");
      if (els.length) highlight(els);
    }
    report?.();
    if (problems.length && !done.length) throw new Error(problems.join("; "));
    return [
      done.length ? `filled ${done.join(", ")}` : "nothing filled",
      ...problems,
      missing.length ? `still missing: ${missing.join(", ")}` : "the details are complete; «Registrarse» is ringed for the visitor to press",
    ].join("; ");
  }
  // setEF: an existing patient; the contact details are optional.
  text("emailpac", p.email, "email");
  if (p.phone) {
    try {
      const el = byId<HTMLInputElement>("fono");
      if (el) {
        typePhone(el, phoneDigits(p.phone));
        done.push("phone");
      }
    } catch (e) {
      problems.push(e instanceof Error ? e.message : String(e));
    }
  }
  if (problems.length) throw new Error(problems.join("; "));
  if (p.confirm_existing) {
    press(byId("actualiza-datos")!);
    await leaveStep("setEF");
    ringStep(currentStep());
    report?.();
    return `${done.length ? `filled ${done.join(", ")}; ` : ""}pressed Continuar; ${describe()}`;
  }
  ringStep("setEF");
  report?.();
  return `${done.length ? `filled ${done.join(", ")}` : "nothing filled"}; Continuar is ringed (say confirm_existing to press it)`;
}

// booking_pick ───────────────────────────────────────────────────────────

interface Pick {
  motivo?: number | null;
  region?: string | null;
  comuna?: string | null;
  sucursal?: string | null;
  date?: string | null;
  time?: string | null;
}

interface Place {
  region: string;
  comuna: string;
  sucursal: string;
}

/** The clinic tree embedded in the page (`#jsonSucursales`). */
function tree(): Record<string, { id: string; descripcion: string; getcomunas?: { id: string; descripcion: string; sucursales: { id: string; descripcion: string }[] }[] }> {
  try {
    return JSON.parse(byId("jsonSucursales")?.textContent ?? "{}");
  } catch {
    return {};
  }
}

/** Where a clinic is, by its id or its name, from the embedded tree. */
function placeOf(said: string): Place | null {
  const want = norm(said);
  const squash = (s: string) => norm(s).replace(/[^a-z0-9]/g, "");
  let fuzzy: Place | null = null;
  for (const r of Object.values(tree())) {
    for (const c of r.getcomunas ?? []) {
      for (const s of c.sucursales ?? []) {
        const place = { region: r.id, comuna: c.id, sucursal: s.id };
        if (s.id === said.trim() || norm(s.descripcion) === want) return place;
        if (!fuzzy && (squash(s.descripcion).includes(squash(said)) || norm(s.descripcion).startsWith(want))) fuzzy = place;
      }
    }
  }
  return fuzzy;
}

/** The option the brain named: its value, else its words. */
function optionFor(select: HTMLSelectElement, said: string): HTMLOptionElement | null {
  const options = [...select.options].filter((o) => o.value && !o.disabled);
  return options.find((o) => o.value === said.trim()) ?? pickOption(select, said);
}

async function chooseIn(id: string, said: string, what: string): Promise<void> {
  const select = byId<HTMLSelectElement>(id);
  if (!select) throw new Error(`the booking has no ${what} list`);
  const ready = await waitFor(() => !select.disabled && [...select.options].some((o) => o.value), 8000);
  if (!ready) throw new Error(`the ${what} list did not load`);
  const option = optionFor(select, said);
  if (!option) {
    const known = [...select.options].filter((o) => o.value).map((o) => clean(o.text)).slice(0, 40).join(" | ");
    throw new Error(`no ${what} "${said}"; the list has: ${known}`);
  }
  if (select.value !== option.value) setValue(select, option.value);
  await sleep(250);
}

async function pickMotivo(motivo: number): Promise<void> {
  needStep("getMRes", "the motivo");
  if (!(motivo >= 14 && motivo <= 23)) throw new Error(`motivo ${motivo} refused: it is one of 14–23`);
  await chooseIn("motivo", String(motivo), "motivo");
  press(byId("selecciona-motivo")!);
  await leaveStep("getMRes");
}

async function pickClinic(p: Pick): Promise<void> {
  needStep("getSuc", "the clinic");
  let { region, comuna } = p;
  const sucursal = p.sucursal?.trim() ?? "";
  if (sucursal && (!region || !comuna)) {
    const place = placeOf(sucursal);
    if (!place) throw new Error(`no clinic "${sucursal}" in the booking's list`);
    region ||= place.region;
    comuna ||= place.comuna;
  }
  if (region) await chooseIn("region", region, "región");
  if (comuna) await chooseIn("comuna", comuna, "comuna");
  if (sucursal) {
    const place = placeOf(sucursal);
    await chooseIn("sucursal", place?.sucursal ?? sucursal, "clínica");
    const go = byId<HTMLButtonElement>("continue_getSuc");
    await waitFor(() => go && !go.disabled, 3000);
    press(go!);
    await leaveStep("getSuc");
  }
}

// The calendar ─────────────────────────────────────────────────────────

const MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const MONTHS_EN = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"];

const daysPanel = () => document.querySelector<HTMLElement>('#datepicker-fecha .datepicker-panel[data-view="days picker"]');

/** The month the calendar shows, as "2026-10" ("2026 - Octubre"). */
function monthShown(): string {
  const t = norm(daysPanel()?.querySelector('li[data-view="month current"]')?.textContent);
  const year = t.match(/\d{4}/)?.[0];
  const word = t.replace(/[^a-z]/g, " ").trim().split(/\s+/).find((w) => MONTHS.includes(w) || MONTHS_EN.includes(w)) ?? "";
  const m = Math.max(MONTHS.indexOf(word), MONTHS_EN.indexOf(word)) + 1;
  return year && m ? `${year}-${pad(m)}` : "";
}

/** The current month's day cells, with their dates and whether they open. */
function dayCells(): { iso: string; el: HTMLElement; open: boolean }[] {
  const month = monthShown();
  const panel = daysPanel();
  if (!month || !panel) return [];
  return [...panel.querySelectorAll<HTMLElement>('ul[data-view="days"] li')]
    .filter((li) => !/\b(prev|next)\b/.test(li.dataset.view ?? "") && !li.classList.contains("muted"))
    .map((li) => ({
      iso: `${month}-${pad(clean(li.textContent))}`,
      el: li,
      open: !li.classList.contains("disabled") && !/disabled/.test(li.dataset.view ?? "") && li.style.pointerEvents !== "none",
    }));
}

/** The calendar is showing (after a day with hours it gives way to them). */
async function calendarUp(): Promise<void> {
  // On a phone the calendar folds away (`ocultar`) once a day's hours show;
  // its "Volver" brings it back.
  const box = byId("container_select_fecha");
  if (box && box.classList.contains("ocultar") && !visible(daysPanel())) {
    const back = byId("volver_hora");
    if (back) press(back);
    await waitFor(() => !box.classList.contains("ocultar"), 2000);
    await sleep(150);
  }
}

/** Turn the calendar to `month` ("2026-11"). */
async function toMonth(month: string): Promise<void> {
  for (let i = 0; i < 24 && monthShown() !== month; i++) {
    const now = monthShown();
    const dir = now < month ? "next" : "prev";
    const arrow = daysPanel()?.querySelector<HTMLElement>(`li[data-view="month ${dir}"]`);
    if (!arrow || arrow.classList.contains("disabled")) break;
    press(arrow);
    await waitFor(() => monthShown() !== now, 1000);
  }
  if (monthShown() !== month) throw new Error(`the calendar cannot show ${month}`);
}

/** Press the day `iso` and wait for its hours (or that it has none). */
async function chooseDay(iso: string): Promise<string[]> {
  needStep("getHor", "the day");
  await calendarUp();
  await toMonth(iso.slice(0, 7));
  const cell = dayCells().find((c) => c.iso === iso);
  if (!cell) throw new Error(`${iso} is not in the calendar`);
  if (!cell.open) {
    const open = dayCells().filter((c) => c.open).map((c) => c.iso.slice(8)).join(", ");
    throw new Error(`${iso} cannot be booked${open ? `; open days this month: ${open}` : ""}`);
  }
  press(cell.el);
  lastMove = Date.now();
  await waitFor(() => hoursLoading() || slotEls().length || noSlots() || errorText(), 3000);
  const answered = await waitFor(() => !hoursLoading() && (slotEls().length || noSlots() || errorText()), SERVER_MS);
  const err = errorText();
  if (err) throw new Error(`the booking answered: ${err}`);
  if (!answered) throw new Error(`the hours for ${iso} did not come back`);
  const q = byId("horarios");
  if (q) await quiet(q, 250, 1500);
  return noSlots() ? [] : slots();
}

async function chooseTime(time: string): Promise<void> {
  needStep("getHor", "the hour");
  const want = hhmm(time);
  const el = slotEls().find((s) => hhmm(s.textContent ?? "") === want);
  if (!el) {
    throw new Error(`no hour ${time} on ${bookingState().date || "this day"}; the hours are: ${slots().join(", ") || "none"}`);
  }
  await scrollTo(el, "center");
  press(el);
  lastMove = Date.now();
  await leaveStep("getHor");
}

async function bookingPick(p: Pick): Promise<string> {
  const motivo = Number(p.motivo) || 0;
  const date = (p.date ?? "").trim();
  const time = (p.time ?? "").trim();
  if (!motivo && !p.region && !p.comuna && !p.sucursal && !date && !time) throw new Error("say which step to take");
  lastMove = Date.now();
  const steps: string[] = [];
  if (motivo) {
    await pickMotivo(motivo);
    steps.push(`motivo ${motivo}`);
    report?.();
  }
  if (p.region || p.comuna || p.sucursal) {
    await pickClinic(p);
    steps.push("clinic");
    report?.();
  }
  if (date) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new Error(`date "${date}" refused: give it as YYYY-MM-DD`);
    await chooseDay(date);
    steps.push(`day ${date}`);
    report?.();
  }
  if (time) {
    await chooseTime(time);
    steps.push(`hour ${time}`);
  }
  const step = currentStep();
  const ring = step === "getDC" ? byId("confirma-cita") : null;
  if (ring) {
    await scrollTo(ring, "center");
    highlight(ring);
  } else ringStep(step);
  report?.();
  return `took ${steps.join(", ")}; ${describe()}`;
}

// booking_scan ───────────────────────────────────────────────────────────

const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};
const addMonth = (month: string) => {
  const [y, m] = month.split("-").map(Number);
  return m === 12 ? `${y + 1}-01` : `${y}-${pad(m + 1)}`;
};

/** Press successive open days from `from_date`, reading each one's hours, and
 *  leave the first day with hours picked. Its hours stay on screen. */
async function bookingScan({ from_date, days }: { from_date?: string | null; days?: number | null }): Promise<string> {
  needStep("getHor", "a scan of the days");
  lastMove = Date.now();
  const want = Math.min(Math.max(Number(days) || 5, 1), MAX_SCAN_DAYS);
  const from = /^\d{4}-\d{2}-\d{2}$/.test(from_date ?? "") ? from_date! : todayIso();
  const found: { date: string; times: string[] }[] = [];
  let tried = 0;
  await calendarUp();
  let month = from.slice(0, 7);
  for (let m = 0; m <= MAX_MONTHS_AHEAD && tried < want; m++, month = addMonth(month)) {
    await calendarUp();
    try {
      await toMonth(month);
    } catch {
      break;
    }
    const open = dayCells().filter((c) => c.open && c.iso >= from).map((c) => c.iso);
    for (const iso of open) {
      if (tried >= want) break;
      tried++;
      const times = await chooseDay(iso);
      found.push({ date: iso, times });
      scanned = [...found];
      scannedFor = selected("sucursal");
      report?.();
    }
  }
  const first = found.find((d) => d.times.length);
  if (first && bookingState().date !== first.date) await chooseDay(first.date);
  scanned = found;
  scannedFor = selected("sucursal");
  ringStep("getHor");
  report?.();
  if (!found.length) throw new Error(`no open day from ${from} in the calendar`);
  const said = found.map((d) => `${d.date}: ${d.times.length ? d.times.join(", ") : "none"}`).join("; ");
  return `read ${found.length} day(s): ${said}${first ? `; ${first.date} is picked, its hours on screen` : "; no hours on any of them"}`;
}

// ─── One move at a time ───────────────────────────────────────────────────

let running: Promise<unknown> = Promise.resolve();

function oneAtATime<P, R>(move: (payload: P) => Promise<R>): (payload: P) => Promise<R> {
  return (payload: P) => {
    const next = running.then(() => move(payload));
    running = next.catch(() => {});
    return next.catch((error: unknown) => {
      report?.();
      throw error instanceof GuardError ? error : error;
    });
  };
}

export function bookingCommands(): Record<string, (payload: never) => Promise<string | null | void>> {
  return {
    open_booking: oneAtATime(openBooking) as (payload: never) => Promise<string | null>,
    fill_booking_patient: oneAtATime(fillPatient) as (payload: never) => Promise<string>,
    booking_pick: oneAtATime(bookingPick) as (payload: never) => Promise<string>,
    booking_scan: oneAtATime(bookingScan) as (payload: never) => Promise<string>,
  };
}
