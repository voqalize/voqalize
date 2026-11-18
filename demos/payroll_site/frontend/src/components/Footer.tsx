import { Link } from "react-router-dom";
import { BRAND, MODULES, SITE } from "../data/product";
import { Logo } from "./Logo";

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="wrap footer-grid">
        <div className="footer-brand">
          <Logo />
          <p>{BRAND.one_liner}</p>
          <p className="footer-small">
            {BRAND.legal_name}, {BRAND.hq}. <a href={`mailto:${BRAND.sales_email}`}>{BRAND.sales_email}</a>
          </p>
        </div>
        <div>
          <h2 className="footer-h">Modules</h2>
          <ul>
            {MODULES.map((m) => (
              <li key={m.id}>
                <Link to={`/modules/${m.id}`}>{m.name}</Link>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h2 className="footer-h">Company</h2>
          <ul>
            {SITE.nav.map((n) => (
              <li key={n.path}>
                <Link to={n.path}>{n.label}</Link>
              </li>
            ))}
            <li>
              <Link to="/book-demo">Book a demo</Link>
            </li>
          </ul>
        </div>
      </div>
      <div className="wrap footer-note">
        <p>
          {BRAND.name} is a fictional company made for a Voqalize voice demo. Every company, person and number on this site is invented; tax figures are
          illustrative for FY 2025-26.
        </p>
      </div>
    </footer>
  );
}
