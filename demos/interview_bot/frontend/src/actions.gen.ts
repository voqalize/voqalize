// Generated from interview_bot/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types interview_bot/backend/brain.py -o interview_bot/frontend/src/actions.gen.ts
//
// Every field is present on the wire, `null` included, so nothing here is
// optional and no runtime validation is needed to narrow on `command`.

/**
 * Rendered by the `/interview` progress rail when the interviewer moves on
 * to the next section. `index`/`is_last` are the brain's own pointer, not
 * the model's count — the UI cannot recompute either from the conversation.
 */
export interface SectionChanged {
  index: number;

  key: string;

  title: string;

  is_last: boolean;
}

/**
 * Rendered when the interview ends. `summary` is also this tool's whole
 * parameter — the model's own performance summary is what the app renders.
 */
export interface InterviewCompleted {
  /** A brief overall summary of the candidate's performance. */
  summary: string;
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'section_changed'; payload: SectionChanged }
  | { command: 'interview_completed'; payload: InterviewCompleted };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'section_changed',
  'interview_completed',
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
