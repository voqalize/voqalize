/**
 * Any path the store has no page for. One exception: `/p/?id=<id>` (the
 * product link that works cold on static hosting, see `shareUrl` and
 * scripts/route-shells.mjs) moves straight on to `/p/<id>`.
 */
import { Navigate, Link, useLocation } from "react-router-dom";

export function NotFound() {
  const location = useLocation();
  const id = new URLSearchParams(location.search).get("id");
  if (/^\/p\/?$/.test(location.pathname) && id && /^\d+$/.test(id)) return <Navigate to={`/p/${id}`} replace />;
  return <NotFoundBody what="There is no page at this address." />;
}

export function NotFoundBody({ what }: { what: string }) {
  return (
    <div className="wrap notfound">
      <p className="notfound-mark" aria-hidden>
        404
      </p>
      <h1 className="page-title">This page isn't on the rails</h1>
      <p>{what}</p>
      <div className="notfound-links">
        <Link className="btn primary" to="/shop">
          Browse the store
        </Link>
        <Link className="btn ghost" to="/">
          Go home
        </Link>
      </div>
    </div>
  );
}
