import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <div className="wrap page narrow">
      <h1 className="h1">We couldn’t find that page</h1>
      <p className="muted">The link may be old. Try one of these instead.</p>
      <p className="hero-ctas">
        <Link to="/" className="btn btn-primary">Home</Link>
        <Link to="/my-policies" className="btn btn-ghost">My policies</Link>
      </p>
    </div>
  );
}
