/**
 * A listing page's filter rail, as one typed definition (CONTRACT.md v5).
 *
 * Every facet has a kind, and the kind decides everything else: how the rail
 * draws it, how it reads and writes the URL, how Emily's moves press it, and
 * how `listing_viewed` describes it. A new facet in the catalog's options needs
 * no new code; it is an `options` facet like the rest.
 *
 * - `options`: values to tick (Category, Material, Finish, Fabric, Style…).
 * - `toggle`: one switch (On sale).
 * - `bands`: labelled ranges with numeric bounds (Price), plus free min / max.
 * - `range`: a free min / max with no bands (Price on a page too small for bands).
 */
import { type Product, categories, facets as optionFacets, getCategory, priceBands } from "./catalog";

export type FacetKind = "options" | "toggle" | "bands" | "range";
export interface Band {
  label: string;
  min: number | null;
  max: number | null;
}
type Mut = (n: URLSearchParams) => void;

export interface RailFacet {
  name: string;
  kind: FacetKind;
  /** options: each value with how many pieces carry it. */
  values?: { value: string; count: number }[];
  /** options: more than one value may be on. */
  multi?: boolean;
  /** bands: the labelled ranges. */
  bands?: Band[];
  /** toggle: how many pieces it keeps. */
  count?: number;
  /** What is on: option values, [name] for a toggle, the band label for a band. */
  active: string[];
  /** bands / range: the bounds in force. */
  min: number | null;
  max: number | null;
  /** The URL change a click on `value` makes (options, toggle, bands by label). */
  toggle(value: string): Mut;
  /** bands / range: set the bounds. */
  setRange(min: number | null, max: number | null): Mut;
  /** Take this facet off. */
  clear(): Mut;
}

const num = (sp: URLSearchParams, k: string) => {
  const v = sp.get(k);
  return v != null && v !== "" && !Number.isNaN(Number(v)) ? Number(v) : null;
};
const setOrDelete = (n: URLSearchParams, k: string, v: number | null) => (v == null ? n.delete(k) : n.set(k, String(v)));

/** The rail for these pieces, in the order it is drawn, with the URL's state. */
export function railModel(scoped: Product[], sp: URLSearchParams): RailFacet[] {
  const out: RailFacet[] = [];
  const none = () => () => {};

  // Category: one at a time, by the category's name, in the `cat` param.
  const cats = [...new Set(scoped.map((p) => p.categorySlug))].map((s) => getCategory(s)!).filter(Boolean);
  if (cats.length > 1) {
    const on = getCategory(sp.get("cat") ?? undefined)?.name;
    const slugOf = (name: string) => categories.find((c) => c.name === name)?.slug ?? name;
    out.push({
      name: "Category",
      kind: "options",
      multi: false,
      values: cats.map((c) => ({ value: c.name, count: scoped.filter((p) => p.categorySlug === c.slug).length })),
      active: on ? [on] : [],
      min: null,
      max: null,
      toggle: (name) => (n) => (n.get("cat") === slugOf(name) ? n.delete("cat") : n.set("cat", slugOf(name))),
      setRange: none,
      clear: () => (n) => n.delete("cat"),
    });
  }

  // Price: bands when there are enough pieces to band, else a free range; `min` / `max`.
  const bands = priceBands(scoped);
  const min = num(sp, "min");
  const max = num(sp, "max");
  const setRange = (lo: number | null, hi: number | null): Mut => (n) => {
    setOrDelete(n, "min", lo);
    setOrDelete(n, "max", hi);
  };
  out.push({
    name: "Price",
    kind: bands.length ? "bands" : "range",
    ...(bands.length ? { bands } : {}),
    active: bands.filter((b) => b.min === min && b.max === max).map((b) => b.label),
    min,
    max,
    toggle: (label) => {
      const b = bands.find((x) => x.label === label);
      return (n) => {
        const on = b && num(n, "min") === b.min && num(n, "max") === b.max;
        setRange(on || !b ? null : b.min, on || !b ? null : b.max)(n);
      };
    },
    setRange,
    clear: () => setRange(null, null),
  });

  // On sale: a switch, `sale=1`.
  const saleCount = scoped.filter((p) => p.onSale).length;
  if (saleCount) {
    out.push({
      name: "On sale",
      kind: "toggle",
      count: saleCount,
      active: sp.get("sale") === "1" ? ["On sale"] : [],
      min: null,
      max: null,
      toggle: () => (n) => (n.get("sale") === "1" ? n.delete("sale") : n.set("sale", "1")),
      setRange: none,
      clear: () => (n) => n.delete("sale"),
    });
  }

  // Every option the pieces carry: ticks, several at once, `opt=<Name>:<Value>`.
  const opts = sp.getAll("opt");
  for (const g of optionFacets(scoped)) {
    const key = (v: string) => `${g.name}:${v}`;
    out.push({
      name: g.name,
      kind: "options",
      multi: true,
      values: g.values,
      active: g.values.map((v) => v.value).filter((v) => opts.includes(key(v))),
      min: null,
      max: null,
      toggle: (v) => (n) => {
        const all = n.getAll("opt");
        n.delete("opt");
        (all.includes(key(v)) ? all.filter((x) => x !== key(v)) : [...all, key(v)]).forEach((x) => n.append("opt", x));
      },
      setRange: none,
      clear: () => (n) => {
        const keep = n.getAll("opt").filter((x) => !x.startsWith(`${g.name}:`));
        n.delete("opt");
        keep.forEach((x) => n.append("opt", x));
      },
    });
  }
  return out;
}

/** The facet's description for the brain: its kind and its labels, nothing else. */
export function describeFacet(f: RailFacet) {
  const d: Record<string, unknown> = { name: f.name, kind: f.kind };
  if (f.kind === "options") {
    d.values = f.values?.map((v) => v.value) ?? [];
    d.multi = !!f.multi;
  }
  if (f.kind === "bands") d.bands = f.bands?.map((b) => ({ label: b.label, ...(b.min != null ? { min: b.min } : {}), ...(b.max != null ? { max: b.max } : {}) }));
  if (f.kind === "bands" || f.kind === "range") {
    if (f.min != null) d.min = f.min;
    if (f.max != null) d.max = f.max;
  }
  if (f.active.length) d.active = f.kind === "toggle" ? true : f.active;
  return d as {
    name: string;
    kind: FacetKind;
    values?: string[];
    multi?: boolean;
    bands?: { label: string; min?: number; max?: number }[];
    min?: number;
    max?: number;
    active?: string[] | true;
  };
}

/** The value a facet's option is called by on the page (`data-stage-part`). */
export const partOf = (f: RailFacet, value: string) => `${f.name}:${value}`;
