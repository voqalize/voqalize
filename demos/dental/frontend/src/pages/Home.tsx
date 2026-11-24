import { AlertTriangle, Car, Clock, CreditCard, MapPin, Mic, Phone, ShieldCheck, Utensils } from "lucide-react";
import { Link } from "react-router-dom";
import {
  CATEGORY_LABEL,
  CLINIC,
  type Category,
  DATA,
  POLICY,
  daysAt,
  dentistsAt,
  durationText,
  priceRange,
  service,
  time12,
} from "../data/clinic";
import { shortDate } from "../data/slots";
import { displayName, persona } from "../persona";
import { useStore } from "../state/store";
import { callLabel } from "../voice/label";

const CATS: Category[] = ["appointment", "procedure", "imaging"];
const I = DATA.instructions;

/** The next free time for a few everyday visits, per branch, from the engine. */
function NextFree() {
  const cal = useStore((s) => s.cal);
  const rows = (["emergency", "checkup", "consult"] as const).flatMap((id) =>
    DATA.branches.map((b) => {
      const svc = service(id)!;
      const got = cal.nextDays(svc, { branch: b.id, days: 1 })[0];
      const slot = got?.[1][0];
      return { id, svc, b, slot, date: got?.[0] };
    }),
  );
  return (
    <div className="nextfree" aria-label="Next free times">
      <div className="nextfree-head">
        <p className="nextfree-title">Next free times</p>
        <p className="muted small">Live from our dentists' calendars</p>
      </div>
      <table>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.id}${r.b.id}`}>
              <th scope="row">
                {r.svc.name.replace(" (toothache)", "")}
                <span>{r.b.short}</span>
              </th>
              <td>
                {r.slot && r.date ? (
                  <>
                    <strong>{r.date === cal.today ? "Today" : shortDate(r.date)}</strong> {time12(r.slot.time)}
                  </>
                ) : (
                  <span className="muted">Call us</span>
                )}
              </td>
              <td className="nextfree-who">{r.slot?.dentist ? DATA.dentists.find((d) => d.id === r.slot!.dentist)?.short : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Link to="/book" className="btn btn-primary btn-block">
        See every free time
      </Link>
    </div>
  );
}

export function Home() {
  return (
    <div data-page="home">
      <section className="hero">
        <div className="wrap hero-grid">
          <div className="hero-copy">
            <p className="hero-kicker">
              <MapPin size={15} aria-hidden /> Indiranagar and HSR Layout, Bengaluru
            </p>
            <h1>Dentistry that takes its time, booked in a minute.</h1>
            <p className="lede">
              Five specialists across two clinics, open six days a week. See real free times on each dentist's calendar, book a check-up or a root canal,
              and know the price range and how to prepare before you arrive.
            </p>
            <div className="hero-actions">
              <Link to="/book" className="btn btn-primary btn-lg">
                Book an appointment
              </Link>
              <Link to="/my-appointments" className="btn btn-ghost btn-lg">
                Manage my appointments
              </Link>
            </div>
          </div>
          <NextFree />
        </div>
      </section>

      <div className="emergency-strip" data-stage-thing="emergency" data-stage-label="Emergency care">
        <div className="wrap">
          <AlertTriangle size={18} aria-hidden />
          <p>
            <strong>In pain today?</strong> Emergency visits can be booked for today from 30 minutes ahead. On Sundays call the on-call dentist at{" "}
            <a href={`tel:${CLINIC.emergency_line.replace(/\s/g, "")}`}>{CLINIC.emergency_line}</a>.
          </p>
          <Link to="/book" className="btn btn-sm btn-light" data-dock-avoid>
            Book an emergency visit
          </Link>
        </div>
      </div>

      <section className="section" id="services" data-stage-thing="services" data-stage-label="Services and prices">
        <div className="wrap">
          <header className="section-head">
            <h2>Services and prices</h2>
            <p className="muted">Price ranges are what most patients pay. Your dentist confirms the exact cost before any treatment starts.</p>
          </header>
          <div className="svc-groups">
            {CATS.map((cat) => (
              <div key={cat} className="svc-group">
                <h3>{CATEGORY_LABEL[cat]}</h3>
                <ul className="svc-table">
                  {DATA.services
                    .filter((s) => s.category === cat)
                    .map((s) => (
                      <li key={s.id}>
                        <div className="svc-main">
                          <strong>{s.name}</strong>
                          <span className="muted small">{s.summary}</span>
                          {s.price.note ? <span className="small svc-note">Price {s.price.note}.</span> : null}
                        </div>
                        <div className="svc-meta">
                          <span className="price">{priceRange(s)}</span>
                          <span className="muted small">
                            {durationText(s.duration_min)}
                            {s.sittings ? ` × ${s.sittings} sittings` : ""}
                          </span>
                        </div>
                      </li>
                    ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section section-alt" id="dentists" data-stage-thing="dentists" data-stage-label="Our dentists">
        <div className="wrap">
          <header className="section-head">
            <h2>Our dentists</h2>
            <p className="muted">Every dentist works from a fixed weekly schedule, so the days below are the days you can book them.</p>
          </header>
          <div className="dentists">
            {DATA.dentists.map((d) => (
              <article key={d.id} className="dentist" data-dentist={d.id}>
                <div className="dentist-top">
                  <span className="dentist-mono" aria-hidden>
                    {d.initials}
                  </span>
                  <div>
                    <h3>{d.name}</h3>
                    <p className="dentist-role">{d.role}</p>
                    <p className="small muted">
                      {d.qualification} · {d.years} years
                    </p>
                  </div>
                </div>
                <p className="small">{d.bio}</p>
                <dl className="dentist-facts">
                  <div>
                    <dt>Speaks</dt>
                    <dd>{d.languages.join(", ")}</dd>
                  </div>
                  {DATA.branches.map((b) => {
                    const days = daysAt(d, b.id);
                    return days ? (
                      <div key={b.id}>
                        <dt>{b.short}</dt>
                        <dd>{days}</dd>
                      </div>
                    ) : null;
                  })}
                </dl>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section" id="branches" data-stage-thing="branches" data-stage-label="Our branches">
        <div className="wrap">
          <header className="section-head">
            <h2>Two clinics, one record</h2>
            <p className="muted">Your history, X-rays and bills follow you between branches.</p>
          </header>
          <div className="branches">
            {DATA.branches.map((b) => (
              <article key={b.id} className="branch" data-branch={b.id}>
                <h3>{b.name}</h3>
                <p>{b.address}</p>
                <p className="small muted">{b.landmark}</p>
                <dl className="branch-facts">
                  <div data-stage-thing={b.id === "indiranagar" ? "hours" : undefined} data-stage-label="Opening hours">
                    <dt>
                      <Clock size={15} aria-hidden /> Hours
                    </dt>
                    <dd>
                      Monday to Saturday, {time12(b.open)} to {time12(b.close)}. Closed Sundays.
                    </dd>
                  </div>
                  <div data-stage-thing={b.id === "indiranagar" ? "parking" : undefined} data-stage-label="Parking">
                    <dt>
                      <Car size={15} aria-hidden /> Parking
                    </dt>
                    <dd>{b.parking}</dd>
                  </div>
                  <div>
                    <dt>
                      <Phone size={15} aria-hidden /> Phone
                    </dt>
                    <dd>{b.phone}</dd>
                  </div>
                </dl>
                <p className="small muted">
                  {b.chairs.length} chairs · {b.imaging.map((r) => `${r.label} (${r.does.map((x) => x.toUpperCase()).join(", ")})`).join(", ")} · Dentists here:{" "}
                  {dentistsAt(b.id).map((d) => d.short).join(", ")}
                </p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section section-alt" id="visit-info" data-stage-thing="visit-info" data-stage-label="Visit information">
        <div className="wrap">
          <header className="section-head">
            <h2>Before and after your visit</h2>
            <p className="muted">What our patients ask the front desk most, answered once.</p>
          </header>
          <div className="info-grid">
            <article className="info info-wide" data-stage-thing="eating" data-stage-label={I.eating.title}>
              <h3>
                <Utensils size={17} aria-hidden /> {I.eating.title}
              </h3>
              <p>{I.eating.general}</p>
              <dl className="prep-list">
                {Object.entries(I.eating.by_service ?? {}).map(([id, text]) => (
                  <div key={id}>
                    <dt>{service(id)?.name}</dt>
                    <dd>{text}</dd>
                  </div>
                ))}
              </dl>
            </article>
            <article className="info info-wide" data-stage-thing="aftercare" data-stage-label={I.aftercare.title}>
              <h3>{I.aftercare.title}</h3>
              <dl className="prep-list">
                {Object.entries(I.aftercare.by_service ?? {}).map(([id, text]) => (
                  <div key={id}>
                    <dt>{service(id)?.name}</dt>
                    <dd>{text}</dd>
                  </div>
                ))}
              </dl>
            </article>
            <article className="info" data-stage-thing="payment" data-stage-label={I.payment.title}>
              <h3>
                <CreditCard size={17} aria-hidden /> {I.payment.title}
              </h3>
              <p>{I.payment.text}</p>
            </article>
            <article className="info" data-stage-thing="insurance" data-stage-label={I.insurance.title}>
              <h3>
                <ShieldCheck size={17} aria-hidden /> {I.insurance.title}
              </h3>
              <p>{I.insurance.text}</p>
            </article>
            {(["what_to_bring", "late_arrival", "children", "sunday"] as const).map((k) => (
              <article key={k} className="info" data-stage-thing={k === "sunday" ? "sundays" : k.replace(/_/g, "-")} data-stage-label={I[k].title}>
                <h3>{I[k].title}</h3>
                <p>{I[k].text}</p>
              </article>
            ))}
          </div>
          <article className="policy" id="policy" data-stage-thing="policy" data-stage-label="Cancellation policy">
            <h3>Cancelling or moving an appointment</h3>
            <p>{POLICY.text}</p>
            <p className="small muted">{POLICY.rct_text}</p>
          </article>
        </div>
      </section>

      <section className="section talk-band">
        <div className="wrap talk-grid">
          <div>
            <h2>Rather say it than click it?</h2>
            <p className="muted">
              {displayName} is our {persona.role.toLowerCase()} voice assistant. She works from the same calendars and price list you see here, signs you in with a
              code on your phone, and asks a dentist to call you about anything clinical.
            </p>
          </div>
          <p className="talk-hint">
            <Mic size={18} aria-hidden /> Press <strong>{callLabel(persona.default_language)}</strong> at the bottom of the screen, and pick {persona.languages.map((l) => l.label).join(" or ")} beside it.
          </p>
        </div>
      </section>
    </div>
  );
}
