/**
 * Home: the greeting, the weather, the one card that matters right now
 * (check in, the digital key, check out), the quick tiles, tonight at the
 * resort and what the guest has booked, ordered and asked for.
 */
import {
  ArrowRight,
  CalendarCheck,
  ConciergeBell,
  Info as InfoIcon,
  LogOut,
  Martini,
  Presentation,
  Sparkles,
  Sun,
  Sunset,
  Users,
  UtensilsCrossed,
  Waves,
  Wifi,
} from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { PageHeader, hotelLine } from "../components/Shell";
import { ACTIVITIES, CHECKIN, GUEST, HOTEL } from "../data";
import { day, minutes, money } from "../lib/format";
import { balance, guestName, stayClock, useStay } from "../state/store";
import "../styles/stay.css";

export function greeting(now: string) {
  const m = minutes(now);
  return m < 12 * 60 ? "Good morning" : m < 17 * 60 ? "Good afternoon" : "Good evening";
}

/** "1412" → 14; "0516" → 5. */
export const floorOf = (room: string) => Number(room.slice(0, -2));

/** An NFC-style mark: three arcs from a point. */
function Nfc() {
  return (
    <svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden>
      <path d="M14 12a12 12 0 0 1 0 16" stroke="#e9d3a8" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M20 8a18 18 0 0 1 0 24" stroke="#e9d3a8" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M26 4a24 24 0 0 1 0 32" stroke="#e9d3a8" strokeWidth="2.4" strokeLinecap="round" />
      <circle cx="9" cy="20" r="2.6" fill="#e9d3a8" />
    </svg>
  );
}

/** The digital key: room, floor, hold near the door. */
export function KeyCard() {
  const room = useStay((s) => s.room);
  const scenario = useStay((s) => s.scenario);
  const checkedOut = useStay((s) => s.checkedOut);
  if (!room) return null;
  const c = stayClock();
  void scenario;
  return (
    <div className="st-key" data-stage-thing="key" data-stage-label={`Room ${room} key`}>
      <div className="st-key-top">
        <span>Belmonte key</span>
        <span>{checkedOut ? "Expired" : "Active"}</span>
      </div>
      <div className="st-key-room">
        <small>Room</small>
        <b>{room}</b>
        <span>
          Floor {floorOf(room)} · {GUEST.room_type}
        </span>
      </div>
      <div className="st-key-nfc">
        <Nfc />
      </div>
      <div className="st-key-foot">
        <span>{checkedOut ? "Thank you for staying with us" : "Hold near the door"}</span>
        <span>
          Out <b>{day(c.depart)}</b>
        </span>
      </div>
    </div>
  );
}

export function WifiCard() {
  return (
    <div className="st-card st-wifi">
      <span className="st-wifi-icon">
        <Wifi size={20} />
      </span>
      <div>
        <span className="st-label">Wi-Fi</span>
        <b>{CHECKIN.wifi.network}</b>
        <span>Password: {CHECKIN.wifi.password}</span>
      </div>
    </div>
  );
}

/** Line art for the check-in hero: an arch, the sun on the bay, two cypresses. */
function ArchArt() {
  return (
    <svg className="st-hero-art" viewBox="0 0 360 200" preserveAspectRatio="xMaxYMid slice" aria-hidden>
      <defs>
        <radialGradient id="st-sun" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#f6d9a6" stopOpacity="0.95" />
          <stop offset="1" stopColor="#f6d9a6" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx="276" cy="78" r="70" fill="url(#st-sun)" opacity="0.5" />
      <circle cx="276" cy="80" r="22" fill="#f1c98f" opacity="0.9" />
      <path d="M226 200V92a50 50 0 0 1 100 0v108" stroke="#e9d3a8" strokeOpacity="0.55" strokeWidth="1.5" fill="none" />
      <path d="M210 112c12 0 12-5 24-5s12 5 24 5 12-5 24-5 12 5 24 5 12-5 24-5 12 5 24 5" stroke="#cfe3df" strokeOpacity="0.5" strokeWidth="1.5" fill="none" />
      <path d="M210 126c12 0 12-5 24-5s12 5 24 5 12-5 24-5 12 5 24 5 12-5 24-5 12 5 24 5" stroke="#cfe3df" strokeOpacity="0.3" strokeWidth="1.5" fill="none" />
      <path d="M342 200c-6-30-4-70 4-96 8 26 10 66 4 96z" fill="#0d1a22" opacity="0.55" />
      <path d="M200 200c-5-26-3-58 3-80 6 22 8 54 3 80z" fill="#0d1a22" opacity="0.45" />
    </svg>
  );
}

function NightArt({ variant }: { variant: number }) {
  return (
    <svg className="st-event-art" viewBox="0 0 236 84" preserveAspectRatio="xMidYMid slice" aria-hidden>
      <defs>
        <linearGradient id={`st-night-${variant}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={variant ? "#3a2a3e" : "#1c3a42"} />
          <stop offset="1" stopColor={variant ? "#c0603a" : "#2c5a5e"} />
        </linearGradient>
      </defs>
      <rect width="236" height="84" fill={`url(#st-night-${variant})`} />
      {[18, 52, 96, 150, 190, 214].map((x, i) => (
        <circle key={x} cx={x} cy={10 + ((i * 13) % 30)} r={i % 2 ? 1 : 1.5} fill="#fff" opacity="0.7" />
      ))}
      {variant ? (
        <g>
          <path d="M108 84c-2-14 6-20 10-30 3 10 12 16 10 30z" fill="#f1c98f" />
          <path d="M113 84c0-8 4-11 5-17 2 6 5 9 5 17z" fill="#fff3d6" />
          <path d="M92 84l40-10M144 84l-40-10" stroke="#5a3a2a" strokeWidth="3" strokeLinecap="round" />
        </g>
      ) : (
        <g stroke="#e9d3a8" strokeWidth="1.6" fill="none" strokeLinecap="round">
          <path d="M150 62V30l22-6v32" />
          <circle cx="146" cy="62" r="5" fill="#e9d3a8" />
          <circle cx="168" cy="56" r="5" fill="#e9d3a8" />
          <path d="M0 74c20 0 20-6 40-6s20 6 40 6 20-6 40-6" stroke="#cfe3df" strokeOpacity="0.5" />
        </g>
      )}
      <circle cx="200" cy="22" r="9" fill="#f6e7c8" opacity="0.85" />
    </svg>
  );
}

function Tile({ thing, label, to, icon, badge }: { thing: string; label: string; to: string; icon: ReactNode; badge?: number }) {
  return (
    <Link to={to} className="st-tile" data-stage-thing={thing} data-stage-label={label}>
      <span className="st-tile-icon">{icon}</span>
      <span>{label}</span>
      {badge ? <span className="st-tile-badge">{badge}</span> : null}
    </Link>
  );
}

export function Home() {
  const s = useStay();
  const c = stayClock();
  const pending = s.visitors.filter((v) => v.status === "pending").length;
  const tonight = ACTIVITIES.filter((a) => a.tonight);
  const departing = s.scenario === "departure" || c.today === c.depart;
  const plans = [
    ...s.bookings.map((b) => ({ id: b.id, icon: <CalendarCheck size={18} />, title: b.label, sub: b.when, side: b.total ? money(b.total) : "Free" })),
    ...s.orders.map((o) => ({
      id: o.id,
      icon: o.outlet === "dining" ? <UtensilsCrossed size={18} /> : <Martini size={18} />,
      title: o.outlet === "dining" ? "In-room dining" : "Drinks",
      sub: `To ${o.deliver}, in ${o.eta}`,
      side: money(o.total),
    })),
    ...s.requests.map((r) => ({ id: r.id, icon: <ConciergeBell size={18} />, title: r.label, sub: `Status: ${r.eta}`, side: "" })),
  ];

  return (
    <div className="page st-page" data-stage-place="home">
      <PageHeader title={`${greeting(c.now)}, ${guestName()}`} sub={hotelLine} />
      <div className="st-body">
        <div className="st-weather">
          <span>
            <Sun size={15} /> {HOTEL.weather.temp_f}°F, sunny
          </span>
          <i className="st-dot" />
          <span>{HOTEL.weather.summary}</span>
          <i className="st-dot" />
          <span>
            <Sunset size={15} /> Sunset {HOTEL.weather.sunset}
          </span>
        </div>

        {s.checkedOut ? (
          <div className="st-thanks">
            <span className="st-label" style={{ color: "#fff3d6" }}>
              Checked out
            </span>
            <h2>Safe travels, {guestName()}</h2>
            <p>Your receipt is on its way to {GUEST.email}. We hope to see you back in Halcyon Bay.</p>
          </div>
        ) : !s.checkedIn ? (
          <Link to="/stay/check-in" className="st-hero" data-stage-thing="checkin-card" data-stage-label="Check in">
            <ArchArt />
            <span className="st-label">Arriving {day(c.arrive)}</span>
            <h2>Your room is almost ready</h2>
            <p>Check in now and skip the front desk. Your digital key arrives in the app.</p>
            <div className="st-hero-foot">
              <span className="st-btn is-light is-small">
                Check in <ArrowRight size={16} />
              </span>
              <span style={{ fontSize: 12.5, opacity: 0.75 }}>Reservation {GUEST.reservation}</span>
            </div>
          </Link>
        ) : (
          <KeyCard />
        )}

        {departing && s.checkedIn && !s.checkedOut ? (
          <Link to="/stay/check-out" className="st-hero is-sand" data-stage-thing="checkout-card" data-stage-label="Check out">
            <span className="st-label">Departing today</span>
            <h2 style={{ fontSize: 22 }}>Check out by {HOTEL.check_out_time}</h2>
            <p>
              Review your bill, ask for a late check-out, or check out from here. Balance {money(balance(s))}.
            </p>
            <div className="st-hero-foot">
              <span className="st-btn is-small">
                <LogOut size={16} /> Check out
              </span>
            </div>
          </Link>
        ) : null}

        <section className="st-section" aria-label="Quick links">
          <div className="st-tiles">
            <Tile thing="tile-dining" label="Dining" to="/dining" icon={<UtensilsCrossed size={19} />} />
            <Tile thing="tile-drinks" label="Drinks" to="/bar" icon={<Martini size={19} />} />
            <Tile thing="tile-spa" label="Spa" to="/spa" icon={<Sparkles size={19} />} />
            <Tile thing="tile-activities" label="Activities" to="/activities" icon={<Waves size={19} />} />
            <Tile thing="tile-requests" label="Requests" to="/requests" icon={<ConciergeBell size={19} />} />
            <Tile thing="tile-visitors" label="Visitors" to="/visitors" icon={<Users size={19} />} badge={pending} />
            <Tile thing="tile-meetings" label="Meetings" to="/meetings" icon={<Presentation size={19} />} />
            <Tile thing="tile-info" label="Hotel info" to="/info" icon={<InfoIcon size={19} />} />
          </div>
        </section>

        {tonight.length ? (
          <section className="st-section">
            <div className="st-section-head">
              <h2>Tonight at Belmonte</h2>
              <Link to="/activities">All activities</Link>
            </div>
            <div className="st-tonight">
              {tonight.map((a, i) => (
                <Link key={a.id} to="/activities" className="st-event" data-stage-thing={`tonight-${a.id}`} data-stage-label={a.name}>
                  <NightArt variant={i % 2} />
                  <span className="st-event-body">
                    <b>{a.name}</b>
                    <span>{a.hours}</span>
                    <span>{a.price ? money(a.price) : "Free for guests"}</span>
                  </span>
                </Link>
              ))}
            </div>
          </section>
        ) : null}

        {plans.length ? (
          <section className="st-section">
            <div className="st-section-head">
              <h2>Your plans</h2>
            </div>
            <div className="st-card is-flush">
              {plans.map((p) => (
                <div key={p.id} className="st-plan">
                  <span className="st-plan-icon">{p.icon}</span>
                  <span className="st-plan-text">
                    <b>{p.title}</b>
                    <span>{p.sub}</span>
                  </span>
                  {p.side ? <span className="st-plan-side">{p.side}</span> : null}
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {s.checkedIn && !s.checkedOut ? <WifiCard /> : null}
      </div>
    </div>
  );
}
