import { Link } from "react-router-dom";
import { type Level, type Program, levelLabel, modeLabel, schoolById } from "../data/catalogue";

export function LevelBadge({ level }: { level: Level }) {
  return <span className={`badge badge-${level}`}>{levelLabel(level)}</span>;
}

export function ModeBadge({ p }: { p: Program }) {
  return <span className="badge badge-mode">{modeLabel(p.mode)}</span>;
}

export function SchoolTag({ id }: { id: string }) {
  const s = schoolById(id);
  if (!s) return null;
  return (
    <Link to={`/schools/${s.id}`} className="school-tag" style={{ "--accent": s.accent } as React.CSSProperties}>
      <i aria-hidden />
      {s.short}
    </Link>
  );
}

export function PageHead({ title, lede, crumbs, children }: { title: string; lede?: string; crumbs?: [string, string][]; children?: React.ReactNode }) {
  return (
    <header className="page-head">
      <div className="wrap">
        {crumbs ? (
          <nav className="crumbs" aria-label="Breadcrumb">
            <Link to="/">Home</Link>
            {crumbs.map(([to, label]) => (
              <span key={to}>
                <span aria-hidden> / </span>
                {to ? <Link to={to}>{label}</Link> : label}
              </span>
            ))}
          </nav>
        ) : null}
        {title ? <h1>{title}</h1> : null}
        {lede ? <p className="lede">{lede}</p> : null}
        {children}
      </div>
    </header>
  );
}
