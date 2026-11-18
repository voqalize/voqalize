import { CalendarClock, Check, GitCompare } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { PageHead, LevelBadge, ModeBadge, SchoolTag } from "../components/bits";
import { ADMISSIONS } from "../data/admissions";
import { INTAKES, campusNames, lpa, nextRound, programById, rupees, scholarshipById, schoolById } from "../data/catalogue";
import { useFinder } from "../state/finder";
import { NotFound } from "./NotFound";

export function ProgramPage() {
  const { id } = useParams();
  const p = programById(id);
  const navigate = useNavigate();
  if (!p) return <NotFound />;
  const school = schoolById(p.school)!;
  const intake = INTAKES[p.intake];
  const next = nextRound(p.intake);
  const online = p.campuses.length === 1 && p.campuses[0] === "online";
  const compare = () => {
    const f = useFinder.getState();
    if (!f.ticked.includes(p.id)) f.toggleTick(p.id);
    navigate("/programs");
  };
  return (
    <div className="program-page" style={{ "--accent": school.accent } as React.CSSProperties}>
      <PageHead title="" crumbs={[["/programs", "Programmes"], [`/schools/${school.id}`, school.short], ["", p.award]]}>
        <div className="program-title" data-stage-thing="title" data-stage-label={p.name}>
          <div className="program-badges">
            <SchoolTag id={p.school} />
            <LevelBadge level={p.level} />
            <ModeBadge p={p} />
          </div>
          <h1>{p.name}</h1>
          <p className="lede">{p.highlights[0]}. Taught at {campusNames(p)}; classes from {intake.starts}.</p>
          <div className="program-ctas">
            <Link to={`/apply?program=${p.id}`} className="btn btn-accent">
              Apply now
            </Link>
            <button type="button" className="btn btn-ghost" onClick={compare}>
              <GitCompare size={16} /> Compare
            </button>
          </div>
        </div>
      </PageHead>

      <div className="facts-strip">
        <dl className="wrap">
          <div>
            <dt>Fee a year</dt>
            <dd className="num">{rupees(p.fee_per_year)}</dd>
          </div>
          <div>
            <dt>Duration</dt>
            <dd>{p.duration_label}</dd>
          </div>
          <div>
            <dt>Hours a week</dt>
            <dd>{p.hours_per_week}</dd>
          </div>
          <div>
            <dt>Seats</dt>
            <dd>{p.seats}</dd>
          </div>
          <div>
            <dt>Next deadline</dt>
            <dd>{next ? next.deadline : "—"}</dd>
          </div>
        </dl>
      </div>

      <div className="wrap program-body">
        <nav className="program-toc" aria-label="On this page">
          {[
            ["overview", "Overview"],
            ["eligibility", "Eligibility"],
            ["selection", "Selection"],
            ["fees", "Fees"],
            ["scholarships", "Scholarships"],
            ["deadlines", "Deadlines"],
            ["outcomes", "Outcomes"],
            ["curriculum", "Curriculum"],
            ["highlights", "Highlights"],
          ].map(([id, label]) => (
            <a key={id} href={`#${id}`}>
              {label}
            </a>
          ))}
        </nav>
        <div className="program-sections">
          <section id="overview" className="psec" data-stage-thing="overview" data-stage-label="Overview">
            <h2>Overview</h2>
            <p>
              {p.name} is offered by the {school.name}. {school.blurb}
            </p>
            {p.specialisations.length ? (
              <p>
                <b>Specialisations:</b> {p.specialisations.join(", ")}.
              </p>
            ) : null}
          </section>

          <section id="eligibility" className="psec" data-stage-thing="eligibility" data-stage-label="Eligibility">
            <h2>Eligibility</h2>
            <p className="big-line">{p.eligibility.needs}</p>
            <ul className="ticks">
              {p.eligibility.min_percent ? <li>Minimum {p.eligibility.min_percent}% in {p.eligibility.requires === "class12" ? "Class 12" : "graduation"}</li> : null}
              {p.eligibility.min_experience_years ? <li>At least {p.eligibility.min_experience_years} years of work experience</li> : null}
              <li>Accepted entrance: {p.entrance.join(", ")}</li>
            </ul>
          </section>

          <section id="selection" className="psec" data-stage-thing="selection" data-stage-label="Selection">
            <h2>Selection</h2>
            <ol className="steps-list">
              {p.selection.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ol>
          </section>

          <section id="fees" className="psec" data-stage-thing="fees" data-stage-label="Fees">
            <h2>Fees</h2>
            <table className="table">
              <tbody>
                <tr>
                  <th scope="row">Fee a year</th>
                  <td className="num">{rupees(p.fee_per_year)}</td>
                </tr>
                <tr>
                  <th scope="row">Total programme fee</th>
                  <td className="num">{rupees(p.fee_total)}</td>
                </tr>
                <tr>
                  <th scope="row">Application fee</th>
                  <td className="num">{rupees(p.application_fee)}</td>
                </tr>
                {online
                  ? null
                  : ADMISSIONS.fees.one_time.map((o) => (
                      <tr key={o.item}>
                        <th scope="row">
                          {o.item}
                          {o.refundable ? " (refundable)" : ""}
                        </th>
                        <td className="num">{rupees(o.amount)}</td>
                      </tr>
                    ))}
              </tbody>
            </table>
            <p className="note">{ADMISSIONS.fees.what_is_included}</p>
            <p className="note">
              <b>Instalments.</b> {ADMISSIONS.fees.instalments} {ADMISSIONS.fees.zero_interest_plan}
            </p>
          </section>

          <section id="scholarships" className="psec" data-stage-thing="scholarships" data-stage-label="Scholarships">
            <h2>Scholarships</h2>
            {p.scholarships.length ? (
              <div className="schol-list">
                {p.scholarships.map((sid) => {
                  const s = scholarshipById(sid);
                  if (!s) return null;
                  return (
                    <div key={sid} className="schol-row">
                      <h3>{s.name}</h3>
                      <p className="muted">{s.basis}</p>
                      <ul>
                        {s.tiers.map((t) => (
                          <li key={t.rule}>
                            <span className="waiver">{t.waiver}%</span> {t.rule}
                          </li>
                        ))}
                      </ul>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p>This programme has no scholarship scheme.</p>
            )}
            <p className="note">
              {ADMISSIONS.scholarship_rules[0]} <Link to="/scholarships">All scholarship rules</Link>
            </p>
          </section>

          <section id="deadlines" className="psec" data-stage-thing="deadlines" data-stage-label="Deadlines">
            <h2>Deadlines for {intake.label} entry</h2>
            <p>Classes start {intake.starts}.</p>
            <ol className="rounds">
              {intake.rounds.map((r) => (
                <li key={r.name} className={next?.name === r.name ? "is-next" : ""}>
                  <CalendarClock size={16} aria-hidden />
                  <b>{r.name}</b>
                  <span>{r.deadline}</span>
                  {r.note ? <em>{r.note}</em> : null}
                  {next?.name === r.name ? <span className="next-tag">Next</span> : null}
                </li>
              ))}
            </ol>
          </section>

          <section id="outcomes" className="psec" data-stage-thing="outcomes" data-stage-label="Outcomes">
            <h2>Outcomes</h2>
            {p.outcomes.placement_pct != null ? (
              <dl className="outcome-grid">
                <div>
                  <dt>Placed</dt>
                  <dd>{p.outcomes.placement_pct}%</dd>
                </div>
                {p.outcomes.median_ctc_lpa != null ? (
                  <div>
                    <dt>Median salary</dt>
                    <dd>{lpa(p.outcomes.median_ctc_lpa)}</dd>
                  </div>
                ) : null}
                {p.outcomes.highest_ctc_lpa != null ? (
                  <div>
                    <dt>Highest salary</dt>
                    <dd>{lpa(p.outcomes.highest_ctc_lpa)}</dd>
                  </div>
                ) : null}
              </dl>
            ) : null}
            {p.outcomes.note ? <p className="big-line">{p.outcomes.note}</p> : null}
            <p>
              <b>Roles graduates take:</b> {p.outcomes.roles.join(", ")}.
            </p>
          </section>

          <section id="curriculum" className="psec" data-stage-thing="curriculum" data-stage-label="Curriculum">
            <h2>Curriculum</h2>
            <ul className="module-list">
              {p.modules.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          </section>

          <section id="highlights" className="psec" data-stage-thing="highlights" data-stage-label="Highlights">
            <h2>Highlights</h2>
            <ul className="ticks">
              {p.highlights.map((h) => (
                <li key={h}>
                  <Check size={16} aria-hidden /> {h}
                </li>
              ))}
            </ul>
          </section>

          <div className="apply-inline">
            <div>
              <h2>Apply for {p.name}</h2>
              <p>
                Application fee {rupees(p.application_fee)}. {next ? `${next.name} closes ${next.deadline}.` : ""}
              </p>
            </div>
            <Link to={`/apply?program=${p.id}`} className="btn btn-accent">
              Apply now
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
