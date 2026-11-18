import { useState } from "react";
import { Link } from "react-router-dom";
import { BookOpen, ChevronDown, Send } from "lucide-react";
import { date } from "../lib/format";
import { discardTicketDraft, editTicketDraft, nameOf, submitTicket, useTk } from "../state/store";
import { PageHead, Panel, Status, thing } from "../components/ui";

/** Short articles about Tankora's own features. No legal advice. */
const ARTICLES: { title: string; body: string; link?: [string, string] }[] = [
  {
    title: "Why did someone's net pay drop this month?",
    body: "Open their payslip and press Compare with the previous month. Every line shows its change and why: loss-of-pay days with the leave behind them, TDS with the year's tax it spreads, and the claims paid with that salary.",
    link: ["/payslips/BB-1030/2026-01?against=2025-12", "See an example comparison"],
  },
  {
    title: "How TDS is spread over the year",
    body: "Each month Tankora works out the year's tax from pay so far, the rest of the year at the current structure and the verified declarations, takes away the TDS already deducted, and divides by the months left. When proofs are verified late in the year, the change lands in the few months remaining.",
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
    body: "Employees > Add employee. Tankora builds the structure from the CTC and city, and prorates the first month: days before joining are unpaid. The preview shows the first payslip before you save.",
    link: ["/employees/new", "Add an employee"],
  },
];

export function HelpPage() {
  const st = useTk();
  const [openArticle, setOpenArticle] = useState<number | null>(0);
  const d = st.ticketDraft;
  return (
    <div className="page">
      <PageHead title="Help" sub="Guides to Tankora, your tickets with our payroll team, and a hand-off when something needs a person." />
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
          <Panel title="Your tickets">
            <ul className="tickets">
              {st.tickets.map((t) => (
                <li key={t.id} data-ticket={t.id}>
                  <div className="ticket-head">
                    <span className="num strong">{t.id}</span>
                    <Status value={t.status} />
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
        <aside className={`panel handoff${d ? " has-draft" : ""}`} {...thing("Hand-off ticket")}>
          <h2>Hand off to Tankora's payroll team</h2>
          <p className="small muted">A payroll specialist reads the summary and replies by email. Nothing is sent until you press Send ticket.</p>
          <label className="field">
            <span>Subject</span>
            <input name="ticket_subject" value={d?.subject ?? ""} placeholder="What needs a person" onChange={(e) => editTicketDraft({ subject: e.target.value })} />
          </label>
          <label className="field">
            <span>Summary</span>
            <textarea
              name="ticket_summary"
              rows={9}
              value={d?.summary ?? ""}
              placeholder="What was asked, what you found, what you need"
              onChange={(e) => editTicketDraft({ summary: e.target.value })}
            />
          </label>
          <label className="field">
            <span>Employee, if it is about one</span>
            <select name="ticket_employee" value={d?.employee_id ?? ""} onChange={(e) => editTicketDraft({ employee_id: e.target.value || null })}>
              <option value="">Not about one person</option>
              {st.employees.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name}, {e.id}
                </option>
              ))}
            </select>
          </label>
          <div className="handoff-actions">
            {d ? (
              <button type="button" className="btn btn-ghost" onClick={discardTicketDraft}>
                Discard
              </button>
            ) : null}
            <button type="button" className="btn btn-primary" data-send-ticket disabled={!d?.subject?.trim() || !d?.summary?.trim()} onClick={() => submitTicket()} {...thing("Send ticket")}>
              <Send size={15} aria-hidden /> Send ticket
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
}
