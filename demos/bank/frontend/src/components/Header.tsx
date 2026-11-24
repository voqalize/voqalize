import { LogOut, Menu, Phone, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { brand, customer } from "../data/bank";
import { useSession } from "../state/session";
import { Logo } from "./Logo";

const NAV = [
  { to: "/open-account", label: "Accounts", match: ["/open-account"] },
  { to: "/cards", label: "Cards", match: ["/cards"] },
  { to: "/loans", label: "Loans", match: ["/loans"] },
  { to: "/app/deposits", label: "Deposits", match: ["/app/deposits"] },
];

export function Header() {
  const signedIn = useSession((s) => s.signedIn);
  const signOut = useSession((s) => s.signOut);
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname]);

  return (
    <>
      <div className="util-bar">
        <div className="wrap util-inner">
          <p className="util-note">A fictional bank, built for a voice demo. Every figure is sample data.</p>
          <p className="util-help">
            <Phone size={13} aria-hidden /> Helpline <a href={`tel:${brand.helpline.replace(/\s/g, "")}`}>{brand.helpline}</a>
          </p>
        </div>
      </div>
      <header className={`site-header${open ? " is-open" : ""}`}>
        <div className="wrap header-inner">
          <Link to="/" className="header-logo" aria-label={`${brand.name} home`}>
            <Logo />
          </Link>
          <nav className="header-nav" aria-label="Main">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                className={() => `nav-link${n.match.some((m) => location.pathname.startsWith(m)) ? " is-active" : ""}`}
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="header-actions">
            {signedIn ? (
              <>
                <Link to="/app" className="btn btn-primary btn-sm header-mybank">
                  <span className="avatar-dot" aria-hidden>
                    {customer.profile.first_name.slice(0, 1)}
                  </span>
                  My banking <span className="header-name">· {customer.profile.first_name}</span>
                </Link>
                <button type="button" className="icon-btn header-signout" aria-label="Sign out" title="Sign out" onClick={signOut}>
                  <LogOut size={17} />
                </button>
              </>
            ) : (
              <Link to="/login" className="btn btn-primary btn-sm">
                Sign in
              </Link>
            )}
            <button type="button" className="icon-btn header-menu" aria-expanded={open} aria-controls="mobile-nav" aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen(!open)}>
              {open ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>
        <nav id="mobile-nav" className="mobile-nav" aria-label="Main" hidden={!open}>
          {NAV.map((n) => (
            <Link key={n.to} to={n.to} className="mobile-link">
              {n.label}
            </Link>
          ))}
          {signedIn ? (
            <button type="button" className="mobile-link" onClick={signOut}>
              Sign out
            </button>
          ) : null}
        </nav>
      </header>
    </>
  );
}
