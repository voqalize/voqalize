// Generated from figurella/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types figurella/backend/brain.py -o figurella/extension/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/**
 * Go to one of the site's pages and, with `anchor` (a key of the
 * catalogue) or `text`, scroll to that place and ring it; with `faq`,
 * open that question of the FAQ. The page loads in full and reports
 * `page_changed`.
 */
export interface Navigate {
  path: string;

  anchor: string | null;

  text: string | null;

  faq: string | null;
}

/**
 * A move for the page to make when the voice reaches `at` — the first
 * words of the sentence it belongs to (see `.cues`); empty `at` is
 * when the voice stops. With `path`, it is a `Navigate`; else a
 * place, words or FAQ question on the tab in front.
 */
export interface Cue {
  at: string;

  word: number;

  path: string | null;

  anchor: string | null;

  text: string | null;

  faq: string | null;
}

/**
 * On the tab in front, scroll to the catalogue's place `anchor` and ring
 * it (a testimonial is brought into the carousel's view first); with
 * `text`, ring the smallest element containing that text.
 */
export interface ShowSection {
  anchor: string | null;

  text: string | null;
}

/**
 * Open the FAQ question `question` (its key, `faq_precio`, or its
 * words) on the page in front, close the one open beside it, and ring it.
 */
export interface OpenFaq {
  question: string;
}

/**
 * Open a link of the site's in a new tab: a branch's "¿Cómo llegar?" map.
 * The visitor goes on there; the extension does nothing on that tab.
 */
export interface OpenLink {
  url: string;

  label: string;
}

/**
 * Type what the visitor dictated into the booking form
 * `#form_agendamiento_figurella` ("Reserva tu Diagnóstico Corporal sin
 * costo"), field by field (the value setter, then `input`, `change` and
 * `blur`), and scroll it into view. A field left `None` is not touched;
 * `sucursal` picks the branch's option by its name. On a page without the
 * form (/franquicias/, /gracias/) the home page opens and the fill is made
 * there. It never presses "Reservar mi diagnóstico", never submits, and never
 * touches the privacy box: once every field is in, the button is rung for her
 * to press. Answers `form_state` and `command_done` / `command_failed`.
 */
export interface FillBookingForm {
  nombre: string | null;

  telefono: string | null;

  email: string | null;

  comuna: string | null;

  sucursal: string | null;

  mensaje: string | null;
}

/**
 * Type what the visitor dictated into the franchise form on /franquicias/
 * ("Comunícate con nosotras"), opening that page first when it is not in
 * front. Never presses "Contáctame ahora", never submits. Answers
 * `form_state` and `command_done` / `command_failed`.
 */
export interface FillFranchiseForm {
  nombre: string | null;

  telefono: string | null;

  email: string | null;
}

/** Bring one of the visitor's Figurella tabs to the front. */
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
 * Sent for the form fills, with what went in and what is still empty.
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

/** She pressed the form's own button and the site answered. */
export interface FormResult {
  form?: 'booking' | 'franchise';

  outcome: 'sent' | 'error';

  message?: string;

  fields?: string[];
}

/**
 * A form as it stands, after Javier filled it or after she typed in it or
 * picked a branch on the page herself.
 */
export interface FormState {
  form?: 'booking' | 'franchise';

  filled?: string[];

  missing?: string[];

  invalid?: string[];

  values?: Record<string, string>;

  consent?: boolean;

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

  title?: string;

  kind?: 'home' | 'method' | 'plans' | 'stories' | 'convenios' | 'franchise' | 'faq' | 'blog' | 'post' | 'thanks' | 'privacy' | 'page';

  anchors?: string[];

  faqs?: string[];

  form?: 'booking' | 'franchise' | 'none';
}

/**
 * Every Figurella tab the visitor has open, and the one in front: the whole
 * list each time.
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

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'navigate'; payload: Navigate }
  | { command: 'cue'; payload: Cue }
  | { command: 'show_section'; payload: ShowSection }
  | { command: 'open_faq'; payload: OpenFaq }
  | { command: 'open_link'; payload: OpenLink }
  | { command: 'fill_booking_form'; payload: FillBookingForm }
  | { command: 'fill_franchise_form'; payload: FillFranchiseForm }
  | { command: 'focus_tab'; payload: FocusTab }
  | { command: 'language_changed'; payload: LanguageChanged };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'navigate',
  'cue',
  'show_section',
  'open_faq',
  'open_link',
  'fill_booking_form',
  'fill_franchise_form',
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
  | { event: 'form_result'; payload: FormResult }
  | { event: 'form_state'; payload: FormState }
  | { event: 'language_requested'; payload: LanguageRequested }
  | { event: 'page_changed'; payload: PageChanged }
  | { event: 'tabs_changed'; payload: TabsChanged };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'command_done',
  'command_failed',
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
