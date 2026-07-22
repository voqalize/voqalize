/**
 * The signature piece: a full-viewport ambient border glow standing in for
 * "the agent is live and aware of everything on screen" — not a chat bubble,
 * not a mic button. Sits ABOVE the top bar and left rail (z-index 90) so the
 * ring reads unbroken along all four edges instead of being masked by their
 * opaque backgrounds. State is legible at a glance, by color and motion, not
 * just opacity:
 *   - idle      — faint oxblood, slow breathing (connected, quiet)
 *   - listening — steady solid oxblood ring (actively hearing the lawyer)
 *   - thinking  — shifts to amber/gold, quicker pulse (reasoning — a
 *                 different hue reads as "different mode" even peripherally)
 *   - speaking  — oxblood again, fastest/widest pulse (answering)
 * When the assistant calls `point_to_clause`, a light "beam" travels from the
 * nearest screen edge to the clause's DOM rect, echoing the border glow —
 * the visual tell that the agent, not the lawyer, moved the screen.
 * `prefers-reduced-motion` collapses everything to a static low-opacity ring.
 */

import { useEffect, useRef, useState } from 'react';
import { useLegal } from './store';

interface Beam {
  id: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

const BEAM_MS = 900;

export function AmbientGlow() {
  const { botState, connectionState, pointer } = useLegal();
  const [beams, setBeams] = useState<Beam[]>([]);
  const beamIdRef = useRef(0);

  useEffect(() => {
    if (!pointer) return;
    const el = document.getElementById(`clause-${pointer.clauseId}`);
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const x2 = rect.left + Math.min(140, rect.width * 0.25);
    const y2 = Math.max(24, Math.min(window.innerHeight - 24, rect.top + rect.height / 2));
    // Nearest edge: left border, same height as the target.
    const x1 = 0;
    const y1 = y2;
    const id = ++beamIdRef.current;
    setBeams((list) => [...list, { id, x1, y1, x2, y2 }]);
    const t = window.setTimeout(() => {
      setBeams((list) => list.filter((b) => b.id !== id));
    }, BEAM_MS);
    return () => window.clearTimeout(t);
  }, [pointer]);

  const active = connectionState === 'live';
  const stateClass = active ? `glow-${botState}` : 'glow-offline';

  return (
    <>
      <div className={`ambient-glow ${stateClass}`} aria-hidden />
      {beams.length > 0 && (
        <svg className="ambient-beam-layer" aria-hidden>
          {beams.map((b) => (
            <line
              key={b.id}
              x1={b.x1}
              y1={b.y1}
              x2={b.x2}
              y2={b.y2}
              className="ambient-beam"
            />
          ))}
        </svg>
      )}
      <style>{`
        .ambient-glow {
          position: fixed;
          inset: 0;
          z-index: 90;
          pointer-events: none;
          transition: box-shadow 0.6s ease, opacity 0.6s ease, filter 0.6s ease;
        }
        .ambient-beam-layer {
          position: fixed;
          inset: 0;
          width: 100vw;
          height: 100vh;
          z-index: 91;
          pointer-events: none;
        }
        .ambient-beam {
          stroke: #9A3324;
          stroke-width: 2.5;
          stroke-linecap: round;
          filter: drop-shadow(0 0 7px #9A332488);
          stroke-dasharray: 10 8;
          animation: legal-beam-travel ${BEAM_MS}ms ease-out forwards;
        }
        @keyframes legal-beam-travel {
          0%   { opacity: 0; stroke-dashoffset: 60; }
          15%  { opacity: 1; }
          75%  { opacity: 0.9; stroke-dashoffset: 0; }
          100% { opacity: 0; stroke-dashoffset: 0; }
        }

        .glow-offline {
          box-shadow: inset 0 0 0 1px #E4E1DB;
          opacity: 0.6;
        }
        .glow-idle {
          box-shadow: inset 0 0 0 3px #9A332477, inset 0 0 90px 6px #9A332426;
          animation: legal-glow-idle 5.5s ease-in-out infinite;
        }
        .glow-listening {
          box-shadow: inset 0 0 0 4px #9A3324b0, inset 0 0 130px 10px #9A332440;
          animation: legal-glow-listening 3.2s ease-in-out infinite;
        }
        .glow-thinking {
          box-shadow: inset 0 0 0 4px #B9862Ec0, inset 0 0 150px 12px #B9862E4d;
          animation: legal-glow-thinking 0.9s ease-in-out infinite;
        }
        .glow-speaking {
          box-shadow: inset 0 0 0 5px #9A3324e6, inset 0 0 180px 16px #9A332459;
          animation: legal-glow-speaking 1.1s ease-in-out infinite;
        }

        @keyframes legal-glow-idle {
          0%, 100% { opacity: 0.55; }
          50%      { opacity: 0.9; }
        }
        @keyframes legal-glow-listening {
          0%, 100% { opacity: 0.85; }
          50%      { opacity: 1; }
        }
        @keyframes legal-glow-thinking {
          0%   { opacity: 0.7; box-shadow: inset 0 0 0 4px #B9862Ec0, inset 0 0 120px 8px #B9862E4d; }
          50%  { opacity: 1;   box-shadow: inset 0 0 0 5px #B9862Ee0, inset 0 0 170px 16px #B9862E66; }
          100% { opacity: 0.7; box-shadow: inset 0 0 0 4px #B9862Ec0, inset 0 0 120px 8px #B9862E4d; }
        }
        @keyframes legal-glow-speaking {
          0%, 100% { opacity: 0.8; }
          50%      { opacity: 1; }
        }

        @media (prefers-reduced-motion: reduce) {
          .ambient-glow { animation: none !important; opacity: 0.6 !important; }
          .ambient-beam { animation: none !important; opacity: 0.5 !important; stroke-dasharray: none; }
        }
      `}</style>
    </>
  );
}
