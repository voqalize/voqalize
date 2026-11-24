/**
 * Every fact the site shows, from `data/homes.json`, and the three rules the
 * brain implements identically (CONTRACT.md, "Shared rules"): the filter and
 * its order, the EMI, and the site-visit slots. Change a rule here only with
 * its twin in `backend/homes.py`.
 */
import raw from "../../../data/homes.json";

export type CityId = "bengaluru" | "pune" | "hyderabad";
export type Deal = "buy" | "rent";
export type Possession = "ready" | "under_construction";
export type Kind = "new" | "resale" | "rent";
export type Weekday = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";

export interface Near {
  id: string;
  name: string;
  km: number;
}

export interface Listing {
  id: string;
  kind: Kind;
  deal: Deal;
  title: string;
  project_id: string | null;
  society: string;
  city: CityId;
  locality: string;
  bhk: number;
  carpet_sqft: number;
  price?: number;
  price_per_sqft?: number;
  rent?: number;
  deposit?: number;
  possession: Possession;
  possession_date: string;
  floor: number;
  total_floors: number;
  facing: string;
  bathrooms: number;
  balconies: number;
  parking: number;
  furnishing: string;
  age_years: number | null;
  amenities: string[];
  rera: string;
  address: string;
  x: number;
  y: number;
  palette: [string, string];
  nearby: { offices: Near[]; schools: Near[]; metro: Near[] };
}

export interface Team {
  contact: string;
  phone: string;
  slot_minutes: number;
  hours: Record<Weekday, [string, string] | null>;
  booked: Partial<Record<Weekday, string[]>>;
  office?: string;
}

export interface Project {
  id: string;
  name: string;
  city: CityId;
  locality: string;
  x: number;
  y: number;
  status: Possession;
  possession: string;
  launched: string;
  progress: number;
  rera: string;
  towers: number;
  floors: number;
  units: number;
  acres: number;
  configs: number[];
  address: string;
  pitch: string;
  amenities: string[];
  palette: [string, string];
  milestones: [string, string][];
  team: Team;
  nearby: { offices: Near[]; schools: Near[]; metro: Near[] };
  price_from: number;
  price_to: number;
  listing_ids: string[];
}

export interface Place {
  id: string;
  name: string;
  kind: "office" | "school" | "metro";
  x: number;
  y: number;
}

export interface City {
  id: CityId;
  name: string;
  code: string;
  state: string;
  water: { name: string; points: [number, number][] }[];
  roads: { name: string; points: [number, number][] }[];
  metro: { name: string; colour: string; points: [number, number][] }[];
  localities: { name: string; x: number; y: number }[];
  places: Place[];
  exchange: Team & { office: string };
}

export interface Lender {
  id: string;
  name: string;
  rate: number;
  note: string;
}

interface HomesData {
  brand: { name: string; exchange: string; tagline: string; since: number; helpline: string; email: string; disclaimer: string };
  km_per_unit: number;
  cities: City[];
  projects: Project[];
  listings: Listing[];
  lenders: Lender[];
  emi: { down_pct: number; tenure_years: number; lender: string; max_tenure_years: number; min_down_pct: number };
  bring: Record<"new" | "ready" | "resale" | "rent", string[]>;
}

export const DATA = raw as unknown as HomesData;
export const BRAND = DATA.brand;
export const CITIES = DATA.cities;
export const PROJECTS = DATA.projects;
export const LISTINGS = DATA.listings;
export const LENDERS = DATA.lenders;
export const EMI_DEFAULTS = DATA.emi;

const byId = new Map(LISTINGS.map((l) => [l.id, l]));
export const getListing = (id: string | null | undefined) => (id ? byId.get(id.trim().toUpperCase()) : undefined);
export const getProject = (id: string | null | undefined) => PROJECTS.find((p) => p.id === id);
export const getCity = (id: string | null | undefined) => CITIES.find((c) => c.id === id);
export const getLender = (id: string | null | undefined) => LENDERS.find((l) => l.id === id);
export const officesOf = (city?: CityId | null) =>
  CITIES.filter((c) => !city || c.id === city).flatMap((c) => c.places.filter((p) => p.kind === "office").map((p) => ({ ...p, city: c.id })));
export const placeName = (id: string | null | undefined) => {
  for (const c of CITIES) for (const p of c.places) if (p.id === id) return p.name;
  return id ?? "";
};
export const ALL_AMENITIES = [...new Set(LISTINGS.flatMap((l) => l.amenities))].sort();

// ─── Money and dates, Indian style ──────────────────────────────────────────

/** ₹1,14,00,000 */
export function inr(n: number): string {
  return `₹${Math.round(n).toLocaleString("en-IN")}`;
}

/** ₹1.14 Cr, ₹95 L, ₹42,000 */
export function inrShort(n: number): string {
  if (n >= 1e7) return `₹${trim(n / 1e7)} Cr`;
  if (n >= 1e5) return `₹${trim(n / 1e5)} L`;
  return inr(n);
}
const trim = (x: number) => (Math.round(x * 100) / 100).toString();

export const priceLabel = (l: Listing) => (l.deal === "rent" ? `${inr(l.rent ?? 0)}/mo` : inrShort(l.price ?? 0));
export const amountOf = (l: Listing) => (l.deal === "rent" ? (l.rent ?? 0) : (l.price ?? 0));

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
/** 22 Nov 2026 from 2026-11-22 */
export function dateLabel(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return `${String(d).padStart(2, "0")} ${MONTHS[m - 1]} ${y}`;
}
export function weekdayLabel(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return DAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
}
/** 10:30 → 10:30 am */
export function timeLabel(hhmm: string): string {
  const [h, m] = hhmm.split(":").map(Number);
  const suffix = h >= 12 ? "pm" : "am";
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12}:${String(m).padStart(2, "0")} ${suffix}`;
}

// ─── The filter (CONTRACT: "Filter") ─────────────────────────────────────────

export interface Filters {
  city?: CityId | null;
  deal?: Deal | null;
  bhk?: number[] | null;
  budget_min?: number | null;
  budget_max?: number | null;
  possession?: Possession | null;
  localities?: string[] | null;
  office?: string | null;
  max_km?: number | null;
  school_km?: number | null;
  metro_km?: number | null;
  amenities?: string[] | null;
}

export const FILTER_KEYS: (keyof Filters)[] = [
  "city", "deal", "bhk", "budget_min", "budget_max", "possession", "localities", "office", "max_km", "school_km", "metro_km", "amenities",
];

const set = <T,>(v: T | null | undefined): v is T => v !== null && v !== undefined && !(Array.isArray(v) && v.length === 0);

export const officeKm = (l: Listing, office: string) => l.nearby.offices.find((o) => o.id === office)?.km;

export function matches(l: Listing, f: Filters): boolean {
  if (set(f.city) && l.city !== f.city) return false;
  if (set(f.deal) && l.deal !== f.deal) return false;
  if (set(f.bhk) && !f.bhk.includes(l.bhk)) return false;
  const amount = amountOf(l);
  if (set(f.budget_min) && amount < f.budget_min) return false;
  if (set(f.budget_max) && amount > f.budget_max) return false;
  if (set(f.possession) && l.possession !== f.possession) return false;
  if (set(f.localities) && !f.localities.includes(l.locality)) return false;
  if (set(f.office) && set(f.max_km)) {
    const km = officeKm(l, f.office);
    if (km === undefined || km > f.max_km) return false;
  }
  if (set(f.school_km) && !(l.nearby.schools[0] && l.nearby.schools[0].km <= f.school_km)) return false;
  if (set(f.metro_km) && !(l.nearby.metro[0] && l.nearby.metro[0].km <= f.metro_km)) return false;
  if (set(f.amenities) && !f.amenities.every((a) => l.amenities.includes(a))) return false;
  return true;
}

/** With an office: km to it, then price; otherwise price (buy) or rent ascending, buy before rent; ties by id. */
export function order(list: Listing[], f: Filters): Listing[] {
  const office = set(f.office) ? f.office : null;
  return [...list].sort((a, b) => {
    if (office) {
      const ka = officeKm(a, office) ?? Number.POSITIVE_INFINITY;
      const kb = officeKm(b, office) ?? Number.POSITIVE_INFINITY;
      if (ka !== kb) return ka - kb;
      if (amountOf(a) !== amountOf(b)) return amountOf(a) - amountOf(b);
      return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
    }
    if (a.deal !== b.deal) return a.deal === "buy" ? -1 : 1;
    if (amountOf(a) !== amountOf(b)) return amountOf(a) - amountOf(b);
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  });
}

export function search(f: Filters): Listing[] {
  return order(LISTINGS.filter((l) => matches(l, f)), f);
}

/** "2–3 BHK to buy in Bengaluru, up to ₹1.5 Cr, within 8 km of Cedarline Tech Park" */
export function summarise(f: Filters): string {
  const parts: string[] = [];
  const bhk = set(f.bhk) ? `${[...f.bhk].sort().join(", ")} BHK` : "Homes";
  parts.push(`${bhk}${f.deal === "rent" ? " to rent" : f.deal === "buy" ? " to buy" : ""}`);
  parts.push(`in ${set(f.localities) ? f.localities.join(", ") : (getCity(f.city)?.name ?? "all cities")}`);
  const unit = f.deal === "rent" ? "/mo" : "";
  if (set(f.budget_min) && set(f.budget_max)) parts.push(`${inrShort(f.budget_min)}–${inrShort(f.budget_max)}${unit}`);
  else if (set(f.budget_max)) parts.push(`up to ${inrShort(f.budget_max)}${unit}`);
  else if (set(f.budget_min)) parts.push(`from ${inrShort(f.budget_min)}${unit}`);
  if (f.possession === "ready") parts.push("ready to move");
  if (f.possession === "under_construction") parts.push("under construction");
  if (set(f.office)) parts.push(set(f.max_km) ? `within ${f.max_km} km of ${placeName(f.office)}` : `nearest ${placeName(f.office)} first`);
  if (set(f.school_km)) parts.push(`a school within ${f.school_km} km`);
  if (set(f.metro_km)) parts.push(`metro within ${f.metro_km} km`);
  if (set(f.amenities)) parts.push(`with ${f.amenities.join(", ")}`);
  return parts.join(", ");
}

export function cleanFilters(f: Filters): Filters {
  const out: Filters = {};
  for (const k of FILTER_KEYS) {
    const v = f[k];
    if (set(v)) (out as Record<string, unknown>)[k] = v;
  }
  return out;
}

// ─── EMI (CONTRACT: "EMI") ───────────────────────────────────────────────────

export function emi(price: number, downPct: number, tenureYears: number, rate: number): { emi: number; principal: number; interest: number } {
  const principal = price * (1 - downPct / 100);
  const r = rate / 1200;
  const n = tenureYears * 12;
  const f = (1 + r) ** n;
  const monthly = Math.round((principal * r * f) / (f - 1));
  return { emi: monthly, principal: Math.round(principal), interest: Math.round(monthly * n - principal) };
}

// ─── Visit slots (CONTRACT: "Visit slots") ───────────────────────────────────

const WEEKDAYS: Weekday[] = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];

/** Today's date in Asia/Kolkata, YYYY-MM-DD. */
export function todayIST(now: Date = new Date()): string {
  const ist = new Date(now.getTime() + 5.5 * 3600 * 1000);
  return ist.toISOString().slice(0, 10);
}

export function addDays(day: string, n: number): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}

export const weekdayOf = (day: string): Weekday => {
  const [y, m, d] = day.split("-").map(Number);
  return WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
};

/** The 7 dates after today, IST. */
export const visitDays = (now?: Date) => Array.from({ length: 7 }, (_, i) => addDays(todayIST(now), i + 1));

export function hostOf(l: Listing): Team & { office?: string } {
  if (l.kind === "new" && l.project_id) return getProject(l.project_id)!.team;
  return getCity(l.city)!.exchange;
}

/** Who hosts a visit: the project's team, or the city's Exchange desk. Two visits with one host cannot share a slot. */
export const hostKey = (l: Listing) => (l.kind === "new" && l.project_id ? l.project_id : `exchange:${l.city}`);

export const visitAddress = (l: Listing) => (l.kind === "new" && l.project_id ? getProject(l.project_id)!.address : getCity(l.city)!.exchange.office);

export function bringFor(l: Listing): string[] {
  if (l.kind === "new") return DATA.bring[l.possession === "under_construction" ? "new" : "ready"];
  return DATA.bring[l.kind];
}

const toMin = (hhmm: string) => {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
};
const toHHMM = (min: number) => `${String(Math.floor(min / 60)).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;

export type DayPart = "morning" | "afternoon" | "evening";
export const partOf = (hhmm: string): DayPart => (toMin(hhmm) < 12 * 60 ? "morning" : toMin(hhmm) < 16 * 60 ? "afternoon" : "evening");

export interface Slot {
  id: string; // YYYY-MM-DDTHH:MM
  day: string;
  time: string;
  part: DayPart;
  free: boolean;
}

/** Every slot of `day` for this listing's host; `taken` holds slot ids this browser booked. */
export function slotsFor(l: Listing, day: string, taken: Set<string> = new Set()): Slot[] | null {
  const host = hostOf(l);
  const key = weekdayOf(day);
  const hours = host.hours[key];
  if (!hours) return null;
  const booked = new Set(host.booked[key] ?? []);
  const out: Slot[] = [];
  for (let t = toMin(hours[0]); t + host.slot_minutes <= toMin(hours[1]); t += host.slot_minutes) {
    const time = toHHMM(t);
    const id = `${day}T${time}`;
    out.push({ id, day, time, part: partOf(time), free: !booked.has(time) && !taken.has(id) });
  }
  return out;
}

/** KV-<listing number>-<DD><HHMM> */
export function bookingRef(listingId: string, slot: string): string {
  const num = listingId.split("-").pop();
  const day = slot.slice(8, 10);
  const hhmm = slot.slice(11, 16).replace(":", "");
  return `KV-${num}-${day}${hhmm}`;
}
