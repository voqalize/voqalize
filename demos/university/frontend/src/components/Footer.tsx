import { Link } from "react-router-dom";
import { ADMISSIONS } from "../data/admissions";
import { CAMPUSES, SCHOOLS, UNIVERSITY } from "../data/catalogue";
import { Jaali, Wordmark } from "./Logo";

export function Footer() {
  const c = ADMISSIONS.contact;
  return (
    <footer className="site-footer">
      <Jaali id="jaali-foot" className="footer-jaali" opacity={0.12} />
      <div className="wrap footer-grid">
        <div className="footer-brand">
          <Wordmark />
          <p>{UNIVERSITY.motto}</p>
          <p className="footer-small">Founded {UNIVERSITY.founded}. A fictional university, made for a Voqalize voice demo.</p>
        </div>
        <div>
          <h2>Admissions office</h2>
          <ul>
            <li>
              <a href={`tel:${c.phone.replace(/\s/g, "")}`}>{c.phone}</a>
            </li>
            <li>
              <a href={`mailto:${c.email}`}>{c.email}</a>
            </li>
            <li>WhatsApp {c.whatsapp}</li>
            <li>{c.hours}</li>
          </ul>
        </div>
        <div>
          <h2>Campuses</h2>
          <ul>
            {CAMPUSES.map((k) => (
              <li key={k.id}>
                <strong>{k.label}</strong>
                <br />
                <span className="footer-small">{k.address}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h2>Schools</h2>
          <ul>
            {SCHOOLS.map((s) => (
              <li key={s.id}>
                <Link to={`/schools/${s.id}`}>{s.short}</Link>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h2>Explore</h2>
          <ul>
            <li>
              <Link to="/programs">Find a programme</Link>
            </li>
            <li>
              <Link to="/admissions">Admissions and fees</Link>
            </li>
            <li>
              <Link to="/scholarships">Scholarships</Link>
            </li>
            <li>
              <Link to="/campus-life">Campus life</Link>
            </li>
            <li>
              <Link to="/apply">Apply online</Link>
            </li>
          </ul>
        </div>
      </div>
      <div className="wrap footer-base">
        <span>© {new Date().getFullYear()} Varenya University</span>
        <span>All fees in Indian rupees. Dates as DD MMM YYYY.</span>
      </div>
    </footer>
  );
}
