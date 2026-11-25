/** Things to do: the resort map, kind filters, activity cards (map + Book). */
import { Clock3, MapPin, Users } from "lucide-react";
import { useState } from "react";
import { PageHeader, Pill } from "../components/Shell";
import { ResortMap } from "../components/ResortMap";
import { ACTIVITIES, type Activity, getPlace } from "../data";
import { price } from "../lib/format";
import { openActivity, showOnMap, useStay } from "../state/store";
import { BookingList, ExperienceTabs } from "./Spa";
import "../styles/experiences.css";

const KINDS: { id: Activity["kind"] | "all"; label: string }[] = [
  { id: "all", label: "All" },
  { id: "pools", label: "Pools" },
  { id: "kids", label: "Kids" },
  { id: "golf", label: "Golf" },
  { id: "sport", label: "Sport" },
  { id: "fitness", label: "Fitness" },
  { id: "tours", label: "Tours" },
  { id: "music", label: "Music" },
];

function toMap(place: string) {
  showOnMap(place);
  document.getElementById("resort-map")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export function Activities() {
  const [kind, setKind] = useState<Activity["kind"] | "all">("all");
  const pin = useStay((s) => s.mapPin);
  const booked = useStay((s) => s.bookings.some((b) => b.kind === "activity"));
  const list = ACTIVITIES.filter((a) => kind === "all" || a.kind === kind);
  return (
    <div className="page" data-stage-place="activities">
      <PageHeader title="Experiences" sub="Book the spa, the courses and the coast" tabs={<ExperienceTabs />} />
      <div className="ex-wrap">
        <ResortMap />

        {booked ? (
          <>
            <div className="ex-section-title">
              <h2>You're booked</h2>
            </div>
            <BookingList kind="activity" />
          </>
        ) : null}

        <div className="ex-section-title">
          <h2>Things to do</h2>
          <span>{list.length} at Belmonte</span>
        </div>
        <div className="ex-chips" data-stage-group role="tablist" aria-label="Kind">
          {KINDS.map((k) => {
            const on = kind === k.id;
            return (
              <button key={k.id} type="button" role="tab" aria-selected={on} className={`ex-chip${on ? " is-on" : ""}`} onClick={() => setKind(k.id)} data-stage-thing={`kind-${k.id}`} data-stage-label={k.label}>
                {k.label}
              </button>
            );
          })}
        </div>

        {list.map((a) => {
          const place = getPlace(a.place);
          const here = pin === a.place;
          return (
            <article key={a.id} className="ex-card" data-stage-thing={`activity-${a.id}`} data-stage-label={a.name}>
              <div className="ex-card-head">
                <div>
                  <h3>
                    {a.name} {a.tonight ? <Pill tone="brass">Tonight</Pill> : null}
                  </h3>
                  <p>{a.desc}</p>
                </div>
                <div className="ex-price">
                  <b>{a.price ? price(a.price) : "Free"}</b>
                  {a.price && a.per ? <small>per {a.per}</small> : null}
                </div>
              </div>
              <div className="ex-card-meta">
                <span>
                  <Clock3 size={13} /> {a.hours}
                </span>
                {place ? (
                  <span>
                    <MapPin size={13} /> {place.name}
                  </span>
                ) : null}
                {a.capacity ? (
                  <span>
                    <Users size={13} /> Up to {a.capacity}
                  </span>
                ) : null}
                {a.min_age ? <Pill tone="coral">{a.min_age}+</Pill> : null}
              </div>
              <div className="ex-card-actions">
                <button type="button" className="ex-btn" aria-pressed={here} onClick={() => toMap(a.place)} data-stage-thing={`activity-map-${a.id}`} data-stage-label="Show on map">
                  <MapPin size={14} /> {here ? "On the map" : "Map"}
                </button>
                {a.bookable ? (
                  <button type="button" className="ex-btn is-dark" onClick={() => openActivity(a.id)} data-stage-thing={`activity-book-${a.id}`} data-stage-label={`Book ${a.name}`}>
                    Book
                  </button>
                ) : (
                  <span className="ex-muted" style={{ alignSelf: "center" }}>
                    No booking needed
                  </span>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
