// Generated from ssilva/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types ssilva/backend/brain.py -o ssilva/extension/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/**
 * Go to one of ssilva.cl's pages (a full page load) and then, with
 * `heading` or `text`, scroll to that section and ring it; with
 * `typology`, select that typology on a project page. The page reports
 * `page_changed`.
 */
export interface Navigate {
  path: string;

  heading: string | null;

  text: string | null;

  typology: string | null;
}

/**
 * A move for the page to make when the voice reaches `at` — the first
 * words of the sentence it belongs to (see `.cues`); empty `at` is
 * when the voice stops. With `path`, it is a `Navigate`; with
 * `card`, the card of the project whose page is at that path, rung on the
 * project list (paged to) as he names it, `text` its name; with
 * `photo`, that photo of `photos` full screen; else a section, words or
 * a typology on the page in front. `heading` may be a section's heading
 * or its canonical name: `galería`, `tipologías`, `amenidades`,
 * `tour`, `estado`, `brochure`, `contacto`, `formulario`.
 */
export interface Cue {
  at: string;

  word: number;

  path: string | null;

  heading: string | null;

  text: string | null;

  typology: string | null;

  card: string | null;

  photo: number | null;

  photos: 'gallery' | 'amenities' | null;
}

/**
 * On the page in front, scroll to the heading or canonical section named
 * `heading` and ring it; with `text`, ring the smallest element
 * containing that text (a price, a card).
 */
export interface ShowSection {
  heading: string | null;

  text: string | null;
}

/**
 * On a project page, select the typology labelled `label` ("2D | 2B"),
 * ring its price and floor plan. The page reports `typology_shown`.
 */
export interface SelectTypology {
  label: string;
}

/**
 * Open the project list (`/proyectos/`) filtered by `region`
 * ("metropolitana", "valparaiso", "otros") and `property`
 * ("departamento", "casa", "oficina", "local"), tick the first of `communes`
 * (names as the filter writes them; only the Región Metropolitana has them,
 * and it takes one at a time), and ring
 * the cards of the `highlight` projects (names as the cards write them),
 * found by their project pages in `paths`, which a translated page does
 * not rewrite, paging if needed. The page reports `projects_listed`.
 */
export interface ShowProjects {
  region: string | null;

  property: string | null;

  communes: string[];

  highlight: string[];

  paths: string[];
}

/**
 * On a project page: `gallery` scrolls to the photo gallery and moves it
 * to photo `index` (1 for the first), or with `fullscreen` opens it full
 * screen at that photo; `amenities` opens the amenities' photos full
 * screen at photo `index`. The page reports `photo_shown`.
 */
export interface ShowPhotos {
  which: 'gallery' | 'amenities';

  index: number | null;

  fullscreen: boolean;
}

/**
 * The next photo (`back`: the previous one) in the full-screen viewer,
 * or on the gallery's slider when it is not open.
 */
export interface StepPhoto {
  back: boolean;
}

/**
 * `play`: the photos full screen, by themselves, one every
 * `seconds`, from the one shown to the last, where it stops: the
 * gallery's and then the amenities', or only `which`'s. Not `play`: stop
 * on the photo shown. The visitor starting to speak stops it too.
 */
export interface Slideshow {
  play: boolean;

  which: 'gallery' | 'amenities' | null;

  seconds: number | null;
}

/**
 * Open the project's brochure (`url`, a PDF on ssilva.cl; else the
 * page's own) over the page, at `page`. The page reports
 * `brochure_shown`.
 */
export interface ShowBrochure {
  url: string | null;

  page: number | null;
}

/**
 * Download the project's brochure (`url`, else the page's own) to the
 * visitor's computer.
 */
export interface DownloadBrochure {
  url: string | null;
}

/**
 * A typology's floor plan, full screen: on a project page, select
 * `typology` (when given) and open its plan; on a cotizar page, the
 * typology's unit plan and its place on the floor.
 */
export interface ShowFloorPlan {
  typology: string | null;
}

/**
 * On a project page, open its virtual tour (a modal). Fails, with a
 * reason, where the page has none.
 */
export type OpenTour = Record<string, never>;

/**
 * Close what is open over the page: the full-screen photos or plan, a
 * lightbox, the tour's modal.
 */
export type CloseOverlay = Record<string, never>;

/**
 * On a project page, scroll to the quote form beside the typologies, ring
 * it, and fill in the fields given (a dropdown by its exact option text). What
 * is filled stays. With `next_step`, once step one is complete, press
 * "Siguiente". It never presses "Enviar". The form reports `lead_form`.
 */
export interface FillLeadForm {
  firstname: string | null;

  lastname: string | null;

  rut: string | null;

  email: string | null;

  phone: string | null;

  motivo: string | null;

  tipologia: string | null;

  ingreso: string | null;

  pie: string | null;

  next_step: boolean;
}

/** Open the project's WhatsApp chat with its sales executive in a new tab. */
export type OpenWhatsApp = Record<string, never>;

/** Bring one of the visitor's ssilva.cl tabs to the front. */
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

/** The brochure's download was started on the visitor's computer. */
export interface BrochureDownloaded {
  url: string;
}

/** The project's brochure (a PDF) is open over the page, at `page`. */
export interface BrochureShown {
  url: string;

  page?: number;
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

/**
 * Where the quote form on a project page stands, after every change: its
 * step, what is filled, what is still empty, the exact options of its
 * dropdowns on this project's form, and any error it shows.
 */
export interface LeadFormState {
  step: 'contact' | 'details' | 'sent';

  filled?: Record<string, string>;

  missing?: string[];

  options?: Record<string, string[]>;

  errors?: string[];
}

/**
 * The visitor pressed "Enviar". `blocked` when this preview stopped it
 * before it reached Ssilva.
 */
export interface LeadSubmitted {
  blocked?: boolean;
}

/** The tab in front loaded a page, or came to the front: what is on it now. */
export interface PageChanged {
  url?: string;

  path: string;

  title?: string;

  kind?: 'home' | 'projects' | 'project' | 'quote' | 'page';

  project?: string;

  headings?: string[];

  sections?: string[];

  typologies?: string[];

  typology?: string;

  price?: string;

  typology_price?: string;

  status?: string;

  photos?: string[];

  amenity_photos?: string[];
}

/**
 * A photo or a plan is on screen: in the full-screen viewer, or on the
 * gallery's slider. Sent for every change, the slideshow's included.
 */
export interface PhotoShown {
  which: 'gallery' | 'amenities' | 'plan';

  index?: number;

  total?: number;

  caption?: string;

  playing?: boolean;

  fullscreen?: boolean;

  ended?: boolean;

  by?: 'javier' | 'visitor';
}

/** The project list showed its results for a filter. */
export interface ProjectsListed {
  count?: number;

  region?: string | null;

  property?: string | null;

  communes?: string[];

  projects?: string[];

  paths?: string[];

  cards?: ListedCard[];
}

/**
 * Every ssilva.cl tab the visitor has open, and the one in front: the
 * whole list each time.
 */
export interface TabsChanged {
  tabs?: TabInfo[];

  active?: string;
}

/**
 * A typology was selected on a project page (by Javier or the visitor):
 * what its panel shows now.
 */
export interface TypologyShown {
  label: string;

  price?: string;

  total_area?: string;

  useful_area?: string;

  bedrooms?: string;

  bathrooms?: string;

  orientation?: string;
}

/**
 * The full-screen view closed: by the visitor, or as Javier moved on to
 * another part of the page.
 */
export interface ViewerClosed {
  which: 'gallery' | 'amenities' | 'plan' | 'brochure';

  by?: 'javier' | 'visitor';
}

// ── Shapes used by the messages above ──────────────────────────────

/**
 * One card on the project list, as the site rendered it: its own data,
 * in the site's own Spanish, which no translation of the page rewrites.
 */
export interface ListedCard {
  path: string;

  name?: string;

  price?: string;

  commune?: string;

  bedrooms?: string;

  status?: string;
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
  | { command: 'select_typology'; payload: SelectTypology }
  | { command: 'show_projects'; payload: ShowProjects }
  | { command: 'show_photos'; payload: ShowPhotos }
  | { command: 'step_photo'; payload: StepPhoto }
  | { command: 'slideshow'; payload: Slideshow }
  | { command: 'show_brochure'; payload: ShowBrochure }
  | { command: 'download_brochure'; payload: DownloadBrochure }
  | { command: 'show_floor_plan'; payload: ShowFloorPlan }
  | { command: 'open_tour'; payload: OpenTour }
  | { command: 'close_overlay'; payload: CloseOverlay }
  | { command: 'fill_lead_form'; payload: FillLeadForm }
  | { command: 'open_whatsapp'; payload: OpenWhatsApp }
  | { command: 'focus_tab'; payload: FocusTab }
  | { command: 'language_changed'; payload: LanguageChanged };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'navigate',
  'cue',
  'show_section',
  'select_typology',
  'show_projects',
  'show_photos',
  'step_photo',
  'slideshow',
  'show_brochure',
  'download_brochure',
  'show_floor_plan',
  'open_tour',
  'close_overlay',
  'fill_lead_form',
  'open_whatsapp',
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
  | { event: 'brochure_downloaded'; payload: BrochureDownloaded }
  | { event: 'brochure_shown'; payload: BrochureShown }
  | { event: 'command_failed'; payload: CommandFailed }
  | { event: 'language_requested'; payload: LanguageRequested }
  | { event: 'lead_form'; payload: LeadFormState }
  | { event: 'lead_submitted'; payload: LeadSubmitted }
  | { event: 'page_changed'; payload: PageChanged }
  | { event: 'photo_shown'; payload: PhotoShown }
  | { event: 'projects_listed'; payload: ProjectsListed }
  | { event: 'tabs_changed'; payload: TabsChanged }
  | { event: 'typology_shown'; payload: TypologyShown }
  | { event: 'viewer_closed'; payload: ViewerClosed };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'brochure_downloaded',
  'brochure_shown',
  'command_failed',
  'language_requested',
  'lead_form',
  'lead_submitted',
  'page_changed',
  'photo_shown',
  'projects_listed',
  'tabs_changed',
  'typology_shown',
  'viewer_closed',
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
