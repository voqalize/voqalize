/**
 * Review and pay. The traveller's details are typed by the visitor, and the
 * Pay button is theirs: no move fills or presses anything here. The payment
 * is a mock; nothing is charged.
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Lock, Plane } from "lucide-react";
import { Breakdown, travellers } from "../components/Summary";
import { DestinationArt } from "../components/Art";
import { getDestination, getFlight, originName } from "../data";
import { day1, price, stays } from "../engine";
import { date, money, plural } from "../format";
import { pay, setStep, useTrip } from "../state/trip";

export function Checkout() {
  const trip = useTrip((s) => s.trip);
  const navigate = useNavigate();
  const [lead, setLead] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [method, setMethod] = useState<"upi" | "card">("upi");
  const [agree, setAgree] = useState(false);
  const d = getDestination(trip.brief.destination);
  const f = getFlight(trip.flight_id);
  const st = stays(trip);
  const complete = !!d && !!f && st.length > 0 && st.every((s) => trip.hotels[s.city.id]);
  const p = price(trip);
  const ok = complete && lead.trim().length > 1 && /^\S+@\S+\.\S+$/.test(email) && /^[0-9+ ]{10,14}$/.test(phone.trim()) && agree;

  if (!complete || !d) {
    return (
      <div className="wrap checkout empty" data-stage-place="checkout">
        <h1>Nothing to pay for yet</h1>
        <p className="muted">Choose a flight and a hotel in each city, then come back here.</p>
        <Link to="/plan" className="btn btn-primary" onClick={() => setStep("brief")}>
          Plan a trip
        </Link>
      </div>
    );
  }
  return (
    <div className="wrap checkout" data-stage-place="checkout">
      <Link to="/plan" className="back" onClick={() => setStep("package")}>
        <ArrowLeft size={15} /> Back to the package
      </Link>
      <h1>Review and pay</h1>
      <div className="checkout-grid">
        <div>
          <section className="card co-trip">
            <DestinationArt id={d.id} hue={d.hue} className="co-art" />
            <div>
              <h2>
                {d.name}, {plural(trip.brief.nights ?? 0, "night")}
              </h2>
              <p className="muted">
                From {originName(trip.brief.from_city)} · {travellers(trip)} · arriving {date(day1(trip))}
              </p>
              <p className="co-line">
                <Plane size={14} /> {f!.airline_name}, {f!.stops ? plural(f!.stops, "stop") : "nonstop"} · {f!.baggage}
              </p>
              <p className="co-line">{st.map((s) => `${s.city.name}: ${s.city.hotels.find((h) => h.id === trip.hotels[s.city.id].hotel_id)?.name} (${s.nights}N)`).join(" · ")}</p>
              <p className="co-line">{plural(trip.activities.length, "experience")} booked in</p>
            </div>
          </section>
          <section className="card">
            <h2>Lead traveller</h2>
            <p className="muted small">We send tickets and vouchers here. Type them yourself; the planner never fills these in.</p>
            <div className="form-grid">
              <label>
                Full name, as on passport
                <input value={lead} onChange={(e) => setLead(e.target.value)} autoComplete="name" />
              </label>
              <label>
                Email
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
              </label>
              <label>
                Mobile
                <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} autoComplete="tel" placeholder="+91 98xxx xxxxx" />
              </label>
            </div>
          </section>
          <section className="card">
            <h2>Payment</h2>
            <div className="pay-methods" role="radiogroup" aria-label="Payment method">
              <button type="button" role="radio" aria-checked={method === "upi"} className={`chip${method === "upi" ? " is-on" : ""}`} onClick={() => setMethod("upi")}>
                UPI
              </button>
              <button type="button" role="radio" aria-checked={method === "card"} className={`chip${method === "card" ? " is-on" : ""}`} onClick={() => setMethod("card")}>
                Card
              </button>
            </div>
            <p className="mock-note">
              <Lock size={13} /> This is a demo checkout. No money moves and no {method === "upi" ? "UPI app opens" : "card is charged"}.
            </p>
            <label className="agree">
              <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
              <span>I've checked the names, dates and the package, and I agree to Wanderloom's booking terms.</span>
            </label>
          </section>
        </div>
        <aside className="card co-pay">
          <h2>Price</h2>
          <Breakdown trip={trip} />
          <button
            type="button"
            className="btn btn-primary btn-block"
            disabled={!ok}
            data-stage-thing="checkout-pay"
            data-stage-label="Pay"
            data-dock-avoid
            onClick={() => {
              pay(lead.trim(), email.trim());
              navigate("/booked");
            }}
          >
            <Lock size={15} /> Pay {money(p.total)}
          </button>
          {!ok && <p className="muted small">Fill in the lead traveller and tick the box to pay.</p>}
        </aside>
      </div>
    </div>
  );
}
