import { Link } from "react-router-dom";
import { AlertTriangle, CalendarClock, FileCheck2, ReceiptIndianRupee, UserRoundCheck } from "lucide-react";
import { COMPANY, TODAY } from "../lib/data";
import { date, monthShort, rupees } from "../lib/format";
import { claimsToReview, draftRun, pendingLeave, useTk } from "../state/store";
import { PageHead, Panel, Status, TableWrap, thing } from "../components/ui";

const daysBetween = (a: string, b: string) => Math.round((Date.parse(b) - Date.parse(a)) / 86400000);

export function Dashboard() {
  const st = useTk();
  const run = draftRun(st);
  const leave = pendingLeave(st);
  const claims = claimsToReview(st);
  const fix = claims.filter((c) => c.status === "needs_fix");
  const decl = st.declarations;
  const missingProofs = decl.reduce((n, d) => n + d.items.filter((i) => i.proof_status === "not_submitted" || i.proof_status === "partly_verified").length, 0);
  const proofClose = COMPANY.company.windows.proofs.closes;
  const left = daysBetween(TODAY, proofClose);
  const byLoc = COMPANY.company.locations.map((l) => ({ ...l, n: st.employees.filter((e) => e.location === l.city).length }));
  const max = Math.max(...byLoc.map((l) => l.n));
  const recent = [...st.runs].reverse().slice(0, 5);

  return (
    <div className="page">
      <PageHead title="Good morning, Meghna" sub={`Monday, ${date(TODAY)}. February payroll closes in ${daysBetween(TODAY, "2026-02-25")} days.`} />

      <div className="dash-grid">
        <section className={`runcard${run.status === "draft" ? "" : " is-approved"}`} {...thing("February draft")}>
          <div className="runcard-head">
            <div>
              <h2>February 2026 payroll</h2>
              <p className="muted small">
                {run.id}, pay date {date(run.pay_date)}, {run.days} days
              </p>
            </div>
            <Status value={run.status} />
          </div>
          <div className="runcard-net">
            <span className="small muted">Net pay to {run.employees} employees</span>
            <span className="runcard-figure">{rupees(run.net_pay)}</span>
          </div>
          <dl className="runcard-stats">
            <div>
              <dt>Gross</dt>
              <dd className="num">{rupees(run.gross)}</dd>
            </div>
            <div>
              <dt>TDS</dt>
              <dd className="num">{rupees(run.tds)}</dd>
            </div>
            <div>
              <dt>PF, employee and employer</dt>
              <dd className="num">{rupees(run.employee_pf + run.employer_pf)}</dd>
            </div>
            <div>
              <dt>Employer cost</dt>
              <dd className="num">{rupees(run.employer_cost)}</dd>
            </div>
          </dl>
          <div className="runcard-foot">
            <span className="small">
              {run.status === "draft" ? `${leave.length + claims.length} items to review before ${COMPANY.company.payroll_approver.name} approves` : `Approved by ${run.approved_by}`}
            </span>
            <Link to={`/payroll/${run.id}`} className="btn btn-primary">
              Review run
            </Link>
          </div>
        </section>

        <Panel title="Needs your attention" className="alerts" {...thing("Alerts")}>
          <ul className="alert-list">
            <li>
              <CalendarClock size={18} aria-hidden className="ic-warn" />
              <div>
                <Link to="/leave?tab=requests">{leave.length} leave requests pending</Link>
                <span className="small muted">Leave beyond the balance becomes loss of pay in February</span>
              </div>
            </li>
            <li>
              <ReceiptIndianRupee size={18} aria-hidden className={fix.length ? "ic-bad" : "ic-warn"} />
              <div>
                <Link to="/reimbursements">{claims.length} claims to review</Link>
                <span className="small muted">
                  {fix.length ? `${fix.map((c) => c.id).join(", ")} claims more than its bill` : "All amounts match their bills"}
                </span>
              </div>
            </li>
            <li {...thing("Proof window")}>
              <FileCheck2 size={18} aria-hidden className="ic-warn" />
              <div>
                <Link to="/tax?tab=declarations">Proof window closes {date(proofClose)}</Link>
                <span className="small muted">
                  {left} days left; {missingProofs} declared {missingProofs === 1 ? "item has" : "items have"} no verified proof yet
                </span>
              </div>
            </li>
            <li>
              <AlertTriangle size={18} aria-hidden className="ic-info" />
              <div>
                <Link to="/tax?tab=form16">Form 16 for FY 2025-26</Link>
                <span className="small muted">Generated after the March run and the Q4 TDS return, by {date(COMPANY.form16.fy_2025_26.due_by)}</span>
              </div>
            </li>
          </ul>
        </Panel>

        <Panel title="Headcount by location" {...thing("Headcount")}>
          <ul className="bars">
            {byLoc.map((l) => (
              <li key={l.city}>
                <span className="bar-label">
                  {l.city}
                  <small>{l.state}</small>
                </span>
                <span className="bar-track">
                  <span className="bar-fill" style={{ width: `${(l.n / max) * 100}%` }} />
                </span>
                <span className="num bar-n">{l.n}</span>
              </li>
            ))}
          </ul>
          <p className="small muted">
            <UserRoundCheck size={14} aria-hidden /> {st.employees.length} active, {st.employees.filter((e) => e.tax_regime === "old").length} on the old regime
          </p>
        </Panel>

        <Panel title="Recent runs" actions={<Link to="/payroll" className="link small">All runs</Link>} className="recent">
          <TableWrap label="Recent payroll runs">
            <table className="dense">
              <thead>
                <tr>
                  <th scope="col">Month</th>
                  <th scope="col">Status</th>
                  <th scope="col" className="r">Employees</th>
                  <th scope="col" className="r">Net pay</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <Link to={`/payroll/${r.id}`}>{monthShort(r.month)}</Link>
                    </td>
                    <td>
                      <Status value={r.status} />
                    </td>
                    <td className="r num">{r.employees}</td>
                    <td className="r num">{rupees(r.net_pay)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        </Panel>
      </div>
    </div>
  );
}
