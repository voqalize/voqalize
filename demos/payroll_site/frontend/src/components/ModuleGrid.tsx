import { Check, Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { MODULES, type Module, PLANS } from "../data/product";
import { actions, useSite } from "../state/store";
import { ModuleIcon } from "./ModuleIcon";

const BANDS: { plan: string; title: string }[] = [
  { plan: "starter", title: "In every plan" },
  { plan: "growth", title: "Growth adds" },
  { plan: "scale", title: "Scale adds" },
];

export function ModuleCard({ m, detailed = false }: { m: Module; detailed?: boolean }) {
  const fit = useSite((s) => s.matched.includes(m.id));
  return (
    <article className={`module-card${fit ? " is-fit" : ""}`} data-stage-thing={`module:${m.id}`} data-stage-label={m.name}>
      <div className="module-top">
        <span className="module-icon">
          <ModuleIcon name={m.icon} />
        </span>
        {fit ? (
          <span className="fit-mark">
            <Check size={13} strokeWidth={2.5} /> Fits your team
          </span>
        ) : null}
      </div>
      <h3>
        <Link to={`/modules/${m.id}`} className="module-link">
          {m.name}
        </Link>
      </h3>
      <p className="module-short">{m.short}</p>
      {detailed ? (
        <ul className="module-points">
          {m.points.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      ) : null}
      <button type="button" className={`fit-toggle${fit ? " is-on" : ""}`} aria-pressed={fit} onClick={() => actions.toggleMatched(m.id)}>
        {fit ? <Check size={14} /> : <Plus size={14} />} {fit ? "Marked as a fit" : "Mark as a fit"}
      </button>
    </article>
  );
}

/** The ten modules in three bands, by the plan that first includes them. */
export function ModuleGrid({ detailed = false }: { detailed?: boolean }) {
  return (
    <div className="module-bands" data-stage-group="modules">
      {BANDS.map((b) => {
        const plan = PLANS.find((p) => p.id === b.plan)!;
        const mods = MODULES.filter((m) => m.min_plan === b.plan);
        return (
          <div key={b.plan} className={`module-band band-${b.plan}`}>
            <div className="band-head">
              <h3 className="band-title">{b.title}</h3>
              <p className="band-plan">
                {plan.name}, from <span className="num">₹{plan.price_per_employee_month}</span> per employee a month
              </p>
            </div>
            <div className="band-grid">
              {mods.map((m) => (
                <ModuleCard key={m.id} m={m} detailed={detailed} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
