/**
 * Types for the Meridian Servicing Console demo.
 *
 * A mortgage-servicing advisor works a queue of cases on an internal bank
 * console. Each case is a Jira-like ticket with a stage, a priority, and an
 * assignee (a person or a department). The voice "servicing desk" assistant
 * drives the same screen: it opens cases, switches tabs, routes cases between
 * desks, prepares a case in the background (jobs that animate to completion),
 * and drafts maker-checker approvals the advisor signs off on.
 *
 * **The wire shapes are not written here.** `actions.gen.ts` is generated from
 * the brain's `Action` classes by `voqalize types`, and the closed vocabularies
 * below are read off it rather than typed out a second time. The screen types
 * proper stay hand-written on purpose: a `Job` has a `status` the wire never
 * carries, a `Blocker` can be resolved, a `PacketSection` is approved. What the
 * desk sends is a specification; what the console holds is a thing with a life.
 */

import type {
  ApprovalSpec,
  BlockerSpec,
  FindingSpec,
  MoveCase,
  SetTab,
} from './actions.gen';

export type Stage = MoveCase['stage'];

export type CaseType =
  | 'rate_change'
  | 'early_closure'
  | 'document_request'
  | 'payment_dispute'
  | 'hardship'
  | 'insurance_update';

export type Priority = 'low' | 'normal' | 'high' | 'urgent';

export type DepartmentId = 'pricing' | 'closures' | 'legal' | 'insurance' | 'compliance';

export type CaseTab = SetTab['tab'];

export type View = 'board' | 'case';

export type ApprovalKind = ApprovalSpec['kind'];

export type JobStatus = 'queued' | 'running' | 'done' | 'blocked';
export type ApprovalStatus = 'pending' | 'approved' | 'declined' | 'blocked';

/** How a workup finding reads: a plain fact, a reconciliation worth noticing, or info. */
export type FindingFlag = FindingSpec['flag'];
export type BlockerSeverity = BlockerSpec['severity'];
export type BlockerStatus = 'open' | 'resolved';
export type PacketStatus = 'draft' | 'ready' | 'submitting' | 'submitted';
export type PacketSectionStatus = 'ready' | 'blocked' | 'approved';

export interface Person {
  id: string;
  name: string;
  role: string;
  initials: string;
}

export interface Department {
  id: DepartmentId;
  label: string;
}

export interface Assignee {
  kind: 'person' | 'department';
  id: string; // person id or department id
  label: string; // display name
}

export interface Customer {
  name: string;
  segment: string; // e.g. 'Private Client', 'Premier'
  loanId: string;
  product: string; // e.g. '30-yr fixed home loan'
  balance: number;
  rate: number; // annual %, e.g. 7.1
  monthlyPayment: number;
  property: string; // city, state
  tenureYears: number;
  since: string; // e.g. '2014'
}

/** A background prep step the assistant ran for a case. */
export interface Job {
  id: string;
  label: string;
  detail?: string;
  status: JobStatus;
}

/** A maker-checker draft awaiting the advisor's approval. */
export interface Approval {
  id: string;
  title: string;
  kind: ApprovalKind;
  summary: string;
  lines: string[];
  amount?: number;
  recommendation?: string;
  status: ApprovalStatus;
  /** Why this draft can't be approved yet (set when status === 'blocked'). */
  blockedReason?: string;
}

/**
 * A single line the desk assembled or reconciled during a case "workup" — the
 * cross-system legwork the advisor would otherwise do by hand. A `warn` flag
 * marks a reconciliation the advisor would likely have missed.
 */
export interface Finding {
  id: string;
  label: string;
  value: string;
  flag?: FindingFlag;
}

/**
 * A risk the workup caught that blocks (or warns against) a regulated step — the
 * thing desktop navigation never surfaces because you didn't know to look.
 */
export interface Blocker {
  id: string;
  title: string;
  detail: string;
  severity: BlockerSeverity;
  /** Department to route to in order to clear it, e.g. 'Legal & Custody'. */
  suggestedRoute?: string;
  status: BlockerStatus;
  resolvedNote?: string;
}

export interface PacketField {
  label: string;
  value: string;
  mono?: boolean;
}

/** One section of a multi-step regulated packet (form). */
export interface PacketSection {
  id: string;
  title: string;
  fields: PacketField[];
  status: PacketSectionStatus;
  blockedReason?: string;
}

/**
 * A multi-step regulated form (e.g. an early-closure packet). The desk fills it
 * from the workup, the advisor approves it, and the system submits it — a
 * server-side action gated behind approval and any open blocker.
 */
export interface Packet {
  id: string;
  title: string;
  summary?: string;
  sections: PacketSection[];
  status: PacketStatus;
  submittedTo?: string;
}

/** A past (closed/archived) case surfaced by a server-side precedent search. */
export interface PrecedentResult {
  ref: string;
  customer: string;
  summary: string;
  resolution: string;
  days?: number;
}

/** The result of a server-side archive search — institutional memory on demand. */
export interface ArchiveSearch {
  query: string;
  status: 'searching' | 'done';
  results: PrecedentResult[];
}

export interface ActivityEntry {
  id: string;
  ts: number;
  actor: 'agent' | 'advisor' | 'system';
  text: string;
}

/**
 * A free-text note left on a case. Unlike the activity log (an automatic audit
 * trail), a comment is authored — the advisor or the desk writing context,
 * typically when handing a case to another department.
 */
export interface Comment {
  id: string;
  ts: number;
  author: string; // display name
  authorKind: 'advisor' | 'agent';
  text: string;
  /** Department this note is about (set when the note accompanies a routing). */
  dept?: DepartmentId;
  deptLabel?: string;
}

/** A payment-history row (for the Payments tab). */
export interface PaymentRow {
  date: string;
  amount: number;
  principal: number;
  interest: number;
  escrow: number;
  note?: string;
}

/** A held document (for the Documents tab). */
export interface DocRow {
  name: string;
  kind: string;
  status: 'held' | 'ready' | 'released' | 'pending' | 'open';
}

export interface Case {
  id: string;
  ref: string; // 'MS-1042'
  type: CaseType;
  title: string;
  customer: Customer;
  stage: Stage;
  priority: Priority;
  assignee: Assignee;
  openedDays: number; // days since opened
  slaHours: number;
  summary: string;
  request: string; // what the customer asked for, in plain words
  /** True while the assistant is actively preparing this case in the background. */
  preparing: boolean;
  prepSummary?: string;
  jobs: Job[];
  /** The desk's assembled workup: cross-system facts + reconciliations. */
  findings: Finding[];
  /** A risk the workup caught that gates a regulated step (null if none). */
  blocker: Blocker | null;
  /** The regulated packet/form the desk filled for this case (null if none). */
  packet: Packet | null;
  approvals: Approval[];
  activity: ActivityEntry[];
  /** Authored notes on the case — handoff context, routing rationale, reminders. */
  comments: Comment[];
  payments: PaymentRow[];
  documents: DocRow[];
}

export interface Workspace {
  advisor: Person;
  team: Person[];
  departments: Department[];
  cases: Case[];
}

export const STAGE_LABEL: Record<Stage, string> = {
  new: 'New',
  in_progress: 'In progress',
  needs_approval: 'Needs approval',
  with_dept: 'With department',
  done: 'Done',
};

export const STAGE_ORDER: Stage[] = [
  'new',
  'in_progress',
  'needs_approval',
  'with_dept',
  'done',
];

export const CASE_TYPE_LABEL: Record<CaseType, string> = {
  rate_change: 'Rate change',
  early_closure: 'Loan closure',
  document_request: 'Document request',
  payment_dispute: 'Payment dispute',
  hardship: 'Payment relief',
  insurance_update: 'Insurance update',
};

export const PRIORITY_LABEL: Record<Priority, string> = {
  low: 'Low',
  normal: 'Normal',
  high: 'High',
  urgent: 'Urgent',
};

export function currency(n: number | undefined): string {
  if (n == null || Number.isNaN(n)) return '—';
  return n.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  });
}
