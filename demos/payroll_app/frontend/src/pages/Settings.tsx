import { useSearchParams } from "react-router-dom";
import { COMPANY, PRODUCT } from "../lib/data";
import { rupees } from "../lib/format";
import { PageHead, Panel, Status, TableWrap, Tabs } from "../components/ui";

const c = COMPANY.company;

export function SettingsPage() {
  const [params] = useSearchParams();
  const tab = params.get("tab") ?? "company";
  return (
    <div className="page">
      <PageHead title="Settings" sub={`${c.legal_name}. Changes here apply from the next payroll run.`} />
      <Tabs
        current={tab}
        tabs={[
          ["company", "Company"],
          ["statutory", "Statutory IDs"],
          ["structure", "Pay structure"],
          ["leave", "Leave policy"],
          ["billing", "Billing"],
        ]}
      />
      {tab === "company" ? (
        <div className="detail-grid">
          <Panel title="Company">
            <dl className="kv kv-wide">
              <dt>Name</dt>
              <dd>{c.name}</dd>
              <dt>Legal name</dt>
              <dd>{c.legal_name}</dd>
              <dt>Industry</dt>
              <dd>{c.industry}</dd>
              <dt>Founded</dt>
              <dd>{c.founded}</dd>
              <dt>Registered office</dt>
              <dd>{c.registered_office}</dd>
              <dt>Pay cycle</dt>
              <dd>{c.pay_cycle}</dd>
              <dt>Payroll approver</dt>
              <dd>{c.payroll_approver.name}</dd>
              <dt>HR admin</dt>
              <dd>{c.admin.name}</dd>
            </dl>
          </Panel>
          <Panel title="Locations">
            <ul className="linklist">
              {c.locations.map((l) => (
                <li key={l.city}>
                  <span>
                    <strong>{l.city}</strong>
                    <small className="block muted">{l.office}</small>
                  </span>
                  <span className="small muted">{l.state}</span>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      ) : null}
      {tab === "statutory" ? (
        <Panel title="Statutory IDs">
          <dl className="kv kv-wide">
            <dt>PAN</dt>
            <dd className="num">{c.pan}</dd>
            <dt>TAN</dt>
            <dd className="num">{c.tan}</dd>
            <dt>PF establishment code</dt>
            <dd className="num">{c.pf_code}</dd>
            <dt>ESI code</dt>
            <dd className="num">{c.esi_code}</dd>
            {Object.entries(c.pt_registrations).map(([state, id]) => (
              <div key={state} className="kv-row">
                <dt>PT registration, {state}</dt>
                <dd className="num">{id}</dd>
              </div>
            ))}
          </dl>
          <p className="small muted">Professional tax is deducted by each state's slab; the registrations on file are for {Object.keys(c.pt_registrations).join(" and ")}.</p>
        </Panel>
      ) : null}
      {tab === "structure" ? (
        <Panel title="Pay-structure rule">
          <p className="lede">{COMPANY.structure_rule}</p>
          <TableWrap label="Structure for a sample CTC">
            <table className="grid">
              <thead>
                <tr>
                  <th scope="col">Component</th>
                  <th scope="col">Rule</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Basic</td>
                  <td>40% of monthly CTC</td>
                </tr>
                <tr>
                  <td>HRA</td>
                  <td>50% of basic in Mumbai and New Delhi, 40% elsewhere</td>
                </tr>
                <tr>
                  <td>LTA</td>
                  <td>₹3,000 a month at G5, ₹5,000 at G6 and up</td>
                </tr>
                <tr>
                  <td>Employer PF</td>
                  <td>12% of basic, on wages up to ₹15,000</td>
                </tr>
                <tr>
                  <td>Employer ESI</td>
                  <td>3.25% while gross is up to ₹21,000</td>
                </tr>
                <tr>
                  <td>Special allowance</td>
                  <td>The balance</td>
                </tr>
              </tbody>
            </table>
          </TableWrap>
        </Panel>
      ) : null}
      {tab === "leave" ? (
        <Panel title="Leave policy">
          <dl className="kv kv-wide">
            {COMPANY.leave.policy.types.map((t) => (
              <div key={t.id} className="kv-row">
                <dt>{t.name}</dt>
                <dd>
                  {t.per_year ? `${t.per_year} days a year, ${t.accrual.toLowerCase()}` : t.accrual}
                  {t.carry_forward_max ? `; up to ${t.carry_forward_max} carried forward` : ""}
                </dd>
              </div>
            ))}
            <dt>Cut-off</dt>
            <dd>{COMPANY.leave.policy.attendance_cutoff}</dd>
            <dt>Loss of pay</dt>
            <dd>{COMPANY.leave.policy.lop_rule}</dd>
          </dl>
        </Panel>
      ) : null}
      {tab === "billing" ? (
        <>
          <Panel title="Your plan">
            <p className="lede">{c.plan_note}</p>
            <p className="small muted">Prices exclude {PRODUCT.pricing_rules.gst_pct}% GST. Pay yearly for {PRODUCT.pricing_rules.annual_discount_pct}% off.</p>
          </Panel>
          <div className="plans">
            {PRODUCT.plans.map((p) => (
              <section key={p.id} className={`plan-card${p.id === c.plan ? " is-current" : ""}`}>
                <div className="plan-head">
                  <h3>{p.name}</h3>
                  {p.id === c.plan ? <Status value="approved" /> : null}
                </div>
                <p className="plan-price">
                  <span className="num">{rupees(p.price_per_employee_month)}</span> per employee a month
                </p>
                <p className="small muted">
                  Minimum {rupees(p.minimum_month)} a month, up to {p.max_employees.toLocaleString("en-IN")} employees
                </p>
                <p className="small">{p.summary}</p>
                <p className="small muted">{p.support}</p>
              </section>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
