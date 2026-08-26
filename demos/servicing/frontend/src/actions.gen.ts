// Generated from servicing/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types servicing/backend/brain.py -o servicing/frontend/src/actions.gen.ts
//
// Every field is present on the wire, `null` included, so nothing here is
// optional and no runtime validation is needed to narrow on `command`.

/** Show the advisor's case board (the worklist of all their cases). No fields. */
export type OpenBoard = Record<string, never>;

export interface OpenCase {
  /** Case reference, e.g. 'MS-1042'. */
  ref: string;
}

export interface SetTab {
  /** Which tab of the open case to show. */
  tab: 'overview' | 'payments' | 'documents' | 'activity';
}

export interface AssignCase {
  /** Case reference, e.g. 'MS-1057'. */
  ref: string;

  /** Whether routing to a teammate or a department queue. */
  assignee_kind: 'person' | 'department';

  /** The person's name (e.g. 'Marcus Bell') or department key: one of pricing, closures, legal, insurance, compliance. */
  assignee: string;
}

export interface MoveCase {
  /** Case reference. */
  ref: string;

  /** Target stage column. */
  stage: 'new' | 'in_progress' | 'needs_approval' | 'with_dept' | 'done';
}

export interface AddComment {
  /** Case reference, e.g. 'MS-1057'. */
  ref: string;

  /** The note text — a sentence or two of context for the case. */
  text: string;

  /** Optional department this note is about (one of pricing, closures, legal, insurance, compliance). Tags the note; omit if it's a general note. */
  dept: string;
}

export interface PrepareCase {
  /** Case reference to prepare, e.g. 'MS-1057'. */
  ref: string;

  /** One-line summary of what you're preparing for this case. */
  summary: string;

  /** The background prep steps (usually 3-4). They animate to completion. */
  jobs: JobSpec[];

  /** The workup result — the cross-system facts you assembled and figures you reconciled (payoff, accrued interest, escrow, in-flight payments). Flag the ones the advisor would likely have missed with 'warn'. */
  findings: FindingSpec[];

  /** The one risk you caught that gates a regulated step — the thing the advisor wouldn't have known to look for (e.g. an open second lien before a title release). Omit if the case is clean. */
  blocker: BlockerSpec | null;

  /** The regulated packet (multi-step form) you filled from the workup, e.g. an early-closure packet with payoff figures, document-release, escrow sections. Mark the section a blocker gates with blocked:true. Omit if not relevant. */
  packet: PacketSpec | null;

  /** The draft items to reveal for the advisor's approval once prep finishes (settlement letter, fee waiver, document release, etc.). If a blocker gates one (e.g. document release), set blocked:true on it. */
  approvals: ApprovalSpec[];
}

export interface PostWorkup {
  /** Case reference, e.g. 'MS-1042'. */
  ref: string;

  /** The facts/reconciliations you assembled for this case. */
  findings: FindingSpec[];

  /** A risk you caught that needs attention. Omit if the case is clean. */
  blocker: BlockerSpec | null;
}

export interface LookupPrecedent {
  /** What you're searching for, e.g. 'early closure with an open second lien'. */
  query: string;

  /** The 2-3 most relevant past cases, each with how it was resolved. */
  results: PrecedentSpec[];
}

export interface UpdatePacketField {
  /** Case reference. */
  ref: string;

  /** Section id or title to edit, e.g. 'payoff'. */
  section: string;

  /** Field label to set, e.g. 'Payoff date'. */
  field: string;

  /** The new value. */
  value: string;

  /** Optional one-line activity note. */
  note: string;
}

export interface ResolveBlocker {
  /** Case reference. */
  ref: string;

  /** What cleared it, e.g. 'Legal subordinated the home-equity line'. */
  note: string;
}

export interface SubmitPacket {
  /** Case reference whose packet to submit. */
  ref: string;
}

export interface DraftApproval {
  /** Case reference. */
  ref: string;

  /** The draft to add. */
  approval: ApprovalSpec;
}

export interface Highlight {
  /** Which section to highlight. */
  section: 'summary' | 'loan' | 'payments' | 'documents' | 'approvals' | 'notes' | 'activity';
}

// ── Shapes used by the actions above ───────────────────────────────

/** A draft item dropped into the advisor's 'Needs your approval' queue. */
export interface ApprovalSpec {
  /** Assigned automatically; never set this. */
  id: string;

  /** Draft title, e.g. 'Settlement letter' or 'Early-closure fee waiver'. */
  title: string;

  /** Category of the draft (drives the icon shown). */
  kind: 'settlement_letter' | 'fee_waiver' | 'rate_offer' | 'document_release' | 'escrow_change' | 'other';

  /** One-line summary of what the advisor is approving. */
  summary: string;

  /** A few short detail lines shown on the draft card (figures, terms). */
  lines: string[];

  /** Headline dollar amount if relevant (payoff total, fee waived, new payment). */
  amount: number | null;

  /** Your brief recommendation + reason for the advisor, e.g. 'Recommend waiving — 12-year customer in good standing'. Empty if none. */
  recommendation: string;

  /** True if this draft CANNOT be approved yet because the workup caught a blocker (e.g. a document-release that's blocked by an open lien). It shows locked until the blocker is cleared. */
  blocked: boolean;

  /** If blocked, one short line why, e.g. 'Open second lien must clear first'. */
  blocked_reason: string;
}

/** A risk the workup caught that gates a regulated step — the thing nav never surfaces. */
export interface BlockerSpec {
  /** Short headline, e.g. 'Open second lien on the property'. */
  title: string;

  /** One or two lines on what it is and why it blocks, e.g. 'A 2021 home-equity line is still open — releasing the title now is a compliance exception.' */
  detail: string;

  /** 'block' = a regulated step cannot proceed until cleared; 'warn' = caution only. */
  severity: 'block' | 'warn';

  /** Department to route to in order to clear it, e.g. 'Legal & Custody'. */
  suggested_route: string;
}

/** One line of the desk's "workup" — the cross-system assembly/reconciliation legwork. */
export interface FindingSpec {
  /** Assigned automatically; never set this. */
  id: string;

  /** What was checked, e.g. 'Payoff reconciliation'. */
  label: string;

  /** The assembled/reconciled result, e.g. 'Net payoff 286,400 (a payment posted yesterday wasn't applied)'. */
  value: string;

  /** 'warn' for a reconciliation the advisor would likely have missed; 'ok' otherwise. */
  flag: 'ok' | 'warn' | 'info';
}

/** One background prep step of a `prepare_case` workup. */
export interface JobSpec {
  /** Assigned automatically; never set this. */
  id: string;

  /** Short label of the background step, e.g. 'Pull payoff figure'. */
  label: string;

  /** One short line of the result the step produces, e.g. 'Payoff 284,900 + 1,210 accrued interest'. Shown when the step finishes. */
  detail: string;
}

/** A field/section of a regulated packet (multi-step form) the desk fills. */
export interface PacketFieldSpec {
  /** Field name, e.g. 'Payoff date'. */
  label: string;

  /** Field value, e.g. '30 June 2026' or '286,400'. */
  value: string;

  /** True for figures/ids shown in monospace. */
  mono: boolean;
}

export interface PacketSectionSpec {
  /** Short id, e.g. 'payoff', 'release', 'escrow'. */
  id: string;

  /** Section title, e.g. 'Payoff figures'. */
  title: string;

  fields: PacketFieldSpec[];

  /** True if this section is locked by a blocker (e.g. the document-release section while a lien is open). */
  blocked: boolean;

  /** If blocked, one short line why. */
  blocked_reason: string;
}

export interface PacketSpec {
  /** Short id, e.g. 'closure'. */
  id: string;

  /** Packet title, e.g. 'Early-closure packet'. */
  title: string;

  /** One line on what this packet does. */
  summary: string;

  /** The form sections (e.g. payoff figures, document release, escrow disposition). */
  sections: PacketSectionSpec[];
}

/** A past (archived) case returned by the server-side precedent search. */
export interface PrecedentSpec {
  /** Assigned automatically; never set this. */
  id: string;

  /** Archive case reference, e.g. 'MS-0907'. */
  ref: string;

  /** Customer name on the past case. */
  customer: string;

  /** One line on what the past case was. */
  summary: string;

  /** How it was handled/resolved, e.g. 'Legal subordinated the HELOC; title released after.' */
  resolution: string;

  /** How many days it took to resolve, if relevant. */
  days: number | null;
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'open_board'; payload: OpenBoard }
  | { command: 'open_case'; payload: OpenCase }
  | { command: 'set_tab'; payload: SetTab }
  | { command: 'assign_case'; payload: AssignCase }
  | { command: 'move_case'; payload: MoveCase }
  | { command: 'add_comment'; payload: AddComment }
  | { command: 'prepare_case'; payload: PrepareCase }
  | { command: 'post_workup'; payload: PostWorkup }
  | { command: 'lookup_precedent'; payload: LookupPrecedent }
  | { command: 'update_packet_field'; payload: UpdatePacketField }
  | { command: 'resolve_blocker'; payload: ResolveBlocker }
  | { command: 'submit_packet'; payload: SubmitPacket }
  | { command: 'draft_approval'; payload: DraftApproval }
  | { command: 'highlight'; payload: Highlight };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'open_board',
  'open_case',
  'set_tab',
  'assign_case',
  'move_case',
  'add_comment',
  'prepare_case',
  'post_workup',
  'lookup_precedent',
  'update_packet_field',
  'resolve_blocker',
  'submit_packet',
  'draft_approval',
  'highlight',
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
