import { Link } from "react-router-dom";

/** Home / Women / Kurtas / … */
export function Breadcrumbs({ trail }: { trail: { label: string; to?: string }[] }) {
  return (
    <nav className="crumbs" aria-label="Breadcrumb">
      <ol>
        <li>
          <Link to="/">Home</Link>
        </li>
        {trail.map((t, i) => (
          <li key={i}>{t.to ? <Link to={t.to}>{t.label}</Link> : <span aria-current="page">{t.label}</span>}</li>
        ))}
      </ol>
    </nav>
  );
}
