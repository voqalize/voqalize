/**
 * Aura Bank L1-support demo data model.
 *
 * The knowledge base is authored as a markdown wiki under `kb/` (the single
 * source of truth — see `kb.ts`, which loads and parses it at build time via
 * `import.meta.glob`). Articles carry flat front-matter + a markdown body; video
 * index files carry front-matter + a fenced ```json``` block of timed chapters
 * derived from the real Aura video transcripts.
 *
 * The voice agent drives the on-screen state through `ui_command` RTVI messages,
 * and the browser echoes a compact `screen_state` snapshot back (`state_sync`) so
 * the assistant always knows what the customer is looking at.
 */

export type CategoryId =
  | 'cards'
  | 'accounts'
  | 'netbanking'
  | 'payments'
  | 'loans-deposits'
  | 'support';

export interface Category {
  id: CategoryId;
  title: string;
  title_hi: string;
  blurb: string;
}

/** One timed chapter of a how-to video (start/end seconds + on-screen step). */
export interface VideoChapter {
  start: number;
  end: number;
  label: string;
  label_hi?: string;
  /** Hindi narration cue the assistant can paraphrase / the UI can caption. */
  say?: string;
}

/** A single official Aura how-to video, indexed by timed chapters. */
export interface VideoIndex {
  youtube_id: string;
  title: string;
  title_hi?: string;
  channel?: string;
  duration_sec?: number;
  topics: string[];
  /** Article this video belongs to. */
  article?: string;
  /** Default second to start at (skips the intro). */
  default_start: number;
  chapters: VideoChapter[];
  /** Prose description (markdown body of the video file). */
  description: string;
}

/** A help-centre article. */
export interface Article {
  id: string;
  title: string;
  title_en?: string;
  category: CategoryId;
  tags: string[];
  /** YouTube id of the how-to video, if any. */
  video?: string;
  /** Account-specific task — the customer must be logged in to actually do it. */
  needs_login: boolean;
  /** Featured / hero flow. */
  hero: boolean;
  related: string[];
  helpline?: string;
  /** Markdown body (rendered on the article page). */
  body: string;
}

export type Screen =
  | 'home'
  | 'help'
  | 'category'
  | 'article'
  | 'calculator'
  | 'apply'
  | 'compare'
  | 'locator'
  | 'checklist'
  | 'balance'
  | 'statement'
  | 'card_controls'
  | 'forex';

/** A queued imperative command for the YouTube player (re-fires via `nonce`). */
export interface VideoCommand {
  action: 'play' | 'seek' | 'pause' | 'resume';
  videoId?: string;
  startSec?: number;
  nonce: number;
}

// ── Interactive tools (all usable without a login) ─────────────────────────────

export type CalcKind = 'emi' | 'fd' | 'eligibility';
/** Inputs + computed result for the on-screen calculator. Numbers only. */
export interface CalcState {
  kind: CalcKind;
  inputs: Record<string, number>;
  result: Record<string, number>;
}

export type Product = 'savings' | 'credit_card' | 'loan';
export interface ApplyField {
  id: string;
  label: string;
  type: 'text' | 'tel' | 'email' | 'number';
  value: string;
}
export interface ApplyState {
  product: Product;
  fields: ApplyField[];
  submitted: boolean;
}

export interface CompareItem {
  id: string;
  name: string;
  /** A few short selling-point lines for this option. */
  features: string[];
}
export interface CompareState {
  kind: 'credit_card' | 'savings';
  items: CompareItem[];
  recommendId?: string;
  recommendReason?: string;
}

export interface BranchResult {
  name: string;
  address: string;
  kind: 'branch' | 'atm';
  ifsc?: string;
  hours?: string;
}
export interface LocatorState {
  pincode: string;
  results: BranchResult[];
}

export interface ChecklistState {
  title: string;
  items: string[];
}

/** Confirmation that the agent "sent" the guide to the customer's phone (mock). */
export interface SentToPhone {
  what: string;
  channel: 'whatsapp' | 'sms';
  number: string;
  nonce: number;
}

/** A raised complaint / callback request with a reference number. */
export interface Ticket {
  reference: string;
  topic: string;
  summary: string;
}

/** General-purpose spotlight — rings the element with [data-aura-spotlight=target]. */
export interface Spotlight {
  target: string;
  label?: string;
  nonce: number;
}

// ── Authenticated account access ──────────────────────────────────────────────

/** One of the signed-in customer's accounts (never carries the real number). */
export interface Account {
  account_id: string;
  type: string;
  branch: string;
  nickname?: string;
  masked_number: string;
}

/** The secure sign-in dialog the agent opens (authenticate()). `nonce` is an opaque
 *  server token echoed back on authorise so the server knows which request to
 *  complete — keep it a string; it is NOT numeric. */
export interface AuthPrompt {
  name: string;
  masked_mobile: string;
  nonce: string;
}

/** The signed-in identity, shown as a session badge once authorised. */
export interface AuthSession {
  name: string;
}

/** The account picker the agent opens (choose_account()). `nonce` is an opaque
 *  server token (string, not numeric). */
export interface AccountPicker {
  accounts: Account[];
  nonce: string;
}

/** Balance view for one account (get_account_balance()). */
export interface BalanceView {
  account: Account;
  balance: number;
  currency: string;
  as_of: string;
}

/** One statement row. */
export interface StatementTxn {
  date: string;
  description: string;
  amount: number;
  kind: 'debit' | 'credit';
}

/** Statement view for one account over a date range (get_statement()). */
export interface StatementView {
  account: Account;
  from: string;
  to: string;
  currency: string;
  transactions: StatementTxn[];
}

// ── Credit-card controls + forex cross-sell ────────────────────────────────────

/** One of the signed-in customer's credit cards (never the real number). */
export interface Card {
  card_id: string;
  network: string;
  product: string;
  variant?: string;
  masked_number: string;
}

/** The credit-card picker the agent opens (choose_credit_card()). `nonce` is an
 *  opaque server token (string, not numeric). */
export interface CardPicker {
  cards: Card[];
  nonce: string;
}

/** A card's current usage & limit settings — the customer edits these on screen. */
export interface CardControls {
  domestic_enabled: boolean;
  international_enabled: boolean;
  contactless_enabled: boolean;
  online_enabled: boolean;
  domestic_limit: number;
  international_limit: number;
  atm_cash_limit: number;
}

/** The card-controls form for one card (show_card_controls()). */
export interface CardControlsView {
  card: Card;
  credit_limit: number;
  controls: CardControls;
  /** Set once the customer taps "Update controls". */
  saved: boolean;
}

/** The forex-card cross-sell screen + lead capture (show_forex_card()). */
export interface ForexView {
  submitted: boolean;
  reference?: string;
}
