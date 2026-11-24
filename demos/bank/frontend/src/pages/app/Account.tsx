import { Copy, FileText, Send } from "lucide-react";
import { useMemo } from "react";
import { Link, NavLink, Navigate, useParams } from "react-router-dom";
import { type AccountId, accountById, customer, daysAgo, fmtDate, inr } from "../../data/bank";
import { toast } from "../../app/toast";
import { useAllTxns, useBank } from "../../state/bank";
import { Amount, CatChip, Money, PageHead, Panel } from "./ui";

export function AccountPage() {
  const { id = "sb" } = useParams();
  const balances = useBank((s) => s.balances);
  const all = useAllTxns();
  const acc = accountById(id);
  const txns = useMemo(() => all.filter((t) => t.account === id).sort((a, b) => a.days_ago - b.days_ago), [all, id]);
  if (!acc) return <Navigate to="/app/accounts/sb" replace />;
  const balance = balances[acc.id as AccountId];
  const fullIfsc = acc.ifsc;
  const monthIn = txns.filter((t) => t.days_ago < 30 && t.direction === "credit").reduce((a, t) => a + t.amount, 0);
  const monthOut = txns.filter((t) => t.days_ago < 30 && t.direction === "debit").reduce((a, t) => a + t.amount, 0);

  const details: [string, string, string?][] = [
    ["Account holder", acc.holder],
    ["Account number", acc.number_masked, "Account number"],
    ["IFSC", fullIfsc, "IFSC"],
    ["Branch", acc.branch, "Branch"],
    ["Account type", acc.product],
    ["Interest rate", acc.rate ? `${acc.rate}% a year, paid quarterly` : "Non-interest bearing", "Interest rate"],
    ["Customer ID", customer.profile.customer_id],
  ];

  return (
    <div className="ax-page" data-stage-thing="screen:account" data-stage-label={acc.name}>
      <nav className="ax-subtabs" aria-label="Accounts">
        {customer.accounts.map((a) => (
          <NavLink key={a.id} to={`/app/accounts/${a.id}`} className={a.id === acc.id ? "is-active" : ""}>
            {a.name} <span>•••• {a.last4}</span>
          </NavLink>
        ))}
      </nav>
      <PageHead
        title={acc.name}
        sub={`${acc.product}, ${acc.branch}`}
        actions={
          <>
            <Link to="/app/payments" className="ax-btn ax-btn--primary ax-btn--sm">
              <Send size={15} /> Transfer money
            </Link>
            <Link to="/app/statements" className="ax-btn ax-btn--ghost ax-btn--sm">
              <FileText size={15} /> Statements
            </Link>
          </>
        }
      />

      <div className="ax-acchero">
        <div className="ax-acchero__bal" data-stage-thing="available-balance" data-stage-label="Available balance">
          <span className="ax-k">Available balance</span>
          <Money n={balance} className="ax-acchero__money" />
          <span className="ax-k">As of today, {fmtDate(daysAgo(0))}</span>
        </div>
        <div className="ax-acchero__flow">
          <div>
            <span className="ax-k">Money in, last 30 days</span>
            <strong className="ax-pos">+{inr(monthIn)}</strong>
          </div>
          <div>
            <span className="ax-k">Money out, last 30 days</span>
            <strong>−{inr(monthOut).replace("−", "")}</strong>
          </div>
        </div>
      </div>

      <div className="ax-split">
        <Panel title="Account details" thing="account-details" label="Account details">
          <dl className="ax-dl ax-dl--rows">
            {details.map(([k, v, label]) => (
              <div key={k} data-stage-thing={label ? `detail:${k.toLowerCase().replace(/\s+/g, "_")}` : undefined} data-stage-label={label}>
                <dt>{k}</dt>
                <dd>
                  {v}
                  {k === "IFSC" && (
                    <button type="button" className="ax-iconbtn ax-iconbtn--sm" aria-label="Copy IFSC" onClick={() => { navigator.clipboard?.writeText(v).catch(() => {}); toast("IFSC copied", "ok", 2000); }}>
                      <Copy size={13} />
                    </button>
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </Panel>

        <Panel title="Transactions" pad={false} thing="account-transactions" label="Account transactions" action={<span className="ax-k">{txns.length} entries with running balance</span>}>
          <div className="ax-tablewrap">
            <table className="ax-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Details</th>
                  <th className="ax-hide-sm">Category</th>
                  <th className="ax-r">Amount</th>
                  <th className="ax-r ax-hide-sm">Balance</th>
                </tr>
              </thead>
              <tbody>
                {txns.map((t) => (
                  <tr key={t.id} data-stage-thing={`txn:${t.id}`} data-stage-label={t.merchant}>
                    <td className="ax-nowrap">{fmtDate(daysAgo(t.days_ago))}</td>
                    <td>
                      <Link to="/app/transactions" className="ax-tdlink" onClick={() => useBank.getState().openTxn(t.id)}>
                        <strong>{t.merchant}</strong>
                        <span className="ax-stmt">
                          {t.description} <i>|</i> {t.mode}
                        </span>
                      </Link>
                    </td>
                    <td className="ax-hide-sm">
                      <CatChip id={t.category} />
                    </td>
                    <td className="ax-r">
                      <Amount t={t} />
                    </td>
                    <td className="ax-r ax-hide-sm ax-muted">{t.balance_after != null ? inr(t.balance_after, { paise: true }) : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </div>
  );
}
