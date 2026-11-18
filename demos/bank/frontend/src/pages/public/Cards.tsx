import { ArrowRight, Check, CircleAlert, Plane, RotateCcw, Trophy, Wallet } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { CardFace, Crumbs, OfferBanner } from "../../components/ui";
import { type CreditCardProduct, creditCardProduct, customer, inr, products } from "../../data/bank";
import { type CardValue, type SpendProfile, cardValue, customerProfile, rankCards } from "../../lib/bankmath";
import { persona } from "../../persona";
import { SAMPLE_PROFILE, SPEND_KEYS, compareIds, useAdvisor } from "../../state/advisor";
import { useSession } from "../../state/session";

export const SPEND_LABELS: Record<keyof SpendProfile, string> = {
  dining: "Dining out and food delivery",
  online: "Online shopping and subscriptions",
  groceries: "Groceries",
  travel: "Flights, hotels and trains",
  fuel: "Fuel",
  utilities: "Bills and utilities",
  other: "Everything else",
};

const rewardWord = (c: CreditCardProduct) => (c.reward_type === "cashback" ? "Cashback" : "Reward points");

const SHORT: Record<keyof SpendProfile, string> = {
  dining: "dining",
  online: "online",
  groceries: "groceries",
  travel: "travel",
  fuel: "fuel",
  utilities: "bills",
  other: "everything else",
};

/** The card's earn rates in words: the boosted categories first, then the base rate, then the lower ones. */
function earnLines(c: CreditCardProduct): string[] {
  const cash = c.reward_type === "cashback";
  const rates = (cash ? c.cashback_rates : c.earn) ?? {};
  const base = rates.base ?? 0;
  const per = c.earn_per ?? 100;
  const what = (k: string) => SPEND_LABELS[k as keyof SpendProfile]?.toLowerCase() ?? k;
  const say = (v: number) => (cash ? `${v}%` : `${v} point${v === 1 ? "" : "s"} per ₹${per}`);
  const others = Object.entries(rates).filter(([k, v]) => k !== "base" && v !== base);
  const up = others.filter(([, v]) => v > base).sort((a, b) => b[1] - a[1]);
  const down = others.filter(([, v]) => v < base);
  return [
    ...up.map(([k, v]) => `${say(v)} on ${what(k)}`),
    `${say(base)} everywhere else${cash ? "" : `, 1 point = ₹${c.point_value}`}`,
    ...down.map(([k, v]) => (v === 0 ? `No ${cash ? "cashback" : "points"} on ${what(k)}` : `${say(v)} on ${what(k)}`)),
  ];
}

const lounge = (c: CreditCardProduct) => {
  const d = c.lounge.domestic_per_year;
  const i = c.lounge.international_per_year;
  const dom = d == null ? "Unlimited domestic" : d ? `${d} domestic` : "";
  const intl = i ? `${i} international` : "";
  return [dom, intl].filter(Boolean).join(", ") + (dom || intl ? " visits a year" : "None");
};

/** Signed in, her salary is known and every card is checked against its minimum. */
function useKnownIncome(): number | undefined {
  const signedIn = useSession((s) => s.signedIn);
  return signedIn ? customer.profile.monthly_income : undefined;
}

/** The note on a card whose minimum income is above hers. */
function IncomeNote({ card, income }: { card: CreditCardProduct; income: number }) {
  return (
    <p className="cr-income" data-stage-thing={`income:${card.id}`} data-stage-label={`${card.name.replace("Anvaya ", "")} income requirement`}>
      <CircleAlert size={14} aria-hidden />
      <span>
        <strong>Income below requirement.</strong> Needs {inr(card.min_income_monthly)} a month; yours is {inr(income)}.
      </span>
    </p>
  );
}

// ─── The value breakdown, shared by the catalogue and the detail page ─────────

export function ValueBreakdown({ card, v }: { card: CreditCardProduct; v: CardValue }) {
  return (
    <dl className="value-rows">
      <div>
        <dt>{rewardWord(card)}</dt>
        <dd className="num">+{inr(v.yearly_rewards)}</dd>
      </div>
      <div>
        <dt>Fuel surcharge saved</dt>
        <dd className="num">{v.fuel_saving_yearly ? `+${inr(v.fuel_saving_yearly)}` : "—"}</dd>
      </div>
      <div>
        <dt>Lounge visits</dt>
        <dd className="num">{v.lounge_value ? `+${inr(v.lounge_value)}` : "—"}</dd>
      </div>
      <div>
        <dt>Annual fee</dt>
        <dd className="num">{v.fee_waived ? <span className="waived">Waived</span> : v.fee ? `−${inr(v.fee)}` : "Free"}</dd>
      </div>
    </dl>
  );
}

// ─── Spend panel ─────────────────────────────────────────────────────────────

function SpendPanel() {
  const profile = useAdvisor((s) => s.profile);
  const fromCustomer = useAdvisor((s) => s.fromCustomer);
  const setProfile = useAdvisor((s) => s.setProfile);
  const signedIn = useSession((s) => s.signedIn);
  const total = Object.values(profile).reduce((a, b) => a + b, 0);
  return (
    <section className="spend card" aria-labelledby="spend-h" data-stage-thing="spend-panel" data-stage-label="Your monthly spend">
      <div className="spend-head">
        <h2 id="spend-h" className="side-h">
          Your monthly spend
        </h2>
        <span className="spend-total num" data-stage-thing="spend-total" data-stage-label="Monthly total">
          {inr(total)}
        </span>
      </div>
      <p className="side-small">Move the sliders to your usual month. The cards re-rank as you go.</p>
      {signedIn ? (
        <button type="button" className={`btn btn-sm btn-block ${fromCustomer ? "btn-quiet" : "btn-outline"}`} onClick={() => setProfile(customerProfile(), true)} data-stage-thing="spend:real" data-stage-label="Use my real spend">
          <Wallet size={15} aria-hidden /> {fromCustomer ? "Using your last 3 months" : "Use my real spend"}
        </button>
      ) : null}
      <div className="spend-rows">
        {SPEND_KEYS.map((k) => (
          <div key={k} className="spend-row" data-stage-part={`spend:${k}`} data-stage-thing={`spend:${k}`} data-stage-label={SPEND_LABELS[k]}>
            <label htmlFor={`spend-${k}`}>{SPEND_LABELS[k]}</label>
            <div className="spend-ctl">
              <input
                id={`spend-${k}`}
                type="range"
                min={0}
                max={k === "travel" ? 60000 : 40000}
                step={500}
                value={profile[k]}
                style={{ ["--pct" as string]: `${(profile[k] / (k === "travel" ? 60000 : 40000)) * 100}%` }}
                onChange={(e) => setProfile({ [k]: Number(e.target.value) })}
              />
              <div className="input-wrap spend-num">
                <span className="input-prefix">₹</span>
                <input
                  className="input has-prefix num"
                  inputMode="numeric"
                  aria-label={`${SPEND_LABELS[k]}, rupees a month`}
                  value={profile[k].toLocaleString("en-IN")}
                  onChange={(e) => setProfile({ [k]: Number(e.target.value.replace(/\D/g, "")) || 0 })}
                />
              </div>
            </div>
          </div>
        ))}
      </div>
      <button type="button" className="link-btn spend-reset" onClick={() => setProfile(SAMPLE_PROFILE)}>
        <RotateCcw size={13} aria-hidden /> Reset to a sample month
      </button>
    </section>
  );
}

// ─── /cards ──────────────────────────────────────────────────────────────────

export function CardsPage() {
  const profile = useAdvisor((s) => s.profile);
  const income = useKnownIncome();
  const ranked = rankCards(profile, income);
  const navigate = useNavigate();
  return (
    <main className="page cards-page" data-stage-thing="screen:cards" data-stage-label="Credit cards">
      <div className="wrap">
        <Crumbs items={[{ label: "Credit cards" }]} />
        <header className="page-head page-head-row">
          <div>
            <h1 className="page-title">Credit cards, ranked for how you spend</h1>
            <p className="page-lede">
              Each card's yearly value is its rewards, fuel savings and lounge visits on your spending, minus the fee if you would not spend enough to have it waived.
              {income != null ? " Signed in, the cards your income qualifies for come first." : ""} Ask {persona.name} and the comparison opens with your numbers.
            </p>
          </div>
          <div className="head-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                useAdvisor.getState().setCompare(null);
                navigate("/cards/compare");
              }}
            >
              Compare the top 3
            </button>
            <Link to="/cards/emi" className="btn btn-outline">
              EMI planner
            </Link>
          </div>
        </header>
        <OfferBanner kind="card" />
        <div className="cards-grid">
          <ol className="card-list" aria-label="Cards, best value first">
            {ranked.map((v, i) => {
              const c = creditCardProduct(v.card_id)!;
              return (
                <li key={c.id} className={`card-row${i === 0 && !v.below_income ? " is-best" : ""}${v.below_income ? " is-ineligible" : ""}`} data-stage-thing={`card:${c.id}`} data-stage-label={c.name}>
                  <div className="cr-face">
                    <span className="cr-rank num" aria-label={`Rank ${i + 1}`}>
                      {i + 1}
                    </span>
                    <CardFace card={c} />
                  </div>
                  <div className="cr-body">
                    <div className="cr-title">
                      <h2>
                        <Link to={`/cards/${c.id}`}>{c.name}</Link>
                      </h2>
                      {i === 0 && !v.below_income ? (
                        <span className="chip chip-accent">
                          <Trophy size={12} aria-hidden /> Best for your spend
                        </span>
                      ) : null}
                    </div>
                    <p className="cr-for">Best for {c.best_for}</p>
                    {v.below_income && income != null ? <IncomeNote card={c} income={income} /> : null}
                    <ul className="cr-high">
                      {c.highlights.slice(0, 3).map((h) => (
                        <li key={h}>
                          <Check size={13} aria-hidden /> {h}
                        </li>
                      ))}
                    </ul>
                    <p className="cr-fees">
                      Joining {c.joining_fee ? inr(c.joining_fee) : "free"}, annual {c.annual_fee ? inr(c.annual_fee) : "free"}
                      {c.fee_waiver_spend ? `, waived on ${inr(c.fee_waiver_spend)} a year` : ""}
                    </p>
                    <div className="cr-links">
                      <Link to={`/cards/${c.id}`} className="text-link">
                        Details
                      </Link>
                      <Link to={`/cards/apply?card=${c.id}`} className="text-link">
                        Apply
                      </Link>
                    </div>
                  </div>
                  <div className="cr-value" data-stage-thing={`value:${c.id}`} data-stage-label={`${c.name.replace("Anvaya ", "")} yearly value`}>
                    <span className="cr-value-label">Worth to you a year</span>
                    <span className={`cr-value-num num${v.net_yearly < 0 ? " is-neg" : ""}`}>{inr(v.net_yearly)}</span>
                    <ValueBreakdown card={c} v={v} />
                  </div>
                </li>
              );
            })}
          </ol>
          <aside className="cards-side">
            <SpendPanel />
          </aside>
        </div>
      </div>
    </main>
  );
}

// ─── /cards/:id ──────────────────────────────────────────────────────────────

export function CardDetail() {
  const { id = "" } = useParams();
  const card = creditCardProduct(id);
  const profile = useAdvisor((s) => s.profile);
  const income = useKnownIncome();
  if (!card) {
    return (
      <main className="page" data-stage-thing="screen:card_detail" data-stage-label="Card">
        <div className="wrap section">
          <h1 className="page-title">No such card</h1>
          <p>
            We have five cards: {products.credit_cards.map((c) => c.name).join(", ")}. <Link to="/cards">See them all</Link>.
          </p>
        </div>
      </main>
    );
  }
  const v = cardValue(card, profile);
  const ranked = rankCards(profile, income);
  const rank = ranked.findIndex((x) => x.card_id === card.id) + 1;
  const below = ranked[rank - 1]?.below_income ?? false;
  return (
    <main className="page card-detail" data-stage-thing="screen:card_detail" data-stage-label={card.name}>
      <div className="wrap">
        <Crumbs items={[{ to: "/cards", label: "Credit cards" }, { label: card.name }]} />
        <section className="cd-hero" style={{ ["--card" as string]: card.color }}>
          <CardFace card={card} size="lg" />
          <div className="cd-copy">
            <p className="cd-tier">
              {card.tier}, {card.network}
            </p>
            <h1 className="page-title">{card.name}</h1>
            <p className="page-lede">Best for {card.best_for}.</p>
            <ul className="cr-high">
              {card.highlights.map((h) => (
                <li key={h}>
                  <Check size={13} aria-hidden /> {h}
                </li>
              ))}
            </ul>
            <div className="head-actions">
              <Link to={`/cards/apply?card=${card.id}`} className="btn btn-accent btn-lg" data-stage-thing="cta:apply" data-stage-label="Apply">
                Apply for {card.name.replace("Anvaya ", "")}
              </Link>
              <Link
                to="/cards/compare"
                className="btn btn-outline"
                onClick={() => {
                  const top = ranked.map((x) => x.card_id).filter((x) => x !== card.id).slice(0, 2);
                  useAdvisor.getState().setCompare([card.id, ...top]);
                }}
              >
                Compare
              </Link>
            </div>
          </div>
          <div className="cd-value card" data-stage-thing={`value:${card.id}`} data-stage-label="Yearly value">
            <span className="cr-value-label">Worth to you a year</span>
            <span className={`cr-value-num num${v.net_yearly < 0 ? " is-neg" : ""}`}>{inr(v.net_yearly)}</span>
            <ValueBreakdown card={card} v={v} />
            <p className="side-small">
              Ranked {rank} of {products.credit_cards.length} on your spend of {inr(Object.values(profile).reduce((a, b) => a + b, 0))} a month.{" "}
              <Link to="/cards">Change it</Link>
            </p>
            {below && income != null ? <IncomeNote card={card} income={income} /> : null}
          </div>
        </section>

        <div className="facts-grid">
          <section className="facts card" data-stage-thing="fees" data-stage-label="Fees">
            <h2 className="side-h">Fees</h2>
            <dl className="kv">
              <div>
                <dt>Joining fee</dt>
                <dd className="num">{card.joining_fee ? inr(card.joining_fee) : "Free"}</dd>
              </div>
              <div>
                <dt>Annual fee</dt>
                <dd className="num">{card.annual_fee ? inr(card.annual_fee) : "Free"}</dd>
              </div>
              <div>
                <dt>Annual fee waived on</dt>
                <dd className="num">{inr(card.fee_waiver_spend)} spend a year</dd>
              </div>
              <div data-stage-thing="forex" data-stage-label="Forex markup">
                <dt>Foreign currency markup</dt>
                <dd className="num">{card.forex_markup}%</dd>
              </div>
              <div data-stage-thing="interest" data-stage-label="Interest">
                <dt>Interest on unpaid balance</dt>
                <dd className="num">
                  {card.interest_monthly}% a month ({+(card.interest_monthly * 12).toFixed(1)}% a year)
                </dd>
              </div>
            </dl>
          </section>
          <section className="facts card" data-stage-thing="rewards" data-stage-label="Rewards">
            <h2 className="side-h">{rewardWord(card)}</h2>
            <ul className="plain-list">
              {earnLines(card).map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
            {card.caps.accelerated_points_monthly ? <p className="side-small">Bonus points capped at {card.caps.accelerated_points_monthly.toLocaleString("en-IN")} a month.</p> : null}
            {card.caps.accelerated_cashback_monthly ? <p className="side-small">Bonus cashback capped at {inr(card.caps.accelerated_cashback_monthly)} a month.</p> : null}
            {card.caps.fuel_cashback_monthly ? <p className="side-small">Fuel cashback capped at {inr(card.caps.fuel_cashback_monthly)} a month.</p> : null}
          </section>
          <section className="facts card">
            <h2 className="side-h">Travel and fuel</h2>
            <dl className="kv">
              <div data-stage-thing="lounge" data-stage-label="Lounge access">
                <dt>
                  <Plane size={14} aria-hidden /> Airport lounges
                </dt>
                <dd>{lounge(card)}</dd>
              </div>
              <div data-stage-thing="fuel" data-stage-label="Fuel surcharge">
                <dt>Fuel surcharge waiver</dt>
                <dd>{card.fuel.surcharge_waiver}</dd>
              </div>
            </dl>
          </section>
          <section className="facts card" data-stage-thing="eligibility" data-stage-label="Eligibility">
            <h2 className="side-h">Who can apply</h2>
            <dl className="kv">
              <div>
                <dt>Monthly income from</dt>
                <dd className="num">{inr(card.min_income_monthly)}</dd>
              </div>
              <div>
                <dt>Age</dt>
                <dd>21 to 65</dd>
              </div>
            </dl>
            <p className="side-small">You need a PAN and an address in India.</p>
          </section>
        </div>
      </div>
    </main>
  );
}

// ─── /cards/compare ──────────────────────────────────────────────────────────

export function CardsCompare() {
  const profile = useAdvisor((s) => s.profile);
  useAdvisor((s) => s.compare);
  const ids = compareIds();
  const cards = ids.map((id) => creditCardProduct(id)).filter((c): c is CreditCardProduct => !!c);
  const income = useKnownIncome();
  const values = cards.map((c) => ({ ...cardValue(c, profile), below_income: income != null && income < c.min_income_monthly }));
  // The best is the highest value among the cards her income qualifies for (none: no best).
  const best = values.reduce((b, v, i) => (!v.below_income && (b < 0 || v.net_yearly > values[b].net_yearly) ? i : b), -1);
  const total = Object.values(profile).reduce((a, b) => a + b, 0);
  const rows: { label: string; thing: string; cell: (c: CreditCardProduct, v: CardValue) => React.ReactNode }[] = [
    { label: "Joining fee", thing: "joining", cell: (c) => (c.joining_fee ? inr(c.joining_fee) : "Free") },
    { label: "Annual fee", thing: "annual", cell: (c) => (c.annual_fee ? inr(c.annual_fee) : "Free") },
    { label: "Fee waived on", thing: "waiver", cell: (c, v) => <>{inr(c.fee_waiver_spend)} a year{v.fee_waived ? <span className="waived"> (you qualify)</span> : null}</> },
    {
      label: "Rewards",
      thing: "rewards",
      cell: (c) => (
        <ul className="plain-list tight">
          {earnLines(c).slice(0, 4).map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      ),
    },
    { label: "Lounge access", thing: "lounge", cell: (c) => lounge(c) },
    { label: "Fuel surcharge waiver", thing: "fuel", cell: (c) => c.fuel.surcharge_waiver },
    { label: "Forex markup", thing: "forex", cell: (c) => `${c.forex_markup}%` },
    { label: "Your rewards a year", thing: "rewards-value", cell: (_c, v) => <span className="num">{inr(v.yearly_rewards)}</span> },
    {
      label: "Your estimated yearly value",
      thing: "value",
      cell: (_c, v) => <strong className={`num big-num${v.net_yearly < 0 ? " is-neg" : ""}`}>{inr(v.net_yearly)}</strong>,
    },
    { label: "Best for", thing: "best-for", cell: (c) => c.best_for },
    {
      label: "Monthly income needed",
      thing: "min-income",
      cell: (c, v) => (
        <>
          <span className="num">{inr(c.min_income_monthly)}</span>
          {v.below_income && income != null ? <span className="ct-income-short"> (yours {inr(income)})</span> : null}
        </>
      ),
    },
  ];
  return (
    <main className="page compare" data-stage-thing="screen:cards_compare" data-stage-label="Compare cards">
      <div className="wrap">
        <Crumbs items={[{ to: "/cards", label: "Credit cards" }, { label: "Compare" }]} />
        <header className="page-head page-head-row">
          <div>
            <h1 className="page-title">Side by side</h1>
            <p className="page-lede" data-stage-thing="compare:profile" data-stage-label="Spend profile">
              Worked out on {inr(total)} a month:{" "}
              {SPEND_KEYS.filter((k) => profile[k])
                .map((k) => `${SHORT[k]} ${inr(profile[k])}`)
                .join(", ")}
              .{" "}
              <Link to="/cards">Change your spend</Link>
            </p>
          </div>
        </header>
        <div className="compare-scroll" role="region" aria-label="Card comparison" tabIndex={0}>
          <table className="compare-table" style={{ ["--cols" as string]: cards.length }}>
            <thead>
              <tr>
                <th scope="col" className="ct-corner">
                  <span className="sr-only">Feature</span>
                </th>
                {cards.map((c, i) => (
                  <th key={c.id} scope="col" className={i === best ? "is-best" : undefined} data-stage-thing={`compare:${c.id}`} data-stage-label={c.name}>
                    {i === best ? (
                      <span className="chip chip-accent ct-best">
                        <Trophy size={12} aria-hidden /> Best for you
                      </span>
                    ) : values[i].below_income ? (
                      <span className="chip chip-warn ct-best" data-stage-thing={`income:${c.id}`} data-stage-label={`${c.name.replace("Anvaya ", "")} income requirement`}>
                        <CircleAlert size={12} aria-hidden /> Income below requirement
                      </span>
                    ) : (
                      <span className="ct-best-space" />
                    )}
                    <CardFace card={c} size="sm" />
                    <Link to={`/cards/${c.id}`} className="ct-name">
                      {c.name}
                    </Link>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.thing} className={r.thing === "value" ? "ct-value-row" : undefined}>
                  <th scope="row">{r.label}</th>
                  {cards.map((c, i) => (
                    <td key={c.id} className={i === best ? "is-best" : undefined} data-stage-thing={r.thing === "value" ? `compare-value:${c.id}` : undefined} data-stage-label={r.thing === "value" ? `${c.name.replace("Anvaya ", "")} yearly value` : undefined}>
                      {r.cell(c, values[i])}
                    </td>
                  ))}
                </tr>
              ))}
              <tr>
                <th scope="row">
                  <span className="sr-only">Apply</span>
                </th>
                {cards.map((c, i) => (
                  <td key={c.id} className={i === best ? "is-best" : undefined}>
                    <Link to={`/cards/apply?card=${c.id}`} className={`btn btn-sm ${i === best ? "btn-accent" : "btn-outline"}`}>
                      Apply <ArrowRight size={14} aria-hidden />
                    </Link>
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}
