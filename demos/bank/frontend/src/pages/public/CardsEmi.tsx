import { Info, Repeat } from "lucide-react";
import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { askConfirm } from "../../app/ConfirmSheet";
import { Crumbs } from "../../components/ui";
import { customer, daysAgo, fmtDate, inr, products, txnById } from "../../data/bank";
import { cardEmiTable } from "../../lib/bankmath";
import { useAdvisor } from "../../state/advisor";
import { useSession } from "../../state/session";

/** Credit-card spends that can be converted to EMI, newest first. */
export const emiTxns = () => customer.transactions.filter((t) => t.account === "cc" && t.direction === "debit" && t.emi_eligible).sort((a, b) => a.days_ago - b.days_ago);

export function CardsEmi() {
  const [params, setParams] = useSearchParams();
  const signedIn = useSession((s) => s.signedIn);
  const { emiTxn, emiAmount, emiTenure, setEmi } = useAdvisor();
  const qTxn = params.get("txn");

  // The URL's txn is the selected one (the agent and the visitor both set it there).
  useEffect(() => {
    if (qTxn !== emiTxn) {
      const t = qTxn ? txnById(qTxn) : null;
      setEmi({ txn: qTxn, ...(t ? { amount: t.amount } : {}) });
    }
  }, [qTxn]); // eslint-disable-line react-hooks/exhaustive-deps

  const txn = signedIn && emiTxn ? txnById(emiTxn) : undefined;
  const amount = txn ? txn.amount : emiAmount;
  const rows = amount >= products.emi.min_amount ? cardEmiTable(amount) : [];
  const chosen = rows.find((r) => r.months === emiTenure);

  return (
    <main className="page emi" data-stage-thing="screen:cards_emi" data-stage-label="EMI planner">
      <div className="wrap">
        <Crumbs items={[{ to: "/cards", label: "Credit cards" }, { label: "EMI planner" }]} />
        <header className="page-head">
          <h1 className="page-title">Turn a card spend into EMIs</h1>
          <p className="page-lede">
            Any credit card spend of {inr(products.emi.min_amount)} or more can be paid in 3 to 24 monthly instalments. Here is every tenure, with the interest and
            the one-time processing fee counted in.
          </p>
        </header>
        <div className="emi-grid">
          <section className="card emi-input" aria-label="What to convert">
            {signedIn ? (
              <>
                <h2 className="side-h">Your credit card spends you can convert</h2>
                <ul className="txn-pick" role="radiogroup" aria-label="Card spends">
                  {emiTxns().map((t) => (
                    <li key={t.id}>
                      <button
                        type="button"
                        role="radio"
                        aria-checked={emiTxn === t.id}
                        className={`txn-opt${emiTxn === t.id ? " is-on" : ""}`}
                        data-stage-part={`txn:${t.id}`}
                        data-stage-thing={`txn:${t.id}`}
                        data-stage-label={t.merchant}
                        onClick={() => setParams({ txn: t.id }, { replace: true })}
                      >
                        <span className="to-merchant">{t.merchant}</span>
                        <span className="to-date">{fmtDate(daysAgo(t.days_ago))}</span>
                        <span className="to-amt num">{inr(t.amount)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
                <button type="button" className="link-btn" onClick={() => setParams({}, { replace: true })}>
                  Or work out any amount
                </button>
              </>
            ) : (
              <p className="side-small">
                <Info size={14} aria-hidden /> <Link to="/login?from=/cards/emi">Sign in</Link> to pick one of your own card spends.
              </p>
            )}
            {!txn ? (
              <div className="field">
                <label className="field-label" htmlFor="emi-amount">
                  Amount
                </label>
                <div className="input-wrap" data-stage-part="amount" data-stage-thing="emi:amount" data-stage-label="Amount">
                  <span className="input-prefix">₹</span>
                  <input
                    id="emi-amount"
                    className="input has-prefix num"
                    inputMode="numeric"
                    value={emiAmount ? emiAmount.toLocaleString("en-IN") : ""}
                    onChange={(e) => setEmi({ amount: Number(e.target.value.replace(/\D/g, "")) || 0 })}
                  />
                </div>
                {emiAmount < products.emi.min_amount ? <p className="field-hint">The smallest spend we convert is {inr(products.emi.min_amount)}.</p> : null}
              </div>
            ) : (
              <div className="emi-chosen" data-stage-thing="emi:txn" data-stage-label="Card spend">
                <span>Converting</span>
                <strong>{txn.merchant}</strong>
                <span className="num">
                  {inr(txn.amount)}, spent {fmtDate(daysAgo(txn.days_ago))}
                </span>
              </div>
            )}
            {qTxn && !signedIn ? <p className="field-hint">Sign in to convert this spend; until then you see a plan for any amount.</p> : null}
          </section>

          <section className="card emi-table-wrap" aria-label="EMI options">
            {rows.length ? (
              <>
                <div className="table-scroll">
                  <table className="data-table emi-table">
                    <thead>
                      <tr>
                        <th scope="col">Tenure</th>
                        <th scope="col" className="r">
                          Interest rate
                        </th>
                        <th scope="col" className="r">
                          Monthly EMI
                        </th>
                        <th scope="col" className="r">
                          Total interest
                        </th>
                        <th scope="col" className="r">
                          Fee + GST
                        </th>
                        <th scope="col" className="r">
                          Total cost
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => (
                        <tr
                          key={r.months}
                          className={r.months === emiTenure ? "is-on" : undefined}
                          data-stage-part={`tenure:${r.months}`}
                          data-stage-thing={`emi:${r.months}`}
                          data-stage-label={`${r.months} months`}
                          onClick={() => setEmi({ tenure: r.months })}
                        >
                          <th scope="row">
                            <button type="button" className="row-pick" aria-pressed={r.months === emiTenure} onClick={() => setEmi({ tenure: r.months })}>
                              {r.months} months
                            </button>
                          </th>
                          <td className="r num">{r.rate}% a year</td>
                          <td className="r num strong">{inr(r.emi)}</td>
                          <td className="r num">{inr(r.total_interest)}</td>
                          <td className="r num">
                            {inr(r.processing_fee)} + {inr(r.gst_on_fee)}
                          </td>
                          <td className="r num">{inr(r.total_cost)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {chosen ? (
                  <div className="emi-summary" data-stage-thing="emi:summary" data-stage-label="Your plan">
                    <div>
                      <span className="es-label">Your plan</span>
                      <span className="es-big num">
                        {inr(chosen.emi)} <small>a month for {chosen.months} months</small>
                      </span>
                      <span className="es-sub">
                        You pay {inr(amount + chosen.total_cost)} in all for {inr(amount)}: {inr(chosen.total_interest)} interest at {chosen.rate}%, and a one-time{" "}
                        {inr(chosen.processing_fee)} fee plus {inr(chosen.gst_on_fee)} GST on your next statement.
                      </span>
                    </div>
                    {signedIn && txn ? (
                      <button
                        type="button"
                        className="btn btn-accent btn-lg"
                        data-stage-thing="emi:convert"
                        data-stage-label="Convert to EMI"
                        data-dock-avoid
                        onClick={() => askConfirm({ kind: "emi_convert", target: txn.id, tenure_months: chosen.months })}
                      >
                        <Repeat size={17} aria-hidden /> Convert to EMI
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </>
            ) : (
              <p className="empty">Enter an amount of {inr(products.emi.min_amount)} or more to see the plans.</p>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
