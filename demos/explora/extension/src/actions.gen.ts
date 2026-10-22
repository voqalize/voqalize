// Generated from explora/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types explora/backend/brain.py -o explora/extension/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/**
 * Open one of www.explora.com's pages in the tab in front, once his voice
 * is quiet: a full page load. With `heading`, `text` or `faq`, that is
 * shown once the page is up. The page reports `page_changed`.
 */
export interface Navigate {
  path: string;

  after_words: number;

  heading: string | null;

  text: string | null;

  faq: string | null;
}

/**
 * A move on the page in front for when the voice reaches `at` — the first
 * words of the sentence it belongs to (see `.cues`); empty `at` is when
 * the voice stops. A heading, an in-page tab or accordion by its label, words
 * to ring, or an accordion question to open.
 */
export interface Cue {
  at: string;

  word: number;

  heading: string | null;

  text: string | null;

  faq: string | null;
}

/**
 * On the tab in front, scroll to the heading named `heading` (or open the
 * tab or accordion with that label) and ring it; with `text`, ring the
 * smallest element containing that text.
 */
export interface ShowSection {
  heading: string | null;

  text: string | null;
}

/** Open the accordion whose question starts with `question`, and ring it. */
export interface OpenFaq {
  question: string;
}

/**
 * On reservations.explora.com, choose the lodge `hotel_code` and, with
 * them, the arrival `date` (`YYYY-MM-DD`) and `nights`. With `rooms`,
 * press Continue to its rooms and rates. Never past them. The page reports
 * `stay_state`.
 */
export interface CheckAvailability {
  hotel_code: string;

  date: string | null;

  month: string | null;

  nights: number | null;

  rooms: boolean;

  language: 'EN' | 'ES';
}

/**
 * On the rooms and rates (step two), choose `room` for `travellers`
 * with `bed` and press its select button, which shows the room's summary
 * and its check-out button. Never check-out itself. The page reports
 * `stay_state`.
 */
export interface ChooseRoom {
  room: string;

  travellers: number | null;

  bed: string | null;
}

/**
 * On reservations.explora.com, open the enquiry form of the expedition
 * `expedition_code` and fill in the fields given. What is filled stays. The
 * page reports `enquiry_state`.
 */
export interface FillEnquiry {
  expedition_code: string;

  title: string | null;

  first_name: string | null;

  last_name: string | null;

  email: string | null;

  phone: string | null;

  country: string | null;

  message: string | null;

  language: 'EN' | 'ES';
}

/** Press Send Message on the filled enquiry form, once its reCAPTCHA is ticked. */
export type SendEnquiry = Record<string, never>;

/** Bring one of the visitor's Explora tabs to the front. */
export interface FocusTab {
  tab_id: string;
}

/**
 * The call's language moved, by the toggle, by voice or by
 * `set_language`: the widget's toggle follows at once.
 */
export interface LanguageChanged {
  language: 'en' | 'es';
}

/** A move Javier sent could not be carried out on the page. */
export interface CommandFailed {
  command: string;

  reason?: string;
}

/**
 * Send Message was pressed on a complete form: the page is posting it.
 * `by` says who pressed it.
 */
export interface EnquirySent {
  expedition?: string;

  by?: 'javier' | 'visitor';
}

/**
 * The expedition enquiry form: what is filled, what is still empty, and
 * whether the visitor has ticked "I'm not a robot".
 */
export interface EnquiryState {
  expedition?: string;

  expedition_code?: string;

  filled?: EnquiryFields;

  missing?: string[];

  captcha?: boolean;
}

/** The visitor pressed the other language on the widget's toggle. */
export interface LanguageRequested {
  language: 'en' | 'es';
}

/** The tab in front loaded a page, or came to the front: what is on it now. */
export interface PageChanged {
  site?: 'site' | 'reservations';

  url?: string;

  path: string;

  title?: string;

  headings?: string[];

  faqs?: string[];

  tabs?: string[];

  links?: string[];
}

/**
 * Where an availability check on reservations.explora.com stands: the
 * calendar for a lodge with its open days, the nights offered for the chosen
 * day, or the rooms and rates (step two).
 */
export interface StayState {
  step: 'dates' | 'rooms';

  hotel_code?: string;

  hotel?: string;

  month?: string;

  open_days?: string[];

  date?: string;

  nights?: NightsOption[];

  chosen_nights?: number;

  rooms?: RoomOption[];
}

/**
 * Every Explora tab the visitor has open, and the one in front: the whole
 * list each time.
 */
export interface TabsChanged {
  tabs?: TabInfo[];

  active?: string;
}

// ── Shapes used by the messages above ──────────────────────────────

export interface EnquiryFields {
  title?: string;

  first_name?: string;

  last_name?: string;

  email?: string;

  phone?: string;

  country?: string;

  message?: string;
}

export interface NightsOption {
  nights: number;

  label?: string;
}

export interface RoomOption {
  name: string;

  text?: string;
}

export interface TabInfo {
  tab_id: string;

  url?: string;

  title?: string;
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'navigate'; payload: Navigate }
  | { command: 'cue'; payload: Cue }
  | { command: 'show_section'; payload: ShowSection }
  | { command: 'open_faq'; payload: OpenFaq }
  | { command: 'check_availability'; payload: CheckAvailability }
  | { command: 'choose_room'; payload: ChooseRoom }
  | { command: 'fill_enquiry'; payload: FillEnquiry }
  | { command: 'send_enquiry'; payload: SendEnquiry }
  | { command: 'focus_tab'; payload: FocusTab }
  | { command: 'language_changed'; payload: LanguageChanged };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'navigate',
  'cue',
  'show_section',
  'open_faq',
  'check_availability',
  'choose_room',
  'fill_enquiry',
  'send_enquiry',
  'focus_tab',
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
  | { event: 'command_failed'; payload: CommandFailed }
  | { event: 'enquiry_sent'; payload: EnquirySent }
  | { event: 'enquiry_state'; payload: EnquiryState }
  | { event: 'language_requested'; payload: LanguageRequested }
  | { event: 'page_changed'; payload: PageChanged }
  | { event: 'stay_state'; payload: StayState }
  | { event: 'tabs_changed'; payload: TabsChanged };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'command_failed',
  'enquiry_sent',
  'enquiry_state',
  'language_requested',
  'page_changed',
  'stay_state',
  'tabs_changed',
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
