// Generated from legal/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types legal/backend/brain.py -o legal/frontend/src/actions.gen.ts
//
// Every field is present on the wire, `null` included, so nothing here is
// optional and no runtime validation is needed to narrow on `command`.

export interface PointToClause {
  /** The clause to bring on screen. */
  clause_id: 'c1' | 'c2' | 'c3' | 'c4' | 'c5' | 'c6' | 'c7' | 'c8' | 'c9' | 'c10';

  /** One short phrase for why you're pointing here, e.g. 'the liability cap'. */
  reason: string;
}

export interface AddComment {
  /** The clause this comment is about. */
  clause_id: 'c1' | 'c2' | 'c3' | 'c4' | 'c5' | 'c6' | 'c7' | 'c8' | 'c9' | 'c10';

  /** The comment text — a sentence or two. */
  text: string;
}

export interface ProposeRedline {
  /** The clause being redlined. */
  clause_id: 'c1' | 'c2' | 'c3' | 'c4' | 'c5' | 'c6' | 'c7' | 'c8' | 'c9' | 'c10';

  /** The exact (or near-exact) span of the current clause text being replaced. */
  original_excerpt: string;

  /** Your proposed replacement text for that span. */
  proposed_text: string;

  /** One short line on why, grounded in the playbook where relevant. */
  rationale: string;
}

export interface InsertClause {
  /** The clause this new one should be inserted directly after. */
  after_clause_id: 'c1' | 'c2' | 'c3' | 'c4' | 'c5' | 'c6' | 'c7' | 'c8' | 'c9' | 'c10';

  /** Heading for the new clause, e.g. 'Data Processing Addendum'. */
  heading: string;

  /** The full proposed text of the new clause. */
  proposed_text: string;

  /** One short line on why this protection is needed, grounded in the playbook where relevant. */
  rationale: string;
}

export interface RunDiligence {
  /** One entry per background angle, usually 2-4. */
  jobs: DiligenceJob[];
}

export interface RouteForApproval {
  /** Short title of what is being routed. */
  title: string;

  /** One-line summary of the issue. */
  summary: string;

  /** The dollar figure at stake, 0 if not applicable. */
  amount: number;

  /** 2-4 short supporting lines. */
  lines: string[];

  /** Your one-line recommendation. */
  recommendation: string;

  /** The role this is routed to, e.g. 'Finance' or 'General Counsel'. */
  routed_to: string;
}

export interface ExtractObligations {
  /** One entry per date-bound obligation found across the document. */
  obligations: Obligation[];
}

export interface SummarizeSession {
  /** One short headline for the session. */
  headline: string;

  /** 2-4 short lines on what was flagged, redlined or inserted this session. */
  highlights: string[];

  /** Anything still outstanding — can be empty. */
  open_items: string[];
}

// ── Shapes used by the actions above ───────────────────────────────

/**
 * One background angle. Flat rather than a shape per kind: Gemini handles a
 * property bag far more reliably than oneOf branching, so a job carries every
 * outcome field as optional and `kind` tells the frontend which to render.
 */
export interface DiligenceJob {
  /** Short label of the background angle, e.g. 'Check liability cap vs. playbook'. */
  label: string;

  /** One short line of what this task is doing, shown while it runs. */
  detail: string;

  /** What kind of outcome this job produces, and therefore which fields below to fill. `finding` — a reconciled fact about THIS document, e.g. a clause checked against a playbook rule. `precedent` — how Acme has negotiated a similar point before. `benchmark` — how this clause compares to the broader portfolio of vendor paper Acme holds, not just one deal. `exposure` — a dollar scenario model for a risk clause. `search` — a clause pulled and reconciled across MULTIPLE data-room documents. `research` — an external, outside-the-document check, e.g. counterparty litigation history. `memo` — a short drafted comparison against named prior deals. */
  kind: 'finding' | 'precedent' | 'benchmark' | 'exposure' | 'search' | 'research' | 'memo';

  /** One-line result shown before the card is expanded, regardless of kind. */
  summary: string;

  /** kind=finding only: the specific fact found, with the actual figures/terms. */
  finding_value: string;

  /** kind=finding only: risk if it fails the playbook, warn if borderline, ok if it passes. */
  finding_flag: 'ok' | 'warn' | 'risk' | null;

  /** kind=precedent only: ONE invented prior deal — not this one — with a real-sounding company name plus a line of context, e.g. 'the TerraLogix DataWorks MSA (closed Q3 2025)'. Imitate that style, don't reuse it. */
  precedent_deal: string;

  /** kind=precedent only: the specific number or term that deal resolved at, e.g. '$1.75M aggregate cap, uncapped for confidentiality and data breaches — vendor countered at $500K, we held the line over two rounds'. */
  precedent_resolution: string;

  /** kind=benchmark only: e.g. '15th percentile' — low percentile framing for a term that is bad for Acme. */
  benchmark_percentile: string;

  /** kind=benchmark only: one line grounding the percentile against Acme's vendor portfolio, e.g. 'of the 40-odd SaaS vendor MSAs we hold, only a handful cap below $500K'. */
  benchmark_note: string;

  /** kind=exposure only: what the clause currently limits recovery to. */
  exposure_cap: string;

  /** kind=exposure only: a realistic incident-severity dollar figure for what a real claim could cost, reasoned from the data and services at stake. */
  exposure_estimate: string;

  /** kind=exposure only: the delta, stated plainly, e.g. 'a gap of roughly $1.75M between what a real breach could cost and what Section 8 actually recovers'. */
  exposure_gap: string;

  /** kind=search only: how many and which data-room documents this covers, e.g. '3 of 4 data room documents'. Ground it in the data room you were given. */
  search_scope: string;

  /** kind=search only: a representative excerpt or reconciled finding across those documents. */
  search_excerpt: string;

  /** kind=research only: the specific finding, invented but realistic, e.g. 'no active litigation; one closed 2022 contract dispute, settled'. */
  research_finding: string;

  /** kind=research only: where it is drawn from, e.g. 'PACER + state court filings, last 5 years'. */
  research_source: string;

  /** kind=research only: risk/warn/ok, the same meaning as finding_flag. */
  research_flag: 'ok' | 'warn' | 'risk' | null;

  /** kind=memo only: one tight paragraph, citing the named prior deals and their figures. Do not invent unnamed comps. */
  memo_body: string;
}

export interface Obligation {
  /** The clause this obligation comes from. */
  clause_id: 'c1' | 'c2' | 'c3' | 'c4' | 'c5' | 'c6' | 'c7' | 'c8' | 'c9' | 'c10';

  /** Short label, e.g. 'Non-renewal notice'. */
  label: string;

  /** The date-bound figure, e.g. '90 days before renewal' or 'within 72 hours of breach'. */
  window: string;

  /** One short line of context — who owes it and what triggers it. */
  note: string;
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'point_to_clause'; payload: PointToClause }
  | { command: 'add_comment'; payload: AddComment }
  | { command: 'propose_redline'; payload: ProposeRedline }
  | { command: 'insert_clause'; payload: InsertClause }
  | { command: 'run_diligence'; payload: RunDiligence }
  | { command: 'route_for_approval'; payload: RouteForApproval }
  | { command: 'extract_obligations'; payload: ExtractObligations }
  | { command: 'summarize_session'; payload: SummarizeSession };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'point_to_clause',
  'add_comment',
  'propose_redline',
  'insert_clause',
  'run_diligence',
  'route_for_approval',
  'extract_obligations',
  'summarize_session',
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
