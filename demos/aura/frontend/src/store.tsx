/**
 * AuraStore — the single source of truth for the Aura Bank L1-support demo.
 *
 * Both the customer (clicking the help centre) and Aria (via `ui-command` RTVI
 * messages) call the SAME actions, so the screen stays consistent whoever is
 * driving. Navigation is plain React state — never the router — so the
 * `PipecatClient` mounted alongside never unmounts and the call stays live
 * across screens.
 *
 * Both directions are typed and fine-grained. Aria's half arrives as
 * `UiAction`s and is replayed by `handleUiCommand`; the customer's half leaves
 * as `AppEvent`s over `ui-event`, one gesture at a time, through `byHand`. The
 * screen is never echoed back — a whole-state push has to be diffed to find out
 * what changed, and every diff is a place the two pictures can part company.
 *
 * `byHand` is the customer's side of that, and it is why echo suppression is not
 * a thing here: an emit lives at the call site a person actually reaches, never
 * inside the mutation Aria shares with them. What only the browser holds — the
 * calculator it re-solved, the forex reference it minted — rides along; what is
 * merely on screen does not, because Aria reads that back with
 * `get_screen_context`.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { asUiAction, sendAppEvent, unhandledUiAction, type AppEvent } from './actions.gen';
import { chapterAt, getArticle, getVideo } from './kb';
import type {
  Account,
  AccountPicker,
  ApplyField,
  ApplyState,
  AuthPrompt,
  AuthSession,
  BalanceView,
  CalcKind,
  CalcState,
  Card,
  CardControls,
  CardControlsView,
  CardPicker,
  CategoryId,
  CompareState,
  ForexView,
  LocatorState,
  Product,
  Screen,
  SentToPhone,
  SpotlightState,
  StatementView,
  Ticket,
  VideoCommand,
} from './types';

export type AgentSend = (event: string, payload?: unknown) => void;

// ── Calculator maths (kept identical to the brain's Python so a spoken figure
//    and an edited-on-screen figure always agree) ─────────────────────────────
const round = (n: number) => Math.round(n);
export function computeCalc(kind: CalcKind, i: Record<string, number>): Record<string, number> {
  if (kind === 'emi') {
    const p = i.principal || 0;
    const n = i.tenure_months || 0;
    const r = (i.annual_rate || 0) / 1200;
    if (!p || !n) return { emi: 0, total_interest: 0, total_payment: 0 };
    const emi = r > 0 ? (p * r * (1 + r) ** n) / ((1 + r) ** n - 1) : p / n;
    const total = emi * n;
    return { emi: round(emi), total_payment: round(total), total_interest: round(total - p) };
  }
  if (kind === 'fd') {
    const p = i.principal || 0;
    const years = (i.tenure_months || 0) / 12;
    const r = (i.annual_rate || 0) / 100;
    const maturity = p * (1 + r / 4) ** (4 * years); // quarterly compounding
    return { maturity: round(maturity), interest: round(maturity - p) };
  }
  // eligibility: FOIR 50% of income, net of existing EMIs, inverted to a principal.
  const income = i.monthly_income || 0;
  const existing = i.existing_emi || 0;
  const n = i.tenure_months || 0;
  const r = (i.annual_rate || 0) / 1200;
  const maxEmi = Math.max(0, 0.5 * income - existing);
  const maxLoan = r > 0 && n > 0 ? (maxEmi * ((1 + r) ** n - 1)) / (r * (1 + r) ** n) : maxEmi * n;
  return { max_emi: round(maxEmi), max_loan: round(maxLoan) };
}

// Sensible calculator defaults — identical to the brain's _CALC_DEFAULTS. The
// customer only needs to give the amount/income; rate, tenure and existing EMIs
// fall back to these so the form is never blank.
const CALC_DEFAULTS: Record<CalcKind, Record<string, number>> = {
  emi: { annual_rate: 10.5, tenure_months: 60 },
  fd: { annual_rate: 7.0, tenure_months: 60 },
  eligibility: { annual_rate: 10.5, tenure_months: 60, existing_emi: 0 },
};

// Application field templates per product (the form the agent fills by voice).
const APPLY_TEMPLATES: Record<Product, ApplyField[]> = {
  savings: [
    { id: 'name', label: 'Full name', type: 'text', value: '' },
    { id: 'mobile', label: 'Mobile number', type: 'tel', value: '' },
    { id: 'email', label: 'Email', type: 'email', value: '' },
    { id: 'city', label: 'City', type: 'text', value: '' },
    { id: 'pan', label: 'PAN', type: 'text', value: '' },
  ],
  credit_card: [
    { id: 'name', label: 'Full name', type: 'text', value: '' },
    { id: 'mobile', label: 'Mobile number', type: 'tel', value: '' },
    { id: 'email', label: 'Email', type: 'email', value: '' },
    { id: 'employment', label: 'Employment type', type: 'text', value: '' },
    { id: 'monthly_income', label: 'Monthly income (₹)', type: 'number', value: '' },
  ],
  loan: [
    { id: 'name', label: 'Full name', type: 'text', value: '' },
    { id: 'mobile', label: 'Mobile number', type: 'tel', value: '' },
    { id: 'loan_amount', label: 'Loan amount (₹)', type: 'number', value: '' },
    { id: 'monthly_income', label: 'Monthly income (₹)', type: 'number', value: '' },
    { id: 'tenure_years', label: 'Tenure (years)', type: 'number', value: '' },
  ],
};

export interface AuraActions {
  openHome: () => void;
  openHelpCenter: () => void;
  openCategory: (category: string) => void;
  openArticle: (articleId: string) => void;
  playVideo: (videoId: string, startSec: number) => void;
  highlightStep: (index: number) => void;
  seekVideo: (startSec: number) => void;
  pauseVideo: () => void;
  resumeVideo: () => void;
  showContact: (topic: string) => void;
  closeContact: () => void;
  /** The YouTube player reports its current time so chapters auto-highlight. */
  setPlaybackTime: (t: number) => void;
  // ── interactive tools ──
  runCalculator: (kind: CalcKind, inputs: Record<string, number>, result?: Record<string, number>) => void;
  recomputeCalc: (inputs: Record<string, number>) => void;
  startApplication: (product: Product) => void;
  prefillField: (id: string, value: string) => void;
  submitApplication: () => void;
  showCompare: (state: CompareState) => void;
  showLocator: (pincode: string, results: LocatorState['results']) => void;
  showChecklist: (title: string, items: string[]) => void;
  sendToPhone: (what: string, channel: 'whatsapp' | 'sms', number: string) => void;
  closeSentToPhone: () => void;
  raiseTicket: (reference: string, topic: string, summary: string) => void;
  closeTicket: () => void;
  spotlight: (target: string, label: string) => void;
  // ── authenticated account access ──
  openAuth: (prompt: AuthPrompt) => void;
  /** Customer taps "Authorise": tells the server (auth_complete) + shows the badge. */
  confirmAuth: () => void;
  cancelAuth: () => void;
  openAccountPicker: (picker: AccountPicker) => void;
  /** Customer taps an account: tells the server (account_selected) + records it. */
  selectAccount: (account: Account) => void;
  /** Customer dismisses the picker: tells the server (account_cancelled). */
  cancelAccount: () => void;
  showBalance: (view: BalanceView) => void;
  showStatement: (view: StatementView) => void;
  // ── credit-card controls + forex cross-sell ──
  openCardPicker: (picker: CardPicker) => void;
  /** Customer taps a card: tells the server (card_selected) + records it. */
  selectCard: (card: Card) => void;
  /** Customer dismisses the card picker: tells the server (card_cancelled). */
  cancelCard: () => void;
  showCardControls: (view: CardControlsView) => void;
  /** Customer taps "Update controls": commit the edited values + mark saved. */
  saveCardControls: (controls: CardControls) => void;
  showForexCard: () => void;
  /** Customer taps "Request this card": capture the forex lead. */
  submitForexLead: () => void;
}

export interface AuraStore extends AuraActions {
  screen: Screen;
  category: CategoryId | null;
  articleId: string | null;
  /** Video currently loaded in the player (cued or playing). */
  videoId: string | null;
  /** Imperative command for the player; re-fires via `nonce`. */
  videoCmd: VideoCommand | null;
  playing: boolean;
  /** Step the agent explicitly highlighted (used when paused). */
  explicitStep: number;
  /** Step highlighted right now (playback position while playing, else explicit). */
  currentStep: number;
  contactOpen: boolean;
  contactTopic: string;
  // interactive-tool state (null unless that surface is active)
  calc: CalcState | null;
  apply: ApplyState | null;
  compare: CompareState | null;
  locator: LocatorState | null;
  checklist: { title: string; items: string[] } | null;
  sentToPhone: SentToPhone | null;
  ticket: Ticket | null;
  spotlightState: SpotlightState | null;
  // authenticated account access (null unless active)
  authSession: AuthSession | null;
  authPrompt: AuthPrompt | null;
  accountPicker: AccountPicker | null;
  selectedAccount: Account | null;
  balance: BalanceView | null;
  statement: StatementView | null;
  // credit-card controls + forex cross-sell (null unless active)
  cardPicker: CardPicker | null;
  selectedCard: Card | null;
  cardControls: CardControlsView | null;
  forex: ForexView | null;
  agentSend: AgentSend | null;
  byHand: ByHand;
  registerAgentSend: (fn: AgentSend | null) => void;
  handleUiCommand: (command: string, payload: unknown) => void;
}

/**
 * The customer's own hand, on everything Aria can drive too. Each one does what
 * her twin does and then says so — one gesture, one event. She is told *that*
 * they moved the screen, never what it now says: she reads that back with
 * `get_screen_context`.
 *
 * The gestures only a person can make — closing the helpline panel, answering a
 * sign-in, saving card controls — emit from the action itself, since there is no
 * twin of Aria's to confuse them with.
 */
export interface ByHand {
  openHome: () => void;
  openHelpCenter: () => void;
  openCategory: (category: string) => void;
  openArticle: (articleId: string) => void;
  pauseVideo: () => void;
  resumeVideo: () => void;
  /** Tapping a step in the list, which is what jumps the clip. */
  seekVideo: (startSec: number, stepIndex: number) => void;
  runCalculator: (kind: CalcKind, inputs: Record<string, number>) => void;
  startApplication: (product: Product) => void;
  prefillField: (id: string, value: string) => void;
  submitApplication: () => void;
}

const Ctx = createContext<AuraStore | null>(null);

export function AuraProvider({ children }: { children: ReactNode }) {
  const [screen, setScreen] = useState<Screen>('home');
  const [category, setCategory] = useState<CategoryId | null>(null);
  const [articleId, setArticleId] = useState<string | null>(null);
  const [videoId, setVideoId] = useState<string | null>(null);
  const [videoCmd, setVideoCmd] = useState<VideoCommand | null>(null);
  const [playing, setPlaying] = useState(false);
  const [explicitStep, setExplicitStep] = useState(0);
  const [playbackTime, setPlaybackTimeState] = useState(0);
  const [contactOpen, setContactOpen] = useState(false);
  const [contactTopic, setContactTopic] = useState('');
  const [calc, setCalc] = useState<CalcState | null>(null);
  const [apply, setApply] = useState<ApplyState | null>(null);
  const [compare, setCompare] = useState<CompareState | null>(null);
  const [locator, setLocator] = useState<LocatorState | null>(null);
  const [checklist, setChecklist] = useState<{ title: string; items: string[] } | null>(null);
  const [sentToPhone, setSentToPhone] = useState<SentToPhone | null>(null);
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [spotlightState, setSpotlightState] = useState<SpotlightState | null>(null);
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [authPrompt, setAuthPrompt] = useState<AuthPrompt | null>(null);
  const [accountPicker, setAccountPicker] = useState<AccountPicker | null>(null);
  const [selectedAccount, setSelectedAccount] = useState<Account | null>(null);
  const [balance, setBalance] = useState<BalanceView | null>(null);
  const [statement, setStatement] = useState<StatementView | null>(null);
  const [cardPicker, setCardPicker] = useState<CardPicker | null>(null);
  const [selectedCard, setSelectedCard] = useState<Card | null>(null);
  const [cardControls, setCardControls] = useState<CardControlsView | null>(null);
  const [forex, setForex] = useState<ForexView | null>(null);
  const agentSendRef = useRef<AgentSend | null>(null);
  const [, forceTick] = useState(0);
  const nonceRef = useRef(0);
  const nextNonce = () => (nonceRef.current += 1);
  // The step Aria was last told the clip had reached, so the player's per-second
  // tick costs her one event per chapter rather than one per second.
  const stepRef = useRef(-1);

  const emit = useCallback((event: AppEvent) => sendAppEvent(agentSendRef.current, event), []);

  const registerAgentSend = useCallback((fn: AgentSend | null) => {
    agentSendRef.current = fn;
    forceTick((t) => t + 1);
  }, []);

  const openHome = useCallback(() => {
    setScreen('home');
    setContactOpen(false);
  }, []);

  const openHelpCenter = useCallback(() => {
    setScreen('help');
    setContactOpen(false);
  }, []);

  const openCategory = useCallback(
    (cat: string) => {
      setCategory(cat as CategoryId);
      setScreen('category');
      setContactOpen(false);
    },
    [],
  );

  const openArticle = useCallback(
    (id: string) => {
      const article = getArticle(id);
      if (!article) return;
      setArticleId(id);
      setCategory(article.category);
      setScreen('article');
      setContactOpen(false);
      // Cue the article's video (paused at its default start); the agent plays it
      // explicitly with play_help_video.
      const vid = article.video ?? null;
      setVideoId(vid);
      setPlaying(false);
      setExplicitStep(0);
      setPlaybackTimeState(0);
    },
    [],
  );

  const playVideo = useCallback(
    (vid: string, startSec: number) => {
      const video = getVideo(vid);
      setVideoId(vid);
      setPlaying(true);
      setExplicitStep(video ? chapterAt(video, startSec) : 0);
      setPlaybackTimeState(startSec);
      // Ensure the article housing this video is on screen.
      if (video?.article) {
        setArticleId(video.article);
        const a = getArticle(video.article);
        if (a) setCategory(a.category);
        setScreen('article');
      }
      setContactOpen(false);
      setVideoCmd({ action: 'play', videoId: vid, startSec, nonce: nextNonce() });
    },
    [],
  );

  const seekVideo = useCallback(
    (startSec: number) => {
      const video = getVideo(videoId ?? undefined);
      if (video) setExplicitStep(chapterAt(video, startSec));
      setPlaybackTimeState(startSec);
      setPlaying(true);
      setVideoCmd({ action: 'seek', startSec, nonce: nextNonce() });
    },
    [videoId],
  );

  const highlightStep = useCallback(
    (index: number) => {
      setExplicitStep(index);
    },
    [],
  );

  const pauseVideo = useCallback(() => {
    setPlaying(false);
    setVideoCmd({ action: 'pause', nonce: nextNonce() });
  }, []);

  const resumeVideo = useCallback(() => {
    setPlaying(true);
    setVideoCmd({ action: 'resume', nonce: nextNonce() });
  }, []);

  const showContact = useCallback(
    (topic: string) => {
      setContactTopic(topic);
      setContactOpen(true);
    },
    [],
  );

  const closeContact = useCallback(() => {
    setContactOpen(false);
    emit({ event: 'contact_closed', payload: {} });
  }, [emit]);

  // ── interactive tools ───────────────────────────────────────────────────────
  const runCalculator = useCallback(
    (kind: CalcKind, inputs: Record<string, number>, result?: Record<string, number>) => {
      const merged = { ...CALC_DEFAULTS[kind], ...inputs };
      setCalc({ kind, inputs: merged, result: result ?? computeCalc(kind, merged) });
      setScreen('calculator');
    },
    [],
  );

  // Customer edits an input → recompute live. This figure exists nowhere but the
  // page, so unlike a navigation gesture the event carries it.
  const recomputeCalc = useCallback(
    (inputs: Record<string, number>) => {
      if (!calc) return;
      const result = computeCalc(calc.kind, inputs);
      setCalc({ ...calc, inputs, result });
      emit({ event: 'calculator_changed', payload: { inputs, result } });
    },
    [calc, emit],
  );

  const startApplication = useCallback(
    (product: Product) => {
      setApply({ product, fields: APPLY_TEMPLATES[product].map((f) => ({ ...f })), submitted: false });
      setScreen('apply');
    },
    [],
  );

  const prefillField = useCallback(
    (id: string, value: string) => {
      setApply((a) =>
        a ? { ...a, fields: a.fields.map((f) => (f.id === id ? { ...f, value } : f)) } : a,
      );
    },
    [],
  );

  const submitApplication = useCallback(() => {
    setApply((a) => (a ? { ...a, submitted: true } : a));
  }, []);

  const showCompare = useCallback(
    (state: CompareState) => {
      setCompare(state);
      setScreen('compare');
    },
    [],
  );

  const showLocator = useCallback(
    (pincode: string, results: LocatorState['results']) => {
      setLocator({ pincode, results });
      setScreen('locator');
    },
    [],
  );

  const showChecklist = useCallback(
    (title: string, items: string[]) => {
      setChecklist({ title, items });
      setScreen('checklist');
    },
    [],
  );

  const sendToPhone = useCallback(
    (what: string, channel: 'whatsapp' | 'sms', number: string) => {
      setSentToPhone({ what, channel, number, nonce: nextNonce() });
    },
    [],
  );
  const closeSentToPhone = useCallback(() => setSentToPhone(null), []);

  const raiseTicket = useCallback(
    (reference: string, topic: string, summary: string) => {
      setTicket({ reference, topic, summary });
    },
    [],
  );
  const closeTicket = useCallback(() => setTicket(null), []);

  const spotlight = useCallback(
    (target: string, label: string) => {
      setSpotlightState({ target, label, nonce: nextNonce() });
    },
    [],
  );

  // ── authenticated account access ────────────────────────────────────────────
  const openAuth = useCallback(
    (prompt: AuthPrompt) => {
      setAuthPrompt(prompt);
    },
    [],
  );

  // Customer authorises the on-screen sign-in: tell the server (it mints the token
  // only on receiving this) and reflect the signed-in identity locally.
  const confirmAuth = useCallback(() => {
    if (!authPrompt) return;
    emit({ event: 'auth_completed', payload: { nonce: authPrompt.nonce } });
    setAuthSession({ name: authPrompt.name });
    setAuthPrompt(null);
  }, [authPrompt, emit]);

  // Customer declines the sign-in: tell the server, so the agent hears they closed
  // it rather than going on believing a sheet is still up in front of them.
  const cancelAuth = useCallback(() => {
    if (authPrompt) emit({ event: 'auth_cancelled', payload: { nonce: authPrompt.nonce } });
    setAuthPrompt(null);
  }, [authPrompt, emit]);

  const openAccountPicker = useCallback(
    (picker: AccountPicker) => {
      setAccountPicker(picker);
    },
    [],
  );

  // Customer picks an account: tell the server (account_selected) and record it so
  // the balance/statement screens can header it.
  const selectAccount = useCallback(
    (account: Account) => {
      if (accountPicker) {
        emit({
          event: 'account_selected',
          payload: { nonce: accountPicker.nonce, account_id: account.account_id },
        });
      }
      setAccountPicker(null);
      setSelectedAccount(account);
    },
    [accountPicker, emit],
  );

  const cancelAccount = useCallback(() => {
    if (accountPicker) emit({ event: 'account_cancelled', payload: { nonce: accountPicker.nonce } });
    setAccountPicker(null);
  }, [accountPicker, emit]);

  const showBalance = useCallback(
    (view: BalanceView) => {
      setBalance(view);
      setSelectedAccount(view.account);
      setScreen('balance');
    },
    [],
  );

  const showStatement = useCallback(
    (view: StatementView) => {
      setStatement(view);
      setSelectedAccount(view.account);
      setScreen('statement');
    },
    [],
  );

  // ── credit-card controls + forex cross-sell ─────────────────────────────────
  const openCardPicker = useCallback(
    (picker: CardPicker) => {
      setCardPicker(picker);
    },
    [],
  );

  // Customer picks a card: tell the server (card_selected) and record it so the
  // controls screen can header it.
  const selectCard = useCallback(
    (c: Card) => {
      if (cardPicker) {
        emit({ event: 'card_selected', payload: { nonce: cardPicker.nonce, card_id: c.card_id } });
      }
      setCardPicker(null);
      setSelectedCard(c);
    },
    [cardPicker, emit],
  );

  const cancelCard = useCallback(() => {
    if (cardPicker) emit({ event: 'card_cancelled', payload: { nonce: cardPicker.nonce } });
    setCardPicker(null);
  }, [cardPicker, emit]);

  const showCardControls = useCallback(
    (view: CardControlsView) => {
      setCardControls(view);
      setSelectedCard(view.card);
      setScreen('card_controls');
    },
    [],
  );

  const saveCardControls = useCallback(
    (controls: CardControls) => {
      setCardControls((c) => (c ? { ...c, controls, saved: true } : c));
      emit({ event: 'card_controls_saved', payload: controls });
    },
    [emit],
  );

  const showForexCard = useCallback(() => {
    setForex({ submitted: false });
    setScreen('forex');
  }, []);

  const submitForexLead = useCallback(() => {
    // Minted here rather than inside the setter so it can ride the event: the
    // page is the only place this reference exists.
    const reference = `FX${Math.floor(1_000_000 + Math.random() * 8_999_999)}`;
    setForex((f) => (f ? { ...f, submitted: true, reference } : f));
    emit({ event: 'forex_lead_submitted', payload: { reference } });
  }, [emit]);

  // Playback time drives chapter auto-highlight; throttle re-renders to whole
  // seconds so the muted video keeps the step list in sync without churn.
  const setPlaybackTime = useCallback(
    (t: number) => {
      setPlaybackTimeState((prev) => (Math.floor(prev) === Math.floor(t) ? prev : t));
      const v = getVideo(videoId ?? undefined);
      if (!v) return;
      const step = chapterAt(v, t);
      if (step === stepRef.current) return;
      stepRef.current = step;
      emit({ event: 'video_progressed', payload: { step_index: step } });
    },
    [emit, videoId],
  );

  const video = getVideo(videoId ?? undefined);
  const currentStep = useMemo(() => {
    if (playing && video) return chapterAt(video, playbackTime);
    return explicitStep;
  }, [playing, video, playbackTime, explicitStep]);

  const byHand: ByHand = useMemo(
    () => ({
      openHome: () => {
        openHome();
        emit({ event: 'home_opened', payload: {} });
      },
      openHelpCenter: () => {
        openHelpCenter();
        emit({ event: 'help_center_opened', payload: {} });
      },
      openCategory: (cat) => {
        openCategory(cat);
        emit({ event: 'category_opened', payload: { category: cat } });
      },
      openArticle: (id) => {
        openArticle(id);
        emit({ event: 'article_opened', payload: { article_id: id } });
      },
      pauseVideo: () => {
        pauseVideo();
        emit({ event: 'video_paused', payload: {} });
      },
      resumeVideo: () => {
        resumeVideo();
        emit({ event: 'video_resumed', payload: {} });
      },
      seekVideo: (startSec, stepIndex) => {
        seekVideo(startSec);
        stepRef.current = stepIndex;
        emit({ event: 'video_seeked', payload: { start_sec: startSec, step_index: stepIndex } });
      },
      runCalculator: (kind, inputs) => {
        // The figures come off a quick link on the page, so Aria cannot know
        // them: solve here and send both sides.
        const merged = { ...CALC_DEFAULTS[kind], ...inputs };
        const result = computeCalc(kind, merged);
        runCalculator(kind, merged, result);
        emit({ event: 'calculator_opened', payload: { kind, inputs: merged, result } });
      },
      startApplication: (product) => {
        startApplication(product);
        emit({ event: 'application_started', payload: { product } });
      },
      prefillField: (id, value) => {
        prefillField(id, value);
        emit({ event: 'field_filled', payload: { field: id, value } });
      },
      submitApplication: () => {
        submitApplication();
        emit({ event: 'application_submitted', payload: {} });
      },
    }),
    [
      emit,
      openHome,
      openHelpCenter,
      openCategory,
      openArticle,
      pauseVideo,
      resumeVideo,
      seekVideo,
      runCalculator,
      startApplication,
      prefillField,
      submitApplication,
    ],
  );

  const handleUiCommand = useCallback(
    (command: string, payload: unknown) => {
      const action = asUiAction(command, payload);
      if (!action) return;
      switch (action.command) {
        case 'open_home':
          openHome();
          break;
        case 'open_help_center':
          openHelpCenter();
          break;
        case 'open_category':
          openCategory(action.payload.category);
          break;
        case 'open_article':
          openArticle(action.payload.article_id);
          break;
        case 'play_help_video':
          playVideo(action.payload.video_id, action.payload.start_sec);
          break;
        case 'highlight_step':
          highlightStep(action.payload.index);
          break;
        case 'seek_video':
          seekVideo(action.payload.start_sec);
          break;
        case 'pause_video':
          pauseVideo();
          break;
        case 'resume_video':
          resumeVideo();
          break;
        case 'show_contact':
          showContact(action.payload.topic);
          break;
        case 'run_calculator': {
          const { kind, inputs, result } = action.payload;
          runCalculator(kind, inputs, Object.keys(result).length ? result : undefined);
          break;
        }
        case 'start_application':
          startApplication(action.payload.product);
          break;
        case 'prefill_field':
          prefillField(action.payload.field, action.payload.value);
          break;
        case 'submit_application':
          submitApplication();
          break;
        case 'compare':
          showCompare(action.payload);
          break;
        case 'find_branch':
          showLocator(action.payload.pincode, action.payload.results);
          break;
        case 'show_checklist':
          showChecklist(action.payload.title, action.payload.items);
          break;
        case 'send_to_phone': {
          const { what, channel, number } = action.payload;
          sendToPhone(what, channel, number);
          break;
        }
        case 'raise_ticket': {
          const { reference, topic, summary } = action.payload;
          raiseTicket(reference, topic, summary);
          break;
        }
        case 'spotlight':
          spotlight(action.payload.target, action.payload.label);
          break;
        case 'open_auth':
          openAuth(action.payload);
          break;
        case 'choose_account':
          openAccountPicker(action.payload);
          break;
        case 'show_balance':
          showBalance(action.payload);
          break;
        case 'show_statement':
          showStatement(action.payload);
          break;
        case 'choose_credit_card':
          openCardPicker(action.payload);
          break;
        case 'show_card_controls':
          showCardControls({ ...action.payload, saved: false });
          break;
        case 'show_forex_card':
          showForexCard();
          break;
        default:
          return unhandledUiAction(action);
      }
    },
    [
      openHome,
      openHelpCenter,
      openCategory,
      openArticle,
      playVideo,
      highlightStep,
      seekVideo,
      pauseVideo,
      resumeVideo,
      showContact,
      runCalculator,
      startApplication,
      prefillField,
      submitApplication,
      showCompare,
      showLocator,
      sendToPhone,
      raiseTicket,
      showChecklist,
      spotlight,
      openAuth,
      openAccountPicker,
      showBalance,
      showStatement,
      openCardPicker,
      showCardControls,
      showForexCard,
    ],
  );

  const store: AuraStore = {
    screen,
    category,
    articleId,
    videoId,
    videoCmd,
    playing,
    explicitStep,
    currentStep,
    contactOpen,
    contactTopic,
    calc,
    apply,
    compare,
    locator,
    checklist,
    sentToPhone,
    ticket,
    spotlightState,
    authSession,
    authPrompt,
    accountPicker,
    selectedAccount,
    balance,
    statement,
    cardPicker,
    selectedCard,
    cardControls,
    forex,
    agentSend: agentSendRef.current,
    byHand,
    registerAgentSend,
    handleUiCommand,
    openHome,
    openHelpCenter,
    openCategory,
    openArticle,
    playVideo,
    highlightStep,
    seekVideo,
    pauseVideo,
    resumeVideo,
    showContact,
    closeContact,
    setPlaybackTime,
    runCalculator,
    recomputeCalc,
    startApplication,
    prefillField,
    submitApplication,
    showCompare,
    showLocator,
    showChecklist,
    sendToPhone,
    closeSentToPhone,
    raiseTicket,
    closeTicket,
    spotlight,
    openAuth,
    confirmAuth,
    cancelAuth,
    openAccountPicker,
    selectAccount,
    cancelAccount,
    showBalance,
    showStatement,
    openCardPicker,
    selectCard,
    cancelCard,
    showCardControls,
    saveCardControls,
    showForexCard,
    submitForexLead,
  };

  return <Ctx.Provider value={store}>{children}</Ctx.Provider>;
}

export function useAura(): AuraStore {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useAura must be used within AuraProvider');
  return ctx;
}
