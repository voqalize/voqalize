/**
 * Flowforge store — the brain of the demo UI.
 *
 * It owns the workflow model and everything the copilot ("Ada") drives by voice:
 *   • a tiny **statechart interpreter** that actually executes JS guards / code, so
 *     the test-run and the finale persona simulation are real proofs, not theatre;
 *   • the **edit ops** (add a block, insert a branch, set code, add a field…);
 *   • the **test runner** and a **coverage linter** that reads off unhandled
 *     (state, event) pairs;
 *   • **publish → live**, which mints a running instance with a durable history.
 *
 * The voice contract is one method: `handleUiCommand(name, payload)` maps a brain
 * tool call to an op; `snapshot()` sends the workspace back so the LLM stays
 * grounded; `registerAgentSend` lets the UI push state on change.
 */

import { createContext, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import { ADMIN, CONNECTORS, SEED_WORKFLOWS, connectorActionLabel } from './data';
import {
  KIND_EVENTS,
  type Branch,
  type ContextField,
  type CoverageGap,
  type Deployment,
  type HistoryEvent,
  type Simulation,
  type TestCase,
  type Workflow,
  type WorkflowState,
} from './types';

// ─── Interpreter ────────────────────────────────────────────────────────────────
// A state is either *automatic* (runs and advances on its own) or a *stop* (rests
// waiting for an event, or is terminal). This split is what makes the vertical
// flow, the tests, and the persona run all fall out of one spec.

const STOP_KINDS = new Set(['form', 'approval', 'wait', 'end']);
const isStop = (s?: WorkflowState) => !!s && STOP_KINDS.has(s.kind);

/** Expand flat dotted context (`{'requester.type':'contractor'}`) into a nested object. */
function setPath(obj: Record<string, any>, dotted: string, val: unknown): void {
  const parts = dotted.split('.');
  let o = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    if (typeof o[parts[i]] !== 'object' || o[parts[i]] === null) o[parts[i]] = {};
    o = o[parts[i]];
  }
  o[parts[parts.length - 1]] = val;
}

function evalExpr(js: string, ctx: unknown): unknown {
  // eslint-disable-next-line no-new-func
  return Function('ctx', `"use strict"; return (${js});`)(ctx);
}
function runCode(js: string, ctx: unknown): unknown {
  // eslint-disable-next-line no-new-func
  const out = Function('ctx', `"use strict"; ${js}`)(ctx);
  return out === undefined ? ctx : out;
}

/** Build the runtime context object from a test's flat context + the derived fields. */
function buildCtx(flat: Record<string, unknown>, fields: ContextField[]): Record<string, any> {
  const ctx: Record<string, any> = {};
  for (const [k, v] of Object.entries(flat || {})) setPath(ctx, k, v);
  for (const f of fields) {
    if (f.derived && f.expr) {
      try {
        setPath(ctx, f.key, evalExpr(f.expr, ctx));
      } catch {
        /* leave derived field unset if the expr throws */
      }
    }
  }
  return ctx;
}

function stateById(wf: Workflow, id?: string | null): WorkflowState | undefined {
  return wf.states.find((s) => s.id === id);
}

/** Coerce a context payload that may arrive as a JSON string (from the brain). */
function asContext(v: unknown): Record<string, unknown> {
  if (typeof v === 'string') {
    try {
      const parsed = JSON.parse(v);
      return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : {};
    } catch {
      return {};
    }
  }
  return (v as Record<string, unknown>) || {};
}

/**
 * Trace the resting position starting *at* `fromId`, executing automatic states
 * (start → next, service → next, code → run then next, gateway → first truthy
 * guard). Returns every state id visited, ending at the stop/terminal state.
 */
function trace(wf: Workflow, fromId: string | undefined, ctx: Record<string, any>): string[] {
  const path: string[] = [];
  let id = fromId;
  let guardStop = 0;
  while (id && guardStop++ < 64) {
    const s = stateById(wf, id);
    if (!s) break;
    path.push(id);
    if (isStop(s)) break; // rest here (form/approval/wait) or terminal (end)
    if (s.kind === 'code' && s.code) {
      try {
        runCode(s.code, ctx);
      } catch {
        /* a throwing code block just falls through to next in the demo */
      }
    }
    if (s.kind === 'gateway') {
      let target = s.else;
      for (const b of s.branches ?? []) {
        try {
          if (evalExpr(b.guard, ctx)) {
            target = b.to;
            break;
          }
        } catch {
          /* a throwing guard is treated as false */
        }
      }
      id = target;
      continue;
    }
    id = s.next; // start / service
  }
  return path;
}

/** Route a user-task event to its target state id (null = unhandled → a gap). */
function applyEvent(wf: Workflow, s: WorkflowState, event: string): string | null {
  switch (s.kind) {
    case 'form':
      if (event === 'submit') return s.next ?? null;
      if (event === 'cancel') return s.rejectTo ?? null;
      return null;
    case 'approval':
      if (event === 'approve') return s.next ?? null;
      if (event === 'reject') return s.rejectTo ?? null;
      if (event === 'timeout' || event === 'withdrawn') return s.rejectTo ?? null;
      return null;
    case 'wait':
      if (event === 'elapsed') return s.next ?? null;
      if (event === 'cancelled') return s.rejectTo ?? null;
      return null;
    default:
      return null;
  }
}

/** Run one transition test → the full visited path + resting state. */
function runTransition(
  wf: Workflow,
  givenState: string,
  event: string,
  flatCtx: Record<string, unknown>,
): { path: string[]; restedAt: string | null } {
  const ctx = buildCtx(flatCtx, wf.context);
  const given = stateById(wf, givenState);
  if (!given) return { path: [], restedAt: null };

  // A stop-state receives its event; an automatic/start state treats the event as
  // a kickoff and simply advances.
  let path: string[] = [];
  let seed: string | undefined;
  if (isStop(given) && given.kind !== 'end') {
    const target = applyEvent(wf, given, event);
    path = [givenState];
    if (target == null) return { path, restedAt: null }; // unhandled
    seed = target;
  } else {
    seed = givenState;
  }
  const rest = trace(wf, seed, ctx);
  path = path.concat(rest);
  return { path, restedAt: path.length ? path[path.length - 1] : null };
}

// ─── Store ───────────────────────────────────────────────────────────────────────

export type View = 'list' | 'editor';
export type Panel = 'flow' | 'code' | 'tests' | 'runtime';

/**
 * Voice presence, mirrored from the SDK session into the store so the ambient
 * glow (the full-viewport "Ada is present" ring) and the header presence control
 * both read it. `connectionState` uses the desk vocabulary (`live`), not the
 * transport's `connected`.
 */
export type BotState = 'idle' | 'listening' | 'thinking' | 'speaking';
export type ConnStatus = 'idle' | 'connecting' | 'live' | 'error';

/**
 * The **activity feed** — Ada narrates her work in *actions*, not words. Every
 * ui_command (voice-driven or a manual click) becomes one short "task" row that
 * lights up `active` and settles to `done`, so a spoken request is acknowledged
 * on screen the instant she acts. It is the concrete companion to the ambient
 * glow: the ring says "Ada is present", the feed says "here's exactly what she's
 * doing". Navigation-only commands (panel/tab/highlight) don't earn a row.
 */
export interface ActivityItem {
  id: string;
  label: string; // the mono "machine" line, e.g. "Adding a decision"
  detail?: string; // the plain-language object, e.g. "Contractor + privileged app"
  status: 'active' | 'done';
  ts: number;
}

/** How each ui_command reads as a task line — null means "too minor to show". */
const ACTIVITY_KIND_WORD: Record<string, string> = {
  form: 'a form',
  approval: 'an approval',
  service: 'an action',
  wait: 'a timer',
  code: 'a script',
  end: 'an end step',
  gateway: 'a decision',
};

function activityFor(action: string, p: Record<string, any>): { label: string; detail?: string } | null {
  const s = (v: unknown): string | undefined => (v == null || v === '' ? undefined : String(v));
  switch (action) {
    case 'create_workflow':
      return { label: 'Creating a workflow', detail: s(p.name) };
    case 'open_workflow':
      return { label: 'Opening the workflow' };
    case 'open_list':
      return { label: 'Back to workflows' };
    case 'add_state':
    case 'add_step':
      return { label: `Adding ${ACTIVITY_KIND_WORD[p.kind] ?? 'a step'}`, detail: s(p.label) };
    case 'insert_gateway':
    case 'insert_branch':
      return { label: 'Adding a decision', detail: s(p.label) };
    case 'add_branch':
      return { label: 'Adding a branch', detail: s(p.label) };
    case 'set_route':
      return { label: 'Rewiring the routing' };
    case 'update_state':
    case 'update_step':
      return { label: 'Updating a step', detail: s(p.label) };
    case 'remove_state':
    case 'remove_step':
      return { label: 'Removing a step' };
    case 'add_context_field':
      return { label: 'Adding a field', detail: s(p.label ?? p.key) };
    case 'add_field':
      return { label: 'Adding a form field', detail: s(p.field?.label ?? p.field?.key) };
    case 'set_code':
      return { label: 'Writing the logic' };
    case 'add_test':
      return { label: 'Adding a test', detail: s(p.name) };
    case 'run_tests':
      return { label: 'Running the tests' };
    case 'review_coverage':
      return { label: 'Scanning for gaps' };
    case 'resolve_gap':
      return { label: 'Closing a gap' };
    case 'run_scenario':
      return { label: 'Simulating', detail: s(p.personaLabel) };
    case 'publish_workflow':
      return { label: 'Publishing live' };
    case 'show_code':
      return { label: 'Revealing the code' };
    default:
      return null; // set_panel, focus_state/select_block — no noise
  }
}

interface Model {
  admin: typeof ADMIN;
  workflows: Workflow[];
  view: View;
  activeId: string | null;
  panel: Panel;
  selectedId: string | null; // focused block
  codeStateId: string | null; // which block's JS is shown in the code viewer
  sim: Simulation | null;
  deployment: Deployment | null;
  rev: number; // bumps whenever the brain should re-ground
}

let seq = 1000;
const nextSeq = () => ++seq;

function freshModel(): Model {
  return {
    admin: ADMIN,
    workflows: SEED_WORKFLOWS.map((w) => structuredClone(w)),
    view: 'list',
    activeId: null,
    panel: 'flow',
    selectedId: null,
    codeStateId: null,
    sim: null,
    deployment: null,
    rev: 0,
  };
}

/** The agent-send channel: `(type, data)` → an RTVI app message to the brain. */
export type AgentSend = (type: string, data: Record<string, unknown>) => void;

export interface ForgeStore {
  model: Model;
  active: Workflow | null;
  connectors: typeof CONNECTORS;
  // voice presence (mirrored from the live session)
  botState: BotState;
  connectionState: ConnStatus;
  setBotState: (s: BotState) => void;
  setConnectionState: (s: ConnStatus) => void;
  // the live activity feed (what Ada is doing right now)
  activities: ActivityItem[];
  // navigation
  openList: () => void;
  openWorkflow: (id: string) => void;
  setPanel: (p: Panel) => void;
  focusState: (id: string | null) => void;
  showCode: (id: string | null) => void;
  /** Convenience for the UI's own buttons — dispatches like a brain command. */
  dispatch: (action: string, payload?: Record<string, any>) => void;
  // the voice contract
  handleUiCommand: (cmd: Record<string, any>) => void;
  snapshot: () => Record<string, unknown>;
  registerAgentSend: (fn: AgentSend | null) => void;
}

const Ctx = createContext<ForgeStore | null>(null);
export const useForge = (): ForgeStore => {
  const s = useContext(Ctx);
  if (!s) throw new Error('useForge outside provider');
  return s;
};

export function ForgeProvider({ children }: { children: ReactNode }) {
  const ref = useRef<Model>(freshModel());
  const [tick, setTick] = useState(0);
  const [botState, setBotState] = useState<BotState>('idle');
  const [connectionState, setConnectionState] = useState<ConnStatus>('idle');
  const sendRef = useRef<AgentSend | null>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  // Activity-feed timers live in their own pool so a clearTimers() inside an op
  // (run_tests / run_scenario / publish all reset the model's animation timers)
  // never strands a task row as perpetually "active".
  const activitiesRef = useRef<ActivityItem[]>([]);
  const actTimers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const render = () => setTick((t) => t + 1);
  const clearTimers = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };
  const later = (fn: () => void, ms: number) => {
    timers.current.push(setTimeout(fn, ms));
  };
  const laterAct = (fn: () => void, ms: number) => {
    actTimers.current.push(setTimeout(fn, ms));
  };

  // ── the activity feed ──
  const pushActivity = (label: string, detail?: string): string => {
    const id = `act_${nextSeq()}`;
    const arr = activitiesRef.current;
    arr.push({ id, label, detail, status: 'active', ts: Date.now() });
    // keep the stack tight — only the most recent handful ever show
    if (arr.length > 6) activitiesRef.current = arr.slice(-6);
    render();
    return id;
  };
  const completeActivity = (id: string) => {
    const item = activitiesRef.current.find((a) => a.id === id);
    if (!item || item.status === 'done') return;
    item.status = 'done';
    render();
    // let it rest as "done" for a beat, then fade it out of the stack
    laterAct(() => {
      activitiesRef.current = activitiesRef.current.filter((a) => a.id !== id);
      render();
    }, 3200);
  };
  /** How long a task row stays "active" — matched to the op's own on-screen beat. */
  const activityDuration = (action: string): number => {
    if (action === 'run_tests') return 220 * (activeWf()?.tests.length ?? 0) + 550;
    if (action === 'run_scenario') return 620 * ((ref.current.sim?.path.length ?? 5) + 1) + 300;
    if (action === 'publish_workflow') return 950;
    if (action === 'review_coverage') return 800;
    return 620;
  };

  const activeWf = (): Workflow | null => {
    const m = ref.current;
    return m.workflows.find((w) => w.id === m.activeId) ?? null;
  };

  /** Bump rev so the widget re-pushes state_sync, then re-render. */
  const commit = () => {
    ref.current.rev++;
    render();
  };

  // ── navigation ──
  const openList = () => {
    clearTimers();
    ref.current.view = 'list';
    ref.current.activeId = null;
    ref.current.sim = null;
    commit();
  };
  const openWorkflow = (id: string) => {
    clearTimers();
    const m = ref.current;
    if (!m.workflows.some((w) => w.id === id)) return;
    m.view = 'editor';
    m.activeId = id;
    m.panel = 'flow';
    m.selectedId = null;
    m.codeStateId = null;
    m.sim = null;
    m.deployment = null;
    commit();
  };
  const setPanel = (p: Panel) => {
    ref.current.panel = p;
    commit();
  };
  const focusState = (id: string | null) => {
    ref.current.selectedId = id;
    render();
  };
  const showCode = (id: string | null) => {
    ref.current.codeStateId = id;
    if (id) ref.current.panel = 'code';
    commit();
  };

  // ── edit ops ──
  const markFresh = (wf: Workflow, id: string) => {
    const s = stateById(wf, id);
    if (s) s.fresh = true;
    later(() => {
      const st = stateById(wf, id);
      if (st) st.fresh = false;
      render();
    }, 2200);
  };

  const touch = (wf: Workflow) => {
    wf.updatedLabel = 'edited just now';
    if (wf.status === 'published') wf.status = 'draft';
  };

  const createWorkflow = (p: Record<string, any>) => {
    const id = String(p.id || `wf-${nextSeq()}`);
    const startId = `${id}_start`;
    const endId = `${id}_done`;
    const wf: Workflow = {
      id,
      name: String(p.name || 'Untitled workflow'),
      description: String(p.description || ''),
      category: (p.category as Workflow['category']) || 'ITSM',
      status: 'draft',
      version: 1,
      trigger: String(p.trigger || 'A request is raised'),
      channels: Array.isArray(p.channels) ? p.channels.map(String) : ['Teams', 'Web'],
      runsPerMonth: 0,
      updatedLabel: 'new draft',
      context: Array.isArray(p.context) ? (p.context as ContextField[]) : [],
      startId,
      states: [
        { id: startId, kind: 'start', label: String(p.trigger || 'Request raised'), next: endId },
        { id: endId, kind: 'end', label: 'Done', outcome: 'Complete' },
      ],
      tests: [],
      gaps: [],
    };
    ref.current.workflows.unshift(wf);
    openWorkflow(id);
  };

  /** Insert a new state into the linear spine after `after` (rewiring next). */
  const addState = (p: Record<string, any>) => {
    const wf = activeWf();
    if (!wf) return;
    const id = String(p.id || `s_${nextSeq()}`);
    const st: WorkflowState = {
      id,
      kind: p.kind,
      label: String(p.label || 'Step'),
      subtitle: p.subtitle ? String(p.subtitle) : undefined,
      connectorId: p.connectorId,
      actionId: p.actionId,
      approver: p.approver,
      fields: p.fields,
      code: p.code,
      slaHours: p.slaHours,
      outcome: p.outcome,
      next: p.next,
      rejectTo: p.rejectTo,
    };
    if (p.after) {
      const prev = stateById(wf, String(p.after));
      if (prev) {
        if (st.next === undefined) st.next = prev.next;
        prev.next = id;
      }
    }
    wf.states.push(st);
    touch(wf);
    ref.current.selectedId = id;
    if (st.kind === 'code' && st.code) ref.current.codeStateId = id;
    markFresh(wf, id);
    commit();
  };

  /** THE HERO EDIT: splice an exclusive gateway in after `after`. */
  const insertGateway = (p: Record<string, any>) => {
    const wf = activeWf();
    if (!wf) return;
    const after = stateById(wf, String(p.after));
    if (!after) return;
    const id = String(p.id || `g_${nextSeq()}`);
    const branches: Branch[] = (p.branches ?? []).map((b: any, i: number) => ({
      id: `b_${nextSeq()}_${i}`,
      label: String(b.label || 'Branch'),
      guard: String(b.guard || 'true'),
      to: String(b.to),
    }));
    const gate: WorkflowState = {
      id,
      kind: 'gateway',
      label: String(p.label || 'Branch'),
      subtitle: p.subtitle ? String(p.subtitle) : undefined,
      branches,
      else: p.else ? String(p.else) : after.next, // default path = what came next
    };
    after.next = id;
    wf.states.push(gate);
    touch(wf);
    ref.current.selectedId = id;
    markFresh(wf, id);
    commit();
  };

  const addBranch = (p: Record<string, any>) => {
    const wf = activeWf();
    if (!wf) return;
    const gate = stateById(wf, String(p.gateway));
    if (!gate || gate.kind !== 'gateway') return;
    gate.branches = gate.branches ?? [];
    gate.branches.push({
      id: `b_${nextSeq()}`,
      label: String(p.label || 'Branch'),
      guard: String(p.guard || 'true'),
      to: String(p.to),
    });
    touch(wf);
    ref.current.selectedId = gate.id;
    commit();
  };

  const setRoute = (p: Record<string, any>) => {
    const wf = activeWf();
    if (!wf) return;
    const s = stateById(wf, String(p.state));
    if (!s) return;
    if (p.next !== undefined) s.next = p.next ? String(p.next) : undefined;
    if (p.rejectTo !== undefined) s.rejectTo = p.rejectTo ? String(p.rejectTo) : undefined;
    if (p.else !== undefined) s.else = p.else ? String(p.else) : undefined;
    touch(wf);
    commit();
  };

  const updateState = (p: Record<string, any>) => {
    const wf = activeWf();
    if (!wf) return;
    const s = stateById(wf, String(p.id));
    if (!s) return;
    for (const k of ['label', 'subtitle', 'connectorId', 'actionId', 'approver', 'slaHours', 'outcome'] as const) {
      if (p[k] !== undefined) (s as any)[k] = p[k];
    }
    touch(wf);
    ref.current.selectedId = s.id;
    commit();
  };

  const removeState = (p: Record<string, any>) => {
    const wf = activeWf();
    if (!wf) return;
    const id = String(p.id);
    // heal the spine: anyone pointing at `id` skips to its next
    const gone = stateById(wf, id);
    const to = gone?.next;
    for (const s of wf.states) {
      if (s.next === id) s.next = to;
      if (s.rejectTo === id) s.rejectTo = to;
      if (s.else === id) s.else = to;
      if (s.branches) s.branches = s.branches.filter((b) => b.to !== id);
    }
    wf.states = wf.states.filter((s) => s.id !== id);
    touch(wf);
    ref.current.selectedId = null;
    commit();
  };

  const addContextField = (p: Record<string, any>) => {
    const wf = activeWf();
    if (!wf) return;
    wf.context.push({
      key: String(p.key),
      label: String(p.label || p.key),
      type: p.type || 'string',
      enumValues: p.enumValues,
      derived: !!p.derived,
      expr: p.expr,
      note: p.note,
    });
    touch(wf);
    commit();
  };

  const addField = (p: Record<string, any>) => {
    const wf = activeWf();
    if (!wf) return;
    const s = stateById(wf, String(p.state));
    if (!s) return;
    s.fields = s.fields ?? [];
    s.fields.push({
      key: String(p.field?.key),
      label: String(p.field?.label || p.field?.key),
      type: p.field?.type || 'string',
      enumValues: p.field?.enumValues,
    });
    touch(wf);
    ref.current.selectedId = s.id;
    commit();
  };

  const setCode = (p: Record<string, any>) => {
    const wf = activeWf();
    if (!wf) return;
    const s = stateById(wf, String(p.state));
    if (!s) return;
    s.code = String(p.code || '');
    if (s.kind !== 'code' && s.kind !== 'gateway') s.kind = 'code';
    touch(wf);
    ref.current.selectedId = s.id;
    ref.current.codeStateId = s.id;
    ref.current.panel = 'code';
    commit();
  };

  // ── tests ──
  const addTest = (p: Record<string, any>) => {
    const wf = activeWf();
    if (!wf) return;
    const t: TestCase = {
      id: `t_${nextSeq()}`,
      name: String(p.name || 'Test'),
      givenState: String(p.givenState),
      context: asContext(p.context),
      event: String(p.event),
      expectState: String(p.expectState),
      status: 'idle',
    };
    wf.tests.push(t);
    touch(wf);
    ref.current.panel = 'tests';
    commit();
  };

  const runTests = () => {
    const wf = activeWf();
    if (!wf) return;
    clearTimers();
    ref.current.panel = 'tests';
    wf.tests.forEach((t) => (t.status = 'idle'));
    commit();
    wf.tests.forEach((t, i) => {
      later(() => {
        t.status = 'running';
        render();
      }, 220 * i + 120);
      later(() => {
        const { restedAt } = runTransition(wf, t.givenState, t.event, t.context);
        t.actualState = restedAt ?? undefined;
        t.status = restedAt === t.expectState ? 'pass' : 'fail';
        commit();
      }, 220 * i + 360);
    });
  };

  // ── coverage linter ──
  const reviewCoverage = (p: Record<string, any>) => {
    const wf = activeWf();
    if (!wf) return;
    // If the copilot handed us questions, use them; else derive from unhandled pairs.
    let gaps: CoverageGap[] = [];
    if (Array.isArray(p.gaps) && p.gaps.length) {
      gaps = p.gaps.map((g: any) => ({
        id: `gap_${nextSeq()}`,
        state: String(g.state),
        event: String(g.event),
        question: String(g.question),
      }));
    } else {
      for (const s of wf.states) {
        const events = KIND_EVENTS[s.kind];
        if (!events) continue;
        for (const ev of events) {
          if (applyEvent(wf, s, ev) == null) {
            gaps.push({ id: `gap_${nextSeq()}`, state: s.id, event: ev, question: gapQuestion(s, ev) });
          }
        }
      }
    }
    wf.gaps = gaps;
    ref.current.panel = 'tests';
    commit();
  };

  const resolveGap = (p: Record<string, any>) => {
    const wf = activeWf();
    if (!wf) return;
    const g = wf.gaps.find((x) => x.id === p.id || (x.state === p.state && x.event === p.event));
    if (g) g.resolved = true;
    commit();
  };

  // ── persona run (the finale) ──
  const runScenario = (p: Record<string, any>) => {
    const wf = activeWf();
    if (!wf) return;
    clearTimers();
    const flatCtx = asContext(p.context);
    const events: string[] = Array.isArray(p.events) ? p.events.map(String) : [];
    const ctx = buildCtx(flatCtx, wf.context);

    // Walk the full path across each event in the script.
    const full: string[] = [];
    let seed: string | undefined = wf.startId;
    let leg = trace(wf, seed, ctx);
    full.push(...leg);
    for (const ev of events) {
      const restAt = leg[leg.length - 1];
      const s = stateById(wf, restAt);
      if (!s || s.kind === 'end') break;
      const target = applyEvent(wf, s, ev);
      if (target == null) break;
      leg = trace(wf, target, ctx);
      full.push(...leg);
    }

    ref.current.panel = 'flow';
    ref.current.sim = {
      active: true,
      personaLabel: String(p.personaLabel || 'Persona'),
      context: flatCtx,
      path: full,
      current: full[0] ?? null,
      restedAt: null,
      events,
      done: false,
    };
    ref.current.selectedId = null;
    commit();

    // Reveal the trail one node at a time.
    full.forEach((id, i) => {
      later(() => {
        const sim = ref.current.sim;
        if (!sim) return;
        sim.current = id;
        if (i === full.length - 1) {
          sim.restedAt = id;
          sim.done = true;
        }
        render();
      }, 620 * (i + 1));
    });
  };

  // ── publish → live ──
  const publishWorkflow = () => {
    const wf = activeWf();
    if (!wf) return;
    clearTimers();
    wf.status = 'published';
    wf.version += 1;
    wf.updatedLabel = 'published just now';
    const runId = `req-${(nextSeq() * 7).toString(16)}-${wf.id.slice(0, 4)}`;
    const history: HistoryEvent[] = [
      { id: 1, type: 'Published', detail: `${wf.name} v${wf.version} is live`, ts: 'just now' },
      { id: 2, type: 'Versioned', detail: 'Requests already in progress finish on their previous version', ts: 'just now' },
    ];
    ref.current.deployment = { workflowId: wf.id, runId, version: wf.version, status: 'live', history };
    ref.current.panel = 'runtime';
    commit();
  };

  // ── the voice contract ──
  // A ui_command arrives as one flat object: `{ action, ...payload }`. The whole
  // object is handed to each op (they read the keys they need).
  const dispatch = (action: string, payload: Record<string, any> = {}) => {
    // Acknowledge on screen the moment the command lands: paint a task row, run
    // the op, then settle the row to "done" on the op's own beat.
    const desc = activityFor(action, payload);
    if (desc) {
      const id = pushActivity(desc.label, desc.detail);
      runOp(action, payload);
      laterAct(() => completeActivity(id), activityDuration(action));
      return;
    }
    runOp(action, payload);
  };

  const runOp = (action: string, payload: Record<string, any> = {}) => {
    switch (action) {
      case 'open_list':
        return openList();
      case 'open_workflow':
        return openWorkflow(String(payload.id));
      case 'create_workflow':
        return createWorkflow(payload);
      case 'add_state':
      case 'add_step':
        return addState(payload);
      case 'insert_gateway':
      case 'insert_branch':
        return insertGateway(payload);
      case 'add_branch':
        return addBranch(payload);
      case 'set_route':
        return setRoute(payload);
      case 'update_state':
      case 'update_step':
        return updateState(payload);
      case 'remove_state':
      case 'remove_step':
        return removeState(payload);
      case 'add_context_field':
        return addContextField(payload);
      case 'add_field':
        return addField(payload);
      case 'set_code':
        return setCode(payload);
      case 'add_test':
        return addTest(payload);
      case 'run_tests':
        return runTests();
      case 'review_coverage':
        return reviewCoverage(payload);
      case 'resolve_gap':
        return resolveGap(payload);
      case 'run_scenario':
        return runScenario(payload);
      case 'publish_workflow':
        return publishWorkflow();
      case 'set_panel':
        return setPanel(payload.panel as Panel);
      case 'focus_state':
      case 'select_block':
        return focusState(payload.id ? String(payload.id) : null);
      case 'show_code':
        return showCode(payload.id ? String(payload.id) : null);
      default:
        // Unknown command — ignore rather than break the session.
        return;
    }
  };

  const handleUiCommand = (cmd: Record<string, any> = {}) => dispatch(String(cmd.action ?? ''), cmd);

  const snapshot = (): Record<string, unknown> => {
    const m = ref.current;
    const wf = activeWf();
    const base = {
      view: m.view,
      panel: m.panel,
      admin: m.admin.name,
      workflows: m.workflows.map((w) => ({ id: w.id, name: w.name, category: w.category, status: w.status })),
    };
    if (!wf) return base;
    return {
      ...base,
      active: {
        id: wf.id,
        name: wf.name,
        status: wf.status,
        version: wf.version,
        trigger: wf.trigger,
        context: wf.context.map((c) => ({ key: c.key, type: c.type, derived: !!c.derived, enumValues: c.enumValues })),
        states: wf.states.map((s) => ({
          id: s.id,
          kind: s.kind,
          label: s.label,
          next: s.next,
          rejectTo: s.rejectTo,
          else: s.else,
          approver: s.approver,
          connector: s.connectorId ? connectorActionLabel(s.connectorId, s.actionId) : undefined,
          branches: s.branches?.map((b) => ({ label: b.label, guard: b.guard, to: b.to })),
        })),
        tests: wf.tests.map((t) => ({
          name: t.name,
          given: t.givenState,
          event: t.event,
          expect: t.expectState,
          status: t.status,
          actual: t.actualState,
        })),
        gaps: wf.gaps.filter((g) => !g.resolved).map((g) => ({ state: g.state, event: g.event, question: g.question })),
        selected: m.selectedId,
      },
      sim: m.sim ? { persona: m.sim.personaLabel, restedAt: m.sim.restedAt, done: m.sim.done } : null,
      deployment: m.deployment ? { runId: m.deployment.runId, version: m.deployment.version } : null,
    };
  };

  const registerAgentSend = (fn: AgentSend | null) => {
    sendRef.current = fn;
  };

  const store = useMemo<ForgeStore>(
    () => ({
      get model() {
        return ref.current;
      },
      get active() {
        return activeWf();
      },
      connectors: CONNECTORS,
      botState,
      connectionState,
      setBotState,
      setConnectionState,
      get activities() {
        return activitiesRef.current;
      },
      openList,
      openWorkflow,
      setPanel,
      focusState,
      showCode,
      dispatch,
      handleUiCommand,
      snapshot,
      registerAgentSend,
    }),
    // The store methods are ref-backed, but the Provider value must change
    // identity on each commit — otherwise a stable value + the children-as-props
    // bailout means consumers never re-render. `tick` bumps on every commit();
    // botState/connectionState are proper React state, so they belong here too.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tick, botState, connectionState],
  );

  // dev handle for poking the store from the console
  if (typeof window !== 'undefined') (window as any).__forge = store;

  return <Ctx.Provider value={store}>{children}</Ctx.Provider>;
}

// ─── helpers ─────────────────────────────────────────────────────────────────────

function gapQuestion(s: WorkflowState, ev: string): string {
  const who = s.approver || 'the approver';
  if (s.kind === 'approval' && ev === 'timeout') return `What should happen if ${who} doesn't respond in time at "${s.label}"?`;
  if (s.kind === 'approval' && ev === 'withdrawn') return `What if the requester withdraws before ${who} decides at "${s.label}"?`;
  if (s.kind === 'form' && ev === 'cancel') return `What if the requester cancels at "${s.label}"?`;
  if (s.kind === 'wait' && ev === 'cancelled') return `What if the "${s.label}" timer is cancelled?`;
  return `What should happen on "${ev}" at "${s.label}"?`;
}
