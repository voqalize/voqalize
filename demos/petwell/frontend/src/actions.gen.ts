// Generated from petwell/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types petwell/backend/brain.py -o petwell/frontend/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

export interface Navigate {
  page: 'home' | 'services' | 'locations' | 'health_hub' | 'at_home';
}

export interface ShowBranches {
  city: string;
}

export interface OpenArticle {
  article_id: string;
}

export interface LanguageChanged {
  language: 'English' | 'Hindi' | 'Bengali' | 'Gujarati' | 'Kannada' | 'Malayalam' | 'Marathi' | 'Punjabi' | 'Tamil' | 'Telugu';

  screen_language: 'en' | 'hi';
}

export interface StartBooking {
  visit_type: 'clinic' | 'home';
}

export interface ChooseCity {
  city: string;
}

export interface ChooseBranch {
  branch_id: string;
}

export interface ChooseService {
  service_id: string;
}

export interface ShowSlots {
  branch_id: string;

  /** ISO date, e.g. 2026-10-07. */
  date: string;

  visit_type: 'clinic' | 'home';

  times: string[];
}

export interface ChooseSlot {
  /** ISO date, e.g. 2026-10-07. */
  date: string;

  /** 24-hour HH:MM, exactly as show_slots returned it. */
  time: string;
}

export interface FillDetails {
  /** Leave empty if not learned this turn. */
  owner_name: string;

  /** Leave empty if not learned this turn. */
  pet_name: string;

  /** Leave empty if not learned this turn. */
  pet_type: 'dog' | 'cat' | 'bird' | 'rabbit' | 'other' | '';

  /** Digits only. Empty if not learned this turn. */
  phone: string;

  /** Empty if not given. */
  email: string;

  /** Home visits only. Empty if not given. */
  address: string;

  /** A short note for the vet. Empty if none. */
  notes: string;
}

export type ShowReview = Record<string, never>;

export interface ShowEmergency {
  city: string;

  helpline: string;

  branch_ids: string[];
}

export type GoHome = Record<string, never>;

/** The visitor tapped Send Request, and the browser minted the reference. */
export interface AppointmentRequested {
  ref?: string;

  owner_name?: string;

  pet_name?: string;

  phone?: string;
}

/** The visitor opened a Health Hub article. */
export interface ArticleOpened {
  article_id?: string;
}

/**
 * The visitor opened the booking panel — from the header, a service card or
 * an article's call to action, which may name the service to book.
 */
export interface BookingOpened {
  service_id?: string;
}

/** The visitor tapped a branch in the booking panel. */
export interface BranchPicked {
  branch_id?: string;
}

/** The visitor tapped a city in the booking panel. */
export interface CityPicked {
  city?: string;
}

/** The visitor chose a language on the page's picker. */
export interface LanguagePicked {
  language?: 'English' | 'Hindi' | 'Bengali' | 'Gujarati' | 'Kannada' | 'Malayalam' | 'Marathi' | 'Punjabi' | 'Tamil' | 'Telugu';
}

/** The visitor opened a page from the site's navigation. */
export interface PagePicked {
  page?: 'home' | 'services' | 'locations' | 'health_hub' | 'at_home';
}

/** The visitor tapped a reason for the visit. */
export interface ServicePicked {
  service_id?: string;
}

/** The visitor tapped a time on the slot grid. */
export interface SlotPicked {
  date?: string;

  time?: string;
}

/** The visitor tapped Clinic visit or Vet at home. */
export interface VisitTypePicked {
  visit_type?: 'clinic' | 'home';
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'navigate'; payload: Navigate }
  | { command: 'show_branches'; payload: ShowBranches }
  | { command: 'open_article'; payload: OpenArticle }
  | { command: 'language_changed'; payload: LanguageChanged }
  | { command: 'start_booking'; payload: StartBooking }
  | { command: 'choose_city'; payload: ChooseCity }
  | { command: 'choose_branch'; payload: ChooseBranch }
  | { command: 'choose_service'; payload: ChooseService }
  | { command: 'show_slots'; payload: ShowSlots }
  | { command: 'choose_slot'; payload: ChooseSlot }
  | { command: 'fill_details'; payload: FillDetails }
  | { command: 'show_review'; payload: ShowReview }
  | { command: 'show_emergency'; payload: ShowEmergency }
  | { command: 'go_home'; payload: GoHome };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'navigate',
  'show_branches',
  'open_article',
  'language_changed',
  'start_booking',
  'choose_city',
  'choose_branch',
  'choose_service',
  'show_slots',
  'choose_slot',
  'fill_details',
  'show_review',
  'show_emergency',
  'go_home',
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
  | { event: 'appointment_requested'; payload: AppointmentRequested }
  | { event: 'article_opened'; payload: ArticleOpened }
  | { event: 'booking_opened'; payload: BookingOpened }
  | { event: 'branch_picked'; payload: BranchPicked }
  | { event: 'city_picked'; payload: CityPicked }
  | { event: 'language_picked'; payload: LanguagePicked }
  | { event: 'page_picked'; payload: PagePicked }
  | { event: 'service_picked'; payload: ServicePicked }
  | { event: 'slot_picked'; payload: SlotPicked }
  | { event: 'visit_type_picked'; payload: VisitTypePicked };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'appointment_requested',
  'article_opened',
  'booking_opened',
  'branch_picked',
  'city_picked',
  'language_picked',
  'page_picked',
  'service_picked',
  'slot_picked',
  'visit_type_picked',
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
