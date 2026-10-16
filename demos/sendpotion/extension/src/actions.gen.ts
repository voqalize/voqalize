// Generated from sendpotion/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types sendpotion/backend/brain.py -o sendpotion/extension/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/**
 * Go to one of sendpotion.com's pages and, with `heading` or `text`,
 * scroll to that section and ring it; with `faq`, open that FAQ on it. The
 * page reports `page_changed`.
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
 * when the voice stops. With `path`, it is a `Navigate` (and goes to
 * a sendpotion.com tab); else a section, words or FAQ on the tab in front.
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
 * plan card, a feature, a line of a post).
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
 * Show `posts` in the widget's reading list, on every tab, under
 * `heading`; and open `open` (one of them) in a new tab.
 */
export interface OpenPosts {
  heading: string;

  posts: ReadingItem[];

  open: string | null;
}

/**
 * Open one blog post — in the tab that already shows it, or a new one —
 * and, with `heading`, scroll to that section of it.
 */
export interface OpenPost {
  url: string;

  heading: string | null;
}

/**
 * Open /demo/ and, in its Calendly calendar, choose `day` and `time` and
 * fill in the details given. The page reports `demo_state`; it never
 * presses Schedule Event.
 */
export interface BookDemo {
  day: string | null;

  time: string | null;

  name: string | null;

  email: string | null;

  notes: string | null;
}

/** Open the Potion app's sign-up (app.sendpotion.com) in a new tab. */
export type OpenSignup = Record<string, never>;

/** Bring one of the visitor's SendPotion tabs to the front. */
export interface FocusTab {
  tab_id: string;
}

/** A move Tushar sent could not be carried out on the page. */
export interface CommandFailed {
  command: string;

  reason?: string;
}

/**
 * The visitor pressed Schedule Event. `blocked` when the demo stopped it
 * before it reached SendPotion's calendar.
 */
export interface DemoScheduled {
  date?: string;

  time?: string;

  filled?: DemoFields;

  blocked?: boolean;
}

/**
 * Where the demo booking on /demo/ stands: the calendar with its open days
 * (and the chosen day's times), or the details step with what is still empty.
 */
export interface DemoState {
  step: 'calendar' | 'details' | 'scheduled';

  month?: string;

  days?: string[];

  date?: string;

  times?: string[];

  time?: string;

  timezone?: string;

  filled?: DemoFields;

  missing?: string[];
}

/** The tab in front changed page, or came to the front: what is on it now. */
export interface PageChanged {
  site?: 'site' | 'blog';

  url?: string;

  path: string;

  title?: string;

  kind?: 'page' | 'post' | 'blog';

  headings?: string[];

  faqs?: string[];

  plans?: string[];
}

/**
 * Every SendPotion tab the visitor has open, and the one in front: the
 * whole list each time.
 */
export interface TabsChanged {
  tabs?: TabInfo[];

  active?: string;
}

// ── Shapes used by the messages above ──────────────────────────────

export interface DemoFields {
  name?: string;

  email?: string;

  notes?: string;
}

export interface ReadingItem {
  url: string;

  title: string;

  why: string | null;
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
  | { command: 'open_posts'; payload: OpenPosts }
  | { command: 'open_post'; payload: OpenPost }
  | { command: 'book_demo'; payload: BookDemo }
  | { command: 'open_signup'; payload: OpenSignup }
  | { command: 'focus_tab'; payload: FocusTab };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'navigate',
  'cue',
  'show_section',
  'open_faq',
  'open_posts',
  'open_post',
  'book_demo',
  'open_signup',
  'focus_tab',
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
  | { event: 'demo_scheduled'; payload: DemoScheduled }
  | { event: 'demo_state'; payload: DemoState }
  | { event: 'page_changed'; payload: PageChanged }
  | { event: 'tabs_changed'; payload: TabsChanged };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'command_failed',
  'demo_scheduled',
  'demo_state',
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
