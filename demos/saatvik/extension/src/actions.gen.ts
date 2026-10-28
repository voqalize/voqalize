// Generated from saatvik/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types saatvik/backend/brain.py -o saatvik/extension/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/** The brief, whole, each time it changes: the widget's card replaces itself. */
export interface LeadBrief {
  fields: LeadFields;

  observed: Observed;

  score: Score;

  routing: string;

  summary: string;

  submitted: boolean;
}

/**
 * Go to one of the site's pages and, once it is up, scroll to `heading`
 * or `text` and ring it, open the spec tab `tab`, or open the FAQ
 * `faq`. The page reports `page_changed`.
 */
export interface Navigate {
  path: string;

  heading: string | null;

  text: string | null;

  tab: string | null;

  faq: string | null;
}

/**
 * A move for the page to make when the voice reaches `at` — the first
 * words of the sentence it belongs to (see `.cues`); empty `at` is
 * when the voice stops. With `path`, it is a `Navigate`; else a
 * section, words, spec tab or FAQ on the page in front.
 */
export interface Cue {
  at: string;

  word: number;

  path: string | null;

  heading: string | null;

  text: string | null;

  tab: string | null;

  faq: string | null;
}

/**
 * Scroll to the heading named `heading` and ring its section; with
 * `text`, ring the smallest element in it that contains that text (with no
 * heading, anywhere on the page: a spec row, a model, a card).
 */
export interface ShowSection {
  heading: string | null;

  text: string | null;
}

/** Open the accordion question that starts with `question` and ring it. */
export interface OpenFaq {
  question: string;
}

/** Click one of the page's spec tabs, scroll to it and ring its panel. */
export interface OpenTab {
  label: string;
}

/**
 * Open one of Saatvik's PDFs in a tab beside the visitor's Saatvik tab, at
 * `page`, highlighting `quote` when given. The next document reuses that
 * tab; a later move on the site brings the Saatvik tab back to the front.
 *
 * `boxes` is set on a page whose text is drawn as outlines (Saatvik's module
 * datasheets), where the viewer's text layer has nothing to find: the quote's
 * words were read off the page image at build time, and the page marks these
 * rectangles instead.
 */
export interface OpenDocument {
  url: string;

  title: string;

  page: number;

  quote: string | null;

  boxes: QuoteBox[] | null;
}

/** Close the document's tab and bring the visitor's Saatvik tab back. */
export type CloseDocument = Record<string, never>;

/**
 * The call's language moved, by the toggle, by voice or by `set_language`:
 * the widget's toggle follows at once.
 */
export interface LanguageChanged {
  language: 'en' | 'hi';
}

/**
 * Open the enquiry form's `kind` tab and fill in `prefill`. The page
 * rings the required fields still empty and the SUBMIT button; it never ticks
 * consent and never submits.
 */
export interface OpenEnquiry {
  kind: 'domestic' | 'dealer' | 'export';

  prefill: EnquiryPrefill;
}

/**
 * Open `product`'s booking page (its BOOK NOW), choose `installation` on
 * its first step, press Continue, and fill in `details` on the second. The
 * page rings the fields still empty, the consent box and CONFIRM BOOKING; it
 * never ticks consent and never confirms.
 */
export interface BookProduct {
  product: 'surya-connect-kit' | 'tej-plus-g12r' | 'tej-m10r' | 'n-topcon' | 'bifacial-g2tb' | 'mono-perc' | 'vega-g2wb' | 'uday-single-phase' | 'uday-three-phase' | 'uday-plus-hybrid';

  installation: 'residential' | 'commercial';

  details: BookingPrefill;
}

/** Fill in and run the savings calculator; the page reports `calculator_result`. */
export interface RunCalculator {
  units: number;

  state: string;

  rate: number;
}

/** Filter the dealer locator; the page reports `dealers_shown`. */
export interface FindDealer {
  state: string | null;

  query: string | null;
}

/**
 * A product's booking page is at its details step, for this installation
 * type, with these fields still empty.
 */
export interface BookingOpened {
  installation: 'residential' | 'commercial';

  product?: string;

  missing?: string[];
}

/** The visitor pressed CONFIRM BOOKING; the details as they stood. */
export interface BookingSubmitted {
  installation: 'residential' | 'commercial';

  product?: string;

  fields?: BookingFields;
}

/**
 * The solar calculator finished: its inputs, and its result as the page
 * prints it.
 */
export interface CalculatorResult {
  inputs?: CalculatorInputs;

  text?: string;
}

/** A move Tushar sent could not be carried out on the page. */
export interface CommandFailed {
  command: string;

  reason?: string;
}

/** The dealer locator shows these, for this state and search. */
export interface DealersShown {
  state?: string;

  query?: string;

  dealers?: Dealer[];
}

/** The PDF viewer closed. */
export interface DocumentClosed {
  url?: string;

  page?: number;
}

/** The PDF viewer opened, or turned to a page. */
export interface DocumentOpened {
  url: string;

  page?: number;
}

/** The enquiry form is on screen, on this tab, with these required fields empty. */
export interface EnquiryOpened {
  kind: 'domestic' | 'dealer' | 'export';

  missing?: string[];
}

/** The visitor pressed SUBMIT; the fields as they stood, read before the page sent. */
export interface EnquirySubmitted {
  kind: 'domestic' | 'dealer' | 'export';

  fields?: EnquiryFields;
}

/** The visitor pressed the other language on the widget's toggle. */
export interface LanguageRequested {
  language: 'en' | 'hi';
}

/** The route changed, or the page first loaded: what is on it now. */
export interface PageChanged {
  path: string;

  title?: string;

  headings?: string[];

  faqs?: string[];

  tabs?: string[];
}

// ── Shapes used by the messages above ──────────────────────────────

export interface BookingFields {
  name?: string;

  mobile?: string;

  email?: string;

  address?: string;

  state?: string;

  city?: string;

  pincode?: string;
}

export interface BookingPrefill {
  name: string | null;

  mobile: string | null;

  email: string | null;

  address: string | null;

  state: string | null;

  city: string | null;

  pincode: string | null;
}

export interface CalculatorInputs {
  units?: number | null;

  state?: string | null;

  rate?: number | null;
}

export interface Dealer {
  name: string;

  type?: string;

  city?: string;

  phone?: string;
}

export interface EnquiryFields {
  name?: string;

  company?: string;

  email?: string;

  mobile?: string;

  category?: string;

  state?: string;

  message?: string;
}

export interface EnquiryPrefill {
  name: string | null;

  company: string | null;

  email: string | null;

  mobile: string | null;

  category: string | null;

  state: string | null;

  message: string | null;
}

export interface Estimate {
  units: number;

  state: string;

  rate: number;

  result: string;
}

/**
 * What the visitor told Tushar, or typed into the enquiry form. Every field is
 * optional: a brief is useful from its first fact.
 */
export interface LeadFields {
  name: string | null;

  company: string | null;

  email: string | null;

  mobile: string | null;

  segment: 'residential' | 'commercial' | 'industrial' | 'institutional' | 'agricultural' | 'utility' | 'dealer' | 'export' | 'investor' | 'job-seeker' | 'other' | null;

  need: string | null;

  system_size_kw: number | null;

  monthly_units: number | null;

  monthly_bill_inr: number | null;

  state: string | null;

  city: string | null;

  roof_type: string | null;

  roof_area: string | null;

  ownership: 'own' | 'rent' | 'shared' | null;

  timeline: 'immediately' | 'within 3 months' | '3 to 6 months' | '6 to 12 months' | 'over a year' | 'exploring' | null;

  budget: string | null;

  financing_interest: boolean | null;

  subsidy_interest: boolean | null;

  products_interested: string[];

  decision_maker: boolean | null;

  callback_requested: boolean | null;

  preferred_time: string | null;

  language: string | null;

  objections: string[];

  enquiry_kind: string | null;

  category: string | null;

  message: string | null;
}

/** What the visitor did on the site during the call, from the page's events. */
export interface Observed {
  pages: string[];

  documents: string[];

  estimate: Estimate | null;

  dealers_shown: string[];

  questions: string[];
}

/**
 * A rectangle to mark on a PDF page, in fractions of the page from its top
 * left corner.
 */
export interface QuoteBox {
  x: number;

  y: number;

  w: number;

  h: number;
}

/** Points on three axes, each with the reason it was given. */
export interface Score {
  grade: 'hot' | 'warm' | 'cold' | 'not sales';

  intent: number;

  fit: number;

  readiness: number;

  reasons: string[];
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'lead_brief'; payload: LeadBrief }
  | { command: 'navigate'; payload: Navigate }
  | { command: 'cue'; payload: Cue }
  | { command: 'show_section'; payload: ShowSection }
  | { command: 'open_faq'; payload: OpenFaq }
  | { command: 'open_tab'; payload: OpenTab }
  | { command: 'open_document'; payload: OpenDocument }
  | { command: 'close_document'; payload: CloseDocument }
  | { command: 'language_changed'; payload: LanguageChanged }
  | { command: 'open_enquiry'; payload: OpenEnquiry }
  | { command: 'book_product'; payload: BookProduct }
  | { command: 'run_calculator'; payload: RunCalculator }
  | { command: 'find_dealer'; payload: FindDealer };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'lead_brief',
  'navigate',
  'cue',
  'show_section',
  'open_faq',
  'open_tab',
  'open_document',
  'close_document',
  'language_changed',
  'open_enquiry',
  'book_product',
  'run_calculator',
  'find_dealer',
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
  | { event: 'booking_opened'; payload: BookingOpened }
  | { event: 'booking_submitted'; payload: BookingSubmitted }
  | { event: 'calculator_result'; payload: CalculatorResult }
  | { event: 'command_failed'; payload: CommandFailed }
  | { event: 'dealers_shown'; payload: DealersShown }
  | { event: 'document_closed'; payload: DocumentClosed }
  | { event: 'document_opened'; payload: DocumentOpened }
  | { event: 'enquiry_opened'; payload: EnquiryOpened }
  | { event: 'enquiry_submitted'; payload: EnquirySubmitted }
  | { event: 'language_requested'; payload: LanguageRequested }
  | { event: 'page_changed'; payload: PageChanged };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'booking_opened',
  'booking_submitted',
  'calculator_result',
  'command_failed',
  'dealers_shown',
  'document_closed',
  'document_opened',
  'enquiry_opened',
  'enquiry_submitted',
  'language_requested',
  'page_changed',
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
