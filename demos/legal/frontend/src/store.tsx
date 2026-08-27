/**
 * Shared store for the Docket contract-review demo.
 *
 * One React context drives the document view and the ambient voice layer, so
 * the assistant and the lawyer work the same screen. The assistant mutates
 * state through RTVI's own `ui-command` — the brain's `session.dispatch(...)`
 * arrives as `{ command, payload }`, `actions.gen.ts` (generated from the
 * brain's `Action` classes) says what that pair can be, and
 * {@link LegalStore.handleUiCommand} is the one reducer over it: `point_to_clause` scrolls/highlights a clause,
 * `add_comment`/`propose_redline` anchor content to a clause, and
 * `run_diligence` drops fully-resolved background-task cards that animate
 * queued -> running -> done on their own (no real backend concurrency — the
 * model generates each result up front, the browser just paces the reveal). An
 * unknown command is a no-op by design: the brain and this page ship separately.
 *
 * The browser silently tells the assistant which clause is in view by sending
 * `clause_focus` as an RTVI `client-message`, so it always knows where the
 * lawyer is reading.
 *
 * What this store deliberately does **not** hold is what the assistant is
 * doing. Presence is a rendering of pipecat's own state, never a second copy of
 * it kept here — the call component derives it from RTVI events and hands it
 * to the ring as a prop.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { CLAUSES, CLAUSES_BY_ID, type Clause, type ClauseId } from './content';
import {
  asUiAction,
  unhandledUiAction,
  type AddComment,
  type DiligenceJob,
  type InsertClause,
  type Obligation as ObligationSpec,
  type ProposeRedline,
  type RouteForApproval,
} from './actions.gen';

/** The tray's own lifecycle — the brain sends a resolved job, never a running one. */
export type TaskStatus = 'queued' | 'running' | 'done';

export type TaskKind = DiligenceJob['kind'];
export type FindingFlag = NonNullable<DiligenceJob['finding_flag']>;

/** The lawyer's verdict on a routed item — nothing the assistant sets. */
export type ApprovalStatus = 'pending' | 'approved' | 'declined';

export interface Comment {
  id: string;
  clauseId: ClauseId;
  text: string;
}

export interface Redline {
  id: string;
  clauseId: ClauseId;
  originalExcerpt: string;
  proposedText: string;
  rationale: string;
}

export interface Insertion {
  id: string;
  afterClauseId: ClauseId;
  heading: string;
  proposedText: string;
  rationale: string;
}

export interface TaskCard {
  id: string;
  label: string;
  detail?: string;
  status: TaskStatus;
  kind: TaskKind;
  /** Total ms this job takes to resolve once running — drives the tray's progress bar. */
  durationMs: number;
  summary: string;
  findingValue?: string;
  findingFlag?: FindingFlag;
  precedentDeal?: string;
  precedentResolution?: string;
  benchmarkPercentile?: string;
  benchmarkNote?: string;
  exposureCap?: string;
  exposureEstimate?: string;
  exposureGap?: string;
  searchScope?: string;
  searchExcerpt?: string;
  researchFinding?: string;
  researchSource?: string;
  researchFlag?: FindingFlag;
  memoBody?: string;
}

export interface Approval {
  id: string;
  title: string;
  summary: string;
  amount: number;
  lines: string[];
  recommendation: string;
  routedTo: string;
  status: ApprovalStatus;
}

export interface Obligation {
  id: string;
  clauseId: ClauseId;
  label: string;
  window: string;
  note?: string;
}

export interface SessionSummary {
  headline: string;
  highlights: string[];
  openItems: string[];
}

interface PointerEvent_ {
  clauseId: ClauseId;
  reason: string;
  nonce: number;
}

type AgentSend = (type: string, data: Record<string, unknown>) => void;

export interface LegalStore {
  clauses: Clause[];
  focusedClauseId: ClauseId | null;
  comments: Comment[];
  redlines: Redline[];
  insertions: Insertion[];
  tasks: TaskCard[];
  approvals: Approval[];
  obligations: Obligation[];
  sessionSummary: SessionSummary | null;
  pointer: PointerEvent_ | null;

  setFocusedClause: (clauseId: ClauseId | null) => void;
  setApprovalStatus: (id: string, status: ApprovalStatus) => void;

  /** Replay one `ui-command` onto the screen. Unknown commands are ignored. */
  handleUiCommand: (command: string, payload: unknown) => void;
  registerAgentSend: (fn: AgentSend | null) => void;
  sendClauseFocus: (clauseId: ClauseId) => void;
}

const Ctx = createContext<LegalStore | null>(null);

export function useLegal(): LegalStore {
  const v = useContext(Ctx);
  if (!v) throw new Error('useLegal must be used within LegalProvider');
  return v;
}

let _idc = 0;
const rid = (p: string): string => `${p}-${Date.now().toString(36)}-${_idc++}`;

// Background-task animation cadence — staggered so cards visibly run
// concurrently, with a per-kind duration long enough to read as real
// diligence work (a data-room search resolves in seconds; a drafted memo
// takes real minutes-equivalent) rather than instant.
const TASK_LEAD = 500;
const TASK_STEP = 1400;
const TASK_RUN_MS: Record<TaskKind, number> = {
  finding: 6000,
  exposure: 7500,
  search: 9500,
  benchmark: 10500,
  precedent: 12500,
  research: 17000,
  memo: 23000,
};

export function LegalProvider({ children }: { children: ReactNode }) {
  const [focusedClauseId, setFocusedClauseId] = useState<ClauseId | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [redlines, setRedlines] = useState<Redline[]>([]);
  const [insertions, setInsertions] = useState<Insertion[]>([]);
  const [tasks, setTasks] = useState<TaskCard[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [obligations, setObligations] = useState<Obligation[]>([]);
  const [sessionSummary, setSessionSummary] = useState<SessionSummary | null>(null);
  const [pointer, setPointer] = useState<PointerEvent_ | null>(null);

  const agentSendRef = useRef<AgentSend | null>(null);
  const timersRef = useRef<number[]>([]);

  useEffect(
    () => () => {
      timersRef.current.forEach((t) => window.clearTimeout(t));
      timersRef.current = [];
    },
    [],
  );

  const setFocusedClause = useCallback((clauseId: ClauseId | null) => {
    setFocusedClauseId(clauseId);
  }, []);

  const registerAgentSend = useCallback((fn: AgentSend | null) => {
    agentSendRef.current = fn;
  }, []);

  const sendClauseFocus = useCallback((clauseId: ClauseId) => {
    const clause = CLAUSES_BY_ID[clauseId];
    if (!agentSendRef.current) return;
    try {
      agentSendRef.current('clause_focus', {
        clause_id: clause.id,
        number: clause.number,
        heading: clause.heading,
      });
    } catch {
      /* ignore */
    }
  }, []);

  const pointToClause = useCallback((clauseId: ClauseId, reason: string) => {
    setPointer({ clauseId, reason, nonce: Date.now() });
  }, []);

  const addComment = useCallback((p: AddComment) => {
    if (!p.text) return;
    setComments((list) => [...list, { id: rid('cm'), clauseId: p.clause_id, text: p.text }]);
  }, []);

  const addRedline = useCallback((p: ProposeRedline) => {
    if (!p.original_excerpt || !p.proposed_text) return;
    setRedlines((list) => [
      ...list,
      {
        id: rid('rl'),
        clauseId: p.clause_id,
        originalExcerpt: p.original_excerpt,
        proposedText: p.proposed_text,
        rationale: p.rationale,
      },
    ]);
  }, []);

  const addInsertion = useCallback((p: InsertClause) => {
    if (!p.heading || !p.proposed_text) return;
    setInsertions((list) => [
      ...list,
      {
        id: rid('ins'),
        afterClauseId: p.after_clause_id,
        heading: p.heading,
        proposedText: p.proposed_text,
        rationale: p.rationale,
      },
    ]);
  }, []);

  const runDiligence = useCallback((specs: DiligenceJob[]) => {
    // A job carries every kind's fields; `kind` says which of them to read, and
    // the rest arrive empty. `|| undefined` is what turns an empty one back off.
    const jobs: TaskCard[] = specs
      .filter((j) => j.label)
      .map((j) => ({
        id: rid('t'),
        label: j.label,
        detail: j.detail || undefined,
        status: 'queued' as const,
        kind: j.kind,
        durationMs: TASK_RUN_MS[j.kind],
        summary: j.summary,
        findingValue: j.finding_value || undefined,
        findingFlag: j.finding_flag ?? undefined,
        precedentDeal: j.precedent_deal || undefined,
        precedentResolution: j.precedent_resolution || undefined,
        benchmarkPercentile: j.benchmark_percentile || undefined,
        benchmarkNote: j.benchmark_note || undefined,
        exposureCap: j.exposure_cap || undefined,
        exposureEstimate: j.exposure_estimate || undefined,
        exposureGap: j.exposure_gap || undefined,
        searchScope: j.search_scope || undefined,
        searchExcerpt: j.search_excerpt || undefined,
        researchFinding: j.research_finding || undefined,
        researchSource: j.research_source || undefined,
        researchFlag: j.research_flag ?? undefined,
        memoBody: j.memo_body || undefined,
      }));
    if (!jobs.length) return;

    setTasks((list) => [...list, ...jobs]);

    const setStatus = (id: string, status: TaskStatus) =>
      setTasks((list) => list.map((t) => (t.id === id ? { ...t, status } : t)));

    jobs.forEach((job, i) => {
      const startAt = TASK_LEAD + i * TASK_STEP;
      const runMs = TASK_RUN_MS[job.kind];
      timersRef.current.push(window.setTimeout(() => setStatus(job.id, 'running'), startAt));
      timersRef.current.push(
        window.setTimeout(() => setStatus(job.id, 'done'), startAt + runMs),
      );
    });
  }, []);

  const routeForApproval = useCallback((p: RouteForApproval) => {
    if (!p.title || !p.summary || !p.recommendation || !p.routed_to) return;
    setApprovals((list) => [
      ...list,
      {
        id: rid('ap'),
        title: p.title,
        summary: p.summary,
        amount: p.amount,
        lines: p.lines,
        recommendation: p.recommendation,
        routedTo: p.routed_to,
        status: 'pending',
      },
    ]);
  }, []);

  const setApprovalStatus = useCallback((id: string, status: ApprovalStatus) => {
    setApprovals((list) => list.map((a) => (a.id === id ? { ...a, status } : a)));
  }, []);

  const extractObligations = useCallback((specs: ObligationSpec[]) => {
    const entries: Obligation[] = specs
      .filter((o) => o.label && o.window)
      .map((o) => ({
        id: rid('ob'),
        clauseId: o.clause_id,
        label: o.label,
        window: o.window,
        note: o.note || undefined,
      }));
    if (!entries.length) return;
    setObligations((list) => [...list, ...entries]);
  }, []);

  const handleUiCommand = useCallback(
    (command: string, payload: unknown) => {
      const action = asUiAction(command, payload);
      if (!action) return;
      switch (action.command) {
        case 'point_to_clause':
          pointToClause(action.payload.clause_id, action.payload.reason);
          break;
        case 'add_comment':
          addComment(action.payload);
          break;
        case 'propose_redline':
          addRedline(action.payload);
          break;
        case 'insert_clause':
          addInsertion(action.payload);
          break;
        case 'run_diligence':
          runDiligence(action.payload.jobs);
          break;
        case 'route_for_approval':
          routeForApproval(action.payload);
          break;
        case 'extract_obligations':
          extractObligations(action.payload.obligations);
          break;
        case 'summarize_session': {
          const { headline, highlights, open_items } = action.payload;
          if (headline) setSessionSummary({ headline, highlights, openItems: open_items });
          break;
        }
        default:
          unhandledUiAction(action);
      }
    },
    [
      pointToClause,
      addComment,
      addRedline,
      addInsertion,
      runDiligence,
      routeForApproval,
      extractObligations,
    ],
  );

  const value: LegalStore = {
    clauses: CLAUSES,
    focusedClauseId,
    comments,
    redlines,
    insertions,
    tasks,
    approvals,
    obligations,
    sessionSummary,
    pointer,
    setFocusedClause,
    setApprovalStatus,
    handleUiCommand,
    registerAgentSend,
    sendClauseFocus,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
