import { CalendarClock, Clock, MapPin } from "lucide-react";
import { Link } from "react-router-dom";
import { type Program, campusNames, nextRound, rupees, schoolById } from "../data/catalogue";
import { PERSONA } from "../data/persona";
import { LevelBadge, ModeBadge } from "./bits";

export function ProgramCard({
  p,
  pick,
  pinned,
  compare,
}: {
  p: Program;
  /** 1..3 when it is one of the advisor's picks. */
  pick?: number;
  pinned?: boolean;
  compare?: { checked: boolean; onChange(): void };
}) {
  const school = schoolById(p.school);
  const r = nextRound(p.intake);
  return (
    <article
      className={`pcard${pick ? " is-pick" : ""}`}
      data-stage-card={`/programs/${p.id}`}
      data-stage-group
      data-program={p.id}
      style={{ "--accent": school?.accent } as React.CSSProperties}
    >
      {pick ? (
        <p className="pick-badge">
          <b>{pick}</b>
          <span>
            {PERSONA.name}'s pick
            {pinned ? <span className="pinned-note">, outside your filters</span> : null}
          </span>
        </p>
      ) : null}
      <div className="pcard-top">
        <span className="pcard-school">{school?.short}</span>
        <span className="pcard-badges">
          <LevelBadge level={p.level} />
          <ModeBadge p={p} />
        </span>
      </div>
      <h3>
        <Link to={`/programs/${p.id}`} data-program-link={p.id}>
          {p.name}
        </Link>
      </h3>
      <dl className="pcard-facts">
        <div>
          <dt>Fee a year</dt>
          <dd className="num">{rupees(p.fee_per_year)}</dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd>{p.duration_label}</dd>
        </div>
        <div>
          <dt>
            <Clock size={13} aria-hidden /> Hours
          </dt>
          <dd>{p.hours_per_week} a week</dd>
        </div>
        <div>
          <dt>
            <MapPin size={13} aria-hidden /> Campus
          </dt>
          <dd>{campusNames(p)}</dd>
        </div>
      </dl>
      <p className="pcard-deadline">
        <CalendarClock size={14} aria-hidden /> {r ? `${r.name} closes ${r.deadline}` : "Deadlines to be announced"}
      </p>
      <div className="pcard-foot">
        {compare ? (
          <label className="compare-box">
            <input type="checkbox" checked={compare.checked} onChange={compare.onChange} /> Compare
          </label>
        ) : (
          <span />
        )}
        <Link to={`/programs/${p.id}`} className="pcard-view">
          View programme
        </Link>
      </div>
    </article>
  );
}
