/** Tell the desk to expect a visitor: name, a window until 10:00 PM, where to meet, a note. "Add visitor" is the guest's own press. */
import { UserPlus } from "lucide-react";
import { BottomSheet } from "../components/Shell";
import { VISITORS } from "../data";
import { clock, hhmm, minutes } from "../lib/format";
import { type Sheet, addExpected, closeSheet, setExpectField, stayClock } from "../state/store";
import "../styles/stay.css";

function halfHoursUntil(now: string, until: string): string[] {
  const out: string[] = [];
  for (let m = Math.ceil(minutes(now) / 30) * 30; m <= minutes(until); m += 30) out.push(hhmm(m));
  return out;
}

export default function ExpectSheet({ sheet }: { sheet: Extract<Sheet, { kind: "expect" }> }) {
  const times = halfHoursUntil(stayClock().now, VISITORS.until);
  const fromTimes = times.slice(0, -1);
  const toTimes = sheet.from ? times.filter((t) => minutes(t) > minutes(sheet.from)) : times.slice(1);
  const blocked = !sheet.name.trim() ? "Add the visitor's name." : !sheet.from || !sheet.to ? "Choose when they'll arrive." : !sheet.meet ? "Choose where to meet." : null;
  return (
    <BottomSheet
      title="Expect a visitor"
      sub={`Today, until ${clock(VISITORS.until)}`}
      onClose={closeSheet}
      footer={
        <div className="st-final">
          <button type="button" className="st-btn is-block" disabled={!!blocked} onClick={addExpected} data-stage-thing="expect-add" data-stage-label="Add visitor" data-dock-avoid data-guest-only>
            <UserPlus size={17} /> Add visitor
          </button>
          {blocked ? <p className="st-reason">{blocked}</p> : null}
        </div>
      }
    >
      <div className="rq-sheet">
        <label className="st-field">
          <span className="st-label">Visitor's name</span>
          <input className="st-input" value={sheet.name} placeholder="Full name" autoComplete="off" onChange={(e) => setExpectField({ name: e.target.value })} data-stage-thing="expect-name" data-stage-label="Visitor's name" />
        </label>
        <div className="st-field-pair">
          <label className="st-field">
            <span className="st-label">From</span>
            <select
              className="st-select"
              value={sheet.from}
              onChange={(e) => {
                const from = e.target.value;
                setExpectField({ from, to: sheet.to && from && minutes(sheet.to) <= minutes(from) ? "" : sheet.to });
              }}
              data-stage-thing="expect-from"
              data-stage-label="From"
            >
              <option value="">Choose</option>
              {fromTimes.map((t) => (
                <option key={t} value={t}>
                  {clock(t)}
                </option>
              ))}
            </select>
          </label>
          <label className="st-field">
            <span className="st-label">To</span>
            <select className="st-select" value={sheet.to} onChange={(e) => setExpectField({ to: e.target.value })} data-stage-thing="expect-to" data-stage-label="To">
              <option value="">Choose</option>
              {toTimes.map((t) => (
                <option key={t} value={t}>
                  {clock(t)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <section className="st-section" data-stage-thing="meet" data-stage-label="Where to meet" data-stage-group>
          <span className="st-label">When they arrive</span>
          <div className="st-options" role="radiogroup" aria-label="Where to meet">
            {VISITORS.meet.map((m) => (
              <button
                key={m.id}
                type="button"
                role="radio"
                aria-checked={sheet.meet === m.id}
                className="st-option"
                onClick={() => setExpectField({ meet: m.id as "room" | "lobby" })}
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
        <label className="st-field">
          <span className="st-label">Note for the desk (optional)</span>
          <input className="st-input" value={sheet.note} placeholder="For example: dropping off a package" onChange={(e) => setExpectField({ note: e.target.value })} data-stage-thing="expect-note" data-stage-label="Note" />
        </label>
        <p className="st-note">{VISITORS.rule}</p>
      </div>
    </BottomSheet>
  );
}
