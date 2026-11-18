// Generated from dental/backend/app_events.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types dental/backend/app_events.py -o dental/frontend/src/voice/events.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/** The call now speaks `language`: the page moves its EN / हिंदी toggle. */
export interface LanguageChanged {
  language: 'en' | 'hi';
}

/** The page in front: `home`, `book` or `my-appointments`. */
export interface PageViewed {
  page?: string;

  path?: string;

  by?: 'visitor' | 'agent';
}

/**
 * Every appointment this browser has made or changed so far (new
 * bookings, moves, cancellations), whole: sent when the call connects and
 * after each change. The brain lays it over the authored calendar.
 */
export interface ScheduleChanged {
  appointments?: AppointmentIn[];

  by?: 'visitor' | 'agent';
}

/** The phone number was verified with its code (or a new patient registered). */
export interface PatientSignedIn {
  patient_id: string;

  name?: string;

  phone?: string;

  is_new?: boolean;

  by?: 'visitor' | 'agent';
}

/** The patient signed out. */
export interface PatientSignedOut {
  by?: 'visitor' | 'agent';
}

/** The visitor picked something on the booking page by hand. */
export interface SelectionChanged {
  service_id?: string | null;

  branch_id?: string | null;

  dentist_id?: string | null;

  date?: string | null;

  time?: string | null;

  by?: 'visitor' | 'agent';
}

/** An appointment was booked (the visitor pressed Confirm, or a move did). */
export interface Booked {
  booking_id: string;

  service_id: string;

  date: string;

  time: string;

  dentist_id?: string | null;

  branch_id?: string;

  by?: 'visitor' | 'agent';
}

/** An appointment was moved or cancelled on My appointments. */
export interface AppointmentChanged {
  appointment_id: string;

  action: 'reschedule' | 'cancel';

  date?: string | null;

  time?: string | null;

  fee?: number;

  by?: 'visitor' | 'agent';
}

/** The visitor asked for a dentist to call back, by hand. */
export interface CallbackRequested {
  callback_id: string;

  reason?: string;

  urgency?: string;

  by?: 'visitor' | 'agent';
}

/** The visitor pressed the other language on the toggle during the call. */
export interface LanguageRequested {
  language: 'en' | 'hi';

  by?: 'visitor' | 'agent';
}

// ── Shapes used by the messages above ──────────────────────────────

/** One appointment this browser made or changed, with its real date. */
export interface AppointmentIn {
  id: string;

  patient_id?: string | null;

  service: string;

  branch: string;

  date: string;

  time: string;

  duration_min: number;

  dentist?: string | null;

  chair?: string | null;

  resource?: string | null;

  sitting?: number | null;

  changes?: number;

  status?: 'booked' | 'cancelled';
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'language_changed'; payload: LanguageChanged };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'language_changed',
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
  | { event: 'page_viewed'; payload: PageViewed }
  | { event: 'schedule_changed'; payload: ScheduleChanged }
  | { event: 'patient_signed_in'; payload: PatientSignedIn }
  | { event: 'patient_signed_out'; payload: PatientSignedOut }
  | { event: 'selection_changed'; payload: SelectionChanged }
  | { event: 'booked'; payload: Booked }
  | { event: 'appointment_changed'; payload: AppointmentChanged }
  | { event: 'callback_requested'; payload: CallbackRequested }
  | { event: 'language_requested'; payload: LanguageRequested };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'page_viewed',
  'schedule_changed',
  'patient_signed_in',
  'patient_signed_out',
  'selection_changed',
  'booked',
  'appointment_changed',
  'callback_requested',
  'language_requested',
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
