/**
 * The MSA document surface for the Docket demo.
 *
 * Renders the contract as numbered sections. An IntersectionObserver tracks
 * which clause sits in a band near the vertical center of the viewport — that
 * is the lawyer's "reading position" — and debounce-sends `clause_focus` to
 * the assistant. Comment bubbles and redline diffs render inline, anchored to
 * their clause. When the assistant calls `point_to_clause`, this smoothly
 * scrolls to it and fires a brief highlight + a "beam" cue that `AmbientPresence`
 * picks up (via the clause's DOM rect) to animate a light thread from the
 * screen border to the clause.
 */

import { useEffect, useMemo, useRef } from 'react';
import { useLegal } from './store';
import { MATTER } from './content';

const FOCUS_DEBOUNCE_MS = 500;
const HIGHLIGHT_MS = 2200;

export function DocumentViewer() {
  const { clauses, comments, redlines, insertions, pointer, setFocusedClause, sendClauseFocus } =
    useLegal();
  const clauseRefs = useRef<Map<string, HTMLElement>>(new Map());
  const focusDebounceRef = useRef<number | null>(null);
  const highlightTimerRef = useRef<number | null>(null);

  const commentsByClause = useMemo(() => {
    const m = new Map<string, typeof comments>();
    for (const c of comments) m.set(c.clauseId, [...(m.get(c.clauseId) ?? []), c]);
    return m;
  }, [comments]);

  const redlinesByClause = useMemo(() => {
    const m = new Map<string, typeof redlines>();
    for (const r of redlines) m.set(r.clauseId, [...(m.get(r.clauseId) ?? []), r]);
    return m;
  }, [redlines]);

  const insertionsByClause = useMemo(() => {
    const m = new Map<string, typeof insertions>();
    for (const ins of insertions) m.set(ins.afterClauseId, [...(m.get(ins.afterClauseId) ?? []), ins]);
    return m;
  }, [insertions]);

  // ── reading-position tracking ─────────────────────────────────────────────
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const hit = entries.find((e) => e.isIntersecting);
        if (!hit) return;
        const id = hit.target.getAttribute('data-clause-id');
        if (!id) return;
        setFocusedClause(id);
        if (focusDebounceRef.current) window.clearTimeout(focusDebounceRef.current);
        focusDebounceRef.current = window.setTimeout(() => sendClauseFocus(id), FOCUS_DEBOUNCE_MS);
      },
      // A thin band near the vertical center — whichever clause crosses it is
      // "what the lawyer is reading right now".
      { rootMargin: '-45% 0px -45% 0px', threshold: 0 },
    );
    clauseRefs.current.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── assistant-driven scroll + highlight ───────────────────────────────────
  useEffect(() => {
    if (!pointer) return;
    const el = clauseRefs.current.get(pointer.clauseId);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.setAttribute('data-pointed', 'true');
    if (highlightTimerRef.current) window.clearTimeout(highlightTimerRef.current);
    highlightTimerRef.current = window.setTimeout(() => {
      el.removeAttribute('data-pointed');
    }, HIGHLIGHT_MS);
  }, [pointer]);

  return (
    <div className="doc-scroll">
      <div className="doc-page">
        <div className="doc-header">
          <div className="doc-eyebrow">{MATTER.documentTitle}</div>
          <div className="doc-title">
            {MATTER.client} &amp; {MATTER.counterparty}
          </div>
          <div className="doc-meta">Governing law: {MATTER.governingLaw} &middot; Draft for review</div>
        </div>

        {clauses.map((clause) => (
          <div key={clause.id}>
            <section
              id={`clause-${clause.id}`}
              data-clause-id={clause.id}
              ref={(el) => {
                if (el) clauseRefs.current.set(clause.id, el);
                else clauseRefs.current.delete(clause.id);
              }}
              className="doc-clause"
            >
              <div className="doc-clause-head">
                <span className="doc-clause-num">{clause.number}</span>
                <span className="doc-clause-heading">{clause.heading}</span>
              </div>
              <p className="doc-clause-text">{clause.text}</p>

              {(redlinesByClause.get(clause.id) ?? []).map((r) => (
                <div key={r.id} className="doc-redline">
                  <p className="doc-redline-diff">
                    <span className="doc-redline-old">{r.originalExcerpt}</span>{' '}
                    <span className="doc-redline-new">{r.proposedText}</span>
                  </p>
                  {r.rationale && <div className="doc-redline-rationale">{r.rationale}</div>}
                </div>
              ))}

              {(commentsByClause.get(clause.id) ?? []).map((c) => (
                <div key={c.id} className="doc-comment">
                  <span className="doc-comment-dot" aria-hidden />
                  {c.text}
                </div>
              ))}
            </section>

            {(insertionsByClause.get(clause.id) ?? []).map((ins) => (
              <section key={ins.id} className="doc-clause doc-insertion">
                <div className="doc-clause-head">
                  <span className="doc-insertion-badge">New</span>
                  <span className="doc-clause-heading">{ins.heading}</span>
                </div>
                <p className="doc-clause-text doc-insertion-text">{ins.proposedText}</p>
                {ins.rationale && <div className="doc-redline-rationale">{ins.rationale}</div>}
              </section>
            ))}
          </div>
        ))}
      </div>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap');

        .doc-scroll {
          position: absolute;
          inset: 0;
          overflow-y: auto;
          padding: 48px 0 30vh;
          font-family: 'Inter', system-ui, sans-serif;
        }
        .doc-page {
          max-width: 680px;
          margin: 0 auto;
          padding: 0 40px;
          color: #33312C;
        }
        .doc-header {
          margin-bottom: 40px;
          padding-bottom: 20px;
          border-bottom: 1px solid #E4E1DB;
        }
        .doc-eyebrow {
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: #8F8B85;
        }
        .doc-title {
          font-family: 'Source Serif 4', Georgia, serif;
          font-size: 23px;
          font-weight: 600;
          color: #0F0E0D;
          margin-top: 6px;
        }
        .doc-meta {
          font-size: 12.5px;
          color: #706D66;
          margin-top: 8px;
        }
        .doc-clause {
          margin-bottom: 34px;
          padding: 12px 16px;
          margin-left: -16px;
          margin-right: -16px;
          border-radius: 8px;
          border: 1px solid transparent;
          transition: background 0.5s ease, border-color 0.5s ease;
          scroll-margin-top: 20vh;
        }
        .doc-clause[data-pointed='true'] {
          background: rgba(154, 51, 36, 0.06);
          border-color: rgba(154, 51, 36, 0.28);
        }
        .doc-clause-head {
          display: flex;
          align-items: baseline;
          gap: 10px;
          margin-bottom: 8px;
        }
        .doc-clause-num {
          font-variant-numeric: tabular-nums;
          color: #AFA9A0;
          font-size: 13px;
          font-weight: 600;
        }
        .doc-clause-heading {
          font-family: 'Source Serif 4', Georgia, serif;
          font-size: 15px;
          font-weight: 600;
          color: #0F0E0D;
        }
        .doc-clause-text {
          font-size: 14px;
          line-height: 1.65;
          color: #33312C;
          white-space: pre-wrap;
        }
        .doc-redline {
          margin-top: 10px;
          padding: 2px 0 2px 14px;
          border-left: 2px solid #9A3324;
        }
        .doc-redline-diff {
          margin: 0;
          font-size: 14px;
          line-height: 1.65;
        }
        .doc-redline-old {
          color: #A85C50;
          text-decoration: line-through;
          text-decoration-thickness: 1px;
          opacity: 0.75;
        }
        .doc-redline-new {
          color: #9A3324;
          text-decoration: underline;
          text-decoration-thickness: 1px;
          text-underline-offset: 2px;
          font-weight: 500;
        }
        .doc-redline-rationale {
          margin-top: 3px;
          font-size: 11.5px;
          color: #8F8B85;
          font-style: italic;
        }
        .doc-comment {
          margin-top: 8px;
          display: flex;
          gap: 7px;
          align-items: flex-start;
          padding: 6px 0 6px 14px;
          border-left: 2px solid #CCCAC6;
          font-size: 12.5px;
          line-height: 1.5;
          color: #706D66;
        }
        .doc-comment-dot {
          display: none;
        }
        .doc-insertion {
          border-style: dashed;
          border-color: rgba(154, 51, 36, 0.28);
          background: rgba(154, 51, 36, 0.03);
        }
        .doc-insertion-badge {
          font-size: 9.5px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          color: #9A3324;
          background: rgba(154, 51, 36, 0.1);
          border-radius: 4px;
          padding: 2px 6px;
        }
        .doc-insertion-text {
          color: #9A3324;
          text-decoration: underline;
          text-decoration-thickness: 1px;
          text-underline-offset: 2px;
        }
      `}</style>
    </div>
  );
}
