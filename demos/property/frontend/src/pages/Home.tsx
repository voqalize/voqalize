/** / — the developer's front door: a search, the projects, the cities, the Exchange. */
import { ArrowRight, Search } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ProjectArt } from "../components/Art";
import { ListingCard } from "../components/ListingCard";
import { BRAND, CITIES, type CityId, inrShort, LISTINGS, PROJECTS } from "../data/homes";
import { PERSONA } from "../data/persona";

const BUY_MAX = [7500000, 10000000, 15000000, 20000000, 30000000];
const RENT_MAX = [30000, 40000, 50000, 60000];

export function Home() {
  const navigate = useNavigate();
  const [city, setCity] = useState<CityId>("bengaluru");
  const [deal, setDeal] = useState<"buy" | "rent">("buy");
  const [bhk, setBhk] = useState<number[]>([]);
  const [max, setMax] = useState<number | "">("");
  const go = (e: React.FormEvent) => {
    e.preventDefault();
    const q = new URLSearchParams({ city, deal });
    if (bhk.length) q.set("bhk", bhk.join(","));
    if (max) q.set("budget_max", String(max));
    navigate(`/listings?${q}`);
  };
  const counts = (c: CityId) => LISTINGS.filter((l) => l.city === c).length;
  const exchange = LISTINGS.filter((l) => l.kind !== "new").slice(0, 3);

  return (
    <>
      <section className="hero">
        <div className="wrap hero-grid">
          <div className="hero-copy">
            <p className="eyebrow">Bengaluru · Pune · Hyderabad</p>
            <h1>
              Homes planned around <em>the way you live.</em>
            </h1>
            <p className="hero-lede">
              Seven Kosha projects and {LISTINGS.filter((l) => l.kind !== "new").length} resale and rental homes from {BRAND.exchange}. Tell {PERSONA.name}, our {PERSONA.role.toLowerCase()}, what you need: your budget, your office, your children's school.
            </p>
            <form className="hero-search" onSubmit={go} aria-label="Search homes">
              <div className="seg">
                {(["buy", "rent"] as const).map((d) => (
                  <button key={d} type="button" className={`chip${deal === d ? " is-on" : ""}`} onClick={() => (setDeal(d), setMax(""))}>
                    {d === "buy" ? "Buy" : "Rent"}
                  </button>
                ))}
              </div>
              <div className="hero-fields">
                <label>
                  <span>City</span>
                  <select value={city} onChange={(e) => setCity(e.target.value as CityId)}>
                    {CITIES.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>BHK</span>
                  <div className="chips tight">
                    {[1, 2, 3, 4].map((n) => (
                      <button key={n} type="button" className={`chip${bhk.includes(n) ? " is-on" : ""}`} onClick={() => setBhk(bhk.includes(n) ? bhk.filter((x) => x !== n) : [...bhk, n])}>
                        {n}
                      </button>
                    ))}
                  </div>
                </label>
                <label>
                  <span>Budget</span>
                  <select value={max} onChange={(e) => setMax(e.target.value ? Number(e.target.value) : "")}>
                    <option value="">Any</option>
                    {(deal === "buy" ? BUY_MAX : RENT_MAX).map((b) => (
                      <option key={b} value={b}>
                        Up to {inrShort(b)}
                        {deal === "rent" ? "/mo" : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <button type="submit" className="btn primary">
                  <Search size={16} /> Search
                </button>
              </div>
            </form>
          </div>
          <div className="hero-art">
            <ProjectArt project={PROJECTS[0]} />
            <div className="hero-art-card">
              <b>{PROJECTS[0].name}</b>
              <span>
                {PROJECTS[0].locality} · from {inrShort(PROJECTS[0].price_from)} · possession {PROJECTS[0].possession}
              </span>
            </div>
          </div>
        </div>
      </section>

      <section className="wrap section" id="projects">
        <div className="section-head">
          <h2>Kosha projects</h2>
          <Link to="/listings?deal=buy">All homes to buy <ArrowRight size={15} /></Link>
        </div>
        <div className="projects">
          {PROJECTS.map((p) => (
            <Link key={p.id} to={`/project/${p.id}`} className="pcard" data-stage-thing={`project:${p.id}`} data-stage-label={p.name}>
              <ProjectArt project={p} />
              <div className="pcard-body">
                <span className={`tag ${p.status === "ready" ? "is-ready" : "is-uc"}`}>{p.status === "ready" ? "Ready to move" : `Possession ${p.possession}`}</span>
                <h3>{p.name}</h3>
                <p>
                  {p.locality}, {CITIES.find((c) => c.id === p.city)!.name}
                </p>
                <p className="pcard-meta">
                  {p.configs.join(", ")} BHK · {inrShort(p.price_from)} – {inrShort(p.price_to)}
                </p>
              </div>
            </Link>
          ))}
        </div>
      </section>

      <section className="wrap section">
        <div className="section-head">
          <h2>Cities</h2>
        </div>
        <div className="cities">
          {CITIES.map((c) => (
            <Link key={c.id} to={`/listings?city=${c.id}`} className="ccard">
              <b>{c.name}</b>
              <span>
                {counts(c.id)} homes · {c.localities.map((l) => l.name).slice(0, 3).join(", ")}
              </span>
              <ArrowRight size={18} />
            </Link>
          ))}
        </div>
      </section>

      <section className="exchange">
        <div className="wrap">
          <div className="section-head">
            <div>
              <p className="eyebrow">{BRAND.exchange}</p>
              <h2>Resale and rental homes, verified by us</h2>
            </div>
            <Link to="/listings?deal=rent">Homes for rent <ArrowRight size={15} /></Link>
          </div>
          <div className="exchange-grid">
            {exchange.map((l) => (
              <ListingCard key={l.id} l={l} />
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
