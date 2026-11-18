import { ArrowUpRight, Search } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Jaali } from "../components/Logo";
import { ProgramCard } from "../components/ProgramCard";
import { ADMISSIONS, CAMPUS_LIFE } from "../data/admissions";
import { CATALOGUE, INTAKES, PROGRAMS, SCHOLARSHIPS, SCHOOLS, UNIVERSITY, parseDate, programById, programsOf } from "../data/catalogue";
import { useFinder } from "../state/finder";
import { PERSONA } from "../data/persona";

const FEATURED = ["btech-cse", "mba", "bdes-ux", "ballb", "online-mba", "bsc-nursing"];
const INDIAN = new Intl.NumberFormat("en-IN");

interface Dated {
  date: string;
  what: string;
  detail: string;
}

/** Key admission dates from now on, in order. */
function keyDates(): Dated[] {
  const out: Dated[] = [];
  const add = (key: string, who: string) => {
    for (const r of INTAKES[key].rounds) out.push({ date: r.deadline, what: `${who}: ${r.name}`, detail: r.note ? `Deadline, ${r.note}` : `Deadline for ${INTAKES[key].label} entry` });
  };
  add("ug-2027", "Undergraduate");
  add("pg-2027", "Postgraduate");
  add("mba-2027", "MBA");
  for (const ph of ADMISSIONS.ausat.phases) out.push({ date: ph.dates.split("–")[0].replace(/^(\d+)$/, `$1 ${ph.dates.split(" ").slice(1).join(" ")}`), what: `AUSAT ${ph.name}`, detail: `Test on ${ph.dates}, register by ${ph.register_by}` });
  const now = Date.now();
  return out
    .map((d) => ({ ...d, t: parseDate(d.date)?.getTime() ?? 0 }))
    .filter((d) => d.t >= now)
    .sort((a, b) => a.t - b.t)
    .slice(0, 8);
}

export function Home() {
  const u = UNIVERSITY;
  const navigate = useNavigate();
  const [level, setLevel] = useState("");
  const [school, setSchool] = useState("");
  const find = () => {
    const f = useFinder.getState();
    f.clear();
    if (level) f.setOption("Level", level, true);
    if (school) f.setOption("School", school, true);
    navigate("/programs");
  };
  const dates = keyDates();
  const topWaiver = (id: string) => Math.max(...(SCHOLARSHIPS.find((s) => s.id === id)?.tiers.map((t) => t.waiver) ?? [0]));
  return (
    <div className="home">
      <section className="hero">
        <Jaali id="jaali-hero" className="hero-jaali" opacity={0.2} />
        <div className="wrap hero-grid">
          <div className="hero-copy">
            <p className="hero-kicker">Pune, Bengaluru and Anvaya Online. Since {u.founded}.</p>
            <h1>{u.motto}</h1>
            <p className="hero-lede">
              Seven schools and {PROGRAMS.length} programmes, from a four-year B.Tech to a six-week online certificate. Find the one that fits your marks, your budget and
              the hours you have.
            </p>
            <form
              className="hero-finder"
              onSubmit={(e) => {
                e.preventDefault();
                find();
              }}
            >
              <label>
                <span>I want to study</span>
                <select value={level} onChange={(e) => setLevel(e.target.value)}>
                  <option value="">any level</option>
                  {CATALOGUE.levels.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.label.toLowerCase()}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>in</span>
                <select value={school} onChange={(e) => setSchool(e.target.value)}>
                  <option value="">any school</option>
                  {SCHOOLS.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.short}
                    </option>
                  ))}
                </select>
              </label>
              <button type="submit" className="btn btn-accent">
                <Search size={17} /> Find your programme
              </button>
            </form>
            <p className="hero-help">
              Not sure where to start? Press <b>Talk to {PERSONA.name}</b> and say what you are looking for.
            </p>
          </div>
          <dl className="hero-plate" aria-label="Anvaya in numbers">
            <div>
              <dt>Students</dt>
              <dd>{INDIAN.format(u.students)}</dd>
            </div>
            <div>
              <dt>Faculty</dt>
              <dd>{INDIAN.format(u.faculty)}</dd>
            </div>
            <div>
              <dt>Recruiters on campus</dt>
              <dd>{u.recruiters}</dd>
            </div>
            <div>
              <dt>Campuses, plus online</dt>
              <dd>{u.campus_count}</dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="section wrap">
        <div className="section-head">
          <h2>Seven schools</h2>
          <Link to="/schools" className="text-link">
            All schools <ArrowUpRight size={15} />
          </Link>
        </div>
        <div className="school-grid">
          {SCHOOLS.map((s) => (
            <Link key={s.id} to={`/schools/${s.id}`} className="school-tile" style={{ "--accent": s.accent } as React.CSSProperties}>
              <span className="school-tile-count">{programsOf(s.id).length} programmes</span>
              <h3>{s.name}</h3>
              <p>{s.blurb}</p>
            </Link>
          ))}
        </div>
      </section>

      <section className="section section-tint">
        <div className="wrap">
          <div className="section-head">
            <h2>Programmes families ask about most</h2>
            <Link to="/programs" className="text-link">
              Compare all {PROGRAMS.length} <ArrowUpRight size={15} />
            </Link>
          </div>
          <div className="card-grid">
            {FEATURED.map((id) => {
              const p = programById(id);
              return p ? <ProgramCard key={id} p={p} /> : null;
            })}
          </div>
        </div>
      </section>

      <section className="section wrap timeline-section">
        <div className="section-head">
          <h2>Admissions 2027: the dates that matter</h2>
          <Link to="/admissions" className="text-link">
            How admission works <ArrowUpRight size={15} />
          </Link>
        </div>
        <ol className="timeline">
          {dates.map((d) => (
            <li key={d.what}>
              <time>{d.date}</time>
              <strong>{d.what}</strong>
              <span>{d.detail}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="section wrap split">
        <div className="life-teaser">
          <h2>Life on campus</h2>
          <dl className="mini-stats">
            {CAMPUS_LIFE.stats.map((s) => (
              <div key={s.label}>
                <dd>{s.value}</dd>
                <dt>{s.label}</dt>
              </div>
            ))}
          </dl>
          {CAMPUS_LIFE.sections.slice(0, 3).map((s) => (
            <p key={s.id}>
              <b>{s.title}.</b> {s.text}
            </p>
          ))}
          <Link to="/campus-life" className="text-link">
            Hostels, clubs, sports and food <ArrowUpRight size={15} />
          </Link>
        </div>
        <div className="schol-teaser">
          <h2>Scholarships</h2>
          <p>{ADMISSIONS.scholarship_rules[0]}</p>
          <ul>
            {["ausat-rank", "udaan", "merit-12", "women-stem"].map((id) => {
              const s = SCHOLARSHIPS.find((x) => x.id === id)!;
              return (
                <li key={id}>
                  <span className="waiver">up to {topWaiver(id)}%</span>
                  <span>
                    <b>{s.name}</b>
                    <br />
                    {s.basis}
                  </span>
                </li>
              );
            })}
          </ul>
          <Link to="/scholarships" className="text-link">
            All {SCHOLARSHIPS.length} scholarships <ArrowUpRight size={15} />
          </Link>
        </div>
      </section>

      <section className="apply-band">
        <Jaali id="jaali-band" className="band-jaali" opacity={0.16} />
        <div className="wrap apply-band-row">
          <div>
            <h2>Applications for 2027 are open</h2>
            <p>Five steps, about fifteen minutes. One application fee covers up to three programmes.</p>
          </div>
          <Link to="/apply" className="btn btn-accent btn-lg">
            Start your application
          </Link>
        </div>
      </section>
    </div>
  );
}
