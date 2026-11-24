import { CalendarClock, ChevronRight, Gift, Lock, LockOpen, ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CONTROL_LABEL, eligibleEmiTxns } from "../../app/actions";
import { askConfirm, useConfirm } from "../../app/ConfirmSheet";
import { cardById, creditCardProduct, customer, daysAgo, daysFromNow, fmtDate, inr, products } from "../../data/bank";
import { cardEmi } from "../../lib/bankmath";
import { type CardId, useAllTxns, useBank } from "../../state/bank";
import { Amount, CardFace, CatChip, Meter, PageHead, Panel, Toggle, inDays } from "./ui";

const SWITCH_HINT: Record<string, string> = {
  international: "Payments and withdrawals outside India",
  online: "Websites and apps, in India and abroad",
  contactless: "Tap to pay at shops, up to the contactless limit",
  atm: "Cash withdrawals at any ATM",
};

/** Block + the four switches; every change goes through the confirmation sheet. */
function Controls({ card }: { card: CardId }) {
  const c = useBank((s) => s.cards[card].controls);
  const ask = (control: string, on: boolean) => askConfirm({ kind: "card_control", card, control: control as "online", value: on ? "on" : "off" });
  return (
    <Panel title="Card controls" thing={`controls:${card}`} label="Card controls" group>
      <div className={`ax-blockrow${c.blocked ? " is-blocked" : ""}`} data-stage-thing={`control:${card}:blocked`} data-stage-label="Block card">
        {c.blocked ? <Lock size={20} /> : <ShieldAlert size={20} />}
        <div>
          <strong>{c.blocked ? "This card is blocked" : "Block card"}</strong>
          <span>{c.blocked ? "Nothing can be charged to it until you unblock it." : "Lost it or see a charge you do not know? Block it at once."}</span>
        </div>
        <button
          type="button"
          className={`ax-btn ax-btn--sm ${c.blocked ? "ax-btn--primary" : "ax-btn--danger"}`}
          onClick={() => askConfirm({ kind: c.blocked ? "card_unblock" : "card_block", card })}
        >
          {c.blocked ? (
            <>
              <LockOpen size={15} /> Unblock
            </>
          ) : (
            <>
              <Lock size={15} /> Block
            </>
          )}
        </button>
      </div>
      {(["international", "online", "contactless", "atm"] as const).map((k) => (
        <Toggle
          key={k}
          label={CONTROL_LABEL[k]}
          hint={SWITCH_HINT[k]}
          checked={c[k]}
          disabled={c.blocked}
          thing={`control:${card}:${k}`}
          onChange={() => ask(k, !c[k])}
        />
      ))}
    </Panel>
  );
}

function LimitRow({ card, k }: { card: CardId; k: string }) {
  const value = useBank((s) => s.cards[card].limits[k]);
  const max = cardById(card)!.limits_max[k];
  const step = max > 200000 ? 10000 : 5000;
  const [draft, setDraft] = useState(value);
  const sheet = useConfirm((s) => s.sheet);
  // Back to the saved value whenever the sheet closes (cancelled) or the value changes.
  useEffect(() => {
    setDraft(value);
  }, [value, sheet === null]);
  const changed = draft !== value;
  return (
    <div className="ax-limit" data-stage-thing={`limit:${card}:${k}`} data-stage-label={CONTROL_LABEL[k]}>
      <div className="ax-limit__top">
        <span>{CONTROL_LABEL[k]}</span>
        <strong>{inr(draft)}</strong>
      </div>
      <input
        type="range"
        min={step}
        max={max}
        step={step}
        value={draft}
        onChange={(e) => setDraft(Number(e.target.value))}
        aria-label={`${CONTROL_LABEL[k]}, per day`}
        style={{ ["--fill" as string]: `${((draft - step) / (max - step)) * 100}%` }}
      />
      <div className="ax-limit__foot">
        <span>Per day, up to {inr(max)}</span>
        {changed && (
          <span className="ax-limit__acts">
            <button type="button" className="ax-link" onClick={() => setDraft(value)}>
              Reset
            </button>
            <button type="button" className="ax-btn ax-btn--primary ax-btn--xs" onClick={() => askConfirm({ kind: "card_limit", card, control: k as "atm_daily", value: String(draft) })}>
              Save limit
            </button>
          </span>
        )}
      </div>
    </div>
  );
}

function Limits({ card }: { card: CardId }) {
  const keys = ["online_daily", "pos_daily", "atm_daily"];
  return (
    <Panel title="Daily limits" thing={`limits:${card}`} label="Daily limits" group>
      {keys.map((k) => (
        <LimitRow key={k} card={card} k={k} />
      ))}
    </Panel>
  );
}

function CardTxns({ account, n = 10 }: { account: "cc" | "sb"; n?: number }) {
  const all = useAllTxns();
  const emi = useBank((s) => s.emi);
  const rows = useMemo(() => all.filter((t) => t.account === account && (account === "cc" || ["card", "ATM", "POS"].includes(t.mode))).sort((a, b) => a.days_ago - b.days_ago).slice(0, n), [all, account, n]);
  return (
    <ul className="ax-txlist ax-txlist--plain">
      {rows.map((t) => (
        <li key={t.id} data-stage-thing={`txn:${t.id}`} data-stage-label={t.merchant}>
          <Link to="/app/transactions" onClick={() => useBank.getState().openTxn(t.id)}>
            <div className="ax-txlist__main">
              <strong>{t.merchant}</strong>
              <span>
                {fmtDate(daysAgo(t.days_ago))}
                {emi[t.id] && <em className="ax-tag">On EMI</em>}
                {!emi[t.id] && t.emi_eligible && t.account === "cc" && <em className="ax-tag ax-tag--gold">EMI eligible</em>}
              </span>
            </div>
            <CatChip id={t.category} />
            <Amount t={t} />
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function CardsHub() {
  const cards = useBank((s) => s.cards);
  const cc = useBank((s) => s.cc);
  const debit = cardById("debit")!;
  const credit = cardById("credit")!;
  return (
    <div className="ax-page" data-stage-thing="screen:cards_hub" data-stage-label="Cards">
      <PageHead title="Cards" sub="Your debit and credit card, their controls and limits." />
      <div className="ax-cardshub">
        {(["debit", "credit"] as const).map((id) => {
          const c = id === "debit" ? debit : credit;
          const st = cards[id];
          return (
            <Link key={id} to={`/app/cards/${id}`} className="ax-cardtile" data-stage-thing={`card:${id}`} data-stage-label={id === "debit" ? "Debit card" : "Credit card"}>
              <CardFace card={id} blocked={st.controls.blocked} />
              <div className="ax-cardtile__body">
                <div className="ax-cardtile__title">
                  <strong>{c.name}</strong>
                  <span className={`ax-status ${st.controls.blocked ? "ax-status--bad" : "ax-status--ok"}`}>{st.controls.blocked ? "Blocked" : "Active"}</span>
                </div>
                {id === "credit" ? (
                  <dl className="ax-minidl">
                    <div>
                      <dt>Outstanding</dt>
                      <dd>{inr(cc.outstanding)}</dd>
                    </div>
                    <div>
                      <dt>Available</dt>
                      <dd>{inr(cc.available)}</dd>
                    </div>
                    <div>
                      <dt>Reward points</dt>
                      <dd>{credit.reward_points!.toLocaleString("en-IN")}</dd>
                    </div>
                  </dl>
                ) : (
                  <dl className="ax-minidl">
                    <div>
                      <dt>Linked to</dt>
                      <dd>Savings •••• {customer.accounts[0].last4}</dd>
                    </div>
                    <div>
                      <dt>ATM a day</dt>
                      <dd>{inr(st.limits.atm_daily)}</dd>
                    </div>
                    <div>
                      <dt>International</dt>
                      <dd>{st.controls.international ? "On" : "Off"}</dd>
                    </div>
                  </dl>
                )}
                <span className="ax-cardtile__go">
                  Manage card <ChevronRight size={16} />
                </span>
              </div>
            </Link>
          );
        })}
      </div>
      <Panel title="Explore other Global Bank credit cards">
        <div className="ax-catalogue">
          {products.credit_cards
            .filter((p) => p.id !== credit.product_id)
            .map((p) => (
              <Link key={p.id} to={`/cards/${p.id}`} className="ax-catalogue__item">
                <CardFace color={p.color} name={p.name} network={p.network} last4="0000" expiry="--/--" small />
                <strong>{p.name}</strong>
                <span>{p.best_for}</span>
              </Link>
            ))}
        </div>
      </Panel>
    </div>
  );
}

export function DebitCardPage() {
  const st = useBank((s) => s.cards.debit);
  const balance = useBank((s) => s.balances.sb);
  const c = cardById("debit")!;
  return (
    <div className="ax-page" data-stage-thing="screen:debit_card" data-stage-label="Debit card">
      <PageHead title="Debit card" sub={`${c.name}, linked to your savings account`} />
      <div className="ax-cardpage">
        <div className="ax-cardpage__left">
          <CardFace card="debit" blocked={st.controls.blocked} />
          <Panel>
            <dl className="ax-dl ax-dl--rows">
              <div data-stage-thing="card-status" data-stage-label="Card status">
                <dt>Status</dt>
                <dd>
                  <span className={`ax-status ${st.controls.blocked ? "ax-status--bad" : "ax-status--ok"}`}>{st.controls.blocked ? "Blocked" : "Active"}</span>
                </dd>
              </div>
              <div>
                <dt>Card number</dt>
                <dd>•••• •••• •••• {c.last4}</dd>
              </div>
              <div>
                <dt>Valid thru</dt>
                <dd>{c.expiry}</dd>
              </div>
              <div>
                <dt>Network</dt>
                <dd>{c.network}</dd>
              </div>
              <div data-stage-thing="linked-balance" data-stage-label="Available balance">
                <dt>Savings balance</dt>
                <dd>{inr(balance, { paise: true })}</dd>
              </div>
            </dl>
          </Panel>
          <Panel title="Recent card use" pad={false}>
            <CardTxns account="sb" n={6} />
          </Panel>
        </div>
        <div className="ax-cardpage__right">
          <Controls card="debit" />
          <Limits card="debit" />
        </div>
      </div>
    </div>
  );
}

export function CreditCardPage() {
  const st = useBank((s) => s.cards.credit);
  const cc = useBank((s) => s.cc);
  const paid = useBank((s) => s.billsPaid["globalbank-card"]);
  const emiMap = useBank((s) => s.emi);
  const all = useAllTxns();
  const c = cardById("credit")!;
  const prod = creditCardProduct(c.product_id!)!;
  const stmt = c.statement!;
  const eligible = useMemo(() => eligibleEmiTxns(), [all, emiMap]); // eslint-disable-line react-hooks/exhaustive-deps
  const conversions = Object.values(emiMap);

  return (
    <div className="ax-page" data-stage-thing="screen:credit_card" data-stage-label="Credit card">
      <PageHead title="Credit card" sub={`${c.name}, ${prod.tier.toLowerCase()} card on ${c.network}`} />

      <div className="ax-cchero">
        <CardFace card="credit" blocked={st.controls.blocked} />
        <div className="ax-cchero__nums">
          <div className="ax-cchero__big" data-stage-thing="outstanding" data-stage-label="Outstanding">
            <span className="ax-k">Outstanding</span>
            <strong className="ax-fig ax-fig--xl">{inr(cc.outstanding)}</strong>
          </div>
          <Meter value={cc.outstanding} max={c.credit_limit!} tone="gold" />
          <div className="ax-cchero__row">
            <div data-stage-thing="available-limit" data-stage-label="Available limit">
              <span className="ax-k">Available limit</span>
              <strong>{inr(cc.available)}</strong>
            </div>
            <div data-stage-thing="credit-limit" data-stage-label="Credit limit">
              <span className="ax-k">Credit limit</span>
              <strong>{inr(c.credit_limit!)}</strong>
            </div>
            <div data-stage-thing="cash-limit" data-stage-label="Cash limit">
              <span className="ax-k">Cash limit</span>
              <strong>{inr(c.cash_limit!)}</strong>
            </div>
            <div data-stage-thing="unbilled" data-stage-label="Unbilled amount">
              <span className="ax-k">Unbilled</span>
              <strong>{inr(c.unbilled!)}</strong>
            </div>
          </div>
        </div>
      </div>

      <div className="ax-cardpage">
        <div className="ax-cardpage__left">
          <Panel title="Statement" thing="statement" label="Statement" action={<Link to="/app/statements" className="ax-link">All statements</Link>}>
            <p className="ax-k">
              Generated {fmtDate(daysAgo(stmt.generated_days_ago))}
            </p>
            <div className="ax-stmtbox" data-stage-group="">
              <div data-stage-thing="total-due" data-stage-label="Total due">
                <span className="ax-k">Total due</span>
                <strong className="ax-fig">{inr(stmt.total_due)}</strong>
              </div>
              <div data-stage-thing="min-due" data-stage-label="Minimum due">
                <span className="ax-k">Minimum due</span>
                <strong className="ax-fig">{inr(stmt.min_due)}</strong>
              </div>
              <div data-stage-thing="due-date" data-stage-label="Due date">
                <span className="ax-k">Due date</span>
                <strong className="ax-fig">{fmtDate(daysFromNow(stmt.due_days_from_now))}</strong>
              </div>
            </div>
            {paid ? (
              <div className="ax-paidline">
                Paid {inr(paid.amount)}. Reference {paid.reference}
              </div>
            ) : (
              <div className="ax-payline">
                <span>
                  <CalendarClock size={15} /> Due {inDays(stmt.due_days_from_now)}
                </span>
                <button type="button" className="ax-btn ax-btn--primary ax-btn--sm" data-stage-thing="biller:globalbank-card" data-stage-label="Pay card bill" onClick={() => askConfirm({ kind: "bill_pay", target: "globalbank-card", from_account: "sb" })}>
                  Pay {inr(stmt.total_due)}
                </button>
              </div>
            )}
          </Panel>

          <Panel title="Reward points" thing="reward-points" label="Reward points">
            <div className="ax-points">
              <Gift size={22} />
              <div>
                <strong className="ax-fig">{c.reward_points!.toLocaleString("en-IN")}</strong>
                <span className="ax-k">Worth about {inr(Math.round(c.reward_points! * prod.point_value))} at {prod.point_value * 100} paise a point</span>
              </div>
            </div>
            <div className="ax-expiring" data-stage-thing="points-expiring" data-stage-label="Points expiring">
              {c.points_expiring!.points.toLocaleString("en-IN")} points expire on {fmtDate(daysFromNow(c.points_expiring!.days_from_now))}
            </div>
          </Panel>

          <Panel title="Convert to EMI" pad={false} thing="emi-eligible" label="EMI eligible spends" action={<span className="ax-k">From {inr(products.emi.min_amount)}</span>}>
            {eligible.length === 0 ? (
              <div className="ax-empty">
                <strong>No spends left to convert.</strong>
              </div>
            ) : (
              <ul className="ax-emilist">
                {eligible.map((t) => (
                  <EmiRow key={t.id} id={t.id} merchant={t.merchant} amount={t.amount} days={t.days_ago} />
                ))}
              </ul>
            )}
            {conversions.length > 0 && (
              <div className="ax-convs" data-stage-thing="emi-conversions" data-stage-label="EMI conversions">
                <h3>On EMI</h3>
                {conversions.map((x) => {
                  const t = all.find((y) => y.id === x.txn_id)!;
                  return (
                    <div key={x.txn_id} className="ax-convs__row" data-stage-thing={`emi-plan:${x.txn_id}`} data-stage-label={`EMI for ${t.merchant}`}>
                      <strong>{t.merchant}</strong>
                      <span>
                        {inr(t.amount)} as {x.tenure_months} × {inr(x.emi)} at {x.rate}%
                      </span>
                      <span className="ax-k">Ref {x.reference}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </Panel>

          <Panel title="Recent card transactions" pad={false} action={<Link to="/app/transactions" className="ax-link" onClick={() => useBank.getState().setFilter({ account: "cc", label: null })}>See all</Link>}>
            <CardTxns account="cc" n={10} />
          </Panel>
        </div>
        <div className="ax-cardpage__right">
          <Controls card="credit" />
          <Limits card="credit" />
        </div>
      </div>
    </div>
  );
}

function EmiRow({ id, merchant, amount, days }: { id: string; merchant: string; amount: number; days: number }) {
  const [tenure, setTenure] = useState(6);
  const row = cardEmi(amount, tenure);
  return (
    <li data-stage-thing={`emi:${id}`} data-stage-label={merchant}>
      <div className="ax-emilist__main">
        <strong>{merchant}</strong>
        <span className="ax-k">
          {fmtDate(daysAgo(days))}, {inr(amount)}
        </span>
      </div>
      <select value={tenure} onChange={(e) => setTenure(Number(e.target.value))} aria-label={`Tenure for ${merchant}`}>
        {products.emi.tenures.map((x) => (
          <option key={x.months} value={x.months}>
            {x.months} months
          </option>
        ))}
      </select>
      <span className="ax-emilist__emi">
        {inr(row.emi)}
        <small>/month</small>
      </span>
      <button type="button" className="ax-btn ax-btn--ghost ax-btn--xs" onClick={() => askConfirm({ kind: "emi_convert", target: id, tenure_months: tenure })}>
        Convert
      </button>
    </li>
  );
}
