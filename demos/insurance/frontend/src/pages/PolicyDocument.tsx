import { ArrowLeft, Check, Download, Minus, ShieldAlert } from "lucide-react";
import { useEffect } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { customer, policyById } from "../data";
import type { Clause } from "../data/types";
import { KindBadge, ProductIcon } from "../components/bits";
import { fmtDate, inr } from "../lib/format";
import { startClaim } from "../state/claim";
import { VERDICT_LABEL, usePolicyView, viewPolicy } from "../state/policyView";

export function PolicyDocument() {
  const { policyId } = useParams();
  const pol = policyById(policyId);
  const navigate = useNavigate();
  const mark = usePolicyView((s) => s.mark);
  const section = usePolicyView((s) => s.section);
  useEffect(() => {
    if (pol) viewPolicy(pol.id, usePolicyView.getState().policyId === pol.id ? usePolicyView.getState().section : null);
  }, [pol]);
  if (!pol || !customer.policies.includes(pol.id)) return <Navigate to="/my-policies" replace />;
  const marked = mark && mark.policyId === pol.id ? mark : null;
  const clauses = pol.sections.reduce((n, s) => n + s.clauses.length, 0);
  const canClaim = pol.product === "car" || pol.product === "bike" || pol.product === "health";

  const goSection = (id: string) => {
    viewPolicy(pol.id, id);
    document.querySelector(`[data-stage-part="section:${id}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="wrap page policy-page" data-stage-part={`policy-doc:${pol.id}`}>
      <div className="doc-toolbar">
        <Link to="/my-policies" className="link-btn">
          <ArrowLeft size={16} aria-hidden /> My policies
        </Link>
        <div className="doc-toolbar-actions">
          <button type="button" className="btn btn-ghost btn-sm" disabled title="Downloads are switched off in this demo">
            <Download size={15} aria-hidden /> PDF
          </button>
          {canClaim ? (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => {
                startClaim(pol.product === "health" ? "health" : "motor", pol.id);
                navigate("/claim");
              }}
            >
              <ShieldAlert size={15} aria-hidden /> Claim on this policy
            </button>
          ) : null}
        </div>
      </div>

      <article className="doc">
        <header className="doc-head" data-stage-part="policy-head">
          <div className="doc-brand">
            <span className="product-icon"><ProductIcon product={pol.product} size={22} /></span>
            <div>
              <p className="doc-kicker">Chhatri Insurance · Policy wording and schedule</p>
              <h1 className="doc-title">{pol.title}</h1>
              <p className="doc-plan">{pol.plan}</p>
            </div>
            <span className={`status status-${pol.status}`}>{pol.status === "active" ? "Active" : "Starts soon"}</span>
          </div>
          <dl className="doc-meta">
            <div><dt>Policy number</dt><dd className="mono">{pol.policy_number}</dd></div>
            <div><dt>Period of insurance</dt><dd>{fmtDate(pol.start)} to {fmtDate(pol.end)}</dd></div>
            <div><dt>Insured</dt><dd>{pol.insured.map((m) => m.name).join(", ")}</dd></div>
            <div><dt>Premium paid</dt><dd>{inr(pol.premium_paid)}</dd></div>
          </dl>
          <p className="doc-summary">{pol.summary}</p>
        </header>

        <div className="doc-tables">
          <section className="doc-block" aria-labelledby="sched-h">
            <h2 id="sched-h" className="doc-h">Schedule</h2>
            <table className="sched">
              <tbody>
                {pol.schedule.map((r) => (
                  <tr key={r.label}>
                    <th scope="row">{r.label}</th>
                    <td>{r.value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <div className="doc-side-tables">
            <section className="doc-block" aria-labelledby="ins-h">
              <h2 id="ins-h" className="doc-h">Insured persons</h2>
              <table className="sched">
                <tbody>
                  {pol.insured.map((m) => (
                    <tr key={m.id}>
                      <th scope="row">{m.name}</th>
                      <td>{m.role}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
            <section className="doc-block" aria-labelledby="add-h">
              <h2 id="add-h" className="doc-h">Add-ons</h2>
              <table className="sched addons-table">
                <tbody>
                  {pol.addons.map((a) => (
                    <tr key={a.id} className={a.included ? "is-in" : "is-out"}>
                      <th scope="row">{a.label}</th>
                      <td>
                        {a.included ? (
                          <span className="inc"><Check size={14} aria-hidden /> Included</span>
                        ) : (
                          <span className="exc"><Minus size={14} aria-hidden /> Not taken</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </div>
        </div>

        <div className="doc-body">
          <nav className="toc" aria-label="Sections">
            <p className="toc-h">Contents · {clauses} clauses</p>
            <ol>
              {pol.sections.map((s) => (
                <li key={s.id}>
                  <button type="button" className={`toc-link${section === s.id ? " is-on" : ""}`} onClick={() => goSection(s.id)}>
                    <span className="toc-n">{s.number}</span> {s.title}
                    {marked && s.clauses.some((c) => c.id === marked.clauseId) ? <span className="toc-dot" aria-label="marked clause" /> : null}
                  </button>
                </li>
              ))}
            </ol>
          </nav>
          <div className="sections">
            {pol.sections.map((s) => (
              <section key={s.id} className="doc-section" data-stage-part={`section:${s.id}`} aria-labelledby={`sec-${s.id}`}>
                <h2 id={`sec-${s.id}`} className="doc-sec-h">
                  <span className="doc-sec-n">{s.number}</span> {s.title}
                </h2>
                {s.clauses.map((c) => (
                  <ClauseView key={c.id} clause={c} mark={marked && marked.clauseId === c.id ? marked : null} />
                ))}
              </section>
            ))}
            <p className="doc-end">End of policy wording. Chhatri Insurance is fictional; this wording is illustrative.</p>
          </div>
        </div>
      </article>
    </div>
  );
}

function ClauseView({ clause: c, mark }: { clause: Clause; mark: { verdict: keyof typeof VERDICT_LABEL; n: number } | null }) {
  return (
    <div id={`clause-${c.id}`} className={`clause${mark ? ` is-marked v-${mark.verdict}` : ""}`} data-stage-part={`clause:${c.id}`}>
      <div className="clause-head">
        <span className="clause-n">{c.id}</span>
        <h3 className="clause-title">{c.title}</h3>
        <KindBadge kind={c.kind} />
        {mark ? <span className={`verdict v-${mark.verdict}`}>{VERDICT_LABEL[mark.verdict]}</span> : null}
      </div>
      <p className="clause-text">{c.text}</p>
      {mark && c.plain ? (
        <p className="plain">
          <span className="plain-h">In plain words</span> {c.plain}
        </p>
      ) : null}
    </div>
  );
}
