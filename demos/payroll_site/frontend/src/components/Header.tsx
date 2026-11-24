import { Menu, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { SITE } from "../data/product";
import { Logo } from "./Logo";

export function Header() {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => setOpen(false), [pathname]);
  return (
    <header className={`site-header${open ? " is-open" : ""}`}>
      <div className="wrap header-row">
        <Link to="/" className="header-logo" data-stage-thing="nav:/" data-stage-label="Home" aria-label="Paynora home">
          <Logo />
        </Link>
        <nav className="header-nav" aria-label="Main">
          {SITE.nav.map((n) => (
            <NavLink key={n.path} to={n.path} data-stage-thing={`nav:${n.path}`} data-stage-label={n.label}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <Link to="/book-demo" className="btn btn-primary header-cta" data-stage-thing="nav:/book-demo" data-stage-label="Book a demo">
          Book a demo
        </Link>
        <button type="button" className="header-menu" aria-expanded={open} aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen(!open)}>
          {open ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>
    </header>
  );
}
