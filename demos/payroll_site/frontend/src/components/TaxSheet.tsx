/**
 * The hero's working sheet: the sample employee from tax_example.json, her
 * year's tax under both regimes after proofs, as Tankora's payroll shows it.
 * Every number is read from the file, nothing recomputed.
 */
import { TAX_EXAMPLE } from "../data/product";
import { inr, lakh } from "../lib/format";

type Regime = typeof TAX_EXAMPLE.after_proofs.new;

const ROWS: { label: string; get: (r: Regime) => number; minus?: boolean }[] = [
  { label: "Gross salary", get: (r) => r.gross_salary },
  { label: "HRA exemption", get: (r) => r.exempt_hra, minus: true },
  { label: "Standard deduction", get: (r) => r.standard_deduction, minus: true },
  { label: "Professional tax", get: (r) => r.professional_tax, minus: true },
  { label: "80C, 80D, 80CCD(1B)", get: (r) => r.total_deductions, minus: true },
  { label: "Taxable income", get: (r) => r.taxable_income },
];

export function TaxSheet() {
  const { profile, after_proofs: ap } = TAX_EXAMPLE;
  const newer = ap.new;
  const older = ap.old;
  const better = newer.total_tax <= older.total_tax ? "new" : "old";
  const gap = Math.abs(newer.total_tax - older.total_tax);
  return (
    <figure className="sheet" aria-label="Sample tax working for one employee">
      <div className="sheet-head">
        <div>
          <p className="sheet-kind">Tax working, {TAX_EXAMPLE.fy_label.split(" (")[0]}</p>
          <p className="sheet-who">
            {profile.role}, {profile.city}
          </p>
        </div>
        <span className="sheet-ctc num">{lakh(profile.annual_ctc)} CTC</span>
      </div>
      <table className="sheet-table">
        <thead>
          <tr>
            <th scope="col">
              <span className="sr-only">Line</span>
            </th>
            <th scope="col" className={`num${better === "old" ? " is-best" : ""}`}>
              Old regime
            </th>
            <th scope="col" className={`num${better === "new" ? " is-best" : ""}`}>
              New regime
            </th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => (
            <tr key={r.label} className={r.label === "Taxable income" ? "is-sum" : undefined}>
              <th scope="row">{r.label}</th>
              <td className="num">{r.get(older) ? `${r.minus ? "− " : ""}${inr(r.get(older))}` : "—"}</td>
              <td className="num">{r.get(newer) ? `${r.minus ? "− " : ""}${inr(r.get(newer))}` : "—"}</td>
            </tr>
          ))}
          <tr className="is-total">
            <th scope="row">Tax with cess</th>
            <td className={`num${better === "old" ? " is-best" : ""}`}>{inr(older.total_tax)}</td>
            <td className={`num${better === "new" ? " is-best" : ""}`}>{inr(newer.total_tax)}</td>
          </tr>
          <tr>
            <th scope="row">TDS a month</th>
            <td className="num">{inr(Math.round(older.total_tax / 12))}</td>
            <td className="num">{inr(Math.round(newer.total_tax / 12))}</td>
          </tr>
        </tbody>
      </table>
      <figcaption className="sheet-foot">
        <span className="sheet-verdict">
          The {better} regime saves her <strong className="num">{inr(gap)}</strong> this year.
        </span>
        <span className="sheet-note">Sample employee, after proofs. Illustrative, FY 2025-26.</span>
      </figcaption>
    </figure>
  );
}
