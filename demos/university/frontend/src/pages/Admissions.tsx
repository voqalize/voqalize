import { Mail, MessageCircle, Phone } from "lucide-react";
import { Link } from "react-router-dom";
import { PageHead } from "../components/bits";
import { ADMISSIONS } from "../data/admissions";
import { CAMPUSES, INTAKES, SCHOLARSHIPS, nextRound, rupees } from "../data/catalogue";

const SECTIONS: [string, string][] = [
  ["process", "How admission works"],
  ["deadlines", "Deadlines"],
  ["vusat", "VUSAT 2027"],
  ["fees", "Fees"],
  ["instalments", "Instalments"],
  ["refund", "Refunds"],
  ["scholarships", "Scholarships"],
  ["hostel", "Hostel"],
  ["loans", "Education loans"],
  ["documents", "Documents"],
  ["faqs", "Questions families ask"],
  ["contact", "Contact"],
];

const INTAKE_NAMES: Record<string, string> = {
  "ug-2027": "Undergraduate and diploma",
  "pg-2027": "Postgraduate (except MBA)",
  "mba-2027": "MBA",
  "online-jan-2027": "Online degrees",
  "exec-jan-2027": "Executive programmes",
  "cert-monthly": "Online certificates",
};

export function Admissions() {
  const A = ADMISSIONS;
  return (
    <div className="admissions-page">
      <PageHead
        title="Admissions 2027"
        lede="Everything a family needs before applying: the steps, the dates, what it costs and how to pay for it."
        crumbs={[["", "Admissions"]]}
      />
      <div className="wrap doc-layout">
        <nav className="doc-toc" aria-label="On this page">
          {SECTIONS.map(([id, label]) => (
            <a key={id} href={`#${id}`}>
              {label}
            </a>
          ))}
        </nav>
        <div className="doc-body">
          <section id="process" className="psec" data-stage-thing="process" data-stage-label="How admission works">
            <h2>How admission works</h2>
            <ol className="process">
              {A.process.map((s) => (
                <li key={s.step}>
                  <span className="process-n">{s.step}</span>
                  <div>
                    <h3>{s.title}</h3>
                    <p>{s.text}</p>
                  </div>
                </li>
              ))}
            </ol>
          </section>

          <section id="deadlines" className="psec" data-stage-thing="deadlines" data-stage-label="Deadlines">
            <h2>Deadlines</h2>
            <div className="table-scroll">
              <table className="table deadlines-table">
                <thead>
                  <tr>
                    <th scope="col">Programmes</th>
                    <th scope="col">Intake</th>
                    <th scope="col">Rounds</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(INTAKES).map(([key, intake]) => {
                    const next = nextRound(key);
                    return (
                      <tr key={key}>
                        <th scope="row">{INTAKE_NAMES[key] ?? key}</th>
                        <td>
                          {intake.label}
                          <br />
                          <span className="muted">classes from {intake.starts}</span>
                        </td>
                        <td>
                          <ul className="round-cells">
                            {intake.rounds.map((r) => (
                              <li key={r.name} className={next?.name === r.name ? "is-next" : ""}>
                                <b>{r.name}</b> {r.deadline}
                                {r.note ? <em> ({r.note})</em> : null}
                              </li>
                            ))}
                          </ul>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <section id="vusat" className="psec" data-stage-thing="vusat" data-stage-label="VUSAT 2027">
            <h2>{A.vusat.name}</h2>
            <p>{A.vusat.format}</p>
            <div className="phase-grid">
              {A.vusat.phases.map((p) => (
                <div key={p.name} className="phase">
                  <h3>{p.name}</h3>
                  <p className="phase-date">{p.dates}</p>
                  <p className="muted">Register by {p.register_by}</p>
                </div>
              ))}
            </div>
            <p className="note">{A.vusat.note}</p>
          </section>

          <section id="fees" className="psec" data-stage-thing="fees" data-stage-label="Fees">
            <h2>Fees</h2>
            <p>{A.fees.what_is_included}</p>
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">One-time charge</th>
                  <th scope="col">Amount</th>
                  <th scope="col">Refundable</th>
                </tr>
              </thead>
              <tbody>
                {A.fees.one_time.map((o) => (
                  <tr key={o.item}>
                    <th scope="row">{o.item}</th>
                    <td className="num">{rupees(o.amount)}</td>
                    <td>{o.refundable ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p>
              <b>Seat confirmation.</b> {A.fees.seat_confirmation}
            </p>
            <p>
              <b>Ways to pay.</b> {A.fees.payment_methods}
            </p>
            <p className="note">
              Each programme's yearly fee is on its page and in the <Link to="/programs">programme finder</Link>.
            </p>
          </section>

          <section id="instalments" className="psec" data-stage-thing="instalments" data-stage-label="Instalments">
            <h2>Instalments</h2>
            <p>{A.fees.instalments}</p>
            <p className="callout">{A.fees.zero_interest_plan}</p>
          </section>

          <section id="refund" className="psec" data-stage-thing="refund" data-stage-label="Refunds">
            <h2>Refunds</h2>
            <p>{A.fees.refund}</p>
          </section>

          <section id="scholarships" className="psec" data-stage-thing="scholarships" data-stage-label="Scholarships">
            <h2>Scholarships</h2>
            <p>
              {SCHOLARSHIPS.length} schemes cut tuition by up to {Math.max(...SCHOLARSHIPS.flatMap((s) => s.tiers.map((t) => t.waiver)))}%.
            </p>
            <ul className="rules">
              {A.scholarship_rules.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
            <Link to="/scholarships" className="btn btn-ghost btn-sm">
              See every scholarship and its tiers
            </Link>
          </section>

          <section id="hostel" className="psec" data-stage-thing="hostel" data-stage-label="Hostel">
            <h2>Hostel</h2>
            <p>{A.hostel.summary}</p>
            <div className="hostel-grid">
              {CAMPUSES.filter((c) => A.hostel.rooms.some((r) => r.campus === c.id)).map((c) => (
                <table key={c.id} className="table">
                  <caption>{c.label}</caption>
                  <thead>
                    <tr>
                      <th scope="col">Room</th>
                      <th scope="col">A year, with meals</th>
                    </tr>
                  </thead>
                  <tbody>
                    {A.hostel.rooms
                      .filter((r) => r.campus === c.id)
                      .map((r) => (
                        <tr key={r.id}>
                          <th scope="row">{r.label}</th>
                          <td className="num">{rupees(r.per_year)}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              ))}
            </div>
            <p>
              <b>Hostel deposit:</b> {rupees(A.hostel.deposit)}.
            </p>
            <p>{A.hostel.allotment}</p>
            <p className="note">{A.hostel.rules}</p>
          </section>

          <section id="loans" className="psec" data-stage-thing="loans" data-stage-label="Education loans">
            <h2>Education loans</h2>
            <p>{A.loans.summary}</p>
            <dl className="def-list">
              <dt>What lenders cover</dt>
              <dd>{A.loans.covers}</dd>
              <dt>How long it takes</dt>
              <dd>{A.loans.timeline}</dd>
              <dt>Who decides the terms</dt>
              <dd>{A.loans.who_decides}</dd>
              <dt>Loan desk</dt>
              <dd>{A.loans.contact}</dd>
            </dl>
          </section>

          <section id="documents" className="psec" data-stage-thing="documents" data-stage-label="Documents">
            <h2>Documents</h2>
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Document</th>
                  <th scope="col">Who needs it</th>
                </tr>
              </thead>
              <tbody>
                {A.documents.map((d) => (
                  <tr key={d.id}>
                    <th scope="row">{d.label}</th>
                    <td>{d.for.charAt(0).toUpperCase() + d.for.slice(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section id="faqs" className="psec" data-stage-thing="faqs" data-stage-label="Questions families ask">
            <h2>Questions families ask</h2>
            <div className="faqs">
              {A.faqs.map((f, i) => (
                <details key={f.q} data-stage-thing={`faq-${i + 1}`} data-stage-label={f.q}>
                  <summary>{f.q}</summary>
                  <p>{f.a}</p>
                </details>
              ))}
            </div>
          </section>

          <section id="contact" className="psec" data-stage-thing="contact" data-stage-label="Contact">
            <h2>Talk to the admissions office</h2>
            <div className="contact-grid">
              <a href={`tel:${A.contact.phone.replace(/\s/g, "")}`}>
                <Phone size={18} /> {A.contact.phone}
              </a>
              <a href={`mailto:${A.contact.email}`}>
                <Mail size={18} /> {A.contact.email}
              </a>
              <span>
                <MessageCircle size={18} /> WhatsApp {A.contact.whatsapp}
              </span>
            </div>
            <p className="muted">{A.contact.hours}</p>
          </section>
        </div>
      </div>
    </div>
  );
}
