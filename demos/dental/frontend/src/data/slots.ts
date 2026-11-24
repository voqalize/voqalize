/**
 * The calendar and the slot engine — CONTRACT.md "Slots", "Root canal
 * sittings", "Rules" and "Cancellation / reschedule terms", exactly as
 * `backend/clinic.py` computes them. `slots.test.ts` holds this file to
 * `data/slot_fixtures.json`, which the backend writes.
 *
 * Dates are ISO strings ("2026-11-18") and times minutes after midnight, all
 * in Asia/Kolkata. "Now" is a {@link Clock}: today's date there and the
 * minute of the day, never the browser's own zone.
 */
import {
  type Booking,
  DATA,
  DAYS,
  type Day,
  FILLER,
  type Patient,
  POLICY,
  type Rule,
  type Service,
  branch,
  dentist,
  hhmm,
  minutes,
  rupees,
  service,
} from "./clinic";

// ─── Dates ───────────────────────────────────────────────────────────────────

/** "Now" in Asia/Kolkata: today's date, the minute of the day (whole), and
 *  the exact minute (with seconds) for the policy's hour counts. */
export interface Clock {
  today: string;
  minute: number;
  exact: number;
}

export function clockAt(instant: Date): Clock {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(instant);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "0";
  const minute = Number(get("hour")) * 60 + Number(get("minute"));
  return { today: `${get("year")}-${get("month")}-${get("day")}`, minute, exact: minute + Number(get("second")) / 60 };
}

export const nowClock = () => clockAt(new Date());

const dayNo = (iso: string) => {
  const [y, m, d] = iso.split("-").map(Number);
  return Date.UTC(y, m - 1, d) / 86_400_000;
};
const fromDayNo = (n: number) => new Date(n * 86_400_000).toISOString().slice(0, 10);

export const addDays = (iso: string, n: number) => fromDayNo(dayNo(iso) + n);
export const daysBetween = (a: string, b: string) => dayNo(b) - dayNo(a);
/** 0 = Monday … 6 = Sunday. */
export const weekdayIndex = (iso: string) => (new Date(dayNo(iso) * 86_400_000).getUTCDay() + 6) % 7;
export const weekdayOf = (iso: string): Day => DAYS[weekdayIndex(iso)];
export const mondayOf = (iso: string) => addDays(iso, -weekdayIndex(iso));
export const dateOf = (today: string, week: number, day: Day) => addDays(mondayOf(today), 7 * week + DAYS.indexOf(day));
export function nextOpenDay(today: string): string {
  let d = addDays(today, 1);
  while (weekdayOf(d) === "sun") d = addDays(d, 1);
  return d;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
/** "18 Nov 2026" */
export function longDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${String(d).padStart(2, "0")} ${MONTHS[m - 1]} ${y}`;
}
export const weekdayName = (iso: string) => WEEKDAYS[weekdayIndex(iso)];
export const shortWeekday = (iso: string) => WEEKDAYS[weekdayIndex(iso)].slice(0, 3);
/** "Thu 19 Nov" */
export function shortDate(iso: string): string {
  const [, m, d] = iso.split("-").map(Number);
  return `${shortWeekday(iso)} ${d} ${MONTHS[m - 1]}`;
}

// ─── Appointments ────────────────────────────────────────────────────────────

/** One appointment with its date: what the calendar and the slots read. */
export interface Appt {
  id: string;
  service: string;
  branch: string;
  date: string;
  start: number;
  duration_min: number;
  dentist: string | null;
  chair: string | null;
  resource: string | null;
  patient_id: string | null;
  sitting: number | null;
  changes: number;
  status: "booked" | "cancelled";
}

export const apptEnd = (a: Appt) => a.start + a.duration_min;
export const apptTime = (a: Appt) => hhmm(a.start);

export function dated(b: Booking, today: string): Appt {
  const date = b.anchor === "next_open_day" ? nextOpenDay(today) : dateOf(today, b.week ?? 0, b.day ?? "mon");
  return {
    id: b.id,
    service: b.service,
    branch: b.branch,
    date,
    start: minutes(b.start),
    duration_min: b.duration_min,
    dentist: b.dentist ?? null,
    chair: b.chair ?? null,
    resource: b.resource ?? null,
    patient_id: b.patient_id ?? null,
    sitting: b.sitting ?? null,
    changes: b.changes ?? 0,
    status: "booked",
  };
}

export interface Slot {
  date: string;
  start: number;
  time: string;
  branch: string;
  dentist: string | null;
  chair: string | null;
  resource: string | null;
}

const holds = (a: Appt) => [a.dentist, a.chair, a.resource].filter(Boolean) as string[];

/** Every appointment as of `clock`: the authored ones, then this browser's
 *  changes laid over them. */
export class Calendar {
  readonly appts = new Map<string, Appt>();
  private byDate = new Map<string, Appt[]>();

  constructor(
    readonly clock: Clock,
    overlay: Iterable<Appt> = [],
  ) {
    for (const b of [...FILLER, ...DATA.patient_appointments]) this.appts.set(b.id, dated(b, clock.today));
    for (const a of overlay) this.appts.set(a.id, a);
    for (const a of this.appts.values()) {
      const list = this.byDate.get(a.date) ?? [];
      list.push(a);
      this.byDate.set(a.date, list);
    }
  }

  get today() {
    return this.clock.today;
  }

  on(date: string): Appt[] {
    return this.byDate.get(date) ?? [];
  }

  busy(key: string, date: string, start: number, end: number, ignore?: string | null): boolean {
    for (const a of this.on(date)) {
      if (a.status !== "booked" || a.id === ignore || !holds(a).includes(key)) continue;
      if (a.start < end && start < apptEnd(a)) return true;
    }
    return false;
  }

  /** Minutes from now until `date` `start` (negative: past). */
  minutesUntil(date: string, start: number): number {
    return daysBetween(this.clock.today, date) * 1440 + start - this.clock.exact;
  }

  ofPatient(pid: string): Appt[] {
    return [...this.appts.values()]
      .filter((a) => a.patient_id === pid)
      .sort((a, b) => daysBetween(b.date, a.date) * 1440 + a.start - b.start);
  }

  upcoming(pid: string): Appt[] {
    return this.ofPatient(pid).filter((a) => a.status === "booked" && this.minutesUntil(a.date, a.start) > 0);
  }

  // ─── Slots ──────────────────────────────────────────────────────────

  earliest(svc: Service, date: string): number {
    if (date !== this.clock.today) return 0;
    const lead = svc.same_day ? DATA.booking.emergency_lead_min : DATA.booking.lead_min;
    return this.clock.minute + lead;
  }

  bookableDay(date: string): boolean {
    const d = daysBetween(this.clock.today, date);
    return d >= 0 && d <= DATA.booking.horizon_days;
  }

  slots(svc: Service, date: string, opts: { branch?: string | null; dentist?: string | null; ignore?: string | null } = {}): Slot[] {
    if (!this.bookableDay(date)) return [];
    const step = DATA.booking.slot_step_min;
    const first = this.earliest(svc, date);
    const dur = svc.duration_min;
    const day = weekdayOf(date);
    const out: Slot[] = [];
    const slot = (start: number, b: string, d: string | null, c: string | null, r: string | null): Slot => ({
      date,
      start,
      time: hhmm(start),
      branch: b,
      dentist: d,
      chair: c,
      resource: r,
    });
    if (svc.resource) {
      for (const b of DATA.branches) {
        if ((opts.branch && b.id !== opts.branch) || !b.open_days.includes(day)) continue;
        for (const room of b.imaging) {
          if (!room.does.includes(svc.resource)) continue;
          for (const s of room.sessions) {
            const end = minutes(s.end);
            for (let t = minutes(s.start); t + dur <= end; t += step) {
              if (t >= first && !this.busy(room.id, date, t, t + dur, opts.ignore)) out.push(slot(t, b.id, null, null, room.id));
            }
          }
        }
      }
    } else {
      for (const did of svc.dentists ?? []) {
        if (opts.dentist && did !== opts.dentist) continue;
        const d = dentist(did);
        if (!d) continue;
        for (const s of d.schedule[day] ?? []) {
          if (opts.branch && s.branch !== opts.branch) continue;
          const b = branch(s.branch);
          if (!b) continue;
          const chairs = b.chairs.filter((c) => (svc.chairs ?? []).includes(c.kind));
          const end = minutes(s.end);
          for (let t = minutes(s.start); t + dur <= end; t += step) {
            if (t < first || this.busy(did, date, t, t + dur, opts.ignore)) continue;
            const c = chairs.find((c) => !this.busy(c.id, date, t, t + dur, opts.ignore));
            if (c) out.push(slot(t, b.id, did, c.id, null));
          }
        }
      }
    }
    const key = (x: Slot) => x.dentist ?? x.resource ?? "";
    return out.sort((a, b) => a.start - b.start || (key(a) < key(b) ? -1 : key(a) > key(b) ? 1 : 0));
  }

  slotAt(
    svc: Service,
    date: string,
    time: string,
    opts: { branch?: string | null; dentist?: string | null; resource?: string | null; ignore?: string | null } = {},
  ): Slot | undefined {
    const t = minutes(time);
    return this.slots(svc, date, opts).find((s) => s.start === t && (!opts.resource || s.resource === opts.resource));
  }

  /** The first `days` days from `start` (today) that have a slot. */
  nextDays(
    svc: Service,
    opts: { branch?: string | null; dentist?: string | null; start?: string; days?: number; ignore?: string | null } = {},
  ): [string, Slot[]][] {
    const out: [string, Slot[]][] = [];
    let on = opts.start && daysBetween(this.clock.today, opts.start) > 0 ? opts.start : this.clock.today;
    const last = addDays(this.clock.today, DATA.booking.horizon_days);
    while (daysBetween(on, last) >= 0 && out.length < (opts.days ?? 3)) {
      const got = this.slots(svc, on, opts);
      if (got.length) out.push([on, got]);
      on = addDays(on, 1);
    }
    return out;
  }

  /** A root canal's later sittings: each on the first day 7–14 days after the
   *  one before with a slot with the same dentist; on that day the slot
   *  nearest the first sitting's time, the first sitting's branch on a tie. */
  planSittings(svc: Service, first: Slot): Slot[] {
    const gap = svc.sitting_gap_days;
    const n = svc.sittings ?? 1;
    if (n <= 1 || !gap) return [];
    const out: Slot[] = [];
    let prev = first;
    for (let i = 0; i < n - 1; i++) {
      let pick: Slot | undefined;
      for (let k = gap.min; k <= gap.max; k++) {
        const on = addDays(prev.date, k);
        const got = this.slots(svc, on, { dentist: prev.dentist }).filter(
          (s) => !out.some((o) => o.date === s.date && Math.abs(o.start - s.start) < svc.duration_min),
        );
        if (got.length) {
          const score = (s: Slot): [number, number] => [Math.abs(s.start - first.start), s.branch !== first.branch ? 1 : 0];
          pick = got.reduce((best, s) => {
            const [a1, a2] = score(s);
            const [b1, b2] = score(best);
            return a1 < b1 || (a1 === b1 && a2 < b2) ? s : best;
          });
          break;
        }
      }
      if (!pick) break;
      out.push(pick);
      prev = pick;
    }
    return out;
  }
}

// ─── Rules that depend on the patient ────────────────────────────────────────

export interface RuleCheck {
  /** null: the patient is not known yet, so the rule is told, not decided. */
  ok: boolean | null;
  rule?: Rule;
  id?: string;
  why: string;
}

export function visits(p: Patient, cal: Calendar): [string, string][] {
  const out: [string, string][] = p.history.map((v) => [v.service, dateOf(cal.today, v.week, v.day)]);
  for (const a of cal.ofPatient(p.id)) if (a.status === "booked") out.push([a.service, a.date]);
  return out;
}

export function checkRule(svc: Service, p: Patient | null | undefined, on: string, cal: Calendar): RuleCheck {
  if (!svc.requires) return { ok: true, why: "" };
  const rule = DATA.rules[svc.requires];
  const id = svc.requires;
  if (!p) return { ok: null, rule, id, why: "the patient is not verified yet" };
  if (id === "cbct_referral") {
    if (p.referral && p.referral.for === "cbct") return { ok: true, rule, id, why: `referral on file from ${p.referral.from}` };
    const seen = visits(p, cal).filter(([s, d]) => (rule.consult_services ?? []).includes(s) && daysBetween(d, on) >= 0);
    if (seen.length) {
      const [s, d] = seen[0];
      return { ok: true, rule, id, why: `${service(s)?.name ?? s} on ${shortDate(d)} counts as the consultation` };
    }
    return { ok: false, rule, id, why: "no referral on file and no consultation with us" };
  }
  if (id === "opg_recent") {
    const within = rule.within_days ?? 180;
    const recent = visits(p, cal).filter(([s, d]) => s === "opg" && daysBetween(d, on) >= 0 && daysBetween(d, on) <= within);
    if (recent.length) return { ok: true, rule, id, why: `OPG on ${shortDate(recent[0][1])}` };
    return { ok: false, rule, id, why: "no OPG in the last six months" };
  }
  return { ok: true, why: "" };
}

// ─── Cancellation and reschedule terms ───────────────────────────────────────

export interface ChangeTerms {
  allowed: boolean;
  fee: number;
  why: string;
  /** The desk handles it by phone (changed online too often). */
  callback?: boolean;
}

export function changeTerms(a: Appt, cal: Calendar): ChangeTerms {
  const svc = service(a.service);
  if (a.status !== "booked") return { allowed: false, fee: 0, why: "this appointment is already cancelled" };
  const until = cal.minutesUntil(a.date, a.start);
  if (until <= 0) return { allowed: false, fee: 0, why: "this appointment has already started or passed" };
  if (a.changes >= POLICY.online_changes_max) {
    return {
      allowed: false,
      fee: 0,
      callback: true,
      why: `it has already been changed online ${a.changes} times; after ${POLICY.online_changes_max}, the desk arranges it by phone`,
    };
  }
  const hours = until / 60;
  if (svc?.category === "imaging") {
    if (hours >= POLICY.imaging_free_until_hours) {
      return { allowed: true, fee: 0, why: `free: scans can be changed up to ${POLICY.imaging_free_until_hours} hours before` };
    }
    return { allowed: true, fee: POLICY.late_fee, why: `within ${POLICY.imaging_free_until_hours} hours of the scan` };
  }
  if (hours >= POLICY.free_until_hours) return { allowed: true, fee: 0, why: `free: more than ${POLICY.free_until_hours} hours away` };
  if (POLICY.late_fee_waived_for.includes(a.service)) {
    return { allowed: true, fee: 0, why: "the late-change fee is waived for emergency visits" };
  }
  return {
    allowed: true,
    fee: POLICY.late_fee,
    why: `within ${POLICY.free_until_hours} hours: a ${rupees(POLICY.late_fee)} late-change fee`,
  };
}

/** For a root canal's later sitting: the dates it may move to (7–14 days
 *  after the sitting before it). */
export function sittingWindow(a: Appt, cal: Calendar, p: Patient | null | undefined): [string, string] | null {
  const svc = service(a.service);
  if (!svc?.sitting_gap_days || !a.sitting || a.sitting <= 1 || !p) return null;
  let before: string | null = null;
  for (const v of p.history) if (v.service === a.service && v.sitting === a.sitting - 1) before = dateOf(cal.today, v.week, v.day);
  for (const o of cal.ofPatient(p.id)) {
    if (o.service === a.service && o.sitting === a.sitting - 1 && o.status === "booked") before = o.date;
  }
  if (!before) return null;
  return [addDays(before, svc.sitting_gap_days.min), addDays(before, svc.sitting_gap_days.max)];
}
