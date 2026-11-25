/** Book an activity: day, time, guests, the total, and Book. */
import { Minus, Plus } from "lucide-react";
import { BottomSheet } from "../components/Shell";
import { getActivity, getPlace } from "../data";
import { clock, day, money, price, shortDay } from "../lib/format";
import { activityTimes, activityTotal, bookableDates } from "../lib/rules";
import { type Sheet, bookActivity, closeSheet, setActivityField, stayClock } from "../state/store";
import "../styles/experiences.css";

const hm = (t: string) => t.replace(":", "");

export default function ActivitySheet({ sheet }: { sheet: Extract<Sheet, { kind: "activity" }> }) {
  const a = getActivity(sheet.activity_id);
  if (!a) return null;
  const c = stayClock();
  const dates = bookableDates(c);
  const times = activityTimes(c, a.id, sheet.date);
  const max = a.capacity ?? 10;
  const total = activityTotal(a.id, sheet.guests);
  const timeOk = !!sheet.time && times.includes(sheet.time);
  const unit = a.per ?? "guest";
  const place = getPlace(a.place);
  const countLabel = ({ court: "Courts", child: "Children", player: "Players" } as Record<string, string>)[unit.split(",")[0]] ?? "Guests";

  return (
    <BottomSheet
      title={a.name}
      sub={`${a.price ? `${price(a.price)} per ${unit}` : "Free"}${place ? ` · ${place.name}` : ""}`}
      onClose={closeSheet}
      footer={
        <div className="ex-foot">
          <div className="ex-foot-line">
            <span>{timeOk ? `${day(sheet.date)}, ${clock(sheet.time!)}` : "Total"}</span>
            <b>{total ? money(total) : "Free"}</b>
          </div>
          {!timeOk ? <p className="ex-foot-why">Choose a time to book.</p> : null}
          <button type="button" className="ex-primary" disabled={!timeOk} onClick={bookActivity} data-stage-thing="act-book" data-stage-label="Book" data-dock-avoid data-guest-only>
            Book{total ? ` · ${money(total)}` : ""}
          </button>
        </div>
      }
    >
      <div className="ex-sheet">
        <p className="ex-muted">
          {a.desc} {a.hours}.
        </p>
        {a.min_age ? <p className="ex-note">Guests {a.min_age} and over only; bring a photo ID.</p> : null}

        <div className="ex-group" data-stage-thing="act-dates" data-stage-label="Day" data-stage-group>
          <span className="ex-label">Day</span>
          <div className="ex-chips">
            {dates.map((d) => {
              const on = d === sheet.date;
              return (
                <button key={d} type="button" className={`ex-chip is-tall${on ? " is-on" : ""}`} aria-pressed={on} onClick={() => setActivityField({ date: d, time: null })} data-stage-thing={`act-date-${d}`} data-stage-label={day(d)}>
                  {d === c.today ? "Today" : day(d).slice(0, 3)}
                  <small>{shortDay(d)}</small>
                </button>
              );
            })}
          </div>
        </div>

        <div className="ex-group" data-stage-thing="act-times" data-stage-label="Time" data-stage-group>
          <span className="ex-label">Time</span>
          {times.length ? (
            <div className="ex-chips is-wrap">
              {times.map((t) => {
                const on = sheet.time === t;
                return (
                  <button key={t} type="button" className={`ex-chip${on ? " is-on" : ""}`} aria-pressed={on} onClick={() => setActivityField({ time: t })} data-stage-thing={`act-time-${hm(t)}`} data-stage-label={clock(t)}>
                    {clock(t)}
                  </button>
                );
              })}
            </div>
          ) : (
            <p className="ex-empty">No more times on this day. Try another day.</p>
          )}
        </div>

        <div className="ex-group">
          <div className="ex-group-head">
            <span className="ex-label">{countLabel}</span>
            <span className="ex-hint">Up to {max}</span>
          </div>
          <div className="ex-stepper" data-stage-thing="act-guests" data-stage-label={`${countLabel} ${sheet.guests}`} style={{ alignSelf: "flex-start" }}>
            <button type="button" aria-label="One fewer" disabled={sheet.guests <= 1} onClick={() => setActivityField({ guests: sheet.guests - 1 })}>
              <Minus size={16} />
            </button>
            <output aria-live="polite">{sheet.guests}</output>
            <button type="button" aria-label="One more" disabled={sheet.guests >= max} onClick={() => setActivityField({ guests: sheet.guests + 1 })}>
              <Plus size={16} />
            </button>
          </div>
        </div>

        <div className="ex-sum">
          <div className="ex-sum-row">
            <span>{a.price ? `${price(a.price)} per ${unit}` : "Complimentary"}</span>
            <span>× {sheet.guests}</span>
          </div>
          <div className="ex-sum-row is-total">
            <span>Total{total ? ", to your room" : ""}</span>
            <b>{total ? money(total) : "Free"}</b>
          </div>
        </div>
      </div>
    </BottomSheet>
  );
}
