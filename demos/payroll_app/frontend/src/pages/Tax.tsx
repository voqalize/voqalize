import { Link, useParams, useSearchParams } from "react-router-dom";
import { COMPANY, PRODUCT, TODAY } from "../lib/data";
import { date, rupees } from "../lib/format";
import { comparisonOf } from "../lib/payroll";
import { nameOf, useTk } from "../state/store";
import { RegimeView } from "../components/RegimeView";
import { PageHead, Panel, Status, TableWrap, Tabs, thing } from "../components/ui";

const W = COMPANY.company.windows;

export function TaxPage() {
  const [params] = useSearchParams();
  const tab = params.get("tab") ?? "declarations";
  return (
    <div className="page">
      <PageHead title="Tax" sub={`${PRODUCT.tax.fy_label}. Tax figures are illustrative, FY 2025-26.`} />
      <Tabs
        current={tab}
        tabs={[
          ["declarations", "Declarations and proofs"],
          ["regime", "Regimes"],
          ["form16", "Form 16"],
        ]}
      />
      {tab === "declarations" ? <Declarations /> : null}
      {tab === "regime" ? <Regimes /> : null}
      {tab === "form16" ? <Form16 /> : null}
    </div>
  );
}

function Window() {
  const total = Date.parse(W.proofs.closes) - Date.parse(W.proofs.opens);
  const done = Date.parse(TODAY) - Date.parse(W.proofs.opens);
  const left = Math.round((Date.parse(W.proofs.closes) - Date.parse(TODAY)) / 86400000);
  return (
    <div className="window" {...thing("Proof window")}>
      <div className="window-text">
        <strong>Proof window: {date(W.proofs.opens)} to {date(W.proofs.closes)}</strong>
        <span className="small muted">
          First verification {date(W.proofs.first_verification)}. {left} days left. Declared items without a verified proof do not reduce TDS.
        </span>
      </div>
      <div className="window-track" aria-hidden>
        <span className="window-fill" style={{ width: `${(done / total) * 100}%` }} />
      </div>
    </div>
  );
}

function Declarations() {
  const st = useTk();
  return (
    <>
      <Window />
      <Panel title="Declarations" {...thing("Declarations")} actions={<span className="small muted">Declared {date(W.declaration.opens)} to {date(W.declaration.closes)}</span>}>
        <TableWrap label="Declarations">
          <table className="grid">
            <thead>
              <tr>
                <th scope="col">Employee</th>
                <th scope="col">Item</th>
                <th scope="col">Section</th>
                <th scope="col" className="r">Declared</th>
                <th scope="col" className="r">Verified</th>
                <th scope="col">Proof status</th>
              </tr>
            </thead>
            <tbody>
              {st.declarations.flatMap((d) =>
                d.items.map((i, n) => (
                  <tr key={`${d.employee_id}-${n}`} className={n === 0 ? "group-start" : ""}>
                    <td>
                      {n === 0 ? (
                        <>
                          <Link to={`/employees/${d.employee_id}`}>{nameOf(d.employee_id, st)}</Link>
                          <small className="block muted">
                            {d.employee_id}, {d.regime} regime
                          </small>
                        </>
                      ) : null}
                    </td>
                    <td>{i.label}</td>
                    <td>{i.section.replace("_", " ")}</td>
                    <td className="r num">{rupees(i.declared)}</td>
                    <td className={`r num${i.verified < i.declared ? " neg" : ""}`}>{rupees(i.verified)}</td>
                    <td {...(i.proof_status !== "verified" ? thing("Proof status", `proof-${d.employee_id}-${n}`) : {})}>
                      <Status value={i.proof_status} />
                    </td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </TableWrap>
        <p className="small muted">{st.employees.length - st.declarations.length} employees declared nothing; their TDS is worked out with no deductions.</p>
      </Panel>
    </>
  );
}

function Regimes() {
  const st = useTk();
  const rows = st.employees.map((e) => ({ e, c: comparisonOf(e, st.declarations) }));
  const better = rows.filter((r) => r.c.better !== r.e.tax_regime && r.c.saving > 0);
  return (
    <Panel title="Regime by employee" actions={<span className="small muted">{better.length} would pay less on the other regime</span>}>
      <TableWrap label="Regime by employee">
        <table className="grid">
          <thead>
            <tr>
              <th scope="col">Employee</th>
              <th scope="col">Current</th>
              <th scope="col" className="r">New regime</th>
              <th scope="col" className="r">Old regime</th>
              <th scope="col">Lower</th>
              <th scope="col" className="r">Compare</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ e, c }) => {
              const off = c.better !== e.tax_regime && c.saving > 0;
              return (
                <tr key={e.id} className={off ? "is-flag" : ""}>
                  <td>
                    <Link to={`/employees/${e.id}`}>{e.name}</Link>
                    <small className="block muted">{e.id}</small>
                  </td>
                  <td>{e.tax_regime === "new" ? "New" : "Old"}</td>
                  <td className="r num">{rupees(c.new.total_tax)}</td>
                  <td className="r num">{rupees(c.old.total_tax)}</td>
                  <td>{c.saving ? `${c.better === "new" ? "New" : "Old"} by ${rupees(c.saving)}` : "Equal"}</td>
                  <td className="r">
                    <Link to={`/tax/regime/${e.id}`} className="link">
                      Open
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </TableWrap>
    </Panel>
  );
}

function Form16() {
  const f = COMPANY.form16;
  return (
    <div className="detail-grid" {...thing("Form 16")}>
      <Panel title="FY 2025-26">
        <p>
          <Status value={f.fy_2025_26.status} /> Due by {date(f.fy_2025_26.due_by)}
        </p>
        <p className="muted">{f.fy_2025_26.note}</p>
      </Panel>
      <Panel title="FY 2024-25">
        <p>
          <Status value={f.fy_2024_25.status} /> Issued {date(f.fy_2024_25.issued_on)}
        </p>
        <p className="muted">{f.fy_2024_25.note}</p>
      </Panel>
    </div>
  );
}

export function RegimePage() {
  const { employeeId = "" } = useParams();
  const e = useTk((s) => s.employees.find((x) => x.id === employeeId));
  return (
    <div className="page">
      <PageHead
        title={e ? `${e.name}: new or old regime` : "Regime comparison"}
        sub={
          <>
            <Link to="/tax?tab=regime">Tax</Link> / Regime comparison{e ? `, ${e.id}, ${e.location}` : ""}
          </>
        }
      />
      <RegimeView employeeId={employeeId} />
    </div>
  );
}
