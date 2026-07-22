/**
 * TravelStore — the single source of truth for the Travel Desk demo.
 *
 * Both the human (clicking the portal) and the Travel Desk agent (via `ui_command`
 * RTVI messages) call the SAME actions, so the screen stays consistent no matter
 * who is driving. Navigation is plain React state — never the router — so the
 * `PipecatClient` mounted alongside never unmounts and the call stays live.
 *
 * Itineraries persist to localStorage (build-from-scratch: trips created during a
 * call survive a reload, so "open Poddar's Vietnam trip" works later). Every data
 * mutation bumps `rev`; the voice widget watches `rev` and echoes a compact
 * snapshot back to the agent (`state_sync`) so the AI always knows the active
 * itinerary and its state — including edits the travel agent makes by hand.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  paxSummary,
  selectedFlight,
  selectedHotel,
  slugify,
  type Activity,
  type DayPlan,
  type Family,
  type FlightOption,
  type HotelOption,
  type HotelStay,
  type Itinerary,
  type Leg,
  type SpecialRequest,
  type Task,
  type TaskKind,
} from './types';
import { SEED_ITINERARIES } from './data';

export type View = 'dashboard' | 'overview' | 'flights' | 'hotels';

export interface Highlight {
  section: string;
  nonce: number;
}

const LS_ITINERARIES = 'voqal.travel.itineraries.v1';
const LS_ACTIVE = 'voqal.travel.active.v1';

function seedClone(): Itinerary[] {
  // Deep-clone the seeds so edits never mutate the module-level template.
  return SEED_ITINERARIES.map((it) => structuredClone(it));
}

function loadItineraries(): Itinerary[] {
  if (typeof window === 'undefined') return seedClone();
  try {
    const raw = window.localStorage.getItem(LS_ITINERARIES);
    const parsed = raw ? (JSON.parse(raw) as unknown) : null;
    // Seed the saved draft itineraries on first load (none saved yet). Once the
    // agent or the travel agent edits one, the list persists like any trip.
    if (Array.isArray(parsed) && parsed.length) return parsed as Itinerary[];
    return seedClone();
  } catch {
    return seedClone();
  }
}

function loadActiveId(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage.getItem(LS_ACTIVE);
  } catch {
    return null;
  }
}

function persist(itineraries: Itinerary[], activeId: string | null): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(LS_ITINERARIES, JSON.stringify(itineraries));
    if (activeId) window.localStorage.setItem(LS_ACTIVE, activeId);
    else window.localStorage.removeItem(LS_ACTIVE);
  } catch {
    /* ignore quota / private-mode errors */
  }
}

function now(): number {
  return Date.now();
}

export type AgentSend = (type: string, data: unknown) => void;

export interface TravelActions {
  openDashboard: () => void;
  newBlankItinerary: () => void;
  openItinerary: (idOrName: string) => void;
  createItinerary: (raw: Record<string, unknown>) => void;
  setTripStructure: (raw: Record<string, unknown>) => void;
  setSpecialRequests: (requests: SpecialRequest[]) => void;
  presentFlights: (legId: string, options: FlightOption[]) => void;
  selectFlight: (legId: string, optionId: string) => void;
  presentHotels: (city: string, options: HotelOption[]) => void;
  selectHotel: (city: string, optionId: string) => void;
  /** Kick off a background flight search; reveals options when it finishes. */
  searchFlights: (legId: string, options: FlightOption[]) => void;
  /** Kick off a background hotel search; reveals options when it finishes. */
  searchHotels: (city: string, options: HotelOption[]) => void;
  /** Kick off a background day-plan build; reveals the days when it finishes. */
  generateDayPlan: (days: DayPlan[]) => void;
  setDayPlan: (plan: DayPlan) => void;
  setInclusions: (inclusions: string[], exclusions: string[]) => void;
  setTerms: (terms: string[]) => void;
  patchDates: (updates: { leg_id: string; new_date: string }[], summary: string) => void;
  highlight: (section: string) => void;
  sendWhatsApp: (to: string, recipient: string) => void;
  /** Open the WhatsApp preview without marking it sent (manual share button). */
  openWhatsAppPreview: () => void;
  closeWhatsApp: () => void;
  /** Open the flights screen for a leg without changing data (manual nav). */
  viewFlights: (legId: string) => void;
  viewHotels: (city: string) => void;
}

export interface TravelStore extends TravelActions {
  itineraries: Itinerary[];
  active: Itinerary | null;
  view: View;
  flightsLeg: string | null;
  hotelsCity: string | null;
  highlighted: Highlight | null;
  whatsappOpen: boolean;
  /** Background searches/builds the Travel Desk has kicked off (running + recently done). */
  tasks: Task[];
  /** Open the screen a finished task produced (click-through from the task tray). */
  openTaskTarget: (task: Task) => void;
  /** Bumps on every data mutation; the voice widget syncs state to the agent on change. */
  rev: number;
  agentSend: AgentSend | null;
  registerAgentSend: (fn: AgentSend | null) => void;
  /** Compact snapshot of the active itinerary for `state_sync` (null on dashboard). */
  snapshot: () => Record<string, unknown> | null;
  handleUiCommand: (cmd: Record<string, unknown>) => void;
}

const Ctx = createContext<TravelStore | null>(null);

// ── coercion helpers for untrusted ui_command payloads ────────────────────────
const str = (v: unknown): string | undefined => (typeof v === 'string' && v ? v : undefined);
const arr = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);

function normalizeOptionsIds<T extends { id?: string }>(items: T[], prefix: string): T[] {
  return items.map((it, i) => ({ ...it, id: it.id && String(it.id) ? String(it.id) : `${prefix}${i + 1}` }));
}

// Background-task cadence. Searches feel like a real fare/hotel API call; the
// day-plan build runs a touch longer. A finished task lingers in the tray so the
// agent can see it land before it fades. (Mirrors the servicing prep cadence.)
const TASK_LEAD = 350;
const SEARCH_RUN_MIN = 3200;
const SEARCH_RUN_VAR = 1600; // flights/hotels ≈ 3.2–4.8s
const BUILD_RUN = 5200; // day-plan build ≈ 5.5s
const TASK_LINGER = 4500;
let _taskSeq = 0;
const newTaskId = (): string => `tk-${Date.now().toString(36)}-${_taskSeq++}`;
const searchRunMs = (): number => SEARCH_RUN_MIN + Math.floor(Math.random() * SEARCH_RUN_VAR);

/** Coerce an untrusted day-plan payload into a DayPlan (null if no valid day). */
function toDayPlan(p: Record<string, unknown>): DayPlan | null {
  const day = typeof p.day === 'number' ? p.day : Number(p.day);
  if (!Number.isFinite(day) || day < 1) return null;
  return {
    day,
    date: str(p.date),
    title: str(p.title) ?? `Day ${day}`,
    transport: str(p.transport),
    breakfast: str(p.breakfast),
    lunch: str(p.lunch),
    dinner: str(p.dinner),
    activities: arr<Activity>(p.activities),
  };
}

function buildItinerary(raw: Record<string, unknown>): Itinerary {
  const name = str(raw.name) ?? 'Untitled trip';
  const hotelCities = arr<Record<string, unknown>>(raw.hotel_cities);
  const legs = arr<Record<string, unknown>>(raw.legs).map<Leg>((l, i) => ({
    id: str(l.id) ?? `leg${i + 1}`,
    label: str(l.label) ?? `${str(l.from) ?? ''} → ${str(l.to) ?? ''}`,
    from: str(l.from),
    to: str(l.to),
    date: str(l.date) ?? '',
  }));
  return {
    id: slugify(name),
    name,
    coordinator: str(raw.coordinator),
    destination: str(raw.destination),
    start_date: str(raw.start_date),
    end_date: str(raw.end_date),
    summary: str(raw.summary),
    families: arr(raw.families),
    legs,
    hotels: hotelCities.map<HotelStay>((c) => ({
      city: str(c.city) ?? '',
      nights: typeof c.nights === 'number' ? c.nights : undefined,
    })),
    days: [],
    specialRequests: [],
    inclusions: [],
    exclusions: [],
    terms: [],
    whatsapp: null,
    createdAt: now(),
    updatedAt: now(),
  };
}

export function TravelProvider({ children }: { children: ReactNode }) {
  const [itineraries, setItineraries] = useState<Itinerary[]>(loadItineraries);
  const [activeId, setActiveId] = useState<string | null>(loadActiveId);
  const [view, setView] = useState<View>(() => (loadActiveId() ? 'overview' : 'dashboard'));
  const [flightsLeg, setFlightsLeg] = useState<string | null>(null);
  const [hotelsCity, setHotelsCity] = useState<string | null>(null);
  const [highlighted, setHighlighted] = useState<Highlight | null>(null);
  const [whatsappOpen, setWhatsappOpen] = useState(false);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [rev, setRev] = useState(0);
  const agentSendRef = useRef<AgentSend | null>(null);
  const [, forceTick] = useState(0);

  // Background-task timers (search / build animation), cleared on unmount.
  const timersRef = useRef<number[]>([]);
  useEffect(
    () => () => {
      timersRef.current.forEach((t) => window.clearTimeout(t));
      timersRef.current = [];
    },
    [],
  );
  // Latest active id, readable from a timer that fired after a nav change.
  const activeIdRef = useRef<string | null>(activeId);
  activeIdRef.current = activeId;

  const registerAgentSend = useCallback((fn: AgentSend | null) => {
    agentSendRef.current = fn;
    forceTick((t) => t + 1);
  }, []);

  // Apply a change to the active itinerary, persist, and bump rev (→ state_sync).
  const mutateActive = useCallback(
    (fn: (it: Itinerary) => Itinerary) => {
      setItineraries((list) => {
        const id = activeId;
        if (!id) return list;
        let changed = false;
        const next = list.map((it) => {
          if (it.id !== id) return it;
          changed = true;
          return { ...fn(it), updatedAt: now() };
        });
        if (!changed) return list;
        persist(next, id);
        return next;
      });
      setRev((r) => r + 1);
    },
    [activeId],
  );

  // Apply a change to a SPECIFIC itinerary id (used by background tasks, which
  // capture the itinerary they were started for and may complete after the agent
  // has navigated elsewhere). Persists under whatever is active now.
  const mutateById = useCallback((id: string, fn: (it: Itinerary) => Itinerary) => {
    setItineraries((list) => {
      let changed = false;
      const next = list.map((it) => {
        if (it.id !== id) return it;
        changed = true;
        return { ...fn(it), updatedAt: now() };
      });
      if (!changed) return list;
      persist(next, activeIdRef.current);
      return next;
    });
    setRev((r) => r + 1);
  }, []);

  const openDashboard = useCallback(() => {
    activeIdRef.current = null; // sync, before React commits
    setView('dashboard');
    setActiveId(null);
    persist(itineraries, null);
    setRev((r) => r + 1);
  }, [itineraries]);

  const setActive = useCallback(
    (id: string, list?: Itinerary[]) => {
      // Update the ref synchronously so a search fired in the SAME tick as the
      // open (two back-to-back ui_commands) still targets the right itinerary.
      activeIdRef.current = id;
      setActiveId(id);
      setView('overview');
      setWhatsappOpen(false);
      persist(list ?? itineraries, id);
      setRev((r) => r + 1);
    },
    [itineraries],
  );

  const createItinerary = useCallback((raw: Record<string, unknown>) => {
    const built = buildItinerary(raw);
    setItineraries((list) => {
      // Replace any existing itinerary with the same slug (re-create), else add.
      const exists = list.some((it) => it.id === built.id);
      const next = exists ? list.map((it) => (it.id === built.id ? built : it)) : [built, ...list];
      persist(next, built.id);
      return next;
    });
    activeIdRef.current = built.id; // sync, before React commits
    setActiveId(built.id);
    setView('overview');
    setWhatsappOpen(false);
    setRev((r) => r + 1);
  }, []);

  const newBlankItinerary = useCallback(() => {
    createItinerary({ name: 'Untitled trip' });
  }, [createItinerary]);

  const openItinerary = useCallback(
    (idOrName: string) => {
      const needle = idOrName.toLowerCase().trim();
      const match = itineraries.find(
        (it) => it.id === needle || it.id === slugify(idOrName) || it.name.toLowerCase() === needle,
      );
      if (match) setActive(match.id);
    },
    [itineraries, setActive],
  );

  const setSpecialRequests = useCallback(
    (requests: SpecialRequest[]) => mutateActive((it) => ({ ...it, specialRequests: requests })),
    [mutateActive],
  );

  // Fill the trip structure (travellers, legs, hotel cities) onto the active itinerary —
  // the heavy part split out of create_itinerary so the shell renders first. Legs are
  // merged by id so any options already searched for a leg survive a re-call.
  const setTripStructure = useCallback(
    (raw: Record<string, unknown>) =>
      mutateActive((it) => {
        const families = arr<Family>(raw.families);
        const rawLegs = arr<Record<string, unknown>>(raw.legs);
        const legs: Leg[] =
          rawLegs.length === 0
            ? it.legs
            : rawLegs.map((l, i) => {
                const id = str(l.id) ?? `leg${i + 1}`;
                const existing = it.legs.find((e) => e.id === id);
                return {
                  ...existing,
                  id,
                  label: str(l.label) ?? `${str(l.from) ?? ''} → ${str(l.to) ?? ''}`,
                  from: str(l.from),
                  to: str(l.to),
                  date: str(l.date) ?? existing?.date ?? '',
                };
              });
        const rawCities = arr<Record<string, unknown>>(raw.hotel_cities);
        const hotels =
          rawCities.length === 0
            ? it.hotels
            : rawCities.map((c) => {
                const city = str(c.city) ?? '';
                const existing = it.hotels.find((h) => h.city === city);
                return {
                  ...existing,
                  city,
                  nights: typeof c.nights === 'number' ? c.nights : existing?.nights,
                };
              });
        return {
          ...it,
          families: families.length ? families : it.families,
          legs,
          hotels,
        };
      }),
    [mutateActive],
  );

  const presentFlights = useCallback(
    (legId: string, options: FlightOption[]) => {
      const opts = normalizeOptionsIds(options, 'f');
      mutateActive((it) => ({
        ...it,
        legs: it.legs.map((l) => (l.id === legId ? { ...l, options: opts } : l)),
      }));
      setFlightsLeg(legId);
      setView('flights');
    },
    [mutateActive],
  );

  const selectFlight = useCallback(
    (legId: string, optionId: string) => {
      mutateActive((it) => ({
        ...it,
        legs: it.legs.map((l) => (l.id === legId ? { ...l, selectedId: optionId } : l)),
      }));
      setView('overview');
      setHighlighted({ section: 'flights', nonce: now() });
    },
    [mutateActive],
  );

  const presentHotels = useCallback(
    (city: string, options: HotelOption[]) => {
      const opts = normalizeOptionsIds(options, 'h');
      mutateActive((it) => {
        const has = it.hotels.some((h) => h.city === city);
        const hotels = has
          ? it.hotels.map((h) => (h.city === city ? { ...h, options: opts } : h))
          : [...it.hotels, { city, options: opts }];
        return { ...it, hotels };
      });
      setHotelsCity(city);
      setView('hotels');
    },
    [mutateActive],
  );

  const selectHotel = useCallback(
    (city: string, optionId: string) => {
      mutateActive((it) => ({
        ...it,
        hotels: it.hotels.map((h) => (h.city === city ? { ...h, selectedId: optionId } : h)),
      }));
      setView('overview');
      setHighlighted({ section: 'hotels', nonce: now() });
    },
    [mutateActive],
  );

  // ── Background tasks (search flights/hotels, build the day plan) ─────────────
  // Each kicks off a task that animates in the tray for a few seconds, then
  // reveals its result onto the itinerary it was started for. The agent gets
  // control back at once — never blocked — and several can run at the same time.
  const runTask = useCallback(
    (
      kind: TaskKind,
      label: string,
      detail: string | undefined,
      target: Task['target'],
      runMs: number,
      apply: (itineraryId: string) => void,
    ) => {
      const itineraryId = activeIdRef.current;
      if (!itineraryId) return; // searches only make sense with a trip open
      const id = newTaskId();
      setTasks((ts) => [
        ...ts,
        { id, kind, label, detail, status: 'running', itineraryId, target, startedAt: now() },
      ]);
      setRev((r) => r + 1);
      timersRef.current.push(
        window.setTimeout(() => {
          apply(itineraryId);
          setTasks((ts) => ts.map((t) => (t.id === id ? { ...t, status: 'done' } : t)));
          setRev((r) => r + 1);
          timersRef.current.push(
            window.setTimeout(() => {
              setTasks((ts) => ts.filter((t) => t.id !== id));
            }, TASK_LINGER),
          );
        }, TASK_LEAD + runMs),
      );
    },
    [],
  );

  const searchFlights = useCallback(
    (legId: string, options: FlightOption[]) => {
      const opts = normalizeOptionsIds(options, 'f');
      const leg = itineraries.find((i) => i.id === activeIdRef.current)?.legs.find((l) => l.id === legId);
      runTask('flights', `Searching flights · ${leg?.label ?? legId}`, `${opts.length} fares`, { legId }, searchRunMs(), (id) =>
        mutateById(id, (it) => ({
          ...it,
          legs: it.legs.map((l) => (l.id === legId ? { ...l, options: opts } : l)),
        })),
      );
      // Open the flights screen so the search is visible (skeleton → option cards
      // when it lands). The agent keeps control; only the canvas follows the search.
      setFlightsLeg(legId);
      setView('flights');
    },
    [itineraries, runTask, mutateById],
  );

  const searchHotels = useCallback(
    (city: string, options: HotelOption[]) => {
      const opts = normalizeOptionsIds(options, 'h');
      runTask('hotels', `Searching hotels · ${city}`, `${opts.length} properties`, { city }, searchRunMs(), (id) =>
        mutateById(id, (it) => {
          const has = it.hotels.some((h) => h.city === city);
          const hotels = has
            ? it.hotels.map((h) => (h.city === city ? { ...h, options: opts } : h))
            : [...it.hotels, { city, options: opts }];
          return { ...it, hotels };
        }),
      );
      // Open the hotels screen so the search is visible (skeleton → option cards).
      setHotelsCity(city);
      setView('hotels');
    },
    [runTask, mutateById],
  );

  const generateDayPlan = useCallback(
    (days: DayPlan[]) => {
      if (!days.length) return;
      runTask('dayplan', `Building day-wise plan · ${days.length} days`, undefined, {}, BUILD_RUN, (id) =>
        mutateById(id, (it) => {
          const byDay = new Map(it.days.map((d) => [d.day, d]));
          for (const d of days) byDay.set(d.day, d);
          const merged = [...byDay.values()].sort((a, b) => a.day - b.day);
          return { ...it, days: merged };
        }),
      );
    },
    [runTask, mutateById],
  );

  const openTaskTarget = useCallback(
    (task: Task) => {
      if (task.itineraryId !== activeIdRef.current) setActive(task.itineraryId);
      if (task.kind === 'flights' && task.target?.legId) {
        setFlightsLeg(task.target.legId);
        setView('flights');
      } else if (task.kind === 'hotels' && task.target?.city) {
        setHotelsCity(task.target.city);
        setView('hotels');
      } else {
        setView('overview');
        setHighlighted({ section: 'days', nonce: now() });
      }
      setRev((r) => r + 1);
    },
    [setActive],
  );

  const setDayPlan = useCallback(
    (plan: DayPlan) =>
      mutateActive((it) => {
        const has = it.days.some((d) => d.day === plan.day);
        const days = (
          has ? it.days.map((d) => (d.day === plan.day ? plan : d)) : [...it.days, plan]
        ).sort((a, b) => a.day - b.day);
        return { ...it, days };
      }),
    [mutateActive],
  );

  const setInclusions = useCallback(
    (inclusions: string[], exclusions: string[]) =>
      mutateActive((it) => ({ ...it, inclusions, exclusions })),
    [mutateActive],
  );

  const setTerms = useCallback(
    (terms: string[]) => mutateActive((it) => ({ ...it, terms })),
    [mutateActive],
  );

  const patchDates = useCallback(
    (updates: { leg_id: string; new_date: string }[], summary: string) =>
      mutateActive((it) => {
        const byId = new Map(updates.map((u) => [u.leg_id, u.new_date]));
        return {
          ...it,
          legs: it.legs.map((l) => (byId.has(l.id) ? { ...l, date: byId.get(l.id)! } : l)),
          patchNote: summary || it.patchNote,
        };
      }),
    [mutateActive],
  );

  const highlight = useCallback((section: string) => {
    setView('overview');
    setHighlighted({ section, nonce: now() });
  }, []);

  const sendWhatsApp = useCallback(
    (to: string, recipient: string) => {
      mutateActive((it) => ({ ...it, whatsapp: { to, recipient, sentAt: now() } }));
      setWhatsappOpen(true);
    },
    [mutateActive],
  );

  const openWhatsAppPreview = useCallback(() => setWhatsappOpen(true), []);
  const closeWhatsApp = useCallback(() => setWhatsappOpen(false), []);

  const viewFlights = useCallback((legId: string) => {
    setFlightsLeg(legId);
    setView('flights');
  }, []);

  const viewHotels = useCallback((city: string) => {
    setHotelsCity(city);
    setView('hotels');
  }, []);

  const active = useMemo(
    () => itineraries.find((it) => it.id === activeId) ?? null,
    [itineraries, activeId],
  );

  const snapshot = useCallback((): Record<string, unknown> | null => {
    if (!active) return null;
    return {
      name: active.name,
      // Where the agent is, plus any searches still running — so the assistant can
      // ground a turn ("you're on the Phu Quoc hotels screen") and know whether a
      // search has finished before it tries to select.
      screen: view,
      screen_context:
        view === 'flights' ? flightsLeg : view === 'hotels' ? hotelsCity : null,
      tasks: tasks
        .filter((t) => t.itineraryId === active.id)
        .map((t) => ({ kind: t.kind, label: t.label, status: t.status })),
      coordinator: active.coordinator,
      destination: active.destination,
      dates: [active.start_date, active.end_date].filter(Boolean).join(' – '),
      pax: paxSummary(active),
      families: active.families.map((f) => ({
        label: f.label,
        origin: f.origin,
        meal: f.meal,
        infants: f.infants,
        assistance: f.assistance,
      })),
      special_requests: active.specialRequests.map((r) => `${r.label}${r.detail ? ` (${r.detail})` : ''}`),
      legs: active.legs.map((l) => {
        const sel = selectedFlight(l);
        return {
          id: l.id,
          label: l.label,
          date: l.date,
          options_shown: l.options?.length ?? 0,
          selected: sel ? `${sel.airline} ${sel.flight_no ?? ''} ${sel.depart}→${sel.arrive}`.trim() : null,
        };
      }),
      hotels: active.hotels.map((h) => {
        const sel = selectedHotel(h);
        return {
          city: h.city,
          options_shown: h.options?.length ?? 0,
          selected: sel ? `${sel.name} (${sel.stars ?? 5}★)` : null,
        };
      }),
      days: active.days.map((d) => ({ day: d.day, date: d.date, title: d.title })),
      inclusions: active.inclusions,
      exclusions: active.exclusions,
      terms_set: active.terms.length > 0,
      whatsapp_sent: Boolean(active.whatsapp),
      patch_note: active.patchNote,
    };
  }, [active, view, flightsLeg, hotelsCity, tasks]);

  const handleUiCommand = useCallback(
    (cmd: Record<string, unknown>) => {
      const action = String(cmd.action ?? '');
      switch (action) {
        case 'open_dashboard':
          openDashboard();
          break;
        case 'open_itinerary':
          if (str(cmd.name)) openItinerary(str(cmd.name)!);
          break;
        case 'create_itinerary':
          if (cmd.itinerary && typeof cmd.itinerary === 'object') {
            createItinerary(cmd.itinerary as Record<string, unknown>);
          }
          break;
        case 'set_trip_structure':
          setTripStructure(cmd);
          break;
        case 'set_special_requests':
          setSpecialRequests(arr<SpecialRequest>(cmd.requests));
          break;
        // Background search (current path). present_* kept for back-compat / manual.
        case 'search_flights':
          if (str(cmd.leg_id)) searchFlights(str(cmd.leg_id)!, arr<FlightOption>(cmd.options));
          break;
        case 'present_flight_options':
          if (str(cmd.leg_id)) presentFlights(str(cmd.leg_id)!, arr<FlightOption>(cmd.options));
          break;
        case 'show_flights':
          if (str(cmd.leg_id)) viewFlights(str(cmd.leg_id)!);
          break;
        case 'select_flight':
          if (str(cmd.leg_id) && str(cmd.option_id)) selectFlight(str(cmd.leg_id)!, str(cmd.option_id)!);
          break;
        case 'search_hotels':
          if (str(cmd.city)) searchHotels(str(cmd.city)!, arr<HotelOption>(cmd.options));
          break;
        case 'present_hotel_options':
          if (str(cmd.city)) presentHotels(str(cmd.city)!, arr<HotelOption>(cmd.options));
          break;
        case 'show_hotels':
          if (str(cmd.city)) viewHotels(str(cmd.city)!);
          break;
        case 'select_hotel':
          if (str(cmd.city) && str(cmd.option_id)) selectHotel(str(cmd.city)!, str(cmd.option_id)!);
          break;
        case 'generate_day_plan': {
          const days = arr<Record<string, unknown>>(cmd.days)
            .map(toDayPlan)
            .filter((d): d is DayPlan => d !== null);
          if (days.length) generateDayPlan(days);
          break;
        }
        case 'set_day_plan':
          if (cmd.plan && typeof cmd.plan === 'object') {
            const plan = toDayPlan(cmd.plan as Record<string, unknown>);
            if (plan) setDayPlan(plan);
          }
          break;
        case 'set_inclusions':
          setInclusions(arr<string>(cmd.inclusions).map(String), arr<string>(cmd.exclusions).map(String));
          break;
        case 'set_terms':
          setTerms(arr<string>(cmd.terms).map(String));
          break;
        case 'patch_dates': {
          const updates = arr<Record<string, unknown>>(cmd.updates)
            .map((u) => ({ leg_id: str(u.leg_id) ?? '', new_date: str(u.new_date) ?? '' }))
            .filter((u) => u.leg_id && u.new_date);
          if (updates.length) patchDates(updates, str(cmd.summary) ?? '');
          break;
        }
        case 'highlight':
          if (str(cmd.section)) highlight(str(cmd.section)!);
          break;
        case 'send_whatsapp':
          sendWhatsApp(str(cmd.to) ?? '', str(cmd.recipient_name) ?? '');
          break;
        default:
          break;
      }
    },
    [
      openDashboard,
      openItinerary,
      createItinerary,
      setTripStructure,
      setSpecialRequests,
      presentFlights,
      selectFlight,
      presentHotels,
      selectHotel,
      searchFlights,
      searchHotels,
      viewFlights,
      viewHotels,
      generateDayPlan,
      setDayPlan,
      setInclusions,
      setTerms,
      patchDates,
      highlight,
      sendWhatsApp,
    ],
  );

  // Rebuilt each render (like the orders store) so `agentSend` always reflects
  // the latest registered channel.
  const store: TravelStore = {
    itineraries,
    active,
    view,
    flightsLeg,
    hotelsCity,
    highlighted,
    whatsappOpen,
    tasks,
    openTaskTarget,
    rev,
    agentSend: agentSendRef.current,
    registerAgentSend,
    snapshot,
    handleUiCommand,
    openDashboard,
    newBlankItinerary,
    openItinerary,
    createItinerary,
    setTripStructure,
    setSpecialRequests,
    presentFlights,
    selectFlight,
    presentHotels,
    selectHotel,
    searchFlights,
    searchHotels,
    generateDayPlan,
    setDayPlan,
    setInclusions,
    setTerms,
    patchDates,
    highlight,
    sendWhatsApp,
    openWhatsAppPreview,
    closeWhatsApp,
    viewFlights,
    viewHotels,
  };

  return <Ctx.Provider value={store}>{children}</Ctx.Provider>;
}

export function useTravel(): TravelStore {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useTravel must be used within TravelProvider');
  return ctx;
}
