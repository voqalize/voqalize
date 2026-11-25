/**
 * Hotel information: an accordion of the house facts, one section open at a
 * time (`infoOpen` in the store, so the concierge can open one too).
 */
import {
  Accessibility,
  ChevronDown,
  Clock,
  Dog,
  Dumbbell,
  type LucideIcon,
  Moon,
  Phone,
  ScrollText,
  SquareParking,
  CigaretteOff,
  UtensilsCrossed,
  Waves,
  Wifi,
} from "lucide-react";
import { PageHeader } from "../components/Shell";
import { HOTEL, INFO } from "../data";
import { openInfo, useStay } from "../state/store";
import "../styles/stay.css";

const ICONS: Record<string, LucideIcon> = {
  checkin: Clock,
  house_rules: ScrollText,
  quiet: Moon,
  pets: Dog,
  smoking: CigaretteOff,
  pools: Waves,
  wifi: Wifi,
  parking: SquareParking,
  dining_hours: UtensilsCrossed,
  fitness: Dumbbell,
  accessibility: Accessibility,
  contact: Phone,
};

export function Info() {
  const open = useStay((s) => s.infoOpen);
  return (
    <div className="page st-page" data-stage-place="info">
      <PageHeader title="Hotel information" sub={HOTEL.address} back="/" />
      <div className="st-body">
        <div className="st-card is-flush">
          {INFO.map((sec) => {
            const Icon = ICONS[sec.id] ?? ScrollText;
            const isOpen = open === sec.id;
            return (
              <div key={sec.id} className={`st-acc${isOpen ? " is-open" : ""}`}>
                <button
                  type="button"
                  className="st-acc-head"
                  aria-expanded={isOpen}
                  onClick={() => openInfo(isOpen ? null : sec.id)}
                  data-stage-thing={`info-${sec.id}`}
                  data-stage-label={sec.title}
                >
                  <Icon size={19} />
                  <span>{sec.title}</span>
                  <ChevronDown size={18} />
                </button>
                {isOpen ? (
                  <ul className="st-facts">
                    {sec.facts.map((f) => (
                      <li key={f}>{f}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            );
          })}
        </div>
        <p className="st-note">
          Front desk {HOTEL.phone}, 24 hours. Check-in from {HOTEL.check_in_time}, check-out by {HOTEL.check_out_time}.
        </p>
      </div>
    </div>
  );
}
