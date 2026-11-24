import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CheckCircle2, CircleAlert, Lock } from "lucide-react";
import { COMPANY, DRAFT_RUN_ID } from "../lib/data";
import { date, monthShort, rupees } from "../lib/format";
import { approveRun, claimsToReview, pendingLeave, useTk } from "../state/store";
import { Dialog, PageHead, Panel, Status, TableWrap, thing } from "../components/ui";

export function PayrollRuns() {
  const runs = useTk((s) => s.runs);
  return (
    <div className="page">
      <PageHead title="Payroll runs" sub="FY 2025-26, April 2025 to February 2026. Each run is reviewed by HR and approved by finance." />
      <TableWrap label="Payroll runs">
        <table className="grid">
          <thead>
            <tr>
              <th scope="col">Run</th>
              <th scope="col">Status</th>
              <th scope="col">Pay date</th>
              <th scope="col" className="r">Employees</th>
              <th scope="col" className="r">Gross</th>
              <th scope="col" className="r">TDS</th>
              <th scope="col" className="r">Net pay</th>
              <th scope="col" className="r">Employer cost</th>
              <th scope="col">Approved by</th>
            </tr>
          </thead>
          <tbody>
            {[...runs].reverse().map((r) => (
              <tr key={r.id} className={r.status === "draft" ? "is-draft" : ""}>
                <td>
                  <Link to={`/payroll/${r.id}`}>
                    <strong>{r.label}</strong>
                  </Link>
                  <small className="block muted">{r.id}</small>
                </td>
                <td>
                  <Status value={r.status} />
                </td>
                <td className="nowrap">{date(r.pay_date)}</td>
                <td className="r num">{r.employees}</td>
                <td className="r num">{rupees(r.gross)}</td>
                <td className="r num">{rupees(r.tds)}</td>
                <td className="r num">{rupees(r.net_pay)}</td>
                <td className="r num">{rupees(r.employer_cost)}</td>
                <td>{r.approved_by ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
    </div>
  );
}

export function PayrollRun() {
  const { runId = "" } = useParams();
  const st = useTk();
  const [confirm, setConfirm] = useState(false);
  const [q, setQ] = useState("");
  const run = st.runs.find((r) => r.id === runId);
  if (!run)
    return (
      <div className="page">
        <PageHead title="No such run" sub={`There is no payroll run ${runId}.`} />
        <Link to="/payroll">All runs</Link>
      </div>
    );
  const isDraft = run.id === DRAFT_RUN_ID;
  const lines = st.employees
    .map((e) => ({ e, s: st.payslips[e.id]?.find((x) => x.month === run.month) }))
    .filter((x) => x.s)
    .filter((x) => !q || `${x.e.name} ${x.e.id}`.toLowerCase().includes(q.toLowerCase()));
  const leave = pendingLeave(st).filter((r) => r.from.startsWith("2026-02"));
  const claims = claimsToReview(st).filter((c) => c.payroll_month === "2026-02");
  const proofs = st.declarations.flatMap((d) => d.items.filter((i) => i.proof_status === "not_submitted").map((i) => ({ d, i })));
  const checks: [boolean, React.ReactNode][] = [
    [!leave.length, <>{leave.length ? <Link to="/leave?tab=requests">{leave.length} February leave requests pending</Link> : "No February leave pending"}</>],
    [!claims.length, <>{claims.length ? <Link to="/reimbursements">{claims.length} February claims to review</Link> : "Every February claim decided"}</>],
    [
      !proofs.length,
      <>
        {proofs.length ? <Link to="/tax?tab=declarations">{proofs.length} declared items without proof</Link> : "Every declared item has a proof"}
        <span className="small muted"> TDS uses verified amounts only</span>
      </>,
    ],
    [true, <>New joiners and LOP from approved leave included</>],
  ];
  return (
    <div className="page">
      <PageHead
        title={`${run.label} payroll`}
        sub={
          <>
            {run.id}, {run.days} days, pay date {date(run.pay_date)}. <Status value={run.status} />
          </>
        }
      />
      <div className="run-top">
        <Panel title="Run totals" className="totals" {...thing("Run totals")}>
          <dl className="totals-grid">
            {(
              [
                ["Employees", String(run.employees)],
                ["Gross", rupees(run.gross)],
                ["Employee PF", rupees(run.employee_pf)],
                ["Employer PF", rupees(run.employer_pf)],
                ["ESI, both shares", rupees(run.employee_esi + run.employer_esi)],
                ["Professional tax", rupees(run.professional_tax)],
                ["TDS", rupees(run.tds)],
                ["Reimbursements", rupees(run.reimbursements)],
                ["LOP days", String(run.lop_days)],
                ["Employer cost", rupees(run.employer_cost)],
              ] as const
            ).map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd className="num">{v}</dd>
              </div>
            ))}
            <div className="totals-net">
              <dt>Net pay</dt>
              <dd className="num">{rupees(run.net_pay)}</dd>
            </div>
          </dl>
        </Panel>
        {isDraft ? (
          <Panel title="Review checklist" className="checklist" {...thing("Review checklist")}>
            <ul>
              {checks.map(([done, text], i) => (
                <li key={i} className={done ? "is-done" : ""}>
                  {done ? <CheckCircle2 size={18} aria-hidden /> : <CircleAlert size={18} aria-hidden />}
                  <span>{text}</span>
                </li>
              ))}
            </ul>
            {run.status === "draft" ? (
              <button type="button" className="btn btn-primary btn-block" onClick={() => setConfirm(true)} data-dock-avoid {...thing("Approve run")}>
                Approve run
              </button>
            ) : (
              <p className="locked">
                <Lock size={16} aria-hidden /> Approved by {run.approved_by}. The run is locked.
              </p>
            )}
            <p className="small muted">Approving locks the run and releases the bank file for {date(run.pay_date)}. Only an admin can approve.</p>
          </Panel>
        ) : null}
      </div>

      <Panel
        title="Payroll register"
        {...thing("Payroll register")}
        actions={lines.length ? <input type="search" className="mini-search" placeholder="Find a person" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find in register" /> : null}
      >
        {st.employees.some((e) => st.payslips[e.id]?.some((x) => x.month === run.month)) ? (
          <TableWrap label="Payroll register">
            <table className="grid register">
              <thead>
                <tr>
                  <th scope="col">Employee</th>
                  <th scope="col" className="r">Paid days</th>
                  <th scope="col" className="r">Gross</th>
                  <th scope="col" className="r">PF</th>
                  <th scope="col" className="r">ESI</th>
                  <th scope="col" className="r">PT</th>
                  <th scope="col" className="r">TDS</th>
                  <th scope="col" className="r">Reimb.</th>
                  <th scope="col" className="r">Net pay</th>
                </tr>
              </thead>
              <tbody>
                {lines.map(({ e, s }) => (
                  <tr key={e.id} className={s!.lop_days ? "has-lop" : ""}>
                    <td>
                      <Link to={`/payslips/${e.id}/${run.month}`}>{e.name}</Link>
                      <small className="block muted">
                        {e.id}, {e.location}
                      </small>
                    </td>
                    <td className="r num">
                      {s!.paid_days}/{s!.days}
                    </td>
                    <td className="r num">{rupees(s!.gross)}</td>
                    <td className="r num">{rupees(s!.employee_pf)}</td>
                    <td className="r num">{s!.employee_esi ? rupees(s!.employee_esi) : "—"}</td>
                    <td className="r num">{rupees(s!.professional_tax)}</td>
                    <td className="r num">{rupees(s!.tds)}</td>
                    <td className="r num">{s!.reimbursements ? rupees(s!.reimbursements) : "—"}</td>
                    <td className="r num strong">{rupees(s!.net_pay)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        ) : (
          <p className="muted">
            Per-employee lines for {monthShort(run.month)} are archived. The register on file starts in November 2025; the totals above are the run as paid.
          </p>
        )}
      </Panel>

      <Dialog open={confirm} title={`Approve ${run.label} payroll?`} onClose={() => setConfirm(false)}>
        <p>
          {rupees(run.net_pay)} to {run.employees} employees on {date(run.pay_date)}. The run locks: later leave, claims or regime changes move to March.
        </p>
        {!checks.every(([d]) => d) ? <p className="warn-text small">Some review items are still open.</p> : null}
        <p className="small muted">
          Approving as {COMPANY.company.admin.name}. Finance ({COMPANY.company.payroll_approver.name}) is told.
        </p>
        <div className="dialog-actions">
          <button type="button" className="btn btn-ghost" onClick={() => setConfirm(false)}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              approveRun(run.id);
              setConfirm(false);
            }}
          >
            Approve and lock
          </button>
        </div>
      </Dialog>
    </div>
  );
}
