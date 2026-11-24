/**
 * The clinic's authored data (../data/clinic.json, ../data/bookings.json),
 * typed, and the small formatting helpers every page uses. Nothing the page
 * shows about prices, rules, hours or dentists comes from anywhere else.
 */
import clinicJson from "../../../data/clinic.json";
import bookingsJson from "../../../data/bookings.json";

export type Day = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
export const DAYS: Day[] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
export type Category = "appointment" | "procedure" | "imaging";

export interface Session {
  branch?: string;
  start: string;
  end: string;
}
export interface Chair {
  id: string;
  label: string;
  kind: string;
}
export interface Room {
  id: string;
  label: string;
  does: string[];
  sessions: Session[];
}
export interface Branch {
  id: string;
  name: string;
  short: string;
  address: string;
  landmark: string;
  phone: string;
  open_days: Day[];
  open: string;
  close: string;
  parking: string;
  chairs: Chair[];
  imaging: Room[];
}
export interface Dentist {
  id: string;
  name: string;
  short: string;
  qualification: string;
  role: string;
  years: number;
  languages: string[];
  bio: string;
  initials: string;
  schedule: Partial<Record<Day, Session[]>>;
}
export interface Service {
  id: string;
  category: Category;
  name: string;
  spoken: string[];
  duration_min: number;
  price: { min: number; max: number; note?: string };
  dentists?: string[];
  chairs?: string[];
  resource?: string;
  same_day?: boolean;
  sittings?: number;
  sitting_gap_days?: { min: number; max: number };
  requires?: string;
  summary: string;
}
export interface Rule {
  title: string;
  text: string;
  consult_services?: string[];
  within_days?: number;
  alternative?: string;
  gap_min_days?: number;
  gap_max_days?: number;
}
export interface Cancellation {
  free_until_hours: number;
  late_fee: number;
  late_fee_waived_for: string[];
  no_show_fee: number;
  imaging_free_until_hours: number;
  online_changes_max: number;
  text: string;
  rct_text: string;
}
export interface Visit {
  service: string;
  branch: string;
  week: number;
  day: Day;
  start: string;
  dentist?: string;
  sitting?: number;
}
export interface Patient {
  id: string;
  name: string;
  phone: string;
  age?: number;
  since?: number;
  referral: { from: string; for: string; note?: string } | null;
  history: Visit[];
}
/** An appointment before it has a date (authored). */
export interface Booking {
  id: string;
  service: string;
  branch: string;
  start: string;
  duration_min: number;
  week?: number;
  day?: Day;
  anchor?: "next_open_day";
  dentist?: string;
  chair?: string;
  resource?: string;
  patient_id?: string;
  sitting?: number;
  changes?: number;
}
export interface Instruction {
  title: string;
  text?: string;
  general?: string;
  by_service?: Record<string, string>;
}

export interface ClinicData {
  clinic: {
    name: string;
    short: string;
    tagline: string;
    phone: string;
    whatsapp: string;
    email: string;
    timezone: string;
    since: number;
    emergency_line: string;
  };
  booking: { slot_step_min: number; lead_min: number; emergency_lead_min: number; horizon_days: number; id_prefix: string };
  otp: { demo_code: string };
  branches: Branch[];
  dentists: Dentist[];
  services: Service[];
  rules: Record<string, Rule>;
  policies: { cancellation: Cancellation };
  instructions: Record<string, Instruction>;
  clinical: { topics: string[]; red_flags: string; callback_windows: Record<string, string> };
  patients: Patient[];
  patient_appointments: Booking[];
}

export const DATA = clinicJson as unknown as ClinicData;
export const FILLER = (bookingsJson as unknown as { bookings: Booking[] }).bookings;
export const CLINIC = DATA.clinic;
export const POLICY = DATA.policies.cancellation;

export const service = (id: string | null | undefined) => DATA.services.find((s) => s.id === id);
export const dentist = (id: string | null | undefined) => DATA.dentists.find((d) => d.id === id);
export const branch = (id: string | null | undefined) => DATA.branches.find((b) => b.id === id);
export const room = (id: string | null | undefined) => {
  for (const b of DATA.branches) for (const r of b.imaging) if (r.id === id) return { room: r, branch: b };
  return undefined;
};
export const chair = (id: string | null | undefined) => {
  for (const b of DATA.branches) for (const c of b.chairs) if (c.id === id) return { chair: c, branch: b };
  return undefined;
};

export const CATEGORY_LABEL: Record<Category, string> = {
  appointment: "Appointments",
  procedure: "Procedures",
  imaging: "Scans & X-rays",
};

/** The last ten digits of what was typed or said. */
export const normalPhone = (phone: string) => phone.replace(/\D/g, "").slice(-10);
/** 9845031726 → 98450 31726 */
export const showPhone = (digits: string) => (digits.length === 10 ? `${digits.slice(0, 5)} ${digits.slice(5)}` : digits);

export function minutes(hhmm: string): number {
  const [h, m] = hhmm.split(":");
  return Number(h) * 60 + Number(m);
}
export function hhmm(total: number): string {
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

/** ₹1,25,000 — the Indian grouping. */
export function rupees(n: number): string {
  const s = String(Math.round(n));
  if (s.length <= 3) return `₹${s}`;
  let head = s.slice(0, -3);
  const tail = s.slice(-3);
  const groups: string[] = [];
  while (head.length > 2) {
    groups.unshift(head.slice(-2));
    head = head.slice(0, -2);
  }
  if (head) groups.unshift(head);
  return `₹${[...groups, tail].join(",")}`;
}

export function priceRange(s: Service): string {
  return s.price.min === s.price.max ? rupees(s.price.min) : `${rupees(s.price.min)} – ${rupees(s.price.max)}`;
}

/** '14:30' → '2:30 pm' */
export function time12(t: string): string {
  const m = minutes(t);
  const h = Math.floor(m / 60);
  const mm = m % 60;
  const suffix = h < 12 ? "am" : "pm";
  return `${h % 12 || 12}:${String(mm).padStart(2, "0")} ${suffix}`;
}

export function durationText(min: number): string {
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

export const prepLine = (serviceId: string) =>
  DATA.instructions.eating.by_service?.[serviceId] ?? DATA.instructions.eating.general ?? "";
export const aftercareLine = (serviceId: string) => DATA.instructions.aftercare.by_service?.[serviceId] ?? "";

export function dentistsAt(branchId: string): Dentist[] {
  return DATA.dentists.filter((d) => Object.values(d.schedule).some((ss) => ss?.some((s) => s.branch === branchId)));
}

/** The days and hours a dentist works at a branch, as short text: "Mon, Wed, Fri". */
export function daysAt(d: Dentist, branchId: string): string {
  const names: Record<Day, string> = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" };
  return DAYS.filter((day) => d.schedule[day]?.some((s) => s.branch === branchId))
    .map((day) => names[day])
    .join(", ");
}
