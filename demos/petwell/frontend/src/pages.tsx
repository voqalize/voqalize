/**
 * The Petwell booking page — the hospital's "Book an Appointment" form, as six
 * short steps the caller can talk through or tap through.
 *
 *   home → location → service → slot → details → review → done
 *
 * Plain state-driven navigation (see store.tsx), so the live voice call is never
 * interrupted. Branches, services and slots carry `data-*` ids so the agent's
 * choices are visible exactly where the caller would have tapped.
 */

import { type ReactNode } from 'react';
import {
  CalendarDays,
  Check,
  ChevronLeft,
  Clock,
  Home,
  MapPin,
  PawPrint,
  Phone,
  Siren,
  Stethoscope,
  X,
} from 'lucide-react';
import {
  bookingDates,
  branchesIn,
  CITIES,
  formatDate,
  formatTime,
  getBranch,
  getService,
  HELPLINES,
  helplineFor,
  OPENING_SOON,
  SERVICES,
  slotsFor,
  todayIst,
  type Service,
} from './catalog';
import { useBooking, type Details, type Step } from './store';

const STEPS: { id: Step; label: string }[] = [
  { id: 'home', label: 'Visit' },
  { id: 'location', label: 'Location' },
  { id: 'service', label: 'Reason' },
  { id: 'slot', label: 'Time' },
  { id: 'details', label: 'Details' },
  { id: 'review', label: 'Review' },
];

// ── Shell ─────────────────────────────────────────────────────────────────────

export function BookingApp({ presence }: { presence: ReactNode }) {
  const b = useBooking();
  return (
    <div className="pw-app">
      <style>{CSS}</style>
      <div className="pw-ticker" aria-hidden>
        <span>Petwell Kolkata — opening soon! · Now open 24x7 for emergencies · 15 branches across 9 cities ·&nbsp;</span>
        <span>Petwell Kolkata — opening soon! · Now open 24x7 for emergencies · 15 branches across 9 cities ·&nbsp;</span>
      </div>
      <header className="pw-top">
        <button className="pw-logo" onClick={b.restart} title="Start over">
          <span className="pw-logo-mark">
            <PawPrint size={18} />
          </span>
          <span>
            <span className="pw-logo-name">Petwell</span>
            <span className="pw-logo-sub">Veterinary Hospitals</span>
          </span>
        </button>
        <div className="pw-top-right">
          <button className="pw-sos" onClick={b.openEmergency}>
            <Siren size={14} /> <span>24x7 Emergency</span>
          </button>
          {presence}
        </div>
      </header>

      <main className="pw-main">
        <div className="pw-card">
          {b.step !== 'done' && <Stepper />}
          {b.step !== 'home' && b.step !== 'done' && <Summary />}
          <div className="pw-body" key={b.step}>
            {b.step === 'home' && <HomeStep />}
            {b.step === 'location' && <LocationStep />}
            {b.step === 'service' && <ServiceStep />}
            {b.step === 'slot' && <SlotStep />}
            {b.step === 'details' && <DetailsStep />}
            {b.step === 'review' && <ReviewStep />}
            {b.step === 'done' && <DoneStep />}
          </div>
        </div>
        <p className="pw-foot">A Voqalize demo · Petwell is a fictional hospital chain.</p>
      </main>

      {b.emergency && <EmergencyPanel />}
    </div>
  );
}

function Stepper() {
  const { step, goTo } = useBooking();
  const at = STEPS.findIndex((s) => s.id === step);
  return (
    <ol className="pw-stepper">
      {STEPS.map((s, i) => (
        <li
          key={s.id}
          className={i < at ? 'is-done' : i === at ? 'is-now' : ''}
          onClick={() => i < at && goTo(s.id)}
        >
          <span className="pw-dot">{i < at ? <Check size={11} /> : i + 1}</span>
          <span className="pw-step-label">{s.label}</span>
        </li>
      ))}
    </ol>
  );
}

/** What has been chosen so far — one line of chips, each a way back. */
function Summary() {
  const b = useBooking();
  const branch = getBranch(b.branchId);
  const service = getService(b.serviceId);
  const chips: { icon: ReactNode; text: string; step: Step }[] = [
    {
      icon: b.visitType === 'home' ? <Home size={13} /> : <Stethoscope size={13} />,
      text: b.visitType === 'home' ? 'Vet at home' : 'Clinic visit',
      step: 'home',
    },
  ];
  if (branch) chips.push({ icon: <MapPin size={13} />, text: branch.name.replace('Petwell ', ''), step: 'location' });
  else if (b.city) chips.push({ icon: <MapPin size={13} />, text: b.city, step: 'location' });
  if (service) chips.push({ icon: <PawPrint size={13} />, text: service.name, step: 'service' });
  if (b.date && b.time)
    chips.push({ icon: <Clock size={13} />, text: `${formatDate(b.date)}, ${formatTime(b.time)}`, step: 'slot' });
  return (
    <div className="pw-summary">
      {chips.map((c) => (
        <button key={c.step} className="pw-chip is-chosen" onClick={() => b.goTo(c.step)}>
          {c.icon}
          {c.text}
        </button>
      ))}
    </div>
  );
}

function Back({ to }: { to: Step }) {
  const { goTo } = useBooking();
  return (
    <button className="pw-back" onClick={() => goTo(to)}>
      <ChevronLeft size={16} /> Back
    </button>
  );
}

// ── 1. Visit type ─────────────────────────────────────────────────────────────

function HomeStep() {
  const b = useBooking();
  return (
    <>
      <h1 className="pw-h1">Book an Appointment</h1>
      <p className="pw-lead">
        Paws anytime — expert vets and modern hospitals across 9 cities. Tap below, or just tell us what your
        pet needs.
      </p>
      <div className="pw-visit-grid">
        <button className="pw-visit" data-visit="clinic" onClick={() => b.pickVisitType('clinic')}>
          <span className="pw-visit-icon">
            <Stethoscope size={26} />
          </span>
          <span className="pw-visit-title">Clinic Visit</span>
          <span className="pw-visit-sub">Everyday and specialty care at a Petwell hospital near you</span>
        </button>
        <button className="pw-visit" data-visit="home" onClick={() => b.pickVisitType('home')}>
          <span className="pw-visit-icon">
            <Home size={26} />
          </span>
          <span className="pw-visit-title">Petwell@Home</span>
          <span className="pw-visit-sub">Vaccinations, minor illness, blood samples and physio — at your door</span>
        </button>
      </div>
      <div className="pw-sos-strip">
        <Siren size={18} />
        <div>
          <strong>Emergency? We're open 24x7.</strong>
          <div className="pw-sos-lines">
            {HELPLINES.map((h) => (
              <span key={h.region}>
                {h.region} <b>{h.phone}</b>
              </span>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

// ── 2. Location ───────────────────────────────────────────────────────────────

function LocationStep() {
  const b = useBooking();
  const branches = b.city ? branchesIn(b.city) : [];
  const soon = b.city !== null && OPENING_SOON.has(b.city);
  return (
    <>
      <Back to="home" />
      <h2 className="pw-h2">{b.visitType === 'home' ? 'Where should our vet come?' : 'Choose your city'}</h2>
      <div className="pw-cities">
        {CITIES.map((c) => (
          <button
            key={c}
            data-city={c}
            className={`pw-chip${b.city === c ? ' is-chosen' : ''}${OPENING_SOON.has(c) ? ' is-soon' : ''}`}
            onClick={() => b.pickCity(c)}
          >
            {c}
            {OPENING_SOON.has(c) && <em>Soon</em>}
          </button>
        ))}
      </div>
      {soon && (
        <div className="pw-note">
          Petwell {b.city} is <strong>opening soon</strong>. Please choose another city for now.
        </div>
      )}
      {b.city && !soon && (
        <>
          <h3 className="pw-h3">
            {b.visitType === 'home' ? 'Nearest branch' : 'Branches'} in {b.city}
          </h3>
          <div className="pw-list">
            {branches.map((br) => (
              <button
                key={br.id}
                data-branch-id={br.id}
                className={`pw-row${b.branchId === br.id ? ' is-chosen' : ''}`}
                onClick={() => b.pickBranch(br.id)}
              >
                <MapPin size={18} className="pw-row-icon" />
                <span className="pw-row-text">
                  <span className="pw-row-title">
                    {br.name}
                    {br.emergency && <span className="pw-tag">24x7 Emergency</span>}
                  </span>
                  <span className="pw-row-sub">{br.address}</span>
                </span>
              </button>
            ))}
          </div>
        </>
      )}
    </>
  );
}

// ── 3. Reason for visit ───────────────────────────────────────────────────────

function ServiceStep() {
  const b = useBooking();
  const groups: Service['group'][] =
    b.visitType === 'home' ? ['At home'] : ['Everyday care', 'Specialty care'];
  return (
    <>
      <Back to="location" />
      <h2 className="pw-h2">What's the visit for?</h2>
      {groups.map((g) => (
        <section key={g}>
          <h3 className="pw-h3">{g}</h3>
          <div className="pw-services">
            {SERVICES.filter((s) => s.group === g).map((s) => (
              <button
                key={s.id}
                data-service-id={s.id}
                className={`pw-service${b.serviceId === s.id ? ' is-chosen' : ''}`}
                onClick={() => b.pickService(s.id)}
              >
                <span className="pw-service-name">{s.name}</span>
                <span className="pw-service-blurb">{s.blurb}</span>
              </button>
            ))}
          </div>
        </section>
      ))}
    </>
  );
}

// ── 4. Day and time ───────────────────────────────────────────────────────────

function nowIstHHMM(): string {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date());
}

function SlotStep() {
  const b = useBooking();
  const dates = bookingDates();
  const date = b.date ?? dates[0];
  const today = todayIst();
  let times = b.times ?? (b.branchId ? slotsFor(b.branchId, date, b.visitType) : []);
  if (!b.times && date === today) {
    const now = nowIstHHMM();
    times = times.filter((t) => t > now);
  }
  return (
    <>
      <Back to="service" />
      <h2 className="pw-h2">
        <CalendarDays size={20} /> Pick a day and time
      </h2>
      <div className="pw-dates">
        {dates.map((d) => (
          <button
            key={d}
            data-date={d}
            className={`pw-date${d === date ? ' is-chosen' : ''}`}
            onClick={() => b.pickDate(d)}
          >
            <span className="pw-date-dow">
              {d === today ? 'Today' : formatDate(d, { weekday: 'short', day: undefined, month: undefined })}
            </span>
            <span className="pw-date-day">{formatDate(d, { weekday: undefined, month: undefined })}</span>
            <span className="pw-date-mon">{formatDate(d, { weekday: undefined, day: undefined })}</span>
          </button>
        ))}
      </div>
      {times.length === 0 ? (
        <div className="pw-note">Fully booked on this day — please pick another.</div>
      ) : (
        <div className="pw-times">
          {times.map((t) => (
            <button
              key={t}
              data-time={t}
              className={`pw-time${b.time === t && b.date === date ? ' is-chosen' : ''}`}
              onClick={() => b.pickSlot(date, t)}
            >
              {formatTime(t)}
            </button>
          ))}
        </div>
      )}
    </>
  );
}

// ── 5. Details — the hospital's own form fields ───────────────────────────────

const PET_TYPES = [
  ['dog', 'Dog'],
  ['cat', 'Cat'],
  ['bird', 'Bird'],
  ['rabbit', 'Rabbit'],
  ['other', 'Other'],
] as const;

function Field({
  name,
  label,
  required,
  children,
}: {
  name: keyof Details;
  label: string;
  required?: boolean;
  children?: ReactNode;
}) {
  const b = useBooking();
  return (
    <label className={`pw-field${b.justFilled.includes(name) ? ' pw-flash' : ''}`}>
      <span className="pw-label">
        {label}
        {required && <i> *</i>}
      </span>
      {children ?? (
        <input
          name={name}
          value={b.details[name]}
          onChange={(e) => b.editDetail(name, e.target.value)}
          inputMode={name === 'phone' ? 'tel' : undefined}
        />
      )}
    </label>
  );
}

function DetailsStep() {
  const b = useBooking();
  const d = b.details;
  const ready = d.owner_name.trim() && d.pet_name.trim() && d.phone.trim();
  return (
    <>
      <Back to="slot" />
      <h2 className="pw-h2">Your details</h2>
      <div className="pw-form">
        <Field name="owner_name" label="Your Name" required />
        <Field name="pet_name" label="Your Pet's Name" required />
        <Field name="pet_type" label="Pet type">
          <div className="pw-seg">
            {PET_TYPES.map(([v, l]) => (
              <button
                key={v}
                type="button"
                className={d.pet_type === v ? 'is-chosen' : ''}
                onClick={() => b.editDetail('pet_type', v)}
              >
                {l}
              </button>
            ))}
          </div>
        </Field>
        <Field name="phone" label="Phone Number" required />
        <Field name="email" label="Email ID (optional)" />
        {b.visitType === 'home' && <Field name="address" label="Home address / locality" required />}
        <Field name="notes" label="Message">
          <textarea
            name="notes"
            rows={2}
            value={d.notes}
            onChange={(e) => b.editDetail('notes', e.target.value)}
          />
        </Field>
      </div>
      <button className="pw-primary" disabled={!ready} onClick={b.reviewNow}>
        Continue
      </button>
    </>
  );
}

// ── 6. Review and send ────────────────────────────────────────────────────────

function BookingFacts() {
  const b = useBooking();
  const branch = getBranch(b.branchId);
  const service = getService(b.serviceId);
  const d = b.details;
  const rows: [string, ReactNode][] = [
    ['Service type', b.visitType === 'home' ? 'Home Visit' : 'Clinic Visit'],
    ['Branch', branch ? <>{branch.name}<small>{branch.address}</small></> : '—'],
    ['Reason', service?.name ?? '—'],
    ['When', b.date && b.time ? `${formatDate(b.date, { weekday: 'long', month: 'long' })}, ${formatTime(b.time)}` : '—'],
    ['Pet', [d.pet_name, d.pet_type && `(${d.pet_type})`].filter(Boolean).join(' ') || '—'],
    ['Owner', d.owner_name || '—'],
    ['Phone', d.phone || '—'],
  ];
  if (d.email) rows.push(['Email', d.email]);
  if (b.visitType === 'home') rows.push(['Address', d.address || '—']);
  if (d.notes) rows.push(['Message', d.notes]);
  return (
    <dl className="pw-facts">
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function ReviewStep() {
  const b = useBooking();
  return (
    <>
      <Back to="details" />
      <h2 className="pw-h2">Check and send</h2>
      <BookingFacts />
      <button className="pw-primary pw-send" onClick={() => b.sendRequest()}>
        Send Request
      </button>
      <p className="pw-small">The branch will call you to confirm your appointment.</p>
    </>
  );
}

function DoneStep() {
  const b = useBooking();
  return (
    <div className="pw-done">
      <span className="pw-done-icon">
        <Check size={32} />
      </span>
      <h2 className="pw-h2">Request sent</h2>
      <p className="pw-lead">
        Your reference is <strong className="pw-ref">{b.ref}</strong>. The branch will call you shortly to
        confirm.
      </p>
      <BookingFacts />
      <button className="pw-secondary" onClick={b.restart}>
        Book another appointment
      </button>
    </div>
  );
}

// ── Emergency ─────────────────────────────────────────────────────────────────

function EmergencyPanel() {
  const b = useBooking();
  const e = b.emergency!;
  const lines = e.city ? [helplineFor(e.city)] : HELPLINES;
  const branches = e.branchIds.length
    ? e.branchIds.map((id) => getBranch(id)).filter((x) => !!x)
    : e.city
      ? branchesIn(e.city).filter((x) => x.emergency)
      : [];
  return (
    <div className="pw-overlay" onClick={b.closeEmergency}>
      <div className="pw-sheet" onClick={(ev) => ev.stopPropagation()} role="dialog" aria-label="Emergency">
        <button className="pw-close" onClick={b.closeEmergency} title="Close">
          <X size={18} />
        </button>
        <div className="pw-sheet-head">
          <Siren size={22} />
          <div>
            <h2>Emergency? Come in now.</h2>
            <p>Our emergency hospitals are open 24x7. Call ahead so the team is ready.</p>
          </div>
        </div>
        {lines.map((h) => (
          <a key={h.region} className="pw-call" href={`tel:${h.phone.replace(/\s/g, '')}`}>
            <Phone size={18} />
            <span>
              <small>{h.region}</small>
              {h.phone}
            </span>
          </a>
        ))}
        {branches.length > 0 && (
          <>
            <h3 className="pw-h3">24x7 emergency branch{branches.length > 1 ? 'es' : ''} in {e.city}</h3>
            {branches.map((br) => (
              <div key={br.id} className="pw-row is-static" data-branch-id={br.id}>
                <MapPin size={18} className="pw-row-icon" />
                <span className="pw-row-text">
                  <span className="pw-row-title">{br.name}</span>
                  <span className="pw-row-sub">{br.address}</span>
                </span>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const CSS = `
.pw-app {
  --pw: #5c42bf; --pw-dark: #4a3596; --pw-tint: #f4f1ff; --pw-line: #e4defa;
  --ink: #1f1b2e; --muted: #6b6880; --sos: #d92d20;
  position: absolute; inset: 0; overflow-y: auto; background: var(--pw-tint);
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: var(--ink);
}
.pw-app *, .pw-app *::before, .pw-app *::after { box-sizing: border-box; }
.pw-app button { font: inherit; color: inherit; }
.pw-ticker { display: flex; white-space: nowrap; overflow: hidden; background: var(--pw); color: #fff;
  font-size: 12px; font-weight: 600; padding: 6px 0; }
.pw-ticker span { animation: pw-ticker 28s linear infinite; padding-right: 8px; }
@keyframes pw-ticker { to { transform: translateX(-100%); } }
.pw-top { position: sticky; top: 0; z-index: 5; display: flex; align-items: center; justify-content: space-between;
  gap: 12px; padding: 10px 20px; background: #fff; border-bottom: 1px solid var(--pw-line); }
.pw-logo { display: flex; align-items: center; gap: 10px; background: none; border: 0; cursor: pointer; padding: 0; text-align: left; }
.pw-logo-mark { width: 34px; height: 34px; border-radius: 10px; background: var(--pw); color: #fff;
  display: grid; place-items: center; }
.pw-logo-name { display: block; font-weight: 800; font-size: 18px; color: var(--pw); letter-spacing: -.01em; line-height: 1.1; }
.pw-logo-sub { display: block; font-size: 11px; color: var(--muted); }
.pw-top-right { display: flex; align-items: center; gap: 12px; min-width: 0; }
.pw-sos { display: flex; align-items: center; gap: 6px; border: 1.5px solid var(--sos); color: var(--sos) !important;
  background: #fff; border-radius: 999px; padding: 6px 12px; font-size: 12.5px; font-weight: 700; cursor: pointer; }
.pw-sos:hover { background: #fef3f2; }
.pw-main { max-width: 760px; margin: 0 auto; padding: 24px 16px 40px; }
.pw-card { background: #fff; border-radius: 20px; box-shadow: 0 6px 30px rgba(74,53,150,.08); padding: 24px; }
.pw-body { animation: pw-in .25s ease; }
@keyframes pw-in { from { opacity: 0; transform: translateY(6px); } }
.pw-foot { text-align: center; color: var(--muted); font-size: 12px; margin-top: 16px; }

.pw-stepper { display: flex; list-style: none; margin: 0 0 18px; padding: 0; gap: 4px; }
.pw-stepper li { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px; font-size: 11.5px;
  color: var(--muted); position: relative; }
.pw-stepper li:not(:last-child)::after { content: ""; position: absolute; top: 11px; left: calc(50% + 14px);
  right: calc(-50% + 14px); height: 2px; background: var(--pw-line); }
.pw-stepper li.is-done::after { background: var(--pw); }
.pw-stepper li.is-done { cursor: pointer; }
.pw-dot { width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; font-weight: 700;
  font-size: 11px; background: var(--pw-tint); color: var(--pw); border: 1.5px solid var(--pw-line); }
.pw-stepper .is-now .pw-dot { background: var(--pw); color: #fff; border-color: var(--pw); }
.pw-stepper .is-done .pw-dot { background: var(--pw); color: #fff; border-color: var(--pw); }
.pw-stepper .is-now { color: var(--pw); font-weight: 700; }

.pw-summary { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 16px; padding-bottom: 14px; border-bottom: 1px dashed var(--pw-line); }
.pw-h1 { font-size: 28px; line-height: 1.15; margin: 4px 0 8px; color: var(--pw-dark); letter-spacing: -.02em; }
.pw-h2 { display: flex; align-items: center; gap: 8px; font-size: 20px; margin: 6px 0 14px; color: var(--pw-dark); }
.pw-h3 { font-size: 13px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 18px 0 8px; }
.pw-lead { color: var(--muted); margin: 0 0 18px; line-height: 1.5; }
.pw-small { color: var(--muted); font-size: 12.5px; text-align: center; margin: 10px 0 0; }
.pw-back { display: inline-flex; align-items: center; gap: 2px; background: none; border: 0; color: var(--muted) !important;
  cursor: pointer; padding: 0; font-size: 13px; }

.pw-visit-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.pw-visit { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; text-align: left; cursor: pointer;
  border: 1.5px solid var(--pw-line); border-radius: 16px; padding: 18px; background: #fff; transition: all .15s; }
.pw-visit:hover { border-color: var(--pw); box-shadow: 0 4px 18px rgba(92,66,191,.12); transform: translateY(-1px); }
.pw-visit-icon { width: 48px; height: 48px; border-radius: 14px; background: var(--pw-tint); color: var(--pw); display: grid; place-items: center; }
.pw-visit-title { font-weight: 800; font-size: 17px; color: var(--pw-dark); }
.pw-visit-sub { font-size: 13px; color: var(--muted); line-height: 1.4; }
.pw-sos-strip { display: flex; gap: 12px; align-items: flex-start; margin-top: 16px; padding: 14px 16px; border-radius: 14px;
  background: var(--pw-dark); color: #fff; font-size: 14px; }
.pw-sos-lines { display: flex; flex-wrap: wrap; gap: 4px 16px; margin-top: 4px; font-size: 12.5px; opacity: .92; }

.pw-cities { display: flex; flex-wrap: wrap; gap: 8px; }
.pw-chip { display: inline-flex; align-items: center; gap: 6px; border: 1.5px solid var(--pw-line); background: #fff;
  border-radius: 999px; padding: 7px 14px; font-size: 13.5px; font-weight: 600; cursor: pointer; transition: all .15s; }
.pw-chip:hover { border-color: var(--pw); }
.pw-chip.is-chosen { background: var(--pw); border-color: var(--pw); color: #fff !important; }
.pw-summary .pw-chip { font-size: 12px; padding: 4px 10px; background: var(--pw-tint); border-color: transparent; color: var(--pw-dark) !important; }
.pw-chip em { font-style: normal; font-size: 10.5px; background: #fff4e5; color: #b54708; padding: 1px 6px; border-radius: 999px; }
.pw-chip.is-soon { color: var(--muted) !important; }
.pw-note { margin-top: 14px; padding: 12px 14px; border-radius: 12px; background: #fff4e5; color: #93370d; font-size: 14px; }

.pw-list { display: flex; flex-direction: column; gap: 8px; }
.pw-row { display: flex; gap: 12px; align-items: flex-start; text-align: left; width: 100%; cursor: pointer;
  border: 1.5px solid var(--pw-line); border-radius: 14px; padding: 12px 14px; background: #fff; transition: all .15s; }
.pw-row:hover { border-color: var(--pw); }
.pw-row.is-static { cursor: default; margin-bottom: 8px; }
.pw-row.is-chosen { border-color: var(--pw); background: var(--pw-tint); box-shadow: 0 0 0 3px rgba(92,66,191,.15); }
.pw-row-icon { color: var(--pw); flex: 0 0 auto; margin-top: 2px; }
.pw-row-text { display: flex; flex-direction: column; gap: 2px; }
.pw-row-title { font-weight: 700; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.pw-row-sub { font-size: 13px; color: var(--muted); }
.pw-tag { font-size: 10.5px; font-weight: 700; color: var(--sos); background: #fef3f2; padding: 2px 7px; border-radius: 999px; }

.pw-services { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; }
.pw-service { display: flex; flex-direction: column; gap: 3px; text-align: left; cursor: pointer; padding: 12px 14px;
  border: 1.5px solid var(--pw-line); border-radius: 14px; background: #fff; transition: all .15s; }
.pw-service:hover { border-color: var(--pw); }
.pw-service.is-chosen { border-color: var(--pw); background: var(--pw-tint); box-shadow: 0 0 0 3px rgba(92,66,191,.15); }
.pw-service-name { font-weight: 700; font-size: 14.5px; }
.pw-service-blurb { font-size: 12.5px; color: var(--muted); }

.pw-dates { display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px; margin-bottom: 16px; }
.pw-date { display: flex; flex-direction: column; align-items: center; gap: 1px; padding: 8px 2px; cursor: pointer;
  border: 1.5px solid var(--pw-line); border-radius: 12px; background: #fff; }
.pw-date.is-chosen { background: var(--pw); border-color: var(--pw); color: #fff !important; }
.pw-date-dow { font-size: 11px; font-weight: 600; opacity: .8; }
.pw-date-day { font-size: 18px; font-weight: 800; }
.pw-date-mon { font-size: 11px; opacity: .8; }
.pw-times { display: grid; grid-template-columns: repeat(auto-fill, minmax(92px, 1fr)); gap: 8px; }
.pw-time { padding: 10px 0; border: 1.5px solid var(--pw-line); border-radius: 10px; background: #fff; cursor: pointer;
  font-weight: 600; font-size: 13.5px; }
.pw-time:hover { border-color: var(--pw); }
.pw-time.is-chosen { background: var(--pw); border-color: var(--pw); color: #fff !important; }

.pw-form { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 14px; margin-bottom: 18px; }
.pw-field { display: flex; flex-direction: column; gap: 5px; border-radius: 10px; }
.pw-field:has(textarea), .pw-field:has(.pw-seg) { grid-column: 1 / -1; }
.pw-label { font-size: 13px; font-weight: 600; }
.pw-label i { color: var(--sos); font-style: normal; }
.pw-field input, .pw-field textarea { font: inherit; padding: 10px 12px; border: 1.5px solid var(--pw-line); border-radius: 10px;
  outline: none; background: #fff; resize: vertical; }
.pw-field input:focus, .pw-field textarea:focus { border-color: var(--pw); }
.pw-flash input, .pw-flash textarea, .pw-flash .pw-seg { animation: pw-flash 1.6s ease; }
@keyframes pw-flash { 0%, 40% { background: #ece6ff; border-color: var(--pw); } }
.pw-seg { display: flex; flex-wrap: wrap; gap: 6px; }
.pw-seg button { border: 1.5px solid var(--pw-line); border-radius: 999px; padding: 6px 14px; background: #fff; cursor: pointer; font-size: 13px; font-weight: 600; }
.pw-seg button.is-chosen { background: var(--pw); border-color: var(--pw); color: #fff !important; }

.pw-primary { width: 100%; padding: 14px; border-radius: 12px; border: 0; background: var(--pw); color: #fff !important;
  font-weight: 700; font-size: 15.5px; cursor: pointer; transition: background .15s; }
.pw-primary:hover:not(:disabled) { background: var(--pw-dark); }
.pw-primary:disabled { opacity: .45; cursor: not-allowed; }
.pw-send { margin-top: 18px; box-shadow: 0 6px 20px rgba(92,66,191,.3); animation: pw-pulse 2s ease-in-out infinite; }
@keyframes pw-pulse { 50% { box-shadow: 0 6px 28px rgba(92,66,191,.55); } }
.pw-secondary { width: 100%; margin-top: 16px; padding: 12px; border-radius: 12px; border: 1.5px solid var(--pw);
  background: #fff; color: var(--pw) !important; font-weight: 700; cursor: pointer; }

.pw-facts { margin: 0; border: 1.5px solid var(--pw-line); border-radius: 14px; overflow: hidden; }
.pw-facts > div { display: grid; grid-template-columns: 130px 1fr; gap: 10px; padding: 10px 14px; font-size: 14px; }
.pw-facts > div:nth-child(odd) { background: #faf8ff; }
.pw-facts dt { color: var(--muted); }
.pw-facts dd { margin: 0; font-weight: 600; }
.pw-facts small { display: block; font-weight: 400; color: var(--muted); font-size: 12.5px; }
.pw-done { text-align: center; }
.pw-done .pw-h2 { justify-content: center; }
.pw-done .pw-facts { text-align: left; }
.pw-done-icon { width: 64px; height: 64px; margin: 6px auto 4px; border-radius: 50%; background: #ecfdf3; color: #12b76a; display: grid; place-items: center; }
.pw-ref { color: var(--pw); font-size: 1.1em; letter-spacing: .03em; }

.pw-overlay { position: fixed; inset: 0; z-index: 20; background: rgba(31,27,46,.45); display: grid; place-items: center; padding: 16px; animation: pw-in .2s; }
.pw-sheet { position: relative; width: min(460px, 100%); max-height: 90vh; overflow-y: auto; background: #fff; border-radius: 20px; padding: 22px; }
.pw-close { position: absolute; top: 12px; right: 12px; border: 0; background: none; cursor: pointer; color: var(--muted) !important; }
.pw-sheet-head { display: flex; gap: 12px; color: var(--sos); margin-bottom: 14px; padding-right: 24px; }
.pw-sheet-head h2 { margin: 0 0 4px; font-size: 19px; color: var(--ink); }
.pw-sheet-head p { margin: 0; color: var(--muted); font-size: 13.5px; }
.pw-call { display: flex; align-items: center; gap: 12px; padding: 12px 14px; margin-bottom: 8px; border-radius: 12px;
  background: var(--sos); color: #fff; text-decoration: none; font-weight: 800; font-size: 17px; }
.pw-call small { display: block; font-size: 11.5px; font-weight: 600; opacity: .85; }

@media (max-width: 640px) {
  .pw-top { padding: 8px 12px; }
  .pw-logo-sub, .pw-sos span { display: none; }
  .pw-card { padding: 18px 16px; border-radius: 16px; }
  .pw-main { padding: 14px 12px 32px; }
  .pw-h1 { font-size: 24px; }
  .pw-visit-grid, .pw-form { grid-template-columns: 1fr; }
  .pw-step-label { display: none; }
  .pw-dates { gap: 4px; }
  .pw-date-day { font-size: 16px; }
  .pw-facts > div { grid-template-columns: 96px 1fr; }
}
@media (prefers-reduced-motion: reduce) {
  .pw-ticker span, .pw-send, .pw-body { animation: none; }
}
`;
