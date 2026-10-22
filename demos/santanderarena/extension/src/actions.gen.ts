// Generated from santanderarena/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types santanderarena/backend/brain.py -o santanderarena/extension/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/**
 * Go to one of the site's pages and, with `heading` or `text`, scroll
 * to that section or card and ring it; with `faq`, open that FAQ on it. The
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
 * section, card, words or FAQ on the tab in front.
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
 * section; with `text`, ring the smallest element containing that text (a
 * show's card, a bar, a date), brought out of its carousel first.
 */
export interface ShowSection {
  heading: string | null;

  text: string | null;
}

/** Open the FAQ that starts with `question` on the page in front, and ring it. */
export interface OpenFaq {
  question: string;
}

/**
 * Open a ticket, parking or VIP link on Puntoticket in a new tab. The
 * visitor buys there; the extension does not run on that site.
 */
export interface OpenTickets {
  url: string;

  label: string;
}

/** Bring one of the visitor's Santander Arena tabs to the front. */
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

/** The visitor pressed the other language on the widget's toggle. */
export interface LanguageRequested {
  language: 'en' | 'es';
}

/** The tab in front changed page, or came to the front: what is on it now. */
export interface PageChanged {
  url?: string;

  path: string;

  title?: string;

  kind?: 'home' | 'event' | 'news' | 'page';

  headings?: string[];

  faqs?: string[];

  cards?: string[];

  tickets?: TicketLink[];
}

/**
 * Every Santander Arena tab the visitor has open, and the one in front:
 * the whole list each time.
 */
export interface TabsChanged {
  tabs?: TabInfo[];

  active?: string;
}

// ── Shapes used by the messages above ──────────────────────────────

export interface TabInfo {
  tab_id: string;

  url?: string;

  title?: string;
}

/** A link on the page that leaves the site to buy: tickets, parking, VIP. */
export interface TicketLink {
  label?: string;

  url: string;

  near?: string;
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'navigate'; payload: Navigate }
  | { command: 'cue'; payload: Cue }
  | { command: 'show_section'; payload: ShowSection }
  | { command: 'open_faq'; payload: OpenFaq }
  | { command: 'open_tickets'; payload: OpenTickets }
  | { command: 'focus_tab'; payload: FocusTab }
  | { command: 'language_changed'; payload: LanguageChanged };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'navigate',
  'cue',
  'show_section',
  'open_faq',
  'open_tickets',
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
  | { event: 'language_requested'; payload: LanguageRequested }
  | { event: 'page_changed'; payload: PageChanged }
  | { event: 'tabs_changed'; payload: TabsChanged };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'command_failed',
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
