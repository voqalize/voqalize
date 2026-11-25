/** Question a folio charge: the line, its detail, the guest's reason, the rule. */
import { BottomSheet } from "../components/Shell";
import { DATA } from "../data";
import { day, money } from "../lib/format";
import { type Sheet, closeSheet, folio, sendDispute, setDisputeReason, useStay } from "../state/store";
import "../styles/stay.css";

export default function DisputeSheet({ sheet }: { sheet: Extract<Sheet, { kind: "dispute" }> }) {
  const line = useStay((s) => folio(s).find((l) => l.id === sheet.line_id));
  if (!line) return null;
  const blocked = sheet.reason.trim() ? null : "Tell us what looks wrong.";
  return (
    <BottomSheet
      title="Question this charge"
      sub={day(line.date)}
      onClose={closeSheet}
      footer={
        <div className="st-final">
          <button type="button" className="st-btn is-block" disabled={!!blocked} onClick={sendDispute} data-stage-thing="dispute-send" data-stage-label="Send to the front desk" data-dock-avoid>
            Send to the front desk
          </button>
          {blocked ? <p className="st-reason">{blocked}</p> : null}
        </div>
      }
    >
      <div className="rq-sheet">
        <div className="st-card" data-stage-thing="dispute-line" data-stage-label={line.label}>
          <div className="st-pay">
            <span style={{ fontWeight: 650 }}>{line.label}</span>
            <b>{money(line.amount)}</b>
          </div>
          <p className="st-note" style={{ marginTop: 8 }}>
            {line.detail}
          </p>
        </div>
        <label className="st-field">
          <span className="st-label">What looks wrong?</span>
          <textarea
            className="st-textarea"
            value={sheet.reason}
            placeholder="For example: we didn't take anything from the minibar"
            onChange={(e) => setDisputeReason(e.target.value)}
            data-stage-thing="dispute-reason"
            data-stage-label="Reason"
          />
        </label>
        <div className="st-rule">{DATA.dispute_rule}</div>
      </div>
    </BottomSheet>
  );
}
