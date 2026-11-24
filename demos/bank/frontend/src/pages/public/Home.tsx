import { ArrowRight, CreditCard, Landmark, LockKeyhole, Mic, UserRoundPlus } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { brand, customer, inr, products } from "../../data/bank";
import { persona } from "../../persona";
import { useSession } from "../../state/session";

const JOBS = [
  {
    to: "/app",
    icon: LockKeyhole,
    title: "My banking",
    line: "Balances, spends, bills and card controls. Ask, and the answer opens on screen. Anything that moves money waits for your yes.",
    ask: "How much did I spend on food last month?",
  },
  {
    to: "/open-account",
    icon: UserRoundPlus,
    title: "Open an account",
    line: "A six-step savings application that fills in as you talk, with each step explained before you answer it.",
    ask: "I'd like a zero-balance account.",
  },
  {
    to: "/cards",
    icon: CreditCard,
    title: "Credit cards",
    line: "Five cards ranked by what they would earn you a year on your own spending, with the fee counted.",
    ask: "Which card pays me most for travel?",
  },
  {
    to: "/loans",
    icon: Landmark,
    title: "Loans",
    line: "Your EMI with the working shown, how much you can borrow, and the papers to keep ready.",
    ask: "What's my EMI on ₹40 lakh over 20 years?",
  },
];

export function Home() {
  const signedIn = useSession((s) => s.signedIn);
  const signIn = useSession((s) => s.signIn);
  const navigate = useNavigate();
  const sb = customer.accounts.find((a) => a.id === "sb");
  const topRate = (v: (typeof products.savings_variants)[number]) => Math.max(...v.rates.map((r) => r.rate));

  return (
    <main className="page home" data-stage-thing="screen:home" data-stage-label="Home">
      <section className="hero">
        <div className="wrap hero-grid">
          <div className="hero-copy">
            <h1 className="hero-title">{brand.tagline}</h1>
            <p className="hero-lede">
              Savings, cards and loans from {brand.name}, with {persona.name}, an assistant you can talk to in{" "}
              {persona.languages.map((l) => persona.language_names[l]).join(" or ")}. Ask a question about your money and the answer opens on the page in
              front of you.
            </p>
            <div className="hero-ctas">
              <Link to="/cards" className="btn btn-accent btn-lg">
                <CreditCard size={18} aria-hidden /> Find your card
              </Link>
              <Link to="/open-account" className="btn btn-outline-light btn-lg">
                Open a savings account
              </Link>
            </div>
            <p className="hero-fine">Fictional bank. Sample data throughout; nothing here is a real offer.</p>
          </div>

          <aside className="hero-login" aria-label="Sign in to My banking" data-stage-thing="login-box" data-stage-label="Sign in">
            {signedIn ? (
              <>
                <p className="hl-kicker">Welcome back</p>
                <p className="hl-name">{customer.profile.name}</p>
                {sb ? (
                  <div className="hl-balance">
                    <span>{sb.name}</span>
                    <strong className="num">{inr(sb.available)}</strong>
                    <span className="hl-sub">available, {sb.number_masked}</span>
                  </div>
                ) : null}
                <Link to="/app" className="btn btn-primary btn-block">
                  Go to My banking <ArrowRight size={16} aria-hidden />
                </Link>
              </>
            ) : (
              <>
                <p className="hl-title">Sign in to My banking</p>
                <label className="field-label" htmlFor="home-cid">
                  Customer ID
                </label>
                <input id="home-cid" className="input" readOnly value={customer.profile.customer_id} />
                <label className="field-label" htmlFor="home-pin">
                  6-digit PIN
                </label>
                <input id="home-pin" className="input" type="password" readOnly value="123456" />
                <button
                  type="button"
                  className="btn btn-primary btn-block"
                  onClick={() => {
                    signIn();
                    navigate("/app");
                  }}
                >
                  Sign in
                </button>
                <p className="hl-note">Demo sign-in: the sample customer's details are filled in. There is no real login.</p>
                <p className="hl-new">
                  New to {brand.short}? <Link to="/open-account">Open an account</Link>
                </p>
              </>
            )}
          </aside>
        </div>
      </section>

      <section className="wrap section">
        <div className="section-head">
          <h2 className="section-title">Four things {persona.name} does for you</h2>
          <p className="section-lede">Each one has its own page. Start a call from any of them, or use the page by hand; it works the same either way.</p>
        </div>
        <div className="jobs">
          {JOBS.map((j) => (
            <Link key={j.to} to={j.to} className="job" data-stage-thing={`job:${j.to}`} data-stage-label={j.title}>
              <j.icon size={22} className="job-icon" aria-hidden />
              <h3 className="job-title">{j.title}</h3>
              <p className="job-line">{j.line}</p>
              <p className="job-ask">
                <Mic size={13} aria-hidden /> “{j.ask}”
              </p>
              <span className="job-go">
                Open <ArrowRight size={15} aria-hidden />
              </span>
            </Link>
          ))}
        </div>
      </section>

      <section className="section band">
        <div className="wrap">
          <div className="section-head">
            <h2 className="section-title">Savings accounts</h2>
            <p className="section-lede">Four accounts, one application. Switch between them later without a new KYC.</p>
          </div>
          <div className="variants">
            {products.savings_variants.map((v) => (
              <article key={v.id} className="variant" data-stage-thing={`variant:${v.id}`} data-stage-label={v.name}>
                <h3 className="variant-name">{v.name.replace("Anvaya ", "")}</h3>
                <p className="variant-tag">{v.tagline}</p>
                <dl className="variant-facts">
                  <div>
                    <dt>Interest</dt>
                    <dd className="num">up to {topRate(v)}%</dd>
                  </div>
                  <div>
                    <dt>Minimum balance</dt>
                    <dd className="num">{v.min_balance ? inr(v.min_balance) : "None"}</dd>
                  </div>
                </dl>
                <Link to="/open-account" className="text-link">
                  Open this account <ArrowRight size={14} aria-hidden />
                </Link>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="wrap section" id="rates">
        <div className="section-head">
          <h2 className="section-title">Today's rates</h2>
          <p className="section-lede">Per year. Senior citizens earn {products.fd.senior_bonus}% more on fixed deposits.</p>
        </div>
        <div className="rates">
          <div className="rate-table" data-stage-thing="rates:fd" data-stage-label="Fixed deposit rates">
            <h3 className="rate-h">Fixed deposits</h3>
            <table>
              <thead>
                <tr>
                  <th scope="col">Tenure</th>
                  <th scope="col" className="r">
                    Rate
                  </th>
                  <th scope="col" className="r">
                    Senior citizens
                  </th>
                </tr>
              </thead>
              <tbody>
                {products.fd.rates.map((r) => (
                  <tr key={r.label}>
                    <td>{r.label}</td>
                    <td className="r num strong">{r.rate.toFixed(2)}%</td>
                    <td className="r num">{(r.rate + products.fd.senior_bonus).toFixed(2)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Link to="/app/deposits" className="text-link">
              Book a deposit in My banking <ArrowRight size={14} aria-hidden />
            </Link>
          </div>
          <div className="rate-loans" data-stage-thing="rates:loans" data-stage-label="Loan rates">
            <h3 className="rate-h">Loans, from</h3>
            <ul>
              {products.loans.map((l) => (
                <li key={l.id}>
                  <Link to={`/loans/${l.id}`}>
                    <span className="rl-name">{l.short}</span>
                    <span className="rl-rate num">{l.rate_min}%</span>
                    <span className="rl-sub">up to {l.tenure_max_months / 12} years</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="wrap section">
        <div className="fiction-note">
          <h2>This bank does not exist</h2>
          <p>
            {brand.name} is made up for a Voqalize voice demo. The products, rates, fees and the customer you sign in as ({customer.profile.name}) are
            sample data. Nothing you type is sent to a bank, and no account, card or loan is real.
          </p>
        </div>
      </section>
    </main>
  );
}
