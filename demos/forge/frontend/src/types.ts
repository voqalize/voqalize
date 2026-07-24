/**
 * Types for Flowforge — the voice workflow studio.
 *
 * The pitch: an ITSM/HR-ops admin authors a **Service Request Workflow** by
 * talking to a copilot ("Ada"). A workflow is a block-based statechart over a
 * typed context — steps (states) wired by transitions, guarded branches, and an
 * escape hatch to JavaScript — assembled from a governed catalog of connectors.
 *
 * The model is deliberately statechart-shaped so three things fall out of one
 * spec: the vertical-flow editor renders it, a JS-executing interpreter runs it
 * (tests + a live persona simulation), and a coverage linter reads off the
 * `(state, event)` pairs the admin hasn't handled yet.
 *
 * Routing is stored ergonomically (a `next` spine + labelled side-exits + gateway
 * branches) rather than as a flat transition table, because that's what keeps the
 * top-to-bottom flow legible on a projector and easy for the LLM to assemble.
 */

// ─── Catalog: the governed building blocks the admin assembles ──────────────────

/** A block kind the admin can drop into a workflow (the left-rail palette). */
export type StateKind =
  | 'start' // the trigger — a request raised from Teams / Slack / web
  | 'form' // a user task: collect fields from the requester
  | 'approval' // a user task: a person approves or rejects
  | 'service' // a service task: call one connector action
  | 'gateway' // an exclusive branch — guarded transitions
  | 'wait' // a timer / SLA pause
  | 'code' // the escape hatch: run JavaScript
  | 'end'; // a terminal outcome

/** One connector in the governed library (Entra, Intune, Okta, Jira…). */
export interface Connector {
  id: string;
  name: string;
  category: string; // 'Identity', 'Devices', 'ITSM', 'HR', 'Collaboration'…
  icon: string; // one emoji, for the demo
  actions: ConnectorAction[];
}

export interface ConnectorAction {
  id: string;
  label: string; // 'Create user', 'Assign device'…
}

/** A palette entry describing a droppable block kind. */
export interface BlockSpec {
  kind: StateKind;
  label: string;
  icon: string;
  blurb: string;
}

// ─── Typed context: the request's data model (the "metadata") ───────────────────

export type FieldType = 'string' | 'boolean' | 'number' | 'enum' | 'user';

/**
 * One field of the request's context — either collected on a form or **derived**
 * from other fields by a JS expression (e.g. `app.privileged`). Derived fields are
 * what guards read, so an edge condition stays declarative.
 */
export interface ContextField {
  key: string; // dotted, e.g. 'requester.type', 'app.privileged'
  label: string;
  type: FieldType;
  enumValues?: string[];
  derived?: boolean;
  expr?: string; // JS, for derived fields: (ctx) => …
  note?: string;
}

// ─── States (blocks) ────────────────────────────────────────────────────────────

/** A guarded branch out of a gateway. First guard that evaluates truthy wins. */
export interface Branch {
  id: string;
  label: string; // human summary, e.g. 'Contractor + privileged app'
  guard: string; // JS expression over ctx, e.g. ctx.requester.type === 'contractor'
  to: string; // target state id
}

/** One field rendered by a `form` block. */
export interface FormField {
  key: string;
  label: string;
  type: FieldType;
  enumValues?: string[];
}

export interface WorkflowState {
  id: string;
  kind: StateKind;
  label: string;
  subtitle?: string; // one line shown under the label on the block

  // ── routing ──
  next?: string; // the primary continuation (submit / approve / done / unconditional)
  rejectTo?: string; // an approval's reject exit (rendered as a side-exit chip)
  branches?: Branch[]; // gateway only, ordered
  else?: string; // gateway only: default target when no branch guard matches

  // ── kind-specific config ──
  connectorId?: string; // service: which connector
  actionId?: string; // service: which action
  approver?: string; // approval: who signs (e.g. "Reporting manager", "VP, Eng")
  fields?: FormField[]; // form: what it collects
  slaHours?: number; // wait: the SLA / timer
  code?: string; // code: the JS body — the escape hatch
  outcome?: string; // end: e.g. 'Provisioned', 'Rejected', 'Closed'

  /** True for a block the admin just added by voice — pulses briefly, then settles. */
  fresh?: boolean;
}

// ─── The workflow ───────────────────────────────────────────────────────────────

export type WorkflowCategory = 'ITSM' | 'HR' | 'Security';
export type WorkflowStatus = 'draft' | 'published';

export interface Workflow {
  id: string;
  name: string;
  description: string;
  category: WorkflowCategory;
  status: WorkflowStatus;
  version: number;
  /** How this workflow is triggered — the start event, in plain words. */
  trigger: string;
  channels: string[]; // 'Teams', 'Slack', 'Web'
  context: ContextField[];
  states: WorkflowState[];
  startId: string; // id of the 'start' state
  tests: TestCase[];
  /** Coverage gaps the copilot surfaced (unhandled (state,event) pairs). */
  gaps: CoverageGap[];
  updatedLabel: string; // e.g. 'edited just now', '3 days ago'
  runsPerMonth?: number; // vanity stat for the list card
}

// ─── Tests + simulation ─────────────────────────────────────────────────────────

export type TestStatus = 'idle' | 'running' | 'pass' | 'fail';

/**
 * A transition test, exactly the admin's mental model: "the workflow is in this
 * {state} with this {context}, this {event} occurs, I expect to rest in {state}".
 * The runner applies the event, auto-advances through automatic states (gateways,
 * service tasks, code) — executing real JS guards — and compares the resting
 * state to `expectState`.
 */
export interface TestCase {
  id: string;
  name: string;
  givenState: string;
  context: Record<string, unknown>;
  event: string; // 'submit' | 'approve' | 'reject' | …
  expectState: string;
  status: TestStatus;
  actualState?: string; // where the run actually landed
  note?: string;
}

/** A coverage gap the copilot flags — an unhandled event in some state. */
export interface CoverageGap {
  id: string;
  state: string; // state id
  event: string; // the unhandled event, e.g. 'timeout', 'withdrawn'
  question: string; // "What should happen if the VP doesn't respond in 2 days?"
  resolved?: boolean;
}

/** A live persona run — the finale. Walks the flow from start, lighting the path. */
export interface Simulation {
  active: boolean;
  personaLabel: string; // 'Contractor · Figma admin'
  context: Record<string, unknown>;
  path: string[]; // state ids visited, in order (the trail)
  current: string | null; // the currently-lit state
  restedAt: string | null; // final resting state when done
  events: string[]; // the remaining event script
  done: boolean;
}

// ─── Publish / live ─────────────────────────────────────────────────────────────

/** One entry in a published workflow's activity log (admin-facing, not engine-facing). */
export interface HistoryEvent {
  id: number;
  type: string; // 'Published', 'Versioned'…
  detail: string;
  ts: string; // relative label
}

export interface Deployment {
  workflowId: string;
  runId: string; // e.g. 'req-9f2a…'
  version: number;
  status: 'live';
  history: HistoryEvent[];
}

// ─── Constants ──────────────────────────────────────────────────────────────────

export const KIND_META: Record<StateKind, { label: string; icon: string; color: string }> = {
  start: { label: 'Trigger', icon: '⚡', color: '#8B5CF6' },
  form: { label: 'Form', icon: '📝', color: '#38BDF8' },
  approval: { label: 'Approval', icon: '✔', color: '#F59E0B' },
  service: { label: 'Action', icon: '🔌', color: '#34D399' },
  gateway: { label: 'Decision', icon: '◇', color: '#FB7185' },
  wait: { label: 'Wait / SLA', icon: '⏳', color: '#A78BFA' },
  code: { label: 'Script', icon: '{ }', color: '#F472B6' },
  end: { label: 'End', icon: '⬛', color: '#94A3B8' },
};

/** How a field's data type is shown to an admin (not the raw programmer type). */
export const TYPE_LABEL: Record<FieldType, string> = {
  string: 'Text',
  boolean: 'Yes / no',
  number: 'Number',
  enum: 'Choice',
  user: 'User',
};

export const CATEGORY_LABEL: Record<WorkflowCategory, string> = {
  ITSM: 'IT Service',
  HR: 'HR Ops',
  Security: 'Security',
};

/** The events each user-task kind can receive — used by the coverage linter. */
export const KIND_EVENTS: Partial<Record<StateKind, string[]>> = {
  form: ['submit', 'cancel'],
  approval: ['approve', 'reject', 'timeout', 'withdrawn'],
  wait: ['elapsed', 'cancelled'],
};
