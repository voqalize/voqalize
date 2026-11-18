/** One listing in a list: picture, price, the facts a buyer scans, heart and compare. */
import { Heart, MapPin, Train, Building2, School } from "lucide-react";
import { Link } from "react-router-dom";
import { type Listing, inr, officeKm, placeName, priceLabel } from "../data/homes";
import { useStore } from "../state/store";
import { BuildingArt } from "./Art";

const KIND: Record<Listing["kind"], string> = { new: "New · Kosha project", resale: "Resale", rent: "For rent" };

export function ListingCard({ l, office, rank }: { l: Listing; office?: string | null; rank?: number }) {
  const focus = useStore((s) => s.focus === l.id);
  const hearted = useStore((s) => s.shortlist.includes(l.id));
  const compared = useStore((s) => s.compare.includes(l.id));
  const { toggleShortlist, toggleCompare, setFocus } = useStore.getState();
  const km = office ? officeKm(l, office) : undefined;
  return (
    <article
      className={`lcard${focus ? " is-focus" : ""}`}
      data-stage-thing={`listing:${l.id}`}
      data-stage-label={l.title}
      onMouseEnter={() => setFocus(l.id)}
      onMouseLeave={() => setFocus(null)}
    >
      <Link to={`/listing/${l.id}`} className="lcard-art" aria-label={l.title}>
        <BuildingArt id={l.id} palette={l.palette} floors={l.total_floors} label={`${l.society}, illustration`} />
        <span className={`tag is-${l.kind}`}>{KIND[l.kind]}</span>
        {rank ? <span className="lcard-rank">{rank}</span> : null}
      </Link>
      <div className="lcard-body">
        <div className="lcard-top">
          <p className="lcard-price">
            {priceLabel(l)}
            {l.deal === "buy" && l.price_per_sqft ? <small> · {inr(l.price_per_sqft)}/sq ft</small> : <small> · deposit {inr(l.deposit ?? 0)}</small>}
          </p>
          <button
            type="button"
            className={`heart${hearted ? " is-on" : ""}`}
            aria-pressed={hearted}
            aria-label={hearted ? "Remove from shortlist" : "Add to shortlist"}
            data-stage-part={`heart:${l.id}`}
            onClick={() => toggleShortlist(l.id)}
          >
            <Heart size={18} fill={hearted ? "currentColor" : "none"} />
          </button>
        </div>
        <h3>
          <Link to={`/listing/${l.id}`}>{l.title}</Link>
        </h3>
        <p className="lcard-where">
          <MapPin size={13} /> {l.locality}, {l.city[0].toUpperCase() + l.city.slice(1)} · <span className="mono">{l.id}</span>
        </p>
        <ul className="lcard-facts">
          <li>
            <b>{l.carpet_sqft.toLocaleString("en-IN")}</b> sq ft carpet
          </li>
          <li>
            Floor <b>{l.floor}</b>/{l.total_floors}
          </li>
          <li>{l.facing} facing</li>
          <li className={l.possession === "ready" ? "ok" : "uc"}>{l.possession === "ready" ? (l.deal === "rent" ? "Available now" : "Ready to move") : `Possession ${l.possession_date}`}</li>
        </ul>
        <p className="lcard-near">
          {km !== undefined ? (
            <span className="is-office">
              <Building2 size={13} /> {km} km to {placeName(office)}
            </span>
          ) : null}
          <span>
            <Train size={13} /> {l.nearby.metro[0]?.name} {l.nearby.metro[0]?.km} km
          </span>
          <span>
            <School size={13} /> {l.nearby.schools[0]?.name.split(" ").slice(0, 2).join(" ")} {l.nearby.schools[0]?.km} km</span>
        </p>
        <label className="lcard-compare" data-stage-part={`compare:${l.id}`}>
          <input type="checkbox" checked={compared} onChange={() => toggleCompare(l.id)} /> Compare
        </label>
      </div>
    </article>
  );
}
