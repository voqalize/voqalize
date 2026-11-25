/**
 * The store's header: the logo, the departments with a mega menu each
 * (sections and types from the catalogue's `departments`), Gifts, the search
 * box, and the wishlist and bag with their counts (the bag pulses on an add).
 * On a phone the departments live in a left drawer (`data-overlay="left"`).
 * Links carry `data-stage-thing="nav:<path>"` so `site.go` can ring them.
 */
import { Gift, Heart, Menu, Package, Search, ShoppingBag, X } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { type Department, typeLabel, useCatalog } from "../data/catalog";
import { POLICY } from "../data/shop";
import { useStore } from "../state/store";
import { Logo } from "./Logo";

const NO_DEPTS: Department[] = [];

export function Header() {
  const departments = useCatalog((s) => s.index?.departments) ?? NO_DEPTS;
  const wish = useStore((s) => s.wishlist.length);
  const bagCount = useStore((s) => s.bag.reduce((t, l) => t + l.qty, 0));
  const pulse = useStore((s) => s.bagPulse);
  const [open, setOpen] = useState<string | null>(null);
  const [drawer, setDrawer] = useState(false);
  const location = useLocation();
  useEffect(() => {
    setOpen(null);
    setDrawer(false);
  }, [location.pathname, location.search]);

  return (
    <header className="site-header" onMouseLeave={() => setOpen(null)}>
      <div className="header-strip">
        <div className="wrap strip-row">
          <span>Free delivery on orders over ₹{POLICY.delivery.free_over}</span>
          <span>{POLICY.returns.window_days}-day returns</span>
          <span className="hide-phone">Cash on delivery</span>
          <Link to="/orders" className="strip-link hide-phone" data-stage-thing="nav:/orders">
            Track an order
          </Link>
        </div>
      </div>
      <div className="wrap header-row">
        <button type="button" className="icon-btn only-phone" aria-label="Open the menu" onClick={() => setDrawer(true)}>
          <Menu size={22} />
        </button>
        <Link to="/" className="header-logo" aria-label="Fashio home" data-stage-thing="nav:/">
          <Logo />
        </Link>
        <nav className="header-nav" aria-label="Departments">
          {departments.map((d) => (
            <div key={d.id} className={`nav-item${open === d.id ? " is-open" : ""}`} onMouseEnter={() => setOpen(d.id)} onFocus={() => setOpen(d.id)}>
              <NavLink to={`/shop/${d.id}`} className="nav-link" data-stage-thing={`nav:/shop/${d.id}`}>
                {d.label}
              </NavLink>
            </div>
          ))}
          <div className="nav-item" onMouseEnter={() => setOpen(null)}>
            <NavLink to="/gifts" className="nav-link nav-gifts" data-stage-thing="nav:/gifts">
              <Gift size={15} aria-hidden /> Gifts
            </NavLink>
          </div>
        </nav>
        <SearchBox />
        <div className="header-icons">
          <Link to="/orders" className="hicon hide-phone" aria-label="Orders">
            <Package size={20} />
            <span className="hicon-label">Orders</span>
          </Link>
          <Link to="/wishlist" className="hicon" aria-label={`Wishlist, ${wish} saved`} data-stage-thing="nav:/wishlist">
            <Heart size={20} />
            <span className="hicon-label">Wishlist</span>
            {wish ? <span className="hicon-count">{wish}</span> : null}
          </Link>
          <Link to="/bag" className="hicon" aria-label={`Bag, ${bagCount} items`} data-stage-thing="nav:/bag">
            <ShoppingBag size={20} />
            <span className="hicon-label">Bag</span>
            {bagCount ? (
              <span key={pulse} className={`hicon-count is-bag${pulse ? " is-pulse" : ""}`}>
                {bagCount}
              </span>
            ) : null}
          </Link>
        </div>
      </div>
      {open ? <MegaMenu dept={departments.find((d) => d.id === open)} onClose={() => setOpen(null)} /> : null}
      {drawer ? <PhoneMenu departments={departments} onClose={() => setDrawer(false)} /> : null}
    </header>
  );
}

function MegaMenu({ dept, onClose }: { dept?: Department; onClose: () => void }) {
  if (!dept) return null;
  return (
    <div className="mega" role="region" aria-label={`${dept.label} menu`}>
      <div className="wrap mega-grid">
        {dept.sections.map((s) => (
          <div key={s.label} className="mega-col">
            <p className="mega-head">{s.label}</p>
            <ul>
              {s.types.map((t) => (
                <li key={t}>
                  <Link to={`/shop/${dept.id}/${t}`} onClick={onClose}>
                    {typeLabel(t)}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
        <div className="mega-col mega-all">
          <Link to={`/shop/${dept.id}`} className="mega-all-link" onClick={onClose}>
            Everything in {dept.label}
          </Link>
        </div>
      </div>
    </div>
  );
}

function PhoneMenu({ departments, onClose }: { departments: Department[]; onClose: () => void }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="phone-menu-scrim" onClick={onClose}>
      <aside className="phone-menu" data-overlay="left" aria-label="Menu" onClick={(e) => e.stopPropagation()}>
        <div className="phone-menu-head">
          <Logo />
          <button type="button" className="icon-btn" aria-label="Close the menu" onClick={onClose}>
            <X size={22} />
          </button>
        </div>
        {departments.map((d) => (
          <div key={d.id} className="pm-dept">
            <button type="button" className="pm-dept-btn" aria-expanded={open === d.id} onClick={() => setOpen(open === d.id ? null : d.id)}>
              {d.label}
            </button>
            {open === d.id ? (
              <div className="pm-sections">
                <Link to={`/shop/${d.id}`}>Everything in {d.label}</Link>
                {d.sections.map((s) => (
                  <div key={s.label}>
                    <p className="mega-head">{s.label}</p>
                    {s.types.map((t) => (
                      <Link key={t} to={`/shop/${d.id}/${t}`}>
                        {typeLabel(t)}
                      </Link>
                    ))}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ))}
        <div className="pm-links">
          <Link to="/gifts">Gift finder</Link>
          <Link to="/orders">Orders</Link>
          <Link to="/returns">Returns</Link>
          <Link to="/about">About Fashio</Link>
        </div>
      </aside>
    </div>
  );
}

function SearchBox() {
  const navigate = useNavigate();
  const location = useLocation();
  const query = useStore((s) => s.filters.query ?? "");
  const [text, setText] = useState(query);
  useEffect(() => {
    if (location.pathname.startsWith("/shop")) setText(query);
  }, [query, location.pathname]);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const q = text.trim();
    useStore.getState().setFilters(q ? { query: q } : {});
    navigate(q ? `/shop?q=${encodeURIComponent(q)}` : "/shop");
  };
  return (
    <form className="search" role="search" onSubmit={submit}>
      <Search size={17} aria-hidden className="search-icon" />
      <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Search kurtas, sneakers, brands…" aria-label="Search the store" />
    </form>
  );
}
