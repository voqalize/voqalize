// Generated from aura/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types aura/backend/brain.py -o aura/frontend/src/actions.gen.ts
//
// Every field is present on the wire, `null` included, so nothing here is
// optional and no runtime validation is needed to narrow on `command`.

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

// ── Shapes used by the actions above ───────────────────────────────

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
