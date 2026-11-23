import { CalendarCheck, Clock } from "lucide-react";
import { useMemo, useState } from "react";
import { BRAND, CALENDAR, SITE } from "../data/product";
import { businessDays, minutes, repById, slotById, slotsOn, todayIst } from "../lib/calendar";
import { dmy, time12, weekday } from "../lib/format";
import { actions, type BookingField, isEmail, useSite } from "../state/store";

const PARTS: { id: string; label: string; test: (m: number) => boolean }[] = [
  { id: "morning", label: "Morning", test: (m) => m < 12 * 60 },
  { id: "afternoon", label: "Afternoon", test: (m) => m >= 12 * 60 && m < 16 * 60 },
  { id: "evening", label: "Evening", test: (m) => m >= 16 * 60 },
];

export function BookDemo() {
  const p = SITE.book_page;
  const booking = useSite((s) => s.booking);
  return (
    <div className="page book-page">
      <header className="page-head wrap">
        <h1>{p.title}</h1>
        <p className="page-intro">{p.intro}</p>
      </header>
      <section className="section section-tight">
        <div className="wrap book-grid">
          <Calendar />
          {booking.status === "confirmed" ? <Confirmation /> : <BookingForm />}
        </div>
      </section>
    </div>
  );
}

function Calendar() {
  const days = useMemo(() => businessDays(todayIst()), []);
  const booking = useSite((s) => s.booking);
  const booked = useSite((s) => s.booked);
  const day = days.includes(booking.day) ? booking.day : days[0];
  const slots = slotsOn(day);
  const free = (d: string) => slotsOn(d).filter((s) => !s.taken && !booked.includes(s.id)).length;
  const locked = booking.status === "confirmed";
  return (
    <div className="calendar" data-stage-thing="calendar" data-stage-label="Calendar">
      <div className="cal-head">
        <h2 className="h-small">Pick a day</h2>
        <p className="cal-tz">
          <Clock size={14} /> {CALENDAR.slot_minutes} minutes, times in {CALENDAR.tz_label}
        </p>
      </div>
      <div className="day-strip" role="tablist" aria-label="Days" data-stage-group="days">
        {days.map((d) => {
          const n = free(d);
          return (
            <button
              type="button"
              role="tab"
              key={d}
              aria-selected={d === day}
              className={`day${d === day ? " is-on" : ""}`}
              data-stage-part={`day:${d}`}
              data-stage-label={dmy(d)}
              onClick={() => actions.pickDay(d)}
            >
              <span className="day-wd">{weekday(d)}</span>
              <span className="day-d num">{Number(d.slice(8))}</span>
              <span className="day-m">{dmy(d).slice(3, 6)}</span>
              <span className="day-free">{n ? `${n} free` : "Full"}</span>
            </button>
          );
        })}
      </div>
      <div className="cal-day" data-stage-group="slots">
        <p className="cal-date">
          {weekday(day)}, {dmy(day)}
        </p>
        <div className="slot-parts">
          {PARTS.map((part) => {
            const list = slots.filter((s) => part.test(minutes(s.time)));
            if (!list.length) return null;
            return (
              <div key={part.id} className="slot-part">
                <h3 className="slot-part-h">{part.label}</h3>
                <div className="slots">
                  {list.map((s) => {
                    const rep = repById(s.rep)!;
                    const taken = s.taken || booked.includes(s.id);
                    const on = booking.slotId === s.id;
                    return (
                      <button
                        type="button"
                        key={s.id}
                        className={`slot${on ? " is-on" : ""}${taken ? " is-taken" : ""}`}
                        disabled={taken || locked}
                        aria-pressed={on}
                        data-stage-part={`slot:${s.id}`}
                        data-stage-label={`${time12(s.time)} with ${rep.name}`}
                        onClick={() => actions.pickSlot(s.id)}
                      >
                        <span className="slot-time num">{time12(s.time)}</span>
                        <span className="slot-rep">
                          <span className="rep-dot" aria-hidden>
                            {rep.initials}
                          </span>
                          {taken ? "Taken" : rep.name.split(" ")[0]}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <div className="reps">
        {CALENDAR.reps.map((r) => (
          <div key={r.id} className="rep">
            <span className="rep-dot rep-dot-lg" aria-hidden>
              {r.initials}
            </span>
            <div>
              <strong>{r.name}</strong>
              <span>
                {r.title}, {r.city}
              </span>
              <span className="rep-focus">{r.focus}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const FIELDS: { id: BookingField; label: string; type?: string; placeholder: string }[] = [
  { id: "name", label: "Your name", placeholder: "Full name" },
  { id: "company", label: "Company", placeholder: "Company name" },
  { id: "headcount", label: "Employees", type: "number", placeholder: "How many people" },
  { id: "email", label: "Work email", type: "email", placeholder: "name@company.in" },
];

function BookingForm() {
  const booking = useSite((s) => s.booking);
  const [tried, setTried] = useState<string[]>([]);
  const slot = booking.slotId ? slotById(booking.slotId) : null;
  const rep = slot ? repById(slot.rep) : null;
  const missing = tried.length ? actions.bookingMissing() : [];
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const r = actions.confirmBooking();
    if ("missing" in r) setTried(r.missing);
  };
  return (
    <form className="book-form" data-stage-group="booking-form" data-stage-thing="booking-form" data-stage-label="Booking form" onSubmit={submit} noValidate>
      <h2 className="h-small">Your details</h2>
      <div className={`picked${slot ? " is-set" : ""}`}>
        {slot && rep ? (
          <>
            <CalendarCheck size={20} />
            <div>
              <strong>
                {weekday(slot.day)}, {dmy(slot.day)} at {time12(slot.time)} IST
              </strong>
              <span>
                With {rep.name}, {rep.title.toLowerCase()}
              </span>
            </div>
          </>
        ) : (
          <span>Pick a slot on the calendar.</span>
        )}
      </div>
      {missing.includes("slot") ? <p className="field-err">Choose a free slot first.</p> : null}
      {FIELDS.map((f) => (
        <label key={f.id} className="field" data-stage-part={`booking:${f.id}`}>
          <span className="field-label">{f.label}</span>
          <input
            type={f.type ?? "text"}
            inputMode={f.type === "number" ? "numeric" : undefined}
            autoComplete={f.id === "email" ? "email" : f.id === "name" ? "name" : f.id === "company" ? "organization" : undefined}
            value={booking.form[f.id]}
            placeholder={f.placeholder}
            aria-invalid={missing.includes(f.id) || undefined}
            onChange={(e) => actions.setBookingField(f.id, e.target.value)}
          />
          {missing.includes(f.id) ? (
            <span className="field-err">{f.id === "email" ? (booking.form.email && !isEmail(booking.form.email) ? "That email is not complete." : "Add your work email.") : `Add your ${f.label.toLowerCase()}.`}</span>
          ) : null}
        </label>
      ))}
      <label className="field" data-stage-part="booking:topic">
        <span className="field-label">What should we cover?</span>
        <select value={booking.form.topic} onChange={(e) => actions.setBookingField("topic", e.target.value)}>
          {SITE.book_page.topics.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label}
            </option>
          ))}
        </select>
      </label>
      <button type="submit" className="btn btn-primary btn-lg btn-block" data-stage-part="booking:confirm" data-dock-avoid>
        Confirm booking
      </button>
      <p className="fine">We use your email only to send the invite. {BRAND.name} is a demo; no email is sent.</p>
    </form>
  );
}

function Confirmation() {
  const booking = useSite((s) => s.booking);
  const slot = slotById(booking.slotId)!;
  const rep = repById(slot.rep)!;
  const topic = SITE.book_page.topics.find((t) => t.id === booking.form.topic)?.label;
  return (
    <div className="confirm" data-stage-thing="booking-confirmed" data-stage-label="Booking confirmed" role="status">
      <CalendarCheck size={28} />
      <h2>Your demo is booked</h2>
      <p className="confirm-ref">
        Reference <span className="num">{booking.reference}</span>
      </p>
      <dl>
        <div>
          <dt>When</dt>
          <dd>
            {weekday(slot.day)}, {dmy(slot.day)}, {time12(slot.time)} IST
          </dd>
        </div>
        <div>
          <dt>With</dt>
          <dd>
            {rep.name}, {rep.title.toLowerCase()}
          </dd>
        </div>
        <div>
          <dt>For</dt>
          <dd>
            {booking.form.name}, {booking.form.company}
          </dd>
        </div>
        {topic ? (
          <div>
            <dt>Topic</dt>
            <dd>{topic}</dd>
          </div>
        ) : null}
      </dl>
      <p>{SITE.book_page.after}</p>
      <button type="button" className="btn btn-ghost" onClick={() => actions.newBooking()}>
        Book another slot
      </button>
    </div>
  );
}
