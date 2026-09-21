/**
 * TravelStore — the single source of truth for the Travel Desk demo.
 *
 * Both the human (clicking the portal) and Tess (via `ui-command` RTVI messages)
 * run the SAME transitions, so the screen stays consistent no matter who is
 * driving. Navigation is plain React state — never the router — so the
 * `PipecatClient` mounted alongside never unmounts and the call stays live.
 *
 * **One state object, moved by pure transitions.** Everything on screen — the
 * drafts, which one is open, which screen, the task tray — is one `State`, and
 * every change is a function from the state before to the state after, run by
 * `apply`. `apply` reads and writes a ref synchronously before React commits, so
 * two commands arriving in the same tick (open a trip, then search its outbound
 * leg) compose: the second sees the first's trip, not the render before it. That
 * is what the old per-field `useState`s could not promise, and why they grew an
 * `activeIdRef` and a render counter to paper over it. Persisting is an effect on
 * the committed state, not a side effect inside an updater.
 *
 * **An edit is a delta.** Tess changes one row at a time — `set_leg`,
 * `set_family`, `set_hotel_stay`, `update_trip` and their removes — so a moved
 * date keeps the leg's identity, and a leg keeps its fares and its pick unless
 * its route or date changed. The brain's mirror merges by the same rule.
 *
 * Itineraries persist to localStorage (trips created during a call survive a
 * reload, so "open Poddar's Vietnam trip" works later) — which is why the brain
 * has never seen a saved draft until one is opened, and why `trip_opened` carries
 * the whole overview while every other event carries only what moved.
 *
 * **Who is driving is not a flag on a message — it is which function you called.**
 * `byHand` is the travel agent's own surface: each entry runs the transition and
 * then tells the brain what they just did. `handleUiCommand` runs the same
 * transitions without the telling, because a command the brain sent is one it
 * already knows about.
 *
 * Both halves are typed off `actions.gen.ts`, generated from the `Action` and
 * `AppEvent` classes in `demos/travel/backend/`: each `ui-command` payload
 * arrives typed and the `default` arm is an exhaustiveness check, and each event
 * leaves typed. `TravelAdvisor` subscribes to pipecat's `RTVIEvent.UICommand`
 * once and hands every envelope here.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
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
  type Task,
  type TaskKind,
} from './types';
import {
  asUiAction,
  sendAppEvent,
  unhandledUiAction,
  type AppEvent,
  type DayPlan as DayPlanWire,
  type Itinerary as ItineraryWire,
  type Leg as LegWire,
  type SetTripStructure,
  type TripOpened,
  type UpdateTrip,
} from './actions.gen';
import { SEED_ITINERARIES } from './data';

export type View = 'dashboard' | 'overview' | 'flights' | 'hotels';

export interface Highlight {
  section: string;
  nonce: number;
}

/** Everything the portal shows, in one place. */
interface State {
  itineraries: Itinerary[];
  activeId: string | null;
  view: View;
  flightsLeg: string | null;
  hotelsCity: string | null;
  highlighted: Highlight | null;
  whatsappOpen: boolean;
  /** Background searches Tess has kicked off (running + recently done). */
  tasks: Task[];
}

/** One step of the portal: the state before, to the state after. */
type Transition = (s: State) => State;

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
    // Seed the saved drafts on first load (none saved yet). Once Tess or the
    // travel agent edits one, the list persists like any trip.
    if (Array.isArray(parsed) && parsed.length) return parsed as Itinerary[];
    return seedClone();
  } catch {
    return seedClone();
  }
}

function loadActiveId(list: Itinerary[]): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const id = window.localStorage.getItem(LS_ACTIVE);
    return id && list.some((it) => it.id === id) ? id : null;
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

function initialState(): State {
  const itineraries = loadItineraries();
  const activeId = loadActiveId(itineraries);
  return {
    itineraries,
    activeId,
    view: activeId ? 'overview' : 'dashboard',
    flightsLeg: null,
    hotelsCity: null,
    highlighted: null,
    whatsappOpen: false,
    tasks: [],
  };
}

function now(): number {
  return Date.now();
}

/** A pipecat client's `sendUIEvent`, or null before the call connects. */
export type AgentSend = ((event: string, payload?: unknown) => void) | null;

/**
 * What a new itinerary needs: the wire shell, or just a name.
 *
 * The brain always sends a complete shell (a pydantic `Action` emits its whole
 * shape), but the "New trip" button has only a placeholder name — so everything
 * but `name` is optional here, and the store fills the rest.
 */
type NewItinerary = Partial<ItineraryWire> & { name: string };

/**
 * The travel agent's own gestures. Each runs a transition and then names the act
 * for the brain — the two halves of one thing, so a page cannot do the first and
 * forget the second. `handleUiCommand` runs the same transitions without the
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
      from: l.from ?? '',
      to: l.to ?? '',
      date: l.date,
      options_shown: l.options?.length ?? 0,
      selected: flightLine(selectedFlight(l)),
    })),
    hotels: it.hotels.map((h) => ({
      city: h.city,
      nights: h.nights ?? 0,
      options_shown: h.options?.length ?? 0,
      selected: hotelLine(selectedHotel(h)),
    })),
    days: it.days.map((d) => ({
      day: d.day,
      date: d.date ?? '',
      title: d.title,
      transport: d.transport ?? '',
      breakfast: d.breakfast ?? '',
      lunch: d.lunch ?? '',
      dinner: d.dinner ?? '',
      activities: d.activities.map(activityLine),
    })),
    inclusions: it.inclusions,
    exclusions: it.exclusions,
    terms_set: it.terms.length > 0,
    whatsapp_sent: Boolean(it.whatsapp),
  };
}

/** One activity as one line — the same shape the brain writes into its mirror. */
function activityLine(a: Activity): string {
  const head = [a.time, a.title].filter(Boolean).join(' ');
  return `${head}${a.detail ? ` (${a.detail})` : ''}${a.ticket_included ? ' · ticket included' : ''}`;
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

export interface TravelStore {
  itineraries: Itinerary[];
  active: Itinerary | null;
  view: View;
  flightsLeg: string | null;
  hotelsCity: string | null;
  highlighted: Highlight | null;
  whatsappOpen: boolean;
  tasks: Task[];
  registerAgentSend: (fn: AgentSend) => void;
  /** The travel agent's own gestures: run the transition, then say what they did. */
  byHand: ByHand;
  /** Dispatch a `ui-command` RTVI event's `{ command, payload }` from Tess. */
  handleUiCommand: (command: string, payload: unknown) => void;
  /** Open the WhatsApp preview without marking it sent (manual share button). */
  openWhatsAppPreview: () => void;
  closeWhatsApp: () => void;
}

const Ctx = createContext<TravelStore | null>(null);

function withOptionIds<T extends { id?: string }>(items: T[], prefix: string): T[] {
  return items.map((it, i) => ({ ...it, id: it.id && String(it.id) ? String(it.id) : `${prefix}${i + 1}` }));
}

// Background-task cadence. Searches feel like a real fare/hotel API call. A
// finished task lingers in the tray so the agent can see it land before it fades.
/** What the "New trip" button names a draft; the brain mirrors the same name. */
const BLANK_TRIP_NAME = 'Untitled trip';

const TASK_LEAD = 350;
const SEARCH_RUN_MIN = 3200;
const SEARCH_RUN_VAR = 1600; // ≈ 3.2–4.8 s
const TASK_LINGER = 4500;
let _taskSeq = 0;
const newTaskId = (): string => `tk-${Date.now().toString(36)}-${_taskSeq++}`;
const searchRunMs = (): number => SEARCH_RUN_MIN + Math.floor(Math.random() * SEARCH_RUN_VAR);

/** The wire shell as the store's own itinerary — id, timestamps, empty sections. */
function buildItinerary(wire: NewItinerary): Itinerary {
  const name = wire.name || BLANK_TRIP_NAME;
  return {
    // The brain mints the id (unique, and numbered for a name with no Latin
    // letters); the slug is for the "New trip" button.
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
    hotels: (wire.hotel_cities ?? []).map<HotelStay>((c) => ({ city: c.city, nights: c.nights })),
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

// ── Transitions ─────────────────────────────────────────────────────────────
// Pure: each takes the state before and returns the state after, and returns
// the same object when nothing applies, so `apply` can skip the render.

/** Change one itinerary by id — the open one, or the one a background task was started for. */
function onTrip(id: string | null, fn: (it: Itinerary) => Itinerary): Transition {
  return (s) => {
    if (!id || !s.itineraries.some((it) => it.id === id)) return s;
    return {
      ...s,
      itineraries: s.itineraries.map((it) => (it.id === id ? { ...fn(it), updatedAt: now() } : it)),
    };
  };
}

/** Change the open itinerary. */
function onActive(fn: (it: Itinerary) => Itinerary): Transition {
  return (s) => onTrip(s.activeId, fn)(s);
}

function flash(section: string): Transition {
  return (s) => ({ ...s, highlighted: { section, nonce: now() } });
}

function seq(...steps: Transition[]): Transition {
  return (s) => steps.reduce((acc, step) => step(acc), s);
}

const toDashboard: Transition = (s) => ({ ...s, activeId: null, view: 'dashboard', whatsappOpen: false });

const toOverview: Transition = (s) => ({ ...s, view: 'overview' });

function toFlights(legId: string): Transition {
  return (s) => ({ ...s, view: 'flights', flightsLeg: legId });
}

function toHotels(city: string): Transition {
  return (s) => ({ ...s, view: 'hotels', hotelsCity: city });
}

function openTrip(id: string): Transition {
  return (s) => ({ ...s, activeId: id, view: 'overview', whatsappOpen: false });
}

function createTrip(wire: NewItinerary): Transition {
  return (s) => {
    const built = buildItinerary(wire);
    // Replace any existing itinerary with the same id (re-create), else add.
    const exists = s.itineraries.some((it) => it.id === built.id);
    const itineraries = exists
      ? s.itineraries.map((it) => (it.id === built.id ? built : it))
      : [built, ...s.itineraries];
    return openTrip(built.id)({ ...s, itineraries });
  };
}

// The first fill of an empty trip. Legs are merged by id so any options already
// searched for a leg survive a re-call; an empty list leaves that section alone.
function tripStructure({ families, legs: wireLegs, hotel_cities }: SetTripStructure): Transition {
  return onActive((it) => ({
    ...it,
    families: families.length ? families : it.families,
    legs: wireLegs.length
      ? wireLegs.map((l, i) => {
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
        })
      : it.legs,
    hotels: hotel_cities.length
      ? hotel_cities.map((c) => ({ ...it.hotels.find((h) => h.city === c.city), city: c.city, nights: c.nights }))
      : it.hotels,
  }));
}

function updateTrip(u: UpdateTrip): Transition {
  return onActive((it) => ({
    ...it,
    name: u.name ?? it.name,
    coordinator: u.coordinator ?? it.coordinator,
    destination: u.destination ?? it.destination,
    start_date: u.start_date ?? it.start_date,
    end_date: u.end_date ?? it.end_date,
    summary: u.summary ?? it.summary,
  }));
}

function setFamily(family: Family): Transition {
  return onActive((it) => {
    const at = it.families.findIndex((f) => f.label === family.label);
    const families = at < 0 ? [...it.families, family] : it.families.map((f, i) => (i === at ? family : f));
    return { ...it, families };
  });
}

function removeFamily(label: string): Transition {
  return onActive((it) => ({ ...it, families: it.families.filter((f) => f.label !== label) }));
}

/**
 * One leg, merged: an empty field keeps what the leg has. A new route or date
 * drops the fares and the pick, which were for a different flight — the brain's
 * `_merged_leg` applies the same rule, so the two agree without telling each other.
 */
function setLeg(wire: LegWire): Transition {
  return onActive((it) => {
    const existing = it.legs.find((l) => l.id === wire.id);
    if (!existing) {
      const leg: Leg = {
        id: wire.id,
        label: wire.label || `${wire.from} → ${wire.to}`,
        from: wire.from,
        to: wire.to,
        date: wire.date,
      };
      return { ...it, legs: [...it.legs, leg] };
    }
    const next: Leg = {
      ...existing,
      label: wire.label || existing.label,
      from: wire.from || existing.from,
      to: wire.to || existing.to,
      date: wire.date || existing.date,
    };
    const moved =
      (next.from ?? '') !== (existing.from ?? '') ||
      (next.to ?? '') !== (existing.to ?? '') ||
      next.date !== existing.date;
    if (moved) {
      delete next.options;
      delete next.selectedId;
    }
    return { ...it, legs: it.legs.map((l) => (l.id === wire.id ? next : l)) };
  });
}

function removeLeg(legId: string): Transition {
  return (s) =>
    onActive((it) => ({ ...it, legs: it.legs.filter((l) => l.id !== legId) }))(
      s.view === 'flights' && s.flightsLeg === legId ? toOverview(s) : s,
    );
}

function setHotelStay(city: string, nights: number): Transition {
  return onActive((it) => {
    const has = it.hotels.some((h) => h.city === city);
    const hotels = has
      ? it.hotels.map((h) => (h.city === city ? { ...h, nights } : h))
      : [...it.hotels, { city, nights }];
    return { ...it, hotels };
  });
}

function removeHotelStay(city: string): Transition {
  return (s) =>
    onActive((it) => ({ ...it, hotels: it.hotels.filter((h) => h.city !== city) }))(
      s.view === 'hotels' && s.hotelsCity === city ? toOverview(s) : s,
    );
}

/**
 * Upsert days by number. A field the brain left empty keeps what the day had;
 * activities, when given, replace the day's list.
 */
function setDays(plans: DayPlanWire[]): Transition {
  return onActive((it) => {
    const days = [...it.days];
    for (const p of plans) {
      const i = days.findIndex((d) => d.day === p.day);
      const was: DayPlan = i >= 0 ? days[i] : { day: p.day, title: '', activities: [] };
      const next: DayPlan = {
        ...was,
        date: p.date || was.date,
        title: p.title || was.title,
        transport: p.transport || was.transport,
        breakfast: p.breakfast || was.breakfast,
        lunch: p.lunch || was.lunch,
        dinner: p.dinner || was.dinner,
        activities: p.activities.length
          ? p.activities.map((a) => ({
              time: a.time || undefined,
              title: a.title,
              detail: a.detail || undefined,
              ticket_included: a.ticket_included,
            }))
          : was.activities,
      };
      if (i >= 0) days[i] = next;
      else days.push(next);
    }
    days.sort((a, b) => a.day - b.day);
    return { ...it, days };
  });
}

function removeDay(day: number): Transition {
  return onActive((it) => ({ ...it, days: it.days.filter((d) => d.day !== day) }));
}

function pickFlight(legId: string, optionId: string): Transition {
  return seq(
    onActive((it) => ({ ...it, legs: it.legs.map((l) => (l.id === legId ? { ...l, selectedId: optionId } : l)) })),
    toOverview,
    flash('flights'),
  );
}

function pickHotel(city: string, optionId: string): Transition {
  return seq(
    onActive((it) => ({ ...it, hotels: it.hotels.map((h) => (h.city === city ? { ...h, selectedId: optionId } : h)) })),
    toOverview,
    flash('hotels'),
  );
}

function landFlights(tripId: string, legId: string, options: FlightOption[]): Transition {
  return onTrip(tripId, (it) => ({
    ...it,
    legs: it.legs.map((l) => (l.id === legId ? { ...l, options } : l)),
  }));
}

function landHotels(tripId: string, city: string, options: HotelOption[]): Transition {
  return onTrip(tripId, (it) => {
    const has = it.hotels.some((h) => h.city === city);
    const hotels = has
      ? it.hotels.map((h) => (h.city === city ? { ...h, options } : h))
      : [...it.hotels, { city, options }];
    return { ...it, hotels };
  });
}

function shareQuote(to: string, recipient: string): Transition {
  return seq(
    onActive((it) => ({ ...it, whatsapp: { to, recipient, sentAt: now() } })),
    (s) => ({ ...s, whatsappOpen: true }),
  );
}

function taskTarget(task: Task): Transition {
  return seq(
    (s) => (task.itineraryId !== s.activeId ? openTrip(task.itineraryId)(s) : s),
    task.kind === 'flights' && task.target?.legId
      ? toFlights(task.target.legId)
      : task.kind === 'hotels' && task.target?.city
        ? toHotels(task.target.city)
        : seq(toOverview, flash('days')),
  );
}

// ── Provider ────────────────────────────────────────────────────────────────

export function TravelProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>(initialState);
  // The state as of the last transition, ahead of React's commit — what makes
  // back-to-back commands compose.
  const current = useRef(state);
  const agentSendRef = useRef<AgentSend>(null);

  const apply = useCallback((step: Transition) => {
    const next = step(current.current);
    if (next === current.current) return;
    current.current = next;
    setState(next);
  }, []);

  useEffect(() => {
    persist(state.itineraries, state.activeId);
  }, [state.itineraries, state.activeId]);

  // Background-task timers (the search animation), cleared on unmount.
  const timersRef = useRef<number[]>([]);
  useEffect(
    () => () => {
      timersRef.current.forEach((t) => window.clearTimeout(t));
      timersRef.current = [];
    },
    [],
  );

  const registerAgentSend = useCallback((fn: AgentSend) => {
    agentSendRef.current = fn;
  }, []);

  const emit = useCallback((event: AppEvent) => sendAppEvent(agentSendRef.current, event), []);

  const ops = useMemo(() => {
    /**
     * Open a draft, and hand it over. These drafts live in this browser, so until
     * now the brain did not know this trip exists: the overview goes whoever
     * opened it — the brain asking for it by name has no more idea what is in it
     * than the agent's own click does.
     */
    const open = (ref: string | undefined): boolean => {
      const match = findDraft(current.current.itineraries, ref);
      if (!match) return false;
      apply(openTrip(match.id));
      emit({ event: 'trip_opened', payload: overviewOf(match) });
      return true;
    };

    /**
     * A search runs in the background: it animates in the task tray for a few
     * seconds, then lands its options on the itinerary it was started for. Tess
     * gets control back at once — never blocked — and several can run together.
     */
    const runTask = (
      kind: TaskKind,
      label: string,
      detail: string,
      target: Task['target'],
      land: (tripId: string) => Transition,
    ) => {
      const itineraryId = current.current.activeId;
      if (!itineraryId) return; // searches only make sense with a trip open
      const id = newTaskId();
      const task: Task = { id, kind, label, detail, status: 'running', itineraryId, target, startedAt: now() };
      apply((s) => ({ ...s, tasks: [...s.tasks, task] }));
      timersRef.current.push(
        window.setTimeout(() => {
          apply(
            seq(land(itineraryId), (s) => ({
              ...s,
              tasks: s.tasks.map((t) => (t.id === id ? { ...t, status: 'done' } : t)),
            })),
          );
          timersRef.current.push(
            window.setTimeout(() => apply((s) => ({ ...s, tasks: s.tasks.filter((t) => t.id !== id) })), TASK_LINGER),
          );
        }, TASK_LEAD + searchRunMs()),
      );
    };

    const searchFlights = (legId: string, options: FlightOption[]) => {
      const opts = withOptionIds(options, 'f');
      const s = current.current;
      const leg = s.itineraries.find((i) => i.id === s.activeId)?.legs.find((l) => l.id === legId);
      runTask('flights', `Searching flights · ${leg?.label ?? legId}`, `${opts.length} fares`, { legId }, (trip) =>
        landFlights(trip, legId, opts),
      );
      // Open the flights screen so the search is visible (skeleton → option cards).
      apply(toFlights(legId));
    };

    const searchHotels = (city: string, options: HotelOption[]) => {
      const opts = withOptionIds(options, 'h');
      // The city goes on the trip now, so the overview lists it while the search runs.
      apply(onActive((it) => (it.hotels.some((h) => h.city === city) ? it : { ...it, hotels: [...it.hotels, { city }] })));
      runTask('hotels', `Searching hotels · ${city}`, `${opts.length} properties`, { city }, (trip) =>
        landHotels(trip, city, opts),
      );
      apply(toHotels(city));
    };

    return { open, searchFlights, searchHotels };
  }, [apply, emit]);

  // Tess's commands. Each payload is the shape its Python `Action` emits, so
  // there is nothing left to coerce or null-check, and the exhausted `default`
  // arm makes a new action a compile error here until it is handled.
  const handleUiCommand = useCallback(
    (command: string, payload: unknown) => {
      const action = asUiAction(command, payload);
      if (!action) return;
      switch (action.command) {
        case 'open_dashboard':
          apply(toDashboard);
          break;
        case 'open_itinerary': {
          // A draft this browser does not hold is answered, not dropped: the
          // brain has already moved its mirror to an overview the screen never showed.
          const { id, name } = action.payload;
          if (!ops.open(id) && !ops.open(name)) {
            emit({ event: 'itinerary_not_found', payload: { id: id ?? '', name: name ?? '' } });
          }
          break;
        }
        case 'create_itinerary':
          apply(createTrip(action.payload.itinerary));
          break;
        case 'set_trip_structure':
          apply(tripStructure(action.payload));
          break;
        case 'search_flights':
          ops.searchFlights(action.payload.leg_id, action.payload.options);
          break;
        case 'show_flights':
          apply(toFlights(action.payload.leg_id));
          break;
        case 'select_flight':
          apply(pickFlight(action.payload.leg_id, action.payload.option_id));
          break;
        case 'search_hotels':
          ops.searchHotels(action.payload.city, action.payload.options);
          break;
        case 'show_hotels':
          apply(toHotels(action.payload.city));
          break;
        case 'select_hotel':
          apply(pickHotel(action.payload.city, action.payload.option_id));
          break;
        case 'update_trip':
          apply(seq(updateTrip(action.payload), toOverview, flash('summary')));
          break;
        case 'set_family':
          apply(seq(setFamily(action.payload.family), toOverview, flash('summary')));
          break;
        case 'remove_family':
          apply(seq(removeFamily(action.payload.label), toOverview, flash('summary')));
          break;
        case 'set_leg':
          apply(seq(setLeg(action.payload.leg), toOverview, flash('flights')));
          break;
        case 'remove_leg':
          apply(seq(removeLeg(action.payload.leg_id), flash('flights')));
          break;
        case 'set_hotel_stay':
          apply(seq(setHotelStay(action.payload.stay.city, action.payload.stay.nights), toOverview, flash('hotels')));
          break;
        case 'remove_hotel_stay':
          apply(seq(removeHotelStay(action.payload.city), flash('hotels')));
          break;
        case 'set_days':
          apply(seq(setDays(action.payload.days), toOverview, flash('days')));
          break;
        case 'remove_day':
          apply(seq(removeDay(action.payload.day), toOverview, flash('days')));
          break;
        default:
          unhandledUiAction(action);
      }
    },
    [apply, emit, ops],
  );

  // ── The travel agent's own hands ─────────────────────────────────────────
  // Every one of these is a transition plus the sentence that names it. Nothing
  // here is reachable from `handleUiCommand`, which is the whole point: an event
  // is always the agent, so the brain never has to work out whether a change it
  // is being told about is its own command coming home.
  const byHand: ByHand = useMemo(
    () => ({
      openDashboard: () => {
        apply(toDashboard);
        emit({ event: 'dashboard_opened', payload: {} });
      },
      openTrip: (ref) => {
        ops.open(ref);
      },
      newTrip: () => {
        apply(createTrip({ name: BLANK_TRIP_NAME }));
        emit({ event: 'trip_opened', payload: { id: slugify(BLANK_TRIP_NAME), name: BLANK_TRIP_NAME } });
      },
      backToOverview: () => {
        apply(toOverview);
        emit({ event: 'overview_viewed', payload: {} });
      },
      viewFlights: (leg) => {
        apply(toFlights(leg.id));
        emit({ event: 'flights_viewed', payload: { leg_id: leg.id, leg_label: leg.label } });
      },
      viewHotels: (city) => {
        apply(toHotels(city));
        emit({ event: 'hotels_viewed', payload: { city } });
      },
      selectFlight: (leg, opt) => {
        apply(pickFlight(leg.id, opt.id));
        emit({ event: 'flight_selected', payload: { leg_id: leg.id, option_id: opt.id, summary: flightLine(opt) } });
      },
      selectHotel: (stay, opt) => {
        apply(pickHotel(stay.city, opt.id));
        emit({ event: 'hotel_selected', payload: { city: stay.city, option_id: opt.id, summary: hotelLine(opt) } });
      },
      shareQuote: (to, recipient) => {
        apply(shareQuote(to, recipient));
        emit({ event: 'quote_shared', payload: { to, recipient } });
      },
      openTaskTarget: (task) => {
        // A task for another trip opens that trip first, and that is a handover.
        const other = task.itineraryId !== current.current.activeId;
        apply(taskTarget(task));
        if (other) {
          const opened = current.current.itineraries.find((it) => it.id === task.itineraryId);
          if (opened) emit({ event: 'trip_opened', payload: overviewOf(opened) });
        }
        if (task.kind === 'flights' && task.target?.legId) {
          emit({ event: 'flights_viewed', payload: { leg_id: task.target.legId } });
        } else if (task.kind === 'hotels' && task.target?.city) {
          emit({ event: 'hotels_viewed', payload: { city: task.target.city } });
        } else {
          emit({ event: 'overview_viewed', payload: {} });
        }
      },
    }),
    [apply, emit, ops],
  );

  const openWhatsAppPreview = useCallback(() => apply((s) => ({ ...s, whatsappOpen: true })), [apply]);
  const closeWhatsApp = useCallback(() => apply((s) => ({ ...s, whatsappOpen: false })), [apply]);

  const active = useMemo(
    () => state.itineraries.find((it) => it.id === state.activeId) ?? null,
    [state.itineraries, state.activeId],
  );

  const store = useMemo<TravelStore>(
    () => ({
      itineraries: state.itineraries,
      active,
      view: state.view,
      flightsLeg: state.flightsLeg,
      hotelsCity: state.hotelsCity,
      highlighted: state.highlighted,
      whatsappOpen: state.whatsappOpen,
      tasks: state.tasks,
      registerAgentSend,
      byHand,
      handleUiCommand,
      openWhatsAppPreview,
      closeWhatsApp,
    }),
    [state, active, registerAgentSend, byHand, handleUiCommand, openWhatsAppPreview, closeWhatsApp],
  );

  return <Ctx.Provider value={store}>{children}</Ctx.Provider>;
}

export function useTravel(): TravelStore {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useTravel must be used within TravelProvider');
  return ctx;
}
