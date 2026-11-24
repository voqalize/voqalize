import { PageHead } from "../components/bits";
import { CAMPUS_LIFE } from "../data/admissions";
import { CAMPUSES } from "../data/catalogue";

/** A small CSS/SVG drawing per section: no photographs on this site. */
function Illustration({ id }: { id: string }) {
  const common = { width: "100%", height: "100%", viewBox: "0 0 160 100", "aria-hidden": true, preserveAspectRatio: "xMidYMid slice" } as const;
  switch (id) {
    case "hostels":
      return (
        <svg {...common}>
          <rect x="20" y="30" width="50" height="60" fill="var(--ink)" />
          <rect x="80" y="18" width="60" height="72" fill="var(--indigo)" />
          {Array.from({ length: 12 }, (_, i) => (
            <rect key={i} x={88 + (i % 3) * 16} y={26 + Math.floor(i / 3) * 15} width="8" height="8" fill={i % 4 === 1 ? "var(--marigold)" : "var(--paper)"} opacity={i % 4 === 1 ? 1 : 0.5} />
          ))}
          {Array.from({ length: 6 }, (_, i) => (
            <rect key={i} x={28 + (i % 2) * 20} y={40 + Math.floor(i / 2) * 15} width="10" height="8" fill="var(--paper)" opacity=".45" />
          ))}
        </svg>
      );
    case "clubs":
      return (
        <svg {...common}>
          {[30, 62, 94, 126].map((x, i) => (
            <circle key={x} cx={x} cy={52} r={18 - (i % 2) * 4} fill={["var(--marigold)", "var(--indigo)", "var(--leaf)", "var(--rose)"][i]} opacity=".9" />
          ))}
        </svg>
      );
    case "sports":
      return (
        <svg {...common}>
          <rect x="10" y="20" width="140" height="64" rx="32" fill="none" stroke="var(--leaf)" strokeWidth="10" />
          <rect x="30" y="38" width="100" height="28" rx="14" fill="none" stroke="var(--paper)" strokeWidth="2" opacity=".6" />
          <circle cx="80" cy="52" r="6" fill="var(--marigold)" />
        </svg>
      );
    case "festivals":
      return (
        <svg {...common}>
          <path d="M0 20 Q 40 40 80 20 T 160 20" stroke="var(--ink)" strokeWidth="1.5" fill="none" />
          {Array.from({ length: 9 }, (_, i) => (
            <path key={i} d={`M${8 + i * 18} ${24 + Math.sin(i) * 6} l6 14 l6 -14 z`} fill={i % 2 ? "var(--marigold)" : "var(--rose)"} />
          ))}
          <circle cx="80" cy="76" r="14" fill="var(--marigold)" opacity=".85" />
          <circle cx="80" cy="76" r="6" fill="var(--paper)" />
        </svg>
      );
    case "wellbeing":
      return (
        <svg {...common}>
          <circle cx="80" cy="50" r="34" fill="var(--leaf)" opacity=".2" />
          <circle cx="80" cy="50" r="22" fill="var(--leaf)" opacity=".45" />
          <circle cx="80" cy="50" r="10" fill="var(--leaf)" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <ellipse cx="80" cy="62" rx="52" ry="14" fill="var(--paper)" opacity=".7" />
          <path d="M34 58 a46 30 0 0 0 92 0 z" fill="var(--marigold)" />
          <circle cx="62" cy="50" r="7" fill="var(--rose)" />
          <circle cx="82" cy="46" r="8" fill="var(--leaf)" />
          <circle cx="100" cy="51" r="6" fill="var(--ink)" />
        </svg>
      );
  }
}

export function CampusLife() {
  return (
    <div>
      <PageHead
        title="Campus life"
        lede="Two residential campuses with their own hostels, sports grounds and mess halls, and a year that runs on festivals."
        crumbs={[["", "Campus life"]]}
      />
      <div className="wrap section">
        <dl className="life-stats" data-stage-thing="stats" data-stage-label="Campus in numbers">
          {CAMPUS_LIFE.stats.map((s) => (
            <div key={s.label}>
              <dd>{s.value}</dd>
              <dt>{s.label}</dt>
            </div>
          ))}
        </dl>
        <div className="life-grid">
          {CAMPUS_LIFE.sections.map((s) => (
            <section key={s.id} id={s.id} className={`life-card life-${s.id}`} data-stage-thing={s.id} data-stage-label={s.title}>
              <div className="life-art">
                <Illustration id={s.id} />
              </div>
              <h2>{s.title}</h2>
              <p>{s.text}</p>
            </section>
          ))}
        </div>
        <section className="campus-cards" data-stage-thing="campuses" data-stage-label="Campuses">
          {CAMPUSES.filter((c) => c.acres > 0).map((c) => (
            <div key={c.id} className="campus-card">
              <h2>{c.label}</h2>
              <p>{c.address}</p>
              <p className="muted">{c.acres} acres</p>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
