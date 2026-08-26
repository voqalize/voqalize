// Generated from travel/backend/brain_gemini.py by `voqalize types`. Do not edit — regenerate with:
//   voqalize types travel/backend/brain_gemini.py -o travel/frontend/src/actions.gen.ts
//
// Every field is present on the wire, `null` included, so nothing here is
// optional and no runtime validation is needed to narrow on `command`.

/** Show the dashboard of saved draft trips. No arguments. */
export type OpenDashboard = Record<string, never>;

export interface OpenItinerary {
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

// ── Shapes used by the actions above ───────────────────────────────

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
  | { command: 'select_hotel'; payload: SelectHotel };

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
