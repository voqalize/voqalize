// Generated from unosalud/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types unosalud/backend/brain.py -o unosalud/extension/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/**
 * Go to one of www.unosalud.cl's pages (on the site tab, opened if there is
 * none) and, after the load, scroll to the place `anchor` (a key of
 * anchors.json) or the smallest element containing `text` and ring it; with
 * `faq`, open that FAQ key. The page reports `page_changed`.
 */
export interface Navigate {
  path: string;

  anchor: string;

  text: string;

  faq: string;
}

/**
 * A move for the page to make when the voice reaches `at` — the first
 * words of the sentence it belongs to (see `.cues`); empty `at` is
 * when the voice stops. With `path`, it is a `Navigate`; else a
 * place (`anchor`), words (`text`) or an FAQ key (`faq`) on the tab in front.
 */
export interface Cue {
  at: string;

  word: number;

  path: string;

  anchor: string;

  text: string;

  faq: string;

  lead: 'nod' | 'now' | null;
}

/**
 * On the tab in front: scroll to the place `anchor` (or the smallest
 * element containing `text`) and ring it; in a carousel, pause it and select
 * the cell.
 */
export interface ShowSection {
  anchor: string;

  text: string;
}

/** Open the FAQ `faq` (a key of anchors.json) on the tab in front, and ring it. */
export interface OpenFaq {
  faq: string;
}

/** Bring one of the visitor's Uno Salud tabs to the front. */
export interface FocusTab {
  tab_id: string;
}

/** The call's language moved: the widget's toggle follows at once. */
export interface LanguageChanged {
  language: 'en' | 'es';
}

/**
 * Open `url` in a new tab: a clinic's "¿Cómo llegar?" Google Maps link, or
 * a www.unosalud.cl page. Resolved and checked by the brain.
 */
export interface OpenLink {
  url: string;
}

/**
 * Open /agenda-tu-hora/ (with `?promo=` when given) in its own tab, or move
 * to the booking tab already open; once loaded, ring the RUT field (#rut). It
 * never types the RUT, never ticks the terms or the captcha, and never presses
 * Continuar there. Reports `booking_state`.
 */
export interface OpenBooking {
  promo: string;
}

/**
 * On the new patient form (#setPAC): fill the fields given, then ring
 * "Registrarse" once valid — the visitor presses it. On the known patient's
 * step (#setEF): fill email and phone if given and, with `confirm_existing`,
 * press its Continuar. There is no RUT here: the visitor types it.
 */
export interface FillBookingPatient {
  nombre: string;

  paterno: string;

  materno: string;

  birth_date: string;

  email: string;

  phone: string;

  confirm_existing: boolean;
}

/**
 * On the booking tab, the given steps in order, one at a time, waiting for
 * each: the motivo (14 to 23) and its Continuar; the region, comuna and clinic
 * (name or id from #jsonSucursales) and their Continuar; the day (YYYY-MM-DD);
 * the hour (HH:MM), which moves to the review, where "Confirmar cita" is rung
 * for the visitor. Reports `booking_state` after each step.
 */
export interface BookingPick {
  motivo: number;

  region: string;

  comuna: string;

  sucursal: string;

  date: string;

  time: string;
}

/**
 * On the day-and-hour step: read the hours of the next open days, from
 * `from_date`, for `days` days, and leave the first day with hours
 * selected. Reports `booking_state.days`.
 */
export interface BookingScan {
  from_date: string;

  days: number;
}

/**
 * Fill the Te llamamos form (/landing/solicitar-diagnostico/) or the one on
 * /urgencias/ (going there if needed), then ring the RUT field for the visitor
 * and ENVIAR once complete. Never types the RUT, never presses ENVIAR. Reports
 * `callback_form_state`.
 */
export interface FillCallbackForm {
  form: 'te_llamamos' | 'urgencias';

  nombre: string;

  apellidos: string;

  email: string;

  phone: string;

  region: string;

  comuna: string;
}

/**
 * Fill the Convenio Empresas form on /landing/convenio-empresa/ (going there
 * if needed) and ring ENVIAR, which the visitor presses. Reports `company_form_state`.
 */
export interface FillCompanyForm {
  nombre: string;

  phone: string;

  email: string;

  empresa: string;

  region: string;

  cargo: string;

  trabajadores: string;

  comentarios: string;
}

/**
 * The booking on /agenda-tu-hora/: on load and after every step, whoever
 * took it. Never the RUT itself: only whether one was typed.
 */
export interface BookingState {
  step?: 'getPAC' | 'setPAC' | 'setEF' | 'notsetRH' | 'getMRes' | 'getSuc' | 'getHor' | 'getDC' | 'setRH' | 'unknown';

  rut_entered?: boolean;

  patient_first_name?: string;

  motivo?: number;

  region?: string;

  comuna?: string;

  sucursal?: string;

  date?: string;

  slots?: string[];

  days?: DaySlots[];

  no_slots?: boolean;

  summary?: BookingSummary | null;

  error?: string;

  booked?: boolean;
}

/**
 * The Te llamamos form (/landing/solicitar-diagnostico/) or the urgencias
 * one, after a fill or the visitor's press.
 */
export interface CallbackFormState {
  form?: 'te_llamamos' | 'urgencias';

  filled?: string[];

  missing?: string[];

  rut_typed?: boolean;

  result?: 'none' | 'success' | 'error';

  message?: string;
}

/** A move Javier sent was carried out: the page now shows what he asked. */
export interface CommandDone {
  command: string;

  detail?: string;
}

/** A move Javier sent could not be carried out on the page. */
export interface CommandFailed {
  command: string;

  reason?: string;
}

/** The Convenio Empresas form, after a fill or the visitor's press. */
export interface CompanyFormState {
  filled?: string[];

  missing?: string[];

  result?: 'none' | 'success' | 'error';

  message?: string;
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

  kind?: 'home' | 'specialties' | 'specialty' | 'clinics' | 'clinic' | 'promotions' | 'promo_landing' | 'convenios' | 'convenio' | 'benefits' | 'plans' | 'urgencias' | 'about' | 'why_us' | 'contact' | 'faq' | 'company' | 'callback' | 'booking' | 'blog' | 'post' | 'terms' | 'page';

  anchors?: string[];

  faqs?: string[];

  form?: 'booking' | 'callback' | 'urgencias' | 'company' | 'none';

  clinic?: ClinicInfo | null;
}

/**
 * Every Uno Salud tab the visitor has open, and the one in front: the
 * whole list each time.
 */
export interface TabsChanged {
  tabs?: TabInfo[];

  active?: string;
}

// ── Shapes used by the messages above ──────────────────────────────

/** The review step's table (`#data-reserva`), as the booking writes it. */
export interface BookingSummary {
  paciente?: string;

  fecha?: string;

  hora?: string;

  odontologo?: string;

  direccion?: string;

  referencia?: string;
}

/** A clinic page as it reads: how its hours reach him, live. */
export interface ClinicInfo {
  name?: string;

  address?: string;

  hours?: string;

  references?: string;

  maps_url?: string;
}

export interface DaySlots {
  date: string;

  times?: string[];
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
  | { command: 'focus_tab'; payload: FocusTab }
  | { command: 'language_changed'; payload: LanguageChanged }
  | { command: 'open_link'; payload: OpenLink }
  | { command: 'open_booking'; payload: OpenBooking }
  | { command: 'fill_booking_patient'; payload: FillBookingPatient }
  | { command: 'booking_pick'; payload: BookingPick }
  | { command: 'booking_scan'; payload: BookingScan }
  | { command: 'fill_callback_form'; payload: FillCallbackForm }
  | { command: 'fill_company_form'; payload: FillCompanyForm };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'navigate',
  'cue',
  'show_section',
  'open_faq',
  'focus_tab',
  'language_changed',
  'open_link',
  'open_booking',
  'fill_booking_patient',
  'booking_pick',
  'booking_scan',
  'fill_callback_form',
  'fill_company_form',
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
  | { event: 'booking_state'; payload: BookingState }
  | { event: 'callback_form_state'; payload: CallbackFormState }
  | { event: 'command_done'; payload: CommandDone }
  | { event: 'command_failed'; payload: CommandFailed }
  | { event: 'company_form_state'; payload: CompanyFormState }
  | { event: 'language_requested'; payload: LanguageRequested }
  | { event: 'page_changed'; payload: PageChanged }
  | { event: 'tabs_changed'; payload: TabsChanged };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'booking_state',
  'callback_form_state',
  'command_done',
  'command_failed',
  'company_form_state',
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
