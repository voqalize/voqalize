/**
 * Stay: the reservation, the key once checked in, the bill so far, check in
 * and check out, hotel information, and the demo's scenario switch.
 */
import { BedDouble, ChevronRight, Clock, Dog, Info as InfoIcon, LogIn, LogOut, Phone, Wifi } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { ScenarioSwitch } from "../App";
import { PageHeader, Pill } from "../components/Shell";
import { GUEST, HOTEL } from "../data";
import { day, money, nightsBetween } from "../lib/format";
import { balance, folio, openInfo, stayClock, useStay } from "../state/store";
import { KeyCard, WifiCard } from "./Home";
import "../styles/stay.css";

/** The reservation: number, room type, dates, nights, guests, rate, tier. */
export function ReservationCard() {
  const scenario = useStay((s) => s.scenario);
  void scenario;
  const c = stayClock();
  const nights = nightsBetween(c.arrive, c.depart);
  return (
    <div className="st-card is-flush" data-stage-thing="reservation" data-stage-label={`Reservation ${GUEST.reservation}`}>
      <div className="st-res-top">
        <div>
          <span className="st-label">Reservation {GUEST.reservation}</span>
          <h3>{GUEST.room_type}</h3>
        </div>
        <Pill tone="brass">Gold</Pill>
      </div>
      <div className="st-dates">
        <div>
          <small>Check-in</small>
          <b>{day(c.arrive)}</b>
          <small>from {HOTEL.check_in_time}</small>
        </div>
        <span className="st-nights">
          {nights} {nights === 1 ? "night" : "nights"}
        </span>
        <div>
          <small>Check-out</small>
          <b>{day(c.depart)}</b>
          <small>by {HOTEL.check_out_time}</small>
        </div>
      </div>
      <dl className="st-rows st-res-rows">
        <div className="st-row">
          <dt>Guests</dt>
          <dd>
            {GUEST.adults} adults: {GUEST.first_name} and {GUEST.companions.join(", ")}
          </dd>
        </div>
        <div className="st-row">
          <dt>Rate</dt>
          <dd>{money(GUEST.rate)} a night</dd>
        </div>
        <div className="st-row">
          <dt>Member</dt>
          <dd>{GUEST.member}</dd>
        </div>
        <div className="st-row">
          <dt>Card on file</dt>
          <dd>{GUEST.card}</dd>
        </div>
      </dl>
    </div>
  );
}

const INFO_LINKS = [
  { id: "checkin", label: "Check-in and check-out", icon: Clock },
  { id: "wifi", label: "Wi-Fi", icon: Wifi },
  { id: "pets", label: "Pet policy", icon: Dog },
  { id: "contact", label: "Contact the front desk", icon: Phone },
];

export function Stay() {
  const s = useStay();
  const nav = useNavigate();
  const lines = folio(s);
  const disputed = Object.keys(s.disputes).length;
  const toInfo = (id: string | null) => {
    openInfo(id);
    nav("/info");
  };

  return (
    <div className="page st-page" data-stage-place="stay">
      <PageHeader title="Your stay" sub={s.checkedOut ? "Checked out" : s.checkedIn ? `Room ${s.room}` : "Not checked in yet"} />
      <div className="st-body">
        <ReservationCard />

        {s.checkedIn && s.room ? <KeyCard /> : null}

        <div className="st-btn-row">
          <Link
            to="/stay/check-in"
            className={`st-btn${s.checkedIn ? " is-ghost" : ""}`}
            data-stage-thing="stay-checkin"
            data-stage-label="Check in"
          >
            <LogIn size={17} /> {s.checkedIn ? "Checked in" : "Check in"}
          </Link>
          <Link to="/stay/check-out" className={`st-btn${s.checkedIn && !s.checkedOut ? "" : " is-ghost"}`} data-stage-thing="stay-checkout" data-stage-label="Check out">
            <LogOut size={17} /> {s.checkedOut ? "Checked out" : "Check out"}
          </Link>
        </div>

        <section className="st-section">
          <div className="st-section-head">
            <h2>Your bill</h2>
            <Link to="/stay/check-out">See every charge</Link>
          </div>
          <div className="st-card" data-stage-thing="folio-summary" data-stage-label="Your bill">
            <div className="st-folio-sum">
              <div>
                <span className="st-label">{balance(s) < 0 ? "Credit" : "Balance"}</span>
                <b>{money(balance(s))}</b>
              </div>
              <Link to="/stay/check-out" className="st-btn is-ghost is-small">
                Review <ChevronRight size={15} />
              </Link>
            </div>
            <p className="st-note" style={{ marginTop: 10 }}>
              {lines.length} {lines.length === 1 ? "entry" : "entries"} on your folio
              {disputed ? `, ${disputed} under review` : ""}. Charged to {GUEST.card} at check-out.
            </p>
          </div>
        </section>

        {s.checkedIn && !s.checkedOut ? <WifiCard /> : null}

        <section className="st-section">
          <div className="st-section-head">
            <h2>Hotel information</h2>
            <button type="button" onClick={() => toInfo(null)}>
              All
            </button>
          </div>
          <div className="st-card is-flush st-links">
            {INFO_LINKS.map((l) => {
              const Icon = l.icon;
              return (
                <button key={l.id} type="button" className="st-link" onClick={() => toInfo(l.id)}>
                  <Icon size={18} />
                  <span>{l.label}</span>
                  <ChevronRight size={17} />
                </button>
              );
            })}
            <Link to="/info" className="st-link" data-stage-thing="stay-info" data-stage-label="Hotel information">
              <InfoIcon size={18} />
              <span>Pools, dining hours, parking and more</span>
              <ChevronRight size={17} />
            </Link>
          </div>
        </section>

        <section className="st-section">
          <div className="st-section-head">
            <span className="st-label">
              <BedDouble size={13} style={{ verticalAlign: -2, marginRight: 6 }} />
              Demo scenario
            </span>
          </div>
          <div className="st-card st-scenario">
            <ScenarioSwitch />
          </div>
        </section>
      </div>
    </div>
  );
}
