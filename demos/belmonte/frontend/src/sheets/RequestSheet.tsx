/**
 * A front-desk request: the fields depend on the kind (housekeeping items,
 * a maintenance issue, a wake-up day and time, the car, a ride, a lost item).
 * Send is guest-only when the request costs money (the airport sedan).
 */
import { Send } from "lucide-react";
import { BottomSheet } from "../components/Shell";
import { REQUESTS } from "../data";
import { clock, day, hhmm, minutes, money } from "../lib/format";
import { bookableDates } from "../lib/rules";
import { REQUEST_META } from "../pages/Requests";
import { type Sheet, closeSheet, requestBlocked, requestFee, sendRequest, setRequestField, stayClock, toggleRequestItem } from "../state/store";
import "../styles/stay.css";

type RequestSheetT = Extract<Sheet, { kind: "request" }>;

/** Half-hour times from `from` to `to` inclusive, as HH:MM. */
function halfHours(from: number, to: number): string[] {
  const out: string[] = [];
  for (let m = Math.ceil(from / 30) * 30; m <= to; m += 30) out.push(hhmm(m));
  return out;
}
/** Now, then the next half hours (for the car and rides). */
function soonTimes(now: string, count = 10): { value: string; label: string }[] {
  const n = minutes(now);
  const next = halfHours(n + 15, Math.min(n + 15 + 30 * (count - 1), 23 * 60 + 30));
  return [{ value: now, label: `Now (${clock(now)})` }, ...next.map((t) => ({ value: t, label: clock(t) }))];
}

function TimeSelect({ value, options, onChange, label }: { value: string | null; options: { value: string; label: string }[]; onChange: (v: string | null) => void; label: string }) {
  return (
    <label className="st-field">
      <span className="st-label">{label}</span>
      <select className="st-select" value={value ?? ""} onChange={(e) => onChange(e.target.value || null)} data-stage-thing="req-time" data-stage-label={label}>
        <option value="">Choose a time</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function Details({ value, label, placeholder }: { value: string; label: string; placeholder: string }) {
  return (
    <label className="st-field">
      <span className="st-label">{label}</span>
      <textarea className="st-textarea" value={value} placeholder={placeholder} onChange={(e) => setRequestField({ details: e.target.value })} data-stage-thing="req-details" data-stage-label={label} />
    </label>
  );
}

function Fields({ sheet }: { sheet: RequestSheetT }) {
  const c = stayClock();
  switch (sheet.request) {
    case "housekeeping":
      return (
        <>
          <section className="st-section" data-stage-thing="req-items" data-stage-label="What you need" data-stage-group>
            <span className="st-label">What do you need?</span>
            <div className="st-chips">
              {REQUESTS.housekeeping.items.map((i) => (
                <button key={i.id} type="button" className="st-chip" aria-pressed={sheet.items.includes(i.id)} onClick={() => toggleRequestItem(i.id)} data-stage-thing={`req-item-${i.id}`} data-stage-label={i.label}>
                  {i.label}
                </button>
              ))}
            </div>
          </section>
          <p className="st-note">
            Usually {REQUESTS.housekeeping.eta}. {REQUESTS.housekeeping.turndown}
          </p>
        </>
      );
    case "maintenance":
      return (
        <>
          <section className="st-section" data-stage-thing="req-issues" data-stage-label="What's wrong" data-stage-group>
            <span className="st-label">What's wrong?</span>
            <div className="st-chips" role="radiogroup">
              {REQUESTS.maintenance.issues.map((i) => (
                <button key={i.id} type="button" role="radio" className="st-chip" aria-checked={sheet.issue === i.id} onClick={() => setRequestField({ issue: i.id })} data-stage-thing={`req-issue-${i.id}`} data-stage-label={i.label}>
                  {i.label}
                </button>
              ))}
            </div>
          </section>
          <Details value={sheet.details} label="Details (optional)" placeholder="For example: the bathroom light flickers" />
          <p className="st-note">We'll send {REQUESTS.maintenance.eta}.</p>
        </>
      );
    case "wakeup": {
      const dates = bookableDates(c);
      const all = halfHours(5 * 60, 11 * 60 + 30);
      const times = sheet.date === c.today ? all.filter((t) => minutes(t) > minutes(c.now)) : all;
      return (
        <>
          <section className="st-section" data-stage-thing="req-dates" data-stage-label="Day" data-stage-group>
            <span className="st-label">Day</span>
            <div className="st-chips is-scroll" role="radiogroup">
              {dates.map((d) => (
                <button
                  key={d}
                  type="button"
                  role="radio"
                  className="st-chip"
                  aria-checked={sheet.date === d}
                  onClick={() => setRequestField({ date: d, time: sheet.time && (d !== c.today || minutes(sheet.time) > minutes(c.now)) ? sheet.time : null })}
                  data-stage-thing={`req-date-${d}`}
                  data-stage-label={day(d)}
                >
                  {d === c.today ? "Today" : day(d)}
                </button>
              ))}
            </div>
          </section>
          {sheet.date && !times.length ? (
            <p className="st-note is-warn">No wake-up times left today. Choose another day.</p>
          ) : (
            <TimeSelect label="Time" value={sheet.time} options={times.map((t) => ({ value: t, label: clock(t) }))} onChange={(time) => setRequestField({ time })} />
          )}
          <p className="st-note">{REQUESTS.wakeup.note}</p>
        </>
      );
    }
    case "valet":
      return (
        <>
          <div className="rq-sheet-hero">
            <div>
              <b>Valet ticket {REQUESTS.valet.ticket}</b>
              <span>Ready in {REQUESTS.valet.eta} at the motor court.</span>
            </div>
          </div>
          <TimeSelect label="When do you need it?" value={sheet.time} options={soonTimes(c.now)} onChange={(time) => setRequestField({ time })} />
          <p className="st-note">{REQUESTS.valet.rate}</p>
        </>
      );
    case "transport": {
      const opt = REQUESTS.transport.options.find((o) => o.id === sheet.option);
      return (
        <>
          <section className="st-section" data-stage-thing="req-options" data-stage-label="Ride" data-stage-group>
            <span className="st-label">Ride</span>
            <div className="st-options" role="radiogroup">
              {REQUESTS.transport.options.map((o) => (
                <button key={o.id} type="button" role="radio" aria-checked={sheet.option === o.id} className="st-option" onClick={() => setRequestField({ option: o.id })} data-stage-thing={`req-option-${o.id}`} data-stage-label={o.label}>
                  <span className="st-radio" />
                  <span className="st-option-text">
                    <span>{o.label}</span>
                    <small>{o.note}</small>
                  </span>
                  <span className={`st-option-side${o.price === 0 ? " is-free" : ""}`}>{o.price === null ? "Metered" : o.price === 0 ? "Free" : money(o.price)}</span>
                </button>
              ))}
            </div>
          </section>
          <TimeSelect label="Pick-up time" value={sheet.time} options={soonTimes(c.now, 14)} onChange={(time) => setRequestField({ time })} />
          <label className="st-field">
            <span className="st-label">Destination</span>
            <input
              className="st-input"
              value={sheet.details}
              placeholder={opt?.id === "airport" ? "Halcyon Bay Regional" : "Where to?"}
              onChange={(e) => setRequestField({ details: e.target.value })}
              data-stage-thing="req-details"
              data-stage-label="Destination"
            />
          </label>
        </>
      );
    }
    case "lost_found":
      return (
        <>
          <Details value={sheet.details} label="What did you lose, and where?" placeholder="For example: a gray sweater, at the cliff pool yesterday afternoon" />
          <p className="st-note">{REQUESTS.lost_found.note}</p>
        </>
      );
  }
}

export default function RequestSheet({ sheet }: { sheet: RequestSheetT }) {
  const blocked = requestBlocked(sheet);
  const fee = requestFee(sheet);
  const meta = REQUEST_META[sheet.request];
  const metered = sheet.request === "transport" && REQUESTS.transport.options.find((o) => o.id === sheet.option)?.price === null;
  return (
    <BottomSheet
      title={meta.title}
      sub={meta.sub}
      onClose={closeSheet}
      footer={
        <div className="st-final">
          {fee > 0 ? (
            <div className="st-pay">
              <span>Fixed fare, on your room bill</span>
              <b>{money(fee)}</b>
            </div>
          ) : metered ? (
            <p className="st-note">Metered fare, paid to the driver.</p>
          ) : null}
          <button
            type="button"
            className="st-btn is-block"
            disabled={!!blocked}
            onClick={sendRequest}
            data-stage-thing="req-send"
            data-stage-label={fee > 0 ? `Send, ${money(fee)}` : "Send"}
            data-dock-avoid
            {...(fee > 0 ? { "data-guest-only": true } : {})}
          >
            <Send size={16} /> {fee > 0 ? `Send · ${money(fee)}` : "Send request"}
          </button>
          {blocked ? <p className="st-reason">{blocked}</p> : null}
        </div>
      }
    >
      <div className="rq-sheet">
        <Fields sheet={sheet} />
      </div>
    </BottomSheet>
  );
}
