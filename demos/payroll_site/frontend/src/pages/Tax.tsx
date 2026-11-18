/**
 * Tax & compliance: FY 2025-26 rules from product.json `tax`, and the worked
 * example from tax_example.json, read as they are and never recomputed here.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { SITE, TAX, TAX_EXAMPLE } from "../data/product";
import { inr, lakh } from "../lib/format";

type Slab = (number | null)[];

function band(lo: number, hi: number | null): string {
  if (lo === 0 && hi !== null) return `Up to ${inr(hi)}`;
  if (hi === null) return `Above ${inr(lo)}`;
  return `${inr(lo)} to ${inr(hi)}`;
}

function SlabTable({ slabs }: { slabs: Slab[] }) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th scope="col">Taxable income</th>
          <th scope="col" className="num">
            Rate
          </th>
        </tr>
      </thead>
      <tbody>
        {slabs.map(([lo, hi, rate]) => (
          <tr key={String(lo)}>
            <td className="num">{band(lo as number, hi)}</td>
            <td className="num">{rate ? `${rate}%` : "Nil"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const SECTIONS = TAX.sections as Record<string, string>;
const L = TAX.limits;

const DEDUCTIONS: { id: string; name: string; limit: string; regime: string }[] = [
  { id: "standard_deduction", name: "Standard deduction", limit: `${inr(TAX.regimes.new.standard_deduction)} new, ${inr(TAX.regimes.old.standard_deduction)} old`, regime: "Both" },
  { id: "80C", name: "Section 80C", limit: inr(L["80C"]), regime: "Old only" },
  { id: "80CCD1B", name: "Section 80CCD(1B)", limit: inr(L["80CCD1B"]), regime: "Old only" },
  { id: "80D", name: "Section 80D", limit: `${inr(L["80D_self"])} + ${inr(L["80D_parents"])}`, regime: "Old only" },
  { id: "hra", name: "HRA", limit: "Least of three", regime: "Old only" },
  { id: "lta", name: "LTA", limit: "Actual fare", regime: "Old only" },
  { id: "24b", name: "Section 24(b)", limit: inr(L["24b"]), regime: "Old only" },
  { id: "professional_tax", name: "Professional tax", limit: inr(L.professional_tax), regime: "Old only" },
];

export function Tax() {
  const p = SITE.tax_page;
  const nr = TAX.regimes.new;
  const or = TAX.regimes.old;
  return (
    <div className="page tax-page">
      <header className="page-head wrap">
        <p className="tag-illustrative">Illustrative, {TAX.fy_label}</p>
        <h1>{p.title}</h1>
        <p className="page-intro">{p.intro}</p>
        <nav className="toc" aria-label="On this page">
          <a href="#new-regime">New regime</a>
          <a href="#old-regime">Old regime</a>
          <a href="#deductions">Deductions</a>
          <a href="#statutory">PF, ESI and PT</a>
          <a href="#tds-form16">TDS and Form 16</a>
          <a href="#worked-example">Worked example</a>
        </nav>
      </header>

      <section className="section section-tight">
        <div className="wrap regimes">
          <article id="new-regime" className="regime" data-stage-thing="new-regime" data-stage-label="New regime slabs">
            <h2>{nr.label}</h2>
            <SlabTable slabs={nr.slabs} />
            <dl className="facts">
              <div>
                <dt>Standard deduction</dt>
                <dd className="num">{inr(nr.standard_deduction)}</dd>
              </div>
              <div>
                <dt>Rebate under 87A</dt>
                <dd>
                  Tax is nil up to <span className="num">{inr(nr.rebate_87a.income_limit)}</span> of taxable income (rebate up to{" "}
                  <span className="num">{inr(nr.rebate_87a.max)}</span>), with marginal relief just above it.
                </dd>
              </div>
            </dl>
          </article>
          <article id="old-regime" className="regime" data-stage-thing="old-regime" data-stage-label="Old regime slabs">
            <h2>{or.label}</h2>
            <SlabTable slabs={or.slabs} />
            <dl className="facts">
              <div>
                <dt>Standard deduction</dt>
                <dd className="num">{inr(or.standard_deduction)}</dd>
              </div>
              <div>
                <dt>Rebate under 87A</dt>
                <dd>
                  Tax is nil up to <span className="num">{inr(or.rebate_87a.income_limit)}</span> of taxable income (rebate up to{" "}
                  <span className="num">{inr(or.rebate_87a.max)}</span>).
                </dd>
              </div>
            </dl>
          </article>
          <p className="regime-note">
            Health and education cess of {TAX.cess_pct}% is added to the tax in both regimes. {TAX.surcharge_note} {TAX.rounding}
          </p>
        </div>
      </section>

      <section id="deductions" className="section section-tight" data-stage-thing="deductions" data-stage-label="Deductions">
        <div className="wrap">
          <h2 className="h-section">Exemptions and deductions</h2>
          <p className="section-lede">The new regime allows only the standard deduction. Everything else on this list needs the old regime.</p>
          <div className="table-scroll">
            <table className="data-table deductions">
              <thead>
                <tr>
                  <th scope="col">Section</th>
                  <th scope="col">What it covers</th>
                  <th scope="col" className="num">Limit</th>
                  <th scope="col">Regime</th>
                </tr>
              </thead>
              <tbody>
                {DEDUCTIONS.map((d) => (
                  <tr key={d.id}>
                    <th scope="row">{d.name}</th>
                    <td>
                      {SECTIONS[d.id]}
                      {d.id === "hra" ? <span className="cell-more">{TAX.hra.rule}</span> : null}
                      {d.id === "lta" ? <span className="cell-more">{TAX.lta.rule}</span> : null}
                    </td>
                    <td className={/\d/.test(d.limit) ? "num" : "text-cell"}>{d.limit}</td>
                    <td>
                      <span className={`regime-pill${d.regime === "Both" ? " is-both" : ""}`}>{d.regime}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <Statutory />

      <section id="tds-form16" className="section section-tight" data-stage-thing="tds-form16" data-stage-label="TDS and Form 16">
        <div className="wrap three-up">
          <article>
            <h3>TDS spread over the year</h3>
            <p>{SECTIONS.tds}</p>
          </article>
          <article>
            <h3>Choosing a regime</h3>
            <p>{TAX.regime_choice}</p>
          </article>
          <article>
            <h3>Form 16</h3>
            <p>{SECTIONS.form16}</p>
          </article>
        </div>
      </section>

      <WorkedExample />

      <section className="section section-tight">
        <div className="wrap inline-cta">
          <p>See this working for your own employees.</p>
          <Link to="/book-demo" className="btn btn-primary">
            Book a demo
          </Link>
        </div>
      </section>
    </div>
  );
}

function Statutory() {
  const pt = TAX.professional_tax.states as Record<string, { slabs: Slab[]; slabs_women?: Slab[]; february?: number; none?: boolean }>;
  return (
    <section id="statutory" className="section section-tight" data-stage-thing="statutory" data-stage-label="PF, ESI and PT">
      <div className="wrap">
        <h2 className="h-section">PF, ESI and professional tax</h2>
        <div className="statutory-grid">
          <article className="stat-card">
            <h3>Provident fund</h3>
            <p className="stat-big num">
              {TAX.pf.employee_pct}% + {TAX.pf.employer_pct}%
            </p>
            <p>{TAX.pf.note}</p>
            <p className="stat-meta">
              Wage ceiling <span className="num">{inr(TAX.pf.wage_ceiling)}</span> a month
            </p>
          </article>
          <article className="stat-card">
            <h3>ESI</h3>
            <p className="stat-big num">
              {TAX.esi.employee_pct}% + {TAX.esi.employer_pct}%
            </p>
            <p>{TAX.esi.note}</p>
            <p className="stat-meta">
              Gross up to <span className="num">{inr(TAX.esi.gross_ceiling)}</span> a month
            </p>
          </article>
          <article className="stat-card stat-pt">
            <h3>Professional tax by state</h3>
            <p className="stat-meta">{TAX.professional_tax.note}</p>
            <div className="table-scroll">
            <table className="data-table compact">
              <thead>
                <tr>
                  <th scope="col">State</th>
                  <th scope="col">Monthly gross</th>
                  <th scope="col" className="num">
                    PT a month
                  </th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(pt).flatMap(([state, s]) =>
                  s.none
                    ? [
                        <tr key={state}>
                          <th scope="row">{state}</th>
                          <td colSpan={2}>No professional tax</td>
                        </tr>,
                      ]
                    : s.slabs.map(([lo, hi, amt], i) => (
                        <tr key={`${state}-${i}`}>
                          <th scope="row">{i === 0 ? state : <span className="sr-only">{state}</span>}</th>
                          <td className="num">{band(lo as number, hi)}</td>
                          <td className="num">
                            {amt ? inr(amt) : "Nil"}
                            {amt && s.february && i === s.slabs.length - 1 ? <span className="cell-more">{inr(s.february)} in February</span> : null}
                          </td>
                        </tr>
                      )),
                )}
              </tbody>
            </table>
            </div>
            {pt.Maharashtra?.slabs_women ? (
              <p className="stat-meta">
                In Maharashtra, women earning up to {inr(pt.Maharashtra.slabs_women[0][1] as number)} a month pay no professional tax.
              </p>
            ) : null}
          </article>
        </div>
      </div>
    </section>
  );
}

type Stage = typeof TAX_EXAMPLE.declared;
type Regime = Stage["new"];

const STEPS: { label: string; get: (r: Regime) => number; minus?: boolean; sum?: boolean }[] = [
  { label: "Gross salary", get: (r) => r.gross_salary },
  { label: "HRA exemption", get: (r) => r.exempt_hra, minus: true },
  { label: "Standard deduction", get: (r) => r.standard_deduction, minus: true },
  { label: "Professional tax", get: (r) => r.professional_tax, minus: true },
  { label: "Income from salary", get: (r) => r.income_from_salary, sum: true },
  { label: "80C", get: (r) => r.ded_80c, minus: true },
  { label: "80CCD(1B), NPS", get: (r) => r.ded_80ccd1b, minus: true },
  { label: "80D, health insurance", get: (r) => r.ded_80d, minus: true },
  { label: "Taxable income", get: (r) => r.taxable_income, sum: true },
  { label: "Tax on income", get: (r) => r.tax_on_income },
  { label: "Rebate under 87A", get: (r) => r.rebate_87a, minus: true },
  { label: `Cess ${TAX.cess_pct}%`, get: (r) => r.cess },
];

function WorkedExample() {
  const p = SITE.tax_page;
  const [stage, setStage] = useState<"declared" | "after_proofs">("after_proofs");
  const ex = TAX_EXAMPLE;
  const s: Stage = ex[stage];
  const best = s.new.total_tax <= s.old.total_tax ? "new" : "old";
  const gap = Math.abs(s.new.total_tax - s.old.total_tax);
  const decl = s.decl;
  return (
    <section id="worked-example" className="section worked" data-stage-thing="worked-example" data-stage-label="Worked example">
      <div className="wrap">
        <p className="tag-illustrative">Illustrative, FY 2025-26</p>
        <h2 className="h-section">{p.example_title}</h2>
        <p className="section-lede">{p.example_intro}</p>

        <div className="example-profile">
          <dl>
            <div>
              <dt>CTC</dt>
              <dd className="num">{lakh(ex.profile.annual_ctc)}</dd>
            </div>
            <div>
              <dt>Basic</dt>
              <dd className="num">{inr(ex.annual_salary.basic)}</dd>
            </div>
            <div>
              <dt>HRA received</dt>
              <dd className="num">{inr(ex.annual_salary.hra)}</dd>
            </div>
            <div>
              <dt>Rent</dt>
              <dd className="num">{inr(ex.profile.rent_monthly)} a month</dd>
            </div>
            <div>
              <dt>City</dt>
              <dd>{ex.profile.city} (metro)</dd>
            </div>
          </dl>
        </div>

        <div className="seg" role="tablist" aria-label="Which figures">
          <button type="button" role="tab" aria-selected={stage === "declared"} className={stage === "declared" ? "is-on" : ""} onClick={() => setStage("declared")}>
            As declared in April
          </button>
          <button type="button" role="tab" aria-selected={stage === "after_proofs"} className={stage === "after_proofs" ? "is-on" : ""} onClick={() => setStage("after_proofs")}>
            After proofs in January
          </button>
        </div>

        <p className="example-decl">
          Declared: 80C <span className="num">{inr(decl.sec80c_other)}</span> beyond EPF, 80D <span className="num">{inr(decl.sec80d_self)}</span> self and{" "}
          <span className="num">{inr(decl.sec80d_parents)}</span> for senior-citizen parents, NPS <span className="num">{inr(decl.sec80ccd1b)}</span>.
          {stage === "after_proofs" ? ` Missing proofs: ${ex.after_proofs.missing.join(", ")}.` : ""}
        </p>

        <div className="example-grid">
          <div className="table-scroll">
            <table className="data-table working">
              <thead>
                <tr>
                  <th scope="col">Step</th>
                  <th scope="col" className={`num${best === "old" ? " is-best" : ""}`}>
                    Old regime
                  </th>
                  <th scope="col" className={`num${best === "new" ? " is-best" : ""}`}>
                    New regime
                  </th>
                </tr>
              </thead>
              <tbody>
                {STEPS.map((st) => (
                  <tr key={st.label} className={st.sum ? "is-sum" : undefined}>
                    <th scope="row">{st.label}</th>
                    {(["old", "new"] as const).map((r) => {
                      const v = st.get(s[r]);
                      return (
                        <td key={r} className="num">
                          {v ? `${st.minus ? "− " : ""}${inr(v)}` : "—"}
                        </td>
                      );
                    })}
                  </tr>
                ))}
                <tr className="is-total">
                  <th scope="row">Tax for the year</th>
                  <td className={`num${best === "old" ? " is-best" : ""}`}>{inr(s.old.total_tax)}</td>
                  <td className={`num${best === "new" ? " is-best" : ""}`}>{inr(s.new.total_tax)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div className="verdict">
            <p className="verdict-big">
              The {best} regime is <span className="num">{inr(gap)}</span> lower.
            </p>
            <p>
              Monthly TDS of about <span className="num">{inr(Math.round(s[best].total_tax / 12))}</span> under the {best} regime.
            </p>
          </div>
        </div>

        <div className="slab-pair">
          {(["old", "new"] as const).map((r) => (
            <div key={r}>
              <h3 className="h-small">{r === "old" ? "Old regime" : "New regime"}, slab by slab</h3>
              <div className="table-scroll">
                <table className="data-table compact">
                  <thead>
                    <tr>
                      <th scope="col">Slab</th>
                      <th scope="col" className="num">
                        Rate
                      </th>
                      <th scope="col" className="num">
                        Income in slab
                      </th>
                      <th scope="col" className="num">
                        Tax
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {s[r].slabs.map((sl) => (
                      <tr key={sl.lo} className={sl.taxable ? undefined : "is-empty"}>
                        <td className="num">{band(sl.lo, sl.hi)}</td>
                        <td className="num">{sl.rate}%</td>
                        <td className="num">{inr(sl.taxable)}</td>
                        <td className="num">{inr(sl.tax)}</td>
                      </tr>
                    ))}
                    <tr className="is-sum">
                      <th scope="row" colSpan={3}>
                        Tax on {inr(s[r].taxable_income)}
                      </th>
                      <td className="num">{inr(s[r].tax_on_income)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
        <p className="fine">{p.example_note} {TAX.disclaimer}</p>
      </div>
    </section>
  );
}
