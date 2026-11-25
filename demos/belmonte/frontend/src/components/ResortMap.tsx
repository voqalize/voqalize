/**
 * An illustrated map of Hotel Belmonte: the Pacific to the west, cliffs along
 * the shore, Belmonte Cove and its beach to the south-west, lawns, paths, the
 * links up on the bluff. Every `PLACES` entry is a pin at its x/y percent;
 * the store's `mapPin` pulses one and shows its name. Tapping a pin calls
 * `showOnMap` (tap again to clear).
 */
import { PLACES } from "../data";
import { showOnMap, useStay } from "../state/store";
import "../styles/experiences.css";

// The art is drawn on a 400 × 400 grid; pins are at x/y percent of it.
const LAND =
  "M70 0C58 30 50 60 58 92C64 116 56 136 60 150C64 176 48 196 44 216C40 236 38 252 50 266C40 276 32 288 30 300C44 330 80 352 116 352C146 352 160 362 166 400H400V0Z";
const COAST_WEST = "M70 0C58 30 50 60 58 92C64 116 56 136 60 150C64 176 48 196 44 216C40 236 38 252 50 266";
const COVE = "M30 300C44 330 80 352 116 352C146 352 160 362 166 400";
const LAWN =
  "M92 30C140 14 230 22 300 14C350 10 392 24 392 70C394 140 392 230 388 300C386 350 360 384 300 388C250 392 210 390 186 372C170 352 140 338 110 330C80 322 62 300 66 272C70 240 60 214 72 186C84 160 76 120 80 90C82 60 74 40 92 30Z";

const TREES: [number, number, number][] = [
  [98, 52, 1], [112, 40, 0], [130, 66, 1], [92, 110, 0], [108, 124, 1], [122, 196, 1], [104, 214, 0], [96, 240, 1],
  [178, 92, 0], [150, 104, 1], [236, 160, 1], [312, 150, 0], [240, 290, 1], [262, 304, 0], [214, 260, 1], [176, 290, 0],
  [196, 318, 1], [300, 290, 1], [320, 320, 0], [350, 300, 1], [368, 240, 0], [372, 200, 1], [300, 110, 1], [276, 52, 0],
  [160, 196, 0], [82, 292, 1], [366, 140, 1], [222, 120, 0], [124, 168, 1], [352, 360, 0], [270, 360, 1], [228, 352, 0],
];

function Tree({ x, y, kind }: { x: number; y: number; kind: number }) {
  if (kind === 1)
    return (
      <g transform={`translate(${x} ${y})`}>
        <ellipse cx="1.5" cy="6" rx="4" ry="1.6" fill="#13212b" opacity="0.12" />
        <path d="M0 -9C3 -4 4.5 1 3.5 5H-3.5C-4.5 1 -3 -4 0 -9Z" fill="#4c6a52" />
        <path d="M0 -9C1.5 -4 2 1 1.6 5" stroke="#6f8f6f" strokeWidth="0.8" fill="none" />
      </g>
    );
  return (
    <g transform={`translate(${x} ${y})`}>
      <ellipse cx="1.5" cy="3.5" rx="5" ry="1.8" fill="#13212b" opacity="0.12" />
      <circle r="5" fill="#6f8f6a" />
      <circle cx="-1.6" cy="-1.6" r="2.4" fill="#8aa883" />
    </g>
  );
}

function Building({ x, y, w, h, r = 3 }: { x: number; y: number; w: number; h: number; r?: number }) {
  return (
    <g>
      <rect x={x + 2} y={y + 3} width={w} height={h} rx={r} fill="#13212b" opacity="0.12" />
      <rect x={x} y={y} width={w} height={h} rx={r} fill="#e9c6a8" stroke="#b98a66" strokeWidth="1" />
      <path d={`M${x + 3} ${y + h / 2}H${x + w - 3}`} stroke="#c99a76" strokeWidth="1" />
    </g>
  );
}

function MapArt() {
  return (
    <svg className="ex-map-art" viewBox="0 0 400 400" preserveAspectRatio="xMidYMid slice" aria-hidden>
      <defs>
        <linearGradient id="ex-sea" x1="0" y1="0" x2="0.6" y2="1">
          <stop offset="0" stopColor="#9cc6c6" />
          <stop offset="1" stopColor="#5f9ea3" />
        </linearGradient>
        <linearGradient id="ex-land" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#efe4cf" />
          <stop offset="1" stopColor="#e6d6b8" />
        </linearGradient>
        <radialGradient id="ex-lawn" cx="0.55" cy="0.45" r="0.7">
          <stop offset="0" stopColor="#c4d6a9" />
          <stop offset="1" stopColor="#adc595" />
        </radialGradient>
        <pattern id="ex-fairway" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(35)">
          <rect width="8" height="8" fill="#93b67c" />
          <rect width="4" height="8" fill="#9dbf85" />
        </pattern>
      </defs>

      {/* Sea, shallows and waves */}
      <rect width="400" height="400" fill="url(#ex-sea)" />
      <path d={LAND} fill="none" stroke="#b8d8d2" strokeWidth="26" strokeLinejoin="round" />
      <path d={LAND} fill="none" stroke="#cfe5df" strokeWidth="12" strokeLinejoin="round" />
      <g stroke="#e8f3f0" strokeWidth="1.3" fill="none" strokeLinecap="round" opacity="0.75">
        <path d="M14 90c4-3 8-3 12 0s8 3 12 0" />
        <path d="M8 190c4-3 8-3 12 0s8 3 12 0" />
        <path d="M18 250c4-3 8-3 12 0" />
        <path d="M10 330c4-3 8-3 12 0s8 3 12 0" />
        <path d="M56 386c4-3 8-3 12 0s8 3 12 0" />
        <path d="M108 376c4-3 8-3 12 0" />
        <path d="M20 128c4-3 8-3 12 0" />
      </g>

      {/* Land, beach and cliffs */}
      <path d={LAND} fill="url(#ex-land)" />
      <path d={COVE} fill="none" stroke="#f3e2bf" strokeWidth="18" strokeLinecap="round" />
      <path d={COVE} fill="none" stroke="#fffaf0" strokeWidth="1.5" strokeDasharray="1 5" strokeLinecap="round" opacity="0.9" />
      <path d={COAST_WEST} fill="none" stroke="#9c8b72" strokeWidth="4" strokeLinecap="round" />
      <g stroke="#9c8b72" strokeWidth="1.2" strokeLinecap="round" opacity="0.7">
        {[12, 28, 44, 60, 76, 100, 118, 134, 150, 168, 186, 204, 222, 240, 256].map((y) => {
          const x = y < 92 ? 70 - (y / 92) * 12 + 4 : y < 150 ? 62 : y < 216 ? 58 - ((y - 150) / 66) * 12 : 48;
          return <path key={y} d={`M${x} ${y}l6 2`} />;
        })}
      </g>

      {/* Lawns and the links */}
      <path d={LAWN} fill="url(#ex-lawn)" />
      <path d="M296 22C330 14 380 18 386 46C392 80 384 118 360 132C336 144 308 136 298 110C290 86 270 70 276 48C280 34 286 26 296 22Z" fill="url(#ex-fairway)" opacity="0.95" />
      <ellipse cx="372" cy="36" rx="9" ry="6" fill="#b9d49c" />
      <path d="M373 36V22l7 3-7 3" stroke="#13212b" strokeWidth="1" fill="#c0603a" />
      <ellipse cx="318" cy="122" rx="8" ry="5" fill="#b9d49c" />
      <path d="M319 122V109l6 3-6 3" stroke="#13212b" strokeWidth="1" fill="#c0603a" />
      <ellipse cx="300" cy="64" rx="7" ry="4" fill="#efe1c0" />

      {/* Drive and paths */}
      <path d="M208 0V40" stroke="#d9cbb3" strokeWidth="11" />
      <path d="M208 0V40" stroke="#f3ebdc" strokeWidth="8" />
      <circle cx="208" cy="48" r="16" fill="#f3ebdc" stroke="#d9cbb3" strokeWidth="1.5" />
      <circle cx="208" cy="48" r="5" fill="#9cc6c6" stroke="#fffaf0" strokeWidth="1.5" />
      <path d="M206 64C204 100 202 140 200 168" stroke="#f3ebdc" strokeWidth="6" fill="none" strokeLinecap="round" />
      <g stroke="#fbf6ec" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeDasharray="0.1 5">
        <path d="M200 196C190 212 170 222 156 230" />
        <path d="M222 196C226 200 226 204 224 206" />
        <path d="M224 186C250 186 270 192 290 198" />
        <path d="M218 172C236 160 252 150 262 140" />
        <path d="M258 122C256 110 252 100 248 92" />
        <path d="M296 192C312 186 324 182 334 178" />
        <path d="M232 214C252 228 266 238 278 246" />
        <path d="M150 248C146 260 140 270 136 278" />
        <path d="M134 290C128 302 120 314 114 324" />
        <path d="M126 282C100 280 76 270 58 266" />
        <path d="M184 170C180 164 178 160 176 156" />
        <path d="M178 160C150 162 116 162 96 160" />
        <path d="M262 92C290 84 320 80 336 80" />
      </g>

      {/* Cliff pool, infinity edge to the sea */}
      <g transform="rotate(-12 88 160)">
        <rect x="72" y="153" width="34" height="13" rx="2" fill="#f7efe0" />
        <rect x="74" y="155" width="30" height="9" rx="1.5" fill="#6fb4c4" />
        <path d="M76 158h10" stroke="#d3eef2" strokeWidth="1" strokeLinecap="round" />
      </g>

      {/* Buildings */}
      <Building x={178} y={166} w={46} h={30} r={4} />
      <rect x={193} y={174} width="16" height="14" rx="2" fill="#f7efe0" stroke="#b98a66" strokeWidth="0.8" />
      <Building x={212} y={198} w={24} h={18} />
      <Building x={158} y={140} w={36} h={22} />
      <Building x={248} y={122} w={32} h={26} />
      <rect x={258} y={130} width="12" height="10" rx="2" fill="#7fc2cf" />
      <Building x={234} y={78} w={28} h={18} />
      <Building x={280} y={188} w={32} h={26} />
      <Building x={266} y={240} w={28} h={18} />
      <circle cx={286} cy={270} r="7" fill="#f3e2bf" stroke="#d9c39c" strokeWidth="1" />
      <Building x={330} y={70} w={28} h={18} />

      {/* Main pool and cabanas */}
      <path d="M134 226C134 216 150 214 160 220C172 226 176 236 168 244C160 252 146 250 140 244C134 240 134 234 134 226Z" fill="#f7efe0" />
      <path d="M137 227C137 219 150 218 158 222C168 228 171 236 165 242C159 248 148 247 143 242C138 238 137 233 137 227Z" fill="#76bccb" />
      <path d="M144 226c4-2 8-2 12 1" stroke="#d3eef2" strokeWidth="1.2" fill="none" strokeLinecap="round" />
      {[0, 1, 2, 3].map((i) => (
        <rect key={i} x={124 + i * 8} y={206} width="6" height="5" rx="1" fill="#fffaf0" stroke="#c9a467" strokeWidth="0.7" />
      ))}

      {/* Tennis courts */}
      {[0, 1].flatMap((cx) =>
        [0, 1].map((cy) => (
          <g key={`${cx}${cy}`}>
            <rect x={322 + cx * 16} y={160 + cy * 22} width="14" height="20" rx="1" fill="#6f9a86" stroke="#fffaf0" strokeWidth="0.8" />
            <path d={`M${322 + cx * 16} ${170 + cy * 22}h14`} stroke="#fffaf0" strokeWidth="0.6" />
          </g>
        )),
      )}

      {/* Fire pit lawn */}
      <circle cx="136" cy="280" r="11" fill="none" stroke="#d9c39c" strokeWidth="2" strokeDasharray="2 3" />
      <circle cx="136" cy="280" r="4" fill="#c0603a" />
      <circle cx="136" cy="280" r="1.8" fill="#f2b25c" />

      {/* Kayak dock */}
      <rect x="22" y="262" width="32" height="5" rx="1" fill="#b48e62" stroke="#8a6a46" strokeWidth="0.6" />
      <ellipse cx="30" cy="274" rx="7" ry="2" fill="#c0603a" />
      <ellipse cx="40" cy="256" rx="7" ry="2" fill="#e0b04c" />

      {/* Beach umbrellas */}
      {[
        [96, 340],
        [126, 346],
        [72, 330],
      ].map(([x, y]) => (
        <g key={`${x}`}>
          <circle cx={x} cy={y} r="4" fill="#fffaf0" />
          <path d={`M${x - 4} ${y}A4 4 0 0 1 ${x} ${y - 4}V${y}Z`} fill="#c0603a" />
          <path d={`M${x + 4} ${y}A4 4 0 0 1 ${x} ${y + 4}V${y}Z`} fill="#c0603a" />
        </g>
      ))}

      {TREES.map(([x, y, k]) => (
        <Tree key={`${x}-${y}`} x={x} y={y} kind={k} />
      ))}

      {/* Labels */}
      <text x="22" y="150" transform="rotate(-90 22 150)" textAnchor="middle" fill="#ffffff" opacity="0.8" fontFamily="var(--display)" fontStyle="italic" fontSize="13" letterSpacing="3">
        Pacific Ocean
      </text>
      <text x="96" y="388" textAnchor="middle" fill="#ffffff" opacity="0.85" fontFamily="var(--display)" fontStyle="italic" fontSize="11">
        Belmonte Cove
      </text>
      <text x="336" y="152" textAnchor="middle" fill="#2c5a5e" opacity="0.6" fontFamily="var(--sans)" fontWeight="700" fontSize="6.5" letterSpacing="1.2">
        COURTS
      </text>
      <text x="350" y="104" textAnchor="middle" fill="#2c5a5e" opacity="0.6" fontFamily="var(--sans)" fontWeight="700" fontSize="6.5" letterSpacing="1.2">
        HALCYON LINKS
      </text>

      {/* Compass */}
      <g transform="translate(28 30)">
        <circle r="13" fill="#fffaf0" opacity="0.85" />
        <path d="M0 -10L3 0 0 10-3 0Z" fill="#13212b" />
        <path d="M0 -10L3 0H-3Z" fill="#a67c3d" />
        <text y="-15" textAnchor="middle" fontFamily="var(--sans)" fontWeight="800" fontSize="7" fill="#13212b">
          N
        </text>
      </g>
    </svg>
  );
}

export function ResortMap() {
  const pin = useStay((s) => s.mapPin);
  const active = PLACES.find((p) => p.id === pin) ?? null;
  return (
    <div className="ex-map" id="resort-map" data-stage-thing="map" data-stage-label="Resort map">
      <MapArt />
      {PLACES.map((p) => {
        const on = p.id === pin;
        return (
          <button
            key={p.id}
            type="button"
            className={`ex-pin${on ? " is-on" : ""}`}
            style={{ left: `${p.x}%`, top: `${p.y}%` }}
            aria-label={p.name}
            aria-pressed={on}
            title={p.name}
            onClick={() => showOnMap(on ? null : p.id)}
            data-stage-thing={`pin-${p.id}`}
            data-stage-label={p.name}
          >
            <span className="ex-pin-dot" />
          </button>
        );
      })}
      {active ? (
        <div
          className="ex-callout"
          role="status"
          style={{
            left: `${active.x}%`,
            top: `${active.y}%`,
            transform: `translate(${active.x < 30 ? "-14px" : active.x > 70 ? "calc(-100% + 14px)" : "-50%"}, ${active.y < 22 ? "16px" : "calc(-100% - 16px)"})`,
          }}
        >
          <small>Here</small>
          {active.name}
        </div>
      ) : (
        <span className="ex-map-legend">Tap a pin to see what's there</span>
      )}
    </div>
  );
}
