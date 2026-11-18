import { ArrowRight, BadgeCheck, Clock3, FileCheck2, Landmark, PhoneCall, Upload } from "lucide-react";
import { Link } from "react-router-dom";
import { PRODUCT_IDS, customer, policies, productById } from "../data";
import { PRODUCT_BLURB, Portrait, ProductIcon, TalkButton } from "../components/bits";
import { daysUntil, fmtDate, inr } from "../lib/format";
import { persona } from "../persona";
import { quote } from "../quote/rating";

/** A "from" price per product: its cheapest sensible quote from the rating tables. */
const FROM: Record<string, Record<string, string>> = {
  car: { vehicle_class: "hatchback", fuel: "petrol", registration_year: "2023", ex_showroom: "600000", city: "jaipur", claim_free_years: "5" },
  bike: { bike_type: "scooter", engine_cc: "upto_150", registration_year: "2023", ex_showroom: "80000", city: "jaipur", claim_free_years: "5" },
  health: { cover_type: "individual", adults: "1", children: "0", eldest_age: "25", sum_insured: "500000", city: "jaipur", pre_existing: "no" },
  term: { age: "25", gender: "female", smoker: "no", cover_amount: "5000000", cover_till_age: "60" },
  home: { ownership: "tenant", property_type: "apartment", building_value: "0", contents_value: "300000", building_age: "5", city: "jaipur" },
  travel: { region: "asia", trip_days: "5", travellers: "1", eldest_age: "30" },
};
const fromPrice = (p: (typeof PRODUCT_IDS)[number]) => quote(p, FROM[p], []).total;

export function Home() {
  const next = [...policies].filter((p) => p.product !== "term" && p.product !== "travel" && daysUntil(p.end) >= 0).sort((a, b) => a.end.localeCompare(b.end))[0];
  return (
    <div className="home">
      <section className="hero">
        <div className="wrap hero-grid">
          <div className="hero-copy">
            <p className="eyebrow">Insurance, explained before you buy</p>
            <h1 className="display">
              Cover that opens <em>when it rains.</em>
            </h1>
            <p className="lede">
              Get a premium in under two minutes, read your policy in plain words, and file a claim without the paperwork maze. {persona.name}, our insurance guide, can walk you through any of it.
            </p>
            <div className="hero-ctas">
              <Link to="/quote" className="btn btn-primary btn-lg">
                Get a quote <ArrowRight size={18} aria-hidden />
              </Link>
              <TalkButton className="btn btn-ghost btn-lg" />
            </div>
            <ul className="hero-facts">
              <li><BadgeCheck size={16} aria-hidden /> Premiums from our published rating tables</li>
              <li><Clock3 size={16} aria-hidden /> Claims helpline open 24x7</li>
            </ul>
          </div>
          <div className="hero-art" aria-hidden>
            <HeroArt />
            <div className="hero-card">
              <Portrait className="hero-face" />
              <div>
                <p className="hero-card-name">{persona.name}</p>
                <p className="hero-card-role">{persona.role}</p>
                <p className="hero-card-quote">“Ask me if flood damage to your engine is covered. I’ll show you the clause.”</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="wrap welcome-strip" aria-label="Your account">
        <div className="welcome-who">
          <span className="avatar-chip lg" aria-hidden>RK</span>
          <div>
            <p className="welcome-hi">Welcome back, {customer.first_name}</p>
            <p className="muted small">
              {policies.length} policies with Chhatri{customer.past_claims.length ? ` · ${customer.past_claims.length} claim${customer.past_claims.length > 1 ? "s" : ""} settled` : ""}
            </p>
          </div>
        </div>
        {next ? (
          <div className="welcome-next">
            <p className="muted small">Next renewal</p>
            <p>
              <strong>{next.plan}</strong> on {fmtDate(next.end)} <span className="muted">({daysUntil(next.end)} days)</span>
            </p>
          </div>
        ) : null}
        <div className="welcome-actions">
          <Link to="/my-policies" className="btn btn-ghost btn-sm">My policies</Link>
          <Link to="/claim" className="btn btn-ghost btn-sm">Make a claim</Link>
        </div>
      </section>

      <section className="wrap section" aria-labelledby="products-h">
        <div className="section-head">
          <h2 id="products-h" className="h2">What would you like to protect?</h2>
          <p className="muted">Six plans, one account. Every price below is a real quote from our tables.</p>
        </div>
        <div className="product-grid">
          {PRODUCT_IDS.map((p) => {
            const spec = productById(p)!;
            return (
              <Link key={p} to={`/insurance/${p}`} className={`product-card pc-${p}`} data-stage-part={`product:${p}`}>
                <span className="product-icon"><ProductIcon product={p} size={24} /></span>
                <span className="product-name">{spec.name}</span>
                <span className="product-plan">{spec.plan}</span>
                <span className="product-blurb">{PRODUCT_BLURB[p]}</span>
                <span className="product-from">
                  from <strong>{inr(fromPrice(p))}</strong>
                  <span className="muted">{p === "travel" ? " a trip" : " a year"}</span>
                </span>
                <span className="product-go">
                  Get a quote <ArrowRight size={16} aria-hidden />
                </span>
              </Link>
            );
          })}
        </div>
      </section>

      <section className="claims-how" aria-labelledby="claims-h">
        <div className="wrap">
          <div className="section-head">
            <h2 id="claims-h" className="h2">How a claim works</h2>
            <p className="muted">One form, saved as you go. Nothing is submitted until you press Submit.</p>
          </div>
          <ol className="steps">
            <li>
              <span className="step-icon"><PhoneCall size={20} aria-hidden /></span>
              <h3>Tell us what happened</h3>
              <p>Choose motor or health, pick the policy, and describe the incident or the hospital stay.</p>
            </li>
            <li>
              <span className="step-icon"><Upload size={20} aria-hidden /></span>
              <h3>Add your documents</h3>
              <p>Upload the RC, photos, bills or discharge summary. We only ask for what your claim needs.</p>
            </li>
            <li>
              <span className="step-icon"><FileCheck2 size={20} aria-hidden /></span>
              <h3>Review and submit</h3>
              <p>See every answer on one page, tick the declaration and get your claim reference at once.</p>
            </li>
            <li>
              <span className="step-icon"><Landmark size={20} aria-hidden /></span>
              <h3>Get paid by NEFT</h3>
              <p>Cashless at network garages and hospitals, or straight to your bank account on file.</p>
            </li>
          </ol>
          <div className="claims-cta">
            <Link to="/claim" className="btn btn-primary">Start a claim</Link>
            <TalkButton className="btn btn-ghost-light" label={`Ask ${persona.name} to fill it with you`} />
          </div>
        </div>
      </section>
    </div>
  );
}

function HeroArt() {
  return (
    <svg className="hero-svg" viewBox="0 0 520 420" role="presentation">
      <defs>
        <linearGradient id="h-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#d9ebe5" />
          <stop offset="1" stopColor="#f6efe2" />
        </linearGradient>
        <linearGradient id="h-can" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#f4b23f" />
          <stop offset="1" stopColor="#e5791b" />
        </linearGradient>
      </defs>
      <rect x="0" y="0" width="520" height="420" rx="28" fill="url(#h-sky)" />
      {Array.from({ length: 42 }).map((_, i) => {
        const x = (i * 61) % 520;
        const y = (i * 37) % 200;
        return <line key={i} x1={x} y1={y} x2={x - 8} y2={y + 22} stroke="#7fa9a1" strokeWidth="2" strokeLinecap="round" opacity=".45" />;
      })}
      <g transform="translate(260 205)">
        <path d="M-170 0c4-92 79-160 170-160S166-92 170 0c-17-15-36-22-57-22s-40 7-57 22c-16-15-35-22-56-22S-40-15-56 0c-17-15-36-22-57-22S-153-15-170 0Z" fill="url(#h-can)" />
        <path d="M0-160c-34 36-52 89-56 160M0-160c34 36 52 89 56 160" stroke="#fff" strokeOpacity=".5" strokeWidth="4" fill="none" />
        <path d="M0-22V150a26 26 0 0 1-52 0" stroke="#0f3d3e" strokeWidth="11" strokeLinecap="round" fill="none" />
        <circle cx="0" cy="-166" r="9" fill="#0f3d3e" />
      </g>
      <g transform="translate(70 330)" fill="#0f3d3e">
        <rect x="0" y="20" width="120" height="70" rx="6" opacity=".9" />
        <path d="M-8 24 60-22l68 46Z" opacity=".9" />
        <rect x="46" y="50" width="28" height="40" rx="3" fill="#f6efe2" />
      </g>
      <g transform="translate(300 352)">
        <rect x="0" y="12" width="150" height="36" rx="16" fill="#155e5a" />
        <path d="M24 12 46-12h56l26 24Z" fill="#155e5a" />
        <circle cx="34" cy="50" r="13" fill="#10282a" />
        <circle cx="118" cy="50" r="13" fill="#10282a" />
        <rect x="56" y="-6" width="40" height="16" rx="4" fill="#d9ebe5" />
      </g>
      <rect x="0" y="398" width="520" height="22" rx="0" fill="#e8dfcd" />
    </svg>
  );
}
