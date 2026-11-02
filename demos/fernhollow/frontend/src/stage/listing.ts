/**
 * Emily filters the page you are on (CONTRACT.md v5). These are the listing
 * page's Stage performers. They are generic over the rail's facet kinds
 * (src/data/rail.ts) and know nothing of Price, Dining or any one facet.
 *
 * Each one finds the rail's own control (`data-stage-part="<Facet>:<Value>"`,
 * or `data-stage-thing="range:<Facet>"` for a free range), rings it and then
 * presses it the way a click does, so the URL, the grid and the count change
 * through the same handler as a shopper's tap. Each answers in one line, and
 * something this page does not offer is refused with that facet's own values.
 */
import type { MoveContext } from "@voqalize/stage";
import { fold } from "@voqalize/stage";
import { SORTS } from "../data/catalog";
import { type Band, type RailFacet, partOf } from "../data/rail";

type Mut = (n: URLSearchParams) => void;

/** What the page hands its performers. */
export interface ListingApi {
  facets: RailFacet[];
  /** The count the grid would show after this URL change, without making it. */
  countAfter(mut: Mut): number;
  /** Make a URL change, as the rail's own handlers do. */
  apply(mut: Mut): void;
  setSort(key: string): void;
  clearAll(): void;
  /** The phone's filter sheet: open it so a ring is seen, close it after. */
  openSheet(): void;
  closeSheet(): void;
  sheetOpen(): boolean;
}

const pieces = (n: number) => `${n} ${n === 1 ? "piece" : "pieces"}`;
const labelsOf = (f: RailFacet): string[] =>
  f.kind === "options" ? (f.values ?? []).map((v) => v.value) : f.kind === "bands" ? (f.bands ?? []).map((b) => b.label) : f.kind === "toggle" ? [f.name] : [];

function facetOf(api: ListingApi, said: string, c: MoveContext, kinds?: RailFacet["kind"][]): RailFacet {
  const pool = kinds ? api.facets.filter((f) => kinds.includes(f.kind)) : api.facets;
  const want = fold(said.trim());
  return (
    pool.find((f) => fold(f.name) === want) ??
    c.refuse("facet", `this page filters by ${pool.map((f) => f.name).join(", ")}`, pool.map((f) => f.name))
  );
}

function optionOf(f: RailFacet, said: string): string | null {
  const options = labelsOf(f);
  const want = fold(said.trim());
  return options.find((v) => fold(v) === want) ?? options.find((v) => fold(v).startsWith(want) && want.length >= 3) ?? null;
}

/** A band by its label as said ("under $300", "300-400", "over 400"), or null. */
function bandOf(f: RailFacet, said: string): Band | null {
  const bands = f.bands ?? [];
  const norm = (s: string) => fold(s).replace(/[\s$,]/g, "").replace(/[–—-]|to/g, "-");
  const byLabel = bands.find((b) => norm(b.label) === norm(said));
  if (byLabel) return byLabel;
  const nums = (said.match(/\d[\d,]*/g) ?? []).map((n) => Number(n.replace(/,/g, "")));
  if (!nums.length) return null;
  const under = /under|below|less|up to|max/i.test(said);
  const over = /over|above|more|from|min/i.test(said);
  return (
    bands.find((b) =>
      nums.length >= 2 ? b.min === nums[0] && b.max === nums[1] : under ? b.min == null && b.max === nums[0] : over ? b.max == null && b.min === nums[0] : false,
    ) ?? null
  );
}

/** The bands a range takes in (touching a band only at its edge does not count). */
const bandsCovering = (f: RailFacet, lo: number | null, hi: number | null) =>
  (f.bands ?? []).filter((b) => (b.min ?? 0) < (hi ?? Number.POSITIVE_INFINITY) && (b.max ?? Number.POSITIVE_INFINITY) > (lo ?? 0));

const part = (key: string) =>
  [...document.querySelectorAll(`[data-stage-part="${CSS.escape(key)}"]`)].find((el) => el.closest(".rail-filters")) ?? null;
const rangeControl = (f: RailFacet) => document.querySelector(`.rail-filters [data-stage-thing="${CSS.escape(`range:${f.name}`)}"]`);

async function appear<T extends Element>(find: () => T | null, ms = 900): Promise<T | null> {
  const end = Date.now() + ms;
  for (;;) {
    const el = find();
    if (el || Date.now() > end) return el;
    await new Promise((r) => setTimeout(r, 25));
  }
}

/** Is the rail on screen? On a phone it lives in a sheet. */
const railShown = () => {
  const rail = document.querySelector(".rail-filters");
  return !!rail && getComputedStyle(rail).display !== "none";
};

/** Bring the rail up (the sheet on a phone), run `fn`, and put the sheet away again. */
async function onRail<T>(api: ListingApi, c: MoveContext, fn: () => Promise<T>): Promise<T> {
  const opened = !railShown() && !api.sheetOpen();
  if (opened) {
    api.openSheet();
    await appear(() => (railShown() ? document.body : null));
  }
  try {
    return await fn();
  } finally {
    if (opened)
      c.after(async () => {
        await c.beat(700);
        api.closeSheet();
      });
  }
}

async function reach(c: MoveContext, el: Element | Element[], label: string) {
  const first = Array.isArray(el) ? el[0] : el;
  // The rail scrolls on its own (sticky on a wide screen, a sheet on a phone).
  first.scrollIntoView({ block: "center" });
  await c.scrollTo(first);
  await c.ring(el, label);
}

/** Ring an option's control, then press it as a click does. */
async function press(c: MoveContext, el: Element, label: string) {
  await reach(c, el, label);
  const input = el.querySelector("input") ?? (el instanceof HTMLButtonElement ? el : null);
  (input as HTMLElement | null)?.click();
}

export function listingPerformers(api: ListingApi) {
  /** Press one option, toggle or band of a facet, as a click on it does. */
  const pressValue = (f: RailFacet, value: string, c: MoveContext, turnOn: boolean) =>
    onRail(api, c, async () => {
      const el = (await appear(() => part(partOf(f, value)))) ?? c.refuse("value", `${f.name}: ${value} is not on screen`, labelsOf(f));
      const count = api.countAfter(f.toggle(value));
      await press(c, el, f.kind === "toggle" ? f.name : `${f.name}: ${value}`);
      const what = f.kind === "toggle" ? f.name : `${f.name}: ${value}`;
      return `${what} ${turnOn ? "on" : "off"} — ${pieces(count)}`;
    });

  /** Set a bands or range facet to [lo, hi]: the band's own chip when one is exactly that. */
  const setRange = async (f: RailFacet, lo: number | null, hi: number | null, c: MoveContext) => {
    if ((lo != null && Number.isNaN(lo)) || (hi != null && Number.isNaN(hi))) c.refuse("min", "say the bounds as numbers");
    if (lo != null && hi != null && lo > hi) c.refuse("max", `the upper bound is below the lower one, ${lo}`);
    if (lo == null && hi == null) {
      if (!f.active.length && f.min == null && f.max == null) return `${f.name} is not set — ${pieces(api.countAfter(() => {}))}`;
      const el = rangeControl(f) ?? part(partOf(f, f.active[0] ?? ""));
      if (el) await reach(c, el, f.name);
      const count = api.countAfter(f.clear());
      api.apply(f.clear());
      return `${f.name} off — ${pieces(count)}`;
    }
    if (f.kind === "bands") {
      const exact = (f.bands ?? []).find((b) => b.min === lo && b.max === hi);
      if (exact) {
        if (f.active.includes(exact.label)) return `${f.name}: ${exact.label} is already on — ${pieces(api.countAfter(() => {}))}`;
        return pressValue(f, exact.label, c, true);
      }
      const covered = bandsCovering(f, lo, hi);
      const count = api.countAfter(f.setRange(lo, hi));
      if (!covered.length || count === 0) c.refuse(hi != null ? "max" : "min", `${f.name} here is ${labelsOf(f).join(", ")}`, labelsOf(f));
      // A range across bands: ring each band it takes in, then set the range itself.
      return onRail(api, c, async () => {
        const els = covered.map((b) => part(partOf(f, b.label))).filter((e): e is Element => !!e);
        if (els.length) await reach(c, els, covered.map((b) => b.label).join(" + "));
        api.apply(f.setRange(lo, hi));
        return `${f.name}: ${covered.map((b) => b.label).join(" and ")} on — ${pieces(count)}`;
      });
    }
    // A free range.
    return onRail(api, c, async () => {
      const el = (await appear(() => rangeControl(f))) ?? c.refuse("facet", `${f.name} is not on screen`);
      await reach(c, el, f.name);
      const count = api.countAfter(f.setRange(lo, hi));
      api.apply(f.setRange(lo, hi));
      const range = lo != null && hi != null ? `${lo}–${hi}` : hi != null ? `up to ${hi}` : `from ${lo}`;
      return `${f.name} ${range} — ${pieces(count)}`;
    });
  };

  const bound = (v: unknown) => (v == null || v === "" ? null : Math.round(Number(String(v).replace(/[$,\s]/g, ""))));
  const rangeFacets: RailFacet["kind"][] = ["bands", "range"];

  return {
    "listing.filter": async ({ facet, value }: { facet: string; value: string }, c: MoveContext) => {
      const f = facetOf(api, facet, c);
      if (f.kind === "range") c.refuse("facet", `${f.name} takes a range: use listing.range`);
      if (f.kind === "toggle") {
        if (f.active.length) return `${f.name} is already on — ${pieces(api.countAfter(() => {}))}`;
        return pressValue(f, f.name, c, true);
      }
      const v =
        (f.kind === "bands" ? bandOf(f, value)?.label : optionOf(f, value)) ??
        c.refuse("value", `${f.name} here is ${labelsOf(f).join(", ")}`, labelsOf(f));
      if (f.active.includes(v)) return `${f.name}: ${v} is already on — ${pieces(api.countAfter(() => {}))}`;
      return pressValue(f, v, c, true);
    },

    "listing.unfilter": async ({ facet, value }: { facet: string; value?: string | null }, c: MoveContext) => {
      const on = api.facets.flatMap((x) => x.active.map((v) => (x.kind === "toggle" ? x.name : `${x.name}: ${v}`)));
      const f = facetOf(api, facet, c);
      if (f.kind === "range" || (f.kind === "bands" && !f.active.length && (f.min != null || f.max != null))) return setRange(f, null, null, c);
      if (f.kind === "toggle") {
        if (!f.active.length) c.refuse("facet", on.length ? `on now: ${on.join(", ")}` : "no filter is on", on);
        return pressValue(f, f.name, c, false);
      }
      const v = value ? (f.kind === "bands" ? bandOf(f, value)?.label : optionOf(f, value)) : f.active[0];
      if (!v || !f.active.includes(v)) c.refuse("value", on.length ? `on now: ${on.join(", ")}` : "no filter is on", on);
      return pressValue(f, v, c, false);
    },

    "listing.range": async ({ facet, min, max }: { facet: string; min?: number | null; max?: number | null }, c: MoveContext) => {
      const f = facetOf(api, facet, c, rangeFacets);
      return setRange(f, bound(min), bound(max), c);
    },

    /** The old name for a range on the page's price. */
    "listing.price": async ({ min, max }: { min?: number | null; max?: number | null }, c: MoveContext) => {
      const f = api.facets.find((x) => rangeFacets.includes(x.kind) && fold(x.name) === "price") ?? facetOf(api, "price", c, rangeFacets);
      return setRange(f, bound(min), bound(max), c);
    },

    "listing.clear_filters": async (_args: Record<string, never>, c: MoveContext) => {
      const button = document.querySelector('[data-stage-thing="clear-filters"]');
      if (!button) return `no filters are on — ${pieces(api.countAfter(() => {}))}`;
      await c.scrollTo(button);
      await c.ring(button, "Clear all");
      const count = api.countAfter((n) => {
        for (const f of api.facets) f.clear()(n);
        n.delete("q");
      });
      api.clearAll();
      return `filters cleared — ${pieces(count)}`;
    },

    "listing.sort": async ({ by }: { by: string }, c: MoveContext) => {
      const want = fold(by.trim());
      const s =
        SORTS.find((x) => fold(x.label) === want || fold(x.key) === want) ??
        SORTS.find((x) => fold(x.label).includes(want) && want.length >= 3) ??
        c.refuse("by", `the page sorts by ${SORTS.map((x) => x.label).join(", ")}`, SORTS.map((x) => x.label));
      const el = document.querySelector('[data-stage-thing="sort"]') ?? c.refuse("by", "the sort is not on screen");
      await c.scrollTo(el);
      await c.ring(el, `Sort: ${s.label}`);
      api.setSort(s.key);
      return `sorted by ${s.label.toLowerCase()}`;
    },
  };
}
