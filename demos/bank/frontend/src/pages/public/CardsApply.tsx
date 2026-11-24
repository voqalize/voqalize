import { CircleCheck, UserRound } from "lucide-react";
import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CardFace, Crumbs, FormField } from "../../components/ui";
import { creditCardProduct, inr } from "../../data/bank";
import { choiceLabel, fieldDef, fieldsOf, profileFill, useForms } from "../../state/forms";
import { useSession } from "../../state/session";

const FORM = "card_apply" as const;

export function CardsApply() {
  const [params] = useSearchParams();
  const values = useForms((s) => s.values[FORM]);
  const submitted = useForms((s) => s.submitted[FORM]);
  const signedIn = useSession((s) => s.signedIn);
  const fromQuery = params.get("card");

  useEffect(() => {
    if (fromQuery && creditCardProduct(fromQuery) && useForms.getState().values[FORM].card_id !== fromQuery) {
      useForms.getState().setField(FORM, "card_id", fromQuery);
    }
  }, [fromQuery]);

  const card = creditCardProduct(values.card_id ?? "");
  const income = Number(values.monthly_income) || 0;

  return (
    <main className="page apply" data-stage-thing="screen:cards_apply" data-stage-label="Card application">
      <div className="wrap">
        <Crumbs items={[{ to: "/cards", label: "Credit cards" }, { label: "Apply" }]} />
        <header className="page-head">
          <h1 className="page-title">Apply for a credit card</h1>
          <p className="page-lede">One page, about three minutes. We check your PAN with the credit bureau only after you submit.</p>
        </header>
        {submitted ? (
          <section className="done card" data-stage-thing="confirmation" data-stage-label="Application submitted" aria-live="polite">
            <CircleCheck size={40} className="done-icon" aria-hidden />
            <h2 className="done-title">Application received</h2>
            <p className="done-ref">
              Reference <strong className="num">{submitted.reference}</strong>
            </p>
            {card ? (
              <div className="done-card">
                <CardFace card={creditCardProduct(submitted.values.card_id)!} size="sm" />
                <p>
                  {choiceLabel("card_id", submitted.values.card_id)} for {submitted.values.full_name}, {submitted.values.city}.
                </p>
              </div>
            ) : null}
            <h3 className="done-h">What happens next</h3>
            <ol className="next-steps">
              <li>We check your PAN and credit history. You hear from us by SMS within two working days.</li>
              <li>If approved, a short video KYC confirms it's you.</li>
              <li>Your card is delivered in 7 working days; the virtual card works the same day.</li>
            </ol>
            <div className="done-actions">
              <Link to="/cards" className="btn btn-quiet">
                Back to cards
              </Link>
              <button type="button" className="btn btn-outline" onClick={() => useForms.getState().reset(FORM)}>
                Start another application
              </button>
            </div>
          </section>
        ) : (
          <div className="apply-grid">
            <section className="card apply-form" aria-label="Application">
              {signedIn ? (
                <button
                  type="button"
                  className="btn btn-sm btn-outline fill-mine"
                  onClick={() => {
                    const fill = profileFill(FORM);
                    for (const [k, v] of Object.entries(fill)) if (fieldsOf(FORM, values).includes(k)) useForms.getState().setField(FORM, k, v);
                  }}
                >
                  <UserRound size={15} aria-hidden /> Fill from my profile
                </button>
              ) : null}
              <div className="field-grid">
                <FormField form={FORM} name="card_id" wide />
                {fieldsOf(FORM, values)
                  .filter((f) => f !== "card_id")
                  .map((f) => (
                    <FormField key={f} form={FORM} name={f} wide={f === "employment"} />
                  ))}
              </div>
              <SubmitBar />
            </section>
            <aside className="apply-side">
              {card ? (
                <div className="card side-card" data-stage-thing="apply:card" data-stage-label={card.name}>
                  <CardFace card={card} />
                  <h2 className="side-h">{card.name}</h2>
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
                      <dt>Income needed</dt>
                      <dd className="num">{inr(card.min_income_monthly)} a month</dd>
                    </div>
                  </dl>
                  {income ? (
                    <p className={`elig-line ${income >= card.min_income_monthly ? "is-ok" : "is-bad"}`} data-stage-thing="apply:income-check" data-stage-label="Income check">
                      {income >= card.min_income_monthly
                        ? `Your income of ${inr(income)} meets the ${inr(card.min_income_monthly)} needed.`
                        : `This card needs ${inr(card.min_income_monthly)} a month; you entered ${inr(income)}.`}
                    </p>
                  ) : null}
                </div>
              ) : (
                <div className="card side-card">
                  <p className="side-small">
                    Pick a card on the left, or <Link to="/cards">see which one suits your spending</Link>.
                  </p>
                </div>
              )}
            </aside>
          </div>
        )}
      </div>
    </main>
  );
}

/** The Submit button and what still blocks it, shared by both one-page forms. */
export function SubmitBar({ form = FORM, label = "Submit application" }: { form?: "card_apply" | "loan_apply"; label?: string }) {
  useForms((s) => s.values[form]);
  const missing = useForms.getState().missing(form);
  return (
    <div className="submit-bar">
      <p className="submit-note" aria-live="polite">
        {missing.length ? `Still needed: ${missing.map((f) => (fieldDef(form, f)?.label ?? f).replace(/ \(.*\)$/, "")).join(", ")}.` : "Everything's in. Check once, then submit."}
      </p>
      <button
        type="button"
        className="btn btn-accent btn-lg"
        data-stage-thing={`submit:${form}`}
        data-stage-label={label}
        data-dock-avoid
        onClick={() => {
          useForms.getState().submit(form);
          window.scrollTo({ top: 0, behavior: "smooth" });
        }}
      >
        {label}
      </button>
    </div>
  );
}
