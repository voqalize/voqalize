/** A visitor at the desk: who, why, the house rule, where to meet, approve or decline (the guest's own presses). */
import { Check, MapPin, Timer, X } from "lucide-react";
import { BottomSheet } from "../components/Shell";
import { VISITORS } from "../data";
import { initials } from "../pages/Visitors";
import { type Sheet, closeSheet, decideVisitor, setVisitorMeet, useStay } from "../state/store";
import "../styles/stay.css";

export default function VisitorSheet({ sheet }: { sheet: Extract<Sheet, { kind: "visitor" }> }) {
  const v = useStay((s) => s.visitors.find((x) => x.id === sheet.visitor_id));
  if (!v) return null;
  return (
    <BottomSheet
      title="Visitor at the desk"
      sub={`Waiting ${v.waiting_min} min`}
      onClose={closeSheet}
      footer={
        <div className="st-final">
          <div className="st-btn-row">
            <button type="button" className="st-btn is-ghost" onClick={() => decideVisitor("declined")} data-stage-thing="visitor-decline" data-stage-label="Decline" data-dock-avoid data-guest-only>
              <X size={17} /> Decline
            </button>
            <button type="button" className="st-btn" disabled={!sheet.meet} onClick={() => decideVisitor("approved")} data-stage-thing="visitor-approve" data-stage-label="Approve" data-dock-avoid data-guest-only>
              <Check size={17} /> Approve
            </button>
          </div>
          {!sheet.meet ? <p className="st-reason">Choose where to meet to approve.</p> : null}
        </div>
      }
    >
      <div className="rq-sheet">
        <div className="rq-sheet-hero" data-stage-thing="visitor" data-stage-label={v.name}>
          <span className="rq-avatar" style={{ background: "var(--paper)" }}>
            {initials(v.name)}
          </span>
          <div>
            <b>{v.name}</b>
            <span>{v.purpose}</span>
            <span className="st-muted" style={{ fontSize: 12, display: "inline-flex", gap: 5, alignItems: "center" }}>
              <Timer size={12} /> {v.waiting_min} min · <MapPin size={12} /> {v.where}
            </span>
          </div>
        </div>
        <section className="st-section" data-stage-thing="meet" data-stage-label="Where to meet" data-stage-group>
          <span className="st-label">Where should they go?</span>
          <div className="st-options" role="radiogroup" aria-label="Where to meet">
            {VISITORS.meet.map((m) => (
              <button
                key={m.id}
                type="button"
                role="radio"
                aria-checked={sheet.meet === m.id}
                className="st-option"
                onClick={() => setVisitorMeet(m.id as "room" | "lobby")}
                data-stage-thing={`meet-${m.id}`}
                data-stage-label={m.label}
              >
                <span className="st-radio" />
                <span className="st-option-text">
                  <span>{m.label}</span>
                </span>
              </button>
            ))}
          </div>
        </section>
        <p className="st-note">{VISITORS.rule}</p>
      </div>
    </BottomSheet>
  );
}
