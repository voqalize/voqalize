/** Employee self-service, as the employee sees it: a simpler shell of its own. */
import { Link, NavLink, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Eye, Upload } from "lucide-react";
import { COMPANY, PRODUCT, TODAY } from "../lib/data";
import { date, rupees, shortDate } from "../lib/format";
import { uploadProof, useTk } from "../state/store";
import { PayslipView } from "../components/PayslipView";
import { RegimeView } from "../components/RegimeView";
import { Logo } from "../components/Shell";
import { Avatar, Status, TableWrap, thing } from "../components/ui";

const TABS: [string, string][] = [
  ["payslips", "My payslips"],
  ["tax", "My tax and regime"],
  ["declarations", "My declarations"],
  ["leave", "My leave"],
];

export function MePage() {
  const { employeeId = "", tab = "payslips", month } = useParams();
  const [params] = useSearchParams();
  const st = useTk();
  const e = st.employees.find((x) => x.id === employeeId);
  return (
    <div className="me-shell">
      <div className="viewas-banner" {...thing("Employee view")}>
        <Eye size={16} aria-hidden />
        <span>
          Viewing as <strong>{e?.name ?? employeeId}</strong>. This is what they see in Paynora.
        </span>
        <Link to={e ? `/employees/${e.id}` : "/employees"} className="btn btn-sm btn-onbanner">
          <ArrowLeft size={14} aria-hidden /> Back to admin
        </Link>
      </div>
      <header className="me-top">
        <div className="me-brand">
          <Logo />
          <span>
            <strong>{COMPANY.company.name}</strong>
            <small>on {PRODUCT.brand.name}</small>
          </span>
        </div>
        {e ? (
          <div className="me-who">
            <Avatar name={e.name} size={36} />
            <span>
              <strong>{e.name}</strong>
              <small>
                {e.title}, {e.location}
              </small>
            </span>
          </div>
        ) : null}
      </header>
      <nav className="me-tabs" aria-label="My Paynora">
        {TABS.map(([id, label]) => (
          <NavLink key={id} to={`/me/${employeeId}/${id}`} className={() => `me-tab${tab === id ? " is-on" : ""}`}>
            {label}
          </NavLink>
        ))}
      </nav>
      <main id="main" className="me-main" tabIndex={-1}>
        <h1 className="sr-only" data-stage-heading>
          {TABS.find(([id]) => id === tab)?.[1] ?? "My Paynora"}
        </h1>
        {!e ? <p className="empty">There is no employee {employeeId}.</p> : null}
        {e && tab === "payslips" ? <PayslipView employeeId={e.id} month={month ?? "2026-01"} against={params.get("against")} base={`/me/${e.id}/payslips`} /> : null}
        {e && tab === "tax" ? <RegimeView employeeId={e.id} mode="self" /> : null}
        {e && tab === "declarations" ? <MyDeclarations id={e.id} /> : null}
        {e && tab === "leave" ? <MyLeave id={e.id} /> : null}
      </main>
    </div>
  );
}

function MyDeclarations({ id }: { id: string }) {
  const d = useTk((s) => s.declarations.find((x) => x.employee_id === id));
  const W = COMPANY.company.windows.proofs;
  const open = TODAY <= W.closes;
  if (!d)
    return (
      <section className="panel">
        <h2>My declarations</h2>
        <p className="muted">You declared no investments for FY 2025-26, so your TDS counts none. The declaration window closed on {date(COMPANY.company.windows.declaration.closes)}.</p>
      </section>
    );
  return (
    <section className="panel" {...thing("Declarations")}>
      <div className="panel-head">
        <h2>My declarations, FY 2025-26</h2>
        <span className="small muted">Proofs accepted until {date(W.closes)}</span>
      </div>
      <TableWrap label="My declarations">
        <table className="grid">
          <thead>
            <tr>
              <th scope="col">Item</th>
              <th scope="col" className="r">Declared</th>
              <th scope="col" className="r">Verified</th>
              <th scope="col">Proof</th>
              <th scope="col" />
            </tr>
          </thead>
          <tbody>
            {d.items.map((i, n) => (
              <tr key={i.label}>
                <td>
                  {i.label}
                  <small className="block muted">Section {i.section.replace("_", " ")}</small>
                </td>
                <td className="r num">{rupees(i.declared)}</td>
                <td className="r num">{rupees(i.verified)}</td>
                <td {...thing("Proof status", `proof-${n}`)}>
                  <Status value={i.proof_status} />
                </td>
                <td className="r">
                  {i.proof_status === "not_submitted" && open ? (
                    <button type="button" className="btn btn-sm btn-primary" onClick={() => uploadProof(id, n)}>
                      <Upload size={14} aria-hidden /> Upload proof
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
      <p className="small muted">An item without a verified proof does not reduce your TDS. Once HR verifies a new proof, the months left are recalculated.</p>
    </section>
  );
}

function MyLeave({ id }: { id: string }) {
  const st = useTk();
  const e = st.employees.find((x) => x.id === id)!;
  const mine = st.leave.filter((r) => r.employee_id === id).sort((a, b) => b.from.localeCompare(a.from));
  const holidays = COMPANY.leave.holidays.filter((h) => h.date >= TODAY && (h.locations.includes("all") || h.locations.includes(e.location))).slice(0, 4);
  return (
    <div className="me-grid">
      <section className="panel" {...thing("Balances")}>
        <h2>My balances</h2>
        <div className="balances">
          {(
            [
              ["EL", "Earned"],
              ["CL", "Casual"],
              ["SL", "Sick"],
            ] as const
          ).map(([k, l]) => (
            <div key={k} className="balance">
              <span className="balance-n">{e.leave_balance[k]}</span>
              <span className="small">{l} leave</span>
            </div>
          ))}
        </div>
        <p className="small muted">With no balance left, leave is without pay and reduces that month's salary.</p>
      </section>
      <section className="panel">
        <h2>My requests</h2>
        {mine.length ? (
          <ul className="linklist">
            {mine.map((r) => (
              <li key={r.id}>
                <span>
                  {r.type} leave, {shortDate(r.from)}
                  {r.to !== r.from ? `–${shortDate(r.to)}` : ""}
                  <small className="block muted">{r.reason}</small>
                </span>
                <Status value={r.status} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No leave this year.</p>
        )}
      </section>
      <section className="panel">
        <h2>Coming holidays, {e.location}</h2>
        <ul className="linklist">
          {holidays.map((h) => (
            <li key={h.date}>
              <span>{h.name}</span>
              <span className="small">{date(h.date)}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
