/**
 * The drawn city map: water, roads, metro lines with their stations, locality
 * names, offices and schools, and a pin per listing. No tiles, no network;
 * everything comes from homes.json. A pin is `data-stage-thing="pin:<id>"`.
 */
import { Building2, GraduationCap } from "lucide-react";
import { type City, type Listing, priceLabel } from "../data/homes";

const W = 100;
const H = 70;
const pts = (p: [number, number][]) => p.map(([x, y]) => `${x},${y}`).join(" ");

interface Props {
  city: City;
  listings: Listing[];
  focus?: string | null;
  office?: string | null;
  officeKm?: number | null;
  onPin?: (id: string) => void;
  onHover?: (id: string | null) => void;
  compact?: boolean;
  className?: string;
  /** Extra pins for projects (the project page): drawn as squares. */
  projects?: { id: string; name: string; x: number; y: number }[];
}

export function CityMap({ city, listings, focus, office, officeKm, onPin, onHover, compact, className, projects }: Props) {
  const officePlace = office ? city.places.find((p) => p.id === office) : undefined;
  const radius = officePlace && officeKm ? officeKm / 0.25 : null;
  return (
    <svg className={`citymap${compact ? " is-compact" : ""} ${className ?? ""}`} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Map of ${city.name} with ${listings.length} homes`}>
      <rect width={W} height={H} fill="var(--map-land)" />
      {/* a faint grid of streets */}
      {Array.from({ length: 13 }, (_, i) => (
        <line key={`v${i}`} x1={i * 8} y1="0" x2={i * 8 + 4} y2={H} stroke="var(--map-street)" strokeWidth="0.25" />
      ))}
      {Array.from({ length: 9 }, (_, i) => (
        <line key={`h${i}`} x1="0" y1={i * 8} x2={W} y2={i * 8 + 3} stroke="var(--map-street)" strokeWidth="0.25" />
      ))}
      {city.water.map((w) =>
        w.points.length > 4 && w.name.toLowerCase().includes("river") ? (
          <polyline key={w.name} points={pts(w.points)} fill="none" stroke="var(--map-water)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        ) : (
          <polygon key={w.name} points={pts(w.points)} fill="var(--map-water)" />
        ),
      )}
      {city.roads.map((r) => (
        <polyline key={r.name} points={pts(r.points)} fill="none" stroke="var(--map-road)" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
      ))}
      {radius ? <circle cx={officePlace!.x} cy={officePlace!.y} r={radius} fill="rgba(194,65,12,0.07)" stroke="var(--accent)" strokeWidth="0.3" strokeDasharray="1 1" /> : null}
      {city.metro.map((m) => (
        <polyline key={m.name} points={pts(m.points)} fill="none" stroke={m.colour} strokeWidth="0.8" strokeLinecap="round" strokeLinejoin="round" opacity="0.85" />
      ))}
      {city.places
        .filter((p) => p.kind === "metro")
        .map((p) => (
          <g key={p.id}>
            <circle cx={p.x} cy={p.y} r="0.9" fill="#fff" stroke="#334155" strokeWidth="0.35" />
            <title>{p.name}</title>
          </g>
        ))}
      {city.localities.map((l) => (
        <text key={l.name} x={l.x} y={l.y - 3.2} fontSize={compact ? 2.4 : 2} textAnchor="middle" className="citymap-locality">
          {l.name}
        </text>
      ))}
      {city.places
        .filter((p) => p.kind !== "metro")
        .map((p) => (
          <g key={p.id} transform={`translate(${p.x - 1.4}, ${p.y - 1.4})`} className={`citymap-place is-${p.kind}${p.id === office ? " is-on" : ""}`}>
            <title>{p.name}</title>
            <rect width="2.8" height="2.8" rx="0.6" />
            {p.kind === "office" ? <Building2 x="0.4" y="0.4" width="2" height="2" strokeWidth="2" /> : <GraduationCap x="0.4" y="0.4" width="2" height="2" strokeWidth="2" />}
            {!compact && p.kind === "office" ? (
              <text x="3.4" y="2.1" fontSize="1.4" className="citymap-place-name">
                {p.name}
              </text>
            ) : null}
          </g>
        ))}
      {projects?.map((p) => (
        <g key={p.id} transform={`translate(${p.x}, ${p.y})`} className="citymap-project">
          <rect x="-1.6" y="-1.6" width="3.2" height="3.2" rx="0.6" />
          <text x="2.4" y="0.8" fontSize="1.9">
            {p.name}
          </text>
        </g>
      ))}
      {listings.map((l) => {
        const on = l.id === focus;
        return (
          <g
            key={l.id}
            className={`citymap-pin${on ? " is-on" : ""} is-${l.deal}`}
            transform={`translate(${l.x}, ${l.y})`}
            data-stage-thing={`pin:${l.id}`}
            data-stage-label={l.title}
            onClick={() => onPin?.(l.id)}
            onMouseEnter={() => onHover?.(l.id)}
            onMouseLeave={() => onHover?.(null)}
            role="button"
            aria-label={`${l.title}, ${priceLabel(l)}`}
          >
            <path d="M0 0 C -1.6 -2.2 -2.4 -3.2 -2.4 -4.4 A 2.4 2.4 0 1 1 2.4 -4.4 C 2.4 -3.2 1.6 -2.2 0 0 Z" />
            <circle cy="-4.4" r="0.9" fill="#fff" />
            {on ? (
              <g transform="translate(0,-8.6)">
                <rect x="-7" y="-2.4" width="14" height="3.6" rx="1" className="citymap-tag" />
                <text y="0.4" textAnchor="middle" fontSize="1.9" fill="#fff">
                  {priceLabel(l)}
                </text>
              </g>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}
