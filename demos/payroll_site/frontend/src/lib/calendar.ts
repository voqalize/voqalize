/**
 * The sales calendar on /book-demo — the page's twin of
 * backend/calendar_rules.py, both pinned by content/calendar_cases.json.
 * The days are the next `business_days` weekdays after today (IST), holidays
 * skipped; a slot is taken by the rule in content/site.json `calendar.taken_rule`.
 */
import { CALENDAR } from "../data/product";

export interface Slot {
  id: string;
  day: string; // YYYY-MM-DD
  time: string; // HH:MM IST
  rep: string;
  taken: boolean;
}

const KEYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"] as const;
export const REPS = CALENDAR.reps;
export const repById = (id: string) => REPS.find((r) => r.id === id);

const toDate = (iso: string) => {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
};
const iso = (d: Date) => d.toISOString().slice(0, 10);

/** Today's date in IST, as YYYY-MM-DD. */
export function todayIst(now: Date = new Date()): string {
  return iso(new Date(now.getTime() + 330 * 60_000));
}

export function businessDays(today: string): string[] {
  const out: string[] = [];
  const d = toDate(today);
  while (out.length < CALENDAR.business_days) {
    d.setUTCDate(d.getUTCDate() + 1);
    const wd = d.getUTCDay();
    if (wd >= 1 && wd <= 5 && !CALENDAR.holidays.includes(iso(d))) out.push(iso(d));
  }
  return out;
}

export const minutes = (t: string) => {
  const [h, m] = t.split(":").map(Number);
  return h * 60 + m;
};

export function isTaken(day: string, time: string, repIndex: number): boolean {
  const epochDay = Math.round(toDate(day).getTime() / 86_400_000);
  return (epochDay * 3 + Math.floor(minutes(time) / 30) * 7 + repIndex * 11) % 5 === 0;
}

export const slotId = (day: string, time: string, rep: string) => `${day}-${time.replace(":", "")}-${rep}`;

export function slotsOn(day: string): Slot[] {
  const key = KEYS[toDate(day).getUTCDay()];
  const out: Slot[] = [];
  REPS.forEach((rep, i) => {
    for (const t of (rep.hours as Record<string, string[]>)[key] ?? []) {
      out.push({ id: slotId(day, t, rep.id), day, time: t, rep: rep.id, taken: isTaken(day, t, i) });
    }
  });
  return out.sort((a, b) => minutes(a.time) - minutes(b.time) || REPS.findIndex((r) => r.id === a.rep) - REPS.findIndex((r) => r.id === b.rep));
}

export function slotById(id: string): Slot | null {
  const m = /^(\d{4}-\d{2}-\d{2})-(\d{4})-([a-z]+)$/.exec(id.trim());
  if (!m) return null;
  return slotsOn(m[1]).find((s) => s.id === id.trim()) ?? null;
}

export function reference(s: Slot): string {
  const [, mo, d] = s.day.split("-");
  return `TKD-${d}${mo}-${s.time.replace(":", "")}-${repById(s.rep)!.initials}`;
}
