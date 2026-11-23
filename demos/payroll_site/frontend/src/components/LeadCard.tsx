/**
 * The lead card on the home page: what the visitor has told us, field by
 * field. The agent fills it with `lead.fill` moves; the visitor can fill or
 * correct every row by hand. A fixed panel on the right on a wide screen, a
 * bottom sheet on a phone.
 */
import { ChevronDown, ClipboardList, X } from "lucide-react";
import { Link } from "react-router-dom";
import { EXTRA_MODULES, LEAD, planById } from "../data/product";
import { actions, type LeadField, painModules, suggestedPlan, useSite } from "../state/store";

const LABELS = LEAD.labels as Record<LeadField, string>;

function filledCount(lead: ReturnType<typeof useSite.getState>["lead"]): number {
  return (LEAD.fields as LeadField[]).filter((f) => {
    const v = lead[f];
    return Array.isArray(v) ? v.length > 0 : v !== null && v !== "";
  }).length;
}

export function LeadCard() {
  const lead = useSite((s) => s.lead);
  const open = useSite((s) => s.leadOpen);
  const changed = useSite((s) => s.leadField);
  const filled = filledCount(lead);
  if (!open && filled === 0) return null;

  if (!open) {
    return (
      <button type="button" className="lead-tab" onClick={() => actions.openLead(true)} data-tile-avoid data-stage-thing="lead-open" data-stage-label="Your brief">
        <ClipboardList size={16} /> Your brief <span className="num">{filled}/{LEAD.fields.length}</span>
      </button>
    );
  }

  const plan = lead.recommended_plan || suggestedPlan(lead);
  const planName = plan ? planById(plan)?.name : "";
  const extra = new Set(EXTRA_MODULES.map((m) => m.id));
  const row = (field: LeadField, body: React.ReactNode) => (
    <div className={`lead-row${changed === field ? " is-new" : ""}`} data-stage-part={`lead:${field}`} key={field}>
      <span className="lead-label">{LABELS[field]}</span>
      {body}
    </div>
  );
  const availableStates = LEAD.states.filter((s) => !lead.states.includes(s));

  return (
    <aside className="lead-card" data-tile-avoid data-stage-thing="lead-card" data-stage-label="Your brief" aria-label="Your Paynora brief">
      <div className="lead-head">
        <div>
          <h2>Your brief</h2>
          <p>
            <span className="num">{filled}</span> of {LEAD.fields.length} filled. Edit anything.
          </p>
        </div>
        <button type="button" className="icon-btn" aria-label="Close your brief" onClick={() => actions.openLead(false)}>
          <span className="lead-close-desk">
            <X size={18} />
          </span>
          <span className="lead-close-phone">
            <ChevronDown size={18} />
          </span>
        </button>
      </div>
      <div className="lead-body">
        {row(
          "company",
          <input className="lead-input" value={lead.company} placeholder="Company name" onChange={(e) => actions.setLead("company", e.target.value)} />,
        )}
        {row("name", <input className="lead-input" value={lead.name} placeholder="Your name" onChange={(e) => actions.setLead("name", e.target.value)} />)}
        {row(
          "headcount",
          <input
            className="lead-input num"
            type="number"
            min={1}
            inputMode="numeric"
            value={lead.headcount ?? ""}
            placeholder="How many people"
            onChange={(e) => actions.setLead("headcount", e.target.value)}
          />,
        )}
        {row(
          "states",
          <div className="chips">
            {lead.states.map((s) => (
              <button type="button" key={s} className="chip is-on" onClick={() => actions.toggleLeadItem("states", s)} aria-label={`Remove ${s}`}>
                {s} <X size={12} />
              </button>
            ))}
            <select
              className="chip-add"
              value=""
              aria-label="Add a state"
              onChange={(e) => e.target.value && actions.toggleLeadItem("states", e.target.value)}
            >
              <option value="">{lead.states.length ? "Add a state" : "Where do you operate?"}</option>
              {availableStates.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>,
        )}
        {row(
          "current_tool",
          <select className="lead-input" value={lead.current_tool} onChange={(e) => actions.setLead("current_tool", e.target.value)}>
            <option value="">How do you run payroll today?</option>
            {LEAD.current_tools.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>,
        )}
        {row(
          "pains",
          <div className="chips">
            {LEAD.pains.map((p) => {
              const on = lead.pains.includes(p.id);
              return (
                <button type="button" key={p.id} className={`chip${on ? " is-on" : ""}`} aria-pressed={on} onClick={() => actions.toggleLeadItem("pains", p.id)}>
                  {p.label}
                </button>
              );
            })}
          </div>,
        )}
        {row(
          "recommended_plan",
          <div className="lead-plan">
            {planName ? (
              <>
                <strong>{planName}</strong>
                <span>{lead.recommended_plan ? "suggested for your team" : "from your headcount and needs"}</span>
              </>
            ) : (
              <span className="lead-empty">Add your headcount to see a plan</span>
            )}
          </div>,
        )}
        {row(
          "email",
          <input
            className="lead-input"
            type="email"
            autoComplete="email"
            value={lead.email}
            placeholder="name@company.in"
            onChange={(e) => actions.setLead("email", e.target.value)}
          />,
        )}
      </div>
      <div className="lead-foot">
        <Link
          to="/pricing"
          className="btn btn-primary btn-block"
          onClick={() => {
            if (lead.headcount) actions.setPricing({ headcount: lead.headcount, modules: painModules(lead.pains).filter((m) => extra.has(m)) });
          }}
        >
          See my price
        </Link>
        <Link to="/book-demo" className="btn btn-ghost btn-block">
          Book a demo
        </Link>
      </div>
    </aside>
  );
}
