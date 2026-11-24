/**
 * The trip engine: the rules in CONTRACT.md ("The engine"), written once for
 * the page. `backend/engine.py` is the brain's copy; `engine.test.ts` runs
 * every case in data/engine_cases.json (written by the brain's engine) through
 * this file, so the two cannot quote different prices.
 *
 * Pure functions over the inventory: no store, no DOM.
 */
import {
  type Activity,
  cityOfActivity,
  type City,
  type Destination,
  type Flight,
  type Hotel,
  RULES,
  type Slot,
  type Style,
  type Transfer,
  type Weekday,
  flightsFor,
  getActivity,
  getDestination,
  getFlight,
} from "./data";

export interface Brief {
  from_city: string | null;
  destination: string | null;
  start_date: string | null;
  nights: number | null;
  adults: number;
  kids: number[];
  budget: number;
  style: Style | null;
}

export interface HotelPick {
  hotel_id: string;
  room_id: string;
}
export interface PlannedActivity {
  day: number;
  activity_id: string;
}
export interface Trip {
  brief: Brief;
  split: number[] | null;
  flight_id: string | null;
  hotels: Record<string, HotelPick>;
  activities: PlannedActivity[];
}

export const emptyBrief = (): Brief => ({
  from_city: null,
  destination: null,
  start_date: null,
  nights: null,
  adults: 2,
  kids: [],
  budget: 0,
  style: null,
});
export const emptyTrip = (): Trip => ({ brief: emptyBrief(), split: null, flight_id: null, hotels: {}, activities: [] });

// ─── Numbers ─────────────────────────────────────────────────────────────────

/** Round half away from zero, as the brain's engine does (never banker's). */
export const roundHalfUp = (x: number) => Math.floor(x + 0.5);
export const roundTo10 = (x: number) => Math.floor(x / 10 + 0.5) * 10;

export const pax = (b: Brief) => b.adults + b.kids.length;
export const infants = (b: Brief) => b.kids.filter((a) => a <= RULES.infant_max_age).length;
export const children = (b: Brief) => b.kids.length - infants(b);

// ─── Dates (calendar dates as YYYY-MM-DD, done in UTC so no clock shifts them) ─

const WEEKDAYS: Weekday[] = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const parse = (iso: string) => new Date(`${iso}T00:00:00Z`);
const iso = (d: Date) => d.toISOString().slice(0, 10);
export const addDays = (date: string, n: number) => {
  const d = parse(date);
  d.setUTCDate(d.getUTCDate() + n);
  return iso(d);
};
export const weekday = (date: string): Weekday => WEEKDAYS[parse(date).getUTCDay()];
export const todayIso = () => {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
};

/** The first Friday on or after the 10th of `month` (1–12), in its next
 *  occurrence at least `min_days_ahead` days after `today`. */
export function defaultStartForMonth(month: number, today: string = todayIso()): string {
  const earliest = addDays(today, RULES.min_days_ahead);
  let year = Number(today.slice(0, 4));
  for (let i = 0; i < 3; i++, year++) {
    let d = `${year}-${String(month).padStart(2, "0")}-10`;
    while (weekday(d) !== "Fri") d = addDays(d, 1);
    if (d >= earliest) return d;
  }
  throw new Error("no date");
}

export const seasonPct = (start: string | null) => (start ? (RULES.season[String(Number(start.slice(5, 7)))] ?? 100) : 100);

// ─── Flights ─────────────────────────────────────────────────────────────────

export interface FlightPrice {
  adult: number;
  child: number;
  infant: number;
  total: number;
}
export function flightPrice(f: Flight, b: Brief): FlightPrice {
  const adult = roundTo10((f.fare_adult * seasonPct(b.start_date)) / 100);
  const child = roundTo10((adult * RULES.child_fare_pct) / 100);
  const infant = RULES.infant_fare;
  return { adult, child, infant, total: adult * b.adults + child * children(b) + infant * infants(b) };
}

export function recommendedFlight(b: Brief): Flight | undefined {
  const all = flightsFor(b.from_city, b.destination);
  const cheapest = (fs: Flight[]) => fs.reduce<Flight | undefined>((best, f) => (!best || f.fare_adult < best.fare_adult ? f : best), undefined);
  return cheapest(all.filter((f) => f.stops === 0)) ?? cheapest(all);
}

// ─── Nights and days ─────────────────────────────────────────────────────────

export function defaultSplit(d: Destination, nights: number): number[] | null {
  return d.splits[String(nights)] ?? null;
}
export const splitOf = (t: Trip): number[] | null => {
  const d = getDestination(t.brief.destination);
  if (!d || !t.brief.nights) return null;
  return t.split ?? defaultSplit(d, t.brief.nights);
};
/** The cities with nights, in route order, with their nights. */
export function stays(t: Trip): { city: City; nights: number }[] {
  const d = getDestination(t.brief.destination);
  const split = splitOf(t);
  if (!d || !split) return [];
  return d.cities.map((city, i) => ({ city, nights: split[i] ?? 0 })).filter((s) => s.nights > 0);
}

export type DayKind = "arrival" | "transfer" | "full" | "departure";
export interface Day {
  day: number;
  date: string | null;
  weekday: Weekday | null;
  city: City;
  kind: DayKind;
  slots: Slot2[];
}
type Slot2 = "morning" | "afternoon" | "evening";

export function day1(t: Trip): string | null {
  if (!t.brief.start_date) return null;
  const f = getFlight(t.flight_id);
  return addDays(t.brief.start_date, f ? f.out.arrive_day : 0);
}

export function days(t: Trip): Day[] {
  const s = stays(t);
  if (!s.length || !t.brief.nights) return [];
  const first = day1(t);
  const out: Day[] = [];
  let n = 1;
  s.forEach((stay, i) => {
    for (let k = 0; k < stay.nights; k++, n++) {
      const kind: DayKind = n === 1 ? "arrival" : k === 0 && i > 0 ? "transfer" : "full";
      out.push(mkDay(n, first, stay.city, kind));
    }
  });
  out.push(mkDay(n, first, s[s.length - 1].city, "departure"));
  return out;
}
function mkDay(day: number, first: string | null, city: City, kind: DayKind): Day {
  const date = first ? addDays(first, day - 1) : null;
  const slots: Slot2[] = kind === "full" ? ["morning", "afternoon", "evening"] : kind === "departure" ? [] : ["evening"];
  return { day, date, weekday: date ? weekday(date) : null, city, kind, slots };
}

const takes = (a: Activity): Slot2[] => (a.slot === "full_day" ? ["morning", "afternoon"] : [a.slot]);

const LONG_DAY: Record<Weekday, string> = { Mon: "Mondays", Tue: "Tuesdays", Wed: "Wednesdays", Thu: "Thursdays", Fri: "Fridays", Sat: "Saturdays", Sun: "Sundays" };

/** Why `activity` cannot go on `day` of the trip, or null when it can (the
 *  brain's `engine.can_add`, same order, same words). `ignore` is a planned
 *  activity to leave out (when moving one). */
export function cannotPlace(t: Trip, activityId: string, dayNo: number, ignore?: PlannedActivity): string | null {
  const a = getActivity(activityId);
  if (!a) return "there is no such activity";
  const all = days(t);
  const day = all.find((d) => d.day === dayNo);
  if (!day) return all.length ? `the trip has days 1 to ${all.length}` : "the trip has no days yet";
  const home = cityOfActivity(a.id);
  if (day.city.id !== home?.id) return `day ${dayNo} is in ${day.city.name}, and ${a.name} is in ${home?.name ?? "another city"}`;
  if (day.kind === "departure") return `day ${dayNo} is the day you fly home`;
  const need = takes(a);
  if (need.some((s) => !day.slots.includes(s))) {
    if (day.kind === "arrival" || day.kind === "transfer") return `day ${dayNo} is a travel day, with only the evening free`;
    return `${a.name} does not fit day ${dayNo}`;
  }
  const taken = new Set<Slot2>(
    t.activities
      .filter((p) => p.day === dayNo && !(ignore && p.day === ignore.day && p.activity_id === ignore.activity_id))
      .flatMap((p) => {
        const x = getActivity(p.activity_id);
        return x ? takes(x) : [];
      }),
  );
  const clash = [...new Set(need.filter((s) => taken.has(s)))].sort();
  if (clash.length) return `the ${clash.join(", ")} of day ${dayNo} is already taken`;
  if (t.brief.kids.some((k) => k < a.min_age)) return `${a.name} is for ages ${a.min_age} and up`;
  if (a.min_age >= 18 && t.brief.kids.length) return `${a.name} is for adults only`;
  if (day.weekday && a.closed.includes(day.weekday)) return `${a.name} does not run on ${LONG_DAY[day.weekday]}`;
  if (t.activities.some((p) => p.day === dayNo && p.activity_id === activityId)) return `${a.name} is already on day ${dayNo}`;
  return null;
}

/** A split the inventory can serve (the brain's `engine.valid_split`). */
export function validSplit(t: Trip, split: number[]): boolean {
  const d = getDestination(t.brief.destination);
  if (!d || !t.brief.nights || split.length !== d.cities.length) return false;
  if (split.some((n) => n < 0) || split.reduce((x, y) => x + y, 0) !== t.brief.nights) return false;
  const ids = d.cities.filter((_, i) => split[i] > 0).map((c) => c.id);
  const legs = new Set(d.transfers.map((x) => `${x.from}>${x.to}`));
  if (ids.slice(1).some((b, i) => !legs.has(`${ids[i]}>${b}`))) return false;
  const arrive = d.transfers.find((x) => x.id.endsWith("-arrive"));
  return !!arrive && (arrive.to === "first" || arrive.to === ids[0]);
}

/** The style picks are made for: the brief's, else family with children, else relaxed. */
export const styleOf = (b: Brief): Style => b.style ?? (b.kids.length ? "family" : "relaxed");

// ─── Prices ──────────────────────────────────────────────────────────────────

export const rooms = (b: Brief) => Math.ceil(b.adults / RULES.adults_per_room);
export const vehicleFor = (n: number) => RULES.vehicles.find(([, cap]) => cap >= n)?.[0] ?? RULES.vehicles[RULES.vehicles.length - 1][0];

export interface TransferLine {
  id: string;
  label: string;
  mode: string;
  duration: string;
  price: number;
}
export function transfers(t: Trip): TransferLine[] {
  const d = getDestination(t.brief.destination);
  const st = stays(t).map((s) => s.city);
  if (!d || !st.length) return [];
  const b = t.brief;
  const arrive = d.transfers.find((x) => x.id.endsWith("-arrive"));
  const depart = d.transfers.find((x) => x.id.endsWith("-depart"));
  if (!arrive || !depart) return [];
  const chosen: [Transfer, string, string][] = [[arrive, `${arrive.from} → ${st[0].name}`, st[0].id]];
  st.slice(1).forEach((city, i) => {
    const x = d.transfers.find((v) => v.from === st[i].id && v.to === city.id);
    if (x) chosen.push([x, `${st[i].name} → ${city.name}`, city.id]);
  });
  const last = st[st.length - 1];
  chosen.push([depart, `${last.name} → ${depart.to}`, last.id]);
  return chosen.map(([x, label, city]) => {
    let mode = x.mode;
    let price: number;
    if (x.pricing === "per_vehicle") {
      const v = vehicleFor(pax(b));
      price = x.prices[v] ?? 0;
      mode = `private ${v === "sedan" ? "car" : v === "suv" ? "SUV" : "van"}`;
    } else {
      let prices: { adult: number; child: number } = { adult: x.prices.adult ?? 0, child: x.prices.child ?? 0 };
      if (x.by_hotel) {
        const pick = t.hotels[city];
        const entry = pick ? x.by_hotel[pick.hotel_id] : undefined;
        prices = entry ?? { adult: 0, child: 0 };
        mode = entry ? entry.mode : "boat or seaplane, set by the resort";
      }
      price = prices.adult * b.adults + prices.child * children(b);
    }
    return { id: x.id, label, mode, duration: x.duration, price };
  });
}

export const activityPrice = (a: Activity, b: Brief) => a.price_adult * b.adults + a.price_child * children(b);

export interface HotelLine {
  city: City;
  nights: number;
  hotel: Hotel | null;
  room: Hotel["rooms"][number] | null;
  price: number;
}
export function hotelLines(t: Trip): HotelLine[] {
  return stays(t).map(({ city, nights }) => {
    const pick = t.hotels[city.id];
    const hotel = pick ? (city.hotels.find((h) => h.id === pick.hotel_id) ?? null) : null;
    const room = hotel ? (hotel.rooms.find((r) => r.id === pick.room_id) ?? null) : null;
    return { city, nights, hotel, room, price: room ? room.price * nights * rooms(t.brief) : 0 };
  });
}

export interface Price {
  flights: number;
  hotels: number;
  transfers: number;
  activities: number;
  land: number;
  gst: number;
  total: number;
  per_person: number;
}
export function price(t: Trip): Price {
  const f = getFlight(t.flight_id);
  const flights = f ? flightPrice(f, t.brief).total : 0;
  const hotels = hotelLines(t).reduce((s, l) => s + l.price, 0);
  const tr = transfers(t).reduce((s, l) => s + l.price, 0);
  const acts = t.activities.reduce((s, p) => {
    const a = getActivity(p.activity_id);
    return s + (a ? activityPrice(a, t.brief) : 0);
  }, 0);
  const land = hotels + tr + acts;
  const gst = roundHalfUp((land * RULES.gst_pct) / 100);
  const total = flights + land + gst;
  const n = Math.max(1, pax(t.brief));
  return { flights, hotels, transfers: tr, activities: acts, land, gst, total, per_person: roundHalfUp(total / n) };
}

// ─── Recommended picks ───────────────────────────────────────────────────────

export function recommendedHotel(c: City, style: Style, cheapest = false): Hotel {
  const fitting = c.hotels.filter((h) => h.tags.includes(style));
  if (!cheapest) return fitting[0] ?? c.hotels[0];
  const pool = fitting.length ? fitting : c.hotels;
  return pool.reduce((best, h) => (h.rooms[0].price < best.rooms[0].price ? h : best), pool[0]);
}

export function recommendedActivities(t: Trip): PlannedActivity[] {
  const style = styleOf(t.brief);
  const planned: PlannedActivity[] = [];
  const work: Trip = { ...t, activities: planned };
  for (const d of days(t)) {
    const wanted: Slot[][] = d.kind === "arrival" ? [["evening"]] : d.kind === "full" ? [["morning", "full_day"], ["afternoon"]] : [];
    for (const slots of wanted) {
      const pick = d.city.activities.find(
        (a) => slots.includes(a.slot) && a.tags.includes(style) && !planned.some((p) => p.activity_id === a.id) && cannotPlace(work, a.id, d.day) === null,
      );
      if (pick) {
        planned.push({ day: d.day, activity_id: pick.id });
        break;
      }
    }
  }
  return planned;
}

export interface Recommendation {
  flight_id: string | null;
  hotels: Record<string, HotelPick>;
  activities: PlannedActivity[];
}
/** The whole suggested package for a complete brief (CONTRACT, "Recommended picks"). */
export function recommend(t: Trip): Recommendation {
  const flight = recommendedFlight(t.brief);
  const pick = (cheapest: boolean) =>
    Object.fromEntries(
      stays(t).map(({ city }) => {
        const h = recommendedHotel(city, styleOf(t.brief), cheapest);
        return [city.id, { hotel_id: h.id, room_id: h.rooms[0].id }];
      }),
    );
  const base: Trip = { ...t, split: splitOf(t), flight_id: flight?.id ?? null, hotels: pick(false), activities: [] };
  base.activities = recommendedActivities(base);
  if (t.brief.budget > 0 && price(base).total > t.brief.budget) base.hotels = pick(true);
  return { flight_id: base.flight_id, hotels: base.hotels, activities: base.activities };
}

/** What a brief still needs before flights and hotels can be shown. */
export function missing(b: Brief): (keyof Brief)[] {
  const out: (keyof Brief)[] = [];
  if (!b.from_city) out.push("from_city");
  if (!b.destination) out.push("destination");
  if (!b.start_date) out.push("start_date");
  if (!b.nights) out.push("nights");
  return out;
}

/** The "from ₹X per person" a destination card shows (the brain's
 *  `engine.from_price`): two adults, default nights and split, the cheapest
 *  flight from `origin`, the cheapest room in each city, transfers and GST, no
 *  activities, no season. */
export function fromPrice(d: Destination, origin = "DEL"): number {
  const t = emptyTrip();
  t.brief = { ...emptyBrief(), from_city: origin, destination: d.id, nights: d.default_nights, adults: 2 };
  t.split = defaultSplit(d, d.default_nights);
  const fl = flightsFor(origin, d.id).reduce<Flight | undefined>((b, x) => (!b || x.fare_adult < b.fare_adult ? x : b), undefined);
  t.flight_id = fl?.id ?? null;
  const minRoom = (h: Hotel) => Math.min(...h.rooms.map((r) => r.price));
  for (const { city } of stays(t)) {
    const h = city.hotels.reduce((b, x) => (minRoom(x) < minRoom(b) ? x : b), city.hotels[0]);
    const r = h.rooms.reduce((b, x) => (x.price < b.price ? x : b), h.rooms[0]);
    t.hotels[city.id] = { hotel_id: h.id, room_id: r.id };
  }
  return price(t).per_person;
}
