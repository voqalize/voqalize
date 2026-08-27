/**
 * Shared store for the Meridian Servicing Console demo.
 *
 * One React context drives both the console UI and the voice widget, so the
 * advisor and the "servicing desk" assistant work the same screen. The assistant
 * mutates state via `ui-command` RTVI messages, `{ command, payload }`
 * (handleUiCommand); the browser echoes a compact workspace snapshot back to
 * the assistant via `state_sync` (snapshot) so it always knows where the
 * advisor is and what's pending. The pair is narrowed against the generated
 * `actions.gen.ts`, so each case reads its payload typed and `default` is an
 * exhaustiveness check — add an `Action` to the brain and this file stops
 * compiling until it is handled.
 *
 * The `norm*` functions below are not validation. They are the one real
 * translation in this demo: the desk sends a *specification* and the console
 * holds a *thing with a life* — a job that is queued then running then done, a
 * blocker that can be resolved, a section that is approved. None of that state
 * belongs on the wire, and none of it is the model's to set.
 *
 * The headline behaviour: `prepareCase` kicks off a case's prep jobs that
 * animate to completion ON THEIR OWN — the advisor stays on whatever case they
 * have open, never blocked — and when the jobs finish, the assistant's drafts
 * appear in that case's "Needs your approval" queue. Maker-checker: the advisor
 * approves; the assistant never executes.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  type Approval,
  type ApprovalStatus,
  type ArchiveSearch,
  type Blocker,
  type Case,
  type CaseTab,
  type Comment,
  type DepartmentId,
  type Finding,
  type Job,
  type Packet,
  type PacketSection,
  type PrecedentResult,
  type Stage,
  type View,
} from './types';
import {
  asUiAction,
  unhandledUiAction,
  type ApprovalSpec,
  type BlockerSpec,
  type FindingSpec,
  type Highlight as HighlightAction,
  type JobSpec,
  type PacketSectionSpec,
  type PacketSpec,
  type PrecedentSpec,
} from './actions.gen';
import { DEPARTMENTS, TEAM, WORKSPACE } from './data';

type AgentSend = (type: string, data: Record<string, unknown>) => void;

interface HighlightState {
  section: HighlightAction['section'];
  nonce: number;
}

/** What the board is filtered to, driven by the left-rail navigation. */
export type BoardFilter =
  | { kind: 'mine' }
  | { kind: 'all' }
  | { kind: 'needs_approval' }
  | { kind: 'department'; dept: DepartmentId };

export interface ServicingStore {
  advisor: typeof WORKSPACE.advisor;
  team: typeof WORKSPACE.team;
  departments: typeof WORKSPACE.departments;
  cases: Case[];
  view: View;
  activeRef: string | null;
  tab: CaseTab;
  filter: BoardFilter;
  highlighted: HighlightState | null;
  rev: number;

  active: Case | null;
  pendingApprovals: number;
  /** Number of cases sitting in the "Needs approval" view (stage or pending drafts). */
  needsApprovalCount: number;
  preparing: Case[];
  /** Result of the last server-side precedent search (null when none/dismissed). */
  archiveSearch: ArchiveSearch | null;

  // navigation
  openBoard: () => void;
  openCase: (ref: string) => void;
  setTab: (tab: CaseTab) => void;
  setFilter: (f: BoardFilter) => void;
  highlight: (section: HighlightAction['section']) => void;

  // board / jira
  assignCase: (ref: string, kind: 'person' | 'department', assignee: string) => void;
  moveCase: (ref: string, stage: Stage) => void;
  /** Add an authored note to a case (advisor or desk); handoff/routing context. */
  addComment: (ref: string, text: string, authorKind?: 'advisor' | 'agent', dept?: string) => void;

  // work + maker-checker
  prepareCase: (
    ref: string,
    summary: string,
    jobs: JobSpec[],
    approvals: ApprovalSpec[],
    extras?: { findings?: FindingSpec[]; blocker?: BlockerSpec | null; packet?: PacketSpec | null },
  ) => void;
  draftApproval: (ref: string, approval: ApprovalSpec) => void;
  decideApproval: (ref: string, approvalId: string, decision: ApprovalStatus) => void;

  // server-side tools (the desk reaches beyond the screen)
  postWorkup: (ref: string, findings: FindingSpec[], blocker?: BlockerSpec | null) => void;
  lookupPrecedent: (query: string, results: PrecedentSpec[]) => void;
  dismissSearch: () => void;
  // packet (regulated multi-step form)
  updatePacketField: (ref: string, section: string, field: string, value: string, note?: string) => void;
  resolveBlocker: (ref: string, note?: string) => void;
  submitPacket: (ref: string) => void;
  canSubmitPacket: (c: Case) => boolean;

  // bridges
  snapshot: () => Record<string, unknown>;
  handleUiCommand: (command: string, payload: unknown) => void;
  registerAgentSend: (fn: AgentSend | null) => void;
}

const Ctx = createContext<ServicingStore | null>(null);

export function useServicing(): ServicingStore {
  const v = useContext(Ctx);
  if (!v) throw new Error('useServicing must be used within ServicingProvider');
  return v;
}

// The desk assigns ids to jobs, findings, approvals and precedents server-side.
// A packet and its sections carry the id the model chose, and a blocker has none
// at all — those three are the only rows the browser has to name itself.
let _idc = 0;
const rid = (p: string): string => `${p}-${Date.now().toString(36)}-${_idc++}`;

/** A draft as sent, plus the queue state it enters — always pending or blocked. */
function normApproval(spec: ApprovalSpec): Approval {
  return {
    id: spec.id,
    title: spec.title,
    kind: spec.kind,
    summary: spec.summary,
    lines: spec.lines,
    amount: spec.amount ?? undefined,
    recommendation: spec.recommendation || undefined,
    status: spec.blocked ? 'blocked' : 'pending',
    blockedReason: spec.blocked
      ? spec.blocked_reason || 'Blocked — resolve the flagged issue first.'
      : undefined,
  };
}

function normFinding(spec: FindingSpec): Finding {
  return { id: spec.id, label: spec.label, value: spec.value, flag: spec.flag };
}

/** A blocker arrives open, is named here, and is resolved by the advisor later. */
function normBlocker(spec: BlockerSpec | null | undefined): Blocker | null {
  if (!spec) return null;
  return {
    id: rid('blk'),
    title: spec.title,
    detail: spec.detail,
    severity: spec.severity,
    suggestedRoute: spec.suggested_route || undefined,
    status: 'open',
  };
}

function normSection(spec: PacketSectionSpec): PacketSection {
  return {
    id: spec.id || rid('sec'),
    title: spec.title,
    fields: spec.fields.map((f) => ({ label: f.label, value: f.value, mono: f.mono })),
    status: spec.blocked ? 'blocked' : 'ready',
    blockedReason: spec.blocked ? spec.blocked_reason || 'Blocked.' : undefined,
  };
}

function normPacket(spec: PacketSpec | null | undefined): Packet | null {
  if (!spec || !spec.sections.length) return null;
  return {
    id: spec.id || rid('pkt'),
    title: spec.title,
    summary: spec.summary || undefined,
    sections: spec.sections.map(normSection),
    status: 'ready',
  };
}

function normPrecedent(spec: PrecedentSpec): PrecedentResult {
  return {
    ref: spec.ref,
    customer: spec.customer,
    summary: spec.summary,
    resolution: spec.resolution,
    days: spec.days ?? undefined,
  };
}

function findPerson(name: string) {
  const n = name.trim().toLowerCase();
  return (
    TEAM.find((p) => p.name.toLowerCase() === n) ||
    TEAM.find((p) => p.name.toLowerCase().startsWith(n)) ||
    TEAM.find((p) => p.name.toLowerCase().includes(n))
  );
}

function findDept(idOrLabel: string) {
  const n = idOrLabel.trim().toLowerCase();
  return (
    DEPARTMENTS.find((d) => d.id === n) ||
    DEPARTMENTS.find((d) => d.label.toLowerCase() === n) ||
    DEPARTMENTS.find((d) => d.label.toLowerCase().includes(n))
  );
}

// Background-prep animation cadence.
const PREP_LEAD = 500;
const PREP_STEP = 1700;
const PREP_RUN = 1500;
// Server-tool latency (the desk reaching beyond the screen) — real delay, so the
// "voice keeps going while the call runs" point lands instead of being hidden.
const SEARCH_DELAY = 1400;
const SUBMIT_DELAY = 1500;

/** Whether a case's regulated packet can be submitted (server-action gate). */
function packetSubmittable(c: Case): boolean {
  if (!c.packet) return false;
  if (c.packet.status !== 'ready') return false;
  if (c.blocker && c.blocker.severity === 'block' && c.blocker.status === 'open') return false;
  if (c.packet.sections.some((s) => s.status === 'blocked')) return false;
  // Maker-checker: every draft must be signed (approved/declined) — nothing left
  // pending or blocked — before the system will submit.
  if (c.approvals.some((a) => a.status === 'pending' || a.status === 'blocked')) return false;
  return true;
}

export function ServicingProvider({ children }: { children: ReactNode }) {
  const [cases, setCases] = useState<Case[]>(() => WORKSPACE.cases.map((c) => ({ ...c })));
  const [view, setView] = useState<View>('board');
  const [activeRef, setActiveRef] = useState<string | null>(null);
  const [tab, setTabState] = useState<CaseTab>('overview');
  const [filter, setFilterState] = useState<BoardFilter>({ kind: 'mine' });
  const [highlighted, setHighlighted] = useState<HighlightState | null>(null);
  const [archiveSearch, setArchiveSearch] = useState<ArchiveSearch | null>(null);
  const [rev, setRev] = useState(0);

  const agentSendRef = useRef<AgentSend | null>(null);
  const timersRef = useRef<number[]>([]);

  useEffect(
    () => () => {
      timersRef.current.forEach((t) => window.clearTimeout(t));
      timersRef.current = [];
    },
    [],
  );

  const bump = useCallback(() => setRev((r) => r + 1), []);

  const mutateCase = useCallback(
    (ref: string, fn: (c: Case) => Case) => {
      setCases((list) => list.map((c) => (c.ref === ref ? fn(c) : c)));
      bump();
    },
    [bump],
  );

  const logActivity = (c: Case, actor: 'agent' | 'advisor' | 'system', text: string): Case => ({
    ...c,
    activity: [...c.activity, { id: rid('act'), ts: Date.now(), actor, text }],
  });

  // ── navigation ──────────────────────────────────────────────────────────
  const openBoard = useCallback(() => {
    setView('board');
    setActiveRef(null);
    bump();
  }, [bump]);

  const openCase = useCallback(
    (ref: string) => {
      const r = ref.trim().toUpperCase();
      setCases((list) => {
        if (!list.some((c) => c.ref === r)) return list;
        return list;
      });
      setActiveRef(r);
      setView('case');
      setTabState('overview');
      bump();
    },
    [bump],
  );

  const setTab = useCallback(
    (t: CaseTab) => {
      setTabState(t);
      bump();
    },
    [bump],
  );

  const setFilter = useCallback(
    (f: BoardFilter) => {
      setFilterState(f);
      bump();
    },
    [bump],
  );

  const highlight = useCallback(
    (section: HighlightAction['section']) => {
      setView('case');
      setHighlighted({ section, nonce: Date.now() });
      bump();
    },
    [bump],
  );

  // ── board / jira ──────────────────────────────────────────────────────────
  const assignCase = useCallback(
    (ref: string, kind: 'person' | 'department', assignee: string) => {
      const r = ref.trim().toUpperCase();
      mutateCase(r, (c) => {
        let next = c;
        if (kind === 'department') {
          const d = findDept(assignee);
          if (!d) return c;
          next = {
            ...c,
            assignee: { kind: 'department', id: d.id, label: d.label },
            stage: c.stage === 'done' ? c.stage : 'with_dept',
          };
          next = logActivity(next, 'agent', `Routed to ${d.label}`);
        } else {
          const p = findPerson(assignee);
          if (!p) return c;
          next = { ...c, assignee: { kind: 'person', id: p.id, label: p.name } };
          next = logActivity(next, 'agent', `Assigned to ${p.name}`);
        }
        return next;
      });
    },
    [mutateCase],
  );

  const moveCase = useCallback(
    (ref: string, stage: Stage) => {
      const r = ref.trim().toUpperCase();
      mutateCase(r, (c) =>
        logActivity({ ...c, stage }, 'agent', `Moved to ${stage.replace('_', ' ')}`),
      );
    },
    [mutateCase],
  );

  const addComment = useCallback(
    (ref: string, text: string, authorKind: 'advisor' | 'agent' = 'advisor', dept?: string) => {
      const body = text.trim();
      if (!body) return;
      const r = ref.trim().toUpperCase();
      const d = dept ? findDept(dept) : undefined;
      const author = authorKind === 'agent' ? 'Servicing desk' : WORKSPACE.advisor.name;
      const comment: Comment = {
        id: rid('cm'),
        ts: Date.now(),
        author,
        authorKind,
        text: body,
        dept: d?.id,
        deptLabel: d?.label,
      };
      mutateCase(r, (c) =>
        logActivity(
          { ...c, comments: [...c.comments, comment] },
          authorKind,
          `Added a note${d ? ` for ${d.label}` : ''}`,
        ),
      );
    },
    [mutateCase],
  );

  // ── work + maker-checker ──────────────────────────────────────────────────
  const prepareCase = useCallback(
    (
      ref: string,
      summary: string,
      rawJobs: JobSpec[],
      rawApprovals: ApprovalSpec[],
      extras?: { findings?: FindingSpec[]; blocker?: BlockerSpec | null; packet?: PacketSpec | null },
    ) => {
      const r = ref.trim().toUpperCase();
      const jobs: Job[] = rawJobs
        .filter((j) => j.label)
        .map((j) => ({
          id: j.id,
          label: j.label,
          detail: j.detail || undefined,
          status: 'queued' as const,
        }));
      if (!jobs.length) return;

      const findings = (extras?.findings ?? []).map(normFinding).filter((f) => f.label);
      const blocker = normBlocker(extras?.blocker);
      const packet = normPacket(extras?.packet);
      // If the workup caught a hard blocker, a document-release draft can't be
      // approved until it's cleared — born blocked, not pending.
      const approvals = rawApprovals.map(normApproval).map((a) =>
        blocker && blocker.severity === 'block' && a.kind === 'document_release' && a.status === 'pending'
          ? { ...a, status: 'blocked' as ApprovalStatus, blockedReason: blocker.title }
          : a,
      );

      mutateCase(r, (c) =>
        logActivity(
          {
            ...c,
            preparing: true,
            prepSummary: summary || c.prepSummary,
            jobs,
            stage: c.stage === 'new' ? 'in_progress' : c.stage,
          },
          'agent',
          `Started preparing in the background${summary ? ` — ${summary}` : ''}`,
        ),
      );

      // Animate jobs queued → running → done, then reveal the drafts. Runs on its
      // own timers so the advisor stays unblocked on whatever they have open.
      const setJob = (jobId: string, status: Job['status']) =>
        mutateCase(r, (c) => ({
          ...c,
          jobs: c.jobs.map((j) => (j.id === jobId ? { ...j, status } : j)),
        }));

      jobs.forEach((job, i) => {
        const startAt = PREP_LEAD + i * PREP_STEP;
        timersRef.current.push(window.setTimeout(() => setJob(job.id, 'running'), startAt));
        timersRef.current.push(
          window.setTimeout(() => setJob(job.id, 'done'), startAt + PREP_RUN),
        );
      });

      const finishAt = PREP_LEAD + jobs.length * PREP_STEP + 300;
      timersRef.current.push(
        window.setTimeout(() => {
          mutateCase(r, (c) => {
            const done: Case = {
              ...c,
              preparing: false,
              jobs: c.jobs.map((j) => ({ ...j, status: 'done' })),
              findings: findings.length ? findings : c.findings,
              blocker: blocker ?? c.blocker,
              packet: packet ?? c.packet,
              approvals: [...c.approvals, ...approvals],
              stage: approvals.length ? 'needs_approval' : c.stage,
            };
            const bits: string[] = [];
            if (approvals.length)
              bits.push(`${approvals.length} item${approvals.length > 1 ? 's' : ''} to approve`);
            if (blocker)
              bits.push(blocker.severity === 'block' ? `flagged a blocker: ${blocker.title}` : `flagged: ${blocker.title}`);
            return logActivity(
              done,
              'agent',
              bits.length ? `Workup complete — ${bits.join('; ')}` : 'Prep complete',
            );
          });
        }, finishAt),
      );
    },
    [mutateCase],
  );

  // ── server-side tools: workup, archive search, packet ──────────────────────
  const setWorkup = useCallback(
    (ref: string, rawFindings: FindingSpec[], rawBlocker?: BlockerSpec | null) => {
      const r = ref.trim().toUpperCase();
      const findings = rawFindings.map(normFinding).filter((f) => f.label);
      const blocker = normBlocker(rawBlocker);
      mutateCase(r, (c) => {
        const next: Case = {
          ...c,
          findings: findings.length ? findings : c.findings,
          blocker: blocker ?? c.blocker,
        };
        const bits: string[] = [];
        if (findings.length) bits.push(`${findings.length} finding${findings.length > 1 ? 's' : ''}`);
        if (blocker) bits.push(`flagged ${blocker.title}`);
        return logActivity(next, 'agent', `Workup — ${bits.join(', ') || 'reviewed the case'}`);
      });
    },
    [mutateCase],
  );

  const postWorkup = useCallback(
    (ref: string, findings: FindingSpec[], blocker?: BlockerSpec | null) =>
      setWorkup(ref, findings, blocker),
    [setWorkup],
  );

  const lookupPrecedent = useCallback(
    (query: string, rawResults: PrecedentSpec[]) => {
      const q = query || 'similar cases';
      const results = rawResults.map(normPrecedent);
      setArchiveSearch({ query: q, status: 'searching', results: [] });
      bump();
      timersRef.current.push(
        window.setTimeout(() => {
          setArchiveSearch({ query: q, status: 'done', results });
          bump();
        }, SEARCH_DELAY),
      );
    },
    [bump],
  );

  const dismissSearch = useCallback(() => {
    setArchiveSearch(null);
    bump();
  }, [bump]);

  const updatePacketField = useCallback(
    (ref: string, section: string, field: string, value: string, note?: string) => {
      const r = ref.trim().toUpperCase();
      const sec = (section || '').trim().toLowerCase();
      const fld = (field || '').trim().toLowerCase();
      mutateCase(r, (c) => {
        if (!c.packet) return c;
        const sections = c.packet.sections.map((s) => {
          const matchSec = s.id.toLowerCase() === sec || s.title.toLowerCase().includes(sec);
          if (!matchSec) return s;
          return {
            ...s,
            fields: s.fields.map((f) =>
              f.label.toLowerCase().includes(fld) ? { ...f, value } : f,
            ),
          };
        });
        return logActivity(
          { ...c, packet: { ...c.packet, sections } },
          'agent',
          note || `Updated ${field} to ${value}`,
        );
      });
    },
    [mutateCase],
  );

  const resolveBlocker = useCallback(
    (ref: string, note?: string) => {
      const r = ref.trim().toUpperCase();
      mutateCase(r, (c) => {
        if (!c.blocker) return c;
        const next: Case = {
          ...c,
          blocker: { ...c.blocker, status: 'resolved', resolvedNote: note || undefined },
          // Unblock anything the blocker was gating.
          approvals: c.approvals.map((a) =>
            a.status === 'blocked' ? { ...a, status: 'pending', blockedReason: undefined } : a,
          ),
          packet: c.packet
            ? {
                ...c.packet,
                sections: c.packet.sections.map((s) =>
                  s.status === 'blocked' ? { ...s, status: 'ready', blockedReason: undefined } : s,
                ),
              }
            : c.packet,
        };
        return logActivity(next, 'system', note || `Cleared: ${c.blocker.title}`);
      });
    },
    [mutateCase],
  );

  const submitPacket = useCallback(
    (ref: string) => {
      const r = ref.trim().toUpperCase();
      const target = cases.find((c) => c.ref === r);
      if (!target || !target.packet || !packetSubmittable(target)) return; // server-action gate
      const dest = target.assignee.kind === 'department' ? target.assignee.label : 'Closures & Payoffs';
      mutateCase(r, (c) =>
        c.packet
          ? logActivity(
              { ...c, packet: { ...c.packet, status: 'submitting' } },
              'advisor',
              `Submitted the ${c.packet.title.toLowerCase()}`,
            )
          : c,
      );
      timersRef.current.push(
        window.setTimeout(() => {
          mutateCase(r, (c) =>
            c.packet
              ? logActivity(
                  {
                    ...c,
                    packet: { ...c.packet, status: 'submitted', submittedTo: dest },
                    stage: 'with_dept',
                  },
                  'system',
                  `${c.packet.title} submitted to ${dest}`,
                )
              : c,
          );
        }, SUBMIT_DELAY),
      );
    },
    [cases, mutateCase],
  );

  const canSubmitPacket = useCallback((c: Case) => packetSubmittable(c), []);

  const draftApproval = useCallback(
    (ref: string, raw: ApprovalSpec) => {
      const r = ref.trim().toUpperCase();
      const approval = normApproval(raw);
      mutateCase(r, (c) =>
        logActivity(
          {
            ...c,
            approvals: [...c.approvals, approval],
            stage: c.stage === 'done' ? c.stage : 'needs_approval',
          },
          'agent',
          `Drafted “${approval.title}” for your approval`,
        ),
      );
    },
    [mutateCase],
  );

  const decideApproval = useCallback(
    (ref: string, approvalId: string, decision: ApprovalStatus) => {
      const r = ref.trim().toUpperCase();
      mutateCase(r, (c) => {
        const target = c.approvals.find((a) => a.id === approvalId);
        if (!target) return c;
        const next = {
          ...c,
          approvals: c.approvals.map((a) => (a.id === approvalId ? { ...a, status: decision } : a)),
        };
        return logActivity(
          next,
          'advisor',
          `${decision === 'approved' ? 'Approved' : 'Declined'} “${target.title}”`,
        );
      });
    },
    [mutateCase],
  );

  // ── derived ─────────────────────────────────────────────────────────────
  const active = useMemo(
    () => cases.find((c) => c.ref === activeRef) ?? null,
    [cases, activeRef],
  );
  const pendingApprovals = useMemo(
    () =>
      cases.reduce((n, c) => n + c.approvals.filter((a) => a.status === 'pending').length, 0),
    [cases],
  );
  const needsApprovalCount = useMemo(
    () =>
      cases.filter(
        (c) => c.stage === 'needs_approval' || c.approvals.some((a) => a.status === 'pending'),
      ).length,
    [cases],
  );
  const preparing = useMemo(() => cases.filter((c) => c.preparing), [cases]);

  // ── state_sync snapshot (lean view for the assistant) ──────────────────────
  const snapshot = useCallback((): Record<string, unknown> => {
    const a = cases.find((c) => c.ref === activeRef) ?? null;
    return {
      advisor: { name: WORKSPACE.advisor.name, role: WORKSPACE.advisor.role },
      view,
      tab,
      pending_approvals: cases.reduce(
        (n, c) => n + c.approvals.filter((x) => x.status === 'pending').length,
        0,
      ),
      preparing: cases.filter((c) => c.preparing).map((c) => c.ref),
      active_case: a
        ? {
            ref: a.ref,
            customer: a.customer.name,
            type: a.type,
            title: a.title,
            stage: a.stage,
            assignee: a.assignee.label,
            rate: a.customer.rate,
            balance: a.customer.balance,
            monthly_payment: a.customer.monthlyPayment,
            tenure_years: a.customer.tenureYears,
            preparing: a.preparing,
            findings: a.findings.map((f) => ({ label: f.label, value: f.value, flag: f.flag })),
            blocker: a.blocker
              ? { title: a.blocker.title, severity: a.blocker.severity, status: a.blocker.status }
              : null,
            packet: a.packet
              ? {
                  title: a.packet.title,
                  status: a.packet.status,
                  blocked_sections: a.packet.sections.filter((s) => s.status === 'blocked').length,
                  can_submit: packetSubmittable(a),
                }
              : null,
            pending_approvals: a.approvals
              .filter((x) => x.status === 'pending')
              .map((x) => x.title),
            blocked_approvals: a.approvals
              .filter((x) => x.status === 'blocked')
              .map((x) => x.title),
            notes: a.comments.map((cm) => ({
              author: cm.author,
              text: cm.text,
              dept: cm.deptLabel,
            })),
          }
        : null,
      archive_search: archiveSearch
        ? { query: archiveSearch.query, status: archiveSearch.status, results: archiveSearch.results.length }
        : null,
      cases: cases.map((c) => ({
        ref: c.ref,
        customer: c.customer.name,
        type: c.type,
        stage: c.stage,
        assignee: c.assignee.label,
        priority: c.priority,
      })),
    };
  }, [cases, activeRef, view, tab, archiveSearch]);

  // ── ui-command dispatch (assistant drives the screen) ──────────────────────
  const handleUiCommand = useCallback(
    (command: string, payload: unknown) => {
      const action = asUiAction(command, payload);
      if (!action) return;
      switch (action.command) {
        case 'open_board':
          openBoard();
          break;
        case 'open_case':
          openCase(action.payload.ref);
          break;
        case 'set_tab':
          setTab(action.payload.tab);
          break;
        case 'assign_case': {
          const { ref, assignee_kind, assignee } = action.payload;
          assignCase(ref, assignee_kind, assignee);
          break;
        }
        case 'move_case':
          moveCase(action.payload.ref, action.payload.stage);
          break;
        case 'add_comment': {
          const { ref, text, dept } = action.payload;
          addComment(ref, text, 'agent', dept);
          break;
        }
        case 'prepare_case': {
          const { ref, summary, jobs, findings, blocker, packet } = action.payload;
          prepareCase(ref, summary, jobs, action.payload.approvals, { findings, blocker, packet });
          break;
        }
        case 'draft_approval':
          draftApproval(action.payload.ref, action.payload.approval);
          break;
        case 'post_workup': {
          const { ref, findings, blocker } = action.payload;
          postWorkup(ref, findings, blocker);
          break;
        }
        case 'lookup_precedent':
          lookupPrecedent(action.payload.query, action.payload.results);
          break;
        case 'update_packet_field': {
          const { ref, section, field, value, note } = action.payload;
          updatePacketField(ref, section, field, value, note);
          break;
        }
        case 'resolve_blocker':
          resolveBlocker(action.payload.ref, action.payload.note);
          break;
        case 'submit_packet':
          submitPacket(action.payload.ref);
          break;
        case 'highlight':
          highlight(action.payload.section);
          break;
        default:
          return unhandledUiAction(action);
      }
    },
    [
      openBoard,
      openCase,
      setTab,
      assignCase,
      moveCase,
      addComment,
      prepareCase,
      draftApproval,
      postWorkup,
      lookupPrecedent,
      updatePacketField,
      resolveBlocker,
      submitPacket,
      highlight,
    ],
  );

  const registerAgentSend = useCallback((fn: AgentSend | null) => {
    agentSendRef.current = fn;
  }, []);

  // Dev-only: expose the command dispatch so the flow can be driven/rehearsed
  // from the browser console without a live mic, e.g.
  //   __servicing.handleUiCommand('open_case', { ref: 'MS-1057' })
  //   __servicing.handleUiCommand('prepare_case', { ref: 'MS-1057', jobs: [...] })
  useEffect(() => {
    if (!import.meta.env.DEV) return;
    (window as unknown as { __servicing?: unknown }).__servicing = {
      handleUiCommand,
      snapshot,
    };
    return () => {
      delete (window as unknown as { __servicing?: unknown }).__servicing;
    };
  }, [handleUiCommand, snapshot]);

  const value: ServicingStore = {
    advisor: WORKSPACE.advisor,
    team: WORKSPACE.team,
    departments: WORKSPACE.departments,
    cases,
    view,
    activeRef,
    tab,
    filter,
    highlighted,
    rev,
    active,
    pendingApprovals,
    needsApprovalCount,
    preparing,
    archiveSearch,
    openBoard,
    openCase,
    setTab,
    setFilter,
    highlight,
    assignCase,
    moveCase,
    addComment,
    prepareCase,
    draftApproval,
    decideApproval,
    postWorkup,
    lookupPrecedent,
    dismissSearch,
    updatePacketField,
    resolveBlocker,
    submitPacket,
    canSubmitPacket,
    snapshot,
    handleUiCommand,
    registerAgentSend,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
