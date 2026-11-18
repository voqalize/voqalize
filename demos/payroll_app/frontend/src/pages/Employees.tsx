import { useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { UserPlus } from "lucide-react";
import { COMPANY, SLIP_MONTHS } from "../lib/data";
import { date, monthShort, rupees } from "../lib/format";
import { structure } from "../lib/engine";
import { comparisonOf, formProblems, GRADES, joiningLop, type NewField, previewSlip, stateOfCity } from "../lib/payroll";
import { employee, febSlipOf, locked, nameOf, nextEmployeeId, saveEmployee, setNewField, useTk } from "../state/store";
import { Avatar, Dialog, PageHead, Panel, Status, TableWrap, thing } from "../components/ui";

export function EmployeesList() {
  const employees = useTk((s) => s.employees);
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const dept = params.get("department") ?? "";
  const loc = params.get("location") ?? "";
  const regime = params.get("regime") ?? "";
  const setP = (k: string, v: string) => {
    const n = new URLSearchParams(params);
    if (v) n.set(k, v);
    else n.delete(k);
    setParams(n, { replace: true });
  };
  const rows = useMemo(
    () =>
      employees.filter(
        (e) =>
          (!q || `${e.name} ${e.id} ${e.title}`.toLowerCase().includes(q.toLowerCase())) &&
          (!dept || e.department === dept) &&
          (!loc || e.location === loc) &&
          (!regime || e.tax_regime === regime),
      ),
    [employees, q, dept, loc, regime],
  );
  return (
    <div className="page">
      <PageHead
        title="Employees"
        sub={`${employees.length} people across ${COMPANY.company.locations.length} locations`}
        actions={
          <Link to="/employees/new" className="btn btn-primary">
            <UserPlus size={16} aria-hidden /> Add employee
          </Link>
        }
      />
      <div className="filters">
        <input type="search" placeholder="Name, ID or title" value={q} onChange={(e) => setP("q", e.target.value)} aria-label="Search employees" />
        <select value={dept} onChange={(e) => setP("department", e.target.value)} aria-label="Department">
          <option value="">All departments</option>
          {COMPANY.company.departments.map((d) => (
            <option key={d}>{d}</option>
          ))}
        </select>
        <select value={loc} onChange={(e) => setP("location", e.target.value)} aria-label="Location">
          <option value="">All locations</option>
          {COMPANY.company.locations.map((l) => (
            <option key={l.city}>{l.city}</option>
          ))}
        </select>
        <select value={regime} onChange={(e) => setP("regime", e.target.value)} aria-label="Tax regime">
          <option value="">Both regimes</option>
          <option value="new">New regime</option>
          <option value="old">Old regime</option>
        </select>
        <span className="small muted filters-count">{rows.length} shown</span>
      </div>
      <TableWrap label="Employees">
        <table className="grid">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Department</th>
              <th scope="col">Location</th>
              <th scope="col">Grade</th>
              <th scope="col">Joined</th>
              <th scope="col">Regime</th>
              <th scope="col" className="r">Annual CTC</th>
              <th scope="col" className="r">Feb net</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id}>
                <td>
                  <Link to={`/employees/${e.id}`} className="person">
                    <Avatar name={e.name} />
                    <span>
                      <strong>{e.name}</strong>
                      <small>
                        {e.id}, {e.title}
                      </small>
                    </span>
                  </Link>
                </td>
                <td>{e.department}</td>
                <td>{e.location}</td>
                <td>{e.grade}</td>
                <td className="nowrap">{date(e.joined)}</td>
                <td>{e.tax_regime === "new" ? "New" : "Old"}</td>
                <td className="r num">{rupees(e.annual_ctc)}</td>
                <td className="r num">{rupees(febSlipOf(e.id)?.net_pay ?? 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
      {!rows.length ? <p className="empty">No one matches these filters. Clear a filter to see more people.</p> : null}
    </div>
  );
}

export function EmployeeDetail() {
  const { id = "" } = useParams();
  const st = useTk();
  const e = employee(id, st);
  if (!e)
    return (
      <div className="page">
        <PageHead title="No such employee" sub={`There is no employee ${id}.`} />
        <Link to="/employees">Back to employees</Link>
      </div>
    );
  const s = structure(e.annual_ctc, e.location, e.lta_monthly);
  const cmp = comparisonOf(e, st.declarations);
  const decl = st.declarations.find((d) => d.employee_id === e.id);
  const slips = st.payslips[e.id] ?? [];
  const reports = st.employees.filter((x) => x.manager_id === e.id);
  const y = e.ytd_to_jan;
  return (
    <div className="page">
      <PageHead
        title={e.name}
        sub={`${e.title}, ${e.department}. ${e.id}, ${e.grade}, ${e.location}.`}
        actions={
          <>
            <Link className="btn btn-ghost" to={`/me/${e.id}/payslips`}>
              View as {e.name.split(" ")[0]}
            </Link>
            <Link className="btn btn-primary" to={`/tax/regime/${e.id}`}>
              Compare regimes
            </Link>
          </>
        }
      />
      <div className="detail-grid">
        <Panel title="Job">
          <dl className="kv">
            <dt>Joined</dt>
            <dd>{date(e.joined)}</dd>
            <dt>Manager</dt>
            <dd>{e.manager_id ? <Link to={`/employees/${e.manager_id}`}>{nameOf(e.manager_id, st)}</Link> : "None"}</dd>
            <dt>Reports</dt>
            <dd>{reports.length ? reports.map((r) => r.name).join(", ") : "None"}</dd>
            <dt>Email</dt>
            <dd>{e.email}</dd>
            <dt>PAN</dt>
            <dd className="num">{e.pan || "To collect"}</dd>
            <dt>UAN</dt>
            <dd className="num">{e.uan || "To generate"}</dd>
            <dt>Bank</dt>
            <dd>{e.bank || "To collect"}</dd>
          </dl>
        </Panel>
        <Panel title="Salary structure" actions={<span className="small muted">from the engine</span>}>
          <TableWrap label="Salary structure">
            <table className="dense">
              <tbody>
                <tr>
                  <th scope="row">Annual CTC</th>
                  <td className="r num">{rupees(e.annual_ctc)}</td>
                </tr>
                <tr>
                  <th scope="row">Monthly CTC</th>
                  <td className="r num">{rupees(s.monthly_ctc)}</td>
                </tr>
                {(
                  [
                    ["Basic", s.basic],
                    ["HRA", s.hra],
                    ["LTA", s.lta],
                    ["Special allowance", s.special],
                  ] as const
                ).map(([k, v]) => (
                  <tr key={k}>
                    <th scope="row" className="indent">
                      {k}
                    </th>
                    <td className="r num">{rupees(v)}</td>
                  </tr>
                ))}
                <tr className="is-strong">
                  <th scope="row">Gross a month</th>
                  <td className="r num">{rupees(s.gross)}</td>
                </tr>
                <tr>
                  <th scope="row">Employer PF</th>
                  <td className="r num">{rupees(s.employer_pf)}</td>
                </tr>
                {s.esi_applicable ? (
                  <tr>
                    <th scope="row">Employer ESI</th>
                    <td className="r num">{rupees(s.employer_esi)}</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </TableWrap>
        </Panel>
        <Panel title="Tax regime" actions={<Link to={`/tax/regime/${e.id}`} className="link small">Full comparison</Link>}>
          <p>
            TDS on the <strong>{e.tax_regime} regime</strong>
            {e.regime_chosen_on ? `, chosen ${date(e.regime_chosen_on)}` : ", the default"}.
          </p>
          <dl className="kv">
            <dt>New regime</dt>
            <dd className="num">{rupees(cmp.new.total_tax)}</dd>
            <dt>Old regime</dt>
            <dd className="num">{rupees(cmp.old.total_tax)}</dd>
            <dt>Lower</dt>
            <dd>{cmp.saving ? `${cmp.better === "new" ? "New" : "Old"}, by ${rupees(cmp.saving)}` : "Equal"}</dd>
          </dl>
        </Panel>
        <Panel title="Leave balances">
          <dl className="kv">
            <dt>Earned leave</dt>
            <dd className="num">{e.leave_balance.EL}</dd>
            <dt>Casual leave</dt>
            <dd className="num">{e.leave_balance.CL}</dd>
            <dt>Sick leave</dt>
            <dd className="num">{e.leave_balance.SL}</dd>
          </dl>
        </Panel>
        <Panel title="Year to date, April to January">
          <dl className="kv">
            <dt>Gross</dt>
            <dd className="num">{rupees(y.gross)}</dd>
            <dt>Provident fund</dt>
            <dd className="num">{rupees(y.employee_pf)}</dd>
            <dt>Professional tax</dt>
            <dd className="num">{rupees(y.professional_tax)}</dd>
            <dt>TDS</dt>
            <dd className="num">{rupees(y.tds)}</dd>
            <dt>Months paid</dt>
            <dd className="num">{y.months}</dd>
          </dl>
        </Panel>
        <Panel title="Payslips">
          <ul className="linklist">
            {SLIP_MONTHS.filter((m) => slips.some((x) => x.month === m))
              .reverse()
              .map((m) => (
                <li key={m}>
                  <Link to={`/payslips/${e.id}/${m}`}>{monthShort(m)}</Link>
                  <span className="num">{rupees(slips.find((x) => x.month === m)!.net_pay)}</span>
                </li>
              ))}
          </ul>
        </Panel>
        <Panel title="Declarations" className="span-2">
          {decl ? (
            <TableWrap label="Declarations">
              <table className="dense">
                <thead>
                  <tr>
                    <th scope="col">Item</th>
                    <th scope="col">Section</th>
                    <th scope="col" className="r">Declared</th>
                    <th scope="col" className="r">Verified</th>
                    <th scope="col">Proof</th>
                  </tr>
                </thead>
                <tbody>
                  {decl.items.map((i) => (
                    <tr key={i.label}>
                      <td>{i.label}</td>
                      <td>{i.section.replace("_", " ")}</td>
                      <td className="r num">{rupees(i.declared)}</td>
                      <td className="r num">{rupees(i.verified)}</td>
                      <td>
                        <Status value={i.proof_status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          ) : (
            <p className="muted">No investment declarations for FY 2025-26. Tax is worked out with none.</p>
          )}
        </Panel>
      </div>
    </div>
  );
}

const LABELS: Record<NewField, string> = {
  name: "Full name",
  email: "Work email",
  gender: "Gender",
  department: "Department",
  title: "Designation",
  grade: "Grade",
  location: "Location",
  joined: "Date of joining",
  annual_ctc: "Annual CTC",
  tax_regime: "Tax regime",
  manager_id: "Reporting manager",
};

export function EmployeeNew() {
  const st = useTk();
  const f = st.newForm;
  const navigate = useNavigate();
  const [tried, setTried] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const problems = formProblems(f, st.employees.map((e) => e.id));
  const preview = previewSlip(f);
  const nextId = nextEmployeeId(st);
  const input = (k: NewField, el: React.ReactNode) => (
    <label className={`field${tried && problems[k] ? " has-error" : ""}`} data-field={k} {...thing(LABELS[k], `field-${k}`)}>
      <span>{LABELS[k]}</span>
      {el}
      {tried && problems[k] ? <small className="err">{problems[k]}</small> : null}
    </label>
  );
  const text = (k: NewField, type = "text", extra: Record<string, unknown> = {}) =>
    input(k, <input name={k} type={type} value={f[k]} onChange={(e) => setNewField(k, e.target.value)} {...extra} />);
  const select = (k: NewField, options: [string, string][]) =>
    input(
      k,
      <select name={k} value={f[k]} onChange={(e) => setNewField(k, e.target.value)}>
        <option value="">Choose…</option>
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>,
    );
  return (
    <div className="page">
      <PageHead title="Add employee" sub={`A February 2026 joiner. Saved as ${nextId}; their prorated February pay joins the draft run.`} />
      <div className="form-grid">
        <form
          className="panel form"
          data-stage-form="new-employee"
          onSubmit={(ev) => {
            ev.preventDefault();
            setTried(true);
            if (!Object.keys(problems).length) setConfirm(true);
          }}
        >
          <fieldset>
            <legend>Person</legend>
            {text("name", "text", { autoComplete: "off" })}
            {text("email", "email")}
            {select("gender", [
              ["F", "Female"],
              ["M", "Male"],
            ])}
          </fieldset>
          <fieldset>
            <legend>Job</legend>
            {select("department", COMPANY.company.departments.map((d) => [d, d]))}
            {text("title")}
            {select("grade", GRADES.map((g) => [g, g]))}
            {select("location", COMPANY.company.locations.map((l) => [l.city, `${l.city}, ${l.state}`]))}
            {text("joined", "date", { min: "2026-02-01", max: "2026-02-28" })}
            {select(
              "manager_id",
              st.employees.map((e) => [e.id, `${e.name}, ${e.id}`]),
            )}
          </fieldset>
          <fieldset>
            <legend>Pay</legend>
            {text("annual_ctc", "number", { min: 120000, step: 1000, inputMode: "numeric" })}
            {select("tax_regime", [
              ["new", "New regime (default)"],
              ["old", "Old regime"],
            ])}
          </fieldset>
          <div className="form-actions">
            <Link to="/employees" className="btn btn-ghost">
              Cancel
            </Link>
            <button type="submit" className="btn btn-primary" data-save-employee disabled={locked(st)} {...thing("Save", "save-employee")}>
              Save and add to February
            </button>
          </div>
          {tried && Object.keys(problems).length ? <p className="err">Still needed: {Object.keys(problems).map((k) => LABELS[k as NewField]).join(", ")}.</p> : null}
        </form>
        <aside className="panel preview" {...thing("February pay preview", "pay-preview")}>
          <h2>February pay, prorated</h2>
          {preview ? (
            <>
              <p className="small muted">
                {f.location}, {stateOfCity(f.location)}. Joins {date(f.joined)}: {joiningLop(f.joined)} days before joining are unpaid, {preview.paid_days} of 28 paid.
              </p>
              <dl className="kv">
                <dt>Basic</dt>
                <dd className="num">{rupees(preview.basic)}</dd>
                <dt>HRA</dt>
                <dd className="num">{rupees(preview.hra)}</dd>
                <dt>LTA</dt>
                <dd className="num">{rupees(preview.lta)}</dd>
                <dt>Special allowance</dt>
                <dd className="num">{rupees(preview.special)}</dd>
                <dt>Gross</dt>
                <dd className="num strong">{rupees(preview.gross)}</dd>
                <dt>Provident fund</dt>
                <dd className="num">−{rupees(preview.employee_pf)}</dd>
                {preview.employee_esi ? (
                  <>
                    <dt>ESI</dt>
                    <dd className="num">−{rupees(preview.employee_esi)}</dd>
                  </>
                ) : null}
                <dt>Professional tax</dt>
                <dd className="num">−{rupees(preview.professional_tax)}</dd>
                <dt>TDS</dt>
                <dd className="num">−{rupees(preview.tds)}</dd>
              </dl>
              <p className="preview-net">
                <span>Net pay</span>
                <span className="num">{rupees(preview.net_pay)}</span>
              </p>
              <p className="small muted">Year's tax {rupees(preview.annual_tax)} on the {f.tax_regime || "new"} regime, spread over February and March. Illustrative, FY 2025-26.</p>
            </>
          ) : (
            <p className="muted">Enter a location, a joining date in February 2026 and the annual CTC to see the prorated pay.</p>
          )}
        </aside>
      </div>
      <Dialog open={confirm} title={`Add ${f.name || "this employee"} as ${nextId}?`} onClose={() => setConfirm(false)}>
        <p>
          Their prorated February pay{preview ? `, ${rupees(preview.net_pay)} net,` : ""} joins the draft run for {date("2026-02-27")}.
        </p>
        <div className="dialog-actions">
          <button type="button" className="btn btn-ghost" onClick={() => setConfirm(false)}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              const r = saveEmployee();
              setConfirm(false);
              if (r.ok) navigate(`/employees/${nextId}`);
            }}
          >
            Add employee
          </button>
        </div>
      </Dialog>
    </div>
  );
}

