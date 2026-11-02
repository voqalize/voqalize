/**
 * Emily filters the page you are on (CONTRACT.md v5). These are the listing
 * page's Stage performers. Each one finds the rail's own control
 * (`data-stage-part="<Facet>:<Value>"`), rings it and then presses it the
 * way a click does, so the URL, the grid and the count all change through
 * the same handler as a shopper's tap. Each answers in one line, and an
 * option this page does not offer is refused with the ones it does.
 */
import type { MoveContext } from "@voqalize/stage";
import { fold } from "@voqalize/stage";
import { SORTS } from "../data/catalog";

/** What the page hands its performers. */
export interface ListingApi {
  /** The rail's facets and their options, by the labels the rail shows. */
  facets: Record<string, string[]>;
  /** What is on, by the same labels. */
  active: Record<string, string[]>;
  /** The count the grid would show after this URL change, without making it. */
  countAfter(mut: (n: URLSearchParams) => void): number;
  /** The URL change a click on this option makes. */
  toggleMut(facet: string, value: string): (n: URLSearchParams) => void;
  setPrice(min: number | null, max: number | null): void;
  setSort(key: string): void;
  clearAll(): void;
  /** The phone's filter sheet: open it so a ring is seen, close it after. */
  openSheet(): void;
  closeSheet(): void;
  sheetOpen(): boolean;
}

const pieces = (n: number) => `${n} ${n === 1 ? "piece" : "pieces"}`;

/** The rail's own name for a facet the voice said, or null. */
function facetOf(api: ListingApi, said: string): string | null {
  const want = fold(said.trim());
  return Object.keys(api.facets).find((f) => fold(f) === want) ?? null;
}
function valueOf(options: string[], said: string): string | null {
  const want = fold(said.trim());
  return options.find((v) => fold(v) === want) ?? options.find((v) => fold(v).startsWith(want) && want.length >= 3) ?? null;
}

const part = (facet: string, value: string) =>
  [...document.querySelectorAll(`[data-stage-part="${CSS.escape(`${facet}:${value}`)}"]`)].find((el) => el.closest(".rail-filters")) ?? null;

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
    if (opened) c.after(async () => {
      await c.beat(700);
      api.closeSheet();
    });
  }
}

/** Ring an option's control, then press it as a click does. */
async function press(c: MoveContext, el: Element, label: string) {
  // The rail scrolls on its own (sticky on a wide screen, a sheet on a phone):
  // bring the option into its view first, then the page.
  el.scrollIntoView({ block: "center" });
  await c.scrollTo(el);
  await c.ring(el, label);
  const input = el.querySelector("input") ?? (el instanceof HTMLButtonElement ? el : null);
  (input as HTMLElement | null)?.click();
}

export function listingPerformers(api: ListingApi) {
  return {
    "listing.filter": async ({ facet, value }: { facet: string; value: string }, c: MoveContext) => {
      const f = facetOf(api, facet) ?? c.refuse("facet", `this page filters by ${Object.keys(api.facets).join(", ")}`, Object.keys(api.facets));
      const v = valueOf(api.facets[f], value) ?? c.refuse("value", `${f} here is ${api.facets[f].join(", ")}`, api.facets[f]);
      if (api.active[f]?.includes(v)) return `${f}: ${v} is already on — ${pieces(api.countAfter(() => {}))}`;
      return onRail(api, c, async () => {
        const el = (await appear(() => part(f, v))) ?? c.refuse("value", `${f}: ${v} is not on screen`, api.facets[f]);
        const count = api.countAfter(api.toggleMut(f, v));
        await press(c, el, `${f}: ${v}`);
        return `${f}: ${v} on — ${pieces(count)}`;
      });
    },

    "listing.unfilter": async ({ facet, value }: { facet: string; value: string }, c: MoveContext) => {
      const on = Object.entries(api.active).flatMap(([k, vs]) => vs.map((x) => `${k}: ${x}`));
      const f = facetOf(api, facet);
      const v = f ? valueOf(api.active[f] ?? [], value) : null;
      if (!f || !v) c.refuse("value", on.length ? `on now: ${on.join(", ")}` : "no filter is on", on);
      return onRail(api, c, async () => {
        const el = (await appear(() => part(f!, v!))) ?? c.refuse("value", `${f}: ${v} is not on screen`, on);
        const count = api.countAfter(api.toggleMut(f!, v!));
        await press(c, el, `${f}: ${v}`);
        return `${f}: ${v} off — ${pieces(count)}`;
      });
    },

    "listing.clear_filters": async (_args: Record<string, never>, c: MoveContext) => {
      const button = document.querySelector('[data-stage-thing="clear-filters"]');
      if (!button) return `no filters are on — ${pieces(api.countAfter(() => {}))}`;
      await c.scrollTo(button);
      await c.ring(button, "Clear all");
      const count = api.countAfter((n) => ["cat", "sale", "min", "max", "opt", "q"].forEach((k) => n.delete(k)));
      api.clearAll();
      return `filters cleared — ${pieces(count)}`;
    },

    "listing.price": async ({ min, max }: { min?: number | null; max?: number | null }, c: MoveContext) => {
      const lo = min == null || (min as unknown) === "" ? null : Math.round(Number(min));
      const hi = max == null || (max as unknown) === "" ? null : Math.round(Number(max));
      if ((lo != null && Number.isNaN(lo)) || (hi != null && Number.isNaN(hi))) c.refuse("min", "say the price in dollars");
      if (lo != null && hi != null && lo > hi) c.refuse("max", `the highest price is below the lowest, ${lo}`);
      return onRail(api, c, async () => {
        const el = (await appear(() => document.querySelector('.rail-filters [data-stage-thing="price"]'))) ?? c.refuse("min", "the price filter is not on screen");
        el.scrollIntoView({ block: "center" });
        await c.scrollTo(el);
        await c.ring(el, "Price");
        const count = api.countAfter((n) => {
          lo == null ? n.delete("min") : n.set("min", String(lo));
          hi == null ? n.delete("max") : n.set("max", String(hi));
        });
        api.setPrice(lo, hi);
        const range = lo != null && hi != null ? `$${lo}–$${hi}` : hi != null ? `up to $${hi}` : lo != null ? `from $${lo}` : "any price";
        return `price ${range} — ${pieces(count)}`;
      });
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
