import { PhoneCall, X } from "lucide-react";
import { showPhone } from "../data/clinic";
import { type Callback, actions, useStore } from "../state/store";

const URGENCY: Record<Callback["urgency"], string> = { urgent: "Urgent", today: "Today", routine: "Routine" };

export function CallbackBody({ cb }: { cb: Callback }) {
  return (
    <>
      <p className="cb-ref">
        Reference <strong>{cb.id}</strong>
        <span className={`tag tag-${cb.urgency}`}>{URGENCY[cb.urgency]}</span>
      </p>
      <p className="cb-reason">{cb.reason}</p>
      <p className="small muted">
        A dentist calls {cb.phone ? `+91 ${showPhone(cb.phone)}` : "you"} {cb.window}.
      </p>
    </>
  );
}

/** The callback just requested, on whichever page is in front. */
export function CallbackCard() {
  const id = useStore((s) => s.lastCallback);
  const cb = useStore((s) => s.callbacks.find((c) => c.id === id));
  if (!cb) return null;
  return (
    <aside className="callback-card" data-overlay="bottom" data-dock-avoid data-stage-thing="callback" data-stage-label="Callback request" aria-live="polite">
      <div className="panel-head">
        <PhoneCall size={18} aria-hidden />
        <h3>Callback requested</h3>
        <button type="button" className="icon-btn" aria-label="Close" onClick={() => actions.dismissCallback()}>
          <X size={16} />
        </button>
      </div>
      <CallbackBody cb={cb} />
    </aside>
  );
}
