import { Check, CircleCheck, FileUp, Loader2, Lock } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { PageHead } from "../components/bits";
import { ADMISSIONS } from "../data/admissions";
import { type FormField, STEPS, invalid, missingIn, optionsFor, shown } from "../data/application";
import { SCHOOLS, campusNames, nextRound, programById, programsOf, rupees, schoolById } from "../data/catalogue";
import { useApplication } from "../state/application";

export function Apply() {
  const [params] = useSearchParams();
  const app = useApplication();
  const preset = useRef(false);

  // ?program=<id> preselects the programme, once.
  useEffect(() => {
    if (preset.current) return;
    preset.current = true;
    const id = params.get("program");
    const s = useApplication.getState();
    if (id && programById(id) && !s.submitted && s.values.program !== id) s.set("program", id);
  }, [params]);

  return (
    <div className="apply-page">
      <PageHead
        title="Apply for 2027"
        lede="Five steps. You can come back to any step before you pay; nothing is sent until you press Pay and submit."
        crumbs={[["/admissions", "Admissions"], ["", "Apply"]]}
      />
      <div className="wrap apply-layout">
        <div className="apply-main" data-stage-thing="application" data-stage-label="Application">
          {app.submitted ? <Confirmation /> : <Form />}
        </div>
        <Summary />
      </div>
    </div>
  );
}

function Stepper() {
  const step = useApplication((s) => s.step);
  const reached = useApplication((s) => s.reached);
  const setStep = useApplication((s) => s.setStep);
  const values = useApplication((s) => s.values);
  return (
    <ol className="stepper" aria-label="Application steps">
      {STEPS.map((s) => {
        const state = s.step === step ? "is-current" : s.step <= reached && missingIn(s.step, values).length === 0 ? "is-done" : "";
        return (
          <li key={s.step} className={state}>
            <button type="button" data-stage-thing={`step-${s.step}`} data-stage-label={s.title} aria-current={s.step === step ? "step" : undefined} onClick={() => setStep(s.step)}>
              <span className="stepper-n">{state === "is-done" ? <Check size={14} /> : s.step}</span>
              <span className="stepper-title">{s.title}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function Form() {
  const app = useApplication();
  const current = STEPS.find((s) => s.step === app.step)!;
  const program = programById(app.values.program);
  const flaggedLabels = app.flagged.map((f) => current.fields.find((x) => x.name === f)?.label ?? f);
  return (
    <>
      <Stepper />
      <form
        className="step-panel"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          app.next();
        }}
      >
        <header className="step-head">
          <p className="step-of">
            Step {current.step} of {STEPS.length}
          </p>
          <h2>{current.title}</h2>
        </header>

        {current.step === 5 ? <Review /> : null}

        <div className={`fields fields-${current.id}`}>
          {current.fields.filter((f) => shown(f, app.values)).map((f) => (
            <Field key={f.name} f={f} />
          ))}
        </div>

        {flaggedLabels.length ? (
          <p className="form-error" role="alert">
            Fill these to continue: {flaggedLabels.join(", ")}.
          </p>
        ) : null}

        <div className="step-actions">
          {current.step > 1 ? (
            <button type="button" className="btn btn-ghost" data-dock-avoid onClick={app.back}>
              Back
            </button>
          ) : (
            <span />
          )}
          {current.step < STEPS.length ? (
            <button type="submit" className="btn btn-primary" data-dock-avoid data-stage-thing="continue" data-stage-label="Continue">
              Continue
            </button>
          ) : (
            <button type="button" className="btn btn-accent btn-lg pay-btn" data-dock-avoid disabled={app.paying} onClick={() => void app.submit()}>
              {app.paying ? (
                <>
                  <Loader2 size={18} className="spin" /> Processing payment…
                </>
              ) : (
                <>
                  <Lock size={16} /> Pay {program ? rupees(program.application_fee) : "the fee"} and submit
                </>
              )}
            </button>
          )}
        </div>
      </form>
    </>
  );
}

function Field({ f }: { f: FormField }) {
  const value = useApplication((s) => s.values[f.name] ?? "");
  const values = useApplication((s) => s.values);
  const flagged = useApplication((s) => s.flagged.includes(f.name));
  const set = useApplication((s) => s.set);
  const files = useApplication((s) => s.files);
  const id = `f-${f.name}`;
  const label = (
    <span className="field-label">
      {f.label}
      {f.required ? <span className="req"> *</span> : <span className="opt"> (optional)</span>}
    </span>
  );
  const help = f.help ? <span className="field-help">{f.help}</span> : null;
  const err = flagged ? <span className="field-error">{value && invalid(f, value) ? invalid(f, value) : "Required"}</span> : null;

  if (f.type === "text" || f.type === "percent") {
    return <TextField f={f} label={label} help={help} err={err} />;
  }

  if (f.type === "program") {
    return (
      <label className={`field field-wide${flagged ? " is-flagged" : ""}`} htmlFor={id} data-stage-group>
        {label}
        <select id={id} name="program" value={value} onChange={(e) => set("program", e.target.value)}>
          <option value="">Choose a programme</option>
          {SCHOOLS.map((s) => (
            <optgroup key={s.id} label={s.name}>
              {programsOf(s.id).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        {err}
      </label>
    );
  }

  if (f.type === "document") {
    return (
      <div className={`doc-row${flagged ? " is-flagged" : ""}`} data-field={f.name} data-stage-group>
        <div>
          {label}
          <span className="doc-status">
            {value === "uploaded" ? (
              <>
                <CircleCheck size={15} /> {files[f.name]}
              </>
            ) : value === "later" ? (
              "You'll upload it from the applicant portal"
            ) : (
              "PDF, JPG or PNG, up to 5 MB"
            )}
          </span>
          {err}
        </div>
        <div className="doc-actions" role="radiogroup" aria-label={f.label}>
          <button type="button" role="radio" aria-checked={value === "uploaded"} className={`pill${value === "uploaded" ? " is-on" : ""}`} data-stage-part={`${f.name}:uploaded`} onClick={() => set(f.name, "uploaded")}>
            <FileUp size={15} /> {value === "uploaded" ? "Uploaded" : "Upload"}
          </button>
          <button type="button" role="radio" aria-checked={value === "later"} className={`pill${value === "later" ? " is-on" : ""}`} data-stage-part={`${f.name}:later`} onClick={() => set(f.name, "later")}>
            Upload later
          </button>
        </div>
      </div>
    );
  }

  // choice, intake, scholarship: pills.
  const options = optionsFor(f, values);
  const needsProgram = (f.type === "intake" || f.type === "scholarship" || f.name === "campus") && !values.program;
  return (
    <div className={`field field-wide${flagged ? " is-flagged" : ""}`} data-field={f.name} data-stage-group>
      <span id={`${id}-l`}>{label}</span>
      {needsProgram && f.name !== "campus" ? (
        <span className="field-help">Choose a programme first.</span>
      ) : (
        <div className={`pills${f.name === "state" ? " pills-many" : ""}`} role="radiogroup" aria-labelledby={`${id}-l`}>
          {options.map(([oid, olabel]) => (
            <button
              key={oid}
              type="button"
              role="radio"
              aria-checked={value === oid}
              className={`pill${value === oid ? " is-on" : ""}`}
              data-stage-part={`${f.name}:${oid}`}
              onClick={() => set(f.name, f.name === "declaration" && value === oid ? "" : oid)}
            >
              {value === oid ? <Check size={14} /> : null}
              {olabel}
            </button>
          ))}
        </div>
      )}
      {help}
      {err}
    </div>
  );
}

/** A typed field commits on blur (and on Enter), so each keystroke is not an event. */
function TextField({ f, label, help, err }: { f: FormField; label: React.ReactNode; help: React.ReactNode; err: React.ReactNode }) {
  const stored = useApplication((s) => s.values[f.name] ?? "");
  const set = useApplication((s) => s.set);
  const [draft, setDraft] = useState(stored);
  useEffect(() => setDraft(stored), [stored]);
  const commit = () => {
    const v = draft.trim().replace(/%$/, "");
    if (v !== stored) set(f.name, v);
  };
  const id = `f-${f.name}`;
  return (
    <label className={`field${err ? " is-flagged" : ""}`} htmlFor={id} data-stage-group>
      {label}
      <span className={f.type === "percent" ? "input-suffix" : undefined}>
        <input
          id={id}
          name={f.name}
          value={draft}
          placeholder={f.placeholder}
          inputMode={f.type === "percent" ? "decimal" : f.name === "mobile" ? "tel" : f.name === "email" ? "email" : undefined}
          autoComplete={f.name === "full_name" ? "name" : f.name === "email" ? "email" : f.name === "mobile" ? "tel" : f.name === "city" ? "address-level2" : "off"}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => e.key === "Enter" && commit()}
        />
        {f.type === "percent" ? <span aria-hidden>%</span> : null}
      </span>
      {help}
      {err}
    </label>
  );
}

function Review() {
  const values = useApplication((s) => s.values);
  const setStep = useApplication((s) => s.setStep);
  return (
    <div className="review">
      {STEPS.slice(0, 4).map((s) => (
        <section key={s.step} className="review-step">
          <header>
            <h3>{s.title}</h3>
            <button type="button" className="text-btn" onClick={() => setStep(s.step)}>
              Edit
            </button>
          </header>
          <dl>
            {s.fields
              .filter((f) => shown(f, values))
              .map((f) => {
                const v = values[f.name];
                const shownValue = !v
                  ? "—"
                  : f.type === "percent"
                    ? `${v}%`
                    : f.type === "program"
                      ? (programById(v)?.name ?? v)
                      : f.type === "text"
                        ? v
                        : (optionsFor(f, values).find(([id]) => id === v)?.[1] ?? v);
                return (
                  <div key={f.name}>
                    <dt>{f.label}</dt>
                    <dd className={v ? "" : "muted"}>{shownValue}</dd>
                  </div>
                );
              })}
          </dl>
        </section>
      ))}
    </div>
  );
}

function Summary() {
  const values = useApplication((s) => s.values);
  const p = programById(values.program);
  const school = p ? schoolById(p.school) : null;
  const r = p ? nextRound(p.intake) : null;
  return (
    <aside className="apply-summary" data-stage-thing="summary" data-stage-label="Your programme" style={{ "--accent": school?.accent } as React.CSSProperties}>
      <h2>Your programme</h2>
      {p ? (
        <>
          <p className="summary-name">
            <Link to={`/programs/${p.id}`}>{p.name}</Link>
          </p>
          <p className="muted">{school?.name}</p>
          <dl>
            <div>
              <dt>Campus</dt>
              <dd>{values.campus ? campusNames({ ...p, campuses: [values.campus] }) : campusNames(p)}</dd>
            </div>
            <div>
              <dt>Fee a year</dt>
              <dd className="num">{rupees(p.fee_per_year)}</dd>
            </div>
            <div>
              <dt>Application fee</dt>
              <dd className="num">{rupees(p.application_fee)}</dd>
            </div>
            <div>
              <dt>Next deadline</dt>
              <dd>{r ? `${r.deadline}, ${r.name}` : "—"}</dd>
            </div>
          </dl>
        </>
      ) : (
        <p className="muted">Choose a programme on step 3, or start from a programme page's Apply button.</p>
      )}
      <p className="summary-help">
        Questions? {ADMISSIONS.contact.phone}, {ADMISSIONS.contact.hours}.
      </p>
    </aside>
  );
}

function Confirmation() {
  const sub = useApplication((s) => s.submitted)!;
  const reset = useApplication((s) => s.reset);
  const p = programById(sub.program);
  return (
    <section className="confirmation" data-stage-thing="confirmation" data-stage-label="Application submitted">
      <CircleCheck size={40} className="confirm-icon" />
      <h2>Application submitted</h2>
      <p className="ref">
        Application number <b>{sub.reference}</b>
      </p>
      <p>
        {p?.name}: application fee of {rupees(sub.fee)} paid. A copy is on its way to your email.
      </p>
      <h3>What happens next</h3>
      <ol className="steps-list">
        {ADMISSIONS.process.slice(2).map((s) => (
          <li key={s.step}>
            <b>{s.title}.</b> {s.text}
          </li>
        ))}
      </ol>
      <p>
        <button type="button" className="btn btn-ghost" onClick={reset}>
          Start another application
        </button>
      </p>
    </section>
  );
}
