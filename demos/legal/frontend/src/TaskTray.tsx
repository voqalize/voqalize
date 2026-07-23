/**
 * Docked activity rail — the "several angles at once" surface. One spoken
 * turn can spawn multiple diligence rows here; each animates
 * queued -> running -> done on its own timeline (client-side pacing only —
 * the model already generated every outcome up front, paced against a
 * per-kind duration long enough to read as real work) so several visibly run
 * concurrently while the lawyer keeps reading. Rows are sorted done-first —
 * a finished result is the payoff and should surface above still-running
 * busywork, not sit buried under it — with a one-line "N done / N running"
 * summary above the list. A done row auto-expands to reveal its typed
 * outcome (finding / precedent / benchmark / exposure); a running row shows
 * elapsed time + a progress bar against its expected duration. The same rail
 * also carries approval routing cards and the end-of-session summary — all
 * ambient "things happening off to the side" surfaces, not modal
 * interruptions.
 */

import { useEffect, useRef, useState } from 'react';
import {
  Circle,
  Loader2,
  Check,
  Scale,
  BarChart3,
  TrendingDown,
  ChevronDown,
  FolderSearch,
  Gavel,
  FileText,
} from 'lucide-react';
import {
  useLegal,
  type Approval,
  type FindingFlag,
  type TaskCard,
  type TaskKind,
  type TaskStatus,
} from './store';

const STATUS_ICON: Record<TaskStatus, typeof Circle> = {
  queued: Circle,
  running: Loader2,
  done: Check,
};

const KIND_LABEL: Record<TaskKind, string> = {
  finding: 'Finding',
  precedent: 'Precedent',
  benchmark: 'Benchmark',
  exposure: 'Exposure',
  search: 'Data room',
  research: 'Research',
  memo: 'Memo',
};

const KIND_ICON: Record<TaskKind, typeof Scale> = {
  finding: Circle,
  precedent: Scale,
  benchmark: BarChart3,
  exposure: TrendingDown,
  search: FolderSearch,
  research: Gavel,
  memo: FileText,
};

const FLAG_COLOR: Record<FindingFlag, string> = {
  ok: '#6B8F5C',
  warn: '#B9862E',
  risk: '#9A3324',
};

function currency(n: number): string {
  if (!n) return '';
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
}

function Outcome({ task }: { task: TaskCard }) {
  switch (task.kind) {
    case 'finding':
      return (
        <div className="tray-outcome">
          {task.findingFlag && (
            <span className="tray-flag" style={{ color: FLAG_COLOR[task.findingFlag] }}>
              {task.findingFlag.toUpperCase()}
            </span>
          )}
          <span className="tray-outcome-text">{task.findingValue ?? task.summary}</span>
        </div>
      );
    case 'precedent':
      return (
        <div className="tray-outcome">
          {task.precedentDeal && <div className="tray-outcome-strong">{task.precedentDeal}</div>}
          <span className="tray-outcome-text">{task.precedentResolution ?? task.summary}</span>
        </div>
      );
    case 'benchmark':
      return (
        <div className="tray-outcome">
          {task.benchmarkPercentile && (
            <span className="tray-outcome-strong">{task.benchmarkPercentile}</span>
          )}
          <span className="tray-outcome-text">{task.benchmarkNote ?? task.summary}</span>
        </div>
      );
    case 'exposure':
      return (
        <div className="tray-outcome tray-outcome-stats">
          {(task.exposureCap || task.exposureEstimate) && (
            <div className="tray-stat-row">
              {task.exposureCap && (
                <div className="tray-stat">
                  <span className="tray-stat-label">Cap</span>
                  <span className="tray-stat-value">{task.exposureCap}</span>
                </div>
              )}
              {task.exposureEstimate && (
                <div className="tray-stat">
                  <span className="tray-stat-label">Real exposure</span>
                  <span className="tray-stat-value tray-stat-value-risk">{task.exposureEstimate}</span>
                </div>
              )}
            </div>
          )}
          <span className="tray-outcome-text">{task.exposureGap ?? task.summary}</span>
        </div>
      );
    case 'search':
      return (
        <div className="tray-outcome">
          {task.searchScope && <div className="tray-outcome-strong">{task.searchScope}</div>}
          <span className="tray-outcome-text">{task.searchExcerpt ?? task.summary}</span>
        </div>
      );
    case 'research':
      return (
        <div className="tray-outcome">
          {task.researchFlag && (
            <span className="tray-flag" style={{ color: FLAG_COLOR[task.researchFlag] }}>
              {task.researchFlag.toUpperCase()}
            </span>
          )}
          <span className="tray-outcome-text">{task.researchFinding ?? task.summary}</span>
          {task.researchSource && <div className="tray-outcome-source">{task.researchSource}</div>}
        </div>
      );
    case 'memo':
      return (
        <div className="tray-outcome">
          <span className="tray-outcome-text">{task.memoBody ?? task.summary}</span>
        </div>
      );
    default:
      return null;
  }
}

// Ticks while a job is running so the row can show "8s" elapsed and drive a
// progress bar against the job's known duration — without this, a realistic
// 15-25s job just looks frozen on a spinner with no sense of how far along it is.
function useElapsed(active: boolean): number {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef<number | null>(null);
  useEffect(() => {
    if (!active) {
      startRef.current = null;
      return;
    }
    startRef.current = Date.now();
    setElapsed(0);
    const id = window.setInterval(() => {
      setElapsed(Date.now() - (startRef.current ?? Date.now()));
    }, 250);
    return () => window.clearInterval(id);
  }, [active]);
  return elapsed;
}

function Row({ task }: { task: TaskCard }) {
  const [expanded, setExpanded] = useState(false);
  const StatusIcon = STATUS_ICON[task.status];
  const KindIcon = KIND_ICON[task.kind];
  const canExpand = task.status === 'done';
  const elapsed = useElapsed(task.status === 'running');
  const progress = task.status === 'running' ? Math.min(96, (elapsed / task.durationMs) * 100) : 0;
  // Auto-reveal the typed outcome the moment a job finishes — this is a
  // hands-free ambient demo, so the payoff (esp. the exposure Cap-vs-real
  // stat) must appear without a mouse click. Still collapsible by hand.
  useEffect(() => {
    if (task.status === 'done') setExpanded(true);
  }, [task.status]);
  return (
    <div className={`tray-row tray-row-${task.status}`}>
      <button
        type="button"
        className="tray-row-main"
        onClick={() => canExpand && setExpanded((v) => !v)}
        disabled={!canExpand}
      >
        <StatusIcon size={12} className={`tray-icon tray-icon-${task.status}`} />
        <span className="tray-row-label">{task.label}</span>
        {task.status === 'running' && (
          <span className="tray-row-elapsed">{Math.round(elapsed / 1000)}s</span>
        )}
        {task.status !== 'done' && task.detail && <span className="tray-row-detail">{task.detail}</span>}
        {task.status === 'done' && !expanded && (
          <span className="tray-row-result">{task.summary}</span>
        )}
        {canExpand && (
          <span className="tray-kind-badge">
            <KindIcon size={9} />
            {KIND_LABEL[task.kind]}
          </span>
        )}
        {canExpand && (
          <ChevronDown size={11} className={`tray-chevron ${expanded ? 'is-open' : ''}`} />
        )}
      </button>
      {task.status === 'running' && (
        <div className="tray-progress-track">
          <div className="tray-progress-fill" style={{ width: `${progress}%` }} />
        </div>
      )}
      {expanded && <Outcome task={task} />}
    </div>
  );
}

function ApprovalRow({ approval }: { approval: Approval }) {
  const { setApprovalStatus } = useLegal();
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="tray-approval">
      <button type="button" className="tray-approval-head" onClick={() => setExpanded((v) => !v)}>
        <span className="tray-approval-title">{approval.title}</span>
        {approval.amount > 0 && <span className="tray-approval-amount">{currency(approval.amount)}</span>}
        <ChevronDown size={11} className={`tray-chevron ${expanded ? 'is-open' : ''}`} />
      </button>
      <div className="tray-approval-summary">{approval.summary}</div>
      {expanded && (
        <div className="tray-approval-body">
          {approval.lines.length > 0 && (
            <ul className="tray-approval-lines">
              {approval.lines.map((l, i) => (
                <li key={i}>{l}</li>
              ))}
            </ul>
          )}
          <div className="tray-approval-rec">{approval.recommendation}</div>
        </div>
      )}
      <div className="tray-approval-foot">
        <span className="tray-approval-routed">Routed to {approval.routedTo}</span>
        {approval.status === 'pending' ? (
          <span className="tray-approval-actions">
            <button type="button" onClick={() => setApprovalStatus(approval.id, 'approved')}>
              Approve
            </button>
            <button type="button" onClick={() => setApprovalStatus(approval.id, 'declined')}>
              Decline
            </button>
          </span>
        ) : (
          <span className={`tray-approval-status is-${approval.status}`}>
            {approval.status === 'approved' ? 'Approved' : 'Declined'}
          </span>
        )}
      </div>
    </div>
  );
}

function SessionSummaryCard() {
  const { sessionSummary } = useLegal();
  if (!sessionSummary) return null;
  return (
    <div className="tray-summary">
      <div className="tray-summary-headline">{sessionSummary.headline}</div>
      {sessionSummary.highlights.length > 0 && (
        <ul className="tray-summary-list">
          {sessionSummary.highlights.map((h, i) => (
            <li key={i}>{h}</li>
          ))}
        </ul>
      )}
      {sessionSummary.openItems.length > 0 && (
        <>
          <div className="tray-summary-sub">Still open</div>
          <ul className="tray-summary-list tray-summary-open">
            {sessionSummary.openItems.map((h, i) => (
              <li key={i}>{h}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

// Results first, busywork last: a done job is the payoff and should surface
// above still-running rows, not get buried under them just because it
// started earlier. Recency breaks ties within each status band.
const STATUS_RANK: Record<TaskStatus, number> = { done: 0, running: 1, queued: 2 };

function TaskSummary({ tasks }: { tasks: TaskCard[] }) {
  const done = tasks.filter((t) => t.status === 'done').length;
  const running = tasks.filter((t) => t.status === 'running').length;
  const queued = tasks.filter((t) => t.status === 'queued').length;
  if (!tasks.length) return null;
  const parts: string[] = [];
  if (done) parts.push(`${done} done`);
  if (running) parts.push(`${running} running`);
  if (queued) parts.push(`${queued} queued`);
  return (
    <div className="tray-summary-bar">
      <span>Diligence</span>
      <span className="tray-summary-bar-dot" aria-hidden>
        &middot;
      </span>
      <span>{parts.join(' · ')}</span>
    </div>
  );
}

export function TaskTray() {
  const { tasks, approvals, sessionSummary } = useLegal();
  if (!tasks.length && !approvals.length && !sessionSummary) return null;

  const sortedTasks = tasks
    .slice()
    .reverse()
    .sort((a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status]);

  return (
    <div className="tray-rail">
      <TaskSummary tasks={tasks} />
      {sortedTasks.map((t) => (
        <Row key={t.id} task={t} />
      ))}
      {approvals
        .slice()
        .reverse()
        .map((a) => (
          <ApprovalRow key={a.id} approval={a} />
        ))}
      <SessionSummaryCard />
      <style>{`
        .tray-rail {
          position: fixed;
          top: 66px;
          right: 18px;
          width: 280px;
          max-width: calc(100vw - 32px);
          max-height: calc(100vh - 90px);
          overflow-y: auto;
          z-index: 60;
          display: flex;
          flex-direction: column;
          gap: 4px;
          font-family: 'Inter', system-ui, sans-serif;
        }
        .tray-summary-bar {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 2px 8px 6px;
          font-size: 10.5px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: #8F8B85;
        }
        .tray-summary-bar-dot { color: #CCCAC6; }
        .tray-row {
          border: 1px solid transparent;
          border-radius: 6px;
          animation: legal-row-in 0.3s ease-out;
        }
        .tray-row-done {
          border-color: #E4E1DB;
          background: #FFFFFF;
        }
        @keyframes legal-row-in {
          from { opacity: 0; transform: translateY(-3px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .tray-row-main {
          display: flex;
          align-items: baseline;
          gap: 7px;
          padding: 4px 8px;
          width: 100%;
          background: none;
          border: none;
          text-align: left;
          cursor: default;
          line-height: 1.4;
          font-family: inherit;
        }
        .tray-row-main:disabled { cursor: default; }
        .tray-row:has(.tray-row-main:not(:disabled)) .tray-row-main { cursor: pointer; }
        .tray-row:has(.tray-row-main:not(:disabled)):hover { background: #F2F1F0; }
        .tray-icon {
          flex: none;
          position: relative;
          top: 1px;
        }
        .tray-icon-queued { color: #CCCAC6; }
        .tray-icon-running {
          color: #9A3324;
          animation: legal-icon-spin 0.9s linear infinite;
        }
        .tray-icon-done { color: #6B8F5C; }
        @keyframes legal-icon-spin { to { transform: rotate(360deg); } }
        .tray-row-label {
          font-size: 11.5px;
          font-weight: 600;
          color: #33312C;
          flex: none;
        }
        .tray-row-detail,
        .tray-row-result {
          font-size: 11.5px;
          color: #8F8B85;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          flex: 1 1 auto;
          min-width: 0;
        }
        .tray-row-result { color: #706D66; }
        .tray-row-elapsed {
          flex: none;
          font-size: 10px;
          font-variant-numeric: tabular-nums;
          color: #AFA9A0;
        }
        .tray-progress-track {
          margin: -2px 8px 6px 27px;
          height: 2px;
          border-radius: 1px;
          background: #EDEBE7;
          overflow: hidden;
        }
        .tray-progress-fill {
          height: 100%;
          background: #9A3324;
          border-radius: 1px;
          transition: width 0.25s linear;
        }
        .tray-kind-badge {
          flex: none;
          display: inline-flex;
          align-items: center;
          gap: 3px;
          font-size: 9px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: #8F8B85;
          margin-left: auto;
        }
        .tray-chevron { flex: none; color: #AFA9A0; transition: transform 0.15s ease; }
        .tray-chevron.is-open { transform: rotate(180deg); }

        .tray-outcome {
          margin: -2px 8px 6px 27px;
          padding: 6px 9px;
          border-left: 2px solid #E4E1DB;
          font-size: 11.5px;
          line-height: 1.5;
          color: #706D66;
        }
        .tray-flag {
          font-size: 9.5px;
          font-weight: 700;
          letter-spacing: 0.04em;
          margin-right: 6px;
        }
        .tray-outcome-strong {
          font-weight: 600;
          color: #33312C;
          margin-bottom: 2px;
        }
        .tray-outcome-text { color: #706D66; }
        .tray-outcome-source {
          margin-top: 4px;
          font-size: 10px;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: #AFA9A0;
        }
        .tray-stat-row {
          display: flex;
          gap: 18px;
          margin-bottom: 6px;
        }
        .tray-stat { display: flex; flex-direction: column; }
        .tray-stat-label {
          font-size: 9.5px;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: #AFA9A0;
        }
        .tray-stat-value {
          font-size: 13px;
          font-weight: 700;
          color: #33312C;
          font-variant-numeric: tabular-nums;
        }
        .tray-stat-value-risk { color: #9A3324; }

        .tray-approval {
          border: 1px solid #E4E1DB;
          border-radius: 8px;
          background: #FFFFFF;
          padding: 8px 10px;
          animation: legal-row-in 0.3s ease-out;
        }
        .tray-approval-head {
          display: flex;
          align-items: center;
          gap: 8px;
          width: 100%;
          background: none;
          border: none;
          padding: 0;
          cursor: pointer;
          font-family: inherit;
        }
        .tray-approval-title {
          font-size: 12px;
          font-weight: 600;
          color: #33312C;
          flex: 1 1 auto;
          text-align: left;
        }
        .tray-approval-amount {
          font-size: 12px;
          font-weight: 700;
          color: #9A3324;
          font-variant-numeric: tabular-nums;
        }
        .tray-approval-summary {
          font-size: 11px;
          color: #8F8B85;
          margin-top: 3px;
        }
        .tray-approval-body { margin-top: 6px; }
        .tray-approval-lines {
          margin: 0 0 6px;
          padding-left: 15px;
          font-size: 11px;
          color: #706D66;
          line-height: 1.55;
        }
        .tray-approval-rec {
          font-size: 11px;
          font-style: italic;
          color: #706D66;
        }
        .tray-approval-foot {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-top: 8px;
          padding-top: 8px;
          border-top: 1px solid #F2F1F0;
        }
        .tray-approval-routed {
          font-size: 10px;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: #AFA9A0;
        }
        .tray-approval-actions { display: flex; gap: 6px; }
        .tray-approval-actions button {
          font-size: 10.5px;
          font-weight: 600;
          padding: 3px 9px;
          border-radius: 5px;
          border: 1px solid #CCCAC6;
          background: #FAFAF9;
          color: #33312C;
          cursor: pointer;
        }
        .tray-approval-actions button:first-child {
          border-color: #9A3324;
          background: #9A3324;
          color: #FAFAF9;
        }
        .tray-approval-status {
          font-size: 10.5px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.03em;
        }
        .tray-approval-status.is-approved { color: #6B8F5C; }
        .tray-approval-status.is-declined { color: #AFA9A0; }

        .tray-summary {
          border: 1px solid #E4E1DB;
          border-radius: 8px;
          background: #F2F1F0;
          padding: 10px 12px;
          animation: legal-row-in 0.3s ease-out;
        }
        .tray-summary-headline {
          font-family: 'Source Serif 4', Georgia, serif;
          font-size: 13px;
          font-weight: 600;
          color: #0F0E0D;
        }
        .tray-summary-list {
          margin: 6px 0 0;
          padding-left: 15px;
          font-size: 11px;
          color: #706D66;
          line-height: 1.55;
        }
        .tray-summary-sub {
          font-size: 9.5px;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: #AFA9A0;
          margin-top: 8px;
        }
        .tray-summary-open { color: #9A3324; }
      `}</style>
    </div>
  );
}
