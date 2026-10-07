/**
 * SiteStore — the single source of truth for the Petwell website.
 *
 * Both the visitor (clicking) and Tushar (via `ui-command` RTVI events) call the
 * SAME actions, so the page stays consistent no matter who is driving. The site
 * is one page app with plain state for its pages — never a router — so the
 * `PipecatClient` mounted alongside never unmounts and the call stays live.
 *
 * Three layers of state: the **page** being read (home, services, locations,
 * health hub or an article, at home), the **booking panel** over it with its six
 * steps, and the **language** — set only by Tushar's `language_changed`, never
 * picked: he hears which language the visitor speaks and the page follows.
 *
 * A click is also *told* to the brain: the `pick*`/`open*` actions emit a typed
 * `AppEvent` (declared in `backend/app_events.py`, generated into
 * `actions.gen.ts`). The agent's own commands call the same setters without
 * emitting — the brain already knows what it did.
 */

import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react';
import { getBranch, getService, OPENING_SOON, type VisitType } from './catalog';
import type { Lang } from './i18n';
import {
  asUiAction,
  sendAppEvent,
  unhandledUiAction,
  type AppEvent,
  type FillDetails,
  type LanguageChanged,
  type Navigate,
} from './actions.gen';

export type VoiceLanguage = LanguageChanged['language'];

export type Page = Navigate['page'] | 'article';
export type Step = 'visit' | 'location' | 'service' | 'slot' | 'details' | 'review' | 'done';

/** The form's fields — the agent's `fill_details` keys, each a plain string the owner can edit. */
export type Details = { [K in keyof FillDetails]: string };

const EMPTY_DETAILS: Details = {
  owner_name: '',
  pet_name: '',
  pet_type: '',
  phone: '',
  email: '',
  address: '',
  notes: '',
};

export interface Emergency {
  city: string;
  helpline: string;
  branchIds: string[];
}

interface State {
  lang: Lang;
  /** The language Tushar is speaking — the page follows it into Hindi only. */
  voiceLanguage: VoiceLanguage;
  page: Page;
  articleId: string | null;
  /** The city the locations page (or home's finder) is showing. */
  browseCity: string | null;
  bookingOpen: boolean;
  step: Step;
  visitType: VisitType;
  city: string | null;
  branchId: string | null;
  serviceId: string | null;
  date: string | null;
  /** Free times the brain sent for `date`; null = compute locally. */
  times: string[] | null;
  time: string | null;
  details: Details;
  justFilled: string[];
  emergency: Emergency | null;
  ref: string | null;
}

const BOOKING_RESET = {
  step: 'visit' as Step,
  visitType: 'clinic' as VisitType,
  city: null,
  branchId: null,
  serviceId: null,
  date: null,
  times: null,
  time: null,
  details: EMPTY_DETAILS,
  justFilled: [],
  ref: null,
};

const INITIAL: State = {
  lang: 'en',
  voiceLanguage: 'English',
  page: 'home',
  articleId: null,
  browseCity: null,
  bookingOpen: false,
  emergency: null,
  ...BOOKING_RESET,
};

export type AgentSend = (event: string, payload?: unknown) => void;

export interface SiteStore extends State {
  // Browsing — set the page and tell the brain.
  openPage: (page: Navigate['page']) => void;
  openArticle: (id: string) => void;
  browse: (city: string | null) => void;
  // Booking taps.
  openBooking: (serviceId?: string) => void;
  closeBooking: () => void;
  pickVisitType: (v: VisitType) => void;
  pickCity: (city: string) => void;
  pickBranch: (id: string) => void;
  pickService: (id: string) => void;
  pickDate: (date: string) => void;
  pickSlot: (date: string, time: string) => void;
  editDetail: (field: keyof Details, value: string) => void;
  goTo: (step: Step) => void;
  reviewNow: () => void;
  sendRequest: () => string | null;
  restartBooking: () => void;
  openEmergency: () => void;
  closeEmergency: () => void;
  // Wiring.
  registerAgentSend: (fn: AgentSend | null) => void;
  handleUiCommand: (command: string, payload: unknown) => void;
}

const Ctx = createContext<SiteStore | null>(null);

function makeRef(): string {
  return `PW-${Math.floor(100000 + Math.random() * 900000)}`;
}

export function SiteProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>(INITIAL);
  const sendRef = useRef<AgentSend | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  const emit = useCallback((event: AppEvent) => sendAppEvent(sendRef.current, event), []);
  const registerAgentSend = useCallback((fn: AgentSend | null) => {
    sendRef.current = fn;
  }, []);

  const scrollTop = () => document.querySelector('.pw-app')?.scrollTo({ top: 0, behavior: 'smooth' });

  // ── Setters shared by clicks and the agent ────────────────────────────────

  const setPage = useCallback((page: Navigate['page']) => {
    setState((s) => ({ ...s, page, articleId: null, bookingOpen: false }));
    scrollTop();
  }, []);

  const setArticle = useCallback((articleId: string) => {
    setState((s) => ({ ...s, page: 'article', articleId, bookingOpen: false }));
    scrollTop();
  }, []);

  const setBrowse = useCallback((city: string | null) => {
    setState((s) => ({ ...s, page: 'locations', browseCity: city, bookingOpen: false }));
  }, []);

  const setVisitType = useCallback((visitType: VisitType) => {
    setState((s) => ({
      ...s,
      bookingOpen: true,
      emergency: null,
      visitType,
      serviceId: getService(s.serviceId)?.visit === visitType ? s.serviceId : null,
      step: 'location',
    }));
  }, []);

  const setCity = useCallback((city: string) => {
    setState((s) => ({
      ...s,
      bookingOpen: true,
      city,
      branchId: getBranch(s.branchId)?.city === city ? s.branchId : null,
      step: 'location',
    }));
  }, []);

  const setBranch = useCallback((branchId: string) => {
    const b = getBranch(branchId);
    if (!b || OPENING_SOON.has(b.city)) return;
    // A service chosen before the branch (from an article) skips its own step.
    setState((s) => ({ ...s, bookingOpen: true, city: b.city, branchId, step: s.serviceId ? 'slot' : 'service' }));
  }, []);

  const setService = useCallback((serviceId: string) => {
    if (!getService(serviceId)) return;
    // Without a branch there are no times to show: keep the reason and stay on the
    // location step, which the branch then moves past (see setBranch).
    setState((s) => ({ ...s, bookingOpen: true, serviceId, step: s.branchId ? 'slot' : 'location' }));
  }, []);

  const setSlot = useCallback((date: string, time: string) => {
    setState((s) => ({ ...s, bookingOpen: true, date, time, step: 'details' }));
  }, []);

  const setLanguage = useCallback(
    (voiceLanguage: VoiceLanguage, lang: Lang) => setState((s) => ({ ...s, voiceLanguage, lang })),
    [],
  );

  // ── Clicks ────────────────────────────────────────────────────────────────

  const openPage = useCallback(
    (page: Navigate['page']) => {
      setPage(page);
      emit({ event: 'page_picked', payload: { page } });
    },
    [setPage, emit],
  );
  const openArticle = useCallback(
    (id: string) => {
      setArticle(id);
      emit({ event: 'article_opened', payload: { article_id: id } });
    },
    [setArticle, emit],
  );
  const browse = useCallback((city: string | null) => setBrowse(city), [setBrowse]);

  const openBooking = useCallback(
    (serviceId?: string) => {
      const service = getService(serviceId);
      setState((s) => ({
        ...s,
        ...BOOKING_RESET,
        bookingOpen: true,
        emergency: null,
        ...(service ? { serviceId: service.id, visitType: service.visit, step: 'location' as Step } : {}),
      }));
      emit({ event: 'booking_opened', payload: { service_id: service?.id ?? '' } });
    },
    [emit],
  );
  const closeBooking = useCallback(() => setState((s) => ({ ...s, bookingOpen: false })), []);

  const pickVisitType = useCallback(
    (v: VisitType) => {
      setVisitType(v);
      emit({ event: 'visit_type_picked', payload: { visit_type: v } });
    },
    [setVisitType, emit],
  );
  const pickCity = useCallback(
    (city: string) => {
      setCity(city);
      emit({ event: 'city_picked', payload: { city } });
    },
    [setCity, emit],
  );
  const pickBranch = useCallback(
    (id: string) => {
      setBranch(id);
      emit({ event: 'branch_picked', payload: { branch_id: id } });
    },
    [setBranch, emit],
  );
  const pickService = useCallback(
    (id: string) => {
      setService(id);
      emit({ event: 'service_picked', payload: { service_id: id } });
    },
    [setService, emit],
  );
  const pickDate = useCallback((date: string) => {
    setState((s) => ({ ...s, date, times: null, time: null }));
  }, []);
  const pickSlot = useCallback(
    (date: string, time: string) => {
      setSlot(date, time);
      emit({ event: 'slot_picked', payload: { date, time } });
    },
    [setSlot, emit],
  );

  const editDetail = useCallback((field: keyof Details, value: string) => {
    setState((s) => ({ ...s, details: { ...s.details, [field]: value } }));
  }, []);

  const goTo = useCallback((step: Step) => setState((s) => ({ ...s, step })), []);
  const reviewNow = useCallback(() => setState((s) => ({ ...s, bookingOpen: true, step: 'review' })), []);

  const sendRequest = useCallback((): string | null => {
    const s = stateRef.current;
    if (s.ref || !s.branchId || !s.time) return null;
    const ref = makeRef();
    setState((prev) => ({ ...prev, ref, step: 'done' }));
    emit({
      event: 'appointment_requested',
      payload: { ref, owner_name: s.details.owner_name, pet_name: s.details.pet_name, phone: s.details.phone },
    });
    return ref;
  }, [emit]);

  const restartBooking = useCallback(() => setState((s) => ({ ...s, ...BOOKING_RESET })), []);
  const openEmergency = useCallback(() => {
    setState((s) => ({ ...s, emergency: { city: s.city ?? s.browseCity ?? '', helpline: '', branchIds: [] } }));
  }, []);
  const closeEmergency = useCallback(() => setState((s) => ({ ...s, emergency: null })), []);

  // ── Agent → page ──────────────────────────────────────────────────────────

  const handleUiCommand = useCallback(
    (command: string, payload: unknown) => {
      const action = asUiAction(command, payload);
      if (!action) return;
      switch (action.command) {
        case 'navigate':
          setPage(action.payload.page);
          break;
        case 'show_branches':
          setBrowse(action.payload.city);
          scrollTop();
          break;
        case 'open_article':
          setArticle(action.payload.article_id);
          break;
        case 'language_changed':
          setLanguage(action.payload.language, action.payload.screen_language);
          break;
        case 'start_booking':
          setVisitType(action.payload.visit_type);
          break;
        case 'choose_city':
          setCity(action.payload.city);
          break;
        case 'choose_branch':
          setBranch(action.payload.branch_id);
          break;
        case 'choose_service':
          setService(action.payload.service_id);
          break;
        case 'show_slots': {
          const { date, times, branch_id, visit_type } = action.payload;
          setState((s) => ({
            ...s,
            bookingOpen: true,
            branchId: branch_id,
            visitType: visit_type,
            date,
            times,
            time: null,
            step: 'slot',
          }));
          break;
        }
        case 'choose_slot':
          setSlot(action.payload.date, action.payload.time);
          break;
        case 'fill_details': {
          const filled = Object.entries(action.payload).filter(([, v]) => v) as [keyof Details, string][];
          setState((s) => ({
            ...s,
            bookingOpen: true,
            step: s.step === 'review' ? 'review' : 'details',
            details: { ...s.details, ...Object.fromEntries(filled) },
            justFilled: filled.map(([k]) => k),
          }));
          break;
        }
        case 'show_review':
          reviewNow();
          break;
        case 'show_emergency': {
          const { city, helpline, branch_ids } = action.payload;
          setState((s) => ({ ...s, emergency: { city, helpline, branchIds: branch_ids } }));
          break;
        }
        case 'go_home':
          setState((s) => ({ ...s, ...BOOKING_RESET, bookingOpen: false, page: 'home', articleId: null }));
          scrollTop();
          break;
        default:
          unhandledUiAction(action);
      }
    },
    [setPage, setBrowse, setArticle, setLanguage, setVisitType, setCity, setBranch, setService, setSlot, reviewNow],
  );

  const store: SiteStore = {
    ...state,
    openPage,
    openArticle,
    browse,
    openBooking,
    closeBooking,
    pickVisitType,
    pickCity,
    pickBranch,
    pickService,
    pickDate,
    pickSlot,
    editDetail,
    goTo,
    reviewNow,
    sendRequest,
    restartBooking,
    openEmergency,
    closeEmergency,
    registerAgentSend,
    handleUiCommand,
  };

  return <Ctx.Provider value={store}>{children}</Ctx.Provider>;
}

export function useSite(): SiteStore {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useSite must be used within SiteProvider');
  return ctx;
}
