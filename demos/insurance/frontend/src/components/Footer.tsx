import { Link } from "react-router-dom";
import { PRODUCT_IDS, productById } from "../data";
import { HELPLINE } from "./Header";
import { Mark } from "./Logo";

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="wrap footer-grid">
        <div className="footer-brand">
          <span className="footer-logo">
            <Mark size={30} /> Chhatri Insurance
          </span>
          <p>Cover that opens when it rains. Car, two-wheeler, health, term life, home and travel insurance, explained in plain words.</p>
          <p className="footer-help">
            Claims helpline <strong>{HELPLINE}</strong>
          </p>
        </div>
        <div>
          <h2 className="footer-h">Insurance</h2>
          <ul>
            {PRODUCT_IDS.map((p) => (
              <li key={p}>
                <Link to={`/insurance/${p}`}>{productById(p)!.name}</Link>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h2 className="footer-h">Your account</h2>
          <ul>
            <li><Link to="/my-policies">My policies</Link></li>
            <li><Link to="/claim">Make a claim</Link></li>
            <li><Link to="/quote">Get a quote</Link></li>
          </ul>
        </div>
      </div>
      <div className="wrap footer-legal">
        <p>
          Chhatri Insurance is a fictional company built for a Voqalize demo. Products, premiums and policy wording are illustrative and not an offer of insurance.
        </p>
        <p className="footer-small">No real insurer, bank, hospital, garage, vehicle or person is represented. Premiums shown follow the demo’s own rating tables for 2026.</p>
      </div>
    </footer>
  );
}
