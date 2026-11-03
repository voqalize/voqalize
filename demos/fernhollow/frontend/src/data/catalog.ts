import raw from "virtual:catalog";
import type { Category, Product, RoomId, Variant } from "./types";

export type { Category, Product, RoomId, Variant } from "./types";

export const products: Product[] = raw.products;
export const categories: Category[] = raw.categories;

const byId = new Map(products.map((p) => [p.id, p]));
const bySlug = new Map(categories.map((c) => [c.slug, c]));

export const getProduct = (id: string | undefined | null): Product | undefined => (id ? byId.get(id) : undefined);
export const getCategory = (slug: string | undefined): Category | undefined => (slug ? bySlug.get(slug) : undefined);

/** Editorial room copy. Authored store voice, never product facts. */
export const ROOMS: { id: RoomId; name: string; short: string; line: string; cover: string }[] = [
  {
    id: "living",
    name: "Living room",
    short: "Living",
    line: "Sofas you sink into, tables that gather the day, and light for long evenings.",
    cover: "",
  },
  {
    id: "dining",
    name: "Dining",
    short: "Dining",
    line: "Tables, chairs and the pieces that set them, for slow dinners and loud ones.",
    cover: "",
  },
  {
    id: "bedroom",
    name: "Bedroom",
    short: "Bedroom",
    line: "Frames, linens and soft light for the quietest room in the house.",
    cover: "",
  },
  {
    id: "home-office",
    name: "Home office",
    short: "Office",
    line: "Desks, chairs and shelving that make a corner feel like a place to think.",
    cover: "",
  },
  {
    id: "bath",
    name: "Bath",
    short: "Bath",
    line: "Towels and mats with weight to them.",
    cover: "",
  },
  {
    id: "kitchen",
    name: "Kitchen",
    short: "Kitchen",
    line: "Cookware and storage that earn their place on the counter.",
    cover: "",
  },
  {
    id: "decor",
    name: "Decor",
    short: "Decor",
    line: "Vases, frames, candles and baskets: the finishing layer.",
    cover: "",
  },
];

/** Cover product per room — chosen by eye from the catalog, ids only. */
const ROOM_COVERS: Record<RoomId, string> = {
  living: "",
  dining: "",
  bedroom: "",
  "home-office": "",
  bath: "",
  kitchen: "",
  decor: "",
};

export const getRoom = (id: string | undefined) => ROOMS.find((r) => r.id === id);
export const roomName = (id: string) => getRoom(id)?.name ?? id;
export const categoriesIn = (room: RoomId) => categories.filter((c) => c.room === room);
export const productsIn = (room: RoomId) => products.filter((p) => p.room === room);
export const productsInCategory = (slug: string) => products.filter((p) => p.categorySlug === slug);

/** A stable pseudo-random number per string, so "featured" orders are deterministic. */
export function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export function roomCover(room: RoomId): Product {
  const chosen = getProduct(ROOM_COVERS[room]);
  if (chosen) return chosen;
  const list = productsIn(room).filter((p) => p.priceMax >= 120);
  const pool = list.length ? list : productsIn(room);
  return [...pool].sort((a, b) => hash(`cover${a.id}`) - hash(`cover${b.id}`))[0];
}

export const collectionName = (slug: string) =>
  slug
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");

export const imgUrl = (file: string, size: 400 | 1000 = 400) => `${import.meta.env.BASE_URL}img/${file}-${size}.webp`;

const whole = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const cents = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });
export const money = (n: number) => (Number.isInteger(n) ? whole.format(n) : cents.format(n));

export const defaultVariant = (p: Product): Variant => p.variants[0];
export const getVariant = (p: Product, id?: string | null): Variant =>
  p.variants.find((v) => v.id === id) ?? defaultVariant(p);

export function variantForOptions(p: Product, chosen: Record<string, string>): Variant | undefined {
  return p.variants.find((v) => Object.entries(chosen).every(([k, val]) => v.options[k] === val));
}

export const savePct = (price: number, compare: number | null | undefined) =>
  compare && compare > price ? Math.round((1 - price / compare) * 100) : 0;

/** The best saving any variant of a product offers, for badges. */
export function bestSaving(p: Product): { pct: number; compare: number | null; price: number } {
  let best = { pct: 0, compare: null as number | null, price: p.priceMin };
  for (const v of p.variants) {
    const pct = savePct(v.price, v.compareAtPrice);
    if (pct > best.pct) best = { pct, compare: v.compareAtPrice, price: v.price };
  }
  return best;
}

export const optionSummary = (p: Product) =>
  p.options
    .map((o) => `${o.values.length} ${o.name.toLowerCase()}${o.values.length === 1 ? "" : "s"}`)
    .join(", ");

// ── Search ────────────────────────────────────────────────────────────────

const tokenize = (s: string) =>
  s
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9\s&-]/g, " ")
    .split(/[\s-]+/)
    .filter(Boolean);

interface Indexed {
  p: Product;
  title: string;
  body: string;
}
const index: Indexed[] = products.map((p) => ({
  p,
  title: `${p.title} ${p.category}`.toLowerCase(),
  body: [p.intro, ...p.highlights, ...p.options.flatMap((o) => [o.name, ...o.values]), roomName(p.room), ...p.collections.map(collectionName)]
    .join(" ")
    .toLowerCase(),
}));

const stem = (t: string) => (t.length > 3 && t.endsWith("s") ? t.slice(0, -1) : t);

/** Text score of a product for a query, 0 when any term is missing. */
export function textScore(p: Product, q: string): number {
  const terms = tokenize(q).map(stem);
  if (!terms.length) return 1;
  const row = index[products.indexOf(p)] ?? { title: p.title.toLowerCase(), body: "" };
  let score = 0;
  for (const t of terms) {
    if (row.title.includes(t)) score += 3;
    else if (row.body.includes(t)) score += 1;
    else return 0;
  }
  return score;
}

export function search(q: string, pool: Product[] = products): Product[] {
  const scored = pool.map((p) => ({ p, s: textScore(p, q) })).filter((x) => x.s > 0);
  return scored.sort((a, b) => b.s - a.s || featuredRank(a.p) - featuredRank(b.p)).map((x) => x.p);
}

// ── Listing: facets, filters, sort ────────────────────────────────────────

export function featuredRank(p: Product): number {
  // Photographed in more than one setting first, then a stable shuffle so the
  // categories interleave rather than arrive in alphabetical blocks.
  return (p.images.length > 1 ? 0 : 1) * 2 ** 32 + hash(`f${p.id}`);
}

export type SortKey = "featured" | "price-asc" | "price-desc" | "sale";
export const SORTS: { key: SortKey; label: string }[] = [
  { key: "featured", label: "Featured" },
  { key: "price-asc", label: "Price, low to high" },
  { key: "price-desc", label: "Price, high to low" },
  { key: "sale", label: "On sale first" },
];

export function sortProducts(list: Product[], key: SortKey): Product[] {
  const out = [...list];
  switch (key) {
    case "price-asc":
      return out.sort((a, b) => a.priceMin - b.priceMin);
    case "price-desc":
      return out.sort((a, b) => b.priceMin - a.priceMin);
    case "sale":
      return out.sort((a, b) => bestSaving(b).pct - bestSaving(a).pct || featuredRank(a) - featuredRank(b));
    default:
      return out.sort((a, b) => featuredRank(a) - featuredRank(b));
  }
}

/** Option facets present in a set of products: { Finish: ["Oak", …], … }. */
/** The rail's groups for `list`. `keep` (selected "Group:value" keys) stay
 *  listed even outside a taste group's top few, so a tick is always visible. */
export function facets(list: Product[], keep: string[] = []): { name: string; values: { value: string; count: number }[] }[] {
  const map = new Map<string, Map<string, number>>();
  for (const p of list)
    for (const o of p.options) {
      const m = map.get(o.name) ?? new Map<string, number>();
      for (const v of o.values) m.set(v, (m.get(v) ?? 0) + 1);
      map.set(o.name, m);
    }
  const ORDER = ["Material", "Finish", "Fabric", "Frame", "Color", "Style", "Size", "Height", "Weight"];
  const byCount = (m: Map<string, number>) =>
    [...m.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([value, count]) => ({ value, count }));
  // The brain's words first — they are what Emily asks about — the most
  // common few of each, so the rail stays short.
  const taste = (Object.keys(TASTE_GROUPS) as TasteGroup[]).flatMap((name) => {
    const m = new Map<string, number>();
    for (const p of list) for (const w of p.taste[TASTE_GROUPS[name]]) m.set(w, (m.get(w) ?? 0) + 1);
    const all = byCount(m);
    const kept = new Set(keep.filter((k) => splitOpt(k)[0] === name).map((k) => splitOpt(k)[1]));
    const values = all.filter((v, i) => i < 8 || kept.has(v.value));
    return values.length > 1 || kept.size ? [{ name, values }] : [];
  });
  const options = [...map.entries()]
    .sort((a, b) => ORDER.indexOf(a[0]) - ORDER.indexOf(b[0]))
    .map(([name, m]) => ({ name, values: byCount(m) }));
  return [...taste, ...options];
}

export interface ListingFilters {
  q: string;
  min: number | null;
  max: number | null;
  sale: boolean;
  category: string | null;
  /** "Finish:Oak" style keys. */
  opts: string[];
}

/**
 * The sidebar groups that filter by the brain's words rather than by a
 * product's options: what Emily asks about ("neutral", "oak", "minimalist")
 * is ticked here, on the listing in front, rather than on a page of its own.
 * "Feel", because a product option is already called "Style".
 */
export const TASTE_GROUPS = { Colour: "colours", Feel: "styles", "Made of": "materials" } as const;
export type TasteGroup = keyof typeof TASTE_GROUPS;
export const isTasteGroup = (name: string): name is TasteGroup => name in TASTE_GROUPS;
/** The group a brain dimension is ticked under. */
export const TASTE_GROUP_OF: Record<keyof Product["taste"], TasteGroup> = {
  colours: "Colour",
  styles: "Feel",
  materials: "Made of",
};

export function applyListingFilters(list: Product[], f: ListingFilters): Product[] {
  const byName = new Map<string, Set<string>>();
  for (const key of f.opts) {
    const [name, value] = splitOpt(key);
    const set = byName.get(name) ?? new Set();
    set.add(value);
    byName.set(name, set);
  }
  return list.filter((p) => {
    if (f.category && p.categorySlug !== f.category) return false;
    if (f.sale && !p.onSale) return false;
    if (f.min != null && p.priceMax < f.min) return false;
    if (f.max != null && p.priceMin > f.max) return false;
    for (const [name, values] of byName) {
      if (isTasteGroup(name)) {
        if (!p.taste[TASTE_GROUPS[name]].some((w) => values.has(w))) return false;
        continue;
      }
      const o = p.options.find((x) => x.name === name);
      if (!o || !o.values.some((v) => values.has(v))) return false;
    }
    if (f.q && textScore(p, f.q) === 0) return false;
    return true;
  });
}

export const splitOpt = (key: string): [string, string] => {
  const i = key.indexOf(":");
  return [key.slice(0, i), key.slice(i + 1)];
};

/** Price bands that make sense for a list (quartiles, rounded). */
export function priceBands(list: Product[]): { label: string; min: number | null; max: number | null }[] {
  if (list.length < 6) return [];
  const prices = list.map((p) => p.priceMin).sort((a, b) => a - b);
  const q = (x: number) => prices[Math.floor((prices.length - 1) * x)];
  const round = (n: number) => (n < 100 ? Math.round(n / 10) * 10 : n < 1000 ? Math.round(n / 50) * 50 : Math.round(n / 250) * 250);
  const a = round(q(0.33));
  const b = round(q(0.66));
  if (!(a > 0 && b > a)) return [];
  return [
    { label: `Under ${money(a)}`, min: null, max: a },
    { label: `${money(a)} – ${money(b)}`, min: a, max: b },
    { label: `Over ${money(b)}`, min: b, max: null },
  ];
}

// ── Contract filters (materials / colours / styles are words) ─────────────

export interface ContractFilters {
  room?: string | null;
  category?: string | null;
  materials?: string[];
  colours?: string[];
  styles?: string[];
  price_min?: number | null;
  price_max?: number | null;
  on_sale?: boolean | null;
}

/** A local reading of the brain's filters, used when the visitor removes a chip by hand. */
export function matchContractFilters(f: ContractFilters): Product[] {
  const words = [...(f.materials ?? []), ...(f.colours ?? []), ...(f.styles ?? [])];
  return products.filter((p) => {
    if (f.room && p.room !== f.room) return false;
    if (f.category && p.categorySlug !== f.category) return false;
    if (f.on_sale && !p.onSale) return false;
    if (f.price_min != null && p.priceMax < f.price_min) return false;
    if (f.price_max != null && p.priceMin > f.price_max) return false;
    return words.every((w) => textScore(p, w) > 0);
  });
}

// ── Related rails (deterministic, catalog fields only) ────────────────────

export function moreFromRoom(p: Product, n = 8): Product[] {
  const others = productsIn(p.room).filter((x) => x.id !== p.id && x.categorySlug !== p.categorySlug);
  // One per category first, so the rail reads as a room rather than a shelf.
  const seen = new Set<string>();
  const sorted = [...others].sort((a, b) => hash(p.id + a.id) - hash(p.id + b.id));
  const first: Product[] = [];
  const rest: Product[] = [];
  for (const x of sorted) (seen.has(x.categorySlug) ? rest : (seen.add(x.categorySlug), first)).push(x);
  return [...first, ...rest].slice(0, n);
}

export function sameCollection(p: Product, n = 8): Product[] {
  const c = p.collections[0];
  return products
    .filter((x) => x.id !== p.id && x.collections.includes(c))
    .sort((a, b) => Number(a.categorySlug === p.categorySlug) - Number(b.categorySlug === p.categorySlug) || hash(p.id + a.id) - hash(p.id + b.id))
    .slice(0, n);
}

export function lookAlikes(p: Product, n = 6): Product[] {
  return productsInCategory(p.categorySlug)
    .filter((x) => x.id !== p.id)
    .sort((a, b) => Math.abs(a.priceMin - p.priceMin) - Math.abs(b.priceMin - p.priceMin))
    .slice(0, n);
}

/** Plain differences between two products, from catalog fields only. */
export function differences(anchor: Product, other: Product): string[] {
  const out: string[] = [];
  const d = other.priceMin - anchor.priceMin;
  if (Math.abs(d) >= 1) out.push(d < 0 ? `${money(Math.abs(d))} less` : `${money(d)} more`);
  if (other.onSale && !anchor.onSale) out.push("On sale");
  for (const o of other.options) {
    const mine = anchor.options.find((x) => x.name === o.name);
    const fresh = o.values.filter((v) => !mine?.values.includes(v));
    if (fresh.length) out.push(`In ${fresh.slice(0, 2).join(" or ")}`);
  }
  return out.slice(0, 3);
}

export const productsByIds = (ids: string[]) => ids.map((id) => byId.get(id)).filter((p): p is Product => !!p);
