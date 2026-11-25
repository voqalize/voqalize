/**
 * The in-store kiosk's state: the search (typed, a quick chip, or the agent's
 * `kiosk.search`), the product open full screen, which QR code is shown, the
 * kiosk shortlist (this screen only: the shopper takes it away by QR) and the
 * floor assistant call.
 */
import { create } from "zustand";
import { type Gender, type Product, index, matches, sortProducts, summarise, shareUrl, typeLabel } from "../data/catalog";

export interface KioskSearch {
  query?: string;
  genders?: string[];
  types?: string[];
  colours?: string[];
  sizes?: string[];
  price_max?: number;
  usage?: string[];
  /** The quick chip that set it, for the chip row's pressed state. */
  chip?: string;
}

const GENDERS: Record<string, Gender[]> = {
  men: ["men", "unisex"],
  women: ["women", "unisex"],
  kids: ["boys", "girls"],
  boys: ["boys"],
  girls: ["girls"],
  unisex: ["unisex"],
};
export const KIOSK_GENDERS = Object.keys(GENDERS);

export const isEmptySearch = (s: KioskSearch | null) => !s || !(s.query || s.genders?.length || s.types?.length || s.colours?.length || s.sizes?.length || s.price_max || s.usage?.length);

/** The kiosk's search over the whole catalogue, popular first. */
export function kioskSearch(s: KioskSearch, products: Product[] = index()?.products ?? []): Product[] {
  const genders = s.genders?.length ? new Set(s.genders.flatMap((g) => GENDERS[g.toLowerCase()] ?? [])) : null;
  const f = { types: s.types, colours: s.colours, sizes: s.sizes, price_max: s.price_max, usage: s.usage, query: s.query };
  return sortProducts(products.filter((p) => (!genders || genders.has(p.gender)) && matches(p, f)));
}

export function kioskSummary(s: KioskSearch | null): string {
  if (isEmptySearch(s)) return "the welcome screen";
  const head = s!.genders?.length ? `${s!.genders.join(" or ")}: ` : "";
  return head + summarise({ types: s!.types, colours: s!.colours, sizes: s!.sizes, price_max: s!.price_max, usage: s!.usage, query: s!.query });
}

/** The quick chips under the search bar. */
export const QUICK_CHIPS: { id: string; label: string; search: KioskSearch }[] = [
  { id: "kurtas", label: "Kurtas", search: { types: ["kurtas"] } },
  { id: "sneakers", label: "Sneakers", search: { types: ["casual-shoes", "sports-shoes"] } },
  { id: "watches", label: "Watches", search: { types: ["watches"] } },
  { id: "sarees", label: "Sarees", search: { types: ["sarees"] } },
  { id: "under999", label: "Under ₹999", search: { price_max: 999 } },
  { id: "handbags", label: "Handbags", search: { types: ["handbags"] } },
  { id: "ethnic", label: "Festive wear", search: { usage: ["Ethnic"] } },
];

export type QrTarget = { kind: "product"; id: number } | { kind: "shortlist" };

interface KioskStore {
  search: KioskSearch | null;
  /** What the search box shows (typed, or the agent's query). */
  typed: string;
  open: number | null;
  /** A big QR shown on its own (the shortlist's, or a product's from `kiosk.qr`). */
  qr: QrTarget | null;
  shortlist: number[];
  assistAt: number | null;
  setTyped: (t: string) => void;
  setSearch: (s: KioskSearch | null) => void;
  openProduct: (id: number | null) => void;
  showQr: (t: QrTarget | null) => void;
  toggleShortlist: (id: number, on?: boolean) => void;
  callAssistant: (on?: boolean) => void;
  home: () => void;
}

export const useKiosk = create<KioskStore>((set, get) => ({
  search: null,
  typed: "",
  open: null,
  qr: null,
  shortlist: [],
  assistAt: null,
  setTyped: (typed) => set({ typed }),
  setSearch: (search) => set({ search: isEmptySearch(search) ? null : search, typed: search?.query ?? "", open: null, qr: null }),
  openProduct: (open) => set({ open, qr: null }),
  showQr: (qr) => set({ qr }),
  toggleShortlist: (id, on) => {
    const has = get().shortlist.includes(id);
    const want = on ?? !has;
    if (want === has) return;
    set({ shortlist: want ? [...get().shortlist, id] : get().shortlist.filter((x) => x !== id) });
  },
  callAssistant: (on = true) => set({ assistAt: on ? Date.now() : null }),
  home: () => set({ search: null, typed: "", open: null, qr: null }),
}));

/** The absolute URL of a product page, for the QR code. */
/** The product page on the shopper's phone: the cold-openable share link (a file exists behind it on static hosting). */
export const productUrl = (id: number) => shareUrl(id);
/** The absolute URL of the wishlist page with these products (`/wishlist?ids=a,b,c`). */
export const shortlistUrl = (ids: number[]) => `${window.location.origin}${import.meta.env.BASE_URL}wishlist?ids=${ids.join(",")}`;

export const describe = (p: Product) => `${p.brand} ${typeLabel(p.type).toLowerCase()}, ₹${p.price.toLocaleString("en-IN")}`;
