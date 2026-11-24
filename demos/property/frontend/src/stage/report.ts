/**
 * What the visitor (or the agent) changed, told as the spec's state events:
 * the page on every route change, the search whenever the filters change, the
 * shortlist whenever it changes. Call once, in the shell.
 */
import { useEffect } from "react";
import { getListing, getProject, search, summarise } from "../data/homes";
import { useStore } from "../state/store";
import { announce, sendEvent } from "./host";

function pageOf(path: string): { page: string; listing_id?: string; title?: string } {
  const listing = /^\/listing\/([^/]+)/.exec(path)?.[1];
  if (listing) return { page: "listing", listing_id: listing, title: getListing(listing)?.title };
  const project = /^\/project\/([^/]+)/.exec(path)?.[1];
  if (project) return { page: "project", title: getProject(project)?.name };
  if (path === "/") return { page: "home", title: "Home" };
  const name = path.slice(1).split("/")[0] || "home";
  return { page: name, title: name[0].toUpperCase() + name.slice(1) };
}

export function useStageReport(path: string, search_: string): void {
  useEffect(() => {
    announce();
    sendEvent("screen.viewed", { path: path + search_, ...pageOf(path) });
  }, [path, search_]);

  useEffect(() => {
    // A move ticks several filters in a row: one event for the lot, 250 ms
    // after the last (still inside the agent's window, so `by` stays right).
    let timer = 0;
    const unsub = useStore.subscribe((s, prev) => {
        if (s.filters !== prev.filters) {
          window.clearTimeout(timer);
          timer = window.setTimeout(() => {
          const f = useStore.getState().filters;
          const results = search(f);
          sendEvent("search.changed", {
            summary: summarise(f),
            count: results.length,
            city: f.city ?? undefined,
            deal: f.deal ?? undefined,
            bhk: f.bhk ?? undefined,
            budget_min: f.budget_min ?? undefined,
            budget_max: f.budget_max ?? undefined,
            possession: f.possession ?? undefined,
            localities: f.localities ?? undefined,
            office: f.office ?? undefined,
            max_km: f.max_km ?? undefined,
            school_km: f.school_km ?? undefined,
            metro_km: f.metro_km ?? undefined,
            amenities: f.amenities ?? undefined,
            ids: results.slice(0, 12).map((l) => l.id),
          });
          }, 250);
        }
        if (s.shortlist !== prev.shortlist) {
          sendEvent("shortlist.changed", { count: s.shortlist.length, ids: s.shortlist });
        }
    });
    return () => {
      window.clearTimeout(timer);
      unsub();
    };
  }, []);
}
