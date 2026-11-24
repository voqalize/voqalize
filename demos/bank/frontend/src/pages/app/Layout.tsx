/** The signed-in app's chrome: sidebar, top bar, the screen, and a tab bar on phones. */
import {
  ArrowLeftRight,
  BadgePercent,
  CreditCard,
  FileText,
  LayoutDashboard,
  LogOut,
  Menu,
  PiggyBank,
  PieChart,
  Receipt,
  Send,
  Wallet,
  X,
  ExternalLink,
  Phone,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { LogoMark } from "../../components/Logo";
import { brand, customer, daysAgo, fmtDate } from "../../data/bank";
import { useSession } from "../../state/session";
import "../../styles/app.css";

const NAV = [
  { to: "/app", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/app/accounts/sb", label: "Accounts", icon: Wallet, match: "/app/accounts" },
  { to: "/app/transactions", label: "Transactions", icon: ArrowLeftRight },
  { to: "/app/insights", label: "Insights", icon: PieChart },
  { to: "/app/cards", label: "Cards", icon: CreditCard },
  { to: "/app/payments", label: "Payments", icon: Send },
  { to: "/app/bills", label: "Bills", icon: Receipt },
  { to: "/app/deposits", label: "Deposits", icon: PiggyBank },
  { to: "/app/statements", label: "Statements", icon: FileText },
  { to: "/app/offers", label: "Offers", icon: BadgePercent },
];
const TABS = [NAV[0], NAV[2], NAV[4], NAV[5]];

// The public site's mark (src/components/Logo.tsx) with the app's own wordmark styling.
function Mark({ light }: { light?: boolean }) {
  return (
    <span className={`ax-mark${light ? " ax-mark--light" : ""}`}>
      <LogoMark size={light ? 34 : 30} />
      <span className="ax-mark__word">
        Global<em>Bank</em>
      </span>
    </span>
  );
}

function isActive(path: string, item: (typeof NAV)[number]) {
  if (item.end) return path === "/app" || path === "/app/";
  return path.startsWith(item.match ?? item.to);
}

function NavList({ path, onPick }: { path: string; onPick?: () => void }) {
  return (
    <nav className="ax-nav" aria-label="Banking">
      {NAV.map((item) => {
        const Icon = item.icon;
        return (
          <NavLink key={item.to} to={item.to} end={item.end} onClick={onPick} className={isActive(path, item) ? "is-active" : ""}>
            <Icon size={18} strokeWidth={1.9} />
            <span>{item.label}</span>
          </NavLink>
        );
      })}
    </nav>
  );
}

export function AppLayout() {
  const signedIn = useSession((s) => s.signedIn);
  const signOut = useSession((s) => s.signOut);
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [drawer, setDrawer] = useState(false);
  const p = customer.profile;

  useEffect(() => {
    setDrawer(false);
  }, [pathname]);

  if (!signedIn) return <Navigate to={`/login?next=${encodeURIComponent(pathname)}`} replace />;

  const out = () => {
    signOut();
    navigate("/");
  };
  const lastLogin = `${fmtDate(daysAgo(1))}, 9:42 pm`;

  return (
    <div className="ax-app">
      <aside className="ax-side">
        <Link to="/app" className="ax-side__logo" aria-label={`${brand.name} dashboard`}>
          <Mark light />
        </Link>
        <NavList path={pathname} />
        <div className="ax-side__foot">
          <div className="ax-rm">
            <span className="ax-rm__k">Relationship manager</span>
            <span className="ax-rm__v">{p.relationship_manager}</span>
            <span className="ax-rm__k">
              <Phone size={12} /> {brand.helpline}
            </span>
          </div>
        </div>
      </aside>

      <div className="ax-main">
        <header className="ax-top">
          <button type="button" className="ax-top__menu" aria-label="Open menu" onClick={() => setDrawer(true)}>
            <Menu size={22} />
          </button>
          <Link to="/app" className="ax-top__logo">
            <Mark />
          </Link>
          <div className="ax-top__who">
            <span className="ax-avatar" aria-hidden>
              {p.first_name[0]}
              {p.name.split(" ").slice(-1)[0][0]}
            </span>
            <div className="ax-top__id">
              <strong>{p.name}</strong>
              <span>
                Customer ID {p.customer_id} <i>|</i> {p.segment}
              </span>
            </div>
          </div>
          <span className="ax-top__login">Last login {lastLogin}</span>
          <Link to="/" className="ax-top__link">
            <ExternalLink size={15} /> <span>Global Bank website</span>
          </Link>
          <button type="button" className="ax-btn ax-btn--ghost ax-btn--sm ax-top__out" onClick={out}>
            <LogOut size={15} /> <span>Sign out</span>
          </button>
        </header>

        <main className="ax-content">
          <Outlet />
        </main>

        <footer className="ax-foot">
          <span>
            {brand.name} is a fictional bank. All accounts, people and numbers here are sample data.
          </span>
          <span>Helpline {brand.helpline}</span>
        </footer>
      </div>

      <nav className="ax-tabs" aria-label="Quick">
        {TABS.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink key={item.to} to={item.to} end={item.end} className={isActive(pathname, item) ? "is-active" : ""}>
              <Icon size={20} strokeWidth={1.9} />
              <span>{item.label === "Transactions" ? "Activity" : item.label === "Payments" ? "Pay" : item.label === "Dashboard" ? "Home" : item.label}</span>
            </NavLink>
          );
        })}
        <button type="button" onClick={() => setDrawer(true)} className={drawer ? "is-active" : ""}>
          <Menu size={20} strokeWidth={1.9} />
          <span>More</span>
        </button>
      </nav>

      {drawer && (
        <div className="ax-drawer-wrap" data-overlay="left" onMouseDown={(e) => e.target === e.currentTarget && setDrawer(false)}>
          <div className="ax-drawer" role="dialog" aria-label="Menu">
            <div className="ax-drawer__head">
              <Mark light />
              <button type="button" aria-label="Close menu" onClick={() => setDrawer(false)}>
                <X size={22} />
              </button>
            </div>
            <NavList path={pathname} onPick={() => setDrawer(false)} />
            <div className="ax-drawer__foot">
              <span>Last login {lastLogin}</span>
              <Link to="/">Global Bank website</Link>
              <button type="button" onClick={out}>
                <LogOut size={15} /> Sign out
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
