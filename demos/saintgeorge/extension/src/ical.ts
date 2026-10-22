/**
 * The school's public calendar, read in the visitor's browser.
 *
 * The calendar page shows a Google Calendar embed, which a script on the page
 * cannot read (another origin), and the calendar's public iCal feed sends no
 * CORS headers, so the page cannot fetch it either. The extension's service
 * worker can, with a host permission for it (`background.ts`), and parses it
 * here: the brain runs far from Chile and never fetches the site or its
 * calendar itself.
 *
 * Only what Javier says is read: each event's day, its time in Santiago when
 * it has one, and its title. A recurring event counts at its first date only
 * (four of the feed's ~760 events recur, all weekly series long over); a
 * cancelled one is left out.
 */

export const ICAL_URL =
  "https://calendar.google.com/calendar/ical/actividades%40saintgeorge.cl/public/basic.ics";
export const TIMEZONE = "America/Santiago";

export interface CalendarEvent {
  /** The day, in Santiago: `2026-10-27`. */
  date: string;
  /** `19:00` in Santiago, or empty for an all-day event. */
  time: string;
  title: string;
}

interface Parsed extends CalendarEvent {
  /** Santiago's wall clock as a number, for order. */
  key: number;
}

/** The feed's lines, with folded continuation lines joined (RFC 5545 §3.1). */
function lines(text: string): string[] {
  const out: string[] = [];
  for (const raw of text.split(/\r?\n/)) {
    if ((raw.startsWith(" ") || raw.startsWith("\t")) && out.length) out[out.length - 1] += raw.slice(1);
    else if (raw) out.push(raw);
  }
  return out;
}

/** A text value as written, with its escapes undone. */
function unescape(value: string): string {
  return value
    .replace(/\\n/gi, " ")
    .replace(/\\([,;\\])/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

const pad = (n: number) => String(n).padStart(2, "0");

/** A UTC instant's day and time on Santiago's clock. */
function inSantiago(utc: Date, timeZone: string): { date: string; time: string; key: number } {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(utc);
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value ?? 0);
  const [y, m, d, h, mi] = [get("year"), get("month"), get("day"), get("hour"), get("minute")];
  return { date: `${y}-${pad(m)}-${pad(d)}`, time: `${pad(h)}:${pad(mi)}`, key: Date.UTC(y, m - 1, d, h, mi) };
}

/** DTSTART's value, with its parameters: a day, a UTC time, or a local time. */
function start(params: string, value: string, timeZone: string): { date: string; time: string; key: number } | null {
  const m = /^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})(Z)?)?$/.exec(value.trim());
  if (!m) return null;
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  if (!m[4] || /VALUE=DATE(?!-)/i.test(params)) {
    return { date: `${m[1]}-${m[2]}-${m[3]}`, time: "", key: Date.UTC(y, mo - 1, d) };
  }
  const [h, mi, s] = [Number(m[4]), Number(m[5]), Number(m[6])];
  if (m[7]) return inSantiago(new Date(Date.UTC(y, mo - 1, d, h, mi, s)), timeZone);
  // A local time with a TZID: the feed's own zone is Santiago's, as the
  // school's calendar is; it is taken as written.
  return { date: `${m[1]}-${m[2]}-${m[3]}`, time: `${m[4]}:${m[5]}`, key: Date.UTC(y, mo - 1, d, h, mi) };
}

/** Every event in an iCal feed, in no particular order. */
export function parseIcs(text: string, timeZone = TIMEZONE): Parsed[] {
  const out: Parsed[] = [];
  let ev: { start?: ReturnType<typeof start>; title?: string; cancelled?: boolean } | null = null;
  for (const line of lines(text)) {
    if (line === "BEGIN:VEVENT") {
      ev = {};
      continue;
    }
    if (line === "END:VEVENT") {
      if (ev?.start && !ev.cancelled) out.push({ ...ev.start, title: ev.title ?? "" });
      ev = null;
      continue;
    }
    if (!ev) continue;
    const colon = line.indexOf(":");
    if (colon < 0) continue;
    const head = line.slice(0, colon);
    const value = line.slice(colon + 1);
    const [name, ...params] = head.split(";");
    switch (name.toUpperCase()) {
      case "DTSTART":
        ev.start = start(params.join(";"), value, timeZone);
        break;
      case "SUMMARY":
        ev.title = unescape(value);
        break;
      case "STATUS":
        ev.cancelled = value.trim().toUpperCase() === "CANCELLED";
        break;
    }
  }
  return out;
}

/** The next `count` events from today on, in Santiago, soonest first. */
export function upcoming(events: Parsed[], now: Date, count: number, timeZone = TIMEZONE): CalendarEvent[] {
  const today = inSantiago(now, timeZone).date;
  return events
    .filter((e) => e.date >= today && e.title)
    .sort((a, b) => a.key - b.key || a.title.localeCompare(b.title))
    .slice(0, count)
    .map(({ date, time, title }) => ({ date, time, title }));
}

/** Today's date in Santiago. */
export function todayIn(now: Date, timeZone = TIMEZONE): string {
  return inSantiago(now, timeZone).date;
}
