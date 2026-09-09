// Generated from forge/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types forge/backend/brain.py -o forge/frontend/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/** Return to the list of all Service Request Workflows. No fields. */
export type OpenList = Record<string, never>;

export interface OpenWorkflow {
  id: string;
}

export interface CreateWorkflow {
  /** Short kebab id, e.g. 'guest-wifi'. Auto-generated if omitted. */
  id: string;

  name: string;

  description: string;

  category: 'ITSM' | 'HR' | 'Security';

  /** How it starts, in plain words. */
  trigger: string;

  channels: string[];

  context: ContextFieldSpec[];
}

export interface AddState {
  /** Optional stable id; auto if omitted. */
  id: string;

  /** Insert after this state id. */
  after: string;

  kind: 'form' | 'approval' | 'service' | 'wait' | 'code' | 'end';

  label: string;

  subtitle: string;

  connector_id: string;

  action_id: string;

  /** e.g. 'Reporting manager', 'VP, Engineering'. */
  approver: string;

  fields: FormFieldSpec[];

  /** JS body ending in 'return ctx;'. */
  code: string;

  sla_hours: number;

  next: string;

  reject_to: string;

  outcome: string;
}

export interface InsertGateway {
  after: string;

  id: string;

  label: string;

  subtitle: string;

  branches: BranchSpec[];

  /** Optional explicit default target id. */
  otherwise: string;
}

export interface AddBranch {
  gateway: string;

  label: string;

  guard: string;

  to: string;
}

export interface SetRoute {
  state: string;

  next: string;

  reject_to: string;

  otherwise: string;
}

export interface UpdateState {
  id: string;

  label: string;

  subtitle: string;

  connector_id: string;

  action_id: string;

  approver: string;

  sla_hours: number;

  outcome: string;
}

export interface RemoveState {
  id: string;
}

export interface AddContextField {
  /** Dotted key, e.g. 'requester.type' or 'privilegedApp'. */
  key: string;

  label: string;

  type: 'string' | 'boolean' | 'number' | 'enum' | 'user';

  enum_values: string[];

  /** True if computed from other fields by a JS expr. */
  derived: boolean;

  /** JS expression for a derived field, e.g. ctx.app length check. */
  expr: string;

  /** Provenance, e.g. 'from Entra ID'. */
  note: string;
}

export interface AddField {
  state: string;

  field: FormFieldSpec;
}

export interface SetCode {
  state: string;

  code: string;
}

export interface AddTest {
  name: string;

  given_state: string;

  event: string;

  expect_state: string;

  /** JSON, e.g. {"requester.type":"contractor","app":"AWS Console"}. */
  context: string;
}

/** Run all tests for the open workflow. No fields. */
export type RunTests = Record<string, never>;

/** Scan for unhandled (state, event) pairs. No fields. */
export type ReviewCoverage = Record<string, never>;

/**
 * Clear one gap once it is really handled. Name it by the pair read_screen
 * shows — the state id and the event.
 */
export interface ResolveGap {
  /** The gap's state id. */
  state: string;

  /** The gap's event. */
  event: string;
}

export interface RunScenario {
  /** e.g. 'Contractor · AWS Console'. */
  persona_label: string;

  /** JSON object of context values. */
  context: string;

  events: string[];
}

/** Publish the open workflow — makes this version live and durable. No fields. */
export type PublishWorkflow = Record<string, never>;

export interface SetPanel {
  panel: 'flow' | 'code' | 'tests' | 'runtime';
}

export interface FocusState {
  id: string;
}

export interface ShowCode {
  /** The state id whose code to reveal. */
  id: string;
}

/** The admin selected a block — which one they are pointing at, not a change. */
export interface BlockFocused {
  id: string;
}

/** The admin opened one block's code. */
export interface CodeOpened {
  id: string;
}

/**
 * A `review_coverage` came back. The gaps are read off the spec by the
 * studio's interpreter, so a question Ada never thought to ask still shows up —
 * which is the whole point of the linter, and why this is an event and not a
 * tool result.
 */
export interface CoverageScanned {
  gaps?: GapSpec[];
}

/** The admin went back to the workflow list. Nothing is open. */
export type ListOpened = Record<string, never>;

/** The admin switched panels on the open workflow. */
export interface PanelOpened {
  panel: 'flow' | 'code' | 'tests' | 'runtime';
}

/** A persona run finished walking the flow — where it came to rest. */
export interface ScenarioFinished {
  persona?: string;

  rested_at?: string;
}

/**
 * A `run_tests` came back. The outcomes are the interpreter's, on its own
 * clock, and arrive only here — there is no other way for Ada to learn them.
 */
export interface TestsFinished {
  tests?: TestOutcome[];
}

/** The admin opened a workflow themselves, off the list. */
export interface WorkflowOpened {
  id: string;
}

/** The publish landed: the version that went live and the run id it minted. */
export interface WorkflowPublished {
  id: string;

  version?: number;

  run_id?: string;
}

// ── Shapes used by the messages above ──────────────────────────────

/** One guarded branch of a gateway. */
export interface BranchSpec {
  /** Human summary, e.g. 'Contractor + privileged app'. */
  label: string;

  /** JS expression over ctx, first truthy wins. */
  guard: string;

  /** Target state id. */
  to: string;
}

/** One field in a new workflow's request context. */
export interface ContextFieldSpec {
  key: string;

  label: string;

  type: 'string' | 'boolean' | 'number' | 'enum' | 'user';

  enum_values: string[];

  /** True if computed from other fields by a JS expr. */
  derived: boolean;

  /** JS expression for a derived field, e.g. ctx.app length check. */
  expr: string;

  /** Provenance, e.g. 'from Entra ID'. */
  note: string;
}

/** One field on a form block. */
export interface FormFieldSpec {
  key: string;

  label: string;

  type: 'string' | 'boolean' | 'number' | 'enum' | 'user';

  enum_values: string[];
}

/** One unhandled `(state, event)` pair the coverage linter found. */
export interface GapSpec {
  state: string;

  event: string;

  question?: string;
}

/** One test as the interpreter settled it. */
export interface TestOutcome {
  name: string;

  passed: boolean;

  /** Where the run actually came to rest. */
  rested_at?: string;
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'open_list'; payload: OpenList }
  | { command: 'open_workflow'; payload: OpenWorkflow }
  | { command: 'create_workflow'; payload: CreateWorkflow }
  | { command: 'add_state'; payload: AddState }
  | { command: 'insert_gateway'; payload: InsertGateway }
  | { command: 'add_branch'; payload: AddBranch }
  | { command: 'set_route'; payload: SetRoute }
  | { command: 'update_state'; payload: UpdateState }
  | { command: 'remove_state'; payload: RemoveState }
  | { command: 'add_context_field'; payload: AddContextField }
  | { command: 'add_field'; payload: AddField }
  | { command: 'set_code'; payload: SetCode }
  | { command: 'add_test'; payload: AddTest }
  | { command: 'run_tests'; payload: RunTests }
  | { command: 'review_coverage'; payload: ReviewCoverage }
  | { command: 'resolve_gap'; payload: ResolveGap }
  | { command: 'run_scenario'; payload: RunScenario }
  | { command: 'publish_workflow'; payload: PublishWorkflow }
  | { command: 'set_panel'; payload: SetPanel }
  | { command: 'focus_state'; payload: FocusState }
  | { command: 'show_code'; payload: ShowCode };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'open_list',
  'open_workflow',
  'create_workflow',
  'add_state',
  'insert_gateway',
  'add_branch',
  'set_route',
  'update_state',
  'remove_state',
  'add_context_field',
  'add_field',
  'set_code',
  'add_test',
  'run_tests',
  'review_coverage',
  'resolve_gap',
  'run_scenario',
  'publish_workflow',
  'set_panel',
  'focus_state',
  'show_code',
];

const _known = new Set<string>(UI_ACTION_COMMANDS);

/**
 * Narrow a `ui-command` off the wire. Returns null for a command this file
 * does not declare — a page and a brain ship separately, and an older page
 * receiving a newer action should ignore it, not throw.
 */
export function asUiAction(command: string, payload: unknown): UiAction | null {
  return _known.has(command) ? ({ command, payload } as UiAction) : null;
}

/**
 * Call this in a `switch`'s default arm. Adding an action then fails to
 * compile here until the new case is handled — which is the whole point of
 * generating this file.
 */
export function unhandledUiAction(action: never): never {
  throw new Error(`Unhandled action: ${JSON.stringify(action)}`);
}

/** Everything the person can do on screen, discriminated by `event`. */
export type AppEvent =
  | { event: 'block_focused'; payload: BlockFocused }
  | { event: 'code_opened'; payload: CodeOpened }
  | { event: 'coverage_scanned'; payload: CoverageScanned }
  | { event: 'list_opened'; payload: ListOpened }
  | { event: 'panel_opened'; payload: PanelOpened }
  | { event: 'scenario_finished'; payload: ScenarioFinished }
  | { event: 'tests_finished'; payload: TestsFinished }
  | { event: 'workflow_opened'; payload: WorkflowOpened }
  | { event: 'workflow_published'; payload: WorkflowPublished };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'block_focused',
  'code_opened',
  'coverage_scanned',
  'list_opened',
  'panel_opened',
  'scenario_finished',
  'tests_finished',
  'workflow_opened',
  'workflow_published',
];

/**
 * Send one thing the person did. `send` is a pipecat client's `sendUIEvent`,
 * or null before the call connects — a gesture made off-call is dropped,
 * which is right: there is no brain that missed it.
 *
 * The name picks the payload type, so a field renamed in Python stops
 * compiling here rather than arriving as a shape the brain discards.
 */
export function sendAppEvent(
  send: ((event: string, payload?: unknown) => void) | null | undefined,
  event: AppEvent,
): void {
  send?.(event.event, event.payload);
}
