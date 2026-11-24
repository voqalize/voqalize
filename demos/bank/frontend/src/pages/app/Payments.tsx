import { CheckCircle2, Plus, Repeat, UserRound, Zap } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { billDue } from "../../app/actions";
import { askConfirm } from "../../app/ConfirmSheet";
import { toast } from "../../app/toast";
import { type AccountId, accountById, billerById, brand, customer, daysFromNow, fmtDate, inr, products } from "../../data/bank";
import { useBank } from "../../state/bank";
import { PageHead, Panel, inDays } from "./ui";

export function Payments() {
  const balances = useBank((s) => s.balances);
  const transfers = useBank((s) => s.transfers);
  const [to, setTo] = useState(customer.beneficiaries[0].id);
  const [from, setFrom] = useState<AccountId>("sb");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const b = customer.beneficiaries.find((x) => x.id === to)!;
  const amt = Number(amount);
  const over = amt > b.limit ? `Above the ${inr(b.limit)} limit for ${b.nickname}` : amt > balances[from] ? "More than the balance" : "";

  return (
    <div className="ax-page" data-stage-thing="screen:payments" data-stage-label="Payments">
      <PageHead title="Payments" sub="Send money to people you have added. Transfers within Global Bank are instant; to other banks by IMPS, or RTGS from ₹2,00,000." />
      <div className="ax-split ax-split--pay">
        <Panel title="Beneficiaries" pad={false} thing="beneficiaries" label="Beneficiaries" action={<button type="button" className="ax-link" onClick={() => toast("Adding a beneficiary needs an OTP; this demo keeps the five you have.", "info")}><Plus size={14} /> Add</button>}>
          <ul className="ax-benes">
            {customer.beneficiaries.map((x) => (
              <li key={x.id} data-stage-thing={`beneficiary:${x.id}`} data-stage-label={`${x.name} (${x.nickname})`}>
                <button type="button" className={to === x.id ? "is-sel" : ""} onClick={() => setTo(x.id)}>
                  <span className="ax-avatar ax-avatar--soft">{x.name.split(" ").map((w) => w[0]).join("")}</span>
                  <span className="ax-benes__main">
                    <strong>
                      {x.name} <em>{x.nickname}</em>
                    </strong>
                    <span>
                      {x.bank}, {x.account_masked}
                    </span>
                  </span>
                  <span className="ax-benes__limit">
                    <span className="ax-k">Limit</span>
                    {inr(x.limit)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Transfer money" thing="transfer-form" label="Transfer form">
          <form
            className="ax-form"
            onSubmit={(e) => {
              e.preventDefault();
              askConfirm({ kind: "transfer", target: to, amount: amt, from_account: from });
            }}
          >
            <label className="ax-field">
              <span>From</span>
              <select value={from} onChange={(e) => setFrom(e.target.value as AccountId)}>
                {customer.accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} •••• {a.last4} ({inr(balances[a.id])})
                  </option>
                ))}
              </select>
            </label>
            <label className="ax-field">
              <span>To</span>
              <select value={to} onChange={(e) => setTo(e.target.value)}>
                {customer.beneficiaries.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.name} ({x.nickname}), {x.bank}
                  </option>
                ))}
              </select>
            </label>
            <div className="ax-tocard">
              <UserRound size={18} />
              <span>
                {b.name}, {b.account_masked}, IFSC {b.ifsc}
                <small>{b.bank === brand.name ? "Within Global Bank, instant" : "IMPS, usually within seconds"}</small>
              </span>
            </div>
            <label className="ax-field">
              <span>Amount</span>
              <div className={`ax-moneyin${over ? " is-bad" : ""}`}>
                <i>₹</i>
                <input inputMode="decimal" placeholder="0" value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ""))} aria-invalid={!!over} />
              </div>
              <small className={over ? "ax-err" : "ax-k"}>{over || `Up to ${inr(Math.min(b.limit, balances[from]))} to ${b.nickname}`}</small>
            </label>
            <label className="ax-field">
              <span>Note (optional)</span>
              <input value={note} maxLength={40} onChange={(e) => setNote(e.target.value)} placeholder="Rent for November" />
            </label>
            <button type="submit" className="ax-btn ax-btn--primary" disabled={!amt || !!over}>
              Review transfer
            </button>
          </form>
        </Panel>
      </div>

      {transfers.length > 0 && (
        <Panel title="Sent in this session" pad={false}>
          <ul className="ax-sent">
            {transfers.map((t) => {
              const x = customer.beneficiaries.find((y) => y.id === t.beneficiary)!;
              return (
                <li key={t.reference}>
                  <CheckCircle2 size={18} />
                  <span>
                    {inr(t.amount)} to {x.name} from {accountById(t.from)!.name}
                  </span>
                  <span className="ax-k">Ref {t.reference}</span>
                </li>
              );
            })}
          </ul>
        </Panel>
      )}
    </div>
  );
}

export function Bills() {
  const paid = useBank((s) => s.billsPaid);
  useBank((s) => s.cc); // re-render when the card is paid elsewhere
  const loan = customer.loans[0];
  const registered = new Set(customer.registered_billers.map((b) => b.biller_id));
  const others = products.billers.filter((b) => !registered.has(b.id));
  const totalDue = customer.registered_billers.reduce((a, b) => a + billDue(b.biller_id), 0);

  return (
    <div className="ax-page" data-stage-thing="screen:bills" data-stage-label="Bills">
      <PageHead title="Bills" sub={`${customer.registered_billers.length} registered billers. ${totalDue ? `${inr(totalDue)} due in the next ${Math.max(...customer.registered_billers.map((b) => b.due_days_from_now))} days.` : "Everything is paid."}`} />
      <Panel pad={false} thing="billers" label="Billers">
        <div className="ax-tablewrap">
          <table className="ax-table ax-table--bills">
            <thead>
              <tr>
                <th>Biller</th>
                <th className="ax-hide-sm">Consumer no.</th>
                <th className="ax-hide-sm">Due date</th>
                <th className="ax-r">Amount due</th>
                <th className="ax-r">
                  <span className="ax-sr">Action</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {customer.registered_billers.map((r) => {
                const b = billerById(r.biller_id)!;
                const p = paid[r.biller_id];
                const due = billDue(r.biller_id);
                return (
                  <tr key={r.biller_id} data-stage-thing={`biller:${r.biller_id}`} data-stage-label={b.name}>
                    <td>
                      <div className="ax-biller">
                        <span className="ax-biller__icon">
                          <Zap size={16} />
                        </span>
                        <span>
                          <strong>{b.name}</strong>
                          <span className="ax-k">
                            {b.category}
                            {r.autopay && (
                              <em className="ax-tag ax-tag--teal">
                                <Repeat size={11} /> Autopay
                              </em>
                            )}
                          </span>
                          <span className={`ax-k ax-show-sm${r.due_days_from_now <= 7 && !p ? " ax-warn" : ""}`}>{p ? "Paid" : `Due ${fmtDate(daysFromNow(r.due_days_from_now))}`}</span>
                        </span>
                      </div>
                    </td>
                    <td className="ax-hide-sm ax-stmt">{r.consumer_masked}</td>
                    <td className="ax-nowrap ax-hide-sm">
                      {fmtDate(daysFromNow(r.due_days_from_now))}
                      <span className={`ax-k ax-block${r.due_days_from_now <= 7 && !p ? " ax-warn" : ""}`}>{p ? "Paid" : inDays(r.due_days_from_now)}</span>
                    </td>
                    <td className="ax-r">
                      <strong>{p ? inr(p.amount) : inr(due)}</strong>
                    </td>
                    <td className="ax-r">
                      {p ? (
                        <span className="ax-status ax-status--ok" title={`Reference ${p.reference}`}>
                          Paid
                        </span>
                      ) : (
                        <button type="button" className="ax-btn ax-btn--primary ax-btn--xs" onClick={() => askConfirm({ kind: "bill_pay", target: r.biller_id, from_account: "sb" })}>
                          Pay
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="ax-split">
        <Panel title="Loan EMIs (auto-debit)" thing={`loan:${loan.id}`} label="Car loan EMI">
          <div className="ax-loanrow">
            <div>
              <strong>{loan.name}</strong>
              <span className="ax-k">
                {loan.months_left} EMIs left, {inr(loan.outstanding)} outstanding at {loan.rate}%
              </span>
            </div>
            <div className="ax-r">
              <strong>{inr(loan.emi)}</strong>
              <span className="ax-k">on {fmtDate(daysFromNow(loan.next_emi_days_from_now))}</span>
            </div>
          </div>
          <p className="ax-k">Debited from savings •••• {accountById("sb")!.last4} on the due date.</p>
        </Panel>
        <Panel title="Add a biller">
          <ul className="ax-addbill">
            {others.map((b) => (
              <li key={b.id}>
                <span>
                  <strong>{b.name}</strong>
                  <span className="ax-k">{b.category}</span>
                </span>
                <button type="button" className="ax-btn ax-btn--ghost ax-btn--xs" onClick={() => toast(`Registering ${b.name} needs your consumer number; not part of this demo.`, "info")}>
                  Add
                </button>
              </li>
            ))}
          </ul>
          <p className="ax-k">
            Card bill? <Link to="/app/cards/credit" className="ax-link">Pay it from the credit card page</Link>.
          </p>
        </Panel>
      </div>
    </div>
  );
}
