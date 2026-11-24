/**
 * Wanderloom's own art: the logo, and one illustrated scene per destination
 * (SVG, drawn here, tinted with the destination's `hue` from the inventory).
 * No photographs: nothing on the page is anyone else's picture.
 */
import type { CSSProperties } from "react";

export function Logo({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <circle cx="20" cy="20" r="19" fill="var(--ink)" />
      {/* A loom's warp, and the route woven through it. */}
      <path d="M11 11v18M16 11v18M21 11v18M26 11v18M31 11v18" stroke="rgba(255,255,255,.28)" strokeWidth="1.4" />
      <path d="M8 27c5-9 9-13 13-9s6 0 11-8" fill="none" stroke="var(--marigold)" strokeWidth="3.2" strokeLinecap="round" />
      <circle cx="32" cy="10" r="2.6" fill="var(--coral)" />
    </svg>
  );
}

type Motif = "hills" | "beach" | "fort" | "terrace" | "dunes" | "islands" | "towers" | "atoll" | "alps";
const MOTIF: Record<string, Motif> = {
  kerala: "hills",
  goa: "beach",
  rajasthan: "fort",
  bali: "terrace",
  dubai: "dunes",
  thailand: "islands",
  singapore: "towers",
  maldives: "atoll",
  switzerland: "alps",
};

/** A small scene for a destination (or a city, by its destination's motif). */
export function DestinationArt({ id, hue, className, style }: { id: string; hue: string; className?: string; style?: CSSProperties }) {
  const m = MOTIF[id] ?? "beach";
  const sky = `color-mix(in oklab, ${hue} 22%, #fff6e6)`;
  const far = `color-mix(in oklab, ${hue} 45%, #f5e6cf)`;
  const mid = `color-mix(in oklab, ${hue} 75%, #1b3b3a)`;
  const near = `color-mix(in oklab, ${hue} 55%, #0d2a2a)`;
  return (
    <svg className={className} style={style} viewBox="0 0 320 180" preserveAspectRatio="xMidYMid slice" role="img" aria-label="">
      <rect width="320" height="180" fill={sky} />
      <circle cx="248" cy="52" r="22" fill="#f6c46a" opacity=".9" />
      {m === "hills" && (
        <>
          <path d="M0 110 Q60 60 120 100 T240 90 T320 100V180H0Z" fill={far} />
          <path d="M0 130 Q80 90 160 125 T320 120V180H0Z" fill={mid} />
          {[20, 50, 80, 110, 140].map((x) => (
            <path key={x} d={`M${x} 150 q10 -8 20 0`} stroke="rgba(255,255,255,.35)" fill="none" strokeWidth="2" />
          ))}
          <path d="M180 160 q40 -14 90 -2 l-6 10 h-80z" fill={near} />
          <path d="M200 146 h52 l-6 -10 h-40z" fill="#f3d9a8" />
        </>
      )}
      {m === "beach" && (
        <>
          <rect y="105" width="320" height="40" fill={`color-mix(in oklab, ${hue} 35%, #6cc3c9)`} />
          <path d="M0 140 Q160 120 320 140V180H0Z" fill="#f2dcb0" />
          <path d="M60 140 q-6 -40 4 -70" stroke={near} strokeWidth="5" fill="none" />
          <path d="M64 72 q-26 -6 -36 10 M64 72 q24 -10 36 6 M64 72 q-10 -20 -30 -18 M64 72 q14 -18 30 -14" stroke={mid} strokeWidth="6" fill="none" strokeLinecap="round" />
          <path d="M220 112 l20 -26 l4 26z" fill="#fff" opacity=".85" />
        </>
      )}
      {m === "fort" && (
        <>
          <path d="M0 120 Q100 95 200 115 T320 105V180H0Z" fill={far} />
          <path d="M70 120 V80 h12 v-8 h10 v8 h20 v-8 h10 v8 h20 v-8 h10 v8 h12 V120Z" fill={mid} />
          <path d="M140 80 a14 14 0 0 1 28 0" fill={near} />
          <rect y="140" width="320" height="40" fill={`color-mix(in oklab, ${hue} 30%, #7fb7c4)`} />
          <path d="M210 150 h50 v-12 h-50z" fill="#f4e3c3" />
        </>
      )}
      {m === "terrace" && (
        <>
          {[0, 1, 2, 3, 4].map((i) => (
            <path key={i} d={`M0 ${90 + i * 18} Q160 ${70 + i * 18} 320 ${92 + i * 18}V180H0Z`} fill={`color-mix(in oklab, ${hue} ${40 + i * 12}%, #e9f0c8)`} />
          ))}
          <path d="M250 120 l18 -34 l18 34z M256 120 l12 -22 l12 22z" fill={near} />
        </>
      )}
      {m === "dunes" && (
        <>
          <path d="M120 120 V40 l6 -12 l6 12 V120Z" fill={mid} opacity=".7" />
          <path d="M150 120 V64 h14 v56Z M90 120 V76 h12 v44Z" fill={mid} opacity=".55" />
          <path d="M0 130 Q90 100 170 132 T320 122V180H0Z" fill={`color-mix(in oklab, ${hue} 70%, #f4cf8e)`} />
          <path d="M0 152 Q120 128 230 156 T320 150V180H0Z" fill={`color-mix(in oklab, ${hue} 85%, #c7843c)`} />
        </>
      )}
      {m === "islands" && (
        <>
          <rect y="110" width="320" height="70" fill={`color-mix(in oklab, ${hue} 20%, #5fb8c2)`} />
          <path d="M40 112 q10 -60 30 -62 q16 4 20 62z" fill={mid} />
          <path d="M190 112 q6 -44 22 -48 q16 6 18 48z" fill={near} />
          <path d="M120 130 h40 l-8 8 h-28z" fill="#8b5a3c" />
          <path d="M140 130 v-20" stroke="#8b5a3c" strokeWidth="2" />
        </>
      )}
      {m === "towers" && (
        <>
          <rect x="70" y="60" width="26" height="80" fill={mid} />
          <rect x="102" y="54" width="26" height="86" fill={mid} />
          <rect x="134" y="60" width="26" height="80" fill={mid} />
          <path d="M64 56 h104 q-4 -10 -52 -10 t-52 10z" fill={near} />
          {[200, 230, 260].map((x) => (
            <path key={x} d={`M${x} 140 v-40 m-14 0 q14 -18 28 0`} stroke={near} strokeWidth="4" fill="none" />
          ))}
          <rect y="140" width="320" height="40" fill={`color-mix(in oklab, ${hue} 35%, #6a9fc7)`} />
        </>
      )}
      {m === "atoll" && (
        <>
          <rect y="96" width="320" height="84" fill={`color-mix(in oklab, ${hue} 30%, #5ed0d0)`} />
          <ellipse cx="160" cy="132" rx="110" ry="18" fill={`color-mix(in oklab, ${hue} 10%, #a7ece6)`} />
          {[60, 100, 140].map((x) => (
            <g key={x}>
              <rect x={x} y="104" width="26" height="12" fill="#f1e2c4" />
              <path d={`M${x - 4} 106 l17 -12 l17 12z`} fill={near} />
              <path d={`M${x + 6} 116 v10 M${x + 20} 116 v10`} stroke="#7a5236" strokeWidth="2" />
            </g>
          ))}
          <path d="M186 116 h70" stroke="#7a5236" strokeWidth="2" />
        </>
      )}
      {m === "alps" && (
        <>
          <path d="M0 130 L70 50 L120 110 L180 30 L250 112 L290 80 L320 104V180H0Z" fill={mid} />
          <path d="M70 50 l-16 18 l10 -2 l6 8 l8 -10 l8 4z M180 30 l-20 24 l12 -4 l8 10 l8 -12 l12 6z" fill="#fff" />
          <rect y="140" width="320" height="40" fill={`color-mix(in oklab, ${hue} 25%, #7cc0c6)`} />
          <path d="M200 152 h60 l-4 8 h-52z" fill="#fff" />
        </>
      )}
    </svg>
  );
}
