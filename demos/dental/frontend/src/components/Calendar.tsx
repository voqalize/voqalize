/**
 * The dentist (or imaging room) calendar: day view with one column per
 * dentist or room, week view with one column per day for one of them. A
 * 15-minute grid from 09:00 to 20:00: working sessions white, the rest
 * hatched, other patients' appointments grey "Booked", the signed-in
 * patient's in the brand colour, and every free start time for the chosen
 * service a button. Everything comes from the store's calendar, so a move
 * that books or moves something shows here at once.
 */
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import { DAYS, branch, dentist, hhmm, minutes, room, service } from "../data/clinic";
import { type Appt, type Slot, addDays, apptEnd, longDate, mondayOf, shortDate, weekdayOf } from "../data/slots";
import { type View, useStore } from "../state/store";

const START = 9 * 60;
const END = 20 * 60;
const STEP = 15;
const ROWS = (END - START) / STEP;

interface Band {
  start: number;
  end: number;
  branch: string;
  other: boolean;
}

export interface CalendarProps {
  serviceId: string | null;
  date: string;
  view: View;
  /** Day view: the dentists or rooms side by side. */
  subjects: string[];
  /** Week view: whose week. */
  weekSubject: string | null;
  branch: string | null;
  /** The appointment being moved: its own time counts as free. */
  ignore?: string | null;
  hold?: Slot | null;
  allowDate?: (date: string) => boolean;
  onPick: (slot: Slot) => void;
  onDate: (date: string) => void;
  onView: (view: View) => void;
  title?: ReactNode;
  /** Days the arrows may reach. */
  minDate?: string;
  maxDate?: string;
}

const isRoom = (id: string) => !!room(id);

function subjectName(id: string): string {
  const d = dentist(id);
  if (d) return d.name;
  const r = room(id);
  return r ? `${r.room.label}, ${r.branch.short}` : id;
}

function bands(subject: string, date: string, filter: string | null): Band[] {
  const day = weekdayOf(date);
  const d = dentist(subject);
  if (d) {
    return (d.schedule[day] ?? []).map((s) => ({
      start: minutes(s.start),
      end: minutes(s.end),
      branch: s.branch ?? "",
      other: !!filter && s.branch !== filter,
    }));
  }
  const r = room(subject);
  if (!r || !r.branch.open_days.includes(day)) return [];
  return r.room.sessions.map((s) => ({ start: minutes(s.start), end: minutes(s.end), branch: r.branch.id, other: false }));
}

const holdsSubject = (a: Appt, subject: string) => a.dentist === subject || a.resource === subject || a.chair === subject;
const y = (m: number, row: number) => ((m - START) / STEP) * row;

function Column({
  subject,
  date,
  row,
  props,
  freeBy,
}: {
  subject: string;
  date: string;
  row: number;
  props: CalendarProps;
  freeBy: Map<string, Slot[]>;
}) {
  const cal = useStore((s) => s.cal);
  const me = useStore((s) => s.signedIn);
  const pulse = useStore((s) => s.pulse);
  const clock = useStore((s) => s.clock);
  const svc = service(props.serviceId);
  const appts = cal.on(date).filter((a) => a.status === "booked" && holdsSubject(a, subject));
  const free = freeBy.get(`${subject}|${date}`) ?? [];
  const held = props.hold && props.hold.date === date && (props.hold.dentist ?? props.hold.resource) === subject ? props.hold : null;
  const isToday = date === clock.today;
  const past = date < clock.today ? END : isToday ? Math.min(END, Math.max(START, clock.minute)) : START;
  const dur = svc?.duration_min ?? 15;
  return (
    <div className="cal-col" style={{ height: ROWS * row }} data-col={`${subject}|${date}`}>
      {bands(subject, date, props.branch).map((b) => (
        <div
          key={`${b.start}`}
          className={`cal-band${b.other ? " is-other" : ""}`}
          style={{ top: y(b.start, row), height: y(b.end, row) - y(b.start, row) }}
        >
          {b.other ? <span>At {branch(b.branch)?.short}</span> : null}
        </div>
      ))}
      {past > START ? <div className="cal-past" style={{ height: y(past, row) }} aria-hidden /> : null}
      {free.map((s) => {
        const style = { top: y(s.start, row), height: row, "--span": `${(dur / STEP) * row}px` } as CSSProperties;
        return (
          <button
            key={s.start}
            type="button"
            className="cal-free"
            style={style}
            data-slot={`${s.date} ${s.time}`}
            data-subject={subject}
            aria-label={`Free at ${s.time} on ${shortDate(s.date)} with ${subjectName(subject)}`}
            onClick={() => props.onPick(s)}
          >
            <span>{s.time}</span>
          </button>
        );
      })}
      {appts.map((a) => {
        const own = !!me && a.patient_id === me;
        const moving = a.id === props.ignore;
        const h = y(apptEnd(a), row) - y(a.start, row);
        return (
          <div
            key={a.id}
            className={`cal-appt${own ? " is-own" : ""}${moving ? " is-moving" : ""}${a.id === pulse ? " is-pulse" : ""}${h < 26 ? " is-short" : ""}`}
            style={{ top: y(a.start, row), height: h }}
            data-appt={a.id}
            title={own ? `${service(a.service)?.name}, ${hhmm(a.start)}` : "Booked"}
          >
            {own ? (
              <>
                <strong>{moving ? "Moving: your appointment" : "Your appointment"}</strong>
                <span>
                  {service(a.service)?.name} · {hhmm(a.start)}–{hhmm(apptEnd(a))} · {a.id}
                </span>
              </>
            ) : (
              <span>Booked</span>
            )}
          </div>
        );
      })}
      {held ? (
        <div className="cal-held" style={{ top: y(held.start, row), height: (dur / STEP) * row }} data-held>
          <strong>Held for you</strong>
          <span>
            {held.time}–{hhmm(held.start + dur)}
          </span>
        </div>
      ) : null}
      {isToday && clock.minute > START && clock.minute < END ? (
        <div className="cal-now" style={{ top: y(clock.minute, row) }} aria-hidden>
          <span />
        </div>
      ) : null}
    </div>
  );
}

function Head({ subject, date, view }: { subject: string; date: string; view: View }) {
  const bs = bands(subject, date, null);
  const where = [...new Set(bs.map((b) => branch(b.branch)?.short))].join(", ");
  if (view === "week") {
    const sun = weekdayOf(date) === "sun";
    return (
      <div className="cal-head">
        <strong>
          {shortDate(date).split(" ").slice(0, 2).join(" ")}
        </strong>
        <span>{sun ? "Closed" : bs.length ? where : "Not in"}</span>
      </div>
    );
  }
  const d = dentist(subject);
  const r = room(subject);
  return (
    <div className="cal-head">
      <span className="cal-avatar" aria-hidden>
        {d ? d.initials : "XR"}
      </span>
      <span className="cal-head-text">
        <strong>{d ? d.short : r?.room.label}</strong>
        <span>
          {bs.length ? (
            <>
              {where}
              <br />
              {hhmm(bs[0].start)}–{hhmm(bs[bs.length - 1].end)}
            </>
          ) : weekdayOf(date) === "sun" ? (
            "Closed Sundays"
          ) : (
            "Not in today"
          )}
        </span>
      </span>
    </div>
  );
}

/** "16 – 22 Nov 2026" (or "30 Nov – 6 Dec 2026"). */
function weekLabel(monday: string): string {
  const a = longDate(monday).split(" ");
  const b = longDate(addDays(monday, 6)).split(" ");
  return a[1] === b[1] ? `${Number(a[0])} – ${Number(b[0])} ${b[1]} ${b[2]}` : `${Number(a[0])} ${a[1]} – ${Number(b[0])} ${b[1]} ${b[2]}`;
}

export function Calendar(props: CalendarProps) {
  const cal = useStore((s) => s.cal);
  const today = useStore((s) => s.clock.today);
  const svc = service(props.serviceId);
  const week = props.view === "week";
  const row = week ? 15 : 18;
  const weekSubject = props.weekSubject ?? props.subjects[0] ?? null;
  const cols: { subject: string; date: string }[] = week
    ? weekSubject
      ? DAYS.map((_, i) => ({ subject: weekSubject, date: addDays(mondayOf(props.date), i) }))
      : []
    : props.subjects.map((subject) => ({ subject, date: props.date }));

  // Free start times per column, from the engine.
  const freeBy = new Map<string, Slot[]>();
  if (svc) {
    for (const c of cols) {
      if (props.allowDate && !props.allowDate(c.date)) continue;
      const roomCol = isRoom(c.subject);
      if (roomCol !== !!svc.resource) continue;
      if (!roomCol && !svc.dentists?.includes(c.subject)) continue;
      const got = cal
        .slots(svc, c.date, { branch: props.branch, dentist: roomCol ? null : c.subject, ignore: props.ignore })
        .filter((s) => (s.dentist ?? s.resource) === c.subject);
      freeBy.set(`${c.subject}|${c.date}`, got);
    }
  }
  const freeCount = [...freeBy.values()].reduce((n, l) => n + l.length, 0);
  const stepDays = week ? 7 : 1;
  const canPrev = !props.minDate || addDays(props.date, -stepDays) >= (week ? mondayOf(props.minDate) : props.minDate);
  const canNext = !props.maxDate || addDays(props.date, stepDays) <= props.maxDate || (week && mondayOf(addDays(props.date, 7)) <= props.maxDate);
  const label = week ? weekLabel(mondayOf(props.date)) : `${shortDate(props.date).split(" ")[0]}, ${longDate(props.date)}`;

  return (
    <section className={`cal is-${props.view}${!week && cols.length > 3 ? " is-many" : ""}`} data-stage-thing="calendar" data-stage-label="Calendar" aria-label="Appointment calendar">
      <div className="cal-bar">
        <div className="cal-title">
          {props.title ?? <strong>{week && weekSubject ? subjectName(weekSubject) : "Calendar"}</strong>}
          <span className="muted small">
            {svc ? (freeCount ? `${freeCount} free start time${freeCount === 1 ? "" : "s"} for ${svc.name.toLowerCase()}` : `No free times for ${svc.name.toLowerCase()} here`) : "Choose a service to see free times"}
          </span>
        </div>
        <div className="cal-nav">
          <button type="button" className="icon-btn" aria-label={week ? "Previous week" : "Previous day"} disabled={!canPrev} onClick={() => props.onDate(addDays(props.date, -stepDays))}>
            <ChevronLeft size={18} />
          </button>
          <span className="cal-date" aria-live="polite">
            {label}
          </span>
          <button type="button" className="icon-btn" aria-label={week ? "Next week" : "Next day"} disabled={!canNext} onClick={() => props.onDate(addDays(props.date, stepDays))}>
            <ChevronRight size={18} />
          </button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => props.onDate(weekdayOf(today) === "sun" ? addDays(today, 1) : today)}>
            Today
          </button>
          <div className="seg" role="radiogroup" aria-label="Calendar view">
            {(["day", "week"] as View[]).map((v) => (
              <button key={v} type="button" role="radio" aria-checked={props.view === v} className={props.view === v ? "is-on" : ""} onClick={() => props.onView(v)}>
                {v === "day" ? "Day" : "Week"}
              </button>
            ))}
          </div>
        </div>
      </div>
      {cols.length ? (
        <div className="cal-scroll">
          <div className="cal-grid" style={{ "--cols": cols.length } as CSSProperties}>
            <div className="cal-corner" />
            {cols.map((c) => (
              <div key={`h${c.subject}${c.date}`} className={`cal-headcell${c.date === today ? " is-today" : ""}`}>
                <Head subject={c.subject} date={c.date} view={props.view} />
              </div>
            ))}
            <div className="cal-gutter" style={{ height: ROWS * row }}>
              {Array.from({ length: (END - START) / 60 }, (_, i) => (
                <span key={i} style={{ top: i * 4 * row }}>
                  {String(9 + i).padStart(2, "0")}:00
                </span>
              ))}
            </div>
            {cols.map((c) => (
              <Column key={`${c.subject}${c.date}`} subject={c.subject} date={c.date} row={row} props={props} freeBy={freeBy} />
            ))}
          </div>
        </div>
      ) : (
        <p className="cal-empty">No dentist matches this choice. Try any branch or any dentist.</p>
      )}
      <ul className="cal-legend" aria-label="Legend">
        <li>
          <i className="lg-free" /> Free start time
        </li>
        <li>
          <i className="lg-booked" /> Booked
        </li>
        <li>
          <i className="lg-own" /> Your appointment
        </li>
        <li>
          <i className="lg-off" /> Not working
        </li>
      </ul>
    </section>
  );
}
