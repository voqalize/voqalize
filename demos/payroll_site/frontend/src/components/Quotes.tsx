import { CUSTOMERS, planById } from "../data/product";

/** The customers' quotes: the first one large, the rest in a row. */
export function Quotes({ all = false }: { all?: boolean }) {
  const [lead, ...rest] = CUSTOMERS;
  const others = all ? rest : rest.slice(0, 3);
  return (
    <div className="quotes">
      <figure className="quote quote-lead">
        <blockquote>{lead.quote}</blockquote>
        <figcaption>
          <strong>{lead.quote_by}</strong>
          <span>
            {lead.name}, {lead.city}
          </span>
          <span className="quote-metric">{lead.metric}</span>
        </figcaption>
      </figure>
      <div className="quote-row">
        {others.map((c) => (
          <figure key={c.id} className="quote">
            <blockquote>{c.quote}</blockquote>
            <figcaption>
              <strong>{c.quote_by}</strong>
              <span>
                {c.name}, {c.employees} people on {planById(c.plan)?.name}
              </span>
            </figcaption>
          </figure>
        ))}
      </div>
    </div>
  );
}
