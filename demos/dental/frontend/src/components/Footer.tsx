import { Link } from "react-router-dom";
import { CLINIC, DATA } from "../data/clinic";
import { actions } from "../state/store";
import { Mark } from "./Logo";

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="wrap footer-grid">
        <div>
          <p className="footer-brand">
            <Mark size={28} /> {CLINIC.name}
          </p>
          <p className="muted">{CLINIC.tagline}. Caring for Bengaluru smiles since {CLINIC.since}.</p>
          <p className="muted">
            Front desk {CLINIC.phone} · WhatsApp {CLINIC.whatsapp}
            <br />
            {CLINIC.email}
          </p>
        </div>
        {DATA.branches.map((b) => (
          <div key={b.id}>
            <p className="footer-head">{b.name}</p>
            <p className="muted">{b.address}</p>
            <p className="muted">
              Mon to Sat, {b.open} to {b.close} · {b.phone}
            </p>
          </div>
        ))}
        <div>
          <p className="footer-head">Patients</p>
          <ul className="footer-links">
            <li>
              <Link to="/book">Book an appointment</Link>
            </li>
            <li>
              <Link to="/my-appointments">My appointments</Link>
            </li>
            <li>
              <a href={`tel:${CLINIC.emergency_line.replace(/\s/g, "")}`}>Emergency line {CLINIC.emergency_line}</a>
            </li>
          </ul>
        </div>
      </div>
      <div className="wrap footer-base">
        <span>Dantika Dental Studio is a fictional clinic made for a Voqalize demo. Nothing here is medical advice.</span>
        <button
          type="button"
          className="link-btn"
          onClick={() => {
            actions.reset();
            window.scrollTo({ top: 0 });
          }}
        >
          Reset demo
        </button>
      </div>
    </footer>
  );
}
