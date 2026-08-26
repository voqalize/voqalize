// Generated from sugar/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types sugar/backend/brain.py -o sugar/frontend/src/actions.gen.ts
//
// Every field is present on the wire, `null` included, so nothing here is
// optional and no runtime validation is needed to narrow on `command`.

export interface LogMeal {
  /** Which meal of the day this is. */
  meal_type: 'breakfast' | 'lunch' | 'snack' | 'dinner' | 'other';

  /** When they ate, as shown on screen, e.g. '1:30 PM' or 'around 2 PM'. */
  time_label: string;

  /** The foods with quantities and your calorie estimates. */
  items: MealItem[];

  /** Optional one-line note, e.g. 'ate out — office canteen'. */
  note: string;

  /**
   * Summed here rather than asked of the model, so the number on screen is
   * always the sum of the items shown under it — and, being computed, it is
   * absent from the schema Gemini is given and present in the payload the
   * browser renders. That is the whole reason this is one class and not two.
   */
  total_calories: number;
}

export interface LogActivity {
  /** Activity in English, e.g. 'Walk', 'Yoga', 'Desk stretches'. */
  kind: string;

  /** Duration in minutes. */
  duration_min: number;

  /** When, e.g. '7:00 AM' or 'now'. */
  time_label: string;

  /** Optional one-line note. */
  note: string;
}

export interface MarkMedication {
  /** Medication name from the care plan, e.g. 'Metformin 500mg'. */
  name: string;

  /** What the patient reported. */
  status: 'taken' | 'missed' | 'skipped';

  /** When they took it, if they said, e.g. 'after breakfast'. */
  time_label: string;
}

export interface ShowGlucose {
  /** Event time to zoom/highlight, e.g. '2:15 PM'. Omit for the whole day. */
  focus_time_label: string;

  /** Optional short on-screen label for the highlight, e.g. 'Rise after lunch'. */
  note: string;
}

export interface PlayVideo {
  /** Library video id from the PATIENT CONTEXT. */
  video_id: string;

  /** Second to start from. Omit to start at the beginning. */
  start_sec: number;
}

export type PauseVideo = Record<string, never>;

export type ResumeVideo = Record<string, never>;

export interface SetCommitment {
  /** The commitment, short and specific, e.g. 'Fifteen-minute walk after dinner'. */
  text: string;

  /** When they'll do it, e.g. 'tomorrow evening'. */
  when: string;
}

export interface FlagForCareTeam {
  /** Short topic in English, e.g. 'Metformin dose question'. */
  topic: string;

  /** One or two lines of what the patient asked or reported, in English. */
  detail: string;
}

export type ShowSensorRenewal = Record<string, never>;

export type ConfirmSensorOrder = Record<string, never>;

export interface ShowSummary {
  /** Three to five short lines capturing the day, e.g. 'Lunch and dinner logged — about 1,400 kcal', 'Evening walk: 20 minutes', 'All medications taken'. */
  lines: string[];

  /** If anything was flagged to the care team, one short line naming it. */
  flagged: string;
}

export interface Highlight {
  /** Which section to highlight. */
  section: 'glucose' | 'meals' | 'activity' | 'meds' | 'plan' | 'summary';
}

// ── Shapes used by the actions above ───────────────────────────────

export interface MealItem {
  /** Food item in clean English, e.g. 'Roti' or 'Dal (katori)'. */
  name: string;

  /** Quantity in the patient's units, e.g. '2', '1 katori', '1 bowl'. */
  quantity: string;

  /** Your calorie estimate for that quantity, rounded to a friendly number. */
  calories: number;
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'log_meal'; payload: LogMeal }
  | { command: 'log_activity'; payload: LogActivity }
  | { command: 'mark_medication'; payload: MarkMedication }
  | { command: 'show_glucose'; payload: ShowGlucose }
  | { command: 'play_video'; payload: PlayVideo }
  | { command: 'pause_video'; payload: PauseVideo }
  | { command: 'resume_video'; payload: ResumeVideo }
  | { command: 'set_commitment'; payload: SetCommitment }
  | { command: 'flag_for_care_team'; payload: FlagForCareTeam }
  | { command: 'show_sensor_renewal'; payload: ShowSensorRenewal }
  | { command: 'confirm_sensor_order'; payload: ConfirmSensorOrder }
  | { command: 'show_summary'; payload: ShowSummary }
  | { command: 'highlight'; payload: Highlight };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'log_meal',
  'log_activity',
  'mark_medication',
  'show_glucose',
  'play_video',
  'pause_video',
  'resume_video',
  'set_commitment',
  'flag_for_care_team',
  'show_sensor_renewal',
  'confirm_sensor_order',
  'show_summary',
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
