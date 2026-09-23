/**
 * The kiosk's single source of truth.
 *
 * Two directions, both typed, and they are not symmetrical.
 *
 * Rohan's half arrives as `UiAction`s over `ui-command` and is replayed by
 * {@link applyAction} — an exhaustive switch that stops compiling the day the
 * brain declares one more action. That reducer is the *shared* mutation: it is
 * the only thing that decides what screen the totem is on.
 *
 * The customer's half leaves as `AppEvent`s over `ui-event`, one gesture at a
 * time, through {@link ByHand}. Every emit sits at the call site a person
 * actually reaches — never inside the reducer, which Rohan drives too. That is
 * why there is no echo suppression here: an action Rohan dispatched cannot
 * produce an event claiming the customer tapped something.
 *
 * **A hand alone is enough.** There is a gesture for every step — begin, answer,
 * acknowledge, open, close, choose, agree, type, restart — so a customer who
 * never says a word still reaches the QR. The screen still moves only because
 * the brain answered the event with an action: one source of truth, silent.
 *
 * The screen is never pushed back wholesale. Rohan knows what he dispatched, and
 * the events tell him the one thing he cannot know: that a hand moved first.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  useRef,
  type ReactNode,
} from 'react';
import {
  asUiAction,
  sendAppEvent,
  unhandledUiAction,
  type AppEvent,
  type ConfirmValue,
  type AskProfile,
  type AskValue,
  type OpenConsent,
  type ShowEligibility,
  type ShowQr,
  type ShowShortlist,
  type UiAction,
} from './actions.gen';
import { screenLanguageFor, type Language, type LanguageName } from './language';

/** Which of the eight screens the stage is showing. */
export type Screen =
  | 'attract'
  | 'discovery'
  | 'eligibility'
  | 'shortlist'
  | 'detail'
  | 'consent'
  | 'value'
  | 'handoff';

export interface KioskState {
  screen: Screen;
  /** The question on the stage, and the chips under it. */
  question: AskProfile | null;
  /** The value being asked for by typing, and the field it fills. */
  entry: AskValue | null;
  /**
   * The chip the customer just tapped, before Rohan has heard it. Purely an
   * echo: it keeps the pressed chip lit for the second it takes him to answer.
   */
  picked: Record<string, string>;
  /** The value being checked back, while it is being checked. */
  checking: ConfirmValue | null;
  /** Settled values, in the order they settled. */
  ledger: ConfirmValue[];
  /**
   * Whether the customer asked to see all three cards' terms at once. It is read
   * by the stage (which unfolds the rows) and written by the lower band's
   * button, so it cannot live in either one.
   */
  comparing: boolean;
  eligibility: ShowEligibility | null;
  shortlist: ShowShortlist | null;
  detailCardId: string | null;
  consent: OpenConsent | null;
  qr: ShowQr | null;
  /** Which of the screen's two copy sets is showing. */
  language: Language;
  /**
   * The language the conversation is in — any the brain declares. Wider than
   * `language`: in Tamil the conversation is Tamil and the screen stays English.
   */
  conversation: LanguageName;
}

const INITIAL: KioskState = {
  screen: 'attract',
  question: null,
  entry: null,
  picked: {},
  checking: null,
  ledger: [],
  comparing: false,
  eligibility: null,
  shortlist: null,
  detailCardId: null,
  consent: null,
  qr: null,
  language: 'en',
  conversation: 'English',
};

/** Replace this field's settled entry, or append it, keeping settle order. */
function settle(ledger: readonly ConfirmValue[], value: ConfirmValue): ConfirmValue[] {
  const at = ledger.findIndex((entry) => entry.field === value.field);
  if (at < 0) return [...ledger, value];
  const next = [...ledger];
  next[at] = value;
  return next;
}

/**
 * Rohan's half. Exhaustive over the action union — the default arm is a
 * compile-time assertion, not a runtime fallback.
 *
 * `confirm_value` deliberately does not move the screen: a mobile number gets
 * checked back on the consent screen, and jumping the customer to discovery to
 * do it would lose their place.
 */
function applyAction(state: KioskState, action: UiAction): KioskState {
  switch (action.command) {
    case 'show_attract':
      // Start over forgets everything but the language — as the brain's own
      // reset does, so the chip and Rohan's voice cannot come apart here.
      return { ...INITIAL, language: state.language, conversation: state.conversation };
    case 'ask_profile':
      return { ...state, screen: 'discovery', question: action.payload, checking: null };
    case 'ask_value':
      return { ...state, screen: 'value', entry: action.payload, question: null, checking: null };
    case 'confirm_value': {
      const value = action.payload;
      if (value.state === 'confirmed') {
        return { ...state, checking: null, ledger: settle(state.ledger, value) };
      }
      return { ...state, checking: value };
    }
    case 'show_eligibility':
      return {
        ...state,
        screen: 'eligibility',
        eligibility: action.payload,
        question: null,
        checking: null,
      };
    case 'show_shortlist':
      return {
        ...state,
        screen: 'shortlist',
        shortlist: action.payload,
        detailCardId: null,
        comparing: false,
      };
    case 'open_card_detail':
      return { ...state, screen: 'detail', detailCardId: action.payload.card_id };
    case 'open_consent':
      return { ...state, screen: 'consent', consent: action.payload };
    case 'show_qr':
      return { ...state, screen: 'handoff', qr: action.payload };
    case 'language_changed':
      return {
        ...state,
        conversation: action.payload.language,
        language: action.payload.screen_language,
      };
    default:
      return unhandledUiAction(action);
  }
}

/**
 * The two things a hand does that no action of Rohan's covers: light the chip it
 * just pressed while he is still hearing about it, and unfold all three cards.
 *
 * Nothing that *moves the screen* is in here. Every other gesture — begin,
 * answer, acknowledge, open, close, choose, agree, type, restart — is answered
 * by an action, and an action carries the whole row, so writing the same
 * transition here as well would be the transition table written twice, in two
 * languages, with nothing to keep the copies honest.
 */
type HandMutation =
  | { kind: 'pick'; field: string; value: string }
  | { kind: 'compare' }
  | { kind: 'language'; language: LanguageName };

function applyHand(state: KioskState, hand: HandMutation): KioskState {
  switch (hand.kind) {
    case 'pick':
      return { ...state, picked: { ...state.picked, [hand.field]: hand.value } };
    case 'compare':
      return { ...state, comparing: true };
    case 'language':
      // Shown at once rather than after Rohan answers: the chip is the one
      // control that must work before there is a call. His `language_changed`
      // arrives with the same value and re-renders idempotently.
      return { ...state, conversation: hand.language, language: screenLanguageFor(hand.language) };
  }
}

type Mutation = { from: 'agent'; action: UiAction } | { from: 'hand'; hand: HandMutation };

function reduce(state: KioskState, mutation: Mutation): KioskState {
  return mutation.from === 'agent'
    ? applyAction(state, mutation.action)
    : applyHand(state, mutation.hand);
}

/**
 * The customer's own hand. Each one does what it says and then tells Rohan it
 * happened — one gesture, one event, at the site a finger actually lands.
 */
export interface ByHand {
  /** Begin, without waiting for Rohan. He has already greeted; this is the answer. */
  begin: () => void;
  /** A chip under the question. A field already heard is a correction, not an answer. */
  answer: (field: string, value: string) => void;
  /** A typed value. A field already heard makes it a correction, not an entry. */
  enterValue: (field: string, value: string) => void;
  /** The yes on a value being checked back. */
  confirm: (field: string) => void;
  /** Read the verdict, ask for the cards. */
  acknowledgeEligibility: () => void;
  /** A shortlist row opened. Rohan repaints with `open_card_detail`. */
  tapCard: (cardId: string) => void;
  /** The comparison rows, opened across all three. */
  compare: () => void;
  /** Out of one card's detail and back to the three. */
  closeDetail: () => void;
  /** The card they want, chosen off the shortlist. */
  chooseCard: (cardId: string) => void;
  /** Consent, by hand. Nothing is submitted here — the desk does that. */
  consent: (cardId: string) => void;
  /** Start over. */
  restart: () => void;
  /** The language picker. Moves Rohan's voice as well as the screen's copy. */
  pickLanguage: (language: LanguageName) => void;
}

export type AgentSend = (event: string, payload?: unknown) => void;

export interface KioskStore {
  state: KioskState;
  byHand: ByHand;
  /** The channel events leave by; null until the call is live. */
  registerAgentSend: (send: AgentSend | null) => void;
  /** One `ui-command` off the wire. */
  handleUiCommand: (command: string, payload: unknown) => void;
}

const Ctx = createContext<KioskStore | null>(null);

export function KioskProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reduce, INITIAL);
  const sendRef = useRef<AgentSend | null>(null);
  // The ledger and the value in flight decide whether a tap is an answer or a
  // correction, and `byHand` must not be rebuilt every time either changes —
  // it is passed to every screen. A ref keeps the callbacks stable.
  const stateRef = useRef(state);
  stateRef.current = state;

  const emit = useCallback((event: AppEvent) => sendAppEvent(sendRef.current, event), []);

  const registerAgentSend = useCallback((send: AgentSend | null) => {
    sendRef.current = send;
  }, []);

  const handleUiCommand = useCallback((command: string, payload: unknown) => {
    const action = asUiAction(command, payload);
    if (action) dispatch({ from: 'agent', action });
  }, []);

  const byHand: ByHand = useMemo(
    () => ({
      begin: () => emit({ event: 'journey_started', payload: {} }),
      answer: (field, value) => {
        const current = stateRef.current;
        const heardBefore =
          current.checking?.field === field || current.ledger.some((e) => e.field === field);
        dispatch({ from: 'hand', hand: { kind: 'pick', field, value } });
        emit(
          heardBefore
            ? { event: 'value_edited', payload: { field, value } }
            : { event: 'profile_answered', payload: { field, value } },
        );
      },
      enterValue: (field, value) => {
        const current = stateRef.current;
        // Same test as a chip: typing over a value Rohan is checking back is the
        // correction and the rejection in one gesture.
        const heardBefore =
          current.checking?.field === field || current.ledger.some((e) => e.field === field);
        emit(
          heardBefore
            ? { event: 'value_edited', payload: { field, value } }
            : { event: 'value_entered', payload: { field, value } },
        );
      },
      confirm: (field) => emit({ event: 'value_confirmed', payload: { field } }),
      acknowledgeEligibility: () => emit({ event: 'eligibility_acknowledged', payload: {} }),
      tapCard: (cardId) => emit({ event: 'card_tapped', payload: { card_id: cardId } }),
      compare: () => {
        dispatch({ from: 'hand', hand: { kind: 'compare' } });
        emit({ event: 'card_compared', payload: {} });
      },
      closeDetail: () => emit({ event: 'card_detail_closed', payload: {} }),
      chooseCard: (cardId) => emit({ event: 'card_chosen', payload: { card_id: cardId } }),
      consent: (cardId) => emit({ event: 'consent_given', payload: { card_id: cardId } }),
      restart: () => emit({ event: 'restart_pressed', payload: {} }),
      pickLanguage: (language) => {
        dispatch({ from: 'hand', hand: { kind: 'language', language } });
        emit({ event: 'language_picked', payload: { language } });
      },
    }),
    [emit],
  );

  const store = useMemo<KioskStore>(
    () => ({ state, byHand, registerAgentSend, handleUiCommand }),
    [state, byHand, registerAgentSend, handleUiCommand],
  );

  return <Ctx.Provider value={store}>{children}</Ctx.Provider>;
}

export function useKiosk(): KioskStore {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useKiosk must be used within KioskProvider');
  return ctx;
}
