// Generated from uahurtado/backend/protocol.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types uahurtado/backend/protocol.py -o uahurtado/extension/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/**
 * Load `url` (a page on one of the three UAH hosts) in the tab the call
 * is in and, once it has loaded, scroll to and ring `heading` (a heading,
 * a tab, pill or accordion label, which is opened first) or `text`, or open
 * the FAQ `faq`. A page already in front is not reloaded: the move is done
 * on it, and it reports `page_changed` again.
 */
export interface Navigate {
  url: string;

  heading: string | null;

  text: string | null;

  faq: string | null;
}

/**
 * A move for the page to make when the voice reaches `at` — the first
 * three folded words of the sentence it belongs to (empty: when the voice
 * stops; `word` is the clock fallback). With `url` it is a
 * `Navigate`; otherwise a heading, tab, pill, accordion, card, words
 * or FAQ on the page in front. Cues still owed when the page unloads are
 * carried to the next page, across hosts.
 */
export interface Cue {
  at: string;

  word: number;

  url: string | null;

  heading: string | null;

  text: string | null;

  faq: string | null;
}

/**
 * On the page in front, open (if it is a tab, pill or accordion label)
 * and ring `heading`; with `text`, ring the smallest laid-out element
 * containing it.
 */
export interface ShowSection {
  heading: string | null;

  text: string | null;
}

/**
 * Open the FAQ (an h3 collapse, a Bootstrap accordion or a details box)
 * that starts with `question` on the page in front, and ring it.
 */
export interface OpenFaq {
  question: string;
}

/** Bring one of the visitor's UAH tabs to the front. */
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
 * Open `url` in a new tab: the PAES simulator (simula.uahurtado.cl), a
 * malla PDF. The extension does nothing on that tab, and on simula it fills
 * nothing: its form creates a lead.
 */
export interface OpenLink {
  url: string;

  label: string;
}

/**
 * Open the Carreras mega-menu (`#collapseCarreras`, via
 * `#menu-menu-principal-1 > li.boton-carrera > a`) and ring the group of
 * `faculty` in it (matched loosely, accents folded; `None`: the whole
 * menu). Off admision.uahurtado.cl, the page first loads `url` (admision's
 * home) and opens the menu there. Answers `command_done` (detail: the
 * careers listed in the ringed group) or `command_failed`.
 */
export interface OpenCareerMenu {
  faculty: string | null;

  url: string;
}

/**
 * On the career page `url`, press play on the audiomalla (`#malla
 * audio`): the director's own voice about the career. While it plays the
 * visitor's microphone is muted, so the call does not take the recording for
 * the visitor speaking; it is unmuted when it ends or is paused. Answers
 * `command_done` once playing, `command_failed` if the browser refused (the
 * play button is then rung for the visitor to press), and
 * `audiomalla_ended` when it stops.
 */
export interface PlayAudiomalla {
  url: string;
}

/**
 * On the career page `url` (loaded first if it is not in front), open
 * the "Requisitos y Aranceles" tab (`#requisitos_carrera-tab`) and ring its
 * fees (`focus` "fees": the right column, `h3` "Aranceles") or its PAES
 * weights table ("requirements": the left column). Then read both from the
 * visible text — never from `data-sheets-value` attributes, which hold old
 * figures — and, in the service worker, the site's own record
 * (`admision.uahurtado.cl/wp-json/wp/v2/carreras?slug=<slug>&_fields=acf.aranceles_carrera`).
 * Answers `admission_read`, or `command_failed` when the tab is not there.
 */
export interface ShowAdmission {
  url: string;

  slug: string;

  focus: 'fees' | 'requirements';
}

/**
 * On the postgraduate programme page `url` (loaded first if needed),
 * expand "Requisitos y Valores" (`[data-bs-target="#collapseRequisitos"]`)
 * and ring it; read it and the sidebar's `h3` blocks (Postulaciones,
 * Inicio…) from the page, and in the service worker
 * `postgrados.uahurtado.cl/wp-json/wp/v2/programa?slug=<slug>&_fields=acf.postulacion_desde,acf.postulacion_hasta,acf.inicio_programa,acf.requisitos_program`.
 * Answers `program_read`, or `command_failed`.
 */
export interface ShowProgram {
  url: string;

  slug: string;
}

/**
 * Type what the visitor dictated into the lead form `#admisionForm` on
 * the page in front, field by field (value setter, then `input`,
 * `change` and `blur`), and scroll it into view. A field left `None` is
 * not touched. `carrera` and `via` pick a `<select>` option by its
 * text, where the form has that select. Never the RUT: with `focus_rut` the
 * RUT field is rung and focused for the visitor to type. Never submit, never
 * press "Enviar": once every required field but the RUT is filled, "Enviar"
 * is rung. Answers `lead_form_state` and `command_done` /
 * `command_failed`.
 */
export interface FillLeadForm {
  nombre: string | null;

  apellido: string | null;

  email: string | null;

  fono: string | null;

  consulta: string | null;

  carrera: string | null;

  via: string | null;

  focus_rut: boolean;
}

/**
 * On /ven-y-conocenos/, ring the "Inscribirse aquí" link of the visit
 * card titled `title`. Never click it: sign-ups are Google and HubSpot
 * forms the visitor opens themselves. `command_failed` if the card is
 * marked REALIZADO, has closed sign-ups, or is not there.
 */
export interface ShowSignup {
  title: string;
}

/**
 * The tab in front changed page, or came to the front: what is on it now,
 * as laid out at this width (hidden mobile duplicates left out).
 */
export interface PageChanged {
  url: string;

  title?: string;

  kind?: 'home' | 'career' | 'program' | 'listing' | 'page';

  headings?: string[];

  toggles?: string[];

  faqs?: string[];

  cards?: string[];

  career?: CareerSheet | null;

  program?: ProgramSheet | null;

  visits?: VisitCard[];

  form?: LeadFormInfo | null;

  translated?: boolean;
}

/** Every UAH tab the visitor has open, and the one in front. */
export interface TabsChanged {
  tabs?: TabInfo[];

  active?: string;
}

/**
 * A move the brain waits on was carried out: `detail` says in a few
 * English words what is on screen now.
 */
export interface CommandDone {
  command: string;

  detail?: string;
}

/**
 * A move Javier sent could not be carried out; `reason` is an English
 * sentence naming what *is* there.
 */
export interface CommandFailed {
  command: string;

  reason?: string;
}

/** The visitor pressed the other language on the widget's toggle. */
export interface LanguageRequested {
  language: 'en' | 'es';
}

/**
 * The answer to `show_admission`: the career's Requisitos y Aranceles,
 * read just now in the visitor's browser.
 */
export interface AdmissionRead {
  slug: string;

  url?: string;

  fees_text?: string;

  year?: string;

  matricula?: string;

  arancel?: string;

  titulacion_uf?: string;

  weights?: Row[];

  requirements_text?: string;

  api_fees_text?: string;

  error?: string;
}

/** The answer to `show_program`. */
export interface ProgramRead {
  slug: string;

  url?: string;

  requisitos_text?: string;

  sidebar?: Row[];

  postulacion_desde?: string;

  postulacion_hasta?: string;

  inicio_programa?: string;

  api_requisitos_text?: string;

  error?: string;
}

/** The lead form after a fill, or after the visitor typed in it. */
export interface LeadFormState {
  filled?: string[];

  missing?: string[];

  invalid?: string[];

  career?: string;

  ready?: boolean;
}

/** The visitor pressed "Enviar": the form went to UAH's admissions. */
export type LeadSubmitted = Record<string, never>;

/** The audiomalla stopped: it finished, or the visitor paused it. */
export interface AudiomallaEnded {
  finished?: boolean;
}

// ── Shapes used by the messages above ──────────────────────────────

/**
 * What a career page (`/carreras/<slug>/`) shows, read off its DOM at
 * load — every tab pane is in the document, shown or not.
 */
export interface CareerSheet {
  slug: string;

  name?: string;

  facts?: Row[];

  tabs?: string[];

  has_audiomalla?: boolean;

  audiomalla_label?: string;

  malla_pdf?: string;

  fees_text?: string;

  weights?: Row[];

  requirements_text?: string;
}

/** The lead form `#admisionForm` on the page, if it has one. */
export interface LeadFormInfo {
  fields?: string[];

  career_options?: string[];

  via_options?: string[];

  career?: string;

  filled?: string[];
}

/** What a postgraduate programme page (`/programa/<slug>/`) shows. */
export interface ProgramSheet {
  slug: string;

  name?: string;

  requisitos_text?: string;

  sidebar?: Row[];

  accordion?: string[];
}

/** One row of a table as the page shows it: `label` → `value`. */
export interface Row {
  label: string;

  value?: string;
}

export interface TabInfo {
  tab_id: string;

  url?: string;

  title?: string;
}

/** A visit or workshop card on /ven-y-conocenos/. */
export interface VisitCard {
  title: string;

  text?: string;

  done?: boolean;

  open?: boolean;

  signup_label?: string;

  signup_url?: string;
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'navigate'; payload: Navigate }
  | { command: 'cue'; payload: Cue }
  | { command: 'show_section'; payload: ShowSection }
  | { command: 'open_faq'; payload: OpenFaq }
  | { command: 'focus_tab'; payload: FocusTab }
  | { command: 'language_changed'; payload: LanguageChanged }
  | { command: 'open_link'; payload: OpenLink }
  | { command: 'open_career_menu'; payload: OpenCareerMenu }
  | { command: 'play_audiomalla'; payload: PlayAudiomalla }
  | { command: 'show_admission'; payload: ShowAdmission }
  | { command: 'show_program'; payload: ShowProgram }
  | { command: 'fill_lead_form'; payload: FillLeadForm }
  | { command: 'show_signup'; payload: ShowSignup };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'navigate',
  'cue',
  'show_section',
  'open_faq',
  'focus_tab',
  'language_changed',
  'open_link',
  'open_career_menu',
  'play_audiomalla',
  'show_admission',
  'show_program',
  'fill_lead_form',
  'show_signup',
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
  | { event: 'page_changed'; payload: PageChanged }
  | { event: 'tabs_changed'; payload: TabsChanged }
  | { event: 'command_done'; payload: CommandDone }
  | { event: 'command_failed'; payload: CommandFailed }
  | { event: 'language_requested'; payload: LanguageRequested }
  | { event: 'admission_read'; payload: AdmissionRead }
  | { event: 'program_read'; payload: ProgramRead }
  | { event: 'lead_form_state'; payload: LeadFormState }
  | { event: 'lead_submitted'; payload: LeadSubmitted }
  | { event: 'audiomalla_ended'; payload: AudiomallaEnded };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'page_changed',
  'tabs_changed',
  'command_done',
  'command_failed',
  'language_requested',
  'admission_read',
  'program_read',
  'lead_form_state',
  'lead_submitted',
  'audiomalla_ended',
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
