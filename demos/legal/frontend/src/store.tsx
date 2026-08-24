/**
 * Shared store for the Docket contract-review demo.
 *
 * One React context drives the document view and the ambient voice layer, so
 * the assistant and the lawyer work the same screen. The assistant mutates
 * state through RTVI's own `ui-command` — the brain's `session.dispatch(...)`
 * arrives as `{ command, payload }` and {@link LegalStore.handleUiCommand} is
 * the one reducer over it: `point_to_clause` scrolls/highlights a clause,
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
import { CLAUSES, CLAUSES_BY_ID, type Clause } from './content';

export type TaskStatus = 'queued' | 'running' | 'done';
export type TaskKind =
  | 'finding'
  | 'precedent'
  | 'benchmark'
  | 'exposure'
  | 'search'
  | 'research'
  | 'memo';
export type FindingFlag = 'ok' | 'warn' | 'risk';
export type ApprovalStatus = 'pending' | 'approved' | 'declined';

export interface Comment {
  id: string;
  clauseId: string;
  text: string;
}

export interface Redline {
  id: string;
  clauseId: string;
  originalExcerpt: string;
  proposedText: string;
  rationale: string;
}

export interface Insertion {
  id: string;
  afterClauseId: string;
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
  clauseId: string;
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
  clauseId: string;
  reason?: string;
  nonce: number;
}

type AgentSend = (type: string, data: Record<string, unknown>) => void;

export interface LegalStore {
  clauses: Clause[];
  focusedClauseId: string | null;
  comments: Comment[];
  redlines: Redline[];
  insertions: Insertion[];
  tasks: TaskCard[];
  approvals: Approval[];
  obligations: Obligation[];
  sessionSummary: SessionSummary | null;
  pointer: PointerEvent_ | null;

  setFocusedClause: (clauseId: string | null) => void;
  setApprovalStatus: (id: string, status: ApprovalStatus) => void;

  /** Replay one `ui-command` onto the screen. Unknown commands are ignored. */
  handleUiCommand: (command: string, payload: Record<string, unknown>) => void;
  registerAgentSend: (fn: AgentSend | null) => void;
  sendClauseFocus: (clauseId: string) => void;
}

const Ctx = createContext<LegalStore | null>(null);

export function useLegal(): LegalStore {
  const v = useContext(Ctx);
  if (!v) throw new Error('useLegal must be used within LegalProvider');
  return v;
}

const str = (v: unknown): string | undefined => (typeof v === 'string' && v ? v : undefined);
const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0);
const arr = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
const strArr = (v: unknown): string[] => arr<unknown>(v).filter((x): x is string => typeof x === 'string' && !!x);
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
  const [focusedClauseId, setFocusedClauseId] = useState<string | null>(null);
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

  const setFocusedClause = useCallback((clauseId: string | null) => {
    setFocusedClauseId(clauseId);
  }, []);

  const registerAgentSend = useCallback((fn: AgentSend | null) => {
    agentSendRef.current = fn;
  }, []);

  const sendClauseFocus = useCallback((clauseId: string) => {
    const clause = CLAUSES_BY_ID[clauseId];
    if (!clause || !agentSendRef.current) return;
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

  const pointToClause = useCallback((clauseId: string, reason?: string) => {
    if (!CLAUSES_BY_ID[clauseId]) return;
    setPointer({ clauseId, reason, nonce: Date.now() });
  }, []);

  const addComment = useCallback((clauseId: string, text: string, id?: string) => {
    if (!CLAUSES_BY_ID[clauseId] || !text) return;
    setComments((list) => [...list, { id: id ?? rid('cm'), clauseId, text }]);
  }, []);

  const addRedline = useCallback(
    (
      clauseId: string,
      originalExcerpt: string,
      proposedText: string,
      rationale: string,
      id?: string,
    ) => {
      if (!CLAUSES_BY_ID[clauseId] || !originalExcerpt || !proposedText) return;
      setRedlines((list) => [
        ...list,
        { id: id ?? rid('rl'), clauseId, originalExcerpt, proposedText, rationale },
      ]);
    },
    [],
  );

  const addInsertion = useCallback(
    (afterClauseId: string, heading: string, proposedText: string, rationale: string, id?: string) => {
      if (!CLAUSES_BY_ID[afterClauseId] || !heading || !proposedText) return;
      setInsertions((list) => [
        ...list,
        { id: id ?? rid('ins'), afterClauseId, heading, proposedText, rationale },
      ]);
    },
    [],
  );

  const runDiligence = useCallback((rawJobs: Record<string, unknown>[]) => {
    const jobs: TaskCard[] = rawJobs
      .filter((j) => str(j.label) && str(j.kind))
      .map((j, i) => ({
        id: str(j.id) ?? `t-${Date.now().toString(36)}-${i}`,
        label: String(j.label),
        detail: str(j.detail),
        status: 'queued' as const,
        kind: str(j.kind) as TaskKind,
        durationMs: TASK_RUN_MS[str(j.kind) as TaskKind] ?? 9000,
        summary: str(j.summary) ?? '',
        findingValue: str(j.finding_value),
        findingFlag: str(j.finding_flag) as FindingFlag | undefined,
        precedentDeal: str(j.precedent_deal),
        precedentResolution: str(j.precedent_resolution),
        benchmarkPercentile: str(j.benchmark_percentile),
        benchmarkNote: str(j.benchmark_note),
        exposureCap: str(j.exposure_cap),
        exposureEstimate: str(j.exposure_estimate),
        exposureGap: str(j.exposure_gap),
        searchScope: str(j.search_scope),
        searchExcerpt: str(j.search_excerpt),
        researchFinding: str(j.research_finding),
        researchSource: str(j.research_source),
        researchFlag: str(j.research_flag) as FindingFlag | undefined,
        memoBody: str(j.memo_body),
      }));
    if (!jobs.length) return;

    setTasks((list) => [...list, ...jobs]);

    const setStatus = (id: string, status: TaskStatus) =>
      setTasks((list) => list.map((t) => (t.id === id ? { ...t, status } : t)));

    jobs.forEach((job, i) => {
      const startAt = TASK_LEAD + i * TASK_STEP;
      const runMs = TASK_RUN_MS[job.kind] ?? 9000;
      timersRef.current.push(window.setTimeout(() => setStatus(job.id, 'running'), startAt));
      timersRef.current.push(
        window.setTimeout(() => setStatus(job.id, 'done'), startAt + runMs),
      );
    });
  }, []);

  const routeForApproval = useCallback((cmd: Record<string, unknown>) => {
    const title = str(cmd.title);
    const summary = str(cmd.summary);
    const recommendation = str(cmd.recommendation);
    const routedTo = str(cmd.routed_to);
    if (!title || !summary || !recommendation || !routedTo) return;
    setApprovals((list) => [
      ...list,
      {
        id: str(cmd.id) ?? rid('ap'),
        title,
        summary,
        amount: num(cmd.amount),
        lines: strArr(cmd.lines),
        recommendation,
        routedTo,
        status: 'pending',
      },
    ]);
  }, []);

  const setApprovalStatus = useCallback((id: string, status: ApprovalStatus) => {
    setApprovals((list) => list.map((a) => (a.id === id ? { ...a, status } : a)));
  }, []);

  const extractObligations = useCallback((rawObligations: Record<string, unknown>[]) => {
    const entries: Obligation[] = rawObligations
      .filter((o) => str(o.clause_id) && CLAUSES_BY_ID[str(o.clause_id) ?? ''] && str(o.label) && str(o.window))
      .map((o, i) => ({
        id: str(o.id) ?? `ob-${Date.now().toString(36)}-${i}`,
        clauseId: String(o.clause_id),
        label: String(o.label),
        window: String(o.window),
        note: str(o.note),
      }));
    if (!entries.length) return;
    setObligations((list) => [...list, ...entries]);
  }, []);

  const handleUiCommand = useCallback(
    (command: string, payload: Record<string, unknown>) => {
      const p = payload;
      switch (command) {
        case 'point_to_clause':
          if (str(p.clause_id)) pointToClause(str(p.clause_id)!, str(p.reason));
          break;
        case 'add_comment':
          if (str(p.clause_id) && str(p.text))
            addComment(str(p.clause_id)!, str(p.text)!, str(p.id));
          break;
        case 'propose_redline':
          if (str(p.clause_id) && str(p.original_excerpt) && str(p.proposed_text))
            addRedline(
              str(p.clause_id)!,
              str(p.original_excerpt)!,
              str(p.proposed_text)!,
              str(p.rationale) ?? '',
              str(p.id),
            );
          break;
        case 'insert_clause':
          if (str(p.after_clause_id) && str(p.heading) && str(p.proposed_text))
            addInsertion(
              str(p.after_clause_id)!,
              str(p.heading)!,
              str(p.proposed_text)!,
              str(p.rationale) ?? '',
              str(p.id),
            );
          break;
        case 'run_diligence':
          runDiligence(arr<Record<string, unknown>>(p.jobs));
          break;
        case 'route_for_approval':
          routeForApproval(p);
          break;
        case 'extract_obligations':
          extractObligations(arr<Record<string, unknown>>(p.obligations));
          break;
        case 'summarize_session':
          if (str(p.headline))
            setSessionSummary({
              headline: str(p.headline)!,
              highlights: strArr(p.highlights),
              openItems: strArr(p.open_items),
            });
          break;
        default:
          break;
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
