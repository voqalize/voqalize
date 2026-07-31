/**
 * The activity feed — Ada thinking out loud in *actions*.
 *
 * A small, ephemeral stack of task rows in the studio's lower-left "console"
 * corner. The instant a spoken request lands (or the admin clicks something),
 * a row lights up `active` — a cyan signal pulse, the studio's "the machine is
 * computing" voice — and settles to a violet `done` check on the op's own beat.
 * A chained edit paints several rows in quick succession, each checking off, so
 * the request is acknowledged and its steps are legible without Ada saying a word.
 *
 * The one bit of state the feed owns itself is the **acknowledgement ghost**: the
 * moment Ada goes `thinking` with nothing yet on the stack, a soft "On it…" row
 * appears so the verbal request never hangs in silence before the first tool call.
 *
 * Presentation-only: it reads `activities` + presence from the store, is
 * `pointer-events: none`, and sits just under the ambient presence ring.
 */

import { useForge } from './store';

export function ActivityFeed() {
  const { activities, botState, connectionState } = useForge();
  const live = connectionState === 'live';
  const hasActive = activities.some((a) => a.status === 'active');
  // Acknowledge the moment she starts reasoning, before the first tool lands.
  const showGhost = live && botState === 'thinking' && !hasActive;

  if (activities.length === 0 && !showGhost) return null;

  return (
    <>
      <div className="ff-activity" aria-live="polite" aria-label="Ada activity">
        {activities.map((a) => (
          <div key={a.id} className={`ff-act ff-act-${a.status}`}>
            <span className="ff-act-node">
              {a.status === 'done' ? <i className="ff-act-check">✓</i> : <i className="ff-act-dot" />}
            </span>
            <span className="ff-act-text">
              <span className="ff-act-label">{a.label}</span>
              {a.detail && <span className="ff-act-detail">{a.detail}</span>}
            </span>
          </div>
        ))}
        {showGhost && (
          <div className="ff-act ff-act-active ff-act-ghost">
            <span className="ff-act-node">
              <i className="ff-act-dot" />
            </span>
            <span className="ff-act-text">
              <span className="ff-act-label">On it…</span>
            </span>
          </div>
        )}
      </div>
      <style>{`
        .ff-activity {
          position: fixed;
          left: 20px;
          bottom: 20px;
          z-index: 55;
          display: flex;
          flex-direction: column;
          gap: 7px;
          max-width: 340px;
          pointer-events: none;
        }

        .ff-act {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 8px 13px 8px 11px;
          background: rgba(17, 22, 43, 0.82);
          border: 1px solid var(--line);
          border-left: 2px solid var(--violet);
          border-radius: 10px;
          backdrop-filter: blur(10px);
          box-shadow: 0 8px 24px rgba(0, 0, 0, 0.38);
          animation: ff-act-in 0.34s cubic-bezier(0.2, 0.8, 0.2, 1) both;
          transition: opacity 0.5s ease, border-color 0.4s ease;
        }
        /* Cyan = the signal: this task is being computed right now. */
        .ff-act-active { border-left-color: var(--cyan); }
        .ff-act-done { opacity: 0.6; }
        .ff-act-ghost { opacity: 0.9; }

        .ff-act-node {
          position: relative;
          width: 14px;
          height: 14px;
          flex: none;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .ff-act-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: var(--cyan);
          box-shadow: 0 0 9px rgba(34, 211, 238, 0.85);
          animation: ff-act-pulse 1.15s ease-in-out infinite;
        }
        .ff-act-check {
          width: 14px;
          height: 14px;
          border-radius: 50%;
          background: var(--violet);
          color: #f5f3ff;
          font-size: 9px;
          font-weight: 700;
          line-height: 14px;
          text-align: center;
          font-style: normal;
        }

        .ff-act-text {
          min-width: 0;
          display: flex;
          flex-direction: column;
          line-height: 1.25;
        }
        .ff-act-label {
          font-family: var(--mono);
          font-size: 11.5px;
          letter-spacing: 0.01em;
          color: var(--ink);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .ff-act-done .ff-act-label { color: var(--dim); }
        .ff-act-ghost .ff-act-label { color: var(--dim); }
        .ff-act-detail {
          font-family: var(--sans);
          font-size: 11px;
          color: var(--dim);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          max-width: 300px;
        }

        @keyframes ff-act-in {
          from { opacity: 0; transform: translateY(7px) scale(0.98); }
          to   { opacity: 1; transform: none; }
        }
        @keyframes ff-act-pulse {
          0%, 100% { transform: scale(0.7); opacity: 0.7; }
          50%      { transform: scale(1);   opacity: 1; }
        }

        /* On a phone the feed spans the bottom gutter rather than a 340px column. */
        @media (max-width: 640px) {
          .ff-activity {
            left: 12px;
            right: 12px;
            bottom: 12px;
            max-width: none;
          }
          .ff-act-detail { max-width: none; }
        }

        @media (prefers-reduced-motion: reduce) {
          .ff-act { animation: none; }
          .ff-act-dot { animation: none; }
        }
      `}</style>
    </>
  );
}
