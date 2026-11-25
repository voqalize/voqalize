/** Any path the store has no page for. */
import { Link } from "react-router-dom";

export function NotFound() {
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
