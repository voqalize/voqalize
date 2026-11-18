import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Check, FileText, Wrench, X } from "lucide-react";
import { COMPANY } from "../lib/data";
import { date, monthShort, rupees } from "../lib/format";
import { decideClaim, fixClaim, nameOf, useTk } from "../state/store";
import { Drawer, PageHead, Panel, Status, TableWrap, thing } from "../components/ui";

export function ReimbursementsPage() {
  const st = useTk();
  const [open, setOpen] = useState<string | null>(null);
  const review = st.claims.filter((c) => c.status === "pending" || c.status === "needs_fix");
  const rest = st.claims.filter((c) => !review.includes(c)).sort((a, b) => b.date.localeCompare(a.date));
  const claim = st.claims.find((c) => c.id === open) ?? null;
  const policy = (cat: string) => COMPANY.reimbursements.policy.find((p) => p.category === cat);
  return (
    <div className="page">
      <PageHead title="Reimbursements" sub="Approved claims are paid with that month's salary, untaxed. Every claim needs a bill." />
      <Panel title="Claims to review" {...thing("Claims to review")} actions={<span className="small muted">{review.length} open, for February</span>}>
        {review.length ? (
          <TableWrap label="Claims to review">
            <table className="grid claims">
              <thead>
                <tr>
                  <th scope="col">Claim</th>
                  <th scope="col">Employee</th>
                  <th scope="col">Category</th>
                  <th scope="col" className="r">Claimed</th>
                  <th scope="col" className="r">Bill amount</th>
                  <th scope="col">Status</th>
                  <th scope="col" className="r">Decide</th>
                </tr>
              </thead>
              <tbody>
                {review.map((c) => {
                  const mismatch = c.amount !== c.bill_amount;
                  const limit = policy(c.category)?.monthly_limit;
                  return (
                    <tr key={c.id} data-claim={c.id} className={mismatch ? "is-mismatch" : ""}>
                      <td>
                        <button type="button" className="linkbtn num" onClick={() => setOpen(c.id)}>
                          {c.id}
                        </button>
                        <small className="block muted">{date(c.date)}</small>
                      </td>
                      <td>
                        <Link to={`/employees/${c.employee_id}`}>{nameOf(c.employee_id, st)}</Link>
                        <small className="block muted">{c.description}</small>
                      </td>
                      <td>
                        {c.category}
                        {limit ? <small className="block muted">Limit {rupees(limit)} a month</small> : null}
                      </td>
                      <td className={`r num${mismatch ? " neg strong" : ""}`}>{rupees(c.amount)}</td>
                      <td className="r num" {...(mismatch ? thing("Bill amount", `bill-${c.id}`) : {})}>
                        {rupees(c.bill_amount)}
                        {mismatch ? (
                          <small className="block mismatch">
                            <AlertTriangle size={12} aria-hidden /> Off by {rupees(Math.abs(c.amount - c.bill_amount))}
                          </small>
                        ) : null}
                      </td>
                      <td>
                        <Status value={c.status} />
                        {c.note && !mismatch ? <small className="block muted">{c.note}</small> : null}
                      </td>
                      <td className="r">
                        <div className="row-actions">
                          {mismatch ? (
                            <button type="button" className="btn btn-primary btn-sm" data-fix={c.id} onClick={() => fixClaim(c.id)} {...thing("Fix amount", `fix-${c.id}`)}>
                              <Wrench size={14} aria-hidden /> Fix to {rupees(c.bill_amount)}
                            </button>
                          ) : (
                            <button type="button" className="btn btn-primary btn-sm" data-decide="approve" onClick={() => decideClaim(c.id, "approve")} {...thing("Approve", `approve-${c.id}`)}>
                              <Check size={14} aria-hidden /> Approve
                            </button>
                          )}
                          <button type="button" className="btn btn-ghost btn-sm" data-decide="reject" onClick={() => decideClaim(c.id, "reject")} {...thing("Reject", `reject-${c.id}`)}>
                            <X size={14} aria-hidden /> Reject
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </TableWrap>
        ) : (
          <p className="empty">Every claim is decided. Approved ones are in the February draft.</p>
        )}
      </Panel>
      <Panel title="All claims">
        <TableWrap label="All claims">
          <table className="grid">
            <thead>
              <tr>
                <th scope="col">Claim</th>
                <th scope="col">Employee</th>
                <th scope="col">Category</th>
                <th scope="col">Paid with</th>
                <th scope="col" className="r">Amount</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {rest.map((c) => (
                <tr key={c.id}>
                  <td>
                    <button type="button" className="linkbtn num" onClick={() => setOpen(c.id)}>
                      {c.id}
                    </button>
                  </td>
                  <td>{nameOf(c.employee_id, st)}</td>
                  <td>{c.category}</td>
                  <td>{monthShort(c.payroll_month)}</td>
                  <td className="r num">{rupees(c.amount)}</td>
                  <td>
                    <Status value={c.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      </Panel>
      <Panel title="Policy">
        <TableWrap label="Reimbursement policy">
          <table className="grid">
            <thead>
              <tr>
                <th scope="col">Category</th>
                <th scope="col" className="r">Monthly limit</th>
                <th scope="col">Who</th>
              </tr>
            </thead>
            <tbody>
              {COMPANY.reimbursements.policy.map((p) => (
                <tr key={p.category}>
                  <td>{p.category}</td>
                  <td className="r num">{p.monthly_limit ? rupees(p.monthly_limit) : "Actuals"}</td>
                  <td>{p.grades}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      </Panel>
      <Drawer open={!!claim} title={claim ? `${claim.id}, ${claim.category}` : ""} onClose={() => setOpen(null)}>
        {claim ? (
          <>
            <dl className="kv">
              <dt>Employee</dt>
              <dd>{nameOf(claim.employee_id, st)}</dd>
              <dt>Description</dt>
              <dd>{claim.description}</dd>
              <dt>Date</dt>
              <dd>{date(claim.date)}</dd>
              <dt>Claimed</dt>
              <dd className="num">{rupees(claim.amount)}</dd>
              <dt>Bill</dt>
              <dd className="num">{rupees(claim.bill_amount)}</dd>
              <dt>Paid with</dt>
              <dd>{monthShort(claim.payroll_month)} salary</dd>
              <dt>Status</dt>
              <dd>
                <Status value={claim.status} />
              </dd>
            </dl>
            {claim.note ? <p className="note">{claim.note}</p> : null}
            <div className="bill">
              <FileText size={28} aria-hidden />
              <span>
                {claim.bill_file}
                <small className="block muted">Bill total {rupees(claim.bill_amount)}</small>
              </span>
            </div>
          </>
        ) : null}
      </Drawer>
    </div>
  );
}
