/**
 * The guest's stay as the app shows it, and the ONE controller that changes it.
 *
 * Every change (a tap, a typed field, or one of the concierge's Stage moves)
 * goes through a function here, and each reports itself as the `stay` slice's
 * event (`cart.changed`, `spa.booked`, …) so the brain hears what changed, by
 * id. Whether the guest or the concierge made it is decided where the event is
 * sent (`stage/host.tsx`), from Stage's own window around a running move.
 *
 * The final step of anything that costs money or approves someone (Place
 * order, Book, Request, Approve, Decline, Complete check-in, Check out) is a
 * function only the guest's own button calls; no performer calls it.
 *
 * Kept in localStorage (wrapped in try/catch), so a refresh or a later call
 * starts from it; "Reset demo" goes back to the scenario's seed.
 */
import { create } from "zustand";
import {
  BAR,
  CHECKIN,
  DATA,
  type FolioLine,
  GUEST,
  LATE,
  type Outlet,
  REQUESTS,
  type ScenarioId,
  VISITORS,
  type Visitor,
  getActivity,
  getItem,
  getMeetingRoom,
  getTherapist,
  getTreatment,
} from "../data";
import { clock, day, money } from "../lib/format";
import {
  type Line,
  activityTotal,
  assignRoom,
  blockSpan,
  choiceLabels,
  clockOf,
  earlyOffered,
  meetingQuote,
  orderTotals,
  roomFree,
  spaTotal,
} from "../lib/rules";

// ─── Shapes ──────────────────────────────────────────────────────────────────

export type Page = "home" | "dining" | "bar" | "spa" | "activities" | "meetings" | "requests" | "visitors" | "stay" | "checkin" | "checkout" | "info";
export type CheckinStep = "reservation" | "id" | "room" | "early" | "review";
export const CHECKIN_STEPS: CheckinStep[] = ["reservation", "id", "room", "early", "review"];
export type RequestKind = "housekeeping" | "maintenance" | "wakeup" | "valet" | "transport" | "lost_found";

export interface Checkin {
  step: CheckinStep;
  confirmed: boolean;
  idVerified: boolean;
  arrival: string | null;
  floor: string | null;
  bed: string | null;
  quiet: boolean | null;
  early: boolean | null;
}

export type Sheet =
  | { kind: "item"; outlet: Outlet; item_id: string; qty: number; choices: string[]; note: string; edit: number | null }
  | { kind: "cart"; outlet: Outlet }
  | { kind: "spa"; treatment_id: string; date: string; pref: string; time: string | null; therapist_id: string | null }
  | { kind: "activity"; activity_id: string; date: string; time: string | null; guests: number }
  | {
      kind: "meeting";
      room_id: string;
      date: string;
      block: string;
      start: string | null;
      hours: number | null;
      headcount: number;
      layout: string;
      catering: string[];
      av: string[];
    }
  | { kind: "visitor"; visitor_id: string; meet: "room" | "lobby" | null }
  | { kind: "expect"; name: string; from: string; to: string; meet: "room" | "lobby" | null; note: string }
  | {
      kind: "request";
      request: RequestKind;
      items: string[];
      issue: string | null;
      option: string | null;
      date: string | null;
      time: string | null;
      details: string;
    }
  | { kind: "dispute"; line_id: string; reason: string };
export type SheetKind = Sheet["kind"];

export interface Order {
  id: string;
  outlet: Outlet;
  lines: Line[];
  total: number;
  eta: string;
  deliver: string;
}
export interface Booking {
  id: string;
  kind: "spa" | "activity" | "meeting";
  label: string;
  when: string;
  total: number;
}
export interface SentRequest {
  id: string;
  kind: RequestKind;
  label: string;
  eta: string;
}
export interface Expected {
  name: string;
  from: string;
  to: string;
  meet: "room" | "lobby" | null;
  note: string;
}
export interface Toast {
  title: string;
  body: string;
}

export interface State {
  scenario: ScenarioId;
  checkin: Checkin;
  checkedIn: boolean;
  room: string | null;
  checkedOut: boolean;
  charges: FolioLine[];
  disputes: Record<string, string>;
  checkoutPart: "folio" | "late" | "express";
  latePick: string | null;
  lateRequested: string | null;
  outletTab: Outlet;
  section: Record<Outlet, string>;
  carts: Record<Outlet, Line[]>;
  tip: Record<Outlet, number | null>;
  deliverTo: "room" | "cabana" | null;
  cabana: string | null;
  orders: Order[];
  spaCategory: string | null;
  bookings: Booking[];
  mapPin: string | null;
  meetingFilter: { headcount: number | null; layout: string | null; date: string };
  visitors: Visitor[];
  expected: Expected[];
  requests: SentRequest[];
  infoOpen: string | null;
  sheet: Sheet | null;
  toast: Toast | null;
}

// ─── Seed and storage ────────────────────────────────────────────────────────

const KEY = "belmonte-guest-v1";

const freshCheckin = (): Checkin => ({ step: "reservation", confirmed: false, idVerified: false, arrival: null, floor: null, bed: null, quiet: null, early: null });

export function seed(scenario: ScenarioId): State {
  const s = DATA.scenarios[scenario];
  return {
    scenario,
    checkin: freshCheckin(),
    checkedIn: s.checked_in,
    room: s.room,
    checkedOut: false,
    charges: [],
    disputes: {},
    checkoutPart: "folio",
    latePick: null,
    lateRequested: null,
    outletTab: "dining",
    section: { dining: "", bar: BAR.sections[0].id },
    carts: { dining: [], bar: [] },
    tip: { dining: null, bar: null },
    deliverTo: null,
    cabana: null,
    orders: [],
    spaCategory: null,
    bookings: [],
    mapPin: null,
    meetingFilter: { headcount: null, layout: null, date: s.today },
    visitors: VISITORS.pending.map((v) => ({ ...v })),
    expected: [],
    requests: [],
    infoOpen: null,
    sheet: null,
    toast: null,
  };
}

function load(): State {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "null") as Partial<State> | null;
    if (raw && (raw.scenario === "arrival" || raw.scenario === "departure")) return { ...seed(raw.scenario), ...raw, sheet: null, toast: null };
  } catch {
    /* storage unavailable or stale */
  }
  return seed("arrival");
}

export const useStay = create<State>(() => load());

useStay.subscribe((s) => {
  try {
    const { sheet: _s, toast: _t, ...keep } = s;
    localStorage.setItem(KEY, JSON.stringify(keep));
  } catch {
    /* storage unavailable: the stay lasts this page only */
  }
});

const get = () => useStay.getState();
const set = (p: Partial<State>) => useStay.setState(p);

// ─── Reporting (stage/host.tsx sends each as the `stay` slice's event) ───────

export type Report = [id: string, data: Record<string, unknown>];
type Reporter = (r: Report) => void;
let reporter: Reporter | null = null;
export const setReporter = (r: Reporter | null) => {
  reporter = r;
};
const report = (id: string, data: Record<string, unknown>) => reporter?.([id, data]);

let seq = 0;
const newId = (p: string) => `${p}-${Date.now().toString(36)}${(seq++).toString(36)}`;
const toast = (title: string, body: string) => set({ toast: { title, body } });
export const clearToast = () => set({ toast: null });

// ─── Derived ─────────────────────────────────────────────────────────────────

export const stayClock = () => clockOf(get().scenario);
export const guestName = () => GUEST.first_name;

/** Every folio line: the scenario's posted lines, then what was charged in the app. */
export const folio = (s: State = get()): FolioLine[] => [...DATA.scenarios[s.scenario].folio, ...s.charges];
export const balance = (s: State = get()) =>
  folio(s)
    .filter((l) => !(l.id in s.disputes))
    .reduce((a, l) => a + l.amount, 0);

/** The room the guest's current preferences get. */
export const roomFor = (c: Checkin = get().checkin) => assignRoom(c.floor, c.bed, c.quiet);

/** How far check-in has got: the furthest step it may open. */
export function reachable(c: Checkin = get().checkin): CheckinStep[] {
  const out: CheckinStep[] = ["reservation"];
  if (!c.confirmed) return out;
  out.push("id");
  if (!c.idVerified) return out;
  out.push("room");
  if (!c.arrival) return out;
  if (earlyOffered(c.arrival, stayClock().now)) {
    out.push("early");
    if (c.early === null) return out;
  }
  out.push("review");
  return out;
}

const charge = (category: string, label: string, amount: number, detail: string) => {
  const line: FolioLine = { id: newId(category), date: stayClock().today, category, label, amount, detail };
  set({ charges: [...get().charges, line] });
  return line;
};

// ─── App and demo ────────────────────────────────────────────────────────────

export function pageViewed(page: Page) {
  report("stay.page", { page });
}

export function setScenario(scenario: ScenarioId) {
  useStay.setState(seed(scenario), true);
  report("stay.scenario", { scenario, label: DATA.scenarios[scenario].label });
}
export const resetDemo = () => setScenario(get().scenario);

export function closeSheet() {
  const s = get().sheet;
  if (!s) return;
  set({ sheet: null });
  report("sheet.closed", { kind: s.kind });
}
export const sheetOf = <K extends SheetKind>(kind: K): Extract<Sheet, { kind: K }> | null => {
  const s = get().sheet;
  return s && s.kind === kind ? (s as Extract<Sheet, { kind: K }>) : null;
};
const patchSheet = <K extends SheetKind>(kind: K, p: Partial<Extract<Sheet, { kind: K }>>) => {
  const s = sheetOf(kind);
  if (s) set({ sheet: { ...s, ...p } as Sheet });
};

export function openInfo(id: string | null) {
  set({ infoOpen: id });
}

// ─── Check-in ────────────────────────────────────────────────────────────────

export function setCheckinStep(step: CheckinStep) {
  if (!reachable().includes(step)) return false;
  set({ checkin: { ...get().checkin, step } });
  report("checkin.step", { step });
  return true;
}
const advance = () => {
  const r = reachable();
  const step = r[r.length - 1];
  set({ checkin: { ...get().checkin, step } });
  report("checkin.step", { step });
};
export function confirmReservation() {
  set({ checkin: { ...get().checkin, confirmed: true } });
  report("checkin.confirmed", { label: GUEST.reservation });
  advance();
}
/** The guest's own tap on "Scan ID" (the concierge never handles an ID). */
export function verifyId() {
  set({ checkin: { ...get().checkin, idVerified: true } });
  report("checkin.id_verified", {});
  advance();
}
export function setPref(field: "arrival" | "floor" | "bed" | "quiet", value: string | boolean | null) {
  const c = { ...get().checkin, [field]: value } as Checkin;
  if (field === "arrival" && !earlyOffered(c.arrival, stayClock().now)) c.early = null;
  set({ checkin: c });
  const shown =
    field === "arrival"
      ? (CHECKIN.arrival_times.find((a) => a.id === value)?.label ?? String(value))
      : field === "floor"
        ? (CHECKIN.floors.find((f) => f.id === value)?.label ?? String(value))
        : field === "bed"
          ? (CHECKIN.beds.find((b) => b.id === value)?.label ?? String(value))
          : value
            ? "a quiet room"
            : "no quiet room preference";
  report("checkin.prefs", { field, value: String(value), label: `${field}: ${shown}` });
}
export function setEarly(want: boolean) {
  set({ checkin: { ...get().checkin, early: want } });
  report("checkin.early", { value: want ? "yes" : "no" });
}
/** Leave the room step (its Continue button). */
export const checkinNext = () => advance();
/** The guest's own "Complete check-in". */
export function completeCheckin() {
  const c = get().checkin;
  if (!reachable(c).includes("review")) return;
  const room = roomFor(c);
  if (c.early) charge("fee", "Early check-in", CHECKIN.early.fee, `Room ready on arrival, before ${clock(CHECKIN.early.before)}.`);
  set({ checkedIn: true, room: room.room });
  report("checkin.done", { room: room.room, label: `room ${room.room}` });
  toast("You're checked in", `Room ${room.room}, floor ${room.floor}. Your digital key is ready.`);
}

// ─── Check-out ───────────────────────────────────────────────────────────────

export const setCheckoutPart = (part: State["checkoutPart"]) => set({ checkoutPart: part });

export function openDispute(lineId: string, reason = "") {
  set({ sheet: { kind: "dispute", line_id: lineId, reason } });
}
export const setDisputeReason = (reason: string) => patchSheet("dispute", { reason });
export function sendDispute() {
  const s = sheetOf("dispute");
  if (!s || !s.reason.trim()) return;
  const line = folio().find((l) => l.id === s.line_id);
  set({ disputes: { ...get().disputes, [s.line_id]: s.reason.trim() }, sheet: null });
  report("folio.disputed", { id: s.line_id, value: s.reason.trim(), label: line ? `${line.label}, ${money(line.amount)}` : s.line_id });
  toast("Sent to the front desk", DATA.dispute_rule);
}
export function pickLate(time: string | null) {
  set({ latePick: time });
  if (time) report("late.picked", { value: time, label: LATE.options.find((o) => o.id === time)?.label ?? time });
}
/** The guest's own "Request late check-out". */
export function requestLate() {
  const o = LATE.options.find((x) => x.id === get().latePick);
  if (!o || !o.available) return;
  if (o.fee) charge("fee", `Late check-out, ${o.label}`, o.fee, `Late check-out until ${o.label} on ${day(stayClock().depart)}.`);
  set({ lateRequested: o.id });
  report("late.requested", { value: o.id, label: o.label, total: o.fee });
  toast("Late check-out requested", `Until ${o.label}. ${LATE.rule}`);
}
/** The guest's own "Check out now". */
export function expressCheckout() {
  if (!get().checkedIn || get().checkedOut) return;
  const b = balance();
  set({ checkedOut: true });
  report("checkout.done", { total: b, label: `balance ${money(b)} on ${GUEST.card}` });
  toast("You're checked out", `${money(b)} was charged to your ${GUEST.card}. Your receipt is on its way to ${GUEST.email}. Safe travels!`);
}

// ─── Dining and drinks ───────────────────────────────────────────────────────

export const setOutletTab = (outlet: Outlet) => set({ outletTab: outlet });
export const setSection = (outlet: Outlet, section: string) => set({ section: { ...get().section, [outlet]: section }, outletTab: outlet });

export function openItem(outlet: Outlet, itemId: string, init?: { qty?: number; choices?: string[]; note?: string; edit?: number }) {
  if (!getItem(outlet, itemId)) return false;
  set({ sheet: { kind: "item", outlet, item_id: itemId, qty: init?.qty ?? 1, choices: init?.choices ?? [], note: init?.note ?? "", edit: init?.edit ?? null } });
  return true;
}
export const setItemQty = (qty: number) => patchSheet("item", { qty: Math.max(1, Math.min(20, qty)) });
export const setItemNote = (note: string) => patchSheet("item", { note });
/** Tap a choice: a pick group keeps one, an add group toggles. */
export function toggleChoice(group: string, choice: string, pick: boolean) {
  const s = sheetOf("item");
  if (!s) return;
  const key = `${group}:${choice}`;
  const rest = pick ? s.choices.filter((c) => !c.startsWith(`${group}:`)) : s.choices.filter((c) => c !== key);
  patchSheet("item", { choices: s.choices.includes(key) && !pick ? rest : [...rest, key] });
}
const lineLabel = (outlet: Outlet, l: Line) => {
  const item = getItem(outlet, l.item_id);
  const extras = choiceLabels(outlet, l);
  return `${l.qty} × ${item?.name ?? l.item_id}${extras.length ? ` (${extras.join(", ")})` : ""}`;
};
/** The item sheet's "Add to order". */
export function addFromSheet() {
  const s = sheetOf("item");
  if (!s) return;
  const line: Line = { item_id: s.item_id, qty: s.qty, choices: s.choices, note: s.note };
  const lines = [...get().carts[s.outlet]];
  if (s.edit !== null) lines[s.edit] = line;
  else lines.push(line);
  set({ carts: { ...get().carts, [s.outlet]: lines }, sheet: null });
  const t = orderTotals(s.outlet, lines, get().tip[s.outlet] ?? 0);
  report("cart.changed", { outlet: s.outlet, id: s.item_id, qty: s.qty, choices: s.choices, total: t.subtotal, label: `added ${lineLabel(s.outlet, line)}` });
}
export function removeLine(outlet: Outlet, index: number) {
  const lines = [...get().carts[outlet]];
  const [gone] = lines.splice(index, 1);
  if (!gone) return;
  set({ carts: { ...get().carts, [outlet]: lines } });
  const t = orderTotals(outlet, lines, get().tip[outlet] ?? 0);
  report("cart.changed", { outlet, id: gone.item_id, qty: 0, total: t.subtotal, label: `removed ${lineLabel(outlet, gone)}` });
}
export function setLineQty(outlet: Outlet, index: number, qty: number) {
  if (qty < 1) return removeLine(outlet, index);
  const lines = get().carts[outlet].map((l, i) => (i === index ? { ...l, qty } : l));
  set({ carts: { ...get().carts, [outlet]: lines } });
  const t = orderTotals(outlet, lines, get().tip[outlet] ?? 0);
  report("cart.changed", { outlet, id: lines[index].item_id, qty, total: t.subtotal, label: `changed to ${lineLabel(outlet, lines[index])}` });
}
export const openCart = (outlet: Outlet) => set({ sheet: { kind: "cart", outlet }, outletTab: outlet });
export const setTip = (outlet: Outlet, pct: number) => set({ tip: { ...get().tip, [outlet]: pct } });
export const setDeliverTo = (to: "room" | "cabana") => set({ deliverTo: to });
export const setCabana = (n: string) => set({ cabana: n });

/** Where the bar order goes, as said. */
export const deliverLabel = (s: State = get()) => (s.deliverTo === "cabana" ? `pool cabana ${s.cabana ?? "?"}` : s.room ? `room ${s.room}` : "your room");

/** Why Place order is not ready yet, or null. */
export function orderBlocked(outlet: Outlet, s: State = get()): string | null {
  if (!s.carts[outlet].length) return "Your order is empty.";
  if (!s.checkedIn) return "Check in first so we know your room.";
  if (s.checkedOut) return "You've checked out.";
  if (s.tip[outlet] === null) return "Choose a tip, or no tip.";
  if (outlet === "bar" && s.deliverTo === null) return "Choose where to deliver.";
  if (outlet === "bar" && s.deliverTo === "cabana" && !s.cabana) return "Choose your cabana.";
  return null;
}
/** The guest's own "Place order". */
export function placeOrder(outlet: Outlet) {
  const s = get();
  if (orderBlocked(outlet, s)) return;
  const lines = s.carts[outlet];
  const t = orderTotals(outlet, lines, s.tip[outlet] ?? 0);
  const section = getItem(outlet, lines[0].item_id)?.section;
  const eta = outlet === "dining" ? (DATA.dining.periods.find((p) => p.id === section)?.eta ?? "30 to 40 minutes") : BAR.eta;
  const deliver = outlet === "bar" ? deliverLabel(s) : `room ${s.room}`;
  const names = lines.map((l) => lineLabel(outlet, l)).join("; ");
  const order: Order = { id: newId(outlet), outlet, lines, total: t.total, eta, deliver };
  charge(outlet, outlet === "dining" ? "In-room dining" : "Drinks delivery", t.total, `${names}. Subtotal ${money(t.subtotal)}, service ${money(t.service)}${t.delivery ? `, delivery ${money(t.delivery)}` : ""}, tax ${money(t.tax)}, tip ${money(t.tip)}.`);
  set({ orders: [...get().orders, order], carts: { ...get().carts, [outlet]: [] }, sheet: null, tip: { ...get().tip, [outlet]: null } });
  report("order.placed", { outlet, id: order.id, total: t.total, time: eta, label: `${names}, ${money(t.total)} to ${deliver}, in ${eta}` });
  toast("Order placed", `${money(t.total)} on your room bill. Arriving at ${deliver} in ${eta}.${outlet === "bar" && lines.some((l) => getItem("bar", l.item_id)?.alcohol) ? " Please have your ID ready." : ""}`);
}

// ─── Spa ─────────────────────────────────────────────────────────────────────

export const setSpaCategory = (c: string | null) => set({ spaCategory: c });
export function openTreatment(treatmentId: string, date?: string, pref?: string) {
  if (!getTreatment(treatmentId)) return false;
  set({ sheet: { kind: "spa", treatment_id: treatmentId, date: date ?? stayClock().today, pref: pref ?? "any", time: null, therapist_id: null } });
  return true;
}
export const setSpaDate = (date: string) => patchSheet("spa", { date, time: null, therapist_id: null });
export const setSpaPref = (pref: string) => patchSheet("spa", { pref, time: null, therapist_id: null });
export function pickSpaSlot(time: string, therapistId: string) {
  const s = sheetOf("spa");
  if (!s) return;
  patchSheet("spa", { time, therapist_id: therapistId });
  const t = getTreatment(s.treatment_id)!;
  report("spa.picked", { id: s.treatment_id, date: s.date, time, therapist: therapistId, label: `${t.name}, ${t.minutes} min, ${day(s.date)} at ${clock(time)} with ${getTherapist(therapistId)?.name}` });
}
/** The guest's own "Book". */
export function bookSpa() {
  const s = sheetOf("spa");
  if (!s || !s.time || !s.therapist_id) return;
  const t = getTreatment(s.treatment_id)!;
  const tot = spaTotal(t.id);
  const label = `${t.name}, ${t.minutes} min, ${day(s.date)} at ${clock(s.time)} with ${getTherapist(s.therapist_id)?.name}`;
  charge("spa", `Salt & Cypress Spa, ${t.name.toLowerCase()}, ${t.minutes} min`, tot.total, `${label}: ${money(tot.price)} plus the 20% spa service charge of ${money(tot.service)}.`);
  set({ bookings: [...get().bookings, { id: newId("spa"), kind: "spa", label: `${t.name}, ${t.minutes} min`, when: `${day(s.date)}, ${clock(s.time)}`, total: tot.total }], sheet: null });
  report("spa.booked", { id: t.id, date: s.date, time: s.time, therapist: s.therapist_id, total: tot.total, label });
  toast("Spa booked", `${label}. ${money(tot.total)} on your room bill.`);
}

// ─── Activities ──────────────────────────────────────────────────────────────

export const showOnMap = (placeId: string | null) => set({ mapPin: placeId });
export function openActivity(activityId: string, init?: { date?: string; time?: string | null; guests?: number }) {
  const a = getActivity(activityId);
  if (!a || !a.bookable) return false;
  set({ sheet: { kind: "activity", activity_id: activityId, date: init?.date ?? stayClock().today, time: init?.time ?? null, guests: init?.guests ?? 1 }, mapPin: a.place });
  const s = sheetOf("activity")!;
  if (s.time) report("activity.picked", { id: a.id, date: s.date, time: s.time, guests: s.guests, label: `${a.name}, ${day(s.date)} at ${clock(s.time)}, ${s.guests} ${s.guests === 1 ? "guest" : "guests"}` });
  return true;
}
export const setActivityField = (p: Partial<{ date: string; time: string | null; guests: number }>) => patchSheet("activity", p);
/** The guest's own "Book". */
export function bookActivity() {
  const s = sheetOf("activity");
  const a = s && getActivity(s.activity_id);
  if (!s || !a || !s.time) return;
  const total = activityTotal(a.id, s.guests);
  const label = `${a.name}, ${day(s.date)} at ${clock(s.time)}, ${s.guests} ${s.guests === 1 ? "guest" : "guests"}`;
  if (total) charge("activity", a.name, total, `${label}: ${money(a.price)} per ${a.per ?? "guest"}.`);
  set({ bookings: [...get().bookings, { id: newId("act"), kind: "activity", label: a.name, when: `${day(s.date)}, ${clock(s.time)}`, total }], sheet: null });
  report("activity.booked", { id: a.id, date: s.date, time: s.time, guests: s.guests, total, label });
  toast("You're booked", `${label}.${total ? ` ${money(total)} on your room bill.` : ""}`);
}

// ─── Meetings ────────────────────────────────────────────────────────────────

export const setMeetingFilter = (p: Partial<State["meetingFilter"]>) => set({ meetingFilter: { ...get().meetingFilter, ...p } });
export function openMeeting(roomId: string, init?: Partial<Omit<Extract<Sheet, { kind: "meeting" }>, "kind" | "room_id">>) {
  const r = getMeetingRoom(roomId);
  if (!r) return false;
  const f = get().meetingFilter;
  // Nothing chosen for the guest: the layout only when the filter (or a one-layout room) settles it, no block.
  const layouts = Object.keys(r.layouts);
  const layout = init?.layout ?? (f.layout && f.layout in r.layouts ? f.layout : layouts.length === 1 ? layouts[0] : "");
  set({
    sheet: {
      kind: "meeting",
      room_id: roomId,
      date: init?.date ?? f.date,
      block: init?.block ?? "",
      start: init?.start ?? null,
      hours: init?.hours ?? null,
      headcount: init?.headcount ?? f.headcount ?? 0,
      layout,
      catering: init?.catering ?? [],
      av: init?.av ?? [],
    },
  });
  return true;
}
export const setMeetingField = (p: Partial<Omit<Extract<Sheet, { kind: "meeting" }>, "kind" | "room_id">>) => patchSheet("meeting", p);
export const meetingLabel = (s: Extract<Sheet, { kind: "meeting" }>) => {
  const r = getMeetingRoom(s.room_id)!;
  const block = s.block === "hours" ? `${s.hours ?? "?"} hours from ${s.start ? clock(s.start) : "?"}` : (DATA.meetings.blocks.find((b) => b.id === s.block)?.label ?? s.block).toLowerCase();
  return `${r.name}, ${day(s.date)}, ${block}, ${s.headcount} people, ${DATA.meetings.layout_labels[s.layout] ?? s.layout}`;
};
/** The guest's own "Request booking". */
export function requestMeeting() {
  const s = sheetOf("meeting");
  if (!s || !s.layout || s.headcount < 1) return;
  const r = getMeetingRoom(s.room_id)!;
  const span = blockSpan(s.block, s.start, s.hours);
  if (!span || !roomFree(s.room_id, s.date, span) || s.headcount > (r.layouts[s.layout] ?? 0)) return;
  const q = meetingQuote(s.room_id, s.block, s.hours, s.headcount, s.catering, s.av);
  const label = meetingLabel(s);
  set({ bookings: [...get().bookings, { id: newId("mtg"), kind: "meeting", label: getMeetingRoom(s.room_id)!.name, when: label, total: q.total }], sheet: null });
  report("meeting.booked", { id: s.room_id, date: s.date, total: q.total, label: `${label}, ${money(q.total)}` });
  toast("Booking requested", `${label}. Estimated ${money(q.total)}. Our events team confirms within two hours.`);
}

// ─── Visitors ────────────────────────────────────────────────────────────────

export function openVisitor(visitorId: string, meet?: "room" | "lobby" | null) {
  if (!get().visitors.some((v) => v.id === visitorId && v.status === "pending")) return false;
  set({ sheet: { kind: "visitor", visitor_id: visitorId, meet: meet ?? null } });
  return true;
}
export const setVisitorMeet = (meet: "room" | "lobby") => patchSheet("visitor", { meet });
/** The guest's own Approve / Decline. */
export function decideVisitor(decision: "approved" | "declined") {
  const s = sheetOf("visitor");
  if (!s || (decision === "approved" && !s.meet)) return;
  const v = get().visitors.find((x) => x.id === s.visitor_id);
  if (!v) return;
  set({ visitors: get().visitors.map((x) => (x.id === v.id ? { ...x, status: decision } : x)), sheet: null });
  report("visitor.decided", { id: v.id, value: decision, label: `${v.name}${decision === "approved" ? `, ${s.meet === "room" ? "sent up to the room" : "waiting in the lobby"}` : ""}` });
  toast(decision === "approved" ? "Visitor approved" : "Visitor declined", decision === "approved" ? `${v.name} ${s.meet === "room" ? "is on the way up" : "will wait in the lobby"}.` : `The front desk will let ${v.name} know.`);
}
export function openExpect(init?: Partial<Omit<Extract<Sheet, { kind: "expect" }>, "kind">>) {
  set({ sheet: { kind: "expect", name: init?.name ?? "", from: init?.from ?? "", to: init?.to ?? "", meet: init?.meet ?? null, note: init?.note ?? "" } });
}
export const setExpectField = (p: Partial<Omit<Extract<Sheet, { kind: "expect" }>, "kind">>) => patchSheet("expect", p);
/** The guest's own "Add visitor". */
export function addExpected() {
  const s = sheetOf("expect");
  if (!s || !s.name.trim() || !s.from || !s.to || !s.meet) return;
  const e: Expected = { name: s.name.trim(), from: s.from, to: s.to, meet: s.meet, note: s.note };
  set({ expected: [...get().expected, e], sheet: null });
  report("visitor.added", { label: `${e.name}, ${clock(e.from)} to ${clock(e.to)}, ${e.meet === "room" ? "send up" : "wait in the lobby"}` });
  toast("Visitor added", `The front desk will expect ${e.name} between ${clock(e.from)} and ${clock(e.to)}.`);
}

// ─── Front desk requests ─────────────────────────────────────────────────────

export function openRequest(kind: RequestKind, init?: Partial<Omit<Extract<Sheet, { kind: "request" }>, "kind" | "request">>) {
  set({
    sheet: {
      kind: "request",
      request: kind,
      items: init?.items ?? [],
      issue: init?.issue ?? null,
      option: init?.option ?? null,
      date: init?.date ?? (kind === "wakeup" ? null : null),
      time: init?.time ?? null,
      details: init?.details ?? "",
    },
  });
}
export const setRequestField = (p: Partial<Omit<Extract<Sheet, { kind: "request" }>, "kind" | "request">>) => patchSheet("request", p);
export function toggleRequestItem(id: string) {
  const s = sheetOf("request");
  if (s) patchSheet("request", { items: s.items.includes(id) ? s.items.filter((x) => x !== id) : [...s.items, id] });
}
/** What a request costs, or 0. */
export function requestFee(s: Extract<Sheet, { kind: "request" }>): number {
  if (s.request !== "transport") return 0;
  return REQUESTS.transport.options.find((o) => o.id === s.option)?.price ?? 0;
}
/** Why Send is not ready, or null. */
export function requestBlocked(s: Extract<Sheet, { kind: "request" }>): string | null {
  switch (s.request) {
    case "housekeeping":
      return s.items.length ? null : "Choose what you need.";
    case "maintenance":
      return s.issue ? null : "Choose what's wrong.";
    case "wakeup":
      return s.date && s.time ? null : "Choose a day and time.";
    case "valet":
      return s.time ? null : "Choose when you need the car.";
    case "transport":
      return s.option && s.time ? null : "Choose a ride and a time.";
    case "lost_found":
      return s.details.trim() ? null : "Describe what you lost and where.";
  }
}
export function requestLabel(s: Extract<Sheet, { kind: "request" }>): string {
  const R = REQUESTS;
  const at = s.time ? ` at ${clock(s.time)}` : "";
  switch (s.request) {
    case "housekeeping":
      return `Housekeeping: ${s.items.map((i) => R.housekeeping.items.find((x) => x.id === i)?.label ?? i).join(", ")}`;
    case "maintenance":
      return `Maintenance: ${R.maintenance.issues.find((x) => x.id === s.issue)?.label ?? s.issue}${s.details ? `, ${s.details}` : ""}`;
    case "wakeup":
      return `Wake-up call, ${s.date ? day(s.date) : "?"}${at}`;
    case "valet":
      return `Car from valet, ticket ${R.valet.ticket}${at}`;
    case "transport":
      return `${R.transport.options.find((o) => o.id === s.option)?.label ?? "Ride"}${at}${s.details ? `, to ${s.details}` : ""}`;
    case "lost_found":
      return `Lost and found: ${s.details}`;
  }
}
const ETA: Record<RequestKind, string> = {
  housekeeping: REQUESTS.housekeeping.eta,
  maintenance: REQUESTS.maintenance.eta,
  wakeup: "set",
  valet: REQUESTS.valet.eta,
  transport: "confirmed by the front desk",
  lost_found: "the front desk will call you",
};
/** "Send" (the concierge may press it only for a request that costs nothing, once the guest said yes). */
export function sendRequest() {
  const s = sheetOf("request");
  if (!s || requestBlocked(s)) return;
  const label = requestLabel(s);
  const fee = requestFee(s);
  if (fee) charge("transport", R_LABEL(s), fee, `${label}. Fixed fare.`);
  set({ requests: [...get().requests, { id: newId("req"), kind: s.request, label, eta: ETA[s.request] }], sheet: null });
  report("request.sent", { kind: s.request, total: fee, label });
  toast("Request sent", `${label}. ${s.request === "wakeup" ? REQUESTS.wakeup.note : `Status: ${ETA[s.request]}.`}`);
}
const R_LABEL = (s: Extract<Sheet, { kind: "request" }>) => REQUESTS.transport.options.find((o) => o.id === s.option)?.label ?? "Transport";

// ─── What the call starts from (CONTRACT.md, "The call") ─────────────────────

/** A compact picture of the stay for `init.stay`: ids and flags only, no personal data. */
export function stayForInit() {
  const s = get();
  return {
    scenario: s.scenario,
    checked_in: s.checkedIn,
    checked_out: s.checkedOut,
    room: s.room,
    checkin: s.checkin,
    carts: s.carts,
    orders: s.orders.length,
    charges: s.charges.map((c) => ({ id: c.id, category: c.category, label: c.label, amount: c.amount })),
    disputes: Object.keys(s.disputes),
    late: s.lateRequested,
    visitors: Object.fromEntries(s.visitors.map((v) => [v.id, v.status])),
    bookings: s.bookings.map((b) => `${b.label}, ${b.when}`),
    requests: s.requests.map((r) => r.label),
  };
}
