import { ArrowUpRight, Ban, CalendarClock, Landmark, PiggyBank, Plane, Receipt, Send, Sparkles } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { billerById, cardById, creditCardProduct, customer, daysFromNow, fmtDate, inr, monthKey, monthName, today } from "../../data/bank";
import { billDue } from "../../app/actions";
import { askConfirm } from "../../app/ConfirmSheet";
import { prevMonth, spendByCategory } from "../../app/spending";
import { useAllTxns, useBank } from "../../state/bank";
import { ACCOUNT_LABEL, Amount, CardFace, CatChip, CatIcon, Meter, Money, Panel, catColor, inDays } from "./ui";

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

export function Dashboard() {
  const balances = useBank((s) => s.balances);
  const cc = useBank((s) => s.cc);
  const cards = useBank((s) => s.cards);
  const billsPaid = useBank((s) => s.billsPaid);
  const offersTaken = useBank((s) => s.offers);
  const all = useAllTxns();
  const p = customer.profile;
  const credit = cardById("credit")!;
  const debit = cardById("debit")!;
  const st = credit.statement!;
  const loan = customer.loans[0];
  const plOffer = customer.offers.find((o) => o.kind === "loan")!;
  const cardOffer = customer.offers.find((o) => o.kind === "card")!;
  const voyage = creditCardProduct(cardOffer.card_id!)!;

  const thisM = monthKey(today());
  const lastM = prevMonth(thisM);
  const spendNow = useMemo(() => spendByCategory(thisM, all), [all, thisM]);
  const spendPrev = useMemo(() => spendByCategory(lastM, all), [all, lastM]);
  const recent = all.slice().sort((a, b) => a.days_ago - b.days_ago).slice(0, 8);

  const dues = [
    ...customer.registered_billers.map((b) => ({
      key: b.biller_id,
      name: b.biller_id === "globalbank-card" ? `Credit card bill •••• ${credit.last4}` : (billerById(b.biller_id)?.name ?? b.biller_id),
      amount: billDue(b.biller_id),
      days: b.due_days_from_now,
      autopay: b.autopay,
      paid: !!billsPaid[b.biller_id],
      to: b.biller_id === "globalbank-card" ? "/app/cards/credit" : "/app/bills",
    })),
    { key: loan.id, name: `${loan.name} EMI`, amount: loan.emi, days: loan.next_emi_days_from_now, autopay: true, paid: false, to: "/app/accounts/sb" },
  ]
    .sort((a, b) => a.days - b.days);

  const maxCat = Math.max(1, ...spendNow.categories.slice(0, 5).map((c) => c.amount), ...spendNow.categories.slice(0, 5).map((c) => spendPrev.categories.find((x) => x.id === c.id)?.amount ?? 0));
  const delta = spendNow.total - spendPrev.total;

  return (
    <div className="ax-page ax-dash" data-stage-thing="screen:dashboard" data-stage-label="Dashboard">
      <header className="ax-dash__hello">
        <div>
          <h1>
            {greeting()}, {p.first_name}
          </h1>
          <p>
            {fmtDate(today())}. Your credit card bill of {inr(cardDue(billsPaid))} is due {inDays(st.due_days_from_now)}.
          </p>
        </div>
        <div className="ax-quick" data-stage-thing="quick-actions" data-stage-label="Quick actions">
          <Link to="/app/bills" className="ax-quick__btn">
            <Receipt size={18} /> Pay a bill
          </Link>
          <Link to="/app/payments" className="ax-quick__btn">
            <Send size={18} /> Transfer
          </Link>
          <Link to="/app/deposits" className="ax-quick__btn">
            <PiggyBank size={18} /> Book an FD
          </Link>
          <button type="button" className="ax-quick__btn ax-quick__btn--bad" onClick={() => askConfirm({ kind: "card_block", card: "debit" })} disabled={cards.debit.controls.blocked}>
            <Ban size={18} /> {cards.debit.controls.blocked ? "Debit card blocked" : "Block a card"}
          </button>
        </div>
      </header>

      <div className="ax-dash__grid">
        <div className="ax-col">
          <div className="ax-accts ax-o1" data-stage-thing="accounts" data-stage-group="" data-stage-label="Your accounts">
            {customer.accounts.map((a) => (
              <Link
                key={a.id}
                to={`/app/accounts/${a.id}`}
                className={`ax-acct ax-acct--${a.id}`}
                data-stage-thing={`account:${a.id}`}
                data-stage-label={a.id === "sb" ? "Savings balance" : "Current account balance"}
              >
                <div className="ax-acct__head">
                  <span>{a.name}</span>
                  <span className="ax-acct__no">{a.number_masked}</span>
                </div>
                <span className="ax-acct__k">Available balance</span>
                <Money n={balances[a.id]} className="ax-acct__bal" />
                <div className="ax-acct__foot">
                  <span>{a.id === "sb" ? `Interest ${a.rate}% a year` : a.holder.split(" (")[0]}</span>
                  <span className="ax-acct__go">
                    Details <ArrowUpRight size={14} />
                  </span>
                </div>
              </Link>
            ))}
          </div>

          <Panel
            title="Spending this month"
            className="ax-o6"
            thing="spend-month"
            label="Spending this month"
            action={
              <Link to="/app/insights" className="ax-link">
                Open insights
              </Link>
            }
          >
            <div className="ax-spendcmp">
              <div className="ax-spendcmp__totals">
                <div>
                  <span className="ax-k">{monthName(thisM)} so far</span>
                  <strong className="ax-fig">{inr(Math.round(spendNow.total))}</strong>
                </div>
                <div>
                  <span className="ax-k">{monthName(lastM)}</span>
                  <strong className="ax-fig ax-fig--muted">{inr(Math.round(spendPrev.total))}</strong>
                </div>
                <p className="ax-spendcmp__note">
                  {delta <= 0 ? `${inr(Math.round(-delta))} less than last month so far.` : `${inr(Math.round(delta))} more than all of last month.`} Savings and credit card, excluding transfers and investments.
                </p>
              </div>
              <div className="ax-spendcmp__bars" role="list">
                {spendNow.categories.slice(0, 5).map((c) => {
                  const prev = spendPrev.categories.find((x) => x.id === c.id)?.amount ?? 0;
                  return (
                    <div key={c.id} className="ax-spendcmp__row" role="listitem">
                      <span className="ax-spendcmp__name">{c.name}</span>
                      <div className="ax-spendcmp__track">
                        <span className="is-now" style={{ width: `${(c.amount / maxCat) * 100}%`, background: catColor(c.id) }} />
                        <span className="is-prev" style={{ width: `${(prev / maxCat) * 100}%` }} />
                      </div>
                      <span className="ax-spendcmp__amt">{inr(Math.round(c.amount))}</span>
                    </div>
                  );
                })}
                <div className="ax-legend">
                  <span>
                    <i className="is-now" /> This month
                  </span>
                  <span>
                    <i className="is-prev" /> Last month
                  </span>
                </div>
              </div>
            </div>
          </Panel>

          <Panel
            title="Recent transactions"
            className="ax-o7"
            pad={false}
            thing="recent-transactions"
            label="Recent transactions"
            action={
              <Link to="/app/transactions" className="ax-link">
                See all
              </Link>
            }
          >
            <ul className="ax-txlist">
              {recent.map((t) => (
                <li key={t.id} data-stage-thing={`txn:${t.id}`} data-stage-label={t.merchant}>
                  <Link to="/app/transactions" onClick={() => useBank.getState().openTxn(t.id)}>
                    <CatIcon id={t.category} />
                    <div className="ax-txlist__main">
                      <strong>{t.merchant}</strong>
                      <span>
                        {t.days_ago === 0 ? "Today" : t.days_ago === 1 ? "Yesterday" : fmtDate(daysFromNow(-t.days_ago))} <i>|</i> {ACCOUNT_LABEL[t.account]}
                      </span>
                    </div>
                    <CatChip id={t.category} />
                    <Amount t={t} />
                  </Link>
                </li>
              ))}
            </ul>
          </Panel>
        </div>

        <div className="ax-col">
          <Link to="/app/cards/credit" className="ax-cctile ax-o2" data-stage-thing="credit-card-tile" data-stage-label="Credit card">
            <div className="ax-cctile__row">
              <div>
                <span className="ax-k">{credit.name} •••• {credit.last4}</span>
                <span className="ax-k ax-k--sub">Outstanding</span>
                <strong className="ax-fig">{inr(cc.outstanding)}</strong>
              </div>
              <CardFace card="credit" small blocked={cards.credit.controls.blocked} />
            </div>
            <Meter value={cc.outstanding} max={credit.credit_limit!} tone="gold" />
            <div className="ax-cctile__nums">
              <div>
                <span className="ax-k">Available</span>
                <span>{inr(cc.available)}</span>
              </div>
              <div>
                <span className="ax-k">Total due</span>
                <span>{billsPaid["globalbank-card"] ? "Paid" : inr(st.total_due)}</span>
              </div>
              <div>
                <span className="ax-k">Min due</span>
                <span>{billsPaid["globalbank-card"] ? "Paid" : inr(st.min_due)}</span>
              </div>
            </div>
            {!billsPaid["globalbank-card"] && (
              <div className="ax-cctile__due">
                <CalendarClock size={15} /> Due {inDays(st.due_days_from_now)}, {fmtDate(daysFromNow(st.due_days_from_now))}
              </div>
            )}
          </Link>

          <Link to="/app/cards/debit" className="ax-dctile ax-o3" data-stage-thing="debit-card-tile" data-stage-label="Debit card">
            <CardFace card="debit" small blocked={cards.debit.controls.blocked} />
            <div>
              <strong>{debit.name}</strong>
              <span className="ax-k">
                •••• {debit.last4}, linked to savings
              </span>
              <span className={`ax-status ${cards.debit.controls.blocked ? "ax-status--bad" : "ax-status--ok"}`}>{cards.debit.controls.blocked ? "Blocked" : "Active"}</span>
              <span className="ax-k">International {cards.debit.controls.international ? "on" : "off"}</span>
            </div>
          </Link>

          <Panel title="Upcoming" className="ax-o4" thing="upcoming-dues" label="Upcoming dues" pad={false}>
            <ul className="ax-dues">
              {dues.map((d) => (
                <li key={d.key} data-stage-thing={`due:${d.key}`} data-stage-label={d.name}>
                  <Link to={d.to}>
                    <span className="ax-dues__date">
                      <strong>{daysFromNow(d.days).getDate()}</strong>
                      <span>{fmtDate(daysFromNow(d.days)).slice(3, 6)}</span>
                    </span>
                    <span className="ax-dues__main">
                      <strong>{d.name}</strong>
                      <span>{d.paid ? "Paid" : d.autopay ? "Autopay on" : `Due ${inDays(d.days)}`}</span>
                    </span>
                    <span className={`ax-dues__amt${d.paid ? " is-paid" : ""}`}>{d.paid ? "Paid" : inr(d.amount || 0)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </Panel>

          <div className="ax-offer ax-offer--loan ax-o5" data-stage-thing={`offer:${plOffer.id}`} data-stage-label="Pre-approved personal loan">
            <Sparkles size={18} className="ax-offer__icon" />
            {offersTaken[plOffer.id] ? (
              <>
                <strong>Personal loan credited</strong>
                <p>{inr(offersTaken[plOffer.id].amount ?? 0)} is in your savings account.</p>
              </>
            ) : (
              <>
                <span className="ax-offer__tag">Pre-approved for you</span>
                <strong>Personal loan up to {inr(plOffer.amount!)}</strong>
                <p>
                  At {plOffer.rate}% a year, up to {plOffer.tenure_max_months} months. Offer open till {fmtDate(daysFromNow(plOffer.valid_days_from_now ?? 0))}.
                </p>
                <div className="ax-offer__ctas">
                  <Link to="/app/offers" className="ax-btn ax-btn--gold ax-btn--sm">
                    See my offer
                  </Link>
                  <Link to="/loans/personal" className="ax-link">
                    About personal loans
                  </Link>
                </div>
              </>
            )}
          </div>

          <div className="ax-offer ax-offer--card ax-o5" data-stage-thing={`offer:${cardOffer.id}`} data-stage-label="Card upgrade" style={{ ["--card" as string]: voyage.color }}>
            <Plane size={18} className="ax-offer__icon" />
            <span className="ax-offer__tag">Card upgrade</span>
            <strong>{cardOffer.title}</strong>
            <p>{cardOffer.line}</p>
            <div className="ax-offer__ctas">
              <Link to={`/cards/${voyage.id}`} className="ax-btn ax-btn--light ax-btn--sm">
                See {voyage.name.replace("Global ", "")}
              </Link>
              <Link to="/app/offers" className="ax-link ax-link--light">
                All offers
              </Link>
            </div>
          </div>

          <div className="ax-loanmini ax-o8">
            <Landmark size={18} />
            <div>
              <strong>{loan.name}</strong>
              <span>
                {inr(loan.outstanding)} outstanding, {loan.months_left} EMIs of {inr(loan.emi)} left at {loan.rate}%
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function cardDue(paid: Record<string, unknown>) {
  return paid["globalbank-card"] ? 0 : cardById("credit")!.statement!.total_due;
}

