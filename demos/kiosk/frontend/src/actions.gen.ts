// Generated from kiosk/backend/brain.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types kiosk/backend/brain.py -o kiosk/frontend/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/** Back to the attract loop: the totem as a passer-by finds it. */
export type ShowAttract = Record<string, never>;

/** One discovery question, with the closed set of answers beside it. */
export interface AskProfile {
  field: string;

  question: string;

  options: ProfileOption[];
}

/**
 * One value for the customer to type in themselves.
 *
 * `kind` is the keypad the totem puts under their finger — `tel` for a
 * mobile number, `text` for a PAN — and `label` is already in this
 * session's language, because the screen is read and not spoken.
 */
export interface AskValue {
  field: string;

  label: string;

  kind: string;
}

/**
 * A value the customer spoke, as the screen holds it.
 *
 * `state` is one of `heard` (shown, nothing asked), `confirming` (read
 * back, waiting on a yes) or `confirmed` (settled). `masked` is the safe
 * form for a totem in a branch, and it is what the screen shows by default.
 */
export interface ConfirmValue {
  field: string;

  display: string;

  masked: string;

  state: string;
}

/**
 * The verdict, as a band and reasons. Never a score, and never a decision —
 * `band` is one of `wide`, `standard` or `secured`.
 */
export interface ShowEligibility {
  band: string;

  reasons: string[];

  line_estimate: string;
}

/** Three cards, ranked, one of them recommended. */
export interface ShowShortlist {
  cards: CardView[];

  recommended_id: string;

  why: string;
}

/** Open one card full screen. Also the parameter of the tool that sends it. */
export interface OpenCardDetail {
  card_id: string;
}

/**
 * The consent panel for one card: what the customer is agreeing to, in the
 * bank's own words. The bullets are written in Python, never by the model.
 */
export interface OpenConsent {
  card_id: string;

  bullets: string[];
}

/** The last screen: a QR code to carry to the desk. */
export interface ShowQr {
  caption: string;
}

/**
 * The conversation moved language. Not a screen: the chip on the brand bar
 * follows it, and the screen's own copy follows it only as far as copy exists.
 */
export interface LanguageChanged {
  language: string;

  native: string;

  screen_language: 'en' | 'hi';
}

/** They touched the attract screen to begin. */
export type JourneyStarted = Record<string, never>;

/** They tapped one of the answers on screen instead of saying it. */
export interface ProfileAnswered {
  field: string;

  value: string;
}

/** They have read what they are likely eligible for and want the cards. */
export type EligibilityAcknowledged = Record<string, never>;

/** They opened a card on the shortlist themselves. */
export interface CardTapped {
  card_id: string;
}

/** They closed a card and went back to the three. */
export type CardDetailClosed = Record<string, never>;

/** They put the shortlist side by side themselves. */
export type CardCompared = Record<string, never>;

/** They settled on one card, with their hand. */
export interface CardChosen {
  card_id: string;
}

/** They accepted the consent panel on screen. */
export interface ConsentGiven {
  card_id: string;
}

/** They typed a value in themselves rather than reading it out. */
export interface ValueEntered {
  field: string;

  value: string;
}

/** They confirmed a value on screen rather than out loud. */
export interface ValueConfirmed {
  field: string;
}

/** They corrected a value by hand. Theirs wins; it is not read back again. */
export interface ValueEdited {
  field: string;

  value: string;
}

/**
 * They pressed Start over. The only way back to the attract loop — there is
 * no idle timeout and nothing resets itself.
 */
export type RestartPressed = Record<string, never>;

/**
 * They tapped the language chip. Not a step in the journey — it moves the
 * conversation, so it is handled beside the journey rather than inside it.
 */
export interface LanguagePicked {
  language: 'English' | 'Hindi' | 'Bengali' | 'Gujarati' | 'Kannada' | 'Malayalam' | 'Marathi' | 'Punjabi' | 'Tamil' | 'Telugu' | 'Assamese' | 'Bodo' | 'Dogri' | 'Kashmiri' | 'Konkani' | 'Maithili' | 'Manipuri' | 'Nepali' | 'Odia' | 'Sanskrit' | 'Santali' | 'Sindhi' | 'Urdu';
}

// ── Shapes used by the messages above ──────────────────────────────

/**
 * One card as the totem renders it — display forms only, every one of them
 * a string the voice must never be handed.
 *
 * `eligible` is false for a card the customer does not clear yet. The
 * shortlist always shows three, so a customer who clears only the secured card
 * still sees where they can go next.
 */
export interface CardView {
  id: string;

  name: string;

  fee: string;

  waiver: string;

  reward: string;

  perk: string;

  line_estimate: string;

  requirement: string;

  eligible: boolean;
}

/**
 * One answer the screen offers. The value is the closed token the rules run
 * on; the two labels are what the customer reads.
 */
export interface ProfileOption {
  value: string;

  label: string;

  label_hi: string;
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'show_attract'; payload: ShowAttract }
  | { command: 'ask_profile'; payload: AskProfile }
  | { command: 'ask_value'; payload: AskValue }
  | { command: 'confirm_value'; payload: ConfirmValue }
  | { command: 'show_eligibility'; payload: ShowEligibility }
  | { command: 'show_shortlist'; payload: ShowShortlist }
  | { command: 'open_card_detail'; payload: OpenCardDetail }
  | { command: 'open_consent'; payload: OpenConsent }
  | { command: 'show_qr'; payload: ShowQr }
  | { command: 'language_changed'; payload: LanguageChanged };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'show_attract',
  'ask_profile',
  'ask_value',
  'confirm_value',
  'show_eligibility',
  'show_shortlist',
  'open_card_detail',
  'open_consent',
  'show_qr',
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
  | { event: 'journey_started'; payload: JourneyStarted }
  | { event: 'profile_answered'; payload: ProfileAnswered }
  | { event: 'eligibility_acknowledged'; payload: EligibilityAcknowledged }
  | { event: 'card_tapped'; payload: CardTapped }
  | { event: 'card_detail_closed'; payload: CardDetailClosed }
  | { event: 'card_compared'; payload: CardCompared }
  | { event: 'card_chosen'; payload: CardChosen }
  | { event: 'consent_given'; payload: ConsentGiven }
  | { event: 'value_entered'; payload: ValueEntered }
  | { event: 'value_confirmed'; payload: ValueConfirmed }
  | { event: 'value_edited'; payload: ValueEdited }
  | { event: 'restart_pressed'; payload: RestartPressed }
  | { event: 'language_picked'; payload: LanguagePicked };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'journey_started',
  'profile_answered',
  'eligibility_acknowledged',
  'card_tapped',
  'card_detail_closed',
  'card_compared',
  'card_chosen',
  'consent_given',
  'value_entered',
  'value_confirmed',
  'value_edited',
  'restart_pressed',
  'language_picked',
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
