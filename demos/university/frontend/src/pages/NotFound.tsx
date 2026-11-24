import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <div className="wrap notfound">
      <h1>This page is not on the site</h1>
      <p>The link may be old. Try the programme finder or the admissions pages.</p>
      <p>
        <Link to="/programs" className="btn btn-accent">
          Find a programme
        </Link>{" "}
        <Link to="/admissions" className="btn btn-ghost">
          Admissions
        </Link>
      </p>
    </div>
  );
}
