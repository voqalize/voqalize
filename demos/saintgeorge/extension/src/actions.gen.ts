// Generated from saintgeorge/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types saintgeorge/backend/brain.py -o saintgeorge/extension/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/**
 * Go to one of the site's pages and, with `heading` or `text`, scroll
 * to that section and ring it; with `faq`, open that accordion on it. The
 * page loads in full and reports `page_changed`.
 */
export interface Navigate {
  path: string;

  heading: string | null;

  text: string | null;

  faq: string | null;
}

/**
 * A move for the page to make when the voice reaches `at` — the first
 * words of the sentence it belongs to (see `.cues`); empty `at` is
 * when the voice stops. With `path`, it is a `Navigate`; else a
 * section, words or accordion on the tab in front.
 */
export interface Cue {
  at: string;

  word: number;

  path: string | null;

  heading: string | null;

  text: string | null;

  faq: string | null;
}

/**
 * On the tab in front, scroll to the heading named `heading` and ring its
 * section; with `text`, ring the smallest element containing that text.
 */
export interface ShowSection {
  heading: string | null;

  text: string | null;
}

/**
 * Open the accordion whose button starts with `question` on the page in
 * front, and ring it. The site's accordions are found by their words: their
 * ids repeat from page to page.
 */
export interface OpenFaq {
  question: string;
}

/**
 * Open a document or a link of the site's in a new tab: a PDF, the
 * musical's tickets, a families' portal. The visitor goes on there; the
 * extension does nothing on that tab.
 */
export interface OpenLink {
  url: string;

  label: string;
}

/**
 * Take the visitor to the admission page (`path`), ring its reference
 * fees (`about="fees"`) or its admission status (`"admission"`), and
 * read both off the page as it stands. The page answers `fees_read`, or
 * `command_failed` when it cannot find them.
 */
export interface ShowFees {
  path: string;

  about: 'fees' | 'admission';
}

/**
 * Read the school's public calendar in the visitor's browser and take
 * them to the calendar page (`path`), with the calendar ringed. The page
 * answers `events_read` with the next `count` events, or
 * `command_failed`.
 */
export interface ShowEvents {
  path: string;

  count: number;
}

/**
 * Put up a card over the page with an email to admissions, written out
 * and ready — `to`, `subject`, `body`, in `language` — and the
 * admissions phone. The parent presses its button to open the email in their
 * own mail app and sends it themselves: nothing is sent from the card. The
 * page answers `command_done` once it is up, and `contact_used` when a
 * button is pressed.
 */
export interface ShowContactCard {
  to: string;

  subject: string;

  body: string;

  phone: string;

  language: 'en' | 'es';
}

/** Bring one of the visitor's Saint George's tabs to the front. */
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

/**
 * A move Javier sent was carried out: the page now shows what he asked.
 * Sent for `show_contact_card` once the card is up.
 */
export interface CommandDone {
  command: string;

  detail?: string;
}

/** A move Javier sent could not be carried out on the page. */
export interface CommandFailed {
  command: string;

  reason?: string;
}

/**
 * The visitor pressed a button on the contact card Javier put up: the
 * email opens in their own mail app (they send it themselves), or the
 * phone number in their phone app.
 */
export interface ContactUsed {
  via: 'email' | 'phone' | 'closed';
}

/**
 * The school's public calendar, fetched and read in the visitor's
 * browser just now: the events not yet over, by their start, so one that
 * began before today and still runs comes first.
 */
export interface EventsRead {
  today?: string;

  events?: CalendarEvent[];
}

/**
 * The admission page in front, read just now in the visitor's browser:
 * the reference fees and the admission status, as the page words them.
 */
export interface FeesRead {
  url?: string;

  heading?: string;

  fees?: Fee[];

  status?: string[];
}

/** The visitor pressed the other language on the widget's toggle. */
export interface LanguageRequested {
  language: 'en' | 'es';
}

/** The tab in front changed page, or came to the front: what is on it now. */
export interface PageChanged {
  url?: string;

  path: string;

  title?: string;

  kind?: 'home' | 'unit' | 'admission' | 'page';

  headings?: string[];

  faqs?: string[];

  cards?: string[];

  links?: PageLink[];
}

/**
 * Every Saint George's tab the visitor has open, and the one in front: the
 * whole list each time.
 */
export interface TabsChanged {
  tabs?: TabInfo[];

  active?: string;
}

// ── Shapes used by the messages above ──────────────────────────────

export interface CalendarEvent {
  date: string;

  time?: string;

  end?: string;

  title?: string;
}

export interface Fee {
  label?: string;

  value?: string;

  note?: string;
}

/**
 * A link on the page that opens something of its own: a PDF, the
 * musical's tickets, a portal.
 */
export interface PageLink {
  label?: string;

  url: string;

  near?: string;
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
  | { command: 'open_link'; payload: OpenLink }
  | { command: 'show_fees'; payload: ShowFees }
  | { command: 'show_events'; payload: ShowEvents }
  | { command: 'show_contact_card'; payload: ShowContactCard }
  | { command: 'focus_tab'; payload: FocusTab }
  | { command: 'language_changed'; payload: LanguageChanged };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'navigate',
  'cue',
  'show_section',
  'open_faq',
  'open_link',
  'show_fees',
  'show_events',
  'show_contact_card',
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
  | { event: 'command_done'; payload: CommandDone }
  | { event: 'command_failed'; payload: CommandFailed }
  | { event: 'contact_used'; payload: ContactUsed }
  | { event: 'events_read'; payload: EventsRead }
  | { event: 'fees_read'; payload: FeesRead }
  | { event: 'language_requested'; payload: LanguageRequested }
  | { event: 'page_changed'; payload: PageChanged }
  | { event: 'tabs_changed'; payload: TabsChanged };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'command_done',
  'command_failed',
  'contact_used',
  'events_read',
  'fees_read',
  'language_requested',
  'page_changed',
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
