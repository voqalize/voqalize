/**
 * The hand-off to Paynora's payroll team: a side drawer over whatever screen
 * is in front (the page under it does not change), with the request written
 * out, editable, and Send. Opened by Help's buttons or by the agent's
 * `ticket.draft`; `ticket.submit` presses its Send. Help lists the tickets.
 */
import { LifeBuoy, Lightbulb, Send } from "lucide-react";
import { closeHandoff, discardTicketDraft, editTicketDraft, submitTicket, TICKET_KINDS, type TicketKind, useTk } from "../state/store";
import { Drawer } from "./ui";

export function HandoffDrawer() {
  const open = useTk((s) => s.handoffOpen);
  const d = useTk((s) => s.ticketDraft);
  const employees = useTk((s) => s.employees);
  const kind: TicketKind = d?.kind ?? "support";
  const ready = !!d?.subject?.trim() && !!d?.summary?.trim();
  return (
    <Drawer
      open={open}
      onClose={closeHandoff}
      className={`handoff handoff-${kind}`}
      data-handoff={kind}
      data-stage-group
      data-stage-thing="hand-off-ticket"
      data-stage-label="Hand-off request"
      head={
        <span className={`kind-chip kind-${kind}`} data-ticket-kind={kind}>
          {kind === "feature" ? <Lightbulb size={13} aria-hidden /> : <LifeBuoy size={13} aria-hidden />} {TICKET_KINDS[kind]}
        </span>
      }
      title="To Paynora's payroll team"
    >
      <p className="small muted">A payroll specialist reads this and replies by email. Nothing is sent until you press Send.</p>
      <div className="kind-pick" role="radiogroup" aria-label="Kind of request">
        {(Object.keys(TICKET_KINDS) as TicketKind[]).map((k) => (
          <button key={k} type="button" role="radio" aria-checked={kind === k} className={`kind-opt${kind === k ? " is-on" : ""}`} onClick={() => editTicketDraft({ kind: k })}>
            {TICKET_KINDS[k]}
          </button>
        ))}
      </div>
      <label className="field">
        <span>Subject</span>
        <input name="ticket_subject" value={d?.subject ?? ""} placeholder={kind === "feature" ? "What you would like Paynora to do" : "What needs a person"} onChange={(e) => editTicketDraft({ subject: e.target.value })} />
      </label>
      <label className="field" data-stage-group>
        <span>The request</span>
        <textarea
          name="ticket_summary"
          rows={10}
          value={d?.summary ?? ""}
          placeholder={kind === "feature" ? "What you tried to do, and what would help" : "What was asked, what you found, what you need"}
          onChange={(e) => editTicketDraft({ summary: e.target.value })}
        />
      </label>
      <label className="field">
        <span>Employee, if it is about one</span>
        <select name="ticket_employee" value={d?.employee_id ?? ""} onChange={(e) => editTicketDraft({ employee_id: e.target.value || null })}>
          <option value="">Not about one person</option>
          {employees.map((e) => (
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
        <button type="button" className="btn btn-primary" data-send-ticket disabled={!ready} onClick={() => submitTicket()} data-stage-thing="send-ticket" data-stage-label="Send">
          <Send size={15} aria-hidden /> Send
        </button>
      </div>
    </Drawer>
  );
}
