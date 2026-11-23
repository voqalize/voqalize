import { Check } from "lucide-react";
import { Link } from "react-router-dom";
import { EXTRA_MODULES, MODULES, PLANS, RULES, SITE } from "../data/product";
import { inr } from "../lib/format";
import { quote } from "../lib/pricing";
import { actions, useSite } from "../state/store";

const FILING = RULES.addons.find((a) => a.id === "filing")!;

export function Pricing() {
  const p = SITE.pricing_page;
  return (
    <div className="page pricing-page">
      <header className="page-head wrap">
        <h1>{p.title}</h1>
        <p className="page-intro">{p.intro}</p>
      </header>
      <Plans />
      <Calculator />
      <section className="section section-tight" data-stage-thing="faq" data-stage-label="FAQ">
        <div className="wrap faq-grid">
          <div>
            <h2 className="h-section">Questions about pricing</h2>
            <ul className="notes">
              {p.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </div>
          <dl className="faq">
            {p.faq.map((f) => (
              <div key={f.q}>
                <dt>{f.q}</dt>
                <dd>{f.a}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>
    </div>
  );
}

function Plans() {
  const chosen = quote(useSite((s) => s.pricing)).plan;
  return (
    <section className="section section-tight" data-stage-thing="plans" data-stage-label="Plans">
      <div className="wrap plans">
        {PLANS.map((pl) => {
          const adds = pl.includes_modules.filter((m) => MODULES.find((x) => x.id === m)?.min_plan === pl.id);
          return (
            <article key={pl.id} className={`plan${chosen === pl.id ? " is-chosen" : ""}`} data-stage-thing={`plan:${pl.id}`} data-stage-label={`${pl.name} plan`}>
              <div className="plan-top">
                <h2>{pl.name}</h2>
                {chosen === pl.id ? <span className="plan-flag">Your plan</span> : null}
              </div>
              <p className="plan-price">
                <span className="num plan-rate">₹{pl.price_per_employee_month}</span>
                <span>per employee a month</span>
              </p>
              <p className="plan-min">
                Minimum <span className="num">{inr(pl.minimum_month)}</span> a month, up to <span className="num">{pl.max_employees.toLocaleString("en-IN")}</span> employees
              </p>
              <p className="plan-summary">{pl.summary}</p>
              <ul className="plan-list">
                {pl.id === "starter" ? (
                  <li>
                    <Check size={16} /> Payroll, employee records, leave, payslips, income tax and PF, ESI and PT
                  </li>
                ) : (
                  <li>
                    <Check size={16} /> Everything in {pl.id === "growth" ? "Starter" : "Growth"}
                  </li>
                )}
                {pl.id !== "starter"
                  ? adds.map((m) => (
                      <li key={m}>
                        <Check size={16} /> {MODULES.find((x) => x.id === m)?.name}
                      </li>
                    ))
                  : null}
                <li>
                  <Check size={16} /> {pl.support}
                </li>
              </ul>
              <p className="plan-setup">
                {pl.setup_fee ? (
                  <>
                    Setup fee <span className="num">{inr(pl.setup_fee)}</span>, waived on annual billing
                  </>
                ) : (
                  "No setup fee"
                )}
              </p>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function Calculator() {
  const input = useSite((s) => s.pricing);
  const q = quote(input);
  const p = SITE.pricing_page;
  return (
    <section className="section calc-sec" data-stage-thing="calculator" data-stage-label="Calculator">
      <div className="wrap calc">
        <div className="calc-controls">
          <h2 className="h-section">{p.calculator_title}</h2>
          <p className="section-lede">{p.calculator_intro}</p>

          <div className="ctl" data-stage-part="pricing:headcount">
            <label htmlFor="hc" className="ctl-label">
              Employees
            </label>
            <div className="hc-row">
              <input
                id="hc"
                className="hc-input num"
                type="number"
                min={1}
                inputMode="numeric"
                value={input.headcount}
                onChange={(e) => e.target.value && actions.setPricing({ headcount: Number(e.target.value) })}
              />
              <input
                className="hc-range"
                type="range"
                min={1}
                max={1100}
                value={Math.min(input.headcount, 1100)}
                aria-label="Employees"
                onChange={(e) => actions.setPricing({ headcount: Number(e.target.value) })}
              />
            </div>
          </div>

          <fieldset className="ctl" data-stage-group="pricing-modules">
            <legend className="ctl-label">Modules</legend>
            <p className="ctl-hint">Payroll, records, leave, payslips, income tax and PF, ESI and PT are in every plan.</p>
            <div className="mod-checks">
              {EXTRA_MODULES.map((m) => {
                const on = input.modules.includes(m.id);
                const plan = PLANS.find((x) => x.id === m.min_plan)!;
                return (
                  <label key={m.id} className={`check${on ? " is-on" : ""}`} data-stage-part={`pricing:module:${m.id}`}>
                    <input type="checkbox" checked={on} onChange={() => actions.togglePricingModule(m.id)} />
                    <span className="check-name">{m.name}</span>
                    <span className="check-plan">{plan.name}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          <div className="ctl" data-stage-part="pricing:billing">
            <span className="ctl-label" id="billing-label">
              Billing
            </span>
            <div className="seg" role="radiogroup" aria-labelledby="billing-label">
              {(["monthly", "annual"] as const).map((b) => (
                <button type="button" key={b} role="radio" aria-checked={input.billing === b} className={input.billing === b ? "is-on" : ""} onClick={() => actions.setBilling(b)}>
                  {b === "monthly" ? "Monthly" : `Annual, ${RULES.annual_discount_pct}% off`}
                </button>
              ))}
            </div>
          </div>

          <label className={`check check-wide${input.filing ? " is-on" : ""}`} data-stage-part="pricing:filing">
            <input type="checkbox" checked={input.filing} onChange={() => actions.setPricing({ filing: !input.filing })} />
            <span className="check-name">
              {FILING.name}, <span className="num">₹{FILING.price_per_employee_month}</span> per employee a month
            </span>
            <span className="check-desc">{FILING.summary}</span>
          </label>
        </div>

        <div className="receipt" aria-live="polite" data-stage-group="breakdown">
          {q.status === "custom" ? (
            <div className="receipt-custom">
              <h3>Custom pricing</h3>
              <p>{RULES.above_max_employees}</p>
              <Link to="/book-demo" className="btn btn-primary" data-dock-avoid>
                Talk to sales
              </Link>
            </div>
          ) : (
            <>
              <div className="receipt-head">
                <p className="receipt-kind">Your plan</p>
                <p className="receipt-plan">{q.plan_name}</p>
                {q.why.length ? <p className="receipt-why">Because {q.why.join("; ")}.</p> : <p className="receipt-why">The cheapest plan that covers your team.</p>}
              </div>
              <ol className="lines">
                {q.lines.map((l) => (
                  <li key={l.key} className={`line line-${l.key}`} data-stage-part={`line:${l.key}`} data-stage-label={l.label}>
                    <span className="line-label">
                      {l.label}
                      {l.note ? <span className="line-note">{l.note}</span> : null}
                    </span>
                    <span className="line-amt num">{l.key === "discount" ? `− ${inr(-l.amount)}` : inr(l.amount)}</span>
                  </li>
                ))}
              </ol>
              <div className="receipt-foot">
                <Link to="/book-demo" className="btn btn-primary btn-block" data-dock-avoid>
                  Book a demo
                </Link>
                <p>{RULES.free_trial_days}-day free trial on any plan.</p>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
