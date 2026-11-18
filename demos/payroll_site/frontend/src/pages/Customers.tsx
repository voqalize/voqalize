import { Link } from "react-router-dom";
import { CUSTOMERS, planById, SITE } from "../data/product";

export function Customers() {
  const p = SITE.customers_page;
  return (
    <div className="page">
      <header className="page-head wrap">
        <h1>{p.title}</h1>
        <p className="page-intro">{p.intro}</p>
      </header>
      <section className="section section-tight" data-stage-thing="customer-quotes" data-stage-label="Customer quotes">
        <div className="wrap customer-list">
          {CUSTOMERS.map((c) => (
            <article key={c.id} className="customer" data-stage-thing={`customer:${c.id}`} data-stage-label={c.name}>
              <div className="customer-facts">
                <h2>{c.name}</h2>
                <p>
                  {c.industry}, {c.city}
                </p>
                <dl>
                  <div>
                    <dt>People</dt>
                    <dd className="num">{c.employees}</dd>
                  </div>
                  <div>
                    <dt>States</dt>
                    <dd className="num">{c.states}</dd>
                  </div>
                  <div>
                    <dt>Plan</dt>
                    <dd>{planById(c.plan)?.name}</dd>
                  </div>
                </dl>
              </div>
              <figure className="customer-quote">
                <p className="customer-metric">{c.metric}</p>
                <blockquote>{c.quote}</blockquote>
                <figcaption>{c.quote_by}</figcaption>
              </figure>
            </article>
          ))}
        </div>
      </section>
      <section className="section section-tight">
        <div className="wrap inline-cta">
          <p>See how your payroll would look in Tankora.</p>
          <Link to="/book-demo" className="btn btn-primary">
            Book a demo
          </Link>
        </div>
      </section>
    </div>
  );
}
