/**
 * The Petwell catalog, mirrored for rendering.
 *
 * `backend/catalog.py` is the source of truth — the ids here, and `isTaken`'s
 * slot rule, MUST stay identical to it, because the brain names branches,
 * services and times by those ids and the screen looks them up here. Every
 * name, address and phone number is invented.
 */

export type VisitType = 'clinic' | 'home';

export interface Branch {
  id: string;
  city: string;
  name: string;
  address: string;
  emergency: boolean;
}

export interface Service {
  id: string;
  name: string;
  group: 'Everyday care' | 'Specialty care' | 'At home';
  visit: VisitType;
  blurb: string;
}

export interface Helpline {
  region: string;
  phone: string;
  cities: string[];
}

export const CITIES = [
  'Goa',
  'Gurugram',
  'Hyderabad',
  'Jaipur',
  'Kolkata',
  'Lucknow',
  'Mumbai',
  'New Delhi',
  'Noida',
] as const;

export const OPENING_SOON = new Set<string>(['Kolkata']);

export const BRANCHES: Branch[] = [
  { id: 'goa-porvorim', city: 'Goa', name: 'Petwell Porvorim', address: '12 Palm Grove Arcade, Porvorim, Goa 403521', emergency: true },
  { id: 'goa-siolim', city: 'Goa', name: 'Petwell Siolim', address: '3 Chapel Road, Siolim, Goa 403517', emergency: false },
  { id: 'ggn-palam-vihar', city: 'Gurugram', name: 'Petwell Palam Vihar', address: 'Plot 21, Palam Vihar Main Road, Sector 23, Gurugram 122017', emergency: false },
  { id: 'ggn-sushant-lok', city: 'Gurugram', name: 'Petwell Sushant Lok', address: 'B-14 Market Lane, Sushant Lok 2, Sector 55, Gurugram 122011', emergency: true },
  { id: 'hyd-jubilee-hills', city: 'Hyderabad', name: 'Petwell Jubilee Hills', address: '8-2-293 Road No. 1, Jubilee Hills, Hyderabad 500033', emergency: true },
  { id: 'jpr-vaishali-nagar', city: 'Jaipur', name: 'Petwell Vaishali Nagar', address: 'C-41 Amrapali Marg, Vaishali Nagar, Jaipur 302021', emergency: true },
  { id: 'kol-ballygunge', city: 'Kolkata', name: 'Petwell Ballygunge', address: '22 Lake View Road, Ballygunge, Kolkata 700029', emergency: false },
  { id: 'lko-gomti-nagar', city: 'Lucknow', name: 'Petwell Gomti Nagar', address: '5/112 Vibhuti Khand, Gomti Nagar, Lucknow 226010', emergency: true },
  { id: 'mum-mahalaxmi', city: 'Mumbai', name: 'Petwell Mahalaxmi', address: 'Racecourse View, 4 Keshavrao Khadye Marg, Mahalaxmi, Mumbai 400034', emergency: true },
  { id: 'mum-powai', city: 'Mumbai', name: 'Petwell Powai', address: 'Shop 6, Lakeside Plaza, Central Avenue, Powai, Mumbai 400076', emergency: false },
  { id: 'mum-churchgate', city: 'Mumbai', name: 'Petwell Churchgate', address: 'Ground Floor, Oval Court, Veer Nariman Road, Churchgate, Mumbai 400020', emergency: false },
  { id: 'del-shanti-niketan', city: 'New Delhi', name: 'Petwell Shanti Niketan', address: 'A-9 Shanti Niketan Market, New Delhi 110021', emergency: false },
  { id: 'del-rajouri-garden', city: 'New Delhi', name: 'Petwell Rajouri Garden', address: 'J-7 Ring Road, Rajouri Garden, New Delhi 110027', emergency: false },
  { id: 'del-gk1', city: 'New Delhi', name: 'Petwell Greater Kailash', address: 'M-31 M Block Market, Greater Kailash 1, New Delhi 110048', emergency: true },
  { id: 'del-east-of-kailash', city: 'New Delhi', name: 'Petwell East of Kailash', address: 'First Floor, E-12 Community Centre, East of Kailash, New Delhi 110065', emergency: false },
  { id: 'noida-sec-50', city: 'Noida', name: 'Petwell Noida Sector 50', address: 'C-2/18 Central Market, Sector 50, Noida 201301', emergency: true },
];

export const SERVICES: Service[] = [
  { id: 'general-consult', name: 'General consultation', group: 'Everyday care', visit: 'clinic', blurb: 'Check-ups and any health concern' },
  { id: 'vaccination', name: 'Vaccination', group: 'Everyday care', visit: 'clinic', blurb: 'Puppy, kitten and booster shots' },
  { id: 'grooming', name: 'Grooming', group: 'Everyday care', visit: 'clinic', blurb: 'Bath, trim, nails and coat care' },
  { id: 'dental', name: 'Dental care', group: 'Everyday care', visit: 'clinic', blurb: 'Cleaning, scaling, extractions' },
  { id: 'skin', name: 'Skin & allergy', group: 'Everyday care', visit: 'clinic', blurb: 'Itching, rashes, ticks and fleas' },
  { id: 'diagnostics', name: 'Diagnostics (X-ray, ultrasound, lab)', group: 'Everyday care', visit: 'clinic', blurb: 'Imaging and laboratory tests' },
  { id: 'cardiology', name: 'Cardiology', group: 'Specialty care', visit: 'clinic', blurb: 'Heart and breathing' },
  { id: 'orthopaedics', name: 'Orthopaedics', group: 'Specialty care', visit: 'clinic', blurb: 'Bones, joints and fractures' },
  { id: 'oncology', name: 'Cancer care', group: 'Specialty care', visit: 'clinic', blurb: 'Lumps, tumours, chemotherapy' },
  { id: 'neurology', name: 'Neurology', group: 'Specialty care', visit: 'clinic', blurb: 'Brain, spine and nerves' },
  { id: 'eye-care', name: 'Eye care', group: 'Specialty care', visit: 'clinic', blurb: 'Eye conditions and vision' },
  { id: 'exotic-pets', name: 'Exotic pets', group: 'Specialty care', visit: 'clinic', blurb: 'Birds, rabbits, reptiles' },
  { id: 'physiotherapy', name: 'Physiotherapy & rehab', group: 'Specialty care', visit: 'clinic', blurb: 'Recovery and mobility' },
  { id: 'home-vaccination', name: 'Vaccination at home', group: 'At home', visit: 'home', blurb: 'Shots without the car ride' },
  { id: 'home-consult', name: 'Minor illness or injury consult', group: 'At home', visit: 'home', blurb: 'A vet at your door' },
  { id: 'home-blood-sample', name: 'Blood sample collection', group: 'At home', visit: 'home', blurb: 'Lab tests from home' },
  { id: 'home-physio', name: 'Physiotherapy at home', group: 'At home', visit: 'home', blurb: 'Rehab in a familiar place' },
];

export const HELPLINES: Helpline[] = [
  { region: 'North India', phone: '+91 90000 01111', cities: ['Gurugram', 'Jaipur', 'Lucknow', 'New Delhi', 'Noida'] },
  { region: 'Mumbai & Goa', phone: '+91 90000 02222', cities: ['Mumbai', 'Goa'] },
  { region: 'Hyderabad & Kolkata', phone: '+91 90000 03333', cities: ['Hyderabad', 'Kolkata'] },
];

// ── Slots — mirrors backend/catalog.py ────────────────────────────────────────

const pad = (n: number) => String(n).padStart(2, '0');

export const CLINIC_TIMES: string[] = Array.from({ length: 11 }, (_, i) => i + 9).flatMap((h) => [
  `${pad(h)}:00`,
  `${pad(h)}:30`,
]);
export const HOME_TIMES: string[] = Array.from({ length: 8 }, (_, i) => `${pad(i + 10)}:00`);

export const BOOKING_DAYS = 7;

/** Mirrors `_taken` in `backend/catalog.py` — keep the two identical. */
function isTaken(key: string): boolean {
  let h = 0x811c9dc5; // 32-bit FNV-1a: spreads neighbouring times, so no morning is all taken
  for (const c of new TextEncoder().encode(key)) h = Math.imul(h ^ c, 0x01000193) >>> 0;
  return h % 10 < 3;
}

export function slotsFor(branchId: string, date: string, visit: VisitType): string[] {
  const times = visit === 'home' ? HOME_TIMES : CLINIC_TIMES;
  return times.filter((t) => !isTaken(`${branchId}|${date}|${t}`));
}

/** Today in India, as an ISO date — the brain books against the same clock. */
export function todayIst(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' }).format(new Date());
}

export function bookingDates(): string[] {
  const [y, m, d] = todayIst().split('-').map(Number);
  return Array.from({ length: BOOKING_DAYS }, (_, i) => {
    const day = new Date(Date.UTC(y, m - 1, d + i));
    return day.toISOString().slice(0, 10);
  });
}

// ── Lookups and formatting ────────────────────────────────────────────────────

export const getBranch = (id: string | null | undefined) => BRANCHES.find((b) => b.id === id);
export const getService = (id: string | null | undefined) => SERVICES.find((s) => s.id === id);
export const branchesIn = (city: string) => BRANCHES.filter((b) => b.city === city);
export const helplineFor = (city: string) =>
  HELPLINES.find((h) => h.cities.includes(city)) ?? HELPLINES[0];

export function formatTime(t: string): string {
  const [h, m] = t.split(':').map(Number);
  const suffix = h >= 12 ? 'PM' : 'AM';
  return `${((h + 11) % 12) + 1}:${pad(m)} ${suffix}`;
}

export function formatDate(iso: string, opts: Intl.DateTimeFormatOptions = {}, loc = 'en-IN'): string {
  const [y, m, d] = iso.split('-').map(Number);
  return new Intl.DateTimeFormat(loc, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
    ...opts,
  }).format(new Date(Date.UTC(y, m - 1, d)));
}
