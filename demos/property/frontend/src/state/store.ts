/**
 * The one store. Every click and every agent move writes here, through the
 * same functions, so the site works by hand and the voice layer only calls
 * these. Bookings and the shortlist persist in localStorage.
 */
import { create } from "zustand";
import { PERSONA } from "../data/persona";
import { bookingRef, hostKey, cleanFilters, EMI_DEFAULTS, type Filters, getListing, search } from "../data/homes";
import { load, save } from "./storage";

export interface Booking {
  reference: string;
  listing_id: string;
  slot: string;
  name: string;
  visitors: number;
  booked_at: string;
}

export interface EmiState {
  down_pct: number;
  tenure_years: number;
  lender: string;
}

export interface VisitState {
  listing_id: string | null;
  day: string | null;
  /** The part of the day the buyer asked for: its free slots are marked "suits you". */
  suits: "morning" | "afternoon" | "evening" | "any" | null;
  slot: string | null;
  name: string;
  visitors: number;
  /** The visitor's mobile number, typed by them only (X9): never sent to the agent,
   * never filled by it, kept in memory for this visit. */
  phone: string;
}

interface Store {
  filters: Filters;
  /** A card or pin the agent or the pointer is on. */
  focus: string | null;
  shortlist: string[];
  compare: string[];
  bookings: Booking[];
  emi: Record<string, EmiState>;
  emiOpen: string | null;
  visit: VisitState;
  /** The visit card just booked (shown on the listing page). */
  justBooked: string | null;
  lang: string;
  filtersOpen: boolean;
  mapOpen: boolean;

  setFilters: (f: Filters) => void;
  patchFilters: (f: Partial<Filters>) => void;
  setFocus: (id: string | null) => void;
  toggleShortlist: (id: string, on?: boolean) => void;
  toggleCompare: (id: string) => void;
  setCompare: (ids: string[]) => void;
  setEmi: (id: string, patch: Partial<EmiState>) => void;
  setEmiOpen: (id: string | null) => void;
  setVisit: (patch: Partial<VisitState>) => void;
  book: (b: Omit<Booking, "reference" | "booked_at">) => Booking;
  cancelBooking: (ref: string) => void;
  setLang: (tag: string) => void;
  setFiltersOpen: (v: boolean) => void;
  setMapOpen: (v: boolean) => void;
}

const SHORTLIST = "kosha-shortlist";
const BOOKINGS = "kosha-bookings";
const LANG = "kosha-lang";

const initialLang = () => {
  const saved = load<string>(LANG, PERSONA.default_language);
  return PERSONA.languages.some((l) => l.tag === saved) ? saved : PERSONA.default_language;
};

export const useStore = create<Store>((set, get) => ({
  filters: {},
  focus: null,
  shortlist: load<string[]>(SHORTLIST, []),
  compare: [],
  bookings: load<Booking[]>(BOOKINGS, []),
  emi: {},
  emiOpen: null,
  visit: { listing_id: null, day: null, suits: null, slot: null, name: "", visitors: 1, phone: "" },
  justBooked: null,
  lang: initialLang(),
  filtersOpen: false,
  mapOpen: false,

  setFilters: (f) => set({ filters: cleanFilters(f) }),
  patchFilters: (f) => set({ filters: cleanFilters({ ...get().filters, ...f }) }),
  setFocus: (focus) => set({ focus }),
  toggleShortlist: (id, on) => {
    const has = get().shortlist.includes(id);
    const want = on ?? !has;
    if (want === has) return;
    const shortlist = want ? [...get().shortlist, id] : get().shortlist.filter((x) => x !== id);
    save(SHORTLIST, shortlist);
    set({ shortlist });
  },
  toggleCompare: (id) => {
    const c = get().compare;
    set({ compare: c.includes(id) ? c.filter((x) => x !== id) : [...c, id].slice(-3) });
  },
  setCompare: (ids) => set({ compare: ids.slice(0, 3) }),
  setEmi: (id, patch) => set({ emi: { ...get().emi, [id]: { ...emiOf(get().emi, id), ...patch } } }),
  setEmiOpen: (emiOpen) => set({ emiOpen }),
  setVisit: (patch) => set({ visit: { ...get().visit, ...patch } }),
  book: (b) => {
    const booking: Booking = { ...b, reference: bookingRef(b.listing_id, b.slot), booked_at: new Date().toISOString() };
    const bookings = [...get().bookings.filter((x) => x.reference !== booking.reference), booking];
    save(BOOKINGS, bookings);
    set({ bookings, justBooked: booking.reference, visit: { ...get().visit, slot: null } });
    return booking;
  },
  cancelBooking: (ref) => {
    const bookings = get().bookings.filter((b) => b.reference !== ref);
    save(BOOKINGS, bookings);
    set({ bookings, justBooked: get().justBooked === ref ? null : get().justBooked });
  },
  setLang: (lang) => {
    save(LANG, lang);
    set({ lang });
  },
  setFiltersOpen: (filtersOpen) => set({ filtersOpen }),
  setMapOpen: (mapOpen) => set({ mapOpen }),
}));

export function emiOf(all: Record<string, EmiState>, id: string): EmiState {
  const l = getListing(id);
  const base: EmiState = {
    down_pct: EMI_DEFAULTS.down_pct,
    tenure_years: EMI_DEFAULTS.tenure_years,
    lender: EMI_DEFAULTS.lender,
  };
  return l ? { ...base, ...all[id] } : base;
}

/** Slot ids this browser booked with the same host as `listingId`: taken after. */
export function takenSlots(bookings: Booking[], listingId: string): Set<string> {
  const l = getListing(listingId);
  if (!l) return new Set();
  const key = hostKey(l);
  return new Set(bookings.filter((b) => { const o = getListing(b.listing_id); return o && hostKey(o) === key; }).map((b) => b.slot));
}

/** The current results, from the store's filters. */
export const useResults = () => {
  const filters = useStore((s) => s.filters);
  return search(filters);
};
