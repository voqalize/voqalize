/** Meeting rooms: headcount, layout and date filters, room cards with capacity, rates and that day's free blocks. */
import { Check, Minus, MonitorSpeaker, Plus, Ruler, X } from "lucide-react";
import { PageHeader } from "../components/Shell";
import { MEETINGS } from "../data";
import { clock, day, price, shortDay } from "../lib/format";
import { blockSpan, roomFree, roomsFor } from "../lib/rules";
import { openMeeting, setMeetingFilter, useStay } from "../state/store";
import { BookingList, ExperienceTabs } from "./Spa";
import "../styles/experiences.css";

const LAYOUTS = Object.entries(MEETINGS.layout_labels);
const MAX_HEAD = Math.max(...MEETINGS.rooms.flatMap((r) => Object.values(r.layouts)));

export function Meetings() {
  const f = useStay((s) => s.meetingFilter);
  const booked = useStay((s) => s.bookings.some((b) => b.kind === "meeting"));
  const fits = new Set(roomsFor(f.headcount, f.layout).map((r) => r.id));
  const head = f.headcount ?? 0;
  const setHead = (n: number) => setMeetingFilter({ headcount: n > 0 ? Math.min(n, MAX_HEAD) : null });
  const date = MEETINGS.dates.includes(f.date) ? f.date : MEETINGS.dates[0];

  return (
    <div className="page" data-stage-place="meetings">
      <PageHeader title="Experiences" sub="Book the spa, the courses and the coast" tabs={<ExperienceTabs />} />
      <div className="ex-wrap">
        <div className="ex-section-title">
          <h2>Meeting rooms</h2>
          <span>
            {clock(MEETINGS.hours_from)} to {clock(MEETINGS.hours_to)}
          </span>
        </div>

        <section className="ex-filters" aria-label="Find a room">
          <div className="ex-filter-row">
            <span className="ex-label">People</span>
            <div className="ex-stepper" data-stage-thing="meeting-headcount" data-stage-label={head ? `${head} people` : "Headcount"}>
              <button type="button" aria-label="Fewer" disabled={head <= 0} onClick={() => setHead(head - (head > 10 ? 5 : 1))}>
                <Minus size={16} />
              </button>
              <input type="number" inputMode="numeric" min={0} max={MAX_HEAD} aria-label="Number of people" placeholder="Any" value={head || ""} onChange={(e) => setHead(Number(e.target.value) || 0)} />
              <button type="button" aria-label="More" disabled={head >= MAX_HEAD} onClick={() => setHead(head + (head >= 10 ? 5 : 1))}>
                <Plus size={16} />
              </button>
            </div>
          </div>
          <div className="ex-group" data-stage-thing="meeting-layouts" data-stage-label="Layout" data-stage-group>
            <span className="ex-label">Layout</span>
            <div className="ex-chips is-wrap">
              {LAYOUTS.map(([id, label]) => {
                const on = f.layout === id;
                return (
                  <button key={id} type="button" className={`ex-chip${on ? " is-on" : ""}`} aria-pressed={on} onClick={() => setMeetingFilter({ layout: on ? null : id })} data-stage-thing={`meeting-layout-${id}`} data-stage-label={label}>
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="ex-group" data-stage-thing="meeting-dates" data-stage-label="Date" data-stage-group>
            <span className="ex-label">Date</span>
            <div className="ex-chips">
              {MEETINGS.dates.map((d) => {
                const on = d === date;
                return (
                  <button key={d} type="button" className={`ex-chip is-tall${on ? " is-on" : ""}`} aria-pressed={on} onClick={() => setMeetingFilter({ date: d })} data-stage-thing={`meeting-date-${d}`} data-stage-label={day(d)}>
                    {day(d).slice(0, 3)}
                    <small>{shortDay(d)}</small>
                  </button>
                );
              })}
            </div>
          </div>
        </section>

        {booked ? <BookingList kind="meeting" /> : null}

        {MEETINGS.rooms.map((r) => {
          const ok = fits.has(r.id);
          const layoutLabel = f.layout ? MEETINGS.layout_labels[f.layout] : null;
          const why = ok
            ? null
            : f.layout && !(f.layout in r.layouts)
              ? `No ${layoutLabel?.toLowerCase()} layout in this room.`
              : `Seats ${f.layout ? r.layouts[f.layout] : Math.max(...Object.values(r.layouts))}${layoutLabel ? ` ${layoutLabel.toLowerCase()}` : ""}; you need ${head}.`;
          const taken = MEETINGS.taken[r.id]?.[date] ?? [];
          return (
            <button key={r.id} type="button" className={`ex-card${ok ? "" : " is-dim"}`} onClick={() => openMeeting(r.id)} data-stage-thing={`room-${r.id}`} data-stage-label={r.name}>
              <div className="ex-card-head">
                <div>
                  <h3>{r.name}</h3>
                  <p>{r.desc}</p>
                </div>
                <div className="ex-price">
                  <b>{price(r.rates.hour)}</b>
                  <small>per hour</small>
                </div>
              </div>
              <div className="ex-card-meta">
                <span>
                  <Ruler size={13} /> {r.sqft.toLocaleString("en-US")} sq ft
                </span>
                <span>
                  <MonitorSpeaker size={13} /> {r.av}
                </span>
              </div>
              <div className="ex-caps">
                {Object.entries(r.layouts).map(([id, cap]) => (
                  <div key={id} className={`ex-cap${f.layout === id ? " is-on" : ""}`}>
                    <b>{cap}</b>
                    <span>{MEETINGS.layout_labels[id] ?? id}</span>
                  </div>
                ))}
              </div>
              <div className="ex-rates">
                <div>
                  <b>{price(r.rates.hour)}</b>
                  <span>Hour</span>
                </div>
                <div>
                  <b>{price(r.rates.half)}</b>
                  <span>Half day</span>
                </div>
                <div>
                  <b>{price(r.rates.full)}</b>
                  <span>Full day</span>
                </div>
              </div>
              <div className="ex-avail" aria-label={`Availability on ${day(date)}`}>
                {MEETINGS.blocks
                  .filter((b) => b.id !== "hours")
                  .map((b) => {
                    const span = blockSpan(b.id, null, null);
                    const free = !!span && roomFree(r.id, date, span);
                    return (
                      <span key={b.id} className={`ex-slot${free ? "" : " is-taken"}`}>
                        {free ? <Check size={11} strokeWidth={3} /> : <X size={11} strokeWidth={3} />}
                        {b.label.replace("Half day, ", "")}
                      </span>
                    );
                  })}
              </div>
              {taken.length ? (
                <p className="ex-muted" style={{ marginTop: 6 }}>
                  {day(date)}: booked {taken.map(([a, b]) => `${clock(a)} to ${clock(b)}`).join(", ")}
                </p>
              ) : (
                <p className="ex-muted" style={{ marginTop: 6 }}>
                  Free all day {day(date)}
                </p>
              )}
              {why ? <p className="ex-why">{why}</p> : null}
            </button>
          );
        })}

        <p className="ex-policy">{MEETINGS.policy}</p>
      </div>
    </div>
  );
}
