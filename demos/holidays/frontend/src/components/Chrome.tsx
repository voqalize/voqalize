import { Link, NavLink } from "react-router-dom";
import { Headphones, ShieldCheck } from "lucide-react";
import { PERSONA } from "../persona";
import { useTrip } from "../state/trip";
import { Logo } from "./Art";

export function Header() {
  const ready = useTrip((s) => !!s.trip.flight_id);
  return (
    <header className="site-header">
      <div className="wrap header-row">
        <Link to="/" className="brand" aria-label="Wanderloom Holidays, home">
          <Logo />
          <span className="brand-name">
            Wanderloom<span className="brand-sub">Holidays</span>
          </span>
        </Link>
        <nav className="main-nav" aria-label="Main">
          <NavLink to="/" end data-stage-thing="nav-home" data-stage-label="Destinations">
            Destinations
          </NavLink>
          <NavLink to="/plan" data-stage-thing="nav-plan" data-stage-label="Plan a trip">
            Plan a trip
          </NavLink>
          <NavLink to="/checkout" className={ready ? "" : "is-muted"} data-stage-thing="nav-checkout" data-stage-label="Checkout">
            Checkout
          </NavLink>
        </nav>
        <div className="header-meta">
          <span className="meta-chip">
            <Headphones size={14} /> {PERSONA.name}, {PERSONA.role.toLowerCase()}, on call
          </span>
        </div>
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="wrap footer-row">
        <div className="footer-brand">
          <Logo size={26} />
          <div>
            <strong>Wanderloom Holidays</strong>
            <p>Packages woven around you: flights, stays, transfers and days out, priced on one page.</p>
          </div>
        </div>
        <ul className="footer-points">
          <li>
            <ShieldCheck size={14} /> GST shown line by line, never folded in
          </li>
          <li>
            <ShieldCheck size={14} /> Fares include airport taxes
          </li>
          <li>
            <ShieldCheck size={14} /> Every item editable before you pay
          </li>
        </ul>
      </div>
      <p className="wrap fiction">
        Wanderloom is a fictional company. Airlines, hotels, experiences and prices on this site are invented for a demo.
      </p>
    </footer>
  );
}
