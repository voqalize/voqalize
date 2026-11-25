/** Request a meeting room: date, block or hours, headcount, layout, catering, AV, the quote, and Request booking. */
import { Check, Minus, Plus } from "lucide-react";
import { BottomSheet } from "../components/Shell";
import { HOTEL, MEETINGS, getMeetingRoom } from "../data";
import { clock, day, hhmm, minutes, money, price, shortDay } from "../lib/format";
import { blockSpan, meetingQuote, roomFree } from "../lib/rules";
import { type Sheet, closeSheet, requestMeeting, setMeetingField } from "../state/store";
import "../styles/experiences.css";

const START_TIMES: string[] = [];
for (let n = minutes(MEETINGS.hours_from); n <= minutes(MEETINGS.hours_to) - 60; n += 30) START_TIMES.push(hhmm(n));

const toggle = (list: string[], id: string) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);

export default function MeetingSheet({ sheet }: { sheet: Extract<Sheet, { kind: "meeting" }> }) {
  const r = getMeetingRoom(sheet.room_id);
  if (!r) return null;
  const cap = r.layouts[sheet.layout] ?? 0;
  const span = blockSpan(sheet.block, sheet.start, sheet.hours);
  const free = !!span && roomFree(r.id, sheet.date, span);
  const q = meetingQuote(r.id, sheet.block, sheet.hours, sheet.headcount, sheet.catering, sheet.av);
  const maxHours = sheet.start ? Math.floor((minutes(MEETINGS.hours_to) - minutes(sheet.start)) / 60) : 0;
  const layoutLabel = MEETINGS.layout_labels[sheet.layout] ?? sheet.layout;
  const blocked = !sheet.block
    ? "Choose a time block."
    : !span
    ? "Choose a start time and how many hours."
    : !free
      ? "The room is booked for part of that time. Choose another block or time."
      : !sheet.layout
        ? "Choose a layout."
      : sheet.headcount < 1
        ? "Add how many people are coming."
        : sheet.headcount > cap
          ? `${layoutLabel} seats ${cap} in this room.`
          : null;
  const taken = MEETINGS.taken[r.id]?.[sheet.date] ?? [];

  return (
    <BottomSheet
      title={r.name}
      sub={`${r.sqft.toLocaleString("en-US")} sq ft · from ${price(r.rates.hour)} an hour`}
      onClose={closeSheet}
      footer={
        <div className="ex-foot">
          <div className="ex-foot-line">
            <span>Estimated total</span>
            <b>{money(q.total)}</b>
          </div>
          {blocked ? <p className="ex-foot-why">{blocked}</p> : null}
          <button type="button" className="ex-primary" disabled={!!blocked} onClick={requestMeeting} data-stage-thing="mtg-request" data-stage-label="Request booking" data-dock-avoid data-guest-only>
            Request booking · {money(q.total)}
          </button>
        </div>
      }
    >
      <div className="ex-sheet">
        <div className="ex-group" data-stage-thing="mtg-dates" data-stage-label="Date" data-stage-group>
          <span className="ex-label">Date</span>
          <div className="ex-chips">
            {MEETINGS.dates.map((d) => {
              const on = d === sheet.date;
              return (
                <button key={d} type="button" className={`ex-chip is-tall${on ? " is-on" : ""}`} aria-pressed={on} onClick={() => setMeetingField({ date: d })} data-stage-thing={`mtg-date-${d}`} data-stage-label={day(d)}>
                  {day(d).slice(0, 3)}
                  <small>{shortDay(d)}</small>
                </button>
              );
            })}
          </div>
          <span className="ex-hint">{taken.length ? `Already booked ${taken.map(([a, b]) => `${clock(a)} to ${clock(b)}`).join(", ")}` : `Free all day ${day(sheet.date)}`}</span>
        </div>

        <div className="ex-group" data-stage-thing="mtg-blocks" data-stage-label="Time" data-stage-group>
          <span className="ex-label">Time</span>
          <div className="ex-chips is-wrap">
            {MEETINGS.blocks.map((b) => {
              const on = sheet.block === b.id;
              const s = b.id === "hours" ? null : blockSpan(b.id, null, null);
              const open = b.id === "hours" || (!!s && roomFree(r.id, sheet.date, s));
              const rate = b.rate === "half" ? r.rates.half : b.rate === "full" ? r.rates.full : r.rates.hour;
              return (
                <button
                  key={b.id}
                  type="button"
                  className={`ex-chip is-tall${on ? " is-on" : ""}`}
                  aria-pressed={on}
                  disabled={!open}
                  title={open ? undefined : "Booked"}
                  onClick={() => setMeetingField({ block: b.id })}
                  data-stage-thing={`mtg-block-${b.id}`}
                  data-stage-label={b.label}
                >
                  {b.label}
                  <small>{b.id === "hours" ? `${price(rate)} an hour` : `${clock(b.from!)}–${clock(b.to!)} · ${price(rate)}`}</small>
                </button>
              );
            })}
          </div>
        </div>

        {sheet.block === "hours" ? (
          <div className="ex-filter-row">
            <label className="ex-group" style={{ flex: 1 }}>
              <span className="ex-label">Start</span>
              <select
                className="ex-select"
                value={sheet.start ?? ""}
                onChange={(e) => {
                  const start = e.target.value || null;
                  const room = start ? Math.floor((minutes(MEETINGS.hours_to) - minutes(start)) / 60) : 0;
                  setMeetingField({ start, hours: sheet.hours ? Math.min(sheet.hours, room) : sheet.hours });
                }}
                data-stage-thing="mtg-start"
                data-stage-label="Start time"
              >
                <option value="">Choose</option>
                {START_TIMES.map((t) => (
                  <option key={t} value={t}>
                    {clock(t)}
                  </option>
                ))}
              </select>
            </label>
            <div className="ex-group">
              <span className="ex-label">Hours</span>
              <div className="ex-stepper" data-stage-thing="mtg-hours" data-stage-label={`${sheet.hours ?? 0} hours`}>
                <button type="button" aria-label="One hour less" disabled={!sheet.hours || sheet.hours <= 1} onClick={() => setMeetingField({ hours: (sheet.hours ?? 1) - 1 })}>
                  <Minus size={16} />
                </button>
                <output>{sheet.hours ?? "–"}</output>
                <button type="button" aria-label="One hour more" disabled={!sheet.start || (sheet.hours ?? 0) >= maxHours} onClick={() => setMeetingField({ hours: (sheet.hours ?? 0) + 1 })}>
                  <Plus size={16} />
                </button>
              </div>
            </div>
          </div>
        ) : null}

        <div className="ex-group" data-stage-thing="mtg-layouts" data-stage-label="Layout" data-stage-group>
          <span className="ex-label">Layout</span>
          <div className="ex-chips is-wrap">
            {Object.entries(r.layouts).map(([id, n]) => {
              const on = sheet.layout === id;
              return (
                <button key={id} type="button" className={`ex-chip is-tall${on ? " is-on" : ""}`} aria-pressed={on} onClick={() => setMeetingField({ layout: id })} data-stage-thing={`mtg-layout-${id}`} data-stage-label={MEETINGS.layout_labels[id] ?? id}>
                  {MEETINGS.layout_labels[id] ?? id}
                  <small>up to {n}</small>
                </button>
              );
            })}
          </div>
        </div>

        <div className="ex-filter-row">
          <div>
            <span className="ex-label">People</span>
            <p className="ex-muted">Up to {cap} in {layoutLabel.toLowerCase()}</p>
          </div>
          <div className="ex-stepper" data-stage-thing="mtg-headcount" data-stage-label={`${sheet.headcount} people`}>
            <button type="button" aria-label="Fewer" disabled={sheet.headcount <= 1} onClick={() => setMeetingField({ headcount: Math.min(cap, sheet.headcount - 1) })}>
              <Minus size={16} />
            </button>
            <input
              type="number"
              inputMode="numeric"
              min={1}
              max={cap}
              aria-label="Number of people"
              value={sheet.headcount || ""}
              onChange={(e) => setMeetingField({ headcount: Math.max(0, Math.min(cap, Number(e.target.value) || 0)) })}
            />
            <button type="button" aria-label="More" disabled={sheet.headcount >= cap} onClick={() => setMeetingField({ headcount: sheet.headcount + 1 })}>
              <Plus size={16} />
            </button>
          </div>
        </div>

        <div className="ex-group" data-stage-thing="mtg-catering" data-stage-label="Catering" data-stage-group>
          <div className="ex-group-head">
            <span className="ex-label">Catering</span>
            <span className="ex-hint">Per person</span>
          </div>
          <div className="ex-toggles">
            {MEETINGS.catering.map((c) => {
              const on = sheet.catering.includes(c.id);
              return (
                <button key={c.id} type="button" role="checkbox" aria-checked={on} className={`ex-toggle${on ? " is-on" : ""}`} onClick={() => setMeetingField({ catering: toggle(sheet.catering, c.id) })} data-stage-thing={`mtg-catering-${c.id}`} data-stage-label={c.name}>
                  <span className="ex-check">{on ? <Check size={13} strokeWidth={3} /> : null}</span>
                  <span>{c.name}</span>
                  <em>{price(c.per_person)}</em>
                </button>
              );
            })}
          </div>
        </div>

        <div className="ex-group" data-stage-thing="mtg-avs" data-stage-label="AV" data-stage-group>
          <div className="ex-group-head">
            <span className="ex-label">AV add-ons</span>
            <span className="ex-hint">Built in: {r.av}</span>
          </div>
          <div className="ex-toggles">
            {MEETINGS.av_addons.map((a) => {
              const on = sheet.av.includes(a.id);
              return (
                <button key={a.id} type="button" role="checkbox" aria-checked={on} className={`ex-toggle${on ? " is-on" : ""}`} onClick={() => setMeetingField({ av: toggle(sheet.av, a.id) })} data-stage-thing={`mtg-av-${a.id}`} data-stage-label={a.name}>
                  <span className="ex-check">{on ? <Check size={13} strokeWidth={3} /> : null}</span>
                  <span>{a.name}</span>
                  <em>
                    {price(a.price)}
                    {a.per_hour ? "/hr" : ""}
                  </em>
                </button>
              );
            })}
          </div>
        </div>

        <div className="ex-sum" data-stage-thing="mtg-total" data-stage-label={`Estimated total ${money(q.total)}`}>
          <div className="ex-sum-row">
            <span>Room{sheet.block === "hours" ? `, ${q.hours} h` : ""}</span>
            <span>{money(q.room)}</span>
          </div>
          <div className="ex-sum-row">
            <span>Catering, {sheet.headcount} people</span>
            <span>{money(q.catering)}</span>
          </div>
          <div className="ex-sum-row">
            <span>F&amp;B service {MEETINGS.fb_service_pct}%</span>
            <span>{money(q.fb_service)}</span>
          </div>
          <div className="ex-sum-row">
            <span>Sales tax {HOTEL.sales_tax_pct}% on F&amp;B</span>
            <span>{money(q.tax)}</span>
          </div>
          <div className="ex-sum-row">
            <span>AV add-ons</span>
            <span>{money(q.av)}</span>
          </div>
          <div className="ex-sum-row is-total">
            <span>Estimated total</span>
            <b>{money(q.total)}</b>
          </div>
        </div>
        <p className="ex-policy">{MEETINGS.policy}</p>
      </div>
    </BottomSheet>
  );
}
