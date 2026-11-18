import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Check, X } from "lucide-react";
import { COMPANY } from "../lib/data";
import { date, shortDate } from "../lib/format";
import { approveLeave, impactLine, leaveImpact, nameOf, rejectLeave, useTk } from "../state/store";
import { Avatar, PageHead, Panel, Status, TableWrap, Tabs, thing } from "../components/ui";

const TYPE: Record<string, string> = { EL: "Earned", CL: "Casual", SL: "Sick", LOP: "Without pay" };

export function LeavePage() {
  const [params] = useSearchParams();
  const tab = params.get("tab") ?? "requests";
  const st = useTk();
  const pending = st.leave.filter((r) => r.status === "pending");
  const decided = st.leave.filter((r) => r.status !== "pending").sort((a, b) => b.applied_on.localeCompare(a.applied_on));
  return (
    <div className="page">
      <PageHead title="Leave" sub={`Calendar year 2026. ${pending.length} requests pending. ${COMPANY.leave.policy.approval}`} />
      <Tabs
        current={tab}
        tabs={[
          ["requests", `Requests${pending.length ? ` (${pending.length})` : ""}`],
          ["balances", "Balances"],
          ["holidays", "Holidays"],
          ["policy", "Policy"],
        ]}
      />
      {tab === "requests" ? (
        <>
          <Panel title="Pending requests" {...thing("Pending requests")} actions={<span className="small muted">Approved by the 25th counts in this month's payroll</span>}>
            {pending.length ? (
              <ul className="requests">
                {pending.map((r) => {
                  const impact = leaveImpact(r.id, st);
                  const e = st.employees.find((x) => x.id === r.employee_id)!;
                  return (
                    <li key={r.id} className={`request${impact?.lop && impact.inFebruary ? " has-lop" : ""}`} data-request={r.id}>
                      <div className="request-who">
                        <Avatar name={e.name} size={34} />
                        <div>
                          <Link to={`/employees/${e.id}`} className="strong">
                            {e.name}
                          </Link>
                          <span className="small muted">
                            {r.id}, {e.location}, applied {shortDate(r.applied_on)}
                          </span>
                        </div>
                      </div>
                      <div className="request-what">
                        <span className="strong">
                          {TYPE[r.type]} leave, {r.days} {r.days === 1 ? "day" : "days"}
                        </span>
                        <span className="small">
                          {date(r.from)}
                          {r.to !== r.from ? ` to ${date(r.to)}` : ""}
                        </span>
                        <span className="small muted">“{r.reason}”</span>
                      </div>
                      <div className="request-impact">
                        <span className="small muted">
                          Balance {r.type === "LOP" ? "n/a" : `${e.leave_balance[r.type as "EL"]} ${r.type}`}
                        </span>
                        <span className={`impact${impact?.lop && impact.inFebruary ? " neg" : ""}`}>{impactLine(r.id, st)}</span>
                      </div>
                      <div className="request-actions">
                        <button type="button" className="btn btn-ghost btn-sm" data-decide="reject" onClick={() => rejectLeave(r.id)} {...thing("Reject", `reject-${r.id}`)}>
                          <X size={15} aria-hidden /> Reject
                        </button>
                        <button type="button" className="btn btn-primary btn-sm" data-decide="approve" onClick={() => approveLeave(r.id)} {...thing("Approve", `approve-${r.id}`)}>
                          <Check size={15} aria-hidden /> Approve
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="empty">No requests waiting. New ones arrive here as managers forward them.</p>
            )}
          </Panel>
          <Panel title="Decided">
            <TableWrap label="Decided leave">
              <table className="grid">
                <thead>
                  <tr>
                    <th scope="col">Request</th>
                    <th scope="col">Employee</th>
                    <th scope="col">Type</th>
                    <th scope="col">Dates</th>
                    <th scope="col" className="r">Days</th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {decided.map((r) => (
                    <tr key={r.id}>
                      <td className="num">{r.id}</td>
                      <td>{nameOf(r.employee_id, st)}</td>
                      <td>{TYPE[r.type]}</td>
                      <td className="nowrap">
                        {shortDate(r.from)}
                        {r.to !== r.from ? ` – ${shortDate(r.to)}` : ""}
                      </td>
                      <td className="r num">
                        {r.days}
                        {r.lop_days ? <small className="neg"> ({r.lop_days} LOP)</small> : null}
                      </td>
                      <td>
                        <Status value={r.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          </Panel>
        </>
      ) : null}
      {tab === "balances" ? <Balances /> : null}
      {tab === "holidays" ? <Holidays /> : null}
      {tab === "policy" ? <Policy /> : null}
    </div>
  );
}

function Balances() {
  const employees = useTk((s) => s.employees);
  const [q, setQ] = useState("");
  const rows = employees.filter((e) => !q || e.name.toLowerCase().includes(q.toLowerCase()));
  return (
    <Panel title="Balances" {...thing("Balances")} actions={<input type="search" className="mini-search" placeholder="Find a person" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find a person" />}>
      <TableWrap label="Leave balances">
        <table className="grid">
          <thead>
            <tr>
              <th scope="col">Employee</th>
              <th scope="col">Location</th>
              <th scope="col" className="r">Earned</th>
              <th scope="col" className="r">Casual</th>
              <th scope="col" className="r">Sick</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id}>
                <td>
                  <Link to={`/employees/${e.id}`}>{e.name}</Link>
                </td>
                <td>{e.location}</td>
                {(["EL", "CL", "SL"] as const).map((t) => (
                  <td key={t} className={`r num${e.leave_balance[t] === 0 ? " neg" : ""}`}>
                    {e.leave_balance[t]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
    </Panel>
  );
}

function Holidays() {
  return (
    <Panel title="Holidays, 2026">
      <TableWrap label="Holidays">
        <table className="grid">
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Holiday</th>
              <th scope="col">Where</th>
            </tr>
          </thead>
          <tbody>
            {COMPANY.leave.holidays.map((h) => (
              <tr key={h.date} className={h.date < COMPANY.today ? "is-past" : ""}>
                <td className="nowrap">{date(h.date)}</td>
                <td>{h.name}</td>
                <td>{h.locations.includes("all") ? "Every office" : h.locations.join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
    </Panel>
  );
}

function Policy() {
  const p = COMPANY.leave.policy;
  return (
    <div className="detail-grid">
      <Panel title="Leave types" className="span-2">
        <TableWrap label="Leave types">
          <table className="grid">
            <thead>
              <tr>
                <th scope="col">Type</th>
                <th scope="col" className="r">A year</th>
                <th scope="col">Accrual</th>
                <th scope="col" className="r">Carry forward</th>
                <th scope="col">Encashable</th>
              </tr>
            </thead>
            <tbody>
              {p.types.map((t) => (
                <tr key={t.id}>
                  <td>{t.name}</td>
                  <td className="r num">{t.per_year ?? "—"}</td>
                  <td>{t.accrual}</td>
                  <td className="r num">{t.carry_forward_max}</td>
                  <td>{t.encashable ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      </Panel>
      <Panel title="Rules">
        <dl className="kv kv-wide">
          <dt>Approval</dt>
          <dd>{p.approval}</dd>
          <dt>Loss of pay</dt>
          <dd>{p.lop_rule}</dd>
          <dt>Cut-off</dt>
          <dd>{p.attendance_cutoff}</dd>
          <dt>Sandwich rule</dt>
          <dd>{p.sandwich_rule ? "Weekends between leave days count" : "Weekends between leave days do not count"}</dd>
        </dl>
      </Panel>
    </div>
  );
}
