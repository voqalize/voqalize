/**
 * Standing obligations register — deliberately a persistent artifact, not an
 * ephemeral task row. `extract_obligations` walks the whole document once
 * and the lawyer keeps this list for the rest of the session: renewal
 * windows, notice periods, breach-notification deadlines. A quiet tab on the
 * right edge (hidden until there's anything to show) opens a slide-over
 * drawer; nothing about it is in-your-face until the lawyer asks for it.
 */

import { useState } from 'react';
import { CalendarClock, X } from 'lucide-react';
import { useLegal } from './store';
import { CLAUSES_BY_ID } from './content';

export function ObligationsPanel() {
  const { obligations } = useLegal();
  const [open, setOpen] = useState(false);
  if (!obligations.length) return null;

  return (
    <>
      <button type="button" className="ob-tab" onClick={() => setOpen((v) => !v)}>
        <CalendarClock size={13} />
        Obligations
        <span className="ob-tab-count">{obligations.length}</span>
      </button>

      {open && (
        <>
          <div className="ob-scrim" onClick={() => setOpen(false)} />
          <aside className="ob-panel">
            <div className="ob-panel-head">
              <span className="ob-panel-title">Obligations register</span>
              <button type="button" className="ob-panel-close" onClick={() => setOpen(false)}>
                <X size={14} />
              </button>
            </div>
            <div className="ob-panel-list">
              {obligations.map((o) => (
                <div key={o.id} className="ob-item">
                  <span className="ob-item-clause">§{CLAUSES_BY_ID[o.clauseId]?.number ?? '?'}</span>
                  <div className="ob-item-body">
                    <div className="ob-item-label">{o.label}</div>
                    <div className="ob-item-window">{o.window}</div>
                    {o.note && <div className="ob-item-note">{o.note}</div>}
                  </div>
                </div>
              ))}
            </div>
          </aside>
        </>
      )}

      <style>{`
        .ob-tab {
          position: fixed;
          right: 18px;
          bottom: 20px;
          z-index: 61;
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 7px 12px;
          border-radius: 20px;
          border: 1px solid #E4E1DB;
          background: #FFFFFF;
          color: #706D66;
          font-family: 'Inter', system-ui, sans-serif;
          font-size: 11.5px;
          font-weight: 600;
          cursor: pointer;
          box-shadow: 0 2px 10px rgba(15, 14, 13, 0.06);
          transition: color 0.15s ease, border-color 0.15s ease;
        }
        .ob-tab:hover { color: #9A3324; border-color: #9A332466; }
        .ob-tab-count {
          background: #F2F1F0;
          color: #33312C;
          border-radius: 10px;
          padding: 1px 6px;
          font-size: 10.5px;
        }

        .ob-scrim {
          position: fixed;
          inset: 0;
          z-index: 62;
          background: rgba(15, 14, 13, 0.08);
        }
        .ob-panel {
          position: fixed;
          top: 56px;
          right: 0;
          bottom: 0;
          width: 320px;
          max-width: calc(100vw - 24px);
          z-index: 63;
          background: #FAFAF9;
          border-left: 1px solid #E4E1DB;
          box-shadow: -8px 0 24px rgba(15, 14, 13, 0.08);
          display: flex;
          flex-direction: column;
          font-family: 'Inter', system-ui, sans-serif;
          animation: ob-slide-in 0.2s ease-out;
        }
        @keyframes ob-slide-in {
          from { transform: translateX(16px); opacity: 0; }
          to   { transform: translateX(0); opacity: 1; }
        }
        .ob-panel-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 16px 18px;
          border-bottom: 1px solid #E4E1DB;
        }
        .ob-panel-title {
          font-family: 'Source Serif 4', Georgia, serif;
          font-size: 14px;
          font-weight: 600;
          color: #0F0E0D;
        }
        .ob-panel-close {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 24px;
          height: 24px;
          border-radius: 50%;
          border: none;
          background: transparent;
          color: #8F8B85;
          cursor: pointer;
        }
        .ob-panel-close:hover { background: #F2F1F0; color: #33312C; }
        .ob-panel-list {
          overflow-y: auto;
          padding: 10px 12px;
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .ob-item {
          display: flex;
          gap: 10px;
          padding: 10px 8px;
          border-bottom: 1px solid #F2F1F0;
        }
        .ob-item-clause {
          flex: none;
          font-size: 11px;
          font-weight: 700;
          font-variant-numeric: tabular-nums;
          color: #AFA9A0;
          padding-top: 1px;
        }
        .ob-item-label {
          font-size: 12px;
          font-weight: 600;
          color: #33312C;
        }
        .ob-item-window {
          font-size: 12px;
          font-weight: 600;
          color: #9A3324;
          margin-top: 2px;
        }
        .ob-item-note {
          font-size: 11px;
          color: #8F8B85;
          margin-top: 2px;
          line-height: 1.4;
        }
      `}</style>
    </>
  );
}
