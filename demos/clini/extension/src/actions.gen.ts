// Generated from clini/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types clini/backend/brain.py -o clini/extension/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/**
 * Go to one of www.clini.cl's pages and, with `heading` or `text`,
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
 * a www.clini.cl tab); else a section, words or FAQ on the tab in front.
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
 * card, a service, a line of the page).
 */
export interface ShowSection {
  heading: string | null;

  text: string | null;
}

/** Open the FAQ that starts with `question` on the page in front, and ring it. */
export interface OpenFaq {
  question: string;
}

/** Bring one of the visitor's Clini tabs to the front. */
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
 * Open the booking for `servicio` (and `prestacion`) on agenda-web.clini.cl,
 * in its own tab — or the agenda tab already open, moved to it — and there
 * take the steps given: the region, the search, the day (YYYY-MM-DD), and with
 * `time` (HH:MM) the hour at `centre` (as the booking titles it, e.g.
 * "CENTRO DE SALUD | METRO TOBALABA"), then Continuar. It reports
 * `agenda_state` after each step, and never presses AGENDAR.
 */
export interface OpenAgenda {
  servicio: number;

  prestacion: number | null;

  region: number | null;

  day: string | null;

  centre: string | null;

  time: string | null;
}

/**
 * On the agenda tab already open: the day (YYYY-MM-DD), the morning or
 * afternoon, the centre and the hour (HH:MM) given, then Continuar once an
 * hour is picked.
 */
export interface AgendaPick {
  day: string | null;

  time: string | null;

  centre: string | null;

  period: 'AM' | 'PM' | null;
}

/**
 * Fill the booking's patient form with what the visitor said; a field the
 * booking has locked (an existing patient's) is left as it is. With
 * `focus_rut`, scroll to the RUT field, ring it and focus it: the visitor
 * types their RUT. It never ticks the consent box and never presses AGENDAR,
 * which it rings once the form is valid.
 */
export interface FillAgendaPatient {
  name: string | null;

  last_name: string | null;

  maternal_last_name: string | null;

  birth_date: string | null;

  sex: 'F' | 'M' | 'O' | null;

  phone: string | null;

  email: string | null;

  focus_rut: boolean;
}

/**
 * Fill the free LASIK evaluation form on /cirugia-lasik (going there first
 * if needed) with what the visitor said; `prevision` and `location` are
 * the form's own option texts. With `focus_rut`, ring and focus the RUT
 * field for the visitor to type. It never presses "¡Agendar evaluación!",
 * which it rings once the form is valid. The page reports `lasik_form_state`.
 */
export interface FillLasikForm {
  name: string | null;

  email: string | null;

  phone: string | null;

  prevision: string | null;

  location: string | null;

  focus_rut: boolean;
}

/**
 * Open one of Clini's own links in a new tab: a specialist's booking on
 * Reservo, the results portals, the cotizador, telemedicine, WhatsApp, or the
 * cancellation of a booking. `url` is resolved and checked by the brain.
 */
export interface OpenLink {
  kind: 'reservo' | 'results_lab' | 'results_imaging' | 'cotizador' | 'telemedicine' | 'whatsapp' | 'cancel_booking';

  key: string | null;

  url: string;
}

/**
 * What the booking on agenda-web.clini.cl shows: on load, and after each
 * step, whoever took it (debounced by the page).
 *
 * `search` is the service and prestación picker; `results` the calendar
 * and a day's hours; `booking` the patient form; `done` the success
 * overlay. Names are the booking's own words, as it shows them.
 */
export interface AgendaState {
  step: 'search' | 'results' | 'booking' | 'done';

  servicio?: number | null;

  servicio_name?: string;

  prestacion?: number | null;

  prestacion_name?: string;

  region?: number | null;

  days?: string[];

  centres?: string[];

  day?: string;

  times?: string[];

  selected?: string;

  indications?: string;

  invalid?: string[];

  ready?: boolean;
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

/** The free LASIK evaluation form on /cirugia-lasik, after a fill. */
export interface LasikFormState {
  filled?: string[];

  missing?: string[];

  valid?: boolean;
}

/** The tab in front changed page, or came to the front: what is on it now. */
export interface PageChanged {
  site?: 'site' | 'agenda';

  url?: string;

  path: string;

  title?: string;

  kind?: 'page' | 'post' | 'agenda';

  headings?: string[];

  faqs?: string[];

  plans?: string[];
}

/**
 * Every Clini tab the visitor has open, and the one in front: the
 * whole list each time.
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
  | { command: 'focus_tab'; payload: FocusTab }
  | { command: 'language_changed'; payload: LanguageChanged }
  | { command: 'open_agenda'; payload: OpenAgenda }
  | { command: 'agenda_pick'; payload: AgendaPick }
  | { command: 'fill_agenda_patient'; payload: FillAgendaPatient }
  | { command: 'fill_lasik_form'; payload: FillLasikForm }
  | { command: 'open_link'; payload: OpenLink };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'navigate',
  'cue',
  'show_section',
  'open_faq',
  'focus_tab',
  'language_changed',
  'open_agenda',
  'agenda_pick',
  'fill_agenda_patient',
  'fill_lasik_form',
  'open_link',
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
  | { event: 'agenda_state'; payload: AgendaState }
  | { event: 'command_failed'; payload: CommandFailed }
  | { event: 'language_requested'; payload: LanguageRequested }
  | { event: 'lasik_form_state'; payload: LasikFormState }
  | { event: 'page_changed'; payload: PageChanged }
  | { event: 'tabs_changed'; payload: TabsChanged };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'agenda_state',
  'command_failed',
  'language_requested',
  'lasik_form_state',
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
