/**
 * Drawn pictures, so the site needs no photographs: a building elevation in a
 * listing's own palette, a street-level view, and a floor plan drawn from its
 * BHK and carpet area. Deterministic from the listing id.
 */
import type { Listing, Project } from "../data/homes";

function seed(id: string): number {
  let h = 2166136261;
  for (const ch of id) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  return Math.abs(h);
}

interface ArtProps {
  id: string;
  palette: [string, string];
  floors: number;
  view?: "tower" | "street" | "dusk";
  className?: string;
  label?: string;
}

/** A tower (or a pair) against a soft sky. */
export function BuildingArt({ id, palette, floors, view = "tower", className, label }: ArtProps) {
  const s = seed(id + view);
  const [ink, wash] = palette;
  const dusk = view === "dusk";
  const sky = dusk ? ["#f6c7a1", "#e7a07a"] : ["#eef3f6", wash];
  const towers = view === "street" ? 3 : 1 + (s % 2);
  const rows = Math.max(6, Math.min(16, Math.round(floors / 2.2)));
  const W = 400;
  const H = 260;
  const blocks = Array.from({ length: towers }, (_, i) => {
    const w = view === "street" ? 92 + ((s >> (i * 3)) % 30) : towers === 1 ? 150 : 112;
    const h = view === "street" ? 120 + ((s >> (i * 5)) % 60) : 190 - i * 26;
    const x = view === "street" ? 30 + i * 120 : towers === 1 ? 125 : 70 + i * 140;
    return { w, h, x, y: H - 34 - h };
  });
  return (
    <svg className={className} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label ?? "Illustration of the building"} preserveAspectRatio="xMidYMid slice">
      <defs>
        <linearGradient id={`sky-${id}-${view}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={sky[0]} />
          <stop offset="1" stopColor={sky[1]} />
        </linearGradient>
      </defs>
      <rect width={W} height={H} fill={`url(#sky-${id}-${view})`} />
      <circle cx={dusk ? 330 : 60 + (s % 260)} cy={dusk ? 70 : 44} r={dusk ? 26 : 16} fill={dusk ? "#fff1dc" : "#ffffff"} opacity={dusk ? 0.9 : 0.75} />
      <path d={`M0 ${H - 60} Q 80 ${H - 90} 160 ${H - 66} T 400 ${H - 70} V ${H} H 0 Z`} fill={ink} opacity="0.12" />
      {blocks.map((b, i) => (
        <g key={i}>
          <rect x={b.x} y={b.y} width={b.w} height={b.h} fill="#fbfaf7" stroke={ink} strokeOpacity="0.35" />
          <rect x={b.x} y={b.y} width={b.w} height="8" fill={ink} />
          {Array.from({ length: rows }, (_, r) =>
            Array.from({ length: 4 }, (_, c) => {
              const gw = (b.w - 20) / 4;
              const gh = (b.h - 24) / rows;
              const lit = dusk && ((s >> ((r * 4 + c) % 28)) & 1);
              return (
                <rect
                  key={`${r}-${c}`}
                  x={b.x + 10 + c * gw + 2}
                  y={b.y + 14 + r * gh + 2}
                  width={gw - 4}
                  height={gh - 5}
                  rx="1"
                  fill={lit ? "#ffd99a" : c % 2 ? wash : "#dfe7ec"}
                  stroke={ink}
                  strokeOpacity="0.18"
                />
              );
            }),
          )}
          {Array.from({ length: rows }, (_, r) => (
            <rect key={`b${r}`} x={b.x + 6} y={b.y + 14 + (r + 1) * ((b.h - 24) / rows) - 3} width={b.w - 12} height="2" fill={ink} opacity="0.35" />
          ))}
        </g>
      ))}
      <rect y={H - 34} width={W} height="34" fill="#e7e2d6" />
      {Array.from({ length: 9 }, (_, i) => (
        <g key={i} transform={`translate(${20 + i * 46 + (s % 12)}, ${H - 34})`}>
          <rect x="-1.5" y="-14" width="3" height="14" fill="#6b5a45" />
          <circle cy="-20" r={9 + ((s >> i) % 4)} fill={ink} opacity="0.75" />
        </g>
      ))}
    </svg>
  );
}

interface Room {
  name: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

function rooms(bhk: number): Room[] {
  const r: Room[] = [];
  // A 100 × 64 plan: living and kitchen on the left, bedrooms to the right.
  r.push({ name: "Living & dining", x: 0, y: 0, w: 44, h: 40 });
  r.push({ name: "Kitchen", x: 0, y: 40, w: 24, h: 24 });
  r.push({ name: "Utility", x: 24, y: 52, w: 20, h: 12 });
  r.push({ name: "Foyer", x: 24, y: 40, w: 20, h: 12 });
  const beds = Math.max(1, bhk);
  const colW = 56 / Math.min(beds, 2);
  for (let i = 0; i < beds; i++) {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const rowsN = Math.ceil(beds / 2);
    const h = 64 / rowsN;
    const w = beds === 1 ? 56 : colW;
    r.push({ name: i === 0 ? "Master bedroom" : `Bedroom ${i + 1}`, x: 44 + col * w, y: row * h, w, h: h - (i === 0 ? 0 : 0) });
  }
  return r;
}

/** A floor plan for the listing's configuration, carpet area noted. */
export function FloorPlan({ listing, className }: { listing: Listing; className?: string }) {
  const [ink] = listing.palette;
  const plan = rooms(listing.bhk);
  const S = 5.6;
  return (
    <svg className={className} viewBox="-12 -12 584 400" role="img" aria-label={`Floor plan, ${listing.bhk} BHK, ${listing.carpet_sqft} sq ft carpet`}>
      <rect x="-12" y="-12" width="584" height="400" fill="#fbfaf7" />
      <g stroke={ink} fill="none">
        <rect x="0" y="0" width={100 * S} height={64 * S} strokeWidth="6" />
        {plan.map((room) => (
          <g key={room.name}>
            <rect x={room.x * S} y={room.y * S} width={room.w * S} height={room.h * S} strokeWidth="2.2" fill={room.name.includes("Living") ? "rgba(0,0,0,0.02)" : "none"} />
            <text x={(room.x + room.w / 2) * S} y={(room.y + room.h / 2) * S} textAnchor="middle" fontSize="13" fill={ink} stroke="none" fontFamily="Inter Variable, sans-serif">
              {room.name}
            </text>
            {room.name.startsWith("Master") || room.name.startsWith("Bedroom") ? (
              <rect x={(room.x + 3) * S} y={(room.y + 3) * S} width={14 * S * 0.6} height={18 * S * 0.5} rx="3" strokeWidth="1.2" strokeOpacity="0.5" />
            ) : null}
          </g>
        ))}
        {/* doors */}
        {plan.slice(4).map((room, i) => (
          <path key={i} d={`M ${(room.x + 2) * S} ${(room.y + room.h) * S - 1} a 18 18 0 0 1 18 -18`} strokeWidth="1.2" strokeOpacity="0.6" />
        ))}
        {Array.from({ length: listing.balconies }, (_, i) => (
          <rect key={`bal${i}`} x={(10 + i * 30) * S} y={-10} width={60} height={8} strokeWidth="1.5" strokeDasharray="4 3" />
        ))}
      </g>
      <text x="0" y={64 * S + 26} fontSize="13" fill="#5b5f66" fontFamily="Inter Variable, sans-serif">
        Indicative plan · {listing.bhk} BHK · {listing.carpet_sqft.toLocaleString("en-IN")} sq ft carpet · {listing.bathrooms} baths · {listing.balconies} balconies · not to scale
      </text>
    </svg>
  );
}

export function ProjectArt({ project, className }: { project: Project; className?: string }) {
  return <BuildingArt id={project.id} palette={project.palette} floors={project.floors} view="dusk" className={className} label={`${project.name}, illustration`} />;
}
