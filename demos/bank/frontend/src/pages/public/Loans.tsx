import { ArrowRight, Check, FileText, Wallet } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Crumbs, OfferBanner, SliderRow, lakh } from "../../components/ui";
import { type LoanProduct, inr, loanProduct, products } from "../../data/bank";
import { amortise } from "../../lib/amortise";
import { loanEligibility } from "../../lib/bankmath";
import { persona } from "../../persona";
import { LOAN_TYPES, type LoanType, customerElig, useAdvisor } from "../../state/advisor";
import { useSession } from "../../state/session";

const fmtR = (n: number) => `₹${Math.round(n).toLocaleString("en-IN")}`;
const tenureText = (m: number) => (m % 12 === 0 ? `${m / 12} years` : m >= 12 ? `${m} months` : `${m} months`);

function amountStep(l: LoanProduct) {
  return l.amount_max >= 10000000 ? 100000 : l.amount_max >= 1000000 ? 10000 : 5000;
}
function tenureStep(l: LoanProduct) {
  return l.tenure_max_months >= 120 ? 12 : l.tenure_max_months > 36 ? 6 : 3;
}

// ─── The calculator, with its working ─────────────────────────────────────────

export function EmiCalculator({ type, compact = false }: { type: LoanType; compact?: boolean }) {
  const loan = loanProduct(type)!;
  const calc = useAdvisor((s) => s.calc[type]);
  const setCalc = useAdvisor((s) => s.setCalc);
  const a = amortise(calc.amount, calc.rate, calc.tenure);
  const fy = a.first_year;
  const fyTotal = fy.interest + fy.principal || 1;
  return (
    <section className="card calc" aria-labelledby={`calc-h-${type}`} data-stage-thing="loan:calculator" data-stage-label="EMI calculator">
      <h2 id={`calc-h-${type}`} className="side-h">
        EMI calculator{compact ? `, ${loan.short.toLowerCase()}` : ""}
      </h2>
      <div className="calc-grid">
        <div className="calc-inputs">
          <SliderRow
            label="Loan amount"
            part="amount"
            value={calc.amount}
            min={loan.amount_min}
            max={Math.min(loan.amount_max, type === "home" ? 30000000 : loan.amount_max)}
            step={amountStep(loan)}
            format={(n) => lakh(n)}
            onChange={(n) => setCalc(type, { amount: n })}
          />
          <SliderRow
            label="Tenure"
            part="tenure"
            value={calc.tenure}
            min={loan.tenure_min_months}
            max={loan.tenure_max_months}
            step={tenureStep(loan)}
            format={tenureText}
            onChange={(n) => setCalc(type, { tenure: n })}
          />
          <SliderRow
            label="Interest rate a year"
            part="rate"
            value={calc.rate}
            min={loan.rate_min}
            max={loan.rate_max}
            step={0.05}
            format={(n) => `${n.toFixed(2)}%`}
            onChange={(n) => setCalc(type, { rate: Math.round(n * 100) / 100 })}
          />
        </div>
        <div className="calc-result">
          <div className="emi-big" data-stage-thing="loan:emi" data-stage-label="EMI">
            <span className="eb-label">Monthly EMI</span>
            <span className="eb-num num">{inr(a.emi)}</span>
            <span className="eb-sub">
              for {tenureText(calc.tenure)} at {calc.rate.toFixed(2)}%
            </span>
          </div>
          <dl className="kv kv-tight" data-stage-thing="loan:totals" data-stage-label="Total payable">
            <div>
              <dt>Total interest</dt>
              <dd className="num">{inr(a.total_interest)}</dd>
            </div>
            <div>
              <dt>Total payable</dt>
              <dd className="num">{inr(a.total_payable)}</dd>
            </div>
          </dl>
        </div>
      </div>

      {!compact ? (
        <div className="working" data-stage-thing="loan:working" data-stage-label="The working">
          <h3 className="working-h">The working</h3>
          <ol className="working-lines num">
            <li>
              <span className="wl-k">Formula</span>
              <span className="wl-v formula">
                EMI = P × r × (1 + r)<sup>n</sup> ÷ ((1 + r)<sup>n</sup> − 1)
              </span>
            </li>
            <li>
              <span className="wl-k">P, the amount</span>
              <span className="wl-v">{inr(calc.amount)}</span>
            </li>
            <li>
              <span className="wl-k">r, monthly rate</span>
              <span className="wl-v">
                {calc.rate.toFixed(2)} ÷ 12 ÷ 100 = {a.r.toFixed(6)}
              </span>
            </li>
            <li>
              <span className="wl-k">n, months</span>
              <span className="wl-v">{calc.tenure}</span>
            </li>
            <li>
              <span className="wl-k">
                (1 + r)<sup>n</sup>
              </span>
              <span className="wl-v">
                {(1 + a.r).toFixed(6)}
                <sup>{calc.tenure}</sup> = {a.growth.toFixed(4)}
              </span>
            </li>
            <li className="wl-result">
              <span className="wl-k">EMI</span>
              <span className="wl-v">
                {fmtR(calc.amount)} × {a.r.toFixed(6)} × {a.growth.toFixed(4)} ÷ {(a.growth - 1).toFixed(4)} = <strong>{inr(a.emi)}</strong>
              </span>
            </li>
            <li>
              <span className="wl-k">Total payable</span>
              <span className="wl-v">
                {inr(a.emi)} × {calc.tenure} = {inr(a.total_payable)}
              </span>
            </li>
            <li>
              <span className="wl-k">Total interest</span>
              <span className="wl-v">
                {inr(a.total_payable)} − {inr(calc.amount)} = {inr(a.total_interest)}
              </span>
            </li>
          </ol>
          <div className="first-year" data-stage-thing="loan:first-year" data-stage-label="First year">
            <p className="fy-h">
              In the first {Math.min(12, calc.tenure)} months you pay {inr(a.emi * Math.min(12, calc.tenure))}
            </p>
            <div className="fy-bar" aria-hidden>
              <span className="fy-int" style={{ width: `${(fy.interest / fyTotal) * 100}%` }} />
              <span className="fy-prin" style={{ width: `${(fy.principal / fyTotal) * 100}%` }} />
            </div>
            <dl className="fy-legend">
              <div>
                <dt>
                  <i className="sw sw-int" /> Interest
                </dt>
                <dd className="num">{inr(fy.interest)}</dd>
              </div>
              <div>
                <dt>
                  <i className="sw sw-prin" /> Principal repaid
                </dt>
                <dd className="num">{inr(fy.principal)}</dd>
              </div>
              <div>
                <dt>Still owed after</dt>
                <dd className="num">{inr(fy.balance_after)}</dd>
              </div>
            </dl>
          </div>
        </div>
      ) : null}
    </section>
  );
}

// ─── Eligibility ─────────────────────────────────────────────────────────────

export function EligibilityPanel({ type }: { type: LoanType }) {
  const loan = loanProduct(type)!;
  const input = useAdvisor((s) => s.elig[type]);
  const checked = useAdvisor((s) => s.checked[type]);
  const setElig = useAdvisor((s) => s.setElig);
  const signedIn = useSession((s) => s.signedIn);
  const el = loanEligibility(loan, input);
  const gold = type === "gold";
  const num = (k: keyof typeof input, label: string, unit: "₹" | "g" | "mo") => (
    <div className="field" data-stage-part={k} data-stage-thing={`elig:${k}`} data-stage-label={label}>
      <label className="field-label" htmlFor={`elig-${type}-${k}`}>
        {label}
      </label>
      <div className="input-wrap">
        {unit === "₹" ? <span className="input-prefix">₹</span> : null}
        <input
          id={`elig-${type}-${k}`}
          className={`input num${unit === "₹" ? " has-prefix" : ""}`}
          inputMode="numeric"
          value={input[k] ? input[k].toLocaleString("en-IN") : "0"}
          onChange={(e) => setElig(type, { [k]: Number(e.target.value.replace(/\D/g, "")) || 0 }, false)}
        />
        {unit !== "₹" ? <span className="input-suffix">{unit === "g" ? "grams" : "months"}</span> : null}
      </div>
    </div>
  );
  return (
    <section className="card elig" aria-labelledby={`elig-h-${type}`} data-stage-thing="loan:eligibility-check" data-stage-label="Eligibility check">
      <h2 id={`elig-h-${type}`} className="side-h">
        How much can you borrow?
      </h2>
      <p className="side-small">
        {gold
          ? `Gold loans go by the gold, not your income: ${loan.ltv_pct}% of its value at ₹${(loan.gold_rate_per_gram_22k ?? 0).toLocaleString("en-IN")} a gram (22 carat).`
          : `We lend so that all your EMIs stay within ${Math.round((loan.foir ?? 0.5) * 100)}% of your take-home income, at the typical ${loan.rate_typical}%.`}
      </p>
      {signedIn && !gold ? (
        <button type="button" className="btn btn-sm btn-outline" onClick={() => setElig(type, customerElig(), true)}>
          <Wallet size={15} aria-hidden /> Use my income and EMIs
        </button>
      ) : null}
      <div className="field-grid elig-fields">
        {gold ? (
          num("gold_grams", "Gold you will pledge", "g")
        ) : (
          <>
            {num("monthly_income", "Monthly take-home income", "₹")}
            {num("existing_emis", "EMIs you already pay", "₹")}
            {num("tenure_months", "Tenure", "mo")}
          </>
        )}
      </div>
      {!checked ? (
        <button type="button" className="btn btn-primary" onClick={() => setElig(type, {}, true)} data-stage-thing="elig:check" data-stage-label="Check eligibility">
          Check eligibility
        </button>
      ) : (
        <div className="elig-result" data-stage-thing="loan:eligibility" data-stage-label="Eligibility" aria-live="polite">
          <span className="er-label">You could borrow up to</span>
          <span className="er-num num">{inr(el.max_amount)}</span>
          {el.max_emi != null ? <span className="er-sub">with an EMI of up to {inr(el.max_emi)} a month</span> : null}
          <ol className="er-steps">
            {el.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
          {el.max_amount < loan.amount_min ? <p className="elig-line is-bad">That is below the smallest {loan.short.toLowerCase()} we give, {inr(loan.amount_min)}.</p> : null}
          <Link to={`/loans/apply?type=${type}`} className="btn btn-accent btn-sm">
            Apply for up to {lakh(el.max_amount)}
          </Link>
        </div>
      )}
    </section>
  );
}

// ─── /loans ──────────────────────────────────────────────────────────────────

export function LoansPage() {
  const [type, setType] = useState<LoanType>("home");
  return (
    <main className="page loans" data-stage-thing="screen:loans" data-stage-label="Loans">
      <div className="wrap">
        <Crumbs items={[{ label: "Loans" }]} />
        <header className="page-head">
          <h1 className="page-title">Loans, with the maths shown</h1>
          <p className="page-lede">
            See your EMI and how it is worked out, check how much you can borrow, and leave your details for a call back. {persona.name} can walk you through any of it.
          </p>
        </header>
        <OfferBanner kind="loan" />
        <div className="loan-cards">
          {products.loans.map((l) => (
            <article key={l.id} className="loan-card" data-stage-thing={`loan:${l.id}`} data-stage-label={l.name}>
              <h2 className="lc-name">
                <Link to={`/loans/${l.id}`}>{l.short}</Link>
              </h2>
              <p className="lc-rate">
                <span className="num">{l.rate_min}%</span> <small>a year, from</small>
              </p>
              <dl className="kv kv-tight">
                <div>
                  <dt>Amount</dt>
                  <dd className="num">
                    {lakh(l.amount_min)} to {lakh(l.amount_max)}
                  </dd>
                </div>
                <div>
                  <dt>Tenure</dt>
                  <dd>up to {tenureText(l.tenure_max_months)}</dd>
                </div>
              </dl>
              <ul className="cr-high">
                {l.highlights.map((h) => (
                  <li key={h}>
                    <Check size={13} aria-hidden /> {h}
                  </li>
                ))}
              </ul>
              <div className="lc-links">
                <Link to={`/loans/${l.id}`} className="btn btn-sm btn-outline">
                  Calculate EMI
                </Link>
                <Link to={`/loans/apply?type=${l.id}`} className="text-link">
                  Apply <ArrowRight size={14} aria-hidden />
                </Link>
              </div>
            </article>
          ))}
        </div>
        <div className="loan-tools">
          <div className="seg-tabs" role="tablist" aria-label="Loan type">
            {LOAN_TYPES.map((t) => (
              <button key={t} type="button" role="tab" aria-selected={type === t} className={type === t ? "is-on" : undefined} data-stage-part={`loan_type:${t}`} onClick={() => setType(t)}>
                {loanProduct(t)!.short}
              </button>
            ))}
          </div>
          <div className="tools-grid">
            <EmiCalculator type={type} compact />
            <EligibilityPanel type={type} />
          </div>
          <p className="side-small">
            Want the working line by line? <Link to={`/loans/${type}`}>Open the {loanProduct(type)!.short.toLowerCase()} page</Link>.
          </p>
        </div>
      </div>
    </main>
  );
}

// ─── /loans/:type ────────────────────────────────────────────────────────────

export function LoanPage() {
  const { type = "" } = useParams();
  const loan = loanProduct(type);
  if (!loan) {
    return (
      <main className="page" data-stage-thing="screen:loan" data-stage-label="Loan">
        <div className="wrap section">
          <h1 className="page-title">No such loan</h1>
          <p>
            We offer {products.loans.map((l) => l.short.toLowerCase()).join(", ")}. <Link to="/loans">See them all</Link>.
          </p>
        </div>
      </main>
    );
  }
  const t = loan.id as LoanType;
  return (
    <main className="page loan" data-stage-thing="screen:loan" data-stage-label={loan.name}>
      <div className="wrap">
        <Crumbs items={[{ to: "/loans", label: "Loans" }, { label: loan.short }]} />
        <header className="page-head page-head-row">
          <div>
            <h1 className="page-title">{loan.name}</h1>
            <p className="page-lede">
              {loan.rate_min}% to {loan.rate_max}% a year, typically {loan.rate_typical}%. {lakh(loan.amount_min)} to {lakh(loan.amount_max)}, over{" "}
              {tenureText(loan.tenure_min_months)} to {tenureText(loan.tenure_max_months)}.
            </p>
          </div>
          <div className="head-actions">
            <Link to={`/loans/apply?type=${t}`} className="btn btn-accent btn-lg" data-stage-thing="cta:apply" data-stage-label="Apply">
              Apply for a {loan.short.toLowerCase()}
            </Link>
          </div>
        </header>
        <div className="loan-grid">
          <div className="loan-main">
            <EmiCalculator type={t} />
          </div>
          <aside className="loan-side">
            <EligibilityPanel type={t} />
            <section className="card" data-stage-thing="loan:documents" data-stage-label="Documents">
              <h2 className="side-h">
                <FileText size={16} aria-hidden /> Documents to keep ready
              </h2>
              <ul className="tick-list">
                {loan.documents.map((d) => (
                  <li key={d}>{d}</li>
                ))}
              </ul>
            </section>
            <section className="card" data-stage-thing="loan:terms" data-stage-label="Fees and terms">
              <h2 className="side-h">Fees and terms</h2>
              <dl className="kv">
                <div>
                  <dt>Processing fee</dt>
                  <dd>{loan.processing_fee}</dd>
                </div>
                {loan.ltv ? (
                  <div>
                    <dt>Loan to value</dt>
                    <dd>{loan.ltv}</dd>
                  </div>
                ) : null}
                <div>
                  <dt>Income from</dt>
                  <dd className="num">{inr(loan.min_income_monthly)} a month</dd>
                </div>
                <div>
                  <dt>Age at the end of the loan</dt>
                  <dd>up to {loan.max_age_at_maturity}</dd>
                </div>
                {loan.gold_rate_note ? (
                  <div>
                    <dt>Gold rate</dt>
                    <dd>{loan.gold_rate_note}</dd>
                  </div>
                ) : null}
              </dl>
            </section>
          </aside>
        </div>
      </div>
    </main>
  );
}
