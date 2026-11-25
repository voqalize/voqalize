/**
 * Requests: visitors waiting at the desk, the front-desk services (each opens
 * the request sheet), and what the guest has already asked for.
 */
import { BedDouble, CarFront, Check, ChevronRight, Clock4, type LucideIcon, PackageSearch, Plane, Users, Wrench } from "lucide-react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/Shell";
import { REQUESTS } from "../data";
import { type RequestKind, openRequest, useStay } from "../state/store";
import "../styles/stay.css";

export const REQUEST_META: Record<RequestKind, { title: string; sub: string; icon: LucideIcon }> = {
  housekeeping: { title: "Housekeeping", sub: `Towels, pillows, turndown. ${cap(REQUESTS.housekeeping.eta)}.`, icon: BedDouble },
  maintenance: { title: "Maintenance", sub: "Something not working in the room", icon: Wrench },
  wakeup: { title: "Wake-up call", sub: "A call to your room phone", icon: Clock4 },
  valet: { title: "Bring my car", sub: `Ticket ${REQUESTS.valet.ticket}, ${REQUESTS.valet.eta}`, icon: CarFront },
  transport: { title: "Transport", sub: "House car, airport sedan, taxi", icon: Plane },
  lost_found: { title: "Lost and found", sub: "Tell us what's missing", icon: PackageSearch },
};
function cap(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
const KINDS: RequestKind[] = ["housekeeping", "maintenance", "wakeup", "valet", "transport", "lost_found"];

export function Requests() {
  const visitors = useStay((s) => s.visitors);
  const requests = useStay((s) => s.requests);
  const pending = visitors.filter((v) => v.status === "pending");
  return (
    <div className="page st-page" data-stage-place="requests">
      <PageHeader title="Requests" sub="The front desk, in your pocket" />
      <div className="st-body">
        <Link
          to="/visitors"
          className={`rq-visitors${pending.length ? "" : " is-calm"}`}
          data-stage-thing="visitors-card"
          data-stage-label={pending.length ? `${pending.length} visitors waiting` : "Visitors"}
        >
          <span className="rq-visitors-icon">
            <Users size={21} />
            {pending.length ? <span className="rq-count">{pending.length}</span> : null}
          </span>
          <div>
            <b>{pending.length ? `${pending.length} ${pending.length === 1 ? "visitor is" : "visitors are"} waiting` : "Visitors"}</b>
            <span>{pending.length ? pending.map((v) => v.name).join(", ") : "Nobody waiting. Tell the desk who to expect."}</span>
          </div>
          <ChevronRight size={18} />
        </Link>

        <section className="st-section">
          <div className="st-section-head">
            <h2>How can we help?</h2>
          </div>
          <div className="rq-tiles">
            {KINDS.map((k) => {
              const m = REQUEST_META[k];
              const Icon = m.icon;
              return (
                <button key={k} type="button" className="rq-tile" onClick={() => openRequest(k)} data-stage-thing={`request-${k}`} data-stage-label={m.title}>
                  <span className="rq-tile-icon">
                    <Icon size={19} />
                  </span>
                  <b>{m.title}</b>
                  <span>{m.sub}</span>
                </button>
              );
            })}
          </div>
        </section>

        <section className="st-section">
          <div className="st-section-head">
            <h2>Your requests</h2>
          </div>
          {requests.length ? (
            <div className="st-card is-flush">
              {[...requests].reverse().map((r) => {
                const Icon = REQUEST_META[r.kind].icon;
                return (
                  <div key={r.id} className="st-plan" data-stage-thing={`sent-${r.id}`} data-stage-label={r.label}>
                    <span className="st-plan-icon">
                      <Icon size={18} />
                    </span>
                    <span className="st-plan-text">
                      <b>{r.label}</b>
                      <span>{cap(r.eta)}</span>
                    </span>
                    <span className="rq-status is-sent">
                      <Check size={12} /> Sent
                    </span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="rq-empty">Nothing yet. Anything you ask for shows up here with its status.</div>
          )}
        </section>
      </div>
    </div>
  );
}
