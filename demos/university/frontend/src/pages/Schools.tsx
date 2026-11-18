import { useParams } from "react-router-dom";
import { Link } from "react-router-dom";
import { PageHead } from "../components/bits";
import { ProgramCard } from "../components/ProgramCard";
import { SCHOOLS, campusById, levelLabel, programsOf, rupees, schoolById } from "../data/catalogue";
import { NotFound } from "./NotFound";

export function Schools() {
  return (
    <div>
      <PageHead title="Our schools" lede="Seven schools across two campuses and Anvaya Online. Each runs its own studios, labs and clinics." crumbs={[["", "Schools"]]} />
      <div className="wrap section school-list">
        {SCHOOLS.map((s) => {
          const ps = programsOf(s.id);
          const fees = ps.map((p) => p.fee_per_year);
          return (
            <article key={s.id} className="school-row" style={{ "--accent": s.accent } as React.CSSProperties}>
              <div className="school-row-main">
                <h2>
                  <Link to={`/schools/${s.id}`}>{s.name}</Link>
                </h2>
                <p>{s.blurb}</p>
                <p className="muted">
                  Dean: {s.dean}. Founded {s.founded}. {s.campuses.map((c) => campusById(c)?.label).join(", ")}.
                </p>
              </div>
              <dl className="school-row-facts">
                <div>
                  <dt>Programmes</dt>
                  <dd>{ps.length}</dd>
                </div>
                <div>
                  <dt>Fees a year</dt>
                  <dd className="num">
                    {rupees(Math.min(...fees))} to {rupees(Math.max(...fees))}
                  </dd>
                </div>
                <div>
                  <dt>Levels</dt>
                  <dd>{[...new Set(ps.map((p) => levelLabel(p.level)))].join(", ")}</dd>
                </div>
              </dl>
            </article>
          );
        })}
      </div>
    </div>
  );
}

export function SchoolPage() {
  const { id } = useParams();
  const s = schoolById(id);
  if (!s) return <NotFound />;
  const ps = programsOf(s.id).sort((a, b) => a.fee_per_year - b.fee_per_year);
  return (
    <div className="school-page" style={{ "--accent": s.accent } as React.CSSProperties}>
      <PageHead title={s.name} lede={s.blurb} crumbs={[["/schools", "Schools"], ["", s.short]]}>
        <dl className="school-meta" data-stage-thing="about" data-stage-label="About the school">
          <div>
            <dt>Dean</dt>
            <dd>{s.dean}</dd>
          </div>
          <div>
            <dt>Founded</dt>
            <dd>{s.founded}</dd>
          </div>
          <div>
            <dt>Campuses</dt>
            <dd>{s.campuses.map((c) => campusById(c)?.label).join(", ")}</dd>
          </div>
          <div>
            <dt>Programmes</dt>
            <dd>{ps.length}</dd>
          </div>
        </dl>
      </PageHead>
      <section className="wrap section" data-stage-thing="programmes" data-stage-label="Programmes">
        <h2 className="section-title">Programmes in {s.short}</h2>
        <div className="card-grid">
          {ps.map((p) => (
            <ProgramCard key={p.id} p={p} />
          ))}
        </div>
      </section>
    </div>
  );
}
