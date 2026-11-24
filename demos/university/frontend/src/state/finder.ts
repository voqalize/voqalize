/**
 * The programme finder: filters, the advisor's picks, the comparison. The
 * sidebar's checkboxes and Stage's performers call the same actions here.
 */
import { create } from "zustand";
import { FACET_NAMES, FACETS, type FacetName, PROGRAMS, type Program, facetByName, programById } from "../data/catalogue";

export type Sort = "fee_asc" | "fee_desc" | "duration";
export type Filters = Record<FacetName, string[]>;

const empty = (): Filters => Object.fromEntries(FACET_NAMES.map((n) => [n, []])) as unknown as Filters;

export interface FinderState {
  filters: Filters;
  picks: string[];
  /** Compare boxes the visitor ticked on cards. */
  ticked: string[];
  /** The ids in the open comparison; empty when it is closed. */
  compared: string[];
  sort: Sort;
  /** The filter panel on a phone. */
  panelOpen: boolean;
  setOption(facet: FacetName, option: string, on: boolean): void;
  clear(facet?: FacetName): void;
  setPicks(ids: string[]): void;
  addPick(id: string): void;
  unpick(id: string): void;
  toggleTick(id: string): void;
  openCompare(ids: string[]): void;
  closeCompare(): void;
  setSort(sort: Sort): void;
  setPanel(open: boolean): void;
}

export const useFinder = create<FinderState>((set) => ({
  filters: empty(),
  picks: [],
  ticked: [],
  compared: [],
  sort: "fee_asc",
  panelOpen: false,
  setOption: (facet, option, on) =>
    set((s) => {
      const cur = s.filters[facet];
      if (on === cur.includes(option)) return s;
      return { filters: { ...s.filters, [facet]: on ? [...cur, option] : cur.filter((x) => x !== option) } };
    }),
  clear: (facet) => set((s) => ({ filters: facet ? { ...s.filters, [facet]: [] } : empty() })),
  setPicks: (ids) => set({ picks: ids.slice(0, 3) }),
  addPick: (id) => set((s) => (s.picks.includes(id) ? s : { picks: [...s.picks, id].slice(-3) })),
  unpick: (id) => set((s) => ({ picks: s.picks.filter((x) => x !== id) })),
  toggleTick: (id) =>
    set((s) => ({ ticked: s.ticked.includes(id) ? s.ticked.filter((x) => x !== id) : [...s.ticked, id].slice(-3) })),
  openCompare: (ids) => set({ compared: ids.slice(0, 3), ticked: ids.slice(0, 3), panelOpen: false }),
  closeCompare: () => set({ compared: [] }),
  setSort: (sort) => set({ sort }),
  setPanel: (open) => set({ panelOpen: open }),
}));

/** Programmes matching `filters`: OR within a facet, AND across facets. */
export function matching(filters: Filters, programs: Program[] = PROGRAMS): Program[] {
  return programs.filter((p) =>
    FACETS.every((f) => {
      const on = filters[f.name];
      return on.length === 0 || f.options.some((o) => on.includes(o.id) && o.match(p));
    }),
  );
}

export function sorted(list: Program[], sort: Sort): Program[] {
  const out = [...list];
  if (sort === "fee_asc") out.sort((a, b) => a.fee_per_year - b.fee_per_year || a.name.localeCompare(b.name));
  if (sort === "fee_desc") out.sort((a, b) => b.fee_per_year - a.fee_per_year || a.name.localeCompare(b.name));
  if (sort === "duration") out.sort((a, b) => a.duration_months - b.duration_months || a.fee_per_year - b.fee_per_year);
  return out;
}

/** What the finder lists: picks the filters hide, pinned on top, then the matches. */
export function listed(s: Pick<FinderState, "filters" | "picks" | "sort">): { pinned: Program[]; results: Program[] } {
  const results = sorted(matching(s.filters), s.sort);
  const shown = new Set(results.map((p) => p.id));
  const pinned = s.picks.filter((id) => !shown.has(id)).map(programById).filter((p): p is Program => !!p);
  return { pinned, results };
}

/** Ticked options as "Level: Postgraduate". */
export function filterLabels(filters: Filters): string[] {
  return FACET_NAMES.flatMap((n) => filters[n].map((id) => `${n}: ${facetByName(n).options.find((o) => o.id === id)?.label ?? id}`));
}

/** How many programmes an option would add on top of the other facets' filters. */
export function optionCount(filters: Filters, facet: FacetName, option: string): number {
  return matching({ ...filters, [facet]: [option] }).length;
}
