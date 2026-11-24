import { FileText, Menu, Phone, ShieldCheck, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { PRODUCT_IDS, PRODUCT_SHORT, claimsGuide, customer } from "../data";
import { Logo } from "./Logo";

export const HELPLINE = claimsGuide?.helpline
  ? `${claimsGuide.helpline}${claimsGuide.helpline_note ? ` (${claimsGuide.helpline_note})` : ""}`
  : "1800 266 4242 (fictional number)";

export function Header() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname]);
  const initials = customer.name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2);
  return (
    <header className="site-header">
      <div className="topbar">
        <div className="wrap topbar-in">
          <span className="topbar-note">
            <ShieldCheck size={14} aria-hidden /> A fictional insurer, built for a Voqalize demo
          </span>
          <span className="topbar-help">
            <Phone size={13} aria-hidden /> Claims helpline <strong>{HELPLINE}</strong>
          </span>
        </div>
      </div>
      <div className="wrap nav">
        <Link to="/" className="nav-logo" data-stage-part="nav:home" aria-label="Chhatri Insurance, home">
          <Logo />
        </Link>
        <nav className={`nav-products${open ? " is-open" : ""}`} aria-label="Insurance" data-overlay={open ? "top" : undefined}>
          {PRODUCT_IDS.map((p) => (
            <NavLink key={p} to={`/insurance/${p}`} className="nav-link" data-stage-part={`nav:product:${p}`}>
              {PRODUCT_SHORT[p]}
            </NavLink>
          ))}
          <div className="nav-mobile-extra">
            <NavLink to="/quote" className="nav-link">Get a quote</NavLink>
            <NavLink to="/claim" className="nav-link">Make a claim</NavLink>
            <NavLink to="/my-policies" className="nav-link">My policies</NavLink>
          </div>
        </nav>
        <div className="nav-actions">
          <NavLink to="/claim" className="nav-action" data-stage-part="nav:claim">
            <FileText size={16} aria-hidden /> <span>Make a claim</span>
          </NavLink>
          <NavLink to="/quote" className="btn btn-primary btn-sm nav-quote" data-stage-part="nav:quote">
            Get a quote
          </NavLink>
          <NavLink to="/my-policies" className="nav-account" data-stage-part="nav:my-policies" aria-label={`My policies, signed in as ${customer.name}`}>
            <span className="avatar-chip" aria-hidden>{initials}</span>
            <span className="nav-account-text">
              <span className="nav-account-name">{customer.first_name}</span>
              <span className="nav-account-sub">My policies</span>
            </span>
          </NavLink>
          <button type="button" className="nav-menu" aria-expanded={open} aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen(!open)}>
            {open ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>
    </header>
  );
}
