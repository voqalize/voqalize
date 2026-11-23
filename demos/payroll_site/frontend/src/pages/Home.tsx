import { ClipboardList } from "lucide-react";
import { Link } from "react-router-dom";
import { LeadCard } from "../components/LeadCard";
import { ModuleGrid } from "../components/ModuleGrid";
import { Quotes } from "../components/Quotes";
import { TaxSheet } from "../components/TaxSheet";
import { SITE, TAX_EXAMPLE } from "../data/product";
import { inr } from "../lib/format";
import { actions, useSite } from "../state/store";

export function Home() {
  const h = SITE.home;
  const leadOpen = useSite((s) => s.leadOpen);
  return (
    <div className={`home${leadOpen ? " has-lead" : ""}`}>
      <section className="hero">
        <div className="wrap hero-grid">
          <div className="hero-copy">
            <p className="hero-for">{h.eyebrow}</p>
            <h1>{h.headline}</h1>
            <p className="hero-sub">{h.sub}</p>
            <div className="hero-actions" data-dock-avoid>
              <Link to="/book-demo" className="btn btn-primary btn-lg">
                {h.primary_cta}
              </Link>
              <Link to="/pricing" className="btn btn-ghost btn-lg">
                {h.secondary_cta}
              </Link>
            </div>
            <button type="button" className="hero-brief" onClick={() => actions.openLead(true)} data-stage-thing="lead-open-hero" data-stage-label="Build my plan">
              <ClipboardList size={18} />
              <span>
                <strong>Build my plan.</strong> Tell us your headcount and states, and we will suggest a plan.
              </span>
            </button>
          </div>
          <div className="hero-art">
            <TaxSheet />
          </div>
        </div>
      </section>

      <section className="section pains" data-stage-thing="pain-points" data-stage-label="Pain points">
        <div className="wrap">
          <div className="section-head">
            <h2>{h.pains_title}</h2>
            <p>{h.pains_intro}</p>
          </div>
          <div className="pain-list">
            {h.pains.map((p) => (
              <article key={p.id} className="pain">
                <h3>{p.title}</h3>
                <p>{p.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section modules-sec" data-stage-thing="modules" data-stage-label="Modules">
        <div className="wrap">
          <div className="section-head">
            <h2>{h.modules_title}</h2>
            <p>{h.modules_intro}</p>
          </div>
          <ModuleGrid />
          <p className="section-more">
            <Link to="/modules">Every module in detail</Link>
          </p>
        </div>
      </section>

      <TaxShowcase />

      <section className="section" data-stage-thing="customer-quotes" data-stage-label="Customer quotes">
        <div className="wrap">
          <div className="section-head">
            <h2>{h.quotes_title}</h2>
          </div>
          <Quotes />
        </div>
      </section>

      <section className="section cta-band">
        <div className="wrap cta-inner">
          <div>
            <h2>{h.cta_title}</h2>
            <p>{h.cta_body}</p>
          </div>
          <Link to="/book-demo" className="btn btn-accent btn-lg" data-dock-avoid>
            {h.primary_cta}
          </Link>
        </div>
      </section>
      <LeadCard />
    </div>
  );
}

function TaxShowcase() {
  const h = SITE.home;
  const { declared, after_proofs } = TAX_EXAMPLE;
  const stages = [
    { label: "On what she declared in April", d: declared },
    { label: "On the proofs she submitted in January", d: after_proofs },
  ];
  const max = Math.max(...stages.flatMap((s) => [s.d.new.total_tax, s.d.old.total_tax]));
  return (
    <section className="section showcase" data-stage-thing="tax-showcase" data-stage-label="Tax showcase">
      <div className="wrap showcase-grid">
        <div className="showcase-copy">
          <h2>{h.tax_title}</h2>
          <p>{h.tax_body}</p>
          <p className="showcase-missing">
            Proofs that never came in: {after_proofs.missing.join(" and ")}.
          </p>
          <Link to="/tax" className="btn btn-on-dark" data-dock-avoid>
            See the full working
          </Link>
        </div>
        <div className="showcase-bars">
          {stages.map((s) => {
            const best = s.d.new.total_tax <= s.d.old.total_tax ? "new" : "old";
            return (
              <div key={s.label} className="bar-group">
                <p className="bar-caption">{s.label}</p>
                {(["old", "new"] as const).map((r) => (
                  <div key={r} className={`bar-row${best === r ? " is-best" : ""}`}>
                    <span className="bar-name">{r === "old" ? "Old regime" : "New regime"}</span>
                    <span className="bar-track">
                      <span className="bar-fill" style={{ width: `${(s.d[r].total_tax / max) * 100}%` }} />
                    </span>
                    <span className="bar-val num">{inr(s.d[r].total_tax)}</span>
                  </div>
                ))}
              </div>
            );
          })}
          <p className="bar-note">Year's tax with cess, ₹16.8 lakh CTC in Mumbai. Illustrative, FY 2025-26.</p>
        </div>
      </div>
    </section>
  );
}
