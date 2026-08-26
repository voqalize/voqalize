// Generated from forge/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types forge/backend/brain.py -o forge/frontend/src/actions.gen.ts
//
// Every field is present on the wire, `null` included, so nothing here is
// optional and no runtime validation is needed to narrow on `command`.

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

export interface ResolveGap {
  /** The gap id, if known. */
  id: string;

  /** Gap's state id (with `event`) if no id. */
  state: string;

  /** Gap's event (with `state`) if no id. */
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

// ── Shapes used by the actions above ───────────────────────────────

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
