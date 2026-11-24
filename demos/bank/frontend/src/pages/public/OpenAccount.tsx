import { Check, CircleCheck, Info, Video } from "lucide-react";
import { Link } from "react-router-dom";
import { Crumbs, FormField } from "../../components/ui";
import { inr, products } from "../../data/bank";
import { persona } from "../../persona";
import { OA_STEPS, choiceLabel, display, fieldDef, useForms } from "../../state/forms";

const FORM = "open_account" as const;
const explain = products.account_opening.explain;

export function OpenAccount() {
  const step = useForms((s) => s.step[FORM]);
  const reached = useForms((s) => s.reached[FORM]);
  const values = useForms((s) => s.values[FORM]);
  const submitted = useForms((s) => s.submitted[FORM]);
  const missing = useForms((s) => s.missing);

  return (
    <main className="page oa" data-stage-thing="screen:open_account" data-stage-label="Open an account">
      <div className="wrap">
        <Crumbs items={[{ label: "Open a savings account" }]} />
        <header className="page-head">
          <h1 className="page-title">Open a savings account</h1>
          <p className="page-lede">
            Six short steps, about ten minutes. Finish with a video KYC call and your account number arrives the same day. Prefer to talk it through? {persona.name}, at the bottom of the page, can fill it in with you.
          </p>
        </header>

        {submitted ? (
          <OaDone />
        ) : (
          <div className="oa-grid">
            <ol className="stepper" aria-label="Application steps">
              {OA_STEPS.map((s) => {
                const done = s.n < step || (s.n < reached && missing(FORM, s.n).length === 0 && s.n !== step);
                const can = s.n <= reached;
                return (
                  <li key={s.n} className={`stepper-item${s.n === step ? " is-current" : ""}${done ? " is-done" : ""}`} data-stage-thing={`step-${s.n}`} data-stage-label={s.title}>
                    <button type="button" disabled={!can} aria-current={s.n === step ? "step" : undefined} onClick={() => useForms.getState().setStep(FORM, s.n)}>
                      <span className="stepper-n" aria-hidden>
                        {done ? <Check size={14} /> : s.n}
                      </span>
                      <span className="stepper-t">{s.title}</span>
                    </button>
                  </li>
                );
              })}
            </ol>

            <section className="oa-step card" aria-labelledby="oa-step-h" data-stage-thing={`step-card-${step}`} data-stage-label={OA_STEPS[step - 1].title}>
              <p className="oa-count">
                Step {step} of {OA_STEPS.length}
              </p>
              <h2 id="oa-step-h" className="oa-title">
                {OA_STEPS[step - 1].title}
              </h2>
              <p className="why">
                <Info size={15} aria-hidden /> <span>{explain[OA_STEPS[step - 1].id]}</span>
              </p>

              {step === 5 ? <VariantPicker /> : null}
              {step === 6 ? (
                <Review />
              ) : (
                <div className="field-grid">
                  {OA_STEPS[step - 1].fields
                    .filter((f) => f !== "variant")
                    .map((f) => (
                      <FormField key={f} form={FORM} name={f} wide={f === "address_line" || f === "email"} />
                    ))}
                </div>
              )}

              <div className="step-actions">
                {step > 1 ? (
                  <button type="button" className="btn btn-quiet" onClick={() => useForms.getState().setStep(FORM, step - 1)}>
                    Back
                  </button>
                ) : (
                  <span />
                )}
                {step < 6 ? (
                  <button
                    type="button"
                    className="btn btn-primary"
                    data-stage-thing="oa:continue"
                    data-stage-label="Continue"
                    data-dock-avoid
                    onClick={() => {
                      const s = useForms.getState();
                      if (s.showErrors(FORM, OA_STEPS[step - 1].fields)) s.setStep(FORM, step + 1);
                    }}
                  >
                    Continue
                  </button>
                ) : (
                  <button
                    type="button"
                    className="btn btn-accent btn-lg"
                    data-stage-thing="submit:open_account"
                    data-stage-label="Submit application"
                    data-dock-avoid
                    onClick={() => {
                      const r = useForms.getState().submit(FORM);
                      if ("missing" in r) {
                        const first = OA_STEPS.find((s) => s.fields.some((f) => r.missing.includes(f)));
                        if (first) useForms.getState().setStep(FORM, first.n);
                      }
                    }}
                  >
                    Submit application
                  </button>
                )}
              </div>
            </section>

            <aside className="oa-side">
              <h2 className="side-h">Keep these handy</h2>
              <ul className="tick-list">
                <li>PAN card</li>
                <li>Aadhaar linked to your mobile number</li>
                <li>A quiet, well-lit place for the video KYC</li>
              </ul>
              <p className="side-small">
                Your PAN and Aadhaar are shown masked on every screen. In this demo they are sample values and go nowhere.
              </p>
              {values.variant ? (
                <div className="side-pick">
                  <span>You chose</span>
                  <strong>{choiceLabel("variant", values.variant)}</strong>
                </div>
              ) : null}
            </aside>
          </div>
        )}
      </div>
    </main>
  );
}

function VariantPicker() {
  const value = useForms((s) => s.values[FORM].variant ?? "");
  const error = useForms((s) => s.errors[FORM].variant);
  const setField = useForms((s) => s.setField);
  return (
    <div className="variant-pick" data-stage-part="variant" data-stage-thing={`field:${FORM}:variant`} data-stage-label="Savings account" role="radiogroup" aria-label="Savings account">
      {products.savings_variants.map((v) => {
        const top = Math.max(...v.rates.map((r) => r.rate));
        return (
          <button
            key={v.id}
            type="button"
            role="radio"
            aria-checked={value === v.id}
            className={`vp${value === v.id ? " is-on" : ""}`}
            data-stage-part={`variant:${v.id}`}
            onClick={() => setField(FORM, "variant", v.id)}
          >
            <span className="vp-head">
              <span className="vp-name">{v.name.replace("Anvaya ", "")}</span>
              <span className="vp-radio" aria-hidden>
                {value === v.id ? <Check size={13} /> : null}
              </span>
            </span>
            <span className="vp-tag">{v.tagline}</span>
            <span className="vp-facts">
              <span>
                <b className="num">{v.min_balance ? inr(v.min_balance) : "₹0"}</b> min. balance
              </span>
              <span>
                <b className="num">up to {top}%</b> interest
              </span>
            </span>
            <ul className="vp-features">
              {v.features.slice(0, 4).map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
            <span className="vp-card">
              {v.debit_card}
              {v.debit_card_fee ? `, ${inr(v.debit_card_fee)} a year` : ", free"}
            </span>
          </button>
        );
      })}
      {error ? <p className="field-error">{error}</p> : null}
    </div>
  );
}

function Review() {
  const values = useForms((s) => s.values[FORM]);
  useForms((s) => s.values[FORM]);
  const missing = useForms.getState().missing(FORM);
  return (
    <div className="review" data-stage-thing="review" data-stage-label="Review">
      {missing.length ? (
        <p className="review-warn" role="status">
          Still needed: {missing.map((f) => fieldDef(FORM, f)?.label ?? f).join(", ")}.
        </p>
      ) : null}
      {OA_STEPS.slice(0, 5).map((s) => (
        <section key={s.n} className="review-block">
          <div className="review-head">
            <h3>{s.title}</h3>
            <button type="button" className="link-btn" onClick={() => useForms.getState().setStep(FORM, s.n)}>
              Edit
            </button>
          </div>
          <dl className="review-list">
            {s.fields.map((f) => (
              <div key={f} className={missing.includes(f) ? "is-missing" : undefined}>
                <dt>{fieldDef(FORM, f)?.label}</dt>
                <dd>{display(FORM, f, values[f] ?? "")}</dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
      <p className="review-consent">By submitting you agree to a video KYC call and to {persona.name} or our team contacting you about this application.</p>
    </div>
  );
}

function OaDone() {
  const sub = useForms((s) => s.submitted[FORM])!;
  const v = sub.values;
  return (
    <section className="done card" data-stage-thing="confirmation" data-stage-label="Application submitted" aria-live="polite">
      <CircleCheck size={40} className="done-icon" aria-hidden />
      <h2 className="done-title">Application received</h2>
      <p className="done-ref">
        Reference <strong className="num">{sub.reference}</strong>
      </p>
      <p className="done-line">
        <Video size={17} aria-hidden /> A video KYC link has been sent to your mobile, +91 {v.mobile?.slice(0, 2)}XXX XX{v.mobile?.slice(-3)}.
      </p>
      <dl className="done-facts">
        <div>
          <dt>Account</dt>
          <dd>{choiceLabel("variant", v.variant)}</dd>
        </div>
        <div>
          <dt>Name</dt>
          <dd>{v.full_name}</dd>
        </div>
        <div>
          <dt>Debit card</dt>
          <dd>{v.debit_card === "yes" ? "Yes" : "No"}</dd>
        </div>
        <div>
          <dt>Cheque book</dt>
          <dd>{v.cheque_book === "yes" ? "Yes" : "No"}</dd>
        </div>
      </dl>
      <h3 className="done-h">What happens next</h3>
      <ol className="next-steps">
        <li>Join the video KYC call from the link, with your PAN card in hand. It takes about five minutes.</li>
        <li>Your account number and customer ID arrive by SMS and email once the call is approved.</li>
        <li>{v.debit_card === "yes" ? "Your debit card and welcome kit reach your address in 5 to 7 working days." : "Your welcome kit reaches your address in 5 to 7 working days."}</li>
      </ol>
      <div className="done-actions">
        <Link to="/" className="btn btn-quiet">
          Back to home
        </Link>
        <button type="button" className="btn btn-outline" onClick={() => useForms.getState().reset(FORM)}>
          Start another application
        </button>
      </div>
    </section>
  );
}
