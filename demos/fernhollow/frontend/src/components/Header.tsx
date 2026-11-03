import { Heart, Menu, Search, ShoppingBag, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { ROOMS, bestSaving, categoriesIn, money, products, roomCover } from "../data/catalog";
import { DELIVERY_FREE_OVER, site } from "../data/content";
import { useCart } from "../state/cart";
import { useShortlist } from "../state/shortlist";
import { Photo } from "./bits";

export function Wordmark() {
  return (
    <Link to="/" className="wordmark" aria-label="Fernhollow, home">
      <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden className="wordmark-leaf">
        <path
          d="M12 22V9M12 13c-2.6-.3-4.6-2-5.2-4.6 2.6.2 4.6 1.9 5.2 4.6Zm0-3c2.4-.5 4-2.3 4.3-4.9-2.4.6-4 2.4-4.3 4.9Zm0 7c-3-.2-5.4-2-6.3-5 3 .2 5.4 2 6.3 5Zm0-.5c2.8-.5 4.8-2.5 5.4-5.5-2.8.6-4.8 2.6-5.4 5.5ZM12 7c-.9-1.4-.9-3.3 0-5 .9 1.7.9 3.6 0 5Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.25"
          strokeLinejoin="round"
        />
      </svg>
      <span>Fernhollow</span>
    </Link>
  );
}

/** The store's running offers, read from the catalog and the delivery policy. */
const ON_SALE = products.filter((p) => p.onSale);
const SALE_UP_TO = Math.max(0, ...ON_SALE.map((p) => bestSaving(p).pct));

function NoticeBar() {
  return (
    <div className="notice-bar">
      <p>
        {ON_SALE.length ? (
          <>
            <Link to="/sale" className="notice-item">
              <strong>Sale: up to {SALE_UP_TO}% off</strong> on {ON_SALE.length} pieces
            </Link>
            <span className="notice-sep" aria-hidden>
              ·
            </span>
          </>
        ) : null}
        <span className="notice-item">Free delivery on orders over {money(DELIVERY_FREE_OVER)}</span>
      </p>
    </div>
  );
}

export function Header() {
  const lines = useCart((s) => s.lines);
  const openCart = useCart((s) => s.setOpen);
  const saved = useShortlist((s) => s.ids.length);
  const openSaved = useShortlist((s) => s.setOpen);
  const count = lines.reduce((n, l) => n + l.qty, 0);
  const [menu, setMenu] = useState<string | null>(null);
  const [mobile, setMobile] = useState(false);
  const [searching, setSearching] = useState(false);
  const location = useLocation();
  const closeTimer = useRef<number>(undefined);

  useEffect(() => {
    setMenu(null);
    setMobile(false);
    setSearching(false);
  }, [location.pathname, location.search]);

  const openMenu = (id: string) => {
    window.clearTimeout(closeTimer.current);
    setMenu(id);
  };
  const closeSoon = () => {
    closeTimer.current = window.setTimeout(() => setMenu(null), 140);
  };

  return (
    <>
      <NoticeBar />
      <header className="site-header" onKeyDown={(e) => e.key === "Escape" && setMenu(null)}>
        <div className="wrap header-row">
          <button type="button" className="icon-btn only-mobile" aria-label="Open menu" onClick={() => setMobile(true)}>
            <Menu size={20} strokeWidth={1.6} />
          </button>
          <Wordmark />
          <nav className="main-nav" aria-label="Rooms" onMouseLeave={closeSoon}>
            <ul>
              {ROOMS.map((r) => (
                <li key={r.id} onMouseEnter={() => openMenu(r.id)}>
                  <NavLink
                    to={`/room/${r.id}`}
                    className="nav-link"
                    aria-expanded={menu === r.id}
                    onFocus={() => openMenu(r.id)}
                  >
                    {r.short}
                  </NavLink>
                </li>
              ))}
              <li onMouseEnter={() => setMenu(null)}>
                <NavLink to="/sale" className="nav-link">
                  Sale
                </NavLink>
              </li>
              <li onMouseEnter={() => setMenu(null)}>
                <NavLink to="/journal" className="nav-link">
                  Journal
                </NavLink>
              </li>
            </ul>
            {menu ? <MegaMenu room={menu} onEnter={() => openMenu(menu)} onLeave={closeSoon} /> : null}
          </nav>
          <div className="header-tools">
            <button type="button" className="icon-btn" aria-label="Search" onClick={() => setSearching(true)}>
              <Search size={19} strokeWidth={1.6} />
            </button>
            <button type="button" className="icon-btn" aria-label={`Saved pieces, ${saved}`} onClick={() => openSaved(true)}>
              <Heart size={19} strokeWidth={1.6} />
              {saved ? <span className="count-dot">{saved}</span> : null}
            </button>
            <button
              type="button"
              className="icon-btn"
              aria-label={`Cart, ${count} item${count === 1 ? "" : "s"}`}
              onClick={() => openCart(true)}
              data-spot="button:cart"
            >
              <ShoppingBag size={19} strokeWidth={1.6} />
              {count ? <span className="count-dot">{count}</span> : null}
            </button>
          </div>
        </div>
      </header>
      {searching ? <SearchOverlay onClose={() => setSearching(false)} /> : null}
      {mobile ? <MobileMenu onClose={() => setMobile(false)} /> : null}
    </>
  );
}

function MegaMenu({ room, onEnter, onLeave }: { room: string; onEnter: () => void; onLeave: () => void }) {
  const r = ROOMS.find((x) => x.id === room);
  if (!r) return null;
  const cover = roomCover(r.id);
  return (
    <div className="mega" onMouseEnter={onEnter} onMouseLeave={onLeave}>
      <div className="wrap mega-inner">
        <div className="mega-intro">
          <p className="h3">{r.name}</p>
          <p className="small">{site.rooms[r.id]}</p>
          <Link to={`/room/${r.id}`} className="link mega-all">
            Shop all {r.name.toLowerCase()}
          </Link>
        </div>
        <ul className="mega-cats">
          {categoriesIn(r.id).map((c) => (
            <li key={c.slug}>
              <Link to={`/category/${c.slug}`}>{c.name}</Link>
            </li>
          ))}
        </ul>
        <Link to={`/product/${cover.id}`} className="mega-photo" tabIndex={-1} aria-hidden>
          <Photo file={cover.images[0]} alt="" sizes="240px" />
        </Link>
      </div>
    </div>
  );
}

function SearchOverlay({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => ref.current?.focus(), []);
  const SUGGEST = ["Oak dining table", "Linen bedding", "Floor lamp", "Walnut", "Boucle", "Stoneware vase"];
  return (
    <div className="search-overlay" role="dialog" aria-modal="true" aria-label="Search the store" onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <button type="button" className="scrim" aria-label="Close search" onClick={onClose} />
      <div className="search-panel">
        <div className="wrap">
          <form
            className="search-form"
            role="search"
            onSubmit={(e) => {
              e.preventDefault();
              if (q.trim()) navigate(`/search?q=${encodeURIComponent(q.trim())}`);
            }}
          >
            <Search size={22} strokeWidth={1.5} aria-hidden />
            <input
              ref={ref}
              className="search-input"
              type="search"
              placeholder="Search sofas, oak, linen…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-label="Search"
            />
            <button type="button" className="icon-btn" aria-label="Close search" onClick={onClose}>
              <X size={20} strokeWidth={1.6} />
            </button>
          </form>
          <div className="search-suggest">
            <span className="small">Try</span>
            {SUGGEST.map((s) => (
              <button key={s} type="button" className="chip" onClick={() => navigate(`/search?q=${encodeURIComponent(s)}`)}>
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function MobileMenu({ onClose }: { onClose: () => void }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="drawer-root" role="dialog" aria-modal="true" aria-label="Menu" onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <button type="button" className="scrim" aria-label="Close menu" onClick={onClose} />
      <div className="drawer drawer-left">
        <div className="drawer-head">
          <Wordmark />
          <button type="button" className="icon-btn" aria-label="Close menu" onClick={onClose} autoFocus>
            <X size={20} strokeWidth={1.6} />
          </button>
        </div>
        <nav className="drawer-body mobile-nav" aria-label="Rooms">
          {ROOMS.map((r) => (
            <div key={r.id} className="mobile-room">
              <button type="button" className="mobile-room-btn" aria-expanded={open === r.id} onClick={() => setOpen(open === r.id ? null : r.id)}>
                <span>{r.name}</span>
                <span aria-hidden>{open === r.id ? "−" : "+"}</span>
              </button>
              {open === r.id ? (
                <ul>
                  <li>
                    <Link to={`/room/${r.id}`}>All {r.name.toLowerCase()}</Link>
                  </li>
                  {categoriesIn(r.id).map((c) => (
                    <li key={c.slug}>
                      <Link to={`/category/${c.slug}`}>{c.name}</Link>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ))}
          <div className="mobile-extra">
            <Link to="/sale">Sale</Link>
            <Link to="/journal">Journal</Link>
            <Link to="/board">Plan a room</Link>
            <Link to="/about">About</Link>
            <Link to="/contact">Contact</Link>
          </div>
        </nav>
      </div>
    </div>
  );
}
