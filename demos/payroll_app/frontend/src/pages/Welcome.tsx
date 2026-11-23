/**
 * First sign-in: the setup wizard. Fields start empty. The company details
 * can come from signup; the pay structure and leave policy are the admin's
 * choice (or the common defaults, which she can edit); the employee file is
 * imported by the admin herself (owner, round 1, A1).
 */
import { useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Check, CircleAlert, Download, FileSpreadsheet, ListChecks, Play, Sparkles, Upload } from "lucide-react";
import sampleUrl from "../../../data/employees_import.csv?url";
import { COMPANY } from "../lib/data";
import { rupees } from "../lib/format";
import { parseCsv } from "../lib/payroll";
import { fieldsOf, PRESET_SOURCE, SETUP_STEPS, type SetupField, type SetupStep, STEP_TITLES } from "../lib/setup";
import { fillPresets, finishSetup, importEmployees, runTestPayroll, SAMPLE_IMPORT, setSetupField, setSetupStep, useTk } from "../state/store";
import { PageHead, TableWrap, thing } from "../components/ui";

const DRAFT = COMPANY.payroll_runs.find((r) => r.id === "PR-2026-02")!;

function Field({ f }: { f: SetupField }) {
  const value = useTk((s) => s.setup.fields[f.name] ?? "");
  const set = (v: string) => setSetupField(f.name, v);
  const common = { name: f.name, "data-setup-field": f.name, value, id: `f-${f.name}` };
  return (
    <label className={`field${f.kind === "textarea" ? " span-2" : ""}`} htmlFor={`f-${f.name}`} {...thing(f.label, `setup-${f.name}`)}>
      <span>
        {f.label}
        {f.hint ? <small className="muted"> {f.hint}</small> : null}
      </span>
      <span className={`input-unit${f.unit ? " has-unit" : ""}`}>
        {f.unit === "₹" ? <span className="unit pre">₹</span> : null}
        {f.kind === "select" ? (
          <select {...common} onChange={(e) => set(e.target.value)}>
            <option value="">Choose…</option>
            {f.options!.map((o) => (
              <option key={o}>{o}</option>
            ))}
          </select>
        ) : f.kind === "textarea" ? (
          <textarea {...common} rows={2} onChange={(e) => set(e.target.value)} />
        ) : (
          <input {...common} inputMode={f.kind === "number" ? "numeric" : undefined} onChange={(e) => useTk.setState((s) => ({ setup: { ...s.setup, fields: { ...s.setup.fields, [f.name]: e.target.value } } }))} onBlur={(e) => set(e.target.value)} />
        )}
        {f.unit && f.unit !== "₹" ? <span className="unit post">{f.unit}</span> : null}
      </span>
    </label>
  );
}

function FieldsStep({ step, intro }: { step: SetupStep; intro: string }) {
  const fields = fieldsOf(step);
  const filled = useTk((s) => fields.filter((f) => s.setup.fields[f.name]?.trim()).length);
  return (
    <section className="step-body" {...thing(STEP_TITLES[step], `step-${step}`)}>
      <div className="step-head">
        <div>
          <h2>{STEP_TITLES[step]}</h2>
          <p className="muted">{intro}</p>
        </div>
        <button type="button" className="btn btn-ghost" data-presets={step} onClick={() => fillPresets(step, fields)} {...thing(PRESET_SOURCE[step] === "signup" ? "Use details from signup" : "Use common defaults")}>
          {PRESET_SOURCE[step] === "signup" ? <Sparkles size={15} aria-hidden /> : <ListChecks size={15} aria-hidden />}
          {PRESET_SOURCE[step] === "signup" ? "Use details from signup" : "Use common defaults"}
        </button>
      </div>
      <div className="fields">
        {fields.map((f) => (
          <Field key={f.name} f={f} />
        ))}
      </div>
      <p className="small muted">
        {filled} of {fields.length} filled
      </p>
    </section>
  );
}

/** The sample file's header and first rows, as the example of what the import expects. */
const SAMPLE = parseCsv(SAMPLE_IMPORT);
const EXAMPLE_COLS = ["employee_id", "name", "department", "designation", "location", "date_of_joining", "annual_ctc", "pan", "tax_regime", "manager_id"];

function ImportStep() {
  const imp = useTk((s) => s.setup.imported);
  const input = useRef<HTMLInputElement>(null);
  const choose = async (file: File | undefined) => {
    if (!file) return;
    importEmployees(await file.text(), file.name);
    if (input.current) input.current.value = "";
  };
  return (
    <section className="step-body">
      <div className="step-head">
        <div>
          <h2>Import employees</h2>
          <p className="muted">One row per person, exported from your previous payroll or a spreadsheet. Paynora checks every row before anything is saved.</p>
        </div>
      </div>
      <div className="import-example" {...thing("Expected data", "import-example")}>
        <div className="import-example-head">
          <h3>What the file looks like</h3>
          <a className="btn btn-ghost" href={sampleUrl} download="employees_import.csv" data-sample-download {...thing("Download sample file", "sample-download")}>
            <Download size={15} aria-hidden /> Download sample file
          </a>
        </div>
        <p className="small muted">
          A CSV with these {SAMPLE.header.length} columns, in any order: {SAMPLE.header.join(", ")}. Dates as YYYY-MM-DD, CTC in rupees a year, regime new or old. The sample is {COMPANY.company.name}'s own file, {SAMPLE.rows.length} rows.
        </p>
        <TableWrap label="Example rows" className="import-table">
          <table className="grid dense">
            <thead>
              <tr>
                {EXAMPLE_COLS.map((c) => (
                  <th key={c} scope="col" className={c === "annual_ctc" ? "r" : undefined}>
                    <code>{c}</code>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {SAMPLE.rows.slice(0, 3).map((r) => (
                <tr key={r.employee_id}>
                  {EXAMPLE_COLS.map((c) => (
                    <td key={c} className={`${c === "annual_ctc" ? "r " : ""}num nowrap`}>
                      {r[c] || "—"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      </div>
      <div className={`dropzone${imp ? " is-done" : ""}`} {...thing("Import employees", "step-import")}>
        <FileSpreadsheet size={28} aria-hidden />
        <div>
          <strong>{imp ? imp.file : "Your employee file"}</strong>
          <span className="small muted">{imp ? `${imp.rows.length} rows read` : "Choose the CSV on your computer: the sample above works"}</span>
        </div>
        <input ref={input} type="file" accept=".csv,text/csv" hidden data-import-input onChange={(e) => void choose(e.target.files?.[0])} />
        <button type="button" className="btn btn-primary" data-import onClick={() => input.current?.click()} {...thing("Import file", "import-file")}>
          <Upload size={15} aria-hidden /> {imp ? "Import another file" : "Import file"}
        </button>
      </div>
      {imp ? (
        <>
          <div className="validation" {...thing("Validation summary")}>
            <div className={`v-big ${imp.issues.length ? "bad" : "ok"}`}>
              {imp.issues.length ? <CircleAlert size={22} aria-hidden /> : <Check size={22} aria-hidden />}
              <span>
                <strong>
                  {imp.valid} of {imp.rows.length} rows valid
                </strong>
                <small>{imp.issues.length ? `${imp.issues.length} to fix` : "No errors: required fields, PAN format, duplicate IDs and managers all check out"}</small>
              </span>
            </div>
            <dl className="v-stats">
              <div>
                <dt>Rows</dt>
                <dd className="num">{imp.rows.length}</dd>
              </div>
              <div>
                <dt>Valid</dt>
                <dd className="num">{imp.valid}</dd>
              </div>
              <div>
                <dt>Errors</dt>
                <dd className="num">{imp.issues.length}</dd>
              </div>
              <div>
                <dt>New regime</dt>
                <dd className="num">{imp.regimes.new}</dd>
              </div>
              <div>
                <dt>Old regime</dt>
                <dd className="num">{imp.regimes.old}</dd>
              </div>
            </dl>
            <ul className="v-locations">
              {imp.byLocation.map(([city, n]) => (
                <li key={city}>
                  <span>{city}</span>
                  <span className="num">{n}</span>
                </li>
              ))}
            </ul>
            {imp.issues.length ? (
              <ul className="v-issues">
                {imp.issues.map((i, n) => (
                  <li key={n}>
                    Row {i.row}, {i.employee_id}: {i.problem}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
          <TableWrap label="Imported rows" className="import-table">
            <table className="grid dense">
              <thead>
                <tr>
                  <th scope="col">ID</th>
                  <th scope="col">Name</th>
                  <th scope="col">Department</th>
                  <th scope="col">Designation</th>
                  <th scope="col">Location</th>
                  <th scope="col">Joined</th>
                  <th scope="col" className="r">Annual CTC</th>
                  <th scope="col">PAN</th>
                  <th scope="col">Regime</th>
                  <th scope="col">Manager</th>
                </tr>
              </thead>
              <tbody>
                {imp.rows.map((r) => (
                  <tr key={r.employee_id}>
                    <td className="num">{r.employee_id}</td>
                    <td className="nowrap">{r.name}</td>
                    <td>{r.department}</td>
                    <td>{r.designation}</td>
                    <td>{r.location}</td>
                    <td className="num nowrap">{r.date_of_joining}</td>
                    <td className="r num">{rupees(Number(r.annual_ctc))}</td>
                    <td className="num">{r.pan}</td>
                    <td>{r.tax_regime}</td>
                    <td className="num">{r.manager_id || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        </>
      ) : null}
    </section>
  );
}

function TestStep() {
  const st = useTk((s) => s.setup);
  const t = st.test?.totals;
  const KEYS: [string, keyof typeof DRAFT][] = [
    ["Employees", "employees"],
    ["Gross", "gross"],
    ["Employee PF", "employee_pf"],
    ["Professional tax", "professional_tax"],
    ["TDS", "tds"],
    ["Reimbursements", "reimbursements"],
    ["Net pay", "net_pay"],
    ["Employer cost", "employer_cost"],
  ];
  const matches = t && KEYS.every(([, k]) => t[k as keyof typeof t] === DRAFT[k]);
  return (
    <section className="step-body">
      <div className="step-head">
        <div>
          <h2>Test payroll</h2>
          <p className="muted">A February 2026 run over the imported employees, with nothing paid. Pay so far this year, verified declarations, approved leave and claims come over from your previous payroll.</p>
        </div>
      </div>
      <div className="testrun" {...thing("Test payroll", "step-test_run")}>
        <span>
          <strong>February 2026, 28 days</strong>
          <small className="block muted">{st.imported ? `${st.imported.valid} employees imported` : "Import employees first"}</small>
        </span>
        <button type="button" className="btn btn-primary" data-test-run disabled={!st.imported} onClick={() => runTestPayroll()}>
          <Play size={15} aria-hidden /> {t ? "Run again" : "Run test payroll"}
        </button>
      </div>
      {t ? (
        <div className="test-totals" {...thing("Test totals")}>
          <TableWrap label="Test totals">
            <table className="grid">
              <thead>
                <tr>
                  <th scope="col">Total</th>
                  <th scope="col" className="r">Test run</th>
                  <th scope="col" className="r">Previous payroll, February</th>
                </tr>
              </thead>
              <tbody>
                {KEYS.map(([l, k]) => (
                  <tr key={k}>
                    <th scope="row">{l}</th>
                    <td className="r num strong">{k === "employees" ? t.employees : rupees(t[k as keyof typeof t] as number)}</td>
                    <td className="r num muted">{k === "employees" ? DRAFT.employees : rupees(DRAFT[k] as number)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
          <p className={`match ${matches ? "ok" : "bad"}`}>
            {matches ? <Check size={16} aria-hidden /> : <CircleAlert size={16} aria-hidden />}
            {matches ? "Every total matches, to the rupee. Tax figures are illustrative, FY 2025-26." : "Some totals differ; check the rows flagged on the import step."}
          </p>
        </div>
      ) : null}
    </section>
  );
}

function DoneStep() {
  const st = useTk((s) => s.setup);
  const navigate = useNavigate();
  const filled = Object.values(st.fields).filter((v) => v.trim()).length;
  return (
    <section className="step-body" {...thing("Done", "step-done")}>
      <h2>Ready for February</h2>
      <ul className="checks">
        <li className={filled ? "is-done" : ""}>
          <Check size={16} aria-hidden /> {filled} setup fields filled
        </li>
        <li className={st.imported ? "is-done" : ""}>
          <Check size={16} aria-hidden /> {st.imported ? `${st.imported.valid} employees imported` : "Employees not imported yet"}
        </li>
        <li className={st.test ? "is-done" : ""}>
          <Check size={16} aria-hidden /> {st.test ? "Test payroll matches" : "Test payroll not run yet"}
        </li>
      </ul>
      <button
        type="button"
        className="btn btn-primary"
        data-finish-setup
        disabled={!st.test}
        onClick={() => {
          if (finishSetup().ok) navigate("/");
        }}
      >
        Finish setup
      </button>
    </section>
  );
}

const INTRO: Partial<Record<SetupStep, string>> = {
  company: "As registered. These go on payslips, Form 16 and the statutory returns.",
  structure: "How a CTC becomes a monthly salary. Every employee's structure is worked out from this rule.",
  leave: "Leave types, how they accrue, and when leave becomes loss of pay.",
};

export function WelcomePage() {
  const step = useTk((s) => s.setup.step);
  const st = useTk((s) => s.setup);
  const done = (s: SetupStep): boolean =>
    s === "import" ? !!st.imported : s === "test_run" ? !!st.test : s === "done" ? st.finished : fieldsOf(s).every((f) => st.fields[f.name]?.trim());
  const i = SETUP_STEPS.indexOf(step);
  return (
    <div className="page welcome">
      <PageHead title="Welcome to Paynora" sub={`Set up ${COMPANY.company.name} for payroll. Six steps; you can come back to any of them.`} />
      <ol className="stepper">
        {SETUP_STEPS.map((s, n) => (
          <li key={s}>
            <button type="button" className={`step${s === step ? " is-on" : ""}${done(s) ? " is-done" : ""}`} data-setup-step={s} aria-current={s === step ? "step" : undefined} onClick={() => setSetupStep(s)}>
              <span className="step-n">{done(s) ? <Check size={13} aria-hidden /> : n + 1}</span>
              <span className="step-t">{STEP_TITLES[s]}</span>
            </button>
          </li>
        ))}
      </ol>
      <div className="panel wizard">
        {step === "company" || step === "structure" || step === "leave" ? <FieldsStep step={step} intro={INTRO[step]!} /> : null}
        {step === "import" ? <ImportStep /> : null}
        {step === "test_run" ? <TestStep /> : null}
        {step === "done" ? <DoneStep /> : null}
        <div className="wizard-nav">
          <button type="button" className="btn btn-ghost" disabled={i === 0} onClick={() => setSetupStep(SETUP_STEPS[i - 1]!)}>
            Back
          </button>
          {i < SETUP_STEPS.length - 1 ? (
            <button type="button" className="btn btn-primary" onClick={() => setSetupStep(SETUP_STEPS[i + 1]!)}>
              Next: {STEP_TITLES[SETUP_STEPS[i + 1]!]}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
