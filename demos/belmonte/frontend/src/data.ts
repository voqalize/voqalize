/**
 * Hotel Belmonte's data, typed: `../data/hotel.json`, the same file the
 * concierge's brain reads (`backend/hotel.py`). Everything in it is invented.
 * Nothing on screen states a price, slot, menu or policy that is not here.
 */
import raw from "../../data/hotel.json";

export type Choice = [id: string, label: string, add: number];
export interface OptionGroup {
  label: string;
  pick: boolean;
  choices: Choice[];
}
export interface MenuItem {
  id: string;
  name: string;
  price: number;
  bottle?: number;
  desc: string;
  allergens: string[];
  diet: string[];
  options: string[];
  alcohol?: boolean;
}
export interface Period {
  id: string;
  label: string;
  hours: string;
  from: string;
  to: string;
  eta: string;
  items: MenuItem[];
}
export interface BarSection {
  id: string;
  label: string;
  items: MenuItem[];
}
export interface FolioLine {
  id: string;
  date: string;
  category: string;
  label: string;
  amount: number;
  detail: string;
}
export interface Scenario {
  label: string;
  today: string;
  now: string;
  arrive: string;
  depart: string;
  checked_in: boolean;
  room: string | null;
  folio: FolioLine[];
}
export interface CheckinRoom {
  room: string;
  floor: number;
  bed: "king" | "queens";
  quiet: boolean;
  ready: string;
  note: string;
}
export interface LateOption {
  id: string;
  label: string;
  fee: number;
  available: boolean;
  note: string | null;
}
export interface Therapist {
  id: string;
  name: string;
  gender: "female" | "male";
  focus: string;
}
export interface Treatment {
  id: string;
  name: string;
  category: "massage" | "facial" | "ritual" | "nails";
  minutes: number;
  price: number;
  desc: string;
  therapists: string[];
  for_two?: boolean;
}
export interface Place {
  id: string;
  name: string;
  x: number;
  y: number;
}
export interface Activity {
  id: string;
  name: string;
  kind: "pools" | "kids" | "golf" | "sport" | "fitness" | "tours" | "music";
  place: string;
  desc: string;
  hours: string;
  price: number;
  per?: string;
  bookable: boolean;
  times: string[];
  capacity?: number;
  min_age?: number;
  tonight?: boolean;
}
export interface MeetingRoom {
  id: string;
  name: string;
  sqft: number;
  layouts: Record<string, number>;
  rates: { hour: number; half: number; full: number };
  av: string;
  desc: string;
}
export interface Visitor {
  id: string;
  name: string;
  purpose: string;
  waiting_min: number;
  where: string;
  status: "pending" | "approved" | "declined";
}
export interface InfoSection {
  id: string;
  title: string;
  facts: string[];
}

interface HotelFile {
  hotel: {
    name: string;
    place: string;
    address: string;
    phone: string;
    weather: { temp_f: number; summary: string; sunset: string };
    check_in_time: string;
    check_out_time: string;
    resort_fee: number;
    room_tax_pct: number;
    sales_tax_pct: number;
  };
  guest: {
    first_name: string;
    last_name: string;
    companions: string[];
    email: string;
    phone: string;
    member: string;
    card: string;
    reservation: string;
    room_type: string;
    adults: number;
    rate: number;
  };
  scenarios: Record<"arrival" | "departure", Scenario>;
  checkin: {
    arrival_times: { id: string; label: string }[];
    floors: { id: string; label: string }[];
    beds: { id: string; label: string }[];
    early: { fee: number; before: string; rule: string };
    rooms: CheckinRoom[];
    wifi: { network: string; password: string };
  };
  late_checkout: { standard: string; options: LateOption[]; rule: string };
  dispute_rule: string;
  option_groups: Record<string, OptionGroup>;
  dining: { outlet: string; service_charge_pct: number; delivery_fee: number; tips: number[]; policy: string; periods: Period[] };
  bar: {
    service_charge_pct: number;
    delivery_fee: number;
    tips: number[];
    age_rule: string;
    policy: string;
    deliver_to: { id: string; label: string }[];
    cabanas: string[];
    eta: string;
    bars: { id: string; name: string; hours: string; from: string; to: string }[];
    sections: BarSection[];
  };
  spa: {
    name: string;
    hours: string;
    service_charge_pct: number;
    arrive: string;
    cancellation: string;
    therapists: Therapist[];
    treatments: Treatment[];
    schedule: Record<string, Record<string, string[]>>;
  };
  places: Place[];
  activities: Activity[];
  meetings: {
    blocks: { id: string; label: string; from?: string; to?: string; rate: string }[];
    hours_from: string;
    hours_to: string;
    rooms: MeetingRoom[];
    layout_labels: Record<string, string>;
    catering: { id: string; name: string; per_person: number }[];
    av_addons: { id: string; name: string; price: number; per_hour?: boolean }[];
    fb_service_pct: number;
    policy: string;
    taken: Record<string, Record<string, string[][]>>;
    dates: string[];
  };
  visitors: {
    pending: Visitor[];
    rule: string;
    meet: { id: string; label: string }[];
    until: string;
  };
  requests: {
    housekeeping: { items: { id: string; label: string }[]; eta: string; turndown: string };
    maintenance: { issues: { id: string; label: string }[]; eta: string };
    wakeup: { note: string };
    valet: { ticket: string; eta: string; rate: string };
    transport: { options: { id: string; label: string; price: number | null; note: string }[] };
    lost_found: { note: string };
  };
  info: InfoSection[];
}

export const DATA = raw as unknown as HotelFile;
export const HOTEL = DATA.hotel;
export const GUEST = DATA.guest;
export const CHECKIN = DATA.checkin;
export const LATE = DATA.late_checkout;
export const GROUPS = DATA.option_groups;
export const DINING = DATA.dining;
export const BAR = DATA.bar;
export const SPA = DATA.spa;
export const PLACES = DATA.places;
export const ACTIVITIES = DATA.activities;
export const MEETINGS = DATA.meetings;
export const VISITORS = DATA.visitors;
export const REQUESTS = DATA.requests;
export const INFO = DATA.info;

export type Outlet = "dining" | "bar";
export type ScenarioId = "arrival" | "departure";

/** Every menu item of an outlet by id, with its section. */
export const ITEMS: Record<Outlet, Map<string, MenuItem & { section: string }>> = {
  dining: new Map(DINING.periods.flatMap((p) => p.items.map((i) => [i.id, { ...i, section: p.id }] as const))),
  bar: new Map(BAR.sections.flatMap((s) => s.items.map((i) => [i.id, { ...i, section: s.id }] as const))),
};
export const getItem = (outlet: Outlet, id: string) => ITEMS[outlet].get(id) ?? null;
export const getTreatment = (id: string) => SPA.treatments.find((t) => t.id === id) ?? null;
export const getTherapist = (id: string) => SPA.therapists.find((t) => t.id === id) ?? null;
export const getActivity = (id: string) => ACTIVITIES.find((a) => a.id === id) ?? null;
export const getPlace = (id: string) => PLACES.find((p) => p.id === id) ?? null;
export const getMeetingRoom = (id: string) => MEETINGS.rooms.find((r) => r.id === id) ?? null;
export const getInfo = (id: string) => INFO.find((s) => s.id === id) ?? null;
