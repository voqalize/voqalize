import { CheckCircle2, Plane } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { offerTenureDefault } from "../../app/actions";
import { askConfirm } from "../../app/ConfirmSheet";
import { cardById, creditCardProduct, customer, daysFromNow, fmtDate, inr, loanProduct } from "../../data/bank";
import { emi } from "../../lib/bankmath";
import { useBank } from "../../state/bank";
import { CardFace, PageHead } from "./ui";

export function Offers() {
  const taken = useBank((s) => s.offers);
  const loanOffer = customer.offers.find((o) => o.kind === "loan")!;
  const cardOffer = customer.offers.find((o) => o.kind === "card")!;
  const loan = loanProduct("personal")!;
  const voyage = creditCardProduct(cardOffer.card_id!)!;
  const current = creditCardProduct(cardById("credit")!.product_id!)!;
  const max = loanOffer.amount!;
  const [amount, setAmount] = useState(max);
  const tenures = [12, 24, 36, 48, 60].filter((t) => t <= loanOffer.tenure_max_months! && t >= loan.tenure_min_months);
  const [tenure, setTenure] = useState(offerTenureDefault(loanOffer.tenure_max_months!));
  const m = Math.round(emi(amount, loanOffer.rate!, tenure));
  const done = taken[loanOffer.id];
  const upgraded = taken[cardOffer.id];

  return (
    <div className="ax-page" data-stage-thing="screen:offers" data-stage-label="Offers">
      <PageHead title="Offers for you" sub="Worked out from your accounts and card spends. Nothing is applied until you confirm." />

      <section className="ax-bigoffer" data-stage-thing={`offer:${loanOffer.id}`} data-stage-label="Pre-approved personal loan">
        <div className="ax-bigoffer__copy">
          <span className="ax-offer__tag">Pre-approved</span>
          <h2>{loanOffer.title}</h2>
          <p>{loanOffer.line}</p>
          <ul className="ax-facts">
            <li>
              <span className="ax-k">Up to</span>
              <strong>{inr(max)}</strong>
            </li>
            <li>
              <span className="ax-k">Rate</span>
              <strong>{loanOffer.rate}% a year</strong>
            </li>
            <li>
              <span className="ax-k">Tenure</span>
              <strong>up to {loanOffer.tenure_max_months} months</strong>
            </li>
            <li>
              <span className="ax-k">Open till</span>
              <strong>{fmtDate(daysFromNow(loanOffer.valid_days_from_now ?? 0))}</strong>
            </li>
          </ul>
          <Link to="/loans/personal" className="ax-link ax-link--light">
            Personal loan details and documents
          </Link>
        </div>

        {done ? (
          <div className="ax-bigoffer__panel ax-bigoffer__done" data-stage-thing="offer-credited" data-stage-label="Loan credited">
            <CheckCircle2 size={30} />
            <strong className="ax-fig">{inr(done.amount ?? 0)} credited to savings</strong>
            <span>
              {done.tenure_months} EMIs of {inr(done.emi ?? 0)} at {loanOffer.rate}%.
            </span>
            <span className="ax-k">Reference {done.reference}</span>
            <Link to="/app/accounts/sb" className="ax-btn ax-btn--light ax-btn--sm">
              See savings account
            </Link>
          </div>
        ) : (
          <div className="ax-bigoffer__panel" data-stage-thing="offer-calculator" data-stage-label="Loan amount and EMI">
            <label className="ax-field">
              <span>
                Amount <strong>{inr(amount)}</strong>
              </span>
              <input
                type="range"
                min={loan.amount_min}
                max={max}
                step={10000}
                value={amount}
                onChange={(e) => setAmount(Number(e.target.value))}
                style={{ ["--fill" as string]: `${((amount - loan.amount_min) / (max - loan.amount_min)) * 100}%` }}
              />
              <span className="ax-range-ends">
                <span>{inr(loan.amount_min)}</span>
                <span>{inr(max)}</span>
              </span>
            </label>
            <div className="ax-field">
              <span>Tenure</span>
              <div className="ax-seg ax-seg--full" role="radiogroup" aria-label="Tenure">
                {tenures.map((t) => (
                  <button key={t} type="button" role="radio" aria-checked={tenure === t} className={tenure === t ? "is-on" : ""} onClick={() => setTenure(t)}>
                    {t}m
                  </button>
                ))}
              </div>
            </div>
            <div className="ax-emiout">
              <span className="ax-k">Monthly EMI</span>
              <strong className="ax-fig ax-fig--xl">{inr(m)}</strong>
              <span className="ax-k">Total interest {inr(m * tenure - amount)}</span>
            </div>
            <button type="button" className="ax-btn ax-btn--gold" onClick={() => askConfirm({ kind: "offer_accept", target: loanOffer.id, amount, tenure_months: tenure })}>
              Get {inr(amount)} now
            </button>
          </div>
        )}
      </section>

      <section className="ax-upgrade" data-stage-thing={`offer:${cardOffer.id}`} data-stage-label="Card upgrade" style={{ ["--card" as string]: voyage.color }}>
        <div className="ax-upgrade__cards">
          <CardFace color={current.color} name={current.name} network={current.network} last4={cardById("credit")!.last4} expiry={cardById("credit")!.expiry} small />
          <CardFace color={voyage.color} name={voyage.name} network={voyage.network} last4="••••" expiry="--/--" />
        </div>
        <div className="ax-upgrade__copy">
          <span className="ax-offer__tag ax-offer__tag--dark">
            <Plane size={13} /> Card upgrade
          </span>
          <h2>{cardOffer.title}</h2>
          <p>{cardOffer.line}</p>
          <ul className="ax-ticks">
            {voyage.highlights.slice(0, 4).map((h) => (
              <li key={h}>
                <CheckCircle2 size={16} /> {h}
              </li>
            ))}
          </ul>
          <p className="ax-k">
            Annual fee {inr(voyage.annual_fee)}, waived when you spend {inr(voyage.fee_waiver_spend)} in a year.
          </p>
          {upgraded ? (
            <div className="ax-paidline">Upgrade requested. Reference {upgraded.reference}</div>
          ) : (
            <div className="ax-offer__ctas">
              <Link to={`/cards/apply?card=${voyage.id}`} className="ax-btn ax-btn--primary">
                Apply for {voyage.name.replace("Anvaya ", "")}
              </Link>
              <Link to={`/cards/${voyage.id}`} className="ax-btn ax-btn--ghost">
                See card details
              </Link>
              <Link to="/cards/compare" className="ax-link">
                Compare with my card
              </Link>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
