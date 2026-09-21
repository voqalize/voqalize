// Generated from travel/backend/brain_gemini.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types travel/backend/brain_gemini.py -o travel/frontend/src/actions.gen.ts
//
// Every field of an action is present on the wire, `null` included, so nothing
// there is optional and no runtime validation is needed to narrow on `command`.

/** Show the dashboard of saved draft trips. No arguments. */
export type OpenDashboard = Record<string, never>;

/**
 * Open one saved draft. The model puts the name or id it heard in `id`; the
 * brain resolves that against the catalog and dispatches the draft's own id, with
 * its own name in `name`, which is all a page that predates ids matches on.
 */
export interface OpenItinerary {
  /** The draft's name or id, as the agent said it. */
  id: string;

  /** Leave empty — the desk fills in the draft's name. */
  name: string;
}

export interface CreateItinerary {
  itinerary: Itinerary;
}

export interface SetTripStructure {
  families: Family[];

  legs: Leg[];

  hotel_cities: CityNights[];
}

export interface SearchFlights {
  leg_id: string;

  options: FlightOption[];
}

export interface ShowFlights {
  leg_id: string;
}

export interface SelectFlight {
  leg_id: string;

  option_id: string;
}

export interface SearchHotels {
  city: string;

  options: HotelOption[];
}

export interface ShowHotels {
  city: string;
}

export interface SelectHotel {
  city: string;

  option_id: string;
}

/** Change the open trip's headline fields. A field left null stays as it is. */
export interface UpdateTrip {
  name: string | null;

  coordinator: string | null;

  destination: string | null;

  start_date: string | null;

  end_date: string | null;

  summary: string | null;
}

/** Add one travelling family, or replace the one with the same label. */
export interface SetFamily {
  family: Family;
}

/** Take one travelling family off the trip, by its label. */
export interface RemoveFamily {
  label: string;
}

/**
 * Add one flight leg, or change the one with this id. An empty field keeps
 * the value the leg already has; a new route or date clears the leg's fares and
 * its pick, which were for a different flight.
 */
export interface SetLeg {
  leg: Leg;
}

/** Take one flight leg off the trip, fares and pick with it. */
export interface RemoveLeg {
  leg_id: string;
}

/**
 * Add one hotel city, or change its nights. The searched hotels and the pick
 * stay: a longer stay is the same hotel.
 */
export interface SetHotelStay {
  stay: CityNights;
}

/** Take one hotel city off the trip, hotels and pick with it. */
export interface RemoveHotelStay {
  city: string;
}

/**
 * The agent closed the trip and went back to the list of drafts. Nothing is
 * open, so nothing on screen has an id worth holding.
 */
export type DashboardOpened = Record<string, never>;

/**
 * The agent picked a flight themselves, off the option cards. `summary` is
 * what the overview will now show for the leg, so the mirror needs no lookup.
 */
export interface FlightSelected {
  leg_id: string;

  option_id: string;

  summary?: string;
}

/** The agent opened one leg's flight options. */
export interface FlightsViewed {
  leg_id: string;

  leg_label?: string;
}

/** The agent picked a hotel themselves, off the option cards. */
export interface HotelSelected {
  city: string;

  option_id: string;

  summary?: string;
}

/** The agent opened one city's hotel options. */
export interface HotelsViewed {
  city: string;
}

/**
 * An `open_itinerary` named a draft this browser does not hold, by id or by
 * name, so the screen did not move.
 *
 * Nobody's gesture — the page's answer to a command, and the only place it
 * exists: the drafts live in this browser, and a command the page cannot resolve
 * otherwise leaves the brain's mirror on an overview the screen never showed.
 */
export interface ItineraryNotFound {
  id?: string;

  name?: string;
}

/**
 * The agent came back to the itinerary overview from a flights or hotels
 * screen.
 */
export type OverviewViewed = Record<string, never>;

/** The agent sent the quote on WhatsApp from the share sheet. */
export interface QuoteShared {
  to?: string;

  recipient?: string;
}

/**
 * The agent opened a saved draft, or started a blank one.
 *
 * The drafts live in the browser, so this is the brain's first sight of the
 * trip: it carries the itinerary as the overview shows it, and the mirror is
 * built from it. Every later change is a patch.
 */
export interface TripOpened {
  /** The draft's id — what open_itinerary names it by. Empty from an older page. */
  id?: string;

  name: string;

  coordinator?: string;

  destination?: string;

  dates?: string;

  pax?: string;

  families?: string[];

  special_requests?: string[];

  legs?: LegLine[];

  hotels?: StayLine[];

  days?: string[];

  inclusions?: string[];

  exclusions?: string[];

  terms_set?: boolean;

  whatsapp_sent?: boolean;
}

// ── Shapes used by the messages above ──────────────────────────────

/** One hotel city and how many nights the group stays there. */
export interface CityNights {
  city: string;

  nights: number;
}

/** One travelling family on the itinerary. */
export interface Family {
  label: string;

  origin: string;

  adults: number;

  children: number;

  infants: number;

  meal: 'veg' | 'nonveg' | 'mixed';

  assistance: string;
}

/** One invented flight option for a leg. */
export interface FlightOption {
  id: string;

  airline: string;

  flight_no: string;

  depart: string;

  arrive: string;

  duration: string;

  stops: string;

  cabin: string;

  baggage: string;

  price: number;

  note: string;
}

/** One invented hotel option for a city. */
export interface HotelOption {
  id: string;

  name: string;

  area: string;

  stars: number;

  board: string;

  room_type: string;

  rating: number;

  amenities: string[];

  price_per_night: number;

  note: string;
}

/** The itinerary shell `create_itinerary` puts on screen. */
export interface Itinerary {
  /** Leave empty — the desk assigns it. */
  id: string;

  name: string;

  coordinator: string;

  destination: string;

  start_date: string;

  end_date: string;

  summary: string;

  families: Family[];

  legs: Leg[];

  hotel_cities: CityNights[];
}

/** One flight leg of the trip. */
export interface Leg {
  id: string;

  label: string;

  from: string;

  to: string;

  date: string;
}

/** One flight leg as the overview lists it — the pick, never the options. */
export interface LegLine {
  id: string;

  label?: string;

  from?: string;

  to?: string;

  date?: string;

  options_shown?: number;

  selected?: string;
}

/** One hotel city as the overview lists it. */
export interface StayLine {
  city: string;

  nights?: number;

  options_shown?: number;

  selected?: string;
}

/** Everything the brain can put on screen, discriminated by `command`. */
export type UiAction =
  | { command: 'open_dashboard'; payload: OpenDashboard }
  | { command: 'open_itinerary'; payload: OpenItinerary }
  | { command: 'create_itinerary'; payload: CreateItinerary }
  | { command: 'set_trip_structure'; payload: SetTripStructure }
  | { command: 'search_flights'; payload: SearchFlights }
  | { command: 'show_flights'; payload: ShowFlights }
  | { command: 'select_flight'; payload: SelectFlight }
  | { command: 'search_hotels'; payload: SearchHotels }
  | { command: 'show_hotels'; payload: ShowHotels }
  | { command: 'select_hotel'; payload: SelectHotel }
  | { command: 'update_trip'; payload: UpdateTrip }
  | { command: 'set_family'; payload: SetFamily }
  | { command: 'remove_family'; payload: RemoveFamily }
  | { command: 'set_leg'; payload: SetLeg }
  | { command: 'remove_leg'; payload: RemoveLeg }
  | { command: 'set_hotel_stay'; payload: SetHotelStay }
  | { command: 'remove_hotel_stay'; payload: RemoveHotelStay };

export type UiActionCommand = UiAction['command'];

export const UI_ACTION_COMMANDS: readonly UiActionCommand[] = [
  'open_dashboard',
  'open_itinerary',
  'create_itinerary',
  'set_trip_structure',
  'search_flights',
  'show_flights',
  'select_flight',
  'search_hotels',
  'show_hotels',
  'select_hotel',
  'update_trip',
  'set_family',
  'remove_family',
  'set_leg',
  'remove_leg',
  'set_hotel_stay',
  'remove_hotel_stay',
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
  | { event: 'dashboard_opened'; payload: DashboardOpened }
  | { event: 'flight_selected'; payload: FlightSelected }
  | { event: 'flights_viewed'; payload: FlightsViewed }
  | { event: 'hotel_selected'; payload: HotelSelected }
  | { event: 'hotels_viewed'; payload: HotelsViewed }
  | { event: 'itinerary_not_found'; payload: ItineraryNotFound }
  | { event: 'overview_viewed'; payload: OverviewViewed }
  | { event: 'quote_shared'; payload: QuoteShared }
  | { event: 'trip_opened'; payload: TripOpened };

export type AppEventName = AppEvent['event'];

export const APP_EVENT_NAMES: readonly AppEventName[] = [
  'dashboard_opened',
  'flight_selected',
  'flights_viewed',
  'hotel_selected',
  'hotels_viewed',
  'itinerary_not_found',
  'overview_viewed',
  'quote_shared',
  'trip_opened',
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
