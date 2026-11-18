import { CalendarDays, LogOut, Phone } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { CLINIC } from "../data/clinic";
import { navigate } from "../stage/nav";
import { actions, signedInPatient, useStore } from "../state/store";
import { Logo } from "./Logo";

/** Scroll to a home section, opening home first. */
export function goSection(id: string) {
  const jump = () => {
    const el = document.getElementById(id);
    if (!el) return false;
    const top = el.getBoundingClientRect().top + window.scrollY - 84;
    window.scrollTo({ top, behavior: "smooth" });
    return true;
  };
  if (window.location.pathname.replace(/\/+$/, "").endsWith("/dental") && jump()) return;
  navigate("/");
  let tries = 0;
  const t = window.setInterval(() => {
    if (jump() || ++tries > 30) window.clearInterval(t);
  }, 50);
}

const SECTIONS: [string, string][] = [
  ["services", "Services"],
  ["dentists", "Dentists"],
  ["visit-info", "Visit info"],
];

export function Header() {
  const { pathname } = useLocation();
  useStore((s) => s.signedIn);
  const me = signedInPatient();
  return (
    <header className="site-header">
      <div className="wrap header-row">
        <Link to="/" className="logo-link" data-nav="home" aria-label={`${CLINIC.name}, home`}>
          <Logo />
        </Link>
        <nav className="site-nav" aria-label="Main">
          {SECTIONS.map(([id, label]) => (
            <a
              key={id}
              href={`${import.meta.env.BASE_URL}#${id}`}
              data-nav-section={id}
              onClick={(e) => {
                e.preventDefault();
                goSection(id);
              }}
            >
              {label}
            </a>
          ))}
          <Link to="/book" data-nav="book" className={pathname.startsWith("/book") ? "is-on" : ""}>
            Book
          </Link>
          <Link to="/my-appointments" data-nav="my-appointments" className={pathname.startsWith("/my-appointments") ? "is-on" : ""}>
            My appointments
          </Link>
        </nav>
        <div className="header-end">
          <a className="header-phone" href={`tel:${CLINIC.phone.replace(/\s/g, "")}`}>
            <Phone size={15} aria-hidden /> {CLINIC.phone}
          </a>
          {me ? (
            <span className="me-chip" title={`${me.name}, ${me.id}`}>
              <span className="me-dot" aria-hidden>
                {me.name.split(" ").map((w) => w[0]).slice(0, 2).join("")}
              </span>
              <span className="me-name">{me.name.split(" ")[0]}</span>
              <button type="button" className="icon-btn" aria-label="Sign out" onClick={() => actions.signOut()}>
                <LogOut size={14} />
              </button>
            </span>
          ) : (
            <Link to="/book" className="btn btn-primary btn-sm header-book">
              <CalendarDays size={15} aria-hidden /> Book a visit
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
