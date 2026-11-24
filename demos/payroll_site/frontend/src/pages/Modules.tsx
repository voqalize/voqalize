import { Link } from "react-router-dom";
import { ModuleGrid } from "../components/ModuleGrid";
import { SITE } from "../data/product";

export function Modules() {
  const p = SITE.modules_page;
  return (
    <div className="page">
      <header className="page-head wrap">
        <h1>{p.title}</h1>
        <p className="page-intro">{p.intro}</p>
      </header>
      <section className="section section-tight" data-stage-thing="modules" data-stage-label="Modules">
        <div className="wrap">
          <ModuleGrid detailed />
        </div>
      </section>
      <section className="section section-tight">
        <div className="wrap inline-cta">
          <p>Not sure which plan your modules need?</p>
          <Link to="/pricing" className="btn btn-primary" data-dock-avoid>
            Work out your price
          </Link>
        </div>
      </section>
    </div>
  );
}
