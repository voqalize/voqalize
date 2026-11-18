/**
 * The trip builder: brief → flights → hotels → days → package, beside a sticky
 * summary. Every control calls the controller in state/trip.ts, the same
 * functions the planner's Stage moves call, so the page is a complete
 * package builder by hand.
 */
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  BedDouble,
  Check,
  Clock3,
  Luggage,
  Minus,
  Moon,
  Plane,
  Plus,
  Sparkles,
  Star,
  Sun,
  Sunrise,
  Sunset,
  Trash2,
  Utensils,
  Wand2,
  X,
} from "lucide-react";
import { DestinationArt } from "../components/Art";
import { Breakdown, TripSummary, travellers } from "../components/Summary";
import { DESTINATIONS, type Flight, ORIGINS, RULES, STYLES, airportCity, flightsFor, getActivity, getDestination, getFlight } from "../data";
import {
  activityPrice,
  addDays,
  cannotPlace,
  day1,
  days,
  defaultStartForMonth,
  flightPrice,
  missing,
  recommend,
  recommendedFlight,
  rooms,
  splitOf,
  stays,
  styleOf,
  todayIso,
  transfers,
  validSplit,
} from "../engine";
import { MONTH_NAMES, date, hm, money, plural, shortDate } from "../format";
import { hotelMatches } from "../stage/performers";
import {
  STEPS,
  type Step,
  addActivity,
  buildPackage,
  pickFlight,
  pickHotel,
  removeActivity,
  setBrief,
  setFlightSort,
  setHotelCity,
  setHotelWant,
  setSplit,
  setStep,
  useTrip,
} from "../state/trip";

export function Plan() {
  const step = useTrip((s) => s.step);
  const brief = useTrip((s) => s.trip.brief);
  const ready = missing(brief).length === 0;
  const d = getDestination(brief.destination);
  return (
    <div className="plan" data-stage-place="plan">
      <div className="plan-band" style={d ? ({ "--hue": d.hue } as React.CSSProperties) : undefined}>
        <div className="wrap plan-band-row">
          <div>
            <p className="eyebrow">Build your package</p>
            <h1>{d ? `${d.name}, your way` : "Plan a holiday"}</h1>
          </div>
          <nav className="steps" aria-label="Steps">
            {STEPS.map((s, i) => {
              const locked = s.id !== "brief" && !ready;
              return (
                <button
                  key={s.id}
                  type="button"
                  className={`step-tab${step === s.id ? " is-on" : ""}`}
                  disabled={locked}
                  onClick={() => setStep(s.id)}
                  data-stage-thing={`step-${s.id}`}
                  data-stage-label={s.label}
                  aria-current={step === s.id ? "step" : undefined}
                >
                  <span className="step-n">{i + 1}</span>
                  {s.label}
                </button>
              );
            })}
          </nav>
        </div>
      </div>
      <div className="wrap plan-grid">
        <section className="panel" data-step-panel={step} aria-live="polite">
          {step === "brief" && <BriefStep />}
          {step === "flights" && ready && <FlightsStep />}
          {step === "hotels" && ready && <HotelsStep />}
          {step === "days" && ready && <DaysStep />}
          {step === "package" && ready && <PackageStep />}
          {step !== "brief" && !ready && <BriefStep />}
        </section>
        <TripSummary />
      </div>
    </div>
  );
}

function Next({ to, label }: { to: Step; label: string }) {
  return (
    <div className="panel-foot">
      <button type="button" className="btn btn-primary" onClick={() => setStep(to)}>
        {label} <ArrowRight size={16} />
      </button>
    </div>
  );
}

// ─── Brief ──────────────────────────────────────────────────────────────────

function Field({ name, label, children }: { name: string; label: string; children: React.ReactNode }) {
  return (
    <div className="field" data-stage-part={`brief:${name}`}>
      <span className="field-label">{label}</span>
      {children}
    </div>
  );
}

function Stepper({ value, min, max, onChange, label }: { value: number; min: number; max: number; onChange: (n: number) => void; label: string }) {
  return (
    <div className="stepper" role="group" aria-label={label}>
      <button type="button" aria-label={`Fewer ${label}`} disabled={value <= min} onClick={() => onChange(value - 1)}>
        <Minus size={14} />
      </button>
      <output>{value}</output>
      <button type="button" aria-label={`More ${label}`} disabled={value >= max} onClick={() => onChange(value + 1)}>
        <Plus size={14} />
      </button>
    </div>
  );
}

const BUDGETS = [0, 100000, 200000, 300000, 500000];

function BriefStep() {
  const trip = useTrip((s) => s.trip);
  const b = trip.brief;
  const d = getDestination(b.destination);
  const gaps = missing(b);
  const months = useMemo(() => {
    const now = new Date();
    return Array.from({ length: 8 }, (_, i) => new Date(now.getFullYear(), now.getMonth() + 1 + i, 1).getMonth() + 1);
  }, []);
  const minDate = addDays(todayIso(), RULES.min_days_ahead);
  const [kidAge, setKidAge] = useState(6);
  return (
    <div>
      <header className="panel-head">
        <h2>Tell us the trip</h2>
        <p>Where from and to, when, who's going and the feel of it. Everything after this is priced from these.</p>
      </header>
      <div className="brief-grid">
        <Field name="from_city" label="Flying from">
          <select value={b.from_city ?? ""} onChange={(e) => setBrief({ from_city: e.target.value || null })}>
            <option value="">Choose a city</option>
            {ORIGINS.map((o) => (
              <option key={o.id} value={o.id}>
                {o.city} ({o.id})
              </option>
            ))}
          </select>
        </Field>
        <Field name="nights" label={d ? `Nights (${d.nights[0]}–${d.nights[1]})` : "Nights"}>
          <Stepper
            label="nights"
            value={b.nights ?? d?.default_nights ?? 5}
            min={d?.nights[0] ?? 3}
            max={d?.nights[1] ?? 9}
            onChange={(n) => setBrief({ nights: n })}
          />
        </Field>
        <div className="field wide" data-stage-part="brief:destination">
          <span className="field-label">Destination</span>
          <div className="dest-chips">
            {DESTINATIONS.map((x) => (
              <button
                key={x.id}
                type="button"
                className={`dest-chip${b.destination === x.id ? " is-on" : ""}`}
                onClick={() => setBrief({ destination: x.id })}
                aria-pressed={b.destination === x.id}
              >
                <DestinationArt id={x.id} hue={x.hue} className="chip-art" />
                <span>{x.name}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="field wide" data-stage-part="brief:start_date">
          <span className="field-label">Leaving home on</span>
          <div className="date-row">
            <input type="date" min={minDate} value={b.start_date ?? ""} onChange={(e) => setBrief({ start_date: e.target.value || null })} />
            <div className="month-chips" aria-label="Or pick a month">
              {months.map((m) => {
                const iso = defaultStartForMonth(m);
                return (
                  <button key={m} type="button" className={`chip${b.start_date === iso ? " is-on" : ""}`} onClick={() => setBrief({ start_date: iso })}>
                    {MONTH_NAMES[m - 1].slice(0, 3)}
                    {d?.best_months.includes(m) ? <Sun size={11} aria-label="good season" /> : null}
                  </button>
                );
              })}
            </div>
          </div>
          {b.start_date && <small className="hint">{shortDate(b.start_date)}, {date(b.start_date)}</small>}
        </div>
        <Field name="adults" label="Adults (12+)">
          <Stepper label="adults" value={b.adults} min={1} max={RULES.max_travellers - b.kids.length} onChange={(n) => setBrief({ adults: n })} />
        </Field>
        <Field name="kids" label="Children (0–11)">
          <div className="kids">
            {b.kids.map((age, i) => (
              <span className="kid" key={i}>
                {age === 0 ? "under 1" : `${age} yr`}
                <button type="button" aria-label="Remove child" onClick={() => setBrief({ kids: b.kids.filter((_, j) => j !== i) })}>
                  <X size={12} />
                </button>
              </span>
            ))}
            {b.adults + b.kids.length < RULES.max_travellers && (
              <span className="kid-add">
                <select aria-label="Child's age" value={kidAge} onChange={(e) => setKidAge(Number(e.target.value))}>
                  {Array.from({ length: 12 }, (_, a) => (
                    <option key={a} value={a}>
                      {a === 0 ? "under 1" : `${a} yr`}
                    </option>
                  ))}
                </select>
                <button type="button" className="chip" onClick={() => setBrief({ kids: [...b.kids, kidAge] })}>
                  <Plus size={12} /> Add child
                </button>
              </span>
            )}
          </div>
        </Field>
        <div className="field wide" data-stage-part="brief:style">
          <span className="field-label">The feel of it</span>
          <div className="style-cards">
            {STYLES.map((s) => (
              <button key={s.id} type="button" className={`style-card${b.style === s.id ? " is-on" : ""}`} onClick={() => setBrief({ style: b.style === s.id ? null : s.id })} aria-pressed={b.style === s.id}>
                <b>{s.label}</b>
                <small>{STYLE_LINE[s.id]}</small>
              </button>
            ))}
          </div>
        </div>
        <div className="field wide" data-stage-part="brief:budget">
          <span className="field-label">Budget for everyone</span>
          <div className="month-chips">
            {BUDGETS.map((n) => (
              <button key={n} type="button" className={`chip${b.budget === n ? " is-on" : ""}`} onClick={() => setBrief({ budget: n })}>
                {n ? `up to ${money(n)}` : "No limit"}
              </button>
            ))}
            <input
              className="budget-input"
              type="number"
              inputMode="numeric"
              min={0}
              step={5000}
              aria-label="Budget in rupees"
              value={b.budget || ""}
              placeholder="Or type ₹"
              onChange={(e) => setBrief({ budget: Math.max(0, Number(e.target.value) || 0) })}
            />
          </div>
        </div>
      </div>
      <div className="panel-foot">
        {gaps.length ? (
          <p className="muted">Still needed: {gaps.map((g) => GAP[g]).join(", ")}.</p>
        ) : (
          <>
            <button type="button" className="btn btn-ghost" onClick={() => (buildPackage(), setStep("package"))}>
              <Wand2 size={16} /> Build it for me
            </button>
            <button type="button" className="btn btn-primary" onClick={() => setStep("flights")}>
              See flights <ArrowRight size={16} />
            </button>
          </>
        )}
      </div>
    </div>
  );
}
const GAP: Record<string, string> = { from_city: "where you fly from", destination: "a destination", start_date: "a date", nights: "nights" };
const STYLE_LINE: Record<string, string> = {
  relaxed: "Slow mornings, views, spas",
  adventure: "Treks, water, early starts",
  honeymoon: "Villas, sunsets, dinners for two",
  family: "Kid-friendly stays and days",
};

// ─── Flights ────────────────────────────────────────────────────────────────

const SORTS = [
  ["recommended", "Suggested"],
  ["price", "Cheapest"],
  ["duration", "Fastest"],
  ["departure", "Earliest"],
] as const;

export function sortedFlights(list: Flight[], sort: string, recommended?: string): Flight[] {
  const out = [...list];
  if (sort === "price") out.sort((a, b) => a.fare_adult - b.fare_adult);
  else if (sort === "duration") out.sort((a, b) => a.out.minutes - b.out.minutes);
  else if (sort === "departure") out.sort((a, b) => a.out.legs[0].depart.localeCompare(b.out.legs[0].depart));
  else out.sort((a, b) => Number(b.id === recommended) - Number(a.id === recommended) || a.fare_adult - b.fare_adult);
  return out;
}

function Journey({ j, label, on }: { j: Flight["out"]; label: string; on: string | null }) {
  const first = j.legs[0];
  const last = j.legs[j.legs.length - 1];
  return (
    <div className="journey">
      <span className="j-label">
        {label}
        {on ? <small>{shortDate(on)}</small> : null}
      </span>
      <span className="j-time">
        <b>{first.depart}</b>
        <small>{first.from}</small>
      </span>
      <span className="j-line">
        <small>{hm(j.minutes)}</small>
        <i>{j.legs.slice(0, -1).map((l) => <em key={l.to} title={`Change in ${airportCity(l.to)}`} />)}</i>
        <small>{j.stops ? `${plural(j.stops, "stop")} · ${j.legs.slice(0, -1).map((l) => l.to).join(", ")}` : "Nonstop"}</small>
      </span>
      <span className="j-time">
        <b>
          {last.arrive}
          {last.arrive_day ? <sup>+{last.arrive_day}</sup> : null}
        </b>
        <small>{last.to}</small>
      </span>
    </div>
  );
}

function FlightsStep() {
  const trip = useTrip((s) => s.trip);
  const sort = useTrip((s) => s.flightSort);
  const b = trip.brief;
  const rec = recommendedFlight(b);
  const list = sortedFlights(flightsFor(b.from_city, b.destination), sort, rec?.id);
  const d = getDestination(b.destination)!;
  const backOn = b.start_date && b.nights ? addDays(day1(trip) ?? b.start_date, b.nights) : null;
  return (
    <div>
      <header className="panel-head">
        <h2>
          Flights · {airportCity(b.from_city ?? "")} to {d.name}
        </h2>
        <p>
          Round trips for {travellers(trip)}. Fares are per adult, return, including airport taxes
          {b.start_date && Number(RULES.season[String(Number(b.start_date.slice(5, 7)))] ?? 100) > 100 ? "; peak-season fares apply in this month" : ""}.
        </p>
      </header>
      <div className="sort-row" role="group" aria-label="Sort flights">
        {SORTS.map(([id, label]) => (
          <button key={id} type="button" className={`chip${sort === id ? " is-on" : ""}`} data-stage-part={`sort:${id}`} onClick={() => setFlightSort(id)}>
            {label}
          </button>
        ))}
      </div>
      <div className="flight-list" data-stage-thing="flight-list" data-stage-label="Flight options">
        {list.map((f, i) => {
          const p = flightPrice(f, b);
          const on = trip.flight_id === f.id;
          return (
            <article
              key={f.id}
              className={`flight${on ? " is-on" : ""}`}
              data-flight={f.id}
              data-stage-thing={`flight-${i + 1}`}
              data-stage-label={`Flight ${i + 1}`}
            >
              <div className="flight-air">
                <span className={`air-badge air-${f.airline}`}>{f.airline_name.slice(0, 2)}</span>
                <div>
                  <b>{f.airline_name}</b>
                  <small>
                    {f.out.legs.map((l) => l.number).join(" · ")} · {f.kind}
                  </small>
                </div>
                <span className="flight-n">Option {i + 1}</span>
                {f.id === rec?.id && (
                  <span className="badge">
                    <Sparkles size={11} /> Suggested
                  </span>
                )}
              </div>
              <div className="flight-journeys">
                <Journey j={f.out} label="Out" on={b.start_date} />
                <Journey j={f.back} label="Back" on={backOn} />
              </div>
              <div className="flight-perks">
                <span>
                  <Luggage size={13} /> {f.baggage}
                </span>
                <span>
                  <Utensils size={13} /> {f.meal}
                </span>
              </div>
              <div className="flight-buy">
                <span className="price">
                  {money(p.adult)}
                  <small>per adult</small>
                </span>
                <small className="muted">{money(p.total)} for all</small>
                <button type="button" className={`btn ${on ? "btn-on" : "btn-primary"} btn-small`} onClick={() => pickFlight(f.id)} aria-pressed={on}>
                  {on ? (
                    <>
                      <Check size={14} /> Selected
                    </>
                  ) : (
                    "Select"
                  )}
                </button>
              </div>
            </article>
          );
        })}
      </div>
      {trip.flight_id && <Next to="hotels" label="Choose hotels" />}
    </div>
  );
}

// ─── Hotels ─────────────────────────────────────────────────────────────────

const WANT_CHIPS = ["beach", "pool", "luxury", "budget", "family", "honeymoon", "adventure", "culture"];

function NightsEditor() {
  const trip = useTrip((s) => s.trip);
  const d = getDestination(trip.brief.destination)!;
  const split = splitOf(trip) ?? [];
  if (d.cities.length < 2) return null;
  const move = (i: number, delta: number): number[] | null => {
    // Take the night from (or give it to) the nearest other city that can.
    const order = d.cities.map((_, j) => j).filter((j) => j !== i).sort((a, b) => Math.abs(a - i) - Math.abs(b - i));
    for (const j of order) {
      const s = [...split];
      s[i] += delta;
      s[j] -= delta;
      if (validSplit(trip, s)) return s;
    }
    return null;
  };
  return (
    <div className="nights" data-stage-thing="nights" data-stage-label="Nights in each city">
      <span className="field-label">
        <Moon size={13} /> Nights in each city
      </span>
      <div className="nights-row">
        {d.cities.map((c, i) => {
          const less = move(i, -1);
          const more = move(i, 1);
          return (
            <div key={c.id} className={`night-city${split[i] ? "" : " is-zero"}`}>
              <b>{c.name}</b>
              <div className="stepper" role="group" aria-label={`Nights in ${c.name}`}>
                <button type="button" disabled={!less} onClick={() => less && setSplit(less)} aria-label={`One night fewer in ${c.name}`}>
                  <Minus size={13} />
                </button>
                <output>{split[i]}</output>
                <button type="button" disabled={!more} onClick={() => more && setSplit(more)} aria-label={`One night more in ${c.name}`}>
                  <Plus size={13} />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function HotelsStep() {
  const trip = useTrip((s) => s.trip);
  const cityPick = useTrip((s) => s.hotelCity);
  const want = useTrip((s) => s.hotelWant);
  const st = stays(trip);
  const stay = st.find((s) => s.city.id === cityPick) ?? st[0];
  const d = getDestination(trip.brief.destination)!;
  if (!stay) return null;
  const style = styleOf(trip.brief);
  const suggested = recommend(trip).hotels[stay.city.id]?.hotel_id;
  const shown = stay.city.hotels.filter((h) => hotelMatches(want, h));
  const n = rooms(trip.brief);
  return (
    <div>
      <header className="panel-head">
        <h2>Where you'll stay</h2>
        <p>
          {plural(n, "room")} for {travellers(trip)}; children share their parents' room. Prices are per room per night.
        </p>
      </header>
      <NightsEditor />
      <div className="city-tabs" role="tablist">
        {st.map((s) => {
          const pick = trip.hotels[s.city.id];
          return (
            <button
              key={s.city.id}
              role="tab"
              type="button"
              aria-selected={s.city.id === stay.city.id}
              className={`city-tab${s.city.id === stay.city.id ? " is-on" : ""}`}
              data-city-tab={s.city.id}
              onClick={() => setHotelCity(s.city.id)}
            >
              <b>{s.city.name}</b>
              <small>
                {plural(s.nights, "night")} · {pick ? <Check size={11} /> : "choose"}
              </small>
            </button>
          );
        })}
      </div>
      <p className="city-blurb">
        {stay.city.blurb}
        {stay.city.inland ? " · inland, no beach" : ""}
      </p>
      <div className="sort-row" role="group" aria-label="Filter hotels">
        <button type="button" className={`chip${!want ? " is-on" : ""}`} onClick={() => setHotelWant(null)}>
          All {stay.city.hotels.length}
        </button>
        {WANT_CHIPS.filter((w) => stay.city.hotels.some((h) => hotelMatches(w, h))).map((w) => (
          <button key={w} type="button" className={`chip${want === w ? " is-on" : ""}`} data-stage-part={`want:${w}`} onClick={() => setHotelWant(want === w ? null : w)}>
            {w[0].toUpperCase() + w.slice(1)}
          </button>
        ))}
      </div>
      <div className="hotel-list">
        {shown.map((h) => {
          const pick = trip.hotels[stay.city.id];
          return (
            <article key={h.id} className={`hotel${pick?.hotel_id === h.id ? " is-on" : ""}`} data-stage-thing={h.id} data-stage-label={h.name}>
              <div className="hotel-art">
                <DestinationArt id={d.id} hue={d.hue} />
                {h.id === suggested && (
                  <span className="badge">
                    <Sparkles size={11} /> Suggested for {style}
                  </span>
                )}
              </div>
              <div className="hotel-body">
                <div className="hotel-top">
                  <h3>{h.name}</h3>
                  <span className="stars" aria-label={`${h.stars} star`}>
                    {Array.from({ length: h.stars }, (_, i) => (
                      <Star key={i} size={12} fill="currentColor" />
                    ))}
                  </span>
                </div>
                <p className="muted">
                  {h.area} · {h.blurb}
                </p>
                <div className="tags">
                  {h.inclusions.map((x) => (
                    <span key={x} className="tag inc">
                      <Check size={11} /> {x}
                    </span>
                  ))}
                  {h.tags.map((x) => (
                    <span key={x} className="tag">
                      {x}
                    </span>
                  ))}
                </div>
                <div className="rooms">
                  {h.rooms.map((r) => {
                    const on = pick?.hotel_id === h.id && pick.room_id === r.id;
                    return (
                      <div key={r.id} className={`room${on ? " is-on" : ""}`}>
                        <span>
                          <BedDouble size={14} /> {r.name}
                        </span>
                        <span className="room-price">
                          {money(r.price)}
                          <small>/night</small>
                        </span>
                        <span className="muted room-total">{money(r.price * stay.nights * n)} for the stay</span>
                        <button
                          type="button"
                          className={`btn btn-small ${on ? "btn-on" : "btn-outline"}`}
                          data-room={`${h.id}:${r.id}`}
                          onClick={() => pickHotel(stay.city.id, h.id, r.id)}
                          aria-pressed={on}
                        >
                          {on ? (
                            <>
                              <Check size={13} /> Chosen
                            </>
                          ) : (
                            "Choose"
                          )}
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            </article>
          );
        })}
      </div>
      {st.every((s) => trip.hotels[s.city.id]) && <Next to="days" label="Plan the days" />}
    </div>
  );
}

// ─── Days ───────────────────────────────────────────────────────────────────

const SLOT_ICON = { morning: Sunrise, afternoon: Sun, evening: Sunset, full_day: Clock3 } as const;
const KIND: Record<string, string> = { arrival: "Arrival", transfer: "Travel day", full: "Free day", departure: "Fly home" };

function DaysStep() {
  const trip = useTrip((s) => s.trip);
  const [openDay, setOpenDay] = useState<number | null>(null);
  const all = days(trip);
  return (
    <div>
      <header className="panel-head">
        <h2>Your days</h2>
        <p>Arrival and travel days have the evening free; full days have morning, afternoon and evening. We check ages and closing days as you add.</p>
      </header>
      <div className="panel-tools">
        <button
          type="button"
          className="btn btn-ghost btn-small"
          onClick={() => {
            for (const p of useTrip.getState().trip.activities) removeActivity(p.activity_id, p.day);
            for (const p of recommend(useTrip.getState().trip).activities) addActivity(p.activity_id, p.day);
          }}
        >
          <Wand2 size={14} /> Suggest days for a {styleOf(trip.brief)} trip
        </button>
      </div>
      <ol className="day-list">
        {all.map((d) => {
          const planned = trip.activities.filter((p) => p.day === d.day);
          const options = d.city.activities;
          return (
            <li key={d.day} className={`day kind-${d.kind}`} data-stage-thing={`day-${d.day}`} data-stage-label={`Day ${d.day}`}>
              <div className="day-head">
                <span className="day-n">Day {d.day}</span>
                <span className="day-date">{d.date ? shortDate(d.date) : ""}</span>
                <span className="day-city">{d.city.name}</span>
                <span className="day-kind">{KIND[d.kind]}</span>
              </div>
              <div className="day-body">
                {planned.map((p) => {
                  const a = getActivity(p.activity_id)!;
                  const Icon = SLOT_ICON[a.slot];
                  return (
                    <div key={p.activity_id} className="planned" data-planned={`${p.day}:${p.activity_id}`}>
                      <Icon size={14} />
                      <span>
                        <b>{a.name}</b>
                        <small>
                          {a.duration} · {a.slot.replace("_", " ")} · {money(activityPrice(a, trip.brief))}
                        </small>
                      </span>
                      <button type="button" className="icon-btn" aria-label={`Remove ${a.name}`} onClick={() => removeActivity(a.id, d.day)}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  );
                })}
                {d.kind === "departure" && <p className="muted small">Check out and transfer to the airport.</p>}
                {d.kind !== "departure" && (
                  <button type="button" className="link add-link" onClick={() => setOpenDay(openDay === d.day ? null : d.day)} aria-expanded={openDay === d.day}>
                    <Plus size={13} /> {openDay === d.day ? "Close" : `Add an experience in ${d.city.name}`}
                  </button>
                )}
                {openDay === d.day && (
                  <div className="options">
                    {options.map((a) => {
                      const why = cannotPlace(trip, a.id, d.day);
                      const Icon = SLOT_ICON[a.slot];
                      return (
                        <div key={a.id} className={`option${why ? " is-off" : ""}`} data-activity={a.id}>
                          <Icon size={14} />
                          <span>
                            <b>{a.name}</b>
                            <small>
                              {a.duration} · {a.slot.replace("_", " ")}
                              {a.min_age ? ` · ages ${a.min_age}+` : ""}
                              {a.closed.length && a.closed.length < 7 ? ` · not on ${a.closed.join(", ")}` : ""}
                            </small>
                            <small className="opt-blurb">{a.blurb}</small>
                            {why && <small className="why">{why}</small>}
                          </span>
                          <span className="opt-price">{money(activityPrice(a, trip.brief))}</span>
                          <button type="button" className="btn btn-small btn-outline" disabled={!!why} onClick={() => addActivity(a.id, d.day)}>
                            Add
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      <Next to="package" label="See the package" />
    </div>
  );
}

// ─── Package ────────────────────────────────────────────────────────────────

function PackageStep() {
  const trip = useTrip((s) => s.trip);
  const navigate = useNavigate();
  const b = trip.brief;
  const d = getDestination(b.destination)!;
  const f = getFlight(trip.flight_id);
  const all = days(trip);
  const legs = transfers(trip);
  const st = stays(trip);
  const complete = !!f && st.every((s) => trip.hotels[s.city.id]);
  return (
    <div className="package">
      <div className="pkg-hero" style={{ "--hue": d.hue } as React.CSSProperties}>
        <DestinationArt id={d.id} hue={d.hue} className="pkg-art" />
        <div className="pkg-hero-text">
          <p className="eyebrow">Your package</p>
          <h2>
            {plural(b.nights ?? 0, "night")} in {d.name}
          </h2>
          <p>
            {st.map((s) => `${s.city.name} ${s.nights}N`).join(" · ")} · {travellers(trip)}
            {b.start_date ? ` · leaving ${date(b.start_date)}` : ""}
          </p>
        </div>
      </div>
      {f ? (
        <div className="pkg-flight">
          <Plane size={16} />
          <div>
            <b>
              {f.airline_name} · {f.stops ? plural(f.stops, "stop") : "nonstop"}
            </b>
            <Journey j={f.out} label="Out" on={b.start_date} />
            <Journey j={f.back} label="Back" on={all.length ? all[all.length - 1].date : null} />
            <small className="muted">{f.baggage}</small>
          </div>
          <button type="button" className="link" onClick={() => setStep("flights")}>
            Change
          </button>
        </div>
      ) : (
        <button type="button" className="pkg-missing" onClick={() => setStep("flights")}>
          <Plane size={16} /> Choose a flight to complete the package
        </button>
      )}
      <ol className="timeline">
        {all.map((day) => {
          const pick = trip.hotels[day.city.id];
          const h = pick ? day.city.hotels.find((x) => x.id === pick.hotel_id) : null;
          const leg = day.kind === "arrival" ? legs[0] : day.kind === "transfer" ? legs.find((l) => l.label.endsWith(day.city.name)) : day.kind === "departure" ? legs[legs.length - 1] : null;
          return (
            <li key={day.day} data-stage-thing={`day-${day.day}`} data-stage-label={`Day ${day.day}`}>
              <div className="tl-date">
                <b>Day {day.day}</b>
                <small>{day.date ? shortDate(day.date) : ""}</small>
              </div>
              <div className="tl-body">
                <p className="tl-city">
                  {day.city.name} <span className="day-kind">{KIND[day.kind]}</span>
                </p>
                {leg && (
                  <p className="tl-item">
                    <span className="dot transfer" />
                    {leg.label} · {leg.mode} · {leg.duration}
                  </p>
                )}
                {trip.activities
                  .filter((p) => p.day === day.day)
                  .map((p) => {
                    const a = getActivity(p.activity_id)!;
                    return (
                      <p className="tl-item" key={p.activity_id}>
                        <span className="dot act" />
                        <b>{a.name}</b> · {a.duration}, {a.slot.replace("_", " ")}
                        <button type="button" className="icon-btn" aria-label={`Remove ${a.name}`} onClick={() => removeActivity(a.id, day.day)}>
                          <X size={13} />
                        </button>
                      </p>
                    );
                  })}
                {day.kind !== "departure" && (
                  <p className="tl-item stay">
                    <span className="dot hotel" />
                    Night at {h ? h.name : <button type="button" className="link" onClick={() => (setHotelCity(day.city.id), setStep("hotels"))}>choose a hotel</button>}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      <h3 className="pkg-sub">Price, line by line</h3>
      <Breakdown trip={trip} />
      <div className="panel-foot">
        <button type="button" className="btn btn-ghost" onClick={() => setStep("days")}>
          Edit days
        </button>
        <button type="button" className="btn btn-primary" disabled={!complete} onClick={() => navigate("/checkout")} data-dock-avoid>
          Review & pay <ArrowRight size={16} />
        </button>
      </div>
    </div>
  );
}
