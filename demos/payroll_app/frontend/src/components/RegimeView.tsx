/**
 * Both regimes for one employee, computed live by the engine with verified
 * declarations: every step side by side, slab by slab, and the switch with
 * its policy and what it does to TDS for the months left.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeftRight } from "lucide-react";
import { COMPANY, PRODUCT } from "../lib/data";
import type { Regime, TaxBreakdown } from "../lib/engine";
import { date, num, rupees } from "../lib/format";
import { comparisonOf, declOf, febSlip, reimbursementsFor } from "../lib/payroll";
import { febSlipOf, locked, notify, switchRegime, useTk } from "../state/store";
import { Dialog, thing } from "./ui";

type Row = [label: string, get: (t: TaxBreakdown) => number, opts?: { sign?: "−" | "+"; strong?: boolean; group?: "ded" }];

const ROWS: Row[] = [
  ["Gross salary for the year", (t) => t.gross_salary, { strong: true }],
  ["HRA exemption", (t) => t.exempt_hra, { sign: "−" }],
  ["LTA exemption", (t) => t.exempt_lta, { sign: "−" }],
  ["Standard deduction", (t) => t.standard_deduction, { sign: "−" }],
  ["Professional tax", (t) => t.professional_tax, { sign: "−" }],
  ["Income from salary", (t) => t.income_from_salary, { strong: true }],
  ["Home loan interest, 24(b)", (t) => -t.house_property, { sign: "−" }],
  ["Gross total income", (t) => t.gross_total_income, { strong: true }],
  ["80C: PF and investments", (t) => t.ded_80c, { sign: "−", group: "ded" }],
  ["80CCD(1B): own NPS", (t) => t.ded_80ccd1b, { sign: "−", group: "ded" }],
  ["80D: health insurance", (t) => t.ded_80d, { sign: "−", group: "ded" }],
];
const AFTER: Row[] = [
  ["Taxable income", (t) => t.taxable_income, { strong: true }],
  ["Tax on income, by slab", (t) => t.tax_on_income],
  ["Rebate, section 87A", (t) => t.rebate_87a, { sign: "−" }],
  ["Marginal relief", (t) => t.marginal_relief, { sign: "−" }],
  ["Tax after rebate", (t) => t.tax_after_rebate],
  ["Health and education cess, 4%", (t) => t.cess, { sign: "+" }],
];

const label = (r: Regime) => (r === "new" ? "New regime" : "Old regime");

function Amount({ v, sign }: { v: number; sign?: string }) {
  if (!v) return <span className="num muted">—</span>;
  return (
    <span className="num">
      {sign ? `${sign} ` : ""}
      {rupees(v)}
    </span>
  );
}

function SlabTable({ t, title }: { t: TaxBreakdown; title: string }) {
  return (
    <section className="slabs" {...thing(title)}>
      <h3>{title}</h3>
      <div className="tablewrap">
        <table className="dense">
          <thead>
            <tr>
              <th scope="col">Income band</th>
              <th scope="col" className="r">Rate</th>
              <th scope="col" className="r">Taxable here</th>
              <th scope="col" className="r">Tax</th>
            </tr>
          </thead>
          <tbody>
            {t.slabs.map((s) => (
              <tr key={s.lo} className={s.taxable ? "" : "is-idle"}>
                <td className="num">{s.hi === null ? `Above ₹${num(s.lo)}` : `₹${num(s.lo)} to ₹${num(s.hi)}`}</td>
                <td className="r num">{s.rate}%</td>
                <td className="r num">{s.taxable ? rupees(s.taxable) : "—"}</td>
                <td className="r num">{s.tax ? rupees(s.tax) : "—"}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" colSpan={3}>
                Tax on {rupees(t.taxable_income)}
              </th>
              <td className="r num">{rupees(t.tax_on_income)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  );
}

export function RegimeView({ employeeId, mode = "admin" }: { employeeId: string; mode?: "admin" | "self" }) {
  const st = useTk();
  const navigate = useNavigate();
  const [confirm, setConfirm] = useState(false);
  const e = st.employees.find((x) => x.id === employeeId);
  if (!e) return <p className="empty">There is no employee {employeeId}.</p>;
  const cmp = comparisonOf(e, st.declarations);
  const current = e.tax_regime;
  const other: Regime = current === "new" ? "old" : "new";
  const feb = febSlipOf(e.id, st);
  const ifSwitched = febSlip({ ...e, tax_regime: other }, st.febLop[e.id] ?? 0, declOf(e.id, st.declarations), reimbursementsFor(e.id, st.claims));
  const decl = st.declarations.find((d) => d.employee_id === e.id);
  const isLocked = locked(st);
  const verdict =
    cmp.saving === 0 ? "Both regimes come to the same tax this year." : `${label(cmp.better)} saves ${rupees(cmp.saving)} this year.`;

  return (
    <div className="regime">
      <div className="regime-top">
        {mode === "admin" ? (
          <label className="field field-inline" {...thing("Employee picker")}>
            <span>Employee</span>
            <select value={e.id} onChange={(ev) => navigate(`/tax/regime/${ev.target.value}`)}>
              {st.employees.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.name}, {x.id}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <p className="regime-basis">
          Projected for FY 2025-26: pay to January, then February and March at the current structure
          {decl ? `, with declarations as verified on ${date(decl.proofs_verified_on)}` : ", with no declarations on file"}. Illustrative, FY 2025-26.
        </p>
      </div>

      <div className="verdict">
        <p className="verdict-line">{verdict}</p>
        <p className="verdict-sub">
          TDS is worked out on the <strong>{label(current).toLowerCase()}</strong>
          {e.regime_chosen_on ? `, chosen on ${date(e.regime_chosen_on)}` : ", the default"}.
        </p>
      </div>

      <div className="regime-cards">
        {(["new", "old"] as Regime[]).map((r) => {
          const t = cmp[r];
          return (
            <div key={r} className={`regime-card${cmp.better === r && cmp.saving ? " is-better" : ""}${current === r ? " is-current" : ""}`} {...thing(label(r))}>
              <div className="regime-card-head">
                <h3>{label(r)}</h3>
                {current === r ? <span className="pill pill-info">TDS on this</span> : null}
                {cmp.better === r && cmp.saving ? <span className="pill pill-ok">Lower by {rupees(cmp.saving)}</span> : null}
              </div>
              <span className="regime-total">{rupees(t.total_tax)}</span>
              <span className="regime-note">
                tax for the year on taxable income of {rupees(t.taxable_income)}
              </span>
            </div>
          );
        })}
      </div>

      <section className="panel compute">
        <div className="panel-head">
          <h2>Step by step</h2>
          <span className="muted small">{PRODUCT.tax.fy_label}</span>
        </div>
        <div className="tablewrap">
          <table className="compute-table">
            <thead>
              <tr>
                <th scope="col">Step</th>
                <th scope="col" className="r">New regime</th>
                <th scope="col" className="r">Old regime</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.filter(([, , o]) => o?.group !== "ded").map(([l, get, o]) => (
                <tr key={l} className={o?.strong ? "is-strong" : ""}>
                  <th scope="row">{l}</th>
                  <td className="r">
                    <Amount v={get(cmp.new)} sign={o?.sign} />
                  </td>
                  <td className="r">
                    <Amount v={get(cmp.old)} sign={o?.sign} />
                  </td>
                </tr>
              ))}
            </tbody>
            <tbody className="deductions" {...thing("Deductions")}>
              <tr className="group-head">
                <th scope="row" colSpan={3}>
                  Deductions, chapter VI-A {cmp.new.total_deductions === 0 ? "(the new regime allows none of these)" : ""}
                </th>
              </tr>
              {ROWS.filter(([, , o]) => o?.group === "ded").map(([l, get, o]) => (
                <tr key={l}>
                  <th scope="row">{l}</th>
                  <td className="r">
                    <Amount v={get(cmp.new)} sign={o?.sign} />
                  </td>
                  <td className="r">
                    <Amount v={get(cmp.old)} sign={o?.sign} />
                  </td>
                </tr>
              ))}
            </tbody>
            <tbody>
              {AFTER.map(([l, get, o]) => (
                <tr key={l} className={o?.strong ? "is-strong" : ""}>
                  <th scope="row">{l}</th>
                  <td className="r">
                    <Amount v={get(cmp.new)} sign={o?.sign} />
                  </td>
                  <td className="r">
                    <Amount v={get(cmp.old)} sign={o?.sign} />
                  </td>
                </tr>
              ))}
              <tr className="is-total">
                <th scope="row">Total tax for the year</th>
                <td className={`r num${cmp.better === "new" && cmp.saving ? " better" : ""}`}>{rupees(cmp.new.total_tax)}</td>
                <td className={`r num${cmp.better === "old" && cmp.saving ? " better" : ""}`}>{rupees(cmp.old.total_tax)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <div className="slab-pair">
        <SlabTable t={cmp.new} title="New regime slabs" />
        <SlabTable t={cmp.old} title="Old regime slabs" />
      </div>

      <section className="panel switch" {...thing("Switch regime")}>
        <div className="panel-head">
          <h2>{mode === "admin" ? "Switch regime" : "Change my regime"}</h2>
        </div>
        <p className="policy">{COMPANY.company.regime_change_policy}</p>
        <div className="switch-row">
          <div className="tds-left" {...thing("TDS for months left")}>
            <span className="small muted">TDS for months left, February and March</span>
            <div className="tds-compare">
              <div>
                <span className="small">On the {current} regime</span>
                <span className="num big">{rupees(feb?.tds ?? 0)}</span>
                <span className="small muted">a month</span>
              </div>
              <ArrowLeftRight size={18} aria-hidden className="muted" />
              <div>
                <span className="small">On the {other} regime</span>
                <span className="num big">{rupees(ifSwitched.tds)}</span>
                <span className="small muted">a month</span>
              </div>
            </div>
            <span className="small muted">
              ({rupees(cmp[other].total_tax)} for the year less {rupees(e.ytd_to_jan.tds)} deducted to January) ÷ 2
            </span>
          </div>
          {mode === "admin" ? (
            <button type="button" className="btn btn-primary" data-switch-regime={other} disabled={isLocked} onClick={() => setConfirm(true)}>
              Switch to {other} regime
            </button>
          ) : (
            <button type="button" className="btn btn-primary" onClick={() => notify(`Request to move to the ${other} regime sent to HR`)}>
              Ask HR to switch me to {other}
            </button>
          )}
        </div>
        {isLocked ? <p className="small warn-text">The February run is approved and locked; a switch now applies from March.</p> : null}
      </section>

      <Dialog open={confirm} title={`Move ${e.name} to the ${other} regime?`} onClose={() => setConfirm(false)}>
        <p>
          February TDS goes from {rupees(feb?.tds ?? 0)} to {rupees(ifSwitched.tds)}, and March follows. The employee makes the final choice in their income-tax return.
        </p>
        <div className="dialog-actions">
          <button type="button" className="btn btn-ghost" onClick={() => setConfirm(false)}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              switchRegime(e.id, other);
              setConfirm(false);
            }}
          >
            Switch to {other}
          </button>
        </div>
      </Dialog>
    </div>
  );
}
