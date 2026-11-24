/**
 * /listing/:id — one home: pictures and plan, the facts, what is near, the
 * EMI (to buy), and the site-visit panel the booker drives.
 */
import { BadgeCheck, Building2, CalendarDays, Heart, MapPin, Phone, School, Scale, Train } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { BuildingArt, FloorPlan } from "../components/Art";
import { CityMap } from "../components/CityMap";
import {
  bringFor,
  dateLabel,
  EMI_DEFAULTS,
  emi,
  getCity,
  getLender,
  getListing,
  getProject,
  hostOf,
  inr,
  inrShort,
  LENDERS,
  type Listing,
  priceLabel,
  slotsFor,
  timeLabel,
  visitAddress,
  visitDays,
  weekdayLabel,
} from "../data/homes";
import { bookVisit, pickSlot } from "../state/actions";
import { type Booking, emiOf, takenSlots, useStore } from "../state/store";
import { NotFound } from "./Misc";

export function ListingPage() {
  const { id } = useParams();
  const l = getListing(id);
  if (!l) return <NotFound what={`listing ${id}`} />;
  return <Listing_ l={l} key={l.id} />;
}

function Listing_({ l }: { l: Listing }) {
  const [view, setView] = useState<"tower" | "street" | "dusk" | "plan">("tower");
  const hearted = useStore((s) => s.shortlist.includes(l.id));
  const compared = useStore((s) => s.compare.includes(l.id));
  const project = getProject(l.project_id);
  const city = getCity(l.city)!;
  return (
    <div className="wrap lpage">
      <p className="crumb">
        <Link to="/listings">Find a home</Link> / {city.name} / {l.locality} / <span className="mono">{l.id}</span>
      </p>
      <div className="lpage-grid">
        <div className="lpage-main">
          <div className="gallery">
            <div className="gallery-stage">
              {view === "plan" ? <FloorPlan listing={l} /> : <BuildingArt id={l.id} palette={l.palette} floors={l.total_floors} view={view} label={`${l.society}, ${view} view`} />}
            </div>
            <div className="gallery-thumbs" role="tablist" aria-label="Pictures">
              {(["tower", "street", "dusk", "plan"] as const).map((v) => (
                <button key={v} type="button" role="tab" aria-selected={view === v} className={view === v ? "is-on" : ""} onClick={() => setView(v)}>
                  {v === "plan" ? <FloorPlan listing={l} /> : <BuildingArt id={l.id} palette={l.palette} floors={l.total_floors} view={v} />}
                  <span>{v === "plan" ? "Floor plan" : v === "tower" ? "Elevation" : v === "street" ? "Street" : "Evening"}</span>
                </button>
              ))}
            </div>
          </div>

          <header className="lpage-title">
            <div>
              <span className={`tag is-${l.kind}`}>{l.kind === "new" ? "New · Kosha project" : l.kind === "resale" ? "Resale" : "For rent"}</span>
              <h1>{l.title}</h1>
              <p className="lpage-where">
                <MapPin size={15} /> {l.address}
              </p>
            </div>
            <div className="lpage-price">
              <b>{l.deal === "rent" ? `${inr(l.rent ?? 0)}/mo` : inr(l.price ?? 0)}</b>
              <span>{l.deal === "rent" ? `Deposit ${inr(l.deposit ?? 0)}` : `${inrShort(l.price ?? 0)} · ${inr(l.price_per_sqft ?? 0)}/sq ft carpet`}</span>
              <div className="lpage-actions">
                <button type="button" className={`btn ghost${hearted ? " is-on" : ""}`} data-stage-part={`heart:${l.id}`} data-dock-avoid onClick={() => useStore.getState().toggleShortlist(l.id)}>
                  <Heart size={16} fill={hearted ? "currentColor" : "none"} /> {hearted ? "Shortlisted" : "Shortlist"}
                </button>
                <button type="button" className={`btn ghost${compared ? " is-on" : ""}`} data-stage-part={`compare:${l.id}`} data-dock-avoid onClick={() => useStore.getState().toggleCompare(l.id)}>
                  <Scale size={16} /> {compared ? "In compare" : "Compare"}
                </button>
              </div>
            </div>
          </header>

          <section className="facts" aria-label="Key facts">
            {[
              ["Configuration", `${l.bhk} BHK`],
              ["Carpet area", `${l.carpet_sqft.toLocaleString("en-IN")} sq ft`],
              ["Floor", `${l.floor} of ${l.total_floors}`],
              ["Facing", l.facing],
              ["Possession", l.possession === "ready" ? (l.deal === "rent" ? "Available now" : "Ready to move") : `Under construction · ${l.possession_date}`],
              ["Bathrooms", String(l.bathrooms)],
              ["Balconies", String(l.balconies)],
              ["Parking", l.parking ? `${l.parking} covered` : "None"],
              ["Furnishing", l.furnishing],
              ["Age", l.age_years ? `${l.age_years} years` : l.kind === "new" ? "New" : "—"],
              ["Reg. no. (demo)", l.rera],
              ["Listing id", l.id],
            ].map(([k, v]) => (
              <div key={k} className="fact">
                <span>{k}</span>
                <b className={k.startsWith("Reg") || k === "Listing id" ? "mono" : ""}>{v}</b>
              </div>
            ))}
          </section>

          {project ? (
            <section className="card project-strip">
              <div>
                <p className="eyebrow">Part of</p>
                <h3>
                  <Link to={`/project/${project.id}`} data-stage-thing={`project:${project.id}`}>
                    {project.name}
                  </Link>
                </h3>
                <p>{project.pitch}</p>
              </div>
              <div className="project-strip-stats">
                <span>
                  <b>{project.towers}</b> towers
                </span>
                <span>
                  <b>{project.acres}</b> acres
                </span>
                <span>
                  <b>{project.progress}%</b> built
                </span>
              </div>
            </section>
          ) : null}

          <section className="card">
            <h2>Amenities</h2>
            <ul className="amenities">
              {l.amenities.map((a) => (
                <li key={a}>
                  <BadgeCheck size={15} /> {a}
                </li>
              ))}
            </ul>
          </section>

          <section className="card near">
            <h2>What's near</h2>
            <div className="near-grid">
              <div>
                <h4>
                  <Building2 size={15} /> Offices
                </h4>
                {l.nearby.offices.map((o) => (
                  <p key={o.id}>
                    {o.name} <b>{o.km} km</b>
                  </p>
                ))}
              </div>
              <div>
                <h4>
                  <School size={15} /> Schools
                </h4>
                {l.nearby.schools.map((o) => (
                  <p key={o.id}>
                    {o.name} <b>{o.km} km</b>
                  </p>
                ))}
              </div>
              <div>
                <h4>
                  <Train size={15} /> Metro
                </h4>
                {l.nearby.metro.map((o) => (
                  <p key={o.id}>
                    {o.name} <b>{o.km} km</b>
                  </p>
                ))}
              </div>
            </div>
            <CityMap city={city} listings={[l]} focus={l.id} compact className="near-map" />
            <p className="fine">Straight-line distances from the drawn map; road distances are longer.</p>
          </section>

          {l.deal === "buy" ? <EmiCard l={l} /> : null}
        </div>
        <aside className="lpage-side">
          <VisitPanel l={l} />
        </aside>
      </div>
    </div>
  );
}

function EmiCard({ l }: { l: Listing }) {
  const saved = useStore((s) => s.emi[l.id]);
  const state = emiOf(saved ? { [l.id]: saved } : {}, l.id);
  const set = (p: Parameters<ReturnType<typeof useStore.getState>["setEmi"]>[1]) => useStore.getState().setEmi(l.id, p);
  const lender = getLender(state.lender) ?? LENDERS[1];
  const r = emi(l.price ?? 0, state.down_pct, state.tenure_years, lender.rate);
  const lenders = LENDERS.filter((x) => x.id !== "kosha-partner" || l.kind === "new");
  return (
    <section className="card emi" data-stage-thing="emi" data-stage-label="EMI calculator">
      <h2>EMI estimate</h2>
      <div className="emi-grid">
        <div className="emi-controls">
          <label data-stage-part="emi:down">
            <span>
              Down payment <b>{state.down_pct}%</b> · {inr(((l.price ?? 0) * state.down_pct) / 100)}
            </span>
            <input type="range" min={EMI_DEFAULTS.min_down_pct} max={90} step={5} value={state.down_pct} onChange={(e) => set({ down_pct: Number(e.target.value) })} />
          </label>
          <label data-stage-part="emi:tenure">
            <span>
              Tenure <b>{state.tenure_years} years</b>
            </span>
            <input type="range" min={5} max={EMI_DEFAULTS.max_tenure_years} step={1} value={state.tenure_years} onChange={(e) => set({ tenure_years: Number(e.target.value) })} />
          </label>
          <label data-stage-part="emi:lender">
            <span>Lender</span>
            <select value={lender.id} onChange={(e) => set({ lender: e.target.value })}>
              {lenders.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.name} · {x.rate}%
                </option>
              ))}
            </select>
          </label>
          <p className="fine">{lender.note}</p>
        </div>
        <div className="emi-result" data-stage-part="emi:result">
          <span>Monthly EMI</span>
          <b>{inr(r.emi)}</b>
          <dl>
            <dt>Loan</dt>
            <dd>{inr(r.principal)}</dd>
            <dt>Total interest</dt>
            <dd>{inr(r.interest)}</dd>
            <dt>Rate</dt>
            <dd>{lender.rate}% floating</dd>
          </dl>
          <p className="fine">Indicative, at the rates on this page. Excludes stamp duty, registration and GST.</p>
        </div>
      </div>
    </section>
  );
}

function VisitPanel({ l }: { l: Listing }) {
  const visit = useStore((s) => s.visit);
  const bookings = useStore((s) => s.bookings);
  const justBooked = useStore((s) => s.justBooked);
  const days = visitDays();
  const host = hostOf(l);
  const mine = visit.listing_id === l.id;
  const day = mine && visit.day && days.includes(visit.day) ? visit.day : days.find((d) => slotsFor(l, d)) ?? days[0];
  const taken = takenSlots(bookings, l.id);
  const slots = slotsFor(l, day, taken);
  const slot = mine ? visit.slot : null;
  const suits = mine ? visit.suits : null;
  const [error, setError] = useState("");
  const booked = bookings.filter((b) => b.listing_id === l.id);
  const latest = booked.find((b) => b.reference === justBooked) ?? null;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!slot) return setError("Pick a time first.");
    if (!visit.name.trim()) return setError("Add the name the visit is booked under.");
    setError("");
    bookVisit(l.id, slot, visit.name, visit.visitors);
  };

  return (
    <div className="visit" data-stage-thing="visit" data-stage-label="Book a site visit">
      <div className="visit-head">
        <CalendarDays size={18} />
        <div>
          <h2>Book a site visit</h2>
          <p>
            With {host.contact}, {l.kind === "new" ? "Kosha sales" : "Kosha Exchange"} · {host.slot_minutes} min · IST
          </p>
        </div>
      </div>
      {latest ? <VisitCard b={latest} /> : null}
      <div className="visit-days" role="tablist" aria-label="Day" data-stage-group>
        {days.map((d) => {
          const s = slotsFor(l, d, taken);
          const free = s ? s.filter((x) => x.free).length : 0;
          return (
            <button
              key={d}
              type="button"
              role="tab"
              aria-selected={d === day}
              disabled={!s}
              className={`vday${d === day ? " is-on" : ""}`}
              data-stage-thing={`visit-day:${d}`}
              onClick={() => useStore.getState().setVisit({ listing_id: l.id, day: d, slot: null, suits: null })}
            >
              <span>{weekdayLabel(d)}</span>
              <b>{Number(d.slice(8))}</b>
              <small>{s ? `${free} free` : "Closed"}</small>
            </button>
          );
        })}
      </div>
      {slots ? (
        <div className="visit-slots" data-stage-group>
          {(["morning", "afternoon", "evening"] as const).map((p) => {
            const list = slots.filter((s) => s.part === p);
            if (!list.length) return null;
            return (
              <div key={p} className="vpart">
                <span className="vpart-name">{p[0].toUpperCase() + p.slice(1)}</span>
                <div className="vpart-slots">
                  {list.map((s) => {
                    const fits = s.free && suits && (suits === "any" || suits === s.part);
                    return (
                      <button
                        key={s.id}
                        type="button"
                        disabled={!s.free}
                        className={`vslot${slot === s.id ? " is-on" : ""}${fits ? " is-fit" : ""}`}
                        data-stage-part={`slot:${s.id}`}
                        onClick={() => pickSlot(l.id, s.id)}
                        aria-pressed={slot === s.id}
                        title={s.free ? "Free" : "Taken"}
                      >
                        {timeLabel(s.time)}
                        {fits ? <em>suits you</em> : null}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="fine">The team does not take visits on {weekdayLabel(day)}s.</p>
      )}
      <form className="visit-form" onSubmit={submit}>
        <label data-stage-part="visit:name">
          <span>Name</span>
          <input value={mine ? visit.name : ""} placeholder="Your name" onChange={(e) => useStore.getState().setVisit({ listing_id: l.id, name: e.target.value })} />
        </label>
        <label data-stage-part="visit:visitors">
          <span>Visitors</span>
          <select value={mine ? visit.visitors : 1} onChange={(e) => useStore.getState().setVisit({ listing_id: l.id, visitors: Number(e.target.value) })}>
            {[1, 2, 3, 4, 5, 6].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="btn primary" data-stage-part="visit:book" data-dock-avoid>
          {slot ? `Book ${weekdayLabel(slot.slice(0, 10))} ${timeLabel(slot.slice(11))}` : "Book visit"}
        </button>
        {error ? <p className="form-error">{error}</p> : null}
      </form>
      <p className="fine">
        Meet at: {visitAddress(l)}. Free, no obligation. {dateLabel(days[0])} to {dateLabel(days[6])}.
      </p>
      {booked.filter((b) => b.reference !== latest?.reference).map((b) => (
        <VisitCard key={b.reference} b={b} compact />
      ))}
    </div>
  );
}

export function VisitCard({ b, compact }: { b: Booking; compact?: boolean }) {
  const l = getListing(b.listing_id);
  if (!l) return null;
  const host = hostOf(l);
  const day = b.slot.slice(0, 10);
  return (
    <article className={`vcard${compact ? " is-compact" : ""}`} data-stage-thing={`visit-card:${b.reference}`} data-stage-label={`Visit ${b.reference}`}>
      <div className="vcard-head">
        <BadgeCheck size={18} />
        <div>
          <p className="eyebrow">Site visit confirmed</p>
          <h3>
            {weekdayLabel(day)}, {dateLabel(day)} · {timeLabel(b.slot.slice(11))}
          </h3>
        </div>
        <span className="mono vcard-ref">{b.reference}</span>
      </div>
      <p className="vcard-what">
        <Link to={`/listing/${l.id}`}>{l.title}</Link> · {priceLabel(l)} · {b.name}
        {b.visitors > 1 ? ` + ${b.visitors - 1}` : ""}
      </p>
      {compact ? null : (
        <>
          <dl className="vcard-dl">
            <dt>
              <MapPin size={14} /> Where
            </dt>
            <dd>{visitAddress(l)}</dd>
            <dt>
              <Phone size={14} /> Your contact
            </dt>
            <dd>
              {host.contact} · <a href={`tel:${host.phone.replace(/\s/g, "")}`}>{host.phone}</a>
            </dd>
          </dl>
          <h4>What to bring</h4>
          <ul>
            {bringFor(l).map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        </>
      )}
    </article>
  );
}
