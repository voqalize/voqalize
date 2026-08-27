// Generated from lead_qual/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types lead_qual/backend/brain.py -o lead_qual/frontend/src/actions.gen.ts
//
// Every field is present on the wire, `null` included, so nothing here is
// optional and no runtime validation is needed to narrow on `command`.

/**
 * Rendered by the `/lead_qual` end screen. `branch` is set only for a
 * qualified outcome.
 */
export interface CallEnded {
  outcome: 'qualified' | 'not_interested' | 'unresponsive' | 'ineligible' | 'other';

  lead: Lead;

  branch: Branch | null;
}

// ── Shapes used by the actions above ───────────────────────────────

/** The nearest Auric branch, from the enquiry payload the page sent. */
export interface Branch {
  name: string;

  address: string;
}

/**
 * The qualification record as the end screen renders it: the four identity
 * fields the enquiry form already carried, plus the six `end_call`
 * collected. Unanswered questions stay null and the screen omits their rows.
 */
export interface Lead {
  name: string;

  phone: string;

  state: string;

  city: string;

  gold_form: 'jewelry' | 'coins' | 'bars' | 'mixed' | null;

  gold_weight_grams: number | null;

  loan_amount_inr: number | null;

  loan_purpose: string | null;

  timeline: 'immediate' | 'within_week' | 'within_month' | 'exploring' | null;

  preferred_next_step: 'branch_visit' | 'home_visit' | null;
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'call_ended'; payload: CallEnded };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'call_ended',
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
