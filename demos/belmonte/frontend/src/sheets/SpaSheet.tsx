/** Book a spa treatment: day, therapist preference, a free time, the price, and Book. */
import { BottomSheet } from "../components/Shell";
import { SPA, getTherapist, getTreatment } from "../data";
import { clock, day, money, shortDay } from "../lib/format";
import { bookableDates, spaSlots, spaTotal } from "../lib/rules";
import { type Sheet, bookSpa, closeSheet, pickSpaSlot, setSpaDate, setSpaPref, stayClock } from "../state/store";
import "../styles/experiences.css";

const hm = (t: string) => t.replace(":", "");

export default function SpaSheet({ sheet }: { sheet: Extract<Sheet, { kind: "spa" }> }) {
  const t = getTreatment(sheet.treatment_id);
  if (!t) return null;
  const c = stayClock();
  const dates = bookableDates(c);
  const slots = spaSlots(c, t.id, sheet.date, sheet.pref);
  const tot = spaTotal(t.id);
  const prefs = [
    { id: "any", label: "No preference" },
    { id: "female", label: "Female" },
    { id: "male", label: "Male" },
    ...t.therapists.map((id) => ({ id, label: getTherapist(id)?.name ?? id })),
  ];
  const picked = sheet.time && sheet.therapist_id;
  const who = sheet.therapist_id ? getTherapist(sheet.therapist_id)?.name : null;

  return (
    <BottomSheet
      title={t.name}
      sub={`${t.minutes} min · ${money(t.price)}${t.for_two ? " for two" : ""}`}
      onClose={closeSheet}
      footer={
        <div className="ex-foot">
          <div className="ex-foot-line">
            <span>{picked ? `${day(sheet.date)}, ${clock(sheet.time!)}` : "Total with service charge"}</span>
            <b>{money(tot.total)}</b>
          </div>
          {!picked ? <p className="ex-foot-why">Choose a time to book.</p> : null}
          <button type="button" className="ex-primary" disabled={!picked} onClick={bookSpa} data-stage-thing="spa-book" data-stage-label="Book" data-dock-avoid data-guest-only>
            Book · {money(tot.total)}
          </button>
        </div>
      }
    >
      <div className="ex-sheet">
        <p className="ex-muted">{t.desc}</p>

        <div className="ex-group" data-stage-thing="spa-dates" data-stage-label="Day" data-stage-group>
          <span className="ex-label">Day</span>
          <div className="ex-chips">
            {dates.map((d) => {
              const on = d === sheet.date;
              return (
                <button key={d} type="button" className={`ex-chip is-tall${on ? " is-on" : ""}`} aria-pressed={on} onClick={() => setSpaDate(d)} data-stage-thing={`spa-date-${d}`} data-stage-label={day(d)}>
                  {d === c.today ? "Today" : day(d).slice(0, 3)}
                  <small>{shortDay(d)}</small>
                </button>
              );
            })}
          </div>
        </div>

        <div className="ex-group" data-stage-thing="spa-prefs" data-stage-label="Therapist" data-stage-group>
          <span className="ex-label">Therapist</span>
          <div className="ex-chips">
            {prefs.map((p) => {
              const on = sheet.pref === p.id;
              return (
                <button key={p.id} type="button" className={`ex-chip${on ? " is-on" : ""}`} aria-pressed={on} onClick={() => setSpaPref(p.id)} data-stage-thing={`spa-pref-${p.id}`} data-stage-label={p.label}>
                  {p.label}
                </button>
              );
            })}
          </div>
          {t.for_two ? <span className="ex-hint">Two therapists side by side; the time shows the first.</span> : null}
        </div>

        <div className="ex-group" data-stage-thing="slots" data-stage-label="Times" data-stage-group>
          <div className="ex-group-head">
            <span className="ex-label">Times on {day(sheet.date)}</span>
            {slots.length ? <span className="ex-hint">{slots.length} open</span> : null}
          </div>
          {slots.length ? (
            <div className="ex-slots">
              {slots.map(([time, th]) => {
                const on = sheet.time === time && sheet.therapist_id === th;
                const name = getTherapist(th)?.name ?? th;
                return (
                  <button key={`${time}-${th}`} type="button" className={`ex-slotbtn${on ? " is-on" : ""}`} aria-pressed={on} onClick={() => pickSpaSlot(time, th)} data-stage-thing={`slot-${hm(time)}-${th}`} data-stage-label={`${clock(time)} with ${name}`}>
                    {clock(time)}
                    <small>with {name}</small>
                  </button>
                );
              })}
            </div>
          ) : (
            <p className="ex-empty">No times left on this day. Try another day or therapist.</p>
          )}
        </div>

        <div className="ex-sum" data-stage-thing="spa-summary" data-stage-label="Summary">
          <div className="ex-sum-row">
            <span>
              {t.name}, {t.minutes} min
            </span>
            <span>{money(tot.price)}</span>
          </div>
          <div className="ex-sum-row">
            <span>Spa service charge {SPA.service_charge_pct}%</span>
            <span>{money(tot.service)}</span>
          </div>
          {who ? (
            <div className="ex-sum-row">
              <span>Therapist</span>
              <span>{who}</span>
            </div>
          ) : null}
          <div className="ex-sum-row is-total">
            <span>Total, to your room</span>
            <b>{money(tot.total)}</b>
          </div>
        </div>
        <p className="ex-policy">
          {SPA.arrive} {SPA.cancellation}
        </p>
      </div>
    </BottomSheet>
  );
}
