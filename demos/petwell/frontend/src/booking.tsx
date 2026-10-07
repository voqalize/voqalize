/**
 * The booking panel — the hospital's "Book an Appointment" form as a drawer over
 * the website, in six short steps the visitor can talk through or click through:
 *
 *   visit → location → service → slot → details → review → done
 *
 * Branches, services and slots carry `data-*` ids so the agent's choices are
 * visible exactly where the visitor would have clicked.
 */

import { useEffect, type ReactNode } from 'react';
import { CalendarDays, Check, ChevronLeft, Clock, Home, MapPin, PawPrint, Phone, Siren, Stethoscope, X } from 'lucide-react';
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
import { cityName, groupName, locale, serviceBlurb, serviceName, strings } from './i18n';
import { useSite, type Details, type Step } from './store';

const STEPS: Step[] = ['visit', 'location', 'service', 'slot', 'details', 'review'];

export function BookingDrawer() {
  const b = useSite();
  const t = strings(b.lang);
  const { bookingOpen, closeBooking } = b;
  useEffect(() => {
    if (!bookingOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && closeBooking();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [bookingOpen, closeBooking]);
  if (!bookingOpen) return null;
  return (
    <div className="pw-drawer-wrap" onClick={b.closeBooking}>
      <aside className="pw-drawer" onClick={(e) => e.stopPropagation()} aria-label={t.bookingTitle}>
        <header className="pw-drawer-head">
          <h2>{t.bookingTitle}</h2>
          <button className="pw-icon-btn" onClick={b.closeBooking} title="Close">
            <X size={20} />
          </button>
        </header>
        <div className="pw-drawer-body">
          {b.step !== 'done' && <Stepper />}
          {b.step !== 'visit' && b.step !== 'done' && <Summary />}
          <div className="pw-body" key={b.step}>
            {b.step === 'visit' && <VisitStep />}
            {b.step === 'location' && <LocationStep />}
            {b.step === 'service' && <ServiceStep />}
            {b.step === 'slot' && <SlotStep />}
            {b.step === 'details' && <DetailsStep />}
            {b.step === 'review' && <ReviewStep />}
            {b.step === 'done' && <DoneStep />}
          </div>
        </div>
      </aside>
    </div>
  );
}

function Stepper() {
  const { step, goTo, lang } = useSite();
  const t = strings(lang);
  const labels: Record<string, string> = {
    visit: t.stepVisit,
    location: t.stepLocation,
    service: t.stepReason,
    slot: t.stepTime,
    details: t.stepDetails,
    review: t.stepReview,
  };
  const at = STEPS.indexOf(step);
  return (
    <ol className="pw-stepper">
      {STEPS.map((s, i) => (
        <li key={s} className={i < at ? 'is-done' : i === at ? 'is-now' : ''} onClick={() => i < at && goTo(s)}>
          <span className="pw-dot">{i < at ? <Check size={11} /> : i + 1}</span>
          <span className="pw-step-label">{labels[s]}</span>
        </li>
      ))}
    </ol>
  );
}

/** What has been chosen so far — one line of chips, each a way back. */
function Summary() {
  const b = useSite();
  const t = strings(b.lang);
  const branch = getBranch(b.branchId);
  const service = getService(b.serviceId);
  const chips: { icon: ReactNode; text: string; step: Step }[] = [
    {
      icon: b.visitType === 'home' ? <Home size={13} /> : <Stethoscope size={13} />,
      text: b.visitType === 'home' ? t.homeVisit : t.clinicVisit,
      step: 'visit',
    },
  ];
  if (branch) chips.push({ icon: <MapPin size={13} />, text: branch.name.replace('Petwell ', ''), step: 'location' });
  else if (b.city) chips.push({ icon: <MapPin size={13} />, text: cityName(b.city, b.lang), step: 'location' });
  if (service) chips.push({ icon: <PawPrint size={13} />, text: serviceName(service, b.lang), step: 'service' });
  if (b.date && b.time)
    chips.push({
      icon: <Clock size={13} />,
      text: `${formatDate(b.date, {}, locale(b.lang))}, ${formatTime(b.time)}`,
      step: 'slot',
    });
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
  const { goTo, lang } = useSite();
  return (
    <button className="pw-back" onClick={() => goTo(to)}>
      <ChevronLeft size={16} /> {strings(lang).back}
    </button>
  );
}

function VisitStep() {
  const b = useSite();
  const t = strings(b.lang);
  return (
    <div className="pw-visit-grid">
      <button className="pw-visit" data-visit="clinic" onClick={() => b.pickVisitType('clinic')}>
        <span className="pw-visit-icon">
          <Stethoscope size={24} />
        </span>
        <span className="pw-visit-title">{t.clinicVisit}</span>
        <span className="pw-visit-sub">{t.clinicVisitSub}</span>
      </button>
      <button className="pw-visit" data-visit="home" onClick={() => b.pickVisitType('home')}>
        <span className="pw-visit-icon">
          <Home size={24} />
        </span>
        <span className="pw-visit-title">{t.homeVisit}</span>
        <span className="pw-visit-sub">{t.homeVisitSub}</span>
      </button>
    </div>
  );
}

function LocationStep() {
  const b = useSite();
  const t = strings(b.lang);
  const branches = b.city ? branchesIn(b.city) : [];
  const soon = b.city !== null && OPENING_SOON.has(b.city);
  return (
    <>
      <Back to="visit" />
      <h3 className="pw-h2">{b.visitType === 'home' ? t.whereVet : t.chooseCity}</h3>
      <div className="pw-cities">
        {CITIES.map((c) => (
          <button
            key={c}
            data-city={c}
            className={`pw-chip${b.city === c ? ' is-chosen' : ''}${OPENING_SOON.has(c) ? ' is-soon' : ''}`}
            onClick={() => b.pickCity(c)}
          >
            {cityName(c, b.lang)}
            {OPENING_SOON.has(c) && <em>{t.openingSoon}</em>}
          </button>
        ))}
      </div>
      {soon && b.city && (
        <div className="pw-note">
          Petwell {cityName(b.city, b.lang)} {t.soonNote}
        </div>
      )}
      {b.city && !soon && (
        <>
          <h4 className="pw-h3">
            {b.visitType === 'home' ? t.nearestIn : t.branchesIn} {cityName(b.city, b.lang)}
          </h4>
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
                    {br.emergency && <span className="pw-tag">{t.emergencyBranch}</span>}
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

function ServiceStep() {
  const b = useSite();
  const t = strings(b.lang);
  const groups: Service['group'][] = b.visitType === 'home' ? ['At home'] : ['Everyday care', 'Specialty care'];
  return (
    <>
      <Back to="location" />
      <h3 className="pw-h2">{t.whatFor}</h3>
      {groups.map((g) => (
        <section key={g}>
          <h4 className="pw-h3">{groupName(g, b.lang)}</h4>
          <div className="pw-services">
            {SERVICES.filter((s) => s.group === g).map((s) => (
              <button
                key={s.id}
                data-service-id={s.id}
                className={`pw-service${b.serviceId === s.id ? ' is-chosen' : ''}`}
                onClick={() => b.pickService(s.id)}
              >
                <span className="pw-service-name">{serviceName(s, b.lang)}</span>
                <span className="pw-service-blurb">{serviceBlurb(s, b.lang)}</span>
              </button>
            ))}
          </div>
        </section>
      ))}
    </>
  );
}

function nowIstHHMM(): string {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date());
}

function SlotStep() {
  const b = useSite();
  const t = strings(b.lang);
  const loc = locale(b.lang);
  const dates = bookingDates();
  const today = todayIst();
  const now = nowIstHHMM();
  const freeOn = (d: string) =>
    (b.branchId ? slotsFor(b.branchId, d, b.visitType) : []).filter((x) => d !== today || x > now);
  // Open on the first day that still has a time — late in the evening that is tomorrow.
  const date = b.date ?? dates.find((d) => freeOn(d).length > 0) ?? dates[0];
  const times = b.times ?? freeOn(date);
  return (
    <>
      <Back to="service" />
      <h3 className="pw-h2">
        <CalendarDays size={20} /> {t.pickTime}
      </h3>
      <div className="pw-dates">
        {dates.map((d) => (
          <button key={d} data-date={d} className={`pw-date${d === date ? ' is-chosen' : ''}`} onClick={() => b.pickDate(d)}>
            <span className="pw-date-dow">
              {d === today ? t.today : formatDate(d, { weekday: 'short', day: undefined, month: undefined }, loc)}
            </span>
            <span className="pw-date-day">{formatDate(d, { weekday: undefined, month: undefined }, loc)}</span>
            <span className="pw-date-mon">{formatDate(d, { weekday: undefined, day: undefined }, loc)}</span>
          </button>
        ))}
      </div>
      {times.length === 0 ? (
        <div className="pw-note">{t.fullyBooked}</div>
      ) : (
        <div className="pw-times">
          {times.map((x) => (
            <button
              key={x}
              data-time={x}
              className={`pw-time${b.time === x && b.date === date ? ' is-chosen' : ''}`}
              onClick={() => b.pickSlot(date, x)}
            >
              {formatTime(x)}
            </button>
          ))}
        </div>
      )}
    </>
  );
}

const PET_TYPES = ['dog', 'cat', 'bird', 'rabbit', 'other'] as const;

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
  const b = useSite();
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
          onBlur={() => b.flushDetail(name)}
          inputMode={name === 'phone' ? 'tel' : undefined}
        />
      )}
    </label>
  );
}

function DetailsStep() {
  const b = useSite();
  const t = strings(b.lang);
  const d = b.details;
  const ready =
    d.owner_name.trim() &&
    d.pet_name.trim() &&
    d.phone.trim() &&
    d.notes.trim() &&
    (b.visitType !== 'home' || d.address.trim());
  return (
    <>
      <Back to="slot" />
      <h3 className="pw-h2">{t.yourDetails}</h3>
      <div className="pw-form">
        <Field name="owner_name" label={t.name} required />
        <Field name="pet_name" label={t.petName} required />
        <Field name="pet_type" label={t.petType}>
          <div className="pw-seg">
            {PET_TYPES.map((v) => (
              <button
                key={v}
                type="button"
                className={d.pet_type === v ? 'is-chosen' : ''}
                onClick={() => b.editDetail('pet_type', v)}
              >
                {t.pets[v]}
              </button>
            ))}
          </div>
        </Field>
        <Field name="phone" label={t.phone} required />
        <Field name="email" label={t.email} />
        {b.visitType === 'home' && <Field name="address" label={t.address} required />}
        <Field name="notes" label={t.message} required>
          <textarea
            name="notes"
            rows={2}
            value={d.notes}
            placeholder={t.messageHint}
            onChange={(e) => b.editDetail('notes', e.target.value)}
            onBlur={() => b.flushDetail('notes')}
          />
        </Field>
      </div>
      <button className="pw-primary" disabled={!ready} onClick={b.continueToReview}>
        {t.continue}
      </button>
    </>
  );
}

function BookingFacts() {
  const b = useSite();
  const t = strings(b.lang);
  const branch = getBranch(b.branchId);
  const service = getService(b.serviceId);
  const d = b.details;
  const rows: [string, ReactNode][] = [
    [t.serviceType, b.visitType === 'home' ? t.homeVisit : t.clinicVisit],
    [
      t.branch,
      branch ? (
        <>
          {branch.name}
          <small>{branch.address}</small>
        </>
      ) : (
        '—'
      ),
    ],
    [t.reason, service ? serviceName(service, b.lang) : '—'],
    [
      t.when,
      b.date && b.time
        ? `${formatDate(b.date, { weekday: 'long', month: 'long' }, locale(b.lang))}, ${formatTime(b.time)}`
        : '—',
    ],
    [t.pet, [d.pet_name, d.pet_type && `(${t.pets[d.pet_type] ?? d.pet_type})`].filter(Boolean).join(' ') || '—'],
    [t.owner, d.owner_name || '—'],
    [t.phone, d.phone || '—'],
  ];
  if (d.email) rows.push(['Email', d.email]);
  if (b.visitType === 'home') rows.push([t.address, d.address || '—']);
  if (d.notes) rows.push([t.message, d.notes]);
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
  const b = useSite();
  const t = strings(b.lang);
  return (
    <>
      <Back to="details" />
      <h3 className="pw-h2">{t.checkSend}</h3>
      <BookingFacts />
      <button className="pw-primary pw-send" onClick={() => b.sendRequest()}>
        {t.send}
      </button>
      <p className="pw-small">{t.willCall}</p>
    </>
  );
}

function DoneStep() {
  const b = useSite();
  const t = strings(b.lang);
  return (
    <div className="pw-done">
      <span className="pw-done-icon">
        <Check size={32} />
      </span>
      <h3 className="pw-h2">{t.sent}</h3>
      <p className="pw-lead">
        {t.refIs} <strong className="pw-ref">{b.ref}</strong>. {t.callShortly}
      </p>
      <BookingFacts />
      <button className="pw-secondary" onClick={b.restartBooking}>
        {t.another}
      </button>
    </div>
  );
}

export function EmergencyPanel() {
  const b = useSite();
  const t = strings(b.lang);
  const e = b.emergency;
  if (!e) return null;
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
            <h2>{t.sosTitle}</h2>
            <p>{t.sosLead}</p>
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
            <h3 className="pw-h3">
              {t.sosBranches} {cityName(e.city, b.lang)}
            </h3>
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
