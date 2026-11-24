import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <div className="page wrap page-head">
      <h1>That page is not here</h1>
      <p className="page-intro">
        The link may be old. Start from the <Link to="/">home page</Link> or see <Link to="/modules">all modules</Link>.
      </p>
    </div>
  );
}
