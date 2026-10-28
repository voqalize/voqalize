// Generated from enveedo/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types enveedo/backend/brain.py -o enveedo/extension/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/**
 * Go to one of the site's pages and, with `anchor` (a key of the
 * catalogue) or `text`, scroll to that place and ring it. `path` is the
 * English site's path; while the call is in Spanish the extension loads its
 * /es/ twin. The page loads in full and reports `page_changed`.
 */
export interface Navigate {
  path: string;

  anchor: string | null;

  text: string | null;
}

/**
 * A move for the page to make when the voice reaches `at` — the first
 * words of the sentence it belongs to (see `.cues`); empty `at` is
 * when the voice stops. With `path`, it is a `Navigate`; else a
 * place or words on the tab in front. A place the catalogue marks
 * `reveal` (a tab, an accordion, the Without/With toggle) is opened by
 * its own control first, then ringed.
 */
export interface Cue {
  at: string;

  word: number;

  path: string | null;

  anchor: string | null;

  text: string | null;
}

/**
 * On the tab in front, scroll to the catalogue's place `anchor` (opening
 * it first when the catalogue marks it `reveal`) and ring it; with
 * `text`, ring the smallest element containing that text.
 */
export interface ShowSection {
  anchor: string | null;

  text: string | null;
}

/**
 * Open a link the site gives in a new tab: a gated eBook or webinar on
 * info.enveedo.com, a YouTube webinar, a blog post, the platform PDF, the
 * customers' sign-in. The visitor goes on there; the extension does nothing
 * on that tab.
 */
export interface OpenLink {
  url: string;

  label: string;
}

/**
 * Open /book-a-demo (its /es/ twin in a Spanish call) and, in its HubSpot
 * Meetings scheduler (a meetings.hubspot.com frame), choose `duration`,
 * `day` and `time` and fill in the details given, as far as they go. A
 * field left `None` is not touched. The frame reports `demo_state`; it
 * never presses the scheduler's final confirm button.
 */
export interface BookDemo {
  duration: string | null;

  day: string | null;

  time: string | null;

  first_name: string | null;

  last_name: string | null;

  email: string | null;
}

/**
 * Type what the visitor dictated into one of the site's HubSpot forms,
 * field by field (the native value setter, then `input`, `change` and
 * `blur`), and scroll it into view: `contact` on /contact (also at the
 * foot of /frameworks), `soc2` (the SOC 2 report request) on
 * /trust-center. On another page the form's page opens first (its /es/ twin
 * in a Spanish call) and the fill is made there. A field left `None` is
 * not touched; a field the form does not have is ignored. It never ticks the
 * consent box, never presses Submit and never touches the reCAPTCHA: once
 * every field is in, the consent box and Submit are rung for the visitor.
 * Answers `form_state` and `command_done` / `command_failed`.
 */
export interface FillForm {
  form: 'contact' | 'soc2';

  firstname: string | null;

  lastname: string | null;

  email: string | null;

  phone: string | null;

  country: string | null;

  company: string | null;

  job_title: string | null;

  message: string | null;
}

/** Bring one of the visitor's Enveedo tabs to the front. */
export interface FocusTab {
  tab_id: string;
}

/**
 * The call's language moved, by the toggle, by voice or by
 * `set_language`: the widget's toggle follows at once, and the tab keeps
 * it for the rest of the call, on every page.
 */
export interface LanguageChanged {
  language: 'en' | 'es';

  site: 'follow' | 'twin' | 'stay';
}

/**
 * A move Javier sent was carried out: the page now shows what he asked.
 * Sent for the form fills and the reveals, with what was done.
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
 * The visitor pressed the scheduler's final button. `blocked` when the
 * demo stopped it before it reached Enveedo's calendar.
 */
export interface DemoScheduled {
  date?: string;

  time?: string;

  filled?: DemoFields;

  blocked?: boolean;
}

/**
 * Where the demo scheduler on /book-a-demo stands: still loading, the
 * calendar with its open days (and the chosen day's times), or the details
 * step with what is still empty.
 */
export interface DemoState {
  step: 'loading' | 'calendar' | 'details' | 'scheduled';

  duration?: string;

  durations?: string[];

  month?: string;

  days?: string[];

  date?: string;

  times?: string[];

  time?: string;

  timezone?: string;

  filled?: DemoFields;

  missing?: string[];
}

/**
 * The visitor pressed Submit on one of the site's forms and the site
 * answered.
 */
export interface FormResult {
  form?: 'contact' | 'soc2';

  outcome: 'sent' | 'invalid' | 'failed';

  message?: string;

  fields?: string[];
}

/**
 * One of the site's forms as it stands, after Javier filled it or after
 * the visitor typed in it.
 */
export interface FormState {
  form?: 'contact' | 'soc2';

  filled?: string[];

  missing?: string[];

  invalid?: string[];

  values?: Record<string, string>;

  ready?: boolean;

  by?: 'javier' | 'visitor';
}

/** The visitor pressed the other language on the widget's toggle. */
export interface LanguageRequested {
  language: 'en' | 'es';
}

/** The tab in front changed page, or came to the front: what is on it now. */
export interface PageChanged {
  url?: string;

  path: string;

  lang?: 'en' | 'es';

  title?: string;

  kind?: string;

  anchors?: string[];

  form?: 'contact' | 'soc2' | 'demo' | 'none';
}

/**
 * Every Enveedo tab the visitor has open, and the one in front: the whole
 * list each time.
 */
export interface TabsChanged {
  tabs?: TabInfo[];

  active?: string;
}

// ── Shapes used by the messages above ──────────────────────────────

/** What the scheduler's details step holds now. */
export interface DemoFields {
  first_name?: string;

  last_name?: string;

  email?: string;
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
  | { command: 'open_link'; payload: OpenLink }
  | { command: 'book_demo'; payload: BookDemo }
  | { command: 'fill_form'; payload: FillForm }
  | { command: 'focus_tab'; payload: FocusTab }
  | { command: 'language_changed'; payload: LanguageChanged };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'navigate',
  'cue',
  'show_section',
  'open_link',
  'book_demo',
  'fill_form',
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
  | { event: 'demo_scheduled'; payload: DemoScheduled }
  | { event: 'demo_state'; payload: DemoState }
  | { event: 'form_result'; payload: FormResult }
  | { event: 'form_state'; payload: FormState }
  | { event: 'language_requested'; payload: LanguageRequested }
  | { event: 'page_changed'; payload: PageChanged }
  | { event: 'tabs_changed'; payload: TabsChanged };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'command_done',
  'command_failed',
  'demo_scheduled',
  'demo_state',
  'form_result',
  'form_state',
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
