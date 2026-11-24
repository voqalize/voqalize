import { ArrowRight, CalendarClock, Check, PhoneCall, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { DATA, POLICY, aftercareLine, branch, dentist, hhmm, prepLine, priceRange, room, rupees, service, showPhone, time12 } from "../data/clinic";
import { type Appt, addDays, changeTerms, dateOf, longDate, shortDate, sittingWindow, weekdayName } from "../data/slots";
import { Calendar } from "../components/Calendar";
import { CallbackBody } from "../components/CallbackCard";
import { SignIn } from "../components/SignIn";
import { type Callback, actions, inWindow, patientById, signedInPatient, useStore } from "../state/store";

const who = (a: { dentist: string | null; resource: string | null }) =>
  a.dentist ? dentist(a.dentist)?.name : room(a.resource)?.room.label;

function When({ date, start }: { date: string; start: number }) {
  return (
    <>
      {longDate(date)}, {weekdayName(date)} · {time12(hhmm(start))}
    </>
  );
}

function ChangeSheet({ a }: { a: Appt }) {
  const ch = useStore((s) => s.change);
  const cal = useStore((s) => s.cal);
  if (!ch || ch.apptId !== a.id) return null;
  const terms = changeTerms(a, cal);
  const slot = ch.slot;
  const done = ch.done;
  const now = cal.appts.get(a.id)!;
  return (
    <div className={`sheet${done ? " is-done" : ""}`} data-stage-thing="change-sheet" data-stage-label={ch.action === "cancel" ? "Cancellation" : "Reschedule"} role="region" aria-label="Change appointment">
      {done ? (
        <>
          <p className="sheet-title">
            <Check size={17} aria-hidden /> {ch.action === "cancel" ? "Cancelled" : "Moved"}
          </p>
          <p>
            {ch.action === "cancel" ? (
              <>
                {a.id} is cancelled{ch.fee ? `. A ${rupees(ch.fee)} late-change fee is added to your next bill.` : ", free of charge."}
              </>
            ) : (
              <>
                {a.id} is now on <When date={now.date} start={now.start} /> with {who(now)} at {branch(now.branch)?.short}.
                {ch.fee ? ` A ${rupees(ch.fee)} late-change fee applies.` : ""}
              </>
            )}
          </p>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => actions.closeChange()}>
            Close
          </button>
        </>
      ) : (
        <>
          <p className="sheet-title">{ch.action === "cancel" ? "Cancel this appointment?" : "Move this appointment?"}</p>
          <div className="sheet-change">
            <div className={ch.action === "cancel" ? "is-struck" : ""}>
              <span className="small muted">Now</span>
              <strong>
                <When date={a.date} start={a.start} />
              </strong>
              <span className="small">
                {who(a)}, {branch(a.branch)?.short}
              </span>
            </div>
            <ArrowRight size={18} aria-hidden />
            {ch.action === "cancel" ? (
              <div>
                <span className="small muted">After</span>
                <strong>Cancelled</strong>
                <span className="small">The time goes back on the calendar</span>
              </div>
            ) : slot ? (
              <div className="is-new">
                <span className="small muted">New</span>
                <strong>
                  <When date={slot.date} start={slot.start} />
                </strong>
                <span className="small">
                  {slot.dentist ? dentist(slot.dentist)?.name : room(slot.resource)?.room.label}, {branch(slot.branch)?.short}
                </span>
              </div>
            ) : null}
          </div>
          <p className="sheet-policy">
            {terms.allowed ? `${terms.why.replace(/^free: /, "Free: ")}.` : `Not possible online: ${terms.why}.`}{" "}
            <strong>{ch.fee ? `Fee: ${rupees(ch.fee)}` : "No fee"}</strong>
          </p>
          {ch.error ? <p className="form-error">{ch.error}</p> : null}
          <div className="sheet-actions" data-dock-avoid>
            <button type="button" className="btn btn-primary" data-confirm onClick={() => actions.applyChange()} disabled={!terms.allowed}>
              {ch.action === "cancel" ? "Confirm cancellation" : "Confirm new time"}
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => actions.closeChange()}>
              Keep
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function Picker({ a }: { a: Appt }) {
  const p = useStore((s) => s.picker);
  const today = useStore((s) => s.clock.today);
  const cal = useStore((s) => s.cal);
  if (!p || p.apptId !== a.id) return null;
  const svc = service(a.service)!;
  const pat = patientById(a.patient_id);
  const win = sittingWindow(a, cal, pat);
  const subjects = p.focus
    ? [p.focus]
    : svc.resource
      ? DATA.branches.flatMap((b) => b.imaging.filter((r) => r.does.includes(svc.resource!)).map((r) => r.id))
      : (svc.dentists ?? []);
  return (
    <div className="picker">
      <div className="picker-head">
        <p>
          <strong>Choose a new time</strong> for {svc.name.toLowerCase()}. Your current time shows as “Moving”.
          {win ? ` Sitting ${a.sitting} must be between ${shortDate(win[0])} and ${shortDate(win[1])}.` : ""}
        </p>
        <button type="button" className="icon-btn" aria-label="Close the calendar" onClick={() => actions.closePicker()}>
          <X size={16} />
        </button>
      </div>
      <div className="chips">
        {(svc.resource ? [] : (svc.dentists ?? [])).map((id) => (
          <button key={id} type="button" className={`chip${p.focus === id ? " is-on" : ""}`} onClick={() => actions.pickerPatch({ focus: id })}>
            {dentist(id)?.short}
          </button>
        ))}
        {!svc.resource && (svc.dentists?.length ?? 0) > 1 ? (
          <button type="button" className={`chip${!p.focus ? " is-on" : ""}`} onClick={() => actions.pickerPatch({ focus: null })}>
            All
          </button>
        ) : null}
      </div>
      <Calendar
        serviceId={a.service}
        date={p.date}
        view={p.view}
        subjects={subjects}
        weekSubject={p.focus ?? a.dentist ?? a.resource}
        branch={null}
        ignore={a.id}
        allowDate={(d) => inWindow(a, d)}
        minDate={today}
        maxDate={addDays(today, DATA.booking.horizon_days)}
        onPick={(slot) => actions.propose(a.id, "reschedule", slot)}
        onDate={(d) => actions.pickerPatch({ date: d })}
        onView={(v) => actions.pickerPatch({ view: v })}
      />
    </div>
  );
}

function ApptCard({ a }: { a: Appt }) {
  const cal = useStore((s) => s.cal);
  const pulse = useStore((s) => s.pulse);
  const svc = service(a.service)!;
  const terms = changeTerms(a, cal);
  const after = aftercareLine(a.service);
  return (
    <article className={`appt${a.id === pulse ? " is-pulse" : ""}`} data-stage-group data-stage-thing={`appt-${a.id}`} data-stage-label={a.id}>
      <div className="appt-date" aria-hidden>
        <span>{shortDate(a.date).split(" ")[0]}</span>
        <strong>{a.date.slice(8)}</strong>
        <span>{shortDate(a.date).split(" ")[2]}</span>
      </div>
      <div className="appt-body">
        <p className="appt-id">
          {a.id}
          {a.sitting ? <span className="tag">Sitting {a.sitting} of {svc.sittings}</span> : null}
          {a.changes ? <span className="tag tag-muted">Changed {a.changes}×</span> : null}
        </p>
        <h3>{svc.name}</h3>
        <p className="appt-when">
          <When date={a.date} start={a.start} /> – {time12(hhmm(a.start + a.duration_min))}
        </p>
        <p className="small">
          {who(a)} · {branch(a.branch)?.name} · {priceRange(svc)}
        </p>
        <dl className="appt-notes">
          <div>
            <dt>Before</dt>
            <dd>{prepLine(a.service)}</dd>
          </div>
          {after ? (
            <div>
              <dt>After</dt>
              <dd>{after}</dd>
            </div>
          ) : null}
        </dl>
        <div className="appt-actions">
          <button type="button" className="btn btn-ghost btn-sm" disabled={!terms.allowed} onClick={() => actions.openPicker(a.id)}>
            <CalendarClock size={15} aria-hidden /> Reschedule
          </button>
          <button type="button" className="btn btn-ghost btn-sm btn-danger" disabled={!terms.allowed} onClick={() => actions.propose(a.id, "cancel", null)}>
            Cancel
          </button>
          <span className="small muted">
            {terms.allowed ? (terms.fee ? `A change now costs ${rupees(terms.fee)}` : "Free to change") : `Call the desk: ${terms.why}`}
          </span>
        </div>
        <ChangeSheet a={a} />
      </div>
      <Picker a={a} />
    </article>
  );
}

function CallbackForm() {
  const me = signedInPatient();
  const [reason, setReason] = useState("");
  const [urgency, setUrgency] = useState<Callback["urgency"]>("today");
  const [phone, setPhone] = useState(me ? showPhone(me.phone) : "");
  const callbacks = useStore((s) => s.callbacks);
  const mine = callbacks.filter((c) => !me || c.patient_id === me.id || c.phone === me.phone).slice().reverse();
  return (
    <section className="panel" data-stage-thing="callback-form" data-stage-label="Request a callback">
      <div className="panel-head">
        <PhoneCall size={18} aria-hidden />
        <h3>Request a callback from a dentist</h3>
      </div>
      <p className="small muted">For pain, swelling, medicines or anything clinical. Our front desk does not give medical advice. {DATA.clinical.red_flags}</p>
      <form
        className="cb-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (!reason.trim()) return;
          actions.requestCallback({ reason: reason.trim(), urgency, phone });
          setReason("");
        }}
      >
        <label className="field">
          <span>What should the dentist call about?</span>
          <textarea name="reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Swelling since the extraction on Monday" />
        </label>
        <div className="cb-row">
          <label className="field">
            <span>How soon</span>
            <select value={urgency} onChange={(e) => setUrgency(e.target.value as Callback["urgency"])}>
              <option value="urgent">Urgent ({DATA.clinical.callback_windows.urgent})</option>
              <option value="today">Today ({DATA.clinical.callback_windows.today})</option>
              <option value="routine">Routine ({DATA.clinical.callback_windows.routine})</option>
            </select>
          </label>
          <label className="field">
            <span>Phone</span>
            <input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="numeric" />
          </label>
        </div>
        <button type="submit" className="btn btn-primary" data-dock-avoid disabled={!reason.trim()}>
          Request callback
        </button>
      </form>
      {mine.length ? (
        <ul className="cb-list">
          {mine.map((c) => (
            <li key={c.id} className="cb-item">
              <CallbackBody cb={c} />
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function PastVisits({ pid }: { pid: string }) {
  const cal = useStore((s) => s.cal);
  const p = patientById(pid)!;
  const history = p.history.map((v) => ({ key: `${v.service}${v.week}${v.day}`, service: v.service, date: dateOf(cal.today, v.week, v.day), start: v.start, dentist: v.dentist ?? null, branch: v.branch, sitting: v.sitting }));
  const past = cal
    .ofPatient(pid)
    .filter((a) => a.status === "booked" && cal.minutesUntil(a.date, a.start) <= 0)
    .map((a) => ({ key: a.id, service: a.service, date: a.date, start: hhmm(a.start), dentist: a.dentist, branch: a.branch, sitting: a.sitting ?? undefined }));
  const rows = [...history, ...past].sort((x, y) => (x.date < y.date ? 1 : -1));
  const cancelled = cal.ofPatient(pid).filter((a) => a.status === "cancelled");
  return (
    <section className="panel" data-stage-thing="past-visits" data-stage-label="Past visits">
      <h3>Past visits</h3>
      {rows.length ? (
        <ul className="past">
          {rows.map((r) => (
            <li key={r.key}>
              <strong>{service(r.service)?.name}{r.sitting ? `, sitting ${r.sitting}` : ""}</strong>
              <span className="small muted">
                {longDate(r.date)} · {r.dentist ? dentist(r.dentist)?.short : "Imaging"} · {branch(r.branch)?.short}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="small muted">No visits with us yet.</p>
      )}
      {cancelled.length ? (
        <>
          <h4>Cancelled</h4>
          <ul className="past">
            {cancelled.map((a) => (
              <li key={a.id}>
                <strong className="is-struck">{service(a.service)?.name}</strong>
                <span className="small muted">
                  {a.id} · {longDate(a.date)}
                </span>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}

export function MyAppointments() {
  const signedIn = useStore((s) => s.signedIn);
  const cal = useStore((s) => s.cal);
  const change = useStore((s) => s.change);
  const me = signedInPatient();
  if (!signedIn || !me) {
    return (
      <div data-page="my-appointments" className="wrap appts-page">
        <header className="page-head">
          <h1>My appointments</h1>
          <p className="muted">Sign in with the mobile number you booked with to see, move or cancel your visits.</p>
        </header>
        <div className="appts-signin">
          <SignIn />
          <aside className="panel policy-aside">
            <h3>Changing a visit</h3>
            <p className="small">{POLICY.text}</p>
            <p className="small muted">{POLICY.rct_text}</p>
          </aside>
        </div>
      </div>
    );
  }
  const upcoming = cal.upcoming(me.id);
  // A card whose change just finished stays on screen with its result.
  const changed = change?.done ? cal.appts.get(change.apptId) : undefined;
  const cards = changed && !upcoming.some((a) => a.id === changed.id) ? [...upcoming, changed] : upcoming;
  return (
    <div data-page="my-appointments" className="wrap appts-page">
      <header className="page-head appts-head">
        <div>
          <h1>My appointments</h1>
          <p className="muted">
            {me.name} · Patient ID {me.id} · +91 {showPhone(me.phone)}
          </p>
        </div>
        <Link to="/book" className="btn btn-primary">
          Book another visit
        </Link>
      </header>
      <div className="appts-grid">
        <section className="appts-list" data-stage-thing="appointments" data-stage-label="Upcoming appointments" aria-label="Upcoming appointments">
          <h2 className="list-title">Upcoming ({upcoming.length})</h2>
          {cards.length ? (
            cards.map((a) => <ApptCard key={a.id} a={a} />)
          ) : (
            <div className="panel empty">
              <p>No upcoming appointments.</p>
              <Link to="/book" className="btn btn-primary btn-sm">
                Book a visit
              </Link>
            </div>
          )}
          <p className="small muted policy-line">{POLICY.text}</p>
        </section>
        <aside className="appts-rail">
          <CallbackForm />
          <PastVisits pid={me.id} />
        </aside>
      </div>
    </div>
  );
}
