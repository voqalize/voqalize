import { BadgeCheck, CalendarClock, FileText, MapPin, UserRound } from "lucide-react";
import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Crumbs, FormField, lakh } from "../../components/ui";
import { inr, loanProduct } from "../../data/bank";
import { fieldsOf, profileFill, useForms } from "../../state/forms";
import { useAdvisor } from "../../state/advisor";
import { useSession } from "../../state/session";
import { SubmitBar } from "./CardsApply";

const FORM = "loan_apply" as const;

export function LoanApply() {
  const [params] = useSearchParams();
  const values = useForms((s) => s.values[FORM]);
  const submitted = useForms((s) => s.submitted[FORM]);
  const signedIn = useSession((s) => s.signedIn);
  const qType = params.get("type");

  useEffect(() => {
    if (qType && loanProduct(qType) && useForms.getState().values[FORM].loan_type !== qType) useForms.getState().setField(FORM, "loan_type", qType);
  }, [qType]);

  const loan = loanProduct(values.loan_type ?? "");
  const calc = useAdvisor((s) => (loan ? s.calc[loan.id] : null));

  return (
    <main className="page apply" data-stage-thing="screen:loan_apply" data-stage-label="Loan application">
      <div className="wrap">
        <Crumbs items={[{ to: "/loans", label: "Loans" }, { label: "Apply" }]} />
        <header className="page-head">
          <h1 className="page-title">{submitted ? "We'll call you back" : `Apply for a ${loan ? loan.short.toLowerCase() : "loan"}`}</h1>
          <p className="page-lede">
            {submitted
              ? "Your application is with a loan officer, who will call at the time you chose."
              : "Tell us a little about you and the loan. A loan officer calls back at the time you pick, with the offer and the papers to sign."}
          </p>
        </header>
        {submitted?.lead ? (
          <LeadCard />
        ) : (
          <div className="apply-grid">
            <section className="card apply-form" aria-label="Application">
              {signedIn ? (
                <button
                  type="button"
                  className="btn btn-sm btn-outline fill-mine"
                  onClick={() => {
                    for (const [k, v] of Object.entries(profileFill(FORM))) useForms.getState().setField(FORM, k, v);
                  }}
                >
                  <UserRound size={15} aria-hidden /> Fill from my profile
                </button>
              ) : null}
              <div className="field-grid">
                <FormField form={FORM} name="loan_type" wide />
                {fieldsOf(FORM, values)
                  .filter((f) => f !== "loan_type")
                  .map((f) => (
                    <FormField key={f} form={FORM} name={f} wide={f === "employment" || f === "preferred_time"} />
                  ))}
              </div>
              <SubmitBar form={FORM} label="Submit application" />
            </section>
            <aside className="apply-side">
              {loan && calc ? (
                <div className="card side-card">
                  <h2 className="side-h">{loan.name}</h2>
                  <dl className="kv">
                    <div>
                      <dt>Rate</dt>
                      <dd className="num">
                        {loan.rate_min}% to {loan.rate_max}%
                      </dd>
                    </div>
                    <div>
                      <dt>Amount</dt>
                      <dd className="num">
                        {lakh(loan.amount_min)} to {lakh(loan.amount_max)}
                      </dd>
                    </div>
                    <div>
                      <dt>Tenure</dt>
                      <dd>
                        {loan.tenure_min_months} to {loan.tenure_max_months} months
                      </dd>
                    </div>
                  </dl>
                  <button
                    type="button"
                    className="btn btn-sm btn-outline"
                    onClick={() => {
                      useForms.getState().setField(FORM, "amount", String(calc.amount));
                      useForms.getState().setField(FORM, "tenure_months", String(calc.tenure));
                    }}
                  >
                    Use my calculator figures ({lakh(calc.amount)}, {calc.tenure} months)
                  </button>
                </div>
              ) : null}
            </aside>
          </div>
        )}
      </div>
    </main>
  );
}

function LeadCard() {
  const sub = useForms((s) => s.submitted[FORM])!;
  const lead = sub.lead!;
  const v = sub.values;
  return (
    <section className="lead card" data-stage-thing="lead-card" data-stage-label="Lead card" aria-live="polite">
      <div className="lead-top">
        <div>
          <p className="lead-kicker">Lead</p>
          <p className="lead-id num">{lead.id}</p>
        </div>
        <span className="chip chip-ok lead-chip">
          <BadgeCheck size={14} aria-hidden /> Qualified
        </span>
      </div>
      <div className="lead-grid">
        <dl className="lead-facts">
          <div>
            <dt>Product</dt>
            <dd>{lead.product}</dd>
          </div>
          <div>
            <dt>Amount</dt>
            <dd className="num">{inr(lead.amount)}</dd>
          </div>
          <div>
            <dt>Tenure</dt>
            <dd>{lead.tenure_months} months</dd>
          </div>
          <div data-stage-thing="lead:emi" data-stage-label="EMI">
            <dt>EMI at {lead.rate}%</dt>
            <dd className="num strong">{inr(lead.emi)} a month</dd>
          </div>
          <div>
            <dt>Applicant</dt>
            <dd>
              {v.full_name}, {v.employment === "salaried" ? `salaried at ${v.employer}` : v.employer}
            </dd>
          </div>
        </dl>
        <div className={`lead-verdict ${lead.within ? "is-ok" : "is-warn"}`} data-stage-thing="lead:verdict" data-stage-label="Eligibility verdict">
          <p className="lv-h">{lead.within ? "Within your eligibility" : "Above your eligibility"}</p>
          <p className="lv-line">
            {lead.within
              ? `${inr(lead.amount)} is within the ${inr(lead.eligibility.max_amount)} you can borrow.`
              : `You asked for ${inr(lead.amount)}; on these figures you can borrow up to ${inr(lead.eligibility.max_amount)}. The officer will talk through a lower amount or a longer tenure.`}
          </p>
          <ol className="er-steps">
            {lead.eligibility.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
        </div>
      </div>
      <div className="lead-cols">
        <div data-stage-thing="lead:documents" data-stage-label="Documents">
          <h3 className="lead-h">
            <FileText size={15} aria-hidden /> Documents to keep ready
          </h3>
          <ul className="tick-list">
            {lead.documents.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="lead-h">
            <CalendarClock size={15} aria-hidden /> Call back
          </h3>
          <p className="lead-p" data-stage-thing="lead:callback" data-stage-label="Call back">
            {lead.callback}, on the next working day, to +91 {v.mobile.slice(0, 2)}XXX XX{v.mobile.slice(-3)}
          </p>
          <h3 className="lead-h">
            <MapPin size={15} aria-hidden /> Your loan officer
          </h3>
          <p className="lead-p">Assigned to the {lead.team}</p>
        </div>
      </div>
      <div className="done-actions">
        <Link to="/loans" className="btn btn-quiet">
          Back to loans
        </Link>
        <button type="button" className="btn btn-outline" onClick={() => useForms.getState().reset(FORM)}>
          Start another application
        </button>
      </div>
    </section>
  );
}
