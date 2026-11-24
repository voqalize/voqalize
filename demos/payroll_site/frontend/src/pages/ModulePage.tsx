import { Check } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { ModuleCard } from "../components/ModuleGrid";
import { ModuleIcon } from "../components/ModuleIcon";
import { CUSTOMERS, MODULES, moduleById, moduleDetail, PLANS, planById } from "../data/product";
import { actions, useSite } from "../state/store";
import { NotFound } from "./NotFound";

/** Customers whose plan includes this module, as the related proof. */
function customersWith(id: string) {
  return CUSTOMERS.filter((c) => planById(c.plan)?.includes_modules.includes(id));
}

export function ModulePage() {
  const { id = "" } = useParams();
  const m = moduleById(id);
  const fit = useSite((s) => s.matched.includes(id));
  if (!m) return <NotFound />;
  const d = moduleDetail(m.id);
  const plan = planById(m.min_plan)!;
  const plansWith = PLANS.filter((p) => p.includes_modules.includes(m.id));
  const related = customersWith(m.id).slice(0, 2);
  const others = MODULES.filter((x) => x.id !== m.id && x.min_plan === m.min_plan).slice(0, 3);
  return (
    <div className="page module-page">
      <header className="page-head wrap module-hero" data-stage-thing={`module:${m.id}`} data-stage-label={m.name}>
        <p className="crumbs">
          <Link to="/modules">Modules</Link> <span aria-hidden>/</span> {m.name}
        </p>
        <div className="module-hero-row">
          <span className="module-icon module-icon-lg">
            <ModuleIcon name={m.icon} size={28} />
          </span>
          <div>
            <h1>{d.headline}</h1>
            <p className="page-intro">{d.body}</p>
          </div>
        </div>
      </header>
      <section className="section section-tight">
        <div className="wrap module-cols">
          <div>
            <h2 className="h-small">What {m.name.toLowerCase()} does</h2>
            <ul className="tick-list">
              {m.points.map((p) => (
                <li key={p}>
                  <Check size={18} strokeWidth={2.25} /> {p}
                </li>
              ))}
            </ul>
            <button type="button" className={`fit-toggle fit-toggle-lg${fit ? " is-on" : ""}`} aria-pressed={fit} onClick={() => actions.toggleMatched(m.id)}>
              {fit ? "Marked as a fit for your team" : "Mark as a fit for your team"}
            </button>
          </div>
          <aside className="plan-note">
            <h2 className="h-small">Included in</h2>
            <ul className="plan-pills">
              {plansWith.map((p) => (
                <li key={p.id}>
                  <strong>{p.name}</strong>
                  <span className="num">₹{p.price_per_employee_month}</span>
                  <span>per employee a month</span>
                </li>
              ))}
            </ul>
            <p>
              {m.min_plan === "starter" ? "Part of every plan." : `Starts on ${plan.name}.`}{" "}
              <Link to="/pricing">See pricing</Link>
            </p>
          </aside>
        </div>
      </section>
      {related.length ? (
        <section className="section section-tight">
          <div className="wrap">
            <h2 className="h-small">Teams using it</h2>
            <div className="related">
              {related.map((c) => (
                <figure key={c.id} className="quote">
                  <blockquote>{c.quote}</blockquote>
                  <figcaption>
                    <strong>{c.quote_by}</strong>
                    <span>
                      {c.name}, {c.city}
                    </span>
                  </figcaption>
                </figure>
              ))}
            </div>
          </div>
        </section>
      ) : null}
      {others.length ? (
        <section className="section section-tight">
          <div className="wrap">
            <h2 className="h-small">Works alongside</h2>
            <div className="band-grid">
              {others.map((x) => (
                <ModuleCard key={x.id} m={x} />
              ))}
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}
