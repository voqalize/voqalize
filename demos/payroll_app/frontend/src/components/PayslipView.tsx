/**
 * One payslip, every line with a one-line plain explanation from the data,
 * optionally side by side with another month and the difference per line.
 * Used by the admin's Payslips and the employee's own view.
 */
import { Link } from "react-router-dom";
import { GitCompareArrows } from "lucide-react";
import { COMPANY, type Employee, SLIP_MONTHS, type Slip } from "../lib/data";
import { date, delta, monthLabel, monthShort, rupees, shortDate } from "../lib/format";
import { isMetro } from "../lib/engine";
import { tdsBefore } from "../lib/payroll";
import { type TkState, useTk } from "../state/store";
import { Money, thing } from "./ui";

type Key = keyof Slip;
interface Line {
  label: string;
  key?: Key;
  kind: "earn" | "ded" | "add" | "total" | "net" | "info";
  value: (s: Slip) => number;
  explain: (s: Slip) => string;
  hide?: (s: Slip, p: Slip | null) => boolean;
}

const prevMonth = (ym: string) => SLIP_MONTHS[SLIP_MONTHS.indexOf(ym) - 1] ?? null;

function lopReason(e: Employee, s: Slip, st: TkState): string {
  if (!s.lop_days) return "No loss of pay this month";
  const amount = rupees(e.structure.gross - s.gross);
  if (s.month === "2026-02" && e.joined.startsWith("2026-02")) return `Joined ${date(e.joined)}: ${s.lop_days} days before joining are unpaid (${amount})`;
  const reqs = st.leave.filter((r) => r.employee_id === e.id && r.status === "approved" && r.from.startsWith(s.month) && (r.type === "LOP" || (r.lop_days ?? 0) > 0));
  const which = reqs.map((r) => `${r.id}, ${shortDate(r.from)}${r.to !== r.from ? `–${shortDate(r.to)}` : ""}${r.type === "LOP" ? " leave without pay" : " beyond the balance"}`).join("; ");
  return `${s.lop_days} ${s.lop_days === 1 ? "day" : "days"} unpaid (${amount} less than a full month)${which ? `: ${which}` : ""}`;
}

function tdsReason(e: Employee, s: Slip, p: Slip | null, st: TkState): string {
  const slips = st.payslips[e.id] ?? [];
  const before = s.month === "2026-02" ? e.ytd_to_jan.tds : tdsBefore(e, slips, s.month);
  const left = 12 - s.month_idx;
  let line = `Year's tax ${rupees(s.annual_tax)} (${s.regime} regime) less ${rupees(before)} already deducted, over the ${left} months left`;
  if (p && p.annual_tax !== s.annual_tax) {
    const decl = st.declarations.find((d) => d.employee_id === e.id);
    const missing = decl?.items.filter((i) => i.verified < i.declared) ?? [];
    if (decl?.proofs_verified_on?.startsWith(s.month) && missing.length) {
      line += `. Proofs verified ${date(decl.proofs_verified_on)}: ${missing.map((i) => `${i.label} ${rupees(i.declared - i.verified)}`).join(", ")} declared without proof, so the year's tax rose from ${rupees(p.annual_tax)}`;
    } else {
      line += `. The year's tax moved from ${rupees(p.annual_tax)}`;
    }
  }
  return line;
}

function reimbReason(e: Employee, s: Slip, st: TkState): string {
  const claims = st.claims.filter((c) => c.employee_id === e.id && c.payroll_month === s.month && (c.status === "approved" || c.status === "paid"));
  if (!claims.length) return "No claims paid with this month";
  return claims.map((c) => `${c.id} ${c.category.toLowerCase()} ${rupees(c.amount)}`).join("; ") + "; not taxed";
}

function linesFor(e: Employee, st: TkState): Line[] {
  const metro = isMetro(e.location);
  return [
    { label: "Basic", key: "basic", kind: "earn", value: (s) => s.basic, explain: (s) => `40% of monthly CTC ${rupees(e.structure.monthly_ctc)}${s.lop_days ? `, for ${s.paid_days} of ${s.days} days` : ""}` },
    { label: "HRA", key: "hra", kind: "earn", value: (s) => s.hra, explain: () => `${metro ? 50 : 40}% of basic, ${e.location} is ${metro ? "a metro" : "not a metro"} for HRA` },
    { label: "LTA", key: "lta", kind: "earn", value: (s) => s.lta, explain: () => (e.lta_monthly ? `${rupees(e.lta_monthly)} a month at grade ${e.grade}` : `No LTA at grade ${e.grade}`) },
    { label: "Special allowance", key: "special", kind: "earn", value: (s) => s.special, explain: () => "The rest of monthly CTC after basic, HRA, LTA and employer PF" },
    { label: "Gross", key: "gross", kind: "total", value: (s) => s.gross, explain: (s) => `Earnings for ${s.paid_days} paid of ${s.days} days` },
    { label: "Loss of pay", kind: "info", value: (s) => s.lop_days ? -(e.structure.gross - s.gross) : 0, explain: (s) => lopReason(e, s, st) },
    { label: "Provident fund", key: "employee_pf", kind: "ded", value: (s) => s.employee_pf, explain: () => "12% of basic, on wages up to ₹15,000" },
    {
      label: "ESI",
      key: "employee_esi",
      kind: "ded",
      value: (s) => s.employee_esi,
      explain: () => "0.75% of gross while gross is up to ₹21,000",
      hide: (s, p) => !s.employee_esi && !p?.employee_esi,
    },
    {
      label: "Professional tax",
      key: "professional_tax",
      kind: "ded",
      value: (s) => s.professional_tax,
      explain: (s) =>
        s.professional_tax
          ? `${e.state} slab on gross${e.state === "Maharashtra" && s.month_idx === 10 ? "; ₹300 in February" : ""}`
          : `No professional tax on this gross in ${e.state}`,
    },
    { label: "TDS", key: "tds", kind: "ded", value: (s) => s.tds, explain: (s) => tdsReason(e, s, null, st) },
    { label: "Reimbursements", key: "reimbursements", kind: "add", value: (s) => s.reimbursements, explain: (s) => reimbReason(e, s, st) },
    { label: "Net pay", key: "net_pay", kind: "net", value: (s) => s.net_pay, explain: () => "Gross, less deductions, plus reimbursements" },
  ];
}

export function PayslipView({ employeeId, month, against, base }: { employeeId: string; month: string; against: string | null; base: string }) {
  const st = useTk();
  const e = st.employees.find((x) => x.id === employeeId);
  if (!e) return <p className="empty">There is no employee {employeeId}.</p>;
  const slips = st.payslips[e.id] ?? [];
  const s = slips.find((x) => x.month === month);
  const p = against ? (slips.find((x) => x.month === against) ?? null) : null;
  const months = SLIP_MONTHS.filter((m) => slips.some((x) => x.month === m));
  if (!s)
    return (
      <p className="empty">
        No payslip for {monthLabel(month)}. Payslips on file: {months.map(monthLabel).join(", ") || "none yet"}.
      </p>
    );
  const draft = month === "2026-02" && st.runs.find((r) => r.id === "PR-2026-02")?.status === "draft";
  const lines = linesFor(e, st).filter((l) => !l.hide?.(s, p));
  const prev = prevMonth(month);
  const net = p ? s.net_pay - p.net_pay : 0;
  const contributions = p
    ? [
        ["Loss of pay", -(p.gross - s.gross)],
        ["TDS", -(s.tds - p.tds)],
        ["Provident fund and PT", -(s.employee_pf + s.professional_tax + s.employee_esi - p.employee_pf - p.professional_tax - p.employee_esi)],
        ["Reimbursements", s.reimbursements - p.reimbursements],
      ].filter(([, v]) => v !== 0)
    : [];
  return (
    <div className="payslip-wrap">
      <div className="slip-controls">
        <div className="months" role="group" aria-label="Month">
          {months.map((m) => (
            <Link
              key={m}
              to={`${base}/${m}${p && prevMonth(m) && months.includes(prevMonth(m)!) ? `?against=${prevMonth(m)}` : ""}`}
              className={`chip${m === month ? " is-on" : ""}`}
            >
              {monthShort(m)}
              {m === "2026-02" ? <span className="chip-note">draft</span> : null}
            </Link>
          ))}
        </div>
        {prev && months.includes(prev) ? (
          p ? (
            <Link className="btn btn-ghost" to={`${base}/${month}`}>
              Show {monthShort(month)} alone
            </Link>
          ) : (
            <Link className="btn btn-ghost" to={`${base}/${month}?against=${prev}`}>
              <GitCompareArrows size={16} aria-hidden /> Compare with {monthShort(prev)}
            </Link>
          )
        ) : null}
      </div>

      <article className={`slip${p ? " is-compare" : ""}`} aria-label={`Payslip for ${monthLabel(month)}`} {...thing("Payslip")}>
        <header className="slip-head">
          <div>
            <p className="slip-co">{COMPANY.company.legal_name}</p>
            <h2 className="slip-title">
              Payslip for {monthLabel(month)}
              {draft ? <span className="pill pill-warn">Draft run</span> : null}
            </h2>
            <dl className="slip-meta">
              <div>
                <dt>Employee</dt>
                <dd>
                  {e.name}, {e.id}
                </dd>
              </div>
              <div>
                <dt>Designation</dt>
                <dd>
                  {e.title}, {e.grade}
                </dd>
              </div>
              <div>
                <dt>Location</dt>
                <dd>{e.location}</dd>
              </div>
              <div>
                <dt>Regime</dt>
                <dd>{s.regime === "new" ? "New" : "Old"}</dd>
              </div>
              <div>
                <dt>Paid days</dt>
                <dd className="num">
                  {s.paid_days} / {s.days}
                </dd>
              </div>
            </dl>
          </div>
          <div className="slip-net" {...thing("Net pay", "net-pay-hero")}>
            <span className="slip-net-label">Net pay</span>
            <span className="slip-net-value">{rupees(s.net_pay)}</span>
            {p ? <span className={`slip-net-delta ${net < 0 ? "neg" : "pos"}`}>{delta(net)} on {monthShort(p.month)}</span> : null}
          </div>
        </header>

        {p ? (
          <div className="difference" {...thing("Difference")}>
            <p className="difference-head">
              Net pay {net < 0 ? "fell" : "rose"} by <strong className="num">{rupees(Math.abs(net))}</strong>, from {rupees(p.net_pay)} in {monthShort(p.month)} to {rupees(s.net_pay)}.
            </p>
            <ul className="difference-parts">
              {contributions.map(([k, v]) => (
                <li key={k as string}>
                  <span>{k}</span>
                  <span className={`num ${(v as number) < 0 ? "neg" : "pos"}`}>{delta(v as number)}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="tablewrap">
          <table className={`slip-table${p ? " cols-3" : ""}`}>
            <thead>
              <tr>
                <th scope="col">Line</th>
                {p ? <th scope="col" className="r">{monthShort(p.month)}</th> : null}
                <th scope="col" className="r">{monthShort(s.month)}</th>
                {p ? <th scope="col" className="r">Change</th> : null}
              </tr>
            </thead>
            <tbody>
              {lines.map((l) => {
                const v = l.value(s);
                const pv = p ? l.value(p) : 0;
                const d = v - pv;
                const changed = !!p && d !== 0;
                const explain = l.key === "tds" ? tdsReason(e, s, p ?? (prev ? (slips.find((x) => x.month === prev) ?? null) : null), st) : l.explain(s);
                return (
                  <tr key={l.label} className={`row-${l.kind}${changed ? " is-changed" : ""}`} {...thing(l.label)}>
                    <th scope="row">
                      <span className="line-label">
                        {l.kind === "ded" ? <span className="sign">−</span> : l.kind === "add" ? <span className="sign">+</span> : null}
                        {l.label}
                        {l.label === "Loss of pay" && s.lop_days ? <span className="line-days">{s.lop_days} d</span> : null}
                      </span>
                      <span className="line-why">{explain}</span>
                    </th>
                    {p ? <td className="r num muted" data-col={monthShort(p.month)}>{l.kind === "info" && !pv ? "—" : rupees(pv)}</td> : null}
                    <td className="r num" data-col={monthShort(s.month)}>{l.kind === "info" && !v ? "—" : rupees(v)}</td>
                    {p ? <td className={`r num delta ${!d ? "" : (l.kind === "ded" ? d > 0 : d < 0) ? "neg" : "pos"}`} data-col="Change">{d ? delta(d) : "—"}</td> : null}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <footer className="slip-foot">
          <span>Employer PF {rupees(s.employer_pf)}{s.employer_esi ? `, employer ESI ${rupees(s.employer_esi)}` : ""}, not part of net pay.</span>
          <span>Tax figures illustrative, FY 2025-26.</span>
        </footer>
      </article>
    </div>
  );
}

export { Money };
