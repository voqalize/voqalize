/**
 * Wanderloom's inventory, typed: ../../data/inventory.json, the same file the
 * brain reads (written by data/build_inventory.py). Every fare, hotel and
 * activity on the page comes from here; nothing is fetched or invented.
 */
import raw from "../../data/inventory.json";

export type Style = "relaxed" | "adventure" | "honeymoon" | "family";
export type Slot = "morning" | "afternoon" | "evening" | "full_day";
export type Weekday = "Mon" | "Tue" | "Wed" | "Thu" | "Fri" | "Sat" | "Sun";

export interface Room {
  id: string;
  name: string;
  price: number;
}
export interface Hotel {
  id: string;
  name: string;
  stars: number;
  area: string;
  rooms: Room[];
  inclusions: string[];
  tags: string[];
  blurb: string;
}
export interface Activity {
  id: string;
  name: string;
  duration: string;
  slot: Slot;
  price_adult: number;
  price_child: number;
  min_age: number;
  closed: Weekday[];
  tags: string[];
  blurb: string;
}
export interface City {
  id: string;
  name: string;
  blurb: string;
  inland?: boolean;
  hotels: Hotel[];
  activities: Activity[];
}
export interface ByHotel {
  adult: number;
  child: number;
  mode: string;
}
export interface Transfer {
  id: string;
  from: string;
  to: string;
  mode: string;
  duration: string;
  pricing: "per_vehicle" | "per_person";
  prices: Record<string, number>;
  by_hotel?: Record<string, ByHotel>;
}
export interface Destination {
  id: string;
  name: string;
  country: string;
  domestic: boolean;
  tagline: string;
  best_months: number[];
  arrive: string;
  depart: string;
  nights: [number, number];
  default_nights: number;
  hue: string;
  splits: Record<string, number[]>;
  cities: City[];
  transfers: Transfer[];
}
export interface Leg {
  from: string;
  to: string;
  depart: string;
  depart_day: number;
  arrive: string;
  arrive_day: number;
  minutes: number;
  airline: string;
  number: string;
}
export interface Journey {
  legs: Leg[];
  minutes: number;
  stops: number;
  arrive_day: number;
}
export interface Flight {
  id: string;
  origin: string;
  destination: string;
  airline: string;
  airline_name: string;
  kind: string;
  baggage: string;
  meal: string;
  out: Journey;
  back: Journey;
  stops: number;
  fare_adult: number;
}
export interface Rules {
  child_max_age: number;
  infant_max_age: number;
  child_fare_pct: number;
  infant_fare: number;
  adults_per_room: number;
  gst_pct: number;
  season: Record<string, number>;
  vehicles: [string, number][];
  min_days_ahead: number;
  max_travellers: number;
}
export interface Inventory {
  brand: string;
  rules: Rules;
  styles: { id: Style; label: string }[];
  origins: { id: string; city: string }[];
  airports: Record<string, { city: string; offset: number }>;
  airlines: Record<string, { name: string; kind: string }>;
  destinations: Destination[];
  flights: Flight[];
}

export const INV = raw as unknown as Inventory;
export const RULES = INV.rules;
export const STYLES = INV.styles;
export const ORIGINS = INV.origins;
export const DESTINATIONS = INV.destinations;

const byDest = new Map(DESTINATIONS.map((d) => [d.id, d]));
const byFlight = new Map(INV.flights.map((f) => [f.id, f]));
const byCity = new Map(DESTINATIONS.flatMap((d) => d.cities.map((c) => [c.id, c] as const)));
const byActivity = new Map(DESTINATIONS.flatMap((d) => d.cities.flatMap((c) => c.activities.map((a) => [a.id, { activity: a, city: c }] as const))));

export const getDestination = (id: string | null | undefined) => (id ? byDest.get(id) : undefined);
export const getFlight = (id: string | null | undefined) => (id ? byFlight.get(id) : undefined);
export const getCity = (id: string | null | undefined) => (id ? byCity.get(id) : undefined);
export const getActivity = (id: string | null | undefined) => (id ? byActivity.get(id)?.activity : undefined);
export const cityOfActivity = (id: string) => byActivity.get(id)?.city;
export const getHotel = (cityId: string, hotelId: string) => getCity(cityId)?.hotels.find((h) => h.id === hotelId);
export const originName = (code: string | null | undefined) => ORIGINS.find((o) => o.id === code)?.city ?? code ?? "";
export const airportCity = (code: string) => INV.airports[code]?.city ?? code;

export function flightsFor(origin: string | null | undefined, destination: string | null | undefined): Flight[] {
  if (!origin || !destination) return [];
  return INV.flights.filter((f) => f.origin === origin && f.destination === destination);
}
