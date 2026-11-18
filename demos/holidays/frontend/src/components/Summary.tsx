/**
 * The trip summary beside the builder, and the price breakdown it shares with
 * the package step and checkout. Every line here is the engine's number.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { BedDouble, CalendarDays, ChevronUp, Plane, Ticket, Users } from "lucide-react";
import { getActivity, getDestination, getFlight, originName } from "../data";
import { type Trip, activityPrice, day1, flightPrice, hotelLines, pax, price, rooms, stays, transfers } from "../engine";
import { date, money, plural, shortDate } from "../format";
import { setStep, useTrip } from "../state/trip";
import { DestinationArt } from "./Art";

export function travellers(t: Trip): string {
  const b = t.brief;
  const kids = b.kids.length ? `, ${plural(b.kids.length, "child", "children")} (${b.kids.join(", ")})` : "";
  return `${plural(b.adults, "adult")}${kids}`;
}

export function Breakdown({ trip, detail = true }: { trip: Trip; detail?: boolean }) {
  const p = price(trip);
  const f = getFlight(trip.flight_id);
  const fp = f ? flightPrice(f, trip.brief) : null;
  const legs = transfers(trip);
  return (
    <div className="breakdown" data-stage-thing="breakdown" data-stage-label="Price breakdown">
      <div className="bd-row">
        <span>Flights{fp && detail ? <small> {money(fp.adult)} × adult{trip.brief.kids.length ? ", child and infant fares" : ""}</small> : null}</span>
        <b>{money(p.flights)}</b>
      </div>
      {detail ? (
        hotelLines(trip).map((l) => (
          <div className="bd-row sub" key={l.city.id}>
            <span>
              {l.hotel ? l.hotel.name : `${l.city.name}: hotel to choose`}
              <small>
                {" "}
                {plural(l.nights, "night")} × {plural(rooms(trip.brief), "room")}
              </small>
            </span>
            <b>{money(l.price)}</b>
          </div>
        ))
      ) : (
        <div className="bd-row">
          <span>Hotels</span>
          <b>{money(p.hotels)}</b>
        </div>
      )}
      {detail ? (
        legs.map((l) => (
          <div className="bd-row sub" key={l.id}>
            <span>
              {l.label}
              <small> {l.mode}</small>
            </span>
            <b>{l.price ? money(l.price) : "Included"}</b>
          </div>
        ))
      ) : (
        <div className="bd-row">
          <span>Transfers</span>
          <b>{money(p.transfers)}</b>
        </div>
      )}
      <div className="bd-row">
        <span>Activities{detail ? <small> {plural(trip.activities.length, "experience")}</small> : null}</span>
        <b>{money(p.activities)}</b>
      </div>
      <div className="bd-row">
        <span>
          GST 5%<small> on hotels, transfers and activities</small>
        </span>
        <b>{money(p.gst)}</b>
      </div>
      <div className="bd-total" data-stage-thing="total" data-stage-label="Total price">
        <span>
          Total
          <small>{money(p.per_person)} per person</small>
        </span>
        <b>{money(p.total)}</b>
      </div>
    </div>
  );
}

export function TripSummary() {
  const trip = useTrip((s) => s.trip);
  const [open, setOpen] = useState(false);
  const d = getDestination(trip.brief.destination);
  const f = getFlight(trip.flight_id);
  const p = price(trip);
  const first = day1(trip);
  const s = stays(trip);
  const complete = !!f && s.length > 0 && s.every((x) => trip.hotels[x.city.id]);
  return (
    <aside className={`summary${open ? " is-open" : ""}`} aria-label="Your trip">
      <button type="button" className="summary-bar" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span>
          {d ? d.name : "Your trip"} · <b>{money(p.total)}</b>
        </span>
        <ChevronUp size={18} />
      </button>
      <div className="summary-inner">
        <div className="summary-head">
          {d ? <DestinationArt id={d.id} hue={d.hue} className="summary-art" /> : <div className="summary-art empty" />}
          <div>
            <p className="summary-kicker">Your trip</p>
            <h3>{d ? d.name : "Pick a destination"}</h3>
            <p className="muted">
              {trip.brief.from_city ? `from ${originName(trip.brief.from_city)}` : "Choose where you fly from"}
              {trip.brief.nights ? ` · ${plural(trip.brief.nights, "night")}` : ""}
            </p>
          </div>
        </div>
        <ul className="summary-lines">
          <li>
            <CalendarDays size={15} />
            <span>{first ? `${date(first)} → ${date(new Date(Date.parse(`${first}T00:00:00Z`) + (trip.brief.nights ?? 0) * 864e5).toISOString().slice(0, 10))}` : "Dates to choose"}</span>
          </li>
          <li>
            <Users size={15} />
            <span>{travellers(trip)}</span>
          </li>
          <li>
            <Plane size={15} />
            <span>
              {f ? (
                <>
                  {f.airline_name} · {f.stops ? `${plural(f.stops, "stop")}` : "nonstop"}
                  <button type="button" className="link" onClick={() => setStep("flights")}>
                    change
                  </button>
                </>
              ) : (
                <button type="button" className="link" onClick={() => setStep("flights")}>
                  Choose a flight
                </button>
              )}
            </span>
          </li>
          {s.map(({ city, nights }) => {
            const pick = trip.hotels[city.id];
            const h = pick ? city.hotels.find((x) => x.id === pick.hotel_id) : null;
            return (
              <li key={city.id}>
                <BedDouble size={15} />
                <span>
                  <b>{city.name}</b> {nights}N · {h ? h.name : "hotel to choose"}
                  <button type="button" className="link" onClick={() => setStep("hotels")}>
                    {h ? "swap" : "choose"}
                  </button>
                </span>
              </li>
            );
          })}
          <li>
            <Ticket size={15} />
            <span>
              {trip.activities.length ? plural(trip.activities.length, "experience") : "No experiences yet"}
              <button type="button" className="link" onClick={() => setStep("days")}>
                {trip.activities.length ? "edit" : "add"}
              </button>
            </span>
          </li>
        </ul>
        {d && <Breakdown trip={trip} detail={false} />}
        {complete ? (
          <Link to="/checkout" className="btn btn-primary btn-block" data-dock-avoid>
            Review & pay {money(p.total)}
          </Link>
        ) : (
          <p className="summary-note">{d ? "Choose a flight and a hotel in each city to book." : "Start with the trip details on the left."}</p>
        )}
        {pax(trip.brief) > 0 && f && <p className="summary-fine">Flights {shortDate(trip.brief.start_date)} · fares include airport taxes</p>}
      </div>
    </aside>
  );
}

export const activityLine = (id: string, t: Trip) => {
  const a = getActivity(id);
  return a ? `${a.name} · ${money(activityPrice(a, t.brief))}` : id;
};
