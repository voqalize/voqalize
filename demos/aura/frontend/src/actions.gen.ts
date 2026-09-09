// Generated from aura/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types aura/backend/brain.py -o aura/frontend/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/** Back to the Aura Bank home page. */
export type OpenHome = Record<string, never>;

/** The help centre's category index. */
export type OpenHelpCenter = Record<string, never>;

/** One help-centre category's article list. */
export interface OpenCategory {
  category: string;
}

/** One help article, full screen. */
export interface OpenArticle {
  article_id: string;
}

/** Start Aura's own how-to clip, muted, at a given second. */
export interface PlayHelpVideo {
  video_id: string;

  start_sec: number;
}

/** Move the on-screen step list's focus to one step. */
export interface HighlightStep {
  index: number;
}

/** Jump the playing clip to another second. */
export interface SeekVideo {
  start_sec: number;
}

/** Hold the clip where it is. */
export type PauseVideo = Record<string, never>;

/** Play on from where it was paused. */
export type ResumeVideo = Record<string, never>;

/** The helpline panel, headed by what they were stuck on. */
export interface ShowContact {
  topic: string;
}

/**
 * The calculator screen, filled in and already solved.
 *
 * `inputs` carries the defaults the customer never gave, because the screen
 * shows its own working — and `result` is computed here rather than in the
 * browser so the figure Aria speaks and the figure on screen cannot drift.
 */
export interface RunCalculator {
  kind: 'emi' | 'fd' | 'eligibility';

  inputs: Record<string, number>;

  result: Record<string, number>;
}

/** Open a blank product application. */
export interface StartApplication {
  product: 'savings' | 'credit_card' | 'loan';
}

/** Type one value into the open application. */
export interface PrefillField {
  field: string;

  value: string;
}

/** Send the open application — only ever after the customer says so. */
export type SubmitApplication = Record<string, never>;

/** The side-by-side comparison table, with one column starred. */
export interface Compare {
  kind: 'credit_card' | 'savings';

  items: CompareItem[];

  recommend_id: string;

  recommend_reason: string;
}

/** The branch/ATM locator, showing results for one pincode. */
export interface FindBranch {
  pincode: string;

  results: BranchResult[];
}

/** A titled list of short lines — documents, eligibility, next steps. */
export interface ShowChecklist {
  title: string;

  items: string[];
}

/** The 'sent to your phone' confirmation. */
export interface SendToPhone {
  what: string;

  channel: 'whatsapp' | 'sms';

  number: string;
}

/** The ticket receipt, with the reference the server minted. */
export interface RaiseTicket {
  reference: string;

  topic: string;

  summary: string;
}

/** Draw a ring around one element on screen. */
export interface Spotlight {
  target: string;

  label: string;
}

/** The Multi-Currency Forex Card screen, with its one-tap request. */
export type ShowForexCard = Record<string, never>;

/**
 * The secure sign-in sheet. The browser answers with `auth_complete` (or
 * `auth_cancelled`), carrying this nonce; the token is minted there, never
 * here — see `AuraBrain._complete_auth`.
 */
export interface OpenAuth {
  nonce: string;

  name: string;

  masked_mobile: string;
}

/** The account picker. Answered by `account_selected` / `account_cancelled`. */
export interface ChooseAccount {
  nonce: string;

  accounts: AccountRef[];
}

/** The balance card for one account, as of a date. */
export interface ShowBalance {
  account: AccountRef;

  balance: number;

  currency: string;

  as_of: string;
}

/** A dated transaction list for one account. */
export interface ShowStatement {
  account: AccountRef;

  from_date: string;

  to_date: string;

  transactions: StatementTxn[];

  currency: string;
}

/** The card picker. Answered by `card_selected` / `card_cancelled`. */
export interface ChooseCreditCard {
  nonce: string;

  cards: CardRef[];
}

/**
 * The usage & limits form for one card — the customer edits and saves it
 * themselves, so the assistant never reads the toggles aloud.
 */
export interface ShowCardControls {
  card: CardRef;

  credit_limit: number;

  controls: CardControls;
}

/** The customer dismissed the account picker. */
export interface AccountCancelled {
  nonce: string;
}

/** The customer tapped an account in the picker. */
export interface AccountSelected {
  nonce: string;

  account_id: string;
}

/** The customer started an application themselves, off a quick link. */
export interface ApplicationStarted {
  /** One of savings, credit_card, loan. */
  product?: string;
}

/** The customer submitted the open application themselves. */
export type ApplicationSubmitted = Record<string, never>;

/** The customer opened one help article themselves. */
export interface ArticleOpened {
  article_id: string;
}

/** The customer closed the sign-in without signing in — an answer too. */
export interface AuthCancelled {
  nonce: string;
}

/**
 * The customer authorised the secure sign-in. THIS is what mints the handle,
 * server-side, which is why the model can never produce one itself.
 */
export interface AuthCompleted {
  nonce: string;
}

/** The customer edited a calculator input, and the page re-solved it. */
export interface CalculatorChanged {
  inputs?: Record<string, number>;

  result?: Record<string, number>;
}

/**
 * The customer opened a calculator off the help page's quick links, which
 * arrives already filled in with that link's figures and solved.
 */
export interface CalculatorOpened {
  /** One of emi, fd, eligibility. */
  kind?: string;

  inputs?: Record<string, number>;

  result?: Record<string, number>;
}

/** The customer dismissed the card picker. */
export interface CardCancelled {
  nonce: string;
}

/**
 * The customer saved the usage & limits form. The values are theirs — they
 * edited the toggles and sliders on screen, and this is the only copy.
 */
export interface CardControlsSaved {
  domestic_enabled?: boolean;

  international_enabled?: boolean;

  contactless_enabled?: boolean;

  online_enabled?: boolean;

  domestic_limit?: number;

  international_limit?: number;

  atm_cash_limit?: number;
}

/** The customer tapped a card in the picker. */
export interface CardSelected {
  nonce: string;

  card_id: string;
}

/** The customer opened one help-centre category themselves. */
export interface CategoryOpened {
  category: string;
}

/** The customer closed the helpline panel. */
export type ContactClosed = Record<string, never>;

/** The customer typed into one field of the open application. */
export interface FieldFilled {
  field: string;

  value?: string;
}

/**
 * The customer requested the forex card. The page mints the reference, so it
 * rides along — there is nowhere else Aria could read it.
 */
export interface ForexLeadSubmitted {
  reference?: string;
}

/** The customer opened the help centre's category index. */
export type HelpCenterOpened = Record<string, never>;

/** The customer went back to the Aura Bank home page. */
export type HomeOpened = Record<string, never>;

/** The customer paused the clip. */
export type VideoPaused = Record<string, never>;

/**
 * The clip crossed into its next chapter — the page's own clock, not a
 * gesture. Folded into the mirror in silence; see the module docstring.
 */
export interface VideoProgressed {
  step_index?: number;
}

/** The customer started the clip playing again. */
export type VideoResumed = Record<string, never>;

/** The customer tapped a step in the list, which jumps the clip to it. */
export interface VideoSeeked {
  start_sec?: number;

  step_index?: number;
}

// ── Shapes used by the messages above ──────────────────────────────

/**
 * An account as the picker and the balance card show it — the projection of
 * the bank's record that is safe to send, with the money left behind.
 */
export interface AccountRef {
  account_id: string;

  type: string;

  branch: string;

  nickname: string;

  masked_number: string;
}

/** One branch or ATM, as its card renders. */
export interface BranchResult {
  /** Branch or ATM name, in clean English. */
  name: string;

  /** One-line street address, in clean English. */
  address: string;

  /** Which of the two it is. */
  kind: 'branch' | 'atm';

  /** IFSC code — branches only. */
  ifsc: string | null;

  /** Opening hours, e.g. 'Mon-Sat, ten to four'. */
  hours: string | null;
}

/** A card's current usage and limit settings, as the form renders them. */
export interface CardControls {
  domestic_enabled: boolean;

  international_enabled: boolean;

  contactless_enabled: boolean;

  online_enabled: boolean;

  domestic_limit: number;

  international_limit: number;

  atm_cash_limit: number;
}

/** A credit card as the screen shows it. Never the real number. */
export interface CardRef {
  card_id: string;

  network: string;

  product: string;

  variant: string;

  masked_number: string;
}

/** One product in a comparison, as its column renders. */
export interface CompareItem {
  /** Short slug for this option, unique within the list. */
  id: string;

  /** The real Aura product name, in clean English. */
  name: string;

  /** Three or four short feature lines, in clean English. */
  features: string[];
}

/** One row of a statement. */
export interface StatementTxn {
  date: string;

  description: string;

  amount: number;

  kind: 'debit' | 'credit';
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'open_home'; payload: OpenHome }
  | { command: 'open_help_center'; payload: OpenHelpCenter }
  | { command: 'open_category'; payload: OpenCategory }
  | { command: 'open_article'; payload: OpenArticle }
  | { command: 'play_help_video'; payload: PlayHelpVideo }
  | { command: 'highlight_step'; payload: HighlightStep }
  | { command: 'seek_video'; payload: SeekVideo }
  | { command: 'pause_video'; payload: PauseVideo }
  | { command: 'resume_video'; payload: ResumeVideo }
  | { command: 'show_contact'; payload: ShowContact }
  | { command: 'run_calculator'; payload: RunCalculator }
  | { command: 'start_application'; payload: StartApplication }
  | { command: 'prefill_field'; payload: PrefillField }
  | { command: 'submit_application'; payload: SubmitApplication }
  | { command: 'compare'; payload: Compare }
  | { command: 'find_branch'; payload: FindBranch }
  | { command: 'show_checklist'; payload: ShowChecklist }
  | { command: 'send_to_phone'; payload: SendToPhone }
  | { command: 'raise_ticket'; payload: RaiseTicket }
  | { command: 'spotlight'; payload: Spotlight }
  | { command: 'show_forex_card'; payload: ShowForexCard }
  | { command: 'open_auth'; payload: OpenAuth }
  | { command: 'choose_account'; payload: ChooseAccount }
  | { command: 'show_balance'; payload: ShowBalance }
  | { command: 'show_statement'; payload: ShowStatement }
  | { command: 'choose_credit_card'; payload: ChooseCreditCard }
  | { command: 'show_card_controls'; payload: ShowCardControls };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'open_home',
  'open_help_center',
  'open_category',
  'open_article',
  'play_help_video',
  'highlight_step',
  'seek_video',
  'pause_video',
  'resume_video',
  'show_contact',
  'run_calculator',
  'start_application',
  'prefill_field',
  'submit_application',
  'compare',
  'find_branch',
  'show_checklist',
  'send_to_phone',
  'raise_ticket',
  'spotlight',
  'show_forex_card',
  'open_auth',
  'choose_account',
  'show_balance',
  'show_statement',
  'choose_credit_card',
  'show_card_controls',
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
  | { event: 'account_cancelled'; payload: AccountCancelled }
  | { event: 'account_selected'; payload: AccountSelected }
  | { event: 'application_started'; payload: ApplicationStarted }
  | { event: 'application_submitted'; payload: ApplicationSubmitted }
  | { event: 'article_opened'; payload: ArticleOpened }
  | { event: 'auth_cancelled'; payload: AuthCancelled }
  | { event: 'auth_completed'; payload: AuthCompleted }
  | { event: 'calculator_changed'; payload: CalculatorChanged }
  | { event: 'calculator_opened'; payload: CalculatorOpened }
  | { event: 'card_cancelled'; payload: CardCancelled }
  | { event: 'card_controls_saved'; payload: CardControlsSaved }
  | { event: 'card_selected'; payload: CardSelected }
  | { event: 'category_opened'; payload: CategoryOpened }
  | { event: 'contact_closed'; payload: ContactClosed }
  | { event: 'field_filled'; payload: FieldFilled }
  | { event: 'forex_lead_submitted'; payload: ForexLeadSubmitted }
  | { event: 'help_center_opened'; payload: HelpCenterOpened }
  | { event: 'home_opened'; payload: HomeOpened }
  | { event: 'video_paused'; payload: VideoPaused }
  | { event: 'video_progressed'; payload: VideoProgressed }
  | { event: 'video_resumed'; payload: VideoResumed }
  | { event: 'video_seeked'; payload: VideoSeeked };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'account_cancelled',
  'account_selected',
  'application_started',
  'application_submitted',
  'article_opened',
  'auth_cancelled',
  'auth_completed',
  'calculator_changed',
  'calculator_opened',
  'card_cancelled',
  'card_controls_saved',
  'card_selected',
  'category_opened',
  'contact_closed',
  'field_filled',
  'forex_lead_submitted',
  'help_center_opened',
  'home_opened',
  'video_paused',
  'video_progressed',
  'video_resumed',
  'video_seeked',
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
