import { Download, FileText } from "lucide-react";
import { useMemo, useState } from "react";
import { askConfirm } from "../../app/ConfirmSheet";
import { toast } from "../../app/toast";
import { type AccountId, accountById, cardById, customer, daysAgo, daysFromNow, fmtDate, inr, monthBounds, monthName, products } from "../../data/bank";
import { fdQuote, fdRate } from "../../lib/bankmath";
import { useAllTxns, useBank } from "../../state/bank";
import { txnMonth } from "../../app/spending";
import { PageHead, Panel } from "./ui";

const PAYOUT_LABEL: Record<string, string> = { cumulative: "At maturity", monthly: "Monthly", quarterly: "Quarterly" };
const TENURES = [6, 9, 12, 15, 18, 24, 36, 48, 60, 84, 120];

export function Deposits() {
  const deposits = useBank((s) => s.deposits);
  const balances = useBank((s) => s.balances);
  const [amount, setAmount] = useState("100000");
  const [months, setMonths] = useState(18);
  const [payout, setPayout] = useState<"cumulative" | "monthly" | "quarterly">("cumulative");
  const [from, setFrom] = useState<AccountId>("sb");
  const amt = Number(amount) || 0;
  const q = fdQuote(amt, months, payout);
  const err = amt < products.fd.min_amount ? `The smallest deposit is ${inr(products.fd.min_amount)}` : amt > balances[from] ? "More than the account balance" : "";
  const total = deposits.reduce((a, d) => a + d.amount, 0);

  return (
    <div className="ax-page" data-stage-thing="screen:deposits" data-stage-label="Deposits">
      <PageHead title="Fixed deposits" sub={`${deposits.length} deposits, ${inr(total)} in all.`} />
      <Panel pad={false} thing="fd-list" label="Your deposits">
        <div className="ax-tablewrap">
          <table className="ax-table">
            <thead>
              <tr>
                <th>Deposit</th>
                <th className="ax-r">Amount</th>
                <th className="ax-r ax-hide-sm">Rate</th>
                <th className="ax-hide-sm">Opened</th>
                <th>Matures</th>
                <th className="ax-r">At maturity</th>
                <th className="ax-hide-sm">Interest paid</th>
              </tr>
            </thead>
            <tbody>
              {deposits.map((d) => (
                <tr key={d.id} data-stage-thing={`fd:${d.id}`} data-stage-label={`Deposit of ${inr(d.amount)}`}>
                  <td>
                    <strong>{d.tenure_months}-month FD</strong>
                    <span className="ax-k ax-block">{d.reference ? `New, ref ${d.reference}` : d.id.toUpperCase()}</span>
                  </td>
                  <td className="ax-r">{inr(d.amount)}</td>
                  <td className="ax-r ax-hide-sm">{d.rate}%</td>
                  <td className="ax-hide-sm ax-nowrap">{fmtDate(daysAgo(d.opened_days_ago))}</td>
                  <td className="ax-nowrap">{fmtDate(daysFromNow(d.matures_days_from_now))}</td>
                  <td className="ax-r">
                    <strong>{inr(d.maturity_amount)}</strong>
                  </td>
                  <td className="ax-hide-sm">{PAYOUT_LABEL[d.payout] ?? d.payout}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="ax-split ax-split--fd">
        <Panel title="Book a fixed deposit" thing="fd-form" label="Book an FD">
          <form
            className="ax-form"
            onSubmit={(e) => {
              e.preventDefault();
              askConfirm({ kind: "fd_book", amount: amt, tenure_months: months, payout, from_account: from });
            }}
          >
            <label className="ax-field">
              <span>Amount</span>
              <div className={`ax-moneyin${err ? " is-bad" : ""}`}>
                <i>₹</i>
                <input inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value.replace(/\D/g, ""))} aria-invalid={!!err} />
              </div>
              {err && <small className="ax-err">{err}</small>}
            </label>
            <label className="ax-field">
              <span>Tenure</span>
              <select value={months} onChange={(e) => setMonths(Number(e.target.value))}>
                {TENURES.map((m) => (
                  <option key={m} value={m}>
                    {m} months ({fdRate(m)}%)
                  </option>
                ))}
              </select>
            </label>
            <div className="ax-field">
              <span>Interest payout</span>
              <div className="ax-seg ax-seg--full" role="radiogroup" aria-label="Interest payout">
                {(["cumulative", "quarterly", "monthly"] as const).map((p) => (
                  <button key={p} type="button" role="radio" aria-checked={payout === p} className={payout === p ? "is-on" : ""} onClick={() => setPayout(p)}>
                    {PAYOUT_LABEL[p]}
                  </button>
                ))}
              </div>
            </div>
            <label className="ax-field">
              <span>From</span>
              <select value={from} onChange={(e) => setFrom(e.target.value as AccountId)}>
                {customer.accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} ({inr(balances[a.id])})
                  </option>
                ))}
              </select>
            </label>
            <div className="ax-quote" data-stage-thing="fd-quote" data-stage-label="FD quote" aria-live="polite">
              <div>
                <span className="ax-k">Rate</span>
                <strong>{q.rate}% a year</strong>
              </div>
              <div>
                <span className="ax-k">{payout === "cumulative" ? "You get at maturity" : `Interest ${payout}`}</span>
                <strong className="ax-fig">{payout === "cumulative" ? inr(q.maturity) : inr(q.payout_each)}</strong>
              </div>
              <div>
                <span className="ax-k">Total interest</span>
                <strong>{inr(q.interest)}</strong>
              </div>
              <div>
                <span className="ax-k">Matures on</span>
                <strong>{fmtDate(daysFromNow(Math.round(months * 30.44)))}</strong>
              </div>
            </div>
            <button type="submit" className="ax-btn ax-btn--primary" disabled={!!err}>
              Review deposit
            </button>
          </form>
        </Panel>
        <Panel title="Rates" thing="fd-rates" label="FD rates">
          <table className="ax-table ax-table--tight">
            <tbody>
              {products.fd.rates.map((r) => (
                <tr key={r.label} className={months >= r.min_months && months <= r.max_months ? "is-sel" : ""}>
                  <td>{r.label}</td>
                  <td className="ax-r">
                    <strong>{r.rate}%</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="ax-k">Senior citizens get {products.fd.senior_bonus}% more. Interest compounds quarterly on cumulative deposits.</p>
        </Panel>
      </div>
    </div>
  );
}

export function Statements() {
  const all = useAllTxns();
  const credit = cardById("credit")!;
  const rows = useMemo(() => {
    const out: { acc: "sb" | "ca"; month: string; opening: number; closing: number; credits: number; debits: number; n: number }[] = [];
    for (const acc of ["sb", "ca"] as const) {
      const txns = all.filter((t) => t.account === acc);
      const months = [...new Set(txns.map(txnMonth))].sort().reverse();
      for (const m of months) {
        const inM = txns.filter((t) => txnMonth(t) === m).sort((a, b) => a.days_ago - b.days_ago);
        const credits = inM.filter((t) => t.direction === "credit").reduce((a, t) => a + t.amount, 0);
        const debits = inM.filter((t) => t.direction === "debit").reduce((a, t) => a + t.amount, 0);
        const closing = inM[0].balance_after ?? 0;
        out.push({ acc, month: m, closing, opening: Math.round((closing - credits + debits) * 100) / 100, credits, debits, n: inM.length });
      }
    }
    return out;
  }, [all]);
  const download = (what: string) => toast(`${what}: PDF download is not part of this demo.`, "info");

  return (
    <div className="ax-page" data-stage-thing="screen:statements" data-stage-label="Statements">
      <PageHead title="Statements" sub="Monthly account statements and credit card statements." />
      {(["sb", "ca"] as const).map((acc) => {
        const a = accountById(acc)!;
        return (
          <Panel key={acc} title={`${a.name} •••• ${a.last4}`} pad={false} thing={`statements:${acc}`} label={`${a.name} statements`}>
            <div className="ax-tablewrap">
              <table className="ax-table">
                <thead>
                  <tr>
                    <th>Month</th>
                    <th className="ax-r ax-hide-sm">Opening</th>
                    <th className="ax-r">Money in</th>
                    <th className="ax-r">Money out</th>
                    <th className="ax-r">Closing</th>
                    <th className="ax-r">
                      <span className="ax-sr">Download</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows
                    .filter((r) => r.acc === acc)
                    .map((r) => {
                      const b = monthBounds(r.month);
                      const partial = b.to_days_ago === 0;
                      return (
                        <tr key={r.month} data-stage-thing={`statement:${acc}:${r.month}`} data-stage-label={`${monthName(r.month)} statement`}>
                          <td>
                            <strong>{monthName(r.month)}</strong>
                            <span className="ax-k ax-block">
                              {r.n} entries{partial ? ", so far" : ""}
                            </span>
                          </td>
                          <td className="ax-r ax-hide-sm">{inr(r.opening, { paise: true })}</td>
                          <td className="ax-r ax-pos">+{inr(r.credits)}</td>
                          <td className="ax-r">−{inr(r.debits)}</td>
                          <td className="ax-r">
                            <strong>{inr(r.closing, { paise: true })}</strong>
                          </td>
                          <td className="ax-r">
                            <button type="button" className="ax-iconbtn" aria-label={`Download ${monthName(r.month)} statement`} onClick={() => download(`${a.name}, ${monthName(r.month)}`)}>
                              <Download size={16} />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          </Panel>
        );
      })}
      <Panel title={`Credit card •••• ${credit.last4}`} pad={false} thing="statements:cc" label="Card statements">
        <div className="ax-tablewrap">
          <table className="ax-table">
            <thead>
              <tr>
                <th>Statement period</th>
                <th className="ax-hide-sm">Generated</th>
                <th className="ax-r">Total due</th>
                <th className="ax-r ax-hide-sm">Min due</th>
                <th>Status</th>
                <th className="ax-r">
                  <span className="ax-sr">Download</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {customer.statements
                .slice()
                .reverse()
                .map((s) => (
                  <tr key={s.id} data-stage-thing={`statement:${s.id}`} data-stage-label={`Card statement ${fmtDate(daysAgo(s.generated_days_ago))}`}>
                    <td className="ax-nowrap">
                      <FileText size={14} className="ax-inline-ic" /> {fmtDate(daysAgo(s.from_days_ago))} to {fmtDate(daysAgo(s.to_days_ago))}
                    </td>
                    <td className="ax-hide-sm ax-nowrap">{fmtDate(daysAgo(s.generated_days_ago))}</td>
                    <td className="ax-r">
                      <strong>{inr(s.total_due)}</strong>
                    </td>
                    <td className="ax-r ax-hide-sm">{inr(s.min_due)}</td>
                    <td>
                      {s.paid_days_ago != null ? (
                        <span className="ax-status ax-status--ok">Paid {fmtDate(daysAgo(s.paid_days_ago))}</span>
                      ) : (
                        <CardStatus due={s.due_days_from_now ?? 0} />
                      )}
                    </td>
                    <td className="ax-r">
                      <button type="button" className="ax-iconbtn" aria-label="Download card statement" onClick={() => download(`Card statement of ${fmtDate(daysAgo(s.generated_days_ago))}`)}>
                        <Download size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}

function CardStatus({ due }: { due: number }) {
  const paid = useBank((s) => s.billsPaid["anvaya-card"]);
  if (paid) return <span className="ax-status ax-status--ok">Paid today</span>;
  return <span className="ax-status ax-status--warn">Due {fmtDate(daysFromNow(due))}</span>;
}
