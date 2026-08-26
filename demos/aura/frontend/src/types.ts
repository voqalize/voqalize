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
 *
 * **What the agent puts on screen is not declared here.** `actions.gen.ts` is
 * generated from the brain's `Action` classes by `voqalize types`, and the
 * twenty-odd types below that mirror one are derived from it. What is left is
 * the knowledge base, the screens the customer navigates alone, and the handful
 * of fields the browser adds for itself — a re-fire `nonce`, a `saved` flag.
 */

import type {
  AccountRef,
  CardRef,
  ChooseAccount,
  ChooseCreditCard,
  Compare,
  FindBranch,
  OpenAuth,
  RaiseTicket,
  RunCalculator,
  SendToPhone,
  ShowBalance,
  ShowCardControls,
  ShowChecklist,
  ShowStatement,
  Spotlight,
  StartApplication,
} from './actions.gen';

export type { BranchResult, CardControls, CompareItem, StatementTxn } from './actions.gen';

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

export type CalcKind = RunCalculator['kind'];
/** Inputs + computed result for the on-screen calculator. Numbers only. */
export type CalcState = RunCalculator;

export type Product = StartApplication['product'];
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

export type CompareState = Compare;

export type LocatorState = FindBranch;

export type ChecklistState = ShowChecklist;

/** Confirmation that the agent "sent" the guide to the customer's phone (mock). */
export type SentToPhone = SendToPhone & {
  /** Bumped per send, so a repeat of the same message re-shows the toast. */
  nonce: number;
};

/** A raised complaint / callback request with a reference number. */
export type Ticket = RaiseTicket;

/** General-purpose spotlight — rings the element with [data-aura-spotlight=target]. */
export type SpotlightState = Spotlight & {
  /** Bumped per call, so ringing the same element twice re-runs the animation. */
  nonce: number;
};

// ── Authenticated account access ──────────────────────────────────────────────

/** One of the signed-in customer's accounts (never carries the real number). */
export type Account = AccountRef;

/** The secure sign-in dialog the agent opens (show_auth_popup()). `nonce` is an
 *  opaque server token echoed back on authorise or cancel, so the server knows which
 *  dialog is being answered — keep it a string; it is NOT numeric. */
export type AuthPrompt = OpenAuth;

/** The signed-in identity, shown as a session badge once authorised. */
export interface AuthSession {
  name: string;
}

/** The account picker the agent opens (choose_account()). `nonce` is an opaque
 *  server token (string, not numeric). */
export type AccountPicker = ChooseAccount;

/** Balance view for one account (get_account_balance()). */
export type BalanceView = ShowBalance;

/** Statement view for one account over a date range (get_statement()). */
export type StatementView = ShowStatement;

// ── Credit-card controls + forex cross-sell ────────────────────────────────────

/** One of the signed-in customer's credit cards (never the real number). */
export type Card = CardRef;

/** The credit-card picker the agent opens (choose_credit_card()). `nonce` is an
 *  opaque server token (string, not numeric). */
export type CardPicker = ChooseCreditCard;

/** The card-controls form for one card (show_card_controls()). */
export type CardControlsView = ShowCardControls & {
  /** Set once the customer taps "Update controls". */
  saved: boolean;
};

/** The forex-card cross-sell screen + lead capture (show_forex_card()). */
export interface ForexView {
  submitted: boolean;
  reference?: string;
}
