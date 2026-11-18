import { CalendarCheck2, Check, Info, Layers, Lock } from "lucide-react";
import { Link } from "react-router-dom";
import {
  type Branch,
  CATEGORY_LABEL,
  type Category,
  DATA,
  type Service,
  branch,
  daysAt,
  dentist,
  durationText,
  hhmm,
  prepLine,
  priceRange,
  room,
  service,
  time12,
} from "../data/clinic";
import { type Slot, addDays, checkRule, longDate, weekdayName } from "../data/slots";
import { Calendar } from "../components/Calendar";
import { SignIn } from "../components/SignIn";
import { type BookUi, actions, signedInPatient, useStore } from "../state/store";

const CATS: Category[] = ["appointment", "procedure", "imaging"];

export function branchesFor(svc: Service | undefined): Branch[] {
  if (!svc) return DATA.branches;
  if (svc.resource) return DATA.branches.filter((b) => b.imaging.some((r) => r.does.includes(svc.resource!)));
  return DATA.branches.filter((b) => (svc.dentists ?? []).some((id) => daysAt(dentist(id)!, b.id)));
}

/** The calendar's columns for the booking page's choice. */
export function subjectsFor(b: BookUi): string[] {
  if (b.focus) return [b.focus];
  const svc = service(b.service);
  if (svc?.resource) {
    if (b.resource) return [b.resource];
    return DATA.branches
      .filter((br) => !b.branch || br.id === b.branch)
      .flatMap((br) => br.imaging.filter((r) => r.does.includes(svc.resource!)).map((r) => r.id));
  }
  const pool = svc ? (svc.dentists ?? []) : DATA.dentists.map((d) => d.id);
  return pool.filter((id) => (!b.dentist || id === b.dentist) && (!b.branch || daysAt(dentist(id)!, b.branch)));
}

function ruleBadges(s: Service): string[] {
  const out: string[] = [];
  if (s.same_day) out.push("Same day");
  if (s.sittings && s.sittings > 1) out.push(`${s.sittings} sittings, ${s.sitting_gap_days?.min}–${s.sitting_gap_days?.max} days apart`);
  if (s.requires === "cbct_referral") out.push("Needs a referral or consultation");
  if (s.requires === "opg_recent") out.push("Needs an OPG from the last 6 months");
  if (s.resource && s.resource !== "iopa") out.push("Indiranagar only");
  if (s.id === "whitening") out.push("Indiranagar only");
  return out;
}

function ServiceStep() {
  const b = useStore((s) => s.book);
  return (
    <section className="step" data-stage-thing="service-list" data-stage-label="Services">
      <h2 className="step-title">
        <span className="step-n">1</span> Choose a service
      </h2>
      <div className="tabs" role="tablist" aria-label="Service type">
        {CATS.map((c) => (
          <button key={c} type="button" role="tab" aria-selected={b.tab === c} className={b.tab === c ? "is-on" : ""} onClick={() => actions.setTab(c)}>
            {CATEGORY_LABEL[c]}
          </button>
        ))}
      </div>
      <div className="svc-cards" role="tabpanel">
        {DATA.services
          .filter((s) => s.category === b.tab)
          .map((s) => {
            const on = b.service === s.id;
            return (
              <button
                key={s.id}
                type="button"
                className={`svc-card${on ? " is-on" : ""}`}
                aria-pressed={on}
                data-service={s.id}
                onClick={() => actions.selectService(on ? null : s.id)}
              >
                <span className="svc-card-top">
                  <strong>{s.name}</strong>
                  {on ? <Check size={16} aria-hidden /> : null}
                </span>
                <span className="svc-card-meta">
                  <span className="price">{priceRange(s)}</span>
                  <span>{durationText(s.duration_min)}</span>
                </span>
                <span className="svc-card-sum">{s.summary}</span>
                {ruleBadges(s).length ? (
                  <span className="badges">
                    {ruleBadges(s).map((t) => (
                      <span key={t} className="badge">
                        {t}
                      </span>
                    ))}
                  </span>
                ) : null}
              </button>
            );
          })}
      </div>
      {b.service && service(b.service)?.requires ? (
        <p className="rule-note">
          <Info size={15} aria-hidden /> {DATA.rules[service(b.service)!.requires!].text}
        </p>
      ) : null}
      {b.service === "rct" ? (
        <p className="rule-note">
          <Layers size={15} aria-hidden /> {DATA.rules.rct_sittings.text}
        </p>
      ) : null}
    </section>
  );
}

function WhoStep() {
  const b = useStore((s) => s.book);
  const svc = service(b.service);
  const brs = branchesFor(svc);
  const dentists = svc?.resource ? [] : (svc?.dentists ?? DATA.dentists.map((d) => d.id)).filter((id) => !b.branch || daysAt(dentist(id)!, b.branch));
  const rooms = svc?.resource
    ? DATA.branches.filter((br) => !b.branch || br.id === b.branch).flatMap((br) => br.imaging.filter((r) => r.does.includes(svc.resource!)).map((r) => ({ r, br })))
    : [];
  return (
    <section className="step" data-stage-thing="choose" data-stage-label="Branch and dentist">
      <h2 className="step-title">
        <span className="step-n">2</span> Branch and {svc?.resource ? "imaging room" : "dentist"}
      </h2>
      <div className="chips" role="radiogroup" aria-label="Branch">
        <button type="button" role="radio" aria-checked={!b.branch} className={`chip${!b.branch ? " is-on" : ""}`} onClick={() => actions.selectBranch(null)}>
          Any branch
        </button>
        {brs.map((br) => (
          <button
            key={br.id}
            type="button"
            role="radio"
            aria-checked={b.branch === br.id}
            data-branch={br.id}
            className={`chip${b.branch === br.id ? " is-on" : ""}`}
            onClick={() => actions.selectBranch(br.id)}
          >
            {br.short}
          </button>
        ))}
      </div>
      {svc?.resource ? (
        <div className="who-list">
          {rooms.map(({ r, br }) => (
            <button
              key={r.id}
              type="button"
              className={`who${b.resource === r.id ? " is-on" : ""}`}
              data-resource={r.id}
              onClick={() => actions.selectResource(b.resource === r.id ? null : r.id)}
            >
              <span className="who-mono">XR</span>
              <span>
                <strong>{r.label}</strong>
                <span className="small muted">
                  {br.short} · Mon–Sat {r.sessions.map((s) => `${s.start}–${s.end}`).join(", ")}
                </span>
              </span>
            </button>
          ))}
        </div>
      ) : (
        <div className="who-list">
          <button type="button" className={`who${!b.dentist ? " is-on" : ""}`} onClick={() => actions.selectDentist(null)}>
            <span className="who-mono who-any">All</span>
            <span>
              <strong>Any available dentist</strong>
              <span className="small muted">See everyone's free times side by side</span>
            </span>
          </button>
          {dentists.map((id) => {
            const d = dentist(id)!;
            const at = (b.branch ? [branch(b.branch)!] : DATA.branches).map((br) => [br.short, daysAt(d, br.id)]).filter(([, days]) => days);
            return (
              <button key={id} type="button" className={`who${b.dentist === id ? " is-on" : ""}`} data-dentist={id} onClick={() => actions.selectDentist(b.dentist === id ? null : id)}>
                <span className="who-mono">{d.initials}</span>
                <span>
                  <strong>{d.name}</strong>
                  <span className="small muted">
                    {d.role} · {at.map(([s, days]) => `${s} ${days}`).join("; ")}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}

function slotWho(s: Slot) {
  return s.dentist ? dentist(s.dentist)!.name : `${room(s.resource)?.room.label}`;
}

function Summary() {
  const b = useStore((s) => s.book);
  const cal = useStore((s) => s.cal);
  useStore((s) => s.signedIn);
  const me = signedInPatient();
  const wanted = useStore((s) => s.signin.wanted);
  const hold = b.hold;
  if (b.confirmed) return <Confirmation />;
  if (!hold) {
    return (
      <section className="panel summary-empty" data-stage-thing="summary" data-stage-label="Booking summary">
        <CalendarCheck2 size={22} aria-hidden />
        <h3>{b.service ? "Pick a free time" : "Your booking"}</h3>
        <p className="small muted">
          {b.service
            ? "Click any free start time on the calendar to hold it. Nothing is booked until you confirm."
            : "Choose a service, then a free time on the calendar. You'll see the price range and how to prepare before you confirm."}
        </p>
      </section>
    );
  }
  const svc = service(hold.service)!;
  const s = hold.slot;
  const rule = checkRule(svc, me, s.date, cal);
  return (
    <section className="panel summary" data-stage-thing="summary" data-stage-label="Booking summary" aria-live="polite">
      <p className="summary-kicker">Held for you, not yet booked</p>
      <h3>{svc.name}</h3>
      <dl className="facts">
        <div>
          <dt>{s.dentist ? "Dentist" : "Room"}</dt>
          <dd>{slotWho(s)}</dd>
        </div>
        <div>
          <dt>Branch</dt>
          <dd>{branch(s.branch)?.name}</dd>
        </div>
        <div>
          <dt>Date</dt>
          <dd>
            {longDate(s.date)}, {weekdayName(s.date)}
          </dd>
        </div>
        <div>
          <dt>Time</dt>
          <dd>
            {time12(s.time)} to {time12(hhmm(s.start + svc.duration_min))}
          </dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd>{durationText(svc.duration_min)}</dd>
        </div>
        <div>
          <dt>Price</dt>
          <dd>
            {priceRange(svc)}
            {svc.price.note ? <span className="small muted"> {svc.price.note}</span> : null}
          </dd>
        </div>
      </dl>
      {hold.sittings.length ? (
        <div className="sittings">
          <p className="small strong">Later sittings, pencilled in</p>
          <ol>
            <li>
              Sitting 1: {longDate(s.date)}, {time12(s.time)}
            </li>
            {hold.sittings.map((x, i) => (
              <li key={x.date}>
                Sitting {i + 2}: {longDate(x.date)} ({weekdayName(x.date).slice(0, 3)}), {time12(x.time)}, {branch(x.branch)?.short}
              </li>
            ))}
          </ol>
        </div>
      ) : null}
      <p className="prep">
        <strong>Before you come:</strong> {prepLine(svc.id)}
      </p>
      {rule.ok === false ? (
        <p className="form-error">
          {rule.rule?.title}: {rule.why}. {rule.rule?.text}
        </p>
      ) : rule.ok === null && rule.rule ? (
        <p className="rule-note small">
          <Info size={14} aria-hidden /> {rule.rule.title}. We check this when you sign in.
        </p>
      ) : rule.rule ? (
        <p className="rule-ok small">
          <Check size={14} aria-hidden /> {rule.rule.title}: {rule.why}.
        </p>
      ) : null}
      {b.error ? <p className="form-error">{b.error}</p> : null}
      <div className="summary-actions">
        <button type="button" className="btn btn-primary btn-lg" data-stage-thing="confirm" data-stage-label="Confirm" onClick={() => actions.confirm()} disabled={rule.ok === false}>
          {me ? "Confirm booking" : "Confirm"}
        </button>
        <button type="button" className="btn btn-ghost" onClick={() => actions.clearHold()}>
          Release
        </button>
      </div>
      <p className="small muted">
        {me ? (
          <>
            Booking for <strong>{me.name}</strong> ({me.id}).
          </>
        ) : (
          <>
            <Lock size={12} aria-hidden /> {wanted ? "Sign in below to confirm." : "You'll sign in with your mobile number to confirm."}
          </>
        )}{" "}
        Free to cancel or move up to {DATA.policies.cancellation.free_until_hours} hours before.
      </p>
    </section>
  );
}

function Confirmation() {
  const b = useStore((s) => s.book);
  const cal = useStore((s) => s.cal);
  const a = b.confirmed ? cal.appts.get(b.confirmed.id) : undefined;
  if (!a || !b.confirmed) return null;
  const svc = service(a.service)!;
  const later = b.confirmed.sittingIds.map((id) => cal.appts.get(id)).filter(Boolean);
  return (
    <section className="panel confirmed" data-stage-thing="summary" data-stage-label="Booking confirmed" aria-live="polite">
      <p className="confirmed-tick">
        <Check size={18} aria-hidden /> Booked
      </p>
      <h3>{svc.name}</h3>
      <p className="confirmed-id">
        Booking ID <strong>{a.id}</strong>
      </p>
      <p>
        {longDate(a.date)}, {weekdayName(a.date)} at {time12(hhmm(a.start))}
        <br />
        {a.dentist ? dentist(a.dentist)?.name : room(a.resource)?.room.label}, {branch(a.branch)?.name}
      </p>
      {later.length ? (
        <ul className="small">
          {later.map((x) => (
            <li key={x!.id}>
              Sitting {x!.sitting}: {longDate(x!.date)}, {time12(hhmm(x!.start))} ({x!.id})
            </li>
          ))}
        </ul>
      ) : null}
      <p className="prep">
        <strong>Before you come:</strong> {prepLine(svc.id)}
      </p>
      <p className="small muted">We've sent the details by SMS. Please arrive 10 minutes early for a first visit.</p>
      <div className="summary-actions">
        <Link to="/my-appointments" className="btn btn-primary">
          My appointments
        </Link>
        <button type="button" className="btn btn-ghost" onClick={() => actions.selectService(null)}>
          Book another
        </button>
      </div>
    </section>
  );
}

export function Book() {
  const b = useStore((s) => s.book);
  const today = useStore((s) => s.clock.today);
  const signedIn = useStore((s) => s.signedIn);
  const wanted = useStore((s) => s.signin.wanted);
  const svc = service(b.service);
  const subjects = subjectsFor(b);
  const weekSubject = b.focus ?? b.dentist ?? b.resource ?? subjects[0] ?? null;
  return (
    <div data-page="book" className="book-page">
      <div className="wrap">
        <header className="page-head">
          <h1>Book an appointment</h1>
          <p className="muted">
            Real calendars for every dentist and scan room, up to {DATA.booking.horizon_days} days ahead. Holding a time costs nothing; you confirm with your mobile number.
          </p>
        </header>
        <div className="book-grid">
          <div className="book-choose">
            <ServiceStep />
            <WhoStep />
          </div>
          <div className="book-cal">
            <h2 className="step-title">
              <span className="step-n">3</span> Pick a time
            </h2>
            <Calendar
              serviceId={b.service}
              date={b.date}
              view={b.view}
              subjects={subjects}
              weekSubject={weekSubject}
              branch={b.branch}
              hold={b.hold?.slot ?? null}
              minDate={today}
              maxDate={addDays(today, DATA.booking.horizon_days)}
              onPick={(slot) => actions.hold(slot)}
              onDate={(d) => actions.setDate(d)}
              onView={(v) => actions.setView(v)}
              title={
                <strong>
                  {b.focus
                    ? (dentist(b.focus)?.name ?? room(b.focus)?.room.label)
                    : b.view === "week" && weekSubject
                      ? (dentist(weekSubject)?.name ?? `${room(weekSubject)?.room.label}, ${room(weekSubject)?.branch.short}`)
                      : svc
                        ? svc.resource
                          ? "Imaging rooms"
                          : subjects.length === 1
                            ? dentist(subjects[0])?.name
                            : "All dentists for this service"
                        : "All dentists"}
                </strong>
              }
            />
            {b.focus ? (
              <button type="button" className="link-btn small" onClick={() => actions.setFocus(null)}>
                Back to the dentists for your choice
              </button>
            ) : null}
          </div>
          <aside className="book-rail">
            <h2 className="step-title">
              <span className="step-n">4</span> Confirm
            </h2>
            <Summary />
            {!signedIn && (wanted || b.hold) ? <SignIn title="Sign in to confirm" note="We send a one-time code to your mobile. New patients register here too." /> : null}
            {signedIn && !b.confirmed && b.hold ? null : null}
          </aside>
        </div>
      </div>
    </div>
  );
}
