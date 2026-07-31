/**
 * Meridian Servicing Console — the UI.
 *
 * A self-contained teal "Blueprint" enterprise dashboard (scoped `svc-*` styles,
 * isolated from the console's own theme). Three surfaces carry the pitch:
 *   - the top-bar ASSISTANT TRAY — cases the assistant is preparing in the
 *     background tick to completion here while the advisor works elsewhere;
 *   - the Jira-style BOARD — cases as tickets across stage columns, routable to
 *     people and departments;
 *   - the CASE view — with the "Needs your approval" maker-checker queue.
 */

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useServicing } from './store';
import {
  CASE_TYPE_LABEL,
  PRIORITY_LABEL,
  STAGE_LABEL,
  STAGE_ORDER,
  currency,
  type Approval,
  type Blocker,
  type Case,
  type CaseTab,
  type Comment,
  type Packet,
  type Priority,
  type Stage,
} from './types';

// ── small presentational helpers ──────────────────────────────────────────────
const PRIORITY_CLASS: Record<Priority, string> = {
  low: 'svc-pri-low',
  normal: 'svc-pri-normal',
  high: 'svc-pri-high',
  urgent: 'svc-pri-urgent',
};

const TYPE_ABBR: Record<string, string> = {
  rate_change: 'RC',
  early_closure: 'CL',
  document_request: 'DOC',
  payment_dispute: 'PD',
  hardship: 'PR',
  insurance_update: 'INS',
};

const APPROVAL_ICON: Record<string, string> = {
  settlement_letter: '◇',
  fee_waiver: '％',
  rate_offer: '↓',
  document_release: '⎙',
  escrow_change: '≈',
  other: '◦',
};

function Avatar({ label, kind }: { label: string; kind?: 'person' | 'department' }) {
  const initials =
    kind === 'department'
      ? label.slice(0, 2).toUpperCase()
      : label
          .split(' ')
          .map((p) => p[0])
          .slice(0, 2)
          .join('')
          .toUpperCase();
  return (
    <span className={`svc-avatar ${kind === 'department' ? 'svc-avatar-dept' : ''}`} title={label}>
      {initials}
    </span>
  );
}

function PriorityDot({ p }: { p: Priority }) {
  return <span className={`svc-pri-dot ${PRIORITY_CLASS[p]}`} title={PRIORITY_LABEL[p]} />;
}

// ── top bar ───────────────────────────────────────────────────────────────────
// `presence` is the voice layer's one control, handed up from `ServicingDesk` so
// the desk reads as part of Meridian's own chrome rather than a bolted-on widget.
function TopBar({ presence }: { presence?: ReactNode }) {
  const { advisor, view, active, openBoard } = useServicing();
  return (
    <header className="svc-topbar">
      <div className="svc-brand" onClick={openBoard} role="button">
        <span className="svc-brand-mark">M</span>
        <div className="svc-brand-text">
          <strong>Meridian</strong>
          <span>Servicing Console</span>
        </div>
      </div>

      <nav className="svc-crumbs">
        <button className="svc-crumb" onClick={openBoard}>
          Cases
        </button>
        {view === 'case' && active && (
          <>
            <span className="svc-crumb-sep">/</span>
            <span className="svc-crumb svc-crumb-active">{active.ref}</span>
          </>
        )}
      </nav>

      <div className="svc-topbar-search" aria-hidden>
        <span>⌕</span> Search cases, customers, loans…
      </div>

      <AssistantTray />

      <div className="svc-advisor">
        <div className="svc-advisor-text">
          <strong>{advisor.name}</strong>
          <span>{advisor.role}</span>
        </div>
        <Avatar label={advisor.name} />
      </div>

      {presence && (
        <>
          <span className="svc-topbar-div" aria-hidden />
          {presence}
        </>
      )}
    </header>
  );
}

/**
 * The assistant task tray — the headline surface. The cases the assistant is
 * preparing in the BACKGROUND show their live job progress here while the advisor
 * works elsewhere on screen; finished prep surfaces as "needs approval".
 */
function AssistantTray() {
  const { preparing, pendingApprovals, openCase } = useServicing();
  const [open, setOpen] = useState(false);
  const activeCount = preparing.length;

  // Auto-open the tray when the assistant starts working a case in the background,
  // so the "it keeps moving while you work elsewhere" moment is visible.
  const prevCount = useRef(0);
  useEffect(() => {
    if (activeCount > prevCount.current) setOpen(true);
    prevCount.current = activeCount;
  }, [activeCount]);

  return (
    <div className="svc-tray">
      <button
        className={`svc-tray-btn ${activeCount ? 'svc-tray-btn-active' : ''}`}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="svc-tray-spark" aria-hidden>
          {activeCount ? <span className="svc-tray-pulse" /> : '✦'}
        </span>
        Assistant
        {activeCount > 0 && <span className="svc-tray-count">{activeCount} working</span>}
        {pendingApprovals > 0 && (
          <span className="svc-tray-approve">{pendingApprovals} to approve</span>
        )}
      </button>

      {open && (
        <div className="svc-tray-pop">
          <div className="svc-tray-pop-head">
            <span>Servicing desk · working for you</span>
            <button onClick={() => setOpen(false)}>✕</button>
          </div>

          {activeCount === 0 && pendingApprovals === 0 && (
            <div className="svc-tray-empty">
              Nothing running. Ask the desk to get a case ready while you work another.
            </div>
          )}

          {preparing.map((c) => (
            <button key={c.id} className="svc-tray-row" onClick={() => openCase(c.ref)}>
              <div className="svc-tray-row-head">
                <span className="svc-mono">{c.ref}</span>
                <span className="svc-tray-row-name">{c.customer.name}</span>
                <span className="svc-tray-row-badge">preparing</span>
              </div>
              <div className="svc-tray-jobs">
                {c.jobs.map((j) => (
                  <div key={j.id} className={`svc-tray-job svc-job-${j.status}`}>
                    <span className="svc-job-tick">
                      {j.status === 'done' ? '✓' : j.status === 'running' ? '' : '○'}
                    </span>
                    <span className="svc-job-label">{j.label}</span>
                  </div>
                ))}
              </div>
            </button>
          ))}

          {pendingApprovals > 0 && (
            <div className="svc-tray-foot">
              <span className="svc-dot-orange" /> {pendingApprovals} draft
              {pendingApprovals > 1 ? 's' : ''} waiting for your approval
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── left rail ─────────────────────────────────────────────────────────────────
function LeftRail() {
  const { cases, filter, setFilter, openBoard, view, departments, advisor, needsApprovalCount } =
    useServicing();
  const mine = cases.filter((c) => c.assignee.kind === 'person' && c.assignee.id === advisor.id);
  const deptCount = (id: string) =>
    cases.filter((c) => c.assignee.kind === 'department' && c.assignee.id === id).length;
  // A rail item is "active" only on the board and when its filter is selected.
  const onBoard = view === 'board';
  const isActive = (pred: boolean) => (onBoard && pred ? 'svc-rail-active' : '');
  const go = (f: Parameters<typeof setFilter>[0]) => {
    setFilter(f);
    openBoard();
  };

  return (
    <aside className="svc-rail">
      <div className="svc-rail-group">
        <div className="svc-rail-label">Work</div>
        <button
          className={`svc-rail-item ${isActive(filter.kind === 'mine')}`}
          onClick={() => go({ kind: 'mine' })}
        >
          My queue <span className="svc-rail-num">{mine.length}</span>
        </button>
        <button
          className={`svc-rail-item ${isActive(filter.kind === 'all')}`}
          onClick={() => go({ kind: 'all' })}
        >
          All cases <span className="svc-rail-num">{cases.length}</span>
        </button>
        <button
          className={`svc-rail-item ${isActive(filter.kind === 'needs_approval')}`}
          onClick={() => go({ kind: 'needs_approval' })}
        >
          Needs approval
          {needsApprovalCount > 0 && (
            <span className="svc-rail-num svc-rail-num-orange">{needsApprovalCount}</span>
          )}
        </button>
      </div>

      <div className="svc-rail-group">
        <div className="svc-rail-label">Departments</div>
        {departments.map((d) => (
          <button
            key={d.id}
            className={`svc-rail-item svc-rail-dept ${isActive(
              filter.kind === 'department' && filter.dept === d.id,
            )}`}
            onClick={() => go({ kind: 'department', dept: d.id })}
          >
            {d.label} <span className="svc-rail-num">{deptCount(d.id)}</span>
          </button>
        ))}
      </div>

      <div className="svc-rail-foot">
        <span className="svc-mono">v2026.6</span> · Servicing Ops
      </div>
    </aside>
  );
}

// ── board ─────────────────────────────────────────────────────────────────────
function BoardPage() {
  const { cases, filter, advisor, departments, openCase } = useServicing();
  const visible = cases.filter((c) => {
    switch (filter.kind) {
      case 'mine':
        return c.assignee.kind === 'person' && c.assignee.id === advisor.id;
      case 'needs_approval':
        return c.stage === 'needs_approval' || c.approvals.some((a) => a.status === 'pending');
      case 'department':
        return c.assignee.kind === 'department' && c.assignee.id === filter.dept;
      case 'all':
      default:
        return true;
    }
  });

  const title =
    filter.kind === 'mine'
      ? 'My queue'
      : filter.kind === 'needs_approval'
        ? 'Needs approval'
        : filter.kind === 'department'
          ? (departments.find((d) => d.id === filter.dept)?.label ?? 'Department')
          : 'All cases';

  return (
    <div className="svc-board-wrap">
      <div className="svc-board-head">
        <h1>{title}</h1>
        <span className="svc-board-sub">
          {visible.length} case{visible.length === 1 ? '' : 's'} · mortgage servicing
        </span>
      </div>
      <div className="svc-board">
        {STAGE_ORDER.map((stage) => {
          const col = visible.filter((c) => c.stage === stage);
          return (
            <div key={stage} className="svc-col">
              <div className="svc-col-head">
                <span className={`svc-col-dot svc-stage-${stage}`} />
                {STAGE_LABEL[stage]}
                <span className="svc-col-count">{col.length}</span>
              </div>
              <div className="svc-col-body">
                {col.map((c) => (
                  <CaseCard key={c.id} c={c} onOpen={() => openCase(c.ref)} />
                ))}
                {col.length === 0 && <div className="svc-col-empty">—</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CaseCard({ c, onOpen }: { c: Case; onOpen: () => void }) {
  const pending = c.approvals.filter((a) => a.status === 'pending').length;
  return (
    <button className="svc-card" onClick={onOpen}>
      <div className="svc-card-top">
        <span className="svc-type-badge">{TYPE_ABBR[c.type] ?? '··'}</span>
        <span className="svc-mono svc-card-ref">{c.ref}</span>
        <PriorityDot p={c.priority} />
      </div>
      <div className="svc-card-title">{c.title}</div>
      <div className="svc-card-cust">
        {c.customer.name} · <span className="svc-muted">{c.customer.segment}</span>
      </div>
      <div className="svc-card-foot">
        <Avatar label={c.assignee.label} kind={c.assignee.kind} />
        <div className="svc-card-flags">
          {c.preparing && <span className="svc-flag svc-flag-prep">preparing…</span>}
          {pending > 0 && <span className="svc-flag svc-flag-approve">{pending} to approve</span>}
        </div>
      </div>
    </button>
  );
}

// ── case detail ───────────────────────────────────────────────────────────────
const TABS: { id: CaseTab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'payments', label: 'Payments' },
  { id: 'documents', label: 'Documents' },
  { id: 'activity', label: 'Activity' },
];

function CasePage({ c }: { c: Case }) {
  const { tab, setTab, highlighted, openBoard } = useServicing();

  // highlight: scroll to + flash a section when the assistant calls highlight().
  useEffect(() => {
    if (!highlighted) return;
    const el = document.getElementById(`svc-sec-${highlighted.section}`);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.classList.add('svc-flash');
    const t = setTimeout(() => el.classList.remove('svc-flash'), 1600);
    return () => clearTimeout(t);
  }, [highlighted]);

  const pending = c.approvals.filter((a) => a.status === 'pending').length;

  return (
    <div className="svc-case">
      <div className="svc-case-main">
        <div className="svc-case-head">
          <button className="svc-back" onClick={openBoard}>
            ← Board
          </button>
          <span className="svc-type-badge">{TYPE_ABBR[c.type] ?? '··'}</span>
          <span className="svc-mono svc-case-ref">{c.ref}</span>
          <h1>{c.title}</h1>
          <span className={`svc-stage-pill svc-stage-${c.stage}`}>{STAGE_LABEL[c.stage]}</span>
        </div>

        <div className="svc-case-req" id="svc-sec-summary">
          <span className="svc-req-quote">{c.request}</span>
          <span className="svc-muted">{c.summary}</span>
        </div>

        <div className="svc-tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`svc-tab ${tab === t.id ? 'svc-tab-active' : ''}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
              {t.id === 'overview' && pending > 0 && <span className="svc-tab-badge">{pending}</span>}
            </button>
          ))}
        </div>

        <div className="svc-tab-body">
          {tab === 'overview' && <OverviewTab c={c} />}
          {tab === 'payments' && <PaymentsTab c={c} />}
          {tab === 'documents' && <DocumentsTab c={c} />}
          {tab === 'activity' && <ActivityTab c={c} />}
        </div>
      </div>

      <CaseRail c={c} />
    </div>
  );
}

function OverviewTab({ c }: { c: Case }) {
  const pending = c.approvals.filter((a) => a.status === 'pending' || a.status === 'blocked');
  const resolved = c.approvals.filter((a) => a.status === 'approved' || a.status === 'declined');
  return (
    <>
      {(c.preparing || c.jobs.length > 0) && <PrepPanel c={c} />}

      {(c.findings.length > 0 || c.blocker) && <WorkupPanel c={c} />}

      {c.packet && <PacketPanel c={c} />}

      <section className="svc-panel" id="svc-sec-approvals">
        <div className="svc-panel-head">
          <h2>Needs your approval</h2>
          <span className="svc-panel-sub">
            The desk drafts — you approve. Nothing here is sent until you sign off.
          </span>
        </div>
        {c.approvals.length === 0 ? (
          <div className="svc-empty-line">No drafts yet for this case.</div>
        ) : (
          <div className="svc-approvals">
            {pending.map((a) => (
              <ApprovalCard key={a.id} caseRef={c.ref} a={a} />
            ))}
            {resolved.map((a) => (
              <ApprovalCard key={a.id} caseRef={c.ref} a={a} />
            ))}
          </div>
        )}
      </section>

      <NotesPanel c={c} />

      <section className="svc-panel" id="svc-sec-loan">
        <div className="svc-panel-head">
          <h2>Loan</h2>
        </div>
        <div className="svc-loan-grid">
          <Field label="Product" value={c.customer.product} />
          <Field label="Loan ID" value={c.customer.loanId} mono />
          <Field label="Outstanding balance" value={currency(c.customer.balance)} mono />
          <Field label="Interest rate" value={`${c.customer.rate.toFixed(2)}%`} mono />
          <Field label="Monthly payment" value={currency(c.customer.monthlyPayment)} mono />
          <Field label="Property" value={c.customer.property} />
          <Field label="Customer since" value={c.customer.since} />
          <Field label="Tenure" value={`${c.customer.tenureYears} years`} />
        </div>
      </section>
    </>
  );
}

function PrepPanel({ c }: { c: Case }) {
  return (
    <section className="svc-panel svc-panel-prep">
      <div className="svc-panel-head">
        <h2>
          {c.preparing ? (
            <>
              <span className="svc-tray-pulse" /> Preparing in the background
            </>
          ) : (
            'Background prep'
          )}
        </h2>
        {c.prepSummary && <span className="svc-panel-sub">{c.prepSummary}</span>}
      </div>
      <div className="svc-prep-jobs">
        {c.jobs.map((j) => (
          <div key={j.id} className={`svc-prep-job svc-job-${j.status}`}>
            <span className="svc-job-tick">
              {j.status === 'done' ? '✓' : j.status === 'running' ? '' : '○'}
            </span>
            <span className="svc-prep-job-label">{j.label}</span>
            <span className="svc-prep-job-detail">
              {j.status === 'done' && j.detail ? j.detail : j.status === 'running' ? 'running…' : ''}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

/**
 * The workup — the desk's cross-system assembly + reconciliation, and the
 * blocker it caught. This is the "it did the legwork you'd have done by hand,
 * and found the thing you'd have missed" surface.
 */
function WorkupPanel({ c }: { c: Case }) {
  return (
    <section className="svc-panel svc-panel-workup" id="svc-sec-workup">
      <div className="svc-panel-head">
        <h2>Desk workup</h2>
        <span className="svc-panel-sub">
          What the desk assembled and reconciled across systems for you.
        </span>
      </div>

      {c.blocker && <BlockerCard c={c} b={c.blocker} />}

      {c.findings.length > 0 && (
        <div className="svc-findings">
          {c.findings.map((f) => (
            <div key={f.id} className={`svc-finding svc-finding-${f.flag ?? 'ok'}`}>
              <span className="svc-finding-label">{f.label}</span>
              <span className="svc-finding-value">
                {f.flag === 'warn' && <span className="svc-finding-mark">!</span>}
                {f.value}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function BlockerCard({ c, b }: { c: Case; b: Blocker }) {
  const { assignCase } = useServicing();
  const resolved = b.status === 'resolved';
  return (
    <div className={`svc-blocker svc-blocker-${resolved ? 'resolved' : b.severity}`}>
      <div className="svc-blocker-icon">{resolved ? '✓' : b.severity === 'block' ? '⛔' : '⚠'}</div>
      <div className="svc-blocker-body">
        <div className="svc-blocker-title">
          {resolved ? `Cleared — ${b.title}` : b.title}
          {!resolved && b.severity === 'block' && <span className="svc-blocker-tag">Blocks release</span>}
        </div>
        <div className="svc-blocker-detail">{resolved ? b.resolvedNote || b.detail : b.detail}</div>
        {!resolved && b.suggestedRoute && (
          <div className="svc-blocker-actions">
            <span className="svc-muted">Clear via {b.suggestedRoute}</span>
            <button
              className="svc-btn svc-btn-route"
              onClick={() => assignCase(c.ref, 'department', b.suggestedRoute!)}
            >
              Route to {b.suggestedRoute}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/** The regulated packet (multi-step form) the desk filled — approve-gated submit. */
function PacketPanel({ c }: { c: Case }) {
  const { submitPacket, canSubmitPacket } = useServicing();
  const packet = c.packet as Packet;
  const submitted = packet.status === 'submitted';
  const submitting = packet.status === 'submitting';
  const blockedSection = packet.sections.find((s) => s.status === 'blocked');
  const pendingApprovals = c.approvals.filter((a) => a.status === 'pending').length;
  const canSubmit = canSubmitPacket(c);

  const reason = submitted
    ? null
    : blockedSection
      ? blockedSection.blockedReason || 'A section is blocked.'
      : c.blocker && c.blocker.status === 'open' && c.blocker.severity === 'block'
        ? c.blocker.title
        : c.approvals.some((a) => a.status === 'blocked')
          ? 'A draft is still blocked.'
          : pendingApprovals > 0
            ? `${pendingApprovals} draft${pendingApprovals > 1 ? 's' : ''} still need your approval.`
            : null;

  return (
    <section className="svc-panel svc-panel-packet" id="svc-sec-packet">
      <div className="svc-panel-head">
        <h2>
          {packet.title}
          <span className={`svc-packet-status svc-packet-${packet.status}`}>
            {submitted ? `Submitted${packet.submittedTo ? ` · ${packet.submittedTo}` : ''}` : packet.status}
          </span>
        </h2>
        {packet.summary && <span className="svc-panel-sub">{packet.summary}</span>}
      </div>

      <div className="svc-packet-secs">
        {packet.sections.map((s) => (
          <div key={s.id} className={`svc-packet-sec svc-packet-sec-${s.status}`}>
            <div className="svc-packet-sec-head">
              <span className="svc-packet-sec-title">{s.title}</span>
              {s.status === 'blocked' && <span className="svc-packet-sec-lock">🔒 locked</span>}
            </div>
            <div className="svc-packet-fields">
              {s.fields.map((f, i) => (
                <div key={i} className="svc-field">
                  <span className="svc-field-label">{f.label}</span>
                  <span className={`svc-field-value ${f.mono ? 'svc-mono' : ''}`}>{f.value}</span>
                </div>
              ))}
            </div>
            {s.status === 'blocked' && s.blockedReason && (
              <div className="svc-packet-sec-reason">{s.blockedReason}</div>
            )}
          </div>
        ))}
      </div>

      <div className="svc-packet-foot">
        {submitted ? (
          <span className="svc-packet-done">✓ Submitted to {packet.submittedTo}</span>
        ) : (
          <>
            <button
              className="svc-btn svc-btn-approve"
              disabled={!canSubmit || submitting}
              onClick={() => submitPacket(c.ref)}
            >
              {submitting ? 'Submitting…' : 'Submit packet'}
            </button>
            {reason && <span className="svc-packet-reason">{reason}</span>}
          </>
        )}
      </div>
    </section>
  );
}

function ApprovalCard({ caseRef, a }: { caseRef: string; a: Approval }) {
  const { decideApproval } = useServicing();
  return (
    <div className={`svc-approval svc-approval-${a.status}`}>
      <div className="svc-approval-icon">{APPROVAL_ICON[a.kind] ?? '◦'}</div>
      <div className="svc-approval-body">
        <div className="svc-approval-title">
          {a.title}
          {a.amount != null && <span className="svc-approval-amount">{currency(a.amount)}</span>}
        </div>
        <div className="svc-approval-summary">{a.summary}</div>
        {a.lines.length > 0 && (
          <ul className="svc-approval-lines">
            {a.lines.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        )}
        {a.recommendation && (
          <div className="svc-approval-rec">
            <span>Desk recommends</span> {a.recommendation}
          </div>
        )}
        {a.status === 'pending' ? (
          <div className="svc-approval-actions">
            <button
              className="svc-btn svc-btn-approve"
              onClick={() => decideApproval(caseRef, a.id, 'approved')}
            >
              Approve
            </button>
            <button
              className="svc-btn svc-btn-decline"
              onClick={() => decideApproval(caseRef, a.id, 'declined')}
            >
              Decline
            </button>
          </div>
        ) : a.status === 'blocked' ? (
          <div className="svc-approval-blocked-note">
            🔒 Can't approve yet — {a.blockedReason || 'resolve the flagged issue first.'}
          </div>
        ) : (
          <div className={`svc-approval-status svc-approval-${a.status}`}>
            {a.status === 'approved' ? '✓ Approved by you' : '✕ Declined'}
          </div>
        )}
      </div>
    </div>
  );
}

function timeAgo(ts: number): string {
  if (!ts) return '';
  const s = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (s < 45) return 'just now';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

/**
 * Notes — authored comments on the case. The advisor (or the desk by voice)
 * leaves context here, typically when handing a case to another department; an
 * optional "Route to" tags the note with that department and routes the case.
 */
function NotesPanel({ c }: { c: Case }) {
  const { departments, addComment, assignCase } = useServicing();
  const [text, setText] = useState('');
  const [dept, setDept] = useState('');

  const submit = () => {
    const body = text.trim();
    if (!body) return;
    addComment(c.ref, body, 'advisor', dept || undefined);
    if (dept) assignCase(c.ref, 'department', dept);
    setText('');
    setDept('');
  };

  return (
    <section className="svc-panel" id="svc-sec-notes">
      <div className="svc-panel-head">
        <h2>Notes</h2>
        <span className="svc-panel-sub">
          Capture handoff context — what the next desk needs to know.
        </span>
      </div>

      {c.comments.length > 0 && (
        <div className="svc-notes">
          {[...c.comments].reverse().map((cm: Comment) => (
            <div key={cm.id} className="svc-note">
              <div className="svc-note-head">
                <span className={`svc-note-author svc-note-${cm.authorKind}`}>{cm.author}</span>
                {cm.deptLabel && <span className="svc-note-dept">→ {cm.deptLabel}</span>}
                <span className="svc-note-time">{timeAgo(cm.ts)}</span>
              </div>
              <div className="svc-note-text">{cm.text}</div>
            </div>
          ))}
        </div>
      )}

      <div className="svc-note-compose">
        <textarea
          className="svc-note-input"
          placeholder="Add a note for this case…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit();
          }}
          rows={2}
        />
        <div className="svc-note-compose-foot">
          <select
            className="svc-note-dept-select"
            value={dept}
            onChange={(e) => setDept(e.target.value)}
            title="Optionally route this case to a department"
          >
            <option value="">Route to… (optional)</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.label}
              </option>
            ))}
          </select>
          <button className="svc-btn svc-btn-approve" disabled={!text.trim()} onClick={submit}>
            {dept ? 'Add note & route' : 'Add note'}
          </button>
        </div>
      </div>
    </section>
  );
}

function PaymentsTab({ c }: { c: Case }) {
  return (
    <section className="svc-panel" id="svc-sec-payments">
      <div className="svc-panel-head">
        <h2>Payment history</h2>
      </div>
      {c.payments.length === 0 ? (
        <div className="svc-empty-line">No recent payments on file.</div>
      ) : (
        // Six money columns: on a phone they scroll inside this box rather than
        // pushing the whole console sideways.
        <div className="svc-table-wrap">
        <table className="svc-table">
          <thead>
            <tr>
              <th>Date</th>
              <th className="svc-num">Amount</th>
              <th className="svc-num">Principal</th>
              <th className="svc-num">Interest</th>
              <th className="svc-num">Insurance/Tax</th>
              <th>Note</th>
            </tr>
          </thead>
          <tbody>
            {c.payments.map((p, i) => (
              <tr key={i}>
                <td>{p.date}</td>
                <td className="svc-num svc-mono">{currency(p.amount)}</td>
                <td className="svc-num svc-mono">{currency(p.principal)}</td>
                <td className="svc-num svc-mono">{currency(p.interest)}</td>
                <td className="svc-num svc-mono">{p.escrow ? currency(p.escrow) : '—'}</td>
                <td className="svc-muted">{p.note ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </section>
  );
}

function DocumentsTab({ c }: { c: Case }) {
  return (
    <section className="svc-panel" id="svc-sec-documents">
      <div className="svc-panel-head">
        <h2>Documents held in custody</h2>
      </div>
      {c.documents.length === 0 ? (
        <div className="svc-empty-line">No documents held for this loan.</div>
      ) : (
        <div className="svc-table-wrap">
        <table className="svc-table">
          <thead>
            <tr>
              <th>Document</th>
              <th>Type</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {c.documents.map((d, i) => (
              <tr key={i}>
                <td>{d.name}</td>
                <td className="svc-muted">{d.kind}</td>
                <td>
                  <span className={`svc-doc-status svc-doc-${d.status}`}>{d.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </section>
  );
}

function ActivityTab({ c }: { c: Case }) {
  return (
    <section className="svc-panel" id="svc-sec-activity">
      <div className="svc-panel-head">
        <h2>Activity</h2>
      </div>
      <div className="svc-activity">
        {[...c.activity].reverse().map((e) => (
          <div key={e.id} className="svc-activity-row">
            <span className={`svc-activity-actor svc-actor-${e.actor}`}>
              {e.actor === 'agent' ? 'Desk' : e.actor === 'advisor' ? 'You' : 'System'}
            </span>
            <span className="svc-activity-text">{e.text}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function CaseRail({ c }: { c: Case }) {
  return (
    <aside className="svc-case-rail">
      <div className="svc-rail-card">
        <div className="svc-rail-card-label">Customer</div>
        <div className="svc-rail-cust">
          <Avatar label={c.customer.name} />
          <div>
            <strong>{c.customer.name}</strong>
            <span className="svc-muted">{c.customer.segment}</span>
          </div>
        </div>
      </div>
      <div className="svc-rail-card">
        <Field label="Assignee" value={c.assignee.label} />
        <Field label="Stage" value={STAGE_LABEL[c.stage]} />
        <Field label="Priority" value={PRIORITY_LABEL[c.priority]} />
        <Field label="Type" value={CASE_TYPE_LABEL[c.type]} />
        <Field label="SLA" value={`${c.slaHours}h`} mono />
        <Field label="Opened" value={c.openedDays === 0 ? 'Today' : `${c.openedDays}d ago`} />
      </div>
    </aside>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="svc-field">
      <span className="svc-field-label">{label}</span>
      <span className={`svc-field-value ${mono ? 'svc-mono' : ''}`}>{value}</span>
    </div>
  );
}

/**
 * The server-side precedent search result — institutional memory the desk pulled
 * from the archive (past cases not in the queue). A floating overlay so it reads
 * as "the desk reached beyond the screen", with a real "searching…" beat.
 */
function ArchiveResults() {
  const { archiveSearch, dismissSearch, openCase } = useServicing();
  if (!archiveSearch) return null;
  const searching = archiveSearch.status === 'searching';
  return (
    <div className="svc-archive">
      <div className="svc-archive-head">
        <div>
          <span className="svc-archive-kicker">Archive search</span>
          <span className="svc-archive-query">“{archiveSearch.query}”</span>
        </div>
        <button onClick={dismissSearch} title="Dismiss">
          ✕
        </button>
      </div>
      {searching ? (
        <div className="svc-archive-searching">
          <span className="svc-tray-pulse" /> Searching past cases…
        </div>
      ) : archiveSearch.results.length === 0 ? (
        <div className="svc-archive-empty">No matching precedent found.</div>
      ) : (
        <div className="svc-archive-list">
          {archiveSearch.results.map((r) => (
            <div key={r.ref} className="svc-archive-row">
              <div className="svc-archive-row-head">
                <span className="svc-mono">{r.ref}</span>
                {r.customer && <span className="svc-archive-cust">{r.customer}</span>}
                {r.days != null && <span className="svc-archive-days">{r.days}d</span>}
              </div>
              <div className="svc-archive-summary">{r.summary}</div>
              <div className="svc-archive-res">
                <span>Resolved</span> {r.resolution}
              </div>
            </div>
          ))}
          <button className="svc-archive-foot" onClick={() => openCase(archiveSearch.results[0].ref)}>
            Open {archiveSearch.results[0].ref}
          </button>
        </div>
      )}
    </div>
  );
}

// ── root ──────────────────────────────────────────────────────────────────────
export function ServicingApp({ presence }: { presence?: ReactNode }) {
  const { view, active } = useServicing();
  return (
    <div className="svc-root">
      <ServicingStyles />
      <TopBar presence={presence} />
      <div className="svc-body">
        <LeftRail />
        <main className="svc-main">
          {view === 'case' && active ? <CasePage c={active} /> : <BoardPage />}
        </main>
      </div>
      <ArchiveResults />
    </div>
  );
}

// ── scoped styles (teal "Blueprint" enterprise look) ──────────────────────────
function ServicingStyles() {
  return <style dangerouslySetInnerHTML={{ __html: STYLES }} />;
}

const STYLES = `
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

.svc-root{
  position:absolute; inset:0; display:flex; flex-direction:column;
  font-family:'Archivo',system-ui,sans-serif;
  color:#10211F; background:#EFF4F3;
  background-image:linear-gradient(#0f766e0d 1px,transparent 1px),linear-gradient(90deg,#0f766e0d 1px,transparent 1px);
  background-size:28px 28px;
  --teal:#0F766E; --teal-d:#0B524C; --teal-l:#14B8A6; --teal-bg:#E5F0EE;
  --orange:#EA580C; --orange-l:#FB923C; --orange-bg:#FEEBDD;
  --ink:#10211F; --muted:#5C6F6C; --line:#D3E0DD; --surface:#FFFFFF;
  -webkit-font-smoothing:antialiased; font-size:14px;
}
.svc-mono{ font-family:'JetBrains Mono',monospace; }
.svc-muted{ color:var(--muted); }
.svc-num{ text-align:right; }

/* top bar */
.svc-topbar{ height:54px; flex:0 0 auto; display:flex; align-items:center; gap:18px;
  padding:0 18px; background:var(--teal-d); color:#EAF6F4; box-shadow:0 1px 0 #0000001a; z-index:20; }
.svc-brand{ display:flex; align-items:center; gap:10px; cursor:pointer; }
.svc-brand-mark{ width:30px; height:30px; border-radius:8px; display:grid; place-items:center;
  background:linear-gradient(135deg,var(--teal-l),var(--teal)); color:#04211E; font-weight:700; font-size:17px;
  box-shadow:inset 0 0 0 1px #ffffff22; }
.svc-brand-text{ display:flex; flex-direction:column; line-height:1.05; }
.svc-brand-text strong{ font-size:14.5px; letter-spacing:.2px; }
.svc-brand-text span{ font-size:10.5px; color:#9FD4CD; letter-spacing:.4px; text-transform:uppercase; }
.svc-crumbs{ display:flex; align-items:center; gap:8px; }
.svc-crumb{ background:none; border:none; color:#BFE3DE; font-size:13px; cursor:pointer; font-family:inherit; padding:0; }
.svc-crumb-active{ color:#fff; font-family:'JetBrains Mono',monospace; }
.svc-crumb-sep{ color:#5C8C86; }
.svc-topbar-search{ margin-left:auto; display:flex; align-items:center; gap:8px; font-size:12.5px;
  color:#8FBDB7; background:#0000001f; border:1px solid #ffffff14; border-radius:8px; padding:7px 12px; width:280px; }
.svc-advisor{ display:flex; align-items:center; gap:9px; padding-left:6px; }
.svc-advisor-text{ display:flex; flex-direction:column; line-height:1.15; text-align:right; }
.svc-advisor-text strong{ font-size:12.5px; }
.svc-advisor-text span{ font-size:10.5px; color:#9FD4CD; }
/* hairline before the voice layer's presence control (mounted by ServicingDesk) */
.svc-topbar-div{ width:1px; height:24px; background:#ffffff24; flex:0 0 auto; }

/* avatars */
.svc-avatar{ width:28px; height:28px; border-radius:50%; display:inline-grid; place-items:center;
  background:linear-gradient(135deg,var(--teal-l),var(--teal)); color:#04211E; font-size:10.5px; font-weight:700;
  flex:0 0 auto; box-shadow:inset 0 0 0 1px #ffffff30; }
.svc-avatar-dept{ background:linear-gradient(135deg,var(--orange-l),var(--orange)); color:#3a1402; border-radius:7px; }

/* assistant tray */
.svc-tray{ position:relative; }
.svc-tray-btn{ display:flex; align-items:center; gap:8px; height:34px; padding:0 12px; border-radius:9px;
  border:1px solid #ffffff22; background:#ffffff14; color:#EAF6F4; font-family:inherit; font-size:12.5px; font-weight:600;
  cursor:pointer; }
.svc-tray-btn-active{ background:linear-gradient(135deg,#14b8a6,#0f766e); border-color:#7fe6da; box-shadow:0 0 0 3px #14b8a633; }
.svc-tray-spark{ display:inline-grid; place-items:center; width:14px; }
.svc-tray-pulse{ width:9px; height:9px; border-radius:50%; background:#5EEAD4; box-shadow:0 0 0 0 #5eead4aa;
  animation:svc-pulse 1.4s infinite; display:inline-block; }
@keyframes svc-pulse{ 0%{box-shadow:0 0 0 0 #5eead4aa;} 70%{box-shadow:0 0 0 7px #5eead400;} 100%{box-shadow:0 0 0 0 #5eead400;} }
.svc-tray-count{ background:#04211e55; padding:2px 7px; border-radius:6px; font-size:11px; }
.svc-tray-approve{ background:var(--orange); color:#fff; padding:2px 7px; border-radius:6px; font-size:11px; }
.svc-tray-pop{ position:absolute; top:42px; right:0; width:330px; background:var(--surface); color:var(--ink);
  border:1px solid var(--line); border-radius:12px; box-shadow:0 20px 48px #0b3d3933; overflow:hidden; z-index:40; }
.svc-tray-pop-head{ display:flex; justify-content:space-between; align-items:center; padding:11px 14px;
  background:var(--teal-bg); font-size:12px; font-weight:600; color:var(--teal-d); border-bottom:1px solid var(--line); }
.svc-tray-pop-head button{ background:none; border:none; cursor:pointer; color:var(--muted); font-size:13px; }
.svc-tray-empty{ padding:18px 14px; font-size:12.5px; color:var(--muted); line-height:1.5; }
.svc-tray-row{ display:block; width:100%; text-align:left; padding:11px 14px; border:none; border-bottom:1px solid var(--line);
  background:none; cursor:pointer; font-family:inherit; }
.svc-tray-row:hover{ background:#f3f9f8; }
.svc-tray-row-head{ display:flex; align-items:center; gap:8px; margin-bottom:7px; }
.svc-tray-row-head .svc-mono{ font-size:11px; color:var(--teal); }
.svc-tray-row-name{ font-size:12.5px; font-weight:600; }
.svc-tray-row-badge{ margin-left:auto; font-size:10px; color:var(--teal-d); background:var(--teal-bg);
  padding:2px 6px; border-radius:5px; }
.svc-tray-jobs{ display:flex; flex-direction:column; gap:4px; }
.svc-tray-job{ display:flex; align-items:center; gap:7px; font-size:11.5px; color:var(--muted); }
.svc-tray-foot{ display:flex; align-items:center; gap:7px; padding:11px 14px; font-size:11.5px; color:var(--orange);
  background:var(--orange-bg); }
.svc-dot-orange{ width:7px; height:7px; border-radius:50%; background:var(--orange); display:inline-block; }

/* job ticks (shared by tray + prep panel) */
.svc-job-tick{ width:14px; height:14px; border-radius:50%; display:inline-grid; place-items:center; font-size:9px; flex:0 0 auto; }
.svc-job-queued .svc-job-tick{ color:var(--muted); }
.svc-job-running .svc-job-tick{ border:2px solid var(--teal-l); border-top-color:transparent; animation:svc-spin .7s linear infinite; }
.svc-job-done .svc-job-tick{ background:var(--teal); color:#fff; }
.svc-job-running .svc-job-label,.svc-job-running .svc-prep-job-label{ color:var(--ink); }
.svc-job-done .svc-job-label{ color:var(--ink); }
@keyframes svc-spin{ to{ transform:rotate(360deg); } }

/* body / rail */
.svc-body{ flex:1 1 auto; display:flex; min-height:0; }
.svc-rail{ width:210px; flex:0 0 auto; background:#ffffffcc; border-right:1px solid var(--line);
  padding:14px 10px; display:flex; flex-direction:column; gap:18px; backdrop-filter:blur(2px); }
.svc-rail-group{ display:flex; flex-direction:column; gap:2px; }
.svc-rail-label{ font-size:10px; text-transform:uppercase; letter-spacing:.7px; color:var(--muted); padding:0 8px 6px; }
.svc-rail-item{ display:flex; align-items:center; justify-content:space-between; padding:7px 8px; border-radius:7px;
  background:none; border:none; cursor:pointer; font-family:inherit; font-size:12.5px; color:var(--ink); text-align:left; }
.svc-rail-item:hover{ background:var(--teal-bg); }
.svc-rail-active{ background:var(--teal-bg); color:var(--teal-d); font-weight:600; box-shadow:inset 2px 0 0 var(--teal); }
.svc-rail-dept{ font-size:12px; color:var(--muted); }
.svc-rail-num{ font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--muted); background:#eef4f3; padding:1px 6px; border-radius:5px; }
.svc-rail-num-orange{ background:var(--orange-bg); color:var(--orange); }
.svc-rail-foot{ margin-top:auto; font-size:11px; color:var(--muted); padding:8px; }
.svc-main{ flex:1 1 auto; min-width:0; overflow:auto; }

/* board */
.svc-board-wrap{ padding:20px 22px; }
.svc-board-head{ display:flex; align-items:baseline; gap:12px; margin-bottom:16px; }
.svc-board-head h1{ font-size:19px; font-weight:700; margin:0; }
.svc-board-sub{ font-size:12.5px; color:var(--muted); }
.svc-board{ display:flex; gap:14px; align-items:flex-start; overflow-x:auto; padding-bottom:8px; }
.svc-col{ flex:1 1 0; min-width:222px; background:#ffffff99; border:1px solid var(--line); border-radius:11px; }
.svc-col-head{ display:flex; align-items:center; gap:8px; padding:11px 13px; font-size:12px; font-weight:600;
  color:var(--ink); border-bottom:1px solid var(--line); }
.svc-col-dot{ width:8px; height:8px; border-radius:50%; }
.svc-col-count{ margin-left:auto; font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--muted); }
.svc-col-body{ padding:10px; display:flex; flex-direction:column; gap:9px; min-height:60px; }
.svc-col-empty{ text-align:center; color:#c2d2cf; padding:14px 0; }
.svc-stage-new{ background:#94a3b8; } .svc-col-dot.svc-stage-new{ background:#94a3b8; }
.svc-stage-in_progress{ background:var(--teal-l); } .svc-col-dot.svc-stage-in_progress{ background:var(--teal-l); }
.svc-stage-needs_approval{ background:var(--orange); } .svc-col-dot.svc-stage-needs_approval{ background:var(--orange); }
.svc-stage-with_dept{ background:#8b5cf6; } .svc-col-dot.svc-stage-with_dept{ background:#8b5cf6; }
.svc-stage-done{ background:#10b981; } .svc-col-dot.svc-stage-done{ background:#10b981; }

/* card */
.svc-card{ display:block; width:100%; text-align:left; background:var(--surface); border:1px solid var(--line);
  border-radius:9px; padding:11px; cursor:pointer; font-family:inherit; transition:border-color .12s,box-shadow .12s; }
.svc-card:hover{ border-color:var(--teal-l); box-shadow:0 4px 14px #0f766e1f; }
.svc-card-top{ display:flex; align-items:center; gap:8px; margin-bottom:7px; }
.svc-type-badge{ font-family:'JetBrains Mono',monospace; font-size:9.5px; font-weight:600; color:var(--teal-d);
  background:var(--teal-bg); padding:2px 5px; border-radius:5px; letter-spacing:.3px; }
.svc-card-ref{ font-size:11px; color:var(--muted); }
.svc-pri-dot{ margin-left:auto; width:9px; height:9px; border-radius:50%; }
.svc-pri-low{ background:#cbd5e1; } .svc-pri-normal{ background:var(--teal-l); }
.svc-pri-high{ background:var(--orange-l); } .svc-pri-urgent{ background:#ef4444; }
.svc-card-title{ font-size:13.5px; font-weight:600; margin-bottom:3px; }
.svc-card-cust{ font-size:12px; color:var(--ink); margin-bottom:10px; }
.svc-card-foot{ display:flex; align-items:center; gap:8px; }
.svc-card-flags{ margin-left:auto; display:flex; gap:5px; }
.svc-flag{ font-size:10px; padding:2px 6px; border-radius:5px; }
.svc-flag-prep{ background:var(--teal-bg); color:var(--teal-d); }
.svc-flag-approve{ background:var(--orange-bg); color:var(--orange); font-weight:600; }

/* case detail */
.svc-case{ display:flex; min-height:100%; }
.svc-case-main{ flex:1 1 auto; min-width:0; padding:18px 22px; }
.svc-case-head{ display:flex; align-items:center; gap:10px; margin-bottom:10px; flex-wrap:wrap; }
.svc-back{ background:none; border:1px solid var(--line); border-radius:7px; padding:5px 10px; font-size:12px;
  cursor:pointer; font-family:inherit; color:var(--muted); }
.svc-back:hover{ color:var(--teal-d); border-color:var(--teal-l); }
.svc-case-ref{ font-size:12px; color:var(--muted); }
.svc-case-head h1{ font-size:18px; font-weight:700; margin:0; }
.svc-stage-pill{ font-size:11px; color:#fff; padding:3px 9px; border-radius:6px; }
.svc-case-req{ display:flex; flex-direction:column; gap:5px; background:var(--surface); border:1px solid var(--line);
  border-left:3px solid var(--teal); border-radius:9px; padding:12px 14px; margin-bottom:16px; }
.svc-req-quote{ font-size:14px; font-style:italic; color:var(--ink); }
.svc-case-req .svc-muted{ font-size:12.5px; }
.svc-tabs{ display:flex; gap:4px; border-bottom:1px solid var(--line); margin-bottom:16px; }
.svc-tab{ position:relative; background:none; border:none; padding:9px 13px; font-family:inherit; font-size:13px;
  color:var(--muted); cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-1px; }
.svc-tab-active{ color:var(--teal-d); font-weight:600; border-bottom-color:var(--teal); }
.svc-tab-badge{ margin-left:6px; font-size:10px; background:var(--orange); color:#fff; padding:1px 6px; border-radius:8px; }
.svc-tab-body{ display:flex; flex-direction:column; gap:16px; }

/* panels */
.svc-panel{ background:var(--surface); border:1px solid var(--line); border-radius:11px; padding:16px; }
.svc-panel-prep{ border-color:var(--teal-l); background:linear-gradient(180deg,#f3fbfa,#fff); }
.svc-panel-head{ display:flex; flex-direction:column; gap:2px; margin-bottom:12px; }
.svc-panel-head h2{ font-size:14px; font-weight:700; margin:0; display:flex; align-items:center; gap:8px; }
.svc-panel-sub{ font-size:12px; color:var(--muted); }
.svc-empty-line{ font-size:12.5px; color:var(--muted); padding:6px 0; }

/* prep jobs */
.svc-prep-jobs{ display:flex; flex-direction:column; gap:9px; }
.svc-prep-job{ display:flex; align-items:center; gap:10px; font-size:13px; color:var(--muted); }
.svc-prep-job-label{ flex:0 0 auto; }
.svc-prep-job-detail{ margin-left:auto; font-family:'JetBrains Mono',monospace; font-size:11.5px; color:var(--teal-d); }

/* approvals */
.svc-approvals{ display:flex; flex-direction:column; gap:11px; }
.svc-approval{ display:flex; gap:12px; border:1px solid var(--line); border-radius:10px; padding:13px; background:#fff; }
.svc-approval-pending{ border-color:var(--orange-l); box-shadow:0 0 0 3px #fb923c1a; }
.svc-approval-approved{ opacity:.78; }
.svc-approval-declined{ opacity:.6; }
.svc-approval-icon{ width:34px; height:34px; flex:0 0 auto; border-radius:9px; display:grid; place-items:center;
  background:var(--teal-bg); color:var(--teal-d); font-size:16px; }
.svc-approval-body{ flex:1 1 auto; min-width:0; }
.svc-approval-title{ font-size:14px; font-weight:600; display:flex; align-items:center; gap:10px; }
.svc-approval-amount{ font-family:'JetBrains Mono',monospace; font-size:13px; color:var(--teal-d);
  background:var(--teal-bg); padding:1px 8px; border-radius:6px; }
.svc-approval-summary{ font-size:12.5px; color:var(--muted); margin:3px 0 0; }
.svc-approval-lines{ margin:8px 0 0; padding-left:16px; display:flex; flex-direction:column; gap:3px; }
.svc-approval-lines li{ font-size:12.5px; color:var(--ink); }
.svc-approval-rec{ margin-top:9px; font-size:12px; color:var(--orange); background:var(--orange-bg);
  padding:7px 10px; border-radius:7px; }
.svc-approval-rec span{ font-weight:700; }
.svc-approval-actions{ display:flex; gap:8px; margin-top:11px; }
.svc-btn{ padding:7px 16px; border-radius:8px; font-family:inherit; font-size:12.5px; font-weight:600; cursor:pointer; border:1px solid transparent; }
.svc-btn-approve{ background:var(--teal); color:#fff; }
.svc-btn-approve:hover{ background:var(--teal-d); }
.svc-btn-decline{ background:#fff; color:var(--muted); border-color:var(--line); }
.svc-btn-decline:hover{ border-color:#ef4444; color:#ef4444; }
.svc-approval-status{ margin-top:10px; font-size:12px; font-weight:600; }
.svc-approval-status.svc-approval-approved{ color:var(--teal-d); }
.svc-approval-status.svc-approval-declined{ color:#ef4444; }

/* loan grid + fields */
.svc-loan-grid{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px 18px; }
.svc-field{ display:flex; flex-direction:column; gap:3px; }
.svc-field-label{ font-size:10.5px; text-transform:uppercase; letter-spacing:.5px; color:var(--muted); }
.svc-field-value{ font-size:13.5px; font-weight:500; }

/* tables */
.svc-table-wrap{ overflow-x:auto; }
.svc-table{ width:100%; border-collapse:collapse; font-size:12.5px; }
.svc-table th{ text-align:left; font-size:10.5px; text-transform:uppercase; letter-spacing:.5px; color:var(--muted);
  padding:7px 10px; border-bottom:1px solid var(--line); font-weight:600; }
.svc-table td{ padding:9px 10px; border-bottom:1px solid #eef4f3; }
.svc-table tr:last-child td{ border-bottom:none; }
.svc-doc-status{ font-size:11px; padding:2px 8px; border-radius:6px; text-transform:capitalize; }
.svc-doc-held{ background:#eef2f7; color:#475569; } .svc-doc-ready{ background:var(--teal-bg); color:var(--teal-d); }
.svc-doc-released{ background:#dcfce7; color:#15803d; } .svc-doc-pending{ background:var(--orange-bg); color:var(--orange); }
.svc-doc-open{ background:#fee2e2; color:#b91c1c; font-weight:600; }

/* notes (authored comments) */
.svc-notes{ display:flex; flex-direction:column; gap:10px; margin-bottom:14px; }
.svc-note{ border:1px solid var(--line); border-left:3px solid var(--teal-l); border-radius:9px; padding:10px 12px; background:#fbfdfc; }
.svc-note-head{ display:flex; align-items:center; gap:9px; margin-bottom:5px; }
.svc-note-author{ font-size:12px; font-weight:700; }
.svc-note-advisor{ color:var(--orange); } .svc-note-agent{ color:var(--teal); }
.svc-note-dept{ font-size:11px; font-weight:600; color:var(--teal-d); background:var(--teal-bg); padding:1px 7px; border-radius:5px; }
.svc-note-time{ margin-left:auto; font-size:10.5px; color:var(--muted); font-family:'JetBrains Mono',monospace; }
.svc-note-text{ font-size:12.5px; color:var(--ink); line-height:1.5; white-space:pre-wrap; }
.svc-note-compose{ border:1px solid var(--line); border-radius:9px; padding:10px; background:#fff; }
.svc-note-input{ width:100%; border:none; outline:none; resize:vertical; font-family:inherit; font-size:13px; color:var(--ink);
  background:transparent; padding:2px; line-height:1.5; }
.svc-note-input::placeholder{ color:#9bb2ae; }
.svc-note-compose-foot{ display:flex; align-items:center; gap:10px; margin-top:8px; padding-top:9px; border-top:1px solid var(--line); }
.svc-note-dept-select{ font-family:inherit; font-size:12px; color:var(--ink); background:#fff; border:1px solid var(--line);
  border-radius:7px; padding:6px 9px; cursor:pointer; }
.svc-note-compose-foot .svc-btn{ margin-left:auto; }

/* activity */
.svc-activity{ display:flex; flex-direction:column; gap:9px; }
.svc-activity-row{ display:flex; gap:10px; align-items:baseline; font-size:12.5px; }
.svc-activity-actor{ flex:0 0 auto; width:48px; font-size:10.5px; font-weight:700; text-transform:uppercase; letter-spacing:.4px; }
.svc-actor-agent{ color:var(--teal); } .svc-actor-advisor{ color:var(--orange); } .svc-actor-system{ color:var(--muted); }
.svc-activity-text{ color:var(--ink); }

/* case rail */
.svc-case-rail{ width:248px; flex:0 0 auto; border-left:1px solid var(--line); background:#ffffffcc; padding:16px 14px;
  display:flex; flex-direction:column; gap:14px; }
.svc-rail-card{ background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:13px; display:flex; flex-direction:column; gap:11px; }
.svc-rail-card-label{ font-size:10.5px; text-transform:uppercase; letter-spacing:.5px; color:var(--muted); }
.svc-rail-cust{ display:flex; align-items:center; gap:10px; }
.svc-rail-cust strong{ display:block; font-size:13px; }
.svc-rail-cust .svc-muted{ font-size:11.5px; }

/* highlight flash */
.svc-flash{ animation:svc-flash 1.6s ease; }
@keyframes svc-flash{ 0%,100%{ box-shadow:0 0 0 0 #ea580c00; } 25%,60%{ box-shadow:0 0 0 3px #ea580c66; border-color:var(--orange); } }

/* workup panel */
.svc-panel-workup{ border-color:var(--teal-l); }
.svc-findings{ display:flex; flex-direction:column; gap:1px; background:var(--line); border:1px solid var(--line);
  border-radius:9px; overflow:hidden; }
.svc-finding{ display:flex; gap:14px; align-items:baseline; padding:10px 13px; background:#fff; }
.svc-finding-label{ flex:0 0 38%; font-size:12px; color:var(--muted); }
.svc-finding-value{ flex:1 1 auto; font-size:13px; color:var(--ink); display:flex; align-items:baseline; gap:8px; }
.svc-finding-warn{ background:var(--orange-bg); }
.svc-finding-warn .svc-finding-value{ color:#9a3412; font-weight:500; }
.svc-finding-info .svc-finding-value{ color:var(--teal-d); }
.svc-finding-mark{ flex:0 0 auto; width:15px; height:15px; border-radius:50%; background:var(--orange); color:#fff;
  font-size:10px; font-weight:700; display:inline-grid; place-items:center; }

/* blocker */
.svc-blocker{ display:flex; gap:12px; border-radius:10px; padding:13px; margin-bottom:13px; border:1px solid; }
.svc-blocker-block{ background:#fef2f2; border-color:#fca5a5; }
.svc-blocker-warn{ background:var(--orange-bg); border-color:var(--orange-l); }
.svc-blocker-resolved{ background:#ecfdf5; border-color:#6ee7b7; }
.svc-blocker-icon{ width:34px; height:34px; flex:0 0 auto; border-radius:9px; display:grid; place-items:center; font-size:17px;
  background:#ffffffb0; }
.svc-blocker-body{ flex:1 1 auto; min-width:0; }
.svc-blocker-title{ font-size:14px; font-weight:700; color:#7f1d1d; display:flex; align-items:center; gap:10px; }
.svc-blocker-warn .svc-blocker-title{ color:#9a3412; }
.svc-blocker-resolved .svc-blocker-title{ color:#065f46; }
.svc-blocker-tag{ font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.4px; color:#fff;
  background:#dc2626; padding:2px 7px; border-radius:5px; }
.svc-blocker-detail{ font-size:12.5px; color:var(--ink); margin-top:4px; line-height:1.45; }
.svc-blocker-actions{ display:flex; align-items:center; gap:12px; margin-top:10px; }
.svc-blocker-actions .svc-muted{ font-size:11.5px; }
.svc-btn-route{ background:var(--teal-d); color:#fff; }
.svc-btn-route:hover{ background:#083f3a; }

/* packet (regulated form) */
.svc-panel-packet{ border-color:var(--line); }
.svc-packet-status{ font-family:'JetBrains Mono',monospace; font-size:10.5px; font-weight:500; text-transform:uppercase;
  letter-spacing:.4px; padding:2px 8px; border-radius:6px; background:#eef4f3; color:var(--muted); }
.svc-packet-ready{ background:var(--teal-bg); color:var(--teal-d); }
.svc-packet-submitting{ background:var(--orange-bg); color:var(--orange); }
.svc-packet-submitted{ background:#dcfce7; color:#15803d; }
.svc-packet-secs{ display:flex; flex-direction:column; gap:10px; }
.svc-packet-sec{ border:1px solid var(--line); border-radius:9px; padding:12px; }
.svc-packet-sec-blocked{ border-color:#fca5a5; background:#fef2f2; }
.svc-packet-sec-approved{ border-color:#6ee7b7; }
.svc-packet-sec-head{ display:flex; align-items:center; justify-content:space-between; margin-bottom:9px; }
.svc-packet-sec-title{ font-size:12.5px; font-weight:600; }
.svc-packet-sec-lock{ font-size:11px; color:#b91c1c; font-weight:600; }
.svc-packet-fields{ display:grid; grid-template-columns:repeat(3,1fr); gap:11px 16px; }
.svc-packet-sec-reason{ margin-top:10px; font-size:11.5px; color:#b91c1c; background:#fff; border-radius:6px; padding:6px 9px; }
.svc-packet-foot{ display:flex; align-items:center; gap:12px; margin-top:14px; padding-top:13px; border-top:1px solid var(--line); }
.svc-packet-reason{ font-size:12px; color:var(--muted); }
.svc-packet-done{ font-size:13px; font-weight:600; color:#15803d; }
.svc-btn:disabled{ opacity:.45; cursor:not-allowed; }

/* approval blocked state */
.svc-approval-blocked{ border-color:#fca5a5; box-shadow:0 0 0 3px #fecaca66; }
.svc-approval-blocked .svc-approval-icon{ background:#fee2e2; color:#b91c1c; }
.svc-approval-blocked-note{ margin-top:10px; font-size:12px; font-weight:600; color:#b91c1c; background:#fef2f2;
  border-radius:7px; padding:7px 10px; }

/* archive search overlay */
.svc-archive{ position:fixed; top:66px; left:50%; transform:translateX(-50%); width:430px; max-width:calc(100vw - 32px);
  background:var(--surface); border:1px solid var(--line); border-radius:13px; box-shadow:0 22px 54px #0b3d3938; z-index:60;
  overflow:hidden; font-family:'Archivo',system-ui,sans-serif; }
.svc-archive-head{ display:flex; align-items:flex-start; justify-content:space-between; padding:12px 15px;
  background:var(--teal-d); color:#EAF6F4; }
.svc-archive-kicker{ display:block; font-size:10px; text-transform:uppercase; letter-spacing:.6px; color:#9FD4CD; }
.svc-archive-query{ display:block; font-size:13.5px; font-weight:600; margin-top:2px; }
.svc-archive-head button{ background:#ffffff22; border:none; color:#EAF6F4; border-radius:7px; width:24px; height:24px;
  cursor:pointer; flex:0 0 auto; }
.svc-archive-searching{ display:flex; align-items:center; gap:9px; padding:20px 15px; font-size:13px; color:var(--muted); }
.svc-archive-empty{ padding:20px 15px; font-size:13px; color:var(--muted); }
.svc-archive-list{ display:flex; flex-direction:column; }
.svc-archive-row{ padding:12px 15px; border-bottom:1px solid var(--line); }
.svc-archive-row-head{ display:flex; align-items:center; gap:9px; margin-bottom:5px; }
.svc-archive-row-head .svc-mono{ font-size:11.5px; color:var(--teal); }
.svc-archive-cust{ font-size:12.5px; font-weight:600; }
.svc-archive-days{ margin-left:auto; font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--muted);
  background:#eef4f3; padding:1px 7px; border-radius:5px; }
.svc-archive-summary{ font-size:12.5px; color:var(--ink); margin-bottom:5px; }
.svc-archive-res{ font-size:12px; color:var(--teal-d); }
.svc-archive-res span{ font-weight:700; text-transform:uppercase; font-size:10px; letter-spacing:.4px; margin-right:5px; }
.svc-archive-foot{ width:100%; text-align:center; padding:11px; background:var(--teal-bg); color:var(--teal-d);
  border:none; cursor:pointer; font-family:inherit; font-size:12.5px; font-weight:600; }
.svc-archive-foot:hover{ background:#d6ebe7; }

/* ── phone (≤640px) ───────────────────────────────────────────────────────────
   Same console, one column. The desk furniture that only earns its space on a
   wide monitor (search box, breadcrumb, advisor name, rail labels) steps aside;
   the work itself — queue, case, approvals — stays whole, and anything genuinely
   wide (the payment ledger) scrolls inside its own box instead of dragging the
   page sideways. */
@media (max-width:640px){
  /* top bar: brand mark, assistant tray, advisor avatar, voice control. */
  .svc-topbar{ gap:10px; padding:0 10px; overflow:hidden; }
  .svc-brand-text,.svc-crumbs,.svc-topbar-search,.svc-advisor-text,.svc-topbar-div{ display:none; }
  .svc-tray{ margin-left:auto; }
  .svc-tray-btn{ height:32px; padding:0 10px; gap:6px; font-size:12px; }
  .svc-tray-pop{ position:fixed; top:56px; left:10px; right:10px; width:auto; }
  .svc-advisor{ padding-left:0; }

  /* left rail → a horizontal filter strip above the work */
  .svc-body{ flex-direction:column; }
  .svc-rail{ width:auto; flex:0 0 auto; flex-direction:row; align-items:center; gap:8px;
    padding:8px 10px; border-right:none; border-bottom:1px solid var(--line);
    overflow-x:auto; overflow-y:hidden; }
  .svc-rail-group{ flex-direction:row; align-items:center; gap:6px; flex:0 0 auto; }
  .svc-rail-label,.svc-rail-foot{ display:none; }
  .svc-rail-item{ flex:0 0 auto; gap:6px; padding:6px 10px; border:1px solid var(--line);
    background:var(--surface); white-space:nowrap; font-size:12px; }
  .svc-rail-dept{ font-size:12px; }
  .svc-main{ min-height:0; }

  /* board: the stage columns stack instead of scrolling sideways */
  .svc-board-wrap{ padding:14px 12px; }
  .svc-board-head{ flex-direction:column; align-items:flex-start; gap:2px; margin-bottom:12px; }
  .svc-board{ flex-direction:column; gap:12px; overflow-x:visible; }
  .svc-col{ width:100%; min-width:0; }

  /* case: the customer rail drops under the case body */
  .svc-case{ flex-direction:column; }
  .svc-case-main{ padding:14px 12px; }
  .svc-case-head h1{ font-size:16px; }
  .svc-case-rail{ width:auto; flex:0 0 auto; border-left:none; border-top:1px solid var(--line);
    padding:14px 12px; }
  .svc-tabs{ gap:2px; overflow-x:auto; }
  .svc-tab{ flex:0 0 auto; padding:9px 10px; white-space:nowrap; }

  /* panels: two-up grids, nothing side-by-side that needs the width */
  .svc-panel{ padding:13px; }
  .svc-loan-grid{ grid-template-columns:repeat(2,1fr); gap:12px 14px; }
  .svc-packet-fields{ grid-template-columns:repeat(2,1fr); }
  .svc-finding{ flex-direction:column; gap:3px; }
  .svc-finding-label{ flex:0 0 auto; }
  .svc-approval{ gap:9px; padding:11px; }
  .svc-approval-icon{ width:28px; height:28px; font-size:14px; }
  .svc-approval-title{ flex-wrap:wrap; gap:7px; }
  .svc-blocker-actions{ flex-direction:column; align-items:flex-start; gap:7px; }
  .svc-prep-job{ flex-wrap:wrap; }
  .svc-packet-foot,.svc-note-compose-foot{ flex-wrap:wrap; }
  .svc-note-dept-select{ max-width:100%; }

  /* the payment ledger is the one genuinely wide thing: its own scroll box */
  .svc-table-wrap{ -webkit-overflow-scrolling:touch; }
  #svc-sec-payments .svc-table{ min-width:520px; }

  /* legibility floor — nothing under 11px on a phone */
  .svc-field-label,.svc-rail-card-label,.svc-table th,.svc-activity-actor,
  .svc-note-time{ font-size:11px; }
  .svc-activity-actor{ width:44px; }

  /* archive overlay spans the viewport gutters */
  .svc-archive{ left:10px; right:10px; top:60px; width:auto; max-width:none; transform:none; }
}
`;
