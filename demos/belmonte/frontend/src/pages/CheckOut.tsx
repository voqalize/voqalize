/**
 * Check-out: the folio by date (tap a line for its detail and to question
 * it), late check-out, and express check-out. Requesting late check-out and
 * checking out are the guest's own presses.
 */
import { Check, ChevronDown, Clock, LogOut, Mail } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader, Pill, Segments } from "../components/Shell";
import { type FolioLine, GUEST, HOTEL, LATE } from "../data";
import { day, money } from "../lib/format";
import { type State, balance, expressCheckout, folio, openDispute, pickLate, requestLate, setCheckoutPart, stayClock, useStay } from "../state/store";
import "../styles/stay.css";

const hhmmId = (id: string) => id.replace(":", "");

function BalanceBlock({ s }: { s: State }) {
  const lines = folio(s).filter((l) => !(l.id in s.disputes));
  const charges = lines.filter((l) => l.amount > 0).reduce((a, l) => a + l.amount, 0);
  const paid = lines.filter((l) => l.amount < 0).reduce((a, l) => a + l.amount, 0);
  const b = balance(s);
  return (
    <div className="st-balance" data-stage-thing="balance" data-stage-label={`Balance ${money(b)}`}>
      <div>
        <span className="st-label">{b < 0 ? "Credit" : "Balance due"}</span>
        <b>{money(b)}</b>
      </div>
      <div className="st-balance-side">
        Charges {money(charges)}
        <br />
        Payments {money(paid)}
      </div>
    </div>
  );
}

function Folio({ s }: { s: State }) {
  const [open, setOpen] = useState<string | null>(null);
  const lines = folio(s);
  const dates = [...new Set(lines.map((l) => l.date))].sort();
  const row = (l: FolioLine) => {
    const disputed = l.id in s.disputes;
    const isOpen = open === l.id;
    return (
      <div key={l.id} className={`st-line${isOpen ? " is-open" : ""}${disputed ? " is-disputed" : ""}`}>
        <button type="button" className="st-line-btn" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : l.id)} data-stage-thing={`line-${l.id}`} data-stage-label={l.label}>
          <span className="st-line-label">
            <span>{l.label}</span>
            <small>{l.amount < 0 ? "Payment" : l.category}</small>
          </span>
          {disputed ? <Pill tone="coral">Under review</Pill> : null}
          <span className={`st-line-amt${l.amount < 0 ? " is-credit" : ""}`}>{l.amount < 0 ? `−${money(-l.amount)}` : money(l.amount)}</span>
          <ChevronDown size={16} className="st-line-chev" />
        </button>
        {isOpen ? (
          <div className="st-line-detail">
            <span>{l.detail}</span>
            {disputed ? (
              <span className="st-review-note">Under review: “{s.disputes[l.id]}”. It is held off your balance until the front office replies.</span>
            ) : l.amount > 0 && !s.checkedOut ? (
              <button type="button" className="st-btn is-ghost is-small" onClick={() => openDispute(l.id)} data-stage-thing={`dispute-${l.id}`} data-stage-label="Question this charge">
                Question this charge
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  };
  return (
    <>
      <BalanceBlock s={s} />
      <div className="st-card is-flush">
        {dates.map((d) => {
          const ls = lines.filter((l) => l.date === d);
          const sum = ls.filter((l) => !(l.id in s.disputes)).reduce((a, l) => a + l.amount, 0);
          return (
            <div key={d}>
              <div className="st-day-head">
                <span className="st-label">{day(d)}</span>
                <span className="st-label">{money(sum)}</span>
              </div>
              {ls.map(row)}
            </div>
          );
        })}
      </div>
      <p className="st-note">Tap a charge to see what it was for. Anything you question is held off the balance while the front office reviews it.</p>
    </>
  );
}

function Late({ s }: { s: State }) {
  const c = stayClock();
  const pick = LATE.options.find((o) => o.id === s.latePick) ?? null;
  const requested = LATE.options.find((o) => o.id === s.lateRequested) ?? null;
  const blocked = s.checkedOut ? "You've checked out." : requested ? null : !pick ? "Choose a time." : null;
  return (
    <>
      <div className="st-card">
        <div className="st-card-head">
          <div>
            <span className="st-label">Standard check-out</span>
            <h3 style={{ marginTop: 4 }}>
              {HOTEL.check_out_time}, {day(c.depart)}
            </h3>
          </div>
          <Clock size={22} color="var(--brass)" />
        </div>
        <p className="st-note">{LATE.rule}</p>
      </div>
      {requested ? (
        <div className="st-card" data-stage-thing="late-requested" data-stage-label={`Late check-out until ${requested.label}`}>
          <div className="st-done" style={{ padding: "6px 0 0" }}>
            <span className="st-done-mark">
              <Check size={26} />
            </span>
            <h2 style={{ fontSize: 22 }}>Late check-out until {requested.label}</h2>
            <p>{requested.fee ? `${money(requested.fee)} on your room bill.` : "Complimentary."} The front desk confirms within about 15 minutes.</p>
          </div>
        </div>
      ) : (
        <>
          <section className="st-section" data-stage-thing="late" data-stage-label="Late check-out times" data-stage-group>
            <span className="st-label">Stay until</span>
            <div className="st-options" role="radiogroup" aria-label="Late check-out">
              {LATE.options.map((o) => (
                <button
                  key={o.id}
                  type="button"
                  role="radio"
                  aria-checked={s.latePick === o.id}
                  className="st-option"
                  disabled={!o.available || s.checkedOut}
                  onClick={() => pickLate(o.id)}
                  data-stage-thing={`late-${hhmmId(o.id)}`}
                  data-stage-label={o.label}
                >
                  <span className="st-radio" />
                  <span className="st-option-text">
                    <span>{o.label}</span>
                    {o.note ? <small>{o.note}</small> : null}
                  </span>
                  <span className={`st-option-side${o.available && !o.fee ? " is-free" : ""}`}>{!o.available ? "Unavailable" : o.fee ? money(o.fee) : "Complimentary"}</span>
                </button>
              ))}
            </div>
          </section>
          <div className="st-final">
            <div className="st-pay">
              <span>{pick ? `Late check-out, ${pick.label}` : "Late check-out fee"}</span>
              <b>{pick ? (pick.fee ? money(pick.fee) : "Complimentary") : "—"}</b>
            </div>
            <button type="button" className="st-btn is-block" disabled={!!blocked} onClick={requestLate} data-stage-thing="late-request" data-stage-label="Request late check-out" data-dock-avoid data-guest-only>
              Request late check-out
            </button>
            {blocked ? <p className="st-reason">{blocked}</p> : null}
          </div>
        </>
      )}
    </>
  );
}

function Express({ s }: { s: State }) {
  const c = stayClock();
  const b = balance(s);
  const disputed = Object.keys(s.disputes).length;
  if (s.checkedOut)
    return (
      <div className="st-thanks" data-stage-thing="checkout-done" data-stage-label="Checked out">
        <span className="st-label" style={{ color: "#fff3d6" }}>
          Checked out
        </span>
        <h2>Thank you, {GUEST.first_name}</h2>
        <p>
          {money(b)} was charged to your {GUEST.card}. Your receipt is on its way to {GUEST.email}. Safe travels.
        </p>
        <Link to="/" className="st-btn is-light is-small" style={{ marginTop: 6 }}>
          Back to home
        </Link>
      </div>
    );
  const blocked = !s.checkedIn ? "You're not checked in yet." : null;
  return (
    <>
      <div className="st-card" data-stage-thing="express-review" data-stage-label="Express check-out summary">
        <dl className="st-rows">
          <div className="st-row">
            <dt>Room</dt>
            <dd>{s.room ?? "Not assigned"}</dd>
          </div>
          <div className="st-row">
            <dt>Departure</dt>
            <dd>
              {day(c.depart)}, by {s.lateRequested ? (LATE.options.find((o) => o.id === s.lateRequested)?.label ?? HOTEL.check_out_time) : HOTEL.check_out_time}
            </dd>
          </div>
          <div className="st-row">
            <dt>Charged to</dt>
            <dd>{GUEST.card}</dd>
          </div>
          <div className="st-row">
            <dt>Receipt to</dt>
            <dd>{GUEST.email}</dd>
          </div>
          {disputed ? (
            <div className="st-row">
              <dt>Under review</dt>
              <dd>
                {disputed} {disputed === 1 ? "charge" : "charges"}, held off
              </dd>
            </div>
          ) : null}
          <div className="st-row is-total">
            <dt>Balance</dt>
            <dd>{money(b)}</dd>
          </div>
        </dl>
      </div>
      <p className="st-note">
        <Mail size={13} style={{ verticalAlign: -2, marginRight: 4 }} />
        Your final bill is emailed to you and your digital key stops working.
      </p>
      <div className="st-final">
        <div className="st-pay">
          <span>Charge to {GUEST.card}</span>
          <b>{money(b)}</b>
        </div>
        <button type="button" className="st-btn is-block is-brass" disabled={!!blocked} onClick={expressCheckout} data-stage-thing="express-checkout" data-stage-label="Check out now" data-dock-avoid data-guest-only>
          <LogOut size={18} /> Check out now
        </button>
        {blocked ? <p className="st-reason">{blocked}</p> : null}
      </div>
    </>
  );
}

export function CheckOut() {
  const s = useStay();
  return (
    <div className="page st-page" data-stage-place="checkout">
      <PageHeader
        title="Check out"
        sub={s.room ? `Room ${s.room} · ${day(stayClock().depart)}` : day(stayClock().depart)}
        back="/stay"
        tabs={
          <Segments
            items={[
              { id: "folio", label: "Your bill", thing: "checkout-folio" },
              { id: "late", label: "Late check-out", thing: "checkout-late" },
              { id: "express", label: "Check out", thing: "checkout-express" },
            ]}
            value={s.checkoutPart}
            onChange={(id) => setCheckoutPart(id as State["checkoutPart"])}
          />
        }
      />
      <div className="st-body">
        {s.checkoutPart === "folio" ? <Folio s={s} /> : null}
        {s.checkoutPart === "late" ? <Late s={s} /> : null}
        {s.checkoutPart === "express" ? <Express s={s} /> : null}
      </div>
    </div>
  );
}
