/**
 * The guest app's chrome: the brand mark, the phone's status bar, the sticky
 * page header, the bottom tab bar, the bottom sheet every flow opens in, and
 * the toast that confirms what just happened.
 *
 * Pages render inside `.app-scroll` (the one scroll area of the app) and open
 * sheets through the store (`state/store.ts`, `sheet`), which `SheetHost`
 * (App.tsx) draws with `<BottomSheet>`. A sheet marks itself
 * `data-overlay="bottom"`, so the concierge's tile moves to a top corner while
 * it is open.
 */
import { BedDouble, ChevronLeft, ConciergeBell, Home, Sparkles, UtensilsCrossed, X } from "lucide-react";
import { type ReactNode, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { HOTEL } from "../data";
import { clock } from "../lib/format";
import { tabOf } from "../persona";
import { clearToast, stayClock, useStay } from "../state/store";

/** The Belmonte mark: a doorway arch, the sun setting into the bay. */
export function Mark({ size = 28, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" aria-hidden>
      <path d="M8 36V17a12 12 0 0 1 24 0v19" stroke={color} strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="20" cy="22" r="5" fill={color} opacity="0.9" />
      <path d="M11 27.5c3 0 3-1.6 6-1.6s3 1.6 6 1.6 3-1.6 6-1.6" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
      <path d="M11 32c3 0 3-1.6 6-1.6s3 1.6 6 1.6 3-1.6 6-1.6" stroke={color} strokeWidth="1.8" strokeLinecap="round" opacity="0.6" />
      <path d="M5 36h30" stroke={color} strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

export function Wordmark({ small = false }: { small?: boolean }) {
  return (
    <span className={`wordmark${small ? " is-small" : ""}`}>
      <Mark size={small ? 22 : 30} />
      <span>
        <b>BELMONTE</b>
        <i>Halcyon Bay</i>
      </span>
    </span>
  );
}

/** The phone's status bar, drawn by the frame (a real phone has its own). */
export function StatusBar() {
  const scenario = useStay((s) => s.scenario);
  void scenario;
  const t = clock(stayClock().now).replace(/ (AM|PM)$/, "");
  return (
    <div className="status-bar" aria-hidden>
      <span className="status-time">{t}</span>
      <span className="status-island" />
      <span className="status-icons">
        <svg width="18" height="12" viewBox="0 0 18 12">
          <rect x="0" y="8" width="3" height="4" rx="1" fill="currentColor" />
          <rect x="5" y="5.5" width="3" height="6.5" rx="1" fill="currentColor" />
          <rect x="10" y="3" width="3" height="9" rx="1" fill="currentColor" />
          <rect x="15" y="0" width="3" height="12" rx="1" fill="currentColor" />
        </svg>
        <svg width="16" height="12" viewBox="0 0 16 12">
          <path d="M8 11.5 5.6 9a3.4 3.4 0 0 1 4.8 0L8 11.5Z" fill="currentColor" />
          <path d="M3.4 6.8a6.6 6.6 0 0 1 9.2 0" stroke="currentColor" strokeWidth="1.7" fill="none" strokeLinecap="round" />
          <path d="M1 4.3a10 10 0 0 1 14 0" stroke="currentColor" strokeWidth="1.7" fill="none" strokeLinecap="round" />
        </svg>
        <svg width="27" height="13" viewBox="0 0 27 13">
          <rect x="0.5" y="0.5" width="23" height="12" rx="3.5" stroke="currentColor" opacity="0.4" fill="none" />
          <rect x="2" y="2" width="17" height="9" rx="2" fill="currentColor" />
          <rect x="24.5" y="4.5" width="2" height="4" rx="1" fill="currentColor" opacity="0.4" />
        </svg>
      </span>
    </div>
  );
}

const TABS = [
  { id: "home", label: "Home", to: "/", icon: Home },
  { id: "dining", label: "Dining", to: "/dining", icon: UtensilsCrossed },
  { id: "experiences", label: "Experiences", to: "/activities", icon: Sparkles },
  { id: "requests", label: "Requests", to: "/requests", icon: ConciergeBell },
  { id: "stay", label: "Stay", to: "/stay", icon: BedDouble },
] as const;

/** The bottom tab bar. Each tab is a `data-stage-thing="tab-<id>"`. */
export function TabBar() {
  const tab = tabOf(useLocation().pathname);
  const pending = useStay((s) => s.visitors.filter((v) => v.status === "pending").length);
  return (
    <nav className="tab-bar" aria-label="Main">
      {TABS.map((t) => {
        const Icon = t.icon;
        const on = tab === t.id || (t.id === "home" && tab === "info");
        return (
          <Link key={t.id} to={t.to} className={`tab${on ? " is-on" : ""}`} aria-current={on ? "page" : undefined} data-stage-thing={`tab-${t.id}`} data-stage-label={t.label}>
            <span className="tab-icon">
              <Icon size={22} strokeWidth={on ? 2.2 : 1.7} />
              {t.id === "requests" && pending > 0 ? <span className="tab-badge">{pending}</span> : null}
            </span>
            <span>{t.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

/**
 * The sticky header at the top of a page. `back` shows a back chevron to that
 * path. `sub` is a line under the title; `tabs` a segmented row under it
 * (Dining | Drinks, Activities | Spa | Meetings).
 */
export function PageHeader({ title, sub, back, right, tabs }: { title: string; sub?: ReactNode; back?: string; right?: ReactNode; tabs?: ReactNode }) {
  const nav = useNavigate();
  return (
    <header className="page-header">
      <div className="page-header-row">
        {back ? (
          <button type="button" className="icon-btn" aria-label="Back" onClick={() => nav(back)}>
            <ChevronLeft size={22} />
          </button>
        ) : null}
        <div className="page-header-text">
          <h1>{title}</h1>
          {sub ? <p>{sub}</p> : null}
        </div>
        {right}
      </div>
      {tabs ? <div className="page-header-tabs">{tabs}</div> : null}
    </header>
  );
}

/** A segmented control row: each segment is a link or a button. */
export function Segments({ items, value, onChange }: { items: { id: string; label: string; thing?: string }[]; value: string; onChange: (id: string) => void }) {
  return (
    <div className="segments" role="tablist" data-stage-group>
      {items.map((i) => (
        <button key={i.id} type="button" role="tab" aria-selected={value === i.id} className={value === i.id ? "is-on" : ""} onClick={() => onChange(i.id)} data-stage-thing={i.thing} data-stage-label={i.label}>
          {i.label}
        </button>
      ))}
    </div>
  );
}

/**
 * A bottom sheet inside the phone. `onClose` is the store's `closeSheet`.
 * `footer` holds the primary action (Place order, Book…), which stays pinned
 * at the bottom of the sheet; mark the guest-only final button
 * `data-dock-avoid` so nothing covers it.
 */
export function BottomSheet({ title, sub, onClose, children, footer, label }: { title: string; sub?: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; label?: string }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="sheet-layer">
      <button type="button" className="sheet-scrim" aria-label="Close" onClick={onClose} />
      <section className="sheet" data-overlay="bottom" role="dialog" aria-modal="true" aria-label={label ?? title}>
        <div className="sheet-grip" aria-hidden />
        <header className="sheet-head">
          <div>
            <h2>{title}</h2>
            {sub ? <p>{sub}</p> : null}
          </div>
          <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}>
            <X size={20} />
          </button>
        </header>
        <div className="sheet-body">{children}</div>
        {footer ? <footer className="sheet-foot">{footer}</footer> : null}
      </section>
    </div>
  );
}

/** The confirmation after a guest's final press. */
export function ToastHost() {
  const t = useStay((s) => s.toast);
  useEffect(() => {
    if (!t) return;
    const id = window.setTimeout(clearToast, 6500);
    return () => window.clearTimeout(id);
  }, [t]);
  if (!t) return null;
  return (
    <div className="toast" role="status" onClick={clearToast}>
      <b>{t.title}</b>
      <span>{t.body}</span>
    </div>
  );
}

/** A small label: "Gold member", "21+", "GF". */
export function Pill({ children, tone = "plain" }: { children: ReactNode; tone?: "plain" | "brass" | "sea" | "ok" | "coral" }) {
  return <span className={`pill is-${tone}`}>{children}</span>;
}

export const hotelLine = `${HOTEL.name} · ${HOTEL.place}`;
