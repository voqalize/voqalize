/** Salt & Cypress Spa: the intro and policy, category chips, treatment cards, the guest's spa bookings. */
import { CalendarCheck, Clock3, Hourglass, Users, XCircle } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { PageHeader, Segments } from "../components/Shell";
import { SPA } from "../data";
import { money, price } from "../lib/format";
import { openTreatment, setSpaCategory, useStay } from "../state/store";
import "../styles/experiences.css";

/** Activities | Spa | Meetings, the same row on all three Experiences pages. */
export function ExperienceTabs() {
  const nav = useNavigate();
  const path = useLocation().pathname;
  const value = path.includes("/spa") ? "spa" : path.includes("/meetings") ? "meetings" : "activities";
  return (
    <Segments
      items={[
        { id: "activities", label: "Activities", thing: "exp-activities" },
        { id: "spa", label: "Spa", thing: "exp-spa" },
        { id: "meetings", label: "Meetings", thing: "exp-meetings" },
      ]}
      value={value}
      onChange={(id) => nav(`/${id}`)}
    />
  );
}

/** The guest's bookings of one kind, as confirmed cards. */
export function BookingList({ kind }: { kind: "spa" | "activity" | "meeting" }) {
  const list = useStay((s) => s.bookings).filter((b) => b.kind === kind);
  if (!list.length) return null;
  return (
    <div className="ex-bookings">
      {list.map((b) => (
        <div key={b.id} className="ex-booking">
          <CalendarCheck size={20} />
          <div>
            <b>{b.label}</b>
            <span>{b.when}</span>
          </div>
          {b.total ? <em>{money(b.total)}</em> : <em>Free</em>}
        </div>
      ))}
    </div>
  );
}

const CATS: { id: string | null; label: string }[] = [
  { id: null, label: "All" },
  { id: "massage", label: "Massage" },
  { id: "facial", label: "Facial" },
  { id: "ritual", label: "Ritual" },
  { id: "nails", label: "Nails" },
];

export function Spa() {
  const cat = useStay((s) => s.spaCategory);
  const list = SPA.treatments.filter((t) => !cat || t.category === cat);
  const booked = useStay((s) => s.bookings.some((b) => b.kind === "spa"));
  return (
    <div className="page" data-stage-place="spa">
      <PageHeader title="Experiences" sub="Book the spa, the courses and the coast" tabs={<ExperienceTabs />} />
      <div className="ex-wrap">
        <section className="ex-hero" data-stage-thing="spa-intro" data-stage-label={SPA.name}>
          <Stones />
          <span className="ex-eyebrow">The spa</span>
          <h2>{SPA.name}</h2>
          <div className="ex-hero-facts">
            <p>
              <Clock3 size={15} />
              <span>Open daily, {SPA.hours}</span>
            </p>
            <p>
              <Hourglass size={15} />
              <span>{SPA.arrive}</span>
            </p>
            <p data-stage-thing="spa-cancellation" data-stage-label="Cancellation policy">
              <XCircle size={15} />
              <span>{SPA.cancellation}</span>
            </p>
          </div>
        </section>

        {booked ? (
          <>
            <div className="ex-section-title">
              <h2>Your appointments</h2>
            </div>
            <BookingList kind="spa" />
          </>
        ) : null}

        <div className="ex-section-title">
          <h2>Treatments</h2>
          <span>Plus {SPA.service_charge_pct}% service charge</span>
        </div>
        <div className="ex-chips" data-stage-group role="tablist" aria-label="Treatment type">
          {CATS.map((c) => {
            const on = cat === c.id;
            return (
              <button key={c.label} type="button" role="tab" aria-selected={on} className={`ex-chip${on ? " is-on" : ""}`} onClick={() => setSpaCategory(c.id)} data-stage-thing={`spa-cat-${c.id ?? "all"}`} data-stage-label={c.label}>
                {c.label}
              </button>
            );
          })}
        </div>

        {list.map((t) => (
          <button key={t.id} type="button" className="ex-card" onClick={() => openTreatment(t.id)} data-stage-thing={`treatment-${t.id}`} data-stage-label={`${t.name}, ${t.minutes} min`}>
            <div className="ex-card-head">
              <div>
                <h3>{t.name}</h3>
                <p>{t.desc}</p>
              </div>
              <div className="ex-price">
                <b>{price(t.price)}</b>
                <small>{t.for_two ? "for two" : "per guest"}</small>
              </div>
            </div>
            <div className="ex-card-meta">
              <span>
                <Clock3 size={13} /> {t.minutes} min
              </span>
              {t.for_two ? (
                <span>
                  <Users size={13} /> Side by side, two therapists
                </span>
              ) : null}
              <span>
                {t.therapists.length} {t.therapists.length === 1 ? "therapist" : "therapists"}
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

/** Stacked massage stones beside a sprig of cypress. */
function Stones() {
  return (
    <svg className="ex-hero-art" viewBox="0 0 140 120" aria-hidden>
      <circle cx="84" cy="44" r="34" fill="#fffdf9" opacity="0.65" />
      <path d="M112 18c-6 10-6 22 0 34M112 26l-8-4M112 34l8-5M112 42l-8-3M112 50l7-3" stroke="#2c5a5e" strokeWidth="1.6" strokeLinecap="round" fill="none" opacity="0.7" />
      <ellipse cx="74" cy="100" rx="40" ry="11" fill="#13212b" />
      <ellipse cx="72" cy="96" rx="40" ry="10" fill="#33434d" />
      <ellipse cx="76" cy="79" rx="31" ry="9" fill="#6e7a81" />
      <ellipse cx="74" cy="76" rx="31" ry="8.5" fill="#9aa4a9" />
      <ellipse cx="72" cy="61" rx="22" ry="7" fill="#33434d" />
      <ellipse cx="73" cy="59" rx="22" ry="6.5" fill="#6e7a81" />
      <ellipse cx="75" cy="46.5" rx="13" ry="5" fill="#c9a467" />
      <ellipse cx="74" cy="45" rx="13" ry="4.5" fill="#e0c48f" />
      <path d="M50 74c8 3 30 3 40-1" stroke="#fffdf9" strokeWidth="1.4" strokeLinecap="round" opacity="0.6" fill="none" />
      <path d="M56 94c10 3 30 3 40-1" stroke="#fffdf9" strokeWidth="1.2" strokeLinecap="round" opacity="0.35" fill="none" />
    </svg>
  );
}
