/** The admin shell: sidebar, top bar (company, FY, search, view as employee, user). */
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  CalendarDays, CircleHelp, IndianRupee, Landmark, LayoutDashboard, ListChecks, Menu, ReceiptText, Search, Settings, Users, Wallet, X,
} from "lucide-react";
import { ADMIN, COMPANY, PRODUCT } from "../lib/data";
import type { PageName } from "../lib/routes";
import { claimsToReview, pendingLeave, useTk } from "../state/store";
import { Avatar } from "./ui";

const NAV: [PageName, string, typeof Users][] = [
  ["Dashboard", "/", LayoutDashboard],
  ["Employees", "/employees", Users],
  ["Payroll", "/payroll", Wallet],
  ["Payslips", "/payslips", ReceiptText],
  ["Leave", "/leave", CalendarDays],
  ["Reimbursements", "/reimbursements", IndianRupee],
  ["Tax", "/tax", Landmark],
  ["Settings", "/settings", Settings],
  ["Help", "/help", CircleHelp],
];

export function Logo() {
  return <span className="logo" aria-hidden dangerouslySetInnerHTML={{ __html: PRODUCT.brand.logo_svg }} />;
}

export function Shell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  useEffect(() => setOpen(false), [loc.pathname]);
  const leaveCount = useTk((s) => pendingLeave(s).length);
  const claimCount = useTk((s) => claimsToReview(s).length);
  const setupDone = useTk((s) => s.setup.finished);
  const counts: Partial<Record<PageName, number>> = { Leave: leaveCount, Reimbursements: claimCount };
  return (
    <div className={`shell${open ? " nav-open" : ""}`}>
      <aside className="sidebar" aria-label="Main">
        <div className="brand">
          <Logo />
          <span className="brand-name">{PRODUCT.brand.name}</span>
          <button type="button" className="iconbtn sidebar-close" aria-label="Close menu" onClick={() => setOpen(false)}>
            <X size={18} />
          </button>
        </div>
        <nav className="nav">
          {NAV.map(([name, to, Icon]) => (
            <NavLink key={name} to={to} end={to === "/"} className={({ isActive }) => `nav-item${isActive ? " is-on" : ""}`} data-nav={name}>
              <Icon size={18} strokeWidth={1.8} aria-hidden />
              <span>{name}</span>
              {counts[name] ? <span className="nav-count" aria-label={`${counts[name]} to review`}>{counts[name]}</span> : null}
            </NavLink>
          ))}
        </nav>
        <NavLink to="/welcome" className={({ isActive }) => `nav-item nav-setup${isActive ? " is-on" : ""}`} data-nav="Setup">
          <ListChecks size={18} strokeWidth={1.8} aria-hidden />
          <span>Setup</span>
          <span className="nav-hint">{setupDone ? "Done" : "First sign-in"}</span>
        </NavLink>
        <div className="sidebar-foot">
          <span className="plan">Growth plan</span>
          <span className="plan-note">{COMPANY.employees.length} employees, 4 states</span>
        </div>
      </aside>
      <div className="scrim" onClick={() => setOpen(false)} aria-hidden />
      <div className="main-col">
        <Topbar onMenu={() => setOpen(true)} />
        <main id="main" className="main" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}

function Topbar({ onMenu }: { onMenu: () => void }) {
  const navigate = useNavigate();
  return (
    <header className="topbar">
      <button type="button" className="iconbtn menu-btn" aria-label="Open menu" onClick={onMenu}>
        <Menu size={20} />
      </button>
      <div className="org">
        <span className="org-name">{COMPANY.company.name}</span>
        <span className="fy-badge" title="Financial year 2025-26 (1 Apr 2025 to 31 Mar 2026)">
          FY 2025-26
        </span>
      </div>
      <SearchBox />
      <label className="viewas">
        <span className="viewas-label">View as employee</span>
        <select
          value=""
          onChange={(e) => {
            if (e.target.value) navigate(`/me/${e.target.value}/payslips`);
          }}
          aria-label="View as employee"
        >
          <option value="">Choose…</option>
          <option value="BB-1030">Ravi Kumar, BB-1030</option>
          <option value="BB-1007">Kavitha Menon, BB-1007</option>
          <optgroup label="Everyone">
            {COMPANY.employees.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}, {e.id}
              </option>
            ))}
          </optgroup>
        </select>
      </label>
      <div className="me-chip" title={`${ADMIN.name}, ${ADMIN.role}`}>
        <Avatar name={ADMIN.name} size={30} />
        <span className="me-text">
          <span className="me-name">{ADMIN.name}</span>
          <span className="me-role">{ADMIN.role}</span>
        </span>
      </div>
    </header>
  );
}

function SearchBox() {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const employees = useTk((s) => s.employees);
  const navigate = useNavigate();
  const box = useRef<HTMLDivElement>(null);
  const hits = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return [];
    return employees.filter((e) => e.name.toLowerCase().includes(t) || e.id.toLowerCase().includes(t) || e.title.toLowerCase().includes(t)).slice(0, 7);
  }, [q, employees]);
  useEffect(() => {
    const away = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, []);
  const pick = (id: string) => {
    setQ("");
    setOpen(false);
    navigate(`/employees/${id}`);
  };
  return (
    <div className="search" ref={box}>
      <Search size={16} aria-hidden />
      <input
        type="search"
        placeholder="Search people, IDs, titles"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && hits[0]) pick(hits[0].id);
          if (e.key === "Escape") setOpen(false);
        }}
        aria-label="Search employees"
      />
      {open && q.trim() ? (
        <ul className="search-results" role="listbox">
          {hits.length ? (
            hits.map((e) => (
              <li key={e.id}>
                <button type="button" onClick={() => pick(e.id)}>
                  <Avatar name={e.name} size={24} />
                  <span>
                    <strong>{e.name}</strong>
                    <small>
                      {e.id}, {e.title}
                    </small>
                  </span>
                </button>
              </li>
            ))
          ) : (
            <li className="search-none">No one matches “{q.trim()}”</li>
          )}
        </ul>
      ) : null}
    </div>
  );
}

export function BackToAdmin() {
  return (
    <Link to="/employees" className="btn btn-ghost">
      Back to admin
    </Link>
  );
}
