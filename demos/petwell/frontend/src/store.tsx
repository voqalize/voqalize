/**
 * BookingStore — the single source of truth for the Petwell booking screen.
 *
 * Both the pet owner (tapping) and the Appointment Desk agent (via `ui-command`
 * RTVI events) call the SAME actions, so the screen stays consistent no matter
 * who is driving. Navigation is plain React state — never a router — so the
 * `PipecatClient` mounted alongside never unmounts and the call stays live.
 *
 * A tap is also *told* to the brain: the `pick*` actions emit a typed
 * `AppEvent` (declared in `backend/app_events.py`, generated into
 * `actions.gen.ts`), so the assistant carries on from where the screen now is.
 * The agent's own commands call the same setters without emitting — the brain
 * already knows what it did.
 */

import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react';
import { getBranch, getService, OPENING_SOON, type VisitType } from './catalog';
import {
  asUiAction,
  sendAppEvent,
  unhandledUiAction,
  type AppEvent,
  type FillDetails,
} from './actions.gen';

export type Step = 'home' | 'location' | 'service' | 'slot' | 'details' | 'review' | 'done';

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
  /** Field names the agent just filled — flashed on screen. */
  justFilled: string[];
  emergency: Emergency | null;
  ref: string | null;
}

const INITIAL: State = {
  step: 'home',
  visitType: 'clinic',
  city: null,
  branchId: null,
  serviceId: null,
  date: null,
  times: null,
  time: null,
  details: EMPTY_DETAILS,
  justFilled: [],
  emergency: null,
  ref: null,
};

export type AgentSend = (event: string, payload?: unknown) => void;

export interface BookingStore extends State {
  // Taps — set the screen and tell the brain.
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
  openEmergency: () => void;
  closeEmergency: () => void;
  restart: () => void;
  // Wiring.
  registerAgentSend: (fn: AgentSend | null) => void;
  handleUiCommand: (command: string, payload: unknown) => void;
}

const Ctx = createContext<BookingStore | null>(null);

function makeRef(): string {
  return `PW-${Math.floor(100000 + Math.random() * 900000)}`;
}

export function BookingProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>(INITIAL);
  const sendRef = useRef<AgentSend | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  const emit = useCallback((event: AppEvent) => sendAppEvent(sendRef.current, event), []);
  const registerAgentSend = useCallback((fn: AgentSend | null) => {
    sendRef.current = fn;
  }, []);

  // ── Setters shared by taps and the agent ──────────────────────────────────

  const setVisitType = useCallback((visitType: VisitType) => {
    setState((s) => ({
      ...s,
      visitType,
      serviceId: getService(s.serviceId)?.visit === visitType ? s.serviceId : null,
      step: 'location',
      emergency: null,
    }));
  }, []);

  const setCity = useCallback((city: string) => {
    setState((s) => ({
      ...s,
      city,
      branchId: getBranch(s.branchId)?.city === city ? s.branchId : null,
      step: 'location',
    }));
  }, []);

  const setBranch = useCallback((branchId: string) => {
    const b = getBranch(branchId);
    if (!b || OPENING_SOON.has(b.city)) return;
    setState((s) => ({ ...s, city: b.city, branchId, step: 'service' }));
  }, []);

  const setService = useCallback((serviceId: string) => {
    if (!getService(serviceId)) return;
    setState((s) => ({ ...s, serviceId, step: 'slot' }));
  }, []);

  const setSlot = useCallback((date: string, time: string) => {
    setState((s) => ({ ...s, date, time, step: 'details' }));
  }, []);

  // ── Taps ──────────────────────────────────────────────────────────────────

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
  const reviewNow = useCallback(() => setState((s) => ({ ...s, step: 'review' })), []);

  const sendRequest = useCallback((): string | null => {
    const s = stateRef.current;
    if (s.ref || !s.branchId || !s.time) return null;
    const ref = makeRef();
    setState((prev) => ({ ...prev, ref, step: 'done' }));
    emit({
      event: 'appointment_requested',
      payload: {
        ref,
        owner_name: s.details.owner_name,
        pet_name: s.details.pet_name,
        phone: s.details.phone,
      },
    });
    return ref;
  }, [emit]);

  const openEmergency = useCallback(() => {
    setState((s) => ({ ...s, emergency: { city: s.city ?? '', helpline: '', branchIds: [] } }));
  }, []);
  const closeEmergency = useCallback(() => setState((s) => ({ ...s, emergency: null })), []);
  const restart = useCallback(() => setState(INITIAL), []);

  // ── Agent → screen ────────────────────────────────────────────────────────

  const handleUiCommand = useCallback(
    (command: string, payload: unknown) => {
      const action = asUiAction(command, payload);
      if (!action) return;
      switch (action.command) {
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
          const filled = Object.entries(action.payload).filter(([, v]) => v) as [
            keyof Details,
            string,
          ][];
          setState((s) => ({
            ...s,
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
          setState((s) => ({
            ...s,
            city: city || s.city,
            emergency: { city, helpline, branchIds: branch_ids },
          }));
          break;
        }
        case 'go_home':
          restart();
          break;
        default:
          unhandledUiAction(action);
      }
    },
    [setVisitType, setCity, setBranch, setService, setSlot, reviewNow, restart],
  );

  const store: BookingStore = {
    ...state,
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
    openEmergency,
    closeEmergency,
    restart,
    registerAgentSend,
    handleUiCommand,
  };

  return <Ctx.Provider value={store}>{children}</Ctx.Provider>;
}

export function useBooking(): BookingStore {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useBooking must be used within BookingProvider');
  return ctx;
}
