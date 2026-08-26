/**
 * Seed draft itineraries for the Trip Studio demo.
 *
 * The dashboard opens on these so the agent can be asked to OPEN and MODIFY an
 * existing trip ("open the Mehta Vietnam group and move the Delhi family's return
 * a day earlier") instead of always building from scratch. They span a range of
 * complexity:
 *   1. Mehta Group — Vietnam   — flagship: 3 families, 3 origins, bassinet +
 *      wheelchair, aligned arrivals, partly built (returns still un-searched).
 *   2. Sharma Honeymoon — Bali — simple couple, fully booked; good for small edits.
 *   3. Iyer Family — Dubai     — one family of five with an infant; medium.
 *   4. Acme Offsite — Phuket   — a 24-pax corporate MICE group; skeletal.
 *   5. Reddy Pilgrimage — KTM  — seniors group, assistance-heavy; skeletal.
 *
 * Seeded into the store on first load (when localStorage has none). Once the
 * agent or the travel agent edits one, the whole list persists like any trip.
 */

import { slugify, type Itinerary } from './types';

// Fixed base time so seeds are deterministic; later entries look "older".
const T = 1_717_200_000_000;

function seed(it: Omit<Itinerary, 'id' | 'createdAt' | 'updatedAt'> & { ageDays?: number }): Itinerary {
  const { ageDays = 0, ...rest } = it;
  const updatedAt = T - ageDays * 86_400_000;
  return { ...rest, id: slugify(rest.name), createdAt: T - 14 * 86_400_000, updatedAt };
}

export const SEED_ITINERARIES: Itinerary[] = [
  // ── 1. Flagship complex group: 3 families, 3 origins ───────────────────────
  seed({
    name: 'Mehta Group — Vietnam',
    coordinator: 'Mr. Anand Mehta · +91 98xxxxxx21',
    destination: 'Phu Quoc, Vietnam (via Ho Chi Minh City)',
    start_date: '12 Aug 2026',
    end_date: '18 Aug 2026',
    summary: '12 travellers, 3 families from Bangalore, Delhi & Hyderabad. Arrivals aligned for a shared coach.',
    ageDays: 0,
    families: [
      { label: 'Mehta family (Bangalore)', origin: 'Bangalore', adults: 2, children: 1, infants: 1, meal: 'veg', assistance: '' },
      { label: 'Sharma family (Delhi)', origin: 'Delhi', adults: 2, children: 0, infants: 0, meal: 'nonveg', assistance: '' },
      { label: 'Rao family (Hyderabad)', origin: 'Hyderabad', adults: 2, children: 2, infants: 0, meal: 'mixed', assistance: 'Wheelchair assistance for 1 senior' },
    ],
    legs: [
      {
        id: 'blr-out', label: 'Bangalore → Ho Chi Minh (Outbound)', from: 'Bangalore', to: 'Ho Chi Minh City', date: '12 Aug 2026',
        selectedId: 'f1',
        options: [
          { id: 'f1', airline: 'Vietnam Airlines', flight_no: 'VN632', depart: 'BLR 23:50', arrive: 'SGN 06:35+1', duration: '5h 15m', stops: 'Non-stop', cabin: 'Economy', baggage: '23kg + 7kg', price: 31200, note: 'Arrival aligned with Delhi family for the shared coach' },
          { id: 'f2', airline: 'IndiGo', flight_no: '6E1631', depart: 'BLR 21:05', arrive: 'SGN 06:10+1', duration: '6h 35m', stops: '1 stop · BKK', cabin: 'Economy', baggage: '20kg + 7kg', price: 27450, note: '' },
          { id: 'f3', airline: 'Singapore Airlines', flight_no: 'SQ509', depart: 'BLR 21:40', arrive: 'SGN 09:20+1', duration: '8h 10m', stops: '1 stop · SIN', cabin: 'Economy', baggage: '30kg + 7kg', price: 39800, note: '' },
        ],
      },
      {
        id: 'del-out', label: 'Delhi → Ho Chi Minh (Outbound)', from: 'Delhi', to: 'Ho Chi Minh City', date: '12 Aug 2026',
        selectedId: 'f1',
        options: [
          { id: 'f1', airline: 'Vietjet Air', flight_no: 'VJ972', depart: 'DEL 23:20', arrive: 'SGN 06:40+1', duration: '5h 50m', stops: 'Non-stop', cabin: 'Economy', baggage: '20kg + 7kg', price: 29600, note: 'Lands 5 min after Bangalore family — one coach for both' },
          { id: 'f2', airline: 'Vietnam Airlines', flight_no: 'VN670', depart: 'DEL 20:30', arrive: 'SGN 04:05+1', duration: '6h 05m', stops: 'Non-stop', cabin: 'Economy', baggage: '23kg + 7kg', price: 33100, note: '' },
          { id: 'f3', airline: 'Thai Airways', flight_no: 'TG316', depart: 'DEL 22:30', arrive: 'SGN 08:15+1', duration: '8h 15m', stops: '1 stop · BKK', cabin: 'Economy', baggage: '30kg + 7kg', price: 35400, note: '' },
        ],
      },
      // Hyderabad outbound — searched, awaiting a pick.
      {
        id: 'hyd-out', label: 'Hyderabad → Ho Chi Minh (Outbound)', from: 'Hyderabad', to: 'Ho Chi Minh City', date: '12 Aug 2026',
        options: [
          { id: 'f1', airline: 'IndiGo', flight_no: '6E1009', depart: 'HYD 22:15', arrive: 'SGN 06:55+1', duration: '6h 10m', stops: '1 stop · BKK', cabin: 'Economy', baggage: '20kg + 7kg', price: 28900, note: 'Closest to the others — coach can wait 20 min' },
          { id: 'f2', airline: 'Vietjet Air', flight_no: 'VJ888', depart: 'HYD 20:40', arrive: 'SGN 05:20+1', duration: '6h 10m', stops: '1 stop · BKK', cabin: 'Economy', baggage: '20kg + 7kg', price: 26700, note: '' },
          { id: 'f3', airline: 'Malaysia Airlines', flight_no: 'MH199', depart: 'HYD 23:55', arrive: 'SGN 10:05+1', duration: '8h 40m', stops: '1 stop · KUL', cabin: 'Economy', baggage: '30kg + 7kg', price: 34200, note: '' },
        ],
      },
      // Returns not searched yet — the agent can run these.
      { id: 'blr-ret', label: 'Ho Chi Minh → Bangalore (Return)', from: 'Ho Chi Minh City', to: 'Bangalore', date: '18 Aug 2026' },
      { id: 'del-ret', label: 'Ho Chi Minh → Delhi (Return)', from: 'Ho Chi Minh City', to: 'Delhi', date: '18 Aug 2026' },
      { id: 'hyd-ret', label: 'Ho Chi Minh → Hyderabad (Return)', from: 'Ho Chi Minh City', to: 'Hyderabad', date: '18 Aug 2026' },
    ],
    hotels: [
      {
        city: 'Ho Chi Minh City', nights: 1, selectedId: 'h1',
        options: [
          { id: 'h1', name: 'Rex Hotel Saigon', area: 'District 1', stars: 5, board: 'Breakfast included', room_type: '6 rooms — Deluxe', rating: 8.7, amenities: ['Rooftop pool', 'City centre', 'Family rooms'], price_per_night: 11800, note: 'One transit night before the Phu Quoc flight' },
          { id: 'h2', name: 'Hotel Nikko Saigon', area: 'District 1', stars: 5, board: 'Breakfast included', room_type: '6 rooms — Superior', rating: 8.9, amenities: ['Pool', 'Spa', 'Kids welcome'], price_per_night: 13200, note: '' },
          { id: 'h3', name: 'Sheraton Saigon', area: 'Dong Khoi', stars: 5, board: 'Breakfast included', room_type: '6 rooms — Grand', rating: 9.0, amenities: ['Central', 'Club lounge'], price_per_night: 15600, note: '' },
        ],
      },
      // Phu Quoc — searched, awaiting a pick.
      {
        city: 'Phu Quoc', nights: 4,
        options: [
          { id: 'h1', name: 'JW Marriott Phu Quoc Emerald Bay', area: 'Khem Beach', stars: 5, board: 'Breakfast included', room_type: '6 rooms incl. 2 family rooms', rating: 9.2, amenities: ['Beachfront', 'Pool', 'Kids club', 'Bassinet on request'], price_per_night: 42500, note: 'Bassinet confirmed for the Mehta infant' },
          { id: 'h2', name: 'Premier Village Phu Quoc', area: 'An Thoi', stars: 5, board: 'Breakfast included', room_type: '3 two-bed villas', rating: 9.0, amenities: ['Private beach', 'Villa pools', 'Family-friendly'], price_per_night: 47800, note: '' },
          { id: 'h3', name: 'InterContinental Phu Quoc Long Beach', area: 'Bai Truong', stars: 5, board: 'Breakfast included', room_type: '6 rooms — Classic', rating: 8.9, amenities: ['Beachfront', 'Accessible rooms', 'Pool'], price_per_night: 38900, note: 'Has step-free accessible rooms for the Rao senior' },
        ],
      },
    ],
    days: [
      {
        day: 1, date: '12 Aug 2026', title: 'Arrivals — Ho Chi Minh City', transport: 'Shared airport coach (all 3 families)', breakfast: 'In flight', lunch: 'Pho lunch — District 1', dinner: 'At hotel',
        activities: [
          { time: 'Morning', title: 'Aligned arrivals at SGN', detail: 'Single coach collects Bangalore, Delhi & Hyderabad families', ticket_included: false },
          { time: 'Evening', title: 'Walk — Nguyen Hue & Bui Vien', detail: 'Easy stroll, wheelchair-friendly pavements', ticket_included: false },
        ],
      },
      {
        day: 2, date: '13 Aug 2026', title: 'Fly to Phu Quoc — Beach evening', transport: 'Domestic flight + resort transfer', breakfast: 'At hotel (included)', lunch: 'At resort', dinner: 'Beachfront BBQ',
        activities: [
          { time: '10:00', title: 'SGN → PQC short hop', detail: 'Internal flight, ~1h', ticket_included: true },
          { time: 'Afternoon', title: 'Check-in & Khem Beach', detail: 'Kids club open; bassinet set up', ticket_included: false },
        ],
      },
    ],
    specialRequests: [
      { type: 'bassinet', label: 'Infant bassinet', detail: '1 infant, Mehta family' },
      { type: 'assistance', label: 'Wheelchair assistance', detail: '1 senior, Rao family' },
      { type: 'meal', label: 'Veg meals', detail: 'Mehta family — all legs' },
    ],
    inclusions: ['Daily breakfast', 'Aligned airport coach transfers', 'Domestic Phu Quoc flights', 'Cable car & Sun World tickets'],
    exclusions: ['Visa fees', 'Lunches & dinners unless stated', 'Personal expenses'],
    terms: ['Rates held for 5 days subject to availability', 'Infant fare excludes a seat', 'Wheelchair assistance to be reconfirmed 72h before travel'],
    whatsapp: null,
  }),

  // ── 2. Simple couple, fully booked ─────────────────────────────────────────
  seed({
    name: 'Sharma Honeymoon — Bali',
    coordinator: 'Mrs. Neha Sharma · +91 99xxxxxx04',
    destination: 'Seminyak, Bali, Indonesia',
    start_date: '5 Sep 2026',
    end_date: '10 Sep 2026',
    summary: 'Honeymoon for two from Bangalore. Flights and hotel locked; sightseeing to be finalised.',
    ageDays: 2,
    families: [{ label: 'Sharma couple (Bangalore)', origin: 'Bangalore', adults: 2, children: 0, infants: 0, meal: 'veg', assistance: '' }],
    legs: [
      {
        id: 'blr-out', label: 'Bangalore → Denpasar (Outbound)', from: 'Bangalore', to: 'Denpasar', date: '5 Sep 2026', selectedId: 'f1',
        options: [
          { id: 'f1', airline: 'Singapore Airlines', flight_no: 'SQ511', depart: 'BLR 21:40', arrive: 'DPS 13:05+1', duration: '10h 55m', stops: '1 stop · SIN', cabin: 'Economy', baggage: '30kg + 7kg', price: 38600, note: 'Honeymoon — smoothest single-stop option' },
          { id: 'f2', airline: 'AirAsia', flight_no: 'AK24', depart: 'BLR 23:10', arrive: 'DPS 15:40+1', duration: '11h 00m', stops: '1 stop · KUL', cabin: 'Economy', baggage: '20kg + 7kg', price: 29900, note: '' },
        ],
      },
      {
        id: 'blr-ret', label: 'Denpasar → Bangalore (Return)', from: 'Denpasar', to: 'Bangalore', date: '10 Sep 2026', selectedId: 'f1',
        options: [
          { id: 'f1', airline: 'Singapore Airlines', flight_no: 'SQ512', depart: 'DPS 16:35', arrive: 'BLR 22:10', duration: '10h 05m', stops: '1 stop · SIN', cabin: 'Economy', baggage: '30kg + 7kg', price: 37200, note: '' },
          { id: 'f2', airline: 'AirAsia', flight_no: 'AK25', depart: 'DPS 18:20', arrive: 'BLR 01:05+1', duration: '11h 15m', stops: '1 stop · KUL', cabin: 'Economy', baggage: '20kg + 7kg', price: 28400, note: '' },
        ],
      },
    ],
    hotels: [
      {
        city: 'Seminyak', nights: 5, selectedId: 'h1',
        options: [
          { id: 'h1', name: 'The Legian Seminyak', area: 'Seminyak Beach', stars: 5, board: 'Breakfast included', room_type: 'Ocean Suite', rating: 9.3, amenities: ['Beachfront', 'Honeymoon setup', 'Infinity pool'], price_per_night: 26500, note: 'Honeymoon turndown & private dinner on the house' },
          { id: 'h2', name: 'W Bali Seminyak', area: 'Seminyak', stars: 5, board: 'Breakfast included', room_type: 'Spectacular Pool Suite', rating: 9.0, amenities: ['Beach club', 'Spa', 'Pool suite'], price_per_night: 31200, note: '' },
        ],
      },
    ],
    days: [
      { day: 1, date: '6 Sep 2026', title: 'Seminyak — Beach & Sunset', transport: 'Private car', breakfast: 'At hotel (included)', lunch: 'La Lucciola', dinner: 'Ku De Ta sunset',
        activities: [{ time: 'Afternoon', title: 'Seminyak Beach & spa', detail: "Couple's massage booked", ticket_included: true }] },
      { day: 2, date: '7 Sep 2026', title: 'Ubud day trip', transport: 'Private car', breakfast: 'At hotel (included)', lunch: 'Local warung',
        activities: [{ time: '09:00', title: 'Tegallalang rice terraces', detail: 'Photo stop', ticket_included: true }, { time: 'Afternoon', title: 'Sacred Monkey Forest', ticket_included: true }] },
    ],
    specialRequests: [{ type: 'other', label: 'Honeymoon', detail: 'Room decoration + private dinner' }],
    inclusions: ['Daily breakfast', 'Private car for sightseeing', 'Airport transfers'],
    exclusions: ['Visa on arrival fee', 'Lunches & dinners unless stated'],
    terms: ['Non-refundable hotel rate', 'Honeymoon perks subject to a valid marriage certificate'],
    whatsapp: null,
  }),

  // ── 3. One family of five with an infant — medium ──────────────────────────
  seed({
    name: 'Iyer Family — Dubai',
    coordinator: 'Mr. Karthik Iyer · +91 98xxxxxx55',
    destination: 'Dubai, United Arab Emirates',
    start_date: '20 Oct 2026',
    end_date: '25 Oct 2026',
    summary: 'Family of five (2 adults, 2 children, 1 infant) from Bangalore. Outbound booked; return and activities pending.',
    ageDays: 4,
    families: [{ label: 'Iyer family (Bangalore)', origin: 'Bangalore', adults: 2, children: 2, infants: 1, meal: 'veg', assistance: '' }],
    legs: [
      {
        id: 'blr-out', label: 'Bangalore → Dubai (Outbound)', from: 'Bangalore', to: 'Dubai', date: '20 Oct 2026', selectedId: 'f1',
        options: [
          { id: 'f1', airline: 'Emirates', flight_no: 'EK569', depart: 'BLR 04:25', arrive: 'DXB 07:15', duration: '4h 20m', stops: 'Non-stop', cabin: 'Economy', baggage: '30kg + 7kg', price: 24800, note: 'Bassinet seats confirmed for the infant' },
          { id: 'f2', airline: 'IndiGo', flight_no: '6E63', depart: 'BLR 09:10', arrive: 'DXB 11:55', duration: '4h 15m', stops: 'Non-stop', cabin: 'Economy', baggage: '20kg + 7kg', price: 19400, note: '' },
        ],
      },
      // Return — not searched yet.
      { id: 'blr-ret', label: 'Dubai → Bangalore (Return)', from: 'Dubai', to: 'Bangalore', date: '25 Oct 2026' },
    ],
    hotels: [
      {
        city: 'Dubai Marina', nights: 5, selectedId: 'h1',
        options: [
          { id: 'h1', name: 'Address Dubai Marina', area: 'Dubai Marina', stars: 5, board: 'Breakfast included', room_type: '2 connecting rooms', rating: 9.0, amenities: ['Marina view', 'Kids pool', 'Bassinet', 'Mall access'], price_per_night: 22600, note: '' },
          { id: 'h2', name: 'JW Marriott Marquis', area: 'Business Bay', stars: 5, board: 'Breakfast included', room_type: 'Family room', rating: 8.8, amenities: ['Pool', 'Spa', 'Family-friendly'], price_per_night: 20100, note: '' },
        ],
      },
    ],
    days: [
      { day: 1, date: '20 Oct 2026', title: 'Arrival & Marina evening', transport: 'Private van', breakfast: 'In flight', dinner: 'Marina Walk',
        activities: [{ time: 'Evening', title: 'Dubai Marina & JBR beach', detail: 'Easy first day with the kids', ticket_included: false }] },
    ],
    specialRequests: [
      { type: 'bassinet', label: 'Infant bassinet', detail: '1 infant, Iyer family' },
      { type: 'meal', label: 'Veg meals', detail: 'All members' },
    ],
    inclusions: ['Daily breakfast', 'Airport transfers'],
    exclusions: ['Visa fee', 'Park tickets unless stated'],
    terms: ['Connecting rooms subject to availability'],
    whatsapp: null,
  }),

  // ── 4. Corporate MICE offsite — skeletal ───────────────────────────────────
  seed({
    name: 'Acme Offsite — Phuket',
    coordinator: 'Priya Menon (Acme HR) · +91 90xxxxxx77',
    destination: 'Phuket, Thailand',
    start_date: '3 Nov 2026',
    end_date: '6 Nov 2026',
    summary: '24-person annual offsite from Bangalore. Conference + team activities. Flights, hotel and agenda to be built.',
    ageDays: 6,
    families: [{ label: 'Acme team (Bangalore)', origin: 'Bangalore', adults: 24, children: 0, infants: 0, meal: 'mixed', assistance: '' }],
    legs: [
      { id: 'blr-out', label: 'Bangalore → Phuket (Outbound)', from: 'Bangalore', to: 'Phuket', date: '3 Nov 2026' },
      { id: 'blr-ret', label: 'Phuket → Bangalore (Return)', from: 'Phuket', to: 'Bangalore', date: '6 Nov 2026' },
    ],
    hotels: [{ city: 'Phuket', nights: 3 }],
    days: [],
    specialRequests: [
      { type: 'other', label: 'Conference hall + AV', detail: 'Half-day plenary, Day 2' },
      { type: 'meal', label: 'Mixed meals', detail: 'Veg + non-veg buffet' },
    ],
    inclusions: ['Conference hall (half day)', 'Group coach transfers'],
    exclusions: ['Alcohol', 'Personal expenses'],
    terms: ['Group rate needs a 50% advance to hold'],
    whatsapp: null,
  }),

  // ── 5. Seniors pilgrimage, assistance-heavy — skeletal ─────────────────────
  seed({
    name: 'Reddy Pilgrimage — Kathmandu',
    coordinator: 'Mr. Suresh Reddy · +91 99xxxxxx30',
    destination: 'Kathmandu & Pashupatinath, Nepal',
    start_date: '15 Nov 2026',
    end_date: '19 Nov 2026',
    summary: 'A pilgrimage group of six seniors from Hyderabad. Gentle pace; wheelchair assistance needed. To be built.',
    ageDays: 8,
    families: [
      { label: 'Reddy family (Hyderabad)', origin: 'Hyderabad', adults: 4, children: 0, infants: 0, meal: 'veg', assistance: '' },
      { label: 'Companions (Hyderabad)', origin: 'Hyderabad', adults: 2, children: 0, infants: 0, meal: 'veg', assistance: 'Wheelchair assistance for 2' },
    ],
    legs: [
      { id: 'hyd-out', label: 'Hyderabad → Kathmandu (Outbound)', from: 'Hyderabad', to: 'Kathmandu', date: '15 Nov 2026' },
      { id: 'hyd-ret', label: 'Kathmandu → Hyderabad (Return)', from: 'Kathmandu', to: 'Hyderabad', date: '19 Nov 2026' },
    ],
    hotels: [{ city: 'Kathmandu', nights: 4 }],
    days: [],
    specialRequests: [
      { type: 'assistance', label: 'Wheelchair assistance', detail: '2 seniors — airports & temples' },
      { type: 'meal', label: 'Veg meals', detail: 'All members, satvik preferred' },
      { type: 'other', label: 'Gentle pace', detail: 'Senior-friendly itinerary' },
    ],
    inclusions: ['Daily breakfast', 'Temple visits with a guide', 'Wheelchair-accessible coach'],
    exclusions: ['Pooja offerings', 'Personal expenses'],
    terms: ['Assistance to be reconfirmed 72h before travel'],
    whatsapp: null,
  }),
];
