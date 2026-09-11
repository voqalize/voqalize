/**
 * TravelStore — the single source of truth for the Travel Desk demo.
 *
 * Both the human (clicking the portal) and the Travel Desk agent (via `ui-command`
 * RTVI messages) call the SAME actions, so the screen stays consistent no matter
 * who is driving. Navigation is plain React state — never the router — so the
 * `PipecatClient` mounted alongside never unmounts and the call stays live.
 *
 * Itineraries persist to localStorage (build-from-scratch: trips created during a
 * call survive a reload, so "open Poddar's Vietnam trip" works later) — which is
 * why the brain has never seen a saved draft until one is opened, and why
 * `trip_opened` carries the whole overview while every other event carries only
 * what moved.
 *
 * **Who is driving is not a flag on a message — it is which function you called.**
 * `byHand` is the travel agent's own surface: each entry does the mutation and
 * then tells the brain what they just did. `handleUiCommand` calls the same
 * mutations without the telling, because a command the brain sent is one it
 * already knows about. That split is what replaced the debounced whole-itinerary
 * push the brain used to have to diff against its last copy to guess what
 * changed.
 *
 * Both halves are typed off `actions.gen.ts`, generated from the `Action` and
 * `AppEvent` classes in `demos/travel/backend/brain_gemini.py`: each `ui-command`
 * payload arrives typed and the `default` arm is an exhaustiveness check, and
 * each event leaves typed. `TravelAdvisor` subscribes to pipecat's
 * `RTVIEvent.UICommand` once and hands every envelope here.
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
import {
  asUiAction,
  sendAppEvent,
  unhandledUiAction,
  type AppEvent,
  type Itinerary as ItineraryWire,
  type SetTripStructure,
  type TripOpened,
} from './actions.gen';
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

/** A pipecat client's `sendUIEvent`, or null before the call connects. */
export type AgentSend = ((event: string, payload?: unknown) => void) | null;

/**
 * What `createItinerary` needs: the wire shell, or just a name.
 *
 * The brain always sends a complete shell (a pydantic `Action` emits its whole
 * shape), but the "New trip" button in the UI has only a placeholder name — so
 * everything but `name` is optional here, and the store fills the rest.
 */
export type NewItinerary = Partial<ItineraryWire> & { name: string };

export interface TravelActions {
  openDashboard: () => void;
  newBlankItinerary: () => void;
  /** Open the draft `ref` names — id first, then name. False when none matches. */
  openItinerary: (ref: string | undefined) => boolean;
  /** Build and open a new itinerary. `name` is all the agent must send. */
  createItinerary: (wire: NewItinerary) => void;
  setTripStructure: (args: SetTripStructure) => void;
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

/**
 * The travel agent's own gestures. Each mutates the screen and then names the
 * act for the brain — the two halves of one thing, so a page cannot do the first
 * and forget the second. `handleUiCommand` drives the same mutations without the
 * telling: the brain does not need to be told what it asked for.
 */
export interface ByHand {
  openDashboard: () => void;
  /** Open a saved draft — the brain's first sight of it, so the overview goes too. */
  openTrip: (idOrName: string) => void;
  newTrip: () => void;
  backToOverview: () => void;
  viewFlights: (leg: Leg) => void;
  viewHotels: (city: string) => void;
  selectFlight: (leg: Leg, opt: FlightOption) => void;
  selectHotel: (stay: HotelStay, opt: HotelOption) => void;
  shareQuote: (to: string, recipient: string) => void;
  openTaskTarget: (task: Task) => void;
}

/**
 * The itinerary as the overview shows it — the payload of `trip_opened`.
 *
 * Picks and counts, never the option lists: this is the brain's mirror of a
 * screen, not a copy of the store. What the agent chose is here; the fares they
 * did not choose are the browser's business.
 */
function overviewOf(it: Itinerary): TripOpened {
  return {
    id: it.id,
    name: it.name,
    coordinator: it.coordinator,
    destination: it.destination,
    dates: [it.start_date, it.end_date].filter(Boolean).join(' – '),
    pax: paxSummary(it),
    families: it.families.map(familyLine),
    special_requests: it.specialRequests.map((r) => `${r.label}${r.detail ? ` (${r.detail})` : ''}`),
    legs: it.legs.map((l) => ({
      id: l.id,
      label: l.label,
      date: l.date,
      options_shown: l.options?.length ?? 0,
      selected: flightLine(selectedFlight(l)),
    })),
    hotels: it.hotels.map((h) => ({
      city: h.city,
      options_shown: h.options?.length ?? 0,
      selected: hotelLine(selectedHotel(h)),
    })),
    days: it.days.map((d) => `Day ${d.day}${d.date ? ` · ${d.date}` : ''} · ${d.title}`),
    inclusions: it.inclusions,
    exclusions: it.exclusions,
    terms_set: it.terms.length > 0,
    whatsapp_sent: Boolean(it.whatsapp),
  };
}

/** One saved draft as the brain's catalog lists it. */
export interface DraftLine {
  id: string;
  name: string;
  destination: string;
  dates: string;
}

/**
 * The saved drafts, for the connect request's `init`. They live in this browser,
 * so this is the only way the brain learns which exist and what each is keyed by
 * — without the ids, `open_itinerary` is a guess at a name.
 */
export function draftsOf(list: Itinerary[]): DraftLine[] {
  return list.map((it) => ({
    id: it.id,
    name: it.name,
    destination: it.destination ?? '',
    dates: [it.start_date, it.end_date].filter(Boolean).join(' – '),
  }));
}

/**
 * A name the way it is said rather than typed: NFKC-normalized, lower-cased,
 * one space between words. The brain folds the same way.
 */
function spoken(s: string): string {
  return s.normalize('NFKC').toLowerCase().replace(/\s+/g, ' ').trim();
}

/**
 * The draft `ref` names: its exact id, then its id or name as spoken, then its
 * slug — the order the brain resolves in. `slugify` falls back to `'trip'` for a
 * name with no Latin letters, so that fallback never counts as a match.
 */
function findDraft(list: Itinerary[], ref: string | undefined): Itinerary | undefined {
  const needle = (ref ?? '').trim();
  if (!needle) return undefined;
  const said = spoken(needle);
  const slug = slugify(needle);
  return (
    list.find((it) => it.id === needle) ??
    list.find((it) => spoken(it.id) === said || spoken(it.name) === said) ??
    (slug !== 'trip' ? list.find((it) => it.id === slug) : undefined)
  );
}

/** One family, worded the way the brain words it from its own `set_trip_structure`. */
function familyLine(f: Family): string {
  const heads = [
    f.adults ? `${f.adults} adults` : '',
    f.children ? `${f.children} children` : '',
    f.infants ? `${f.infants} infants` : '',
  ].filter(Boolean);
  return [
    f.label,
    f.origin ? `from ${f.origin}` : '',
    heads.join(', '),
    f.meal && f.meal !== 'mixed' ? f.meal : '',
    f.assistance ?? '',
  ]
    .filter(Boolean)
    .join(' · ');
}

/** A picked flight, worded as the brain words it. */
function flightLine(opt: FlightOption | undefined): string {
  if (!opt) return '';
  const head = [opt.airline, opt.flight_no].filter(Boolean).join(' ');
  return opt.depart || opt.arrive ? `${head} ${opt.depart}→${opt.arrive}` : head;
}

/** A picked hotel, worded as the brain words it. */
function hotelLine(opt: HotelOption | undefined): string {
  return opt ? `${opt.name} (${opt.stars ?? 5}★)` : '';
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
  /** Bumps on every data mutation; the UI re-renders off it. */
  rev: number;
  agentSend: AgentSend;
  registerAgentSend: (fn: AgentSend) => void;
  /** The travel agent's own gestures: mutate the screen, then say what they did. */
  byHand: ByHand;
  /** Dispatch a `ui-command` RTVI event's `{ command, payload }` from the agent. */
  handleUiCommand: (command: string, payload: unknown) => void;
}

const Ctx = createContext<TravelStore | null>(null);

function normalizeOptionsIds<T extends { id?: string }>(items: T[], prefix: string): T[] {
  return items.map((it, i) => ({ ...it, id: it.id && String(it.id) ? String(it.id) : `${prefix}${i + 1}` }));
}

// Background-task cadence. Searches feel like a real fare/hotel API call; the
// day-plan build runs a touch longer. A finished task lingers in the tray so the
// agent can see it land before it fades. (Mirrors the servicing prep cadence.)
/** What the "New trip" button names a draft; the brain mirrors the same name. */
const BLANK_TRIP_NAME = 'Untitled trip';

const TASK_LEAD = 350;
const SEARCH_RUN_MIN = 3200;
const SEARCH_RUN_VAR = 1600; // flights/hotels ≈ 3.2–4.8s
const BUILD_RUN = 5200; // day-plan build ≈ 5.5s
const TASK_LINGER = 4500;
let _taskSeq = 0;
const newTaskId = (): string => `tk-${Date.now().toString(36)}-${_taskSeq++}`;
const searchRunMs = (): number => SEARCH_RUN_MIN + Math.floor(Math.random() * SEARCH_RUN_VAR);

/** The wire shell as the store's own itinerary — id, timestamps, empty sections. */
function buildItinerary(wire: NewItinerary): Itinerary {
  const name = wire.name || 'Untitled trip';
  return {
    // The brain mints the id (unique, and numbered for a name with no Latin
    // letters); the slug is for the "New trip" button and an older brain.
    id: wire.id || slugify(name),
    name,
    coordinator: wire.coordinator,
    destination: wire.destination,
    start_date: wire.start_date,
    end_date: wire.end_date,
    summary: wire.summary,
    families: wire.families ?? [],
    legs: (wire.legs ?? []).map<Leg>((l, i) => ({
      id: l.id || `leg${i + 1}`,
      label: l.label || `${l.from} → ${l.to}`,
      from: l.from,
      to: l.to,
      date: l.date,
    })),
    hotels: (wire.hotel_cities ?? []).map<HotelStay>((c) => ({
      city: c.city,
      nights: c.nights,
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
  const agentSendRef = useRef<AgentSend>(null);
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

  const registerAgentSend = useCallback((fn: AgentSend) => {
    agentSendRef.current = fn;
    forceTick((t) => t + 1);
  }, []);

  const emit = useCallback((event: AppEvent) => sendAppEvent(agentSendRef.current, event), []);

  // Apply a change to the active itinerary, persist, and bump rev.
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
      const all = list ?? itineraries;
      persist(all, id);
      setRev((r) => r + 1);
      // The handover, and the one event that carries a whole screen: these drafts
      // live in this browser, so until now the brain did not know this trip
      // exists. It goes whoever opened it — the brain asking for it by name has
      // no more idea what is in it than the agent's own click does.
      const opened = all.find((it) => it.id === id);
      if (opened) emit({ event: 'trip_opened', payload: overviewOf(opened) });
    },
    [itineraries, emit],
  );

  const createItinerary = useCallback((wire: NewItinerary) => {
    const built = buildItinerary(wire);
    setItineraries((list) => {
      // Replace any existing itinerary with the same id (re-create), else add.
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
    createItinerary({ name: BLANK_TRIP_NAME });
  }, [createItinerary]);

  const openItinerary = useCallback(
    (ref: string | undefined) => {
      const match = findDraft(itineraries, ref);
      if (match) setActive(match.id);
      return match !== undefined;
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
    ({ families, legs: wireLegs, hotel_cities }: SetTripStructure) =>
      mutateActive((it) => {
        const legs: Leg[] =
          wireLegs.length === 0
            ? it.legs
            : wireLegs.map((l, i) => {
                const id = l.id || `leg${i + 1}`;
                const existing = it.legs.find((e) => e.id === id);
                return {
                  ...existing,
                  id,
                  label: l.label || `${l.from} → ${l.to}`,
                  from: l.from,
                  to: l.to,
                  date: l.date || existing?.date || '',
                };
              });
        const hotels =
          hotel_cities.length === 0
            ? it.hotels
            : hotel_cities.map((c) => {
                const existing = it.hotels.find((h) => h.city === c.city);
                return { ...existing, city: c.city, nights: c.nights };
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

  const viewOverview = useCallback(() => setView('overview'), []);

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

  // The agent's ten commands. Each payload is the shape its Python `Action`
  // emits, so there is nothing left to coerce or null-check, and the exhausted
  // `default` arm makes an eleventh action a compile error here.
  const handleUiCommand = useCallback(
    (command: string, payload: unknown) => {
      const action = asUiAction(command, payload);
      if (!action) return;
      switch (action.command) {
        case 'open_dashboard':
          openDashboard();
          break;
        case 'open_itinerary': {
          // The id first; `name` is all an older brain sends. A draft this
          // browser does not hold is answered, not dropped: the brain has
          // already moved its mirror to an overview the screen never showed.
          const { id, name } = action.payload;
          if (!openItinerary(id) && !openItinerary(name)) {
            emit({ event: 'itinerary_not_found', payload: { id: id ?? '', name: name ?? '' } });
          }
          break;
        }
        case 'create_itinerary':
          createItinerary(action.payload.itinerary);
          break;
        case 'set_trip_structure':
          setTripStructure(action.payload);
          break;
        case 'search_flights':
          searchFlights(action.payload.leg_id, action.payload.options);
          break;
        case 'show_flights':
          viewFlights(action.payload.leg_id);
          break;
        case 'select_flight':
          selectFlight(action.payload.leg_id, action.payload.option_id);
          break;
        case 'search_hotels':
          searchHotels(action.payload.city, action.payload.options);
          break;
        case 'show_hotels':
          viewHotels(action.payload.city);
          break;
        case 'select_hotel':
          selectHotel(action.payload.city, action.payload.option_id);
          break;
        default:
          unhandledUiAction(action);
      }
    },
    [
      emit,
      openDashboard,
      openItinerary,
      createItinerary,
      setTripStructure,
      searchFlights,
      viewFlights,
      selectFlight,
      searchHotels,
      viewHotels,
      selectHotel,
    ],
  );

  // ── The travel agent's own hands ─────────────────────────────────────────
  // Every one of these is a mutation plus the sentence that names it. Nothing
  // here is reachable from `handleUiCommand`, which is the whole point: an event
  // is always the agent, so the brain never has to work out whether a change it
  // is being told about is its own command coming home.
  const byHand: ByHand = useMemo(
    () => ({
      openDashboard: () => {
        openDashboard();
        emit({ event: 'dashboard_opened', payload: {} });
      },
      openTrip: openItinerary,
      newTrip: () => {
        newBlankItinerary();
        emit({ event: 'trip_opened', payload: { id: slugify(BLANK_TRIP_NAME), name: BLANK_TRIP_NAME } });
      },
      backToOverview: () => {
        viewOverview();
        emit({ event: 'overview_viewed', payload: {} });
      },
      viewFlights: (leg) => {
        viewFlights(leg.id);
        emit({ event: 'flights_viewed', payload: { leg_id: leg.id, leg_label: leg.label } });
      },
      viewHotels: (city) => {
        viewHotels(city);
        emit({ event: 'hotels_viewed', payload: { city } });
      },
      selectFlight: (leg, opt) => {
        selectFlight(leg.id, opt.id);
        emit({
          event: 'flight_selected',
          payload: { leg_id: leg.id, option_id: opt.id, summary: flightLine(opt) },
        });
      },
      selectHotel: (stay, opt) => {
        selectHotel(stay.city, opt.id);
        emit({
          event: 'hotel_selected',
          payload: { city: stay.city, option_id: opt.id, summary: hotelLine(opt) },
        });
      },
      shareQuote: (to, recipient) => {
        sendWhatsApp(to, recipient);
        emit({ event: 'quote_shared', payload: { to, recipient } });
      },
      openTaskTarget: (task) => {
        openTaskTarget(task);
        // Where the tray click lands. `openTaskTarget` may switch itinerary on the
        // way, and that sends its own `trip_opened` — this names the screen it
        // settled on.
        if (task.kind === 'flights' && task.target?.legId) {
          emit({ event: 'flights_viewed', payload: { leg_id: task.target.legId } });
        } else if (task.kind === 'hotels' && task.target?.city) {
          emit({ event: 'hotels_viewed', payload: { city: task.target.city } });
        } else {
          emit({ event: 'overview_viewed', payload: {} });
        }
      },
    }),
    [
      emit,
      openDashboard,
      openItinerary,
      newBlankItinerary,
      viewOverview,
      viewFlights,
      viewHotels,
      selectFlight,
      selectHotel,
      sendWhatsApp,
      openTaskTarget,
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
    byHand,
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
