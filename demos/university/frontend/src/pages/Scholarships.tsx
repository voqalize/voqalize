import { Link } from "react-router-dom";
import { PageHead } from "../components/bits";
import { ADMISSIONS } from "../data/admissions";
import { PROGRAMS, SCHOLARSHIPS } from "../data/catalogue";

export function Scholarships() {
  return (
    <div>
      <PageHead
        title="Scholarships"
        lede="Eight schemes that reduce tuition, on marks, VUSAT rank, family income, sport and service. Choose one on step 3 of the application."
        crumbs={[["/admissions", "Admissions"], ["", "Scholarships"]]}
      />
      <div className="wrap section schol-page">
        <section className="rules-card" data-stage-thing="rules" data-stage-label="Scholarship rules">
          <h2>How scholarships work</h2>
          <ol>
            {ADMISSIONS.scholarship_rules.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ol>
        </section>
        <div className="schol-grid">
          {SCHOLARSHIPS.map((s) => {
            const count = PROGRAMS.filter((p) => p.scholarships.includes(s.id)).length;
            const top = Math.max(...s.tiers.map((t) => t.waiver));
            return (
              <section key={s.id} id={s.id} className="schol-card" data-stage-thing={s.id} data-stage-label={s.name}>
                <p className="schol-top">
                  up to <b>{top}%</b> of tuition
                </p>
                <h2>{s.name}</h2>
                <p className="muted">
                  <b>For:</b> {s.for}
                </p>
                <p className="muted">
                  <b>Based on:</b> {s.basis}
                </p>
                <table className="table tiers">
                  <tbody>
                    {s.tiers.map((t) => (
                      <tr key={t.rule}>
                        <th scope="row">{t.rule}</th>
                        <td className="num">{t.waiver}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="muted small">Offered on {count} programmes.</p>
              </section>
            );
          })}
        </div>
        <p className="center">
          <Link to="/apply" className="btn btn-accent">
            Apply and choose your scholarship
          </Link>
        </p>
      </div>
    </div>
  );
}
