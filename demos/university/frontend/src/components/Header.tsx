import { Menu, Phone, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { ADMISSIONS } from "../data/admissions";
import { nextRound } from "../data/catalogue";
import { Wordmark } from "./Logo";

const NAV: [string, string][] = [
  ["/programs", "Programmes"],
  ["/schools", "Schools"],
  ["/admissions", "Admissions"],
  ["/scholarships", "Scholarships"],
  ["/campus-life", "Campus life"],
];

export function Header() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname]);
  const ug = nextRound("ug-2027");
  return (
    <>
      <div className="utility">
        <div className="wrap utility-row">
          <p>
            Admissions 2027 are open.{" "}
            {ug ? (
              <span className="utility-deadline">
                Undergraduate {ug.name} closes {ug.deadline}.
              </span>
            ) : null}
          </p>
          <a href={`tel:${ADMISSIONS.contact.phone.replace(/\s/g, "")}`} className="utility-phone">
            <Phone size={13} /> {ADMISSIONS.contact.phone}
          </a>
        </div>
      </div>
      <header className="site-header">
        <div className="wrap header-row">
          <Link to="/" className="brand" aria-label="Varenya University home" data-nav="/">
            <Wordmark />
          </Link>
          <nav className={`main-nav${open ? " is-open" : ""}`} aria-label="Main">
            {NAV.map(([to, label]) => (
              <NavLink key={to} to={to} data-nav={to}>
                {label}
              </NavLink>
            ))}
            <Link to="/apply" className="btn btn-accent nav-apply" data-nav="/apply">
              Apply now
            </Link>
          </nav>
          <button type="button" className="menu-btn" aria-expanded={open} aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen(!open)}>
            {open ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>
      </header>
    </>
  );
}
