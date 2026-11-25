/**
 * Hotel Belmonte's rules for the app, the twin of the brain's
 * `backend/hotel.py`: order totals, the spa's free times, which room the
 * guest's preferences get, a meeting quote. `data/rules_cases.json` (written by
 * the brain's `write_cases()`) holds the two to one answer (rules.test.ts).
 */
import {
  ACTIVITIES,
  BAR,
  CHECKIN,
  type CheckinRoom,
  DATA,
  DINING,
  GROUPS,
  HOTEL,
  MEETINGS,
  type MenuItem,
  type OptionGroup,
  type Outlet,
  type Period,
  SPA,
  type ScenarioId,
  getItem,
  getMeetingRoom,
  getTreatment,
} from "../data";
import { cents, datesBetween, hhmm, minutes } from "./format";

// ─── The stay's clock ────────────────────────────────────────────────────────

export interface Clock {
  today: string;
  now: string;
  arrive: string;
  depart: string;
}
export const clockOf = (s: ScenarioId): Clock => {
  const x = DATA.scenarios[s];
  return { today: x.today, now: x.now, arrive: x.arrive, depart: x.depart };
};
/** Today through the departure day. */
export const bookableDates = (c: Clock) => datesBetween(c.today, c.depart);
/** Is `t` on `d` far enough ahead to book (30 minutes from now today). */
export const later = (c: Clock, d: string, t: string, leadMin = 30) => d > c.today || (d === c.today && minutes(t) >= minutes(c.now) + leadMin);

// ─── Check-in ────────────────────────────────────────────────────────────────

export function assignRoom(floor: string | null, bed: string | null, quiet: boolean | null): CheckinRoom {
  const fits = (r: CheckinRoom, f: string | null, q: boolean | null) => {
    if ((bed ?? "king") !== r.bed) return false;
    if (f === "high" && r.floor < 10) return false;
    if (f === "low" && r.floor > 6) return false;
    return !(q && !r.quiet);
  };
  for (const [f, q] of [
    [floor, quiet],
    [floor, null],
    [null, null],
  ] as const) {
    const hit = CHECKIN.rooms.find((r) => fits(r, f, q));
    if (hit) return hit;
  }
  return CHECKIN.rooms[0];
}
const arrivalMin = (arrival: string, now: string) => (arrival === "now" ? minutes(now) : minutes(arrival));
export const earlyOffered = (arrival: string | null, now: string) => arrival !== null && arrivalMin(arrival, now) < minutes(CHECKIN.early.before);
export const readyBy = (room: CheckinRoom, now: string) => (room.ready === "now" ? minutes(now) : minutes(room.ready));
export const earlyAvailable = (room: CheckinRoom, arrival: string, now: string) => readyBy(room, now) <= arrivalMin(arrival, now);

// ─── Menus and orders ────────────────────────────────────────────────────────

export interface Line {
  item_id: string;
  qty: number;
  choices: string[];
  note: string;
}

const SIZE: OptionGroup = {
  label: "Size",
  pick: true,
  choices: [
    ["glass", "Glass", 0],
    ["bottle", "Bottle", 0],
  ],
};
/** An item's option groups, with a size group for a wine sold by the glass. */
export function groupsOf(item: MenuItem): [string, OptionGroup][] {
  const out: [string, OptionGroup][] = item.options.map((g) => [g, GROUPS[g]]);
  if (item.bottle !== undefined) out.unshift(["size", SIZE]);
  return out;
}
export function unitPrice(outlet: Outlet, line: Line): number {
  const item = getItem(outlet, line.item_id);
  if (!item) return 0;
  const base = line.choices.includes("size:bottle") && item.bottle !== undefined ? item.bottle : item.price;
  let extra = 0;
  for (const [gid, g] of groupsOf(item)) for (const [cid, , add] of g.choices) if (line.choices.includes(`${gid}:${cid}`)) extra += add;
  return cents(base + extra);
}
export function choiceLabels(outlet: Outlet, line: Line): string[] {
  const item = getItem(outlet, line.item_id);
  if (!item) return [];
  const out: string[] = [];
  for (const [gid, g] of groupsOf(item)) for (const [cid, label] of g.choices) if (line.choices.includes(`${gid}:${cid}`)) out.push(label);
  return out;
}
/** The pick groups that still have no choice (the Add button waits for them). */
export function missingPicks(item: MenuItem, choices: string[]): string[] {
  return groupsOf(item)
    .filter(([gid, g]) => g.pick && !choices.some((c) => c.startsWith(`${gid}:`)))
    .map(([, g]) => g.label);
}

export interface Totals {
  subtotal: number;
  service: number;
  delivery: number;
  tax: number;
  tip: number;
  total: number;
}
export function orderTotals(outlet: Outlet, lines: Line[], tipPct: number): Totals {
  const policy = outlet === "dining" ? DINING : BAR;
  const subtotal = cents(lines.reduce((s, l) => s + unitPrice(outlet, l) * l.qty, 0));
  const service = cents((subtotal * policy.service_charge_pct) / 100);
  const delivery = lines.length ? cents(policy.delivery_fee) : 0;
  const tax = cents((subtotal * HOTEL.sales_tax_pct) / 100);
  const tip = cents((subtotal * tipPct) / 100);
  return { subtotal, service, delivery, tax, tip, total: cents(subtotal + service + delivery + tax + tip) };
}
export function periodOpen(p: Period, now: string): boolean {
  const [a, b, n] = [minutes(p.from), minutes(p.to), minutes(now)];
  return a < b ? a <= n && n < b : n >= a || n < b;
}
export const openPeriod = (now: string) => DINING.periods.find((p) => periodOpen(p, now))!.id;
/** California: no alcohol sold from 2:00 to 6:00 AM. */
export const alcoholServed = (now: string) => !(minutes(now) >= minutes("02:00") && minutes(now) < minutes("06:00"));
export function cabanaOpen(now: string): boolean {
  const pool = BAR.bars.find((b) => b.id === "pool")!;
  return minutes(now) >= minutes(pool.from) && minutes(now) < minutes(pool.to);
}

// ─── Spa ─────────────────────────────────────────────────────────────────────

export const SPA_CLOSE = "20:00";
export function therapistsFor(treatmentId: string, pref: string | null): string[] {
  const t = getTreatment(treatmentId);
  if (!t) return [];
  const p = (pref ?? "any").toLowerCase();
  const g = (id: string) => SPA.therapists.find((x) => x.id === id)?.gender;
  if (p === "female") return t.therapists.filter((id) => g(id) === "female");
  if (p === "male") return t.therapists.filter((id) => g(id) === "male");
  if (SPA.therapists.some((x) => x.id === p)) return t.therapists.filter((id) => id === p);
  return [...t.therapists];
}
function free(th: string, d: string, t: string, mins: number): boolean {
  const sched = SPA.schedule[d]?.[th] ?? [];
  if (!sched.includes(t)) return false;
  if (mins > 60 && !sched.includes(hhmm(minutes(t) + 60))) return false;
  return minutes(t) + mins <= minutes(SPA_CLOSE);
}
/** [time, therapist id] for each free start, by time then therapist. */
export function spaSlots(c: Clock, treatmentId: string, d: string, pref: string | null): [string, string][] {
  const t = getTreatment(treatmentId);
  if (!t) return [];
  const who = therapistsFor(treatmentId, pref);
  const times = [...new Set(who.flatMap((th) => SPA.schedule[d]?.[th] ?? []))].sort();
  const out: [string, string][] = [];
  for (const x of times) {
    if (!later(c, d, x)) continue;
    const ok = who.filter((th) => free(th, d, x, t.minutes));
    if (t.for_two) {
      if (ok.length >= 2) out.push([x, ok[0]]);
    } else for (const th of ok) out.push([x, th]);
  }
  return out;
}
export function spaTotal(treatmentId: string): { price: number; service: number; total: number } {
  const p = getTreatment(treatmentId)?.price ?? 0;
  const service = cents((p * SPA.service_charge_pct) / 100);
  return { price: p, service, total: cents(p + service) };
}

// ─── Activities ──────────────────────────────────────────────────────────────

export const activityTotal = (id: string, guests: number) => cents((ACTIVITIES.find((a) => a.id === id)?.price ?? 0) * guests);
export const activityTimes = (c: Clock, id: string, d: string) => (ACTIVITIES.find((a) => a.id === id)?.times ?? []).filter((t) => later(c, d, t));

// ─── Meetings ────────────────────────────────────────────────────────────────

export function blockSpan(block: string, start: string | null, hours: number | null): [string, string] | null {
  const b = MEETINGS.blocks.find((x) => x.id === block);
  if (!b) return null;
  if (block === "hours") return start && hours ? [start, hhmm(minutes(start) + hours * 60)] : null;
  return [b.from!, b.to!];
}
export function roomFree(roomId: string, d: string, span: [string, string]): boolean {
  const [a, b] = [minutes(span[0]), minutes(span[1])];
  if (a < minutes(MEETINGS.hours_from) || b > minutes(MEETINGS.hours_to)) return false;
  return (MEETINGS.taken[roomId]?.[d] ?? []).every(([x, y]) => b <= minutes(x) || a >= minutes(y));
}
export function roomsFor(headcount: number | null, layout: string | null) {
  return MEETINGS.rooms.filter((r) => {
    if (layout && !(layout in r.layouts)) return false;
    const cap = layout ? r.layouts[layout] : Math.max(...Object.values(r.layouts));
    return !(headcount && cap < headcount);
  });
}
export interface Quote {
  room: number;
  catering: number;
  fb_service: number;
  tax: number;
  av: number;
  total: number;
  hours: number;
}
export function meetingQuote(roomId: string, block: string, hours: number | null, headcount: number, catering: string[], av: string[]): Quote {
  const r = getMeetingRoom(roomId)!;
  const span = ({ morning: 4, afternoon: 4, full: 9 } as Record<string, number>)[block] ?? hours ?? 0;
  const room = block === "morning" || block === "afternoon" ? r.rates.half : block === "full" ? r.rates.full : r.rates.hour * span;
  const cat = cents(MEETINGS.catering.filter((c) => catering.includes(c.id)).reduce((s, c) => s + c.per_person, 0) * headcount);
  const fb = cents((cat * MEETINGS.fb_service_pct) / 100);
  const tax = cents((cat * HOTEL.sales_tax_pct) / 100);
  const avTotal = cents(MEETINGS.av_addons.filter((a) => av.includes(a.id)).reduce((s, a) => s + a.price * (a.per_hour ? span : 1), 0));
  return { room, catering: cat, fb_service: fb, tax, av: avTotal, total: cents(room + cat + fb + tax + avTotal), hours: span };
}
