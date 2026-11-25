/** The footer on every page: the store's links, its policies in brief, and the dataset credit (required on every page). */
import { Link } from "react-router-dom";
import { useCatalog } from "../data/catalog";
import { POLICY, STORE } from "../data/shop";
import { LogoMark } from "./Logo";

export const KAGGLE_URL = "https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-dataset";
export const MIT_URL = "https://opensource.org/license/mit";

export function DatasetCredit() {
  return (
    <p className="credit">
      Product data and images:{" "}
      <a href={KAGGLE_URL} target="_blank" rel="noreferrer">
        Fashion Product Images Dataset
      </a>{" "}
      by Param Aggarwal (
      <a href={MIT_URL} target="_blank" rel="noreferrer">
        MIT
      </a>
      ), sourced from Myntra.
    </p>
  );
}

const NO_DEPTS: never[] = [];

export function Footer() {
  const departments = useCatalog((s) => s.index?.departments) ?? NO_DEPTS;
  return (
    <footer className="site-footer">
      <div className="wrap footer-grid">
        <div className="footer-brand">
          <p className="footer-logo">
            <LogoMark size={28} /> <span>Fashio</span>
          </p>
          <p className="footer-tag">{STORE.brand.tagline}.</p>
          <p className="footer-small">
            Help: {STORE.brand.support_phone}, {STORE.brand.support_hours}.
          </p>
        </div>
        <nav aria-label="Shop">
          <p className="footer-head">Shop</p>
          {departments.map((d) => (
            <Link key={d.id} to={`/shop/${d.id}`}>
              {d.label}
            </Link>
          ))}
          <Link to="/gifts">Gift finder</Link>
        </nav>
        <nav aria-label="Help">
          <p className="footer-head">Your orders</p>
          <Link to="/orders">Track an order</Link>
          <Link to="/returns">Return an item</Link>
          <Link to="/wishlist">Wishlist</Link>
          <Link to="/bag">Bag</Link>
          <Link to="/kiosk">In-store kiosk</Link>
          <Link to="/about">About Fashio</Link>
        </nav>
        <div>
          <p className="footer-head">Good to know</p>
          <p className="footer-small">{POLICY.delivery.summary}</p>
          <p className="footer-small">{POLICY.returns.summary}</p>
        </div>
      </div>
      <div className="wrap footer-legal">
        <DatasetCredit />
        <p className="credit">Fashio is a demo store; it is not Myntra and not affiliated with any brand shown.</p>
      </div>
    </footer>
  );
}
