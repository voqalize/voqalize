/** Project, compare, shortlist, visits, not found. */
import { Check, Clock, Heart, MapPin, Phone } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ProjectArt } from "../components/Art";
import { CityMap } from "../components/CityMap";
import { ListingCard } from "../components/ListingCard";
import {
  amountOf,
  getCity,
  getListing,
  getProject,
  inr,
  inrShort,
  type Listing,
  LISTINGS,
  priceLabel,
  timeLabel,
  type Weekday,
} from "../data/homes";
import { useStore } from "../state/store";
import { VisitCard } from "./ListingPage";

export function NotFound({ what }: { what?: string }) {
  return (
    <div className="wrap empty-page">
      <h1>Not found</h1>
      <p>{what ? `There is no ${what}.` : "That page does not exist."}</p>
      <Link to="/listings" className="btn primary">
        Find a home
      </Link>
    </div>
  );
}

const DAY_NAMES: [Weekday, string][] = [
  ["mon", "Mon"],
  ["tue", "Tue"],
  ["wed", "Wed"],
  ["thu", "Thu"],
  ["fri", "Fri"],
  ["sat", "Sat"],
  ["sun", "Sun"],
];

export function ProjectPage() {
  const { id } = useParams();
  const p = getProject(id);
  if (!p) return <NotFound what={`project ${id}`} />;
  const city = getCity(p.city)!;
  const units = p.listing_ids.map((x) => getListing(x)!).filter(Boolean);
  const rentals = LISTINGS.filter((l) => l.project_id === p.id && l.deal === "rent");
  const configs = p.configs.map((bhk) => {
    const us = units.filter((u) => u.bhk === bhk);
    return { bhk, n: us.length, min: Math.min(...us.map((u) => u.carpet_sqft)), max: Math.max(...us.map((u) => u.carpet_sqft)), from: Math.min(...us.map(amountOf)) };
  });
  return (
    <div className="wrap ppage">
      <p className="crumb">
        <Link to="/#projects">Projects</Link> / {city.name} / {p.name}
      </p>
      <div className="ppage-hero">
        <ProjectArt project={p} className="ppage-art" />
        <div className="ppage-intro">
          <span className={`tag ${p.status === "ready" ? "is-ready" : "is-uc"}`}>{p.status === "ready" ? "Ready to move · OC received" : `Under construction · possession ${p.possession}`}</span>
          <h1>{p.name}</h1>
          <p className="lpage-where">
            <MapPin size={15} /> {p.locality}, {city.name}
          </p>
          <p className="ppage-pitch">{p.pitch}</p>
          <div className="ppage-stats">
            <span>
              <b>{inrShort(p.price_from)}</b> onwards
            </span>
            <span>
              <b>{p.configs.join(", ")}</b> BHK
            </span>
            <span>
              <b>{p.towers}</b> towers · <b>{p.floors}</b> floors
            </span>
            <span>
              <b>{p.units}</b> homes on <b>{p.acres}</b> acres
            </span>
          </div>
          <p className="mono fine">Reg. no. (demo) {p.rera} · launched {p.launched}</p>
        </div>
      </div>

      <div className="ppage-grid">
        <div>
          <section className="card">
            <h2>Construction</h2>
            <div className="progress">
              <div style={{ width: `${p.progress}%` }} />
            </div>
            <p className="fine">{p.progress}% complete</p>
            <ol className="milestones">
              {p.milestones.map(([name, state]) => (
                <li key={name} className={state === "done" ? "is-done" : state === "in progress" ? "is-now" : ""}>
                  {state === "done" ? <Check size={14} /> : <Clock size={14} />} <b>{name}</b> <span>{state}</span>
                </li>
              ))}
            </ol>
          </section>
          <section className="card">
            <h2>Configurations</h2>
            <table className="table">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Carpet area</th>
                  <th>Available</th>
                  <th>From</th>
                </tr>
              </thead>
              <tbody>
                {configs.map((c) => (
                  <tr key={c.bhk}>
                    <td>{c.bhk} BHK</td>
                    <td>
                      {c.min.toLocaleString("en-IN")}
                      {c.max !== c.min ? `–${c.max.toLocaleString("en-IN")}` : ""} sq ft
                    </td>
                    <td>{c.n}</td>
                    <td>{inr(c.from)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section className="section-tight">
            <h2>Homes available</h2>
            <div className="results">
              {[...units, ...rentals].map((l) => (
                <ListingCard key={l.id} l={l} />
              ))}
            </div>
          </section>
        </div>
        <aside>
          <section className="card">
            <h2>Location</h2>
            <CityMap city={city} listings={[]} compact projects={[{ id: p.id, name: p.name, x: p.x, y: p.y }]} />
            <ul className="near-list">
              {[...p.nearby.offices.slice(0, 2), ...p.nearby.schools.slice(0, 2), ...p.nearby.metro.slice(0, 1)].map((n) => (
                <li key={n.id}>
                  {n.name} <b>{n.km} km</b>
                </li>
              ))}
            </ul>
          </section>
          <section className="card">
            <h2>Amenities</h2>
            <ul className="amenities">
              {p.amenities.map((a) => (
                <li key={a}>
                  <Check size={14} /> {a}
                </li>
              ))}
            </ul>
          </section>
          <section className="card">
            <h2>Sales office</h2>
            <p>{p.address}</p>
            <p>
              <Phone size={14} /> {p.team.contact} · {p.team.phone}
            </p>
            <table className="table hours">
              <tbody>
                {DAY_NAMES.map(([k, name]) => (
                  <tr key={k}>
                    <td>{name}</td>
                    <td>{p.team.hours[k] ? `${timeLabel(p.team.hours[k]![0])} – ${timeLabel(p.team.hours[k]![1])}` : "Closed"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="fine">Book a visit from any home's page.</p>
          </section>
        </aside>
      </div>
    </div>
  );
}

interface Row {
  key: string;
  label: string;
  value: (l: Listing) => string;
  /** Lower is better (price), higher is better (area), or no winner. */
  better?: (l: Listing) => number;
  dir?: "low" | "high";
}

const ROWS: Row[] = [
  { key: "price", label: "Price", value: (l) => (l.deal === "rent" ? `${inr(l.rent ?? 0)}/mo` : inr(l.price ?? 0)), better: amountOf, dir: "low" },
  { key: "carpet", label: "Carpet area", value: (l) => `${l.carpet_sqft.toLocaleString("en-IN")} sq ft`, better: (l) => l.carpet_sqft, dir: "high" },
  { key: "psf", label: "Price per sq ft", value: (l) => (l.price_per_sqft ? inr(l.price_per_sqft) : "—"), better: (l) => l.price_per_sqft ?? Number.POSITIVE_INFINITY, dir: "low" },
  { key: "bhk", label: "Configuration", value: (l) => `${l.bhk} BHK · ${l.bathrooms} baths` },
  { key: "possession", label: "Possession", value: (l) => (l.possession === "ready" ? "Ready to move" : l.possession_date), better: (l) => (l.possession === "ready" ? 0 : 1), dir: "low" },
  { key: "floor", label: "Floor", value: (l) => `${l.floor} of ${l.total_floors}` },
  { key: "facing", label: "Facing", value: (l) => l.facing },
  { key: "metro", label: "Nearest metro", value: (l) => `${l.nearby.metro[0]?.name} · ${l.nearby.metro[0]?.km} km`, better: (l) => l.nearby.metro[0]?.km ?? 99, dir: "low" },
  { key: "school", label: "Nearest school", value: (l) => `${l.nearby.schools[0]?.name} · ${l.nearby.schools[0]?.km} km`, better: (l) => l.nearby.schools[0]?.km ?? 99, dir: "low" },
  { key: "office", label: "Nearest office", value: (l) => `${l.nearby.offices[0]?.name} · ${l.nearby.offices[0]?.km} km`, better: (l) => l.nearby.offices[0]?.km ?? 99, dir: "low" },
  { key: "amenities", label: "Amenities", value: (l) => `${l.amenities.length}: ${l.amenities.slice(0, 4).join(", ")}${l.amenities.length > 4 ? "…" : ""}`, better: (l) => l.amenities.length, dir: "high" },
  { key: "reg", label: "Reg. no. (demo)", value: (l) => l.rera },
];

export function ComparePage() {
  const [params] = useSearchParams();
  const stored = useStore((s) => s.compare);
  const ids = (params.get("ids")?.split(",") ?? stored).map((x) => x.trim().toUpperCase());
  const homes = ids.map((x) => getListing(x)).filter((x): x is Listing => !!x).slice(0, 3);
  if (homes.length < 2) {
    return (
      <div className="wrap empty-page">
        <h1>Compare homes</h1>
        <p>Tick Compare on two or three homes, then come back here.</p>
        <Link to="/listings" className="btn primary">
          Find a home
        </Link>
      </div>
    );
  }
  return (
    <div className="wrap cpage">
      <p className="crumb">
        <Link to="/listings">Find a home</Link> / Compare
      </p>
      <h1>Side by side</h1>
      <div className="ctable" style={{ gridTemplateColumns: `minmax(120px, 0.7fr) repeat(${homes.length}, minmax(0, 1fr))` }}>
        <div />
        {homes.map((l) => (
          <div key={l.id} className="ctable-head" data-stage-thing={`listing:${l.id}`}>
            <Link to={`/listing/${l.id}`}>
              <b>{l.title}</b>
            </Link>
            <span>
              {l.locality} · <span className="mono">{l.id}</span>
            </span>
            <span className="lcard-price">{priceLabel(l)}</span>
          </div>
        ))}
        {ROWS.map((row) => {
          const scores = row.better ? homes.map(row.better) : [];
          const best = row.better ? (row.dir === "low" ? Math.min(...scores) : Math.max(...scores)) : null;
          const unique = best !== null && scores.filter((s) => s === best).length === 1 && homes.every((h) => h.deal === homes[0].deal || row.key !== "price");
          const winner = homes.map((h) => (unique ? row.better!(h) === best : false));
          const winnerName = homes.find((_, i) => winner[i])?.id;
          return (
            <div key={row.key} className="ctable-row" data-stage-thing={`row:${row.key}`} data-stage-label={winnerName ? `${row.label}: ${winnerName}` : row.label}>
              <div className="ctable-label">{row.label}</div>
              {homes.map((l, i) => (
                <div key={l.id} className={`ctable-cell${winner[i] ? " is-best" : ""}`}>
                  {row.value(l)}
                  {winner[i] ? <Check size={14} /> : null}
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function ShortlistPage() {
  const ids = useStore((s) => s.shortlist);
  const homes = ids.map((x) => getListing(x)).filter((x): x is Listing => !!x);
  return (
    <div className="wrap section">
      <h1>
        <Heart size={22} /> Shortlist
      </h1>
      {homes.length ? (
        <div className="results grid3">
          {homes.map((l) => (
            <ListingCard key={l.id} l={l} />
          ))}
        </div>
      ) : (
        <p className="empty">Tap the heart on any home to keep it here.</p>
      )}
    </div>
  );
}

export function VisitsPage() {
  const bookings = useStore((s) => s.bookings);
  const sorted = [...bookings].sort((a, b) => (a.slot < b.slot ? -1 : 1));
  return (
    <div className="wrap section">
      <h1>My site visits</h1>
      {sorted.length ? (
        <div className="visits-list">
          {sorted.map((b) => (
            <div key={b.reference} className="visits-item">
              <VisitCard b={b} />
              <button type="button" className="btn link" onClick={() => useStore.getState().cancelBooking(b.reference)}>
                Cancel this visit
              </button>
            </div>
          ))}
        </div>
      ) : (
        <p className="empty">No visits booked yet. Book one from any home's page.</p>
      )}
    </div>
  );
}
