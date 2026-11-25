/**
 * Visitors: who is waiting at the desk (tap to approve or decline), what was
 * decided, and the visitors the guest told the desk to expect.
 */
import { CalendarClock, ChevronRight, MapPin, Timer, UserPlus } from "lucide-react";
import { PageHeader } from "../components/Shell";
import { VISITORS } from "../data";
import { clock } from "../lib/format";
import { openExpect, openVisitor, useStay } from "../state/store";
import "../styles/stay.css";

export const initials = (name: string) =>
  name
    .replace(/,.*/, "")
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();

export function Visitors() {
  const visitors = useStay((s) => s.visitors);
  const expected = useStay((s) => s.expected);
  const pending = visitors.filter((v) => v.status === "pending");
  const decided = visitors.filter((v) => v.status !== "pending");
  return (
    <div className="page st-page" data-stage-place="visitors">
      <PageHeader title="Visitors" sub={pending.length ? `${pending.length} waiting for you` : "Nobody waiting"} back="/requests" />
      <div className="st-body">
        <section className="st-section" data-stage-group>
          <div className="st-section-head">
            <h2>Waiting</h2>
          </div>
          {pending.length ? (
            <div className="rq-list">
              {pending.map((v) => (
                <button key={v.id} type="button" className="rq-visitor is-pending" onClick={() => openVisitor(v.id)} data-stage-thing={`visitor-${v.id}`} data-stage-label={v.name}>
                  <span className="rq-avatar">{initials(v.name)}</span>
                  <span className="rq-visitor-text">
                    <b>{v.name}</b>
                    <span>{v.purpose}</span>
                    <small>
                      <Timer size={12} /> waiting {v.waiting_min} min · <MapPin size={12} /> {v.where}
                    </small>
                  </span>
                  <ChevronRight size={18} color="var(--faint)" />
                </button>
              ))}
            </div>
          ) : (
            <div className="rq-empty">Nobody is waiting for you right now.</div>
          )}
          <p className="st-note">{VISITORS.rule}</p>
        </section>

        {decided.length ? (
          <section className="st-section">
            <div className="st-section-head">
              <h2>Decided</h2>
            </div>
            <div className="rq-list">
              {decided.map((v) => (
                <div key={v.id} className="rq-visitor" data-stage-thing={`visitor-${v.id}`} data-stage-label={v.name}>
                  <span className="rq-avatar">{initials(v.name)}</span>
                  <span className="rq-visitor-text">
                    <b>{v.name}</b>
                    <span>{v.purpose}</span>
                  </span>
                  <span className={`rq-status is-${v.status}`}>{v.status === "approved" ? "Approved" : "Declined"}</span>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        <section className="st-section">
          <div className="st-section-head">
            <h2>Expected</h2>
          </div>
          {expected.length ? (
            <div className="st-card is-flush">
              {expected.map((e, i) => (
                <div key={`${e.name}-${i}`} className="st-plan" data-stage-thing={`expected-${i}`} data-stage-label={e.name}>
                  <span className="st-plan-icon">
                    <CalendarClock size={18} />
                  </span>
                  <span className="st-plan-text">
                    <b>{e.name}</b>
                    <span>
                      {clock(e.from)} to {clock(e.to)} · {e.meet === "room" ? "Send up to the room" : "Wait in the lobby"}
                      {e.note ? ` · ${e.note}` : ""}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="rq-empty">Expecting someone? Add them and the front desk will be ready for them.</div>
          )}
          <button type="button" className="st-btn is-ghost is-block" onClick={() => openExpect()} data-stage-thing="visitor-expect" data-stage-label="Expect a visitor">
            <UserPlus size={17} /> Expect a visitor
          </button>
        </section>
      </div>
    </div>
  );
}
