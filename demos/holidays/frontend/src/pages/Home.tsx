import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, CalendarDays, Clock3, MapPin, Plane, Sparkles, Users } from "lucide-react";
import { DestinationArt } from "../components/Art";
import { DESTINATIONS, ORIGINS } from "../data";
import { defaultStartForMonth, fromPrice } from "../engine";
import { MONTH_NAMES, money } from "../format";
import { PERSONA } from "../persona";
import { setBrief, setStep, useTrip } from "../state/trip";

function nextMonths(n: number): { month: number; year: number }[] {
  const now = new Date();
  return Array.from({ length: n }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth() + 1 + i, 1);
    return { month: d.getMonth() + 1, year: d.getFullYear() };
  });
}

export function Home() {
  const navigate = useNavigate();
  const brief = useTrip((s) => s.trip.brief);
  const origin = brief.from_city ?? "DEL";
  const prices = useMemo(() => Object.fromEntries(DESTINATIONS.map((d) => [d.id, fromPrice(d, origin)])), [origin]);
  const months = useMemo(() => nextMonths(10), []);
  const [from, setFrom] = useState(brief.from_city ?? "DEL");
  const [dest, setDest] = useState(brief.destination ?? "bali");
  const [month, setMonth] = useState<number>(brief.start_date ? Number(brief.start_date.slice(5, 7)) : months[1].month);
  const [adults, setAdults] = useState(brief.adults || 2);

  const start = () => {
    setBrief({ from_city: from, destination: dest, start_date: defaultStartForMonth(month), adults });
    setStep("brief");
    navigate("/plan");
  };
  const open = (id: string) => {
    setBrief({ destination: id });
    setStep("brief");
    navigate("/plan");
  };

  return (
    <div className="home" data-stage-place="home">
      <section className="hero">
        <div className="wrap hero-grid">
          <div className="hero-copy">
            <p className="eyebrow">
              <Sparkles size={14} /> Holiday packages, built live
            </p>
            <h1>
              Your whole holiday,
              <br />
              <em>woven</em> on one page.
            </h1>
            <p className="lede">
              Flights from eight Indian cities, hand-picked stays, transfers and days out across nine destinations. Pick each piece yourself, or tell{" "}
              {PERSONA.name} what you want and watch her build it, priced to the rupee.
            </p>
            <div className="quick" role="search" aria-label="Start a trip">
              <label>
                <span>
                  <Plane size={13} /> From
                </span>
                <select value={from} onChange={(e) => setFrom(e.target.value)}>
                  {ORIGINS.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.city}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>
                  <MapPin size={13} /> To
                </span>
                <select value={dest} onChange={(e) => setDest(e.target.value)}>
                  {DESTINATIONS.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>
                  <CalendarDays size={13} /> When
                </span>
                <select value={month} onChange={(e) => setMonth(Number(e.target.value))}>
                  {months.map((m) => (
                    <option key={`${m.year}-${m.month}`} value={m.month}>
                      {MONTH_NAMES[m.month - 1]} {m.year}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>
                  <Users size={13} /> Adults
                </span>
                <select value={adults} onChange={(e) => setAdults(Number(e.target.value))}>
                  {[1, 2, 3, 4, 5, 6].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
              <button type="button" className="btn btn-primary" onClick={start}>
                Plan my trip <ArrowRight size={16} />
              </button>
            </div>
          </div>
          <div className="hero-art" aria-hidden="true">
            <div className="hero-card hc-1">
              <DestinationArt id="bali" hue="#3a8f7a" />
            </div>
            <div className="hero-card hc-2">
              <DestinationArt id="switzerland" hue="#b8433b" />
            </div>
            <div className="hero-card hc-3">
              <DestinationArt id="kerala" hue="#2f7d5b" />
            </div>
            <div className="hero-talk">
              <span className="talk-dot" />
              <p>
                “Six nights in Bali from Delhi in February, two of us, honeymoon.”
                <small>
                  Say it to {PERSONA.name}. She fills the brief, picks flights and stays, and lays out every day.
                </small>
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="wrap section" aria-labelledby="dest-h">
        <div className="section-head">
          <h2 id="dest-h">Where to next</h2>
          <p>
            Prices are per person for two adults, {ORIGINS.find((o) => o.id === origin)?.city} departures, cheapest flight and stay, transfers and GST in.
          </p>
        </div>
        <div className="dest-grid">
          {DESTINATIONS.map((d) => (
            <button
              key={d.id}
              type="button"
              className="dest-card"
              data-stage-thing={d.id}
              data-stage-label={d.name}
              onClick={() => open(d.id)}
            >
              <DestinationArt id={d.id} hue={d.hue} className="dest-art" />
              <span className={`dest-tag ${d.domestic ? "is-dom" : ""}`}>{d.domestic ? "India" : d.country}</span>
              <span className="dest-body">
                <span className="dest-name">{d.name}</span>
                <span className="dest-line">{d.tagline}</span>
                <span className="dest-meta">
                  <span>
                    <Clock3 size={12} /> {d.nights[0]}–{d.nights[1]} nights · {d.cities.map((c) => c.name).join(", ")}
                  </span>
                </span>
                <span className="dest-price">
                  <small>from</small> {money(prices[d.id])} <small>per person</small>
                </span>
              </span>
            </button>
          ))}
        </div>
      </section>

      <section className="how">
        <div className="wrap">
          <h2>How a Wanderloom package comes together</h2>
          <ol className="how-steps">
            <li>
              <strong>Tell us the trip</strong>
              <span>From where, where to, when, who's going, and the feel: relaxed, adventure, honeymoon or family.</span>
            </li>
            <li>
              <strong>Pick your flight</strong>
              <span>Round trips on our partner airlines, with times, stops and baggage side by side.</span>
            </li>
            <li>
              <strong>Choose stays per city</strong>
              <span>Move nights between cities, then pick the hotel and room for each.</span>
            </li>
            <li>
              <strong>Fill your days</strong>
              <span>Add experiences day by day. We check slots, ages and closing days for you.</span>
            </li>
          </ol>
        </div>
      </section>
    </div>
  );
}
