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

/**
 * A modal confirm. Drawn in the page (a scrim and a centred card, not the
 * browser's top layer) so the agent's face can sit above it in a top corner
 * while it is open (`data-overlay`, read by `voice/useDockMode`).
 */
export function Dialog({ open, title, children, onClose }: { open: boolean; title: string; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    if (!open) return;
    const back = document.activeElement as HTMLElement | null;
    const k = (e: KeyboardEvent) => e.key === "Escape" && close.current();
    window.addEventListener("keydown", k);
    // Focus the dialog's last action (its confirm), as showModal did.
    const btns = ref.current?.querySelectorAll<HTMLElement>(".dialog-actions button");
    (btns?.[btns.length - 1] ?? ref.current)?.focus();
    return () => {
      window.removeEventListener("keydown", k);
      back?.focus?.();
    };
  }, [open]);
  if (!open) return null;
  return (
    <div className="dialog-scrim" data-overlay="center" onClick={onClose}>
      <div ref={ref} className="dialog" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h2>{title}</h2>
          <button type="button" className="iconbtn" aria-label="Close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

/** A side drawer over the page (`data-overlay="right"`: the agent moves to the top left while it is open). */
export function Drawer({
  open,
  title,
  children,
  onClose,
  className = "",
  head,
  ...rest
}: { open: boolean; title: ReactNode; children: ReactNode; onClose: () => void; className?: string; head?: ReactNode } & Record<string, unknown>) {
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="drawer-scrim" data-overlay="right" onClick={onClose}>
      <aside className={`drawer ${className}`} role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : undefined} onClick={(e) => e.stopPropagation()} {...rest}>
        <div className="drawer-head">
          <div className="drawer-title">
            {head}
            <h2>{title}</h2>
          </div>
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
