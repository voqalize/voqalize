import { SlidersHorizontal, Star, X } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { PageHead } from "../components/bits";
import { ProgramCard } from "../components/ProgramCard";
import {
  FACETS,
  type Program,
  campusNames,
  lpa,
  modeLabel,
  nextDeadline,
  programById,
  rupees,
  scholarshipById,
} from "../data/catalogue";
import { PERSONA } from "../data/persona";
import { type Sort, listed, matching, optionCount, useFinder } from "../state/finder";

export function Programs() {
  const s = useFinder();
  const { pinned, results } = listed(s);
  const count = matching(s.filters).length;
  const chips = FACETS.flatMap((f) => s.filters[f.name].map((id) => ({ facet: f.name, id, label: f.options.find((o) => o.id === id)?.label ?? id })));
  const active = chips.length;

  return (
    <div className="finder-page">
      <PageHead
        title="Find your programme"
        lede="Filter by level, school, mode, campus, fee and the hours you can give each week. Tick two or three to compare them side by side."
        crumbs={[["", "Programmes"]]}
      />
      <div className="wrap finder">
        <aside className={`facets${s.panelOpen ? " is-open" : ""}`} data-stage-thing="filters" data-stage-label="Filters" aria-label="Filters">
          <div className="facets-head">
            <h2>Filters</h2>
            {active ? (
              <button type="button" className="text-btn" onClick={() => s.clear()}>
                Clear all
              </button>
            ) : null}
            <button type="button" className="facets-close" aria-label="Close filters" onClick={() => s.setPanel(false)}>
              <X size={18} />
            </button>
          </div>
          {FACETS.map((f) => (
            <fieldset key={f.name} className="facet" data-stage-thing={`facet-${f.name}`} data-stage-label={`${f.name} filter`}>
              <legend>{f.name}</legend>
              {f.options.map((o) => {
                const on = s.filters[f.name].includes(o.id);
                const n = optionCount(s.filters, f.name, o.id);
                return (
                  <label key={o.id} className={`facet-opt${on ? " is-on" : ""}${n === 0 && !on ? " is-empty" : ""}`} data-stage-part={`${f.name}:${o.label}`}>
                    <input type="checkbox" checked={on} onChange={(e) => s.setOption(f.name, o.id, e.target.checked)} />
                    <span>{o.label}</span>
                    <span className="facet-count">{n}</span>
                  </label>
                );
              })}
            </fieldset>
          ))}
        </aside>

        <section className="results" aria-label="Programmes">
          <div className="results-head" data-stage-thing="results" data-stage-label="Programmes">
            <div className="results-count">
              <h2>
                {count} {count === 1 ? "programme" : "programmes"}
              </h2>
              <button type="button" className="btn btn-ghost filters-btn" onClick={() => s.setPanel(true)}>
                <SlidersHorizontal size={16} /> Filters{active ? ` (${active})` : ""}
              </button>
              <label className="sort">
                <span>Sort by</span>
                <select value={s.sort} onChange={(e) => s.setSort(e.target.value as Sort)}>
                  <option value="fee_asc">Fee a year, low to high</option>
                  <option value="fee_desc">Fee a year, high to low</option>
                  <option value="duration">Duration, shortest first</option>
                </select>
              </label>
            </div>
            {active ? (
              <ul className="chips" data-stage-thing="chips" data-stage-label="Active filters" aria-label="Active filters">
                {chips.map((c) => (
                  <li key={`${c.facet}:${c.id}`}>
                    <button type="button" onClick={() => s.setOption(c.facet, c.id, false)} aria-label={`Remove ${c.facet}: ${c.label}`}>
                      <span className="chip-facet">{c.facet}:</span> {c.label} <X size={13} />
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>

          <Shortlist />

          {pinned.length ? (
            <div className="pinned">
              <h3>Picked for you, outside these filters</h3>
              <div className="card-list">
                {pinned.map((p) => (
                  <ProgramCard key={p.id} p={p} pick={s.picks.indexOf(p.id) + 1} pinned compare={{ checked: s.ticked.includes(p.id), onChange: () => s.toggleTick(p.id) }} />
                ))}
              </div>
            </div>
          ) : null}

          {results.length ? (
            <div className="card-list">
              {results.map((p) => (
                <ProgramCard
                  key={p.id}
                  p={p}
                  pick={s.picks.includes(p.id) ? s.picks.indexOf(p.id) + 1 : undefined}
                  compare={{ checked: s.ticked.includes(p.id), onChange: () => s.toggleTick(p.id) }}
                />
              ))}
            </div>
          ) : (
            <div className="empty">
              <h3>No programme matches all of these filters</h3>
              <p>Untick one of them, or clear them all to see every programme.</p>
              <button type="button" className="btn btn-ghost" onClick={() => s.clear()}>
                Clear all filters
              </button>
            </div>
          )}
        </section>
      </div>

      {s.ticked.length > 0 && s.compared.length === 0 ? (
        <div className="compare-bar" role="region" aria-label="Compare">
          <span>
            {s.ticked.length} of 3 ticked: {s.ticked.map((id) => programById(id)?.name).join(", ")}
          </span>
          <button type="button" className="btn btn-accent" disabled={s.ticked.length < 2} onClick={() => s.openCompare(s.ticked)}>
            Compare {s.ticked.length < 2 ? "(tick one more)" : "side by side"}
          </button>
          <button type="button" className="text-btn" onClick={() => s.ticked.forEach((id) => s.toggleTick(id))}>
            Clear
          </button>
        </div>
      ) : null}

      {s.compared.length ? <Comparison ids={s.compared} onClose={s.closeCompare} /> : null}
      {s.panelOpen ? <div className="facets-scrim" onClick={() => s.setPanel(false)} aria-hidden /> : null}
    </div>
  );
}

function Shortlist() {
  const picks = useFinder((s) => s.picks);
  const unpick = useFinder((s) => s.unpick);
  const openCompare = useFinder((s) => s.openCompare);
  if (!picks.length) return null;
  return (
    <div className="shortlist" data-stage-thing="shortlist" data-stage-label="Shortlist">
      <p className="shortlist-title">
        <Star size={16} aria-hidden /> {PERSONA.name}'s shortlist
      </p>
      <ol>
        {picks.map((id, i) => {
          const p = programById(id);
          if (!p) return null;
          return (
            <li key={id}>
              <b>{i + 1}</b>
              <Link to={`/programs/${id}`}>{p.name}</Link>
              <span className="num">{rupees(p.fee_per_year)}/yr</span>
              <button type="button" aria-label={`Remove ${p.name} from the shortlist`} onClick={() => unpick(id)}>
                <X size={14} />
              </button>
            </li>
          );
        })}
      </ol>
      {picks.length >= 2 ? (
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => openCompare(picks)}>
          Compare the shortlist
        </button>
      ) : null}
    </div>
  );
}

const ROWS: [string, (p: Program) => React.ReactNode][] = [
  ["Duration", (p) => p.duration_label],
  ["Mode", (p) => modeLabel(p.mode)],
  ["Campus", (p) => campusNames(p)],
  ["Fee per year", (p) => <span className="num">{rupees(p.fee_per_year)}</span>],
  ["Total fee", (p) => <span className="num">{rupees(p.fee_total)}</span>],
  ["Hours a week", (p) => `${p.hours_per_week} hours`],
  ["Eligibility", (p) => p.eligibility.needs],
  ["Selection", (p) => p.selection.join(", then ")],
  ["Next deadline", (p) => nextDeadline(p)],
  ["Scholarships", (p) => (p.scholarships.length ? p.scholarships.map((id) => scholarshipById(id)?.name ?? id).join("; ") : "None")],
  ["Placement / outcome", (p) => (p.outcomes.placement_pct != null ? `${p.outcomes.placement_pct}% placed` : (p.outcomes.note ?? "—"))],
  ["Median salary", (p) => (p.outcomes.median_ctc_lpa != null ? lpa(p.outcomes.median_ctc_lpa) : "Not published")],
];

function Comparison({ ids, onClose }: { ids: string[]; onClose(): void }) {
  const ps = ids.map(programById).filter((p): p is Program => !!p);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="compare-overlay" role="dialog" aria-modal="true" aria-label="Comparison">
      <div className="compare-scrim" onClick={onClose} aria-hidden />
      <div className="compare-panel" ref={ref} data-stage-thing="comparison" data-stage-label="Comparison">
        <header>
          <h2>Side by side</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close the comparison">
            <X size={20} />
          </button>
        </header>
        <div className="compare-scroll">
          <table className="compare-table" style={{ "--cols": ps.length } as React.CSSProperties}>
            <thead>
              <tr>
                <th scope="col">
                  <span className="sr-only">Detail</span>
                </th>
                {ps.map((p) => (
                  <th key={p.id} scope="col">
                    <Link to={`/programs/${p.id}`} onClick={onClose}>
                      {p.name}
                    </Link>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map(([label, cell]) => (
                <tr key={label}>
                  <th scope="row">{label}</th>
                  {ps.map((p) => (
                    <td key={p.id}>{cell(p)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <footer>
          {ps.map((p) => (
            <Link key={p.id} to={`/apply?program=${p.id}`} className="btn btn-ghost btn-sm" onClick={onClose}>
              Apply for {p.award === p.name ? p.name : p.name.split(" (")[0]}
            </Link>
          ))}
        </footer>
      </div>
    </div>
  );
}

