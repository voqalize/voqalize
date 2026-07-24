/**
 * The presence signature: a full-viewport ambient border glow that says "Ada is
 * live and aware of the whole studio" — not a docked chat bubble, not a floating
 * mic. It rings all four edges of the app (fixed, inset 0, pointer-events none)
 * so the copilot reads as part of the product's chrome, present across the entire
 * surface, while the admin keeps working the center untouched.
 *
 * Flowforge's own reading of the treatment (distinct from Docket's oxblood desk):
 * the studio's palette is a **violet build-surface with a cyan signal**, so the
 * ring speaks in those two voices — violet when Ada is present/listening/answering,
 * and it **shifts to cyan the moment she's thinking**, echoing the "plain workflows
 * backed by executable rigor" thesis (cyan = the machine computing). State is
 * legible peripherally, by hue and motion, not just opacity:
 *   - idle      — faint violet, slow breathing (connected, quiet)
 *   - listening — steady, brighter violet ring (hearing the admin)
 *   - thinking  — shifts to cyan, quicker pulse (reasoning / compiling the edit)
 *   - speaking  — violet again, widest/brightest pulse (answering + driving screen)
 * `prefers-reduced-motion` collapses everything to a static low-opacity ring.
 */

import { useForge } from './store';

export function AmbientGlow() {
  const { botState, connectionState } = useForge();
  const active = connectionState === 'live';
  const stateClass = active ? `ffglow-${botState}` : 'ffglow-offline';

  return (
    <>
      <div className={`ff-ambient ${stateClass}`} aria-hidden />
      <style>{`
        .ff-ambient {
          position: fixed;
          inset: 0;
          z-index: 60;
          pointer-events: none;
          border-radius: 2px;
          transition: box-shadow 0.6s ease, opacity 0.6s ease;
        }

        /* Connected but not yet in a call: a hairline seam, barely there. */
        .ffglow-offline {
          box-shadow: inset 0 0 0 1px rgba(124, 58, 237, 0.16);
          opacity: 0.5;
        }

        .ffglow-idle {
          box-shadow: inset 0 0 0 2px rgba(124, 58, 237, 0.42),
                      inset 0 0 110px 8px rgba(124, 58, 237, 0.14);
          animation: ff-glow-breathe 7s ease-in-out infinite;
        }
        .ffglow-listening {
          box-shadow: inset 0 0 0 3px rgba(124, 58, 237, 0.72),
                      inset 0 0 150px 12px rgba(124, 58, 237, 0.24);
          animation: ff-glow-listening 4.5s ease-in-out infinite;
        }
        /* Cyan = the signal: Ada is computing the edit. A different hue reads as a
           different mode even at the edge of vision. */
        .ffglow-thinking {
          box-shadow: inset 0 0 0 3px rgba(34, 211, 238, 0.82),
                      inset 0 0 165px 14px rgba(34, 211, 238, 0.28);
          animation: ff-glow-thinking 2.4s ease-in-out infinite;
        }
        .ffglow-speaking {
          box-shadow: inset 0 0 0 4px rgba(124, 58, 237, 0.9),
                      inset 0 0 200px 18px rgba(124, 58, 237, 0.34);
          animation: ff-glow-speaking 3s ease-in-out infinite;
        }

        @keyframes ff-glow-breathe {
          0%, 100% { opacity: 0.6; }
          50%      { opacity: 0.88; }
        }
        @keyframes ff-glow-listening {
          0%, 100% { opacity: 0.86; }
          50%      { opacity: 1; }
        }
        @keyframes ff-glow-thinking {
          0%   { opacity: 0.78;
                 box-shadow: inset 0 0 0 3px rgba(34, 211, 238, 0.78),
                             inset 0 0 140px 11px rgba(34, 211, 238, 0.26); }
          50%  { opacity: 1;
                 box-shadow: inset 0 0 0 4px rgba(34, 211, 238, 0.92),
                             inset 0 0 180px 17px rgba(34, 211, 238, 0.34); }
          100% { opacity: 0.78;
                 box-shadow: inset 0 0 0 3px rgba(34, 211, 238, 0.78),
                             inset 0 0 140px 11px rgba(34, 211, 238, 0.26); }
        }
        @keyframes ff-glow-speaking {
          0%, 100% { opacity: 0.85; }
          50%      { opacity: 1; }
        }

        @media (prefers-reduced-motion: reduce) {
          .ff-ambient { animation: none !important; opacity: 0.6 !important; }
        }
      `}</style>
    </>
  );
}
