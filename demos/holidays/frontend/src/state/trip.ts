/**
 * The trip on screen, and the ONE controller that changes it.
 *
 * Every change — a click, a typed field, or one of the planner's Stage moves —
 * goes through a function here. Each one applies CONTRACT.md's cascade
 * (a new destination resets the plan, new nights reset the split, and so on),
 * drops activities that no longer fit, and reports itself as the `trip` slice's
 * event (`trip.flight_picked`, …) so the brain hears what changed, by id.
 * Whether the visitor or the agent made it is decided where the event is sent
 * (`stage/host.ts`), from Stage's own window around a running move.
 *
 * The trip is kept in localStorage, so a refresh or a later call starts from it.
 */
import { create } from "zustand";
import { type Style, getActivity, getCity, getDestination, getFlight, getHotel, originName } from "../data";
import {
  type Brief,
  type PlannedActivity,
  type Trip,
  cannotPlace,
  defaultSplit,
  emptyTrip,
  price,
  recommend,
  stays,
  validSplit,
} from "../engine";
import { date as fmtDate, money } from "../format";

export type Step = "brief" | "flights" | "hotels" | "days" | "package";
export const STEPS: { id: Step; label: string }[] = [
  { id: "brief", label: "Trip" },
  { id: "flights", label: "Flights" },
  { id: "hotels", label: "Hotels" },
  { id: "days", label: "Days" },
  { id: "package", label: "Package" },
];
export type FlightSort = "recommended" | "price" | "duration" | "departure";

export interface Booking {
  reference: string;
  total: number;
  lead: string;
  email: string;
  trip: Trip;
  paid_at: string;
}

interface State {
  trip: Trip;
  step: Step;
  flightSort: FlightSort;
  hotelCity: string | null;
  hotelWant: string | null;
  booking: Booking | null;
}

const KEY = "wanderloom-trip-v1";
function load(): Partial<State> {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) ?? "null") as Partial<State> | null;
    if (s && s.trip && s.trip.brief) return { trip: s.trip, step: s.step ?? "brief", booking: s.booking ?? null };
  } catch {
    /* storage unavailable: start empty */
  }
  return {};
}

export const useTrip = create<State>(() => ({
  trip: emptyTrip(),
  step: "brief",
  flightSort: "recommended",
  hotelCity: null,
  hotelWant: null,
  booking: null,
  ...load(),
}));

useTrip.subscribe((s) => {
  try {
    localStorage.setItem(KEY, JSON.stringify({ trip: s.trip, step: s.step, booking: s.booking }));
  } catch {
    /* storage unavailable: the trip lives for this page only */
  }
});

// ─── Reporting each change to the brain ──────────────────────────────────────

export type TripEvent =
  | ["trip.brief_changed", { field: string; value: string; label: string }]
  | ["trip.flight_picked", { flight_id: string; label: string }]
  | ["trip.hotel_picked", { city: string; hotel_id: string; room_id: string; label: string }]
  | ["trip.nights_changed", { split: number[]; label: string }]
  | ["trip.activity_added", { activity_id: string; day: number; label: string }]
  | ["trip.activity_removed", { activity_id: string; day: number; label: string }]
  | ["trip.step_changed", { step: string }]
  | ["trip.page_changed", { page: string }]
  | ["trip.paid", { reference: string; total: number }];

type Reporter = (event: TripEvent) => void;
let reporter: Reporter | null = null;
/** The Stage host sets this while a call is live. */
export const setReporter = (r: Reporter | null) => {
  reporter = r;
};
const report = (e: TripEvent) => reporter?.(e);

// ─── The controller ──────────────────────────────────────────────────────────

const get = () => useTrip.getState();
const setTrip = (trip: Trip) => useTrip.setState({ trip });

/** Activities that no longer fit (a day gone, a new city, a child too young, a closed weekday) leave. */
function prune(t: Trip): Trip {
  const kept: PlannedActivity[] = [];
  const work: Trip = { ...t, activities: kept };
  for (const p of t.activities) {
    if (cannotPlace(work, p.activity_id, p.day) === null) kept.push(p);
  }
  const cities = new Set(stays(t).map((s) => s.city.id));
  const hotels = Object.fromEntries(Object.entries(t.hotels).filter(([c]) => cities.has(c)));
  return { ...t, activities: kept, hotels };
}

const BRIEF_LABEL: Record<keyof Brief, string> = {
  from_city: "flying from",
  destination: "destination",
  start_date: "departure date",
  nights: "nights",
  adults: "adults",
  kids: "children",
  budget: "budget",
  style: "style",
};

function shown(field: keyof Brief, b: Brief): string {
  switch (field) {
    case "from_city":
      return originName(b.from_city);
    case "destination":
      return getDestination(b.destination)?.name ?? "";
    case "start_date":
      return fmtDate(b.start_date);
    case "kids":
      return b.kids.length ? `${b.kids.length} (ages ${b.kids.join(", ")})` : "none";
    case "budget":
      return b.budget ? money(b.budget) : "no limit";
    default:
      return String(b[field] ?? "");
  }
}

/** Set some fields of the brief, with CONTRACT's cascade. Returns the fields that changed. */
export function setBrief(changes: Partial<Brief>): (keyof Brief)[] {
  const t = get().trip;
  let next: Trip = { ...t, brief: { ...t.brief } };
  const changed: (keyof Brief)[] = [];
  for (const [k, v] of Object.entries(changes) as [keyof Brief, unknown][]) {
    if (v === undefined) continue;
    if (JSON.stringify(next.brief[k]) === JSON.stringify(v)) continue;
    (next.brief as unknown as Record<string, unknown>)[k] = v;
    changed.push(k);
  }
  if (!changed.length) return [];
  const d = getDestination(next.brief.destination);
  if (changed.includes("destination")) {
    next = { ...next, split: null, flight_id: null, hotels: {}, activities: [] };
    if (d && (!next.brief.nights || next.brief.nights < d.nights[0] || next.brief.nights > d.nights[1])) {
      next.brief.nights = d.default_nights;
      if (!changed.includes("nights")) changed.push("nights");
    }
  }
  if (changed.includes("from_city")) next.flight_id = null;
  if (changed.includes("nights")) next.split = null;
  next = prune(next);
  setTrip(next);
  for (const f of changed) report(["trip.brief_changed", { field: f, value: f === "kids" ? next.brief.kids.join(",") : String(next.brief[f] ?? ""), label: `${BRIEF_LABEL[f]}: ${shown(f, next.brief)}` }]);
  return changed;
}

export function setStyle(style: Style | null) {
  return setBrief({ style });
}

export function pickFlight(id: string): string | null {
  const f = getFlight(id);
  const b = get().trip.brief;
  if (!f) return "there is no such flight";
  if (f.origin !== b.from_city || f.destination !== b.destination) return "that flight is not for this trip's cities";
  if (get().trip.flight_id === id) return null;
  setTrip(prune({ ...get().trip, flight_id: id }));
  report(["trip.flight_picked", { flight_id: id, label: `${f.airline_name} ${f.out.legs[0].number}, ${f.stops ? `${f.stops} stop` : "nonstop"}` }]);
  return null;
}

export function pickHotel(city: string, hotelId: string, roomId: string): string | null {
  const t = get().trip;
  const h = getHotel(city, hotelId);
  if (!stays(t).some((s) => s.city.id === city)) return `${getCity(city)?.name ?? city} has no nights in this trip`;
  if (!h) return "there is no such hotel in that city";
  const room = h.rooms.find((r) => r.id === roomId);
  if (!room) return `${h.name} has ${h.rooms.map((r) => r.name).join(", ")}`;
  const cur = t.hotels[city];
  if (cur && cur.hotel_id === hotelId && cur.room_id === roomId) return null;
  setTrip(prune({ ...t, hotels: { ...t.hotels, [city]: { hotel_id: hotelId, room_id: roomId } } }));
  report(["trip.hotel_picked", { city, hotel_id: hotelId, room_id: roomId, label: `${h.name}, ${room.name}, in ${getCity(city)?.name}` }]);
  return null;
}

export function setSplit(split: number[]): string | null {
  const t = get().trip;
  if (!validSplit(t, split)) return "that split of nights is not one this trip can take";
  const d = getDestination(t.brief.destination)!;
  setTrip(prune({ ...t, split }));
  report(["trip.nights_changed", { split, label: d.cities.map((c, i) => `${c.name} ${split[i]}`).join(", ") }]);
  return null;
}

export function addActivity(activityId: string, day: number): string | null {
  const t = get().trip;
  const why = cannotPlace(t, activityId, day);
  if (why) return why;
  setTrip({ ...t, activities: [...t.activities, { day, activity_id: activityId }].sort((a, b) => a.day - b.day) });
  report(["trip.activity_added", { activity_id: activityId, day, label: `${getActivity(activityId)!.name} on day ${day}` }]);
  return null;
}

export function removeActivity(activityId: string, day: number): string | null {
  const t = get().trip;
  if (!t.activities.some((p) => p.activity_id === activityId && p.day === day)) return `that activity is not on day ${day}`;
  setTrip({ ...t, activities: t.activities.filter((p) => !(p.activity_id === activityId && p.day === day)) });
  report(["trip.activity_removed", { activity_id: activityId, day, label: `${getActivity(activityId)?.name} from day ${day}` }]);
  return null;
}

/** "Build it for me": the recommended flight, hotels and activities, each reported. */
export function buildPackage() {
  const t = get().trip;
  const rec = recommend(t);
  if (rec.flight_id) pickFlight(rec.flight_id);
  for (const [city, h] of Object.entries(rec.hotels)) pickHotel(city, h.hotel_id, h.room_id);
  for (const p of get().trip.activities) removeActivity(p.activity_id, p.day);
  for (const p of rec.activities) addActivity(p.activity_id, p.day);
}

export function setStep(step: Step) {
  if (get().step === step) return;
  useTrip.setState({ step });
  report(["trip.step_changed", { step }]);
}
export const setFlightSort = (flightSort: FlightSort) => useTrip.setState({ flightSort });
export const setHotelCity = (hotelCity: string | null) => useTrip.setState({ hotelCity });
export const setHotelWant = (hotelWant: string | null) => useTrip.setState({ hotelWant });

export function pageViewed(page: string) {
  report(["trip.page_changed", { page }]);
}

export function startOver() {
  useTrip.setState({ trip: emptyTrip(), step: "brief", hotelCity: null, hotelWant: null });
}

/** Pressed by the visitor on the checkout page only. A mock payment. */
export function pay(lead: string, email: string): Booking {
  const t = get().trip;
  const reference = `WL-${String(Math.floor(100000 + Math.random() * 900000))}`;
  const booking: Booking = { reference, total: price(t).total, lead, email, trip: t, paid_at: new Date().toISOString() };
  useTrip.setState({ booking });
  report(["trip.paid", { reference, total: booking.total }]);
  return booking;
}

/** The trip as the connect request's `init.trip` carries it (CONTRACT, Pages). */
export function tripForInit(): Record<string, unknown> | undefined {
  const t = get().trip;
  if (!t.brief.destination && !t.brief.from_city) return undefined;
  return { ...t.brief, split: t.split ?? (getDestination(t.brief.destination) && t.brief.nights ? defaultSplit(getDestination(t.brief.destination)!, t.brief.nights) : null), flight_id: t.flight_id, hotels: t.hotels, activities: t.activities };
}
