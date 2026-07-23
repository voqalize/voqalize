/**
 * AuraStore — the single source of truth for the Aura Bank L1-support demo.
 *
 * Both the human (clicking the help centre) and the voice assistant (via
 * `ui_command` RTVI messages) call the SAME actions, so the screen stays
 * consistent whoever is driving. Navigation is plain React state — never the
 * router — so the `PipecatClient` mounted alongside never unmounts and the call
 * stays live across screens.
 *
 * Every change bumps `rev`; the voice widget watches `rev` and echoes a compact
 * `screen_state` snapshot back to the agent (`state_sync`) so the assistant
 * always knows which screen / article / video the customer is looking at.
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
  Spotlight,
  StatementView,
  Ticket,
  VideoCommand,
} from './types';

export type AgentSend = (type: string, data: unknown) => void;

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
  spotlight: (target: string, label?: string) => void;
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
  spotlightState: Spotlight | null;
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
  rev: number;
  agentSend: AgentSend | null;
  registerAgentSend: (fn: AgentSend | null) => void;
  snapshot: () => Record<string, unknown>;
  handleUiCommand: (cmd: Record<string, unknown>) => void;
}

const Ctx = createContext<AuraStore | null>(null);

const str = (v: unknown): string | undefined => (typeof v === 'string' && v ? v : undefined);
const num = (v: unknown): number | undefined => {
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : undefined;
};
const arr = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
const obj = (v: unknown): Record<string, unknown> => (v && typeof v === 'object' ? (v as Record<string, unknown>) : {});
// Coerce an untrusted {k: v} map to numbers (calculator inputs).
const numMap = (v: unknown): Record<string, number> => {
  const out: Record<string, number> = {};
  for (const [k, val] of Object.entries(obj(v))) {
    const n = num(val);
    if (n !== undefined) out[k] = n;
  }
  return out;
};

// Coerce an untrusted object to an Account (never trusts a real account number).
const account = (v: unknown): Account => {
  const o = obj(v);
  return {
    account_id: str(o.account_id) ?? '',
    type: str(o.type) ?? 'Account',
    branch: str(o.branch) ?? '',
    nickname: str(o.nickname),
    masked_number: str(o.masked_number) ?? '',
  };
};

const bool = (v: unknown, d: boolean): boolean => (typeof v === 'boolean' ? v : d);

// Coerce an untrusted object to a Card (never trusts a real card number).
const card = (v: unknown): Card => {
  const o = obj(v);
  return {
    card_id: str(o.card_id) ?? '',
    network: str(o.network) ?? '',
    product: str(o.product) ?? 'Credit Card',
    variant: str(o.variant),
    masked_number: str(o.masked_number) ?? '',
  };
};

const toControls = (v: unknown): CardControls => {
  const o = obj(v);
  return {
    domestic_enabled: bool(o.domestic_enabled, true),
    international_enabled: bool(o.international_enabled, false),
    contactless_enabled: bool(o.contactless_enabled, true),
    online_enabled: bool(o.online_enabled, true),
    domestic_limit: num(o.domestic_limit) ?? 0,
    international_limit: num(o.international_limit) ?? 0,
    atm_cash_limit: num(o.atm_cash_limit) ?? 0,
  };
};

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
  const [spotlightState, setSpotlightState] = useState<Spotlight | null>(null);
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
  const [rev, setRev] = useState(0);
  const agentSendRef = useRef<AgentSend | null>(null);
  const [, forceTick] = useState(0);
  const nonceRef = useRef(0);
  const nextNonce = () => (nonceRef.current += 1);

  const bump = useCallback(() => setRev((r) => r + 1), []);

  const registerAgentSend = useCallback((fn: AgentSend | null) => {
    agentSendRef.current = fn;
    forceTick((t) => t + 1);
  }, []);

  const openHome = useCallback(() => {
    setScreen('home');
    setContactOpen(false);
    bump();
  }, [bump]);

  const openHelpCenter = useCallback(() => {
    setScreen('help');
    setContactOpen(false);
    bump();
  }, [bump]);

  const openCategory = useCallback(
    (cat: string) => {
      setCategory(cat as CategoryId);
      setScreen('category');
      setContactOpen(false);
      bump();
    },
    [bump],
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
      bump();
    },
    [bump],
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
      bump();
    },
    [bump],
  );

  const seekVideo = useCallback(
    (startSec: number) => {
      const video = getVideo(videoId ?? undefined);
      if (video) setExplicitStep(chapterAt(video, startSec));
      setPlaybackTimeState(startSec);
      setPlaying(true);
      setVideoCmd({ action: 'seek', startSec, nonce: nextNonce() });
      bump();
    },
    [bump, videoId],
  );

  const highlightStep = useCallback(
    (index: number) => {
      setExplicitStep(index);
      bump();
    },
    [bump],
  );

  const pauseVideo = useCallback(() => {
    setPlaying(false);
    setVideoCmd({ action: 'pause', nonce: nextNonce() });
    bump();
  }, [bump]);

  const resumeVideo = useCallback(() => {
    setPlaying(true);
    setVideoCmd({ action: 'resume', nonce: nextNonce() });
    bump();
  }, [bump]);

  const showContact = useCallback(
    (topic: string) => {
      setContactTopic(topic);
      setContactOpen(true);
      bump();
    },
    [bump],
  );

  const closeContact = useCallback(() => {
    setContactOpen(false);
    bump();
  }, [bump]);

  // ── interactive tools ───────────────────────────────────────────────────────
  const runCalculator = useCallback(
    (kind: CalcKind, inputs: Record<string, number>, result?: Record<string, number>) => {
      const merged = { ...CALC_DEFAULTS[kind], ...inputs };
      setCalc({ kind, inputs: merged, result: result ?? computeCalc(kind, merged) });
      setScreen('calculator');
      bump();
    },
    [bump],
  );

  // Human edits an input → recompute live (UI source of truth after a manual edit).
  const recomputeCalc = useCallback(
    (inputs: Record<string, number>) => {
      setCalc((c) => (c ? { ...c, inputs, result: computeCalc(c.kind, inputs) } : c));
      bump();
    },
    [bump],
  );

  const startApplication = useCallback(
    (product: Product) => {
      setApply({ product, fields: APPLY_TEMPLATES[product].map((f) => ({ ...f })), submitted: false });
      setScreen('apply');
      bump();
    },
    [bump],
  );

  const prefillField = useCallback(
    (id: string, value: string) => {
      setApply((a) =>
        a ? { ...a, fields: a.fields.map((f) => (f.id === id ? { ...f, value } : f)) } : a,
      );
      bump();
    },
    [bump],
  );

  const submitApplication = useCallback(() => {
    setApply((a) => (a ? { ...a, submitted: true } : a));
    bump();
  }, [bump]);

  const showCompare = useCallback(
    (state: CompareState) => {
      setCompare(state);
      setScreen('compare');
      bump();
    },
    [bump],
  );

  const showLocator = useCallback(
    (pincode: string, results: LocatorState['results']) => {
      setLocator({ pincode, results });
      setScreen('locator');
      bump();
    },
    [bump],
  );

  const showChecklist = useCallback(
    (title: string, items: string[]) => {
      setChecklist({ title, items });
      setScreen('checklist');
      bump();
    },
    [bump],
  );

  const sendToPhone = useCallback(
    (what: string, channel: 'whatsapp' | 'sms', number: string) => {
      setSentToPhone({ what, channel, number, nonce: nextNonce() });
      bump();
    },
    [bump],
  );
  const closeSentToPhone = useCallback(() => setSentToPhone(null), []);

  const raiseTicket = useCallback(
    (reference: string, topic: string, summary: string) => {
      setTicket({ reference, topic, summary });
      bump();
    },
    [bump],
  );
  const closeTicket = useCallback(() => setTicket(null), []);

  const spotlight = useCallback(
    (target: string, label?: string) => {
      setSpotlightState({ target, label, nonce: nextNonce() });
      bump();
    },
    [bump],
  );

  // ── authenticated account access ────────────────────────────────────────────
  const openAuth = useCallback(
    (prompt: AuthPrompt) => {
      setAuthPrompt(prompt);
      bump();
    },
    [bump],
  );

  // Customer authorises the on-screen sign-in: tell the server (it mints the token
  // only on receiving this) and reflect the signed-in identity locally.
  const confirmAuth = useCallback(() => {
    if (!authPrompt) return;
    agentSendRef.current?.('auth_complete', { nonce: authPrompt.nonce });
    setAuthSession({ name: authPrompt.name });
    setAuthPrompt(null);
    bump();
  }, [authPrompt, bump]);

  // Customer declines the sign-in: tell the server so the waiting authenticate()
  // tool returns immediately (the mic is muted during the call, so this button is
  // the customer's only way out).
  const cancelAuth = useCallback(() => {
    if (authPrompt) agentSendRef.current?.('auth_cancelled', { nonce: authPrompt.nonce });
    setAuthPrompt(null);
    bump();
  }, [authPrompt, bump]);

  const openAccountPicker = useCallback(
    (picker: AccountPicker) => {
      setAccountPicker(picker);
      bump();
    },
    [bump],
  );

  // Customer picks an account: tell the server (account_selected) and record it so
  // the balance/statement screens can header it.
  const selectAccount = useCallback(
    (account: Account) => {
      if (accountPicker) {
        agentSendRef.current?.('account_selected', { nonce: accountPicker.nonce, account_id: account.account_id });
      }
      setAccountPicker(null);
      setSelectedAccount(account);
      bump();
    },
    [accountPicker, bump],
  );

  const cancelAccount = useCallback(() => {
    if (accountPicker) agentSendRef.current?.('account_cancelled', { nonce: accountPicker.nonce });
    setAccountPicker(null);
    bump();
  }, [accountPicker, bump]);

  const showBalance = useCallback(
    (view: BalanceView) => {
      setBalance(view);
      setSelectedAccount(view.account);
      setScreen('balance');
      bump();
    },
    [bump],
  );

  const showStatement = useCallback(
    (view: StatementView) => {
      setStatement(view);
      setSelectedAccount(view.account);
      setScreen('statement');
      bump();
    },
    [bump],
  );

  // ── credit-card controls + forex cross-sell ─────────────────────────────────
  const openCardPicker = useCallback(
    (picker: CardPicker) => {
      setCardPicker(picker);
      bump();
    },
    [bump],
  );

  // Customer picks a card: tell the server (card_selected) and record it so the
  // controls screen can header it.
  const selectCard = useCallback(
    (c: Card) => {
      if (cardPicker) {
        agentSendRef.current?.('card_selected', { nonce: cardPicker.nonce, card_id: c.card_id });
      }
      setCardPicker(null);
      setSelectedCard(c);
      bump();
    },
    [cardPicker, bump],
  );

  const cancelCard = useCallback(() => {
    if (cardPicker) agentSendRef.current?.('card_cancelled', { nonce: cardPicker.nonce });
    setCardPicker(null);
    bump();
  }, [cardPicker, bump]);

  const showCardControls = useCallback(
    (view: CardControlsView) => {
      setCardControls(view);
      setSelectedCard(view.card);
      setScreen('card_controls');
      bump();
    },
    [bump],
  );

  const saveCardControls = useCallback(
    (controls: CardControls) => {
      setCardControls((c) => (c ? { ...c, controls, saved: true } : c));
      bump();
    },
    [bump],
  );

  const showForexCard = useCallback(() => {
    setForex({ submitted: false });
    setScreen('forex');
    bump();
  }, [bump]);

  const submitForexLead = useCallback(() => {
    setForex((f) =>
      f
        ? { ...f, submitted: true, reference: `FX${Math.floor(1_000_000 + Math.random() * 8_999_999)}` }
        : f,
    );
    bump();
  }, [bump]);

  // Playback time drives chapter auto-highlight; throttle re-renders to whole
  // seconds so the muted video keeps the step list in sync without churn.
  const setPlaybackTime = useCallback((t: number) => {
    setPlaybackTimeState((prev) => (Math.floor(prev) === Math.floor(t) ? prev : t));
  }, []);

  const video = getVideo(videoId ?? undefined);
  const currentStep = useMemo(() => {
    if (playing && video) return chapterAt(video, playbackTime);
    return explicitStep;
  }, [playing, video, playbackTime, explicitStep]);

  const snapshot = useCallback((): Record<string, unknown> => {
    const article = articleId ? getArticle(articleId) : undefined;
    const v = getVideo(videoId ?? undefined);
    return {
      screen,
      category,
      article: article ? { id: article.id, title_en: article.title_en, needs_login: article.needs_login } : null,
      video: v
        ? {
            id: v.youtube_id,
            playing,
            step_index: currentStep,
            step: v.chapters[currentStep]?.label,
            total_steps: v.chapters.length,
          }
        : null,
      contact_open: contactOpen,
      // Active interactive tool (so the agent can speak the figure / read the form back).
      calculator: calc ? { kind: calc.kind, inputs: calc.inputs, result: calc.result } : null,
      application: apply
        ? {
            product: apply.product,
            submitted: apply.submitted,
            fields: Object.fromEntries(apply.fields.map((f) => [f.id, f.value])),
            missing: apply.fields.filter((f) => !f.value).map((f) => f.id),
          }
        : null,
      compare: compare
        ? { kind: compare.kind, options: compare.items.map((it) => it.name), recommended: compare.recommendId }
        : null,
      locator: locator ? { pincode: locator.pincode, count: locator.results.length } : null,
      checklist: checklist ? { title: checklist.title, items: checklist.items.length } : null,
      last_ticket: ticket ? ticket.reference : null,
      sent_to_phone: sentToPhone ? { what: sentToPhone.what, channel: sentToPhone.channel } : null,
      // Authenticated-account state, so the agent knows where it is in the flow.
      authenticated: !!authSession,
      customer_name: authSession?.name ?? null,
      selected_account: selectedAccount
        ? { account_id: selectedAccount.account_id, nickname: selectedAccount.nickname, masked_number: selectedAccount.masked_number }
        : null,
      selected_card: selectedCard
        ? { card_id: selectedCard.card_id, product: selectedCard.product, masked_number: selectedCard.masked_number }
        : null,
      card_controls: cardControls
        ? {
            product: cardControls.card.product,
            international_enabled: cardControls.controls.international_enabled,
            domestic_enabled: cardControls.controls.domestic_enabled,
            contactless_enabled: cardControls.controls.contactless_enabled,
            saved: cardControls.saved,
          }
        : null,
      forex_lead: forex ? { submitted: forex.submitted, reference: forex.reference ?? null } : null,
    };
  }, [
    screen,
    category,
    articleId,
    videoId,
    playing,
    currentStep,
    contactOpen,
    calc,
    apply,
    compare,
    locator,
    checklist,
    ticket,
    sentToPhone,
    authSession,
    selectedAccount,
    selectedCard,
    cardControls,
    forex,
  ]);

  const handleUiCommand = useCallback(
    (cmd: Record<string, unknown>) => {
      switch (String(cmd.action ?? '')) {
        case 'open_home':
          openHome();
          break;
        case 'open_help_center':
          openHelpCenter();
          break;
        case 'open_category':
          if (str(cmd.category)) openCategory(str(cmd.category)!);
          break;
        case 'open_article':
          if (str(cmd.article_id)) openArticle(str(cmd.article_id)!);
          break;
        case 'play_help_video':
          if (str(cmd.video_id)) playVideo(str(cmd.video_id)!, num(cmd.start_sec) ?? 0);
          break;
        case 'highlight_step':
          highlightStep(num(cmd.index) ?? 0);
          break;
        case 'seek_video':
          seekVideo(num(cmd.start_sec) ?? 0);
          break;
        case 'pause_video':
          pauseVideo();
          break;
        case 'resume_video':
          resumeVideo();
          break;
        case 'show_contact':
          showContact(str(cmd.topic) ?? '');
          break;
        case 'run_calculator': {
          const kind = str(cmd.kind) as CalcKind | undefined;
          if (kind === 'emi' || kind === 'fd' || kind === 'eligibility')
            runCalculator(kind, numMap(cmd.inputs), Object.keys(obj(cmd.result)).length ? numMap(cmd.result) : undefined);
          break;
        }
        case 'start_application': {
          const product = str(cmd.product) as Product | undefined;
          if (product === 'savings' || product === 'credit_card' || product === 'loan') startApplication(product);
          break;
        }
        case 'prefill_field': {
          // Single {field,value} or bulk {fields:[{field,value}]}.
          const bulk = arr<Record<string, unknown>>(cmd.fields);
          if (bulk.length) bulk.forEach((f) => str(f.field) && prefillField(str(f.field)!, String(f.value ?? '')));
          else if (str(cmd.field)) prefillField(str(cmd.field)!, String(cmd.value ?? ''));
          break;
        }
        case 'submit_application':
          submitApplication();
          break;
        case 'compare': {
          const kind = str(cmd.kind) === 'savings' ? 'savings' : 'credit_card';
          showCompare({
            kind,
            items: arr<Record<string, unknown>>(cmd.items).map((it, i) => ({
              id: str(it.id) ?? `c${i + 1}`,
              name: str(it.name) ?? `Option ${i + 1}`,
              features: arr<unknown>(it.features).map(String),
            })),
            recommendId: str(cmd.recommend_id),
            recommendReason: str(cmd.recommend_reason),
          });
          break;
        }
        case 'find_branch':
          showLocator(
            str(cmd.pincode) ?? '',
            arr<Record<string, unknown>>(cmd.results).map((r) => ({
              name: str(r.name) ?? 'Aura Bank',
              address: str(r.address) ?? '',
              kind: str(r.kind) === 'atm' ? 'atm' : 'branch',
              ifsc: str(r.ifsc),
              hours: str(r.hours),
            })),
          );
          break;
        case 'send_to_phone':
          sendToPhone(str(cmd.what) ?? 'this guide', str(cmd.channel) === 'sms' ? 'sms' : 'whatsapp', str(cmd.number) ?? '');
          break;
        case 'raise_ticket':
          raiseTicket(str(cmd.reference) ?? '', str(cmd.topic) ?? '', str(cmd.summary) ?? '');
          break;
        case 'show_checklist':
          showChecklist(str(cmd.title) ?? 'Checklist', arr<unknown>(cmd.items).map(String));
          break;
        case 'spotlight':
          if (str(cmd.target)) spotlight(str(cmd.target)!, str(cmd.label));
          break;
        case 'open_auth':
          openAuth({
            name: str(cmd.name) ?? 'your Aura account',
            masked_mobile: str(cmd.masked_mobile) ?? '',
            nonce: str(cmd.nonce) ?? '',
          });
          break;
        case 'choose_account':
          openAccountPicker({
            accounts: arr<unknown>(cmd.accounts).map(account),
            nonce: str(cmd.nonce) ?? '',
          });
          break;
        case 'show_balance':
          showBalance({
            account: account(cmd.account),
            balance: num(cmd.balance) ?? 0,
            currency: str(cmd.currency) ?? 'INR',
            as_of: str(cmd.as_of) ?? '',
          });
          break;
        case 'show_statement':
          showStatement({
            account: account(cmd.account),
            from: str(cmd.from_date) ?? '',
            to: str(cmd.to_date) ?? '',
            currency: str(cmd.currency) ?? 'INR',
            transactions: arr<Record<string, unknown>>(cmd.transactions).map((t) => ({
              date: str(t.date) ?? '',
              description: str(t.description) ?? '',
              amount: num(t.amount) ?? 0,
              kind: str(t.kind) === 'credit' ? 'credit' : 'debit',
            })),
          });
          break;
        case 'choose_credit_card':
          openCardPicker({
            cards: arr<unknown>(cmd.cards).map(card),
            nonce: str(cmd.nonce) ?? '',
          });
          break;
        case 'show_card_controls':
          showCardControls({
            card: card(cmd.card),
            credit_limit: num(cmd.credit_limit) ?? 0,
            controls: toControls(cmd.controls),
            saved: false,
          });
          break;
        case 'show_forex_card':
          showForexCard();
          break;
        default:
          break;
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
    rev,
    agentSend: agentSendRef.current,
    registerAgentSend,
    snapshot,
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
