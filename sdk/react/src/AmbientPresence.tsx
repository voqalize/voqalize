/**
 * AmbientPresence — the voice agent as a property of the whole page, not a
 * widget parked in a corner.
 *
 * It paints a full-viewport border glow (fixed, `inset: 0`, `pointer-events:
 * none`) that sits above the app's own chrome, so the ring reads unbroken along
 * all four edges instead of being masked by opaque top bars and rails. The agent's
 * state is legible peripherally — by hue and motion, not by reading a label:
 *
 *   - offline   — a hairline seam; the session is not live
 *   - idle      — faint, slow breathing (connected, quiet)
 *   - listening — steady, brighter ring (hearing the user)
 *   - thinking  — shifts to the `thinking` hue, quickest pulse (a different hue
 *                 reads as "different mode" even at the edge of vision)
 *   - speaking  — back to the primary hue, widest and brightest pulse
 *
 * Everything visual is a prop. `palette` names the hue per state; `weight` scales
 * the ring, `tempo` the breathing period, so a calm product can slow the whole
 * thing down without forking the component. The optional `beam` layer draws a
 * short travelling line from the screen edge to an element the agent just acted
 * on — the visual tell that the agent, not the user, moved the screen.
 *
 * The component is deliberately self-contained: no CSS import, no dependencies
 * beyond React. It ships its own `<style>` block and plumbs the palette through
 * CSS custom properties, so it drops into any app — Tailwind, CSS-in-JS, or plain
 * stylesheets — without a build step or a stylesheet side effect (the package
 * declares `sideEffects: false`).
 *
 * `prefers-reduced-motion` collapses all of it to a static, low-opacity ring.
 */

import { useEffect, useRef, useState } from "react";
import type { VoqalBotState, VoqalConnectionState } from "./useVoqalSession";

/** One hue per agent state, plus the offline seam and the beam. */
export interface AmbientPresencePalette {
  /** Connected and quiet. */
  idle: string;
  /** Hearing the user. */
  listening: string;
  /** Reasoning — give this a distinctly different hue; it is the state a user
   *  reads peripherally most often. */
  thinking: string;
  /** Answering. */
  speaking: string;
  /** The hairline seam shown when no session is live. */
  offline: string;
  /** The optional beam layer's stroke. */
  beam: string;
}

/**
 * A pointer at something on screen. Change `id` to fire a new beam; `targetId`
 * is the `id` of the DOM element to point at. Pass `null` for no beam.
 */
export interface AmbientPresenceBeam {
  /** Changes whenever a new beam should fire (a nonce, a counter, a timestamp). */
  id: string | number;
  /** `document.getElementById` target the beam travels to. */
  targetId: string;
}

export interface AmbientPresenceProps {
  /** The agent's conversational state — pass `botState` from `useVoqalSession`. */
  botState?: VoqalBotState;
  /**
   * Transport state — pass `connectionState` from `useVoqalSession`. Anything
   * other than `"connected"` renders the offline seam.
   */
  connectionState?: VoqalConnectionState;
  /** Per-state hues. Any subset; the rest fall back to the Voqalize default. */
  palette?: Partial<AmbientPresencePalette>;
  /** Breathing-period multiplier. `1` is the default cadence; `2` is half speed. */
  tempo?: number;
  /** Ring-thickness multiplier. `1` is the default weight. */
  weight?: number;
  /** Stacking order. Default `90` — above app chrome, below modals. */
  zIndex?: number;
  /** Corner radius of the ring, for apps whose shell is inset or rounded. */
  radius?: number | string;
  /** Optional pointer beam. Omit entirely if the demo never points at anything. */
  beam?: AmbientPresenceBeam | null;
}

/** Voqalize house palette: vermilion presence, amber reasoning. */
const DEFAULT_PALETTE: AmbientPresencePalette = {
  idle: "#E24E2A",
  listening: "#E24E2A",
  thinking: "#B9862E",
  speaking: "#E24E2A",
  offline: "#8F8B85",
  beam: "#E24E2A",
};

const BEAM_MS = 900;

/**
 * Any CSS hex or `rgb()`/`rgba()` colour → an `"r, g, b"` triple, so the
 * stylesheet can vary alpha per state (`rgba(var(--…), 0.47)`) without asking
 * callers for eight-digit hex. Unparseable input falls back to the default hue.
 */
function rgbTriple(color: string, fallback: string): string {
  const parsed = parseColor(color) ?? parseColor(fallback);
  return parsed ?? "226, 78, 42";
}

function parseColor(color: string): string | null {
  const c = color.trim();
  const hex = /^#([0-9a-f]{3,8})$/i.exec(c);
  if (hex) {
    let h = hex[1];
    if (h.length === 3 || h.length === 4) {
      h = h
        .slice(0, 3)
        .split("")
        .map((ch) => ch + ch)
        .join("");
    }
    if (h.length < 6) return null;
    const n = Number.parseInt(h.slice(0, 6), 16);
    return `${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}`;
  }
  const fn = /^rgba?\(([^)]+)\)$/i.exec(c);
  if (fn) {
    const parts = fn[1].split(/[\s,/]+/).filter(Boolean).slice(0, 3);
    if (parts.length === 3) return parts.map((p) => Math.round(Number.parseFloat(p))).join(", ");
  }
  return null;
}

interface DrawnBeam {
  key: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export function AmbientPresence({
  botState = "idle",
  connectionState = "idle",
  palette,
  tempo = 1,
  weight = 1,
  zIndex = 90,
  radius = 0,
  beam,
}: AmbientPresenceProps) {
  const [beams, setBeams] = useState<DrawnBeam[]>([]);
  const keyRef = useRef(0);
  const beamId = beam?.id;
  const beamTarget = beam?.targetId;

  // One beam per change of `beam.id`, measured at fire time against the live DOM.
  useEffect(() => {
    if (beamId === undefined || !beamTarget) return;
    const el = document.getElementById(beamTarget);
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const x2 = rect.left + Math.min(140, rect.width * 0.25);
    const y2 = Math.max(24, Math.min(window.innerHeight - 24, rect.top + rect.height / 2));
    const key = ++keyRef.current;
    setBeams((list) => [...list, { key, x1: 0, y1: y2, x2, y2 }]);
    const t = window.setTimeout(() => {
      setBeams((list) => list.filter((b) => b.key !== key));
    }, BEAM_MS);
    return () => window.clearTimeout(t);
  }, [beamId, beamTarget]);

  const p = { ...DEFAULT_PALETTE, ...palette };
  const state = connectionState === "connected" ? botState : "offline";

  const vars = {
    "--vz-presence-idle": rgbTriple(p.idle, DEFAULT_PALETTE.idle),
    "--vz-presence-listening": rgbTriple(p.listening, DEFAULT_PALETTE.listening),
    "--vz-presence-thinking": rgbTriple(p.thinking, DEFAULT_PALETTE.thinking),
    "--vz-presence-speaking": rgbTriple(p.speaking, DEFAULT_PALETTE.speaking),
    "--vz-presence-offline": rgbTriple(p.offline, DEFAULT_PALETTE.offline),
    "--vz-presence-tempo": String(tempo),
    "--vz-presence-weight": String(weight),
    "--vz-presence-z": String(zIndex),
    "--vz-presence-radius": typeof radius === "number" ? `${radius}px` : radius,
    "--vz-presence-beam": p.beam,
  } as React.CSSProperties;

  return (
    <>
      <div className="vz-presence" data-vz-state={state} style={vars} aria-hidden />
      {beams.length > 0 && (
        <svg className="vz-presence-beams" style={vars} aria-hidden>
          {beams.map((b) => (
            <line key={b.key} x1={b.x1} y1={b.y1} x2={b.x2} y2={b.y2} className="vz-presence-beam" />
          ))}
        </svg>
      )}
      <style>{STYLES}</style>
    </>
  );
}

const STYLES = `
.vz-presence {
  position: fixed;
  inset: 0;
  z-index: var(--vz-presence-z, 90);
  pointer-events: none;
  border-radius: var(--vz-presence-radius, 0);
  transition: box-shadow 0.6s ease, opacity 0.6s ease;
}

/* No live session: a seam, barely there. */
.vz-presence[data-vz-state="offline"] {
  box-shadow: inset 0 0 0 1px rgba(var(--vz-presence-offline), 0.55);
  opacity: 0.6;
}

.vz-presence[data-vz-state="idle"] {
  box-shadow:
    inset 0 0 0 calc(3px * var(--vz-presence-weight)) rgba(var(--vz-presence-idle), 0.47),
    inset 0 0 90px calc(6px * var(--vz-presence-weight)) rgba(var(--vz-presence-idle), 0.15);
  animation: vz-presence-idle calc(5.5s * var(--vz-presence-tempo)) ease-in-out infinite;
}

.vz-presence[data-vz-state="listening"] {
  box-shadow:
    inset 0 0 0 calc(4px * var(--vz-presence-weight)) rgba(var(--vz-presence-listening), 0.69),
    inset 0 0 130px calc(10px * var(--vz-presence-weight)) rgba(var(--vz-presence-listening), 0.25);
  animation: vz-presence-listening calc(3.2s * var(--vz-presence-tempo)) ease-in-out infinite;
}

/* A different hue, and the quickest pulse — "thinking" must be unmistakable
   without looking directly at any edge. */
.vz-presence[data-vz-state="thinking"] {
  box-shadow:
    inset 0 0 0 calc(4px * var(--vz-presence-weight)) rgba(var(--vz-presence-thinking), 0.75),
    inset 0 0 150px calc(12px * var(--vz-presence-weight)) rgba(var(--vz-presence-thinking), 0.30);
  animation: vz-presence-thinking calc(0.9s * var(--vz-presence-tempo)) ease-in-out infinite;
}

.vz-presence[data-vz-state="speaking"] {
  box-shadow:
    inset 0 0 0 calc(5px * var(--vz-presence-weight)) rgba(var(--vz-presence-speaking), 0.90),
    inset 0 0 180px calc(16px * var(--vz-presence-weight)) rgba(var(--vz-presence-speaking), 0.35);
  animation: vz-presence-speaking calc(1.1s * var(--vz-presence-tempo)) ease-in-out infinite;
}

@keyframes vz-presence-idle {
  0%, 100% { opacity: 0.55; }
  50%      { opacity: 0.9; }
}
@keyframes vz-presence-listening {
  0%, 100% { opacity: 0.85; }
  50%      { opacity: 1; }
}
@keyframes vz-presence-thinking {
  0%, 100% {
    opacity: 0.7;
    box-shadow:
      inset 0 0 0 calc(4px * var(--vz-presence-weight)) rgba(var(--vz-presence-thinking), 0.75),
      inset 0 0 120px calc(8px * var(--vz-presence-weight)) rgba(var(--vz-presence-thinking), 0.30);
  }
  50% {
    opacity: 1;
    box-shadow:
      inset 0 0 0 calc(5px * var(--vz-presence-weight)) rgba(var(--vz-presence-thinking), 0.88),
      inset 0 0 170px calc(16px * var(--vz-presence-weight)) rgba(var(--vz-presence-thinking), 0.40);
  }
}
@keyframes vz-presence-speaking {
  0%, 100% { opacity: 0.8; }
  50%      { opacity: 1; }
}

.vz-presence-beams {
  position: fixed;
  inset: 0;
  width: 100vw;
  height: 100vh;
  z-index: calc(var(--vz-presence-z, 90) + 1);
  pointer-events: none;
}
.vz-presence-beam {
  stroke: var(--vz-presence-beam);
  stroke-width: 2.5;
  stroke-linecap: round;
  filter: drop-shadow(0 0 7px var(--vz-presence-beam));
  stroke-dasharray: 10 8;
  animation: vz-presence-beam-travel ${BEAM_MS}ms ease-out forwards;
}
@keyframes vz-presence-beam-travel {
  0%   { opacity: 0; stroke-dashoffset: 60; }
  15%  { opacity: 1; }
  75%  { opacity: 0.9; stroke-dashoffset: 0; }
  100% { opacity: 0; stroke-dashoffset: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .vz-presence { animation: none !important; opacity: 0.6 !important; }
  .vz-presence-beam {
    animation: none !important;
    opacity: 0.5 !important;
    stroke-dasharray: none;
  }
}
`;
