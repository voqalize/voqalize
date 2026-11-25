/**
 * The one store for what the shopper owns and what the listing shows. Every
 * click and every agent move writes here, through the same functions, so the
 * site works by hand and the voice layer only calls these. The wishlist, bag,
 * language, orders placed here, cancellations and returns persist in
 * localStorage (keys `fashio-*`); a private window just forgets.
 *
 * Page-local UI state (the gift finder, the kiosk, the selected order) lives in
 * the page's own small store next to it (`state/gifts.ts`, `state/kiosk.ts`,
 * `state/orders.ts`).
 */
import { create } from "zustand";
import { type Filters, cleanFilters, getProduct } from "../data/catalog";
import type { FitPref } from "../data/fit";
import { PERSONA } from "../data/persona";
import { type BagLine, type Order, POLICY, addDays, bagTotals, lineKey, todayIST } from "../data/shop";
import { load, save } from "./storage";

export interface FitPanel {
  open: boolean;
  height_cm?: number;
  usual_size?: string;
  fit?: FitPref;
  /** The pick shown on the panel (by the agent's `fit.recommend` or the panel's button). */
  pick?: { size: string; reason: string; wanted?: string };
}

interface Store {
  // Listing
  filters: Filters;
  filtersOpen: boolean;
  setFilters: (f: Filters) => void;
  patchFilters: (f: Partial<Filters>) => void;
  setFiltersOpen: (v: boolean) => void;

  // Product page (per product id)
  size: Record<number, string>;
  fit: Record<number, FitPanel>;
  sizeChart: { product_id: number; size?: string } | null;
  pickSize: (id: number, size: string | null) => void;
  setFit: (id: number, patch: Partial<FitPanel>) => void;
  openSizeChart: (id: number | null, size?: string) => void;

  // Wishlist and compare
  wishlist: number[];
  toggleWishlist: (id: number, on?: boolean) => void;
  compare: number[];
  setCompare: (ids: number[]) => void;
  toggleCompare: (id: number) => void;

  // Bag
  bag: BagLine[];
  /** A pulse for the header's bag icon after an add. */
  bagPulse: number;
  addToBag: (id: number, size: string, qty?: number) => void;
  setQty: (id: number, size: string, qty: number) => void;
  removeLine: (id: number, size: string) => void;
  setGift: (id: number, size: string, on: boolean, note?: string) => void;
  clearBag: () => void;

  // Orders placed, cancelled and returned in this browser
  placed: Order[];
  cancelled: string[];
  /** `<order id>|<product id>` → return reference. */
  returns: Record<string, string>;
  placeOrder: (o: Omit<Order, "id" | "placed" | "status" | "eta" | "events" | "courier" | "local">) => Order;
  cancelOrder: (id: string) => void;
  requestReturn: (orderId: string, productId: number, reference: string) => void;

  // Language (remembered across reloads; the next call and a redial start in it)
  lang: string;
  setLang: (tag: string) => void;
}

const K = {
  wishlist: "fashio-wishlist",
  bag: "fashio-bag",
  placed: "fashio-orders",
  cancelled: "fashio-cancelled",
  returns: "fashio-returns",
  lang: "fashio-lang",
};

const initialLang = () => {
  const saved = load<string>(K.lang, PERSONA.default_language);
  return PERSONA.languages.some((l) => l.tag === saved) ? saved : PERSONA.default_language;
};

export const useStore = create<Store>((set, get) => ({
  filters: {},
  filtersOpen: false,
  setFilters: (f) => set({ filters: cleanFilters(f) }),
  patchFilters: (f) => set({ filters: cleanFilters({ ...get().filters, ...f }) }),
  setFiltersOpen: (filtersOpen) => set({ filtersOpen }),

  size: {},
  fit: {},
  sizeChart: null,
  pickSize: (id, size) => {
    const next = { ...get().size };
    if (size === null) delete next[id];
    else next[id] = size;
    set({ size: next });
  },
  setFit: (id, patch) => set({ fit: { ...get().fit, [id]: { ...get().fit[id], ...patch, open: patch.open ?? get().fit[id]?.open ?? true } } }),
  openSizeChart: (id, size) => set({ sizeChart: id === null ? null : { product_id: id, size } }),

  wishlist: load<number[]>(K.wishlist, []),
  toggleWishlist: (id, on) => {
    const has = get().wishlist.includes(id);
    const want = on ?? !has;
    if (want === has) return;
    const wishlist = want ? [...get().wishlist, id] : get().wishlist.filter((x) => x !== id);
    save(K.wishlist, wishlist);
    set({ wishlist });
  },
  compare: [],
  setCompare: (ids) => set({ compare: ids.slice(0, 4) }),
  toggleCompare: (id) => {
    const c = get().compare;
    set({ compare: c.includes(id) ? c.filter((x) => x !== id) : [...c, id].slice(-4) });
  },

  bag: load<BagLine[]>(K.bag, []),
  bagPulse: 0,
  addToBag: (id, size, qty = 1) => {
    const key = lineKey(id, size);
    const bag = get().bag.some((l) => lineKey(l.product_id, l.size) === key)
      ? get().bag.map((l) => (lineKey(l.product_id, l.size) === key ? { ...l, qty: Math.min(l.qty + qty, 5) } : l))
      : [...get().bag, { product_id: id, size, qty: Math.min(qty, 5), gift: false, note: "" }];
    save(K.bag, bag);
    set({ bag, bagPulse: get().bagPulse + 1 });
  },
  setQty: (id, size, qty) => {
    const key = lineKey(id, size);
    const bag = qty <= 0 ? get().bag.filter((l) => lineKey(l.product_id, l.size) !== key) : get().bag.map((l) => (lineKey(l.product_id, l.size) === key ? { ...l, qty: Math.min(qty, 5) } : l));
    save(K.bag, bag);
    set({ bag });
  },
  removeLine: (id, size) => get().setQty(id, size, 0),
  setGift: (id, size, on, note) => {
    const key = lineKey(id, size);
    const bag = get().bag.map((l) => (lineKey(l.product_id, l.size) === key ? { ...l, gift: on, note: (note ?? l.note).slice(0, POLICY.gift_wrap.note_max) } : l));
    save(K.bag, bag);
    set({ bag });
  },
  clearBag: () => {
    save(K.bag, []);
    set({ bag: [] });
  },

  placed: load<Order[]>(K.placed, []),
  cancelled: load<string[]>(K.cancelled, []),
  returns: load<Record<string, string>>(K.returns, {}),
  placeOrder: (o) => {
    const today = todayIST();
    const id = `FSH-${49000 + get().placed.length + 1}`;
    const time = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" }).format(new Date());
    const order: Order = {
      ...o,
      id,
      placed: today,
      status: "placed",
      eta: addDays(today, POLICY.delivery.days_max),
      events: [{ date: today, time, status: "placed", text: "Order placed" }],
      courier: null,
      local: true,
    };
    const placed = [order, ...get().placed];
    save(K.placed, placed);
    set({ placed });
    return order;
  },
  cancelOrder: (id) => {
    if (get().cancelled.includes(id)) return;
    const cancelled = [...get().cancelled, id];
    save(K.cancelled, cancelled);
    set({ cancelled });
  },
  requestReturn: (orderId, productId, reference) => {
    const returns = { ...get().returns, [`${orderId}|${productId}`]: reference };
    save(K.returns, returns);
    set({ returns });
  },

  lang: initialLang(),
  setLang: (lang) => {
    save(K.lang, lang);
    set({ lang });
  },
}));

/** The bag's totals now (CONTRACT.md, Bag). */
export const totalsNow = () => bagTotals(useStore.getState().bag);

/** A bag line's product, or undefined when the catalogue does not have it (yet). */
export const lineProduct = (l: BagLine) => getProduct(l.product_id);
