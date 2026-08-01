/**
 * The Travel Desk screen contract — the browser half.
 *
 * **`demos/travel/backend/brain.py` is the source of truth.** Every interface here
 * mirrors one `voqalize.sdk.Action` subclass declared there, field for field, and
 * the key it is filed under is that action's wire name (derived from the Python
 * class name: `SearchFlights` → `search_flights`). Change one side and the other
 * must move with it; `demos/tests/test_travel_adk.py` asserts the exact envelopes
 * these describe, so a drift fails a test rather than a demo.
 *
 * These are **wire** shapes, deliberately separate from the domain types in
 * `types.ts`. They are what the brain sends — every field always present, because
 * a pydantic `Action` emits its whole declared shape (no `exclude_none`). The
 * store's own model then adds what only the browser knows: a slug id, timestamps,
 * which option is selected, the day plan.
 *
 * The `useUiCommand` hook (`@voqalize/client-react`) checks a handler map against
 * `TravelCommands` below: an unknown action name is a compile error, and each
 * handler's argument is typed — which is what removed the old `switch` with its
 * `str(cmd.leg_id)!` coercions.
 */

/** `Family` — one travelling family. */
export interface WireFamily {
  label: string;
  origin: string;
  adults: number;
  children: number;
  infants: number;
  meal: 'veg' | 'nonveg' | 'mixed';
  assistance: string;
}

/** `Leg` — one flight leg. `from` is the alias of the brain's `from_` field. */
export interface WireLeg {
  id: string;
  label: string;
  from: string;
  to: string;
  date: string;
}

/** `CityNights` — one hotel city and its night count. */
export interface WireCityNights {
  city: string;
  nights: number;
}

/** `FlightOption` — one invented flight, id assigned by the brain. */
export interface WireFlightOption {
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

/** `HotelOption` — one invented property, id assigned by the brain. */
export interface WireHotelOption {
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

/** `Itinerary` — the shell `create_itinerary` opens. */
export interface WireItinerary {
  name: string;
  coordinator: string;
  destination: string;
  start_date: string;
  end_date: string;
  summary: string;
  families: WireFamily[];
  legs: WireLeg[];
  hotel_cities: WireCityNights[];
}

/**
 * Wire name → argument shape, for every `ui_command` the Travel Desk brain fires.
 * The ten keys are the ten `Action` subclasses in `brain.py`.
 */
export interface TravelCommands {
  /** Show the dashboard of saved drafts. */
  open_dashboard: Record<string, never>;
  /** Open a saved itinerary by name (the store also matches on slug). */
  open_itinerary: { name: string };
  /** Create the itinerary shell and open its overview. */
  create_itinerary: { itinerary: WireItinerary };
  /** Fill the active itinerary's travellers, legs and hotel cities. */
  set_trip_structure: {
    families: WireFamily[];
    legs: WireLeg[];
    hotel_cities: WireCityNights[];
  };
  /** Kick off the flight search for a leg and reveal the options when it lands. */
  search_flights: { leg_id: string; options: WireFlightOption[] };
  /** Bring an already-searched leg back on screen. */
  show_flights: { leg_id: string };
  /** Pin one option to a leg. */
  select_flight: { leg_id: string; option_id: string };
  /** Kick off the hotel search for a city. */
  search_hotels: { city: string; options: WireHotelOption[] };
  /** Bring an already-searched city back on screen. */
  show_hotels: { city: string };
  /** Pin one property to a city. */
  select_hotel: { city: string; option_id: string };
}
