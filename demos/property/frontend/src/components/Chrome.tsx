/** The site's frame: logo, header, footer. */
import { Heart, CalendarCheck, Scale, Menu, X } from "lucide-react";
import { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { BRAND, CITIES } from "../data/homes";
import { useStore } from "../state/store";

/** Kosha Homes' mark: a roof over a seed (kosha, a sheath that holds). */
export function Logo({ small }: { small?: boolean }) {
  return (
    <span className={`logo${small ? " is-small" : ""}`}>
      <svg viewBox="0 0 40 40" aria-hidden="true" className="logo-mark">
        <rect width="40" height="40" rx="10" fill="var(--forest)" />
        <path d="M8 21 L20 10 L32 21" fill="none" stroke="#f3e9d8" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M20 31 C 13 27 13 20 20 16 C 27 20 27 27 20 31 Z" fill="var(--accent-soft)" />
        <path d="M20 31 V 20" stroke="var(--forest)" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
      <span className="logo-word">
        Kosha<span>Homes</span>
      </span>
    </span>
  );
}

export function Header() {
  const shortlist = useStore((s) => s.shortlist.length);
  const visits = useStore((s) => s.bookings.length);
  const compare = useStore((s) => s.compare);
  const [open, setOpen] = useState(false);
  const nav = (
    <>
      <NavLink to="/listings" data-stage-thing="nav:/listings" onClick={() => setOpen(false)}>
        Find a home
      </NavLink>
      {useProjectsLink(() => setOpen(false))}
      <NavLink to={`/compare${compare.length ? `?ids=${compare.join(",")}` : ""}`} data-stage-thing="nav:/compare" onClick={() => setOpen(false)}>
        <Scale size={15} /> Compare{compare.length ? <b className="pill">{compare.length}</b> : null}
      </NavLink>
      <NavLink to="/shortlist" data-stage-thing="nav:/shortlist" onClick={() => setOpen(false)}>
        <Heart size={15} /> Shortlist{shortlist ? <b className="pill">{shortlist}</b> : null}
      </NavLink>
      <NavLink to="/visits" data-stage-thing="nav:/visits" onClick={() => setOpen(false)}>
        <CalendarCheck size={15} /> My visits{visits ? <b className="pill">{visits}</b> : null}
      </NavLink>
    </>
  );
  return (
    <header className="site-header">
      <div className="wrap header-row">
        <Link to="/" data-stage-thing="nav:/" aria-label={`${BRAND.name} home`}>
          <Logo />
        </Link>
        <nav className="header-nav" aria-label="Main">
          {nav}
        </nav>
        <span className="header-help">
          Helpline <b>{BRAND.helpline}</b>
        </span>
        <button type="button" className="header-burger" aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen(!open)}>
          {open ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>
      {open ? <nav className="header-sheet" aria-label="Main">{nav}</nav> : null}
    </header>
  );
}

function useProjectsLink(close: () => void) {
  return (
    <Link to="/#projects" onClick={close}>
      Projects
    </Link>
  );
}

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="wrap footer-grid">
        <div>
          <Logo small />
          <p className="footer-tag">{BRAND.tagline}</p>
          <p className="footer-meta">
            Building since {BRAND.since} · {BRAND.helpline} · {BRAND.email}
          </p>
        </div>
        <div>
          <h4>Cities</h4>
          {CITIES.map((c) => (
            <p key={c.id}>
              <Link to={`/listings?city=${c.id}`}>Homes in {c.name}</Link>
            </p>
          ))}
        </div>
        <div>
          <h4>{BRAND.exchange}</h4>
          <p>
            <Link to="/listings?deal=buy">Homes to buy</Link>
          </p>
          <p>
            <Link to="/listings?deal=rent">Homes for rent</Link>
          </p>
          <p>
            <Link to="/visits">My site visits</Link>
          </p>
        </div>
      </div>
      <div className="wrap footer-legal">
        <p>{BRAND.disclaimer}</p>
        <p>Registration numbers marked DEMO are invented and follow no real authority's format. Prices are indicative and exclude stamp duty, registration and GST.</p>
      </div>
    </footer>
  );
}
