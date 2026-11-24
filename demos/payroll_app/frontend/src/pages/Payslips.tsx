import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { SLIP_MONTHS } from "../lib/data";
import { monthLabel, monthShort, rupees } from "../lib/format";
import { useTk } from "../state/store";
import { PayslipView } from "../components/PayslipView";
import { Avatar, PageHead, TableWrap } from "../components/ui";

export function PayslipsIndex() {
  const st = useTk();
  const navigate = useNavigate();
  const [who, setWho] = useState("BB-1030");
  const [month, setMonth] = useState("2026-01");
  const [q, setQ] = useState("");
  const rows = st.employees.filter((e) => !q || `${e.name} ${e.id}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="page">
      <PageHead title="Payslips" sub="Every payslip explains each line. November 2025 to the February 2026 draft are on file." />
      <form
        className="panel picker"
        onSubmit={(e) => {
          e.preventDefault();
          navigate(`/payslips/${who}/${month}`);
        }}
      >
        <label className="field">
          <span>Employee</span>
          <select value={who} onChange={(e) => setWho(e.target.value)}>
            {st.employees.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}, {e.id}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Month</span>
          <select value={month} onChange={(e) => setMonth(e.target.value)}>
            {SLIP_MONTHS.map((m) => (
              <option key={m} value={m}>
                {monthLabel(m)}
                {m === "2026-02" ? " (draft)" : ""}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="btn btn-primary">
          Open payslip
        </button>
      </form>
      <div className="filters">
        <input type="search" placeholder="Find a person" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find a person" />
      </div>
      <TableWrap label="Payslips by month">
        <table className="grid">
          <thead>
            <tr>
              <th scope="col">Employee</th>
              {SLIP_MONTHS.map((m) => (
                <th key={m} scope="col" className="r">
                  {monthShort(m)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id}>
                <td>
                  <span className="person">
                    <Avatar name={e.name} size={24} />
                    <span>
                      <strong>{e.name}</strong>
                      <small>{e.id}</small>
                    </span>
                  </span>
                </td>
                {SLIP_MONTHS.map((m) => {
                  const s = st.payslips[e.id]?.find((x) => x.month === m);
                  return (
                    <td key={m} className="r num">
                      {s ? <Link to={`/payslips/${e.id}/${m}`}>{rupees(s.net_pay)}</Link> : <span className="muted">—</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
    </div>
  );
}

export function PayslipPage() {
  const { employeeId = "", month = "" } = useParams();
  const [params] = useSearchParams();
  const e = useTk((s) => s.employees.find((x) => x.id === employeeId));
  const against = params.get("against");
  return (
    <div className="page">
      <PageHead
        title={e ? `${e.name}, ${monthLabel(month)}` : "Payslip"}
        sub={
          <>
            <Link to="/payslips">Payslips</Link>
            {e ? (
              <>
                {" "}
                / <Link to={`/employees/${e.id}`}>{e.id}</Link>
              </>
            ) : null}
          </>
        }
      />
      <PayslipView employeeId={employeeId} month={month} against={against} base={`/payslips/${employeeId}`} />
    </div>
  );
}
