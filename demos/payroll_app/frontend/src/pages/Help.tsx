import { useState } from "react";
import { Link } from "react-router-dom";
import { BookOpen, ChevronDown, LifeBuoy, Lightbulb } from "lucide-react";
import { date } from "../lib/format";
import { TICKET_KINDS, nameOf, openHandoff, useTk } from "../state/store";
import { PageHead, Panel, Status, thing } from "../components/ui";

/** Short articles about Paynora's own features. No legal advice. */
const ARTICLES: { title: string; body: string; link?: [string, string] }[] = [
  {
    title: "Why did someone's net pay drop this month?",
    body: "Open their payslip and press Compare with the previous month. Every line shows its change and why: loss-of-pay days with the leave behind them, TDS with the year's tax it spreads, and the claims paid with that salary.",
    link: ["/payslips/BB-1030/2026-01?against=2025-12", "See an example comparison"],
  },
  {
    title: "How TDS is spread over the year",
    body: "Each month Paynora works out the year's tax from pay so far, the rest of the year at the current structure and the verified declarations, takes away the TDS already deducted, and divides by the months left. When proofs are verified late in the year, the change lands in the few months remaining.",
  },
  {
    title: "Comparing the new and old regimes",
    body: "Tax > Regimes lists every employee's tax on both regimes. Open one to see each step side by side: exemptions, deductions, slab by slab, rebate and cess. An admin can switch the regime used for TDS until the proof window closes.",
    link: ["/tax?tab=regime", "Open regimes"],
  },
  {
    title: "Leave and loss of pay",
    body: "When you approve leave, days beyond the employee's balance of that type become loss of pay. If they fall in the month being paid, the draft run is recalculated at once; the request shows the effect before you approve.",
    link: ["/leave?tab=requests", "Review pending leave"],
  },
  {
    title: "Fixing a claim that does not match its bill",
    body: "A claim whose amount differs from the bill is marked Needs fix. Fix sets it to the bill's amount and approves it into that month's pay. Reimbursements are paid with salary and are not taxed.",
    link: ["/reimbursements", "Open claims"],
  },
  {
    title: "Adding a mid-month joiner",
    body: "Employees > Add employee. Paynora builds the structure from the CTC and city, and prorates the first month: days before joining are unpaid. The preview shows the first payslip before you save.",
    link: ["/employees/new", "Add an employee"],
  },
];

export function HelpPage() {
  const st = useTk();
  const [openArticle, setOpenArticle] = useState<number | null>(0);
  const d = st.ticketDraft;
  return (
    <div className="page">
      <PageHead title="Help" sub="Guides to Paynora, your requests to our payroll team, and a hand-off when something needs a person." />
      <div className="help-grid">
        <div className="help-main">
          <Panel title="Guides">
            <ul className="articles">
              {ARTICLES.map((a, i) => (
                <li key={a.title} className={openArticle === i ? "is-open" : ""}>
                  <button type="button" className="article-q" aria-expanded={openArticle === i} onClick={() => setOpenArticle(openArticle === i ? null : i)}>
                    <BookOpen size={16} aria-hidden />
                    <span>{a.title}</span>
                    <ChevronDown size={16} aria-hidden className="chev" />
                  </button>
                  {openArticle === i ? (
                    <div className="article-a">
                      <p>{a.body}</p>
                      {a.link ? (
                        <Link to={a.link[0]} className="link">
                          {a.link[1]}
                        </Link>
                      ) : null}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="Your tickets" data-stage-group>
            <ul className="tickets">
              {st.tickets.map((t) => (
                <li key={t.id} data-ticket={t.id}>
                  <div className="ticket-head">
                    <span className="num strong">{t.id}</span>
                    <Status value={t.status} />
                    {t.kind ? <span className={`kind-chip kind-${t.kind}`}>{TICKET_KINDS[t.kind]}</span> : null}
                    <span className="small muted">Opened {date(t.opened)}</span>
                  </div>
                  <p className="strong">{t.subject}</p>
                  <p className="small muted">{t.summary}</p>
                  {t.employee_id ? <p className="small">About {nameOf(t.employee_id, st)}</p> : null}
                </li>
              ))}
            </ul>
          </Panel>
        </div>
        <aside className="panel handoff-card" data-stage-group {...thing("Hand-off")}>
          <h2>Hand off to Paynora's payroll team</h2>
          <p className="small muted">When something needs a person, write it up here: a payroll specialist reads it and replies by email. The request opens beside the screen you are on.</p>
          {d ? (
            <button type="button" className="draft-chip" onClick={() => openHandoff()}>
              <span className="small muted">{TICKET_KINDS[d.kind]}, not sent</span>
              <strong>{d.subject || "Untitled"}</strong>
            </button>
          ) : null}
          <div className="handoff-open">
            <button type="button" className="btn btn-primary" onClick={() => openHandoff("support")}>
              <LifeBuoy size={15} aria-hidden /> Support request
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => openHandoff("feature")}>
              <Lightbulb size={15} aria-hidden /> Feature request
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
}
