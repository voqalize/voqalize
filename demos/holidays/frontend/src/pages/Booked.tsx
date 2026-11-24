import { Link } from "react-router-dom";
import { CheckCircle2 } from "lucide-react";
import { Breakdown, travellers } from "../components/Summary";
import { getDestination } from "../data";
import { day1 } from "../engine";
import { date, money } from "../format";
import { startOver, useTrip } from "../state/trip";

export function Booked() {
  const booking = useTrip((s) => s.booking);
  if (!booking) {
    return (
      <div className="wrap checkout empty" data-stage-place="booked">
        <h1>No booking yet</h1>
        <Link to="/plan" className="btn btn-primary">
          Plan a trip
        </Link>
      </div>
    );
  }
  const d = getDestination(booking.trip.brief.destination);
  return (
    <div className="wrap booked" data-stage-place="booked">
      <div className="card booked-card">
        <CheckCircle2 size={40} className="ok" />
        <p className="eyebrow">Booking confirmed</p>
        <h1 data-stage-thing="reference" data-stage-label="Booking reference">
          {booking.reference}
        </h1>
        <p>
          {d?.name}, arriving {date(day1(booking.trip))}, for {travellers(booking.trip)}. {money(booking.total)} paid (demo). Vouchers go to {booking.email}.
        </p>
        <Breakdown trip={booking.trip} />
        <Link to="/" className="btn btn-ghost" onClick={startOver}>
          Plan another holiday
        </Link>
      </div>
    </div>
  );
}
