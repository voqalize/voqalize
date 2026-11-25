/**
 * The catalogue: the index fetched once from the bucket (`catalog/v1/index.json`,
 * the same file as `demos/fashio/data/catalog.json`, which the brain reads), and
 * each product's detail fetched when its page opens. The search rule here is
 * the brain's (`backend/fashio.py` `search`), word for word: CONTRACT.md,
 * "Shared rules".
 */
import { create } from "zustand";
import { detailUrl, indexUrl } from "./assets";

export type Gender = "men" | "women" | "boys" | "girls" | "unisex";
export type Scale = "alpha" | "waist" | "uk" | "age" | "one";

export interface Product {
  id: number;
  name: string;
  brand: string;
  gender: Gender;
  type: string;
  colour: string;
  price: number;
  mrp: number;
  usage: string;
  season: string;
  year: number;
  /** [label, stock] in size order. */
  sizes: [string, number][];
  scale: Scale;
  rank: number;
  group?: number;
  attrs?: Record<string, string>;
  model?: string;
}

export interface TypeInfo {
  label: string;
  article: string;
  chart: Record<string, string> | null;
}

export interface Department {
  id: string;
  label: string;
  genders: Gender[];
  usage?: string;
  sections: { label: string; types: string[] }[];
}

export interface CatalogIndex {
  version: string;
  credit: { dataset: string; author: string; licence: string; source: string; url: string };
  count: number;
  types: Record<string, TypeInfo>;
  departments: Department[];
  brands: string[];
  colours: Record<string, string>;
  products: Product[];
}

export interface ProductDetail {
  id: number;
  article_number?: string;
  attributes: Record<string, string>;
  description: { heading: string; text: string }[];
  blurb?: string;
  similar?: number[];
  variants?: number[];
}

// ─── Loading ────────────────────────────────────────────────────────────────

interface CatalogState {
  index: CatalogIndex | null;
  byId: Map<number, Product>;
  error: string | null;
  details: Record<number, ProductDetail | "loading" | "missing">;
}

export const useCatalog = create<CatalogState>(() => ({ index: null, byId: new Map(), error: null, details: {} }));

let loading: Promise<CatalogIndex> | null = null;

/** Fetch the index once (later calls share the request). */
export function loadCatalog(): Promise<CatalogIndex> {
  if (loading) return loading;
  loading = (async () => {
    try {
      const res = await fetch(indexUrl());
      if (!res.ok) throw new Error(`catalogue ${res.status}`);
      return setIndex((await res.json()) as CatalogIndex);
    } catch (err) {
      // The bucket is unreachable (offline, a proxy missing): the same file,
      // shipped with the build as a lazy chunk, so the store still works.
      console.warn("Catalogue fetch failed, using the bundled copy:", err);
      const mod = await import("../../../data/catalog.json");
      return setIndex(mod.default as unknown as CatalogIndex);
    }
  })();
  return loading;
}

export function setIndex(index: CatalogIndex): CatalogIndex {
  const byId = new Map(index.products.map((p) => [p.id, p]));
  useCatalog.setState({ index, byId, error: null });
  return index;
}

export async function loadDetail(id: number): Promise<ProductDetail | null> {
  const have = useCatalog.getState().details[id];
  if (have && have !== "loading") return have === "missing" ? null : have;
  useCatalog.setState((s) => ({ details: { ...s.details, [id]: "loading" } }));
  try {
    const res = await fetch(detailUrl(id));
    if (!res.ok) throw new Error(String(res.status));
    const d = (await res.json()) as ProductDetail;
    useCatalog.setState((s) => ({ details: { ...s.details, [id]: d } }));
    return d;
  } catch {
    useCatalog.setState((s) => ({ details: { ...s.details, [id]: "missing" } }));
    return null;
  }
}

export const getProduct = (id: number | string): Product | undefined => useCatalog.getState().byId.get(Number(id));
export const index = (): CatalogIndex | null => useCatalog.getState().index;
export const typeLabel = (t: string): string => index()?.types[t]?.label ?? t;
export const department = (id: string | undefined): Department | undefined => index()?.departments.find((d) => d.id === id);

// ─── Facts about a product ──────────────────────────────────────────────────

export const discountPct = (p: Pick<Product, "price" | "mrp">): number => (p.mrp > p.price ? Math.round(((p.mrp - p.price) * 100) / p.mrp) : 0);
export const inStock = (p: Product, size: string): boolean => p.sizes.some(([l, n]) => l === size && n > 0);
export const stockOf = (p: Product, size: string): number => p.sizes.find(([l]) => l === size)?.[1] ?? 0;
export const anyStock = (p: Product): boolean => p.sizes.some(([, n]) => n > 0);
export const isOneSize = (p: Product): boolean => p.scale === "one";
/** The colour variants of a product (itself included), by `group`. */
export function variantsOf(p: Product): Product[] {
  if (!p.group) return [p];
  return (index()?.products ?? []).filter((q) => q.group === p.group);
}

/** ₹1,25,999: Indian grouping. */
export function inr(n: number): string {
  return `₹${Math.round(n).toLocaleString("en-IN")}`;
}

// ─── Search ─────────────────────────────────────────────────────────────────

export type Sort = "popular" | "price_asc" | "price_desc" | "discount" | "new";
export type Dept = "men" | "women" | "kids" | "boys" | "girls" | "ethnic" | "footwear" | "accessories" | "all";

export interface Filters {
  dept?: Dept;
  types?: string[];
  brands?: string[];
  colours?: string[];
  sizes?: string[];
  price_min?: number;
  price_max?: number;
  discount_min?: number;
  usage?: string[];
  seasons?: string[];
  query?: string;
  sort?: Sort;
}

/** The filter keys in sidebar order (the order a move rings them). */
export const FILTER_KEYS: (keyof Filters)[] = ["dept", "types", "brands", "colours", "sizes", "price_min", "price_max", "discount_min", "usage", "seasons", "query", "sort"];

/** Drop empty values, so two equal searches compare equal. */
export function cleanFilters(f: Filters): Filters {
  const out: Filters = {};
  for (const k of FILTER_KEYS) {
    const v = f[k];
    if (v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0)) continue;
    if (k === "dept" && v === "all") continue;
    if (k === "sort" && v === "popular") continue;
    (out as Record<string, unknown>)[k] = v;
  }
  return out;
}

const DEPT_GENDERS: Partial<Record<Dept, Gender[]>> = {
  men: ["men", "unisex"],
  women: ["women", "unisex"],
  kids: ["boys", "girls"],
  boys: ["boys"],
  girls: ["girls"],
};

function deptTypes(id: string): Set<string> {
  return new Set(department(id)?.sections.flatMap((s) => s.types) ?? []);
}

const lower = (xs?: string[]) => (xs ? new Set(xs.map((x) => x.toLowerCase())) : null);

export function matches(p: Product, f: Filters): boolean {
  if (f.dept && f.dept !== "all") {
    const genders = DEPT_GENDERS[f.dept];
    if (genders && !genders.includes(p.gender)) return false;
    if (f.dept === "ethnic" && p.usage !== "Ethnic") return false;
    if ((f.dept === "footwear" || f.dept === "accessories") && !deptTypes(f.dept).has(p.type)) return false;
  }
  if (f.types?.length && !f.types.includes(p.type)) return false;
  const brands = lower(f.brands);
  if (brands && brands.size && !brands.has(p.brand.toLowerCase())) return false;
  const colours = lower(f.colours);
  if (colours && colours.size && !colours.has(p.colour.toLowerCase())) return false;
  if (f.sizes?.length && !p.sizes.some(([l, n]) => n > 0 && f.sizes!.includes(l))) return false;
  if (f.price_min != null && p.price < f.price_min) return false;
  if (f.price_max != null && p.price > f.price_max) return false;
  if (f.discount_min != null && discountPct(p) < f.discount_min) return false;
  if (f.usage?.length && !f.usage.includes(p.usage)) return false;
  if (f.seasons?.length && !f.seasons.includes(p.season)) return false;
  if (f.query) {
    const hay = `${p.name} ${p.brand} ${p.colour} ${typeLabel(p.type)}`.toLowerCase();
    const words = f.query.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter((w) => w.length >= 2);
    if (!words.every((w) => hay.includes(w))) return false;
  }
  return true;
}

export function sortProducts(xs: Product[], sort: Sort = "popular"): Product[] {
  const by = (fn: (a: Product, b: Product) => number) => [...xs].sort((a, b) => fn(a, b) || a.rank - b.rank);
  switch (sort) {
    case "price_asc":
      return by((a, b) => a.price - b.price);
    case "price_desc":
      return by((a, b) => b.price - a.price);
    case "discount":
      return by((a, b) => discountPct(b) - discountPct(a));
    case "new":
      return by((a, b) => b.year - a.year);
    default:
      return by(() => 0);
  }
}

export function search(f: Filters, products: Product[] = index()?.products ?? []): Product[] {
  return sortProducts(
    products.filter((p) => matches(p, f)),
    f.sort,
  );
}

const SORT_LABEL: Record<Sort, string> = {
  popular: "popular first",
  price_asc: "price low to high",
  price_desc: "price high to low",
  discount: "biggest discount first",
  new: "newest first",
};

/** One line saying the search, for the brain and the page's heading. */
export function summarise(f: Filters): string {
  const parts: string[] = [];
  if (f.dept && f.dept !== "all") parts.push(department(f.dept)?.label ?? f.dept);
  if (f.types?.length) parts.push(f.types.map(typeLabel).join(" or "));
  if (f.colours?.length) parts.push(f.colours.join(" or "));
  if (f.brands?.length) parts.push(`by ${f.brands.join(" or ")}`);
  if (f.sizes?.length) parts.push(`size ${f.sizes.join(" or ")} in stock`);
  if (f.usage?.length) parts.push(f.usage.join(" or "));
  if (f.seasons?.length) parts.push(f.seasons.join(" or "));
  if (f.price_min != null && f.price_max != null) parts.push(`${inr(f.price_min)} to ${inr(f.price_max)}`);
  else if (f.price_max != null) parts.push(`under ${inr(f.price_max)}`);
  else if (f.price_min != null) parts.push(`over ${inr(f.price_min)}`);
  if (f.discount_min != null) parts.push(`${f.discount_min}% off or more`);
  if (f.query) parts.push(`"${f.query}"`);
  const what = parts.length ? parts.join(", ") : "everything";
  return f.sort && f.sort !== "popular" ? `${what}; ${SORT_LABEL[f.sort]}` : what;
}

// ─── Routes and facets (the listing's URL and its sidebar) ──────────────────

/**
 * The listing route for a search: `/shop/<dept>/<type>` when it is one
 * department and one type, `/shop/<dept>` for a department, else `/shop`,
 * with `?q=` for words. The rest of a search lives in the store only.
 */
export function routeFor(f: Filters): string {
  let path = "/shop";
  if (f.dept && f.dept !== "all") {
    path += `/${f.dept}`;
    if (f.types?.length === 1) path += `/${f.types[0]}`;
  }
  return f.query ? `${path}?q=${encodeURIComponent(f.query)}` : path;
}

const DEPTS: Dept[] = ["men", "women", "kids", "boys", "girls", "ethnic", "footwear", "accessories"];
export const isDept = (s: string | undefined): s is Dept => !!s && (DEPTS as string[]).includes(s);

/** The search a listing URL stands for, when someone opens it by hand. */
export function filtersFromRoute(dept?: string, type?: string, q?: string | null): Filters {
  const f: Filters = {};
  if (isDept(dept)) {
    f.dept = dept;
    if (type && /^[a-z0-9-]+$/.test(type)) f.types = [type];
  }
  if (q && q.trim()) f.query = q.trim();
  return f;
}

const ALPHA_ORDER = ["XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL"];
/** A sortable key for any size label: letters, then waists, then UK sizes, then kids' ages, then one size. */
export function sizeKey(label: string): number {
  const a = ALPHA_ORDER.indexOf(label);
  if (a >= 0) return a;
  if (/^\d+$/.test(label)) return 100 + Number(label);
  const uk = /^UK (\d+)$/.exec(label);
  if (uk) return 200 + Number(uk[1]);
  const age = /^(\d+)(?:-(\d+))?([YM])$/.exec(label);
  if (age) return 300 + (age[3] === "M" ? Number(age[1]) / 12 : Number(age[1]));
  return 900;
}

export interface Facet {
  value: string;
  count: number;
}

/**
 * The sidebar's options for one filter key: the values present among the
 * products that match every OTHER filter, with counts (the usual faceting:
 * ticking a brand never hides the other brands).
 */
export function facet(key: "types" | "brands" | "colours" | "sizes" | "usage" | "seasons", f: Filters, products: Product[] = index()?.products ?? []): Facet[] {
  const rest: Filters = { ...f, [key]: undefined };
  const counts = new Map<string, number>();
  for (const p of products) {
    if (!matches(p, rest)) continue;
    const values =
      key === "types" ? [p.type] : key === "brands" ? [p.brand] : key === "colours" ? [p.colour] : key === "usage" ? [p.usage] : key === "seasons" ? [p.season] : p.sizes.filter(([, n]) => n > 0).map(([l]) => l);
    for (const v of values) if (v && v !== "NA") counts.set(v, (counts.get(v) ?? 0) + 1);
  }
  const out = [...counts].map(([value, count]) => ({ value, count }));
  if (key === "sizes") return out.filter((x) => x.value !== "Onesize").sort((a, b) => sizeKey(a.value) - sizeKey(b.value));
  return out.sort((a, b) => b.count - a.count || a.value.localeCompare(b.value));
}

/** The catalogue's own spelling of a brand, colour or type the agent named (case-insensitive), or undefined. */
export function canonical(kind: "brands" | "colours" | "types", value: string): string | undefined {
  const ix = index();
  if (!ix) return undefined;
  const v = value.trim().toLowerCase();
  if (kind === "types") {
    if (ix.types[v]) return v;
    return Object.entries(ix.types).find(([, t]) => t.label.toLowerCase() === v)?.[0];
  }
  const pool = kind === "brands" ? ix.brands : Object.keys(ix.colours);
  return pool.find((x) => x.toLowerCase() === v);
}

/** A product's size label as the agent may say it: "m" → "M", "7" → "UK 7" for shoes, "one size" → "Onesize". */
export function sizeLabel(p: Product, said: string): string | undefined {
  const s = said.trim().toUpperCase().replace(/\s+/g, " ");
  const labels = p.sizes.map(([l]) => l);
  const hit = labels.find((l) => l.toUpperCase() === s);
  if (hit) return hit;
  if (p.scale === "uk") {
    const n = /(\d+)/.exec(s)?.[1];
    return n ? labels.find((l) => l === `UK ${n}`) : undefined;
  }
  if (p.scale === "one" && /ONE|FREE/.test(s)) return labels[0];
  if (s === "2XL") return labels.find((l) => l === "XXL");
  if (s === "XXXL") return labels.find((l) => l === "3XL");
  return undefined;
}

/**
 * A product page link that also works when opened cold (a QR code on a phone,
 * a reload on static hosting): `/p/?id=<id>` has a file behind it
 * (`dist/p/index.html`), and the page then moves to `/p/<id>`.
 */
export function shareUrl(id: number | string, origin: string = window.location.origin): string {
  return `${origin}${import.meta.env.BASE_URL}p/?id=${id}`;
}

/** The colour swatch's CSS background. */
export function swatch(colour: string): string {
  const hex = index()?.colours[colour];
  if (!hex) return "#ccc";
  if (hex === "conic") return "conic-gradient(#d6246e, #f2a400, #3c7a46, #2f5fb3, #6c3c8f, #d6246e)";
  return hex;
}
