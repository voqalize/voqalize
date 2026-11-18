/** Small shared pieces: money, status pills, page heads, tabs, tables, dialogs. */
import { type ReactNode, useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { X } from "lucide-react";
import { rupees } from "../lib/format";

/** Marks a thing the agent can point at: `{show: TDS}` finds it by label. */
export function thing(label: string, name?: string) {
  return { "data-stage-thing": name ?? label.toLowerCase().replace(/[^a-z0-9]+/g, "-"), "data-stage-label": label };
}

export function Money({ value, className = "", signed = false }: { value: number; className?: string; signed?: boolean }) {
  const text = signed ? (value > 0 ? `+${rupees(value)}` : rupees(value)) : rupees(value);
  return <span className={`num ${className}`}>{text}</span>;
}

const TONES: Record<string, string> = {
  paid: "ok",
  approved: "ok",
  verified: "ok",
  resolved: "ok",
  issued: "ok",
  draft: "warn",
  pending: "warn",
  submitted: "info",
  open: "info",
  upcoming: "info",
  needs_fix: "bad",
  not_submitted: "bad",
  partly_verified: "warn",
  rejected: "mute",
};
const WORDS: Record<string, string> = { needs_fix: "Needs fix", not_submitted: "Not submitted", partly_verified: "Partly verified" };

export function Status({ value }: { value: string }) {
  const word = WORDS[value] ?? value.charAt(0).toUpperCase() + value.slice(1).replace(/_/g, " ");
  return <span className={`pill pill-${TONES[value] ?? "mute"}`}>{word}</span>;
}

export function PageHead({ title, sub, actions, children }: { title: string; sub?: ReactNode; actions?: ReactNode; children?: ReactNode }) {
  return (
    <header className="pagehead">
      <div className="pagehead-text">
        <h1 data-stage-heading tabIndex={-1}>
          {title}
        </h1>
        {sub ? <p className="pagehead-sub">{sub}</p> : null}
        {children}
      </div>
      {actions ? <div className="pagehead-actions">{actions}</div> : null}
    </header>
  );
}

export function Tabs({ tabs, current, param = "tab" }: { tabs: [string, string][]; current: string; param?: string }) {
  const [params] = useSearchParams();
  return (
    <nav className="tabs" aria-label="Sections">
      {tabs.map(([id, label]) => {
        const next = new URLSearchParams(params);
        next.set(param, id);
        return (
          <Link key={id} to={`?${next.toString()}`} className={`tab${current === id ? " is-on" : ""}`} aria-current={current === id ? "page" : undefined} replace>
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

/** A wide table scrolls inside its own frame, never the page. */
export function TableWrap({ children, label, className = "" }: { children: ReactNode; label?: string; className?: string }) {
  return (
    <div className={`tablewrap ${className}`} role="region" aria-label={label} tabIndex={0}>
      {children}
    </div>
  );
}

export function Panel({ title, actions, children, className = "", ...rest }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string } & Record<string, unknown>) {
  return (
    <section className={`panel ${className}`} {...rest}>
      {title || actions ? (
        <div className="panel-head">
          {title ? <h2>{title}</h2> : <span />}
          {actions}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function Dialog({ open, title, children, onClose }: { open: boolean; title: string; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} className="dialog" onClose={onClose} aria-label={title}>
      <div className="dialog-head">
        <h2>{title}</h2>
        <button type="button" className="iconbtn" aria-label="Close" onClick={onClose}>
          <X size={18} />
        </button>
      </div>
      {children}
    </dialog>
  );
}

export function Drawer({ open, title, children, onClose }: { open: boolean; title: ReactNode; children: ReactNode; onClose: () => void }) {
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="drawer-scrim" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <h2>{title}</h2>
          <button type="button" className="iconbtn" aria-label="Close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <div className="drawer-body">{children}</div>
      </aside>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

export function Avatar({ name, size = 28 }: { name: string; size?: number }) {
  const ini = name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join("");
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return (
    <span className="avatar" style={{ width: size, height: size, fontSize: size * 0.4, background: `oklch(0.9 0.04 ${h})`, color: `oklch(0.35 0.06 ${h})` }} aria-hidden>
      {ini}
    </span>
  );
}

export function Stat({ label, value, note, ...rest }: { label: string; value: ReactNode; note?: ReactNode } & Record<string, unknown>) {
  return (
    <div className="stat" {...rest}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {note ? <span className="stat-note">{note}</span> : null}
    </div>
  );
}
